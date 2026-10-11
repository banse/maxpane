# Surfboard offline status and detail layout plan

Date: 2026-10-11. Basis: [specification](surfboard_status_layout_spec.md).
Tier 2, below 1,000 expected production lines. Root coordinates two independent
implementation packages and one final review; no package-level reviews or child
agents. Preserve all unrelated/user work in the shared workspace.

## Ownership and dependencies

Production paths below are relative to `maxpane_dashboard/`.

| Package | Exclusive owner/files | Dependency |
|---|---|---|
| WP0: freeze the seam | Root confirms existing `meter_state='offline'` and status mapping | Specification |
| WP1: truthful card status | Data implementer: `data/surfboard.py`, `tests/data/test_surfboard.py`; narrowly related existing manager/activity tests only if needed | WP0 |
| WP2: render and layout | Root: `widgets/surfboard/rack.py`, `screens/surfboard.py`, `themes/minimal.tcss`, widget/screen tests, `tests/surfboard_fixtures.py` | WP0; integrates WP1 afterward |
| WP3: live render, measurement, final review | Root; one separate final reviewer | WP1 and WP2 |

WP1 and WP2 can run concurrently with no shared-file edits. Root owns any measured
pin/documentation updates and final integration. The planner owns only this spec
and plan. Report defects in another owner's files instead of fixing them.

## WP0 — plain-data seam

1. Keep existing card fields and widget signatures. Reuse `meter_state='offline'`
   for the OFF renderer and `status` for inset presence color.
2. Fresh OFF requires the same token's projected activity `idle` plus live
   `offline`; stale/unavailable projection must not promote retained worker state.
3. Preserve persisted activity history and projected remaining time. Rendering OFF
   ignores remaining time and paints hollow cells. Do not change activity storage.
4. Freeze new slot coordinates and BAY 10 behavior before root changes navigation
   assertions. Remove only the obsolete EARNINGS projection placeholder.

## WP1 — card projection and source honesty

1. Start at `surfboard.py::cards`'s local `activity_meter` helper and the adjacent
   selected-agent and rank-one card projections. Read `canonical_board`,
   `surf_swarm._seat_live_from_slot`, and `surfboard_activity.project` only as needed.
2. Add failing tests for fresh offline on each card; complete versus incomplete
   absence; old offline after failed/expired workers; unrelated selected and leader
   tokens; busy on one of several devices; and online idle with existing decay.
3. Implement the smallest shared presence projection for the two cards. Map working,
   idle, offline, paused, and unknown consistently. Keep acceptance/rank source
   semantics, clocks, and full detail intact; expose OFF through the existing meter
   field only after the freshness/known-state gate.
4. Remove the EARNINGS placeholder from generated rack data without introducing a
   BAY 10 data source. The widget synthesizes empty bay content as for BAY 11/12.
5. Run changed data cases and a consuming manager case. Prove the offline gate with
   a mutation that promotes stale or incomplete legacy offline to OFF; restore via
   `scripts/mutate.py`. Hand root exact node IDs and the final card-state mapping.

## WP2 — footer, inset, and central layout

1. Add failing composited widget tests for red OFF with only hollow cells,
   preserved orange-BUSY/green-full and accent-IDLE/green-orange-decay rendering,
   and LEADERBOARD/AGENT inset color parity. Update neutral-bay references in tests
   that currently find EARNINGS as their grey reference.
2. Teach `meter_text` the offline presentation. Keep existing activity arithmetic
   and stale/unknown treatment. Use the projected status consistently for both
   cards' inset border and status-colored text.
3. Update `SLOTS`: PORTFOLIO to `(1,5)`, AGENT to `(2,0)`, BAY 10 to `(2,5)`;
   retain BAY 11/12 and the top row. Ensure empty bays never focus or activate,
   and test arrow transitions and the unchanged active destinations.
4. Wrap the terminal and `#surfboard-detail` in one ordinary VerticalScroll within the
   center grid slot. Keep terminal ID, detail ID, descendant panel dispatch, and
   event ownership. Remove the old screen-level detail instance.
5. Render complete sanitized detail with wrapping and auto height; remove only
   the detail-specific widen hint/pre-truncation. Synchronize screen CSS with its
   theme block. Give the terminal a measured minimum and keep its controls usable
   when detail grows; overflow belongs to an observable scroll container.
6. Test actual regions and painted lines at 149×45 and resize boundaries. Verify
   terminal/detail left and right coordinates match, detail starts below the
   terminal, long detail survives completely, focus/refresh changes update it,
   and hostile/unbroken text neither leaks markup nor clips silently.
7. Update shared display fixtures and compositing helpers for the center container,
   new card order, and BAY 10. Preserve substantive assertions instead of merely
   replacing old expected strings or removing geometry checks.

## WP3 — verification and completion

1. Integrate both packages, then show the owner a real keyless live 149×45 render.
   Apply feedback before hardening pins or dispatching review.
2. Read the terminal-layout skill; measure width/height against content with normal,
   stress, unavailable, wide-text, and long-detail cases. The previous 144×36 pins
   are starting measurements. Preserve the three protocol columns and both end
   spaces; document any measured floor/pin change in its adjacent `#:` block and
   skill table, and recenter boundary tests. A full wrapped detail must remain
   reachable at small sizes and must not suppress real scroll hints.
3. During editing run named changed cases only, using `env -u NO_COLOR`. Once before
   commit run touched and composing files with the repository isolated-home,
   four-worker worksteal recipe: relevant data/manager tests,
   `tests/widgets/test_surfboard_rack.py`,
   `tests/widgets/test_surfboard_card_activity.py`,
   `tests/screens/test_surfboard_screen.py`, and
   `tests/screens/test_surfboard_layout.py`. Include terminal tests if their
   implementation/behavior changed. Run `guard and not mounts_app` and docpins
   when pinned documentation changes. No full suite or unrelated registration run.
4. Prove status/geometry tests bite with focused mutations. A moved pin must be
   rejected both above and below its measured value. Restore all mutations before
   final verification or review; coordinate shared-tree mutations with root.
5. Dispatch one final whole-change reviewer with the repository reviewer contract
   verbatim and named risks. Allow one fix wave, then one scoped re-review only if
   production changed. File Minor-only findings in the appropriate followups doc.
6. Record tests, mutations, live render, measured pins, and any residual limitations.
   Leave no task-owned planning workspace; preserve existing user files/worktrees.

## Measured result

The live keyless 149×45 preview shows three wrapped announcement-detail lines
under the terminal and the requested card positions. Width remains 144; height
falls from 36 to 35 because detail no longer consumes a separate screen row.
The terminal/detail width is 93 at the pin and 96 at the owner's width, with
a reserved center scrollbar gutter. Extreme detail scrolls visibly.

Final review caught the previous 11-row terminal floor hiding its market footer
when long detail consumes the remaining space. The measured 12-row floor keeps
the title, three log rows, command input, market footer, and borders visible.
A compositor regression first failed at 11 and passes at 12. Width/height pin
mutations on both sides of the measured values were rejected.
