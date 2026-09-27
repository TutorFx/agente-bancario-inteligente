from deepeval.models.base_model import DeepEvalBaseLLM
import litellm
from root_agent.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME

class CustomGeminiEvaluator(DeepEvalBaseLLM):
    """
    LLM customizado para atuar como Juiz no DeepEval, utilizando
    o modelo do LLM via LiteLLM com autenticação direta.
    """
    def __init__(self, model: str = None):
        # O nome do modelo é pego da configuração central, mas permite override.
        self.model_name = model or LLM_MODEL_NAME

    def load_model(self):
        return self.model_name

    def generate(self, prompt: str) -> str:
        response = litellm.completion(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )
        return response.choices[0].message.content

    async def a_generate(self, prompt: str) -> str:
        response = await litellm.acompletion(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
        )
        return response.choices[0].message.content

    def get_model_name(self):
        return self.model_name
