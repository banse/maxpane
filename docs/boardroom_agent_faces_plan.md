# Boardroom agent card faces

Owner-approved layout, 2026-11-11. Tier 2, one root-owned package below 150
production lines; one final review, no intermediate task review.

## Display contract

- A selected agent whose last valid state is NOT ACCEPTING has orange inner
  and outer borders. Its seat digits remain unchanged. The inner footer reads
  `NOT ACCEPTING` in orange. The outer footer is orange `NA` followed by a full
  red bar fitted to the card width. This is a refusal-state indicator, retained
  through refresh failures; it does not represent measured activity. Busy seats
  refusing new assignments continue to show BUSY and their working counts.
- SWARM uses the existing overview's `agents_online` as its central native
  digits, with inner heading `AGENTS` and `working_seats` as `x working` below.
  The count is distinct working seats, consistent with WIP, never the worker
  list length or daemon/job count. Fresh positive work activates the usual green
  frame and digits. Fresh zero is neutral; missing/stale sources retain values
  without claiming current activity. The outer worked-duration footer remains.
- Preserve last valid digits/counts through reloads and accept a genuine zero.
  Do not change source polling, standing precedence, assignments or navigation.

## Implementation and verification

Root owns data/surfboard.py, widgets/surfboard/rack.py and the matching data,
widget and screen fixture tests. Reuse existing card fields and number fitting;
remove the retired fleet inset helpers. Read-only planning sanity check and one
final review use the existing Agency agents. No parallel source edits.

Write failing data and composited-render tests first. Cover NA placement/colors,
full red width-fitted bar, state transitions, actual zero, stale/unknown counts,
large digit fallback, duration footer and unchanged metadata/navigation. Prove
source selection and presentation with focused mutations. Render current public
data at 149x45 before boundary checks and documentation updates; confirm the
143x37 pin and independent boundary samples. Run touched/composing files once,
fast guards and doc pins; compare residual failures with HEAD e9c621af. Finish
the single final review, record followups and commit exact paths locally.

## Verification

- Public live render at 149x45 shown on 2026-11-11 02:10 CET: SWARM 1,053
  online / 17 working, seat 650 orange NOT ACCEPTING and NA/red refusal bar.
  Native seat digits remain neutral. `/tmp/agent-faces-live.{json,svg,png,log}`.
- Eleven boundary samples (110–160 columns, 25–55 rows) passed with the existing
  143x37 pin and scrollbar onsets. `/tmp/agent-faces-sweep.log`.
- Four mutations caught: wrong working-count source, disabled SWARM activity
  colors, wrong NA bar color and an orange border leaking into subsequent states.
  `/tmp/agent-faces-mutations.log`.
- Focused behavior checks: 22 passed, plus both expanded NA cases covering
  digit color, focus, resize, failed refreshes, BUSY/IDLE/OFF and empty reassignment.
- Changed/composing checks: 521 passed initially; one old FLEET-title assertion
  was updated and then passed. The 39 other failures reproduce at unchanged
  e9c621af. Fast guards: 130 passed, one existing CSS-slice failure also reproduced
  at e9c621af. Doc pins: 12 passed. No full suite run.
  Evidence: `/tmp/agent-faces-{composing,baseline}.xml`,
  `/tmp/agent-faces-title-test.log`, `/tmp/agent-faces-{guards,docpins}.log`.
- Final review: Approved, no findings. Ten named checks passed; an independent
  freshness mutation failed the stale/unavailable cases and was restored.
  `/tmp/agent-faces-review-{tests,mutations}.log`. No new follow-up remains.
