"""Tests for bot/main.py"""

import importlib
import json
import sys
from unittest.mock import MagicMock, patch, call


def _setup_env(monkeypatch):
    monkeypatch.setenv("APP_ID", "cli_test")
    monkeypatch.setenv("APP_SECRET", "test_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_USER_ID", "ou_bot_test")
    monkeypatch.setenv("APPROVER_OPEN_ID", "ou_approver_test")


def _reload_main(monkeypatch):
    _setup_env(monkeypatch)
    import bot.config as config
    importlib.reload(config)
    import bot.state_machine as sm
    importlib.reload(sm)
    import bot.main as main
    importlib.reload(main)
    return main


def test_build_env_has_lark_cli_no_proxy(monkeypatch):
    main = _reload_main(monkeypatch)
    env = main._build_env()
    assert env["LARK_CLI_NO_PROXY"] == "1"


def test_build_env_has_nvm_bin_in_path(monkeypatch):
    main = _reload_main(monkeypatch)
    env = main._build_env()
    assert ".nvm" in env["PATH"]


def test_event_routing_to_state_machine(monkeypatch):
    """NDJSON lines are parsed and routed to state_machine.handle_event."""
    main = _reload_main(monkeypatch)

    event = {
        "event": {
            "message": {
                "message_id": "om_001",
                "chat_id": "oc_001",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
            },
            "sender": {"sender_id": {"open_id": "ou_user1"}},
        }
    }

    handled_events = []

    def fake_handle(evt):
        handled_events.append(evt)

    # Simulate one line of NDJSON then EOF
    line = json.dumps(event)
    mock_stdout = iter([line + "\n"])

    mock_proc = MagicMock()
    mock_proc.stdout = mock_stdout
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0

    with patch.object(main.state_machine, "handle_event", side_effect=fake_handle):
        with patch("subprocess.Popen", return_value=mock_proc):
            # Run one iteration only — patch time.sleep to raise after first reconnect attempt
            call_count = [0]
            original_sleep = __import__("time").sleep

            def fake_sleep(n):
                call_count[0] += 1
                if call_count[0] >= 1:
                    raise KeyboardInterrupt

            with patch("time.sleep", side_effect=fake_sleep):
                try:
                    main._run_event_loop()
                except (KeyboardInterrupt, SystemExit):
                    pass

    assert len(handled_events) == 1
    assert handled_events[0] == event


def test_bad_json_line_does_not_crash(monkeypatch):
    """Malformed NDJSON lines are logged and skipped, not raised."""
    main = _reload_main(monkeypatch)

    mock_proc = MagicMock()
    mock_proc.stdout = iter(["NOT VALID JSON\n"])
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0

    with patch("subprocess.Popen", return_value=mock_proc):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            try:
                main._run_event_loop()
            except (KeyboardInterrupt, SystemExit):
                pass
    # No exception raised — test passes if we get here


def test_dry_run_exits_zero(monkeypatch, capsys):
    """--dry-run prints 'config valid' and exits 0."""
    _setup_env(monkeypatch)

    # Force reload of all bot modules to pick up monkeypatched env
    import bot.config as config
    importlib.reload(config)

    import bot.main as main
    importlib.reload(main)

    with patch("sys.exit") as mock_exit:
        main._dry_run()

    captured = capsys.readouterr()
    assert "config valid" in captured.out
    mock_exit.assert_called_once_with(0)
