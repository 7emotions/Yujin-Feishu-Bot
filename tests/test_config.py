"""Tests for bot/config.py"""
import os

import pytest


def test_confirm_keywords_is_list(monkeypatch):
    """CONFIRM_KEYWORDS should be a list, not a string."""
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")
    monkeypatch.setenv("CONFIRM_KEYWORDS", "confirm,yes,确认")

    # Re-import to pick up monkeypatched env vars
    import importlib
    import bot.config as config

    importlib.reload(config)

    assert isinstance(config.CONFIRM_KEYWORDS, list)
    assert "确认" in config.CONFIRM_KEYWORDS


def test_cancel_keywords_is_list(monkeypatch):
    """CANCEL_KEYWORDS should be a list, not a string."""
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")
    monkeypatch.setenv("CANCEL_KEYWORDS", "cancel,取消,算了")

    import importlib
    import bot.config as config

    importlib.reload(config)

    assert isinstance(config.CANCEL_KEYWORDS, list)
    assert "取消" in config.CANCEL_KEYWORDS


def test_timeout_is_int(monkeypatch):
    """TIMEOUT_SECONDS should be an integer."""
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")
    monkeypatch.setenv("AWAITING_CONFIRM_TIMEOUT_SECONDS", "300")

    import importlib
    import bot.config as config

    importlib.reload(config)

    assert isinstance(config.TIMEOUT_SECONDS, int)
    assert config.TIMEOUT_SECONDS == 300


def test_missing_required_key_raises_value_error(monkeypatch):
    """Missing APP_ID should raise ValueError."""
    monkeypatch.setenv("APP_ID", "")
    monkeypatch.setenv("APP_SECRET", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")

    import importlib
    import bot.config as config

    with pytest.raises(ValueError):
        importlib.reload(config)


def test_openai_api_key_is_optional(monkeypatch):
    """OPENAI_API_KEY should no longer be required for local-only runtime."""
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")

    import importlib
    import bot.config as config

    importlib.reload(config)

    assert config.OPENAI_API_KEY == ""
