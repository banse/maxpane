# Onchain Monsters (OCM) Dashboard -- Implementation Plan

## Overview

Add an OCM (Onchain Monsters) collection analytics dashboard to MaxPane. This is a staking-centric NFT dashboard reading Ethereum mainnet contracts directly via JSON-RPC. No external API -- all data comes from `eth_call` and `eth_getLogs`.

**Design spec:** `/Library/Vibes/autopull/docs/superpowers/specs/2026-03-29-ocm-dashboard-design.md`
**Technical findings:** `/Library/Vibes/autopull/docs/ocm_technical_findings.md`

---

## Wave 1: Independent Work (all parallel)

### WP-1: Models (`dashboard/data/ocm_models.py`)

**Create:** `/Library/Vibes/autopull/dashboard/data/ocm_models.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/data/cattown_models.py`

Pydantic v2 frozen models. Follow the exact `ConfigDict(frozen=True)` pattern from Cat Town.

```python
from pydantic import BaseModel, ConfigDict
```

**Models to define:**

1. **`OCMCollectionStats`** (frozen)
   - `total_supply: int` -- from NFT `totalSupply()`
   - `max_supply: int` -- hardcoded 10_000
   - `current_minting_cost: int` -- from NFT `currentMintingCost()`, raw wei (OCMD has 18 decimals)
   - `burned_count: int` -- derived from max minted minus current supply (or from Transfer-to-zero logs)
   - `net_supply: int` -- `total_supply - burned_count`
   - `remaining: int` -- `max_supply - total_supply`
   - `minted_pct: float` -- `total_supply / max_supply * 100`

2. **`OCMStakingStats`** (frozen)
   - `total_staked: int` -- count of NFTs transferred to OCMD contract address
   - `ocmd_total_supply: float` -- from OCMD `totalSupply()`, converted from wei
   - `daily_emission: float` -- `total_staked * 1.0` (1 OCMD/day/monster)
   - `staking_ratio: float` -- `total_staked / net_supply * 100` (percentage)
   - `days_to_earn_mint: float` -- `current_minting_cost_ocmd / 1.0` (days per monster to earn enough to mint)

3. **`OCMActivityEvent`** (frozen)
   - `tx_hash: str`
   - `block_number: int`
   - `timestamp: int` -- resolved from block
   - `event_type: str` -- one of "mint", "burn", "stake", "unstake"
   - `actor_address: str` -- the user address involved
   - `token_id: int | None` -- for mint/burn events
   - `count: int` -- for stake/unstake events (number of NFTs in that tx)

4. **`OCMSnapshot`** (frozen)
   - `fetched_at: float`
   - `collection: OCMCollectionStats`
   - `staking: OCMStakingStats`
   - `holder_count: int`
   - `recent_events: list[OCMActivityEvent]`

**Notes:**
- No `from_raw` classmethod needed here since we are decoding hex directly in the client, but add one on `OCMStakingStats` if it simplifies the client code.
- `_WEI = 10**18` constant at module top.

---

### WP-2: Client (`dashboard/data/ocm_client.py`)

**Create:** `/Library/Vibes/autopull/dashboard/data/ocm_client.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/data/cattown_client.py` (first ~60 lines for structure, retry logic, selector constants)

Async httpx client with serialized RPC calls (no parallelism). All reads use raw `eth_call` with 4-byte function selectors.

**Constants:**

```python
import os

_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_REQUEST_TIMEOUT = 15.0
_WEI = 10**18

_RPC_URL = os.environ.get("MAXPANE_ETH_RPC_URL", "https://eth.merkle.io")

# Contract addresses
_NFT_ADDRESS = "0xaA5D0f2E6d008117B16674B0f00B6FCa46e3EFC4"
_OCMD_ADDRESS = "0x10971797FcB9925d01bA067e51A6F8333Ca000B1"
_FAUCET_ADDRESS = "0xd495a9955550c20d03197c8ba3f3a8c7f8d17eb3"

# Function selectors (4-byte keccak prefixes)
_SEL_TOTAL_SUPPLY = "0x18160ddd"        # totalSupply()
_SEL_CURRENT_MINTING_COST = "0xc8a4c3c5"  # currentMintingCost() -- VERIFY THIS SELECTOR
_SEL_BALANCE_OF = "0x70a08231"          # balanceOf(address)
_SEL_IS_CLOSED = "0xc2b6b58c"           # isClosed() -- VERIFY THIS SELECTOR

# ERC-721 Transfer event topic
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_ZERO_ADDR_TOPIC = "0x" + "0" * 64
```

