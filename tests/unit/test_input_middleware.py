import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from root_agent.application.middlewares.input_middleware import (
    before_model_callback,
    _extrair_texto_usuario,
    _mascarar_pii,
    _construir_resposta,
    _obter_estado,
    _limpar_estado,
    _disparar_encerramento,
    _tratar_aguardando_cpf,
    _tratar_aguardando_data_nascimento,
    _classificar_input_semantico,
    NivelRisco,
)
from root_agent.domain.models import ClienteDTO
from root_agent.domain.conversation_state import (
    BankingConversationState,
    CONVERSATION_STATE_KEY,
    AUTH_TENTATIVAS_KEY,
    AUTH_CPF_TEMP_KEY,
    CLIENTE_KEY,
)


def _criar_user_request(texto: str) -> LlmRequest:
    part = types.Part(text=texto)
    content = types.Content(role="user", parts=[part])
    return LlmRequest(contents=[content])


def test_extrair_texto_usuario_vazio():
    req_sem_contents = LlmRequest(contents=[])
    assert _extrair_texto_usuario(req_sem_contents) is None

    req_role_model = LlmRequest(contents=[types.Content(role="model", parts=[types.Part(text="Olá")])])
    assert _extrair_texto_usuario(req_role_model) is None


@pytest.mark.parametrize("texto, esperado", [
    ("123.456.789-01", "[CPF omitido]"),
    ("Meu CPF é 12345678901", "Meu CPF é [CPF omitido]"),
    ("nasci em 15/03/1985", "nasci em [data omitida]"),
    ("15-03-1985", "[data omitida]"),
    ("quero 8000 de limite", "quero 8000 de limite"),
    # Aceitos pelo login (ou comuns), mas antes chegavam à LLM nos turnos seguintes
    ("123 456 789 00", "[CPF omitido]"),
    ("nasci em 15 de março de 1985", "nasci em [data omitida]"),
    ("1985-03-15", "[data omitida]"),
    ("R$ 8.000,00", "R$ 8.000,00"),
])
def test_mascarar_pii(texto, esperado):
    assert _mascarar_pii(texto) == esperado


def test_obter_e_limpar_estado():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {}

    # Estado padrão quando ausente
    assert _obter_estado(ctx) == BankingConversationState.IDLE

    # Estado inválido converte para IDLE
    ctx.state[CONVERSATION_STATE_KEY] = "estado_inexistente"
    assert _obter_estado(ctx) == BankingConversationState.IDLE

    # Estado válido
    ctx.state[CONVERSATION_STATE_KEY] = BankingConversationState.AGUARDANDO_CPF.value
    assert _obter_estado(ctx) == BankingConversationState.AGUARDANDO_CPF

    # Limpar estado
    _limpar_estado(ctx)
    assert ctx.state[CONVERSATION_STATE_KEY] == BankingConversationState.IDLE


def test_disparar_encerramento():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {CLIENTE_KEY: "dados", "is_authenticated": True}
    ctx.actions = MagicMock()

    with patch("root_agent.dependencies.encerrar_atendimento", new_callable=AsyncMock) as mock_encerrar:
        _disparar_encerramento(ctx)
        assert ctx.state["is_authenticated"] is False
        assert ctx.state[CLIENTE_KEY] is None
        assert ctx.actions.transfer_to_agent == "agente_triagem"
        assert ctx.actions.end_of_agent is True


def test_tratar_aguardando_cpf():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {}
    req = _criar_user_request("olá, bom dia")

    # Mensagem sem dígitos é repassada para LLM
    resp = _tratar_aguardando_cpf(ctx, "olá, bom dia", req)
    assert resp is None

    # CPF com formato inválido
    resp_invalido = _tratar_aguardando_cpf(ctx, "12345", req)
    assert resp_invalido is not None
    assert "Não identificamos um CPF válido" in resp_invalido.content.parts[0].text

    # CPF com formato válido
    resp_valido = _tratar_aguardando_cpf(ctx, "123.456.789-00", req)
    assert resp_valido is not None
    assert "data de nascimento" in resp_valido.content.parts[0].text
    assert ctx.state[AUTH_CPF_TEMP_KEY] == "12345678900"
    assert ctx.state[CONVERSATION_STATE_KEY] == BankingConversationState.AGUARDANDO_DATA_NASCIMENTO


CLIENTE_TESTE = ClienteDTO(
    cpf="12345678901", nome="Carlos Silva", data_nascimento="15/03/1985",
    limite_credito=5000.0, score_credito=750, conta="0001",
)


def _mock_adapter(retorno=None, erro=None):
    adapter = MagicMock()
    if erro:
        adapter.autenticar.side_effect = erro
    else:
        adapter.autenticar.return_value = retorno
    return patch("root_agent.dependencies.get_banco_agil_adapter", return_value=adapter), adapter


