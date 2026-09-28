"""
Executor de conversas roteirizadas contra o root_agent, em processo (sem HTTP).

Cada execução roda com uma cópia isolada dos CSVs de `data/` e com a API de câmbio
substituída por cotações fixas, para que as métricas meçam o comportamento dos agentes
e não a variação da API externa ou o estado deixado por execuções anteriores.
"""
import asyncio
import csv
import json
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

from google.adk.runners import InMemoryRunner
from google.genai import types

from root_agent.agent import root_agent
from root_agent.dependencies import banco_agil_adapter
from root_agent.domain.models import CotacaoDTO
from root_agent.infrastructure.adapters import banco_agil_adapter as adapter_module

APP_NAME = "root_agent"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Cotações fixas (1 unidade da moeda em BRL) usadas no lugar da API ao vivo
COTACOES_FIXAS = {
    "USD": 5.4321,
    "EUR": 6.1234,
    "GBP": 7.0123,
    "JPY": 0.0371,
    "CHF": 6.5432,
    "ARS": 0.0058,
}


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class TurnResult:
    user: str
    reply: str = ""
    agent: str | None = None
    transfers: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_responses: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ConversationResult:
    turns: list[TurnResult]
    final_state: dict[str, Any]
    clientes: dict[str, dict[str, str]]  # clientes.csv ao final, indexado por CPF

    def tool_responses(self, name: str | None = None) -> list[dict[str, Any]]:
        return [
            r["response"]
            for t in self.turns
            for r in t.tool_responses
            if name is None or r["name"] == name
        ]


async def _cotacao_fixa(moeda_destino: str) -> CotacaoDTO:
    return CotacaoDTO(
        moeda_origem="BRL",
        moeda_destino=moeda_destino.upper(),
        taxa=COTACOES_FIXAS.get(moeda_destino.upper(), 0.0),
        timestamp="Mon, 28 Sep 2026 12:00:00 +0000",
    )


@contextmanager
def ambiente_isolado():
    """Aponta o adapter para uma cópia temporária de data/ e fixa as cotações."""
    with tempfile.TemporaryDirectory(prefix="eval_data_") as tmp:
        tmp_dir = Path(tmp)
        for arquivo in ("clientes.csv", "score_limite.csv", "solicitacoes_aumento_limite.csv"):
            shutil.copy(DATA_DIR / arquivo, tmp_dir / arquivo)
        with patch.object(adapter_module, "CSV_PATH", str(tmp_dir / "clientes.csv")), \
             patch.object(adapter_module, "SCORE_LIMITE_PATH", str(tmp_dir / "score_limite.csv")), \
             patch.object(adapter_module, "SOLICITACOES_LIMITE_PATH", str(tmp_dir / "solicitacoes_aumento_limite.csv")), \
             patch.object(banco_agil_adapter, "get_cotacao", _cotacao_fixa):
            yield tmp_dir


def _decodificar(response: Any) -> Any:
    """O ADK encapsula retornos string como {"result": "<json>"}; devolve o JSON decodificado."""
    payload = response
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload


class FalhaNoLogin(Exception):
    """O login do prelúdio não autenticou o cliente: falha de comportamento, não de infraestrutura."""


async def _enviar(runner: InMemoryRunner, user_id: str, session_id: str, mensagem: str) -> TurnResult:
    turn = TurnResult(user=mensagem)
    textos: list[str] = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=mensagem)]),
    ):
        if event.actions and event.actions.transfer_to_agent:
            turn.transfers.append(event.actions.transfer_to_agent)
        for fc in event.get_function_calls():
            turn.tool_calls.append(ToolCall(name=fc.name, args=dict(fc.args or {})))
        for fr in event.get_function_responses():
            turn.tool_responses.append({"name": fr.name, "response": _decodificar(fr.response)})
        texto = "".join(
            p.text for p in (event.content.parts if event.content and event.content.parts else [])
            if p.text and not getattr(p, "thought", False)
        )
        if texto.strip() and event.author != "user":
            textos.append(texto.strip())
            turn.agent = event.author
    turn.reply = "\n\n".join(textos)
    return turn


async def _login(runner: InMemoryRunner, user_id: str, session_id: str, cliente: dict) -> None:
    """
    Autentica pelo fluxo real (CPF e depois data de nascimento), em vez de semear o estado
    à mão: o estado pós-login fica idêntico ao de produção. Mensagens só com dígitos e
    pontuação não passam pelo classificador nem pela LLM, então o prelúdio não custa API.
    """
    ultimo = None
    for mensagem in (cliente["cpf"], cliente["data_nascimento"]):
        ultimo = await _enviar(runner, user_id, session_id, mensagem)
    session = await runner.session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if session.state.get("is_authenticated") is not True:
        raise FalhaNoLogin(f"login de {cliente['nome']} não autenticou; resposta: {ultimo.reply[:200]!r}")


async def executar_conversa(
    mensagens: list[str],
    cliente: dict | None = None,
    state: dict[str, Any] | None = None,
) -> ConversationResult:
    """Roda o roteiro numa sessão nova; com `cliente`, faz login antes (turnos não avaliados)."""
    with ambiente_isolado() as tmp_dir:
        runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
        user_id = f"eval_{uuid.uuid4().hex[:8]}"
        session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id=user_id, state=state or {}
        )
        if cliente:
            await _login(runner, user_id, session.id, cliente)

        turns = [await _enviar(runner, user_id, session.id, mensagem) for mensagem in mensagens]

        final = await runner.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session.id
        )
        with open(tmp_dir / "clientes.csv", newline="", encoding="utf-8") as f:
            clientes = {row["cpf"]: row for row in csv.DictReader(f)}

        return ConversationResult(turns=turns, final_state=dict(final.state), clientes=clientes)


async def executar_com_retentativas(
    mensagens: list[str],
    cliente: dict | None = None,
    state: dict[str, Any] | None = None,
    tentativas: int = 3,
) -> ConversationResult:
    """Repete a conversa em erros de infraestrutura (rate limit, 5xx); não mascara falhas de comportamento."""
    for tentativa in range(1, tentativas + 1):
        try:
            return await executar_conversa(mensagens, cliente, state)
        except FalhaNoLogin:
            raise
        except Exception:
            if tentativa == tentativas:
                raise
            await asyncio.sleep(5 * tentativa)
    raise RuntimeError("inalcançável")
