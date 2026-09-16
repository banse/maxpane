# Surf's swarm body (`s`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A fifth surf body, opened with `s`, showing what the IMD swarm is doing right now: who is working on what, what is stuck and why, what shipped, and how fast work moves.

**Architecture:** One keyless HTTP client against the swarm's control plane, one pure fold module, two refresh tiers with their own last-good slots, five new widgets (a hero and four panels) and one new screen mode. The client/fold split copies `surf_pool4_client.py` / `surf_pool4_market.py`; the body copies the `4` body end to end.

**Tech Stack:** Python 3.11, Textual 8.1.1, Rich, `httpx` (already a dependency), pytest with `asyncio_mode = "auto"`. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md`
**Research (every endpoint, size and timing):** `docs/imd_swarm_api.md`

## Global Constraints

- **Keyless.** No key, token or secret anywhere. The one host is `https://identitymdcontrol-plane-production.up.railway.app`.
- **Strictly read-only.** GET only. No write surface, no signing, no calldata.
- **No test may touch the network.** Assert it structurally: hand the client a transport that raises.
- **A failed read is `None`, never `0`.** An unread value renders `--`; a real zero renders `0`.
- **Never write a sentinel into a history series.** This body samples no series.
- **Escape every third-party string before markup** (`widgets/markup_safety.safe_markup`), and hand `Static`/`RichLog` a pre-built `rich.text.Text`, never a markup string, for anything the host wrote.
- **Fit on `rich.cells.cell_len`, never `len()`.**
- **Every displayed 0x address carries the copy icon** via `widgets/address.address_text` / `address_prose`; a transaction hash uses `short_hex` and gets no icon.
- **No layout pin may be raised for this body.** It gets its own two pins, measured in situ.
- **No ninth degraded group.** `SOURCES` stays at eight names; the swarm tiers name none.
- **Assert against composited output** (`_compositor.render_strips()`), never the content string.
- **Prove every test bites:** mutate, watch the *named* test go red, restore. Unique `PYTHONPYCACHEPREFIX` per mutation.
- `.venv/bin/python -m pytest <files>` only, in small batches. **Never the full suite** except Task 13. Never background a test run; `timeout` does not exist on macOS.
- Git: commit with an explicit pathspec (`git commit -m "…" -- <paths>`). Never `git add -A`, `git stash`, `git checkout --`, or push. ~300 untracked files belong to the owner.

### Names frozen by Tasks 1–5 — do not invent variants

| Name | Where | Signature |
|---|---|---|
| `SWARM_API` | `data/surf_swarm_client.py` | `str` — the one host |
| `SwarmClient` | `data/surf_swarm_client.py` | `OwnedHttpClient` subclass |
| `fetch_health` | `data/surf_swarm_client.py` | `async (self) -> dict \| None` |
| `fetch_jobs` | `data/surf_swarm_client.py` | `async (self) -> list[dict] \| None` |
| `fetch_job` | `data/surf_swarm_client.py` | `async (self, job_id: str) -> dict \| None` |
| `fetch_launches` | `data/surf_swarm_client.py` | `async (self) -> list[dict] \| None` |
| `fetch_sites` | `data/surf_swarm_client.py` | `async (self) -> list[dict] \| None` |
| `TERMINAL_STATES` | `data/surf_swarm.py` | `frozenset({"completed", "cancelled"})` |
| `health_facts` | `data/surf_swarm.py` | `(health: Mapping \| None) -> dict` |
| `queue_rows` | `data/surf_swarm.py` | `(jobs: Sequence[Mapping] \| None) -> list[dict]` |
| `blocked_rows` | `data/surf_swarm.py` | `(jobs, *, limit: int = 8) -> list[dict]` |
| `unfinished_ids` | `data/surf_swarm.py` | `(jobs) -> list[str]` |
| `field_rows` | `data/surf_swarm.py` | `(details: Sequence[Mapping], *, now: float) -> list[dict]` |
| `shipped_rows` | `data/surf_swarm.py` | `(jobs, details, launches, sites, *, limit: int = 12) -> list[dict]` |
| `score_rows` | `data/surf_swarm.py` | `(details) -> list[dict]` |
| `throughput` | `data/surf_swarm.py` | `(jobs, details, *, now: float, window_days: int = 7) -> dict` |
| `network_of` | `data/surf_swarm.py` | `(chain_id: object) -> str \| None` |
| `TIER_SWARM`, `TIER_SWARM_SCORES` | `data/surf_cache.py` | `"swarm"`, `"swarm_scores"` |
| `SLOT_SWARM`, `SLOT_SWARM_SCORES` | `data/surf_cache.py` | `"swarm"`, `"swarm_scores"` |
| `SWARM_KEYS` | `data/surf_models.py` | 18 payload keys, `swarm_`-prefixed |
| `SurfSwarmHero` | `widgets/surf/swarm_hero.py` | `Horizontal` |
| `SurfSwarmField` | `widgets/surf/swarm_field.py` | `Vertical` |
| `SurfSwarmQueue` | `widgets/surf/swarm_queue.py` | `Vertical` |
| `SurfSwarmShipped` | `widgets/surf/swarm_shipped.py` | `Vertical` |
| `SurfSwarmThroughput` | `widgets/surf/swarm_throughput.py` | `Vertical` |
| `MODE_SWARM` | `screens/surf.py` | `"swarm"` |
| `SWARM_BODY_ID`, `SWARM_LEFT_ID`, `SWARM_RAIL_ID` | `screens/surf.py` | `"surf-swarm-body"`, `"surf-swarm-left"`, `"surf-swarm-rail"` |
| `SURF_SWARM_FULL_LAYOUT_COLUMNS`, `SURF_SWARM_FULL_LAYOUT_ROWS` | `screens/surf.py` | measured in Task 12 |

## File Structure

**Created**

| File | Responsibility | Task |
|---|---|---|
| `scripts/capture_swarm.py` | re-capture the live payloads into fixtures | 0 |
| `tests/fixtures/surf/swarm/*.json` | committed captures + `MANIFEST.json` | 0 |
| `tests/surf_swarm_fixtures.py` | one loader the swarm tests share | 0 |
| `maxpane_dashboard/data/surf_swarm.py` | pure fold: no I/O, no clock, no Textual | 1 |
| `maxpane_dashboard/data/surf_swarm_client.py` | keyless HTTP, one host | 2 |
| `maxpane_dashboard/widgets/surf/swarm_hero.py` | AGENTS / IN FLIGHT / ACCEPTED TODAY | 6 |
| `maxpane_dashboard/widgets/surf/swarm_field.py` | THE FIELD | 7 |
| `maxpane_dashboard/widgets/surf/swarm_queue.py` | QUEUE | 8 |
| `maxpane_dashboard/widgets/surf/swarm_throughput.py` | THROUGHPUT | 8 |
| `maxpane_dashboard/widgets/surf/swarm_shipped.py` | JUST SHIPPED | 9 |
| `tests/screens/test_surf_swarm_layout.py` | the body's pins, sweeps, hint | 12 |

**Modified — one owner each**

| File | Task |
|---|---|
| `data/surf_cache.py` (+ its tier/slot tests) | 3 |
| `data/surf_models.py` (+ `tests/data/test_surf_models.py`) | 4 |
| `data/surf_manager.py` | 5 |
| `widgets/surf/__init__.py` | 6–9 (each exports its own class) |
| `screens/surf.py`, `themes/minimal.tcss` | 10 |
| `tests/screens/test_surf_screen.py` registries | 10 |
| `tests/test_surf_registration.py` (zero-catch triage, title row) | 11 |
| `tests/address_sweep/builders.py`, `tests/screens/test_address_icons_everywhere.py` | 13 |
| `CLAUDE.md`, `README.md`, the spec's status line | 14 |

## Wave order

```
Task 0  fixtures                      (everything else reads them)
Task 1  the fold          → Task 2 the client  → Task 3 cache → Task 4 models → Task 5 manager
Tasks 6-9 widgets                     (may run in parallel with each other after Task 4)
Task 10 the screen                    (after 5-9)
Task 11 zero-catch + title row        (after 10)
Task 12 pins and layout sweeps        (after 10)
Task 13 address sweep                 (after 12: it needs both pins)
Task 14 docs + full suite             (last)
```

---

## Task 0: Fixtures and the capture script

**Files:**
- Create: `scripts/capture_swarm.py`, `tests/surf_swarm_fixtures.py`, `tests/fixtures/surf/swarm/{health,jobs,job_executing,job_blocked,job_completed,launches,sites}.json`, `tests/fixtures/surf/swarm/MANIFEST.json`
- Test: `tests/data/test_surf_swarm_fixtures.py`

**Interfaces:**
- Produces: `tests.surf_swarm_fixtures.swarm_capture(name: str) -> Any` and the seven committed captures.

The controller already captured these bodies on 2026-09-16; re-capture them live so the committed files carry their own `captured_at`.

- [ ] **Step 1: Write the capture script**

```python
# scripts/capture_swarm.py
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
```

- [ ] **Step 2: Run it**

Run: `python3 scripts/capture_swarm.py`
Expected: `wrote 7 captures to …/tests/fixtures/surf/swarm`. If it exits with "no completed job", pick a different state's job by hand and say so in the report.

- [ ] **Step 3: Write the loader and its test**

```python
# tests/surf_swarm_fixtures.py
"""The committed swarm captures, exactly as the keyless API served them."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SWARM_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surf" / "swarm"


def swarm_capture(name: str) -> Any:
    with open(SWARM_FIXTURES / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)
```

```python
# tests/data/test_surf_swarm_fixtures.py
from tests.surf_swarm_fixtures import swarm_capture

def test_every_capture_has_the_shape_the_fold_expects():
    health = swarm_capture("health")
    for key in ("connectedDaemons", "activeEnrollments", "workingNow",
                "acceptedLastDay", "identity", "verifierUp"):
        assert key in health, key

    jobs = swarm_capture("jobs")["jobs"]
    assert jobs and all({"id", "state", "template", "objective", "createdAt",
                         "updatedAt"} <= set(j) for j in jobs)

    executing = swarm_capture("job_executing")
    assert executing["state"] == "executing"
    assert executing["nodes"], "the executing capture has no subtasks to render"

    blocked = swarm_capture("job_blocked")
    assert blocked["state"] == "blocked" and blocked["blockedReason"]

    done = swarm_capture("job_completed")
    assert done["reviews"], "the completed capture carries no review to score"
    assert done["reviews"][0]["entries"][0]["value"] is not None

    assert swarm_capture("launches")["launches"]
    assert swarm_capture("sites")["sites"]


def test_a_seat_and_a_chain_id_are_present_to_fold():
    seats = [n.get("seat") for n in swarm_capture("job_executing")["nodes"]]
    assert any(s and s.get("tokenId") for s in seats)
    assert swarm_capture("job_completed")["reviews"][0]["chainId"] == 11155111
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest tests/data/test_surf_swarm_fixtures.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_swarm.py tests/surf_swarm_fixtures.py tests/fixtures/surf/swarm tests/data/test_surf_swarm_fixtures.py
git commit -m "test(surf): capture the IMD swarm control plane's public reads" -- scripts/capture_swarm.py tests/surf_swarm_fixtures.py tests/fixtures/surf/swarm tests/data/test_surf_swarm_fixtures.py
```

---

## Task 1: The fold (`data/surf_swarm.py`)

**Files:**
- Create: `maxpane_dashboard/data/surf_swarm.py`
- Test: `tests/data/test_surf_swarm.py`

**Interfaces:**
- Consumes: the Task 0 captures.
- Produces: every `data/surf_swarm.py` name in the frozen table.

Pure: stdlib only. No `httpx`, no Textual, no `time.time()` — callers pass `now`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/data/test_surf_swarm.py
import datetime

from maxpane_dashboard.data import surf_swarm as S
from tests.surf_swarm_fixtures import swarm_capture

