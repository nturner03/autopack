# Shared settings and helpers for the dev server and the headless client.
# Source it from a bin/ script:  . "$(dirname -- "$0")/../../lib/common.sh"
#
# Everything version-specific is read from the pack's pack.toml, so the same
# scripts work whatever Minecraft version and loader the pack moves to.
#
# Env overrides:
#   PEXP_PACK_TOML   pack.toml to install from (default <repo>/packwiz/pack.toml)
#   PEXP_JAVA        Java executable for the game (default picked from the MC version)
#   PEXP_PACKWIZ     packwiz binary (default ~/go/bin/packwiz)
#   PEXP_MCPFABRIC_DIR  MCPFabric checkout with mcp-server built (default ~/tools/mcpfabric;
#                    read by .mcp.json, scripts/mcf.py and scripts/doctor.sh)

set -euo pipefail

INFRA_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$INFRA_DIR/.." && pwd)
STATE_DIR="$INFRA_DIR/.state"
CACHE_DIR="$INFRA_DIR/cache"

SERVER_ROOT="$INFRA_DIR/dev-server"
SERVER_DIR="$SERVER_ROOT/server"
BACKUP_DIR="$SERVER_ROOT/backups"
CLIENT_ROOT="$INFRA_DIR/headless-client"
CLIENT_HMC_DIR="$CLIENT_ROOT/hmc"
CLIENT_DIR="$CLIENT_ROOT/instance"

# Per-experiment settings: ports, LAN address, tmux prefix. Ports must be
# free on this host (and not used by another experiment) before they are filled in.
PROJECT_ENV="$INFRA_DIR/project.env"
[ -f "$PROJECT_ENV" ] || { echo "error: missing $PROJECT_ENV" >&2; exit 1; }
# shellcheck source=../project.env
. "$PROJECT_ENV"
GAME_PORT=${GAME_PORT:-}
SERVE_PORT=${SERVE_PORT:-}
SERVER_BRIDGE_PORT=${SERVER_BRIDGE_PORT:-}
CLIENT_BRIDGE_PORT=${CLIENT_BRIDGE_PORT:-}
LAN_HOST=${LAN_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}
SESSION_PREFIX=${SESSION_PREFIX:-pexp-$(basename "$REPO_DIR")}

ports_configured() {
  [ -n "$GAME_PORT" ] && [ -n "$SERVE_PORT" ] && [ -n "$SERVER_BRIDGE_PORT" ] && [ -n "$CLIENT_BRIDGE_PORT" ]
}
# Every script except status.sh needs the ports. status.sh sets
# PEXP_PORTS_OPTIONAL=1 so it can report that they are missing.
if [ "${PEXP_PORTS_OPTIONAL:-0}" != 1 ] && ! ports_configured; then
  echo "error: ports are not set in $PROJECT_ENV." >&2
  echo "Pick four free ports first (README.md \"Starting an experiment\")." >&2
  exit 1
fi

SERVER_SESSION=$SESSION_PREFIX-server
CLIENT_SESSION=$SESSION_PREFIX-client
SERVE_SESSION=$SESSION_PREFIX-packhost
BOT_NAME=PexpBot

PACK_TOML=${PEXP_PACK_TOML:-$REPO_DIR/packwiz/pack.toml}
PACKWIZ=${PEXP_PACKWIZ:-$HOME/go/bin/packwiz}
TOKEN_FILE="$STATE_DIR/mcpfabric-token"
BOOTSTRAP_JAR="$CACHE_DIR/packwiz-installer-bootstrap.jar"
BOOTSTRAP_URL=https://github.com/packwiz/packwiz-installer-bootstrap/releases/download/v0.0.3/packwiz-installer-bootstrap.jar

mkdir -p "$STATE_DIR" "$CACHE_DIR"

die() { echo "error: $*" >&2; exit 1; }
log() { echo "[$(date +%H:%M:%S)] $*"; }

# pack_field <minecraft|loader|loader_version|name|version>
pack_field() {
  [ -f "$PACK_TOML" ] || die "no pack.toml at $PACK_TOML (run 'packwiz init' in packwiz/ first)"
  python3 -I - "$PACK_TOML" "$1" <<'PY'
import sys, tomllib
data = tomllib.load(open(sys.argv[1], "rb"))
v = data.get("versions", {})
loaders = [k for k in ("neoforge", "fabric", "forge", "quilt") if k in v]
field = sys.argv[2]
if field == "minecraft":
    print(v["minecraft"])
elif field == "loader":
    print(loaders[0] if loaders else "vanilla")
elif field == "loader_version":
    print(v[loaders[0]] if loaders else "")
else:
    print(data.get(field, ""))
PY
}

