---
name: ingame-testing
description: Verify pack behaviour in the running game - MCPFabric usage rules (mc-server and mc-client tools, or scripts/mcf.py), the test platform, how to prove recipes, gates, machines, worldgen, loot and quests work, how to inspect GUIs/EMI/quest book with screenshots, how to write test records, and how to queue checks only a human can do. Use for any in-game verification or when deciding whether something needs the owner.
---

# In-game testing

Two bridges, same tools, different sides:
- **mc-server** (`127.0.0.1:SERVER_BRIDGE_PORT`): world read/write, entities, players,
  `run_command` (op level 4, returns output), chat, events.
- **mc-client** (`127.0.0.1:CLIENT_BRIDGE_PORT`, the headless client as PexpBot): what a
  player sees and does - `screenshot`, `get_screen`, `get_ui`,
  `click_widget`, `set_text_field`, `close_screen`, movement, `look_at`,
  `use_item`, `place_block`, `break_block`, inventory, `describe_scene`.
- Without the MCP tools (or for scripting): `python3 -I scripts/mcf.py
  [--client] <tool> '<json>'`; `--list` shows tools; screenshots are saved
  to a PNG path it prints (Read it to look).

Lifecycle and deploys: the dev-server skill. Only the agent that owns the
runtime in its brief deploys or restarts.

## Rules

1. `get_status` first on each bridge you use; if unreachable, check
   `infrastructure/dev-server/bin/status.sh` before anything else.
2. `list_players` before any restart, reset or world edit near spawn. A
   non-bot player online = owner playtesting: don't disturb them.
3. `find_blocks` has a scan budget: radius <= ~30, check `truncated` and
   `searchedRadius` in the result. For larger surveys use `/locate`,
   `execute if block`, or a KubeJS probe.
4. Prefer structured reads (`get_block`, `get_blocks_region`, `get_entity`,
   `run_command` output) over screenshots; use screenshots for what only
   pixels show (GUIs, EMI, quest book, textures, visuals). Each screenshot
   costs context: take the ones you need, describe what you saw in the
   record.
5. Evidence or it didn't happen: every claimed pass names the command/tool
   output, log line or screenshot path.

## 1.21.1 command syntax

Items carry **data components**, not NBT (see `docs/knowledge/platform.md`).
- Give with components:
  `give PexpBot minecraft:diamond_sword[minecraft:enchantments={levels:{"minecraft:sharpness":5}}]`.
  Custom data goes in `[minecraft:custom_data={...}]`.
- Test held or carried items:
  `execute if items entity PexpBot weapon.mainhand #c:ingots/iron`,
  `execute if items entity PexpBot container.* <item>`.
- Loot: `loot give PexpBot loot <ns>:<table>`, `loot spawn <x y z> loot <table>`.
- Speed up machines and growth: `tick sprint <ticks>`; `tick freeze` and
  `tick unfreeze` for timing-sensitive checks.
- Common tags are `c:` (`#c:ores/iron`); `forge:` tags don't exist.

The command reference is <https://minecraft.wiki/w/Commands> (Java 1.21.1).
If a command fails on syntax, check the wiki page for that command before
searching the web.

## Test platform

Build tests away from spawn and from each other:
- Test area: a flat platform at `x=10000+, z=10000+, y=200`
  (`fill_blocks` smooth stone, 32x32), one platform per topic, coordinates
  noted in the record. Teleport PexpBot there (`teleport_player`) before
  client checks.
- `set_gamemode` creative for setup; **survival** for "can a player
  actually do this" checks.
- Clean up big builds when done if they would confuse later tests; the world
  can also simply be reset (`reset-world.sh`).

## Recipes and gates

Static (cheap, always): `scripts/recipe_index.py makes|uses <item>` on the
jars + read the pack's KubeJS for overrides. Loaded state (authoritative):
`recipe_index.py build --live` after the deploy (the `/pexp dump` of what
the server loaded, KubeJS scripts included), then the same queries; a
KubeJS probe (kubejs skill) only for what the dump can't show. Player-visible (when progression-critical or
GUI-related): on the client, give inputs, open the crafting table / machine
GUI, check EMI's recipe page (screenshot), craft it, confirm the output in
`get_inventory`. A gate is verified when (a) the intended recipe exists,
(b) every bypass is gone (live index: `makes <item>` lists only the
intended recipe), and
(c) the inputs are obtainable at that tier (recipe_index chain + loot).
Then (a) and (b) become regression checks (`only_makers` with the intended
recipe ids; see "Regression checks" below), so no later change reopens a
bypass.

## Machines and multiblocks

Place with `set_block`/`fill_blocks` (or have PexpBot `place_block` for
facing-sensitive blocks), power/feed via commands (`item replace block`,
`data merge block`), then poll `run_command "data get block <pos>"` for the
output after the expected processing time (`tick sprint` can speed it up). Quirks:
multiblocks may not see fluids inserted with `data modify` until re-formed;
belt-like blocks placed one per `setblock` can break - place them in one
tick from a temporary function.

