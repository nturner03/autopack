#!/usr/bin/env python3
"""FTB Quests helper (written for FTB Quests 2101.1.x / MC 1.21.1, file version 13).

Subcommands (run with `python3 -I`; works from any directory):
  ids [N]              print N new 16-hex IDs not used in the quest files
  check                validate the quest files (exit 1 on errors)
  outline [CHAPTER]    text summary of chapters: positions, deps, tasks, text
  render CHAPTER OUT   draw a chapter layout preview PNG (needs Pillow)

CHAPTER is a chapter filename (e.g. `getting_started`) or ID.
`--root DIR` points at another quests directory (default
<repo>/packwiz/config/ftbquests/quests; e.g. the dev server's copy at
infrastructure/dev-server/server/config/ftbquests/quests).

If the pack targets another FTB Quests line, confirm FILE_VERSION and the
task/reward type sets below against a file the mod itself saved, and update
them before trusting `check`.
"""
from __future__ import annotations

import argparse
import math
import re
import secrets
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "packwiz" / "config" / "ftbquests" / "quests"
KUBEJS_ASSETS = Path(__file__).resolve().parents[1] / "packwiz" / "kubejs" / "assets"
FILE_VERSION = 13
SHAPES = {"circle", "square", "rsquare", "diamond", "pentagon", "hexagon",
          "octagon", "heart", "gear", "none"}
TASK_TYPES = {"advancement", "biome", "checkmark", "custom", "dimension", "fluid",
              "gamestage", "interaction", "item", "kill", "location",
              "observation", "stat", "structure", "xp", "forge_energy"}
REWARD_TYPES = {"advancement", "all_table", "choice", "command", "currency",
                "custom", "gamestage", "item", "loot", "random", "toast", "xp",
                "xp_levels"}
LANG_FIELDS = {"title", "quest_subtitle", "quest_desc", "chapter_subtitle"}
INLINE_TEXT = {"title", "subtitle", "description"}
ID_RE = re.compile(r"^[0-9A-F]{16}$")
# FTB Quests parses IDs with Long.parseLong(id, 16): anything >= 8000000000000000
# fails, is replaced by a random ID on every load, and loses its lang keys and
# dependencies.
MAX_ID = 0x7FFFFFFFFFFFFFFF


# ---------------------------------------------------------------- SNBT parser

class SNBTError(ValueError):
    pass


class _Parser:
    def __init__(self, text: str, name: str):
        self.s, self.i, self.name = text, 0, name

    def err(self, msg):
        line = self.s.count("\n", 0, self.i) + 1
        raise SNBTError(f"{self.name}:{line}: {msg}")

    def ws(self):
        s, n = self.s, len(self.s)
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n,":
                self.i += 1
            elif c == "/" and s.startswith("//", self.i):
                while self.i < n and s[self.i] != "\n":
                    self.i += 1
            else:
                break

    def value(self):
        self.ws()
        if self.i >= len(self.s):
            self.err("unexpected end of file")
        c = self.s[self.i]
        if c == "{":
            return self.compound()
        if c == "[":
            return self.array()
        if c in "\"'":
            return self.string()
        return self.bare()

    def compound(self):
        self.i += 1
        out = {}
        while True:
            self.ws()
            if self.i >= len(self.s):
                self.err("unterminated compound")
            if self.s[self.i] == "}":
                self.i += 1
                return out
            key = self.string() if self.s[self.i] in "\"'" else self.word(key=True)
            self.ws()
            if self.i >= len(self.s) or self.s[self.i] != ":":
                self.err(f"expected ':' after key {key!r}")
            self.i += 1
            if key in out:
                self.err(f"duplicate key {key!r}")
            out[key] = self.value()

    def array(self):
        self.i += 1
        m = re.match(r"\s*[BIL]\s*;", self.s[self.i:])
        if m:
            self.i += m.end()
        out = []
        while True:
            self.ws()
            if self.i >= len(self.s):
                self.err("unterminated list")
            if self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.value())

    def string(self):
        q = self.s[self.i]
        self.i += 1
        buf = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                nxt = self.s[self.i + 1:self.i + 2]
                buf.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                self.i += 2
                continue
            if c == q:
                self.i += 1
                return "".join(buf)
            buf.append(c)
            self.i += 1
        self.err("unterminated string")

    def word(self, key=False):
        pat = r"[A-Za-z0-9_.+\-]+" if key else r"[A-Za-z0-9_.+\-:]+"
        m = re.compile(pat).match(self.s, self.i)
        if not m:
            self.err(f"unexpected character {self.s[self.i]!r}")
        self.i = m.end()
        return m.group()

    def bare(self):
        w = self.word()
        if w in ("true", "false"):
            return w == "true"
        m = re.fullmatch(r"(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)([bBsSlLfFdD]?)", w)
        if m:
            num, suf = m.groups()
            if suf.lower() in ("f", "d") or "." in num or "e" in num.lower():
                return float(num)
            return int(num)
        return w


