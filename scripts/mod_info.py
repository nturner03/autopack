#!/usr/bin/env python3
"""Look up a Modrinth project's builds for the pack's MC version + loader, and their deps.

Usage (run with `python3 -I`):
  mod_info.py <slug-or-id>                 list matching versions (newest first)
  mod_info.py <slug-or-id> <version-id>    show one version, download its jar into
                                           a fresh temp dir, print its mod metadata
                                           (neoforge.mods.toml / mods.toml / fabric.mod.json)
  mod_info.py --mc 1.21.1 --loader neoforge <slug>   override (before packwiz init)

MC version and loader default to packwiz/pack.toml.

Read-only research aid: it never touches the pack. The jar is treated as
untrusted data (only its metadata is read; nothing is executed).
"""

import argparse
import json
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.modrinth.com/v2"
PACK = Path(__file__).resolve().parents[1] / "packwiz" / "pack.toml"
MC, LOADER = None, None


def pack_target() -> tuple[str | None, str | None]:
    if not PACK.is_file():
        return None, None
    v = tomllib.loads(PACK.read_text()).get("versions", {})
    loader = next((k for k in ("neoforge", "fabric", "forge", "quilt") if k in v), None)
    return v.get("minecraft"), loader


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "pack-experiment-mod-info"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def project_name(pid: str) -> str:
    try:
        return get(f"{API}/project/{pid}")["slug"]
    except OSError:
        return pid


def list_versions(slug: str) -> None:
    proj = get(f"{API}/project/{slug}")
    print(f"{proj['title']} ({proj['id']}) client={proj['client_side']} "
          f"server={proj['server_side']} license={proj['license']['id']}")
    q = urllib.parse.urlencode({"loaders": json.dumps([LOADER]),
                                "game_versions": json.dumps([MC])})
    versions = get(f"{API}/project/{slug}/version?{q}")
    if not versions:
        print(f"no {LOADER} {MC} builds")
    for v in versions[:15]:
        deps = ", ".join(f"{project_name(d['project_id'])}:{d['dependency_type']}"
                         for d in v["dependencies"] if d.get("project_id")) or "-"
        print(f"{v['id']}  {v['version_number']}  {v['version_type']}  "
              f"{v['date_published'][:10]}  deps: {deps}")


def show_version(vid: str) -> None:
    v = get(f"{API}/version/{vid}")
    print(f"{v['version_number']} loaders={v['loaders']} game={v['game_versions']}")
    f = next((f for f in v["files"] if f["primary"]), v["files"][0])
    with tempfile.TemporaryDirectory(prefix="modinfo-") as tmp:
        jar = Path(tmp) / "mod.jar"
        urllib.request.urlretrieve(f["url"], jar)
        with zipfile.ZipFile(jar) as z:
            names = set(z.namelist())
            meta = next((n for n in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml",
                                     "fabric.mod.json", "quilt.mod.json") if n in names), None)
            raw = z.read(meta).decode() if meta else None
            nested = sorted(n for n in names if (n.startswith("META-INF/jarjar/")
                            or n.startswith("META-INF/jars/")) and n.endswith(".jar"))
            payload_hint = sorted(n for n in names if "network" in n.lower() or "packet" in n.lower()
                                  or "payload" in n.lower())[:5]
    if meta is None:
        print("no loader metadata in jar")
        return
    print(f"metadata: {meta}")
    if meta.endswith(".toml"):
        data = tomllib.loads(raw)
        for mod in data.get("mods", []):
            print(f"modId={mod.get('modId')} version={mod.get('version')}")
            for dep in data.get("dependencies", {}).get(mod.get("modId"), []):
                kind = dep.get("type") or ("required" if dep.get("mandatory") else "optional")
                print(f"  {kind:9} {dep.get('modId')} {dep.get('versionRange')} side={dep.get('side')}")
    else:
        data = json.loads(raw)
        print(f"id={data.get('id')} version={data.get('version')} environment={data.get('environment')}")
        for kind in ("depends", "recommends", "suggests", "breaks", "conflicts"):
            for dep, rng in (data.get(kind) or {}).items():
                print(f"  {kind:10} {dep} {rng}")
    if nested:
        print("jar-in-jar: " + ", ".join(Path(n).name for n in nested))
    if payload_hint:
        print("network/payload classes (side hint; confirm in code): " + ", ".join(payload_hint))


def main() -> int:
    global MC, LOADER
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project")
    ap.add_argument("version_id", nargs="?")
    ap.add_argument("--mc")
    ap.add_argument("--loader")
    a = ap.parse_args()
    MC, LOADER = pack_target()
    MC, LOADER = a.mc or MC, a.loader or LOADER
    if not (MC and LOADER):
        print("no packwiz/pack.toml yet: pass --mc and --loader", file=sys.stderr)
        return 2
    if a.version_id:
        show_version(a.version_id)
    else:
        list_versions(a.project)
    return 0


if __name__ == "__main__":
    sys.exit(main())
