#!/usr/bin/env python3
"""Recipe / tag / loot-table index of the dev-server pack.

Usage (run with `python3 -I`):
  recipe_index.py build                 STATIC: index server/mods/*.jar (+ jar-in-jar), the vanilla
                                        server jar, the NeoForge universal jar (c: tags), and packwiz/kubejs/data (overrides last)
  recipe_index.py build --live          LIVE: run `/pexp dump` on the running dev server (pexp_devtools,
                                        through MCPFabric) and index what the game actually loaded,
                                        KubeJS script edits included. --no-trigger reuses the last dump.
  recipe_index.py status                which kind of index this is, and how old
  recipe_index.py makes <item>          recipes whose outputs include <item>
  recipe_index.py uses <item|#tag>      recipes with <item> (or a tag containing it) as input
  recipe_index.py tag <#tag|tag>        resolved members of an item tag (nested tags expanded)
  recipe_index.py tags-of <item>        item tags that contain <item>
  recipe_index.py types [filter]        recipe types with counts (find a mod's machine types)
  recipe_index.py show <recipe-id>      raw JSON of one recipe
  recipe_index.py loot <substring>      loot tables whose id or contents mention <substring>
  recipe_index.py mod <namespace>       counts of recipes/tags/loot a namespace ships
  recipe_index.py raw-cost <item> [n]   best-effort expansion to raw inputs (first recipe
                                        per item; approximate, ignores KubeJS script edits)

The index lives in infrastructure/cache/recipe_index.sqlite. A STATIC index
reflects JSON on disk only: recipes added/removed by KubeJS *scripts* are NOT
in it. A LIVE index is the loaded game at the moment of the dump (item tags
fully resolved): use it to prove a recipe exists, is gone, or has no bypass.
Rebuild after any pack change (live: after the deploy). Jars are read as data;
nothing is executed.
"""

import io
import json
import re
import sqlite3
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "infrastructure" / "dev-server" / "server"
DB = REPO / "infrastructure" / "cache" / "recipe_index.sqlite"
OVERLAY = REPO / "packwiz" / "kubejs" / "data"
LIVE_DUMP = SERVER / "pexp" / "dump"
STARTED_AT = REPO / "infrastructure" / ".state" / "server-started-at"

DATA_RE = re.compile(r"^data/([^/]+)/(recipes?|tags/items?|loot_tables?)/(.+)\.json$")
OUT_KEYS = re.compile(r"result|output", re.I)


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB)


def schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    DROP TABLE IF EXISTS recipes; DROP TABLE IF EXISTS items; DROP TABLE IF EXISTS tags;
    DROP TABLE IF EXISTS loot; DROP TABLE IF EXISTS meta;
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE recipes(id TEXT PRIMARY KEY, type TEXT, source TEXT, json TEXT);
    CREATE TABLE items(recipe TEXT, role TEXT, ref TEXT, count REAL);
    CREATE TABLE tags(tag TEXT, entry TEXT, source TEXT);
    CREATE TABLE loot(id TEXT PRIMARY KEY, source TEXT, json TEXT);
    CREATE INDEX items_ref ON items(ref); CREATE INDEX items_recipe ON items(recipe);
    CREATE INDEX tags_tag ON tags(tag); CREATE INDEX tags_entry ON tags(entry);
    """)


def refs(node, role: str, out: list) -> None:
    """Collect item/tag/fluid references from arbitrary recipe JSON."""
    if isinstance(node, list):
        for x in node:
            refs(x, role, out)
        return
    if not isinstance(node, dict):
        return
    count = node.get("count") or node.get("amount") or 1
    count = count if isinstance(count, (int, float)) else 1
    for key in ("item", "id", "fluid"):
        val = node.get(key)
        if isinstance(val, str) and ":" in val:
            out.append((role, val, count))
            break
    tag = node.get("tag")
    if isinstance(tag, str):
        out.append((role, "#" + tag.lstrip("#"), count))
    for k, v in node.items():
        if isinstance(v, (dict, list)):
            refs(v, "out" if OUT_KEYS.search(k) else role, out)
        elif isinstance(v, str) and OUT_KEYS.search(k) and ":" in v:
            out.append(("out", v, count))


def add_file(db, kind: str, ns: str, path: str, raw: bytes, source: str) -> None:
    try:
        data = json.loads(raw)
    except ValueError:
        return
    rid = f"{ns}:{path}"
    if kind.startswith("recipe"):
        if not isinstance(data, dict):
            return
        db.execute("DELETE FROM items WHERE recipe=?", (rid,))
        db.execute("INSERT OR REPLACE INTO recipes VALUES(?,?,?,?)",
                   (rid, data.get("type", "?"), source, json.dumps(data)))
        found: list = []
        pattern, key = data.get("pattern"), data.get("key")
        if isinstance(pattern, list) and isinstance(key, dict):
            # Shaped: a key ingredient counts once per pattern slot it fills.
            slots = "".join(row for row in pattern if isinstance(row, str))
            for ch, ing in key.items():
                part: list = []
                refs(ing, "in", part)
                found += [(role, ref, slots.count(ch)) for role, ref, _ in part[:1]]
        for k, v in data.items():
            if k not in ("type", "pattern", "key"):
                refs({k: v}, "in", found)
        db.executemany("INSERT INTO items VALUES(?,?,?,?)", [(rid, *f) for f in found])
    elif kind.startswith("tags"):
        if not isinstance(data, dict):
            return
        if data.get("replace"):
            db.execute("DELETE FROM tags WHERE tag=?", (rid,))
        for v in data.get("values", []):
            entry = v.get("id") if isinstance(v, dict) else v
            if isinstance(entry, str):
                db.execute("INSERT INTO tags VALUES(?,?,?)", (rid, entry, source))
    else:
        db.execute("INSERT OR REPLACE INTO loot VALUES(?,?,?)", (rid, source, json.dumps(data)))


def scan_zip(db, z: zipfile.ZipFile, source: str, depth: int = 0) -> int:
    n = 0
    for name in z.namelist():
        m = DATA_RE.match(name)
        if m:
            add_file(db, m.group(2), m.group(1), m.group(3), z.read(name), source)
            n += 1
        elif depth < 2 and name.startswith("META-INF/jarjar/") and name.endswith(".jar"):
            try:
                with zipfile.ZipFile(io.BytesIO(z.read(name))) as inner:
                    n += scan_zip(db, inner, f"{source}>{Path(name).name}", depth + 1)
            except zipfile.BadZipFile:
                pass
    return n


def neoforge_jars() -> list[Path]:
    """The NeoForge universal jar for the version pinned in packwiz/pack.toml."""
    ver = None
    try:
        m = re.search(r'^neoforge\s*=\s*"([^"]+)"', (REPO / "packwiz" / "pack.toml").read_text(), re.M)
        ver = m.group(1) if m else None
    except OSError:
        pass
    base = SERVER / "libraries" / "net" / "neoforged" / "neoforge"
    found = sorted(base.glob(f"{ver}/neoforge-{ver}-universal.jar")) if ver else []
    if not found:
        found = sorted(base.glob("*/neoforge-*-universal.jar"))[-1:]
    if not found:
        print("warning: NeoForge universal jar not found; c: tags missing", file=sys.stderr)
    return found


def build() -> int:
    if not SERVER.is_dir():
        print(f"no server at {SERVER}; run infrastructure/dev-server/bin/install.sh", file=sys.stderr)
        return 2
    db = connect()
    schema(db)
    # Vanilla first, then mods, then the pack's own data overlay.
    vanilla = [p for p in SERVER.glob("libraries/net/minecraft/server/**/*.jar")]
    vanilla += [p for p in SERVER.glob(".fabric/**/*.jar")]
    vanilla += [p for p in SERVER.glob("versions/**/*.jar")]
    # NeoForge's universal jar ships the c: common tags (e.g. c:stones, c:gems/*).
    vanilla += neoforge_jars()
    jars = vanilla + sorted(SERVER.glob("mods/*.jar"))
    total = 0
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as z:
                total += scan_zip(db, z, jar.name)
        except zipfile.BadZipFile:
            print(f"skip unreadable {jar.name}", file=sys.stderr)
    if OVERLAY.is_dir():
        for f in sorted(OVERLAY.rglob("*.json")):
            rel = "data/" + f.relative_to(OVERLAY).as_posix()
            m = DATA_RE.match(rel)
            if m:
                add_file(db, m.group(2), m.group(1), m.group(3), f.read_bytes(), "packwiz/kubejs/data")
                total += 1
    db.executemany("INSERT INTO meta VALUES(?,?)", [("mode", "static"), ("built", str(int(time.time())))])
    db.commit()
    counts = [db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("recipes", "tags", "loot")]
    print(f"indexed {total} files from {len(jars)} jars: {counts[0]} recipes, "
          f"{counts[1]} tag entries, {counts[2]} loot tables -> {DB.relative_to(REPO)}")
    if not vanilla:
        print("warning: vanilla server jar not found; vanilla recipes missing", file=sys.stderr)
    return 0


def trigger_dump() -> int:
    """Run /pexp dump on the dev server through MCPFabric; 0 when it reports success."""
    proc = subprocess.run([sys.executable, "-I", str(REPO / "scripts" / "mcf.py"), "run_command",
                           json.dumps({"command": "pexp dump"}), "--timeout", "300"],
                          capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    if proc.returncode != 0 or "pexp: dumped" not in out:
        print("`/pexp dump` failed. Is the dev server running, with pexp_devtools installed "
              "(infrastructure/dev-server/bin/update-pack.sh installs it)?\n" + out.strip()[-800:],
              file=sys.stderr)
        return 1
    line = next((m for m in re.findall(r"pexp: dumped[^\"]*", out)), "pexp: dumped")
    print(line)
    return 0


def build_live(trigger: bool) -> int:
    if trigger and trigger_dump() != 0:
        return 1
    meta_file = LIVE_DUMP / "meta.json"
    if not meta_file.is_file():
        print(f"no dump at {LIVE_DUMP}; run without --no-trigger on a running server", file=sys.stderr)
        return 2
    meta = json.loads(meta_file.read_text())
    db = connect()
    schema(db)
    for rid, data in json.loads((LIVE_DUMP / "recipes.json").read_text()).items():
        ns, path = rid.split(":", 1)
        add_file(db, "recipe", ns, path, json.dumps(data).encode(), "live")
    item_tags = json.loads((LIVE_DUMP / "tags" / "item.json").read_text())
    db.executemany("INSERT INTO tags VALUES(?,?,?)",
                   [(tag, entry, "live") for tag, members in item_tags.items() for entry in members])
    db.executemany("INSERT INTO loot VALUES(?,?,?)",
                   [(lid, "live", json.dumps(data))
                    for lid, data in json.loads((LIVE_DUMP / "loot.json").read_text()).items()])
    written = int(meta.get("written_ms", 0) // 1000)
    db.executemany("INSERT INTO meta VALUES(?,?)", [
        ("mode", "live"), ("built", str(int(time.time()))), ("dump_written", str(written)),
        ("game_time", str(meta.get("game_time", ""))), ("mods", json.dumps(meta.get("mods", {}))),
    ])
    db.commit()
    c = meta.get("counts", {})
    print(f"indexed live dump ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(written))}): "
          f"{c.get('recipes')} recipes ({c.get('recipes_partial')} partial), {len(item_tags)} item tags, "
          f"{c.get('loot_tables')} loot tables, {len(meta.get('mods', {}))} mods -> {DB.relative_to(REPO)}")
    if c.get("recipes_partial"):
        print("note: partial recipes have only type and result (\"_pexp_partial\" in `show`); "
              "their inputs are not indexed", file=sys.stderr)
    return 0


def meta_get(db, key: str) -> str | None:
    try:
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def status(db) -> str:
    mode = meta_get(db, "mode") or "static (old index, no metadata)"
    built = int(meta_get(db, "built") or 0)
    age = f"built {time.strftime('%Y-%m-%d %H:%M', time.localtime(built))}" if built else "build time unknown"
    if mode != "live":
        return (f"index: STATIC ({age}): jars + packwiz/kubejs/data only; KubeJS script edits are "
                f"NOT included. `recipe_index.py build --live` indexes the loaded game.")
    written = int(meta_get(db, "dump_written") or 0)
    started = int(STARTED_AT.read_text().strip()) if STARTED_AT.is_file() else 0
    stale = " - OLDER than the last server start: rebuild with --live" if started > written else ""
    return (f"index: LIVE dump from {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(written))} "
            f"(game time {meta_get(db, 'game_time')}){stale}")


def norm(ref: str) -> str:
    """Default the namespace to minecraft, keeping a leading # for tags."""
    hashed, bare = ref.startswith("#"), ref.lstrip("#")
    return ("#" if hashed else "") + (bare if ":" in bare else f"minecraft:{bare}")


