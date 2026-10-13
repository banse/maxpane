# Seat activity history recovery

2026-10-13 · Tier 2 · owner request: seat 420 shows full orange less than four
hours after working. Estimated production change under 100 lines.

## Evidence and behavior

The persisted workers observation knows seat 420 is idle but has no observed
busy-to-idle transition. Its cached seat record contains a recent submitted job.
The renderer currently paints unknown idle age as full orange.

Use the newest valid own-work `submittedAt` from existing validated seat records
to seed or advance an idle activity anchor. Preserve a newer observed stop.
Heartbeats, feedback and later acceptance do not reset that anchor. This is a
last-work display, not a claim about the exact execution stop time. Read clocks
still belong to workers; failures and unknown counters cannot establish idle.
No extra requests, polling changes, cache schema changes or layout changes.

Unknown idle age displays a dash. During the first 24 hours, retain at least one
green segment until the window actually expires. The existing orange-to-empty
24–72 hour phase remains unchanged.

## Work packages

The session owns all implementation and tests. Sequential dependencies:

1. Failing regressions for cold idle/recent work, newer work between polls,
   timestamp validation, persistence, unknown rendering and the 24h boundary.
2. Extend the activity observation fold to consume the cached seat slot; wire it
   into the existing workers read; correct the shared meter rendering.
3. Show a live 149×45 boardroom render including seats 3, 7, 420 and 650, then
   mutation proof, touched/composing checks and fast guards.
4. One final review of this scoped change (including the native AGENT meter
   consumer), at most one fix wave and scoped re-review, then local commit.

No task reviews or parallel implementation are needed for this small change.
