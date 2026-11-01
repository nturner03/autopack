#!/usr/bin/env python3
"""Pixel-art texture toolkit for the pack (needs Pillow). Method: the pack-art skill.

Art sources live in art/assets/<ns>/textures/<path>.<kind> and compile to
packwiz/kubejs/assets/<ns>/textures/<path>.png (same relative path):
  .grid          hand-written text grid (palette + rows; frames for animation)
  .derive.json   recolour/layer an existing texture (vanilla, a mod's, or ours)
  .compose.json  larger UI art layered from captures and textures
  .png           a finished image copied as is (e.g. studio panorama faces)

Subcommands (run with `python3 -I`; works from any directory):
  find PATTERN               texture ids matching a glob, e.g. '*copper*', 'minecraft:block/tuff*'
  show REF [--grid]          size, frames and colours (dark to light); --grid prints a text grid
  extract REF OUT.png        copy a texture (and its .mcmeta) to a file
  ramp REF [-n N]            a dark-to-light colour ramp from a texture, as JSON (for art/palette.json)
  to-grid REF OUT.grid       write a texture as an editable text grid (starting point for new art)
  render SOURCE OUT.png      compile one art source to a PNG without touching the pack
  build [SOURCE...] [--check]  compile art sources into the pack; --check only reports stale outputs
  preview REF... --out PNG [--ref REF...] [--row] [--kind item|block|ui] [--grey]  review sheet to Read and judge
  lint [PNG...]              check pack textures, sources and startup registrations (exit 1 on errors)
  quantize IN OUT.png (--colors N | --palette)  reduce colours (renders and captures to pixel art)
  panorama-check DIR --out PNG  check six panorama faces and lay them out with their seams

REF is a texture id (`minecraft:item/stick`, `<packns>:block/<name>`),
a .png path, or an art source path. Ids resolve in this order: the pack's
kubejs/assets, the headless client's mods, the dev server's mods, the vanilla
client jar. `--root DIR` changes the repo root (for tests).
"""
from __future__ import annotations

import argparse
import colorsys
import fnmatch
import io
import json
import re
import sys
import tomllib
import zipfile
from functools import lru_cache
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except ImportError:
    sys.exit("texture.py needs Pillow (python3 -m pip install pillow)")

ROOT = Path(__file__).resolve().parents[1]
SOURCE_KINDS = (".grid", ".derive.json", ".compose.json", ".png")
GRID_SYMBOLS = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                "+*%&@$!?~^<>/|()[]{}:;,'\"`_")
# Folders whose textures are 16-64 px pixel art; anything else (gui, quests,
# title panoramas) is UI art with looser rules.
PIXEL_FOLDERS = {"item", "block", "entity", "mob_effect", "particle", "painting"}
DEFAULT_MAX_COLORS = 32


class ArtError(Exception):
    pass


# ---------------------------------------------------------------- paths and lookup

class Repo:
    def __init__(self, root: Path):
        self.root = root
        self.pack_assets = root / "packwiz" / "kubejs" / "assets"
        self.art = root / "art"
        self.art_assets = self.art / "assets"
        self.palette_file = self.art / "palette.json"
        self.startup = root / "packwiz" / "kubejs" / "startup_scripts"

    @lru_cache(maxsize=None)
    def mc_version(self) -> str:
        try:
            data = tomllib.loads((self.root / "packwiz" / "pack.toml").read_text())
            return data["versions"]["minecraft"]
        except (OSError, KeyError, tomllib.TOMLDecodeError):
            return "1.21.1"

    @lru_cache(maxsize=None)
    def jars(self) -> list[Path]:
        infra = self.root / "infrastructure"
        out: list[Path] = []
        seen: set[str] = set()
        for d in (infra / "headless-client" / "instance" / "mods",
                  infra / "dev-server" / "server" / "mods"):
            for j in sorted(d.glob("*.jar")) if d.is_dir() else []:
                if j.name not in seen and not j.name.startswith("mcpfabric"):
                    seen.add(j.name)
                    out.append(j)
        mc = self.mc_version()
        vanilla = infra / "headless-client" / "hmc" / ".minecraft" / "versions" / mc / f"{mc}.jar"
        if vanilla.is_file():
            out.append(vanilla)
        return out

    @lru_cache(maxsize=None)
    def jar_textures(self, jar: Path) -> dict[str, str]:
        """texture id -> member name for every PNG under assets/*/textures/."""
        found = {}
        try:
            with zipfile.ZipFile(jar) as z:
                for n in z.namelist():
                    m = re.fullmatch(r"assets/([a-z0-9_.-]+)/textures/(.+)\.png", n)
                    if m:
                        found.setdefault(f"{m[1]}:{m[2]}", n)
        except (OSError, zipfile.BadZipFile):
            pass
        return found

    def all_texture_ids(self) -> dict[str, str]:
        """texture id -> where it comes from (first match wins, like resolve)."""
        ids: dict[str, str] = {}
        if self.pack_assets.is_dir():
            for p in sorted(self.pack_assets.glob("*/textures/**/*.png")):
                rel = p.relative_to(self.pack_assets)
                ids.setdefault(f"{rel.parts[0]}:{Path(*rel.parts[2:]).with_suffix('').as_posix()}",
                               "pack")
        for jar in self.jars():
            for tid in self.jar_textures(jar):
                ids.setdefault(tid, jar.name)
        return ids

    def source_for(self, png: Path) -> Path | None:
        """The art source that builds a pack PNG, if any."""
        rel = png.relative_to(self.pack_assets).with_suffix("")
        for kind in SOURCE_KINDS:
            cand = self.art_assets / (rel.as_posix() + kind)
            if cand.is_file():
                return cand
        return None

    def output_for(self, source: Path) -> Path:
        rel = source.resolve().relative_to(self.art_assets.resolve()).as_posix()
        for kind in SOURCE_KINDS:
            if rel.endswith(kind):
                return self.pack_assets / (rel[: -len(kind)] + ".png")
        raise ArtError(f"{source}: not an art source ({', '.join(SOURCE_KINDS)})")

    def sources(self) -> list[Path]:
        if not self.art_assets.is_dir():
            return []
        # Names starting with "_" are helpers (derive bases): never built into the pack.
        return sorted(p for p in self.art_assets.rglob("*")
                      if p.is_file() and p.name.endswith(SOURCE_KINDS) and not p.name.startswith("_"))


