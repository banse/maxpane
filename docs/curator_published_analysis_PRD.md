# THE LIST — the published 0.2.0 analysis as the source of the cleaned list

**Status:** approved 2026-08-27 · spec for implementation
**Dashboard:** `curator` (THE LIST), positions `f` (linked-wallet analysis), `l` (record lists), `y` (your standing)
**Supersedes:** the detached Tier-B/C sweep introduced in the sybil build (WP3)

---

## 1. Goal

THE LIST's linked-wallet analysis stops being computed locally from a partially
enriched sweep and starts **loading the published, immutable analysis** that
`clustermap.vibingco.de` serves — currently `2026-08-25-sybilkit-0.2.0`, produced by
the `v2h` rule set that ships as `sybilkit` 0.2.0's main utility.

The old on-disk list exports are **archived, never deleted**, the new complete lists
are written in their place, and `e` re-exports from the new data exactly as before.

## 2. Why

**The local sweep cannot catch up.** It is budgeted to *candidate* members and
resumable across sweeps by design (candidates only, never the population — PRD §4,
ruling R3). The published analysis carries a first funder for **all 19,522**
contributors and 28,353 transaction fingerprints, at snapshot block 25807057. The
game settled 2026-08-19, so the population is frozen: there is no future sweep in
which the local path overtakes the published one.

**The cleaned list on screen is already wrong.** `load_export_list` rejects an export
whose row count does not equal `clean_contributors` (`curator_list_source.py:140`).
`~/.maxpane/curator_cleaned_list.json` holds 8,745 rows written 2026-08-19; the live
slot says 7,949. The file is therefore rejected on every open and the `l` CLEANED view
falls back to the capped 1,000 live rows with `complete=False`. Today the reader sees
1,000 of 7,949, and `e` re-exports from a slot the file already disagrees with.

**The verdicts moved.** Measured against the live slot's own `clean_ranks`:

| | slot (0.1.1, partial enrichment) | published (0.2.0) |
|---|---|---|
| clean | 7,949 | **6,782** |
| linked | 11,573 | **12,416** |
| review | — | **324** |
| groups | 263 | **160** |
| clean points | 12,572,924 | **6,665,619** |
| linked share | 57.63 % | **77.54 %** |

4,882 wallets keep their clean standing, 3,067 lose it, 1,900 gain it.

## 3. The source

Base URL `https://clustermap.vibingco.de/api/v1`. Keyless, read-only, `GET` only.
Three endpoints are used; **`/list` is not**, because it caps `limit` at 200 and
paging the population would take 98 round trips.

### 3.1 `GET /versions`

~1 KB. Returns `published_version` (a version id) and a `versions[]` array. The entry
whose `id` equals `published_version` carries `content_hash`, `detector_version`,
`rule_set`, `rules_sha256`, `snapshot_block`, `stage`, `cluster_count` and
`status_counts {clean, flagged, review}`.

This is the **only** request made on a steady-state tick.

### 3.2 `GET /overview?version=<id>`

Cluster metadata for every cluster — verified uncapped: 160 returned against a
declared `cluster_count` of 160. Per cluster:

```
id · size · confidence · band · points · points_share · span_blocks
families[] · reasons[{family, strength, text}] · edge_count · risk
review_flag · review_reasons[]
```

Plus `totals {population, deposits, groups, linked_wallets, unlinked_wallets,
status_counts, points, linked_points, tx_fingerprints, funding_rows}` and
`provenance {chain_id, contract, deployment_block, snapshot_block, snapshot_at}`.

**No membership.** That is what §3.3 is for.

### 3.3 `GET /list/export?q=&link=all&evidence=all&preset=none&version=<id>`

The whole population in one response — 19,522 rows, 8.3 MB, `application/json`.
Per row:

```
rank · address · points · credit_eth · tx_count · weight_eth
first_hour · first_index · name · flagged · link_conf
cluster_id · status · risk · evidence_band
member_families[] · member_family_count · under_review
```

`link=unlinked` returns the 6,782 clean rows and is what the site's own CLEAN view
exports; we fetch `link=all` instead, once, and derive both lists from it.

### 3.4 Self-consistency, verified against the live service

Before designing against this API it was cross-checked against itself:

