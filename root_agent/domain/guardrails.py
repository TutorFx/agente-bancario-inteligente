import re
from datetime import datetime

from root_agent.domain.value_objects import CPF

MOEDAS_SUPORTADAS = {"USD", "EUR", "GBP", "ARS", "JPY", "CHF"}  # códigos com taxa disponível em open.er-api.com/v6/latest/BRL
MAX_TENTATIVAS_AUTH = 3
TETO_SCORE_DESEMPREGADO = 600

def limpar_cpf(cpf: str) -> str:
    return re.sub(r'\D', '', cpf)

def validar_formato_cpf(cpf: str) -> bool:
    cpf_vo = CPF(limpar_cpf(cpf))
    if not cpf_vo.possui_tamanho_correto():
        return False
    if cpf_vo.possui_digitos_repetidos():
        return False
    return True

def validar_formato_data(data: str) -> bool:
    """Valida DD/MM/AAAA e se é uma data real."""
    data_limpa = data.strip().replace('-', '/')
    match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', data_limpa)
    if not match:
        return False
    try:
        datetime.strptime(match.group(1), "%d/%m/%Y")
        return True
    except ValueError:
        return False

def extrair_data(texto: str) -> str | None:
    """Extrai uma data válida DD/MM/AAAA de um texto."""
    data_limpa = texto.strip().replace('-', '/')
    match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', data_limpa)
    if match and validar_formato_data(match.group(1)):
        return match.group(1)
    return None

def validar_moeda(moeda: str) -> bool:
    return moeda.upper().strip() in MOEDAS_SUPORTADAS

def validar_aumento_limite(limite_atual: float, novo_limite: float, limite_maximo: float | None = None) -> tuple[bool, str]:
    """Regra de negócio única para decisão de aumento de limite (usada pelo BancoAgilAdapter)."""
    if novo_limite <= limite_atual:
        return False, "O novo limite deve ser maior que o limite atual."
    if limite_maximo is not None and novo_limite > limite_maximo:
        return False, (
            "Score insuficiente para o valor solicitado: excede o limite máximo permitido "
            f"para o seu score de crédito (R$ {limite_maximo:,.2f})."
        )
    return True, ""

def calcular_score_detalhado(entrevista: dict) -> tuple[int, dict]:
    """
    Score ponderado por categoria, cada uma com teto próprio (0 a 1000):
    - Renda mensal:          até 300 pts (escala de raiz quadrada até teto de R$ 30.000)
    - Empregabilidade:       até 200 pts (formal/CLT=200, autônomo/freelancer=100, desempregado=0)
    - Comprometimento:       até 200 pts (relação despesas/renda, quanto menor melhor)
    - Dependentes:           até 150 pts (0=150, 1=120, 2=90, 3+=50)
    - Dívidas ativas:        até 150 pts (sem dívidas=150, com dívidas=0)

    A soma dos tetos máximos individuais é exatamente 1.000 pontos.

    Regras de borda:
    - Renda <= 0: comprometimento vale 0 pts (não há renda para comprometer; sem
      essa regra, renda zero e despesa zero concediam os 200 pts cheios).
    - Desempregado: score final limitado a TETO_SCORE_DESEMPREGADO (600), mantendo o
      cliente fora das faixas de limite >= 700 mesmo com renda declarada alta. O corte
      aparece em `ajuste_teto_desemprego` (valor <= 0), de modo que a soma das parcelas
      com o ajuste sempre bate com o score final.
    """
    # 1. Renda (max 300 pts)
    renda_bruta = max(0.0, float(entrevista.get("renda_mensal", 0) or 0))
    renda_limitada = min(renda_bruta, 30000.0)
    parcela_renda = int((renda_limitada / 30000.0) ** 0.5 * 300)

    # 2. Emprego (max 200 pts)
    tipo_emprego = str(entrevista.get("tipo_emprego", "desempregado") or "").strip().lower()
    if tipo_emprego in ("formal", "clt", "carteira assinada"):
        parcela_emprego = 200
    elif tipo_emprego in ("autonomo", "autônomo", "freelancer", "pj", "autonomo/freelancer"):
        parcela_emprego = 100
    else:
        parcela_emprego = 0

    # 3. Comprometimento Financeiro (max 200 pts)
    despesas = max(0.0, float(entrevista.get("despesas_mensais", 0) or 0))
    if renda_bruta <= 0:
        parcela_comprometimento = 0
    else:
        comprometimento = despesas / renda_bruta
        parcela_comprometimento = max(0, min(200, int((1.0 - comprometimento) * 200)))

    # 4. Dependentes (max 150 pts)
    num_dep = max(0, int(entrevista.get("num_dependentes", 0) or 0))
    dep_map = {0: 150, 1: 120, 2: 90}
    parcela_dependentes = dep_map.get(num_dep, 50)

    # 5. Dívidas (max 150 pts)
    # Conservador: só pontua quando a ausência de dívidas é explícita; valores
    # ambíguos (ex: "tenho sim", "talvez") são tratados como dívida ativa.
    dividas_raw = entrevista.get("tem_dividas", True)
    if isinstance(dividas_raw, str):
        tem_dividas = dividas_raw.strip().lower() not in ("nao", "não", "n", "false", "0", "nao tenho", "não tenho")
    else:
        tem_dividas = bool(dividas_raw)
    parcela_dividas = 0 if tem_dividas else 150

    score_bruto = (
        parcela_renda
        + parcela_emprego
        + parcela_comprometimento
        + parcela_dependentes
        + parcela_dividas
    )

    # 6. Teto para desempregado: renda declarada sem vínculo não sustenta faixas altas
    teto = 1000 if parcela_emprego > 0 else TETO_SCORE_DESEMPREGADO
    score_final = max(0, min(teto, score_bruto))

    detalhes = {
        "parcela_renda": parcela_renda,
        "parcela_emprego": parcela_emprego,
        "parcela_comprometimento": parcela_comprometimento,
        "parcela_dependentes": parcela_dependentes,
        "parcela_dividas": parcela_dividas,
        "ajuste_teto_desemprego": score_final - score_bruto,
    }

    return score_final, detalhes

