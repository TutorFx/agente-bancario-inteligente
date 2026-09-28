"""
Mascaramento de credenciais de login (CPF e data de nascimento) em texto livre.

Cobre todo formato que o login aceita (o CPF é qualquer mensagem com 11 dígitos, pois
`guardrails.validar_formato_cpf` ignora espaços, pontos, traços e barras) e as formas
comuns de escrever datas. Valores monetários da entrevista de crédito (ex: "R$ 8.000,00",
"8000") não são mascarados, para não esconder dos agentes as respostas do cliente.
"""
import re

MASCARA_CPF = "[CPF omitido]"
MASCARA_DATA = "[data omitida]"

_MESES = (
    r"(?:janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
    r"|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?"
)
_SEPARADOR_DATA = r"\s?[/.\-]\s?"

_REGEX_DATAS = (
    # DD/MM/AAAA, DD-MM-AAAA, DD.MM.AAAA (e separadores misturados); também D/M/AA
    re.compile(rf"(?<!\d)\d{{1,2}}{_SEPARADOR_DATA}\d{{1,2}}{_SEPARADOR_DATA}(?:\d{{4}}|\d{{2}})(?!\d)"),
    # ISO: AAAA-MM-DD (ou AAAA/MM/DD)
    re.compile(rf"(?<!\d)\d{{4}}{_SEPARADOR_DATA}\d{{1,2}}{_SEPARADOR_DATA}\d{{1,2}}(?!\d)"),
    # Por extenso: "15 de março de 1985", "1º de mar. de 1985", "15/mar/1985"
    re.compile(
        rf"(?i)(?<!\d)\d{{1,2}}[ºo°]?(?:\s+de\s+|\s+|\s*[/.\-]\s*){_MESES}(?:\s+de\s+|\s+|\s*[/.\-]\s*)\d{{4}}(?!\d)"
    ),
)

# Sequência de dígitos unidos só por separadores (espaço, ponto, traço, barra): com
# exatamente 11 dígitos é um CPF em qualquer formatação que o login aceita.
_REGEX_SEQUENCIA_NUMERICA = re.compile(r"(?<!\d)\d(?:[\s.\-/]*\d)*")
# CPF no formato usual dentro de uma sequência mais longa (ex: "12345678900 0001")
_REGEX_CPF_USUAL = re.compile(r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[\-\s]?\d{2}(?!\d)")
_REGEX_PREFIXO_MOEDA = re.compile(r"R\$\s*$")
_DIGITOS_CPF = 11


def _eh_valor_monetario(match: re.Match) -> bool:
    inicio = match.start()
    return bool(_REGEX_PREFIXO_MOEDA.search(match.string[max(0, inicio - 4):inicio]))


def _mascarar_sequencia(match: re.Match) -> str:
    trecho = match.group(0)
    if _eh_valor_monetario(match):
        return trecho
    if sum(c.isdigit() for c in trecho) == _DIGITOS_CPF:
        return MASCARA_CPF
    return _REGEX_CPF_USUAL.sub(MASCARA_CPF, trecho)


def mascarar_pii(texto: str) -> str:
    """Substitui CPFs e datas do texto por marcadores; o restante fica intacto."""
    if not texto:
        return texto
    # Datas primeiro: "123.456.789-00 15/03/1985" formaria uma única sequência de 19 dígitos
    for regex in _REGEX_DATAS:
        texto = regex.sub(MASCARA_DATA, texto)
    return _REGEX_SEQUENCIA_NUMERICA.sub(_mascarar_sequencia, texto)
