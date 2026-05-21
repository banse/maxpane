# Ten Thousand Tokens (TTT) Dashboard — Design Spec

**Date:** 2026-05-21
**Status:** Approved
**Framing:** Launch Pulse — balanced overview of NFT-side state and the 100+ launched ERC20 markets.

## Summary

A single-screen dashboard for Ten Thousand Tokens (TTT), an Ethereum-mainnet NFT collection by TokenWorks where each of 10,000 NFTs can be burned to launch a paired ERC20 via a shared Uniswap V4 hook. The dashboard surfaces protocol-wide state (un-burned count, holder pool, floor) alongside live token-market data (top tokens by 24h volume, fees flowing into the holder pool, buyback bounty opportunities, and the unique decay-tax window on fresh launches). Reuses the MaxPane template layout; runs entirely with **no API keys** (public RPC + DexScreener + Reservoir keyless).

## Scope Decisions (resolved during brainstorm)

- **Point of view**: Balanced overview — both NFT-side and ERC20 markets.
- **Wallet mode**: None in v1 — overview-only, like Base/DOTA. Wallet view is a future addition.
- **Framing**: "Launch Pulse" (template-faithful) rather than fee-engine-only or trader-only.
- **No API keys**: Public mainnet RPC + DexScreener + Reservoir keyless. Per the [[feedback-no-api-keys]] memory.
- **Bottom-right widget**: Hybrid α + γ toggle — *Top Fee Engines (24h)* by default, switchable to *Holder Claim Math* via `c` key.

## Layout & Widget Mapping

Same skeleton as all other MaxPane dashboards (title bar → hero row → middle row → activity row → status bar).

| Template Widget | TTT Use | Data Source |
|---|---|---|
| Title bar | `Ten Thousand Tokens · Ethereum Mainnet · <launches>/10,000` | RPC `burnCount()` |
| Hero cards (4) | Unburned NFTs · Launches (24h / total) · Holder Pool ETH · NFT Floor (ETH/USD) | RPC + Reservoir |
| Leaderboard (left mid) | Top 10 launched tokens by 24h USD volume | DexScreener batch |
| Sparkline (right mid) | Cumulative burns + NFT floor, 7d hourly buckets | Local snapshot + Reservoir |
| Signals panel (right mid, below sparkline) | Fresh-launch alert, buyback-ready count, decay-window count, concentration ratio | Derived |
| Activity feed (bottom left) | Last 25 protocol events (BURN / SWAP / FEE / BBACK / SALE) | RPC event logs + Reservoir sales |
| Two-column table (bottom right) | **Toggle:** α Top Fee Engines (24h) / γ Holder Claim Math scenarios | RPC `Deposit` events / derived |
| Status bar | Standard last-update / errors / poll interval / active view (Fees/Claims) | Existing widget |

## Data Sources (all keyless)

Per refresh cycle (~30s):

| Data | Source | Endpoint | TTL |
|---|---|---|---|
| `burnCount`, `accETHPerShare`, factory state | Public Ethereum RPC | `https://eth.llamarpc.com` (primary), `https://ethereum.publicnode.com`, `https://cloudflare-eth.com` (fallback) | 15s |
| Batched on-chain reads | Multicall3 | `0xcA11bde05977b3631167028862bE2a173976CA11` | n/a |
| `BurnAndLaunch` / `Deposit` / `Buyback` events | Same RPC, `eth_getLogs` | incremental from last-seen block | n/a (persisted) |
| Launched-token price / vol / mcap | DexScreener public API | `GET /tokens/v1/ethereum/<addrs>` (≤30 per call) | 30s |
| NFT floor + 24h sales | Reservoir keyless | `GET https://api.reservoir.tools/collections/v7?contract=0x26d7…fb2e` | 60s |
| ETH/USD | Existing `price.py` (CoinGecko keyless) | — | 60s |

**No API keys.** No Alchemy / Infura / OpenSea / Reservoir-keyed / Etherscan-keyed endpoints. Public RPCs are rate-limited, so we Multicall3-batch every block-state read and persist event logs incrementally to `data/snapshot.py`-style local storage.

## Hero Cards (top row)

Four tiles, left to right:

1. **UNBURNED** — `10,000 − burnCount` with `(<percent>%)` subtitle. RPC. Updates every cycle.
2. **LAUNCHES** — `<burnCount>` total, with `+<N> 24h` subtitle counted from `BurnAndLaunch` events in the last 24h.
3. **HOLDER POOL** — Cumulative ETH paid into the 30% holder bucket all-time, with `+<X> Ξ 24h` subtitle. From sum of `Deposit` events (multiplied by 0.30 if the deposit topic carries gross, or read directly from a holder-bucket-specific event if available).
4. **FLOOR** — NFT floor in ETH with USD subtitle. Reservoir; falls back to `—` if Reservoir unavailable.

## Leaderboard — Top Tokens (24h Volume)

DataTable, 10 rows. Columns:

