#!/usr/bin/env python3
"""Regression checks: keep proving verified claims on every deploy.

Usage (run with `python3 -I`):
  checks.py run                    trigger one `/pexp dump` on the dev server, evaluate every check
  checks.py run --only <id|topic>  only these checks (repeatable or comma-separated; a topic is a
                                   file name without .toml, e.g. 00-platform)
  checks.py run --no-dump          reuse the last dump instead of triggering a new one
  checks.py run --quiet            print only FAIL/skip lines and the summary (deploy.sh uses this)
  checks.py run --list             validate the files and list the checks; evaluates nothing

Checks live in tests/checks/<topic>.toml (or $PEXP_CHECKS_DIR, e.g. a throwaway
pack's own set), one [[check]] table each with `id`, `why`, `kind` and the
kind's fields; tests/README.md documents every kind. Dump-based kinds read the
live dump that pexp_devtools writes (infrastructure/dev-server/server/pexp/dump/),
so they see the game as loaded, KubeJS script edits included. Log kinds read
the server's logs since its last start; tests/log-noise.txt is the allowlist.

Prints one line per check (`pass|FAIL|skip <id> - <detail>`) and writes
docs/local/checks-last.json. Exit 0 = all pass, 1 = a check failed,
3 = nothing failed but some checks could not be evaluated (skip),
2 = invalid check files or usage.
"""

import json
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "infrastructure" / "dev-server" / "server"
DUMP = SERVER / "pexp" / "dump"
STARTED_AT = REPO / "infrastructure" / ".state" / "server-started-at"
# deploy.sh --reload/--quests writes this just before reloading (manual reloads do not)
RELOADED_AT = REPO / "infrastructure" / ".state" / "server-reloaded-at"
CHECKS_DIR = Path(os.environ["PEXP_CHECKS_DIR"]) if os.environ.get("PEXP_CHECKS_DIR") else REPO / "tests" / "checks"
NOISE_FILE = REPO / "tests" / "log-noise.txt"
RESULT_FILE = REPO / "docs" / "local" / "checks-last.json"
LOGS = {
    "latest": SERVER / "logs" / "latest.log",
    "kubejs_server": SERVER / "logs" / "kubejs" / "server.log",
    "kubejs_startup": SERVER / "logs" / "kubejs" / "startup.log",
}
REGISTRIES = ("item", "block", "fluid", "entity_type")

# kind -> (required fields, optional fields with defaults, needs the dump)
KINDS = {
    "recipe_exists": ({"recipe": str}, {}, True),
    "recipe_absent": ({"recipe": str}, {}, True),
    "only_makers": ({"item": str, "recipes": list}, {}, True),
    "makes_any": ({"item": str}, {}, True),
    "tag_contains": ({"tag": str, "item": str}, {"registry": "item"}, True),
    "tag_lacks": ({"tag": str, "item": str}, {"registry": "item"}, True),
    "loot_mentions": ({"table": str, "item": str}, {}, True),
    "loot_lacks": ({"table": str, "item": str}, {}, True),
    "item_exists": ({"item": str}, {"registry": "item"}, True),
    "mod_loaded": ({"mod": str}, {"version": ""}, True),
    "log_clean": ({}, {"allow": []}, False),
    "log_matches": ({"pattern": str}, {"log": "latest"}, False),
    "command": ({"command": str, "expect": str}, {}, False),
}
COMMON = {"id", "why", "kind"}
OUT_KEYS = re.compile(r"result|output", re.I)
# `[31Oct2026 12:16:19.994] [main/ERROR] [logger]: msg` (latest.log) or `[12:16:25] [ERROR] msg` (KubeJS)
LOG_LEVEL = re.compile(r"^\[[^\]]*\] \[(?:[^\]]*/)?(ERROR|FATAL)\]")
LOG_TIME = re.compile(r"^\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2})[.\]]")
DONE = re.compile(r"\]: Done \(\d")


