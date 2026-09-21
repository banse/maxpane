"""Capture the IMD swarm control plane's public reads into test fixtures.

Keyless, GET only. Run: .venv/bin/python scripts/capture_swarm.py

Writes ONLY into ``tests/fixtures/surf/swarm/v2/`` (plan A3): the six list routes, a details
corpus of the 25 newest jobs plus any 2026-09-16 job id from the old manifest that still answers,
and a ``MANIFEST.json`` whose ``criteria`` block is computed from the captured details — never
typed by hand. Hand-made shapes already recorded under ``hand_made`` are carried forward.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.error
import urllib.request
from typing import Any

# Plan R1: ``api.imd.fun`` is the public name of the same deployment that answers as
# ``https://identitymdcontrol-plane-production.up.railway.app`` (identical ``/version`` commit,
# measured 2026-09-21). Capture from the public name; the Railway host is the fallback.
API = "https://api.imd.fun"
SWARM = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "surf" / "swarm"
OUT = SWARM / "v2"
DETAILS = OUT / "details"
OLD_MANIFEST = SWARM / "MANIFEST.json"
UA = {"User-Agent": "maxpane-capture/0.2"}
PACE_S = 0.2
DETAILS_N = 25

LIST_ROUTES = (("health", "/health"), ("version", "/version"), ("jobs", "/jobs"),
               ("skills", "/skills"), ("launches", "/launches"), ("sites", "/sites"))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def get(path: str) -> tuple[bytes, str]:
    """GET a list route; any failure propagates (the six list routes are mandatory)."""
    req = urllib.request.Request(API + path, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read(), _now()


def try_get(path: str) -> tuple[bytes | None, str, int | str]:
    """GET a detail route; a 404 or any other failure is returned, never raised."""
    try:
        body, at = get(path)
        return body, at, 200
    except urllib.error.HTTPError as exc:
        return None, _now(), exc.code
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return None, _now(), type(exc).__name__


def write(name: str, path: str, body: bytes, at: str, files: dict) -> None:
    (OUT / f"{name}.json").write_bytes(body)
    files[name] = {"endpoint": path, "captured_at": at, "bytes": len(body)}


def summarize_detail(job: dict[str, Any]) -> dict[str, Any]:
    """What a reader needs to see which A1 criterion a detail satisfies."""
    nodes = [n for n in job.get("nodes") or [] if isinstance(n, dict)]
    seats = sorted({str(n["seat"]["tokenId"]) for n in nodes
                    if isinstance(n.get("seat"), dict) and n["seat"].get("tokenId") is not None})
    reviews = [r for r in job.get("reviews") or [] if isinstance(r, dict)]
    return {
        "state": job.get("state"),
        "node_states": [n.get("state") for n in nodes],
        "seats": seats,
        "has_review_entries": any(r.get("entries") for r in reviews),
        "failure_reasons": sum(1 for n in nodes if n.get("failureReason") is not None),
    }


def criteria(details: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Amendment A1's four selection criteria, evaluated over the captured details."""
    summaries = {jid: summarize_detail(job) for jid, job in details.items()}
    working = sorted(j for j, s in summaries.items() if "working" in s["node_states"])
    failed = sorted(j for j, s in summaries.items() if s["failure_reasons"] > 0)
    reviewed = sorted(j for j, s in summaries.items() if s["has_review_entries"])
    seat_jobs: dict[str, set[str]] = {}
    for jid, s in summaries.items():
        for seat in s["seats"]:
            seat_jobs.setdefault(seat, set()).add(jid)
    shared = sorted(set().union(*(jobs for jobs in seat_jobs.values() if len(jobs) >= 2))
                    if any(len(j) >= 2 for j in seat_jobs.values()) else set())
    return {
        "node_working": {"met": bool(working), "job_ids": working},
        "failure_reason": {"met": bool(failed), "job_ids": failed},
        "review_entries": {"met": bool(reviewed), "job_ids": reviewed},
        "seat_in_several_jobs": {"met": bool(shared), "job_ids": shared},
    }


def _version_commit(body: dict[str, Any]) -> tuple[str | None, Any]:
    field = next((k for k in body if "commit" in k.lower()), None)
    return field, (body.get(field) if field else None)


def _old_detail_ids() -> list[str]:
    if not OLD_MANIFEST.exists():
        return []
    old = json.loads(OLD_MANIFEST.read_text())
    ids = []
    for entry in old.values():
        ep = entry.get("endpoint", "") if isinstance(entry, dict) else ""
        if ep.startswith("/jobs/"):
            ids.append(ep.removeprefix("/jobs/"))
    return ids


def capture_detail(job_id: str, details: dict, absent: dict, manifest_details: dict) -> None:
    path = f"/jobs/{job_id}"
    body, at, status = try_get(path)
    if body is None:
        absent[job_id] = {"endpoint": path, "probed_at": at, "status": status}
        return
    try:
        job = json.loads(body)
    except ValueError:
        absent[job_id] = {"endpoint": path, "probed_at": at, "status": "non-JSON"}
        return
    (DETAILS / f"{job_id}.json").write_bytes(body)
    details[job_id] = job
    manifest_details[job_id] = {"endpoint": path, "captured_at": at, "bytes": len(body),
                                **summarize_detail(job)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    DETAILS.mkdir(exist_ok=True)
    previous: dict = {}
    if (OUT / "MANIFEST.json").exists():
        previous = json.loads((OUT / "MANIFEST.json").read_text())

    files: dict = {}
    for name, path in LIST_ROUTES:
        body, at = get(path)
        write(name, path, body, at, files)
        time.sleep(PACE_S)

    version_field, version_commit = _version_commit(json.loads((OUT / "version.json").read_text()))

    jobs = [j for j in json.loads((OUT / "jobs.json").read_text())["jobs"] if isinstance(j, dict)]
    newest = sorted(jobs, key=lambda j: str(j.get("createdAt", "")), reverse=True)[:DETAILS_N]

    details: dict[str, dict] = {}
    absent: dict = {}
    manifest_details: dict = {}
    for job in newest:
        capture_detail(str(job["id"]), details, absent, manifest_details)
        time.sleep(PACE_S)

    old_ids = _old_detail_ids()
    for job_id in old_ids:
        if job_id in details:
            continue
        capture_detail(job_id, details, absent, manifest_details)
        time.sleep(PACE_S)

    manifest = {
        "host": API,
        "version": version_commit,
        "version_field": version_field,
        "captured_at": _now(),
        "files": files,
        "details": dict(sorted(manifest_details.items())),
        "details_search": {
            "newest_from_jobs": DETAILS_N,
            "old_manifest_ids_probed": old_ids,
            "old_manifest_ids_present": sorted(i for i in old_ids if i in details),
        },
        "probed_absent": dict(sorted(absent.items())),
        "criteria": criteria(details),
        "hand_made": previous.get("hand_made", {}),
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(files)} list captures and {len(details)} details to {OUT}; "
          f"{len(absent)} probed absent")
    print(json.dumps(manifest["criteria"], indent=2))


if __name__ == "__main__":
    main()
