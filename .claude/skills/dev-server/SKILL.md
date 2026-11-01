---
name: dev-server
description: Operate the agents' test runtime - the dev server (infrastructure/dev-server), the headless client (infrastructure/headless-client, HeadlessMC under Xvfb as offline player PexpBot), and the packwiz HTTP host - install/reinstall for the pack's version and loader, start/stop/restart, deploy, reset or back up the world, read logs, and recover from failures. Use before touching any of them.
---

# Dev server, headless client, pack host

All three read the MC version and loader from `packwiz/pack.toml`
(currently **1.21.1 / NeoForge 21.1.265**, Java 21). Per-experiment
settings (ports, LAN address, tmux prefix) are in
`infrastructure/project.env`; shared logic is in `infrastructure/lib/common.sh`.
Until the ports are filled in, every script except `status.sh` refuses to
run (Phase 0 "Runtime setup" allocates them). Install once with each
`install.sh`, then start with `scripts/deploy.sh --restart [--client]`;
reinstall only after a NeoForge build change (`install.sh --reinstall`).

| Piece | Where | tmux | Port (inventory) |
|---|---|---|---|
| Dev server | `infrastructure/dev-server/server/` | `<prefix>-server` | game `*:GAME_PORT` |
| Server MCPFabric bridge | inside the server | - | `127.0.0.1:SERVER_BRIDGE_PORT` |
| Headless client | `infrastructure/headless-client/instance/` (game dir), `hmc/` (HeadlessMC, MC/libs/assets cache) | `<prefix>-client` | bridge `127.0.0.1:CLIENT_BRIDGE_PORT` |
| Pack host | `scripts/serve.sh` (`packwiz serve`) | `<prefix>-packhost` | `*:SERVE_PORT` |

`<prefix>` is `SESSION_PREFIX` (default `pexp-<repo directory>`); `status.sh`
prints the real session names and ports.

