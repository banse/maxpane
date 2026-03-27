# Themes Implementation Plan

**Date:** 2026-03-27
**Status:** Ready for implementation
**Mode:** Standard

---

## Problem Statement

The MaxPane dashboard currently ships a single visual theme (`minimal.tcss`). The game has distinct aesthetic contexts -- financial terminal users, system-monitor fans, retro-game enthusiasts, and the actual rugpullbakery.com brand -- and the dashboard should let users pick the one that fits. There is no runtime theme switching and the existing `--theme` CLI argument is accepted but ignored.

## What Exists Today

- **One theme file:** `/Library/Vibes/autopull/dashboard/themes/minimal.tcss` (163 lines)
- **Hardcoded CSS path:** `app.py` line 24 sets `CSS_PATH` to `minimal.tcss` unconditionally
- **CLI arg exists but is dead:** `__main__.py` accepts `--theme` with choices `[minimal, bloomberg, htop, retro]` but never passes it to `MaxPaneApp`
- **Widget structure is stable:** 7 widgets with well-defined CSS selectors (see inventory below)
- **Textual CSS model:** `App.CSS_PATH` is read at class definition time; runtime switching requires calling `app.stylesheet.read()` or similar after swapping the path. Textual 0.x+ supports `app.dark` toggling and stylesheet reloading.

## CSS Selector Inventory

All theme files must style these selectors. Layout properties (width, height, fr ratios, dock) should be copied verbatim from `minimal.tcss`; only colors, borders, text-style, and padding/margin may vary.

| Selector | Widget | Notes |
|---|---|---|
| `Screen` | Root | background, color |
| `#title-bar` | Static | background, color, text-style |
| `HeroMetrics` | Horizontal | height, padding, margin |
| `HeroBox` | Static | border, padding, background, text-align |
| `#middle-row` | Horizontal | height, margin |
| `Leaderboard` | Vertical | width, padding |
| `Leaderboard > Static` | Title | color |
| `Leaderboard DataTable` | DataTable | background, scrollbar |
| `DataTable > .datatable--header` | Built-in | background, color, text-style |
| `DataTable > .datatable--cursor` | Built-in | background, color |
| `DataTable > .datatable--even-row` | Built-in | background |
| `DataTable > .datatable--odd-row` | Built-in | background |
| `#right-col` | Vertical | width, padding |
| `CookieChart` | Vertical | height, padding |
| `CookieChart > .chart-title` | Static | color |
| `SignalsPanel` | Vertical | height, padding, margin |
| `SignalsPanel > .signals-title` | Static | color |
| `#separator` | Static | color, padding |
| `#bottom-row` | Horizontal | height |
| `ActivityFeed` | Vertical | width, padding |
| `ActivityFeed > .feed-title` | Static | color |
| `ActivityFeed RichLog` | RichLog | background, scrollbar |
| `EVTable` | Vertical | width, padding |
| `EVTable > .ev-title` | Static | color |
| `StatusBar` | Horizontal | background, color, dock, height |

## Constraints

1. **Colors and borders only.** Themes must not alter layout (widths, heights, fr ratios, dock positions). This keeps all themes structurally compatible with the same widget tree.
2. **No widget code changes for theming.** Rich markup colors inside widgets (green/red/yellow for indicators) are semantic and should remain as-is. Theme CSS controls the chrome, not inline data colors.
3. **All 5 themes must use identical selector sets.** Copy the full selector list from `minimal.tcss` into each new file so nothing falls through to DEFAULT_CSS.
4. **`bakery` theme is new scope.** The CLI choices list currently has `[minimal, bloomberg, htop, retro]`. It needs `bakery` added.

## Unknowns and Risks

