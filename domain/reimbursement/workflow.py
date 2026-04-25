import json
import logging
import time
from typing import Any

import domain.reimbursement.parser as invoice_parser_module
import toolsets.feishu.approval_attachments as attachment_uploader_module
import toolsets.feishu.approvals as approval_creator_module
import toolsets.feishu.file_resources as file_downloader_module
import toolsets.feishu.messaging as message_sender_module
from domain.reimbursement.settings import CANCEL_KEYWORDS, CONFIRM_KEYWORDS, TIMEOUT_SECONDS
from runtime.session_store import SessionStore, UserSession
from utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)

PROCESSING_STATE = "reimbursement:processing"
AWAITING_CONFIRM_STATE = "reimbursement:awaiting_confirm"


class ReimbursementWorkflow:
    def __init__(
        self,
        approval_creator: Any = approval_creator_module,
        attachment_uploader: Any = attachment_uploader_module,
        file_downloader: Any = file_downloader_module,
        invoice_parser: Any = invoice_parser_module,
        message_sender: Any = message_sender_module,
    ) -> None:
        self._approval_creator = approval_creator
        self._attachment_uploader = attachment_uploader
        self._file_downloader = file_downloader
        self._invoice_parser = invoice_parser
        self._message_sender = message_sender

    def match(self, event: dict[str, Any], session: UserSession, plugin_name: str) -> float:
        try:
            message = event["event"]["message"]
        except (KeyError, TypeError):
            return 0.0
        if not isinstance(message, dict):
            return 0.0
        if session.active_plugin == plugin_name:
            return 1.0 if isinstance(message.get("message_type"), str) else 0.0
        message_type = message.get("message_type")
        if message_type in {"image", "file"}:
            return 1.0
        if message_type != "text":
            return 0.0
        text = self._extract_text(message.get("content", "{}"))
        if not text:
            return 0.0
        if any(keyword in text for keyword in ("报销", "发票", "审批", "invoice", "reimburse")):
            return 0.9
        if any(keyword in text for keyword in ("确认", "取消", "金额", "类别", "供应商", "日期", "修改")):
            return 0.7
        return 0.0

    def handle(self, event: dict[str, Any], session: UserSession, plugin_name: str) -> None:
        message = event["event"]["message"]
        message_type = message.get("message_type", "")
        if session.active_plugin != plugin_name:
            if message_type in ("image", "file"):
                self._handle_invoice_message(session, message, plugin_name)
            elif message_type == "text":
                self._message_sender.send_text(session.chat_id, "请发送发票图片或PDF文件，我将帮您提交报销申请。")
            return
        if session.state == PROCESSING_STATE:
            self._message_sender.reply_text(message["message_id"], "正在处理中，请稍候...")
            return
        if session.state == AWAITING_CONFIRM_STATE and message_type == "text":
            self._handle_text_reply(session, message)

    def on_tick(self, session_store: SessionStore, plugin_name: str) -> None:
        now = time.time()
        for user_id, session in session_store.all_sessions():
            if session.active_plugin != plugin_name or session.state != AWAITING_CONFIRM_STATE:
                continue
            if (now - session.last_activity) <= TIMEOUT_SECONDS:
                continue
            logger.info("Reimbursement session timed out for user %s", user_id)
            self._reset_session(session)
            try:
                self._message_sender.reply_text(session.message_id, "⏰ 超时未确认，已自动取消。")
            except Exception as exc:
                logger.warning("Failed to send timeout notice to user %s: %s", user_id, exc)

    def _handle_invoice_message(self, session: UserSession, message: dict[str, Any], plugin_name: str) -> None:
        session.active_plugin = plugin_name
        session.state = PROCESSING_STATE
        session.message_id = message["message_id"]
        logger.info("Starting reimbursement flow for user %s via %s", session.sender_open_id, message.get("message_type", ""))
        try:
            self._message_sender.mark_typing(session.message_id)
        except Exception as exc:
            logger.warning("Failed to mark typing for user %s: %s", session.sender_open_id, exc)
        try:
            file_bytes, filename = self._file_downloader.download_file(message["message_id"], message["message_type"], message["content"])
            fields = self._invoice_parser.parse_invoice(file_bytes, filename)
            session.data = {"file_bytes": file_bytes, "filename": filename, "invoice_fields": fields}
            session.state = AWAITING_CONFIRM_STATE
            logger.info("Invoice parsed for user %s; awaiting confirmation", session.sender_open_id)
            self._message_sender.reply_text(session.message_id, self._message_sender.format_confirmation(fields))
        except Exception as exc:
            logger.error("Failed to process invoice for user %s: %s", session.sender_open_id, exc)
            self._reset_session(session)
            self._message_sender.reply_text(session.message_id, "❌ 处理发票失败，请重试。")

    def _handle_text_reply(self, session: UserSession, message: dict[str, Any]) -> None:
        try:
            self._message_sender.mark_typing(session.message_id)
        except Exception as exc:
            logger.warning("Failed to mark typing for user %s: %s", session.sender_open_id, exc)
        try:
            content = json.loads(message.get("content", "{}"))
            text = content.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            text = ""

        if text in CONFIRM_KEYWORDS:
            invoice_fields = self._get_invoice_fields(session)
            file_bytes = self._get_file_bytes(session)
            filename = self._get_filename(session)
            logger.info("User %s confirmed reimbursement submission", session.sender_open_id)
            self._reset_session(session)
            try:
                file_code = self._attachment_uploader.upload_approval_attachment(file_bytes, filename)
                instance_code = self._approval_creator.create_reimbursement_approval(session.sender_open_id, invoice_fields, file_code)
                self._message_sender.reply_text(session.message_id, f"✅ 报销单已提交！审批单号：{instance_code}")
            except Exception as exc:
                logger.error("Failed to submit approval for user %s: %s", session.sender_open_id, exc)
                self._message_sender.reply_text(session.message_id, "❌ 提交失败，请重试。")
            return

        if text in CANCEL_KEYWORDS:
            logger.info("User %s cancelled reimbursement flow", session.sender_open_id)
            self._reset_session(session)
            self._message_sender.reply_text(session.message_id, "已取消报销。")
            return

        logger.info("Applying reimbursement correction for user %s", session.sender_open_id)
        self._apply_correction(session, text)

    def _apply_correction(self, session: UserSession, correction_text: str) -> None:
        try:
            corrected = self._invoice_parser.correct_invoice_fields(self._get_file_bytes(session), self._get_filename(session), self._get_invoice_fields(session), correction_text)
            session.data["invoice_fields"] = corrected
        except Exception as exc:
            logger.warning("Correction failed, keeping original fields: %s", exc)
        self._message_sender.reply_text(session.message_id, self._message_sender.format_confirmation(self._get_invoice_fields(session)))

    def _reset_session(self, session: UserSession) -> None:
        session.active_plugin = None
        session.state = "idle"
        session.data = {}

    def _get_file_bytes(self, session: UserSession) -> bytes:
        file_bytes = session.data.get("file_bytes", b"")
        return file_bytes if isinstance(file_bytes, bytes) else b""

    def _get_filename(self, session: UserSession) -> str:
        filename = session.data.get("filename", "")
        return filename if isinstance(filename, str) else ""

    def _get_invoice_fields(self, session: UserSession) -> dict[str, str]:
        fields = session.data.get("invoice_fields", {})
        if isinstance(fields, dict):
            return {str(key): "" if value is None else str(value) for key, value in fields.items()}
        return {}

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
