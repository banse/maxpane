# Boardroom agent presence correction

Authorized by the owner's 2026-11-11 request to fix agent card status. Tier 2;
one root-owned package, expected below 250 production lines. One final review,
no task review. Reuse IMDb and terminal-layout guidance; no Superpowers.

## Contract

Selected-seat standing is authoritative for presence and dispatch readiness.
A fresh disconnected or stale-heartbeat observation proves OFF. A connected,
nonstale seat with positive working count is BUSY, even while refusing new work
(the refusal remains in its tooltip). Connected, zero-working, accepting=false
shows NOT ACCEPTING in amber with its observed slot counts. Connected and
accepting with zero assignments is IDLE. Enrollment status is not runtime status.
Missing worker-list rows never prove OFF on Boardroom cards.

Keep copied last-good standing per selected identity and original observation
time; failed, malformed, cancelled or old responses never overwrite it. Positive
fresh worker evidence may fill in while standing is missing/stale. Otherwise
retain observed quantities/state without painting a live activity bar. An aged
standing read is not itself evidence that the heartbeat is stale.

## Implementation

1. Root: independent `presence:<token>` tasks in SurfCardReader, at most four
   unique seats, 60-second retry/refresh spacing even under force. Validate
   identity, source timestamp, booleans and integer counts. No cache-format or
   shared model change; no hidden AGENT enrichment fan-out.
2. Root: synchronous retirement in SurfManager.set_hub_seats with per-token
   epochs, cancellation and old-result rejection, including remove/re-add races.
   Project the copied presence facts into the existing internal agent_seats rows.
3. Root: Boardroom-only status/slot projection in surfboard.cards; preserve the
   existing history anchor calculation. Remove enrollment text as offline state.
   Add amber NOT ACCEPTING footer in the rack, and suppress live activity bars
   when only retained standing is available.
4. Root: fixture-backed decoder, reader, race, budget, projection and composited
   widget checks. Update superseded convention in .claude/rules/surf.md.

## Verification sequence

Write failing tests first. Mutation proof covers false OFF, wrong identity,
expired/failed evidence clocks, forced-read throttling and retired request ABA.
Show public-data rendering at 149x45 before boundary certification/docs evidence
or review; check NOT ACCEPTING at 143x37 and independent boundary samples.
Run changed/composing files once, fast guards and doc pins, compare failures with
unchanged HEAD c8d3d4bf. Existing baseline failures are in surfboard_followups.md.
One final review, bounded fix wave if needed, commit exact paths locally.

## Verification evidence

- Public standing captured at 00:26 UTC on 2026-11-11: seat 650 was connected,
  nonstale, not accepting work, with 0 working / 1 capacity. Worker-list absence
  and enrollment `active` did not describe that runtime state.
- Live 149x45 render at 01:39 CET showed 650 as `0 of 1` / `NOT ACCEPTING` in
  amber; seats 3, 7 and 420 retained `0 of 3`, `0 of 4` and `0 of 3` / IDLE.
  Eleven independent boundary samples passed; the 143x37 pin is unchanged.
- All 22 new reader/projection/composited checks passed. Seven deliberately
  broken implementations were caught, including wrong identity, forced retry,
  ABA publication, failed-read clock advancement and a retained busy live bar.
- Changed/composing run: 653 passed initially; three older tests were updated
  to supply positive worker evidence or expect unknown on absence, then passed.
  The other 57 failures reproduce at unchanged `c8d3d4bf`. Fast guards: 130
  passed, one existing TOKENS/SWORN CSS-slice failure reproduced at that commit.
  Doc pins: 12 passed. No full suite was run.
- Temporary evidence: `/tmp/seat-presence-live.{json,svg,png,log}`,
  `/tmp/seat-presence-sweep.log`, `/tmp/seat-presence-mutations.log`,
  `/tmp/seat-presence-identity-mutation.log`, `/tmp/seat-presence-composing.xml`,
  `/tmp/seat-presence-baseline.xml` and `/tmp/seat-presence-contract-tests.log`.
- Final review found one transition issue: fresh standing IDLE without a usable
  activity anchor could retain the prior BUSY footer. The fix explicitly paints
  a gray IDLE label without a history bar until history is available. The new
  composited busy-to-idle assertion failed before the fix; all 24 focused
  presence/render/history checks pass afterward (`/tmp/seat-presence-idle-fix.log`).
- Scoped re-review verified the finding ADDRESSED at both terminal sizes. Its
  inverse mutation fails both cases; files were restored byte for byte. Evidence:
  `/tmp/seat-presence-idle-rereview-{tests,mutation}.log`. No new follow-up remains.
