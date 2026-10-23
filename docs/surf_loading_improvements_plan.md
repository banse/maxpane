# BOARDROOM loading improvements: specification and implementation plan

Date: 2026-10-23. Baseline: `21208b1a7207295fda51eb3d66975c93d9782161`.
Status: implemented, verified and final review approved on 2026-10-24. Authorized by the
owner's “go with the recommended order and implement all”. Tier 2: shared reader
behavior and multiple dashboards.

This implements the actionable recommendations in
[the loading review](surf_boardroom_loading_review_2026_10_23.md). Its
[captured evidence](surf_boardroom_loading_review_2026_10_23.json) is the measured
baseline. The older `surf_loading_review_2026_10_23_plan.md` describes an earlier
implementation and remains historical; it is not this task's ownership plan.

## Decision and scope

Keep the existing client → validated cache → manager → reader snapshot → screen
boundary. Make independently guarded sources eligible on time, publish useful
validated results before optional enrichment, and reuse normalized catalogues.
Keep one reader event loop and the current UI thread. No new service, database,
generic scheduler, dashboard, widget, navigation binding or layout change is needed.

| Option | Benefit | Cost / decision |
|---|---|---|
| More threads or a generic dependency scheduler | Broad scheduling flexibility | New ownership, cancellation and persistence races; unnecessary for the measured bottlenecks. Rejected. |
| Small changes to existing adapters and source publication | Reuses tested lifecycle, cache and identity boundaries | Each adapter must explicitly expose independent work and retain its own bounds. Selected. |

Implement the approved order: shared foundation, NFT correctness, SWARM/AGENT,
TOKENS, then remaining native views. Disjoint preparation or implementation may
run concurrently; integration follows dependencies below. Code review is not
authorization for signatures or writes to chain: MaxPane remains keyless/read-only.

Conditional review items remain evidence-gated: token contributor continuation
beyond 12 jobs, Launchpad decoy/history staging, and a changed disk-write durability
window are not automatic additions. Establish the specified problem before adding
behavior. Do not silently call a conditional item implemented; record its evidence
and disposition. Endpoint remediation requires a current canonical/official-source
check and may not introduce a guessed replacement host.

## Frozen public contracts and required behavior

- Preserve `SURF_KEYS`, `SURF_ROW_KEYS`, `SWARM_KEYS`, `SURFBOARD_KEYS`, `NFT_KEYS`,
  token projection/snapshot keys and all existing widget signatures. No public
  model key or widget import from data is added. Private helper methods and
  optional validated cache metadata may change.
- A visible scope first receives retained observations for its exact view and
  selection identity. Entering refreshes required live data immediately;
  successful optional/history freshness survives navigation and popup return.
- The ordinary acquisition offer remains 30 seconds. Source-specific success
  TTLs and failure backoff remain separate. Optional work cannot prevent another
  due source from being offered. The same source never overlaps itself, missed
  ticks are never replayed as a burst, and a monolithic manager keeps its guard.
- The private opt-in seam is `reader_offer_only(view)`: true means fetching only
  offers guarded asynchronous work and returns the current snapshot. The reader
  can reuse that result without a third projection. Managers without the method,
  or modes returning false, keep the existing monolithic completion behavior.
  NFT/TOKENS implementations coordinate this exact seam with root.
- Leaving cancels and drains owned work, including downstream tasks started by
  a completion callback. Old generations cannot publish into the new identity.
  Parent/child borrowed clients stay open until their actual owner closes them.
- A new passive snapshot never starts I/O. Publication carries complete/partial
  coverage, provider observations and existing loading metadata truthfully.
  Existing count-caption display overrides remain display-only; missing source
  values remain `None` internally, never a fabricated observed zero.
- Child detail/proof observations are bound to source identity and revision.
  A memo hit carries its original `observed_at`; publication time cannot make
  old evidence fresh. Failed reads retain the last good observation and clock.
