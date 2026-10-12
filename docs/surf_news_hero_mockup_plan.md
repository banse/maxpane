# ONCHAIN NEWS / SURFBOARD hero mockup

## Approved design and current stage

The owner selected proposal 3: six equal hero cards using the dashboard rack's
equipment-card design. The purpose is to make the news dashboard's most important
information readable at a glance while retaining its announcement feed and detail
panels below.

This package implements only a standalone Textual preview with explicitly fictional
data. The sequence is ASCII selection → Textual mock-data preview → owner feedback
and approval → live API preview. The ASCII selection is complete; API loading and
production integration are deferred until the mock-data preview is approved.

Treat this as Tier 2 for the scoped demo and its new widget composition. Keep the
implementation below 1,000 production lines, with one final review and no individual
package reviews. Superpowers remain disabled by the project instructions.

## Visual and content contract

The target terminal is **149 columns × 45 rows**. Arrange six equal-width cards in
one row, each **nine terminal rows high**, ordered as follows. Values and prose are
fictional mock data; never describe them as current observations.

| Outer title | Inner title | Inner content | Inner bottom line | Outer bottom line |
| --- | --- | --- | --- | --- |
| ANNOUNCEMENT | LATEST | Short fictional official-post preview | `18m ago` | `OFFICIAL` |
| LATEST REPLY | COMMUNITY | Short fictional community-reply preview | `7m ago` | `REPLY` |
| SIGNALS | STATUS | Three aligned rows: `fired 2`, `watch 1`, `quiet 8` | None required | `KNOWN 11 of 11` |
| DEV ACTIVITY | RECENT | Three fictional recent actions with age and wallet context | `2 wallets` | `RECENT` |
| IMD MARKET | USD | Native Textual Digits displaying `9.41` | `+2.3% 24h` | Mock price sparkline |
| NFT BOARDS | STATS | Three aligned rows: `holders 812`, `written 1967`, `24h moves 38` | None required | `IDENTITY.MD` |

Use the rack's grey outer casing and frame, recessed dark inner readout, theme-green
accents and neutral secondary text. Preserve meaningful signal-state distinctions;
do not make a decorative green status imply that an alert is safe. The price
sparkline uses the rack chart color. Lists align labels and values consistently,
and previews wrap within their inner frame. All six outer bottoms share a baseline.
No hero card may clip its title, metric, inner footer or outer footer at the target
size. Intentional prose truncation is allowed when visibly indicated.

Below the hero, retain enough native NEWS dashboard context to judge how the cards
work with the page: mock announcement feed, signals, dev activity, market and NFT
panels. This is presentation context, not approval to redesign the production body.
Use existing native panel widgets where practical, populated directly from mock
records, and keep body changes limited to what the standalone composition needs.

Keep an explicit `MOCK DATA` indication visible in the exported frame. Mock records
must be separate from rendering/layout construction so later real-data mapping does
not require a geometry rewrite. Prefer small local records and ordinary Textual
composition; do not introduce a framework or force MVC layers.

## Boundary and future data mapping

The demo must not instantiate a manager or client, fetch a URL, access a live API,
write user configuration, or change a production screen, widget, layout pin, route
or application registration. It uses the existing Python/Textual environment.
Preview artifacts go to a temporary directory and are not committed.

Later integration can reuse existing announcement, signal, activity, market and NFT
reads. Freeze that contract only after the preview is accepted. In particular:

- FIRED is the number of detector types currently fired, not a 24-hour event count.
  Known detector coverage must remain distinct from quiet detectors.
- The public feed and dev-activity lists are capped at 25 rows. Do not promote their
  lengths to exhaustive daily totals or invent activity-history sparklines.
- The latest official preview and its age must come from the same full-channel
  projection; do not combine a capped-feed excerpt with another post's age.
- A future live render must distinguish unavailable values from genuine zero and
  preserve source freshness. The current mock values make no coverage claim.
- The existing `SurfHero` is shared with LAUNCHPAD and protocol modes. Future NEWS
  integration must isolate its hero so those dashboards change only in their own
  approved design loop.

## Work packages, owners and dependencies

### 1. Spec and plan — planning agent

**Owned file:** `docs/surf_news_hero_mockup_plan.md` only.

Record the chosen card contract, stage boundaries and verification requirements.
Do not alter implementation files or user work. This package precedes implementation
and needs no separate task review.

### 2. Standalone demo and tests — root session

**Owned files:** `scripts/surf_news_hero_demo.py` and
`tests/screens/test_surf_news_hero_demo.py` only.

**Dependencies:** Proposal 3 selected and this plan available.

Write focused failing tests, then the smallest matching Textual composition. Support
running the demo locally and exporting an SVG at 149×45. Test actual composited
content and widget geometry: six equal nine-row cards, common top/bottom baselines,
no overlaps, visible data and footers, native price digits, mock-data marker and the
five contextual body panels. Keep data fixtures local and network-free.

During editing, run only changed cases. Export and visually inspect the mock SVG,
then show it to the owner before final review. The owner's mock-only instruction
governs this stage; a live API render belongs to the next approval stage.

Prove a geometry assertion detects a deliberate layout regression using the
repository mutation tool, restoring the source afterward. Once before commit, run
the complete affected test file with isolated HOME and `-n 4 --dist worksteal`, the
fast `guard and not mounts_app` set, and the applicable docpin tests. Do not run the
full suite. Record exact results and preview location in the delivery message.

### 3. One final review — independent reviewer

**Ownership:** Read-only review of this plan and the two implementation files;
root retains all fix ownership.

**Dependencies:** Working demo, inspected/exported preview and green scoped checks.

Review the composited result, six-card contract, mock-only boundary, simple data /
view separation and test evidence. Follow the repository reviewer contract: one
final review, one fix wave for Critical/Important findings, and one scoped re-review
only if the fix wave changes production code. File Minor-only residuals through
the existing follow-up process rather than broadening the preview.

## Next decision

Deliver the Textual mock preview for owner feedback. After that approval, plan and
perform the keyless live-data stage for this dashboard, show the real render before
hardening, and obtain confirmation before continuing the same ASCII → mock → live
workflow with the next SURFBOARD dashboard. No other dashboard is implemented by
this package.
