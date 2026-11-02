"""Record subagent return blocks on disk and query them for the orchestrator.

The orchestrator used to carry each subagent's results only in its own
context: copying ``PROGRESS`` into dependent briefs, tracking which brief is
done, and filling the handoff's ``## Briefs`` table. That fails silently when
it forgets or after compaction. The ``SubagentStop`` hook now calls
:func:`record` for every stop, so the record lives in scratch and the
orchestrator reads it back with this CLI instead of from memory.

Storage, per task (``<root>/.claude/scratch/<task>/returns/``):

- ``index.jsonl``: one JSON line per stop (time, agent, brief, parsed block).
- ``<agent_id>.md``: every raw block that agent returned, in order.
- ``answers.jsonl``: one JSON line per question the orchestrator recorded as
  answered (``answer`` below). A question counts as answered when a record
  has its agent ID and question ID and is no older than the return that
  asked it, so a later re-ask is open again.

The task and brief come from the first ``.claude/scratch/<task>/brief-<n>.md``
path in the agent's transcript (its spawn prompt); agents spawned without a
brief are filed under their task if any scratch path appears, else under
``_unassigned``.

Usage::

    python3 -I <scripts>/returns.py status    <task>          # latest per brief/agent
    python3 -I <scripts>/returns.py inputs    <task> <n>...   # brief inputs
    python3 -I <scripts>/returns.py briefs    <task>          # handoff "## Briefs" rows
    python3 -I <scripts>/returns.py questions <task>          # open questions
    python3 -I <scripts>/returns.py answer    <task> <ref>... --round <label>
    python3 -I <scripts>/returns.py debt      <task>          # shortcuts, follow-ups
    python3 -I <scripts>/returns.py scope     <task>          # files outside briefs
    python3 -I <scripts>/returns.py review    <task>          # scope + debt, for the reviewer
    python3 -I <scripts>/returns.py show      <task> <brief-n | agent_id>

An ``answer`` ref is ``brief-<n>:<qid>``, ``<agent_id>:<qid>`` or a bare
``brief-<n>`` (every question of that brief's latest asking return).

``--root DIR`` overrides the project root (default ``$CLAUDE_PROJECT_DIR``,
else the current directory). Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

STATUS = re.compile(r"^\s*STATUS:\s*(DONE|NEEDS_INPUT|PARTIAL|FAILED)\b", re.M)
BRIEF_PATH = re.compile(r"\.claude/scratch/([A-Za-z0-9._-]+)/brief-(\d+[a-z]?)\.md")
TASK_PATH = re.compile(r"\.claude/scratch/([A-Za-z0-9._-]+)/")
KEY = re.compile(r"^(\s*)(?:-\s*)?([A-Za-z_]+):\s?(.*)$")
LIST_KEYS = ("done", "files_touched", "checks", "defaults_taken", "debt")
TRANSCRIPT_SCAN_BYTES = 400_000
UNASSIGNED = "_unassigned"


# --- parsing -----------------------------------------------------------------


def split_list(text: str) -> list[str]:
    """Split ``[a, "b, c", d (x, y)]`` on top-level commas."""
    inner = text.strip()
    if inner.startswith("["):
        inner = inner[1:]
    if inner.endswith("]"):
        inner = inner[:-1]
    items: list[str] = []
    current: list[str] = []
    quote = ""
    depth = 0
    for char in inner:
        if quote:
            if char == quote:
                quote = ""
            else:
                current.append(char)
            continue
        if char in "\"'":
            quote = char
        elif char in "([{":
            depth += 1
            current.append(char)
        elif char in ")]}":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    items.append("".join(current).strip())
    return [item for item in items if item]


def strip_comment(value: str) -> str:
    return re.sub(r"\s+#.*$", "", value).strip()


def parse_block(message: str) -> dict[str, Any] | None:
    """Parse the last return block in ``message``; None if there is none."""
    found = list(STATUS.finditer(message))
    if not found:
        return None
    lines = message[found[-1].start() :].splitlines()
    block: dict[str, Any] = {
        "status": found[-1].group(1),
        "summary": "",
        "questions": [],
        **{key: [] for key in LIST_KEYS},
        "continuation": None,
        "report": None,
    }
    section = ""
    pending_list: str | None = None
    buffer = ""
    question: dict[str, Any] | None = None
    for raw in lines[1:]:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            break
        if pending_list is not None:
            buffer += " " + line.strip()
            if "]" in line:
                block[pending_list] = split_list(buffer)
                pending_list = None
            continue
        match = KEY.match(line)
        if not match:
            stripped = line.strip()
            if section == "summary" and stripped:
                block["summary"] = f"{block['summary']} {stripped}".strip()
            elif section in LIST_KEYS and stripped.startswith("- "):
                block[section].append(strip_comment(stripped[2:]).strip("\"'"))
            continue
        indent, key, value = match.groups()
        value = strip_comment(value)
        key = key.lower()
        if not indent and key in (
            "summary",
            "questions",
            "progress",
            "continuation",
            "report",
        ):
            section = key
            if key == "summary":
                block["summary"] = value
            elif key in ("continuation", "report"):
                block[key] = value or None
            continue
        if section == "questions":
            if key == "id" and line.lstrip().startswith("-"):
                question = {"id": value}
                block["questions"].append(question)
            elif question is not None and key in ("q", "recommended"):
                question[key] = value
            elif question is not None and key == "options":
                question["options"] = split_list(value)
            elif question is not None and key == "blocking":
                question["blocking"] = value.lower() != "false"
            continue
        if key in LIST_KEYS:
            section = key
            if value.startswith("[") and "]" not in value:
                pending_list, buffer = key, value
            elif value:
                block[key] = split_list(value)
    if pending_list is not None:
        block[pending_list] = split_list(buffer)
    return block


# --- recording ---------------------------------------------------------------


def project_root(payload: dict[str, Any] | None = None) -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or (payload or {}).get("cwd") or "."
    return Path(root).resolve()


def locate(payload: dict[str, Any]) -> tuple[str, str | None]:
    """Find (task, brief) from the agent transcript, then the final message."""
    texts: list[str] = []
    for key in ("agent_transcript_path", "transcript_path"):
        path = payload.get(key)
        if not path:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                texts.append(handle.read(TRANSCRIPT_SCAN_BYTES))
        except OSError:
            continue
        # The agent's own transcript starts with its spawn prompt; the parent
        # transcript would name every brief, so only fall back to it for the task.
        break
    texts.append(payload.get("last_assistant_message") or "")
    for text in texts:
        match = BRIEF_PATH.search(text)
        if match:
            return match.group(1), f"brief-{match.group(2)}"
    for text in texts:
        match = TASK_PATH.search(text)
        if match and match.group(1) != UNASSIGNED:
            return match.group(1), None
    return UNASSIGNED, None


def record(payload: dict[str, Any], valid: bool) -> Path | None:
    """Append this stop to the task's return log. Never raises."""
    try:
        message = payload.get("last_assistant_message") or ""
        block = parse_block(message)
        task, brief = locate(payload)
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        agent_id = str(payload.get("agent_id") or f"unknown-{now}")
        agent_type = str(payload.get("agent_type") or "unknown")
        directory = project_root(payload) / ".claude" / "scratch" / task / "returns"
        directory.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", agent_id)
        entry = {
            "ts": now,
            "agent_id": agent_id,
            "agent_type": agent_type,
            "brief": brief,
            "valid": valid,
            "file": f"returns/{safe_id}.md",
            **(block or {"status": "INVALID"}),
        }
        with open(directory / "index.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        tail = (
            message[list(STATUS.finditer(message))[-1].start() :]
            if block
            else message[-2000:]
        )
        with open(directory / f"{safe_id}.md", "a", encoding="utf-8") as handle:
            handle.write(
                f"## {now} {entry['status']} ({agent_type}, {brief or 'no brief'})\n\n"
                f"```\n{tail.strip()}\n```\n\n"
            )
        return directory
    except Exception:  # A recording failure must never block an agent.
        return None


