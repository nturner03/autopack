"""PreToolUse budget guard for orchestrated subagents.

Subagent prompts set a roughly 150k-token limit (200k for architects) and
function-sized reads, but an agent cannot see its own token count, and prompts
alone did not hold: in one run an implementer ``cat``'d whole modules,
passed 150k at turn 56 and ran past 240k without returning ``PARTIAL``. This hook enforces both rules for subagents whose type starts
with ``--prefix``; the main session and every other agent pass untouched.

- **Context limit.** Once the agent's latest recorded context (input plus
  cache tokens on its last assistant message) reaches its limit (``--limit``,
  or the role's entry in ``ROLE_LIMITS``), every tool
  call is denied except Write/Edit of a file under ``.claude/scratch/`` and
  the ``SubagentHandback`` call that delivers the report. The reason tells the
  agent to write its continuation note and return ``PARTIAL``.
- **Bulk reads.** Read of a project file longer than ``READ_MAX_LINES``
  without a ``limit`` (or with a larger one), and Bash ``cat``/``sed``/
  ``head``/``tail`` that print more than ``READ_MAX_LINES`` lines of one
  project file or ``COMMAND_MAX_LINES`` in one command, are denied with a
  pointer to targeted reads. Output that is piped or redirected is not read
  into context and passes.
- **Shell writes.** ``sed -i``, ``perl -i``, output redirection, ``tee`` and
  Python ``-c``/heredoc scripts that write a project file are denied; agents
  use Edit/Write. A linked worktree (``orch-refactorer``) is exempt.

Files under ``.claude/scratch/`` and outside the project are exempt from the
read and write rules. Anything the hook cannot determine (no agent identity,
an unreadable transcript, a parse error) allows the call.

Wired in ``.claude/settings.json`` with
``--prefix pack-``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

DEFAULT_LIMIT = 150_000
# Per-role limits, keyed by the agent type without ``--prefix``. Architects
# read across many modules: in transcripts up to 2026-10-27, 12 of 35 hit 150k
# (median peak about 140k), against about 6% of all agents.
ROLE_LIMITS = {"architect": 200_000}
READ_MAX_LINES = 200
COMMAND_MAX_LINES = 300
TRANSCRIPT_TAIL_BYTES = 1 << 20
MAX_COUNTED_BYTES = 20 << 20
# Tools that deliver the agent's report and end its run; never denied, or an
# agent past its limit cannot hand back at all.
HANDBACK_TOOLS = {"SubagentHandback"}

CAT_LIKE = {"cat", "nl", "tac", "bat", "batcat", "less", "more"}
OPERATORS = {";", "&&", "||", "|", "|&", "&", "(", ")", ";;", ";&"}
STDOUT_REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
INPUT_REDIRECTS = {"<", "<<", "<<<", "<<-", "<>"}
HEREDOC = re.compile(
    r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n(.*?)\n[ \t]*\2[ \t]*(?=\n|$)", re.S
)
SED_RANGE = re.compile(r"(\d+|\$)\s*(?:,\s*(\d+|\$|\+\d+))?\s*p")
PY_WRITE = re.compile(
    r"\.write_text\(|\.write_bytes\(|open\([^)]*['\"][wax]\+?b?['\"]"
    r"|\.open\(\s*['\"][wax]|shutil\.(?:copy|move)|os\.replace\("
)
STRING_LITERAL = re.compile(r"['\"]([^'\"\n]+)['\"]")


def decision(kind: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": kind,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


# --- agent identity and context -------------------------------------------


def agent_transcript(payload: dict[str, Any]) -> Path | None:
    """The calling subagent's own transcript, or None in the main session.

    Subagent transcripts live at ``<session>/subagents/agent-<id>.jsonl``
    beside the main ``<session>.jsonl``.
    """
    explicit = payload.get("agent_transcript_path")
    if isinstance(explicit, str) and explicit:
        return Path(explicit)
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return None
    path = Path(transcript)
    if path.parent.name == "subagents":
        return path
    agent_id = payload.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        return path.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"
    return None


def subagent_type(payload: dict[str, Any], transcript: Path | None) -> str | None:
    if transcript is None and not payload.get("agent_id"):
        return None
    value = payload.get("agent_type")
    if isinstance(value, str) and value:
        return value
    if transcript is None:
        return None
    meta = transcript.with_name(transcript.stem + ".meta.json")
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("agentType") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def context_tokens(transcript: Path) -> int | None:
    """Prompt size of the agent's latest assistant message, from its usage."""
    try:
        with transcript.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            tail = handle.read()
    except OSError:
        return None
    for raw in reversed(tail.splitlines()):
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        usage = message.get("usage") if isinstance(message, dict) else None
        if isinstance(usage, dict):
            keys = (
                "input_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            )
            return sum(int(usage.get(key) or 0) for key in keys)
    return None


# --- paths -----------------------------------------------------------------


def project_root(payload: dict[str, Any]) -> Path:
    return Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    ).resolve()


