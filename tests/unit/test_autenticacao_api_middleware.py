"""Controle de acesso da API do ADK: token quando configurado, só loopback sem ele."""

import pytest
from fastapi import FastAPI, WebSocket
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from root_agent import config
from root_agent.infrastructure.api.middlewares.autenticacao_api_middleware import (
    AutenticacaoApiMiddleware,
    eh_cliente_local,
)

TOKEN = "segredo-de-teste"
LOCAL = ("127.0.0.1", 5000)
REMOTO = ("192.168.0.50", 5000)


def _app(token=None):
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/apps/root_agent/users/u1/sessions")
    async def sessoes():
        return [{"id": "s1"}]

    @app.websocket("/run_live")
    async def run_live(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("ok")
        await websocket.close()

    app.add_middleware(AutenticacaoApiMiddleware, obter_token=lambda: token)
    return app


async def _get(app, path="/apps/root_agent/users/u1/sessions", client=LOCAL, headers=None):
    transport = ASGITransport(app=app, client=client)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers or {}) as c:
        return await c.get(path)


@pytest.mark.asyncio
async def test_sem_token_aceita_loopback():
    r = await _get(_app(), client=LOCAL)
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("cliente", [REMOTO, ("10.0.0.2", 1), ("testclient", 50000)])
async def test_sem_token_recusa_conexao_remota(cliente):
    r = await _get(_app(), client=cliente)
    assert r.status_code == 403
    assert "BANCO_AGIL_API_TOKEN" in r.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {"Authorization": f"Bearer {TOKEN}"},
    {"authorization": f"bearer {TOKEN}"},
    {"X-API-Key": TOKEN},
])
async def test_com_token_aceita_credencial_valida_mesmo_remota(headers):
    r = await _get(_app(TOKEN), client=REMOTO, headers=headers)
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer errado"},
    {"Authorization": f"Basic {TOKEN}"},
    {"Authorization": "Bearer "},
    {"X-API-Key": "errado"},
])
async def test_com_token_recusa_sem_credencial_ate_em_loopback(headers):
    r = await _get(_app(TOKEN), client=LOCAL, headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, TOKEN])
async def test_health_e_publico(token):
    r = await _get(_app(token), path="/health", client=REMOTO)
    assert r.status_code == 200


def test_websocket_sem_token_valido_e_recusado():
    with TestClient(_app(TOKEN)) as client:
        with pytest.raises(WebSocketDisconnect) as erro:
            with client.websocket_connect("/run_live"):
                pass
    assert erro.value.code == 1008


def test_websocket_com_token_e_aceito():
    with TestClient(_app(TOKEN)) as client:
        with client.websocket_connect("/run_live", headers={"Authorization": f"Bearer {TOKEN}"}) as ws:
            assert ws.receive_text() == "ok"


def test_token_padrao_vem_da_configuracao(monkeypatch):
    middleware = AutenticacaoApiMiddleware(app=None)
    monkeypatch.setattr(config, "API_TOKEN", "do-env")
    assert middleware.obter_token() == "do-env"


@pytest.mark.parametrize("cliente, esperado", [
    (("127.0.0.1", 1), True),
    (("127.8.9.10", 1), True),
    (("::1", 1), True),
    (("::ffff:127.0.0.1", 1), True),
    (("localhost", 1), True),
    (("192.168.0.1", 1), False),
    (("::ffff:10.0.0.1", 1), False),
    (("nao-e-ip", 1), False),
    (None, False),
])
def test_eh_cliente_local(cliente, esperado):
    assert eh_cliente_local({"client": cliente}) is esperado
