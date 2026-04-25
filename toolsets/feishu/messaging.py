import logging
from collections.abc import Mapping
from typing import Any, cast

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageReactionRequest,
    CreateMessageReactionRequestBody,
    CreateMessageReactionResponse,
    CreateMessageRequest,
    CreateMessageRequestBody,
    Emoji,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from adapters.feishu.settings import APP_ID, APP_SECRET
from utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)

CONFIRMATION_TEMPLATE = """\
📋 已识别发票信息，请确认：

🔢 发票号码：{invoice_no}
💰 金额：{amount} {currency}
📅 日期：{date}
🏢 供应商：{vendor}
📂 类别：{category}
📝 说明：{description}

✅ 回复「确认」提交报销
✏️ 如需修改，请直接说明（如：「类别改为交通」）
❌ 回复「取消」放弃"""


def _build_client() -> lark.Client:
    return lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()


CLIENT = _build_client()


def _build_text_content(text: str) -> str:
    return cast(str, lark.JSON.marshal({"text": text}))


def send_text(chat_id: str, text: str) -> None:
    client = cast(Any, CLIENT)
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(_build_text_content(text))
            .build()
        )
        .build()
    )
    response = client.im.v1.message.create(request)
    if not response.success():
        raise RuntimeError(
            f"Feishu send message failed (code {response.code}): {response.msg}, log_id: {response.get_log_id()}"
        )


def mark_typing(message_id: str) -> None:
    client = cast(Any, CLIENT)
    request: CreateMessageReactionRequest = CreateMessageReactionRequest.builder() \
        .message_id(message_id) \
            .request_body(CreateMessageReactionRequestBody.builder()
                .reaction_type(Emoji.builder()
                    .emoji_type("Typing")
                    .build())
                .build()) \
            .build()
    response: CreateMessageReactionResponse = client.im.v1.message_reaction.create(request)
    if not response.success():
        raise RuntimeError(
            f"Feishu send message failed (code {response.code}): {response.msg}, log_id: {response.get_log_id()}"
        )


def reply_text(message_id: str, text: str) -> None:
    client = cast(Any, CLIENT)
    request = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(_build_text_content(text))
            .build()
        )
        .build()
    )
    response = client.im.v1.message.reply(request)
    if not response.success():
        raise RuntimeError(
            f"Feishu reply message failed (code {response.code}): {response.msg}, log_id: {response.get_log_id()}"
        )


def format_confirmation(fields: Mapping[str, str]) -> str:
    return CONFIRMATION_TEMPLATE.format(
        invoice_no=fields.get("invoice_no", ""),
        amount=fields.get("amount", ""),
        currency=fields.get("currency", ""),
        date=fields.get("date", ""),
        vendor=fields.get("vendor", ""),
        category=fields.get("category", ""),
        description=fields.get("description", ""),
    )
