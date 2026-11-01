# FTB Quests file format reference

For FTB Quests `2101.1.37` (NeoForge 1.21.1), file `version: 13`. The field
names come from the mod's `writeData` methods (`javap` on the jar), verified on
earlier packs. **If this pack pins a different FTB Quests
line or MC version, re-verify before relying on it** (procedure below) and
update this file. Usage patterns: any existing FTB Quests book for 1.21.1 (a sibling
experiment's `packwiz/config/ftbquests/quests/`, or a published modpack's
`config/ftbquests/quests/`). These are read-only structure references:
learn the format, never copy their text, themes or images (published packs
are usually All Rights Reserved).

Re-check this file after an FTB Quests update: extract the jar and run
`javap -c -p` on `Quest`, `Chapter`, `ChapterImage`, `task/*Task`, and
`reward/*Reward`.

## SNBT syntax

- `{ key: value }` compounds, one entry per line, with no commas between
  lines. `[ … ]` lists. Inline `{ count: 1, id: "minecraft:crafter" }` uses commas.
- Strings are always double-quoted. Keys that contain `:` are quoted
  (`"ftbquests:icon"`).
- Numbers: doubles get `d` (`2.0d`), longs `L`. Ints and booleans are bare.
- Tabs for indentation, LF line endings (`.gitattributes` enforces LF).
- FTB Quests rewrites a file in its own key order when it saves. Match that
  order (alphabetical) so in-game saves produce small diffs.

## Directory

```
config/ftbquests/quests/
  data.snbt              file-wide settings (version 13)
  chapter_groups.snbt    { chapter_groups: [ { id: "…" } … ] }
  chapters/<name>.snbt   one chapter each; `filename` = <name>
  lang/en_us.snbt        all player-facing text
  reward_tables/<id>.snbt   only if random/loot rewards are ever approved
```

Translation key prefixes are `file`, `chapter_group`, `chapter`, `quest`,
`task`, `reward`, `reward_table`, `quest_link`, and `image`. The fields are
`title`, `quest_subtitle`, `quest_desc`, and `chapter_subtitle`. Single
strings are plain values; descriptions and chapter subtitles are lists of
lines.

## data.snbt

`version: 13`. Settings the pack decides once (record them in
`docs/design/quests.md`): `progression_mode` (`"default"`, or `"flexible"`:
tasks can be done before their dependencies). A reasonable start:
`default_consume_items: false`, `default_autoclaim_rewards: "disabled"`,
`default_quest_shape: "circle"`, `grid_scale: 0.5d` (the editor snaps to
half cells), `detection_delay: 20`. Other keys that FTB may add on
save, such as `presets`, `verify_on_load`, and `hide_excluded_quests`, are
harmless defaults.

## Chapter

| Key | Notes |
| --- | --- |
| `id`, `filename`, `group`, `order_index` | `group: ""` = ungrouped; `order_index` sets the sidebar order. |
| `icon` | `{ id: "<item>" }` |
| `default_quest_shape` | `""` = use the file default. |
| `default_quest_size`, `default_min_width` | Optional chapter-wide defaults. |
| `default_hide_dependency_lines` | Usually `false`. |
| `autofocus_id` | Quest the map centres on when opened (optional). |
| `progression_mode` | Overrides the file default for this chapter (avoid). |
| `always_invisible`, `hide_quest_until_deps_visible`, `hide_quest_until_deps_complete`, `hide_quest_details_until_startable`, `hide_text_until_complete` | Visibility defaults. Keep guidance visible; don't use these without a reason. |
| `require_sequential_tasks`, `consume_items`, `default_repeatable_quest` | Leave unset. |
| `quests: [ … ]`, `quest_links: [ … ]`, `images: [ … ]` | Contents. |

## Quest

