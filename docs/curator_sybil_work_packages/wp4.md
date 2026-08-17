# WP4 — The third view: `MODE_ANALYSIS` (key `f`), three panels, width sweep, export

**Goal:** A third body on THE LIST — `MODE_ANALYSIS`, toggled by `f` — holding the OPERATORS,
SEGMENTS and CLEANED-LIST panels, all pattern-language, with the hero (doomsday clock) left in
place. Add the `e` export action, the `minimal.tcss` mirror block, and a **measured** width
that does not move `__main__.FULL_LAYOUT_COLUMNS`.

**Dependencies:** WP0 (the new keys/rows + the routing table), WP5 (the graded leaderboard flag
and the `y`-view linked line must exist before the full-screen width is pinned; WP4 consumes
WP5's hand-off for the wallet widgets' new kwargs). Runs in **wave 2** in parallel with WP2.

**Owner note — this WP owns:**

- `maxpane_dashboard/screens/curator.py` (sole owner — adds `MODE_ANALYSIS`, the `f`/`e`
  bindings, the analysis body compose, three-mode `_show_mode`, `WIDGET_SIGNATURES` entries for
  the three new panels **and** the wallet widgets' new kwargs, the width sweep, the export)
- `maxpane_dashboard/themes/minimal.tcss` (the curator-analysis additions only — the
  `DEFAULT_CSS`/`minimal.tcss` mirror test compares copies rule by rule)

and **creates:**

- `maxpane_dashboard/widgets/curator/{operators,segments,cleaned_list}.py`
- additions to `tests/screens/test_curator_screen.py` and `tests/widgets/test_curator_widgets.py`

It **must not edit** `widgets/curator/wallet.py` or `leaderboard.py` (WP5's), the manager, the
models, or `app.py`/`game_select.py`/`__main__.py`. It wires the wallet widgets' new kwargs from
**WP0's routing table** and **WP5's hand-off**, never by reading WP5's source.

### Interface consumed (frozen upstream)

- `CURATOR_KEYS` + `CURATOR_ROW_KEYS` (WP0): the new keys and the three row shapes.
- The routing table (WP0.5) and WP5's hand-off: which new key each widget takes.
- WP3's hand-off: the payload states (not-yet-run `None`/`analysis_as_of_hhmm=None`;
  analyzed-none `operators_count=0`; analyzed-linked; degraded last-good).

### Ground rules

- **The screen stays clock-free** — every time string arrives in the payload; a source scan
  already forbids `time.time()`/`datetime.now()` here. The `analysis_as_of_hhmm` marker is a
  payload string.
- **`safe_markup` every third-party string** before it reaches markup or a `DataTable` — the
  operator `reasons` strings and the CLEANED-LIST addresses/names are the attacker-controlled
  ones (a token/ENS symbol can be `[/x]`).
- **Widgets never import `data/` or `analytics/`** — the AST guard covers the three new modules.
- **Pattern-language only** on screen: each new panel gets its **own** composited forbidden-word
  render test.
- **Width is measured, never reasoned** — re-sweep after any copy edit; the analysis body is a
  new layout and gets its own sweep, exactly like the `y`-view precedent.
- Build against WP0's **worst-case** fixtures (`operator_row_worst.json` etc.) so the sweep
  measures the state the data is normally in.
- Commit after each task.

---

### Task WP4.1: `CuratorOperators` widget

**Interfaces:** `update_data(operator_rows=None, operators_count=None,
flagged_points_share_pct=None, analysis_as_of_hhmm=None, **_kwargs)`. Columns per
`CURATOR_ROW_KEYS["operator_rows"]`: `size · reasons · points · points_share_pct ·
sqrt_subsidy_x · conf`. One row per operator, widest first (PRD §5.1):
`1,995 linked · 0.45Ξ ×N · 2-blk cadence · shared funder   6.8%   44×`.

**Steps:**

- [ ] Failing tests (composited): the worst-case operator renders with its size, its
      pattern-language reasons, `6.8%`, `44×`; `conf` renders as a filled/hollow marker
      (`⚑`/`◌`), **never a raw number that reads as a verdict** (PRD §5.1); `operators_count is
      None` renders `analysis unavailable` while `operators_count == 0` renders `no linked
      groups found` (the representable-zero vs could-not-analyze distinction — the FARM-row
      precedent); `analysis_as_of_hhmm` renders `as of HH:MM`; the panel's own **pattern-language
      render test** (forbidden words `sybil/cheat/fraud/attack/abuse/wash`) — its own copy, PRD
      §8; a hostile `reasons` string (`"[/x]"`) renders literally, not `MarkupError`; width tiers
      shed the block/`sqrt_subsidy` columns first with `‹ widen`.
- [ ] Implement on the shared `_table` tiers; `safe_markup` every cell; `visible_len` for width
      decisions.
- [ ] **Bite:** remove a `safe_markup` and pass `reasons=["[/x]"]` → the hostile-string test
      reddens. Restore.
- [ ] Commit: `feat(curator): OPERATORS panel with pattern-only language and a verdict-free grade`

---

### Task WP4.2: `CuratorSegments` widget

**Interfaces:** `update_data(segment_rows=None, analysis_as_of_hhmm=None, **_kwargs)`. Columns
per `CURATOR_ROW_KEYS["segment_rows"]`: `label · contributors · points_share_pct · detail`
(PRD §5.2 — whale operators, per-hour bands, per-multiplier bands, the index-1000 early cohort).

**Steps:**

- [ ] Failing tests (composited): the "largest operators" and "early cohort" labels render
      (pattern-language, **never** "whale sybil"); the index-1000 cohort's `7.6%` renders; a
      `None` list renders `segments unavailable`, `[]` renders `no segments yet`; its own
      pattern-language render test; `analysis_as_of_hhmm`.
- [ ] Commit: `feat(curator): SEGMENTS panel — operator/temporal/multiplier bands`

---

### Task WP4.3: `CuratorCleanList` widget + the export

**Interfaces:** `update_data(clean_list_rows=None, clean_points=None, clean_contributors=None,
you_clean_rank=None, analysis_as_of_hhmm=None, clean_list_export_path=None, **_kwargs)`.
`clean_list_export_path` is the **screen-supplied** value (plan §6 risk 1) — set after `e`, not
a manager key. Columns per `CURATOR_ROW_KEYS["clean_list_rows"]`: `clean_rank · address ·
points · credit_eth · name`.

**Steps:**

- [ ] Failing tests (composited): `total points` vs `clean points` (farm groups removed) and the
      survivor count render (PRD §5.3); **your clean rank** renders when `you_clean_rank` is set
      and shows `set a wallet` otherwise; after export, `clean_list_export_path` renders the
      written path; `None`/`[]` distinct states; its own pattern-language render test; addresses
      `safe_markup`-escaped and `NAME_COLS`-capped like the leaderboard.
- [ ] The **export writer** is a small helper on the screen (WP4.6), not the widget; the widget
      only renders the path it is handed. Note that in the module docstring.
- [ ] Commit: `feat(curator): CLEANED LIST panel with clean-rank and an export path line`

---

### Task WP4.4: `MODE_ANALYSIS` screen plumbing

**Interfaces:** extend the existing three-file mode machinery in `screens/curator.py`:
`MODE_ANALYSIS = "analysis"`, `MODES = (MODE_DASHBOARD, MODE_WALLET, MODE_ANALYSIS)`,
`ANALYSIS_BODY_ID = "curator-analysis-body"`, the `f` binding
(`Binding("f", "toggle_analysis", "Linked", show=True)`), and the `e` binding scoped to the
analysis mode.

**The hero stays in place (PRD §5):** unlike `MODE_WALLET` (which swaps to `CuratorWalletHero`),
`MODE_ANALYSIS` keeps the **dashboard** `CuratorHero` visible — the doomsday clock never leaves
the screen. So `_show_mode` must handle three modes:

| mode | dashboard hero | dashboard body | wallet hero | wallet body | analysis body |
|---|---|---|---|---|---|
| `dashboard` | on | on | off | off | off |
| `wallet` | off | off | on | on | off |
| `analysis` | **on** | off | off | off | on |

**Steps:**

- [ ] Read the current `_show_mode`, `action_toggle_mode` (`y`), `action_back_to_dashboard`
      (`esc`) — they already handle two modes; extend to three.
- [ ] Failing tests: `f` toggles into `MODE_ANALYSIS` and back; `esc` backs out one-way from
      analysis to dashboard (the existing `action_back_to_dashboard` handles "any non-dashboard
      → dashboard", so confirm it covers analysis); the **dashboard hero is still displayed** in
      analysis mode (`test_the_clock_never_leaves_the_screen_in_the_analysis_view`); the three
      analysis panels are composed once and shown by `display` (the `y`-view precedent — no
      blank first frame); `f` on the dashboard and `y`→`f` transitions behave; footer help gains
      `f`.
- [ ] Extend `compose` with a `Vertical(id=ANALYSIS_BODY_ID)` holding the three panels (a layout
      the width sweep will decide — likely OPERATORS full-width over a SEGMENTS | CLEANED-LIST
      row, or three stacked; measure in WP4.7). Extend `_show_mode`, `on_mount`,
      `on_screen_resume`.
- [ ] Add the three panels to the `_do_refresh` dispatch loop and to `WIDGET_SIGNATURES`
      (from WP0's routing table). **Also add the wallet widgets' new kwargs** (`you_linked_*`,
      `you_clean_rank`) to the existing `CuratorWalletStanding` signature entry — from WP5's
      hand-off — so the totality test passes.
- [ ] **Bite:** drop one analysis panel's `WIDGET_SIGNATURES` entry → the dispatch totality test
      fails with `contract keys reach no widget: [...]`. Restore.
- [ ] Commit: `feat(curator): MODE_ANALYSIS body toggled by f, hero left in place`

---

### Task WP4.5: The `f`/`e` bindings and the export action

**Steps:**

- [ ] `action_toggle_analysis()` mirrors `action_toggle_mode`: into `MODE_ANALYSIS` from
      dashboard, back to dashboard if already there. It does **not** require a wallet (the
      OPERATORS/SEGMENTS panels are about the population; only the CLEANED-LIST "your clean rank"
      line needs one, and it degrades to `set a wallet`).
- [ ] `action_export_clean_list()` (`e`): **only acts in `MODE_ANALYSIS`** (a no-op elsewhere,
      so the key never swallows an escape meant for something else). Writes
      `~/.maxpane/curator_clean_list.json` (+ `.csv`) from the payload's `clean_list_rows`, then
      hands the CLEANED-LIST widget the written path. The write is an explicit user action
      matching the read-only-chain / local-file-ok ethic (the `WalletInputScreen`/cache
      precedent); it never touches the chain.
- [ ] Failing tests: `e` in dashboard mode is a no-op; `e` in analysis mode writes both files
      to a **tmp path** (inject the home dir, like the cache tests) and the widget then renders
      the path; the JSON is `clean_list_rows`-shaped; escaping/entering behaves.
- [ ] Commit: `feat(curator): f toggles the analysis view, e exports the cleaned list`

---

### Task WP4.6: The three pattern-language render tests

**Steps:**

- [ ] Each of `CuratorOperators`, `CuratorSegments`, `CuratorCleanList` gets its **own** copy of
      the composited forbidden-word test (`tests/widgets/test_curator_widgets.py`), scanning
      `_compositor.render_strips()` output for `sybil/cheat/fraud/attack/abuse/wash` (the
      `CuratorClusters` precedent). PRD §8 mandates one per new third-view widget.
- [ ] Add the three-way exercise (no args / all-`None` / full worst-case payload) to the widget
      contract test, and extend `CURATOR_WIDGET_SIGNATURES` / `_EXPORTED_CLASSES` for the three
      new classes.
- [ ] Commit: `test(curator): pattern-language render tests for the three analysis panels`

---

### Task WP4.7: Measure and pin the analysis-view width

**Steps:**

- [ ] Extend the screen's width sweep to cover `MODE_ANALYSIS` (the new body) alongside the
      existing dashboard + `y`-view sweeps, at two terminal heights (the reserved-gutter lesson).
      The analysis body must clear at `CURATOR_FULL_LAYOUT_COLUMNS` (currently 138) or advertise
      `‹ widen` per column; **it must not raise `FULL_LAYOUT_COLUMNS` (143)**. If a panel cannot
      clear, shed a column with `‹ widen`, re-sweep.
- [ ] Because WP5's graded leaderboard flag and `y`-view linked line change those panels'
      widths, **run this pin AFTER WP5 has landed** (WP5 is wave 1; WP4 is wave 2 — the ordering
      holds). Re-derive `CURATOR_FULL_LAYOUT_COLUMNS` if the analysis body binds wider than the
      dashboard body; record which panel is the last one asking for a column
      (`_panels_asking_for_width`), not in prose.
- [ ] Mirror the layout into `minimal.tcss` as a `/* curator analysis body */` addition and
      update the `DEFAULT_CSS`/`minimal.tcss` mirror test so the two copies agree rule by rule
      (the existing curator-block mirror test). **No vertical padding** that would clip a panel's
      last row.
- [ ] Failing tests: `test_the_analysis_view_clears_the_measured_width`;
      `test_the_analysis_view_advertises_rather_than_truncating` at width−N;
      `test_curator_fits_inside_the_documented_app_width` still holds (`CURATOR_FULL_LAYOUT_COLUMNS
      <= FULL_LAYOUT_COLUMNS`).
- [ ] If the analysis body genuinely cannot clear ≤143, **do not raise the constant** — report
      the number to WP6 with the binding panel named, so WP6 raises `FULL_LAYOUT_COLUMNS`, the
      README width table and the `--font-size` help text together (the base-build WP7.7 rule).
- [ ] Commit: `feat(curator): pin the analysis-view width and mirror the stylesheet`

---

### Task WP4.8: Full-screen + suite green and sign-off

**Steps:**

- [ ] Run `tests/screens/test_curator_screen.py` and `tests/widgets/test_curator_widgets.py`,
      then the full suite. The screen totality test WP0 reddened is green (all new keys
      dispatched); nothing outside curator moved.
- [ ] Confirm the screen source still contains no clock call (the existing scan) and no
      `data/`/`analytics/` import in the three new widgets.
- [ ] Write the WP6 hand-off note: the `f`/`e` bindings and their footer strings, the three
      panel titles and unavailable-state strings, the export path, and whether
      `CURATOR_FULL_LAYOUT_COLUMNS` moved (so WP6 decides the `FULL_LAYOUT_COLUMNS`/README/
      CLAUDE.md width sentence).
- [ ] Commit: `test(curator): WP4 sign-off — the analysis view renders, exports and fits`

**Done when:** `f` opens a pattern-language analysis body with the clock still on screen, `e`
exports the cleaned list, each new panel has its own forbidden-word render test, and the width is
swept and pinned without moving the app-wide constant.
