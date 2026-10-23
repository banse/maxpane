# SURF loading review — 2026-10-23

Audit base: `9511bb26`. Scope: BOARDROOM and the SURF family, including nested
NFT/token/detail views. Keyless and read-only. No provider replacement, new
service, public model key, or layout change. Implementation follows the
[plan](surf_loading_review_2026_10_23_plan.md).

## SWORN identity and acquisition

The owner's [Explorer reference](https://explorer.imd.fun/jobs/2759fb3d-89a9-4c2f-a5e3-6472208fac0e)
is a workflow despite its `/jobs/` URL. The public API's workflow route links:

- workflow `2759fb3d-89a9-4c2f-a5e3-6472208fac0e`;
- contracts job `4f2565af-3ba6-4fde-9444-473ed6b1ee68`;
- launch 2404 / `1377d17c-3f09-49e8-87e7-20a07ad45ea9`;
- Ethereum Registry `0x0da2679000ea5380d1361cc3cca7d4e8c881f766`;
- repository `identity-md-launches/launch-2404-renderer-composer-registry`.

The Registry was already a retained discovery candidate, but its inspection and
job hydration were queued behind unrelated work. The unchanged direct inspector
proved ERC-721 in 1.303 seconds with 10 HTTP/10 RPC requests. This isolated proof
latency is not dashboard latency. The real contracts-job response was 48,594
bytes, largely repeated project-version objectives; the old 32KiB extraction
limit discarded it entirely. The corrected compact payload is 9,641 bytes and
retains all ten version IDs, direct workflow/launch links and explicit truncation.

The older Sworn deployment in launch 2147 has a different direct request identity.
It remains historical evidence. No address/name override or name-only merge was
introduced; a newer website continuation alone is not a new contract deployment.

## Corrected data paths

1. Reader publishes persisted observations before acquisition or cancellation
   barriers. New acquisition still waits for retired reads to drain.
2. Reader reconciles the passive snapshot once after fetch, catching enrichment
   that completed between monitor ticks.
3. Seat/record selection invalidates its own collection throttle and retires old
   collection work immediately.
4. BOARDROOM uses the same workflow lifecycle as WORK: paused is not active and
   an unrecognized status remains unknown.
5. Site/project facts revalidate after 600 seconds, retry after 60 seconds, and use
   a bounded oldest-attempt batch of three. Failed reads retain their observation
   time; changed job identity cannot borrow old membership.
6. Launch-fact retention keeps up to 2,000 facts ordered by successful acquisition
   and validated version, allowing explicitly acquired old launches to survive
   publication/reload. Other existing 500-entry caps are unchanged.
7. WORK retains up to 128 revision-bound optional detail observations and rotates
   a persisted cursor; required active/context jobs still go first. Optional
   acquisition remains 24 jobs per round with a 120-second reuse period.
8. Token contributor timestamps come from job-observation envelopes, including
   the oldest contributing frontend/contract read. Memo hits cannot manufacture
   freshness.
9. NFT priority follows exact workflow/job/launch joins and uses persistent,
   bounded weighted progress. Priority never substitutes for deployment proof.
10. NFT compaction retains consumed version relationships instead of repeated
    embedded objectives, avoiding permanent rejection of large job histories.
11. Newly proven collections receive up to three HTTP requests for metadata
    before the factory lane. Existing factory stages retain their progress.
    Total NFT budgets remain 24 HTTP / 256 RPC / 15 seconds; BOARDROOM remains 12/96.

## Live measurements

The [counted measurements](research_notes/surf_loading_review_2026_10_23_measurements.json)
use production managers and ReaderRuntime with isolated copies of the user's
caches. Each scope was observed for 35 seconds, left, drained, checked for new
dispatch, then reopened. Existing cache files were not modified by this probe.

