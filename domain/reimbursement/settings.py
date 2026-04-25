import os

from adapters.feishu.settings import APPROVAL_CODE, APPROVER_NODE_KEY, APPROVER_OPEN_ID, FORM_FIELD_IDS, FORM_OPTION_IDS


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


CONFIRM_KEYWORDS: list[str] = [k.strip() for k in _optional("CONFIRM_KEYWORDS", "confirm,yes,确认,好的,ok").split(",") if k.strip()]
CANCEL_KEYWORDS: list[str] = [k.strip() for k in _optional("CANCEL_KEYWORDS", "cancel,取消,算了,不了").split(",") if k.strip()]
TIMEOUT_SECONDS: int = int(_optional("AWAITING_CONFIRM_TIMEOUT_SECONDS", "600"))

__all__ = [
    "APPROVAL_CODE",
    "APPROVER_NODE_KEY",
    "APPROVER_OPEN_ID",
    "FORM_FIELD_IDS",
    "FORM_OPTION_IDS",
    "CONFIRM_KEYWORDS",
    "CANCEL_KEYWORDS",
    "TIMEOUT_SECONDS",
]
