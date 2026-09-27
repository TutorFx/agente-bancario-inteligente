import json
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.domain.guardrails import validar_moeda, MOEDAS_SUPORTADAS

def get_cambio_tool(adapter: BancoAgilAdapter):
    async def consultar_cotacao(moeda_destino: str) -> str:
        """
        Busca cotação em tempo real via API externa (BRL → moeda_destino).
        Valida se moeda está na lista suportada antes de chamar API.
        """
        if not validar_moeda(moeda_destino):
            return json.dumps({"erro": "moeda_nao_suportada",
                               "suportadas": list(MOEDAS_SUPORTADAS)})
        cotacao = await adapter.get_cotacao(moeda_destino)
        return json.dumps(cotacao.model_dump())
    return consultar_cotacao
