"""
Agregação das execuções em taxas de acerto por cenário, categoria e métrica.

Saídas:
- reports/latest.md e latest.json: relatório detalhado com transcrições (local, fora do git).
- results/RESULTS.md: resumo compacto para publicar no repositório. Só é reescrito quando a
  execução cobre todos os cenários do dataset (ou com EVAL_PUBLICAR=1), para que um
  `pytest -m eval -k ...` parcial não substitua o resultado publicado.
"""
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tests.evals.checks import CheckResult

REPORT_DIR = Path(__file__).parent / "reports"
RESULTS_DIR = Path(__file__).parent / "results"
PREFIXO_ERRO_JUIZ = "erro do juiz:"


@dataclass
class RunRecord:
    scenario: str
    category: str
    run: int
    checks: list[CheckResult]
    transcript: list[dict] = field(default_factory=list)
    error: str | None = None
    erro_infra: bool = False  # a conversa não rodou por infraestrutura (rate limit, timeout...)
    tentativas: int = 1
    incidentes: list[dict[str, Any]] = field(default_factory=list)
    duracao_s: float = 0.0

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.passed for c in self.checks)


def _formatar_duracao(segundos: float) -> str:
    minutos, seg = divmod(round(segundos), 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas} h {minutos:02d} min"
    return f"{minutos} min {seg:02d} s" if minutos else f"{seg} s"


def _formatar_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f} M"
    if n >= 1_000:
        return f"{n / 1_000:.1f} mil"
    return str(n)


def _commit_atual() -> str | None:
    try:
        saida = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, check=False,
            cwd=Path(__file__).parent,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return saida.stdout.strip() or None


def _status(taxa: float, limiar: float | None) -> str:
    return "" if limiar is None else ("✅" if taxa >= limiar else "❌")


def _pct(limiar: float | None) -> str:
    return "" if limiar is None else f"{limiar:.0%}"


