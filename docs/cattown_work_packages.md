# Cat Town Fishing -- Work Packages

> Created: 2026-03-28
> Source: cattown_implementation_plan.md
> Total WPs: 10 across 3 waves

---

## Dependency Graph

```
Wave 1 (all start immediately, no dependencies):
  WP-1  ABI Discovery + Known ABIs
  WP-2  Static Data Tables + Conditions Analytics
  WP-3  Economy Analytics Module
  WP-4  Pydantic Models
  WP-5  Widget Scaffolds (all 6 widgets)

Wave 2 (depends on Wave 1 outputs):
  WP-6  RPC Client            <- WP-1 (ABIs), WP-4 (models)
  WP-7  Signal Generation     <- WP-2 (conditions), WP-3 (economy)
  WP-8  Cache + Manager       <- WP-4 (models), WP-6 (client), WP-7 (signals)

Wave 3 (final integration):
  WP-9  Screen + App Wiring   <- WP-5 (widgets), WP-8 (manager)
  WP-10 Full Test Suite       <- WP-6, WP-7, WP-8, WP-9
```

---

## Wave 1 -- All Start Immediately

---

## WP-1: ABI Discovery and Known ABI Files

**Agent type:** Research / scripting agent
**Dependencies:** None
**Wave:** 1
**Files to create:**
- `/Library/Vibes/autopull/dashboard/abis/cattown/kibble_token.json`
- `/Library/Vibes/autopull/dashboard/abis/cattown/sushi_v2_pair.json`
- `/Library/Vibes/autopull/dashboard/abis/cattown/kibble_oracle.json`
- `/Library/Vibes/autopull/dashboard/abis/cattown/fishing_game.json`
- `/Library/Vibes/autopull/dashboard/abis/cattown/competition.json`
- `/Library/Vibes/autopull/dashboard/abis/cattown/revenue_share.json`
- `/Library/Vibes/autopull/scripts/extract_cattown_abis.py`
- `/Library/Vibes/autopull/scripts/validate_cattown_abis.py`
**Files to modify:** None
**Files to read (patterns):** `/Library/Vibes/autopull/docs/cattown_technical_findings.md`

**Description:**

Part A -- Known ABIs (immediate, no extraction needed):
1. Create `dashboard/abis/cattown/` directory.
2. Write `kibble_token.json` with standard ERC-20 ABI (balanceOf, totalSupply, decimals, name, symbol, Transfer event). The KIBBLE token at `0x64cc19A52f4D631eF5BE07947CABA14aE00c52Eb` is verified on BaseScan.
3. Write `sushi_v2_pair.json` with standard UniswapV2 pair ABI (getReserves, token0, token1, totalSupply). Pool at `0x8e93c90503391427bff2a945b990c2192c0de6cf`.

Part B -- Frontend bundle extraction:
4. Write `scripts/extract_cattown_abis.py` that:
   - Fetches `https://cat.town` HTML
   - Finds `_next/static/chunks/*.js` script URLs
   - Downloads all chunks
   - Scans for ABI-shaped JSON arrays (patterns: `"inputs"`, `"outputs"`, `"stateMutability"`)
   - Extracts and saves candidate ABIs
   - Cross-references with known selectors (e.g. `0x71c9f256` for fishing)
5. Write `scripts/validate_cattown_abis.py` that:
   - For each extracted ABI + contract pair, makes a test `eth_call` to Base RPC (`https://mainnet.base.org`)
   - Validates KIBBLE Oracle (`0xE97B7ab01837A4CbF8ef75551a0f79b1116b3dc119ad9ccd`) returns a price
   - Validates Competition (`0x62a8F851AEB7d333e07445E59457eD150CEE2B7a`) returns data
   - Validates Revenue Share (`0x9e1Ced3b5130EBfff428eE0Ff471e4Df5383C0a1`) returns staking state
   - Prints pass/fail for each contract
6. Save validated ABIs as the final JSON files listed above.

Part C -- Fallback:
7. If frontend extraction fails for any contract, document which contracts failed and what selectors/events are still unknown. Update `docs/cattown_technical_findings.md` with findings.

**Acceptance criteria:**
- `dashboard/abis/cattown/` contains at least `kibble_token.json` and `sushi_v2_pair.json` with valid ABI arrays
- `scripts/extract_cattown_abis.py` runs without error and produces candidate ABI files
- `scripts/validate_cattown_abis.py` confirms at least one successful `eth_call` per target contract
- For any contract where ABI extraction fails, the failure is documented with next steps

---

## WP-2: Static Data Tables and Conditions Analytics

