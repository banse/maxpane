# FrenPet Dashboard Plan for MaxPane

## Problem Statement

MaxPane is a terminal TUI (Textual) that currently shows a single RugPull Bakery dashboard. We need to add a second game -- FrenPet -- as a fully separate dashboard within the same app, switchable with Tab. The FrenPet dashboard needs three internal views (General, Wallet, Pet) switchable with 1/2/3 keys. This requires restructuring the app from a single-game layout to a multi-game shell, then building the full FrenPet data pipeline and widget set.

### Who is affected

- The existing Bakery dashboard must keep working identically after the refactor.
- The FrenPet dashboard is new; it reads from Ponder GraphQL, the game REST API, and Base RPC.

### Success criteria

1. Tab switches between Bakery and FrenPet without data loss or timer conflicts.
2. FrenPet General view shows population stats, leaderboard, battle feed, market conditions.
3. FrenPet Wallet view shows per-pet cards, aggregate stats, action queue, alerts.
4. FrenPet Pet view shows deep single-pet analytics with battle log and target landscape.
5. Left/right arrows navigate between pets in Pet view.
6. Data refreshes on a configurable poll interval without blocking the UI.
7. Existing Bakery dashboard behavior is unchanged.

---

## Context and Constraints

### Known facts

- Textual version in use supports `Screen`, `TabbedContent`, registered themes, `run_worker`, and `set_interval`.
- The existing app composes all Bakery widgets directly in `MaxPaneApp.compose()` with no Screen abstraction.
- The existing `DataManager` owns a `GameDataClient` (httpx), a `DataCache`, and all analytics. All wired in `_do_refresh()` on the App class itself.
- FrenPet's autopet codebase uses `aiohttp` for HTTP and raw `eth_call` for RPC. The dashboard uses `httpx`. We need to pick one.
- FrenPet API sources: Ponder GraphQL at `https://api.pet.game`, REST at `https://api.pet.game/api`, Base RPC for on-chain reads.
- Diamond contract: `0x0e22b5f3e11944578b37ed04f5312dfc246f443c` on Base.
- Battle math is fully implemented in `/Library/Vibes/autopet/backend/mechanics/battle_calc.py` and can be adapted.
- The indexer DB in autopet uses sqlite3 for population tracking. The dashboard should not depend on a local sqlite DB -- it should query Ponder directly.

### Constraints

- Must use `httpx` (not `aiohttp`) to stay consistent with the existing dashboard HTTP stack.
- No wallet private keys or transaction signing needed -- this is read-only.
- The FrenPet client needs a wallet address (or list of pet IDs) to know "your pets." This should come from CLI args or config.
- Textual's `TabbedContent` does not natively support switching tabs via number keys. We will need custom key bindings that call `TabbedContent.active = "tab-id"`.

### Assumptions

- The Ponder GraphQL API at `https://api.pet.game` supports bulk queries for all pets (with pagination) and single-pet queries. Confirmed by existing autopet code.
- On-chain reads via `eth_call` to Base RPC are fast enough for dashboard polling (< 2s per pet).
- The user manages a small number of pets (1-10), so per-pet RPC calls are feasible every poll cycle.
- Score values from Ponder are in raw format (need `/1e12` for display). Confirmed by `score_to_display()` in battle_calc.py.

### Unknowns

1. **Ponder pagination limits.** The autopet code fetches up to 100 targets. For population stats we may need thousands. Need to verify if Ponder supports `limit: 1000+` or requires cursor pagination.
2. **Attack event feed.** No existing code fetches historical Attack events from chain. Options: (a) subscribe to logs via RPC, (b) poll recent blocks, (c) use Ponder if it indexes events. Needs investigation.
3. **FP token price.** No existing endpoint identified. May need a DEX aggregator or skip for v1.
4. **Rate limiting on Ponder/RPC.** Unknown. Population queries hitting thousands of pets could trigger limits.

---

## Architecture Decisions

### AD-1: Multi-game structure

**Decision:** Separate Textual Screens per game (Option A).

**Options considered:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A: Separate Screens | Each game is a `Screen` subclass. Tab pushes/pops between them. | Clean separation. Each screen owns its compose tree. Independent lifecycle. Easy to add more games later. | Screen push/pop has a small transition cost. Need to manage poll timers per-screen. |
| B: Single screen, swap containers | One Screen, show/hide game containers. | Faster visual switch. Single compose tree. | Tangled widget namespaces. Complex show/hide logic. Hard to reason about. |