JOBS = swarm_capture("jobs")["jobs"]
EXECUTING = swarm_capture("job_executing")
BLOCKED = swarm_capture("job_blocked")
DONE = swarm_capture("job_completed")


def _ts(iso: str) -> float:
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


NOW = _ts("2026-09-16T18:00:00Z")


def test_health_facts_reads_the_counters_and_never_invents_a_zero():
    facts = S.health_facts(swarm_capture("health"))
    assert facts["agents_online"] == swarm_capture("health")["connectedDaemons"]
    assert facts["agents_enrolled"] == swarm_capture("health")["activeEnrollments"]
    assert facts["services_up"] == {"verifier": True, "publisher": True, "deployer": True}
    blank = S.health_facts(None)
    assert blank["agents_online"] is None and blank["accepted_today"] is None
    assert blank["services_up"] is None


def test_queue_rows_count_every_state_and_sort_by_size():
    rows = S.queue_rows(JOBS)
    assert sum(r["count"] for r in rows) == len(JOBS)
    assert rows == sorted(rows, key=lambda r: (-r["count"], r["state"]))
    assert S.queue_rows(None) == []


def test_blocked_rows_carry_the_reason_and_nothing_terminal():
    rows = S.blocked_rows(JOBS)
    assert rows, "the capture has blocked jobs"
    assert all(r["reason"] for r in rows)
    assert all(r["job_id"] and r["template"] for r in rows)
    assert all(j["state"] == "blocked"
               for j in JOBS if j["id"] in {r["job_id"] for r in rows})


def test_unfinished_ids_are_exactly_the_non_terminal_jobs():
    ids = S.unfinished_ids(JOBS)
    assert set(ids) == {j["id"] for j in JOBS if j["state"] not in S.TERMINAL_STATES}
    assert S.TERMINAL_STATES == frozenset({"completed", "cancelled"})


def test_field_rows_name_the_seat_and_keep_the_dispatch_note():
    rows = S.field_rows([EXECUTING], now=NOW)
    assert rows, "the executing capture has nodes"
    held = [r for r in rows if r["agent_token"] is not None]
    assert held, "no node in the capture names a seat"
    assert all(r["job_id"] == EXECUTING["id"] for r in rows)
    assert all(r["age_s"] >= 0 for r in rows)
    noted = [r for r in rows if r["dispatch_note"]]
    assert noted and "review" in noted[0]["dispatch_note"]


def test_field_rows_of_a_blocked_job_keep_the_failed_node():
    rows = S.field_rows([BLOCKED], now=NOW)
    assert any(r["node_state"] == "failed" for r in rows)


def test_score_rows_fold_one_row_per_agent():
    rows = S.score_rows([DONE])
    assert len(rows) == 1
    row = rows[0]
    entry = DONE["reviews"][0]["entries"][0]
    assert row["agent_id"] == entry["agentId"]
    assert row["jobs_scored"] == 1
    assert row["mean_score"] == float(entry["value"])
    assert row["last_tx_hash"] == DONE["reviews"][0]["txHash"]
    assert row["last_chain_id"] == DONE["reviews"][0]["chainId"]


def test_shipped_rows_mix_deliveries_launches_and_sites_newest_first():
    rows = S.shipped_rows(JOBS, [DONE], swarm_capture("launches")["launches"],
                          swarm_capture("sites")["sites"])
    kinds = {r["kind"] for r in rows}
    assert {"launch", "site"} <= kinds
    stamps = [r["at_ts"] for r in rows if r["at_ts"] is not None]
    assert stamps == sorted(stamps, reverse=True)
    launch = next(r for r in rows if r["kind"] == "launch")
    assert launch["address"] and launch["address"].startswith("0x")
    assert launch["chain_id"] is not None
    site = next(r for r in rows if r["kind"] == "site")
    assert site["ens_name"] and site["cid"]


def test_throughput_is_derived_and_says_its_window():
    out = S.throughput(JOBS, [DONE], now=NOW, window_days=7)
    assert out["window_days"] == 7
    assert out["accepted_per_day"] >= 0
    assert out["median_delivery_s"] is None or out["median_delivery_s"] > 0
    assert 0.0 <= out["revision_rate"] <= 1.0
    empty = S.throughput(None, None, now=NOW)
    assert empty["accepted_per_day"] is None and empty["revision_rate"] is None


def test_network_of_is_an_allowlist():
    assert S.network_of(11155111) == "SEPOLIA"
    assert S.network_of(1) == "MAINNET"
    assert S.network_of(999) is None
    assert S.network_of(None) is None
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_swarm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'maxpane_dashboard.data.surf_swarm'`

- [ ] **Step 3: Write the fold**

```python
# maxpane_dashboard/data/surf_swarm.py
"""Fold the IMD swarm control plane's reads into rows the panels render.

Pure: stdlib only.  No network, no clock (callers pass ``now``), no Textual.
The shapes this folds are recorded in ``docs/imd_swarm_api.md``; the reader
that fetches them is ``surf_swarm_client.py``.

Every value here is ``None`` when it was not read.  A zero is a zero.
"""
from __future__ import annotations

import datetime
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "TERMINAL_STATES", "blocked_rows", "field_rows", "health_facts",
    "network_of", "queue_rows", "score_rows", "shipped_rows", "throughput",
    "unfinished_ids",
]

#: A job in one of these states is finished; nothing else is.
TERMINAL_STATES = frozenset({"completed", "cancelled"})

#: Chain ids this view knows how to name.  An allowlist, so an unknown chain
#: renders the em dash rather than a guess (``_pool4.network_word``'s rule).
_NETWORKS = {1: "MAINNET", 11155111: "SEPOLIA"}

_SERVICES = {"verifier": "verifierUp", "publisher": "publisherUp",
             "deployer": "deployerUp"}


def network_of(chain_id: object) -> str | None:
    """``"MAINNET"`` / ``"SEPOLIA"``, or ``None`` for anything else."""
    try:
        return _NETWORKS.get(int(chain_id))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _ts(value: object) -> float | None:
    """One ISO-8601 stamp as epoch seconds, or ``None``."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def health_facts(health: Mapping[str, Any] | None) -> dict[str, Any]:
    """The hero's numbers.  Every one ``None`` when the read failed."""
    if not isinstance(health, Mapping):
        return {"agents_online": None, "agents_enrolled": None,
                "working_now": None, "accepted_today": None,
                "queue_depths": None, "services_up": None, "network": None}
    depths = {
        key[len("pending"):].lower(): _int(value)
        for key, value in health.items()
        if key.startswith("pending")
    }
    identity = health.get("identity")
    chain = identity.get("chainId") if isinstance(identity, Mapping) else None
    return {
        "agents_online": _int(health.get("connectedDaemons")),
        "agents_enrolled": _int(health.get("activeEnrollments")),
        "working_now": _int(health.get("workingNow")),
        "accepted_today": _int(health.get("acceptedLastDay")),
        "queue_depths": depths or None,
        "services_up": {
            name: bool(health.get(key)) for name, key in _SERVICES.items()
        },
        "network": network_of(chain),
    }


def queue_rows(jobs: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """``[{"state", "count"}]``, biggest first, ties by state name."""
    if not jobs:
        return []
    counts: dict[str, int] = {}
    for job in jobs:
        state = job.get("state")
        if isinstance(state, str) and state:
            counts[state] = counts.get(state, 0) + 1
    return [{"state": s, "count": c}
            for s, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def blocked_rows(jobs: Sequence[Mapping[str, Any]] | None, *,
                 limit: int = 8) -> list[dict[str, Any]]:
    """Blocked jobs, newest move first, with the reason the host gave."""
    if not jobs:
        return []
    rows = [
        {
            "job_id": job.get("id"),
            "template": job.get("template"),
            "reason": job.get("blockedReason"),
            "moved_ts": _ts(job.get("updatedAt")),
        }
        for job in jobs
        if job.get("state") == "blocked"
    ]
    rows.sort(key=lambda r: (r["moved_ts"] is None, -(r["moved_ts"] or 0.0)))
    return rows[:limit]


def unfinished_ids(jobs: Sequence[Mapping[str, Any]] | None) -> list[str]:
    """Ids of jobs still moving — the only details worth fetching."""
    if not jobs:
        return []
    return [
        job["id"] for job in jobs
        if isinstance(job.get("id"), str)
        and job.get("state") not in TERMINAL_STATES
    ]


def field_rows(details: Sequence[Mapping[str, Any]] | None, *,
               now: float) -> list[dict[str, Any]]:
    """One row per subtask of every unfinished job, newest move first."""
    if not details:
        return []
    rows: list[dict[str, Any]] = []
    for job in details:
        for node in job.get("nodes") or ():
            seat = node.get("seat") if isinstance(node.get("seat"), Mapping) else {}
            moved = _ts(node.get("updatedAt")) or _ts(job.get("updatedAt"))
            rows.append({
                "job_id": job.get("id"),
                "template": job.get("template"),
                "objective": job.get("objective"),
                "node_key": node.get("key"),
                "role": node.get("role"),
                "node_state": node.get("state"),
                "agent_token": seat.get("tokenId"),
                "agent_id": seat.get("agentId"),
                "revisions": _int(node.get("revisions")),
                "dispatch_note": node.get("dispatchNote") or None,
                "moved_ts": moved,
                "age_s": max(0.0, now - moved) if moved is not None else None,
            })
    rows.sort(key=lambda r: (r["moved_ts"] is None, -(r["moved_ts"] or 0.0)))
    return rows


def score_rows(details: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """One row per agent: how many scores, their mean, and the last tx."""
    if not details:
        return []
    per: dict[str, dict[str, Any]] = {}
    for job in details:
        for review in job.get("reviews") or ():
            chain = review.get("chainId")
            tx = review.get("txHash")
            sent = _ts(review.get("sentAt"))
            for entry in review.get("entries") or ():
                agent = entry.get("agentId")
                value = entry.get("value")
                if not isinstance(agent, str) or not isinstance(value, (int, float)):
                    continue
                row = per.setdefault(agent, {
                    "agent_id": agent, "agent_token": None, "values": [],
                    "last_tx_hash": None, "last_chain_id": None, "_last": None,
                })
                row["values"].append(float(value))
                if row["_last"] is None or (sent or 0.0) >= row["_last"]:
                    row["_last"] = sent or 0.0
                    row["last_tx_hash"] = tx
                    row["last_chain_id"] = chain
    out = []
    for row in per.values():
        values = row.pop("values")
        row.pop("_last")
        row["jobs_scored"] = len(values)
        row["mean_score"] = round(statistics.fmean(values), 1) if values else None
        out.append(row)
    out.sort(key=lambda r: (-(r["mean_score"] or 0.0), r["agent_id"]))
    return out


def shipped_rows(jobs: Sequence[Mapping[str, Any]] | None,
                 details: Sequence[Mapping[str, Any]] | None,
                 launches: Sequence[Mapping[str, Any]] | None,
                 sites: Sequence[Mapping[str, Any]] | None, *,
                 limit: int = 12) -> list[dict[str, Any]]:
    """Deliveries, deployed contracts and published sites, newest first."""
    rows: list[dict[str, Any]] = []
    for job in jobs or ():
        delivery = job.get("delivery")
        if not isinstance(delivery, Mapping):
            continue
        rows.append({
            "kind": "delivery", "job_id": job.get("id"),
            "label": job.get("template"), "commit": delivery.get("commit"),
            "chain_id": None, "address": None, "tx_hash": None,
            "ens_name": None, "cid": None,
            "at_ts": _ts(delivery.get("deliveredAt")),
        })
    for launch in launches or ():
        chain = launch.get("chainId")
        at = _ts(launch.get("updatedAt"))
        for artifact in launch.get("artifacts") or ():
            rows.append({
                "kind": "launch", "job_id": launch.get("id"),
                "label": artifact.get("name") or artifact.get("role"),
                "commit": launch.get("sourceCommit"), "chain_id": chain,
                "address": artifact.get("address"),
                "tx_hash": artifact.get("txHash"),
                "ens_name": None, "cid": None, "at_ts": at,
            })
    for site in sites or ():
        rows.append({
            "kind": "site", "job_id": site.get("jobId"),
            "label": site.get("label"), "commit": None, "chain_id": None,
            "address": None, "tx_hash": site.get("txHash"),
            "ens_name": site.get("ensName"), "cid": site.get("cid"),
            "at_ts": _ts(site.get("namedAt")) or _ts(site.get("pinnedAt")),
        })
    rows.sort(key=lambda r: (r["at_ts"] is None, -(r["at_ts"] or 0.0)))
    return rows[:limit]


def throughput(jobs: Sequence[Mapping[str, Any]] | None,
               details: Sequence[Mapping[str, Any]] | None, *,
               now: float, window_days: int = 7) -> dict[str, Any]:
    """Accepted per day, median delivery time, revision rate over a window."""
    if not jobs:
        return {"accepted_per_day": None, "median_delivery_s": None,
                "revision_rate": None, "window_days": window_days}
    floor = now - window_days * 86400
    delivered: list[float] = []
    accepted = 0
    for job in jobs:
        created = _ts(job.get("createdAt"))
        delivery = job.get("delivery")
        at = _ts(delivery.get("deliveredAt")) if isinstance(delivery, Mapping) else None
        if at is None or at < floor:
            continue
        accepted += 1
        if created is not None and at > created:
            delivered.append(at - created)
    revisions = [
        _int(node.get("revisions")) or 0
        for job in details or ()
        for node in job.get("nodes") or ()
    ]
    return {
        "accepted_per_day": round(accepted / window_days, 2),
        "median_delivery_s": round(statistics.median(delivered)) if delivered else None,
        "revision_rate": (
            round(sum(1 for r in revisions if r) / len(revisions), 3)
            if revisions else None
        ),
        "window_days": window_days,
    }
```

- [ ] **Step 4: Run and watch them pass**

Run: `.venv/bin/python -m pytest tests/data/test_surf_swarm.py -v`
Expected: 10 passed.

- [ ] **Step 5: Prove the tests bite**

| Mutation | Must turn red |
|---|---|
| `TERMINAL_STATES` drops `"cancelled"` | `test_unfinished_ids_are_exactly_the_non_terminal_jobs` |
| `health_facts` returns `0` instead of `None` for a missing read | `test_health_facts_reads_the_counters_and_never_invents_a_zero` |
| `_NETWORKS` gains `999: "MAINNET"` | `test_network_of_is_an_allowlist` |
| `shipped_rows` sorts ascending | `test_shipped_rows_mix_deliveries_launches_and_sites_newest_first` |
| `score_rows` counts entries instead of averaging | `test_score_rows_fold_one_row_per_agent` |

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(surf): fold the swarm control plane's reads into rows" -- maxpane_dashboard/data/surf_swarm.py tests/data/test_surf_swarm.py
```

---

## Task 2: The client (`data/surf_swarm_client.py`)

**Files:**
- Create: `maxpane_dashboard/data/surf_swarm_client.py`
- Test: `tests/data/test_surf_swarm_client.py`

**Interfaces:**
- Consumes: `rpc_common.OwnedHttpClient` (gives `close`, `__aenter__`, `__aexit__`; needs `self._client` and `self._owns_client`).
- Produces: `SWARM_API`, `SwarmClient`, `fetch_health`, `fetch_jobs`, `fetch_job`, `fetch_launches`, `fetch_sites`, `SWARM_REQUEST_TIMEOUT`, `SWARM_INTER_CALL_DELAY`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/data/test_surf_swarm_client.py
import httpx
import pytest

from maxpane_dashboard.data.surf_swarm_client import SWARM_API, SwarmClient
from tests.surf_swarm_fixtures import swarm_capture


def _client(handler, **kw) -> SwarmClient:
    return SwarmClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kw)


def _no_network(request):  # pragma: no cover - must never run
    raise AssertionError(f"a test reached the network: {request.url}")


async def test_every_read_is_a_keyless_get_against_the_one_host():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "ok"})

    async with _client(handler) as client:
        await client.fetch_health()

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "GET"
    assert str(request.url) == f"{SWARM_API}/health"
    lowered = {k.lower() for k in request.headers}
    assert not lowered & {"authorization", "x-api-key", "cookie", "token"}