**Agent type:** Code generation agent
**Dependencies:** None
**Wave:** 1
**Files to create:**
- `/Library/Vibes/autopull/dashboard/analytics/cattown_conditions.py`
- `/Library/Vibes/autopull/tests/analytics/test_cattown_conditions.py`
**Files to modify:** None
**Files to read (patterns):**
- `/Library/Vibes/autopull/docs/cattown_game_mechanics.md` (source data for all tables)
- `/Library/Vibes/autopull/dashboard/analytics/signals.py` (analytics module pattern)
- `/Library/Vibes/autopull/dashboard/analytics/ev.py` (static catalog pattern -- see BOOST_CATALOG)

**Description:**

Create the conditions/fish/treasure analytics module. This is entirely static data plus UTC time logic -- no onchain reads needed.

1. Create `dashboard/analytics/cattown_conditions.py` with:
   - `get_time_of_day(utc_hour: int) -> str` -- Morning (6-11), Afternoon (12-17), Evening (18-23), Night (0-5)
   - `get_season(utc_month: int) -> str` -- Spring (3-5), Summer (6-8), Autumn (9-11), Winter (12,1,2)
   - `get_current_conditions() -> dict` -- returns `{"time_of_day": str, "season": str, "weather": "Unknown"}` from current UTC time
   - `FISH_TABLE: list[dict]` -- all 35 species from the game mechanics doc. Each entry: `{"name": str, "rarity": str, "weight_min": float, "weight_max": float, "condition_type": str, "condition_value": str}`. Use `condition_type` in `{"any", "season", "time_of_day", "weather"}` and `condition_value` as the specific value (e.g. "Spring", "Morning", "Storm").
   - `TREASURE_TABLE: list[dict]` -- all 33 treasures. Each entry: `{"name": str, "rarity": str, "value_min": float, "value_max": float, "condition_type": str, "condition_value": str}`.
   - `get_available_fish(conditions: dict) -> list[dict]` -- filter FISH_TABLE: include if condition_type is "any" OR condition matches current conditions
   - `get_available_treasures(conditions: dict) -> list[dict]` -- same logic for treasures
   - `is_legendary_window(conditions: dict) -> bool` -- True if any legendary fish's condition is met
   - `get_competition_timing() -> dict` -- returns `{"is_active": bool, "seconds_until_start": int, "seconds_until_end": int}` based on UTC weekday (Sat morning to Sun night)

2. Create `tests/analytics/test_cattown_conditions.py` with ~15 tests:
   - `test_time_of_day_morning` / `_afternoon` / `_evening` / `_night` (boundary values: 0, 5, 6, 11, 12, 17, 18, 23)
   - `test_season_spring` / `_summer` / `_autumn` / `_winter` (boundary months: 2, 3, 5, 6, 8, 9, 11, 12)
   - `test_fish_filter_any_always_included` -- Bluegill (Any condition) appears regardless
   - `test_fish_filter_specific_time` -- Oddball (Morning) appears only when time_of_day=Morning
   - `test_fish_filter_specific_season` -- Smallmouth Bass (Spring) appears only in Spring
   - `test_legendary_window_storm` -- Storm enables Elusive Marlin
   - `test_legendary_window_no_match` -- Sun alone does not enable any legendary
   - `test_competition_timing_saturday` -- is_active=True on Saturday
   - `test_competition_timing_wednesday` -- is_active=False on Wednesday
   - `test_fish_table_has_35_entries`
   - `test_treasure_table_has_33_entries`

**Acceptance criteria:**
- `FISH_TABLE` has exactly 35 entries matching the game mechanics doc
- `TREASURE_TABLE` has exactly 33 entries matching the game mechanics doc
- All 15 tests pass via `pytest tests/analytics/test_cattown_conditions.py`
- `get_available_fish({"time_of_day": "Morning", "season": "Spring", "weather": "Sun"})` returns a non-empty list including all "Any" fish plus Morning and Spring fish

---

## WP-3: Economy Analytics Module

**Agent type:** Code generation agent
**Dependencies:** None
**Wave:** 1
**Files to create:**
- `/Library/Vibes/autopull/dashboard/analytics/cattown_economy.py`
- `/Library/Vibes/autopull/tests/analytics/test_cattown_economy.py`
**Files to modify:** None
**Files to read (patterns):**
- `/Library/Vibes/autopull/dashboard/analytics/ev.py` (calculation pattern)
- `/Library/Vibes/autopull/dashboard/analytics/signals.py` (return dict pattern)
- `/Library/Vibes/autopull/docs/cattown_game_mechanics.md` (revenue split percentages)

**Description:**

Create economy analytics -- pure math functions, no onchain reads.

