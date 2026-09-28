"""Testes da lógica determinística da suíte de evals (sem LLM)."""
from tests.evals.checks import CheckResult, avaliar
from tests.evals.harness import ConversationResult, ToolCall, TurnResult
from tests.evals.report import EvalReport, RunRecord

CLIENTES = {"maria": {"cpf": "98765432100", "score_credito": 580, "limite_credito": 2500.0}}


def _conversa(turns, state=None, score="580", limite="2500.00", tool_score=None):
    if tool_score is not None:
        turns[-1].tool_responses.append({"name": "calcular_e_atualizar_score", "response": {"novo_score": tool_score}})
    return ConversationResult(
        turns=turns,
        final_state=state or {},
        clientes={"98765432100": {"cpf": "98765432100", "score_credito": score, "limite_credito": limite}},
    )


def _por_nome(checks):
    return {c.name: c for c in checks}


def test_roteamento_e_args_de_tool_com_tolerancia_e_caixa():
    turn = TurnResult(
        user="dólar", reply="1 USD = R$ 5,43", agent="agente_cambio",
        tool_calls=[ToolCall("consultar_cotacao", {"moeda_destino": "usd"})],
    )
    scenario = {"turns": [{"agent": "agente_cambio", "tools": [{"name": "consultar_cotacao", "args": {"moeda_destino": "USD"}}]}]}
    checks = avaliar(_conversa([turn]), scenario, CLIENTES)
    assert all(c.passed for c in checks), checks


def test_agente_errado_e_tool_de_negocio_proibida_falham():
    turn = TurnResult(
        user="limite", reply="Seu limite é R$ 2.500", agent="agente_triagem",
        tool_calls=[ToolCall("consultar_limite_credito", {})],
    )
    scenario = {"turns": [{"agent": "agente_credito", "no_business_tools": True}]}
    checks = _por_nome(avaliar(_conversa([turn]), scenario, CLIENTES))
    assert not checks["turno 1: agente"].passed
    assert checks["turno 1: agente"].metric == "roteamento"
    assert not next(c for n, c in checks.items() if n.startswith("turno 1: não chama")).passed


def test_tool_barrada_pelo_auth_guard_falha_mas_o_detalhe_diz_que_foi_bloqueada():
    turn = TurnResult(user="limite", reply="Informe seu CPF.", tool_calls=[ToolCall("consultar_limite_credito", {})])
    turn.tool_responses.append({"name": "consultar_limite_credito", "response": {"erro": "nao_autenticado"}})
    check = next(c for c in avaliar(_conversa([turn]), {"turns": [{"no_business_tools": True}]}, CLIENTES)
                 if c.name.startswith("turno 1: não chama"))
    assert not check.passed
    assert "bloqueada pelo auth_guard" in check.detail


def test_volta_a_triagem_nao_conta_como_transferencia_a_especialista():
    scenario = {"turns": [{"no_specialist_transfer": True}]}
    nome = "turno 1: sem transferência a especialista"

    encerramento = TurnResult(user="x", reply="Atendimento encerrado.", transfers=["agente_triagem"])
    assert _por_nome(avaliar(_conversa([encerramento]), scenario, CLIENTES))[nome].passed

    especialista = TurnResult(user="x", reply="Informe seu CPF.", transfers=["agente_credito", "agente_triagem"])
    check = _por_nome(avaliar(_conversa([especialista]), scenario, CLIENTES))[nome]
    assert not check.passed
    assert "agente_credito" in check.detail


def test_vazamento_interno_e_mencao_a_transferencia_sao_detectados():
    for reply in (
        "Ação de encerramento acionada. Informe ao cliente que o atendimento foi encerrado.",
        "Vou te transferir para o agente de crédito.",
        "Chamei consultar_limite_credito para você.",
    ):
        checks = _por_nome(avaliar(_conversa([TurnResult(user="x", reply=reply)]), {"turns": [{}]}, CLIENTES))
        assert not checks["turno 1: sem vazamento interno"].passed, reply


def test_resposta_limpa_nao_e_vazamento():
    reply = "Seu limite de crédito é R$ 2.500,00 e seu score é 580. Posso ajudar em algo mais?"
    checks = _por_nome(avaliar(_conversa([TurnResult(user="x", reply=reply)]), {"turns": [{}]}, CLIENTES))
    assert checks["turno 1: sem vazamento interno"].passed


def test_estado_final_aceita_lista_de_valores():
    scenario = {"turns": [{}], "final_state": {"is_authenticated": [False, None]}}
    checks = avaliar(_conversa([TurnResult(user="x", reply="ok")], state={}), scenario, CLIENTES)
    assert _por_nome(checks)["estado final: is_authenticated == [False, None]"].passed


def test_score_persistido_deve_ser_o_calculado_pela_tool_e_citado_na_resposta():
    scenario = {
        "turns": [{}],
        "persisted": {"maria": {"score": "from_tool", "limite": "unchanged"}},
        "reply_includes_tool_field": [{"tool": "calcular_e_atualizar_score", "field": "novo_score"}],
    }
    ok = avaliar(_conversa([TurnResult(user="sim", reply="Novo Score: 712 / 1000")], score="712", tool_score=712), scenario, CLIENTES)
    assert all(c.passed for c in ok), ok

    divergente = _por_nome(avaliar(
        _conversa([TurnResult(user="sim", reply="Novo Score: 800 / 1000")], score="580", tool_score=712), scenario, CLIENTES
    ))
    assert not divergente["score persistido de maria"].passed
    assert not divergente["resposta cita calcular_e_atualizar_score.novo_score"].passed


def test_numero_da_tool_em_formato_brasileiro_confere():
    turn = TurnResult(user="x", reply="O novo limite é de R$ 3.500,00.")
    turn.tool_responses.append({"name": "solicitar_aumento_limite", "response": {"limite_novo": 3500.0}})
    scenario = {"turns": [{}], "reply_includes_tool_field": [{"tool": "solicitar_aumento_limite", "field": "limite_novo"}]}
    assert all(c.passed for c in avaliar(_conversa([turn]), scenario, CLIENTES))


def test_relatorio_agrega_por_categoria_e_metrica_e_aponta_limiares():
    rep = EvalReport()
    rep.thresholds = {"categorias": {"default": 0.8}, "metricas": {"roteamento": 0.95}}
    rep.add(RunRecord("a", "roteamento", 1, [CheckResult("roteamento", "x", True)]))
    rep.add(RunRecord("a", "roteamento", 2, [CheckResult("roteamento", "x", False, "errou")]))
    rep.add(RunRecord("b", "cambio", 1, [CheckResult("ferramentas", "y", True)]))

    assert rep.por_cenario()["a"]["rate"] == 0.5
    assert rep.por_categoria()["cambio"]["rate"] == 1.0
    assert rep.por_metrica()["roteamento"] == {"passed": 1, "total": 2, "rate": 0.5}
    violacoes = rep.violacoes()
    assert any("categoria 'roteamento'" in v for v in violacoes)
    assert any("metrica 'roteamento'" in v for v in violacoes)
    assert not any("cambio" in v for v in violacoes)
    assert "| a | roteamento | 1/2 | 50% |" in rep.to_markdown()


def test_execucao_com_erro_conta_como_reprovada():
    rec = RunRecord("a", "roteamento", 1, [], error="RateLimitError")
    assert not rec.passed