**Why Option A:** The existing codebase already uses `Screen` for splash. Each game's compose tree, data manager, and poll timer are fully independent. No risk of widget ID collisions. Adding a third game later is trivial.

**Consequences:** Must refactor `MaxPaneApp.compose()` to yield nothing (or a minimal shell) and push the Bakery screen on mount. Tab handler on the App level switches screens. Each screen manages its own `DataManager` and refresh timer.

### AD-2: View switching within FrenPet

**Decision:** `ContentSwitcher` with manual key bindings (Option C variant).

**Options considered:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A: TabbedContent | Built-in tabbed container. | Tab bar shows view names. Built-in switching. | Tab bar wastes vertical space. Number-key switching requires monkey-patching or custom bindings to set `.active`. |
| B: Separate Screens | Each view is its own Screen. | Maximum isolation. | Loses shared state (selected pet, data manager ref). Screen push/pop stack gets deep. |
| C: ContentSwitcher | Container that shows one child at a time. `1`/`2`/`3` keys set active child. | No wasted space. Clean switching. Shared state on parent. | Must build own tab indicator (one line, cheap). |

**Why Option C:** Vertical space is precious in a terminal. ContentSwitcher is a first-class Textual widget. We add a one-line status indicator showing `[1] General  [2] Wallet  [3] Pet` with the active one highlighted. Number keys are bound on the FrenPetScreen.

### AD-3: HTTP client choice

**Decision:** Use `httpx` for all FrenPet API calls, replacing `aiohttp` from autopet.

The existing dashboard standardizes on httpx with retry logic. The FrenPet client will follow the same pattern as `GameDataClient`: httpx.AsyncClient with exponential backoff. Raw `eth_call` goes through httpx POST to the RPC URL instead of the autopet `aiohttp` approach.

### AD-4: Battle math reuse

**Decision:** Copy and adapt battle_calc.py functions into the dashboard analytics module rather than importing from autopet.

Rationale: The autopet repo is a separate project. The dashboard should not have a cross-repo import dependency. The battle math is ~100 lines of pure functions with no external dependencies. We copy `win_probability`, `could_lose`, `could_win`, `reward_risk_ratio`, `battle_outcome`, and `score_to_display` into `dashboard/analytics/frenpet_battle.py`.

### AD-5: Pet identity configuration

**Decision:** Accept wallet address via CLI `--wallet` flag. Derive pet IDs by querying the FrenPet NFT contract's `tokensOfOwner(address)` or Ponder's owner filter.

If no wallet is provided, the FrenPet dashboard runs in "spectator mode" showing only the General view (population/leaderboard). Wallet and Pet views show a placeholder message.

---

## File Structure

```
dashboard/
  app.py                    (MODIFY: remove compose body, add Tab binding, push game screens)
  __main__.py               (MODIFY: add --wallet, --game flags)
  themes/
    __init__.py             (existing, no changes)
    minimal.tcss            (MODIFY: add FrenPet widget styles)
  screens/
    __init__.py             (existing)
    splash.py               (MODIFY: update to show game selection or just pass through)
    bakery.py               (NEW: extract current app.py compose + refresh into BakeryScreen)
    frenpet.py              (NEW: FrenPetScreen with ContentSwitcher, 3 views)
  data/
    client.py               (existing, no changes)
    models.py               (existing, no changes)
    cache.py                (existing, no changes)
    snapshot.py             (existing, no changes)
    manager.py              (existing, no changes)
    frenpet_client.py       (NEW: httpx client for Ponder GraphQL + REST + RPC)
    frenpet_models.py       (NEW: Pydantic models for pet, population, battle event)
    frenpet_snapshot.py     (NEW: FrenPetSnapshot model)
    frenpet_cache.py        (NEW: per-pet score time-series + population snapshot cache)
    frenpet_manager.py      (NEW: orchestrates fetch -> cache -> analytics)
  analytics/
    (existing files unchanged)
    frenpet_battle.py       (NEW: battle math copied from autopet + EV calc)
    frenpet_signals.py      (NEW: threat assessment, market conditions, velocity)
    frenpet_population.py   (NEW: score distribution, population aggregates)
  widgets/
    (existing files unchanged)
    status_bar.py           (MODIFY: add game indicator)
    frenpet/
      __init__.py
      view_bar.py           (NEW: [1] General [2] Wallet [3] Pet indicator bar)
      hero_metrics.py       (NEW: top-row stats for FrenPet)
      population.py         (NEW: population stats panel)
      score_dist.py         (NEW: score distribution histogram using bar chars)
      leaderboard.py        (NEW: top 10 pets DataTable)
      battle_feed.py        (NEW: live battle events log)
      game_stats.py         (NEW: global stats — battles/hr, avg win rate)
      market_conditions.py  (NEW: target density, avg DEF, verdict)
      pet_card.py           (NEW: compact card for wallet view)
      action_queue.py       (NEW: unified action timeline sorted by urgency)
      alerts.py             (NEW: TOD/FP/staking alert panel)
      pet_stats.py          (NEW: detailed single-pet stats)
      score_trend.py        (NEW: sparkline for pet score 24h)
      battle_log.py         (NEW: last 20 battles DataTable)
      target_landscape.py   (NEW: target availability summary)
      sniper_queue.py       (NEW: upcoming targets with countdown)
      training_status.py    (NEW: ATK/DEF training bars)
      pet_signals.py        (NEW: per-pet strategic signals)
      gas_monitor.py        (NEW: gas price sparkline)
```

