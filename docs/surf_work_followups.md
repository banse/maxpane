# WORK IN PROGRESS follow-ups

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
