import json
from unittest.mock import MagicMock
from root_agent.application.tools.autenticacao_tool import get_autenticacao_tool
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.domain.models import ClienteDTO

def test_autenticar_cliente_sucesso():
    mock_adapter = MagicMock(spec=BancoAgilAdapter)
    mock_adapter.autenticar.return_value = ClienteDTO(
        cpf="12345678900",
        nome="Cliente Teste",
        data_nascimento="10/10/1990",
        score_credito=600,
        limite_credito=2000.0,
        conta="1234"
    )
    tool = get_autenticacao_tool(mock_adapter)
    res_str = tool("12345678900", "10/10/1990")
    data = json.loads(res_str)

    assert data["autenticado"] is True
    assert data["cliente"]["nome"] == "Cliente Teste"

def test_autenticar_cliente_invalido():
    mock_adapter = MagicMock(spec=BancoAgilAdapter)
    mock_adapter.autenticar.return_value = None
    tool = get_autenticacao_tool(mock_adapter)
    res_str = tool("00000000000", "01/01/1980")
    data = json.loads(res_str)

    assert data["autenticado"] is False
    assert data["erro"] == "credenciais_invalidas"
