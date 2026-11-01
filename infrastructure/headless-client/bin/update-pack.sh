#!/usr/bin/env bash
# Install the pack's working tree into the headless client (client-side files),
# then make sure MCPFabric and its bridge config (CLIENT_BRIDGE_PORT) are in place,
# plus the dev-only tool mods (ensure_dev_mods / install_dev_mods in lib/common.sh).
# Run while the client is stopped; launch.sh calls it unless PEXP_SKIP_UPDATE=1.
. "$(dirname -- "$0")/../../lib/common.sh"
[ -f "$CLIENT_DIR/.installed-version" ] || die "client not installed; run bin/install.sh"
refresh_pack
ensure_bootstrap
cd "$CLIENT_DIR"
"$(pack_java)" -jar "$BOOTSTRAP_JAR" -g -s client "$(pack_url)" >"$CLIENT_DIR/packwiz-update.log" 2>&1 ||
  { tail -20 "$CLIENT_DIR/packwiz-update.log" >&2; die "packwiz-installer failed (log: $CLIENT_DIR/packwiz-update.log)"; }
if ! ls mods/mcpfabric-*.jar >/dev/null 2>&1; then
  jar=$(fetch_mcpfabric "$CLIENT_DIR/mods")
  log "MCPFabric added: $jar"
fi
write_mcpfabric_config "$CLIENT_DIR/config" "$CLIENT_BRIDGE_PORT" true
ensure_dev_mods
install_dev_mods "$CLIENT_DIR/mods"
log "client pack installed: $(pack_field name) $(pack_field version)"
