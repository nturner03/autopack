#!/usr/bin/env bash
# Runs inside xvfb-run for launch.sh: starts the session recorder (detached,
# so it outlives the client's tmux session) unless the stamp is "-", then
# replaces itself with the game command.
#   xvfb-session.sh <stamp|-> <command...>
stamp=$1
shift
# stop.sh kills this Xvfb if xvfb-run could not (it dies with the tmux session).
echo "$DISPLAY" >"$(dirname -- "$0")/../../.state/client-display"
if [ "$stamp" != - ]; then
  setsid "$(dirname -- "$0")/record.sh" "$stamp" </dev/null >/dev/null 2>&1 &
fi
exec "$@"