**IMPORTANT: Selector verification.** The implementing agent MUST verify `currentMintingCost()` and `isClosed()` selectors by computing `keccak256` of the function signature. Use Python: `from web3 import Web3; Web3.keccak(text="currentMintingCost()")[:4].hex()`. If web3 is not available, use the verified Etherscan ABI. The Cat Town client has a comment about selector verification -- follow that same practice.

**Class structure:**

```python
class OCMClient:
    def __init__(self, rpc_url: str = _RPC_URL) -> None:
        self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        self._rpc_url = rpc_url
        self._rpc_id = 0

    async def close(self) -> None: ...
    async def _rpc_call(self, method: str, params: list) -> Any: ...
    async def _eth_call(self, to: str, data: str) -> str: ...
    async def _eth_get_logs(self, params: dict) -> list: ...
    async def _get_block_timestamp(self, block_hex: str) -> int: ...
    async def _resolve_block_timestamps(self, block_numbers: set[int]) -> dict[int, int]: ...
    async def fetch_snapshot(self) -> OCMSnapshot: ...
```

**`fetch_snapshot()` implementation flow:**

1. **Collection stats:**
   - `eth_call` to NFT contract: `totalSupply()` -> decode uint256
   - `eth_call` to NFT contract: `currentMintingCost()` -> decode uint256 (in OCMD wei)
   - `eth_call` to Faucet: `isClosed()` -> decode bool (informational, not displayed in Phase 1 but good to have)

2. **Staking stats:**
   - `eth_call` to OCMD: `totalSupply()` -> decode uint256 (total OCMD minted)
   - Staked count: count NFTs held by the OCMD contract address. Use `eth_call` to NFT: `balanceOf(OCMD_ADDRESS)` -> decode uint256. This gives total staked NFT count.

3. **Activity events (last 500 blocks):**
   - Get current block number via `eth_blockNumber`
   - Scan NFT Transfer events from `(current - 500)` to `latest`
   - Filter: `from == 0x0` -> mint; `to == 0x0` -> burn; `to == OCMD_ADDRESS` -> stake; `from == OCMD_ADDRESS` -> unstake
   - Each Transfer event has 3 indexed topics: `Transfer(from, to, tokenId)`
   - For stake/unstake, group by tx_hash to get count per transaction

4. **Block timestamp resolution:**
   - Collect unique block numbers from events
   - Batch `eth_getBlockByNumber` calls (serialize, one at a time) to resolve timestamps
   - Same fix pattern as Cat Town: batch unique blocks, not per-event

5. **Holder count:**
   - This is the trickiest part. Options:
     - (a) Use NFT `balanceOf` spot checks -- not viable for total holder count
     - (b) Scrape Etherscan token holder page (fragile)
     - (c) Count unique addresses from Transfer event logs over full history (expensive RPC)
     - (d) Hardcode a reasonable estimate and update periodically
   - **Recommended approach:** Try `eth_getLogs` for Transfer events over a wider range (e.g., last 50,000 blocks) on first load, then cache. If too slow, fall back to a hardcoded estimate. The holder count field can gracefully show "~" prefix if estimated.
   - Cache holder count for 5 polls (5 minutes at 60s interval). Only recompute every 5th poll.

6. **Burned count:**
   - Use `balanceOf(0x000...dead)` plus scanning Transfer-to-zero events.
   - OR simpler: if the NFT contract tracks burns, the difference between max-ever-minted and current `totalSupply()` gives burn count. Check if `totalSupply` decreases on burn (it does for standard ERC-721 with burn). If so: `burned = (highest_known_tokenId) - totalSupply`. But since we do not know highest tokenId without scanning, a simpler approach: count Transfer-to-zero events in the log scan window and accumulate over time. For Phase 1, start with burned_count=0 and increment from observed burns.
   - **Simplest approach:** `burned_count = 0` initially, accumulate from Transfer-to-zero events seen in logs. The cache will persist this across restarts.

**Retry logic:** Copy the `_rpc_call` retry pattern exactly from `cattown_client.py` -- exponential backoff on HTTP errors and 429 status codes.

**Error handling:** All RPC calls should raise on failure after retries. The manager catches exceptions.

---

### WP-3: Cache (`dashboard/data/ocm_cache.py`)

**Create:** `/Library/Vibes/autopull/dashboard/data/ocm_cache.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/data/cattown_cache.py`

Time-series deque cache with JSON persistence. Follow Cat Town cache structure exactly.

