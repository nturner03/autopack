---
name: pack-handoff
description: Write a stand-alone handoff for the next orchestrator session (docs/handoffs/NNN-<slug>.md) when a session ends with work remaining - at the context limit, when the owner asks to stop, or when a milestone is blocked on owner playtesting. Updates docs/status.md to point at it.
---

# Session handoff

The next session starts cold with only `docs/status.md`, this handoff and the
repo. Write for that reader: facts and pointers, not narrative.

1. Number: next free `NNN` in `docs/handoffs/` (001, 002, ...). Slug: the
   step it starts, e.g. `014-phase3-create-chapter`.
2. Write the file with exactly these sections:

```markdown
# Handoff NNN: <what the next session starts with>

**Date:** YYYY-MM-DD · **Git:** <short sha> · **Pack version:** <x.y.z> · **Phase:** <n - name>

## Kickoff
/pack-orchestrate continue   <!-- mid-phase; plus any focus the next session needs -->
<!-- At a completed phase boundary use instead:
/pack-orchestrate Begin Phase <n> - <name>. Phase <n-1> is complete (tag v<x.y.z>; handoff docs/handoffs/NNN-...). <first focus>.
Only when every item of the finished phase is ticked, reviewed, committed and tagged.
A phase may span several handoffs. The owner pastes this prompt into a new session;
never start, schedule or chain that session yourself. -->

## State
- Deployed on the dev server: <build / git sha, or "nothing running">
- World: <seed / last reset from docs/testing/world-log.md>
- Branch and uncommitted work: <normally "main, clean">

## Done this session
- <item> - <commit sha> - <how verified>

## In progress
- <item>: <exact state>; brief `.claude/scratch/<task>/brief-<n>.md`;
  continuation note `<path>` if any. (Scratch is gitignored but stays on disk.)

## Next steps (in order)
1. <step> - <why first>

## Open debt and unverified claims
- <from returns.py debt; anything marked unverified>

## Waiting on the owner
- <queue entries by id + build version, or "nothing">

## Gotchas found this session
- <new lesson; also added to docs/knowledge/gotchas.md if durable>
```

3. Update `docs/status.md` "Last session" and "Next action" to point at the
   handoff, then commit both (`docs(handoff): NNN <slug>`).
4. Keep it under ~120 lines. Link to docs and briefs; don't paste them.
