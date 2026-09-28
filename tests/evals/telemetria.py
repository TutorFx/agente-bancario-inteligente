"""
Consumo de LLM durante os evals, medido pelos callbacks do LiteLLM (agentes, guardrails e juiz
passam todos por ele), e detecção de rate limit do provedor.

O contador também revela 429 que não chegam ao harness como exceção: o guardrail de entrada
engole a falha da própria LLM e aplica a política fail-open/fail-closed, o que viraria uma
falha de comportamento falsa se a conversa não fosse refeita.
"""
import re
from dataclasses import asdict, dataclass, replace

from litellm.integrations.custom_logger import CustomLogger

_REGEX_RATE_LIMIT = re.compile(r"(?i)\b429\b|resource[_ ]exhausted|rate[ _-]?limit|quota exceeded|too many requests")


def eh_rate_limit(exc: BaseException | None) -> bool:
    """429 do provedor, direto ou encadeado (__cause__/__context__) em outra exceção."""
    vistos: set[int] = set()
    while exc is not None and id(exc) not in vistos:
        vistos.add(id(exc))
        if 429 in (getattr(exc, "status_code", None), getattr(exc, "code", None)):
            return True
        if type(exc).__name__ == "RateLimitError" or _REGEX_RATE_LIMIT.search(str(exc)):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


@dataclass
class ConsumoLLM:
    chamadas: int = 0
    falhas: int = 0
    rate_limits: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0

    def __sub__(self, outro: "ConsumoLLM") -> "ConsumoLLM":
        return ConsumoLLM(**{k: v - getattr(outro, k) for k, v in asdict(self).items()})

    def como_dict(self) -> dict[str, int]:
        return asdict(self)


class ContadorLLM(CustomLogger):
    """Callback do LiteLLM. Chamadas assíncronas só disparam os ganchos async (sem contagem dupla)."""

    def __init__(self) -> None:
        super().__init__()
        self.consumo = ConsumoLLM()

    def instantaneo(self) -> ConsumoLLM:
        return replace(self.consumo)

    def _sucesso(self, response_obj) -> None:
        self.consumo.chamadas += 1
        uso = getattr(response_obj, "usage", None)
        self.consumo.tokens_entrada += int(getattr(uso, "prompt_tokens", 0) or 0)
        self.consumo.tokens_saida += int(getattr(uso, "completion_tokens", 0) or 0)

    def _falha(self, kwargs) -> None:
        self.consumo.chamadas += 1
        self.consumo.falhas += 1
        if eh_rate_limit(kwargs.get("exception")):
            self.consumo.rate_limits += 1

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._sucesso(response_obj)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._sucesso(response_obj)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._falha(kwargs)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._falha(kwargs)


contador = ContadorLLM()


def instalar() -> None:
    """Registra o contador nos callbacks globais do LiteLLM (só nas execuções de evals)."""
    import litellm

    if contador not in litellm.callbacks:
        litellm.callbacks.append(contador)