1. Create `dashboard/analytics/cattown_economy.py` with:
   - `calculate_burn_rate(burn_amounts: list[float], span_hours: float) -> float` -- total KIBBLE burned / span_hours. Returns 0.0 if span_hours <= 0.
   - `calculate_fishing_volume(catch_count: int, span_hours: float) -> float` -- casts per hour. Returns 0.0 if span_hours <= 0.
   - `calculate_prize_pool_growth(snapshots: list[tuple[float, float]], hours: float) -> float` -- KIBBLE added per hour based on (timestamp, amount) pairs. Returns 0.0 if < 2 snapshots.
   - `calculate_staking_apy(total_staked: float, weekly_revenue: float) -> float` -- `(weekly_revenue / total_staked) * 52 * 100` as percentage. Returns 0.0 if total_staked <= 0.
   - `calculate_kibble_burn_pct(burned: float, total_supply: float) -> float` -- `(burned / total_supply) * 100`. Returns 0.0 if total_supply <= 0.
   - `calculate_identification_ev(kibble_price_usd: float) -> dict` -- based on $0.25 cost, returns `{"cost_usd": float, "treasure_pool_share": float, "staker_share": float, "burn_share": float}` using the 70/10/10/7.5/2.5 revenue split.
   - `format_kibble(amount: float) -> str` -- "1.2M", "450K", "1,234" based on magnitude.

2. Create `tests/analytics/test_cattown_economy.py` with ~10 tests:
   - `test_burn_rate_normal` -- 1000 KIBBLE over 2 hours = 500/hr
   - `test_burn_rate_zero_span` -- returns 0.0
   - `test_burn_rate_empty_list` -- returns 0.0
   - `test_fishing_volume_normal` -- 60 casts over 2 hours = 30/hr
   - `test_staking_apy_normal` -- 1M staked, 10K weekly revenue = 52%
   - `test_staking_apy_zero_staked` -- returns 0.0
   - `test_burn_pct_normal` -- 553M burned of 1B = 55.3%
   - `test_burn_pct_zero_supply` -- returns 0.0
   - `test_format_kibble_millions` -- 1_200_000 -> "1.2M"
   - `test_format_kibble_thousands` -- 450_000 -> "450.0K"
   - `test_identification_ev_splits` -- verify revenue split percentages sum correctly

**Acceptance criteria:**
- All functions are pure (no I/O, no imports beyond stdlib)
- All ~10 tests pass via `pytest tests/analytics/test_cattown_economy.py`
- `format_kibble` handles values from 0 to 1B

---

## WP-4: Pydantic Models

**Agent type:** Code generation agent
**Dependencies:** None
**Wave:** 1
**Files to create:**
- `/Library/Vibes/autopull/dashboard/data/cattown_models.py`
**Files to modify:** None
**Files to read (patterns):**
- `/Library/Vibes/autopull/dashboard/data/frenpet_models.py` (frozen Pydantic model pattern, `from_raw()` classmethods)
- `/Library/Vibes/autopull/dashboard/data/models.py` (BakerySummary, ActivityEvent patterns)

**Description:**

Create all Pydantic models for Cat Town data. These define the data shapes consumed by the client, cache, manager, and widgets. No business logic -- just data containers.

1. Create `dashboard/data/cattown_models.py` with frozen Pydantic BaseModel subclasses:

   ```
   class KibbleEconomy(BaseModel):
       price_usd: float
       total_supply: float        # raw token units
       circulating: float
       burned: float
       staked_total: float
       price_change_24h: float    # percentage

   class CompetitionEntry(BaseModel):
       fisher_address: str
       fish_weight_kg: float
       fish_species: str
       rarity: str
       rank: int

   class CompetitionState(BaseModel):
       week_number: int
       is_active: bool
       prize_pool_kibble: float
       start_time: int            # unix timestamp
       end_time: int              # unix timestamp
       entries: list[CompetitionEntry]

   class FishCatch(BaseModel):
       tx_hash: str
       fisher_address: str
       species: str
       weight_kg: float
       rarity: str
       timestamp: int             # unix timestamp
       block_number: int

   class StakingState(BaseModel):
       total_staked: float
       user_staked: float
       pending_rewards: float
       weekly_revenue: float

   class CatTownSnapshot(BaseModel):
       fetched_at: float          # time.time()
       kibble: KibbleEconomy
       competition: CompetitionState
       recent_catches: list[FishCatch]
       staking: StakingState
   ```

2. Each model should be `model_config = ConfigDict(frozen=True)` following the frenpet pattern.
3. Add `from_raw()` classmethods where raw RPC data needs transformation (e.g., wei to float for KIBBLE amounts using 18 decimals).

**Acceptance criteria:**
- All 6 models are importable: `from dashboard.data.cattown_models import CatTownSnapshot, KibbleEconomy, CompetitionState, CompetitionEntry, FishCatch, StakingState`
- Models are frozen (immutable)
- A `CatTownSnapshot` can be constructed with sample data without error
- `from_raw()` classmethods exist for `KibbleEconomy` and `StakingState` (converting wei to float)

---

## WP-5: Widget Scaffolds (All 6 Widgets)

