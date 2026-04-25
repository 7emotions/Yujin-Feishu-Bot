import logging
import threading
import time
import os
from typing import Any

from runtime.plugin import BotPlugin
from runtime.session_store import SessionStore
from utils import ColoredFormatter

EventDict = dict[str, Any]
MIN_PLUGIN_MATCH_SCORE = 0.2

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)


class FeishuBot:
    def __init__(self, session_store: SessionStore | None = None) -> None:
        self._plugins: list[BotPlugin] = []
        self._plugins_by_name: dict[str, BotPlugin] = {}
        self._session_store = session_store or SessionStore()
        self._lock = threading.Lock()

    def register_plugin(self, plugin: BotPlugin) -> None:
        self._plugins_by_name[plugin.name] = plugin
        self._plugins.append(plugin)
        logger.info("Registered plugin: %s", plugin.name)

    @property
    def session_store(self) -> SessionStore:
        return self._session_store

    def chat(self, event: EventDict) -> bool:
        try:
            message = event["event"]["message"]
            sender_open_id = event["event"]["sender"]["sender_id"]["open_id"]
        except (KeyError, TypeError):
            logger.warning("Ignored malformed event: %s", event)
            return False

        if sender_open_id == os.environ.get("BOT_USER_ID", ""):
            logger.info("Ignored self-message from BOT_USER_ID")
            return False
        if message.get("chat_type") != "p2p":
            logger.info("Ignored non-p2p message: chat_type=%s", message.get("chat_type"))
            return False

        with self._lock:
            session = self._session_store.get_or_create_session(sender_open_id)
            session.last_activity = time.time()
            session.chat_id = message.get("chat_id", "")
            session.message_id = message.get("message_id", "")
            session.sender_open_id = sender_open_id
            self._append_recent_message(session, message)

            active_plugin = self._plugins_by_name.get(session.active_plugin or "")
            if active_plugin is not None and active_plugin.match(event, session) > 0:
                logger.info(
                    "Routing message_type=%s user=%s to active plugin=%s",
                    message.get("message_type", ""),
                    sender_open_id,
                    active_plugin.name,
                )
                active_plugin.handle(event, session)
                return True

            best_score = 0.0
            best_plugin: BotPlugin | None = None
            for plugin in self._plugins:
                score = plugin.match(event, session)
                if score <= best_score:
                    continue
                best_score = score
                best_plugin = plugin

            if best_plugin is None or best_score < MIN_PLUGIN_MATCH_SCORE:
                logger.info(
                    "No plugin matched user=%s message_type=%s score=%.2f",
                    sender_open_id,
                    message.get("message_type", ""),
                    best_score,
                )
                return False

            logger.info(
                "Selected plugin=%s for user=%s message_type=%s score=%.2f",
                best_plugin.name,
                sender_open_id,
                message.get("message_type", ""),
                best_score,
            )
            best_plugin.handle(event, session)
            return True

    def tick(self) -> None:
        with self._lock:
            for plugin in self._plugins:
                plugin.on_tick(self._session_store)

    def _append_recent_message(self, session: Any, message: dict[str, Any]) -> None:
        message_type = message.get("message_type", "")
        content = message.get("content", "")
        session.recent_messages.append({"type": str(message_type), "content": str(content)})
        if len(session.recent_messages) > 10:
            session.recent_messages = session.recent_messages[-10:]
