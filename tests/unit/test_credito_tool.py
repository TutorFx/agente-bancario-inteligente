"""Testes unitários para as ferramentas de crédito (credito_tool.py)."""

import json
import pytest
from unittest.mock import MagicMock
from root_agent.domain.models import ClienteDTO, SolicitacaoLimiteDTO
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.application.tools.credito_tool import get_credito_tools

@pytest.fixture
def mock_adapter():
    adapter = MagicMock(spec=BancoAgilAdapter)
    return adapter

@pytest.fixture
def tools(mock_adapter):
    return get_credito_tools(mock_adapter)

def test_consultar_limite_credito_sucesso(tools, mock_adapter):
    consultar_limite, _, _, _ = tools
    mock_adapter.buscar_cliente.return_value = ClienteDTO(
        cpf="12345678900",
        nome="Teste Cliente",
        data_nascimento="01/01/1990",
        score_credito=800,
        limite_credito=5000.0,
        conta="0001"
    )

    resp_str = consultar_limite("12345678900")
    resp = json.loads(resp_str)
    assert resp["cpf"] == "12345678900"
    assert resp["score_credito"] == 800
    assert resp["limite_credito"] == 5000.0

def test_consultar_limite_credito_nao_encontrado(tools, mock_adapter):
    consultar_limite, _, _, _ = tools
    mock_adapter.buscar_cliente.return_value = None

    resp_str = consultar_limite("00000000000")
    resp = json.loads(resp_str)
    assert resp["erro"] == "cliente_nao_encontrado"

def test_solicitar_aumento_limite_aprovado(tools, mock_adapter):
    _, solicitar_aumento, _, _ = tools
    mock_adapter.buscar_cliente.return_value = ClienteDTO(
        cpf="12345678900",
        nome="Teste Cliente",
        data_nascimento="01/01/1990",
        score_credito=800,
        limite_credito=5000.0,
        conta="0001"
    )
    mock_adapter.solicitar_aumento_limite.return_value = SolicitacaoLimiteDTO(
        aprovado=True,
        motivo="Aprovado de acordo com a política de crédito.",
        limite_anterior=5000.0,
        limite_novo=8000.0,
        limite_maximo_permitido=10000.0
    )

    resp_str = solicitar_aumento("12345678900", 8000.0)
    resp = json.loads(resp_str)
    assert resp["aprovado"] is True
    assert resp["limite_novo"] == 8000.0
    assert resp["limite_max_score"] == 10000.0
    assert resp["score_atual"] == 800

def test_solicitar_aumento_limite_rejeitado(tools, mock_adapter):
    _, solicitar_aumento, _, _ = tools
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

    resp_str = solicitar_aumento("12345678900", 6000.0)
    resp = json.loads(resp_str)
    assert resp["aprovado"] is False
    assert resp["limite_novo"] is None
    assert resp["limite_max_score"] == 4000.0
    assert resp["score_atual"] == 600

def test_calcular_e_atualizar_score(tools, mock_adapter):
    _, _, _, calcular_score = tools
    mock_adapter.atualizar_score.return_value = True

    resp_str = calcular_score(
        cpf="12345678900",
        renda_mensal=5000.0,
        tipo_emprego="formal",
        despesas_mensais=2000.0,
        num_dependentes=0,
        tem_dividas="nao"
    )
    resp = json.loads(resp_str)
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
    Valida a robustez matemática: alta renda com despesas baixas não deve estourar
    a pontuação para 1000 se o cliente estiver desempregado e possuir dívidas ativas.
    """
    _, _, _, calcular_score = tools
    mock_adapter.atualizar_score.return_value = True

    resp_str = calcular_score(
        cpf="12345678900",
        renda_mensal=15000.0,
        tipo_emprego="desempregado",
        despesas_mensais=100.0,
        num_dependentes=3,
        tem_dividas="sim"
    )
    resp = json.loads(resp_str)
    assert resp["persistido"] is True
    # Renda: 212, Emprego: 0, Comprometimento: 198, Dependentes: 50, Dívidas: 0 -> Total: 460
    assert resp["novo_score"] == 460
    assert resp["novo_score"] < 1000
    assert resp["detalhes"]["parcela_emprego"] == 0
    assert resp["detalhes"]["parcela_dividas"] == 0

