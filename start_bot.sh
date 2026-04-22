#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
export LARK_CLI_NO_PROXY=1
python bot/main.py "$@"
