# Boardroom launch and research job counts

Tier 2, under 1,000 production lines. One implementation owner (root), one final
review. The classification audit is read-only and independent of implementation.

## Accepted behavior

- WIP counts executing launch jobs, including jobs explicitly belonging to a launch
  workflow. A standalone site, audit or code job is not automatically a launch.
- RESEARCH counts executing goal/report/research jobs and oracle jobs, once per job
  ID. The explorer's normal Now list excludes oracle jobs; RESEARCH includes them.
- Each footer counts distinct busy seats assigned to jobs in that card's category.
  A seat with several assignments in one category counts once. SWARM remains the
  distinct busy-seat total for every category; category totals are not subtracted
  from independently observed totals.
- Fresh complete active-job coverage is required, including old executing jobs.
  Failed/incomplete reads remain unknown. Existing last-valid content and color
  retention during refresh remains intact. Layout, labels and navigation stay put.

## Evidence and implementation

Current official docs and explorer were read on 2026-11-11. `/jobs` has no working
state filter: `state=executing` silently returns terminal rows too. Recent history
also omits an older executing oracle job. Reuse the bounded discovery, oracle ID
seeding, fresh details and `/swarm` executing-count agreement already in the reader.
Classify from explicit detail fields, never objective prose or the complement of
research. `job.continue` does not deploy; an ancestor launch alone proves nothing.

1. Commit trimmed captured job fixtures; add failing mixed-category, coverage,
   distinct-seat and composited-card regression cases.
2. Root owns the reader, pure category projection and card wiring. Reuse its bounded
   standing reads for both categories; no extra unbounded worker fan-out.
3. Render current keyless data at 149 x 45 and show the owner.
4. Update relevant conventions, run touched/composing files and fast guards, prove
   decoder behavior with mutation, request one final review, commit exact paths.

## Validation

- Live keyless render at 149 x 45: WIP 0 launch jobs / 0 working; RESEARCH 5 jobs
  (four goals plus the old oracle) / 4 assigned seats. Complete active-set coverage
  was 6/6; the remaining job was a standalone site. Render shown before hardening.
- 430 touched/composing checks passed; 17 existing harness failures reproduced on
  unchanged `0c4d5d6b`. Fast guards: 130 passed; the existing TOKENS/SWORN CSS-slice
  failure also reproduced there. No new failures, no full suite.
- Final focused checks after the new-job observation-time guard: 17 passed.
  Documentation pins: 12 passed. Four classification/coverage/deduplication
  mutations killed and restored byte for byte.
- Final review: no production findings; one Important fixture-convention finding.
  Moved synthetic roster/standing responses into the committed fixture with explicit
  provenance. Final category file: 16 passed. The reviewer also ran seven named
  cases, including existing refresh retention, and killed a mutation removing the
  job-creation-time guard. Test-only fix; no production re-review required.
