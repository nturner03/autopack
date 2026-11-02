"""PostToolUse hook that records every orchestrated spawn in ``agents.md``.

The orchestrator needs each agent's ID to ``SendMessage`` it later, even after
a compaction. It used to append the row itself, one Bash call per spawn, and
flip its status with ``sed -i`` on every return. This hook writes the spawn
row instead, and the current status comes from ``returns.py status``, so
``agents.md`` is append-only.

For an Agent call whose ``subagent_type`` starts with ``--prefix``, the task
and brief come from the first ``.claude/scratch/<task>/brief-<n>.md`` path in
the spawn prompt, as ``returns.py`` finds them. The row appended to
``.claude/scratch/<task>/agents.md`` is::

    brief-<n> | <agent type> | <agent ID> | spawned <model>/<effort> T<n>

The agent ID is ``tool_response.agentId``. The model and effort are the
call's own, else the resolved model and the agent file's ``effort:``; the
tier is the brief's ``**Tier:** T<n>`` line, when it has one. A spawn that
names a task but no brief is recorded with ``-`` as its brief. orch-fleet's
``parseAgentsMd`` reads these rows and takes the last one per brief.

Any failure is swallowed: logging must never block a spawn.

Wired in ``.claude/settings.json`` with
``--prefix pack-``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

BRIEF_PATH = re.compile(r"\.claude/scratch/([A-Za-z0-9._-]+)/brief-(\d+[a-z]?)\.md")
TASK_PATH = re.compile(r"\.claude/scratch/([A-Za-z0-9._-]+)/")
TIER = re.compile(r"\*\*Tier:\*\*\s*(T\d)")
MODEL = re.compile(r"claude-([a-z]+)")
UNASSIGNED = "_unassigned"


def project_root(payload: dict[str, Any]) -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    return Path(root).resolve()


def frontmatter(root: Path, agent_type: str) -> dict[str, str]:
    """``key: value`` lines of the agent file's frontmatter, project first."""
    for directory in (root / ".claude" / "agents", Path.home() / ".claude" / "agents"):
        try:
            text = (directory / f"{agent_type}.md").read_text(encoding="utf-8")
        except OSError:
            continue
        fields: dict[str, str] = {}
        for line in text.split("---", 2)[1].splitlines() if text.startswith("---") else []:
            key, sep, value = line.partition(":")
            if sep and not line.startswith((" ", "-")):
                fields[key.strip()] = value.strip()
        return fields
    return {}


def row(payload: dict[str, Any], prefix: str) -> tuple[Path, str] | None:
    tool_input = payload.get("tool_input")
    response = payload.get("tool_response")
    if not isinstance(tool_input, dict) or not isinstance(response, dict):
        return None
    agent_type = tool_input.get("subagent_type")
    agent_id = response.get("agentId")
    if not isinstance(agent_type, str) or not agent_type.startswith(prefix):
        return None
    if not isinstance(agent_id, str) or not agent_id:
        return None
    prompt = str(tool_input.get("prompt") or "")
    match = BRIEF_PATH.search(prompt)
    if match:
        task, brief = match.group(1), f"brief-{match.group(2)}"
    else:
        task_match = TASK_PATH.search(prompt)
        if not task_match or task_match.group(1) == UNASSIGNED:
            return None
        task, brief = task_match.group(1), "-"
    root = project_root(payload)
    scratch = root / ".claude" / "scratch" / task
    defaults = frontmatter(root, agent_type)
    model = tool_input.get("model")
    if not model:
        resolved = MODEL.search(str(response.get("resolvedModel") or ""))
        model = resolved.group(1) if resolved else defaults.get("model", "default")
    effort = tool_input.get("effort") or defaults.get("effort", "default")
    status = f"spawned {model}/{effort}"
    if brief != "-":
        try:
            head = (scratch / f"{brief}.md").read_text(encoding="utf-8")[:4000]
        except OSError:
            head = ""
        tier = TIER.search(head)
        if tier:
            status += f" {tier.group(1)}"
    return scratch / "agents.md", f"{brief} | {agent_type} | {agent_id} | {status}\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    options = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        found = row(payload, options.prefix) if isinstance(payload, dict) else None
        if found is None:
            return 0
        path, line = found
        path.parent.mkdir(parents=True, exist_ok=True)
        # One short O_APPEND write, so parallel spawns don't interleave.
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
