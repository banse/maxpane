# WORKFLOWS framed-diagram revision plan

Date: 2026-10-18. Tier 2. Owner requested larger diagrams resembling hero inner
cards and removal of this view's hero row. Contract: [PRD](workflow_guide_PRD.md).
Source research: [game mechanics](workflow_guide_game_mechanics.md).

The existing guide, local catalogue, lifecycle and boardroom route are already
implemented. This revision changes presentation while retaining all ten topics,
79 selectable nodes, source popups and caller-owned selection state. Expected
under 1,000 production lines excluding authored presentation plans. One final
review, no intermediate reviews, no full suite.

## Work packages and ownership

All writers work alongside other agents and user changes. Do not revert or edit
another owner's files. No child agents. File seams, rather than functions,
define ownership.

| Package | Exclusive owner and files | Dependency and result |
| --- | --- | --- |
| P0: revision specification | Planning architect: `docs/workflow_guide_PRD.md`, this plan | Current source/catalogue and UI read; diagrams and interaction requirements fixed before renderer work. |
| P1: outlined diagram renderer | Renderer implementer: new `maxpane_dashboard/widgets/workflow_guide_diagrams.py`, `tests/widgets/test_workflow_guide_diagrams.py` | Presentation-only authored placements/routes keyed by existing topic/node IDs, plus small Rich Text renderer. All roles, branches, joins, retries and failure states preserved. No imports from `data/`. |
| P2: view integration | Controller: `widgets/workflow_guide.py`, `screens/workflow_guide.py`, `themes/minimal.tcss`, composing screen tests | Remove hero composition and sizing; integrate P1, preserve interaction/source detail; enlarge diagram; mirror screen CSS. P2 may remove heroes and write failing tests alongside P1, but rendering integration depends on P1's interface. |
| P3: verification and documentation | Controller: registry/geometry tests if needed, README and follow-ups | After P1/P2: actual bundled-source preview, measured pins, scoped mutation checks, touched/composing tests, one final review and local commit. |

The controller owns every existing production file and shared CSS/test seam.
The catalogue, manager, model keys, boardroom routing and polling behavior do
not need edits. New dependencies, generic graph layout engines, graph services
and runtime HTML parsing are outside scope.

## Renderer handoff

Use authored presentation plans with primitive values: each node ID has a
position; edges have explicit elbow routes and optional literal labels; group
labels separate independent diagrams or observed/proposed paths. The agreed
`render_diagram` helper returns `DiagramRender(text, width, height, boxes)`.
The view passes selected topic, selected node ID, available content width and
theme colors. Returned geometry sizes the diagram and keeps selected cards
visible when scrolling is necessary.

Use four-row cards: role embedded in top border, two wrapped label rows,
bottom border. Adapt card widths within 18–25 cells, targeting
five columns within the open-index width. Build strokes and arrows as a small
cell canvas; place node cards after connector strokes so no line erases labels.
Resolve branch/join intersections deliberately. Click metadata must cover card
faces and borders. Literal source strings never become Rich markup.

Keep all 79 nodes individually addressable. The contracts-only six parallel
stages use one vertical column at y=0,4,...20, with shared inlet and outlet rails
and a PARALLEL label. Stacking is spatial, never a sequence: no arrows connect
siblings. Import/adapt are left of the group, judge/deploy/live to its right;
undeployed branches separately from judge. This bounds the dense graph to
24 rows while avoiding the crossings of a two-dimensional audit group.
For shapes, three distinct bands preserve CHAIN, FAN OUT / JOIN and DAG.
Failure/retry edges and route conditions remain visible. Site/growth proposed
paths must not read as observed successes. Intake's failed branch leaves
admitted, not paid or received.

The source catalogue's ASCII figure remains a provenance/reference representation;
the new boxed plans are presentation only. Validate plan IDs against the real
catalogue in tests, not by importing the data layer into the widget. The six
former hero facts remain available as DOCUMENTED FACTS in the source popup,
after references, without consuming graph space.

## Sequence and verification

1. Write focused failing tests for no hero row, outlined node labels, existing
   selection-to-detail behavior and larger diagram region. Confirm current
   behavior fails the new requirements before implementation.
2. Build authored plans and render all ten topics. Test all 79 nodes exactly
   once, connector endpoints, true parallel joins, failure/retry branches and
   separation of observed/proposed paths. Use real catalogue input in offline
   tests; no network or live clipboard.
3. Remove hero composition and hero-only imports/styles. Reallocate the freed
   eleven rows to the graph. Keep the topic strip, 28-column index, three lower
   panels, source popup and shared footer. Preserve topic/node/index state on
   resize, index toggle and reopening. Scroll selected nodes into view only
   where required, without resetting manual scroll on unrelated paints.
4. Mirror screen rules into production CSS. Render actual bundled documentation
   at **149×45** in Matrix: contracts, shapes, single-skill retry, site failure,
   open index and source detail. Show the result before changing pin evidence,
   writing measured documentation or requesting review. Incorporate the owner's
   visual corrections in this implementation phase.
5. Measure composed layout with index closed/open and all ten topics. Aim for
   roughly 27 diagram rows including title/source link and nine detail rows;
   these are a budget, not certified pin values. Dense content must scroll with
   honest hints if a smaller terminal cannot fit it. Re-sweep actual boundaries
   and update `#:` blocks only after preview. Keep app-wide pins unchanged unless
   measurements demonstrate necessity.
6. Confirm mouse clicks across card faces and borders, arrows, Enter popup,
   Escape return, retained state, literal text safety, and unknown/empty data.
   Regression tests must inspect composited output, not just a Text object's
   content. Prove pin tests fail for both under/overstated thresholds and one
   changed mapping/topology guard fails under a focused mutation; restore by
   inverse edit.
7. Once before commit, run touched and composing files with isolated HOME and
   worksteal, plus `guard and not mounts_app` and docpin tests as required by
   CLAUDE.md. Registration/mount tests are needed only if bindings or routing
   actually change. Do not run the whole suite.
8. One final reviewer receives the complete revision diff, repository reviewer
   contract, exact evidence and risks: truthful topology, 79-node preservation,
   literal text safety, click/keyboard selection and expanded-index geometry.
   One fix wave; scoped re-review only for production fixes. File Minor residuals
   in follow-ups and commit only authorized paths locally.

## Evidence

The framed renderer and view integration are implemented. Actual bundled-source
previews at 149×45 cover contracts, site, step shapes, retry, schedules, index and
source popup. Both CSS paths preserve every node at the measured 148×43 boundary.
Final checks and residuals are recorded in [follow-ups](workflow_guide_followups.md).
Existing static documentation dates remain dates of the source, never live
observation times.
