"""Tests for bot/attachment_uploader.py"""

import importlib
from unittest.mock import MagicMock, patch

import pytest


def _setup_env(monkeypatch):
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver")


def _reload_uploader():
    import bot.config as config
    import bot.token_manager as tm
    import bot.attachment_uploader as au

    importlib.reload(config)
    importlib.reload(tm)
    return importlib.reload(au)


def test_upload_uses_www_feishu_cn_url(monkeypatch):
    """Upload must use www.feishu.cn, NOT open.feishu.cn."""
    _setup_env(monkeypatch)
    au = _reload_uploader()

    au.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 0, "data": {"code": "D93653C3-2609-4EE0-8041-61DC1D84F0B5"}}
    mock_response.raise_for_status = MagicMock()

    with patch("bot.attachment_uploader.requests.post", return_value=mock_response) as mock_post:
        file_code = au.upload_approval_attachment(b"test_bytes", "invoice.jpg")

    call_url = mock_post.call_args[0][0]
    assert "www.feishu.cn" in call_url
    assert "open.feishu.cn" not in call_url
    assert file_code == "D93653C3-2609-4EE0-8041-61DC1D84F0B5"


def test_upload_sends_multipart_with_name_type_content(monkeypatch):
    """Upload request must include name, type, content in multipart form."""
    _setup_env(monkeypatch)
    au = _reload_uploader()

    au.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 0, "data": {"code": "ABCD1234-5678-90AB-CDEF-ABCDEF123456"}}
    mock_response.raise_for_status = MagicMock()

    with patch("bot.attachment_uploader.requests.post", return_value=mock_response) as mock_post:
        au.upload_approval_attachment(b"pdf_bytes", "receipt.pdf")

    call_kwargs = mock_post.call_args[1]
    assert "files" in call_kwargs
    files = call_kwargs["files"]
    assert "name" in files
    assert "type" in files
    assert "content" in files
    assert files["type"] == (None, "attachment")


def test_upload_uses_image_type_for_images(monkeypatch):
    """Image attachments should send type=image, not the MIME string."""
    _setup_env(monkeypatch)
    au = _reload_uploader()

    au.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 0, "data": {"code": "IMG-CODE"}}
    mock_response.raise_for_status = MagicMock()

    with patch("bot.attachment_uploader.requests.post", return_value=mock_response) as mock_post:
        au.upload_approval_attachment(b"img_bytes", "invoice.jpg")

    files = mock_post.call_args[1]["files"]
    assert files["type"] == (None, "image")
    assert files["content"][2] == "image/jpeg"


def test_upload_returns_file_code_uuid(monkeypatch):
    """Should return the file_code from data.code."""
    _setup_env(monkeypatch)
    au = _reload_uploader()

    au.token_manager.get_token = MagicMock(return_value="fake_token")

    expected_code = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 0, "data": {"code": expected_code}}
    mock_response.raise_for_status = MagicMock()

    with patch("bot.attachment_uploader.requests.post", return_value=mock_response):
        result = au.upload_approval_attachment(b"bytes", "invoice.jpg")

    assert result == expected_code


def test_upload_raises_runtime_error_on_api_error(monkeypatch):
    """Non-zero code in response should raise RuntimeError."""
    _setup_env(monkeypatch)
    au = _reload_uploader()

    au.token_manager.get_token = MagicMock(return_value="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = {"code": 1, "msg": "upload failed"}
    mock_response.raise_for_status = MagicMock()

    with patch("bot.attachment_uploader.requests.post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="Failed to upload attachment"):
            au.upload_approval_attachment(b"bytes", "invoice.jpg")
