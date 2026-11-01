#!/usr/bin/env bash
# Stop the headless client (kills its tmux session, Xvfb and the game JVM).
# The session recording is ended first so its last seconds are kept; the mp4
# is saved in the background (bin/record.sh) and nobody needs to wait for it.
. "$(dirname -- "$0")/../../lib/common.sh"
if [ -s "$RECORDER_STATE" ] && kill -TERM "$(cat "$RECORDER_STATE")" 2>/dev/null; then
  for _ in $(seq 1 15); do [ -e "$RECORDER_STATE" ] || break; sleep 1; done
  log "recording ended; the mp4 is saved to $RECORDINGS_DIR/ in the background"
fi
running=0
session_up "$CLIENT_SESSION" && running=1
if [ $running = 1 ]; then
  # End the game first, so xvfb-run sees it exit and removes its Xvfb; killing
  # the tmux session first would kill xvfb-run and leave the Xvfb behind.
  pkill -f -- "--gameDir $CLIENT_DIR" 2>/dev/null || true
  for _ in $(seq 1 30); do listening "$CLIENT_BRIDGE_PORT" || break; sleep 1; done
  tmux kill-session -t "=$CLIENT_SESSION" 2>/dev/null || true
  pkill -9 -f -- "--gameDir $CLIENT_DIR" 2>/dev/null || true
  sleep 2
fi
if [ -s "$STATE_DIR/client-display" ]; then
  pkill -x -f -- "Xvfb $(cat "$STATE_DIR/client-display") .*" 2>/dev/null || true
  rm -f "$STATE_DIR/client-display"
fi
[ $running = 1 ] || { log "not running"; exit 0; }
listening "$CLIENT_BRIDGE_PORT" && die "client bridge :$CLIENT_BRIDGE_PORT still open"
log "stopped"