# --- queries -----------------------------------------------------------------


def load(root: Path, task: str, name: str = "index.jsonl") -> list[dict[str, Any]]:
    path = root / ".claude" / "scratch" / task / "returns" / name
    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return entries
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def load_answers(root: Path, task: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    answers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in load(root, task, "answers.jsonl"):
        if record.get("agent_id") and record.get("id") and record.get("ts"):
            key = (str(record["agent_id"]), str(record["id"]))
            answers.setdefault(key, []).append(record)
    return answers


def answer_for(
    answers: dict[tuple[str, str], list[dict[str, Any]]],
    entry: dict[str, Any],
    question: dict[str, Any],
) -> dict[str, Any] | None:
    """The latest answer record for this question, if it is not older than the ask."""
    found = [
        record
        for record in answers.get((str(entry["agent_id"]), str(question.get("id"))), [])
        if str(record["ts"]) >= str(entry.get("ts", ""))
    ]
    return found[-1] if found else None


def natural(key: str) -> tuple[int, str]:
    match = re.search(r"(\d+)([a-z]?)$", key)
    return (int(match.group(1)), match.group(2)) if match else (10**9, key)


def latest_by(entries: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        key = entry.get(field) or f"{entry['agent_type']}:{entry['agent_id']}"
        latest[key] = entry
    return latest


def checks_failing(entry: dict[str, Any]) -> bool:
    return any(
        re.search(r"->\s*fail", str(check), re.I) for check in entry.get("checks", [])
    )


def brief_state(entry: dict[str, Any] | None) -> str:
    if entry is None:
        return "not started"
    status = entry.get("status")
    if status == "DONE":
        return "done, checks failing" if checks_failing(entry) else "done"
    return {
        "PARTIAL": "partial",
        "NEEDS_INPUT": "waiting on user",
        "FAILED": "failed",
    }.get(str(status), "no valid return")


def fmt(items: list[str]) -> str:
    return (
        ", ".join(f"`{item}`" if "/" in item or "." in item else item for item in items)
        or "—"
    )


def cmd_status(root: Path, task: str) -> int:
    entries = load(root, task)
    if not entries:
        print(f"no returns recorded for {task}")
        return 1
    print("| brief | agent type | agent ID | status | at | files touched |")
    print("|---|---|---|---|---|---|")
    for key, entry in sorted(
        latest_by(entries, "agent_id").items(), key=lambda kv: kv[1]["ts"]
    ):
        print(
            f"| {entry.get('brief') or '—'} | {entry['agent_type']} | {key} | "
            f"{entry.get('status')} | {entry['ts']} | "
            f"{fmt(entry.get('files_touched', []))} |"
        )
    return 0


def cmd_inputs(root: Path, task: str, briefs: list[str]) -> int:
    latest = latest_by(load(root, task), "brief")
    missing = 0
    for raw in briefs:
        name = raw if raw.startswith("brief-") else f"brief-{raw}"
        entry = latest.get(name)
        if entry is None:
            print(f"- {name}: no return recorded")
            missing += 1
            continue
        print(
            f"- {name} ({entry['agent_type']}, {entry.get('status')}): "
            f"{entry.get('summary') or ''}".rstrip()
        )
        print(f"  - files touched: {fmt(entry.get('files_touched', []))}")
        if entry.get("defaults_taken"):
            print(f"  - defaults taken: {'; '.join(entry['defaults_taken'])}")
        if entry.get("debt"):
            print(f"  - debt: {'; '.join(entry['debt'])}")
        if entry.get("checks"):
            print(f"  - checks: {'; '.join(entry['checks'])}")
        for key in ("continuation", "report"):
            if entry.get(key):
                print(f"  - {key}: `{entry[key]}`")
    return 1 if missing else 0


def cmd_briefs(root: Path, task: str) -> int:
    scratch = root / ".claude" / "scratch" / task
    latest = latest_by(load(root, task), "brief")
    names = {p.stem for p in scratch.glob("brief-*.md")} | {
        k for k in latest if k.startswith("brief-")
    }
    if not names:
        print(f"no briefs found in {scratch}")
        return 1
    print("| brief | state | files touched | continuation note |")
    print("|---|---|---|---|")
    for name in sorted(names, key=natural):
        entry = latest.get(name)
        files = fmt(entry.get("files_touched", [])) if entry else "—"
        note = (
            f"`{entry['continuation']}`" if entry and entry.get("continuation") else "—"
        )
        print(f"| {name} | {brief_state(entry)} | {files} | {note} |")
    return 0


def cmd_questions(root: Path, task: str) -> int:
    entries = load(root, task)
    latest = latest_by(entries, "agent_id")
    answers = load_answers(root, task)
    # The newest ask of each (agent, question ID) wins, so a re-ask replaces
    # the earlier one in place.
    asked: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for entry in entries:
        for question in entry.get("questions", []):
            asked[(entry["agent_id"], str(question.get("id")))] = (entry, question)
    blocking: list[str] = []
    later: list[str] = []
    hidden = 0
    for entry, question in asked.values():
        is_blocking = question.get("blocking", True)
        is_open = (
            latest[entry["agent_id"]] is entry
            and entry.get("status") == "NEEDS_INPUT"
        )
        if is_blocking and not is_open:
            continue
        if answer_for(answers, entry, question):
            hidden += 1
            continue
        line = (
            f"- [{entry.get('brief') or entry['agent_type']} {question.get('id')}] "
            f"{question.get('q', '')} options: {question.get('options', [])}; "
            f"recommended: {question.get('recommended', '?')} "
            f"(agent {entry['agent_id']})"
        )
        (blocking if is_blocking else later).append(line)
    print("Blocking (agent waiting):")
    print("\n".join(blocking) or "- none")
    print("Non-blocking (defaults taken; ask at end of step):")
    print("\n".join(later) or "- none")
    if hidden:
        print(f"{hidden} answered (hidden)")
    return 0


def resolve_ref(
    entries: list[dict[str, Any]], ref: str
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """The (entry, question) pairs a ref names: its newest ask, or [] if none."""
    target, _, qid = ref.partition(":")
    name = f"brief-{target}" if target.isdigit() else target
    mine = [e for e in entries if e.get("brief") == name or e["agent_id"] == name]
    for entry in reversed(mine):
        questions = entry.get("questions") or []
        if not qid and questions:
            return [(entry, question) for question in questions]
        for question in questions:
            if str(question.get("id")) == qid:
                return [(entry, question)]
    return []


def cmd_answer(root: Path, task: str, refs: list[str], round_label: str) -> int:
    entries = load(root, task)
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for ref in refs:
        pairs = resolve_ref(entries, ref)
        if not pairs:
            missing.append(ref)
        for entry, question in pairs:
            records.append(
                {
                    "ts": now,
                    "agent_id": entry["agent_id"],
                    "brief": entry.get("brief"),
                    "id": str(question.get("id")),
                    "ret_ts": entry.get("ts"),
                    "round": round_label,
                }
            )
    if missing:
        print(f"no question recorded for: {', '.join(missing)}; nothing written")
        return 2
    path = root / ".claude" / "scratch" / task / "returns" / "answers.jsonl"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    for r in records:
        print(f"answered: {r['brief'] or '-'} {r['id']} (agent {r['agent_id']})")
    return 0


def cmd_debt(root: Path, task: str) -> int:
    """Every shortcut or follow-up any agent recorded, de-duplicated, in order.

    All returns count, not only the latest: an agent resumed after a question
    may not repeat debt it reported before it stopped.
    """
    seen: set[tuple[str, str]] = set()
    lines: list[str] = []
    for entry in load(root, task):
        owner = entry.get("brief") or entry["agent_type"]
        for item in entry.get("debt", []):
            if (owner, item) in seen:
                continue
            seen.add((owner, item))
            lines.append(f"- [{owner}, {entry['agent_type']}] {item}")
    print("\n".join(lines) or "- none recorded")
    return 0


SCOPE_LINE = re.compile(r"^\s*-\s*\*{0,2}Files to change\*{0,2}:(.*)$", re.I)
BULLET = re.compile(r"^\s*-\s")
BACKTICK = re.compile(r"`([^`]+)`")


def brief_files(path: Path) -> list[str] | None:
    """Backticked paths on a brief's "Files to change" line (and its wraps)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for index, line in enumerate(lines):
        match = SCOPE_LINE.match(line)
        if not match:
            continue
        text = match.group(1)
        for follow in lines[index + 1 :]:
            if not follow.strip() or BULLET.match(follow) or follow.startswith("#"):
                break
            text += " " + follow.strip()
        return [token.strip() for token in BACKTICK.findall(text) if "<" not in token]
    return None


def relative(root: Path, touched: str) -> str:
    """Agents report some paths absolute; briefs list them from the root."""
    prefix = f"{root}/"
    return touched[len(prefix) :] if touched.startswith(prefix) else touched


def in_scope(touched: str, allowed: list[str]) -> bool:
    if touched.startswith(".claude/scratch/"):  # continuation notes, reports
        return True
    for pattern in allowed:
        pattern = pattern.rstrip("/") if pattern.endswith("/") else pattern
        if touched == pattern or touched.startswith(pattern + "/"):
            return True
        if any(char in pattern for char in "*?[") and fnmatch(touched, pattern):
            return True
    return False


def cmd_scope(root: Path, task: str) -> int:
    """Files agents touched that their brief's "Files to change" doesn't list.

    A lead for the reviewer, not a verdict: a brief may justify the extra file.
    """
    scratch = root / ".claude" / "scratch" / task
    touched: dict[str, set[str]] = {}
    for entry in load(root, task):
        if entry.get("brief"):
            touched.setdefault(entry["brief"], set()).update(
                entry.get("files_touched", [])
            )
    if not touched:
        print(f"no returns with a brief recorded for {task}")
        return 1
    drift = 0
    for brief in sorted(touched, key=natural):
        allowed = brief_files(scratch / f"{brief}.md")
        if allowed is None:
            print(f'- {brief}: no "Files to change" line found; check by hand')
            continue
        extra = sorted(
            f for f in touched[brief] if not in_scope(relative(root, f), allowed)
        )
        if extra:
            drift += 1
            print(f'- {brief}: outside "Files to change": {fmt(extra)}')
        else:
            print(f"- {brief}: in scope")
    return 2 if drift else 0


def cmd_review(root: Path, task: str) -> int:
    """``scope`` and ``debt`` in one call: the reviewer's inputs from the log."""
    print("## Scope: files outside each brief's \"Files to change\"")
    code = cmd_scope(root, task)
    print("\n## Debt: shortcuts and follow-ups agents recorded")
    cmd_debt(root, task)
    return code


def cmd_show(root: Path, task: str, target: str) -> int:
    entries = load(root, task)
    name = f"brief-{target}" if target.isdigit() else target
    matches = [e for e in entries if e.get("brief") == name or e["agent_id"] == name]
    if not matches:
        print(f"no return recorded for {target}")
        return 1
    entry = matches[-1]
    path = root / ".claude" / "scratch" / task / entry["file"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        print(json.dumps(entry, indent=2))
        return 0
    print(text.rsplit("\n## ", 1)[-1] if "\n## " in text else text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "briefs", "questions", "debt", "scope", "review"):
        sub.add_parser(name).add_argument("task")
    inputs = sub.add_parser("inputs")
    inputs.add_argument("task")
    inputs.add_argument("briefs", nargs="+")
    answer = sub.add_parser("answer")
    answer.add_argument("task")
    answer.add_argument("refs", nargs="+")
    answer.add_argument("--round", required=True, dest="round_label")
    show = sub.add_parser("show")
    show.add_argument("task")
    show.add_argument("target")
    args = parser.parse_args()
    root = (args.root or project_root()).resolve()
    if args.command == "status":
        return cmd_status(root, args.task)
    if args.command == "inputs":
        return cmd_inputs(root, args.task, args.briefs)
    if args.command == "briefs":
        return cmd_briefs(root, args.task)
    if args.command == "questions":
        return cmd_questions(root, args.task)
    if args.command == "answer":
        return cmd_answer(root, args.task, args.refs, args.round_label)
    if args.command == "debt":
        return cmd_debt(root, args.task)
    if args.command == "scope":
        return cmd_scope(root, args.task)
    if args.command == "review":
        return cmd_review(root, args.task)
    return cmd_show(root, args.task, args.target)


if __name__ == "__main__":
    sys.exit(main())