**Agent type:** Frontend / TUI agent
**Dependencies:** None
**Wave:** 1
**Files to create:**
- `/Library/Vibes/autopull/dashboard/widgets/cattown/__init__.py`
- `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_hero_metrics.py`
- `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_leaderboard.py`
- `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_sparklines.py`
- `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_signals.py`
- `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_activity_feed.py`
- `/Library/Vibes/autopull/dashboard/widgets/cattown/ct_best_plays.py`
**Files to modify:** None
**Files to read (patterns):**
- `/Library/Vibes/autopull/dashboard/templates/hero_metrics_template.py`
- `/Library/Vibes/autopull/dashboard/templates/leaderboard_template.py`
- `/Library/Vibes/autopull/dashboard/templates/sparkline_template.py`
- `/Library/Vibes/autopull/dashboard/templates/signals_template.py`
- `/Library/Vibes/autopull/dashboard/templates/activity_feed_template.py`
- `/Library/Vibes/autopull/dashboard/templates/two_column_table_template.py`
- `/Library/Vibes/autopull/dashboard/widgets/hero_metrics.py` (live example)
- `/Library/Vibes/autopull/dashboard/widgets/leaderboard.py` (live example)
- `/Library/Vibes/autopull/dashboard/widgets/cookie_chart.py` (sparkline example)
- `/Library/Vibes/autopull/dashboard/widgets/activity_feed.py` (live example)
- `/Library/Vibes/autopull/dashboard/widgets/signals_panel.py` (live example)
- `/Library/Vibes/autopull/dashboard/widgets/ev_table.py` (live example)

**Description:**

Build all 6 widgets by copying templates and adapting for Cat Town data shapes. Widgets accept data via `update_data()` kwargs -- they do NOT import models or analytics. They receive pre-computed primitives (strings, floats, lists of dicts).

1. **`ct_hero_metrics.py`** -- 3 hero boxes:
   - "KIBBLE PRICE": `$X.XXXX` with green/red 24h delta percentage
   - "COMPETITION": countdown timer or "LIVE" + prize pool in KIBBLE
   - "TOP FISHER": short address + weight in kg + species
   - `update_data(kibble_price_usd, kibble_change_24h, competition_state, top_fisher)`

2. **`ct_leaderboard.py`** -- DataTable:
   - Columns: #, Fisher, Best Fish, Weight (kg), Rarity
   - Short addresses (`0xABCD..1234`)
   - Weight right-aligned with 1 decimal
   - `update_data(competition_entries: list[dict])`

3. **`ct_sparklines.py`** -- 3 sparkline rows:
   - "KIBBLE Burn", "Fishing Volume", "Prize Pool"
   - Reuse `_build_sparkline()` from `cookie_chart.py` (copy the function)
   - `update_data(burn_rate_history, fishing_volume_history, prize_pool_history)`

4. **`ct_signals.py`** -- 5 signal rows:
   - Conditions, Legendary Window, Competition, Staking APY, KIBBLE Price
   - Each row: label + value + colored indicator dot
   - `update_data(condition_signal, legendary_signal, competition_signal, staking_signal, kibble_signal)`

5. **`ct_activity_feed.py`** -- RichLog:
   - Format: `HH:MM | 0xABCD | Caught Rainbow Trout (2.3kg) [Common]`
   - Color by rarity: Common=dim, Uncommon=white, Rare=cyan, Epic=magenta, Legendary=yellow
   - `update_data(recent_catches: list[dict])`

6. **`ct_best_plays.py`** -- two-column layout:
   - Left: "TOP FISH NOW" -- top 5 fish by max weight under current conditions
   - Right: "TOP TREASURES NOW" -- top 5 treasures by max value
   - Each row: name, weight/value range, rarity with color
   - `update_data(available_fish: list[dict], available_treasures: list[dict])`

7. **`__init__.py`** -- re-export all widget classes.

**Important:** All `update_data()` signatures must use simple types (str, float, int, list[dict], dict). Do NOT import Pydantic models in widget code. The screen layer does the unpacking.

**Acceptance criteria:**
- All 6 widget files exist and are importable
- `from dashboard.widgets.cattown import CTHeroMetrics, CTLeaderboard, CTSparklines, CTSignals, CTActivityFeed, CTBestPlays` works
- Each widget has a `compose()` method that yields Textual widgets
- Each widget has an `update_data()` method with the documented signature
- Widgets render placeholder text ("Loading...") in their default state
- No imports of `cattown_models`, `cattown_client`, or any analytics module

---

## Wave 2 -- Depends on Wave 1

---

## WP-6: RPC Client

**Agent type:** Backend / integration agent
**Dependencies:** WP-1 (ABIs), WP-4 (models)
**Wave:** 2
**Files to create:**
- `/Library/Vibes/autopull/dashboard/data/cattown_client.py`
- `/Library/Vibes/autopull/tests/data/test_cattown_client.py`
**Files to modify:** None
**Files to read (patterns):**
- `/Library/Vibes/autopull/dashboard/data/frenpet_client.py` (httpx async client pattern, retry logic, `eth_call` encoding)
- `/Library/Vibes/autopull/dashboard/data/client.py` (bakery client pattern)
- `/Library/Vibes/autopull/dashboard/abis/cattown/` (all ABI files from WP-1)
- `/Library/Vibes/autopull/dashboard/data/cattown_models.py` (from WP-4)

