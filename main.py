from google.adk.cli.fast_api import get_fast_api_app

from root_agent.infrastructure.api.queue.memory_session_queue import MemorySessionQueue
from root_agent.infrastructure.api.middlewares.session_conflict_middleware import SessionConflictMiddleware

# 1. Cria a instância base do Google ADK
app = get_fast_api_app(agents_dir=".", web=True)

# 2. Injeção de dependência: Configura a fila com o bottleneck desejado (29 requisições por segundo globais)
# Para sessões simultâneas a nível individual, o lock também protegerá e enfileirará.
session_queue = MemorySessionQueue(max_requests_per_second=29)

# 3. Adiciona o middleware injetando a fila
app.add_middleware(
    SessionConflictMiddleware,
    session_queue=session_queue
)

# O app agora está pronto para ser servido via Uvicorn (veja o docker-compose.yml)
