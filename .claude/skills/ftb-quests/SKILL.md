---
name: ftb-quests
description: Write, edit, lay out and review FTB Quests chapters directly as SNBT (text, tasks, rewards, dependencies, positions, shapes), then validate, render a layout preview, deploy, and check the real quest book through the headless client. Use for any change under packwiz/config/ftbquests/quests/, when planning a chapter, and when reconciling quest files edited in game.
---

# ftb-quests

Quests are SNBT files in `packwiz/config/ftbquests/quests/`. Agents write
them directly; the in-game editor is optional.

Helper: `python3 -I scripts/quests.py` (from the repo root):

| Command | Use |
|---|---|
| `ids N` | N new IDs, in range and unused. **The only way to get IDs.** |
| `check` | Parse every file; IDs, lang keys, deps, cycles, overlaps, text. Exit 1 on errors. |
| `outline [chapter]` | Text summary: positions, deps, tasks, text length. Read before editing. |
| `render <chapter> <out.png>` | Layout preview PNG (Pillow is installed). Read the PNG and look at it. |

`--root DIR` points any command at another copy, e.g. the dev server's
`infrastructure/dev-server/server/config/ftbquests/quests`.

The field-by-field format, task and reward types and text markup are in
[references/format.md](references/format.md). It was verified for FTB Quests
`2101.1.37` (MC 1.21.1); if the pack pins another line, re-verify it first
(procedure in that file) and update `FILE_VERSION`/type sets in
`scripts/quests.py`. Read it before writing anything beyond checkmark and
item tasks.

FTB Quests, FTB Library and FTB Teams for 1.21.1 NeoForge come from
**CurseForge** (projects 289412, 404465, 404468; see
`docs/knowledge/platform.md`). 2101.1.37 was the newest FTB Quests build on
2026-10-30. Pin it unless a newer 2101.1.x fixes something you need, and
re-verify the format reference if you move. Official docs:
<https://go.ftb.team/docs>. Item references in tasks and rewards use 1.21
component syntax, not NBT. When the reference, the jar and the docs don't
answer a format question, search the web (FTB issue tracker), then confirm
in game.

## Hard rules

1. **IDs: 16 uppercase hex digits starting `0`-`7`.** FTB Quests parses IDs
   with `Long.parseLong(id, 16)`; `8000...` and above fail, get a random new
   ID on every load, and silently lose lang text and dependencies. Get IDs
   only from `quests.py ids`.
2. **Never change an existing ID** once a build with it was handed to the
   owner: team progress is keyed by ID.
3. **All player-facing text goes in `lang/en_us.snbt`**:
   `chapter.<ID>.title`, `chapter.<ID>.chapter_subtitle` (list),
   `quest.<ID>.title`, `quest.<ID>.quest_subtitle`, `quest.<ID>.quest_desc`
   (list, one string per line, `""` for a blank line); optional
   `task.<ID>.title`, `reward.<ID>.title`. No inline `title`/`subtitle`/
   `description` in chapter files. Keep the lang file's sorted key order.
4. **Every fact is verified.** Item IDs, recipes, numbers and mechanics come
   from the installed jars (`scripts/recipe_index.py`, `unzip -l`/`unzip -p`
   on `infrastructure/dev-server/server/mods/*.jar`), the pack's KubeJS
   scripts (which override jar recipes), then the mod's official docs for the
   pinned version, then an in-game test. A chapter is not done until
   `pack-quest-fact-checker` has passed it. A wrong tutorial is worse than none.