| Key | Notes |
| --- | --- |
| `id`, `x`, `y` | Position in grid cells; `y` grows down. Use whole or half values. |
| `icon` | Defaults to the first task's icon. |
| `shape` | `circle`, `square`, `rsquare`, `diamond`, `pentagon`, `hexagon`, `octagon`, `heart`, `gear`, `none`. |
| `size` | Default `1.0`. Usual range 0.75–2.0. The house layout (ftb-quests skill) uses 1.5 for the chapter start only. |
| `icon_scale` | Shrinks or enlarges the icon inside the shape. |
| `dependencies` | List of quest IDs (any chapter). |
| `dependency_requirement` | `all_completed` (default), `one_completed`, `all_started`, `one_started`. |
| `min_required_dependencies` | Integer, an alternative to the above. |
| `optional` | `true` = doesn't count toward chapter completion. |
| `hide_dependency_lines`, `hide_dependent_lines` | Line visibility for this quest. |
| `hide_until_deps_visible`, `hide_until_deps_complete`, `invisible`, `invisible_until_tasks`, `hide_text_until_complete`, `hide_details_until_startable`, `hide_lock_icon` | Visibility. |
| `can_repeat`, `repeat_cooldown` | Repeatable quests. Not used here. |
| `min_width` | Minimum width of the quest's text panel. |
| `guide_page`, `disable_recipe_mod` | Optional link and EMI/JEI behaviour. |
| `tasks: [ … ]`, `rewards: [ … ]` | At least one task. |
| `tags` | Free-form list of strings. |

## Tasks (`type`)

Common keys: `id`, `type`, `optional_task` (the task isn't needed to
complete the quest).

| Type | Keys | Notes |
| --- | --- | --- |
| `checkmark` | none | The player ticks it. Use it for reading or explaining. |
| `item` | `item: { id, count[, components] }`, `count` (task total), `consume_items`, `match_components`, `only_from_crafting`, `task_screen_only` | Detected in the inventory. Never consume here. |
| `advancement` | `advancement`, `criterion` | e.g. `minecraft:story/mine_stone`. |
| `kill` | `entity`, `value`, `custom_name`, `nbt_filter` | |
| `dimension` | `dimension` | e.g. `minecraft:the_nether`. |
| `structure` | `structure` | Structure ID or `#tag`. |
| `biome` | `biome` | Biome ID or `#tag`. |
| `location` | `dimension`, `position`, `size`, `ignore_dimension` | |
| `observation` | `observation_type`, `to_observe`, `timer`, `observe_type` | The player looks at a block or entity. |
| `stat` | `stat`, `value` | |
| `xp` | `value`, `points` | |
| `fluid`, `forge_energy`, `interaction`, `gamestage`, `custom` | | Rare. Check the jar before use. |

## Rewards (`type`)

The reward policy is in `docs/design/quests.md`. Common keys: `id`, `type`, `team_reward`,
`auto` (a **string enum**, not a boolean: `"default"`, `"disabled"`,
`"enabled"` (auto-claim), `"no_toast"`, `"invisible"`; `auto: true` is
ignored silently), `exclude_from_claim_all`. Command rewards
(`CommandReward.claim`, 2101.1.37) run from the claiming player's own
command source (`@s`, position and dimension are the player's), with
`permission_level` applied only when > 0; placeholders `{p}`, `{x}`,
`{y}`, `{z}`, `{chapter}`, `{quest}`.

| Type | Keys |
| --- | --- |
| `xp` | `xp` |
| `xp_levels` | `xp_levels` |
| `item` | `item: { id, count }`, `count`, `random_bonus`, `only_one` |
| `choice`, `random`, `all_table`, `loot` | `table_id` (needs `reward_tables/`) |
| `command` | `command`, `permission_level`, `silent`, `feedback_message` |
| `toast` | `description` |
| `advancement`, `currency`, `gamestage`, `custom` | rare |

## Quest links and images

- `quest_links: [ { id, linked_quest, x, y, shape?, size? } ]` places a
  pointer to a quest from another chapter on this map.
- `images: [ { image, x, y, width, height, rotation, alpha?, color?, order?,
  click_action?, dependency?, corner?, text_* … } ]` draws decoration on the
  map. `image` is a texture path such as `minecraft:item/iron_pickaxe` or
  `minecraft:textures/…png`. Pack images are built by pack-artist into
  `kubejs/assets/<packns>/textures/quests/` (pack-art skill).

## Description markup (`quest_desc` lines)

- Formatting codes: `&0`–`&f` colours, `&l` bold, `&o` italic, `&n`
  underline, `&m` strikethrough, `&r` reset.
- `""` = blank line. `{@pagebreak}` as its own line starts a new page.
- Inline image:
  `{image:minecraft:textures/item/diamond.png width:100 height:100 align:center}`.
- A whole line may be a JSON text component (escape the inner quotes):
  - Link to another quest or chapter:
    `"{\"text\":\"Working Storage\",\"underlined\":true,\"clickEvent\":{\"action\":\"change_page\",\"value\":\"057546E497F1BFF9\"}}"`
  - External link: `"action":"open_url"`.
  `quests.py check` verifies that `change_page` targets exist.
- Don't embed `\n` in a line. Use separate list entries.
