from typing import Protocol, AsyncGenerator
from contextlib import asynccontextmanager

class SessionQueuePort(Protocol):
    """
    Porta (Interface) para gerenciar o bloqueio e bottleneck de requisições
    por sessão/usuário.
    """
    
    @asynccontextmanager
    async def acquire(self, session_id: str) -> AsyncGenerator[None, None]:
        """
        Adquire um lock para o session_id e gerencia o throughput (ex: 2/segundo).
        Garante que requisições concorrentes sejam enfileiradas ou descartadas.
        """
        ...