def parse_snbt(path: Path):
    p = _Parser(path.read_text(encoding="utf-8"), str(path))
    v = p.value()
    p.ws()
    if p.i != len(p.s):
        p.err("trailing content")
    return v


# ---------------------------------------------------------------- loading

class QuestFiles:
    def __init__(self, root: Path):
        self.root = root
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.data = self._load(root / "data.snbt")
        self.groups = self._load(root / "chapter_groups.snbt")
        self.lang = self._load(root / "lang" / "en_us.snbt") or {}
        self.chapters = {}
        for f in sorted((root / "chapters").glob("*.snbt")):
            ch = self._load(f)
            if ch is not None:
                self.chapters[f.stem] = ch

    def _load(self, path: Path):
        if not path.exists():
            self.errors.append(f"missing {path}")
            return None
        try:
            return parse_snbt(path)
        except SNBTError as e:
            self.errors.append(f"parse error: {e}")
            return None

    def chapter(self, key: str):
        if key in self.chapters:
            return key, self.chapters[key]
        for name, ch in self.chapters.items():
            if ch.get("id") == key.upper():
                return name, ch
        sys.exit(f"no chapter {key!r}; have: {', '.join(self.chapters)}")

    def text(self, kind: str, oid: str, field: str = "title", default=""):
        v = self.lang.get(f"{kind}.{oid}.{field}", default)
        return " ".join(v) if isinstance(v, list) else v

    def all_ids(self) -> dict[str, str]:
        """Map every object ID to the object kind that owns it."""
        ids: dict[str, str] = {}

        def add(oid, kind, where):
            if not isinstance(oid, str) or not ID_RE.match(oid):
                self.errors.append(f"{where}: bad ID {oid!r} (need 16 uppercase hex)")
                return
            if int(oid, 16) > MAX_ID:
                self.errors.append(f"{where}: ID {oid} is >= 8000000000000000; FTB Quests "
                                   "will replace it on load (IDs must start with 0-7)")
            if oid in ids:
                self.errors.append(f"{where}: duplicate ID {oid}")
            ids[oid] = kind

        for g in (self.groups or {}).get("chapter_groups", []):
            add(g.get("id"), "chapter_group", "chapter_groups.snbt")
        for name, ch in self.chapters.items():
            add(ch.get("id"), "chapter", name)
            for q in ch.get("quests", []):
                add(q.get("id"), "quest", name)
                for t in q.get("tasks", []):
                    add(t.get("id"), "task", name)
                for r in q.get("rewards", []):
                    add(r.get("id"), "reward", name)
            for ln in ch.get("quest_links", []):
                add(ln.get("id"), "quest_link", name)
        for f in sorted((self.root / "reward_tables").glob("*.snbt")):
            t = self._load(f)
            if t:
                add(t.get("id"), "reward_table", f.name)
        return ids


