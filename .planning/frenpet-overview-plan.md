# FrenPet Overview Dashboard -- Implementation Plan

**Date:** 2026-03-27
**Mode:** Standard
**Status:** Ready for implementation

---

## Problem

The FrenPet screen has three views (General, Wallet, Pet) but lacks a single-pane "at a glance" dashboard that matches the proven Bakery screen layout. The Bakery layout is the best-aligned dashboard in the project and serves as the canonical template. We need a 4th view -- "Overview" -- that replicates the Bakery layout exactly, substituting FrenPet game data for Bakery game data.

## Goals

1. Add view [4] "Overview" to the FrenPet ContentSwitcher.
2. Match the Bakery screen layout pixel-for-pixel: hero row, middle row (3fr left | 2fr right with trends + signals), separator, bottom row (3fr left | 2fr right), status bar.
3. Reuse existing data from FrenPetManager wherever possible, adding only the new computed fields needed for overview widgets.
4. Keep the 3 existing views completely untouched.

## Constraints

- Must fit inside the existing ContentSwitcher architecture in `frenpet.py`.
- Widgets must use unique IDs/class names to avoid collisions with existing General/Wallet/Pet widgets (some share the same screen DOM).
- Score history is only cached for **managed pets** (via FrenPetCache). Top leaderboard pets that are not managed will not have sparkline history unless we extend caching. This is a known gap.
- The `game_start_date` is a hardcoded constant (FrenPet deployed ~March 2024).
- Activity feed data comes from `recent_attacks` (already fetched) and optionally `autopet_battles` (local API).

## What Already Exists and Can Be Reused

| Need | Existing asset | Reuse strategy |
|------|---------------|----------------|
| Pet Leaderboard | `TopLeaderboard` widget + `top_pets` data | **Cannot reuse directly** -- same class would conflict in DOM queries. Create `FPOverviewLeaderboard` with identical logic but unique IDs. |
| Battle data | `recent_attacks` + `global_battle_rate` in manager | Reuse as-is. |
| Population stats | `population_stats` dict in manager | Reuse `total`, `active`, `hibernated`. |
| Score histories | `FrenPetCache.get_pet_score_history()` | Only works for managed pets. For top-10 sparklines, need to extend cache to track top pets too. |
| Sparkline renderer | `_build_sparkline()` in `dashboard/templates/sparkline_template.py` (same as `cookie_chart.py`) | Copy the function into new widget. |

## Option Analysis

### Option A: Six standalone overview widgets (Recommended)

Create 6 new widget files under `dashboard/widgets/frenpet/overview/`:
- `fp_hero_metrics.py` -- 3 hero cards
- `fp_overview_leaderboard.py` -- DataTable, top 10 pets
- `fp_score_trends.py` -- Sparklines for top 3-5 pets
- `fp_game_signals.py` -- Key-value signal rows
- `fp_battle_activity.py` -- RichLog battle feed
- `fp_best_plays.py` -- Two-column ranked table

Each widget is a direct adaptation of its Bakery counterpart template, with FrenPet-specific data signatures.

**Benefits:** Clean separation, each widget testable in isolation, matches Bakery 1:1.
**Drawbacks:** 6 new files, some duplication of sparkline/formatting logic.

### Option B: Composite single widget

One large `FPOverviewPanel` widget that composes the entire layout internally (like the BaseTerminal OverviewPanel).

**Benefits:** Single file, fewer imports.
**Drawbacks:** Harder to maintain, harder to test individual sections, does not match the Bakery pattern where each panel is a separate widget class.

### Decision: Option A (recommended)

Matches the Bakery architecture exactly. Each widget has its own `update_data()` method, making the screen's `_do_refresh` wiring clean and predictable.

---

## Work Package Breakdown

### WP-FP1: Overview Widgets

**Owner:** Agent A
**Files to create:**

#### 1. `dashboard/widgets/frenpet/overview/__init__.py`

Exports all 6 overview widgets.

#### 2. `dashboard/widgets/frenpet/overview/fp_hero_metrics.py`

Copy pattern from: `/Library/Vibes/autopull/dashboard/templates/hero_metrics_template.py`

Three `HeroBox`-style statics inside a `Horizontal`:

| Card | ID | Title | Value | Subtitle |
|------|----|-------|-------|----------|
| 1 | `fpo-hero-treasure` | PLAYERS TREASURE | `format_cookies(total_score)` + " pts" | "{active_count} active pets" |
| 2 | `fpo-hero-since` | PLAYING SINCE | Relative duration from `GAME_START = 1709251200` (~March 1, 2024) formatted as "Xy Zm" | "Base L2" |
| 3 | `fpo-hero-leader` | LEADER | "Pet #{id} -- {score} pts" | "ATK {atk} / DEF {def}" |

Class name: `FPOverviewHero`
CSS: Reuse existing `HeroBox` styles (they target the class name not an ID). Use `FPOHeroBox` subclass to avoid style collision.

`update_data(total_score, active_count, game_start_ts, leader_pet)` where `leader_pet` is the first entry from `top_pets`.

#### 3. `dashboard/widgets/frenpet/overview/fp_overview_leaderboard.py`

Copy pattern from: `/Library/Vibes/autopull/dashboard/templates/leaderboard_template.py`

DataTable with columns: `#`, `Pet ID`, `Score`, `ATK/DEF`, `Status`.
Same logic as existing `TopLeaderboard` but with class `FPOverviewLeaderboard` and table ID `fpo-lb-table`.

`update_data(top_pets: list[FrenPet])` -- identical signature to existing `TopLeaderboard.update_data`.

#### 4. `dashboard/widgets/frenpet/overview/fp_score_trends.py`

Copy pattern from: `/Library/Vibes/autopull/dashboard/templates/sparkline_template.py`

Show sparklines for top 3-5 pets. Uses `_build_sparkline()` (copied from `cookie_chart.py`).

`update_data(histories: dict[int, list[tuple[float, float]]])` where keys are pet IDs.

Each line: `  Pet #XXXX  [color]sparkline[/]  score  arrow`

**Data gap:** Score histories are only cached for managed pets. Two options:
- (a) Extend `FrenPetCache.update()` to also record scores for `snapshot.top_pets` -- **recommended**, small change.
- (b) Show sparklines only for managed pets that appear in top 10 -- acceptable fallback.

Decision: Extend the cache (WP-FP2 handles this).

#### 5. `dashboard/widgets/frenpet/overview/fp_game_signals.py`

Copy pattern from: `/Library/Vibes/autopull/dashboard/templates/signals_template.py`

Signal rows:

| Label | Source | Format |
|-------|--------|--------|
| Battle Rate | `global_battle_rate` | "~{n}/hr" |
| Avg Win Rate | computed from `recent_attacks` | "{n}%" |
| Hibernation Rate | `population_stats.hibernated / population_stats.total * 100` | "{n}%" |
| Top Dominance | `top_pets[0].score / top_pets[1].score` | "{n:.1f}x" |
| Recommendation | generated text based on game state | italic text |

Class: `FPGameSignals`

`update_data(battle_rate, avg_win_rate, hibernation_rate, top_dominance, recommendation)`

#### 6. `dashboard/widgets/frenpet/overview/fp_battle_activity.py`

Copy pattern from: `/Library/Vibes/autopull/dashboard/templates/activity_feed_template.py`

RichLog showing recent battles. Same data as existing `BattleFeed` but:
- Class name: `FPOverviewActivity`
- Log ID: `fpo-activity-log`
- Format: `  HH:MM:SS  #{atk} > #{def}  Won/Lost  +/-pts`

`update_data(attacks: list[dict], battle_rate: float)` -- same signature as `BattleFeed`.

**Important:** Must have its own `_seen_keys` set since it is a separate widget instance from `BattleFeed` on the General view.

#### 7. `dashboard/widgets/frenpet/overview/fp_best_plays.py`

Copy pattern from: `/Library/Vibes/autopull/dashboard/templates/two_column_table_template.py`

Two-column layout:
- Left: TOP EARNERS -- pets with highest estimated pts/day
- Right: RISING STARS -- pets with best ATK/DEF ratio (proxy for growth potential)

Class: `FPBestPlays`

`update_data(top_earners: list[tuple[str, str]], rising_stars: list[tuple[str, str]])`

