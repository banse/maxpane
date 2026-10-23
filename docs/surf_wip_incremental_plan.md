# WIP incremental loading

Date: 2026-10-23. Status: implementation authorized by the owner's “adapt”.
Tier 2: private persisted loading state and shared API-client query support.
This document is the specification and work-package plan for this bounded change.

## Problem and measured baseline

A complete WIP refresh took 40.729 seconds and 64 successful HTTP requests to
`api.imd.fun`: 31 job-list pages containing 14,942 rows, two workflow pages,
one overview and 30 job details. HTTP concurrency was one. The six executing-job
details were available after 4.074 seconds, but the reader published only after
history and optional details finished. The extra offer at 30 seconds reused the
running task; polling did not queue another sweep. The 60-second success TTL then
started at completion.

Explorer's shipped loader uses `since` against source `updatedAt`, with a
five-minute overlap, ID merges and a ten-minute full reconciliation. Canonical API
probes confirmed that `/jobs?since=...` and `/workflows?since=...` return older-created
records updated inside the query window. The measured filtered jobs delta was five
rows in 0.288 seconds; the workflow delta was one row in 0.507 seconds. These are
source observations, not a promised WIP latency or evidence that child changes
always advance a parent revision.

Evidence: `imdb:lessons/2026-10-23-explorer-refreshes-jobs-and-workflows-with-update-deltas.md`
and Explorer's published `/_next/static/chunks/1f14iyrz_zwid.js` on that date.

## Decision and alternatives

Keep one WIP reader, its existing single-flight lifecycle, and the existing
`surf_work` display contract. Add a private catalogue to the existing cache slot.
Acquire changes instead of rescanning history on every warm read; publish current
data before historical work. No new endpoint, database, thread, dashboard, public
model key, layout, or widget is required. Preserve WIP's inclusion of oracle jobs.

Two approaches were considered:

| Approach | Benefit | Cost |
| --- | --- | --- |
| Cache every full API response in a new generic store | Direct replay of historical reads | Large payloads, another persistence boundary, unnecessary raw fields |
| Private normalized catalogue inside the existing WIP slot | Existing atomic cache and migration path; bounded, cleaned data | A small normalized-to-list adapter and explicit coverage metadata |

Choose the second. The existing display snapshot is not itself a catalogue:
it contains historical context scopes and prunes old terminal jobs. Legacy display
rows must not silently become proof of a completed incremental baseline.

## Private catalogue contract

`coerce_snapshot` accepts an optional internal `catalogue` field and returns it
alongside the existing internal snapshot fields. `project` does not emit it to
widgets. Old snapshots remain readable with no certified catalogue.

Suggested minimal shape:

```text
catalogue:
  jobs: null | {rows, watermark, full_ts, read_ts}
  workflows: null | {rows, watermark, full_ts, read_ts}
```

Each entry represents a completed listing operation, never a partial page buffer.
`rows` are normalized list rows validated with the existing job/workflow field
allowlists. Job catalogue rows contain no node detail (`nodes: null`,
`detail_state: not_loaded`). Retain all nonterminal jobs and the existing 24-hour
terminal history; retain the bounded workflow catalogue. Source watermarks are
calculated across every validated listing row before pruning. A valid empty
catalogue has no source watermark and uses a full read on its next refresh.

`watermark` is the last complete listing's maximum source update timestamp;
`full_ts` records the start of its last successful full reconciliation;
`read_ts` records the start of its last successful delta/full listing. All are
validated finite, nonfuture timestamps with consistent ordering. IDs are unique,
text stays cleaned, and existing row limits remain enforced. An entry without
usable source timestamps cannot authorize a delta query.

Validate private catalogue metadata independently. Drop a malformed catalogue
and bootstrap again while preserving an otherwise valid last-good display.
Never use the display snapshot's `read_ts` as the watermark or reconciliation
clock: that timestamp can legitimately be older because it includes reused
optional detail observations. Do not change the cache file's existing version.

Keep unfinished pagination buffers and cursors process-local. A cancelled,
malformed, capped or failed page sequence cannot advance persisted watermarks,
replace a certified catalogue, delete previously known rows, or certify zero.

## Read phases

### 1. Current data

1. Paint the existing display cache immediately through the existing passive UI
   path; entering WIP already makes its reader due.
