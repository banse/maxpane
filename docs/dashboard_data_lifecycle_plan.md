# Dashboard data lifecycle implementation plan

2026-10-17 · Tier 2 · implements
[`dashboard_data_lifecycle_spec.md`](dashboard_data_lifecycle_spec.md).

Status: implemented. Agency architecture, backend and frontend packages are
integrated. The single final review's four Important findings were corrected
in one wave; scoped re-review marked all four ADDRESSED. Evidence and baseline
failures live in [the existing follow-ups](surf_data_loading_followups.md#visible-dashboard-lifecycle-2026-10-17).

## Sizing and ownership

Target approximately 650–950 added production lines using existing task
registries, projection methods and clients. No per-package review under this
size; one final review covers the completed diff. If implementation crosses
1,000 production lines, reassess the package review rule before review. No new
layout pins, model contract keys, signer or keyed provider is planned.

Final implementation: 973 added / 410 removed production lines, including the
134-line card reader. Integration extended D to Curator's detached tasks and C
to existing generated source labels plus three legacy screen fetch adapters.
Those files remained exclusively owned by their package implementer. Only the
shared footer received a measured boundary test; dashboard pins were unchanged.

| Package | Owner | Exclusive files / responsibility | Dependencies |
|---|---|---|---|
| A. Lifecycle and navigation | Controller | `app.py`, `screens/dashboard_screen.py`, `screens/refresh_guard.py`, `screens/surf_loading.py`, `screens/surf.py`, `screens/surfboard.py`; related screen/app tests | Agreed manager methods and footer method |
| B. Narrow data scopes | Backend implementer after architecture handoff | `data/surf_manager.py` and minimal affected retained reader/manager modules; corresponding data tests | Lifecycle method contract frozen with A |
| C. Shared footer | Frontend implementer | `widgets/status_bar.py`, footer widget tests and its compositing coverage; status-only stylesheet edits if necessary | Loading setter agreed with A |
| D. Other manager lifecycle and plan | Software Architect | These two documents; `data/{portfolio_manager,swarm_token_detail,fwa_manager,ttt_manager,talismans_manager}.py`; new `tests/data/test_{detail,other_dashboard}_lifecycle.py` | Shared token-manager lifecycle from B; A owns nested screens |
| E. Integration and evidence | Controller | Cross-scope trace tests, existing followups doc and authoritative rule text after verification | A–C complete |

Packages A, B and C may run in parallel after their method seam is agreed;
files do not overlap. Findings in another owner's files are reported, never
fixed by the discovering worker. No subagents spawn subagents. Existing user
work, cache files and untracked files are preserved.

## Implementation sequence

1. Write failing request-trace tests for cold BOARDROOM, hub→detail→hub,
   detail→other detail, and warm reopen. Freeze the minimum public lifecycle
   methods and footer setter before independent edits. Preserve existing
   snapshot payload signatures.
2. Remove the splash's unrestricted full prefetch; the visible dashboard owns
   the first offer. Keep compatibility helpers only where callers still need
   them. A menu or modal must not accidentally reactivate a hidden data scope.
3. Extend the shared screen lifecycle: show cache before network wait, activate
   the correct manager scope, start one immediate refresh plus one 30-second
   interval, stop timers/cancel worker on suspend and unmount, and avoid the
   old-worker-finally/new-worker state race. Route Surf body changes through
   the same ownership transition even when the Textual screen is retained.
4. Add retained-manager suspension separate from `close()`. Cancel and drain
   outstanding detached task families; preserve completed values and client
   connections. Force an entry offer without falsifying source clocks or
   clearing expensive historical caches. A new scope waits for retired work
   to settle, then starts only its own request families.
5. Replace `fetch_hub_snapshot()` full-collector fanout with the card whitelist
   in the spec. Reuse narrow existing sources; add summary variants only where
   the existing method bundles unused detail. Source jobs are parallel where
   their dependencies allow. Full board fetches dispatch by native mode.
6. Move the animation into the shared status bar and remove printed key/poll
   clutter. Generalize loading observation so every dashboard uses actual
   foreground/background work. Keep source state internal and retain cache on
   failure. Paint completed detached reads through passive projection only.
7. Integrate packages, prove the concurrency tests with mutations, run the
   bounded live request trace and show the 149×45 live render. Resolve owner
   corrections before layout hardening or final review. Update authoritative
   rule text that currently prescribes title spinners/full splash prefetch.
8. Run touched/composing test files once in isolated HOME, required fast
   guards, one final review, at most one review fix wave, and a scoped re-review
   only for production changes. File Minor findings. Commit locally; no push.

## Required acceptance tests

| Case | Measurable assertion |
|---|---|
| Cold BOARDROOM | Recorded transport calls are entirely in card whitelist; zero full-board collector calls, NFT detail/source/token reads, selected-job reads, historical receipt scans, wallet reads or candles/trades. Bounded per-deployment NFT code/receipt/ERC-165 proof is allowed and required before counting a deployment |
| Startup splash/menu | Zero unsolicited full-dashboard transport calls before a visible dashboard owns a scope |
| Open detail | Cached projection is rendered while a gated first request is still blocked; exactly one immediate refresh is offered |
| Poll cadence | Injected timer tick at 30 seconds offers one active-scope refresh; an in-flight refresh causes a skip, not cancellation or a queued duplicate |
| Leave while busy | Old transport coroutine observes cancellation; after its finalizer is drained, zero subsequent calls from the old scope while hub/next detail performs its allowed reads |
| Native body switch | Surf `agent→work` and `pool4→swarm` stop the old task family despite no ScreenSuspend; the new family starts immediately |
| Warm reopen | Return inside the former 30-second offer window preserves visible values and filters, starts a fresh request now and resets only the poll cadence |
| Rapid A→B→A | Late finalizers/results from the first A cannot lower the latest loading flag, replace B/A selection or authorize a hidden task; at most one active refresh per scope |
| Detached descendants | Manager collectors and child readers are cancelled and drained, including `_full_task`, auxiliary tier tasks and borrowed job-detail waiters |
| Shared job reads | Cancelling one waiter preserves another valid owner; cancelling the final waiter ends HTTP; completed shared memo remains reusable on reopen |
| Neutral first/reload paint | Cold, warm, failed and cancelled fixtures never paint application-generated stale/unavailable/connecting/error-age text; real domain values and timestamps remain intact |
| Spinner | Composited bottom row contains changing animation frames only during actual active work; spinner center is within one cell of terminal center at narrow and 149-column sizes |
| Footer compatibility | Removed strings do not appear in the composited footer; existing keys and operation messages still work; no overlapping right context |
| Passive repaint | `get_snapshot()`, filters and loading completion repaint cause zero transport calls and do not advance observation clocks |
| Cache safety | Cancellation neither replaces last-good values with defaults nor marks unfinished source tiers as fetched; clients remain open until application shutdown |
| Shutdown | All owned tasks settle before clients close; no retry/timer can restart after close |

Use event-gated async fixtures and captured call lists, not wall-clock sleeps.
Mutation proofs must show a named test fails when full hub fanout returns,
scope cancellation is removed, or activation skips the fresh offer.

## Live evidence and test scope

Record separate cold/warm sequences against keyless sources under an isolated
HOME: hub for one cycle, NFT (or another representative detail) for one cycle,
hub again, a second detail, then the first detail again. Record scope change
times, request starts/completions/cancellations, count and elapsed duration.
The decisive evidence is zero hidden-scope request starts after its cancellation
barrier and no full detail fanout during hub cycles; do not turn variable public
API latency into a deterministic pass threshold.

Render BOARDROOM, one native Surf body, NFT Explorer and one ordinary dashboard
with production CSS at the known 149×45 terminal size. Inspect actual composited
footer placement during load and after completion. A live collection count is
supporting evidence, not a substitute for ownership traces.

While editing run only named cases for changed behavior. Before commit run
touched and composing files with `HOME=$(mktemp -d) .venv/bin/python -m pytest
-n 4 --dist worksteal <files>` and the `guard and not mounts_app` set. Add
registration mounts only if bindings or another registration surface changed;
removing their printed hints does not itself remove a key. Run docpin checks
when authoritative docs are updated. Do not run the full suite.

## Known pitfalls to keep explicit

- `asyncio.shield(_full_task)` separates cancellation of a screen waiter from
  the actual owner; cancelling the Textual worker alone is insufficient.
- Existing SwarmClient job flights cancel on their last waiter; avoid clearing
  completed memo on navigation or globally cancelling another live owner's
  lease. Wait for finalizers rather than assuming `task.cancel()` is drained.
- Cached timestamps describe successful source reads. Forcing an entry offer
  must not re-date old data, reset scan watermarks, or forge zero values.
- A pending old Textual worker may execute its `finally` after the next worker
  begins. Use ownership/generation checks or a drain before replacement.
- Existing display decorators and named lifecycle handlers may both run.
  Consolidate timer ownership so resume cannot install duplicate poll or
  animation timers, and unmount stops them even without a preceding suspend.
- A spinner timer may project completed data, but must never act as an implicit
  200-millisecond retry loop.
- Summary reads must retain provenance and coverage semantics; cheap counts
  are not permission to label partial API lists as complete chain totals.
- TTT and Talismans formerly created independent sibling tasks and awaited
  them sequentially, leaving the unawaited sibling alive on cancellation.
  Await each pair through `gather(return_exceptions=True)` and retain each
  source's existing fallback handling. FWA separately retires both its floor
  and name tasks; navigation preserves their completed cache values.