def relative(path: Path, root: Path) -> Path | None:
    try:
        return path.resolve().relative_to(root)
    except (OSError, ValueError):
        return None


def in_scratch(path: Path, root: Path) -> bool:
    rel = relative(path, root)
    return rel is not None and rel.parts[:2] == (".claude", "scratch")


def guarded(path: Path, root: Path) -> Path | None:
    """Project-relative path when the read and write rules apply to it."""
    rel = relative(path, root)
    if rel is None or rel.parts[:2] == (".claude", "scratch"):
        return None
    return rel


def line_count(path: Path) -> int | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_COUNTED_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)


def in_linked_worktree(cwd: str) -> bool:
    path = Path(cwd or ".").resolve()
    for candidate in (path, *path.parents):
        dot_git = candidate / ".git"
        if dot_git.exists():
            return dot_git.is_file()
    return False


# --- shell parsing ---------------------------------------------------------


class Command:
    def __init__(self) -> None:
        self.argv: list[str] = []
        self.captured = False  # stdout piped or redirected, so not read into context
        self.writes: list[str] = []


def parse_shell(command: str) -> tuple[list[Command], list[str]]:
    """Split a Bash command into simple commands, plus its heredoc bodies."""
    bodies: list[str] = []

    def take_body(match: re.Match[str]) -> str:
        bodies.append(match.group(4))
        return match.group(3)

    text = HEREDOC.sub(take_body, command).replace("\\\n", " ")
    commands: list[Command] = []
    for line in text.split("\n"):
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            tokens = line.split()
        current = Command()
        index = 0
        while index < len(tokens):
            token = tokens[index]
            following = tokens[index + 1] if index + 1 < len(tokens) else ""
            if token in OPERATORS:
                current.captured = current.captured or token in ("|", "|&")
                commands.append(current)
                current = Command()
            elif token in STDOUT_REDIRECTS:
                fd_two = bool(current.argv) and current.argv[-1] == "2"
                if fd_two:
                    current.argv.pop()
                if following:
                    current.writes.append(following)
                current.captured = current.captured or not fd_two
                index += 1
            elif token in (">&", "<&"):
                index += 1  # fd duplication such as 2>&1
            elif token in INPUT_REDIRECTS:
                index += 1
            else:
                current.argv.append(token)
            index += 1
        commands.append(current)
    return [c for c in commands if c.argv or c.writes], bodies


def strip_prefixes(argv: list[str]) -> list[str]:
    rest = list(argv)
    while rest:
        head = rest[0]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", head) or head in (
            "env",
            "command",
            "nohup",
        ):
            rest.pop(0)
        elif head == "timeout" and len(rest) > 1:
            rest = rest[2:]
        elif rest[:2] == ["uv", "run"]:
            rest = rest[2:]
            while rest and rest[0].startswith("-"):
                rest.pop(0)
        else:
            break
    return rest


