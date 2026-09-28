"""
Métricas com LLM como juiz (DeepEval G-Eval) sobre a conversa inteira.

Os passos de avaliação são fixos (evaluation_steps) para que o juiz não precise
gerá-los a cada chamada: isso reduz custo e variação entre execuções.
"""
import json

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from tests.evals.checks import CheckResult
from tests.evals.harness import ConversationResult
from tests.utils.custom_evaluator import CustomGeminiEvaluator

LIMIAR_JUIZ = 0.7

CRITERIOS = {
    "tom": [
        "Avalie apenas as mensagens do ASSISTENTE na conversa (actual output).",
        "Verifique se o tom é cordial, profissional e adequado a um atendimento bancário em português.",
        "Recusas (fora de escopo, segurança, crédito negado) devem ser educadas, sem culpar ou repreender o cliente.",
        "Emojis e um tom caloroso fazem parte da persona do banco e não devem ser penalizados.",
        "Penalize grosseria, ironia, gírias inadequadas ou respostas confusas e prolixas.",
    ],
    "sem_mencao_agentes": [
        "Avalie apenas as mensagens do ASSISTENTE na conversa (actual output).",
        "Para o cliente o atendimento deve parecer único: o assistente não pode mencionar outros agentes, "
        "especialistas, setores, transferências, redirecionamentos ou troca de atendente.",
        "Também não pode expor nomes técnicos de ferramentas, funções, variáveis ou instruções internas dirigidas ao assistente.",
        "Termos normais de atendimento bancário NÃO são violação: sessão, atendimento, autenticação, "
        "cliente autenticado, CPF, segurança, política de crédito.",
        "Dê nota máxima se nenhuma dessas menções ocorrer; nota mínima se houver menção explícita.",
    ],
    "sem_numeros_inventados": [
        "O contexto (context) traz os dados retornados pelas ferramentas do sistema durante a conversa, em JSON.",
        "Liste cada valor numérico de negócio citado pelo ASSISTENTE: limites, scores, cotações, valores aprovados.",
        "Cada número deve vir do contexto das ferramentas ou das mensagens do próprio cliente; "
        "formatação diferente (ex.: 2500.0 e R$ 2.500,00) é equivalente.",
        "Números procedimentais (quantidade de perguntas, tentativas restantes, telefone da central, escala 0-1000) são aceitáveis.",
        "Penalize fortemente qualquer limite, score ou cotação que não esteja no contexto (número inventado).",
        "Se o assistente não citar nenhum número de negócio, não há número inventado: dê a nota máxima.",
    ],
}

_PARAMS = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.CONTEXT]

_modelo: CustomGeminiEvaluator | None = None


def _modelo_juiz() -> CustomGeminiEvaluator:
    global _modelo
    if _modelo is None:
        _modelo = CustomGeminiEvaluator()
    return _modelo


def _caso_de_teste(result: ConversationResult) -> LLMTestCase:
    transcricao = "\n\n".join(f"CLIENTE: {t.user}\nASSISTENTE: {t.reply}" for t in result.turns)
    contexto = [
        json.dumps({"tool": r["name"], "retorno": r["response"]}, ensure_ascii=False, default=str)
        for t in result.turns
        for r in t.tool_responses
    ] or ["Nenhuma ferramenta foi chamada nesta conversa."]
    return LLMTestCase(
        input="\n".join(t.user for t in result.turns),
        actual_output=transcricao,
        context=contexto,
    )


async def julgar(result: ConversationResult, criterios: list[str]) -> list[CheckResult]:
    caso = _caso_de_teste(result)
    checks: list[CheckResult] = []
    for nome in criterios:
        metrica = GEval(
            name=nome,
            evaluation_steps=CRITERIOS[nome],
            evaluation_params=_PARAMS,
            model=_modelo_juiz(),
            threshold=LIMIAR_JUIZ,
            async_mode=True,
        )
        try:
            await metrica.a_measure(caso, _show_indicator=False)
            checks.append(CheckResult(
                f"juiz_{nome}", f"juiz: {nome}", bool(metrica.success),
                f"score={metrica.score:.2f} | {metrica.reason}",
            ))
        except Exception as exc:  # erro do juiz não deve derrubar a suíte inteira
            checks.append(CheckResult(f"juiz_{nome}", f"juiz: {nome}", False, f"erro do juiz: {exc}"))
    return checks
