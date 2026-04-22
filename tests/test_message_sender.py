"""Tests for bot/message_sender.py"""

import importlib
from unittest.mock import MagicMock, patch

import pytest


def _reload_sender():
    import bot.message_sender as ms

    return importlib.reload(ms)


def test_send_text_uses_lark_cli_no_proxy_env():
    """send_text must call lark-cli with LARK_CLI_NO_PROXY=1 in env."""
    ms = _reload_sender()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("bot.message_sender.subprocess.run", return_value=mock_result) as mock_run:
        ms.send_text("oc_chat123", "Hello")

    env = mock_run.call_args.kwargs.get("env", {})
    assert env.get("LARK_CLI_NO_PROXY") == "1"


def test_send_text_passes_correct_args():
    """send_text should call lark-cli with correct arguments."""
    ms = _reload_sender()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("bot.message_sender.subprocess.run", return_value=mock_result) as mock_run:
        ms.send_text("oc_chat123", "Test message")

    cmd = mock_run.call_args.args[0]
    assert cmd[:4] == ["lark-cli", "im", "messages", "send"]
    assert "--chat-id" in cmd
    assert "oc_chat123" in cmd
    assert "--text" in cmd
    assert "Test message" in cmd


def test_reply_text_passes_message_id():
    """reply_text should call lark-cli reply with correct message_id."""
    ms = _reload_sender()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("bot.message_sender.subprocess.run", return_value=mock_result) as mock_run:
        ms.reply_text("om_msg789", "Reply text")

    cmd = mock_run.call_args.args[0]
    assert cmd[:4] == ["lark-cli", "im", "messages", "reply"]
    assert "--message-id" in cmd
    assert "om_msg789" in cmd
    assert "--text" in cmd
    assert "Reply text" in cmd


def test_non_zero_exit_raises_runtime_error():
    """Non-zero subprocess exit should raise RuntimeError."""
    ms = _reload_sender()

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "lark-cli error"

    with patch("bot.message_sender.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError):
            ms.send_text("oc_chat", "message")


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