- membership counts derived from `cluster_id` match `/overview`'s `size` for **all 160** clusters
- total members 12,740 = `totals.linked_wallets`
- `sum(row.points)` over all 19,522 rows = 29,675,956 = `totals.points`
- `sum(row.points)` over the clean rows = 6,665,619 = `totals.points − totals.linked_points`
- `status_counts` 6,782 + 12,416 + 324 = 19,522 = `totals.population`

### 3.5 The `link_conf` trap — load-bearing

Every row carries **two** standings:

- `status` ∈ `clean | flagged | review` — the **0.2.0** verdict
- `link_conf` ∈ `clean | low | high | null` — the **0.1.1** standing, carried for comparison

They disagree on **4,641 wallets**. 1,727 rows the 0.1.1 field calls `high` are 0.2.0
`clean`; 2,914 it calls `clean` are 0.2.0 `flagged`. `flagged` (the boolean) is
Tier-A's answer and is `True` on 2,589 of the 6,782 clean rows.

**The payload's `link_conf` and `flagged` fields are never read.** THE LIST's band is
derived from `status`, `evidence_band` and `under_review` only. A test pins this by
feeding a fixture whose `link_conf` contradicts its `status` and asserting the
rendered band follows `status`.

## 4. Architecture — the seam

The published data supplies **membership and reasons**. Everything downstream stays
sybilkit's own pure code, run over the local `Dataset`:

```
                    ┌─ detect(ds, cfg)          ← removed from this path
build_analysis ─────┤
                    └─ segments() · clean_list()  ← reused verbatim

build_analysis_from_published ── DetectResult(hand-built) ─┬─ segments()
                                                            └─ clean_list()
```

