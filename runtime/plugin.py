from abc import ABC, abstractmethod
from typing import Any

from runtime.session_store import SessionStore, UserSession

EventDict = dict[str, Any]


class BotPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def capability_description(self) -> str:
        return self.name

    @property
    def tool_descriptions(self) -> list[str]:
        return []

    @abstractmethod
    def match(self, event: EventDict, session: UserSession) -> float: ...

    @abstractmethod
    def handle(self, event: EventDict, session: UserSession) -> None: ...

    def on_tick(self, session_store: SessionStore) -> None:
        pass
