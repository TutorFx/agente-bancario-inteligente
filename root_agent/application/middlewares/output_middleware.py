from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types

from root_agent.domain.conversation_state import (
    BankingConversationState,
    CONVERSATION_STATE_KEY,
)


def _extrair_texto_resposta(llm_response: LlmResponse) -> Optional[str]:
    try:
        content = llm_response.content
        if not content or not content.parts:
            return None
        texto = "".join(
            part.text
            for part in content.parts
            if hasattr(part, "text") and part.text
        )
        return texto if texto else None
    except (AttributeError, TypeError):
        return None


def _aguardando_cpf(texto: str) -> bool:
    texto_lower = texto.lower()
    return "cpf" in texto_lower


def _aguardando_data_nascimento(texto: str) -> bool:
    texto_lower = texto.lower()
    return "data de nascimento" in texto_lower or "nascimento" in texto_lower


def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """
    Callback pós-modelo: detecta transições de estado baseadas no texto
    gerado pela LLM (quando o agente pede CPF ou data de nascimento).

    NOTA: O controle de tentativas de autenticação é gerenciado
    EXCLUSIVAMENTE pelo input_middleware (interceptando o function_response
    de autenticar_cliente). Não duplicar essa lógica aqui.
    """
    texto = _extrair_texto_resposta(llm_response)
    if not texto:
        return None

    if _aguardando_data_nascimento(texto):
        callback_context.state[CONVERSATION_STATE_KEY] = BankingConversationState.AGUARDANDO_DATA_NASCIMENTO
    elif _aguardando_cpf(texto):
        callback_context.state[CONVERSATION_STATE_KEY] = BankingConversationState.AGUARDANDO_CPF

    return None
