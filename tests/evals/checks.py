"""
Métricas determinísticas calculadas sobre os eventos do ADK de uma conversa.

Cada verificação produz um CheckResult com a métrica à qual pertence, para que o
relatório agregue taxas de acerto por métrica (ex.: roteamento, ferramentas) além
de por cenário e por categoria.
"""
import re
from dataclasses import dataclass
from typing import Any

from tests.evals.harness import ConversationResult, TurnResult

TRIAGEM = "agente_triagem"

BUSINESS_TOOLS = frozenset({
    "consultar_limite_credito",
    "solicitar_aumento_limite",
    "calcular_e_atualizar_score",
    "consultar_cotacao",
})

# Nada do que é interno ao sistema pode chegar ao cliente: nomes de tools/agentes,
# instruções devolvidas por tools e menções explícitas à troca de atendente.
_REGEX_VAZAMENTO = re.compile(
    r"(?i)("
    r"\bagente_[a-z_]+|transfer_to_agent|autenticar_cliente|encerrar_atendimento"
    r"|consultar_limite|solicitar_aumento_limite|calcular_e_atualizar_score|consultar_cotacao"
    r"|a[çc][ãa]o de encerramento acionada|informe ao cliente"
    r"|\btransferi(r|ndo|rei|do)\b|redirecion\w+"
    r"|agente (de|da|do) (cr[ée]dito|c[âa]mbio|entrevista|triagem)"
    r")"
)

_TOLERANCIA_NUMERICA = 0.01


@dataclass
class CheckResult:
    metric: str
    name: str
    passed: bool
    detail: str = ""


def _lista(valor: Any) -> list:
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _valor_confere(esperado: Any, obtido: Any) -> bool:
    if isinstance(esperado, list):
        return any(_valor_confere(e, obtido) for e in esperado)
    if isinstance(esperado, bool) or isinstance(obtido, bool):
        return esperado == obtido
    if isinstance(esperado, (int, float)):
        try:
            return abs(float(obtido) - float(esperado)) <= _TOLERANCIA_NUMERICA
        except (TypeError, ValueError):
            return False
    return str(esperado).strip().lower() == str(obtido).strip().lower()


def _args_conferem(esperados: dict, obtidos: dict) -> bool:
    return all(k in obtidos and _valor_confere(v, obtidos[k]) for k, v in esperados.items())


def _checar_turno(i: int, turn: TurnResult, spec: dict) -> list[CheckResult]:
    rotulo = f"turno {i + 1}"
    results: list[CheckResult] = []
    chamadas = [c.name for c in turn.tool_calls]

    if "agent" in spec:
        esperados = _lista(spec["agent"])
        results.append(CheckResult(
            "roteamento", f"{rotulo}: agente", turn.agent in esperados,
            f"esperado {esperados}, obtido {turn.agent!r}",
        ))

    for esperado in spec.get("tools", []):
        candidatos = [c for c in turn.tool_calls if c.name == esperado["name"]]
        ok = any(_args_conferem(esperado.get("args", {}), c.args) for c in candidatos)
        results.append(CheckResult(
            "ferramentas", f"{rotulo}: chama {esperado['name']}", ok,
            f"esperado args {esperado.get('args', {})}, chamadas {[(c.name, c.args) for c in turn.tool_calls]}",
        ))

    proibidas = set(spec.get("forbidden_tools", []))
    if spec.get("no_business_tools"):
        proibidas |= BUSINESS_TOOLS
    if proibidas:
        indevidas = sorted(proibidas.intersection(chamadas))
        # A chamada conta como falha de comportamento mesmo se o auth_guard a barrou;
        # o detalhe diferencia "tentou e foi bloqueada" de "executou"
        bloqueadas = sorted({
            r["name"] for r in turn.tool_responses
            if r["name"] in indevidas and isinstance(r["response"], dict) and r["response"].get("erro") == "nao_autenticado"
        })
        detalhe = f"chamou {indevidas}" if indevidas else ""
        if bloqueadas:
            detalhe += f" (bloqueada pelo auth_guard: {bloqueadas})"
        results.append(CheckResult(
            "ferramentas", f"{rotulo}: não chama {sorted(proibidas)}", not indevidas, detalhe,
        ))

    if spec.get("no_specialist_transfer"):
        # Voltar à triagem é legítimo (é o que o encerramento de sessão faz); o que não pode
        # é o turno chegar a um agente especializado
        especialistas = [t for t in turn.transfers if t != TRIAGEM]
        results.append(CheckResult(
            "roteamento", f"{rotulo}: sem transferência a especialista", not especialistas,
            f"transferiu para {especialistas}" if especialistas else "",
        ))

    for padrao in _lista(spec.get("reply_matches")):
        results.append(CheckResult(
            "resposta", f"{rotulo}: contém /{padrao}/",
            re.search(padrao, turn.reply, re.IGNORECASE | re.DOTALL) is not None,
            turn.reply[:300],
        ))
    for padrao in _lista(spec.get("reply_not_matches")):
        achado = re.search(padrao, turn.reply, re.IGNORECASE | re.DOTALL)
        results.append(CheckResult(
            "resposta", f"{rotulo}: não contém /{padrao}/", achado is None,
            f"encontrado {achado.group(0)!r}" if achado else "",
        ))

    vazamento = _REGEX_VAZAMENTO.search(turn.reply)
    results.append(CheckResult(
        "transicao_invisivel", f"{rotulo}: sem vazamento interno", vazamento is None,
        f"encontrado {vazamento.group(0)!r}" if vazamento else "",
    ))
    if not turn.reply.strip():
        results.append(CheckResult("resposta", f"{rotulo}: resposta não vazia", False, "resposta vazia"))
    return results