2. For each valid, recent catalogue, fetch all bounded delta pages using
   `since = watermark - 300 seconds`. On first use, start with a recent page.
3. Read the overview population witness. Revalidate every currently/prior known
   executing ID with the existing fresh-detail boundary, even if its list revision
   did not change. Never carry an old executing state forward as current evidence.
4. Merge validated listing changes by ID, using source revisions to avoid an older
   overlapping row overwriting a newer row. Apply terminal transitions and prune
   only according to the existing history scope. A delta's missing IDs are not
   deletions. Older-created reactivated jobs are admitted normally.
5. Publish a valid current snapshot as soon as available, before a deep history
   scan or optional detail reads. A cold snapshot may be explicitly partial;
   unknown activity stays unknown. Do not invent an empty project/workflow count
   from an incomplete page. Existing scope checks still decide whether a project
   or workflow is current or context.

The fast phase must not wait for full project version enrichment. Fresh active
jobs can be published without authorizing unvalidated historical membership.
The later enriched snapshot adds checked project/workflow context using the
existing membership rules, caps and direct identity checks.

### 2. Reconciliation and context

Full reconciliation is due without a certified catalogue, after 600 seconds, or
when validated population evidence contradicts the merged catalogue. Continue
using the existing bounded pagination and coverage checks, preserving old open
jobs such as blocked/queued records. The overview is a witness, not permission
to infer membership or ignore a malformed tail.

For a warm catalogue, publish a successful delta/current phase before reconciling.
For a cold catalogue, publish the partial current phase before scanning older
pages. Replace catalogue state only after its listing coverage is established.
Preserve independent jobs/workflows completion: a long workflow scan must not
discard a valid jobs baseline. Completed source listings can survive a missing
optional detail without pretending the entire display is complete.

Pagination uses `createdAt` for `before`, while delta selection uses `updatedAt`.
Hold the same `since` cutoff across every delta page. Check cursor progress,
duplicates, malformed timestamps, row limits and truncated tails. An exclusive
timestamp cursor cannot alone prove that a boundary tie lost no rows; use valid
coverage evidence or remain partial. If a full scan spans multiple reads, retain
its initial start time and catch up intervening updates before promoting it as a
new baseline. Never leap a watermark over an unobserved interval.

### 3. Optional details

Keep the existing revision-aware detail memo, fair persisted cursor, original
observation clocks and maximum cache size. Publish before optional work, then
publish a second validated snapshot if enrichment succeeds. Optional work has
a small admitted-work/time budget within the existing 24-read ceiling; bounded
concurrency of four independent detail reads may reduce the measured serial tail.
Do not exceed the shared client's admission or detail-flight limits. It must
not occupy the reader indefinitely or starve normal current-data refreshes.
Budget exhaustion is a normal continuation point, not an outage or an empty set.

The existing reader task owns all phases. No independent recurring background
scheduler is introduced. Cancelling/suspending drains owned work and prevents
later publication; already committed valid current data remains. A cancelled
optional attempt does not advance its cursor or erase prior same-version nodes.

## Cadence and failure policy

Use a 30-second WIP success interval measured from the current phase's read start,
not from the end of optional work. Never schedule catch-up bursts. If a read is
still running, `offer()` returns it. On return from a subview, cached data paints
immediately and a fresh read is offered as today.

A foreground list failure or busy response keeps the last-good snapshot and
uses the existing failure backoff. A failed background reconciliation retains its
old catalogue and retries with backoff; it must not erase a successfully published
current phase or mark unattempted pages as fresh. Optional failure preserves valid
same-revision evidence at its original timestamp. Completed zero observations are
distinct from unknown data throughout.

## Work packages and ownership

Target: less than 1,000 changed production lines. One final review covers the
whole task diff; no separate package review under the repository's small Tier-2
exception. No full test suite unless the owner requests it.

| Package | Owner | Files | Dependency |
| --- | --- | --- | --- |
| A: query support | API worker | `maxpane_dashboard/data/surf_swarm_client.py`, `tests/data/test_surf_swarm_client.py` | None |
| B: catalogue helpers | Catalogue worker | `maxpane_dashboard/data/surf_work_catalogue.py`, `tests/data/test_surf_work_catalogue.py` | A's frozen interface and existing work row validators |
| C: staged reader and integration | Root implementer | `maxpane_dashboard/data/surf_work.py`, `maxpane_dashboard/data/surf_work_reader.py`, `maxpane_dashboard/data/surf_cache.py`, corresponding reader/model/cache tests | A and B interfaces; implementation can proceed in parallel |
| D: evidence and documentation | Root implementer | `tests/screens/test_surf_work_screen.py` only if needed, `docs/surf_work_followups.md`, relevant WORK section of `.claude/rules/surf.md`, this plan's completion notes | A, B and C |
| E: final review | Independent reviewer | Read-only review of the task diff and named checks; no feature edits | Live measurement and focused checks complete |

