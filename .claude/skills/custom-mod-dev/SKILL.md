---
name: custom-mod-dev
description: Build custom Minecraft mods for this pack in custom-mods/<name>/ - when a custom mod is justified, project setup for NeoForge 21.1 / MC 1.21.1 (ModDevGradle), Java/JAVA_HOME rules, gametests, reproducible builds, and shipping the jar into the pack with scripts/build-custom-mod.sh. Use for any work under custom-mods/.
---

# Custom mod development

## When a custom mod is justified

Only when the design needs something no existing mod, KubeJS script or
datapack can do well: a story-critical block/item with behaviour, a bridge
mechanic between two mods, a custom structure processor, a progression
system. Record the decision (`docs/decisions/`) with what was tried first.
Keep each mod small and single-purpose; one mod per concern beats a grab
bag. KubeJS startup scripts can register simple items/blocks: prefer them
for content without behaviour.

## Project setup

One Gradle project per mod: `custom-mods/<name>/` (`<name>` = the mod id,
lowercase, e.g. `custom-mods/pexp_core/`). Match the pack exactly:
MC version, loader and loader version from `packwiz/pack.toml`, and every
dependency at the version pinned in `packwiz/mods/*.pw.toml`.

- **Platform: NeoForge 21.1.x on MC 1.21.1** (owner decision 0001), using
  ModDevGradle (`net.neoforged.moddev`), Parchment mappings and Java
  toolchain 21. Start from the official MDK,
  <https://github.com/NeoForgeMDKs/MDK-1.21.1-ModDevGradle>, not from memory.
  Set `neo_version` to the pack's `[versions] neoforge`.
- A working reference in this repo is `infrastructure/dev-mods/pexp_devtools/`
  (1.21.1 NeoForge, ModDevGradle). Its `build.gradle` shows a `gametest`
  source set and a generated `neoforge.mods.toml`. The MCPFabric checkout
  (`$PEXP_MCPFABRIC_DIR`) is a second reference (multi-loader, read-only).
- Mod metadata is `src/main/resources/META-INF/neoforge.mods.toml`, usually
  generated from `src/main/templates/`. Declare each dependency on another
  pack mod with its version range and `side`.
