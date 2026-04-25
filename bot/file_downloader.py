
"""Download invoice images and PDF files from Feishu message resources.

message.content may arrive either as a JSON-encoded string or as an already
decoded mapping, depending on the SDK event shape. This helper accepts both.
"""
import json
import logging
from collections.abc import Mapping
from typing import Any

import requests

from bot.token_manager import token_manager
from bot.utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

DOWNLOAD_URL_TEMPLATE = (
    "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{key}"
)


def _parse_content(content: str | Mapping[str, Any]) -> dict[str, Any]:
    """Parse Feishu message.content from either JSON string or mapping."""
    if isinstance(content, Mapping):
        return dict(content)
    return json.loads(content)


def download_file(
    message_id: str,
    message_type: str,
    content_str: str | Mapping[str, Any],
) -> tuple[bytes, str]:
    """Download an invoice image or PDF from Feishu.

    Args:
        message_id: Feishu message ID (e.g. "om_xxx")
        message_type: "image" or "file"
        content_str: Raw JSON string or mapping from event message.content.

    Returns:
        Tuple of (file_bytes, filename)

    Raises:
        ValueError: If message_type is not "image" or "file"
    """
    if message_type not in ("image", "file"):
        raise ValueError(
            f"Unsupported message_type '{message_type}'. Must be 'image' or 'file'."
        )

    content = _parse_content(content_str)

    if message_type == "image":
        key = content["image_key"]
        resource_type = "image"
        filename = "invoice.jpg"
    else:
        key = content["file_key"]
        resource_type = "file"
        filename = content.get("file_name", "invoice.pdf")

    url = DOWNLOAD_URL_TEMPLATE.format(message_id=message_id, key=key)
    token = token_manager.get_token()

    logger.info("Downloading %s from message %s", message_type, message_id)
    response = requests.get(
        url,
        params={"type": resource_type},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()

    logger.info("Downloaded %d bytes for %s", len(response.content), filename)
    return response.content, filename
