# LEADERBOARD launch contribution tab

## Approved behavior

Add a second tab to the existing agent leaderboard:

```text
LEADERBOARD · recorded seats · launch contribution
```

The user chose ranking by **contributing jobs**, rather than distinct launches. A
seat receives one contribution for each distinct job ID that contributed to a
launch. Multiple successful nodes or repeated records for the same seat/job must
not inflate that count. A job contributing to more than one launch still counts
once for that seat. Only seats with a confirmed positive contribution appear.

The recorded-seats tab retains its existing rows, columns, ranking, and behavior.
The new tab uses compact columns backed by available data: rank, seat, contributing
jobs, and, if the source proves the association, distinct launches. Runtime and
current state may reuse the existing worker projection. Do not fetch detailed
answers merely to populate turns, pending, or other unsupported columns. Hero
cards stay unchanged.

Tabs are clickable, following the agent RECORD title's click pattern. Reuse
`SwarmTableBase`; add no keyboard binding. Preserve each tab's selected seat and
sort choice across refreshes and tab switches when that seat remains present.
Existing row click and Enter behavior still open the selected agent. Default
contribution order is descending contributing-job count, with numeric seat ID as
the deterministic tie break.

## Frozen presentation contract and verified source join

The user selected **all launch history**, excluding testnets. Source research
verified the public keyless API at `https://api.imd.fun`. A wallet earning a token
alone is not proof that a particular seat worked on its launch.

Add one nested primitive projection named `swarm_launch_contribution` to
`SWARM_KEYS` and the appropriate `WIDGET_SIGNATURES` entry:

```python
{
    "state": "pending" | "ok" | "partial" | "stale" | "failed" | "unavailable",
    "read_ts": float | None,
    "rows": list[dict] | None,
    "loaded": int,
    "total": int | None,
    "detail": str,
}
# A row:
{"rank": int, "token_id": int, "jobs": int, "launches": int | None}
```

`token_id` is the existing seat identifier. `jobs` counts distinct contributing
job IDs; `launches` counts distinct supported launch associations, otherwise
`None`. `loaded` and `total` describe launch-read coverage, not seat-row counts.
Coverage counts live production launches with complete verified job/seat joins.
`detail` explains that coverage and source failures for the table footer. Use
`rows=None` before a successful read, and `rows=[]` for a confirmed empty result.
Keep rows and their `read_ts` during refresh or failure after a successful read.
Missing metrics are `None`, never synthetic zeros.

The UI locally joins existing `swarm_board_rows` by `token_id` for runtime and
worker state. Its columns are `#`, `seat`, `jobs`, `launches`, `runtime`, `state`;
unsupported launches may display `—` or the column may be omitted. Widgets
perform no I/O and import no data module. This presentation contract is frozen,
so the UI package can start independently of the source-join investigation.

Verified source contract:

- Reuse the existing paginated `/launches?limit=500&before=...` catalogue. Read
  only production chains accepted by `is_production`, with status `live`.
- `/launches/{id}?light=1` proves attached job IDs without large reward payloads.
  Validate identity, chain, status and catalogue version before accepting it.
- `/jobs/{id}` supplies nodes. Count only accepted non-oracle nodes; deduplicate
  by seat/job, including repeated nodes and jobs referenced by multiple launches.
- A job's workflow may expose a frontend job absent from the launch's job list.
  `/workflows/{id}` must link the same contract job and live launch before its
  frontend job is included. The captured launch #1445 proves seats 401 and 402.
- Publish the first ranking only after the whole catalogue and every qualifying
  launch join are complete. A refresh in the middle of pagination is incomplete
  even if an older catalogue had completed. Keep the last complete ranking until
  a coherent replacement is available.
- Six launches per background batch, sequential through existing client pacing;
  offer only while the tab is visible. Poll completion once per second. Cancel on
  hiding/suspending and close before clients close. Getters never perform I/O.
- Persist compact validated facts and the last complete ranking. Terminal facts
  refresh after 1,800 seconds; active facts after 60 seconds. Failed batches back
  off for 120 seconds. Cache reads validate identities, timestamps and fields.
  Restore the reader after loading the manager's disk cache.
- Distinct launch counts use the same verified seat/job associations. Runtime
  and live worker state remain the existing independent board source.

