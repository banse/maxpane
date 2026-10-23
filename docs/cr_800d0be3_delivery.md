# CR 800d0be3 delivery evidence — 2026-10-23

Batch: `800d0be3-b83e-4316-ab2d-e2cd177561e8`. Nine notes, grouped into AGENT,
BOARDROOM, NFT and WORK. Baseline: `735f54c2`. Scope and interpretation are in
`cr_800d0be3_plan.md`; the owner's NFT correction is **same job request AND same
deployer**, in addition to the same name. Existing unrelated files are excluded.

## Result

- AGENT: LAUNCHES/JOBS and ORACLE/JOBS show distinct production jobs across
  attempts, with accepted/total percentage. Unknown membership or testnet
  classification does not become a number. OWNER links to the IMD wallet page
  and retains the address copy action. Runtime state transitions were audited
  and tested; their existing production behavior needed no change.
- BOARDROOM: TOKENS shows the newest three launches regardless of volume or age.
  WIP shows the active original-workflow count, including known zero. A known
  absence of working jobs reads `0 working`. BUILT BY SWARM owns its 24H chart.
  SIGNALS puts the count first and uses only fired detectors; unknown detector
  coverage remains unknown.
- NFT: head-page catch-up now continues across a gap without resetting history;
  new launch summaries invalidate older details; bounded BOARDROOM cycles also
  advance launch details. Duplicate display groups require matching chain, name,
  direct launch-job IDs and successful-receipt sender. Most minted wins, newest
  breaks ties; missing provenance stays separate and underlying records remain.
- WORK: Open follows the original workflow lifecycle. Finished/paused parents
  no longer hide ordinary follow-up jobs. Empty project headings are omitted.
  Running/completed colors are swapped. Partial workflow pagination cannot
  certify a zero; an empty tree also renders under NO_COLOR.

## Live observations

Actual MaxPaneApp/reader renders, Matrix at 149×45, used copied caches in an
isolated HOME and keyless public sources. BOARDROOM, AGENT, WORK and NFT renders
were shown before final review. Artifacts: `/private/tmp/maxpane-cr800-live/`
(`boardroom`, `agent`, `work`, `nft`: SVG, compositor text and snapshot JSON).

BOARDROOM showed the newest token rows. AGENT seat 420 showed 19 launch jobs and
94.74% accepted; missing oracle-chain coverage stayed unknown. WORK showed jobs
without bare project headings. Its later incomplete scan correctly retained an
unknown workflow total. NFT showed 24 verified collections.

A separate NFT isolated-cache probe measured three cycles:

| Mode | Seconds | HTTP | Errors | Pending launch details |
| --- | ---: | ---: | ---: | ---: |
| BOARDROOM proof cycle | 5.774 | 12 | 0 | 174 → 173 |
| NFT detail cycle | 12.647 | 22 | 0 | 173 → 172 |
| NFT detail cycle | 9.826 | 22 | 0 | 172 → 171 |

Two previously uninspected contracts were classified unsupported; factory reads
also progressed. The observed inventory stayed at 24. These samples demonstrate
reader progress, not complete inventory, a full-backlog completion time, or UI
latency. Trace: `/private/tmp/cr800-nft-live/report.json`. The offline transport
regression separately proves a new candidate reaches verified published rows
within four bounded BOARDROOM cycles. Existing single-flight and R2 wire-budget
checks remain in the tested set.

## Verification

No network in tests; isolated HOME and NO_COLOR unset for color-sensitive
composites. No full suite or prior R2 final review was run.

- AGENT package: 378 passed; 6 mutations rejected and restored.
- NFT package/cache/rules/widgets/R2 budgets: 228 passed; 8 mutations rejected.
- WORK data/reader/widgets/screens: 183 passed; 9 mutations rejected.
- BOARDROOM rack/layout: 162 passed.
- Root data/shared-widget checks: 542 passed and one pre-existing import-allowlist
  failure. After the final tooltip/doc edits, 406 checks passed with that known
  failure deselected.
- Root behavior mutations: 5 rejected and restored.
- Address rendering/link/copy: all three affected Surf sweep sizes passed.
- Fast guards: 128 passed. Documentation pins: 12 passed.

The final composing run passed 154 checks; two exact-key assertions in the
existing token-ranking tests needed the new `latest` field. After correcting
those expectations and asserting newest order independently, all 22 ranking
tests passed. These sets overlap; they are not an additive unique-test total.
Final review is recorded below.

## Independent review

The final reviewer reproduced two findings: category membership differed between
accepted and all-attempt job counts; representative reduction also hid an NFT
from explicit identity lookup. Both were addressed in the single fix wave.
The category fix classifies all attempts of each accepted job using the same
oracle precedence as the denominator. Its touched/composing set passed 383 cases;
three additional mutations were rejected and restored. The NFT fix retains raw
inventory through the manager-to-screen boundary, allows exact contract/identity
search and explicit selection, respects filters and binds README to that identity.
Its focused set passed 114 checks and the entire NFT screen file passed 34 with
NO_COLOR unset; three additional mutations were rejected. A color assertion failed
with inherited NO_COLOR=1 and reproduced before the fix; no style or test
expectation was changed to hide it.
The reviewer independently passed 41 focused checks and rejected two targeted
mutations, restoring the files byte-for-byte. Scoped re-review: **Approved**;
F1 and F2 both ADDRESSED. The reviewer independently passed 10 regression cases
and rejected two further mutations, including the mounted category card and
manager-to-screen NFT identity delivery. No reviewer edits remain.

## Existing failures outside this CR

Independently reproduced against baseline 735f54c2 in an isolated archive:

- `test_widget_modules_import_no_data_layer_and_no_analytics`: existing pure
  `surf_launch_checks` import absent from the allowlist.
- `test_every_case_is_swept_at_its_pins`: expected pin list lacks existing
  WORK/ORACLES dimensions. Actual affected address renders pass.
- Nine AGENT manager failure/retained-clock cases: one
  `test_finished_failure_does_not_keep_loading_while_sibling_read_waits` and
  eight `test_retained_never_paired_result_keeps_its_stale_clock` cases.
- Fourteen old `test_surfboard_card_activity.py` failures.

Logs: `/private/tmp/cr800-shared-baseline.txt`,
`/private/tmp/cr800-boardroom-baseline-activity.txt`, and the AGENT baseline
archive `/private/tmp/cr800-agent-baseline`. They were not hidden or attributed
to this change, and were not expanded into unrelated fixes.
