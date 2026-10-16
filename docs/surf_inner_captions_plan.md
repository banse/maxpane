# Surf inner captions implementation plan

**Spec:** [surf_inner_captions_spec.md](surf_inner_captions_spec.md)

**Execution:** Tier 2, one work package owned by the session implementer;
comfortably below 1,000 production lines. No per-task review or additional
implementation agents. One final review after live verification and hardening.
Use Python, Textual and Rich already in the project; follow KISS and the
existing widget/data separation. No new API, schema, dependencies or MVC layers.

## WP1 — Move and certify the twelve captions

**Ownership:**

| Files | Responsibility |
| --- | --- |
| `maxpane_dashboard/widgets/surf/work.py` | `_WorkHeroCard`, `SurfWorkHero` initial and updated records |
| `maxpane_dashboard/widgets/surf/oracles.py` | `_OracleCard`, `SurfOraclesHero` initial and updated records |
| `tests/widgets/test_surf_work.py`, `tests/widgets/test_surf_oracles.py` | Composited caption, frame-style, state and clipping regressions |
| `tests/screens/test_surf_work_layout.py`, `tests/screens/test_surf_oracles_layout.py` | Subtitle expectations and measured width boundaries |
| `maxpane_dashboard/screens/surf.py` | Only affected width constants and their existing `#:` blocks if measurement changes pins |
| `.claude/skills/terminal-layout/SKILL.md` | Only corresponding measured table values/descriptions if pins change |

Read-only reuse: `news_hero.py` (`HeroRecord`, bottom-border subtitle renderer,
source tooltip/footer), `pool4_hero.py` (`Pool4HeroCard._update_title`),
`scripts/measure_layout.py`, and existing shared style tests. The existing `docs/surf_work_followups.md` records the final review outcome;
no other docs are part of this change. Do not overwrite unrelated working-tree edits.

**Dependencies:** state/render regression → minimal implementation → fresh live
149×45 render shown to owner → in-situ measurements → pin hardening → final
verification → single final review. Measurement must follow the live render.

- [x] Add failing tests in the two widget files. Assert each of the six literal
  captions from the spec per view on the composited inner-bottom row; compare
  caption segments with the frame segments' full style and assert the outer
  footer is empty. Cover initial composition, fresh nonzero, zero, unavailable,
  stale and partial states, including ORACLES partial tooltip coverage. Keep
  count assertions and existing neutral/green/yellow/red expectations. Run the
  new node IDs and observe failure before implementation.
- [x] In both `compose()` and `update_data()`, populate records with
  `footer="", subtitle=caption` while leaving digits and accent expressions
  unchanged. Derive native card classes from `Pool4HeroCard` to reuse its
  subtitle-aware clipping detector. Remove WORK's obsolete outer-footer-only
  clipping calculation. Preserve `_frame_style()` overrides. Suppress partial
  outer footers locally, retaining inherited tooltip information. Run focused
  widget regression cases and adjust the existing WORK clipping test to exercise
  the inner subtitle budget.
- [x] Fetch through the existing keyless production path and show both live
  native views at 149×45. Verify exact words, placement, resolved colors,
  unchanged digits and geometry. Incorporate any owner corrections before the
  next step. Fixture screenshots do not satisfy this gate.
- [x] Update both layout `_render()` helpers to require `card.data.subtitle`
  rather than an outer caption or source-state footer. Then measure `w` across
  `work-capture`, `work-stress`, `work-empty`, `work-unavailable`, `work-stale`;
  measure `o` across `oracle-capture`, `oracle-complete`, `oracle-stress`,
  `oracle-empty`, `oracle-unavailable`, `oracle-stale`. For example:

  ```bash
  .venv/bin/python scripts/measure_layout.py w work-capture 110:160x45 --whole-from
  .venv/bin/python scripts/measure_layout.py o oracle-complete 110:160x45 --whole-from
  ```

  Probe one normal payload per view to locate its boundary, then check the
  remaining named payloads at that measured width and its neighbors. Expand
  the band if it does not bracket the first wholly fitting width. These ranges are probes,
  not asserted thresholds. Check the owner size and height boundaries at
  29/30/31 WORK rows and 41/42/43 ORACLES rows using 149 columns.
- [x] Use the measured binders in the two layout tests, renaming footer-specific
  tests to reflect inner captions. Certify measured width −1, width, width +1
  and the relevant boundary-set endpoints; below the boundary, require the
  lost caption and widen hint, and at/above it require complete fixed chrome.
  Keep equal nine-row cards, body panes and status visibility assertions.
  Change width constants and their existing `#:` records only from evidence;
  update the skill's two table rows if necessary. Retain 30/42 row pins unless
  the measured render proves otherwise; do not edit body geometry to hold a pin.
- [x] Use `scripts/mutate.py` to prove the focused tests detect a wrong count,
  a caption/frame style mismatch and each width pin shifted by −1 and +1.
  Restore mutations byte for byte. Record the commands and named failing tests
  in the handoff/commit evidence, without creating a report file.
- [x] Run touched and composing tests once before completion, with an isolated
  temporary HOME for the test subprocess and four worksteal workers:
  `tests/widgets/test_surf_work.py`, `tests/widgets/test_surf_oracles.py`,
  `tests/widgets/test_surf_card_inner.py`,
  `tests/screens/test_surf_work_layout.py`,
  `tests/screens/test_surf_oracles_layout.py`,
  `tests/screens/test_surf_work_screen.py`,
  `tests/screens/test_surf_oracles_screen.py`.
  Also run `.venv/bin/python -m pytest -m "guard and not mounts_app" tests`.
  Include docpin checks for the updated skill table. No registration surface
  changes and no full suite are expected; cite the last known green full suite.
- [x] Dispatch one final reviewer with the exact reviewer contract from
  `CLAUDE.md`, scoped to this diff and focused risks: all twelve captions,
  partial tooltip/footer behavior, inherited colors/digits and measured pins.
  One fix wave and a scoped re-review only if production code changes. File
  Minor-only residuals in the existing follow-up channel without expanding
  this implementation. Finish with no temporary plan workspace left behind.

**Done when:** the approved twelve captions are visible on the inner bottom
border with their frame's style, all existing values and geometry are preserved,
both live views were shown before hardening, measured boundary tests and scoped
checks pass, mutation proofs bite, and the single final review is resolved.