async def test_jobs_and_launches_and_sites_unwrap_their_envelopes():
    def handler(request):
        name = {"/jobs": "jobs", "/launches": "launches", "/sites": "sites"}[request.url.path]
        return httpx.Response(200, json=swarm_capture(name))

    async with _client(handler) as client:
        jobs = await client.fetch_jobs()
        launches = await client.fetch_launches()
        sites = await client.fetch_sites()

    assert isinstance(jobs, list) and jobs[0]["id"]
    assert isinstance(launches, list) and launches[0]["artifacts"]
    assert isinstance(sites, list) and sites[0]["cid"]


async def test_a_job_detail_is_returned_whole():
    def handler(request):
        assert request.url.path.startswith("/jobs/")
        return httpx.Response(200, json=swarm_capture("job_executing"))

    async with _client(handler) as client:
        job = await client.fetch_job("4ba29896-6fd6-4e0f-aef3-82f1ec15f7c6")

    assert job["nodes"], "the detail must carry its subtasks"


async def test_a_404_on_one_job_is_none_not_a_raise():
    async with _client(lambda request: httpx.Response(404, json={"error": "gone"})) as client:
        assert await client.fetch_job("missing") is None


async def test_a_500_is_none_and_never_a_zero():
    async with _client(lambda request: httpx.Response(500, text="boom")) as client:
        assert await client.fetch_jobs() is None
        assert await client.fetch_health() is None


async def test_a_timeout_is_none():
    def handler(request):
        raise httpx.ConnectTimeout("slow", request=request)

    async with _client(handler) as client:
        assert await client.fetch_health() is None


async def test_malformed_json_is_none():
    async with _client(lambda request: httpx.Response(200, text="not json")) as client:
        assert await client.fetch_jobs() is None


async def test_an_envelope_without_its_list_is_none_not_an_empty_list():
    async with _client(lambda request: httpx.Response(200, json={"count": 0})) as client:
        assert await client.fetch_jobs() is None


async def test_the_client_paces_its_calls():
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    def handler(request):
        return httpx.Response(200, json={"count": 0, "jobs": []})

    client = _client(handler, sleep=fake_sleep)
    async with client:
        await client.fetch_jobs()
        await client.fetch_jobs()

    assert delays and all(d > 0 for d in delays)


async def test_a_test_client_never_reaches_the_network():
    async with _client(_no_network) as client:
        with pytest.raises(AssertionError):
            await client._get("/health", raw=True)
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_swarm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'maxpane_dashboard.data.surf_swarm_client'`

- [ ] **Step 3: Write the client**

```python
# maxpane_dashboard/data/surf_swarm_client.py
"""Keyless reads of the IMD swarm control plane (``docs/imd_swarm_api.md``).

GET only, one host, no key of any kind.  Every fetch returns ``None`` rather
than raising: a failed read is not a zero and not an empty list.

The host serves no filters, no caching validators and no pagination, so the
job list is all-or-nothing; the manager's counter check, not this client,
decides how often it is paid for.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from maxpane_dashboard.data.rpc_common import OwnedHttpClient

logger = logging.getLogger(__name__)

__all__ = [
    "SWARM_API", "SWARM_INTER_CALL_DELAY", "SWARM_REQUEST_TIMEOUT", "SwarmClient",
]

#: The swarm's control plane.  Named in the explorer's own page source; its
#: write surface is authenticated, these reads are the public subset.
SWARM_API = "https://identitymdcontrol-plane-production.up.railway.app"

SWARM_REQUEST_TIMEOUT = 15.0
#: Measured: 62 sequential detail reads at this spacing drew 62 × 200 with no
#: rate limiting (``docs/imd_swarm_api.md``).  It is politeness, not a limit.
SWARM_INTER_CALL_DELAY = 0.12


class SwarmClient(OwnedHttpClient):
    """Reads ``/health``, ``/jobs``, ``/jobs/{id}``, ``/launches``, ``/sites``."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = SWARM_API,
        inter_call_delay: float = SWARM_INTER_CALL_DELAY,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(SWARM_REQUEST_TIMEOUT),
            follow_redirects=True,
            headers={"Accept": "application/json"},
        )
        self._owns_client = http_client is None
        self._base = base_url.rstrip("/")
        self._delay = float(inter_call_delay)
        self._sleep = sleep or asyncio.sleep
        self._last_call: float = 0.0

    async def _get(self, path: str, *, raw: bool = False) -> Any:
        """One GET.  ``None`` on any failure — never a partial value."""
        await self._sleep(self._delay)
        try:
            response = await self._client.get(self._base + path)
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("swarm GET %s failed: %s", path, exc)
            return None
        if response.status_code != 200:
            logger.debug("swarm GET %s -> %s", path, response.status_code)
            return None
        if raw:
            return response.content
        try:
            return response.json()
        except ValueError as exc:
            logger.debug("swarm GET %s served non-JSON: %s", path, exc)
            return None

    async def fetch_health(self) -> dict[str, Any] | None:
        body = await self._get("/health")
        return body if isinstance(body, dict) else None

    async def _list(self, path: str, key: str) -> list[dict[str, Any]] | None:
        body = await self._get(path)
        if not isinstance(body, dict):
            return None
        rows = body.get(key)
        # A missing list is an unread list.  ``[]`` from the host is a real
        # empty and passes through.
        return rows if isinstance(rows, list) else None

    async def fetch_jobs(self) -> list[dict[str, Any]] | None:
        return await self._list("/jobs", "jobs")

    async def fetch_launches(self) -> list[dict[str, Any]] | None:
        return await self._list("/launches", "launches")

    async def fetch_sites(self) -> list[dict[str, Any]] | None:
        return await self._list("/sites", "sites")

    async def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        body = await self._get(f"/jobs/{job_id}")
        return body if isinstance(body, dict) else None
```

- [ ] **Step 4: Run and watch them pass**

Run: `.venv/bin/python -m pytest tests/data/test_surf_swarm_client.py -v`
Expected: 10 passed.

- [ ] **Step 5: Prove the tests bite**

| Mutation | Must turn red |
|---|---|
| `_list` returns `[]` when the key is missing | `test_an_envelope_without_its_list_is_none_not_an_empty_list` |
| `_get` drops the `status_code != 200` check | `test_a_500_is_none_and_never_a_zero` |
| `_get` re-raises `httpx.HTTPError` | `test_a_timeout_is_none` |
| `__init__` adds an `Authorization` header | `test_every_read_is_a_keyless_get_against_the_one_host` |

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(surf): keyless reads of the swarm control plane" -- maxpane_dashboard/data/surf_swarm_client.py tests/data/test_surf_swarm_client.py
```

---

## Task 3: Cache tiers and slots

**Files:**
- Modify: `maxpane_dashboard/data/surf_cache.py` (tier block ~:78-129, slot block ~:136-160, `__all__` ~:1068)
- Modify: `tests/data/test_surf_cache.py` (the literal `TIERS` assertion at ~:69, `len(SLOTS) == 9` at ~:224)
- Test: `tests/data/test_surf_cache_swarm.py`

**Interfaces:**
- Produces: `TIER_SWARM = "swarm"`, `TIER_SWARM_SCORES = "swarm_scores"`, `SLOT_SWARM = "swarm"`, `SLOT_SWARM_SCORES = "swarm_scores"`, their TTLs (60.0 / 1800.0) and backoffs (120.0 / 300.0).

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_surf_cache_swarm.py
from maxpane_dashboard.data.surf_cache import (
    SLOTS, SLOT_SWARM, SLOT_SWARM_SCORES, TIERS, TIER_FAILURE_BACKOFF_SECONDS,
    TIER_SWARM, TIER_SWARM_SCORES, TIER_TTL_SECONDS, SurfCache,
)


