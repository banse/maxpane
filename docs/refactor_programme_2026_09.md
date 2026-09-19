# Refactor programme 2026-09 — plan for HANDOVER.md §3 plus two UX items

Owner decisions taken in chat on 2026-09-19. The spec for each branch is the matching
HANDOVER.md §3 paragraph; this file is the plan (sequence, work packages, acceptance tests,
what to leave alone). Each Tier 2 branch: one implementer per work package, reviewer contract
per diff, full suite ONCE by the controller before merge, owner merges. No ledger or report
files; the commit message is the evidence.

## Decisions

1. **Sequence resequenced** from the handover: deletions and hoists first, screens before
   panels, §3.4 and §3.6 each split so no branch migrates more than one risky thing.
2. **Spec depth:** handover paragraph + this plan. No separate spec documents.
3. **Panels are subclass-based** (`class OCMHero(HeroRow)`). Composition (`format_row`
   callable injected) is a later phase — recorded in "Later phases", not done now.
4. **surf / curator / fwa inherit `DashboardScreen` for the lifecycle only** (timer, StatusBar,
   suspend/resume); they keep their custom `_do_refresh`. Their full migration is a later phase.
5. **Two UX items join the programme** (the owner listed them as behaviour NOT to preserve):
   - **Copy.** Cmd+C copies nothing inside MaxPane: Textual owns the mouse, so the terminal
     never has a selection, and Textual's own `ctrl+c` / `super+c` copy goes through OSC 52,
     which Apple Terminal ignores. Fix = BOTH: route Textual's selection copy through
     `clipboard.py` (`pbcopy` first, OSC 52 second, status bar says `copied`), AND copy on
     mouse-up (select-to-copy) so Cmd+C becomes irrelevant. Limitation to state in README:
     Textual text selection covers `Static`-based panels, `Log`, `Markdown`; NOT `DataTable`
     or `RichLog` — leaderboards and feeds keep the `⧉` icon as their copy path.
   - **Links.** MaxPane renders no URLs; "links" are 0x addresses (42 widget files, all through
     `address_text`), transaction hashes (`short_hex`, 4 sites) and ENS names. Click on the
     address/hash TEXT opens the chain's explorer page via `App.open_url` (a Textual `@click`
     action, no terminal support needed) AND the same span carries an OSC 8 hyperlink so
     Cmd+click works in Terminal.app / iTerm2. The `⧉` glyph keeps its copy action. Explorer
     per chain is one field on the dashboard (Etherscan for mainnet, Basescan for Base); the
     icon budget stays at `ICON_COLS = 2`, so no pin moves.

## Branch order

| # | Branch | Handover | Tier | Est. lines removed | Acceptance tests |
|---|---|---|---|---|---|
| 0 | `fix/select-to-copy` | new (UX copy) | 1 | 0 | `tests/test_clipboard*.py`, `tests/screens/test_refresh_guard.py`, one new pilot test |
| 1 | `refactor/dead-base-code` | §3.1 | 2 | ~2,465 | below |
| 2 | `refactor/sanitize-cell` | §3.2 | 2 | ~150 | below (also moves `_rowfit.py` to `widgets/rowfit.py`, shim left) |
| 3 | `refactor/fmt-rowfit` | §3.3 (move already done in 2) | 2 | ~900 | every widget test file that imports a converted helper |
| 4 | `feat/explorer-links` | new (UX links) | 2 | 0 | `tests/test_address_rule.py`, `tests/screens/test_address_icons_everywhere.py`, address sweep |
| 5 | `refactor/dashboard-screen` | §3.5 | 2 | ~1,100 | address sweep + every `tests/screens/test_*_screen.py` migrated |
| 6 | `refactor/panels-ocm` | §3.4a | 2 | small | `tests/widgets/test_panels.py` (new), ocm tests |
| 7 | `refactor/panels-small-four` | §3.4b | 2 | ~2,000 | cattown / dota / talismans / ttt widget + screen tests |
| 8 | `refactor/panels-bt-bakery` | §3.4c | 2 | ~800 | base + bakery tests; templates deleted; `rules/widgets.md` step 3 |
| 9 | `refactor/series-cache` | §3.6a | 2 | ~600 | `tests/data/test_*_cache.py`, `test_series_points.py` |
| 10 | `refactor/rpc-pool` | §3.6b | 2 | ~700 | fixture-first: one committed error-string fixture, classifier tests, then per-client tests |
| 11 | docs | §3.7 | 0 | 0 | doc-pinning tests |

Branch 0 first: it touches `app.py`, `copy_action.py`, `clipboard.py` and one test, nothing
the refactors touch. Branch 4 sits after the hoists and before `DashboardScreen` so the later
screen and panel migrations inherit the link behaviour instead of being retrofitted.

## Branch 1 — `refactor/dead-base-code` (one work package)

