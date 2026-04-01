# Cat Town Fishing Dashboard -- Implementation Plan

> Created: 2026-03-28
> Mode: Deep (new game integration, unverified contracts, ABI risk)

---

## 1. Problem Statement

MaxPane supports 3 games (Bakery, FrenPet, Base Trading). We want to add Cat Town Fishing as a 4th game dashboard. The core challenge is that Cat Town contracts are UUPS proxies with unverified source on BaseScan, meaning there are no readily available ABIs. All game data must come from onchain reads and event log parsing, with ABI discovery as a gating prerequisite.

**Who is affected:** Dashboard users who play Cat Town Fishing and want real-time competition, economy, and condition visibility in their terminal.

**Success criteria:** A fully wired `cattown` screen in MaxPane with live data for KIBBLE price, competition leaderboard, fishing activity feed, condition-based signals, sparkline trends, and best-plays recommendations. All data updates on the standard 30-second poll cycle.

---

## 2. Known Facts

- **Chain:** Base (8453) -- same chain as FrenPet and Base Trading, so RPC infrastructure is shared
- **Contracts:** 8+ addresses identified (Fishing Game, Competition, Fish Raffle, KIBBLE, Revenue Share, Oracle, DEX Pool, Rods)
- **KIBBLE token:** Verified on BaseScan (full ABI available). ERC-20.
- **Other contracts:** UUPS proxies, source unverified. Implementation addresses known.
- **No public API:** No tRPC, REST, or GraphQL. Dashboard is onchain-only.
- **Frontend:** Next.js (wagmi/viem), which embeds ABIs in the bundle -- extractable.
- **Dominant fishing function selector:** `0x71c9f256` (from technical findings)
- **Competition:** Weekly Sat-Sun UTC, ranked by heaviest single fish
- **Conditions system:** Time-of-day (4 slots) x Weather (6 types) x Season (4 types) gates fish availability
- **Existing templates:** 8 widget templates ready for copy-paste adaptation
- **Existing pattern:** DataManager + Client + Cache + Analytics + Screen + Widgets

## 3. Constraints

- All data must come from onchain reads (eth_call) or event logs (eth_getLogs). No server API.
- ABI discovery is required before any contract interaction beyond KIBBLE token.
- Weather conditions may be server-determined or embedded in contract state -- unknown until ABI is extracted.
- The timing mini-game is client-side; we cannot observe or automate it. Dashboard is read-only.
- Must follow existing patterns: Pydantic models, httpx AsyncClient, DataCache, `fetch_and_compute()` returning flat dict.
- Must wire into app.py game cycle, game_select.py, and `__main__.py` CLI choices.

## 4. Key Unknowns

| Unknown | Impact | Mitigation |
|---------|--------|------------|
| Contract ABIs (Fishing Game, Competition, Revenue Share) | **Blocks all onchain reads** except KIBBLE and Oracle | Extract from frontend bundle or decompile implementations |
| Weather system source | Blocks condition/signal widgets | Start with time-of-day + season (deterministic from UTC); add weather later |
| Competition event format | Blocks leaderboard widget | Parse from Competition contract once ABI extracted |
| Fish identification event structure | Blocks activity feed and sparklines | Reconstruct from tx calldata + event topics |
| Staking APY calculation precision | Affects signal accuracy | Start with estimate from Revenue Share events; refine |
| Drop rate probabilities | Affects best-plays EV calculations | Use published weight ranges; omit drop rates initially |

## 5. ABI Discovery Strategy (Phase 0 -- Gates Everything)

### Option A: Frontend Bundle Extraction (Recommended)

1. Fetch `https://cat.town` HTML, find `_next/static/chunks/*.js` URLs
2. Download all chunk files, search for ABI arrays (look for `"inputs"`, `"outputs"`, `"stateMutability"` JSON patterns)
3. Match ABIs to known contract addresses by cross-referencing function selectors
4. Validate extracted ABIs by making test eth_call against known state

**Benefits:** Most complete ABIs with parameter names, event definitions, all functions.
**Risk:** Frontend may obfuscate or split ABIs across chunks. Medium effort.

### Option B: Decompile Proxy Implementations

