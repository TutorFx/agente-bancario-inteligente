import uuid
import json
import ast
import re
import httpx
import streamlit as st

st.set_page_config(page_title="Banco Ágil", page_icon="🏦", layout="centered")

st.title("🏦 Banco Ágil")
st.caption("Atendimento digital: limite de crédito, score e câmbio.")

AVATARES = {"user": "🙂", "assistant": "🏦"}
MENSAGEM_ERRO_GENERICA = (
    "😕 Tivemos uma instabilidade ao processar sua mensagem. "
    "Por favor, tente novamente em alguns instantes."
)

AGENT_LABELS = {
    "agente_triagem": "Agente de Triagem",
    "agente_credito": "Agente de Crédito",
    "agente_entrevista_credito": "Agente de Entrevista",
    "agente_cambio": "Agente de Câmbio",
    "agente_fora_escopo": "Agente Fora de Escopo",
}

DEFAULT_USER_ID = "user_simulacao"

def extrair_info_cliente(cliente_raw) -> dict | None:
    """Extrai informações do cliente a partir de diferentes formatos retornados pelo ADK."""
    if not cliente_raw:
        return None
    if isinstance(cliente_raw, dict):
        if "cliente" in cliente_raw and isinstance(cliente_raw["cliente"], dict):
            return cliente_raw["cliente"]
        if "result" in cliente_raw:
            return extrair_info_cliente(cliente_raw["result"])
        return cliente_raw
    if isinstance(cliente_raw, str):
        try:
            parsed = json.loads(cliente_raw)
            res = extrair_info_cliente(parsed)
            if res:
                return res
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(cliente_raw)
            res = extrair_info_cliente(parsed)
            if res:
                return res
        except Exception:
            pass
        m = re.search(r'["\']nome["\']\s*:\s*["\']([^"\']+)["\']', cliente_raw)
        if m:
            return {"nome": m.group(1)}
    return None

def limpar_mensagens_transferencia(texto: str) -> str:
    """
    Remove mensagens internas de transferência ou menções técnicas de agentes,
    assegurando a persona unificada do Banco Ágil (transição implícita).
    """
    if not texto:
        return ""
    
    padroes = [
        r"(?i)(?:transferindo|encaminhando|redirecionando)\s+(?:o\s+)?(?:seu\s+)?(?:atendimento|contato)?\s*(?:para\s+o?\s*(?:agente|sub-agente|especialista)?[^.\n]*)?[.!\s]*",
        r"(?i)vou\s+(?:te\s+|lhe\s+)?transferir\s+para\s+[^.\n]*[.!\s]*",
        r"(?i)aguarde\s+(?:um\s+instante|um\s+momento)\s*(?:enquanto\s+transfiro)?[^.\n]*[.!\s]*",
        r"(?i)transfer_to_agent\([^)]*\)",
        r"(?i)\b(?:agente_triagem|agente_credito|agente_entrevista_credito|agente_cambio|agente_fora_escopo)\b",
    ]
    
    resultado = texto
    for p in padroes:
        resultado = re.sub(p, "", resultado)
    
    resultado = re.sub(r"^[\s.\-,!?:;]+", "", resultado)
    resultado = re.sub(r"\n\s*\n", "\n\n", resultado).strip()
    return resultado or texto.strip()

def limpar_chaves_autenticacao():
    """Limpa todas as chaves de autenticação do st.session_state."""
    auth_keys = [
        "cliente_autenticado",
        "cpf",
        "nome",
        "tentativas_login",
        "is_authenticated",
        "auth_cpf_temp",
        "auth_data_temp",
        "auth_tentativas",
        "conv_state",
        "cliente_nome",
    ]
    for key in auth_keys:
        st.session_state.pop(key, None)
    st.session_state.is_authenticated = False
    st.session_state.cliente_nome = None
    st.session_state.active_agent = "agente_triagem"

# Inicialização de variáveis de sessão
if "session_id" not in st.session_state:
    st.session_state.session_id = f"sess_{uuid.uuid4().hex[:8]}"