- Incremental rows merge by stable ID and source revision. Missing delta rows
  are not deletions. Only a complete validated listing advances a certified
  watermark; malformed, capped, failed or cancelled pagination cannot do so.
  Keep the five-minute overlap and periodic full reconciliation where supported.
- Jobs/workflows update filtering is already verified. Do not assume launches
  support `since`; use bounded periodic reconciliation until independently proven.
- Existing cache version keys are unchanged. Private additions load additively;
  malformed optional metadata triggers re-acquisition without erasing valid
  display data. Persist only bounded, allowlisted data, never raw unbounded bodies.
- Keep POOL4 exact-block getter bundles, chain/deployment binding, discovery
  provenance, rolling-log cursors, reorg handling and complete-ranking rules.
  An early current-value publication cannot imply that history is also current.

## Work packages, dependencies and exclusive ownership

All paths below are relative to `maxpane_dashboard/` unless noted. Each test file
has one implementation owner; another package needing it sends the requested
addition to that owner. No worker edits `surf_manager.py` or `surf_cache.py`.
Root integrates all shared-file seams. No subagent spawns another subagent.

| Package | Owner and files | Work / dependencies | Estimated production lines |
|---|---|---|---:|
| A: shared foundation | Root: `data/reader.py`, `data/surf_manager.py`, `data/surf_cache.py`, `data/surf_card_reader.py`, `data/surfboard.py`, `data/surf_swarm.py`; corresponding reader/hub/board tests | First. Explicit offer-only scheduling capability; source guards remain authoritative. Avoid repeated expensive projections, reuse worker groups/launch projections, make BOARDROOM WIP summary cheap, preserve optional freshness on reentry. Reuse existing workflow catalogue helpers for the card. | 250–400 |
| B: NFT correctness and publication | NFT worker: `data/surf_nft_*` excluding public model contracts; NFT tests only | Can run beside A in disjoint files. Acquire older revisions via verified jobs/workflows deltas and bounded launch reconciliation. Index discovery relationships per revision; publish validated selected/proof results before optional tails without repeating the full expensive projection unnecessarily. | 300–450 |
| C: SWARM and AGENT | Root: shared manager and `surf_work_catalogue.py` if a reusable narrow helper is needed. Helper worker: `data/surf_agent_card_sources.py`, matching helper tests | Integrate after A; helper changes require an explicit handoff. Publish workflow/launch lists early, reuse WIP-style catalogue checkpoints, bound optional score details and retain revision-aware enrichment. Prioritize visible records independently of ENS/earnings/rewards, with fair resumable membership work. | 250–400 |
| D: TOKENS | Token worker: `data/swarm_tokens_manager.py`, `data/swarm_tokens_market.py`, `data/swarm_token_detail.py`, new private `data/swarm_tokens_cache.py`, token tests | Disjoint work may run beside B; root integrates constructor/shared-client seams after A. Persist bounded catalogue/quotes/history with original clocks; retain TTLs across navigation; offer bounded dependent work on successful inputs; publish chains/contributors independently; index selected identity. | 300–450 |
| E: remaining native sources | Root: manager FLEET/POOL4/ONCHAIN integration. Helper worker: `data/surf_oracles_reader.py`, `data/surf_launch_contribution.py`, corresponding helper tests | After A/C shared-file changes. Publish workers/contributors independently; preserve contribution observation time and add real request/time budgets with fair progress/error isolation. Use Oracle start-based cadence and cancel superseded detail. Stage POOL4 getters and independent ONCHAIN sources while preserving block and signal causality. | 250–400 |
| F: measured integration and endpoint disposition | Root: bounded diagnostic artifacts, follow-ups/doc updates; `data/surf_swarm_client.py` and its tests only if endpoint evidence warrants a change | After relevant packages. Compare stable copied-cache workloads; inspect actual render/input responsiveness. Recheck official endpoints with small bounded reads; implement only evidence-backed endpoint correction. | 50–150 |

