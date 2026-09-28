import asyncio
import json
from typing import Optional
from root_agent.utils import get_logger
from google.adk.agents.callback_context import CallbackContext
from root_agent.domain.ports.event_publisher import IEventPublisher
from root_agent.config import EVENTS_FLOW_ID
from root_agent.domain.conversation_state import resetar_autenticacao

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
            session = getattr(ctx, "session", None)
            if session:
                thread_id = getattr(session, "id", "unknown_thread") or "unknown_thread"
            _logger.info("Encerramento de atendimento solicitado | thread_id=%s", thread_id)

            # Só pela API pública do State: o reset vai no state_delta do evento da tool e é
            # persistido pelo SessionService (inclusive o CPF em cliente_autenticado).
            if getattr(ctx, "state", None) is not None:
                resetar_autenticacao(ctx.state)

            # Sem transfer_to_agent/end_of_agent: a tool só roda na triagem, e transferir para ela
            # mesma ou encerrar o agente cortava o turno antes de o modelo escrever a despedida
            # (os evals mostravam resposta vazia após o "tchau").

            _logger.info("Estado da sessão limpo com sucesso | thread_id=%s", thread_id)

        if publisher:
            asyncio.create_task(publisher.publish_flow_completed(
                thread_id=thread_id,
                flow_id=EVENTS_FLOW_ID
            ))

        # Só o texto a ser dito ao cliente: uma instrução no retorno ("informe ao cliente...")
        # acabava repetida na resposta, e os evals pegaram o vazamento.
        return json.dumps({
            "status": "atendimento_encerrado",
            "mensagem_cliente": "Seu atendimento foi encerrado. Se quiser um novo atendimento, é só enviar uma mensagem ou a palavra *Menu*.",
        }, ensure_ascii=False)

    return encerrar_atendimento

