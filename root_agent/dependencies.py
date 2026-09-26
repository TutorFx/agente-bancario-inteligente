from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.application.tools.autenticacao_tool import get_autenticacao_tool
from root_agent.application.tools.credito_tool import get_credito_tools
from root_agent.application.tools.cambio_tool import get_cambio_tool
from root_agent.application.tools.session_tool import get_encerrar_atendimento_tool

__all__ = [
    "autenticar_cliente",
    "consultar_limite",
    "solicitar_aumento_limite",
    "calcular_e_atualizar_score",
    "consultar_cotacao",
    "encerrar_atendimento",
    "get_banco_agil_adapter",
]

from functools import lru_cache

@lru_cache(maxsize=1)
def get_banco_agil_adapter():
    return BancoAgilAdapter()

autenticar_cliente = get_autenticacao_tool(get_banco_agil_adapter())
consultar_limite, solicitar_aumento_limite, _, calcular_e_atualizar_score = get_credito_tools(get_banco_agil_adapter())
consultar_cotacao = get_cambio_tool(get_banco_agil_adapter())
encerrar_atendimento = get_encerrar_atendimento_tool()
