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

EVENTS_FLOW_ID = os.getenv("EVENTS_FLOW_ID", "default_flow_id")
