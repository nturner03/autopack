#!/usr/bin/env bash
# Block until the server started by start.sh logs "Done (", or fails.
#   wait-ready.sh [timeout-seconds, default 900]
# Exit 0 ready; 1 crashed/exited (prints the log tail and newest crash report); 2 timeout.
. "$(dirname -- "$0")/../../lib/common.sh"
timeout=${1:-900}
started=$(cat "$STATE_DIR/server-started-at" 2>/dev/null || echo 0)
logf="$SERVER_DIR/logs/latest.log"
for ((i = 0; i < timeout; i += 2)); do
  if [ -f "$logf" ] && [ "$(stat -c %Y "$logf")" -ge "$started" ] && grep -q 'Done (' "$logf"; then
    log "ready: $(grep -m1 -o 'Done ([0-9.]*s)' "$logf")"
    exit 0
  fi
  if ! session_up "$SERVER_SESSION" ||
    tmux capture-pane -p -t "$SERVER_SESSION" | grep -q '\[server exited\]'; then
    break
  fi
  sleep 2
done
if [ "$i" -ge "$timeout" ]; then echo "timeout after ${timeout}s" >&2; exit 2; fi
echo "server exited before Done. Last log lines:" >&2
tail -25 "$logf" >&2 2>/dev/null || true
crash=$(ls -1t "$SERVER_DIR"/crash-reports/*.txt 2>/dev/null | head -1 || true)
[ -n "$crash" ] && [ "$(stat -c %Y "$crash")" -ge "$started" ] && echo "crash report: $crash" >&2
exit 1