1. Use Dedaub or Heimdall decompiler on implementation bytecode at known impl addresses
2. Reconstruct function signatures and event topics from decompiled output
3. Build minimal ABIs with only the functions/events needed for dashboard reads

**Benefits:** Works even if frontend changes. Direct from bytecode.
**Risk:** Decompiled names are synthetic (func_0x1234), events may be harder to parse. Higher effort.

### Option C: Transaction Calldata Reconstruction

1. Query BaseScan for recent transactions to each contract
2. Extract function selectors from calldata
3. Match against known 4-byte signatures (4byte.directory)
4. Build partial ABIs from matched signatures

**Benefits:** Quick for known common functions.
**Risk:** Only covers functions that have been called recently. Incomplete for read-only functions and events.

### Recommended approach: Option A first, fall back to Option B for any gaps.

### Minimum viable ABIs needed:

| Contract | Functions Needed | Events Needed |
|----------|-----------------|---------------|
| KIBBLE Token | `balanceOf`, `totalSupply`, `decimals` | `Transfer` (for burn tracking) |
| KIBBLE Oracle | `latestAnswer` or equivalent | -- |
| Competition | Leaderboard read, prize pool read | Competition entry, result events |
| Fishing Game | VRF fee read (if available) | Fish caught / identified events |
| Revenue Share | Total staked, user stake, pending rewards | Deposit, Withdraw, Claim events |
| DEX Pool | `getReserves` (Sushi v2 standard) | -- |

**KIBBLE Token and DEX Pool have known ABIs** (standard ERC-20 and UniV2 pair). These can be used immediately without extraction.

---

## 6. File Inventory (New Files)

```
dashboard/
  data/
    cattown_models.py          # Pydantic models: CatTownSnapshot, FishCatch, CompetitionEntry, etc.
    cattown_client.py          # RPC client: eth_call + eth_getLogs against Base chain
    cattown_cache.py           # Time-series cache for sparklines
    cattown_manager.py         # Orchestrator: fetch_and_compute() -> flat dict
  analytics/
    cattown_conditions.py      # UTC time -> time-of-day/season; fish/treasure availability tables
    cattown_economy.py         # Burn rate, staking APY, prize pool growth
    cattown_signals.py         # Signal generation: conditions, legendary window, competition, etc.
  widgets/
    cattown/
      __init__.py              # Re-exports all widgets
      ct_hero_metrics.py       # 3 hero cards
      ct_leaderboard.py        # Competition leaderboard (DataTable)
      ct_sparklines.py         # 3 sparkline charts
      ct_signals.py            # 5 signal rows
      ct_activity_feed.py      # Onchain event feed (RichLog)
      ct_best_plays.py         # 2-column: top fish + top treasures
  screens/
    cattown.py                 # CatTownScreen with compose + refresh wiring
  abis/
    cattown/
      kibble_token.json        # Standard ERC-20 (known)
      sushi_v2_pair.json       # Standard UniV2 pair (known)
      kibble_oracle.json       # Extracted ABI
      fishing_game.json        # Extracted ABI (partial)
      competition.json         # Extracted ABI (partial)
      revenue_share.json       # Extracted ABI (partial)
tests/
  analytics/
    test_cattown_conditions.py # Condition logic tests
    test_cattown_economy.py    # Burn rate, APY calculation tests
    test_cattown_signals.py    # Signal generation tests
  data/
    test_cattown_client.py     # Client with mocked RPC responses
    test_cattown_cache.py      # Cache time-series tests
    test_cattown_manager.py    # Integration test for fetch_and_compute
```

**Modified files:**
- `dashboard/app.py` -- add CatTownManager, CatTownScreen to imports, _GAME_CYCLE, _launch_game, action_quit
- `dashboard/__main__.py` -- add "cattown" to --game choices and --theme choices
- `dashboard/screens/game_select.py` -- add Cat Town entry to GAMES list

---

## 7. Implementation Phases

### Phase 0: ABI Discovery and Contract Interface (Days 1-2)

**Goal:** Extract working ABIs for the 4 non-standard contracts. Validate with test reads.

**Steps:**

