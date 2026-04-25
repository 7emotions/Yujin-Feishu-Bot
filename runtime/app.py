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

from adapters.feishu.events import adapt_event as _adapt_event
from adapters.feishu.events import extract_event_key as _extract_event_key
from adapters.feishu.events import safe_str as _safe_str
from adapters.feishu.settings import APP_ID, APP_SECRET
from utils.utils import ColoredFormatter
from runtime.bootstrap import bot

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TIMEOUT_CHECK_INTERVAL_SECONDS = 30
MAX_COMPLETED_EVENT_KEYS = 1000
PROXY_ENV_KEYS = ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
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
    while True:
        event = _event_queue.get()
        try:
            _process_queued_event(event)
        except Exception as exc:
            logger.error("Background event worker crashed: %s", exc)
        finally:
            _event_queue.task_done()


def _process_queued_event(event: dict[str, object]) -> None:
    event_key = cast(str, event.get("_event_key", ""))
    try:
        logger.info("Processing queued event %s", event_key)
        bot.chat(event)
    except Exception as exc:
        logger.error("Background event processing failed for %s: %s", event_key, exc)
    finally:
        if event_key:
            _mark_event_complete(event_key)


def _timeout_checker() -> None:
    while True:
        time.sleep(TIMEOUT_CHECK_INTERVAL_SECONDS)
        try:
            bot.tick()
        except Exception as exc:
            logger.warning("Timeout checker error: %s", exc)


def _config_proxy_env() -> None:
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    os.environ["http_proxy"] = "http://127.0.0.1:7890"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
    os.environ["https_proxy"] = "http://127.0.0.1:7890"
    os.environ["ALL_PROXY"] = "socks5://127.0.0.1:7890"
    os.environ["all_proxy"] = "socks5://127.0.0.1:7890"
    os.environ["NO_PROXY"] = "*.feishu.cn"
    os.environ["no_proxy"] = "*.feishu.cn"


def _handle_message_receive(data: P2ImMessageReceiveV1) -> None:
    event = _adapt_event(data)
    event_key = cast(str, event.get("_event_key", ""))
    message = cast(dict[str, object], event.get("event", {})).get("message", {})
    with _event_key_lock:
        if event_key in _pending_event_keys or event_key in _completed_event_keys:
            logger.info("Skipping duplicate event %s", event_key)
            return
        _pending_event_keys.add(event_key)
    logger.info(
        "Queued event %s message_type=%s chat_type=%s",
        event_key,
        getattr(message, "get", lambda *_: "")("message_type", "") if isinstance(message, dict) else "",
        getattr(message, "get", lambda *_: "")("chat_type", "") if isinstance(message, dict) else "",
    )
    _event_queue.put(event)


def _handle_message_read(_: object) -> None:
    return None


def _build_ws_client() -> lark.ws.Client:
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_handle_message_receive)
        .register_p2_im_message_message_read_v1(_handle_message_read)
        .build()
    )
    return lark.ws.Client(APP_ID, APP_SECRET, event_handler=event_handler, log_level=lark.LogLevel.CRITICAL)


def _sigterm_handler(signum: int, frame: object) -> None:
    del signum, frame
    sys.exit(0)


def start_event_loop() -> None:
    _config_proxy_env()
    logger.info("Starting Feishu Bot Platform event loop")
    signal.signal(signal.SIGTERM, _sigterm_handler)
    threading.Thread(target=_timeout_checker, daemon=True).start()
    threading.Thread(target=_event_worker, daemon=True).start()
    ws_client = _build_ws_client()
    try:
        logger.info("Starting Feishu websocket client")
        ws_client.start()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)


def _dry_run() -> None:
    _config_proxy_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        import adapters.feishu.auth as _auth  # noqa: F401
        import domain.reimbursement.parser as _parser  # noqa: F401
        import plugins.chat.plugin as _chat  # noqa: F401
        import plugins.reimbursement.plugin as _reimbursement  # noqa: F401
        import runtime.bootstrap as _bootstrap  # noqa: F401
        import runtime.router as _router  # noqa: F401
        import toolsets.feishu.approvals as _approvals  # noqa: F401
        import toolsets.feishu.approval_attachments as _attachments  # noqa: F401
        import toolsets.feishu.file_resources as _files  # noqa: F401
        import toolsets.feishu.messaging as _messaging  # noqa: F401

        print("config valid, all modules loaded")
        _ = (_auth, _parser, _chat, _reimbursement, _bootstrap, _router, _approvals, _attachments, _files, _messaging)
        sys.exit(0)
    except Exception as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Feishu Bot Platform")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and exit")
    args: argparse.Namespace = parser.parse_args(argv)
    if cast(bool, args.dry_run):
        _dry_run()
    else:
        logger.info("Starting event loop...")
        start_event_loop()


if __name__ == "__main__":
    main()
