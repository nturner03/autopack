# Platform: Minecraft 1.21.1 on NeoForge

The owner set the platform on 2026-10-30 (decision
[0001](../decisions/0001-platform-minecraft-1.21.1-neoforge.md)). This file
holds the platform facts agents keep needing, each with its source, and
where to look up the rest. Facts marked *verified* were checked against the
source named on the date given. When you confirm or disprove one, update
this file.

## Pinned

| Thing | Value | Source |
|---|---|---|
| Minecraft | **1.21.1** (protocol 767, world version 3955) | `version.json` in the 1.21.1 jar |
| Loader | **NeoForge 21.1.x**, currently `21.1.265` (the newest 21.1 build on 2026-10-30) | [NeoForge maven](https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml) |
| Java | 21 (`/usr/lib/jvm/java-21-openjdk-amd64`) | `version.json` (`java_version: 21`) |
| Data pack format | 48 | `version.json` |
| Resource pack format | 34 | `version.json` |
| MCPFabric | `mcpfabric-neoforge-0.8.0+1.21.1.jar`, installed outside the pack | `infrastructure/cache/` |

Moving to a newer NeoForge **21.1.x** build is an agent decision: record it,
reinstall with `install.sh --reinstall` and run a full deploy test. A
different Minecraft version or loader is owner-reserved (see the charter).

Library versions observed on 2026-10-30. These are a starting point for
research, not decisions:

| Mod | Newest 1.21.1 NeoForge build | Where |
|---|---|---|
| KubeJS (KubeJS 7) | `2101.7.2-build.377` | Modrinth `kubejs` |
| Rhino | `2101.2.7-build.85` (release); `2101.2.8` is beta | Modrinth `rhino` |
| LootJS | `1.21.1-3.7.0+neoforge` | Modrinth `lootjs` |
| FTB Quests | `2101.1.37` (the version `scripts/quests.py` and the format reference were verified on) | CurseForge 289412 |
| FTB Library / FTB Teams | 2101.1.x | CurseForge 404465 / 404468 |
| Architectury API | `13.0.11+neoforge` | Modrinth `architectury-api`, CurseForge 419699 |
| EMI | `1.1.24+1.21.1+neoforge` | Modrinth `emi` |
| JEI | 19.x (recent builds tagged beta) | Modrinth `jei` |

## Where to find information (research order)

1. **The installed game.** Jars in `infrastructure/dev-server/server/mods/`
   (`unzip -l` or `unzip -p`), `scripts/recipe_index.py` (recipes, tags and
   loot from the jars), the live server through MCPFabric, and KubeJS probes.
   This is ground truth for what the pack actually does.
2. **The repo.** `packwiz/`, `docs/research/`, `docs/knowledge/`, this file.
3. **Official documentation for the pinned version** (links below).
4. **General web search** (WebSearch, then WebFetch on the best results)
   when 1-3 don't answer it. Good targets include mod issue trackers and
   changelogs, mod wikis, GitHub source at the 1.21.1 branch or tag, and
   Modrinth or CurseForge pages. Forum or Reddit answers count only as hints.
   Rules:
   - Prefer primary sources: official docs, source code, or the mod author.
     Check the page is about **1.21.1 / NeoForge**: answers for Forge 1.20.1
     or Fabric are often wrong here, especially for paths, tags and
     component syntax.
   - Cite the URL and the date you read it in your report or doc.
   - A web claim about behaviour stays **unverified** until the jar, the
     recipe index or the game confirms it.
   - Never run downloaded code. Jars are inspected with `unzip` in a new
     scratch directory only.

### Sources

