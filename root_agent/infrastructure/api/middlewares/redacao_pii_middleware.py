import json
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from root_agent.domain.conversation_state import AUTH_CPF_TEMP_KEY
from root_agent.domain.pii import MASCARA_CPF, MASCARA_DATA, mascarar_pii
from root_agent.utils import get_logger

logger = get_logger("middleware.redacao_pii")

# Valores sempre ocultados, em qualquer nível do JSON (estado, stateDelta, respostas de tools)
CHAVES_CPF = frozenset({"cpf", "cpf_cliente", AUTH_CPF_TEMP_KEY})
CHAVES_DATA = frozenset({"data_nascimento", "auth_data_temp"})
# Subárvores de texto livre em que CPF/datas digitados são mascarados
CHAVES_ESTADO = frozenset({"state", "stateDelta", "state_delta"})
PREFIXOS_REDIGIDOS = ("/apps/", "/run", "/debug/")


def _mascarar_textos(valor: Any) -> Any:
    if isinstance(valor, str):
        return mascarar_pii(valor)
    if isinstance(valor, dict):
        return {k: _redigir_campo(k, v, mascarar_textos=True) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_mascarar_textos(v) for v in valor]
    return valor


def _redigir_campo(chave: str, valor: Any, mascarar_textos: bool = False) -> Any:
    if valor is not None and chave in CHAVES_CPF:
        return MASCARA_CPF
    if valor is not None and chave in CHAVES_DATA:
        return MASCARA_DATA
    if mascarar_textos or chave in CHAVES_ESTADO:
        return _mascarar_textos(valor)
    return redigir_pii(valor)


def _redigir_evento_do_usuario(evento: dict) -> dict:
    # Mensagens do cliente gravadas antes do MascaramentoCredenciaisPlugin (ou sem ele)
    conteudo = evento.get("content")
    if isinstance(conteudo, dict):
        evento["content"] = {
            **conteudo,
            "parts": [
                {**p, "text": mascarar_pii(p["text"])} if isinstance(p, dict) and isinstance(p.get("text"), str) else p
                for p in conteudo.get("parts") or []
            ],
        }
    return evento


def redigir_pii(valor: Any) -> Any:
    """
    Oculta CPF e data de nascimento num corpo JSON da API do ADK: chaves sensíveis em
    qualquer nível, texto livre do estado e mensagens do usuário. Identificadores e as
    respostas dos agentes ficam intactos (ex: IDs de evento não passam pela máscara).
    """
    if isinstance(valor, list):
        return [redigir_pii(v) for v in valor]
    if not isinstance(valor, dict):
        return valor
    redigido = {k: _redigir_campo(k, v) for k, v in valor.items()}
    if redigido.get("author") == "user":
        redigido = _redigir_evento_do_usuario(redigido)
    return redigido


def _redigir_bytes_json(corpo: bytes) -> bytes:
    try:
        dados = json.loads(corpo)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return corpo
    return json.dumps(redigir_pii(dados), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _redigir_bloco_sse(bloco: bytes) -> bytes:
    linhas = []
    for linha in bloco.split(b"\n"):
        if linha.startswith(b"data:"):
            linha = b"data: " + _redigir_bytes_json(linha[5:].strip())
        linhas.append(linha)
    return b"\n".join(linhas)


class RedacaoPiiMiddleware:
    """
    Defesa em profundidade na leitura: mesmo com acesso autorizado, as respostas JSON e SSE
    das rotas de sessão/execução do ADK saem sem CPF e data de nascimento. Cobre sessões
    gravadas antes do mascaramento na entrada e o CPF que o estado guarda para as tools.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(PREFIXOS_REDIGIDOS):
            await self.app(scope, receive, send)
            return

        modo = None
        inicio: Message | None = None
        corpo = bytearray()
        pendente = b""

        async def send_redigido(message: Message) -> None:
            nonlocal modo, inicio, pendente
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                tipo = headers.get("content-type", "")
                if tipo.startswith("application/json"):
                    modo, inicio = "json", message  # só envia com o corpo redigido
                    return
                if tipo.startswith("text/event-stream"):
                    modo = "sse"
                    # O tamanho muda com a redação
                    if "content-length" in headers:
                        del headers["content-length"]
                await send(message)
                return

            if message["type"] != "http.response.body" or modo is None:
                await send(message)
                return

            mais = message.get("more_body", False)
            if modo == "json":
                corpo.extend(message.get("body", b""))
                if mais:
                    return
                assert inicio is not None  # modo "json" só é definido junto com inicio
                redigido = _redigir_bytes_json(bytes(corpo))
                headers = MutableHeaders(raw=inicio["headers"])
                headers["content-length"] = str(len(redigido))
                await send(inicio)
                await send({"type": "http.response.body", "body": redigido, "more_body": False})
                return

            # SSE: redige cada evento completo ("data: {...}\n\n") assim que ele chega
            pendente += message.get("body", b"")
            *completos, pendente = pendente.split(b"\n\n")
            saida = b"".join(_redigir_bloco_sse(b) + b"\n\n" for b in completos)
            if not mais and pendente:
                saida += _redigir_bloco_sse(pendente)
                pendente = b""
            await send({"type": "http.response.body", "body": saida, "more_body": mais})

        await self.app(scope, receive, send_redigido)
