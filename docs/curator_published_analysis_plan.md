# THE LIST — published 0.2.0 analysis · implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** THE LIST loads its linked-wallet analysis from the published, immutable
`clustermap` dataset instead of computing it from a partial local sweep; the superseded
list exports are archived and rewritten so `e` exports the new data.

**Architecture:** Two keyless `GET`s supply cluster membership and reasons. A hand-built
`sybilkit.DetectResult` carries them into the library's own pure `segments()` /
`clean_list()`, run over the local `Dataset` — so everything downstream of `detect()` in
`build_analysis` is reused rather than reimplemented. The tier, slot, detachment,
freshness marker and degradation rules do not change; only the producer does.

**Tech Stack:** Python 3.11 · `httpx` (already a dependency) · `sybilkit>=0.1.0`
(unchanged — 0.2.0 is not on PyPI) · Textual 8.1.1 · pytest

**Spec:** `docs/curator_published_analysis_PRD.md`

## Global Constraints

Every task's requirements implicitly include these.

- **Strictly read-only.** No signer, transactor, nonce manager, keystore or calldata for
  a state change. Nothing in this plan needs one.
- **Keyless.** `https://clustermap.vibingco.de/api/v1` takes no key. No key, token or
  secret may be introduced anywhere.
- **No test may touch the network.** Assert it structurally: inject a transport that
  raises on use. Every external payload is a committed fixture under `tests/fixtures/`.
- **Read values live; never hardcode a documented one.** Every count, hash and version id
  in the spec is read from the payload at runtime. The spec's tables are evidence, not
  constants to type into code.
- **A failed read is `None`, never `0` or `[]`.**
- **A dead source degrades to an explicit unavailable state** — last-good behind
  `as of HH:MM`, never a stale number presented as live, never a blank panel.
- **`data/curator_clusters.py` stays the only maxpane module importing `sybilkit`.**
  `rg -n "import sybilkit|from sybilkit" maxpane_dashboard/` must return exactly that one
  file.
- **`analytics/curator_signals.py` is never opened.** It stays byte-identical.
- **`pattern_language()` re-checks every third-party string** — reason, label, detail —
  including strings read back from a persisted payload.
- **Escape every third-party string** before markup or a `DataTable`
  (`widgets/markup_safety.safe_markup`); a widget rendering third-party text through
  `Static` hands it a pre-built `rich.text.Text`.
- **Widgets stay pure** — no `data/` import in anything new; `analytics/` only.
- **Inject the clock.** No new module calls `time.time()` internally.
- **Layout obeys `.claude/skills/terminal-layout/SKILL.md`** — `cell_len`, not `len()`.
- **Never `git checkout --` a file.** The tree holds uncommitted user work, including
  ~300 untracked curator fixtures. Stage only files you created or edited.
- **Do not merge or push.** Commit only.

## Symbol ownership

`data/curator_clusters.py` is edited by five tasks. Ownership follows **symbols**, not
files — a file-level lock would serialise the whole plan.

| Symbol | Owner |
|---|---|
| `clusters_from_published`, `detect_result_from_published` | T3 |
| `build_analysis_from_published`, `_review_segment_row`, `_review_suffix` | T4 |
| `bands_by_address`, `grade_of`, `you_linkage`, `merge_leaderboard_grade` | T5 |
| `slot_payload`, `AnalysisResult.published` | T7 |
| `analysis_keys` (`analysis_version` line only) | T8 |
| `fetch_enrichment`, `candidate_targets`, `EnrichmentState`, `TX_BUDGET`, `FUNDING_BUDGET`, the `sybilkit.sources` imports | T11 |

`data/curator_manager.py`: T8 owns the `analysis_version` stamp, T10 owns
`_pool_analysis`, T11 owns `_analysis_session`. No other task edits it.

## Sequencing

```
T1 ──┬── T2 ──────────────┐
     └── T3 ── T4 ──┬── T5 ──┬── T6 ┐
                    └── T7 ──┴── T8 ├── T10 ── T11 ── T12
                         T9 ────────┘
```

T2/T3 may run in parallel once T1 lands. T5/T7 in parallel after T4. T6/T8/T9 in parallel
after that. T10 needs T2, T4, T7 and T9. T11 must follow T10 (it deletes what T10 stops
calling). T12 last.

---

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `maxpane_dashboard/data/curator_published.py` | The three fetches, size caps, top-level shape validation. No `sybilkit`, no `pattern_language`, no clock. |
| `maxpane_dashboard/data/curator_archive.py` | Move superseded exports aside, write the new complete lists, carry ENS across. Injected root and clock. |
| `tests/data/test_curator_published.py` | Fetch layer, caps, degradation. |
| `tests/data/test_curator_archive.py` | Move-not-delete, manifest, re-rank, idempotence. |
| `tests/data/test_curator_published_analysis.py` | Reconstruction and `build_analysis_from_published`. |
| `tests/fixtures/curator/published/*.json` | Four fixtures (T1). |
| `scripts/capture_published_analysis.py` | One-shot fixture trimmer. Imported by nothing. |

**Modified**

`data/curator_clusters.py` · `data/curator_models.py` · `data/curator_manager.py` ·
`data/curator_list_filters.py` · `widgets/curator/leaderboard.py` ·
`widgets/curator/{segments,operators,cleaned_list,lists}.py` · `screens/curator.py` ·
`CLAUDE.md` · `README.md` · their test files.

---

### Task 1: The fixtures

**Files:**
- Create: `scripts/capture_published_analysis.py`
- Create: `tests/fixtures/curator/published/versions.json`
- Create: `tests/fixtures/curator/published/overview_trimmed.json`
- Create: `tests/fixtures/curator/published/export_trimmed.json`
- Create: `tests/fixtures/curator/published/export_hostile.json`

**Interfaces:**
- Produces: four fixture paths every later task reads. `export_trimmed.json` and
  `overview_trimmed.json` are a **matched pair** — the trimmed export's `cluster_id`
  values are exactly the trimmed overview's cluster ids, and each kept cluster's `size`
  is rewritten to its kept-member count so the pair is internally consistent. Later
  tasks assert against that pair, so it must reconcile the way the live service does.

- [ ] **Step 1: Write the trimmer**

`scripts/capture_published_analysis.py`. It fetches live and writes fixtures; it is run
by a human once and imported by nothing.