def parse_id(ref: str) -> tuple[str, str] | None:
    m = re.fullmatch(r"([a-z0-9_.-]+):([a-z0-9_./-]+?)(?:\.png)?", ref)
    if not m or "/" not in m[2]:
        return None
    path = m[2]
    if path.startswith("textures/"):
        path = path[len("textures/"):]
    return m[1], path


class Texture:
    """An RGBA image plus its animation metadata (vertical frame strip)."""

    def __init__(self, img: Image.Image, mcmeta: dict | None = None, origin: str = ""):
        self.img = img.convert("RGBA")
        self.mcmeta = mcmeta
        self.origin = origin

    @property
    def frame_count(self) -> int:
        w, h = self.img.size
        return h // w if self.mcmeta and h % w == 0 and h > w else 1

    def frames(self) -> list[Image.Image]:
        w = self.img.width
        return [self.img.crop((0, i * w, w, (i + 1) * w)) for i in range(self.frame_count)] \
            if self.frame_count > 1 else [self.img]


def load_ref(repo: Repo, ref: str, _stack: tuple = ()) -> Texture:
    """Load a texture id, a PNG path or an art source (rendered)."""
    p = Path(ref)
    if ref.endswith(SOURCE_KINDS[:3]):
        src = p if p.is_absolute() else (Path.cwd() / p if (Path.cwd() / p).exists() else repo.root / p)
        if src.resolve() in _stack:
            raise ArtError(f"{ref}: source refers to itself")
        return render_source(repo, src, _stack + (src.resolve(),))
    if ref.endswith(".png") and not parse_id(ref):
        for cand in (p, Path.cwd() / p, repo.root / p):
            if cand.is_file():
                meta = cand.with_name(cand.name + ".mcmeta")
                return Texture(Image.open(cand), json.loads(meta.read_text()) if meta.is_file() else None,
                               str(cand))
        raise ArtError(f"{ref}: no such file")
    parsed = parse_id(ref)
    if not parsed:
        raise ArtError(f"{ref!r}: not a texture id (ns:item/name), PNG or art source")
    ns, path = parsed
    local = repo.pack_assets / ns / "textures" / f"{path}.png"
    if local.is_file():
        meta = local.with_name(local.name + ".mcmeta")
        return Texture(Image.open(local), json.loads(meta.read_text()) if meta.is_file() else None,
                       "pack")
    tid = f"{ns}:{path}"
    for jar in repo.jars():
        member = repo.jar_textures(jar).get(tid)
        if member:
            with zipfile.ZipFile(jar) as z:
                img = Image.open(io.BytesIO(z.read(member)))
                img.load()
                meta = None
                if member + ".mcmeta" in z.namelist():
                    try:
                        meta = json.loads(z.read(member + ".mcmeta"))
                    except json.JSONDecodeError:
                        meta = {"animation": {}}
            return Texture(img, meta, jar.name)
    hint = "" if repo.jars() else " (no jars found: install the dev server or headless client)"
    raise ArtError(f"{tid}: texture not found in the pack, mods or vanilla{hint}")


# ---------------------------------------------------------------- colours

def hex_to_rgba(s: str) -> tuple[int, int, int, int]:
    s = s.strip()
    if s.lower() in ("transparent", "none", "clear"):
        return (0, 0, 0, 0)
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", s)
    if not m:
        raise ArtError(f"bad colour {s!r} (use #rrggbb, #rrggbbaa or transparent)")
    v = int(m[1], 16)
    return (v >> 16 & 255, v >> 8 & 255, v & 255, int(m[2], 16) if m[2] else 255)


def rgba_to_hex(c) -> str:
    r, g, b, a = c
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


def luma(c) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def colours(img: Image.Image) -> dict[tuple, int]:
    counts: dict[tuple, int] = {}
    for c in img.getdata():
        if c[3] == 0:
            c = (0, 0, 0, 0)
        counts[c] = counts.get(c, 0) + 1
    return counts


def load_palette(repo: Repo) -> dict:
    if not repo.palette_file.is_file():
        return {}
    try:
        return json.loads(repo.palette_file.read_text())
    except json.JSONDecodeError as e:
        raise ArtError(f"{repo.palette_file}: {e}")


def get_ramp(repo: Repo, spec) -> list[tuple]:
    if isinstance(spec, list):
        return [hex_to_rgba(h) for h in spec]
    ramps = load_palette(repo).get("ramps", {})
    if spec not in ramps:
        raise ArtError(f"ramp {spec!r} not in {repo.palette_file} (have: {', '.join(ramps) or 'none'})")
    return [hex_to_rgba(h) for h in ramps[spec]]


def palette_colours(repo: Repo) -> set[tuple]:
    pal = load_palette(repo)
    out = {hex_to_rgba(h)[:3] for r in pal.get("ramps", {}).values() for h in r}
    out |= {hex_to_rgba(h)[:3] for h in pal.get("extra", [])}
    return out


# ---------------------------------------------------------------- grid format

def parse_grid(text: str, name: str = "grid") -> tuple[list[Image.Image], dict | None]:
    """Parse a .grid file into frames and an optional mcmeta dict.

    Header lines: `# comment`, `<symbol> = <colour>`, `frametime N`,
    `interpolate true`. Then rows of symbols, one char per pixel; `---`
    separates animation frames. `.` is transparent unless redefined.
    """
    pal: dict[str, tuple] = {".": (0, 0, 0, 0)}
    meta: dict = {}
    frames: list[list[str]] = [[]]
    for n, raw in enumerate(text.splitlines(), 1):
        # Trailing comments need a space after '#', so '#2f527f' stays a colour.
        s = re.sub(r"\s+#\s.*$", "", raw).strip()
        if not s or s.startswith("#"):
            continue
        m = re.fullmatch(r"(\S)\s*=\s*(\S+)", s)
        if m and not frames[0]:
            pal[m[1]] = hex_to_rgba(m[2])
            continue
        m = re.fullmatch(r"(frametime|interpolate|size)\s+(\S+)", s)
        if m and not frames[0]:
            if m[1] == "frametime":
                meta["frametime"] = int(m[2])
            elif m[1] == "interpolate":
                meta["interpolate"] = m[2].lower() == "true"
            continue
        if s == "---":
            frames.append([])
            continue
        frames[-1].append(s)
    frames = [f for f in frames if f]
    if not frames:
        raise ArtError(f"{name}: no rows")
    w, h = len(frames[0][0]), len(frames[0])
    out = []
    for fi, rows in enumerate(frames):
        if len(rows) != h or any(len(r) != w for r in rows):
            raise ArtError(f"{name}: frame {fi + 1} is not {w}x{h} (rows {[len(r) for r in rows]})")
        img = Image.new("RGBA", (w, h))
        px = img.load()
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch not in pal:
                    raise ArtError(f"{name}: frame {fi + 1} row {y + 1} col {x + 1}: "
                                   f"symbol {ch!r} has no colour")
                px[x, y] = pal[ch]
        out.append(img)
    mcmeta = None
    if len(out) > 1 or meta:
        anim = {k: meta[k] for k in ("frametime", "interpolate") if k in meta}
        mcmeta = {"animation": anim}
    return out, mcmeta


