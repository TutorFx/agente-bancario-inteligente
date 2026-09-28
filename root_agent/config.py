import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

LLM_BASE_URL = os.getenv("LLM_BASE_URL") or None
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini/gemini-2.5-flash")

# No LiteLLM, para usar API Key direta, o modelo precisa ter o prefixo 'gemini/'
# Sem esse prefixo, o LiteLLM tenta usar Vertex AI e força login no gcloud
if not LLM_BASE_URL and LLM_MODEL_NAME.startswith("gemini-"):
    LLM_MODEL_NAME = f"gemini/{LLM_MODEL_NAME}"

# Garante que as variáveis padrão do LiteLLM e Google SDK estejam populadas no ambiente
if LLM_API_KEY:
    os.environ["GEMINI_API_KEY"] = LLM_API_KEY
    os.environ["GOOGLE_API_KEY"] = LLM_API_KEY

# --- Guardrails via LLM (classificador de entrada e validador de saída) ---
# Política quando a LLM do guardrail falha (erro, timeout ou resposta fora do formato):
#   fail_closed → bloqueia a mensagem; fail_open → segue o fluxo e registra aviso no log.
FAIL_OPEN = "fail_open"
FAIL_CLOSED = "fail_closed"


def _politica_falha(variavel: str, padrao: str) -> str:
    valor = (os.getenv(variavel) or padrao).strip().lower().replace("-", "_")
    # Valor desconhecido cai no modo seguro, em vez de desligar o guardrail por engano
    return valor if valor in (FAIL_OPEN, FAIL_CLOSED) else FAIL_CLOSED


# Permite um modelo mais barato/rápido só para classificação (padrão: o mesmo dos agentes)
GUARDRAIL_MODEL_NAME = os.getenv("GUARDRAIL_MODEL_NAME") or LLM_MODEL_NAME
if not LLM_BASE_URL and GUARDRAIL_MODEL_NAME.startswith("gemini-"):
    GUARDRAIL_MODEL_NAME = f"gemini/{GUARDRAIL_MODEL_NAME}"
GUARDRAIL_TIMEOUT_SEGUNDOS = float(os.getenv("GUARDRAIL_TIMEOUT_SEGUNDOS", "5"))

# Entrada: fail-closed nos agentes que executam ações de crédito/score, fail-open na conversa geral
GUARDRAIL_AGENTES_SENSIVEIS = frozenset(
    nome.strip()
    for nome in os.getenv("GUARDRAIL_AGENTES_SENSIVEIS", "agente_credito,agente_entrevista_credito").split(",")
    if nome.strip()
)
GUARDRAIL_FALHA_ENTRADA_SENSIVEL = _politica_falha("GUARDRAIL_FALHA_ENTRADA_SENSIVEL", FAIL_CLOSED)
GUARDRAIL_FALHA_ENTRADA_GERAL = _politica_falha("GUARDRAIL_FALHA_ENTRADA_GERAL", FAIL_OPEN)

# Saída: a LLM só é consultada diante de sinal suspeito, por isso a falha bloqueia por padrão
GUARDRAIL_FALHA_SAIDA = _politica_falha("GUARDRAIL_FALHA_SAIDA", FAIL_CLOSED)
# Acima deste tamanho, uma resposta sem nenhum termo bancário é tratada como suspeita
GUARDRAIL_SAIDA_TEXTO_LONGO = int(os.getenv("GUARDRAIL_SAIDA_TEXTO_LONGO", "500"))

# --- API HTTP (main.py) ---
# Com token, toda rota (exceto /health) exige "Authorization: Bearer <token>" ou "X-API-Key".
# Sem token, a API só aceita conexões locais (loopback): nada de leitura remota de sessões.
API_TOKEN = (os.getenv("BANCO_AGIL_API_TOKEN") or "").strip() or None

# Interface de desenvolvimento do ADK (/dev-ui): desligada por padrão, pois exibe sessões e estado
DEV_UI_HABILITADA = (os.getenv("BANCO_AGIL_DEV_UI") or "").strip().lower() in ("1", "true", "sim", "yes", "on")
