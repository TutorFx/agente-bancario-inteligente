import pytest
from root_agent.infrastructure.middleware.session_manager import SessionManager

def test_session_initialization():
    manager = SessionManager()
    session_id = manager.create_session()
    
    assert session_id is not None
    assert isinstance(session_id, str)
    assert manager.get_session(session_id) is not None