**Description:**

Create the async RPC client that reads Cat Town contract state from Base chain.

1. Create `dashboard/data/cattown_client.py` with class `CatTownClient`:
   - Constructor: `__init__(self, rpc_url: str = "https://mainnet.base.org")` -- creates `httpx.AsyncClient`, loads ABIs from `dashboard/abis/cattown/`
   - Uses the retry pattern from `FrenPetClient`: `_MAX_RETRIES = 3`, `_BACKOFF_SECONDS = (1.0, 2.0, 4.0)`, `_REQUEST_TIMEOUT = 15.0`
   - Internal helper `_eth_call(to, data) -> str` for raw RPC calls
   - Internal helper `_eth_get_logs(address, topics, from_block, to_block) -> list[dict]` for event queries

   Methods:
   - `get_kibble_price() -> float` -- call KIBBLE Oracle `latestAnswer` (or fall back to DEX pool reserves calculation)
   - `get_kibble_stats() -> KibbleEconomy` -- `totalSupply()` + `balanceOf(0x0...dead)` for burned + Oracle for price
   - `get_competition_state() -> CompetitionState` -- read from Competition contract (use extracted ABI functions)
   - `get_competition_leaderboard() -> list[CompetitionEntry]` -- read top entries from Competition contract or parse events
   - `get_recent_catches(block_range: int = 200) -> list[FishCatch]` -- parse Fishing Game events from last N blocks
   - `get_staking_state() -> StakingState` -- read from Revenue Share contract
   - `fetch_snapshot() -> CatTownSnapshot` -- orchestrates all methods with `asyncio.gather()` for parallelism
   - `close() -> None` -- close httpx client

   ABI encoding: encode function calls manually using `eth_abi` or inline hex (matching existing client patterns). Decode return values similarly.

2. Create `tests/data/test_cattown_client.py` with ~8 tests:
   - Mock httpx responses for each method
   - `test_get_kibble_price_from_oracle` -- mock successful Oracle response
   - `test_get_kibble_price_fallback_to_dex` -- Oracle fails, DEX pool works
   - `test_get_kibble_stats` -- mock totalSupply + burned balance
   - `test_get_competition_state` -- mock Competition contract response
   - `test_get_recent_catches` -- mock event logs
   - `test_get_staking_state` -- mock Revenue Share response
   - `test_fetch_snapshot_assembles_all` -- mock all calls, verify CatTownSnapshot
   - `test_rpc_failure_retries` -- verify retry behavior on 503

**Acceptance criteria:**
- `CatTownClient` is importable and constructable
- All methods return the correct Pydantic model types from WP-4
- `fetch_snapshot()` uses `asyncio.gather()` for parallel calls
- Tests pass with mocked RPC responses
- Retry logic matches the FrenPet pattern (3 retries, exponential backoff)

---

## WP-7: Signal Generation

**Agent type:** Code generation agent
**Dependencies:** WP-2 (conditions), WP-3 (economy)
**Wave:** 2
**Files to create:**
- `/Library/Vibes/autopull/dashboard/analytics/cattown_signals.py`
- `/Library/Vibes/autopull/tests/analytics/test_cattown_signals.py`
**Files to modify:** None
**Files to read (patterns):**
- `/Library/Vibes/autopull/dashboard/analytics/signals.py` (signal return format)
- `/Library/Vibes/autopull/dashboard/analytics/frenpet_signals.py` (signal generation pattern)
- `/Library/Vibes/autopull/dashboard/analytics/cattown_conditions.py` (from WP-2)
- `/Library/Vibes/autopull/dashboard/analytics/cattown_economy.py` (from WP-3)

**Description:**

Create signal generators that produce the dict format expected by `ct_signals.py` widget.

1. Create `dashboard/analytics/cattown_signals.py` with:

   Each function returns `{"label": str, "value_str": str, "indicator": str, "color": str}`.

   - `generate_condition_signal(conditions: dict) -> dict` -- shows current time-of-day + season. Color: always white (informational).
   - `generate_legendary_signal(conditions: dict) -> dict` -- "ACTIVE: [fish names]" (green) or "None available" (dim). Uses `is_legendary_window()` and `get_available_fish()` from WP-2, filtered to legendary only.
   - `generate_competition_signal(is_active: bool, seconds_remaining: int, prize_pool_kibble: float) -> dict` -- "LIVE" (yellow) with prize pool, or countdown to next start (dim).
   - `generate_staking_signal(apy: float, kibble_price_change: float) -> dict` -- APY value with color: green if > 20%, yellow if 5-20%, dim if < 5%.
   - `generate_kibble_signal(price_usd: float, change_24h: float) -> dict` -- price with green/red delta.

