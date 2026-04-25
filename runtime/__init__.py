def __getattr__(name: str) -> object:
    if name == "bot":
        from runtime.bootstrap import bot

        return bot
    if name == "BotPlugin":
        from runtime.plugin import BotPlugin

        return BotPlugin
    if name == "FeishuBot":
        from runtime.router import FeishuBot

        return FeishuBot
    if name == "SessionStore":
        from runtime.session_store import SessionStore

        return SessionStore
    if name == "UserSession":
        from runtime.session_store import UserSession

        return UserSession
    if name == "session_store":
        from runtime.session_store import session_store

        return session_store
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["BotPlugin", "FeishuBot", "SessionStore", "UserSession", "bot", "session_store"]
