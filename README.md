# Modpack experiment template

A starting point for an autonomous modpack experiment: a team of Claude Code
agents designs and builds a whole Minecraft modpack (mods, story, recipes,
quests, art and balance). It targets a fixed platform, **Minecraft 1.21.1 on
NeoForge 21.1.265**. The agents test in game themselves through a dev server
and a headless client driven by MCPFabric, and ask you only for what a person
has to judge.

> **Status: experiment.** This template has only been run on one Linux
> host. Expect rough edges, and read the scripts before running them.

Your rules for the agents go in [docs/charter.md](docs/charter.md); their
working guide is [AGENTS.md](AGENTS.md).

## What to expect

You write a charter describing the pack you want; the agents do the rest in
phases, one phase per session at most, and you start every session. The
template ships with the first two phases in
[docs/roadmap.md](docs/roadmap.md):

- **Phase 0 - Foundations:** a pack name, premise and core mod roster,
  booting on the dev server with the headless client joined.
- **Phase 1 - Design:** a complete, reviewed set of design docs (story,
  roster, progression, recipes, quests, balance, art direction) and a
  roadmap the agents write for every phase through release.

From Phase 2 on the agents implement that roadmap: mods, configs, KubeJS
recipes, quests, textures and custom mods, each verified in game, with a
commit per verified item. Along the way they queue playtests for you. A phase
can take several sessions, and a full pack takes many.

### Cost

This is a long-running, token-heavy workload. The main session runs as the
orchestrator on whatever model you start Claude Code with, and it spawns
subagents for most of the work: Opus for the designer and reviewer, Sonnet
for most others (Opus for hero UI art and other tiered-up briefs), Haiku for
cheap lookups. You need a Claude plan with Opus access, and usage adds up over
the many sessions a pack takes. To spend less, lower the `model` and `effort`
defaults in the frontmatter of `.claude/agents/*.md` (expect lower-quality
design and review).

## What's in the box

| Piece | Where |
|---|---|
| Orchestrator workflow, briefs, return protocol, handoffs | `.claude/skills/pack-orchestrate/`, `pack-handoff/` |
| 11 subagents (designer, researcher, implementer, quest writer and fact checker, tester, mod dev, artist, reviewer, scout, log triage) | `.claude/agents/` |
| Skills: design method, packwiz, KubeJS, FTB Quests, dev server, in-game testing, custom mods, pixel art | `.claude/skills/` |
| Hooks (spawn log, context budget, return-block check) and MCP servers | `.claude/settings.json`, `.mcp.json` |
| Dev server: install, start/stop, deploy, backups, world reset | `infrastructure/dev-server/` |
| Headless client: HeadlessMC on Xvfb, GPU via VirtualGL, session recording, XTest clicks | `infrastructure/headless-client/` |
| Dev-only tool mod `pexp_devtools`: `/pexp dump` of the loaded recipes, tags and loot (for `recipe_index.py build --live`), `/studio` captures | `infrastructure/dev-mods/` |
| Per-experiment ports, LAN address, tmux names | `infrastructure/project.env` |
| Tooling: deploy, pack checks, regression checks, recipe index, quest tools, MCPFabric CLI, texture toolkit, mod lookup, custom-mod builds, prerequisite check | `scripts/` |
| Regression checks run on every deploy (recipes, no-bypass gates, tags, loot, mods, clean logs, commands; platform starter set) and the known-log-noise allowlist | `tests/` |
| Empty packwiz project (MC 1.21.1, NeoForge 21.1.265, no mods) | `packwiz/` |
| Art source tree (empty palette) | `art/` |
| Doc scaffold: charter template, status, roadmap (Phases 0-1), decision 0001, platform facts, gotchas, test/human-test formats | `docs/` |

## Prerequisites

