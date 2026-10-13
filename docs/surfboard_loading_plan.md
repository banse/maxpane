# BOARDROOM loading display

## Approved specification

Tier 2: one dashboard, more than six affected production/test/documentation files.
The complete change is expected to remain below 1,000 production lines. One
implementer (the controller), no package reviews, one final whole-change review.
The project's superpowers exclusion applies.

The owner requests removal of all automatic visible stale/unavailable information
from BOARDROOM and a loading indicator while data is still being fetched:

- Retain cached values. A missing value renders as `—`; a failed read never becomes
  zero. No cached value, source clock, or source failure is discarded for display.
- Show `◌ loading` only while the relevant read is actually in flight. Clear it on
  success, failure, or cancellation; stale or missing data alone is not loading.
- Apply the display policy to card faces, previews, meters, outer footers, and
  terminal header/footer. Freshness/activity colors resume after loading; loading belongs
  in the existing footer display, without changing geometry.
- Preserve source states and clocks in tooltip/internal projections. This is an
  owner-authorized BOARDROOM display exception to the general visible degradation
  convention, not a change to source reliability or other dashboards.
- Leave empty agent bays unchanged. Never scrub literal event or reply prose,
  even when it contains words such as `stale` or `unavailable`.
- Do not change endpoints, public contract keys, shared widgets, layout pins,
  navigation, or persistence. Reuse the existing card `status` field for loading.

## Work packages and ownership

All implementation packages have the same owner because they meet in the manager
projection and card rendering. The responsibilities below are separate logical
steps, not concurrent file assignments. Each implementation step is scoped to
approximately 30–60 minutes; validation time depends on the existing tests/live read.

| Package | Responsibility and files | Depends on |
|---|---|---|
| 1. Lifecycle projection | `maxpane_dashboard/data/surf_manager.py`: `_project_hub`, `get_hub_snapshot`; `screens/surfboard.py`: cache-only repaints through the existing refresh guard; focused tests in `tests/data/test_surf_manager_surfboard.py` | Approved specification |
| 2. Card display | `maxpane_dashboard/data/surfboard.py`: retain ordinary WIP/ORACLES subtitles; `maxpane_dashboard/widgets/surfboard/rack.py`: `SurfboardCard.set_data`, `render`, `_update_meter`, `_token_preview`, `_top_agents_preview`, `_protocol_footer`; `tests/widgets/test_surfboard_rack.py` | 1's status semantics |
| 3. Terminal display | `maxpane_dashboard/widgets/surfboard/terminal.py`: `_header`, `_paint_footer`, `_paint`; `tests/widgets/test_surfboard_terminal.py` | 1's transient source projection |
| 4. Integration and verification | Relevant manager/widget tests; `tests/screens/test_surfboard_screen.py`, `tests/screens/test_surfboard_layout.py`; existing behavior notes and `docs/surfboard_followups.md` | 1–3 |

### 1. Project actual work state

Write failing tests first for cold start, cached refresh, and task completion by
success, failure, and cancellation. Determine loading from existing unfinished
tasks: `_hub_source_tasks`, `_full_task`, `_swarm_board_task`, `_pool4_task`,
`_work_reader.task`, `_oracles_reader.task`, and `_swarm_tokens_manager._tasks`.
Map each read to its affected card/source; unrelated work must not activate it.
Use transient copies at the final hub projection for header/footer loading state;
never rewrite persisted or authoritative source states. Retain the 30-second read cadence and nonblocking first paint. While reads are
pending, the existing one-second age timer requests a guarded cache-only repaint;
completion must clear loaders without offering another network read.

Acceptance: cached numbers remain identical during a refresh, absent numbers stay
`None` internally, finished tasks do not keep a loader, and the next hub snapshot
reflects completion without a new read. Internal source diagnostics remain intact.

### 2. Render cards without automatic degradation labels

Add failing compositor tests, then remove generated stale/unavailable decorations
at their rendering branches. Keep detailed diagnostics in tooltips. Do not perform
blanket substitutions on rendered content. Render the loader only in the existing
footer when status indicates active work; retain normal content and color rules.

Acceptance: no automatic stale/unavailable labels appear in card faces, preview
rows, meters, or footers; genuine zero and cached nonzero values survive; missing
values show `—`; empty bays and literal event/reply text render unchanged.

### 3. Render terminal source status

Add failing compositor tests for header/footer degradation labels and active source
loads. Consume the transient projection without changing the stored source state.

Acceptance: terminal source summaries omit automatic stale/unavailable labels,
show loading only for relevant active tasks, preserve source clocks for internal
diagnostics, and retain literal event/reply prose and existing width behavior.

### 4. Validate, show the live result, and review

1. During implementation, run only the changed behavior's test cases. Use injected
   transports and controlled tasks; automated tests must not access the network or
   rely on wall-clock sleeps.
2. Once functional, show the owner a keyless live BOARDROOM render at **149×45**
   before documentation hardening or review. Incorporate display corrections.
3. Prove the lifecycle tests detect a stuck or falsely active loader with
   `scripts/mutate.py`; record the named failing test and restore the edit.
4. Run the touched test files plus the composing screen and layout files once,
   with the project's isolated parallel-test setup. Run the fast guards:
   `.venv/bin/python -m pytest -m "guard and not mounts_app" tests`.
   Include doc-pin checks for changed behavior documentation; do not run the full
   suite or registration-mount checks when their surfaces are unchanged.
5. Update existing behavior notes and followups, then obtain one final review using
   the `CLAUDE.md` reviewer contract. Allow one fix wave and a scoped re-review only
   if production code changed; file Minor-only findings without expanding scope.

Final acceptance: lifecycle transitions, cached values, source diagnostics, prose,
empty bays, color semantics, and the existing layout all have focused evidence;
the owner has seen the actual live render before hardening and review.