def sed_parts(args: list[str]) -> tuple[bool, bool, list[str], list[str]]:
    """(quiet, in_place, scripts, files) for a sed argument list."""
    quiet = in_place = False
    scripts: list[str] = []
    files: list[str] = []
    explicit_script = any(
        a in ("-e", "--expression") or a.startswith("--expression=") for a in args
    )
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-e", "--expression", "-f", "--file"):
            if arg in ("-e", "--expression") and index + 1 < len(args):
                scripts.append(args[index + 1])
            index += 2
            continue
        if arg.startswith("--expression="):
            scripts.append(arg.partition("=")[2])
        elif arg == "--in-place" or arg.startswith("--in-place="):
            in_place = True
        elif arg in ("--quiet", "--silent"):
            quiet = True
        elif arg.startswith("-") and len(arg) > 1 and not arg.startswith("--"):
            flags = arg[1:]
            in_place = in_place or flags.startswith("i") or "i" in flags.split(".")[0]
            quiet = quiet or "n" in flags.split(".")[0]
        elif not explicit_script and not scripts:
            scripts.append(arg)
        else:
            files.append(arg)
        index += 1
    return quiet, in_place, scripts, files


def sed_lines(scripts: list[str], total: int) -> int:
    printed = 0
    for script in scripts:
        for match in SED_RANGE.finditer(script):
            start = total if match.group(1) == "$" else int(match.group(1))
            end_text = match.group(2)
            if end_text is None:
                end = start
            elif end_text == "$":
                end = total
            elif end_text.startswith("+"):
                end = start + int(end_text[1:])
            else:
                end = int(end_text)
            printed += max(0, min(end, total) - start + 1)
    return printed


def head_tail_lines(
    name: str, args: list[str], cwd: Path
) -> list[tuple[str, int | None]]:
    """(file, lines printed or None for "all") for head/tail."""
    count: int | None = 10
    from_line = False
    files: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        text: str | None = None
        if arg in ("-n", "--lines"):
            text = args[index + 1] if index + 1 < len(args) else "10"
            index += 1
        elif arg.startswith("--lines="):
            text = arg.partition("=")[2]
        elif arg.startswith("-n") and len(arg) > 2:
            text = arg[2:]
        elif re.fullmatch(r"-\d+", arg):
            text = arg[1:]
        elif arg in ("-c", "--bytes"):
            index += 1
        elif not arg.startswith("-"):
            files.append(arg)
        if text is not None:
            from_line = text.startswith("+")
            digits = text.lstrip("+-")
            if not digits.isdigit():
                count = None
            elif text.startswith("-"):
                count = None  # head -n -K: all but the last K lines
            else:
                count = int(digits)
        index += 1
    results: list[tuple[str, int | None]] = []
    for file in files:
        total = line_count(cwd / file)
        if total is None:
            continue
        if count is None:
            printed = total
        elif name == "tail" and from_line:
            printed = max(0, total - count + 1)
        else:
            printed = min(count, total)
        results.append((file, printed))
    return results


# --- rules -----------------------------------------------------------------


def read_hint(md_section: str) -> str:
    return (
        f"Reads are limited to {READ_MAX_LINES} lines of a project file at a time "
        f"and {COMMAND_MAX_LINES} lines per command. Locate the symbol with "
        "`grep -n`, then read the enclosing function or class (about 100 lines) "
        "with Read offset/limit or `sed -n a,bp`. For long Markdown use "
        f'`python3 -I {md_section} <file> "<heading>"` (outline: --toc). '
        "Files under .claude/scratch/ are exempt."
    )


def context_reason(
    tool: str, tool_input: dict[str, Any], tokens: int, limit: int, root: Path
) -> str | None:
    if tokens < limit or tool in HANDBACK_TOOLS:
        return None
    path = tool_input.get("file_path")
    if (
        tool in ("Write", "Edit")
        and isinstance(path, str)
        and in_scratch(Path(path), root)
    ):
        return None
    return (
        f"Context limit: this agent's context is about {tokens // 1000}k tokens, "
        f"past its {limit // 1000}k limit. Stop working now. With the Write tool, "
        "put what remains (state, next edits, open failures, checks not yet run) "
        "in .claude/scratch/<task>/continuation-<n>.md, then deliver your report "
        "(with SubagentHandback when you have it, else as your final message) "
        "ending in your return block: STATUS: PARTIAL and CONTINUATION: <that "
        "path>. Every other tool call is denied from here on."
    )