---

## Pydantic Models (frenpet_models.py)

Key models needed:

```
Pet:
  id, name, owner, score (raw), score_display, attack_points, defense_points,
  level, status (0=alive, 1=dead, 2=hibernated), time_until_starving,
  last_attacked, last_attack_used, shield_expires, shrooms,
  pet_wins, win_qty, loss_qty, wheel_last_spin, staking_perks_until,
  fp_owed, is_training (from RPC), training_data (from RPC)

PopulationSnapshot:
  total_pets, active_count, hibernated_count, dead_count, shielded_count,
  in_battle_cd_count, training_count,
  score_buckets: dict[str, int]  (the histogram),
  timestamp

BattleEvent:
  block_number, tx_hash, attacker_id, defender_id, attacker_won,
  attacker_score_delta, defender_score_delta, timestamp

WalletSummary:
  address, pet_ids, total_score, combined_win_rate, fp_balance,
  gas_spent_estimate

FrenPetSnapshot:
  population: PopulationSnapshot
  my_pets: list[Pet]
  top_pets: list[Pet]  (top 10 by score)
  recent_battles: list[BattleEvent]
  targets_available: int
  sweet_spot_targets: int
  fetched_at: float
```

---

## Data Flow

```
FrenPetClient                    FrenPetManager                    FrenPetScreen
  .fetch_population()  ------>     .fetch_and_compute()  ------>     ._do_refresh()
  .fetch_pet(id)                     |                                  |
  .fetch_targets(atk)                v                                  v
  .fetch_training(id)            FrenPetCache                     update widgets
  .fetch_battles()                 .update()
                                   .get_score_history(pet_id)
                                   .get_population_history()
```

Each FrenPetScreen refresh cycle:
1. Fetch population (Ponder GraphQL, paginated) -- needed for General view
2. Fetch my pets (Ponder + RPC for training status) -- needed for Wallet + Pet views
3. Fetch targets for selected pet (Ponder) -- needed for Pet view
4. Run analytics: population stats, battle math per target, signals
5. Update cache with time-series points
6. Push computed dict to widgets

Poll intervals:
- Population: every 60s (heavier query)
- My pets: every 30s
- Targets: every 30s (only if Pet view is active, to save bandwidth)
- RPC training data: every 30s per pet

---

## Work Packages

### WP-F1: FrenPet API Client + Models

**Scope:** New files `frenpet_client.py`, `frenpet_models.py`, `frenpet_snapshot.py`

**Details:**
- `FrenPetClient` class with httpx, retry logic matching existing `GameDataClient` pattern
- GraphQL methods:
  - `fetch_population(limit, offset)` -- all pets paginated, for population stats
  - `fetch_pet(pet_id)` -- single pet full info
  - `fetch_pets_by_owner(address)` -- all pets owned by a wallet
  - `fetch_targets(own_pet_id, max_defense)` -- eligible battle targets (reuse autopet query logic)
