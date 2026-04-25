"""Main event loop for feishu-reimbursement-bot.

Receives Feishu IM events using the official lark-oapi long connection client,
adapts incoming SDK events into the existing state-machine event shape, and
routes them to ConversationStateMachine. A background thread calls
state_machine._check_timeouts() every 30 seconds.
"""
# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnusedCallResult=false, reportMissingTypeStubs=false, reportMissingParameterType=false, reportImplicitOverride=false, reportUnannotatedClassAttribute=false
import argparse
import logging
import os
import queue
import signal
import sys
import threading
import time
from collections import deque
from typing import cast

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

if __package__ is None or __package__ == "":
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import APP_ID, APP_SECRET
from bot.state_machine import state_machine
from bot.utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TIMEOUT_CHECK_INTERVAL_SECONDS = 30
MAX_COMPLETED_EVENT_KEYS = 1000
PROXY_ENV_KEYS = [
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
]


handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

_event_queue: queue.Queue[dict[str, object]] = queue.Queue()
_event_key_lock = threading.Lock()
_pending_event_keys: set[str] = set()
_completed_event_keys: set[str] = set()
_completed_event_order: deque[str] = deque()


def _remember_completed_event_key(event_key: str) -> None:
    _completed_event_keys.add(event_key)
    _completed_event_order.append(event_key)
    while len(_completed_event_order) > MAX_COMPLETED_EVENT_KEYS:
        expired = _completed_event_order.popleft()
        _completed_event_keys.discard(expired)


def _mark_event_complete(event_key: str) -> None:
    with _event_key_lock:
        _pending_event_keys.discard(event_key)
        _remember_completed_event_key(event_key)


def _event_worker() -> None:
    """Process queued Feishu events off the SDK callback thread."""
    while True:
        event = _event_queue.get()
        try:
            _process_queued_event(event)
        except Exception as exc:
            logger.error("Background event worker crashed: %s", exc)
        finally:
            _event_queue.task_done()


def _process_queued_event(event: dict[str, object]) -> None:
    """Handle a single queued event and update dedupe bookkeeping."""
    event_key = cast(str, event.get("_event_key", ""))
    try:
        state_machine.handle_event(event)
    except Exception as exc:
        logger.error("Background event processing failed for %s: %s", event_key, exc)
    finally:
        if event_key:
            _mark_event_complete(event_key)

def _timeout_checker() -> None:
    """Background thread: call state_machine._check_timeouts() every 30s."""
    while True:
        time.sleep(TIMEOUT_CHECK_INTERVAL_SECONDS)
        try:
            state_machine._check_timeouts()
        except Exception as exc:
            logger.warning("Timeout checker error: %s", exc)


def _disable_proxy_env() -> None:
    """Remove proxy settings that break Feishu/OpenAI network calls."""
    # for key in PROXY_ENV_KEYS:
    #     os.environ.pop(key, None)
    # os.environ["NO_PROXY"] = "*"
    # os.environ["no_proxy"] = "*"
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    os.environ["http_proxy"] = "http://127.0.0.1:7890"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
    os.environ["https_proxy"] = "http://127.0.0.1:7890"
    os.environ["ALL_PROXY"] = "socks5://127.0.0.1:7890"
    os.environ["all_proxy"] = "socks5://127.0.0.1:7890"
    os.environ["NO_PROXY"] = "*.feishu.cn"
    os.environ["no_proxy"] = "*.feishu.cn"