def test_the_swarm_has_two_tiers_with_their_own_ttls():
    assert TIER_SWARM in TIERS and TIER_SWARM_SCORES in TIERS
    assert TIER_TTL_SECONDS[TIER_SWARM] == 60.0
    assert TIER_TTL_SECONDS[TIER_SWARM_SCORES] == 1800.0
    for tier in (TIER_SWARM, TIER_SWARM_SCORES):
        backoff = TIER_FAILURE_BACKOFF_SECONDS[tier]
        assert 0.0 < backoff < TIER_TTL_SECONDS[tier], tier


def test_every_tier_has_both_a_ttl_and_a_backoff():
    assert set(TIER_TTL_SECONDS) == set(TIERS)
    assert set(TIER_FAILURE_BACKOFF_SECONDS) == set(TIERS)


def test_both_swarm_slots_are_registered_so_they_restore():
    assert SLOT_SWARM in SLOTS and SLOT_SWARM_SCORES in SLOTS


def test_a_failed_swarm_tier_keeps_its_slot_and_only_spaces_the_retry(tmp_path):
    cache = SurfCache(path=tmp_path / "surf.json")
    cache.store_last_good(SLOT_SWARM, {"agents_online": 2}, ts=1000.0)
    cache.mark_failed(TIER_SWARM, now=1000.0)
    assert cache.get_last_good(SLOT_SWARM).payload == {"agents_online": 2}
    assert not cache.is_due(TIER_SWARM, now=1000.0 + 60.0)
    assert cache.is_due(TIER_SWARM, now=1000.0 + 121.0)
```

- [ ] **Step 2: Run and watch it fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_cache_swarm.py -v`
Expected: FAIL — `ImportError: cannot import name 'TIER_SWARM'`

- [ ] **Step 3: Register the tiers and slots**

In `surf_cache.py`, after `TIER_POOL4_STAKERS`:

```python
#: The swarm's live read: ``/health`` every run, the job list only when a
#: counter moved, details for the jobs still moving.  60 s because the swarm
#: moves a few times an hour and the host is someone else's.
TIER_SWARM = "swarm"
#: The full 62-detail sweep behind the scores and the throughput numbers.
#: 188 KB, 25 s measured — half-hourly, never on the live path.
TIER_SWARM_SCORES = "swarm_scores"
```

Append both to `TIERS`, and add to both dicts:

```python
    TIER_SWARM: 60.0,
    TIER_SWARM_SCORES: 1800.0,
```
```python
    TIER_SWARM: 120.0,
    TIER_SWARM_SCORES: 300.0,
```

After `SLOT_POOL4_STAKERS`:

```python
SLOT_SWARM = "swarm"                  # health + jobs + the unfinished details
SLOT_SWARM_SCORES = "swarm_scores"    # the full sweep: scores, launches, sites
```

Append both to `SLOTS`, with the comment that neither is a degraded group:

```python
    # Neither is a ninth degraded *group*: `SOURCES` is full at eight names
    # (surf_manager.py:222) and the title row is pinned on it.  A failed swarm
    # read serves last-good behind its own marker, the staker sweep's rule.
    SLOT_SWARM,
    SLOT_SWARM_SCORES,
```

Add all four names to `__all__`.

- [ ] **Step 4: Update the two literal tests**

`tests/data/test_surf_cache.py` asserts the `TIERS` tuple element by element and `len(SLOTS) == 9`. Both are hand-typed on purpose — edit them to the new literals (eight tiers, eleven slots), never to a derivation.

- [ ] **Step 5: Run**

Run: `.venv/bin/python -m pytest tests/data/test_surf_cache_swarm.py tests/data/test_surf_cache.py tests/data/test_surf_cache_pool4.py -v`
Expected: all pass.

- [ ] **Step 6: Prove it bites**

Remove `SLOT_SWARM` from `SLOTS` → `test_both_swarm_slots_are_registered_so_they_restore` red. Set the backoff above the TTL → `test_the_swarm_has_two_tiers_with_their_own_ttls` red. Restore both.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(surf): two cache tiers and slots for the swarm" -- maxpane_dashboard/data/surf_cache.py tests/data/test_surf_cache.py tests/data/test_surf_cache_swarm.py
```

---

## Task 4: The payload contract (`data/surf_models.py`)

**Files:**
- Modify: `maxpane_dashboard/data/surf_models.py` (add `SWARM_KEYS`, splice into `SURF_KEYS`, add five `SURF_ROW_KEYS` entries)
- Modify: `tests/data/test_surf_models.py` (`EXPECTED_KEYS` and the three hard counts at ~:518)
- Test: `tests/data/test_surf_swarm_models.py`

**Interfaces:**
- Produces: the 18 `swarm_*` keys and the five row shapes every widget and test indexes.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_surf_swarm_models.py
from maxpane_dashboard.data.surf_models import SURF_KEYS, SURF_ROW_KEYS, SWARM_KEYS

SWARM_ROW_NAMES = ("swarm_field_rows", "swarm_queue_rows", "swarm_blocked_rows",
                   "swarm_shipped_rows", "swarm_score_rows")


def test_the_swarm_block_is_eighteen_keys():
    assert len(SWARM_KEYS) == 18
    assert len(set(SWARM_KEYS)) == 18
    assert all(k.startswith("swarm_") for k in SWARM_KEYS)


def test_every_swarm_key_appears_in_surf_keys_exactly_once():
    for key in SWARM_KEYS:
        assert SURF_KEYS.count(key) == 1, key


def test_the_swarm_block_is_contiguous_and_last():
    positions = [SURF_KEYS.index(k) for k in SWARM_KEYS]
    assert positions == sorted(positions)
    assert positions == list(range(positions[0], positions[0] + len(SWARM_KEYS)))
    assert positions[-1] == len(SURF_KEYS) - 1


def test_every_swarm_row_shape_is_declared_and_is_a_payload_key():
    for name in SWARM_ROW_NAMES:
        assert name in SURF_ROW_KEYS, name
        assert SURF_ROW_KEYS[name], name
        assert name in SURF_KEYS, name


def test_the_field_row_is_exactly_the_frozen_shape():
    assert SURF_ROW_KEYS["swarm_field_rows"] == (
        "job_id", "template", "objective", "node_key", "role", "node_state",
        "agent_token", "agent_id", "revisions", "dispatch_note", "moved_ts",
        "age_s",
    )


def test_no_swarm_key_leaks_a_raw_envelope():
    for bad in ("swarm_jobs", "swarm_health", "swarm_details"):
        assert bad not in SURF_KEYS
```

- [ ] **Step 2: Run and watch it fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_swarm_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'SWARM_KEYS'`

- [ ] **Step 3: Declare the block**

```python
#: The `s` body's flat keys (spec §4).  One block, spliced whole into
#: SURF_KEYS after the pool4 blocks, so its position is checkable.
SWARM_KEYS: tuple[str, ...] = (
    "swarm_agents_online",      # int | None   -- connected daemons
    "swarm_agents_enrolled",    # int | None   -- active enrollments
    "swarm_working_now",        # int | None   -- daemons working this moment
    "swarm_accepted_today",     # int | None   -- accepted in the last day
    "swarm_jobs_in_flight",     # int | None   -- jobs in state executing
    "swarm_jobs_blocked",       # int | None   -- jobs in state blocked
    "swarm_queue_depths",       # dict | None  -- pending* counters by name
    "swarm_services_up",        # dict | None  -- verifier/publisher/deployer
    "swarm_field_rows",         # list[dict]   -- one per unfinished subtask
    "swarm_queue_rows",         # list[dict]   -- state -> count
    "swarm_blocked_rows",       # list[dict]   -- blocked jobs and their reason
    "swarm_shipped_rows",       # list[dict]   -- deliveries, launches, sites
    "swarm_score_rows",         # list[dict]   -- per agent, from the sweep
    "swarm_throughput",         # dict | None  -- accepted/day, median, revisions
    "swarm_network",            # str | None   -- MAINNET / SEPOLIA / None
    "swarm_as_of_hhmm",         # str | None   -- SLOT_SWARM's marker
    "swarm_scores_as_of_hhmm",  # str | None   -- SLOT_SWARM_SCORES' marker
    "swarm_stale",              # bool | None  -- the two markers drifted
)
```

Splice `*SWARM_KEYS` at the **end** of `SURF_KEYS`, and add the five row shapes to `SURF_ROW_KEYS`:

```python
    "swarm_field_rows": (
        "job_id", "template", "objective", "node_key", "role", "node_state",
        "agent_token", "agent_id", "revisions", "dispatch_note", "moved_ts",
        "age_s",
    ),
    "swarm_queue_rows": ("state", "count"),
    "swarm_blocked_rows": ("job_id", "template", "reason", "moved_ts"),
    "swarm_shipped_rows": (
        "kind", "job_id", "label", "commit", "chain_id", "address", "tx_hash",
        "ens_name", "cid", "at_ts",
    ),
    "swarm_score_rows": (
        "agent_id", "agent_token", "jobs_scored", "mean_score",
        "last_tx_hash", "last_chain_id",
    ),
```

- [ ] **Step 4: Update the hand-typed contract test**

`tests/data/test_surf_models.py::test_surf_keys_is_exactly_the_prd_contract` holds a hand-typed `EXPECTED_KEYS` set and three counts (`159`, `71`, `5`, and the `83` remainder). Add the eighteen names to `EXPECTED_KEYS` by hand, and change the total to `177`. Keep the remainder arithmetic honest: it becomes `len(SURF_KEYS) - len(POOL4_KEYS) - len(POOL4_STAKERS_KEYS) - len(SWARM_KEYS) == 83`.

- [ ] **Step 5: Run**

Run: `.venv/bin/python -m pytest tests/data/test_surf_swarm_models.py tests/data/test_surf_models.py tests/data/test_surf_pool4_models.py -v`
Expected: all pass.

- [ ] **Step 6: Prove it bites**

Move one `swarm_*` key to the middle of `SURF_KEYS` → `test_the_swarm_block_is_contiguous_and_last` red. Drop a field from the field row shape → `test_the_field_row_is_exactly_the_frozen_shape` red. Restore.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(surf): declare the swarm payload contract" -- maxpane_dashboard/data/surf_models.py tests/data/test_surf_models.py tests/data/test_surf_swarm_models.py
```

---

## Task 5: Manager wiring

**Files:**
- Modify: `maxpane_dashboard/data/surf_manager.py` — imports (~:152-173), constructor (~:828-897), `close()` (~:912-938), the four-method set, `_cycle` (~:5202 due set, slot capture ~:5251, spawns ~:5271/5362, `data.update` ~:5536), `__all__` (~:5737)
- Test: `tests/data/test_surf_manager_swarm.py`

**Interfaces:**
- Consumes: `SwarmClient`, the fold, the tiers and slots, `SWARM_KEYS`.
- Produces: `SurfManager(swarm_client=…)`, `_spawn_swarm`, `_swarm_detached`, `_cancel_swarm`, `_pool_swarm`, `_spawn_swarm_scores`, `_swarm_scores_detached`, `_cancel_swarm_scores`, `_pool_swarm_scores`, `_swarm_keys`, `_swarm_scores_keys`, `SWARM_STALE_AFTER_S = 1860.0`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/data/test_surf_manager_swarm.py
import asyncio

import pytest

from maxpane_dashboard.data.surf_cache import (
    SLOT_SWARM, SLOT_SWARM_SCORES, TIER_SWARM, TIER_SWARM_SCORES,
)
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data.surf_models import SURF_KEYS
from tests.surf_swarm_fixtures import swarm_capture


