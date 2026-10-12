# LAUNCHES / SWARM TOKENS hero mockup — proposal 1

## Approved scope and stage

The owner selected proposal 1, the market overview. Build a standalone Textual
preview of six rack-style cards above the existing SWARM TOKENS body. The cards
summarize the selection; individual launches, trades and movers remain in the
native lower panels.

The current stage is fictional mock data only. The owner's sequence is three
ASCII proposals → selected Textual preview → approval → API integration. No live
API render is required or authorized by this mockup stage; defer that gate until
the later integration. Treat this as Tier 2, target fewer than 1,000 production
lines, and use one final review with no package reviews. Superpowers stay disabled.

## Selected visual contract

At **149 columns × 45 rows**, arrange six equal-width cards in one row, each
**nine terminal rows high**, with the following explicitly fictional content.

| Outer title | Inner title | Inner content | Inner bottom line | Outer bottom line |
| --- | --- | --- | --- | --- |
| TOKENS | STATS | `tracked 48`, `new 24h 4`, `chains 3` | None | `SELECTION` |
| VOLUME | kUSD / 24H | Large numeric `124.8` | `41/48 known` | `MEASURED` |
| LIQUIDITY | PAIRED | `>=12.4k IMD`, `>=3.8 ETH` | `43/48 known` | `QUOTE ASSETS` |
| POOLS | STATE | `two-sided 35`, `one-sided 8`, `unknown 5` | None | `LIQUIDITY` |
| MOMENTUM | 24H | `rising 22`, `falling 14`, `flat 5` | `41/48 known` | `PRICE CHANGE` |
| TOP VOLUME | USD / 24H | `ORBIT $38.2k`, `BMC $21.4k`, `RNNN $14.8k` | None | `LEADERS` |

The VOLUME readout is exactly **$124,800**: `124.8` in `HeroRecord.digits`, with
`kUSD / 24H` making the scale explicit. This presentation uses the existing
renderer unchanged. Reuse `NewsHeroCard` and `HeroRecord` from
`widgets/surf/news_hero.py`; do not fork or modify their production behavior.

Retain grey outer casings, dark insets, theme-green accents, aligned lists and
common outer-footer baselines. No title, metric or footer may clip at the target
size. All amounts retain explicit units; do not add IMD and ETH into one total.
Partial paired amounts carry the lower-bound marker, not an implied USD TVL.

Below the cards, compose native `TokenActivity`, `NewlyLaunched` and `BestPlays`
panels above `TokensTable`, matching `screens/swarm_tokens.py`. Populate them
directly from the fictional snapshot. This is body context for review, not a
redesign of the production screen. Keep a visible `MOCK DATA` indication in the
interactive frame and exported SVG. At narrow sizes, preserve all six cards with
scrolling rather than silently hiding cards or crushing their content.

## Mock dataset and boundaries

Keep data records separate from layout/rendering and use a fixed mock clock.
Create 48 local fictional token rows so the body and six cards agree:

- Three chains; four tokens launched within the last 24 hours.
- Forty-one known volumes totaling $124,800; the leaders are ORBIT $38,200,
  BMC $21,400 and RNNN $14,800.
- Forty-one known changes: 22 rising, 14 falling and five flat.
- Thirty-five two-sided pools, eight one-quote pools and five unknown pools.
- Forty-three known paired amounts totaling 12,400 IMD and 3.8 ETH, kept separate.

Reuse the existing pure `project_snapshot` helper for native body projections.
The data is fictional throughout: no manager/client construction, API requests,
user configuration/cache reads or writes, production screen/style changes, new
data contracts, registration edits or layout-pin changes. Use the existing virtual
environment. Export preview artifacts to a temporary directory, not Git.

Later integration must retain the dashboard's active-filter scope, source coverage,
unknown-versus-zero semantics and real 24-hour windows. Liquidity describes quoted
paired quantities, and two-sided liquidity is a state rather than an assurance of
safety. Those live mappings are not implemented by this package.

## Work packages and ownership

### 1. Plan — planning agent

**Owned file:** `docs/surf_launches_hero_mockup_plan.md` only.

Record the approved contract and implementation boundaries. Preserve all other
agents' and user work. No separate task review.

### 2. Standalone preview and tests — root session

**Owned files:** `scripts/surf_launches_hero_demo.py` and
`tests/screens/test_surf_launches_hero_demo.py` only.

**Dependency:** Proposal 1 selected and this contract available.

Follow `scripts/surf_swarm_hero_demo.py` and its screen tests: write focused failing
tests, implement the smallest composition, and provide local launch and SVG export
at 149×45. Verify actual composited values, titles, footers, units and mock marker;
measure six equal nine-row cards, shared baselines, containment and no overlaps.
Assert the native body is populated and the fictional aggregates agree with its
underlying rows. Exercise narrow resize/scroll behavior and recovery at owner size.
Tests are network-free and clipboard-free.

While editing, run changed cases only. Export, visually inspect and show the real
Textual mock render before final review. Prove a geometry assertion detects a
deliberate reversible regression using repository mutation tooling. Once before
commit, run the affected whole test file with isolated HOME and
`-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and applicable
docpins. No full suite. Root records the preview location and exact green results.

### 3. One final review — independent reviewer

**Ownership:** Read-only review of the plan, script and tests; root owns fixes.

**Dependencies:** Working preview, inspected SVG and green scoped verification.

Check the selected design, dataset consistency, truthful units, unchanged shared
renderer, mock-only boundary, narrow behavior and compositor test evidence. Apply
one final review, one fix wave for Critical/Important findings, and one scoped
re-review only if fixes alter production code. File Minor-only residuals through
the repository's existing process rather than expanding this preview.

## Next decision

Deliver the LAUNCHES / SWARM TOKENS Textual mockup for owner feedback. After
approval, connect existing live data in a separate integration package and show
the live render before hardening. Finish that dashboard's confirmation before
starting the next dashboard's ASCII → mockup → API loop.
