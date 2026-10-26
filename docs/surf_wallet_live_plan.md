# WALLET / SWARM — production integration plan

Date: 2026-10-26. Baseline: `dc94e8e9`. User authorization: **“ja so umsetzen”**.
Tier 2: new nested screen, primitive data contract and read adapters. The live
PRD is `surf_wallet_live_PRD.md`; approved visuals remain the existing A/B demo.
No new top-level dashboard or paid Swarm operation is planned.

## Architecture and work split

Use the existing flow: keyless clients → retained wallet manager → primitive
snapshot → shared screen lifecycle → render-only widgets. Reuse existing RPC,
host rotation, address/explorer, panel, hero and segmented-meter components.
Keep application interpretation in pure analytics and reviewed local rules.

The expected production change is approximately 1,100–1,700 lines across data,
evidence, presentation and integration. This is an estimate, not a code limit.
Use the normal Tier-2 task review per completed package plus final branch
review. Root may record a smaller frozen estimate before implementation if
substantial reuse puts the entire change below about 1,000 production lines;
only then does the documented final-review-only exception apply. Do not remove
validation or evidence semantics to meet that threshold.

| Package | Owner and exclusive files | Dependencies |
|---|---|---|
| 0 — contract | Root: `data/surf_wallet_models.py`, agreement fixture/schema and final interface section below | This PRD and source probes |
| 1 — orders and retained state | Data implementer: wallet-specific client/manager/cache and pure analytics; corresponding data/analytics tests and wallet fixtures. Root explicitly assigns any edit to `surf_swarm_client.py`. | Frozen package 0 |
| 2 — A/B presentation | UI implementer: `widgets/surf_wallet/` and corresponding widget tests. Root owns `screens/surf_wallet.py`, screen tests and shared stylesheet insertion. | Frozen package 0; uses fixture snapshot while 1 runs |
| 3 — onchain evidence | Root: wallet evidence adapter and reviewed local usage rule/ABI fixtures; corresponding evidence tests | Frozen contract; package 1 artifact/payment candidates |
| 4 — shared integration | Root: `screens/surfboard.py`, `data/reader.py`, `data/surf_manager.py`, `themes/minimal.tcss`, README shortcut and integration/registration tests | Packages 1–3 available |

Planner owns only this plan and `surf_wallet_live_PRD.md`; root takes over their
execution records after planning. Workers are not alone: never revert another
owner's work. Packages 1 and 2 may run in parallel after the contract is frozen;
3 can proceed independently on committed evidence fixtures. Shared integration
is sequential and has one owner. No subagent may create more subagents.

## 0. Freeze the primitive interface

Export the snapshot key list, row fields and widget signatures before workers
start. Freeze the manager constructor and supported lifecycle methods, its
wallet identity representation, source clocks/coverage, and artifact-selection
key. Use Python primitives at the widget boundary; amounts may be exact strings
or integer atomic values with proven decimals, never binary-float sums.

Required semantic groups: selected wallet, observed requests, artifacts,
request/payment summaries, onchain signal/coverage facts, source observation
times and coverage. Distinguish unread None from observed empty lists and exact
zero. Data contracts carry facts; widgets own human-readable rendering.

Acceptance: one agreement test binds widget inputs to declared keys, no widget
imports a data module, and all owners receive the same frozen interface.

## 1. Public requests, result joins and retained wallet state

1. Capture a trimmed public paid-by payload and representative result/schedule
   shapes under `tests/fixtures/`. Add tests before validated public wrappers.
   Use `SwarmClient._get(..., params=...)` and existing pooled reads, never a
   tokenless request-detail call or arbitrary result URL.
2. Normalize action and request identity independently from execution result.
   Join explicit job, workflow, launch, oracle and schedule IDs. Launch actions
   resolve through their result job's launch. Keep child work and automatic
   schedule runs as linked context rather than duplicate direct requests.
3. Build attributed sites/projects and confirmed deployment candidates. Dedupe
   sites by project and contracts by `(chain_id, address)`; tokens stay a subset.
   Never infer artifact ownership from a seat, contributor or text similarity.