def _safe_str(value: object | None) -> str:
    """Convert nullable SDK fields to strings expected by the state machine."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _adapt_event(data: P2ImMessageReceiveV1) -> dict[str, object]:
    """Convert lark-oapi message event into the existing internal event shape."""
    if data.event is None or data.event.message is None or data.event.sender is None:
        raise ValueError("Received malformed Feishu message event")

    sender_id = getattr(getattr(data.event.sender, "sender_id", None), "open_id", None)
    message = data.event.message

    event_key = _extract_event_key(data)

    return {
        "_event_key": event_key,
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": _safe_str(sender_id),
                }
            },
            "message": {
                "message_id": _safe_str(message.message_id),
                "chat_id": _safe_str(message.chat_id),
                "chat_type": _safe_str(message.chat_type),
                "message_type": _safe_str(message.message_type),
                "content": _safe_str(message.content),
            },
        }
    }


def _extract_event_key(data: P2ImMessageReceiveV1) -> str:
    """Prefer Feishu event_id, fall back to message_id."""
    header = getattr(data, "header", None)
    event_id = getattr(header, "event_id", None)
    if isinstance(event_id, str) and event_id:
        return event_id
    if data.event is not None and data.event.message is not None:
        message_id = getattr(data.event.message, "message_id", None)
        if isinstance(message_id, str) and message_id:
            return message_id
    return f"event-{time.time_ns()}"


def _handle_message_receive(data: P2ImMessageReceiveV1) -> None:
    """Adapter handler for sample-style long connection message events."""
    logger.debug("Received message event: %s", data)
    logger.info("Handling message event")
    event = _adapt_event(data)
    event_key = cast(str, event.get("_event_key", ""))
    with _event_key_lock:
        if event_key in _pending_event_keys or event_key in _completed_event_keys:
            logger.info("Skipping duplicate event %s", event_key)
            return
        _pending_event_keys.add(event_key)
    _event_queue.put(event)


def _handle_message_read(_: object) -> None:
    """Ignore read-receipt events the bot does not process."""
    logger.debug("Ignoring message_read event")


def _build_ws_client() -> lark.ws.Client:
    """Create the long connection client and register the message handler."""
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_handle_message_receive)
        .register_p2_im_message_message_read_v1(_handle_message_read)
        .build()
    )

    return lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.CRITICAL,
    )


def _sigterm_handler(signum: int, frame: object) -> None:
    """Handle SIGTERM by exiting cleanly."""
    del signum, frame
    logger.info("Received SIGTERM, shutting down.")
    sys.exit(0)


def start_event_loop() -> None:
    """Start timeout checker thread, then start the Feishu long connection."""
    _disable_proxy_env()
    logger.info("feishu-reimbursement-bot starting up")
    signal.signal(signal.SIGTERM, _sigterm_handler)

    checker = threading.Thread(target=_timeout_checker, daemon=True)
    checker.start()

    worker = threading.Thread(target=_event_worker, daemon=True)
    worker.start()

    ws_client = _build_ws_client()
    logger.info("Starting lark long connection event subscriber...")

    try:
        ws_client.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down.")
        sys.exit(0)


def _dry_run() -> None:
    """Validate config and imports, then exit 0."""
    _disable_proxy_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        import lark_oapi as _lark_oapi  # noqa: F401
        import bot.approval_creator as _approval_creator  # noqa: F401
        import bot.attachment_uploader as _attachment_uploader  # noqa: F401
        import bot.config as _cfg  # noqa: F401
        import bot.file_downloader as _file_downloader  # noqa: F401
        import bot.invoice_parser as _invoice_parser  # noqa: F401
        import bot.message_sender as _message_sender  # noqa: F401
        import bot.state_machine as _state_machine  # noqa: F401
        import bot.token_manager as _token_manager  # noqa: F401

        print("config valid, all modules loaded")
        _ = (
            _approval_creator,
            _attachment_uploader,
            _cfg,
            _file_downloader,
            _invoice_parser,
            _lark_oapi,
            _message_sender,
            _state_machine,
            _token_manager,
        )
        sys.exit(0)
    except Exception as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Feishu Reimbursement Bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and exit",
    )
    args: argparse.Namespace = parser.parse_args(argv)

    if cast(bool, args.dry_run):
        _dry_run()
    else:
        start_event_loop()


if __name__ == "__main__":
    main()
