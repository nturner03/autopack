#!/usr/bin/env bash
# Record the headless client's game window for the owner's audit of agent
# sessions. Started by xvfb-session.sh inside xvfb-run (DISPLAY and XAUTHORITY
# come from there), detached with setsid so it outlives the client's tmux
# session. Never run it by hand; PEXP_CLIENT_RECORD=0 on launch.sh turns it off.
#   record.sh <stamp>
# Waits for the game window, captures it at 30 fps (NVENC; libx264 when NVENC
# is unavailable) into recordings/.work/<stamp>.mkv. The capture ends on
# SIGTERM (stop.sh) or when the game window or Xvfb goes away (crash, kill);
# the mkv is then remuxed to recordings/<stamp>.mp4 (seconds, no re-encode).
# Log: recordings/.work/<stamp>.log, kept only if something went wrong.
. "$(dirname -- "$0")/../../lib/common.sh"
stamp=$1
work="$RECORDINGS_DIR/.work"
mkdir -p "$work"
exec >>"$work/$stamp.log" 2>&1
echo $$ >"$RECORDER_STATE"
fpid=
stop() { stopping=1; [ -z "$fpid" ] || kill -TERM "$fpid" 2>/dev/null || true; }
stopping=0
trap stop TERM INT HUP
finish() { rm -f "$RECORDER_STATE"; }
trap finish EXIT

# The game window (NeoForge's early loading window is the same window). It is
# captured by id, not by screen region: it is centred only after it appears.
win=
for ((i = 0; i < 900 && stopping == 0; i++)); do
  xdpyinfo >/dev/null 2>&1 || { log "display gone before the game window appeared"; exit 0; }
  win=$(xwininfo -root -tree 2>/dev/null | grep -m1 -E '"Minecraft[^"]*"' | awk '{print $1}' || true)
  [ -n "$win" ] && break
  sleep 1
done
[ -n "$win" ] || { log "no game window; nothing recorded"; exit 0; }

enc=(-c:v h264_nvenc -preset p4 -tune hq -rc vbr -cq 28 -b:v 0 -maxrate 6M -bufsize 12M)
if ! ffmpeg -nostdin -loglevel error -f lavfi -i color=black:s=256x144:r=30 -frames:v 5 \
  -c:v h264_nvenc -f null - 2>/dev/null; then
  log "NVENC unavailable; recording with libx264"
  enc=(-c:v libx264 -preset veryfast -crf 26)
fi
log "recording window $win on $DISPLAY (${enc[1]})"
nice -n 5 ffmpeg -nostdin -hide_banner -loglevel warning \
  -f x11grab -framerate 30 -window_id "$((win))" -draw_mouse 1 -i "$DISPLAY" \
  "${enc[@]}" -g 60 -pix_fmt yuv420p "$work/$stamp.mkv" &
fpid=$!
# Watchdog: end the capture when the game window is gone, whatever happened
# to the client, so a leftover Xvfb is never recorded.
while kill -0 "$fpid" 2>/dev/null; do
  sleep 5 &
  wait $! || true
  if [ "$stopping" = 0 ] && ! xwininfo -root -tree 2>/dev/null | grep -q -E '"Minecraft[^"]*"'; then
    log "game window gone; ending the capture"
    stop
  fi
done
wait "$fpid" 2>/dev/null || true
# stop.sh waits for this file to go before it ends the game.
rm -f "$RECORDER_STATE"

if [ ! -s "$work/$stamp.mkv" ] || [ "$(stat -c %s "$work/$stamp.mkv")" -lt 4096 ]; then
  log "empty capture; discarded"
  rm -f "$work/$stamp.mkv"
  exit 0
fi
if nice -n 10 ffmpeg -nostdin -loglevel error -i "$work/$stamp.mkv" -c copy -movflags +faststart \
  -f mp4 "$work/$stamp.mp4.part" && mv "$work/$stamp.mp4.part" "$RECORDINGS_DIR/$stamp.mp4"; then
  rm -f "$work/$stamp.mkv" "$work/$stamp.log"
else
  rm -f "$work/$stamp.mp4.part"
  log "remux failed; the capture is kept as $work/$stamp.mkv"
fi
