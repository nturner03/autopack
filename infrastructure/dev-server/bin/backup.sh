#!/usr/bin/env bash
# Back up the dev-server world to backups/<world>-<stamp>[-label].tar.gz.
# A running server is paused (save-off, save-all flush) for the copy.
#   backup.sh [label]       env PEXP_BACKUP_KEEP (default 20; 0 keeps all)
. "$(dirname -- "$0")/../../lib/common.sh"
KEEP=${PEXP_BACKUP_KEEP:-20}
LEVEL=$(sed -n 's/^level-name=//p' "$SERVER_DIR/server.properties")
LEVEL=${LEVEL:-world}
LOGF="$SERVER_DIR/logs/latest.log"
label=${1:-}
label=${label//[^A-Za-z0-9._-]/_}
name="${LEVEL}-$(date +%Y%m%d-%H%M%S)${label:+-$label}.tar.gz"
[ -d "$SERVER_DIR/$LEVEL" ] || die "no world at $SERVER_DIR/$LEVEL"
mkdir -p "$BACKUP_DIR"

running=0
session_up "$SERVER_SESSION" && listening "$GAME_PORT" && running=1
console() { tmux send-keys -t "$SERVER_SESSION" "$1" Enter; }
resume() { [ "$running" = 1 ] && console "save-on" || true; }
if [ "$running" = 1 ]; then
  trap resume EXIT
  before=$(wc -l <"$LOGF")
  console "save-off"
  console "save-all flush"
  for _ in $(seq 1 120); do
    tail -n +"$((before + 1))" "$LOGF" | grep -q 'Saved the game' && break
    sleep 0.5
  done
  tail -n +"$((before + 1))" "$LOGF" | grep -q 'Saved the game' || die "timed out waiting for 'Saved the game'"
fi
tmp="$BACKUP_DIR/.$name.partial"
tar -C "$SERVER_DIR" -czf "$tmp" "$LEVEL"
mv "$tmp" "$BACKUP_DIR/$name"
if [ "$running" = 1 ]; then trap - EXIT; resume; fi
if [ "$KEEP" -gt 0 ]; then
  ls -1t "$BACKUP_DIR/$LEVEL"-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm --
fi
echo "$BACKUP_DIR/$name ($(du -h "$BACKUP_DIR/$name" | cut -f1))"
