# PORTFOLIO dashboard — design research

Date: 2026-10-10. Status: the owner selected ASCII option 1, Portfolio overview.
The offline Textual mockup is approved; live wallet integration remains future
work. Scope and work packages are in `portfolio_PRD.md` and
`portfolio_implementation_plan.md`.

## Requested outcome

Open PORTFOLIO from the SURFBOARD hub, set a wallet using THE LIST's existing
flow, and see swarm-launched tokens held by that wallet plus tokens claimable
through its IMD agents. Reuse BASE TRADING widgets and SWARM TOKENS fetching,
enrichment and liquidity presentation. Follow native MaxPane styling and KISS.

The initial design target is the previous SURFBOARD/SWARM TOKENS target,
149 columns by 45 rows. This is a design assumption, not a measured layout pin.

## Repository evidence and reuse

- `screens/wallet_input.py::WalletInputScreen` and
  `screens/curator.py::action_set_wallet/_wallet_entered`: validated address
  input, persistence, immediate wallet identity repaint and wallet-scoped refresh.
  `config.py::get_wallet` currently prioritizes MAXPANE_WALLET over saved config;
  Portfolio must define the effective wallet consistently when it is changed.
- `screens/surfboard.py` and `widgets/surfboard/rack.py`: PORTFOLIO already has a
  planned hub card. Activate that destination rather than add another top-level
  dashboard entry.
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

The market dashboard's token projection currently admits only `live` launches
on chains 1, 8453 and 4663. Portfolio completeness needs the paginated catalogue
and verified deployed identities, not the bounded LAUNCHES display. Audit
status filtering so a verified deployed token still held by the wallet cannot
disappear solely because its launch status changed. Declare unsupported chains.

## Current external evidence

The [official IMD documentation](https://imd.fun/docs/) was checked this session.
It documents these public reads:

- Explorer `GET /api/earned?wallet=...`: claimable launch IDs and unlock times.
- Explorer `GET /api/claim?launch=...&wallet=...`: wallet allocation amount and
  reward-tree evidence; a null claim means no allocation.
- Control plane `GET /launches/:id?claims=1`: frozen wallet reward allocations.
- Control plane `GET /pair/wallet/:address`: wallet-held seats and devices.

Allocations reflect accepted work and seats connected at launch admission.
Current online status alone cannot establish eligibility. These documented
routes need captured payloads and contract-state checks before live integration;
an allocation leaf alone does not prove it remains unclaimed and unlocked.

The [official explorer earned view](https://explorer.imd.fun/wallet/0x65fcec1f5bfa9c8d8b93bc1dba740b5977019696/earned)
also visibly distinguishes ready claims, unlock countdowns, launching records
and claimed allocations. This public example is evidence, not a default wallet.

## Proposed shared semantics

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

## Presentation and next design step

Hero cards first; wallet/filter context beneath them. Standard panels are
borderless, with muted uppercase titles and their established blank line.
Use theme background/surface/panel tokens, neutral values, green/red price
changes, and yellow degraded states. Address links and copy actions use shared
helpers. Required fields remain reachable through scrolling and honest
`widen`/`taller` hints, measured when the chosen Textual mockup exists.

Three ASCII alternatives were presented: full-width overview, separate holdings
and claims, and a table with a persistent selected-token inspector. The owner
selected the first. Build its offline Textual preview before connecting live
portfolio reads: four heroes, wallet/filter context, market activity / claimable
/ movers, then the full-width portfolio table. All figures remain synthetic and
visibly marked MOCK DATA. Show the actual 149×45 mock render before hardening;
the explicit mock-first workflow replaces the live-render step for this phase.