# Java for a Minecraft version: 1.20.5-1.21.x need 21, 26.x needs 25, older 17.
# Never fall back to the PATH java, which may be the wrong version.
# These are Debian/Ubuntu package paths; set PEXP_JAVA elsewhere.
java_for_mc() {
  if [ -n "${PEXP_JAVA:-}" ]; then echo "$PEXP_JAVA"; return; fi
  local mc=$1 major minor patch
  IFS=. read -r major minor patch <<<"$mc"
  patch=${patch:-0}
  if [ "$major" -ge 26 ]; then
    echo /usr/lib/jvm/zulu-25-amd64/bin/java
  elif [ "$major" = 1 ] && { [ "$minor" -gt 20 ] || { [ "$minor" = 20 ] && [ "$patch" -ge 5 ]; }; }; then
    echo /usr/lib/jvm/java-21-openjdk-amd64/bin/java
  else
    echo /usr/lib/jvm/java-17-openjdk-amd64/bin/java
  fi
}

pack_java() {
  local j
  j=$(java_for_mc "$(pack_field minecraft)")
  [ -x "$j" ] || die "Java not found: $j (set PEXP_JAVA)"
  echo "$j"
}

# MCPFabric only exists for Fabric and NeoForge on 1.21.1-1.21.11 and 26.x.
require_supported_loader() {
  case "$(pack_field loader)" in
    neoforge|fabric) ;;
    *) die "loader '$(pack_field loader)' unsupported: MCPFabric (agent test bridge) ships only for fabric and neoforge" ;;
  esac
}

ensure_token() {
  if [ ! -s "$TOKEN_FILE" ]; then
    umask 077
    python3 -I -c 'import secrets; print(secrets.token_hex(24), end="")' >"$TOKEN_FILE"
  fi
  chmod 600 "$TOKEN_FILE"
}

ensure_bootstrap() {
  [ -s "$BOOTSTRAP_JAR" ] || curl -fsSL -o "$BOOTSTRAP_JAR" "$BOOTSTRAP_URL"
}

