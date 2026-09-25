import uuid

class SessionManager:
    def __init__(self):
        self.sessions = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {}
        return session_id

    def get_session(self, session_id: str) -> dict | None:
        return self.sessions.get(session_id)
