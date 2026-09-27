import pytest
import uuid
import re
from httpx import AsyncClient
from unittest.mock import AsyncMock
from root_agent.domain.models import ClienteDTO

@pytest.fixture
def mock_banco_agil_cliente(mocker):
    """Fixture para simular um cliente autenticado com sucesso."""
    cliente = ClienteDTO(
        cpf="12345678901",
        nome="Carlos Silva",
        data_nascimento="15/03/1985",
        limite_credito=5000.0,
        score_credito=750,
        conta="0001"
    )
    mocker.patch(
        "root_agent.dependencies.banco_agil_adapter.buscar_cliente",
        return_value=cliente
    )
    return mocker.patch(
        "root_agent.dependencies.banco_agil_adapter.autenticar",
        return_value=cliente
    )

@pytest.mark.asyncio
async def test_mixed_query_apos_autenticacao(local_client: AsyncClient, mock_banco_agil_cliente):
    """
    Testa que, após a autenticação, o agente consegue lidar com uma pergunta
    que mistura um tópico do domínio (crédito) com um tópico fora de escopo (receita),
    acionando a resposta de "fora de escopo" corretamente.
    """
    session_id = f"sess_mixed_{uuid.uuid4().hex[:8]}"
    user_id = "556299999999"

    url_session = f"/apps/root_agent/users/{user_id}/sessions"
    res_session = await local_client.post(url_session, json={"sessionId": session_id})
    assert res_session.status_code == 200, f"Falha ao criar sessão: {res_session.text}"

    async def interact(message_text: str) -> str:
        payload = {
            "appName": "root_agent",
            "userId": user_id,
            "sessionId": session_id,
            "newMessage": { "parts": [{"text": message_text}] }
        }
        res = await local_client.post("/run", json=payload)
        res.raise_for_status()
        data = res.json()
        return data[-1]["content"]["parts"][0]["text"]
    
    # Etapa 1: Autenticação completa
    await interact("Olá")
    await interact("Meu CPF é 123.456.789-01")
    resp_auth = await interact("Nasci em 15/03/1985")
    assert re.search(r"Carlos|confirmada|limite|prazer", resp_auth, re.IGNORECASE)
    
    # Etapa 2: Pergunta Mista (Domínio + Fora de Escopo)
    resp_mixed = await interact("Legal! Agora quero saber meu limite e também como fazer um bolo")

    # Validação: A resposta deve tratar ambas as partes da pergunta.
    # 1. Reconhecer a parte que está fora de escopo.
    assert re.search(r"bolo|receita", resp_mixed, re.IGNORECASE), "Não mencionou o tópico fora de escopo."
    assert re.search(r"não posso|não consigo|fora d[oe].*escopo|serviços bancários", resp_mixed, re.IGNORECASE), "Não deu a resposta padrão de 'fora de escopo'."

    # 2. Endereçar a parte do domínio (crédito), possivelmente delegando-a.
    assert re.search(r"limite|crédito|agente de crédito", resp_mixed, re.IGNORECASE), "Não endereçou a parte sobre crédito."
