"""Testes unitários para as ferramentas de crédito (credito_tool.py)."""

import json
import pytest
from unittest.mock import MagicMock
from root_agent.domain.models import ClienteDTO, SolicitacaoLimiteDTO
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.application.tools.credito_tool import get_credito_tools


def _ctx(autenticado: bool = True, cpf: str = "12345678900") -> MagicMock:
    ctx = MagicMock()
    ctx.state = {
        "is_authenticated": autenticado,
        "cliente_autenticado": {"cpf": cpf, "nome": "Teste Cliente", "conta": "0001"} if autenticado else None,
    }
    return ctx


@pytest.fixture
def mock_adapter():
    adapter = MagicMock(spec=BancoAgilAdapter)
    return adapter

@pytest.fixture
def tools(mock_adapter):
    return get_credito_tools(mock_adapter)

@pytest.fixture
def cliente():
    return ClienteDTO(
        cpf="12345678900",
        nome="Teste Cliente",
        data_nascimento="01/01/1990",
        score_credito=800,
        limite_credito=5000.0,
        conta="0001"
    )

def test_consultar_limite_credito_sucesso(tools, mock_adapter, cliente):
    consultar_limite, _, _ = tools
    mock_adapter.buscar_cliente.return_value = cliente

    resp = json.loads(consultar_limite(tool_context=_ctx()))

    mock_adapter.buscar_cliente.assert_called_once_with("12345678900")
    assert resp["score_credito"] == 800
    assert resp["limite_credito"] == 5000.0
    # Minimização de PII: credenciais não voltam para a LLM
    assert "data_nascimento" not in resp
    assert "cpf" not in resp

def test_consultar_limite_credito_nao_encontrado(tools, mock_adapter):
    consultar_limite, _, _ = tools
    mock_adapter.buscar_cliente.return_value = None

    resp = json.loads(consultar_limite(tool_context=_ctx(cpf="00000000000")))
    assert resp["erro"] == "cliente_nao_encontrado"

def test_solicitar_aumento_limite_aprovado(tools, mock_adapter, cliente):
    _, solicitar_aumento, _ = tools
    mock_adapter.buscar_cliente.return_value = cliente
    mock_adapter.solicitar_aumento_limite.return_value = SolicitacaoLimiteDTO(
        aprovado=True,
        motivo="Aprovado de acordo com a política de crédito.",
        limite_anterior=5000.0,
        limite_novo=8000.0,
        limite_maximo_permitido=10000.0
    )

    resp = json.loads(solicitar_aumento(8000.0, tool_context=_ctx()))
    mock_adapter.solicitar_aumento_limite.assert_called_once_with("12345678900", 8000.0)
    assert resp["aprovado"] is True
    assert resp["limite_novo"] == 8000.0
    assert resp["limite_max_score"] == 10000.0
    assert resp["score_atual"] == 800

def test_solicitar_aumento_limite_rejeitado(tools, mock_adapter):
    _, solicitar_aumento, _ = tools
    mock_adapter.buscar_cliente.return_value = ClienteDTO(
        cpf="12345678900",
        nome="Teste Cliente",
        data_nascimento="01/01/1990",
        score_credito=600,
        limite_credito=3000.0,
        conta="0001"
    )
    mock_adapter.solicitar_aumento_limite.return_value = SolicitacaoLimiteDTO(
        aprovado=False,
        motivo="Score insuficiente para o valor solicitado.",
        limite_anterior=3000.0,
        limite_novo=None,
        limite_maximo_permitido=4000.0
    )

    resp = json.loads(solicitar_aumento(6000.0, tool_context=_ctx()))
    assert resp["aprovado"] is False
    assert resp["limite_novo"] is None
    assert resp["limite_max_score"] == 4000.0
    assert resp["score_atual"] == 600

def test_calcular_e_atualizar_score(tools, mock_adapter):
    _, _, calcular_score = tools
    mock_adapter.atualizar_score.return_value = True
    ctx = _ctx()

    resp = json.loads(calcular_score(
        renda_mensal=5000.0,
        tipo_emprego="formal",
        despesas_mensais=2000.0,
        num_dependentes=0,
        tem_dividas="nao",
        tool_context=ctx,
    ))
    mock_adapter.atualizar_score.assert_called_once_with("12345678900", 742)
    assert ctx.state["entrevista_realizada_na_sessao"] is True
    assert resp["persistido"] is True
    assert resp["novo_score"] == 742
    assert resp["entrevista_realizada_na_sessao"] is True
    assert resp["detalhes"]["parcela_renda"] == 122
    assert resp["detalhes"]["parcela_emprego"] == 200
    assert resp["detalhes"]["parcela_comprometimento"] == 120
    assert resp["detalhes"]["parcela_dependentes"] == 150
    assert resp["detalhes"]["parcela_dividas"] == 150

def test_calcular_e_atualizar_score_alta_renda_com_dividas_e_desemprego(tools, mock_adapter):
    """
    Alta renda com despesas baixas não deve levar a pontuação a 1000
    se o cliente estiver desempregado e possuir dívidas ativas.
    """
    _, _, calcular_score = tools
    mock_adapter.atualizar_score.return_value = True

    resp = json.loads(calcular_score(
        renda_mensal=15000.0,
        tipo_emprego="desempregado",
        despesas_mensais=100.0,
        num_dependentes=3,
        tem_dividas="sim",
        tool_context=_ctx(),
    ))
    assert resp["persistido"] is True
    # Renda: 212, Emprego: 0, Comprometimento: 198, Dependentes: 50, Dívidas: 0 -> Total: 460
    assert resp["novo_score"] == 460
    assert resp["novo_score"] < 1000
    assert resp["detalhes"]["parcela_emprego"] == 0
    assert resp["detalhes"]["parcela_dividas"] == 0


class TestControleDeAcesso:
    """As tools nunca aceitam identidade vinda da LLM e exigem sessão autenticada."""

    def test_tools_nao_expoem_parametro_cpf_para_a_llm(self, tools):
        import inspect
        for tool in tools:
            assert "cpf" not in inspect.signature(tool).parameters

    def test_consultar_limite_sem_autenticacao_e_negado(self, tools, mock_adapter):
        consultar_limite, _, _ = tools
        resp = json.loads(consultar_limite(tool_context=_ctx(autenticado=False)))
        assert resp["erro"] == "nao_autenticado"
        mock_adapter.buscar_cliente.assert_not_called()

    def test_solicitar_aumento_sem_autenticacao_e_negado(self, tools, mock_adapter):
        _, solicitar_aumento, _ = tools
        resp = json.loads(solicitar_aumento(9000.0, tool_context=_ctx(autenticado=False)))
        assert resp["erro"] == "nao_autenticado"
        mock_adapter.solicitar_aumento_limite.assert_not_called()

    def test_score_sem_autenticacao_nao_persiste(self, tools, mock_adapter):
        _, _, calcular_score = tools
        resp = json.loads(calcular_score(
            renda_mensal=30000.0, tipo_emprego="formal", despesas_mensais=0.0,
            num_dependentes=0, tem_dividas="nao", tool_context=_ctx(autenticado=False),
        ))
        assert resp["erro"] == "nao_autenticado"
        mock_adapter.atualizar_score.assert_not_called()

    def test_flag_autenticado_sem_cliente_na_sessao_e_negado(self, tools, mock_adapter):
        consultar_limite, _, _ = tools
        ctx = MagicMock()
        ctx.state = {"is_authenticated": True, "cliente_autenticado": None}
        resp = json.loads(consultar_limite(tool_context=ctx))
        assert resp["erro"] == "nao_autenticado"
