"""Upload invoice files to Feishu approval attachment endpoint.

CRITICAL: This endpoint uses www.feishu.cn.
Returns a file_code UUID that is used when creating approval instances.
"""

import logging
import mimetypes

import requests

from bot.token_manager import token_manager

logger = logging.getLogger(__name__)

# CRITICAL: www.feishu.cn
UPLOAD_URL = "https://www.feishu.cn/approval/openapi/v2/file/upload"


def upload_approval_attachment(file_bytes: bytes, filename: str) -> str:
    """Upload a file to Feishu approval and return the file_code.

    Args:
        file_bytes: Raw bytes of the invoice file
        filename: Original filename (used for MIME type detection)

    Returns:
        file_code string (UUID format, e.g. "D93653C3-2609-4EE0-8041-61DC1D84F0B5")

    Raises:
        RuntimeError: If the upload fails (API returns code != 0)
    """
    token = token_manager.get_token()

    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    logger.info("Uploading %s (%d bytes) to approval attachment endpoint", filename, len(file_bytes))

    response = requests.post(
        UPLOAD_URL,
        headers={"Authorization": f"Bearer {token}"},
        files={
            "name": (None, filename),
            "type": (None, mime_type),
            "content": (filename, file_bytes, mime_type),
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("code") != 0:
        raise RuntimeError(f"Failed to upload attachment: code={data.get('code')}, msg={data.get('msg')}")

    file_code = data["data"]["code"]
    logger.info("Attachment uploaded, file_code: %s", file_code)
    return file_code