**Time series (3 deques, `max_history=120`):**
- `supply_history: deque[TimeSeriesPoint]` -- NFT total supply over time
- `staked_history: deque[TimeSeriesPoint]` -- staked NFT count over time
- `ocmd_supply_history: deque[TimeSeriesPoint]` -- OCMD token total supply over time

**Additional cached state:**
- `_latest: OCMSnapshot | None`
- `_last_updated: float | None`
- `_cumulative_burned: int` -- accumulated burn count from observed events
- `_cumulative_minted: int` -- accumulated mint count from observed events (for velocity calc)
- `_holder_count: int` -- cached holder count
- `_holder_count_updated: float` -- timestamp of last holder count update

**Methods (mirror Cat Town cache):**
- `update(snapshot, ...)` -- append to all 3 deques, update `_latest`
- `get_supply_history()` -> `list[TimeSeriesPoint]`
- `get_staked_history()` -> `list[TimeSeriesPoint]`
- `get_ocmd_supply_history()` -> `list[TimeSeriesPoint]`
- `get_latest()` -> `OCMSnapshot | None`
- `save_to_file(path)` -- atomic write via tmp + rename
- `load_from_file(path)` -- load with graceful fallback

**Persistence file:** `~/.maxpane/ocm_cache.json`

**Persistence format:**
```json
{
    "saved_at": 1711756800.0,
    "max_history": 120,
    "supply_history": [[ts, val], ...],
    "staked_history": [[ts, val], ...],
    "ocmd_supply_history": [[ts, val], ...],
    "cumulative_burned": 312,
    "cumulative_minted": 4084,
    "holder_count": 678
}
```

---

### WP-4: Signals (`dashboard/analytics/ocm_signals.py`)

**Create:** `/Library/Vibes/autopull/dashboard/analytics/ocm_signals.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/analytics/cattown_signals.py`

Pure functions, no side effects. Each returns a signal dict with keys: `label`, `value_str`, `indicator`, `color`.

**Functions to implement:**

1. **`generate_staking_signal(staking_ratio: float) -> dict`**
   - Green `healthy`: ratio > 40%
   - Yellow `moderate`: 20-40%
   - Red `low`: ratio < 20%
   - `label`: "Staking Rate"
   - `value_str`: e.g. "51% staked"

2. **`generate_mint_velocity_signal(mints_per_day: float) -> dict`**
   - Green `active`: > 5/day
   - Yellow `steady`: 1-5/day
   - Dim `quiet`: < 1/day
   - `label`: "Mint Velocity"
   - `value_str`: e.g. "~3/day"

3. **`generate_burn_rate_signal(burns_per_week: float) -> dict`**
   - Red `high`: > 5/week
   - Yellow `moderate`: 1-5/week
   - Dim `rare`: < 1/week
   - `label`: "Burn Rate"
   - `value_str`: e.g. "~2/week"

4. **`generate_recommendation(staking_ratio: float, mints_per_day: float, burns_per_week: float, supply_trend_up: bool) -> str`**
   - One-line recommendation string
   - Logic from the design spec:
     - Staking > 40% + velocity > 1 -> "Healthy staking ratio, steady mints"
     - Staking < 20% -> "Low staking activity -- holders may be disengaged"
     - Velocity trending up (caller determines this) -> "Mint velocity rising -- growing interest"
     - Net supply decreasing (burns > mints) -> "Supply contracting -- more burns than mints"
     - Default: "Collection stable -- monitoring trends"

5. **`compute_mint_velocity(supply_history: list[tuple[float, float]]) -> float`**
   - Given supply time-series, compute rolling average mints per day.
   - Look at supply delta over the time range. `delta_supply / delta_time_days`.
   - If fewer than 2 points, return 0.0.

6. **`compute_burn_rate(burned_history: list[tuple[float, float]]) -> float`**
   - Similar: compute burns per week from observed data.
   - If fewer than 2 points, return 0.0.

---

### WP-5: Hero Metrics Widget (`dashboard/widgets/ocm/ocm_hero_metrics.py`)

**Create:** `/Library/Vibes/autopull/dashboard/widgets/ocm/ocm_hero_metrics.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_hero_metrics.py`

3 hero boxes in a Horizontal:

1. **SUPPLY** -- `id="ocm-hero-supply"`
   - Main: `"{total_supply:,} / 10K"`
   - Sub: `"{minted_pct:.1f}% minted"`

2. **HOLDERS** -- `id="ocm-hero-holders"`
   - Main: `"{holder_count:,}"`
   - Sub: `"avg {avg_per_holder:.1f} / holder"`