- REST methods:
  - None needed for read-only dashboard (commit/reveal are write operations)
- RPC methods:
  - `fetch_training_data(pet_id)` -- raw eth_call to diamond, decode 12 uint256s
  - `fetch_is_training(pet_id)` -- raw eth_call, decode bool
  - `fetch_pet_on_chain(pet_id)` -- getPet call if Ponder data is stale
- All responses parsed into frozen Pydantic models
- `FrenPetSnapshot` aggregation model

**Reference files:**
- `/Library/Vibes/autopull/dashboard/data/client.py` -- pattern to follow (httpx, retry, `from_api`)
- `/Library/Vibes/autopet/backend/game_api.py` -- GraphQL queries and RPC call format to port
- `/Library/Vibes/autopet/backend/core/contracts.py` -- contract addresses, diamond address

**Acceptance:** Can call `client.fetch_population()` and `client.fetch_pet(123)` and get typed models back.

**Agent assignment:** Backend Architect

---

### WP-F2: FrenPet Analytics

**Scope:** New files `frenpet_battle.py`, `frenpet_signals.py`, `frenpet_population.py`

**Details:**

`frenpet_battle.py`:
- Copy from `/Library/Vibes/autopet/backend/mechanics/battle_calc.py`: `win_probability`, `could_lose`, `could_win`, `reward_risk_ratio`, `battle_outcome`, `score_to_display`
- Add `expected_value(win_prob, could_win, could_lose)` for dashboard display
- Add `battle_efficiency(wins, losses)` metric

`frenpet_population.py`:
- `score_distribution(pets) -> dict[str, int]` with buckets: 0-10K, 10-50K, 50-100K, 100-200K, 200-500K, 500K+
- `population_stats(pets) -> PopulationStats` with counts by status
- `rank_pet(pet, all_pets) -> (rank, percentile)`

`frenpet_signals.py`:
- `target_density(available_targets, total_alive)` -- what fraction of population is attackable
- `market_conditions(avg_def, hibernation_rate, target_density) -> MarketVerdict` (FAVORABLE / NEUTRAL / HOSTILE)
- `threat_assessment(pet, recent_attacks_on_pet)` -- are we being targeted
- `score_velocity(score_history) -> float` -- points per hour trend
- `staking_health(pet) -> str` -- time until starving assessment

**Reference files:**
- `/Library/Vibes/autopet/backend/mechanics/battle_calc.py` -- battle math source
- `/Library/Vibes/autopet/backend/strategy/battle.py` -- growth phases, EV calculation
- `/Library/Vibes/autopull/dashboard/analytics/signals.py` -- pattern for signal functions

**Acceptance:** Pure functions, no I/O. All testable with synthetic data.

**Agent assignment:** Backend Architect

---

### WP-F3: FrenPet Cache + Manager

**Scope:** New files `frenpet_cache.py`, `frenpet_manager.py`

**Details:**

`frenpet_cache.py`:
- `FrenPetCache` class following pattern from `/Library/Vibes/autopull/dashboard/data/cache.py`
- Per-pet score time-series: `deque[(timestamp, score)]` keyed by pet_id
- Population snapshot history: `deque[(timestamp, PopulationStats)]`
- Persistence to `~/.maxpane/frenpet_cache.json`

`frenpet_manager.py`:
- `FrenPetDataManager` class following pattern from `/Library/Vibes/autopull/dashboard/data/manager.py`
- Constructor takes `wallet_address: str | None`, `poll_interval: int`
- `fetch_and_compute() -> dict[str, Any]` that:
  1. Fetches population via client
  2. Fetches my pets (if wallet configured)
  3. Fetches targets for active pet
  4. Runs population analytics
  5. Runs per-pet battle analytics
  6. Runs signal calculations
  7. Updates cache
  8. Returns flat dict keyed for widget consumption
- Staggered fetching: population every 2nd cycle, targets only when Pet view active
- `set_active_pet(pet_id)` to control which pet's targets are fetched
- `set_active_view(view_name)` to skip unnecessary fetches

**Dependencies:** WP-F1 (client), WP-F2 (analytics)

**Acceptance:** `await manager.fetch_and_compute()` returns a dict with all widget data populated.

**Agent assignment:** Backend Architect

---

### WP-F4: Multi-Game App Refactor

