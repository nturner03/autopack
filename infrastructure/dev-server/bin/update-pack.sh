#!/usr/bin/env bash
# Install the pack's working tree into the dev server (server-side files only),
# plus MCPFabric and the dev-only tool mods (infrastructure/dev-mods/).
# Runs `packwiz refresh` first, then packwiz-installer from a file:// URL, so
# the packwiz serve daemon is not needed. Safe to run while the server is
# stopped; while it runs, only KubeJS server scripts / quests / datapacks take
# effect without a restart (via /reload or `ftbquests reload quests`).
. "$(dirname -- "$0")/../../lib/common.sh"
[ -d "$SERVER_DIR" ] || die "server not installed; run bin/install.sh"
refresh_pack
ensure_bootstrap
cd "$SERVER_DIR"
"$(pack_java)" -jar "$BOOTSTRAP_JAR" -g -s server "$(pack_url)" >"$SERVER_DIR/packwiz-update.log" 2>&1 ||
  { tail -20 "$SERVER_DIR/packwiz-update.log" >&2; die "packwiz-installer failed (log: $SERVER_DIR/packwiz-update.log)"; }
if ! ls mods/mcpfabric-*.jar >/dev/null 2>&1; then
  jar=$(fetch_mcpfabric "$SERVER_DIR/mods")
  log "MCPFabric re-added: $jar"
fi
ensure_dev_mods
install_dev_mods "$SERVER_DIR/mods"
log "pack installed: $(pack_field name) $(pack_field version)"
