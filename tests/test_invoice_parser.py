"""Tests for bot/invoice_parser.py"""

import importlib
import os
from unittest.mock import MagicMock


def _setup_env(monkeypatch):
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_testbot")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver_test")


def _reload_parser(monkeypatch):
    _setup_env(monkeypatch)
    import bot.config as config

    importlib.reload(config)
    import bot.invoice_parser as invoice_parser

    importlib.reload(invoice_parser)
    return invoice_parser


def test_parse_invoice_image_returns_all_7_keys(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        '{"invoice_no":"INV-001","amount":"100.00","currency":"CNY","date":"2024-01-01",'
        '"vendor":"供应商","category":"餐饮","description":"午餐"}'
    )
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(invoice_parser, "OpenAI", MagicMock(return_value=mock_client))

    result = invoice_parser.parse_invoice(b"fakeimgbytes", "invoice.jpg")

    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "invoice_no",
        "amount",
        "currency",
        "date",
        "vendor",
        "category",
        "description",
    }


def test_parse_invoice_pdf_sends_input_file_type(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "{}"
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(invoice_parser, "OpenAI", MagicMock(return_value=mock_client))

    invoice_parser.parse_invoice(b"fakepdfbytes", "invoice.pdf")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    user_message = messages[1]
    assert "input_file" in str(user_message["content"]) or "file_data" in str(user_message["content"])


def test_parse_invoice_missing_field_returns_empty_string(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"invoice_no":"001","amount":"100"}'
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(invoice_parser, "OpenAI", MagicMock(return_value=mock_client))

    result = invoice_parser.parse_invoice(b"fakeimgbytes", "invoice.jpg")

    assert result["invoice_no"] == "001"
    assert result["amount"] == "100"
    for key in ["currency", "date", "vendor", "category", "description"]:
        assert result[key] == ""


def test_parse_invoice_json_error_returns_empty_dict(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Sorry, I cannot process this."
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(invoice_parser, "OpenAI", MagicMock(return_value=mock_client))

    result = invoice_parser.parse_invoice(b"fakeimgbytes", "invoice.jpg")

    assert result == {
        "invoice_no": "",
        "amount": "",
        "currency": "",
        "date": "",
        "vendor": "",
        "category": "",
        "description": "",
    }


def test_parse_invoice_strips_markdown_fences(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '```json\n{"invoice_no":"X001"}\n```'
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(invoice_parser, "OpenAI", MagicMock(return_value=mock_client))

    result = invoice_parser.parse_invoice(b"fakeimgbytes", "invoice.jpg")

    assert result["invoice_no"] == "X001"
