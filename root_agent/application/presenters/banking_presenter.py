from root_agent.domain.models import ClienteDTO, CotacaoDTO

class BankingPresenter:
    @staticmethod
    def boas_vindas() -> str:
        return (
            "Olá! Bem-vindo(a) ao *Banco Ágil* 🏦\n\n"
            "Para garantir a segurança da sua conta, precisamos confirmar sua identidade.\n\n"
            "Por favor, informe seu *CPF* (apenas números):"
        )

    @staticmethod
    def solicitar_data_nascimento() -> str:
        return "Obrigado! Agora informe sua *data de nascimento* no formato DD/MM/AAAA:"

    @staticmethod
    def cpf_invalido() -> str:
        return "⚠️ Não identificamos um CPF válido. Por favor, informe os 11 dígitos numéricos do seu CPF (apenas números):"

    @staticmethod
    def data_invalida() -> str:
        return "⚠️ Data inválida. Por favor, use o formato DD/MM/AAAA (ex: 01/01/1990):"

    @staticmethod
    def autenticacao_falha(tentativas_restantes: int) -> str:
        return (
            f"❌ Não conseguimos confirmar sua identidade.\n"
            f"Você tem mais *{tentativas_restantes} tentativa(s)*. Tente novamente.\n\n"
            "Para reiniciar o processo, por favor, informe seu *CPF* novamente. Em seguida, pediremos sua Data de Nascimento:"
        )

    @staticmethod
    def autenticacao_bloqueada() -> str:
        return (
            "🔒 Por segurança, não foi possível autenticar sua conta após 3 tentativas.\n\n"
            "Se precisar de ajuda, entre em contato pela nossa central:\n"
            "📞 *0800 123 4567* (24h)\n\n"
            "Até logo! 👋"
        )

    @staticmethod
    def autenticacao_erro_tecnico() -> str:
        return (
            "😕 Não conseguimos validar seus dados agora por uma instabilidade.\n\n"
            "Por favor, informe seu *CPF* novamente para tentarmos outra vez:"
        )

    @staticmethod
    def verificacao_seguranca_indisponivel() -> str:
        return (
            "😕 Não conseguimos concluir a verificação de segurança da sua mensagem agora.\n\n"
            "Por favor, tente novamente em alguns instantes."
        )

    @staticmethod
    def autenticacao_sucesso(nome: str) -> str:
        return (
            f"✅ Identidade confirmada! Olá, *{nome}*!\n\n"
            "Como posso ajudar você hoje?\n\n"
            "- 💳 Consultar ou solicitar aumento de *limite de crédito*\n"
            "- 📊 Realizar *entrevista de crédito* para atualizar seu score\n"
            "- 💱 Consultar *cotação de moedas* (câmbio)\n\n"
            "Basta me dizer o que precisa!"
        )

    @staticmethod
    def limite_credito(cliente: ClienteDTO) -> str:
        return (
            f"💳 *Seu Limite de Crédito*\n\n"
            f"Limite Atual: R$ {cliente.limite_credito:,.2f}\n"
            f"Score de Crédito: {cliente.score_credito}/1000\n\n"
            "Você pode solicitar um aumento de limite se desejar."
        )

    @staticmethod
    def cotacao(cotacao: CotacaoDTO) -> str:
        return (
            f"💱 *Cotação de Câmbio*\n\n"
            f"A cotação atual do {cotacao.moeda_destino} em relação ao Real é:\n"
            f"1 {cotacao.moeda_destino} ≈ R$ {cotacao.taxa:,.4f}\n\n"
            f"(Cotação de referência atualizada em: {cotacao.timestamp})"
        )

    @staticmethod
    def encerramento() -> str:
        return "Foi um prazer ajudar! Qualquer coisa, estamos à disposição. *Banco Ágil* 🏦👋"
