# MaxPane UI Fix Plan

## Problem

Multiple layout bugs cause wasted space and visual inconsistency across all screens. The root cause is a recurring pattern: containers sized with `height: 1fr` contain only `height: auto` children, so content collapses to the top and the remaining 1fr space sits empty. Secondary issues include excessive padding/margins eating terminal rows, hardcoded separator widths that do not adapt to terminal width, and duplicated sizing rules split between widget `DEFAULT_CSS` and `minimal.tcss`.

## Scope

4 issue types, 3 screen files, 1 theme file, ~45 widget files.

---

## Work Package A: CSS Height + Padding/Margin Fixes (minimal.tcss + frenpet.py DEFAULT_CSS)

**Agent A owns:** `/Library/Vibes/autopull/dashboard/themes/minimal.tcss` and the inline `DEFAULT_CSS` block in `/Library/Vibes/autopull/dashboard/screens/frenpet.py` (lines 72-168).

**Risk:** Medium. These are pure CSS changes with no logic, but a wrong `1fr` assignment on a non-scrollable widget will cause it to stretch with empty space instead of fixing the collapse. Test each screen visually after changes.

### A1. Fix auto-height-in-1fr containers

For each 1fr container below, at least one child must become `height: 1fr`. The best candidate is always the scrollable widget (DataTable, RichLog) or the widget that should expand to fill remaining space. Static info panels stay `auto`.

#### Bakery screen

| Container | Current children (all auto?) | Fix |
|-----------|------------------------------|-----|
| `#right-col` (implicit 1fr as child of `#middle-row`) | CookieChart auto, SignalsPanel auto | Change **SignalsPanel** to `height: 1fr` -- it is the lower panel and should stretch to fill. CookieChart stays auto. |

In `minimal.tcss` change:
```
SignalsPanel {
    height: auto;       -->  height: 1fr;
```

#### FrenPet General view

| Container | Current children | Fix |
|-----------|-----------------|-----|
| `#fp-bottom-row` (1fr) | GameStats auto, `#fp-right-bottom` 1fr | `#fp-right-bottom` is already 1fr -- good. But its children PetsInContext (auto) and MarketConditions (auto) are both auto inside a 1fr Vertical. Change **MarketConditions** to `height: 1fr`. |

In `minimal.tcss` change:
```
MarketConditions {
    height: auto;       -->  height: 1fr;
```

Also: GameStats should become `height: 1fr` so it fills its half of `#fp-bottom-row`:
```
GameStats {
    height: auto;       -->  height: 1fr;
```

#### FrenPet Wallet view (in frenpet.py DEFAULT_CSS)

| Container | Current children | Fix |
|-----------|-----------------|-----|
| `#wallet-mid` (auto, inside ContentSwitcher 1fr > Vertical 1fr) | AggregateStats, divider, ActionQueue -- all auto | This is actually `height: auto` itself so children being auto is fine. But the parent Vertical `#wallet` is `height: 1fr` via ContentSwitcher, and `#wallet-bottom` is `height: 1fr`. The real issue: `#wallet-mid` is auto, which is correct -- it sizes to content. No fix needed here. |
| `#wallet-bottom` (1fr) | WalletActivity, divider, AlertsPanel | WalletActivity DEFAULT_CSS already has `height: 1fr`. AlertsPanel is auto. This is fine -- WalletActivity fills. **No fix needed.** |

#### FrenPet Pet view (in frenpet.py DEFAULT_CSS)

| Container | Current children | Fix |
|-----------|-----------------|-----|
| `#pet-bottom-row` (auto) | TrainingStatus auto, divider, PetSignals auto | Container itself is `height: auto`. This means it collapses. Since this is the bottom section of a 1fr parent Vertical, it should be `height: 1fr` so it takes remaining space. Change `#pet-bottom-row` to `height: 1fr`. Then make **PetSignals** `height: 1fr` and **TrainingStatus** `height: 1fr` so they fill equally. |

In `frenpet.py` DEFAULT_CSS change:
```
#pet-bottom-row { height: auto;  -->  height: 1fr; }
```

