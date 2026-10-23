# Card loading captions and BOARDROOM WIP counts

## Count-footer display override — 2026-10-23

Owner now requests static `0` instead of a dash/loading diamond in card-bottom
count captions, including WIP `working`, ORACLES `agents` and outer `workflows`.
This supersedes the earlier display rule below, not the unknown-data contract.
Tier 2, under 1,000 production lines; root owns implementation and one final
review. Agency architect recommends a shared count-caption formatter.

Plan: recognize generated count labels (including compound/compact NFT counts)
in `LoadingCard`; substitute before loading and clipping, preserving styles.
Wire the generic inner/outer hero footer and BOARD's outer-footer override as
well as BOARDROOM. Cold count footers bypass the generic `loading` text.
Do not mark these fragments as animation demand. Keep primary values, currency,
percentages, coverage ratios, dates and prose on their existing paths. Source
records, clocks and `None` values are unchanged; no API or polling changes.

Validation: composited cold/idle/busy count captions, three dash spellings,
compound/compact counts, non-count exclusions, retained values, source immutability
and footer-only no-redraw behavior. Show a live 149×45 BOARDROOM, verify existing
card geometry at its boundary, run affected/composing files and guards/doc pins,
kill a zero-fallback mutation, obtain one scoped review and commit locally.
No full suite. Preserve unrelated files and the preceding outage source gap.

Validation evidence: the affected/composing set covered 615 cases. Its first
run passed 607; eight assertions still expected the former missing-count text.
After updating those expectations, all three affected files passed (115 cases).
Fast guards: 128 passed. Doc pins: 12 passed. Both deliberate regressions were
killed and restored: `count-footer-keeps-missing-marker` and
`cold-count-footer-shows-loader`. Logs are `/private/tmp/maxpane-count-final.log`,
`maxpane-count-recheck.log`, `maxpane-count-guards.log`,
`maxpane-count-docpins.log` and `maxpane-count-mutants.log` in the same directory.
The actual keyless 149×45 BOARDROOM capture in
`/private/tmp/maxpane-count-live/` showed static `0 working`, `0 agents`,
`0 workflows` and `0 SIGNALS`; its cached source kept the unknown worker count.
Independent final review: Approved, no findings; 42 additional focused checks
passed and both mutation records were reviewed. No new follow-up was identified.

## Monochrome pulse follow-up

Owner request (2026-10-23): keep `⛋`, but pulse from black through neutral gray
to white and back. Tier 2 because this is the shared card renderer. The session
owns this small follow-up; the existing plan and single-review boundary apply.
Use eight grayscale frames on the existing clock, preserve the background and
all loading gates. Strengthen existing composited body/footer color assertions,
capture the live BOARDROOM at 149×45, then check the affected widget/lifecycle
files, guards and doc pins before a scoped review and local commit.

Validation: 54 card/lifecycle tests, 128 guards and 12 doc pins passed. A live
149×45 BOARDROOM capture shows the white peak and subsequent loaded values
(`/private/tmp/maxpane-card-monochrome/`). Scoped review: Approved, no findings.

Owner request (2026-10-23): use WHITE DIAMOND IN SQUARE (`⛋`, U+26CB)
for the animated card loading marker, including missing numeric inner/outer
card captions. Investigate WIP showing a known jobs digit beside `— working`
and `— workflows`; fix the missing observations where the existing keyless API
can establish them.

Tier 2: the shared loading renderer changes and the WIP acquisition path needs
a bounded correction. This extends `card_loading_diamond_plan.md` at baseline
`7dff0d8d`. Estimated production change stays below 1,000 lines: two disjoint
implementation packages, no package reviews, one final review.

## Evidence and semantics

- `SurfCardReader._work()` fetches only the newest 100 workflows. `_page()`
  deliberately treats a full page as incomplete, so another poll of the same
  head cannot establish an open-workflow count once the catalogue exceeds 100.
  `fetch_workflows()` already supports a validated exclusive `before` cursor.
