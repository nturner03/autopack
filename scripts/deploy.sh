#!/usr/bin/env bash
# Deploy the packwiz/ working tree to the dev server (and optionally the
# headless client) and report health.
#
#   deploy.sh --restart          stop, update, start, wait for Done (mods, configs, startup scripts, worldgen)
#   deploy.sh --reload           update files, then /reload (KubeJS server scripts, datapacks, recipes, tags, loot)
#   deploy.sh --quests           update files, then reload FTB Quests (quest SNBT / lang only)
#   add --client                 also update + (re)launch the headless client and join
#   add --no-checks              skip the regression checks (tests/checks/)
#
# A stopped server is always started (--restart behaviour). Static checks run
# first and abort the deploy on errors. Ends with a health summary and the
# regression checks (scripts/checks.py run); exits non-zero when a check fails
# or cannot be evaluated. Use the pack-log-triage agent for anything non-trivial.
. "$(dirname -- "$0")/../infrastructure/lib/common.sh"
mode="" client=0 checks=1
for a in "$@"; do
  case $a in
    --restart|--reload|--quests) mode=${a#--} ;;
    --client) client=1 ;;
    --no-checks) checks=0 ;;
    *) sed -n '2,14p' "$0" >&2; exit 2 ;;
  esac
done
[ -n "$mode" ] || { sed -n '2,14p' "$0" >&2; exit 2; }
SRV="$INFRA_DIR/dev-server/bin" CLI="$INFRA_DIR/headless-client/bin"

refresh_pack
python3 -I "$REPO_DIR/scripts/check_pack.py" | tail -n 15 || die "check_pack.py found errors; not deploying"
[ -d "$SERVER_DIR" ] || "$SRV/install.sh"
session_up "$SERVER_SESSION" || mode=restart
[ "$client" = 1 ] && "$CLI/stop.sh" >/dev/null

started=$(date +%s)
mcf() { python3 -I "$REPO_DIR/scripts/mcf.py" "$@"; }
case $mode in
  restart)
    "$SRV/stop.sh"
    "$SRV/start.sh"
    "$SRV/wait-ready.sh" || die "server failed to start (see above)"
    ;;
  reload)
    "$SRV/update-pack.sh"
    date +%s >"$STATE_DIR/server-reloaded-at"   # checks.py log_clean: older post-startup lines are stale
    mcf run_command '{"command":"reload"}' >/dev/null || die "reload via bridge failed"
    sleep 3
    ;;
  quests)
    "$SRV/update-pack.sh"
    mcf run_command '{"command":"ftbquests reload quests"}' | grep -E '"(success|output)"' || true
    ;;
esac

if [ "$client" = 1 ]; then
  [ -f "$CLIENT_DIR/.installed-version" ] || "$CLI/install.sh"
  "$CLI/launch.sh" --join || die "headless client failed to launch"
fi

echo "--- health ---"
"$SRV/status.sh"
logf="$SERVER_DIR/logs/latest.log"
kjs="$SERVER_DIR/logs/kubejs/server.log"
if [ -f "$kjs" ] && [ "$(stat -c %Y "$kjs")" -ge "$started" ]; then
  echo "kubejs server.log: $(grep -c -E '\[(ERROR|WARN)\]|Error' "$kjs") error/warn lines"
fi
grep -m 3 -E 'Loaded [0-9]+ (chapters|quests)' "$logf" 2>/dev/null || true

[ "$checks" = 1 ] || { echo "--- checks: skipped (--no-checks) ---"; exit 0; }
echo "--- checks ---"
rc=0
python3 -I "$REPO_DIR/scripts/checks.py" run --quiet || rc=$?
case $rc in
  0) ;;
  3) die "regression checks incomplete (skipped checks above; docs/local/checks-last.json)" ;;
  *) die "regression checks failed (exit $rc; docs/local/checks-last.json)" ;;
esac
