---
name: kubejs
description: Write and verify KubeJS changes for this pack - recipe adds/removes/replacements, tags and unification, loot tables, item names/tooltips, worldgen data, startup registrations - with the Rhino gotchas, the reload-vs-restart rules, the in-game probe workflow, and the recipe index. Use for any change under packwiz/kubejs/ and whenever a recipe, tag or loot claim must be checked against the live game.
---

# KubeJS

KubeJS is the integration layer: recipes, tags, loot and small content
tweaks live in `packwiz/kubejs/`, one file per topic. Plain datapacks only
for what KubeJS cannot express. Every pack-specific change also gets a row
(with its reason) in `docs/design/integration.md`.

## Layout

| Path | What | Takes effect |
|---|---|---|
| `kubejs/server_scripts/<topic>.js` | `ServerEvents.recipes`, `ServerEvents.tags`, loot events | `/reload` (`scripts/deploy.sh --reload`) |
| `kubejs/startup_scripts/<topic>.js` | item/block registration, item properties | server **restart** and client restart |
| `kubejs/client_scripts/<topic>.js` | tooltips, recipe-viewer hiding, client-only | client restart |
| `kubejs/data/<ns>/...` | datapack JSON (recipes, tags, loot, worldgen, NeoForge data maps, loot modifiers, biome modifiers) | `/reload` for recipes/tags/loot/data maps; worldgen and biome modifiers need a restart **and new chunks** |
| `kubejs/assets/<ns>/lang/en_us.json` | item names, custom lang (story text) | client restart (resource reload) |
| `kubejs/assets/<ns>/textures/**` | textures: **build outputs** of `art/` (pack-art skill); never edit by hand | client restart (resource reload) |

**Startup registrations name their texture.** Every `event.create(...)` for
an item or block chains `.texture('<ns>:item/<name>')` (blocks:
`'<ns>:block/<name>'` or `.textures({...})`). Until pack-artist has made it,
point at a vanilla placeholder that looks close (`minecraft:item/...`) and
list the placeholder in `debt`. `scripts/check_pack.py` (texture lint) fails
on a registration with no `.texture()` or a texture that doesn't exist.

