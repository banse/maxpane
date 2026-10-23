# BOARDROOM loading improvements

Baseline: `21208b1a7207295fda51eb3d66975c93d9782161`.
Status: implemented, verified and final review approved (completed 2026-10-24).

The owner authorized the recommended order in the
[loading review](surf_boardroom_loading_review_2026_10_23.md): shared reader,
NFT correctness, SWARM/AGENT, TOKENS, then targeted native sources. The
[implementation plan](surf_loading_improvements_plan.md) fixes ownership and
acceptance criteria. No dashboard layout or public model keys are changed.

## Behavior

- Reader managers explicitly opt into offering independent guarded work while
  another source is pending. Monolithic managers retain their old guard. Missed
  polls do not accumulate, and leaving still cancels and drains the old scope.
- BOARDROOM reuses the worker index and launch projection, and constructs its
  WIP summary without projecting the hidden detail history. Reentry preserves
  optional-source TTLs. The workflow summary persists a private, validated
  catalogue checkpoint and uses the verified update-delta route.
- SWARM publishes workflow and launch lists before optional detail work. Score
  enrichment uses four concurrent reads, at most 24 reads/eight seconds per
  offer, revision-aware retained observations and fair continuation.
- AGENT records load independently of ENS, rewards and unrelated card sources.
  Answers/panels remain prerequisites for popup details. A launch-only filter
  waits for membership because that is an actual dependency. Each cycle has one
  bounded record pass; unknown membership is never painted as a confirmed launch.
- NFT acquisition refreshes older updated jobs/workflows and periodically
  reconciles launch history without assuming unsupported launch `since`
  semantics. Publication reuses candidate indexes and avoids repeated cache
  validation. Selected/proof results publish before unrelated tails.
- TOKENS persists bounded normalized observations with original clocks; fresh
  optional work survives navigation. Published catalogue/pool inputs can start
  bounded dependent reads without waiting for another poll. Selected-token
  lookup reuses an identity index.
- FLEET publishes workers/contributors independently. Contribution work has
  request/time limits, fair per-launch continuation and original memo ages;
  only complete facts replace a complete ranking. ORACLES uses read-start
  cadence and cancels superseded detail independently of list acquisition.
- POOL4 publishes exact-block getters before logs. Retained history keeps its
  older timestamp and reconciliation remains unchecked until aligned logs
  arrive. Reopening POOL4 or Launchpad refreshes current getters immediately
  without expiring fresh history. A changed deployment binding invalidates
  carried history/counter evidence. ONCHAIN publishes completed source slots while full signal assembly
  remains pending; prior signal causality is preserved.
- Native quote reads and POOL4 channel acquisition have their own guarded tasks.
  A held quote cannot delay the next due protocol, seat or Launchpad offer;
  a held channel cannot delay stakers. Leaving cancels and drains these reads
  through the existing source owner.
- The dead Railway fallback is replaced by the documented current alias after
  matching its `/version` to `api.imd.fun`. Rotation remains per request.

## Measured evidence

Full sanitized measurements: [evidence JSON](surf_loading_improvements_evidence_2026_10_23.json).

| Paired offline workload | Baseline | Changed |
|---|---:|---:|
| BOARDROOM projection, same 22.6 MB copied cache, median of five | 992 ms | 217 ms |
| NFT publication, same 14.2 MB / 33-record cache, median of five | 954 ms | 396 ms |

The normalized NFT record hashes matched in full. These are CPU/serialization
measurements, not a claim about network latency or terminal response. The first
new NFT publication took 609 ms; later calls reuse the candidate index.

The integrated live probe used the actual ReaderRuntime and Textual screens at
149×45, isolated copies of public-data caches, and a key-to-next-paint event:

| View | First local snapshot | Probe duration | HTTP sends | Input median / maximum | Result |
|---|---:|---:|---:|---:|---|
| BOARDROOM | 2.78 s | 13.74 s | 30 | 16 / 74 ms | Offered reads became idle; no HTTP failures |
| NFT EXPLORER | 1.68 s | 13.57 s | 24 | 1.4 / 67 ms | Normal bounded batch; partial history retained |
| TOKENS | 1.58 s | 15.44 s | 18 | 0.4 / 38 ms | Stopped at GeckoTerminal HTTP429 |
| ONCHAIN | 2.89 s | 8.93 s | 55 | 25 / 57 ms | Request-budget cutoff; not full completion |
| Launchpad | 2.25 s | 13.57 s | 55 | 12 / 45 ms | Request-budget cutoff; not full completion |

