"""Send and reply to Feishu messages via lark-cli subprocess.

Uses lark-cli as the messaging backend rather than direct HTTP API.
All subprocess calls include LARK_CLI_NO_PROXY=1 environment variable.
"""

import logging
import os
import subprocess


logger = logging.getLogger(__name__)

LARK_CLI = "lark-cli"

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


def _run_lark_cli(args: list[str]) -> None:
    """Run a lark-cli command via subprocess."""
    env = {**os.environ}
    env["LARK_CLI_NO_PROXY"] = "1"

    nvm_bin = os.path.expanduser("~/.nvm/versions/node/v18.20.8/bin")
    if nvm_bin not in env.get("PATH", ""):
        env["PATH"] = f"{nvm_bin}:{env.get('PATH', '')}"

    cmd = [LARK_CLI, *args]
    logger.debug("Running lark-cli command: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"lark-cli command failed (exit {result.returncode}): {result.stderr}"
        )


def send_text(chat_id: str, text: str) -> None:
    """Send a text message to a chat."""
    logger.info("Sending text message to chat %s", chat_id)
    _run_lark_cli(["im", "messages", "send", "--chat-id", chat_id, "--text", text])


def reply_text(message_id: str, text: str) -> None:
    """Reply to a specific message."""
    logger.info("Replying to message %s", message_id)
    _run_lark_cli(["im", "messages", "reply", "--message-id", message_id, "--text", text])


def format_confirmation(fields: dict) -> str:
    """Format invoice fields into the confirmation message."""
    return CONFIRMATION_TEMPLATE.format(
        invoice_no=fields.get("invoice_no", ""),
        amount=fields.get("amount", ""),
        currency=fields.get("currency", ""),
        date=fields.get("date", ""),
        vendor=fields.get("vendor", ""),
        category=fields.get("category", ""),
        description=fields.get("description", ""),
    )
