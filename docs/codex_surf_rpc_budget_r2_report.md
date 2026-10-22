# SURF RPC budget — round 2 implementation report

Date: 2026-10-22. Branch: `feature/surf-rpc-budget`.
Comparison base: completed R1 at `a02d9b50`.
The owner deferred independent verification until both rounds are finished.
This is the implementation evidence; no independent review, full suite,
network recapture, merge, push or tag was performed.

## Result

Implemented the safe R2-a/b/d changes. Existing Ethereum endpoint pools already
satisfy the recorded R2-c exclusions. Do not interpret this as verification of
every original outcome: the archive-provider evidence and static-cache limits
below remain, and some request-count rows increase for correctness.

- Recent Surf, CurveSwap, POOL4 hook/swap/drip reads retain complete bounded
  windows and replace the previous twelve blocks plus newly arrived blocks.
  Failed/cancelled tails never publish partial history. Expired windows rebuild.
- Launchpad rewinds lifetime launches, traders, swaps and burn totals as well as
  recent rows. Its process-local pre-tail checkpoint means a new process must
  rebuild an old persisted aggregate cursor instead of guessing its rollback.
- POOL4 cumulative controls persist a validated pre-tail checkpoint in the
  existing accumulator. Orphan contributions disappear after a reorg, including
  after cache reload. Old caches still load; a refresh without a provable tail
  reseeds only from a window containing genesis. The >24-hour gap discard rule
  is unchanged. No cache version or public model key was added.
- Surf, POOL4, Base/RH launch, swarm, earnings and NFT clients share reader-loop
  host admission. Host locks serialize starts at the strictest interval. HTTP
  429 sets numeric/date Retry-After or a 60-second fallback; cooling hosts are
  skipped before dispatch so another provider can answer. Parked transports
  and per-chain overrides remain unchanged.
- Explicit refresh contexts share one logical chain-head acquisition per chain,
  including detached tasks. Embedded Multicall block witnesses remain. Every
  log host must also serve the exact target-height header; a lagging host cannot
  certify an empty future range. Header checks count as RPC requests.
- POOL4 executes duplicate identity/model calldata once per atomic round:
  73→67 subcalls in the first known-state aggregate. Healthy state still uses
  two HTTP requests. Mutable metadata and unproven getter failures remain live.
- NFT inspections batch independent getters at the pinned block and retain
  individual failures. Robinhood keeps its single-call compatibility path.
  BOARDROOM retains unchanged proven deployment evidence with its original
  observation time; changed proof inputs/runtime evidence invalidate reuse.
  Factories still discover children and native NFT detail polling stays active.
  Completed proof replay slots are released so new candidates are not starved.
- Visible-view polling, cancellation, local cached projection and reader/UI
  separation remain in place. No layout, binding or new polling service changed.

## Reproducible offline budget

The committed command counts physical dispatches, entries, REST requests,
Multicall subcalls, attempted log blocks and returned rows. The compact artifact
`codex_surf_rpc_budget_r2_budget.json` includes 39 scenarios and fingerprints of
all 46 Surf data modules, the harness, helper source, fixtures and original capture.
All 39 compared projections match; no completeness flag fails. All 16 rolling
results also match independent full fixture-window projections.

| Scenario | RPC POSTs R1 → R2 | Attempted log blocks R1 → R2 |
|---|---:|---:|
| POOL4 hook, warm | 15 → 4 | 37,508 → 28 |
| POOL4 swaps, warm | 15 → 4 | 37,508 → 28 |
| POOL4 drip, warm | 8 → 4 | 50,401 → 28 |
| Launchpad, warm | 16 → 13 | 12,014 → 112 |
| Recent Surf logs, warm | 6 → 10 | 12,005 → 98 |
| NFT mainnet full inspection | 22 → 11 | — |
| NFT RH full inspection | 22 → 22 | — |
| NFT unchanged BOARDROOM proof | 10 → 0 | — |
| BOARDROOM steady minute | 4 → 4 | 0 → 0 |

NFT mainnet batching preserves **22 RPC entries** and two REST GETs: it halves
HTTP overhead, not EVM work. Other explicit premiums: decoy 2→3 requests,
stakers warm 3→5, POOL4 cold hook 15→17, expired hook/week 16→18 and
launchpad/day 32→40. Empty confirmation and per-host target-height proofs remain
required. The brief's unconditional “no row gets worse” target is therefore not
met; the artifact includes every row rather than selecting only improvements.

