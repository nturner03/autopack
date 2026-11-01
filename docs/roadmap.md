# Roadmap

The phases from scaffolding to release. The orchestrator reads one phase at a
time with `python3 -I .claude/scripts/md_section.py docs/roadmap.md "<heading>"`,
so keep each phase under a `## Phase N - Name` heading. Tick items with
`[x]` and add discovered work under the phase it belongs to. Phases 2 and
later are written by the agents at the end of Phase 1; rules every
implementation phase shares go under `## Phases 2+ - shared rules`.

## Phase 0 - Foundations

Goal: a named pack with a premise and core roster, booting on the dev server
with the headless client joined.

- [x] **Platform**: Minecraft 1.21.1 on NeoForge 21.1.265, set by the owner
  (decision 0001). Facts and sources: `docs/knowledge/platform.md`.
- [x] **Pack init**: "Untitled Pack" 0.0.1 (placeholder name) from the
  experiment template. Never run `packwiz init` again.
- [ ] **Runtime setup** (orchestrator inline, or a general-purpose brief;
  skip any step the owner already did):
  - `scripts/doctor.sh` passes its prerequisite checks.
  - Pick four free TCP ports (game `*`, pack host `*`, server bridge
    `127.0.0.1`, client bridge `127.0.0.1`): check live sockets, Docker
    publications and sibling experiments (AGENTS.md → Ports), fill
    `infrastructure/project.env` and record them in AGENTS.md → Ports
    (and the owner's port inventory, if one is configured).
  - Install: `infrastructure/dev-server/bin/install.sh`,
    `infrastructure/headless-client/bin/install.sh`.
  - Empty-pack boot: `scripts/deploy.sh --restart --client`; server
    `Done`, PexpBot joins, `scripts/mcf.py --client screenshot` renders;
    `python3 -I scripts/recipe_index.py build`. Write a test record
    (`docs/testing/records/<date>-empty-pack-boot.md`), then stop the client.
  - The MCP tools (`mc-server`, `mc-client`) load only in a session started
    after the ports exist; until then use `scripts/mcf.py`.
- [ ] **Charter readings**: pack-designer drafts the charter's
  "Interpretation notes" from the owner's request (a decision record if any
  reading is a real choice). Record the template-default owner decisions
  the charter kept (art pipeline, questbook) as decision records.
- [ ] **Identity**: pack name, short namespace id (lowercase, used for
  KubeJS ids, tags, datapack and custom-mod ids), premise and pillars.
  Write a first `docs/design/vision.md` and decision records. Set `name`
  (and `author` if wanted) in `packwiz/pack.toml`.
- [ ] **Core mod roster**:
  - pack-designer drafts a shortlist with the role each candidate plays.
  - pack-mod-researcher fans out over the shortlist in batches (one mod
    per spawn, at most 4 at once) and writes `docs/research/mods/<slug>.md`.
  - pack-designer curates the roster in `docs/design/mods.md`, with
    integration links per mod.
  - pack-reviewer critiques the roster (design mode).
  - One decision record per mod added or cut.
- [ ] **Roster install**: add the core roster (pinned versions, sides from
  the jar; FTB mods come from CurseForge, see platform.md). The tooling
  expects KubeJS (+ Rhino), FTB Quests (+ Library, Teams) and a recipe
  viewer (EMI and/or JEI) unless the charter says otherwise.
- [ ] **First boot with the roster**: the server reaches `Done` with no
  errors, the headless client joins, and the recipe viewer and the quest
  book open. Write a test record.
- [ ] **Namespace**: record it in AGENTS.md → Conventions and in
  `art/palette.json` → `namespaces`.
- [ ] **Phase review** (`docs/design/reviews/<date>-phase0-exit.md`), then
  tag `v0.1.0`.

## Phase 1 - Design

Goal: a complete, critiqued design and a roadmap that runs through release.

- [ ] Full design docs in `docs/design/` (the set in
  `docs/design/README.md`, adapted to the charter), including the
  play-time ledger and the art direction with its inventory. Formats are
  in the pack-design skill.
- [ ] pack-reviewer design critique of the whole set; resolve blockers and
  majors.
- [ ] Write the rest of this roadmap: the phases from implementation through
  release, each with a goal, items and an exit check, where human
  playtests fit, where the art batches land, and a
  `## Phases 2+ - shared rules` section.
- [ ] **Phase review** (`docs/design/reviews/<date>-phase1-exit.md`).

<!-- Later phases are written by the agents in Phase 1. -->
