"""
Chamada compartilhada à LLM dos guardrails (classificador de entrada e validador de saída).

Concentra o que é comum aos dois: timeout, leitura do rótulo devolvido e o registro de
latência e contagem de chamadas por turno no logger. A política de falha fica com quem
chama, que recebe FalhaGuardrail quando não há veredito utilizável.
"""
import asyncio
import logging
import re
import time
from typing import Iterable, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest
from google.genai import types

from root_agent import config
from root_agent.domain.conversation_state import GUARDRAIL_METRICAS_KEY
from root_agent.infrastructure.llm import guardrail_model
from root_agent.utils import get_logger, registrar_metricas

logger = get_logger("middleware.guardrail")


class FalhaGuardrail(Exception):
    """A LLM do guardrail não devolveu um veredito utilizável (erro, timeout ou formato inválido)."""


def turno_atual(callback_context: CallbackContext) -> str:
    """
    Chave do turno: o invocation_id do ADK, gerado a cada mensagem do usuário e
    compartilhado por todos os subagentes que participam da mesma resposta.
    """
    return str(getattr(callback_context, "invocation_id", None) or "")


def _extrair_rotulo(texto: str, rotulos: tuple[str, ...]) -> Optional[str]:
    """Aceita a resposta só se ela citar exatamente um dos rótulos (tolera markdown e pontuação)."""
    maiusculo = (texto or "").upper()
    encontrados = {
        rotulo
        for rotulo in rotulos
        # "FORA_DE_ESCOPO" também casa com "FORA DE ESCOPO"; "INSEGURO" não casa com "SEGURO"
        if re.search(r"(?<![A-Z_])" + r"[\s_-]+".join(map(re.escape, rotulo.split("_"))) + r"(?![A-Z_])", maiusculo)
    }
    return encontrados.pop() if len(encontrados) == 1 else None


async def _gerar_texto(request: LlmRequest) -> str:
    # generate_content_async é um async generator no ADK: precisa ser iterado, não aguardado
    texto = ""
    async for resposta in guardrail_model.generate_content_async(request):
        if resposta.content and resposta.content.parts:
            # Partes de raciocínio (thought) não fazem parte do rótulo devolvido
            texto = "".join(p.text for p in resposta.content.parts if p.text and not p.thought)
    return texto


def _registrar_chamada(
    callback_context: CallbackContext,
    guardrail: str,
    resultado: str,
    latencia_ms: float,
    erro: Optional[str],
) -> None:
    turno = turno_atual(callback_context)
    anteriores = callback_context.state.get(GUARDRAIL_METRICAS_KEY)
    if not isinstance(anteriores, dict) or anteriores.get("turno") != turno:
        anteriores = {}
    metricas = {
        "turno": turno,
        "chamadas": anteriores.get("chamadas", 0) + 1,
        "latencia_ms": anteriores.get("latencia_ms", 0.0) + latencia_ms,
    }
    callback_context.state[GUARDRAIL_METRICAS_KEY] = metricas

    campos = {
        "guardrail": guardrail,
        "agente": getattr(callback_context, "agent_name", None),
        "turno": turno,
        "resultado": resultado,
        "latencia_ms": round(latencia_ms),
        "chamadas_turno": metricas["chamadas"],
        "latencia_turno_ms": round(metricas["latencia_ms"]),
    }
    if erro:
        campos["erro"] = erro
    registrar_metricas(logger, "guardrail.llm", logging.WARNING if erro else logging.INFO, **campos)


async def consultar_llm_guardrail(
    callback_context: CallbackContext,
    *,
    guardrail: str,
    instrucao: str,
    conteudo: str,
    rotulos: Iterable[str],
) -> str:
    """
    Faz UMA chamada à LLM do guardrail e devolve o rótulo escolhido entre `rotulos`.

    Levanta FalhaGuardrail em caso de erro, de timeout (config.GUARDRAIL_TIMEOUT_SEGUNDOS)
    ou de resposta sem exatamente um dos rótulos; quem chama aplica a política de falha.
    """
    rotulos = tuple(rotulos)
    # A instrução vai no papel de sistema e o texto avaliado no de usuário, como dado
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text=conteudo)])],
        config=types.GenerateContentConfig(system_instruction=instrucao, temperature=0),
    )
    rotulo, erro = None, None
    inicio = time.perf_counter()
    try:
        texto = await asyncio.wait_for(_gerar_texto(request), timeout=config.GUARDRAIL_TIMEOUT_SEGUNDOS)
        rotulo = _extrair_rotulo(texto, rotulos)
        if rotulo is None:
            erro = "resposta_invalida"
    except asyncio.TimeoutError:
        erro = "timeout"
    except Exception as exc:
        logger.debug("Falha na chamada à LLM do guardrail %s", guardrail, exc_info=True)
        erro = type(exc).__name__
    _registrar_chamada(callback_context, guardrail, rotulo or "falha", (time.perf_counter() - inicio) * 1000, erro)

    if rotulo is None:
        raise FalhaGuardrail(erro)
    return rotulo