3. **REWARD / MONSTER** -- `id="ocm-hero-reward"`
   - Main: `"1 $OCMD/day"`
   - Sub: `"mint cost: {cost} $OCMD"` (where cost is 0, 1, 2, 3, or 4 based on tier)

**Class names:**
- `OCMHeroBox(Static)` -- single box
- `OCMHeroMetrics(Horizontal)` -- container

**`update_data` signature:**
```python
def update_data(
    self,
    total_supply: int = 0,
    minted_pct: float = 0.0,
    holder_count: int = 0,
    avg_per_holder: float = 0.0,
    current_minting_cost_ocmd: float = 0.0,
    **_kwargs,
) -> None:
```

---

### WP-6: Staking Overview Widget (`dashboard/widgets/ocm/ocm_staking_overview.py`)

**Create:** `/Library/Vibes/autopull/dashboard/widgets/ocm/ocm_staking_overview.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/templates/two_column_table_template.py` (layout concept, but simpler -- just Static rows in a Vertical)

Key-value table using Static widgets in a Vertical. Not a DataTable -- just formatted text rows.

**Class name:** `OCMStakingOverview(Vertical)`

**Rows:**
- "Total Staked" : `"{staked} / {net_supply} ({ratio:.0f}%)"`
- "$OCMD Supply" : `"{ocmd_supply:,.0f}"`
- "Daily Emission" : `"{emission:,.0f} $OCMD"`
- "Days to Earn Mint" : `"{days:.1f} days"`
- "Burned / Remaining" : `"{burned:,} / {remaining:,}"`

**Structure:**
```python
class OCMStakingOverview(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("STAKING OVERVIEW", classes="overview-title")
        yield Static("", id="ocm-staking-spacer")
        yield Static("[dim]Loading...[/]", classes="overview-row", id="ocm-stake-row-0")
        yield Static("", classes="overview-row", id="ocm-stake-row-1")
        yield Static("", classes="overview-row", id="ocm-stake-row-2")
        yield Static("", classes="overview-row", id="ocm-stake-row-3")
        yield Static("", classes="overview-row", id="ocm-stake-row-4")
```

**`update_data` signature:**
```python
def update_data(
    self,
    total_staked: int = 0,
    net_supply: int = 0,
    staking_ratio: float = 0.0,
    ocmd_total_supply: float = 0.0,
    daily_emission: float = 0.0,
    days_to_earn_mint: float = 0.0,
    burned_count: int = 0,
    remaining: int = 0,
    **_kwargs,
) -> None:
```

**CSS class names for the TCSS file:**
- `OCMStakingOverview` -- main container
- `.overview-title` -- title styling
- `.overview-row` -- row styling

---

### WP-7: Sparklines Widget (`dashboard/widgets/ocm/ocm_sparklines.py`)

**Create:** `/Library/Vibes/autopull/dashboard/widgets/ocm/ocm_sparklines.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_sparklines.py`

Copy the Cat Town sparklines widget almost verbatim. Change:
- Class name: `CTSparklines` -> `OCMSparklines`
- Title: `"CAT TOWN TRENDS"` -> `"TRENDS (1h)"`
- Element IDs: `ct-chart-*` -> `ocm-chart-*`
- Series labels: change to "Supply", "Staked", "$OCMD"
- Colors: "green", "cyan", "yellow" (same as Cat Town, works fine)
- Units: no unit suffix for Supply/Staked (just counts), no unit for $OCMD

**`update_data` signature:**
```python
def update_data(
    self,
    supply_history: list[tuple[float, float]] | None = None,
    staked_history: list[tuple[float, float]] | None = None,
    ocmd_supply_history: list[tuple[float, float]] | None = None,
    **_kwargs,
) -> None:
```

Copy `_build_sparkline`, `_trend_arrow`, `_fmt_value` helper functions from the Cat Town file. They are generic.

---

### WP-8: Signals Widget (`dashboard/widgets/ocm/ocm_signals.py`)

**Create:** `/Library/Vibes/autopull/dashboard/widgets/ocm/ocm_signals.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_signals.py`

Copy the Cat Town signals widget structure. Change:
- Class name: `CTSignals` -> `OCMSignals`
- Element IDs: `ct-sig-*` -> `ocm-sig-*`
- Signal rows: 3 signals (staking, mint velocity, burn rate) + recommendation

**Compose yields:**
```python
yield Static("SIGNALS", classes="signals-title")
yield Static("", id="ocm-sig-spacer")
yield Static("[dim]  Loading...[/]", classes="signals-body", id="ocm-sig-staking")
yield Static("", classes="signals-body", id="ocm-sig-velocity")
yield Static("", classes="signals-body", id="ocm-sig-burns")
yield Static("", id="ocm-sig-spacer-2")
yield Static("", classes="signals-rec", id="ocm-sig-recommendation")
```