2. Create `tests/analytics/test_cattown_signals.py` with ~10 tests:
   - `test_condition_signal_format` -- verify all 4 keys present
   - `test_legendary_signal_active` -- Storm conditions show Elusive Marlin
   - `test_legendary_signal_inactive` -- Sun/Morning shows "None available"
   - `test_competition_signal_live` -- is_active=True returns yellow
   - `test_competition_signal_countdown` -- is_active=False returns dim
   - `test_staking_signal_high_apy` -- 25% APY returns green
   - `test_staking_signal_low_apy` -- 3% APY returns dim
   - `test_kibble_signal_positive` -- +5% change returns green
   - `test_kibble_signal_negative` -- -3% change returns red
   - `test_kibble_signal_zero_change` -- 0% returns white

**Acceptance criteria:**
- All signal functions return dicts with keys: `label`, `value_str`, `indicator`, `color`
- Color values are valid Rich markup color names: "green", "red", "yellow", "dim", "white"
- All 10 tests pass via `pytest tests/analytics/test_cattown_signals.py`

---

## WP-8: Cache and Data Manager

**Agent type:** Backend agent
**Dependencies:** WP-4 (models), WP-6 (client), WP-7 (signals)
**Wave:** 2
**Files to create:**
- `/Library/Vibes/autopull/dashboard/data/cattown_cache.py`
- `/Library/Vibes/autopull/dashboard/data/cattown_manager.py`
- `/Library/Vibes/autopull/tests/data/test_cattown_cache.py`
- `/Library/Vibes/autopull/tests/data/test_cattown_manager.py`
**Files to modify:** None
**Files to read (patterns):**
- `/Library/Vibes/autopull/dashboard/data/frenpet_cache.py` (cache pattern: deque, max_history, save/load)
- `/Library/Vibes/autopull/dashboard/data/frenpet_manager.py` (manager pattern: _safe_call, fetch_and_compute, flat dict return)
- `/Library/Vibes/autopull/dashboard/data/manager.py` (bakery manager pattern)
- `/Library/Vibes/autopull/dashboard/data/cattown_models.py` (from WP-4)
- `/Library/Vibes/autopull/dashboard/data/cattown_client.py` (from WP-6)
- `/Library/Vibes/autopull/dashboard/analytics/cattown_signals.py` (from WP-7)
- `/Library/Vibes/autopull/dashboard/analytics/cattown_conditions.py` (from WP-2)
- `/Library/Vibes/autopull/dashboard/analytics/cattown_economy.py` (from WP-3)

**Description:**

Part A -- Cache:

1. Create `dashboard/data/cattown_cache.py` with class `CatTownCache`:
   - Constructor: `__init__(self, max_history: int = 120)`
   - Tracks 4 time-series as `deque[tuple[float, float]]` (timestamp, value):
     - KIBBLE price history
     - Fishing volume per hour
     - Burn rate per hour
     - Prize pool KIBBLE
   - `update(snapshot: CatTownSnapshot) -> None` -- append new data points
   - `get_price_history() -> list[tuple[float, float]]`
   - `get_volume_history() -> list[tuple[float, float]]`
   - `get_burn_history() -> list[tuple[float, float]]`
   - `get_prize_pool_history() -> list[tuple[float, float]]`
   - `save_to_file(path: str) -> None` / `load_from_file(path: str) -> None` -- JSON persistence
   - Persistence path: `~/.maxpane/cattown_cache.json`

Part B -- Manager:

2. Create `dashboard/data/cattown_manager.py` with class `CatTownManager`:
   - Constructor: `__init__(self, poll_interval: int = 30)`
   - Creates `CatTownClient` and `CatTownCache`
   - Loads cache from `~/.maxpane/cattown_cache.json` on init

   `async fetch_and_compute() -> dict[str, Any]`:
   - Calls `client.fetch_snapshot()`
   - Updates cache
   - Computes all analytics using `_safe_call()` pattern (never crash on analytics failure)
   - Returns flat dict with ALL keys needed by ALL widgets:

     ```python
     {
         # Hero metrics (ct_hero_metrics.py)
         "kibble_price_usd": float,
         "kibble_change_24h": float,
         "competition_state": {"is_active": bool, "seconds_remaining": int, "prize_pool_kibble": float},
         "top_fisher": {"address": str, "weight_kg": float, "species": str} | None,

         # Leaderboard (ct_leaderboard.py)
         "competition_entries": list[dict],  # dicts with fisher_address, fish_weight_kg, fish_species, rarity, rank

         # Sparklines (ct_sparklines.py)
         "burn_rate_history": list[tuple[float, float]],
         "fishing_volume_history": list[tuple[float, float]],
         "prize_pool_history": list[tuple[float, float]],

         # Signals (ct_signals.py)
         "condition_signal": dict,
         "legendary_signal": dict,
         "competition_signal": dict,
         "staking_signal": dict,
         "kibble_signal": dict,

         # Best plays (ct_best_plays.py)
         "available_fish": list[dict],
         "available_treasures": list[dict],

         # Activity feed (ct_activity_feed.py)
         "recent_catches": list[dict],  # dicts with tx_hash, fisher_address, species, weight_kg, rarity, timestamp

         # Meta (status_bar)
         "error_count": int,
         "last_updated_seconds_ago": float,
         "poll_interval": int,
     }
     ```

   - `save_cache() -> None`
   - `async close() -> None` -- save cache + close client

