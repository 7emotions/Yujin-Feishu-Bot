from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Sequence
from io import BytesIO
from threading import Lock
from typing import Any, cast

import torch

from utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)

SYSTEM_PROMPT = (
    "你是一个发票信息提取助手。请从发票中提取以下字段并以JSON格式返回: "
    "invoice_no(发票号码), amount(金额，纯数字), currency(货币类型, 如CNY), "
    "date(日期，格式YYYY-MM-DD), vendor(供应商名称), "
    "category(费用类别，固定为\"选项1\"), "
    "description(简短描述). 如果某字段无法识别，返回空字符串。"
)

REQUIRED_KEYS = ["invoice_no", "amount", "currency", "date", "vendor", "category", "description"]
QWEN_VL_MODEL = os.environ.get("QWEN_VL_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
_DEFAULT_MAX_NEW_TOKENS = int(os.environ.get("QWEN_VL_MAX_NEW_TOKENS", "96"))
QWEN_VL_PARSE_MAX_NEW_TOKENS = int(os.environ.get("QWEN_VL_PARSE_MAX_NEW_TOKENS", str(max(_DEFAULT_MAX_NEW_TOKENS, 192))))
QWEN_VL_CORRECTION_MAX_NEW_TOKENS = int(os.environ.get("QWEN_VL_CORRECTION_MAX_NEW_TOKENS", str(_DEFAULT_MAX_NEW_TOKENS)))
PDF_RENDER_DPI = int(os.environ.get("PDF_RENDER_DPI", "150"))
QWEN_VL_MIN_PIXELS = int(os.environ.get("QWEN_VL_MIN_PIXELS", str(256 * 28 * 28)))
QWEN_VL_MAX_PIXELS = int(os.environ.get("QWEN_VL_MAX_PIXELS", str(1280 * 28 * 28)))
QWEN_VL_LOCAL_FILES_ONLY = os.environ.get("QWEN_VL_LOCAL_FILES_ONLY", "1") != "0"

_BACKEND_LOCK = Lock()
_INFERENCE_LOCK = Lock()
_backend: tuple[Any, Any, Any] | None = None


def _empty_result() -> dict[str, str]:
    return {key: "" for key in REQUIRED_KEYS}


def _normalize_result(data: dict[str, Any]) -> dict[str, str]:
    result = _empty_result()
    for key in REQUIRED_KEYS:
        value = data.get(key, "")
        result[key] = "" if value is None else str(value)
    return result


def _load_image_file(file_bytes: bytes) -> Any:
    from PIL import Image

    return Image.open(BytesIO(file_bytes)).convert("RGB")


def _load_pdf_images(file_bytes: bytes) -> list[Any]:
    from pdf2image import convert_from_bytes

    return convert_from_bytes(file_bytes, dpi=PDF_RENDER_DPI)


def _load_images(file_bytes: bytes, filename: str) -> list[Any]:
    lower_name = filename.lower()
    if lower_name.endswith(".pdf") or file_bytes.startswith(b"%PDF-"):
        return _load_pdf_images(file_bytes)
    return [_load_image_file(file_bytes)]


def _get_backend() -> tuple[Any, Any, Any]:
    global _backend
    if _backend is not None:
        return _backend
    with _BACKEND_LOCK:
        if _backend is not None:
            return _backend
        from qwen_vl_utils import process_vision_info
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            QWEN_VL_MODEL,
            device_map="auto",
            torch_dtype="auto",
            low_cpu_mem_usage=True,
            local_files_only=QWEN_VL_LOCAL_FILES_ONLY,
        )
        _ = model.eval()
        processor = AutoProcessor.from_pretrained(
            QWEN_VL_MODEL,
            min_pixels=QWEN_VL_MIN_PIXELS,
            max_pixels=QWEN_VL_MAX_PIXELS,
            local_files_only=QWEN_VL_LOCAL_FILES_ONLY,
        )
        _backend = (model, processor, process_vision_info)
        return _backend


def _build_messages(images: Sequence[Any]) -> list[dict[str, Any]]:
    user_content: list[dict[str, Any]] = [{"type": "image", "image": image} for image in images]
    user_content.append({"type": "text", "text": f"{SYSTEM_PROMPT} 仅返回JSON对象，不要返回Markdown代码块或额外说明。"})
    return [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {"role": "user", "content": user_content},
    ]


def _extract_assistant_text(output_text: str, prompt_text: str) -> str:
    stripped = output_text.strip()
    if stripped.startswith(prompt_text):
        return stripped[len(prompt_text):].strip()
    return stripped


