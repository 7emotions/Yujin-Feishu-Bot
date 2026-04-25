import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise ValueError(f"Required environment variable '{key}' is missing or empty. Check your .env file.")
    return value


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _parse_form_field_ids(raw_value: str) -> dict[str, str]:
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


APP_ID: str = _require("APP_ID")
APP_SECRET: str = _require("APP_SECRET")
BOT_USER_ID: str = _require("BOT_USER_ID")
OPENAI_API_KEY: str = _optional("OPENAI_API_KEY")
APPROVAL_CODE: str = _optional("APPROVAL_CODE")
APPROVER_NODE_KEY: str = _optional("APPROVER_NODE_KEY")
APPROVER_OPEN_ID: str = _require("APPROVER_OPEN_ID")
FORM_FIELD_IDS: dict[str, str] = _parse_form_field_ids(_optional("FORM_FIELD_IDS", "{}"))
FORM_OPTION_IDS: dict[str, str] = _parse_form_field_ids(_optional("FORM_OPTION_IDS", "{}"))