0.1. **KIBBLE + DEX Pool ABIs** -- Create `dashboard/abis/cattown/` directory. Write standard ERC-20 ABI (`kibble_token.json`) and UniV2 pair ABI (`sushi_v2_pair.json`). These are known and need no extraction.

0.2. **Frontend bundle extraction script** -- Write `scripts/extract_cattown_abis.py`:
   - Fetch `https://cat.town` HTML
   - Parse `<script>` tags for `_next/static/chunks/*.js` URLs
   - Download all chunk files
   - Regex-scan for ABI-shaped JSON arrays (containing `"inputs"`, `"stateMutability"`)
   - Extract and save candidate ABIs to `dashboard/abis/cattown/`
   - Cross-reference with known selectors (e.g., `0x71c9f256`)

0.3. **Validate extracted ABIs** -- Write `scripts/validate_cattown_abis.py`:
   - For each extracted ABI + contract address pair, attempt an eth_call
   - Confirm KIBBLE Oracle returns a price
   - Confirm Competition contract returns leaderboard data
   - Confirm Fishing Game returns VRF fee or game state
   - Confirm Revenue Share returns staking totals

0.4. **Fallback: Decompile** -- If frontend extraction fails for any contract, use Dedaub/Heimdall on the implementation bytecodes (addresses listed in technical findings).

0.5. **Document discovered interfaces** -- Record which functions and events were found, with their selectors and parameter types. Update `docs/cattown_technical_findings.md` with the ABI findings.

**Exit criteria:** Can successfully call at least one read function on each of: KIBBLE Oracle, Competition, Fishing Game, Revenue Share. Have event topic hashes for fish identification and competition events.

**Risk:** If ABIs cannot be extracted, the entire project is blocked. Mitigation: fallback to decompilation + 4byte.directory lookup. Worst case: build a KIBBLE-token-and-DEX-only dashboard (price, supply, burn rate) and add contract-specific widgets incrementally as ABIs are discovered.

---

### Phase 1: Data Layer -- Models, Client, Cache (Days 2-3)

**Goal:** Build the data pipeline from RPC to structured Python objects.

**Steps:**

1.1. **Create `dashboard/data/cattown_models.py`** -- Pydantic models:
   ```
   CatTownSnapshot       -- top-level container (fetched_at, all sub-data)
   KibbleEconomy         -- price_usd, total_supply, circulating, burned, staked_total
   CompetitionState      -- week_number, is_active, prize_pool_kibble, start_time, end_time
   CompetitionEntry      -- fisher_address, fish_weight_kg, fish_species, rank
   FishCatch             -- tx_hash, fisher_address, species, weight_kg, rarity, timestamp
   StakingState          -- total_staked, user_staked, pending_rewards, last_payout
   ```
   Follow `frenpet_models.py` pattern: frozen Pydantic models, `from_raw()` classmethods.

1.2. **Create `dashboard/data/cattown_client.py`** -- Async RPC client:
   - `CatTownClient(rpc_url, abi_dir)` -- loads ABIs from JSON files
   - Uses `httpx.AsyncClient` with retry logic (same pattern as `FrenPetClient`)
   - Methods:
     - `get_kibble_price() -> float` -- Oracle or DEX pool reserves
     - `get_kibble_stats() -> KibbleEconomy` -- totalSupply, burned (from Transfer to 0x0 events)
     - `get_competition_state() -> CompetitionState` -- current week, active, prize pool
     - `get_competition_leaderboard() -> list[CompetitionEntry]` -- top 10
     - `get_recent_catches(block_range) -> list[FishCatch]` -- from event logs
     - `get_staking_state() -> StakingState` -- total staked, APY inputs
     - `get_burn_history(block_range) -> list[tuple[int, float]]` -- KIBBLE Transfer to 0x0
     - `fetch_snapshot() -> CatTownSnapshot` -- orchestrates all above
   - RPC URL: Use Base RPC (same as FrenPet: `https://mainnet.base.org` or Alchemy)
   - All contract interactions use raw `eth_call` via httpx (no web3.py dependency needed, matching existing pattern)