| Item | Impact | Mitigation |
|---|---|---|
| Textual stylesheet hot-reload mechanism | Medium -- if `app.stylesheet` reload is unreliable, runtime switching breaks | Validate with a spike: load a second `.tcss` and call `app.stylesheet.read()` then `app.refresh(layout=True)`. Fallback: clear and re-read via `app._css_has_errors`. |
| DEFAULT_CSS in widgets vs theme CSS precedence | Low -- Textual merges DEFAULT_CSS with app CSS; app CSS wins for matching selectors | Each theme must explicitly set every property that DEFAULT_CSS sets, so app-level always overrides. Verified: `minimal.tcss` already does this for all widgets. |
| Rich markup colors baked into widget code | Low -- `[green]`, `[red]`, `[yellow]` in update_data methods are semantic, not theme colors | Leave them alone. They render as ANSI colors which look acceptable on any background. Only the bloomberg theme might want amber instead of green, but that requires widget code changes and is out of scope. |
| bakery theme on dark terminals | Low -- beige/peach backgrounds will look jarring on terminals expecting dark themes | Acceptable tradeoff. The bakery theme is intentionally light/warm. Document that it works best on terminals with truecolor support. |

---

## Work Packages

### WP-A: Theme CSS Files (parallelizable)

Create four new `.tcss` files in `/Library/Vibes/autopull/dashboard/themes/`. Each file copies the full selector structure from `minimal.tcss` and changes only color, border, and spacing values.

#### WP-A1: `bloomberg.tcss`

**Aesthetic:** Dense financial terminal. Think Bloomberg Terminal, monospace green-on-black.

| Property | Value |
|---|---|
| Screen background | `#0a0a0a` (near-black) |
| Screen color | `#00ff00` (terminal green) |
| Title bar bg | `#1a1a1a` |
| Title bar color | `#ff8c00` (amber) |
| Hero box border | `thin #333333` |
| Hero box bg | `#111111` |
| Section titles | `#ff8c00` (amber) |
| DataTable header bg | `#1a1a1a` |
| DataTable header color | `#ff8c00` |
| DataTable even row | `#0a0a0a` |
| DataTable odd row | `#0f0f0f` |
| DataTable cursor | `#1a3a1a` (dark green highlight) |
| Separator | `#333333` |
| Status bar bg | `#1a1a1a` |
| Status bar color | `#00ff00` |
| Borders throughout | `thin` (not solid -- thinner for density) |

#### WP-A2: `htop.tcss`

**Aesthetic:** System monitor. Dark background, multi-colored text, high-contrast.

| Property | Value |
|---|---|
| Screen background | `#000000` (true black) |
| Screen color | `#ffffff` |
| Title bar bg | `#00008b` (dark blue, like htop header) |
| Title bar color | `#ffffff` |
| Hero box border | `solid #005f87` |
| Hero box bg | `#000000` |
| Section titles | `#00ffff` (cyan) |
| DataTable header bg | `#00008b` |
| DataTable header color | `#ffffff` bold |
| DataTable even row | `#000000` |
| DataTable odd row | `#0a0a1a` |
| DataTable cursor | `#00008b` |
| Separator | `#005f87` |
| Status bar bg | `#00008b` |
| Status bar color | `#00ffff` |
| Borders | `solid` with blue tones |

#### WP-A3: `retro.tcss`

**Aesthetic:** RPG game UI. Double-line borders, bright fantasy colors, dark background.

| Property | Value |
|---|---|
| Screen background | `#0d0221` (deep purple-black) |
| Screen color | `#f0e68c` (khaki/gold text) |
| Title bar bg | `#1a0533` |
| Title bar color | `#ff6ec7` (hot pink) |
| Hero box border | `double #ff6ec7` |
| Hero box bg | `#1a0533` |
| Section titles | `#00ffff` (cyan, RPG menu feel) |
| DataTable header bg | `#1a0533` |
| DataTable header color | `#ff6ec7` |
| DataTable even row | `#0d0221` |
| DataTable odd row | `#140330` |
| DataTable cursor | `#2a0a4a` |
| Separator | `#ff6ec7` |
| Status bar bg | `#1a0533` |
| Status bar color | `#00ffff` |
| Borders | `double` throughout for RPG frame feel |