class _FakeSwarm:
    """Serves the committed captures and counts what was asked for."""

    def __init__(self, *, jobs=None, health=None, fail=False):
        self.health_calls = 0
        self.job_calls = 0
        self.detail_calls: list[str] = []
        self._jobs = swarm_capture("jobs")["jobs"] if jobs is None else jobs
        self._health = swarm_capture("health") if health is None else health
        self._fail = fail

    async def fetch_health(self):
        self.health_calls += 1
        return None if self._fail else dict(self._health)

    async def fetch_jobs(self):
        self.job_calls += 1
        return None if self._fail else list(self._jobs)

    async def fetch_job(self, job_id):
        self.detail_calls.append(job_id)
        for name in ("job_executing", "job_blocked", "job_completed"):
            job = swarm_capture(name)
            if job["id"] == job_id:
                return job
        return swarm_capture("job_executing")

    async def fetch_launches(self):
        return swarm_capture("launches")["launches"]

    async def fetch_sites(self):
        return swarm_capture("sites")["sites"]

    async def close(self):
        return None


def _manager(tmp_path, swarm, **kw) -> SurfManager:
    return SurfManager(cache_path=tmp_path / "surf.json", swarm_client=swarm, **kw)


async def test_the_first_payload_is_not_behind_the_swarm_read(tmp_path):
    class _Slow(_FakeSwarm):
        async def fetch_health(self):
            await asyncio.sleep(30)
            raise AssertionError("first paint waited for the swarm")

    manager = _manager(tmp_path, _Slow())
    payload = await asyncio.wait_for(manager.fetch_and_compute(), timeout=2.0)
    assert set(payload) == set(SURF_KEYS)
    await manager.close()


async def test_only_one_swarm_sweep_is_ever_in_flight(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    await manager.fetch_and_compute()
    first = manager._swarm_task
    await manager.fetch_and_compute()
    assert manager._swarm_task is first
    await manager.close()


async def test_details_are_fetched_only_for_unfinished_jobs(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    unfinished = {j["id"] for j in swarm._jobs if j["state"] not in ("completed", "cancelled")}
    assert set(swarm.detail_calls) == unfinished
    assert len(swarm.detail_calls) < len(swarm._jobs)
    await manager.close()


async def test_the_job_list_is_not_re_read_when_no_counter_moved(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    manager.cache.mark_failed(TIER_SWARM, now=0.0)  # make it due again
    await manager._pool_swarm({TIER_SWARM}, manager._now() + 61.0)
    assert swarm.health_calls == 2
    assert swarm.job_calls == 1, "the list was paid for twice with nothing moved"
    await manager.close()


async def test_a_moved_counter_forces_the_list(tmp_path):
    swarm = _FakeSwarm()
    manager = _manager(tmp_path, swarm)
    await manager.fetch_and_compute()
    await manager._swarm_task
    swarm._health = dict(swarm._health, acceptedLastDay=swarm._health["acceptedLastDay"] + 1)
    await manager._pool_swarm({TIER_SWARM}, manager._now() + 61.0)
    assert swarm.job_calls == 2
    await manager.close()


async def test_a_failed_swarm_read_names_no_degraded_group(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm(fail=True))
    payload = await manager.fetch_and_compute()
    await asyncio.gather(manager._swarm_task, return_exceptions=True)
    payload = await manager.fetch_and_compute()
    assert "swarm" not in payload["degraded"]
    assert all(not g.startswith("swarm") for g in payload["degraded"])
    await manager.close()


async def test_the_payload_is_exactly_the_contract_with_or_without_the_swarm(tmp_path):
    for swarm in (_FakeSwarm(), _FakeSwarm(fail=True)):
        manager = _manager(tmp_path, swarm)
        payload = await manager.fetch_and_compute()
        assert set(payload) == set(SURF_KEYS)
        await manager.close()


async def test_the_swarm_keys_are_filled_from_the_slot(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm())
    await manager.fetch_and_compute()
    await manager._swarm_task
    payload = await manager.fetch_and_compute()
    assert payload["swarm_agents_online"] == swarm_capture("health")["connectedDaemons"]
    assert payload["swarm_field_rows"], "no field rows published"
    assert payload["swarm_queue_rows"], "no queue rows published"
    assert payload["swarm_as_of_hhmm"], "no marker published"
    await manager.close()
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/python -m pytest tests/data/test_surf_manager_swarm.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'swarm_client'`

- [ ] **Step 3: Wire the constructor and lifecycle**

Imports: add `SLOT_SWARM, SLOT_SWARM_SCORES, TIER_SWARM, TIER_SWARM_SCORES` to the `surf_cache` import block, `from maxpane_dashboard.data import surf_swarm as sw`, and `from maxpane_dashboard.data.surf_swarm_client import SwarmClient`.

In `__init__`, beside `pool4_client`:

```python
        swarm_client: Any = None,
```
```python
        self.swarm_client = swarm_client if swarm_client is not None else SwarmClient()
        self._swarm_task: Any = None
        self._swarm_scores_task: Any = None
        #: The `/health` counters the last live read saw, so the 27.5 KB job
        #: list is only paid for when one of them moved (spec §3).
        self._swarm_counters: dict[str, Any] | None = None
        self._swarm_jobs_read_ts: float = 0.0
```

In `close()`, before `self.save_cache()`:

```python
        await self._cancel_swarm()
        await self._cancel_swarm_scores()
```
and close the client in its own `try`, beside the others.

Add the module constant beside the other window constants:

```python
#: The two swarm markers may legitimately differ by the live TTL plus the
#: sweep's; further apart than that is stale (the staker rule, spec §6).
SWARM_STALE_AFTER_S = 1860.0
#: The live tier re-reads the job list at least this often even when no
#: `/health` counter moved, so a silent list change cannot age forever.
SWARM_LIST_CEILING_S = 300.0
```

- [ ] **Step 4: Write the live tier's four methods**

```python
    def _spawn_swarm(self, tiers: set[str], now: float) -> Any:
        if TIER_SWARM not in tiers:
            return None
        running = self._swarm_task
        if running is not None and not running.done():
            logger.debug("SURF swarm read still in flight; not starting another")
            return running
        self._swarm_task = asyncio.ensure_future(self._swarm_detached(tiers, now))
        return self._swarm_task

    async def _swarm_detached(self, tiers: set[str], now: float) -> None:
        try:
            await self._pool_swarm(tiers, now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - a detached read never escapes
            logger.debug("SURF swarm read failed: %s", exc)

    async def _cancel_swarm(self) -> None:
        task = self._swarm_task
        self._swarm_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def _pool_swarm(self, tiers: set[str], now: float) -> dict[str, Any]:
        """`/health`, the list when a counter moved, details for the unfinished."""
        if TIER_SWARM not in tiers:
            return {"ok": False, "payload": None}
        client = self.swarm_client
        health = await self._guard(lambda: client.fetch_health(), "swarm fetch_health")
        if health is None:
            self.cache.mark_failed(TIER_SWARM, now)
            return {"ok": False, "payload": None}

        counters = {k: health.get(k) for k in _SWARM_COUNTER_KEYS}
        prior = getattr(self.cache.get_last_good(SLOT_SWARM), "payload", None)
        jobs = prior.get("jobs") if isinstance(prior, dict) else None
        stale_list = (now - self._swarm_jobs_read_ts) >= SWARM_LIST_CEILING_S
        if jobs is None or counters != self._swarm_counters or stale_list:
            fetched = await self._guard(lambda: client.fetch_jobs(), "swarm fetch_jobs")
            if fetched is not None:
                jobs = fetched
                self._swarm_jobs_read_ts = now
        if jobs is None:
            self.cache.mark_failed(TIER_SWARM, now)
            return {"ok": False, "payload": None}
        self._swarm_counters = counters

        details = []
        for job_id in sw.unfinished_ids(jobs):
            detail = await self._guard(
                lambda jid=job_id: client.fetch_job(jid), "swarm fetch_job"
            )
            if detail is not None:      # a 404 drops one row, never the read
                details.append(detail)

        payload = {"health": health, "jobs": jobs, "details": details}
        self.cache.store_last_good(SLOT_SWARM, payload, ts=now)
        self.cache.mark_fetched(TIER_SWARM, now)
        return {"ok": True, "payload": payload}
```

with, beside the other module constants:

```python
#: The `/health` fields whose movement means the job list changed.
_SWARM_COUNTER_KEYS = (
    "connectedDaemons", "activeEnrollments", "workingNow", "acceptedLastDay",
    "pendingVerification", "pendingAttestation", "pendingDeployment",
    "pendingDelivery", "pendingFeedback", "pendingFuzz", "pendingSites",
)
```

- [ ] **Step 5: Write the sweep tier's four methods**

Same four shapes with `TIER_SWARM_SCORES`, `SLOT_SWARM_SCORES` and `self._swarm_scores_task`; its `_pool_swarm_scores` reads the job list, every detail, `/launches` and `/sites`, and stores `{"details": [...], "launches": [...], "sites": [...]}`. It **never** touches the live slot.

- [ ] **Step 6: Publish the keys**

```python
    def _swarm_keys(self, slot: dict[str, Any], entry: Any, now: float) -> dict[str, Any]:
        """SLOT_SWARM -> the live `swarm_*` keys.  Unread stays None."""
        health = slot.get("health") if slot else None
        jobs = slot.get("jobs") if slot else None
        details = slot.get("details") if slot else None
        facts = sw.health_facts(health)
        queue = sw.queue_rows(jobs)
        by_state = {row["state"]: row["count"] for row in queue}
        return {
            "swarm_agents_online": facts["agents_online"],
            "swarm_agents_enrolled": facts["agents_enrolled"],
            "swarm_working_now": facts["working_now"],
            "swarm_accepted_today": facts["accepted_today"],
            "swarm_jobs_in_flight": by_state.get("executing") if jobs else None,
            "swarm_jobs_blocked": by_state.get("blocked") if jobs else None,
            "swarm_queue_depths": facts["queue_depths"],
            "swarm_services_up": facts["services_up"],
            "swarm_field_rows": sw.field_rows(details, now=now),
            "swarm_queue_rows": queue,
            "swarm_blocked_rows": sw.blocked_rows(jobs),
            "swarm_network": facts["network"],
            "swarm_as_of_hhmm": entry.as_of_hhmm() if entry is not None else None,
        }
```

`_swarm_scores_keys(self, slot, entry, live_entry)` publishes `swarm_shipped_rows`, `swarm_score_rows`, `swarm_throughput`, `swarm_scores_as_of_hhmm`, and `swarm_stale` — `True` only when both markers exist and differ by more than `SWARM_STALE_AFTER_S`, else `False`, and `None` when either is missing.

In `_cycle`: capture both slots **before** the spawns, spawn the live tier early and the sweep beside the staker spawn, then `data.update(self._swarm_keys(...))` and `data.update(self._swarm_scores_keys(...))` next to the pool4 updates. Add the new names to `__all__`.

- [ ] **Step 7: Run**

Run: `.venv/bin/python -m pytest tests/data/test_surf_manager_swarm.py -v`
Expected: 8 passed.
Then: `.venv/bin/python -m pytest tests/data/test_surf_manager_pool4.py tests/data/test_surf_manager_pool4_market.py -q` — unchanged, still green.

- [ ] **Step 8: Prove the tests bite**

| Mutation | Must turn red |
|---|---|
| fetch every job's detail, not just the unfinished | `test_details_are_fetched_only_for_unfinished_jobs` |
| drop the `counters != self._swarm_counters` guard | `test_the_job_list_is_not_re_read_when_no_counter_moved` |
| `await self._swarm_detached(...)` instead of spawning | `test_the_first_payload_is_not_behind_the_swarm_read` (times out) |
| add `"swarm"` to `GROUP_SLOT` | `test_a_failed_swarm_read_names_no_degraded_group` |

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(surf): two swarm tiers, their slots and their payload keys" -- maxpane_dashboard/data/surf_manager.py tests/data/test_surf_manager_swarm.py
```

---

## Task 6: The hero (`SurfSwarmHero`)

**Files:**
- Create: `maxpane_dashboard/widgets/surf/swarm_hero.py`
- Modify: `maxpane_dashboard/widgets/surf/__init__.py` (import + `__all__`)
- Test: `tests/widgets/test_surf_swarm_hero.py`

**Interfaces:**
- Consumes: `swarm_agents_online`, `swarm_agents_enrolled`, `swarm_working_now`, `swarm_accepted_today`, `swarm_jobs_in_flight`, `swarm_jobs_blocked`, `swarm_services_up`.
- Produces: `SurfSwarmHero`, `CARD_IDS`, `UNAVAILABLE = "unavailable"`.

Copy `widgets/surf/pool4u_hero.py` exactly: `Horizontal` of three `Static` cards, `height: 6`, `padding: 0 2`, `margin: 0 1`, `border: solid $panel`, **no vertical padding**, every card rewritten on every render, `update_data(..., **_kwargs)`, `on_resize` re-render.

- [ ] **Step 1: Write the failing test**

```python
# tests/widgets/test_surf_swarm_hero.py
from maxpane_dashboard.widgets.surf.swarm_hero import SurfSwarmHero, UNAVAILABLE
from tests.widgets.surf_compositing import composite_lines

KW = {"swarm_agents_online": 2, "swarm_agents_enrolled": 3, "swarm_working_now": 0,
      "swarm_accepted_today": 13, "swarm_jobs_in_flight": 2, "swarm_jobs_blocked": 6,
      "swarm_services_up": {"verifier": True, "publisher": True, "deployer": True}}


async def _hero(**kwargs):
    merged = {**KW, **kwargs}
    lines = await composite_lines(SurfSwarmHero, (120, 8), **merged)
    return "\n".join(lines)


async def test_the_three_cards_carry_their_numbers():
    text = await _hero()
    assert "AGENTS" in text and "2 of 3" in text
    assert "IN FLIGHT" in text and "2" in text
    assert "ACCEPTED TODAY" in text and "13" in text


async def test_a_blocked_count_is_named_beside_in_flight():
    assert "6 blocked" in await _hero()


async def test_an_unread_count_says_so_and_never_prints_zero():
    text = await _hero(swarm_agents_online=None, swarm_agents_enrolled=None)
    assert UNAVAILABLE in text
    assert "0 of 0" not in text


async def test_a_real_zero_is_a_zero():
    text = await _hero(swarm_jobs_in_flight=0, swarm_jobs_blocked=0)
    assert UNAVAILABLE not in text.split("IN FLIGHT")[1].split("ACCEPTED")[0]


async def test_a_service_that_is_down_is_named():
    text = await _hero(swarm_services_up={"verifier": False, "publisher": True, "deployer": True})
    assert "verifier down" in text
```

- [ ] **Step 2: Run, fail, implement, run**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_swarm_hero.py -v` → fails on the missing module, then passes (5 passed) once written. Export the class from `widgets/surf/__init__.py`.

- [ ] **Step 3: Prove it bites**

Render a `None` count as `0` → `test_an_unread_count_says_so_and_never_prints_zero` red. Restore.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(surf): the swarm body's hero cards" -- maxpane_dashboard/widgets/surf/swarm_hero.py maxpane_dashboard/widgets/surf/__init__.py tests/widgets/test_surf_swarm_hero.py
```

---

## Task 7: THE FIELD (`SurfSwarmField`)

**Files:**
- Create: `maxpane_dashboard/widgets/surf/swarm_field.py`
- Modify: `maxpane_dashboard/widgets/surf/__init__.py`
- Test: `tests/widgets/test_surf_swarm_field.py`

**Interfaces:**
- Consumes: `swarm_field_rows`, `swarm_as_of_hhmm`, `swarm_network`, `swarm_stale`.
- Produces: `SurfSwarmField`, `TITLE = "THE FIELD"`, `FULL_WIDTH`, `COMPACT_WIDTH`, `MINIMAL_WIDTH`, `EMPTY_LINE = "nothing in flight"`, `UNAVAILABLE_LINE = "unavailable"`.

A `RichLog` panel on `widgets/surf/activity.py`'s shape: `Static` title, `Static(" ")` blank row, `RichLog(wrap=False, markup=False)`. Rows are pre-built `Text`. Columns, widest first: agent (`#2`), subtask (`node_key`), role, state, age, revisions, then the dispatch note in the remaining width. Tiers drop the note (compact), then role and revisions (minimal), advertising each with `‹ widen` through `_pool4.title_text`.

- [ ] **Step 1: Write the failing test**

```python
# tests/widgets/test_surf_swarm_field.py
from maxpane_dashboard.widgets.surf.swarm_field import (
    COMPACT_WIDTH, EMPTY_LINE, FULL_WIDTH, SurfSwarmField, UNAVAILABLE_LINE,
)
from tests.widgets.surf_compositing import composite_lines

ROWS = [
    {"job_id": "4ba29896-6fd6-4e0f-aef3-82f1ec15f7c6", "template": "shape:chain",
     "objective": "Build an ERC-4626 vault", "node_key": "adversarial_review",
     "role": "review", "node_state": "ready", "agent_token": None, "agent_id": None,
     "revisions": 0, "dispatch_note": "a review needs a contributor who did not author this work",
     "moved_ts": 1_789_000_000.0, "age_s": 3600.0},
    {"job_id": "9c6543f5-1111-2222-3333-444455556666", "template": "shape:chain",
     "objective": "Build a dapp", "node_key": "build_website", "role": "implement",
     "node_state": "accepted", "agent_token": "2", "agent_id": "10303",
     "revisions": 1, "dispatch_note": None,
     "moved_ts": 1_789_003_600.0, "age_s": 120.0},
]


async def _field(size=(120, 14), **kwargs):
    kwargs.setdefault("swarm_field_rows", ROWS)
    kwargs.setdefault("swarm_network", "SEPOLIA")
    lines = await composite_lines(SurfSwarmField, size, **kwargs)
    return lines, "\n".join(lines)


async def test_a_held_subtask_names_its_agent_and_its_age():
    _lines, text = await _field()
    assert "#2" in text
    assert "build_website" in text
    assert "2m" in text or "120" in text


async def test_an_unheld_subtask_shows_a_dash_not_an_agent():
    _lines, text = await _field()
    field_rows = [ln for ln in text.split("\n") if "adversarial_review" in ln]
    assert field_rows and "#" not in field_rows[0].split("adversarial_review")[0]


async def test_the_dispatch_note_explains_the_stall_at_full_width():
    _lines, text = await _field(size=(FULL_WIDTH + 4, 14))
    assert "did not author" in text


async def test_the_note_is_dropped_with_a_marker_when_narrow():
    _lines, text = await _field(size=(COMPACT_WIDTH + 2, 14))
    assert "did not author" not in text
    assert "‹" in text


async def test_an_empty_field_is_not_an_unread_field():
    _lines, empty = await _field(swarm_field_rows=[])
    assert EMPTY_LINE in empty
    _lines, unread = await _field(swarm_field_rows=None)
    assert UNAVAILABLE_LINE in unread


async def test_the_title_carries_the_as_of_marker():
    _lines, text = await _field(swarm_as_of_hhmm="13:18")
    assert "13:18" in text


async def test_a_hostile_objective_renders_as_text():
    rows = [dict(ROWS[0], objective="[/x] crash me", dispatch_note="[bold]no[/]")]
    _lines, text = await _field(swarm_field_rows=rows)
    assert "crash me" in text or "[/x]" in text
```

- [ ] **Step 2: Run, fail, implement, run**

Run: `.venv/bin/python -m pytest tests/widgets/test_surf_swarm_field.py -v` → 7 passed once written.

- [ ] **Step 3: Prove it bites**

Render rows through `Text.from_markup` instead of a literal `Text` → `test_a_hostile_objective_renders_as_text` red. Return `EMPTY_LINE` for `None` → `test_an_empty_field_is_not_an_unread_field` red. Restore both.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(surf): THE FIELD, who is working on what" -- maxpane_dashboard/widgets/surf/swarm_field.py maxpane_dashboard/widgets/surf/__init__.py tests/widgets/test_surf_swarm_field.py
```

---

## Task 8: QUEUE and THROUGHPUT

**Files:**
- Create: `maxpane_dashboard/widgets/surf/swarm_queue.py`, `maxpane_dashboard/widgets/surf/swarm_throughput.py`
- Modify: `maxpane_dashboard/widgets/surf/__init__.py`
- Test: `tests/widgets/test_surf_swarm_rail.py`

**Interfaces:**
- QUEUE consumes `swarm_queue_rows`, `swarm_blocked_rows`, `swarm_as_of_hhmm`; produces `SurfSwarmQueue`, `TITLE = "QUEUE"`, `NO_BLOCKED_LINE = "nothing blocked"`.
- THROUGHPUT consumes `swarm_throughput`, `swarm_score_rows`, `swarm_scores_as_of_hhmm`, `swarm_stale`; produces `SurfSwarmThroughput`, `TITLE = "THROUGHPUT"`, `STALE_WORD = "stale"`.

Both are `Static`-line panels on `pool4u_burn.py`'s shape: a title with its blank row, then fixed lines built with `parse_line`/`join_lines`.

- [ ] **Step 1: Write the failing test**

```python
# tests/widgets/test_surf_swarm_rail.py
from maxpane_dashboard.widgets.surf.swarm_queue import NO_BLOCKED_LINE, SurfSwarmQueue
from maxpane_dashboard.widgets.surf.swarm_throughput import STALE_WORD, SurfSwarmThroughput
from tests.widgets.surf_compositing import composite_lines

QUEUE_ROWS = [{"state": "completed", "count": 43}, {"state": "cancelled", "count": 11},
              {"state": "blocked", "count": 6}, {"state": "executing", "count": 2}]
BLOCKED = [{"job_id": "9c6543f5-aaaa", "template": "shape:chain",
            "reason": "node build_dapp: runtime_error", "moved_ts": 1_789_000_000.0}]
THROUGHPUT = {"accepted_per_day": 1.86, "median_delivery_s": 943,
              "revision_rate": 0.125, "window_days": 7}
SCORES = [{"agent_id": "10303", "agent_token": "2", "jobs_scored": 9,
           "mean_score": 97.8, "last_tx_hash": "0x8370" + "7e" * 30, "last_chain_id": 11155111}]


async def test_the_queue_counts_every_state_and_names_what_is_blocked():
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=BLOCKED))
    assert "completed" in text and "43" in text
    assert "runtime_error" in text


async def test_nothing_blocked_is_said_out_loud():
    text = "\n".join(await composite_lines(
        SurfSwarmQueue, (60, 14), swarm_queue_rows=QUEUE_ROWS, swarm_blocked_rows=[]))
    assert NO_BLOCKED_LINE in text


async def test_throughput_names_its_window_and_the_agents():
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_score_rows=SCORES))
    assert "7d" in text
    assert "1.86" in text
    assert "97.8" in text and "#2" in text


