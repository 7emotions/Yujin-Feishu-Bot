"""Create Feishu approval instances for expense reimbursement.

Uses tenant_access_token for authentication (NOT user_access_token).
The form field must be JSON-stringified (double-encoded) when sent to the API.
"""
# pyright: reportAny=false, reportExplicitAny=false
import json
import logging
import uuid
from typing import Any

import requests

from bot.config import APPROVAL_CODE, APPROVER_NODE_KEY, APPROVER_OPEN_ID, FORM_FIELD_IDS
from bot.token_manager import token_manager

logger = logging.getLogger(__name__)

APPROVAL_INSTANCE_URL = "https://open.feishu.cn/open-apis/approval/v4/instances"
InvoiceFields = dict[str, str]
ApprovalFormItem = dict[str, str | list[str]]

# Default field type mapping (matches the form control types in Feishu)
FIELD_TYPE_MAP = {
    "invoice_no": "input",
    "amount": "number",
    "currency": "radioV2",
    "date": "date",
    "vendor": "input",
    "category": "radioV2",
    "description": "textarea",
    "attachment": "attachmentV2",
}


def create_reimbursement_approval(
    user_open_id: str,
    invoice_fields: InvoiceFields,
    file_code: str,
) -> str:
    """Create a Feishu approval instance for expense reimbursement.

    Args:
        user_open_id: The open_id of the user submitting the reimbursement
        invoice_fields: Dict with keys: invoice_no, amount, currency, date,
                        vendor, category, description
        file_code: File code UUID returned by attachment_uploader

    Returns:
        instance_code string (e.g. "81D31358-93AF-92D6-7425-01A5D67C4E71")

    Raises:
        RuntimeError: If approval creation fails
        ValueError: If APPROVAL_CODE is not configured in .env
    """
    if not APPROVAL_CODE:
        raise ValueError(
            "APPROVAL_CODE is not configured. Complete APPROVAL_SETUP.md steps first."
        )

    # Validate configured widget IDs before any external API calls
    form = _build_form(invoice_fields, file_code)

    token = token_manager.get_token()

    # form must be JSON-stringified (double-encoded)
    form_json_str = json.dumps(form)

    payload: dict[str, Any] = {
        "approval_code": APPROVAL_CODE,
        "open_id": user_open_id,
        "form": form_json_str,
        "uuid": str(uuid.uuid4()).upper(),
    }
    if APPROVER_NODE_KEY:
        payload["node_approver_open_id_list"] = [
            {"key": APPROVER_NODE_KEY, "value": [APPROVER_OPEN_ID]}
        ]

    logger.info(
        "Creating approval instance for user %s, approval_code %s",
        user_open_id,
        APPROVAL_CODE,
    )

    response = requests.post(
        APPROVAL_INSTANCE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()

    if data.get("code") != 0:
        raise RuntimeError(
            f"Failed to create approval instance: code={data.get('code')}, msg={data.get('msg')}"
        )

    instance_code = data["data"]["instance_code"]
    logger.info("Created approval instance: %s", instance_code)
    return instance_code


def _build_form(invoice_fields: InvoiceFields, file_code: str) -> list[ApprovalFormItem]:
    """Build the form array for the approval API.

    Requires FORM_FIELD_IDS from config to provide real Feishu widget IDs.
    """
    if not FORM_FIELD_IDS:
        raise ValueError("FORM_FIELD_IDS not configured — add widget IDs to .env")

    field_mapping = [
        ("invoice_no", "invoice_no", "input"),
        ("amount", "amount", "number"),
        ("currency", "currency", "radioV2"),
        ("date", "date", "date"),
        ("vendor", "vendor", "input"),
        ("category", "category", "radioV2"),
        ("description", "description", "textarea"),
    ]

    form: list[ApprovalFormItem] = []
    for field_key, config_key, field_type in field_mapping:
        widget_id = FORM_FIELD_IDS.get(config_key)
        if not widget_id:
            raise ValueError(f"FORM_FIELD_IDS missing widget ID for '{config_key}'")
        value = invoice_fields.get(field_key, "")
        form.append(
            {
                "id": widget_id,
                "type": field_type,
                "value": value,
            }
        )

    attachment_id = FORM_FIELD_IDS.get("attachment")
    if not attachment_id:
        raise ValueError("FORM_FIELD_IDS missing widget ID for 'attachment'")
    form.append(
        {
            "id": attachment_id,
            "type": "attachmentV2",
            "value": [file_code],
        }
    )

    return form
