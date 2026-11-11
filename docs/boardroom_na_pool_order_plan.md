# NA card styling and POOL4 order

Owner request, 2026-11-11. Tier 2, one root-owned package under 20 production
lines; one final review, no task review.

- Exchange POOL4 and SHIPPED, including keyboard geometry. Top row:
  ONCHAIN FEED, SWARM, WIP, RESEARCH, SHIPPED, POOL4.
- NOT ACCEPTING keeps its orange inner frame/caption and normal outer frame.
  Seat digits use the same green as active cards. The outer footer is muted
  gray NA and an entirely empty segmented track, with no red filled segments.
- Retain the current footer sources, counts, destinations and source clocks.
  Preserve NA on a failed refresh and normal transitions to BUSY/IDLE/OFF.

Update existing composited regressions first, then implement the bounded rack
change. Show live 149x45 output before boundary checks and documentation. Check
the existing 143x37 pin, mutation witnesses, touched/composing files once and
guards/doc pins. Compare residual failures with c0a773a6. One final review and
local commit; no polling or data changes.

## Verification

- Both initial regression cases failed before implementation. Four focused
  presence/navigation cases pass after it. Three mutations were caught and
  restored: colored filled NA track, white NA digits and wrong POOL4 column.
- Public live 149x45 render shown with seat 650 in the requested styling and
  POOL4 at the right edge. `/tmp/boardroom-na-order-live.{json,svg,png}`.
- Eleven boundary samples retain 143x37 and existing scrollbar onsets, with
  no clipped cards. `/tmp/boardroom-na-order-sweep.log`.
- One composing run: 151 passed, 40 failed. One full-POOL4-face assertion still
  used a 140-column viewport, which crops the card's new far-right location.
  It now uses the existing minimum fitting 143x37; both POOL4 cases pass.
  All other 39 failures reproduce at unchanged c0a773a6. Fast guards: 130 passed,
  one known TOKENS/SWORN CSS-slice failure also reproduced. Doc pins: 12 passed.
  Exact results: `/tmp/boardroom-na-order-{composing,baseline,guards}.xml`.
- Final review Approved, no findings. Seven named cases passed. Independent
  mutation suppressing NA on a stale refresh failed both presence cases and was
  restored byte-for-byte. `/tmp/boardroom-na-review-{tests,mutations}.log`.
