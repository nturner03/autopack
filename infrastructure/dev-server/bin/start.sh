#!/usr/bin/env bash
# Start the dev server in tmux session <SESSION_PREFIX>-server.
#   start.sh            update the pack from the working tree, then start
#   PEXP_SKIP_UPDATE=1 start.sh   start without updating
# Returns immediately; use bin/wait-ready.sh to block until "Done (".
. "$(dirname -- "$0")/../../lib/common.sh"
[ -d "$SERVER_DIR" ] || die "server not installed; run bin/install.sh"
session_up "$SERVER_SESSION" && die "already running (tmux session $SERVER_SESSION)"
listening "$GAME_PORT" && die "port $GAME_PORT is taken by another process"
installed=$(cat "$SERVER_DIR/.installed-loader")
want="$(pack_field loader) $(pack_field loader_version) $(pack_field minecraft)"
[ "$installed" = "$want" ] || die "server has '$installed' but pack.toml wants '$want'; run bin/install.sh --reinstall"
[ "${PEXP_SKIP_UPDATE:-0}" = 1 ] || "$SERVER_ROOT/bin/update-pack.sh"
sed -i "s/^server-port=.*/server-port=$GAME_PORT/" "$SERVER_DIR/server.properties"
write_mcpfabric_config "$SERVER_DIR/config" "$SERVER_BRIDGE_PORT" false
date +%s >"$STATE_DIR/server-started-at"
tmux new-session -d -s "$SERVER_SESSION" -c "$SERVER_DIR" "$SERVER_ROOT/bin/run-server.sh; echo '[server exited]'; sleep 600"
log "started in tmux session $SERVER_SESSION"