**Scope:** Modify `app.py`, `__main__.py`, `splash.py`. New files `screens/bakery.py`, `screens/frenpet.py` (shell only).

**Details:**

`screens/bakery.py`:
- Extract the entire `compose()` body from current `MaxPaneApp` into `BakeryScreen(Screen)`
- Move `_do_refresh()` logic into the screen
- Screen owns its `DataManager` instance
- Screen starts/stops its own poll timer on `on_mount()` / `on_unmount()` (or `on_screen_resume` / `on_screen_suspend`)

`screens/frenpet.py` (shell):
- `FrenPetScreen(Screen)` with `ContentSwitcher` containing three `Container` children
- Placeholder content in each container: "General View (coming soon)" etc.
- Key bindings: `1` -> General, `2` -> Wallet, `3` -> Pet
- View bar widget at top showing active view
- `_do_refresh()` stub that does nothing yet (wired in WP-F8)

`app.py`:
- `MaxPaneApp.compose()` yields only the `StatusBar` (docked bottom, persistent across screens)
- `on_mount()`: register themes, show splash, then push default game screen
- Add `Binding("tab", "switch_game", "Switch Game")`
- `action_switch_game()`: if current screen is BakeryScreen, switch to FrenPetScreen and vice versa. Use `self.switch_screen()` or `pop + push` pattern.
- Both screen instances created once in `__init__` and reused (so state is preserved on switch)

`__main__.py`:
- Add `--wallet` argument (hex address, optional)
- Add `--game` argument (`bakery` | `frenpet`, default `bakery`) for which game to show first
- Pass wallet to FrenPetScreen / FrenPetDataManager

`splash.py`:
- No structural changes needed. Splash dismisses, then game screen appears.

**Key risk:** The existing `_do_refresh` in `app.py` directly queries widgets by type (e.g., `self.query_one(HeroMetrics)`). When moved into BakeryScreen, these queries will scope to the screen automatically. Must verify Textual's query scoping.

**Reference files:**
- `/Library/Vibes/autopull/dashboard/app.py` -- current monolithic layout to decompose
- `/Library/Vibes/autopull/dashboard/screens/splash.py` -- existing Screen pattern

**Acceptance:**
- App launches, shows splash, then shows Bakery dashboard (identical to current behavior)
- Tab switches to FrenPet placeholder screen and back
- 1/2/3 keys switch views within FrenPet screen
- Bakery data still refreshes correctly

**Agent assignment:** Frontend Developer

---

### WP-F5: General View Widgets

**Scope:** New widget files in `dashboard/widgets/frenpet/`. Wire into FrenPetScreen General container.

**Widgets:**

| Widget | File | Content |
|--------|------|---------|
| FPHeroMetrics | `hero_metrics.py` | Total pets, active count, battles/hr, avg reward |
| PopulationPanel | `population.py` | Breakdown: active, hibernated, shielded, battle CD, training |
| ScoreDistribution | `score_dist.py` | Horizontal bar chart using block characters per bucket |
| FPLeaderboard | `leaderboard.py` | DataTable: rank, pet ID, score, ATK/DEF, status |
| BattleFeed | `battle_feed.py` | RichLog of recent Attack events (attacker, defender, result, delta) |
| GameStats | `game_stats.py` | Battles/hr, avg win rate, avg reward panel |
| MarketConditions | `market_conditions.py` | Target density, avg DEF, hibernation rate, verdict badge |
| PetsInContext | (inside `population.py`) | Your pets' rank + percentile vs population |

**Layout (General view container):**
```
[FPHeroMetrics                                               ] (top row, h=7)
[PopulationPanel (left 2fr)  | ScoreDistribution (right 3fr) ] (middle-top)
[FPLeaderboard (left 3fr)    | MarketConditions (right 2fr)  ] (middle)
[BattleFeed (left 3fr)       | GameStats (right 2fr)         ] (bottom)
```

Each widget follows the existing pattern: a `Vertical` or `Horizontal` subclass with `compose()` returning Static/DataTable/RichLog children, and an `update_data(**kwargs)` method.

**Dependencies:** WP-F4 (screen shell exists)

**Acceptance:** General view renders with placeholder data. `update_data()` methods accept the dict keys from WP-F3's manager output.

**Agent assignment:** Frontend Developer

---

### WP-F6: Wallet View Widgets