#### WP-A4: `bakery.tcss`

**Aesthetic:** Warm brand theme matching rugpullbakery.com. Light background, blue/pink/peach accents.

| Property | Value |
|---|---|
| Screen background | `#fff8f5` (light beige) |
| Screen color | `#484646` (brand grey) |
| Title bar bg | `#1b96ca` (brand blue) |
| Title bar color | `#ffffff` |
| Hero box border | `solid #DC8360` (peach) |
| Hero box bg | `#ffdbcc` (beige) |
| Section titles | `#1b96ca` (brand blue) |
| DataTable header bg | `#1b96ca` |
| DataTable header color | `#ffffff` |
| DataTable even row | `#fff8f5` |
| DataTable odd row | `#ffdbcc` |
| DataTable cursor | `#ebf8fd` (light blue) |
| Separator | `#DC8360` |
| Status bar bg | `#1b96ca` |
| Status bar color | `#ffffff` |
| Borders | `solid` with peach tones |

**Estimated effort per theme:** 20-30 minutes each. All four are independent and can be written in parallel.

---

### WP-B: Runtime Theme Switcher

**Goal:** Pressing `t` cycles through all 5 themes. The current theme name is shown in the status bar.

#### Implementation approach -- Option comparison

**Option 1: Reload stylesheet from file (recommended)**

- Store a `THEME_ORDER` list and a `_current_theme_index` on the app
- On `t` keypress, increment index, resolve the new `.tcss` path, and reload
- Reload mechanism: clear `app.stylesheet`, read new file, call `app.stylesheet.reparse()` or use the simpler `app.CSS_PATH = new_path; app._refresh_css()`
- Textual's `App._refresh_css()` (or the public `refresh_css()` in newer versions) handles invalidation

Benefits: Simple, uses Textual's built-in CSS machinery, each theme stays a standalone file.
Drawbacks: Brief visual flicker during reload. Need to verify the exact reload API.
Risk: Low -- this is the pattern Textual's own theme examples use.

**Option 2: Merge all themes into one file with CSS variables**

- Define CSS custom properties per theme, swap variable values at runtime
- Textual's TCSS supports variables via `$variable-name` syntax in the design system

Benefits: No file reload, instant switching.
Drawbacks: Textual's CSS variable system is tied to its `Design` class, not arbitrary custom properties. Would require defining a custom `Design` per theme and calling `app.design = new_design`. More complex, less readable, harder to maintain 5 separate color schemes in one file.
Risk: Medium -- fighting Textual's design system abstractions.

**Recommendation:** Option 1. File-based reload is simpler, keeps themes decoupled, and aligns with how Textual apps typically handle theming.

#### Implementation steps for WP-B

1. Add `THEME_ORDER = ["minimal", "bloomberg", "htop", "retro", "bakery"]` to `app.py`
2. Add `_current_theme_index: int` instance variable, initialized from the `--theme` arg
3. Add a `Binding("t", "cycle_theme", "Theme", show=False)` to `BINDINGS`
4. Implement `action_cycle_theme()`:
   ```
   def action_cycle_theme(self) -> None:
       self._current_theme_index = (self._current_theme_index + 1) % len(THEME_ORDER)
       theme_name = THEME_ORDER[self._current_theme_index]
       theme_path = Path(__file__).parent / "themes" / f"{theme_name}.tcss"
       self.stylesheet.read(theme_path)  # or equivalent reload call
       self.refresh(layout=True)
   ```
5. Update `StatusBar` to show `[t] theme: {name}` in the left section
6. **Spike first:** Before writing the full implementation, verify the exact Textual API for stylesheet reload. The method name varies between Textual versions. Check `app.stylesheet`, `app._refresh_css()`, or `app.CSS_PATH` reassignment behavior.

