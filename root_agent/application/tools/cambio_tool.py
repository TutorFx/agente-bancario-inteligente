import json
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.domain.guardrails import validar_moeda, MOEDAS_SUPORTADAS

def get_cambio_tool(adapter: BancoAgilAdapter):
    async def consultar_cotacao(moeda_destino: str) -> str:
        """
        Busca cotação de referência via API externa (BRL → moeda_destino).
        O provedor atualiza a taxa uma vez por dia; não é cotação em tempo real.
        Valida se moeda está na lista suportada antes de chamar API.
        """
        if not validar_moeda(moeda_destino):
            return json.dumps({"erro": "moeda_nao_suportada",
                               "suportadas": list(MOEDAS_SUPORTADAS)})
        cotacao = await adapter.get_cotacao(moeda_destino)
        if cotacao.erro == "moeda_indisponivel_no_provedor":
            return json.dumps({
                "erro": "moeda_indisponivel_no_provedor",
                "mensagem": f"No momento o provedor de câmbio não disponibiliza cotação para {moeda_destino.upper()}. Por favor, tente novamente mais tarde ou consulte outra moeda."
            })
        if cotacao.erro or cotacao.taxa <= 0.0:
            return json.dumps({
                "erro": "servico_temporariamente_indisponivel",
                "mensagem": "Não foi possível obter a cotação no momento devido a instabilidade no serviço externo. Por favor, tente novamente em alguns instantes."
            })
        return json.dumps(cotacao.model_dump())
    return consultar_cotacao
