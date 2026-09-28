"""
Leitura dos eventos do `/run` do ADK para os testes E2E.

As asserções usam sinais determinísticos (autor, transferências, chamadas e respostas de
tools, stateDelta) e o estado da sessão lido via GET, em vez do texto livre da LLM.
"""
import json
import uuid
import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from httpx import AsyncClient

from root_agent.application.presenters.banking_presenter import BankingPresenter

APP_NAME = "root_agent"

T = TypeVar("T")


def _campo(obj: dict, camel: str, snake: str) -> Any:
    """O /run serializa em camelCase (aliases do ADK); aceita snake_case por robustez."""
    return obj.get(camel, obj.get(snake))


def _decodificar(response: Any) -> Any:
    """O ADK encapsula retornos string de tools como {"result": "<json>"}."""
    if isinstance(response, dict) and set(response) == {"result"}:
        response = response["result"]
    if isinstance(response, str):
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return response
    return response


@dataclass
class Turno:
    """Eventos devolvidos pelo /run para uma mensagem do cliente."""

    eventos: list[dict]

    def _partes(self):
        for ev in self.eventos:
            for parte in (ev.get("content") or {}).get("parts") or []:
                yield ev, parte

    @property
    def autor_final(self) -> str | None:
        """Autor do último evento com texto (quem respondeu ao cliente)."""
        com_texto = [ev.get("author") for ev, p in self._partes() if p.get("text") and not p.get("thought")]
        return com_texto[-1] if com_texto else None

    @property
    def transferencias(self) -> list[str]:
        return [
            destino for ev in self.eventos
            if (destino := _campo(ev.get("actions") or {}, "transferToAgent", "transfer_to_agent"))
        ]

    @property
    def tools_chamadas(self) -> list[str]:
        return [
            chamada["name"] for _, p in self._partes()
            if (chamada := _campo(p, "functionCall", "function_call"))
        ]

    def respostas_tool(self, nome: str) -> list[Any]:
        return [
            _decodificar(resposta.get("response"))
            for _, p in self._partes()
            if (resposta := _campo(p, "functionResponse", "function_response")) and resposta.get("name") == nome
        ]

    @property
    def state_delta(self) -> dict:
        delta: dict = {}
        for ev in self.eventos:
            delta.update(_campo(ev.get("actions") or {}, "stateDelta", "state_delta") or {})
        return delta

    @property
    def texto(self) -> str:
        """Texto de todos os eventos do agente no turno (para asserções negativas e mensagens de erro)."""
        return "\n".join(p["text"] for _, p in self._partes() if p.get("text") and not p.get("thought"))

    @property
    def ultimo_texto(self) -> str:
        textos = [p["text"] for _, p in self._partes() if p.get("text") and not p.get("thought")]
        return textos[-1] if textos else ""


class ConversaE2E:
    """Uma sessão nova no /run; cada `enviar` devolve os eventos do turno já interpretados."""

    def __init__(self, client: AsyncClient, user_id: str):
        self.client = client
        self.user_id = user_id
        self.session_id = f"sess_e2e_{uuid.uuid4().hex[:12]}"

    async def iniciar(self) -> "ConversaE2E":
        res = await self.client.post(f"/apps/{APP_NAME}/users/{self.user_id}/sessions", json={"sessionId": self.session_id})
        assert res.status_code == 200, f"Falha ao criar sessão: {res.status_code} {res.text}"
        return self

    async def enviar(self, texto: str) -> Turno:
        payload = {
            "appName": APP_NAME,
            "userId": self.user_id,
            "sessionId": self.session_id,
            "newMessage": {"role": "user", "parts": [{"text": texto}]},
        }
        res = await self.client.post("/run", json=payload)
        assert res.status_code == 200, f"Falha no /run: {res.status_code} {res.text}"
        eventos = res.json()
        assert isinstance(eventos, list) and eventos, f"/run sem eventos: {res.text}"
        return Turno(eventos)

    async def estado(self) -> dict:
        res = await self.client.get(f"/apps/{APP_NAME}/users/{self.user_id}/sessions/{self.session_id}")
        assert res.status_code == 200, f"Falha ao ler sessão: {res.status_code} {res.text}"
        return res.json().get("state") or {}


async def com_retentativa(cenario: Callable[[], Awaitable[T]], tentativas: int = 2) -> T:
    """
    Repete a conversa INTEIRA (sessão nova a cada tentativa) quando uma decisão da LLM
    diverge do esperado. As asserções não são afrouxadas: a tentativa só passa se cumprir
    todas. Um aviso registra quando foi preciso repetir, para a instabilidade não ficar
    silenciosa; a taxa real de acerto desses comportamentos é medida pela suíte de evals.

    Só AssertionError provoca nova tentativa. Invariantes garantidas pelo código (que não
    dependem da LLM) devem usar pytest.fail, que não é AssertionError e falha na hora.
    """
    falhas: list[str] = []
    for tentativa in range(1, tentativas + 1):
        try:
            resultado = await cenario()
        except AssertionError as exc:
            falhas.append(f"tentativa {tentativa}: {exc}")
            continue
        if falhas:
            warnings.warn(f"E2E passou só na tentativa {tentativa}; anteriores: {falhas}", stacklevel=2)
        return resultado
    raise AssertionError(f"Falhou nas {tentativas} tentativas:\n" + "\n".join(falhas))


async def autenticar_por_numeros(conversa: ConversaE2E, cpf: str, data_nascimento: str, nome: str) -> dict:
    """
    Login pela máquina de estados: mensagens só com dígitos e pontuação não passam pelo
    classificador nem pela LLM, e as respostas vêm do BankingPresenter (texto determinístico).
    Devolve o estado da sessão após o login.
    """
    turno_cpf = await conversa.enviar(cpf)
    assert turno_cpf.ultimo_texto == BankingPresenter.solicitar_data_nascimento(), turno_cpf.texto
    turno_data = await conversa.enviar(data_nascimento)
    assert turno_data.ultimo_texto == BankingPresenter.autenticacao_sucesso(nome), turno_data.texto
    estado = await conversa.estado()
    assert estado.get("is_authenticated") is True, estado
    return estado
