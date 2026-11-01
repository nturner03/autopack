# Handoffs

One stand-alone handoff per orchestrator session that ends with work left:
at the context limit, when the owner asks to stop, or when a milestone is
blocked on owner playtests. Files are `NNN-<slug>.md`, numbered in sequence.
The template and rules are in the `pack-handoff` skill
(`.claude/skills/pack-handoff/SKILL.md`). `docs/status.md` → "Last session"
points at the newest one.