4. Add retained wallet snapshots with per-source observation times, success TTL
   and failure retry. Polling deadlines/concurrency limits bound work; unfinished
   cursors/IDs remain eligible in subsequent cycles. Record partial coverage
   instead of pretending the truncated set is a complete catalogue.
5. Wallet changes cancel/retire reads, clear current identity state and reject
   late commits. Same-wallet failures preserve last observed facts and clocks.
   Empty responses, failed reads and absent wallets remain distinct.

Acceptance: fixture cases cover multiple actions, malformed payloads, unknown
result kinds, duplicate links, two token/contract representations, latest-100
truncation, schedule cursor interruption, failure retention and delayed old-wallet
responses. All overview data loads without opening detail. The manager owns
only its created clients and supports the shared lifecycle/drain barrier.

## 2. Production A/B presentation

1. Adapt the approved composition to the frozen live snapshot using shared
   `HeroRecord`/`NewsHeroCard`, `PanelBase`, sparkline and `meter_text` components.
   Eliminate all fixed sample counts, dates, fabricated evidence and demo imports.
2. Render six heroes, four compact insight widgets, CREATED, relationship path,
   follow-ups and RECORD in A. Scope denominators and labels to observed data;
   unknown execution states do not imply success. A/B changes are cache-only.
3. Render B's selected details and payment widget. Preserve stable artifact ID
   through refresh/reordering, arrow selection, Enter, Escape and scroll changes.
   Missing selections resolve deliberately without pointing at another row's
   evidence. Guard queued highlights from hidden/previous views.
4. Use shared link/copy helpers for addresses and validated evidence links.
   Long names, markup-like payloads, mixed assets, empty data and unknown usage
   remain readable. Scrolling handles variable detail content.

Acceptance: actual compositor assertions at 149×45 prove complete card frames,
footers, metrics, diagrams and table columns. Unknown/static/partial cases stay
honest. At 100×30 all parts remain reachable and resizing restores layout and
identity. No I/O, key material, signing or clipboard access occurs in tests.

## 3. Receipt and application evidence

1. Resolve public payment transaction evidence with existing ETH/Base/RH state
   clients. Confirm canonical successful receipts, explicit payer/recipient/asset
   attribution and live decimals. Multiple plausible transfers remain ambiguous;
   never use current quote prices or total transaction outflow as payment proof.
2. Preserve chain/asset groups and payment evidence links. Do not turn absent
   refunds into zero or show net paid as complete when refund coverage is absent.
3. Reuse existing deployment checks for candidate contracts. A successful job or
   claimed address is insufficient to count a confirmed deployment.
4. Implement the first reviewed non-trading utility adapter only after its
   deployed identity/code and event interpretation are verified. BurnTracker
   is a candidate; owner setup/recovery actions must not be counted as ordinary
   user usage without an explicit semantic decision. Vendor the reviewed ABI
   and rule locally and retain source/commit/code evidence.
5. Use existing bounded log-history behavior and actual chain capabilities.
   Establish exact time/block windows and successful canonical event receipts.
   Positive partial history gives a lower bound; complete zero gives QUIET;
   missing/unsupported/failed history stays NO DATA. Changed code invalidates
   the matched rule. A site's mirrored evidence is not counted twice.

Acceptance: tests reject wrong chain, code mismatch, failed/noncanonical receipt,
duplicate log, ambiguous payment, unavailable decimals and incomplete-zero
windows. A meaningful mutation must redden a named decoder/evidence test.
Unsupported artifacts remain usable in the inventory with explicit unknown
evidence. No fallback to swaps, generic token transfers or site telemetry.

## 4. Reader and Boardroom integration

Add a retained `SurfManager.wallet_manager(wallet=...)` child and parent-owned
closure. Add the explicit `ReaderHandle.wallet_manager` wrapper; arbitrary
factory forwarding through `__getattr__` is not supported. Reuse the reader's
wallet metadata invalidation and normal `SurfDashboardScreen` refresh/drain
lifecycle rather than a second worker implementation.

