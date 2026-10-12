# PROTOCOL / SURFBOARD hero mockup — proposal 1

## Approved outcome and stage

The owner selected the protocol overview: six rack-style cards that expose the
protocol's cumulative flows, inventory, reward allocation, unsettled claims,
delivery queue and accounting status before the detailed panels. This standalone
Textual preview is the next step in the requested sequence: three ASCII proposals
→ selected mockup → owner feedback → existing API integration.

This package is Tier 2 and below 1,000 production lines: approximately 160 lines
for the preview, plus focused tests and this plan. Use one final review, with no
package review. The user explicitly requested the mockup phase first; defer the
production live-render gate and production layout measurements to API integration.

## Selected visual contract

At **149 columns × 45 rows**, render six equal-width cards in one row, each **nine
terminal rows high**, using unchanged `HeroRecord` and `NewsHeroCard` from
`widgets/surf/news_hero.py`. Preserve the rack's grey outer casing, dark inset,
green inner frame, aligned columns and common footer baseline.

| Outer title | Inner title | Inner content | Outer bottom line |
| --- | --- | --- | --- |
| TOTALS | IMD | `burned 33.3k`, `rewarded 5.9k`, `fees 3.8k` | `CUMULATIVE` |
| INVENTORY | IMD | `cap 840k`, `reserve 835k`, `headroom 5k` | `RATCHET` |
| REWARD SPLIT | REWARD % | `staking 30`, `nodes 30`, `bonding* 40` | `* DERIVED` |
| UNSETTLED | IMD | `burn 120`, `rewards 21` | `PENDING` |
| DELIVERY | IMD | `queued 7.44k`, `ready 250`, `cap 1.2k/d` | `RATE LIMITED` |
| CHECKS | STATUS | `reconciled`, `drift 0.0 bps`, `distributor` | `ACCOUNTING` |

List labels align left and values align right. CHECKS can use a three-line preview.
Keep the derived marker and its explanation visible; a tooltip alone is not enough.
No title, value, unit, marker or footer may clip at the owner size. At narrow sizes,
allow scrolling while retaining all six cards, then recover the owner-size layout.

Show a visible `MOCK DATA` label in both the interactive app and exported render.
Below the cards, reuse the existing protocol panels — RATCHET, SPLIT, VAULT and
HATCHES — when they can be composed directly without starting the live lifecycle.
Their role is review context; their production layout and behavior are unchanged.

## Coherent fictional data

Use one fixed fictional snapshot shared by the hero records and native panels.
Amounts remain in whole IMD; values are compacted only for display.

- Cumulative totals can use 33,279 IMD burned, 5,873 IMD rewarded and 3,786 IMD
  fees, yielding the selected compact values. Rewarded refers to the total reward
  leg, not the amount received solely by staking.
- Inventory cap is 840,000 IMD and reserve is 835,000 IMD; headroom is their
  5,000 IMD difference. Do not contradict that positive headroom with a body
  claim that burning is currently active.
- Distributor allocations are 30% staking, 30% nodes and the remaining 40%
  bonding. Bonding is explicitly derived from the denominator minus the two
  observed allocations; these are percentages of rewards, not of gross sells.
- Unsettled burn and reward claims are 120 IMD and 21 IMD. They are pending
  balances, separate from the cumulative settled totals.
- Delivery has 7,440 IMD queued, 250 IMD currently ready and a 1,200 IMD/day
  rate ceiling. Keep ready within the queued amount. The ceiling is a limit,
  not earned daily income or a promised delivery schedule.
- CHECKS uses a fictional reconciled observation and 0.0 bps measured split
  drift. Any native-panel counter inputs must support the same state. The
  distributor label describes the reward path, not an audit or safety rating.

Use a fixed mock clock. Any contextual addresses are fictional and rendered by
the existing address widgets. No manager/client construction, API calls, user
configuration/cache reads or writes, production contract additions, registration
changes, shared-widget edits, screen/theme edits or production pin changes.

## Ownership and order

1. **Planning agent:** only `docs/surf_protocol_hero_mockup_plan.md`; write this
   approved scope and implementation sequence before implementation begins.
2. **Root:** new `scripts/surf_protocol_hero_demo.py`, new
   `tests/screens/test_surf_protocol_hero_demo.py` and the applicable follow-up
   document. Reuse the standalone POOL4 demo's safe direct-widget composition
   and export pattern. Support interactive launch and
   `--export /tmp/surf-protocol-heroes.svg --size 149x45`.
3. **Final reviewer:** the completed diff after the preview is rendered, visually
   inspected, shown to the owner and checked. Root owns any required fixes.

There is one implementation package; its only dependency is this selected design.
All other files and concurrent work remain untouched. Agents do not spawn agents.
Report unexpected shared-file dependencies to root rather than expanding scope.

## Acceptance and validation

- Write focused failing tests, then implement the smallest standalone preview.
  Tests must reject network and real clipboard access and isolate user state.
- Assert actual composited output includes the mock label, all six titles,
  headings, values, units, derived marker and footers. Check representative
  body facts agree with the same snapshot and the protocol context is populated.
- At 149×45 check six equal-width nine-row cards, equal footer baselines,
  containment and no overlap or clipping. Exercise narrow resize, horizontal
  scrolling and recovery. Do not certify a production pin from this preview.
- Export the Textual SVG to a temporary path, inspect its raster render and
  show it before review. Use the repository mutation tool to demonstrate a
  geometry assertion catches a reversible regression.
- Before commit, run the affected test file once under isolated HOME with
  `-n 4 --dist worksteal`, plus the fast `guard and not mounts_app` checks and
  applicable docpins. No full suite. Record the actual results and artifact.
- Perform one final review and at most one fix wave for Critical/Important
  findings; re-review only those fixes when they touch production code. File
  Minor-only residuals in the existing follow-up document.

Deliver this explicitly fictional preview for owner feedback. Connect the live
PROTOCOL sources only in the subsequent approved API phase, then verify the real
production render before hardening that integration or advancing the dashboard loop.
