# Brief <n>: <one-line objective>

<!-- Written by the orchestrator to .claude/scratch/<task>/brief-<n>.md.
     The subagent reads this file first. Keep it under ~60 lines: link to
     doc sections, don't paste them. -->

- **Agent:** pack-<role>
- **Tier:** T<n> (<model> <effort>) because <reason>
- **Source:** `docs/<file>.md` § "<exact heading>" — read with
  `python3 -I .claude/scripts/md_section.py <file> "<heading>"`
- **Depends on:** brief <m> (done; summary below) | none

## Objective

<The bounded outcome in one or two sentences, in player terms where possible.>

## Scope

- Files to change: `<path>` (<what>), ... — every file the agent may change.
- Files to read first: `<path>` (<why>)
- Out of scope: <neighbouring work another brief owns>
- Running in parallel: brief <m> (`<its files>`); do not touch them | none

## Decisions already made (do not reopen)

- <decision> (docs/decisions/NNNN-*.md | design doc § | orchestrator, this session)

## Inputs from earlier agents

- <files touched, defaults taken, facts discovered>

## Acceptance

- <observable criteria: "recipe X needs Y in EMI", "quest Q completes on
  picking up Z", "server reaches Done with 0 new ERROR lines">

## Verification

- Static: `python3 -I scripts/check_pack.py`, `python3 -I scripts/quests.py check`, ...
- In game: <what pack-tester (or this agent via scripts/mcf.py) must observe>
- Regression checks to add (`tests/checks/<topic>.toml`, kinds in
  `tests/README.md`): <id - kind - what it proves, e.g. `early.no-iron-pick-bypass`
  - only_makers - iron pickaxe only from the forge recipe>. The full set must
  still pass after the deploy (`scripts/deploy.sh` runs it).

## Stop condition

Return `DONE` when acceptance and verification pass. `NEEDS_INPUT` only for
a blocking decision (see the return protocol). `PARTIAL` with
`.claude/scratch/<task>/continuation-<n>.md` if the work needs files outside
"Files to change", grows past the brief-size gate (~6 files or one new
mechanic), or your context nears 150k tokens.
