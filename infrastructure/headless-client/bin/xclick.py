#!/usr/bin/env python3
"""Real mouse input for the headless client via XTest (stdlib only).

The MCPFabric tools cannot click inside FTB Quests (and other screens that
take real GLFW mouse events). The headless client runs on an Xvfb display;
this sends X pointer motion and button events to it, so the game sees a
real mouse.

Usage (run with `python3 -I`):
    xclick.py move  X Y            move the pointer to window-relative X,Y
    xclick.py click X Y [--button 1|3]   move, wait, press and release
    xclick.py pos                  print the display, window offset and size
    xclick.py key KEYSYM [HOLD]    press and hold an X keysym (e.g. Escape, space, u,
                                   F9) for HOLD seconds (default 0.15); the pointer is
                                   first parked mid-window so the game has focus

Coordinates are relative to the game window (as in a screenshot at the
window size: 1280x720 unless launch.sh got PEXP_CLIENT_SIZE). The window's
position on the Xvfb screen is read with xwininfo (centred: 160,90 at the
default size) and added here. Notes: the first click right after a pointer move can be swallowed, so
the script moves, waits ~1 s, then clicks; repeat the click if nothing
changed. DISPLAY and XAUTHORITY are read from the client java process
(/proc/<pid>/environ), so no setup is needed after a client relaunch.
Never prints the MCPFabric token or any environment values besides DISPLAY.
"""
import ctypes
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# This experiment's client instance: only its game process is targeted, so a
# second experiment's client on the same host is never clicked.
GAME_DIR = str(Path(__file__).resolve().parents[1] / "instance")
STATE_DIR = Path(__file__).resolve().parents[2] / ".state"
GEOM = None  # (x, y, w, h) of the game window, set by main()


def client_env():
    """DISPLAY/XAUTHORITY of this experiment's running client (the game JVM)."""
    out = subprocess.run(["pgrep", "-f", "--", f"--gameDir {GAME_DIR}"],
                         capture_output=True, text=True).stdout.split()
    for pid in reversed(out):
        try:
            raw = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
        except OSError:
            continue
        env = dict(e.decode(errors="replace").split("=", 1) for e in raw if b"=" in e)
        if env.get("DISPLAY") and env.get("XAUTHORITY"):
            return env["DISPLAY"], env["XAUTHORITY"]
    return None, None


def window_geometry():
    """(x, y, w, h) of the game window on the screen, from xwininfo.

    Falls back to a window centred on a screen 320x180 larger than the size
    launch.sh recorded (its layout), else the default 1280x720."""
    try:
        out = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for line in out.splitlines():
        if '"Minecraft' in line:
            m = re.search(r"(\d+)x(\d+)[+-]-?\d+[+-]-?\d+\s+\+(-?\d+)\+(-?\d+)", line)
            if m:
                w, h, x, y = map(int, m.groups())
                return x, y, w, h
    w, h = 1280, 720
    try:
        sw, sh = (STATE_DIR / "client-size").read_text().strip().split("x")
        w, h = int(sw), int(sh)
    except (OSError, ValueError):
        pass
    return 160, 90, w, h


def open_display():
    disp, auth = client_env()
    if not disp:
        sys.exit("xclick: no running client with DISPLAY/XAUTHORITY found")
    os.environ["DISPLAY"], os.environ["XAUTHORITY"] = disp, auth
    x11 = ctypes.CDLL("libX11.so.6")
    xtst = ctypes.CDLL("libXtst.so.6")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    d = x11.XOpenDisplay(None)
    if not d:
        sys.exit("xclick: cannot open display " + disp)
    return x11, xtst, ctypes.c_void_p(d), disp


def move(x11, xtst, d, x, y):
    xtst.XTestFakeMotionEvent(d, -1, x + GEOM[0], y + GEOM[1], 0)
    x11.XFlush(d)


def press_key(x11, xtst, d, name, hold):
    move(x11, xtst, d, GEOM[2] // 2, GEOM[3] // 2)
    time.sleep(0.5)
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XKeysymToKeycode.restype = ctypes.c_ubyte
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ks = x11.XStringToKeysym(name.encode())
    kc = x11.XKeysymToKeycode(d, ks) if ks else 0
    if not kc:
        print(f"xclick: unknown keysym {name}")
        return 1
    xtst.XTestFakeKeyEvent(d, kc, 1, 0)
    x11.XFlush(d)
    time.sleep(hold)
    xtst.XTestFakeKeyEvent(d, kc, 0, 0)
    x11.XFlush(d)
    print(f"key {name} (keycode {kc}) held {hold}s")
    return 0


def main(argv):
    if not argv or argv[0] not in ("move", "click", "pos", "key"):
        print(__doc__)
        return 2
    global GEOM
    x11, xtst, d, disp = open_display()
    GEOM = window_geometry()
    if argv[0] == "pos":
        print(f"display {disp}, window offset {GEOM[:2]}, size {GEOM[2]}x{GEOM[3]}")
        return 0
    if argv[0] == "key":
        return press_key(x11, xtst, d, argv[1], float(argv[2]) if len(argv) > 2 else 0.15)
    x, y = int(argv[1]), int(argv[2])
    button = 1
    if "--button" in argv:
        button = int(argv[argv.index("--button") + 1])
    move(x11, xtst, d, x, y)
    if argv[0] == "move":
        print("moved")
        return 0
    time.sleep(1.0)
    move(x11, xtst, d, x, y)
    time.sleep(0.2)
    xtst.XTestFakeButtonEvent(d, button, 1, 0)
    x11.XFlush(d)
    time.sleep(0.1)
    xtst.XTestFakeButtonEvent(d, button, 0, 0)
    x11.XFlush(d)
    print(f"clicked button {button} at window ({x},{y})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