Part C -- Tests:

3. `tests/data/test_cattown_cache.py` (~6 tests):
   - `test_update_appends_history` -- verify deque grows
   - `test_max_history_enforced` -- verify old entries are dropped
   - `test_persistence_roundtrip` -- save then load, verify data preserved
   - `test_load_nonexistent_file` -- no crash, empty state
   - `test_get_price_history_returns_list` -- verify return type
   - `test_empty_cache_returns_empty_lists`

4. `tests/data/test_cattown_manager.py` (~5 tests):
   - `test_fetch_and_compute_returns_all_keys` -- mock client, verify all expected keys present
   - `test_fetch_and_compute_types` -- verify value types for key fields
   - `test_error_count_increments_on_failure` -- mock client exception
   - `test_safe_call_returns_default_on_error` -- verify analytics failure is swallowed
   - `test_close_saves_cache` -- verify cache persistence called

**Acceptance criteria:**
- `CatTownManager().fetch_and_compute()` returns a dict with all keys listed above
- Cache persists and loads correctly from `~/.maxpane/cattown_cache.json`
- Analytics failures are caught by `_safe_call()` and do not crash the manager
- All 11 tests pass

---

## Wave 3 -- Final Integration

---

## WP-9: Screen Assembly and App Wiring

**Agent type:** Frontend / integration agent
**Dependencies:** WP-5 (widgets), WP-8 (manager)
**Wave:** 3
**Files to create:**
- `/Library/Vibes/autopull/dashboard/screens/cattown.py`
**Files to modify:**
- `/Library/Vibes/autopull/dashboard/app.py`
- `/Library/Vibes/autopull/dashboard/__main__.py`
- `/Library/Vibes/autopull/dashboard/screens/game_select.py`
**Files to read (patterns):**
- `/Library/Vibes/autopull/dashboard/screens/bakery.py` (screen pattern: compose, on_screen_resume, on_screen_suspend, _do_refresh)
- `/Library/Vibes/autopull/dashboard/templates/screen_template.py`
- `/Library/Vibes/autopull/dashboard/app.py` (current state)
- `/Library/Vibes/autopull/dashboard/__main__.py` (current state)
- `/Library/Vibes/autopull/dashboard/screens/game_select.py` (current state)

**Description:**

1. Create `dashboard/screens/cattown.py` with class `CatTownScreen(Screen)`:

   Layout (matching implementation plan wireframe):
   ```
   Static (title bar: "Cat Town Fishing . Competition Week X")
   CTHeroMetrics
   Horizontal:
     CTLeaderboard
     Vertical:
       CTSparklines
       CTSignals
   Static (separator: horizontal rule)
   Horizontal:
     CTActivityFeed
     CTBestPlays
   StatusBar
   ```

   Behavior (copy BakeryScreen pattern exactly):
   - `__init__(self, data_manager: CatTownManager, poll_interval: int, **kwargs)`
   - `BINDINGS = [Binding("r", "refresh", ...)]`
   - `on_screen_resume()` -- start timer + initial refresh + set status bar game name to "cat town fishing"
   - `on_screen_suspend()` -- stop timer
   - `_do_refresh()` -- `await manager.fetch_and_compute()`, then update each widget in individual try/except blocks
   - `action_refresh()` -- manual refresh via 'r' key

   Widget update calls in `_do_refresh()`:
   - `CTHeroMetrics.update_data(kibble_price_usd, kibble_change_24h, competition_state, top_fisher)`
   - `CTLeaderboard.update_data(competition_entries)`
   - `CTSparklines.update_data(burn_rate_history, fishing_volume_history, prize_pool_history)`
   - `CTSignals.update_data(condition_signal, legendary_signal, competition_signal, staking_signal, kibble_signal)`
   - `CTActivityFeed.update_data(recent_catches)`
   - `CTBestPlays.update_data(available_fish, available_treasures)`
   - `StatusBar.update_data(last_updated_seconds_ago, error_count, poll_interval)`

   Title bar updates with competition week number from `data["competition_state"]["week_number"]` if available.

