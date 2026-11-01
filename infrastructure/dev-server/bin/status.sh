#!/usr/bin/env bash
# One-screen health report for the dev server, headless client and pack host.
# Exit 0 always; read the lines.
PEXP_PORTS_OPTIONAL=1
. "$(dirname -- "$0")/../../lib/common.sh"
ports_configured || echo "ports:          NOT SET in infrastructure/project.env (allocate them first; README.md)"
up() { if listening "${1:-}"; then echo "listening"; else echo "closed"; fi; }
if [ -f "$PACK_TOML" ]; then
  echo "pack.toml:      $PACK_TOML ($(pack_field name 2>/dev/null) $(pack_field version 2>/dev/null); $(pack_field loader 2>/dev/null) $(pack_field loader_version 2>/dev/null), MC $(pack_field minecraft 2>/dev/null))"
else
  echo "pack.toml:      none at $PACK_TOML (run 'packwiz init' in packwiz/)"
fi
if [ -f "$SERVER_DIR/.installed-loader" ]; then
  echo "server install: $(cat "$SERVER_DIR/.installed-loader")"
else
  echo "server install: none (bin/install.sh)"
fi
echo "server tmux:    $(session_up "$SERVER_SESSION" && echo up || echo down) ($SERVER_SESSION); game :$GAME_PORT $(up "$GAME_PORT"); bridge :$SERVER_BRIDGE_PORT $(up "$SERVER_BRIDGE_PORT")"
logf="$SERVER_DIR/logs/latest.log"
if [ -f "$logf" ]; then
  started=$(cat "$STATE_DIR/server-started-at" 2>/dev/null || echo 0)
  fresh=$([ "$(stat -c %Y "$logf")" -ge "$started" ] && echo current || echo STALE)
  done_line=$(grep -m1 -o 'Done ([0-9.]*s)' "$logf" || echo "no Done yet")
  echo "server log:     $fresh run; $done_line; $(grep -c -E '/(ERROR|FATAL)\]' "$logf") ERROR/FATAL lines"
fi
if [ -f "$SERVER_DIR/packwiz.json" ] && [ -f "$PACK_TOML" ]; then
  python3 -I - "$SERVER_DIR/packwiz.json" "$PACK_TOML" <<'PY'
import hashlib, json, sys
inst = json.load(open(sys.argv[1]))["packFileHash"]["value"]
cur = hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()
print("server pack:    " + ("== working tree pack.toml" if inst == cur else "!= working tree (run bin/update-pack.sh / restart)"))
PY
fi
echo "client tmux:    $(session_up "$CLIENT_SESSION" && echo up || echo down) ($CLIENT_SESSION); bridge :$CLIENT_BRIDGE_PORT $(up "$CLIENT_BRIDGE_PORT")"
echo "pack host:      $(session_up "$SERVE_SESSION" && echo up || echo down) ($SERVE_SESSION); :$SERVE_PORT $(up "$SERVE_PORT")"
