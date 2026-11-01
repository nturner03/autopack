---
name: pack-design
description: Design method and quality bar for this modpack - pillars, story delivery, curating an interconnected mod set, progression maps and gating, recipe-integration rules and anti-patterns, the play-time budget, and the design-doc and decision-record formats. Use when designing or critiquing story, mod selection, progression, recipes, balance, or quest structure.
---

# Pack design method

The charter (`docs/charter.md`) is the brief from the owner. This skill is how
to meet it well. It is written for a story-driven, progression-gated pack
with a questbook; where the charter asks for something different (a skyblock,
a kitchen-sink pack, no story), the charter wins: keep the method that still
applies and record the departures as decisions. The platform is fixed: **Minecraft 1.21.1 on NeoForge**
(decision 0001). Candidate mods need a 1.21.1 NeoForge build.

For research: Modrinth filtered to the platform
<https://modrinth.com/mods?g=categories:neoforge&v=1.21.1>, mod wikis, and
general web search for what players say about a mod: its depth, pacing, and
known balance or performance problems. Treat opinions as input, not fact.
Mechanics claims get verified by a researcher (jar) or tester (game). The target player knows vanilla Minecraft, has played a few
modpacks, and wants a coherent journey rather than a pile of content.

## Documents the design lives in

| Doc | Purpose | Owner |
|---|---|---|
| `docs/design/vision.md` | Pitch, pillars (3-5), tone, story premise, what the pack is *not* | pack-designer |
| `docs/design/story.md` | Canon: setting, factions/characters, mysteries and reveals, ending; how each beat is delivered in game | pack-designer |
| `docs/design/mods.md` | The mod roster: each mod's role, which pillar it serves, what it connects to, what was cut and why | pack-designer |
| `docs/design/progression.md` | Tiers/acts, gates between them, the progression graph, the time budget ledger | pack-designer |
| `docs/design/integration.md` | Interconnection matrix: which mod's outputs feed which mod's inputs, and every pack-specific recipe change with its reason | pack-designer, kept current by implementers |
| `docs/design/quests.md` | Questbook structure: chapters, their purpose, story beats, reward policy, house style | pack-designer |
| `docs/design/balance.md` | Numbers: ore rates, machine speeds, costs per tier, reward economy | pack-designer |

Keep each doc scannable: tables and short sections. Anything a later agent
must obey goes in these docs or a decision record, not in chat.

## Pillars and story

