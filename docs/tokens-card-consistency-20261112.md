# Token card consistency and spacing — 2026-11-12

Tier 2, expected below 250 production lines. Root owns implementation; the
planning agent audits numerical provenance. One final review for the complete diff.

The cards and summary rankings must describe the same selected token cohort as
ALL TOKENS. Retain valid cached observations during refresh and expose their real
successful read clocks/source state; never record unknown liquidity as a measured
zero. Keep the existing card display fallbacks.
Validate all six cards, network identity and known-value coverage. Keep source
fetching bounded and preserve filters, token navigation and current card styling.

TOP TRADED and NEWLY LAUNCHED should display a scrollbar only when content
actually overflows. Remove the extra row before ALL TOKENS and reserve that row
below its table, leaving one blank line before the status/footer row. Preserve
all table rows and internal scrolling.

Plan: reproduce data and compositor faults with focused failing tests; fix pure
projections/presentation and the two mirrored CSS blocks; show a keyless live
149x45 render; measure layout boundaries in situ; run touched/composing tests,
mutation proof and guards; final review; local commit and IMD capture.

Implementation responsibilities: the agent owns the parent liquidity bridge and
its new offline tests; root owns projection, token polling, widgets and spacing.
The parent reuses provenance receipts, reads at most three selected pools and
merges only still-current catalogue identities. Normal active polling revisits
known swarm tokens with missing/stale liquidity; passive snapshots remain passive.

Live acceptance at 149x45 used public keyless endpoints and copies of operator
caches. The retained snapshot at 20:49 local reconciled 533 tokens across three
chains, two new launches, $6,350.64 from 12 observed volumes, 7 rising / 4 falling
prices, and 130 two-sided / 398 one-sided / 5 unknown pools. IMD and ETH totals
remain separate: 17,205.4312 IMD and 13.5066 ETH, 506/533 supported observations.
These totals combine successful observations of different ages; most liquidity
reads were older cached values, not newly verified balances. Source states and
original clocks remain stale until each bounded refresh succeeds.

The 145/146/147-column and 33/34/35-row boundary sweep passed without moving pins.
Six functional mutations were killed, plus the parent's catalogue-identity guard
mutation. Removing the theme margin alone survived because DEFAULT_CSS intentionally
provides the same property; explicitly setting the margin to zero killed the test.

Final targeted verification: 217 passed; three failures reproduced unchanged on
HEAD 57e7bbc5 are recorded in swarm_tokens_followups.md. The fast guard set passed
131 cases; documentation pins passed 12. No full-suite run or push. IMDb capture
recorded `none`: this fix adds no new protocol knowledge.

Final review: Approved, no blocking findings. Eight focused checks passed;
the catalogue-identity mutation was independently killed and restored. No new
review follow-ups or production fix wave were needed.