def to_grid_text(tex: Texture, title: str = "") -> str:
    frames = tex.frames()
    counts: dict[tuple, int] = {}
    for f in frames:
        for c, n in colours(f).items():
            counts[c] = counts.get(c, 0) + n
    opaque = sorted((c for c in counts if c[3] > 0), key=lambda c: (luma(c), c[3]))
    if len(opaque) > len(GRID_SYMBOLS):
        raise ArtError(f"{len(opaque)} colours; quantize first (max {len(GRID_SYMBOLS)})")
    sym = {(0, 0, 0, 0): "."}
    sym.update({c: GRID_SYMBOLS[i] for i, c in enumerate(opaque)})
    lines = [f"# {title}" if title else "# texture",
             f"# {frames[0].width}x{frames[0].height}, {len(frames)} frame(s), "
             f"{len(opaque)} colours dark to light"]
    if tex.mcmeta:
        anim = tex.mcmeta.get("animation", {})
        if "frametime" in anim:
            lines.append(f"frametime {anim['frametime']}")
        if anim.get("interpolate"):
            lines.append("interpolate true")
    lines.append(". = transparent")
    lines += [f"{sym[c]} = {rgba_to_hex(c)}" for c in opaque]
    for i, f in enumerate(frames):
        lines.append("" if i == 0 else "---")
        px = f.load()
        for y in range(f.height):
            lines.append("".join(sym[px[x, y] if px[x, y][3] else (0, 0, 0, 0)]
                                 for x in range(f.width)))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- derive ops

def op_ramp(repo: Repo, img: Image.Image, op: dict) -> Image.Image:
    ramp = get_ramp(repo, op["ramp"])
    only = {hex_to_rgba(h)[:3] for h in op.get("only", [])}
    src = sorted({c for c in colours(img) if c[3] > 0 and (not only or c[:3] in only)},
                 key=lambda c: (luma(c), c))
    if not src:
        return img
    uniq = sorted({c[:3] for c in src}, key=lambda c: (luma(c), c))
    mode = op.get("mode", "rank" if len(uniq) <= len(ramp) else "luma")
    lo, hi = luma(uniq[0]), luma(uniq[-1])
    mapping = {}
    for i, c in enumerate(uniq):
        if mode == "rank":
            t = i / (len(uniq) - 1) if len(uniq) > 1 else 0.5
        else:
            t = (luma(c) - lo) / (hi - lo) if hi > lo else 0.5
        mapping[c] = ramp[round(t * (len(ramp) - 1))][:3]
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            c = px[x, y]
            if c[3] and c[:3] in mapping:
                px[x, y] = mapping[c[:3]] + (c[3],)
    return out


def op_hsv(img: Image.Image, op: dict) -> Image.Image:
    dh, sm, vm = op.get("h", 0) / 360.0, op.get("s", 1.0), op.get("v", 1.0)
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            r2, g2, b2 = colorsys.hsv_to_rgb((h + dh) % 1, min(1, s * sm), min(1, v * vm))
            px[x, y] = (round(r2 * 255), round(g2 * 255), round(b2 * 255), a)
    return out


def op_replace(img: Image.Image, op: dict) -> Image.Image:
    table = {hex_to_rgba(k)[:3]: hex_to_rgba(v) for k, v in op["map"].items()}
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            c = px[x, y]
            if c[3] and c[:3] in table:
                n = table[c[:3]]
                px[x, y] = n[:3] + (n[3] if n[3] != 255 else c[3],)
    return out


def op_outline(img: Image.Image, op: dict) -> Image.Image:
    col = hex_to_rgba(op.get("color", "#000000"))
    diag = op.get("diagonal", False)
    out = img.copy()
    src, px = img.load(), out.load()
    w, h = img.size
    steps = [(1, 0), (-1, 0), (0, 1), (0, -1)] + ([(1, 1), (1, -1), (-1, 1), (-1, -1)] if diag else [])
    for y in range(h):
        for x in range(w):
            if src[x, y][3]:
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and src[x + dx, y + dy][3]
                   for dx, dy in steps):
                px[x, y] = col
    return out


def op_mask(repo: Repo, img: Image.Image, op: dict, stack) -> Image.Image:
    mask = load_ref(repo, op["from"], stack).frames()[0].resize(img.size, Image.NEAREST)
    out = img.copy()
    px, mp = out.load(), mask.load()
    keep = op.get("keep", "opaque")
    for y in range(out.height):
        for x in range(out.width):
            if (mp[x, y][3] > 0) != (keep == "opaque"):
                px[x, y] = (0, 0, 0, 0)
    return out


