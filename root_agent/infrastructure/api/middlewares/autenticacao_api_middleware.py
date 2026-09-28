import hmac
import ipaddress
from typing import Callable, Optional

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from root_agent import config
from root_agent.utils import get_logger

logger = get_logger("middleware.autenticacao_api")

# Sonda de liveness: não expõe dados
ROTAS_PUBLICAS = frozenset({"/health"})

MENSAGEM_TOKEN_INVALIDO = "Token da API ausente ou inválido."
MENSAGEM_SOMENTE_LOCAL = (
    "Sem BANCO_AGIL_API_TOKEN configurado, a API só aceita conexões locais. "
    "Defina o token para acesso remoto."
)


def _token_configurado() -> Optional[str]:
    return config.API_TOKEN


def token_da_requisicao(headers: Headers) -> Optional[str]:
    autorizacao = headers.get("authorization", "")
    esquema, _, credencial = autorizacao.partition(" ")
    if esquema.lower() == "bearer" and credencial.strip():
        return credencial.strip()
    return headers.get("x-api-key") or None


def eh_cliente_local(scope: Scope) -> bool:
    cliente = scope.get("client")
    if not cliente:
        return False
    host = cliente[0]
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


class AutenticacaoApiMiddleware:
    """
    Controle de acesso da API REST/WebSocket do ADK, que não tem autenticação própria.

    - Com BANCO_AGIL_API_TOKEN: exige o token em toda rota, exceto /health (401 sem ele).
    - Sem token: aceita só conexões de loopback (403 para as demais), o suficiente para a
      demo local (Streamlit e testes na mesma máquina) sem abrir as sessões para a rede.
    """

    def __init__(self, app: ASGIApp, obter_token: Callable[[], Optional[str]] = _token_configurado):
        self.app = app
        self.obter_token = obter_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or scope.get("path") in ROTAS_PUBLICAS:
            await self.app(scope, receive, send)
            return

        token = self.obter_token()
        if token:
            recebido = token_da_requisicao(Headers(scope=scope))
            if recebido and hmac.compare_digest(recebido.encode(), token.encode()):
                await self.app(scope, receive, send)
                return
            await self._recusar(scope, receive, send, 401, MENSAGEM_TOKEN_INVALIDO)
            return

        if eh_cliente_local(scope):
            await self.app(scope, receive, send)
            return
        await self._recusar(scope, receive, send, 403, MENSAGEM_SOMENTE_LOCAL)

    @staticmethod
    async def _recusar(scope: Scope, receive: Receive, send: Send, status: int, mensagem: str) -> None:
        logger.warning(
            "Requisição à API recusada | status=%s | path=%s | cliente=%s",
            status, scope.get("path"), (scope.get("client") or ("?",))[0],
        )
        if scope["type"] == "websocket":
            # Fechar antes do accept faz o servidor responder 403 ao handshake
            await send({"type": "websocket.close", "code": 1008, "reason": mensagem})
            return
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        response = JSONResponse({"detail": mensagem}, status_code=status, headers=headers)
        await response(scope, receive, send)
