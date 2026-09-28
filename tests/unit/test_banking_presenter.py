from root_agent.application.presenters.banking_presenter import BankingPresenter
from root_agent.domain.models import ClienteDTO, CotacaoDTO

def test_banking_presenter_boas_vindas():
    msg = BankingPresenter.boas_vindas()
    assert "Banco Ágil" in msg
    assert "CPF" in msg

def test_banking_presenter_solicitar_data_nascimento():
    msg = BankingPresenter.solicitar_data_nascimento()
    assert "data de nascimento" in msg
    assert "DD/MM/AAAA" in msg

def test_banking_presenter_cpf_invalido():
    msg = BankingPresenter.cpf_invalido()
    assert "Não identificamos um CPF válido" in msg

def test_banking_presenter_data_invalida():
    msg = BankingPresenter.data_invalida()
    assert "Data inválida" in msg

def test_banking_presenter_autenticacao_falha():
    msg = BankingPresenter.autenticacao_falha(2)
    assert "2 tentativa(s)" in msg

def test_banking_presenter_autenticacao_bloqueada():
    msg = BankingPresenter.autenticacao_bloqueada()
    assert "3 tentativas" in msg
    assert "0800 123 4567" in msg

def test_banking_presenter_autenticacao_sucesso():
    msg = BankingPresenter.autenticacao_sucesso("Maria Silva")
    assert "Maria Silva" in msg
    assert "limite de crédito" in msg

def test_banking_presenter_limite_credito():
    cliente = ClienteDTO(
        cpf="12345678900",
        nome="Maria",
        data_nascimento="01/01/1990",
        score_credito=750,
        limite_credito=4500.0,
        conta="12345-6"
    )
    msg = BankingPresenter.limite_credito(cliente)
    assert "4,500.00" in msg
    assert "750/1000" in msg

def test_banking_presenter_cotacao():
    cotacao = CotacaoDTO(
        moeda_origem="BRL",
        moeda_destino="USD",
        taxa=5.4321,
        timestamp="2026-09-28"
    )
    msg = BankingPresenter.cotacao(cotacao)
    assert "USD" in msg
    assert "5.4321" in msg

def test_banking_presenter_encerramento():
    msg = BankingPresenter.encerramento()
    assert "Foi um prazer ajudar" in msg