def _extract_json_object(raw: str) -> str:
    start = raw.find("{")
    if start == -1:
        return raw.strip()
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(raw)):
        char = raw[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw[start:index + 1]
    return raw[start:].strip()


def _generate_invoice_json(images: Sequence[Any]) -> str:
    model, processor, process_vision_info = _get_backend()
    messages = _build_messages(images)
    prompt_text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(text=[prompt_text], images=image_inputs, videos=video_inputs, padding=True, return_tensors="pt")
    inputs = inputs.to(model.device)
    generated_ids = None
    try:
        with _INFERENCE_LOCK:
            with torch.inference_mode():
                generated_ids = model.generate(**inputs, max_new_tokens=QWEN_VL_PARSE_MAX_NEW_TOKENS)
        input_ids = inputs.input_ids
        trimmed_ids = [output_ids[len(source_ids):].cpu() for source_ids, output_ids in zip(input_ids, generated_ids)]
        output_text = processor.batch_decode(trimmed_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        return _extract_assistant_text(output_text, prompt_text)
    finally:
        del inputs
        if generated_ids is not None:
            del generated_ids
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _generate_correction_json(images: Sequence[Any], invoice_fields: dict[str, str], correction_text: str) -> str:
    model, processor, process_vision_info = _get_backend()
    messages = _build_messages(images)
    messages.append({"role": "assistant", "content": [{"type": "text", "text": json.dumps(invoice_fields, ensure_ascii=False)}]})
    messages.append(
        {
            "role": "user",
            "content": [{"type": "text", "text": f"当前提取结果是: {json.dumps(invoice_fields, ensure_ascii=False)}。用户修改要求: {correction_text}。请结合前面的发票图片，返回修正后的完整JSON对象。只返回JSON，不要返回Markdown代码块或额外说明。"}],
        }
    )
    prompt_text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(text=[prompt_text], images=image_inputs, videos=video_inputs, padding=True, return_tensors="pt")
    inputs = inputs.to(model.device)
    generated_ids = None
    try:
        with _INFERENCE_LOCK:
            with torch.inference_mode():
                generated_ids = model.generate(**inputs, max_new_tokens=QWEN_VL_CORRECTION_MAX_NEW_TOKENS)
        input_ids = inputs.input_ids
        trimmed_ids = [output_ids[len(source_ids):].cpu() for source_ids, output_ids in zip(input_ids, generated_ids)]
        output_text = processor.batch_decode(trimmed_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        return _extract_assistant_text(output_text, prompt_text)
    finally:
        del inputs
        if generated_ids is not None:
            del generated_ids
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def _parse_json_text(raw: str) -> dict[str, str]:
    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```$", "", cleaned.strip())
    cleaned = _extract_json_object(cleaned)
    parsed_obj = json.loads(cleaned)
    if not isinstance(parsed_obj, dict):
        logger.warning("Invoice parse returned non-dict JSON")
        return _empty_result()
    amount_value = parsed_obj.get("amount", "")
    amount_text = "" if amount_value is None else str(amount_value)
    if "￥" in amount_text:
        parsed_obj["amount"] = amount_text.replace("￥", "")
        parsed_obj["currency"] = "CNY"
    elif "$" in amount_text:
        parsed_obj["amount"] = amount_text.replace("$", "")
        parsed_obj["currency"] = "USD"
    else:
        parsed_obj["amount"] = amount_text
    parsed = cast(dict[str, Any], parsed_obj)
    return _normalize_result(parsed)


def parse_invoice(file_bytes: bytes, filename: str) -> dict[str, str]:
    try:
        images = _load_images(file_bytes, filename)
        if not images:
            return _empty_result()
        raw = _generate_invoice_json(images)
        if not raw:
            return _empty_result()
        return _parse_json_text(raw)
    except Exception as exc:
        logger.warning("Failed to parse invoice: %s", exc)
        return _empty_result()


def correct_invoice_fields(file_bytes: bytes, filename: str, invoice_fields: dict[str, str], correction_text: str) -> dict[str, str]:
    try:
        images = _load_images(file_bytes, filename)
        if not images:
            return _normalize_result(invoice_fields)
        raw = _generate_correction_json(images, invoice_fields, correction_text)
        if not raw:
            return _normalize_result(invoice_fields)
        return _parse_json_text(raw)
    except Exception as exc:
        logger.warning("Failed to correct invoice fields: %s", exc)
        return _normalize_result(invoice_fields)
