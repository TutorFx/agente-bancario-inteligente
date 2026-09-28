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
        timestamp="",
        erro="falha_servico_externo"
    ))
    tool = get_cambio_tool(mock_adapter)

    res_str = await tool("EUR")
    data = json.loads(res_str)

    assert data["erro"] == "servico_temporariamente_indisponivel"
    assert "instabilidade" in data["mensagem"]

@pytest.mark.asyncio
async def test_consultar_cotacao_moeda_indisponivel_no_provedor():
    """Requisição bem-sucedida, mas o provedor não retornou taxa para a moeda:
    não deve ser confundido com falha geral de serviço."""
    mock_adapter = MagicMock(spec=BancoAgilAdapter)
    mock_adapter.get_cotacao = AsyncMock(return_value=CotacaoDTO(
        moeda_origem="BRL",
        moeda_destino="CHF",
        taxa=0.0,
        timestamp="Tue, 22 Sep 2026 12:00:00 +0000",
        erro="moeda_indisponivel_no_provedor"
    ))
    tool = get_cambio_tool(mock_adapter)

    res_str = await tool("CHF")
    data = json.loads(res_str)

    assert data["erro"] == "moeda_indisponivel_no_provedor"
    assert "CHF" in data["mensagem"]

@pytest.mark.asyncio
async def test_consultar_cotacao_taxa_zero_sem_erro_explicito_e_tratada_como_indisponivel():
    """Defesa em profundidade: mesmo sem `erro` setado, taxa<=0 nunca deve ser
    repassada ao cliente como se fosse uma cotação válida."""
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
