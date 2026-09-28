import json
from google.adk.tools.tool_context import ToolContext
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.domain.guardrails import calcular_score_detalhado
from root_agent.application.middlewares.auth_guard import (
    cpf_do_cliente_autenticado,
    ERRO_NAO_AUTENTICADO,
)


def get_credito_tools(adapter: BancoAgilAdapter):
    def consultar_limite_credito(tool_context: ToolContext | None = None) -> str:
        """Retorna nome, conta, limite e score atual do cliente autenticado na sessão."""
        cpf = cpf_do_cliente_autenticado(tool_context)
        if not cpf or tool_context is None:
            return json.dumps(ERRO_NAO_AUTENTICADO)
        cliente = adapter.buscar_cliente(cpf)
        if not cliente:
            return json.dumps({"erro": "cliente_nao_encontrado"})
        # Minimização de PII: CPF e data de nascimento não são devolvidos à LLM
        return json.dumps(cliente.model_dump(include={"nome", "conta", "score_credito", "limite_credito"}))

    def solicitar_aumento_limite(novo_limite: float, tool_context: ToolContext | None = None) -> str:
        """
        Processa a solicitação de aumento de limite do cliente autenticado na sessão,
        validando o valor pela tabela de faixas de score e registrando a solicitação.

        Parâmetros:
            novo_limite: Novo limite de crédito desejado, em R$.
        """
        cpf = cpf_do_cliente_autenticado(tool_context)
        if not cpf or tool_context is None:
            return json.dumps(ERRO_NAO_AUTENTICADO)
        cliente = adapter.buscar_cliente(cpf)
        if not cliente:
            return json.dumps({"erro": "cliente_nao_encontrado"})

        entrevista_feita = bool(tool_context.state.get("entrevista_realizada_na_sessao", False))

        resultado = adapter.solicitar_aumento_limite(cpf, novo_limite)
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

    def calcular_e_atualizar_score(
        renda_mensal: float,
        tipo_emprego: str,
        despesas_mensais: float,
        num_dependentes: int,
        tem_dividas: str,
        tool_context: ToolContext | None = None,
    ) -> str:
        """
        Calcula o novo score de crédito do cliente autenticado com base nos dados
        coletados na entrevista, usando a fórmula ponderada por categoria
        (cada uma com teto próprio), e persiste o resultado no banco de dados (clientes.csv).

        Parâmetros:
            renda_mensal: Renda mensal bruta em R$.
            tipo_emprego: Situação de emprego ('formal', 'autonomo' ou 'desempregado').
            despesas_mensais: Total de despesas fixas mensais em R$.
            num_dependentes: Número de dependentes financeiros (inteiro >= 0).
            tem_dividas: Indica se há dívidas ativas ('sim' ou 'nao').

        Retorna JSON com novo_score calculado, detalhamento das parcelas e status da persistência.
        """
        cpf = cpf_do_cliente_autenticado(tool_context)
        if not cpf or tool_context is None:
            return json.dumps(ERRO_NAO_AUTENTICADO)

        entrevista = {
            "renda_mensal": renda_mensal,
            "tipo_emprego": tipo_emprego,
            "despesas_mensais": despesas_mensais,
            "num_dependentes": num_dependentes,
            "tem_dividas": tem_dividas,
        }

        novo_score, detalhes = calcular_score_detalhado(entrevista)

        # --- Persistência ---
        sucesso = adapter.atualizar_score(cpf, novo_score)
        tool_context.state["entrevista_realizada_na_sessao"] = True

        return json.dumps({
            "novo_score": novo_score,
            "detalhes": detalhes,
            "persistido": sucesso,
            "entrevista_realizada_na_sessao": True,
            "erro": None if sucesso else "cliente_nao_encontrado",
        })

    return consultar_limite_credito, solicitar_aumento_limite, calcular_e_atualizar_score
