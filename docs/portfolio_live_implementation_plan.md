# PORTFOLIO — live integration plan

Status: **implemented and verified**. The owner
approved the Textual preview, including **P/L**, then authorized the build.
Packages 0/A/B/C/D are implemented and package reviews are approved. Package E
is integrated with the hub; actual live rendering preceded final hardening.
Final review is approved after fixing ISO unlock timestamp normalization and
proving the captured-claim detail regression with a killed mutation.

The plan below records the approved work breakdown. Live sources are now
established in `portfolio_game_mechanics.md`; remaining limits are tracked in
`portfolio_followups.md`. No verified keyless cost-basis acquisition was found,
so live P/L deliberately stays unavailable. Token decimals are reread with each
balance batch instead of separately cached, avoiding stale proxy metadata.

## Approved outcome and scope

Preserve the 149×45 design, four heroes (HELD VALUE, CLAIMABLE, IMD AGENTS,
P/L), native BASE TRADING/shared panel adaptations, supporting panels, filters,
detail flow and table. Keep IMD/ETH launch liquidity in PAIRED LP and detail.
Show every discovered swarm token with a positive selected-wallet holding or
verified ready claim, including claim-only and unpriced holdings. Agent
association describes the whole wallet; every token panel follows one filter.

Use Python/Textual/Rich and the existing read-only, keyless architecture.
No signing, transaction construction, API keys, private keys or claim execution.
No new market client, duplicated catalogue polling or new top-level game.
Estimated production scope is **1,500–2,500 lines**, excluding fixtures/tests;
source limitations may change that estimate. Use normal Tier 2 package reviews
and final review, not the under-1,000-line exception. No scheduling estimate.

## Confirmed reuse versus source-validation work

Confirmed in the repository:

- `SurfManager.swarm_tokens_manager()` retains one `SwarmTokensManager` and
  closes it; `swarm_tokens_source()` supplies versioned launch/LP evidence.
- `SwarmTokensClient.fetch_page()` validates numeric-cursor catalogue pages.
  The manager retains partial scans, independent market/history/trade caches,
  bounded scheduling and source clocks. These are session caches, not a new
  Portfolio persistent store. `_tokens()` currently selects only `live` launches
  on chain IDs 1, 8453 and 4663; its output is insufficient for wallet discovery.
- Existing market quotes, selected-pool histories/trades and launch liquidity
  can be shared. `analytics/portfolio.py` already supplies identity deduplication,
  filtering, valuations and remaining-position P/L arithmetic, but currently
  drops source metadata and does not validate cost-basis provenance/freshness.
- The screen already clears rows and guards wallet generations. Hub routing
  still creates `DemoPortfolioManager`; detail/chrome still assume mock data.

Unverified: exact earned/allocation schemas, pagination, units, contract identity,
claimed-state reads, unlock authority and historical agent-to-wallet linkage.
`portfolio_game_mechanics.md` records documented earned, claim, launch-allocation
and wallet-pair routes; documentation alone does not establish a working source.
Reliable remaining-position USD basis is also unresolved. Do not invent ABI
signatures, contract addresses, endpoint paths or a successful source response.

## Contract and semantic decisions to freeze first

Retain the mock contract and widget signatures; add explicit live key tuples in
`portfolio_models.py`. Freeze names/types with fixture evidence before dispatch.
The following are required semantics, not claims of existing APIs:

- Identity is normalized `(chain_id, token_address)`, with launch UUID/number
  as provenance. Preserve aliases where several launches reference one token;
  sum distinct reward allocations once rather than dropping them with token
  deduplication. Shared market identity and launch-position identity stay separate.
- Snapshot carries wallet, wallet generation, evaluation time, `is_mock=False`,
  and `sources`. Each source has its own last-success time, attempt/state and
  coverage; snapshot time cannot refresh a failed balance, claim or quote.
- Track catalogue scan completeness, supported/unsupported chains, candidate
  counts, balances checked, known positives/zeros, claims checked and failures.
  Coverage includes unresolved candidates absent from the visible table. An
  empty filtered table never establishes an empty wallet during an incomplete scan.
- Keep balance raw integer, observed decimals and read block/time at the data
  boundary. Decode before display conversion; missing decimals never means 18.
  Zero requires a successful read. No malformed/nonfinite/negative value becomes
  a valid quantity. Cache chain/token decimals separately from wallet balances.
