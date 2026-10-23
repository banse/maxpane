# BOARDROOM and linked views: loading review

Reviewed commit: `21208b1a7207295fda51eb3d66975c93d9782161` (2026-10-23).
Status: review only; no runtime changes. Three Agency specialists audited shared
reader architecture, catalogue views, and swarm/seat views. The controller
measured bounded live reads and inspected the remaining native views.

The WIP approach should be extended selectively: publish useful validated data
early, reconcile catalogues incrementally, preserve source observation times,
and bound optional enrichment. The existing UI/reader separation and per-source
single-flight guards should remain. More threads are not the first remedy.

## Measurement scope

[Captured measurements](surf_boardroom_loading_review_2026_10_23.json) contain
sanitized request timings, source-cache writes, CPU samples and offline gates.
No response bodies, credentials or RPC parameters are included.

Live probes used Python 3.13 and independent copies of the current persisted
SURF/NFT caches. They measured manager construction, projection, acquisition and
quiescence, **not time to terminal paint**. Each view is one observation, not a
latency distribution; the user's running app could update the source cache
between copies. Passive projection ran about once per second while busy.
Deadlines were checked between synchronous operations. A completed offer does
not mean that every historical row or optional enrichment is complete.

| View | Initial cached projection | Observed run | HTTP sends | Interpretation |
|---|---:|---:|---:|---|
| BOARDROOM | 1.248 s | 23.312 s | 29 | Tasks finished; two API routes timed out and retained old data |
| BUILT BY SWARM | 1.053 s | 47.891 s, stopped | 48 | Scores still pending at time limit; 32 job-detail sends |
| FLEET / BOARD | 0.972 s | 7.809 s | 2 | Workers/contributors cycle; historical ranking not benchmarked |
| AGENT, seat 420 | 1.147 s | 32.609 s, stopped | 60 | Request limit reached; 54 job-detail sends; not a completed refresh |
| ORACLES | 0.900 s | 7.774 s | 2 | List written at 4.210 s, selected detail at 6.115 s |
| NFT EXPLORER | 0.045 s | 2.623 s, cache-only | 0 | No selected/read activity established; not a network-refresh benchmark |
| SWARM TOKENS | 0.115 s | 5.758 s | 9 | Initial offered batch; subsequent market/history rounds not measured |
| POOL4 user view | 0.911 s | 7.816 s, stopped | 12 | First HTTP 429 ended the live audit |
| POOL4 protocol / ONCHAIN FEED / Launchpad | — | Not live benchmarked | — | Source reviewed; no further RPC load after 429 |
| Workflow guide | — | Local bundled content | 0 by design | `POLL_DATA = False`; no acquisition optimization needed |

Run times include construction and the initial projection. Cache-write events
are not UI paint events or proof of fresh observations. For example, BOARDROOM
overview/records writes followed failed reads. No additional request starts
were observed in each probe's short 100 ms post-deactivation drain window;
this is limited evidence, not a long-duration lifecycle certification.

BOARDROOM's `/swarm` and `/seats/records` calls to `api.imd.fun` timed out after
15.074/15.167 seconds. Both fallback calls to
`identitymdcontrol-plane-production.up.railway.app` returned 404. Other calls to
the canonical API succeeded. POOL4 reached HTTP 429 at `1rpc.io/sepolia`.
These are dated endpoint observations, not a claim that the canonical API is
generally unavailable. Revalidate alternatives before changing the endpoint pool.

## Highest-priority findings

### 1. Shared polling prevents queues but also delays unrelated sources

`data/reader.py:184` refuses a refresh while the manager is loading, and
`:313–325` advances past elapsed polls while any relevant task remains busy.
`data/surf_manager.py:7434–7465` includes optional work in that busy state.
Thus a slow token/NFT/detail tail can stop an otherwise due overview refresh.

An injected-clock probe of the production polling method kept one detached
source busy until second 95. Offers at 30, 60 and 90 were skipped; the next
refresh occurred at 120. There was no accumulating request queue. The defect
is coupling independent refresh schedules to the slowest relevant task.

