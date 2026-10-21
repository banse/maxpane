# Surfboard follow-ups

## POOL4 discovery segment removed — 2026-10-16

HATCHES now starts with its contract addresses. The discovery verdict, detail,
source and citation warnings are removed from display; discovery and validation
in the data layer are unchanged. A public live render at 149×45 was shown before
the four-payload height sweep. The full-layout height is now 44 rows (was 47),
with the 138-column width unchanged. Contract copy links and all levers remain.

Validation: 248 affected/composing checks, 125 fast guards, 12 documentation
pins and both Surf address sweeps passed. Three other assertions fail identically
on clean pre-change commit b24b429b: the old Surf binding list, generic launchpad
hero visibility, and the STAKERS 40-character address expectation. No full suite
was run. Three implementation mutations and the reviewer's unread/empty mutation
were rejected and restored. Review: Approved.

Minor follow-up: the terminal-layout skill's POOL4 table and row-record paragraph
still quote 47 rows. Update them to the current 44-row measurement when that
skill is next edited; the source pin and Surf rules already record the new size.

## Selected-token dashboard — 2026-10-15

Option 2 is implemented: six native cards above launch/contributors and
market/position panels, with full-width artifacts below. Click or Enter from
SWARM TOKENS opens the selected identity; Escape retains list selection and
filters. Independent source clocks, bounded proven launch/job/site joins and
owned-task cancellation preserve the existing keyless, read-only behavior.

Live MEDICI/BLACKOUT renders were shown at 149×45 before hardening. The new
146×44 pin and both neighboring dimensions pass complete/degraded composites.
Final affected/composing checks: 181 passed, with only the same three baseline
address failures documented below (old Surf pin list and both Portfolio wide
coverage cases). The new detail and overview-to-detail address sweeps pass.
Also passed: 125 fast guards, 80 registration checks, 12 documentation pins
and the new screen's panel-dispatch agreement. No full suite was run.

Sixteen mutation witnesses were killed and restored. Final review identified
one wrong-number issue: partial contributor counts lost their lower-bound
marker when stale. The fix retains coverage separately from freshness; aging,
failed reads and recovery regressions pass. Scoped re-review: ADDRESSED.
No new unresolved feature findings.

## SHIPPED RECENTLY — 2026-10-15

BUILT BY SWARM now puts LAUNCHES beside a plain five-item age/name/type list,
with full-width WORKFLOWS below. Parked reason stays in launch detail only.
Tokens, named contracts and current published sites merge newest-first;
confirmed testnet entries and token helper artifacts are excluded. Publication
uses retained namedAt; approximate API update/request ages carry a tilde.
Existing caches gain site timestamps on their next normal site refresh.

Live public renders were shown at 149×45 before boundary hardening, including
fresh site publication data and the final green linked names. The existing
141×38 minimum holds across five payloads; WORKFLOWS reaches full columns at
72 and LAUNCHES at 203. The latter keeps liquidity from 138 and hides no
column from 124 at the row pin. Name copy links and the independent x shortcut
remain intact. Data/widget/layout mutations (13) all failed their named tests.

Validation: 176 data checks and 127 guards/docpins passed. The broader 850-case
UI/address run passed 845 initially; the obsolete column-count assertion and
wide-address coverage setup were corrected and their containing/table or
named address cases passed (49 and 3 checks). Three unrelated address-suite
failures reproduce unchanged on HEAD 9d50e8e5: the old Surf pin-list assertion
and portfolio/portfolio_live wide sweeps whose TokensHeroCard has no icon.
They are existing debt, outside this feature.

Final review approved; its publication-time mutation was killed and restored.
Minor review follow-up: at very narrow widths the list omits type, but the
row tooltip currently includes the name and timing only. Add type to the
hover text when swarm_latest.py is next touched; normal 46-column rows show
all three columns.

## Inactive numeric readouts — 2026-10-15

Inactive digits with neutral inset borders again use each card's normal white
text color across Surf and boardroom views. Active green digits, red-frame
orange digits, other colored frames, stat values, labels and captions keep
their existing colors. The live 149×45 boardroom render shows the restored
inactive white readout. Geometry and layout boundaries are unchanged.
All 462 affected widget/composing checks and 127 guards/docpins passed. Removing
the restored text color failed 11 regression cases; final review approved.

## Red-frame numeric readouts — 2026-10-15