Verified 2026-09-19: the 17 top-level modules exported by `widgets/base/__init__.py` have no
reference outside `widgets/base` except three lines in `tests/widgets/test_base_address_icons.py`;
`widgets/base/overview.py` and `overview/_legacy_overview.py` are byte-identical
(md5 `d765cc8e…`); `screens/base_terminal.py` imports only the six `BT*` classes from
`widgets/base/overview`; `OverviewPanel` is imported by nothing but tests.

**Delete** (2,465 lines): `widgets/base/{fee_claims,fee_leaderboard,fee_stats,gecko_pools,
graduated,launch_feed,launch_stats,pool_info,price_sparklines,token_chart,token_price,
token_signals,top_movers,trade_feed,trending_table,volume_bars,volume_sparklines,overview}.py`,
`widgets/base/overview/_legacy_overview.py`, `widgets/base/overview/bt_leaderboard.py`.

**Keep**: `widgets/base/overview/{bt_hero_metrics,bt_overview_leaderboard,bt_sparklines,
bt_signals,bt_activity_feed,bt_best_plays}.py`.

**Edit**:
- `widgets/base/__init__.py` → docstring + the six `BT*` re-exports (or empty; the screen
  imports from `overview`). `widgets/base/overview/__init__.py` → drop the `OverviewPanel` line.
- `themes/minimal.tcss` → remove the orphaned `OverviewPanel` rules (~`:508-580`); nothing
  else in the file. (Shared file, single owner = this package.)
- `widgets/sparkline_common.py` docstring "older copies" list → drop the deleted modules.
- `tests/test_address_rule.py` → drop the entries for deleted files (keep
  `bt_overview_leaderboard`); the set-equality assert must still pass.
- `tests/widgets/test_base_address_icons.py` → delete the tests and MODULES entries for removed
  modules (fee_claims, shadowed overview, `_legacy_overview`, `bt_leaderboard`); keep the
  `bt_overview_leaderboard` and other `BT*` tests; rewrite the module docstring.
- `tests/widgets/test_markup_safety.py` → re-point the `bt_leaderboard` import at
  `bt_overview_leaderboard` (check the assertion still holds against that widget).
- `tests/widgets/test_surf_widget_contract.py:371` comment if it names a deleted file.

**Tests to run** (named files only, no suite): `tests/widgets/test_base_address_icons.py`,
`tests/widgets/test_markup_safety.py`, `tests/widgets/test_title_blank_row.py`,
`tests/widgets/test_sparkline_common.py`, `tests/widgets/test_hidden_shared_address_icons.py`,
`tests/screens/test_base_terminal_screen.py`, `tests/screens/test_address_icons_everywhere.py`,
`tests/test_address_rule.py`, `tests/test_address_sweep_registry.py`,
`tests/test_surf_registration.py`, `tests/test_curator_registration.py`. Then
`.venv/bin/python -c "import maxpane_dashboard.widgets.base, maxpane_dashboard.screens.base_terminal"`
and `rg -n 'widgets\.base\.(fee_|gecko|graduated|launch_|pool_info|price_spark|token_|top_movers|trade_feed|trending|volume_|overview\b)|_legacy_overview|bt_leaderboard\b' maxpane_dashboard tests` must be empty.

**Not in scope**: any change to the six kept widgets' rendering; any pin; `templates/`.

## Branch 2 — `refactor/sanitize-cell` (one work package)

Verified 2026-09-19: the strip-then-escape sanitiser is declared four times in `widgets/surf/`
(`launchpad.py:119-170` — `_TAG_LIKE`, `_flatten`, `_clip` on `len()`, `_sanitize`;
`launchpad_activity.py:210-232` — `_TAG_LIKE`, `_flatten`, `_strip_tags`; `burnkeepers.py:115-128`
— `_TAG_LIKE`, `_strip_tags`; `_pool4.py:210-235` — `_TAG_LIKE`, public `strip_tags`, imported
by 14 surf modules). fwa declares `_MARKUP = re.compile(r"\[/?[^\[\]]*\]")` in
`fwa_settlement_table.py:60` and `fwa_signals.py:71` and **uses neither** (both already import
`markup_safety.visible_len`). No talismans/ttt copies; base's `_strip_non_ascii` is a different
function. Tests name none of the private helpers (only docstrings mention them), so every test
is behavioural and stays as it is.

