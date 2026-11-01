"""SubagentStop check: every agent the hook matcher selects (``pack-*`` here) must end with a return block.

The orchestrator parses the block to decide whether to relay questions, resume
the agent, or move on, so an agent that silently guesses or rambles breaks the
protocol. On the first malformed stop the agent is sent back once with the
schema; ``stop_hook_active`` lets the second attempt through to avoid loops.
The schema lives in ``.claude/skills/pack-orchestrate/return-protocol.md``.

An agent that ends with a ``SubagentHandback`` call carries its block in that
call's ``message``, not in its final text, and has already finished: a
send-back reaches no one, so its stop is always logged, never blocked. When
the handback drops a block the agent already wrote in this run's text (the
harness asks for a handback after a plain-text report), that text's block is
logged instead, so the report is not logged as INVALID.

Claude Code 2.1.307 can run this hook before the handback reaches the
transcript, so a background agent's transcript is re-read for a short while
before its stop is blocked.
"""

from __future__ import annotations

import json
import re
import sys
import time

STATUS = re.compile(r"^\s*STATUS:\s*(DONE|NEEDS_INPUT|PARTIAL|FAILED)\b", re.M)
QUESTION = re.compile(r"^\s*-\s*id:\s*\S+", re.M)
HANDBACK = "SubagentHandback"
# How long to wait for a handback to reach the transcript: the hook's
# timeout is 10 s.
HANDBACK_WAIT = 3.0
HANDBACK_POLL = 0.25

SCHEMA = """\
End your final message with the return block, starting on its own line:

STATUS: DONE | NEEDS_INPUT | PARTIAL | FAILED
SUMMARY: <=3 lines
QUESTIONS:            # required for NEEDS_INPUT
  - id: Q1
    q: <question>
    options: [<a>, <b>]
    recommended: <a>
    blocking: true|false
PROGRESS:
  done: [...]
  files_touched: [...]
  checks: ["<command> -> pass|fail (counts)"]
  defaults_taken: ["<choice> because <reason>"]
  debt: ["<path:line> <shortcut or follow-up> because <reason>"]
CONTINUATION: <path>  # PARTIAL only
REPORT: <path>        # optional

Do not redo work; restate what you already did in the block."""


def problem(message: str) -> str | None:
    found = STATUS.findall(message)
    if not found:
        return "Your final message has no `STATUS:` line."
    status = found[-1]
    if status == "NEEDS_INPUT" and not QUESTION.search(message):
        return "STATUS is NEEDS_INPUT but QUESTIONS lists no `- id:` entries."
    if status == "PARTIAL" and "CONTINUATION:" not in message:
        return "STATUS is PARTIAL but there is no CONTINUATION path."
    return None


def is_prompt(entry: dict[str, object]) -> bool:
    """Whether a user entry starts a run: a spawn, resume or notification.

    The spawn prompt has no ``isMeta``; a resume or task notification has an
    ``origin``. Tool results and the harness's own nudges (a handback
    reminder or enforce message, a skill's text) start nothing.
    """
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(part, dict) and part.get("type") == "tool_result" for part in content
    ):
        return False
    return bool(entry.get("origin")) or not entry.get("isMeta")


# last tool call, its line, run start, latest prompt, texts, told to hand back
Transcript = tuple[dict[str, object] | None, int, int, int, list[tuple[int, str]], bool]


def read_transcript(path: str) -> Transcript:
    """Scan an agent transcript for its last tool call and this run's texts.

    Returns the last ``tool_use`` part, its line, the line its run starts on,
    the line of the latest prompt, every ``(line, text)`` an assistant wrote,
    and whether the agent was told to report through a handback. A run
    starts at the last prompt (``is_prompt``) or the line after an earlier
    handback, whichever is later. Raises OSError.
    """
    last: dict[str, object] | None = None
    last_at = 0
    start = 0
    run_start = 0
    prompt_at = 0
    texts: list[tuple[int, str]] = []
    told = False
    with open(path, encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "user":
                content = (entry.get("message") or {}).get("content")
                if isinstance(content, str) and HANDBACK in content and entry.get("isMeta"):
                    told = True
                if is_prompt(entry):
                    start = prompt_at = index
                continue
            if entry.get("type") != "assistant":
                continue
            content = (entry.get("message") or {}).get("content")
            for part in content if isinstance(content, list) else []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    if last is not None and last.get("name") == HANDBACK:
                        # The previous run ended with that handback.
                        start = max(start, last_at + 1)
                    last, last_at, run_start = part, index, start
                elif part.get("type") == "text" and isinstance(part.get("text"), str):
                    texts.append((index, part["text"]))
    return last, last_at, run_start, prompt_at, texts, told


def handback(payload: dict[str, object]) -> str | None:
    """The message of the agent's last tool call, when that call was a handback.

    Only the last call counts, so a resumed agent's earlier handback is never
    mistaken for this run's report. If the message has no valid block, the
    last text with one since this run started is returned instead (see
    ``read_transcript``); ``promptId`` is not used, as since Claude Code
    2.1.307 it can change in the middle of a run. An agent told to hand
    back whose transcript does not show a handback yet is re-read for up to
    ``HANDBACK_WAIT`` seconds. Any read or parse failure gives None.
    """
    path = payload.get("agent_transcript_path")
    if not isinstance(path, str) or not path:
        return None
    deadline = time.monotonic() + HANDBACK_WAIT
    while True:
        try:
            last, last_at, start, prompt_at, texts, told = read_transcript(path)
        except OSError:
            return None
        # A handback before the latest prompt belongs to an earlier run.
        if last and last.get("name") == HANDBACK and last_at > prompt_at:
            break
        if not told or time.monotonic() >= deadline:
            return None
        time.sleep(HANDBACK_POLL)
    message = (last.get("input") or {}).get("message")
    if not isinstance(message, str):
        return None
    if problem(message) is None:
        return message
    written = [text for at, text in texts if start <= at < last_at and problem(text) is None]
    return written[-1] if written else message


def record_return(payload: dict[str, object], valid: bool) -> None:
    """Log this stop via ``scripts/returns.py`` so results survive compaction.

    Loaded by path because ``python3 -I`` keeps the scripts directory off
    ``sys.path``. Any failure is swallowed: recording must never block an agent.
    """
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "returns.py"
    try:
        spec = importlib.util.spec_from_file_location("orch_returns", path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.record(payload, valid)
    except Exception:
        return


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    issue = problem(payload.get("last_assistant_message") or "")
    handed = handback(payload) if issue else None
    if handed is not None:
        # The report went out in the handback; log that, the way returns.py parses it.
        payload = {**payload, "last_assistant_message": handed}
        issue = problem(handed)
    if issue is None or handed is not None or payload.get("stop_hook_active"):
        # Valid blocks, handed-back agents and the final attempt after one
        # send-back are logged.
        record_return(payload, valid=issue is None)
        return 0
    print(json.dumps({"decision": "block", "reason": f"{issue}\n\n{SCHEMA}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
