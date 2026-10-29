# POOL4 website prototype

Status saved 2026-10-30: the website and hourly archive backfill are published.
Resume from [HANDOVER.md](../HANDOVER.md), which records the deployed source,
data coverage and remaining P&L/indexing work. The initial cache inventory below
is historical and was superseded by 504 archive samples per chart.

Date: 2026-10-29. Tier 2. The user requests a website before a second terminal
view, with real charts, pool/protocol P&L, and all token routes. Wallet P&L is
explicitly out of scope. Keep the existing Textual application unchanged.

## Decision

Build a small, read-only site in `sites/pool4-observatory/`: static HTML/CSS/JS,
an independently generated public JSON snapshot, and pure chart/accounting
transformations. A Python export/refresh script can reuse existing decoders and
public RPC clients without adding another long-running backend. The site may
refresh its JSON, but must not claim continuous live collection when the deployed
file is a dated snapshot.

Alternatives: browser-direct RPC refresh adds provider/CORS dependencies and makes
long event scans expensive for each visitor; a hosted indexing service gives
better continuous history but is unnecessary for the first design. Prefer the
static snapshot now and preserve its data boundary for later collection.

## Real data available now

The inspected `~/.maxpane/surf_cache.json` was saved at 2026-10-29 22:07 UTC.
Copy only allowlisted public POOL4/market facts, never the entire cache or wallet
configuration. This is an observation of local state, not a runtime constant.

| Source | Available evidence | Limit |
| --- | --- | --- |
| `series.pool4_reserve_mainnet` | 168 actual reserve observations, Oct 9–29 | Observation cadence is irregular; not hourly trading volume |
| `series.imd_price_usd` | 168 actual IMD market quotes, ending Oct 23 UTC | Separate market source; not necessarily POOL4 execution price |
| `last_good.pool4.payload.flow` | 25 timestamped swaps and associated fee/accrual legs | Capped recent feed; not an exhaustive 24-hour history |
| `last_good.pool4.payload` | Reserves, retained ETH, vault, reward routing and cumulative counters | Current values are not period revenue or P&L |
| `last_good.pool4_burn_pipeline.payload` | Independent executor queue, latest bridge and verified Base burn | Shared executor; no POOL4-only attribution or batch pairing |

Relevant implementation: `data/surf_pool4.py` decodes swaps and hook events;
`data/surf_pool4_client.py` exposes bounded logs and timestamp reads;
`data/surf_pool4_burn.py` verifies destination burn receipts;
`data/surf_pool4_market.py` computes staking return, not protocol P&L.

The existing public research reader at
`/Users/banse/.agents/skills/pool4hook-research/pool4hook.ts` supports `state`,
`swaps --list --json`, `events --all --json`, and `stakers --json`, with explicit
`--from`/`--to` blocks. Event vocabulary includes fees, withdrawal, inventory
funding, keeper tips, market close, settlement and reward routes. Its state
backstop principal must not be mistaken for current inventory value after fills.

## Accounting contract

The operating treasury boundary comprises the hook's trading position, current
buy-wall position, idle ETH/IMD and collectible fee claims, net of obligations
already allocated to burn/reward beneficiaries. Staked principal, sIMD shares,
shared executor holdings and beneficiary reserves are separate balances.

Protocol P&L in ETH is:

`closing net treasury NAV - opening net treasury NAV - owner capital added + owner capital withdrawn`

Use same-block position amounts and consistent timestamped ETH-denominated IMD
valuation. Adjust only external capital movements; swaps and internal moves are
not capital injections. Fee revenue already included in NAV must not be added
again. Burn allocations and reward distributions are outflows/obligations, not
profit. Keeper costs belong to the pool only when the pool pays them; caller gas
and caller-paid LayerZero fees are external operating context.

The current cache cannot establish this P&L: it lacks historical complete NAV,
capital-flow coverage and cost decomposition. Render P&L as unavailable with
its short reason; show authentic reserve, price, fee and flow charts alongside
it. A price return, reserve change, TVL change, cumulative fee total or negative
allocation amount must never be renamed protocol P&L. This is an explicit data
gap, not permission to generate a plausible curve.

## Minimal JSON v1

