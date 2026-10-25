# POOL4 executor and Base burn evidence

Date: 2026-10-25. Tier 2: a new data contract, independent reader and changes to both
POOL4 views. Estimated scope: 600–950 production lines. One final review; no package
reviews while the implementation remains below approximately 1,000 production lines.

## Specification

The owner asks to “review of pool4 board especially regarding the BurnExecutor as it
seems it doesnt cover lthe latest one” and approves implementing the reviewed fixes.

Required outcomes:

- Opening either POOL4 view directly collects current executor and recent Base burn
  evidence without first visiting Launchpad.
- Keep four meanings distinct: hook-settled allocation, current executor queue,
  an observed bridge send, and an independently confirmed Base token burn.
- Describe the hook's `totalBurned()` counter as settled allocation, not proof of a
  completed Base burn. Preserve hook-specific unsettled claims as a separate fact.
- Qualify `totalSupply()` and its percentage as Ethereum wrapper supply. It is not a
  cross-chain circulating-supply denominator.
- Show the latest verified bridge and receiver burn in bounded recent block windows
  spanning nominally seven days. Do not introduce lifetime reconciliation or claim one-to-one attribution
  between those events. Executor receipts can include funds from other sources.
- Retain last-good observations for the same identity. Failed or unattempted reads
  remain unknown facts, distinct from a successful read of zero or an empty window.
- All operations remain public, keyless, read-only, bounded and cancellable. UI
  handlers and passive snapshots perform no network I/O.

Use the existing POOL4 panels. No new dashboard, transaction path,
generic scheduler, lifetime index or unrelated Launchpad collection is required.

## Evidence and source semantics

At Ethereum block 26,266,580, the adopted hook returned the current V2 executor from
`burnSink()`. The hook had approximately 35,135.9435 IMD settled, no outstanding burn
claim, and the executor held approximately 29.9462 IMD. A successful October 23 bridge
receipt sent approximately 159.563587 IMD. These are review observations, never
runtime constants. The raw review capture is `/tmp/maxpane-pool4-review/rpc-live.json`;
commit the minimal public fixture subset needed by tests with provenance.

The current implementation reads executor getters and bridge logs only through the
Launchpad path (`surf_client.py` / `SurfManager._spawn_launchpad`). POOL4 dynamically
discovers its hook and sink but does not independently collect the executor pipeline.
Its market BURN panel and protocol totals currently give hook settlement the stronger
meaning of completed burning.

Verified BaseBurnReceiver behavior: `token()` identifies its immutable burn token;
`burn()` burns its token balance and emits `BurnExecuted(caller, token)`. That event
has no amount and there is no cumulative-burn getter. The executor's empty compose
message does not automatically execute the receiver burn. Therefore:

| Stage | Authoritative evidence | Display boundary |
|---|---|---|
| Hook settled | Adopted hook `totalBurned()` | Hook allocation counter, not Base completion |
| Hook unsettled | Existing hook claim getter | Still owed by the hook, not yet executor inventory |
| Queued | Validated current executor token balance / existing preview getters | Executor inventory, potentially from multiple sources |
| Bridged | Valid executor `TokensBridgedForBurn` event in a successful Ethereum receipt | Latest observed send in the covered window |
| Base burned | Successful Base receipt with receiver `BurnExecuted` and matching token `Transfer(receiver, zero, amount)` | Latest receiver burn, not attribution to a particular bridge or hook |

The Base transfer must come from the validated receiver token contract in that same
receipt. A successful Ethereum transaction, an OFT delivery, a receiver balance change
or a `BurnExecuted` event without its matching transfer is insufficient amount proof.
Sum matching burn transfers only within a receipt when necessary; deduplicate by
transaction and log index. Do not sum unrelated token transfers or burns by other receivers.

## Data contract and collection boundaries