| # | SYM | PRICE | 24h% | VOL (USD) | AGE | MCAP |
|---|---|---|---|---|---|---|

- Token list discovered from `BurnAndLaunch` events; symbol + decimals cached once per token.
- 24h%, vol, mcap, price from DexScreener; sorted by `volume.h24` desc.
- `AGE` = blocks since launch, formatted as `<m>m` / `<h>h` / `<d>d`.
- Bold row 1. Top 10 only.

## Sparkline — Burns & Floor (7-day)

Two overlaid series on shared time axis (hourly buckets, 168 points):

- **Burns** (e.g. orange) — cumulative `burnCount` per hour. Lifetime-from-deploy series, persisted locally so we don't rescan logs every refresh.
- **Floor** (e.g. cyan) — Reservoir floor snapshot taken each refresh, persisted same way.

If Reservoir is unavailable for a refresh, the floor line gaps but burns continues — same defensive pattern as Base/DOTA when an API hiccups.

## Signals Panel (right mid)

Four lines (some conditional):

1. **🔥 NEW LAUNCH** — Shown only if a `BurnAndLaunch` event fired in the last 10 minutes. Format: `🔥 NEW: <SYM> launched <Nm> ago — <buy tax>% buy tax`. Disappears after 10 min.
2. **Buybacks ready** — `► <N> buybacks ready (Σ <X> Ξ bounty)`. Count of launched tokens with reservoir ≥ 0.1 Ξ; bounty sum across them.
3. **Decay window** — `► <N> tokens in decay window (>1% buy tax)`. Count of tokens with `currentBlock − launchBlock < 98`.
4. **Holder concentration** — `► Each NFT now claims 1/<unburned> of every fee deposit (≈ <X> Ξ/deposit at current rate)`.

## Activity Feed (bottom left)

RichLog, last 25 events, descending by block. Heterogeneous event types from RPC logs:

```
22:14  BURN   TFT     by 0x12ab…  tokenId 4271
22:13  SWAP   ONE     +0.14 Ξ     tax 1%
22:12  FEE    BURN    0.02 Ξ → holders
22:10  BBACK  STR     0.005 Ξ bounty paid
22:08  SALE   TTT     #2102  0.0498 Ξ  on OpenSea
```

- **BURN**: from `BurnAndLaunch`. Shows the new token's symbol + tokenId + deployer.
- **SWAP**: from per-pool Swap events, filtered to ≥ 0.05 Ξ size (to avoid spam). Shows direction (+/− Ξ) and current buy tax %.
- **FEE**: from FeeSplitter `Deposit` events. Shows source token + 30%-bucket amount.
- **BBACK**: from per-token `Buyback` events. Shows token + bounty paid.
- **SALE**: from Reservoir's sales endpoint (optional; only if Reservoir returns it cheaply).

## Bottom-Right Toggle: Fee Engines ⇄ Claim Math

Single widget, two views. Keybinding `c` toggles.

### α — Top Fee Engines (24h) — default view

DataTable, top 10 rows. Columns:

| # | SYM | 24h FEES (Ξ) | LIFETIME FEES (Ξ) | 24h FEES / VOL |
|---|---|---|---|---|

- Sourced from FeeSplitter `Deposit` events grouped by token address.
- `24h FEES / VOL` is the effective fee rate — tokens still in decay window show high values (10–50%), mature tokens show ~1%.
- Sort by 24h fees descending.

### γ — Holder Claim Math — toggle view

Static scenario table, 6 rows:

| Scenario | Unburned | Per-NFT share / deposit | Projected per-NFT claim |
|---|---|---|---|
| Today | `<unburned>` | `0.30 / <unburned>` | `<accETHPerShare> × adjusted` |
| 25% burned | 7,500 | 0.0040% | `<projection>` |
| 50% burned | 5,000 | 0.0060% | `<projection>` |
| 75% burned | 2,500 | 0.0120% | `<projection>` |
| 90% burned | 1,000 | 0.0300% | `<projection>` |
| Sole survivor | 1 | 30.0000% | `<projection>` |

Projections extrapolate from current 24h `Deposit` accrual rate × concentration multiplier (not a price forecast — an *if-current-volume-holds* arithmetic projection).

Status bar shows the active view label (`Fees` / `Claims`).

## Refresh & Caching

- Default poll: **30s** (matches OCM/Base).
- Per-source TTLs: RPC reads 15s · DexScreener 30s · Reservoir 60s · CoinGecko ETH/USD 60s.
- Multicall3 collapses NFT-state reads (`burnCount`, `accETHPerShare`, every-token `reservoir()`) into one RPC call per cycle.
- Event-log queries are **incremental**: persist `lastSeenBlock` per topic, scan `lastSeenBlock → latest` only.
- Local snapshot persistence (`ttt_cache.py`) survives restarts so the sparkline and activity feed aren't blank for ~30s on each launch.

## Error Handling

