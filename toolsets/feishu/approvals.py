import json
import logging
import uuid
from typing import Any

import requests

from adapters.feishu.auth import token_manager
from domain.reimbursement.approval_form import build_form
from domain.reimbursement.settings import APPROVAL_CODE, APPROVER_NODE_KEY, APPROVER_OPEN_ID
from utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)

APPROVAL_INSTANCE_URL = "https://open.feishu.cn/open-apis/approval/v4/instances"
InvoiceFields = dict[str, str]


def create_reimbursement_approval(user_open_id: str, invoice_fields: InvoiceFields, file_code: str) -> str:
    if not APPROVAL_CODE:
        raise ValueError("APPROVAL_CODE is not configured. Complete APPROVAL_SETUP.md steps first.")
    form = build_form(invoice_fields, file_code)
    token = token_manager.get_token()
    payload: dict[str, Any] = {
        "approval_code": APPROVAL_CODE,
        "open_id": user_open_id,
        "form": json.dumps(form),
        "uuid": str(uuid.uuid4()).upper(),
    }
    if APPROVER_NODE_KEY:
        payload["node_approver_open_id_list"] = [{"key": APPROVER_NODE_KEY, "value": [APPROVER_OPEN_ID]}]

    response = requests.post(
        APPROVAL_INSTANCE_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to create approval instance: code={data.get('code')}, msg={data.get('msg')}")
    return data["data"]["instance_code"]
