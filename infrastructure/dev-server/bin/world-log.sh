#!/usr/bin/env bash
# Append a dated line to docs/testing/world-log.md (world resets, seeds, reinstalls).
#   world-log.sh "<what happened>"
. "$(dirname -- "$0")/../../lib/common.sh"
[ $# -ge 1 ] || die "usage: world-log.sh <message>"
f="$REPO_DIR/docs/testing/world-log.md"
[ -f "$f" ] || printf '# Dev-server world log\n\nAppend-only. Written by the dev-server scripts; add context by hand when useful.\n\n' >"$f"
rev=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo none)
echo "- $(date '+%Y-%m-%d %H:%M') (git $rev): $*" >>"$f"
