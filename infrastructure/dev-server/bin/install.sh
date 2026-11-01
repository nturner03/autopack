#!/usr/bin/env bash
# Install (or reinstall) the dev server for the Minecraft version and loader
# named in packwiz/pack.toml, then install the pack into it.
#
#   install.sh                 install if missing; keep an existing world
#   install.sh --reinstall     wipe server/ (world moved to backups/ first) and install fresh
#   install.sh --seed N        seed for a new world (default: random, recorded in world-log)
#
# Writes server.properties, eula.txt, user_jvm_args.txt, the MCPFabric bridge
# config (SERVER_BRIDGE_PORT from project.env, token from infrastructure/.state) and installs
# MCPFabric outside packwiz management. The server is not started.

. "$(dirname -- "$0")/../../lib/common.sh"

reinstall=0
seed=""
while [ $# -gt 0 ]; do
  case $1 in
    --reinstall) reinstall=1 ;;
    --seed) seed=$2; shift ;;
    *) sed -n '2,12p' "$0" >&2; exit 2 ;;
  esac
  shift
done

require_supported_loader
session_up "$SERVER_SESSION" && die "server is running; stop it first (bin/stop.sh)"

mc=$(pack_field minecraft)
loader=$(pack_field loader)
lver=$(pack_field loader_version)
java=$(pack_java)
log "installing $loader $lver for Minecraft $mc with $java"

if [ "$reinstall" = 1 ] && [ -d "$SERVER_DIR" ]; then
  if [ -d "$SERVER_DIR/world" ]; then
    mkdir -p "$BACKUP_DIR"
    aside="$BACKUP_DIR/world-before-reinstall-$(date +%Y%m%d-%H%M%S)"
    mv "$SERVER_DIR/world" "$aside"
    log "old world moved to $aside"
  fi
  rm -rf "$SERVER_DIR"
fi
mkdir -p "$SERVER_DIR"
cd "$SERVER_DIR"

case $loader in
  neoforge)
    if [ ! -f "libraries/net/neoforged/neoforge/$lver/unix_args.txt" ]; then
      inst="$CACHE_DIR/neoforge-$lver-installer.jar"
      [ -s "$inst" ] || curl -fsSL -o "$inst" \
        "https://maven.neoforged.net/releases/net/neoforged/neoforge/$lver/neoforge-$lver-installer.jar"
      "$java" -jar "$inst" --installServer "$SERVER_DIR" >"$SERVER_DIR/installer.log" 2>&1 ||
        die "NeoForge installer failed; see $SERVER_DIR/installer.log"
      # The installer drops its own run scripts; bin/run-server.sh replaces them.
      rm -f run.sh run.bat
    fi
    ;;
  fabric)
    if [ ! -s fabric-server-launch.jar ]; then
      installer=$(curl -fsSL https://meta.fabricmc.net/v2/versions/installer |
        python3 -I -c 'import json,sys; print(next(v["version"] for v in json.load(sys.stdin) if v["stable"]))')
      curl -fsSL -o fabric-server-launch.jar \
        "https://meta.fabricmc.net/v2/versions/loader/$mc/$lver/$installer/server/jar"
    fi
    ;;
esac
echo "$loader $lver $mc" >"$SERVER_DIR/.installed-loader"

cp "$SERVER_ROOT/templates/user_jvm_args.txt" user_jvm_args.txt
echo "eula=true" >eula.txt
if [ ! -f server.properties ]; then
  [ -n "$seed" ] || seed=$(python3 -I -c 'import random; print(random.randrange(-2**63, 2**63))')
  sed -e "s/@SEED@/$seed/" -e "s/@GAME_PORT@/$GAME_PORT/" -e "s/@MOTD@/$(basename "$REPO_DIR") dev server/" \
    "$SERVER_ROOT/templates/server.properties" >server.properties
  "$SERVER_ROOT/bin/world-log.sh" "new world from install.sh (seed $seed, $loader $lver, MC $mc)"
elif [ -n "$seed" ]; then
  [ -d world ] && die "world exists; use bin/reset-world.sh --seed $seed"
  sed -i "s/^level-seed=.*/level-seed=$seed/" server.properties
  "$SERVER_ROOT/bin/world-log.sh" "seed set to $seed by install.sh before first start"
fi

# Op the headless client's offline account so agents can run commands as it.
python3 -I - "$BOT_NAME" <<'PY'
import hashlib, json, sys, uuid
name = sys.argv[1]
h = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode()).digest())
h[6] = (h[6] & 0x0F) | 0x30
h[8] = (h[8] & 0x3F) | 0x80
entry = {"uuid": str(uuid.UUID(bytes=bytes(h))), "name": name, "level": 4,
         "bypassesPlayerLimit": True}
try:
    ops = json.load(open("ops.json"))
except (OSError, ValueError):
    ops = []
ops = [o for o in ops if o.get("name") != name] + [entry]
json.dump(ops, open("ops.json", "w"), indent=2)
PY

write_mcpfabric_config "$SERVER_DIR/config" "$SERVER_BRIDGE_PORT" false
jar=$(fetch_mcpfabric "$SERVER_DIR/mods")
log "MCPFabric: $jar"
"$SERVER_ROOT/bin/update-pack.sh"
log "installed into $SERVER_DIR; start with bin/start.sh"