1.3. **Create `dashboard/data/cattown_cache.py`** -- Time-series cache:
   - Follow `frenpet_cache.py` pattern
   - Track: KIBBLE price history, fishing volume per hour, burn rate per hour, prize pool over time
   - `max_history=120` (same as other caches)
   - Persistence to `~/.maxpane/cattown_cache.json`

**Tests:**
- `tests/data/test_cattown_client.py` -- mock RPC responses, verify model construction
- `tests/data/test_cattown_cache.py` -- time-series insertion, retrieval, persistence

**Exit criteria:** `CatTownClient.fetch_snapshot()` returns a `CatTownSnapshot` with real data from Base mainnet.

---

### Phase 2: Static Data -- Conditions and Fish Tables (Day 3)

**Goal:** Encode the full fish/treasure availability tables and condition logic.

**Steps:**

2.1. **Create `dashboard/analytics/cattown_conditions.py`:**
   - `get_time_of_day(utc_hour: int) -> str` -- Morning (6-12), Afternoon (12-18), Evening (18-24), Night (0-6)
   - `get_season(utc_month: int) -> str` -- Spring (3-5), Summer (6-8), Autumn (9-11), Winter (12-2)
   - `get_current_conditions() -> dict` -- returns `{time_of_day, season, weather}` (weather TBD, default "Sun")
   - `FISH_TABLE: list[dict]` -- all 35 species with name, rarity, weight_min, weight_max, required_conditions
   - `TREASURE_TABLE: list[dict]` -- all 33 treasures with name, rarity, value_min, value_max, required_conditions
   - `get_available_fish(conditions: dict) -> list[dict]` -- filter FISH_TABLE by current conditions
   - `get_available_treasures(conditions: dict) -> list[dict]` -- filter TREASURE_TABLE by current conditions
   - `is_legendary_window(conditions: dict) -> bool` -- True if any legendary fish is available
   - `get_competition_timing() -> dict` -- returns `{is_active, seconds_until_start, seconds_until_end}` based on UTC day of week

**Data source:** The fish and treasure tables from `docs/cattown_game_mechanics.md` (already documented in full).

**Tests:**
- `tests/analytics/test_cattown_conditions.py`:
  - Time-of-day boundaries (edge cases: 0, 6, 12, 18, 23)
  - Season boundaries (edge cases: month 2, 3, 5, 6, 8, 9, 11, 12)
  - Fish filtering: "Any" condition matches always; specific conditions filter correctly
  - Legendary window detection for Storm, Heatwave, each season
  - Competition timing for each day of week

---

### Phase 3: Analytics Modules (Days 3-4)

**Goal:** Compute derived metrics consumed by widgets.

**Steps:**

3.1. **Create `dashboard/analytics/cattown_economy.py`:**
   - `calculate_burn_rate(burn_events: list, hours: float) -> float` -- KIBBLE burned per hour
   - `calculate_fishing_volume(catch_events: list, hours: float) -> float` -- casts per hour
   - `calculate_prize_pool_growth(prize_snapshots: list) -> float` -- KIBBLE added per hour
   - `calculate_staking_apy(total_staked: float, weekly_revenue: float) -> float` -- annualized yield
   - `calculate_kibble_burn_pct(burned: float, total_supply: float) -> float` -- cumulative burn %
   - `format_kibble(amount: float) -> str` -- human-readable with M/K suffixes

3.2. **Create `dashboard/analytics/cattown_signals.py`:**
   - `generate_condition_signal(conditions: dict) -> dict` -- label, color, detail
   - `generate_legendary_signal(conditions: dict) -> dict` -- green/red + which legendaries available
   - `generate_competition_signal(comp_state: CompetitionState) -> dict` -- countdown + prize pool
   - `generate_staking_signal(apy: float, kibble_price_delta_24h: float) -> dict` -- APY + price trend
   - `generate_kibble_signal(price: float, change_24h: float) -> dict` -- price + delta with color

3.3. **Signal color rules** (match existing pattern):
   - Legendary window active: green; inactive: dim
   - Staking APY > 20%: green; 5-20%: yellow; < 5%: dim
   - KIBBLE 24h change: green if positive, red if negative
   - Competition active: yellow ("LIVE"); countdown: dim with timer