Recreate the isolated R1 comparison tree if needed, then run one command:

```sh
mkdir -p /private/tmp/maxpane-rpc-budget-r1-a02d9b50
git archive a02d9b50 maxpane_dashboard tests pyproject.toml README.md CLAUDE.md .claude \
  | tar -x -C /private/tmp/maxpane-rpc-budget-r1-a02d9b50
.venv/bin/python scripts/measure_surf_rpc_budget.py \
  --baseline /private/tmp/maxpane-rpc-budget-r1-a02d9b50 \
  --repo . --output /private/tmp/surf-rpc-budget-r2-measured.json \
  --summary-output docs/codex_surf_rpc_budget_r2_budget.json
```

These are deterministic request counts, not live latency or UI responsiveness
measurements. Quiet catch-up advances fixture heads without inventing later
trades. Complete POOL4 event corpora are recorded; recent-log/NFT fixtures and
bounded target-header availability are explicitly synthetic. NFT proof
comparison excludes and separately records revision/observation metadata.
This does not prove every dashboard's entire flat dict or real current density.

## Validation

- Final integration command: isolated `HOME`, `.venv/bin/python -m pytest -n 4
  --dist worksteal`, 31 touched/composing data test files: **1,638 passed,
  one existing failure**, in 15.09 seconds. No new regression remained.
- The remaining failure is
  `tests/data/test_surfboard_supply.py::test_supply_visible_cadence_failure_clock_and_cache`
  at line 65 (`unavailable` versus `ok`). Reproduced unchanged in an isolated
  archive of exact R1 `a02d9b50`, before attributing it to this round. Left out
  of the implementation scope. The older four screen expectation failures in
  the R1 report were not rerun or altered here.
- Two stale launch-client test doubles from R1 were corrected in the touched
  test file: replies now bind to request identity instead of current batch
  position, and missing receipts expect retry on alternate Surf providers.
- Final measurement module: **9 passed**. Fast guards: **128 passed**.
  Documentation pins: **12 passed**. `git diff --check` passed.
- **27 named mutants killed**, original files restored byte-for-byte:
  6 rolling/launchpad, 5 POOL4, 6 NFT, 7 shared transport/counter checkpoint,
  and 3 measurement-accounting mutants. Configurations live in
  `tests/fixtures/surf/rpc_window_mutants.json`, `rpc_pool4_r2_mutants.json`,
  `rpc_budget_r2_nft_mutants.json`, `rpc_transport_mutants.json` and
  `rpc_budget_measure_mutants.json`. Run each with `scripts/mutate.py` and its
  corresponding focused test file(s).
- A mutation exposed a test waiting indefinitely when admission was bypassed.
  The test now awaits either admission completion or its wait signal, so that
  mutant fails rather than hanging. The interrupted source was restored before
  the complete successful mutation rerun.

No Python 3.11/full-suite or independent Claude verification has been performed
in R2. Those remain the final verification step requested by the owner.

## Evidence limits and deliberate omissions

1. IMD name/symbol are owner-mutable (`surf_addresses.py`, `surf_PRD.md`). Do not
   cache them forever. Captured values alone also do not prove that POOL4
   decimals, pool IDs or getter reverts are immutable across runtime/proxy
   changes. No permanent negative cache, assumed 18 decimals or speculative
   static cache was introduced. Live successful reads retain their semantics.
2. Ethereum Surf/POOL4 archives already use Tenderly/Mevblocker and exclude the
   named unsuitable log providers. Base/RH launch adapters are state-only.
   The supplied captures prove neither two Base archive providers nor an RH
   archive pair. No invented replacement or fresh verification date was added;
   a temporary Base 429 is handled by cooldown instead of permanent removal.
3. Reorg handling covers twelve blocks, not arbitrary deep reorgs. Launchpad
   restart rebuilding and POOL4 old-cache reseeding are conservative costs.
4. The whole-app workload, live provider latency and current log density remain
   unmeasured. All endpoint statements derive from supplied dated captures,
   not new requests. No external aidude edits or new IMD protocol lessons.