def test_tratar_aguardando_data_nascimento_data_invalida():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {AUTH_CPF_TEMP_KEY: "12345678901"}
    patcher, adapter = _mock_adapter(CLIENTE_TESTE)

    with patcher:
        resp = _tratar_aguardando_data_nascimento(ctx, "amanhã")

    assert "Data inválida" in resp.content.parts[0].text
    adapter.autenticar.assert_not_called()
    assert ctx.state[AUTH_CPF_TEMP_KEY] == "12345678901"


def test_tratar_aguardando_data_nascimento_sucesso_autentica_sem_llm():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {AUTH_TENTATIVAS_KEY: 1, AUTH_CPF_TEMP_KEY: "12345678901"}
    patcher, adapter = _mock_adapter(CLIENTE_TESTE)

    with patcher:
        resp = _tratar_aguardando_data_nascimento(ctx, "15/03/1985")

    adapter.autenticar.assert_called_once_with("12345678901", "15/03/1985")
    assert "Identidade confirmada" in resp.content.parts[0].text
    assert "Carlos Silva" in resp.content.parts[0].text
    assert ctx.state["is_authenticated"] is True
    assert ctx.state[AUTH_TENTATIVAS_KEY] == 0
    assert ctx.state[CONVERSATION_STATE_KEY] == BankingConversationState.AUTENTICADO.value
    assert ctx.state[CLIENTE_KEY] == {"cpf": "12345678901", "nome": "Carlos Silva", "conta": "0001"}
    assert ctx.state["nome"] == "Carlos Silva"
    # Credenciais temporárias saem do estado logo após a validação
    assert ctx.state[AUTH_CPF_TEMP_KEY] is None
    assert ctx.state["auth_data_temp"] is None


@pytest.mark.parametrize("estado_inicial, patcher_args", [
    ({AUTH_CPF_TEMP_KEY: "12345678901"}, {"erro": OSError("csv indisponível")}),
    ({}, {"retorno": CLIENTE_TESTE}),
])
def test_autenticacao_fail_closed_em_erro_tecnico(estado_inicial, patcher_args):
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {AUTH_TENTATIVAS_KEY: 1, **estado_inicial}
    patcher, _ = _mock_adapter(**patcher_args)

    with patcher:
        resp = _tratar_aguardando_data_nascimento(ctx, "15/03/1985")

    assert "instabilidade" in resp.content.parts[0].text
    assert ctx.state["is_authenticated"] is False
    assert ctx.state[CLIENTE_KEY] is None
    # Erro técnico não consome tentativa do cliente
    assert ctx.state[AUTH_TENTATIVAS_KEY] == 1
    assert ctx.state[CONVERSATION_STATE_KEY] == BankingConversationState.AGUARDANDO_CPF
    assert ctx.state[AUTH_CPF_TEMP_KEY] is None


async def _turno(ctx, historico: list, texto: str):
    historico.append(types.Content(role="user", parts=[types.Part(text=texto)]))
    req = LlmRequest(contents=[c.model_copy(deep=True) for c in historico])
    resp = await before_model_callback(ctx, req)
    if resp is not None:
        historico.append(resp.content)
    return req, resp


@pytest.mark.asyncio
async def test_bloqueio_apos_3_tentativas_invalidas():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {}
    ctx.actions = MagicMock()
    historico = []
    patcher, adapter = _mock_adapter(None)

    with patcher, patch(
        "root_agent.application.middlewares.input_middleware._classificar_input_semantico",
        new_callable=AsyncMock, return_value=NivelRisco.SEGURO,
    ), patch("root_agent.dependencies.encerrar_atendimento", new_callable=AsyncMock):
        for tentativa, restantes in ((1, "2 tentativa(s)"), (2, "1 tentativa(s)")):
            _, resp = await _turno(ctx, historico, "111.222.333-44")
            assert "data de nascimento" in resp.content.parts[0].text
            _, resp = await _turno(ctx, historico, "01/01/2000")
            assert restantes in resp.content.parts[0].text
            assert ctx.state[AUTH_TENTATIVAS_KEY] == tentativa

        await _turno(ctx, historico, "111.222.333-44")
        _, resp = await _turno(ctx, historico, "01/01/2000")

    assert "3 tentativas" in resp.content.parts[0].text
    assert adapter.autenticar.call_count == 3
    assert ctx.state["is_authenticated"] is False
    # Encerramento reseta o estado de tentativas
    assert ctx.state[AUTH_TENTATIVAS_KEY] == 0
    assert ctx.actions.end_of_agent is True


