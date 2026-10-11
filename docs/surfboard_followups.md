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