Coverage must be visible whenever the read covers only a bounded launch set or
window. Never present a bounded ranking as an all-time result. Deduplicate
launches and seat/job pairs before aggregation. A valid empty response yields an
empty state; a failed or incomplete read must not become an empty successful
ranking. Keep the last good projection during refresh. Show loading only before
the first successful read; show a clear failure statement when a read fails,
retaining the previous snapshot and its timestamp if available.

## Scope and work packages

Tier 2: one dashboard, a new nested contract key, and integration across more than
six files. Expected total is below 1,000 production lines. Package-level reviews
are waived; there is one final review. Each package owns whole files. No package
may change another owner's files or revert concurrent work.

1. **Controller: contract freeze and integration.** Own
   `maxpane_dashboard/data/surf_models.py`, the existing Surf manager/cache and
   leaderboard screen integration files, their integration/contract tests, and
   this plan after the planning handoff. Confirm exact filenames and freeze the
   projection/interface first. Own any shared-file seam. Wire refresh, caching,
   panel dispatch, and existing seat navigation after packages 2 and 3 land.
2. **Data implementer: contribution fetch and aggregation.** Own
   `maxpane_dashboard/data/surf_launch_contribution.py`,
   `tests/data/test_surf_launch_contribution.py`, and dedicated fixtures. Use the
   frozen contract and existing public client facilities. Existing client edits,
   if essential, must be named and assigned exclusively before dispatch. Cover
   pagination, validation, deduplication, joins, bounded coverage, and failures.
3. **UI implementer: leaderboard tabs and contribution rows.** Own only
   `maxpane_dashboard/widgets/surf/swarm_leaderboard.py` and
   `tests/widgets/test_surf_swarm_leaderboard.py`. Reuse the title click
   pattern and table base; render only the frozen projection. Cover tab switching,
   sorting, selection retention, navigation, loading/error/empty states, and
   composed rendering.

Package 3 can begin immediately against the frozen presentation contract.
Package 2 follows the confirmed source join, then may run in parallel with
package 3. Controller integration follows their delivered interfaces. No
implementer spawns agents. Avoid changing shared widgets unless inspection
proves it necessary; route such a change to the controller first.

## Validation and delivery

- Start with failing focused tests, then implement the smallest passing change.
  Fixtures and injected transports keep every automated test offline.
- Data fixtures must prove two nodes for one seat/job count once, two distinct
  contributing jobs count twice, non-launch work is excluded, repeated launch
  pages do not inflate counts, and failures are distinct from valid empty reads.
- Composed widget tests must prove the original tab is unchanged, contribution
  ordering and counts are correct, each tab can be clicked, sorting and selected
  seat survive refreshes, and click/Enter still open the correct seat. Exercise
  unknown worker fields and visible bounded coverage.
- Use `scripts/mutate.py` on the named critical tests to prove contribution
  deduplication, launch membership, and the new tab's dispatch tests fail when
  those behaviors are broken. Restore mutations byte for byte.
- Once functional, show a keyless live render at the owner's **149 × 45** size
  before layout-pin hardening, reference-doc updates, or review. Verify both tabs
  and genuine launch-contribution data. If minimum layout changes, re-sweep with
  the established layout tooling and update the owning pin comment.
- Before commit, run the touched test files and composing manager/screen files
  once, with isolated `HOME` and `-n 4 --dist worksteal`, then the fast non-mounting
  guards and relevant doc pins. Run registration mounting checks only if a
  registration surface changes. Do not run the full suite.
- One final whole-change review uses the repository's verbatim reviewer contract;
  allow one fix wave and a scoped re-review only for production-code fixes. File
  Minor-only residuals in the existing follow-ups document. Commit locally with
  verification evidence; do not push.


## Live validation — 2026-10-14

The complete keyless read covered 317 live production launches (620 catalogue
rows across two pages) and completed in 391 seconds on a cold contribution cache.
The top three seats were 192, 535 and 1357, each with 13 distinct contributing
jobs. The 149×45 live render showed both tabs, genuine counts, worker joins and
whole-history coverage. Preview artifacts are local in `/tmp/launch-contribution-live.png`
and `/tmp/launch-contribution-recorded-live.png`. The original BOARD pin remains
143×35; the new compact columns do not increase its requirement.

A cached live refresh completed in about one second and included the next
production launch: 318 launches and 727 contributing seats. Final review was
Approved with no findings; final validation is recorded in
`docs/surf_swarm_followups.md`.
