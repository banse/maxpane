# LAUNCHPAD / SURFBOARD hero mockup — proposal 1

## Approved scope and stage

The owner selected **proposal 1**, the launchpad overview. Build a standalone
Textual mockup using fictional data, following the requested sequence: three
ASCII proposals → selected mockup → owner feedback → live API integration.
This phase makes no production changes and starts no API integration.

This is Tier 2, below 1,000 production lines overall, with one implementation
package and one final review only. Superpowers remain disabled. The explicit
mockup-first instruction takes precedence over the live-render gate for this
standalone phase; production rendering and pin measurements belong to the later
approved API phase.

## Selected visual contract

At **149 columns × 45 rows**, show six equal-width cards in one row, each **nine
terminal rows high**. Reuse unchanged `HeroRecord` and `NewsHeroCard`: grey outer
casing, black inset, green inner border, native numeric faces, aligned list
labels/values and a common footer baseline.

| Outer title | Inner title | Inner content | Inner bottom line | Outer bottom line |
| --- | --- | --- | --- | --- |
| COINS | COINS | Large `210` | `2 new /24h` | `FACTORY` |
| CURVE FLOW | HISTORY | `swaps 12.4k`, `traders 486`, `creators 64` | None | `OBSERVED` |
| VOLUME | kUSD | Large `42.6` | `2h to 12:00` | `2H` plus sparkline |
| CREATOR FEES | ETH | Large `0.0842` | `owed` | `UNCLAIMED` |
| BURN QUEUE | IMD | `accrued 250`, `staged 120`, `sendable 120` | None | `READY` |
| BURNED | kIMD | Large `15.7` | `cumulative` | `EVENT TOTAL` |

The full `0.0842` ETH value, units, subtitles, all titles and all footers must
remain readable at the owner size. Use the existing numeric renderer's fallback
when a native numeric face cannot fit; never truncate digits or round this small
balance to zero. Preserve every card at narrow sizes using horizontal scrolling.

Show a visible `MOCK DATA` label in the app and exported artifact. Below the
cards, reuse the native launchpad body: `SurfLaunchpadCoins` and
`SurfLaunchpadActivity` on the left; `SurfCurveFlow`, `SurfBurnPipeline` and
`SurfBurnkeepers` on the right. These supply review context; their production
behavior and layout are unchanged. Allow body scrolling where needed.

## Coherent fictional snapshot

Use one fixed fictional snapshot and clock. Derive hero values and native panel
inputs from it rather than keeping independent competing figures.

- Factory count and swept launch count are both 210, with 2 new launches in the
  day window and 64 distinct creator wallets. Any capped native coin list is an
  excerpt, not the whole population; do not calculate factory/creator totals
  from its length. The existing day counts use a block-based approximation.
- Curve history records 12,400 swaps and 486 distinct senders. These are
  accumulated observed history, not 24-hour activity or unique people.
- Volume comprises **eight completed 15-minute buckets**, ending at the fixed
  displayed `12:00`, over launchpad-token CurveSwap trading, not IMD-pool swaps.
  Use a fictional current ETH/USD quote of 3,200 and nonnegative buckets. One
  coherent USD sequence is `[2800, 4100, 2500, 6200, 9800, 5600, 4300, 7300]`,
  which totals 42,600 USD; divide each by the quote for matching ETH amounts.
  Derive the displayed `42.6` kUSD total and sparkline from these same buckets.
  This is valuation at the mock current quote, not historical USD execution value.
- Creator fees owed total 0.0842 ETH. This is an outstanding balance, not earned
  daily yield or fees already withdrawn.
- Burn accrual is 250 IMD at the hook, staged balance is 120 IMD at the executor,
  and the fictional bridge preview permits 120 IMD with `burn_ready=True`.
  A native minimum bridge value of 100 IMD is compatible. Readiness comes from
  the preview result, not from comparing hook accrual against the minimum.
- Cumulative launchpad event burns total 15,700 IMD. This is distinct from
  supply-change observations and from the separate PROTOCOL burn total. Populate
  native coin/burnkeeper examples compatibly without presenting an excerpt as
  complete historical accounting.
- Recent activity contains plausible fictional buys, sells and launches. A
  launch has no trade amount, represented by `None`, not zero ETH. Any addresses
  are clearly fictional and use existing address rendering helpers unchanged.

No manager/client construction, network calls, user configuration/cache reads or
writes, production source keys, shared-widget edits, screen/theme edits,
registration changes or layout pin changes. The demo may read the existing
stylesheet unchanged and write requested exports to a temporary path.

## Ownership and dependencies

1. **Planning agent:** only `docs/surf_launchpad_hero_mockup_plan.md`; finalize
   this selected design and sequence before implementation begins.
2. **Implementer:** new `scripts/surf_launchpad_hero_demo.py` and new
   `tests/screens/test_surf_launchpad_hero_demo.py`. Follow the prior standalone
   demos' direct-widget composition, matrix theme and CLI export pattern.
   Support interactive launch and
   `--export /tmp/surf-launchpad-heroes.svg --size 149x45`.
3. **Root:** final render/export inspection, owner preview, applicable follow-up
   documentation, final review coordination, required fixes and commit.
4. **Final reviewer:** one review of the completed diff after the mock has been
   shown and scoped checks have run. No package review or additional reviewer.

The implementation depends only on this approved proposal. Preserve concurrent
work; do not edit another owner's files or spawn subagents. Report unexpected
shared-file dependencies to root instead of expanding the package.

## Acceptance and verification

- Begin with focused failing tests, then the smallest implementation. Tests
  refuse network and real clipboard use, isolate HOME and guard against user
  configuration/cache access. Reject an invalid number of hero records.
- Test actual compositor `render_strips()` at 149×45: all six titles, headings,
  amounts, units, subtitles, footers, sparkline and the mock marker are visible.
  Confirm the black inset/green border and equal nine-row cards, widths within
  one cell, common baseline, containment and no overlap or clipped digits.
- Verify the volume has eight nonnegative buckets summing to 42,600 USD and
  matches the ETH buckets/quote; confirm hero and native body agreement for
  population, flow, creator fees and the burn pipeline.
- Exercise narrow scrolling at 100×30 and recovery to 149×45. Keep all cards
  mounted and the final cards/body reachable. Use observable Textual state.
- Export SVG to a temporary path, inspect its raster render and show the owner
  before final review. Prove one geometry assertion detects a reversible
  regression with the repository mutation tool. Do not certify production pins.
- Before commit, run affected/composing tests once with isolated HOME and
  `-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and applicable
  docpins. No full suite. Root records actual results and the artifact path.
- One final review, one fix wave for Critical/Important findings and scoped
  re-review only when production fixes require it. File Minor-only residuals.

Deliver this explicitly fictional preview for owner feedback. Only after approval
will the existing API sources be connected and their live production render shown.
