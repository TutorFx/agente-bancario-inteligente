"""Testes unitários para o BancoAgilAdapter."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from root_agent.infrastructure.adapters.banco_agil_adapter import BancoAgilAdapter


@pytest.fixture
def adapter():
    return BancoAgilAdapter()


@pytest.fixture
def clientes_mock():
    return [
        {
            "cpf": "123.456.789-00",
            "nome": "Maria Silva",
            "data_nascimento": "1990-05-15",
            "score_credito": "750",
            "limite_credito": "3000.00",
            "conta": "0001",
        },
        {
            "cpf": "987.654.321-11",
            "nome": "João Santos",
            "data_nascimento": "1985-10-20",
            "score_credito": "550",
            "limite_credito": "1500.00",
            "conta": "0002",
        },
    ]


class TestAutenticarEBuscarCliente:
    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_autenticar_sucesso(self, mock_carregar, adapter, clientes_mock):
        mock_carregar.return_value = clientes_mock

        cliente = adapter.autenticar("12345678900", "1990-05-15")

        assert cliente is not None
        assert cliente.cpf == "123.456.789-00"
        assert cliente.nome == "Maria Silva"

    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_autenticar_data_nascimento_incorreta(self, mock_carregar, adapter, clientes_mock):
        mock_carregar.return_value = clientes_mock

        cliente = adapter.autenticar("123.456.789-00", "2000-01-01")

        assert cliente is None

    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_buscar_cliente_existente(self, mock_carregar, adapter, clientes_mock):
        mock_carregar.return_value = clientes_mock

        cliente = adapter.buscar_cliente("98765432111")

        assert cliente is not None
        assert cliente.nome == "João Santos"

    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_buscar_cliente_inexistente(self, mock_carregar, adapter, clientes_mock):
        mock_carregar.return_value = clientes_mock

        cliente = adapter.buscar_cliente("000.000.000-00")

        assert cliente is None


class TestRegrasScoreEDinamico:
    def test_obter_limite_maximo_faixas_score(self, adapter):
        assert adapter.obter_limite_maximo_por_score(150) == 0.00
        assert adapter.obter_limite_maximo_por_score(350) == 1500.00
        assert adapter.obter_limite_maximo_por_score(550) == 4000.00
        assert adapter.obter_limite_maximo_por_score(750) == 10000.00
        assert adapter.obter_limite_maximo_por_score(900) == 25000.00
        assert adapter.obter_limite_maximo_por_score(1200) == 0.00


class TestSolicitacaoLimiteEScore:
    @patch.object(BancoAgilAdapter, "_registrar_auditoria_solicitacao")
    @patch.object(BancoAgilAdapter, "_salvar_clientes")
    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_solicitar_aumento_limite_aprovado_score_alto(self, mock_carregar, mock_salvar, mock_auditoria, adapter, clientes_mock):
        mock_carregar.return_value = [dict(c) for c in clientes_mock]

        resultado = adapter.solicitar_aumento_limite("123.456.789-00", 5000.0)

        assert resultado.aprovado is True
        assert resultado.limite_novo == 5000.0
        assert resultado.limite_anterior == 3000.0
        assert resultado.limite_maximo_permitido == 10000.0
        mock_salvar.assert_called_once()
        mock_auditoria.assert_called_once_with(
            cpf_cliente="123.456.789-00",
            limite_atual=3000.0,
            novo_limite_solicitado=5000.0,
            status_pedido="aprovado"
        )

    @patch.object(BancoAgilAdapter, "_registrar_auditoria_solicitacao")
    @patch.object(BancoAgilAdapter, "_salvar_clientes")
    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_solicitar_aumento_limite_reprovado_acima_do_teto(self, mock_carregar, mock_salvar, mock_auditoria, adapter, clientes_mock):
        mock_carregar.return_value = [dict(c) for c in clientes_mock]

        resultado = adapter.solicitar_aumento_limite("987.654.321-11", 5000.0)

        assert resultado.aprovado is False
        assert resultado.limite_novo is None
        assert resultado.limite_maximo_permitido == 4000.0
        assert "Score insuficiente" in resultado.motivo
        mock_salvar.assert_not_called()
        mock_auditoria.assert_called_once_with(
            cpf_cliente="987.654.321-11",
            limite_atual=1500.0,
            novo_limite_solicitado=5000.0,
            status_pedido="rejeitado"
        )

    @patch.object(BancoAgilAdapter, "_registrar_auditoria_solicitacao")
    @patch.object(BancoAgilAdapter, "_salvar_clientes")
    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_solicitar_aumento_limite_reprovado_menor_ou_igual_ao_atual(self, mock_carregar, mock_salvar, mock_auditoria, adapter, clientes_mock):
        mock_carregar.return_value = [dict(c) for c in clientes_mock]

        resultado = adapter.solicitar_aumento_limite("987.654.321-11", 1000.0)

        assert resultado.aprovado is False
        assert resultado.limite_novo is None
        assert "deve ser maior que o limite atual" in resultado.motivo
        mock_salvar.assert_not_called()
        mock_auditoria.assert_called_once_with(
            cpf_cliente="987.654.321-11",
            limite_atual=1500.0,
            novo_limite_solicitado=1000.0,
            status_pedido="rejeitado"
        )

    @patch.object(BancoAgilAdapter, "_salvar_clientes")
    @patch.object(BancoAgilAdapter, "_carregar_clientes")
    def test_atualizar_score_sucesso(self, mock_carregar, mock_salvar, adapter, clientes_mock):
        clientes_copia = [dict(c) for c in clientes_mock]
        mock_carregar.return_value = clientes_copia

        sucesso = adapter.atualizar_score("987.654.321-11", 820)

        assert sucesso is True
        assert clientes_copia[1]["score_credito"] == "820"
        mock_salvar.assert_called_once_with(clientes_copia)


class TestCambioCotacao:
    @pytest.mark.asyncio
    async def test_get_cotacao_sucesso(self, adapter):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rates": {"USD": 0.18, "EUR": 0.16},
            "time_last_update_utc": "Tue, 22 Sep 2026 12:00:00 +0000",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            cotacao = await adapter.get_cotacao("USD")

            assert cotacao.moeda_origem == "BRL"
            assert cotacao.moeda_destino == "USD"
            assert cotacao.taxa == 5.5556
            assert cotacao.erro is None
            assert cotacao.timestamp == "Tue, 22 Sep 2026 12:00:00 +0000"
            mock_client.get.assert_called_once_with("https://open.er-api.com/v6/latest/BRL")

    @pytest.mark.asyncio
    async def test_get_cotacao_moeda_ausente_no_provedor(self, adapter):
        """Requisição bem-sucedida, mas o provedor não retorna taxa para a moeda:
        deve ser sinalizado como 'moeda_indisponivel_no_provedor', não como falha
        geral de serviço."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "rates": {"USD": 0.18},
            "time_last_update_utc": "Tue, 22 Sep 2026 12:00:00 +0000",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            cotacao = await adapter.get_cotacao("CHF")

            assert cotacao.taxa == 0.0
            assert cotacao.erro == "moeda_indisponivel_no_provedor"
            assert cotacao.timestamp == "Tue, 22 Sep 2026 12:00:00 +0000"


