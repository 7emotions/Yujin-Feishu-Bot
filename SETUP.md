# Feishu Platform Setup Guide

This document describes the **one-time manual steps** required to configure the Feishu app before running the bot.

---

## Step 1: Open App Configuration

Go to [Feishu Open Platform](https://open.feishu.cn/app) and select app **`cli_a962cb8308391bd9`**.

## Step 2: Enable Bot Capability

Navigate to **Add Features** → enable **Bot** capability.

## Step 3: Configure Event Subscription

Navigate to **Events & Callbacks** → **Subscription method** → select **"Use long connection to receive events"** (使用长连接接收事件).

> This allows the bot to subscribe to events via `lark-cli event +subscribe` without needing a public HTTPS endpoint.

## Step 4: Add Event Type

Under **Events & Callbacks** → click **"Add Event"** → search for and add:
- `im.message.receive_v1` — triggered when the bot receives a message

## Step 5: Grant Permissions

Navigate to **Permissions** → enable the following scopes:
- `im:message:receive_as_bot` — allows the bot to receive messages
- `im:message.p2p_msg:readonly` — allows reading P2P (direct) messages

## Step 6: Publish the App

Click **Publish / Release** the app version to apply all changes.

> ⚠️ Changes only take effect after publishing. Re-publish whenever you add new permissions.

## Step 7: Capture Event Fixtures for Tests

After publishing, capture real event NDJSON for unit tests:

```bash
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh"
LARK_CLI_NO_PROXY=1 lark-cli event +subscribe --event-types im.message.receive_v1 --compact --quiet
```

1. Send a **JPEG invoice image** to the bot in a P2P chat → copy the printed NDJSON line to:
   `tests/fixtures/sample_event_image.json`

2. Send a **PDF invoice file** to the bot in a P2P chat → copy the printed NDJSON line to:
   `tests/fixtures/sample_event_file.json`

> ⚠️ These fixture files are **required** before Wave 3 integration tests can run (T13, T15).

---

## Verification

After completing all steps, run:

```bash
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh"
LARK_CLI_NO_PROXY=1 lark-cli event +subscribe --event-types im.message.receive_v1 --compact --quiet
```

Send a message to the bot — you should see an NDJSON event line printed to stdout.
