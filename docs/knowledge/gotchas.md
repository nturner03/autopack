# Gotchas

Lessons that cost time in earlier packs and experiments. Add new entries as
you hit them. Keep each one short, with the symptom first and then the fix.
Skills link here instead of repeating these. Mod-specific lessons (one
mod's machines, one mod's quirks) go under "Roster mods" at the end.

## Host and toolchain

- **The PATH `java` is 1.8.** Symptom: Gradle, NeoForge or a jar fails with
  class-version errors. MC 1.21.1 needs Java 21:
  `/usr/lib/jvm/java-21-openjdk-amd64`. The infrastructure scripts and
  `build-custom-mod.sh` pick it from the MC version.
- **tmux prefix matching.** `tmux has-session -t pexp-x-server` also
  matches `pexp-x-server-old`. Target sessions as `=name` (exact match), as
  `infrastructure/lib/common.sh` does.
- **Several experiments on one host.** Each repo has its own ports and tmux
  names (`infrastructure/project.env`), its own token, server and client.
  Never reuse another experiment's ports; `start.sh` refuses a port that is
  already taken.
- **HeadlessMC needs `hmc.check.xvfb=true`.** Without it, offline accounts
  silently stub LWJGL: the client "runs" but screenshots fail or come back
  black. `headless-client/bin/install.sh` sets it. Keep it if you rewrite
  the config.
- **VirtualGL `vglrun` resets `VGL_LIBRARY_PATH`.** Symptom: the client log
  says `OpenGL Renderer: llvmpipe` and the tmux pane shows `ld.so: object
  'libdlfaker.so' from LD_PRELOAD cannot be preloaded`. Pass the unpacked
  library folder with `vglrun -ld <dir>`, as `launch.sh` does.
- **Kill the client game before its tmux session.** Killing the tmux session
  first kills `xvfb-run` and leaves its Xvfb running (orphans pile up).
  `stop.sh` ends the game first and kills the recorded display as a
  backstop.
- **The client window moves after it appears.** It's created at +0+0 and
  centred at +160+90 a moment later (the Xvfb screen is 320x180 larger than
  the window, whatever `PEXP_CLIENT_SIZE` is), so a screen-region capture
  can be off by (160, 90). `record.sh` captures by X window id, and
  `xclick.py` reads the window position with `xwininfo`.
- **Don't call `GameRenderer.renderLevel` outside the frame loop** (client
  mod code). Vanilla's `Minecraft.grabPanoramixScreenshot` does, and in the
  headless client it drew sky without terrain into a separate render
  target, or terrain under a black sky into the main one. Change state in
  `RenderFrameEvent.Pre` and read the main render target in
  `RenderFrameEvent.Post` instead (how `/studio` works).
- **Never print or ship the MCPFabric token** (`infrastructure/.state/mcpfabric-token`).
  Don't echo it, put it in docs or logs, or let a config containing it into
  `packwiz/`. The pack's `.packwizignore` already excludes the mcpfabric
  config.
- **`PEXP_PACK_TOML` does not persist between Bash calls.** Export it in the
  same command as `update-pack.sh` / `restart.sh`, or the script refreshes
  and installs the real `packwiz/` pack over a throwaway one.
- **Runtime scripts without `PEXP_PACK_TOML` install the working-tree
  `packwiz/`.** Running `update-pack.sh` that way onto a scratch-pack server
  deletes files from the previous manifest (including generated server
  configs), and clients can then fail config sync at join
  (`NoSuchFileException <mod>-server.toml`). Always set `PEXP_PACK_TOML` for
  scratch runs; a restart regenerates the file.

## packwiz

- **Re-adding a mod resets `side`.** `packwiz modrinth add` with a new
  version id rewrites the `.pw.toml` with the default side. Set it again.
- **packwiz can pull in a library the mod already bundles** (jar-in-jar) as
  an auto-dependency. Check the jar's metadata and remove the duplicate.
- **Stale files on installed copies.** packwiz-installer only replaces files
  whose hash changed. A file hand-edited on the server or client survives
  deploys until the pack's copy changes. Never hot-fix the installed copy;
  edit `packwiz/` and deploy.
- **Line endings are LF only.** packwiz hashes bytes, so CRLF changes the
  hash. `.gitattributes` enforces `eol=lf`.