In the frenpet widget DEFAULT_CSS files, TrainingStatus and PetSignals both have `height: auto` -- but since minimal.tcss does not define them, they need updating in their own DEFAULT_CSS. However, since Agent B owns widget files, coordinate: Agent A changes the container height in frenpet.py, Agent B changes widget heights. **Alternative:** Agent A adds rules for TrainingStatus and PetSignals to frenpet.py's DEFAULT_CSS block. This avoids cross-agent conflict.

Add to frenpet.py DEFAULT_CSS:
```css
TrainingStatus { height: 1fr; }
PetSignals { height: 1fr; }
```

#### Base Terminal Trending view

| Container | Current children | Fix |
|-----------|-----------------|-----|
| `#bt-trending-top` (1fr) | TrendingTable (`bt-trending-table`), PriceSparklines (`bt-sparklines`) | TrendingTable has `height: 1fr` in both DEFAULT_CSS and minimal.tcss -- good. PriceSparklines is `height: auto`. **No fix needed** -- TrendingTable already fills. |
| `#bt-trending-bottom` (1fr) | `#bt-trending-bl` (1fr Vertical), GeckoPools (auto) | Inside `#bt-trending-bl`: TopMovers auto, VolumeBars auto -- both auto in a 1fr Vertical. Change **VolumeBars** to `height: 1fr`. GeckoPools should also be `height: 1fr` to fill its share of the bottom row. |
| `#bt-sparklines` (width: 2fr, no height set) | PriceSparklines is the widget itself, placed directly. Its height is auto. The container `#bt-sparklines` has no height rule in minimal.tcss. Since it is a child of `#bt-trending-top` (1fr Horizontal), it inherits stretch. But PriceSparklines inside has `height: auto`. Since `#bt-sparklines` is just an id on PriceSparklines itself (see base_terminal.py line 90), the widget IS the container. Change PriceSparklines height to 1fr so it fills. |

In `minimal.tcss` change:
```
VolumeBars { height: auto;      -->  height: 1fr; }
GeckoPools { height: auto;      -->  height: 1fr; }
PriceSparklines { height: auto; -->  height: 1fr; }
```

#### Base Terminal Token Detail view

| Container | Current children | Fix |
|-----------|-----------------|-----|
| `#bt-token-bottom` (1fr) | `#bt-token-left` (1fr Vertical), TradeFeed | Inside `#bt-token-left`: PoolInfo auto, TokenSignals auto -- both auto in 1fr. Change **TokenSignals** to `height: 1fr`. TradeFeed has no height in minimal.tcss but DEFAULT_CSS sets `height: 1fr` -- good. |

In `minimal.tcss` change:
```
TokenSignals { height: auto;    -->  height: 1fr; }
```

#### Base Terminal Fee Monitor view

| Container | Current children | Fix |
|-----------|-----------------|-----|
| `#bt-fee-top` (1fr) | FeeClaims (2fr width), FeeLeaderboard (1fr width, auto height) | FeeClaims DEFAULT_CSS has `height: 1fr` but minimal.tcss has no height for it (it inherits). FeeLeaderboard is `height: auto` in minimal.tcss. Change **FeeLeaderboard** to `height: 1fr`. |
| `#bt-fee-bottom` (auto) | FeeStats auto, `#bt-fee-alerts` auto | Container is auto -- should be `height: 1fr` to fill remaining space. Change `#bt-fee-bottom` to `height: 1fr`. Then change **FeeStats** to `height: 1fr`. |

In `minimal.tcss` change:
```
FeeLeaderboard { height: auto;  -->  height: 1fr; }
#bt-fee-bottom { height: auto;  -->  height: 1fr; }
FeeStats { height: auto;        -->  height: 1fr; }
#bt-fee-alerts { height: auto;  -->  height: 1fr; }
```

#### Base Terminal Overview view

| Container | Current children | Fix |
|-----------|-----------------|-----|
| OverviewPanel (1fr) | `#ov-hero` auto, `#ov-sparklines` auto, `#ov-sep` 1 row, `#ov-bottom` auto | `#ov-bottom` should be `height: 1fr`. Its children `#ov-left` and `#ov-right` should also be `height: 1fr`. |

