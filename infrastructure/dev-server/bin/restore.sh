#!/usr/bin/env bash
# Restore a world backup made by backup.sh. Refuses while the server runs;
# the current world is moved aside to <world>.replaced-<stamp>, never deleted.
#   restore.sh <archive>
. "$(dirname -- "$0")/../../lib/common.sh"
[ $# -eq 1 ] || die "usage: restore.sh <archive>"
archive=$1
LEVEL=$(sed -n 's/^level-name=//p' "$SERVER_DIR/server.properties")
LEVEL=${LEVEL:-world}
[ -f "$archive" ] || die "no archive: $archive"
tar -tzf "$archive" "$LEVEL/level.dat" >/dev/null 2>&1 || die "$archive does not contain $LEVEL/level.dat"
session_up "$SERVER_SESSION" && die "server is running; stop it first"
if [ -e "$SERVER_DIR/$LEVEL" ]; then
  aside="$SERVER_DIR/$LEVEL.replaced-$(date +%Y%m%d-%H%M%S)"
  mv "$SERVER_DIR/$LEVEL" "$aside"
  log "current world moved to $aside"
fi
tar -C "$SERVER_DIR" -xzf "$archive"
"$SERVER_ROOT/bin/world-log.sh" "restored world from $(basename "$archive")"
log "restored $archive"