Total estimate: **1,400–2,250 production lines** (approximately 1,500–2,300 with
small integration adjustments), excluding tests/docs. This is above the
1,000-line exception: each completed package diff receives one task review,
then the controller requests the final whole-change review. Do not split ownership
by functions within the shared manager. Root may complete manager subpackages
sequentially while disjoint NFT/token/helper owners work concurrently.

## Package acceptance and focused tests

Use injected clocks/transports and event gates. Add a failing behavioral test,
implement the smallest change, then refactor green. No test touches the network;
live diagnostics are separate bounded tools. Threaded tests wait for observable
state, not arbitrary wall-clock sleeps. Apply and restore focused mutations for
decoder/concurrency-shaped changes with `scripts/mutate.py`.

### A — independence and projection

- A slow optional source remains busy across 30/60/90 seconds while another due
  source is offered on schedule; active-source sends never overlap and no missed
  ticks burst after recovery. Non-capable/monolithic managers keep old guards.
- Initial retained publication and updates completing between monitor ticks remain
  visible. A result captured before a detached update cannot overwrite that update.
- Hidden view detail derivation is not repeated for a BOARDROOM summary. Dirty
  source revisions invalidate relevant projection caches; clock-only captions and
  loading changes still update without reparsing every historical row.
- Reentry offers required live data but reuses fresh optional history. Corrupt
  persisted snapshots still pass through validation and cannot populate bad values.
- Primary files: `tests/data/test_reader.py`, `test_surf_manager_surfboard.py`,
  `test_surfboard.py`, `test_surfboard_seats.py`, and reader responsiveness tests.

### B — NFT correctness and boundedness

- An old created record updated outside the prior head becomes visible; overlap,
  equal timestamps, cancelled pages and empty successful deltas behave correctly.
- Unknown launch update filtering uses a bounded resumable reconciliation, not
  unsupported query semantics. Prior proof survives a failed metadata refresh.
- A finished selected/proof result is visible while optional work is gated.
  Indexing lowers repeated projection work without stale relation joins.
- Existing 8-second hub/15-second explorer source budgets and fair lanes remain;
  cancellation retains completed progress, but never certifies unfinished coverage.
- Primary files: `test_surf_nft_discovery.py`, `test_surf_nft_cache.py`,
  `test_surf_nft_manager.py`, `test_surf_nft_references.py`, and NFT composing screen.

### C — useful SWARM and AGENT data before optional work

- Skills/workflow/list publication occurs while a slow optional job detail is gated.
  Detail concurrency, actual read budget and elapsed budget stay bounded; the next
  cycle resumes fairly and reuses same-version observations.
- An old updated workflow appears through incremental acquisition; incomplete
  history never becomes a certified complete catalogue or zero-work count.
- A new launch can appear with unknown pending proof fields, but cannot inherit
  another version's legitimacy, contract, site, receipt or liquidity facts.
- Seat and independent visible RECORD answers publish before slow ENS/earnings;
  grouping requiring membership still waits for validated membership evidence.
- Primary files: `test_surf_manager_swarm.py`, `test_surf_manager_launches.py`,
  `test_surf_agent_card_sources.py`, `test_surf_manager_answers.py`, relevant AGENT
  tests, and the matching SWARM/AGENT composing screen files.

### D — TOKENS lifecycle, persistence and dependent offers

- Restart paints persisted valid catalogue/market/history data with its original
  observation times. Invalid cache entries are individually rejected; caps hold.
- Reentry at the same clock does not repeat fresh optional reads. A newly published
  catalogue row can start its bounded market work without another 30-second wait;
  a newly discovered pool can then offer bounded history/trades.
- Fast-chain data and completed contributors publish while another chain/sites is
  gated. Pool changes invalidate old market/history facts for the selected identity.
- Selected projection does not rebuild the whole universe when its source revision
  is unchanged. Cancellation prevents chained callbacks from starting hidden work.
