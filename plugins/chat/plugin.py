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

    @property
    def chat_actions(self) -> dict[str, str]:
        return {"chat": "继续普通聊天对话"}

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
        text = self._extract_text(message.get("content", "{}"))
        if text == "/new":
            self._reset_session(session)
            message_sender.reply_text(session.message_id, "已开始新会话。")
            return

        memory_kind = self._capture_memory_directive(session, text)
        if memory_kind is not None:
            session.last_intent = "chat"
            reply = "好的，我记住了。之后我会按这个偏好继续和你对话。"
            session.recent_messages.append({"type": "assistant", "content": reply})
            if len(session.recent_messages) > 10:
                session.recent_messages = session.recent_messages[-10:]
            session.summary = responder.build_summary(session)
            message_sender.reply_text(session.message_id, reply)
            return

        session.active_plugin = self.name
        session.state = "chat:active"
        decision = responder.build_decision(session, text, self._plugins_provider())
        if self._dispatch_action(decision["action"], decision["reply"], session, event, self._plugins_provider()):
            logger.info("Chat plugin dispatched action=%s user=%s reason=%s", decision["action"], session.sender_open_id, decision.get("reason", ""))
            return
        session.last_intent = "chat"
        reply = decision["reply"]
        logger.info("Chat plugin replying to user=%s intent=%s reason=%s", session.sender_open_id, session.last_intent, decision.get("reason", ""))
        session.recent_messages.append({"type": "assistant", "content": reply})
        if len(session.recent_messages) > 10:
            session.recent_messages = session.recent_messages[-10:]
        session.summary = responder.build_summary(session)
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

    def _reset_session(self, session: UserSession) -> None:
        session.active_plugin = self.name
        session.state = "chat:active"
        session.data = {}
        session.recent_messages = []
        session.summary = ""
        session.last_intent = "chat"

    def _chat_memory(self, session: UserSession) -> dict[str, list[str]]:
        memory = session.data.get("chat_memory")
        if isinstance(memory, dict):
            preferences = memory.get("preferences")
            facts = memory.get("facts")
            if isinstance(preferences, list) and isinstance(facts, list):
                return {"preferences": [str(item) for item in preferences], "facts": [str(item) for item in facts]}
        memory = {"preferences": [], "facts": []}
        session.data["chat_memory"] = memory
        return memory

    def _capture_memory_directive(self, session: UserSession, text: str) -> str | None:
        stripped = text.strip()
        if not stripped:
            return None
        memory = self._chat_memory(session)
        if stripped.startswith(("以后", "请记住", "记住", "之后", "从现在开始")):
            memory["preferences"].append(stripped)
            memory["preferences"] = memory["preferences"][-10:]
            return "preference"
        if stripped.startswith(("我是", "我叫", "我的", "我现在在")):
            memory["facts"].append(stripped)
            memory["facts"] = memory["facts"][-10:]
            return "fact"
        return None

    def _dispatch_action(
        self,
        action: str,
        reply: str,
        session: UserSession,
        event: EventDict,
        plugins: list[BotPlugin],
    ) -> bool:
        if action == "chat":
            return False
        for plugin in plugins:
            if plugin is self:
                continue
            if plugin.handle_chat_action(action, reply, session, event):
                return True
        return False
