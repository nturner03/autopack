#!/usr/bin/env python3
"""Call an MCPFabric bridge directly (same tools as the mc-server / mc-client MCP servers).

Usage (run with `python3 -I`):
  mcf.py [--client] <tool> ['<json-args>']      e.g. mcf.py run_command '{"command":"list"}'
  mcf.py [--client] --method <rpc.method> ['<json-args>']
  mcf.py --list                                 tool -> bridge method table
  mcf.py --client screenshot [--out FILE.png]   saves the PNG (default: docs/local/screenshots/)

--client targets the headless client's bridge (CLIENT_BRIDGE_PORT) instead of the
dev server's (SERVER_BRIDGE_PORT); both come from infrastructure/project.env. The token is read from infrastructure/.state.
Prints the JSON result; exit 1 on a bridge error, 2 if the bridge is unreachable.
For subagents without the MCP tools and for scripted checks; the tool names and
arguments are the same as the MCP tools' (see the MCPFabric README §Tools).
"""

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOKEN_FILE = REPO / "infrastructure" / ".state" / "mcpfabric-token"
MCPFABRIC_DIR = os.environ.get("PEXP_MCPFABRIC_DIR", "")
def project_env() -> dict[str, str]:
    """KEY=value pairs from infrastructure/project.env (ports, LAN host)."""
    out = {}
    path = REPO / "infrastructure" / "project.env"
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out



def tool_methods() -> dict[str, str]:
    if not MCPFABRIC_DIR:
        sys.exit("error: PEXP_MCPFABRIC_DIR not set (path to your MCPFabric checkout)")
    text = (Path(MCPFABRIC_DIR) / "mcp-server" / "src" / "tools.ts").read_text()
    return dict(re.findall(r'name:\s*"([a-z_]+)",\s*method:\s*"([A-Za-z_.]+)"', text))


def call(port: int, method: str, params: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/rpc",
        data=json.dumps({"method": method, "params": params}).encode(),
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {TOKEN_FILE.read_text().strip()}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tool", nargs="?")
    ap.add_argument("args", nargs="?", default="{}")
    ap.add_argument("--client", action="store_true")
    ap.add_argument("--method", help="raw bridge method instead of a tool name")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", help="where to save a screenshot PNG")
    ap.add_argument("--timeout", type=float, default=30)
    a = ap.parse_args()

    methods = tool_methods()
    if a.list:
        for name, method in sorted(methods.items()):
            print(f"{name:28} {method}")
        return 0
    if a.method:
        method, raw = a.method, (a.tool or "{}")
    else:
        if not a.tool:
            ap.print_usage(sys.stderr)
            return 2
        if a.tool not in methods:
            print(f"unknown tool {a.tool!r}; see --list", file=sys.stderr)
            return 2
        method, raw = methods[a.tool], a.args
    params = json.loads(raw)
    env_vars = project_env()
    key = "CLIENT_BRIDGE_PORT" if a.client else "SERVER_BRIDGE_PORT"
    if not env_vars.get(key, "").isdigit():
        print(f"{key} is not set in infrastructure/project.env", file=sys.stderr)
        return 2
    port = int(env_vars[key])
    try:
        env = call(port, method, params, a.timeout)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} from bridge :{port}: {exc.read()[:300]!r}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"bridge :{port} unreachable ({exc}); is the "
              f"{'client' if a.client else 'server'} running?", file=sys.stderr)
        return 2
    if not env.get("ok"):
        print(json.dumps(env.get("error"), indent=2), file=sys.stderr)
        return 1
    result = env.get("result")
    if isinstance(result, dict) and isinstance(result.get("base64"), str):
        ext = "jpg" if result.get("format") in ("jpeg", "jpg") else "png"
        out = Path(a.out) if a.out else (
            REPO / "docs" / "local" / "screenshots" / f"{time.strftime('%Y%m%d-%H%M%S')}.{ext}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(result.pop("base64")))
        result["savedTo"] = str(out)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