def apply_ops(repo: Repo, img: Image.Image, ops: list, stack) -> Image.Image:
    for op in ops:
        kind = op.get("op")
        if kind == "ramp":
            img = op_ramp(repo, img, op)
        elif kind == "hsv":
            img = op_hsv(img, op)
        elif kind == "replace":
            img = op_replace(img, op)
        elif kind == "overlay":
            layer = load_ref(repo, op["from"], stack).frames()[0]
            if "ops" in op:
                layer = apply_ops(repo, layer, op["ops"], stack)
            base = img.copy()
            base.alpha_composite(layer, (op.get("x", 0), op.get("y", 0)))
            img = base
        elif kind == "underlay":
            layer = load_ref(repo, op["from"], stack).frames()[0]
            if "ops" in op:
                layer = apply_ops(repo, layer, op["ops"], stack)
            base = Image.new("RGBA", img.size)
            base.alpha_composite(layer, (op.get("x", 0), op.get("y", 0)))
            base.alpha_composite(img)
            img = base
        elif kind == "mask":
            img = op_mask(repo, img, op, stack)
        elif kind == "outline":
            img = op_outline(img, op)
        elif kind == "flip":
            img = img.transpose(Image.FLIP_LEFT_RIGHT if op.get("axis", "x") == "x"
                                else Image.FLIP_TOP_BOTTOM)
        elif kind == "rotate":
            img = img.rotate(-90 * op.get("turns", 1), expand=True)
        elif kind == "shift":
            base = Image.new("RGBA", img.size)
            base.paste(img, (op.get("x", 0), op.get("y", 0)))
            img = base
        elif kind == "erase":
            px = img.load()
            for x, y in op["pixels"]:
                px[x, y] = (0, 0, 0, 0)
        elif kind == "set":
            px = img.load()
            col = hex_to_rgba(op["color"])
            for x, y in op["pixels"]:
                px[x, y] = col
        else:
            raise ArtError(f"unknown op {kind!r} (ramp, hsv, replace, overlay, underlay, mask, "
                           "outline, flip, rotate, shift, erase, set)")
    return img


# ---------------------------------------------------------------- compose (UI art)