**`update_data` signature:**
```python
def update_data(
    self,
    staking_signal: dict | None = None,
    mint_velocity_signal: dict | None = None,
    burn_rate_signal: dict | None = None,
    recommendation: str = "",
    **_kwargs,
) -> None:
```

Reuse the `_fmt` helper from Cat Town signals (same format: `"  [{color}]{indicator}[/] [dim]{label:<15}[/] [{color}]{value}[/]"`).

---

### WP-9: Activity Feed Widget (`dashboard/widgets/ocm/ocm_activity_feed.py`)

**Create:** `/Library/Vibes/autopull/dashboard/widgets/ocm/ocm_activity_feed.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_activity_feed.py`

Copy the Cat Town activity feed structure. Change:
- Class name: `CTActivityFeed` -> `OCMActivityFeed`
- Element IDs: `ct-activity-log` -> `ocm-activity-log`
- Title: `"FISHING ACTIVITY"` -> `"ACTIVITY FEED"`
- Event formatting: instead of fish catches, format OCM events

**Event formatting function `_event_to_markup(event: dict) -> str`:**

```
  {HH:MM}  {TYPE}  {address}  {description}
```

Event type colors and descriptions:
- `mint` (green): `"Minted Monster #{tokenId}"`
- `burn` (red): `"Sacrificed Monster #{tokenId}"`
- `stake` (cyan): `"Staked {count} monster(s)"`
- `unstake` (yellow): `"Unstaked {count} monster(s)"`

**`update_data` signature:**
```python
def update_data(
    self,
    recent_events: list[dict] | None = None,
    **_kwargs,
) -> None:
```

De-duplicate by `tx_hash` (same pattern as Cat Town).

---

### WP-10: Supply Breakdown Widget (`dashboard/widgets/ocm/ocm_supply_breakdown.py`)

**Create:** `/Library/Vibes/autopull/dashboard/widgets/ocm/ocm_supply_breakdown.py`
**Pattern:** None -- new widget, but use `Vertical` + `Static` pattern from other widgets.

Simple Static-based widget showing supply numbers and an ASCII progress bar.

**Class name:** `OCMSupplyBreakdown(Vertical)`

**Display:**
```
SUPPLY BREAKDOWN

Minted:     4,084
Burned:       312
Net Supply: 3,772
Remaining:  5,916
[=========>            ] 40.8%
```

**Implementation:**
```python
class OCMSupplyBreakdown(Vertical):
    DEFAULT_CSS = """
    OCMSupplyBreakdown > .breakdown-title { ... }
    OCMSupplyBreakdown > .breakdown-body { ... }
    """

    def compose(self) -> ComposeResult:
        yield Static("SUPPLY BREAKDOWN", classes="breakdown-title")
        yield Static("", id="ocm-breakdown-spacer")
        yield Static("[dim]Loading...[/]", classes="breakdown-body", id="ocm-breakdown-stats")
        yield Static("", classes="breakdown-body", id="ocm-breakdown-bar")

    def update_data(
        self,
        total_supply: int = 0,
        burned_count: int = 0,
        net_supply: int = 0,
        remaining: int = 0,
        minted_pct: float = 0.0,
        **_kwargs,
    ) -> None:
```

**Progress bar logic:**
```python
bar_width = 30
filled = int(minted_pct / 100 * bar_width)
bar = "=" * filled + ">" + " " * (bar_width - filled - 1)
bar_str = f"[{bar}] {minted_pct:.1f}%"
```

---

## Wave 2: Dependent on Wave 1

### WP-11: Widget `__init__.py` (`dashboard/widgets/ocm/__init__.py`)

**Create:** `/Library/Vibes/autopull/dashboard/widgets/ocm/__init__.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/widgets/cattown/__init__.py`
**Depends on:** WP-5, WP-6, WP-7, WP-8, WP-9, WP-10

```python
"""OCM dashboard widgets."""

from .ocm_hero_metrics import OCMHeroMetrics
from .ocm_staking_overview import OCMStakingOverview
from .ocm_sparklines import OCMSparklines
from .ocm_signals import OCMSignals
from .ocm_activity_feed import OCMActivityFeed
from .ocm_supply_breakdown import OCMSupplyBreakdown

__all__ = [
    "OCMHeroMetrics",
    "OCMStakingOverview",
    "OCMSparklines",
    "OCMSignals",
    "OCMActivityFeed",
    "OCMSupplyBreakdown",
]
```