All five recorded zero HTTP sends after deactivation. ONCHAIN's market slot
published at 3.51 s, launch list at 3.70 s and channel at 5.05 s, before the
request cutoff. No further live probes ran after the token provider returned 429.
The token preview also logged two pre-publication `tokens`-key errors from the
existing screen adapter; the subsequent snapshot rendered 441 tokens and 9 quotes.
That initial empty-handle adapter is unchanged and remains a follow-up. The refreshed BOARDROOM render was checked in headless Chromium;
its terminal export is `/private/tmp/maxpane-loading-surfboard.svg` and the checked
image is `/private/tmp/maxpane-loading-surfboard.png` (local artifacts).

These live caches/upstream states differ from the earlier review; do not subtract
its durations to claim paired end-to-end speedups. Large-history acquisition can
remain pending across polls even though input and cached content are usable.

## Conditional recommendations

- Keep Launchpad's existing persisted cursor and checkpoint behavior. The bounded
  probe confirmed a long history tail but did not isolate a decoy/getter barrier;
  splitting its history model further is not justified by this measurement.
  Current-value entry refresh now uses a separate cheap nine-getter batch.
- Token contributor continuation beyond the existing 12-job prefix remains
  conditional: no live over-cap launch was established. Partial coverage remains
  explicit; do not turn it into a complete ranking.
- Dirty cache serialization remains costly (earlier copied-cache median 686 ms;
  clean saves are effectively free). No new coalescing policy is introduced:
  completed progress must be durable on cancellation. Measure actual write
  frequency before changing that policy.
- The local workflow guide does not poll. SWORN remains parked at the owner's
  request and is not part of this loading change.

## Verification record

Package reviews found and corrected fair contribution progress, NFT head/cursor/
watermark/cancellation recovery, malformed token points, chain-order blocking,
AGENT dependency/budget ordering, and malformed launch-list cancellation. Native
entry getter/history separation passed its focused client/manager checks.

- Native composing screens: **556 passed, 27 failed**. All 27 failures reproduced
  on the untouched baseline; they include old label/hero/filter expectations and
  the previous independent loading-timer contract. Baseline reproduction used
  isolated cache homes and the exact failed node IDs.
- Fast guards: **128 passed, one failed**. The failure is the pre-existing TOKENS
  CSS extraction test, which absorbs the later SWORN section; baseline reproduced.
- Data packages: NFT 135, TOKENS 167 and helper 73 passed in their final focused
  runs. Shared cache 98 and AGENT/staging 48 passed after dependency fixes.
- Final shared/native data run across 18 whole files: **1,528 passed, nine
  failed**. Three collector-boundary mocks needed the new entry-refresh keyword;
  the complete affected file then passed 19 checks with its four baseline
  failures. The combined final result is **1,531 passing cases and six baseline
  failures**: four old pool-card mocks, a BOARD expected-key omission, and an old
  seat caption. All six reproduced against the untouched baseline.
- Native entry: **258 client/new/staging checks**, **184 selected existing native
  checks**, and **33 final POOL4 checks** passed; six focused mutations killed.
- Reviews independently killed targeted mutations for offer cadence, read caps,
  per-point persistence, chain order, NFT recovery and contribution fairness.
  Mutation files were restored byte-for-byte. No full project suite was run.
- Documentation pins: **12 passed**. Diff whitespace checks passed.
- Final whole-change review found one remaining native quote/channel barrier.
  The single correction wave passed **29 focused checks**; five new regression
  cases failed before the fix and passed afterward. Three mutations reintroduced
  quote blocking, channel blocking and source overlap, and all were killed.
  Scoped re-review independently passed all five new cases and returned
  **Approved**. The earlier normalization-only test residual remains filed.
- After that correction, the 14 affected data/composing files ran whole:
  **1,005 passed, 30 failed** in 266 seconds. Every failed node ID matches the
  already reproduced baseline failures; no new failures remain.