**Scope:** New widget files for the Wallet container.

**Widgets:**

| Widget | File | Content |
|--------|------|---------|
| PetCard | `pet_card.py` | Compact card: score, ATK/DEF, TOD bar, win rate, status dot, mini sparkline |
| AggregateStats | (inside `hero_metrics.py` or new) | Total score, combined win rate, FP balance, gas spent |
| ActionQueue | `action_queue.py` | Table: pet ID, action type, countdown, urgency color |
| AlertsPanel | `alerts.py` | TOD warnings (amber <24h, red <6h), low FP, staking failures |
| RecentActivity | (reuse `battle_feed.py` pattern) | Combined activity log for all managed pets |

**Layout (Wallet view container):**
```
[AggregateStats                                              ] (top row, h=5)
[PetCard] [PetCard] [PetCard] ... (responsive grid, h=auto)
[ActionQueue (left 3fr)       | AlertsPanel (right 2fr)      ] (bottom)
```

Pet cards should use a `Grid` or wrapping `Horizontal` that fits 2-3 cards per row depending on terminal width.

**Dependencies:** WP-F4 (screen shell), WP-F5 (share widget patterns)

**Agent assignment:** Frontend Developer

---

### WP-F7: Pet View Widgets

**Scope:** New widget files for the Pet deep-dive container.

**Widgets:**

| Widget | File | Content |
|--------|------|---------|
| PetStatsPanel | `pet_stats.py` | Score, ATK, DEF, TOD countdown, level, wins, shrooms, growth phase |
| ScoreTrend | `score_trend.py` | Sparkline (24h) using braille/block chars |
| NextActions | `action_queue.py` (reuse) | Countdown bars for stake, wheel, battle, training |
| BattleLog | `battle_log.py` | DataTable: opponent ID, opp stats, win prob, ratio, result, delta |
| TargetLandscape | `target_landscape.py` | Available count, sweet spot count, best target summary |
| SniperQueue | `sniper_queue.py` | Table: target ID, score, DEF, cooldown-expires countdown, win prob |
| TrainingStatus | `training_status.py` | ATK training progress bar, DEF training progress bar |
| PetSignals | `pet_signals.py` | Battle efficiency, staking health, rank, threats, velocity |
| GasMonitor | `gas_monitor.py` | Current gas price + sparkline |

**Layout (Pet view container):**
```
[PetNavBar: <- Pet #123 "Fluffy" ->                          ] (h=1)
[PetStatsPanel (left 2fr)    | ScoreTrend + Signals (right 3fr)] (top)
[BattleLog (left 3fr)        | TargetLandscape (right 2fr)     ] (middle)
[SniperQueue (left 3fr)      | TrainingStatus + Gas (right 2fr)] (bottom)
```

Pet navigation:
- Left/right arrow keys bound on FrenPetScreen
- `set_active_pet(pet_id)` updates all Pet view widgets
- Pet nav bar shows current pet name/ID with arrow indicators

**Dependencies:** WP-F4, WP-F5 (widget patterns), WP-F2 (battle math for target analysis)

**Agent assignment:** Frontend Developer

---

### WP-F8: Integration + Polish

**Scope:** Wire live data from FrenPetDataManager into all FrenPet widgets. End-to-end functionality.

**Details:**
- Implement `FrenPetScreen._do_refresh()` calling `self.data_manager.fetch_and_compute()` and distributing results to all widgets via `update_data()` calls (following the pattern in current `app.py` lines 110-205)
- Start poll timer on `on_screen_resume()`, pause on `on_screen_suspend()`
- Optimize: only fetch target data when Pet view is active (check `self._active_view`)
- Handle edge cases:
  - No wallet provided: disable Wallet/Pet views, show "configure --wallet" message
  - No pets found for wallet: show "no pets" state
  - Ponder API down: show last cached data with staleness indicator
  - RPC errors: graceful degradation (training status shows "unknown")
- StatusBar updates: show current game name, active view, selected pet
- TCSS additions for all new FrenPet widgets (add to `minimal.tcss`)
- Test all three views with live data against the real Ponder API

**Dependencies:** WP-F3 (manager), WP-F5, WP-F6, WP-F7 (all widgets)

**Agent assignment:** Full-stack

---

## Dependency Graph

