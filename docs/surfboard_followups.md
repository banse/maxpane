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

## SWARM hero mockup — 2026-10-12

Proposal 2 is available in `scripts/surf_swarm_hero_demo.py`: FLEET, OUTPUT,
WORKFLOWS, LAUNCHES, LATEST WORKFLOW and SITES. The standalone demo reuses the
existing rack renderer above the native SWARM tables. All figures and records
are fictional, with visible MOCK DATA labels; production data and screens are
unchanged. Owner feedback on the 149×45 preview precedes API integration.

The six cards share a nine-row height. Narrow terminals scroll to retain every
card. Six mockup/composing tests passed, and both deliberate layout regressions
(wrapping the cards and removing the narrow-screen width floor) were detected
by their named tests and restored byte-for-byte.

Final review approved with no findings. The 124 fast guards and 12 docpins also
passed. No full suite run.

## SWARM live rack heroes — 2026-10-12

The approved six-card overview now receives `surf_swarm_hero` through native
SWARM dispatch. FLEET and OUTPUT use the overview; OUTPUT's accepted-step chart
has its own hourly clock. Cached workflows, production launches and current
named sites retain their independent successful-read times. Empty collections,
unavailable fields and stale last-good observations remain distinct. Native
SWARM visibility enables the existing hourly scheduler; no new endpoint or
parallel poller was introduced. The previous hero is parked.

The 149×45 keyless live preview was shown before layout hardening. It displayed
977 online / 9 working, 2,501 accepted steps, 157 cached workflows, 219 cached
production launches and 68 named sites. The older sites observation was marked
stale. API-derived workflow status and objective came from the same record.

All five SWARM layout payloads measure 141×38. LATEST WORKFLOW's outer title
is ellipsised at 140 columns, while 141/142 are whole. The body scrolls with a
taller marker at 37 rows and clears from 38; the four contextual panels retain
their existing floors and tiers. The six larger hero cards add three rows.
Six data/source/scheduler mutants and four two-sided width/height mutants were
rejected and restored byte-for-byte.

Final review: Approved, no findings; seven additional named checks passed.
Validation covered 1,582 affected/composing cases across the closing run and
the two corrected screen-file reruns, plus all 86 registration cases. The
corrections replace the old SWARM geometry, the pre-rack default rail boundary
(now measured whole from 45 rows), and the retired hero's title assumptions.
Also passed: 124 fast guards, 12 docpins and two SWARM address sweeps. No full
suite run and no outstanding findings for this integration.

## LAUNCHES hero mockup — 2026-10-12

Proposal 1 is available in `scripts/surf_launches_hero_demo.py`: TOKENS, VOLUME,
LIQUIDITY, POOLS, MOMENTUM and TOP VOLUME. It reuses the existing rack renderer
above native token panels. The fixed fictional 48-token snapshot agrees with the
hero totals, coverage and leaders. VOLUME uses native Digits with an explicit
`kUSD / 24H` scale; paired IMD and ETH amounts stay separate and retain the
partial-coverage marker. The frame and export are visibly marked MOCK DATA.

The 149×45 Textual preview was exported, inspected and shown to the owner.
All cards share nine-row geometry; smaller terminals expose scrolling and retain
every card. No production screen, source, cache, configuration or layout pin
changed. Owner feedback precedes API integration, following the requested loop.

Validation: 21 mockup/native-screen cases, 124 fast guards and 12 docpins passed.
Both deliberate layout regressions (wrapped heroes and a removed width floor)
were detected by named compositor tests and restored byte-for-byte. No full suite.
Final review approved with no findings.

## LAUNCHES live rack heroes — 2026-10-12

The approved six-card row now receives `tokens_hero` from the existing live
provider through the native filtered projection. TOKENS uses the catalogue;
VOLUME, MOMENTUM and TOP VOLUME use eligible market observations; LIQUIDITY and
POOLS use their own liquidity observations. Coverage and oldest contributing
read clocks stay separate, stale quotes do not enter fresh totals, and known
zero/empty selections remain distinct from unavailable data. No endpoint,
scheduler, cache format or configuration write was added.

The keyless 149×45 live preview was shown before layout hardening. It displayed
164 selected tokens, 29 new within 24 hours, and $1.565M measured volume with
39/164 coverage. Paired liquidity was at least 4.3k IMD and 4.798 ETH, with
79/164 coverage. Partial source footers use orange and the dashboard's local
time. USD scaling is explicit and small nonzero figures retain precision.

The six equal nine-row cards measure 146×34 in the native layout. The 143-column
body floor is unchanged; the old 145-column pin missed one clipped frame column
at the reserved scrollbar gutter. Chrome now detects actual scroll extent,
including this case when Textual's scrollbar flag is false. Width 145 marks;
146/147 show all frames. Height 33 marks; 34/35 fit. The 24 fixture rows remain
internally scrollable. Six data/source mutants and five geometry/marker mutants
were rejected and restored byte-for-byte.

Validation: 136 affected/composing cases, 124 fast guards, 12 docpins and three
focused native dispatch/address cases passed. Final review approved with no
findings after eight additional named checks. No full suite run or outstanding
findings for this integration.

## POOL4 hero mockup — 2026-10-12

Proposal 1 is available in `scripts/surf_pool4_hero_demo.py`: IMD PRICE,
sIMD RATE, STAKING, VAULT, DOWNSIDE BID and DRIP QUEUE. The standalone Textual
app reuses the unchanged rack renderer above the native market panels. All
figures and holder addresses are fictional, with visible MOCK DATA labels in
the frame and exported preview. Vault assets/shares, holder totals, queue days
and the deployed bid reconcile across the hero and body. STAKING explicitly
labels annualised APR from the trailing seven days; the queue's daily figure
is a delivery cap.

The 149×45 preview was exported, visually inspected and shown to the owner.
Six cards share a nine-row baseline, and smaller terminals scroll to retain
every card. No production data source, cache, configuration, screen, shared
widget or layout pin changed. API integration follows owner feedback in the
requested mockup workflow.

Validation: three compositor/data cases, 124 fast guards and 12 docpins passed.
Both deliberate geometry regressions were detected by named tests and restored
byte-for-byte. Final review approved with no findings. No full suite run.
