# BOARD card polish implementation plan

**Date:** 2026-10-15

**Status:** implemented, validated and approved in final review

**Tier:** 2 — shared hero renderer plus tests and measured layout evidence

**Size:** approximately 30 production lines; below 1,000 production lines

**Goal:** Make BOARD values easier to scan and give FLEET's paused state the
requested breathing room at the owner's **149 × 45** terminal.

**Architecture:** Keep the existing Textual/Rich renderer and primitive data
contracts. Add two opt-in class hooks to `NewsHeroCard`; only `BoardHeroCard`
enables them. Adjust FLEET's existing row declaration without adding a new
component, data source or rendering layer.

## Approved specification

This narrowly supersedes the relevant visual behavior in
`surf_board_values_plan.md`; its data meanings remain unchanged.

| Surface | Required result |
|---|---|
| LAUNCHES, WORKERS, EFFORT | Each of the three inset statistics rows has exactly one blank character immediately inside both vertical borders. Labels stay left aligned and values right aligned within the reduced interior width. |
| TOP SEAT, RECORDED, ACCEPT RATE | The large value glyphs use the existing numeric foreground green. |
| LAUNCHES, WORKERS, EFFORT values | The right-hand statistics values use that same green. |
| Card context | Labels, inset frames, headings, subtitles and normal outer footers keep their existing neutral styling; source/error indications retain their established semantics. |
| FLEET heartbeat | Remove the displayed heartbeat row and its associated separating row. |
| FLEET paused | Leave two blank rows below `paused`, or below `paused-detail` when that detail is visible, before RECEIPTS. Preserve the red paused count and green `none`. |

Keep existing values, clipping/compact-number behavior, literal hover details,
source states, refresh paths and equal card geometry. Other hero-card subclasses
must retain their current rendering. Use KISS, no dependencies, network-free
tests and no secrets. This is the approved design; no new mockup or approval
round is required.

## Ownership and dependencies

| Work package | Owner | Files and responsibility |
|---|---|---|
| Specification and plan | Planning agent | This document only. |
| Implementation and delivery | Root controller | `maxpane_dashboard/widgets/surf/news_hero.py`, `pool4_hero.py`, `swarm_board_hero.py`, `swarm_fleet.py`; their focused widget tests; composing screen/layout tests; measured pin evidence and relevant behavior/follow-up documentation. |

There is one implementation package: the shared renderer, BOARD opt-in and
composing geometry need a single integrated test cycle. No useful disjoint
production package warrants parallel implementation. The root controller owns
all files other than this plan; preserve concurrent edits and report issues in
another owner's files instead of changing them.

Dependency order: **plan → root TDD and implementation → live output and measured
geometry → final review → local commit**. No push is requested.

## Implementation and verification

- [x] Add focused failing compositor tests in
  `tests/widgets/test_surf_swarm_board_hero.py` and
  `tests/widgets/test_surf_swarm_fleet.py`. At 149 × 45 inspect
  `render_strips()` and actual character styles: one inner blank on each side
  of every statistics row, green large values and right-hand values, neutral
  surrounding text, no heartbeat, and two blank rows before RECEIPTS for both
  empty and nonempty paused lists. Update the prior neutral-value assertions
  to the approved behavior.
- [x] Run only these new/changed node IDs and confirm failures describe the
  requested visual differences. Cover refresh and resize so style and spacing
  survive record replacement and reduced width; retain existing source-state
  and clipping checks.
- [x] Add backward-compatible hooks to `NewsHeroCard`:
  `STAT_PADDING = 0` and `VALUE_COLOR = None`. For statistics, subtract twice
  the padding before fitting label/value content, then restore the blank
  cells. Build label and value spans separately so the optional value color
  cannot recolor labels. Apply the optional color to digit glyphs as well.
  Preserve existing default styles, including fired/watch status styling.
- [x] Include `STAT_PADDING * 2` in `Pool4HeroCard._update_title`'s existing
  statistics width budget (`label + value + 1`) so narrow BOARD cards still
  advertise truncated content correctly. Default zero preserves other
  consumers; pin this through the BOARD resize/clipping compositor test.
- [x] Set `BoardHeroCard.STAT_PADDING = 1` and its `VALUE_COLOR` to the existing
  numeric foreground color. Replace FLEET's sequence
  `'heartbeat', None, 'paused', 'paused-detail', None, 'contributors'` with
  `'paused', 'paused-detail', None, None, 'contributors'`; remove rendering
  code/imports used only by the deleted heartbeat row.
- [x] Run the focused tests green. Verify the default hooks preserve another
  `NewsHeroCard` consumer through `tests/widgets/test_surf_news_hero.py` and
  existing shared-renderer coverage. Keep changes limited to the approved
  semantics.
- [x] Show feasible live production output at 149 × 45 using the established
  app/live-render procedure before hardening layout evidence. Honor the
  owner's no-new-preview preference; do not create another mockup or
  confirmation gate. Record any inability to obtain live output accurately.
- [x] Re-measure BOARD `b` geometry with `scripts/measure_layout.py` and the
  established sweep in `tests/screens/test_surf_swarm_layout.py`. Update row
  pins and adjacent `#:` evidence from measurements, including the populated
  paused-detail case. Update relevant behavior docs and use
  `scripts/mutate.py` to prove the new behavior/pin assertions fail when the
  corresponding change is reversed and restore the files byte for byte.
- [x] Once before commit, run the touched widget tests and the composing
  files `tests/screens/test_surf_leaderboard_hero_live.py`,
  `tests/screens/test_surf_launch_contribution.py` and
  `tests/screens/test_surf_swarm_layout.py` using `.venv/bin/python -m pytest`
  with an isolated test home and `-n 4 --dist worksteal`. Unset `NO_COLOR` for
  style checks. Run `.venv/bin/python -m pytest -m "guard and not mounts_app"
  tests` and `.venv/bin/python -m pytest -m docpin
  tests/test_surf_registration.py tests/test_curator_registration.py`.
  Do not run the full suite; cite observed scoped results only.
- [x] Dispatch one final reviewer for the complete diff, with the repository
  reviewer contract and the approved spec. No per-package reviews are needed
  below the size estimate. Allow one fix wave, then one scoped re-review only
  if a fix changes production code. File Minor-only residuals in
  `docs/surf_swarm_followups.md` instead of widening scope.
- [x] Record actual validation and measured geometry, then commit locally
  with the scoped evidence. Leave no temporary plan workspace or capture in
  Git and do not push.

## Review focus

Check that padding remains inside the frame at narrow widths; styled values do
not tint labels or neutral footer numerals; non-BOARD shared-renderer consumers
retain their prior appearance; source failures and refreshes retain correct
unknown/error semantics; and paused-detail visibility preserves the measured
two-row gap without clipping RECEIPTS. These risks are owned by the root
controller's compositor and composing-layout tests above.

## Delivery evidence

Six focused compositor checks failed before implementation and passed afterward.
The affected widget/composing run passed 374 cases. The layout run passed 517
cases and exposed an obsolete 140-column stress expectation; the native CLI
measured the new padded boundary at 141, and all 87 width cases then passed
serially, completing coverage of the 518-case layout file. BOARD is 142×43;
the owner-size 149×45 production render used retained cache data after a failed
refresh, rather than claiming freshly fetched figures.

Five implementation mutants were killed and restored. Review verified default
consumer colors and BOARD refresh/resize styles, and the corrected screen
boundary killed its padding-budget mutant. Guards: 124 passed; docpins: 12
passed. No full suite. Final verdict: Approved, with one cosmetic narrow-width
unknown-color follow-up filed in `surf_swarm_followups.md`.
