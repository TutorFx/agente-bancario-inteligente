"""
As instruções dos agentes passam pelo template do ADK: `{chave}` vira o valor da chave no
estado da sessão e, sem o `?`, uma chave ausente derruba o turno inteiro com KeyError
("Context variable not found"). Aqui cada instrução é renderizada com o próprio ADK, na
sessão de um cliente que acabou de se autenticar.
"""

import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.sessions import InMemorySessionService
from google.adk.utils.instructions_utils import inject_session_state

from root_agent.agent import root_agent


def _agentes(agente):
    yield agente
    for sub in agente.sub_agents:
        yield from _agentes(sub)


@pytest.mark.parametrize("agente", list(_agentes(root_agent)), ids=lambda a: a.name)
async def test_instrucao_renderiza_com_estado_de_cliente_autenticado(agente):
    servico = InMemorySessionService()
    sessao = await servico.create_session(
        app_name="root_agent",
        user_id="u",
        state={"is_authenticated": True, "nome": "João Silva", "entrevista_realizada_na_sessao": False},
    )
    contexto = ReadonlyContext(
        InvocationContext(session_service=servico, invocation_id="inv", agent=agente, session=sessao)
    )

    instrucao = await inject_session_state(agente.instruction, contexto)

    assert "João Silva" in instrucao or "{nome?}" not in agente.instruction
