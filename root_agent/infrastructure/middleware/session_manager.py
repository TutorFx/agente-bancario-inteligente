import uuid
from .session_config import DEFAULT_SESSION_STATE

class SessionManager:
    def __init__(self):
        self.sessions = {}

    async def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = DEFAULT_SESSION_STATE.copy()
        return session_id

    async def get_session(self, session_id: str) -> dict | None:
        return self.sessions.get(session_id)
