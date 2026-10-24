# WORK IN PROGRESS follow-ups

## Recent activity and shared workflow checkpoint (2026-10-24)

WIP now defaults to all statuses in a rolling 24-hour activity window. The owner
confirmed that an old-created record updated today belongs in the window. Open,
Blocked, Build and Review remain available for active work and older context.
Completed jobs/workflows and accepted steps use dim theme foreground, matching
the dark-green BOARDROOM captions. Hero metrics keep their active/current meaning.
See `surf_work_24h_plan.md` for the contract and package ownership.

Comparison found two catalogue consumers calling the same mutable workflow pager
with separate certified checkpoints. WIP, BUILT BY SWARM and cards now reuse one
reader-owned workflow loader/checkpoint, with serialized refresh and cancellation
owned by its caller. The all-history catalogue remains available to BUILT BY SWARM.
Cold job discovery catches older records updated within the activity window before
certifying its checkpoint. Completed jobs enter bounded optional detail rotation.
Visible recent details publish before historical reconciliation, including when
project context is still being validated; project grouping remains withheld until
validated. One offer still admits at most 24 optional reads, four at once, for
eight seconds total across its foreground/reconciliation phases.

Live keyless captures at 149x45 on October 24 around 01:23–01:29 UTC showed 82
recent jobs and no recent workflows. The latest served workflow activity was
October 21 at 21:13:47.694 UTC. First publication was 5.288s before moving optional
details forward and 5.247s afterward. Detail coverage increased from 1 to 8 by
14.26s afterward; the earlier long capture still showed 1 at 65.696s. These are
observed sequential workloads, not a controlled latency benchmark. Historical
reconciliation remains an occasional background cost; the final 40-second cold
capture was still partial, with 8/82 expected details. Subsequent polls continue
the bounded rotation. No complete-hydration or full-scan speedup is claimed.

Existing test failures reproduced on unchanged HEAD `210f9e57`: the SWARM manager
key expectation omits `swarm_launch_read_ts`, and the widget import guard omits
the already-used pure `surf_launch_checks` module. The existing SWARM TOKENS CSS
guard also still includes the later SWORN block. These are outside this change.
Sixteen existing `test_surf_card_current.py` fixtures also lack the manager's
`_refresh_workflow_catalogue` method; the data implementer reproduced all sixteen
against HEAD modules.

Final review found one Important regression: filtering optional workflow stages
by age broke linked-job hydration for older Open/Blocked workflows. The single
fix wave restored age-independent workflow-stage hydration. Open work gets first
priority, followed by recent jobs and then stopped history. Unlisted stages retain
their original observation times across reconciliation only while their parent
workflow listing is unchanged; changed links/revisions invalidate the evidence.
Pending project grouping remains withheld. Eleven scoped age/context/priority
cases passed, including eight that failed before the fix. The affected/composing
data run passed 246 tests after the fix.

Scoped re-review approved the fix: 13 cases passed; restoring the workflow age
cutoff and removing parent-revision invalidation both failed their named tests.
The initial review also killed shared-lock and doubled-budget mutations; the
session's default-filter and completion-color mutations were killed. All restored.

The old F-C1 caption-test follow-up below is resolved for WORK: expected inner
caption literals are now independently listed. ORACLES remains untouched.

## Inner captions (2026-10-16)

The twelve native WORK and ORACLES captions now occupy their inner bottom
borders and inherit the complete frame style. Fresh live 149×45 renders were
shown before measuring the new width pins: WORK 138, ORACLES 143. Height pins
remain 30 and 42. All eleven payload variants fit at and above those widths,
and the boundary checks detect clipping below them. The scoped run passed
137 tests plus 128 fast guard/docpin checks. Nine implementer mutations and
the reviewer's partial-footer mutation were killed and restored.

Final review approved with no Critical or Important findings. Minor F-C1:
the caption tests in `tests/widgets/test_surf_work.py` and
`tests/widgets/test_surf_oracles.py` read their expected wording from production
`CARDS`. They protect placement/style but do not independently pin literal
wording: `assigned seats` → `assigned teams` survived the WORK `[ok]` test.
Bind the approved literals independently when those test files are next touched.
The review mutation was restored; production retains the approved wording.

The initial newest-100/24-detail limitation was extended on 2026-10-16.
Active discovery now scans up to 100 total pages, revalidates prior active IDs,
and loads each active project's versions and linked workflows by ID regardless
of age. Collection remains bounded: 512 required job details, 128 workflow
details, 256 versions per project and 24 optional background details. Missing
reads, inconsistent discovery and caps remain partial coverage.

No estimated completion percentage is shown; step states and timestamps are
the available evidence.

