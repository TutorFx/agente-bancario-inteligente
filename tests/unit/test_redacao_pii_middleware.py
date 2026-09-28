"""Redação de CPF/data nas respostas da API do ADK (defesa em profundidade na leitura)."""

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, StreamingResponse
from httpx import ASGITransport, AsyncClient

from root_agent.infrastructure.api.middlewares.redacao_pii_middleware import (
    RedacaoPiiMiddleware,
    redigir_pii,
)

SESSAO = {
    "id": "sess_12345678900",
    "appName": "root_agent",
    "userId": "user_simulacao",
    "state": {
        "is_authenticated": True,
        "nome": "João Silva",
        "auth_cpf_temp": None,
        "cliente_autenticado": {"cpf": "12345678900", "nome": "João Silva", "conta": "0001"},
        "legado": '{"cliente": {"cpf": "123.456.789-00"}}',
    },
    "events": [
        {
            "id": "a1234567-8901-4bcd-9ef0-123456789012",
            "author": "user",
            "content": {"role": "user", "parts": [{"text": "123.456.789-00"}, {"text": "nasci em 15/03/1985"}]},
        },
        {
            "id": "e-2",
            "author": "agente_triagem",
            "content": {"role": "model", "parts": [{"text": "Pedido registrado em 28/09/2026."}]},
            "actions": {"stateDelta": {"auth_cpf_temp": "12345678900", "auth_data_temp": "15/03/1985"}},
        },
        {
            "id": "e-3",
            "author": "agente_credito",
            "content": {"parts": [{"functionResponse": {"name": "consultar", "response": {
                "cliente": {"cpf": 12345678900, "data_nascimento": "15/03/1985", "limite": 5000.0}
            }}}]},
        },
    ],
}


def test_redige_estado_eventos_do_usuario_e_chaves_sensiveis():
    redigido = redigir_pii(json.loads(json.dumps(SESSAO)))
    texto = json.dumps(redigido, ensure_ascii=False)

    for pii in ("12345678900", "123.456.789-00", "15/03/1985"):
        assert pii not in texto.replace("sess_12345678900", "")

    assert redigido["state"]["cliente_autenticado"] == {"cpf": "[CPF omitido]", "nome": "João Silva", "conta": "0001"}
    assert redigido["state"]["auth_cpf_temp"] is None  # ausência continua visível
    assert redigido["state"]["is_authenticated"] is True
    assert [p["text"] for p in redigido["events"][0]["content"]["parts"]] == ["[CPF omitido]", "nasci em [data omitida]"]
    assert redigido["events"][1]["actions"]["stateDelta"] == {
        "auth_cpf_temp": "[CPF omitido]", "auth_data_temp": "[data omitida]",
    }
    resposta_tool = redigido["events"][2]["content"]["parts"][0]["functionResponse"]["response"]["cliente"]
    assert resposta_tool == {"cpf": "[CPF omitido]", "data_nascimento": "[data omitida]", "limite": 5000.0}


def test_preserva_identificadores_e_respostas_dos_agentes():
    redigido = redigir_pii(json.loads(json.dumps(SESSAO)))
    assert redigido["id"] == "sess_12345678900"
    assert redigido["events"][0]["id"] == "a1234567-8901-4bcd-9ef0-123456789012"
    # Datas nas respostas dos agentes não são dados digitados pelo cliente
    assert redigido["events"][1]["content"]["parts"][0]["text"] == "Pedido registrado em 28/09/2026."


@pytest.fixture
def app():
    app = FastAPI()

    @app.get("/apps/root_agent/users/u1/sessions/s1")
    async def sessao():
        return SESSAO

    @app.post("/run_sse")
    async def run_sse():
        async def eventos():
            yield "data: " + json.dumps(SESSAO["events"][1]) + "\n\n"
            yield "data: " + json.dumps(SESSAO["events"][2])[:40]  # evento dividido em dois pedaços
            yield json.dumps(SESSAO["events"][2])[40:] + "\n\n"
        return StreamingResponse(eventos(), media_type="text/event-stream")

    @app.get("/apps/root_agent/texto")
    async def texto():
        return PlainTextResponse("cpf 12345678900")

    @app.get("/openapi-like")
    async def fora_do_escopo():
        return {"cpf": "12345678900"}

    app.add_middleware(RedacaoPiiMiddleware)
    return app


async def _cliente(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_resposta_json_de_sessao_sai_redigida(app):
    async with await _cliente(app) as c:
        r = await c.get("/apps/root_agent/users/u1/sessions/s1")
    assert r.status_code == 200
    assert int(r.headers["content-length"]) == len(r.content)
    assert r.json()["state"]["cliente_autenticado"]["cpf"] == "[CPF omitido]"
    assert "15/03/1985" not in r.text


@pytest.mark.asyncio
async def test_stream_sse_sai_redigido_evento_a_evento(app):
    async with await _cliente(app) as c:
        r = await c.post("/run_sse")
    blocos = [b for b in r.text.split("\n\n") if b]
    assert len(blocos) == 2
    eventos = [json.loads(b.removeprefix("data: ")) for b in blocos]
    assert eventos[0]["actions"]["stateDelta"]["auth_cpf_temp"] == "[CPF omitido]"
    assert "12345678900" not in r.text and "15/03/1985" not in r.text


@pytest.mark.asyncio
async def test_respostas_nao_json_ou_fora_das_rotas_do_adk_passam_intactas(app):
    async with await _cliente(app) as c:
        texto = await c.get("/apps/root_agent/texto")
        fora = await c.get("/openapi-like")
    assert texto.text == "cpf 12345678900"
    assert fora.json() == {"cpf": "12345678900"}


def test_corpo_json_invalido_e_mantido():
    from root_agent.infrastructure.api.middlewares.redacao_pii_middleware import _redigir_bytes_json
    assert _redigir_bytes_json(b"nao e json") == b"nao e json"
