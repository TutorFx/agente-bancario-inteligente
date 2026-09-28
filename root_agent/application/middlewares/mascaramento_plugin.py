from typing import Optional

from google.adk.agents.invocation_context import InvocationContext
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

from root_agent.domain.conversation_state import TEXTO_ORIGINAL_USUARIO_KEY
from root_agent.domain.pii import mascarar_pii
from root_agent.utils import get_logger

logger = get_logger("middleware.mascaramento")


def _texto(content: types.Content) -> str:
    return "".join(p.text for p in content.parts or [] if p.text and not p.thought).strip()


class MascaramentoCredenciaisPlugin(BasePlugin):
    """
    Impede que CPF e data de nascimento digitados no chat sejam persistidos: o Runner grava
    no histórico da sessão (session.db, API REST) a mensagem que este callback devolver.

    O texto original vai para a sessão em memória sob uma chave temp:, sem state_delta, então
    não é persistido nem sobrevive ao turno; o input_middleware o recupera para autenticar.
    """

    def __init__(self, name: str = "mascaramento_credenciais"):
        super().__init__(name=name)

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> Optional[types.Content]:
        # Limpa o registro de um turno anterior na mesma sessão em memória (ex: InMemoryRunner)
        invocation_context.session.state.pop(TEXTO_ORIGINAL_USUARIO_KEY, None)
        if not user_message or not user_message.parts:
            return None

        original = _texto(user_message)
        mascarado = mascarar_pii(original)
        if mascarado == original:
            return None

        invocation_context.session.state[TEXTO_ORIGINAL_USUARIO_KEY] = {
            "original": original,
            "mascarado": mascarado,
        }
        partes = [
            p.model_copy(update={"text": mascarar_pii(p.text)}) if p.text else p
            for p in user_message.parts
        ]
        logger.info("Credenciais mascaradas antes de persistir a mensagem do usuário")
        return types.Content(role=user_message.role, parts=partes)
