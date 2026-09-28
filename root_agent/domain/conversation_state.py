from enum import Enum

class BankingConversationState(str, Enum):
    IDLE = "idle"
    # --- Autenticação ---
    AGUARDANDO_CPF = "aguardando_cpf"
    AGUARDANDO_DATA_NASCIMENTO = "aguardando_data_nascimento"
    AUTENTICADO = "autenticado"
    # --- Entrevista de Crédito ---
    ENTREVISTA_PERGUNTA_1 = "entrevista_p1_renda"
    ENTREVISTA_PERGUNTA_2 = "entrevista_p2_emprego"
    ENTREVISTA_PERGUNTA_3 = "entrevista_p3_despesas"
    ENTREVISTA_PERGUNTA_4 = "entrevista_p4_dependentes"
    ENTREVISTA_PERGUNTA_5 = "entrevista_p5_dividas"

CONVERSATION_STATE_KEY = "conv_state"
AUTH_TENTATIVAS_KEY = "auth_tentativas"
AUTH_CPF_TEMP_KEY = "auth_cpf_temp"
CLIENTE_KEY = "cliente_autenticado"
ENTREVISTA_KEY = "entrevista_dados"
ENTREVISTA_REALIZADA_KEY = "entrevista_realizada_na_sessao"

# Guardrails: valem só para o turno atual. O prefixo temp: faz o ADK mantê-las em memória
# durante a invocação (inclusive nos subagentes que recebem o turno) sem persisti-las.
GUARDRAIL_ENTRADA_KEY = "temp:guardrail_entrada"
GUARDRAIL_METRICAS_KEY = "temp:guardrail_metricas"

# Mensagem do cliente neste turno como foi digitada, antes do mascaramento de CPF/datas feito
# pelo MascaramentoCredenciaisPlugin: o evento persistido guarda só a versão mascarada, e o
# original fica em memória (temp:) para a máquina de login e o guardrail de entrada.
TEXTO_ORIGINAL_USUARIO_KEY = "temp:texto_original_usuario"
