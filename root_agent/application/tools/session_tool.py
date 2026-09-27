import asyncio
from typing import Optional
from root_agent.utils import get_logger
from google.adk.agents.callback_context import CallbackContext
from root_agent.domain.ports.event_publisher import IEventPublisher
from root_agent.config import EVENTS_FLOW_ID
from root_agent.domain.conversation_state import (
    BankingConversationState,
    CONVERSATION_STATE_KEY,
    AUTH_TENTATIVAS_KEY,
    AUTH_CPF_TEMP_KEY,
    CLIENTE_KEY,
    ENTREVISTA_KEY,
    ENTREVISTA_REALIZADA_KEY,
)

def get_encerrar_atendimento_tool(publisher: Optional[IEventPublisher] = None):
    async def encerrar_atendimento(
        callback_context: Optional[CallbackContext] = None,
    ) -> str:
        """
        Encerra o atendimento com o cliente e limpa todo o estado da sessão.
        """
        _logger = get_logger("tools.session")
        ctx = callback_context
        thread_id = "unknown_thread"

        if ctx:
            if hasattr(ctx, "session") and ctx.session:
                thread_id = getattr(ctx.session, "id", "unknown_thread") or "unknown_thread"
                _logger.info("Encerramento de atendimento solicitado | thread_id=%s", thread_id)
                if hasattr(ctx.session, "state") and isinstance(ctx.session.state, dict):
                    for k in [
                        CLIENTE_KEY,
                        "cliente_autenticado",
                        AUTH_CPF_TEMP_KEY,
                        "auth_data_temp",
                        ENTREVISTA_KEY,
                        "cpf",
                        "nome",
                        "tentativas_login",
                    ]:
                        ctx.session.state.pop(k, None)
                    ctx.session.state[CONVERSATION_STATE_KEY] = BankingConversationState.IDLE.value
                    ctx.session.state[AUTH_TENTATIVAS_KEY] = 0
                    ctx.session.state["is_authenticated"] = False
                    ctx.session.state[ENTREVISTA_REALIZADA_KEY] = False
                    ctx.session.state["session_active"] = False

            if hasattr(ctx, "state") and ctx.state is not None:
                # Reset em ctx.state (delta-aware State dict)
                ctx.state[CLIENTE_KEY] = None
                ctx.state["cliente_autenticado"] = None
                ctx.state["is_authenticated"] = False
                ctx.state[AUTH_CPF_TEMP_KEY] = None
                ctx.state["auth_data_temp"] = None
                ctx.state[AUTH_TENTATIVAS_KEY] = 0
                ctx.state[CONVERSATION_STATE_KEY] = BankingConversationState.IDLE.value
                ctx.state[ENTREVISTA_KEY] = None
                ctx.state[ENTREVISTA_REALIZADA_KEY] = False
                ctx.state["session_active"] = False
                ctx.state["cpf"] = None
                ctx.state["nome"] = None
                ctx.state["tentativas_login"] = 0

                # Remove do dict interno de State se disponível
                if hasattr(ctx.state, "_value") and isinstance(ctx.state._value, dict):
                    for k in [CLIENTE_KEY, "cliente_autenticado", "cpf", "nome", AUTH_CPF_TEMP_KEY, "auth_data_temp", ENTREVISTA_KEY]:
                        ctx.state._value.pop(k, None)
                if hasattr(ctx.state, "_delta") and isinstance(ctx.state._delta, dict):
                    for k in [CLIENTE_KEY, "cliente_autenticado", "cpf", "nome", AUTH_CPF_TEMP_KEY, "auth_data_temp", ENTREVISTA_KEY]:
                        ctx.state._delta.pop(k, None)

            if hasattr(ctx, "actions") and ctx.actions:
                ctx.actions.transfer_to_agent = "agente_triagem"
                ctx.actions.end_of_agent = True

            _logger.info("Estado da sessão limpo com sucesso | thread_id=%s", thread_id)

        if publisher:
            asyncio.create_task(publisher.publish_flow_completed(
                thread_id=thread_id,
                flow_id=EVENTS_FLOW_ID
            ))

        return "Ação de encerramento acionada. Informe ao cliente que o atendimento foi encerrado e que caso queira um novo atendimento pode enviar uma mensagem ou a palavra *Menu*."

    return encerrar_atendimento