Red inset borders now use orange digits in all Surf and boardroom cards,
including custom Agent STATUS readouts. Symbolic ANSI red and resolved theme
RGB red share the rule. Other body colors, frame colors, captions and geometry
retain their existing behavior. The live public-source WORK view at 149×45
shows the red BLOCKED card with orange digits. The seven composited red-frame
checks reject removing the orange override.
All 424 affected widget/composing checks and 127 guards/docpins passed. The
single review approved the change; no geometry or layout pins moved.

## Shared card inner styling — 2026-10-15

All mounted Surf and boardroom card bodies share label/value/digit colors and
one-cell text-edge padding; frames and captions retain their state colors.
Live public-source renders were checked at 149×45 for boardroom and every Surf
mode. The boardroom stress composite remains whole from 143×37, with unchanged
column geometry. Narrow text uses short labels while keeping complete values.
Protocol's fitted short labels make CHECKS the new 138-column boundary; the
market stays at 148, Swarm at 141 and Agent at 132. The Surf address sweep passes.
Launchpad retains 138 columns using shorter exact counts and a reversible
`sendable`/`ready` label; Agent keeps full runtime versions and STATUS counts.

Final affected/composing checks passed: 385 Agent, 178 Launchpad, 159 market
layout, 96 default Surf, and 303 boardroom/protocol/layout cases. The other
affected widget and screen cases passed in the broader integration run; its
new failures were resolved in these focused reruns. All 127 selected guards and
docpins passed. Six deliberate regressions were rejected: inactive-digit color,
edge padding, warning-frame color, both adjacent protocol pins, and owner rich
address spans. Scoped review approved both narrow-layout fixes. No full suite
was run; the existing failures below remain outside this change.

Existing test debt, reproduced on untouched HEAD 191216cc: twelve cases in
`tests/widgets/test_surfboard_card_activity.py` still expect the retired FLEET
activity meter/status colors, pre-centered footer widths, or visible unavailable
subtitles. Its eight remaining cases pass. Update those expectations when that
footer behavior is next changed; this styling change does not alter the footers.
Four composing checks also fail on that unchanged baseline: the two hero-routing
checks in `test_surf_pool4_market_screen.py` still expect the parked `SurfHero`
for Launchpad, and `test_surf_pool4_screen.py` retains the old binding/body
expectations. Keep these separate from the padded card layout checks.

## Seat activity recovery — 2026-10-13

Seat 420's cold idle observation had no stop timestamp and was incorrectly
rendered full orange despite recent recorded work. Existing cached own-work
submissions now seed or advance idle history on the next workers read. Unknown
age renders a dash; the last green segment remains until 24h. No extra API reads
or layout changes. Cached submissions are validated individually before selecting
the latest, so a future-dated row cannot hide valid recent work.

Live keyless 149×45 render verified seat 420 with about 20h green remaining.
544 affected/composing tests, 124 guards and 12 docpins passed; after the review's
timestamp correction, all 177 affected data/manager tests passed. Four regression
mutations and the review's monotonic-history mutation were rejected. No full suite
run. Existing unknown history remains explicitly unknown when no cached own-work
record or observed transition is available.
Scoped re-review approved the timestamp correction; both mixed-validity cases
rejected removal of per-submission validation. No outstanding review findings.

## Boardroom card tones and consecutive price reads — 2026-10-13

IMD BOARDROOM uses its former muted title color; ONCHAIN FEED has a white active
inset and SWARM BUILDS keeps its activity colors. PROTOCOL has a neutral inset and
centered burned-supply footer; empty AGENT seats center Identity.md. POOL4 compares
successive confirmed USD prices, retaining direction across repaints and resetting
on equal reads or pool identity changes. Failed reads do not replace the baseline.

Live keyless render shown at 149×45. Existing 144×35 layout boundaries and one-line
caption gaps remain unchanged. Verification: 449 affected/composing tests, 124 guards,
12 docpins and eight mutation checks passed. Final review approved without findings;
six focused review cases passed and a cross-pool comparison mutation was rejected.
No outstanding findings; no full suite run.

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


## Rack content refresh — 2026-10-13

Implemented the owner's TOKENS arrows/newest footer/24h count, TOP AGENTS medal
rows, supply-burn sentence, empty-seat prompt/NFT footer, and Katakana side captions.
The terminal no longer paints stale qualifiers or V/P/D flags; generated status
and seat replies retain read times without stale labels. Metadata and literal
third-party prose remain intact. Consecutive-load price comparison is unchanged.

Live keyless preview was shown at 149×45 before hardening. The protocol footer
needs a wider column; all cards retain equal heights and the terminal retains its
full vertical span. Exact measurements live beside the screen pins. Large accepted
counts shed comma separators before clipping; ordinary counts retain them.

