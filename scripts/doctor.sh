#!/usr/bin/env bash
# Check that this host has everything the experiment's tooling needs, and that
# infrastructure/project.env is filled in with ports nobody else uses.
# Read-only: installs nothing, changes nothing.
#   doctor.sh          exit 0 = no FAIL lines (WARN lines are worth reading)
set -uo pipefail
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Optional: a host port inventory file to check the ports against. Unset = skip.
INVENTORY=${PEXP_PORT_INVENTORY:-}
MCF_DIR=${PEXP_MCPFABRIC_DIR:-}
JAVA21=${PEXP_JAVA:-/usr/lib/jvm/java-21-openjdk-amd64/bin/java}
fails=0
ok() { echo "ok    $*"; }
warn() { echo "WARN  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

echo "== toolchain"
[ -x "$JAVA21" ] && ok "Java 21 ($JAVA21)" || fail "Java 21 missing at $JAVA21 (game and custom-mod builds; set PEXP_JAVA)"
pw=${PEXP_PACKWIZ:-$HOME/go/bin/packwiz}
[ -x "$pw" ] && ok "packwiz ($pw)" || fail "packwiz missing at $pw (go install github.com/packwiz/packwiz@latest)"
if python3 -c 'import sys, tomllib; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then ok "python3 >= 3.11"; else fail "python3 >= 3.11 (tomllib) needed"; fi
python3 -c 'import PIL' 2>/dev/null && ok "Pillow" || fail "Pillow missing (texture.py, quests.py render): python3 -m pip install --user pillow"
for c in tmux curl unzip ss git xvfb-run dpkg-deb sha256sum; do
  have "$c" && ok "$c" || fail "$c missing"
done
for c in ffmpeg xwininfo xdpyinfo; do
  have "$c" && ok "$c" || warn "$c missing: headless-client session recording is off"
done
ldconfig -p 2>/dev/null | grep -q libXtst.so.6 && ok "libXtst (xclick.py)" || warn "libXtst.so.6 missing: xclick.py can't click mod GUIs"
if have nvidia-smi && [ -f /usr/share/glvnd/egl_vendor.d/10_nvidia.json ]; then
  ok "NVIDIA GPU + EGL (client renders through VirtualGL)"
else
  warn "no NVIDIA GPU/EGL: the headless client renders with Mesa llvmpipe (slower)"
fi

echo "== MCPFabric and Claude Code"
node=$(command -v node || ls -1d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null | sort -V | tail -1)
[ -n "$node" ] && ok "node ($node)" || fail "node missing (MCP servers in .mcp.json)"
if [ -z "$MCF_DIR" ]; then
  fail "PEXP_MCPFABRIC_DIR not set (path to your MCPFabric checkout; install per https://github.com/denfry/mcpfabric)"
else
  [ -f "$MCF_DIR/mcp-server/dist/index.js" ] && ok "MCPFabric MCP server ($MCF_DIR)" || fail "$MCF_DIR/mcp-server/dist/index.js missing (.mcp.json; build MCPFabric's mcp-server per https://github.com/denfry/mcpfabric)"
  [ -f "$MCF_DIR/mcp-server/src/tools.ts" ] && ok "MCPFabric tool table (scripts/mcf.py)" || fail "$MCF_DIR/mcp-server/src/tools.ts missing (scripts/mcf.py)"
fi
for f in hooks/orch_agent_budget.py hooks/orch_log_spawn.py hooks/orch_check_return_block.py scripts/md_section.py scripts/returns.py; do
  [ -e "$REPO/.claude/$f" ] && ok ".claude/$f" || fail ".claude/$f missing (.claude/settings.json hooks and skills use it)"
done

echo "== repo"
git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 && ok "git repo" || warn "not a git repo yet: git init && git add -A && git commit"
grep -q '^> <Paste the request' "$REPO/docs/charter.md" 2>/dev/null && warn "docs/charter.md still has the template request placeholder" || ok "charter filled in"
python3 -I "$REPO/scripts/check_pack.py" >/dev/null 2>&1 && ok "check_pack.py" || fail "check_pack.py reports errors"

echo "== ports (infrastructure/project.env)"
prefix=$(cd "$REPO" && PEXP_PORTS_OPTIONAL=1 bash -c '. infrastructure/lib/common.sh; echo "$SESSION_PREFIX"')
env_get() { sed -n "s/^$1=//p" "$REPO/infrastructure/project.env" | tail -1; }
for key in GAME_PORT SERVE_PORT SERVER_BRIDGE_PORT CLIENT_BRIDGE_PORT; do
  port=$(env_get "$key")
  if [ -z "$port" ]; then
    fail "$key not set (pick a free port and set it in infrastructure/project.env)"
    continue
  fi
  owner=""
  # Sibling experiments (directories next to this one) must not share ports.
  for other in "$REPO"/../*/infrastructure/project.env; do
    other=$(realpath -m "$other")
    [ "$other" = "$REPO/infrastructure/project.env" ] && continue
    [ -f "$other" ] && grep -q "^[A-Z_]*=$port\$" "$other" && owner="$owner $(basename "$(dirname "$(dirname "$other")")")"
  done
  [ -n "$owner" ] && fail "$key=$port is also used by:$owner"
  if [ -z "$INVENTORY" ]; then
    :
  elif [ -f "$INVENTORY" ]; then
    grep -q "\b$port\b" "$INVENTORY" && ok "$key=$port is in the port inventory (check the row names this repo)" ||
      fail "$key=$port is not in the port inventory ($INVENTORY)"
  else
    warn "port inventory not found at $INVENTORY"
  fi
  if ss -H -ltn "sport = :$port" | grep -q .; then
    if tmux has-session -t "=$prefix-server" 2>/dev/null || tmux has-session -t "=$prefix-client" 2>/dev/null ||
      tmux has-session -t "=$prefix-packhost" 2>/dev/null; then
      ok "$key=$port is listening (this experiment's runtime is up)"
    else
      warn "$key=$port is already listening and this experiment's runtime is down: something else holds it (ss -ltnp)"
    fi
  fi
done

echo
[ "$fails" = 0 ] && echo "doctor: no failures" || echo "doctor: $fails failure(s)"
[ "$fails" = 0 ]
