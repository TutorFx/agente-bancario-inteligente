"""Testes unitários para o output_middleware (transição de estados e ausência de contagem de auth)."""

from unittest.mock import MagicMock
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types

from root_agent.application.middlewares.output_middleware import (
    after_model_callback,
    _extrair_texto_resposta,
    _aguardando_cpf,
    _aguardando_data_nascimento,
)
from root_agent.domain.conversation_state import (
    BankingConversationState,
    CONVERSATION_STATE_KEY,
)


def _criar_llm_response(texto: str) -> LlmResponse:
    part = types.Part.from_text(text=texto)
    content = types.Content(parts=[part], role="model")
    return LlmResponse(content=content)


def test_extrair_texto_resposta_valido():
    response = _criar_llm_response("Por favor, digite seu CPF.")
    assert _extrair_texto_resposta(response) == "Por favor, digite seu CPF."


def test_extrair_texto_resposta_invalido():
    assert _extrair_texto_resposta(None) is None
    mock_resp = MagicMock(content=None)
    assert _extrair_texto_resposta(mock_resp) is None


import pytest

@pytest.mark.asyncio
async def test_after_model_callback_aguardando_cpf():
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.state = {}

    response = _criar_llm_response("Por favor, informe o seu CPF para prosseguir.")
    result = await after_model_callback(mock_context, response)

    assert result is None
    assert mock_context.state.get(CONVERSATION_STATE_KEY) == BankingConversationState.AGUARDANDO_CPF
    # Garante que tentativas de auth não são tocadas pelo output_middleware
    assert "auth_tentativas" not in mock_context.state


@pytest.mark.asyncio
async def test_after_model_callback_aguardando_data_nascimento():
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.state = {}

    response = _criar_llm_response("Agora informe sua data de nascimento (DD/MM/AAAA).")
    result = await after_model_callback(mock_context, response)

    assert result is None
    assert mock_context.state.get(CONVERSATION_STATE_KEY) == BankingConversationState.AGUARDANDO_DATA_NASCIMENTO
    assert "auth_tentativas" not in mock_context.state


@pytest.mark.asyncio
async def test_after_model_callback_nao_reabre_login_quando_autenticado():
    from unittest.mock import AsyncMock, patch

    mock_context = MagicMock(spec=CallbackContext)
    mock_context.state = {"is_authenticated": True, CONVERSATION_STATE_KEY: "autenticado"}

    response = _criar_llm_response("Consultei o limite vinculado ao seu CPF: R$ 5.000,00.")
    with patch(
        "root_agent.application.middlewares.output_middleware._validar_output_semantico",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await after_model_callback(mock_context, response)

    assert result is None
    assert mock_context.state[CONVERSATION_STATE_KEY] == "autenticado"


@pytest.mark.asyncio
async def test_after_model_callback_sem_texto():
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.state = {}

    mock_resp = MagicMock(content=None)
    result = await after_model_callback(mock_context, mock_resp)

    assert result is None
    assert mock_context.state == {}



# --- Persona unificada: filtro de anúncios de transferência ---

from root_agent.application.middlewares.output_middleware import _remover_anuncio_transferencia


@pytest.mark.parametrize(
    "texto, esperado",
    [
        (
            "Vou transferir você para o especialista de crédito. Seu limite atual é R$ 5.000,00.",
            "Seu limite atual é R$ 5.000,00.",
        ),
        (
            "Estou encaminhando seu atendimento para o agente de câmbio.\nA cotação do dólar é R$ 5,10.",
            "A cotação do dólar é R$ 5,10.",
        ),
        (
            "Aguarde um momento enquanto transfiro você. Vamos começar a entrevista!",
            "Vamos começar a entrevista!",
        ),
        (
            "Certo! transfer_to_agent(agent_name='agente_credito') Qual valor você deseja?",
            "Certo! Qual valor você deseja?",
        ),
        (
            "Redirecionando para a equipe responsável... Qual moeda deseja consultar?",
            "Qual moeda deseja consultar?",
        ),
    ],
)
def test_remover_anuncio_transferencia_corta_anuncios(texto, esperado):
    assert _remover_anuncio_transferencia(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Já encaminhamos seu comprovante para o seu e-mail cadastrado.",
        "Estou encaminhando o comprovante da solicitação para o seu e-mail.",
        "Vou transferir o valor para a sua conta assim que aprovado.",
        "Aguarde um momento enquanto consulto seu limite.",
        "Você pode encaminhar dúvidas pelo nosso 0800 123 4567.",
    ],
)
def test_remover_anuncio_transferencia_preserva_conteudo_legitimo(texto):
    assert _remover_anuncio_transferencia(texto) == texto


def test_remover_anuncio_transferencia_nao_esvazia_resposta():
    texto = "Vou transferir você para o especialista."
    assert _remover_anuncio_transferencia(texto) == texto


@pytest.mark.asyncio
async def test_after_model_callback_remove_anuncio_e_preserva_function_call():
    from unittest.mock import AsyncMock, patch

    mock_context = MagicMock(spec=CallbackContext)
    mock_context.state = {"is_authenticated": True}

    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(text="Vou te transferir para o agente de crédito. Um instante!"),
                types.Part.from_function_call(name="transfer_to_agent", args={"agent_name": "agente_credito"}),
            ],
        )
    )
    with patch(
        "root_agent.application.middlewares.output_middleware._validar_output_semantico",
        new_callable=AsyncMock,
        return_value=True,
    ) as validador:
        result = await after_model_callback(mock_context, response)

    assert result is None
    assert response.content.parts[0].text == "Um instante!"
    assert response.content.parts[1].function_call.name == "transfer_to_agent"
    validador.assert_awaited_once_with(mock_context, "Um instante!", parcial=False)
