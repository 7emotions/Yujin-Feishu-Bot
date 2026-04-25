"""Tests for bot/file_downloader.py"""
import json
from unittest.mock import MagicMock, patch

import pytest


def _setup_env(monkeypatch):
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")


def test_image_download_uses_correct_url_and_key(monkeypatch):
    """Image download should use image_key and type=image."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.file_downloader as fd

    importlib.reload(fd)

    fd.token_manager.get_token = MagicMock(return_value="fake_token")

    content_dict = {"image_key": "img_abc123xyz"}
    content_str = json.dumps(content_dict)

    mock_response = MagicMock()
    mock_response.content = b"fake_image_bytes"
    mock_response.raise_for_status = MagicMock()

    with patch("bot.file_downloader.requests.get", return_value=mock_response) as mock_get:
        file_bytes, filename = fd.download_file("om_msg123", "image", content_str)

    call_args = mock_get.call_args
    assert "img_abc123xyz" in call_args[0][0]
    assert call_args[1]["params"] == {"type": "image"}
    assert call_args[1]["headers"]["Authorization"] == "Bearer fake_token"

    assert file_bytes == b"fake_image_bytes"
    assert filename == "invoice.jpg"


def test_file_download_uses_file_key_and_preserves_filename(monkeypatch):
    """File download should use file_key and preserve original filename."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.file_downloader as fd

    importlib.reload(fd)

    fd.token_manager.get_token = MagicMock(return_value="fake_token")

    content_dict = {"file_key": "file_xyz789", "file_name": "receipt.pdf"}
    content_str = json.dumps(content_dict)

    mock_response = MagicMock()
    mock_response.content = b"fake_pdf_bytes"
    mock_response.raise_for_status = MagicMock()

    with patch("bot.file_downloader.requests.get", return_value=mock_response) as mock_get:
        file_bytes, filename = fd.download_file("om_msg456", "file", content_str)

    call_args = mock_get.call_args
    assert "file_xyz789" in call_args[0][0]
    assert call_args[1]["params"] == {"type": "file"}

    assert file_bytes == b"fake_pdf_bytes"
    assert filename == "receipt.pdf"


def test_invalid_message_type_raises_value_error(monkeypatch):
    """Unsupported message_type should raise ValueError."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.file_downloader as fd

    importlib.reload(fd)

    with pytest.raises(ValueError, match="Unsupported message_type"):
        fd.download_file("om_msg789", "sticker", "{}")


def test_content_str_is_double_parsed(monkeypatch):
    """Verify that content_str undergoes json.loads() — not used as raw string."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.file_downloader as fd

    importlib.reload(fd)

    fd.token_manager.get_token = MagicMock(return_value="fake_token")

    content_str = json.dumps({"image_key": "img_double_parse_test"})

    mock_response = MagicMock()
    mock_response.content = b"image_data"
    mock_response.raise_for_status = MagicMock()

    with patch("bot.file_downloader.requests.get", return_value=mock_response):
        file_bytes, _ = fd.download_file("om_test", "image", content_str)

    assert file_bytes == b"image_data"


def test_content_mapping_is_accepted(monkeypatch):
    """download_file should accept already-decoded message.content mappings."""
    _setup_env(monkeypatch)

    import importlib
    import bot.config as config

    importlib.reload(config)
    import bot.token_manager as tm

    importlib.reload(tm)
    import bot.file_downloader as fd

    importlib.reload(fd)

    fd.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.content = b"fake_pdf_bytes"
    mock_response.raise_for_status = MagicMock()

    with patch("bot.file_downloader.requests.get", return_value=mock_response):
        file_bytes, filename = fd.download_file(
            "om_msg456",
            "file",
            {"file_key": "file_xyz789", "file_name": "receipt.pdf"},
        )

    assert file_bytes == b"fake_pdf_bytes"
    assert filename == "receipt.pdf"