- Add independent balance, claim, agent and basis states/clocks alongside the
  existing market/history/trade/liquidity states. Distinguish pending, known zero,
  partial, stale, unavailable and unsupported; retain last-good values with age.
- Only verified unlocked, unclaimed allocation enters ready claims. Cached ready
  claims may remain as visibly stale rows, excluded from current claim valuation.
  Locked/claimed/unverified allocations remain distinguishable in cached detail.
- Preserve `held_cost_usd`, adding provenance, quantity coverage and basis state/
  clock. Live rows default it to `None`; synthetic demo basis is never imported.
  P/L is unavailable if any in-scope held valuation/basis or discovery/balance
  coverage is incomplete. Claims and realized gains stay excluded. A genuinely
  verified zero basis has no percentage; zero basis must never be inferred.
- Source coverage survives projection/filtering. Token totals use matching IDs;
  wallet-wide discovery/agent state remains explicitly scoped. Unknown token
  membership cannot silently become complete filtered coverage.

## Work packages and exclusive file ownership

Each package has one implementer. Root owns shared integration files throughout;
no worker edits another package's files. New file names below are proposed paths.

### 0 — source feasibility and contract freeze (root)

Own `data/portfolio_models.py`, research updates in `docs/portfolio_game_mechanics.md`
and `tests/fixtures/portfolio/discovery/`. Capture minimal public payloads and
read evidence with source/time/chain metadata; tests consume committed fixtures,
never live APIs. Validate earned enumeration, no-allocation vs failed lookup,
allocation IDs/units, deployed reward contract, authoritative claimed/unlock
state and agent linkage. Record precise verified read contracts locally.

Investigate basis feasibility separately: complete acquisition/disposal history,
transfers, rewards, remaining quantity reconciliation and historical USD quotes.
Document an inventory-allocation and conversion rule before emitting any basis.
Transfers/rewards are not automatically free; missing upstream basis, missing
history or unsupported rebasing behavior means unavailable. Do not build an
unbounded history crawler merely to fill P/L. If no reliable keyless source is
demonstrated, plan the unavailable P/L state and leave numeric basis deferred.

Acceptance: frozen primitive contract, fixtures identifying established facts
and gaps, and an explicit availability decision for claims, agents and basis.
Unavailable basis does not block balances/claims; missing claimed/unlock proof
blocks confirmed-ready claims and is reported as a remaining requirement.

### A — shared catalogue and enrichment seam (market implementer)

Own `data/swarm_tokens_manager.py`, `data/swarm_tokens_client.py`,
`data/swarm_tokens_models.py`, `tests/data/test_swarm_tokens_live.py`,
`tests/data/test_swarm_tokens_source.py` and `tests/fixtures/portfolio/catalogue/`.
Expose a public cached complete-candidate projection and shared enrichment offer
through the retained manager; do not make Portfolio reach into private caches.
Separate deployed-token discovery from SWARM TOKENS' existing live-only view.

Acceptance: all pages are traversed across bounded refreshes; status changes
cannot hide a verified deployed holding; malformed/nonprogressing pages never
certify completeness; ambiguous artifacts and unsupported chains are reported.
Prioritize relevant Portfolio tokens within existing enrichment budgets, without
starving the market view or issuing duplicate work when both screens are used.
Keep current market-view semantics and source clocks; provide sparse records
when deployment is known but quotes or launch evidence are unavailable.

### B — multichain wallet balances (balance implementer)

Own new `data/portfolio_balance_client.py`,
`tests/data/test_portfolio_balances.py`, `tests/fixtures/portfolio/balances/`.
Reuse established RPC transport/error handling and supported chain pools;
read token balances and actual decimals for all verified catalogue candidates.
Use bounded batches/concurrency, independent per-chain progress and injected
transport/clock. Every read must be tied to the intended chain and wallet.

Acceptance: mixed decimals, large raw amounts, positive/unpriced holdings,
successful zero, revert/malformed return, partial batch failure and unsupported
chain fixtures all preserve honest quantities and coverage. Failed reads retain
qualified last-good balances; no first-read failure is interpreted as no holding.
Any required shared endpoint-pool edit belongs to root and needs source evidence.