Regression checks cover the card/data contract, canonical rank order, 24h count
provenance, terminal variants, empty inputs, caption geometry and address links.
Four deliberate data/layout mutations were rejected and restored byte-for-byte.
The full repository suite was not run. Final review findings are recorded below.

Validation: 645 affected/composing tests, 124 fast guards, 12 docpins and two
address checks passed. Final review: Approved, no findings; 17 focused cases
passed and an explorer-link mutation was rejected and restored. No outstanding
findings for this refresh.


## Rack sizing and captions correction — 2026-10-13

Owner shortened the protocol footer to `x% burned`. All six columns again use
equal fractional widths, with only terminal-cell rounding differences. Both
Katakana captions use the card background color and occupy the lower middle
spare row, moving down one line at 149×45. Card heights and the terminal span
are unchanged. The live keyless preview was shown before remeasuring the layout;
the screen pin and its measurement block document the restored geometry.

Validation: 210 affected/composing tests, 124 fast guards and 12 docpins passed.
Five layout/behavior mutants were rejected and restored. Final review approved
with no findings; six focused cases passed and both width-pin mutations failed
as intended. No full suite run or outstanding findings.


## IMD boardroom rack polish — 2026-10-13

Implemented the owner request: centered green IMD BOARDROOM heading, bold surface-color
Katakana captions, borderless `seat number` placeholders and `Identity.md` footers,
blank unchanged/unknown price indicators, and padded medal rows with accepted counts
right-aligned. Oversized counts compact only when needed; equal card widths and pins
remain unchanged. TOKENS restores gray `24h` and the existing all-status USD-volume
history, independent of its last-24h top-three ranking. Polling schedules the existing
bounded volume reader alongside shared markets, preserving selected-pool identity.

Fresh keyless render shown at 149×45 before final hardening. The final live snapshot
had partial volume coverage (2/349 candidates), with four measured three-hour buckets
and four gaps; source coverage remains explicit in the tooltip. A direct selected-pool
read for SNITCH returned HTTP 200 and 13 known completed hourly candles. No history
was fabricated or substituted from rolling 24h quote snapshots.

Nine deliberate regression mutants were rejected and restored. Final validation and
review are recorded in the commit. No new endpoints, contract fields, or layout pins.

Validation: 528 affected/composing tests, 124 guards and 12 docpins passed.
Final review approved with no findings after 13 focused checks and a further
gap-to-zero mutation was rejected and restored. No full suite or open findings.


## Side captions between cards — 2026-10-13

LAUNCHPAD and PORTFOLIO now have three rows before their AGENT cards. キープ and
ビルディング occupy the middle row, retaining bold card-surface-colored text.
Other gaps remain one row. The terminal still fills its center span, and all
cards retain equal dimensions. At 149×45, the two added rows consume the former
spare space at the bottom; card and terminal sizes remain unchanged.

Fresh keyless live render shown at 149×45. In-situ normal/stress/unavailable/wide
probes measured the unchanged 144-column minimum and a 37-row height minimum,
up from 35. No clipping at either the new minimum or the owner size.

Validation: 165 affected/composing tests, 124 guards and 12 docpins passed.
Four mutations were rejected, including the row pin in both directions.
Review approved with no findings after five focused cases and a further
caption-placement mutation. No full suite or outstanding findings.


## One-line side captions — 2026-10-13

Owner revision: reduce the gaps below LAUNCHPAD and PORTFOLIO to one line,
retaining the centered bold キープ / ビルディング in those lines. Other styling,
equal card sizes and the full-height center terminal are preserved.

Fresh keyless 149×45 preview shown. Four-payload in-situ checks restored the
144×35 minimum without clipping; all card gaps are one line across resizing.
The two extra rows are no longer reserved, so the rack floor is 31 rows again.

Validation: 165 affected/composing tests, 124 guards and 12 docpins passed.
Four regression mutations were rejected, including the row pin both ways.
Review approved with no findings after five focused cases and an additional
caption-overlap mutation. No full suite or outstanding findings.


## ORACLES boardroom card — 2026-10-13

Replaced LAUNCHPAD's rack slot with the approved ASSESSING digit card, loaded-page
subtitle and attested footer. The native LAUNCHPAD view remains accessible in Surf.
ORACLES uses the existing request reader/cache: the boardroom polls only the list,
while the native ORACLES view enables selected details. Suspend/resume cancellation
restarts immediately on the next offer without duplicate in-flight requests.

