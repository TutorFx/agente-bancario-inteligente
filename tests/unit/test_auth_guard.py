"""Testes do guard determinístico de autenticação (before_tool_callback)."""

from unittest.mock import MagicMock

import pytest

from root_agent.application.middlewares.auth_guard import (
    before_tool_callback,
    cpf_do_cliente_autenticado,
)


def _tool(nome: str) -> MagicMock:
    tool = MagicMock()
    tool.name = nome
    return tool


def _ctx(state: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state
    return ctx


SESSAO_AUTENTICADA = {
    "is_authenticated": True,
    "cliente_autenticado": {"cpf": "12345678900", "nome": "João Silva", "conta": "0001"},
}


@pytest.mark.parametrize("tool_name", ["consultar_limite_credito", "solicitar_aumento_limite", "calcular_e_atualizar_score", "consultar_cotacao"])
def test_tools_de_negocio_bloqueadas_sem_autenticacao(tool_name):
    res = before_tool_callback(tool=_tool(tool_name), args={}, tool_context=_ctx({}))
    assert res is not None
    assert res["erro"] == "nao_autenticado"


def test_tools_publicas_liberadas_sem_autenticacao():
    assert before_tool_callback(tool=_tool("encerrar_atendimento"), args={}, tool_context=_ctx({})) is None


@pytest.mark.parametrize("destino", ["agente_triagem", "agente_fora_escopo"])
def test_transferencia_para_agente_publico_liberada_sem_autenticacao(destino):
    res = before_tool_callback(
        tool=_tool("transfer_to_agent"), args={"agent_name": destino}, tool_context=_ctx({})
    )
    assert res is None


@pytest.mark.parametrize("destino", ["agente_credito", "agente_entrevista_credito", "agente_cambio", None])
def test_transferencia_para_especialista_bloqueada_sem_autenticacao(destino):
    res = before_tool_callback(
        tool=_tool("transfer_to_agent"), args={"agent_name": destino}, tool_context=_ctx({})
    )
    assert res is not None
    assert res["erro"] == "nao_autenticado"


def test_transferencia_para_especialista_liberada_com_autenticacao():
    res = before_tool_callback(
        tool=_tool("transfer_to_agent"),
        args={"agent_name": "agente_credito"},
        tool_context=_ctx(dict(SESSAO_AUTENTICADA)),
    )
    assert res is None


def test_triagem_usa_o_guard_de_autenticacao():
    from root_agent.agent import root_agent

    assert root_agent.before_tool_callback is before_tool_callback


def test_tool_de_negocio_liberada_com_autenticacao():
    res = before_tool_callback(
        tool=_tool("consultar_limite_credito"), args={}, tool_context=_ctx(dict(SESSAO_AUTENTICADA))
    )
    assert res is None


def test_cpf_ignora_argumentos_e_usa_apenas_a_sessao():
    # Mesmo que a LLM tente passar outro CPF, a identidade vem do estado da sessão
    ctx = _ctx(dict(SESSAO_AUTENTICADA))
    assert cpf_do_cliente_autenticado(ctx) == "12345678900"


@pytest.mark.parametrize("state", [
    {},
    {"is_authenticated": False, "cliente_autenticado": {"cpf": "12345678900"}},
    {"is_authenticated": "true", "cliente_autenticado": {"cpf": "12345678900"}},
    {"is_authenticated": True, "cliente_autenticado": None},
    {"is_authenticated": True, "cliente_autenticado": "texto sem json"},
    {"is_authenticated": True, "cliente_autenticado": {"nome": "Sem CPF"}},
])
def test_cpf_none_quando_sessao_nao_autenticada_ou_inconsistente(state):
    assert cpf_do_cliente_autenticado(_ctx(state)) is None


def test_cpf_aceita_formato_legado_em_json_string():
    ctx = _ctx({
        "is_authenticated": True,
        "cliente_autenticado": '{"autenticado": true, "cliente": {"cpf": "98765432100"}}',
    })
    assert cpf_do_cliente_autenticado(ctx) == "98765432100"
