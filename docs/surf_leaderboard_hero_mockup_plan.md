# LEADERBOARD / SURFBOARD hero mockup — proposal 1

## Approved scope and stage

The owner's latest selection is **proposal 1**, the ranking overview. Build its
standalone Textual mockup using fictional data, continuing the requested sequence:
three ASCII proposals → selected mockup → owner feedback → live API integration.
This phase changes no production screen or source; API work follows approval.

Treat the package as Tier 2, below approximately 250 production lines, with one
root implementer and one final review. Superpowers remain disabled. The owner's
explicit mockup-first workflow defers the live-render gate and production pin
measurements to the subsequent API phase.

## Selected visual contract

At **149 columns × 45 rows**, show six equal-width, nine-row cards in one row.
Reuse unchanged `HeroRecord` and `NewsHeroCard`, preserving the rack's grey outer
casing, black inset, green inner border, native numeric faces, aligned list
labels/values and common footer baseline.

| Outer title | Inner title | Inner content | Inner bottom line | Outer bottom line |
| --- | --- | --- | --- | --- |
| TOP SEAT | SEAT | Large `527` | `4.18k accepted` | `RANK 1` |
| RECORDED | RECORDS | `seats 1,024`, `attempts 100k` | None | `RECORDS` |
| ACCEPT RATE | % | Large `96.0` | `96k / 100k` | `ACCEPTED` |
| OUTCOMES | RECORDS | `rejected 2k`, `failed 1k`, `pending 1k` | None | `RECORDS` |
| WORKERS | NOW | `live 966`, `working 24`, `capacity 2,880` | None | `CURRENT` |
| EFFORT | RECEIPTS | `receipts 18.4k`, `turns 580k`, `hours 18k` | None | `CONTRIBUTORS` |

Show a visible `MOCK DATA` label in the app and exported artifact. Below the
cards, compose the existing `SurfSwarmLeaderboard` table beside `SurfSwarmFleet`
as native review context. Keep their production implementation untouched. Allow
the table/body to scroll and give narrow terminals horizontal scrolling rather
than hiding cards or compressing their contents beyond legibility.

## One coherent fictional snapshot

Keep mock data separate from rendering and use a fixed mock clock. Populate the
hero records and native body from the same snapshot and derived summary.

- Create exactly 1,024 distinct recorded seat IDs. Seat **527** has **4,180
  accepted records**, making it rank 1. Across all rows, accepted is 96,000,
  rejected 2,000, failed 1,000 and pending 1,000, so attempts is 100,000 and the
  acceptance rate is 96.0%.
- A simple generator avoids hundreds of literals: reserve 4,180 accepted for
  seat 527, distribute the remaining 91,820 over the other 1,023 seats using
  quotient/remainder, and distribute each of the other three totals across all
  1,024 rows. Derive each row's attempts as the sum of its four outcomes.
  Rank by accepted descending, then acceptance ratio descending, then seat ID.
- Derive the displayed recorded-seat count, outcome totals, acceptance rate and
  top seat from those rows. Do not maintain independently invented hero totals.
- Worker data reports 966 live workers, 24 concurrent work slots and capacity
  for 2,880 slots. These are different quantities: **working is not a count of
  unique working agents**, and live workers are not wallets or recorded seats.
  Native worker metadata, pause entries and table presence must be compatible
  with the chosen fictional worker population.
- Contributor effort reports 18,400 receipts, 580,000 turns and 18,000 aggregate
  hours (`64_800_000_000` milliseconds). Those figures belong to contributor
  receipts, independently of canonical recorded outcomes. Contributor counters
  and optional token figures may differ from the records totals, and must not
  be substituted for them or forcibly reconciled with them.
- Populate enough fleet metadata and independent clock fields for the existing
  FLEET body to be meaningful. Any runtime/model mix describes advertised
  workers, not completed work. Use coherent fictional values or explicit unknown
  values; do not present gaps as zero.

Use existing primitive widget inputs only. Do not construct managers or clients,
read or write configuration/cache state, contact APIs, alter production models,
widgets, screens, theme files or layout pins, or change dashboard registration.
The standalone app may read the existing theme stylesheet unchanged.

## Ownership and sequence

1. **Planning agent:** only `docs/surf_leaderboard_hero_mockup_plan.md`; record the
   selected design, source meanings, boundaries and checks before implementation.
2. **Root:** new `scripts/surf_leaderboard_hero_demo.py`, new
   `tests/screens/test_surf_leaderboard_hero_demo.py` and applicable follow-up
   documentation. Follow the standalone PROTOCOL demo's direct-widget app,
   theme registration, interactive launch and SVG export pattern. Support
   `--export /tmp/surf-leaderboard-heroes.svg --size 149x45`.
3. **Final reviewer:** review this completed diff once after the root has shown
   the working mock render and run the scoped checks. Root owns any fixes.

There is one implementation package, depending on this approved proposal. Other
files and concurrent edits remain untouched. Report unexpected dependencies to
root; do not broaden ownership or spawn subagents.

## Acceptance and verification

- Write focused failing tests first, then the smallest preview implementation.
  Patch network and clipboard operations to refuse use, isolate user state, and
  assert no configuration/cache access occurs through the standalone app.
- Test actual compositor `render_strips()` at 149×45: six titles, inner headings,
  formatted values, subtitles, footers and the mock label must be visible. Check
  black inset and green frame, native table/fleet content, equal nine-row heights,
  widths within one cell, common baselines, containment and no overlap/clipping.
- Verify 1,024 distinct row identities, rank 1 seat 527, all row outcome identities,
  the 100,000 attempt/96,000 accepted totals, 96.0% rate and contributor time units.
  Exercise the six-card count refusal so incomplete proposals cannot render.
- Resize to 100×30, scroll to the final cards/body, and recover to 149×45 with all
  six cards intact. Use observable Textual state, not wall-clock sleeps.
- Export SVG to a temporary path, inspect the raster render and show the owner
  before review. Prove a geometry assertion catches one reversible mutation via
  the repository mutation tool; do not certify or move a production layout pin.
- Before commit, run affected/composing tests once with isolated HOME and
  `-n 4 --dist worksteal`, the fast `guard and not mounts_app` checks and applicable
  docpins. No full suite. Root records the real results and artifact location.
- Use one final review and one fix wave for Critical/Important findings; scoped
  re-review follows only production fixes. File Minor-only residuals through the
  existing follow-up process.

Deliver the fictional LEADERBOARD preview for owner feedback. The next approved
phase will connect its existing independent records, workers and contributor
sources and show the live production result before integration hardening.