Root freezes the contract before parallel implementation. Use one new primitive payload
key, `pool4_burn_pipeline`, rather than duplicating lifecycle fields across the flat
snapshot. Existing hook keys keep their source meaning and remain compatible.

The frozen payload contains an identity binding and three independently observed stages:

| Member | Required content |
|---|---|
| `identity` | `network`, `hook`, `executor`, `token`, `oft`, `dst_eid`, `receiver`, `base_token` |
| `queue` | `state`, `read_ts`, `block`, `amount_wei`, `min_bridge_wei`, `bridge_amount_wei`, `decimals` |
| `bridge` | `state`, `read_ts`, `from_block`, `to_block`, `complete`, `event` |
| `base_burn` | `state`, `read_ts`, `from_block`, `to_block`, `complete`, `event` |

`event` is `None` or contains `tx`, `block`, `log_index`, `timestamp`, `amount_wei`
and `decimals`; a bridge event also contains `dst_eid`, `receiver` and `guid`.
Chain follows the stage and validated identity. Raw integer amounts and live
decimals are the calculation boundary; formatting belongs to widgets. Use existing
source-state conventions. `None` is never coerced into a factual zero. An empty covered
window is not a zero lifetime total. The two history stages retain separate success
clocks and coverage so one provider's failure cannot make the other appear current.

Discover from the adopted hook's current `burnSink()`, then verify the executor's
token/OFT/destination/receiver configuration and Base receiver token. Use the existing
network and token identity sources. An unsupported destination or failed binding leaves
that stage unverified; do not substitute a hardcoded receiver or reuse another market's
history. A late response for a replaced identity cannot overwrite its successor.

Reuse existing keyless state/log transports and ABI helpers. Current state must finish
independently of history. History uses pinned finalized heads and recent block spans:
50,400 Ethereum blocks and 302,400 Base blocks, with exact inclusive from/to blocks
recorded. These approximate seven days; do not claim exact time coverage without a
timestamp-boundary search. UI source detail says “recent window.” Base pages contain at
most 40,000 blocks; the publicnode endpoint rejects a 302,400-block request with its
50,000-block maximum. Reuse the existing bounded history helper and two-host empty-result
proof. Use a bounded request count and overall deadline; persist progress when coverage
cannot complete in one refresh. Root records measured request/deadline caps before
implementation. Measured implementation bounds: 12 accepted pages and 4,096 retained
logs per history invocation; 12-second queue/bridge deadlines and a separate 30-second
Base deadline. The measured cold Base scan needs about 20–26 seconds for eight pages,
three additional empty confirmations, headers and receipt proof. Queue success is due
after 30 seconds, history success after 90 seconds, and failure after 60 seconds.
Base logs use Publicnode plus the measured keyless Bloxroute fallback, which agreed on
an empty 40,000-block page, the latest positive event and the finalized block hash.
Base state retains the existing pool. Use existing due/TTL conventions instead of adding a timer layer.
An incomplete scan cannot be presented as an exhaustive latest event (`complete=False`).
Success without a matching event means “none observed in window,” never zero lifetime
burning. Keep a small reorg
overlap, deduplicate logs and verify selected receipts. Never scan from genesis.

Network, hook, executor or destination changes invalidate incompatible observations and
cursors. Cancellation drains reader tasks. Source completion can repaint from cache
without requiring a second network cycle or a navigation round-trip.

## Options

| Approach | Decision |
|---|---|
| Invoke Launchpad collection from POOL4 | Reject: unrelated launches, curves and keeper work; hides source ownership |
| New narrow reader using existing RPC helpers | Select: independent current state and bounded cross-chain evidence |
| Treat every bridge send as a confirmed burn | Reject: receiver execution is a separate transaction |
| Build lifetime cross-chain reconciliation | Defer: unnecessary for the latest-executor bug and exceeds available attribution evidence |
| Retain existing labels with explanatory prose elsewhere | Reject: the visible numbers themselves need accurate labels |