**NeoForge**
- Docs for 1.21.1: <https://docs.neoforged.net/docs/1.21.1/gettingstarted/>.
  Pages used most:
  - [Data maps](https://docs.neoforged.net/docs/1.21.1/resources/server/datamaps/builtin)
  - [Global loot modifiers](https://docs.neoforged.net/docs/1.21.1/resources/server/loottables/glm)
  - [Conditions](https://docs.neoforged.net/docs/1.21.1/resources/server/conditions)
  - [Biome modifiers](https://docs.neoforged.net/docs/1.21.1/worldgen/biomemodifier)
  - [Recipes](https://docs.neoforged.net/docs/1.21.1/resources/server/recipes/)
  - [Tags](https://docs.neoforged.net/docs/1.21.1/resources/server/tags)
  - [Configs](https://docs.neoforged.net/docs/1.21.1/misc/config)
  - [Game tests](https://docs.neoforged.net/docs/1.21.1/misc/gametest)
  - [Data components](https://docs.neoforged.net/docs/1.21.1/items/datacomponents)
  - [Capabilities](https://docs.neoforged.net/docs/1.21.1/inventories/capabilities)
  - [Networking](https://docs.neoforged.net/docs/1.21.1/networking/)
  - [Sides](https://docs.neoforged.net/docs/1.21.1/concepts/sides)
- Porting primers (what changed from 1.20.x):
  - [1.20.5/6](https://github.com/neoforged/.github/blob/main/primers/1.20.5/index.md)
  - [1.21](https://github.com/neoforged/.github/blob/main/primers/1.21/index.md)
- **Local decompiled source** for exactly MC 1.21.1 + NeoForge 21.1.265,
  with Parchment parameter names (5,168 Minecraft and 956 NeoForge files):
  `infrastructure/dev-mods/pexp_devtools/build/moddev/artifacts/neoforge-21.1.265-sources.jar`
  (written by the first `pexp_devtools` build during the dev-server install; read-only; a custom-mod project here generates its own copy under
  `build/moddev/artifacts/` on its first Gradle build). Search it with
  `unzip -l <jar> | grep -i <name>` and read a file with `unzip -p <jar> <path>`.
  It's the quickest ground truth for vanilla and NeoForge class and method
  names. See the custom-mod-dev skill.
- Source at 1.21.1: <https://github.com/neoforged/NeoForge/tree/1.21.1>.
  - Common tags: [`Tags.java`](https://github.com/neoforged/NeoForge/blob/1.21.1/src/main/java/net/neoforged/neoforge/common/Tags.java)
    and the [generated `c` tag JSON](https://github.com/neoforged/NeoForge/tree/1.21.1/src/generated/resources/data/c/tags).
  - FML (config loading) is in [FancyModLoader `1.21.1`](https://github.com/neoforged/FancyModLoader/tree/1.21.1).
- Releases and versions:
  - [Version list](https://projects.neoforged.net/neoforged/neoforge)
  - [21.0 release notes](https://neoforged.net/news/21.0release/)
- Modding toolchain:
  - [ModDevGradle](https://github.com/neoforged/ModDevGradle)
  - [MDK for 1.21.1 with ModDevGradle](https://github.com/NeoForgeMDKs/MDK-1.21.1-ModDevGradle)
  - [Parchment mappings](https://parchmentmc.org/docs/getting-started)

**Vanilla 1.21.1 data and commands**
- Minecraft Wiki:
  - Version pages: [1.21](https://minecraft.wiki/w/Java_Edition_1.21), [1.21.1](https://minecraft.wiki/w/Java_Edition_1.21.1)
  - [Data pack](https://minecraft.wiki/w/Data_pack)
  - [Recipe](https://minecraft.wiki/w/Recipe)
  - [Loot table](https://minecraft.wiki/w/Loot_table)
  - [Tag](https://minecraft.wiki/w/Tag)
  - [Data component format](https://minecraft.wiki/w/Data_component_format)
  - [Pack format](https://minecraft.wiki/w/Pack_format)
  - Set the wiki's version notes to Java 1.21.1.
- Misode's generators, with the version picker set to 1.21.1 (recipes, loot
  tables, worldgen, predicates): <https://misode.github.io/>
- Misode's per-version changelog of data-format changes: <https://misode.github.io/versions/>

**Pack tooling and mods**
- packwiz: <https://packwiz.infra.link/>.
  packwiz-installer: <https://packwiz.infra.link/tutorials/installing/packwiz-installer/>
- Modrinth:
  - Filtered search: <https://modrinth.com/mods?g=categories:neoforge&v=1.21.1>
  - [API](https://docs.modrinth.com/api/), e.g.
    `https://api.modrinth.com/v2/project/<slug>/version?loaders=["neoforge"]&game_versions=["1.21.1"]`
- CurseForge project files without an API key: `https://api.cfwidget.com/<project-id>`
- KubeJS wiki: <https://kubejs.com/wiki> (check that a page applies to KubeJS 7 / 1.21).
  LootJS: <https://modrinth.com/mod/lootjs>
- FTB docs (Quests, Library, Teams): <https://go.ftb.team/docs>
- EMI: <https://github.com/emilyploszaj/emi/wiki>. Create: <https://wiki.createmod.net/>
- Other mods: each mod's own wiki, issue tracker and changelog, linked from
  its Modrinth or CurseForge page.

## Facts

### Data and datapack layout (1.21)

- **Folder names are singular** since 1.21: `tags/item`, `tags/block`,
  `tags/fluid`, `tags/entity_type`, `tags/game_event`, `recipe`,
  `loot_table`, `advancement`, `structure`. Files under the old plural
  folders (`recipes/`, `tags/items/`, `loot_tables/`) **load silently as
  nothing**. Verified: [1.21 primer](https://github.com/neoforged/.github/blob/main/primers/1.21/index.md)
  "Depluralizing Registry and Tag Folders".
- **Recipe results use `id`**, not `item`:
  `"result": {"id": "minecraft:iron_pickaxe", "count": 1}`. Ingredients are
  still `{"item": ...}` or `{"tag": ...}`. Verified: NeoForge
  [built-in recipes](https://docs.neoforged.net/docs/1.21.1/resources/server/recipes/builtin).
- **Item NBT is replaced by data components** (since 1.20.5). In commands,
  components go in brackets:
  `/give @s minecraft:diamond_sword[minecraft:enchantments={levels:{"minecraft:sharpness":5}}]`.
  Arbitrary data goes in `minecraft:custom_data`. Recipe outputs and loot
  functions carry `components`, not `nbt`. See the
  [data component format](https://minecraft.wiki/w/Data_component_format).
  Item tests in commands: `execute if items entity <who> <slot> <item_predicate>`.
- **Enchantments are data-driven** (`data/<ns>/enchantment/`), a datapack
  registry. Verified: 1.21 primer "The Enchantment Datapack Object".
- Pack formats: data **48**, resource **34**. Verified from the jar.

### NeoForge data features (no code needed; KubeJS `kubejs/data/` or a datapack)

- **Conditions.** A root `"neoforge:conditions": [ ... ]` on most data files.
  Types: `neoforge:mod_loaded`, `item_exists`, `tag_empty`, `and`, `or`,
  `not`, `true` and `false`. A file containing only
  `{"neoforge:conditions":[{"type":"neoforge:false"}]}` at the same path as a
  mod's file **cleanly disables** that recipe or advancement without log
  spam. Loot tables whose conditions fail become empty tables. Verified:
  [conditions](https://docs.neoforged.net/docs/1.21.1/resources/server/conditions).
- **Global loot modifiers (GLM).** List them in
  `data/neoforge/loot_modifiers/global_loot_modifiers.json` as
  `{"replace": false, "entries": ["<ns>:<name>"]}`, and put each modifier in
  `data/<ns>/loot_modifiers/<name>.json`. The built-in `neoforge:add_table`
  rolls an extra loot table, for example
  `{"type":"neoforge:add_table","conditions":[...],"table":"<ns>:chests/extra"}`.
  For conditional loot edits in scripts, LootJS is the KubeJS route. Verified:
  [GLM](https://docs.neoforged.net/docs/1.21.1/resources/server/loottables/glm).
- **Biome modifiers.** Put them at `data/<ns>/neoforge/biome_modifier/<name>.json`.
  Types: `neoforge:add_features`, `remove_features`, `add_spawns`,
  `remove_spawns`, `add_carvers`, `remove_carvers`, `add_spawn_costs`,
  `remove_spawn_costs` and `none`. This is how ores and features are
  added to or removed from biomes. They apply to new chunks only. Verified:
  [biome modifiers](https://docs.neoforged.net/docs/1.21.1/worldgen/biomemodifier).
- **Data maps.** Put them at `data/<map ns>/data_maps/<registry>/<map>.json`.
  The built-in ones live under `data/neoforge/data_maps/`:
  - `item/furnace_fuels.json`: `{"values": {"minecraft:stick": {"burn_time": 100}}}`
  - `item/compostables.json`
  - `block/oxidizables.json` and `block/waxables.json`
  - `entity_type/monster_room_mobs.json` and `entity_type/parrot_imitations.json`
  - `villager_profession/raid_hero_gifts.json`
  - `game_event/vibration_frequencies.json`

  Entries can use `#tags`, `"replace": true` and a top-level `"remove": [...]`.
  Verified: [data maps](https://docs.neoforged.net/docs/1.21.1/resources/server/datamaps/).
- **Custom ingredient types:** `neoforge:compound`, `neoforge:components`
  (match items with given components), `neoforge:difference`,
  `neoforge:intersection` and `neoforge:block_tag`. Verified: `NeoForgeMod.java`
  at the 1.21.1 branch.

### Common tags (`c:`)

- NeoForge 1.21 uses the shared **`c:`** namespace; `forge:` tags are gone.
  NeoForge's functional tags use `neoforge:`, for example
  `neoforge:needs_wood_tool`.
- Material families: `c:ingots/<m>`, `c:nuggets/<m>`, `c:raw_materials/<m>`,
  `c:storage_blocks/<m>`, `c:ores/<m>`, `c:dusts/<m>`, `c:gems/<m>` and
  `c:rods/<m>`, each also with a bare parent tag (`c:ingots`).
- Ore metadata: `c:ore_rates/{sparse,singular,dense}` and
  `c:ores_in_ground/{stone,deepslate,netherrack}`.
- **`c:hidden_from_recipe_viewers`** exists for items, blocks and fluids.
  EMI and JEI hide what it contains, which is the clean way to hide unified
  duplicates.
- NeoForge itself defines **no** `c:plates` or `c:gears`. Mods use
  `c:plates/<m>` and `c:gears/<m>` by convention, but check each mod's jar
  for what it actually tags.
- Verified: [`Tags.java`](https://github.com/neoforged/NeoForge/blob/1.21.1/src/main/java/net/neoforged/neoforge/common/Tags.java)
  at the 1.21.1 branch.

### Configs

- File types: `<modid>-client.toml`, `-common.toml`, `-server.toml` and
  `-startup.toml`, all in `config/`.
- **SERVER configs load from `config/<modid>-server.toml`** for every world.
  A per-world override can go in `<world>/serverconfig/<same file name>`.
  Server configs are synced to clients.
- `defaultconfigs/<file>` is only a **seed**, copied when the config file
  doesn't exist yet. So **ship pack configs in `config/`**, server configs
  included. Shipping them in `defaultconfigs/` changes nothing once the file
  exists.
- A shipped config that is missing keys, or has values that fail
  validation, is backed up and **rewritten ("corrected")** when it loads.
  Ship complete files generated by the mod version you pin, then edit
  values.
- Verified:
  - FML [`ConfigTracker`](https://github.com/neoforged/FancyModLoader/blob/1.21.1/loader/src/main/java/net/neoforged/fml/config/ConfigTracker.java)
    and NeoForge `ServerLifecycleHooks` (1.21.1 branches)
  - [Config docs](https://docs.neoforged.net/docs/1.21.1/misc/config)

### Mods and distribution

- Mod metadata lives at **`META-INF/neoforge.mods.toml`**; older
  `META-INF/mods.toml` is Forge or pre-20.5. Dependencies are listed there with
  version ranges. Bundled libraries are in `META-INF/jarjar/`.
- Payload registration, used to decide whether a mod must be on both sides:
  `RegisterPayloadHandlersEvent`, `PayloadRegistrar`, `CustomPacketPayload`.
- **FTB mods for 1.21.1 NeoForge are on CurseForge**, not Modrinth: FTB
  Quests 289412, FTB Library 404465, FTB Teams 404468. `scripts/mod_info.py`
  only covers Modrinth.
  - List CurseForge files with `curl -s https://api.cfwidget.com/<project-id>`
    and filter on `versions` containing `1.21.1` and `NeoForge`.
  - Add a file with `packwiz curseforge add --addon-id <project-id> --file-id <file-id> -y`.
  - The metafile gets `mode = "metadata:curseforge"`; packwiz-installer
    resolves the download at install time. This has worked on earlier packs.
- KubeJS 7 (`2101.7.x`) pairs with Rhino `2101.2.x`. KubeJS for 1.21.1 is
  NeoForge-only.

### Client assets (textures, panorama, chapter images)

Checked 2026-10-30 against the installed jars unless marked otherwise.
Method and tools: the pack-art skill and `scripts/texture.py`.
- **Texture paths are singular**: `assets/<ns>/textures/item/`,
  `textures/block/`. A texture id `<ns>:item/<name>` is the file
  `assets/<ns>/textures/item/<name>.png`. Animation: a vertical
  frame strip plus `<file>.png.mcmeta` (`{"animation": {"frametime": N}}`).
  Resource pack format 34 (above).
- **KubeJS assets** ship from `packwiz/kubejs/assets/<ns>/...` (lang
  already works this way). KubeJS 2101.7.2's item and block builders have
  `.texture(String)`, `.textures(Map)`, `.parentModel(...)` and
  `.modelGenerator(...)`, and the item builder has `.color(index, tint)`
  (javap on the jar). What texture a builder uses when none is given wasn't
  confirmed from the bytecode, so the pack always names one (kubejs skill).
- **Vanilla textures** (605 item textures and all blocks) are in the client
  jar `infrastructure/headless-client/hmc/.minecraft/versions/1.21.1/1.21.1.jar`;
  `texture.py find` searches it and the roster's jars.
- **Title panorama**: six faces `minecraft:textures/gui/title/background/panorama_0..5.png`
  (vanilla order: 0 front, 1 right, 2 back, 3 left, 4 top, 5 bottom) plus
  `panorama_overlay.png`. In the 1.21.1 client jar these PNGs are 69-byte
  stubs; the real faces come from the asset index. An override in
  `kubejs/assets/minecraft/...` should replace them; *unverified until the
  first panorama lands*.
- **Capture hooks in vanilla 1.21.1**: `Minecraft.grabPanoramixScreenshot(File, int, int)`
  is public; `Minecraft.grabHugeScreenshot` exists but is private;
  `net.minecraft.client.Screenshot` has public tiled-writing methods. No
  key binding calls the first two. `grabPanoramixScreenshot` renders
  outside the frame loop and gives broken faces in the headless client
  (gotchas); `/studio panorama` re-implements it on real frames with the
  same face order and orientation.
- **FTB Quests chapter images** (2101.1.37, `dev.ftb.mods.ftbquests.quest.ChapterImage`):
  a chapter's `images` list; field names in the class include `image`,
  `width`, `height`, `rotation`, `alpha`, `color`, `order`, `dependency`,
  `click`, `hover`, `corner`, `position_locked`, `text*`, plus `x`/`y`.
  Image alignment values are `left`/`center`/`right` since the 1.21 line
  ([releases](https://github.com/FTBTeam/FTB-Quests/releases), read
  2026-10-30). Confirm the SNBT shape against a chapter the mod re-saves.
- **FancyMenu** (title-screen layouts, logos, slideshows) has NeoForge
  1.21.1 builds according to third-party listings (read 2026-10-30,
  *unverified*). Adding it is a roster decision; the panorama override
  above needs no mod.