def tag_members(db, tag: str, seen=None) -> set[str]:
    seen = seen if seen is not None else set()
    tag = tag.lstrip("#")
    if tag in seen:
        return set()
    seen.add(tag)
    out = set()
    for (entry,) in db.execute("SELECT entry FROM tags WHERE tag=?", (tag,)):
        out |= tag_members(db, entry, seen) if entry.startswith("#") else {entry}
    return out


def tags_of(db, item: str) -> set[str]:
    found, frontier = set(), {item}
    while frontier:
        nxt = set()
        for e in frontier:
            for (t,) in db.execute("SELECT tag FROM tags WHERE entry=?", (e,)):
                if t not in found:
                    found.add(t)
                    nxt.add("#" + t)
        frontier = nxt
    return found


def summary(db, rid: str) -> str:
    rtype, = db.execute("SELECT type FROM recipes WHERE id=?", (rid,)).fetchone()
    rows = db.execute("SELECT role, ref, count FROM items WHERE recipe=?", (rid,)).fetchall()
    ins = ", ".join(f"{c:g}x {r}" if c != 1 else r for role, r, c in rows if role == "in")
    outs = ", ".join(f"{c:g}x {r}" if c != 1 else r for role, r, c in rows if role == "out")
    return f"{rid}  [{rtype}]\n    in:  {ins or '-'}\n    out: {outs or '-'}"


