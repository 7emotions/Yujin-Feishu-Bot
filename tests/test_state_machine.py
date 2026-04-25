"""Tests for bot/state_machine.py"""
# pyright: reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportPrivateLocalImportUsage=false, reportPrivateUsage=false, reportUnusedCallResult=false

import importlib
import json
import time
from unittest.mock import patch


def _setup_env(monkeypatch):
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_bot_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver_test")
    monkeypatch.setenv(
        "FORM_FIELD_IDS",
        json.dumps(
            {
                "invoice_no": "widget_invoice_no",
                "amount": "widget_amount",
                "currency": "widget_currency",
                "date": "widget_date",
                "vendor": "widget_vendor",
                "category": "widget_category",
                "description": "widget_description",
                "attachment": "widget_attachment",
            }
        ),
    )


def _reload_module(monkeypatch):
    _setup_env(monkeypatch)
    import bot.config as config
    importlib.reload(config)
    import bot.state_machine as sm
    importlib.reload(sm)
    return sm


def make_image_event(
    sender_id="ou_user1",
    chat_type="p2p",
    message_id="om_001",
    chat_id="oc_001",
):
    return {
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "image",
                "content": '{"image_key": "img_xxx"}',
            },
            "sender": {"sender_id": {"open_id": sender_id}},
        }
    }


def make_text_event(
    text,
    sender_id="ou_user1",
    chat_type="p2p",
    message_id="om_002",
    chat_id="oc_001",
):
    return {
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "text",
                "content": json.dumps({"text": text}),
            },
            "sender": {"sender_id": {"open_id": sender_id}},
        }
    }


