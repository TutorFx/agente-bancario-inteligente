import pytest
from root_agent.infrastructure.middleware.session_manager import SessionManager

@pytest.mark.asyncio
async def test_session_initialization():
    manager = SessionManager()
    session_id = await manager.create_session()
    
    assert session_id is not None
    assert isinstance(session_id, str)
    assert await manager.get_session(session_id) is not None
