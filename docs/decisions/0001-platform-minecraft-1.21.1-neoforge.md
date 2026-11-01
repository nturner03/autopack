# 0001: Platform - Minecraft 1.21.1 on NeoForge

**Status:** accepted (owner decision, carried over from the experiment template) · **Date:** 2026-10-30 · **Phase:** 0

## Context
The agents' test bridge, MCPFabric, supports Fabric and NeoForge on MC
1.21.1-1.21.11 and 26.1-26.3. The experiment template's tooling was built
and verified on 1.21.1 NeoForge in an earlier experiment:
`scripts/quests.py` and the FTB Quests format reference (FTB Quests
2101.1.37), the KubeJS 7 / Rhino notes, and the end-to-end runtime test. The
1.21.1 NeoForge line has the most mature mod ecosystem in that range.

## Decision
The owner pinned **Minecraft 1.21.1 with NeoForge 21.1.x** before Phase 0.
The template initialises the pack with NeoForge `21.1.265`. Agents may
move to a newer 21.1.x build, recorded as a new decision after a full
deploy test. Changing the Minecraft version or the
loader is owner-reserved.

## Consequences
- Phase 0 starts at identity and the mod roster; the version comparison is
  skipped.
- Platform facts and sources are kept in `docs/knowledge/platform.md`.
- Java 21 for the game and for custom mods (ModDevGradle).
- Mods without a 1.21.1 NeoForge build are out of scope, and so is anything
  that needs Fabric.

## Alternatives considered
- Leave the choice to the agents: costs a Phase 0 research fan-out that
  would very likely land on the same platform, with a tail risk of picking a
  version the tooling wasn't verified on.
- Newer 1.21.x or 26.x: thinner mod support, and the quest and KubeJS tooling
  would need re-verifying.