@pytest.mark.asyncio
async def test_nenhum_llm_request_contem_cpf_ou_data_de_nascimento(modelo_guardrail):
    """Critério de aceite T2: credenciais nunca chegam ao provedor da LLM em nenhum ponto do fluxo."""
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {}
    ctx.actions = MagicMock()
    historico = []
    requests_para_agente = []
    classificador = modelo_guardrail("SEGURO")

    patcher, _ = _mock_adapter(CLIENTE_TESTE)
    with patcher:
        for i, texto in enumerate(("Olá, bom dia!", "Meu CPF é 123.456.789-01", "nasci em 15/03/1985",
                                   "qual meu limite?", "meu cpf é 12345678901 e nasci em 15-03-1985, certo?")):
            # Como no ADK: cada mensagem é um turno novo e o classificador lê o user_content sem máscara
            ctx.invocation_id = f"turno-{i}"
            ctx.user_content = types.Content(role="user", parts=[types.Part(text=texto)])
            req, resp = await _turno(ctx, historico, texto)
            if resp is None:
                # O request seguiu para o modelo do agente
                requests_para_agente.append(req)
            else:
                assert "12345678901" not in resp.content.parts[0].text

    assert ctx.state["is_authenticated"] is True
    # Todas as mensagens têm letras: o classificador roda em todos os turnos
    assert classificador.chamadas == 5
    requests_para_llm = requests_para_agente + classificador.requisicoes
    assert len(requests_para_llm) >= 7
    for req in requests_para_llm:
        serializado = req.model_dump_json()
        for pii in ("12345678901", "123.456.789-01", "15/03/1985", "15-03-1985"):
            assert pii not in serializado


def test_prompts_dos_agentes_nao_injetam_dados_do_cliente():
    """O estado cliente_autenticado contém o CPF; os prompts de sistema só podem receber o nome."""
    from root_agent.agent import root_agent

    agentes = [root_agent, *root_agent.sub_agents]
    for agente in agentes:
        assert "{cliente_autenticado" not in agente.instruction, agente.name
    assert not any(getattr(t, "__name__", "") == "autenticar_cliente" for t in root_agent.tools)


@pytest.mark.asyncio
async def test_cliente_autenticado_nao_tem_mensagem_numerica_tratada_como_cpf():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {
        "is_authenticated": True,
        CONVERSATION_STATE_KEY: BankingConversationState.AGUARDANDO_CPF.value,
    }
    req = _criar_user_request("quero aumentar meu limite para 8000")

    with patch("root_agent.application.middlewares.input_middleware._classificar_input_semantico", new_callable=AsyncMock) as mock_semantico:
        mock_semantico.return_value = NivelRisco.SEGURO
        res = await before_model_callback(ctx, req)

    assert res is None
    assert req.contents[0].parts[0].text == "quero aumentar meu limite para 8000"


@pytest.mark.asyncio
@pytest.mark.parametrize("texto", [
    "qual o código do banco?",
    "comprei um remédio na Drogasil",
    "tenho um script de cobrança recebido por email, é golpe?",
])
async def test_regex_nao_encerra_mensagens_bancarias_legitimas(texto):
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {"is_authenticated": True}
    ctx.actions = MagicMock()

    with patch("root_agent.application.middlewares.input_middleware._classificar_input_semantico", new_callable=AsyncMock) as mock_semantico:
        mock_semantico.return_value = NivelRisco.SEGURO
        res = await before_model_callback(ctx, _criar_user_request(texto))

    assert res is None
    assert ctx.state["is_authenticated"] is True


@pytest.mark.asyncio
async def test_classificador_semantico_nao_roda_novamente_apos_tool():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {"is_authenticated": True}
    func_resp = types.FunctionResponse(name="consultar_limite_credito", response={"result": "{}"})
    req = LlmRequest(contents=[
        types.Content(role="user", parts=[types.Part(text="qual meu limite?")]),
        types.Content(role="tool", parts=[types.Part(function_response=func_resp)]),
    ])

    with patch("root_agent.application.middlewares.input_middleware._classificar_input_semantico", new_callable=AsyncMock) as mock_semantico:
        res = await before_model_callback(ctx, req)

    assert res is None
    mock_semantico.assert_not_called()


@pytest.mark.asyncio
async def test_before_model_callback_cpf_direto_em_idle():
    ctx = MagicMock(spec=CallbackContext)
    ctx.state = {CONVERSATION_STATE_KEY: BankingConversationState.IDLE.value}
    req = _criar_user_request("123.456.789-00")

    with patch("root_agent.application.middlewares.input_middleware._classificar_input_semantico", new_callable=AsyncMock) as mock_semantico:
        mock_semantico.return_value = NivelRisco.SEGURO
        res = await before_model_callback(ctx, req)
        assert res is not None
        assert "data de nascimento" in res.content.parts[0].text
        assert ctx.state[AUTH_CPF_TEMP_KEY] == "12345678900"
        assert ctx.state[CONVERSATION_STATE_KEY] == BankingConversationState.AGUARDANDO_DATA_NASCIMENTO
