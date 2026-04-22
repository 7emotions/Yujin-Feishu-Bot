"""Extract invoice fields from images and PDFs using GPT-4o vision.

GPT-4o handles PDFs natively via base64 input payloads.
"""

import base64
import json
import logging
import re

from openai import OpenAI

from bot.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是一个发票信息提取助手。请从发票中提取以下字段并以JSON格式返回: "
    "invoice_no(发票号码), amount(金额，纯数字), currency(货币，如CNY), "
    "date(日期，格式YYYY-MM-DD), vendor(供应商名称), "
    "category(费用类别，从以下选择: 餐饮/交通/住宿/办公/其他), "
    "description(简短描述). 如果某字段无法识别，返回空字符串。"
)

REQUIRED_KEYS = [
    "invoice_no",
    "amount",
    "currency",
    "date",
    "vendor",
    "category",
    "description",
]


def _empty_result() -> dict:
    return {key: "" for key in REQUIRED_KEYS}


def _normalize_result(data: dict) -> dict:
    result = _empty_result()
    for key in REQUIRED_KEYS:
        value = data.get(key, "")
        result[key] = "" if value is None else str(value)
    return result


def parse_invoice(file_bytes: bytes, filename: str) -> dict:
    """Returns dict with invoice fields, never raising on parse errors."""
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        b64 = base64.b64encode(file_bytes).decode("ascii")
        lower_name = filename.lower()

        if lower_name.endswith((".jpg", ".jpeg", ".png")):
            content_parts = [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]
        elif lower_name.endswith(".pdf"):
            content_parts = [
                {
                    "type": "input_file",
                    "filename": filename,
                    "file_data": f"data:application/pdf;base64,{b64}",
                },
            ]
        else:
            content_parts = [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content_parts},
            ],
        )
        raw = response.choices[0].message.content
        if not raw:
            return _empty_result()

        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw.strip())
        raw = re.sub(r"\n?```$", "", raw.strip())
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            logger.warning("Invoice parse returned non-dict JSON")
            return _empty_result()
        return _normalize_result(parsed)
    except Exception as exc:
        logger.warning("Failed to parse invoice: %s", exc)
        return _empty_result()
