# pyright: reportImportCycles=false
"""Public package exports for feishu-reimbursement-bot."""

def __getattr__(name: str) -> object:
    if name == "token_manager":
        from .token_manager import token_manager

        return token_manager
    if name == "TokenManager":
        from .token_manager import TokenManager

        return TokenManager
    if name == "state_machine":
        from .state_machine import state_machine

        return state_machine
    if name == "ConversationStateMachine":
        from .state_machine import ConversationStateMachine

        return ConversationStateMachine
    if name == "start_event_loop":
        from .main import start_event_loop

        return start_event_loop
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
