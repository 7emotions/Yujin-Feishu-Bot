"""Tests for bot/invoice_parser.py"""

import importlib


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
    monkeypatch.setattr(invoice_parser, "_load_images", lambda _file_bytes, _filename: ["image"])
    monkeypatch.setattr(
        invoice_parser,
        "_generate_invoice_json",
        lambda _images: (
            '{"invoice_no":"INV-001","amount":"100.00","currency":"CNY","date":"2024-01-01",'
            '"vendor":"供应商","category":"餐饮","description":"午餐"}'
        ),
    )

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


def test_load_images_pdf_uses_pdf_renderer(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)
    calls: list[bytes] = []

    def fake_pdf_loader(file_bytes: bytes):
        calls.append(file_bytes)
        return ["page1"]

    monkeypatch.setattr(invoice_parser, "_load_pdf_images", fake_pdf_loader)

    result = invoice_parser._load_images(b"fakepdfbytes", "invoice.pdf")

    assert result == ["page1"]
    assert calls == [b"fakepdfbytes"]


def test_load_images_pdf_magic_bytes_use_pdf_renderer(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)
    calls: list[bytes] = []

    def fake_pdf_loader(file_bytes: bytes):
        calls.append(file_bytes)
        return ["page1"]

    monkeypatch.setattr(invoice_parser, "_load_pdf_images", fake_pdf_loader)

    result = invoice_parser._load_images(b"%PDF-1.7\nfake", "receipt")

    assert result == ["page1"]
    assert calls == [b"%PDF-1.7\nfake"]


def test_parse_invoice_missing_field_returns_empty_string(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)
    monkeypatch.setattr(invoice_parser, "_load_images", lambda _file_bytes, _filename: ["image"])
    monkeypatch.setattr(invoice_parser, "_generate_invoice_json", lambda _images: '{"invoice_no":"001","amount":"100"}')

    result = invoice_parser.parse_invoice(b"fakeimgbytes", "invoice.jpg")

    assert result["invoice_no"] == "001"
    assert result["amount"] == "100"
    for key in ["currency", "date", "vendor", "category", "description"]:
        assert result[key] == ""


def test_parse_invoice_json_error_returns_empty_dict(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)
    monkeypatch.setattr(invoice_parser, "_load_images", lambda _file_bytes, _filename: ["image"])
    monkeypatch.setattr(invoice_parser, "_generate_invoice_json", lambda _images: "Sorry, I cannot process this.")

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
    monkeypatch.setattr(invoice_parser, "_load_images", lambda _file_bytes, _filename: ["image"])
    monkeypatch.setattr(invoice_parser, "_generate_invoice_json", lambda _images: '```json\n{"invoice_no":"X001"}\n```')

    result = invoice_parser.parse_invoice(b"fakeimgbytes", "invoice.jpg")

    assert result["invoice_no"] == "X001"


def test_parse_invoice_extracts_json_from_wrapped_text(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)
    monkeypatch.setattr(invoice_parser, "_load_images", lambda _file_bytes, _filename: ["image"])
    monkeypatch.setattr(
        invoice_parser,
        "_generate_invoice_json",
        lambda _images: '好的，结果如下：```json\n{"invoice_no":"X009","amount":"100"}\n```',
    )

    result = invoice_parser.parse_invoice(b"fakeimgbytes", "invoice.jpg")

    assert result["invoice_no"] == "X009"
    assert result["amount"] == "100"


def test_correct_invoice_fields_returns_normalized_json(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)
    monkeypatch.setattr(invoice_parser, "_load_images", lambda _file_bytes, _filename: ["image"])
    monkeypatch.setattr(
        invoice_parser,
        "_generate_correction_json",
        lambda _images, _fields, _text: '{"invoice_no":"X002","amount":200,"currency":"CNY"}',
    )

    result = invoice_parser.correct_invoice_fields(
        b"fakeimgbytes",
        "invoice.jpg",
        {
            "invoice_no": "X001",
            "amount": "100",
            "currency": "CNY",
            "date": "",
            "vendor": "",
            "category": "",
            "description": "",
        },
        "金额改成200",
    )

    assert result["invoice_no"] == "X002"
    assert result["amount"] == "200"
    assert result["currency"] == "CNY"


def test_correct_invoice_fields_fallback_keeps_existing_fields(monkeypatch):
    invoice_parser = _reload_parser(monkeypatch)
    monkeypatch.setattr(invoice_parser, "_load_images", lambda _file_bytes, _filename: ["image"])
    monkeypatch.setattr(invoice_parser, "_generate_correction_json", lambda _images, _fields, _text: "")

    original = {
        "invoice_no": "X001",
        "amount": "100",
        "currency": "CNY",
        "date": "2024-01-01",
        "vendor": "供应商",
        "category": "餐饮",
        "description": "午餐",
    }
    result = invoice_parser.correct_invoice_fields(
        b"fakeimgbytes",
        "invoice.jpg",
        original,
        "金额改成200",
    )

    assert result == original