```
Phase 0 (parallel, no dependencies):
  WP-F1: API Client + Models
  WP-F2: Analytics (pure functions)
  WP-F4: Multi-game refactor

Phase 1 (depends on F1 + F2):
  WP-F3: Cache + Manager

Phase 2 (depends on F4, parallel with each other):
  WP-F5: General view widgets
  WP-F6: Wallet view widgets
  WP-F7: Pet view widgets

Phase 3 (depends on F3 + F5 + F6 + F7):
  WP-F8: Integration + Polish
```

**Critical path:** F1 -> F3 -> F8

**Parallelism:** F1, F2, and F4 can all proceed simultaneously. F5/F6/F7 can proceed once F4 is done (they only need the screen shell). F3 needs F1 and F2. F8 needs everything.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Ponder API rate limits on population queries | Medium | High -- General view breaks | Cache population aggressively (60s TTL). Fetch in batches. Add backoff. |
| Ponder schema changes | Low | High -- all queries break | Pin query fields. Add response validation in Pydantic models. Log parse errors. |
| Textual Screen switching drops state | Low | Medium -- timers stop, data lost | Create both screens once in App.__init__, reuse them. Use on_screen_resume/suspend for timer management. |
| Battle event feed infeasible | Medium | Medium -- General view incomplete | If Ponder doesn't index events and RPC log scanning is too slow, stub the battle feed widget and mark as "coming soon." |
| Score format inconsistency | Medium | Medium -- wrong numbers displayed | Use score_to_display() consistently. Add assertion checks in models. |
| Too many RPC calls for large pet collections | Low | Medium -- slow refresh | Batch eth_call using multicall3 contract if pet count > 5. |

---

## Validation Plan

1. **Unit tests for analytics** (WP-F2): Test battle math against known outcomes from autopet's verified calculations.
2. **Integration test for client** (WP-F1): Hit real Ponder API, verify model parsing with a known pet ID.
3. **Smoke test for refactor** (WP-F4): Launch app, verify Bakery dashboard works identically, Tab switches to FrenPet shell.
4. **Visual test per view** (WP-F5/6/7): Launch with mock data manager returning synthetic data, screenshot each view.
5. **End-to-end** (WP-F8): Launch with real wallet address, verify all three views populate with real data, switch between games and views, let it run for 5+ minutes checking refresh stability.

---

## Open Questions

1. Does the Ponder GraphQL API support `offset`-based pagination or only cursor-based? This affects how we implement population scanning.
2. Should the FrenPet dashboard support multiple wallets (multi-account), or single wallet only? Suggest single for v1.
3. Is there an existing event indexer or subgraph for FrenPet Attack events on Base, or do we need to scan raw logs?
4. Should the General view's "battles/hr" stat be calculated from observed events (requires event feed) or estimated from population analysis?
5. What is the desired poll interval for FrenPet? Suggest 30s for pets, 60s for population.

---

## Recommended Approach

Proceed with the phased plan as described. Start with WP-F1, WP-F2, and WP-F4 in parallel. These three have no dependencies on each other and together unlock all downstream work.

The multi-game refactor (WP-F4) is the highest-risk item because it touches the existing working Bakery dashboard. Prioritize testing it thoroughly before building on top.

The FrenPet client (WP-F1) should be validated against the live Ponder API early to resolve the unknowns around pagination limits and data availability.

## Why This Approach

- Separate Screens per game gives clean isolation with no widget namespace conflicts.
- ContentSwitcher for views maximizes terminal real estate.
- Copying battle math avoids cross-repo dependencies.
- Phased delivery means the Bakery dashboard never breaks -- it is refactored and verified before FrenPet work begins on top.
- The widget pattern (compose + update_data) is proven by the existing 6 Bakery widgets and requires no new abstractions.

## Implementation Steps (ordered)

1. **WP-F4** -- Refactor app to multi-game (highest risk, must be solid before building on it)
2. **WP-F1** -- FrenPet client + models (validate against live API immediately)
3. **WP-F2** -- Analytics pure functions (can be done any time, no API needed)
4. **WP-F3** -- Cache + Manager (depends on F1 + F2)
5. **WP-F5** -- General view widgets (depends on F4 shell)
6. **WP-F6** -- Wallet view widgets
7. **WP-F7** -- Pet view widgets
8. **WP-F8** -- Wire everything together
