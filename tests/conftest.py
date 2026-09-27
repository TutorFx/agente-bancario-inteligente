import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.fixture
async def local_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
