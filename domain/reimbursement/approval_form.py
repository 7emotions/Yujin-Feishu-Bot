import re

from domain.reimbursement.settings import FORM_FIELD_IDS, FORM_OPTION_IDS

InvoiceFields = dict[str, str]
ApprovalFormValue = str | int | float | list[str]
ApprovalFormItem = dict[str, ApprovalFormValue]


def _normalize_number_value(raw_value: str) -> int | float | str:
    cleaned = re.sub(r"[^0-9.\-]", "", raw_value)
    if not cleaned:
        return ""
    try:
        numeric = float(cleaned)
    except ValueError:
        return raw_value
    return int(numeric) if numeric.is_integer() else numeric


def _normalize_date_value(raw_value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_value):
        return f"{raw_value}T00:00:00+08:00"
    return raw_value


def _normalize_field_value(field_type: str, raw_value: str) -> str | int | float:
    if field_type == "number":
        return _normalize_number_value(raw_value)
    if field_type == "date":
        return _normalize_date_value(raw_value)
    if field_type == "radioV2":
        option_id = FORM_OPTION_IDS.get(raw_value)
        return option_id if option_id is not None else raw_value
    return raw_value


def build_form(invoice_fields: InvoiceFields, file_code: str) -> list[ApprovalFormItem]:
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
        raw_value = invoice_fields.get(field_key, "")
        form.append({"id": widget_id, "type": field_type, "value": _normalize_field_value(field_type, raw_value)})

    attachment_id = FORM_FIELD_IDS.get("attachment")
    if not attachment_id:
        raise ValueError("FORM_FIELD_IDS missing widget ID for 'attachment'")
    form.append({"id": attachment_id, "type": "attachmentV2", "value": [file_code]})
    return form