if "user_id" not in st.session_state:
    st.session_state.user_id = DEFAULT_USER_ID

if "active_agent" not in st.session_state:
    st.session_state.active_agent = "agente_triagem"

if "is_authenticated" not in st.session_state:
    st.session_state.is_authenticated = False

if "cliente_nome" not in st.session_state:
    st.session_state.cliente_nome = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# Barra lateral com configurações e telemetria de debug
with st.sidebar:
    st.header("⚙️ Configurações de Teste")
    api_url = st.text_input("URL da API / SDK", value="http://127.0.0.1:8085")
    st.text(f"Session ID: {st.session_state.session_id}")
    user_id = st.session_state.user_id

    st.divider()

    st.subheader("🕵️ Telemetria & Debug")
    agent_name = AGENT_LABELS.get(
        st.session_state.active_agent,
        st.session_state.active_agent.replace("_", " ").title()
    )
    st.markdown(f"**Agente Ativo:** `{agent_name}`")

    if st.session_state.is_authenticated and st.session_state.cliente_nome:
        st.markdown(f"**Status de Autenticação:**\n\n🟢 **Autenticado (Cliente: {st.session_state.cliente_nome})**")
    elif st.session_state.is_authenticated:
        st.markdown("**Status de Autenticação:**\n\n🟢 **Autenticado**")
    else:
        st.markdown("**Status de Autenticação:**\n\n🔴 **Não Autenticado**")

    if st.session_state.get("ultimo_erro"):
        st.caption("Último erro técnico:")
        st.code(st.session_state.ultimo_erro, language=None)

    st.divider()

    if st.button("🔄 Nova Sessão / Limpar Conversa", use_container_width=True):
        base_url = api_url.rstrip("/")
        try:
            httpx.delete(
                f"{base_url}/apps/root_agent/users/{user_id}/sessions/{st.session_state.session_id}",
                timeout=5.0
            )
        except Exception:
            pass
        limpar_chaves_autenticacao()
        st.session_state.pop("ultimo_erro", None)
        st.session_state.session_id = f"sess_{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.rerun()

# Exibe o histórico de mensagens preservado
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar=AVATARES.get(msg["role"])):
        st.markdown(msg["content"])

