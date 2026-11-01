#!/usr/bin/env bash
# Install the headless client for the version/loader in packwiz/pack.toml.
#   install.sh             install or update in place (keeps options, saves)
#   install.sh --reinstall wipe instance/ first (HeadlessMC's game cache in hmc/ is kept)
#
# HeadlessMC (pinned below) installs Minecraft + loader into hmc/.minecraft;
# the game directory (mods, config, logs, screenshots) is instance/. The pack
# is installed with packwiz-installer -s client, then MCPFabric is added
# outside packwiz management with its bridge on 127.0.0.1:CLIENT_BRIDGE_PORT
# (project.env), UI control on.
# VirtualGL (pinned in lib/common.sh) is unpacked into infrastructure/cache/
# so launch.sh can render on the GPU.
. "$(dirname -- "$0")/../../lib/common.sh"

HMC_VERSION=2.10.0
HMC_JAR="$CLIENT_HMC_DIR/headlessmc-launcher-wrapper-$HMC_VERSION.jar"
HMC_SHA256=bf80d84516eeeb9a51fa35894c4466b146d55d0146cd6d2adc49fdd231654536

[ "${1:-}" = "--reinstall" ] && { session_up "$CLIENT_SESSION" && die "client running; stop it first"; rm -rf "$CLIENT_DIR"; }
require_supported_loader
mc=$(pack_field minecraft)
loader=$(pack_field loader)
lver=$(pack_field loader_version)
java=$(pack_java)

mkdir -p "$CLIENT_HMC_DIR/HeadlessMC" "$CLIENT_DIR"
if [ ! -s "$HMC_JAR" ]; then
  curl -fsSL -o "$HMC_JAR" "https://github.com/headlesshq/headlessmc/releases/download/$HMC_VERSION/headlessmc-launcher-wrapper-$HMC_VERSION.jar"
fi
echo "$HMC_SHA256  $HMC_JAR" | sha256sum -c --quiet - || die "HeadlessMC jar checksum mismatch"
ensure_virtualgl

cat >"$CLIENT_HMC_DIR/HeadlessMC/config.properties" <<PROPS
hmc.java.versions=/usr/lib/jvm/java-21-openjdk-amd64/bin/java;/usr/lib/jvm/java-17-openjdk-amd64/bin/java;/usr/lib/jvm/zulu-25-amd64/bin/java
hmc.mcdir=$CLIENT_HMC_DIR/.minecraft
hmc.gamedir=$CLIENT_DIR
hmc.offline=true
hmc.offline.username=$BOT_NAME
hmc.jline.enabled=false
hmc.check.xvfb=true
hmc.auto.download.java=false
hmc.crash.report.watcher=true
PROPS

hmc() { (cd "$CLIENT_HMC_DIR" && "$java" -jar "$HMC_JAR" --command "$@" 2>&1); }
case $loader in
  neoforge) hmc neoforge "$mc" --uid "$lver" | tail -5 ;;
  fabric) hmc fabric "$mc" --uid "$lver" | tail -5 ;;
esac
# Record the installed version directory so launch.sh can find it.
vdir=$(ls -1t "$CLIENT_HMC_DIR/.minecraft/versions" | grep -i "$loader" | grep -F "$lver" | head -1 || true)
[ -n "$vdir" ] || die "HeadlessMC did not produce a $loader $lver version in hmc/.minecraft/versions"
echo "$vdir $loader $lver $mc" >"$CLIENT_DIR/.installed-version"
log "client version: $vdir"

[ -f "$CLIENT_DIR/options.txt" ] || cp "$CLIENT_ROOT/templates/options.txt" "$CLIENT_DIR/options.txt"
python3 -I - "$CLIENT_DIR/servers.dat" "127.0.0.1:$GAME_PORT" "$(basename "$REPO_DIR") dev" <<'PY'
# Minimal uncompressed NBT writer: one server-list entry for the dev server,
# so MCPFabric's list_worlds/join_world can see it.
import struct, sys
def s(v): b = v.encode(); return struct.pack(">H", len(b)) + b
entry = b"\x08" + s("ip") + s(sys.argv[2]) + b"\x08" + s("name") + s(sys.argv[3]) + b"\x01" + s("acceptTextures") + b"\x01" + b"\x00"
data = b"\x0a" + s("") + b"\x09" + s("servers") + b"\x0a" + struct.pack(">i", 1) + entry + b"\x00"
open(sys.argv[1], "wb").write(data)
PY

"$CLIENT_ROOT/bin/update-pack.sh"
log "installed; launch with bin/launch.sh --join"