`Cluster`, `DetectResult` and `Reason` are top-level `sybilkit` exports and the
library documents the hand-built result as first-class ("a hand-built one that ruling
D1-B made first-class", `report.DetectResult`). They exist in 0.1.0.

**No dependency bump.** `sybilkit>=0.1.0` stands. 0.2.0 is in-tree but **not on
PyPI** (0.1.1 is the latest published), and pinning it would make `pip install
maxpane` unresolvable — the exact failure the guarded import exists to avoid.

`SYBILKIT_AVAILABLE` keeps its current meaning and its current behaviour: absent
library → the analysis is unavailable, spaced retry, no banner.

### 4.1 Proven, not assumed

The reconstruction was run against the real cache and the live payload before this
spec was written:

```
cache: 28353 events, 19522 firsts, rate=1000, min=50000000000000000
clean_contributors: 6782            (published says 6782)
clean sets identical: True | diff: 0
clean points:        6665619        (expect 6665619)
bands: 72 | operators: 160 | top subsidy_x: 14.66×
segments+clean_list in 0.1s
```

Not merely the same count — **the same 6,782 addresses**. `sqrt_subsidy_x` and all 72
segment bands come out of the existing code path unchanged.

### 4.2 Module layout

| Module | Role |
|---|---|
| `data/curator_published.py` **(new)** | The three fetches and the raw-payload validation. No sybilkit import, no `pattern_language`. Takes an injected client/transport exactly like the enrichment fetch it replaces. |
| `data/curator_clusters.py` | Gains `build_analysis_from_published()` and the published→`Cluster`/`DetectResult` reconstruction. Still the **only** module that imports `sybilkit`, and still the translation boundary. |
| `data/curator_archive.py` **(new)** | Moves the superseded exports aside and writes the new ones. Injected root and clock; no network. |
| `data/curator_manager.py` | `_pool_analysis` swaps its Tier-B/C body for the version check + published load. Tier, slot, detachment, freshness and degradation rules unchanged. |

### 4.3 Fetch policy

A published version is **immutable and content-addressed**. Each analysis tick:

1. `GET /versions`. On failure → `mark_failed(TIER_ANALYSIS)`, 300 s backoff, last-good served.
2. If `published_version` and its `content_hash` equal what the slot already holds →
   `mark_fetched`, republish the held payload. **No large fetch.**
3. Otherwise `GET /overview` and `GET /list/export?link=all`, rebuild, `store_analysis`, archive (§6).

Steady state is ~1 KB per 30 minutes. The 8.3 MB pair is fetched only when the
publisher ships a new analysis.

**Follow, do not pin.** The version id comes from `published_version`, so a future
0.3.0 is picked up without a code change. The id is recorded in the payload and
rendered, so the panel always says which analysis it is showing.

## 5. Data contract

### 5.1 The slot payload

`SLOT_CLUSTERS`'s key set is unchanged except that `enrichment` is replaced by
`published`, and two keys are added inside `groups` and at the top level.

| Key | Source |
|---|---|
| `operator_rows[].size / points` | `/overview` cluster `size` / `points` |
| `operator_rows[].points_share_pct` | cluster `points_share` × 100 |
| `operator_rows[].reasons` | cluster `reasons[].text`, through `pattern_language` |
| `operator_rows[].conf` | cluster `band` — `high` or `low`. **Never `review`** (§5.3). |
| `operator_rows[].sqrt_subsidy_x` | `segments()` — `OperatorSegment.subsidy_x` |
| `segment_rows` | `segments()`, plus the review band (§5.3) |
| `clean_list_rows` | `clean_list()`, capped at `CLEAN_LIST_LIMIT` as now |
| `clean_ranks` | `clean_list()` — all 6,782 |
| `groups[].members` | addresses grouped by `cluster_id` from the export |
| `groups[].review_members` **(new)** | `{address: [families]}` for that group's `status == "review"` rows; `{}` for the 134 groups that have none |
| `operators_count` / `points_total` | `totals.groups` / `totals.points` |
| `clean_points` / `clean_contributors` | `clean_list()` |
| `flagged_points_share_pct` | `totals.linked_points / totals.points × 100` |
| `published` **(new, replaces `enrichment`)** | `{version_id, content_hash, detector_version, rule_set, rules_sha256, snapshot_block, status_counts, fetched_at, archived_version}` |

`published` holds no verdict — an id, a hash and counts. The "nothing is persisted as
a verdict" scan keeps biting: groups still carry a band **word** and their families,
and `review_members` is membership data of the same class as `members`.

### 5.2 One new analysis key

`CURATOR_ANALYSIS_KEYS` grows to fourteen with `analysis_version: str | None` — a
short rendered label, e.g. `sybilkit 0.2.0 · 2026-08-25`. It is threaded to the same
four widgets that already take `analysis_as_of_hhmm` (`segments`, `operators`,
`cleaned_list`, `lists`) and rendered beside it.

The tuple is hand-typed, so
`test_the_analysis_keys_are_exactly_the_thirteen_the_adapter_fills` is updated by
hand and renamed to say fourteen. It stays hand-typed: deriving it would make the
test compare a constant against itself.

`rules_sha256` is persisted but **not rendered** — 64 characters do not fit any tier,
and a truncated hash proves nothing.

### 5.3 The review band

`review` joins the band vocabulary as a fifth glyph.

- `widgets/curator/leaderboard.py` — `LINK_REVIEW = "~"` and a `"review"` entry in
  `_LINK_GLYPH`. One column by `cell_len`, ASCII, not East-Asian-ambiguous, and
  distinct from `⚑` `◌` `?` and the empty cell in greyscale. `_FLAG_COLS` does not
  move; re-measure and pin it rather than assuming.
- `widgets/curator/operators.py` — **unchanged.** Its `conf` vocabulary stays
  `high`/`low`/`?`; see the disjointness result below.
- `data/curator_clusters.grade_of` — returns `"review"` when the address is in its
  group's `review_members`, before falling through to the group's band.
- `data/curator_clusters.you_linkage` — `you_linked_state` gains `"review"`; the
  reasons are the wallet's **own** families through `pattern_language`, not the
  group's, and `you_linked_group_size` stays the group's.
- `data/curator_list_filters.py` — the band filter accepts `review`.
- One appended segment row: `label: "under review"`, `contributors: 324`,
  `points_share_pct: 0.89`, `detail` naming the periphery rule. Ordered directly
  after the `linked groups` aggregate. The 324 and the 0.89 % are read from the
  payload, never written as constants.

**`~` is a per-wallet mark and never a group mark.** The endpoint carries *two*
unrelated review concepts, and conflating them puts contradicting glyphs on one screen:

- **group-level** — `review_flag` on 5 clusters (`20, 44, 141, 147, 148`), of which 4
  also have `risk: "review"`; sizes 5–10.
- **member-level** — `status: "review"` on 324 wallets, spread across **26** clusters.

Measured 2026-08-27: the two sets are **disjoint**. The 5 review-flagged groups contain
**zero** review members, and all 26 groups holding review members have
`review_flag: False`. Every member of a review-flagged group is `status: flagged`.

So a group's `conf` stays its `band`, and the flag column's `~` is only ever the
per-wallet mark. The 5 review-flagged groups instead get `under review` appended to
their reasons through `pattern_language`, so the fact reaches the screen without a
group row saying `~` while every one of its members says `⚑`. `review_flag` and
`risk` do not agree either (5 against 4), so `review_flag` alone drives that suffix.

**Do not invent the mechanism.** 202 of the 324 carry `amount` alone, 65 `sequence`,
42 `cadence` — but **15 carry two families** (`amount` + `cadence`). "Fewer than two
families" is therefore *not* the rule. The publisher names it `v2h (v2g + aged-weak
periphery)`; the detail string describes what it means for the reader — thin evidence,
shown rather than removed — and claims nothing about the gate.

Review wallets are **outside** the cleaned list, matching the publisher: clean = 6,782,
and `clean_list()` reproduces exactly that set from the reconstructed membership.

## 6. Archive and reload

On the first successful load of a version id the slot has not seen, `curator_archive`:

**1. Moves** — never copies-then-deletes, never deletes — into
`~/.maxpane/archive/<version-id>/`:

```
curator_cleaned_list.json         curator_cleaned_list.enriched.json
curator_raw_list.json             curator_raw_list.enriched.json
curator_clean_list.json           curator_clean_list.csv
curator_lists.json
clusters_slot.json                ← the superseded SLOT_CLUSTERS payload
manifest.json                     ← what moved, from where, when, and the version it superseded
```

A file that is not there is not an error. A move that fails is logged and **does not
fail the load**: the analysis is the deliverable, the archive is housekeeping.

**2. Writes** the new complete lists from the published export:

- `curator_raw_list.json` — all 19,522, `rank` as published (1..19,522, contiguous)
- `curator_cleaned_list.json` — the 6,782, re-ranked **contiguously as `clean_rank`**

The published `rank` is the *raw* rank and is full of gaps on the clean subset;
`_normalise_rows` requires `clean_rank == expected_rank` for every row, so re-ranking
is mandatory, not cosmetic.

Row fields are exactly `CURATOR_ROW_KEYS["leaderboard_rows"]` and
`CURATOR_ROW_KEYS["clean_list_rows"]` — nothing extra, and `link_conf` on the raw
rows is **our** band from §3.5, never the payload's.

**3. Carries ENS across.** The archived `.enriched.json` files hold 21 verified names
across the raw list and 9 across the cleaned one. They are merged into the new files
by lowercase address so hydration does not start over. A name that fails to match is
dropped, not guessed.

**4. Is idempotent.** `published.archived_version` in the slot records what has been
archived. A second load of the same version archives nothing and rewrites nothing.

## 7. What is removed

From `curator_clusters.py`: `fetch_enrichment`, `candidate_targets`, the
`EnrichmentState` cursor, `TX_BUDGET`/`FUNDING_BUDGET`, and the `sybilkit.sources`
imports (`txs`, `blockscout`, `PENDING_PAGES`, `DEFAULT_CONFIG`).

From `curator_manager.py`: the Tier-B/C half of `_pool_analysis`, `_analysis_session`'s
enrichment plumbing, and the partial-coverage retry logic that reads `enrich.tx_ok` /
`enrich.funding_ok`.

`_spawn_analysis`, `_analysis_detached`, `_cancel_analysis`, `_analysis_failed`,
`TIER_ANALYSIS`, `SLOT_CLUSTERS` and `analysis_last_good()` all **stay** — the sweep
is still detached and still must not block first paint.

Their tests go with them. `test_the_first_payload_is_not_behind_the_analysis_read`
stays and must still fail by timing out if the load is ever awaited.

## 8. Degradation and freshness

Unchanged in shape, so this section is a promise rather than a design:

- A failed read is `None`, never `0` or `[]`. A version check that fails leaves the
  held payload alone.
- Last-good is served behind `analysis_as_of_hhmm`, on `TIER_ANALYSIS`'s slower clock.
- The `logs` degraded group lights **only when there is nothing to serve**.
- A payload built before the load lands is the already-supported "analysis has not run
  yet" state: twelve keys in their honest `None`, `?` in the flag column, never an
  empty cell.
- A published version whose `overview` or `export` fetch fails **does not** half-apply:
  the slot is written once, from a complete pair, or not at all.

## 9. Third-party string discipline

Every string from the endpoint is third-party input, and the endpoint is not the
library — it is an HTTP service that can serve anything.

- `pattern_language()` re-checks every cluster reason, review reason, band label and
  detail on the way out. The forbidden-word list does not change.
- Every evidence panel keeps its composited forbidden-word test; the fixtures gain a
  payload whose `reasons[].text` contains a forbidden word, and the test asserts the
  family's own phrase is what renders.
- `safe_markup` / pre-built `rich.text.Text` on every surface that renders a name or a
  reason, as now. A malformed reason costs its row, not the app.
- Addresses are validated (`0x` + 40 hex) and lowercased on read. A row that fails
  validation is dropped with a debug log, never rendered.
- Numbers are coerced per field; a `points` that will not parse costs the cell.
- Each response is size-capped before it is parsed (`/versions` 1 MiB, `/overview`
  16 MiB, `/list/export` 64 MiB — the export measures 8.3 MB today, so the cap is
  headroom for a larger population and not a limit anything real approaches) and
  type-checked at the top level before it reaches the adapter.

## 10. Testing

**No test touches the network** — an injected transport that raises on use, asserted
structurally.

Fixtures under `tests/fixtures/curator/published/`:

| Fixture | What it is for |
|---|---|
| `versions.json` | the real `/versions` body, verbatim |
| `overview_trimmed.json` | ~12 clusters preserving `high`/`low`/`review_flag` and multi-family reasons |
| `export_trimmed.json` | ~400 wallets spanning all three `status` values, including the `link_conf`-contradicts-`status` rows |
| `export_hostile.json` | forbidden words in reasons, a `[/x]` name, a bad address, a non-integer `points`, an oversized field |

Tests that must **bite** (mutate the code, watch the right test go red, restore):

1. the band follows `status`, not the payload's `link_conf` — flip one row's `link_conf` and the render must not move
2. `clean_list()` over reconstructed membership equals the published clean set (over the trimmed fixture, exactly)
3. re-ranking is contiguous — `load_export_list` accepts the written cleaned file
4. a failed `/overview` after a successful `/versions` leaves the slot untouched
5. the archive moves rather than deletes, and a second run is a no-op
6. the archive failing does not fail the load
7. `~` is one column at every tier, and `_FLAG_COLS` did not move
8. the first payload is not behind the analysis read (existing, unchanged)
9. `rg -n "import sybilkit|from sybilkit" maxpane_dashboard/` still returns exactly `data/curator_clusters.py`
10. no boolean verdict is persisted — the cache-file scan, extended to `review_members`

## 11. Global constraints

- **Read-only.** No signer, no transaction, no calldata for a state change, no key material.
- **Keyless.** `clustermap.vibingco.de` needs no key; verified with a bare `curl`.
- **No test touches the network.**
- **Read values live; never hardcode a documented one.** The version id, counts and
  hashes are read from `/versions`; nothing in this spec's tables is written into code
  as a constant.
- **`data/curator_clusters.py` stays the only importer of `sybilkit`.**
- **`analytics/curator_signals.py` is not opened.** It never learns any of this exists.
- **Widgets stay pure** — no `data/` import in anything new.
- Layout changes obey `.claude/skills/terminal-layout/SKILL.md`; the review glyph is
  measured with `cell_len`, not `len()`.

## 12. Out of scope

- `/wallets/{addr}`, `/clusters/{id}`, `/delta` and `/changelog` — the two bulk
  endpoints cover every panel; a per-wallet lookup would be a second source of truth.
- Version *selection* in the UI. The dashboard follows `published_version`. Browsing
  superseded analyses is the website's job.
- Re-running `sk_v2.py` locally. The rules file is pinned by content and shipped
  byte-identical; reproducing it is `clustermap`'s audit harness, not a TUI's job.
- Any change to the six-surface registration. This is an expansion of an existing
  dashboard, not a ninth one.

## 13. Appendix — how the numbers here were measured

Every figure in this document came from the live service or the local cache on
2026-08-27, not from documentation:

```sh
curl -s 'https://clustermap.vibingco.de/api/v1/versions'
curl -s 'https://clustermap.vibingco.de/api/v1/overview?version=2026-08-25-sybilkit-0.2.0'
curl -s 'https://clustermap.vibingco.de/api/v1/list/export?q=&link=all&evidence=all&preset=none&version=2026-08-25-sybilkit-0.2.0'
```

The reconstruction spike that produced §4.1 read `~/.maxpane/curator_cache.json`
directly and called `sybilkit.curator.segments` / `clean_list` unmodified.
