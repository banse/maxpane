# Widget Conversion Plan: Static to Proper Textual Widgets

## Problem

The Bakery dashboard aligns correctly because it uses proper Textual layout widgets
(DataTable, HeroBox with `width: 1fr`, RichLog). The FrenPet and Base Terminal
dashboards render tabular and structured data using Static widgets with manually
formatted Rich markup text. This causes alignment issues because:

- Column widths depend on string padding, not layout constraints.
- Terminal width changes break alignment assumptions.
- Zebra striping, row cursors, and scroll behavior are absent.

The goal is to convert widgets that display tabular data to DataTable, and widgets
that display progress-style data to Textual ProgressBar, matching the patterns
already established in `leaderboard.py` and `trending_table.py`.

## Scope

### Files confirmed OK -- no changes needed

These already use DataTable, RichLog, or are simple key-value Statics:

| File | Widget | Why OK |
|------|--------|--------|
| `base/trending_table.py` | TrendingTable | DataTable |
| `base/launch_feed.py` | LaunchFeed | DataTable |
| `base/trade_feed.py` | TradeFeed | RichLog |
| `base/fee_claims.py` | FeeClaims | RichLog |
| `base/launch_stats.py` | LaunchStats | Simple key-value Static |
| `base/pool_info.py` | PoolInfo | Simple key-value Static |
| `base/fee_stats.py` | FeeStats | Simple key-value Static |
| `base/price_sparklines.py` | PriceSparklines | Sparkline text (keep Static) |
| `base/token_chart.py` | TokenChart | Sparkline text (keep Static) |
| `frenpet/top_leaderboard.py` | TopLeaderboard | DataTable |
| `frenpet/battle_feed.py` | BattleFeed | RichLog |
| `frenpet/battle_log.py` | BattleLog | RichLog |
| `frenpet/population.py` | PopulationPanel | Simple key-value Static |
| `frenpet/game_stats.py` | GameStats | Simple key-value Static |
| `frenpet/market_conditions.py` | MarketConditions | Simple key-value Static |
| `frenpet/target_landscape.py` | TargetLandscape | Simple key-value Static |
| `frenpet/training_status.py` | TrainingStatus | Simple key-value Static |
| `frenpet/score_trend.py` | ScoreTrend | Sparkline text (keep Static) |

### Files to convert

17 widgets across 3 independent work packages.

---

## Reference Pattern: DataTable Conversion

The canonical pattern is in `leaderboard.py` and `trending_table.py`. Every table
conversion MUST follow this structure:

```python
class SomePanel(Vertical):
    DEFAULT_CSS = """
    SomePanel > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SomePanel > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TITLE")
        table = DataTable(id="some-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#some-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("Col1", width=N)
        table.add_column("Col2", width=M)

    def update_data(self, ...) -> None:
        table = self.query_one("#some-table", DataTable)
        table.clear()
        for item in data:
            table.add_row(...)
```

Key rules:
- Title is a plain Static above the DataTable.
- DataTable gets `height: 1fr` to fill available space.
- Columns get explicit widths.
- `cursor_type = "row"` and `zebra_stripes = True` for consistency.
- `update_data` calls `table.clear()` then re-adds rows.
- Rich markup in cell values is fine (DataTable renders it).

## Reference Pattern: ProgressBar Conversion

Textual's `ProgressBar` widget is appropriate for countdown/fraction displays.
However, for multi-row progress displays (like NextActions with 4 bars), using
individual ProgressBar widgets composed into a container is cleaner than a single
Static with text bars.

Structure:

```python
from textual.widgets import ProgressBar, Static
from textual.containers import Horizontal, Vertical

class SomeBarPanel(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("TITLE", classes="panel-title")
        with Horizontal(classes="bar-row"):
            yield Static("Label", classes="bar-label")
            yield ProgressBar(total=100, id="bar-1")
            yield Static("", id="bar-1-value", classes="bar-value")
```

Note: Textual ProgressBar does not support color customization per-bar natively.
If color-coded bars are essential, keeping the block-character approach inside a
Static is acceptable -- but the Static should use `width: 1fr` so bars scale to
container width rather than using a hardcoded `_MAX_BAR_WIDTH` constant.

---

## Work Package WP-W1: Base Terminal Table Conversions

**Scope:** Convert 5 files from Static line-building to DataTable.
**Dependencies:** None. All files are independent leaf widgets.
**Risk:** Low. The `update_data` signatures stay the same; only internal rendering changes.

