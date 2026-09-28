"""
Suíte de avaliação (evals) do comportamento dos agentes.

Fora do `pytest` padrão; execute com `pytest -m eval`. Variáveis de ambiente:
- EVAL_RUNS: execuções por cenário (padrão em dataset.yaml), para medir o não determinismo.
- EVAL_JUDGE=0: desliga as métricas com LLM como juiz (mais rápido e barato).
- EVAL_PAUSA_SEGUNDOS, EVAL_TIMEOUT_CONVERSA, EVAL_TENTATIVAS, EVAL_ESPERA_RATE_LIMIT:
  ritmo e tolerância a erros do provedor (ver harness.py); EVAL_TIMEOUT_JUIZ (ver judge.py).
- EVAL_PUBLICAR=1: grava results/RESULTS.md mesmo numa execução parcial (ver report.py).
"""
import asyncio
import os
import time
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from root_agent.config import GUARDRAIL_MODEL_NAME, LLM_MODEL_NAME
from tests.evals.checks import avaliar
from tests.evals.harness import FalhaDeInfraestrutura, executar_com_retentativas
from tests.evals.report import RunRecord, report

pytestmark = pytest.mark.eval

DATASET = yaml.safe_load((Path(__file__).parent / "dataset.yaml").read_text(encoding="utf-8"))
CONFIG = DATASET["config"]
CLIENTES = DATASET["clientes"]
RUNS = int(os.getenv("EVAL_RUNS", CONFIG["runs"]))
JUIZ_ATIVO = os.getenv("EVAL_JUDGE", "1") != "0"

report.thresholds = DATASET["thresholds"]
report.runs_per_scenario = RUNS
report.model = LLM_MODEL_NAME
report.guardrail_model = GUARDRAIL_MODEL_NAME
report.juiz = list(CONFIG["judge"]) if JUIZ_ATIVO else []
report.total_cenarios_dataset = len(DATASET["scenarios"])


@pytest.mark.parametrize("scenario", DATASET["scenarios"], ids=lambda s: s["id"])
async def test_cenario(scenario):
    alias = scenario.get("auth")
    cliente = CLIENTES[alias] if alias else None
    mensagens = [t["user"] for t in scenario["turns"]]
    criterios = scenario.get("judge", CONFIG["judge"]) if JUIZ_ATIVO else []

    registros = []
    for run in range(1, RUNS + 1):
        inicio = time.monotonic()
        try:
            result = await executar_com_retentativas(mensagens, cliente, scenario.get("state"))
        except FalhaDeInfraestrutura as exc:
            registro = RunRecord(
                scenario["id"], scenario["category"], run, [], error=repr(exc),
                erro_infra=True, tentativas=len(exc.incidentes), incidentes=exc.incidentes,
            )
        except Exception as exc:
            registro = RunRecord(scenario["id"], scenario["category"], run, [], error=repr(exc))
        else:
            checks = avaliar(result, scenario, CLIENTES)
            if criterios:
                # Import tardio: o DeepEval só é exigido com o juiz ligado, e a coleta do
                # `pytest` padrão continua funcionando só com o requirements.txt
                from tests.evals.judge import julgar
                checks += await julgar(result, criterios)
            transcript = [
                {"user": t.user, "reply": t.reply, "agent": t.agent, "transfers": t.transfers,
                 "tool_calls": [asdict(c) for c in t.tool_calls], "tool_responses": t.tool_responses}
                for t in result.turns
            ]
            registro = RunRecord(
                scenario["id"], scenario["category"], run, checks, transcript,
                tentativas=result.tentativas, incidentes=result.incidentes,
            )
        registro.duracao_s = round(time.monotonic() - inicio, 1)
        report.add(registro)
        registros.append(registro)

    # O LiteLLM registra o uso das chamadas bem-sucedidas numa task em segundo plano;
    # cede o loop antes que ele seja fechado ao fim do teste, para a contagem de tokens não perder a última
    await asyncio.sleep(0.1)

    aprovadas = sum(r.passed for r in registros)
    minimo = scenario.get("min_pass_rate", CONFIG["min_pass_rate"])
    falhas = sorted({f"[run {r.run}] {c.name}: {c.detail[:200]}" for r in registros for c in r.checks if not c.passed}
                    | {f"[run {r.run}] erro: {r.error}" for r in registros if r.error})
    assert aprovadas / RUNS >= minimo, (
        f"{scenario['id']}: {aprovadas}/{RUNS} execuções aprovadas (mínimo {minimo:.0%})\n" + "\n".join(falhas)
    )