# fetch_mcpfabric <dest-mods-dir>: put the MCPFabric build matching the pack's
# MC version and loader into a mods folder, outside packwiz's management.
# MCPFabric is test infrastructure, not pack content: players never get it.
fetch_mcpfabric() {
  local dest=$1 mc loader info url file
  mc=$(pack_field minecraft)
  loader=$(pack_field loader)
  info=$(curl -fsSL -A pack-experiment-infra \
    "https://api.modrinth.com/v2/project/mcpfabric/version?loaders=%5B%22$loader%22%5D&game_versions=%5B%22$mc%22%5D" |
    python3 -I -c 'import json,sys
v=json.load(sys.stdin)
f=next((f for f in v[0]["files"] if f["primary"]), v[0]["files"][0]) if v else None
print(f["url"], f["filename"]) if f else None')
  [ -n "$info" ] || die "no MCPFabric build on Modrinth for $loader $mc"
  url=${info% *}
  file=${info#* }
  mkdir -p "$dest"
  [ -s "$CACHE_DIR/$file" ] || curl -fsSL -o "$CACHE_DIR/$file" "$url"
  find "$dest" -maxdepth 1 -name 'mcpfabric-*.jar' ! -name "$file" -delete
  cp -f "$CACHE_DIR/$file" "$dest/$file"
  echo "$file"
}

# Dev-only tool mods (agent infrastructure such as pexp_devtools: /pexp dump
# and the /studio capture commands). Sources live in infrastructure/dev-mods/
# (tracked); `scripts/build-custom-mod.sh <name> --dev` builds them into
# $DEV_MODS_DIR, and the update-pack scripts install them into the dev server
# AND the headless client, beside MCPFabric. Never pack content, never in
# packwiz/. Every dev mod must load on both sides (client code behind Dist
# checks) and use displayTest IGNORE_ALL_VERSION.
DEV_MODS_DIR="$CACHE_DIR/dev-mods"
DEV_MODS_SRC="$INFRA_DIR/dev-mods"

# dev_mod_hash <project-dir>: hash of a dev mod's sources and build files.
dev_mod_hash() {
  (cd "$1" && find src build.gradle settings.gradle gradle.properties -type f -print0 2>/dev/null |
    sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)
}

# ensure_dev_mods: (re)build every dev mod whose sources changed since its last
# build (first build downloads Gradle and NeoForge: a few minutes).
ensure_dev_mods() {
  local dir name hash stamp
  [ -d "$DEV_MODS_SRC" ] || return 0
  for dir in "$DEV_MODS_SRC"/*/; do
    [ -x "$dir/gradlew" ] || continue
    name=$(basename "$dir")
    hash=$(dev_mod_hash "$dir")
    stamp="$DEV_MODS_DIR/.$name.srchash"
    if [ "$(cat "$stamp" 2>/dev/null)" != "$hash" ] || ! ls "$DEV_MODS_DIR/$name"[-_][0-9]*.jar >/dev/null 2>&1; then
      log "building dev mod $name (sources changed or no jar)"
      "$REPO_DIR/scripts/build-custom-mod.sh" "$name" --dev >&2 || die "dev mod $name failed to build"
      mkdir -p "$DEV_MODS_DIR"
      echo "$hash" >"$stamp"
    fi
  done
}

# install_dev_mods <dest-mods-dir>: copy every dev-only jar in, replacing older
# builds of the same mod (same file name up to the version).
install_dev_mods() {
  local dest=$1 jar file stem
  [ -d "$DEV_MODS_DIR" ] || return 0
  mkdir -p "$dest"
  for jar in "$DEV_MODS_DIR"/*.jar; do
    [ -e "$jar" ] || continue
    file=$(basename "$jar")
    stem=$(echo "$file" | sed -E 's/[-_][0-9].*$//')
    find "$dest" -maxdepth 1 -name "$stem[-_][0-9]*.jar" ! -name "$file" -delete
    cmp -s "$jar" "$dest/$file" || { cp -f "$jar" "$dest/$file"; log "dev mod installed: $file"; }
  done
}

# VirtualGL (pinned, checksum-verified, unpacked into the cache, no root):
# the headless client renders on the host's NVIDIA GPU through VirtualGL's
# EGL back end while its window stays on Xvfb. Mesa llvmpipe is the fallback.
VGL_VERSION=3.1.5
VGL_SHA256=df3f7788ce41b182a47c0d298e5cd6d2d63579522cb41825970b7726e825485e
VGL_DIR="$CACHE_DIR/virtualgl-$VGL_VERSION"
NVIDIA_EGL_VENDOR=/usr/share/glvnd/egl_vendor.d/10_nvidia.json
# Below this much free GPU memory (other services share the card) the client
# falls back to llvmpipe.
CLIENT_GPU_MIN_FREE_MIB=1536

# Session videos of the headless client (bin/record.sh), one mp4 per launch.
RECORDINGS_DIR="$CLIENT_ROOT/recordings"
RECORDER_STATE="$STATE_DIR/client-recorder"
RECORD_MIN_FREE_GIB=5

ensure_virtualgl() {
  [ -x "$VGL_DIR/opt/VirtualGL/bin/vglrun" ] && return 0
  local deb="$CACHE_DIR/virtualgl_${VGL_VERSION}_amd64.deb"
  [ -s "$deb" ] || curl -fsSL -o "$deb" \
    "https://github.com/VirtualGL/virtualgl/releases/download/$VGL_VERSION/virtualgl_${VGL_VERSION}_amd64.deb"
  echo "$VGL_SHA256  $deb" | sha256sum -c --quiet - || { rm -f "$deb"; die "VirtualGL .deb checksum mismatch"; }
  rm -rf "$VGL_DIR.tmp"
  dpkg-deb -x "$deb" "$VGL_DIR.tmp"
  mv "$VGL_DIR.tmp" "$VGL_DIR"
}

# gpu_free_mib: free memory on the first NVIDIA GPU, or nothing if there is none.
gpu_free_mib() {
  command -v nvidia-smi >/dev/null && [ -f "$NVIDIA_EGL_VENDOR" ] || return 0
  nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -dc 0-9
}

# write_mcpfabric_config <config-dir> <port> <ui-control true|false>
write_mcpfabric_config() {
  local dir=$1 port=$2 ui=$3 cfg
  ensure_token
  mkdir -p "$dir"
  cfg="$dir/mcpfabric.config.json"
  python3 -I - "$cfg" "$port" "$(cat "$TOKEN_FILE")" "$ui" <<'PY'
import json, os, sys
path, port, token, ui = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4] == "true"
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data.update({
    "host": "127.0.0.1", "port": port, "requireAuth": True, "token": token,
    "callTimeoutMs": 8000, "enableWorldWrite": True, "enableCommands": True,
    "enablePlayerControl": True, "enableVision": True, "enableUiControl": ui,
    "enableSupervisedControl": False,
})
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump(data, f, indent=2)
PY
}

# pack_url: file:// URL of the pack (no dependency on the packwiz serve daemon).
pack_url() { echo "file://$PACK_TOML"; }

# refresh_pack: re-hash the pack so installers see the working tree.
refresh_pack() { (cd "$(dirname "$PACK_TOML")" && "$PACKWIZ" refresh >/dev/null); }

listening() { [ -n "${1:-}" ] && ss -H -ltn "sport = :$1" | grep -q .; }

session_up() { tmux has-session -t "=$1" 2>/dev/null; }
