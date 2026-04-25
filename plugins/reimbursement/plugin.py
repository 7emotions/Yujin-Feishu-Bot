from typing import Any

from domain.reimbursement.workflow import AWAITING_CONFIRM_STATE, PROCESSING_STATE
from domain.reimbursement.workflow import ReimbursementWorkflow
from runtime.plugin import BotPlugin
from runtime.session_store import SessionStore, UserSession
from toolsets.feishu import approval_attachments as attachment_uploader
from toolsets.feishu import approvals as approval_creator
from toolsets.feishu import file_resources as file_downloader
from toolsets.feishu import messaging as message_sender
import domain.reimbursement.parser as invoice_parser

EventDict = dict[str, Any]


class ReimbursementPlugin(BotPlugin):
    def __init__(self, workflow: ReimbursementWorkflow | None = None) -> None:
        self._workflow = workflow or ReimbursementWorkflow(
            approval_creator,
            attachment_uploader,
            file_downloader,
            invoice_parser,
            message_sender,
        )

    @property
    def name(self) -> str:
        return "reimbursement"

    @property
    def capability_description(self) -> str:
        return "处理报销相关流程，包括发票图片/PDF识别、字段修改、确认提交、取消和审批提交。"

    @property
    def tool_descriptions(self) -> list[str]:
        return [
            "download_file：下载飞书消息中的图片或文件资源",
            "format_confirmation：格式化报销确认消息",
            "mark_typing：给用户显示处理中状态",
            "upload_approval_attachment：上传审批附件",
            "create_reimbursement_approval：创建报销审批单",
        ]

    def match(self, event: EventDict, session: UserSession) -> float:
        return self._workflow.match(event, session, self.name)

    def handle(self, event: EventDict, session: UserSession) -> None:
        self._workflow.handle(event, session, self.name)

    def on_tick(self, session_store: SessionStore) -> None:
        self._workflow.on_tick(session_store, self.name)