**Tests:**
- `tests/analytics/test_cattown_economy.py` -- burn rate, volume, APY math, edge cases (zero division)
- `tests/analytics/test_cattown_signals.py` -- signal generation for each condition combination

---

### Phase 4: Data Manager (Day 4)

**Goal:** Wire client, cache, and analytics into single `fetch_and_compute()` method.

**Steps:**

4.1. **Create `dashboard/data/cattown_manager.py`:**
   - `CatTownManager(poll_interval, rpc_url?)` -- constructor creates CatTownClient, CatTownCache
   - `fetch_and_compute() -> dict[str, Any]` -- returns flat dict with all widget keys:
     ```
     # Hero metrics
     kibble_price_usd, kibble_change_24h,
     competition_state (dict with is_active, seconds_remaining, prize_pool),
     top_fisher (dict with address, weight, species),

     # Leaderboard
     competition_entries (list of CompetitionEntry),

     # Sparklines
     burn_rate_history, fishing_volume_history, prize_pool_history,

     # Signals
     condition_signal, legendary_signal, competition_signal,
     staking_signal, kibble_signal,

     # Best plays
     available_fish, available_treasures,

     # Activity feed
     recent_catches (list of FishCatch),

     # Meta
     error_count, last_updated_seconds_ago, poll_interval,
     ```
   - `close()` -- save cache, close httpx client
   - Uses `_safe_call()` pattern (same as other managers) for graceful degradation

**Tests:**
- `tests/data/test_cattown_manager.py` -- mock client, verify dict keys and types

---

### Phase 5: Widgets (Days 4-5)

**Goal:** Build 6 widgets from templates. Each widget is a standalone Textual widget with `compose()` and `update_data()`.

**Steps:**

5.1. **`dashboard/widgets/cattown/__init__.py`** -- re-export all widgets.

5.2. **`ct_hero_metrics.py`** (from `hero_metrics_template.py`):
   - 3 boxes: KIBBLE Price, Competition Countdown, Top Fisher
   - `update_data(kibble_price_usd, kibble_change_24h, competition_state, top_fisher)`
   - KIBBLE Price: `$X.XXXX` with green/red 24h delta
   - Competition: countdown timer or "LIVE" indicator + prize pool in KIBBLE
   - Top Fisher: short address + weight in kg + species name

5.3. **`ct_leaderboard.py`** (from `leaderboard_template.py`):
   - DataTable with columns: Rank, Fisher, Best Fish, Weight (kg), Rarity
   - `update_data(competition_entries: list[CompetitionEntry])`
   - Short addresses (0xABCD...1234)
   - Weight right-aligned with 1 decimal

5.4. **`ct_sparklines.py`** (from `sparkline_template.py`):
   - 3 ASCII sparkline charts stacked vertically
   - `update_data(burn_rate_history, fishing_volume_history, prize_pool_history)`
   - Labels: "KIBBLE Burn Rate", "Fishing Volume (casts/hr)", "Prize Pool Growth"

5.5. **`ct_signals.py`** (from `signals_template.py`):
   - 5 signal rows with label, value, color indicator
   - `update_data(condition_signal, legendary_signal, competition_signal, staking_signal, kibble_signal)`
   - Each signal dict has: label, value_str, indicator, color

5.6. **`ct_activity_feed.py`** (from `activity_feed_template.py`):
   - RichLog showing recent onchain events
   - `update_data(recent_catches: list[FishCatch])`
   - Format: `HH:MM | 0xABCD | Caught Rainbow Trout (2.3kg) [Common]`
   - Color by rarity: Common=dim, Uncommon=white, Rare=cyan, Epic=magenta, Legendary=yellow

5.7. **`ct_best_plays.py`** (from `two_column_table_template.py`):
   - Left column: "TOP FISH NOW" -- top 5 fish by max weight under current conditions
   - Right column: "TOP TREASURES NOW" -- top 5 treasures by max value under current conditions
   - `update_data(available_fish, available_treasures)`
   - Each row: name, weight/value range, rarity tag with color

---

### Phase 6: Screen Assembly and App Wiring (Day 5)

**Goal:** Create CatTownScreen, wire into app.py game cycle.