```python
"""One-shot: trim the live published analysis into committed test fixtures.

Run from the repo root with the venv interpreter:

    .venv/bin/python scripts/capture_published_analysis.py

The live export is 8.3 MB over 19,522 wallets, which is not a fixture.  This keeps
every cluster that carries a distinguishing property and rewrites the kept clusters'
sizes so the trimmed overview and the trimmed export reconcile exactly as the live
pair does -- a fixture whose halves disagree tests the disagreement, not the code.
"""
from __future__ import annotations

import json
import pathlib
import urllib.request

BASE = "https://clustermap.vibingco.de/api/v1"
OUT = pathlib.Path("tests/fixtures/curator/published")
MEMBERS_PER_CLUSTER = 6
CLEAN_KEPT = 40


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/{path}", timeout=180) as resp:
        return json.load(resp)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    versions = get("versions")
    version_id = versions["published_version"]
    overview = get(f"overview?version={version_id}")
    export = get(
        "list/export?q=&link=all&evidence=all&preset=none&version=" + version_id
    )
    rows = export["rows"]

    by_cluster: dict[int, list[dict]] = {}
    for row in rows:
        if row["cluster_id"] is not None:
            by_cluster.setdefault(row["cluster_id"], []).append(row)

    review_ids = {
        row["cluster_id"] for row in rows if row["status"] == "review"
    }
    flagged_ids = {c["id"] for c in overview["clusters"] if c["review_flag"]}
    low_ids = {c["id"] for c in overview["clusters"] if c["band"] == "low"}
    biggest = max(overview["clusters"], key=lambda c: c["size"])["id"]
    keep_ids = (
        set(sorted(review_ids)[:4]) | set(sorted(flagged_ids)[:2])
        | set(sorted(low_ids)[:2]) | {biggest}
    )

    kept_rows: list[dict] = []
    for cid in sorted(keep_ids):
        members = by_cluster[cid]
        # Review members first so a trimmed cluster never loses the property it
        # was kept for.
        members.sort(key=lambda r: (r["status"] != "review", r["rank"]))
        kept_rows.extend(members[:MEMBERS_PER_CLUSTER])

    clean = [r for r in rows if r["status"] == "clean"]
    # Keep the rows whose 0.1.1 `link_conf` CONTRADICTS their 0.2.0 `status`:
    # they are the whole point of the trap test.
    contradicting = [r for r in clean if r["link_conf"] in ("high", "low")]
    kept_rows.extend(contradicting[:CLEAN_KEPT // 2])
    kept_rows.extend(
        [r for r in clean if r["link_conf"] == "clean"][: CLEAN_KEPT // 2]
    )

    sizes = {cid: 0 for cid in keep_ids}
    for row in kept_rows:
        if row["cluster_id"] is not None:
            sizes[row["cluster_id"]] += 1

    kept_rows.sort(key=lambda r: r["rank"])
    for rank, row in enumerate(kept_rows, start=1):
        row["rank"] = rank

    clusters = []
    for cluster in overview["clusters"]:
        if cluster["id"] not in keep_ids:
            continue
        cluster = dict(cluster)
        cluster["size"] = sizes[cluster["id"]]
        clusters.append(cluster)

    trimmed_overview = dict(overview)
    trimmed_overview["clusters"] = clusters
    trimmed_overview["totals"] = dict(overview["totals"])
    (OUT / "versions.json").write_text(json.dumps(versions, indent=1))
    (OUT / "overview_trimmed.json").write_text(
        json.dumps(trimmed_overview, indent=1)
    )
    (OUT / "export_trimmed.json").write_text(
        json.dumps({**export, "rows": kept_rows, "count": len(kept_rows)}, indent=1)
    )
    print(
        f"clusters={len(clusters)} rows={len(kept_rows)} "
        f"review={sum(1 for r in kept_rows if r['status'] == 'review')} "
        f"contradicting={sum(1 for r in kept_rows if r['status'] == 'clean' and r['link_conf'] in ('high', 'low'))}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
.venv/bin/python scripts/capture_published_analysis.py
```

Expected: a line naming a cluster count between 5 and 9, ~70–90 rows, a non-zero
`review=` and a non-zero `contradicting=`. **If `contradicting=0`, stop** — the trap
test in T3 cannot bite and the trimmer needs fixing, not the fixture accepting.

- [ ] **Step 3: Hand-write the hostile fixture**

`tests/fixtures/curator/published/export_hostile.json` — same envelope, six rows,
each carrying exactly one defect so a failure names its cause:

```json
{
  "source": "CuratorWhitelist",
  "contract": "0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91",
  "snapshot_block": 25807057,
  "count": 6,
  "rows": [
    {"rank": 1, "address": "0x1111111111111111111111111111111111111111",
     "points": 100, "credit_eth": 1.0, "tx_count": 1, "flagged": false,
     "name": "[/x]", "weight_eth": 1.0, "first_hour": 0, "first_index": 1,
     "link_conf": "clean", "cluster_id": 1, "status": "flagged",
     "risk": "critical", "evidence_band": "high",
     "member_families": ["amount"], "member_family_count": 1,
     "under_review": false},
    {"rank": 2, "address": "0xNOTHEXNOTHEXNOTHEXNOTHEXNOTHEXNOTHEXNOTH",
     "points": 90, "credit_eth": 1.0, "tx_count": 1, "flagged": false,
     "name": null, "weight_eth": 1.0, "first_hour": 0, "first_index": 2,
     "link_conf": "clean", "cluster_id": null, "status": "clean",
     "risk": "independent", "evidence_band": "none",
     "member_families": [], "member_family_count": 0, "under_review": false},
    {"rank": 3, "address": "0x3333333333333333333333333333333333333333",
     "points": "not-a-number", "credit_eth": 1.0, "tx_count": 1,
     "flagged": false, "name": null, "weight_eth": 1.0, "first_hour": 0,
     "first_index": 3, "link_conf": "clean", "cluster_id": null,
     "status": "clean", "risk": "independent", "evidence_band": "none",
     "member_families": [], "member_family_count": 0, "under_review": false},
    {"rank": 4, "address": "0x4444444444444444444444444444444444444444",
     "points": 80, "credit_eth": 1.0, "tx_count": 1, "flagged": false,
     "name": null, "weight_eth": 1.0, "first_hour": 0, "first_index": 4,
     "link_conf": "high", "cluster_id": null, "status": "clean",
     "risk": "independent", "evidence_band": "none",
     "member_families": [], "member_family_count": 0, "under_review": false},
    {"rank": 5, "address": "0x5555555555555555555555555555555555555555",
     "points": 70, "credit_eth": 1.0, "tx_count": 1, "flagged": false,
     "name": null, "weight_eth": 1.0, "first_hour": 0, "first_index": 5,
     "link_conf": "clean", "cluster_id": 1, "status": "review",
     "risk": "review", "evidence_band": "low",
     "member_families": ["amount"], "member_family_count": 1,
     "under_review": true},
    {"rank": 6, "address": "0x6666666666666666666666666666666666666666",
     "points": 60, "credit_eth": 1.0, "tx_count": 1, "flagged": false,
     "name": null, "weight_eth": 1.0, "first_hour": 0, "first_index": 6,
     "link_conf": "clean", "cluster_id": 1, "status": "flagged",
     "risk": "critical", "evidence_band": "high",
     "member_families": ["amount"], "member_family_count": 1,
     "under_review": false}
  ]
}
```

Row 1 is a markup bomb in `name`; row 2 a malformed address; row 3 a non-numeric
`points`; row 4 the `link_conf`-contradicts-`status` trap; row 5 a review member; row 6
its flagged neighbour in the same cluster.

The matching hostile overview lives inline in the tests that need it (one cluster, id 1,
with a reason whose `text` contains a forbidden word) — it is three lines and putting it
in a file would separate the bomb from the assertion about it.

- [ ] **Step 4: Verify the fixtures load and reconcile**

