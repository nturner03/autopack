# Charter

The owner's goal and rules for this pack. Everything not settled here is the
agents' decision. Agents change this file only to fix a factual error; the
owner's words below are never edited.

<!-- OWNER: fill in "The owner's request" and "Requirements, as rules"
     before the first /pack-orchestrate session, and delete or edit the
     template defaults you don't want (they are marked "template default").
     Delete this comment when done. -->

## The owner's request (verbatim, YYYY-MM-DD)

> <Paste the request that starts this experiment: the kind of pack, its
> theme or premise if you have one, what you care about, what you want to
> see the agents do.>

## Owner decisions

Decisions the owner made in addition to the request. Where they conflict
with it, they take precedence.

- **Platform pinned (template default):** Minecraft **1.21.1** on
  **NeoForge** (21.1.x). Decision record:
  [0001](decisions/0001-platform-minecraft-1.21.1-neoforge.md). Platform
  facts and sources: [knowledge/platform.md](knowledge/platform.md).
- **Web research allowed (template default):** agents and the orchestrator
  may search the web when the information can't be found in the game, the
  jars or the repo. The research order is in
  [knowledge/platform.md](knowledge/platform.md#where-to-find-information-research-order).
- **Agent-made art (template default):** the agents make the pack's own
  textures and UI art themselves (pack-art skill). Blocks and items are
  derived from existing textures, then refined as text grids; signature
  pieces get their own silhouettes rather than recoloured vanilla ones. UI
  art (chapter images, title panorama, menu art) is composed from captures
  taken with the dev-only studio client mod. No image-generation models or
  paid services. Shader shots wait until the owner has judged the vanilla
  look. Record it as a decision in Phase 0.
- **Questbook (template default):** FTB Quests. The tooling
  (`scripts/quests.py`, the ftb-quests skill, `deploy.sh --quests`) is built
  for it.

## Requirements, as rules

<!-- OWNER: turn the request into numbered, checkable rules. Examples from
     an earlier experiment:
     1. Agents decide: mods, story, recipes, quests, balancing.
     2. Story: there is an overall story, and play delivers it.
     3. Curated: each mod earns its place and connects to the others.
     4. Progression: the player always has a clear next goal.
     5. Length: about <N> hours of play.
     Keep the git and budget rules below. -->

1. ...
2. **Git**: agents own the local repo completely. Remotes are the owner's.
3. **Budget**: usage is limited, so spawn subagents deliberately.

## Interpretation notes

How the agents read the rules. The first orchestrator session drafts these
from the request (pack-designer), and they are revised through a decision
record if playtests show a reading was wrong.

- **Git**: commit locally, freely and often. Never push, and never add,
  change or remove remotes.
- **Budget**: quality per token. Follow the budget rules in the
  pack-orchestrate skill.

## Hard constraints

- **Platform**: Minecraft **1.21.1** on **NeoForge 21.1.x** (decision
  0001). Moving between 21.1.x builds is an agent decision; changing the
  Minecraft version or the loader is owner-reserved. MCPFabric, the agents'
  in-game test bridge, supports this platform.
- **The test runtime is shared**: one dev server, one headless client, and
  the four ports in `infrastructure/project.env` (see AGENTS.md → Ports).

## Owner-reserved

Only these go to the owner. Everything else the agents decide.

- **Remote git**: pushing, pulling from remotes, and adding or changing
  remotes, hosting and releases.
- **Spending money**: paid services, assets or mods.
- **Platform changes**: a different Minecraft version or loader.
- **Real-player playtests and taste**: fun, pacing over real hours,
  difficulty feel, visual taste, readability on a normal client, and
  performance on real hardware. Queue these in
  `docs/human-testing/queue.md`.
- **Changes outside this repo**, except a host port inventory the owner
  has pointed the agents at (AGENTS.md → Ports), which they keep accurate
  when they claim, change or release a port. Reading the owner's other
  repos is fine; writing to them is not.

## Human gates

Human-only checks are **queued, not blocking**. When work needs the owner:

1. Add a request to `docs/human-testing/queue.md` with the build version,
   exact steps, what to look for, the time needed and the decision it feeds.
2. Keep working on anything that doesn't depend on the answer.
3. End a session for the owner only when the **whole current milestone** is
   blocked on their results. Say so in the session summary and in
   `docs/status.md` under "Waiting on owner".

Never ask the owner to check something an agent can verify: recipes, quest
completion, worldgen presence, crashes, or GUIs through the headless client.