### 1. `base/top_movers.py` -- TopMovers

**Current:** 6 Static widgets (`mover-0` through `mover-5`), each updated individually.
**Target:** Single DataTable with columns.

| Column | Width | Content |
|--------|-------|---------|
| Direction | 3 | Green up-arrow or red down-arrow |
| Token | 10 | Symbol (bold) |
| Change | 8 | Percentage with color |
| MCap | 10 | Formatted market cap |

Steps:
1. Remove the 6 `mover-*` Static widgets from `compose()`.
2. Add a DataTable with id `movers-table`.
3. Add `on_mount` to configure columns.
4. Rewrite `update_data` to `table.clear()` then `table.add_row()` for each gainer/loser.
5. Remove `_MAX_EACH` constant (use row count directly).

### 2. `base/gecko_pools.py` -- GeckoPools

**Current:** 5 Static widgets (`gecko-0` through `gecko-4`), each updated individually.
**Target:** Single DataTable.

| Column | Width | Content |
|--------|-------|---------|
| Pool | 16 | Pair string (TOKEN/WETH) |
| Volume | 10 | Formatted 24h volume |
| Change | 10 | Price change with color |

Steps:
1. Remove `gecko-*` Statics.
2. Add DataTable with id `gecko-table`.
3. Add `on_mount` with 3 columns.
4. Rewrite `update_data` to clear + add_row loop.

### 3. `base/fee_leaderboard.py` -- FeeLeaderboard

**Current:** Single Static body (`fl-body`) with `"\n".join(lines)` of manually padded text.
**Target:** DataTable.

| Column | Width | Content |
|--------|-------|---------|
| # | 4 | Rank number |
| Token | 14 | Token name (bold for top 3) |
| Claimed | 12 | ETH amount |

Steps:
1. Remove `fl-body` Static.
2. Add DataTable with id `fl-table`.
3. Add `on_mount` with 3 columns.
4. Rewrite `update_data` to clear + add_row loop, bold markup on top-3 cells.

### 4. `base/graduated.py` -- GraduatedTokens

**Current:** Single Static body (`graduated-body`) with joined lines.
**Target:** DataTable.

| Column | Width | Content |
|--------|-------|---------|
| Token | 12 | Symbol with $ prefix |
| Price | 14 | Formatted price |
| Change | 10 | Price change with color |

Steps:
1. Remove `graduated-body` Static.
2. Add DataTable with id `graduated-table`.
3. Add `on_mount` with 3 columns.
4. Rewrite `update_data` to clear + add_row loop.

### 5. `base/overview.py` -- OverviewPanel bottom sections

**Current:** Two Statics (`ov-left`, `ov-right`) each containing multi-section text built
with `"\n".join(lines)`. Left has Volume Ranking + Recent Launches. Right has Movers + Trending Pools.

**Target:** Replace the two monolithic Statics with composed containers holding DataTables.

This is the most complex conversion in WP-W1 because:
- Each Static currently holds TWO logical sections.
- The compose tree needs restructuring.

Approach:
1. Replace `Static("", id="ov-left")` with a Vertical containing:
   - Static title "VOLUME RANKING"
   - DataTable id `ov-volume-table` (columns: Token 10, Bar 30, Volume 10)
   - Static title "RECENT LAUNCHES"
   - DataTable id `ov-launches-table` (columns: Name 22, Deployer 12, Age 10)
2. Replace `Static("", id="ov-right")` with a Vertical containing:
   - Static title "MOVERS"
   - DataTable id `ov-movers-table` (columns: Dir 3, Token 12, Change 10, Status 12)
   - Static title "TRENDING POOLS"
   - DataTable id `ov-pools-table` (columns: Pool 16, Volume 10, Change 10)
3. Split `_update_bottom_left` into two methods updating each table.
4. Split `_update_bottom_right` into two methods updating each table.
5. Keep the sparklines section as Static (no conversion needed).
6. Keep the hero cards as-is (already using `_HeroCard` with `width: 1fr`).

Note on the volume bars in overview: the Volume Ranking section currently renders
block-character bars inside text. In a DataTable, we can either:
- (a) Put bar characters in a cell -- simple, keeps visual, but bars are fixed width.
- (b) Drop bars and just show rank + symbol + volume -- cleaner alignment.