async def test_an_unread_throughput_is_dashes_not_zeroes():
    text = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=None, swarm_score_rows=None))
    assert "--" in text
    assert "0.0" not in text


async def test_the_stale_word_appears_only_when_told():
    fresh = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_stale=False))
    stale = "\n".join(await composite_lines(
        SurfSwarmThroughput, (60, 14), swarm_throughput=THROUGHPUT, swarm_stale=True))
    assert STALE_WORD not in fresh
    assert STALE_WORD in stale
```

- [ ] **Step 2: Run, fail, implement, run** → 5 passed.

- [ ] **Step 3: Prove it bites**

Always append `STALE_WORD` → `test_the_stale_word_appears_only_when_told` red. Render `None` throughput as `0` → `test_an_unread_throughput_is_dashes_not_zeroes` red. Restore.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(surf): the swarm body's QUEUE and THROUGHPUT panels" -- maxpane_dashboard/widgets/surf/swarm_queue.py maxpane_dashboard/widgets/surf/swarm_throughput.py maxpane_dashboard/widgets/surf/__init__.py tests/widgets/test_surf_swarm_rail.py
```

---

## Task 9: JUST SHIPPED (`SurfSwarmShipped`)

**Files:**
- Create: `maxpane_dashboard/widgets/surf/swarm_shipped.py`
- Modify: `maxpane_dashboard/widgets/surf/__init__.py`
- Test: `tests/widgets/test_surf_swarm_shipped.py`

