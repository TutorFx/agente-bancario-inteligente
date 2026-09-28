"""Agregação das execuções em taxas de acerto por cenário, categoria e métrica."""
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tests.evals.checks import CheckResult

REPORT_DIR = Path(__file__).parent / "reports"


@dataclass
class RunRecord:
    scenario: str
    category: str
    run: int
    checks: list[CheckResult]
    transcript: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.passed for c in self.checks)


class EvalReport:
    def __init__(self) -> None:
        self.runs: list[RunRecord] = []
        self.thresholds: dict = {}
        self.runs_per_scenario = 0
        self.model = ""

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
            linhas.append(f"| {cat} | {info['scenarios']} | {info['runs']} | {info['rate']:.1%}{status} | {'' if lim is None else f'{lim:.0%}'} |")
        linhas += ["", "## Por métrica", "", "| Métrica | Verificações | Taxa de acerto | Limiar |", "| :--- | ---: | ---: | ---: |"]
        for m, info in self.por_metrica().items():
            lim = self.limiar("metricas", m)
            status = "" if lim is None else (" ✅" if info["rate"] >= lim else " ❌")
            linhas.append(f"| {m} | {info['passed']}/{info['total']} | {info['rate']:.1%}{status} | {'' if lim is None else f'{lim:.0%}'} |")
        linhas += ["", "## Por cenário", "", "| Cenário | Categoria | Aprovadas | Taxa | Falhas |", "| :--- | :--- | ---: | ---: | :--- |"]
        for sid, info in self.por_cenario().items():
            falhas = "<br>".join(f.replace("|", "\\|") for f in info["failed_checks"][:4])
            linhas.append(f"| {sid} | {info['category']} | {info['passed']}/{info['runs']} | {info['rate']:.0%} | {falhas} |")
        violacoes = self.violacoes()
        linhas += ["", "## Limiares", ""]
        linhas += [f"- ❌ {v}" for v in violacoes] or ["- ✅ Todos os limiares mínimos foram atingidos."]
        return "\n".join(linhas) + "\n"

    def write(self) -> Path:
        REPORT_DIR.mkdir(exist_ok=True)
        (REPORT_DIR / "latest.md").write_text(self.to_markdown(), encoding="utf-8")
        payload = {
            "model": self.model,
            "runs_per_scenario": self.runs_per_scenario,
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
        (REPORT_DIR / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return REPORT_DIR / "latest.md"


report = EvalReport()