- `_current()` sees only the newest 100 jobs plus previously retained active
  IDs. A still-executing job older than that page cannot be discovered on a
  cold start. `current_work()` correctly withholds node counts unless fresh
  detail coverage agrees with the overview's executing-job count.
- WIP's jobs digit, current node caption and open-workflow caption are different
  measurements. A jobs count does not establish a worker or workflow count.
  Preserve current node-category caption semantics and the conservative Oracle
  agent rule. Never replace an unproved quantity with zero.
- The data worker's live probe found 199 workflows over two pages with no open
  states, so that observation supports zero open workflows. It also found three
  still-executing job details while the overview reported two executing jobs.
  This upstream disagreement does not support a complete current-node count;
  preserve the unknown value rather than weakening its proof.
- Existing API/filter observations are dated; preserve the current cursor-based
  client rather than assuming a new executing/status filter works. The IMDB
  lesson `2026-10-21-current-node-activity-and-oracle-agent-counts.md` describes
  why node state, live assignment and a complete Oracle roster are distinct.

## Decision

Use the existing lightweight BOARDROOM reader with bounded, resumable workflow
discovery. Keep current-node coverage gates unchanged for observed upstream
snapshot disagreement.
Do not start the hidden WORK dashboard reader: its large history/context budgets
are inappropriate for a card. Do not relax the coverage/freshness checks merely
to display a number. The trade-off is that a cold catalogue may need several
polls before its first proven count; later pending reads retain the last proven
observation and its actual timestamp.

Use the existing shared card pulse and semantic value renderer. The new glyph
occupies one terminal cell; no additional frame rows, rotation, Braille frames,
per-card timer, data fetch or global StatusBar change is needed.

## Work packages and ownership

### UI — root session

Own `maxpane_dashboard/widgets/card_inner.py`,
`maxpane_dashboard/widgets/surfboard/rack.py`,
`maxpane_dashboard/widgets/surf/news_hero.py`, any necessary explicit AGENT
caption callsite, and their widget/screen regression tests.

1. Change the shared marker to `⛋`, retaining the theme-aware color pulse.
2. Add a small semantic numeric-caption rendering seam. Feed only generated
   numeric portions through `loading_value`; append units/labels with their
   original style. Cover WIP's inner and outer captions and equivalent explicit
   numeric captions in the participating card renderers.
3. Recompute animated outer border subtitles when the shared frame changes;
   refreshing the body alone does not rebuild a stored border subtitle.
4. Preserve view pending gates and unknown values outside a read. A loaded
   BOARDROOM primary may coexist with missing secondary values, so active/idle
   cards also animate those missing fields while the visible view reads.
   Keep terminal failure/offline states and empty-seat behavior unchanged. Preserve
   cached numbers, known zero, dates, third-party prose, addresses, empty-seat
   inputs, dimensions and the footer's existing loading indicator.

### Data — assigned worker

Own `maxpane_dashboard/data/surf_card_reader.py`,
`tests/data/test_surf_card_current.py`, necessary card-budget regressions and
their offline fixtures. `data/surfboard.py` or manager projection changes need
an explicit ownership handoff from root before editing; prefer the existing
data contract and client methods.

1. Reproduce the full-workflow-page failure and current-node disagreement first.
2. Continue a validated workflow catalogue beyond the head using `before`.
   Keep only the card's required identity/status/time facts. Impose explicit
   page and retained-row caps, carry progress across polls where necessary,
   and publish a count only after complete valid coverage. A full page, malformed
   row, repeated/non-progressing cursor, duplicate boundary or exhausted budget
   must not become a proven empty tail. Keep observation clocks honest across
   a multi-poll scan and retain a prior proven result on a failed attempt.
3. Keep current-node freshness and overview agreement checks. Deeper active-job
   discovery is a separate follow-up unless live evidence proves the current
   missing value results from an older job absent from the head page. If that
   case is established during this task, root may assign a bounded extension
   using the existing overview expectation, cursor pages and fresh-detail
   fence; keep the 24-detail cap. Do not interpret an index row as a fresh node
   read or use unrelated worker totals to resolve a disagreement.