- Pillars are testable promises ("every tier needs something from the world
  you haven't seen yet"), not adjectives ("fun", "immersive").
- The story must change what the player *does*: locations to find, artifacts
  that unlock tiers, a reason to go to dimension X before building Y. Lore
  that never touches gameplay is decoration; keep it light.
- Delivery channels, cheapest first: quest text and chapter framing; item
  names/tooltips via KubeJS lang; custom loot (written notes, books via
  Patchouli/lectern loot if the roster has it); structures with placed lore;
  advancements; a custom mod only when no existing mod can carry the beat.
- Every reveal is earned by progression; the ending is a concrete goal the
  player can complete (a final craft, a boss, a structure, a journey).

## Curating the mod set

- Start from the pillars, not from popular mods. For each candidate ask:
  which pillar does it serve, what does it *connect to*, what does it
  duplicate? Two mods that solve the same problem (two pipe systems, two ore
  processors, two magic power systems) need an explicit reason to coexist.
- A mod is "interconnected" when at least one of its key progression items
  needs inputs from another core mod, or its outputs are required by one.
  Target: every core mod has >=2 such links; record them in `integration.md`.
- Prefer mods that are maintained for the chosen MC version, server-safe, and
  KubeJS-friendly (recipe types exposed, or JSON recipes), with sane configs.
- Quality-of-life and performance mods are infrastructure; list them but
  don't count them as content. Recipe viewer (EMI or JEI), FTB Quests and its
  libraries, KubeJS, and a performance baseline are expected.
- Size is a consequence, not a goal. A tight 60-120 mod pack is typical for
  this scope; justify anything far outside.
- Before adding a mod: `pack-mod-researcher` report (version, deps, side,
  conflicts, recipe types, integration hooks). Record the add as a decision.

## Progression

- Organize into 4-7 acts/tiers. Each has: a goal the player understands, new
  capabilities, a gate to the next act, and story beats.
- A gate is a *requirement the player must go and do*: reach a place, defeat
  something, build a working system, combine two mods' outputs. Good gates
  teach the next mod. Bad gates are pure grind (×64 compressed blocks) or
  arbitrary rare items unrelated to the theme.
- Keep a progression graph (Mermaid in `progression.md`): nodes are key
  items/milestones, edges are hard requirements. Check that there are no
  dead ends, every node is reachable, and parallel branches exist inside each
  act (players need choices).
- Exploration and tech alternate and depend on each other: exploration
  yields what tech needs (rare materials, structures, biomes, dimensions);
  tech enables farther exploration (travel, survival gear, detection).
- Early game must be fast and inviting: first hour = shelter, first mod
  interactions, first story hook.

## Recipe integration: rules and anti-patterns

Good changes have a reason a player can see:
- Thematic: the recipe uses what the item is made of or does.
- Bridging: a recipe pulls in another mod's intermediate at the tier where
  the player has it, so both mods matter.
- Pacing: cost moves an item to the act where the design wants it.
- Unification: one canonical material per tag (one copper ingot, one steel),
  with others converted or hidden.

Anti-patterns (the reviewer rejects these):
- Compressed/×9 block spam or nested crafting just to slow players down.
- Requiring a late-game item in an early recipe "for balance".
- Swapping ingredients for another mod's item with no thematic reason.
- Uncraftable or loot-only items on the critical path without a reliable
  source (check `scripts/recipe_index.py` and loot tables).
- Changing so many vanilla recipes that vanilla knowledge stops helping.
- Leaving duplicate machines/ores producing the same thing at different
  costs (exploitable), unless intended and documented.

Every pack-specific recipe change goes in `integration.md` with its reason.

## Time budget

Keep a ledger table in `progression.md`: act | main activities | estimated
hours | basis. Estimate from concrete work: number of crafts and machines,
resource quantities vs. production rates, travel distances, boss
preparation. Target the charter's play time for a typical first playthrough
(a focused player is ~30% faster, a completionist ~40% slower). Re-estimate after balance
changes and owner playtests; owner timing data beats estimates.

## Questbook

FTB Quests is the spine. Chapters follow acts and mods. Quests assume vanilla
knowledge but explain each mod's core loop and every pack-specific change or
route. One quest = one action or concept. Text is short, in the pack's
voice, and never wrong (verified by pack-quest-fact-checker). Rewards
accelerate (useful items, not loot spam) and never skip gates. See the
ftb-quests skill for format.

## Decision records

`docs/decisions/NNNN-short-title.md` (index in `docs/decisions/README.md`):
Status (accepted / superseded by NNNN), Context, Decision, Consequences,
Alternatives considered. Short: 10-30 lines. Required for: the platform (0001, owner-set),
each mod add/cut, act structure and gates, story canon changes, balance
rules, custom mods.

## Design critique checklist (pack-reviewer, design mode)

1. Does every element serve a pillar? Name any that don't.
2. Kitchen-sink check: overlapping mods, mods with <2 integration links.
3. Progression: dead ends, unreachable nodes, grind gates, missing choices.
4. Recipes: any anti-pattern above; any change without a recorded reason.
5. Story: does it drive play; are beats delivered in game; is the ending
   achievable.
6. Time budget: is the ledger grounded; acts wildly unbalanced?
7. Feasibility: can the mod roster and KubeJS actually do this on the chosen
   version (cite the research reports)?
Rate findings blocker / major / minor with a concrete fix for each.
