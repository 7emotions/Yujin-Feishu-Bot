import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserSession:
    active_plugin: str | None = None
    state: str = "idle"
    data: dict[str, Any] = field(default_factory=dict)
    message_id: str = ""
    chat_id: str = ""
    sender_open_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    last_intent: str = ""


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, UserSession] = {}
        self._lock = threading.Lock()

    def get_session(self, user_id: str) -> UserSession | None:
        with self._lock:
            return self._sessions.get(user_id)

    def get_or_create_session(self, user_id: str) -> UserSession:
        with self._lock:
            if user_id not in self._sessions:
                self._sessions[user_id] = UserSession(sender_open_id=user_id)
            return self._sessions[user_id]

    def remove_session(self, user_id: str) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)

    def all_sessions(self) -> list[tuple[str, UserSession]]:
        with self._lock:
            return list(self._sessions.items())

    def reset_session(self, user_id: str) -> UserSession:
        with self._lock:
            session = UserSession(sender_open_id=user_id)
            self._sessions[user_id] = session
            return session


session_store = SessionStore()
