"""Testes do middleware que impede o cliente HTTP de escrever estado de autenticação."""

import json

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from root_agent.infrastructure.api.middlewares.protected_state_middleware import (
    ProtectedStateMiddleware,
    chaves_protegidas_no_body,
)


@pytest.fixture
def app():
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["POST", "PATCH", "GET"])
    async def echo(request: Request, path: str):
        return {"body": (await request.body()).decode()}

    app.add_middleware(ProtectedStateMiddleware)
    return app


@pytest.mark.parametrize("body", [
    {"sessionId": "s1", "state": {"is_authenticated": True}},
    {"stateDelta": {"cliente_autenticado": {"cpf": "98765432100"}}},
    {"appName": "root_agent", "state_delta": {"auth_tentativas": 0}},
    {"is_authenticated": True},  # endpoint legado: o body é o próprio estado
])
def test_detecta_chaves_protegidas(body):
    assert chaves_protegidas_no_body(json.dumps(body).encode())


@pytest.mark.parametrize("body", [
    b"",
    b"nao e json",
    json.dumps({"sessionId": "s1"}).encode(),
    json.dumps({"appName": "root_agent", "newMessage": {"parts": [{"text": "is_authenticated"}]}}).encode(),
    json.dumps({"stateDelta": {}}).encode(),
])
def test_ignora_bodies_sem_estado_protegido(body):
    assert chaves_protegidas_no_body(body) == set()


@pytest.mark.asyncio
async def test_bloqueia_criacao_de_sessao_ja_autenticada(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/apps/root_agent/users/u1/sessions",
            json={"sessionId": "s1", "state": {"is_authenticated": True, "cliente_autenticado": {"cpf": "98765432100"}}},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bloqueia_patch_de_state_delta(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.patch(
            "/apps/root_agent/users/u1/sessions/s1",
            json={"stateDelta": {"is_authenticated": True}},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_repassa_body_intacto_para_requisicoes_legitimas(app):
    payload = {"appName": "root_agent", "userId": "u1", "sessionId": "s1", "newMessage": {"parts": [{"text": "olá"}]}}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/run", json=payload)
    assert r.status_code == 200
    assert json.loads(r.json()["body"]) == payload
