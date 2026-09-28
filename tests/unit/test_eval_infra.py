"""Testes da tolerância a erros do provedor nos evals: retentativas, timeout e telemetria (sem LLM)."""
import asyncio

import litellm
import pytest

from tests.evals import harness
from tests.evals.harness import (
    ConversationResult,
    FalhaDeInfraestrutura,
    FalhaNoLogin,
    executar_com_retentativas,
)
from tests.evals.telemetria import ConsumoLLM, ContadorLLM, eh_rate_limit


def _erro_429() -> Exception:
    return litellm.RateLimitError("Resource exhausted", llm_provider="gemini", model="gemini-2.5-flash")


def _resultado() -> ConversationResult:
    return ConversationResult(turns=[], final_state={}, clientes={})


class Executor:
    """Dublê de executar_conversa: cada chamada consome o próximo efeito (exceção, callable ou resultado)."""

    def __init__(self, *efeitos):
        self.efeitos = list(efeitos)
        self.chamadas = 0

    async def __call__(self, mensagens, cliente, state):
        self.chamadas += 1
        efeito = self.efeitos.pop(0)
        if isinstance(efeito, BaseException):
            raise efeito
        if callable(efeito):
            return await efeito()
        return efeito


class Relogio:
    def __init__(self):
        self.esperas = []

    async def __call__(self, segundos):
        self.esperas.append(segundos)


@pytest.fixture(autouse=True)
def _sem_pausa(monkeypatch):
    monkeypatch.setattr(harness, "PAUSA_ENTRE_CONVERSAS", 0.0)
    monkeypatch.setattr(harness, "ESPERA_RATE_LIMIT", 30.0)


async def test_rate_limit_refaz_a_conversa_com_espera_crescente_e_registra_incidentes():
    executor, relogio = Executor(_erro_429(), _erro_429(), _resultado()), Relogio()

    result = await executar_com_retentativas(["oi"], tentativas=3, executor=executor, dormir=relogio, medidor=ContadorLLM())

    assert executor.chamadas == 3
    assert relogio.esperas == [30.0, 60.0]
    assert result.tentativas == 3
    assert [i["tipo"] for i in result.incidentes] == ["rate_limit", "rate_limit"]


async def test_timeout_da_conversa_e_erro_de_infraestrutura():
    async def lenta():
        await asyncio.sleep(1)

    executor, relogio = Executor(lenta, _resultado()), Relogio()
    result = await executar_com_retentativas(
        ["oi"], tentativas=2, timeout=0.01, executor=executor, dormir=relogio, medidor=ContadorLLM(),
    )
    assert result.incidentes[0]["tipo"] == "timeout"
    assert relogio.esperas == [5.0]


async def test_429_engolido_pelo_guardrail_tambem_refaz_a_conversa():
    medidor = ContadorLLM()

    async def conversa_com_429_absorvido():
        # O guardrail trata a falha e a conversa termina "normalmente"; só o LiteLLM viu o 429
        await medidor.async_log_failure_event({"exception": _erro_429()}, None, None, None)
        return _resultado()

    executor = Executor(conversa_com_429_absorvido, _resultado())
    result = await executar_com_retentativas(["oi"], tentativas=2, executor=executor, dormir=Relogio(), medidor=medidor)

    assert executor.chamadas == 2
    assert result.tentativas == 2
    assert result.incidentes[0]["tipo"] == "rate_limit"
    assert "absorvida" in result.incidentes[0]["detalhe"]


async def test_esgotar_tentativas_levanta_falha_de_infraestrutura_com_incidentes():
    executor = Executor(RuntimeError("503 Service Unavailable"), _erro_429())

    with pytest.raises(FalhaDeInfraestrutura) as exc:
        await executar_com_retentativas(["oi"], tentativas=2, executor=executor, dormir=Relogio(), medidor=ContadorLLM())

    assert [i["tipo"] for i in exc.value.incidentes] == ["RuntimeError", "rate_limit"]
    assert "2 tentativa(s)" in str(exc.value)


async def test_falha_de_comportamento_no_login_nao_e_repetida():
    executor = Executor(FalhaNoLogin("não autenticou"), _resultado())

    with pytest.raises(FalhaNoLogin):
        await executar_com_retentativas(["oi"], tentativas=3, executor=executor, dormir=Relogio(), medidor=ContadorLLM())
    assert executor.chamadas == 1


async def test_pausa_entre_conversas_limita_o_ritmo(monkeypatch):
    monkeypatch.setattr(harness, "PAUSA_ENTRE_CONVERSAS", 4.0)
    relogio = Relogio()
    await executar_com_retentativas(["oi"], executor=Executor(_resultado()), dormir=relogio, medidor=ContadorLLM())
    assert relogio.esperas == [4.0]


@pytest.mark.parametrize("exc, esperado", [
    (_erro_429(), True),
    (RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded for requests per minute"), True),
    (type("ErroGoogle", (Exception,), {"code": 429})("cota"), True),
    (ValueError("resposta inválida"), False),
    (None, False),
])
def test_eh_rate_limit(exc, esperado):
    assert eh_rate_limit(exc) is esperado


def test_eh_rate_limit_em_excecao_encadeada():
    try:
        try:
            raise _erro_429()
        except Exception as causa:
            raise RuntimeError("falha no agente") from causa
    except RuntimeError as exc:
        assert eh_rate_limit(exc)


async def test_contador_registra_chamadas_tokens_e_rate_limit_via_callbacks_do_litellm():
    contador = ContadorLLM()
    litellm.callbacks.append(contador)
    try:
        await litellm.acompletion(
            model="gemini/gemini-2.5-flash", messages=[{"role": "user", "content": "oi"}],
            mock_response="ok", api_key="chave-falsa",
        )
        with pytest.raises(litellm.RateLimitError):
            await litellm.acompletion(
                model="gemini/gemini-2.5-flash", messages=[{"role": "user", "content": "oi"}],
                mock_response=_erro_429(), api_key="chave-falsa",
            )
        await asyncio.sleep(0.1)  # o callback de sucesso roda numa task em segundo plano
    finally:
        litellm.callbacks.remove(contador)

    consumo = contador.instantaneo()
    assert (consumo.chamadas, consumo.falhas, consumo.rate_limits) == (2, 1, 1)
    assert consumo.tokens_entrada > 0 and consumo.tokens_saida > 0


def test_consumo_subtrai_instantaneos():
    depois = ConsumoLLM(chamadas=5, falhas=1, rate_limits=1, tokens_entrada=100, tokens_saida=10)
    antes = ConsumoLLM(chamadas=2, tokens_entrada=40)
    assert (depois - antes).como_dict() == {
        "chamadas": 3, "falhas": 1, "rate_limits": 1, "tokens_entrada": 60, "tokens_saida": 10,
    }
