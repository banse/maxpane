# Visible dashboard data lifecycle

Status: implemented and reviewed, 2026-10-17. Verification and remaining baseline
failures are recorded in [the loading follow-ups](surf_data_loading_followups.md#visible-dashboard-lifecycle-2026-10-17).

## Problem at the starting revision

At `09a84ddc`, opening BOARDROOM starts `SurfManager._offer_full()` as well as
its card sources. `_cycle()` consequently starts launchpad, pool4, staker,
swarm, score, board and launch collectors, including data for unopened boards.
The app also calls the full collector during the splash. Stopping a screen's
30-second timer leaves manager-owned tasks running; `_full_task` is shielded
from cancellation of its screen waiter. Surf body switches do not produce a
Textual ScreenSuspend event. These are separate causes of unnecessary reads.

The existing data split remains appropriate: clients fetch, caches retain,
managers coordinate and project, screens choose the visible scope, widgets
render primitive values. This change adds lifecycle ownership and narrower
reads within that split. It does not introduce a service, remote endpoint,
event bus, generic dependency graph, or a second source of domain facts.

## Required behavior

1. BOARDROOM fetches only inputs consumed by its cards. Opening BOARDROOM must
   never start a destination board's full collector as a side effect.
2. Opening a detail board displays its retained or persisted cached projection
   before awaiting network I/O. It starts one refresh immediately and then
   schedules refreshes every 30 seconds while visible. Concurrent ticks skip
   an existing refresh rather than restarting or queueing it.
3. Leaving a board stops its poll and presentation timers, cancels its refresh
   worker and all detached reads owned by that scope, and drains cancellation
   before starting the next scope. Existing clients, completed cache values,
   lookup memo entries, cursors, filters and selections remain reusable.
4. Returning to BOARDROOM resumes card reads only. Opening a different board
   starts that board's reads only. Reopening a recently visited board displays
   its cached state immediately and refreshes now, even if its last offer was
   less than 30 seconds ago. Observation timestamps are never advanced by an
   activation, repaint, cancellation, or failed read.
5. The loading signal is the same animated `◐◓◑◒ loading` on every dashboard,
   centered on the terminal's bottom status row. It reflects the active screen
   refresh and that scope's detached requests; it is not inferred from data
   age, missing values, or a failed request. Idle has no spinner.
6. Remove footer key-hint clutter and poll/freshness/error announcements,
   including `r refresh`, `p protocol`, `w work`, `/ cmd`, `esc`, and `30s poll`.
   Keyboard bindings remain functional. Retain the app/version/theme context
   where it fits without moving the loading signal away from terminal center.
   The existing operation-message API must remain usable without hiding loading.
7. First loads and reloads retain good cached values and use neutral dashes for
   values never observed. They do not paint application-generated stale,
   unavailable, source-failure or connecting notices. Internal source states,
   timestamps, coverage and logs remain truthful. Domain states and third-party
   prose are not text-filtered.
8. All reads remain keyless and read-only. Existing provenance, chain identity,
   runtime, receipt, and NFT classification checks are unchanged.

## Minimal lifecycle boundary

Use one active scope for each retained manager. For Surf the scope is
`surfboard`, one of its existing native mode strings, or inactive. Nested NFT,
token overview, token detail and portfolio managers own their local reads and
borrow clients/cache safely. A new request belongs to a scope at its creation;
an old scope cannot regain eligibility merely because a later screen shares
the same manager.

`set_active_view(view | None)` changes eligibility synchronously and cancels
retired reads. A narrow awaited drain in the next fetch settles those tasks
before opening another scope. Existing fetch/snapshot APIs remain the data
contract: `get_snapshot()` and `get_hub_snapshot()` do no I/O;
`fetch_hub_snapshot()` offers card-only work; `fetch_and_compute()` offers
only the selected detail scope. Optional lifecycle methods on other managers
keep generic screen support compatible with existing simple awaited clients.

The screen owns timers and its guarded refresh worker. Manager cancellation
owns detached tasks, including descendants and borrowed task leases. Closing
an HTTP client is an application-shutdown operation, not navigation. A
generation or equivalent ownership check prevents an old refresh's `finally`
from clearing the replacement refresh's state.

## BOARDROOM source boundary

The whitelist is defined by consumed facts, not by the name of a collector.

| Card | Eligible input | Excluded destination work |
|---|---|---|
| ONCHAIN FEED / SIGNALS | Channel items/replies plus all eleven detector inputs: chain state/nonces, bounded decoded logs and wallet activity, launchpad getters/decoys/swap history, one validated launch list | Full dashboard cycle, NFT statistics and launch-detail enrichment |
| BUILT BY SWARM | `/swarm` (`fetch_overview`), `/steps/hourly` summary facts | Completed-job detail walk and launch evidence |
| WORK IN PROGRESS | Overview job-state counts; bounded workflow/job list when needed | Work tree hydration and individual job reads |
| ORACLES | One request-list summary | Selected request, answer and provenance detail reads |
| FLEET / AGENT cards | Workers, contributors, seat-record summaries; at most four assigned `/seats/<token>` responses for status and own-work timestamps | Agent record enrichment, earnings, ENS and runtime enrichment |
| POOL4 | Verified identity discovery and exact state/price getters the card consumes | Staker, flow, burn, receipt and historical scans |
| TOKENS | Catalogue plus volume/market inputs consumed by the card | Candles, trades, full token detail and wallet position reads |
| NFTS | Proven collection summary; bounded discovery with per-deployment code, receipt and ERC-165 proof | Mint rules, source retrieval, token samples and selected collection detail |

Unobserved summary facts stay unknown; a card cannot borrow an unverified claim
or present an incomplete list as a verified global count. Reuse completed full
board evidence in summary projections, but do not refresh that evidence from
BOARDROOM unless it supplies an eligible input listed above. A summary-specific collector may reuse the existing transport,
decoders and cache slots without calling the full board collector.

SIGNALS uses independent source tasks with a 12-second deadline each, source TTLs
and failure backoff. Cheap getters publish independently of historical reads;
interrupted launchpad history retains client checkpoints for a later bounded retry.
The existing eleven detector functions and baselines remain authoritative. Unknown
inputs remain unknown, and passive projection cannot renew source observation times.

## Decisions and tradeoffs

| Approach | Advantage | Cost |
|---|---|---|
| Explicit visible scopes and narrow summary offers (selected) | Small extension of current managers; testable request ownership; no new backend | Must enumerate each existing detached task and mode dependency |
| Generic graph scheduler and separate summary service | Central dependency accounting and future remote reuse | Additional lifetime/state machinery and deployment surface with no current need |

Cancelling on navigation sacrifices completion of the current request in return
for the owner's strict no-hidden-reads requirement. Completed results and scan
checkpoints remain cached. Cold detail boards may take longer than under eager
prefetch, while the boardroom and navigation stop paying for unused detail work.

## Verification contract

Tests use injected transports, clocks and observable gates; none touch the
network or clipboard. A separate bounded keyless live run records actual
request counts by visible scope and renders at 149 columns by 45 rows before
review. The implementation plan names the acceptance cases and ownership.