The live keyless 149×45 render showed 0 assessing, 100 loaded and 70 attested.
The neutral zero state and unchanged 144×37 minimum were verified in the real rack.
Capped pages retain the loaded-count scope; tooltip coverage and source clocks
remain explicit. Stale data has a dated subtitle; missing counts stay unknown.

Validation: 482 affected/composing tests, 124 guards and 12 docpins passed. Three
implementation mutations and the reviewer's hidden-detail cancellation mutation
were rejected and restored. Final review approved with no findings after 12 focused
checks. No full suite, open findings, endpoint additions or layout-pin changes.

## Boardroom loading display — 2026-10-14

Owner-requested display exception: remove automatic stale/unavailable placeholders
from cards and terminal summaries. Retain cached figures, use em dashes for missing
values, and preserve source clocks/states internally and in card tooltips. WIP keeps
its workflow subtitle; ORACLES keeps `in progress`. Literal event/reply prose remains
untouched. Actual in-flight reads show `◌ loading`, including the terminal footer with cached
figures; empty agent inputs are unchanged. Literal single-word announcements are
not treated as missing-value placeholders.
The existing age timer requests guarded cache-only repaints while loading, so finished
reads appear without waiting for the next 30-second network poll or offering new I/O.

Live keyless renders at 149×45 showed 13 pending indicators, then zero after reads
finished, with no automatic stale/unavailable text. Existing 144×37 layout checks
remain green. The final affected/composing run passed all 560 cases; 124 guards and 12 docpins
passed. The final live reading preview also showed the terminal footer loader
beside cached values. Three implementation mutations
were caught and restored (stuck loader, extra network read, hidden loader).
No full suite run. Initial review identified literal single-word announcement handling
and cached terminal-footer loading; both were fixed with compositor regressions.
Scoped re-review approved both fixes after eight passing cases and two reversal
mutations caught and restored. No outstanding findings.
The final combined fast-guard/docpin check passed all 127 selected cases.

## Boardroom FLEET runtime summary — 2026-10-15

Replaced the top-agent list with codex/claude percentages of distinct online
seats, the most-used daemon base version, and the leading advertised model and
effort. The inner footer has no label (`astra 6 xhigh`); the centered worked
duration remains independent. Worker facts and their source clock share one
captured cache snapshot. No endpoints, timers or caches were added.

The owner explicitly waived another preview. Production-screen composites
retain the 146×37 minimum and fit 149×45, including a nine-cell daemon version
and the model/effort footer. Validation: 822 affected/composing cases and 124
fast guards and 12 documentation pins passed; the migrated optional-theme palette assertion passed after
using its resolved foreground. Eight implementation mutations and two review
mutations were rejected and restored. No full suite was run.

Final review approved with no Critical or Important findings. Minor residual:
`.claude/rules/surf.md` says hover preserves per-worker daemon/model weighting,
but hover currently describes current advertised configuration and combined
daemon builds without explicitly saying “per worker.” Correct that wording
when the rules file is next touched; the calculations and approved UI are
unaffected.

## Boardroom FLEET / TOKENS position swap — 2026-10-15

TOKENS now sits below ONCHAIN FEED on the left; FLEET sits below PROTOCOL on
the right. Card identities, data and destinations stay attached to their cards.
Arrow navigation follows the new positions. The translated captions remain
above the original left and right AGENT columns.

Live keyless preview at 149×45 shows the swapped cards. Boundary composites
retain the 146×37 minimum. Position, navigation and caption regression checks
reject reversals of both changes; the mutation runner restores the source.
Final affected/composing checks: 185 passed; fast guards and documentation pins:
127 passed. Review approved with no findings and independently killed both
mutants. No outstanding follow-ups for this swap; no full suite was run.

## Boardroom PROTOCOL / FLEET position swap — 2026-10-15

FLEET now occupies the top-right slot; PROTOCOL sits directly below it beside
the terminal. TOKENS remains on the left. Card data and destinations are unchanged;
arrow navigation follows the swapped slots. Both translated captions and all four
AGENT seats retain their positions.

The live keyless 149×45 preview shows the swap. Reverting the slot order or
anchoring the right caption to FLEET again fails the existing position,
navigation and caption checks; both mutation proofs restored the source.
All 185 affected/composing checks and 127 guards/documentation pins passed;
the layout remains 146×37. Review approved with no findings and independently
rejected both mutations. No outstanding follow-ups; no full suite was run.

## Boardroom TOKENS / PROTOCOL position swap — 2026-10-15

PROTOCOL now occupies the left slot below ONCHAIN FEED; TOKENS sits on the
right below FLEET. The top row, agent seats and translated captions retain
their positions. Card data and destinations follow the same identities, and
arrow navigation follows the new columns.

