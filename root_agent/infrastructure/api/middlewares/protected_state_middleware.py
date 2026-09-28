import json
from typing import Any, Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from root_agent.domain.conversation_state import (
    AUTH_CPF_TEMP_KEY,
    AUTH_TENTATIVAS_KEY,
    CLIENTE_KEY,
    CONVERSATION_STATE_KEY,
    ENTREVISTA_KEY,
    ENTREVISTA_REALIZADA_KEY,
    GUARDRAIL_ENTRADA_KEY,
    GUARDRAIL_METRICAS_KEY,
)
from root_agent.utils import get_logger

logger = get_logger("middleware.protected_state")

# Chaves que só o backend (callbacks/tools) pode escrever. Se o cliente HTTP pudesse
# enviá-las, bastaria criar uma sessão com {"is_authenticated": true} para pular a triagem.
CHAVES_PROTEGIDAS = frozenset({
    "is_authenticated",
    CLIENTE_KEY,
    AUTH_TENTATIVAS_KEY,
    AUTH_CPF_TEMP_KEY,
    "auth_data_temp",
    CONVERSATION_STATE_KEY,
    ENTREVISTA_KEY,
    ENTREVISTA_REALIZADA_KEY,
    "session_active",
    "cpf",
    "nome",
    "tentativas_login",
    # Um veredito forjado via stateDelta faria o turno pular o classificador de entrada
    GUARDRAIL_ENTRADA_KEY,
    GUARDRAIL_METRICAS_KEY,
})

_CAMPOS_DE_ESTADO = ("state", "stateDelta", "state_delta")


def _dicts_de_estado(body: dict[str, Any]) -> Iterable[dict]:
    # POST /apps/{app}/users/{user}/sessions/{id} (legado) recebe o próprio estado como body
    yield body
    for campo in _CAMPOS_DE_ESTADO:
        valor = body.get(campo)
        if isinstance(valor, dict):
            yield valor


def chaves_protegidas_no_body(body_bytes: bytes) -> set[str]:
    if not body_bytes:
        return set()
    try:
        body = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return set()
    if not isinstance(body, dict):
        return set()
    encontradas: set[str] = set()
    for estado in _dicts_de_estado(body):
        encontradas |= CHAVES_PROTEGIDAS.intersection(estado.keys())
    return encontradas


class ProtectedStateMiddleware:
    """Rejeita (403) requisições que tentem escrever chaves de autenticação no estado da sessão."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PATCH", "PUT"):
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        body_bytes = b"".join(chunks)

        proibidas = chaves_protegidas_no_body(body_bytes)
        if proibidas:
            logger.warning(
                "Escrita de estado protegido bloqueada | path=%s | chaves=%s",
                scope.get("path"), sorted(proibidas),
            )
            response = JSONResponse(
                {"detail": "Chaves de estado protegidas não podem ser definidas pelo cliente."},
                status_code=403,
            )
            await response(scope, receive, send)
            return

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)