**Steps:**

6.1. **Create `dashboard/screens/cattown.py`** (from `screen_template.py`):
   - Layout matches the wireframe from the brief
   - Compose:
     ```
     Static (title bar: "Cat Town Fishing . Competition Week X")
     CTHeroMetrics
     Horizontal:
       CTLeaderboard
       Vertical:
         CTSparklines
         CTSignals
     Static (separator)
     Horizontal:
       CTActivityFeed
       CTBestPlays
     StatusBar
     ```
   - Refresh wiring: same pattern as BakeryScreen
     - `on_screen_resume` -> start timer + initial refresh
     - `on_screen_suspend` -> stop timer
     - `_do_refresh` -> `manager.fetch_and_compute()` then update each widget in try/except
   - Title bar updates with competition week number from data

6.2. **Modify `dashboard/app.py`:**
   - Add import: `from dashboard.data.cattown_manager import CatTownManager`
   - Add import: `from dashboard.screens.cattown import CatTownScreen`
   - In `__init__`: create `self._cattown_manager = CatTownManager(poll_interval=poll_interval)`
   - Update `_GAME_CYCLE`: `["bakery", "frenpet", "base", "cattown"]`
   - In `on_mount`: add `elif self._initial_game == "cattown":` prefetch branch
   - In `_launch_game`: add `elif game_id == "cattown":` install screen branch
   - In `action_quit`: add `await self._cattown_manager.close()` cleanup

6.3. **Modify `dashboard/__main__.py`:**
   - Add `"cattown"` to `--game` choices
   - Add `"cattown"` to `--theme` choices (if a cattown theme is created)

6.4. **Modify `dashboard/screens/game_select.py`:**
   - Add entry to `GAMES` list:
     ```python
     ("4", "cattown", "Cat Town Fishing", "Fish, compete, stake KIBBLE on Base L2"),
     ```

---

### Phase 7: Tests (Days 5-6)

**Goal:** Test coverage for all analytics, data, and manager modules.

**Steps:**

7.1. **`tests/analytics/test_cattown_conditions.py`** (~15 tests):
   - Time-of-day mapping (4 tests, boundary values)
   - Season mapping (4 tests, boundary months)
   - Fish filtering by condition (3 tests: "Any" species, specific time, specific season)
   - Legendary window detection (2 tests: favorable vs unfavorable)
   - Competition timing (2 tests: weekday vs weekend)

7.2. **`tests/analytics/test_cattown_economy.py`** (~10 tests):
   - Burn rate calculation (normal, zero events, single event)
   - Fishing volume (normal, zero span)
   - Staking APY (normal, zero staked)
   - Prize pool growth (normal, empty history)
   - format_kibble (millions, thousands, small values)

7.3. **`tests/analytics/test_cattown_signals.py`** (~10 tests):
   - Each of the 5 signal generators with representative inputs
   - Edge cases: zero price change, competition not active, staking APY zero

7.4. **`tests/data/test_cattown_client.py`** (~8 tests):
   - Mock RPC responses for each client method
   - Error handling: RPC failure returns graceful error
   - KIBBLE price from Oracle vs DEX pool fallback

7.5. **`tests/data/test_cattown_cache.py`** (~6 tests):
   - Insert and retrieve time-series data
   - Max history limit enforcement
   - Persistence round-trip (save/load)

7.6. **`tests/data/test_cattown_manager.py`** (~5 tests):
   - Full fetch_and_compute with mocked client
   - Verify all expected keys present in returned dict
   - Error count increment on failure
   - Cache persistence on close

