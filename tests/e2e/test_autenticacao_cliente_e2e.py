"""
E2E da autenticação e do encerramento pela API HTTP do ADK (/run).

As asserções usam sinais determinísticos: textos do BankingPresenter (atalhos da máquina de
estados), tools chamadas, transferências e o estado da sessão lido via GET. O que é texto
livre da LLM (ex.: a saudação pedir o CPF) é medido na suíte de evals (`pytest -m eval`),
nos cenários autenticacao_* e tchau_*.
"""
import pytest

from root_agent.application.presenters.banking_presenter import BankingPresenter
from root_agent.domain.conversation_state import (
    AUTH_TENTATIVAS_KEY,
    CLIENTE_KEY,
    CONVERSATION_STATE_KEY,
    BankingConversationState,
)
from root_agent.domain.guardrails import MAX_TENTATIVAS_AUTH
from root_agent.domain.models import ClienteDTO
from tests.e2e.apoio import autenticar_por_numeros, com_retentativa

TRIAGEM = "agente_triagem"
CLIENTE = ClienteDTO(
    cpf="12345678901",
    nome="Carlos Silva",
    data_nascimento="15/03/1985",
    limite_credito=5000.0,
    score_credito=750,
    conta="0001",
)


@pytest.fixture
def mock_banco_agil_cliente(mocker):
    return mocker.patch("root_agent.dependencies.banco_agil_adapter.autenticar", return_value=CLIENTE)


@pytest.mark.e2e
async def test_fluxo_completo_autenticacao_sucesso(nova_conversa, mock_banco_agil_cliente):
    """
    Fluxo completo de autenticação bem-sucedida:
    1. Saudação (LLM): a triagem responde sem transferir, sem tools e sem autenticar.
    2. CPF junto de texto: a máquina de estados captura o CPF e pede a data (presenter).
    3. Data de nascimento: o adapter autentica e o presenter dá as boas-vindas com o menu.
    Só o passo 1 depende da LLM, e apenas pelas invariantes estruturais acima.
    """
    conversa = await nova_conversa("5511999990001")

    saudacao = await conversa.enviar("Olá, bom dia!")
    assert saudacao.autor_final == TRIAGEM, saudacao.eventos
    assert not saudacao.transferencias, f"transferiu antes do login: {saudacao.transferencias}"
    assert not saudacao.tools_chamadas, f"chamou tools antes do login: {saudacao.tools_chamadas}"
    assert (await conversa.estado()).get("is_authenticated") is not True

    turno_cpf = await conversa.enviar("Meu CPF é 123.456.789-01")
    assert turno_cpf.ultimo_texto == BankingPresenter.solicitar_data_nascimento(), turno_cpf.texto
    assert turno_cpf.state_delta.get(CONVERSATION_STATE_KEY) == BankingConversationState.AGUARDANDO_DATA_NASCIMENTO.value

    turno_data = await conversa.enviar("15/03/1985")
    assert turno_data.ultimo_texto == BankingPresenter.autenticacao_sucesso("Carlos Silva"), turno_data.texto
    mock_banco_agil_cliente.assert_called_once_with("12345678901", "15/03/1985")

    estado = await conversa.estado()
    assert estado["is_authenticated"] is True
    assert estado["nome"] == "Carlos Silva"
    assert estado[CLIENTE_KEY]["cpf"] == "12345678901"
    assert estado[CONVERSATION_STATE_KEY] == BankingConversationState.AUTENTICADO.value


async def test_fluxo_autenticacao_credenciais_invalidas(nova_conversa, mocker, sem_llm):
    """
    Credenciais não encontradas pelo adapter: o presenter informa a falha com as tentativas
    restantes e a sessão volta a aguardar o CPF, sem autenticar. Só há mensagens numéricas,
    que não passam pela LLM (garantido por `sem_llm`), então o teste roda offline.
    """
    autenticar = mocker.patch("root_agent.dependencies.banco_agil_adapter.autenticar", return_value=None)
    conversa = await nova_conversa("5511999990002")

    turno_cpf = await conversa.enviar("111.222.333-44")
    assert turno_cpf.ultimo_texto == BankingPresenter.solicitar_data_nascimento(), turno_cpf.texto

    turno_data = await conversa.enviar("01/01/2000")
    assert turno_data.ultimo_texto == BankingPresenter.autenticacao_falha(MAX_TENTATIVAS_AUTH - 1), turno_data.texto
    autenticar.assert_called_once_with("11122233344", "01/01/2000")

    estado = await conversa.estado()
    assert estado.get("is_authenticated") is not True
    assert not estado.get(CLIENTE_KEY)
    assert estado[AUTH_TENTATIVAS_KEY] == 1
    assert estado[CONVERSATION_STATE_KEY] == BankingConversationState.AGUARDANDO_CPF.value


@pytest.mark.e2e
async def test_encerramento_atendimento_reseta_sessao_e_exige_reautenticacao(nova_conversa, mock_banco_agil_cliente):
    """
    Ao se despedir, o cliente autenticado tem o atendimento encerrado (tool
    encerrar_atendimento) e a sessão perde a autenticação; a consulta seguinte não chega a
    agentes especializados nem expõe dados da sessão anterior.

    Chamar a tool na despedida e não transferir depois são decisões da LLM: se alguma
    divergir, a conversa inteira é repetida uma vez (com_retentativa, com aviso). As
    invariantes garantidas pelo código (estado sem autenticação, auth_guard nas tools,
    nenhum dado do cliente no texto) usam pytest.fail e falham na hora, sem nova tentativa.
    A taxa real desses comportamentos é medida nos evals tchau_encerra_sessao e
    tchau_exige_nova_autenticacao.
    """
    async def cenario():
        conversa = await nova_conversa("5511999990003")
        await autenticar_por_numeros(conversa, "123.456.789-01", "15/03/1985", "Carlos Silva")

        despedida = await conversa.enviar("Muito obrigado, tchau!")
        assert "encerrar_atendimento" in despedida.tools_chamadas, (
            f"despedida sem encerrar_atendimento: tools={despedida.tools_chamadas} texto={despedida.texto[:200]!r}"
        )
        estado = await conversa.estado()
        if estado.get("is_authenticated") is True or estado.get(CLIENTE_KEY):
            pytest.fail(f"encerramento não limpou a autenticação: {estado}")

        consulta = await conversa.enviar("Qual é o meu limite de crédito?")
        for resposta in consulta.respostas_tool("consultar_limite_credito"):
            if not (isinstance(resposta, dict) and resposta.get("erro") == "nao_autenticado"):
                pytest.fail(f"consultar_limite_credito executou após o encerramento: {resposta}")
        if any(dado in consulta.texto for dado in ("Carlos Silva", "5.000", "5000")):
            pytest.fail(f"dados da sessão anterior expostos após o encerramento: {consulta.texto[:300]!r}")
        if (await conversa.estado()).get("is_authenticated") is True:
            pytest.fail("sessão voltou a ficar autenticada sem novo login")

        especialistas = [t for t in consulta.transferencias if t != TRIAGEM]
        assert not especialistas, f"transferiu sem autenticação para {especialistas}"
        assert not consulta.tools_chamadas, f"chamou tools sem autenticação: {consulta.tools_chamadas}"
        assert consulta.autor_final == TRIAGEM, consulta.eventos

    await com_retentativa(cenario)