### C — claims and agent association (claim implementer)

Own new `data/portfolio_claims_client.py`, `tests/data/test_portfolio_claims.py`,
`tests/fixtures/portfolio/claims/` and any new verified Portfolio claim ABI JSON.
Implement only reads validated in package 0; reuse existing public swarm
transport and seat/presence primitives where their semantics match.

Acceptance: reconcile wallet-earned entries with allocation, deployed token,
chain/decimals, authoritative claimed status and unlock evidence at a recorded
chain read/time. Test duplicate allocation leaves, pagination, null allocation,
locked/unlocked boundary, already/partially claimed if supported, stale failures
and conflicting identities. Never multiply one wallet allocation by agent count.
Current association/presence is separate from historical reward entitlement;
offline/transferred agents cannot erase earned claims. Unknown linkage is shown.

### D — wallet manager and pure live projection (portfolio implementer)

Own new `data/portfolio_manager.py`, existing `analytics/portfolio.py`,
`tests/data/test_portfolio_live.py` and `tests/analytics/test_portfolio.py`.
If package 0 verifies a bounded keyless basis-acquisition path, also own and
implement new `data/portfolio_basis_client.py`, `tests/data/test_portfolio_basis.py`
and `tests/fixtures/portfolio/basis/`. Test complete history/remaining-quantity
reconciliation, transfer/reward uncertainty and historical USD conversion gaps.
Borrow the retained market provider; own only wallet balance/claim/basis state.
Inject clients, clock and task completion seams. Give catalogue, balances,
claims, agents and optional basis independent bounded refresh policies.

Acceptance: `set_wallet` increments generation and invalidates wallet data
immediately. Every result/cache write checks captured wallet + generation;
cancelled or late wallet A results cannot enter wallet B or a later A session.
Shared market/decimal caches survive switches; owned tasks close cleanly without
closing the borrowed provider. Deterministic interleaving tests cover these races.
Merge balances and deduplicated claims before one coherent projection; preserve
coverage/clocks and cached detail. Test missing sources, partial/stale valuations,
distinct LP positions, filters, and numeric P/L only for complete verified basis.
Unless package 0 proves acquisition feasibility, emit unavailable basis/P/L with
a precise reason; no mock fallback and no cost inferred from 24h price changes.

### E — approved UI and lifecycle integration (root)

Own `data/surf_manager.py`, `screens/portfolio.py`, `screens/surfboard.py`,
`widgets/portfolio/`, `widgets/surfboard/rack.py`, `themes/minimal.tcss`,
`demos/portfolio.py`, composing screen/hub tests and required guard registries.
Add retained Portfolio ownership/close alongside the shared market provider,
then replace only the hub's mock destination. Preserve standalone offline demo.

Acceptance: startup uses saved/environment wallet; accepted wallet input controls
this session. Live chrome/detail use real source state and age, with no MOCK DATA
or sample basis; the demo remains clearly mocked. Preserve the approved layout,
draft filters, stable selection and Escape behavior. Contract/token links use
verified row chain through shared address/explorer helpers; unknown chains get
no guessed explorer. Detail remains cached; no network await in message handlers.

## Dependencies, validation and review

Package 0 freezes contracts first. A/B/C can then run in parallel because their
files are disjoint. D can prepare against contract fakes, but integrated D
depends on A/B/C outcomes. E may prepare UI states in parallel; live routing
depends on D. Root alone coordinates shared hooks, model changes and registries.

Use TDD: failing fixture/behavior test, smallest implementation, green refactor.
Add mutation proof for decoders, wallet-generation races and any moved layout
pin. Run focused cases during work, then touched and composing files once plus
fast non-mounting guards, relevant registration checks and address sweeps.
All tests prohibit network and real clipboard/browser effects; no full suite.

Before layout hardening or final review, show the real keyless live screen at
149×45 for the selected wallet, including source gaps; a fixture render cannot
replace this live-phase step. Verify smaller composited layouts and CSS mirror.
Give each package diff one task review, at most two fix rounds; then one final
whole-feature review on the most capable model, one fix wave and one scoped
re-review only for production fixes. File Minor-only findings as followups.
Completion evidence must distinguish implemented live sources from unavailable
ones; unresolved claims cannot be described as full feature completion. No
additional design approval is requested by this plan.