```text
schemaVersion: 1
generatedAt: ISO timestamp
identity: {hook, token, symbol, decimals, chainId}
sources: [{id, label, observedAt, coverage:{from,to,complete}, url}]
metrics: {poolImd,poolEth,buyWallEth,rewardQueueImd,settledToBurnImd,
          settledToRewardsImd,feesImd,retainedEth,sharePriceImd,vaultImd}
series: {reserve:[{t,value}], marketPriceUsd:[{t,value}]}
events: [{id,t,chainId,kind,scope,from,to,asset,amount,tx,sourceId}]
burnPipeline: {queue:{amount,observedAt},
               bridge:{amount,t,tx,complete}, baseBurn:{amount,t,tx,complete}}
pnl: {status:'unavailable'|'complete',unit:'ETH',value,series,reason}
topology: {rewardPath:'direct'|'via-distributor'|null, addresses:{...}}
```

`t` is UTC epoch seconds. Optional values are null; numeric zero requires a
successful observation. Use decimal amount strings at the export boundary;
convert to finite chart numbers only for presentation. Bind each series to its
source through stable source IDs (`reserve`, `marketPrice`, `flow`, `pipeline`).
For future complete P&L, series points retain their own coverage and valuation
provenance; do not infer missing values by interpolation.

Each event is deduplicated by chain/transaction/log index/asset leg when the raw
logs supply these facts. Cache swap rows lack full log identity; preserve their
source limitation. Their burn/reward fields represent accruals with a `settled`
flag, not timestamps of actual settlement transfers. Keep those fields as swap
details unless independent settlement events are collected.

## Complete route map

Show a topology map with units and explicit directions, separate from measured
volume. Only a measured edge gets an amount. No edge width implies volume when
coverage is incomplete.

1. Traders exchange ETH and IMD with the pool; swap fees move to a separate fee
   ledger and can be withdrawn to the configured fee recipient.
2. Excess inventory is trimmed into burn/reward claims; settlement transfers IMD
   to the executor/reward recipient and releases ETH to the buy-wall balance.
3. Idle ETH enters the buy-wall position; fills exchange ETH for IMD; rebalance
   closes/redeploys the position and routes acquired IMD through the same split.
   Keeper tips are a separate ETH edge.
4. Rewards follow the observed configuration. With a distributor: staking to
   dripper, bonding/node allocations booked as held reserves. With a direct
   route: rewards go to the actual direct recipient. Do not imply inactive
   bonding/node payout programs are paying users.
5. Dripper transfers rewards to sIMD vault and may pay its caller an IMD tip.
   Depositors send IMD and receive minted sIMD; withdrawal burns sIMD and returns
   IMD. Share mint/burn is distinct from IMD supply mint/burn.
6. Executor bridges burn-bound IMD to Base. Base receiver burns only upon
   independently verified receiver/token receipt evidence. Shared histories do
   not establish a one-to-one bridge/burn match or POOL4-only totals.
7. Owner funding, fee withdrawals, permitted rescue/retained withdrawals and
   market close form explicit boundary routes when observed. Caller-paid gas and
   LayerZero fees are labelled external costs.

## Work packages and ownership

| Package | Owner and files | Depends on | Acceptance |
| --- | --- | --- | --- |
| WP0: contract and plan | Root / this document | None | Freeze JSON v1 and P&L semantics |
| WP1: public data export | Data implementer: `sites/pool4-observatory/scripts/`, `tests/`, `dist/data/` | WP0 | Real dated snapshot; no full-cache copying; meaningful offline tests |
| WP2: website | UI implementer: `sites/pool4-observatory/dist/index.html`, `styles.css`, `app.js`, UI-only modules | WP0 | Responsive charts, hover/keyboard details, timeframe controls, topology interaction, P&L gap |
| WP3: integrate and verify | Root: site config, README, integration glue | WP1 + WP2 | Real snapshot renders; timezone/coverage clear; desktop and mobile inspection; checks pass |
| WP4: final focused review | Reviewer, no fixes | WP3 | One review of accounting, data provenance and visible behaviour; root fixes material findings |

WP1 and WP2 may run concurrently after WP0; they own disjoint files. Root owns
hosting/registration and integration. No worker changes TUI contracts or shared
modules. No production changes, dependencies or assets outside the site need to
be touched for this prototype.

## Verification

Write failing tests for export filtering and scope, missing/zero distinction,
timestamp ordering, cached accrual versus transfer classification, and refusal
to fabricate P&L. Test time-range filtering and aggregation with representative
events rather than snapshots of implementation strings. No test uses network.

Inspect actual rendering at desktop and narrow mobile widths. Exercise timeline
selection, chart hover/focus, topology branch selection, range changes, empty
periods and partial coverage. Confirm data/source detail remains accessible and
all transaction links point to the correct chain. Snapshot age stays visible.

Follow-up: complete adjusted-NAV reconstruction and ongoing indexing are a later
data implementation, not a fake number in the first website.
