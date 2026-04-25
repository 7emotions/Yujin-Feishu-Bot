"""Tests for bot/main.py"""

# pyright: reportAny=false, reportExplicitAny=false, reportPrivateUsage=false, reportPrivateLocalImportUsage=false, reportUnusedCallResult=false, reportUnknownArgumentType=false, reportIndexIssue=false, reportArgumentType=false, reportUnknownLambdaType=false, reportUnknownMemberType=false

import importlib
import json
from types import SimpleNamespace

from _pytest.monkeypatch import MonkeyPatch


def _setup_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_bot_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver_test")


def _reload_main(monkeypatch: MonkeyPatch):
    _setup_env(monkeypatch)
    import bot.config as config
    importlib.reload(config)
    import bot.state_machine as sm
    importlib.reload(sm)
    import bot.main as main
    importlib.reload(main)
    return main


def _make_receive_event(event_id: str = "evt-001", message_id: str = "om_001"):
    return SimpleNamespace(
        header=SimpleNamespace(event_id=event_id),
        event=SimpleNamespace(
            sender=SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_user1")),
            message=SimpleNamespace(
                message_id=message_id,
                chat_id="oc_001",
                chat_type="p2p",
                message_type="text",
                content=json.dumps({"text": "hello"}),
            ),
        ),
    )


def test_handle_message_receive_enqueues_without_inline_processing(monkeypatch: MonkeyPatch) -> None:
    main = _reload_main(monkeypatch)
    event = _make_receive_event()

    handled = []
    monkeypatch.setattr(main.state_machine, "handle_event", lambda evt: handled.append(evt))

    main._handle_message_receive(event)

    assert handled == []
    queued = main._event_queue.get_nowait()
    assert queued["event"]["message"]["message_id"] == "om_001"
    assert queued["_event_key"] == "evt-001"
    main._event_queue.task_done()


def test_handle_message_receive_dedupes_pending_and_completed(monkeypatch: MonkeyPatch) -> None:
    main = _reload_main(monkeypatch)
    event = _make_receive_event(event_id="evt-dup")

    main._handle_message_receive(event)
    first = main._event_queue.get_nowait()
    assert first["_event_key"] == "evt-dup"

    main._handle_message_receive(event)
    assert main._event_queue.empty()

    main._process_queued_event(first)
    main._event_queue.task_done()

    main._handle_message_receive(event)
    assert main._event_queue.empty()


def test_process_queued_event_routes_to_state_machine_and_marks_complete(monkeypatch: MonkeyPatch) -> None:
    main = _reload_main(monkeypatch)
    adapted_event = main._adapt_event(_make_receive_event(event_id="evt-process", message_id="om_777"))

    handled = []
    monkeypatch.setattr(main.state_machine, "handle_event", lambda evt: handled.append(evt))
    main._pending_event_keys.add("evt-process")

    main._process_queued_event(adapted_event)

    assert len(handled) == 1
    assert handled[0]["event"]["message"]["message_id"] == "om_777"
    assert "evt-process" not in main._pending_event_keys
    assert "evt-process" in main._completed_event_keys


def test_adapt_event_prefers_header_event_id(monkeypatch: MonkeyPatch) -> None:
    main = _reload_main(monkeypatch)
    adapted = main._adapt_event(_make_receive_event(event_id="evt-header", message_id="om_999"))

    assert adapted["_event_key"] == "evt-header"
    assert adapted["event"]["message"]["message_id"] == "om_999"


def test_adapt_event_falls_back_to_message_id(monkeypatch: MonkeyPatch) -> None:
    main = _reload_main(monkeypatch)
    event = _make_receive_event(event_id="", message_id="om_fallback")
    event.header = SimpleNamespace(event_id=None)

    adapted = main._adapt_event(event)

    assert adapted["_event_key"] == "om_fallback"
