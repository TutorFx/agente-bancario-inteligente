"""Testes unitários para o MemorySessionQueue (LRU eviction e rate limiting)."""

import asyncio
import pytest

from root_agent.infrastructure.api.queue.memory_session_queue import MemorySessionQueue


@pytest.mark.asyncio
async def test_memory_session_queue_acquire():
    queue = MemorySessionQueue(max_requests_per_second=100, max_locks=10)
    executed = False

    async with queue.acquire("sessao_1"):
        executed = True

    assert executed is True
    assert "sessao_1" in queue._locks


@pytest.mark.asyncio
async def test_memory_session_queue_lru_eviction():
    # Cria fila com limite max_locks = 3
    queue = MemorySessionQueue(max_requests_per_second=100, max_locks=3)

    async with queue.acquire("sessao_1"):
        pass
    async with queue.acquire("sessao_2"):
        pass
    async with queue.acquire("sessao_3"):
        pass

    assert len(queue._locks) == 3
    assert list(queue._locks.keys()) == ["sessao_1", "sessao_2", "sessao_3"]

    # Adicionar 4ª sessão deve evictar sessao_1 (o mais antigo)
    async with queue.acquire("sessao_4"):
        pass

    assert len(queue._locks) == 3
    assert "sessao_1" not in queue._locks
    assert list(queue._locks.keys()) == ["sessao_2", "sessao_3", "sessao_4"]


@pytest.mark.asyncio
async def test_memory_session_queue_lru_move_to_end_on_access():
    queue = MemorySessionQueue(max_requests_per_second=100, max_locks=3)

    async with queue.acquire("sessao_1"):
        pass
    async with queue.acquire("sessao_2"):
        pass
    async with queue.acquire("sessao_3"):
        pass

    # Reacessar sessao_1 move-o para o final (mais recente)
    async with queue.acquire("sessao_1"):
        pass

    assert list(queue._locks.keys()) == ["sessao_2", "sessao_3", "sessao_1"]

    # Adicionar sessao_4 deve evictar sessao_2 agora
    async with queue.acquire("sessao_4"):
        pass

    assert len(queue._locks) == 3
    assert "sessao_2" not in queue._locks
    assert "sessao_1" in queue._locks
    assert list(queue._locks.keys()) == ["sessao_3", "sessao_1", "sessao_4"]
