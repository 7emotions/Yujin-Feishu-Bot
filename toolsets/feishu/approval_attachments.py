import logging
import mimetypes

import requests

from adapters.feishu.auth import token_manager
from utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)

UPLOAD_URL = "https://www.feishu.cn/approval/openapi/v2/file/upload"


def upload_approval_attachment(file_bytes: bytes, filename: str) -> str:
    token = token_manager.get_token()
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"
    upload_type = "image" if mime_type.startswith("image/") else "attachment"
    response = requests.post(
        UPLOAD_URL,
        headers={"Authorization": f"Bearer {token}"},
        files={
            "name": (None, filename),
            "type": (None, upload_type),
            "content": (filename, file_bytes, mime_type),
        },
        timeout=30,
        proxies={"https": "http://127.0.0.1:7890"},
    )
    response.raise_for_status()
    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to upload attachment: code={data.get('code')}, msg={data.get('msg')}")
    return data["data"]["code"]