**Recommendation:** Option (b). The standalone `volume_bars.py` widget handles the
visual bar display; the overview should be a compact ranked list.

---

## Work Package WP-W2: FrenPet Table and Card Conversions

**Scope:** Convert 5 files.
**Dependencies:** None. Independent of WP-W1 and WP-W3.
**Risk:** Low-medium. `pet_card.py` is a fixed-size card that extends Static directly
rather than Vertical, so the conversion pattern is slightly different.

### 6. `frenpet/sniper_queue.py` -- SniperQueue

**Current:** Single Static body (`sq-content`) with joined lines.
**Target:** DataTable.

| Column | Width | Content |
|--------|-------|---------|
| Pet | 8 | Pet ID (bold) |
| Score | 8 | Formatted score |
| Ratio | 8 | Reward-risk ratio with color |
| Bonkable | 16 | Countdown string or "now" (green) |

Steps:
1. Remove `sq-content` Static.
2. Add DataTable with id `sq-table`.
3. Add `on_mount` with 4 columns.
4. Move candidate filtering logic into `update_data` (unchanged).
5. Replace line-building with `table.add_row()` calls.
6. Hot marker can go in the Bonkable column as markup.

### 7. `frenpet/pets_in_context.py` -- PetsInContext

**Current:** Single Static body (`pic-content`) with joined lines.
**Target:** DataTable.

| Column | Width | Content |
|--------|-------|---------|
| Pet | 8 | Pet ID with percentile color |
| Score | 10 | Formatted score (bold) |
| Rank | 10 | Rank number with color |
| Percentile | 10 | "top N%" with color |

Steps:
1. Remove `pic-content` Static.
2. Add DataTable with id `pic-table`.
3. Add `on_mount` with 4 columns.
4. Rewrite `update_data` to clear + add_row.

### 8. `frenpet/pet_card.py` -- PetCard

**Current:** Extends Static directly. Fixed 32-wide, 9-tall bordered box. Updates with
`self.update("\n".join(lines))`.

**Target:** Convert to a Vertical container with individual Statics for each row, plus
border styling. This gives layout control over each line.

This is NOT a DataTable conversion -- it is a card-style panel.

Approach:
1. Change `PetCard` from `Static` to `Vertical`.
2. Add child Statics for: title, phase+score, atk/def, TOD bar, win/velocity, sparkline.
3. Keep border CSS (`border: solid $secondary`, `width: 32`, `height: 9`).
4. In `update_data`, query each child Static and call `.update()`.

**Alternative considered:** Keep as single Static.
The alignment issue with PetCard is minimal because it has a fixed width (32 chars)
and is not a table. The main benefit of conversion would be if we wanted responsive
width. Since pet cards sit in a fixed Horizontal row, keeping as Static is acceptable.

**Recommendation:** Keep as Static for now. The fixed-width card layout works. Mark
for future conversion only if responsive width becomes a requirement.

### 9. `frenpet/pet_stats.py` -- PetStats

**Current:** Single Static body (`ps-content`) with joined lines of key-value pairs
and a TOD progress bar.

**Target:** Convert to individual Statics per row inside the Vertical container.

Approach:
1. Replace single `ps-content` Static with individual Statics:
   - `ps-score`, `ps-combat`, `ps-tod`, `ps-level`, `ps-shrooms`
2. Each gets `width: 100%` and `padding: 0 1`.
3. `update_data` queries each by ID and updates individually.
4. TOD bar stays as block characters (converting one bar to ProgressBar adds
   complexity without visual benefit here).

**Alternative:** Keep as single Static. The alignment is actually fine for key-value
displays -- the issue is more about consistency.

**Recommendation:** Convert to individual Statics. Low effort, improves the ability
to style individual rows and add future interactivity.

### 10. `frenpet/pet_signals.py` -- PetSignals

**Current:** Single Static body (`psig-content`) with 6 lines of manually spaced
key-value-indicator triples.

**Target:** Individual Statics per signal row, matching the Bakery SignalsPanel pattern.

The Bakery `signals_panel.py` already does this correctly: each signal is its own
Static with a unique ID, updated independently.

Steps:
1. Replace `psig-content` with individual Statics:
   - `psig-efficiency`, `psig-health`, `psig-rank`, `psig-threats`, `psig-velocity`, `psig-recommendation`
2. Each has class `psig-body` for consistent styling.
3. `update_data` queries each by ID.

