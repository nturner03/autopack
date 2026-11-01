#!/usr/bin/env bash
# Send a console command through tmux (fallback when the MCPFabric bridge is
# down; prefer `scripts/mcf.py run_command` because it returns output).
#   console.sh "say hello"
. "$(dirname -- "$0")/../../lib/common.sh"
session_up "$SERVER_SESSION" || die "server not running"
tmux send-keys -t "$SERVER_SESSION" "$*" Enter