def _numero_na_resposta(valor: float, texto: str) -> bool:
    """Procura o valor no texto aceitando formatos BR (1.234,56) e US (1234.56)."""
    for bruto in re.findall(r"\d[\d.,]*", texto):
        candidatos = {bruto.replace(".", "").replace(",", "."), bruto.replace(",", "")}
        for c in candidatos:
            try:
                if abs(float(c.rstrip(".")) - float(valor)) <= _TOLERANCIA_NUMERICA:
                    return True
            except ValueError:
                continue
    return False


def _checar_final(result: ConversationResult, spec: dict, clientes: dict) -> list[CheckResult]:
    results: list[CheckResult] = []

    for chave, esperado in (spec.get("final_state") or {}).items():
        obtido = result.final_state.get(chave)
        results.append(CheckResult(
            "estado", f"estado final: {chave} == {esperado!r}", _valor_confere(esperado, obtido),
            f"obtido {obtido!r}",
        ))

    for alias, regras in (spec.get("persisted") or {}).items():
        original = clientes[alias]
        linha = result.clientes.get(original["cpf"], {})
        if "score" in regras:
            esperado = regras["score"]
            obtido = int(linha.get("score_credito", -1))
            if esperado == "from_tool":
                scores = [r.get("novo_score") for r in result.tool_responses("calcular_e_atualizar_score") if isinstance(r, dict)]
                ok = bool(scores) and obtido == scores[-1]
                detalhe = f"persistido {obtido}, calculado pela tool {scores}"
            else:
                esperado = original["score_credito"] if esperado == "unchanged" else esperado
                ok = obtido == int(esperado)
                detalhe = f"persistido {obtido}, esperado {esperado}"
            results.append(CheckResult("estado", f"score persistido de {alias}", ok, detalhe))
        if "limite" in regras:
            esperado = original["limite_credito"] if regras["limite"] == "unchanged" else regras["limite"]
            obtido = float(linha.get("limite_credito", -1))
            results.append(CheckResult(
                "estado", f"limite persistido de {alias}", abs(obtido - float(esperado)) <= _TOLERANCIA_NUMERICA,
                f"persistido {obtido}, esperado {esperado}",
            ))

    # Fidelidade às tools: o número devolvido pela tool precisa aparecer na resposta ao cliente
    for regra in spec.get("reply_includes_tool_field", []):
        respostas = [r for r in result.tool_responses(regra["tool"]) if isinstance(r, dict)]
        valores = [r.get(regra["field"]) for r in respostas if r.get(regra["field"]) is not None]
        texto = "\n".join(t.reply for t in result.turns)
        ok = bool(valores) and _numero_na_resposta(float(valores[-1]), texto)
        results.append(CheckResult(
            "fidelidade_tools", f"resposta cita {regra['tool']}.{regra['field']}", ok,
            f"valores da tool {valores}",
        ))
    return results


def avaliar(result: ConversationResult, scenario: dict, clientes: dict) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for i, (turn, spec) in enumerate(zip(result.turns, scenario["turns"])):
        checks.extend(_checar_turno(i, turn, spec))
    checks.extend(_checar_final(result, scenario, clientes))
    return checks