A Linux host (developed on Ubuntu, x86_64) with
[Claude Code](https://claude.com/claude-code). `scripts/doctor.sh` checks
all of these:

- **Java 21** at `/usr/lib/jvm/java-21-openjdk-amd64` (`apt install
  openjdk-21-jdk`), or set `PEXP_JAVA` to another Java 21 binary.
- **packwiz** at `~/go/bin/packwiz` (`go install
  github.com/packwiz/packwiz@latest`), or set `PEXP_PACKWIZ`.
- **Python 3.11+** with Pillow; **tmux**, **xvfb-run**, **curl**, **unzip**,
  **git**, `ss`, `dpkg-deb`, `sha256sum`.
- **Node.js** on PATH or via nvm.
- **[MCPFabric](https://github.com/denfry/mcpfabric)**: install its MCP
  server by following that repo's instructions, then set
  `PEXP_MCPFABRIC_DIR` to the checkout in the environment you start Claude
  Code from. The template needs `mcp-server/dist/index.js` (the MCP server
  `.mcp.json` runs) and `mcp-server/src/tools.ts` (the tool table
  `scripts/mcf.py` reads). You don't install the MCPFabric mod: the install
  scripts download the matching jar from Modrinth.
- Optional:
  - **ffmpeg** and **xwininfo**/**xdpyinfo**: session recording. Without
    them the headless client still runs, but its sessions aren't recorded.
  - **libXtst**: XTest clicks in the headless client's GUIs.
  - An **NVIDIA GPU** with EGL: without one the headless client renders on
    Mesa llvmpipe, which is slower and uses more CPU.

The Claude Code hooks and helper scripts (`.claude/hooks/`,
`.claude/scripts/`) are included in the repo.

| Env var | Default | Use |
|---|---|---|
| `PEXP_JAVA` | picked from the MC version | Java binary for the game and builds |
| `PEXP_PACKWIZ` | `~/go/bin/packwiz` | packwiz binary |
| `PEXP_MCPFABRIC_DIR` | none (required) | MCPFabric checkout (MCP server, tool table) |
| `PEXP_PORT_INVENTORY` | unset | optional host port inventory file for `doctor.sh` to check ports against |

## Starting an experiment

1. **Clone and start fresh history:**

   ```sh
   git clone https://github.com/nturner03/autopack.git experiments/<name>
   cd experiments/<name>
   rm -rf .git
   git init && git add -A && git commit -m "chore: experiment scaffolding from template"
   ```

   Dropping `.git` gives the experiment its own history and no `origin`
   remote (the agents never push or touch remotes; add one yourself if you
   want). The directory name becomes the default tmux prefix
   (`pexp-<name>-*`) and the dev server's MOTD.

   Running several experiments? Keep them side by side in one parent
   directory (for example `experiments/`). `scripts/doctor.sh` checks for
   port clashes with these sibling directories, and agents may read them
   (never write) for format and method.

2. **Check the host:** run `scripts/doctor.sh` and fix anything it reports.
   It is read-only. The four "`*_PORT` not set" failures are expected until
   the ports are set (step 4); everything else should pass.

3. **Write the charter:** fill in `docs/charter.md` → "The owner's request"
   and "Requirements, as rules", and delete the template defaults you don't
   want (agent-made art, FTB Quests, web research). Commit it.

4. **Ports** (pick one):
   - Let the agents do it: the first item of Phase 0 is "Runtime setup".
     The orchestrator picks four free ports, fills
     `infrastructure/project.env`, installs the server and client and boots
     the empty pack.
   - Or do it yourself before the first session: pick four free TCP ports,
     `GAME_PORT` and `SERVE_PORT` (LAN-facing) and `SERVER_BRIDGE_PORT` and
     `CLIENT_BRIDGE_PORT` (loopback only), fill them into
     `infrastructure/project.env`, then run
     `infrastructure/dev-server/bin/install.sh`,
     `infrastructure/headless-client/bin/install.sh` and
     `scripts/deploy.sh --restart --client`.

   Never reuse another experiment's ports; `scripts/doctor.sh` flags clashes
   with sibling experiments' `infrastructure/project.env` files (directories
   next to this one).

5. **Run it:**

   ```sh
   claude
   ```

   then

   ```
   /pack-orchestrate Begin Phase 0
   ```

   Continue later sessions with `/pack-orchestrate continue`, optionally
   followed by notes (`/pack-orchestrate continue; focus on quests`,
   `/pack-orchestrate process my playtest notes`).

The MCP tools (`mc-server`, `mc-client`) only work once the ports are set,
and load only in a session started after that. If the agents allocate the
ports during Phase 0, the next session picks the tools up; that session is a
fresh start anyway, because a session never crosses a phase boundary.

On the first start Claude Code may ask you to approve the two project MCP
servers; `.claude/settings.json` already lists them in
`enabledMcpjsonServers`. The only permission rules the project sets allow
`WebSearch` and `WebFetch`; you handle every other permission prompt.

## Playtesting

When the agents need a human check (fun, pacing, difficulty feel, visuals,
performance), they add a request to
[docs/human-testing/queue.md](docs/human-testing/queue.md) and keep working.
They only stop a session when a whole milestone is waiting on you. Client
setup (Prism with the packwiz pre-launch hook, the server address) is in
[docs/human-testing/README.md](docs/human-testing/README.md). To report,
fill in the request's **Results** field and start a session with
`/pack-orchestrate continue`.

## Watching progress

- [docs/status.md](docs/status.md): current phase, what's deployed, what's
  waiting on you, the next action.
- `git log`: one commit per verified item; `v<version>` tags mark builds
  queued for you.
- [docs/roadmap.md](docs/roadmap.md), [docs/decisions/](docs/decisions/)
  and [docs/design/](docs/design/): plans, decisions and design.
- [docs/testing/records/](docs/testing/records/): the agents' in-game test
  evidence; `infrastructure/headless-client/recordings/`: a video of every
  headless-client session.

## Runtime footprint

All of it is started on demand by the agents and runs in tmux.

| Piece | tmux | Ports (`project.env`) | Cost while running |
|---|---|---|---|
| Dev server | `<prefix>-server` | `GAME_PORT` (LAN), `SERVER_BRIDGE_PORT` (loopback) | heap up to 6 GB |
| Headless client (HeadlessMC, Xvfb, VirtualGL; session recorder) | `<prefix>-client` | `CLIENT_BRIDGE_PORT` (loopback) | ~4 GB, ~1.5 cores (3-4 on llvmpipe) |
| Pack host (`packwiz serve`) | `<prefix>-packhost` | `SERVE_PORT` (LAN) | small |

Check status with `infrastructure/dev-server/bin/status.sh`. To stop
everything: `infrastructure/headless-client/bin/stop.sh`,
`infrastructure/dev-server/bin/stop.sh`, `scripts/serve.sh --stop`.

> **Security:** the dev server runs in offline mode with no whitelist, so
> the headless bot can join. Anyone who can reach `GAME_PORT` can join under
> any name, including an operator's. Keep `GAME_PORT` and `SERVE_PORT` on a
> trusted LAN, and never port-forward them or expose them to the internet.

Runtime state (server, world backups, client instance, HeadlessMC and
download caches, the MCPFabric token) lives under `infrastructure/` and is
gitignored. Each experiment downloads its own Minecraft client (~1 GB in
`infrastructure/headless-client/hmc/`), and the first server install builds
`pexp_devtools` with Gradle (a few minutes the first time on a host).

## Keeping the template current

Improvements made inside an experiment (a script fix, a new gotcha, a better
skill) don't flow back automatically. If you keep your own copy of this
template, port generic fixes into it by hand, and keep pack-specific content
(mod names, story, decisions beyond 0001) out of it.

## License

[MIT](LICENSE). Third-party pieces the scripts download at install time
(Minecraft, NeoForge, MCPFabric, HeadlessMC, VirtualGL, packwiz-installer,
mods) keep their own licenses.
`infrastructure/dev-server/bin/install.sh` writes `eula=true`; by running it
you accept the [Minecraft EULA](https://www.minecraft.net/eula).
