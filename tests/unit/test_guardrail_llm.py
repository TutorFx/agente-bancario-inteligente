"""Testes da chamada compartilhada à LLM dos guardrails: rótulo, timeout, falhas e métricas por turno."""

import logging
import time
from unittest.mock import MagicMock

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types

from root_agent import config
from root_agent.application.middlewares import guardrail_llm
from root_agent.application.middlewares.guardrail_llm import FalhaGuardrail, consultar_llm_guardrail
from root_agent.domain.conversation_state import GUARDRAIL_METRICAS_KEY

ROTULOS = ("SEGURO", "FORA_DE_ESCOPO", "ATAQUE")


def _ctx(state=None, turno="e-turno-1", agente="agente_triagem"):
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {} if state is None else state
    ctx.invocation_id = turno
    ctx.agent_name = agente
    return ctx


async def _consultar(ctx, conteudo="mensagem do cliente"):
    return await consultar_llm_guardrail(
        ctx, guardrail="entrada", instrucao="REGRAS", conteudo=conteudo, rotulos=ROTULOS
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("resposta, esperado", [
    ("SEGURO", "SEGURO"),
    ("**ATAQUE**\n", "ATAQUE"),
    ("fora de escopo.", "FORA_DE_ESCOPO"),
    ("Classificação: FORA_DE_ESCOPO", "FORA_DE_ESCOPO"),
])
async def test_rotulo_tolera_formatacao(modelo_guardrail, resposta, esperado):
    modelo_guardrail(resposta)
    assert await _consultar(_ctx()) == esperado


@pytest.mark.asyncio
@pytest.mark.parametrize("resposta", ["", "talvez", "INSEGURO", "SEGURO ou ATAQUE"])
async def test_resposta_fora_do_formato_vira_falha(modelo_guardrail, resposta):
    modelo_guardrail(resposta)
    with pytest.raises(FalhaGuardrail, match="resposta_invalida"):
        await _consultar(_ctx())


@pytest.mark.asyncio
async def test_timeout_vira_falha_sem_esperar_a_llm(modelo_guardrail, monkeypatch):
    monkeypatch.setattr(config, "GUARDRAIL_TIMEOUT_SEGUNDOS", 0.05)
    modelo_guardrail("SEGURO", atraso=5)

    inicio = time.perf_counter()
    with pytest.raises(FalhaGuardrail, match="timeout"):
        await _consultar(_ctx())
    assert time.perf_counter() - inicio < 1


@pytest.mark.asyncio
async def test_erro_do_provedor_vira_falha(modelo_guardrail):
    modelo_guardrail(erro=RuntimeError("provedor fora do ar"))
    with pytest.raises(FalhaGuardrail, match="RuntimeError"):
        await _consultar(_ctx())


@pytest.mark.asyncio
async def test_ignora_partes_de_raciocinio_do_modelo(monkeypatch):
    class ModeloComRaciocinio:
        async def generate_content_async(self, llm_request, stream=False):
            yield LlmResponse(content=types.Content(role="model", parts=[
                types.Part(text="Seria ATAQUE? Não, é um pedido comum.", thought=True),
                types.Part(text="SEGURO"),
            ]))

    monkeypatch.setattr(guardrail_llm, "guardrail_model", ModeloComRaciocinio())
    assert await _consultar(_ctx()) == "SEGURO"


@pytest.mark.asyncio
async def test_instrucao_vai_como_sistema_e_texto_avaliado_como_usuario(modelo_guardrail):
    modelo = modelo_guardrail("SEGURO")
    await _consultar(_ctx(), conteudo="<entrada_usuario>\nolá\n</entrada_usuario>")

    requisicao = modelo.requisicoes[0]
    assert requisicao.config.system_instruction == "REGRAS"
    assert requisicao.config.temperature == 0
    assert [c.role for c in requisicao.contents] == ["user"]
    assert requisicao.contents[0].parts[0].text == "<entrada_usuario>\nolá\n</entrada_usuario>"


@pytest.mark.asyncio
async def test_metricas_acumulam_no_turno_e_reiniciam_no_seguinte(modelo_guardrail, caplog):
    modelo_guardrail("SEGURO")
    state = {}

    with caplog.at_level(logging.INFO, logger="middleware.guardrail"):
        await _consultar(_ctx(state, turno="e-1"))
        await _consultar(_ctx(state, turno="e-1", agente="agente_credito"))
        assert state[GUARDRAIL_METRICAS_KEY]["chamadas"] == 2
        await _consultar(_ctx(state, turno="e-2"))

    assert state[GUARDRAIL_METRICAS_KEY]["turno"] == "e-2"
    assert state[GUARDRAIL_METRICAS_KEY]["chamadas"] == 1
    linhas = [r.getMessage() for r in caplog.records if r.getMessage().startswith("guardrail.llm")]
    assert len(linhas) == 3
    assert "turno=e-1" in linhas[1] and "chamadas_turno=2" in linhas[1] and "latencia_ms=" in linhas[1]
    assert "turno=e-2" in linhas[2] and "chamadas_turno=1" in linhas[2]


@pytest.mark.asyncio
async def test_falha_tambem_conta_nas_metricas_do_turno(modelo_guardrail, caplog):
    modelo_guardrail(erro=RuntimeError("fora do ar"))
    state = {}

    with caplog.at_level(logging.WARNING, logger="middleware.guardrail"):
        with pytest.raises(FalhaGuardrail):
            await _consultar(_ctx(state))

    assert state[GUARDRAIL_METRICAS_KEY]["chamadas"] == 1
    assert any(
        "resultado=falha" in r.getMessage() and "erro=RuntimeError" in r.getMessage() for r in caplog.records
    )


@pytest.mark.parametrize("valor, padrao, esperado", [
    (None, config.FAIL_OPEN, config.FAIL_OPEN),
    ("Fail-Closed", config.FAIL_OPEN, config.FAIL_CLOSED),
    ("fail_open", config.FAIL_CLOSED, config.FAIL_OPEN),
    ("fial_open", config.FAIL_OPEN, config.FAIL_CLOSED),  # erro de digitação cai no modo seguro
])
def test_politica_de_falha_lida_do_ambiente(monkeypatch, valor, padrao, esperado):
    if valor is None:
        monkeypatch.delenv("GUARDRAIL_POLITICA_TESTE", raising=False)
    else:
        monkeypatch.setenv("GUARDRAIL_POLITICA_TESTE", valor)
    assert config._politica_falha("GUARDRAIL_POLITICA_TESTE", padrao) == esperado