Each list is `[(label, value), ...]` with 3 rows.

---

### WP-FP2: Data Manager Additions

**Owner:** Agent B
**File to modify:** `/Library/Vibes/autopull/dashboard/data/frenpet_manager.py`

Add the following computed fields to the dict returned by `fetch_and_compute()`:

```python
# Overview view (new keys)
"overview_total_score": int,        # sum of ALL pet scores (not just managed)
"overview_active_count": int,       # population_stats["active"]
"overview_game_start": int,         # hardcoded 1709251200 (March 1, 2024 UTC)
"overview_leader": FrenPet | None,  # top_pets[0] if available
"overview_top_dominance": float,    # top_pets[0].score / top_pets[1].score
"overview_avg_win_rate": float,     # from recent_attacks analysis
"overview_hibernation_rate": float, # hibernated / total * 100
"overview_recommendation": str,     # generated text
"overview_top_earners": list[tuple[str, str]],  # [(label, value), ...]
"overview_rising_stars": list[tuple[str, str]], # [(label, value), ...]
"overview_score_histories": dict[int, list[tuple[float, float]]],  # for top pet sparklines
```

#### Specific computations:

**overview_total_score:**
```python
sum(p.score for p in snapshot.population.pets)
```
Note: `population_stats["total_score"]` already exists from `calculate_population_stats`. Reuse it.

**overview_avg_win_rate:**
```python
wins = sum(1 for a in recent_attacks if a.get("attacker_won"))
total = len(recent_attacks)
avg_win_rate = (wins / total * 100) if total > 0 else 50.0
```

**overview_hibernation_rate:**
```python
pop = population_stats
rate = (pop["hibernated"] / pop["total"] * 100) if pop["total"] > 0 else 0.0
```

**overview_top_dominance:**
```python
if len(top_pets) >= 2 and top_pets[1].score > 0:
    dominance = top_pets[0].score / top_pets[1].score
else:
    dominance = float("inf")
```

**overview_recommendation:**
Generate based on game state:
- If hibernation_rate > 40%: "Many hibernated -- easy targets available"
- If top_dominance > 3.0: "Single pet dominance -- challenging meta"
- If battle_rate > 100: "High activity -- train defense"
- If battle_rate < 10: "Low activity -- safe to train stats"
- Default: "Meta balanced -- train stats"

**overview_top_earners:**
Estimate pts/day for each managed pet using velocity from `pet_velocities`. Take top 3.
Format: `("Pet #XXXX", "~1.2M pts/day")`
If no managed pets, use top_pets with placeholder velocity.

**overview_rising_stars:**
Pets with best ATK+DEF total among top_pets (proxy for training investment).
Format: `("Pet #XXXX", "ATK 973 DEF 450")`
Take top 3.

**overview_score_histories (cache extension):**

Modify `FrenPetCache.update()` to also record scores for `snapshot.top_pets`:

```python
# In FrenPetCache.update():
# Record top pets in addition to managed pets
for pet in snapshot.top_pets:
    pet_id = pet.id
    if pet_id not in self._pet_histories:
        self._pet_histories[pet_id] = deque(maxlen=self._max_history)
    self._pet_histories[pet_id].append((snapshot.fetched_at, float(pet.score)))
```

Add a method `get_top_pet_score_histories(pet_ids: list[int])` that returns `dict[int, list[tuple[float, float]]]` for the requested IDs.

Then in `fetch_and_compute()`:
```python
top_pet_ids = [p.id for p in top_pets[:5]]
overview_score_histories = {
    pid: self.cache.get_pet_score_history(pid)
    for pid in top_pet_ids
}
```

---

### WP-FP3: Screen Wiring

**Owner:** Agent A (after WP-FP1)
**File to modify:** `/Library/Vibes/autopull/dashboard/screens/frenpet.py`

#### Changes:

**1. Add import for overview widgets:**
```python
from dashboard.widgets.frenpet.overview import (
    FPOverviewHero,
    FPOverviewLeaderboard,
    FPScoreTrends,
    FPGameSignals,
    FPOverviewActivity,
    FPBestPlays,
)
```

**2. Add keybinding "4":**
```python
Binding("4", "show_overview", "Overview", show=False),
```

