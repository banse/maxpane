# PORTFOLIO dashboard — design research

Date: 2026-10-10. Status: the owner approved the completed Textual design,
ASCII option 1 with the P/L hero. Live wallet integration is implemented.
The approved design is in `portfolio_PRD.md`; the completed mock work is in
`portfolio_implementation_plan.md`, and live work packages are in
`portfolio_live_implementation_plan.md`.

## Requested outcome

Open PORTFOLIO from the SURFBOARD hub, set a wallet using THE LIST's existing
flow, and see swarm-launched tokens held by that wallet plus tokens claimable
through its IMD agents. Reuse BASE TRADING widgets and SWARM TOKENS fetching,
enrichment and liquidity presentation. Follow native MaxPane styling and KISS.

The approved design target is 149 columns by 45 rows. The offline composition
has since measured a 145×35 minimum for fixed chrome.

## Repository evidence and reuse

- `screens/wallet_input.py::WalletInputScreen` and
  `screens/curator.py::action_set_wallet/_wallet_entered`: validated address
  input, persistence, immediate wallet identity repaint and wallet-scoped refresh.
  `config.py::get_wallet` currently prioritizes MAXPANE_WALLET over saved config;
  Portfolio must define the effective wallet consistently when it is changed.
- `screens/surfboard.py` and `widgets/surfboard/rack.py`: PORTFOLIO now has an
  active live hub card, backed by a retained `PortfolioManager`. The standalone
  mock stays separate; no top-level dashboard entry was added.
- `widgets/base/overview/`: hero, table, sparkline, signals, activity and movers
  components. Reuse their shared panel bases and suitable renderers through
  small adapters; their ETH-market labels and Base-only explorer are not valid
  unchanged for a multichain wallet portfolio.
- `data/swarm_tokens_manager.py::SwarmTokensManager`: retained catalogue,
  market/history/trade caches, source clocks and launch-liquidity enrichment.
  Borrow the existing manager; do not create a second market polling stack.
- `data/swarm_tokens_models.py` and `analytics/swarm_tokens.py`: primitive token
  payloads, filtering and independent IMD/ETH paired-liquidity aggregation.
- `widgets/swarm_tokens/`: multichain market rows, token details, filters,
  observed price sparklines and liquidity formatting.
- `data/surf_swarm_client.py::fetch_seat` and existing SURF agent projections:
  seat detail and presence. Existing `surf_agent_rewards_spec.md` measures IMD
  already paid; it is not a source for unclaimed launch-token allocations.

The market dashboard keeps its `live` launch view on chains 1, 8453 and 4663.
Its new `fetch_portfolio()` seam discovers token artifacts across launch states,
retains launch aliases and reports unsupported/ambiguous candidates. Both views
share bounded enrichment and source clocks. Holdings and ready claims receive
priority while remaining candidates continue to advance.

## Current external evidence

