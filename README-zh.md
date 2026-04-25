# 飞书机器人平台

这是一个通用飞书机器人平台，包含：
- 运行时路由与会话管理
- 可复用的飞书适配层与工具集
- 插件化能力扩展
- 作为示例能力的报销工作流插件
- 带上下文字段的聊天兜底插件

## 安装

```bash
pip install -r requirements.txt
```

## 运行

主入口：

```bash
python -m runtime.app
```

脚本快捷方式：

```bash
./start_bot.sh
```

## 验证环境

```bash
python -m runtime.app --dry-run
```

## 测试

完整测试：

```bash
python -m pytest tests/ -q
```

聚焦示例：

```bash
python -m pytest tests/test_chat_plugin.py -q
```

## 架构

- `runtime/` —— 路由器、会话存储、启动装配、主入口
- `adapters/feishu/` —— 飞书鉴权、配置、事件适配
- `toolsets/feishu/` —— 飞书消息 / 文件 / 审批等可复用操作
- `plugins/chat/` —— 通用聊天兜底插件
- `plugins/reimbursement/` —— 报销插件
- `domain/reimbursement/` —— 报销领域逻辑、解析、工作流、表单构造

## 路由规则

- 优先命中当前激活插件会话
- 否则按插件 `match()` 分数选择最高者
- 忽略机器人自己的消息
- 忽略非 `p2p` 会话消息

## 新增插件示例

插件需要实现 `runtime.plugin.BotPlugin`。

示例：

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
        return "处理问候语与简单欢迎消息。"

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

在 `runtime/bootstrap.py` 中注册：

```python
from plugins.hello.plugin import HelloPlugin

bot.register_plugin(HelloPlugin())
```

说明：
- `match()` 返回分数，未激活会话时分数最高的插件获胜。
- `capability_description` 与 `tool_descriptions` 会参与聊天插件系统提示词构造。
- 如果插件是多轮流程，应该在 `handle()` 中设置 `session.active_plugin`，并在流程结束时释放。

## 说明

- `start_bot.sh` 只是 `python -m runtime.app` 的封装。
- 旧的 `bot.*` 路径如果还存在，只应用于兼容场景，不应作为新代码依赖目标。
