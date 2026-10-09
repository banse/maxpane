# SWARM TOKENS design research

## Evidence and scope

The owner approved version 1, Market overview, on 2026-10-09, after requesting
"first work with mock data and propose 3 different variations in ASCII before
starting to build in textual." The chain decision is "All production chains,
with a chain filter." The approved terminal size is 149 columns × 45 rows.

The first phase was an offline design demo. Every token, price, launch time, liquidity
observation and event is synthetic and prominently labelled MOCK DATA. These
records exercise presentation and interaction; they are not API observations or
investment recommendations. The standalone demo retains these fixtures; the hub now opens the live adapter below.

## Existing building blocks

- `screens/base_terminal.py`: four metrics above a market table, trends, best
  plays and activity. Reuse the overall information hierarchy.
- `screens/surf.py` launchpad body: per-token market data, launch history and
  protocol-specific supporting detail. Keep token inspection close to the table.
- `widgets/surf/swarm_launches.py`: launch identity, chain, verdict and liquidity
  context. Its current displayed slice is twelve production and twelve other
  launches (`production` and `other` in `update_data`).
- `data/surf_swarm_client.py::fetch_launches`: requests `/launches` with
  `limit=100`. This bounded read and the display slice cannot substantiate a
  future claim that every historical token is present.
- `widgets/panels.py`, `widgets/sparkline_common.py` and shared formatting helpers
  supply established visual primitives. Widgets receive only primitives and may
  use pure analytics, never data clients.

## Metric meanings

| Field | Meaning in the demo and future contract |
|---|---|
| Tokens | Number of deployed token records matching the current filters |
| New / 24h | Matching tokens launched within the preceding 86,400 seconds |
| Volume / 24h | Sum of available USD volume values; unknown coverage disclosed |
| Paired LP | Amount and unit of the paired asset in the identified launch position |
| LP state | `two-sided`, `one-token`, `one-quote`, `withdrawn`, or `unknown` |
| Price / 24h | Per-token, equally spaced samples across the same 24h window |
| Best plays | Descriptive gainers and losers with known prices and changes; LP state stays visible |
| Activity | Synthetic events whose stable token IDs match the filtered population |

The launch position is not necessarily the token's entire market. One-sided is
a position observation, not proof that a token is untradeable or fraudulent.
Paired quantities cannot be added across different assets without conversion.
Unknown values remain `None` and render `--`; a successful zero renders zero.
Never draw a price sparkline from absent samples, volume values, or random data.
Missing history shows `--`; a supplied series with fewer than two samples shows
`new`. Sparklines express each token's path, not a common absolute price scale.

All filters operate on one token population before projections are calculated.
Sorting changes row order, not counts or ranking membership. Identity uses a
stable token ID, never ticker or row number; two chains may contain the same ticker.
The mock ID is `chain:launch`; a future live token identity must use chain plus
contract address. One-sided positions remain eligible for rankings when price
and change are known; hiding them would silently change the mover population.

## Original mock-phase boundary (superseded by live integration)

A later task must establish complete launch enumeration, canonical deployed
token/chain identities, historical market samples, source freshness, position
amounts and activity coverage. It must distinguish unsupported sources from
successful empty results. No existing bounded endpoint is certified complete by
this mock implementation. No new HTTP client, RPC calls, wallets, secrets,
transactions, subscriptions or external links are needed in this phase.

## Live integration — 2026-10-09

The owner approved the design and requested real data. The dashboard uses the
same geometry and native controls; the hub owns one retained live adapter.

- Catalogue: `api.imd.fun/launches?limit=500&before=<launchNumber>` on the existing
  SwarmClient host pool. Strict descending numeric cursors, at most three pages
  per cycle, five-minute rescan. Completion requires a valid short/empty page.
  A failed rescan retains the prior complete catalogue with an explicit state.
- Population: one valid deployed token artifact, live status, chain 1/8453/4663;
  identity is numeric chain plus normalized token address. Deduplicate by newest
  launch number. Shared launch evidence must match UUID, chain, address and
  updated timestamp. Bounded metadata/K8 reads also cover older catalogue rows.
- Market snapshots: keyless DexScreener `/tokens/v1/{network}/{addresses}`, up to
  30 tokens per batch, 120-second TTL. Match exact chain and base-token address;
  prefer the verified launch pool when known. Otherwise select the indexed pool
  with highest reported USD liquidity, breaking ties by pool ID. A selected pool
  is not a claim to aggregate every market. Price, cap and FDV stay independent.
- History/trades: keyless GeckoTerminal pool hourly OHLCV and recent trades for
  `eth`, `base` and `robinhood`. Validate base-token identity for OHLCV and trade
  direction/address for swaps. Pool IDs may be bytes32. Hourly prices occupy a
  common 24-bucket window with absent samples left blank. Trades display actual
  indexed USD notional and are deduplicated by chain/pool/source event ID.
  History TTL is 15 minutes; trades two minutes. Two detail reads per source per
  cycle and shared 2.1-second pacing limit the public API request rate.
- Launch LP: reuse SURF's original position amounts, decimals, fee and withdrawal
  facts. Ten-minute K8 freshness is independent of catalogue freshness. Stale
  evidence becomes unknown for current sidedness/paired amounts. Indexer USD
  liquidity never substitutes launch-position sidedness.
- Coverage: the catalogue and each source carry separate state/read times. An
  unindexed market is distinct from a failed read. Failed reads retain last-good
  quotes behind `~`; stale quotes do not rank or contribute to current volume.
  First-read failure renders unavailable, not zero. The 30-second screen poll
  progressively fills bounded queues; revisiting the hub preserves progress.

Live verification at 149×45 found 416 catalogue records, 115 deployed tokens,
26 indexed quote rows, and actual history/trades with partial provider coverage.
These are capture observations, not fixed totals. Market, OHLCV and trade fixtures
are committed under `tests/fixtures/swarm_tokens/market/`; catalogue fixtures have
separate provenance. Manual live checks are outside the test suite.

Scope limits: age/new counts use the launch record's `createdAt`, not a proven
onchain deployment timestamp. Activity includes those launch records and the
provider's recent trade window, not complete chain-wide activity. Older or
unsupported indexed pools may have no history. Unknown future chain IDs require
an explicit mapping before admission; no explorer or provider network is guessed.

## Paired-liquidity totals — 2026-10-10

The liquidity hero sums the current filtered tokens' paired balances by their
displayed unit: IMD then ETH. Other units are excluded and no conversion occurs.
Stale, missing or invalid balances do not enter the sum. A known incomplete sum
is a lower bound (`≥`); an entirely unknown asset sum is `--`. A complete empty
selection, or a complete selection with no balance in that unit, yields zero.
Newly Launched now shows these per-token paired amounts instead of LP state.
