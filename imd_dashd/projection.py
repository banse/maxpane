"""The ``seat`` projection: the ONLY reader of ``config.json``, run as ``imd-worker`` (spec §5.2, §13).

It (i) loads the file, (ii) asserts the source object has EXACTLY the 8 known keys and refuses
otherwise (a renamed or added key in a future build fails closed -- formats already changed between
builds), (iii) builds its output from an explicit allowlist of literal key names plus tool *ids* from
``tools.json``, and (iv) never opens a path ending in ``.bak-*``. The broker then runs the value-aware
canary (key names, ``sk-``/``eyJ``, ``deviceKey == imd whoami``, no other hex64) before anything
crosses the socket. Exit 3 with ``{"error": "unknown_keys"}`` on schema drift.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # python3 -I: no script dir

import argparse
import json
import re
from collections.abc import Mapping

CONFIG_KEYS = ("server", "deviceKey", "devicePrivateKey", "maxConcurrency", "wallet", "tokenId", "skillsOptOut", "inference")  # exactly 8
ALLOWLIST = ("server", "deviceKey", "wallet", "tokenId", "maxConcurrency", "skillsOptOut", "inference")
CONFIG_PATH = "/home/imd-worker/.identitymd/config.json"
TOOLS_PATH = "/home/imd-worker/.identitymd/tools.json"
BACKUP_RE = re.compile(r"\.bak-[^/]*$")

EXIT_OK = 0
EXIT_UNREADABLE = 2
EXIT_UNKNOWN_KEYS = 3
EXIT_REFUSED_PATH = 4


def project(config: Mapping, tools: Mapping | None) -> dict:
    """The allowlisted view; raises ``KeyError("unknown_keys")`` unless ``set(config) == set(CONFIG_KEYS)``."""
    if not isinstance(config, Mapping) or set(config) != set(CONFIG_KEYS):
        raise KeyError("unknown_keys")
    out = {key: config[key] for key in ALLOWLIST}          # literal names only -- never `for k in config`
    out["tools"] = tool_ids(tools)
    return out


def tool_ids(tools: Mapping | None) -> list[str]:
    """Only the ids: ``tools.json`` may hold commands, args and env names beside them (spec §5.2)."""
    if not isinstance(tools, Mapping):
        return []
    entries = tools.get("tools")
    if isinstance(entries, Mapping):
        return sorted(str(k) for k in entries)
    if isinstance(entries, list):
        return sorted(str(e.get("id")) for e in entries if isinstance(e, Mapping) and isinstance(e.get("id"), str))
    return []


def _load(path: str) -> object:
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="projection.py", add_help=False)
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--tools", default=TOOLS_PATH)
    args = parser.parse_args(argv)
    for path in (args.config, args.tools):
        if BACKUP_RE.search(path):
            sys.stdout.write(json.dumps({"error": "refused_path"}) + "\n")
            return EXIT_REFUSED_PATH
    try:
        config = _load(args.config)
    except (OSError, ValueError):
        sys.stdout.write(json.dumps({"error": "unreadable"}) + "\n")
        return EXIT_UNREADABLE
    tools: object = None
    try:
        tools = _load(args.tools)
    except (OSError, ValueError):
        tools = None                                          # tools.json is optional
    try:
        payload = project(config, tools if isinstance(tools, Mapping) else None)
    except KeyError:
        sys.stdout.write(json.dumps({"error": "unknown_keys"}) + "\n")
        return EXIT_UNKNOWN_KEYS
    try:
        payload["configMtimeUtc"] = _mtime_iso(args.config)
    except OSError:
        payload["configMtimeUtc"] = None
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return EXIT_OK


def _mtime_iso(path: str) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.stat(path).st_mtime))


__all__ = ["ALLOWLIST", "BACKUP_RE", "CONFIG_KEYS", "CONFIG_PATH", "EXIT_OK", "EXIT_REFUSED_PATH", "EXIT_UNKNOWN_KEYS",
           "EXIT_UNREADABLE", "TOOLS_PATH", "main", "project", "tool_ids"]

if __name__ == "__main__":
    raise SystemExit(main())
