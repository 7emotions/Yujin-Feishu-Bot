# pyright: reportMissingParameterType=false, reportUnknownParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportPrivateLocalImportUsage=false, reportUnusedCallResult=false, reportAny=false, reportUnknownLambdaType=false, reportUnusedImport=false, reportMissingTypeArgument=false
import importlib
import json
from pathlib import Path
from unittest.mock import patch


FIXTURES_DIR = Path(__file__).parent / "fixtures"


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


def _reload_all(monkeypatch):
    _setup_env(monkeypatch)
    import bot.config as config
    importlib.reload(config)
    import bot.token_manager as tm
    importlib.reload(tm)
    import bot.file_downloader as fd
    importlib.reload(fd)
    import bot.invoice_parser as ip
    importlib.reload(ip)
    import bot.attachment_uploader as au
    importlib.reload(au)
    import bot.message_sender as ms
    importlib.reload(ms)
    import bot.approval_creator as ac
    importlib.reload(ac)
    import bot.state_machine as sm
    importlib.reload(sm)
    return sm


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def test_full_image_flow_confirm(monkeypatch):
    sm = _reload_all(monkeypatch)
    fsm = sm.ConversationStateMachine()

    image_event = _load_fixture("sample_event_image.json")
    sender_id = image_event["event"]["sender"]["sender_id"]["open_id"]

    mock_fields = {
        "invoice_no": "INV-2024-001",
        "amount": "288.00",
        "currency": "CNY",
        "date": "2024-04-22",
        "vendor": "北京餐饮有限公司",
        "category": "餐饮",
        "description": "团队午餐",
    }

    reply_calls = []

    with (
        patch.object(sm.file_downloader, "download_file", return_value=(b"fakebytes", "invoice.jpg")),
        patch.object(sm.invoice_parser, "parse_invoice", return_value=mock_fields),
        patch.object(sm.message_sender, "reply_text", side_effect=lambda mid, txt: reply_calls.append((mid, txt))),
        patch.object(sm.message_sender, "format_confirmation", return_value="CONFIRMATION_TEXT"),
        patch.object(sm.attachment_uploader, "upload_approval_attachment", return_value="file-code-uuid"),
        patch.object(sm.approval_creator, "create_reimbursement_approval", return_value="INSTANCE-2024-001") as mock_approve,
    ):
        # Step 1: user sends invoice image
        fsm.handle_event(image_event)

        session = fsm.get_or_create_session(sender_id)
        assert session.state == sm.ConversationState.AWAITING_CONFIRM, (
            f"Expected AWAITING_CONFIRM, got {session.state}"
        )
        assert len(reply_calls) == 1, "Should have sent one confirmation message"
        assert reply_calls[0][1] == "CONFIRMATION_TEXT"

        # Step 2: user replies "确认"
        confirm_event = {
            "event": {
                "message": {
                    "message_id": "om_confirm_001",
                    "chat_id": "oc_fixture_001",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": json.dumps({"text": "确认"}),
                },
                "sender": {"sender_id": {"open_id": sender_id}},
            }
        }
        fsm.handle_event(confirm_event)

        assert session.state == sm.ConversationState.IDLE, (
            f"Expected IDLE after confirm, got {session.state}"
        )
        mock_approve.assert_called_once_with(sender_id, mock_fields, "file-code-uuid")
        assert len(reply_calls) == 2, "Should have sent success message after confirm"
        assert "INSTANCE-2024-001" in reply_calls[1][1]


def test_full_image_flow_cancel(monkeypatch):
    sm = _reload_all(monkeypatch)
    fsm = sm.ConversationStateMachine()

    image_event = _load_fixture("sample_event_image.json")
    sender_id = image_event["event"]["sender"]["sender_id"]["open_id"]

    mock_fields = {k: "" for k in ["invoice_no", "amount", "currency", "date", "vendor", "category", "description"]}

    reply_calls = []

    with (
        patch.object(sm.file_downloader, "download_file", return_value=(b"bytes", "invoice.jpg")),
        patch.object(sm.invoice_parser, "parse_invoice", return_value=mock_fields),
        patch.object(sm.message_sender, "reply_text", side_effect=lambda mid, txt: reply_calls.append((mid, txt))),
        patch.object(sm.message_sender, "format_confirmation", return_value="CONFIRMATION_TEXT"),
    ):
        fsm.handle_event(image_event)

        cancel_event = {
            "event": {
                "message": {
                    "message_id": "om_cancel_001",
                    "chat_id": "oc_fixture_001",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": json.dumps({"text": "取消"}),
                },
                "sender": {"sender_id": {"open_id": sender_id}},
            }
        }
        fsm.handle_event(cancel_event)

    session = fsm.get_or_create_session(sender_id)
    assert session.state == sm.ConversationState.IDLE
    assert len(reply_calls) == 2
    assert "取消" in reply_calls[1][1]


def test_bot_self_trigger_ignored_integration(monkeypatch):
    sm = _reload_all(monkeypatch)
    fsm = sm.ConversationStateMachine()

    self_event = {
        "event": {
            "message": {
                "message_id": "om_self_001",
                "chat_id": "oc_fixture_001",
                "chat_type": "p2p",
                "message_type": "image",
                "content": '{"image_key": "img_xxx"}',
            },
            "sender": {"sender_id": {"open_id": "ou_bot_test"}},
        }
    }

    with patch.object(sm.file_downloader, "download_file") as mock_dl:
        fsm.handle_event(self_event)

    mock_dl.assert_not_called()


def test_fixture_file_exists():
    fixture = FIXTURES_DIR / "sample_event_image.json"
    assert fixture.exists(), f"Fixture not found: {fixture}"
    data = json.loads(fixture.read_text())
    assert data["event"]["message"]["chat_type"] == "p2p"
    assert data["event"]["message"]["message_type"] == "image"


def test_fixture_pdf_file_exists():
    fixture = FIXTURES_DIR / "sample_event_file.json"
    assert fixture.exists(), f"Fixture not found: {fixture}"
    data = json.loads(fixture.read_text())
    assert data["event"]["message"]["chat_type"] == "p2p"
    assert data["event"]["message"]["message_type"] == "file"
    assert "file_key" in json.loads(data["event"]["message"]["content"])