class EvalReport:
    def __init__(self) -> None:
        self.runs: list[RunRecord] = []
        self.thresholds: dict = {}
        self.runs_per_scenario = 0
        self.model = ""
        self.guardrail_model = ""
        self.juiz: list[str] = []  # critérios padrão do juiz; vazio = juiz desligado
        self.total_cenarios_dataset = 0
        self.llm: dict[str, int] | None = None  # consumo total (telemetria.ConsumoLLM.como_dict)
        self.inicio = time.monotonic()

    def add(self, record: RunRecord) -> None:
        self.runs.append(record)

    @staticmethod
    def _taxa(acertos: int, total: int) -> float:
        return acertos / total if total else 0.0

    def por_cenario(self) -> dict[str, dict]:
        grupos: dict[str, list[RunRecord]] = defaultdict(list)
        for r in self.runs:
            grupos[r.scenario].append(r)
        return {
            sid: {
                "category": rs[0].category,
                "runs": len(rs),
                "passed": sum(r.passed for r in rs),
                "rate": self._taxa(sum(r.passed for r in rs), len(rs)),
                "failed_checks": sorted({f"{c.name} ({c.detail[:160]})" for r in rs for c in r.checks if not c.passed}
                                        | {f"erro: {r.error[:160]}" for r in rs if r.error}),
            }
            for sid, rs in grupos.items()
        }

    def por_categoria(self) -> dict[str, dict]:
        grupos: dict[str, list[RunRecord]] = defaultdict(list)
        for r in self.runs:
            grupos[r.category].append(r)
        return {
            cat: {
                "scenarios": len({r.scenario for r in rs}),
                "runs": len(rs),
                "rate": self._taxa(sum(r.passed for r in rs), len(rs)),
            }
            for cat, rs in sorted(grupos.items())
        }

    def por_metrica(self) -> dict[str, dict]:
        totais: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in self.runs:
            for c in r.checks:
                totais[c.metric][0] += c.passed
                totais[c.metric][1] += 1
        return {
            m: {"passed": ok, "total": tot, "rate": self._taxa(ok, tot)}
            for m, (ok, tot) in sorted(totais.items())
        }

    def violacoes(self) -> list[str]:
        """Categorias/métricas abaixo do limiar mínimo configurado no dataset."""
        falhas = []
        for grupo, dados in (("categorias", self.por_categoria()), ("metricas", self.por_metrica())):
            limiares = self.thresholds.get(grupo, {})
            padrao = limiares.get("default")
            for nome, info in dados.items():
                limiar = limiares.get(nome, padrao)
                if limiar is not None and info["rate"] < limiar:
                    falhas.append(f"{grupo[:-1]} '{nome}': {info['rate']:.1%} < {limiar:.0%}")
        return falhas

    def limiar(self, grupo: str, nome: str):
        limiares = self.thresholds.get(grupo, {})
        return limiares.get(nome, limiares.get("default"))

    def infraestrutura(self) -> dict[str, Any]:
        """Erros do provedor, separados das falhas de comportamento para a leitura do resultado."""
        return {
            "conversas_com_incidente": sum(bool(r.incidentes) for r in self.runs),
            "recuperadas": sum(bool(r.incidentes) and not r.erro_infra for r in self.runs),
            "incidentes": dict(sorted(Counter(i["tipo"] for r in self.runs for i in r.incidentes).items())),
            "execucoes_perdidas": sum(r.erro_infra for r in self.runs),
            "erros_juiz": sum(
                c.metric.startswith("juiz_") and c.detail.startswith(PREFIXO_ERRO_JUIZ)
                for r in self.runs for c in r.checks
            ),
        }

    def _motivos(self, cenario: str) -> list[str]:
        """Nomes das verificações reprovadas (sem detalhes nem transcrição) e erros por tipo."""
        motivos: set[str] = set()
        for r in self.runs:
            if r.scenario != cenario:
                continue
            if r.error:
                motivos.add("erro de infraestrutura" if r.erro_infra else f"erro: {r.error.split('(')[0]}")
            motivos.update(c.name for c in r.checks if not c.passed)
        return sorted(motivos)

    @property
    def execucao_completa(self) -> bool:
        return bool(self.total_cenarios_dataset) and len(self.por_cenario()) >= self.total_cenarios_dataset

    def duracao_s(self) -> float:
        return time.monotonic() - self.inicio

    def to_markdown(self) -> str:
        total = len(self.runs)
        aprovadas = sum(r.passed for r in self.runs)
        linhas = [
            "# Relatório de avaliação dos agentes",
            "",
            f"- Data: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"- Modelo: `{self.model}`",
            f"- Execuções por cenário: {self.runs_per_scenario}",
            f"- Conversas aprovadas: {aprovadas}/{total} ({self._taxa(aprovadas, total):.1%})",
            "",
            "## Por categoria",
            "",
            "| Categoria | Cenários | Execuções | Taxa de acerto | Limiar |",
            "| :--- | ---: | ---: | ---: | ---: |",
        ]
        for cat, info in self.por_categoria().items():
            lim = self.limiar("categorias", cat)
            status = "" if lim is None else (" ✅" if info["rate"] >= lim else " ❌")
            linhas.append(f"| {cat} | {info['scenarios']} | {info['runs']} | {info['rate']:.1%}{status} | {_pct(lim)} |")
        linhas += ["", "## Por métrica", "", "| Métrica | Verificações | Taxa de acerto | Limiar |", "| :--- | ---: | ---: | ---: |"]
        for m, info in self.por_metrica().items():
            lim = self.limiar("metricas", m)
            status = "" if lim is None else (" ✅" if info["rate"] >= lim else " ❌")
            linhas.append(f"| {m} | {info['passed']}/{info['total']} | {info['rate']:.1%}{status} | {_pct(lim)} |")
        linhas += ["", "## Por cenário", "", "| Cenário | Categoria | Aprovadas | Taxa | Falhas |", "| :--- | :--- | ---: | ---: | :--- |"]
        for sid, info in self.por_cenario().items():
            falhas = "<br>".join(f.replace("|", "\\|") for f in info["failed_checks"][:4])
            linhas.append(f"| {sid} | {info['category']} | {info['passed']}/{info['runs']} | {info['rate']:.0%} | {falhas} |")
        violacoes = self.violacoes()
        linhas += ["", "## Limiares", ""]
        linhas += [f"- ❌ {v}" for v in violacoes] or ["- ✅ Todos os limiares mínimos foram atingidos."]
        return "\n".join(linhas) + "\n"

    def to_resumo_markdown(
        self,
        agora: datetime | None = None,
        duracao_s: float | None = None,
        commit: str | None = None,
    ) -> str:
        """Resumo compacto e versionado (results/RESULTS.md): o que o README cita como resultado."""
        agora = agora or datetime.now(timezone.utc)
        duracao_s = self.duracao_s() if duracao_s is None else duracao_s
        total = len(self.runs)
        aprovadas = sum(r.passed for r in self.runs)
        cenarios = self.por_cenario()
        violacoes = self.violacoes()
        infra = self.infraestrutura()
        juiz = f"ligado ({', '.join(self.juiz)})" if self.juiz else "desligado (`EVAL_JUDGE=0`)"

        cobertura = str(len(cenarios))
        if self.total_cenarios_dataset:
            cobertura += f" de {self.total_cenarios_dataset}"
            if not self.execucao_completa:
                cobertura += " (execução parcial)"
        linhas = [
            "# Resultados da avaliação dos agentes",
            "",
            "> Gerado por `pytest -m eval` (tests/evals/report.py); não edite à mão.",
            "> Detalhes por cenário e transcrições: `tests/evals/reports/latest.md` e `latest.json` (locais, fora do git).",
            "",
            "| Item | Valor |",
            "| :--- | :--- |",
            f"| Data | {agora.strftime('%Y-%m-%d %H:%M UTC')} |",
        ]
        if commit:
            linhas.append(f"| Commit | `{commit}` |")
        linhas.append(f"| Modelo dos agentes (`LLM_MODEL_NAME`) | `{self.model}` |")
        if self.guardrail_model and self.guardrail_model != self.model:
            linhas.append(f"| Modelo dos guardrails (`GUARDRAIL_MODEL_NAME`) | `{self.guardrail_model}` |")
        linhas += [
            f"| Execuções por cenário (`EVAL_RUNS`) | {self.runs_per_scenario} |",
            f"| LLM como juiz | {juiz} |",
            f"| Cenários | {cobertura} |",
            f"| Conversas aprovadas | {aprovadas}/{total} ({self._taxa(aprovadas, total):.1%}) |",
            f"| Tempo total | {_formatar_duracao(duracao_s)} |",
        ]
        if self.llm:
            linhas += [
                (f"| Chamadas à LLM (agentes, guardrails e juiz) | {self.llm.get('chamadas', 0)}"
                 f" ({self.llm.get('falhas', 0)} com erro, das quais {self.llm.get('rate_limits', 0)} por rate limit) |"),
                (f"| Tokens | {_formatar_tokens(self.llm.get('tokens_entrada', 0))} de entrada, "
                 f"{_formatar_tokens(self.llm.get('tokens_saida', 0))} de saída |"),
            ]
        linhas.append(
            f"| Resultado | {'✅ todos os limiares atingidos' if not violacoes else f'❌ {len(violacoes)} limiar(es) não atingido(s)'} |"
        )

        linhas += ["", "## Por categoria", "", "| Categoria | Cenários | Execuções | Acerto | Limiar | |",
                   "| :--- | ---: | ---: | ---: | ---: | :---: |"]
        for cat, info in self.por_categoria().items():
            lim = self.limiar("categorias", cat)
            linhas.append(f"| {cat} | {info['scenarios']} | {info['runs']} | {info['rate']:.1%} | {_pct(lim)} | {_status(info['rate'], lim)} |")

        linhas += ["", "## Por métrica", "", "| Métrica | Verificações | Acerto | Limiar | |",
                   "| :--- | ---: | ---: | ---: | :---: |"]
        for m, info in self.por_metrica().items():
            lim = self.limiar("metricas", m)
            linhas.append(f"| {m} | {info['passed']}/{info['total']} | {info['rate']:.1%} | {_pct(lim)} | {_status(info['rate'], lim)} |")

        incidentes = ", ".join(f"{tipo}: {n}" for tipo, n in infra["incidentes"].items()) or "nenhum"
        linhas += [
            "",
            "## Infraestrutura",
            "",
            "Erros do provedor (429, timeout, 5xx) não contam como falha de comportamento quando uma nova",
            "tentativa da conversa resolve; se todas as tentativas falham, a execução conta como reprovada.",
            "",
            (f"- Conversas com incidente: {infra['conversas_com_incidente']}, recuperadas numa nova tentativa: "
             f"{infra['recuperadas']} (incidentes: {incidentes})"),
            f"- Execuções perdidas após todas as tentativas: {infra['execucoes_perdidas']}",
            f"- Verificações do juiz com erro: {infra['erros_juiz']}",
        ]
        if infra["execucoes_perdidas"] or infra["erros_juiz"]:
            linhas += ["", "> ⚠️ Houve perdas por infraestrutura: as taxas acima estão subestimadas; reexecute a suíte."]

        linhas += ["", "## Limiares não atingidos", ""]
        linhas += [f"- {v}" for v in violacoes] or ["- Nenhum."]

        reprovados = [(sid, info) for sid, info in sorted(cenarios.items()) if info["passed"] < info["runs"]]
        linhas += ["", "## Cenários com execuções reprovadas", ""]
        linhas += [
            f"- `{sid}` ({info['category']}): {info['passed']}/{info['runs']} aprovadas: {'; '.join(self._motivos(sid)[:3])}"
            for sid, info in reprovados
        ] or ["- Nenhum."]

        comando = f"EVAL_RUNS={self.runs_per_scenario}{'' if self.juiz else ' EVAL_JUDGE=0'} pytest -m eval"
        linhas += ["", "## Como reproduzir", "", "```bash", comando, "```"]
        return "\n".join(linhas) + "\n"

    def to_json(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "guardrail_model": self.guardrail_model,
            "runs_per_scenario": self.runs_per_scenario,
            "juiz": self.juiz,
            "total_cenarios_dataset": self.total_cenarios_dataset,
            "duracao_s": round(self.duracao_s(), 1),
            "llm": self.llm,
            "infraestrutura": self.infraestrutura(),
            "categorias": self.por_categoria(),
            "metricas": self.por_metrica(),
            "cenarios": self.por_cenario(),
            "violacoes": self.violacoes(),
            "execucoes": [
                {**{k: v for k, v in asdict(r).items() if k != "checks"},
                 "passed": r.passed,
                 "checks": [asdict(c) for c in r.checks]}
                for r in self.runs
            ],
        }

    def deve_publicar(self) -> bool:
        """Só execuções completas substituem o resumo versionado (EVAL_PUBLICAR=1 força)."""
        return self.execucao_completa or os.getenv("EVAL_PUBLICAR") == "1"

    def write(self, report_dir: Path = REPORT_DIR, results_dir: Path = RESULTS_DIR) -> Path:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "latest.md").write_text(self.to_markdown(), encoding="utf-8")
        (report_dir / "latest.json").write_text(
            json.dumps(self.to_json(), ensure_ascii=False, indent=2, default=str), encoding="utf-8",
        )
        if self.deve_publicar():
            results_dir.mkdir(parents=True, exist_ok=True)
            (results_dir / "RESULTS.md").write_text(self.to_resumo_markdown(commit=_commit_atual()), encoding="utf-8")
        return report_dir / "latest.md"


report = EvalReport()
