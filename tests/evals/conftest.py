import logging
import os
import time

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

import pytest  # noqa: E402

from tests.evals import telemetria  # noqa: E402
from tests.evals.report import report  # noqa: E402


def _somente_evals(config) -> bool:
    expr = (config.option.markexpr or "").replace(" ", "")
    return "eval" in expr and "noteval" not in expr


def pytest_configure(config):
    # O limiar de cobertura (pytest.ini) vale para a suíte de código; numa execução só de
    # evals a cobertura parcial não é sinal de regressão, e a régua passa a ser os limiares do dataset.
    if _somente_evals(config):
        if getattr(config.option, "numprocesses", None):
            # O relatório é agregado em memória no processo e o harness troca atributos globais
            # do adapter: as conversas rodam em série; o ritmo se ajusta com EVAL_PAUSA_SEGUNDOS
            raise pytest.UsageError("a suíte de evals roda em série: não use -n (pytest-xdist)")
        telemetria.instalar()
        report.inicio = time.monotonic()
        cov = config.pluginmanager.getplugin("_cov")
        if cov is not None:
            cov.options.cov_fail_under = None
        # Logs dos middlewares/adapter poluiriam as falhas; as transcrições vão para o relatório
        logging.disable(logging.ERROR)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not report.runs:
        return
    consumo = telemetria.contador.instantaneo()
    if consumo.chamadas:
        report.llm = consumo.como_dict()
    caminho = report.write()
    tr = terminalreporter
    tr.section("Avaliação de agentes")
    tr.write_line(f"Modelo: {report.model} | execuções por cenário: {report.runs_per_scenario}")
    tr.write_line("")
    tr.write_line(f"{'Categoria':<22}{'Execuções':>10}{'Acerto':>10}{'Limiar':>9}")
    for cat, info in report.por_categoria().items():
        lim = report.limiar("categorias", cat)
        tr.write_line(f"{cat:<22}{info['runs']:>10}{info['rate']:>10.1%}{'' if lim is None else f'{lim:.0%}':>9}")
    tr.write_line("")
    tr.write_line(f"{'Métrica':<30}{'Verificações':>14}{'Acerto':>10}{'Limiar':>9}")
    for m, info in report.por_metrica().items():
        lim = report.limiar("metricas", m)
        tr.write_line(f"{m:<30}{info['passed']:>7}/{info['total']:<6}{info['rate']:>10.1%}{'' if lim is None else f'{lim:.0%}':>9}")
    tr.write_line("")
    for v in report.violacoes():
        tr.write_line(f"LIMIAR NÃO ATINGIDO: {v}", red=True)
    infra = report.infraestrutura()
    tr.write_line(
        f"Infraestrutura: {infra['conversas_com_incidente']} conversa(s) com incidente {infra['incidentes'] or ''}, "
        f"{infra['execucoes_perdidas']} execução(ões) perdida(s), {infra['erros_juiz']} erro(s) do juiz"
    )
    if report.llm:
        tr.write_line(
            f"LLM: {report.llm['chamadas']} chamadas, {report.llm['tokens_entrada']} tokens de entrada, "
            f"{report.llm['tokens_saida']} de saída | tempo total: {report.duracao_s():.0f} s"
        )
    tr.write_line(f"Relatório completo: {caminho} (transcrições em {caminho.with_suffix('.json')})")
    if report.deve_publicar():
        tr.write_line("Resumo publicável atualizado: tests/evals/results/RESULTS.md")
    else:
        tr.write_line("Execução parcial: tests/evals/results/RESULTS.md não foi alterado (EVAL_PUBLICAR=1 força)")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if report.runs and report.violacoes() and session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