def test_idle_image_triggers_processing_and_awaiting_confirm(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    mock_fields = {
        "invoice_no": "001", "amount": "100", "currency": "CNY",
        "date": "2024-01-01", "vendor": "V", "category": "餐饮", "description": "test",
    }

    with (
        patch.object(sm.file_downloader, "download_file", return_value=(b"bytes", "inv.jpg")),
        patch.object(sm.invoice_parser, "parse_invoice", return_value=mock_fields),
        patch.object(sm.message_sender, "reply_text") as mock_reply,
        patch.object(sm.message_sender, "format_confirmation", return_value="CONFIRMATION_MSG"),
    ):
        fsm.handle_event(make_image_event())

    session = fsm.get_or_create_session("ou_user1")
    assert session.state == sm.ConversationState.AWAITING_CONFIRM
    mock_reply.assert_called_once_with("om_001", "CONFIRMATION_MSG")


def test_awaiting_confirm_confirm_keyword_creates_approval(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    # Pre-seed session into AWAITING_CONFIRM state
    session = fsm.get_or_create_session("ou_user1")
    session.state = sm.ConversationState.AWAITING_CONFIRM
    session.invoice_fields = {
        "invoice_no": "001", "amount": "100", "currency": "CNY",
        "date": "2024-01-01", "vendor": "V", "category": "餐饮", "description": "test",
    }
    session.file_bytes = b"bytes"
    session.filename = "inv.jpg"
    session.message_id = "om_001"

    with (
        patch.object(sm.attachment_uploader, "upload_approval_attachment", return_value="file-uuid"),
        patch.object(sm.approval_creator, "create_reimbursement_approval", return_value="INST-001") as mock_approve,
        patch.object(sm.message_sender, "reply_text") as mock_reply,
    ):
        fsm.handle_event(make_text_event("确认"))

    assert session.state == sm.ConversationState.IDLE
    mock_approve.assert_called_once_with("ou_user1", session.invoice_fields, "file-uuid")
    assert "INST-001" in mock_reply.call_args[0][1]


def test_awaiting_confirm_cancel_sets_idle(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    session = fsm.get_or_create_session("ou_user1")
    session.state = sm.ConversationState.AWAITING_CONFIRM
    session.message_id = "om_001"

    with patch.object(sm.message_sender, "reply_text") as mock_reply:
        fsm.handle_event(make_text_event("取消"))

    assert session.state == sm.ConversationState.IDLE
    mock_reply.assert_called_once()
    assert "取消" in mock_reply.call_args[0][1]


def test_self_trigger_ignored(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    with patch.object(sm.file_downloader, "download_file") as mock_dl:
        fsm.handle_event(make_image_event(sender_id="ou_bot_test"))
    
    mock_dl.assert_not_called()
    # Session should NOT be created for the bot user
    assert "ou_bot_test" not in fsm._sessions


def test_group_chat_ignored(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    with patch.object(sm.file_downloader, "download_file") as mock_dl:
        fsm.handle_event(make_image_event(chat_type="group"))

    mock_dl.assert_not_called()


def test_check_timeouts_sends_notification_and_resets(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    session = fsm.get_or_create_session("ou_user1")
    session.state = sm.ConversationState.AWAITING_CONFIRM
    session.message_id = "om_001"
    session.last_activity = time.time() - 9999  # far in the past

    with patch.object(sm.message_sender, "reply_text") as mock_reply:
        fsm._check_timeouts()

    assert session.state == sm.ConversationState.IDLE
    mock_reply.assert_called_once()
    assert "超时" in mock_reply.call_args[0][1]


def test_processing_state_replies_wait_message(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    session = fsm.get_or_create_session("ou_user1")
    session.state = sm.ConversationState.PROCESSING
    session.message_id = "om_001"

    with patch.object(sm.message_sender, "reply_text") as mock_reply:
        fsm.handle_event(make_text_event("hello"))

    mock_reply.assert_called_once()
    assert "正在处理中" in mock_reply.call_args[0][1]


def test_idle_text_sends_usage_hint_without_state_change(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    with patch.object(sm.message_sender, "send_text") as mock_send:
        fsm.handle_event(make_text_event("你好", message_id="om_003", chat_id="oc_hint"))

    session = fsm.get_or_create_session("ou_user1")
    assert session.state == sm.ConversationState.IDLE
    mock_send.assert_called_once_with(
        "oc_hint", "请发送发票图片或PDF文件，我将帮您提交报销申请。"
    )


def test_awaiting_confirm_correction_uses_local_invoice_parser(monkeypatch):
    sm = _reload_module(monkeypatch)
    fsm = sm.ConversationStateMachine()

    session = fsm.get_or_create_session("ou_user1")
    session.state = sm.ConversationState.AWAITING_CONFIRM
    session.invoice_fields = {
        "invoice_no": "001", "amount": "100", "currency": "CNY",
        "date": "2024-01-01", "vendor": "V", "category": "餐饮", "description": "test",
    }
    session.file_bytes = b"bytes"
    session.filename = "inv.jpg"
    session.message_id = "om_001"

    original = {
        "invoice_no": "001", "amount": "100", "currency": "CNY",
        "date": "2024-01-01", "vendor": "V", "category": "餐饮", "description": "test",
    }
    session.invoice_fields = dict(original)

    corrected = {
        "invoice_no": "001", "amount": "120", "currency": "CNY",
        "date": "2024-01-01", "vendor": "V", "category": "餐饮", "description": "test",
    }

    with (
        patch.object(sm.invoice_parser, "correct_invoice_fields", return_value=corrected) as mock_correct,
        patch.object(sm.message_sender, "format_confirmation", return_value="UPDATED_CONFIRMATION") as mock_format,
        patch.object(sm.message_sender, "reply_text") as mock_reply,
    ):
        fsm.handle_event(make_text_event("金额改成120"))

    assert session.invoice_fields == corrected
    mock_correct.assert_called_once_with(b"bytes", "inv.jpg", original, "金额改成120")
    mock_format.assert_called_once_with(corrected)
    mock_reply.assert_called_once_with("om_001", "UPDATED_CONFIRMATION")