- 1.21 API changes that trip older examples:
  - `ResourceLocation.fromNamespaceAndPath(ns, path)` replaces
    `new ResourceLocation(...)`.
  - Items carry data components (`DataComponents`, custom
    `DataComponentType`s), not NBT.
  - Enchantments are data-driven.
  - Networking uses `CustomPacketPayload` with `StreamCodec`, registered in
  `RegisterPayloadHandlersEvent`.
  - Capabilities are registered with `RegisterCapabilitiesEvent`.

  Read the [1.20.5](https://github.com/neoforged/.github/blob/main/primers/1.20.5/index.md)
  and [1.21](https://github.com/neoforged/.github/blob/main/primers/1.21/index.md)
  porting primers before borrowing code written for 1.20.1 or older.
- **Vanilla and NeoForge source** (the first place to look up a class, method
  or signature): ModDevGradle writes the decompiled Minecraft 1.21.1 +
  NeoForge source with Parchment parameter names to
  `build/moddev/artifacts/neoforge-<neo_version>-sources.jar`. Your own
  project gets it on its first Gradle build. Until then, read the copy for the
  pinned build at
  `infrastructure/dev-mods/pexp_devtools/build/moddev/artifacts/neoforge-21.1.265-sources.jar`
  (built by the first dev-server install; read-only):
  `unzip -l <jar> | grep -i furnace` to find a file, then
  `unzip -p <jar> net/minecraft/world/level/block/FurnaceBlock.java` to read it.
  Check against this jar rather than relying on memory or Fabric-era
  examples.
- Docs: <https://docs.neoforged.net/docs/1.21.1/gettingstarted/>
  ([game tests](https://docs.neoforged.net/docs/1.21.1/misc/gametest),
  [data components](https://docs.neoforged.net/docs/1.21.1/items/datacomponents),
  [payloads](https://docs.neoforged.net/docs/1.21.1/networking/payload),
  [capabilities](https://docs.neoforged.net/docs/1.21.1/inventories/capabilities),
  [configs](https://docs.neoforged.net/docs/1.21.1/misc/config)), and
  [ModDevGradle](https://github.com/neoforged/ModDevGradle). The NeoForge
  source at the `1.21.1` branch is the final word. When docs and source
  don't answer a question, search the web (NeoForge Discord answers mirrored
  on GitHub, other mods' 1.21.1 source), and treat the answers as hints to
  verify.
- Gradle wrapper committed with `distributionSha256Sum` pinned
  (`gradle/wrapper/gradle-wrapper.jar` is the one tracked jar besides pack
  jars). Host Gradle 9.2 exists at `/opt/gradle/gradle-9.2.0` for
  generating a wrapper.
- `build/`, `run/`, `runs/`, `.gradle/` are gitignored.
- Mod id/namespace: the pack's short id (`AGENTS.md` → Conventions) or a
  clear derivative; group `io.github.pexp.<modid>` unless the design says
  otherwise. License: the project's choice; record it in the mod's README.

## Java

The host's PATH `java` is **1.8**. Always set
`JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64` for Gradle; `scripts/build-custom-mod.sh`
does this from the pack's MC version. Use `--no-daemon` in scripted builds
so stale daemons don't pile up (8 cores, shared with the dev server).

## Tests

- **Gametests** (NeoForge `runGameTestServer`; enable your namespace with
  `neoforge.enabledGameTestNamespaces`) for
  block/item behaviour: put them in a separate `gametest` source set so the
  release jar is `main` only. They boot a headless server with no port.
- Unit tests (JUnit) for pure logic.
- Then integration: ship the jar to the pack (below), deploy, verify with
  pack-tester like any other content, including the client side (does the
  client load it, do textures/lang/GUI render) via the headless client.

## Build and ship

```sh
scripts/build-custom-mod.sh <name> --test   # gametests, build, copy jar to packwiz/mods/, packwiz refresh
python3 -I scripts/check_pack.py            # warns "raw jar shipped" for it: expected
scripts/deploy.sh --restart --client
```

The jar in `packwiz/mods/` is committed (the only jars tracked besides
Gradle wrappers) so `packwiz serve` and file:// installs ship it. Bump the
mod's version for every shipped change; the script replaces the previous
jar. Builds should be reproducible (`preserveFileTimestamps = false`,
`reproducibleFileOrder = true`): building twice gives the same sha256.

## Dev-only tool mods

Some mods are tools for the agents, not pack content. The template ships
one, `pexp_devtools` (`infrastructure/dev-mods/pexp_devtools/`, see its
README): the server command `/pexp dump` behind `recipe_index.py build
--live`, and the client `/studio` capture commands for art
(`.claude/skills/pack-art/references/studio.md`). Dev mods differ from pack
mods:
- Source lives in `infrastructure/dev-mods/<name>/`, not `custom-mods/`.
- Loaded on **both** the dev server and the headless client: client code
  only behind `Dist.CLIENT` checks, no registries or network payloads, and
  `displayTest = "IGNORE_ALL_VERSION"` so the owner's client without it can
  still join.
- Built with `scripts/build-custom-mod.sh <name> --dev`: the jar goes to
  `infrastructure/cache/dev-mods/` and both installs' `mods/`, **never** to
  `packwiz/mods/`, so no `packwiz refresh` and nothing ships. The
  update-pack scripts rebuild it automatically when its sources change
  (`ensure_dev_mods` in `infrastructure/lib/common.sh`) and re-install it.
- Mod id prefix `pexp_` (project infrastructure), not the pack namespace.
- Server-side features get gametests (`--test`); client features are
  accepted in the headless client. The jar isn't tracked (it rebuilds from
  source). A dev mod is template infrastructure: fixes that aren't
  pack-specific belong in the template too (tell the owner).

## Rules

- Server-safe: no client classes reachable from common code; client code
  behind the loader's dist checks / client entrypoint. The dedicated dev
  server boot proves this.
- Network payloads: register both sides; the mod is `side = "both"` (the
  raw jar is indexed as both).
- Data-driven where possible (recipes/tags/loot as JSON in the mod or in
  KubeJS) so balancing doesn't need a rebuild.
- Keep a `README.md` in each mod: purpose, design doc link, blocks/items,
  commands, config.
