"""
E2E de uma pergunta mista (domínio + fora de escopo) após a autenticação.

Antes, o teste conferia o texto livre da LLM com regex ("bolo", "não posso"...) e falhava de
forma intermitente. Agora as asserções usam os eventos do /run; se a resposta menciona as
duas partes e recusa a receita com gentileza é medido pelo eval
roteamento_pergunta_mista_limite_e_receita (`pytest -m eval`).
"""
import pytest

from root_agent.domain.models import ClienteDTO
from tests.e2e.apoio import autenticar_por_numeros, com_retentativa

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
    """Cliente autenticado com sucesso e encontrado pela consulta de limite."""
    mocker.patch("root_agent.dependencies.banco_agil_adapter.buscar_cliente", return_value=CLIENTE)
    return mocker.patch("root_agent.dependencies.banco_agil_adapter.autenticar", return_value=CLIENTE)


@pytest.mark.e2e
async def test_mixed_query_apos_autenticacao(nova_conversa, mock_banco_agil_cliente):
    """
    Uma mensagem que mistura limite de crédito com receita de bolo não é tratada como ataque
    (a sessão continua autenticada) e a parte bancária é atendida com dados reais: a triagem
    transfere para agente_credito, que consulta o limite pela tool.

    O roteamento é decisão da LLM: se divergir, a conversa inteira é repetida uma vez
    (com_retentativa, com aviso). O valor devolvido pela tool vem do mock e é determinístico:
    se divergir, pytest.fail falha na hora, sem nova tentativa.
    """
    async def cenario():
        conversa = await nova_conversa("556299999999")
        await autenticar_por_numeros(conversa, "123.456.789-01", "15/03/1985", "Carlos Silva")

        mista = await conversa.enviar("Legal! Agora quero saber meu limite e também como fazer um bolo")

        assert (await conversa.estado()).get("is_authenticated") is True, (
            f"a pergunta mista encerrou o atendimento (classificada como ataque?): {mista.texto[:200]!r}"
        )
        assert "agente_credito" in mista.transferencias, (
            f"parte de crédito não roteada: transferências={mista.transferencias} texto={mista.texto[:200]!r}"
        )
        assert "consultar_limite_credito" in mista.tools_chamadas, (
            f"limite não consultado: tools={mista.tools_chamadas} texto={mista.texto[:200]!r}"
        )
        for resposta in mista.respostas_tool("consultar_limite_credito"):
            if not (isinstance(resposta, dict) and resposta.get("limite_credito") == 5000.0):
                pytest.fail(f"consultar_limite_credito devolveu {resposta!r}, esperado limite 5000.0 do mock")

    await com_retentativa(cenario)