## Work packages and ownership

### WP0 — Verify bindings, bounds and freeze the contract

Owner: root session. Owns source investigation and the final field schema.

1. Capture minimal public executor configuration, bridge receipt and Base burn receipt
   evidence with chain, block, observation time and contract provenance.
2. Measure keyless RPC limits; choose explicit chunk, request, retention and deadline
   bounds for the recent block windows. Confirm live token decimals.
3. Freeze the reader result and `pool4_burn_pipeline` payload with both implementers.

Acceptance: each stage has an authoritative positive fixture and a defined unknown /
empty result; Base proof validates the transfer amount independently of bridge amounts.
Source access gaps are research dependencies, not user-approval blockers. If a source
cannot provide proof, preserve the explicit unknown fact instead of inventing evidence.

### WP1 — Narrow executor and Base evidence reader

Owner: data implementer. Owns a focused module such as
`maxpane_dashboard/data/surf_pool4_burn.py`, its dedicated tests and fixture directory.
May edit `surf_client.py` and `surf_launch_base_client.py` only for agreed small helper
exposure; root coordinates any shared-file changes. Does not edit manager, models or cache.

1. Write failing decoder and transport-fixture tests for current V2 configuration,
   queue/preview values, recent bridge and verified Base burn receipt.
2. Implement current state and independently bounded history operations using existing
   RPC clients. Validate every identity and preserve per-source observations.
3. Reject wrong receiver/token/destination, failed receipts, malformed data, unrelated
   transfers and absent burn proof. Preserve resumable coverage and reorg deduplication.
4. Prove timeout, request limits, cancellation and response identity handling offline.

Acceptance: a cold narrow reader supplies current V2 evidence without invoking Launchpad;
slow or failing Base history cannot delay the current Ethereum queue result. All tests
inject transports and use committed fixtures. Decoder mutation tests must fail.

Dependency: WP0 contract. Can run alongside WP2 because ownership is disjoint.

### WP2 — Accurate POOL4 presentation

Owner: UI implementer. Owns `widgets/surf/pool4u_burn.py`, `pool4_split.py`,
`pool4_ratchet.py`, `protocol_hero.py`, `screens/surf.py`, mirrored theme rules only if
necessary, and their focused widget/screen tests. Does not edit data files.

1. Write failing composited-output tests for settled versus confirmed burn language,
   Ethereum supply qualification, pipeline values, unknowns and covered empty windows.
2. Pass the frozen payload through both POOL4 views. Present queued inventory, latest
   bridge and latest verified Base burn with concise stage and scope labels. Existing
   hook allocation and unsettled values remain separately understandable.
3. Remove claims that the hook counter or its supply percentage proves Base burns.
   Never suggest that executor-wide bridge/burn activity belongs exclusively to POOL4.
4. Preserve the existing layout at 149×45 where possible. Render before changing pins;
   use existing formatters, shared address links and loading-footer conventions.

Acceptance: direct POOL4 market and protocol entry show the same source meanings;
unread values remain dashes in these panels; longer values fit in composited output.
No widget reads data or clocks. New visible addresses follow the shared copy/link rules.

Dependency: WP0 contract. Final integration depends on WP3. Do not harden layout pins
or their documentation before root shows the actual live render.

### WP3 — Lifecycle, cache and snapshot integration

Owner: root session, sole owner of `surf_manager.py`, `surf_models.py`, `surf_cache.py`,
their manager/cache/model tests, and lifecycle documentation.

1. Add failing cold-entry tests for both POOL4 views, with no previous Launchpad visit.
2. Add the independent single-flight source offer, due checks and loading participation.
   Keep current queue and the two history stages independently completable.
3. Persist validated last-good values; retain bounded scan progress in the session,
   rebuilding the bounded window after restart, as the shared history helper requires.
   Guard against late identity
   responses; invalidate unrelated history on network/hook/sink/destination changes.