```bash
.venv/bin/python - <<'PY'
import json, pathlib, collections
d = pathlib.Path("tests/fixtures/curator/published")
ov = json.loads((d / "overview_trimmed.json").read_text())
ex = json.loads((d / "export_trimmed.json").read_text())
mem = collections.Counter(r["cluster_id"] for r in ex["rows"] if r["cluster_id"] is not None)
assert {c["id"] for c in ov["clusters"]} == set(mem), "cluster ids disagree"
assert all(mem[c["id"]] == c["size"] for c in ov["clusters"]), "sizes disagree"
assert [r["rank"] for r in ex["rows"]] == list(range(1, len(ex["rows"]) + 1))
print("fixtures reconcile:", len(ov["clusters"]), "clusters,", len(ex["rows"]), "rows")
PY
```

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_published_analysis.py tests/fixtures/curator/published/
git commit -m "test(curator): fixtures for the published 0.2.0 analysis"
```

---

### Task 2: `data/curator_published.py` — the fetch layer

**Files:**
- Create: `maxpane_dashboard/data/curator_published.py`
- Test: `tests/data/test_curator_published.py`

**Interfaces:**
- Consumes: T1's fixtures.
- Produces:
  - `PUBLISHED_BASE_URL: str`
  - `@dataclass(frozen=True) PublishedVersion(version_id, content_hash, detector_version, rule_set, rules_sha256, snapshot_block, cluster_count, status_counts: dict[str, int])`
  - `@dataclass(frozen=True) PublishedAnalysis(version: PublishedVersion, clusters: tuple[dict, ...], totals: dict, rows: tuple[dict, ...])`
  - `async def fetch_published_version(*, client=None, transport=None, base_url=PUBLISHED_BASE_URL) -> PublishedVersion | None`
  - `async def fetch_published_analysis(version, *, client=None, transport=None, base_url=PUBLISHED_BASE_URL) -> PublishedAnalysis | None`
  - `def version_label(version: PublishedVersion) -> str` — `"sybilkit 0.2.0 · 2026-08-25"`

With neither `client` nor `transport`, both fetches return `None` without opening a
socket. That is the structural no-network guarantee, not a convention.

- [ ] **Step 1: Write the failing tests**

`tests/data/test_curator_published.py`:

```python
import json
import pathlib

import httpx
import pytest

from maxpane_dashboard.data import curator_published as pub

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures/curator/published"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _transport(handler):
    return httpx.MockTransport(handler)


def _ok(payloads):
    def handler(request):
        for fragment, body in payloads.items():
            if fragment in str(request.url):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"detail": "no"})
    return _transport(handler)


class _ExplodingTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        raise AssertionError(f"a test opened the network: {request.url}")


@pytest.mark.asyncio
async def test_with_no_client_and_no_transport_nothing_is_fetched():
    assert await pub.fetch_published_version() is None


@pytest.mark.asyncio
async def test_the_version_is_the_one_the_service_calls_published():
    transport = _ok({"/versions": _load("versions.json")})
    version = await pub.fetch_published_version(transport=transport)
    assert version.version_id == _load("versions.json")["published_version"]
    assert version.content_hash
    assert version.status_counts["clean"] > 0


@pytest.mark.asyncio
async def test_a_versions_body_with_no_matching_entry_is_none():
    body = dict(_load("versions.json"))
    body["published_version"] = "no-such-version"
    assert await pub.fetch_published_version(transport=_ok({"/versions": body})) is None


@pytest.mark.asyncio
async def test_a_failed_overview_returns_none_rather_than_half_an_analysis():
    def handler(request):
        if "/overview" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200, json=_load("export_trimmed.json"))
    version = pub.PublishedVersion(
        version_id="v", content_hash="h", detector_version="0.2.0",
        rule_set="v2h", rules_sha256="deadbeef", snapshot_block=1,
        cluster_count=1, status_counts={"clean": 1},
    )
    got = await pub.fetch_published_analysis(version, transport=_transport(handler))
    assert got is None


@pytest.mark.asyncio
async def test_an_html_body_is_not_mistaken_for_json():
    # Unknown API paths on this host return the SPA's index with HTTP 200.
    def handler(request):
        return httpx.Response(200, text="<!doctype html>", headers={"content-type": "text/html"})
    assert await pub.fetch_published_version(transport=_transport(handler)) is None


@pytest.mark.asyncio
async def test_an_oversized_body_is_refused_before_it_is_parsed(monkeypatch):
    monkeypatch.setattr(pub, "MAX_VERSIONS_BYTES", 8)
    transport = _ok({"/versions": _load("versions.json")})
    assert await pub.fetch_published_version(transport=transport) is None


@pytest.mark.asyncio
async def test_the_analysis_carries_every_cluster_and_row():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    transport = _ok({"/overview": ov, "/list/export": ex})
    version = await pub.fetch_published_version(
        transport=_ok({"/versions": _load("versions.json")})
    )
    got = await pub.fetch_published_analysis(version, transport=transport)
    assert len(got.clusters) == len(ov["clusters"])
    assert len(got.rows) == len(ex["rows"])
    assert got.totals["population"] == ov["totals"]["population"]


@pytest.mark.asyncio
async def test_the_version_travels_in_every_request_query():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if "/overview" in str(request.url):
            return httpx.Response(200, json=_load("overview_trimmed.json"))
        return httpx.Response(200, json=_load("export_trimmed.json"))

    version = pub.PublishedVersion(
        version_id="2026-08-25-sybilkit-0.2.0", content_hash="h",
        detector_version="0.2.0", rule_set="v2h", rules_sha256="d",
        snapshot_block=1, cluster_count=1, status_counts={},
    )
    await pub.fetch_published_analysis(version, transport=_transport(handler))
    assert seen and all("2026-08-25-sybilkit-0.2.0" in url for url in seen)


