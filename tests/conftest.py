import asyncio

import pytest
from google.adk.models import LlmResponse
from google.genai import types
from httpx import AsyncClient, ASGITransport
from main import app

from root_agent.application.middlewares import guardrail_llm

@pytest.fixture
async def local_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


class ModeloGuardrailFalso:
    """
    Dublê da LLM dos guardrails: registra cada requisição e devolve os rótulos na ordem
    dada (o último se repete). `atraso` simula lentidão e `erro` simula falha do provedor.
    """

    def __init__(self, *rotulos: str, atraso: float = 0.0, erro: Exception | None = None):
        self.rotulos = list(rotulos) or ["SEGURO"]
        self.atraso = atraso
        self.erro = erro
        self.requisicoes = []

    @property
    def chamadas(self) -> int:
        return len(self.requisicoes)

    async def generate_content_async(self, llm_request, stream=False):
        self.requisicoes.append(llm_request)
        if self.atraso:
            await asyncio.sleep(self.atraso)
        if self.erro:
            raise self.erro
        rotulo = self.rotulos.pop(0) if len(self.rotulos) > 1 else self.rotulos[0]
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=rotulo)]))


@pytest.fixture
def modelo_guardrail(monkeypatch):
    """Instala o dublê no lugar da LLM dos guardrails: modelo_guardrail("SEGURO", atraso=5)."""
    def instalar(*rotulos: str, **opcoes) -> ModeloGuardrailFalso:
        modelo = ModeloGuardrailFalso(*rotulos, **opcoes)
        monkeypatch.setattr(guardrail_llm, "guardrail_model", modelo)
        return modelo
    return instalar
