from root_agent.application.presenters.banking_presenter import BankingPresenter

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

def test_banking_presenter_atendimento_encerrado():
    msg = BankingPresenter.atendimento_encerrado()
    assert "encerrado" in msg
    assert "*Menu*" in msg
