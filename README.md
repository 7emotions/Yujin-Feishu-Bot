# Feishu Bot Platform

Universal Feishu bot platform with:
- runtime routing and session handling
- reusable Feishu adapters/toolsets
- plugin-based capabilities
- reimbursement workflow as one plugin
- chat fallback with context fields in session state

## Install

```bash
pip install -r requirements.txt
```

## Run

Entrypoint:

```bash
python -m runtime.app
```

Shell shortcut:

```bash
./start_bot.sh
```

## Verify setup

```bash
python -m runtime.app --dry-run
```

## Tests

Full suite:

```bash
python -m pytest tests/ -q
```

Focused example:

```bash
python -m pytest tests/test_reimbursement_plugin.py -q
```

## Architecture

- `runtime/` — router, session store, bootstrap, canonical app entrypoint
- `adapters/feishu/` — Feishu auth, settings, event adaptation
- `toolsets/feishu/` — reusable Feishu message/file/approval operations
- `plugins/chat/` — fallback chat plugin
- `plugins/reimbursement/` — reimbursement plugin
- `domain/reimbursement/` — reimbursement parser, workflow, form shaping

## Add a new plugin

Plugins implement `runtime.plugin.BotPlugin`.

Minimal example:

```python
from runtime.plugin import BotPlugin
from runtime.session_store import SessionStore, UserSession
from toolsets.feishu import messaging as message_sender

EventDict = dict[str, object]


class HelloPlugin(BotPlugin):
    @property
    def name(self) -> str:
        return "hello"

    @property
    def capability_description(self) -> str:
        return "处理问候语和简单欢迎消息。"

    @property
    def tool_descriptions(self) -> list[str]:
        return ["reply_text：直接回复用户"]

    def match(self, event: EventDict, session: UserSession) -> float:
        try:
            message = event["event"]["message"]
            content = str(message.get("content", ""))
        except (KeyError, TypeError, AttributeError):
            return 0.0
        if message.get("message_type") != "text":
            return 0.0
        return 0.8 if "hello" in content.lower() or "你好" in content else 0.0

    def handle(self, event: EventDict, session: UserSession) -> None:
        message_sender.reply_text(session.message_id, "你好！很高兴见到你。")

    def on_tick(self, session_store: SessionStore) -> None:
        _ = session_store
```

Register it in `runtime/bootstrap.py`:

```python
from plugins.hello.plugin import HelloPlugin

bot.register_plugin(HelloPlugin())
```

Notes:
- `match()` returns a score; higher scores win when there is no active plugin session.
- `capability_description` and `tool_descriptions` are consumed by the chat prompt builder.
- If the plugin owns a multi-turn workflow, set `session.active_plugin` in `handle()` and release it when the workflow completes.

## Routing

- active plugin session first
- otherwise highest plugin `match()` score wins
- self-messages and non-`p2p` chats are ignored

## Notes

- `start_bot.sh` launches the canonical runtime entrypoint.
- `bot.*` imports still work for compatibility but emit `DeprecationWarning`.