BOARDROOM `u` pushes the nested view, with an input-focus guard and retained
wallet/view state. Inside the view, `w` reuses `WalletInputScreen`, `r` refreshes,
Escape returns B→A→BOARDROOM, and Tab remains local navigation. Preserve the
parent terminal draft/focus. Do not seed from an agent or add a top-level game.

Insert screen CSS identically into `DEFAULT_CSS` and a bounded stylesheet
section; use explicit section markers. Add the real shortcut to README and
visible hints. Integration tests cover the actual ReaderHandle child factory,
identity metadata, owned/borrowed closure, empty/prompt-cancel/change flows,
literal `u` in terminal input and reopened wallet state.

## Verification, reviews and completion

During editing, run only named tests for the touched behavior. Before commit,
run touched and composing files whole, plus fast guards and the required
registration/mount checks because a binding changes. Include the 12 docpins.
Use isolated temporary test state; no unit/compositor test makes a live call.
Root selects the final exact file list from the actual diff rather than running
the repository suite. No full suite unless the owner asks or a version is tagged.

Record at least one killed concurrency/identity mutation and one killed evidence
decoder mutation; pin changes require the prescribed boundary and inverse
mutation checks. Test both sides of measured layout thresholds with normal,
unread, empty and adverse payloads. Do not derive production pins from the demo.

Root shows real keyless A/B renders for the configured wallet at 149×45 before
hardening geometry or dispatching reviews. Capture source response clocks,
coverage, amounts actually proven, unmatched usage rules and observed latency;
never convert a live access failure into fabricated sample values. Read-only
runtime verification is separate from deterministic offline tests.

Each applicable task review receives the exact `CLAUDE.md` reviewer contract and
its owned diff; no reviewer fixes code or runs a suite. Cap task fixes at two
rounds. Final whole-branch review uses the most capable model after integration,
with one fix wave and one scoped re-review if production code changed. File
Minor-only findings in the follow-ups record without widening this task.

Completion records the installed entry key, real data coverage, matching usage
adapters, successful checks, baseline failures, preview paths and commit. Commit
only task-owned files; no push, deployment, payment or external message follows
from this dashboard authorization. The existing standalone DEMO stays runnable.

## Frozen interface and execution record

The contract was frozen in `data/surf_wallet_models.py` before workers started:
`wallet_snapshot` contains `wallet`, `orders`, `artifacts`, `schedules`,
`payment_totals`, `sources`, `coverage`, `as_of`. Unread populations are None;
observed empty populations are lists. `WalletBody.update_data(wallet_snapshot)`
is the sole presentation dispatch. Same-wallet identity uses stable artifact IDs.

The retained manager borrows `SwarmClient` and an evidence adapter. Its first
publication contains direct API orders; it does not await receipts to paint.
`fetch_and_compute` offers detached work; `set_active_view`, `set_wallet`,
`drain_reads`, `is_loading`, `get_snapshot` and `close` follow the reader lifecycle.
`wait_pending` supports deterministic tests and the explicit live capture.
Success/failure retry is 30/60 seconds from completion; detail memo is 120/60
seconds. Detail work is bounded to 48 reads per cycle and four concurrent reads;
unread IDs are prioritized ahead of already observed rows. Schedules stop at
four 100-row pages per cycle with explicit partial coverage and a per-wallet
continuation cursor. Public catalogues persist in
`~/.maxpane/surf_wallet.json`, validated separately for each wallet.

The root adapter borrows existing ETH/Base/RH state clients, verifies chain ID,
successful two-block-confirmed canonical receipts, payer/asset/recipient transfer
attribution and live historical decimals. It does not sum transaction outflow or
quote current prices. Its 150-second budget preserves completed evidence.
The first reviewed usage rule binds BurnTracker's Ethereum address and runtime
Keccak to `Ordered(bytes32,uint8,address,uint256,string)` with kind 2. Setup and
owner recovery are excluded. The exact 24-hour block window uses timestamp
binary search, the existing independently confirmed log-window reader and
successful matching event receipts. No generic Base/RH utility rule is claimed.

