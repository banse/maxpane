# SWARM TOKENS verdict reader

## Problem and acceptance criteria

The token catalogue and market readers run when SWARM TOKENS is visible, but
its provenance source is deliberately passive. Launch rows such as SHIFT #2124
can therefore remain `unknown`: the cached row exists while `detail_version`
and K1–K7 checks have never been populated. Opening the child screen stops the
parent SURF collectors, so waiting for their next poll cannot fix this.

The overview must offer its own bounded provenance read on entry/refresh and
after a cold catalogue completes. Cached values remain immediately available.
Only the visible SWARM TOKENS overview owns this work; BOARDROOM, PORTFOLIO,
passive getters and an inactive screen must not acquire it. Departure cancels
and drains the task before another scope starts. The task participates in the
existing loading indicator and reader snapshot publication.

Checks retain their current meaning: K1–K4 establish launch provenance, not
investment safety; missing evidence remains unknown/partial. Production chains
are 1, 8453 and 4663. Abandoned launches and testnets are not enriched.

## Decision

Extract the existing detail and provenance acquisition block inside
`SurfManager._pool_swarm_launches` into one private shared method. Keep the full
SURF collector calling it with its current inputs. Expose the narrow async API:

```python
await surf_manager.refresh_swarm_token_evidence(rows)
```

`rows` is a copied list of raw catalogue launch rows chosen by the token manager.
The helper validates canonical identities, admits at most three production
candidates, and returns after publishing validated facts and any policy update.
It uses the existing injected clock, clients, policy checker and facts cache.
It does not spawn a task, fetch the parent head/sites, match site jobs, collect K8
liquidity or advance the parent launch tier/read clocks. Its caller owns lifetime.

The helper retains completed contract checks, policy refresh rules, detail and
RPC failure handling, and the 1,800-second coverage/admission retry gates.
Requests remain batched by production chain using existing state RPC clients.
The three-candidate cap also bounds the narrow reader's RPC candidate count.

| Alternative | Benefit | Cost / reason not selected |
| --- | --- | --- |
| Enable the parent launch tier from the child | Smallest call-site change | Fetches head, sites and liquidity; violates visible-scope ownership and hidden-board isolation |
| Duplicate provenance acquisition in the token manager | Child has complete ownership | Two policy/identity/retry implementations can diverge |
| Share the existing evidence block, child owns task | Reuses validated facts and policy semantics; small explicit API | A mechanical extraction in the shared SURF manager needs composing regression coverage |

## Identity, cache and projection

The newest successful head row takes precedence over an equally old or older
catalogue row. A newer catalogue revision takes precedence over a retained head.
Before publication, compare each requested identity/version with the latest
retained catalogue/head; discard results superseded while awaiting reads.
Cancellation must not publish the private in-flight copies. Merge only accepted
points into the current cache, preserving unrelated launch/site facts.

The passive source must project its retained catalogue plus matching facts even
when the parent has never fetched a head list. The existing source timestamp
continues to mean a successful head read; no synthetic `launches_ts` is written.
Metadata/checks/pool IDs remain withheld when the selected row and stored detail
identity/version do not match. Returned source data remains copy-isolated.

When newly acquired evidence confirms the exact pool already used by a market
quote, retain that quote and its original observation time. A quote for a
different pool, or an invalidated launch-pool identity, remains withheld. This
avoids a price gap while the independent market queue catches up.

## Scheduling

`SwarmTokensManager._tasks['provenance']` owns the coroutine through the existing
`_start`, cancellation, retired-task drain and loading machinery. The production
scope is `SWARM TOKENS`; `legacy` remains available for direct-manager tests.
No screen or layout changes are needed.

On a refresh or successful catalogue completion, choose at most three eligible
unknown/partial rows. Order never-attempted candidates first, then oldest attempt,
then newest launch. Track attempts by canonical UUID, status and updatedAt;
retry after 60 seconds and allow a changed version immediately. A failing first
batch must not starve later launches. Do not repeatedly schedule completed
verdicts. The helper's existing longer retry gates remain authoritative.

## Packages and dependencies

1. **Shared evidence and source (reader_architecture)** — owns
   `maxpane_dashboard/data/surf_manager.py`,
   `tests/data/test_swarm_tokens_source.py`, and narrowly needed shared-manager
   tests. Extract the shared block; add the narrow method, identity publication
   guard and cold-source projection. Preserve the full SURF collector semantics.
2. **Token task lifecycle (root)** — owns
   `maxpane_dashboard/data/swarm_tokens_manager.py` and
   `tests/data/test_swarm_tokens_verdicts.py`. Schedule the shared API, maintain
   fairness/cadence, chain cold catalogue completion and enforce visible scope.
3. **Integration and final review (root)** — after both packages, run affected
   composing files once, inspect a live keyless overview, run required guards and
   request the final scoped Agency review.

Packages 1 and 2 can proceed in parallel against the frozen async API. Package 3
depends on both. Estimated production diff: 250–400 moved/added lines in the
shared manager plus 60–120 token scheduling lines; below 1,000 overall. Do not
introduce a second cache, event bus, thread or parent activation mechanism.

## Verification plan

Write targeted failing tests before implementation, using committed fixtures and
injected clients/clocks only:

- Cold catalogue obtains real fixture-derived provenance without head/sites/K8
  reads; source getter remains passive and launch tier clocks remain untouched.
- Three-detail cap, production filtering, retained completed checks and existing
  long retry gates; failed/foreign details cannot establish provenance.
- Newer catalogue/head identity wins; late results and mismatched pool metadata
  are withheld; cached source results are copy-isolated.
- Root: cold catalogue kicks acquisition, single-flight/loading, no acquisition
  from passive/hidden/portfolio scopes, cancel/drain/re-entry, failed-first-batch
  fairness and per-version retry reset.
- Mutation proofs target a publication identity guard and lifecycle cancellation
  or scope gate, then restore byte-for-byte before composing checks.

The first two existing source tests currently expect a passive getter to launch
the parent task. Replace those obsolete expectations with explicit acquisition
and passive-getter assertions; the passive boundary itself is intentional.

## Integration evidence

The live keyless 149×45 render used a separate cache containing only public
launch slots. SHIFT #2124's evidence was removed from that temporary copy to
reproduce the missing-detail path. The final run observed `unknown` at 0.55 s,
its market quote at 1.65 s, and `swarm` with the same quote at 3.52 s. K1, K2 and
K4 passed; K3 passed via immutable-code evidence. This is one live observation,
not a response-time guarantee. The user's cache was not modified.

Touched/composing files: 248 passed and 33 older title-test failures. All 33
failed node IDs reproduce on an unchanged `bce65c4e` archive. After the quote
handoff correction, all 93 affected data/market/source cases passed. Fast guards:
126 passed. No full suite was run. Identity, scope, cancellation, cold-start and
pool-match rollback mutations were killed and restored byte-for-byte.

Final independent Agency review: **Approved, no findings**. The reviewer verified
25 source/lifecycle cases and three policy/retry cases, killed the publication
identity mutation, restored it byte-for-byte and confirmed the restored test
passed. `git diff --check` passed.

Temporary evidence: `/tmp/maxpane-verdict-live/`,
`/tmp/maxpane-verdict-live-final.log`, `/tmp/maxpane-verdict-tests.log`,
`/tmp/maxpane-verdict-baseline.log`, `/tmp/maxpane-verdict-final-data.log`,
`/tmp/maxpane-verdict-guards.log`.
