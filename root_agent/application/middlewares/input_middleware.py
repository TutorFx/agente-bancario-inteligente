import re
import json
import asyncio

from root_agent.utils import get_logger

logger = get_logger("middleware.input")

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from root_agent.domain.conversation_state import (
    BankingConversationState,
    CONVERSATION_STATE_KEY,
    AUTH_TENTATIVAS_KEY,
    AUTH_CPF_TEMP_KEY,
    CLIENTE_KEY,
    ENTREVISTA_KEY,
    ENTREVISTA_REALIZADA_KEY
)
from root_agent.application.presenters.banking_presenter import BankingPresenter
from root_agent.domain.guardrails import (
    validar_formato_cpf,
    validar_formato_data,
    extrair_data,
    limpar_cpf,
    MAX_TENTATIVAS_AUTH
)

_REGEX_ATAQUE_INJECTION = re.compile(
    r"(?i)(ignore.*instru[çc][õo]es|system_override|ai_ping|identity_dump|bypass|jailbreak|esque[çc]a.*instru[çc][õo]es|override|system prompt|modelo.*vers[ãa]o|developer.*google|ignore.*regras|transferir.*sistema|pix.*override)"
)

_REGEX_APENAS_NUMERO = re.compile(r"^\s*(\d+)\s*$")

def _extrair_texto_usuario(llm_request: LlmRequest) -> str | None:
    try:
        contents = llm_request.contents
        if not contents:
            return None
        for content in reversed(contents):
            if content.role == "user" and content.parts:
                for part in reversed(content.parts):
                    if hasattr(part, "text") and part.text:
                        return part.text.strip()
    except (AttributeError, TypeError):
        pass
    return None

def _substituir_texto_usuario(llm_request: LlmRequest, novo_texto: str) -> None:
    try:
        contents = llm_request.contents
        if not contents:
            return
        for content in reversed(contents):
            if content.role == "user" and content.parts:
                for part in reversed(content.parts):
                    if hasattr(part, "text") and part.text:
                        part.text = novo_texto
                        return
    except (AttributeError, TypeError):
        pass

def _construir_resposta(texto: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=texto)],
        )
    )

def _obter_estado(callback_context: CallbackContext) -> BankingConversationState:
    estado_raw = callback_context.state.get(CONVERSATION_STATE_KEY)
    if estado_raw is None:
        return BankingConversationState.IDLE
    try:
        return BankingConversationState(estado_raw)
    except ValueError:
        return BankingConversationState.IDLE

def _limpar_estado(callback_context: CallbackContext) -> None:
    callback_context.state[CONVERSATION_STATE_KEY] = BankingConversationState.IDLE

def _disparar_encerramento(callback_context: CallbackContext) -> None:
    from root_agent.dependencies import encerrar_atendimento
    try:
        if hasattr(callback_context, "state") and callback_context.state is not None:
            callback_context.state[CLIENTE_KEY] = None
            callback_context.state["cliente_autenticado"] = None
            callback_context.state["is_authenticated"] = False
            callback_context.state[AUTH_CPF_TEMP_KEY] = None
            callback_context.state["auth_data_temp"] = None
            callback_context.state[AUTH_TENTATIVAS_KEY] = 0
            callback_context.state[CONVERSATION_STATE_KEY] = BankingConversationState.IDLE.value
            callback_context.state[ENTREVISTA_KEY] = None
            callback_context.state[ENTREVISTA_REALIZADA_KEY] = False
            callback_context.state['session_active'] = False
            callback_context.state['cpf'] = None
            callback_context.state['nome'] = None
            callback_context.state['tentativas_login'] = 0
        if hasattr(callback_context, "actions") and callback_context.actions:
            callback_context.actions.transfer_to_agent = "agente_triagem"
            callback_context.actions.end_of_agent = True
        coro = encerrar_atendimento(callback_context=callback_context)
        if asyncio.iscoroutine(coro):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
    except Exception:
        logger.exception("Erro ao disparar encerramento de sessão")


