"""Tests for bot/approval_creator.py"""
import json
from unittest.mock import MagicMock, patch

import pytest


def _setup_env(monkeypatch):
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver_test")
    monkeypatch.setenv("APPROVAL_CODE", "TEST-APPROVAL-CODE-1234")


def test_create_approval_returns_instance_code(monkeypatch):
    """Should return instance_code from API response."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.approval_creator as ac

    importlib.reload(ac)

    ac.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": 0,
        "data": {"instance_code": "81D31358-93AF-92D6-7425-01A5D67C4E71"},
    }
    mock_response.raise_for_status = MagicMock()

    invoice_fields = {
        "invoice_no": "INV-001",
        "amount": "100.00",
        "currency": "CNY",
        "date": "2024-01-01",
        "vendor": "供应商",
        "category": "餐饮",
        "description": "午餐",
    }

    with patch("bot.approval_creator.requests.post", return_value=mock_response):
        result = ac.create_reimbursement_approval(
            "ou_user123", invoice_fields, "FILE-CODE-UUID"
        )

    assert result == "81D31358-93AF-92D6-7425-01A5D67C4E71"


def test_form_is_json_string_not_dict(monkeypatch):
    """The form field in the request payload must be a JSON string (double-encoded)."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.approval_creator as ac

    importlib.reload(ac)

    ac.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": 0,
        "data": {"instance_code": "INST-CODE-TEST"},
    }
    mock_response.raise_for_status = MagicMock()

    invoice_fields = {
        k: "test"
        for k in [
            "invoice_no",
            "amount",
            "currency",
            "date",
            "vendor",
            "category",
            "description",
        ]
    }

    with patch("bot.approval_creator.requests.post", return_value=mock_response) as mock_post:
        ac.create_reimbursement_approval("ou_user", invoice_fields, "file_code_123")

    call_kwargs = mock_post.call_args[1]
    payload = call_kwargs.get("json", {})

    assert isinstance(payload["form"], str), "form must be a JSON string (double-encoded)"

    parsed_form = json.loads(payload["form"])
    assert isinstance(parsed_form, list)


def test_attachment_field_value_is_array(monkeypatch):
    """Attachment field value must be an array [file_code], not a string."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.approval_creator as ac

    importlib.reload(ac)

    ac.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 0, "data": {"instance_code": "TEST"}}
    mock_response.raise_for_status = MagicMock()

    invoice_fields = {
        k: "test"
        for k in [
            "invoice_no",
            "amount",
            "currency",
            "date",
            "vendor",
            "category",
            "description",
        ]
    }

    with patch("bot.approval_creator.requests.post", return_value=mock_response) as mock_post:
        ac.create_reimbursement_approval("ou_user", invoice_fields, "MY-FILE-CODE")

    payload = mock_post.call_args[1]["json"]
    form = json.loads(payload["form"])

    attachment_field = next((f for f in form if f.get("type") == "attachmentV2"), None)
    assert attachment_field is not None, "attachmentV2 field not found in form"
    assert isinstance(attachment_field["value"], list), "attachment value must be a list"
    assert "MY-FILE-CODE" in attachment_field["value"]


def test_missing_approval_code_raises_value_error(monkeypatch):
    """If APPROVAL_CODE not set, should raise ValueError."""
    _setup_env(monkeypatch)
    monkeypatch.setenv("APPROVAL_CODE", "")

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.approval_creator as ac

    importlib.reload(ac)

    invoice_fields = {
        k: "test"
        for k in [
            "invoice_no",
            "amount",
            "currency",
            "date",
            "vendor",
            "category",
            "description",
        ]
    }

    with pytest.raises(ValueError, match="APPROVAL_CODE"):
        ac.create_reimbursement_approval("ou_user", invoice_fields, "file_code")


def test_api_error_raises_runtime_error(monkeypatch):
    """API code != 0 should raise RuntimeError."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.approval_creator as ac

    importlib.reload(ac)

    ac.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 1, "msg": "approval failed"}
    mock_response.raise_for_status = MagicMock()

    invoice_fields = {
        k: "test"
        for k in [
            "invoice_no",
            "amount",
            "currency",
            "date",
            "vendor",
            "category",
            "description",
        ]
    }

    with patch("bot.approval_creator.requests.post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="Failed to create approval instance"):
            ac.create_reimbursement_approval("ou_user", invoice_fields, "file_code")
