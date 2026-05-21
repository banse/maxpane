# Ten Thousand Tokens (TTT) Dashboard -- Implementation Plan

**Date:** 2026-05-21
**Design spec:** `docs/superpowers/specs/2026-05-21-tenthousandtokens-dashboard-design.md`
**Research:** `docs/tenthousandtokens_game_mechanics.md`, `docs/tenthousandtokens_technical_findings.md`
**Status:** Ready for implementation

## Overview

Seven work packages (WP0-WP6) broken into parallel tracks. WP0 (ABI verification & contract reconnaissance) must run first because every other package depends on the exact event signatures and storage slots in the verified source. WP1 (models) and WP2 (analytics) start in parallel once WP0 lands. WP3 (data layer) depends on WP1. WP4 (widgets) and WP5 (screen + integration) depend on WP3. WP6 (tests) starts alongside WP2 and finalizes after WP3.

## Dependency Graph

```
WP0 (ABI recon) ─┬──> WP1 (Models) ─────┐
                  │                       ├──> WP3 (Data Layer) ──> WP5 (Screen + Integration)
                  └──> WP2 (Analytics) ──┤                      └──> WP4 (Widgets)
                                          │
                          WP6 (Tests) ────┘ (starts with WP2, finishes after WP3)
```

**Parallel tracks:**
- Track A: WP0 -> WP1 -> WP3 -> WP5
- Track B: WP0 -> WP2 (independent, parallel with WP1)
- Track C: WP4 (parallel with WP5; needs WP3 done)
- Track D: WP6 (starts with WP2, finishes after WP3)

---

## WP0: ABI Reconnaissance & Contract Map

**Agent:** Backend Architect
**Depends on:** Nothing (start immediately)
**Estimated scope:** Small (~60 lines of ABI JSON + 1 markdown reconnaissance note)

### Goal

Fetch verified source for the master contract `0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e` from Etherscan (public endpoint, no key required for the source view), identify the supporting contracts (FeeSplitter, TTTHook, per-token ERC20 template), and write minimal ABI JSONs containing only the reads and events the dashboard needs. This eliminates the "selector unknown" risk that the OCM dashboard hit (see `maxpane_dashboard/data/ocm_client.py:60-66` -- the OCM team had to verify selectors by keccak after the fact; for TTT we do it up front).

### Files to create