---

## Work Package WP-W3: Progress Bar Conversions

**Scope:** Convert 3 files to use Textual ProgressBar or width-adaptive bars.
**Dependencies:** None.
**Risk:** Medium. Textual ProgressBar has limited styling options. May need fallback
to block-character bars with `width: 1fr` scaling.

### Assessment: Textual ProgressBar Limitations

After reviewing the current implementations:
- `volume_bars.py` uses colored bars with token labels and volume values on the same line.
- `score_dist.py` uses bars with tier labels and counts.
- `next_actions.py` uses bars with action labels and countdown values.

Textual's `ProgressBar` widget:
- Does not support inline labels.
- Does not support custom colors per bar.
- Renders as its own widget taking a full row.

This means a direct ProgressBar replacement would require a Horizontal container per
bar row: `[Label Static] [ProgressBar] [Value Static]`. This is more widgets and more
CSS than the current approach, with arguable visual improvement.

**Revised recommendation for WP-W3:**

Instead of Textual ProgressBar, fix the underlying alignment problem by making bars
scale to container width rather than using hardcoded `_MAX_BAR_WIDTH` constants.

### 11. `base/volume_bars.py` -- VolumeBars

**Current:** 5 Static widgets with `_MAX_BAR_WIDTH = 20` hardcoded.
**Change:** Make bar width dynamic based on available container width, OR convert to
DataTable with a bar column.

**Option A: DataTable with bar column**

| Column | Width | Content |
|--------|-------|---------|
| Token | 10 | Symbol |
| Bar | 24 | Block characters (scaled to column width) |
| Volume | 10 | Formatted volume |

This gives alignment via DataTable columns while keeping the visual bars.

**Option B: Keep Static, use `width: 1fr`**

Keep the 5 Statics but remove hardcoded bar width. Calculate bar width dynamically
in `update_data` by reading `self.size.width` and subtracting label/value space.

**Recommendation:** Option A (DataTable). Consistent with all other WP-W1 conversions.
The bars become fixed-width within the column but still scale relative to each other.

### 12. `frenpet/score_dist.py` -- ScoreDistribution

**Current:** Single Static body with `_MAX_BAR_WIDTH = 36` hardcoded.
**Change:** Same approach as volume_bars -- DataTable.

| Column | Width | Content |
|--------|-------|---------|
| Tier | 10 | Score range label |
| Bar | 30 | Green block characters |
| Count | 8 | Pet count |

Steps:
1. Replace `dist-content` Static with DataTable.
2. Add `on_mount` with 3 columns.
3. Rewrite `update_data` to clear + add_row with bar characters in cells.

### 13. `frenpet/next_actions.py` -- NextActions

**Current:** Single Static body with 4 rows of label + countdown + block bar.

This one is different from the bar charts. Each row represents a different action
with a different cooldown period. This is NOT tabular data -- it is 4 independent
progress indicators.

**Option A: Individual Statics per action row**

Replace single Static with 4 Statics (`na-stake`, `na-wheel`, `na-battle`, `na-training`).
Keep block-character bars. Each row updates independently.

**Option B: Textual ProgressBar per action**

4 Horizontal containers, each with Label + ProgressBar + Value. More widgets but
native progress rendering.

**Option C: DataTable**

| Column | Width | Content |
|--------|-------|---------|
| Action | 10 | Stake/Wheel/Battle/Training |
| Time | 10 | Countdown or "ready" |
| Bar | 12 | Block characters |

**Recommendation:** Option A. Individual Statics per row. This is the simplest change
that enables independent updates and consistent width. ProgressBar adds complexity
without clear benefit here. DataTable is overkill for 4 fixed rows.

---

## Implementation Steps (per work package)

### WP-W1: Base Terminal Tables

| Step | File | Action |
|------|------|--------|
| 1 | `base/top_movers.py` | Replace 6 Statics with DataTable. Add on_mount. Rewrite update_data. |
| 2 | `base/gecko_pools.py` | Replace 5 Statics with DataTable. Add on_mount. Rewrite update_data. |
| 3 | `base/fee_leaderboard.py` | Replace body Static with DataTable. Add on_mount. Rewrite update_data. |
| 4 | `base/graduated.py` | Replace body Static with DataTable. Add on_mount. Rewrite update_data. |
| 5 | `base/overview.py` | Replace ov-left and ov-right Statics with Vertical containers holding 4 DataTables. Split update methods. |

