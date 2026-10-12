# AGENT / SURFBOARD hero mockup — proposal 4

## Approved scope and stage

The owner selected **proposal 4**: convert the existing twelve AGENT topics into
two rows of six rack cards, with the native RECORD table below. This is a
standalone Textual mockup using fictional data. Follow the owner's sequence:
ASCII proposals → selected mockup → feedback → API integration.

This is Tier 2, sized below 1,000 production lines overall, with one implementation
package and one final review. Superpowers remain disabled. The explicit
mockup-first request governs this standalone phase; the live-render gate and
production pin measurements apply to the later approved API integration.
No production screen, theme, widget, contract, endpoint, configuration or cache
changes belong to this phase.

## Selected visual contract

At **149 columns × 45 rows**, render **twelve nine-row cards**, six per row, with
one terminal row between rows. Preserve column alignment and equal card widths
within one cell. Use the existing rack's grey outer casing, black inset, green
inner frame and text, large digits where useful, and aligned three-line lists.
Reuse unchanged `HeroRecord` and `NewsHeroCard` from
`maxpane_dashboard/widgets/surf/news_hero.py`.

| Row | Outer title | Inner content | Context to retain |
|---|---|---|---|
| 1 | SEAT | IDMD seat **420**, large digits | Selected seat identity |
| 1 | ACCEPTED | **960**, large digits; **of 1,000** attempts | **96.0%**, canonical records |
| 1 | EFFORT | **320 h**, **1.8M tokens** | Contributor receipts |
| 1 | REWARDS | **12.84 IMD**, large digits; **~$120.82** | **OWNER SHARE** |
| 1 | RANK | **27**, large digits; **of 1,024** | Canonical records |
| 1 | STATUS | working **2**, capacity **3**, devices **2** | **BUSY**, completely green segmented bar |
| 2 | OWNER | **example.eth**, paired **10-01** | Fictional owner, IDMD collection |
| 2 | RUNTIME | codex **vX.Y.Z**, daemon **vX.Y**, **2 devices** | Reported software |
| 2 | MODELS | **model A high**, **model B medium** | **ADVERTISED**, not actual submission models |
| 2 | FEEDBACK | sent **186**, submitted **4**, queued **2** | Review delivery states |
| 2 | COLLAB | **12** seats, large digits; **#527 ×84** | Shared jobs with the top collaborator |
| 2 | NODES | REVIEW **500**, BUILD **340**, ORACLE **120** | Accepted detail-history work |

Keep the existing rack's orange BUSY label and green filled segments. Capacity
is a separately labelled count, not a utilization denominator: oracle work can
exceed configured concurrency. EFFORT retains hours and output tokens; turns
remain a BOARD topic. Footer labels, inset headings and compact formatting may
use the shortest honest wording that fits the selected topic.

Display **MOCK DATA** prominently in the title and export, plus a concise footer
stating that all values are fictional and no API is connected. The RECORD table
uses all remaining height below the card grid and scrolls internally. Keep a
minimum readable table height. At smaller sizes, scroll the outer viewport so
all cards and the table remain reachable; do not shrink card height or silently
drop columns/cards. No production layout pin is changed or certified here.

## Fixture and source semantics

- Use one deterministic mock snapshot and fixed timestamps. Generate 1,000
  fictional work rows: 960 accepted, 20 rejected, 10 failed and 10 pending.
  Accepted rows comprise 500 reviews, 340 builds and 120 oracle assessments.
  Derive displayed acceptance and node counts from these fixtures. Feed the
  existing `SurfSwarmSeatRecord` its normal primitives; its native 40-row cap and
  remaining-row indication represent the larger history honestly.
- Give each work row a stable fictional job/submission identifier, node, state,
  objective and suitable submitted/accepted timestamps. Known accepted rows may
  have completed jobs; pending/rejected/failed outcomes must not become accepted
  merely because a job is completed. Use actual-submission model examples in
  RECORD separately from the advertised-model list.
- Contributor effort is an independent mock receipt aggregate: 320 hours and
  1,800,000 output tokens. It is neither uptime nor an implied sum of only the
  forty visible record rows.
- Rewards are attributed owner receipts since pairing, divided by current held
  IDMD seats. For example, 38.52 IMD divided by three seats gives 12.84 IMD;
  multiplying by the fictional current quote 9.41 USD gives 120.8244 USD, shown
  as approximately $120.82. Do not describe this as direct seat earnings.
- Rank 27 of 1,024 is a fictional canonical-board result. No invented change
  interval, rank movement or history graph is required.
- Feedback totals 192 delivery entries, independent of accepted work; sent,
  submitted and queued retain their existing meanings. Twelve collaborators
  includes seat 527 with 84 shared jobs; do not imply those counts sum to work
  attempts. NODE counts sum to the 960 accepted mock attempts.
- `example.eth` is an explicitly fictional display label backed by a fixed
  fictional address. Use the existing rich address/copy/explorer helper if the
  card paints an address or interactive label. Do not perform ENS lookup, launch
  a browser, or access the real clipboard during preview tests.

## Ownership and implementation sequence

1. **Planner:** only this new plan, finalized before implementation.
2. **Root implementer:** new `scripts/surf_agent_hero_demo.py` and new
   `tests/screens/test_surf_agent_hero_demo.py`. Follow
   `scripts/surf_launchpad_hero_demo.py`: direct widget composition, matrix
   theme, interactive launch and
   `--export /tmp/surf-agent-heroes.svg --size 149x45`.
   A small demo-local `NewsHeroCard` subclass may preserve rich owner text and
   style the BUSY/footer bar; do not change shared records or widget rendering.
3. **Root:** inspect/export the mock, show it to the owner, coordinate the one
   final review, record applicable follow-ups and verification, and commit.
4. **Final reviewer:** one review of the completed mock-only diff after the
   owner-size render and scoped checks. No package review or second reviewer.

These files have disjoint ownership. Preserve concurrent edits; do not edit
other owners' files, broaden the package, spawn subagents, or commit as planner.
Report an unexpected shared dependency to root instead of changing it.

## Acceptance and verification

- Start with focused failing tests, then the smallest implementation. Refuse
  network, user configuration/cache and real clipboard access; isolate user
  state. Reject an invalid number of hero records.
- Assert actual compositor `render_strips()` at 149×45: all twelve titles,
  headings, important values, units, context/footer labels and MOCK DATA marker
  are visible. Verify exactly six cards per row, heights of nine, equal widths
  within one cell, common column edges, a one-row gap, and no overlaps.
- Check digit glyphs remain whole, list labels and values align, inset backgrounds
  stay black, healthy frames use the theme green, and STATUS paints orange BUSY
  with a completely filled green segmented bar. Inspect rich owner label spans
  and copy affordance without triggering external actions.
- Verify fixture counts, acceptance arithmetic, node totals and reward valuation.
  Confirm RECORD is visible below the second row and preserves native truncation
  markers and scrolling rather than promising all table columns fit at 149.
- Resize to 100×30, reach the far-right cards and table through scrolling, then
  recover to 149×45 with all twelve cards intact. Use observable Textual state,
  not wall-clock waits.
- Export SVG to a temporary path, inspect its raster rendering and show the
  owner. Prove one geometry assertion catches a reversible regression using the
  repository mutation tool. Do not measure production pins in this phase.
- Before commit, run touched/composing tests once, applicable docpins and fast
  `guard and not mounts_app` checks. No full suite. Record actual outcomes.
- One final review, one fix wave for Critical/Important findings, and a scoped
  re-review only if production fixes require it. File Minor-only residuals.

Deliver the explicitly fictional preview for feedback. Connect existing API
sources only after approval of this mockup.