**3. Update view selector text** in `compose()`:
```python
yield Static(
    "[bold reverse] 1 General [/]  [dim][2] Wallet[/]  [dim][3] Pet[/]  [dim][4] Overview[/]",
    id="fp-view-selector",
)
```

**4. Add Overview view inside ContentSwitcher** in `compose()`:

```python
# -- Overview View (Bakery-style) ----------------------
with Vertical(id="overview"):
    # Hero row
    yield FPOverviewHero()

    # Middle row: leaderboard (3fr) | trends + signals (2fr)
    with Horizontal(id="fpo-middle-row"):
        yield FPOverviewLeaderboard()
        with Vertical(id="fpo-right-col"):
            yield FPScoreTrends()
            yield FPGameSignals()

    # Separator
    yield Static("\u2500" * 300, id="fpo-separator")

    # Bottom row: activity (3fr) | best plays (2fr)
    with Horizontal(id="fpo-bottom-row"):
        yield FPOverviewActivity()
        yield FPBestPlays()
```

**5. Add action method:**
```python
def action_show_overview(self) -> None:
    self.query_one(ContentSwitcher).current = "overview"
    self._update_selector(4)
```

**6. Update `_update_selector`** to include 4th label:
```python
def _update_selector(self, active: int) -> None:
    labels = ["General", "Wallet", "Pet", "Overview"]
    parts = []
    for i, label in enumerate(labels, 1):
        if i == active:
            parts.append(f"[bold reverse] {i} {label} [/]")
        else:
            parts.append(f"[dim][{i}] {label}[/]")
    self.query_one("#fp-view-selector", Static).update("  ".join(parts))
```

**7. Add `update_overview_view(data)` method** and call it from `_do_refresh`:

```python
def update_overview_view(self, data: dict) -> None:
    """Push fresh data into Overview widgets."""
    top_pets = data.get("top_pets", [])
    population_stats = data.get("population_stats", {})

    # Title bar update (pet count)
    try:
        total = population_stats.get("total", 0)
        title = self.query_one("#fp-title", Static)
        title.update(f"FrenPet \u00b7 Base L2 \u00b7 {total:,} Pets")
    except Exception:
        pass

    # Hero metrics
    try:
        self.query_one(FPOverviewHero).update_data(
            total_score=data.get("overview_total_score", 0),
            active_count=data.get("overview_active_count", 0),
            game_start_ts=data.get("overview_game_start", 1709251200),
            leader_pet=top_pets[0] if top_pets else None,
        )
    except Exception as exc:
        logger.warning("Failed to update FPOverviewHero: %s", exc)

    # Leaderboard
    try:
        self.query_one(FPOverviewLeaderboard).update_data(top_pets)
    except Exception as exc:
        logger.warning("Failed to update FPOverviewLeaderboard: %s", exc)

    # Score trends
    try:
        self.query_one(FPScoreTrends).update_data(
            histories=data.get("overview_score_histories", {}),
        )
    except Exception as exc:
        logger.warning("Failed to update FPScoreTrends: %s", exc)

    # Signals
    try:
        self.query_one(FPGameSignals).update_data(
            battle_rate=data.get("global_battle_rate", 0.0),
            avg_win_rate=data.get("overview_avg_win_rate", 50.0),
            hibernation_rate=data.get("overview_hibernation_rate", 0.0),
            top_dominance=data.get("overview_top_dominance", 1.0),
            recommendation=data.get("overview_recommendation", ""),
        )
    except Exception as exc:
        logger.warning("Failed to update FPGameSignals: %s", exc)

    # Activity feed
    try:
        self.query_one(FPOverviewActivity).update_data(
            attacks=data.get("recent_attacks", []),
            battle_rate=data.get("global_battle_rate", 0.0),
        )
    except Exception as exc:
        logger.warning("Failed to update FPOverviewActivity: %s", exc)

    # Best plays
    try:
        self.query_one(FPBestPlays).update_data(
            top_earners=data.get("overview_top_earners", []),
            rising_stars=data.get("overview_rising_stars", []),
        )
    except Exception as exc:
        logger.warning("Failed to update FPBestPlays: %s", exc)
```

