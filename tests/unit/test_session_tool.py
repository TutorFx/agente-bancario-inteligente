import json
import pytest
from unittest.mock import MagicMock
from google.adk.agents.callback_context import CallbackContext
from root_agent.application.tools.session_tool import get_encerrar_atendimento_tool

@pytest.mark.asyncio
async def test_encerrar_atendimento_returns_success_message():
    mock_session = MagicMock()
    mock_session.id = "thread_123"

    mock_context = MagicMock(spec=CallbackContext)
    mock_context.session = mock_session

    encerrar_atendimento = get_encerrar_atendimento_tool()

    res = await encerrar_atendimento(callback_context=mock_context)

    dados = json.loads(res)
    assert dados["status"] == "atendimento_encerrado"
    assert "palavra *Menu*" in dados["mensagem_cliente"]
    assert "Informe ao cliente" not in res

@pytest.mark.asyncio
async def test_encerrar_atendimento_without_context_returns_success_message():
    encerrar_atendimento = get_encerrar_atendimento_tool()

    res = await encerrar_atendimento()

    assert json.loads(res)["status"] == "atendimento_encerrado"

@pytest.mark.asyncio
async def test_encerrar_atendimento_clears_session_state_and_resets_agent():
    # Arrange
    mock_session = MagicMock()
    mock_session.id = "thread_xyz"
    mock_session.state = {
        "cliente_autenticado": '{"cpf": "12345678900", "nome": "Teste"}',
        "is_authenticated": True,
        "auth_cpf_temp": "12345678900",
        "auth_data_temp": "15/03/1985",
        "auth_tentativas": 1,
        "conv_state": "autenticado",
        "cpf": "12345678900",
        "nome": "Teste",
        "entrevista_dados": {"renda": 5000},
        "entrevista_realizada_na_sessao": True,
    }

    mock_actions = MagicMock()
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.session = mock_session
    mock_context.actions = mock_actions
    mock_context.state = dict(mock_session.state)

    encerrar_atendimento = get_encerrar_atendimento_tool()

    # Act
    res = await encerrar_atendimento(callback_context=mock_context)

    # Assert
    assert json.loads(res)["status"] == "atendimento_encerrado"
    # State reset
    assert mock_context.state["cliente_autenticado"] is None
    assert mock_context.state["is_authenticated"] is False
    assert mock_context.state["auth_cpf_temp"] is None
    assert mock_context.state["auth_data_temp"] is None
    assert mock_context.state["auth_tentativas"] == 0
    assert mock_context.state["conv_state"] == "idle"
    assert mock_context.state["cpf"] is None
    assert mock_context.state["nome"] is None
    assert mock_context.state["entrevista_dados"] is None
    assert mock_context.state["entrevista_realizada_na_sessao"] is False

    assert mock_context.state["session_active"] is False

    # O modelo ainda precisa escrever a despedida neste turno: nada de transferir ou encerrar o agente
    assert mock_actions.transfer_to_agent != "agente_triagem"
    assert mock_actions.end_of_agent is not True