Direction: let explicitly offer-only managers offer independently guarded due
sources while detached work is active. Keep monolithic refresh guards and
per-source single flight; never replay missed polls in a burst. This needs a
narrow capability boundary, not a blanket removal of the busy guard.

### 2. Shared projection spends substantial CPU on hidden views

`data/surf_manager.py:7739–7869` builds WIP rows, board rows, launch details and
heroes even for small BOARDROOM summaries. `data/surf_card_reader.py:179–188`
first projects the full WIP snapshot and then substitutes summary counts.
Launch keys are derived twice, including from `_swarm_hero()` at `:7930`.

With a copied 22,553,444-byte cache, five offline samples gave a **695 ms median
hub projection**, including a 273 ms WIP projection and a 166 ms board projection.
The projected payload was 4.70 MB. Live probes with more child-manager state
took roughly 0.9–1.25 seconds for the initial shared projection. These workloads
are different; neither number is a direct UI frame measurement.

`data/reader.py:201–225` can perform initial publication, the manager's returned
projection, and another passive projection for one offer. Three comparable
695 ms projections would be about 2.1 seconds of work; that is an arithmetic
estimate, not measured end-to-end latency. While synchronous projection runs,
newly scheduled async reads cannot progress on that reader loop.

Direction: summary-only BOARDROOM projection, reuse launch keys and worker
groups, then cache validated projections by source revision. Only rebuild
active-view detail contracts when their source changed. Preserve cache-input
validation at ingestion; do not remove it to improve timing.

`data/surfboard.py:345–351` already builds worker groups, but each seat's
`data/surf_swarm.py:1502` path groups them again. Profiling counted 1,111 grouping
calls for 1,107 seat-live projections. Reuse the existing group index.

Dirty whole-cache serialization is another reader-loop cost:
`data/surf_cache.py:1143–1194` took a 686 ms median for three copied-cache writes;
clean writes already short-circuit. Coalescing dirty writes is a later option
with an explicit durability window and flush-on-close, not a reason to remove
persistence or weaken cancellation cleanup.

### 3. NFT can miss revisions of older records

`data/surf_nft_client.py:255` supplies creation-page parameters, while
`data/surf_nft_discovery.py:452–483` stops refreshing once an old head ID is seen.
At `:501` completed historical scans are skipped. An older updated launch,
workflow or job outside the refreshed head can therefore remain unchanged
unless another explicit reference requeues it.

An offline reproduction returned a previously seen head: only that head was
read, terminal coverage stayed true, and the old row's `updatedAt` stayed
unchanged. This proves an acquisition gap, not that a particular currently
displayed collection is wrong.

Direction: reuse verified jobs/workflows update deltas, with overlap and periodic
reconciliation. **Launches `since` support is not established here**; retain a
bounded periodic launch reconciliation until its API contract is verified.
Keep persisted history cursors, fair FIFO work, and proof-before-counting.

NFT also holds completed selected-collection work at
`data/surf_nft_manager.py:507` until final publication at `:554`, behind optional
discovery. An offline gate reproduced this. With a copied 13.76 MB cache (33
records, 917 evidence entries), seven samples averaged 927 ms publication,
200 ms preparation and 268 ms save: **about 1.39 seconds** of sequential cleanup
outside the 8-second BOARDROOM / 15-second Explorer source budgets.
Cache/index discovery relationships first, then publish validated selection and
proof results progressively; blindly adding extra full publications would add CPU.

### 4. SWARM still has the long serial enrichment pattern removed from WIP

`data/surf_manager.py:7150–7189` reads up to 100 jobs, awaits their details
serially through `:6240`, then reads skills and workflows, and only then publishes
scores. With 100 misses this permits 112 logical reads, including workflow
pages. Configured detail pauses alone contribute about 12 seconds in that case.
Memo hits can reduce physical requests; this bound is not a live timing.

