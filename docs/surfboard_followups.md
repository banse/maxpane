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

## Launchpad volume and reduced chrome — 2026-10-11

PROTOCOL now has aligned label/amount/IMD columns and a blank inset footer.
Both launch volume charts use SWARM's green; degraded labels retain their amber
prefix. The focused detail row is removed and the terminal fills its direct
central span. This supersedes the wrapping-detail presentation above.

LAUNCHPAD uses eight closed UTC 15-minute buckets, exact block timestamps, and
uncapped CurveSwap ETH quote amounts across the complete pool population. USD
values use the fresh current ETH/USD quote, not historical execution prices.
The existing read-only state RPC hydrates at most 256 event-block headers plus
two boundaries within 20 seconds. Missing headers, malformed identities,
unknown pools, or exhausted coverage budget yield unavailable data. Factory
count mismatch yields partial without a complete chart. Snapshot clocks and
window end remain independent of the launchpad slot's timestamp.

Live keyless preview shown at 149×45 with complete 210/210-pool coverage and a
nonzero two-hour chart. LAUNCHES volume was unavailable on this refresh and
rendered a dash. Composited checks cover green fresh/partial/stale charts.
Measured layout remains 144×35; terminal widths are 94 at the pin and 97 at the
owner's size, with its bottom aligned to BAY 11/12.

Verification: 981 affected/composing cases green across coordinated passes;
124 guards and 12 docpins. Seven data/clock mutants rejected: inadequate time
coverage, open interval inclusion, conflicting event identity, header budget,
unknown pools, stale USD quote, and expired quarter window. The broader run's
five failures were outdated model/transport test doubles; their full 438-case
client/model/manager rerun passed after test-only updates. No full-suite run.

Final review: Approved, no Critical or Important findings. The reviewer ran
29 focused checks and rejected an additional wrong-quote-leg mutation; all
files were restored byte-for-byte. No outstanding findings for this change.

## ONCHAIN NEWS hero mockup — 2026-10-12

Proposal 3 is available as the standalone six-card Textual demo in
`scripts/surf_news_hero_demo.py`, with fictional records and no API connection.
Owner review of the 149×45 preview precedes production/live-data integration.
Final review approved; three mockup tests, 124 guards and 12 docpins passed with
`NO_COLOR` unset, and two geometry mutants were rejected.

Closed during live integration: the mockup test fixture now clears inherited
`NO_COLOR`, so its accent assertions exercise the intended palette.

## ONCHAIN NEWS live heroes — 2026-10-12

The approved six-card hero is connected to existing cache/API reads in the
default NEWS body. LAUNCHPAD and protocol retain their existing hero. Announcement
and community reply previews use the full cached channel independently of the
25-row feed window. Each card retains its source clock and distinguishes missing,
empty and real-zero data. Market freshness includes both the selected pool price
and its USD conversion source. No new API requests or cache slots were added.

Live keyless preview shown at 149×45. The upstream activity page limit and an
older pool-price observation appeared explicitly as stale. The six cards are
nine rows each; measured default width remains 143. The mixed-payload height
measurement moves from 39 to 41: at 39/40 all fixed content is visible but the
rail scrolls; 41/42/43 have no scrolling or taller marker. At 37/38 the missing
activity rows remain advertised by the taller marker.

Final review approved after one fix wave: a genuine zero USD conversion now
preserves the native onchain-price selection, and the models declare every hero
section and activity-row field. Both regressions were observed failing before
their fixes. Eight source/zero/layout/dispatch mutations were rejected and restored.

Validation: the closing affected/composing run passed 609 cases; the remaining
137 affected cases passed in the preceding coordinated run. Also passed: 124
guards, 12 docpins, five address sweeps and the full-outage app check. No full
suite run. No outstanding review findings for this integration.
