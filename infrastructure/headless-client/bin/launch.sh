#!/usr/bin/env bash
# Launch the headless client (real rendering on an Xvfb display, so
# screenshots work) in tmux session <SESSION_PREFIX>-client as offline player PexpBot.
# It renders on the NVIDIA GPU through VirtualGL, or on Mesa llvmpipe, and
# every session is recorded to recordings/<stamp>.mp4 (bin/record.sh).
#   launch.sh            open at the title screen
#   launch.sh --join     quick-play straight into the dev server (127.0.0.1:GAME_PORT)
#   PEXP_SKIP_UPDATE=1   skip the pack update
#   PEXP_CLIENT_XMX      client heap (default 4G)
#   PEXP_CLIENT_SIZE     game window WxH (default 1280x720; 320x240 to 3840x2160).
#                        The Xvfb screen is 320x180 larger; the window is centred
#                        on it (xclick.py reads the real position).
#   PEXP_CLIENT_GPU      auto (default): GPU when it has enough free memory,
#                        else llvmpipe; 1: GPU or fail; 0: llvmpipe
#   PEXP_CLIENT_RECORD   1 (default): record the session; 0: don't (only for
#                        FPS-sensitive tests: the capture costs a little CPU)
# Returns once the MCPFabric client bridge answers (or fails after ~10 min).
. "$(dirname -- "$0")/../../lib/common.sh"
[ -f "$CLIENT_DIR/.installed-version" ] || die "client not installed; run bin/install.sh"
session_up "$CLIENT_SESSION" && die "already running (tmux session $CLIENT_SESSION)"
read -r vdir loader lver mc <"$CLIENT_DIR/.installed-version"
want="$(pack_field loader) $(pack_field loader_version) $(pack_field minecraft)"
[ "$loader $lver $mc" = "$want" ] || die "client has '$loader $lver $mc' but pack wants '$want'; run bin/install.sh"
[ "${PEXP_SKIP_UPDATE:-0}" = 1 ] || "$CLIENT_ROOT/bin/update-pack.sh"

java=$(java_for_mc "$mc")
jar=$(ls "$CLIENT_HMC_DIR"/headlessmc-launcher-wrapper-*.jar | head -1)
# 1280x720 keeps GUIs (EMI, quest book) legible in screenshots without huge
# images; larger sizes are for art captures (/studio shot is at the window size).
size=${PEXP_CLIENT_SIZE:-1280x720}
[[ "$size" =~ ^([0-9]+)x([0-9]+)$ ]] || die "PEXP_CLIENT_SIZE must be WxH, got '$size'"
cw=${BASH_REMATCH[1]} ch=${BASH_REMATCH[2]}
{ [ "$cw" -ge 320 ] && [ "$cw" -le 3840 ] && [ "$ch" -ge 240 ] && [ "$ch" -le 2160 ]; } ||
  die "PEXP_CLIENT_SIZE $size out of range (320x240 to 3840x2160)"
gameargs="-Dhmc.gameargs=--width $cw --height $ch"
[ "${1:-}" = "--join" ] && gameargs="$gameargs --quickPlayMultiplayer 127.0.0.1:$GAME_PORT"
xmx=${PEXP_CLIENT_XMX:-4G}

# Renderer. Xvfb has no GPU: VirtualGL sends the game's GL to the NVIDIA card
# (EGL back end, NVIDIA's EGL vendor forced so Mesa is never picked) and
# copies frames into the Xvfb window. Fallback: LIBGL_ALWAYS_SOFTWARE makes
# Mesa use llvmpipe, which provides the GL 4.x core profile MC needs.
gpu=${PEXP_CLIENT_GPU:-auto}
renderer=llvmpipe
if [ "$gpu" != 0 ]; then
  free=$(gpu_free_mib)
  if [ -n "$free" ] && [ "$free" -ge "$CLIENT_GPU_MIN_FREE_MIB" ]; then
    ensure_virtualgl
    renderer=gpu
  elif [ "$gpu" = 1 ]; then
    die "PEXP_CLIENT_GPU=1 but the GPU is unavailable (free memory: ${free:-none} MiB)"
  else
    log "GPU unavailable (free memory: ${free:-none} MiB); rendering with llvmpipe"
  fi
fi
if [ "$renderer" = gpu ]; then
  render=(env __EGL_VENDOR_LIBRARY_FILENAMES="$NVIDIA_EGL_VENDOR"
    "$VGL_DIR/opt/VirtualGL/bin/vglrun" -d egl -ld "$VGL_DIR/usr/lib")
else
  render=(env LIBGL_ALWAYS_SOFTWARE=1)
fi

stamp=-
if [ "${PEXP_CLIENT_RECORD:-1}" != 0 ]; then
  mkdir -p "$RECORDINGS_DIR"
  freegib=$(df -BG --output=avail "$RECORDINGS_DIR" | tail -1 | tr -dc 0-9)
  if [ "$freegib" -lt "$RECORD_MIN_FREE_GIB" ]; then
    log "only ${freegib} GiB free; this session is NOT recorded"
  else
    stamp=$(date +%Y-%m-%d_%H%M%S)
  fi
fi

date +%s >"$STATE_DIR/client-started-at"
echo "$renderer" >"$STATE_DIR/client-renderer"
echo "${cw}x${ch}" >"$STATE_DIR/client-size"
tmux new-session -d -s "$CLIENT_SESSION" -c "$CLIENT_HMC_DIR" \
  xvfb-run -a -s "-screen 0 $((cw + 320))x$((ch + 180))x24" "$CLIENT_ROOT/bin/xvfb-session.sh" "$stamp" \
  "${render[@]}" "$java" "$gameargs" -jar "$jar" --command launch "$vdir" -offline --jvm "-Xmx$xmx"
log "renderer: $renderer; window: ${cw}x${ch}; recording: $([ "$stamp" = - ] && echo off || echo "recordings/$stamp.mp4")"
for ((i = 0; i < 600; i += 3)); do
  if listening "$CLIENT_BRIDGE_PORT"; then log "client bridge up on :$CLIENT_BRIDGE_PORT"; exit 0; fi
  session_up "$CLIENT_SESSION" || break
  sleep 3
done
echo "client did not come up; last output:" >&2
tmux capture-pane -p -t "$CLIENT_SESSION" 2>/dev/null | tail -30 >&2 || tail -30 "$CLIENT_DIR/logs/latest.log" >&2 || true
exit 1
