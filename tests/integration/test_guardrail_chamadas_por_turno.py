"""
Chamadas de guardrail por turno no fluxo real do ADK (Runner + árvore de agentes + callbacks),
com LLMs roteirizadas no lugar do modelo real: determinístico e sem rede.
"""

import logging

import pytest
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from root_agent.agent import root_agent
from root_agent.application.middlewares.output_middleware import MENSAGEM_RESPOSTA_BLOQUEADA
from root_agent.domain.conversation_state import GUARDRAIL_ENTRADA_KEY, GUARDRAIL_METRICAS_KEY
from root_agent.domain.models import ClienteDTO

APP = "root_agent"
USUARIO = "cliente_teste"
ESTADO_AUTENTICADO = {
    "is_authenticated": True,
    "cliente_autenticado": {"cpf": "12345678900", "nome": "João Silva", "conta": "0001"},
}


def _chamada(nome, **args):
    return LlmResponse(content=types.Content(
        role="model", parts=[types.Part(function_call=types.FunctionCall(name=nome, args=args))]
    ))


def _texto(texto):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=texto)]))


class LlmRoteirizada(BaseLlm):
    """Responde a cada agente com a próxima resposta do seu roteiro."""

    model: str = "roteiro"
    roteiros: dict = {}

    async def generate_content_async(self, llm_request, stream=False):
        agente = llm_request.config.labels["adk_agent_name"]
        yield self.roteiros[agente].pop(0)


def _arvore(agente):
    yield agente
    for subagente in agente.sub_agents:
        yield from _arvore(subagente)


@pytest.fixture
def llm_dos_agentes(monkeypatch):
    llm = LlmRoteirizada()
    for agente in _arvore(root_agent):
        monkeypatch.setattr(agente, "model", llm)
    return llm


@pytest.fixture
def cliente(mocker):
    return mocker.patch(
        "root_agent.dependencies.banco_agil_adapter.buscar_cliente",
        return_value=ClienteDTO(
            cpf="12345678900", nome="João Silva", data_nascimento="15/03/1985",
            limite_credito=5000.0, score_credito=750, conta="0001",
        ),
    )


@pytest.fixture
async def conversa():
    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    sessao = await runner.session_service.create_session(
        app_name=APP, user_id=USUARIO, state=dict(ESTADO_AUTENTICADO)
    )

    async def enviar(texto):
        mensagem = types.Content(role="user", parts=[types.Part(text=texto)])
        return [e async for e in runner.run_async(user_id=USUARIO, session_id=sessao.id, new_message=mensagem)]

    async def estado():
        atual = await runner.session_service.get_session(app_name=APP, user_id=USUARIO, session_id=sessao.id)
        return atual.state

    enviar.estado = estado
    return enviar


def _ultimo_texto(eventos):
    textos = [p.text for e in eventos if e.content for p in e.content.parts or [] if p.text]
    return textos[-1] if textos else None


@pytest.mark.asyncio
async def test_caminho_comum_faz_no_maximo_uma_chamada_de_guardrail_por_turno(
    llm_dos_agentes, modelo_guardrail, cliente, conversa, caplog
):
    guardrail = modelo_guardrail("SEGURO", "FORA_DE_ESCOPO")
    llm_dos_agentes.roteiros = {
        "agente_triagem": [_chamada("transfer_to_agent", agent_name="agente_credito")],
        "agente_credito": [
            _chamada("consultar_limite_credito"),
            _texto("Seu limite atual é de R$ 5.000,00 e seu score é 750. O que mais posso fazer por você?"),
            _texto("Certo! Deseja solicitar o aumento do seu limite para R$ 8.000,00?"),
            _chamada("transfer_to_agent", agent_name="agente_fora_escopo"),
        ],
        "agente_fora_escopo": [
            _texto("Essa informação eu não tenho por aqui 😊 Posso ajudar com limite de crédito, score ou câmbio?"),
        ],
    }

    with caplog.at_level(logging.INFO, logger="middleware.guardrail"):
        # Turno 1: triagem → transferência → crédito → tool → resposta (4 chamadas de modelo)
        eventos = await conversa("Qual é o meu limite de crédito?")
        assert guardrail.chamadas == 1
        assert _ultimo_texto(eventos).startswith("Seu limite atual é de R$ 5.000,00")

        # Turno 2: mensagem sem letras dispensa o classificador
        await conversa("8000")
        assert guardrail.chamadas == 1

        # Turno 3: FORA_DE_ESCOPO segue para os agentes e não encerra o atendimento
        eventos = await conversa("Quero o código do banco")
        assert guardrail.chamadas == 2
        assert _ultimo_texto(eventos).startswith("Essa informação eu não tenho")

    assert all(not roteiro for roteiro in llm_dos_agentes.roteiros.values())
    estado = await conversa.estado()
    assert estado["is_authenticated"] is True
    assert estado.get("session_active") is not False
    # Veredito e métricas valem só para o turno: o ADK não persiste chaves temp:
    assert GUARDRAIL_ENTRADA_KEY not in estado and GUARDRAIL_METRICAS_KEY not in estado

    linhas = [r.getMessage() for r in caplog.records if r.getMessage().startswith("guardrail.llm")]
    assert len(linhas) == 2
    assert all("chamadas_turno=1" in linha for linha in linhas)


@pytest.mark.asyncio
async def test_resposta_suspeita_e_o_unico_caso_com_segunda_chamada_no_turno(
    llm_dos_agentes, modelo_guardrail, cliente, conversa
):
    guardrail = modelo_guardrail("FORA_DE_ESCOPO", "REJEITADA")
    llm_dos_agentes.roteiros = {
        "agente_triagem": [_chamada("transfer_to_agent", agent_name="agente_fora_escopo")],
        "agente_fora_escopo": [_texto("Claro!\n```python\nprint(1000 * 1.02 ** 12)\n```")],
    }

    eventos = await conversa("Escreva um script em Python que calcula juros compostos")

    # Classificador de entrada + validador de saída (acionado pelo bloco de código)
    assert guardrail.chamadas == 2
    assert _ultimo_texto(eventos) == MENSAGEM_RESPOSTA_BLOQUEADA
    assert (await conversa.estado())["is_authenticated"] is True