# ---------------------------------------------------------------- check

def check(qf: QuestFiles) -> int:
    E, W = qf.errors, qf.warnings
    ids = qf.all_ids()
    d = qf.data or {}
    if d and d.get("version") != FILE_VERSION:
        E.append(f"data.snbt: version {d.get('version')} != {FILE_VERSION}")
    group_ids = {g.get("id") for g in (qf.groups or {}).get("chapter_groups", [])}
    quest_ids = {i for i, k in ids.items() if k == "quest"}
    orders = {}
    by_group = {}
    for name, ch in qf.chapters.items():
        by_group.setdefault(ch.get("group", ""), []).append(ch.get("order_index"))
    for g, idx in by_group.items():
        if sorted(i for i in idx if isinstance(i, int)) != list(range(len(idx))):
            W.append(f"group {g or '(none)'}: order_index {sorted(idx, key=str)} is not 0..{len(idx) - 1}; "
                     "FTB Quests rewrites it on save, so a partial deploy can misorder the sidebar")

    for name, ch in qf.chapters.items():
        where = f"chapters/{name}.snbt"
        if ch.get("filename") != name:
            E.append(f"{where}: filename {ch.get('filename')!r} != file stem {name!r}")
        g = ch.get("group", "")
        if g and g not in group_ids:
            E.append(f"{where}: group {g} not in chapter_groups.snbt")
        # FTB Quests sorts each group by order_index on load but saves the
        # 0-based position in the group, so use that numbering here too.
        oi = ch.get("order_index")
        if (g, oi) in orders:
            W.append(f"{where}: order_index {oi} also used by {orders[(g, oi)]} in the same group")
        orders[(g, oi)] = name
        if not qf.text("chapter", ch.get("id", "")):
            E.append(f"{where}: no lang title for chapter {ch.get('id')}")
        for k in INLINE_TEXT & ch.keys():
            E.append(f"{where}: inline {k!r} on chapter; move it to lang/en_us.snbt")
        shape = ch.get("default_quest_shape", "")
        if shape and shape not in SHAPES:
            E.append(f"{where}: unknown default_quest_shape {shape!r}")
        for im in ch.get("images", []):
            image = str(im.get("image", ""))
            ns = image.split(":")[0] if ":" in image else ""
            # Images in the pack's own namespaces must ship in kubejs/assets;
            # other namespaces come from mod jars and aren't checked here.
            if (KUBEJS_ASSETS / ns).is_dir() and not image_file(image):
                E.append(f"{where}: chapter image {image!r} is not in packwiz/kubejs/assets "
                         "(build it with scripts/texture.py build)")
            if "x" not in im or "y" not in im:
                E.append(f"{where}: chapter image {image!r} missing x/y")

        quests = ch.get("quests", [])
        for q in quests:
            qid = q.get("id", "?")
            qw = f"{where} quest {qid}"
            for k in INLINE_TEXT & q.keys():
                E.append(f"{qw}: inline {k!r}; move it to lang/en_us.snbt")
            if "x" not in q or "y" not in q:
                E.append(f"{qw}: missing x/y")
            if q.get("shape") and q["shape"] not in SHAPES:
                E.append(f"{qw}: unknown shape {q['shape']!r}")
            title = qf.text("quest", qid)
            tasks = q.get("tasks", [])
            if not tasks:
                # In game a task-less quest never completes, even with its deps done (FTB Quests
                # 2101.1.37, record 2026-10-30-phase2-quests): gate nodes take one checkmark task.
                E.append(f"{qw}: no tasks (never completes in game; give a gate node one checkmark task)")
            if not title and not (len(tasks) == 1 and tasks[0].get("type") != "checkmark"):
                W.append(f"{qw}: no lang title (FTB falls back to the task name)")
            for dep in q.get("dependencies", []):
                if dep not in quest_ids:
                    E.append(f"{qw}: dependency {dep} is not a quest")
                if dep == qid:
                    E.append(f"{qw}: depends on itself")
            for t in tasks:
                tt = t.get("type")
                if tt not in TASK_TYPES:
                    W.append(f"{qw}: task type {tt!r} not in the known list")
                if tt == "item" and "item" not in t:
                    E.append(f"{qw}: item task {t.get('id')} has no item")
                if tt == "item" and t.get("consume_items"):
                    W.append(f"{qw}: item task {t.get('id')} consumes items; confirm the owner asked for a delivery quest")
            for r in q.get("rewards", []):
                if r.get("type") not in REWARD_TYPES:
                    W.append(f"{qw}: reward type {r.get('type')!r} not in the known list")
        for a_i, a in enumerate(quests):
            for b in quests[a_i + 1:]:
                if "x" not in a or "x" not in b:
                    continue
                dist = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                ra = a.get("size", ch.get("default_quest_size", 1.0)) / 2
                rb = b.get("size", ch.get("default_quest_size", 1.0)) / 2
                # Size-1 quests one cell apart is normal FTB spacing; only flag
                # nodes whose centres sit closer than that.
                if dist < 0.6 * (ra + rb):
                    E.append(f"{where}: quests {a['id']} and {b['id']} overlap ({dist:.2f} apart)")
                elif dist < 0.95 * (ra + rb):
                    W.append(f"{where}: quests {a['id']} and {b['id']} crowd each other ({dist:.2f} apart)")
        for ln in ch.get("quest_links", []):
            if ln.get("linked_quest") not in quest_ids:
                E.append(f"{where}: quest_link {ln.get('id')} points at unknown quest")

    # dependency cycles
    deps = {q["id"]: q.get("dependencies", []) for ch in qf.chapters.values()
            for q in ch.get("quests", []) if "id" in q}
    state: dict[str, int] = {}

    def visit(n, path):
        if state.get(n) == 1:
            E.append("dependency loop: " + " -> ".join(path + [n]))
            return
        if state.get(n) == 2:
            return
        state[n] = 1
        for m in deps.get(n, []):
            visit(m, path + [n])
        state[n] = 2

    for n in deps:
        visit(n, [])

    # lang keys
    for key, val in qf.lang.items():
        m = re.fullmatch(r"([a-z_]+)\.([0-9A-F]{16})\.([a-z_]+)", key)
        if not m:
            W.append(f"lang: unrecognised key {key!r}")
            continue
        kind, oid, field = m.groups()
        if field not in LANG_FIELDS:
            W.append(f"lang: unknown field in {key!r}")
        # the quest file itself has id 1 (BaseQuestFile, FTB Quests 2101.1.37): file.0000000000000001.title
        if kind == "file" and oid == "0000000000000001":
            continue
        if oid not in ids:
            E.append(f"lang: {key} refers to a missing object")
        elif ids[oid] != kind:
            E.append(f"lang: {key} is a {ids[oid]}, not a {kind}")
        lines = val if isinstance(val, list) else [val]
        for ln in lines:
            if not isinstance(ln, str):
                E.append(f"lang: {key} has a non-string line")
                continue
            if "\\n" in ln or "\n" in ln:
                W.append(f"lang: {key} embeds a newline; use separate list lines")
            if re.search(r"&[^0-9a-fk-or\s]", ln):
                W.append(f"lang: {key} has '&' not followed by a format code: {ln[:60]!r}")
            for cid in re.findall(r'"change_page"[^}]*?"value"\s*:\s*"([0-9A-F]{16})"', ln):
                if cid not in ids:
                    E.append(f"lang: {key} links to missing object {cid}")

    for w in W:
        print("warning:", w)
    for e in E:
        print("ERROR:", e)
    n_q = sum(len(c.get("quests", [])) for c in qf.chapters.values())
    print(f"{len(qf.chapters)} chapter(s), {n_q} quest(s): {len(E)} error(s), {len(W)} warning(s)")
    return 1 if E else 0


