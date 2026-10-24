# WIP recent activity and shared workflow loading

Owner request, 2026-10-24: compare WIP with BUILT BY SWARM, show all jobs and
workflows active within the last 24 hours, and paint completed tasks dark green.
The owner confirmed that an older record updated today belongs in this window.

## Contract and behavior

- Default WIP filter is `24h`: all statuses, latest valid updated/created activity
  within the inclusive rolling 24-hour window, using the injected snapshot clock.
  Records without a usable timestamp cannot establish recent activity.
- Keep the existing Open, Blocked, Build and Review filters for older active work
  and project context. Project parents may group recent workflows; missing or old
  children do not become recent merely through a relationship. Detail panels keep
  their full linked context. Each job appears once.
- Completed workflows, completed jobs and accepted steps use dim theme foreground,
  matching the dark-green BOARDROOM middle text. Executing work keeps its bright accent.
- Hero metrics keep their existing active/current meanings, independently of the
  selected list filter. No public payload keys or layout pins change.
- WIP and BUILT BY SWARM reuse one certified workflow catalogue/checkpoint,
  preserving the all-history catalogue needed by BUILT BY SWARM. Updated-at
  deltas, pagination, reconciliation and partial-source clocks remain truthful.
- WIP retains old-created/recently-updated jobs, including a bounded activity
  catch-up on cold discovery. Recently completed job details enter the existing
  bounded optional enrichment after active work. View handlers perform no I/O.
- Preserve single-flight polling, cancellation, last-good snapshots and source
  `None` semantics. No credentials, mutations or new external sources.

## Packages and sequence

Estimated under 500 production lines; one final whole-diff review.

1. Agency architect: data readers/catalogue, minimal manager delegation and data
   regressions. Owns `data/surf_work*.py`, affected `surf_manager.py` sections and
   associated data tests. Cold/warm/view-switch request counts and optional
   enrichment are checked offline, with bounded live timing outside tests.
2. Session: shared pure activity helper, WIP widget/filter and painted tests.
   Owns `analytics/surf_work.py`, `widgets/surf/work.py`, their tests and docs.
   Independent from package 1 except the shared helper contract above.
3. Session: live keyless render at 149x45; touched/composing tests, guards/docpins,
   final Agency review and local commit. No full repository suite or push.

Regression evidence covers cutoff boundaries, updated old records, unknown
timestamps, blocked/failed/completed visibility, retained context filters,
selection/deduplication, painted completion color, shared checkpoint reuse,
failed partial scans, cancellation and bounded completed-job hydration.
