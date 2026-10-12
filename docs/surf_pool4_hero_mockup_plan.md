# POOL4 / SURFBOARD hero mockup — proposal 1

## Approved scope and stage

The owner selected the balanced market overview. The rack's POOL4 destination is
`MODE_POOL4_USER`, the market body; the separate PROTOCOL card opens `MODE_POOL4`.
Build a standalone Textual preview with six rack-style cards above the existing
market panels. This stage uses fictional data only, following the owner's sequence:
three ASCII proposals → chosen Textual mockup → approval → API integration.

Treat the whole package as Tier 2, below 1,000 production lines, with one final
review and no package reviews. Superpowers remain disabled. The owner explicitly
requested a mockup first, so defer the live-render gate to later API integration.

## Selected visual contract

At **149 columns × 45 rows**, show six equal-width cards in one row, each **nine
terminal rows high**. The approved figures below are explicitly fictional.

| Outer title | Inner title | Inner content | Inner bottom line | Outer bottom line |
| --- | --- | --- | --- | --- |
| IMD PRICE | USD | Large numeric `9.410` | `here -1.20%` | `POOL4` |
| sIMD RATE | IMD | Large numeric `7.964` | `per 1 sIMD` | `EXCHANGE` |
| STAKING | APR % | Large numeric `8.4` | `trailing 7d` | `REALISED` |
| VAULT | STATS | `IMD 82.4k`, `sIMD 10.35k`, `addresses 126` | None | `STAKED` |
| DOWNSIDE BID | ETH | Large numeric `18.60` | `3.20% under` | `DEPLOYED` |
| DRIP QUEUE | DELIVERY | `queued 7.44k IMD`, `cap 1.2k IMD/d`, `queue 6.2d` | None | `RATE LIMITED` |

Reuse unchanged `NewsHeroCard` and `HeroRecord` from `widgets/surf/news_hero.py`.
Retain grey outer casings, dark insets, theme-green accents, aligned labels and
values, native numeric faces and common footer baselines. No title, amount, unit
or footer may clip at the owner size. Preserve all six cards at narrow sizes with
scrolling rather than hiding cards or crushing their contents.

Keep a visible `MOCK DATA` label in the interactive frame and exported SVG. Below
the cards, use native POOL4 FLOW, BURN & SUPPLY, SIGNALS, STAKERS and IF IMD FALLS
panels in the existing market arrangement. These panels provide review context;
their production design and behavior are outside this package.

## Fictional records and truthful units

Keep mock records separate from rendering and use a fixed mock clock. Supply the
same underlying figures to hero and body, not independently invented summaries:

- Price is USD per IMD. The fictional cheaper-venue result is `here` with a
  negative 1.20% gap; do not invert the meaning of that venue comparison.
- One whole sIMD converts to 7.964 IMD. Use vault assets of 82,400 IMD and exact
  shares `82400 / 7.964`, displayed as approximately 10.35k sIMD.
- The 8.4% staking figure is **annualised realised return derived from trailing
  seven-day drips**, not an 8.4% gain in seven days or the delivery-rate ceiling.
  Keep both `APR %` and `trailing 7d` visible.
- The vault has 126 holder addresses, not 126 distinct people. Any shorter table
  is a clearly identified excerpt; its mock totals/concentration remain coherent.
- The deployed band contains 18.60 ETH. Choose consistent tick inputs whose
  existing distance helper rounds to 3.20% under spot, so SIGNALS and the hero
  agree. The existing depth model describes current positions, not a price floor.
- The queue holds 7,440 IMD at a delivery cap of 1,200 IMD/day: 6.2 days at that
  cap. Do not call the cap earned daily income or guarantee delivery timing.
- Populate recent flow, burn, supply and depth with compatible fictional values.
  Recent flow is a bounded event list, not a complete 24-hour volume history.

No manager/client construction, API calls, configuration/cache reads or writes,
production screen/theme edits, new contracts, registration changes or pin changes.
Use the repository virtual environment and export temporary artifacts outside Git.

## Ownership and dependencies

1. **Planning agent:** only `docs/surf_pool4_hero_mockup_plan.md`. Record the
   selected design, data coherence, boundaries and checks; preserve other work.
2. **Root:** `scripts/surf_pool4_hero_demo.py`,
   `tests/screens/test_surf_pool4_hero_demo.py` and applicable follow-up records.
   Follow the SWARM and LAUNCHES standalone demos. A demo-only `SurfScreen`
   subclass is suitable if its live lifecycle and configuration/cache access are
   fully bypassed; otherwise compose the native market widgets directly in the
   standalone app. Keep the simpler safe option and change no production screen.
   Provide local launch and `--export ... --size 149x45` behavior.
3. **Final reviewer:** read-only review after the root's working, visually inspected
   preview and scoped verification. Root owns fixes. No separate package review.

The approved proposal is the implementation dependency. No package needs API
research or a new live contract. Shared files remain untouched; any unexpected
cross-owner dependency is reported to root rather than edited by another agent.

## Scoped validation and delivery

- Write focused failing tests, then the smallest preview implementation. During
  edits run only cases affected by each change. Tests prohibit network and real
  clipboard access and use isolated user-state paths.
- Assert actual composited content: all six titles, headings, values, units,
  subtitles, footers and the mock marker. Confirm the native body is populated
  and its rate, queue, vault, bid and price facts match the hero.
- At 149×45 measure six equal nine-row cards, footer baselines, containment and
  absence of overlap/clipping. Exercise narrow resize/scroll and recovery to the
  owner size. Do not update production pins from this standalone preview.
- Export the Textual SVG, visually inspect it and show it before final review.
  Prove a geometry assertion catches a deliberate reversible regression using
  repository mutation tooling.
- Once before commit, run the complete affected test file with isolated HOME and
  `-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and applicable
  docpins. No full suite. Root records the artifact and exact green results.
- Use one final review and one fix wave for Critical/Important findings; a scoped
  re-review is needed only if fixes change production code. File Minor-only
  residuals through the existing follow-up process.

Deliver the fictional POOL4 preview for owner feedback. Connect existing live
sources only after mockup approval, then show the live production render before
hardening that integration. Continue the dashboard loop after POOL4 confirmation.