Ports are set in `infrastructure/project.env` (AGENTS.md → Ports). Never
change a port, bind address or add a listener without updating that file
and AGENTS.md (and the owner's port inventory, if one is configured) in the
same task, and never use another experiment's ports.

The token for both bridges is `infrastructure/.state/mcpfabric-token`
(mode 600, gitignored, pre-seeded into both configs). Never print it.

## Status first

`infrastructure/dev-server/bin/status.sh` - install, tmux, listeners, Done
line, ERROR count, installed pack == working tree, client, pack host.

## Dev server (`infrastructure/dev-server/bin/`)

| Script | Does |
|---|---|
| `install.sh [--reinstall] [--seed N]` | install loader + pack (+ MCPFabric outside packwiz, bridge config, ops PexpBot, server.properties from `templates/`). `--reinstall` moves the world to `backups/` and wipes `server/` (use after MC/loader change). |
| `update-pack.sh` | `packwiz refresh` + packwiz-installer `-s server` from `file://` (no pack host needed); re-adds MCPFabric; rebuilds (when its sources changed) and installs the dev-only tool mods from `infrastructure/dev-mods/` |
| `start.sh` | update pack (skip with `PEXP_SKIP_UPDATE=1`), start in tmux; refuses if the install doesn't match pack.toml |
| `wait-ready.sh [timeout]` | block until `Done (`; on failure prints log tail + crash report path; exit 1 crash, 2 timeout |
| `stop.sh` | `stop` via console, waits for the port to close |
| `restart.sh` | stop + start + wait-ready |
| `console.sh "<cmd>"` | raw console command (no output; prefer `scripts/mcf.py run_command`) |
| `backup.sh [label]`, `restore.sh <archive>` | world tar.gz in `backups/` (live backups pause saving) |
| `reset-world.sh [--seed N]` | back up, delete world, set seed; logs to `docs/testing/world-log.md` |
| `world-log.sh "<msg>"` | append to the world log |

`scripts/deploy.sh --restart|--reload|--quests [--client] [--no-checks]`
wraps the usual sequence (refresh, `check_pack.py`, update, restart or
reload, health summary) and ends with the regression checks
(`scripts/checks.py run`, `tests/README.md`): it exits non-zero when one
FAILs or can't be evaluated. Use it rather than hand-running the steps.
`--no-checks` is for scratch work only (a throwaway pack can bring its own
set with `PEXP_CHECKS_DIR`). After a `/reload` by hand (not through
`deploy.sh`), `log_clean` still counts errors logged before that reload.

Server facts: `online-mode=false` (LAN-only test server; PexpBot is
offline), `spawn-protection=0`, command blocks on, `allow-flight=true`,
`difficulty=normal`. Heap 2-6 GB (`templates/user_jvm_args.txt`; raise if
GC pressure shows). Java 21 is picked from the MC version; the host's PATH
`java` is 1.8, never use it.

**The world is disposable.** Agents may restart, reset and restore it
without asking. Before a restart/reset: `scripts/mcf.py list_players`; if a
non-bot player is online, the owner is playtesting - don't interrupt:
queue the change and note it in `docs/status.md`. Worldgen changes only
apply to new chunks: reset or explore far away before judging them.

## Headless client (`infrastructure/headless-client/bin/`)

| Script | Does |
|---|---|
| `install.sh [--reinstall]` | HeadlessMC (pinned, checksum-verified) installs MC + loader; pack `-s client`; MCPFabric + bridge config (UI control on); `servers.dat` with the dev server; `options.txt` from `templates/` |
| `update-pack.sh` | client pack update (run while stopped); rebuilds and re-installs the dev-only tool mods (`pexp_devtools`) like the server's |
| `launch.sh [--join]` | Xvfb display, window 1280x720 (`PEXP_CLIENT_SIZE=WxH` for another size, e.g. 1920x1080 for art captures), offline player `PexpBot`, rendered on the NVIDIA GPU through VirtualGL (llvmpipe fallback); records the session; `--join` quick-plays into the dev server. Returns when the client bridge answers. |
| `stop.sh` | end the recording, then the game, its tmux session and its Xvfb |

- The client costs ~1.5 CPU cores and ~2-4 GB while running on the GPU
  (3-4 cores on llvmpipe). Stop it when you're done with GUI checks.
- **Renderer.** `PEXP_CLIENT_GPU=auto` (default) renders on the host's
  NVIDIA GPU through VirtualGL when it has 1.5 GB of free memory (other
  services share the card), else on Mesa llvmpipe; `=1` fails instead of falling
  back, `=0` forces llvmpipe. `launch.sh` prints the renderer and writes it
  to `infrastructure/.state/client-renderer`; the game log's
  `OpenGL Renderer:` line confirms it. If the client won't start on the
  GPU, relaunch with `PEXP_CLIENT_GPU=0` and report it. On the GPU the game
  holds its 30 fps cap; on llvmpipe the lows drop (p99.5 about 5 fps).
  Screenshots from the two renderers differ slightly: don't compare
  captures across them pixel by pixel.
- **Session recording.** Every launch records the game window (by X window
  id, 30 fps, NVENC; libx264 if NVENC is busy) to
  `infrastructure/headless-client/recordings/<stamp>.mp4`; `launch.sh`
  prints the name. The owner watches these to audit agent sessions, so
  keep it on. Set `PEXP_CLIENT_RECORD=0` only for a test that measures
  FPS. `stop.sh` ends the capture first; the mp4 is saved in the
  background in a few seconds, and nobody waits for it. A crash or killed
  client still gets its mp4 (the recorder stops when the game window
  goes). Sessions under 5 GB of free disk aren't recorded (logged). A
  stuck capture leaves `recordings/.work/<stamp>.mkv` and `.log`; report
  it instead of deleting it. The recorder needs no port.
- Start the server first; `launch.sh --join` connects at boot. After a
  server restart the client is disconnected: `join_world` (no args rejoins
  the last server) or relaunch.
- Client-side MCPFabric tools (mc-client): `screenshot`, `get_screen`,
  `get_ui`, `click_widget`, `set_text_field`, `close_screen`, `join_world`,
  `list_worlds`, movement/look/use/attack, inventory, `describe_scene`,
  `navigate_to`, `send_chat` (a `/command` from the player). World and admin
  commands (`run_command`, `give_item`, `teleport_player`...) go through the
  **server** bridge (mc-server), which has no client tools.
- Give PexpBot creative/op powers through mc-server
  (`set_gamemode`, `give_item`); PexpBot is opped by install.sh.
- HeadlessMC notes: offline accounts only render when `hmc.check.xvfb=true`
  and Xvfb is detected (otherwise it silently stubs LWJGL and screenshots
  fail); config is `hmc/HeadlessMC/config.properties`, written by
  install.sh. If HeadlessMC cannot install/launch a future loader version,
  fall back to portablemc (`pip install --user portablemc`) under the same
  Xvfb wrapper, and document it here.

## Pack host

`scripts/serve.sh` / `scripts/serve.sh --stop`. Only needed when the owner
plays (their Prism client installs from `http://LAN_HOST:SERVE_PORT/pack.toml`;
`serve.sh` prints the URL).
It serves the **working tree** of whatever is checked out: don't leave
half-finished edits or another branch checked out while a human test is
pending. Start it when you queue a human test and say so in the request.

## Logs and failures

- Server: `server/logs/latest.log` (check its mtime against
  `infrastructure/.state/server-started-at`; an old file says nothing about
  this run), `server/logs/kubejs/{startup,server}.log`, `server/crash-reports/`,
  `server/packwiz-update.log`, `server/installer.log`.
- Client: `instance/logs/latest.log`, `instance/crash-reports/`,
  `tmux capture-pane -p -t <prefix>-client`.
- For anything beyond a glance, spawn `pack-log-triage` (haiku).
- Common failures: a client-only mod on the server (`side` wrong: crash
  naming a client class) → set `side = "client"`; missing dependency (mod
  loading error lists it); mod/loader version mismatch; KubeJS script error
  (server starts, script log shows it); port in use (another process - find
  it with `ss -ltnp`, don't kill unknown processes).
