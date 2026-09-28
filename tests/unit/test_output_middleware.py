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
async def test_after_model_callback_sem_texto():
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.state = {}

    mock_resp = MagicMock(content=None)
    result = await after_model_callback(mock_context, mock_resp)

    assert result is None
    assert mock_context.state == {}