# Entrada de nova mensagem do usuário
if prompt := st.chat_input("Digite sua mensagem..."):
    # Renderiza e salva mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARES["user"]):
        st.markdown(prompt)

    # Envio para o ADK com feedback visual
    with st.chat_message("assistant", avatar=AVATARES["assistant"]):
        with st.spinner("Processando solicitação..."):
            base_url = api_url.rstrip("/")
            payload = {
                "appName": "root_agent",
                "userId": user_id,
                "sessionId": st.session_state.session_id,
                "newMessage": {
                    "parts": [{"text": prompt}]
                }
            }
            try:
                # Garante que a sessão exista no ADK antes de disparar o /run
                sess_url = f"{base_url}/apps/root_agent/users/{user_id}/sessions/{st.session_state.session_id}"
                check_sess = httpx.get(sess_url, timeout=10.0)
                if check_sess.status_code == 404:
                    create_url = f"{base_url}/apps/root_agent/users/{user_id}/sessions"
                    httpx.post(create_url, json={"sessionId": st.session_state.session_id}, timeout=10.0).raise_for_status()

                response = httpx.post(f"{base_url}/run", json=payload, timeout=30.0)
                if response.status_code == 200:
                    data = response.json()
                    bot_text = ""
                    encerrou_sessao = False

                    if isinstance(data, list) and len(data) > 0:
                        # 1. Atualiza telemetria de agente ativo e encerramento
                        for ev in data:
                            actions = ev.get("actions") or {}
                            if isinstance(actions, dict):
                                if actions.get("transferToAgent"):
                                    st.session_state.active_agent = actions["transferToAgent"]
                                state_delta = actions.get("stateDelta") or {}
                                if isinstance(state_delta, dict):
                                    if state_delta.get("is_authenticated") is True:
                                        st.session_state.is_authenticated = True
                                        c_info = extrair_info_cliente(state_delta.get("cliente_autenticado"))
                                        if c_info and c_info.get("nome"):
                                            st.session_state.cliente_nome = c_info.get("nome")
                                    elif state_delta.get("is_authenticated") is False:
                                        st.session_state.is_authenticated = False
                                        st.session_state.cliente_nome = None

                            author = ev.get("author")
                            if author and author not in ("user", "system"):
                                st.session_state.active_agent = author

                            parts = ev.get("content", {}).get("parts", []) if isinstance(ev.get("content"), dict) else []
                            for p in parts:
                                fn_call = p.get("functionCall") or p.get("function_call")
                                fn_resp = p.get("functionResponse") or p.get("function_response")
                                if (fn_call and fn_call.get("name") == "encerrar_atendimento") or \
                                   (fn_resp and fn_resp.get("name") == "encerrar_atendimento"):
                                    encerrou_sessao = True

                        # 2. Sincroniza estado da sessão no backend para garantir autenticação e nome atualizados
                        try:
                            s_res = httpx.get(sess_url, timeout=5.0)
                            if s_res.status_code == 200:
                                b_state = s_res.json().get("state", {})
                                if b_state.get("is_authenticated"):
                                    st.session_state.is_authenticated = True
                                    c_info = extrair_info_cliente(b_state.get("cliente_autenticado"))
                                    if c_info and c_info.get("nome"):
                                        st.session_state.cliente_nome = c_info.get("nome")
                                elif b_state.get("is_authenticated") is False:
                                    st.session_state.is_authenticated = False
                                    st.session_state.cliente_nome = None
                        except Exception:
                            pass

                        # 3. Extração da resposta textual com persona unificada (última resposta do modelo)
                        for ev in reversed(data):
                            if ev.get("author") == st.session_state.active_agent:
                                p_list = ev.get("content", {}).get("parts", []) if isinstance(ev.get("content"), dict) else []
                                t = "".join(p.get("text", "") for p in p_list if isinstance(p, dict) and p.get("text"))
                                if t:
                                    bot_text = t
                                    break

                        if not bot_text:
                            for ev in reversed(data):
                                p_list = ev.get("content", {}).get("parts", []) if isinstance(ev.get("content"), dict) else []
                                t = "".join(p.get("text", "") for p in p_list if isinstance(p, dict) and p.get("text"))
                                if t:
                                    bot_text = t
                                    break

                    # Limpa mensagens técnicas ou de transferência para persona unificada
                    bot_text = limpar_mensagens_transferencia(bot_text)

                    if not bot_text:
                        bot_text = "*(Resposta sem conteúdo textual recebida)*"

                    # Detecção adicional de encerramento via texto
                    text_lower = bot_text.lower()
                    if "atendimento foi encerrado" in text_lower or \
                       "atendimento encerrado" in text_lower or \
                       "0800 123 4567" in text_lower or \
                       "sessão finalizada" in text_lower:
                        encerrou_sessao = True

                    if encerrou_sessao:
                        limpar_chaves_autenticacao()
                        try:
                            httpx.delete(
                                f"{base_url}/apps/root_agent/users/{user_id}/sessions/{st.session_state.session_id}",
                                timeout=5.0
                            )
                        except Exception:
                            pass
                        st.session_state.session_id = f"sess_{uuid.uuid4().hex[:8]}"

                    st.session_state.messages.append({"role": "assistant", "content": bot_text})
                    st.rerun()
                else:
                    # Detalhes técnicos ficam só na sidebar de debug; o chat recebe mensagem amigável
                    st.session_state.ultimo_erro = f"HTTP {response.status_code}: {response.text[:500]}"
                    st.session_state.messages.append({"role": "assistant", "content": MENSAGEM_ERRO_GENERICA})
                    st.rerun()
            except Exception as e:
                st.session_state.ultimo_erro = f"Falha de conexão com a API: {e}"
                st.session_state.messages.append({"role": "assistant", "content": MENSAGEM_ERRO_GENERICA})
                st.rerun()