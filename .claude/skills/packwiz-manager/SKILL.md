---
name: packwiz-manager
description: Manage the pack in packwiz/ - add/update/remove/pin mods by exact version, classify client/server/both sides from the jar, edit shipped configs, validate metadata and hashes, and roll back. Use for any change to packwiz/pack.toml, index.toml, mods/, config/, defaultconfigs/, kubejs/, resourcepacks/ or .packwizignore, and whenever asked whether the pack is consistent.
---

# packwiz-manager

Drive the packwiz CLI; never reproduce what it does (hashing, index entries,
download metadata) by hand.

| Thing | Value |
|---|---|
| packwiz | `~/go/bin/packwiz` (not on PATH); run it **from `packwiz/`** |
| Pack root | `packwiz/` (`pack.toml`, `index.toml`, `mods/`, `config/`, `kubejs/`, ...) |
| Validate | `python3 -I scripts/check_pack.py` (`--deploy` adds installed-state checks) |
| Platform | Minecraft 1.21.1, NeoForge 21.1.x (owner decision 0001); facts and sources in `docs/knowledge/platform.md` |
| Research (Modrinth) | `python3 -I scripts/mod_info.py <slug> [version-id]` (MC/loader from pack.toml) |
| Research (CurseForge) | `curl -s https://api.cfwidget.com/<project-id>`: files with `versions` containing `1.21.1` and `NeoForge` |
| Deploy | `scripts/deploy.sh --restart|--reload|--quests [--client]` (see the dev-server skill) |

## Pack state

Initialised by the experiment template: `name = "Untitled Pack"` (a
placeholder; Phase 0 sets the real name in `pack.toml`), `version = "0.0.1"`,
`minecraft = "1.21.1"`, `neoforge = "21.1.265"`, no mods. Never run
`packwiz init` again. `mods/` and `config/` appear with the first add.

## Adding a mod

1. **Research first.** `mod_info.py <slug>` lists builds for the pack's
   version/loader with Modrinth deps; `mod_info.py <slug> <version-id>` reads
   the jar's metadata (dependency ranges, jar-in-jar, payload-class hints).
   For several mods, the orchestrator spawns one `pack-mod-researcher` each.
2. **Install by exact ids:**
   `packwiz modrinth add --project-id <id> --version-id <vid> -y`.
   CurseForge only if not on Modrinth:
   `packwiz curseforge add --addon-id <project-id> --file-id <file-id> -y`.
   This is where the **FTB mods** (Quests 289412, Library 404465, Teams
   404468) live for 1.21.1 NeoForge; the metafile gets
   `mode = "metadata:curseforge"`. Never let `-y` pick from search results;
   always pass ids.
3. **Dependencies:** packwiz offers Modrinth required deps. Accept only after
   checking each the same way; if one is already in the pack, confirm its
   pinned version is in range instead of adding a second copy. Libraries
   that another mod already bundles (jar-in-jar) must not be added twice.
4. **Side** (below): set `side` in the new `.pw.toml`; packwiz defaults most
   mods to `both`.
5. `packwiz refresh`, then `python3 -I scripts/check_pack.py`.
6. Record it: roster row in `docs/design/mods.md` (role, pillar, links) and a
   decision record for a content mod. Mark unverified compatibility as such.
7. The orchestrator commits the metafile, `index.toml` and `pack.toml`
   together with the docs.

## Updating / removing

- Update one mod at a time: re-add with the new `--version-id` (this resets
  `side`; set it again) or `packwiz update <name>` when the latest build is
  the one you reviewed. **Never `packwiz update --all`.**
- `packwiz pin <name>` holds a mod; note why in `mods.md`.
- Removal: `packwiz remove <name>`, then remove its recipes/quests/configs/
  KubeJS references (`grep -rn '<modid>:' packwiz/`), refresh, check, and
  record the cut as a decision.
- The Minecraft version and loader are **owner-reserved** (decision 0001).
  Moving to a newer NeoForge 21.1.x build is allowed: change
  `[versions] neoforge`, record a decision, `install.sh --reinstall` on the
  server and client, and run a full deploy test.

## Side classification

Decide from the jar and code, not the Modrinth `client_side` tag:
Metadata is `META-INF/neoforge.mods.toml` (dependency ranges, `side` per
dependency); bundled libraries are in `META-INF/jarjar/`.
- `both`: adds blocks/items/entities/registries, network payloads, recipes,
  worldgen, or has a server half feeding a client half (Jade, AppleSkin).
- `client`: rendering, shaders, minimaps, HUD/UI, sounds, input, client
  performance. A client-only class loaded on a dedicated server crashes it;
  the dev server boot catches this.
- `server`: admin/perf tooling that registers **no** network payloads and no
  content. Inspect the jar for payload registration
  (`RegisterPayloadHandlersEvent`, `PayloadRegistrar`, `CustomPacketPayload`).
- MCPFabric is **not** part of the pack: the infrastructure installs it into
  the dev server and headless client outside packwiz. Do not add it.

## Shipped files

- `config/`: **all** configs, server configs included
  (`<modid>-server.toml`). On NeoForge 21.1, server configs load from
  `config/` for every world; `<world>/serverconfig/` only overrides them.
  `defaultconfigs/` is just a seed, copied when a config file doesn't exist
  yet, so don't ship pack settings there. Ship the **complete** file the
  pinned mod version generates (take it from
  `infrastructure/dev-server/server/config/` after a boot) and change only
  the keys you need. A file with missing or invalid keys is backed up and
  rewritten at load. Record pack-relevant changes in
  `docs/design/integration.md` or `balance.md`.
- `kubejs/`: recipes, tags, loot, item/lang tweaks (see the kubejs skill).
- `config/ftbquests/quests/`: definitions only (see the ftb-quests skill).
  Never ship progress, team data, `local/` or `saves/`.
- Custom mod jars: built by `scripts/build-custom-mod.sh` into
  `packwiz/mods/` (the only jars allowed in git). Never drop other jars in.
- Never ship secrets or per-host state: tokens, `mcpfabric.config.json`,
  ops/whitelists, worlds, player data, personal client options.
- New non-shipping paths go in `packwiz/.packwizignore` **before** refresh.
  Everything not ignored goes to every client and server.

## Validation

```sh
cd packwiz && ~/go/bin/packwiz refresh && cd ..
python3 -I scripts/check_pack.py
git status --short packwiz/
```

`check_pack.py` parses every TOML, checks sides, download hashes, duplicate
filenames, index-to-disk hashes, unindexed files in shipped folders, stray
jars, and repo-only/secret paths leaking into the index. Errors block a
deploy; read the warnings. A diff after `packwiz refresh` that you didn't
expect means something changed unrecorded: inspect it.

## Rollback

`git revert <sha>` (never rewrite history), refresh, check, redeploy. For a
broken world after a bad deploy: `infrastructure/dev-server/bin/restore.sh`
with a backup, or `reset-world.sh` (the dev world is disposable).

## Sources

packwiz docs <https://packwiz.infra.link/>; Modrinth search filtered to the
platform <https://modrinth.com/mods?g=categories:neoforge&v=1.21.1>; more in
`docs/knowledge/platform.md` → Sources. Use web search when a mod's version,
dependency or side question isn't settled by its jar and pages.

## Gotchas

`docs/knowledge/gotchas.md` - especially: re-adding resets `side`; packwiz
can pull a library a mod already bundles; LF line endings only (hashes);
packwiz-installer only replaces files whose hash changed, so a hand-edited
file on the server survives deploys until the pack's copy changes.
