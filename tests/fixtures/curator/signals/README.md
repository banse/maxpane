# WP3's own slices — `tests/fixtures/curator/signals/`

The real payloads live in `../captures/` and are read directly; nothing is
copied here, because a second copy of a capture is a second thing to keep true.

What lives here instead is the handful of **states the chain has not reached
yet**, hand-built so the analytics layer can be tested against them before
they exist:

| file | state | replace with |
|---|---|---|
| `readings_judged_deficit.json` | a post-grace judged hour running a live deficit (`earlyBps` flat at 10 000, `ethNeededThisHour() > 0`) | capture **B** — first window 2026-08-17 19:58:47 UTC |
| `readings_settled.json` | `isSettled() == true`, the latch filled, the obituary log seen | capture **C** — earliest window 2026-08-17 20:58:47 UTC, one-shot |

Both carry the literal marker

    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>

in their `_synthetic` field, so `rg "SYNTHETIC — re-point"` finds them along
with the marked comments in `tests/analytics/test_curator_signals.py`.

Every number in them is calibrated to the real deployment (`launchTime`
1786910327, `hourlyThreshold` 5e18, `creditCap` 1e21, `firstJudgedHour` 24,
`POINTS_PER_ETH` 1000) so re-pointing them at a real bundle changes the
provenance, not the arithmetic.