An offline gate completed 99 details and blocked the 100th: scores were absent,
and skills/workflows had not started. The live SWARM probe remained busy at
47.891 seconds. Its main swarm slot was written at 11.236 seconds and launches
at 17.483 seconds; there was still no scores publication at cutoff.

Workflow history (`data/surf_swarm_client.py:450`) also restarts capped incomplete
scans, or refreshes only the creation head after a complete scan. Reuse WIP's
certified catalogue/cursor/update-delta model. Publish lists/workflows before
bounded optional detail enrichment. Launches similarly wait for provenance,
liquidity and site-job work before publication at `data/surf_manager.py:5773`;
publish validated rows first, keeping unverified fields unknown.

Navigation amplifies this: `data/surf_manager.py:7507–7509` marks **all** tiers due,
including the normally 1,800-second scores tier. Reopening should refresh the
visible live data immediately while preserving fresh historical enrichment.

## Other views and targeted improvements

| Area | Finding | Recommended change |
|---|---|---|
| BOARDROOM WIP card | `surf_card_reader.py:72–106` repeats complete workflow scans after each finished scan, within its four-page bound | Reuse the incremental workflow catalogue for the summary; do not invoke the full WIP detail tree |
| TOKENS restart/navigation | Catalogue, quotes, history and trades are session-only (`swarm_tokens_manager.py:71`); activation resets attempt clocks (`:92`) | Persist bounded normalized caches with original observation times; keep fresh enrichment TTLs across navigation |
| TOKENS dependency scheduling | New catalogue rows wait until the next 30-second offer for markets; newly found pools wait for another offer for history (`:165`, `:663`) | Offer bounded dependent work when its input is published, retaining rate limits and single flight |
| TOKENS publication | `swarm_tokens_market.py:63` completes chains sequentially before manager publication | Publish each independent chain's result promptly; offline gate confirmed completed ETH data waits for Base |
| Token detail | `swarm_token_detail.py:184` waits for global sites before publishing completed contributor reads | Publish contributors independently; preserve provenance and explicit partial coverage |
| Token selection CPU | `swarm_tokens_manager.py:636` derives the whole token universe to choose one token | Index by immutable chain/address/launch identity. Offline 441-token population: 133 ms full snapshot vs 127 ms single selection, means of seven samples |
| AGENT / RECORDS | Base seat publishes early, but independent record answers wait behind up to 64 membership jobs, earnings, ENS and rewards (`surf_manager.py:6764–6784`) | Visible records first; separate cosmetic and financial enrichment; retain membership checks for grouping and resume historical work fairly |
| FLEET / BOARD | Workers and contributors are stored only after both finish (`surf_manager.py:6491–6516`) | Normalize/publish each independently. Offline gate confirmed completed workers were withheld by slow contributors |
| FLEET contribution ranking | Six-launch batch is not a request budget; each launch can contain up to 128 linked jobs (`surf_launch_contribution.py:282–319`) | Bound actual reads/time, preserve progress and isolate per-launch failures; retain the last complete ranking until the replacement is complete |
| FLEET fact age | `surf_launch_contribution.py:210–221` retimestamps a shared memo result with the current clock | Carry `read_job_detail().observed_at`. Offline transport reproduced a 100-second artificial rejuvenation with just one HTTP read |
| ORACLES | List-first publication already works; success TTL starts at completion and changed selection can wait behind the previous detail (`surf_oracles_reader.py:64`, `:124`, `:134`) | Start-based cadence; cancel/drain superseded detail only. This needs a small targeted change, not a loader rewrite |
| POOL4 user + protocol | `_collect_visible_detail` waits for channel/market before pool tasks (`surf_manager.py:8108`); `_pool_pool4` waits for logs/drip after atomic getters (`:3329`) | Publish block-pinned getter results before history. Separate independent market/channel scheduling where retained discovery is still verified; preserve provenance, chain identity and reorg rules |
| ONCHAIN FEED / SURF | `_cycle` awaits chain first, then six independent groups before `_last_full_payload` replacement (`surf_manager.py:8246`, `:8378`, `:8027`) | Stage independent source projections without changing signal causality or supplying mixed-block values. Measure first-feed publication before sizing this work |
| Launchpad | Existing persisted history cursor is reused (`surf_manager.py:2432`); pool and launchpad reads are gathered, then the decoy scan precedes final payload | Preserve incremental history. Consider early independent pool publication after measuring the decoy/history delay; not a proven top bottleneck |
| Workflow guide | Bundled local catalogue; `screens/workflow_guide.py:85` disables polling | No network work needed |