---

### WP-12: Manager (`dashboard/data/ocm_manager.py`)

**Create:** `/Library/Vibes/autopull/dashboard/data/ocm_manager.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/data/cattown_manager.py`
**Depends on:** WP-1 (models), WP-2 (client), WP-3 (cache), WP-4 (signals)

Orchestrates client, cache, and signals. Returns a flat dict for widget consumption.

**Class structure:**
```python
class OCMManager:
    def __init__(self, poll_interval: int = 60) -> None:
        self.client = OCMClient()
        self.cache = OCMCache(max_history=120)
        self._poll_interval = poll_interval
        self._error_count = 0
        # Load persisted cache
        self.cache.load_from_file(str(_CACHE_FILE))

    async def fetch_and_compute(self) -> dict[str, Any]: ...
    def save_cache(self) -> None: ...
    async def close(self) -> None: ...
```

**`fetch_and_compute()` return dict:**
```python
{
    # Hero metrics
    "total_supply": int,
    "minted_pct": float,
    "holder_count": int,
    "avg_per_holder": float,
    "current_minting_cost_ocmd": float,
    # Staking overview
    "total_staked": int,
    "net_supply": int,
    "staking_ratio": float,
    "ocmd_total_supply": float,
    "daily_emission": float,
    "days_to_earn_mint": float,
    "burned_count": int,
    "remaining": int,
    # Sparklines
    "supply_history": list[tuple[float, float]],
    "staked_history": list[tuple[float, float]],
    "ocmd_supply_history": list[tuple[float, float]],
    # Signals
    "staking_signal": dict,
    "mint_velocity_signal": dict,
    "burn_rate_signal": dict,
    "recommendation": str,
    # Activity feed
    "recent_events": list[dict],
    # Supply breakdown (same keys as hero, reused)
    # Meta
    "last_updated_seconds_ago": float,
    "error_count": int,
    "poll_interval": int,
}
```

**Implementation flow in `fetch_and_compute`:**
1. Call `self.client.fetch_snapshot()` (raises on failure, increment `_error_count`)
2. Update cache: `self.cache.update(snapshot)`
3. Compute derived values:
   - `avg_per_holder = snapshot.collection.net_supply / max(1, snapshot.holder_count)`
   - `current_minting_cost_ocmd = snapshot.collection.current_minting_cost / 10**18`
4. Get histories from cache
5. Compute signals using `_safe_call` wrapper (same pattern as Cat Town manager):
   - `generate_staking_signal(snapshot.staking.staking_ratio)`
   - `generate_mint_velocity_signal(compute_mint_velocity(supply_history))`
   - `generate_burn_rate_signal(compute_burn_rate(...))`
   - `generate_recommendation(...)`
6. Format recent_events as list of dicts
7. Assemble and return flat dict

Use the `_safe_call` helper pattern from Cat Town manager for all analytics calls.

---

### WP-13: Screen (`dashboard/screens/ocm.py`)

**Create:** `/Library/Vibes/autopull/dashboard/screens/ocm.py`
**Pattern:** `/Library/Vibes/autopull/dashboard/screens/cattown.py`
**Depends on:** WP-11 (widget exports), WP-12 (manager)

Follow the Cat Town screen almost exactly. Changes:
- Class name: `CatTownScreen` -> `OCMScreen`
- Import from `dashboard.widgets.ocm` instead of `dashboard.widgets.cattown`
- Import `OCMManager` instead of `CatTownManager`
- Poll interval: 60 seconds (passed via constructor)
- Worker name: `"ocm-refresh"`

**`compose()` method:**
```python
def compose(self) -> ComposeResult:
    yield Static("Onchain Monsters \u00b7 Collection Analytics", id="title-bar")
    yield OCMHeroMetrics()
    with Horizontal(id="middle-row"):
        yield OCMStakingOverview()
        with Vertical(id="right-col"):
            yield OCMSparklines()
            yield OCMSignals()
    yield Static("\u2500" * 300, id="separator")
    with Horizontal(id="bottom-row"):
        yield OCMActivityFeed()
        yield OCMSupplyBreakdown()
    yield StatusBar()
```

**`_do_refresh()` method:**
Update each widget via `query_one` + `update_data`, wrapped in try/except, same pattern as Cat Town. Map the flat dict keys to each widget's `update_data` kwargs.