2. Modify `dashboard/app.py`:
   - Add imports: `from dashboard.data.cattown_manager import CatTownManager` and `from dashboard.screens.cattown import CatTownScreen`
   - In `__init__`: add `self._cattown_manager = CatTownManager(poll_interval=poll_interval)`
   - Update `_GAME_CYCLE` to `["bakery", "frenpet", "base", "cattown"]`
   - In `on_mount`: add `elif self._initial_game == "cattown":` prefetch branch
   - In `_launch_game`: add `elif game_id == "cattown":` block that installs `CatTownScreen(self._cattown_manager, self.poll_interval, name="cattown")`
   - In `action_quit`: add `await self._cattown_manager.close()` in a try/except block

3. Modify `dashboard/__main__.py`:
   - Add `"cattown"` to `--game` choices list
   - Add `"cattown"` to `--theme` choices list (if applicable)

4. Modify `dashboard/screens/game_select.py`:
   - Add entry to `GAMES` list: `("4", "cattown", "Cat Town Fishing", "Fish, compete, stake KIBBLE on Base L2")`

**Acceptance criteria:**
- `python -m dashboard --game cattown` launches without import errors
- Tab key cycles through all 4 games including Cat Town
- Game select screen shows Cat Town as option 4
- CatTownScreen renders all 6 widgets in the correct layout
- Pressing 'r' triggers a manual refresh
- Timer-based refresh runs on the configured poll interval
- Status bar shows "cat town fishing" as the game name

---

## WP-10: Full Test Suite

**Agent type:** Testing agent
**Dependencies:** WP-6 (client), WP-7 (signals), WP-8 (manager), WP-9 (screen)
**Wave:** 3
**Files to create:** None (test files created in WP-2, WP-3, WP-6, WP-7, WP-8)
**Files to modify:**
- `/Library/Vibes/autopull/tests/analytics/test_cattown_conditions.py` (from WP-2 -- verify/fix)
- `/Library/Vibes/autopull/tests/analytics/test_cattown_economy.py` (from WP-3 -- verify/fix)
- `/Library/Vibes/autopull/tests/analytics/test_cattown_signals.py` (from WP-7 -- verify/fix)
- `/Library/Vibes/autopull/tests/data/test_cattown_client.py` (from WP-6 -- verify/fix)
- `/Library/Vibes/autopull/tests/data/test_cattown_cache.py` (from WP-8 -- verify/fix)
- `/Library/Vibes/autopull/tests/data/test_cattown_manager.py` (from WP-8 -- verify/fix)
**Files to read (patterns):**
- All test files in `/Library/Vibes/autopull/tests/` for existing test patterns (conftest, fixtures, mocking style)

**Description:**

Integration pass across ALL Cat Town test files to ensure:

1. Run `pytest tests/ -x` and fix any failures across the entire Cat Town test suite.
2. Verify no regressions in existing tests (bakery, frenpet, base).
3. Ensure import chains are correct (models -> client -> cache -> manager -> analytics).
4. Add any missing edge case tests discovered during integration.
5. Verify test count: target ~54 new tests across 6 test files.
6. Run `pytest tests/ --tb=short` for a clean full-suite report.

**Acceptance criteria:**
- `pytest tests/` passes with 0 failures
- All existing tests (bakery, frenpet, base) still pass
- Cat Town test count is >= 50
- No import errors in any Cat Town module
- `python -m dashboard --game cattown` launches without error (smoke test)

---

## Summary

| Wave | WP | Title | Agent Type | New Files | Est. Tests |
|------|----|-------|-----------|-----------|------------|
| 1 | WP-1 | ABI Discovery | Research | 8 | 0 |
| 1 | WP-2 | Conditions & Fish Tables | Code gen | 2 | 15 |
| 1 | WP-3 | Economy Analytics | Code gen | 2 | 10 |
| 1 | WP-4 | Pydantic Models | Code gen | 1 | 0 |
| 1 | WP-5 | Widget Scaffolds | Frontend | 7 | 0 |
| 2 | WP-6 | RPC Client | Backend | 2 | 8 |
| 2 | WP-7 | Signal Generation | Code gen | 2 | 10 |
| 2 | WP-8 | Cache + Manager | Backend | 4 | 11 |
| 3 | WP-9 | Screen + App Wiring | Integration | 1 (+3 mod) | 0 |
| 3 | WP-10 | Full Test Suite | Testing | 0 (+6 mod) | ~5 new |
| **Total** | | | | **29 new, 9 modified** | **~54** |

### Parallelism Analysis

- **Wave 1:** 5 agents can work simultaneously (WP-1 through WP-5)
- **Wave 2:** 3 agents can work simultaneously (WP-6, WP-7, WP-8 once dependencies land)
- **Wave 3:** 2 agents work sequentially (WP-9 then WP-10)
- **Critical path:** WP-1 -> WP-6 -> WP-8 -> WP-9 -> WP-10
