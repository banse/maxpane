# AGENT counts and Boardroom card data

Date: 2026-10-25. Tier 2: shared manager behavior across the AGENT and Boardroom views.
Scope: fewer than 1,000 production lines; one final review, no package reviews.

## Specification

The owner reports: “missing launches and oracle digit numbers” and “agent cards only
load data after opening the detail view,” and requests review of all Boardroom card data.

Required outcomes:

- LAUNCHES and ORACLE show their existing production-job totals and acceptance rates
  when complete evidence is available. A real zero is distinct from an unread value.
- Historical evidence collection can converge for the selected seat's actual record
  size. It cannot continuously evict required evidence before completing the count.
- Boardroom cards acquire the facts they display on a cold start without first
  visiting a destination. Assigned seats remain independent of the selected AGENT seat.
- Last-good values, source clocks, unknown facts and existing display fallbacks remain
  intact. A partial count must not silently become a lifetime total.
- Reads remain public, keyless, bounded, single-flight and cancelled/drained on exit.
  Passive snapshots and UI event handlers perform no network I/O.

No new dashboard, layout pin, endpoint pool, signing path or generic scheduler is intended.
Keep existing primitive payload keys unless a demonstrated requirement forces a contract change.

## Evidence and failure conditions

AGENT digit path: `agent_rack_hero.agent_records` → `surf_agent_hero.project` →
`surf_agent_card_sources.project` → `surf_agent_work.summarize`.
The fold requires complete membership/chain coverage. Membership retention currently
caps at 400 entries for 48 hours, while a seat can have thousands of work records.
The exact distinct-job population and missing oracle-chain coverage must be measured
from the available captured/live payload before choosing bounds.

Oracle metadata uses `SLOT_SWARM_ORACLE_INDEX` and
`SurfManager._pool_swarm_oracle` / `_refresh_oracle_index`. A bounded page read must
retain progress across refreshes; a completed index with unmatched jobs is not proof
of a production chain or a zero count.

Boardroom `fetch_hub_snapshot` offers overview/records/hourly, workers/contributors,
card readers and token/NFT summaries. It does not offer assigned-seat detail.
Offline labels consume cached seat status. `work_activity.observe` seeds idle anchors
from cached own-work timestamps only when the workers reader completes; seat hydration
must refresh this projection even if the workers read completed first.

## Options

| Approach | Benefit | Cost / boundary |
|---|---|---|
| Preserve sufficient historical evidence; resume bounded collection (selected) | Keeps existing lifetime-count meaning and rendering | Bounds must fit measured records; cold complete totals may take several polls |
| Display partial observed counts immediately | Earlier digits | Changes the metric; requires explicit partial semantics and must not masquerade as total |
| Start the full AGENT collector from Boardroom | Reuses existing entry point | Rejected: triggers unrelated earnings, ENS, runtime, record and oracle work |
| Narrow reads for assigned-seat facts (selected) | Resolves cold status/idle data with at most four identities | Requires identity validation, deduplication, retry bounds and activity recomputation |

The current lifecycle spec excludes agent record-page hydration from Boardroom.
This fix permits only the assigned-seat response needed for existing status and own-work
timestamp facts; it does not enable the AGENT enrichment fan-out. If a cheaper authoritative
summary supplies those same facts, reuse it instead.

## Work packages and file ownership

### WP1 — Historical membership completion

Owner: AGENT data implementer. May edit `maxpane_dashboard/data/surf_agent_work.py`,
`maxpane_dashboard/data/surf_agent_card_sources.py`,
`tests/data/test_surf_agent_work.py`, `tests/data/test_surf_agent_card_sources.py`.

1. Measure actual candidate counts before changing retention. Seat #420 has only 75
   distinct non-oracle jobs, so the 400-point cap is not this failure's cause.
2. Add a failing restart regression: missing evidence must precede expired cached
   visible jobs within each fairness turn. Preserve budgets, failure rotation and caps.
3. Exclude oracle jobs only when the complete request index covers all their attempts
   and proves no request exists. Keep unread/ambiguous chain metadata unknown.
4. Prove complete accepted/all-attempt totals through the frozen capture/project path.

Dependency: none. Report any manager integration requirement to WP3; do not edit manager.

### WP2 — Boardroom cold card hydration

Owner: Boardroom implementer. May edit `maxpane_dashboard/data/surf_card_reader.py`,
`maxpane_dashboard/data/surfboard_activity.py`, `tests/data/test_surfboard_seats.py`,
and `tests/data/test_surfboard_activity.py`.

1. Trace every visible Boardroom field against its offer path; retain a compact source
   checklist in the implementation handoff. Existing source paths are listed below.
2. Add failing tests for cold assigned seats, duplicate slots, empty slots, reassignment,
   failed reads, last-good retention, workers-first/seat-first completion and navigation.
3. Add only the missing bounded card source work. Fetch each valid assigned identity
   once per eligible refresh; no selected-seat mutation and no AGENT enrichment calls.
4. Refresh activity/status from completed evidence without requiring a detail visit or
   another workers poll. Reuse existing validation and cache helpers where appropriate.

Dependency: none for reader implementation. Send exact integration requirements to WP3.