**Widget update mapping:**
- `OCMHeroMetrics.update_data(total_supply=, minted_pct=, holder_count=, avg_per_holder=, current_minting_cost_ocmd=)`
- `OCMStakingOverview.update_data(total_staked=, net_supply=, staking_ratio=, ocmd_total_supply=, daily_emission=, days_to_earn_mint=, burned_count=, remaining=)`
- `OCMSparklines.update_data(supply_history=, staked_history=, ocmd_supply_history=)`
- `OCMSignals.update_data(staking_signal=, mint_velocity_signal=, burn_rate_signal=, recommendation=)`
- `OCMActivityFeed.update_data(recent_events=)`
- `OCMSupplyBreakdown.update_data(total_supply=, burned_count=, net_supply=, remaining=, minted_pct=)`
- `StatusBar.update_data(last_updated_seconds_ago=, error_count=, poll_interval=)`

**Keybinding:** `r` for manual refresh (same as Cat Town).

**`on_screen_resume`:** Set status bar game name to `"onchain monsters"`.

---

## Wave 3: Integration (sequential, depends on Wave 2)

### WP-14: App Integration (`dashboard/app.py`, `dashboard/screens/game_select.py`, `dashboard/__main__.py`)

**Modify:** 3 existing files
**Pattern:** Follow how `cattown` was added (visible in current git diff)
**Depends on:** WP-12 (manager), WP-13 (screen)

#### `dashboard/app.py`

1. Add imports:
   ```python
   from dashboard.data.ocm_manager import OCMManager
   from dashboard.screens.ocm import OCMScreen
   ```

2. In `__init__`, add:
   ```python
   self._ocm_manager = OCMManager(poll_interval=poll_interval)
   ```

3. In `on_mount`, add prefetch branch:
   ```python
   elif self._initial_game == "ocm":
       self.run_worker(
           self._ocm_manager.fetch_and_compute(),
           exclusive=True,
           name="prefetch",
       )
   ```

4. Add `"ocm"` to `_GAME_CYCLE`:
   ```python
   _GAME_CYCLE = ["bakery", "frenpet", "base", "cattown", "ocm"]
   ```

5. In `_launch_game`, add:
   ```python
   elif game_id == "ocm":
       if not self.is_screen_installed("ocm"):
           self.install_screen(
               OCMScreen(self._ocm_manager, self.poll_interval, name="ocm"),
               name="ocm",
           )
   ```

6. In `action_quit`, add:
   ```python
   try:
       await self._ocm_manager.close()
   except Exception as exc:
       logger.warning("Error during ocm shutdown: %s", exc)
   ```

#### `dashboard/screens/game_select.py`

Add OCM to the `GAMES` list:
```python
("5", "ocm", "Onchain Monsters", "NFT staking, $OCMD rewards on Ethereum"),
```

#### `dashboard/__main__.py`

Add `"ocm"` to `--game` choices:
```python
choices=["bakery", "frenpet", "base", "cattown", "ocm"],
```

---

### WP-15: CSS Rules (`dashboard/themes/minimal.tcss`)

**Modify:** `/Library/Vibes/autopull/dashboard/themes/minimal.tcss`
**Pattern:** Cat Town CSS block at the end of the file (lines 686-766)
**Depends on:** WP-5 through WP-10 (widget class names must be finalized)

Add a new section at the end of the file, before any trailing whitespace:

```css
/* -- Onchain Monsters screen -------------------------------------------- */

OCMHeroMetrics {
    height: 7;
    padding: 0 1;
    margin: 1 0 0 0;
}

OCMHeroBox {
    width: 1fr;
    height: 7;
    border: solid $panel;
    padding: 1 2;
    content-align: center middle;
    text-align: center;
    background: $surface;
    margin: 0 1;
}

OCMStakingOverview {
    width: 3fr;
    padding: 0 1;
}

OCMStakingOverview > .overview-title {
    color: $text-muted;
    padding: 0 1;
    text-style: bold;
    margin: 0 0 1 0;
}

OCMStakingOverview > .overview-row {
    padding: 0 1;
    width: 100%;
}

OCMSparklines {
    height: auto;
    padding: 0 1;
    content-align: center top;
}

OCMSparklines > .chart-title {
    color: $text-muted;
}

OCMSignals {
    height: 1fr;
    padding: 0 1;
    margin: 1 0 0 0;
    overflow-y: auto;
    content-align: center top;
}

OCMSignals > .signals-title {
    color: $text-muted;
}

OCMActivityFeed {
    width: 3fr;
    padding: 0 1;
}

OCMActivityFeed > .feed-title {
    color: $text-muted;
    margin: 0 0 1 0;
}

OCMActivityFeed RichLog {
    background: $background;
    scrollbar-size: 1 1;
}

OCMSupplyBreakdown {
    width: 2fr;
    padding: 0 1;
    content-align: center top;
}

OCMSupplyBreakdown > .breakdown-title {
    color: $text-muted;
    padding: 0 1;
    text-style: bold;
    margin: 0 0 1 0;
}

OCMSupplyBreakdown > .breakdown-body {
    padding: 0 1;
    width: 100%;
}
```

