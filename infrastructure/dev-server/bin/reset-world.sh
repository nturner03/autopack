#!/usr/bin/env bash
# Replace the dev-server world with a fresh one (old world is backed up first).
#   reset-world.sh [--seed N]     default: random seed
# Refuses while the server runs. Logs the reset and seed in docs/testing/world-log.md.
# Worldgen changes (new ores, structures, biomes) only appear in new chunks:
# reset or explore far away before judging them.
. "$(dirname -- "$0")/../../lib/common.sh"
seed=""
[ "${1:-}" = "--seed" ] && seed=${2:?--seed needs a value}
session_up "$SERVER_SESSION" && die "server is running; stop it first (bin/stop.sh)"
[ -n "$seed" ] || seed=$(python3 -I -c 'import random; print(random.randrange(-2**63, 2**63))')
if [ -d "$SERVER_DIR/world" ]; then
  "$SERVER_ROOT/bin/backup.sh" before-reset >/dev/null
  rm -rf "$SERVER_DIR/world"
fi
sed -i "s/^level-seed=.*/level-seed=$seed/" "$SERVER_DIR/server.properties"
"$SERVER_ROOT/bin/world-log.sh" "world reset (seed $seed)"
log "world reset; seed $seed. Start with bin/start.sh"