5. **Teach what the player needs.** Assume vanilla knowledge. Explain each
   mod's core loop the first time it matters, and every pack-specific
   change, gate and route (these are what players can't look up). Follow the
   structure and voice in `docs/design/quests.md`.
6. **Rewards** follow the reward policy in `docs/design/quests.md`: speed up,
   never skip a gate or replace the production system a quest introduces.
   `consume_items: true` only for deliberate delivery quests.
7. Keep `data.snbt` at the format version the pinned FTB Quests writes.
   Never hand-edit `index.toml`.

## Workflow

1. **Read.** The chapter's section in `docs/design/quests.md`, the relevant
   progression/story sections, and `quests.py outline` of neighbouring
   chapters. Render one finished chapter to match the house style.
2. **Plan on paper first.** Quest list (title, subtitle, task, what it
   teaches, dependencies), then a grid sketch, before any SNBT.
3. **Write.** `ids N` with N = chapter + quests + tasks + rewards. New
   chapter: `chapters/<filename>.snbt`, `filename` equal to the file stem,
   the right `group`, and the next `order_index` *within that group*
   (0-based per group; book-wide numbering drifts when FTB Quests re-saves).
4. **Check.** `quests.py check` reports 0 errors; read the warnings.
5. **Look.** `quests.py render <chapter> .claude/scratch/<task>/<chapter>.png`,
   Read the PNG, fix crowding/crossed lines/strays, re-render.
6. **Deploy.** `scripts/deploy.sh --quests` (updates the server copy and runs
   `ftbquests reload quests`, which reloads definitions only; never plain
   `reload team_progress`). Check the log line `Loaded N chapters` and no FTB
   Quests errors.
7. **See it for real** (pack-tester or you, if you own the runtime): with the
   headless client joined (`scripts/deploy.sh --quests --client` or
   `infrastructure/headless-client/bin/launch.sh --join`), open the book
   (the FTB Quests keybind or the book item; `get_ui`/`click_widget` via the
   mc-client tools), open the chapter, `screenshot`, and look: text fits,
   colours render, icons resolve (no missing-texture squares), lines read
   well. Complete one or two quests for real (`give_item` to PexpBot via
   mc-server, or a checkmark click) to prove tasks detect.
8. **Ship.** `scripts/check_pack.py`; the orchestrator commits chapter,
   lang, `index.toml`, `pack.toml` together.

## Layout

Grid: `x` grows right, `y` grows **down**; a size-1 quest is ~1 cell.
- Flow left to right. The first quest sits at `(0, 0)`, `shape: "hexagon"`,
  `size: 1.5d`, the only quest that size. Main path along `y = 0`.
- 2 cells between main-path steps; branches at `y = +-2`; two siblings
  sharing a parent at `y = +-1`. Whole or half cells only; never closer than
  1 cell (`check` warns).
- Optional side quests: `optional: true`, off the main line, fanned below
  their parent.
- One shape = one meaning within a chapter (e.g. `gear` for machines,
  `diamond` for story beats); be consistent.
- No crossing lines or lines behind quests: move quests. At most ~3 children
  per quest. `hide_dependency_lines` only for long cross-map links.
- Item tasks show their item; give checkmark quests a topical `icon`, never
  the same icon on neighbours.
- Cross-chapter: prefer a `quest_links` pointer or a `change_page` text link
  over a hard dependency.
- Chapter images (`images: [...]`, a background or illustration on the
  quest map): the picture is pack-artist's (built into
  `kubejs/assets/<packns>/textures/quests/`); you place it (`x`, `y`,
  `width`, `height`, `order` < 0 to sit behind quests, `alpha`). Fields and
  sizes: the pack-art skill § "UI art". `quests.py render` draws the real
  image under the layout and `check` fails on a pack image that doesn't
  exist. Keep quest icons readable over it.

## Text

- Title 1-4 words, Title Case. Subtitle a short phrase (`Optional: ...` for
  optional quests).
- Description: paragraphs of 1-3 sentences separated by `""`; under ~12
  lines per page, `{@pagebreak}` on its own line to split. Lead with why
  (the story or engineering problem), then the what.
- Colour sparingly: `&e` key terms, `&c` warnings, `&7` asides/commands,
  `&l` bold; always close with `&r`. A literal `&` needs a following space.
- Numbers only when verified.

## Drift and in-game edits

The in-game editor (if anyone uses it) saves to the server's copy, and FTB
Quests re-saves files in its own key order. When the server copy differs
from the repo (`diff -r packwiz/config/ftbquests/quests
infrastructure/dev-server/server/config/ftbquests/quests`):
1. `quests.py --root <server copy> check`, diff the meaningful changes.
2. Copy intentional changes back to the repo; reject accidental ones.
3. Check for IDs >= `8000...` and reassigned IDs that dropped lang keys.
4. `check` the repo copy, commit. packwiz-installer only replaces files
   whose hash changed, so an abandoned draft on the server stays there until
   you copy the repo version back.