Final review: four Important findings were fixed in one wave and all four
were verified addressed. No Critical or Important findings remain. The fixes
cover conservative read-start freshness, workflow search/filter/default
selection, required detail fields, and the page-count contract. No Minor
findings were raised.

## Active project history (2026-10-16)

The live keyless 149×45 render showed three active projects and all ten of
their job versions with steps, including completed work from October 11.
Historical blocked attempts do not increase current blocked-job totals.
Project grouping, folding, search and stable selection use the existing tree
and panel geometry. See `surf_work_context_spec.md` and its implementation plan.

Bounded coverage remains intentional: the general workflow list is still the
latest 100; direct references from active project history extend it. The UI
reports partial coverage when optional background details remain unloaded,
even if all versions of the active projects were fetched successfully.

Integration found four obsolete layout expectations for the removed stale/unavailable
card labels; the layout tests now require the retained semantic footer instead.
The unrelated widget import guard still fails on `swarm_latest` importing the pure
`analytics.surf_launch_checks` module missing from its allowlist. Confirmed unchanged
on HEAD `ae74f425` in an isolated archive; leave this guard repair to its own scope.

Final review found one Critical pagination overlap: an older job revalidated
directly could make a legitimate cursor page look repeated and hide another
active job. The single fix wave separated listing-page IDs from stored job IDs.
The regression asserts both active jobs, unique rows, one detail read per job
and complete coverage; scoped re-review approved the fix. No remaining review
findings. Ten implementer mutations and one reviewer mutation were killed and
restored, covering history, counts, discovery, memberships, busy reads and folding.

## Boardroom card replacement (2026-10-13)

The WORK IN PROGRESS card replaces PORTFOLIO and reuses the same bounded reader.
Final review approved it with no findings. A fresh keyless 149×45 render was shown;
the 144×37 rack boundary remains unchanged. Actual-app navigation preserves an
in-flight read between the two views and cancels it on leaving both.

Unrelated existing issue: `PortfolioHero.update_data()` calls a missing
`render_box` method in `widgets/portfolio/__init__.py:53`. The Portfolio screen
file has nine failing tests both before this change (HEAD d67d83cb, isolated
checkout) and after it; 15 tests pass in both runs. Track this separately from
the replacement card. The old card-opening test now opens the retained Portfolio
screen directly, preserving that screen's return-navigation coverage.

## Incremental catalogue loading (2026-10-23)

WIP now persists validated jobs/workflows catalogues, merges update deltas with a
five-minute overlap, and reconciles the full catalogue every ten minutes. Current
work publishes before historical scanning, old project versions/workflow details
and optional detail enrichment; unchecked project grouping appears only after
its context reads validate. The
existing reader thread and view cancellation remain in charge; polling is 30s
from read start, with no queued catch-up cycles. Optional work is capped at four
concurrent reads, 24 admissions and eight seconds per cycle. Source checkpoints,
observation clocks and failure states stay separate from display data.

Measured with live api.imd.fun and isolated cache copies: regular jobs discovery
fell from 31 pages to one delta call. The first adapted warm publication took
3.450s; the production reader-thread/manager/screen integration painted cached
content in 1.597s and refreshed content in 7.549s. These are different observed
workloads, not a controlled same-payload benchmark. A legacy cache published a
partial current snapshot at 5.811s while baseline reconstruction finished at
45.833s. Full scans therefore remain an occasional cost. The live 149x45 render
was shown before final review. See `surf_wip_incremental_plan.md` for evidence.

Known upstream limitation: child changes may not bump parent updatedAt. Active
job details are still revalidated; periodic full reconciliation remains necessary.
An exceptionally slow full jobs scan exceeding the five-minute delta overlap
retains the foreground and retries instead of promoting an unsafe checkpoint.
Multi-cycle workflow baselines catch up updates since their scan start. Unknown
counts remain unknown; an omitted executing bucket means zero only with a complete,
validated state-total witness and complete discovery.

Validation baseline: the unrelated SWARM TOKENS CSS agreement guard fails because
its extraction includes the later SWORN CSS block. The identical failure was
reproduced on untouched HEAD 5d17872c in a temporary git archive. The other 128
fast guards passed. This task does not change either stylesheet or that guard.

Final review raised four Important findings; the single fix wave added regressions
for malformed reconciliation, hidden creation-time boundary ties, historical context
blocking first publication, and mixed optional failure/timeout rollback.

Scoped re-review: Approved; all four findings addressed, with 19 focused cases
independently verified. Final isolated four-worker touched/composing run: 683
passed in 14.77s. Seventeen implementer mutation checks and the reviewer's
boundary mutation were killed and restored. The full suite was not run.
