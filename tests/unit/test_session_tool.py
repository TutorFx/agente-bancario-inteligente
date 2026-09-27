import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from google.adk.agents.callback_context import CallbackContext
from root_agent.application.tools.session_tool import get_encerrar_atendimento_tool
from root_agent.domain.ports.event_publisher import IEventPublisher
from root_agent.config import EVENTS_FLOW_ID

@pytest.mark.asyncio
async def test_encerrar_atendimento_calls_event_publisher_and_returns_success_message():
    # Arrange
    mock_publisher = MagicMock(spec=IEventPublisher)
    mock_publisher.publish_flow_completed = AsyncMock()
    
    mock_session = MagicMock()
    mock_session.id = "thread_123"
    
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.session = mock_session
    
    encerrar_atendimento = get_encerrar_atendimento_tool(mock_publisher)
    
    # Act
    res = await encerrar_atendimento(callback_context=mock_context)
    
    # Assert
    assert "Ação de encerramento acionada" in res
    assert "Atendimento com a SEMAD encerrado" not in res # A resposta é a instrução interna, não a externa
    assert "palavra *Menu*" in res
    
    # Como a chamada ao publisher é feita via asyncio.create_task, precisamos ceder o loop para que ela execute
    await asyncio.sleep(0.01)
    
    mock_publisher.publish_flow_completed.assert_called_once_with(
        thread_id="thread_123",
        flow_id=EVENTS_FLOW_ID
    )

@pytest.mark.asyncio
async def test_encerrar_atendimento_without_context_uses_unknown_thread():
    # Arrange
    mock_publisher = MagicMock(spec=IEventPublisher)
    mock_publisher.publish_flow_completed = AsyncMock()
    
    encerrar_atendimento = get_encerrar_atendimento_tool(mock_publisher)
    
    # Act
    res = await encerrar_atendimento()
    
    # Assert
    await asyncio.sleep(0.01)
    mock_publisher.publish_flow_completed.assert_called_once_with(
        thread_id="unknown_thread",
        flow_id=EVENTS_FLOW_ID
    )

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
    assert "Ação de encerramento acionada" in res
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

    # Session dict cleanup
    assert "cliente_autenticado" not in mock_session.state
    assert "cpf" not in mock_session.state
    assert "nome" not in mock_session.state
    assert mock_session.state["is_authenticated"] is False
    assert mock_session.state["conv_state"] == "idle"

    # Redirection to agente_triagem
    assert mock_actions.transfer_to_agent == "agente_triagem"
    assert mock_actions.end_of_agent is True