The live keyless 149×45 preview shows the swap. Tests reject restoring the old
card order or moving the captions with the cards; both mutations were restored.
All 185 affected/composing checks and 127 guards/documentation pins passed;
the layout remains 146×37. Review approved with no findings and independently
rejected both mutations. No outstanding follow-ups; no full suite was run.


## Source notices and loading — 2026-10-16

Removed explicit stale/unavailable/source-failure presentation throughout Surf,
boardroom and token overview/detail screens, including source tooltips. Cached
values, neutral timestamps, partial coverage and operational statuses remain;
missing values use dashes. Real pending tasks drive an animated title indicator
on opening/reopening. Background completion uses a passive projection, avoiding
extra fetches or failure retry loops. Source TTLs and state contracts are retained.

Live public data was rendered at 149×45 for boardroom and Built by Swarm before
hardening. No CSS or layout constants changed. The affected/composing run covered
61 files: 2,886 passed initially; obsolete source-notice assertions were updated,
and two regressions (duplicate startup fetch, oracle assessing color) were fixed.
Focused reruns passed, including all 254 boardroom projection cases and 27
loading/oracle cases. Review found fast detached reads could escape the first
loading sample and long titles could clip loading. Both received failing
regression tests, production fixes and focused checks: 21 lifecycle/title/startup
cases pass. Twelve lifecycle/task/title mutations were rejected and restored.
Fast guards and documentation pins passed after registering the new
shared screen as abstract. No full repository suite ran.

Scoped re-review confirmed both findings addressed, reran the three regression
tests and independently rejected the fast-completion mutation. No open findings
remain for this change.

Seven remaining failures were reproduced against clean HEAD `e3b7074f` and are
unrelated follow-ups: two old POOL4 binding/body assertions, two old launchpad
hero assertions, two site fixtures missing `named_ts`, and an old swarm widget
ordering assertion. Update those tests when their respective files are next
touched for those behaviors. They were not weakened to make this task green.

## White inner-box labels — 2026-10-17

All mounted cards using the shared inner palette now use their normal text
white for labels, matching ONCHAIN prose. The FLEET-only timestamp-gray override
is removed. Active green readouts, warning colors, measured values, captions,
padding and the green empty-seat input arrow retain their previous appearance.
Missing placeholders using label ink follow the white labels.

Fresh public keyless BOARDROOM and BOARD renders at 149×45 were shown before
review (`/tmp/maxpane-white-labels/`). Existing color regressions failed before
implementation and 32 focused cases passed afterwards. Three palette/FLEET
rollback mutations were caught. The single review found that the empty-seat
arrow also inherited the white label ink; an explicit green style corrected it.
Both existing seat render cases failed with the new color assertion before the
fix and passed after. Scoped re-review marked the finding ADDRESSED and
independently killed/restored that rollback. No open review findings remain.

Final fast guards: 126 passed; documentation pins: 12 passed. The 27 affected
widget/composing files produced 1,084 passes and 16 failures. One remaining
PROTOCOL assertion expected the former green diagnostic text; corrected to
normal card text while preserving red-frame and recovery checks, its whole
24-test file passes. The other 15 failures match the already documented
Portfolio/Surf baseline failures in `surf_data_loading_followups.md` (nine
Portfolio, two POOL4 market, two POOL4 protocol, one AGENT row, one NEWS fixture).
Logs: `/tmp/maxpane-white-labels/tests.log`. No full suite or pin changes.

## CR round 3b86085d — 2026-10-21

The top title and center navigation hint replace the previous gap-title/WORKFLOWS link.
FLEET jobs means successfully completed jobs, per the owner's clarification. TOKENS uses
rolling selected-pool USD volume for the entire launched-token catalogue, with `≥` for a known
subtotal and details for coverage; the hourly-volume fetch is no longer offered from BOARDROOM.
Work/Oracle mouse selection, workflow history, border removal and the NFT source-timeout fix
are documented in `cr-round-3b86085d-plan.md` with live evidence and scoped validation.

Current limits remain explicit: public NFT source failures can leave fields unknown; selected
pool quotes do not claim all pools of a token; workflow safety caps publish partial coverage.
No new endpoint, signer, payment path or API key was added. The final review found one
older-open-job retention issue; it was fixed in one wave and scoped re-review approved it.
956 affected cases, 128 guards and 12 doc pins passed across the scoped runs/reruns.
The final Work live read took 34.92s with 493 normalized jobs and 197 workflows.
No remaining review findings.
