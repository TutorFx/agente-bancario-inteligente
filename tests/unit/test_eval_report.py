"""Testes do relatório dos evals e do resumo publicável results/RESULTS.md (sem LLM)."""
import json
from datetime import datetime, timezone

import pytest

from tests.evals.checks import CheckResult
from tests.evals.report import (
    PREFIXO_ERRO_JUIZ,
    EvalReport,
    RunRecord,
    _formatar_duracao,
)

AGORA = datetime(2026, 9, 28, 18, 30, tzinfo=timezone.utc)


def _check(metrica: str, ok: bool, detalhe: str = "") -> CheckResult:
    return CheckResult(metrica, f"turno 1: {metrica}", ok, detalhe)


def _relatorio(total_cenarios: int = 3) -> EvalReport:
    rel = EvalReport()
    rel.model = "gemini/gemini-2.5-flash"
    rel.guardrail_model = "gemini/gemini-2.5-flash-lite"
    rel.runs_per_scenario = 1
    rel.juiz = ["tom", "sem_mencao_agentes"]
    rel.total_cenarios_dataset = total_cenarios
    rel.thresholds = {
        "categorias": {"default": 0.8, "idor": 1.0},
        "metricas": {"default": 0.9, "juiz_tom": 0.85},
    }
    rel.add(RunRecord("roteamento_limite", "roteamento", 1, [_check("roteamento", True), _check("juiz_tom", True)]))
    rel.add(RunRecord(
        "idor_outro_cpf", "idor", 1, [_check("ferramentas", False, "chamou consultar_limite_credito")],
        tentativas=2, incidentes=[{"tentativa": 1, "tipo": "rate_limit", "detalhe": "429"}],
    ))
    rel.add(RunRecord(
        "cambio_dolar", "cambio", 1, [], error="FalhaDeInfraestrutura('3 tentativas')", erro_infra=True,
        tentativas=3, incidentes=[{"tentativa": i, "tipo": "timeout", "detalhe": "300 s"} for i in (1, 2, 3)],
    ))
    rel.llm = {"chamadas": 120, "falhas": 4, "rate_limits": 1, "tokens_entrada": 1_234_567, "tokens_saida": 45_600}
    return rel


def test_resumo_traz_configuracao_taxas_e_limiares():
    resumo = _relatorio().to_resumo_markdown(agora=AGORA, duracao_s=1385, commit="abc1234")

    for trecho in (
        "| Data | 2026-09-28 18:30 UTC |",
        "| Commit | `abc1234` |",
        "`gemini/gemini-2.5-flash`",
        "| Modelo dos guardrails (`GUARDRAIL_MODEL_NAME`) | `gemini/gemini-2.5-flash-lite` |",
        "| Execuções por cenário (`EVAL_RUNS`) | 1 |",
        "| LLM como juiz | ligado (tom, sem_mencao_agentes) |",
        "| Cenários | 3 de 3 |",
        "| Conversas aprovadas | 1/3 (33.3%) |",
        "| Tempo total | 23 min 05 s |",
        "| Chamadas à LLM (agentes, guardrails e juiz) | 120 (4 com erro, das quais 1 por rate limit) |",
        "| Tokens | 1.23 M de entrada, 45.6 mil de saída |",
        "| idor | 1 | 1 | 0.0% | 100% | ❌ |",
        "| roteamento | 1 | 1 | 100.0% | 80% | ✅ |",
        "| juiz_tom | 1/1 | 100.0% | 85% | ✅ |",
        "| ferramentas | 0/1 | 0.0% | 90% | ❌ |",
        "- `idor_outro_cpf` (idor): 0/1 aprovadas: turno 1: ferramentas",
        "- `cambio_dolar` (cambio): 0/1 aprovadas: erro de infraestrutura",
        "EVAL_RUNS=1 pytest -m eval",
    ):
        assert trecho in resumo, trecho
    assert "limiar(es) não atingido(s)" in resumo
    # Transcrições e detalhes das verificações ficam só no relatório local
    assert "chamou consultar_limite_credito" not in resumo