## Worldgen, structures, loot

- `run_command "locate structure <id>"` / `locate biome <id>`; then
  `teleport_player` and `find_blocks` (radius <= 30) at a few spots to count
  ores; or a probe/`/alscan`-style command for wide counts.
- New worldgen needs new chunks: reset the world or go >2000 blocks out.
- Loot: `run_command "loot spawn <x> <y> <z> loot <table>"` several times,
  then `query_entities` for item entities; or `loot give PexpBot loot <table>`
  and `get_inventory` on the client.

## Quests

Deploy with `scripts/deploy.sh --quests`; log shows `Loaded N chapters`
(worth a `log_matches` check once the chapter count is settled).
On the client: open the quest book (FTB Quests keybind / book item), use
`get_ui` to find widgets and `click_widget` to open the chapter, screenshot.
Look for: missing-texture icons, text overflow, colour codes not rendering,
overlapping nodes, lines behind quests. Prove a few tasks detect: `give_item`
the item to PexpBot, wait a second, check the quest shows complete (UI or
`ftbquests` command output).

**Mod GUI clicks** (checkmarks, reward buttons, any widget `click_widget`
can't reach): `python3 -I infrastructure/headless-client/bin/xclick.py
click X Y` sends a real XTest click at window coordinates (screenshot to
find them; move, wait ~1 s, click; repeat if the first is swallowed).
Complete quests only by real clicks or real tasks, never by command
(gotchas § In-game testing).

## Client-only checks the headless client can do

Join works (server log `PexpBot joined the game`), no client crash with the
current mod set, item names/tooltips/lang, EMI recipe pages, quest book,
custom GUIs, block/item textures (zoom with `look_at` close up), basic
rendering of structures/biomes. It renders through VirtualGL on the GPU or
on Mesa llvmpipe (`infrastructure/.state/client-renderer`), capped at 30
FPS with no shaders: judge correctness, not performance or shader looks.

Pack textures: give the item and screenshot it in the hotbar and inventory;
place blocks in a 3x3 wall and look from ~5 blocks away. A purple-and-black
square is a missing texture: check `texture.py lint` and the client log.
For clean captures (no HUD, hand or crosshair) use the `/studio` client
commands: `shot`, `panorama`, `clean on|off` (pack-art skill,
`references/studio.md`).

## What only the owner can judge

Fun, pacing over real hours, difficulty feel, visual taste, readability on a
normal monitor, performance on real hardware, multiplayer with real
latency, shaders. Queue these; never ask the owner to check anything the
headless client or a probe can prove.

## Regression checks

What you verify stays verified only if a check keeps proving it.
`tests/checks/<topic>.toml` holds them (format and kinds:
`tests/README.md`); `scripts/deploy.sh` runs the full set after every deploy
and exits non-zero on a FAIL.

- **Add a check for every verified, progression-critical claim** that the
  live dump, the logs or a read-only command can prove: a removed recipe
  (`recipe_absent`), a gate with no bypass (`only_makers`), tag or loot
  membership (`tag_contains`, `loot_mentions`), a registered item
  (`item_exists`), a quest chapter count (`log_matches`). One topic file
  per area; `why` names the design section or decision it protects.
- Run the new ones: `python3 -I scripts/checks.py run --only <topic>`. A
  check that passes before the change it guards is useless: where you can,
  watch it FAIL first (e.g. before the KubeJS removal is deployed).
- Claims that need a player (GUI, EMI page, rendering, feel) stay in the
  record and, if a human must judge them, the human-testing queue.
- A FAIL in someone else's check is a finding: report it, don't edit the
  check. A known-harmless ERROR line goes in `tests/log-noise.txt` with the
  condition it appears under, never a blanket pattern.

## Records

Write one record per test session: `docs/testing/records/YYYY-MM-DD-<topic>.md`

```markdown
# <topic> - YYYY-MM-DD
**Build:** pack <version> @ git <sha> · **World:** <seed/reset date> · **By:** pack-tester (brief <task>/<n>)
| Check | Method | Result | Evidence |
|---|---|---|---|
| Steel needs blast furnace | probe PROBE-STEEL, EMI screenshot | pass | log line ...; docs/local/screenshots/... |
**Regression checks added:** `tests/checks/<topic>.toml`: <id>, <id> (all pass; full set: N pass)
**Unverified / follow-ups:** ...
```

Screenshots worth keeping (evidence for a decision or a bug) go in
`docs/testing/screenshots/` (committed, keep them few and small); routine ones
stay in `docs/local/screenshots/` (gitignored).

## Human test requests

Append to `docs/human-testing/queue.md` using the request template there:
id, build version, what to do (exact steps and where), what to look for,
time needed, and what decision the result feeds. Then continue other work.