| Scope | First snapshot, seconds | HTTP attempts in sample | First idle, seconds |
|---|---:|---:|---:|
| BOARDROOM | 2.001 | 35 | 22.737 |
| NEWS | 1.244 | 78 | 27.912 |
| SWARM | 1.291 | 44 | not reached |
| AGENT | 1.495 | 46 | not reached |
| LEADERBOARD | 1.175 | 3 | 7.572 |
| WORK | 1.544 | 26 | not reached |
| ORACLES | 1.294 | 1 | 6.157 |
| PROTOCOL | 1.213 | 51 | 18.724 |
| MARKET | 1.457 | 22 | 9.110 |
| LAUNCHPAD | 1.269 | 122 | not reached |
| TOKENS | 0.199 | 21 | 7.383 |
| TOKEN DETAIL | 0.198 | 3 | 2.232 |
| PORTFOLIO, no wallet | 0.052 | 0 | 0.052 |

All 13 scopes reopened with an immediately available local snapshot. All had zero
new HTTP dispatch during the 250 ms observation after awaited cancellation/drain.
Long collectors skipped the 30-second offer; completed collectors made at most
one new offer at that deadline. There was no catch-up burst. Gated offline tests
cover longer cancellation, overlapping offers and late generations.

These are bounded observations, not all-history completion times or a before/after
performance comparison. The no-wallet portfolio sample does not exercise balance
or claim reads. The local WORKFLOWS guide has no acquisition poll; its existing
integration test covers that lifecycle. Public providers returned one429 and
one403 during the native samples; existing fallback behavior remains.

The real NFT screen was rendered at 149×45 using the production stylesheet and
reader. From a fresh copy containing 24 records and no target row, the normal
pipeline published **Sworn / SWORN at the supplied Registry after 163.695 seconds**,
in the sixth 30-second cycle. The correct launch 2404 repository/README appeared.
Live totalSupply was 8; the separately labeled explorer holder estimate was 8.
No target proof or row was injected. Each cycle used 22 attempted HTTP reads plus
two reserved shared-job slots, at most 48 RPC calls, and 10.01–14.729 seconds.
Historical Sworn and the new deployment remained separate, with the newer row
selected. This demonstrates eventual backlog progress, not an instant cold scan.

[Local live render](/private/tmp/maxpane-loading-review/nft-sworn.png), shown to
the owner during verification. Screenshots remain untracked under repository
policy; the identity, clocks and request counts are in the versioned JSON above.

## Validation and review

- Entity package: 249 passed; one unrelated key-set test fails identically on exact
  baseline 9511bb26. It omits pre-existing `swarm_launch_read_ts` from its expected
  keys (`test_surf_manager_swarm.py::test_board_keys_are_exact_before_finalization_and_survive_cold_start`).
- Combined reader/WORK/card/token/R2 and composing UI run: 488 passed; one new
  private-WORK roundtrip inconsistency was corrected. The complete WORK decoder
  and reader files then passed 133 tests.
- Final NFT discovery/manager/cache/R2 package: 98 passed. NFT screen: 34 passed.
- Fast guards: 128 passed. Documentation pins: 12 passed.
- Named mutation probes: reader/WORK 7, entities 5, NFT 7, root workflow/clock 2;
  all killed their intended regressions and restored source files.
- No full suite or version tag. R2 checks are focused compatibility checks,
  not an independent certification of every prior transport change or provider.

Independent final review found one Important issue: a changed job/site revision
could retain authoritative old membership after a failed detail refresh. The
single fix wave invalidates those facts and their observation time before
admission; same-version failures still retain valid evidence. Both revision
variants are covered; all 11 entity regressions and 62 composing launch/cache
tests pass, and a named rollback mutant is killed. The independent scoped re-review passed the original reproduction
and five related cases, killed/restored its regression mutation, and returned
**Approved — F1 ADDRESSED**. No Critical/Important finding remains open.

IMDB capture: `kb none` recorded. Existing KB lessons already cover the workflow
URL and deployment-identity distinctions; new findings here are application
implementation defects, retained in this report rather than a duplicate lesson.
