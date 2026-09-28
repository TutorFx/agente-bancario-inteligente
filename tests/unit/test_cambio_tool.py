import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from root_agent.application.tools.cambio_tool import get_cambio_tool
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.domain.models import CotacaoDTO

@pytest.mark.asyncio
async def test_consultar_cotacao_moeda_invalida():
    mock_adapter = MagicMock(spec=BancoAgilAdapter)
    tool = get_cambio_tool(mock_adapter)

    res_str = await tool("INVALID")
    data = json.loads(res_str)

    assert data["erro"] == "moeda_nao_suportada"
    assert "suportadas" in data

@pytest.mark.asyncio
async def test_consultar_cotacao_sucesso():
    mock_adapter = MagicMock(spec=BancoAgilAdapter)
    mock_adapter.get_cotacao = AsyncMock(return_value=CotacaoDTO(
        moeda_origem="BRL",
        moeda_destino="USD",
        taxa=5.50,
        timestamp="2026-09-28"
    ))
    tool = get_cambio_tool(mock_adapter)

    res_str = await tool("USD")
    data = json.loads(res_str)

    assert data["moeda_destino"] == "USD"
    assert data["taxa"] == 5.50

@pytest.mark.asyncio
async def test_consultar_cotacao_servico_indisponivel():
    mock_adapter = MagicMock(spec=BancoAgilAdapter)
    mock_adapter.get_cotacao = AsyncMock(return_value=CotacaoDTO(
        moeda_origem="BRL",
        moeda_destino="EUR",
        taxa=0.0,
        timestamp=""
    ))
    tool = get_cambio_tool(mock_adapter)

    res_str = await tool("EUR")
    data = json.loads(res_str)

    assert data["erro"] == "servico_temporariamente_indisponivel"
    assert "instabilidade" in data["mensagem"]