**8. Wire into `_do_refresh`:**
```python
try:
    self.update_overview_view(data)
except Exception as exc:
    logger.warning("Failed to update Overview view: %s", exc)
```

#### CSS additions to `minimal.tcss`:

```css
/* -- FrenPet Overview (Bakery-style layout) -- */

FPOverviewHero {
    height: 7;
    padding: 0 1;
    margin: 1 0 0 0;
}

FPOHeroBox {
    width: 1fr;
    height: 7;
    border: solid $panel;
    padding: 1 2;
    content-align: center middle;
    text-align: center;
    background: $surface;
    margin: 0 1;
}

#fpo-middle-row {
    height: 1fr;
    padding: 0 0;
    margin: 1 0 0 0;
}

FPOverviewLeaderboard {
    width: 3fr;
    padding: 0 1;
}

FPOverviewLeaderboard > .fpo-lb-title {
    color: $text-muted;
    padding: 0 1;
    margin: 0 0 1 0;
}

FPOverviewLeaderboard DataTable {
    height: 1fr;
    padding: 0 0;
    background: $background;
    scrollbar-size: 1 1;
}

#fpo-right-col {
    width: 2fr;
    padding: 0 1;
}

FPScoreTrends {
    height: auto;
    padding: 0 1;
    content-align: center top;
}

FPScoreTrends > .fpo-chart-title {
    color: $text-muted;
}

FPGameSignals {
    height: 1fr;
    padding: 0 1;
    margin: 1 0 0 0;
    overflow-y: auto;
    content-align: center top;
}

FPGameSignals > .fpo-sig-title {
    color: $text-muted;
}

#fpo-separator {
    width: 100%;
    height: 1;
    color: $panel;
    padding: 0 2;
    margin: 0 0;
}

#fpo-bottom-row {
    height: 1fr;
    padding: 0 0;
    margin: 0 0 1 0;
}

FPOverviewActivity {
    width: 3fr;
    padding: 0 1;
}

FPOverviewActivity > .fpo-feed-title {
    color: $text-muted;
    margin: 0 0 1 0;
}

FPOverviewActivity RichLog {
    background: $background;
    scrollbar-size: 1 1;
}

FPBestPlays {
    width: 2fr;
    padding: 0 1;
    content-align: center top;
}

FPBestPlays > .fpo-bp-title {
    color: $text-muted;
}
```

---

## Implementation Sequence

### Phase 1: Data (Agent B, can start immediately)

1. Extend `FrenPetCache.update()` to record top_pets scores.
2. Add `get_top_pet_score_histories()` to cache.
3. Add all `overview_*` keys to `fetch_and_compute()` return dict.
4. Test: call `fetch_and_compute()` and verify all new keys are present and well-typed.

### Phase 2: Widgets (Agent A, can start immediately in parallel)

1. Create `dashboard/widgets/frenpet/overview/` directory with `__init__.py`.
2. Implement each of the 6 widgets in order:
   - `fp_hero_metrics.py` (simplest, no external deps)
   - `fp_overview_leaderboard.py` (direct copy of TopLeaderboard with renames)
   - `fp_score_trends.py` (copy sparkline logic from cookie_chart.py)
   - `fp_game_signals.py` (copy from signals_panel.py, simplify)
   - `fp_battle_activity.py` (copy from battle_feed.py, rename IDs)
   - `fp_best_plays.py` (copy from ev_table.py, adapt columns)
3. Update `dashboard/widgets/frenpet/__init__.py` to export overview widgets.

### Phase 3: Wiring (Agent A, after Phase 2)

1. Add CSS rules to `minimal.tcss`.
2. Modify `frenpet.py`:
   - Add imports
   - Add keybinding
   - Add Overview Vertical in ContentSwitcher compose
   - Update selector labels
   - Add `update_overview_view()` method
   - Wire into `_do_refresh()`
3. Smoke test: launch app, press `4`, verify layout renders with loading states.

### Phase 4: Integration test

1. Verify all 4 views switch correctly with keys 1-4.
2. Verify data flows from manager through to overview widgets.
3. Verify existing views 1-3 are unaffected.
4. Verify no DOM query collisions between Overview widgets and General/Wallet/Pet widgets.

---

## Risks and Unknowns

