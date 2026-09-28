"""
Testes de integração: tools de crédito + BancoAgilAdapter reais sobre CSVs temporários.

Nada é mockado além dos caminhos dos arquivos, que apontam para `tmp_path`
para não tocar em `data/`. Leitura, decisão de domínio, FileLock, escrita
atômica e trilha de auditoria rodam de ponta a ponta.
"""

import csv
import json
import re
from types import SimpleNamespace

import pytest

from root_agent.infrastructure.adapters import banco_agil_adapter as adapter_module
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter
from root_agent.application.tools.credito_tool import get_credito_tools

CPF = "98765432100"

CLIENTES = [
    {"cpf": CPF, "nome": "Maria Santos", "data_nascimento": "22/07/1990",
     "score_credito": "580", "limite_credito": "2500.00", "conta": "0002"},
    {"cpf": "12345678900", "nome": "João Silva", "data_nascimento": "15/03/1985",
     "score_credito": "824", "limite_credito": "50000.00", "conta": "0001"},
]

SCORE_LIMITE = [
    {"score_min": "0", "score_max": "299", "limite_maximo": "0.00"},
    {"score_min": "300", "score_max": "499", "limite_maximo": "1500.00"},
    {"score_min": "500", "score_max": "699", "limite_maximo": "4000.00"},
    {"score_min": "700", "score_max": "849", "limite_maximo": "10000.00"},
    {"score_min": "850", "score_max": "1000", "limite_maximo": "25000.00"},
]


def _escrever_csv(path, linhas):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=linhas[0].keys())
        writer.writeheader()
        writer.writerows(linhas)


def _ler_csv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _cliente(path, cpf=CPF):
    return next(row for row in _ler_csv(path) if row["cpf"] == cpf)


def _ctx(autenticado=True):
    return SimpleNamespace(state={
        "is_authenticated": autenticado,
        "cliente_autenticado": {"cpf": CPF, "nome": "Maria Santos", "conta": "0002"},
    })


@pytest.fixture
def arquivos(tmp_path, monkeypatch):
    clientes = tmp_path / "clientes.csv"
    score_limite = tmp_path / "score_limite.csv"
    solicitacoes = tmp_path / "solicitacoes_aumento_limite.csv"
    _escrever_csv(clientes, CLIENTES)
    _escrever_csv(score_limite, SCORE_LIMITE)

    monkeypatch.setattr(adapter_module, "CSV_PATH", str(clientes))
    monkeypatch.setattr(adapter_module, "SCORE_LIMITE_PATH", str(score_limite))
    monkeypatch.setattr(adapter_module, "SOLICITACOES_LIMITE_PATH", str(solicitacoes))
    return SimpleNamespace(clientes=clientes, solicitacoes=solicitacoes, tmp=tmp_path)


@pytest.fixture
def tools(arquivos):
    adapter = BancoAgilAdapter(
        clientes_lock_path=str(arquivos.tmp / ".clientes.lock"),
        solicitacoes_lock_path=str(arquivos.tmp / ".solicitacoes.lock"),
    )
    consultar, solicitar, calcular = get_credito_tools(adapter)
    return SimpleNamespace(consultar=consultar, solicitar=solicitar, calcular=calcular)


def test_consultar_limite_le_csv_sem_expor_credenciais(tools):
    resp = json.loads(tools.consultar(tool_context=_ctx()))

    assert resp == {"nome": "Maria Santos", "conta": "0002", "score_credito": 580, "limite_credito": 2500.0}


def test_aumento_aprovado_persiste_limite_e_audita(tools, arquivos):
    resp = json.loads(tools.solicitar(3000.0, tool_context=_ctx()))

    assert resp["aprovado"] is True
    assert resp["limite_max_score"] == 4000.0
    assert _cliente(arquivos.clientes)["limite_credito"] == "3000.00"
    # Os demais clientes permanecem intactos após a reescrita atômica
    assert _cliente(arquivos.clientes, "12345678900") == CLIENTES[1]

    auditoria = _ler_csv(arquivos.solicitacoes)
    assert len(auditoria) == 1
    assert auditoria[0]["cpf_cliente"] == CPF
    assert auditoria[0]["limite_atual"] == "2500.00"
    assert auditoria[0]["novo_limite_solicitado"] == "3000.00"
    assert auditoria[0]["status_pedido"] == "aprovado"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", auditoria[0]["data_hora_solicitacao"])


def test_aumento_acima_da_matriz_rejeita_sem_alterar_limite(tools, arquivos):
    resp = json.loads(tools.solicitar(50000.0, tool_context=_ctx()))

    assert resp["aprovado"] is False
    assert _cliente(arquivos.clientes)["limite_credito"] == "2500.00"
    assert [row["status_pedido"] for row in _ler_csv(arquivos.solicitacoes)] == ["rejeitado"]


def test_auditoria_append_only_acumula_solicitacoes(tools, arquivos):
    tools.solicitar(3000.0, tool_context=_ctx())
    tools.solicitar(50000.0, tool_context=_ctx())

    auditoria = _ler_csv(arquivos.solicitacoes)
    assert [row["status_pedido"] for row in auditoria] == ["aprovado", "rejeitado"]
    assert auditoria[1]["limite_atual"] == "3000.00"


def test_calcular_score_persiste_resultado_no_csv(tools, arquivos):
    ctx = _ctx()
    resp = json.loads(tools.calcular(
        renda_mensal=8000.0,
        tipo_emprego="formal",
        despesas_mensais=2000.0,
        num_dependentes=1,
        tem_dividas="nao",
        tool_context=ctx,
    ))

    assert resp["persistido"] is True
    assert 0 <= resp["novo_score"] <= 1000
    assert _cliente(arquivos.clientes)["score_credito"] == str(resp["novo_score"])
    assert ctx.state["entrevista_realizada_na_sessao"] is True


def test_sem_autenticacao_nao_le_nem_grava(tools, arquivos):
    antes = arquivos.clientes.read_bytes()

    resp = json.loads(tools.solicitar(3000.0, tool_context=_ctx(autenticado=False)))

    assert resp["erro"] == "nao_autenticado"
    assert arquivos.clientes.read_bytes() == antes
    assert not arquivos.solicitacoes.exists()
