import json
import logging
from importlib import import_module
from typing import Any, Callable

responder = import_module("plugins.chat.responder")
from runtime.plugin import BotPlugin
from runtime.session_store import SessionStore, UserSession
from toolsets.feishu import messaging as message_sender
from utils import ColoredFormatter

EventDict = dict[str, Any]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)


class ChatPlugin(BotPlugin):
    def __init__(self, plugins_provider: Callable[[], list[BotPlugin]] | None = None) -> None:
        self._plugins_provider = plugins_provider or (lambda: [])

    @property
    def name(self) -> str:
        return "chat"

    @property
    def capability_description(self) -> str:
        return "通用聊天、解释、问答、功能介绍和任务引导。"

    @property
    def tool_descriptions(self) -> list[str]:
        return [
            "reply_text：直接回复用户",
            "基于 recent_messages / summary / last_intent 继续上下文对话",
        ]

    def set_plugins_provider(self, plugins_provider: Callable[[], list[BotPlugin]]) -> None:
        self._plugins_provider = plugins_provider

    def match(self, event: EventDict, session: UserSession) -> float:
        try:
            message = event["event"]["message"]
        except (KeyError, TypeError):
            return 0.0
        if not isinstance(message, dict):
            return 0.0
        message_type = message.get("message_type")
        if session.active_plugin == self.name:
            return 1.0 if message_type == "text" else 0.0
        return 0.2 if message_type == "text" else 0.0

    def handle(self, event: EventDict, session: UserSession) -> None:
        message = event["event"]["message"]
        if message.get("message_type") != "text":
            return
        session.active_plugin = self.name
        session.state = "chat:active"
        text = self._extract_text(message.get("content", "{}"))
        decision = responder.build_decision(session, text, self._plugins_provider())
        session.last_intent = "reimbursement" if decision["action"] == "handoff_reimbursement" else "chat"
        if decision["action"] == "handoff_reimbursement":
            logger.info("Chat plugin requested reimbursement handoff for user=%s reason=%s", session.sender_open_id, decision.get("reason", ""))
            message_sender.reply_text(session.message_id, decision["reply"])
            return
        reply = decision["reply"]
        logger.info("Chat plugin replying to user=%s intent=%s reason=%s", session.sender_open_id, session.last_intent, decision.get("reason", ""))
        session.recent_messages.append({"type": "assistant", "content": reply})
        if len(session.recent_messages) > 10:
            session.recent_messages = session.recent_messages[-10:]
        message_sender.reply_text(session.message_id, reply)

    def on_tick(self, session_store: SessionStore) -> None:
        _ = session_store

    def _extract_text(self, content: object) -> str:
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return content.strip().lower()
            if isinstance(parsed, dict):
                text = parsed.get("text", "")
                return text.strip().lower() if isinstance(text, str) else ""
        return ""
