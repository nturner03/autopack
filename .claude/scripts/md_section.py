"""Print one Markdown section, or a heading outline, with line numbers.

Long design docs, plans and specifications can run to 100 KB or more. Reading one
step section instead of the whole file is the single largest context saving
for agents, so this replaces ad hoc ``sed -n`` ranges.

Usage::

    python3 -I .claude/scripts/md_section.py --toc FILE [--max-level N]
    python3 -I .claude/scripts/md_section.py FILE "heading text" [--no-children]

A section runs from its heading to the next heading of the same or a higher
level. The heading text match is case-insensitive and matches a substring;
when several headings match, the outline of matches is printed instead.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return (line index, level, text) for headings outside fenced blocks."""
    found: list[tuple[int, int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(line)
        if match:
            found.append((index, len(match.group(1)), match.group(2)))
    return found


def print_toc(found: list[tuple[int, int, str]], max_level: int) -> None:
    for index, level, text in found:
        if level <= max_level:
            print(f"{index + 1:>6}  {'  ' * (level - 1)}{'#' * level} {text}")


def section_end(
    found: list[tuple[int, int, str]], position: int, total: int, children: bool
) -> int:
    _, level, _ = found[position]
    for index, other_level, _ in found[position + 1 :]:
        if other_level <= level or not children:
            return index
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("heading", nargs="?", help="heading text to match")
    parser.add_argument("--toc", action="store_true", help="print the outline")
    parser.add_argument("--max-level", type=int, default=3)
    parser.add_argument(
        "--no-children", action="store_true", help="stop at the first subheading"
    )
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    found = headings(lines)
    if args.toc or args.heading is None:
        print_toc(found, args.max_level)
        return 0

    needle = args.heading.casefold()
    matches = [i for i, (_, _, text) in enumerate(found) if needle in text.casefold()]
    exact = [i for i in matches if found[i][2].casefold() == needle]
    if exact:
        matches = exact
    if not matches:
        print(f"no heading matches {args.heading!r}; outline follows", file=sys.stderr)
        print_toc(found, args.max_level)
        return 1
    if len(matches) > 1:
        print(f"{len(matches)} headings match; be more specific:", file=sys.stderr)
        print_toc([found[i] for i in matches], 6)
        return 1

    position = matches[0]
    start = found[position][0]
    end = section_end(found, position, len(lines), not args.no_children)
    for index in range(start, end):
        print(f"{index + 1:>6}\t{lines[index]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