def read_tool_reason(
    tool_input: dict[str, Any], root: Path, md_section: str
) -> str | None:
    path_text = tool_input.get("file_path")
    if not isinstance(path_text, str) or not path_text:
        return None
    path = Path(path_text)
    rel = guarded(path, root)
    if rel is None:
        return None
    total = line_count(path)
    limit = tool_input.get("limit")
    if total is None or total <= READ_MAX_LINES:
        return None
    if isinstance(limit, int) and 0 < limit <= READ_MAX_LINES:
        return None
    return (
        f"{rel} has {total} lines; pass offset and limit (at most {READ_MAX_LINES}). "
        + read_hint(md_section)
    )


def bash_reason(
    command: str, payload: dict[str, Any], root: Path, md_section: str
) -> str | None:
    commands, bodies = parse_shell(command)
    cwd = Path(payload.get("cwd") or root)
    writes_allowed = in_linked_worktree(str(cwd))
    printed_total = 0
    for item in commands:
        argv = strip_prefixes(item.argv)
        name = Path(argv[0]).name if argv else ""
        args = argv[1:]
        if name == "cd" and args:
            cwd = (cwd / args[0]).resolve()
            continue

        if not writes_allowed:
            targets = list(item.writes)
            if name == "tee":
                targets += [a for a in args if not a.startswith("-")]
            if name == "sed":
                _, in_place, _, files = sed_parts(args)
                if in_place:
                    targets += files
            if name == "perl" and any(a.startswith("-") and "i" in a for a in args):
                targets += [a for a in args if not a.startswith("-")][1:]
            for target in targets:
                rel = guarded(cwd / target, root)
                if rel is not None:
                    return (
                        f"Shell write to {rel} denied: subagents change project files "
                        "with Edit/Write only, because shell edits bypass review and "
                        "are hard to audit. Files under .claude/scratch/ are exempt."
                    )
            if re.fullmatch(r"python[0-9.]*", name):
                code = list(bodies)
                if "-c" in args and args.index("-c") + 1 < len(args):
                    code.append(args[args.index("-c") + 1])
                for text in code:
                    if not PY_WRITE.search(text):
                        continue
                    for literal in STRING_LITERAL.findall(text):
                        if "/" not in literal and "." not in literal:
                            continue
                        rel = guarded(cwd / literal, root)
                        if rel is not None and (
                            "/" in literal or (cwd / literal).exists()
                        ):
                            return (
                                f"Python script writing {rel} denied: subagents change "
                                "project files with Edit/Write only. Files under "
                                ".claude/scratch/ are exempt."
                            )

        if item.captured:
            continue
        reads: list[tuple[str, int | None]] = []
        if name in CAT_LIKE:
            reads = [(a, line_count(cwd / a)) for a in args if not a.startswith("-")]
        elif name == "sed":
            quiet, in_place, scripts, files = sed_parts(args)
            if in_place:
                continue
            for file in files:
                total = line_count(cwd / file)
                if total is not None:
                    reads.append((file, sed_lines(scripts, total) if quiet else total))
        elif name in ("head", "tail"):
            reads = head_tail_lines(name, args, cwd)
        for file, printed in reads:
            rel = guarded(cwd / file, root)
            if rel is None or printed is None:
                continue
            if printed > READ_MAX_LINES:
                return f"This prints {printed} lines of {rel}. " + read_hint(md_section)
            printed_total += printed
    if printed_total > COMMAND_MAX_LINES:
        return (
            f"This command prints {printed_total} lines of project files. "
            + read_hint(md_section)
        )
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--md-section", default="md_section.py")
    options = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        transcript = agent_transcript(payload)
        kind = subagent_type(payload, transcript)
        if not kind or not kind.startswith(options.prefix):
            return 0
        root = project_root(payload)
        tool = str(payload.get("tool_name") or "")
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            return 0
        reason: str | None = None
        tokens = context_tokens(transcript) if transcript is not None else None
        if tokens is not None:
            limit = ROLE_LIMITS.get(kind[len(options.prefix) :], options.limit)
            reason = context_reason(tool, tool_input, tokens, limit, root)
        if reason is None and tool == "Read":
            reason = read_tool_reason(tool_input, root, options.md_section)
        if reason is None and tool == "Bash":
            command = tool_input.get("command")
            if isinstance(command, str) and command:
                reason = bash_reason(command, payload, root, options.md_section)
    except Exception:
        return 0  # a guard bug must never block work
    if reason:
        decision("deny", reason)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