@pytest.mark.asyncio
async def test_nothing_in_this_module_opens_a_socket():
    exploding = _ExplodingTransport()
    assert await pub.fetch_published_version(transport=exploding) is None
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/bin/python -m pytest tests/data/test_curator_published.py -q
```

Expected: collection error, `No module named 'maxpane_dashboard.data.curator_published'`.

- [ ] **Step 3: Write the module**

Key decisions the implementer must not vary:

- **Size cap before parse.** Read the response body as bytes, check `len(body)` against
  the per-endpoint cap, then `json.loads`. `resp.json()` parses first, which is what the
  cap exists to prevent.
- **Content type is checked.** This host answers unknown paths with the SPA's HTML at
  HTTP 200. A body that is not `application/json` is a failure, not a payload.
- **`None` on every failure**, logged at `warning` with the URL and the reason. Never a
  partial `PublishedAnalysis`: both bodies land or the call returns `None`.
- **No clock, no retries of its own** — the tier's backoff is the retry policy.

```python
"""THE LIST's published analysis, read from clustermap's keyless HTTP API.

One version check per tick, and the two bulk reads only when the publisher has
shipped a new analysis.  A published version is immutable and content-addressed,
so a tick that finds the same ``content_hash`` has nothing to download.

This module imports no ``sybilkit`` and knows no pattern language: it fetches and
shape-checks, and ``data/curator_clusters.py`` -- the translation boundary -- is
what turns a payload into something a screen may see.

Socket discipline: with neither ``client`` nor ``transport`` every entry point
returns ``None`` without constructing a client, so a test that forgets to inject
cannot reach the network by accident.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: The published analysis service.  Keyless, read-only, GET only.
PUBLISHED_BASE_URL = "https://clustermap.vibingco.de/api/v1"

#: Bodies are capped BEFORE they are parsed.  The live export measures 8.3 MB
#: over 19,522 wallets, so 64 MiB is headroom for a larger population rather
#: than a limit anything real approaches; a body past the cap is a failure, not
#: a truncation.
MAX_VERSIONS_BYTES = 1 << 20
MAX_OVERVIEW_BYTES = 16 << 20
MAX_EXPORT_BYTES = 64 << 20

_TIMEOUT = 60.0
_HEADERS = {"Accept": "application/json", "User-Agent": "maxpane"}


@dataclass(frozen=True)
class PublishedVersion:
    version_id: str
    content_hash: str
    detector_version: str | None
    rule_set: str | None
    rules_sha256: str | None
    snapshot_block: int | None
    cluster_count: int | None
    status_counts: dict[str, int]


@dataclass(frozen=True)
class PublishedAnalysis:
    version: PublishedVersion
    clusters: tuple[dict, ...]
    totals: dict
    rows: tuple[dict, ...]


def version_label(version: PublishedVersion | None) -> str | None:
    """``"sybilkit 0.2.0 · 2026-08-25"`` -- what the panels render."""
    if version is None:
        return None
    detector = version.detector_version
    stamp = version.version_id.split("-sybilkit-")[0] if version.version_id else None
    parts = [p for p in (f"sybilkit {detector}" if detector else None, stamp) if p]
    return " · ".join(parts) or None
```

…plus a private `_get_json(client, url, params, cap)` doing cap-then-parse, and the two
public fetches. `_session(client, transport)` yields either the borrowed client or a
short-lived `httpx.AsyncClient(transport=transport, timeout=_TIMEOUT)`, and yields
nothing at all when both are `None`.

- [ ] **Step 4: Run the tests**

```bash
.venv/bin/python -m pytest tests/data/test_curator_published.py -q
```
Expected: all pass.

- [ ] **Step 5: Prove two of them bite**

Mutate, watch the *named* test go red, restore:

1. Delete the content-type check → `test_an_html_body_is_not_mistaken_for_json` fails.
2. Move the size check to after `json.loads` →
   `test_an_oversized_body_is_refused_before_it_is_parsed` still passes, which is the
   point: change the assertion to also patch a body that would raise on parse, or make
   the cap check read `resp.content` length. **Report which test actually reddened** —
   a mutation that reddens a different test than the one you named is a finding.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/curator_published.py tests/data/test_curator_published.py
git commit -m "feat(curator): read the published analysis, capped and shape-checked"
```

---

### Task 3: Reconstruct `sybilkit` objects from published membership

**Files:**
- Modify: `maxpane_dashboard/data/curator_clusters.py`
- Test: `tests/data/test_curator_published_analysis.py`

**Interfaces:**
- Consumes: T1 fixtures; T2's `PublishedAnalysis` (import for typing only — do **not**
  make `curator_clusters` depend on `curator_published` at runtime; take the three
  pieces as plain arguments so the adapter stays testable from raw dicts).
- Produces:
  - `def clusters_from_published(clusters, rows) -> list[Cluster]`
  - `def detect_result_from_published(clusters, rows, totals) -> DetectResult`
  - `def published_band(cluster: Mapping) -> str` — `"high"`/`"low"`
  - `def review_members_of(rows) -> dict[int, dict[str, list[str]]]` — cluster id →
    `{address: families}` for `status == "review"`

**This code has been run.** The block below is from a spike executed against the real
cache and the live payload; it produced the published clean list exactly. Transcribe its
shape rather than reinventing it.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_reconstructed_clusters_match_the_overviews_own_sizes():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    clusters = cc.clusters_from_published(ov["clusters"], ex["rows"])
    by_id = {c.cluster_id: c for c in clusters}
    for declared in ov["clusters"]:
        assert len(by_id[declared["id"]].members) == declared["size"]


def test_members_are_lowercased_on_both_sides():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    rows = [dict(r, address=r["address"].upper()) for r in ex["rows"]]
    clusters = cc.clusters_from_published(ov["clusters"], rows)
    assert all(m == m.lower() for c in clusters for m in c.members)


def test_a_row_whose_address_is_malformed_is_dropped_not_rendered():
    ov = {"clusters": [_hostile_cluster()]}
    rows = _load("export_hostile.json")["rows"]
    clusters = cc.clusters_from_published(ov["clusters"], rows)
    joined = [m for c in clusters for m in c.members]
    assert not any("nothex" in m for m in joined)


def test_the_band_is_the_publishers_word_when_it_is_one_we_know():
    assert cc.published_band({"band": "low", "families": ["amount", "cadence", "gas"]}) == "low"


def test_an_unknown_band_word_falls_back_to_our_own_family_grading():
    # The endpoint is third-party: "critical" must never reach a screen.
    assert cc.published_band({"band": "critical", "families": ["amount", "funding"]}) == "high"
    assert cc.published_band({"band": None, "families": ["amount", "cadence"]}) == "low"


def test_review_members_are_indexed_by_cluster_with_their_own_families():
    ex = _load("export_hostile.json")
    got = cc.review_members_of(ex["rows"])
    assert got[1] == {"0x5555555555555555555555555555555555555555": ["amount"]}


def test_a_hand_built_result_answers_membership_like_a_detected_one():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    res = cc.detect_result_from_published(ov["clusters"], ex["rows"], ov["totals"])
    member = next(r["address"] for r in ex["rows"] if r["cluster_id"] is not None)
    assert res.wallet(member).in_cluster is True
    clean = next(r["address"] for r in ex["rows"] if r["status"] == "clean")
    assert res.wallet(clean).in_cluster is False


def test_a_boolean_is_not_read_as_a_number():
    # json.loads turns `true` into a Python bool, which IS an int.
    assert cc.published_band({"band": "low", "families": []}) == "low"
    clusters = cc.clusters_from_published(
        [{"id": 1, "points": True, "confidence": 0.9, "points_share": 0.1,
          "span_blocks": None, "families": [], "reasons": [], "band": "low"}], []
    )
    assert clusters[0].points == 0


def test_a_non_finite_confidence_is_refused():
    clusters = cc.clusters_from_published(
        [{"id": 1, "points": 1, "confidence": float("inf"), "points_share": 0.1,
          "span_blocks": None, "families": [], "reasons": [], "band": "low"}], []
    )
    assert clusters[0].confidence == 0.0


def test_clusters_are_ordered_widest_share_first():
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    res = cc.detect_result_from_published(ov["clusters"], ex["rows"], ov["totals"])
    shares = [c.points_share for c in res.clusters]
    assert shares == sorted(shares, reverse=True)
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/bin/python -m pytest tests/data/test_curator_published_analysis.py -q
```
Expected: `AttributeError: module ... has no attribute 'clusters_from_published'`.

- [ ] **Step 3: Implement**

Add to `curator_clusters.py`, importing `Cluster` and `Reason` alongside the existing
`DetectResult` import (all three are top-level `sybilkit` exports since 0.1.0):

**First**, `curator_clusters.py` has no numeric coercers of its own — `_opt_int` lives
in `curator_manager.py` and importing it would point the adapter at the manager. Add
both, module-private, above `_valid_address`:

```python
def _opt_int(value: Any) -> int | None:
    """An ``int`` or ``None``.  ``bool`` is not an int here: ``True`` in a JSON
    payload is a type error, not the number one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _opt_float(value: Any) -> float | None:
    """A finite ``float`` or ``None``.  ``nan``/``inf`` survive ``json.loads``
    and would poison every share and confidence they touch."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None
```

`import math` joins the module's imports. Both are pinned by
`test_a_boolean_is_not_read_as_a_number` and
`test_a_non_finite_confidence_is_refused` in T3's test file.

```python
def _valid_address(value: Any) -> str | None:
    """Lowercased ``0x``-prefixed 40-hex address, or ``None``.

    The endpoint is third-party input.  A row whose address will not parse costs
    the ROW, never the sweep -- the same rule the list source already applies to
    a hand-edited export file.
    """
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        return None
    try:
        int(value[2:], 16)
    except ValueError:
        return None
    return value.lower()


def published_band(cluster: Mapping) -> str:
    """The group's band word: the publisher's, or ours derived from families.

    Measured 2026-08-27: over all 160 published clusters the publisher's ``band``
    and :func:`_grade_families` agree exactly, so this is not a reconciliation --
    it is a guard.  ``band`` is a string from an HTTP service and the vocabulary
    beside it (``risk``: ``critical``/``elevated``) is one this dashboard does not
    speak; only ``high`` and ``low`` are passed through, and anything else falls
    back to the grading we can defend from the families we also read.
    """
    band = cluster.get("band")
    if band in ("high", "low"):
        return band
    families = cluster.get("families")
    return _grade_families(set(families) if isinstance(families, list) else set())


def review_members_of(rows: Iterable[Any]) -> dict[int, dict[str, list[str]]]:
    """Cluster id -> ``{address: families}`` for every ``status == "review"`` row."""
    out: dict[int, dict[str, list[str]]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("status") != "review":
            continue
        address = _valid_address(row.get("address"))
        cluster_id = row.get("cluster_id")
        if address is None or not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            continue
        families = row.get("member_families")
        out.setdefault(cluster_id, {})[address] = (
            [f for f in families if isinstance(f, str)] if isinstance(families, list) else []
        )
    return out


def clusters_from_published(clusters: Iterable[Any], rows: Iterable[Any]) -> list[Any]:
    """``sybilkit.Cluster`` objects carrying the published membership.

    The published data supplies membership and reasons; every number downstream
    of here is still computed by the library's own pure code over the LOCAL
    dataset, so a cluster that the endpoint describes but our fold has never seen
    simply contributes no members and no points.
    """
    _require_sybilkit()
    members: dict[int, list[str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        cluster_id = row.get("cluster_id")
        address = _valid_address(row.get("address"))
        if address is None or not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            continue
        members.setdefault(cluster_id, []).append(address)

    out: list[Any] = []
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            continue
        cluster_id = cluster.get("id")
        if not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            continue
        reasons = tuple(
            Reason(
                family=r.get("family") if isinstance(r.get("family"), str) else "",
                human_string=pattern_language(r.get("text"), r.get("family")),
                strength=_opt_float(r.get("strength")) or 0.0,
            )
            for r in (cluster.get("reasons") or ())
            if isinstance(r, Mapping)
        )
        seats = tuple(sorted(members.get(cluster_id, ())))
        out.append(
            Cluster(
                cluster_id=cluster_id,
                members=seats,
                reasons=reasons,
                confidence=_opt_float(cluster.get("confidence")) or 0.0,
                points=_opt_int(cluster.get("points")) or 0,
                points_share=_opt_float(cluster.get("points_share")) or 0.0,
                span_blocks=_opt_int(cluster.get("span_blocks")),
                size=len(seats),
            )
        )
    return out


def detect_result_from_published(
    clusters: Iterable[Any], rows: Iterable[Any], totals: Mapping
) -> Any:
    """A hand-built :class:`DetectResult` over published membership.

    ``sybilkit`` documents the hand-built result as first-class (ruling D1-B) and
    ``DetectResult.__init__`` sorts by ``points_share`` and lowercases its member
    index, so this object answers ``wallet()`` and feeds ``segments()`` /
    ``clean_list()`` identically to one ``detect()`` produced.

    ``analyzed`` is left at its ``frozenset()`` default here and is set by the
    caller from the LOCAL dataset -- the population this build actually folded,
    not the one the publisher folded.  A wallet in neither reads "not analyzed",
    which is the safe default the library chose on purpose.
    """
    _require_sybilkit()
    built = clusters_from_published(clusters, rows)
    total = _opt_int(totals.get("points")) or 0
    linked = _opt_int(totals.get("linked_points")) or 0
    return DetectResult(built, total, linked, max(total - linked, 0))
```

`size=len(seats)` rather than the declared `size` is deliberate: the two agree on the
live service (verified for all 160 clusters) and, when they ever disagree, the members we
actually hold are the honest count.

- [ ] **Step 4: Run the tests**

```bash
.venv/bin/python -m pytest tests/data/test_curator_published_analysis.py -q
```

- [ ] **Step 5: Prove the band guard bites**

Change `published_band` to `return cluster.get("band")` →
`test_an_unknown_band_word_falls_back_to_our_own_family_grading` goes red with
`assert 'critical' == 'high'`. Restore.

- [ ] **Step 6: Commit**

```bash
git add maxpane_dashboard/data/curator_clusters.py tests/data/test_curator_published_analysis.py
git commit -m "feat(curator): rebuild sybilkit clusters from published membership"
```

---

### Task 4: `build_analysis_from_published`

**Files:**
- Modify: `maxpane_dashboard/data/curator_clusters.py`
- Test: `tests/data/test_curator_published_analysis.py`

**Interfaces:**
- Consumes: T3's `detect_result_from_published`, `published_band`, `review_members_of`.
- Produces:
  `def build_analysis_from_published(events, first_deposits, *, clusters, rows, totals, wallet=None, config) -> AnalysisResult`
  — same `AnalysisResult` T10 and T7 consume, with `groups[].review_members` populated
  and one appended `under review` segment row.

- [ ] **Step 1: Write the failing test — the one that matters**

```python
def test_the_rebuilt_clean_list_is_the_published_clean_list_exactly():
    """Not the same count -- the same addresses."""
    ov, ex = _load("overview_trimmed.json"), _load("export_trimmed.json")
    result = cc.build_analysis_from_published(
        _fixture_events(), _fixture_firsts(),
        clusters=ov["clusters"], rows=ex["rows"], totals=ov["totals"],
        config=cc.build_preset(1000, 50_000_000_000_000_000),
    )
    published_clean = {
        r["address"].lower() for r in ex["rows"] if r["status"] == "clean"
    }
    assert set(result.clean_ranks) == published_clean
    assert result.clean_contributors == len(published_clean)
```

`_fixture_events()` / `_fixture_firsts()` build a local `Dataset` covering exactly the
trimmed export's addresses — a small deposit per address with the row's own
`weight_eth`, `first_hour` and `first_index`. Put them in the test module; they are the
local half of the seam and no other task needs them.

Further tests in the same file:

```python
def test_every_group_carries_its_own_review_members_and_no_others():
def test_a_group_with_no_review_member_carries_an_empty_mapping_not_none():
def test_the_review_segment_row_counts_the_review_wallets_and_their_share():
def test_a_review_flagged_group_says_so_in_its_reasons_and_not_in_its_band():
def test_a_forbidden_word_in_a_published_reason_never_reaches_the_row():
def test_sqrt_subsidy_x_is_filled_for_every_operator_row():
def test_operator_rows_lead_with_the_widest_share():
def test_two_calls_over_one_payload_return_equal_results():   # purity: no clock, no I/O
```

- [ ] **Step 2: Run and watch fail**

- [ ] **Step 3: Implement**

Fork `build_analysis`'s body from the `res = detect(...)` line onward. The only
differences:

```python
    res = detect_result_from_published(clusters, rows, totals)
    res.analyzed = frozenset(d.contributor for d in ds.deposits)
    seg = _segments(ds, res, preset)
    clean = _clean_list(ds, res, preset)
    reviews = review_members_of(rows)
```

then, inside the per-cluster loop, `conf = published_band(cluster_dict)` instead of
`_grade_families(families)`, `reasons` gaining the review suffix, and `groups.append`
gaining `"review_members": reviews.get(cluster.cluster_id, {})`.

```python
def _review_suffix(reasons: list[str], cluster: Mapping) -> list[str]:
    """Append ``under review`` to a group the publisher has flagged as such.

    Group review and MEMBER review are disjoint on the live service (measured
    2026-08-27: the 5 ``review_flag`` groups hold zero review members, and all 26
    groups that hold them are unflagged).  So this is a sentence in the group's
    reasons, never a band word -- a group row reading ``~`` while every one of its
    members reads ``⚑`` would be a contradiction the publisher never made.
    """
    if not cluster.get("review_flag"):
        return reasons
    return [*reasons, pattern_language("under review", None, fallback="under review")]
```

and the appended band, inserted directly after the `operators` aggregate row:

```python
    review_total = sum(len(m) for m in reviews.values())
    if review_total:
        # Per-wallet points come from the published rows, which agreed with our
        # own fold to the digit on every shared address (spec §2).  `build_analysis`
        # has no per-address points map in scope -- `segments()` builds one
        # privately -- and reaching for one would mean a second fold of the
        # population for one number.
        review_addresses = {addr for m in reviews.values() for addr in m}
        review_points = sum(
            _opt_int(row.get("points")) or 0
            for row in rows
            if isinstance(row, Mapping)
            and (_valid_address(row.get("address")) or "") in review_addresses
        )
        # After the LAST operators-kind band, not at a remembered index 1: when
        # `seg.operators` is empty `ordered` starts with a cohort band and a
        # hardcoded 1 would drop this row into the middle of the cohorts.
        segment_rows.insert(
            sum(1 for b in ordered if b.kind == "operators"),
            {
                "label": "under review",
                "contributors": review_total,
                "points_share_pct": (
                    review_points / res.total_points * 100
                    if res.total_points
                    else None
                ),
                "detail": pattern_language(
                    "one evidence family or less than the group's · shown, never removed",
                    None,
                    fallback="thin evidence · shown, never removed",
                ),
            },
        )
```

Both numbers are folded from the payload. **Neither 324 nor 0.89 is written into code.**

- [ ] **Step 4: Run the tests** — expected: all pass.

- [ ] **Step 5: Prove the headline test bites**

Change `_clean_list(ds, res, preset)` to `_clean_list(ds, detect(ds, preset.detect_config()), preset)`
→ `test_the_rebuilt_clean_list_is_the_published_clean_list_exactly` goes red on the set
comparison, not the count. Restore. **Name which test reddened**; if the count assertion
fires but the set one does not, the fixture is too small to distinguish them and needs
more contradicting rows.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(curator): build the analysis from published membership"
```

---

### Task 5: The review band, data layer

**Files:**
- Modify: `maxpane_dashboard/data/curator_clusters.py` (`bands_by_address`, `grade_of`, `you_linkage`, `merge_leaderboard_grade`)
- Test: `tests/data/test_curator_clusters.py`

**Interfaces:**
- Consumes: `groups[].review_members` from T4.
- Produces: `def bands_by_address(analysis) -> dict[str, str]` — every analysed address
  to `"high" | "low" | "review" | "clean"`, built in one pass. `grade_of` becomes its
  single-address form. `you_linkage` gains `you_linked_state == "review"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_review_member_grades_review_and_not_its_groups_band():
def test_a_flagged_member_of_the_same_group_still_grades_the_groups_band():
def test_a_clean_address_still_grades_clean_and_a_stranger_still_grades_none():
def test_bands_by_address_agrees_with_grade_of_on_every_address():
    # The two must never diverge: one is the bulk form of the other.
def test_you_linked_state_is_review_with_the_wallets_own_families_as_reasons():
def test_a_review_wallet_keeps_its_groups_size():
def test_an_unreadable_review_members_mapping_costs_the_band_not_the_row():
```

- [ ] **Step 2: Run and watch fail.**

- [ ] **Step 3: Implement**

`grade_of` gains one branch before the band read:

```python
    if group is not None:
        review = group.get("review_members")
        if isinstance(review, Mapping) and address.lower() in review:
            return "review"
        conf = group.get("conf")
        return conf if conf in ("high", "low") else None
```

`bands_by_address` walks groups once and `clean_ranks` once — O(population) rather than
`grade_of`'s O(address × groups), which is what makes the 19,522-row archive write in T9
finish. `merge_leaderboard_grade` builds the map once and indexes it.

`you_linkage` gains, before the existing `"linked"` branch:

```python
    if group is not None:
        review = group.get("review_members")
        if isinstance(review, Mapping) and wallet.lower() in review:
            families = review.get(wallet.lower())
            out["you_linked_state"] = "review"
            out["you_linked_reasons"] = [
                pattern_language(None, family) for family in (families or ())
            ]
            out["you_linked_group_size"] = ...  # unchanged: the group's own size
            return out
```

A review wallet's reasons are its **own** families, not the group's — the group's
reasons describe evidence this wallet does not carry.

- [ ] **Step 4: Run.** - [ ] **Step 5: Prove it bites** — delete the `review` branch in
`grade_of`; `test_a_review_member_grades_review_and_not_its_groups_band` goes red.
- [ ] **Step 6: Commit.**

---

### Task 6: The review glyph and the band filter

**Files:**
- Modify: `maxpane_dashboard/widgets/curator/leaderboard.py`
- Modify: `maxpane_dashboard/data/curator_list_filters.py`
- Test: `tests/widgets/test_curator_leaderboard.py`, `tests/data/test_curator_list_filters.py`

**Interfaces:**
- Consumes: `link_conf == "review"` from T5.
- Produces: `LINK_REVIEW = "~"`, a `"review"` entry in `_LINK_GLYPH`, and `"review"` in
  the filter's accepted band set.

`widgets/curator/operators.py` is **not** modified. See spec §5.3.

- [ ] **Step 1: Measure before you write**

```bash
.venv/bin/python -c "from rich.cells import cell_len; print({g: cell_len(g) for g in ('⚑','◌','?','~','')})"
```
Expected: every glyph 1 except `''` at 0. If `~` is not 1, pick another ASCII mark and
say so in the commit — do not proceed on an assumption.

- [ ] **Step 2: Write the failing tests**

```python
def test_review_renders_its_own_glyph_and_not_the_flag():
def test_the_review_glyph_is_one_column_like_every_other_flag():
    assert all(cell_len(g) == 1 for g in (LINK_HIGH, LINK_LOW, LINK_UNKNOWN, LINK_REVIEW))
def test_the_five_glyphs_are_distinct_in_greyscale():
    assert len({LINK_HIGH, LINK_LOW, LINK_CLEAN, LINK_UNKNOWN, LINK_REVIEW}) == 5
def test_the_flag_column_width_did_not_move():
    assert _FLAG_COLS == 2 and LEADERBOARD_FULL_WIDTH == 49
def test_a_review_row_composites_at_the_minimal_tier():
    # render_strips(), not the content string.
def test_the_band_filter_selects_review_rows():
def test_an_unknown_band_word_still_filters_as_unknown():
```

- [ ] **Step 3: Run and watch fail.**
- [ ] **Step 4: Implement** — `LINK_REVIEW = "~"`, `_LINK_GLYPH["review"] = f"[dim]{LINK_REVIEW}[/]"`,
      and `{"clean", "low", "high", "review"}` in `curator_list_filters`.
- [ ] **Step 5: Run, including the screen test that composites the leaderboard.**
- [ ] **Step 6: Prove it bites** — remove the `_LINK_GLYPH` entry;
      `test_review_renders_its_own_glyph_and_not_the_flag` goes red rather than the
      width test. If the width test reddens instead, the glyph is not one column.
- [ ] **Step 7: Commit.**

---

### Task 7: `slot_payload` — `published` replaces `enrichment`

**Files:**
- Modify: `maxpane_dashboard/data/curator_clusters.py` (`slot_payload`, `AnalysisResult`)
- Test: `tests/data/test_curator_clusters.py`

**Interfaces:**
- Produces: `slot_payload(result, *, published: Mapping | None = None)`. The
  `enrichment=` keyword is **removed** in T11, not here — T11 owns the deletion, this
  task owns the addition, and the two keywords coexist for one commit.

- [ ] **Step 1: Failing tests**

```python
def test_the_published_block_carries_the_version_and_its_hash():
def test_the_payload_holds_no_boolean_verdict():
    # extended to walk review_members too
def test_groups_carry_review_members_through_a_round_trip():
def test_a_payload_with_no_published_block_still_loads():   # backwards compatibility
```

- [ ] **Step 2–6:** run-fail, implement, run, prove (delete the `review_members` copy in
  `slot_payload` → the round-trip test reddens), commit.

---

### Task 8: `analysis_version` — one new key, four widgets

**Files:**
- Modify: `data/curator_models.py`, `data/curator_clusters.py` (`analysis_keys`),
  `data/curator_manager.py` (the stamp beside `analysis_as_of_hhmm`),
  `widgets/curator/{segments,operators,cleaned_list,lists}.py`, `screens/curator.py`
- Test: `tests/data/test_curator_models.py`, the four widget test files, `tests/screens/test_curator_screen.py`

**Interfaces:**
- Produces: `analysis_version: str | None` in `CURATOR_ANALYSIS_KEYS` (now fourteen),
  rendered beside `as of HH:MM`.

- [ ] **Step 1: Failing tests**

```python
def test_the_analysis_keys_are_exactly_the_fourteen_the_adapter_fills():
    # renamed from ...thirteen...; the tuple stays HAND-TYPED, so update it by hand.
def test_the_version_label_renders_beside_the_freshness_marker():
def test_a_missing_version_renders_the_marker_alone_and_not_the_word_none():
def test_the_label_never_widens_a_panel_past_its_pin():
    # measure at SEGMENTS' and OPERATORS' own widths; if it does not fit, the
    # label sheds before the marker does -- the marker is the load-bearing half.
```

- [ ] **Step 2–7:** run-fail, implement, run each widget's file plus the screen test that
  composites it, prove the ordering test bites by swapping the shed order, commit.

**Note for the implementer:** `analysis_as_of_hhmm` is threaded through
`screens/curator.py`'s per-widget key map (around lines 442–456). Grow every entry that
already names it. A widget that receives the key and ignores it is a silent no-op, so
assert the rendered output, not the call.

---

### Task 9: `data/curator_archive.py`

**Files:**
- Create: `maxpane_dashboard/data/curator_archive.py`
- Test: `tests/data/test_curator_archive.py`

**Interfaces:**
- Consumes: T5's `bands_by_address`, the published rows, the superseded slot payload.
- Produces:
  `def archive_and_write(root: Path, *, version_id: str, rows, bands, previous_slot, now: float) -> ArchiveResult`
  with `ArchiveResult(archived: tuple[str, ...], written: tuple[str, ...], failed: tuple[str, ...])`.

**Every path is injected.** No `Path.home()` inside the module; the manager passes the
cache root. No `time.time()`; `now` is a parameter.

- [ ] **Step 1: Failing tests**

```python
def test_the_old_exports_are_moved_and_still_exist_afterwards(tmp_path):
    # move, never delete: assert the archived copy is byte-identical to the original
def test_a_missing_file_is_not_an_error(tmp_path):
def test_the_manifest_records_what_moved_and_what_it_superseded(tmp_path):
def test_the_new_cleaned_list_is_ranked_contiguously_from_one(tmp_path):
def test_the_new_cleaned_list_is_accepted_by_load_export_list(tmp_path):
    # the end-to-end claim: write it, then read it back through the real consumer
def test_the_raw_rows_carry_our_band_and_never_the_payloads_link_conf(tmp_path):
def test_ens_names_are_carried_across_by_address(tmp_path):
def test_a_name_that_matches_no_address_is_dropped_not_guessed(tmp_path):
def test_running_twice_for_one_version_archives_and_writes_nothing_the_second_time(tmp_path):
def test_an_unwritable_archive_directory_does_not_raise(tmp_path):
    # housekeeping never fails the analysis
def test_row_fields_are_exactly_the_frozen_column_tuples(tmp_path):
```

- [ ] **Step 2: Run and watch fail.**

- [ ] **Step 3: Implement**

Archive set, in order:

```python
_ARCHIVED = (
    "curator_cleaned_list.json", "curator_cleaned_list.enriched.json",
    "curator_raw_list.json", "curator_raw_list.enriched.json",
    "curator_clean_list.json", "curator_clean_list.csv",
    "curator_lists.json",
)
```

plus `clusters_slot.json` written from `previous_slot`, plus `manifest.json`:

```json
{"archived_at": 1787900000.0, "superseded_version": "…", "new_version": "…",
 "files": [{"name": "...", "bytes": 2043639, "sha256": "..."}]}
```

Use `os.replace` within the same filesystem; fall back to `shutil.move`. **Never
`unlink`.** A per-file failure appends to `failed` and is logged; the function still
returns.

Then write, using `CURATOR_ROW_KEYS["leaderboard_rows"]` and
`CURATOR_ROW_KEYS["clean_list_rows"]` as the column tuples — imported, never retyped:

- `curator_raw_list.json` — every valid row, published `rank` preserved, `link_conf`
  from `bands`, `name` from the carried-over ENS map.
- `curator_cleaned_list.json` — `status == "clean"` rows only, `clean_rank` renumbered
  `1..N` in published rank order.

- [ ] **Step 4: Run.**
- [ ] **Step 5: Prove two bite** — (a) change `os.replace` to `shutil.copy` +
  `os.unlink`: `test_the_old_exports_are_moved_and_still_exist_afterwards` must stay
  green (it checks the archived copy, not the mechanism) while nothing else changes —
  if a test reddens, say which and why. (b) Renumber from 0:
  `test_the_new_cleaned_list_is_ranked_contiguously_from_one` **and**
  `test_the_new_cleaned_list_is_accepted_by_load_export_list` both redden. Two reds from
  one mutation is the signal that the second test is real rather than a restatement.
- [ ] **Step 6: Commit.**

---

### Task 10: `_pool_analysis` — the new body

**Files:**
- Modify: `maxpane_dashboard/data/curator_manager.py`
- Test: `tests/data/test_curator_manager_analysis.py` (existing file; find it with
  `rg -l "_pool_analysis" tests/`)

**Interfaces:**
- Consumes: T2, T4, T7, T9.
- Produces: no new public surface. `_spawn_analysis`, `_analysis_detached`,
  `_cancel_analysis`, `_analysis_failed`, `TIER_ANALYSIS` and `SLOT_CLUSTERS` are
  unchanged.

- [ ] **Step 1: Failing tests**

```python
def test_a_tick_that_finds_the_same_content_hash_makes_no_bulk_request():
    # the whole fetch policy in one assertion: count the transport's calls
def test_a_new_version_id_triggers_the_two_bulk_reads_and_stores_once():
def test_a_failed_version_check_leaves_the_held_payload_untouched():
def test_a_failed_export_after_a_good_overview_stores_nothing():
def test_the_slot_is_never_written_from_half_a_payload():
def test_the_first_payload_is_not_behind_the_analysis_read():   # EXISTING - must still time out on failure
def test_a_missing_sybilkit_is_still_the_cannot_run_state_with_no_banner():
def test_the_archive_is_called_once_per_new_version():
def test_an_archive_failure_does_not_fail_the_load():
def test_a_cannot_run_tick_still_does_not_clear_the_failed_flag():   # existing behaviour, keep
```

- [ ] **Step 2: Run and watch fail.**

- [ ] **Step 3: Implement**

The body, in order — and the order is the design:

1. `TIER_ANALYSIS not in tiers` → `{"ok": None, "swept": False}` (unchanged)
2. `not SYBILKIT_AVAILABLE` → the existing cannot-run branch, **unchanged**: the
   reconstruction needs the library even though the verdicts no longer do
3. events / rate / minimum missing → the existing cannot-run branch, unchanged
4. `fetch_published_version` → `None` → `mark_failed`, return `{"ok": False, "swept": True}`
5. version id **and** `content_hash` match the held `published` block → `mark_fetched`,
   return; **no bulk fetch**
6. `fetch_published_analysis` → `None` → `mark_failed`, held payload untouched
7. `build_analysis_from_published` in `asyncio.to_thread` — the pure folds took 0.1 s in
   the spike but `Dataset.from_events` took 0.5 s over 28,353 events, and the TUI's loop
   must not wear either
8. `store_analysis(payload, ts=now)` — **once**, from a complete pair
9. archive, inside its own `try`, after the store: a failed archive is logged and the
   sweep still succeeded
10. `mark_fetched`, `self._analysis_failed = False`

- [ ] **Step 4: Run the manager's analysis tests plus the screen tests that render the
  analysis panels.**
- [ ] **Step 5: Prove step 5 bites** — compare only the version id, not the hash; add a
  fixture pair with one id and two hashes;
  `test_a_tick_that_finds_the_same_content_hash_makes_no_bulk_request` must not be the
  test that catches it — write the one that does.
- [ ] **Step 6: Commit.**

---

### Task 11: Remove the sweep

**Files:**
- Modify: `maxpane_dashboard/data/curator_clusters.py`, `maxpane_dashboard/data/curator_manager.py`
- Delete: the enrichment tests (find with `rg -l "fetch_enrichment|candidate_targets|TX_BUDGET" tests/`)

**Interfaces:**
- Removes: `fetch_enrichment`, `candidate_targets`, `EnrichmentState`, `TX_BUDGET`,
  `FUNDING_BUDGET`, `PENDING_PAGES` and the four `sybilkit.sources` imports;
  `slot_payload`'s `enrichment=` keyword; `_analysis_session`'s enrichment plumbing;
  the `enrich.tx_ok` / `enrich.funding_ok` retry logic.
- Keeps: everything named in spec §7.

- [ ] **Step 1: Find every caller**

```bash
rg -n "fetch_enrichment|candidate_targets|EnrichmentState|TX_BUDGET|FUNDING_BUDGET|sybilkit.sources" maxpane_dashboard/ tests/
```

Delete nothing until this list is empty of production callers.

- [ ] **Step 2: Remove, one symbol per commit-sized step**, running the two owning test
  files after each.

- [ ] **Step 3: Confirm the import guard still holds**

```bash
rg -n "import sybilkit|from sybilkit" maxpane_dashboard/
```
Expected: exactly `maxpane_dashboard/data/curator_clusters.py`.

- [ ] **Step 4: Confirm the cache still loads a payload written by the old build**

```bash
.venv/bin/python -c "
from maxpane_dashboard.data import curator_cache as c
# load the developer's real ~/.maxpane/curator_cache.json read-only and assert
# an old payload carrying 'enrichment' does not raise"
```

An old cache file still carries `enrichment`. It must be **ignored, not rejected** — a
startup that aborts on a superseded key is the defect this repo already fixed once for
persisted series.

- [ ] **Step 5: Commit.**

---

### Task 12: Guardrails and documentation

**Files:**
- Modify: `CLAUDE.md`, `README.md`
- Test: `tests/test_curator_registration.py`, `tests/data/test_curator_clusters.py`

- [ ] **Step 1: The guardrail tests**

```python
def test_only_curator_clusters_imports_sybilkit():          # existing - must still pass
def test_curator_signals_never_imports_sybilkit():          # existing - must still pass
def test_no_verdict_is_persisted_in_the_cache_file():       # extended to review_members
def test_every_evidence_panel_still_refuses_the_forbidden_words():
    # composited, with a published payload whose reasons carry one
def test_the_published_base_url_is_the_only_new_host():
    # no key, no token, no secret anywhere in the new modules
```

- [ ] **Step 2: Update `CLAUDE.md`**

The curator section currently describes the sweep as "Tier-B/C analysis (tx fingerprints
via publicnode/tenderly batches, first funders via Blockscout … resumable through a
cursor in the slot)". Replace that paragraph with the published-analysis story. Keep the
detached-spawn contract, `TIER_ANALYSIS`, `SLOT_CLUSTERS`, the last-good rules and the
"nothing is persisted as a verdict" paragraph — **all still true**. Add the review band
to the evidence vocabulary line (`⚑`/`◌`/`~`/`?`).

Keep it to the same register and do not grow the file: this is a replacement, not an
addition. Target a net change under +15 lines.

- [ ] **Step 3: Update `README.md`** wherever it describes the linked-wallet analysis.

- [ ] **Step 4: Run the doc-pinning tests**

```bash
.venv/bin/python -m pytest tests/test_curator_registration.py -q
```

- [ ] **Step 5: Full suite — this is one of the times it is warranted**

```bash
.venv/bin/python -m pytest
```

A multi-task branch touching the data layer, four widgets and a screen is exactly the
"before a merge that follows real code changes" case. Expect one pre-existing failure,
`tests/screens/test_curator_screen.py::test_screen_adds_removes_and_deduplicates_custom_collection`
(a known flake, missing await, 4 fails in 12 runs — follow-up item 10). Any *other*
failure is yours.

- [ ] **Step 6: Commit.**

---

## Self-review

**Spec coverage** — every section has a task: §3 → T2; §4 → T3, T4; §5.1 → T7; §5.2 →
T8; §5.3 → T5, T6; §6 → T9; §7 → T11; §8 → T10; §9 → T3, T4, T12; §10 → T1 and each
task's own tests; §11 → Global Constraints; §12 → nothing, by design.

**Placeholders** — none. Every step names a file, a command and its expected output.
T4's `_fixture_events()` and T6's glyph choice are the two places the implementer
decides something, and both say what to do if the measurement disagrees.

**Type consistency** — `PublishedVersion` / `PublishedAnalysis` (T2) are consumed only
by T10; T3 and T4 take plain `clusters`/`rows`/`totals` so the adapter never imports the
fetch layer. `bands_by_address` (T5) is consumed by T9 and by `merge_leaderboard_grade`.
`ArchiveResult` (T9) is consumed only by T10. `review_members` is written by T4, read by
T5, persisted by T7 and scanned by T12.

**The known risk** — T4's local-`Dataset` fixture is the one piece not validated by the
spike, which used the real 28,353-event cache. If `_fixture_events()` cannot reproduce a
`Dataset` whose `first_index` and weights match the trimmed rows, the clean-set equality
test compares two things that were never equal. T4 Step 5 is written to catch exactly
that: if the count assertion fires and the set assertion does not, the fixture is wrong,
not the code.