### WP3 — Manager integration and oracle completeness

Owner: root session, sole owner of `maxpane_dashboard/data/surf_manager.py` and its
manager/oracle lifecycle tests. This prevents overlapping edits to a shared file.

1. Add failing coverage for oracle-chain paging/backfill and retained progress matching
   the observed failure; implement the minimum correction indicated by evidence.
2. Integrate WP2 offers, loading participation, cancellation/drain and cache-only repaint.
   Validate a late response cannot overwrite another token or revive an inactive reader.
3. Compose WP1/WP2 changes through the real manager; verify counts render and all four
   Boardroom slots load without entering AGENT.

Dependencies: oracle investigation can run alongside WP1/WP2; their manager integration
is sequential after the interfaces are agreed. Root also owns any necessary widget,
composing-screen, rule/spec or followup edits.

## Boardroom source checklist

| Card | Existing source path to verify from a cold cache |
|---|---|
| ONCHAIN FEED | `SurfCardReader._feed` → channel items/replies |
| BUILT BY SWARM | overview + hourly source offers |
| WIP | overview + bounded workflow/current-job readers |
| ORACLES | list-only oracle reader + current-job summary |
| POOL4 | verified discovery, card quote and ETH/USD quote |
| FLEET | workers, contributors, canonical records and overview |
| AGENT ×4 | workers/records/activity plus missing assigned-seat status/work evidence |
| TOKENS | catalogue, selected markets and volume summary offers |
| NFTS | bounded catalogue/deployment proof summary offer |

An unavailable provider remains an unavailable source; visiting another screen is not
an acceptable prerequisite. Fix only demonstrated missing dependencies.

## Verification and completion

- TDD per package. Network access is forbidden in tests; external payloads use committed
  fixtures. Mutation proof is required for decoder/concurrency changes using
  `scripts/mutate.py`; restore only the mutation, preserving other work.
- While editing, run focused node IDs. Before completion, run touched test files plus
  composing manager/screen files once, with isolated caches for parallel execution,
  and the fast `guard and not mounts_app` set. No full suite unless requested.
- Root performs a separate keyless live check and renders both views at the owner's
  terminal size before final review. Record observed counts, coverage, completion time
  and any provider limitations; fixture renders alone do not establish this gate.
- One final whole-change reviewer receives the verbatim CLAUDE.md reviewer contract.
  Apply one fix wave and one scoped re-review if production fixes are required.
- Update affected source-boundary documentation and existing followups after the live
  render; file Minor-only findings. Preserve unrelated untracked files and changes.

## Observed result

Live public data on 2026-10-25: seat #420 has 3,421 attempts, 75 distinct non-oracle
jobs and 3,332 distinct oracle-node jobs. The persisted complete request index has
8,811 entries; four old blocked/cancelled jobs have no request. Complete production
counts are LAUNCHES 19 (18 accepted, 94.74%) and ORACLE 3,328 (3,210 accepted, 96.45%).
Three parked workflow links parsed correctly; no decoder or cache-size change was needed.

A separate empty Boardroom cache loaded assigned seats #3, #7, #420 and #650,
including their activity bars, without an AGENT visit. The repeat live sample completed
in 14.38 seconds; the restored-cache AGENT sample completed in 16.74 seconds.
These timings are observations, not latency guarantees. Both production screen renders
were inspected at 149x45. Local evidence is under `/tmp/maxpane-agent-card-review/`.

The source audit also found that ONCHAIN FEED's aggregate SIGNALS footer depended on
the full dashboard's eleven detectors. The owner explicitly selected **Load all 11
detectors**. Preserve the existing metric and supply its inputs from Boardroom.

## WP4 — All eleven Boardroom detectors (owner-selected scope)

Owner: Boardroom implementer for `surf_card_reader.py`, an optional focused
`surf_card_signals.py` helper and `tests/data/test_surfboard_signals.py`; root owns
the projection integration in `surf_manager.py`, composing checks and documentation.

Reuse `_readings` and `_signal_keys`, including persisted baselines and fired-event
ages. Offer only the required inputs: chain state/nonces; matching channel reads;
existing decoded log/activity windows; launchpad decoy/burn/hot-coin evidence; and
one bounded launch list for the swarm detector. Each source keeps its own cadence,
deadline, failure backoff and observation clock. Fast successful inputs publish while
slower history reads continue. Existing card-task cancellation owns all these reads.
Do not call the full dashboard cycle, acquire NFT/seat enrichment, fabricate empty
windows, or turn partial provider responses into eleven known detector states.

Add offline cold-start coverage for every registered detector, changed facts, source
failure, passive projection and cancellation. Verify bounded live acquisition and
the composited SIGNALS footer before the extended final review.

The new all-eleven offline source test passes through the real manager and card
projection. A fresh public-data probe loaded all four assigned seats and ten
detectors in 12.75 seconds. HOT COIN remained unknown through the 64.99-second
sample because its history read exceeded the 12-second deadline; the existing
180-second history failure backoff applies before checkpoint resumption. This
is observed partial coverage, not eleven verified live detector results. No
requests continued after deactivation. The live 149x45 Boardroom render and
source trace are under `/tmp/maxpane-agent-card-review/`.