class Invalid(Exception):
    pass


# ---- loading and validation -------------------------------------------------

def norm(ref: str) -> str:
    """Default the namespace to minecraft and drop a leading #."""
    ref = ref.strip().lstrip("#")
    return ref if ":" in ref else f"minecraft:{ref}"


def load_checks() -> list[dict]:
    if not CHECKS_DIR.is_dir():
        return []
    checks, seen, errors = [], {}, []
    for path in sorted(CHECKS_DIR.glob("*.toml")):
        topic = path.stem
        try:
            data = tomllib.loads(path.read_text())
        except (tomllib.TOMLDecodeError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        extra = set(data) - {"check"}
        if extra:
            errors.append(f"{path.name}: unknown top-level keys {sorted(extra)} (only [[check]] tables)")
        for n, c in enumerate(data.get("check", []), 1):
            where = f"{path.name} check #{n}"
            try:
                checks.append(validate(c, topic, where))
            except Invalid as exc:
                errors.append(f"{where}: {exc}")
                continue
            cid = c["id"]
            if cid in seen:
                errors.append(f"{where}: duplicate id {cid!r} (also in {seen[cid]})")
            seen[cid] = path.name
    if errors:
        raise Invalid("\n".join(errors))
    return checks


def validate(c: dict, topic: str, where: str) -> dict:
    for f in ("id", "why", "kind"):
        if not isinstance(c.get(f), str) or not c[f].strip():
            raise Invalid(f"missing or empty `{f}`")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", c["id"]):
        raise Invalid(f"id {c['id']!r}: use letters, digits and . _ : - only")
    kind = c["kind"]
    if kind not in KINDS:
        raise Invalid(f"unknown kind {kind!r} (known: {', '.join(KINDS)})")
    required, optional, _ = KINDS[kind]
    unknown = set(c) - COMMON - set(required) - set(optional)
    if unknown:
        raise Invalid(f"kind {kind}: unknown fields {sorted(unknown)}")
    out = dict(optional, **c, topic=topic)
    for f, typ in required.items():
        if f not in c:
            raise Invalid(f"kind {kind}: missing `{f}`")
    for f in list(required) + list(optional):
        want = type(optional[f]) if f in optional else required[f]
        if not isinstance(out[f], want):
            raise Invalid(f"`{f}` must be a {want.__name__}")
    if isinstance(out.get("recipes"), list) and not all(isinstance(r, str) for r in out["recipes"]):
        raise Invalid("`recipes` must be a list of recipe ids")
    if isinstance(out.get("allow"), list) and not all(isinstance(r, str) for r in out["allow"]):
        raise Invalid("`allow` must be a list of regexes")
    if out.get("registry", "item") not in REGISTRIES:
        raise Invalid(f"registry must be one of {', '.join(REGISTRIES)}")
    if kind == "log_matches" and out["log"] not in LOGS:
        raise Invalid(f"log must be one of {', '.join(LOGS)}")
    for f in ("pattern", "expect"):
        if f in out:
            compile_re(out[f], f)
    for r in out.get("allow", []):
        compile_re(r, "allow")
    return out


def compile_re(pattern: str, field: str) -> re.Pattern:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise Invalid(f"`{field}` is not a valid regex: {exc}")


def load_noise() -> list[re.Pattern]:
    if not NOISE_FILE.is_file():
        return []
    out = []
    for n, line in enumerate(NOISE_FILE.read_text().splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                out.append(re.compile(line))
            except re.error as exc:
                raise Invalid(f"{NOISE_FILE.name}:{n}: not a valid regex: {exc}")
    return out


# ---- the live dump ------------------------------------------------------------

def mcf(args: list[str], timeout: float) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-I", str(REPO / "scripts" / "mcf.py"), *args,
                           "--timeout", str(timeout)], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def trigger_dump() -> str | None:
    """Run /pexp dump; None on success, else the reason."""
    rc, out = mcf(["run_command", json.dumps({"command": "pexp dump"})], 300)
    if rc != 0 or "pexp: dumped" not in out:
        return ("`/pexp dump` failed (is the dev server running with pexp_devtools?): "
                + " ".join(out.split())[-300:])
    return None


class Dump:
    def __init__(self) -> None:
        self.meta = json.loads((DUMP / "meta.json").read_text())
        self._cache: dict = {}

    def _load(self, name: str):
        if name not in self._cache:
            self._cache[name] = json.loads((DUMP / name).read_text())
        return self._cache[name]

    @property
    def recipes(self) -> dict:
        return self._load("recipes.json")

    @property
    def loot(self) -> dict:
        return self._load("loot.json")

    def ids(self, registry: str) -> set:
        key = f"ids:{registry}"
        if key not in self._cache:
            self._cache[key] = set(self._load("ids.json").get(registry, []))
        return self._cache[key]

    def tags(self, registry: str) -> dict:
        return self._load(f"tags/{registry}.json")

    def makers(self, item: str) -> list[str]:
        if "makers" not in self._cache:
            idx: dict = {}
            for rid, data in self.recipes.items():
                for ref in outputs(data):
                    idx.setdefault(ref, set()).add(rid)
            self._cache["makers"] = idx
        return sorted(self._cache["makers"].get(item, ()))


def outputs(node, out: bool = False, found: set | None = None) -> set:
    """Item/fluid ids under result/output keys of arbitrary recipe JSON."""
    found = set() if found is None else found
    if isinstance(node, list):
        for x in node:
            outputs(x, out, found)
    elif isinstance(node, dict):
        if out:
            for key in ("item", "id", "fluid"):
                if isinstance(node.get(key), str) and ":" in node[key]:
                    found.add(node[key])
                    break
        for k, v in node.items():
            child_out = out or bool(OUT_KEYS.search(k))
            if isinstance(v, (dict, list)):
                outputs(v, child_out, found)
            elif isinstance(v, str) and child_out and OUT_KEYS.search(k) and ":" in v:
                found.add(v)
    return found


def mentions(node, value: str) -> bool:
    if isinstance(node, str):
        return node == value
    if isinstance(node, list):
        return any(mentions(x, value) for x in node)
    if isinstance(node, dict):
        return any(mentions(v, value) for v in node.values())
    return False


def short(items, n: int = 5) -> str:
    items = list(items)
    return ", ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "")


# ---- evaluation -----------------------------------------------------------------

def stamp(path: Path) -> int:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return 0


def started_at() -> int:
    return stamp(STARTED_AT)


def current_lines(lines: list[str]) -> list[str]:
    """latest.log lines that describe the server's current state: the startup
    (up to `Done`) plus everything from the last deploy.sh reload on. Lines
    between those came from scripts/data the reload replaced."""
    reloaded = stamp(RELOADED_AT)
    if reloaded <= started_at():
        return lines
    done = next((i for i, ln in enumerate(lines) if DONE.search(ln)), None)
    if done is None:
        return lines
    for i in range(done + 1, len(lines)):
        m = LOG_TIME.match(lines[i])
        if m:
            try:
                t = time.mktime(time.strptime(m.group(1), "%d%b%Y %H:%M:%S"))
            except ValueError:
                return lines
            if t >= reloaded:
                return lines[:done + 1] + lines[i:]
    return lines[:done + 1]


def log_lines(name: str) -> list[str] | None:
    """Lines of a server log written since the last server start; None if absent."""
    path = LOGS[name]
    if not path.is_file() or path.stat().st_mtime < started_at():
        return None
    return path.read_text(errors="replace").splitlines()


def evaluate(c: dict, dump: Dump | None, noise: list[re.Pattern]) -> tuple[str, str]:
    kind = c["kind"]
    if KINDS[kind][2] and dump is None:
        return "skip", "no dump"
    if kind in ("recipe_exists", "recipe_absent"):
        rid = norm(c["recipe"])
        present = rid in dump.recipes
        ok = present == (kind == "recipe_exists")
        return ("pass" if ok else "FAIL"), f"{rid} {'loaded' if present else 'not loaded'}"
    if kind == "makes_any":
        item = norm(c["item"])
        makers = dump.makers(item)
        return ("pass", f"{len(makers)} recipes: {short(makers, 3)}") if makers else ("FAIL", f"no recipe outputs {item}")
    if kind == "only_makers":
        item, allowed = norm(c["item"]), {norm(r) for r in c["recipes"]}
        makers = set(dump.makers(item))
        extra, missing = sorted(makers - allowed), sorted(allowed - makers)
        if extra or missing:
            parts = [f"unexpected makers: {short(extra)}"] if extra else []
            parts += [f"listed but not making it: {short(missing)}"] if missing else []
            return "FAIL", f"{item}: " + "; ".join(parts)
        return "pass", (f"{item}: made only by {short(sorted(makers))}" if makers
                        else f"{item}: no recipe makes it, as listed")
    if kind in ("tag_contains", "tag_lacks"):
        reg, tag, item = c["registry"], norm(c["tag"]), norm(c["item"])
        tags = dump.tags(reg)
        if tag not in tags and kind == "tag_contains":
            return "FAIL", f"{reg} tag #{tag} does not exist"
        member = item in tags.get(tag, [])
        ok = member == (kind == "tag_contains")
        return ("pass" if ok else "FAIL"), f"#{tag} {'contains' if member else 'lacks'} {item}"
    if kind in ("loot_mentions", "loot_lacks"):
        table, item = norm(c["table"]), norm(c["item"])
        if table not in dump.loot:
            return "FAIL", f"loot table {table} not loaded"
        hit = mentions(dump.loot[table], item)
        ok = hit == (kind == "loot_mentions")
        return ("pass" if ok else "FAIL"), f"{table} {'mentions' if hit else 'does not mention'} {item}"
    if kind == "item_exists":
        reg, item = c["registry"], norm(c["item"])
        ok = item in dump.ids(reg)
        return ("pass" if ok else "FAIL"), f"{reg} {item} {'registered' if ok else 'not registered'}"
    if kind == "mod_loaded":
        mods = dump.meta.get("mods", {})
        ver = mods.get(c["mod"])
        if ver is None:
            return "FAIL", f"mod {c['mod']} not loaded"
        if c["version"] and ver != c["version"]:
            return "FAIL", f"mod {c['mod']} is {ver}, expected {c['version']}"
        return "pass", f"{c['mod']} {ver}"
    if kind == "log_clean":
        allow = noise + [re.compile(r) for r in c["allow"]]
        bad, seen_any = [], False
        for name in LOGS:
            lines = log_lines(name)
            if lines is None:
                continue
            seen_any = True
            lines = current_lines(lines) if name == "latest" else lines
            for line in lines:
                if LOG_LEVEL.match(line) and not any(p.search(line) for p in allow):
                    bad.append(f"{name}: {line.strip()[:200]}")
        if not seen_any:
            return "skip", "no server log since the last start"
        if bad:
            return "FAIL", f"{len(bad)} ERROR/FATAL lines not in tests/log-noise.txt; first: {bad[0]}"
        return "pass", "no unexpected ERROR/FATAL lines in the startup or since the last reload"
    if kind == "log_matches":
        lines = log_lines(c["log"])
        if lines is None:
            return "skip", f"no {c['log']} log since the last start"
        pat = re.compile(c["pattern"])
        hit = next((ln for ln in lines if pat.search(ln)), None)
        return ("pass", hit.strip()[:160]) if hit else ("FAIL", f"no line matches /{c['pattern']}/ in {c['log']}")
    if kind == "command":
        rc, out = mcf(["run_command", json.dumps({"command": c["command"].lstrip("/")})], 60)
        if rc == 2:
            return "skip", "server bridge unreachable"
        text = out
        try:
            res = json.loads(out)
            if isinstance(res, dict) and "output" in res:
                o = res["output"]
                text = "\n".join(map(str, o)) if isinstance(o, list) else str(o)
        except ValueError:
            pass
        if rc == 0 and re.search(c["expect"], text):
            return "pass", " ".join(text.split())[:160]
        return "FAIL", f"/{c['command']}: output does not match /{c['expect']}/: {' '.join(text.split())[:160]}"
    raise AssertionError(kind)


# ---- CLI ----------------------------------------------------------------------------

def usage(code: int) -> int:
    print(__doc__, file=sys.stderr if code else sys.stdout)
    return code


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        return usage(0 if argv else 2)
    if argv[0] != "run":
        return usage(2)
    only: set[str] = set()
    flags = set()
    args = iter(argv[1:])
    for a in args:
        if a == "--only":
            v = next(args, None)
            if not v:
                return usage(2)
            only |= {x.strip() for x in v.split(",") if x.strip()}
        elif a in ("--no-dump", "--quiet", "--list"):
            flags.add(a)
        else:
            return usage(2)
    try:
        checks = load_checks()
        noise = load_noise()
    except Invalid as exc:
        print(f"invalid checks:\n{exc}", file=sys.stderr)
        return 2
    if only:
        unknown = only - {c["id"] for c in checks} - {c["topic"] for c in checks}
        if unknown:
            print(f"--only: no check or topic named {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        checks = [c for c in checks if c["id"] in only or c["topic"] in only]
    rel = CHECKS_DIR.relative_to(REPO) if CHECKS_DIR.is_relative_to(REPO) else CHECKS_DIR
    if not checks:
        print(f"no checks in {rel}")
        return 0
    if "--list" in flags:
        for c in checks:
            print(f"{c['id']:40} {c['kind']:14} {c['topic']}  - {c['why']}")
        print(f"{len(checks)} checks in {rel}: valid")
        return 0

    t0 = time.time()
    dump, dump_note = None, ""
    if any(KINDS[c["kind"]][2] for c in checks):
        reason = None if "--no-dump" in flags else trigger_dump()
        if reason:
            dump_note = reason
        elif not (DUMP / "meta.json").is_file():
            dump_note = f"no dump at {DUMP.relative_to(REPO)}"
        else:
            dump = Dump()
            written = int(dump.meta.get("written_ms", 0) // 1000)
            stale = " - OLDER than the last server start" if written < started_at() else ""
            dump_note = (f"dump {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(written))}"
                         f" ({dump.meta.get('counts', {}).get('recipes')} recipes){stale}")
        print(f"checks: {dump_note}")

    results = []
    for c in checks:
        try:
            status, detail = evaluate(c, dump, noise)
        except (OSError, ValueError, KeyError) as exc:
            status, detail = "skip", f"could not evaluate: {exc}"
        if status == "skip" and detail == "no dump":
            detail = "no dump (see the `checks:` line above)"
        results.append({"id": c["id"], "topic": c["topic"], "kind": c["kind"], "why": c["why"],
                        "status": status, "detail": detail})
        if status != "pass" or "--quiet" not in flags:
            print(f"{status:4} {c['id']} - {detail}")
    counts = {s: sum(r["status"] == s for r in results) for s in ("pass", "FAIL", "skip")}
    print(f"checks: {counts['pass']} pass, {counts['FAIL']} FAIL, {counts['skip']} skip "
          f"({len(results)} in {rel}, {time.time() - t0:.1f}s) -> {RESULT_FILE.relative_to(REPO)}")
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps({
        "ran_at": int(time.time()), "checks_dir": str(rel), "dump": dump_note,
        "counts": counts, "results": results}, indent=2) + "\n")
    return 1 if counts["FAIL"] else 3 if counts["skip"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
