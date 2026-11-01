# Regression checks

Once a claim is verified (a recipe is gone, an item has no bypass, a tag holds
an item, a quest chapter loads), a check here keeps proving it on every
deploy, so a later change can't silently break an earlier gate.

- `checks/<topic>.toml`: the checks, one file per topic (`00-platform.toml`
  ships with the template; add e.g. `10-early-game.toml`, `quests.toml`).
- `log-noise.txt`: ERROR/FATAL log lines confirmed harmless (one regex per
  line), used by `log_clean` and by the pack-log-triage agent.

## Running

```bash
python3 -I scripts/checks.py run                 # one /pexp dump, then every check
python3 -I scripts/checks.py run --only 10-early-game,quests.ch1-loads
python3 -I scripts/checks.py run --no-dump       # reuse the last dump (fast, no server call)
python3 -I scripts/checks.py run --list          # validate the files and list the checks
```

`scripts/deploy.sh` runs the full set after every `--restart`, `--reload` and
`--quests` (`--no-checks` skips it) and exits non-zero when a check fails or
cannot be evaluated. Each run prints `pass|FAIL|skip <id> - <detail>` per
check and writes `docs/local/checks-last.json`.

| Exit | Meaning |
|---|---|
| 0 | every check passed |
| 1 | at least one FAIL |
| 2 | invalid check files (unknown kind, missing or unknown field, bad regex, duplicate id) or usage |
| 3 | nothing failed, but some checks were skipped (no dump, server bridge down, no log since the start) |

`PEXP_CHECKS_DIR=<dir>` points the runner at another set, e.g. a throwaway
pack's own checks when `PEXP_PACK_TOML` swaps the pack (the repo's checks
describe the real pack and would fail against it). `log-noise.txt` is always
the repo's.

## Format

```toml
[[check]]
id = "early.no-iron-pick-bypass"         # unique across all files; letters, digits, . _ : -
why = "docs/design/progression.md#tier-1 (decision 0007)"   # what it protects
kind = "only_makers"
item = "minecraft:iron_pickaxe"
recipes = ["mypack:iron_pickaxe_forged"]
```

`id`, `why` and `kind` are required, plus the kind's fields; anything else is
an error. Ids without a namespace default to `minecraft:` and a leading `#` on
a tag is optional.

| Kind | Fields | Passes when |
|---|---|---|
| `recipe_exists` | `recipe` | the recipe id is loaded |
| `recipe_absent` | `recipe` | the recipe id is not loaded (removed by KubeJS or a datapack) |
| `makes_any` | `item` | at least one loaded recipe outputs the item |
| `only_makers` | `item`, `recipes` | the recipes outputting the item are exactly this list (`[]` = uncraftable): no bypass, and no intended maker lost |
| `tag_contains` | `tag`, `item`, `registry` (`item`) | the resolved tag holds the entry (nested tags expanded) |
| `tag_lacks` | `tag`, `item`, `registry` (`item`) | the resolved tag does not hold it (a missing tag counts as lacking) |
| `loot_mentions` | `table`, `item` | the loaded loot table names the item anywhere |
| `loot_lacks` | `table`, `item` | the loaded loot table exists and does not name the item |
| `item_exists` | `item`, `registry` (`item`) | the id is registered |
| `mod_loaded` | `mod`, `version` (any) | the mod id is loaded (at exactly that version, if given) |
| `log_clean` | `allow` (`[]`) | no ERROR/FATAL lines since the last start in `logs/latest.log` or the KubeJS `server.log` / `startup.log`, other than `log-noise.txt` and `allow` regexes |
| `log_matches` | `pattern`, `log` (`latest`) | a line since the last start matches the regex; `log` is `latest`, `kubejs_server` or `kubejs_startup` |
| `command` | `command`, `expect` | the server command's output matches the regex (run through MCPFabric as op) |

`registry` is `item`, `block`, `fluid` or `entity_type`. All kinds except the
last three read the live dump (pexp_devtools), so they see the game as loaded:
KubeJS script edits, datapacks and resolved tags included. `only_makers` finds
outputs under `result`/`output`-like keys of every recipe type, modded
machines included; check a new machine type once with
`recipe_index.py build --live` + `makes <item>` before relying on it.

Prefer dump kinds over `command`: they are cheap and need no world state.
`command` suits facts only the game can answer, e.g.
`command = "ftbquests ..."`; keep it read-only (no `/give`, no world edits).

## Who adds checks

- **pack-tester:** every verified, progression-critical claim in a test
  record becomes a check (or several) in the same task; the record lists the
  check ids. Claims that need a player (GUI, rendering, feel) stay in the
  record and the human-testing queue.
- **pack-implementer:** runs the set after its own deploys, adds the checks a
  brief's Verification section names, and never edits or deletes another
  check to make a deploy pass. A check that is wrong or obsolete is changed
  by the orchestrator with the design change that made it so.
- **Orchestrator:** a phase review runs the full set; any FAIL is a blocker.
  Briefs list the check ids to add or keep passing.
