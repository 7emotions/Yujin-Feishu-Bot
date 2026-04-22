"""Main event loop for feishu-reimbursement-bot.

Spawns a lark-cli subprocess, reads NDJSON events line-by-line, routes
each event to ConversationStateMachine. Reconnects automatically on EOF.
Runs a background thread that calls state_machine._check_timeouts() every 30s.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time

if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.state_machine import state_machine

logger = logging.getLogger(__name__)

LARK_CLI_CMD = [
    "lark-cli",
    "event",
    "+subscribe",
    "--as",
    "bot",
    "--event-types",
    "im.message.receive_v1",
    "--compact",
    "--quiet",
]
RECONNECT_DELAY_SECONDS = 5
TIMEOUT_CHECK_INTERVAL_SECONDS = 30


def _build_env() -> dict:
    """Build subprocess environment with LARK_CLI_NO_PROXY=1 and nvm PATH."""
    env = dict(os.environ)
    env["LARK_CLI_NO_PROXY"] = "1"
    nvm_bin = os.path.expanduser("~/.nvm/versions/node/v18.20.8/bin")
    if nvm_bin not in env.get("PATH", ""):
        env["PATH"] = f"{nvm_bin}:{env.get('PATH', '')}"
    return env


def _timeout_checker() -> None:
    """Background thread: call state_machine._check_timeouts() every 30s."""
    while True:
        time.sleep(TIMEOUT_CHECK_INTERVAL_SECONDS)
        try:
            state_machine._check_timeouts()
        except Exception as exc:
            logger.warning("Timeout checker error: %s", exc)


def _run_event_loop() -> None:
    """Inner loop: spawn subprocess, read NDJSON, reconnect on EOF."""
    env = _build_env()
    while True:
        logger.info("Starting lark-cli event subscriber...")
        try:
            proc = subprocess.Popen(
                LARK_CLI_CMD,
                stdout=subprocess.PIPE,
                env=env,
                text=True,
            )
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    state_machine.handle_event(event)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse NDJSON line: %s | line: %r", exc, line)
                except Exception as exc:
                    logger.error("Error handling event: %s", exc)
            # EOF reached
            proc.wait()
            logger.warning(
                "lark-cli subprocess ended (exit %s). Reconnecting in %ds...",
                proc.returncode,
                RECONNECT_DELAY_SECONDS,
            )
        except Exception as exc:
            logger.error("Subprocess error: %s. Reconnecting in %ds...", exc, RECONNECT_DELAY_SECONDS)
        time.sleep(RECONNECT_DELAY_SECONDS)


def start_event_loop() -> None:
    """Start the bot: launch timeout checker thread, then enter event loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info("feishu-reimbursement-bot starting up")

    checker = threading.Thread(target=_timeout_checker, daemon=True)
    checker.start()

    try:
        _run_event_loop()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down.")
        sys.exit(0)


def _dry_run() -> None:
    """Validate config and imports, then exit 0."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        # Import all modules to trigger config validation
        import bot.config as cfg  # noqa: F401
        import bot.token_manager  # noqa: F401
        import bot.file_downloader  # noqa: F401
        import bot.invoice_parser  # noqa: F401
        import bot.attachment_uploader  # noqa: F401
        import bot.message_sender  # noqa: F401
        import bot.approval_creator  # noqa: F401
        import bot.state_machine  # noqa: F401
        print("config valid, all modules loaded")
        sys.exit(0)
    except Exception as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feishu Reimbursement Bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and exit",
    )
    args = parser.parse_args()

    if args.dry_run:
        _dry_run()
    else:
        start_event_loop()
