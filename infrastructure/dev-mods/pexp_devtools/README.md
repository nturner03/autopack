# pexp_devtools

Dev-only tooling for agent-built modpacks. **Never pack content**: it is
installed into the dev server and the headless client beside MCPFabric,
never into `packwiz/`. It registers no blocks, items, registries or network
payloads, and `displayTest = "IGNORE_ALL_VERSION"` lets a client or server
without it connect (the owner's Prism client never has it).

## Build and install

The update-pack scripts (`infrastructure/dev-server/bin/update-pack.sh`,
`infrastructure/headless-client/bin/update-pack.sh`) rebuild it when its
sources change (`ensure_dev_mods` in `infrastructure/lib/common.sh`) and
install it. By hand:

```sh
scripts/build-custom-mod.sh pexp_devtools --dev --test   # gametests, build, install into both
```

Restart the server or client to load a new build. Gametests run on
NeoForge's GameTestServer, which binds no port. Versions in
`gradle.properties` must match `packwiz/pack.toml`.

## Server: `/pexp dump` (op level 2)

Writes what the server has loaded (after datapacks, KubeJS scripts and every
other reload listener) to `<server dir>/pexp/dump/`, replacing the previous
dump as a whole:

| File | Holds |
|---|---|
| `meta.json` | time, game time, Minecraft version, counts, loaded mods and versions |
| `recipes.json` | `{recipe id: recipe JSON}`, one entry per line, encoded with the game's own codec (same shape as the JSON in mod jars) |
| `tags/{item,block,fluid,entity_type}.json` | `{tag: [member ids]}`, fully resolved (nested tags expanded) |
| `loot.json` | `{loot table id: loot table JSON}`, one entry per line |
| `ids.json` | every registered item, block, fluid and entity type id |

A recipe the codec can't encode (rare; some special recipes) is written with
its `type`, `result` (from `getResultItem`) and `"_pexp_partial": "<error>"`.
The reply is one line: `pexp: dumped N recipes (...) ...` or `pexp: error ...`.

Agents don't call it directly: `python3 -I scripts/recipe_index.py build --live`
runs it through MCPFabric and indexes the result.

## Client: `/studio` (client dist only)

`client/StudioClient` is a second `@Mod` entry point with
`dist = Dist.CLIENT`; the dedicated server never loads it (gametests run on
the server dist and cover only `/pexp dump`; the client side is verified
live, see the spec). Client commands, sent through MCPFabric
(`scripts/mcf.py --client send_chat '{"message":"/studio ping"}'`); each
answers with one system chat line starting `studio: ` (read it with
`get_recent_chat`, or `[CHAT] studio:` in the client log):

| Command | Does |
|---|---|
| `/studio ping` | `studio: ok <version> <W>x<H>` |
| `/studio clean on\|off` | hide or restore HUD, hand, crosshair and chat (`options.hideGui`) |
| `/studio shot <name>` | the frame at the window size, without GUI or hand, to `<gamedir>/studio/<name>.png` |
| `/studio panorama <name> <size>` | six square faces (16-2048 px) to `<gamedir>/studio/<name>/panorama_0..5.png` |

The window size comes from `PEXP_CLIENT_SIZE=WxH` on
`infrastructure/headless-client/bin/launch.sh` (default 1280x720). Captures
are read from real frames (`RenderFrameEvent`), not from vanilla's
`grabPanoramixScreenshot`, which gives broken faces in the headless client.
Spec, design notes, results and usage:
`.claude/skills/pack-art/references/studio.md`.
