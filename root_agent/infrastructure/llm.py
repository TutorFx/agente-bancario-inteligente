from google.adk.models.lite_llm import LiteLlm
from root_agent.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME

custom_model = LiteLlm(
    model=LLM_MODEL_NAME,
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
)