4. Include all new tasks in cancellation, drain and close; preserve passive snapshots.
   Merge individual source results without clobbering successful sibling stages.
5. Wire exact widget signatures and snapshot projection once WP1/WP2 interfaces agree.

Acceptance: direct-entry manager tests prove offers, completion, cache-only repaint,
failed-source retention, last-good restart, in-session resume and identity replacement. Concurrency mutation
tests catch removed identity/cancellation guards. Existing Launchpad behavior is unchanged.

Dependency: interfaces frozen in WP0; integration follows WP1. Skeleton manager tests may
start in parallel. Other agents must not edit these shared root-owned files.

### WP4 — Live verification, focused regression and final review

Owner: root session. Owns final integration fixes and follow-up documentation.

1. Render both views keyless with live data at 149×45 and show the owner before pin
   sweeps, layout documentation or final review. Compare visible stages to independently
   captured chain evidence; record chain/block/time and coverage limitations.
2. If the measured layout requires a pin change, use the terminal-layout workflow and
   prove the boundary with the mandated mutation. Otherwise retain existing pins.
3. Run touched tests plus composing POOL4 manager/screen files once, with isolated caches
   when parallel, and `guard and not mounts_app`. Include doc-pin tests for doc changes.
   No full suite unless requested or a version is tagged.
4. Request one final whole-change review with the repository reviewer contract. Fix
   at most one final-review wave; re-review the affected scope only when production
   code changes. File Minor-only findings and remaining provider limits as follow-ups.

Completion requires visible latest-executor coverage from a cold POOL4 entry, accurate
stage labels, independently verified Base amount evidence when available, passing scoped
tests and mutation proofs, and recorded live rendering. Do not claim confirmed burning
where the destination evidence remains unavailable or outside verified coverage.


## Implementation evidence — 2026-10-25

The implemented payload is `POOL4_BURN_FIELDS` in `surf_models.py`, with one
independent cache slot. `Pool4BurnClient` borrows the existing POOL4 transport.
Queue reads dynamically recheck `burnSink()` and the executor configuration at
one Ethereum block. A positively observed incompatible binding clears old stages
even when subsequent getters fail; an unobserved outage preserves last-good facts.
A generation guard prevents cancelled reads publishing after a view/identity switch.

The source reader measured 0.326 seconds / 3 HTTP requests for queue, 2.637 seconds /
14 HTTP requests for Ethereum history, and 20.127 seconds / 16 HTTP requests for
Base history. The real manager's first complete cold pipeline took 31.66 seconds,
including discovery and independent view work. No Launchpad visit was made.

| Live stage | Observation |
|---|---|
| Hook settled | 35,135.94350285028 IMD; zero unsettled burn claim |
| V2 executor queue | 29.946233978030186465 IMD at Ethereum block 26,266,709 |
| Last bridge | 159.563587 IMD, Ethereum block 26,257,982 |
| Last verified Base burn | 159.563587 IMD, Base block 53,000,745 |
| Ethereum wrapper supply | 4,165,864.945986 IMD; settled/supply 0.84342493% |

The two event amounts are separate observations from separate receipts. Ethereum
coverage was blocks 26,216,215–26,266,614; Base coverage was 52,750,066–53,052,465.
Neither window is a lifetime total or a proof of POOL4-only attribution.
Committed evidence is `tests/fixtures/surf_pool4_burn/live.json` plus
`base_log_fallback.json`. Temporary detailed captures and the shown live renders are
under `/tmp/maxpane-pool4-review/pool4-pipeline-*`; request measurements are in
`reader-measured.json`. These local observations are dated, not runtime constants.

Both live views were shown at 149×45 before layout hardening. Market now fits
148×42; protocol remains 138×44. Positive, empty, incomplete and uint256-max payloads
fit the measured pins. Both market-height mutations and the manager generation
mutation were killed; four receipt/filter mutations were also killed.