Estimated effort: Steps 1-4 are straightforward (15 min each). Step 5 is larger (45 min).

### WP-W2: FrenPet Tables and Cards

| Step | File | Action |
|------|------|--------|
| 1 | `frenpet/sniper_queue.py` | Replace body Static with DataTable. Add on_mount. Rewrite update_data. |
| 2 | `frenpet/pets_in_context.py` | Replace body Static with DataTable. Add on_mount. Rewrite update_data. |
| 3 | `frenpet/pet_signals.py` | Replace single body Static with 6 individual Statics (match Bakery SignalsPanel pattern). |
| 4 | `frenpet/pet_stats.py` | Replace single body Static with 5 individual Statics. |
| 5 | `frenpet/pet_card.py` | No change (keep as fixed-width Static card). |

Estimated effort: Steps 1-2 (15 min each). Steps 3-4 (20 min each).

### WP-W3: Bar and Progress Conversions

| Step | File | Action |
|------|------|--------|
| 1 | `base/volume_bars.py` | Replace 5 Statics with DataTable (Token, Bar, Volume columns). |
| 2 | `frenpet/score_dist.py` | Replace body Static with DataTable (Tier, Bar, Count columns). |
| 3 | `frenpet/next_actions.py` | Replace single body Static with 4 individual Statics (na-stake, na-wheel, na-battle, na-training). |

Estimated effort: Steps 1-2 (15 min each). Step 3 (15 min).

---

## Risks and Unknowns

| Risk | Severity | Mitigation |
|------|----------|------------|
| DataTable row cursor may be distracting in panels meant for passive viewing | Low | Set `cursor_type = "none"` instead of `"row"` for non-interactive panels (volume_bars, score_dist). Use `"row"` only for panels where selection might be added later (movers, pools, leaderboard). |
| DataTable `height: 1fr` may cause panels to expand excessively if parent container has no height constraint | Medium | Test each converted widget in its screen layout. Fall back to `height: auto` with `max-height` if needed. |
| Block-character bars inside DataTable cells may render differently than in Static | Low | Test bar rendering in DataTable cells. Rich markup in cells is supported. |
| overview.py compose tree change could break screen CSS selectors | Medium | Check the overview screen CSS for any selectors targeting `#ov-left` or `#ov-right`. Update selectors if needed. |
| ProgressBar was not used anywhere -- deliberately avoided | None | Decision documented above. Block-character bars in DataTable cells or individual Statics are the chosen approach. |

## Validation Plan

For each converted widget:

1. **Visual check:** Launch the dashboard, navigate to the relevant view, confirm columns align.
2. **Data check:** Verify all data fields still render (no missing columns, no truncation).
3. **Resize check:** Resize terminal window, confirm DataTable columns stay aligned.
4. **Empty state:** Verify the "no data" / "loading" state renders correctly.
5. **Theme check:** Switch themes (the app supports multiple), verify colors work.

Run all 3 work packages, then do a full visual pass across:
- Base Terminal View 1 (trending + movers + volume)
- Base Terminal View 3 (token detail with signals)
- Base Terminal View 4 (fee monitor with leaderboard)
- Base Terminal View 5 (overview)
- FrenPet General View (score dist + pets in context)
- FrenPet Pet View (stats + signals + sniper queue + next actions)
- FrenPet Wallet View (pet cards)

## Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Table-like panels | DataTable | Matches bakery pattern. Auto-alignment. Zebra stripes. Scroll. |
| Signal/stat panels | Individual Statics per row | Matches bakery SignalsPanel. Independent updates. Easier styling. |
| Bar charts in tables | DataTable with bar characters in cells | Alignment via columns. Bars still render visually. |
| Progress bars | Block-character bars (not Textual ProgressBar) | ProgressBar lacks inline labels and per-bar color. Overhead exceeds benefit. |
| Pet card | Keep as Static | Fixed-width card. No alignment issue. Convert later if responsive width needed. |
| Overview bottom sections | 4 DataTables in 2 Verticals | Replaces 2 monolithic Statics. Each logical section gets its own table. |
| Non-interactive tables (volume, score_dist) | `cursor_type = "none"` | Avoids distracting cursor on passive-view panels. |
| Interactive tables (movers, pools, sniper, leaderboard) | `cursor_type = "row"` | Enables future row-selection features. |
