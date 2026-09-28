from typing import Optional

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from root_agent import config
from root_agent.infrastructure.api.queue.memory_session_queue import MemorySessionQueue
from root_agent.infrastructure.api.middlewares.autenticacao_api_middleware import AutenticacaoApiMiddleware
from root_agent.infrastructure.api.middlewares.redacao_pii_middleware import RedacaoPiiMiddleware
from root_agent.infrastructure.api.middlewares.session_conflict_middleware import SessionConflictMiddleware
from root_agent.infrastructure.api.middlewares.protected_state_middleware import ProtectedStateMiddleware
from root_agent.utils import get_logger

logger = get_logger("main")


def criar_app(*, session_service_uri: Optional[str] = None, web: Optional[bool] = None) -> FastAPI:
    """
    Monta a API do ADK com os middlewares do Banco Ágil. No Starlette, o último
    `add_middleware` é o mais externo; uma requisição atravessa, nesta ordem:
    AutenticacaoApi → ProtectedState → SessionConflict → RedacaoPii → ADK.
    """
    # 1. Instância base do Google ADK. A dev UI (/dev-ui) só com BANCO_AGIL_DEV_UI=true:
    # ela lista sessões, eventos e estado, e não envia o token da API.
    web = config.DEV_UI_HABILITADA if web is None else web
    app = get_fast_api_app(agents_dir=".", web=web, session_service_uri=session_service_uri)

    # 2. Mais interno: respostas de sessão/execução saem sem CPF e data de nascimento.
    # Fica dentro do SessionConflict para cobrir também o PATCH de loopback que ele faz.
    app.add_middleware(RedacaoPiiMiddleware)

    # 3. Injeção de dependência: fila com o bottleneck desejado (29 requisições por segundo globais).
    # Para sessões simultâneas a nível individual, o lock também protegerá e enfileirará.
    app.add_middleware(
        SessionConflictMiddleware,
        session_queue=MemorySessionQueue(max_requests_per_second=29)
    )

    # 4. Impede que o cliente HTTP escreva chaves de autenticação no estado da sessão
    # (state/stateDelta), que só podem ser definidas pelo backend.
    app.add_middleware(ProtectedStateMiddleware)

    # 5. Mais externo: a API do ADK não tem autenticação própria. Com BANCO_AGIL_API_TOKEN,
    # exige o token; sem ele, só aceita conexões locais. Recusa antes de ler o corpo.
    app.add_middleware(AutenticacaoApiMiddleware)

    if not config.API_TOKEN:
        logger.warning("BANCO_AGIL_API_TOKEN não definido: a API aceita apenas conexões locais (loopback)")
    return app


app = criar_app()

# O app agora está pronto para ser servido via Uvicorn (veja o docker-compose.yml)
