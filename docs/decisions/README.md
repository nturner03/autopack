# Decisions

One short record per consequential decision. Required for the version and
loader, each mod added or cut, the act structure and gates, story canon
changes, balance rules and custom mods. Decisions stand until a new record
supersedes them; never edit an accepted record's Decision section. Instead,
mark it superseded and write a new record.

## Format

File `docs/decisions/NNNN-short-title.md` (4-digit sequence, kebab-case
title), 10-30 lines:

```markdown
# NNNN: <title>

**Status:** accepted | superseded by NNNN · **Date:** YYYY-MM-DD · **Phase:** <n>

## Context
<the problem and the forces at play; cite research reports or test records>

## Decision
<what was decided, specifically>

## Consequences
<what this enables, costs, or rules out; follow-up work>

## Alternatives considered
- <option> - <why not>
```

Add a row to the index below in the same commit.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-platform-minecraft-1.21.1-neoforge.md) | Platform: Minecraft 1.21.1 on NeoForge (owner decision) | accepted | 2026-10-30 |