In `minimal.tcss` change:
```
#ov-bottom { height: auto;  -->  height: 1fr; }
#ov-left { height: auto;    -->  height: 1fr; }
#ov-right { height: auto;   -->  height: 1fr; }
```

### A2. Reduce padding/margin waste

#### ContentSwitcher padding

Current: `padding: 1 2` (wastes 2 rows -- 1 top, 1 bottom).
Change to: `padding: 0 1`

In `minimal.tcss` (line 624):
```
ContentSwitcher { padding: 1 2;  -->  padding: 0 1; }
```

#### View selector margins

Current `#fp-view-selector`: `margin: 1 0` (wastes 2 rows).
Change to: `margin: 0 0 1 0` (1 row bottom only).

Current `#bt-view-selector`: `margin: 1 0` (wastes 2 rows).
Change to: `margin: 0 0 1 0` (1 row bottom only).

In `minimal.tcss`:
```
#fp-view-selector { margin: 1 0;  -->  margin: 0 0 1 0; }
#bt-view-selector { margin: 1 0;  -->  margin: 0 0 1 0; }
```

### A -- Summary of all minimal.tcss edits

```
Line  93: CookieChart      height: auto       (keep -- no change)
Line 103: SignalsPanel      height: auto  -->  height: 1fr
Line 244: PriceSparklines   height: auto  -->  height: 1fr
Line 254: TopMovers         height: auto       (keep -- no change)
Line 264: VolumeBars        height: auto  -->  height: 1fr
Line 275: GeckoPools        height: auto  -->  height: 1fr
Line 388: TokenPrice        height: auto       (keep -- no change)
Line 404: TokenChart        height: auto       (keep -- no change)
Line 420: PoolInfo          height: auto       (keep -- no change)
Line 448: TokenSignals      height: auto  -->  height: 1fr
Line 493: #ov-bottom        height: auto  -->  height: 1fr
Line 499: #ov-left          height: auto  -->  height: 1fr
Line 505: #ov-right         height: auto  -->  height: 1fr
Line 534: #bt-fee-bottom    height: auto  -->  height: 1fr
Line 541: #bt-fee-alerts    height: auto  -->  height: 1fr
Line 577: FeeLeaderboard    height: auto  -->  height: 1fr
Line 589: FeeStats          height: auto  -->  height: 1fr
Line 624: ContentSwitcher   padding: 1 2  -->  padding: 0 1
Line 619: #fp-view-selector margin: 1 0   -->  margin: 0 0 1 0
Line 185: #bt-view-selector margin: 1 0   -->  margin: 0 0 1 0
Line 738: GameStats         height: auto  -->  height: 1fr
Line 765: MarketConditions  height: auto  -->  height: 1fr
```

### A -- frenpet.py DEFAULT_CSS edits

```
#pet-bottom-row   height: auto  -->  height: 1fr
```

Add new rules inside the DEFAULT_CSS block:
```css
TrainingStatus { height: 1fr; }
PetSignals { height: 1fr; }
```

### A -- Files touched

- `/Library/Vibes/autopull/dashboard/themes/minimal.tcss`
- `/Library/Vibes/autopull/dashboard/screens/frenpet.py` (DEFAULT_CSS block only)

---

## Work Package B: Separator Fixes + DEFAULT_CSS Cleanup

**Agent B owns:** all screen `.py` files (separator strings) and all widget `.py` files (DEFAULT_CSS dedup).

### B1. Replace hardcoded separator strings

7 instances of `"--- " * N` pattern across 3 screen files. Replace each with an empty Static that gets its visual rule from CSS.

**Pattern:** Keep the Static, clear its text content, apply styling via a shared CSS class.

Add to `minimal.tcss` (coordinate with Agent A -- append at end of file or Agent B can add to a new section):

Actually -- Agent B should NOT touch minimal.tcss. Instead, use existing `#separator`, `#fp-separator`, `#bt-trending-sep`, `#bt-token-sep`, `#bt-fee-sep`, `#ov-sep` rules that already exist in minimal.tcss with `width: 100%; height: 1; color: $panel;`. The CSS rules are already correct. The issue is only the hardcoded text content.