class TestAuditoriaSolicitacao:
    def test_registrar_auditoria_solicitacao_escreve_csv(self, adapter, tmp_path):
        import csv
        from datetime import datetime
        csv_temp = tmp_path / "solicitacoes_temp.csv"

        with patch("root_agent.infrastructure.adapters.banco_agil_adapter.SOLICITACOES_LIMITE_PATH", str(csv_temp)):
            adapter._registrar_auditoria_solicitacao(
                cpf_cliente="12345678900",
                limite_atual=3000.0,
                novo_limite_solicitado=5000.0,
                status_pedido="aprovado"
            )

            assert csv_temp.exists()
            with open(csv_temp, newline="", encoding="utf-8") as f:
                linhas = list(csv.DictReader(f))

            assert len(linhas) == 1
            linha = linhas[0]
            assert linha["cpf_cliente"] == "12345678900"
            assert linha["limite_atual"] == "3000.00"
            assert linha["novo_limite_solicitado"] == "5000.00"
            assert linha["status_pedido"] == "aprovado"

            import re
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", linha["data_hora_solicitacao"])
            dt = datetime.fromisoformat(linha["data_hora_solicitacao"].replace("Z", "+00:00"))
            assert dt is not None

    @pytest.mark.asyncio
    async def test_get_cotacao_timeout_graceful(self, adapter):
        import httpx
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("Timeout na requisição")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            cotacao = await adapter.get_cotacao("USD")
            assert cotacao.taxa == 0.0
            assert cotacao.moeda_destino == "USD"
            assert cotacao.erro == "falha_servico_externo"

    @pytest.mark.asyncio
    async def test_get_cotacao_connect_error_graceful(self, adapter):
        import httpx
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Falha de conexão DNS")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            cotacao = await adapter.get_cotacao("EUR")
            assert cotacao.taxa == 0.0
            assert cotacao.moeda_destino == "EUR"
            assert cotacao.erro == "falha_servico_externo"

    @pytest.mark.asyncio
    async def test_get_cotacao_http_status_500_graceful(self, adapter):
        import httpx
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("500 Server Error", request=MagicMock(), response=MagicMock())
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            cotacao = await adapter.get_cotacao("USD")
            assert cotacao.taxa == 0.0
            assert cotacao.erro == "falha_servico_externo"