Token detail has a 12-contract-job prefix and explicit partial state, but no
continuation past that prefix. No live launch exceeding the cap was established
in this review; treat fair continuation as a conditional follow-up, not a proven
current data loss. Market hydration is bounded to 30 tokens per offer against a
120-second freshness target: more than about 120 simultaneously relevant tokens
need explicit prioritization or a different source capacity, not unbounded fan-out.

The ONCHAIN source review confirmed collector eligibility guards: scores, agent,
board and staker loaders are not all active just because `_cycle` calls their
spawn helpers. Do not mistake those calls for unconditional hidden network work.

## Proposed implementation order and ownership

1. **Shared reader/projection package** — one owner for `reader.py`, shared
   `surf_manager.py` integration and BOARDROOM summaries. Separate refresh offers
   from source single-flight; remove repeated derivation and preserve fresh
   enrichment across navigation. Measure cached publication and input latency.
2. **NFT correctness package** — one owner for `surf_nft_*`: older-record update
   acquisition/reconciliation, revision-scoped indexes, then early publication.
   Can proceed beside package 1 if manager integration is handed to its owner.
3. **SWARM and AGENT package** — use the new WIP catalogue helpers, publish lists
   and visible records first, and budget optional details. Shared manager changes
   follow package 1 to avoid multiple owners editing that file.
4. **TOKENS package** — bounded persistence, retained TTLs, dependency-triggered
   offers, per-chain/selected publication. Can run beside NFT in disjoint files;
   shared manager seams remain with the package 1 owner.
5. **Targeted native-view package** — FLEET independent sources and observation
   clocks, ORACLES selection/cadence, then measured POOL4/ONCHAIN staging.
   Keep Launchpad/history work conditional on a measured delay.

Endpoint-pool remediation is a separate small investigation: validate canonical
and official fallback behavior before replacing/removing hosts. The observed
404 fallback cannot rescue a timeout; no newly guessed fallback should be added.

## Acceptance checks for implementation

- Offline clock tests: a slow optional task cannot block due independent reads;
  the same source never overlaps itself and missed ticks never burst on recovery.
- Source-gate tests: fast list/selected results become visible while optional
  enrichment is blocked; cancellation retains completed progress and original clocks.
- Catalogue tests: an old row updated outside the creation head appears, equal
  timestamps/ties are safe, failed scans do not advance certified watermarks,
  and partial data never becomes a complete ranking or catalogue.
- Navigation tests: retained data appears immediately, required live reads start
  on entry, fresh optional work is reused, and old-view acquisition stops after
  draining. Popup return must not force historical rehydration.
- Repeat bounded live probes with stable copied caches, recording first useful
  publication, completion/cutoff, HTTP sends/bytes, CPU and cancellation separately.
  Stop on rate limiting. Do not compare censored runs as completion times.
- Render the changed views at the owner's terminal size and measure input latency
  separately from HTTP/manager timings before claiming a UI improvement.

WIP remains the comparison baseline, not a new rewrite target. SWORN and the
parked graphics experiments are outside this BOARDROOM review. No application
code or user's live cache was modified, and no full test suite was run.

Report validation: the 12 documentation-pin tests passed (Python 3.11, 15.21 s);
JSON parsing and whitespace checks passed. IMDB recorded `none`: these findings
concern MaxPane acquisition/processing, with no new protocol lesson to publish.