- Primary files: token manager/source/live/market tests, `test_swarm_token_detail.py`,
  new private-cache tests and TOKENS/detail composing screens.

### E — native-view correctness

- Workers publish while contributors is gated. Ranking stays at the last complete
  certified result until all required replacement facts are ready; one failed
  launch cannot starve other launches and actual request/time caps hold.
- A memo read retains original observation time; attempts/failures do not advance
  observation TTLs. Oracle selection cancels/drains only superseded detail and
  preserves the published list; success cadence uses read start.
- Atomic POOL4 getters become visible before slow logs without mixed-block fields,
  altered provenance or falsely fresh history. ONCHAIN staging preserves signal
  inputs and prior values while independent sources remain pending.
- Measure the unbenchmarked ONCHAIN/Launchpad staging boundary before extending
  their behavior. Keep existing Launchpad cursor reuse and rollback checkpoints.
- Primary files: `test_surf_oracles_reader.py`, contribution-reader tests,
  `test_surf_manager_pool4.py`, `test_surf_manager_pool4_market.py`,
  `test_surf_manager.py` and matching native composing screen files.

## Validation, review and completion

1. While editing, run only touched behavior and immediate consumers. Before each
   package is reviewed, run its touched test files and composing files once with
   an isolated test home and the project's Python environment. Root coordinates
   shared-file tests so agents do not run competing broad suites.
2. Changes affect publication timing but not intended visual design. Before final
   hardening/review, root shows actual keyless live renders at the previously used
   **149×45** terminal size, using isolated public-data caches. Preserve all pins;
   if a necessary change unexpectedly touches sizing, read the layout skill and
   reclassify that specific requirement before editing its pin.
3. Repeat the baseline diagnostics with fixed copied caches. Record cache-load and
   projection CPU, first useful source publication, full completion or cutoff,
   HTTP sends/bytes, selected-record publication and requests after deactivation.
   Measure actual input responsiveness separately. Stop live probes on rate limits;
   never claim a cutoff is a completion or HTTP speed is UI speed.
4. Each package gets one scoped review with CLAUDE.md's complete reviewer contract;
   at most two package fix rounds. Reviewers do not fix files. Once integrated,
   request one final whole-change review on the most capable available model,
   one correction wave, and a scoped re-review only if production code changed.
   Minor-only findings are filed rather than opening another fix wave.
5. Root runs the fast guard set and 12 documentation pins once for the integrated
   result. Registration mounts are needed only if an actual registration surface
   changed. No full suite unless the user explicitly asks or a version is tagged.
   Known baseline failures are reproduced/documented, never silently fixed here.
6. Update the existing area follow-ups and this plan with actual evidence,
   conditional-item dispositions and remaining upstream limitations. Commit only
   task-owned files; preserve unrelated untracked work. Do not leave a plan worktree.
   Run the IMDB lesson/none step once at the task's end; no new protocol knowledge
   should be invented from application scheduling changes.

Completion requires all five approved groups implemented or an explicitly
evidence-backed conditional disposition, green relevant checks, reviewed final
changes and measured behavior. Merely completing this plan or exhausting a probe
budget does not satisfy the user request.


## Implementation handoff

All actionable packages A–F are implemented. Package reviews corrected the
reported source-fairness, watermark, cancellation, point-validation, chain-order
and native-entry defects. Native reentry adds one small Launchpad client helper
and separate current-value offers; history clocks/cursors stay independent.
See [implementation evidence](surf_loading_improvements_2026_10_23.md) for paired
CPU measurements, bounded live captures, known baseline test failures and the
conditional recommendations. Final whole-change review identified one native
quote/channel cadence barrier. The single correction wave detached those reads
under existing source ownership, with five red/green regression cases and three
killed mutations. Scoped re-review approved the fix. The final affected whole-file
run passed 1,005 checks; all 30 failures match independently reproduced baseline
failures. No full project suite or additional live probe was run.
