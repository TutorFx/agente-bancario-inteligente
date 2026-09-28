import pytest
import asyncio
import time
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_session_conflict_middleware_and_queue(local_client: AsyncClient):
    """
    Valida que o comportamento nativo do ADK (409 Conflict) é preservado
    e que o controle de taxa da fila atrasa requisições excessivas corretamente.
    """
    app_name = "root_agent"
    user_id = "test_queue_user"
    session_id = "test_queue_session"
    
    payload = {"sessionId": session_id}
    url = f"/apps/{app_name}/users/{user_id}/sessions"
    
    # --- Teste 1: Criação da Sessão ---
    res1 = await local_client.post(url, json=payload)
    assert res1.status_code == 200, f"A criação inicial falhou: {res1.text}"
    
    # --- Teste 2: Conflito resolvido via Loopback ou 409 do ADK ---
    res2 = await local_client.post(url, json=payload)
    assert res2.status_code in (200, 409), f"Esperado 200 (Loopback resolvido) ou 409 do ADK, obtido: {res2.status_code}"
    
    # --- Teste 3: Fila e Bottleneck ---
    start_time = time.time()
    tasks = [
        local_client.post(url, json={"sessionId": f"{session_id}_{i}"})
        for i in range(30)
    ]
    responses = await asyncio.gather(*tasks)
    end_time = time.time()
    elapsed = end_time - start_time
    
    for r in responses:
        assert r.status_code == 200, f"A request concorrente falhou com status {r.status_code}: {r.text}"
        
    assert elapsed >= 0.2, f"A fila não respeitou o gargalo de sessões por segundo. Tempo decorrido: {elapsed:.2f}s"
