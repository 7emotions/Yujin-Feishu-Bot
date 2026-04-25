from __future__ import annotations

import json
import logging
from typing import Any

import torch

import domain.reimbursement.parser as qwen_parser
from runtime.plugin import BotPlugin
from runtime.session_store import UserSession
from utils import ColoredFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logger.addHandler(handler)


QWEN_VL_CHAT_MAX_NEW_TOKENS = 192
def build_decision(session: UserSession, user_text: str, plugins: list[BotPlugin]) -> dict[str, str]:
    if not user_text.strip():
        logger.warning("Empty user input")
        return _fallback_decision(user_text)

    try:
        model, processor, _ = qwen_parser._get_backend()
        messages = _build_messages(session, user_text, plugins)
        logger.info(f"Messages: {json.dumps(messages, ensure_ascii=False)}")
        prompt_text = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = processor(text=[prompt_text], padding=True, return_tensors="pt")
        inputs = inputs.to(model.device)
        generated_ids = None
        try:
            with qwen_parser._INFERENCE_LOCK:
                with torch.inference_mode():
                    generated_ids = model.generate(**inputs, max_new_tokens=QWEN_VL_CHAT_MAX_NEW_TOKENS)
            input_ids = inputs.input_ids
            trimmed_ids = [
                output_ids[len(source_ids) :].cpu()
                for source_ids, output_ids in zip(input_ids, generated_ids)
            ]
            output_text = processor.batch_decode(
                trimmed_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
            logger.info(f"Generated text: {output_text}")
            raw = qwen_parser._extract_assistant_text(output_text, prompt_text)
            return _parse_decision(raw, user_text)
        finally:
            del inputs
            if generated_ids is not None:
                del generated_ids
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    except Exception as e:
        logger.error(f"Error during decision making: {e}")
        return _fallback_decision(user_text)


def build_summary(session: UserSession) -> str:
    if not session.recent_messages:
        return ""
    items = session.recent_messages[-6:]
    summary_parts: list[str] = []
    for item in items:
        role = item.get("type", "user")
        content = item.get("content", "").strip()
        if not content:
            continue
        summary_parts.append(f"{role}: {content}")
    return " | ".join(summary_parts)


def _build_messages(session: UserSession, user_text: str, plugins: list[BotPlugin]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": _build_system_prompt(plugins),
                }
            ],
        }
    ]

    if session.summary:
        messages.append(
            {
                "role": "system",
                "content": [{"type": "text", "text": f"对话摘要：{session.summary}"}],
            }
        )

    memory = session.data.get("chat_memory")
    if isinstance(memory, dict):
        preferences = memory.get("preferences")
        facts = memory.get("facts")
    else:
        preferences = None
        facts = None

    if isinstance(preferences, list) and preferences:
        messages.append(
            {
                "role": "system",
                "content": [{"type": "text", "text": f"用户长期偏好：{' | '.join(str(item) for item in preferences)}"}],
            }
        )

    if isinstance(facts, list) and facts:
        messages.append(
            {
                "role": "system",
                "content": [{"type": "text", "text": f"用户长期事实：{' | '.join(str(item) for item in facts)}"}],
            }
        )

    if session.recent_messages:
        transcript_lines: list[str] = []
        for item in session.recent_messages[-8:]:
            speaker = "assistant" if item.get("type") == "assistant" else "user"
            transcript_lines.append(f"{speaker}: {item.get('content', '')}")
        messages.append(
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "最近对话记录（仅供理解上下文，不要模仿其输出格式）：\n"
                            + "\n".join(transcript_lines)
                        ),
                    }
                ],
            }
        )

    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"用户当前消息：{user_text}\n"
                        "再次提醒：你的输出必须是 JSON，对象字段只能包含 action、reply、reason。"
                        "不要输出普通自然语言，不要输出 Markdown，不要输出代码块。"
                    ),
                }
            ],
        }
    )
    return messages


def _build_system_prompt(plugins: list[BotPlugin]) -> str:
    plugin_lines = []
    tool_lines = []
    action_lines = []
    for index, plugin in enumerate(plugins, start=1):
        plugin_lines.append(f"{index}. {plugin.name}：{plugin.capability_description}")
        for tool in plugin.tool_descriptions:
            tool_lines.append(f"- {plugin.name}: {tool}")
        for action_name, action_desc in plugin.chat_actions.items():
            action_lines.append(f"- {action_name}: {action_desc}")
    plugins_text = "\n".join(plugin_lines) if plugin_lines else "- 无已注册插件"
    tools_text = "\n".join(tool_lines) if tool_lines else "- 无额外工具描述"
    actions_text = "\n".join(action_lines) if action_lines else "- chat: 继续普通聊天对话"
    return (
        "你是一个通用飞书机器人助手。"
        "你需要先理解用户意图，再决定是直接聊天回复，还是把任务交给现有插件。"
        f"\n可用插件：\n{plugins_text}"
        f"\n可用工具能力（由系统执行，不需要你自己真的调用代码）：\n{tools_text}"
        f"\n允许输出的 action：\n{actions_text}"
        "\n你的任务是输出 JSON，字段为 action, reply, reason。"
        "\naction 必须从允许输出的 action 列表中选择。"
        "\nreply 是你要回复给用户的话。如果没有相应的插件和工具，必须告知用户。"
        "\n只返回 JSON，不要返回 Markdown 代码块或额外说明。"
    )


def _parse_decision(raw: str, user_text: str) -> dict[str, str]:
    try:
        cleaned = qwen_parser._extract_json_object(raw.strip())
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            return _fallback_decision(user_text)
        action = str(parsed.get("action", "chat"))
        reply = str(parsed.get("reply", "")).strip() or _fallback_decision(user_text)["reply"]
        reason = str(parsed.get("reason", ""))
        return {"action": action, "reply": reply, "reason": reason}
    except Exception:
        return _fallback_decision(user_text)


def _fallback_decision(user_text: str) -> dict[str, str]:
    text = user_text.strip()
    if not text:
        return {"action": "chat", "reply": "你好，有什么我可以帮你的？", "reason": "empty-input"}
    lower = text.lower()
    if any(keyword in lower for keyword in ("报销", "发票", "审批", "invoice", "reimburse")):
        return {
            "action": "handoff_reimbursement",
            "reply": "看起来你想处理报销。请直接发送发票图片或 PDF，我会继续进入报销流程。",
            "reason": "keyword-match",
        }
    return {
        "action": "chat",
        "reply": f"我收到了：{text}\n\n你可以继续和我聊天；或者告诉我你想做什么，我会尽力帮你。",
        "reason": "generic-chat",
    }