# ---------------------------------------------------------------- outline

def label(qf: QuestFiles, q: dict) -> str:
    """Quest title, or what FTB Quests falls back to: the first task's item."""
    title = qf.text("quest", q.get("id", ""))
    if title:
        return title
    tasks = q.get("tasks", [])
    if tasks and tasks[0].get("type") == "item":
        return "(" + tasks[0].get("item", {}).get("id", "?").split(":")[-1] + ")"
    return "(untitled " + q.get("id", "?") + ")"


def outline(qf: QuestFiles, key: str | None):
    names = [qf.chapter(key)[0]] if key else sorted(
        qf.chapters, key=lambda n: qf.chapters[n].get("order_index", 0))
    for name in names:
        ch = qf.chapters[name]
        cid = ch.get("id")
        print(f"# {qf.text('chapter', cid)}  [{name} {cid}] order={ch.get('order_index')} "
              f"group={ch.get('group') or '-'} default_shape={ch.get('default_quest_shape') or '(file)'}")
        titles = {q["id"]: label(qf, q) for q in ch.get("quests", [])}
        for q in sorted(ch.get("quests", []), key=lambda q: (q.get("x", 0), q.get("y", 0))):
            qid = q["id"]
            extra = []
            if q.get("shape"):
                extra.append(q["shape"])
            if q.get("size"):
                extra.append(f"size {q['size']}")
            if q.get("optional"):
                extra.append("optional")
            print(f"- {titles[qid]!r} {qid} @({q.get('x')}, {q.get('y')}) {' '.join(extra)}")
            sub = qf.text("quest", qid, "quest_subtitle")
            if sub:
                print(f"    subtitle: {sub}")
            for dep in q.get("dependencies", []):
                print(f"    after: {titles.get(dep, dep)}")
            for t in q.get("tasks", []):
                desc = t.get("item", {}).get("id") if t.get("type") == "item" else ""
                print(f"    task: {t.get('type')} {desc}".rstrip())
            for r in q.get("rewards", []):
                print(f"    reward: {r.get('type')}")
            n = len(qf.lang.get(f"quest.{qid}.quest_desc", []))
            print(f"    description: {n} line(s)")
        print()


