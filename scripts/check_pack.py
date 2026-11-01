#!/usr/bin/env python3
"""Static and deployment consistency checks for the pack in packwiz/.

Usage (from anywhere; run with `python3 -I`):
  check_pack.py            static checks (metadata, sides, index, leaks)
  check_pack.py --deploy   also compare git HEAD, the served pack (if packwiz serve runs),
                           and what the dev server and headless client have installed

Read-only: never runs `packwiz refresh`, never edits files. Exit 0 = no
errors, 1 = errors found, 2 = could not run.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# PEXP_PACK_TOML (same override the infrastructure scripts use) points at another pack.
REPO = Path(os.environ["PEXP_PACK_TOML"]).parent if os.environ.get("PEXP_PACK_TOML") else ROOT / "packwiz"
INSTALLS = {
    "dev server": ROOT / "infrastructure" / "dev-server" / "server",
    "headless client": ROOT / "infrastructure" / "headless-client" / "instance",
}
def project_env() -> dict[str, str]:
    """KEY=value pairs from infrastructure/project.env (ports, LAN host)."""
    out = {}
    path = ROOT / "infrastructure" / "project.env"
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


SERVE_URL = f"http://localhost:{project_env().get('SERVE_PORT') or '0'}/pack.toml"
VALID_SIDES = {"client", "server", "both"}
LOADERS = {"neoforge", "fabric", "forge", "quilt"}
# Paths that must never appear in index.toml (mutable state, generated files, secrets).
FORBIDDEN_PREFIXES = (
    "world/", "logs/", "crash-reports/", "saves/", "local/",
    "kubejs/config/", "kubejs/exported/", "kubejs/local/",
)
FORBIDDEN_NAMES = {".gitattributes", ".gitkeep", "mcpfabric.config.json", "web_server.json"}

errors: list[str] = []
warnings: list[str] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_toml(path: Path):
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"{path.relative_to(REPO)}: cannot parse TOML: {exc}")
        return None


def check_static() -> dict:
    pack = load_toml(REPO / "pack.toml")
    index = load_toml(REPO / "index.toml")
    if pack is None or index is None:
        return {}

    versions = pack.get("versions", {})
    loaders = sorted(set(versions) & LOADERS)
    print(f"pack: {pack.get('name')} {pack.get('version')} — minecraft {versions.get('minecraft')}, "
          + ", ".join(f"{name} {versions[name]}" for name in loaders))
    if len(loaders) != 1:
        errors.append(f"pack.toml: expected exactly one loader, found {loaders}")

    idx_hash = pack.get("index", {}).get("hash")
    if idx_hash != sha256(REPO / "index.toml"):
        errors.append("pack.toml index hash does not match index.toml — run `packwiz refresh`")

    files = index.get("files", [])
    indexed = {f["file"]: f for f in files}
    for rel, entry in indexed.items():
        path = REPO / rel
        if rel.startswith(FORBIDDEN_PREFIXES) or Path(rel).name in FORBIDDEN_NAMES \
                or rel.endswith(".md"):
            errors.append(f"index.toml ships repo-only/mutable/secret path: {rel} (fix .packwizignore)")
        if not path.is_file():
            errors.append(f"index.toml references missing file: {rel}")
            continue
        if entry.get("hash") != sha256(path):
            errors.append(f"stale index hash for {rel} — run `packwiz refresh`")

    # Every metafile on disk must be indexed, and every metafile must be sane.
    filenames: dict[str, str] = {}
    sides = {"client": [], "server": [], "both": []}
    for meta in sorted(REPO.glob("**/*.pw.toml")):
        rel = meta.relative_to(REPO).as_posix()
        if rel.startswith(FORBIDDEN_PREFIXES):
            continue
        if rel not in indexed:
            errors.append(f"{rel} is not in index.toml — run `packwiz refresh`")
        elif not indexed[rel].get("metafile"):
            errors.append(f"{rel} indexed without metafile = true")
        data = load_toml(meta)
        if data is None:
            continue
        side = data.get("side")
        if side not in VALID_SIDES:
            errors.append(f"{rel}: side is {side!r}; set client, server, or both")
        else:
            sides[side].append(data.get("name", rel))
        dl = data.get("download", {})
        if not data.get("filename"):
            errors.append(f"{rel}: missing filename")
        if not (dl.get("url") or dl.get("mode") == "metadata:curseforge"):
            errors.append(f"{rel}: download has neither url nor metadata:curseforge mode")
        if not (dl.get("hash") and dl.get("hash-format")):
            errors.append(f"{rel}: download hash/hash-format missing")
        other = filenames.setdefault(f"{meta.parent}/{data.get('filename')}", rel)
        if other != rel:
            errors.append(f"{rel} and {other} install the same filename")
        if "update" not in data:
            warnings.append(f"{rel}: no [update] source (url/custom artifact) — updates are manual")
        if data.get("pin"):
            warnings.append(f"{rel}: pinned (packwiz update skips it)")

    for side, names in sides.items():
        print(f"side={side}: {len(names)}" + (f" — {', '.join(names)}" if side != "both" else ""))

    # Loose files that sit in distributed folders but are not indexed.
    for folder in ("mods", "config", "defaultconfigs", "kubejs", "resourcepacks", "shaderpacks"):
        for p in (REPO / folder).glob("**/*") if (REPO / folder).is_dir() else []:
            rel = p.relative_to(REPO).as_posix()
            if p.is_file() and rel not in indexed:
                errors.append(f"unindexed file in distributed folder: {rel}")
            if p.suffix == ".jar" and not (folder == "mods" and p.parent == REPO / "mods"):
                errors.append(f"jar outside mods/: {rel}")
            elif p.suffix == ".jar":
                warnings.append(f"raw jar shipped: {rel} — only custom-mods builds belong here "
                                "(scripts/build-custom-mod.sh); others use packwiz add")

    return {"pack": sha256(REPO / "pack.toml"), "index": sha256(REPO / "index.toml")}


def git_hashes() -> dict | None:
    out = {}
    for key, name in (("pack", "pack.toml"), ("index", "index.toml")):
        res = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:./{name}"],
                             capture_output=True)
        if res.returncode != 0:
            return None
        out[key] = hashlib.sha256(res.stdout).hexdigest()
    return out


def check_deploy(local: dict) -> None:
    head = git_hashes()
    status = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--",
                             "pack.toml", "index.toml", "mods", "config", "defaultconfigs",
                             "kubejs", ".packwizignore"],
                            capture_output=True, text=True).stdout.strip()
    rev = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print(f"git HEAD {rev}; pack content {'DIRTY' if status else 'clean'}")
    if status:
        warnings.append("uncommitted pack changes — `packwiz serve` is serving the working "
                        "tree, not HEAD; commit before calling a revision tested")

    try:
        with urllib.request.urlopen(SERVE_URL, timeout=3) as r:
            served = hashlib.sha256(r.read()).hexdigest()
        print(f"served pack.toml {'== working tree' if served == local['pack'] else '!= working tree'}")
    except OSError:
        print(f"pack host not running at {SERVE_URL} (only needed for the owner's Prism client)")

    for label, inst_dir in INSTALLS.items():
        state = inst_dir / "packwiz.json"
        if not state.is_file():
            print(f"{label}: not installed")
            continue
        data = json.loads(state.read_text())
        inst = {"pack": data["packFileHash"]["value"], "index": data["indexFileHash"]["value"]}
        rel = {name: inst == ref for name, ref in (("working tree", local), ("HEAD", head)) if ref}
        print(f"{label} installed state: " + ", ".join(
            f"{'==' if same else '!='} {name}" for name, same in rel.items()))
        if inst != local:
            warnings.append(f"{label} has not installed the current working tree "
                            "(scripts/deploy.sh, or the update-pack.sh of that install)")


def check_textures() -> None:
    """Texture lint (scripts/texture.py): stale builds, missing or unnamed
    textures for startup registrations, bad sizes. Skipped without Pillow."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import texture
    except SystemExit:
        warnings.append("texture lint skipped: Pillow is not installed")
        return
    try:
        errs, warns = texture.lint(texture.Repo(REPO.parent), [])
    except texture.ArtError as e:
        errs, warns = [str(e)], []
    errors.extend(f"texture: {e}" for e in errs)
    warnings.extend(f"texture: {w}" for w in warns)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deploy", action="store_true", help="also check serve + installed state")
    args = ap.parse_args()
    if not (REPO / "pack.toml").is_file():
        print(f"pack.toml not found under {REPO}", file=sys.stderr)
        return 2
    local = check_static()
    check_textures()
    if args.deploy and local:
        check_deploy(local)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