- `maxpane_dashboard/abis/ttt_factory.json` -- minimal ABI for the NFT/launcher master contract
- `maxpane_dashboard/abis/ttt_fee_splitter.json` -- minimal ABI for the FeeSplitter
- `maxpane_dashboard/abis/ttt_erc20.json` -- minimal ABI for the per-launched-token ERC20 (the shared template)
- `maxpane_dashboard/abis/multicall3.json` -- Multicall3 `aggregate3` ABI (standard, paste from https://github.com/mds1/multicall)
- `docs/tenthousandtokens_abi_recon.md` -- reconnaissance note: which address corresponds to FeeSplitter, which method names map to which concepts in the whitepaper, anything that differs from the whitepaper's vocabulary

### How to recon

1. Visit `https://etherscan.io/address/0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e#code` and read verified source.
2. From the constructor or known state-getters, locate the FeeSplitter, TTTHook, and renderer addresses.
3. For each launched token, click into one of the child ERC20 addresses (e.g. via the Token Tracker page) and confirm the per-token ABI is identical (shared template).
4. Identify the exact event signature and method names for:
   - NFT factory: `MAX_SUPPLY`, `burnCount` (or `totalBurned`), `totalMinted`, `BurnAndLaunch` event (parameters: tokenId, erc20 address, deployer, ?launch block)
   - FeeSplitter: cumulative ETH-paid-to-holders accessor (likely `accETHPerShare` or `totalDistributedToHolders`), `Deposit` event (token source, gross or net amount)
   - Per-token ERC20: buyback reservoir read (likely `reservoir()` or `pendingReservoir()`), `Buyback` event (caller, ethSpent, tokensBought)
5. Write each ABI as a JSON array of method/event entries, **only including what the dashboard needs**. Do NOT include the full ABI.

### Output format example (`ttt_factory.json`)

```json
[
  {
    "inputs": [],
    "name": "MAX_SUPPLY",
    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [],
    "name": "burnCount",
    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "anonymous": false,
    "inputs": [
      {"indexed": true,  "internalType": "uint256", "name": "tokenId",  "type": "uint256"},
      {"indexed": true,  "internalType": "address", "name": "erc20",    "type": "address"},
      {"indexed": true,  "internalType": "address", "name": "deployer", "type": "address"},
      {"indexed": false, "internalType": "uint256", "name": "launchBlock", "type": "uint256"}
    ],
    "name": "BurnAndLaunch",
    "type": "event"
  }
]
```

### Output format example (`docs/tenthousandtokens_abi_recon.md`)

```markdown
# TTT ABI Reconnaissance

## Contract addresses
- NFT factory / launcher: 0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e
- FeeSplitter:            0x<TBD-from-recon>
- TTTHook (V4):           0x<TBD-from-recon>
- Renderer:               0x<TBD-from-recon>
- GlobalDistributorHandler: 0x<TBD-from-recon>

## Method/event name map (whitepaper -> actual)
| Whitepaper term            | Actual method/event                | Notes |
|----------------------------|------------------------------------|-------|
| burn count                 | `burnCount()`                      | uint256, view |
| holder pool accETHPerShare | `accETHPerShare()` or `<actual>`   |       |
| BurnAndLaunch event        | `BurnAndLaunch(uint256,address,address,uint256)` |  |
| FeeSplitter Deposit event  | `Deposit(address indexed token, uint256 amount)` |  |
| Buyback event              | `Buyback(address caller, uint256 ethSpent, uint256 tokensBought)` |  |
| Buyback reservoir read     | `reservoir()` or `<actual>`        |       |

## Topic hashes (keccak256 of event signatures)
- BurnAndLaunch: 0x<computed>
- Deposit:       0x<computed>
- Buyback:       0x<computed>

## Surprises / deviations from whitepaper
- ...
```

### Validation

- All 4 ABI files parse as valid JSON.
- All event topic hashes recomputed locally (e.g. `web3.keccak(text="BurnAndLaunch(uint256,address,address,uint256)").hex()`) match what is in the recon note.
- Recon note has no `<TBD>` placeholders left.

### Notes

- Etherscan source view does NOT require an API key. The recon note must record the actual exact names; downstream code reads from these.
- If the source is split across multiple files (Solidity multi-file verification), follow the import graph to the relevant contracts.

---

## WP1: Pydantic Models

**Agent:** Backend Architect
**Depends on:** WP0 (ABI recon must finalize event field names)
**Estimated scope:** Small (~140 lines)

### Files to create

- `maxpane_dashboard/data/ttt_models.py`

### What to implement

Frozen Pydantic models matching the dashboard's internal data shapes. Follow the pattern in `maxpane_dashboard/data/ocm_models.py` -- all models use `ConfigDict(frozen=True)`.

**Models to define:**

```python
"""Pydantic models for Ten Thousand Tokens dashboard data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_WEI = 10**18
_ETH_PER_LAUNCH = 10.0   # whitepaper-hardcoded initial pool value


class TTTFactoryState(BaseModel):
    """NFT factory state read in one multicall."""

    model_config = ConfigDict(frozen=True)

    max_supply: int            # constant 10_000
    burn_count: int
    total_minted: int          # 10_000 once mint closed (already true in May 2026)
    unburned: int              # max_supply - burn_count
    burned_pct: float          # burn_count / max_supply * 100
    acc_eth_per_share: int     # raw FeeSplitter cumulative, SCALE-fixed (uint256)
    total_eth_to_holders_wei: int   # cumulative 30%-bucket ETH all-time, wei
    current_block: int


class TTTLaunchedToken(BaseModel):
    """One ERC20 launched from a burned NFT."""

    model_config = ConfigDict(frozen=True)

    token_id: int              # source NFT id
    address: str               # ERC20 contract address, lowercased 0x...
    deployer: str              # ETH address of burner
    launch_block: int
    symbol: str | None         # discovered once per token, cached
    decimals: int              # default 18
    # Market data from DexScreener (None if unavailable)
    price_usd: float | None = None
    price_change_h24: float | None = None
    volume_usd_h24: float | None = None
    market_cap_usd: float | None = None
    # On-chain
    reservoir_wei: int = 0     # ETH waiting to be buyback-drawn
    # Fee history (aggregated locally from Deposit events)
    fees_eth_24h: float = 0.0
    fees_eth_lifetime: float = 0.0


class TTTNFTFloor(BaseModel):
    """NFT collection floor + 24h sales from Reservoir."""

    model_config = ConfigDict(frozen=True)

    floor_eth: float | None
    floor_usd: float | None
    sales_24h: int | None


class TTTActivityEvent(BaseModel):
    """Single event for the activity feed."""

    model_config = ConfigDict(frozen=True)

    tx_hash: str
    block_number: int
    timestamp: int             # unix seconds
    event_type: str            # "burn", "swap", "fee", "buyback", "sale"
    token_symbol: str | None
    token_address: str | None  # for swap/fee/buyback
    actor_address: str | None  # deployer / swap-sender / buyback-caller / buyer
    eth_amount_wei: int        # signed for swaps (+ buy, - sell), unsigned otherwise
    token_id: int | None       # for burn / sale
    extra: dict | None = None  # tax pct, bounty amount, etc.


class TTTSignal(BaseModel):
    """One row of the Signals panel."""

    model_config = ConfigDict(frozen=True)

    label: str
    value_str: str
    indicator: str             # colored dot (e.g. "●" or "🔥")
    color: str                 # "green" / "yellow" / "red" / "dim"


class TTTSnapshot(BaseModel):
    """Top-level container for one TTT poll cycle."""

    model_config = ConfigDict(frozen=True)

    fetched_at: float
    factory: TTTFactoryState | None
    floor: TTTNFTFloor | None
    eth_usd: float | None
    launched_tokens: list[TTTLaunchedToken]
    recent_events: list[TTTActivityEvent]
    # signals
    fresh_launch_signal: TTTSignal | None  # None if no launch in last 10 min
    buybacks_ready_signal: TTTSignal
    decay_window_signal: TTTSignal
    concentration_signal: TTTSignal
    # 24h derived counters
    launches_24h: int
    eth_to_holders_24h: float
```

### Reference

- Pattern: `maxpane_dashboard/data/ocm_models.py`
- Snapshot pattern: `maxpane_dashboard/data/dota_models.py:104` (DOTASnapshot)

### Notes

- The `acc_eth_per_share` field is stored as raw uint256 (no float conversion at model layer). The SCALE constant (probably `1e18` or `1e30`) is applied in analytics. WP0 must record the SCALE value used by the contract.
- `eth_amount_wei` for swaps is signed: positive = ETH spent by buyer (a buy), negative = ETH received by seller (a sell). Activity feed renders accordingly.
- `extra` is a free-form dict for type-specific fields: `{"tax_pct": 47.0}` on swaps, `{"bounty_wei": 12345}` on buyback, `{"price_eth": 0.0498}` on sales.

---

## WP2: Signal Analytics

**Agent:** Backend Architect
**Depends on:** WP0 (only to know the SCALE constant for `accETHPerShare`)
**Estimated scope:** Small (~200 lines)

### Files to create

- `maxpane_dashboard/analytics/ttt_signals.py`

### What to implement

Pure functions that take raw state and return `TTTSignal` instances (or scalar derived values). Follow the pattern in `maxpane_dashboard/analytics/ocm_signals.py`.

**Constants:**

```python
DECAY_BLOCKS = 98              # whitepaper: 99% -> 1% over 98 blocks
BUY_TAX_START_PCT = 99
BUY_TAX_FLOOR_PCT = 1
SELL_TAX_PCT = 1
HOLDER_FEE_SHARE = 0.30
DEPLOYER_FEE_SHARE = 0.50
PROTOCOL_FEE_SHARE = 0.10      # TokenWorks
PUNKSTRATEGY_FEE_SHARE = 0.10
BUYBACK_BOUNTY_FRAC = 0.005    # 0.5%
BUYBACK_MAX_DRAW_WEI = 10**18  # 1 ETH per block
FRESH_LAUNCH_WINDOW_SEC = 600  # 10 minutes
BUYBACK_READY_THRESHOLD_WEI = 10**17  # 0.1 ETH -- worth surfacing
MAX_NFTS = 10_000
```

**Functions:**

1. `decay_tax_pct(blocks_since_launch: int) -> int`
   ```python
   def decay_tax_pct(blocks_since_launch: int) -> int:
       """Returns current buy-tax percent for a token N blocks past launch."""
       return max(BUY_TAX_START_PCT - blocks_since_launch, BUY_TAX_FLOOR_PCT)
   ```
   - Block 0: 99; Block 50: 49; Block 98+: 1.

2. `per_nft_share(unburned: int) -> float`
   ```python
   def per_nft_share(unburned: int) -> float:
       """Fraction of each Deposit event accruing to one un-burned NFT."""
       if unburned <= 0:
           return 0.0
       return HOLDER_FEE_SHARE / unburned
   ```

3. `concentration_multiplier(unburned: int) -> float`
   - Returns `per_nft_share(unburned) / per_nft_share(MAX_NFTS)` -- "you now claim Nx what a day-1 holder claimed".

4. `count_buybacks_ready(tokens: list[TTTLaunchedToken]) -> tuple[int, int]`
   - Returns (count, total_bounty_wei). Tokens count if `reservoir_wei >= BUYBACK_READY_THRESHOLD_WEI`. Bounty = `0.005 * min(reservoir, 1 ETH)`.

5. `count_decay_window(tokens: list[TTTLaunchedToken], current_block: int) -> int`
   - Tokens with `current_block - launch_block < DECAY_BLOCKS`.

6. `fresh_launch_alert(recent_events: list[TTTActivityEvent], current_block: int, now_ts: float) -> TTTSignal | None`
   - Find most recent `event_type == "burn"` within `FRESH_LAUNCH_WINDOW_SEC`.
   - If found, format: `f"NEW: {symbol} launched {mins}m ago — {tax_pct}% buy tax"`
   - Tax pct via `decay_tax_pct(current_block - launch_block)`
   - Indicator `"🔥"`, color `"yellow"`.
   - Returns None otherwise.

7. `buybacks_ready_signal(tokens: list[TTTLaunchedToken]) -> TTTSignal`
   - From `count_buybacks_ready`. Format: `f"{count} buybacks ready (Σ {bounty_eth:.4f} Ξ bounty)"`.
   - Indicator `"►"`, color `"green"` if count > 0 else `"dim"`.

8. `decay_window_signal(tokens, current_block) -> TTTSignal`
   - Format: `f"{count} tokens in decay window (>1% buy tax)"`.
   - Indicator `"►"`, color `"yellow"` if count > 0 else `"dim"`.

9. `concentration_signal(state: TTTFactoryState, eth_to_holders_24h: float) -> TTTSignal`
   - Per-NFT share = `0.30 / unburned`.
   - Per-NFT 24h projection = `eth_to_holders_24h / unburned`.
   - Format: `f"Each NFT claims 1/{unburned:,} of pool — ≈{per_nft_24h:.5f} Ξ/day at current rate"`.
   - Indicator `"►"`, color `"green"`.

10. `claim_math_scenarios(state: TTTFactoryState, eth_to_holders_24h: float) -> list[dict]`
    - Returns rows for the γ-view scenario table. Each row:
      ```python
      {"scenario": "Today", "unburned": <int>, "share_pct": <float>, "projected_24h_eth": <float>, "multiplier_vs_today": 1.0}
      ```
    - Scenarios: Today, 25% burned (7500 unburned), 50% (5000), 75% (2500), 90% (1000), Sole survivor (1).
    - Projection assumes 24h ETH flow stays constant; per-NFT amount = `eth_to_holders_24h / unburned_scenario`.
    - `multiplier_vs_today` = scenario_per_nft / today_per_nft.

11. `top_fee_engines(tokens: list[TTTLaunchedToken], top_n: int = 10) -> list[TTTLaunchedToken]`
    - Sorted by `fees_eth_24h` desc, top N.

12. `aggregate_recent_launches(events, window_sec=86400) -> int`
    - Count of `event_type=="burn"` in last 24h.

### Reference

- Pattern: `maxpane_dashboard/analytics/ocm_signals.py`
- Concentration math source: `docs/tenthousandtokens_game_mechanics.md` (Holder Pool table)

---

## WP3: Data Layer (Client + Cache + Manager)

**Agent:** Senior Developer
**Depends on:** WP1 (models), WP0 (ABIs, addresses)
**Estimated scope:** Large (~700 lines across 3 files)

### Files to create

- `maxpane_dashboard/data/ttt_client.py`
- `maxpane_dashboard/data/ttt_cache.py`
- `maxpane_dashboard/data/ttt_manager.py`

### `ttt_client.py` -- Three data sources

HTTP/RPC client using `httpx.AsyncClient`. Follow `maxpane_dashboard/data/ocm_client.py` for the RPC patterns and `maxpane_dashboard/data/base_client.py` for the DexScreener patterns.

**Configuration:**
```python
_PRIMARY_RPC  = "https://eth.llamarpc.com"
_FALLBACK_RPCS = ["https://ethereum.publicnode.com", "https://cloudflare-eth.com"]
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (2.0, 4.0, 8.0)
_REQUEST_TIMEOUT = 15.0
_INTER_CALL_DELAY = 0.3
_DEXSCREENER_BATCH_URL = "https://api.dexscreener.com/tokens/v1/ethereum/{addresses}"
_DEXSCREENER_MAX_BATCH = 30
_RESERVOIR_FLOOR_URL = "https://api.reservoir.tools/collections/v7?contract={contract}"
_MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
_FACTORY = "0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e"
_FEESPLITTER = "<from-WP0>"
_LOG_RANGE_PER_CALL = 10_000  # blocks
```

**Methods to implement:**

1. **`async def fetch_factory_state(client) -> TTTFactoryState`**
   - One Multicall3 `aggregate3` batching:
     - factory.MAX_SUPPLY()
     - factory.burnCount()
     - factory.totalMinted()
     - feeSplitter.accETHPerShare() (or equivalent from WP0)
     - eth_blockNumber (separate raw RPC; can't multicall)
   - Returns `TTTFactoryState`.

2. **`async def fetch_burn_and_launch_events(client, from_block, to_block) -> list[BurnAndLaunchEvent]`**
   - `eth_getLogs` filtered on factory address + `BurnAndLaunch` topic.
   - Paginate: if `to_block - from_block > _LOG_RANGE_PER_CALL`, split into chunks.
   - Decode each log into `{token_id, erc20_address, deployer, launch_block, tx_hash, block_number}`.

3. **`async def fetch_deposit_events(client, from_block, to_block) -> list[DepositEvent]`**
   - `eth_getLogs` filtered on FeeSplitter address + `Deposit` topic.
   - Decode: `{source_token, gross_eth_wei, block_number, tx_hash}`.

4. **`async def fetch_buyback_events(client, token_addresses, from_block, to_block) -> list[BuybackEvent]`**
   - `eth_getLogs` filtered on multiple token addresses + `Buyback` topic.
   - Decode: `{token, caller, eth_spent_wei, tokens_bought, block_number, tx_hash}`.

5. **`async def fetch_swap_events(client, pool_or_token_addresses, from_block, to_block) -> list[SwapEvent]`**
   - Uniswap V4 swaps emit through the `PoolManager`; the TTTHook may also emit a custom event. **WP0 determines** whether we filter on PoolManager's `Swap` topic (with pool-key indexed args) or a hook-emitted custom event.
   - Decode amount and direction (positive = ETH-in / buy, negative = ETH-out / sell).
   - Filter to `abs(eth_amount_wei) >= 5 * 10**16` (≥0.05 Ξ) to avoid spam in the activity feed.

6. **`async def fetch_token_metadata(client, addresses: list[str]) -> dict[str, tuple[str, int]]`**
   - One multicall: for each address, batch `symbol()` and `decimals()`.
   - Returns `{address: (symbol, decimals)}`.
   - Cache this -- metadata is immutable, fetch once per token then never again.

7. **`async def fetch_token_reservoirs(client, addresses: list[str]) -> dict[str, int]`**
   - One multicall: for each address, call `reservoir()` (name from WP0).
   - Returns `{address: reservoir_wei}`.

8. **`async def fetch_market_data(client, addresses: list[str]) -> dict[str, dict]`**
   - Batch DexScreener: split into chunks of `_DEXSCREENER_MAX_BATCH`, concatenate addresses with comma.
   - Parse response: each `pair` has `priceUsd`, `priceChange.h24`, `volume.h24`, `marketCap`, `baseToken.address`.
   - Returns `{token_address_lower: {price_usd, change_h24, volume_h24, mcap}}`.
   - Handle missing tokens (newly launched, not yet indexed) by returning `None` per field.

9. **`async def fetch_nft_floor(client) -> TTTNFTFloor | None`**
   - GET `_RESERVOIR_FLOOR_URL.format(contract=_FACTORY)`.
   - Parse `collections[0].floorAsk.price.amount.native` (ETH) and `.usd` (USD).
   - Parse 24h sales count from `collections[0].volume.daily` if present, else `None`.
   - On 401/403 (keyless tier rate-limited) or network error, return `None`.

10. **Common RPC plumbing:**
    - `async def _eth_call(client, to, data, block="latest") -> str` -- single eth_call with retry/fallback RPC.
    - `async def _multicall(client, calls: list[tuple[str, str]]) -> list[str]` -- builds `aggregate3` calldata, decodes return tuple. Use a small ABI encoder helper (paste the `eth_abi.encode` / `decode` calls inline; library already imported via web3 transitive dep).
    - `async def _get_logs(client, address, topics, from_block, to_block) -> list[dict]` -- raw `eth_getLogs` with auto-paginate.
    - RPC failover: if primary returns 429 or 5xx, retry the same call on `_FALLBACK_RPCS` in order.

**Note on web3/abi encoding:** This project already has `httpx` as a hard dependency. Adding `eth_abi` (small, pure-python) is acceptable since OCM/CatTown projects use it for log decoding. Confirm with `grep` whether it is already in `pyproject.toml` before adding.

### `ttt_cache.py` -- Persistent state

Time-series + event log cache. Follow `maxpane_dashboard/data/ocm_cache.py` for save/load patterns and `maxpane_dashboard/data/base_cache.py` for hourly bucket aggregation.

**State to track:**

```python
class TTTCache:
    # Discovered launched tokens (address -> token metadata + market history)
    tokens: dict[str, TTTLaunchedToken]
    # Per-token cumulative + 24h-window fees, indexed by token_address
    fees_by_token: dict[str, list[FeeBucket]]  # bucket = (ts_hour, eth_wei)
    # Sparkline hourly buckets, 168 hours (7d) deep
    burns_hourly: deque[tuple[float, int]]      # (ts_hour, cumulative_burn_count)
    floor_hourly: deque[tuple[float, float]]    # (ts_hour, floor_eth)
    # Activity feed, recent events ring buffer (last 200)
    activity_log: deque[TTTActivityEvent]
    # Incremental scan watermark per event type
    last_seen_block: dict[str, int]             # {"BurnAndLaunch": N, "Deposit": M, ...}
    # 24h rolling counters
    launches_24h: int
    eth_to_holders_24h_wei: int
```

**Methods:**
- `register_new_token(token_id, address, deployer, launch_block, symbol, decimals)` -- adds to `tokens`, appends to `activity_log` as burn event.
- `apply_deposit(token_addr, gross_eth_wei, block, tx_hash)` -- updates fee buckets, appends activity event (FEE), increments 24h counter.
- `apply_buyback(token_addr, caller, eth_spent, block, tx_hash)` -- appends activity event (BBACK).
- `apply_swap(token_addr, sender, eth_amount, current_buy_tax_pct, block, tx_hash)` -- appends activity event (SWAP) if `|eth_amount| >= 0.05 Ξ`.
- `apply_sale(token_id, buyer, price_eth, tx_hash)` -- appends activity event (SALE) from Reservoir-derived data.
- `sample_burns_and_floor(now_ts, cum_burns, floor_eth)` -- once per refresh, append to hourly deques (dedupe by ts_hour).
- `prune_old(now_ts)` -- drop fee buckets older than 24h+1h, drop hourly samples older than 168h.
- `save_to_file(path) / load_from_file(path)` -- JSON persistence. Pydantic models serialize via `model_dump()`. Path: `~/.maxpane/ttt_cache.json`.

### `ttt_manager.py` -- Orchestrator

Calls client, updates cache, runs analytics, returns flat dict. Follow `maxpane_dashboard/data/ocm_manager.py`.

**Behavior:**
- `_cycle_count` increments each refresh.
- Every cycle:
  1. `fetch_factory_state()` (multicall) -- 1 RPC
  2. Incremental event scan: `from_block = max(cache.last_seen_block[type], current - 5000)`, `to_block = current`. Apply to cache.
  3. For new tokens discovered: `fetch_token_metadata()` (multicall) -- 1 RPC for all new ones.
  4. `fetch_token_reservoirs(all_tokens)` (multicall) -- 1 RPC.
  5. `fetch_market_data(all_tokens)` -- ceil(N/30) HTTP calls; DexScreener batched.
  6. `cache.sample_burns_and_floor()`.
- Every 2nd cycle (60s): `fetch_nft_floor()` (Reservoir).
- Every cycle: `price.py.get_eth_usd()` (60s cached internally).
- Run analytics module functions on the assembled state.
- Return flat dict.

**`fetch_and_compute()` returns:**

```python
{
    # Title bar
    "launches": int,                       # burn_count
    "max_supply": int,                     # always 10_000
    # Hero metrics
    "unburned": int,
    "burned_pct": float,
    "launches_24h": int,
    "holder_pool_eth_total": float,
    "holder_pool_eth_24h": float,
    "floor_eth": float | None,
    "floor_usd": float | None,
    # Leaderboard (top 10 by volume)
    "top_tokens_by_volume": list[dict],    # [{rank, symbol, price_usd, change_h24, vol_usd_h24, age_str, mcap_usd}]
    # Sparkline
    "burns_history": list[tuple[float, int]],
    "floor_history": list[tuple[float, float]],
    # Signals
    "fresh_launch_signal": dict | None,
    "buybacks_ready_signal": dict,
    "decay_window_signal": dict,
    "concentration_signal": dict,
    # Activity feed
    "activity_events": list[dict],         # last 25
    # Bottom-right α
    "top_fee_engines": list[dict],         # [{rank, symbol, fees_24h_eth, fees_lifetime_eth, fees_per_vol_pct}]
    # Bottom-right γ
    "claim_math_scenarios": list[dict],    # 6 rows
    # Meta
    "last_updated_seconds_ago": float,
    "error_count": int,
    "poll_interval": int,
    "active_view": str,                    # "fees" or "claims" -- set by screen, passed through to status bar
}
```

### Reference

- Client pattern: `maxpane_dashboard/data/ocm_client.py`
- Multicall + eth_call: same file, lines 100-200
- DexScreener batch pattern: `maxpane_dashboard/data/base_client.py`
- Cache hourly buckets: `maxpane_dashboard/data/base_cache.py`
- Manager pattern: `maxpane_dashboard/data/ocm_manager.py`
- Cache file location convention: `~/.maxpane/<game>_cache.json`

---

## WP4: Widgets

**Agent:** Frontend Developer
**Depends on:** WP3 (needs the flat dict keys from manager)
**Estimated scope:** Medium-large (~700 lines across 8 files)

### Files to create

All under `maxpane_dashboard/widgets/ttt/`:

- `__init__.py`
- `ttt_hero_metrics.py`
- `ttt_leaderboard.py`
- `ttt_sparkline.py`
- `ttt_signals.py`
- `ttt_activity_feed.py`
- `ttt_fees_table.py`
- `ttt_claims_table.py`

### `__init__.py`

```python
from .ttt_hero_metrics import TTTHeroMetrics
from .ttt_leaderboard import TTTLeaderboard
from .ttt_sparkline import TTTSparkline
from .ttt_signals import TTTSignals
from .ttt_activity_feed import TTTActivityFeed
from .ttt_fees_table import TTTFeesTable
from .ttt_claims_table import TTTClaimsTable

__all__ = [
    "TTTHeroMetrics",
    "TTTLeaderboard",
    "TTTSparkline",
    "TTTSignals",
    "TTTActivityFeed",
    "TTTFeesTable",
    "TTTClaimsTable",
]
```

### `ttt_hero_metrics.py` -- 4 hero boxes

- Class: `TTTHeroMetrics(Horizontal)` containing 4x `TTTHeroBox(Static)`
- IDs: `#ttt-hero-unburned`, `#ttt-hero-launches`, `#ttt-hero-holders`, `#ttt-hero-floor`
- `update_data(unburned, burned_pct, launches_total, launches_24h, holder_pool_eth_total, holder_pool_eth_24h, floor_eth, floor_usd)`

**UNBURNED box:**
- Title `"UNBURNED"`, big number `f"{unburned:,}"`, subtitle `f"{100-burned_pct:.2f}% of 10,000"`.

**LAUNCHES box:**
- Title `"LAUNCHES"`, big number `f"{launches_total}"`, subtitle `f"+{launches_24h} 24h"` colored green if > 0 else dim.

**HOLDER POOL box:**
- Title `"HOLDER POOL"`, big number `f"{holder_pool_eth_total:.3f} Ξ"`, subtitle `f"+{holder_pool_eth_24h:.4f} Ξ 24h"`.

**FLOOR box:**
- Title `"FLOOR"`, big number `f"{floor_eth:.4f} Ξ"` or `"—"` if None.
- Subtitle `f"${floor_usd:,.0f}"` or `"—"`.

**Reference:** `maxpane_dashboard/templates/hero_metrics_template.py`, `maxpane_dashboard/widgets/ocm/ocm_hero_metrics.py`

### `ttt_leaderboard.py` -- Top tokens by volume

- Class: `TTTLeaderboard(Vertical)` containing title Static + DataTable
- Columns: `#` (w=3), `SYM` (w=8), `PRICE` (w=10), `24h%` (w=8), `VOL` (w=10), `AGE` (w=6), `MCAP` (w=10)
- `update_data(top_tokens_by_volume: list[dict])`
- Bold row 1.
- Format helpers:
  - `price`: `$0.0312` if ≥ $0.01, else `$0.0E-4` scientific.
  - `change_h24`: `+12.4%` green, `-3.1%` red, `—` dim.
  - `volume_usd`: `$44.2K`, `$1.1M`.
  - `age`: `<60` → `<N>m`, `<24h` → `<N>h`, else `<N>d`.
  - `mcap`: `$110K`, `$1.7M`.
- Strip non-printable chars from symbol; truncate to 8 chars.

**Reference:** `maxpane_dashboard/templates/leaderboard_template.py`, `maxpane_dashboard/widgets/base/base_leaderboard.py`

### `ttt_sparkline.py` -- Burns + floor overlay

- Class: `TTTSparkline(Vertical)` with title + 2 sparkline rows (one per series)
- Width: 40 chars. Each row labeled (`BURNS`, `FLOOR Ξ`).
- `update_data(burns_history, floor_history)` -- inputs are lists of `(ts, value)` hourly samples.
- Render as 168-point sparkline (7d). If fewer samples, render what we have with `"waiting for data..."` placeholder until ≥ 2 samples per series.
- Burns: orange. Floor: cyan.

**Note:** Existing sparkline widgets render a single series. This widget renders two stacked rows; each row is its own sparkline. No fancy overlay -- just two parallel rows sharing a time axis label.

**Reference:** `maxpane_dashboard/templates/sparkline_template.py`, `maxpane_dashboard/widgets/ocm/ocm_sparklines.py`

### `ttt_signals.py` -- 4-line signals panel

- Class: `TTTSignals(Vertical)` with title + 4 signal rows
- `update_data(fresh_launch_signal, buybacks_ready_signal, decay_window_signal, concentration_signal)`
- Each signal dict has: `label`, `value_str`, `indicator`, `color`.
- Fresh launch row only renders if `fresh_launch_signal is not None`; otherwise show 3 rows.
- Color via Textual markup: `f"[{color}]{indicator}[/] {value_str}"`.

**Reference:** `maxpane_dashboard/templates/signals_template.py`, `maxpane_dashboard/widgets/ocm/ocm_signals.py`

### `ttt_activity_feed.py` -- Heterogeneous event stream

- Class: `TTTActivityFeed(Vertical)` with title Static + RichLog
- `update_data(activity_events: list[dict])` -- last 25 events
- Format per event type:
  - **BURN**:    `HH:MM  [yellow]BURN [/]  {sym:>6}  by {actor:.6}…   tokenId {token_id}`
  - **SWAP**:    `HH:MM  [{dir_color}]SWAP [/]  {sym:>6}  {±eth_amount:>+7.4f} Ξ  tax {tax_pct}%`
  - **FEE**:     `HH:MM  [green]FEE  [/]  {sym:>6}  {eth_30pct:.4f} Ξ → holders`
  - **BBACK**:   `HH:MM  [magenta]BBACK[/]  {sym:>6}  {bounty:.5f} Ξ bounty paid`
  - **SALE**:    `HH:MM  [cyan]SALE [/]  TTT     #{token_id}  {price_eth:.4f} Ξ`
- `dir_color`: green for buys (+), red for sells (-).
- Clear RichLog and rewrite on each update.

**Reference:** `maxpane_dashboard/templates/activity_feed_template.py`, `maxpane_dashboard/widgets/ocm/ocm_activity_feed.py`

### `ttt_fees_table.py` -- α view (Top Fee Engines)

- Class: `TTTFeesTable(Vertical)` with title + DataTable
- Columns: `#` (w=3), `SYM` (w=8), `24h FEES` (w=12), `LIFETIME` (w=12), `24h FEE/VOL` (w=12)
- `update_data(top_fee_engines: list[dict])` -- top 10
- `24h FEE/VOL` shows `f"{ratio*100:.1f}%"` when vol > 0, else `"—"`.
- Bold row 1.

**Reference:** `maxpane_dashboard/templates/two_column_table_template.py`

### `ttt_claims_table.py` -- γ view (Claim Math)

- Class: `TTTClaimsTable(Vertical)` with title + DataTable
- Columns: `SCENARIO` (w=14), `UNBURNED` (w=10), `SHARE / DEPOSIT` (w=16), `24h PROJECTION` (w=14), `× TODAY` (w=8)
- 6 rows from `claim_math_scenarios`.
- Highlight the "Today" row (e.g. `[bold]`).

**Note:** Both fees-table and claims-table are siblings under the screen; the screen swaps which is `display: True` based on the active view.

**Reference:** `maxpane_dashboard/templates/two_column_table_template.py`

---

## WP5: Screen + App Integration

**Agent:** Senior Developer
**Depends on:** WP3 (manager), WP4 (widgets), WP2 (analytics imported by manager)
**Estimated scope:** Medium (~250 lines new + ~50 lines modified across 4 files)

### Files to create

- `maxpane_dashboard/screens/ttt.py`

### Files to modify

- `maxpane_dashboard/app.py`
- `maxpane_dashboard/screens/game_select.py`
- `maxpane_dashboard/themes/minimal.tcss`

### `ttt.py` -- Screen

Follow `maxpane_dashboard/screens/ocm.py` closely. Single screen with `c` toggle binding.

```python
"""TTTScreen — Ten Thousand Tokens dashboard as a Textual Screen."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.data.ttt_manager import TTTManager
from maxpane_dashboard.widgets.ttt import (
    TTTActivityFeed,
    TTTClaimsTable,
    TTTFeesTable,
    TTTHeroMetrics,
    TTTLeaderboard,
    TTTSignals,
    TTTSparkline,
)
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)


class TTTScreen(Screen):
    """Ten Thousand Tokens dashboard."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "toggle_view", "Toggle Fees/Claims", show=True),
    ]

    def __init__(self, data_manager: TTTManager, poll_interval: int, **kwargs):
        super().__init__(**kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        self._active_view: str = "fees"   # or "claims"

    def compose(self) -> ComposeResult:
        yield Static("Ten Thousand Tokens · Ethereum Mainnet · 0/10,000", id="title-bar")
        yield TTTHeroMetrics()

        with Horizontal(id="middle-row"):
            yield TTTLeaderboard()
            with Vertical(id="right-col"):
                yield TTTSparkline()
                yield TTTSignals()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield TTTActivityFeed()
            # Both tables live in the layout; one is hidden at a time.
            yield TTTFeesTable(id="ttt-fees-table")
            yield TTTClaimsTable(id="ttt-claims-table")

        yield StatusBar()

    def on_mount(self) -> None:
        # Start with α visible, γ hidden.
        self.query_one("#ttt-claims-table").display = False

    def action_toggle_view(self) -> None:
        if self._active_view == "fees":
            self._active_view = "claims"
            self.query_one("#ttt-fees-table").display = False
            self.query_one("#ttt-claims-table").display = True
        else:
            self._active_view = "fees"
            self.query_one("#ttt-fees-table").display = True
            self.query_one("#ttt-claims-table").display = False
        try:
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("ten thousand tokens")
            self.query_one(StatusBar).set_active_view(self._active_view)
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def _do_initial_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="ttt-refresh")

    def _schedule_refresh(self) -> None:
        self.run_worker(self._do_refresh(), exclusive=True, name="ttt-refresh")

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            logger.error("TTT refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=999,
                    error_count=self._data_manager._error_count,
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        # Title bar
        try:
            self.query_one("#title-bar", Static).update(
                f"Ten Thousand Tokens · Ethereum Mainnet · "
                f"{data['launches']}/{data['max_supply']:,}"
            )
        except Exception:
            pass

        # Update each widget. Each call is wrapped in try/except so a single
        # widget failure does not break the entire refresh.
        for widget_cls, payload_keys in [
            (TTTHeroMetrics, (
                "unburned", "burned_pct", "launches", "launches_24h",
                "holder_pool_eth_total", "holder_pool_eth_24h",
                "floor_eth", "floor_usd",
            )),
            # ... (full update list, see below)
        ]:
            try:
                self.query_one(widget_cls).update_data(
                    **{k: data.get(k) for k in payload_keys}
                )
            except Exception as exc:
                logger.warning("TTT widget %s update failed: %s", widget_cls.__name__, exc)

        # Status bar
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=0,
                error_count=self._data_manager._error_count,
                poll_interval=self._poll_interval,
            )
        except Exception:
            pass
```

The `for widget_cls, payload_keys` loop is shown abbreviated; in the actual code, list all 7 widget classes with their exact payload keys (matching the manager's flat dict).

### `app.py` modifications

Add to imports:
```python
from maxpane_dashboard.data.ttt_manager import TTTManager
from maxpane_dashboard.screens.ttt import TTTScreen
```

Add to `__init__`:
```python
self._ttt_manager = TTTManager(poll_interval=poll_interval)
```

Add to `on_mount` prefetch block:
```python
elif self._initial_game == "ttt":
    self.run_worker(self._ttt_manager.fetch_and_compute(), exclusive=True, name="prefetch")
```

Add to `_launch_game`:
```python
elif game_id == "ttt":
    if not self.is_screen_installed("ttt"):
        self.install_screen(
            TTTScreen(self._ttt_manager, self.poll_interval, name="ttt"),
            name="ttt",
        )
    self.push_screen("ttt")
```

Add `"ttt"` to `_GAME_CYCLE`.

Add to `action_quit`:
```python
try:
    await self._ttt_manager.close()
except Exception as exc:
    logger.warning("Error during ttt shutdown: %s", exc)
```

### `game_select.py` modification

Add entry to `GAMES` list (assuming the next slot is "7"):
```python
("7", "ttt", "Ten Thousand Tokens", "NFT collection w/ UniV4 burn-to-launch on Ethereum"),
```

### `minimal.tcss` -- CSS Rules

Add after the existing OCM/Base/DOTA sections. Reuse Base/DOTA neon-trading palette since TTT is also a token-trading-flavored mainnet screen.

```css
/* ── Ten Thousand Tokens screen ─────────────────────────────────────── */

TTTHeroMetrics {
    height: 7; padding: 0 1; margin: 1 0 0 0;
}
TTTHeroBox {
    width: 1fr; height: 7; border: solid $panel; padding: 1 2;
    content-align: center middle; text-align: center;
    background: $surface; margin: 0 1;
}
TTTLeaderboard {
    width: 3fr; padding: 0 1;
}
TTTLeaderboard > .leaderboard-title {
    color: $text-muted; padding: 0 1; text-style: bold; margin: 0 0 1 0;
}
TTTSparkline {
    height: auto; padding: 0 1; content-align: center top;
}
TTTSparkline > .chart-title {
    color: $text-muted;
}
TTTSignals {
    height: 1fr; padding: 0 1; margin: 1 0 0 0;
    overflow-y: auto; content-align: center top;
}
TTTSignals > .signals-title {
    color: $text-muted;
}
TTTActivityFeed {
    width: 3fr; padding: 0 1;
}
TTTActivityFeed > .feed-title {
    color: $text-muted; margin: 0 0 1 0;
}
TTTActivityFeed RichLog {
    background: $background; scrollbar-size: 1 1;
}
TTTFeesTable, TTTClaimsTable {
    width: 2fr; padding: 0 1; content-align: center top;
}
TTTFeesTable > .fees-title,
TTTClaimsTable > .claims-title {
    color: $text-muted; padding: 0 1; text-style: bold; margin: 0 0 1 0;
}
```

### Reference

- Screen pattern: `maxpane_dashboard/screens/ocm.py`
- App integration pattern: search for `ocm` in `maxpane_dashboard/app.py`
- Game select pattern: `maxpane_dashboard/screens/game_select.py`
- CSS pattern: OCM section in `maxpane_dashboard/themes/minimal.tcss`

### Status-bar extension

If `StatusBar.set_active_view()` does not exist yet, add it as a small method that prints `"View: fees"` or `"View: claims"` somewhere in the bar:
```python
def set_active_view(self, view: str) -> None:
    self._active_view = view
    self.refresh()
```
And include it in the `render()` template.

---

## WP6: Tests

**Agent:** Backend Architect
**Depends on:** WP2 (analytics), WP1 (models)
**Estimated scope:** Small-medium (~250 lines, ~30 tests)

### Files to create

- `tests/analytics/test_ttt_signals.py`
- `tests/data/test_ttt_client.py` (light -- mocks httpx; full RPC integration is manual)
- `tests/data/test_ttt_cache.py`

### `test_ttt_signals.py`

**Decay tax:**
- `decay_tax_pct(0) == 99`
- `decay_tax_pct(1) == 98`
- `decay_tax_pct(50) == 49`
- `decay_tax_pct(97) == 2`
- `decay_tax_pct(98) == 1`
- `decay_tax_pct(99) == 1`     # floor
- `decay_tax_pct(10_000) == 1` # still floor

**Concentration:**
- `per_nft_share(10_000) == 0.30 / 10_000`
- `per_nft_share(5_000) == 0.30 / 5_000`
- `per_nft_share(1) == 0.30`
- `per_nft_share(0) == 0.0`
- `concentration_multiplier(10_000) == 1.0`
- `concentration_multiplier(1_000) == 10.0`

**count_buybacks_ready:**
- Empty token list returns `(0, 0)`.
- 3 tokens, 1 above 0.1 Ξ threshold returns `(1, 0.005 * reservoir_in_wei)`.
- Token with reservoir > 1 Ξ: bounty caps at `0.005 * 1 Ξ`.

**count_decay_window:**
- Tokens within 98 blocks of `current_block` counted; older ones not.
- Boundary: launch_block exactly 98 ago is NOT counted; 97 ago IS.

**fresh_launch_alert:**
- No burn events in last 10 min returns `None`.
- Burn event 3 min ago returns signal with `value_str` containing `"3m ago"` and the correct tax pct.
- Burn event 11 min ago returns `None`.

**buybacks_ready_signal:**
- Returns dict with `label`, `value_str`, `indicator`, `color`.
- Count of 0 → color "dim". Count > 0 → color "green".

**decay_window_signal:**
- Same shape. Count 0 → dim. Count > 0 → yellow.

**concentration_signal:**
- Format includes `"1/{unburned:,}"` and "Ξ/day" suffix.
- With `unburned=9891`, `eth_to_holders_24h=0.5`, per-NFT 24h projection ≈ 5.05e-5 Ξ.

**claim_math_scenarios:**
- Returns 6 rows.
- "Today" row uses passed `state.unburned`.
- "Sole survivor" row has `unburned=1`, `share_pct=30.0`, multiplier = today_unburned / 1 (very large).
- All projections scale inversely with scenario unburned, holding eth_to_holders_24h constant.

**aggregate_recent_launches:**
- Empty events → 0.
- 3 burn events within 24h + 2 outside → 3.

### `test_ttt_client.py`

Light HTTP-level test: monkeypatch `httpx.AsyncClient.post` to return a canned RPC response and assert the client parses it into the right model. One test per fetch method (factory state, market data, NFT floor). Skip RPC/network integration tests -- those are manual.

### `test_ttt_cache.py`

- `register_new_token` appends to activity log and adds to tokens dict.
- `apply_deposit` increments 24h rolling counter; `prune_old` clears entries beyond 24h+1h.
- `sample_burns_and_floor` dedupes by hourly timestamp.
- `save_to_file` + `load_from_file` round-trips state.

### Reference

- Test pattern: `tests/analytics/test_ocm_signals.py`, `tests/data/test_ocm_client.py` (if present)

---

## Execution Summary

| WP | Name | Agent | Depends on | Files | Est. Lines |
|----|------|-------|------------|-------|------------|
| 0  | ABI Recon | Backend Architect | -- | 5 new | ~150 |
| 1  | Models | Backend Architect | WP0 | 1 new | ~140 |
| 2  | Analytics | Backend Architect | WP0 | 1 new | ~200 |
| 3  | Data Layer | Senior Developer | WP1 | 3 new | ~700 |
| 4  | Widgets | Frontend Developer | WP3 | 8 new | ~700 |
| 5  | Screen + Integration | Senior Developer | WP3, WP4 | 1 new, 3 modified | ~300 |
| 6  | Tests | Backend Architect | WP2 | 3 new | ~250 |

**Total:** ~22 new files, 3 modified files, ~2440 lines

## Recommended Execution Order

1. **Phase 0 (sequential, ~30 min):** WP0 (ABI recon must finish before anything else).
2. **Phase 1 (parallel):** WP1 + WP2 + WP6 (tests against WP2's contracts can be written immediately).
3. **Phase 2:** WP3 (blocked on WP1).
4. **Phase 3 (parallel):** WP4 + WP5 (blocked on WP3; WP5 can start with stubbed widgets and integrate as WP4 lands them).
5. **Phase 4 (manual):** E2E test -- `python -m maxpane_dashboard`, select TTT from the menu, verify all widgets populate over 2-3 refresh cycles, press `c` to toggle Fees/Claims, screenshot each state.
6. **Phase 5 (iteration):** Polish per [[feedback-workflow]] -- iterate on screenshots until layout/spacing/colors are right.

## Risks and Unknowns

1. **ABI recon may reveal naming differences from the whitepaper.** WP0 must complete first; all other WPs read from the ABI JSONs and the recon note. Mitigation: WP0 is sized small so it can iterate.
2. **Reservoir keyless tier coverage.** May rate-limit or 401 unpredictably. Mitigation: `fetch_nft_floor` returns `None` gracefully; floor tile shows `—`; sparkline floor series gaps.
3. **Public RPC rate limits.** Mitigation: Multicall3 batching collapses dozens of per-cycle reads into 2-3 HTTP calls; event-log queries are incremental.
4. **eth_abi dependency.** Confirm before WP3 starts -- run `grep eth_abi pyproject.toml`. If missing, add to `pyproject.toml` as part of WP3 (or use manual hex slicing for the few decodes we need).
5. **DexScreener coverage of fresh launches.** Newly burned tokens may not appear in DexScreener immediately. Mitigation: leaderboard shows only tokens with confirmed market data; new tokens still appear in activity feed and the decay-window signal.
6. **Status-bar `set_active_view` method.** May need to be added; small change in `widgets/status_bar.py`. WP5 owns this.
7. **Multicall3 with 100+ subcalls.** Safe in theory but could hit RPC payload size limits on the more restrictive public endpoints. Mitigation: chunk subcalls into batches of 50 if needed.

## Validation Plan

1. WP0: All 4 ABI JSONs parse; recon note has all addresses filled in (no `<TBD>`); topic hashes verified locally.
2. WP1: `pytest tests/data/test_ttt_models.py` -- model construction with sample dicts.
3. WP2: `pytest tests/analytics/test_ttt_signals.py` -- all ~20 tests pass.
4. WP3: `python -c "import asyncio; from maxpane_dashboard.data.ttt_manager import TTTManager; m=TTTManager(poll_interval=30); print(asyncio.run(m.fetch_and_compute()))"` returns a populated dict with no exceptions.
5. WP4: `pytest tests/widgets/test_ttt_*.py` -- compose tests for each widget.
6. WP5: `python -m maxpane_dashboard` -- TTT appears in game-select; selecting it shows the screen; all 7 widget areas populate within 30s.
7. Toggle: pressing `c` swaps the bottom-right between Fees and Claims tables; status bar reflects active view.
8. Multi-theme: cycling themes does not break TTT widget CSS (all rules use `$panel`, `$surface`, `$text-muted`, `$background` theme variables).
9. Graceful degradation: simulate Reservoir failure by blocking the host in `/etc/hosts`; floor tile shows `—`, error count increments, no crash.
10. Persistence: stop the dashboard, restart; sparkline and activity feed are populated from `~/.maxpane/ttt_cache.json` immediately.

## Self-Review

### Spec coverage check

Walked each spec section against the plan:

| Spec section | Covered by |
|---|---|
| Hero cards (Unburned, Launches, Holder Pool, Floor) | WP1 (TTTFactoryState, TTTNFTFloor) + WP3 (manager flat dict) + WP4 (TTTHeroMetrics) |
| Leaderboard (Top tokens by 24h vol) | WP3 (`fetch_market_data`) + WP4 (TTTLeaderboard) |
| Sparkline (burns + floor 7d) | WP3 (cache hourly buckets) + WP4 (TTTSparkline) |
| Signals (4 items + fresh launch alert) | WP2 (all 5 signal functions) + WP4 (TTTSignals) |
| Activity feed (heterogeneous events) | WP3 (5 fetch + apply methods) + WP4 (TTTActivityFeed) |
| Fees ⇄ Claims toggle | WP2 (claim_math_scenarios, top_fee_engines) + WP4 (two widgets) + WP5 (toggle handler + `c` binding) |
| 30s refresh, multi-source TTLs | WP3 (manager cycle logic) |
| Keyless data | WP0 + WP3 (no API keys anywhere) |
| Error handling | WP3 (each fetch returns T|None) + WP5 (per-widget try/except in `_do_refresh`) |
| Tests ~30 | WP6 |
| File-list match | All 22 new files in the spec's "Implementation Approach" appear under a WP |

No gaps detected.

### Placeholder scan

No `TBD`/`TODO`/"implement later" in the plan body. Two intentional `<TBD-from-recon>` placeholders are inside the example output of WP0 -- these are what WP0 fills in, by design.

### Type consistency

- `TTTLaunchedToken.address` consistently lowercased hex throughout.
- `eth_amount_wei` is signed in `TTTActivityEvent` and the same field used in `apply_swap` / activity-feed formatting.
- `acc_eth_per_share` raw uint256 in WP1, applied with SCALE in WP2 -- consistent.
- `update_data(...)` keyword args between manager flat dict (WP3) and each widget (WP4) match.

Plan is internally consistent.
