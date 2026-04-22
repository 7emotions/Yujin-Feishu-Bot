"""Per-user conversation FSM for invoice reimbursement bot.

States:
  IDLE -> receive invoice image/file -> PROCESSING -> parse -> AWAITING_CONFIRM
  AWAITING_CONFIRM -> confirm text -> IDLE (submit approval)
  AWAITING_CONFIRM -> cancel text -> IDLE (cancel)
  AWAITING_CONFIRM -> correction text -> AWAITING_CONFIRM (re-confirm with updated fields)
  PROCESSING -> any message -> reply "正在处理中，请稍候..."

Guards:
  - Ignore messages from BOT_USER_ID (self-trigger prevention)
  - Ignore group chat messages (chat_type != "p2p")
"""
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from openai import OpenAI

from bot.config import (
    BOT_USER_ID,
    CANCEL_KEYWORDS,
    CONFIRM_KEYWORDS,
    OPENAI_API_KEY,
    TIMEOUT_SECONDS,
)
from bot import (
    approval_creator,
    attachment_uploader,
    file_downloader,
    invoice_parser,
    message_sender,
)

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    AWAITING_CONFIRM = "awaiting_confirm"


@dataclass
class UserSession:
    state: ConversationState = ConversationState.IDLE
    invoice_fields: dict = field(default_factory=dict)
    file_bytes: bytes = b""
    filename: str = ""
    message_id: str = ""
    chat_id: str = ""
    sender_open_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


class ConversationStateMachine:
    """Thread-safe per-user FSM for the reimbursement flow."""

    def __init__(self) -> None:
        self._sessions: dict[str, UserSession] = {}
        self._lock = threading.Lock()

    def get_or_create_session(self, user_id: str) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(sender_open_id=user_id)
        return self._sessions[user_id]

    def handle_event(self, event: dict) -> None:
        """Route an incoming Feishu event to the appropriate handler."""
        try:
            msg = event["event"]["message"]
            sender_open_id = event["event"]["sender"]["sender_id"]["open_id"]
        except (KeyError, TypeError):
            logger.debug("Malformed event, ignoring: %s", event)
            return

        # Guard 1: ignore self-messages from the bot
        if sender_open_id == BOT_USER_ID:
            logger.debug("Ignoring self-message from BOT_USER_ID")
            return

        # Guard 2: P2P only
        if msg.get("chat_type") != "p2p":
            logger.debug("Ignoring non-P2P message (chat_type=%s)", msg.get("chat_type"))
            return

        with self._lock:
            session = self.get_or_create_session(sender_open_id)
            session.last_activity = time.time()
            session.chat_id = msg.get("chat_id", "")
            session.sender_open_id = sender_open_id

            message_type = msg.get("message_type", "")

            if session.state == ConversationState.IDLE:
                if message_type in ("image", "file"):
                    self._handle_invoice_message(session, event)
                # else: ignore text messages in IDLE state

            elif session.state == ConversationState.PROCESSING:
                message_sender.reply_text(msg["message_id"], "正在处理中，请稍候...")

            elif session.state == ConversationState.AWAITING_CONFIRM:
                self._handle_text_reply(session, event)

    def _handle_invoice_message(self, session: UserSession, event: dict) -> None:
        """Download and parse invoice; transition to AWAITING_CONFIRM."""
        msg = event["event"]["message"]
        session.state = ConversationState.PROCESSING
        session.message_id = msg["message_id"]
        try:
            file_bytes, filename = file_downloader.download_file(
                msg["message_id"],
                msg["message_type"],
                msg["content"],
            )
            session.file_bytes = file_bytes
            session.filename = filename
            fields = invoice_parser.parse_invoice(file_bytes, filename)
            session.invoice_fields = fields
            session.state = ConversationState.AWAITING_CONFIRM
            confirmation = message_sender.format_confirmation(fields)
            message_sender.reply_text(session.message_id, confirmation)
        except Exception as exc:
            logger.error(
                "Failed to process invoice for user %s: %s",
                session.sender_open_id,
                exc,
            )
            session.state = ConversationState.IDLE
            message_sender.reply_text(session.message_id, "❌ 处理发票失败，请重试。")

    def _handle_text_reply(self, session: UserSession, event: dict) -> None:
        """Handle text message during AWAITING_CONFIRM state."""
        msg = event["event"]["message"]
        try:
            content = json.loads(msg.get("content", "{}"))
            text = content.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            text = ""

        if text in CONFIRM_KEYWORDS:
            session.state = ConversationState.IDLE
            try:
                file_code = attachment_uploader.upload_approval_attachment(
                    session.file_bytes, session.filename
                )
                instance_code = approval_creator.create_reimbursement_approval(
                    session.sender_open_id, session.invoice_fields, file_code
                )
                message_sender.reply_text(
                    session.message_id,
                    f"✅ 报销单已提交！审批单号：{instance_code}",
                )
            except Exception as exc:
                logger.error(
                    "Failed to submit approval for user %s: %s",
                    session.sender_open_id,
                    exc,
                )
                message_sender.reply_text(session.message_id, "❌ 提交失败，请重试。")

        elif text in CANCEL_KEYWORDS:
            session.state = ConversationState.IDLE
            message_sender.reply_text(session.message_id, "已取消报销。")

        else:
            # Correction flow
            self._apply_correction(session, text)

    def _apply_correction(self, session: UserSession, correction_text: str) -> None:
        """Apply user's field correction via GPT-4o and re-send confirmation."""
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            prompt = (
                f"当前发票信息: {json.dumps(session.invoice_fields, ensure_ascii=False)}\n"
                f"用户修改要求: {correction_text}\n"
                f"请返回修改后的完整JSON（只返回JSON，不要其他文字）"
            )
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content or ""
            raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw.strip())
            raw = re.sub(r"\n?```$", "", raw.strip())
            updated = json.loads(raw)
            if isinstance(updated, dict):
                for k in session.invoice_fields:
                    if k in updated and updated[k] is not None:
                        session.invoice_fields[k] = str(updated[k])
        except Exception as exc:
            logger.warning("Correction failed, keeping original fields: %s", exc)

        # Always re-send confirmation (with updated or unchanged fields)
        confirmation = message_sender.format_confirmation(session.invoice_fields)
        message_sender.reply_text(session.message_id, confirmation)

    def _check_timeouts(self) -> None:
        """Send timeout notifications and reset stale AWAITING_CONFIRM sessions."""
        with self._lock:
            now = time.time()
            for user_id, session in list(self._sessions.items()):
                if (
                    session.state == ConversationState.AWAITING_CONFIRM
                    and (now - session.last_activity) > TIMEOUT_SECONDS
                ):
                    session.state = ConversationState.IDLE
                    try:
                        message_sender.reply_text(
                            session.message_id, "⏰ 超时未确认，已自动取消。"
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to send timeout notice to user %s: %s", user_id, exc
                        )


# Module-level singleton
state_machine = ConversationStateMachine()