Reuse OCM's pattern. Each fetcher returns `T | None`; `manager.fetch_and_compute()` swaps in last-known-good and increments the error counter shown in the status bar. No single source's failure breaks the screen:

- RPC down → primary swaps to fallback RPC; if all three fail, on-chain widgets show stale values with a dimmed indicator.
- DexScreener down → leaderboard + fee-engine table show last-known values.
- Reservoir down → floor tile shows `—`, floor sparkline series gaps.
- ETH/USD down → USD subtitles show `—`.

## Implementation Approach

### New files to create

- `maxpane_dashboard/data/ttt_client.py` — HTTP/RPC adapters: `fetch_factory_state()`, `fetch_launched_tokens()`, `fetch_token_markets()`, `fetch_nft_floor()`, `fetch_recent_events()`, `fetch_buyback_reservoirs()`
- `maxpane_dashboard/data/ttt_models.py` — Pydantic models: `TTTFactoryState`, `TTTLaunchedToken`, `TTTMarketData`, `TTTFeeDeposit`, `TTTBurnEvent`, `TTTBuybackEvent`, `TTTNFTFloor`, `TTTSnapshot`
- `maxpane_dashboard/data/ttt_cache.py` — Incremental event log persistence, sparkline series storage, floor history
- `maxpane_dashboard/data/ttt_manager.py` — Orchestrator: fetch from all sources, cache, call signal module, return flat dict for screen
- `maxpane_dashboard/analytics/ttt_signals.py` — `decay_tax_pct(block_age)`, `holder_concentration(unburned)`, `buybacks_ready(reservoirs)`, `fresh_launch_alert(events)`, `claim_math_scenarios(state, deposits)`
- `maxpane_dashboard/abis/` — Minimal ABI JSONs for: NFT factory (subset: `burnCount`, `MAX_SUPPLY`, `BurnAndLaunch` event), FeeSplitter (`Deposit` event, `accETHPerShare`), per-token ERC20 (`reservoir`, `Buyback` event), Multicall3
- `maxpane_dashboard/widgets/ttt/__init__.py` — exports
- `maxpane_dashboard/widgets/ttt/ttt_hero_metrics.py` — 4 hero tiles
- `maxpane_dashboard/widgets/ttt/ttt_leaderboard.py` — Top tokens by vol
- `maxpane_dashboard/widgets/ttt/ttt_sparkline.py` — Burns + floor overlay
- `maxpane_dashboard/widgets/ttt/ttt_signals.py` — 4-line signals panel
- `maxpane_dashboard/widgets/ttt/ttt_activity_feed.py` — Heterogeneous event stream
- `maxpane_dashboard/widgets/ttt/ttt_fees_table.py` — α view (Top Fee Engines)
- `maxpane_dashboard/widgets/ttt/ttt_claims_table.py` — γ view (Claim Math)
- `maxpane_dashboard/screens/ttt.py` — Single-view screen with `c` toggle binding

### Files to modify

- `maxpane_dashboard/app.py` — Register `TTTManager`, install `TTTScreen`, add to game cycle
- `maxpane_dashboard/screens/game_select.py` — Add TTT as the next option (7)
- `maxpane_dashboard/themes/minimal.tcss` — CSS rules for `ttt-` widgets (reuse Base/DOTA-style neon-trading color palette)

### Tests

Mirror existing pattern (~30 tests total):

- `tests/data/test_ttt_client.py` — Response-shape contracts with vcr-style fixtures for DexScreener, Reservoir, and RPC eth_call/eth_getLogs.
- `tests/analytics/test_ttt_signals.py` — Decay-tax math at each block boundary, concentration math at 0/50/9000/9999 burns, fresh-launch alert window, buyback-ready threshold, claim-math projections.
- `tests/screens/test_ttt_screen.py` — Textual `Pilot` test: layout renders, `c` toggles bottom-right view, all widgets receive data from a mocked manager, no widget crashes on empty/None inputs.

### Naming Convention

Widget IDs and CSS classes use `ttt-` prefix. Widget Python classes use `TTT` prefix. Cache namespace key: `ttt`. Data manager: `TTTManager`. Screen: `TTTScreen`.

## Keybindings

- `r` — refresh now (standard)
- `c` — toggle Fee Engines ⇄ Claim Math in the bottom-right widget
- `t` — jump to TTT screen from `game_select` (if the letter is unused; otherwise reassign)

## Future Work (out of v1 scope)

- **Wallet-aware view** — second screen accepting a wallet address; shows owned NFTs (with on-chain SVG art), per-NFT claim, deployed tokens, total ETH earned.
- **Per-token detail screen** — drill-in from leaderboard row to a single token's pool: price chart, buy-tax timer, swap firehose, reservoir position.
- **Sales/floor history derived on-chain** — replace Reservoir dependency with direct Seaport event scraping.
- **TTT-specific theme** — bespoke color palette inspired by the on-chain SVG art (black field + orbital rings + glyph accents).