- **Run `packwiz refresh` after any file change** under `packwiz/`. Only one
  agent at a time runs packwiz commands, because they rewrite `index.toml`.
- **Side classification** comes from the jar and code, not Modrinth's
  `client_side` tag. A client-only mod on the server crashes with a missing
  client class. See the packwiz-manager skill.
- **Shipping a client default without overwriting the player's copy**: put
  the file in `packwiz/` (for example `options.txt` with only the key lines
  you change; Minecraft fills in the rest) and add `preserve = true` to its
  `[[files]]` entry in `index.toml` by hand. `packwiz refresh` keeps the
  flag and only updates the hash; packwiz-installer then skips the file if
  it already exists
  (<https://packwiz.infra.link/reference/pack-format/index-toml/>). **A
  shipped `options.txt` must start with `version:3955`** (1.21.1's data
  version): without it the file is read as data version 0, the 1.12 key
  fixer throws `NumberFormatException "key.keyboard.unknown"` and every line
  is ignored. Re-check the flag after any refresh diff. An existing
  instance (the headless client) is untouched.
- **Switching back from a throwaway pack leaves empty folders.** The
  installer deletes files the new pack doesn't list but keeps their
  directories, and some mods log errors for an empty book or data folder.
  After a `PEXP_PACK_TOML` test, run the client's `update-pack.sh` too and
  delete empty directories in the install (`find <dir> -depth -type d -empty -delete`).

## KubeJS (Rhino)

Verified on KubeJS 2101.7.x and Rhino 2101.2.x; re-check on other versions.

- No `Array.prototype.flat`. Build arrays with loops or `concat`.
- A `const` declared inside a loop body keeps its first-iteration value. Use
  `let` in loop bodies (loop-head `for (const x of xs)` is fine). Rhino can
  also reject `const` inside a `forEach` body ("redeclaration of var").
- Optional chaining (`?.`) is a syntax error.
- `getClass()` and `Ingredient.getItems()` are hidden.
- `BlockState.setValue` needs a boxed Boolean.
- `level.getGameTime()` doesn't resolve on `ServerLevel`.
- `global.x = ...` is an error in server scripts ("'global' cannot be
  assigned to"); use a top-level `const`.
- `Java.loadClass('java.lang.System')` is blocked by the class filter (use
  `Date.now()` for timing).
- `level.dimension` is already a ResourceLocation: `String(level.dimension)`
  works and `.location()` throws. A per-tick handler error does not show up
  as a script load error, only in the log as "Error in 'PlayerEvents.tick'".
- The block builder has no `textureAll` (use `.texture('minecraft:block/...')`);
  `.fireResistant()` exists on the item builder.
- A command's `ctx.source.player` is null from the console: run player
  commands from the client (`send_chat "/cmd"`).
- Mods without KubeJS recipe schemas (and Create on 1.21.1): use
  `event.custom({...})` mirroring the mod's own recipe JSON.
- **`replaceInput` can silently skip custom recipe types** (it reported
  "modified 1 recipes" for 6 calls on a mod's upgrade recipe; vanilla types
  worked). Use `forEachRecipe` + `r.json...` + `r.save()`, or a
  `kubejs/data` JSON override, and check the loaded recipe with a probe.
  `r.json` in the same event does not reflect `replaceInput` changes.
- Server scripts, recipes, tags and loot reload with `/reload`. Startup
  scripts, registries and worldgen registration need a restart. See the
  kubejs skill.
- **Probes:** `ServerEvents.loaded` does not fire on `/reload`: register a
  probe with `ServerEvents.commandRegistry` and run it as a command. Loaded
  recipes: `server.recipeManager.byKey(Java.loadClass('net.minecraft.resources.ResourceLocation').parse(id))`
  and `Ingredient.test(Item.of(x))`.
- Don't name a shipped script `main.js`: `packwiz/.packwizignore` has
  `kubejs/*/main.js`.
- The texture lint (`texture.py lint`, run by `check_pack.py`) reads
  startup scripts as text. It finds `event.create('<literal id>')` and
  looks for `.texture(...)` in that chain, up to the next `;` or `create`.
  Keep one literal-id `create` per chain with the `.texture()` on it. Ids
  built in a loop or from variables aren't seen, so check those by hand.

## FTB Quests

- **IDs are 16 uppercase hex digits starting `0`-`7`.** IDs `8000...` and
  above overflow `Long.parseLong`. They get a random new ID on every load
  and silently lose their lang text and dependencies. Use `scripts/quests.py ids`.
- **`order_index` drift.** Number chapters per group (0-based within the
  group). Book-wide numbering drifts when FTB Quests re-saves.
- Reload with `ftbquests reload quests` (definitions only). Never use plain
  `reload team_progress`.
- **Task-less quests never complete** (2101.1.37), even when all their
  dependencies are done. Give each gate node one checkmark task.
  `quests.py check` errors on a task-less quest.
- `ftbquests change_progress ... complete` on a dependency may not trigger
  completion checks on its dependants. Complete deps through their real
  tasks when the dependant's behaviour is under test.
- **Quest `command` rewards run as the player** in the player's dimension:
  a map or locate-based reward claimed in the wrong dimension silently does
  nothing useful.

## In-game testing (MCPFabric, headless client)

- **`latest.log` freshness.** Check the log's mtime against
  `infrastructure/.state/server-started-at` (or `client-started-at`). An old
  log says nothing about this run.
- **"Chat messages can't be verified" toast** shows in the top-right of
  headless-client screenshots after joining. This is normal for an
  offline-mode server; it fades after a few seconds.
- **Worldgen changes apply only to new chunks.** Reset the world or explore
  far away before judging them.
- **`find_blocks`** takes `blockIds` (an array, not `block`) and `center`
  ({x,y,z}), plus `dimension` for other dimensions. It has a scan budget:
  keep the radius to about 30 and check `truncated`.
- **`/locate` and maps use the command source's dimension.** `run_command`
  runs as the console in the Overworld: for another dimension use
  `execute in <dim> positioned X Y Z run locate structure <id>`.
- **`exploration_map` `search_radius` counts spacing regions** for
  `random_spread` structure sets, not chunks. It is not a distance limit.
- **No tool opens the player inventory** (MCPFabric 0.8.0), and
  `click_widget` only reaches vanilla widgets. Screens that come from using
  a block or item do open (`use_item` on a quest book, a placed crafting
  table for EMI).
- **Real mouse clicks and key presses work through XTest**:
  `python3 -I infrastructure/headless-client/bin/xclick.py move|click X Y`
  (window-relative; screenshot first to find coordinates) and
  `xclick.py key <keysym> [seconds]`. Move, wait ~1 s, then click; the first
  click after a move can be swallowed. This reaches mod GUIs (FTB Quests
  checkmarks and reward buttons, mod settings screens, inventory buttons).
- **Bridge raw methods `container.click/state/transfer`** exist in
  MCPFabric but not as tools: `scripts/mcf.py --client --method container.click '{"slot":N,"button":0|1}'`
  drives an open container (crafting table: slot 0 result, 1-9 grid, 10-36
  main, 37-45 hotbar). The `swap_slots` tool only touches the player
  inventory menu.
- **Tooltip screenshot trick**: `item replace entity PexpBot inventory.4 with <item>`,
  open a crafting table; the mouse rests on that slot so the tooltip shows.
- **Multiplayer menus don't pause the game**: PexpBot dies to mobs while a
  GUI is open. Set peaceful for long GUI work (and back to normal for
  fights). A dead bot (`get_self` health 0.0, `get_screen` "death") needs
  `close_screen` to respawn before any client check.
- **`attack_entity` on an entity that has just died kicks the client**
  ("Attempting to attack an invalid entity"). Check the entity still exists
  first, or kill with `damage ... by PexpBot`.
- **A bare `tp` doesn't fire a location advancement**; walk a block.
- **`tick sprint N` returns immediately** ("The game is sprinting"): poll
  `time query gametime`, don't wait on the call. MCP/mcf call latency is
  itself ~100 ticks of game time.
- **Multiblocks** may not see fluids or items inserted with `data modify` /
  `data merge` until they're re-formed, and some only form when an entity
  places the controller (`setPlacedBy`). Feed machines through their real
  input (GUI, `item replace`, a hopper) and have PexpBot `place_block` the
  controller when `setblock` doesn't form it.
- **Belt-like and pipe-like blocks** placed one `setblock` at a time can
  break or fail to connect. Place them in one tick from a temporary
  function, or by `place_block`.
- **Trial spawners ignore creative players**, and their own light blocks
  mobs that need block light 0. Test spawn rules with a KubeJS command
  calling `SpawnPlacements.checkSpawnRules(type, level,
  MobSpawnType.TRIAL_SPAWNER, pos, level.random)`.
- **Vault tests**: the `key_item` check needs the key in the selected slot;
  `use_item` reports target "air" on a vault, so right-click it with
  `place_block` on its face.
- **Structure Block SAVE via redstone saves only in memory**, and the
  headless client refuses UI control of the Structure Block screen. Write
  test templates as vanilla structure NBT (gzip, DataVersion 3955) with a
  script.
- **Creative PexpBot can die in a void dimension** below its floor: tp
  first, `fill` a platform after (fill fails in unloaded chunks), then tp
  again.
- **Fall-flying**: the double-jump (`jump` twice) is unreliable; a KubeJS
  command calling `startFallFlying()` via `send_chat` works, and
  `data get entity PexpBot FallFlying` reads the flag.
- **Dimension mods may hand PexpBot starter items** in hotbar slot 0:
  `clear PexpBot` before relying on hotbar slots.

## Platform (1.21.1 / NeoForge)

The full list with sources is in [platform.md](platform.md). These cost the
most time:
- **Plural data folders load nothing, silently.** Use `recipe/`,
  `loot_table/` and `tags/item/`, not `recipes/`, `loot_tables/` or
  `tags/items/`.
- **Pack configs in `defaultconfigs/` do nothing** once the file exists in
  `config/`. Ship them in `config/`.
- **A partial config file gets "corrected"**: backed up and rewritten with
  defaults for the missing keys. Ship complete files.
- **Advice written for 1.20.1 or Fabric** (forums, old wikis) is often wrong
  here: `forge:` tags, NBT item syntax, plural folders. Check the version a
  source is about.
- **A `minecraft [1.21,1.21.1)` range in a jar's `neoforge.mods.toml`
  doesn't stop it loading** on NeoForge 21.1.265. Treat such a range as a
  packaging slip, but still confirm with a boot.
- **`recipe_index.py` reads the NeoForge universal jar** for the `c:` tags
  (`c:stones`, `c:gems/quartz`). Rebuild the index after an install change.
- **A loot `minecraft:tag` entry with `"expand": false` drops every item in
  the tag**; `"expand": true` makes each item its own entry, so one roll picks
  one. A fact-check misread this once and put the error into a quest.

## Known log noise

The list lives in [`tests/log-noise.txt`](../../tests/log-noise.txt): one
regex per line, each with a comment naming the condition it appears under.
The `log_clean` regression check and pack-log-triage both read it. Add an
entry only once a line is confirmed harmless, and keep the pattern narrow.

## Orchestration

- **`orch-*` agent types are blocked outside `/orchestrate` sessions** (the
  global orch hooks); give tooling briefs to `general-purpose`.
- **Subagent report files:** the harness can refuse a subagent's write of
  a scratch report ("subagents should return findings as text"). Put long
  output in a `docs/` path the brief names (for example
  `docs/design/reviews/`), or in the return message.
- **Designer context:** a pack-designer brief that covers a whole doc plus
  many findings runs into the ~150k limit and ends PARTIAL, sometimes with
  nothing written. What works: **write-first** (put the section headers in
  the file within the first few calls, add rows as each fact is confirmed),
  stop researching at ~110k, keep each brief to one doc or one set of
  findings, and split a big doc by act range.
- **Reviewer context:** whole-set critiques hit the limit with only the
  report skeleton written, and the context hook then blocks the big final
  write. Tell reviewers to append each focus area's findings to the report
  **before starting the next area**, and keep each finding a few lines long.
- **Tester context:** testers fill ~150k tokens on 10+ checks. Brief at
  most 5-6 check groups (two to four runtime probes), and have them write
  the record first and append after every check.
- **A context hook can block a reviewer's or tester's final write**; their
  continuation note then holds the report, and the orchestrator files it.
- **Quest writers spend most of their context on fact research.** Split a
  chapter into a plan pass and a write pass: Pass A (read-only) writes
  `plan-<n>.md` with the facts, sources, the settled layout and the
  finished text; Pass B writes the SNBT and lang from that plan. Pass A can
  run in parallel with another chapter's Pass B. Cite rows already
  `verified` instead of re-proving them.

## Roster mods

Quirks of specific mods in this pack's roster (symptom, then the fix).

- None yet.