**Move first** (pulled forward from Branch 3 so the shared module never imports a dashboard
package): `widgets/surf/_rowfit.py` → `widgets/rowfit.py` (`git mv`, no content change beyond
the module docstring's path), and leave `widgets/surf/_rowfit.py` as a re-export shim
(`from maxpane_dashboard.widgets.rowfit import *` plus the explicit names it exports) so the 12
importing modules and 9 test files are untouched. Branch 3 then adds `has_marker()`,
`title_with_hint()`, `Ladder` to the new location and removes the shim.

**Hoist** into `widgets/markup_safety.py` (append-only; `safe_markup` and `visible_len`
unchanged):
- `TAG_LIKE = re.compile(r"\[[^\[\]]*\]")` — a complete `[...]` run with no nested bracket.
- `flatten(value) -> str` — `None` → `""`; `" ".join(str(value).split())`; never raises
  (`_pool4`'s `try` around `str()` is the form to keep).
- `strip_tags(value) -> str` — flatten, `TAG_LIKE.sub("", …)`, re-flatten. Docstring carries the
  rationale from `launchpad.py`'s module docstring and `_pool4.strip_tags`: stripping, not
  merely escaping, because an *escaped* `[/x]` still renders as literal `[/x]`.
- `sanitize_cell(value, width) -> str` — `strip_tags` → `rowfit.clip` (cell-measured, so
  `launchpad.py`'s `len()`-clipped `_clip` is retired: the one behaviour change, and the one the
  handover names) → `safe_markup`. Docstring keeps the fixed-order rationale and the
  mutation-proof note from `launchpad._sanitize`: clip before escape so a cut never bisects an
  escape pair; escape still matters for a lone unmatched `[` that `TAG_LIKE` cannot strip.

**Then, in the four surf modules:** delete the private copies and call the shared names
(`launchpad.py`: `_sanitize(x, w)` → `sanitize_cell(x, w)`, `_flatten` → `flatten`;
`launchpad_activity.py`: `_strip_tags` → `strip_tags`, `_flatten` → `flatten`, keep its
`_clip = _rowfit.clip` / `_pad` aliases; `burnkeepers.py`: `_strip_tags` → `strip_tags`;
`_pool4.py`: drop its definition and **re-export** `strip_tags` from `markup_safety` under the
same name so its 14 importers are untouched). Delete the two dead `_MARKUP` regexes in fwa and
`import re` in `fwa_settlement_table.py` if nothing else uses it (`fwa_signals.py` still does).
Drop the "duplicated here rather than imported … ownership seam" comments: the seam argument
is why the copies existed; the shared module is the contract now.

**Tests to add** (in `tests/widgets/test_markup_safety.py`): `strip_tags` on `None`, embedded
newlines, a complete `[/x]` run, a lone `[`; `sanitize_cell` clips on **cells** (eight CJK
characters into a 10-column budget → `cell_len` ≤ 10 with `…`), escapes what stripping leaves,
and never raises on a non-string. Mutation proofs: (a) `sanitize_cell` clipping on `len()`
again reddens the CJK test; (b) removing the final `safe_markup` reddens the lone-`[` test.

**Tests to run** (named files only, no suite): `tests/widgets/test_markup_safety.py`,
`tests/widgets/test_surf_rowfit.py`, `tests/widgets/test_surf_launchpad_widgets.py`,
`tests/widgets/test_surf_launchpad_activity.py`, `tests/widgets/test_surf_burnkeepers.py`,
`tests/widgets/test_surf_pool4_left.py`, `tests/widgets/test_surf_pool4u_left.py`,
`tests/widgets/test_surf_pool4u_depth.py`, `tests/widgets/test_surf_pool4u_signals.py`,
`tests/widgets/test_surf_swarm_rail.py`, `tests/widgets/test_surf_widgets_a.py`,
`tests/widgets/test_surf_widgets_b.py`, every `tests/widgets/test_fwa*.py`,
`tests/screens/test_surf_screen.py`, `tests/screens/test_fwa*.py`,
`tests/screens/test_address_icons_everywhere.py -k "surf or fwa"`, and `-m guard tests`. Then
`rg -n '_TAG_LIKE|def _strip_tags|def _flatten|def _sanitize|^_MARKUP = ' maxpane_dashboard`
must be empty.

**Not in scope**: any pin; any rendering change other than the cell-measured clip in
`launchpad.py`; the Branch 3 helpers.

## Branch 0 — `fix/select-to-copy` (Tier 1, session implements)

- `MaxPaneApp.copy_to_clipboard(text)` override → `clipboard.copy_text(...)` (the existing
  native-first path) and the status-bar `copied` / `unconfirmed` / `unavailable` message, so
  Textual's `ctrl+c` (and `super+c` where the terminal forwards it) copies the drag selection.
- Select-to-copy: on `MouseUp` with a non-empty `screen.get_selected_text()`, copy the same way.
  One code path; the key and the mouse-up both call it.
- README "Keyboard shortcuts": one line on drag-select + copy, and the DataTable/RichLog limit.
- Tests: the clipboard runner is already stubbed suite-wide (`tests/conftest.py`); one pilot
  test drags across a `Static`, releases, asserts the stub received the text and the status bar
  says `copied`; one asserts `ctrl+c` does the same; one asserts an empty selection copies
  nothing. Mutation proof: remove the mouse-up hook → the drag test reddens.

## Later phases (recorded, not scheduled)

- Panels by composition (`format_row` injected) once every dashboard is on `panels.py`.
- surf / curator / fwa fully onto `PANELS` + panel subclasses.
- Per-row copy for `DataTable` / `RichLog` panels (Textual selection does not reach them).
- The 16 in-body integer sweeps listed in `docs/handover_followups_2026_09.md` #4.
