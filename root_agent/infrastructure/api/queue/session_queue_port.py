from contextlib import AbstractAsyncContextManager
from typing import Protocol

class SessionQueuePort(Protocol):
    """
    Porta (Interface) para gerenciar o bloqueio e bottleneck de requisições
    por sessão/usuário.
    """
    
    def acquire(self, session_id: str) -> AbstractAsyncContextManager[None]:
        """
        Adquire um lock para o session_id e gerencia o throughput (ex: 2/segundo).
        Garante que requisições concorrentes sejam enfileiradas ou descartadas.
        """
        ...