---

## File Summary

### New files (13):
| File | WP | Wave |
|------|----|------|
| `dashboard/data/ocm_models.py` | WP-1 | 1 |
| `dashboard/data/ocm_client.py` | WP-2 | 1 |
| `dashboard/data/ocm_cache.py` | WP-3 | 1 |
| `dashboard/analytics/ocm_signals.py` | WP-4 | 1 |
| `dashboard/widgets/ocm/ocm_hero_metrics.py` | WP-5 | 1 |
| `dashboard/widgets/ocm/ocm_staking_overview.py` | WP-6 | 1 |
| `dashboard/widgets/ocm/ocm_sparklines.py` | WP-7 | 1 |
| `dashboard/widgets/ocm/ocm_signals.py` | WP-8 | 1 |
| `dashboard/widgets/ocm/ocm_activity_feed.py` | WP-9 | 1 |
| `dashboard/widgets/ocm/ocm_supply_breakdown.py` | WP-10 | 1 |
| `dashboard/widgets/ocm/__init__.py` | WP-11 | 2 |
| `dashboard/data/ocm_manager.py` | WP-12 | 2 |
| `dashboard/screens/ocm.py` | WP-13 | 2 |

### Modified files (3):
| File | WP | Wave |
|------|----|------|
| `dashboard/app.py` | WP-14 | 3 |
| `dashboard/screens/game_select.py` | WP-14 | 3 |
| `dashboard/__main__.py` | WP-14 | 3 |
| `dashboard/themes/minimal.tcss` | WP-15 | 3 |

---

## Risks and Unknowns

1. **Function selector verification.** The `currentMintingCost()` and `isClosed()` selectors in WP-2 need keccak verification. If wrong, the client will get zero/garbage responses. The implementing agent should verify against Etherscan's verified ABI.

2. **Holder count.** No efficient on-chain method to get total unique holders. Options: (a) scan full Transfer history (expensive, slow first load), (b) scrape Etherscan page, (c) hardcode and periodically update. Recommend starting with approach (a) on first load with aggressive caching, falling back to 0 if it times out.

3. **Burned count accuracy.** If `totalSupply()` reflects burns (decrements on burn), then `burned = highest_ever_minted - totalSupply`. But we may not know `highest_ever_minted` without scanning. Starting with accumulation from observed events is safe but will undercount initially. The cache persistence helps across restarts.

4. **Staking detection.** The design spec says to detect staking by checking NFT Transfers to/from the OCMD contract address. This must be verified -- if staking uses a different mechanism (e.g., approval-based), the Transfer pattern will not work. Check the OCMD contract source on Etherscan.

5. **RPC rate limits.** `eth.merkle.io` is a free public RPC. At 60s poll intervals with ~8-10 serialized calls per poll, this should be fine. But event log scans over 500 blocks may be slow or rate-limited. The backoff retry logic handles this.

6. **CLAIM_END_TIME.** The technical findings mention `CLAIM_END_TIME: February 1, 2022`. This may mean staking rewards stopped accruing in 2022. If so, `daily_emission` would be 0 and the dashboard metrics around staking rewards would show stale data. The implementing agent should check if staking is still active by reading recent staking events.

---

## Validation Plan

1. **Unit test signals** -- Write tests for all 4 signal functions and the 2 compute functions in `tests/analytics/test_ocm_signals.py`. Pure functions, easy to test.

2. **Smoke test client** -- Run `OCMClient.fetch_snapshot()` against mainnet RPC and verify all fields are populated. Check that Transfer events are correctly classified as mint/burn/stake/unstake.

3. **Visual test** -- Launch `python -m dashboard --game ocm` and verify:
   - All 6 widgets render without errors
   - Hero metrics show non-zero supply
   - Sparklines populate after 2+ polls
   - Activity feed shows recent events (if any in last 500 blocks)
   - Tab cycling includes OCM
   - Game select screen shows OCM as option 5

4. **Error resilience** -- Set `MAXPANE_ETH_RPC_URL` to a bad URL, verify the dashboard shows loading states without crashing.