The [official IMD documentation](https://imd.fun/docs/) was checked this session.
It documents these public reads:

- Explorer `GET /api/earned?wallet=...`: claimable launch IDs and unlock times.
- Explorer `GET /api/claim?launch=...&wallet=...`: wallet allocation amount and
  reward-tree evidence; a null claim means no allocation.
- Control plane `GET /launches/:id?claims=1`: frozen wallet reward allocations.
- Control plane `GET /pair/wallet/:address`: wallet-held seats and devices.

Allocations reflect accepted work and seats connected at launch admission.
Current online status alone cannot establish eligibility. Captured responses
and contract-state checks now validate the implemented routes; an allocation
leaf alone never proves it remains unclaimed and unlocked.

The [official explorer earned view](https://explorer.imd.fun/wallet/0x65fcec1f5bfa9c8d8b93bc1dba740b5977019696/earned)
also visibly distinguishes ready claims, unlock countdowns, launching records
and claimed allocations. This public example is evidence, not a default wallet.

## Verified live contracts and limits

Public captures under `tests/fixtures/portfolio/` record source URLs, capture
UTC times, chain IDs, requests and responses. Balance reads validate chain ID,
pin a block, and read `balanceOf(wallet)` and `decimals()` together. Batches
reuse the existing shared RPC transport and Ethereum/Base/Robinhood state pools.
No fallback assumes 18 decimals or turns a failed balance into zero.

The claims client uses earned launch UUIDs, `/api/claim` and launch artifacts.
It verifies the allocation Merkle proof locally and reads the distributor's
`token`, `roundCount`, `roundOf`, `claimed`, `swept` and `reserved`, plus token
decimals and distributor balance at one block. Block timestamp controls unlock.
The vendored view-only ABI comes from the verified `MerkleDistributor.sol`
additional source of [ProjectFactory on Blockscout](https://eth.blockscout.com/api/v2/smart-contracts/0xff03410d0fe5fa8f7f59f743de35e333d9857120).
Claims are all-or-nothing per round/account; partial leaf claims are unsupported.

At most 12 launches advance per claim refresh, four concurrently. A distributor
with more than eight rounds remains unavailable. Earned responses have no
verified pagination cursor; unexpected pagination/completeness metadata is
refused. This is a ready/locked allocation scan, not a full historical claimed
inventory. Previously observed allocations remain checked after disappearance
from earned enumeration. Wallet association/presence refreshes independently;
offline agents never revoke already-earned entitlement.

Live probes verified positive PRIO and SWARMLER claims for the public example
wallet, with authoritative block reads. The configured-wallet render at 149×45
checked 120 supported candidates, found no positive holdings/ready claims and
reported 171 unsupported-chain launches as incomplete coverage. These are
observations from 2026-10-10, not defaults or hardcoded expected amounts.

No verified bounded source reconciles historical acquisitions, disposals,
transfers, reward basis and historical USD prices to remaining balances.
Live rows therefore carry `held_cost_usd=None` and explicit unavailable basis.
The P/L card does not infer cost from balances, rewards or 24h price changes.

Wallet changes cancel owned tasks and invalidate wallet state immediately.
Captured wallet and generation guard every result, including A→B→A switches.
Market caches survive. Per-source timestamps survive projection; partial scans
and stale values remain qualified. The manager borrows the market provider and
closes only its owned wallet readers; SurfManager closes Portfolio before market.

## Shared semantics

- One token identity is `(chain_id, normalized token address)`, never ticker.
  Include positive wallet balances and positive ready claims, including tokens
  with zero wallet balance. Deduplicate tokens and wallet allocation leaves.
- Read actual balances and decimals for every verified catalogue token with
  bounded keyless reads. Failed reads remain unknown; discovery and balance
  coverage remain visible until complete. Unpriced holdings still get rows.
- Keep held value and claimable value separate. Price times quantity is an
  indicative market valuation, not a liquidation quote. Disclose price coverage;
  partial sums must be labelled, not presented as complete portfolio value.
- Retain wallet reward entitlement when an agent goes offline. Show current
  seat association separately; never infer or duplicate an allocation from the
  number of seats currently owned. Per-agent amounts require explicit evidence.
- Locked allocations may appear in claim detail but do not enter ready-claim
  totals. Already-claimed allocations do not enter claimable totals.
- PAIRED LP means the launch position's paired asset quantity, not assets owned
  by the wallet or guaranteed exit depth. Sum each distinct position once within
  the filtered token population. Keep IMD and ETH separate, with partial and
  unknown states; expose one-sided/withdrawn state beside relevant token detail.
- Activity initially means market activity for portfolio tokens, reusing the
  existing feed. It must not be labelled the selected wallet's transaction history.
- Use token price history for trends. Do not invent historical portfolio value,
  cost basis, or profit/loss from today's balances and token price changes.
  The owner requested an unrealized P/L hero in the mock: it uses explicitly
  synthetic remaining-position cost bases. Live P/L needs a verified cost-basis
  source and otherwise must show unavailable; claimable tokens are excluded.
- Wallet changes invalidate previous wallet balances and claims immediately;
  late results cannot repaint the new wallet. Shared market caches can survive.
- MaxPane remains read-only and keyless. Display claims and verified links;
  do not add signing, transaction construction or claim execution.

## Presentation and approved design

Hero cards first; wallet/filter context beneath them. Standard panels are
borderless, with muted uppercase titles and their established blank line.
Use theme background/surface/panel tokens, neutral values, green/red price
changes, and yellow degraded states. Address links and copy actions use shared
helpers. Required fields remain reachable through scrolling and honest
`widen`/`taller` hints, measured when the chosen Textual mockup exists.

Three ASCII alternatives were presented: full-width overview, separate holdings
and claims, and a table with a persistent selected-token inspector. The owner
selected the first. Its offline Textual preview preceded live integration: four heroes, wallet/filter context, market activity / claimable
/ movers, then the full-width portfolio table. The standalone figures remain synthetic and
visibly marked MOCK DATA. The hub uses actual wallet reads and source coverage.
Both phases rendered at 149×45 before final layout checks.
