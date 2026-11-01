# Studio: the capture mod for UI art

**Status:** lite scope **built and verified** (2026-10-31, `pexp_devtools`
0.2.0): `ping`, `clean`, `shot`, `panorama`, the client half of the
dev-only `pexp_devtools` mod (`infrastructure/dev-mods/pexp_devtools/`).
How to use it: [Usage](#usage) below.

**Scope (owner, 2026-10-31):** build `ping`, `clean`, `shot` and `panorama`
only. `shot` captures at the window size; the client's window size is
set at launch (`PEXP_CLIENT_SIZE=WxH`). The cut-out commands (`entity`, `block`, `item`,
`area`) are **future work**: the rest of this spec keeps them as the design
to build if UI art proves worth it. Until then, a subject on a transparent
background can be approximated by shooting it against a solid-colour
backdrop (a wall of one concrete colour, `/time set`, no fog) and keying
that colour out when composing.

Studio is the **client-only part** of the dev-only `pexp_devtools` mod:
agents use it in the headless client to take art-quality captures. It is
test infrastructure like MCPFabric, never pack content and never in
`packwiz/`. The dev server runs the same jar for `/pexp dump`, but loads no
studio code.

## Why

MCPFabric's `screenshot` grabs the window with the HUD, hand and
crosshair. Art needs clean shots at a chosen size, the six faces of a title
panorama, and subjects (a boss, a machine, an item) on a transparent
background for composition. Vanilla 1.21.1 already has most of the hard
parts: `Minecraft.grabPanoramixScreenshot(File, int, int)` is public, and
`net.minecraft.client.Screenshot` writes large images in tiles (checked
with `javap` on the 1.21.1 client jar, 2026-10-30). In the headless client
`grabPanoramixScreenshot` gives broken faces, so studio drives its own
panorama through real frames (see "How it works").

## Build and install

- Part of `pexp_devtools` (`infrastructure/dev-mods/pexp_devtools/`): the
  `/studio` commands are registered from the client dist only
  (`RegisterClientCommandsEvent` in a `Dist.CLIENT` class), so the same jar
  stays safe on the dev server. `displayTest = "IGNORE_ALL_VERSION"`.
- Build: `scripts/build-custom-mod.sh pexp_devtools --dev`, or let the
  update-pack scripts rebuild it when its sources change. The jar goes to
  `infrastructure/cache/dev-mods/` and both installs' `mods/`.
- Restart the client to load a new build (`scripts/deploy.sh --restart --client`
  or the dev-server skill's client commands).
- Document the commands in the mod's README.

## Commands

Client commands (NeoForge `RegisterClientCommandsEvent`), root `/studio`.
Agents send them with MCPFabric:
`python3 -I scripts/mcf.py --client send_chat '{"message":"/studio ping"}'`,
then read the result line with `get_recent_chat` (verified: MCPFabric's
`send_chat` goes through `ClientPacketListener.sendCommand`, which NeoForge
routes to client commands first, so no file-polling fallback was needed).

Every command answers with one chat line starting `studio:`, either
`studio: wrote <path> (<w>x<h>) in <ms> ms` or `studio: error <reason>`.
The line is a system chat message, so `get_recent_chat` returns it and the
client log has it as `[CHAT] studio: ...`. `<path>` is relative to the game
directory. Output goes to `<gamedir>/studio/`
(`infrastructure/headless-client/instance/studio/`, gitignored). `<name>`
is `[a-z0-9_-]{1,64}`; an existing file is overwritten. One capture runs at
a time (`studio: error busy ...` otherwise). A name with characters outside
brigadier's word set (`!`, `/`, spaces) fails as a red vanilla syntax error
with no `studio:` line.

Built (lite scope):

| Command | Does |
|---|---|
| `/studio ping` | `studio: ok <version> <W>x<H>` (window size; ` clean` appended while clean mode is on) |
| `/studio clean on\|off` | hides or restores the HUD, hand, crosshair, chat and debug overlay (`options.hideGui`) for later MCPFabric screenshots; refused while a capture runs |
| `/studio shot <name>` | hides the GUI for a few frames and writes the frame at the window size, with no HUD, hand or crosshair, to `studio/<name>.png`. For another size, relaunch the client with `PEXP_CLIENT_SIZE` |
| `/studio panorama <name> <size>` | six square faces from the camera position (`size` 16-2048) into `studio/<name>/panorama_0.png` ... `panorama_5.png`: vanilla face order and orientation (0 = facing, 1 = +90 yaw, 2 = behind, 3 = -90, 4 = up, 5 = down; 90 degree FOV), ready to copy to the title-screen path |

Future work (not built):

| Command | Does |
|---|---|
| `/studio shot <name> <width> <height> [fov]` | offscreen render at any size up to 4096, independent of the window |
| `/studio entity <name> <size> [yaw] [pitch]` | the entity under the crosshair (else the nearest non-player within 16 blocks), alone on a transparent background, framed to fit `size`x`size`, in its current pose; `yaw`/`pitch` turn the model |
| `/studio block <name> <size> [<x> <y> <z> \| <block_id>]` | one block state (the block under the crosshair, at a position with its block entity, or by id) in a 3/4 isometric view on a transparent background |
| `/studio item <name> <size> <item_id>` | the item as the GUI renders it (3D block models included), scaled to `size`, transparent background |
| `/studio area <name> <size> <x1> <y1> <z1> <x2> <y2> <z2> [yaw] [pitch]` | optional stretch goal: an isometric render of a box of blocks (a machine setup, a structure room) on a transparent background |

Renders happen on the render thread at a frame boundary (queue the job from
the command, run it in a render-frame event), then restore every setting
they changed (GUI hidden, FOV, framebuffer size).

## How it works (built)

`StudioClient` (`pexp_devtools/src/main/java/.../client/`) is a second
`@Mod` entry point with `dist = Dist.CLIENT`, so the dedicated server never
loads it. Commands only set up a job; captures are read from **real
frames** in `RenderFrameEvent.Post` (after the frame is drawn, before it is
shown):

- `shot` sets `hideGui`, waits 3 frames, reads the main render target.
- `panorama` sets, before each frame (`RenderFrameEvent.Pre`), panoramic
  mode (90 degree FOV), `hideGui`, no block outline, a square window size and
  main render target, and the player's rotation for the current face. A
  face is read once 3 frames have rendered and
  `levelRenderer.hasRenderedAllSections()` (chunk sections compiled), or
  after 5 s (the reply then says `(N faces still compiling chunks)`). The
  window, render target, rotation and GUI state are restored at the end.

Calling `GameRenderer.renderLevel` outside the frame loop, as vanilla's
`grabPanoramixScreenshot` does, failed in the headless client (GPU through
VirtualGL, 2026-10-31): into a separate `TextureTarget` it drew the sky but
no terrain; into the main target, terrain under a black sky (fog/state
leftovers between passes). Its `levelRenderer.graphicsChanged()` also
throws away every compiled chunk section. Don't go back to it.

## Results (lite scope, testbed, 2026-10-31)

Live pack with KubeJS, client joined to the dev server, through
`mcf.py --client send_chat`:

| Check | Result |
|---|---|
| Client boots with the mod; dedicated server boots with the same jar | yes; server deploy with 18 regression checks: all pass |
| `ping` | `studio: ok 0.2.0 1280x720` in `get_recent_chat` and the client log |
| `shot` at 1280x720 / 1920x1080 | no HUD, hotbar, crosshair or hand (creative, sword held); GPU 130-190 ms, llvmpipe 455 ms (1920x1080) |
| `clean on` / `off` (MCPFabric `screenshot`) | hotbar, hand, crosshair and chat hidden / back |
| `panorama` at 1024 | six faces join at the seams (`texture.py panorama-check`), sun in face 4; GPU 1.1-2.0 s, llvmpipe 3.0 s |
| bad name, busy | `studio: error bad name ...`, `studio: error busy ...` |

## Acceptance (the original spec; 1-4 and 7 met for the lite scope, 5-6 future)

1. The client boots with the mod and joins the dev server. The dev server
   loads none of the client code.
2. `/studio ping` sent through `mcf.py --client send_chat` answers. If NeoForge
   doesn't route `sendCommand` to client commands, add a fallback: poll
   `<gamedir>/studio/requests/*.json` once per client tick (`{"command":
   "shot test 1920 1080"}`), run it, delete the file, and write the reply
   line to `studio/requests/<file>.result`. Document which path works.
3. `shot` writes a 1920x1080 PNG with no HUD, hand or crosshair. Read it to
   check.
4. `panorama` at 1024 writes six square faces, and
   `scripts/texture.py panorama-check` shows them joining at the seams.
5. `entity` on a frozen (`/tick freeze`) vanilla mob and on one modded boss or
   mob with a custom renderer (GeckoLib, if the roster has one) gives a correct cut-out: transparent background, no
   clipping, lit like the game.
6. `block` on a vanilla block and on a modded machine with a block
   entity renderer; `item` on a flat item and on a block item.
7. Each capture at 1024 px finishes within about 30 s under llvmpipe.
   Report the times.

Report any command that couldn't be built, and why, in the return block.
The orchestrator decides whether to drop it or re-brief.

## Usage

1. Size: the client window is 1280x720 unless launched with
   `PEXP_CLIENT_SIZE=WxH` (320x240 to 3840x2160), e.g.
   `PEXP_CLIENT_SIZE=1920x1080 infrastructure/headless-client/bin/launch.sh --join`.
   `shot` captures at that size; `panorama` sets its own size.
2. Stage: see the pack-art skill § "UI art" (spectator, time, weather,
   `gamerule doDaylightCycle false`, `NoAI` bosses, `/tick freeze`).
3. Aim the camera: `run_command 'tp PexpBot <x> <y> <z> <yaw> <pitch>'` on the
   server bridge, then wait a few seconds for chunks to render. For a
   panorama the yaw picks face 0; pitch doesn't matter.
4. Capture and read the reply:
   ```sh
   python3 -I scripts/mcf.py --client send_chat '{"message":"/studio shot camp_wide"}'
   python3 -I scripts/mcf.py --client send_chat '{"message":"/studio panorama title 1024"}'
   python3 -I scripts/mcf.py --client get_recent_chat '{"limit":3}'
   ```
   Then Read the PNG (`infrastructure/headless-client/instance/studio/...`);
   check a panorama with `python3 -I scripts/texture.py panorama-check <dir> --out <png>`.
5. Keepers go into `art/captures/<name>.png` (or a panorama into
   `art/assets/minecraft/textures/gui/title/background/`). Copy them with the
   Write tool or `cp`; the budget hook allows `cp` into `art/`.
6. Compose and build (pack-art skill).

Captures look like plain vanilla: the headless client renders with no
shaders (on the GPU through VirtualGL since 2026-10-31; llvmpipe is the
fallback, and its output differs slightly, so take a set of captures on one
renderer: check `infrastructure/.state/client-renderer`). Shader shots are deferred until the owner has
seen the vanilla title screen (charter).
