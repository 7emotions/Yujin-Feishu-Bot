"""Tests for bot/message_sender.py"""

import importlib
from unittest.mock import MagicMock, patch

import pytest


def _reload_sender():
    import bot.message_sender as ms

    return importlib.reload(ms)


def test_send_text_uses_chat_id_create_request():
    """send_text should create a chat_id-based text message request."""
    ms = _reload_sender()
    client = MagicMock()
    response = MagicMock()
    response.success.return_value = True
    client.im.v1.message.create.return_value = response

    with patch.object(ms, "CLIENT", client):
        ms.send_text("oc_chat123", "Hello")

    request = client.im.v1.message.create.call_args.args[0]
    assert request.receive_id_type == "chat_id"
    assert request.request_body.receive_id == "oc_chat123"
    assert request.request_body.msg_type == "text"
    assert request.request_body.content == '{"text": "Hello"}'


def test_reply_text_uses_message_id_reply_request():
    """reply_text should create a message-id based reply request."""
    ms = _reload_sender()
    client = MagicMock()
    response = MagicMock()
    response.success.return_value = True
    client.im.v1.message.reply.return_value = response

    with patch.object(ms, "CLIENT", client):
        ms.reply_text("om_msg789", "Reply text")

    request = client.im.v1.message.reply.call_args.args[0]
    assert request.message_id == "om_msg789"
    assert request.request_body.msg_type == "text"
    assert request.request_body.content == '{"text": "Reply text"}'


def test_send_text_failure_raises_runtime_error():
    """Non-success create response should raise RuntimeError."""
    ms = _reload_sender()
    client = MagicMock()
    response = MagicMock()
    response.success.return_value = False
    response.code = 999
    response.msg = "send failed"
    response.get_log_id.return_value = "log-send"
    client.im.v1.message.create.return_value = response

    with patch.object(ms, "CLIENT", client):
        with pytest.raises(RuntimeError, match="Feishu send message failed"):
            ms.send_text("oc_chat", "message")


def test_reply_text_failure_raises_runtime_error():
    """Non-success reply response should raise RuntimeError."""
    ms = _reload_sender()
    client = MagicMock()
    response = MagicMock()
    response.success.return_value = False
    response.code = 888
    response.msg = "reply failed"
    response.get_log_id.return_value = "log-reply"
    client.im.v1.message.reply.return_value = response

    with patch.object(ms, "CLIENT", client):
        with pytest.raises(RuntimeError, match="Feishu reply message failed"):
            ms.reply_text("om_msg", "reply")


def test_confirmation_template_has_all_fields():
    """CONFIRMATION_TEMPLATE must contain all 7 required invoice fields."""
    ms = _reload_sender()

    required_fields = ["invoice_no", "amount", "currency", "date", "vendor", "category", "description"]
    for field in required_fields:
        assert f"{{{field}}}" in ms.CONFIRMATION_TEMPLATE


def test_format_confirmation_fills_template():
    """format_confirmation should fill in all fields from invoice dict."""
    ms = _reload_sender()

    fields = {
        "invoice_no": "INV-001",
        "amount": "123.45",
        "currency": "CNY",
        "date": "2024-01-15",
        "vendor": "测试公司",
        "category": "餐饮",
        "description": "商务午餐",
    }
    result = ms.format_confirmation(fields)
    assert "INV-001" in result
    assert "123.45" in result
    assert "CNY" in result
    assert "测试公司" in result
