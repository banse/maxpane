# WIP active-job context — implementation plan

The owner asks: “for all active jobs load the whole workflow too for that job
even when the jobs are older.” The owner also approved “include project
history,” including earlier jobs with no formal workflow. This extends
`surf_work_PRD.md`; its unchanged interactions and count definitions remain
in force. The controller owns the companion spec and freezes the contract
before implementation. Tier 2, estimated below 1,000 production lines: two
independent implementation packages, one final review, no package reviews.

## Contract and collection decisions

- Add only `projects` to the public work payload. A project has exactly
  `id`, `objective`, `job_ids`, `workflow_ids`, `active_job_ids`. Existing
  Job, Node and Workflow fields and widget signatures stay unchanged.
- Admit a project from a freshly executing job detail only when its UUID,
  versions and inclusion of that seed are valid. Merge matching projects
  and deduplicate IDs. Validate direct detail identity and project membership;
  conflicting membership is partial evidence, never an arbitrary reparent.
- Persist internal `active_scan_complete` and current job/workflow scope
  IDs. Do not leak these keys into the public payload. Current scope includes
  recent list records, freshly discovered executing jobs and their current
  workflow relationships. Added historical context alone never increases
  JOBS, WORKFLOWS, BLOCKED or working-node counts. In particular, old blocked
  project versions are context, not newly blocked current work.
- Revalidate previous executing IDs; cached state alone cannot make a job
  current. Fetch the recent jobs/workflows pages, then discover older active
  jobs with existing `fetch_jobs(limit=500, before=...)`. The overview's
  executing count is a stopping hint, never a displayed substitute. Stop
  when the observed active target is met, the listing ends, the cursor fails
  to advance, a read fails, or the scan budget is reached. A missing or
  malformed count requires scanning to exhaustion or marking discovery
  partial. Conflicting counts also mark coverage partial.
- Collection budgets: initial 100 recent jobs, then at most 100 total discovery
  pages of up to 500; 512 unique job detail reads, 128 direct workflow reads,
  and 256 versions per project;
  bounded admitted rows must use matching persistence limits. Active seeds
  have first priority, then their workflows and project history, then other
  existing unfinished/blocked context. Preserve references beyond a budget
  as unresolved/metadata-only context and mark partial; never silently drop
  them or claim complete history. Do not recursively expand unrelated projects.
- Use existing `fetch_overview`, `fetch_jobs`, `fetch_job`, `fetch_workflows`
  and `fetch_workflow`; no client endpoint, host pool or manager pipeline is
  needed. Deduplicate calls across seeds, versions and workflow links. A valid
  version supplies a metadata-only Job when its detail cannot be loaded;
  missing nodes remain `None`, not an empty list.
- Initial list failure or all-host busy retains the entire last-good snapshot
  and clock with existing backoff. Later discovery/context failure may publish
  successfully read context as partial. Discovery failure with no observed
  executing jobs must not become zero jobs/seats/build/review. Cancellation
  publishes neither a partial replacement nor a failed-read timestamp.
- Migrate validated legacy snapshots to `projects=[]` with incomplete context
  until a new collection. Validate new scopes, references, uniqueness, strict
  booleans, caps and timestamps at the persisted trust boundary.

## Ownership and dependencies

| Package | Owner | Exclusive files |
|---|---|---|
| Contract/spec | Controller | `data/surf_models.py`, companion spec, contract agreement tests |
| Data | Data implementer | `data/surf_work.py`, `data/surf_work_reader.py`, their two test files, new work fixtures |
| Tree/detail | UI implementer | `widgets/surf/work.py`, `tests/widgets/test_surf_work.py` |
| Integration/closeout | Controller | Work screen/layout tests if necessary, Surf rules, followups, integration evidence and commit |
| Plan | Planning agent | This file only |

Paths above are under `maxpane_dashboard/` or `tests/` as appropriate.
Implementers are not alone: do not revert others' edits, change another
owner's files, spawn agents or commit. Report seam defects to the controller.
Data and UI run in parallel only after the public contract is frozen.

## WP1 — complete current discovery and historical context

Owner: data implementer.

1. Write failing decoder/projection tests, then add project normalization,
   membership checks, current-summary scopes and persisted migration. Keep
   the projection pure with injected time. Public counts remain independent
   of the local tree filter.
2. Write failing reader tests, then add bounded older-active discovery and
   deduplicated job/workflow context lookup through the existing client.
   Preserve single-flight, consumer lifecycle, TTL and cancellation behavior.

Acceptance: a job older than the first 100 records appears with its complete
reachable project/workflow context; two active seeds sharing a project cause
one project and one lookup per ID. Terminal or historical blocked jobs remain
inspectable without inflating current totals. Missing reads and capped scans
are distinguishable from a proven empty result.

Tests: older active job on a later page; known zero and missing overview;
nonadvancing/malformed cursor; duplicate pages and IDs; page/detail limits;
same project with multiple seeds; workflow absent from the recent page;
workflow sibling absent from recent jobs; `workflow: null`; malformed project,
version or detail identity; failed detail versus genuine empty nodes; old
blocked/terminal context; stale cached executing job completing; busy failure;
cancellation during discovery and fanout; corrupt and legacy persisted data.

## WP2 — project/workflow tree and related-job details

Owner: UI implementer.

1. Write failing compositor tests, then render Project → optional Workflow →
   Job → Step. Use existing workflow links for nesting; unresolved workflow
   members remain directly reachable under the project. Render each job once,
   preserve standalone workflow/OTHER JOBS behavior, and include terminal
   project branches as context. Active paths expand by default; historical
   branches start collapsed. Do not change layout pins or card geometry.
2. Add project selection details and project-related jobs to the existing
   detail pane. Preserve stable selection, collapsed state, newest executing
   default selection, local search and all/build/review/blocked filters.
   Searches retain matching descendant paths; filters never alter heroes.

Acceptance: old history can be expanded and selected; the selected detail
matches its row after refresh; no duplicate node keys or disappearing active
job behind a collapsed default ancestor. Existing markup/address helpers
remain the only formatting/link boundary; widgets import no data code.

Tests: shared project seeds; project with and without formal workflows;
history older than the recent page; metadata-only/missing children; terminal
workflow context; stable IDs across regrouping; refresh/collapse preservation;
project/job/step search; each role filter; malicious-looking text; unchanged
hero totals and existing keyboard routes. Assert composited output.

## WP3 — integrate, show and verify

Owner: controller. Depends on WP1 and WP2.

1. Show a live keyless 149×45 WIP render with real active projects before
   documentation hardening or final review. Verify older history is reachable
   and no new geometry pin is needed. Respect existing loading behavior;
   this change must not restore stale/unavailable notices the owner removed.
2. Prove the changed collection/projection and grouping tests bite using
   `scripts/mutate.py`: omit older discovery/project history, count historical
   blocked jobs, or bypass project grouping. Restore
   each mutation before the next check.
3. Run touched data/widget files and the composing work screen/layout tests
   once, plus fast guards and applicable docpins. Isolate HOME for parallel
   pytest and unset `NO_COLOR`. No full suite, server, deploy or push.
4. Dispatch one final review with the exact CLAUDE reviewer contract, scoped
   risks and evidence. One fix wave, one scoped re-review only if production
   changed; file Minor-only residuals in `surf_work_followups.md`. Commit only
   task files. Document actual caps and remaining coverage limitations.
