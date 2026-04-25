import json
import logging
from collections.abc import Mapping
from typing import Any

import requests

from adapters.feishu.auth import token_manager
from utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)

DOWNLOAD_URL_TEMPLATE = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{key}"


def _parse_content(content: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(content, Mapping):
        return dict(content)
    return json.loads(content)


def download_file(message_id: str, message_type: str, content_str: str | Mapping[str, Any]) -> tuple[bytes, str]:
    if message_type not in ("image", "file"):
        raise ValueError(f"Unsupported message_type '{message_type}'. Must be 'image' or 'file'.")
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
    response = requests.get(
        url,
        params={"type": resource_type},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content, filename
