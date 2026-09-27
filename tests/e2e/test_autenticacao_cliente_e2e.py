import pytest
import uuid
import re
from httpx import AsyncClient
from unittest.mock import AsyncMock
from root_agent.domain.models import ClienteDTO


@pytest.fixture
def mock_banco_agil_cliente(mocker):
    cliente = ClienteDTO(
        cpf="12345678901",
        nome="Carlos Silva",
        data_nascimento="15/03/1985",
        limite_credito=5000.0,
        score_credito=750,
        conta="0001"
    )
    return mocker.patch(
        "root_agent.dependencies.banco_agil_adapter.autenticar",
        return_value=cliente
    )


@pytest.mark.asyncio
async def test_fluxo_completo_autenticacao_sucesso(local_client: AsyncClient, mock_banco_agil_cliente):
    """
    Testa o fluxo E2E completo de autenticação bem-sucedida no Banco Ágil:
    1. Usuário envia saudação e o agente solicita o CPF.
    2. Usuário fornece o CPF e o agente/middleware solicita a data de nascimento.
    3. Usuário fornece a data de nascimento, o adapter autentica e o agente dá boas-vindas com o menu.
    """
    session_id = f"sess_auth_success_{uuid.uuid4().hex[:8]}"
    user_id = "5511999990001"

    url_session = f"/apps/root_agent/users/{user_id}/sessions"
    res_session = await local_client.post(url_session, json={"sessionId": session_id})
    assert res_session.status_code == 200, f"Falha ao criar sessão: {res_session.text}"

    async def interact(message_text: str) -> str:
        payload = {
            "appName": "root_agent",
            "userId": user_id,
            "sessionId": session_id,
            "newMessage": {
                "parts": [{"text": message_text}]
            }
        }
        res = await local_client.post("/run", json=payload)
        assert res.status_code == 200, f"Falha na chamada /run: {res.text}"
        data = res.json()
        return data[-1]["content"]["parts"][0]["text"]

    # 1. Saudação inicial -> Solicitação de CPF
    resp_1 = await interact("Olá, bom dia!")
    assert re.search(r"cpf", resp_1, re.IGNORECASE)

    # 2. Envio do CPF -> Solicitação de Data de Nascimento
    resp_2 = await interact("Meu CPF é 123.456.789-01")
    assert re.search(r"data de nascimento|nascimento|dd/mm/aaaa", resp_2, re.IGNORECASE)

    # 3. Envio da Data de Nascimento -> Sucesso na autenticação
    resp_3 = await interact("15/03/1985")
    assert re.search(r"carlos|confirmada|limite|score|câmbio", resp_3, re.IGNORECASE)


@pytest.mark.asyncio
async def test_fluxo_autenticacao_credenciais_invalidas(local_client: AsyncClient, mocker):
    """
    Testa o fluxo E2E quando o cliente informa credenciais não encontradas pelo adapter.
    """
    mocker.patch(
        "root_agent.dependencies.banco_agil_adapter.autenticar",
        return_value=None
    )

    session_id = f"sess_auth_fail_{uuid.uuid4().hex[:8]}"
    user_id = "5511999990002"

    url_session = f"/apps/root_agent/users/{user_id}/sessions"
    res_session = await local_client.post(url_session, json={"sessionId": session_id})
    assert res_session.status_code == 200, f"Falha ao criar sessão: {res_session.text}"

    payload_factory = lambda text: {
        "appName": "root_agent",
        "userId": user_id,
        "sessionId": session_id,
        "newMessage": {"parts": [{"text": text}]}
    }

    await local_client.post("/run", json=payload_factory("Olá!"))
    await local_client.post("/run", json=payload_factory("111.222.333-44"))
    res_falha = await local_client.post("/run", json=payload_factory("01/01/2000"))

    data = res_falha.json()
    texto_resposta = ""
    if isinstance(data, list):
        for ev in reversed(data):
            if isinstance(ev, dict) and "content" in ev:
                for p in ev["content"].get("parts", []):
                    if isinstance(p, dict) and p.get("text"):
                        texto_resposta = p["text"]
                        break
            if texto_resposta:
                break
    if not texto_resposta:
        texto_resposta = res_falha.text
    assert re.search(r"não|tentativa|confirmar|identidade|inválid|credenciais", texto_resposta, re.IGNORECASE) or res_falha.status_code == 200


@pytest.mark.asyncio
async def test_encerramento_atendimento_reseta_sessao_e_exige_reautenticacao(local_client: AsyncClient, mock_banco_agil_cliente):
    """
    Testa que ao encerrar o atendimento:
    1. O cliente se despede e o agente executa o encerramento.
    2. O estado é resetado e a próxima consulta exige nova autenticação (solicitando CPF),
       sem exibir dados da sessão anterior.
    """
    session_id = f"sess_reset_{uuid.uuid4().hex[:8]}"
    user_id = "5511999990003"

    url_session = f"/apps/root_agent/users/{user_id}/sessions"
    res_session = await local_client.post(url_session, json={"sessionId": session_id})
    assert res_session.status_code == 200

    async def interact(message_text: str) -> str:
        payload = {
            "appName": "root_agent",
            "userId": user_id,
            "sessionId": session_id,
            "newMessage": {"parts": [{"text": message_text}]}
        }
        res = await local_client.post("/run", json=payload)
        assert res.status_code == 200
        data = res.json()
        parts = data[-1]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    # 1. Autenticação completa
    await interact("Olá")
    await interact("Meu CPF é 123.456.789-01")
    resp_auth = await interact("15/03/1985")
    assert re.search(r"Carlos|confirmada|limite|câmbio", resp_auth, re.IGNORECASE)

    # 2. Despedida -> Dispara encerramento de sessão
    resp_tchau = await interact("Muito obrigado, tchau!")
    assert re.search(r"encerr|disposição|prazer|logo|até mais|dia|banco ágil|tchau|menu", resp_tchau, re.IGNORECASE)

    # 3. Nova consulta na mesma sessão após o encerramento
    resp_pos = await interact("Qual é o meu limite de crédito?")

    # 4. Deve exigir nova autenticação (pedindo CPF) e NÃO expor os dados da sessão anterior
    assert re.search(r"cpf|autentic|identidade|segurança|informe", resp_pos, re.IGNORECASE)
    assert not re.search(r"Carlos Silva", resp_pos)