def compose(repo: Repo, spec: dict, stack) -> Image.Image:
    w, h = spec["size"]
    bg = spec.get("background", "transparent")
    if isinstance(bg, dict) and "gradient" in bg:
        top, bottom = (hex_to_rgba(c) for c in bg["gradient"])
        canvas = Image.new("RGBA", (w, h))
        dr = ImageDraw.Draw(canvas)
        for y in range(h):
            t = y / max(1, h - 1)
            dr.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    else:
        canvas = Image.new("RGBA", (w, h), hex_to_rgba(bg))
    for layer in spec.get("layers", []):
        img = load_ref(repo, layer["from"], stack).frames()[0]
        if "crop" in layer:
            img = img.crop(tuple(layer["crop"]))
        if "ops" in layer:
            img = apply_ops(repo, img, layer["ops"], stack)
        resample = Image.NEAREST if layer.get("resample", "nearest") == "nearest" else Image.LANCZOS
        fit = layer.get("fit")
        if fit in ("cover", "contain"):
            k = (max if fit == "cover" else min)(w / img.width, h / img.height)
            img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), resample)
        elif "scale" in layer:
            k = layer["scale"]
            img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), resample)
        if "brightness" in layer:
            rgb = ImageEnhance.Brightness(img.convert("RGB")).enhance(layer["brightness"])
            rgb.putalpha(img.getchannel("A"))
            img = rgb
        if "saturation" in layer:
            rgb = ImageEnhance.Color(img.convert("RGB")).enhance(layer["saturation"])
            rgb.putalpha(img.getchannel("A"))
            img = rgb
        if "tint" in layer:
            tint = Image.new("RGBA", img.size, hex_to_rgba(layer["tint"]))
            mixed = Image.blend(img, tint, layer.get("tint_strength", 0.3))
            mixed.putalpha(img.getchannel("A"))
            img = mixed
        if layer.get("blur"):
            img = img.filter(ImageFilter.GaussianBlur(layer["blur"]))
        if "opacity" in layer:
            a = img.getchannel("A").point(lambda v: round(v * layer["opacity"]))
            img.putalpha(a)
        # x/y offset the layer's top-left corner, or its centre from the
        # canvas centre with anchor "center" (the default for fitted layers).
        x, y = layer.get("x", 0), layer.get("y", 0)
        if layer.get("anchor", "center" if fit else "topleft") == "center":
            x += (w - img.width) // 2
            y += (h - img.height) // 2
        tmp = Image.new("RGBA", canvas.size)
        tmp.paste(img, (x, y))
        canvas = Image.alpha_composite(canvas, tmp)
    if spec.get("vignette"):
        v = spec["vignette"]
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).ellipse([-w * 0.15, -h * 0.15, w * 1.15, h * 1.15], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18))
        dark = Image.new("RGBA", (w, h), (0, 0, 0, round(255 * v)))
        dark.putalpha(Image.eval(mask, lambda m: round((255 - m) * v)))
        canvas = Image.alpha_composite(canvas, dark)
    if spec.get("pixelate"):
        k = int(spec["pixelate"])
        canvas = canvas.resize((max(1, w // k), max(1, h // k)), Image.BOX).resize((w, h), Image.NEAREST)
    if spec.get("quantize"):
        canvas = quantize(repo, canvas, spec["quantize"])
    return canvas


def quantize(repo: Repo, img: Image.Image, how) -> Image.Image:
    alpha = img.getchannel("A")
    rgb = img.convert("RGB")
    if how == "palette":
        cols = sorted(palette_colours(repo))
        if not cols:
            raise ArtError("quantize to palette: art/palette.json has no colours")
        pal_img = Image.new("P", (1, 1))
        flat = [v for c in cols for v in c]
        pal_img.putpalette(flat + flat[:3] * (256 - len(cols)))
        q = rgb.quantize(palette=pal_img, dither=Image.Dither.NONE)
    else:
        q = rgb.quantize(colors=int(how), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = q.convert("RGBA")
    out.putalpha(alpha.point(lambda a: 0 if a < 128 else 255))
    return out


# ---------------------------------------------------------------- render and build

def render_source(repo: Repo, src: Path, stack=()) -> Texture:
    name = src.name
    if not src.is_file():
        raise ArtError(f"{src}: no such source")
    if name.endswith(".grid"):
        frames, mcmeta = parse_grid(src.read_text(), str(src))
        w, h = frames[0].size
        img = Image.new("RGBA", (w, h * len(frames)))
        for i, f in enumerate(frames):
            img.paste(f, (0, i * h))
        return Texture(img, mcmeta, str(src))
    if name.endswith(".png"):
        meta = src.with_name(src.name + ".mcmeta")
        return Texture(Image.open(src), json.loads(meta.read_text()) if meta.is_file() else None, str(src))
    try:
        spec = json.loads(src.read_text())
    except json.JSONDecodeError as e:
        raise ArtError(f"{src}: {e}")
    stack = stack or (src.resolve(),)
    if name.endswith(".derive.json"):
        base = load_ref(repo, spec["from"], stack)
        frames = base.frames()
        if "frame" in spec:
            frames = [frames[spec["frame"]]]
        frames = [apply_ops(repo, f, spec.get("ops", []), stack) for f in frames]
        w, h = frames[0].size
        img = Image.new("RGBA", (w, h * len(frames)))
        for i, f in enumerate(frames):
            img.paste(f, (0, i * h))
        mcmeta = spec.get("mcmeta", base.mcmeta if len(frames) > 1 else None)
        return Texture(img, mcmeta, str(src))
    if name.endswith(".compose.json"):
        return Texture(compose(repo, spec, stack), spec.get("mcmeta"), str(src))
    raise ArtError(f"{src}: unknown source kind")


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def write_texture(tex: Texture, out: Path) -> bool:
    """Write PNG (+ .mcmeta); return True if anything changed."""
    out.parent.mkdir(parents=True, exist_ok=True)
    changed = False
    data = png_bytes(tex.img)
    if not out.is_file() or not same_pixels(out, tex.img):
        out.write_bytes(data)
        changed = True
    meta = out.with_name(out.name + ".mcmeta")
    if tex.mcmeta is not None:
        text = json.dumps(tex.mcmeta, indent=2) + "\n"
        if not meta.is_file() or meta.read_text() != text:
            meta.write_text(text)
            changed = True
    elif meta.is_file():
        meta.unlink()
        changed = True
    return changed


def same_pixels(path: Path, img: Image.Image) -> bool:
    try:
        cur = Image.open(path).convert("RGBA")
    except OSError:
        return False
    return cur.size == img.size and cur.tobytes() == img.convert("RGBA").tobytes()


def stale(repo: Repo, src: Path) -> str | None:
    out = repo.output_for(src)
    tex = render_source(repo, src)
    if not out.is_file():
        return "not built"
    if not same_pixels(out, tex.img):
        return "pixels differ"
    meta = out.with_name(out.name + ".mcmeta")
    want = json.dumps(tex.mcmeta, indent=2) + "\n" if tex.mcmeta is not None else None
    have = meta.read_text() if meta.is_file() else None
    if want != have:
        return ".mcmeta differs"
    return None


# ---------------------------------------------------------------- preview sheet

def _font(size: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def slot(img: Image.Image, scale: int) -> Image.Image:
    """The texture drawn in a vanilla-style inventory slot."""
    s = 18 * scale
    out = Image.new("RGBA", (s, s), (198, 198, 198, 255))
    dr = ImageDraw.Draw(out)
    dr.rectangle([0, 0, s - 1, s - 1], fill=(139, 139, 139, 255))
    dr.rectangle([0, 0, s - 1, scale - 1], fill=(55, 55, 55, 255))
    dr.rectangle([0, 0, scale - 1, s - 1], fill=(55, 55, 55, 255))
    dr.rectangle([0, s - scale, s - 1, s - 1], fill=(255, 255, 255, 255))
    dr.rectangle([s - scale, 0, s - 1, s - 1], fill=(255, 255, 255, 255))
    icon = img.resize((16 * scale, 16 * scale), Image.NEAREST)
    out.alpha_composite(icon, (scale, scale))
    return out


def _preview_row(rows, kind, out: Path, grey: bool):
    """Family layout: every texture (and ref) side by side as zoom over inventory slot."""
    font, small = _font(12), _font(11)
    pad, max_w = 10, 1600
    cells = []
    for ref, tex, is_ref in rows:
        f0 = tex.frames()[0]
        k = kind or ("ui" if f0.width > 64 else ("block" if "block/" in ref else "item"))
        if k == "ui":
            scale = max(1, min(2, 256 // max(f0.width, f0.height)))
            parts = [_checker(f0.resize((f0.width * scale, f0.height * scale), Image.NEAREST))]
        else:
            big = max(1, 128 // f0.width)
            parts = [_checker(f0.resize((f0.width * big, f0.height * big), Image.NEAREST)),
                     slot(f0.resize((16, 16), Image.NEAREST) if f0.width != 16 else f0, 3)]
        name = ref
        for suf in (".derive.json", ".compose.json", ".grid", ".png"):
            name = name.removesuffix(suf)
        label = ("REF " if is_ref else "") + name.split("/")[-1]
        w = max(max(p.width for p in parts), 7 * len(label))
        cells.append((label, parts, is_ref, w, sum(p.height for p in parts) + pad * len(parts)))
    lines, cur, cw = [], [], pad
    for c in cells:
        if cur and cw + c[3] + pad > max_w:
            lines.append(cur)
            cur, cw = [], pad
        cur.append(c)
        cw += c[3] + pad
    lines.append(cur)
    width = max(sum(c[3] + pad for c in ln) + pad for ln in lines)
    height = sum(max(c[4] for c in ln) + 24 + pad for ln in lines) + pad + 16
    sheet = Image.new("RGBA", (max(width, 200), height), (34, 36, 42, 255))
    dr = ImageDraw.Draw(sheet)
    y = pad
    for ln in lines:
        x = pad
        for label, parts, is_ref, w, h in ln:
            dr.text((x, y), label, fill=(150, 200, 255) if is_ref else (235, 235, 235), font=font)
            yy = y + 20
            for p in parts:
                sheet.alpha_composite(p, (x, yy))
                yy += p.height + pad
            x += w + pad
        y += max(c[4] for c in ln) + 24 + pad
    dr.text((pad, height - 14), "row: zoom over inventory slot", fill=(120, 120, 130), font=small)
    if grey:
        sheet = sheet.convert("L").convert("RGBA")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def preview(repo: Repo, refs: list[str], refs_cmp: list[str], kind: str | None, out: Path,
            grey: bool = False, row: bool = False):
    rows = []
    for ref in refs + refs_cmp:
        tex = load_ref(repo, ref)
        rows.append((ref, tex, ref in refs_cmp))
    if not rows:
        raise ArtError("nothing to preview")
    if row:
        return _preview_row(rows, kind, out, grey)
    font, small = _font(14), _font(11)
    tiles = []
    for ref, tex, is_ref in rows:
        f0 = tex.frames()[0]
        k = kind or ("ui" if f0.width > 64 else ("block" if "block/" in ref else "item"))
        parts = []
        if k == "ui":
            scale = max(1, min(4, 512 // max(f0.width, f0.height)))
            parts.append(_checker(f0.resize((f0.width * scale, f0.height * scale), Image.NEAREST)))
        else:
            big = max(1, 128 // f0.width)
            parts.append(_checker(f0.resize((f0.width * big, f0.height * big), Image.NEAREST)))
            if k == "block":
                tile = Image.new("RGBA", (f0.width * 3, f0.height * 3))
                for i in range(3):
                    for j in range(3):
                        tile.paste(f0, (i * f0.width, j * f0.height))
                k3 = max(1, 48 // f0.width)
                parts.append(tile.resize((tile.width * k3, tile.height * k3), Image.NEAREST))
            parts.append(slot(f0.resize((16, 16), Image.NEAREST) if f0.width != 16 else f0, 3))
            parts.append(_on(f0, (56, 56, 64, 255), 2))
            parts.append(_on(f0, (220, 220, 210, 255), 2))
            if tex.frame_count > 1:
                strip = Image.new("RGBA", (f0.width * tex.frame_count, f0.height))
                for i, fr in enumerate(tex.frames()):
                    strip.paste(fr, (i * f0.width, 0))
                parts.append(_checker(strip.resize((strip.width * 2, strip.height * 2), Image.NEAREST)))
        cols = colours(f0)
        label = (f"{'REF  ' if is_ref else ''}{ref}  {f0.width}x{f0.height}"
                 f"{f'  x{tex.frame_count} frames' if tex.frame_count > 1 else ''}"
                 f"  {sum(1 for c in cols if c[3])} colours")
        tiles.append((label, parts, is_ref))
    pad = 10
    width = max(sum(p.width for p in parts) + pad * (len(parts) + 1) for _, parts, _ in tiles)
    width = max(width, 420)
    height = sum(max(p.height for p in parts) + 30 + pad for _, parts, _ in tiles) + pad
    sheet = Image.new("RGBA", (width, height), (34, 36, 42, 255))
    dr = ImageDraw.Draw(sheet)
    y = pad
    for label, parts, is_ref in tiles:
        dr.text((pad, y), label, fill=(150, 200, 255) if is_ref else (235, 235, 235), font=font)
        y += 22
        x = pad
        for p in parts:
            sheet.alpha_composite(p, (x, y))
            x += p.width + pad
        y += max(p.height for p in parts) + pad + 8
    dr.text((pad, height - 14), "parts: zoom | 3x3 tile (blocks) | inventory slot | on dark | on light",
            fill=(120, 120, 130), font=small)
    if grey:  # value check: siblings must still differ with the hue gone
        sheet = sheet.convert("L").convert("RGBA")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def _checker(img: Image.Image, cell: int = 8) -> Image.Image:
    bg = Image.new("RGBA", img.size, (90, 90, 96, 255))
    dr = ImageDraw.Draw(bg)
    for y in range(0, img.height, cell):
        for x in range(0, img.width, cell):
            if (x // cell + y // cell) % 2:
                dr.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(110, 110, 118, 255))
    bg.alpha_composite(img)
    return bg


def _on(img: Image.Image, colour, scale: int) -> Image.Image:
    bg = Image.new("RGBA", (img.width * scale + 8, img.height * scale + 8), colour)
    bg.alpha_composite(img.resize((img.width * scale, img.height * scale), Image.NEAREST), (4, 4))
    return bg


# ---------------------------------------------------------------- lint

def lint(repo: Repo, files: list[Path]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    pal = load_palette(repo)
    pal_cols = palette_colours(repo)
    max_colors = pal.get("max_colors", DEFAULT_MAX_COLORS)
    pal_ns = set(pal.get("namespaces", []))
    if not files and repo.pack_assets.is_dir():
        files = sorted(repo.pack_assets.glob("*/textures/**/*.png"))
    for f in files:
        try:
            rel = f.resolve().relative_to(repo.pack_assets.resolve())
        except ValueError:
            errors.append(f"{f}: not under packwiz/kubejs/assets")
            continue
        where = f"kubejs/assets/{rel.as_posix()}"
        parts = rel.parts
        if len(parts) < 3 or parts[1] != "textures":
            errors.append(f"{where}: textures belong in assets/<ns>/textures/")
            continue
        folder = parts[2]
        if folder in ("items", "blocks"):
            errors.append(f"{where}: folder is {folder}/; 1.21 uses singular item/ and block/")
        try:
            img = Image.open(f)
            img.load()
        except OSError as e:
            errors.append(f"{where}: unreadable PNG ({e})")
            continue
        if img.mode not in ("RGBA", "RGB", "P", "LA", "L"):
            warnings.append(f"{where}: unusual mode {img.mode}")
        img = img.convert("RGBA")
        w, h = img.size
        meta = f.with_name(f.name + ".mcmeta")
        if meta.is_file():
            try:
                json.loads(meta.read_text())
            except json.JSONDecodeError as e:
                errors.append(f"{where}.mcmeta: bad JSON ({e})")
        if folder in PIXEL_FOLDERS:
            if w & (w - 1) or not 8 <= w <= 64:
                errors.append(f"{where}: width {w}; pixel textures are 16, 32 or 64 px wide")
            if h != w:
                if h % w:
                    errors.append(f"{where}: {w}x{h} is neither square nor a frame strip")
                elif not meta.is_file():
                    errors.append(f"{where}: {h // w}-frame strip without a .mcmeta")
            cols = colours(img)
            alphas = {c[3] for c in cols}
            if alphas == {0}:
                errors.append(f"{where}: fully transparent")
            opaque = [c for c in cols if c[3]]
            if len(opaque) > max_colors:
                warnings.append(f"{where}: {len(opaque)} colours (art direction max {max_colors})")
            if folder == "item" and any(0 < a < 255 for a in alphas):
                warnings.append(f"{where}: semi-transparent pixels (items use 0 or 255 alpha)")
            if folder == "block" and 0 in alphas:
                warnings.append(f"{where}: transparent pixels in a block texture "
                                "(needs a cutout/translucent render type, or it is a mistake)")
            if pal_cols and parts[0] in pal_ns:
                off = sorted({c[:3] for c in opaque} - pal_cols)
                if off:
                    warnings.append(f"{where}: {len(off)} colour(s) not in art/palette.json "
                                    f"({', '.join(rgba_to_hex(c + (255,)) for c in off[:4])}"
                                    f"{', ...' if len(off) > 4 else ''})")
        elif max(w, h) > 2048:
            warnings.append(f"{where}: {w}x{h} is large; UI art rarely needs more than 1024 px")
        src = repo.source_for(f)
        if src is None:
            warnings.append(f"{where}: no art source in art/assets/ (hand-placed binary)")
        else:
            try:
                why = stale(repo, src)
            except ArtError as e:
                errors.append(f"{src.relative_to(repo.root)}: {e}")
                why = None
            if why:
                errors.append(f"{where}: stale ({why}); run `scripts/texture.py build`")
    for src in repo.sources():
        if not repo.output_for(src).is_file():
            errors.append(f"{src.relative_to(repo.root)}: not built; run `scripts/texture.py build`")
    e2, w2 = lint_registrations(repo)
    return errors + e2, warnings + w2


CREATE_RE = re.compile(r"""\.create\(\s*['"]([a-z0-9_.:/-]+)['"]""")
REGISTRY_RE = re.compile(r"""StartupEvents\.registry\(\s*['"]([a-z_:]+)['"]""")
TEXTURE_RE = re.compile(r"""\.(texture|textures|parentModel|modelGenerator)\(\s*(['"]([^'"]+)['"])?""")


def lint_registrations(repo: Repo) -> tuple[list[str], list[str]]:
    """Every startup-registered item/block must name a texture that exists."""
    errors, warnings = [], []
    if not repo.startup.is_dir():
        return errors, warnings
    known = None
    for js in sorted(repo.startup.glob("*.js")):
        text = js.read_text()
        regs = [(m.start(), m[1].split(":")[-1]) for m in REGISTRY_RE.finditer(text)]
        creates = list(CREATE_RE.finditer(text))
        for cm in re.finditer(r"""\.create\(\s*(?:`|[A-Za-z_$])""", text):
            warnings.append(f"startup_scripts/{js.name}: can't check a computed id "
                            f"(template or variable) near offset {cm.start()}")
        for i, m in enumerate(creates):
            reg = next((r for pos, r in reversed(regs) if pos < m.start()), "item")
            if reg not in ("item", "block"):
                continue
            end = creates[i + 1].start() if i + 1 < len(creates) else len(text)
            stmt = text[m.start():end]
            semi = stmt.find(";")
            stmt = stmt if semi < 0 else stmt[:semi]
            where = f"startup_scripts/{js.name}: {m[1]}"
            if re.match(r"\s*\+", text[m.end():m.end() + 8]):
                warnings.append(f"{where}...: can't check a computed id (string concatenation); "
                                "check its texture by hand")
                continue
            tex = [t for t in TEXTURE_RE.finditer(stmt)]
            if not tex:
                errors.append(f"{where}: no .texture(...); name it explicitly "
                              f"(e.g. .texture('{_ns(m[1])}:{reg}/{m[1].split(':')[-1]}'))")
                continue
            for t in tex:
                if t[1] != "texture" or not t[3]:
                    continue
                if re.match(r"\s*\+", stmt[t.end():t.end() + 8]):
                    warnings.append(f"{where}...: can't check a computed texture (string concatenation)")
                    continue
                if known is None:
                    known = repo.all_texture_ids()
                tid = t[3]
                if ":" not in tid:
                    tid = "minecraft:" + tid
                if tid not in known:
                    errors.append(f"{where}: texture {t[3]} not found in the pack, mods or vanilla")
                elif tid.split(":")[0] != _ns(m[1]):
                    warnings.append(f"{where}: placeholder texture {tid} (needs pack art)")
    return errors, warnings


def _ns(rid: str) -> str:
    return rid.split(":")[0] if ":" in rid else "kubejs"


# ---------------------------------------------------------------- panorama

def panorama_check(repo: Repo, d: Path, out: Path) -> list[str]:
    problems = []
    faces = []
    for i in range(6):
        p = d / f"panorama_{i}.png"
        if not p.is_file():
            problems.append(f"missing {p.name}")
            faces.append(None)
            continue
        img = Image.open(p).convert("RGBA")
        if img.width != img.height:
            problems.append(f"{p.name}: {img.width}x{img.height} is not square")
        faces.append(img)
    sizes = {f.size for f in faces if f}
    if len(sizes) > 1:
        problems.append(f"faces differ in size: {sorted(sizes)}")
    if not any(faces):
        return problems
    c = 256
    faces = [f.resize((c, c), Image.LANCZOS if f.width > c else Image.NEAREST) if f
             else Image.new("RGBA", (c, c), (255, 0, 255, 255)) for f in faces]
    # Vanilla order: 0 front, 1 right, 2 back, 3 left, 4 top, 5 bottom.
    sheet = Image.new("RGBA", (c * 4 + 50, c * 3 + 90), (30, 30, 34, 255))
    for i, (x, y) in {0: (1, 1), 1: (2, 1), 2: (3, 1), 3: (0, 1), 4: (1, 0), 5: (1, 2)}.items():
        sheet.paste(faces[i], (x * c, y * c))
    dr = ImageDraw.Draw(sheet)
    font = _font(12)
    for i, (x, y) in {0: (1, 1), 1: (2, 1), 2: (3, 1), 3: (0, 1), 4: (1, 0), 5: (1, 2)}.items():
        dr.text((x * c + 4, y * c + 4), str(i), fill=(255, 255, 0), font=font)
    # Horizontal seams magnified: the edge columns of neighbours side by side.
    y0 = c * 3 + 10
    for k, (a, b) in enumerate([(3, 0), (0, 1), (1, 2), (2, 3)]):
        strip = Image.new("RGBA", (16, c))
        strip.paste(faces[a].crop((c - 8, 0, c, c)), (0, 0))
        strip.paste(faces[b].crop((0, 0, 8, c)), (8, 0))
        strip = strip.rotate(90, expand=True).resize((c, 32), Image.NEAREST)
        sheet.paste(strip, (k * c, y0))
        dr.text((k * c + 4, y0 + 36), f"seam {a}|{b}", fill=(220, 220, 220), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return problems


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("find"); p.add_argument("pattern")
    p = sub.add_parser("show"); p.add_argument("ref"); p.add_argument("--grid", action="store_true")
    p = sub.add_parser("extract"); p.add_argument("ref"); p.add_argument("out", type=Path)
    p = sub.add_parser("ramp"); p.add_argument("ref"); p.add_argument("-n", type=int, default=0)
    p = sub.add_parser("to-grid"); p.add_argument("ref"); p.add_argument("out", type=Path)
    p = sub.add_parser("render"); p.add_argument("source"); p.add_argument("out", type=Path)
    p = sub.add_parser("build"); p.add_argument("sources", nargs="*"); p.add_argument("--check", action="store_true")
    p = sub.add_parser("preview"); p.add_argument("refs", nargs="+"); p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ref", nargs="+", action="extend", default=[], dest="cmp",
                   help="comparison texture(s); repeatable, or several after one --ref")
    p.add_argument("--row", action="store_true", help="family layout: all textures side by side")
    p.add_argument("--kind", choices=["item", "block", "ui"])
    p.add_argument("--grey", action="store_true", help="greyscale sheet, for value checks")
    p = sub.add_parser("lint"); p.add_argument("files", nargs="*", type=Path)
    p = sub.add_parser("quantize"); p.add_argument("src"); p.add_argument("out", type=Path)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--colors", type=int); g.add_argument("--palette", action="store_true")
    p.add_argument("--size", type=int, help="also downscale (box filter) to this width first")
    p = sub.add_parser("panorama-check"); p.add_argument("dir", type=Path); p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    repo = Repo(a.root.resolve())
    try:
        return run(repo, a)
    except ArtError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def run(repo: Repo, a) -> int:
    if a.cmd == "find":
        pat = a.pattern if ":" in a.pattern else f"*:{a.pattern}"
        hits = sorted((t, src) for t, src in repo.all_texture_ids().items() if fnmatch.fnmatch(t, pat))
        for t, src in hits[:200]:
            print(f"{t}  [{src}]")
        if len(hits) > 200:
            print(f"... {len(hits) - 200} more; narrow the pattern")
        return 0 if hits else 1
    if a.cmd == "show":
        tex = load_ref(repo, a.ref)
        f0 = tex.frames()[0]
        cols = colours(f0)
        opaque = sorted((c for c in cols if c[3]), key=lambda c: (luma(c), c))
        print(f"{a.ref}: {f0.width}x{f0.height}, {tex.frame_count} frame(s), {len(opaque)} colours, "
              f"from {tex.origin}")
        if tex.mcmeta:
            print(f"mcmeta: {json.dumps(tex.mcmeta)}")
        for c in opaque:
            print(f"  {rgba_to_hex(c):10} {cols[c]:4} px  luma {luma(c):5.1f}")
        if a.grid:
            print(to_grid_text(tex, a.ref))
        return 0
    if a.cmd == "extract":
        tex = load_ref(repo, a.ref)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        tex.img.save(a.out)
        if tex.mcmeta:
            a.out.with_name(a.out.name + ".mcmeta").write_text(json.dumps(tex.mcmeta, indent=2) + "\n")
        print(f"wrote {a.out} ({tex.img.width}x{tex.img.height}, from {tex.origin})")
        return 0
    if a.cmd == "ramp":
        f0 = load_ref(repo, a.ref).frames()[0]
        opaque = sorted({c[:3] for c in colours(f0) if c[3]}, key=luma)
        if a.n and a.n < len(opaque):
            opaque = [opaque[round(i * (len(opaque) - 1) / (a.n - 1))] for i in range(a.n)]
        print(json.dumps([rgba_to_hex(c + (255,)) for c in opaque]))
        return 0
    if a.cmd == "to-grid":
        text = to_grid_text(load_ref(repo, a.ref), a.ref)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
        print(f"wrote {a.out}")
        return 0
    if a.cmd == "render":
        tex = load_ref(repo, a.source)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        tex.img.save(a.out)
        if tex.mcmeta is not None:
            a.out.with_name(a.out.name + ".mcmeta").write_text(json.dumps(tex.mcmeta, indent=2) + "\n")
        print(f"wrote {a.out} ({tex.img.width}x{tex.img.height})")
        return 0
    if a.cmd == "build":
        srcs = [Path(s).resolve() for s in a.sources] or repo.sources()
        for s in [x for x in srcs if x.name.startswith("_")]:
            print(f"skip {s.name}: helper source (name starts with _), not built into the pack")
        srcs = [x for x in srcs if not x.name.startswith("_")]
        bad = 0
        for src in srcs:
            out = repo.output_for(src)
            rel_out = out.relative_to(repo.root)
            if a.check:
                why = stale(repo, src)
                if why:
                    print(f"stale: {rel_out} ({why})")
                    bad += 1
                continue
            changed = write_texture(render_source(repo, src), out)
            print(f"{'built' if changed else 'same '} {rel_out}")
        if a.check:
            print(f"{len(srcs) - bad}/{len(srcs)} up to date")
        return 1 if bad else 0
    if a.cmd == "preview":
        preview(repo, a.refs, a.cmp, a.kind, a.out, a.grey, a.row)
        print(f"wrote {a.out}; Read it to judge")
        return 0
    if a.cmd == "lint":
        errors, warnings = lint(repo, [f.resolve() for f in a.files])
        for e in errors:
            print(f"ERROR {e}")
        for w in warnings:
            print(f"WARN  {w}")
        print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1 if errors else 0
    if a.cmd == "quantize":
        img = load_ref(repo, a.src).frames()[0]
        if a.size:
            img = img.resize((a.size, max(1, round(img.height * a.size / img.width))), Image.BOX)
        out = quantize(repo, img, "palette" if a.palette else a.colors)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        out.save(a.out)
        print(f"wrote {a.out} ({out.width}x{out.height}, {sum(1 for c in colours(out) if c[3])} colours)")
        return 0
    if a.cmd == "panorama-check":
        problems = panorama_check(repo, a.dir, a.out)
        for p in problems:
            print(f"ERROR {p}")
        print(f"wrote {a.out}; Read it and look along each seam")
        return 1 if problems else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