**Estimated effort:** 1-2 hours including the API spike.

---

### WP-C: Wire `--theme` CLI Arg

**Goal:** `python -m dashboard --theme bloomberg` starts the app with the bloomberg theme loaded.

#### Implementation steps

1. In `__main__.py`, add `"bakery"` to the `choices` list for `--theme`
2. Pass `theme=args.theme` to `MaxPaneApp()`
3. In `MaxPaneApp.__init__()`, accept a `theme: str = "minimal"` parameter
4. Resolve the theme to an index in `THEME_ORDER` and set `self._current_theme_index`
5. Override `CSS_PATH` on the instance (not the class) before Textual reads it:
   ```
   self.css_path = [Path(__file__).parent / "themes" / f"{theme}.tcss"]
   ```
   Note: Textual reads `css_path` (lowercase, list) on the instance during mount. This needs verification during the WP-B spike.

**Estimated effort:** 30 minutes.

---

## Dependency Graph

```
WP-A1 (bloomberg.tcss)  ─┐
WP-A2 (htop.tcss)       ─┤
WP-A3 (retro.tcss)      ─┼──> WP-B (runtime switcher) ──> WP-C (CLI wiring)
WP-A4 (bakery.tcss)     ─┤
                          │
                          └──> (all theme files must exist before switcher can cycle)
```

WP-B and WP-C share code in `app.py` and `__main__.py` so they should be done sequentially. WP-C is a small extension of WP-B.

In practice, WP-B can start in parallel with WP-A using just `minimal.tcss` for testing, then integration-test with all themes once WP-A is complete.

## Recommended Execution Order

1. **WP-B spike** (30 min) -- Verify the Textual stylesheet reload API in an isolated test. This de-risks the entire plan.
2. **WP-A1 through WP-A4** (parallel, 1-2 hours total) -- Write all four theme files.
3. **WP-B full implementation** (1 hour) -- Build the theme cycler using the validated API.
4. **WP-C** (30 min) -- Wire the CLI arg.
5. **Integration test** (30 min) -- Manually cycle through all 5 themes, verify no layout breakage.

## Validation Plan

| Check | Method |
|---|---|
| Each theme loads without CSS parse errors | Start app with `--theme <name>`, check stderr for Textual CSS warnings |
| No layout shifts between themes | Visually compare widget positions across all 5 themes; widths/heights/docks must be identical |
| `t` key cycles through all 5 themes | Press `t` five times, verify each theme appears and wraps back to first |
| `--theme` arg selects correct startup theme | Start with each of the 5 values, verify initial appearance matches |
| Status bar shows current theme name | Verify after startup and after each `t` press |
| Invalid `--theme` value rejected | Run with `--theme invalid`, verify argparse error |

## Files to Create or Modify

| File | Action |
|---|---|
| `dashboard/themes/bloomberg.tcss` | Create (WP-A1) |
| `dashboard/themes/htop.tcss` | Create (WP-A2) |
| `dashboard/themes/retro.tcss` | Create (WP-A3) |
| `dashboard/themes/bakery.tcss` | Create (WP-A4) |
| `dashboard/app.py` | Modify -- add theme state, keybinding, cycle logic (WP-B) |
| `dashboard/__main__.py` | Modify -- add `bakery` choice, pass theme to app (WP-C) |
| `dashboard/widgets/status_bar.py` | Modify -- show current theme name (WP-B) |

## Open Questions

1. **Exact Textual version in use?** The stylesheet reload API differs between 0.x versions. The spike in step 1 resolves this.
2. **Should theme preference persist between sessions?** Currently no persistence is planned -- theme resets to `minimal` (or `--theme` arg) on each launch. A config file could be added later but is out of scope.
3. **Should the bakery theme use the game's font ("Lance Sans")?** Textual renders in the terminal's monospace font. Custom fonts are not possible in TUI. Out of scope.
