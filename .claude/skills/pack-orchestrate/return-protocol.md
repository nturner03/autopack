# Subagent return protocol

Every `pack-*` subagent ends its final message with at most 3 lines of plain
summary, then this block. The `SubagentStop` hook
(`.claude/hooks/orch_check_return_block.py`, wired in `.claude/settings.json`)
sends an agent back once if the block is missing or malformed, and logs every
block to `.claude/scratch/<task>/returns/`. Each agent file carries a compact
copy; change them together (`grep -l "STATUS: DONE" .claude/agents/pack-*.md`).

```
STATUS: DONE | NEEDS_INPUT | PARTIAL | FAILED
SUMMARY: <=3 lines
QUESTIONS:            # required for NEEDS_INPUT; non-blocking ones allowed on DONE
  - id: Q1
    q: <question>
    options: [<a>, <b>]
    recommended: <a>
    blocking: true|false
PROGRESS:
  done: [...]
  files_touched: [...]
  checks: ["<command or in-game check> -> pass|fail (<evidence>)"]
  defaults_taken: ["<choice> because <reason>"]
  debt: ["<path:line or topic> <shortcut or follow-up> because <reason>"]
CONTINUATION: <path>  # PARTIAL only
REPORT: <path>        # optional long output
```

| Status | Meaning | Orchestrator action |
|---|---|---|
| `DONE` | The brief's stop condition is met. | Verify (or accept the agent's evidence), feed `PROGRESS` into dependent briefs. |
| `NEEDS_INPUT` | A blocking decision the agent may not make. | The **orchestrator** answers it from the charter, design docs and its own judgment, then `SendMessage`s the answer to the same agent. Only questions the charter reserves for the human go to the human queue. Never respawn. |
| `PARTIAL` | Turns or context ran out (~150k tokens; the budget hook then denies everything but scratch writes), or the brief was bigger than stated. `CONTINUATION` says what is left. | Resume with `SendMessage` if the agent's context is still small; otherwise hand the note to a fresh agent. |
| `FAILED` | Blocked by something other than a decision: broken environment, crash it cannot fix, contradiction in the design. | Investigate (pack-log-triage, a debugger-style brief) before retrying. Never retry blindly. |

## Questions

In this project agents make the decisions. Most choices are not questions:
decide, and record the choice in `defaults_taken` when a reviewer would want
to know. Ask a **blocking** question only when the choice changes something
other briefs depend on (a mod added/removed, a progression gate, a story
fact, a custom-mod interface) and the brief/design docs do not settle it.
**Non-blocking** questions: proceed on `recommended`, record it in
`defaults_taken`; the orchestrator may send a follow-up.

## Debt

`debt` lists shortcuts and follow-ups knowingly left: an unverified claim, a
skipped edge case, a placeholder recipe, a quest that still needs an in-game
check. An empty list is a claim the reviewer checks. The orchestrator carries
open debt into `docs/status.md` or the handoff; nothing is silently lost.

## Hand-back size

The final message is at most 3 lines of summary, then the block. Findings,
tables, logs and explanations go in the `REPORT` file
(`.claude/scratch/<task>/report-<agent>-<n>.md`), never in the message: every
hand-back stays in the orchestrator's context for the rest of the session.
