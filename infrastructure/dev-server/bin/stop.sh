#!/usr/bin/env bash
# Stop the dev server cleanly and wait for the game port to close.
#   stop.sh [timeout-seconds, default 120]
. "$(dirname -- "$0")/../../lib/common.sh"
timeout=${1:-120}
if ! session_up "$SERVER_SESSION"; then log "not running"; exit 0; fi
tmux send-keys -t "$SERVER_SESSION" stop Enter
for ((i = 0; i < timeout; i++)); do
  if tmux capture-pane -p -t "$SERVER_SESSION" | grep -q '\[server exited\]' && ! listening "$GAME_PORT"; then
    break
  fi
  sleep 1
done
tmux kill-session -t "=$SERVER_SESSION" 2>/dev/null || true
listening "$GAME_PORT" && die "port $GAME_PORT still open after ${timeout}s"
log "stopped"
