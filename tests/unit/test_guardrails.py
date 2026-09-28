"""Testes unitários para as regras de negócio e guardrails (guardrails.py)."""

import pytest
from root_agent.domain.guardrails import (
    limpar_cpf,
    validar_formato_cpf,
    validar_formato_data,
    extrair_data,
    validar_moeda,
    validar_aumento_limite,
    calcular_score,
    calcular_score_detalhado,
    TETO_SCORE_DESEMPREGADO,
)

def test_limpar_cpf():
    assert limpar_cpf("123.456.789-00") == "12345678900"
    assert limpar_cpf("12345678900") == "12345678900"
    assert limpar_cpf("abc123def") == "123"

def test_validar_formato_cpf():
    assert validar_formato_cpf("123.456.789-00") is True
    assert validar_formato_cpf("12345678900") is True
    assert validar_formato_cpf("123.456.789-0") is False
    assert validar_formato_cpf("123456789012") is False
    assert validar_formato_cpf("111.111.111-11") is False
    assert validar_formato_cpf("00000000000") is False
    assert validar_formato_cpf("abcdefghijk") is False


def test_cpf_value_object():
    from root_agent.domain.value_objects import CPF

    cpf = CPF("12345678900")
    assert cpf.valor == "12345678900"
    assert cpf.possui_tamanho_correto() is True
    assert cpf.possui_digitos_repetidos() is False
    assert cpf.formatado() == "123.456.789-00"
    assert cpf.mascarado() == "***8900"
    assert repr(cpf) == "CPF('***8900')"
    assert str(cpf) == "123.456.789-00"
    assert cpf == CPF("12345678900")
    assert cpf == "12345678900"
    assert cpf != "outra_coisa"

    cpf_curto = CPF("123")
    assert cpf_curto.possui_tamanho_correto() is False
    assert cpf_curto.formatado() == "123"
    assert cpf_curto.mascarado() == "***"

    cpf_repetido = CPF("99999999999")
    assert cpf_repetido.possui_tamanho_correto() is True
    assert cpf_repetido.possui_digitos_repetidos() is True

def test_validar_formato_data():
    assert validar_formato_data("01/01/1990") is True
    assert validar_formato_data("31/12/2000") is True
    assert validar_formato_data("31/02/2020") is False  # data inexistente
    assert validar_formato_data("invalido") is False

def test_extrair_data():
    assert extrair_data("Nasci em 15/05/1985 em SP") == "15/05/1985"
    assert extrair_data("Data: 20-10-1999") == "20/10/1999"
    assert extrair_data("Nenhuma data aqui") is None

def test_validar_moeda():
    assert validar_moeda("USD") is True
    assert validar_moeda("eur") is True
    assert validar_moeda("BTC") is True
    assert validar_moeda("XYZ") is False

def test_validar_aumento_limite():
    # Menor ou igual ao atual
    ok, motivo = validar_aumento_limite(limite_atual=1000.0, novo_limite=1000.0)
    assert ok is False
    assert "maior que o limite atual" in motivo

    # Excede limite máximo
    ok, motivo = validar_aumento_limite(limite_atual=1000.0, novo_limite=5000.0, limite_maximo=4000.0)
    assert ok is False
    assert "excede o limite máximo permitido" in motivo

    # Aprovado
    ok, motivo = validar_aumento_limite(limite_atual=1000.0, novo_limite=3000.0, limite_maximo=4000.0)
    assert ok is True
    assert motivo == ""

def test_calcular_score_perfil_maximo():
    entrevista = {
        "renda_mensal": 30000.0,
        "tipo_emprego": "formal",
        "despesas_mensais": 0.0,
        "num_dependentes": 0,
        "tem_dividas": False,
    }
    score, detalhes = calcular_score_detalhado(entrevista)
    assert score == 1000
    assert detalhes["parcela_renda"] == 300
    assert detalhes["parcela_emprego"] == 200
    assert detalhes["parcela_comprometimento"] == 200
    assert detalhes["parcela_dependentes"] == 150
    assert detalhes["parcela_dividas"] == 150
    assert calcular_score(entrevista) == 1000

def test_calcular_score_autonomo_e_dependentes():
    entrevista = {
        "renda_mensal": 7500.0,
        "tipo_emprego": "autônomo",
        "despesas_mensais": 3750.0,
        "num_dependentes": 2,
        "tem_dividas": "nao",
    }
    score, detalhes = calcular_score_detalhado(entrevista)
    # Renda: int((7500/30000)^0.5 * 300) = int(0.5 * 300) = 150
    # Emprego: autônomo = 100
    # Comprometimento: 3750/7500 = 0.5 -> int((1 - 0.5) * 200) = 100
    # Dependentes: 2 -> 90
    # Dívidas: "nao" -> 150
    # Total: 150 + 100 + 100 + 90 + 150 = 590
    assert score == 590
    assert detalhes["parcela_renda"] == 150
    assert detalhes["parcela_emprego"] == 100
    assert detalhes["parcela_comprometimento"] == 100
    assert detalhes["parcela_dependentes"] == 90
    assert detalhes["parcela_dividas"] == 150
    assert calcular_score(entrevista) == 590