class TestConcorrenciaERaceConditions:
    def test_escrita_atomica_salvar_clientes(self, tmp_path):
        import csv
        csv_file = tmp_path / "clientes_atomic.csv"
        adapter = BancoAgilAdapter(clientes_lock_path=str(tmp_path / "clientes.lock"))

        clientes = [
            {"cpf": "111", "nome": "User 1", "data_nascimento": "01/01/2000", "score_credito": "500", "limite_credito": "1000.00", "conta": "0001"},
            {"cpf": "222", "nome": "User 2", "data_nascimento": "02/02/2000", "score_credito": "600", "limite_credito": "2000.00", "conta": "0002"},
        ]
        with patch("root_agent.infrastructure.adapters.banco_agil_adapter.CSV_PATH", str(csv_file)):
            adapter._salvar_clientes(clientes)
            assert csv_file.exists()
            with open(csv_file, newline="", encoding="utf-8") as f:
                saved = list(csv.DictReader(f))
            assert len(saved) == 2
            assert saved[0]["cpf"] == "111"

    def test_concorrencia_atualizar_score_multi_threads(self, tmp_path):
        """
        Simula 10 threads concorrentes atualizando simultaneamente o score
        de clientes distintos. Valida ausência de lost update.
        """
        import csv
        from concurrent.futures import ThreadPoolExecutor

        csv_file = tmp_path / "clientes_concurrent.csv"
        lock_file = tmp_path / "clientes.lock"

        inicial = [
            {
                "cpf": f"0000000000{i}",
                "nome": f"Cliente {i}",
                "data_nascimento": "01/01/2000",
                "score_credito": "300",
                "limite_credito": "1000.00",
                "conta": f"000{i}"
            }
            for i in range(10)
        ]
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=inicial[0].keys())
            writer.writeheader()
            writer.writerows(inicial)

        adapter = BancoAgilAdapter(clientes_lock_path=str(lock_file), lock_timeout=15.0)

        def worker(idx):
            cpf = f"0000000000{idx}"
            novo_score = 700 + idx
            with patch("root_agent.infrastructure.adapters.banco_agil_adapter.CSV_PATH", str(csv_file)):
                return adapter.atualizar_score(cpf, novo_score)

        with patch("root_agent.infrastructure.adapters.banco_agil_adapter.CSV_PATH", str(csv_file)):
            with ThreadPoolExecutor(max_workers=10) as executor:
                resultados = list(executor.map(worker, range(10)))

        assert all(resultados)

        with open(csv_file, newline="", encoding="utf-8") as f:
            final = list(csv.DictReader(f))

        assert len(final) == 10
        for i, row in enumerate(final):
            assert row["score_credito"] == str(700 + i)

    def test_concorrencia_auditoria_sem_duplicacao_header(self, tmp_path):
        """
        Simula múltiplas threads registrando auditoria simultaneamente
        quando o arquivo de auditoria ainda não existe.
        Valida que o header não é duplicado e todas as linhas são salvas.
        """
        import csv
        from concurrent.futures import ThreadPoolExecutor

        csv_auditoria = tmp_path / "solicitacoes_concurrent.csv"
        lock_auditoria = tmp_path / "solicitacoes.lock"
        adapter = BancoAgilAdapter(solicitacoes_lock_path=str(lock_auditoria), lock_timeout=15.0)

        def worker(idx):
            with patch("root_agent.infrastructure.adapters.banco_agil_adapter.SOLICITACOES_LIMITE_PATH", str(csv_auditoria)):
                adapter._registrar_auditoria_solicitacao(
                    cpf_cliente=f"1112223334{idx}",
                    limite_atual=1000.0,
                    novo_limite_solicitado=2000.0,
                    status_pedido="aprovado" if idx % 2 == 0 else "rejeitado"
                )

        with patch("root_agent.infrastructure.adapters.banco_agil_adapter.SOLICITACOES_LIMITE_PATH", str(csv_auditoria)):
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(worker, range(16)))

        assert csv_auditoria.exists()
        with open(csv_auditoria, newline="", encoding="utf-8") as f:
            linhas_raw = f.readlines()
            f.seek(0)
            rows = list(csv.DictReader(f))

        # Apenas 1 cabeçalho no arquivo inteiro
        assert linhas_raw[0].startswith("cpf_cliente,data_hora_solicitacao")
        for line in linhas_raw[1:]:
            assert not line.startswith("cpf_cliente")

        # Exatamente 16 registros
        assert len(rows) == 16

    def test_lock_timeout_handling(self, tmp_path):
        from filelock import FileLock
        lock_file = tmp_path / "timeout.lock"
        external_lock = FileLock(str(lock_file))

        external_lock.acquire()
        try:
            adapter = BancoAgilAdapter(clientes_lock_path=str(lock_file), lock_timeout=0.2)
            res = adapter.solicitar_aumento_limite("123", 5000.0)
            assert res.aprovado is False
            assert "Sistema temporariamente ocupado" in res.motivo

            score_res = adapter.atualizar_score("123", 800)
            assert score_res is False
        finally:
            external_lock.release()

