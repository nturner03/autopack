#!/usr/bin/env bash
# stop.sh, start.sh (pack update unless PEXP_SKIP_UPDATE=1), wait-ready.sh.
. "$(dirname -- "$0")/../../lib/common.sh"
"$SERVER_ROOT/bin/stop.sh"
"$SERVER_ROOT/bin/start.sh"
exec "$SERVER_ROOT/bin/wait-ready.sh" "${1:-900}"
