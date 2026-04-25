import time
from typing import Any

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1


def safe_str(value: object | None) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def extract_event_key(data: P2ImMessageReceiveV1) -> str:
    header = getattr(data, "header", None)
    event_id = getattr(header, "event_id", None)
    if isinstance(event_id, str) and event_id:
        return event_id
    if data.event is not None and data.event.message is not None:
        message_id = getattr(data.event.message, "message_id", None)
        if isinstance(message_id, str) and message_id:
            return message_id
    return f"event-{time.time_ns()}"


def adapt_event(data: P2ImMessageReceiveV1) -> dict[str, object]:
    if data.event is None or data.event.message is None or data.event.sender is None:
        raise ValueError("Received malformed Feishu message event")
    sender_id = getattr(getattr(data.event.sender, "sender_id", None), "open_id", None)
    message = data.event.message
    event_key = extract_event_key(data)
    return {
        "_event_key": event_key,
        "event": {
            "sender": {"sender_id": {"open_id": safe_str(sender_id)}},
            "message": {
                "message_id": safe_str(message.message_id),
                "chat_id": safe_str(message.chat_id),
                "chat_type": safe_str(message.chat_type),
                "message_type": safe_str(message.message_type),
                "content": safe_str(message.content),
            },
        },
    }
