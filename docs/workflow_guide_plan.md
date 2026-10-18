# WORKFLOWS guide implementation plan

Date: 2026-10-18. Tier 2. Owner approved Variant 2 plus collapsible index.
Contract: [PRD](workflow_guide_PRD.md). Source research:
[game mechanics](workflow_guide_game_mechanics.md). Repository conventions
override this plan. Expected under 1,000 production lines excluding curated
source content; one final review, no intermediate reviews, no full suite.

## Work packages and ownership

All writers are working alongside other agents. Do not revert or edit their
files; accommodate the agreed contracts and report problems to the controller.
No child agents. Owned seams are files, not functions.

| Package | Owner / exclusive files | Dependency and result |
| --- | --- | --- |
| P0: specification | Planning architect: these three `docs/workflow_guide_*.md` files | Source and current integration read; frozen contract before dispatch. |
| P1: catalogue and manager | Data implementer: `maxpane_dashboard/data/workflow_guide_models.py`, `workflow_guide_catalog.py`, `workflow_guide_manager.py`; `tests/data/test_workflow_guide.py` | Starts from frozen PRD; portable static content for every topic, node, limit/example and source excerpt; cached local manager. No shared files. |
| P2: view and source detail | View implementer: new `maxpane_dashboard/widgets/workflow_guide.py`, `maxpane_dashboard/screens/workflow_guide.py`; `tests/screens/test_workflow_guide.py` | Parallel with P1 using handwritten primitive fixtures matching the contract. Six shared-style hero cards, two-row topics, authored diagram, three lower panels, retained selection, index and RecordDetailScreen popup. |
| P3: boardroom/lifecycle integration | Controller: `screens/dashboard_screen.py`, `screens/surfboard.py`, `app.py` only if needed; `themes/minimal.tcss`; shared test/registry files, README and follow-ups; preview tooling if needed | POLL_DATA default-on capability can begin parallel; route/access lands after P1/P2. Controller alone owns all shared files and any registration changes. No new game or Surf live keys. |
| P4: assembled verification | Controller | Depends on P1–P3; preview real packaged source, owner corrections, then layout/doc hardening, scoped tests and one final review. |

Keep the screen and popup in the view package's new screen file unless a clear
need justifies another owned new file. Reuse existing hero rendering and panel
primitives; no third-party layout framework, generic graph service or dependency.
P2 coordinates its screen CSS with the controller, who mirrors applicable rules
into the production stylesheet. Root owns the common lifecycle flag and tests.

## Sequence and verification

1. Freeze the PRD payload and public constructor/update names. Dispatch P1 and
   P2 in parallel. Each implementer writes failing behavior tests first, then
   the smallest implementation. Existing user changes remain untouched.
2. P1 tests all ten ordered topic IDs; six stats/topic; unique nodes and exact
   diagram-reference resolution; source date/version; branch coverage for all
   three shapes, retries, site failure/remedy, intake failure/refusal and schedule
   outcomes. Verify units and that sample counts are historically scoped. No
   network or filesystem source read from the manager. Shared data models never
   import widgets; widgets never import data modules.
3. P2 tests composited content, selection-to-explanation/source correctness,
   topic arrows/node arrows/click/Enter, index toggle and invalid stored state.
   Cover long prose, literal markup and Unicode as content, scrolling, close
   paths, and empty payload. It must not certify final layout pins before the
   real-source preview. New tests must assert behavior, not only constants.
4. Controller adds `DashboardScreen.POLL_DATA = True`; periodic timer creation
   is conditional, initial/manual refresh behavior unchanged. A test verifies
   default dashboards still poll and the static guide has no poll timer across
   resume/suspend. The shared loading timer is presentation, not a data poll.
5. Controller wires the clickable title label and `g` entry. Assert original
   centered boardroom title and rack positions remain; input fields retain a
   typed g; one activation opens one guide; Escape restores the same boardroom;
   reopening retains selection/index. Keep the existing game registry intact.
6. Show the real packaged-source guide at **149×45**, including a branching
   topic, the site failure, open index and source detail. This task has no live
   API: its genuine data is the dated source bundle, not fabricated fixture
   metrics. Incorporate owner corrections before pin evidence or review.
7. Measure collapsed/expanded layout and resize boundaries in the actual
   composition and production CSS; ensure all ten diagrams remain reachable.
   Add evidence blocks only for measured pins. No existing global pin increase
   without demonstrated necessity. Complete focused mutation proof: disable
   no-poll capability, misroute one node detail, or lose retained selection and
   show the named behavior test fails; restore each mutation by inverse edit.
8. Run touched tests and relevant composing files once, using isolated HOME
   and worksteal where safe. Run `guard and not mounts_app`; because a key/route
   changes, include the applicable registration/mount guards named in CLAUDE.md.
   Run docpin checks after documentation edits. Never run the whole suite here.
9. One final reviewer receives the complete diff, repository reviewer contract,
   exact tests/evidence and risks: static no-poll lifecycle, navigation/input
   collision, source provenance, and real compositor geometry. One fix wave;
   scoped re-review only if production fixes result. File Minor residuals in
   follow-ups, update completion evidence and commit only authorized paths.

## Integration decisions grounded in current code

`DashboardScreen.on_screen_resume` sets a timer for every non-ReaderHandle;
passing None/zero as its interval is not a supported no-poll contract. A
default-on capability is the smallest explicit change and avoids overriding
shared lifecycle. The static catalogue manager has no I/O, so no reader thread
registration or reader scheduler change is necessary.

`SurfboardScreen` already pushes nested NFT/token screens; a nested guide keeps
the boardroom return model and excludes it from `_GAME_CYCLE`. Boardroom `g`
and app-level q/t/tab/m do not collide in inspected bindings. Respect focused
Input consumption and cover it with a test. `RecordDetailScreen` supplies the
existing modal frame and close behavior; subclass its content/title only.

## Remaining evidence and assumptions

- Source content is a deliberately frozen documentation snapshot. Updating it
  is a later content change with provenance, never an automatic live claim.
- The owner approved the design; precise pins and observed production line
  count remain unmeasured until the assembled preview.
- No production implementation or tests were written by the planner. The
  completion step records actual commands and results; this plan claims none.