def pick_recipe(db, item: str) -> str | None:
    """First recipe for item, crafting preferred, skipping reversible ones
    (block -> 9 ingots when ingots also craft the block)."""
    for (rid,) in db.execute(
            "SELECT DISTINCT r.id FROM recipes r JOIN items i ON i.recipe=r.id "
            "WHERE i.role='out' AND i.ref=? ORDER BY (r.type LIKE '%crafting_shaped%' "
            "OR r.type LIKE '%crafting_shapeless%') DESC, length(r.json)", (item,)):
        reversible = db.execute(
            "SELECT 1 FROM items src JOIN items o ON o.ref=src.ref AND o.role='out' "
            "JOIN items back ON back.recipe=o.recipe AND back.role='in' AND back.ref=? "
            "WHERE src.recipe=? AND src.role='in' LIMIT 1", (item, rid)).fetchone()
        if not reversible:
            return rid
    return None


def raw_cost(db, item: str, mult: float, depth: int, seen: set, acc: dict) -> None:
    rid = None if depth <= 0 or item in seen or item.startswith("#") else pick_recipe(db, item)
    if rid is None:
        acc[item] = acc.get(item, 0) + mult
        return
    outs = db.execute("SELECT count FROM items WHERE recipe=? AND role='out' AND ref=?", (rid, item)).fetchone()
    per = mult / (outs[0] or 1)
    for ref, count in db.execute("SELECT ref, count FROM items WHERE recipe=? AND role='in'", (rid,)):
        raw_cost(db, ref, per * count, depth - 1, seen | {item}, acc)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, args = argv[0], argv[1:]
    if cmd == "build":
        if "--live" in args:
            return build_live(trigger="--no-trigger" not in args)
        return build()
    if not DB.exists():
        print("no index yet; run `recipe_index.py build` (or `build --live`)", file=sys.stderr)
        return 2
    db = connect()
    if cmd == "status":
        print(status(db))
        return 0
    if meta_get(db, "mode") != "live" and cmd in ("makes", "uses", "tag", "tags-of", "raw-cost", "show"):
        print("(static index: KubeJS script edits not included; `build --live` for the loaded game)",
              file=sys.stderr)
    if cmd == "makes" and args:
        ids = [r for (r,) in db.execute(
            "SELECT DISTINCT recipe FROM items WHERE role='out' AND ref=? ORDER BY recipe", (norm(args[0]),))]
        print("\n".join(summary(db, r) for r in ids) or "no recipes produce it")
    elif cmd == "uses" and args:
        ref = norm(args[0])
        keys = {ref} if ref.startswith("#") else {ref} | {"#" + t for t in tags_of(db, ref)}
        q = ",".join("?" * len(keys))
        ids = [r for (r,) in db.execute(
            f"SELECT DISTINCT recipe FROM items WHERE role='in' AND ref IN ({q}) ORDER BY recipe", tuple(keys))]
        print(f"{len(ids)} recipes (matched {sorted(keys)})")
        print("\n".join(summary(db, r) for r in ids[:200]))
        if len(ids) > 200:
            print(f"... {len(ids) - 200} more")
    elif cmd == "tag" and args:
        print("\n".join(sorted(tag_members(db, norm("#" + args[0].lstrip("#")))))
              or "empty or unknown tag")
    elif cmd == "tags-of" and args:
        print("\n".join(sorted(tags_of(db, norm(args[0])))) or "in no item tags")
    elif cmd == "types":
        flt = args[0] if args else ""
        for t, n in db.execute("SELECT type, count(*) FROM recipes WHERE type LIKE ? GROUP BY type "
                               "ORDER BY count(*) DESC", (f"%{flt}%",)):
            print(f"{n:6}  {t}")
    elif cmd == "show" and args:
        row = db.execute("SELECT source, json FROM recipes WHERE id=?", (args[0],)).fetchone()
        print(f"source: {row[0]}\n{json.dumps(json.loads(row[1]), indent=2)}" if row else "unknown recipe id")
    elif cmd == "loot" and args:
        for lid, src in db.execute("SELECT id, source FROM loot WHERE id LIKE ? OR json LIKE ? ORDER BY id",
                                   (f"%{args[0]}%", f"%{args[0]}%")):
            print(f"{lid}  ({src})")
    elif cmd == "mod" and args:
        ns = args[0]
        r = db.execute("SELECT count(*) FROM recipes WHERE id LIKE ?", (f"{ns}:%",)).fetchone()[0]
        o = db.execute("SELECT count(DISTINCT recipe) FROM items WHERE role='out' AND ref LIKE ?", (f"{ns}:%",)).fetchone()[0]
        t = db.execute("SELECT count(DISTINCT tag) FROM tags WHERE tag LIKE ?", (f"{ns}:%",)).fetchone()[0]
        lt = db.execute("SELECT count(*) FROM loot WHERE id LIKE ?", (f"{ns}:%",)).fetchone()[0]
        print(f"{ns}: {r} recipes shipped, {o} recipes output its items, {t} item tags, {lt} loot tables")
    elif cmd == "raw-cost" and args:
        acc: dict = {}
        raw_cost(db, norm(args[0]), 1.0, int(args[1]) if len(args) > 1 else 6, set(), acc)
        for k, v in sorted(acc.items(), key=lambda kv: -kv[1]):
            print(f"{v:10.3f}  {k}")
        print("(approximate: first recipe per item, crafting preferred; check alternatives with `makes`)")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