def test_calcular_score_desempregado_com_dividas():
    entrevista = {
        "renda_mensal": 1000.0,
        "tipo_emprego": "desempregado",
        "despesas_mensais": 2000.0,
        "num_dependentes": 4,
        "tem_dividas": "sim",
    }
    score, detalhes = calcular_score_detalhado(entrevista)
    # Renda: int((1000/30000)^0.5 * 300) = 54
    # Emprego: 0
    # Comprometimento: 2000/1000 = 2.0 -> max(0, int((1 - 2.0) * 200)) = 0
    # Dependentes: 4 (3+) -> 50
    # Dívidas: "sim" -> 0
    # Total: 54 + 0 + 0 + 50 + 0 = 104
    assert score == 104
    assert detalhes["parcela_emprego"] == 0
    assert detalhes["parcela_comprometimento"] == 0
    assert detalhes["parcela_dividas"] == 0
    assert detalhes["parcela_dependentes"] == 50


@pytest.mark.parametrize("resposta", ["sim", "tenho sim", "talvez", "", "yes"])
def test_calcular_score_dividas_ambiguas_sao_tratadas_como_divida(resposta):
    entrevista = {
        "renda_mensal": 5000.0,
        "tipo_emprego": "formal",
        "despesas_mensais": 1000.0,
        "num_dependentes": 0,
        "tem_dividas": resposta,
    }
    _, detalhes = calcular_score_detalhado(entrevista)
    assert detalhes["parcela_dividas"] == 0


@pytest.mark.parametrize("resposta", ["nao", "não", "N", "não tenho", "false"])
def test_calcular_score_ausencia_explicita_de_dividas_pontua(resposta):
    entrevista = {
        "renda_mensal": 5000.0,
        "tipo_emprego": "formal",
        "despesas_mensais": 1000.0,
        "num_dependentes": 0,
        "tem_dividas": resposta,
    }
    _, detalhes = calcular_score_detalhado(entrevista)
    assert detalhes["parcela_dividas"] == 150


def test_mensagem_data_invalida_nao_vaza_dados_de_clientes():
    from root_agent.application.presenters.banking_presenter import BankingPresenter
    import csv
    from pathlib import Path

    msg = BankingPresenter.data_invalida()
    assert "01/01/1990" in msg
    assert "DD/MM/AAAA" in msg

    # Carrega as datas de nascimento reais de clientes.csv e valida que nenhuma delas está na mensagem
    csv_path = Path(__file__).resolve().parent.parent.parent / "data" / "clientes.csv"
    if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data_real = row.get("data_nascimento")
                if data_real:
                    assert data_real not in msg, f"Vazamento detectado: {data_real} encontrado na mensagem de erro!"


def _entrevista(renda, emprego, despesas=0.0, dependentes=0, dividas="nao"):
    return {
        "renda_mensal": renda,
        "tipo_emprego": emprego,
        "despesas_mensais": despesas,
        "num_dependentes": dependentes,
        "tem_dividas": dividas,
    }


@pytest.mark.parametrize("emprego", ["desempregado", "formal", "autônomo"])
@pytest.mark.parametrize("renda", [0.0, -500.0, None])
def test_calcular_score_renda_zero_nao_pontua_comprometimento(renda, emprego):
    _, detalhes = calcular_score_detalhado(_entrevista(renda, emprego))
    assert detalhes["parcela_renda"] == 0
    assert detalhes["parcela_comprometimento"] == 0


def test_calcular_score_desempregado_sem_renda_e_sem_dividas():
    # Antes: 500 pts (comprometimento cheio com renda zero)
    score, _ = calcular_score_detalhado(_entrevista(0.0, "desempregado"))
    assert score == 300


@pytest.mark.parametrize("renda", [30000.0, 50000.0, 1_000_000.0])
def test_calcular_score_desempregado_renda_alta_respeita_teto(renda):
    # Antes: 800 pts (faixa de R$ 10 mil) para renda >= R$ 30 mil
    score, detalhes = calcular_score_detalhado(_entrevista(renda, "desempregado"))
    assert score == TETO_SCORE_DESEMPREGADO
    assert detalhes["ajuste_teto_desemprego"] == -200
    assert sum(detalhes.values()) == score


def test_calcular_score_desempregado_abaixo_do_teto_nao_sofre_ajuste():
    score, detalhes = calcular_score_detalhado(_entrevista(1000.0, "desempregado", 2000.0, 4, "sim"))
    assert score == 104
    assert detalhes["ajuste_teto_desemprego"] == 0


@pytest.mark.parametrize("renda", [20000.0, 30000.0, 50000.0])
def test_calcular_score_clt_renda_alta_continua_na_faixa_maxima(renda):
    score, detalhes = calcular_score_detalhado(_entrevista(renda, "clt", despesas=renda * 0.1))
    assert score >= 850
    assert detalhes["ajuste_teto_desemprego"] == 0


@pytest.mark.parametrize(
    "entrevista, esperado",
    [
        (_entrevista(30000.0, "formal"), 1000),
        (_entrevista(1_000_000.0, "formal"), 1000),
        (_entrevista(0.0, "desempregado", 5000.0, 3, "sim"), 50),
        (_entrevista(-100.0, "desempregado", -100.0, -1, "sim"), 150),
    ],
)
def test_calcular_score_limites_preservados(entrevista, esperado):
    score, detalhes = calcular_score_detalhado(entrevista)
    assert 0 <= score <= 1000
    assert score == esperado
    assert sum(detalhes.values()) == score