4. Preserve the 30-second offer interval, single-flight task ownership,
   cancellation and 12-second read deadline. Progress must not reset to the
   same head forever or queue another read behind an active one. Do not import
   the WORK dashboard's history or context budgets.

Packages can proceed in parallel: they exchange existing card values only.
Root owns integration, live observation, final documentation and commit.

## Validation and completion

- Offline composited UI tests: `-`, `--`, `—` placeholders and generated numeric
  captions pulse with `⛋`; consecutive frames change color without moving the
  frame; outer subtitles animate; known zero/cached values, literal dash prose,
  links and dates survive; idle/suspend clears pending presentation.
- Offline data tests: more than 100 workflows, open rows on later pages, exact
  page boundaries, unknown statuses, malformed/duplicate/non-progressing pages,
  failure/cancellation, retained clocks and bounded multi-poll progress. Cover
  an executing job outside the first page only if that follow-up enters scope.
  Prove true zero only with complete
  coverage; retain mismatch/old-detail and Oracle-unknown protections.
- Assert request/detail caps and single-flight behavior; mutate the new
  continuation/coverage gate to show the targeted decoder/concurrency regression
  fails. No real network or clipboard in tests.
- Before review/hardening, root shows the real keyless BOARDROOM render at
  149×45, including the WIP card and a captured pending pulse. Record actual
  source coverage and acquisition duration, including any remaining API limit;
  a missing value correctly withheld is not a fabricated success.
- Run touched/composing tests with `NO_COLOR` unset, then non-mounted guards
  and applicable doc pins. No full suite. One final review of this bounded diff,
  one fix wave, scoped re-review only if production fixes were needed. File
  Minor residuals, then commit locally.

## Implementation observations

- `⛋` occupies one terminal cell. It uses the existing accent-color pulse; no
  card timers or additional network reads are added. Numeric caption handling
  is explicitly selected for BOARDROOM, AGENT numeric metrics and token
  coverage, without rewriting news prose, dates, addresses or status text.
- Workflow acquisition now continues beyond a full first page, with four pages
  per read and the existing catalogue ceiling. The last proven count and its
  original timestamp survive incomplete/failed attempts.
- A real reader invocation loaded all 199 workflows in 1.35 seconds and found
  zero open original workflows. A subsequent current-node read agreed with the
  overview at two executing jobs (`build: 1`, `refine: 1`). Earlier overview/detail
  disagreement was transient; the existing completeness checks remain intact.
- The full cold BOARDROOM was rendered at 149×45 with isolated temporary caches.
  Its WIP card displayed `2` jobs, `1 build`, `0 workflows` after 8.22 seconds.
  Actual pending/settled composites and SVG captures are under
  `/private/tmp/maxpane-card-footer-live/`; the source-only measurement is under
  `/private/tmp/maxpane-card-footer-probe/`.
- Regression tests failed before the fixes. Two UI mutations (disable outer
  caption ticks; suppress missing captions when the primary has loaded) were
  killed by the composited WIP regression and restored byte for byte. Three
  data mutants covering first-page completion, observation timestamps and
  nonadvancing short tails were also killed and restored.
- The affected/composing run passed 574 tests; its 18 failures were reproduced
  with all changed production modules loaded from unchanged HEAD. The identical
  failure set consists of 14 legacy BOARDROOM activity expectations (removed
  PROTOCOL card/old footers) and four pre-existing pool quote mocks. No new
  failures were introduced. Non-mounted guards: 128 passed; doc pins: 12 passed.
- The final review found two Important edge cases, fixed in one wave: include
  AGENT ORACLE's numeric percentage caption (`models` record key), and keep the
  previous proven workflow count/timestamp when a completed traversal contains
  an unknown lifecycle. Both regressions failed before their fixes. The final
  affected/composing selection passed 269 tests in 26.44 seconds.