**Fix approach:** Change each separator Static's text from `"\u2500 " * N` to an empty string `""`, then add `border-bottom: solid $panel;` or use the existing `color: $panel` + render a full-width rule via `content-align`. Actually the simplest approach: keep the existing CSS (height: 1, color: $panel) and change the text to use Rich markup `"[dim]" + "\u2500" * 200 + "[/]"` which will get clipped by the container width. Or better: use `"-" * 500` which auto-clips.

**Simplest correct fix:** The separators already have `width: 100%; height: 1` in CSS. Replace the hardcoded content with a single horizontal rule character repeated to an excessive length (the container clips it). Use `"\u2500" * 200`.

Alternatively, for a cleaner approach, give each separator a `border-bottom: solid $panel; height: 1;` CSS rule and set text to `""`. This renders a proper CSS border. But the existing approach (colored text in a 1-row Static) works fine -- the problem is just the `* 40` or `* 50` not being wide enough.

**Recommended: use `"\u2500" * 200` as the text content.** It is simple, the 1-row height clips vertically, and `width: 100%` clips horizontally. No CSS changes needed.

#### Locations to change

| File | Line | Current | New |
|------|------|---------|-----|
| `bakery.py` | 57 | `"\u2500 " * 50` | `"\u2500" * 300` |
| `base_terminal.py` | 93 | `"\u2500 " * 40` | `"\u2500" * 300` |
| `base_terminal.py` | 125 | `"\u2500 " * 40` | `"\u2500" * 300` |
| `base_terminal.py` | 149 | `"\u2500 \u2500 " * 20` | `"\u2500" * 300` |
| `frenpet.py` | 194 | `" \u2500 " * 40` | `"\u2500" * 300` |
| `frenpet.py` | 236 | `" \u2500 " * 40` | `"\u2500" * 300` |
| `frenpet.py` | 250 | `" \u2500 " * 40` | `"\u2500" * 300` |

Also in the overview widget:
| `overview.py` | 167 | `"\u2500 " * 46` | `"\u2500" * 300` |

**Note:** frenpet.py is shared with Agent A (who edits DEFAULT_CSS). Agent B edits only compose() method separator strings. No conflict as long as both agents do not edit the same lines. The DEFAULT_CSS block is lines 72-168; the separator strings are at lines 194, 236, 250. No overlap.

### B2. Clean up DEFAULT_CSS in widgets

Remove `width` and `height` rules from widget `DEFAULT_CSS` blocks when `minimal.tcss` already defines them. Keep only rules that `minimal.tcss` does NOT provide (e.g., `text-style: bold` on title Statics, which minimal.tcss does not set).

**Principle:** `minimal.tcss` is the source of truth for layout (width, height, padding, margin). Widget DEFAULT_CSS should only contain rules that are intrinsic to the widget's rendering (colors, text-style, borders on sub-elements) or needed as a standalone fallback.

#### Widgets where DEFAULT_CSS sizing duplicates minimal.tcss

For each widget below, the DEFAULT_CSS top-level selector sets `width` and/or `height` and/or `padding` that minimal.tcss already defines. Remove the duplicated properties from DEFAULT_CSS.

