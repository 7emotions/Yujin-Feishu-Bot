"""Tests for bot/token_manager.py"""
import time
from unittest.mock import MagicMock, patch

import pytest


def _reload_token_manager(monkeypatch):
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")

    import importlib

    import bot.config as config

    importlib.reload(config)

    import bot.token_manager as tm_module

    importlib.reload(tm_module)
    return tm_module


def test_get_token_calls_refresh_on_first_call(monkeypatch):
    """First call should trigger a refresh since token is empty."""
    tm_module = _reload_token_manager(monkeypatch)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "test_token_abc123",
        "expire": 7200,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("bot.token_manager.requests.post", return_value=mock_response) as mock_post:
        token = tm_module.token_manager.get_token()

    assert token == "test_token_abc123"
    mock_post.assert_called_once()


def test_get_token_no_refresh_when_valid(monkeypatch):
    """Should NOT refresh if token is valid and not expiring soon."""
    tm_module = _reload_token_manager(monkeypatch)

    tm_module.token_manager._token = "existing_token"
    tm_module.token_manager._expires_at = time.time() + 3600

    with patch("bot.token_manager.requests.post") as mock_post:
        token = tm_module.token_manager.get_token()

    assert token == "existing_token"
    mock_post.assert_not_called()


def test_get_token_refresh_when_expiring_soon(monkeypatch):
    """Should refresh if token expires in less than 5 minutes."""
    tm_module = _reload_token_manager(monkeypatch)

    tm_module.token_manager._token = "expiring_soon_token"
    tm_module.token_manager._expires_at = time.time() + 240

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "new_refreshed_token",
        "expire": 7200,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("bot.token_manager.requests.post", return_value=mock_response) as mock_post:
        token = tm_module.token_manager.get_token()

    assert token == "new_refreshed_token"
    mock_post.assert_called_once()


def test_failed_token_refresh_raises_runtime_error(monkeypatch):
    """API error code != 0 should raise RuntimeError."""
    tm_module = _reload_token_manager(monkeypatch)

    tm_module.token_manager._token = ""
    tm_module.token_manager._expires_at = 0.0

    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 99991663, "msg": "app_id or app_secret invalid"}
    mock_response.raise_for_status = MagicMock()

    with patch("bot.token_manager.requests.post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="Failed to get tenant_access_token"):
            tm_module.token_manager.get_token()
