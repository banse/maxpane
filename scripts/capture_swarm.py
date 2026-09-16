"""Capture the IMD swarm control plane's public reads into test fixtures.

Keyless, GET only. Run: python3 scripts/capture_swarm.py
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request

API = "https://identitymdcontrol-plane-production.up.railway.app"
OUT = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "surf" / "swarm"
UA = {"User-Agent": "maxpane-capture/0.1"}


def get(path: str) -> tuple[bytes, str]:
    req = urllib.request.Request(API + path, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read(), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write(name: str, path: str, body: bytes, at: str, manifest: dict) -> None:
    (OUT / f"{name}.json").write_bytes(body)
    manifest[name] = {"endpoint": path, "captured_at": at, "bytes": len(body)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    for name, path in (("health", "/health"), ("jobs", "/jobs"),
                       ("launches", "/launches"), ("sites", "/sites")):
        body, at = get(path)
        write(name, path, body, at, manifest)
        time.sleep(0.2)

    jobs = json.loads((OUT / "jobs.json").read_text())["jobs"]
    wanted = {"executing": "job_executing", "blocked": "job_blocked",
              "completed": "job_completed"}
    for state, name in wanted.items():
        job = next((j for j in jobs if j["state"] == state), None)
        if job is None:
            raise SystemExit(f"no {state} job in this capture; re-run later")
        body, at = get(f"/jobs/{job['id']}")
        write(name, f"/jobs/{job['id']}", body, at, manifest)
        time.sleep(0.2)

    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(manifest)} captures to {OUT}")


if __name__ == "__main__":
    main()