- Scoped re-review: Approved; both findings addressed. Reverting either fix
  made its named regression fail, and all mutation bytes were restored. Review
  reports are `review.md` and `rereview.md` in the live-evidence directory.

## Follow-up: bounded neutral pulse and synchronized side captions

Owner request: keep the monochrome `⛋` pulse inside the dashboard's existing
dark/bright neutral tones, and pulse BOARDROOM's `キープ` and `ビルディング`
from their current green to the active inner-frame green in sync with the
bottom loading indicator. Tier 2 because shared loading lifecycle/renderers
change; one implementer (root), under 1,000 production lines, one final review.
This follow-up changes presentation only; no data-reader work or layout pins.

Verified palette: Matrix uses background `#1c1c1c`, surface `#262626`, green
foreground `#00dd33` and accent `#00ff41`. Its `text` variable is the CSS expression
`auto 87%`; the mounted card resolves that to neutral `#e2e2e2`. Thus neither
the raw `foreground` variable nor parsing `text` as a Rich color is the right
white endpoint. Resolve the current widget's neutral text ink, and bound the
monochrome intensity between the dashboard background and that neutral ink.
For colored themes, derive neutral intensities rather than tinting the marker.

Plan, all owned by root:

1. `widgets/card_inner.py`: retain the eight-frame pulse curve and single-cell
   glyph; replace hardcoded 0/255 gray endpoints with resolved dashboard tones.
   Keep zero, cached values and semantic placeholder rules unchanged.
2. `widgets/status_bar.py` plus `screens/dashboard_screen.py`: make the existing
   screen loading clock the shared phase source. Allow `StatusBar.set_loading`
   to receive an optional external frame; when supplied, stop its private timer
   and render from that frame. Keep the existing timer for standalone callers
   that supply no frame. Preserve external ownership through `_prime_footer`
   and pre-mount setup; stale timer callbacks must not advance an externally
   driven bar. Map the shared phase modulo four to the spinner glyphs, preserving its
   existing 200 ms cadence (two rotations per eight-frame fade). Cards, footer
   and captions consume the same phase, with common reset on stop/resume.
3. `widgets/surfboard/rack.py` plus `screens/surfboard.py`: add a small rack
   caption setter accepting busy/frame, called from the screen's loading hook.
   Reuse the existing idle endpoint from `_position_taglines`: effective label
   background blended with theme foreground using `DIM_FACTOR`. Blend toward
   theme accent, the active inner-frame ink, using the shared pulse fraction.
   At idle/suspend restore the exact current idle green. Keep both caption
   strings, geometry and Japanese character widths unchanged; no caption timer.
   Resize/reposition and theme changes must preserve/recompute the active phase
   instead of inadvertently resetting the caption color.

Alternative considered: leave the footer timer independent and approximate its
phase. Rejected because timer starts, suspend/resume and extra refresh callbacks
would permit visible drift. One shared phase is simpler to verify; the optional
footer frame keeps unrelated standalone callers compatible.

Validation: offline composited tests for neutral endpoints (including a second
theme), all eight caption/card phases and deterministic spinner mapping,
external-mode timer cancellation, pre-mount priming, resize, cached known
values, hidden/suspended views and idle restoration. Keep standalone-footer
timer tests. Assert phase advances trigger no reader calls or new timers, and
that an old timer callback cannot change the shared phase. Root then shows a
live 149×45 BOARDROOM rendering before hardening/review, runs affected/composing
tests and guards/doc pins, performs one final review with the usual bounded fix
wave, and commits locally. No full suite or network calls in tests.

Implementation evidence (2026-10-23):

- Shared 200 ms screen clock; eight gray/green fade phases, footer glyph
  selected modulo four. Standalone footer callers retain their original timer.
- Matrix bounds: neutral `#1c1c1c`–`#e2e2e2`; captions
  `#099b2b`–`#00ff41`. Idle restores the original caption color. Theme changes
  and resize resolve/reapply the current phase without restarting it.
