# Surfboard follow-ups

## LAUNCHES latest-token inset — 2026-10-11

No outstanding review findings. Final review approved the latest-three launch
rows, cached liquidity indicators, and retained footer/layout behavior.

## Card activity and footer updates — 2026-10-11

Final review approved: no Critical or Important findings. Per the repository's
Minor-only review rule, defer these wording corrections to the next relevant edit:

- The [activity spec](surfboard_card_activity_spec.md) describes coverage counts
  after pool deduplication. The implemented counts describe token deployments;
  USD volume sums deduplicate shared chain/pool identities.
- The [implementation plan](surfboard_card_activity_plan.md) says orange BUSY
  labels and fill. The requested behavior uses an orange BUSY label with the
  existing green progress bar; IDLE is green.

Verified live at 149×45, including a partial USD volume sparkline, protocol
columns, idle labels, blank zero-news footer, and the live sIMD share rate.
Full content fits at 144×36. Final scoped verification: 937 tests, 124 guards,
12 documentation checks; 19 additional focused review checks passed.

## Offline status and terminal detail layout — 2026-10-11

AGENT and LEADERBOARD now show red OFF with hollow tracks only for fresh,
confirmed offline observations. Their insets share working/idle/offline colors;
the existing green-to-orange idle decay and its history remain unchanged.
Focused details wrap beneath the terminal at matching width. PORTFOLIO and AGENT
have exchanged positions, and BAY 10 replaces EARNINGS.

Live keyless preview shown at 149×45. Measured layout: 144×35; long details scroll
inside the center. Final review found the old terminal floor could hide the market
footer; the 12-row floor and a failing-then-passing compositor regression address
it. Scoped re-review: ADDRESSED. No outstanding findings for this change.

Verification: 448 affected/composing tests green across coordinated passes,
including 188 terminal/rack/layout/screen cases after the floor correction;
124 guards and 12 docpins. Freshness-gate mutation and both sides of the width
and height pins were rejected. No full suite run.