**Bakery widgets:**
| Widget file | DEFAULT_CSS duplicates | Keep in DEFAULT_CSS |
|-------------|----------------------|---------------------|
| `leaderboard.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove all 3 (minimal.tcss lines 50-53) |
| `cookie_chart.py` | width: 1fr, height: auto, padding: 0 1 | Remove all 3 (minimal.tcss lines 92-95) |
| `signals_panel.py` | (check if has DEFAULT_CSS) | Check and remove |
| `activity_feed.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove all 3 (minimal.tcss lines 130-133) |
| `ev_table.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove all 3 (minimal.tcss lines 145-148) |
| `hero_metrics.py` | (check) | Check and remove |
| `status_bar.py` | dock, width, height, background, padding | Remove sizing (minimal.tcss lines 157-162) |

**Base Terminal widgets:**
| Widget file | DEFAULT_CSS duplicates | Action |
|-------------|----------------------|--------|
| `trending_table.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove (minimal.tcss lines 225-228) |
| `price_sparklines.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 243-246) |
| `top_movers.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 253-256) |
| `volume_bars.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 263-267) |
| `gecko_pools.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 274-278) |
| `launch_feed.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove (minimal.tcss lines 304-307) |
| `launch_stats.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 322-326) |
| `graduated.py` | width: 1fr, height: auto, padding: 0 1, margin | Remove (minimal.tcss lines 334-339) |
| `token_price.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 384-388) |
| `token_chart.py` | width: 2fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 401-405) |
| `pool_info.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 418-422) |
| `trade_feed.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove (minimal.tcss lines 430-433) |
| `token_signals.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 446-449) |
| `fee_claims.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove (minimal.tcss lines 558-561) |
| `fee_leaderboard.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 574-578) |
| `fee_stats.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 586-590) |
| `overview.py` | width: 100%, height: 1fr, padding: 0 0 | Remove (minimal.tcss lines 461-465) |

**FrenPet widgets:**
| Widget file | DEFAULT_CSS duplicates | Action |
|-------------|----------------------|--------|
| `population.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 668-672) |
| `score_dist.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 681-685) |
| `top_leaderboard.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove (minimal.tcss lines 694-697) |
| `battle_feed.py` | width: 1fr, height: 1fr, padding: 0 1 | Remove (minimal.tcss lines 713-716) |
| `game_stats.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 735-739) |
| `pets_in_context.py` | width: 1fr, height: auto, padding: 0 1 | Remove (minimal.tcss lines 748-752) |
| `market_conditions.py` | width: 1fr, height: auto, padding: 0 1, margin | Remove (minimal.tcss lines 760-766) |
| `pet_stats.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `score_trend.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `next_actions.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `battle_log.py` | width: 1fr, height: 1fr, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `target_landscape.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `sniper_queue.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `training_status.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `pet_signals.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `aggregate_stats.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `action_queue.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `alerts.py` | width: 1fr, height: auto, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `wallet_activity.py` | width: 1fr, height: 1fr, padding: 0 1 | No minimal.tcss rule -- KEEP |
| `pet_card.py` | width: 32, height: 9, border, padding, margin | No minimal.tcss rule -- KEEP |
| `logo.py` | width: auto, height: auto, padding | No minimal.tcss rule -- KEEP |

**What to remove from each DEFAULT_CSS:** Only the top-level widget selector's `width`, `height`, `padding`, and `margin` properties when minimal.tcss has the same selector with those properties. Keep all child-selector rules (title styles, DataTable styles, etc.) and keep rules not present in minimal.tcss.

**Important:** After Agent A changes some `height: auto` to `height: 1fr` in minimal.tcss, the DEFAULT_CSS values would conflict if left in place. Removing the DEFAULT_CSS sizing ensures minimal.tcss is authoritative. This makes Agent A's height changes take effect cleanly.

### B -- Files touched

**Separator fixes (B1):**
- `/Library/Vibes/autopull/dashboard/screens/bakery.py` (line 57)
- `/Library/Vibes/autopull/dashboard/screens/base_terminal.py` (lines 93, 125, 149)
- `/Library/Vibes/autopull/dashboard/screens/frenpet.py` (lines 194, 236, 250)
- `/Library/Vibes/autopull/dashboard/widgets/base/overview.py` (line 167)

**DEFAULT_CSS cleanup (B2):**
- `/Library/Vibes/autopull/dashboard/widgets/leaderboard.py`
- `/Library/Vibes/autopull/dashboard/widgets/cookie_chart.py`
- `/Library/Vibes/autopull/dashboard/widgets/signals_panel.py`
- `/Library/Vibes/autopull/dashboard/widgets/activity_feed.py`
- `/Library/Vibes/autopull/dashboard/widgets/ev_table.py`
- `/Library/Vibes/autopull/dashboard/widgets/hero_metrics.py`
- `/Library/Vibes/autopull/dashboard/widgets/status_bar.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/trending_table.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/price_sparklines.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/top_movers.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/volume_bars.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/gecko_pools.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/launch_feed.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/launch_stats.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/graduated.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/token_price.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/token_chart.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/pool_info.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/trade_feed.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/token_signals.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/fee_claims.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/fee_leaderboard.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/fee_stats.py`
- `/Library/Vibes/autopull/dashboard/widgets/base/overview.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/population.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/score_dist.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/top_leaderboard.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/battle_feed.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/game_stats.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/pets_in_context.py`
- `/Library/Vibes/autopull/dashboard/widgets/frenpet/market_conditions.py`

