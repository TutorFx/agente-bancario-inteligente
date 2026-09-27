import asyncio
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from root_agent.utils import get_logger
from root_agent.infrastructure.api.queue.session_queue_port import SessionQueuePort

logger = get_logger(__name__)


class MemorySessionQueue(SessionQueuePort):
    def __init__(
        self,
        max_requests_per_second: int = 29,
        max_locks: int = 10_000,
    ):
        """
        :param max_requests_per_second: O máximo de chamadas simultâneas
        permitidas por segundo para inicialização de sessão. Padrão ajustado para 29
        com base no limite de concorrência da API da LLM.
        :param max_locks: Número máximo de locks em memória.
                          Ao atingir o limite, os locks mais antigos (LRU) são evictados.
        """
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
        self._max_locks = max_locks
        # Protege o throughput global
        self._global_semaphore = asyncio.Semaphore(max_requests_per_second)
        self._rate_limit_delay = 1.0 / max_requests_per_second
        self._last_request_time = 0.0

    def _get_or_create_lock(self, session_id: str) -> asyncio.Lock:
        """Retorna o lock da sessão, criando se necessário e aplicando eviction LRU."""
        if session_id in self._locks:
            # Move para o fim (mais recente) para política LRU
            self._locks.move_to_end(session_id)
            return self._locks[session_id]

        # Evicta os locks mais antigos se atingir o limite
        while len(self._locks) >= self._max_locks:
            evicted_id, _ = self._locks.popitem(last=False)
            logger.debug("Lock evictado por LRU | session_id=%s", evicted_id)

        lock = asyncio.Lock()
        self._locks[session_id] = lock
        return lock

    @asynccontextmanager
    async def acquire(self, session_id: str) -> AsyncGenerator[None, None]:
        lock = self._get_or_create_lock(session_id)
        async with lock:
            # Semáforo global atua como um Bottleneck limitando o tráfego total
            async with self._global_semaphore:
                now = time.time()
                time_since_last = now - self._last_request_time
                if time_since_last < self._rate_limit_delay:
                    await asyncio.sleep(self._rate_limit_delay - time_since_last)

                self._last_request_time = time.time()
                yield
