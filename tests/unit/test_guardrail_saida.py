"""
Guardrail de saída: regex determinística sempre ativa e LLM só diante de sinal suspeito
(bloco de código ou texto longo fora do domínio). A LLM é o dublê `modelo_guardrail`.
"""

import logging
from unittest.mock import MagicMock

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types

from root_agent import config
from root_agent.application.middlewares.output_middleware import (
    MENSAGEM_RESPOSTA_BLOQUEADA,
    after_model_callback,
)


def _ctx():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {"is_authenticated": True}
    ctx.invocation_id = "e-turno-1"
    ctx.agent_name = "agente_credito"
    return ctx


def _resposta(texto, parcial=None):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=texto)]), partial=parcial)


def _texto(resposta):
    return "".join(p.text for p in resposta.content.parts if p.text)


RESPOSTAS_COMUNS = [
    "Seu limite atual é de R$ 5.000,00 e seu score é 750. O que mais posso fazer por você hoje?",
    "✅ Anotado: Renda mensal de R$ 8000. Qual é a sua situação de emprego atual?",
    "A cotação atual do USD em relação ao Real é: 1 USD ≈ R$ 5,4321.",
    "Poxa, receitas não são a minha especialidade! 😊 Posso ajudar com limite de crédito, score ou câmbio?",
]

RESULTADO_ENTREVISTA = """✅ Entrevista concluída! Seu novo score de crédito foi calculado:

📊 **Novo Score: 780 / 1000**

Detalhamento:
• Parcela renda: +230 pts
• Parcela emprego: +200 pts
• Parcela comprometimento de renda: +130 pts
• Parcela dependentes: +120 pts
• Parcela dívidas: +100 pts

Seu cadastro foi atualizado com sucesso! 🎉"""

CODIGO = "Claro! Segue o script:\n```python\nprint(1000 * 1.02 ** 12)\n```"
RECEITA = "Bolo de cenoura: bata três cenouras, três ovos e meia xícara de óleo no liquidificador. " * 8


@pytest.mark.asyncio
@pytest.mark.parametrize("texto", RESPOSTAS_COMUNS)
async def test_resposta_comum_nao_chama_a_llm(modelo_guardrail, texto):
    modelo = modelo_guardrail("REJEITADA")
    resposta = _resposta(texto)

    assert await after_model_callback(_ctx(), resposta) is None

    assert _texto(resposta) == texto
    assert modelo.chamadas == 0


@pytest.mark.asyncio
async def test_texto_longo_do_dominio_nao_chama_a_llm(modelo_guardrail, monkeypatch):
    monkeypatch.setattr(config, "GUARDRAIL_SAIDA_TEXTO_LONGO", 100)
    modelo = modelo_guardrail("REJEITADA")
    resposta = _resposta(RESULTADO_ENTREVISTA)

    await after_model_callback(_ctx(), resposta)

    assert _texto(resposta) == RESULTADO_ENTREVISTA
    assert modelo.chamadas == 0


@pytest.mark.asyncio
async def test_termo_interno_e_barrado_pela_regex_sem_llm(modelo_guardrail):
    modelo = modelo_guardrail("APROVADA")
    resposta = _resposta("Vou acionar a ferramenta consultar_limite_credito para você.")

    await after_model_callback(_ctx(), resposta)

    assert _texto(resposta) == MENSAGEM_RESPOSTA_BLOQUEADA
    assert modelo.chamadas == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("texto", [CODIGO, RECEITA], ids=["bloco_de_codigo", "texto_longo_fora_do_dominio"])
async def test_sinal_suspeito_consulta_a_llm_e_a_rejeicao_substitui_a_resposta(modelo_guardrail, texto):
    modelo = modelo_guardrail("REJEITADA")
    resposta = _resposta(texto)

    await after_model_callback(_ctx(), resposta)

    assert modelo.chamadas == 1
    assert _texto(resposta) == MENSAGEM_RESPOSTA_BLOQUEADA


@pytest.mark.asyncio
async def test_bloco_de_formatacao_aprovado_pela_llm_segue_intacto(modelo_guardrail):
    texto = "Confira seus dados:\n```\nRenda: R$ 8.000,00\nDependentes: 1\n```\nEstá correto?"
    modelo = modelo_guardrail("APROVADA")
    resposta = _resposta(texto)

    await after_model_callback(_ctx(), resposta)

    assert modelo.chamadas == 1
    assert _texto(resposta) == texto


@pytest.mark.asyncio
async def test_falha_do_validador_diante_de_sinal_suspeito_bloqueia_por_padrao(modelo_guardrail, monkeypatch):
    monkeypatch.setattr(config, "GUARDRAIL_TIMEOUT_SEGUNDOS", 0.05)
    modelo_guardrail("APROVADA", atraso=5)
    resposta = _resposta(CODIGO)

    await after_model_callback(_ctx(), resposta)

    assert _texto(resposta) == MENSAGEM_RESPOSTA_BLOQUEADA


@pytest.mark.asyncio
async def test_falha_do_validador_em_fail_open_libera_com_log(modelo_guardrail, monkeypatch, caplog):
    monkeypatch.setattr(config, "GUARDRAIL_FALHA_SAIDA", config.FAIL_OPEN)
    modelo_guardrail(erro=ConnectionError("provedor fora do ar"))
    resposta = _resposta(CODIGO)

    with caplog.at_level(logging.WARNING):
        await after_model_callback(_ctx(), resposta)

    assert _texto(resposta) == CODIGO
    assert any("política fail_open" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_fragmento_de_streaming_nao_chama_a_llm(modelo_guardrail):
    modelo = modelo_guardrail("REJEITADA")
    resposta = _resposta(CODIGO, parcial=True)

    await after_model_callback(_ctx(), resposta)

    # A resposta final agregada (partial=False) é que passa pelo validador
    assert modelo.chamadas == 0
    assert _texto(resposta) == CODIGO