Frozen API interface:

```python
fetch_jobs(*, limit=100, before=None, q=None, since: str | None = None)
fetch_workflows(*, limit=SWARM_WORKFLOW_PAGE_SIZE, before=None,
                since: str | None = None)
```

`since` uses the same strict UTC timestamp validation as `before`; both may be
present for delta pagination. Default calls and endpoint selection stay unchanged.
Do not add `exclude=oracle` to WIP. Do not repair unrelated endpoint pools in this
change.

Catalogue helper interfaces, owned by B:

```python
coerce_catalogue(raw, *, now)
source_rows(entry, kind)
make_entry(rawrows, kind, *, now, read_ts, full_ts, watermark=None)
await read_delta(fetch, entry, kind, *, now, start, since_ts=None)
```

`coerce_catalogue` always returns the two source keys, dropping invalid entries
independently. `source_rows` converts only the normalized allowlist to API-shaped
list records. `make_entry` validates the entire supplied page set before pruning;
the optional watermark carries the maximum witnessed by a full scan whose caller
has already discarded old terminal rows. `read_delta` owns only listing pagination
and ID merges, never persistence or UI publication. It returns a complete candidate
entry or raises; the reader owns commitment. Reuse `surf_work` row validators rather
than duplicating them. Avoid a top-level import cycle when `coerce_snapshot` invokes
the helper. Evaluation of `now` during a read must allow a legitimate source update
later than the operation's start; `watermark <= read_ts` is not a valid invariant.

## Verification

Write failing behavioral tests before implementation. Use fake/injected transports,
fixture-shaped payloads and injected clocks; no tests may touch the network.

- API encoding and validation: `since` alone, with `before`, and unchanged default
  requests; reject invalid types, dates and non-UTC formats before any transport.
- Cold publication: block a historical page on an event and assert valid current
  data is already in the cache; it must not falsely certify missing populations.
- Warm delta: bootstrap, update an older-created job, reopen a blocked/completed
  job, complete a prior active job, and verify ID merges and fresh active details
  without any full-history call before reconciliation is due.
- Restart: persist/reload a valid catalogue and use deltas; legacy and malformed
  private metadata preserve display data but force bootstrap.
- Watermarks: fail/cancel a later delta page and verify no advancement or deletion;
  cover duplicate IDs, nonadvancing cursors, timestamp ties and stale overlapping
  revisions. Compute the high watermark before age pruning.
- Reconciliation: due after ten minutes; remove an actually absent row only after
  a successful full read. Failed/capped scans keep the old baseline and cannot
  certify zero. Multi-read scans cannot skip updates made during the scan.
- Staging/lifecycle: cancellation before a valid current commit publishes nothing;
  cancellation after that commit preserves it but no unfinished enrichment.
  Inactive views offer no reads; repeated offers share one task.
- Cadence: a slow optional phase does not restart a further 60-second wait;
  elapsed poll slots are skipped and do not queue tasks.
- Preserve existing project membership, workflow ownership, old blocked rows,
  unknown counts, optional fairness, node revision and observation-time tests.

Some existing tests assert whole-cycle atomicity through optional work. Adjust
only those expectations explicitly changed by staged publication; retain their
failure/cursor/node guarantees. Do not weaken assertions to make the new path pass.

Run focused failing cases while implementing. Before commit, run touched data
tests, `tests/screens/test_surf_work_screen.py`, and
`pytest -m 'guard and not mounts_app' tests` using the repository interpreter.
Run mutation proof for the delta watermark and publication/cancellation behavior.
No layout sweep is needed because no geometry changes.

Finally run an isolated live diagnostic with the production reader and cache
writes redirected away from the user's cache. Measure cold first publication,
full reconciliation completion, warm delta publication, total requests/bytes,
peak concurrency, restart reuse and an offer during an in-flight read. Show a
live WIP render at the already-known terminal size before final review. Compare
these separate milestones with the 40.729-second baseline; report measured values
and remaining slow sources without promising a universal latency.

