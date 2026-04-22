#!/bin/bash
set -e
echo "Restarting feishu-bot..."
tmux kill-session -t feishu-bot 2>/dev/null || true
sleep 1
tmux new-session -d -s feishu-bot
tmux send-keys -t feishu-bot 'cd ~/feishu-reimbursement-bot && ./start_bot.sh' Enter
echo "Bot restarted in tmux session 'feishu-bot'. Attach with: tmux attach -t feishu-bot"
