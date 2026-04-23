"""Centralized configuration loader for feishu-reimbursement-bot."""
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false, reportAny=false, reportExplicitAny=false, reportMissingParameterType=false, reportUnknownParameterType=false
import json
import os
from typing import Any

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()


def _require(key: str) -> str:
    """Get required env var, raise ValueError if missing or empty."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise ValueError(f"Required environment variable '{key}' is missing or empty. Check your .env file.")
    return value


def _optional(key: str, default: str = "") -> str:
    """Get optional env var with a default."""
    return os.environ.get(key, default).strip()


# Required keys
APP_ID: str = _require("APP_ID")
APP_SECRET: str = _require("APP_SECRET")
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
BOT_USER_ID: str = _require("BOT_USER_ID")
APPROVER_OPEN_ID: str = _require("APPROVER_OPEN_ID")

# Optional keys (may not be set until approval definition is created)
APPROVAL_CODE: str = _optional("APPROVAL_CODE")
APPROVER_NODE_KEY: str = _optional("APPROVER_NODE_KEY")


def _parse_form_field_ids(raw_value: str) -> dict[str, str]:
    """Parse FORM_FIELD_IDS from JSON into a string-only mapping."""
    if not raw_value:
        return {}
    try:
        parsed: Any = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    result: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str):
            result[key] = value
    return result


# Form field IDs - JSON dict or empty
_form_field_ids_raw: str = _optional("FORM_FIELD_IDS", "{}")
FORM_FIELD_IDS: dict[str, str] = _parse_form_field_ids(_form_field_ids_raw)

# List-type keys (comma-separated in .env)
CONFIRM_KEYWORDS: list[str] = [
    k.strip()
    for k in _optional("CONFIRM_KEYWORDS", "confirm,yes,确认,好的,ok").split(",")
    if k.strip()
]
CANCEL_KEYWORDS: list[str] = [
    k.strip()
    for k in _optional("CANCEL_KEYWORDS", "cancel,取消,算了,不了").split(",")
    if k.strip()
]

# Integer keys
TIMEOUT_SECONDS: int = int(_optional("AWAITING_CONFIRM_TIMEOUT_SECONDS", "600"))


def __repr__(self):
    """Prevent APP_SECRET from leaking into repr/logs."""
    return "<Config: APP_ID={APP_ID}>"
