"""Mascaramento de CPF e data de nascimento em texto livre (root_agent/domain/pii.py)."""

import pytest

from root_agent.domain.guardrails import extrair_data, validar_formato_cpf
from root_agent.domain.pii import MASCARA_CPF, MASCARA_DATA, mascarar_pii


# Todo formato de CPF que o login aceita (validar_formato_cpf) precisa sair mascarado
@pytest.mark.parametrize("cpf", [
    "12345678900",
    "123.456.789-00",
    "123 456 789 00",
    "123-456-789-00",
    "123/456/789/00",
    "123.456.789 00",
    "123. 456. 789 - 00",
    "123.456.78900",
    "1 2 3 4 5 6 7 8 9 0 0",
])
def test_mascara_todo_cpf_aceito_pelo_login(cpf):
    assert validar_formato_cpf(cpf)
    assert mascarar_pii(cpf) == MASCARA_CPF
    assert mascarar_pii(f"Meu CPF é {cpf}, obrigado.") == f"Meu CPF é {MASCARA_CPF}, obrigado."


@pytest.mark.parametrize("data", [
    "15/03/1985",
    "15-03-1985",
    "15.03.1985",
    "15/03-1985",
    "15 / 03 / 1985",
    "5/3/1985",
    "15/03/85",
    "1985-03-15",
    "1985/03/15",
    "15 de março de 1985",
    "15 de marco de 1985",
    "15 de Março de 1985",
    "1º de março de 1985",
    "15 mar 1985",
    "15 de mar. de 1985",
    "15/mar/1985",
])
def test_mascara_formatos_comuns_de_data(data):
    assert mascarar_pii(data) == MASCARA_DATA
    assert mascarar_pii(f"nasci em {data}.") == f"nasci em {MASCARA_DATA}."


@pytest.mark.parametrize("data", ["15/03/1985", "15-03-1985"])
def test_formatos_de_data_aceitos_pelo_login_sao_mascarados(data):
    assert extrair_data(data)
    assert mascarar_pii(data) == MASCARA_DATA


@pytest.mark.parametrize("texto, esperado", [
    ("123.456.789-00 15/03/1985", f"{MASCARA_CPF} {MASCARA_DATA}"),
    ("CPF 123 456 789 00 e nascimento 15 de março de 1985",
     f"CPF {MASCARA_CPF} e nascimento {MASCARA_DATA}"),
    ("12345678900 0001", f"{MASCARA_CPF} 0001"),
    ("cpf:12345678900;data:1985-03-15", f"cpf:{MASCARA_CPF};data:{MASCARA_DATA}"),
])
def test_mascara_cpf_e_data_na_mesma_mensagem(texto, esperado):
    assert mascarar_pii(texto) == esperado


# Valores da entrevista de crédito e pedidos de limite não podem ser escondidos dos agentes
@pytest.mark.parametrize("texto", [
    "R$ 8.000,00",
    "8000",
    "quero 8000 de limite",
    "quero aumentar para R$ 8.000",
    "R$ 1.234.567,89",
    "minha renda é R$ 12.500,50 e gasto R$ 3.000 por mês",
    "despesas 2500 e renda 8000",
    "2.500",
    "10.000.000",
    "R$ 10.000.000.000",
    "R$10000000000",
    "tenho 2 dependentes",
    "0",
    "qual a cotação do dólar hoje?",
    "",
])
def test_nao_mascara_valores_nem_texto_comum(texto):
    assert mascarar_pii(texto) == texto


def test_mascaramento_e_idempotente():
    mascarado = mascarar_pii("123.456.789-00 e 15/03/1985")
    assert mascarar_pii(mascarado) == mascarado