**Total: ~54 tests** (consistent with project's existing 381 tests)

---

## 8. Implementation Sequence and Dependencies

```
Phase 0: ABI Discovery
    |
    v
Phase 1: Models + Client + Cache  <-- Phase 2: Conditions/Fish Tables (parallel)
    |                                      |
    v                                      v
Phase 3: Analytics (needs both Phase 1 models and Phase 2 tables)
    |
    v
Phase 4: Data Manager (needs Phase 1 + 3)
    |
    v
Phase 5: Widgets (needs Phase 4 for data shape)  <-- can start templates in parallel with Phase 3-4
    |
    v
Phase 6: Screen + App Wiring (needs Phase 5)
    |
    v
Phase 7: Tests (can start in Phase 2, finish after Phase 6)
```

**Parallelizable work:**
- Phase 2 (static tables) can be done concurrently with Phase 1 (client)
- Widget template scaffolding can start during Phase 3
- Test files for analytics can be written alongside analytics modules

---

## 9. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ABI extraction fails entirely | Low | Blocks project | Fallback to decompilation; worst case, KIBBLE-only dashboard |
| Weather system is server-side, not queryable | Medium | Degrades conditions widget | Default to "Unknown" weather; show time-of-day and season only |
| Competition contract has no read function for leaderboard | Medium | Blocks leaderboard widget | Parse CompetitionEntry events from logs instead |
| Base RPC rate limits under heavy event log queries | Medium | Slow/failed data fetch | Use Alchemy with API key (already available in project); cache aggressively |
| Fish identification event structure doesn't include species/weight | Low | Activity feed shows only addresses, not fish details | Combine with ERC-721 metadata reads for enrichment |
| Gelato VRF callback events don't link to original cast | Low | Can't pair casts with results | Use tx sender + block timestamp proximity for correlation |

---

## 10. Data Freshness Plan

| Widget | Source | Update Frequency | Notes |
|--------|--------|-----------------|-------|
| KIBBLE Price | Oracle contract or DEX reserves | Every poll (30s) | Fast, single eth_call |
| Competition Leaderboard | Competition events | Every poll (30s) | Event log query, last ~1000 blocks |
| Sparklines | Cached time-series | Every poll (30s) | Append new data point to cache |
| Signals | Computed from conditions + economy | Every poll (30s) | Pure computation, no RPC |
| Activity Feed | Fishing Game events | Every poll (30s) | Event log query, last ~200 blocks |
| Best Plays | Static tables + conditions | Every poll (30s) | Recalculate on time-of-day change |

---

## 11. Degraded Mode Strategy

If specific contract reads fail, the dashboard should still render with partial data:

- **KIBBLE price fails:** Show "---" in hero card, skip price sparkline
- **Competition contract fails:** Show "No data" in leaderboard, skip competition signal
- **Fishing Game events fail:** Show "Waiting for data..." in activity feed
- **Revenue Share fails:** Show "---" for staking APY signal
- **All RPC fails:** Show all widgets in "Offline" state; increment error count in status bar

This follows the existing `_safe_call()` pattern used by all other managers.

---

## 12. Open Questions

1. **Weather data source:** Is it worth reverse-engineering Ably websocket auth to get real-time weather, or should we start without it?
   - **Recommendation:** Start without. Time-of-day and season cover most fish availability. Weather can be added later.

2. **Historical event depth:** How many blocks back should we query for initial activity feed population?
   - **Recommendation:** Last 1000 blocks (~30 minutes on Base). Increase if feed looks sparse.

3. **KIBBLE price source priority:** Oracle contract vs DEX pool reserves vs DexScreener API?
   - **Recommendation:** Oracle first (single eth_call, cheapest). DEX pool as fallback. DexScreener as last resort (external dependency).

4. **Should we create a "cattown" theme?**
   - **Recommendation:** Optional, low priority. The existing themes work fine. Could add a blue/teal fish-themed palette later.

---

## 13. Validation Plan

After each phase, validate:

| Phase | Validation |
|-------|-----------|
| 0 | Can call at least one function on each target contract from Python |
| 1 | `CatTownClient.fetch_snapshot()` returns populated `CatTownSnapshot` |
| 2 | `get_available_fish()` returns correct fish for known condition sets |
| 3 | All analytics functions return expected types with sample data |
| 4 | `CatTownManager.fetch_and_compute()` returns dict with all expected keys |
| 5 | Each widget renders in isolation with sample data (manual Textual test) |
| 6 | Full app boots, Tab cycles through all 4 games, Cat Town screen refreshes |
| 7 | `pytest tests/` passes with 0 failures |

**Final acceptance:** Run `python -m dashboard --game cattown`, see live data updating on 30-second cycle, all 6 widget areas populated.
