# Agent guide

This repo is an experiment: an autonomous team of Claude Code agents builds a
complete Minecraft modpack and makes nearly every decision itself. The owner's
goal and rules are in [docs/charter.md](docs/charter.md). This file covers how
to work in the repo.

## Read first

1. [docs/charter.md](docs/charter.md): the goal, rules, owner-reserved
   matters and the human-gate policy.
2. [docs/status.md](docs/status.md): where things stand and the next action.
3. [docs/roadmap.md](docs/roadmap.md): the current phase only.
4. [docs/knowledge/platform.md](docs/knowledge/platform.md): Minecraft
   1.21.1 / NeoForge facts (data paths, tags, configs, where mods come
   from) and the sources to look things up in.
5. [docs/knowledge/gotchas.md](docs/knowledge/gotchas.md): before touching
   packwiz, KubeJS, quests or the runtime.
6. The skill for your task (table below). Agents preload theirs.

## Repo layout

| Path | Holds | Owner |
|---|---|---|
| `packwiz/` | The pack: `pack.toml`, `index.toml`, `mods/*.pw.toml`, `config/`, `defaultconfigs/`, `kubejs/`, quests in `config/ftbquests/quests/`. Everything here ships to players. | pack-implementer, pack-quest-writer |
| `custom-mods/<name>/` | One Gradle project per custom mod. Built jars are shipped to `packwiz/mods/` by `scripts/build-custom-mod.sh`. | pack-mod-dev |
| `art/` | Art sources: `assets/<ns>/textures/**` (`.grid`, `.derive.json`, `.compose.json`, `.png`) that `scripts/texture.py build` turns into `packwiz/kubejs/assets/<ns>/textures/**`; `captures/` (studio shots); `palette.json` (art direction ramps). Pack PNGs are build outputs: edit the source. | pack-artist (`palette.json`: pack-designer) |
| `tests/` | Regression checks: `checks/<topic>.toml` (verified claims that every deploy re-proves against the loaded game; format in `tests/README.md`) and `log-noise.txt` (known-harmless ERROR lines) | pack-tester adds, orchestrator changes |
| `docs/` | Charter, status, roadmap, decisions, design, research, testing, human-testing, handoffs, knowledge. `docs/local/` is gitignored scratch output. | orchestrator, designer, tester |
| `infrastructure/dev-mods/<name>/` | Dev-only tool mods (agent infrastructure, never shipped): `pexp_devtools` gives the server `/pexp dump` (behind `recipe_index.py build --live`) and the client `/studio` capture commands. Built and installed into the dev server and headless client automatically by the update-pack scripts. | pack-mod-dev |
| `infrastructure/project.env` | This experiment's ports, LAN address and tmux prefix (tracked) | orchestrator |
| `infrastructure/dev-server/` | `bin/` scripts and `templates/` (tracked); `server/`, `backups/` (runtime, gitignored) | pack-tester |
| `infrastructure/headless-client/` | `bin/`, `templates/` (tracked); `hmc/` (HeadlessMC plus the MC/library cache), `instance/`, `recordings/` (session videos for the owner's audit) (gitignored) | pack-tester |
| `infrastructure/lib/common.sh` | Shared paths, Java selection, `pack.toml` reader; reads `project.env` | - |
| `infrastructure/.state/`, `infrastructure/cache/` | MCPFabric token, start timestamps; downloads and the recipe index (gitignored) | - |
| `scripts/` | Project tooling (table below) | - |
| `.claude/agents/`, `.claude/skills/` | The pack-* agents and skills | orchestrator |
| `.claude/scratch/<task>/` | Briefs, scope files, continuation notes (gitignored) | orchestrator |

`packwiz/.packwizignore` keeps repo-only and generated files out of the pack.
Update it when you add files under `packwiz/` that must not ship.

### scripts/

| Script | Does |
|---|---|
| `doctor.sh` | read-only check of host prerequisites, the charter and `project.env` ports |
| `deploy.sh --restart\|--reload\|--quests [--client] [--no-checks]` | refresh, `check_pack.py`, update the server (and client), restart or reload, health summary, then the regression checks (non-zero exit on a FAIL) |
| `checks.py run [--only <id\|topic>] [--no-dump] [--quiet] [--list]` | regression checks in `tests/checks/` against a fresh `/pexp dump`, the server logs and read-only commands; results in `docs/local/checks-last.json` |
| `check_pack.py [--deploy]` | static pack checks (TOML, sides, hashes, duplicates, texture lint); `--deploy` compares HEAD with the installed server and client |
| `mod_info.py` | Modrinth builds for 1.21.1 NeoForge, plus the jar's mod metadata (CurseForge: see platform.md) |
| `recipe_index.py build [--live]\|status\|makes\|uses\|tag\|tags-of\|raw-cost\|types\|show\|loot` | SQLite index of recipes, tags and loot: static from the installed jars and `packwiz/kubejs/data`, or `--live` from a `/pexp dump` of the running server (KubeJS script edits included) |
| `quests.py ids\|check\|outline\|render` | FTB Quests IDs, validation, outlines and layout previews |
| `mcf.py [--client] <tool> '<json>'` | direct MCPFabric JSON-RPC: the same tools as the MCP servers, for scripts and agents without MCP tools |
| `serve.sh [--stop]` | `packwiz serve` on `SERVE_PORT` for the owner's Prism client |
| `build-custom-mod.sh <name> [--test] [--dev]` | build a custom mod with an explicit `JAVA_HOME` and ship its jar into the pack (`--dev`: headless client only) |
| `texture.py find\|show\|to-grid\|render\|build\|preview\|lint\|...` | pixel-art toolkit: find base textures in vanilla and the jars, build `art/` sources into the pack, review sheets, lint (also run by `check_pack.py`) |

## Workflow

The main session runs **`/pack-orchestrate`**. It reads the state docs, picks
roadmap work, writes briefs to `.claude/scratch/<task>/`, spawns the agents
below on budget-appropriate models, verifies, reviews, commits and keeps
`docs/status.md` current. Subagents do one brief each and end with the return
block from `.claude/skills/pack-orchestrate/return-protocol.md`.

**At most one phase per session; the owner starts every session.** This
isn't a review gate; it keeps session context small.
- A session never crosses a phase boundary. When a phase is absolutely
  complete, the orchestrator hands off and gives the owner a ready-to-paste
  prompt that kicks off the next phase. It doesn't start that phase itself.
- A phase can take several sessions. When the work is long or the
  orchestrator's context fills up, park the current item, hand off and give
  `/pack-orchestrate continue` as the prompt. There's no need to rush a
  phase into one session.
- Only the owner starts `/pack-orchestrate` sessions. Agents never start,
  schedule or chain one themselves (no `claude` CLI runs, cron, scheduled
  triggers, wakeups or remote sessions). The handoff ends with the prompt
  for the owner to paste.

| Agent | Model (default) | Writes | Skills |
|---|---|---|---|
| pack-scout | haiku, low | nothing (pointers) | - |
| pack-log-triage | haiku, low | nothing (triage report) | - |
| pack-mod-researcher | sonnet, medium | `docs/research/mods/` | - |
| pack-designer | opus, high | `docs/design/`, `docs/decisions/`, `docs/roadmap.md`, `art/palette.json` | pack-design |
| pack-implementer | sonnet, medium (tiered up) | `packwiz/` | packwiz-manager, kubejs |
| pack-quest-writer | sonnet, medium | `packwiz/config/ftbquests/` | ftb-quests |
| pack-quest-fact-checker | sonnet, medium | report only | - |
| pack-tester | sonnet, medium | `docs/testing/`, `docs/human-testing/queue.md` | dev-server, ingame-testing |
| pack-mod-dev | sonnet, high | `custom-mods/` | custom-mod-dev |
| pack-artist | sonnet, high (opus for hero UI art) | `art/`, built textures in `packwiz/kubejs/assets/*/textures/` | pack-art |
| pack-reviewer | opus, high | report only | pack-design |

| Skill | Use for |
|---|---|
| pack-orchestrate | running the session as orchestrator (budget rules, return handling, books) |
| pack-handoff | ending a session with work left |
| pack-design | design method, quality bar, decision records |
| packwiz-manager | any change under `packwiz/` metadata, mods, configs |
| kubejs | recipes, tags, loot, worldgen data, startup registrations |
| ftb-quests | quest chapters (SNBT and lang) |
| dev-server | the dev server, headless client and pack host |
| ingame-testing | proving behaviour in game; test records; human test requests |
| custom-mod-dev | anything under `custom-mods/` |
| pack-art | textures, chapter images, title panorama and menu art (`art/`, `scripts/texture.py`, studio captures) |

The project hooks in `.claude/settings.json` (spawn log, per-agent context
budget, return-block check) live in `.claude/hooks/`, and the skills use
`.claude/scripts/md_section.py` and `returns.py` (stdlib only).
`scripts/doctor.sh` checks they exist.

## Platform

**Minecraft 1.21.1 on NeoForge 21.1.x** (currently 21.1.265, Java 21). The
owner set this (decision 0001); changing the Minecraft version or loader is
owner-reserved. Before writing data, configs or recipes, read
[docs/knowledge/platform.md](docs/knowledge/platform.md). The mistakes that
cost the most on this version:
- **Singular data folders**: `recipe/`, `loot_table/`, `tags/item/`,
  `tags/block/`. Plural folders load nothing, silently.
- **Recipe results use `"id"`**, not `"item"`.
- **Item data is components, not NBT**:
  `/give @s minecraft:diamond_sword[minecraft:enchantments={levels:{"minecraft:sharpness":5}}]`.
- **Common tags are `c:`** (for example `c:ingots/iron`); `forge:` tags are gone.
- **Server configs ship in `config/<modid>-server.toml`**. `defaultconfigs/`
  is only a seed for files that don't exist yet.
- **FTB mods come from CurseForge** (`packwiz curseforge add --addon-id ... --file-id ...`).

## Research and web search

Look things up in this order:
1. The installed jars, `scripts/recipe_index.py` (`build --live` for the
   loaded game) and the live game.
2. The repo: pack files, `docs/research/` and `docs/knowledge/`.
3. Official docs for 1.21.1, linked in `platform.md`.
4. **General web search** (WebSearch, then WebFetch) when 1-3 don't answer
   it, if the charter allows it (the template default does).

For web results: prefer primary sources (official docs, source code, the
mod's own tracker or wiki), and make sure they're about 1.21.1 / NeoForge.
Cite the URL and the date read. Keep web claims marked unverified until a
jar, the recipe index or the game confirms them. Never run downloaded code.

## Toolchain facts

- **Java:** never rely on the PATH `java`. The pack uses **Java 21**
  (default `/usr/lib/jvm/java-21-openjdk-amd64`) for the game and for
  custom-mod Gradle builds. `infrastructure/lib/common.sh` picks it from
  `pack.toml`, and `PEXP_JAVA` overrides it.
- **packwiz:** `~/go/bin/packwiz` (not on PATH; `PEXP_PACKWIZ` overrides it).
  Run it from `packwiz/`.
- **Node and MCP:** `node` on PATH, else the newest nvm install
  (`~/.nvm/versions/node/`). `.mcp.json` runs MCPFabric's MCP server from
  `$PEXP_MCPFABRIC_DIR/mcp-server/dist/` (required, no default) as
  `mc-server` (bridge `SERVER_BRIDGE_PORT`) and `mc-client` (bridge
  `CLIENT_BRIDGE_PORT`), reading both ports from
  `infrastructure/project.env` and the token from
  `infrastructure/.state/mcpfabric-token`. MCP tools load only in sessions
  started after the ports are set. Use `scripts/mcf.py` otherwise.
- **MCPFabric:** <https://github.com/denfry/mcpfabric>, checked out at
  `$PEXP_MCPFABRIC_DIR` (read-only). The
  matching jar (`mcpfabric-neoforge-0.8.0+1.21.1.jar` at template time) is
  fetched from Modrinth and installed into the dev server and headless
  client outside packwiz; it is never part of the pack.
- **HeadlessMC:** launcher wrapper 2.10.0 (pinned and checksummed in
  `headless-client/bin/install.sh`), under `xvfb-run`, offline player
  `PexpBot`. It renders on an NVIDIA GPU, if present, through VirtualGL 3.1.5
  (EGL back end; pinned in `lib/common.sh`, unpacked into the cache, no
  root), falling back to Mesa llvmpipe when the GPU is busy or
  `PEXP_CLIENT_GPU=0`. Every client session is recorded to
  `headless-client/recordings/<stamp>.mp4` for the owner
  (`PEXP_CLIENT_RECORD=0` only for FPS-sensitive tests).
- **Python:** `python3` (3.11+) with the standard library and Pillow (for
  `quests.py render` and `texture.py`). Run project scripts with `python3 -I`.
- **Host resources:** the host may be shared with other services and
  other experiments. The server heap is 2-6 GB; the client uses ~2-4 GB and
  ~1.5 cores on the GPU (3-4 on llvmpipe) while running.
- **Read-only references:** sibling experiments, if any (other experiment
  repos in the same parent directory as this one). Read them for format
  and method; never write to them, and never copy their text, story or art.

## Ports

This experiment's four ports are in `infrastructure/project.env`:

| Key | Bind | Use | Port | Evidence |
|---|---|---|---|---|
| `GAME_PORT` | `*` | dev server game port | _unallocated_ | - |
| `SERVE_PORT` | `*` | `packwiz serve` pack host | _unallocated_ | - |
| `SERVER_BRIDGE_PORT` | `127.0.0.1` | server MCPFabric bridge | _unallocated_ | - |
| `CLIENT_BRIDGE_PORT` | `127.0.0.1` | headless-client MCPFabric bridge | _unallocated_ | - |

Until they are set, every runtime script except `status.sh` refuses to run.
Choosing them is the first Phase 0 item (or the owner does it before the
first session). Pick four ports that are free: check live sockets
(`ss -ltnp`), Docker publications (`docker ps -a`) and sibling experiments'
`project.env` files. Whoever changes a port or bind address updates this
table and `project.env` in the same task. If the owner keeps a host port
inventory (set `PEXP_PORT_INVENTORY` so `scripts/doctor.sh` checks it),
record the ports there too, following the owner's rules for it.

## Live-state rules

- **The dev world is disposable.** Agents may restart, reset, back up and
  restore it without asking, unless `docs/status.md` says the owner is
  playtesting on it.
- **Check `list_players` first** (`scripts/mcf.py list_players` or the
  mc-server tool) before a restart, reset or anything disruptive. If a player
  other than `PexpBot` is online, the owner is playtesting: don't restart.
  Queue the change and note it in `docs/status.md`.
- **One runtime owner at a time.** One agent deploys or restarts the server
  or drives the client, and its brief names it. Others use static checks or
  read-only `mcf.py` queries.
- **Never hot-fix installed copies** in `server/` or `instance/`. Change
  `packwiz/` and deploy.
- **Only this experiment's runtime.** Never stop, restart or connect to
  another experiment's server, client, tmux sessions or ports.
- Stop the headless client when GUI checks are done; it is expensive.

## Git

- Agents own the local repo. Commit freely; **never push**, and never add,
  change or remove remotes (owner-reserved).
- The **orchestrator is the only committer**. Subagents leave changes
  uncommitted and report them in their return block.
- Conventional commits: `feat(quests): ...`, `fix(recipes): ...`,
  `docs(design): ...`, `chore(pack): ...`. End each message with the
  attribution line from the current system reminder, if any.
- Work on `main` unless a risky experiment warrants a branch.
- Pack versions are semver (`0.x` until release) in `packwiz/pack.toml`. Bump
  the version when queueing a human test, and tag that commit `v<version>`.
- Don't rewrite published history; revert instead.

## Conventions

- **Platform:** Minecraft 1.21.1, NeoForge 21.1.x (decision 0001).
- **Pack name:** _undecided_ (Phase 0 → Identity; placeholder "Untitled
  Pack" in `packwiz/pack.toml`).
- **Pack namespace:** _undecided_ (Phase 0 → Identity). Once chosen, use it
  for KubeJS ids, tags (`<ns>:...`), datapack paths, art and custom-mod ids,
  and add it to `art/palette.json` → `namespaces`.
- One KubeJS file per topic. Recipe changes cite their reason (design doc
  section or decision record) in a comment.
- All player-facing quest text goes in the FTB Quests lang file.
- If the charter keeps agent-made art: art is made by agents from data, not
  image generators. Textures derive from vanilla or roster textures and are
  refined as text grids; UI art is composed from studio captures. Every
  KubeJS-registered item and block names its texture with `.texture(...)`.
- Decisions go in `docs/decisions/`; lessons go in
  `docs/knowledge/gotchas.md`.

## Secrets

The MCPFabric token (`infrastructure/.state/mcpfabric-token`) is the only
secret. Never print, log, commit or ship it, and never paste it into docs,
briefs or return blocks. Scripts and `.mcp.json` read it from the file.
