# Testing

Agent test evidence. `pack-tester` writes one record per test session. The
ingame-testing skill describes how to test; this file holds the formats.

- `records/YYYY-MM-DD-<topic>.md`: test records (format below).
- `screenshots/`: screenshots worth keeping as evidence for a decision or a
  bug. Keep them few and small. Routine screenshots go to
  `docs/local/screenshots/`, which is gitignored.
- `world-log.md`: dev-world seeds and resets, written by
  `infrastructure/dev-server/bin/install.sh`, `reset-world.sh` and
  `world-log.sh`. It appears after the first server install.

## Record format

```markdown
# <topic> - YYYY-MM-DD
**Build:** pack <version> @ git <sha> · **World:** <seed/reset date> · **By:** pack-tester (brief <task>/<n>)
| Check | Method | Result | Evidence |
|---|---|---|---|
| Steel needs blast furnace | probe PROBE-STEEL, EMI screenshot | pass | log line ...; docs/local/screenshots/... |
**Regression checks added:** `tests/checks/<topic>.toml`: <id>, <id> (all pass; full set: N pass)
**Unverified / follow-ups:** ...
```

Result is `pass`, `fail` or `unverified`. Evidence must let someone check the
claim again: a log line, a command and its output, a screenshot path, or a
probe id. "Looked fine" is not evidence.

Verified claims that a dump, log or command can prove also become
regression checks in `tests/checks/` (see `tests/README.md`), which every
deploy re-runs; the record names the check ids it added.
