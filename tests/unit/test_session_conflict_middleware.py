import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response

from root_agent.infrastructure.api.middlewares.session_conflict_middleware import (
    SessionConflictMiddleware,
    set_body
)


class FakeSessionQueue:
    def __init__(self):
        self.acquired_sessions = []

    @asynccontextmanager
    async def acquire(self, session_id: str):
        self.acquired_sessions.append(session_id)
        yield


@pytest.mark.asyncio
async def test_set_body_permite_releitura():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [],
    }
    req = Request(scope)
    await set_body(req, b"corpo do teste")

    body = await req.body()
    assert body == b"corpo do teste"


@pytest.mark.asyncio
async def test_dispatch_ignora_rotas_nao_sessions():
    fake_queue = FakeSessionQueue()
    app_mock = MagicMock()
    middleware = SessionConflictMiddleware(app=app_mock, session_queue=fake_queue)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/other-route",
        "headers": [],
    }
    req = Request(scope)

    call_next = AsyncMock(return_value=Response(content=b"ok", status_code=200))
    resp = await middleware.dispatch(req, call_next)

    assert resp.status_code == 200
    assert len(fake_queue.acquired_sessions) == 0


@pytest.mark.asyncio
async def test_dispatch_intercepta_post_sessions_sucesso():
    fake_queue = FakeSessionQueue()
    app_mock = MagicMock()
    middleware = SessionConflictMiddleware(app=app_mock, session_queue=fake_queue)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/apps/bank/users/user1/sessions",
        "headers": [(b"content-type", b"application/json")],
    }
    req = Request(scope)
    await set_body(req, b'{"sessionId": "sess123"}')

    call_next = AsyncMock(return_value=Response(content=b'{"created": true}', status_code=200))
    resp = await middleware.dispatch(req, call_next)

    assert resp.status_code == 200
    assert "sess123" in fake_queue.acquired_sessions


@pytest.mark.asyncio
async def test_dispatch_trata_conflito_409_com_patch():
    fake_queue = FakeSessionQueue()
    app_mock = MagicMock()
    middleware = SessionConflictMiddleware(app=app_mock, session_queue=fake_queue)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/apps/bank/users/user1/sessions",
        "headers": [(b"content-type", b"application/json")],
        "server": ("testserver", 80),
        "app": app_mock,
    }
    req = Request(scope)
    await set_body(req, b'{"sessionId": "sess123"}')

    call_next = AsyncMock(return_value=Response(content=b'{"conflict": true}', status_code=409))

    mock_patch_resp = MagicMock()
    mock_patch_resp.content = b'{"patched": true}'
    mock_patch_resp.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_patch_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        resp = await middleware.dispatch(req, call_next)

        assert resp.status_code == 200
        assert resp.body == b'{"patched": true}'
        assert "sess123" in fake_queue.acquired_sessions
        mock_client.patch.assert_called_once()