---

## Execution Order

```
Agent A (minimal.tcss + frenpet.py DEFAULT_CSS)     Agent B (screens + widgets)
  |                                                    |
  |  A1: height fixes in minimal.tcss                  |  B2: DEFAULT_CSS cleanup in widgets
  |  A2: padding/margin fixes in minimal.tcss          |      (removes sizing that would
  |  A3: frenpet.py DEFAULT_CSS height fixes            |       conflict with A1 changes)
  |                                                    |
  |  (both can run in parallel)                        |  B1: separator string fixes in
  |                                                    |      screen compose() methods
  v                                                    v
```

Agent A and Agent B can run in parallel. No file conflicts:
- Agent A: `minimal.tcss`, `frenpet.py` (DEFAULT_CSS block lines 72-168 only)
- Agent B: all widget `.py` files, screen `.py` files (compose methods only), `overview.py`
- Shared file `frenpet.py`: Agent A edits lines 72-168 (DEFAULT_CSS), Agent B edits lines 194/236/250 (separator strings). No overlap.

**Ordering within Agent B:** Do B2 (DEFAULT_CSS cleanup) BEFORE or simultaneously with B1 (separators). B2 is important to do before testing because removing the `height: auto` from widget DEFAULT_CSS allows Agent A's `height: 1fr` in minimal.tcss to take effect. If DEFAULT_CSS still says `height: auto`, Textual's specificity rules mean DEFAULT_CSS wins over the external stylesheet for that property. **This is critical: B2 must complete for A1 to work.**

Actually -- in Textual, external CSS files loaded via `CSS_PATH` have HIGHER specificity than `DEFAULT_CSS`. So Agent A's minimal.tcss changes will override DEFAULT_CSS regardless. B2 is a cleanup for maintainability, not a blocker for A1. Confirmed: Textual specificity order is DEFAULT_CSS < CSS_PATH < inline styles.

---

## Risks and Unknowns

1. **SignalsPanel stretching:** If SignalsPanel is set to `height: 1fr` but only renders 4-5 lines of text, it may look odd with empty space below the text. Acceptable tradeoff -- it prevents the worse problem of collapsed content with a gap after `#right-col`.

2. **FeeStats / FeeLeaderboard as 1fr:** These are Static-based info panels. Making them 1fr means their text sits at the top of a tall box. If this looks bad, an alternative is to wrap them in a scrollable container or add `content-align: left top` (which is default anyway). Monitor after implementation.

3. **Overview panel children:** `#ov-left` and `#ov-right` are plain Statics. Making them 1fr gives them stretch but they render Rich text from the top down. Should be fine.

4. **DEFAULT_CSS removal safety:** If the app is ever run without `minimal.tcss` (unlikely but possible), widgets would lose their sizing. This is acceptable -- the app requires the theme file.

5. **Separator overflow:** `"\u2500" * 300` is 300 chars. On terminals wider than 300 columns this would not span fully. 300 columns is well beyond any realistic terminal width. Safe.

---

## Validation Plan

After both agents complete:

1. Launch the app and cycle through all 3 screens (Bakery, FrenPet, Base Terminal).
2. For each screen, verify:
   - No empty gaps between sections (the 1fr fix)
   - Scrollable widgets (DataTable, RichLog) expand to fill available space
   - Separators span the full terminal width
   - View selectors have minimal vertical padding (1 row gap below, not above)
3. Resize the terminal to various widths (80, 120, 200 columns) and verify separators adapt.
4. Switch between all FrenPet views (1/2/3) and all Base Terminal views (1-5).
5. Confirm no visual regressions on the Bakery screen.
