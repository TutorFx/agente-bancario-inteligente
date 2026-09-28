import csv, os
from datetime import datetime, timezone
from filelock import FileLock, Timeout
from root_agent.domain.models import ClienteDTO, SolicitacaoLimiteDTO, CotacaoDTO, RegraScoreLimiteDTO
from root_agent.domain.guardrails import limpar_cpf, validar_aumento_limite
from root_agent.utils import get_logger

logger = get_logger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
CSV_PATH = os.path.join(DATA_DIR, "clientes.csv")
SCORE_LIMITE_PATH = os.path.join(DATA_DIR, "score_limite.csv")
SOLICITACOES_LIMITE_PATH = os.path.join(DATA_DIR, "solicitacoes_aumento_limite.csv")

CLIENTES_LOCK_PATH = os.path.join(DATA_DIR, ".clientes.csv.lock")
SOLICITACOES_LOCK_PATH = os.path.join(DATA_DIR, ".solicitacoes_aumento_limite.csv.lock")
DEFAULT_LOCK_TIMEOUT = 10.0

class BancoAgilAdapter:

    def __init__(
        self,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
        clientes_lock_path: str | None = None,
        solicitacoes_lock_path: str | None = None
    ):
        self._lock_timeout = lock_timeout
        self._clientes_lock_path = clientes_lock_path or CLIENTES_LOCK_PATH
        self._solicitacoes_lock_path = solicitacoes_lock_path or SOLICITACOES_LOCK_PATH
        self._clientes_lock = FileLock(self._clientes_lock_path, timeout=self._lock_timeout)
        self._solicitacoes_lock = FileLock(self._solicitacoes_lock_path, timeout=self._lock_timeout)

    def _ler_clientes_csv(self) -> list[dict]:
        """Leitura direta do arquivo CSV sem acquire de lock."""
        if not os.path.exists(CSV_PATH):
            return []
        with open(CSV_PATH, newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    def _carregar_clientes(self, lock: bool = True) -> list[dict]:
        if not lock:
            return self._ler_clientes_csv()
        with self._clientes_lock:
            return self._ler_clientes_csv()

    def _salvar_clientes(self, clientes: list[dict]) -> None:
        """
        Escrita atômica via arquivo temporário + os.replace para evitar truncamento
        para 0 bytes e leituras parciais durante concorrência.
        """
        if not clientes:
            return
        tmp_path = f"{CSV_PATH}.{os.getpid()}_{id(clientes)}.tmp"
        with open(tmp_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=clientes[0].keys())
            writer.writeheader()
            writer.writerows(clientes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CSV_PATH)

    def _carregar_regras_score(self) -> list[RegraScoreLimiteDTO]:
        regras = []
        if not os.path.exists(SCORE_LIMITE_PATH):
            return regras
        with open(SCORE_LIMITE_PATH, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                regras.append(
                    RegraScoreLimiteDTO(
                        score_min=int(row["score_min"]),
                        score_max=int(row["score_max"]),
                        limite_maximo=float(row["limite_maximo"])
                    )
                )
        return regras

    def obter_limite_maximo_por_score(self, score: int) -> float:
        """Busca o limite máximo permitido com base na tabela dinâmica score_limite.csv."""
        regras = self._carregar_regras_score()
        for r in regras:
            if r.score_min <= score <= r.score_max:
                return r.limite_maximo
        return 0.0

    def _registrar_auditoria_solicitacao(
        self,
        cpf_cliente: str,
        limite_atual: float,
        novo_limite_solicitado: float,
        status_pedido: str
    ) -> None:
        """
        Registra cada solicitação de aumento de limite no arquivo
        solicitacoes_aumento_limite.csv com timestamp UTC ISO 8601 estrito (AAAA-MM-DDTHH:MM:SSZ).
        Protegido por FileLock contra duplicação de cabeçalho e interleaving.
        """
        with self._solicitacoes_lock:
            arquivo_existe = os.path.exists(SOLICITACOES_LIMITE_PATH) and os.path.getsize(SOLICITACOES_LIMITE_PATH) > 0
            fieldnames = ["cpf_cliente", "data_hora_solicitacao", "limite_atual", "novo_limite_solicitado", "status_pedido"]
            with open(SOLICITACOES_LIMITE_PATH, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not arquivo_existe:
                    writer.writeheader()

                timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                writer.writerow({
                    "cpf_cliente": cpf_cliente,
                    "data_hora_solicitacao": timestamp_utc,
                    "limite_atual": f"{limite_atual:.2f}",
                    "novo_limite_solicitado": f"{novo_limite_solicitado:.2f}",
                    "status_pedido": status_pedido
                })
                f.flush()
                os.fsync(f.fileno())

    def autenticar(self, cpf: str, data_nascimento: str) -> ClienteDTO | None:
        cpf_limpo = limpar_cpf(cpf)
        cpf_masked = f"***{cpf_limpo[-4:]}"
        logger.info("Tentativa de autenticação | cpf_masked=%s", cpf_masked)
        for row in self._carregar_clientes():
            if limpar_cpf(row["cpf"]) == cpf_limpo and row["data_nascimento"] == data_nascimento:
                logger.info("Autenticação bem-sucedida | cpf_masked=%s", cpf_masked)
                return ClienteDTO(**row)
        logger.warning("Autenticação falhou — credenciais não encontradas | cpf_masked=%s", cpf_masked)
        return None

    def buscar_cliente(self, cpf: str) -> ClienteDTO | None:
        cpf_limpo = limpar_cpf(cpf)
        for row in self._carregar_clientes():
            if limpar_cpf(row["cpf"]) == cpf_limpo:
                return ClienteDTO(**row)
        return None

    def solicitar_aumento_limite(self, cpf: str, novo_limite: float) -> SolicitacaoLimiteDTO:
        logger.info("Solicitação de aumento de limite | cpf_masked=***%s | novo_limite=%.2f", limpar_cpf(cpf)[-4:], novo_limite)
        auditoria_params = None
        resultado_dto = None

        try:
            # 1. Operação em clientes.csv sob lock exclusivo de clientes (sem locks aninhados)
            with self._clientes_lock:
                cpf_limpo = limpar_cpf(cpf)
                # Passa lock=False para evitar reentrância desnecessária de _clientes_lock
                clientes = self._carregar_clientes(lock=False)
                for row in clientes:
                    if limpar_cpf(row["cpf"]) == cpf_limpo:
                        limite_atual = float(row["limite_credito"])
                        score = int(row["score_credito"])
                        limite_maximo = self.obter_limite_maximo_por_score(score)

                        # Decisão delegada ao domínio; o adapter apenas persiste e audita
                        aprovado, motivo = validar_aumento_limite(limite_atual, novo_limite, limite_maximo)
                        if aprovado:
                            row["limite_credito"] = f"{novo_limite:.2f}"
                            self._salvar_clientes(clientes)

                        auditoria_params = (row["cpf"], limite_atual, novo_limite, "aprovado" if aprovado else "rejeitado")
                        resultado_dto = SolicitacaoLimiteDTO(
                            aprovado=aprovado,
                            motivo=motivo or "Aprovado de acordo com a política de crédito.",
                            limite_anterior=limite_atual,
                            limite_novo=novo_limite if aprovado else None,
                            limite_maximo_permitido=limite_maximo
                        )
                        break

                if resultado_dto is None:
                    resultado_dto = SolicitacaoLimiteDTO(
                        aprovado=False,
                        motivo="Cliente não encontrado",
                        limite_anterior=0.0,
                        limite_novo=None,
                        limite_maximo_permitido=0.0
                    )

            # 2. Registro de auditoria desacoplado: executado FORA de _clientes_lock
            if auditoria_params is not None:
                self._registrar_auditoria_solicitacao(
                    cpf_cliente=auditoria_params[0],
                    limite_atual=auditoria_params[1],
                    novo_limite_solicitado=auditoria_params[2],
                    status_pedido=auditoria_params[3]
                )

            return resultado_dto

        except Timeout:
            logger.error("FileLock timeout ao processar aumento de limite | cpf_masked=***%s", limpar_cpf(cpf)[-4:])
            return SolicitacaoLimiteDTO(
                aprovado=False,
                motivo="Sistema temporariamente ocupado. Por favor, tente novamente em alguns instantes.",
                limite_anterior=0.0,
                limite_novo=None,
                limite_maximo_permitido=0.0
            )

    def atualizar_score(self, cpf: str, novo_score: int) -> bool:
        """Persiste o novo score em clientes.csv com proteção de concorrência."""
        cpf_masked = f"***{limpar_cpf(cpf)[-4:]}"
        logger.info("Atualizando score | cpf_masked=%s | novo_score=%d", cpf_masked, novo_score)
        try:
            with self._clientes_lock:
                clientes = self._carregar_clientes(lock=False)
                for row in clientes:
                    if limpar_cpf(row["cpf"]) == limpar_cpf(cpf):
                        row["score_credito"] = str(novo_score)
                        self._salvar_clientes(clientes)
                        logger.info("Score atualizado com sucesso | cpf_masked=%s | novo_score=%d", cpf_masked, novo_score)
                        return True
                logger.warning("Cliente não encontrado para atualização de score | cpf_masked=%s", cpf_masked)
                return False
        except Timeout:
            logger.error("FileLock timeout ao atualizar score | cpf_masked=%s", cpf_masked)
            return False

    async def get_cotacao(self, moeda_destino: str) -> CotacaoDTO:
        """
        Chama API externa e retorna a cotação invertida:
        quanto custa 1 unidade da moeda_destino em BRL.
        A API retorna BRL→X, então invertemos para X→BRL.
        A cotação é de referência — a API atualiza `time_last_update_utc` uma vez por
        dia, não em tempo real; o timestamp é repassado ao cliente sem alteração.
        Trata graciosamente erros de rede, timeout, HTTP status e ausência da moeda
        na resposta do provedor, sem propagar exceção. O motivo da indisponibilidade
        (moeda ausente no provedor vs. falha de rede/HTTP) é distinguido em `erro`.
        """
        import httpx
        moeda = moeda_destino.upper()
        logger.info("Consultando cotação | moeda_destino=%s", moeda)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get("https://open.er-api.com/v6/latest/BRL")
                r.raise_for_status()
                data = r.json()
                timestamp = str(data.get("time_last_update_utc", ""))
                taxa_bruta = data.get("rates", {}).get(moeda)
                if taxa_bruta and taxa_bruta > 0:
                    taxa_invertida = round(1.0 / taxa_bruta, 4)
                    logger.info("Cotação obtida | 1 %s = R$ %.4f", moeda, taxa_invertida)
                    return CotacaoDTO(
                        moeda_origem="BRL",
                        moeda_destino=moeda,
                        taxa=taxa_invertida,
                        timestamp=timestamp
                    )
                # Requisição bem-sucedida, mas o provedor não retornou taxa para esta
                # moeda (ex: removida temporariamente do feed) — não é falha de rede.
                logger.warning("Taxa não encontrada ou zero para moeda=%s", moeda)
                return CotacaoDTO(
                    moeda_origem="BRL",
                    moeda_destino=moeda,
                    taxa=0.0,
                    timestamp=timestamp,
                    erro="moeda_indisponivel_no_provedor"
                )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.error("Falha de rede/HTTP ao consultar cotação para %s: %s", moeda, exc)
            return CotacaoDTO(
                moeda_origem="BRL",
                moeda_destino=moeda,
                taxa=0.0,
                timestamp="",
                erro="falha_servico_externo"
            )
        except Exception as exc:
            logger.error("Erro inesperado ao consultar cotação para %s: %s", moeda, exc)
            return CotacaoDTO(
                moeda_origem="BRL",
                moeda_destino=moeda,
                taxa=0.0,
                timestamp="",
                erro="falha_servico_externo"
            )