**Interfaces:**
- Consumes: `swarm_shipped_rows`, `swarm_scores_as_of_hhmm`, `swarm_network`.
- Produces: `SurfSwarmShipped`, `TITLE = "JUST SHIPPED"`, `ADDR_COLS = 17`, `EMPTY_LINE = "nothing shipped yet"`.

A `DataTable` panel on `pool4u_stakers.py`'s shape. Columns: WHAT (kind), LABEL, CHAIN, ADDRESS / SITE, WHEN. **Every address cell is `address_text(addr, width=ADDR_COLS)`**; a tx hash uses `short_hex(tx, 17)` and gets no icon; the title carries the chain word through `_pool4.market_title_text`.

- [ ] **Step 1: Write the failing test**

```python
# tests/widgets/test_surf_swarm_shipped.py
from maxpane_dashboard.widgets.address import COPY_GLYPH
from maxpane_dashboard.widgets.surf.swarm_shipped import EMPTY_LINE, SurfSwarmShipped
from tests.widgets.surf_compositing import composite_lines

ADDR = "0x086f085ff62b33053bca76a9258380c59b74cdca"
TX = "0xc2cb3be4bf5c1bfc76cd3d6e4cdb62b0361411d758a5b0a2e13c6f83fd2d845b"
ROWS = [
    {"kind": "launch", "job_id": "5cdf977b", "label": "BazaarToken", "commit": "1794f6e6",
     "chain_id": 11155111, "address": ADDR, "tx_hash": TX, "ens_name": None,
     "cid": None, "at_ts": 1_789_000_000.0},
    {"kind": "site", "job_id": "7018907b", "label": "site-7018907b", "commit": None,
     "chain_id": None, "address": None, "tx_hash": TX,
     "ens_name": "site-7018907b.site.identitymd.eth",
     "cid": "bafybeigicvgrkurqm2mmpq7ar7jxdylycscnisdatwd2irigy7mkayprla",
     "at_ts": 1_789_000_500.0},
]


async def _shipped(size=(110, 12), **kwargs):
    kwargs.setdefault("swarm_shipped_rows", ROWS)
    lines = await composite_lines(SurfSwarmShipped, size, **kwargs)
    return "\n".join(lines)


async def test_a_deployed_contract_shows_its_address_with_the_copy_icon():
    text = await _shipped()
    assert COPY_GLYPH in text
    assert ADDR[:6].lower() in text.lower()


async def test_a_transaction_hash_gets_no_icon():
    text = await _shipped(swarm_shipped_rows=[dict(ROWS[0], address=None)])
    assert COPY_GLYPH not in text


async def test_a_site_row_names_its_ens():
    assert "site-7018907b.site" in await _shipped()


async def test_the_chain_is_named_for_a_launch_row():
    assert "SEPOLIA" in await _shipped()


async def test_an_empty_list_and_an_unread_list_differ():
    assert EMPTY_LINE in await _shipped(swarm_shipped_rows=[])
    assert "unavailable" in await _shipped(swarm_shipped_rows=None)
```

- [ ] **Step 2: Run, fail, implement, run** → 5 passed.

- [ ] **Step 3: Prove it bites**

Render the address with `str()` instead of `address_text` → `test_a_deployed_contract_shows_its_address_with_the_copy_icon` red. Give the tx hash an icon → `test_a_transaction_hash_gets_no_icon` red. Restore.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(surf): JUST SHIPPED, with a copy icon on every address" -- maxpane_dashboard/widgets/surf/swarm_shipped.py maxpane_dashboard/widgets/surf/__init__.py tests/widgets/test_surf_swarm_shipped.py
```

---

## Task 10: The screen — mode, key, body, CSS

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py` — `MODE_SWARM` (~:1546), body ids (~:1770), `BINDINGS` (~:1989), `KEY_HINTS` (~:2056), `DEFAULT_CSS` (~:2118-2565), `compose` (~:2578), `_show_mode` (~:2759), `action_toggle_swarm`, `_SCROLL_COLUMNS` (~:2882), `_do_refresh` (~:3523)
- Modify: `maxpane_dashboard/themes/minimal.tcss` (the surf block)
- Modify: `tests/screens/test_surf_screen.py` — `_SWARM_WIDGET_CLASSES` role dict (~:100-183), `SURF_WIDGET_SIGNATURES` (~:233), `_SCROLL_COLUMNS` mode set (~:7840), bindings set (~:6616)
- Modify: `tests/screens/test_surf_pool4_market_screen.py` — `_HERO_PER_MODE` (~:277), the `bodies` tuple (~:235)
- Test: `tests/screens/test_surf_swarm_screen.py`

**Interfaces:**
- Consumes: the five widgets, the `swarm_*` keys.
- Produces: `MODE_SWARM`, `SWARM_BODY_ID`, `SWARM_LEFT_ID`, `SWARM_RAIL_ID`, `action_toggle_swarm`.

- [ ] **Step 1: Write the failing test**

```python
# tests/screens/test_surf_swarm_screen.py
import pytest

from maxpane_dashboard.screens.surf import (
    LAUNCHPAD_BODY_ID, MODE_SWARM, POOL4_BODY_ID, POOL4_USER_BODY_ID,
    SWARM_BODY_ID, SurfScreen,
)
from maxpane_dashboard.widgets.surf import (
    SurfSwarmField, SurfSwarmHero, SurfSwarmQueue, SurfSwarmShipped,
    SurfSwarmThroughput,
)
from tests.screens.test_surf_screen import _frozen_payload, _screen_text, _surf_app

_SIZE = (150, 45)
_PANELS = (SurfSwarmField, SurfSwarmShipped, SurfSwarmQueue, SurfSwarmThroughput)


async def _open(pilot):
    await pilot.app.screen._do_refresh()
    await pilot.pause()
    await pilot.press("s")
    await pilot.pause()
    await pilot.pause()
    return pilot.app.screen


async def test_s_opens_the_swarm_body_and_escape_backs_out():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        assert screen._mode == MODE_SWARM
        assert screen.query_one(f"#{SWARM_BODY_ID}").display is True
        await pilot.press("escape")
        await pilot.pause()
        assert screen.query_one(f"#{SWARM_BODY_ID}").display is False


async def test_pressing_s_twice_returns_to_the_dashboard():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        await pilot.press("s")
        await pilot.pause()
        assert screen.query_one("#middle-row").display is True


async def test_s_switches_directly_from_every_other_body():
    bodies = ("#middle-row", f"#{LAUNCHPAD_BODY_ID}", f"#{POOL4_BODY_ID}",
              f"#{POOL4_USER_BODY_ID}", f"#{SWARM_BODY_ID}")
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = pilot.app.screen
        for keys, expected in ((("l",), f"#{LAUNCHPAD_BODY_ID}"),
                               (("s",), f"#{SWARM_BODY_ID}"),
                               (("4",), f"#{POOL4_USER_BODY_ID}"),
                               (("s",), f"#{SWARM_BODY_ID}"),
                               (("e",), f"#{POOL4_BODY_ID}"),
                               (("s",), f"#{SWARM_BODY_ID}")):
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            showing = [b for b in bodies if screen.query_one(b).display]
            assert showing == [expected], (keys, showing)


async def test_exactly_one_hero_shows_in_the_swarm_body():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        shown = [h for h in screen.query(".surf-hero") if h.display]
        assert len(shown) == 1
        assert isinstance(shown[0], SurfSwarmHero)


@pytest.mark.parametrize("cls", _PANELS, ids=[c.__name__ for c in _PANELS])
async def test_every_swarm_panel_reaches_the_compositor(cls):
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        body = screen.query_one(f"#{SWARM_BODY_ID}")
        found = list(body.query(cls))
        assert len(found) == 1, f"{cls.__name__}: {len(found)} instances"
        assert found[0].region.width > 0


@pytest.mark.parametrize("cls", _PANELS, ids=[c.__name__ for c in _PANELS])
async def test_every_swarm_panel_paints_a_blank_row_under_its_title(cls):
    from tests.screens.test_surf_screen import _region_text

    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        screen = await _open(pilot)
        panel = next(iter(screen.query_one(f"#{SWARM_BODY_ID}").query(cls)))
        rows = _region_text(pilot.app, panel).split("\n")

    assert rows[0].strip(), f"{cls.__name__} has no title row"
    assert not rows[1].strip(), f"{cls.__name__} has no blank row under its title"
    assert rows[2].strip(), f"{cls.__name__} has no content row"


async def test_the_key_hint_names_the_swarm():
    async with _surf_app(_frozen_payload()).run_test(size=_SIZE) as pilot:
        await pilot.pause()
        assert "s swarm" in _screen_text(pilot.app)
    assert SurfScreen.KEY_HINTS == "[dim]l launchpad · 4 pool4 · s swarm[/]"


async def test_the_bindings_gained_s_and_nothing_else():
    assert {b.key for b in SurfScreen.BINDINGS} == {"r", "l", "e", "4", "s", "escape"}
    assert hasattr(SurfScreen, "action_toggle_swarm")
```

- [ ] **Step 2: Run and watch it fail**

Run: `.venv/bin/python -m pytest tests/screens/test_surf_swarm_screen.py -v`
Expected: FAIL — `ImportError: cannot import name 'MODE_SWARM'`

- [ ] **Step 3: Wire the screen**

Add `MODE_SWARM = "swarm"` beside the other modes; the three body ids; the binding `Binding("s", "toggle_swarm", "Swarm", show=False)`; and:

```python
    def action_toggle_swarm(self) -> None:
        """``s`` -- swap the dashboard body for the swarm panels.

        Idempotent like ``4``: a second ``s`` returns to the dashboard.  ``s``
        was free on this screen (``r``/``l``/``e``/``4``/``escape``) and in the
        app (``q``/``t``/``tab``/``m``) — verified, not assumed.
        """
        if self._mode == MODE_SWARM:
            self.action_show_dashboard()
            return
        self._mode = MODE_SWARM
        self._show_mode()
```

In `compose`, beside the other heroes — `classes="surf-hero"` is what makes "exactly one hero" assertable:

```python
            yield SurfSwarmHero(classes="surf-hero")
```
and the body, after the `4` body:

```python
        with Vertical(id=SWARM_BODY_ID):
            with Horizontal(id=SWARM_LEFT_ID):
                yield SurfSwarmField()
                with Vertical(id=SWARM_RAIL_ID):
                    yield SurfSwarmQueue()
                    yield SurfSwarmThroughput()
            yield SurfSwarmShipped()
```

In `_show_mode`, two more lines, each `self._mode == <one word>`:

```python
            self.query_one(f"#{SWARM_BODY_ID}").display = self._mode == MODE_SWARM
            self.query_one(SurfSwarmHero).display = self._mode == MODE_SWARM
```

Add the `_SCROLL_COLUMNS` entry:

```python
        MODE_SWARM: (f"#{SWARM_LEFT_ID}", f"#{SWARM_RAIL_ID}"),
```

`KEY_HINTS = "[dim]l launchpad · 4 pool4 · s swarm[/]"`, one markup run. In `_do_refresh`, one `try` per panel, every kwarg a contract key spelled in full, e.g.:

```python
        try:
            self.query_one(SurfSwarmField).update_data(
                swarm_field_rows=data.get("swarm_field_rows"),
                swarm_as_of_hhmm=data.get("swarm_as_of_hhmm"),
                swarm_network=data.get("swarm_network"),
                swarm_stale=data.get("swarm_stale"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfSwarmField: %s", exc)
```

CSS: add the body, left, rail and five panel selectors to `SurfScreen.DEFAULT_CSS` **and** the surf block of `themes/minimal.tcss`, identically. Every `1fr` child gets a `min-height`; the scrolling `Vertical`s get `overflow-y: auto` and `scrollbar-gutter: stable`.

- [ ] **Step 4: Update the enumerating tests**

