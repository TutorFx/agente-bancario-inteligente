import json
from google.adk.tools.tool_context import ToolContext
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.domain.guardrails import (
    validar_aumento_limite,
    limpar_cpf,
    calcular_score_detalhado,
)

def _resolver_cpf(cpf: str | None, tool_context: ToolContext | None = None) -> str:
    if cpf and str(cpf).strip():
        return str(cpf).strip()
    if tool_context and hasattr(tool_context, "state"):
        cpf_state = tool_context.state.get("auth_cpf_temp")
        if cpf_state:
            return str(cpf_state)
        cliente_state = tool_context.state.get("cliente_autenticado")
        if cliente_state:
            if isinstance(cliente_state, dict):
                return str(cliente_state.get("cpf", ""))
            elif isinstance(cliente_state, str):
                try:
                    data = json.loads(cliente_state)
                    return str(data.get("cpf", ""))
                except (json.JSONDecodeError, TypeError):
                    pass
    return str(cpf or "")

def get_credito_tools(adapter: BancoAgilAdapter):
    def consultar_limite_credito(cpf: str = "", tool_context: ToolContext = None) -> str:
        """Retorna limite e score atual do cliente."""
        cpf_resolvido = _resolver_cpf(cpf, tool_context)
        cliente = adapter.buscar_cliente(cpf_resolvido)
        if not cliente:
            return json.dumps({"erro": "cliente_nao_encontrado"})
        return json.dumps(cliente.model_dump())

    def solicitar_aumento_limite(cpf: str, novo_limite: float, tool_context: ToolContext = None) -> str:
        """
        Processa a solicitação de aumento de limite consultando a política
        dinâmica de crédito e persistindo log de auditoria.
        """
        cpf_resolvido = _resolver_cpf(cpf, tool_context)
        cliente = adapter.buscar_cliente(cpf_resolvido)
        if not cliente:
            return json.dumps({"erro": "cliente_nao_encontrado"})

        entrevista_feita = False
        if tool_context and hasattr(tool_context, "state"):
            entrevista_feita = bool(tool_context.state.get("entrevista_realizada_na_sessao", False))

        resultado = adapter.solicitar_aumento_limite(cpf_resolvido, novo_limite)
        res_data = resultado.model_dump()
        limite_max_score = (
            resultado.limite_maximo_permitido
            if resultado.limite_maximo_permitido is not None
            else adapter.obter_limite_maximo_por_score(cliente.score_credito)
        )
        res_data["limite_max_score"] = limite_max_score
        res_data["score_atual"] = cliente.score_credito
        res_data["entrevista_realizada_na_sessao"] = entrevista_feita
        return json.dumps(res_data)

    def atualizar_score_credito(cpf: str, novo_score: int, tool_context: ToolContext = None) -> str:
        """Persiste novo score após entrevista."""
        cpf_resolvido = _resolver_cpf(cpf, tool_context)
        sucesso = adapter.atualizar_score(cpf_resolvido, novo_score)
        if sucesso:
            return json.dumps({"sucesso": True, "novo_score": novo_score})
        return json.dumps({"sucesso": False, "erro": "cliente_nao_encontrado"})

    def calcular_e_atualizar_score(
        cpf: str,
        renda_mensal: float,
        tipo_emprego: str,
        despesas_mensais: float,
        num_dependentes: int,
        tem_dividas: str,
        tool_context: ToolContext = None,
    ) -> str:
        """
        Calcula o novo score de crédito com base nos dados coletados na entrevista
        utilizando a fórmula calibrada de risco por categoria com tetos estritos,
        e persiste o resultado no banco de dados (clientes.csv).

        Parâmetros:
            cpf: CPF do cliente autenticado.
            renda_mensal: Renda mensal bruta em R$.
            tipo_emprego: Situação de emprego ('formal', 'autonomo' ou 'desempregado').
            despesas_mensais: Total de despesas fixas mensais em R$.
            num_dependentes: Número de dependentes financeiros (inteiro >= 0).
            tem_dividas: Indica se há dívidas ativas ('sim' ou 'nao').

        Retorna JSON com novo_score calculado, detalhamento das parcelas e status da persistência.
        """
        entrevista = {
            "renda_mensal": renda_mensal,
            "tipo_emprego": tipo_emprego,
            "despesas_mensais": despesas_mensais,
            "num_dependentes": num_dependentes,
            "tem_dividas": tem_dividas,
        }

        novo_score, detalhes = calcular_score_detalhado(entrevista)

        # --- Persistência ---
        cpf_resolvido = _resolver_cpf(cpf, tool_context)
        sucesso = adapter.atualizar_score(cpf_resolvido, novo_score)

        if tool_context and hasattr(tool_context, "state"):
            tool_context.state["entrevista_realizada_na_sessao"] = True

        return json.dumps({
            "novo_score": novo_score,
            "detalhes": detalhes,
            "persistido": sucesso,
            "entrevista_realizada_na_sessao": True,
            "erro": None if sucesso else "cliente_nao_encontrado",
        })

    return consultar_limite_credito, solicitar_aumento_limite, atualizar_score_credito, calcular_e_atualizar_score
