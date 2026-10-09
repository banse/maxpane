# SWARM TOKENS design research

## Evidence and scope

The owner approved version 1, Market overview, on 2026-10-09, after requesting
"first work with mock data and propose 3 different variations in ASCII before
starting to build in textual." The chain decision is "All production chains,
with a chain filter." The approved terminal size is 149 columns × 45 rows.

This phase is an offline design demo. Every token, price, launch time, liquidity
observation and event is synthetic and prominently labelled MOCK DATA. These
records exercise presentation and interaction; they are not API observations or
investment recommendations. The existing SURFBOARD hub's SWARM TOKENS card opens
the demo; live source integration remains future work.

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

## Deferred live integration

A later task must establish complete launch enumeration, canonical deployed
token/chain identities, historical market samples, source freshness, position
amounts and activity coverage. It must distinguish unsupported sources from
successful empty results. No existing bounded endpoint is certified complete by
this mock implementation. No new HTTP client, RPC calls, wallets, secrets,
transactions, subscriptions or external links are needed in this phase.