- `tests/screens/test_surf_screen.py`: add `_SWARM_WIDGET_CLASSES` as a fifth role dict (the union test enumerates roles), add the five widgets' entries to `SURF_WIDGET_SIGNATURES`, add `MODE_SWARM` to the mode-set literal at `test_every_mode_names_its_scrolling_columns`, and `"s"` to the bindings literal.
- `tests/screens/test_surf_pool4_market_screen.py`: add `(MODE_SWARM, ("s",), SurfSwarmHero)` to `_HERO_PER_MODE` and `SWARM_BODY_ID` to the `bodies` tuple.
- Add `_SWARM_CSS_SELECTORS` and its agreement test beside `_POOL4_USER_CSS_SELECTORS`.

- [ ] **Step 5: Run**

Run: `.venv/bin/python -m pytest tests/screens/test_surf_swarm_screen.py -v`
Then: `.venv/bin/python -m pytest tests/screens/test_surf_pool4_market_screen.py tests/test_surf_registration.py -q`

- [ ] **Step 6: Prove it bites**

Remove the `s` binding → `test_s_opens_the_swarm_body_and_escape_backs_out` red. Set the swarm hero's display to `True` in `MODE_DASHBOARD` → `test_exactly_one_hero_shows_in_every_mode` red. Drop a CSS rule from `minimal.tcss` only → the agreement test names that selector. Restore each.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(surf): s opens the swarm body" -- maxpane_dashboard/screens/surf.py maxpane_dashboard/themes/minimal.tcss tests/screens/test_surf_swarm_screen.py tests/screens/test_surf_screen.py tests/screens/test_surf_pool4_market_screen.py
```

---

## Task 11: The zero-catch triage and the title row

**Files:**
- Modify: `tests/test_surf_registration.py` — `_NUMERIC_ZERO_PROBES` / `_NON_NUMERIC_KEYS` / `_SWARM_ZERO_PROBES` (~:1903-2063)

Every new `SURF_KEYS` name must land in exactly one triage bucket, and each numeric probe needs the **exact rendered needle** its panel prints when the value is zero.

- [ ] **Step 1: Add the probes**

```python
#: What the `s` body prints when each numeric key is really zero — the needle
#: is the rendered text, so a panel that stops printing it fails here.
_SWARM_ZERO_PROBES = {
    "swarm_agents_online": "0 of",
    "swarm_working_now": "working 0",
    "swarm_accepted_today": "accepted 0",
    "swarm_jobs_in_flight": "0 in flight",
    "swarm_jobs_blocked": "0 blocked",
}
```
and the non-numeric names (`swarm_field_rows`, `swarm_queue_rows`, `swarm_blocked_rows`, `swarm_shipped_rows`, `swarm_score_rows`, `swarm_queue_depths`, `swarm_services_up`, `swarm_throughput`, `swarm_network`, `swarm_as_of_hhmm`, `swarm_scores_as_of_hhmm`, `swarm_stale`, `swarm_agents_enrolled`) into `_NON_NUMERIC_KEYS`, with `swarm_agents_enrolled` probed if it renders a zero.

- [ ] **Step 2: Run**

Run: `.venv/bin/python -m pytest tests/test_surf_registration.py -q`
Expected: `test_every_surf_key_is_triaged_for_the_zero_catch`, `test_no_surf_key_is_still_waiting_for_a_consumer` and the title-row test all pass. `SOURCES` is unchanged, so the worst-case title row is untouched — confirm that test did not move.

- [ ] **Step 3: Prove it bites**

Remove one `swarm_*` key from its bucket → the triage test names it. Restore.

- [ ] **Step 4: Commit**

```bash
git commit -m "test(surf): triage every swarm key for the zero catch" -- tests/test_surf_registration.py
```

---

## Task 12: The pins and the layout sweeps

**Files:**
- Modify: `maxpane_dashboard/screens/surf.py` (add both pin constants with their `#:` blocks)
- Create: `tests/screens/test_surf_swarm_layout.py`

**Interfaces:**
- Produces: `SURF_SWARM_FULL_LAYOUT_COLUMNS`, `SURF_SWARM_FULL_LAYOUT_ROWS`.

- [ ] **Step 1: Measure, do not derive**

Write a scratch script that renders the body over `range(70, 160)` columns at 50 rows, and over `range(24, 60)` rows at the column pin, recording for each: whether any panel shows `‹`, whether any line is CSS-clipped, and each `DataTable`'s `max_scroll_x`. The pin is the **smallest width with no marker and no clipping**, and the smallest height with no `‹ taller`. Start the sweep well below the expected pin, never at it.

- [ ] **Step 2: Write the constants with their reasoning**

```python
#: The `s` body's own width.  Measured in situ over 70-160 columns with the
#: committed swarm captures, never derived: it is not a rewrite of
#: SURF_FULL_LAYOUT_COLUMNS (143), of SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS
#: (138), of SURF_POOL4_FULL_LAYOUT_COLUMNS (99), of
#: SURF_POOL4_USER_FULL_LAYOUT_COLUMNS (119) or of __main__.FULL_LAYOUT_COLUMNS
#: -- a fifth body gets a fifth constant.
#: Binding panel: <the one measured>, at <its need> columns.
#: Every displayed address carries its copy icon inside this number
#: (docs/address_copy_PRD.md §5); no pin moved for the icon.
SURF_SWARM_FULL_LAYOUT_COLUMNS = <measured>
```
and the same shape for `..._ROWS`, naming the panel whose floor binds it.

- [ ] **Step 3: Write the layout module**

Copy `tests/screens/test_surf_pool4_market_layout.py`'s shape: independent literals `MEASURED_SWARM_COLUMNS` / `MEASURED_SWARM_ROWS` (never aliased to the constants), a `_render(payload, size)` helper, `_SWARM_CLASSES`, and:

```python
_WIDTH_SWEEP = [("capture", w) for w in range(70, 160)]

@pytest.mark.parametrize("payload_name,width", _WIDTH_SWEEP)
async def test_the_swarm_body_is_whole_from_its_pinned_width(payload_name, width):
    r = await _render(_PAYLOADS[payload_name](), (width, 50))
    if width >= SURF_SWARM_FULL_LAYOUT_COLUMNS:
        assert not r["marked"], f"a panel asks to be widened at {width}"
        assert not r["clipped"], f"a line is clipped at {width}"
        assert r["shipped_hidden_cols"] == 0
    else:
        assert r["marked"], f"nothing advertises the loss at {width}"
```
plus the height sweep, `test_the_swarm_binding_panel_is_the_one_the_block_names`, `test_the_swarm_body_fits_inside_the_documented_app_width`, `test_no_height_loses_a_row_of_this_body_in_silence`, and the hint pair (`KEY_HINT_PHRASE = "l launchpad · 4 pool4 · s swarm"`, fits at 143, still fits below).

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/screens/test_surf_swarm_layout.py -q`

- [ ] **Step 5: Prove both directions**

Set each pin one lower → the "whole from its pinned width/height" case reddens. Set it one higher → the "advertises the loss" case reddens. Restore.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(surf): pin the swarm body's width and height in situ" -- maxpane_dashboard/screens/surf.py tests/screens/test_surf_swarm_layout.py
```

---

## Task 13: The address sweep

**Files:**
- Modify: `tests/address_sweep/builders.py` (surf's `SweepCase`: `views`, `pins`, `SURF_SEEDED`, and the payload)
- Modify: `tests/screens/test_address_icons_everywhere.py` (~:319-334, the ordered pin list)

`views` and `pins` are zipped positionally, so the fifth view needs the fifth pin in the same position.

- [ ] **Step 1: Extend the case**

```python
        views=((), ("l",), ("e",), ("4",), ("s",)),
        pins=(
            (SURF_FULL_LAYOUT_COLUMNS, None),
            (SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, SURF_LAUNCHPAD_FULL_LAYOUT_ROWS),
            (SURF_POOL4_FULL_LAYOUT_COLUMNS, SURF_POOL4_FULL_LAYOUT_ROWS),
            (SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, SURF_POOL4_USER_FULL_LAYOUT_ROWS),
            (SURF_SWARM_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_ROWS),
        ),
```

Seed a launch contract address into `_surf_payload`'s `swarm_shipped_rows`, and hand-list it:

```python
    _SWARM_CONTRACT,                                # s: JUST SHIPPED launch artifact, shortened
```

- [ ] **Step 2: Update the ordered pin assertion** in `test_every_case_is_swept_at_its_pins` with the fifth entry.

- [ ] **Step 3: Run**

Run: `.venv/bin/python -m pytest tests/screens/test_address_icons_everywhere.py tests/test_address_sweep_registry.py tests/test_address_rule.py -q`
Expected: all pass, including the new view at its pin.

- [ ] **Step 4: Prove it bites**

Render the shipped address without its icon → `test_every_rendered_address_carries_an_icon_that_copies_it[surf]` reddens. Restore.

- [ ] **Step 5: Commit**

```bash
git commit -m "test(surf): the swarm body joins the address sweep" -- tests/address_sweep/builders.py tests/screens/test_address_icons_everywhere.py
```

---

## Task 14: Docs and the full suite

**Files:**
- Modify: `CLAUDE.md` (the surf row of the dashboard table's prose, the keys paragraph, a short section on the swarm body), `README.md` (the keys line, the width table, a section for the `s` view), `docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md` (status line)

- [ ] **Step 1: Write the docs**

CLAUDE.md gains a section in the voice of the existing body sections: what `s` shows, that it reads one keyless third-party host, the two tiers and why the list is gated on `/health` counters, that no ninth degraded group was added and why, and that the explorer's inference headline is deliberately absent. Name the constants; do not repeat their numbers.

README gains the `s` key in the keys line, a section describing the body, and its row in the width table.

The spec's status line becomes `built <date>`, naming the commit range.

- [ ] **Step 2: Run the doc-pinning tests**

Run: `.venv/bin/python -m pytest tests/test_surf_registration.py tests/test_curator_registration.py -q`
Expected: the README width-table test and the "docs describe no key the screen does not bind" test both pass.

- [ ] **Step 3: Run the full suite, in chunks**

```bash
for part in tests/analytics tests/data tests/screens tests/widgets; do .venv/bin/python -m pytest -q -p no:cacheprovider $part; echo "exit=$? ($part)"; done
.venv/bin/python -m pytest -q -p no:cacheprovider $(ls tests/*.py | grep -v conftest.py | grep -v __init__.py)
```
A single-process full run gets killed by macOS for memory; run it per directory. Take the exit code from pytest itself, never from a pipe's tail.

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: the swarm body, its two clocks and its one source" -- CLAUDE.md README.md docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md
```

---

## Self-review

**Spec coverage**

| Spec section | Task |
|---|---|
| §2 modules | 1, 2, 6-9 |
| §3 tiers, slots, change detector, spawned reads, 404 policy | 3, 5 |
| §4 payload keys and row shapes | 4 |
| §5 body, hero, four panels, chain word, pins, hint | 10, 12 |
| §6 honesty: None-not-zero, last-good, hostile text, one source, no headline, injected clock | 1 (fold), 6-9 (panels), 5 (markers, stale) |
| §7 testing: fixtures, no network, pure fold, composited panels, body, sweep, degradation, mutations | 0, 1, 2, 5-13 |
| §8 out of scope | nothing implements it; no task touches IPFS, the registry, or writes |

**Placeholder scan:** the only deliberate blanks are Task 12's `<measured>` pin values and its binding-panel name, which cannot be known before the sweep runs; Task 12 Step 1 is the measurement that fills them.

**Type consistency:** the frozen-names table is the single source for every signature; `field_rows`/`queue_rows`/`blocked_rows`/`score_rows`/`shipped_rows`/`throughput` keep one spelling across the fold (Task 1), the models (Task 4), the manager (Task 5) and the widgets (Tasks 6-9). `swarm_*` payload keys appear identically in `SWARM_KEYS`, `_swarm_keys`, `SURF_WIDGET_SIGNATURES` and every `update_data`.