Live keyless capture, 2026-10-26 05:16 UTC, elapsed 8.88 seconds:

- Five admitted requests: two new jobs, one continuation and two launches.
- One site (`swarmstreet`) and one confirmed contract (`BurnTracker`). The other
  launch is blocked; its order remains an attention item.
- Five payer receipts establish 2.5 IMD paid on Ethereum, with decimals read at
  the receipt blocks. Refund and net-paid history remain unknown.
- BurnTracker: one refresh request by one address in blocks 26267538–26274710,
  through 05:15:59 UTC. The receipt ends in `3e06e2f`. This is a captured
  observation, not a permanent counter or proof of frontend site traffic.
- The factory creation receipt has no direct `contractAddress`; runtime matches
  the published attestation. The view explicitly qualifies address linkage as
  relying on the launch artifact.

Actual production A/B renders were shown at 149×45 before task reviews:
`/tmp/maxpane-wallet-live-{overview,detail}.{png,svg,txt}`. The initial monochrome
shell export was rerendered with normal terminal color support. These files
contain live captured public facts; the old standalone demo remains synthetic.

Verification and review outcomes are recorded below as they complete.


Measured production viewport boundary: 145×45 in both A/B, after checking all
36 combinations of widths 144–149 and heights 44–46 against the captured live
snapshot. At 144×45 overflow is x=2/y=1; at 145×44 x=1/y=2; at 146×44 x=0/y=1.
At 145–149×45/46 the outer viewport is whole. Narrow 100×30 remains scrollable.
Both directions of width/height pin mutation were killed by the measured
boundary test; unchanged CSS geometry is linked to named screen constants.

Task reviews and their scoped re-reviews finished with all findings ADDRESSED;
see `surf_wallet_live_followups.md`. Regression mutations cover malformed event
zero, budget continuation, dependent joins, payer filtering, runtime invalidation,
nested cache validation, schedule continuation, partial amount qualifiers,
unread selected identity and cross-wallet card retention. All mutation tools
restored original file bytes.

Required verification so far: wallet address sweep passed at wide and measured
pin sizes; universal screen dispatch passed; 12 docpins passed; fast guards
129 passed with one baseline CSS failure. Broader composing files returned
222 passed and 11 failures; all 11 plus the guard failure reproduced on an
isolated unchanged baseline. Wheel build succeeded offline and its ZIP includes
the wallet screen, widgets, evidence adapter and local reviewed rule JSON.
No full suite, external write, signature or paid operation was performed.


Final review completed: Approved after one fix wave and scoped re-review.
Duplicate persisted IDs are rejected; retained utility keeps its original clock
only on a failed read against the same code identity. Unsupported/invalidated
rules clear it. Source clocks remain separate in both the snapshot and the
ONCHAIN insight title. Validated onchain capability rows supply each chain's
payment asset/recipient, in addition to HTTP capabilities.

Final cold live refresh at 05:42 UTC took 31.43 seconds, with five requests,
two artifacts and 2.5 IMD proven. Its utility window was unavailable and rendered
NO DATA. A direct read of the earlier successful refresh receipt still decoded
correctly; it is not substituted for a complete current window. The preview
files now show this final honest cold-start state.

Required mount checks: 60 passed, one baseline outage-notice expectation failed
and was reproduced separately on the unchanged archive. The prior 12 baseline
failures plus this one are documented in the follow-ups. The IMDB task-close
marker was recorded with `bin/kb none`; this task's implementation evidence
lives in the project documents rather than a new protocol lesson.

Final composed wallet run: **94 passed** (analytics, manager, evidence, parent
ownership, widgets and production screen), including actual ReaderRuntime
publication without opening detail. The two exact final-review reproductions
also passed. Offline wheel rebuilt successfully after the final code changes;
all owned Python modules compile and required package artifacts are present.