def _tratar_aguardando_cpf(ctx: CallbackContext, texto: str, llm_request: LlmRequest) -> LlmResponse | None:
    # Se a mensagem do usuário não contém NENHUM número (ex: "olá", "quero ajuda"),
    # deixamos passar para o LLM, que foi instruído a responder cordialmente.
    if not any(char.isdigit() for char in texto):
        return None

    # Se contém números, validamos como uma tentativa de CPF.
    if not validar_formato_cpf(texto):
        return _construir_resposta(BankingPresenter.cpf_invalido())
    
    ctx.state[AUTH_CPF_TEMP_KEY] = limpar_cpf(texto)
    ctx.state[CONVERSATION_STATE_KEY] = BankingConversationState.AGUARDANDO_DATA_NASCIMENTO
    return _construir_resposta(BankingPresenter.solicitar_data_nascimento())

def _tratar_aguardando_data_nascimento(ctx: CallbackContext, texto: str, llm_request: LlmRequest) -> LlmResponse | None:
    data_extraida = extrair_data(texto)
    if not data_extraida:
        return _construir_resposta(BankingPresenter.data_invalida())

    ctx.state["auth_data_temp"] = data_extraida
    _limpar_estado(ctx)
    _substituir_texto_usuario(
        llm_request,
        f"Cliente quer se autenticar. CPF: {ctx.state[AUTH_CPF_TEMP_KEY]}, "
        f"Data: {ctx.state['auth_data_temp']}. "
        "Chame IMEDIATAMENTE autenticar_cliente com esses dados."
    )
    return None

def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    if ENTREVISTA_REALIZADA_KEY not in callback_context.state:
        callback_context.state[ENTREVISTA_REALIZADA_KEY] = False

    # Intercepta o resultado da ferramenta de autenticação para um controle determinístico
    if llm_request.contents:
        last_content = llm_request.contents[-1]
        if last_content.parts:
            for part in last_content.parts:
                if hasattr(part, "function_response") and part.function_response:
                    if part.function_response.name == "autenticar_cliente":
                        tool_output_text = str(part.function_response.response)
                        if "credenciais_invalidas" in tool_output_text:
                            # LÓGICA DE FALHA
                            tentativas = callback_context.state.get(AUTH_TENTATIVAS_KEY, 0) + 1
                            callback_context.state[AUTH_TENTATIVAS_KEY] = tentativas

                            if tentativas >= MAX_TENTATIVAS_AUTH:
                                # LÓGICA DE BLOQUEIO
                                callback_context.state[CONVERSATION_STATE_KEY] = BankingConversationState.IDLE
                                _disparar_encerramento(callback_context)
                                return _construir_resposta(BankingPresenter.autenticacao_bloqueada())
                            else:
                                # LÓGICA DE NOVA TENTATIVA
                                tentativas_restantes = MAX_TENTATIVAS_AUTH - tentativas
                                callback_context.state[CONVERSATION_STATE_KEY] = BankingConversationState.AGUARDANDO_CPF
                                return _construir_resposta(BankingPresenter.autenticacao_falha(tentativas_restantes))
                        else:
                            # LÓGICA DE SUCESSO
                            callback_context.state[AUTH_TENTATIVAS_KEY] = 0
                            callback_context.state["is_authenticated"] = True
                            callback_context.state[CLIENTE_KEY] = tool_output_text
                            return None

    texto_usuario = _extrair_texto_usuario(llm_request)
    if not texto_usuario:
        return None

    if _REGEX_ATAQUE_INJECTION.search(texto_usuario):
        logger.warning("Tentativa de prompt injection detectada | texto=%s", texto_usuario[:80])
        _limpar_estado(callback_context)
        _disparar_encerramento(callback_context)
        return _construir_resposta("⚠️ Atividade suspeita detectada. Por motivos de segurança, este atendimento será encerrado.")

    estado = _obter_estado(callback_context)

    # Transição automática de IDLE para AGUARDANDO_DATA_NASCIMENTO se o usuário mandar o CPF de cara
    if estado == BankingConversationState.IDLE and validar_formato_cpf(texto_usuario):
        callback_context.state[AUTH_CPF_TEMP_KEY] = limpar_cpf(texto_usuario)
        callback_context.state[CONVERSATION_STATE_KEY] = BankingConversationState.AGUARDANDO_DATA_NASCIMENTO
        return _construir_resposta(BankingPresenter.solicitar_data_nascimento())

    if estado == BankingConversationState.AGUARDANDO_CPF:
        return _tratar_aguardando_cpf(callback_context, texto_usuario, llm_request)

    if estado == BankingConversationState.AGUARDANDO_DATA_NASCIMENTO:
        return _tratar_aguardando_data_nascimento(callback_context, texto_usuario, llm_request)

    return None