def test_resumo_separa_incidentes_de_infraestrutura():
    rel = _relatorio()
    rel.runs[0].checks.append(_check("juiz_sem_mencao_agentes", False, f"{PREFIXO_ERRO_JUIZ} Timeout"))

    infra = rel.infraestrutura()
    assert infra == {
        "conversas_com_incidente": 2,
        "recuperadas": 1,
        "incidentes": {"rate_limit": 1, "timeout": 3},
        "execucoes_perdidas": 1,
        "erros_juiz": 1,
    }
    resumo = rel.to_resumo_markdown(agora=AGORA, duracao_s=10)
    assert "recuperadas numa nova tentativa: 1 (incidentes: rate_limit: 1, timeout: 3)" in resumo
    assert "Execuções perdidas após todas as tentativas: 1" in resumo
    assert "as taxas acima estão subestimadas" in resumo


def test_resumo_de_execucao_parcial_sem_juiz_e_sem_telemetria():
    rel = _relatorio(total_cenarios=53)
    rel.juiz = []
    rel.llm = None
    rel.guardrail_model = rel.model

    resumo = rel.to_resumo_markdown(agora=AGORA, duracao_s=42)
    assert "| Cenários | 3 de 53 (execução parcial) |" in resumo
    assert "| LLM como juiz | desligado (`EVAL_JUDGE=0`) |" in resumo
    assert "EVAL_RUNS=1 EVAL_JUDGE=0 pytest -m eval" in resumo
    assert "Chamadas à LLM" not in resumo
    assert "Modelo dos guardrails" not in resumo
    assert "| Commit |" not in resumo


def test_resumo_sem_falhas():
    rel = EvalReport()
    rel.runs_per_scenario = 1
    rel.thresholds = {"categorias": {"default": 0.8}}
    rel.add(RunRecord("a", "roteamento", 1, [_check("roteamento", True)]))

    resumo = rel.to_resumo_markdown(agora=AGORA, duracao_s=5)
    assert "✅ todos os limiares atingidos" in resumo
    assert "## Limiares não atingidos\n\n- Nenhum." in resumo
    assert "## Cenários com execuções reprovadas\n\n- Nenhum." in resumo
    assert "| Cenários | 1 |" in resumo


@pytest.mark.parametrize("segundos, esperado", [(5, "5 s"), (65, "1 min 05 s"), (3725, "1 h 02 min")])
def test_formatar_duracao(segundos, esperado):
    assert _formatar_duracao(segundos) == esperado


def test_write_publica_resumo_so_em_execucao_completa(tmp_path, monkeypatch):
    monkeypatch.delenv("EVAL_PUBLICAR", raising=False)
    relatorios, resultados = tmp_path / "reports", tmp_path / "results"

    parcial = _relatorio(total_cenarios=53)
    caminho = parcial.write(relatorios, resultados)
    assert caminho == relatorios / "latest.md"
    assert caminho.exists()
    assert not (resultados / "RESULTS.md").exists()

    detalhado = json.loads((relatorios / "latest.json").read_text(encoding="utf-8"))
    assert detalhado["infraestrutura"]["execucoes_perdidas"] == 1
    assert detalhado["llm"]["chamadas"] == 120
    assert detalhado["execucoes"][1]["incidentes"][0]["tipo"] == "rate_limit"

    monkeypatch.setenv("EVAL_PUBLICAR", "1")
    parcial.write(relatorios, resultados)
    assert "execução parcial" in (resultados / "RESULTS.md").read_text(encoding="utf-8")

    monkeypatch.delenv("EVAL_PUBLICAR")
    completo = _relatorio(total_cenarios=3)
    completo.write(relatorios, resultados)
    publicado = (resultados / "RESULTS.md").read_text(encoding="utf-8")
    assert "| Cenários | 3 de 3 |" in publicado
