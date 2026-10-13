# WORK IN PROGRESS — sources and mechanics

Research date: 2026-10-13. This is a new body of the existing Surf dashboard,
not a new dashboard registration. The owner requested “design a new dashboard
for work in progress. jobs being worked on” and “and workflows”, selected
proposal 2, and approved the textual mockup before API implementation.

## The question this body answers

Which loaded jobs are executing, which workflow each belongs to, which steps
and seats are working, and what is waiting or blocked? A workflow is a parent
record with contracts and frontend job references. A job detail carries the
actual step graph, assignments, outcomes, dependencies and dispatch notes.

There is no verified completion percentage or promised remaining duration.
`createdAt` means creation time; it is not the time execution began. Accepted
steps are outcomes, not estimates of how much future work remains.

## Verified local architecture

- `data/surf_swarm_client.py`: the existing keyless, allowlisted host pool,
  pacing, failure rotation, `/jobs`, `/jobs/{id}` and `/workflows` readers.
- `data/surf_manager.py`: detached tier lifecycle, cancellation, cached first
  paint and flat widget dispatch. Keep network work out of event handlers.
- `data/surf_cache.py`: last-good slots, tier due times and failure backoff.
- `data/surf_swarm.py`: existing `inflight_rows` chooses only one active node
  per job. It cannot supply this body's complete working-step counts.
- `screens/surf.py`: composed-once bodies and heroes, `open_mode`, return
  context and existing keyboard dispatch. `w` is free in this screen and app.
- `widgets/surf/news_hero.py`: the existing rack card renderer. Reuse its
  inset/digit presentation instead of creating a second card system.
- `docs/imd_swarm_api.md`: existing API documentation; historical observations
  are not current totals.

The generic PM paths `ai/memory-bank/site-setup.md` and `ai/agents/pm.md` do not
exist in this repository. The approved chat mockup and project CLAUDE.md are
the specification. This is Python/Textual, not Laravel, Livewire or a website.

## Keyless reads and their limits

| Read | Available facts | Limit |
|---|---|---|
| `/jobs?limit=100` | id, state, template, objective, blockedReason, createdAt, updatedAt | Recent creation-ordered page, not all executing jobs |
| `/workflows?limit=100` | id, status, objective, failure, contractsJobId, frontendJobId, waitingForHosting, timestamps | Recent creation-ordered page, not all active workflows |
| `/jobs/{id}` | Job facts plus nodes, assignments, attempts, dependencies, verdicts, notes and timestamps | Individual reads; missing/busy responses are not empty jobs |

The parent session captured a public read in
`/tmp/maxpane-work-api/snapshot.json` before implementation. Its 100 jobs
included 90 completed, six blocked and four executing jobs; its 100 workflows
included 72 completed, 26 blocked, one deployment and one cancelled workflow.
These are sample evidence, never runtime constants. Working nodes use state
`working` and observed roles include `implement` and `review`. A verdict can
say accepted while the node is working again; count activity from node state.
Tests use a committed public fixture or synthetic data, never this network.

## Why this body owns a bounded snapshot

The existing live swarm tier reuses `/jobs` behind health-counter gating and
its slot clock can advance without a new list read. The scores tier merges
workflow history: an older active status can remain after the latest page
has moved past it. Neither slot is a fresh global work roster.

Use a dedicated active-only work tier, borrowing the existing client and
cache. Read a new 100-job page and 100-workflow page each due cycle; replace
the snapshot rather than merging active history. Read at most 24 distinct
job details, prioritizing executing jobs, nonblocked unfinished workflow
references and then blocked context. Include unknown referenced jobs as
explicit placeholders in the tree. Never treat an unfetched job as completed,
empty or absent.

The view describes loaded records. A full page, missing detail, capped detail
collection, missing displayed workflow reference or rejected malformed row
makes coverage partial. Pagination is deliberately outside this initial
scope. No count is named as a global swarm total.

## Read and failure semantics

- TTL 60 seconds; failure backoff 120 seconds; active only while WORK is shown.
- Cache a coherent work snapshot only after both list reads succeed. Its read
  clock belongs to that snapshot, conservatively the first read in the batch.
- An ordinary missing detail keeps its job and advertises unknown steps.
- All-host `503 {"error":"busy"}` stops the detail fan-out, preserves the
  entire prior snapshot and backs off. No zero counts or new successful clock.
- Other list failures also preserve last-good without refreshing its clock.
- An unavailable first read displays unknown values, not zero. A successful
  empty read displays zero and a genuine no-work message.
- A failed latest attempt or age greater than 120 seconds marks last-good
  stale. This body carries its own source marker; it adds no degraded group to
  the already constrained global title.

Normalized fields, exact count semantics and the implementation boundary are
frozen in `surf_work_PRD.md` and `surf_work_plan.md`.
