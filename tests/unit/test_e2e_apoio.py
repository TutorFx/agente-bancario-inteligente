"""Testes da leitura dos eventos do /run e da retentativa usadas pelos testes E2E (sem LLM)."""
import pytest

from tests.e2e.apoio import Turno, com_retentativa

EVENTOS = [
    {"author": "agente_triagem", "content": {"role": "model", "parts": [
        {"functionCall": {"name": "transfer_to_agent", "args": {"agent_name": "agente_credito"}}}]}},
    {"author": "agente_triagem", "content": {"role": "user", "parts": [
        {"functionResponse": {"name": "transfer_to_agent", "response": {"result": None}}}]},
     "actions": {"transferToAgent": "agente_credito", "stateDelta": {"conv_state": "autenticado"}}},
    {"author": "agente_credito", "content": {"role": "model", "parts": [
        {"functionCall": {"name": "consultar_limite_credito", "args": {}}}]}},
    {"author": "agente_credito", "content": {"role": "user", "parts": [
        {"functionResponse": {"name": "consultar_limite_credito",
                              "response": {"result": "{\"limite_credito\": 5000.0}"}}}]}},
    {"author": "agente_credito", "content": {"role": "model", "parts": [
        {"text": "pensando...", "thought": True}, {"text": "Seu limite é R$ 5.000,00."}]},
     "actions": {"state_delta": {"extra": 1}}},
]


def test_turno_extrai_sinais_deterministicos_dos_eventos():
    turno = Turno(EVENTOS)
    assert turno.transferencias == ["agente_credito"]
    assert turno.tools_chamadas == ["transfer_to_agent", "consultar_limite_credito"]
    assert turno.respostas_tool("consultar_limite_credito") == [{"limite_credito": 5000.0}]
    assert turno.state_delta == {"conv_state": "autenticado", "extra": 1}
    assert turno.autor_final == "agente_credito"
    # Partes de raciocínio (thought) não contam como resposta ao cliente
    assert turno.texto == turno.ultimo_texto == "Seu limite é R$ 5.000,00."


def test_turno_sem_texto():
    turno = Turno([{"author": "agente_triagem", "content": {"parts": [{"functionCall": {"name": "x"}}]}}])
    assert turno.autor_final is None
    assert turno.ultimo_texto == ""
    assert turno.transferencias == []


async def test_com_retentativa_repete_conversa_e_avisa():
    tentativas = []

    async def cenario():
        tentativas.append(1)
        assert len(tentativas) > 1, "LLM tomou outro caminho"
        return "ok"

    with pytest.warns(UserWarning, match="tentativa 2"):
        assert await com_retentativa(cenario) == "ok"
    assert len(tentativas) == 2


async def test_com_retentativa_falha_quando_todas_as_tentativas_falham():
    async def cenario():
        assert False, "sempre diverge"

    with pytest.raises(AssertionError, match="Falhou nas 2 tentativas"):
        await com_retentativa(cenario)


async def test_com_retentativa_nao_repete_invariante_deterministica():
    tentativas = []

    async def cenario():
        tentativas.append(1)
        pytest.fail("vazou dado do cliente")

    with pytest.raises(pytest.fail.Exception, match="vazou"):
        await com_retentativa(cenario)
    assert len(tentativas) == 1