| Risk | Severity | Mitigation |
|------|----------|------------|
| DOM query collision: `query_one(TopLeaderboard)` would match both General and Overview leaderboards | High | Use distinct class names (`FPOverviewLeaderboard` vs `TopLeaderboard`). All `query_one()` calls in `update_overview_view` use the new class names. |
| Sparkline data is empty on first launch | Low | The sparkline widget already handles `len(points) < 2` by showing flat bars. After 2 poll cycles (60s) data appears. |
| `overview_total_score` may be very large (~billions) | Low | `format_cookies()` already handles large numbers with M/B suffixes. |
| Managed pets empty in spectator mode makes `top_earners` empty | Medium | Fall back to top_pets with estimated velocity of 0, showing rank by ATK+DEF ratio instead. |
| Cache persistence: top_pets scores are not saved/loaded from disk | Low | Acceptable -- sparklines will be empty on restart, same as current behavior for managed pets. Can improve later. |

## Open Questions

1. **Should "4" be the keybinding or should Overview be "1" and shift others?** Current plan uses "4" to avoid disrupting existing muscle memory. Could renumber later.
2. **Game start date accuracy:** Using March 1, 2024 (1709251200). The actual FrenPet Base deployment may differ by days. Verify against chain data if precision matters.
3. **Top earners without velocity data:** For non-managed pets we have no battle history. Consider querying `win_qty` and `loss_qty` from top pets via Ponder to estimate rates. Deferred -- use ATK+DEF ratio as proxy for now.

---

## File Index

Files to **create** (7):
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/overview/__init__.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/overview/fp_hero_metrics.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/overview/fp_overview_leaderboard.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/overview/fp_score_trends.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/overview/fp_game_signals.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/overview/fp_battle_activity.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/overview/fp_best_plays.py`

Files to **modify** (4):
- `/Library/Vibes/autopull/dashboard/data/frenpet_manager.py` -- add overview_* computed fields
- `/Library/Vibes/autopull/dashboard/data/frenpet_cache.py` -- extend to cache top_pets scores
- `/Library/Vibes/autopull/dashboard/screens/frenpet.py` -- add view 4, keybinding, wiring
- `/Library/Vibes/autopull/dashboard/themes/minimal.tcss` -- add FPOverview CSS rules

Files to **read but not modify** (reference only):
- `/Library/Vibes/autopull/dashboard/templates/` -- all templates (copy patterns from these)
- `/Library/Vibes/autopull/dashboard/screens/bakery.py` -- layout reference
- `/Library/Vibes/autopull/dashboard/widgets/hero_metrics.py` -- HeroBox pattern
- `/Library/Vibes/autopull/dashboard/widgets/cookie_chart.py` -- sparkline function
- `/Library/Vibes/autopull/dashboard/widgets/signals_panel.py` -- signals pattern
- `/Library/Vibes/autopull/dashboard/widgets/ev_table.py` -- two-column table pattern
- `/Library/Vibes/autopull/dashboard/widgets/activity_feed.py` -- RichLog feed pattern

## Agent Assignment

| Agent | Work Packages | Can Start | Dependencies |
|-------|--------------|-----------|--------------|
| Agent A | WP-FP1 (widgets) + WP-FP3 (screen wiring) | Immediately | WP-FP3 depends on WP-FP1 completion |
| Agent B | WP-FP2 (data manager + cache) | Immediately | None |

Both agents can work in parallel. Agent A builds widgets with stub data first, then wires them in. Agent B adds the data pipeline. Integration happens when both finish.

## Validation Plan

1. **Unit:** Each new widget can be instantiated and `update_data()` called with sample data without errors.
2. **Integration:** `FrenPetManager.fetch_and_compute()` returns all `overview_*` keys with correct types.
3. **Visual:** Launch the app, navigate to FrenPet screen, press 4. Verify:
   - Title bar shows pet count
   - 3 hero cards render with data
   - Leaderboard shows 10 rows
   - Sparklines appear after 2+ refresh cycles
   - Signals show 5 metric rows + recommendation
   - Activity feed populates with battle events
   - Best plays shows two columns with 3 rows each
4. **Regression:** Views 1, 2, 3 still work identically. No widget query collisions.
