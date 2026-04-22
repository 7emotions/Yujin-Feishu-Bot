# Feishu Invoice Reimbursement Bot

## Prerequisites

- Python 3.10+
- Node.js 18+ with `lark-cli` installed (`npm install -g @larksuiteoapi/lark-cli`)
- A Feishu custom app with bot capability enabled
- OpenAI API key with GPT-4o access

```bash
pip install -r requirements.txt
```

## One-time Setup

1. Follow **SETUP.md** — configure your Feishu app, enable events, add scopes
2. Follow **APPROVAL_SETUP.md** — create the approval definition in the admin console
3. Copy `.env.example` to `.env` and fill in all values

## Running

```bash
./start_bot.sh
```

## Stopping

Press `Ctrl+C`. The bot handles `SIGTERM` gracefully.

## Running Tests

```bash
python -m pytest tests/ -v
```

## Architecture

```
User
 │  (sends invoice image / PDF)
 ▼
Feishu IM
 │  (im.message.receive_v1 event)
 ▼
lark-cli event stream  (NDJSON on stdout)
 │
 ▼
main.py  (reads lines, routes events)
 │
 ▼
state_machine.py  (per-user FSM: IDLE → PROCESSING → AWAITING_CONFIRM → IDLE)
 │
 ├─► file_downloader.py  ──► invoice_parser.py (GPT-4o vision)
 │                                │
 │                                ▼
 │                         message_sender.py  (send confirmation via lark-cli)
 │
 └─► [on confirm]
      attachment_uploader.py  (POST to www.feishu.cn)
       │
       ▼
      approval_creator.py  (POST to open.feishu.cn/approval/v4/instances)
       │
       ▼
      message_sender.py  (send success message with instance_code)
```