# ---------------------------------------------------------------- render

def _polygon(cx, cy, r, sides, rot=-90):
    return [(cx + r * math.cos(math.radians(rot + i * 360 / sides)),
             cy + r * math.sin(math.radians(rot + i * 360 / sides))) for i in range(sides)]


def image_file(image: str) -> Path | None:
    """The pack file behind a chapter image id (`ns:textures/x.png`), if the pack ships it."""
    m = re.fullmatch(r"([a-z0-9_.-]+):([a-z0-9_./-]+)", image)
    if not m:
        return None
    path = m[2] if m[2].endswith(".png") else m[2] + ".png"
    if not path.startswith("textures/"):
        path = "textures/" + path
    f = KUBEJS_ASSETS / m[1] / path
    return f if f.is_file() else None


def render(qf: QuestFiles, key: str, out: Path, cell: int = 64):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        sys.exit("render needs Pillow (python3 -m pip install pillow)")
    name, ch = qf.chapter(key)
    quests = ch.get("quests", [])
    images = ch.get("images", [])
    links = ch.get("quest_links", [])
    default_shape = ch.get("default_quest_shape") or (qf.data or {}).get("default_quest_shape") or "circle"
    default_size = ch.get("default_quest_size", 1.0)
    pts = [(q["x"], q["y"], q.get("size", default_size)) for q in quests + links]
    pts += [(i["x"], i["y"], max(i.get("width", 1), i.get("height", 1))) for i in images]
    if not pts:
        sys.exit("chapter has nothing to draw")
    pad = 1.5
    minx = min(x - s / 2 for x, _, s in pts) - pad
    maxx = max(x + s / 2 for x, _, s in pts) + pad
    miny = min(y - s / 2 for _, y, s in pts) - pad
    maxy = max(y + s / 2 for _, y, s in pts) + pad + 0.6
    W, H = int((maxx - minx) * cell), int((maxy - miny) * cell)
    img = Image.new("RGB", (W, H), (32, 34, 40))
    dr = ImageDraw.Draw(img)

    def font(sz):
        for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
            try:
                return ImageFont.truetype(f, sz)
            except OSError:
                pass
        return ImageFont.load_default()

    f_label, f_small = font(max(11, cell // 5)), font(max(9, cell // 7))

    def px(x, y):
        return ((x - minx) * cell, (y - miny) * cell)

    # grid: faint every 0.5, stronger every 1
    for gx in range(math.floor(minx * 2), math.ceil(maxx * 2) + 1):
        x = (gx / 2 - minx) * cell
        dr.line([(x, 0), (x, H)], fill=(48, 50, 58) if gx % 2 else (60, 63, 72))
    for gy in range(math.floor(miny * 2), math.ceil(maxy * 2) + 1):
        y = (gy / 2 - miny) * cell
        dr.line([(0, y), (W, y)], fill=(48, 50, 58) if gy % 2 else (60, 63, 72))
    ox, oy = px(0, 0)
    dr.line([(ox - 6, oy), (ox + 6, oy)], fill=(140, 140, 150))
    dr.line([(ox, oy - 6), (ox, oy + 6)], fill=(140, 140, 150))

    for im in sorted(images, key=lambda i: i.get("order", 0)):
        cx, cy = px(im["x"], im["y"])
        w, h = im.get("width", 1) * cell / 2, im.get("height", 1) * cell / 2
        src = image_file(str(im.get("image", "")))
        if src and int(2 * w) > 0 and int(2 * h) > 0:
            pic = Image.open(src).convert("RGBA")
            if src.with_name(src.name + ".mcmeta").is_file() and pic.height > pic.width:
                pic = pic.crop((0, 0, pic.width, pic.width))  # first animation frame
            pic = pic.resize((int(2 * w), int(2 * h)),
                             Image.NEAREST if pic.width <= 64 else Image.LANCZOS)
            alpha = im.get("alpha", 255) / 255
            if alpha < 1:
                pic.putalpha(pic.getchannel("A").point(lambda a: round(a * alpha)))
            img.paste(pic, (int(cx - w), int(cy - h)), pic)
            continue
        dr.rectangle([cx - w, cy - h, cx + w, cy + h], outline=(120, 160, 120))
        dr.text((cx - w + 3, cy - h + 2), "img " + str(im.get("image", ""))[-28:],
                fill=(120, 160, 120), font=f_small)

    by_id = {q["id"]: q for q in quests}
    if not ch.get("default_hide_dependency_lines"):
        for q in quests:
            if q.get("hide_dependency_lines"):
                continue
            for dep in q.get("dependencies", []):
                d = by_id.get(dep)
                if not d:
                    continue  # cross-chapter dependency
                a, b = px(d["x"], d["y"]), px(q["x"], q["y"])
                dr.line([a, b], fill=(150, 150, 165), width=max(2, cell // 22))
                # arrowhead at the dependent quest's edge
                ang = math.atan2(b[1] - a[1], b[0] - a[0])
                r = q.get("size", default_size) * cell / 2
                tip = (b[0] - r * math.cos(ang), b[1] - r * math.sin(ang))
                for s in (-1, 1):
                    dr.line([tip, (tip[0] - 10 * math.cos(ang + s * 0.45),
                                   tip[1] - 10 * math.sin(ang + s * 0.45))],
                            fill=(150, 150, 165), width=2)

    def draw_node(obj, label, colour, outline_col):
        cx, cy = px(obj["x"], obj["y"])
        size = obj.get("size", default_size)
        r = size * cell / 2 * 0.92
        shape = obj.get("shape") or default_shape
        sides = {"diamond": 4, "pentagon": 5, "hexagon": 6, "octagon": 8}.get(shape)
        if shape in ("square", "rsquare"):
            box = [cx - r * .85, cy - r * .85, cx + r * .85, cy + r * .85]
            if shape == "rsquare":
                dr.rounded_rectangle(box, radius=r * .3, fill=colour, outline=outline_col, width=2)
            else:
                dr.rectangle(box, fill=colour, outline=outline_col, width=2)
        elif sides:
            dr.polygon(_polygon(cx, cy, r, sides, -90 if sides != 4 else -90),
                       fill=colour, outline=outline_col, width=2)
        elif shape == "gear":
            gear = []
            for i in range(24):
                rr = r if i % 2 == 0 else r * 0.8
                a = math.radians(i * 15)
                gear.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
            dr.polygon(gear, fill=colour, outline=outline_col, width=2)
        elif shape == "none":
            dr.ellipse([cx - r * .4, cy - r * .4, cx + r * .4, cy + r * .4], outline=outline_col)
        else:  # circle, heart (approximated)
            dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour, outline=outline_col, width=2)
        icon = (obj.get("icon") or {}).get("id", "")
        if not icon:
            tasks = obj.get("tasks", [])
            if tasks and tasks[0].get("type") == "item":
                icon = tasks[0].get("item", {}).get("id", "")
            elif tasks:
                icon = "[" + tasks[0].get("type", "") + "]"
        icon = icon.split(":")[-1]
        max_w = obj.get("size", default_size) * cell * 0.85
        while icon and dr.textlength(icon, font=f_small) > max_w:
            icon = icon[:-2] + "…" if not icon.endswith("…") else icon[:-2] + "…"
        tw = dr.textlength(icon, font=f_small)
        dr.text((cx - tw / 2, cy - cell * 0.08), icon, fill=(15, 15, 20), font=f_small)
        lw = dr.textlength(label, font=f_label)
        dr.text((cx - lw / 2, cy + r + 3), label, fill=(235, 235, 240), font=f_label)

    for q in quests:
        col = (110, 120, 140) if q.get("optional") else (200, 190, 150)
        draw_node(q, label(qf, q), col, (250, 250, 250))
    for ln in links:
        target = next((q for c in qf.chapters.values() for q in c.get("quests", [])
                       if q["id"] == ln.get("linked_quest")), {})
        node = dict(target, **{k: ln[k] for k in ("x", "y", "shape", "size") if k in ln})
        draw_node(node, "→ " + (qf.text("quest", ln.get("linked_quest", "")) or "link"),
                  (130, 170, 200), (250, 250, 250))

    dr.text((8, 6), f"{qf.text('chapter', ch.get('id'))}  ({name})  grid: 1 cell = 1.0",
            fill=(200, 200, 210), font=f_label)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out} ({W}x{H}); x→right, y→down, + marks (0,0)")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ids")
    p.add_argument("n", type=int, nargs="?", default=1)
    sub.add_parser("check")
    p = sub.add_parser("outline")
    p.add_argument("chapter", nargs="?")
    p = sub.add_parser("render")
    p.add_argument("chapter")
    p.add_argument("out", type=Path)
    p.add_argument("--cell", type=int, default=64, help="pixels per grid unit")
    a = ap.parse_args()

    qf = QuestFiles(a.root)
    if a.cmd == "ids":
        used = set(qf.all_ids())
        new = set()
        while len(new) < a.n:
            i = "%016X" % secrets.randbits(63)
            if i not in used:
                new.add(i)
        print("\n".join(sorted(new)))
    elif a.cmd == "check":
        sys.exit(check(qf))
    elif a.cmd == "outline":
        outline(qf, a.chapter)
    elif a.cmd == "render":
        render(qf, a.chapter, a.out, a.cell)


if __name__ == "__main__":
    main()