## Implementation evidence (2026-10-23)

The staged reader is implemented without changing public widget keys or geometry.
Current active data is committed before full reconciliation, historical project
version/workflow enrichment, and optional detail work. Unchecked project grouping
is omitted from the foreground and appears only after validated context reads.
A full first jobs page from a legacy cache retains prior display history while
marking population coverage incomplete; that history cannot certify a baseline.
Certified catalogues survive restart. A ten-minute reconciliation first publishes
a fresh delta, then performs its bounded full scan in the same owned task.

Optional work uses at most four concurrent requests, 24 admissions and eight
seconds per cycle. Completed batches advance the fair cursor. Cancellation or
timeout drains the outstanding batch; it cannot fail a valid foreground. A full
jobs scan exceeding the five-minute update overlap is not certified. Multi-cycle
workflow scans perform a scan-start delta before becoming a new baseline.

The API can omit a zero-valued executing bucket from `counts.jobStates`. WIP
interprets absence as zero only when all valid state counts sum to `counts.jobs`
and discovery is complete. Otherwise it retains unknown semantics.

Measured keyless reads used isolated copies of the user's cache, never the live
cache. Timing is for observed workloads, not a controlled same-payload benchmark:

| Measurement | Original | Adapted |
| --- | ---: | ---: |
| First published reader snapshot, legacy cache | 40.729 s | 5.811 s |
| Legacy baseline completion, including optional work | 40.729 s | 45.833 s |
| Jobs list requests in regular refresh | 31 | 1 |
| First current publication, warm reader | 40.729 s original cycle | 3.450 s |
| Warm complete cycle, before optional time cap | — | 10.616 s |
| Restart/current publication with time cap | — | 4.022 s |
| Actual UI cached paint, reader thread + SurfManager + SurfScreen | not measured | 1.597 s |
| Actual UI refreshed paint, same integration | not measured | 7.549 s |

The original full cycle made 64 requests and received 9,909,359 bytes. The first
adapted warm cycle made 27 requests and received 597,413 bytes, including optional
details. All observed responses in that cycle were HTTP 200 from api.imd.fun.
The later UI capture had no executing jobs, so it is not equivalent to the earlier
six-active-job workload. A fresh 149x45 live render was shown before review.

Local diagnostic artifacts: `/private/tmp/maxpane-wip-profile.json`,
`maxpane-wip-after-profile.json`, `maxpane-wip-final-profile.json`,
`maxpane-wip-ui-profile.json`, and `maxpane-wip-ui.png` in the same directory.
These are development evidence, not runtime dependencies. Focused tests also
exercise slow/failed pagination, older-created updates, restart, corrupted
metadata, overlapping offers, four-request cancellation and optional timeout.

### Review fix wave

The final review found four Important issues. Regressions now cover each: malformed
reconciliation must retain all committed rows; exclusive creation cursors require
a one-millisecond overlap to avoid hidden timestamp ties; old project versions must
not block the current snapshot; and interrupted optional batches must restore
same-revision evidence without failure backoff. Both full and delta pagination
validate overlapping boundaries, and ambiguous/non-progressing full pages cannot
certify a new catalogue. Source guards preserve previous rows on malformed input.

The fast pass now publishes active details without unchecked project grouping. A
second pass enriches projects and workflow references, reusing delta discovery when
a full reconciliation is not due. That pass may fail or be cancelled while the
validated current snapshot remains available.

### Completion checks

Final touched/composing run in an isolated HOME, four workers: **683 passed**.
Files: data tests for swarm client, work model/reader/catalogue/loading, Surf cache,
Surf manager/boardroom integration and reader runtime; WIP screen and widget tests.
Fast guards: **128 passed**, one unrelated SWARM TOKENS CSS agreement failure,
reproduced on unchanged HEAD `5d17872c`. No full suite was run. Seventeen
implementer mutations and one reviewer mutation were killed and restored.

The scoped final re-review approved all four fixes after 19 focused regression
cases. No unresolved Critical or Important review findings remain.

The new public zero-bucket API observation was recorded separately in IMDB at
local commit `ea5a1cd3f595e2ff91e2dfaed6b93e3160e250a9`; that lesson was not pushed.
