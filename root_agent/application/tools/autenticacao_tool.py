import json
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter

def get_autenticacao_tool(adapter: BancoAgilAdapter):
    def autenticar_cliente(cpf: str, data_nascimento: str) -> str:
        """
        Valida CPF + data de nascimento contra clientes.csv.
        Retorna JSON com {autenticado, cliente?, erro?}.
        Chamada pelo Agente de Triagem após middleware coletar os dados.
        """
        cliente = adapter.autenticar(cpf, data_nascimento)
        if not cliente:
            return json.dumps({"autenticado": False, "erro": "credenciais_invalidas"})
        return json.dumps({"autenticado": True, "cliente": cliente.model_dump()})
    return autenticar_cliente
