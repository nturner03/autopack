#!/usr/bin/env bash
# Serve packwiz/ over HTTP on SERVE_PORT (infrastructure/project.env) for the owner's
# LAN Prism client:
# http://LAN_HOST:SERVE_PORT/pack.toml
#   serve.sh          start in tmux session <SESSION_PREFIX>-packhost (returns immediately)
#   serve.sh --stop   stop it
# packwiz serve serves the WORKING TREE with auto-refresh: whatever branch is
# checked out is what the human installs. Agents' own installs use file://.
. "$(dirname -- "$0")/../infrastructure/lib/common.sh"
if [ "${1:-}" = "--stop" ]; then
  tmux kill-session -t "=$SERVE_SESSION" 2>/dev/null && log "stopped" || log "not running"
  exit 0
fi
session_up "$SERVE_SESSION" && { log "already running"; exit 0; }
[ -f "$PACK_TOML" ] || die "no pack.toml at $PACK_TOML yet"
tmux new-session -d -s "$SERVE_SESSION" -c "$(dirname "$PACK_TOML")" "$PACKWIZ" serve --port "$SERVE_PORT"
for _ in $(seq 1 20); do listening "$SERVE_PORT" && break; sleep 0.5; done
listening "$SERVE_PORT" || die "packwiz serve did not start; tmux attach -t $SERVE_SESSION"
log "serving http://$LAN_HOST:$SERVE_PORT/pack.toml (tmux $SERVE_SESSION)"