Name pack-owned recipe IDs under the pack's namespace
(`event.shaped(...).id('<packns>:<topic>/<name>')`) so they are greppable
and stable. Pick `<packns>` once (the pack's short id) and record it in
`AGENTS.md` → Conventions.

## 1.21.1 data rules (NeoForge 21.1)

Details and sources are in `docs/knowledge/platform.md` → Facts. In short:

- **Singular folders**: `data/<ns>/recipe/`, `loot_table/`, `tags/item/`,
  `tags/block/`, `tags/fluid/`, `tags/entity_type/`, `advancement/`,
  `structure/`. A plural folder (`recipes/`, `tags/items/`) loads nothing
  and logs nothing.
- **Recipe JSON**: `"result": {"id": "<item>", "count": n}` (not `item`);
  item data is **components** (`"components": {...}`), not `nbt`.
- **Tags**: use `c:` common tags (`#c:ingots/iron`, `#c:ores/tin`,
  `#c:storage_blocks/copper`); there are no `forge:` tags. `c:plates/*` and
  `c:gears/*` exist only if mods add them, so check with
  `recipe_index.py tag`. Hide unified duplicates by adding them to
  `c:hidden_from_recipe_viewers` (item tag), which EMI and JEI respect.
- **Disable a mod's data file** (recipe, advancement) with a file at the same
  path containing only `{"neoforge:conditions":[{"type":"neoforge:false"}]}`.
  `ServerEvents.recipes` `event.remove({id: ...})` is the script
  alternative.
- **Loot**: KubeJS edits through LootJS (a separate mod; add it only if
  loot work needs it) or NeoForge global loot modifiers:
  `data/neoforge/loot_modifiers/global_loot_modifiers.json` lists
  `data/<ns>/loot_modifiers/*.json`; `neoforge:add_table` rolls an extra
  table.
- **Fuel, compost and oxidation** are NeoForge data maps, for example
  `data/neoforge/data_maps/item/furnace_fuels.json` with
  `{"values": {"<item>": {"burn_time": 200}}}`.
- **Ore and feature placement**: biome modifiers at
  `data/<ns>/neoforge/biome_modifier/*.json` (`neoforge:add_features`,
  `neoforge:remove_features`), plus the `worldgen/configured_feature` and
  `placed_feature` JSON.
- Pack format for any `pack.mcmeta`: data 48, resource 34.

Sources: the KubeJS wiki <https://kubejs.com/wiki> (check that a page is for
KubeJS 7 / 1.21); Misode generators set to 1.21.1 <https://misode.github.io/>;
the NeoForge 1.21.1 docs on
[conditions](https://docs.neoforged.net/docs/1.21.1/resources/server/conditions),
[GLM](https://docs.neoforged.net/docs/1.21.1/resources/server/loottables/glm),
[data maps](https://docs.neoforged.net/docs/1.21.1/resources/server/datamaps/builtin)
and [biome modifiers](https://docs.neoforged.net/docs/1.21.1/worldgen/biomemodifier).
When an API or schema question isn't answered by the jar, the wiki or a
probe, search the web (KubeJS issue tracker, mod wikis). Then verify the
answer in game.

## Before writing

1. Get IDs from the installed jars, never memory:
   `python3 -I scripts/recipe_index.py build` (after the server install
   changes), then `makes <item>`, `uses <item>`, `types <modns>`,
   `show <recipe-id>`, `tag <tag>`, `tags-of <item>`, `loot <text>`.
   A plain `build` is STATIC (the jars' JSON plus `kubejs/data`): it does
   not see what KubeJS scripts changed. After a deploy, `build --live`
   indexes the loaded game instead (`/pexp dump` through MCPFabric; needs
   the dev server running), so the same queries show the post-script
   truth. `recipe_index.py status` says which one you have. Check
   `packwiz/kubejs/` (`grep -rn`) too.
2. For a mod's machine recipe type, read one of its shipped recipes
   (`recipe_index.py show <id>`) and mirror that JSON with `event.custom({...})`
   when KubeJS has no native schema for it (true of many addons; Create's
   native functions have been unreliable on 1.21.1, prefer JSON there).
3. Check the KubeJS version in the pack (`packwiz/mods/kubejs*.pw.toml`) and
   use that version's API (KubeJS 7 = `2101.7.x` on MC 1.21.1). When unsure
   of an API, read the KubeJS jar or the official wiki for that version
   rather than guessing.

## Rhino gotchas (KubeJS 2101.7 / Rhino 2101.2, verified on earlier packs)

- No `Array.prototype.flat`; build arrays with loops/`concat`.
- A `const` declared **inside a loop body** keeps its first-iteration value:
  use `let` inside loop bodies (loop-head `for (const x of xs)` is fine).
- `getClass()` is hidden; `Ingredient.getItems()` is hidden (use the
  wrapper's `itemIds`).
- `BlockState.setValue` needs a boxed Boolean:
  `Java.loadClass('java.lang.Boolean').valueOf(b)`.
- `level.getGameTime()` does not resolve on `ServerLevel` from Rhino.
- Errors in one script file do not stop others; always read the log.
Add newly found quirks to `docs/knowledge/gotchas.md`.

## Deploy and read the result

```sh
scripts/deploy.sh --reload      # server scripts / data
scripts/deploy.sh --restart     # startup scripts, configs, mods, worldgen
```

Then read `infrastructure/dev-server/server/logs/kubejs/server.log` (and
`startup.log` after a restart): count of scripts loaded, **0 errors**. Grep
for your file name. `/reload` reads the server's *installed* copy, which is
why deploy.sh updates the pack first. The deploy ends with the regression
checks (`tests/checks/`): a FAIL means the change undid something verified
earlier (a removed recipe is back, a gate has a new bypass, a KubeJS ERROR
line). Once a recipe/tag/loot change is verified, add checks for it
(`recipe_absent`, `only_makers`, `tag_contains`, ...; `tests/README.md`).

## Verify in game (probe workflow)

Static JSON is not proof. For progression-critical changes, prove the
loaded state:

- **Recipe present/absent, bypasses, tags after scripts**: first choice is
  the live index: `scripts/deploy.sh --reload` (or `--restart`), then
  `python3 -I scripts/recipe_index.py build --live`, then `makes <item>`
  (every recipe that outputs it, after scripts), `show <id>`, `tag <tag>`.
  It covers every loaded recipe whose codec can encode it; a recipe the
  dump marks `_pexp_partial` has only its type and result, so check its
  inputs with a probe. For anything else (behaviour, a value computed at
  runtime) write a probe:
- **Probe**: a throwaway server script that inspects
  `event.server.getRecipeManager()` after load and logs with a unique
  prefix. Template:

```js
// PROBE <name>: repo copy lives in .claude/scratch/<task>/; copy to
// infrastructure/dev-server/server/kubejs/server_scripts/, /reload,
// grep logs/kubejs/server.log for "PROBE-<NAME>", then DELETE it and /reload.
ServerEvents.loaded(event => {
  const log = m => console.info(`PROBE-NAME ${m}`)
  const access = event.server.registryAccess()
  let hits = 0
  event.server.getRecipeManager().getRecipes().forEach(holder => {
    let out
    try { out = holder.value().getResultItem(access) } catch (e) { return }
    if (out && !out.isEmpty() && String(out.getItem().builtInRegistryHolder().key().location()) === 'minecraft:piston') {
      hits++
      log(`${holder.id()} type=${holder.value().getType()}`)
    }
  })
  log(`done hits=${hits}`)
})
```

  Probes go directly into the **server's** `kubejs/server_scripts/` (not
  `packwiz/`), so they never ship. Always delete them afterwards and
  confirm with a second reload. A recipe scan may log harmless
  `RuntimeDistCleaner` errors on a dedicated server.
- **Craftability end to end**: via mc-server tools, `give_item` the inputs
  to PexpBot, then on the client open the crafting grid / machine and use
  EMI's recipe view (screenshot) - or for machines, place the machine with
  `set_block`, insert items with `run_command "item replace block ..."` /
  `data merge`, wait, and read the output slot. Known quirk: multiblocks
  don't notice fluids inserted with `data modify` until their shape is
  re-checked; belts placed one `setblock` at a time break, so place them
  in one tick from a temporary datapack function.
- **EMI/JEI view**: headless client screenshot of the recipe page
  (pack-tester).
- **Loot**: `run_command "loot spawn ~ ~ ~ loot <table>"` a few times, then
  `query_entities` for item entities nearby, or `/loot give PexpBot loot`.
- **Tags**: `run_command "execute if items entity PexpBot weapon.mainhand #<tag>"`
  after `give_item`, or a probe.

## Unification

Pick one canonical item per material (ingot, dust, plate, gear, nugget) and
make every producer output it (`event.replaceOutput`), keep inputs on tags
(`#c:ingots/copper`), and hide the duplicates in the recipe viewer. Record
the canonical choice per material in `docs/design/integration.md`.
