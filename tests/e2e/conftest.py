"""
Configuração dos testes E2E (API HTTP do ADK em processo).

Testes marcados com `e2e` chamam a LLM real: são pulados quando não há chave de API, para
o `pytest` offline ficar verde, e rodam no `pytest` padrão quando a chave existe.
"""
from collections.abc import Awaitable, Callable

import pytest
from google.adk.models.lite_llm import LiteLlm
from httpx import AsyncClient

from root_agent import config as app_config
from tests.e2e.apoio import ConversaE2E

MOTIVO_SEM_CHAVE = "E2E com LLM real: defina GEMINI_API_KEY, GOOGLE_API_KEY ou LLM_API_KEY"


def pytest_collection_modifyitems(config, items):
    # config.py já leu o .env (load_dotenv) e consolidou as três variáveis em LLM_API_KEY
    if app_config.LLM_API_KEY:
        return
    pular = pytest.mark.skip(reason=MOTIVO_SEM_CHAVE)
    for item in items:
        if item.get_closest_marker("e2e"):
            item.add_marker(pular)


@pytest.fixture
def nova_conversa(local_client: AsyncClient) -> Callable[[str], Awaitable[ConversaE2E]]:
    """Fábrica de sessões novas no /run: `conversa = await nova_conversa("5511999990001")`."""
    async def criar(user_id: str) -> ConversaE2E:
        return await ConversaE2E(local_client, user_id).iniciar()
    return criar


@pytest.fixture
def sem_llm(mocker):
    """
    Prova que o teste roda offline: qualquer chamada a uma LLM (agentes ou guardrails) falha
    na hora e é conferida na finalização, já que o guardrail engole erros da própria LLM.
    """
    chamada = mocker.patch.object(
        LiteLlm, "generate_content_async", side_effect=AssertionError("este teste não deveria chamar a LLM"),
    )
    yield chamada
    assert not chamada.called, f"a LLM foi chamada {chamada.call_count} vez(es)"
