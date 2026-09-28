import json
from typing import Any, Mapping, Optional

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from root_agent.domain.conversation_state import CLIENTE_KEY
from root_agent.utils import get_logger

logger = get_logger("middleware.auth_guard")

IS_AUTHENTICATED_KEY = "is_authenticated"

# Tools que podem rodar sem cliente autenticado (a autenticação é feita pelo input_middleware)
TOOLS_PUBLICAS = frozenset({"encerrar_atendimento", "transfer_to_agent"})

ERRO_NAO_AUTENTICADO = {
    "erro": "nao_autenticado",
    "mensagem": "Cliente não autenticado. Solicite o CPF para iniciar a autenticação.",
}


def _cliente_da_sessao(state: Mapping[str, Any]) -> Optional[dict]:
    cliente = state.get(CLIENTE_KEY)
    if isinstance(cliente, str):
        try:
            cliente = json.loads(cliente)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(cliente, dict) and isinstance(cliente.get("cliente"), dict):
        cliente = cliente["cliente"]
    return cliente if isinstance(cliente, dict) else None


def cpf_do_cliente_autenticado(tool_context: Optional[ToolContext]) -> Optional[str]:
    """
    Única fonte de verdade para o CPF usado pelas tools: o estado da sessão
    gravado pelo backend após autenticação bem-sucedida. Argumentos vindos da
    LLM nunca são aceitos como identidade do cliente (evita IDOR).
    """
    if tool_context is None or getattr(tool_context, "state", None) is None:
        return None
    state = tool_context.state
    if state.get(IS_AUTHENTICATED_KEY) is not True:
        return None
    cliente = _cliente_da_sessao(state)
    cpf = str(cliente.get("cpf", "")).strip() if cliente else ""
    return cpf or None


def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> Optional[dict]:
    """Bloqueia deterministicamente tools de negócio enquanto o cliente não estiver autenticado."""
    if tool.name in TOOLS_PUBLICAS:
        return None
    if cpf_do_cliente_autenticado(tool_context) is None:
        logger.warning("Tool bloqueada por falta de autenticação | tool=%s", tool.name)
        return dict(ERRO_NAO_AUTENTICADO)
    return None