- Live keyless 149×45 BOARDROOM capture shown before final verification:
  `/private/tmp/maxpane-card-sync/bright.png`; dim/bright frames at 1.05/3.33s,
  loaded WIP counts at 6.40s. Isolated temporary cache, no data-source changes.
- Offline affected/composing tests: **213 passed**; non-mounted guards:
  **128 passed**; documentation pins: **12 passed**. No full suite.
- Both concurrency mutations killed and restored byte for byte: removing the
  external footer clock, and allowing a late private-timer tick to advance it.
  Logs and captures: `/private/tmp/maxpane-card-sync/`.
- Final independent review: **Approved, no findings**. Four targeted tests
  passed; an additional external-phase mount mutation was killed/restored.

## Inverse indicator background — 2026-10-24

The owner requests the card loading character's background to animate exactly
opposite its foreground. Keep the current `◇`, neutral dashboard endpoints and
eight-frame screen clock. For phase fraction `f`, the foreground blends dark to
light by `f`, and the background by `1 - f`. Apply the background to the glyph's
single cell only; alignment padding, borders, captions and loaded values keep
their existing backgrounds. No reader, timer, sizing or missing-data changes.

This is Tier 2 because `widgets/card_inner.py` is shared, with fewer than 20
production lines expected. Root owns the single implementation package:
composited regression tests first, then the shared renderer. Verify all eight
phases, two themes, digit/stat/caption/BOARDROOM uses, padding and idle restoration.
Show a live keyless 149×45 rendering, then run affected/composing tests and guards,
one final independent review and a bounded fix wave before committing.

Implementation evidence:

- The inverse background is a one-character Rich span, so alignment padding
  retains its original background. No additional timer or data read was added.
- Live keyless 149×45 cold BOARDROOM captures, shown before final review:
  `/private/tmp/maxpane-card-inverse/dim.png` (1.00s), `bright.png` (1.90s),
  with loaded WIP counts captured at 4.61s using an isolated temporary cache.
- All eight new composited cases passed. Across affected/composing files,
  163 cases passed; one existing token-fetch call-count check remains failing.
  Initial color assertions required rerunning with inherited `NO_COLOR` unset.
  Fast guards: 128 passed, one existing CSS boundary check failed. Documentation
  pins: 12 passed. Both residual failures also reproduce with HEAD's original
  `loading_value` loaded into the test process; no baseline files were modified.
  Logs are in `/private/tmp/maxpane-card-inverse/`.
- Independent final review: Approved, no findings. Replacing the inverse
  fraction with the foreground fraction failed all eight new cases; the
  mutation was restored byte for byte. No full suite was run.

## Centered indicator side cells — 2026-10-24

The owner requests one animated blank on each side of the loading diamond only
in the middle of card boxes. Centered primary/preview indicators become ` ◇ `,
with all three cells sharing the inverse background; the diamond retains its
foreground pulse. Footer/caption and tabular indicators remain single-cell.

Tier 2, one root-owned package, fewer than 20 production lines expected: add an
opt-in padding argument in the shared renderer and use it at the centered body
call sites in NewsHeroCard, SurfboardCard and AgentRackCard's status readout.
Update composited tests first for
both themes/all eight phases, unchanged footer/stat widths, and confinement to
three cells. Show live 149×45 BOARDROOM, check affected/composing tests and
existing layout cases, then one final review. No timers, source changes or pins.

Evidence: the 11 focused cases passed after first failing for missing side-cell
backgrounds. Live keyless 149×45 rendering is in
`/private/tmp/maxpane-card-side-cells/dim-preserved.png`; the SVG export was given
`xml:space="preserve"` for PNG conversion so whitespace matches terminal cells.
Affected/composing/layout tests: 354 passed; the known token-fetch call-count
failure remains. Guards: 128 passed with the known CSS-boundary failure; doc pins:
12 passed. Those two baseline failures remain tracked in `surfboard_followups.md`.
Final review approved without findings. Its glyph-only background mutation failed
all seven padded-indicator cases while four caption/stat cases remained green;
the mutation was restored byte for byte.
