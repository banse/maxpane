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
| 3 | `refactor/fmt-rowfit` | §3.3 (move already done in 2) | 2 | ~900 | below; two WPs, A (rowfit) then B (fmt) |
| 4 | `feat/explorer-links` | new (UX links) | 2 | 0 | below; two WPs, A (helper + action + guards) then B (call sites + E7 sweep) |
| 5 | `refactor/dashboard-screen` | §3.5 | 2 | ~1,100 | address sweep + every `tests/screens/test_*_screen.py` migrated |
| 6 | `refactor/panels-ocm` | §3.4a | 2 | small | `tests/widgets/test_panels.py` (new), ocm tests |
| 7 | `refactor/panels-small-four` | §3.4b | 2 | ~2,000 | cattown / dota / talismans / ttt widget + screen tests |
| 8 | `refactor/panels-bt-bakery` | §3.4c | 2 | ~800 | base + bakery tests; templates deleted; `rules/widgets.md` step 3 |
| 9 | `refactor/series-cache` | §3.6a | 2 | +179 net measured (six caches −276, base +434) | `tests/data/test_*_cache.py` unchanged, `test_series_cache.py` (new, fixture round-trips) |
| 10 | `refactor/rpc-pool` | §3.6b | 2 | option B (owner, 2026-09-20); measured at closure `269beda..de27166 -- maxpane_dashboard/`: +869/−321 = **+548 net** — `rpc_classify.py` +361 (tables, predicates and the documented flips), five binding clients −30 (cattown_client's seam +25 counted here), eleven seam files +220 (eight managers, ocm/frenpet/talismans clients: keyword-only constructor seams and docstrings), `rpc_common.py` +12, `fwa_logs.py` −15 — sums to +548; head `a788ba4` is +878/−326 after the WP-C-review folds; the estimate of −100/+150 undercounted the documentation the hoist carries; the ~700 removal assumed the declined full `RpcPool` | `test_rpc_classify.py` (new, fixture-driven), `test_manager_seams.py` (new); seven client test files and all eight manager test files byte-unchanged |
| 11 | `docs/new-dashboard-checklist` | §3.7 | 0 | 0 (docs: `rules/widgets.md` +80/−0 net, HANDOVER item 7, this row) | `tests/widgets/test_panels.py` (pins widgets.md), `-m guard` |

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
  escape pair; escape still matters for the nested-bracket shape one `TAG_LIKE` pass reduces to a
  bare close (`[[inner]/word]` → `[/word]`, a `MarkupError`). *Corrected in review 2026-09-19: the
  "lone unmatched `[`" this line first named renders literally on the installed Rich and needs no net.*

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

## Branch 3 — `refactor/fmt-rowfit` (two work packages, A then B — they share files)

Surveyed 2026-09-19 on main `c3389e5`. The `_rowfit` move is already done (Branch 2); the shim
`widgets/surf/_rowfit.py` is imported by 12 modules and 9 test files. `WIDEN_HINT = "‹ widen"` is
declared 9 times, `SHORT_HINT = "‹ widen"` 6 times, `GLYPH_HINT = "‹"` once (`_pool4`). Of the 15
`_tier_for` sites, **9 are the plain shape** `def _tier_for(width) -> str` walking
`FULL/COMPACT/(NARROW|TIGHT)/MINIMAL_WIDTH` (`curator/{list_hero,hero,activity}.py`,
`fwa/fwa_activity_feed.py`, `surf/{swarm_queue,activity,burnkeepers,hero,swarm_field}.py`); the
other 6 take a second argument or return a tuple (`surf/{launchpad_activity,market,nft,pool4_flow}.py`,
`fwa/{fwa_chase_board,fwa_settlement_table}.py`) and are **not** ladders over module constants —
they stay (deviation from the handover's "15", recorded here). `_has_marker(as_of)` and
`_title_with_hint(base, widen, budget)` are four identical copies in `surf/swarm_{queue,field,
throughput,shipped}.py`; `curator/_table.title_with_hint(title, hint, width) -> tuple[str, bool]`
is a different contract and stays. `markup_safety._MARKUP_TAG` (`\[/?[^\[\]]*\]`) and `TAG_LIKE`
(`\[[^\[\]]*\]`) are the same language — `[^\[\]]*` already admits `/` — so followups #9 is a
one-line alias. `as_float` and `fmt_age` are byte-identical in `surf/_fmt.py` and `curator/_fmt.py`;
`hhmm` differs only in its unknown marker (`??:??` vs `--:--`); `fmt_eth`, `fmt_countdown`,
`fmt_points`, `fmt_pct` exist only in curator; `mmdd` only in surf. `_fmt_eth` is defined 13 times in
widgets/screens (ttt ×2, frenpet ×2 on **wei**, fwa ×4 + `screens/fwa.py`, surf ×3 incl.
`launchpad._fmt_eth_owed`) with different places, units and zero handling; `_as_float` 3 times in
fwa. Analytics keeps its own `_as_float`/`_fmt_eth`: `analytics/` never imports `widgets/`.

### WP-A — `widgets/rowfit.py` (owner of every file it lists)

1. **Shim out.** Delete `widgets/surf/_rowfit.py`; the 12 modules and 9 tests import
   `maxpane_dashboard.widgets.rowfit` (a module-local alias `as _rowfit` is acceptable where it
   keeps a diff to one line; `tests/widgets/test_surf_rowfit.py` drops its shim-subset assertion
   and reads `rowfit.__file__` only). `docs/surf_pool4_contract.md:531`,
   `.claude/rules/widgets.md` "Reuse" item 2 and `tests/test_address_rule.py:28` name the new path.
2. **Hints.** `rowfit.WIDEN_HINT = "‹ widen"`, `rowfit.SHORT_HINT = WIDEN_HINT`, `rowfit.GLYPH_HINT
   = "‹"`; the 16 module-level re-declarations become imports (a module that re-exports one for its
   own importers, as `_pool4` does for `GLYPH_HINT`/`WIDEN_HINT`, imports and keeps the name).
   `WIDEN_HINTS` dicts stay per module — they are content, not a constant.
3. **`Ladder`.** `rowfit.Ladder(*steps: tuple[str, int])`, first step widest; `tier_for(width)`
   returns the first step's name when `width <= 0` or `width >= first threshold`, else the name of
   the first step whose threshold `<= width`, else the last step's name — exactly the nine bodies.
   Convert the 9 plain sites to `_LADDER = Ladder(("full", FULL_WIDTH), ...)` with `_tier_for =
   _LADDER.tier_for` (keep the module-level name: tests and docstrings cite it). Behaviour is
   pinned by an agreement test per converted module in its existing test file: the new `_tier_for`
   equals the old body (copied into the test as a literal) at every width `0..FULL_WIDTH + 5`.
4. **Swarm title helpers.** `rowfit.has_marker(as_of)` and `rowfit.title_with_hint(base, widen,
   budget)` from the four identical swarm copies; the four modules import them.
5. **Followups #9.** `_MARKUP_TAG = TAG_LIKE` in `markup_safety.py`, with a test that `visible_len`
   is unchanged on `["[bold]x[/]", "[/x]", "a[b", "[x/y]", "plain"]` against literal expected values.

Tests to run: `tests/widgets/test_surf_rowfit.py`, `tests/widgets/test_markup_safety.py`, every
`tests/widgets/test_surf_*.py`, `tests/widgets/test_curator_*.py`, `tests/widgets/test_fwa_*.py`,
`tests/screens/test_surf_screen.py`, `tests/screens/test_surf_swarm_screen.py`,
`tests/screens/test_curator_screen.py`, `tests/screens/test_fwa_screen.py`, `-m guard tests`; then
`rg -n 'surf\._rowfit|surf import _rowfit|^(WIDEN_HINT|SHORT_HINT|GLYPH_HINT) = |def _has_marker|def _title_with_hint' maxpane_dashboard tests` must be empty
(the `WIDEN_HINTS` dicts do not match).

**WP-A outcome (2026-09-20, commit `a0ebb17` + fix round):** 8 of the 9 plain sites were converted.
`surf/activity._tier_for` stays a function: `tests/screens/test_surf_screen.py` reads its `__doc__` for
the measured-width note, and it already delegated to `rowfit.tier_for`, so there was no copy to
remove. The review's one Important finding was a spec defect — this list named `rules/widgets.md`
but not the twin sentence in `CLAUDE.md` "Reuse before you build"; both now name `widgets/rowfit.py`.

### WP-B — `widgets/fmt.py` (after A is committed)

1. **Create `widgets/fmt.py`**: `DASH = "--"`, `EMDASH = "—"`, `as_float`, `fmt_age`,
   `fmt_countdown`, `fmt_points`, `fmt_pct`, `hhmm(timestamp, unknown="??:??")`,
   `mmdd(timestamp, unknown="??-??")`, `fmt_eth(value, places=2, unit="")` (`None`/non-numeric →
   `DASH`; a real 0 renders `0.00`; `unit` appended after one space when non-empty). Bodies are the
   curator/surf ones verbatim; docstrings keep their rationale (the bool rejection, negative age,
   the `timeLeftInHour` edge, zero points).
2. **Thin the two `_fmt.py`**: re-export the shared names (`hhmm` in curator = the shared one with
   `unknown=NO_STAMP`), keep only the dashboard-specific ones (`surf`: `fmt_imd`, `fmt_price`,
   `fmt_liquidity`, `ANTI_POISONING_COLS`; `curator`: `fmt_eth_compact`, `ADDR_COLS`, `NAME_COLS`,
   `NO_STAMP`, `COMPACT_ETH_*`). The 37 importers are untouched.
3. **Convert** fwa's three `_as_float` to `fmt.as_float`, and each widget/screen `_fmt_eth` to
   `fmt.fmt_eth(value, places, unit)` **only where a golden test proves identity**: before touching
   a definition, write in its test file a table test over the probe set `[None, 0, 0.0, 1, 1.5,
   1e-7, 0.123456789, 1234.5678, -2, "abc", "", True, 10**18, 15 * 10**17]` with the OLD function's
   outputs pasted as literals; then convert; the goldens must stay green. A definition whose
   semantics `fmt_eth` cannot express (frenpet's wei input, a zero that must render `DASH`, a
   sign or arrow) keeps a two-line local wrapper that calls `fmt_eth` after its own step, or stays
   as it is with a comment naming why — list each in the report.

Tests to run: `tests/widgets/test_curator_*.py`, `tests/widgets/test_surf_*.py`,
`tests/widgets/test_fwa_*.py`, `tests/widgets/test_ttt_*.py`, `tests/widgets/test_frenpet*.py`
(whatever exists), the screen test of each dashboard whose widget changed
(`tests/screens/test_{curator,surf,fwa,ttt,frenpet*}_screen.py`), `-m guard tests`; then
`rg -n 'def _as_float|def _fmt_eth\b' maxpane_dashboard/widgets maxpane_dashboard/screens` lists only the
wrappers the report names.

**WP-B outcome (2026-09-20):** `widgets/fmt.py` exists with the ten names above; both `_fmt.py`
re-export it (37 importers untouched). Of the 15 private copies, **8 converted** — fwa's
`fwa_odds_board._as_float` and `fwa_hero_metrics._as_float` re-pointed at `fmt.as_float`;
`fwa_hero_metrics._fmt_eth`, `surf/launchpad._fmt_eth_owed` are one-line delegations keeping their
`places`; `surf/pool4u_depth._fmt_eth` was `fmt_eth` exactly and its one call site now calls it;
`surf/pool4_ratchet._fmt_eth` (places by magnitude), `fwa_odds_board._fmt_eth` and
`screens/fwa._fmt_eth` (EMDASH marker) are two-line wrappers — and **7 kept**, each with a comment
naming the probe: frenpet's `fpw_pets`/`fpw_hero` take wei and raise `TypeError` on `None`;
`fwa_chase_board._fmt_eth`, `fwa_settlement_table._fmt_eth`/`_as_float` and both ttt tables coerce
`True` to `1` (bare `float()`), and the ttt pair is also ungrouped (`1234.5678 Ξ`). A golden over
the 14-value probe set pins every one of the 15 in its module's test file; none changed. The one
recorded behaviour change is not a rendering: the two `hhmm` bodies differed beyond their marker —
curator's `int()` guard did not catch `OverflowError`, so `hhmm(float("±inf"))` raised inside the
message pump where surf's returned the marker. The shared body is surf's (CLAUDE.md "never a
crash"); curator's `hhmm(±inf)` now renders `--:--`, and no input that rendered before renders
differently. Known, not in the probe set, and the one rendering change this branch ships (review M1/M2
corrected the record: `fwa_odds_board` and `pool4_ratchet` already rejected ±inf through their
own `as_float`): `screens/fwa._fmt_eth(float("inf"))` printed `inf`, now `—` — a deviation from
"no rendered string change" accepted because `inf` is not a quantity; pinned by its own test,
`tests/screens/test_fwa_screen.py::test_fwa_screen_fmt_eth_renders_infinity_as_the_marker`
(the golden's 14-value probe set is unchanged). Review residuals M3, M4, M6
are filed in `docs/handover_followups_2026_09.md` #10–#12.

**Not in scope (both WPs)**: any pin; any rendered string change; `templates/`; the 6 parametric
tier functions; `curator/_table.title_with_hint`; `analytics/`.

## Branch 4 — `feat/explorer-links` (two work packages, A then B — B edits A's call sites)

Surveyed 2026-09-20 on main `38ffe74`. Facts the design rests on:

- Textual 8.1.1 `App.open_url(url)` → `Driver.open_url` → `webbrowser.open(url)` in a terminal
  (the web driver posts a meta message). Nothing in the repo calls it yet. **In a headless
  `run_test` the base driver still calls `webbrowser.open`**, so the suite needs a guard like the
  clipboard one (`tests/conftest.py::_forbid_real_clipboard`) or a test would open the developer's
  browser.
- Rich `Style(link=url)` renders as an OSC 8 hyperlink (`rich/style.py:712`) and Textual's console
  is `force_terminal=True`, so a linked span reaches the terminal as a Cmd+clickable link in
  Terminal.app / iTerm2 with no Textual support needed. A span with `@click` meta is what Textual
  calls a *link* for styling: `Content._apply_link_style` adds the widget's `link_style` to it, and
  the app default is `link-style: underline` / hover `bold not underline` (`textual/design.py:294`).
  **The `⧉` glyph is already rendered that way today**; giving the address text `@click` meta
  underlines the address too. That is the intended affordance; `minimal.tcss` can retheme
  `link-style` app-wide if the owner dislikes it. No width changes: `ICON_COLS` stays 2.
- Chain per dashboard, read off each client's RPC hosts (`data/*_client.py`): **Ethereum
  mainnet** — curator, fwa, ocm, surf, talismans, ttt; **Base** — base, cattown, frenpet (and its
  hidden `_full/_wallet/_perf` bodies), dota, bakery (`data/client.py`, verify: `models.py:604`
  carries a `chain_id`). Surf has two per-row overrides: pool4 panels carry a network word
  (`POOL4_NETWORKS = ("SEPOLIA", "MAINNET")`, `pool4_network` payload key, `_pool4.network_word`)
  and swarm rows carry a `chain_id` (`data/surf_swarm._NETWORKS = {1: MAINNET, 11155111: SEPOLIA}`,
  `widgets/surf/_swarm_chain.chain_word`). `curator_nft_holders.py` reads Base as well as mainnet;
  a wallet address is the same on both, so curator links to Etherscan.
- Address sites: 39 modules call `address_text`; `address_prose` is used by `surf/swarm_field.py`
  (2) and, indirectly, through `widgets/surf/_icons.link_prose` / `link_in_order` (feed, signals,
  HATCHES); `short_hex` renders a transaction hash in `surf/swarm_throughput.py:277` and
  `surf/swarm_shipped.py:362` (both rows carry a `chain_id`) and a bytes32 of unknown kind in
  `fwa/fwa_signals.py:234` (not necessarily a transaction — **not linked**). The one widget with
  its own click handler is `surf/feed.py:625` (`is_copy_click`, PRD §3.4).
- Enforcement today: `tests/widgets/address_probe.icon_targets` reads every `⧉` cell's `@click`
  meta off the compositor; `tests/screens/test_address_icons_everywhere.py` sweeps every
  `SweepCase` (`tests/address_sweep/case.py`: `name, screen_class, build, payload, views,
  address_free, seeded, pins, extra_sizes`) at 170 columns and at each pin.

### Design (the approved bullet above, made concrete)

- **`widgets/explorer.py`** (pure, Rich-free): `Explorer(name, base_url)` frozen dataclass;
  `ETHEREUM = Explorer("etherscan", "https://etherscan.io")`, `BASE = Explorer("basescan",
  "https://basescan.org")`, `SEPOLIA = Explorer("sepolia", "https://sepolia.etherscan.io")`;
  `EXPLORERS: dict[str, Explorer]` by name (the allowlist the action round-trips through);
  `for_network(word) -> Explorer | None` mapping `"MAINNET"→ETHEREUM`, `"SEPOLIA"→SEPOLIA`,
  `"BASE"→BASE`, anything else (including `None`) → `None` — an unknown chain gets **no** link,
  never a guessed one; `is_tx_hash(value)` = `fullmatch(0x + 64 hex)`; `address_url(explorer,
  address)` and `tx_url(explorer, tx_hash)` (`/address/…`, `/tx/…`), each validating first and
  raising `ValueError` on an invalid value (a caller validates before it renders, exactly like
  `copy_action`); `open_action(explorer, kind, value) -> "app.open_explorer('etherscan',
  'address', '0x…')"` and `parse_open_action(action) -> (explorer, kind, value) | None`, the exact
  inverse (`is_explorer_click(event)` beside `is_copy_click`). Values are validated on both ends
  and the URL is always rebuilt from the parsed parts, never taken from the action string.
- **`widgets/address.py`**: `address_text(..., explorer: Explorer | None = None)` and
  `address_prose(..., explorer=None)`: when an explorer is given and the address is valid, the
  *shown* span (address, window or label — never the icon) is stylised with
  `Style(link=address_url(...), meta={"@click": open_action(...)})` on top of the caller's
  `style`; with `None` it renders exactly as today. New `hash_text(tx_hash, width, *, explorer=None,
  style="")` → `Text` for the two transaction-hash sites (`short_hex` stays the plain string
  helper). `widgets/surf/_icons.link_prose(text, explorer=None)` / `link_in_order(texts,
  addresses, explorer=None)` link the shown address before each surviving glyph the same way.
- **`maxpane_dashboard/explorer_action.py`**: `ExplorerLinkMixin.action_open_explorer(name,
  kind, value)` — re-validates all three against the allowlists (an action is not the only way to
  invoke it), rebuilds the URL, calls `self.open_url(url)`, and posts `opened etherscan` /
  `unavailable` through the same status-bar path `CopyAddressMixin._post_copy_message` uses
  (hoist that method to a small shared `_post_status_message` if the two would otherwise be
  copies — same file family, one owner). `MaxPaneApp(CopyAddressMixin, ExplorerLinkMixin, App)`.
- **Tests never open a browser (E8):** `tests/conftest.py` gains `_forbid_real_browser`
  monkeypatching `webbrowser.open` to raise, suite-wide, beside the clipboard guard;
  `tests/widgets/address_probe.py` gains `LinkRecorder` (records `open_url` calls, opens nothing)
  and `link_targets(app)` — every cell whose style carries a `link` **or** an `@click` that
  `parse_open_action` accepts, as `(x, y, explorer_name, kind, value, url)`.
- **E7 — every rendered address is a link to its chain's explorer** (PRD §7 grows E7/E8):
  `SweepCase` gains `explorer: Explorer | None` (the dashboard's default) and `explorers:
  tuple[Explorer, ...]` (the set a per-row override may pick from; surf lists all three). The
  sweep asserts, for every `⧉` target: the shown token before the icon carries an `@click` open
  action **and** an OSC 8 `link` for the same address, `url == address_url(explorer, address)`,
  with `explorer` in the case's allowed set; and every link on screen names an address (or tx
  hash) the payload holds. An address without a link is a failure, exactly as an address without
  an icon is.

### WP-A — the helper, the action, the guards (no widget call site changes)

1. `widgets/explorer.py` as designed, with `tests/widgets/test_explorer.py`: URLs, validation
   (`0x` + 40/64 hex only, `fullmatch`), the allowlist, action round-trip (every `EXPLORERS` entry
   × both kinds), `parse_open_action` rejecting a foreign explorer name, malformed hex, trailing
   text, a non-string; AST purity test in the shape of `test_fmt.py`'s (allow `__future__`, `re`,
   `dataclasses`).
2. `widgets/address.py` changes above; `tests/widgets/test_address.py` (whatever the existing
   file is) gains: the link is on the shown span only, the glyph keeps the copy action; `explorer=
   None` renders byte- and style-identically to before (assert `Text.__eq__` and the spans);
   window and label forms link the full address; an invalid address gets neither link nor icon
   (unchanged); `hash_text` windows through `short_hex` and links `tx_url`.
3. `explorer_action.py`, `app.py` wiring, `is_explorer_click`; `tests/test_explorer_action.py`
   (pilot, `LinkRecorder`): a click on the address text opens the URL and posts the message; a
   click on the glyph copies and opens nothing; an action with a foreign explorer name or a
   malformed value opens nothing and posts `unavailable`; the mutation proof that the URL is rebuilt
   (mutate `action_open_explorer` to use the action's text → the foreign-name test reddens).
4. `tests/conftest.py::_forbid_real_browser` + a test that it bites (`webbrowser.open` raises
   `AssertionError` inside the suite); `address_probe.LinkRecorder`, `link_targets`.
5. Docs: PRD §7 E7/E8 (short, in the E1–E6 style), README mouse paragraph (one sentence: click an
   address to open it on Etherscan/Basescan, Cmd+click works as a terminal hyperlink), CLAUDE.md
   convention bullet "Every displayed 0x address carries a copy icon" gains "and, once Branch 4
   WP-B lands, a link to its chain's explorer" **only in WP-B** (this WP leaves CLAUDE.md alone),
   `.claude/rules/widgets.md` address section gains the link rule and names `explorer.py`.

Tests to run: `tests/widgets/test_explorer.py`, the address helper's test file,
`tests/test_explorer_action.py`, `tests/test_select_to_copy.py`, `tests/test_clipboard.py`,
`-m guard tests`, `tests/screens/test_address_icons_everywhere.py` (must stay green: no site links
yet, E7 is added by WP-B), `tests/widgets/test_base_address_icons.py`.

### WP-B — every call site, the sweep, the docs (after A is committed)

1. Pass `explorer=` at all 39 `address_text` sites and the `address_prose` / `_icons` sites: the
   dashboard's explorer per the chain table above (import the constant from `widgets/explorer`;
   a dashboard package may bind it once in its `_fmt.py` or `__init__` and import it from there —
   one declaration per dashboard, the sweep's `SweepCase.explorer` is the agreement test that
   binds it). Surf: pool4 panels use `for_network(pool4_network)`, swarm rows
   `for_network(chain_word(chain_id))` (or the chain id directly through a `for_chain_id`
   helper added in this WP with an agreement test against `data/surf_swarm._NETWORKS`), the two
   hash sites use `hash_text`, everything else on surf is mainnet. `surf/feed.py` on_click
   returns early on `is_explorer_click` too. `fwa_signals` bytes32 stays unlinked, with a comment.
2. `SweepCase.explorer` / `explorers` on every case in `tests/address_sweep/builders.py`; E7
   assertions in `test_every_rendered_address_carries_an_icon_that_copies_it` (rename to
   `…_and_a_link_that_opens_it`; update the two other sweep files that name it, if any). Prove it
   bites twice: drop `explorer=` from one Base site (the sweep must name that widget and
   "address without a link"); pass `ETHEREUM` at one Base site (the sweep must name "link on the
   wrong explorer"). Restore both by inverse edit.
3. Docs: CLAUDE.md convention bullet, README, PRD §7 E7 wording final, `rules/widgets.md`,
   `templates/` address examples pass `explorer=` (a template must not teach the old form).

Tests to run: every `tests/widgets/test_*_address_icons.py` and each dashboard's widget tests
whose files changed; `tests/screens/test_address_icons_everywhere.py`;
`tests/test_address_sweep_registry.py`; `tests/test_address_rule.py`; `-m guard tests`; each
`tests/screens/test_<game>_screen.py` for a dashboard whose widgets changed (all of them — run in
three foreground batches).

**Not in scope (both WPs)**: any pin (the link adds no cells); `templates/` beyond the address
example lines; ENS *names* as a separate link kind (a name-backed address links the address);
a `bytes32` that is not known to be a transaction hash; `DashboardScreen` (Branch 5).

**WP-A outcome (2026-09-20, this commit).** Delivered as designed: `widgets/explorer.py` (pure —
`re` and `dataclasses` only; `Explorer`, `ETHEREUM`/`BASE`/`SEPOLIA`, `EXPLORERS`, `KINDS`,
`for_network`, `is_address`/`is_tx_hash`, `address_url`/`tx_url`/`url_for`, `open_action`/
`parse_open_action`); `widgets/address.py` gains `explorer=` on `address_text` and `address_prose`,
`hash_text(tx_hash, width, *, explorer=None, style="")` and `is_explorer_click`; surf's
`_icons.link_prose(text, explorer=None)` / `link_in_order(texts, addresses, explorer=None)` link the
shown address or window right before each surviving glyph (a window that is not of that address
links nothing); `explorer_action.ExplorerLinkMixin.action_open_explorer` re-validates name, kind and
value, rebuilds the URL, calls `App.open_url` and posts `opened <name>` / `explorer unavailable`;
`MaxPaneApp(CopyAddressMixin, ExplorerLinkMixin, App)`. The status-bar poster was hoisted out of
`CopyAddressMixin._post_copy_message` into `maxpane_dashboard/status_message.post_status_message(app,
message, *, seconds)`, which both mixins call (`clipboard.copy_message` untouched). Guards:
`tests/conftest.py::_forbid_real_browser`, `address_probe.LinkRecorder` and `link_targets(app)`
(one entry per linked cell, `(x, y, name, kind, value, url)`). Two deviations from the design
bullet: (1) `widgets/explorer.py` restates `ADDRESS_RE` rather than importing the address helper
(which imports *it*); `test_explorer.py::test_the_address_pattern_agrees_with_the_address_helper` is
the agreement test. (2) The action-string parser is a `fullmatch` on the exact shape plus the
allowlist checks; a round-trip equality was written first and removed when a mutation proof showed
no test could tell it from the regex. Mutation-proven: the URL rebuilt from the allowlist (16 of 24
`test_explorer_action.py` cases redden when the action opens `https://{name}/{kind}/{value}`), the
link on the shown span (5 tests), and the `explorer=None` identity (exactly one test, against
literals from `git show 307255a:…/address.py`). No widget call site changed; the E2 sweep and
`test_surf_screen.py` are green unchanged (42 and 314). WP-B still owes: every call site, `SweepCase.
explorer`/`explorers` + the E7 sweep assertion, `feed.py` returning early on `is_explorer_click`, the
CLAUDE.md convention bullet and the `templates/` address lines.

**WP-B outcome (2026-09-20).** Every call site passes its explorer. Chain table as verified against
each client's RPC hosts: Ethereum mainnet (Etherscan) — curator (`curator_client.py:99`
`ethereum-rpc.publicnode.com`), fwa (`fwa_client.py:120`), ocm (`ocm_client.py:48`), surf
(`surf_client.py:84`), talismans (`talismans_client.py:70` `ethereum.publicnode.com`), ttt
(`ttt_client.py:99`); Base (Basescan) — base (`base_client.py` GeckoTerminal `/networks/base/`,
DexScreener `chainId == "base"`), cattown (`cattown_client.py:167` `mainnet.base.org`), frenpet
(`frenpet_client.py:78` `mainnet.base.org`, the hidden `_full/_wallet/_perf` bodies). **One
disagreement with the chain table above: Bakery is on Abstract, not Base** — `data/client.py` reads
`agent.json` and `tests/data/test_client.py` / `tests/data/test_cache.py` pin `chainId` 2741, explorer
`abscan.org`; `widgets/explorer.py` allowlists no Abstract explorer, so Bakery's one site
(`widgets/activity_feed.py`) stays unlinked with a comment, its `SweepCase` has `explorer=None`, and
E7 asserts that no address on it links (adding `abscan.org` to the allowlist is the owner's call,
not this WP's). DOTA renders no address. One declaration per package: `EXPLORER` in
`widgets/surf/_fmt.py` and `widgets/curator/_fmt.py`, new `_chain.py` in `widgets/{fwa,ttt,
talismans,ocm,base,cattown,frenpet}/`, each `#:`-commented with the client and hosts. Sites converted:
surf 18 (launchpad 2, launchpad_activity 1, activity 1, burnkeepers 2, signals `link_in_order` 1,
feed `link_prose` 1, swarm_field `address_prose` 2, pool4_hatches 3 via `for_network(pool4_network)`,
pool4u_stakers 1 likewise, swarm_throughput `hash_text` 1 and swarm_shipped 3 via the new
`explorer.for_chain_id(chain_id)`; `tests/widgets/test_explorer.py` binds `for_chain_id` to
`data/surf_swarm._NETWORKS` through `for_network` in both directions), curator 9, fwa 7, frenpet
hidden bodies 4 (in `screens/`), cattown 3, ttt 3, base 1, talismans 1, ocm 1. Left unlinked, on
purpose: `fwa_signals.py` bytes32 (unknown kind, commented), Bakery (above), and the two `.plain`
measurement calls (`surf/activity.py:420`, `surf/pool4_hatches.py:401`) that render nothing.
`surf/feed.py` `on_click` returns early on `is_explorer_click`. No rendered text or width changed;
no pin touched. E7 in the sweep (`SweepCase.explorer` / `explorers`, the renamed
`test_every_rendered_address_carries_an_icon_that_copies_it_and_a_link_that_opens_it`): the token
cell before every icon (read with `get_style_at`, the icon's own reader) carries an open action and
an OSC 8 link for the same address on an allowed explorer with `address_url`'s URL; every link on
screen names a payload address or hash; a no-explorer or address-free case shows no link. Bite
proofs: (a) `explorer=EXPLORER` dropped at `widgets/cattown/ct_leaderboard.py` → `[cattown-wide]` and
`[cattown-pin]` fail with `address without a link` (two cells each); (b) `explorer=ETHEREUM` there →
the same two ids fail with `link on the wrong explorer`. Both restored by inverse edit (md5
identical). Templates' address lines pass `explorer=EXPLORER` with a module-level declaration to
replace. Not done: the two historical plan docs under `docs/superpowers/plans/` keep the old test id
where it appears as a dated code listing (`2026-09-14-address-copy-icons.md:1852`); the two
mutation-table rows and `docs/surf_swarm_followups.md` were renamed.

**WP-B fix round 1 (2026-09-20; review of `a44cb95`: 1 Critical, 2 Important, 3 Minor, all six
fixed in one commit).** *C1 was a plan/chain-table gap, not a call-site slip:* the chain table
above assigns one explorer per package, which holds for a **wallet** address (the same 20 bytes on
Ethereum and Base) but not for a **contract** address — curator's filter editor lets the reader add
a custom NFT collection on `ethereum` or `base`, and that collection's contract linked to Etherscan
either way. Now `widgets/curator/list_filter.py` resolves per row through a hand-typed
`NFT_CHAIN_EXPLORERS = {"ethereum": ETHEREUM, "base": BASE}` keyed by the editor's own
`NFT_CHAIN_OPTIONS` (an unknown chain word links nothing); `for_network`'s upper-case vocabulary is
untouched. `tests/widgets/test_curator_address_icons.py` binds the map to the Select's options and
to `data/curator_list_filters.NFT_CHAINS` in both directions, and renders a Base collection
(`basescan.org/address/…`), an Ethereum one (`etherscan.io`) and an unknown word (icon, no link).
The sweep gained `SweepCase.explorer_for` (lower-cased address → the one explorer it must link on;
every value must be in `explorers`); curator's builder now adds a second collection on Base through
the editor's controls (waiting, bounded, for the exclusive name-lookup worker before the second
add), seeds it, and lists `explorers=(ETHEREUM, BASE)`, `explorer_for={<base collection>: BASE}`.
Under the old code `[curator-wide]` and `[curator-pin]` fail with `link on the wrong explorer`
(two cells each, `curator_filter_editor@170x60` / `@138x60`). *I1:* the sweep's per-icon and
per-link loops rebound the parametrised `kind`, so the wide-only presence check was dead for every
case that renders a link; the inner names are `link_kind`/`link_value` and an
`assert kind in ("wide", "pin") or kind.startswith("extra-")` guards the block — with
`copied_somewhere.clear()` after each view, `[ocm-wide]`, `[cattown-wide]`, `[ttt-wide]` and
`[bakery-wide]` now redden with `seeded addresses never got an icon in any view` (`[ocm-pin]`
stays green, presence being a wide property). *I2:* per-row explorers now have tests that can fail:
`tests/widgets/test_surf_swarm_shipped.py` (chain_id 11155111 → `sepolia.etherscan.io` for the
address cell and a hash-only row's tx cell, 1 → `etherscan.io`, an unknown id → icon, no link;
`for_chain_id(1)` at `swarm_shipped.py` reddens the Sepolia and unknown-id tests) and
`tests/widgets/test_surf_pool4_rail.py` (HATCHES on `SEPOLIA` links every address on
`sepolia.etherscan.io`, `MAINNET` on `etherscan.io` and never `basescan.org`, `None` or `ARBITRUM`
links nothing; `for_network("BASE")` at `pool4_hatches.py` reddens all three — note `BASE` *is* an
allowlisted word, so the unknown-word case uses one that is not). *M1:*
`tests/widgets/test_surf_address_icons.py` clicks the linked span of an address a `SurfFeedToggle`
renders: the explorer action runs, the thread does not toggle, plain text still toggles; dropping
`or is_explorer_click(event)` from `feed.py` reddens it. *M2:* the template test also walks the AST
for every `address_text` call's `explorer=` keyword and a module-level `EXPLORER`; deleting the
keyword from `leaderboard_template.py` reddens `[leaderboard_template]`. *M3:*
`widgets/base/_chain.py` cites `base_client.py:554` / `:232` (`/networks/base/`), `:299`
(`chainId == "base"`) and `:702` (`mainnet.base.org`). Every mutation restored by inverse edit,
md5-identical.

**WP-B fix round 2 (2026-09-20; scoped re-review of `ae0ebe0`: all six ADDRESSED, two notes
filed — N1 Important-shaped, N2 Minor; the controller applied N1).** *N1:* widening curator's
`explorers` to `(ETHEREUM, BASE)` for its one Base collection made `SweepCase.explorer` decorative
— E7 checked membership in the set and consulted `explorer_for` only for listed addresses, so a
mutated `widgets/curator/_fmt.EXPLORER = BASE` (every wallet on Basescan, a wrong page on a
mainnet dashboard) left the sweep and the curator widget tests green, where `a44cb95` would have
caught it. `SweepCase` gained `rows_pick_explorer` (surf: `True` — pool4 panels and swarm rows
choose out of `explorers`); for every other case an address `explorer_for` does not list must link
on `explorer` itself, and a hash likewise (`_expected_explorer` in the sweep). `__post_init__`
rejects a set wider than one that nothing is entitled to use, and `rows_pick_explorer` on a case
with no explorer. Proof: the same mutation now reddens `[curator-wide]` and `[curator-pin]` with
`link on the wrong explorer` at the hero, RAW/CLEANED and LEADERBOARD wallets (`basescan`), surf's
two cases stay green; sweep file 43 green on the restored tree. *N2* (per-row sites
`swarm_throughput.py` and `pool4u_stakers.py` still without a biting widget test) and surf's own
`_fmt.EXPLORER`, which `rows_pick_explorer` leaves unbound by the sweep, are filed as
`docs/handover_followups_2026_09.md` #16–#17.

## Branch 5 — `refactor/dashboard-screen` (two work packages, A then B — B migrates onto A's class)

HANDOVER §3.5. Cut from main `8ab531c` (after Branch 4, so every migrated screen inherits the
explorer links rather than being retrofitted). Facts read off the tree on 2026-09-20:

- Fourteen dashboard screens inherit `RefreshGuard, Screen`. Ten are **pure dispatch**: bakery,
  base_terminal, cattown, dota, frenpet, frenpet_perf, frenpet_wallet, ocm, talismans, ttt. Each
  is the same five things hand-copied: `__init__(manager, poll_interval, name=…)` storing the
  manager (`_data_manager` in cattown/talismans/ttt/bakery/frenpet_perf/frenpet_wallet/surf/
  curator/fwa, `_manager` in ocm/dota/base_terminal/frenpet/frenpet_full), `_poll_interval` and
  `_refresh_timer = None`; `on_screen_resume` (initial refresh, `set_interval`, StatusBar
  `set_theme_name(self.app.theme)` + `set_game_name("<words>")` inside one `try/except: pass`);
  `on_screen_suspend` (stop the timer); and `_do_refresh` = fetch → on failure log + StatusBar
  `last_updated_seconds_ago=999, error_count=getattr(manager, "_error_count", 0)` (bakery and
  frenpet read the attribute bare and would raise on a manager without it) → title-bar update →
  one `try: self.query_one(W).update_data(k=data.get("k"), …) except Exception: logger.…` block
  per panel → StatusBar from `data`. 151 such blocks across the 14 screens; log levels drift
  (`debug` in most, `warning` in bakery/frenpet, `error` for a failed fetch in base/bakery/
  frenpet/frenpet_full).
- Four keep a **custom `_do_refresh`** and stay that way this branch (Decision 4): surf (4,593
  lines), curator (2,397), fwa (520), frenpet_full (781). Their lifecycle bodies are the shared
  shape plus one line each: surf `set_key_hints(self.KEY_HINTS)`; fwa, ttt and talismans
  `set_active_view(self._active_view)`; curator's `on_screen_suspend` and `on_unmount` also cancel
  its export/ENS workers.
- Two of the ten pure-dispatch screens compute between fetch and dispatch (frenpet_wallet,
  frenpet_perf: aggregate wins/losses, `compute_win_rate`, `classify_*`, `find_top_earner`, a
  `time.time()` sample for one-point histories — **the clock is not injected there**, a
  pre-existing hazard, filed not fixed). Two panels take a positional argument
  (`FPOverviewLeaderboard.update_data(top_pets)`, `FPWalletPets.update_data(pets)`); both
  parameters are named, so a keyword call is equivalent.
- Constructor call sites: `app.py:236–389` (`Screen(manager, poll_interval, name=…)`, the
  Curator/FWA/Surf/Talismans ones spread over lines) and every test (`Screen(manager,
  poll_interval=30, name="…")`); `app.py` is untouched by this branch. Tests that read a screen's
  manager attribute: `tests/screens/test_{curator,fwa,surf}_screen.py`, `test_refresh_guard.py`,
  `tests/test_{curator,surf}_registration.py` (`_data_manager`).
- Enforcement today: `tests/screens/test_refresh_guard.py::_dashboard_screen_classes` collects a
  screen only when `"_do_refresh" in vars(cls)` — a screen that inherits its refresh would fall
  out of the guard test silently; `test_template_screen_inherits_the_guard` reads
  `templates/screen_template.py`, which is a copy of bakery. Screen-level tests exist for base
  (mount + failed refresh), talismans (mount + toggle), frenpet (titles, pet view, wallet hero
  scaling) and ttt (icon layout); cattown, dota, ocm, bakery and frenpet_perf are covered only by
  the address sweep, the copy harness in `tests/test_address_rule.py` and the degradation tests.

### Design

- **`screens/dashboard_screen.py`** — `class DashboardScreen(RefreshGuard, Screen)`:
  - class attributes a subclass sets: `GAME_NAME: str` (the status-bar words, e.g.
    `"onchain monsters"`), `REFRESH_WORKER_NAME`, `PANELS: tuple[tuple[type[Widget],
    Callable[[dict], dict]], ...]` — the widget class `query_one` finds and an **adapter** from the
    manager's flat dict to that widget's `update_data` **keyword arguments**; `BINDINGS =
    [Binding("r", "refresh", "Refresh", show=False)]` (a subclass extending it re-lists `r`, as
    ttt/talismans do today).
  - `keys(*names, **defaults) -> Callable[[dict], dict]`: the adapter for the dominant shape,
    `lambda data: {n: data.get(n, defaults.get(n)) for n in names}` — so a panel row reads
    `(OCMSparklines, keys("supply_history", "staked_history", "ocmd_supply_history"))`; a
    computing adapter is a module-level function in the screen (`_wallet_hero(data) -> dict`).
  - `__init__(self, manager, poll_interval: int = 30, name: str | None = None, **kwargs)`: stores
    `self._data_manager` (the majority name; ocm/dota/base_terminal/frenpet/frenpet_full rename
    their `self._manager` reads, and the tests that read them), `self._poll_interval`,
    `self._refresh_timer = None`. Positional order and `name=` keyword unchanged, so `app.py`
    and every test construct screens exactly as today.
  - `on_screen_resume`: `_do_initial_refresh()`, `set_interval(poll_interval, _schedule_refresh)`,
    then inside one `try/except Exception: pass` (a harness may mount no StatusBar): `bar =
    self.query_one(StatusBar)`, `bar.set_theme_name(self.app.theme)`,
    `bar.set_game_name(self.GAME_NAME)`, `self._prime_status_bar(bar)`. **`_prime_status_bar(bar)`**
    is the hook for the one extra line (fwa/ttt/talismans `set_active_view`, surf `set_key_hints`);
    default no-op.
  - `on_screen_suspend`: stop and clear the timer (curator overrides and calls `super()` first).
  - `_do_refresh`: `data = await self._data_manager.fetch_and_compute()`; on exception
    `logger.warning("%s refresh failed: %s", self.GAME_NAME, exc)`, StatusBar
    `update_data(last_updated_seconds_ago=999, error_count=getattr(manager, "_error_count", 0),
    poll_interval=self._poll_interval)` in its own try, return. Then `self._update_title(data)`
    (hook, default no-op, its body in the subclass wrapped by the base in `try/except` +
    `logger.warning`), then for each `(cls, adapt)` in `PANELS`: `try:
    self.query_one(cls).update_data(**adapt(data)) except Exception as exc:
    logger.warning("Failed to update %s: %s", cls.__name__, exc)` — one panel's failure never
    stops the next; then StatusBar from `data` (`last_updated_seconds_ago`, `error_count`,
    `poll_interval` defaulting to the screen's). One log level, `warning`, for every degraded
    step (a panel that cannot render is worth a line in `~/.maxpane/maxpane.log`); `debug` was
    the majority but hid exactly the failures the degradation tests exist for.
  - `compose()` stays per screen (layouts differ); `on_mount` (ttt/talismans hide one table) and
    `action_toggle_view` stay per screen.
- **Rendering must not change.** Same widgets, same kwargs, same `data.get` defaults; the
  adapters are transcribed from the dispatch blocks, default by default (`faucet_open=True`,
  `time_to_next_tier=""`, `recommendation=""`, `recent_mints=0`, `game_start_timestamp=
  1709251200`, …). The one intended behaviour change: bakery and frenpet no longer raise inside
  the failure path when a manager has no `_error_count` (they degrade like the other eight).
- **Enforcement (replaces 151 hand-typed blocks with two tests that bite):**
  `tests/screens/test_dashboard_screen.py::test_every_panel_row_names_a_mounted_widget_and_its_update_data_keywords`
  parametrised over every `DashboardScreen` subclass in `screens/` that does not define its own
  `_do_refresh`: mount it with a payload manager (reuse the address-sweep case's `build`/`payload`
  where one exists, else a `_PayloadManager` over `{}`), assert `PANELS` is non-empty, each
  `cls` resolves by `query_one`, no class appears twice, and `set(adapt(payload)) ⊆
  signature(cls.update_data).parameters` (with no positional-only parameter left unfilled) — a
  mistyped key, a dropped panel or a widget not in `compose` reddens the row. Second: the guard
  test's collector becomes `issubclass(obj, DashboardScreen) or "_do_refresh" in vars(obj)` and
  asserts every collected class sets `GAME_NAME` when it inherits the refresh.
- `templates/screen_template.py` is rewritten onto `DashboardScreen` (`GAME_NAME`, `PANELS`,
  `compose`, `_update_title`) — it is the copy-source, and a copy of the old shape reintroduces
  the 151-block pattern in dashboard number fifteen.

### WP-A — the base class, one proof migration, the template

Files (owner of each): `maxpane_dashboard/screens/dashboard_screen.py` (new),
`maxpane_dashboard/screens/ocm.py` (migrated: `GAME_NAME = "onchain monsters"`, `PANELS` of six
rows, `compose` kept, no `_update_title` — ocm has no title logic), `maxpane_dashboard/templates/
screen_template.py` (rewritten onto the base), `tests/screens/test_dashboard_screen.py` (new),
`tests/screens/test_refresh_guard.py` (collector + `GAME_NAME` assertion), CLAUDE.md
Architecture line for `screens/` (add `dashboard_screen.py (DashboardScreen: lifecycle +
PANELS dispatch)`) and `.claude/rules/widgets.md` if it names the screen shape (check; the
new-dashboard checklist rewrite itself is Branch 11).

Tests in `test_dashboard_screen.py` (TDD, each with a mutation that reddens it, recorded in the
report): resume starts the timer and primes the bar with `GAME_NAME` and the app theme, suspend
stops it; `_prime_status_bar` is called with the bar; a failed fetch posts `999` and the
manager's `_error_count` and tolerates a manager without one (port of
`test_base_terminal_screen.py:77–110` onto a minimal subclass); a panel whose `update_data`
raises is logged at `warning` with its class name and the following panel still updates; the
StatusBar row reads `data` with the screen's `poll_interval` as default; `keys()` returns
`data.get` with the given defaults and nothing else; `_update_title` receives `data` and its
exception is contained; the panel-row agreement test above (ocm is its first row). Plus the
pre/post render check: before touching `ocm.py`, render `OCMScreen` at 170×50 and at its pin
with the sweep payload (`tests/address_sweep/builders.py` ocm case) to a scratch file; after
migration the composited text is identical — paste the diff (empty) into the report; the
reviewer repeats it. Named tests: `tests/screens/test_dashboard_screen.py`,
`tests/screens/test_refresh_guard.py`, `tests/test_address_rule.py`, `-m guard tests`,
`HOME=$(mktemp -d) … tests/screens/test_address_icons_everywhere.py -k ocm`.

**WP-A outcome (2026-09-20).** Landed as `d25f9de`, fix round 1 on top. 8 files, +912/−273:
`screens/dashboard_screen.py` new (233 lines), `screens/ocm.py` 177 → 117, `templates/screen_template.py`
187 → 121 (raw `wc -l`, the convention below; the 132 → 72 and 133 → 67 first written here counted
non-blank non-comment lines and were not comparable with anything else in this plan — WP-B
re-review N1), `tests/screens/test_dashboard_screen.py` new, `tests/screens/test_refresh_guard.py`
(collector + `GAME_NAME`), `tests/test_address_sweep_registry.py`, CLAUDE.md, `.claude/rules/widgets.md`.
Pre/post composited render of `OCMScreen` on the sweep payload at 170×50 and at the 143 pin (frozen
clock): **identical, both diffs empty.**

Four deviations from this section, each reported rather than taken silently:

1. **A sixth file was needed.** `tests/test_address_sweep_registry.py::test_every_dashboard_screen_has_a_sweep_case`
   (E3) discovers every `Screen` subclass under `screens/` and demanded a `SweepCase` for the base
   class. Excluded by **class**, not by module (`ABSTRACT_SCREEN_CLASSES = (DashboardScreen,)`,
   tightened in fix round 1 from WP-A's first module-wide cut, which would have hidden a real
   dashboard later added beside the base). WP-B should expect the same tuple to stay one entry long.
2. **The panel-row agreement test does not honour `**kwargs`.** Under the literal rule
   (`set(adapt(payload)) ⊆ signature(...).parameters`) the section's own mutation did **not** bite:
   `OCMHeroMetrics.update_data` ends in `**_kwargs`, so `minted_pcts` was accepted and silently
   discarded. Every key must now be a *named* parameter. Verified safe for WP-B by an AST scan: none
   of the nine remaining pure-dispatch screens sends a keyword its widget does not name.
3. **`keys()` raises on a default that names no listed key.** Semantics for valid input are exactly
   the lambda in the Design bullet; the guard catches `faucet_opn=True` beside `"faucet_open"`, which
   the bare lambda swallows into a silent `None`.
4. **ocm's constructor defaults moved** by deleting its `__init__` (`poll_interval` 60 → 30, `name`
   `"ocm"` → `None`). Every call site passes both explicitly, so nothing observable changed; WP-B
   inherits the same effect on dota/base_terminal/frenpet.

**Review: `Needs fixes: 0 Critical, 1 Important, 4 Minor`; fix round 1 closed all but the one filed
follow-up.** I1 — no test could fail when a migrated screen lost skip-not-queue on its first refresh
(a bare `run_worker` in `on_screen_resume` left all four named files green while an overrun tick
cancelled the in-flight fetch): two pilot tests added on the guard's own doubles, asserting
`_refresh_in_flight` / `_refresh_skipped` on the minimal subclass and the prefetch join on the
migrated `OCMScreen`. M1 — the `BINDINGS` comment claimed Textual does not merge a subclass's
bindings; it does, along the MRO (verified on Textual 8.1.1), so **WP-B need not re-list `r`** and may
drop it from ttt/talismans. M2 — `rules/widgets.md` now dates its scope (only ocm and the template are
migrated). M4 — the E3 exclusion made class-level, as above. M3 was pre-existing and is filed as
follow-up **18**, not fixed: ocm's STAKING OVERVIEW and SUPPLY BREAKDOWN keep their `Loading...`
placeholder under a partial payload because an explicit `None` overrides the widgets' own `= 0`
defaults — **WP-B will surface the same shape on any screen whose widgets default numerically**, and
it is a widget fix (MEDI-38 unavailable state), never a change to the screen or to `keys()`.

### WP-B — the other nine, lifecycle-only for the four custom screens, the docs

- Migrate bakery, base_terminal, cattown, dota, frenpet, frenpet_perf, frenpet_wallet,
  talismans, ttt onto `DashboardScreen`: `GAME_NAME`, `PANELS`, `compose` kept, `_update_title`
  where the screen had title logic (all but cattown? — cattown has one; every screen but ocm
  does), `_prime_status_bar` for ttt/talismans (`set_active_view`), `on_mount` and
  `action_toggle_view` kept. frenpet_perf/frenpet_wallet: computing adapters as module-level
  functions taking `data` only; the wallet address the title needs comes from
  `self._data_manager._wallet_address` inside `_update_title`, which has `self`. `time.time()`
  stays where it is (followup). Delete every `on_screen_resume`/`on_screen_suspend`/
  `_do_refresh`/`__init__` the base now provides.
- surf, curator, fwa, frenpet_full: inherit `DashboardScreen`; `__init__` calls
  `super().__init__(manager, poll_interval, name=name, **kwargs)` and keeps only its extra state;
  delete their `on_screen_resume`/`on_screen_suspend` where identical to the base (surf: keep the
  key hints via `_prime_status_bar`; fwa: `set_active_view` via the hook; curator: override
  `on_screen_suspend`, call `super()`, then its worker cancellations); keep `_do_refresh`. Set
  `GAME_NAME` (`"surf"`, `"curator"`, `"fwa"`, `"frenpet · base"`). frenpet_full renames
  `self._manager` → `self._data_manager` (and dota/base_terminal/frenpet in their migration).
- Tests: the panel-row agreement test gains nine rows for free; `test_base_terminal_screen.py`,
  `test_talismans_screen.py`, `test_frenpet_screens.py`, `test_ttt_address_icon_layout.py`,
  `test_{curator,fwa,surf}_screen.py` (the `_refresh_timer` / resume-suspend assertions at
  `test_fwa_screen.py:700`, `test_curator_screen.py:1765` now exercise the base) must stay green
  unchanged except for the attribute rename; pre/post render diff at 170 columns and each pin
  for all nine migrated screens plus the four custom ones (their compose is untouched, so
  identical by construction — still diffed). Named tests: those files, `tests/test_address_rule.py`,
  `tests/screens/test_dashboard_screen.py`, `tests/screens/test_refresh_guard.py`, `-m guard
  tests`, `HOME=$(mktemp -d) … tests/screens/test_address_icons_everywhere.py`,
  `tests/test_app_startup.py`, `tests/test_{curator,surf}_registration.py`.
- Docs: `docs/handover_followups_2026_09.md` gains the `time.time()`-in-screen item
  (frenpet_wallet/frenpet_perf, "inject the clock") and the outcome paragraph below records the
  line count removed (HANDOVER estimated ~1,100).

**WP-B outcome (2026-09-20).** Landed as `64ab0f8`. All thirteen remaining screens are on
`DashboardScreen`; nothing was left unmigrated.

*Line counts are raw `wc -l`* — blank lines, comments and docstrings included — the only figure
that can be checked with one command, and the convention for every number in this plan (the WP-A
paragraph above was restated in it).

| file | before | after | file | before | after |
| --- | --- | --- | --- | --- | --- |
| `screens/bakery.py` | 189 | 124 | `screens/talismans.py` | 250 | 169 |
| `screens/base_terminal.py` | 177 | 90 | `screens/ttt.py` | 244 | 163 |
| `screens/cattown.py` | 173 | 87 | `screens/surf.py` | 4593 | 4587 |
| `screens/dota.py` | 186 | 114 | `screens/curator.py` | 2397 | 2392 |
| `screens/frenpet.py` | 189 | 117 | `screens/fwa.py` | 520 | 511 |
| `screens/frenpet_perf.py` | 296 | 247 | `screens/frenpet_full.py` | 781 | 758 |
| `screens/frenpet_wallet.py` | 331 | 280 | **total** | **10,326** | **9,639** |

**687 production lines removed in WP-B**, 813 for the branch with WP-A's 126 (ocm 177 → 117,
template 187 → 121). HANDOVER estimated ~1,100; the gap is honest, not a shortfall: the estimate
counted the four custom screens' `_do_refresh` bodies, which stay because their refreshes really
are custom, and it did not net off the 236-line shared base (so the repo is 577 lines smaller, and
the duplicated lifecycle is now written once).

**Render evidence.** Every one of the 14 `tests/address_sweep/registry.CASES` entries was
composited before and after, at 170×60 and at each pin the case lists, for every view the case
lists (76 files): **every render diff empty.** Because the sweep payload leaves some panels on
`Loading...` (followups #18), each mount also logged every `update_data` call with its kwargs
normalised through `inspect.signature().bind()`, plus every title-bar `Static.update`, on three
payloads — the sweep payload, an all-string sentinel payload and an all-numeric one — against the
*pre-migration module* loaded out of `git show e7a37dd:`. Every screen's dispatch log is identical
on all three, with one exception, below.

**Four deliberate deviations, none of them reachable from the real managers.**

1. `screens/bakery.py` was the one hand-written dispatch that read its payload by **subscript**
   (`data["bakeries"]`), so a missing key raised `KeyError` and left the panel on its last render.
   `keys(...)` reads with `data.get`, so a partial payload now reaches the panel as an explicit
   `None`. `data/manager.py` builds its payload as one dict literal in which every one of those
   keys is always present, so against the real manager the two reads are the same read; the
   composited render on the sweep's own partial bakery payload is identical at 170 and at the pin.
   A raising adapter cannot be read by the panel-row agreement test, which would have left bakery
   the one dashboard with no enforcement — the hole this branch exists to close. Recorded in the
   module docstring.
2. Following from 1: on a literally empty `{}` payload old bakery dispatched nothing and new
   bakery dispatches seven rows, including the base's status-bar row
   (`error_count=0, last_updated_seconds_ago=0, poll_interval=30`, the approved WP-A contract).
   This is the one non-identical dispatch log in the whole capture, and `{}` is a payload
   `DataManager.fetch_and_compute()` cannot produce.
3. Constructor signatures drifted to the base's. `screens/dota.py` lost its own `__init__` and
   with it the default `name="dota"` (now `None` from the base); `screens/frenpet_full.py`
   never had a `name` parameter and loses nothing there. `bakery`, `cattown`, `frenpet_perf`
   and `frenpet_wallet` took `poll_interval` as a **required** positional and now inherit the
   base's `poll_interval=30` default. Every call site in `app.py` passes both the interval and
   `name=` explicitly, so nothing observable changed — the same drift WP-A recorded for ocm.
   (Fix-round 1 corrected this entry: the WP-B report had named `frenpet_full` for a `name`
   default it never had and missed the four that lost a required argument.)
4. `screens/frenpet_perf.py` computed four aggregates (`total_wins`, `total_losses`,
   `total_score`, `avg_win_rate`) **once** in `_do_refresh`, ahead of and outside every
   panel's `try` (the summed score history was always inside the trends panel's own `try`).
   A payload on which that arithmetic raised (a pet object missing `win_qty`, say) escaped
   `_do_refresh` entirely: all six panels kept their last render **and the status-bar row
   never ran**, so the screen showed a stale `as of` reading with no degradation marker — the
   exact shape CLAUDE.md's "never a stale number presented as live" forbids. The module-level
   adapters recompute each aggregate inside the panel that needs it and the base contains each
   adapter, so the same payload now fails per panel, the panels that do not need the broken
   field still update, and the status bar is written. An improvement, and one the real
   manager cannot reach (its `managed_pets` are typed records); recorded because the WP-B
   report did not name it (WP-B reviewer M5; wording corrected on the re-review's N1).

`frenpet_perf`/`frenpet_wallet`'s between-fetch arithmetic moved out whole into module-level
adapters (`_perf_hero`, `_perf_trends`, … `_wallet_best_plays`): same helpers, same order, same
values, and `time.time()` still sampled inside `_perf_trends`/`_wallet_trends` rather than
injected — carried across, not fixed, and filed as follow-up 19. `ttt` and `talismans` now list
only `c` in `BINDINGS` (Textual merges along the MRO, WP-A note M1); a pilot keypress test proves
`r` still refreshes, and reddens when the base's binding key is changed.

Reviewer contract verbatim, one reviewer per WP diff, at most two fix rounds each; the full suite
once on the branch head before the merge word.

## Branch 6 — `refactor/panels-ocm` (one work package)

HANDOVER §3.4, first slice (§3.4a): the shared panel bases plus their first subscriber, ocm.
Cut from main `97a3a90` (after Branch 5, so the migrated widgets sit under `DashboardScreen`'s
`PANELS` dispatch and the panel-row agreement test already binds their `update_data`
signatures). Facts read off the tree on 2026-09-20:

- `widgets/ocm/` is six panels, 628 lines: `ocm_hero_metrics` (123), `ocm_staking_overview`
  (92), `ocm_signals` (97), `ocm_sparklines` (88), `ocm_activity_feed` (132),
  `ocm_supply_breakdown` (96). Each carries its own copy of what every sibling dashboard also
  carries: `_UNAVAILABLE = "[yellow]unavailable[/]"` (9 files across `widgets/` + `templates/`),
  `_render_row` (7), `_render_box` (4), a `_seen_tx_hashes` / `_seen_keys` dedupe set (10),
  `_fmt_value` (3 — `sparkline_common.fmt_compact` is the hoisted form and differs only at
  ≥ 1e9, on non-numeric input and on the sign of a negative), `_format_event_time` (5 —
  `widgets/fmt.hhmm` is the hoisted form), `_fmt(sig)` / `_fmt_signal` (8; label width 18 in
  ocm and dota, 15 and `[dim]`-wrapped in cattown and the template). `Loading...` is typed in
  68 files.
- **The blank row under a title has two sources in ocm, and one panel has both.** Signals,
  sparklines, staking overview and supply breakdown yield a `Static("")` spacer from `compose`;
  the activity feed states `margin: 0 0 1 0` on `.feed-title` in `minimal.tcss`; the staking
  overview does *both* (`minimal.tcss:1325-1329` gives `.overview-title` the margin and the
  widget yields `#ocm-stake-spacer`), so it paints **two** blank rows at main (composited rows
  12–13 at 170×50, `render_ocm.py`, captured as `b6_before.*` in the session scratchpad). It is
  the one ocm panel absent from `tests/widgets/test_title_blank_row.py`'s table. Hero boxes
  carry the row as the `\n\n` inside each box string (the hero template's own note).
- `minimal.tcss:1301-1380` selects ocm by widget class name (`OCMHeroMetrics`, `OCMHeroBox`,
  `OCMSignals`, …) and by five per-panel title classes (`.overview-title`, `.chart-title`,
  `.signals-title`, `.feed-title`, `.breakdown-title`); `:1644-1650` records a title selector
  that matched nothing for the life of the file, which is what per-panel class names do.
  Textual matches a type selector against every base class — `_css_type_names` of an
  `OCMSignals(PanelBase)` instance is `{OCMSignals, PanelBase, Vertical, Widget, DOMNode}` — so
  a `PanelBase > .panel-title` rule in the base's `DEFAULT_CSS` reaches every subclass, and the
  tcss rules keyed on the ocm class names keep matching unchanged.
- ocm has no leaderboard and no two-column table. `TableLeaderboard` therefore has no
  subscriber in this branch and is **not** built here: it lands in Branch 7 with its first user
  (cattown), as an append-only hoist into `panels.py`. A base with no subclass is a template by
  another name.
- Coverage of the six widgets today: `tests/widgets/test_medi38_unavailable_state.py` (hero and
  signals, three claims each), `test_title_blank_row.py` (sparklines, signals, supply
  breakdown), `test_hidden_shared_address_icons.py` (the feed's icon and copy), the `ocm` case
  of `tests/screens/test_address_icons_everywhere.py` (whole screen at 170 and the pin under the
  real stylesheet), `tests/screens/test_dashboard_screen.py` (every `PANELS` key is a named
  `update_data` parameter). There is no `tests/screens/test_ocm_screen.py` and no
  `tests/widgets/test_ocm_*.py`. The sweep payload leaves staking overview and supply breakdown
  on `Loading...` (follow-up #18, pre-existing, untouched here).

### Design

**`widgets/panels.py`** (new, shared; the Tier 2 trigger):

- Module constants `UNAVAILABLE = "[yellow]unavailable[/]"` and `LOADING = "[dim]Loading...[/]"`
  — the one definition each; a migrated package defines neither.
- `class PanelBase(Vertical)`: `TITLE: str` (the title row's words). `compose` yields
  `Static(self.TITLE, classes="panel-title")` then `yield from self.compose_body()`;
  `compose_body()` is the subclass hook. `DEFAULT_CSS` states the title once
  (`PanelBase > .panel-title { width: 100%; padding: 0 1; text-style: bold; color: $text-muted;
  margin: 0 0 1 0; }`) and one body line class (`PanelBase > .panel-line { padding: 0 1; width:
  100%; }`). **The margin is the blank row**; a subclass yields no spacer. `write(selector,
  content) -> bool` is `query_one` + `update` inside one guard. `write_guarded(selector, build,
  fallback)` builds inside the guard and writes `fallback` when `build()` raises — the shape
  every `_render_box` / `_render_row` in the tree has, hoisted once.
- `class HeroBox(Static)` (`DEFAULT_CSS = ""`) and `class HeroRow(Horizontal)`: `BOX_CLASS:
  type[HeroBox] = HeroBox`, `BOXES: tuple[tuple[str, str], ...]` — `(widget id, label)` per box,
  composed as `BOX_CLASS(f"[dim]{label}[/]\n\n{LOADING}", id=id)`; `DEFAULT_CSS` `HeroRow >
  HeroBox { margin: 0 1; }`; `render_box(selector, label, build)` is ocm's `_render_box`.
  Not a `PanelBase`: a hero row has no title widget. ocm keeps `class OCMHeroBox(HeroBox)` so
  `minimal.tcss`'s `OCMHeroBox` block and the MEDI-38 harness CSS that names it keep matching.
- `class SignalsPanel(PanelBase)`: `ROWS: tuple[tuple[str, str], ...]` (`(id, label)`),
  `LABEL_WIDTH: int = 18`, `DIM_LABEL: bool = False` (Branch 7 sets 15 / `True` for cattown),
  `RECOMMENDATION_ID: str | None = None`. `compose_body` yields one `.panel-line` `Static` per
  row (the first seeded with `"[dim]  Loading...[/]"`), then — when `RECOMMENDATION_ID` is set —
  one blank `.panel-line` and a `.panel-rec` `Static` (`text-align: center; content-align: center
  middle`). Module function `fmt_signal(sig, *, label_width, dim_label) -> str`;
  `render_signal(selector, label, sig)` is ocm's `_render_row` (a `None` or non-dict signal
  renders the `unavailable` row; a malformed dict lands on the fallback row);
  `render_recommendation(text)` writes `"  [bold]-> {text}[/]"` or `""`.
- `class SparklinePanel(PanelBase)`: `LINE_IDS: tuple[str, ...]`; `compose_body` yields one
  `.panel-line` per id, the first seeded `LOADING`. `render_series(series)` takes
  `(label, points, color, unit)` tuples in line order and is the loop ocm/cattown/dota/the
  template all carry — `coerce_points`, `build_sparkline_from_points`, `trend_arrow` and
  **`fmt_compact`** from `sparkline_common`, label padded `label[:8].ljust(8)`; an empty or
  unusable series writes `""`.
- `class RichLogFeed(PanelBase)`: `LOG_ID: str`, `EMPTY_LINE = "[dim]  No activity yet[/]"`;
  `__init__` sets `self._seen_keys: set[str]`; `compose_body` yields `RichLog(id=LOG_ID,
  wrap=True, highlight=True, markup=True)`. Two hooks: `dedupe_key(event) -> str | None`
  (default `event.get("tx_hash") or None`) and `format_row(event) -> Text | None` (abstract; a
  `Text`, never a markup string, so the address icon's click style survives). `render_events(
  events)` is the merged contract of `templates/activity_feed_template.py:158-199` and ocm: an
  empty poll writes the placeholder only while nothing has ever been shown, and `clear()`s
  first so it is written once, not once per poll; keys are recorded; when nothing is new and
  something is shown it returns without rewriting (ocm's flicker guard); otherwise `clear()`,
  `auto_scroll = False`, every row written inside its own guard (an unwritable or `None` row is
  skipped, the rest still land), `EMPTY_LINE` when nothing was written, then
  `call_after_refresh(log.scroll_home, animate=False)`. A subclass's `update_data(recent_events=
  None, **_kwargs)` calls `self.render_events(recent_events)` — the keyword stays the panel's,
  so `PANELS` rows and the agreement test are untouched.

**ocm migration**, one widget at a time, class names and `update_data` signatures unchanged:
`OCMHeroMetrics(HeroRow)` with `BOX_CLASS = OCMHeroBox`; `OCMSignals(SignalsPanel)`;
`OCMSparklines(SparklinePanel)`; `OCMActivityFeed(RichLogFeed)` with `format_row =
_event_to_text` and `hhmm` replacing `_format_event_time`; `OCMStakingOverview(PanelBase)` and
`OCMSupplyBreakdown(PanelBase)` keep their bespoke bodies on `compose_body` + `write`. Deleted
from the package: every `_UNAVAILABLE`, `_render_box`, `_render_row`, `_fmt`, `_fmt_value`,
`_format_event_time`, `_seen_tx_hashes`, every spacer `Static`, every per-panel title/line CSS
class. In `minimal.tcss` the five `OCM* > .<x>-title` rules go (their values — `$text-muted`,
`padding: 0 1`, the margin — are what `PanelBase` states, and the stylesheet outranking
`DEFAULT_CSS` with the same values moves no pixel); the blocks keyed on the widget class names
stay. `templates/` is untouched (Branch 8 deletes it).

**Rendering.** `render_ocm.py` (session scratchpad) before and after, 170×50 and the pin
143×50, under the real stylesheet and a frozen clock. **The expected diff is exactly one row:
the staking overview's second blank row disappears** and its rows move up one within that
panel. Any other differing cell is a finding. `fmt_compact` versus ocm's `_fmt_value` is
value-identical on every magnitude the ocm series can carry (a supply of 10K, an $OCMD supply in
the millions) and the sweep payload carries no histories, so the diff cannot see it; the new
test module pins the equality at 1, 1e3 and 1e6 and states the ≥ 1e9 / non-numeric divergence
as the hoist's one behaviour change.

### Tests

`tests/widgets/test_panels.py` (new), composited through `tests/widgets/surf_compositing.
composite_lines` under `minimal.tcss` (the helper the surf widget tests share — reuse, do not
copy), each on a minimal subclass defined in the test:

1. `PanelBase`: row 0 title, row 1 blank, row 2 body — and the row is the base's: removing
   `margin: 0 0 1 0` from `PanelBase.DEFAULT_CSS` reddens it (state the mutation in the
   docstring; it is the proof that the margin has one source after the tcss rules go).
2. `HeroRow.render_box`: the three MEDI-38 claims (a failed read renders `unavailable`, a real
   `0` is a number, a malformed poll after a good one is not shown as live).
3. `fmt_signal` at width 18 plain and 15 dim; `render_signal` on `None`, on `{}` and on a
   dict whose `label` is an `object()` (fallback row, panel does not raise);
   `render_recommendation("")` blank.
4. `render_series`: `None`, `[]`, a ragged list and a `None`-valued point render `""`; a good
   series renders the sparkline, `fmt_compact` value and arrow; the label is padded to 8.
5. `render_events`: placeholder written once across three empty polls (not once per poll);
   a populated feed survives a later empty poll; `dedupe_key` collisions are not re-recorded
   and a poll with nothing new does not `clear()` (spy on the log); one unwritable row is
   skipped and the others land; all rows unwritable → `EMPTY_LINE`; newest on top.
6. Agreement: every class in `maxpane_dashboard.widgets.ocm` with an `update_data` is a
   subclass of a `panels.py` base, and neither its module nor the class defines `_UNAVAILABLE`,
   `_render_row`, `_render_box`, `_fmt_value`, `_format_event_time`, `_fmt`, `_fmt_signal` or
   `_seen_tx_hashes` — so a copy pasted back in reddens.

Mutation proofs, each named in the commit message with which test reddened: the `clear()`
before the placeholder (test 5 first claim), the per-row guard (test 5 unwritable-row claim),
the `DEFAULT_CSS` margin (test 1). Existing tests that must stay green unchanged:
`test_medi38_unavailable_state.py`, `test_title_blank_row.py` (**add** `OCMStakingOverview`
and `OCMActivityFeed` rows — both now paint exactly one blank row), `test_hidden_shared_address_
icons.py`, `test_address_icons_everywhere.py -k ocm`, `test_dashboard_screen.py`, `-m guard
tests`, `tests/widgets/test_sparkline_common.py`.

### Docs

`.claude/rules/widgets.md`: a "## Panels subclass `widgets/panels.py`" section under the
`DashboardScreen` one — the five bases, the two hooks, the one-source rules (`UNAVAILABLE`,
`LOADING`, the title margin), `widgets/ocm/` as the worked example, `TableLeaderboard` arriving
with Branch 7, `templates/` still the copy-source for a leaderboard until Branch 8. "Reuse
before you build" step 3 gains one sentence pointing at `panels.py` ahead of the templates for
the four shapes it covers. `CLAUDE.md` Architecture `widgets/` line names `panels`. Outcome
paragraph here with the per-file line table, the render-diff result and any deviation.

One implementer, one reviewer (contract verbatim), fix rounds capped at 2, full suite once on
the branch head by the controller, then the owner's merge word.

**Branch 6 outcome (2026-09-20).** `widgets/panels.py` exists with the five bases the Design
names; `TableLeaderboard` was not built (Branch 7, with cattown). All six ocm widgets are on the
bases, with every class name and every `update_data` signature unchanged — the panel-row agreement
test in `tests/screens/test_dashboard_screen.py` and `screens/ocm.py`'s `PANELS` were not touched.

*Line counts are raw `wc -l`*, the convention this plan settled on in Branch 5 WP-B.

| file | before | after | file | before | after |
| --- | --- | --- | --- | --- | --- |
| `widgets/ocm/ocm_hero_metrics.py` | 123 | 94 | `widgets/ocm/ocm_activity_feed.py` | 132 | 94 |
| `widgets/ocm/ocm_staking_overview.py` | 92 | 89 | `widgets/ocm/ocm_supply_breakdown.py` | 96 | 88 |
| `widgets/ocm/ocm_signals.py` | 97 | 45 | **`widgets/ocm/` total** | **628** | **446** |
| `widgets/ocm/ocm_sparklines.py` | 88 | 36 | `themes/minimal.tcss` ocm block | 78 | 66 |
| | | | `widgets/panels.py` (new) | 0 | 446 |

**182 lines out of `widgets/ocm/` and 12 out of the stylesheet; 446 lines of shared base in.** The
repo is 252 production lines *larger* today, and that is the expected shape of the first slice: one
subscriber cannot amortise a base. Branches 7 and 8 move cattown, dota, ttt, talismans, fwa, base
and bakery onto the same 446 lines and delete `templates/`, which is where the estimate in
HANDOVER §3.4 is paid. `panels.py` is also documentation-heavy by design — it is the file the next
dashboard reads instead of copying a sibling.

**Render diff.** `render_ocm.py` on the sweep payload under the real stylesheet and a frozen clock,
before and after, at 170×50 and at the 143 pin. Both sizes: **50 painted rows, two differing rows,
the same two, and they are the predicted one-row shift**:

```
### 170x50: 50 vs 50 rows
  row 12: before=''
           after='  Loading...'
  row 13: before='  Loading...'
           after=''
  -> 2 differing row(s)
### pin-143x50: 50 vs 50 rows
  row 12: before=''
           after='  Loading...'
  row 13: before='  Loading...'
           after=''
  -> 2 differing row(s)
```

(The first capture of this block said 51: the comparison script split the file on `"\n"` and
counted the trailing empty string after the final newline. `wc -l` says 50, which is the row count
`render_ocm.py` writes and the number the reviewer checked against. Corrected in fix round 1, M5;
no capture changed, only the count printed beside them.)

That is STAKING OVERVIEW's second blank row disappearing and its rows moving up one inside the
panel, exactly as the Design predicted; every other cell is byte-identical at both widths. The
panel is still on `Loading...` under the sweep payload (follow-up **18**, pre-existing, untouched)
and the degradation log is unchanged: `Failed to update OCMStakingOverview` and `Failed to update
OCMSupplyBreakdown` are still raised at the same point, because both panels build their row text
*before* the guarded write, as they did. TRENDS, SIGNALS and SUPPLY BREAKDOWN each traded a spacer
`Static` for the title margin, which is one row either way, so nothing below them moved.

**Mutation proofs** (restored by inverse edit; `git status` clean after each):

| mutation | reddened |
| --- | --- |
| `margin: 0 0 1 0` deleted from `PanelBase.DEFAULT_CSS` | `test_panels.py::test_panel_base_paints_title_blank_row_then_body`, its two `render_series` row-index cases, and all five ocm rows of `test_title_blank_row.py` — 8 failed, 68 passed |
| `clear()` deleted before the placeholder in `render_events` | `test_panels.py::test_the_placeholder_is_written_once_across_three_empty_polls` (3 placeholders on screen, not 1) — 1 failed, 75 passed |
| the per-row `try` deleted in `render_events` | `test_panels.py::test_one_unwritable_row_is_skipped_and_the_others_land` and `::test_every_row_unwritable_falls_back_to_the_empty_line` — 2 failed, 74 passed |
| a private `_coerce_points` pasted back into `ocm_sparklines.py` | `test_sparkline_common.py::test_helpers_are_the_shared_functions[OCMSparklines]` and `::test_no_module_redefines_a_shared_helper[OCMSparklines]` — 2 failed, 126 passed (the fourth proof, for the one existing test this branch had to change) |

**One behaviour change inside the migration, beyond the blank row.**
`fmt.hhmm` replaces ocm's `_format_event_time` in the feed's `HH:MM` cell, as the Design asks, and
the two are not byte-identical: `hhmm` renders `??:??` for `None`, for `0` and for `float("inf")`
where the old copy raised `TypeError` on `None`, printed `01:00` for epoch zero (an unread
timestamp looking like data, H14) and raised `OverflowError` on `inf`. The sweep payload carries a
real timestamp, so the render diff cannot see it; `tests/widgets/test_hidden_shared_address_icons.py`
seeds `timestamp: 0` and now reads `??:??` there, which is the intended reading and is what every
other feed in the repo already shows. `fmt_compact` versus `_fmt_value` is the same shape of change
and `tests/widgets/test_panels.py` pins both the agreement (1, 1e3, 1e6) and the divergence
(≥ 1e9, negatives, non-numeric).

**Three deviations from the Design, each stated rather than taken silently.**

1. **`tests/widgets/test_sparkline_common.py` could not stay green unchanged**, though the Tests
   paragraph lists it among the files that must. Its `test_helpers_are_the_shared_functions`
   resolved `_coerce_points` / `_build_sparkline` on `inspect.getmodule(widget_cls)` — the *leaf*
   module — and `OCMSparklines` no longer imports them, because its render loop moved into
   `panels.SparklinePanel`. Worse than a rename: the lookup returned `None` and the assertion read
   `None is not coerce_points`, so a widget that rendered through a base would have failed this
   test *whatever* the base imported. The claim ("no dashboard may carry its own copy") is
   unchanged; the lookup now walks the widget's MaxPane MRO, leaf first, and
   `test_no_module_redefines_a_shared_helper` reads every module on that chain rather than only the
   leaf — so it covers `panels.py` too, which the old form did not. The alternative — leaving two
   dead import aliases in `ocm_sparklines.py` to satisfy the leaf lookup — would have been a
   re-declaration written to fool a test. Mutation proof that the new form still bites is the
   fourth row above.
2. **`OCMActivityFeed` keeps a `DEFAULT_CSS`.** The Design deletes "every per-panel title/line CSS
   class and the `DEFAULT_CSS` that stated them"; `OCMActivityFeed > RichLog { height: 1fr; padding:
   0 1; scrollbar-size: 1 1 }` is neither a title nor a line class, so it stayed on the widget
   rather than being hoisted into `RichLogFeed`. Hoisting it would have been a second, unasked
   behaviour decision for every future feed; `OCMStakingOverview` keeps its own
   `{ height: auto; padding: 0 }` for the same reason (against `Vertical`'s `height: 1fr` it is
   load-bearing, and it is not a title rule).
3. **"Reuse before you build" step 3 gained the sentence in place rather than a new step.** The
   Docs paragraph reads "step 3 gains one sentence pointing at `panels.py` ahead of the templates";
   inserting `panels.py` as a *new* step 3 would have renumbered `templates/` to 4 and broken the
   Branch 8 row of the table at the top of this file, which cites "`rules/widgets.md` step 3". The
   templates entry now opens with "but only after `widgets/panels.py`".

Named tests, all green, no directory-wide or suite runs — **462 passed** across:
`tests/widgets/test_panels.py` (39), `test_medi38_unavailable_state.py` (26),
`test_title_blank_row.py` (37, two new rows), `test_hidden_shared_address_icons.py` (10),
`test_sparkline_common.py` (89), `test_fmt.py` (25),
`tests/screens/test_address_icons_everywhere.py -k ocm` (2), `tests/screens/test_dashboard_screen.py`
(26), `tests/screens/test_refresh_guard.py` (7), `tests/test_address_rule.py` (10),
`tests/test_address_sweep_registry.py` (9), and `-m guard tests` (182). The full suite is the
controller's, once, on the branch head.

**Branch 6 fix round 1 (2026-09-20).** Review verdict `Needs fixes: 0 Critical, 1 Important`; all
six findings closed in one commit. Re-render of `render_ocm.py` to `b6_fix1.*`: **byte-identical to
`b6_after.*` at 170×50 and at the 143 pin**, so the whole round moved no pixel.

- **I1 (Important).** `panels.HeroBox` and `panels.SignalsPanel` collided **by name** with
  `widgets/hero_metrics.py:40` and `widgets/signals_panel.py:37` (both bakery-only), each of which
  has a **bare** block in `minimal.tcss` (`:31`, `:102`). Textual matches a type selector against
  every base class, so those bakery blocks reached every subscriber of the new bases; nothing moved
  only because ocm's own blocks restated the same values and won on source order. The reviewer
  proved it by inserting `min-width: 60` into `minimal.tcss:31`, which widened ocm's SUPPLY box
  from 54 to 164 columns. Renamed to **`HeroBoxBase`** and **`SignalsPanelBase`** (with
  `HeroRow.DEFAULT_CSS`, the `BOX_CLASS` annotation, `query_one`, `__all__`, both ocm subclasses
  and `rules/widgets.md` updated), and two `guard` agreement tests added to `test_panels.py`: no
  class name defined in `panels.py` may be defined by any other module under
  `maxpane_dashboard/widgets/` or `templates/` (walked with `pkgutil`, compared on `vars(module)`),
  and none may appear as a **bare type selector** in `minimal.tcss` — a token matching
  `(?<![.#$\w-])<Name>(?![\w-])` in the stylesheet's selector text, with `/* … */` comments and
  every declaration body stripped first so a class name written in prose or in a value is not a
  hit. The rename immediately turned three of the hero claims red, because the test's own box
  double had been silently borrowing `width: 1fr` from bakery's `HeroBox` block — the collision,
  demonstrated inside this branch's own tests. The double is now `HeroBoxDouble` and states its
  width, as every real box class does.
- **M1.** `SignalsPanelBase.compose_body` hand-typed `"[dim]  Loading...[/]"` beside `LOADING`.
  Now `LOADING_ROW = LOADING.replace("[dim]", "[dim]  ", 1)`, exported, and
  `test_panels_defines_the_two_strings_exactly_once` pins both the value and the derivation.
- **M2.** `PanelBase.write` swallowed a missing target silently, where the pre-migration
  staking-overview / supply-breakdown writes raised into `DashboardScreen` and got a `warning`.
  It now logs `"%s: could not write %s: %s"` on the module logger
  `maxpane_dashboard.widgets.panels` for a missing target **and** for a failing `update`; one
  `caplog` test. `write_guarded` and `render_box` keep their pre-migration silence on the
  fallback path — that was never a regression, and changing it was not the finding.
- **M3.** `key in self._seen_keys` sat outside the guard around `dedupe_key`, so an unhashable
  `tx_hash` (a JSON list from a third-party payload) raised `TypeError` out of `update_data`
  **after** `log.clear()` and blanked the feed. The membership test and the `add` are now inside
  their own `except TypeError`, which treats such an event as always-new and always-drawn. A
  `dedupe_key` that *raises* still skips without counting as new, so an all-malformed poll still
  leaves a populated feed alone.
- **M4.** `format_row`'s `NotImplementedError` was caught by the per-row guard, so a subclass that
  forgot the hook painted `No activity yet` forever. It is now re-raised ahead of the broad
  `except`: a programming error fails loudly, a bad row is still skipped.
- **M5.** The row count beside the render captures said 51; `wc -l` says 50 (the comparison script
  counted the trailing empty string after the final newline). Corrected above; no capture changed.
- **M6 (filed, not fixed).** `test_sparkline_common.py`'s `_COERCE_NAMES` / `_BUILD_NAMES` are
  fixed name lists, so a private helper bound under an unlisted alias passes. Pre-existing shape,
  carried across rather than introduced. Filed as follow-up **20** in
  `docs/handover_followups_2026_09.md` under a new "## Branch 6 — panels" heading; Minor, Tier 0
  when that file is next touched.

Mutation proof for the new agreement pair: `HeroBoxBase` renamed back to `HeroBox` (with an alias
keeping the rest of the module working) →
`test_panels.py::test_no_panels_base_shares_its_name_with_another_widget_class` **and**
`::test_no_panels_base_is_a_bare_type_selector_in_the_stylesheet[HeroBox]` failed, 48 passed;
restored by inverse edit.

Named tests after the round, all green: `test_panels.py` **49** (was 39), `test_medi38_unavailable_
state.py` 26, `test_title_blank_row.py` 37, `test_hidden_shared_address_icons.py` 10,
`test_sparkline_common.py` 89, `tests/screens/test_dashboard_screen.py` 26,
`tests/screens/test_address_icons_everywhere.py -k ocm` 2, `tests/test_address_rule.py` 10,
`tests/test_address_sweep_registry.py` 9, `-m guard tests` **189** (was 182 — the seven new guard
cases are the class-collision test plus one bare-selector case per class in `panels.py`).

**Branch 6 fix round 2 (2026-09-20).** Re-review: I1 and M1–M6 all ADDRESSED; three new findings,
one Important. The last fix round the tier allows. Re-render to `b6_fix2.*`: **byte-identical to
`b6_after.*` at 170×50 and at the 143 pin** (`cmp`, 50 rows each), so this round moved no pixel
either. The degradation log is unchanged (`OCMStakingOverview` / `OCMSupplyBreakdown` still fail on
the harness's `None` scalars — pre-existing follow-up 18).

- **N3 (Important).** `RichLogFeed.render_events` keyed "a transient empty poll must not wipe a
  populated feed" on `self._seen_keys` being non-empty — but `_seen_keys` only fills on the
  hashable-key path. For the two documented key-less paths, `dedupe_key` returning `None` (the
  "always new" mode) and the unhashable key M3 routes the same way, the set stayed empty while rows
  were on screen, so the next empty poll ran `log.clear(); log.write(EMPTY_LINE)` over live rows: a
  **false degradation**, which CLAUDE.md forbids as explicitly as a stale number. The contract now
  hangs off `self._drawn`, set when at least one row lands, and both the empty-poll branch and the
  flicker guard read it. With `dedupe_key` returning `None` every event is new, so the flicker
  guard never fires and every poll redraws — that is what always-new means, and it is now stated in
  the docstring. Three cases, one per path: `test_a_key_less_feed_survives_a_later_empty_poll`,
  `test_an_unhashable_key_feed_survives_a_later_empty_poll`, and the pre-existing keyed
  `test_a_populated_feed_survives_a_later_empty_poll` (whose docstring now says it passed even
  under the defect, which is why the other two exist). Mutation: empty-poll branch reverted to
  `if not self._seen_keys` → both new cases failed, 49 passed; restored by inverse edit.
- **N1 (Minor).** The bare-selector guard was written as a bare *token* regex and so refused
  `PanelBase > .panel-title { color: $accent; }` — exactly the cross-dashboard theme override
  `rules/widgets.md` documents, in the stylesheet that is *meant* to outrank `DEFAULT_CSS`.
  Narrowed to a **bare block**: the name standing alone as a whole selector, matched as
  `,\s*<Name>\s*,` against each rule's selector list wrapped in sentinel commas
  (`_css_selector_lists` now returns one normalised string per rule instead of one blob).
  `HeroBoxBase {` matches, `A, HeroBoxBase, B {` matches, `OCMHeroBox {` and `HeroBoxBase > X {`
  and `PanelBase > .panel-title {` do not — the five examples are asserted in
  `test_the_bare_block_matcher_admits_a_theme_override`. The class-name walk also now covers
  `maxpane_dashboard.screens`, since a `Screen` subclass is a `Widget` and its name is a type
  selector too. Three mutations: `HeroBox = HeroBoxBase` appended to `panels.py` →
  `test_no_panels_base_shares_its_name_with_another_widget_class` **and**
  `…_is_a_bare_type_selector_in_the_stylesheet[HeroBox]` failed, 51 passed; a bare
  `HeroBoxBase { min-width: 60; }` appended to `minimal.tcss` →
  `…_is_a_bare_type_selector_in_the_stylesheet[HeroBoxBase]` failed **and** so did
  `test_hero_box_malformed_poll_after_a_good_one_is_not_shown_as_live`, 50 passed — the second
  failure is the collision mechanism itself, one bare block reshaping every subclass's geometry;
  `PanelBase > .panel-title { color: $accent; }` appended instead → 52 passed, green. All three
  restored by inverse edit.
- **N2 (Minor).** Follow-up 20's evidence sentence attributed the hole to renaming ocm's import
  alias. The reviewer's actual mutation was a private sparkline builder defined **in `panels.py`**,
  called by `render_series`, renamed `_build_sparkline` → `_spark_from`, after which
  `test_sparkline_common.py` passed 89/89 — the copy sat on the MRO the walk covers, under a name
  the list does not. Corrected in `docs/handover_followups_2026_09.md`.

Named tests after the round, all green: `test_panels.py` **52** (was 49), `test_medi38_unavailable_
state.py` 26, `test_title_blank_row.py` 37, `test_hidden_shared_address_icons.py` 10,
`test_sparkline_common.py` 89, `tests/screens/test_dashboard_screen.py` 26,
`tests/screens/test_address_icons_everywhere.py -k ocm` 2, `tests/test_address_rule.py` 10,
`tests/test_address_sweep_registry.py` 9, `-m guard tests` **190** (was 189 — the one new guard
case is the bare-block matcher's example set).

## Branch 7 — `refactor/panels-small-four` (two work packages)

HANDOVER §3.4, second slice (§3.4b): cattown, dota, talismans and ttt onto the `widgets/panels.py`
bases Branch 6 built, plus the one base Branch 6 deferred, `TableLeaderboard`, with cattown as its
first user. Cut from main `ad5af4d`. Facts read off the tree on 2026-09-20 (survey in the
session, every module read whole):

- 26 widget modules, 3,631 lines with the four `__init__` and three `_chain` files: cattown 6
  (712), dota 6 (609), talismans 7 (897), ttt 7 (1,289). The four hero rows, the four signals
  panels, the four sparkline panels and the four feeds are the Branch 6 shapes; **eight** widgets
  are a title over a `DataTable` (`CTLeaderboard`, `DOTALeaderboard`, `TalismansLeaderboard`,
  `TalismansMaterialsTable`, `TalismansMatrixTable`, `TTTLeaderboard`, `TTTFeesTable`,
  `TTTClaimsTable`) and all eight agree on `cursor_type="row"`, `zebra_stripes=True`, `clear()` then
  a "No data" row or a capped slice (10 / 20 / 10 / 12 / none / 10 / 10 / 6), rank-1 bolding, and
  — six of eight — a `Loading...` seed row added in `on_mount` whose cell position varies. That is
  the `TableLeaderboard` contract. `CTBestPlays` and `DOTABestPlays` are a two-column text board
  with no sibling outside this pair; they go on `PanelBase` with their bodies bespoke.
- **The four packages carry the copies Branch 6 counted, and diverge from the hoisted forms in
  named ways.** `_UNAVAILABLE` ×4 (byte-identical to `panels.UNAVAILABLE`); `_DASH` ×8 (=
  `fmt.DASH`); `_render_box` in cattown and dota (dota's is `HeroRow.render_box` exactly; cattown's
  has a `rich.text.Text` branch because the LEADER box carries an address icon — the base has no
  `Text` path today); `_render_row` / `_fmt` in cattown and dota (= `render_signal` /
  `fmt_signal(15, dim)` / `fmt_signal(18, plain)` exactly); `_format_event_time` / `_format_ts` ×3
  (talismans ≡ ttt ≡ `fmt.hhmm` minus the `OverflowError` arm; cattown's catches only
  `(ValueError, OSError)` so `int(None)` raises, and **renders a clock time for `ts == 0`**);
  `_fmt_int` ×6, `_fmt_float` ×2, `_safe_get` ×2 (talismans ≡ ttt, nothing hoisted covers them);
  `_safe_symbol` ×2 inside ttt; `_RARITY_COLORS` ×3 inside cattown (dead in the feed);
  `_WAITING` ×2 (talismans/ttt sparklines). Dead: `ttt_claims_table._fmt_multiplier`,
  `tal_hero_metrics._GENESIS`, `ct_activity_feed._RARITY_COLORS`, dota hero's `token_price_usd`
  parameter.
- **Where the base contract and the widget disagree, and what the plan does about each:**
  - talismans and ttt **signals drop the label** (`  [c]●[/] [c]{value}[/]`), have a mid-panel
    blank separator row, no recommendation; ttt hides its `fresh` row at runtime
    (`display = bool(text)`) and `safe_markup`s the value where talismans does not; both degrade
    to `--` (talismans through a `_UNAVAILABLE_SIGNAL` dict) and neither guards its four writes.
  - talismans and ttt **sparklines** pad labels to 16 and 12 (dota to 9, cattown/ocm to 8), draw
    **no trend arrow**, write `waiting for data...` below two points where `render_series` writes
    `""`, and format values with `{int(v):,}` (both) and a `$…B` at `.2f` (ttt volume) where the
    base uses `fmt_compact`. cattown's `_fmt_value` differs from `fmt_compact` only on negatives,
    NaN and ≥ 1e9; dota's is unrelated (`abs ≥ 100 → .0f else .1f`, no K/M/B), and the sweep's
    frontline values sit under 100.
  - talismans and ttt **hero rows** have no guard at all (four bare `query_one().update()` each; a
    missing box raises into the screen) and degrade on exception to `--`, not `unavailable`; both
    are absent from `test_medi38_unavailable_state.py`. Box bodies are `big\nsub` under the
    `label\n\n` head, which `render_box`'s `f"[dim]{label}[/]\n\n{build()}"` already carries.
  - the dota feed is a **hero roster** (sorted, rewritten whole each poll, placeholder
    `No heroes yet`); talismans and ttt feeds carry **no `tx_hash`**, cap at 25 and `clear()`
    unconditionally; cattown's is the pre-`_drawn` contract (placeholder stacked once per empty
    poll, unhashable key raises after `clear()`). ttt's `_event_to_line` returns `str` *or* `Text`.
- **Stylesheet.** cattown `:1108-1190` and dota `:1192-1299` blocks are all live; the blank row
  under CT LEADERBOARD is `CTLeaderboard > Static { margin: 0 0 1 0 }` (`:1132`, its title has no
  class), under DOTA LEADERBOARD `.dota-lb-title` (`:1241`), under both feeds a `.feed-title` /
  `.dota-feed-title` margin. ttt `:1596-1689` has **three dead title blocks** (`TTTLeaderboard >
  .leaderboard-title` `:1619`, `TTTActivityFeed > .feed-title` `:1667`, `TTTFeesTable > .fees-title,
  TTTClaimsTable > .claims-title` `:1683`) — the widgets compose `ttt-*-title` classes and paint
  their blank row from a `Static(" ")` spacer; `TTTSignals` alone already states `margin: 0 0 1 0`
  on its own title. talismans `:1691-1749` names no title class at all; every talismans title is
  styled by its widget's `DEFAULT_CSS` and every blank row is a `Static(" ")`. No bare block names
  a `panels.py` class; the `Base` suffix and Branch 6's guard keep it so. **The new base is
  `TableLeaderboard`, not `Leaderboard`**: bakery's `widgets/leaderboard.py` owns that name and a
  bare block.
- **Pins.** None of the four screens declares a pin; all sweep at `__main__.FULL_LAYOUT_COLUMNS`
  (143). The one in-widget pin is `ttt_fees_table._SYM_WIDTH = 5` (measured table at `:43-81`) with
  `ttt_leaderboard._SYM_WIDTH` deliberately equal — both stay where they are, untouched.
  `tests/screens/test_ttt_address_icon_layout.py` certifies that neither ttt table scrolls at 143.
- **Coverage today.** `test_title_blank_row.py` lists CT/DOTA sparklines, signals, best-plays,
  `TTTSparkline`, `TTTSignals` ×2 — not the leaderboards, feeds, hero rows, ttt tables or any
  talismans widget. `test_medi38_unavailable_state.py` lists CT/DOTA hero + signals and
  `TalismansSignals`. `test_sparkline_common.py` binds all four sparklines to the shared
  primitives. `test_markup_safety.py` holds the three hostile-string leaderboard tests;
  `test_cattown_talismans_address_icons.py` and `test_ttt_address_icons.py` the icon tests (the
  latter pins the two `_fmt_eth` goldens, 4 dp fees / 5 dp claims); `test_talismans_widgets.py`
  (310 lines) is the one per-widget module; `test_talismans_screen.py`, `test_ttt_address_icon_
  layout.py`, `test_refresh_guard.py` composite the screens. There is no cattown, dota or ttt
  widget test module.

### Design

**Zero-rendering-change is the acceptance rule, with the changes named here as the only
exceptions.** `render_case.py` (session scratchpad; the Branch 6 harness generalised to a case
name and every view) captured all four dashboards at main `ad5af4d` — 170×50 and the 143 pin,
default view and the `c` view for ttt and talismans, twelve files `b7_before_*` — under a frozen
clock and the sweep payload. Every post-migration capture must be **cmp-identical** to its
`before`, because unlike ocm no panel here paints two blank rows: each spacer `Static`, tcss margin
or `Static(" ")` is traded for the `PanelBase` title margin one-for-one. A differing cell is a
finding. The named behaviour changes, none of which the sweep payload can reach:

1. `fmt.hhmm` replaces the three `_format_event_time` / `_format_ts` copies: `??:??` for `None`,
   `0` and `inf` (Branch 6's change, now on three more feeds; cattown printed a clock for epoch 0).
2. MEDI-38 on the talismans and ttt hero rows and ttt signals: a build that raises lands on
   `unavailable` inside the guard instead of raising into the screen (`--` stays the value for a
   `None` the manager served deliberately — `total_cores` while enumeration syncs).
3. `fmt_signal` escapes `value_str` through `markup_safety.safe_markup` for every subscriber —
   ttt did, talismans did not, and a signal value may carry a token symbol. No `value_str` in
   `analytics/` contains a `[`, so the sweep and the goldens see nothing.
4. The feed contract: the placeholder is written once, an unhashable key is always-new, and a
   populated feed survives an empty poll (talismans, ttt and dota cleared and re-painted the
   placeholder). **Corrected in WP-A fix round 1, review C1 — the premise below was false and
   the design that rested on it would have shipped a stale number.** The original text read "the
   manager serves `None` for a failed read, so the always-new path with `[]` keeps the last
   roster under the status bar's as-of marker". It does not: `data/dota_manager.py:64-70` sets
   `game_state = None` on a failed fetch, `:118` starts `heroes_raw = []` and fills it only when
   `game_state is not None`, `:239-256` builds `heroes` from it and `:306` serves it — so a
   **failed read served `[]`**, and `render_events` tests `if not events`, so both `[]` and
   `None` left the previous poll's HP and ALIVE/DEAD rows on screen. Pre-migration the roster
   cleared and painted `No heroes yet`, so the migration would have *introduced* "a stale number
   presented as live" on the one panel where every row is a number that expires.

   What ships instead: `RichLogFeed` grows `SNAPSHOT: bool = False`. **Stream** (the default,
   every other feed) is the Branch 6 contract byte for byte — an event that happened is still
   true when the next poll brings nothing, so a transient empty poll leaves the rows alone.
   **Snapshot** (dota's roster) re-paints the whole panel every poll, keeps no row from a
   previous one, and therefore tells the two falsy inputs apart: `None` is "could not look" and
   writes the new derived `UNAVAILABLE_LINE`, `[]` is the real negative and writes `EMPTY_LINE`.
   The manager is fixed in the same round so the distinction is reachable at all: the served
   `heroes` key is `None` when `game_state is None`, `[]` when the read succeeded with no heroes
   (`tests/data/test_dota_manager.py` pins both). Nothing else the manager derives from
   `heroes_raw` is touched — that is pre-existing and out of scope.
5. `fmt_compact` replaces cattown's `_fmt_value` (differs on negatives, NaN, ≥ 1e9 — none
   reachable for a prize pool). dota, talismans and ttt **keep their value formatters** through
   the new hook below, because theirs differ on values the panel actually shows.

**WP-A — `panels.py` extensions (append-only; owner of `panels.py` and `minimal.tcss` for this
WP) + cattown + dota.** Every extension is a class attribute with the Branch 6 default, so ocm is
untouched and its tests must stay green unchanged:

- `class TableLeaderboard(PanelBase)`: `TABLE_ID: str`, `COLUMNS: tuple[tuple[str, int], ...]`
  (`(label, width)`), `CURSOR_TYPE = "row"`, `ZEBRA = True`, `ROW_CAP: int | None = 10`,
  `LOADING_ROW: tuple[str, ...] | None = None` (seeded in `on_mount` when set — the cell that
  says `Loading...` differs per table, so the subclass types the whole tuple), `EMPTY_ROW:
  tuple[str, ...]` (the "No data" row). `compose_body` yields `DataTable(id=TABLE_ID)`; `on_mount`
  adds the columns and the seed row. `render_table(rows, *, footer=None)`: `clear()`; `None` or
  empty → `EMPTY_ROW`; else the capped slice through the hook `build_row(index, item) ->
  tuple | None` (`None` skips the item — the non-dict guard talismans and ttt carry), then the
  optional `footer` tuple (the matrix table's bold TOTAL row). Every `add_row` inside its own
  guard so one bad row does not empty the table. Address cells, rank-1 bolding, `_SYM_WIDTH`,
  the matrix's dict payload and the claims table's "Today" detection stay in the subclass —
  the base owns mechanics, never a cell's formatting.
- `HeroRow.render_box`: when `build()` returns a `rich.text.Text`, the box gets
  `Text.from_markup(f"[dim]{label}[/]\n\n") + text` — cattown's LEADER box (address icon with its
  click style) is the reason. The `str` path is unchanged.
- `SignalsPanelBase`: a `ROWS` item may be `(id, None)` — a **label-less** row, formatted
  `  [c]{ind}[/] [c]{value}[/]` by `fmt_signal(sig, label_width=…, dim_label=…, labelled=False)`
  — and may be `None`, a blank `.panel-line` separator. `fmt_signal` escapes `value_str`
  (change 3). Nothing else; ttt's runtime-hidden row is one `display` assignment in ttt's
  `update_data` after `render_signal`.
- `SparklinePanel`: `LABEL_WIDTH = 8`, `SHOW_ARROW = True`, `EMPTY_TEXT = ""`, and a hook
  `fmt_value(value, unit) -> str` defaulting to `fmt_compact`. `render_series` pads
  `label[:LABEL_WIDTH].ljust(LABEL_WIDTH)`, appends the arrow only when `SHOW_ARROW`, writes
  `EMPTY_TEXT` for an unusable series, and seeds `EMPTY_TEXT or LOADING` on the first line — so
  talismans/ttt (`16`/`12`, `False`, `[dim]waiting for data...[/]`) render as today, and cattown
  (8) / dota (9) do not clip.
- `RichLogFeed`: nothing new. dota subclasses it with `dedupe_key → None`, `EMPTY_LINE =
  "[dim]  No heroes yet[/]"`, the alive-first / level-desc sort in `update_data` before
  `render_events`, and `format_row` returning `Text.from_markup(...)` of today's string.
- cattown: `CTHeroMetrics(HeroRow)` with `CTHeroBox(HeroBoxBase)`; `CTSignals(SignalsPanelBase)`
  15/dim with `RECOMMENDATION_ID` — **its recommendation line is `  [dim]→ Recommendation:[/]
  [bold]{rec}[/]`**, not the base's `-> {text}`, so `render_recommendation` gains no option:
  cattown writes that line itself through `write`, keeping the pixel; `CTSparklines(SparklinePanel)`
  (its labels are hand-padded to 8 already); `CTActivityFeed(RichLogFeed)` with `format_row =
  _catch_to_text`; `CTLeaderboard(TableLeaderboard)` (first user; `LOADING_ROW = None`, cap 10);
  `CTBestPlays(PanelBase)` bespoke body. `_RARITY_COLORS` once, in a new `widgets/cattown/_fmt.py`
  beside `_fmt_kibble` and `_countdown`. dota: the same six shapes; `DOTALeaderboard` cap 20;
  `DOTABestPlays(PanelBase)`; `_fmt_usd` stays in the hero module (one user).
- `minimal.tcss` (WP-A owns it for both packages): delete the per-title blocks the base now states
  (`CTLeaderboard > Static`, `CTSparklines > .chart-title`, `CTSignals > .signals-title`,
  `CTActivityFeed > .feed-title`, `CTBestPlays > .ev-title`, the five dota `.dota-*-title` blocks);
  keep every block keyed on a widget class name. `CTBestPlays`/`DOTABestPlays` title rows carry
  the same values, so PanelBase's rule moves no pixel; the render diff is the proof.

**WP-B — talismans + ttt (owner of `minimal.tcss` for the ttt block, `widgets/fmt.py`
append-only).** Hoists first, in the same commit: `fmt.fmt_int(value) -> str` (the module-level
body: `None → DASH`, `int(v)` grouped, `DASH` on failure) replaces all six `_fmt_int`;
`fmt.fmt_float(value, spec) -> str` the two `_fmt_float`; `fmt.safe_get(mapping, key, default)`
the two `_safe_get`; `fmt.DASH` the eight `_DASH`; `fmt.hhmm` the two `_format_ts`. `_safe_symbol`
once in a new `widgets/ttt/_fmt.py`. The two `_fmt_eth` (4 dp / 5 dp, both "not `fmt.fmt_eth`")
stay behind their goldens — a precision change is a pixel change and not this branch's. Then:
`TalismansHeroMetrics(HeroRow)` / `TTTHeroMetrics(HeroRow)` with `render_box` (change 2; the extra
`tal-hero-box` / `ttt-hero-box` classes go — nothing names them); `TalismansSignals` / `TTTSignals`
on `SignalsPanelBase` with label-less rows and the `None` separator, ttt keeping the `display`
toggle; `TalismansSparkline` / `TTTSparkline` on `SparklinePanel` with `LABEL_WIDTH` 16 / 12,
`SHOW_ARROW = False`, `EMPTY_TEXT` the waiting line, `fmt_value` returning today's
`_fmt_count` / `_fmt_burns` / `_fmt_volume_usd` per line (the hook receives `unit`, so one
override can switch on it); `TalismansActivityFeed` / `TTTActivityFeed` on `RichLogFeed` with
`dedupe_key → None`, the `[:25]` cap in `update_data`, and every row a `Text`; the five tables on
`TableLeaderboard` (`LOADING_ROW` the tuple each seeds today; matrix passes `footer=`). Every
`Static(" ")` spacer goes. tcss: the three dead ttt title blocks and `TTTSparkline > .ttt-spark-
title`, `TTTSignals > .ttt-signals-title` go; talismans has none to delete; the widget-class blocks
stay. `test_talismans_widgets.py` is adapted only where it queried a class the base renamed
(`.tal-*-title` → `.panel-title`), never loosened.

WP-B starts only after WP-A's review round closes: it subclasses the extensions WP-A adds and
edits the same stylesheet.

### Tests

`tests/widgets/test_panels.py` gains, each on a minimal subclass composited through
`surf_compositing.composite_lines` under `minimal.tcss`:

1. `TableLeaderboard`: row 0 title, row 1 blank, row 2 the header; the seed row appears when
   `LOADING_ROW` is set and not when `None`; `None` and `[]` paint `EMPTY_ROW` exactly once;
   `ROW_CAP` slices; `build_row` returning `None` skips ~~without a gap in the ranks the subclass
   assigns~~ **without a gap in the composited rows, while `index` stays the item's position in
   the capped slice — so the third item still prints rank `3`** (corrected in WP-A fix round 1,
   review M4: the original wording described the opposite behaviour, and the implemented one is
   what `tal_leaderboard.py:95-98` does today and what a subclass bolding on `index == 0`
   needs); one `add_row` that raises leaves the other rows on screen (mutation: delete the
   per-row guard → this test); `footer` lands last.
2. `render_box` with a `Text` body keeps the `Text`'s style spans (a `meta` click action on a
   span survives — the reason the branch exists) and the label row above it.
3. `fmt_signal(labelled=False)` and the `None` separator row: row indices under composition;
   a `value_str` of `"[red]x"` renders literally (change 3; mutation: drop the escape).
4. `SparklinePanel` at `LABEL_WIDTH = 12`, `SHOW_ARROW = False`, `EMPTY_TEXT` set: the label
   width, no arrow glyph, the empty text on `[]`, `fmt_value` override honoured; the defaults
   still reproduce Branch 6's rows (the existing cases stay green unchanged).
5. Agreement, widened from ocm to the five migrated packages: every widget class with an
   `update_data` in `widgets/{ocm,cattown,dota,talismans,ttt}` subclasses a `panels.py` base;
   no module there defines `_UNAVAILABLE`, `_UNAVAILABLE_SIGNAL`, `_render_row`, `_render_box`,
   `_fmt_value`, `_format_event_time`, `_format_ts`, `_fmt`, `_fmt_signal`, `_seen_tx_hashes`,
   `_fmt_int`, `_fmt_float`, `_safe_get`, `_DASH`, `_WAITING`, and no `compose` yields a `Static`
   whose content is `""` or `" "` (the spacer shapes). WP-A ships it for ocm + cattown + dota,
   WP-B extends the package list.

Existing tables extended, not new files: `test_title_blank_row.py` gains a row for **every**
widget in the four packages that is a `PanelBase` (leaderboards, feeds, tables, all seven
talismans panels); `test_medi38_unavailable_state.py` gains `TalismansHeroMetrics`,
`TTTHeroMetrics`, `TTTSignals` with the three claims (change 2). Named tests per WP, all with
`-m guard tests`: `test_panels.py`, `test_title_blank_row.py`, `test_medi38_unavailable_state.py`,
`test_sparkline_common.py`, `test_fmt.py`, `test_markup_safety.py`, the two address-icon widget
files, `test_talismans_widgets.py`, `tests/screens/test_dashboard_screen.py`,
`test_refresh_guard.py`, `test_talismans_screen.py`, `test_ttt_address_icon_layout.py`,
`test_address_icons_everywhere.py -k "cattown or dota or talismans or ttt or ocm"`,
`tests/test_address_rule.py`, `tests/test_address_sweep_registry.py`. Mutation proofs named in
each commit message with which test reddened. The full suite runs once on the branch head, by
the controller.

### Docs

`.claude/rules/widgets.md` "Panels subclass" section: `TableLeaderboard` joins the list (its
hook, the seed-row rule, what stays in the subclass), the three `SparklinePanel` attributes and
`fmt_value`, label-less and separator signal rows, the `Text` branch of `render_box`; the
worked-example sentence names cattown beside ocm; the "`TableLeaderboard` arriving with Branch 7"
sentence goes. `CLAUDE.md` needs no change (`panels` is already on the `widgets/` line). Outcome
paragraphs here per WP with the per-file line table, the twelve-capture diff result and any
deviation.

One implementer per WP, one reviewer per diff (contract verbatim), fix rounds capped at 2 per WP,
full suite once on the branch head by the controller, then the owner's merge word.

**Branch 7 WP-A outcome (2026-09-20, commit `0feb671`).** `TableLeaderboard` exists and cattown is
its first subscriber; the three widened bases all carry the Branch 6 default as a class attribute,
so ocm reads exactly as it did and no pre-existing `test_panels.py` case changed meaning. All
twelve cattown and dota widgets are on the bases with every class name and every `update_data`
signature unchanged — `screens/cattown.py`, `screens/dota.py` and the panel-row agreement test in
`tests/screens/test_dashboard_screen.py` were not touched.

*Line counts are raw `wc -l`*, the convention this plan settled on in Branch 5 WP-B.

| file | before | after | file | before | after |
| --- | --- | --- | --- | --- | --- |
| `widgets/cattown/ct_hero_metrics.py` | 192 | 141 | `widgets/dota/dota_hero_metrics.py` | 165 | 145 |
| `widgets/cattown/ct_activity_feed.py` | 126 | 90 | `widgets/dota/dota_activity_feed.py` | 95 | 128 |
| `widgets/cattown/ct_best_plays.py` | 115 | 104 | `widgets/dota/dota_best_plays.py` | 98 | 93 |
| `widgets/cattown/ct_signals.py` | 97 | 58 | `widgets/dota/dota_signals.py` | 97 | 50 |
| `widgets/cattown/ct_leaderboard.py` | 94 | 83 | `widgets/dota/dota_leaderboard.py` | 70 | 69 |
| `widgets/cattown/ct_sparklines.py` | 88 | 38 | `widgets/dota/dota_sparklines.py` | 84 | 56 |
| `widgets/cattown/_fmt.py` (new) | 0 | 54 | | | |
| **`widgets/cattown/` total** | **712** | **568** | **`widgets/dota/` total** | **609** | **541** |
| `widgets/panels.py` | 509 | 726 | `themes/minimal.tcss` (10 blocks) | 46 | 0 |

**190 lines out of the two packages and 46 out of the stylesheet; 217 lines of shared base in.**
Net −19 production lines, and the slope is the point rather than the number: Branch 6 paid 252
lines to stand the bases up with one subscriber, WP-A paid −19 to add two more, and WP-B's two
packages plus Branch 8's `templates/` deletion are where HANDOVER §3.4's estimate is collected.
Three files grew and each says why in its docstring: `panels.py` by the whole
`TableLeaderboard`; `dota_activity_feed.py` by the docstring recording that an empty poll no
longer wipes a drawn roster (the base's merged feed contract — the manager serves `None` for a
failed read, so the old "clear and paint `No heroes yet`" was a false degradation); and
`dota_hero_metrics.py`'s and `dota_sparklines.py`'s comments explaining the two things that look
like dead code and are not (below).

**Rendering proof.** `render_case.py` on each dashboard's sweep payload under the real stylesheet
and a frozen clock, at 170×50 and at the 143 pin, against the pre-migration `b7_before_*` captures:

```
$ cmp b7_before_cattown.default.170x50.txt     b7_final_cattown.default.170x50.txt      -> identical
$ cmp b7_before_cattown.default.pin-143x50.txt b7_final_cattown.default.pin-143x50.txt  -> identical
$ cmp b7_before_dota.default.170x50.txt        b7_final_dota.default.170x50.txt         -> identical
$ cmp b7_before_dota.default.pin-143x50.txt    b7_final_dota.default.pin-143x50.txt     -> identical
```

**All four byte-identical**, which is the acceptance this branch was written to. Unlike Branch 6
there is no predicted one-row shift to explain: every spacer `Static` these twelve widgets yielded
traded one-for-one against `PanelBase`'s title margin, and both signals panels and both BEST PLAYS
boards keep their *interior* blank line, which was never the title's row. The five named behaviour
changes are all invisible to this payload and that was checked rather than assumed: the sparkline
histories are empty (so `fmt_compact` vs the old `_fmt_value` never runs), the feeds carry real
timestamps (so `hhmm` agrees with the copy it replaces), and every signal arrives `unavailable`
with no `[` in any `value_str` (so the new `safe_markup` escape is a no-op here). Each is pinned by
a unit test instead.

**Mutation proofs** (restored by inverse edit; `git status` clean after each):

| mutation | reddened |
| --- | --- |
| the per-row `try` deleted in `TableLeaderboard.render_table` | `test_panels.py::test_one_unaddable_row_is_skipped_and_the_others_land` — 1 failed, 95 passed. `ValueError: More values provided than there are columns` escapes after `clear()`, leaving the table empty, which on a leaderboard reads as "nobody is playing" |
| the `except NotImplementedError: raise` deleted from that same guard | `test_panels.py::test_a_subclass_without_build_row_fails_loudly` — 1 failed, 95 passed. A different test from the row above, which is the check that matters: the two halves of the guard are proven separately, so neither is riding on the other |
| `safe_markup` dropped from `fmt_signal`'s `value_str` | `test_panels.py::test_fmt_signal_escapes_a_hostile_value_str` and `::test_a_hostile_value_str_reaches_the_screen_as_text_not_markup` — 2 failed, 172 passed (run with `test_markup_safety.py`, which stayed green: it covers the helper, not this call site) |

**Tests.** `tests/widgets/test_panels.py` 74 → 96 cases: the `Text` branch of `render_box` (spans
and click `meta` checked cell by cell off the compositor, plus its degradation path), label-less
and separator signal rows and the seed-lands-on-the-first-*row* rule, the four `SparklinePanel`
knobs, and ten `TableLeaderboard` cases. Both agreement tests are now parametrised over one
`MIGRATED_PACKAGES` table — `{"ocm": 6, "cattown": 6, "dota": 6}`, package → the number of
`update_data` widget classes the walk must find (corrected in fix round 1, M3: it was a tuple with
a hard-coded `6`, and talismans and ttt export seven each, so WP-B would have had to edit a test
body after all). WP-B adds `"talismans": 7` and `"ttt": 7` — two entries, no test body. `tests/widgets/test_title_blank_row.py` 35 → 41 cases, gaining `CTLeaderboard`,
`CTActivityFeed`, `DOTALeaderboard` and `DOTAActivityFeed` — leaderboards and feeds were absent
from that table and their blank row came from the stylesheet alone, so nothing covered it.
Green on the branch head: **416** across the eleven named files, **6** on
`test_address_icons_everywhere.py -k "cattown or dota or ocm"`, **191** on `-m guard tests`
(88 s). No directory-wide or suite run; the suite is the controller's, once, on the branch head.

**Four deviations from the plan, each stated rather than taken silently.**

1. **The fifth agreement clause is not written as a source check.** The plan asks for "no `compose`
   yields a `Static` whose content is `""` or `" "`". As stated it is false of the tree it would
   guard: `OCMSupplyBreakdown` seeds three body lines empty and fills them on the first poll,
   `SignalsPanelBase` itself yields one before the recommendation, and both BEST PLAYS boards keep
   one between their headers and their rows — a blanket ban reddens on six of the sixteen migrated
   panels, and narrowing it to "the title's spacer" is exactly the distinction no source check can
   make. What made the old spacers wrong was the *row they painted*, so the claim is enforced where
   it is true and stronger: `test_title_blank_row.py` asserts title row, exactly one blank, then
   content, **composited**, for every panel in all three migrated packages. A leftover spacer
   reddens it with two blanks — and so does a spacer reached through a helper, or a regression in
   `PanelBase`'s `margin`, neither of which the source check would have seen. A comment at the
   agreement section records the reasoning so WP-B does not re-litigate it.
2. **dota's hero `token_price_usd` stays**, unused. The plan flags it for removal "if the screen
   does not pass it"; `screens/dota.py`'s `PANELS` row passes it, and
   `test_dashboard_screen.py::test_every_panel_row_names_a_mounted_widget_and_its_update_data_keywords`
   requires every key a row sends to be a **named** parameter of `update_data`. Removing it while
   keeping the screen untouched would have reddened that test; removing it from both would have
   been a `PANELS` edit this WP does not own. A comment on the parameter says so, and the pair is
   WP-B-or-later work at best — file it, do not fix it here.
3. **dota's value formatter keeps a module-level function**, `_fmt_frontline`, reached through the
   new `fmt_value` hook. The plan bans the name `_fmt_value` (the agreement test lists it) and
   offers `widgets/dota/_fmt.py` if two modules need it; only one does, so hoisting would have
   created a package module with a single caller. It is *not* `fmt_compact` in disguise and the
   docstring says why: a lane frontline is a position between two bases, so it has no K/M/B
   magnitudes, and `fmt_compact` would print `1.0K` where this panel shows `950` — every frontline
   the game serves is in the range where the two disagree.
4. **Two `DEFAULT_CSS` blocks survive per package**, on the leaderboards (`> DataTable { height:
   1fr }`) and the feeds (`> RichLog { height: 1fr; padding: 0 1; scrollbar-size: 1 1 }`). The plan
   deletes "every per-panel title/line CSS class and the `DEFAULT_CSS` that stated them"; these are
   geometry on the body widget, neither a title nor a line class, and this is the same call Branch
   6 made for `OCMActivityFeed` (its deviation 2). Hoisting them into the bases would change ocm
   and every future subscriber, which is not an append-only extension.

**Seen in passing, not fixed** (out of scope; for the follow-ups doc): `templates/
leaderboard_template.py` is now behind `TableLeaderboard` and should be deleted with the rest of
`templates/` in Branch 8, not fixed; and `CTBestPlays` / `DOTABestPlays` are the same two-column
board twice, differing only in their column widths and cell formatters — a sixth base worth
considering once WP-B shows whether talismans or ttt has a third.

**Branch 7 WP-A fix round 1 (2026-09-20).** Review verdict `Needs fixes: 1 Critical, 0 Important,
5 Minor`; all six addressed, plus one regression the fix round found in WP-A's own diff. The four
`cmp` captures are still byte-identical to `b7_before_*`, so nothing here moved a pixel.

**C1 (Critical) — a false premise in this plan, and the panel that rested on it.** Design change 4
above said "the manager serves `None` for a failed read". It did not: a failed game-state fetch
served `heroes=[]`, and `render_events` tests `if not events`, so under the migrated feed a failed
read kept the previous poll's HP and ALIVE/DEAD rows on screen — "a stale number presented as
live", on the one panel where every row is a number that expires. Fixed in three places, because
the defect needed all three:

- `data/dota_manager.py` serves `heroes = None` when `game_state is None` and `[]` when the read
  succeeded with no heroes. Nothing else derived from `heroes_raw` is touched.
- `widgets/panels.py` `RichLogFeed` gains `SNAPSHOT: bool = False`. Stream mode is the Branch 6
  contract byte for byte (ocm and cattown are untouched, and their tests pass unchanged); snapshot
  mode re-paints every poll, keeps no row, skips the dedupe guard, and tells `None`
  (`UNAVAILABLE_LINE`, new and derived from `UNAVAILABLE` as `LOADING_ROW` is from `LOADING`) from
  `[]` (`EMPTY_LINE`).
- `widgets/dota/dota_activity_feed.py` sets `SNAPSHOT = True` and its docstring now records the
  behaviour it has.

The plan's Design change 4 is corrected in place above with the file:line evidence. The status-bar
half of the reviewer's probe — `fetched_at` refreshed on a failed read, so the bar reads "updated
0s ago" — is pre-existing and **filed, not fixed**: follow-up #23, Tier 1.

**M1** the per-row skip in `render_table` logs at `warning` with the class and the row index, as
`PanelBase.write` does. **M2** `on_mount` checks `EMPTY_ROW` and `LOADING_ROW` against the column
count and raises `TypeError` naming the class — `add_row` raises on a surplus cell but pads a short
one in silence, and `EMPTY_ROW` is added on the degraded path, where nobody is looking. **M3** the
agreement table is now `MIGRATED_PACKAGES = {"ocm": 6, "cattown": 6, "dota": 6}`, a per-package
count, so WP-B adds two entries and no test body (talismans and ttt export seven each; the old
hard-coded `6` contradicted the docs' claim). **M4** the skip test is renamed
`…skips_and_the_index_is_the_slice_position` and the plan's Tests bullet 1 is corrected — the
behaviour was right and the plan's wording described its opposite. **M5** two unescaped
third-party interpolations closed: `ct_leaderboard.py`'s `rarity` (the colour is still looked up
on the raw value; only the displayed text is escaped) and the recommendation line, escaped once in
`SignalsPanelBase.render_recommendation` and once in cattown's own labelled line.

**Found in this round, in WP-A's own diff:** `test_panels_defines_the_two_strings_exactly_once` had
been **deleted** by commit `0feb671` — the source slice that removed a rejected spacer check
swallowed the function below it, and nothing reddened, because a deleted test is the one defect a
suite cannot report. Restored as `test_panels_defines_the_shared_strings_exactly_once`, widened to
`UNAVAILABLE_LINE` and to the current `__all__`. The three test names that left the file are now
accounted for one by one: two renamed to their migrated-package forms, this one restored.

```
$ cmp b7_before_dota.default.170x50.txt        b7_fix1_dota.default.170x50.txt         -> identical
$ cmp b7_before_dota.default.pin-143x50.txt    b7_fix1_dota.default.pin-143x50.txt     -> identical
$ cmp b7_before_cattown.default.170x50.txt     b7_fix1_cattown.default.170x50.txt      -> identical
$ cmp b7_before_cattown.default.pin-143x50.txt b7_fix1_cattown.default.pin-143x50.txt  -> identical
```

**Mutation proofs** (restored by inverse edit; `git status` clean after each):

| mutation | reddened |
| --- | --- |
| `SNAPSHOT = True` deleted from `DOTAActivityFeed` (back to stream mode) | `test_medi38_unavailable_state.py::test_a_failed_read_renders_unavailable_not_loading[DOTAActivityFeed]` **and** `::test_a_malformed_poll_after_a_good_one_is_not_shown_as_live[DOTAActivityFeed]` — 2 failed, 133 passed |
| `data/dota_manager.py` serving `[]` for a failed read again | `test_dota_manager.py::test_a_failed_game_state_read_serves_heroes_none` — 1 failed, 2 passed (the other two hold: the panel-side and manager-side halves are proven separately) |
| the `logger.warning` deleted from `render_table`'s per-row guard | `test_panels.py::test_a_skipped_row_is_logged_at_warning` — 1 failed, 105 passed |
| the two width checks deleted from `TableLeaderboard.on_mount` | `test_panels.py::test_a_wrong_width_empty_row_fails_at_mount` and `::test_a_wrong_width_loading_row_fails_at_mount` — 2 failed, 104 passed |
| `safe_markup` dropped from `render_recommendation` | `test_panels.py::test_a_hostile_recommendation_reaches_the_screen_as_text` — 1 failed, 105 passed (the log line shows the real failure mode: `closing tag '[/x]' does not match any open tag`, raised in the message pump) |

**Tests.** `test_panels.py` 96 → 106 cases, `test_medi38_unavailable_state.py` 26 → 29 (the roster
is the third shape where a read that never happened used to be shown as live), and a new
`tests/data/test_dota_manager.py` (3 cases; the manager's HTTP client is replaced with a double
whose every method raises, so nothing can reach the wire). Green: **432** across the twelve named
files, **6** on `test_address_icons_everywhere.py -k "cattown or dota or ocm"`, **191** on
`-m guard tests`.

**Branch 7 WP-A fix round 2 (2026-09-20, the last; applied by the controller).** Scoped re-review
verdict: C1, M1–M5 all ADDRESSED; three new findings.

- **N1 (Important).** In snapshot mode a poll whose rows *arrived* but none of which `format_row`
  could show painted `EMPTY_LINE` (`No heroes yet`) — a false negative, since the read returned a
  state. `render_events`'s `written == 0` write now picks `UNAVAILABLE_LINE` under `SNAPSHOT` and
  keeps `EMPTY_LINE` for a stream (Branch 6's answer, where nothing was ever drawn). One test,
  `test_a_snapshot_feed_with_no_showable_row_says_unavailable_not_empty`. Mutation: the branch
  reverted to `EMPTY_LINE` unconditionally → that test alone reddened (see the commit message).
- **N2 (Critical by consequence, pre-existing, outside the diff) — filed, not fixed.** The dota
  manager serves the other `game_state`-derived keys as sentinels on a failed read (`H: 0/0`,
  `TIED`, `Tick 0` on screen). Follow-up **#23** widened to cover it beside the `fetched_at`
  stamp; one Tier 1 item on dota's own data module.
- **N3 (Minor).** The `render_recommendation` docstring and two sentences in `rules/widgets.md`
  said an unescaped `[/x]` "raises out of the message pump where no panel's `try` can reach it".
  Probed on Textual 8.1.1 (`probe_static_update.py`, session scratchpad): `Static.update`
  raises `MarkupError` **synchronously** and the app stays alive, so a guarded write drops the
  line and an unguarded one kills the handler. All three sentences corrected — including the
  older "A widget that renders third-party text…" paragraph the branch had not written, because
  the same file was open and the claim is the one the new sentences copied. The convention itself
  (a `Static` gets a pre-built `Text`) is unchanged and still right.

Renders untouched by this round (no widget path the sweep payload reaches changed): not re-captured.

**Branch 7 WP-A re-review of fix round 2 (2026-09-20): N1 ADDRESSED, N3 ADDRESSED — Approved.** The
reviewer proved the two feed modes apart with a second mutation (the write forced to
`UNAVAILABLE_LINE` reddens only the stream test), re-captured all six renders (identical), and
probed all three markup paths on Textual 8.1.1: `DataTable.add_row` still raises later in `_on_idle`
and kills the app, `Static.update` raises at the call, `RichLog.write` parses nothing. Three docs
Minors closed in the same docs-only commit: **N4** the headline "Escape every third-party string"
paragraph in `rules/widgets.md` now names the path each timing belongs to instead of contradicting
the paragraph below it; **N5** a guarded `Static.update` that raises leaves the *previous* content on
screen (a stale line presented as live), not a blank — docstring and rules corrected; **N6** follow-up
#23's line references re-pointed at `841a0c7`. No code changed in this commit.

**Branch 7 WP-B outcome (2026-09-20).** talismans (7 widgets) and ttt (7 widgets) are on the
bases, which closes the migration: **five packages** — ocm, cattown, dota, talismans, ttt. Every
class name and every `update_data` signature is unchanged, so `screens/talismans.py`,
`screens/ttt.py` and the panel-row agreement test in `tests/screens/test_dashboard_screen.py` were
not touched. The hoists went in first, in the same commit and append-only:
`widgets/fmt.py` gained `fmt_int` (replacing six `_fmt_int`), `fmt_float` (two `_fmt_float`) and
`safe_get` (two `_safe_get`); `fmt.DASH` replaced eight `_DASH`; `fmt.hhmm` replaced the two
`_format_ts` / `_format_event_time`; `safe_symbol` was hoisted once into a new
`widgets/ttt/_fmt.py` (`ttt_leaderboard.py` and `ttt_fees_table.py` carried byte-identical
copies). The two `_fmt_eth` (fees 4 dp, claims 5 dp) stay behind their goldens in
`tests/widgets/test_ttt_address_icons.py`, and both `_SYM_WIDTH` measured pins are untouched.
`ttt_claims_table._fmt_multiplier` and `tal_hero_metrics._GENESIS` were dead and are gone
(`genesis_minted` stays a named `update_data` parameter — `screens/talismans.py`'s `PANELS` row
sends it, the same constraint as WP-A's deviation 2).

*Line counts are raw `wc -l`.*

| file | before | after | file | before | after |
| --- | --- | --- | --- | --- | --- |
| `widgets/talismans/tal_activity_feed.py` | 186 | 184 | `widgets/ttt/ttt_activity_feed.py` | 271 | 277 |
| `widgets/talismans/tal_hero_metrics.py` | 163 | 119 | `widgets/ttt/ttt_leaderboard.py` | 235 | 209 |
| `widgets/talismans/tal_leaderboard.py` | 119 | 92 | `widgets/ttt/ttt_fees_table.py` | 206 | 172 |
| `widgets/talismans/tal_signals.py` | 115 | 73 | `widgets/ttt/ttt_hero_metrics.py` | 179 | 144 |
| `widgets/talismans/tal_matrix_table.py` | 106 | 94 | `widgets/ttt/ttt_signals.py` | 141 | 122 |
| `widgets/talismans/tal_sparkline.py` | 106 | 77 | `widgets/ttt/ttt_claims_table.py` | 132 | 106 |
| `widgets/talismans/tal_materials_table.py` | 102 | 87 | `widgets/ttt/ttt_sparkline.py` | 125 | 100 |
| | | | `widgets/ttt/_fmt.py` (new) | 0 | 43 |
| **`widgets/talismans/` total** | **897** | **726** | **`widgets/ttt/` total** | **1289** | **1173** |
| `widgets/panels.py` | 826 | 888 | `widgets/fmt.py` | 204 | 264 |
| `themes/minimal.tcss` (5 blocks) | 42 | 0 | | | |

**287 lines out of the two packages and 42 out of the stylesheet; 122 lines of shared code in
(62 base + 60 `fmt.py`). Net −207 production lines**, against WP-A's −19 and Branch 6's +252 — the
slope the branch was written to predict. `ttt_activity_feed.py` is the one file that grew, by six
lines of docstring recording why it is a stream and not a snapshot (below).

**Rendering proof.** `render_case.py` on each dashboard's sweep payload under the real stylesheet
and a frozen clock, both views (default and `c`), at 170×50 and at the 143 pin:

```
$ cmp b7_before_talismans.default.170x50.txt      b7_wpb_talismans.default.170x50.txt      -> identical
$ cmp b7_before_talismans.default.pin-143x50.txt  b7_wpb_talismans.default.pin-143x50.txt  -> identical
$ cmp b7_before_talismans.view-c.170x50.txt       b7_wpb_talismans.view-c.170x50.txt       -> identical
$ cmp b7_before_talismans.view-c.pin-143x50.txt   b7_wpb_talismans.view-c.pin-143x50.txt   -> identical
$ cmp b7_before_ttt.default.170x50.txt            b7_wpb_ttt.default.170x50.txt            -> DIFFERS (3 lines)
$ cmp b7_before_ttt.default.pin-143x50.txt        b7_wpb_ttt.default.pin-143x50.txt        -> DIFFERS (3 lines)
$ cmp b7_before_ttt.view-c.170x50.txt             b7_wpb_ttt.view-c.170x50.txt             -> DIFFERS (3 lines)
$ cmp b7_before_ttt.view-c.pin-143x50.txt         b7_wpb_ttt.view-c.pin-143x50.txt         -> DIFFERS (3 lines)
$ cmp b7_before_cattown.default.170x50.txt        b7_wpb_cattown.default.170x50.txt        -> identical
$ cmp b7_before_cattown.default.pin-143x50.txt    b7_wpb_cattown.default.pin-143x50.txt    -> identical
$ cmp b7_before_dota.default.170x50.txt           b7_wpb_dota.default.170x50.txt           -> identical
$ cmp b7_before_dota.default.pin-143x50.txt       b7_wpb_dota.default.pin-143x50.txt       -> identical
$ cmp b6_fix2.170x50.txt                          b7_wpb_ocm.170x50.txt                    -> identical
$ cmp b6_fix2.pin-143x50.txt                      b7_wpb_ocm.pin-143x50.txt                -> identical
```

**Twelve of fourteen byte-identical**, and the two that are not are the same three rows four
times over — **the one deviation, reported rather than absorbed** (deviation 1 below). talismans
is clean in both views at both widths, and so are the three packages WP-A and Branch 6 migrated,
which is what the `fmt.py` hoists and the six new base attributes had to be checked against: a
shared helper that changed a cell would have shown up on ocm, cattown or dota first.

**Deviation 1 — three rows of the ttt signals panel move from `● --` to `● unavailable`, and no
live screen can reach it.** This is plan-named change 2, which the plan expected to be
unreachable on this payload; it is reachable, and the difference is the whole of it. The sweep
payload in `tests/address_sweep/` serves `buyback_signal`, `burn_velocity_signal` and
`holder_concentration_signal` as `None`. `TTTSignals`' own copy rendered a bare `● --` for a
`None` signal; `SignalsPanelBase.render_signal` renders `● unavailable`, which is the convention
("a dead source degrades to an explicit unavailable state", and `--` is reserved for a real
negative). Production never serves that shape: `data/ttt_manager.py` builds each of the three as
a dict with a `--` `value_str` on every path, failed reads included, so the base's degraded row is
unreachable live and the change is a correction to the *test payload's* rendering, not the
dashboard's. Reported as a deviation rather than papered over by keeping a per-panel `None`
branch, because the panel that lies about a dead read is the defect the convention exists for.
Verified as the *only* difference: `diff` on all four captures shows exactly those three rows.

**Deviation 2 — six new class attributes on the bases, each defaulting to Branch 6's behaviour.**
The plan's WP-B paragraph assumed the bases as WP-A left them would render these two packages
unchanged. Five places where they would not, closed by widening the base rather than by moving a
pixel — the same append-only move WP-A made, and ocm/cattown/dota prove it byte for byte above:

1. `SparklinePanel.MIN_POINTS` (default `1`): talismans and ttt refuse to draw a **single** sample,
   which `build_sparkline_from_points` renders as a flat baseline — a run of zeroes that never
   happened.
2. `SparklinePanel.EMPTY_KEEPS_LABEL` (default `False`): both keep the label column on the waiting
   line, because with two stacked series the reader has to know which one is not ready.
3. `SparklinePanel.compose_body` seeds **every** line with `EMPTY_TEXT` when one is set (Branch 6
   seeded `Loading...` on line 0 and `""` below). Both packages composed the waiting line on both
   rows; the `""` second row would have been a blank where a sentence was.
4. `RichLogFeed.WRAP` / `HIGHLIGHT` / `MAX_LINES` (defaults `True` / `True` / `None`): both feeds
   construct `RichLog(wrap=False, highlight=False, max_lines=200)`. Their rows are columnar and
   Rich's repr highlighter recolours numbers on top of the per-event-type colour.
5. `TableLeaderboard.render_table` paints `EMPTY_ROW` only when there are no rows **and** no
   `footer`. `TalismansMatrixTable` serves its bold TOTAL out of a different payload key than its
   rows, so `No data` above a real total would be a false negative.

**Deviation 3 — `widgets/ttt/_fmt.py` holds one function, and `ttt_activity_feed._sym` is not it.**
The plan says "`_safe_symbol` once in a new `widgets/ttt/_fmt.py`". Done: `ttt_leaderboard.py` and
`ttt_fees_table.py` had byte-identical copies and now import `safe_symbol` (public, so the
agreement test's banned-name walk — which inspects bound names, methods and aliases — does not
trip on it). `ttt_activity_feed._sym` looks like a third copy and is not: it dashes on empty
*after* `strip()` and right-pads nothing, and it is used in an f-string with `{sym:>6}`. Left
alone rather than forced into the hoist.

**Deviation 4 — `TalismansActivityFeed` and `TTTActivityFeed` are streams, `SNAPSHOT = False`.**
Per `rules/widgets.md`'s definition: a row is one thing that *happened* at a stated time — a bond,
a cleave, a burn, a fee deposit — and it is still true when the next poll brings nothing. Nothing
in a row expires, so there is no number to present as live. dota's hero roster is the snapshot
shape (every row carries an HP true only of its own poll), and marking these feeds snapshots would
mean re-painting whole every poll and telling `[]` from `None`, a distinction an event log does
not have. Both `dedupe_key` return `None` — these events carry no key the panel trusts to be
unique — so every poll is all-new and redraws, which is what the unconditional `clear()` they
replace did. Recorded in both module docstrings.

Stream mode has **two consequences the first write of this paragraph named neither of**, added in
fix round 1 (M5). (a) An **empty poll after a drawn feed leaves the rows on screen**; the copies
cleared and wrote `No activity yet`. (b) A **non-empty poll whose every row fails to format writes
`No activity yet`** (`written == 0` with nothing ever drawn); the copies left the log blank. Both
are the base's merged contract and both are right here, because — and this is the check that
matters, since it is exactly the shape of WP-A's C1 — **neither manager can serve `None` or a
failure-shaped `[]` for this key**: `data/talismans_manager.py:238-240` and
`data/ttt_manager.py:355-358` both build `activity_events` from
`cache.get_activity_for_display(25)`, which sorts the persisted `activity_log` and slices it
(`talismans_cache.py:178-189`, `ttt_cache.py:493-...`). It never reads the wire, so `[]` means
"nothing has accumulated", never "this poll failed", and there is no state in which leaving the
rows shows a number that has expired. dota's roster was the opposite: every row carried an HP true
only of its own poll, and its manager *did* serve `[]` for a failed read.

**Deviation 5 — the three `DEFAULT_CSS` geometry blocks survive**, on the tables (`> DataTable {
height: 1fr }`) and the feeds (`> RichLog { height: 1fr; padding: 0 1; scrollbar-size: 1 1 }`),
same call as WP-A's deviation 4. Deleted from `themes/minimal.tcss`: `TTTLeaderboard >
.leaderboard-title`, `TTTActivityFeed > .feed-title`, `TTTFeesTable > .fees-title, TTTClaimsTable >
.claims-title`, `TTTSparkline > .ttt-spark-title` and `TTTSignals > .ttt-signals-title` — 42 lines,
every one a title class the base now owns. talismans had no title block to delete.

**Deviation 6 — `TalismansSignals` shows `Loading...` before its first poll, where the copy
showed a blank row.** Added in fix round 1 (M3): a rendering change in a state none of the
fourteen captures can see, because `render_case.py` polls before it composites.
`SignalsPanelBase.compose_body` seeds `LOADING_ROW` on the **first row** (never on a separator);
the old `tal_signals.compose` seeded every row with `""`. This is the base's documented contract
and the right answer — a panel that has never polled should say so rather than read as four
signals that are all empty — but it is a change, so it is listed. ttt is unaffected in practice:
its first row is the optional fresh-launch row, which `TTTSignals.compose_body` hides with
`display = False`, so the seed lands on a collapsed row and the pre-poll panel is blank exactly as
before.

**Mutation proofs** (restored by inverse edit; `git status` clean after each):

| mutation | reddened |
| --- | --- |
| `TalismansSparkline.fmt_value` reverted to `super().fmt_value` (i.e. `fmt_compact`) | `test_talismans_widgets.py::test_the_sparkline_value_cell_is_a_grouped_integer_not_a_compact_one` **and** `::test_a_series_too_short_to_draw_keeps_its_label` — 2 failed, 191 passed |
| `TalismansSparkline.SHOW_ARROW = True` | `test_talismans_widgets.py::test_the_sparkline_draws_no_trend_arrow` **and** the value-cell test (the arrow displaces the cell) — 2 failed, 191 passed |
| `TalismansLeaderboard.EMPTY_ROW`'s `"No data"` moved from the wallet cell to the rank cell | `test_talismans_widgets.py::test_the_empty_leaderboard_says_no_data_under_the_wallet_column` — 1 failed, 192 passed |
| `HeroRow.render_box`'s build-failure fallback changed from `UNAVAILABLE` to `[dim]--[/]` | `test_medi38_unavailable_state.py::test_a_malformed_poll_after_a_good_one_is_not_shown_as_live[CTHeroMetrics]` **and** both new hero-row cases — 3 failed, 35 passed |

**The first mutation is why four tests exist that the plan did not ask for.** Run against the tree
as first migrated, `fmt_value` → `fmt_compact` reddened **nothing**: the whole named set stayed
green at 61 passed. `tests/widgets/test_talismans_widgets.py` was a smoke suite — drive
`update_data` three ways, assert a row count — so it could not see a cell's spelling, an arrow, a
waiting line or a degraded row's column. Four composited pins were added (`render_strips()`, the
repo rule), each naming the mutation it exists to redden, and the mutation then reddened two of
them. A mutation that reddens nothing is a test that cannot fail.

**Tests.** `tests/widgets/test_panels.py` 107 → 128 (`MIGRATED_PACKAGES` gains `"talismans": 7`
and `"ttt": 7` — two table entries, no test body, exactly as WP-A's M3 arranged);
`test_title_blank_row.py` 41 → 51, gaining all six talismans panels that are now `PanelBase`
subclasses and four ttt ones; `test_medi38_unavailable_state.py` 29 → 38, gaining `TTTSignals` in
the widget table and a new hero-row table (`TalismansHeroMetrics`, `TTTHeroMetrics`) driven by a
`_Hostile` value whose `__int__` / `__float__` / `__str__` / `__format__` all raise — the shape
that proves named change 2 (a build that *raises* lands on `unavailable`; a `None` the manager
served deliberately still renders `--`, and there is a test for each direction);
`test_fmt.py` 25 → 59 for the three new helpers — and its `__all__` agreement case reddens under
the hoist if it is not updated with them, which is the cheapest proof that the hoist is visible to
a test at all; `test_talismans_widgets.py` 7 → 11 as above.
**543 passed** across the seventeen named files (499 at `e9a6307`), **10 passed, 33 deselected**
on `test_address_icons_everywhere.py -k "talismans or ttt or cattown or dota or ocm"`, **191** on
`-m guard tests`. No directory-wide or suite run; the suite is the controller's, once, on the
branch head.

**Every test file's function-name list was diffed against `e9a6307`** — WP-A's first commit
silently deleted a test through a careless source slice, and a deleted test is the one defect a
suite cannot report. Additions only: `test_fmt.py` +6, `test_medi38_unavailable_state.py` +3,
`test_talismans_widgets.py` +4; `test_panels.py` and `test_title_blank_row.py` unchanged (both
grew by table rows, not functions). **No test disappeared, and none was renamed.**

**Seen in passing, not fixed** (out of scope; for the follow-ups doc):
`tests/widgets/test_title_blank_row.py`'s pre-existing `TTTSparkline` row passes
`{"burn_history": _SERIES}` — the parameter is `burns_history`, so the payload is swallowed by
`**_kwargs` and that case has only ever exercised the waiting state, never a drawn sparkline. It
is green either way and the fix is a one-word rename plus whatever the drawn state then asserts:
Minor, Tier 0 when the file is next touched. Also: `TTTFeesTable` and `TTTClaimsTable` keep one
`_fmt_eth` each, at 4 and 5 decimal places, pinned by goldens — a single `fmt_eth(value, dp)` in
`widgets/fmt.py` would retire both, but the goldens are outside this WP's diff.

**Branch 7 WP-B fix round 1 (2026-09-20).** Review verdict `Needs fixes: 0 Critical, 1 Important,
5 Minor`; all six addressed. **Tests and docs only — no production file changed**, and the eight
talismans/ttt captures are byte-identical to the WP-B ones:

```
$ cmp b7_wpb_talismans.default.170x50.txt      b7_wpb_fix1_talismans.default.170x50.txt      -> identical
$ cmp b7_wpb_talismans.default.pin-143x50.txt  b7_wpb_fix1_talismans.default.pin-143x50.txt  -> identical
$ cmp b7_wpb_talismans.view-c.170x50.txt       b7_wpb_fix1_talismans.view-c.170x50.txt       -> identical
$ cmp b7_wpb_talismans.view-c.pin-143x50.txt   b7_wpb_fix1_talismans.view-c.pin-143x50.txt   -> identical
$ cmp b7_wpb_ttt.default.170x50.txt            b7_wpb_fix1_ttt.default.170x50.txt            -> identical
$ cmp b7_wpb_ttt.default.pin-143x50.txt        b7_wpb_fix1_ttt.default.pin-143x50.txt        -> identical
$ cmp b7_wpb_ttt.view-c.170x50.txt             b7_wpb_fix1_ttt.view-c.170x50.txt             -> identical
$ cmp b7_wpb_ttt.view-c.pin-143x50.txt         b7_wpb_fix1_ttt.view-c.pin-143x50.txt         -> identical
```

**I1 (Important) — ttt's fresh-launch `display` toggle had no test, and the migration is what
made it load-bearing.** Before WP-B the fresh row was seeded `""`, so losing the toggle cost a
blank row. After it, `render_signal` writes `  [yellow]●[/] unavailable` into that row *before*
the toggle hides it, so a lost toggle gives every live ttt SIGNALS panel with no fresh launch a
permanent `● unavailable` row and shifts the three real rows down one. The reviewer mutated it to
`fresh.display = True` and the whole named set (240) plus the ttt sweep cases stayed green.
New module `tests/widgets/test_ttt_widgets.py`, in the shape of `test_talismans_widgets.py`'s
composited pins (`render_strips()`, `_PIN_SIZE = (120, 24)`), pins **both directions**: with
`fresh_launch_signal=None` the panel is buybacks / decay / separator / concentration and the word
`unavailable` appears nowhere; with a real fresh dict the row is visible at row index 3 (title,
blank — `PanelBase`'s margin, which no payload can cancel — then fresh). Two tests rather than
one, because the toggle can fail in both directions and a single test would leave `display = False`
unproven.

**M1 — five `TTTSparkline` constants were unpinned.** `LABEL_WIDTH = 12` mutated to `8` left
everything green, as did `SHOW_ARROW`, `MIN_POINTS`, `EMPTY_KEEPS_LABEL` and the `$` `fmt_value`
override. Four more pins in the same new module. The label-width one asserts the padding
(`BURNS` padded to twelve cells), not only that the two bars start in the same column: at `8` both
labels still align — the longer one simply truncates to `24H VOLU` — so the same-column assertion
alone would not have bitten.

**M2 — `TalismansSignals`' `None` separator was unpinned.** Deleting it left 299 named cases plus
the sweep plus the guard tests green while the panel lost a row of structure. One composited pin
in `test_talismans_widgets.py`: FORGE MOMENTUM sits two rows below CUT/MERGE with a blank between,
and SCARCITY follows FORGE with no gap — one separator, not two.

**M3 — a sixth deviation, recorded above.** `SignalsPanelBase.compose_body` seeds `LOADING_ROW` on
the first row, so `TalismansSignals` shows `Loading...` before its first poll where the copy showed
a blank. Correct and the base's contract, but invisible to the fourteen captures (which poll before
they composite), so it is now deviation 6 with the ttt case (seed lands on the collapsed
fresh-launch row, so ttt is unchanged) stated beside it.

**M4 — filed, not fixed: follow-up #24.** `fmt_signal` reads `sig.get("value_str", "")` /
`.get("color", "dim")` / `.get("indicator", "●")`, where the eight copies used `or`-defaults, so a
dict carrying `value_str=""` renders an empty cell (copies: `--`) and `color=""`/`None` would emit
`[]`/`[None]`. Unreachable today — `data/talismans_models.py:84-92` and `data/ttt_models.py:127-135`
declare all four as required `str`, computed per poll and never read back from a cache file — and
pre-existing base behaviour since Branch 6. Minor, Tier 0 when `panels.py` is next touched.

**M5 — deviation 4 widened**, above: stream mode's two consequences and the check that the dota
C1 shape cannot recur here.

**Mutation proofs** (restored by inverse edit; `git status` clean after each; counts over the two
widget modules, 18 cases):

| mutation | reddened |
| --- | --- |
| `TTTSignals` `fresh.display = True` | `test_ttt_widgets.py::test_no_fresh_launch_hides_the_row_entirely` — 1 failed, 17 passed. This is the reviewer's own mutation, which previously reddened nothing |
| `TTTSignals` `fresh.display = False` | `::test_a_fresh_launch_shows_the_row_at_the_top_of_the_panel` — 1 failed, 17 passed. The other direction, and a *different* test: neither half rides on the other |
| `TTTSparkline.LABEL_WIDTH` 12 → 8 | `::test_both_sparkline_labels_are_padded_to_the_same_twelve_cells` plus three more that read the truncated label — 4 failed, 14 passed |
| `TTTSparkline.SHOW_ARROW = True` | `::test_the_sparkline_draws_no_trend_arrow` and the volume-cell test (the arrow displaces the cell) — 2 failed, 16 passed |
| `TTTSparkline.fmt_value` → `super()` (`fmt_compact`) | `::test_the_volume_cell_is_dollars_at_two_decimals_not_a_compact_count` and `::test_a_series_too_short_to_draw_keeps_its_label` — 2 failed, 16 passed |
| `TTTSparkline.MIN_POINTS` 2 → 1 | `::test_a_series_too_short_to_draw_keeps_its_label` — 1 failed, 17 passed |
| `TTTSparkline.EMPTY_KEEPS_LABEL = False` | `::test_a_series_too_short_to_draw_keeps_its_label` — 1 failed, 17 passed |
| the bare `None` separator deleted from `TalismansSignals.ROWS` | `test_talismans_widgets.py::test_the_signals_separator_keeps_forge_momentum_off_the_cutmerge_group` — 1 failed, 17 passed |

**Tests.** New `tests/widgets/test_ttt_widgets.py` (6 cases); `test_talismans_widgets.py` 11 → 12.
Green: **550** across the eighteen named files (543 at `ef3a16e`, +7), **4 passed / 39 deselected**
on `test_address_icons_everywhere.py -k "talismans or ttt"`, **191** on `-m guard tests`. Every
edited test file's function-name list diffed against `ef3a16e`: additions only, no deletions.

**Branch 7 WP-B re-review of fix round 1 (2026-09-20): Approved.** All six findings ADDRESSED;
every row of the mutation table above reproduced by the reviewer against the named file, and the
controller independently re-ran the I1 always-show mutation (`True or bool(` at
`ttt_signals.py:107` — the toggle spans three lines, so a one-line substitution silently misses it
and reports green) with exactly `test_no_fresh_launch_hides_the_row_entirely` failing. M3's
deviation 6 re-confirmed by composition; M4's and M5's line references checked. 537 passed over
the sixteen named files, 191 guard. Two new Minors, both filed and closed here as docs rather than
a second fix round: **N1** — the label-width test only bites on truncation; `LABEL_WIDTH` 12 → 13
and 12 → 14 leave 18 passed, and at 12 → 8 the test dies on the truncated label lookup before the
padding assertion it is credited with, so the M1 paragraph above claims more than the test can
deliver (follow-up #25). **N2** — follow-up #24's colour rationale was wrong in both colour
claims: probed on a mounted `TalismansSignals`, `color=""` degrades through `write_guarded` to a
visible `● unavailable` (not a dropped line), and `color=None` renders normally because Textual's
`Content.from_markup` accepts `[None]` as the null style; only `value_str=""` stands. #24 corrected
in place (the reviewer's own M4 wording had speculated the same, unprobed). Seen in passing while
closing N2: two `panels.py` docstrings still claim the deferred message-pump raise that WP-A's
probe refuted — follow-up #26, docstring-only. **WP-B closed: 2ef29dc is the branch head under
review; the docs closure commit that follows changes no code and no test.**

## Branch 8 — `refactor/panels-bt-bakery` (two work packages)

HANDOVER §3.4, third and last slice (§3.4c): the six `BT*` overview widgets and the six
Bakery-only top-level widgets onto the `widgets/panels.py` bases, then `templates/` deleted and
every reference to it retired. Cut from main `d2401ba`. Facts read off the tree on 2026-09-20
(survey in the session, every `update_data` and every `DEFAULT_CSS` read):

- **Twelve widget modules, 1,552 lines.** `widgets/base/overview/` 6 (720: `bt_hero_metrics`
  128, `bt_overview_leaderboard` 142, `bt_sparklines` 118, `bt_signals` 93, `bt_activity_feed`
  127, `bt_best_plays` 112) and the bakery six at the top of `widgets/` (832: `hero_metrics` 187,
  `leaderboard` 87, `cookie_chart` 115, `signals_panel` 118, `activity_feed` 214, `ev_table`
  111). HANDOVER names four bakery widgets; `cookie_chart` (a sparkline panel) and `ev_table` (a
  two-column board) are the other two bakery panels, both of the same lineage and both already
  rows in `test_title_blank_row.py`, so this branch takes all six and bakery ends fully on the
  bases like the five small dashboards.
- **Shapes, two of each.** Hero rows: `BTOverviewHero` (4 boxes) and `HeroMetrics` (3), both a
  `Horizontal` of `Static` boxes seeded `Loading...`; `HeroMetrics` carries its own MEDI-38
  `_UNAVAILABLE` and per-box `try`, which is exactly `HeroRow.render_box`. Leaderboards:
  `BTOverviewLeaderboard` (6 columns, cap 15) and `Leaderboard` (5 columns, cap 10), both
  `clear()` → `"No data"` in the second cell when empty, rank-1 bold — `TableLeaderboard` with
  `build_row`. Sparklines: `BTSparklines` (three fixed labelled series, `label:<10`, arrow,
  `waiting for data...` on an empty series) and `CookieChart` (up to three series **named per
  poll** by the top bakeries, `name[:8].ljust(8)` escaped, blank line for a missing third).
  Signals: `BTSignals` and `SignalsPanel` share a row shape **older than `fmt_signal`'s** —
  `  [dim]{label:<20}[/][bold white]{value:>12}[/]  [{color}]● {indicator:<10}[/]`, the
  indicator *trailing* the value — plus a `→ Recommendation:` line that BT blanks when empty and
  bakery always writes. Neither takes signal dicts: BT classifies plain strings
  (`_signal_indicator`, `None` → dim `...`), bakery derives value/colour/indicator from two dicts
  and a float. Feeds: `BTActivityFeed` (`_has_data` flag, markup strings, whale trades) and
  `ActivityFeed` (`_seen_keys` dedupe, `rich.text.Text` rows through `address_text`, a
  `_MALFORMED_LINE` for an event that fails to format) — the contract `RichLogFeed` already merged
  (`panels.py:612`), stream mode both. Two-column boards: `BTBestPlays` and `EVTable`, the sixth
  and fifth copies of one shape repo-wide (`ct_best_plays`, `dota_best_plays`, `fp_best_plays`,
  `fpw_best_plays` are the others) — no base exists; filed as follow-up #27, here `PanelBase` with
  their own `compose_body`, as `OCMSupplyBreakdown` was.
- **The bare stylesheet blocks stay.** `HeroBox`, `SignalsPanel` and `BTHeroBox` have bare
  geometry blocks in `minimal.tcss`; they are the reason the bases carry `Base` suffixes
  (`test_panels.py`'s two guard tests). Ten *title* blocks go: `Leaderboard > Static`,
  `CookieChart > .chart-title`, `SignalsPanel > .signals-title`, `ActivityFeed > .feed-title`,
  `EVTable > .ev-title`, `BTOverviewLeaderboard > .bto-lb-title`, `BTSparklines > .bto-chart-title`,
  `BTSignals > .bto-sig-title`, `BTActivityFeed > .bto-feed-title`, `BTBestPlays > .bto-bp-title`.
  Four of the ten carry `margin: 0 0 1 0` (the base's margin); the other six panels paint the
  blank row with a spacer `Static`, which the migration deletes.
- **`leaderboard.py` and `activity_feed.py` import `data.models`** (`BakerySummary`,
  `ActivityEvent`), against the widgets-never-import-`data/` convention; pre-existing and named in
  `rules/widgets.md` step 1. Both are annotation-only unless the implementer finds otherwise.
- **Tests.** Bakery has 21 widget tests that are this branch's acceptance and must not change:
  `test_activity_feed_degradation.py` (11), `test_hero_metrics_degradation.py` (6),
  `test_ev_table_catalog_source.py` (4). BT has `test_base_address_icons.py` (2) and
  `tests/screens/test_base_terminal_screen.py` (3) and **no composited widget test**. Six test
  files reference `templates/`: `tests/screens/test_refresh_guard.py` (`TEMPLATE` in the
  bare-worker scan; `test_template_screen_inherits_the_guard`), `tests/widgets/test_markup_safety.py`
  (`GameLeaderboard`, two tests), `test_sparkline_common.py` (`GameSparklines` in
  `SPARKLINE_WIDGETS`; `test_template_seeds_an_import_not_a_copy`),
  `test_hidden_shared_address_icons.py` (`test_each_template_uses_the_helper_and_defines_no_formatter`),
  `test_panels.py` (`"maxpane_dashboard.templates"` in the clash scan), `test_title_blank_row.py`
  (docstring only).
- **`templates/`** is nine files, 1,080 lines. Outside tests it is named in `CLAUDE.md` five
  times (Architecture tree, Known hazards, and the three tier-trigger lists), in
  `rules/widgets.md` (frontmatter path, title, :143, :159, :303, step 3) and in docstrings:
  `screens/refresh_guard.py:16`, `widgets/sparkline_common.py:11-20`, `widgets/panels.py:8, 271,
  411, 612`, `widgets/surf/pool4u_signals.py:3`. `pyproject.toml` does not list it.
- **Renders.** The sweep registry has cases `base` and `bakery` (default view only; neither
  screen has a second view). `render_case.py base b8_before_base` and `… bakery b8_before_bakery`
  are taken at 170×50 and the 143 pin, from the scratchpad as cwd (the script writes relative to
  cwd).

### Design

The five bases plus `TableLeaderboard`, as Branches 6 and 7 used them, with **two append-only
extensions to `panels.py`, both landing in WP-A**:

1. **`fmt_signal_trailing(label, value, *, indicator="", color="dim", label_width=20,
   value_width=12, indicator_width=10) -> str`** — the older row shape both signals panels share,
   label first, value right-aligned, dot and indicator trailing; `value` and `indicator` escaped
   with `safe_markup` (they are analytics output over game-API names; escaping strings that never
   carried a bracket moves no pixel). Without the indicator the row ends after the value, as
   `SignalsPanel._fmt_row` does. `fmt_signal` is untouched; the two are documented side by side as
   the two row shapes in the tree. A helper two packages need is hoisted once, never re-declared.
2. **Per-poll line labels on `SparklinePanel`**, only if the base cannot already express
   `CookieChart` — an append-only hook with a default that reproduces today's behaviour for every
   existing subscriber. If the hook would be a second behaviour decision rather than an extension,
   `CookieChart` goes on `PanelBase` with `compose_body` and the `sparkline_common` helpers instead,
   and the outcome paragraph says which and why.

Both signals panels subclass `SignalsPanelBase` for `ROWS` (ids and labels, a bare `None` where
`sig-spacer-2` / `bto-sig-spacer-2` stood), the first-row `LOADING_ROW` seed, `RECOMMENDATION_ID`
and `write_guarded`, and override `update_data` to build their three rows with
`fmt_signal_trailing` from their own classifiers — the classifiers stay where they are. The
recommendation line goes through `render_recommendation` only if its output is byte-identical to
the copies' `  [dim]→ Recommendation:[/] [bold]…[/]`; otherwise `write_guarded` with that exact
string. BT keeps blank-on-empty, bakery keeps always-write.

`HeroMetrics(HeroRow)` keeps its three box renderers behind `render_box`; its own `_UNAVAILABLE`
and `_num` go (the base's `UNAVAILABLE` and `fmt.py`). `BTOverviewHero(HeroRow)` keeps `No data`
for a `None` gainer — that is the copy's own text for a real negative, not a build failure.
`Leaderboard` and `BTOverviewLeaderboard` on `TableLeaderboard` with `COLUMNS`, `ROW_CAP` (10 /
15) and an `EMPTY_ROW` that puts `No data` in the second cell exactly as today; the `data.models`
import moves under `TYPE_CHECKING` if annotation-only (the file already has `from __future__
import annotations`), else stays and is filed. `ActivityFeed(RichLogFeed)` maps `_seen_keys` onto
`dedupe_key` and its `_MALFORMED_LINE` onto a `format_row` that returns that `Text` for a bad
event — the eleven degradation tests are the proof. `BTActivityFeed(RichLogFeed)` in stream mode
(`_has_data` is the base's `_drawn`). `EVTable(PanelBase)` and `BTBestPlays(PanelBase)` keep their
row `Static`s under `compose_body`; only the title and its margin move to the base.

**Expected render diff: none.** Both captures are expected byte-identical after each WP; every
difference is either fixed or named in the outcome paragraph with the reason it is right. Two
states the captures cannot see are stated up front: pre-poll (`Loading...` seeds land on the first
signal row, sparkline line 0, board row 0 and every hero box — the same places as today, so no
change is expected, but it is uncaptured) and the failed read (each WP names, with file:line,
whether its manager can serve `None` or `[]` for a failed read on each feed and table key — the
dota C1 shape — and what the migrated panel shows for it).

### WP-A — base terminal

`widgets/base/overview/*.py` (6), `widgets/base/overview/__init__.py` unchanged in its exports,
`widgets/panels.py` (+`fmt_signal_trailing`, +the sparkline hook if chosen, with `test_panels.py`
cases for each — the trailing shape with and without an indicator, escaping, widths), five
`BT* > .bto-*-title` blocks out of `minimal.tcss`. Tests: `test_panels.py` (`MIGRATED_PACKAGES`
gains `"base.overview": 6` — `_package` takes a dotted name), `test_title_blank_row.py` (rows for
`BTOverviewLeaderboard` and `BTActivityFeed` beside the three BT rows it has), and a **new
`tests/widgets/test_base_widgets.py`** of composited pins (`render_strips()`) for every constant
the migration introduces: the six column widths and `ROW_CAP = 15`, `EMPTY_ROW`'s cell position,
`LABEL_WIDTH = 10`, `SHOW_ARROW`, the `waiting for data...` line, the trailing-indicator row
order, the recommendation blank on empty, the feed placeholder once and rows kept on an empty
poll. Each pin names the mutation it exists to redden; the outcome paragraph carries the mutation
table (mutation → the test that failed, by name). Named set: the three edited/new widget test
files, `test_base_address_icons.py`, `tests/screens/test_base_terminal_screen.py`,
`test_address_icons_everywhere.py -k base`, `test_medi38_unavailable_state.py`,
`tests/screens/test_refresh_guard.py`, `tests/screens/test_dashboard_screen.py`,
`tests/test_address_rule.py`, `-m guard tests`. Renders: `b8_wpa_base.*` `cmp` `b8_before_base.*`.

### WP-B — bakery, templates, docs

The bakery six (`widgets/__init__.py` re-exports unchanged), five bakery title blocks out of
`minimal.tcss`, **`templates/` deleted whole** (nine files), and every reference retired:

- Tests: `test_refresh_guard.py` — `TEMPLATE` leaves the bare-worker scan and
  `test_template_screen_inherits_the_guard` is deleted (its property is structural now: a new
  screen subclasses `DashboardScreen`, which `test_refresh_guard.py` already collects by
  `issubclass`); `test_markup_safety.py` — the two `GameLeaderboard` tests are re-targeted to a
  minimal `TableLeaderboard` subclass defined in the test file, so the hostile-entries property
  keeps a subject (or deleted if `test_panels.py` already proves it for `TableLeaderboard` — say
  which, with the test name); `test_sparkline_common.py` — `GameSparklines` leaves
  `SPARKLINE_WIDGETS`, `test_template_seeds_an_import_not_a_copy` is deleted, module docstring
  reworded; `test_hidden_shared_address_icons.py` — the template parametrized test deleted,
  docstring reworded; `test_panels.py` — `"maxpane_dashboard.templates"` leaves the clash scan and
  the bakery six join the banned-name / migrated scans by an explicit module list (bakery is not a
  package; the table gains a `"bakery"` entry whose modules are listed, not globbed);
  `test_title_blank_row.py` — docstring, plus rows for `Leaderboard` and `ActivityFeed`. A **new
  `tests/widgets/test_bakery_widgets.py`** of composited pins on the same terms as WP-A's. **The 21
  existing bakery tests do not change**: `git diff --stat` against the branch base shows no edit to
  `test_activity_feed_degradation.py`, `test_hero_metrics_degradation.py` or
  `test_ev_table_catalog_source.py`.
- Docs: `rules/widgets.md` — the `templates/**` frontmatter path goes, the title loses
  "templates", :143 and :159 say "copy any migrated screen; `screens/ocm.py` is the smallest",
  :303 drops "or `templates/`", and step 3 is rewritten: reuse ends at the bases and the siblings,
  `templates/` was deleted in Branch 8 and the sentence about a template drifting ahead of its
  copies becomes the one-line history of why the bases exist. `CLAUDE.md` — the `templates/` line
  leaves the Architecture tree, the Known-hazards bullet is deleted, and `templates/` is dropped
  from the three tier-trigger lists (a trigger on a directory that no longer exists is misleading,
  not harmless). Docstrings naming a template (`screens/refresh_guard.py:16`,
  `widgets/sparkline_common.py:11-20`, `widgets/panels.py:8, 271, 411, 612`,
  `widgets/surf/pool4u_signals.py:3`) are reworded to the past tense — comment-only edits in
  shared modules, no code line touched.

Named set: the 21 bakery tests, the six edited test files, the new module,
`test_address_icons_everywhere.py -k bakery`, `tests/test_app_startup.py`,
`tests/screens/test_refresh_guard.py`, every file `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/'
tests/` names, `-m guard tests`. Renders: `b8_wpb_bakery.*` `cmp` `b8_before_bakery.*`, and
`b8_wpb_base.*` `cmp` `b8_wpa_base.*` (the docstring edits in `panels.py` must move nothing).

### Tests

- Every new constant is pinned by a composited test that names its mutation, and the outcome
  paragraph proves each with "mutation → test that reddened". A mutation that reddens nothing is a
  test that cannot fail (Branch 7 WP-B found one; the rule stands).
- Test-name lists of every edited test file are diffed against the branch base before each commit
  and the diff is stated (deletions in WP-B are the four template tests named above and nothing
  else).
- One implementer per WP, sequential, single writer to the tree; one opus reviewer per diff with
  the CLAUDE.md contract verbatim; fix rounds capped at 2 with a scoped re-review; full suite once
  on the branch head by the controller; the owner's untracked files never touched.

### Docs

`rules/widgets.md` as above, plus the Panels section's `MIGRATED_PACKAGES` table gaining
`base.overview` and `bakery` and a line on `fmt_signal_trailing`. `CLAUDE.md` as above. Outcome
paragraphs here per WP with the per-file line table, the render-diff result, the mutation table
and any deviation. Follow-up #27 (a sixth base for the six two-column boards) filed with this
section.

**Branch 8 WP-A outcome (2026-09-20).** The six `widgets/base/overview/bt_*.py` widgets are on
the bases: `BTOverviewHero(HeroRow)` with `BTHeroBox(HeroBoxBase)`,
`BTOverviewLeaderboard(TableLeaderboard)`, `BTSparklines(SparklinePanel)`,
`BTSignals(SignalsPanelBase)`, `BTActivityFeed(RichLogFeed)` and `BTBestPlays(PanelBase)`.
Every class name and every `update_data` signature is unchanged, `__init__.py` is untouched, so
`screens/base_terminal.py`'s `PANELS` and the panel-row agreement test were not touched. Every
spacer `Static`, every per-panel title class and every `DEFAULT_CSS` title block is gone from the
package; the two **geometry** blocks stay (`BTOverviewLeaderboard > DataTable { height: 1fr }`,
`BTActivityFeed > RichLog { height: 1fr; padding: 0 1; scrollbar-size: 1 1 }`), the Branch 6 /
Branch 7 precedent. `themes/minimal.tcss` lost the five `BT* > .bto-*-title` blocks and nothing
else (`grep -c 'bto-'` 5 → 0; the nine `BT*` geometry/colour blocks remain). `panels.py` grew
append-only: `fmt_signal_trailing` (in `__all__`), `SparklinePanel.SPARK_WIDTH` (default
`sparkline_common.SPARK_WIDTH`, 22) and `RichLogFeed.HEADER_LINE` (default `None`), each
defaulting to the pre-WP-A behaviour and each proven below.

*Line counts are raw `wc -l`.*

| file | before | after |
| --- | --- | --- |
| `widgets/base/overview/bt_hero_metrics.py` | 128 | 113 |
| `widgets/base/overview/bt_overview_leaderboard.py` | 142 | 148 |
| `widgets/base/overview/bt_sparklines.py` | 118 | 83 |
| `widgets/base/overview/bt_signals.py` | 93 | 79 |
| `widgets/base/overview/bt_activity_feed.py` | 127 | 135 |
| `widgets/base/overview/bt_best_plays.py` | 112 | 108 |
| **`widgets/base/overview/` total** | **720** | **666** |
| `widgets/panels.py` | 888 | 968 |
| `themes/minimal.tcss` (5 `bto-*-title` blocks) | 2988 | 2965 |

**54 lines out of the package and 23 out of the stylesheet; 80 lines of shared code in** (the
function, two knobs and their docstrings). Net +3 production lines — the two files that grew did
so by docstring: the leaderboard's records the per-row guard, the feed's records why it is a
stream and why its rows highlight themselves (deviations 4 and 7).

**Rendering proof.** `render_case.py base b8_wpa_base` on the sweep payload under the real
stylesheet and a frozen clock, at 170×50 and at the 143 pin, against the pre-migration capture:

```
$ cmp b8_before_base.default.170x50.txt     b8_wpa_base.default.170x50.txt
b8_before_base.default.170x50.txt b8_wpa_base.default.170x50.txt differ: char 6555, line 33
$ cmp b8_before_base.default.pin-143x50.txt b8_wpa_base.default.pin-143x50.txt
b8_before_base.default.pin-143x50.txt b8_wpa_base.default.pin-143x50.txt differ: char 5529, line 33
```

Not byte-identical, by one line at each size, and the line is the one the Design predicted: the
copy wrote `No activity yet` **once per empty poll** and the harness's mount performs two
refreshes, so the before-capture shows it twice (170×50 lines 32–33); `RichLogFeed` clears and
writes it once, so line 33 is now blank (`diff`: `33d32 < No activity yet`, and a blank row
appended at 49; at 143 the same line keeps the wrapped BEST PLAYS `Change` and loses only the
placeholder). Nothing else moved at either size: the six leaderboard columns, the three
sparkline rows and their `$…` / `…/h` values, the three signal rows with their trailing dot, the
blank recommendation row, the feed header and the BEST PLAYS header + gap all sit where they did.
The capture is text only (`seg.text`), so a **style** change would not show in `cmp`; the one
style hazard (a `Text` row is not run through `RichLog`'s `ReprHighlighter`, a `str` is) is pinned
instead by `test_feed_rows_carry_the_repr_highlight_the_copy_had`. States the capture does not
reach: **pre-poll**, the sparkline seeds `waiting for data...` on all three lines where the copy
seeded `Loading...` on the first (deviation 6); the other five panels seed as before
(`Loading...` on the first row / box, `No activity yet` after the first empty poll). **Failed
read**, below.

**Failed read — what the base manager serves.** `data/base_client.py:742-747`
(`_safe_dex_trending`) swallows a failed DexScreener trending fetch and returns `[]`, so
`BaseSnapshot.trending_tokens` is empty; `data/base_manager.py:112` copies it, `:168` serves
`"trending_tokens": tokens` (`[]`), `:255` / `:260` build `gainers` / `losers` from the same list
(`[]`), `:281` builds `whale_trades` from it (`[]`), and `:234` / `:246` set `total_volume = None`
and a `"N/A"` / `"0.0%"` top gainer. **A failed trending read and a poll that truly found no
tokens are indistinguishable in this payload — the dota C1 shape.** Pre-existing, in a data
module this WP does not own; filed as follow-up **#28** in `docs/handover_followups_2026_09.md`, not
fixed. The three histories are
never `None`: `base_cache.py:223-233` return `list(...)` and `record_overview_point`
(`:196`, the `None` skips at `:216-221`) records no point for a failed cycle, so they hold the
prior true points and no sentinel. A wholly failed `fetch_snapshot` re-raises at
`base_manager.py:109` and `DashboardScreen._do_refresh` skips every panel — that path is correct.
What the migrated widgets show on the `[]` payload is what the copies showed: leaderboard the
`EMPTY_ROW` (`-- No data -- -- -- --`), feed its prior rows (stream) or `No activity yet`, BEST
PLAYS ten blank rows, hero `...` for the `None` volume and `N/A` / `0.0%` for the gainer. None
of it is a false degradation and none of it is a crash; it is a real-negative reading of a failed
read, which is #28's subject.

**Mutation table** — each mutation applied in place, the *named file* run, the test that
reddened recorded, the mutation reversed by inverse edit and the file `cmp`'d byte-for-byte
against a pre-mutation snapshot (27 of 27 restored identical; the run's `git diff` afterwards
was the WP-A diff and nothing else).

| # | mutation | file run | result | test that reddened |
| --- | --- | --- | --- | --- |
| 1 | `("Token", 14)` → 13 | `test_base_widgets.py` | 1 failed, 17 passed | `test_leaderboard_header_cells_sit_at_the_six_column_widths` |
| 2 | `ROW_CAP = 15` → 16 | same | 1 failed, 17 passed | `test_leaderboard_draws_fifteen_rows_and_not_the_sixteenth` |
| 3 | `EMPTY_ROW` cells `--`/`No data` swapped | same | 1 failed, 17 passed | `test_leaderboard_empty_row_puts_no_data_in_the_token_cell` |
| 4 | `is_top = idx <= 3` → `<= 4` | same | 1 failed, 17 passed | `test_leaderboard_bolds_the_top_three_symbols_only` |
| 5 | `LABEL_WIDTH = 10` → 8 | same | 2 failed, 16 passed | `test_sparkline_labels_are_padded_to_ten_cells`, `test_an_empty_series_says_waiting_beside_its_label` |
| 6 | `SPARK_WIDTH = 20` → 22 | same | 1 failed, 17 passed | `test_sparkline_is_twenty_blocks_wide_not_the_shared_twenty_two` |
| 7 | `SHOW_ARROW = True` → `False` | same | 1 failed, 17 passed | `test_sparkline_draws_the_trend_arrow` |
| 8 | `EMPTY_KEEPS_LABEL = True` → `False` | same | 1 failed, 17 passed | `test_an_empty_series_says_waiting_beside_its_label` |
| 9 | `EMPTY_TEXT` → `""` | same | 1 failed, 17 passed | `test_an_empty_series_says_waiting_beside_its_label` |
| 10 | `fmt_value` drops the `$` prefix | same | 1 failed, 17 passed | `test_sparkline_values_keep_the_dollar_prefix_and_per_hour_suffix` |
| 11 | `fmt_value` drops the `/h` suffix | same | 1 failed, 17 passed | same |
| 12 | `BTSignals` rows `indicator=""` → `None` (dot gone) | same | 1 failed, 17 passed | `test_signal_rows_are_label_value_then_trailing_dot` |
| 13 | recommendation always written (never blank) | same | 1 failed, 17 passed | `test_recommendation_is_blank_when_empty_and_one_row_under_the_rows` |
| 14 | bare `None` separator added to `ROWS` | same | 1 failed, 17 passed | same (two blanks, recommendation one row lower) |
| 15 | `HEADER_LINE` → `None` | same | 1 failed, 17 passed | `test_feed_writes_its_column_header_above_the_first_row` |
| 16 | `SNAPSHOT = True` on `BTActivityFeed` | same | 2 failed, 16 passed | `test_feed_paints_the_placeholder_once_across_empty_polls`, `test_feed_keeps_its_rows_on_an_empty_poll` |
| 17 | `format_row` returns the un-highlighted `Text` | same | 1 failed, 17 passed | `test_feed_rows_carry_the_repr_highlight_the_copy_had` |
| 18 | BEST PLAYS gap `Static` removed | same | 1 failed, 17 passed | `test_best_plays_keeps_one_gap_row_between_header_and_rows` |
| 19 | hero `[dim]No data[/]` → `[yellow]unavailable[/]` | same | 1 failed, 17 passed | `test_hero_says_no_data_for_a_missing_gainer_and_dots_for_none` |
| 20 | `panels.py` drops `width=self.SPARK_WIDTH` | `test_panels.py` | 1 failed, 144 passed | `test_spark_width_is_the_bars_cell_count` |
| 21 | same mutation | `test_base_widgets.py` | 1 failed, 17 passed | `test_sparkline_is_twenty_blocks_wide_not_the_shared_twenty_two` |
| 22 | `fmt_signal_trailing` value not escaped | `test_panels.py` | 1 failed, 144 passed | `test_fmt_signal_trailing_escapes_a_hostile_value_and_keeps_its_width` |
| 23 | `fmt_signal_trailing` indicator word not escaped | same | 1 failed, 144 passed | same |
| 24 | `HEADER_LINE` never written | same | 1 failed, 144 passed | `test_a_header_line_is_written_above_the_rows_on_every_paint` |
| 25 | same mutation | `test_base_widgets.py` | 1 failed, 17 passed | `test_feed_writes_its_column_header_above_the_first_row` |
| 26 | no `log.clear()` before the placeholder when a header stands | `test_panels.py` | 1 failed, 144 passed | `test_a_header_never_stands_over_an_empty_table` |
| 27 | `PanelBase > .panel-title` margin `0 0 1 0` → `0` | `test_title_blank_row.py` | 33 failed, 20 passed | `test_every_panel_paints_a_blank_row_under_its_title[BTSparklines / BTSignals / BTBestPlays / BTOverviewLeaderboard / BTActivityFeed]` among the 33 |

**Tests.** Named set, all green on the WP-A tree: `tests/widgets/test_base_widgets.py` 18 (new),
`tests/widgets/test_panels.py` 145 collected (was 128: +9 functions, +8 parametrised cases the
`base.overview` table row adds to the banned-name and clash scans), `tests/widgets/test_title_blank_row.py` 53 (was 51),
`tests/widgets/test_base_address_icons.py` 2, `tests/widgets/test_medi38_unavailable_state.py` 38,
`tests/widgets/test_markup_safety.py` 78 (run additionally: it calls
`BTOverviewLeaderboard().update_data([...])` positionally and asserts `#bto-lb-table`'s row
count), `tests/screens/test_base_terminal_screen.py` 3, `tests/screens/test_refresh_guard.py` 7,
`tests/screens/test_dashboard_screen.py` 26, `tests/test_address_rule.py` 10,
`tests/screens/test_address_icons_everywhere.py -k base` 2 (41 deselected); `-m guard tests`
last — see the commit. **Name-list diff** against `2c6447a`: `test_panels.py` +9 functions
(`test_fmt_signal_trailing_with_an_indicator_has_the_three_padded_cells`, `…_without_an_indicator_ends_after_the_value`,
`…_with_an_empty_indicator_is_the_dot_alone`, `…_honours_the_three_width_keywords`,
`…_escapes_a_hostile_value_and_keeps_its_width`, `test_spark_width_is_the_bars_cell_count`,
`test_a_header_line_is_written_above_the_rows_on_every_paint`,
`test_a_header_never_stands_over_an_empty_table`, `test_a_feed_without_a_header_line_writes_none`),
no deletion, no rename; `test_title_blank_row.py` no function added or removed — the two new cases
(`BTOverviewLeaderboard`, `BTActivityFeed`) are rows in its `_PANELS` parametrisation;
`test_base_widgets.py` is new, 18 functions, all additions.

**Deviations from the Design**, numbered:

1. `fmt_signal_trailing`'s `indicator` defaults to **`None`** (row ends after the value, bakery's
   `None`-signal shape) and **`""` is the dot alone**, which is what every BT row ends in. The
   Design's `indicator=""` default "ending after the value" would have left `BTSignals` no way to
   ask for a bare dot, and padding an empty word to `indicator_width` would have put ten trailing
   cells past the pin. Both endings are pinned (`test_fmt_signal_trailing_without_an_indicator…`,
   `…_with_an_empty_indicator_is_the_dot_alone`).
2. `BTSignals.ROWS` carries **no bare `None`** separator: `SignalsPanelBase` yields the blank row
   before the recommendation itself when `RECOMMENDATION_ID` is set, so the copy's
   `bto-sig-spacer-2` is that row and a `None` item would paint two (mutation 14; the cattown
   precedent).
3. `SparklinePanel.SPARK_WIDTH` was added — the Design allowed a hook "only if it defaults to
   today's behaviour and is tested": it defaults to `sparkline_common.SPARK_WIDTH` (22, what every
   migrated panel drew) and BT is laid out for 20 (mutations 6, 20, 21). It also serves WP-B's
   cookie chart (30).
4. `RichLogFeed.HEADER_LINE` was added on the same terms (default `None`, mutations 15, 24–26):
   the copy wrote a column heading above its ranking and the Design's "stream, keep the copy's
   text" cannot be met without it.
5. No per-poll-label sparkline hook: `render_series` already takes the labels per call, so a
   missing third line is `("", [], color, "")`.
6. Pre-poll the three sparkline lines seed `waiting for data...` (the base's `EMPTY_TEXT` rule)
   where the copy seeded `Loading...` on the first line only; uncaptured (the render harness
   polls before it captures), stated here.
7. `BTActivityFeed.format_row` runs `ReprHighlighter` over its `Text` itself: `RichLog` applies
   its highlighter to a `str` row and not to a `Text`, and the copy's rows were `str`. Without it
   the numbers lose their colour with no change to the text capture (mutation 17).
8. `SHOW_ARROW = True` is restated on `BTSparklines` although it is the default, so the panel's
   knobs read in one place.
9. Two `DEFAULT_CSS` geometry blocks kept (leaderboard `DataTable`, feed `RichLog`), as Branch 6
   dev.2 / Branch 7 dev.5.
10. `tests/widgets/test_markup_safety.py` was run beyond the named set as a consumer of
    `BTOverviewLeaderboard.update_data`'s positional signature.

**Seen, not fixed (filed as #28–#31 in `docs/handover_followups_2026_09.md`, not owned by this WP):**
**#28** the base client's `[]`-for-a-failed-read
above (the dota C1 shape; the fix is in `data/base_client.py` / `base_manager.py`, out of a
widgets-only WP, and turns the feed into a `SNAPSHOT` candidate once `None` is served); **#29**
the TOP GAINER hero box clips its `+12.0%` second body line in the 7-row box at 170 and 143 —
pre-existing, in the before-capture; **#30** the BEST PLAYS header wraps at the 143 pin (`Change`
on its own line 33) — pre-existing, in the before-capture; **#31** the status bar reads
`updated 0s ago` after a partially failed read because the manager returns a payload (#28's
sibling).

**Branch 8 WP-A fix round 1 (2026-09-20).** Review verdict `Needs fixes: 0 Critical, 2 Important`
plus four Minor; all six addressed except M4, which the review asked to be filed, not fixed.

- **I1 — the BT degraded states were pinned by nothing.** `tests/widgets/test_medi38_unavailable_state.py`
  now names `BTOverviewHero` and `BTSignals`. Both went into the **second** table (`_HERO_ROWS`),
  not the first, for the reason its docstring gives for talismans and ttt: they are handed scalars,
  and a `None` scalar is the manager's "absent this poll" (`eth_price` / `total_volume` omitted
  when no token trended; a signal string the analytics could not compute), which the copy rendered
  `...` — so claim 1 for them is "`...`, never `Loading`, never `unavailable`". The table gained a
  fifth field, the row's *absent word* (`--` for talismans/ttt, `...` for base), and the claim-1
  test asserts that field instead of a literal `--`; claims 2 and 3 are unchanged and `BTHeroBox`
  joined the harness's `height: 9` list. The hero's malformed value is `_Hostile()` on `eth_price`
  (`_price_body` catches `ValueError`/`TypeError` itself, so the value has to raise past those);
  the signals' is `_Hostile()` on `buy_sell_signal` (`_signal_indicator` calls `str(value)`).
  `tests/widgets/test_base_widgets.py` gained the two composited pins the review asked for:
  `test_signal_malformed_value_after_a_good_poll_is_a_yellow_unavailable_row` (good poll, hostile
  second poll; the Buy/Sell row reads `unavailable` right-aligned to 36 with the dot at 38, the
  other two rows keep `Rising` / `Neutral`, and the word's composited segment is yellow and not
  bold — M3's pin) and `test_best_plays_malformed_entry_after_a_good_poll_lands_on_unavailable`
  (good poll, then a gainer whose `price_change_24h` is `"abc"`; row 0 is `unavailable` at column
  4 in yellow, `ALPHA +12.0%` gone, rows 1–9 blank).
- **I2 — #28–#31 were not in the backlog.** Filed in `docs/handover_followups_2026_09.md` under
  "## Branch 8 — panels, base terminal and bakery" in the #23–#27 shape (file:line, what breaks,
  tier, filed-by): #28 `base_client.py:742-747` `[]` for a failed trending fetch (Tier 1; the
  feed becomes a `SNAPSHOT` candidate once `None` is served), #29 TOP GAINER second line clipped
  (sibling of #6), #30 BEST PLAYS header wraps at 143, #31 `updated 0s ago` after a partial
  failure (sibling of #23/#28). The outcome paragraph's two "below" pointers now name the backlog.
- **M1 — `sparkline_common.py`'s ledger.** `bt_sparklines.py` moved from the "not yet on this
  module" list (now seven) to the converged list, "through `panels.SparklinePanel`". `BTSparklines`
  joined `SPARKLINE_WIDGETS` in `tests/widgets/test_sparkline_common.py` (that list entry and its
  import, nothing else in the file): 89 → 99 collected, all green.
- **M2** — `bt_best_plays.py` imports `UNAVAILABLE_LINE` instead of re-typing `f"  {UNAVAILABLE}"`.
- **M3 — the degraded signal word was bold white.** `fmt_signal_trailing` gained an append-only
  keyword `value_color: str | None = None` that replaces the value cell's `[bold white]` with one
  style word; `None` is the previous behaviour byte for byte. `BTSignals` builds its fallback with
  `color="yellow", value_color="yellow"`. Chosen over assembling the row by hand in `bt_signals.py`
  so bakery's `SignalsPanel` (WP-B) can degrade through the same call, and because the function
  escapes `value`, which is why the shared `UNAVAILABLE` markup cannot simply be passed as the
  value. Pinned in `test_panels.py::test_fmt_signal_trailing_value_color_replaces_bold_white_and_nothing_else`
  and, composited, in the I1 signals pin (style triplet `(255, 255, 0)` — Textual resolves the
  markup's `yellow` to `#ffff00`, so the pin compares the triplet, not the name).
- **M4** — not fixed, per the review: filed as **#32** (Minor, Tier 0 when a migrated sparkline
  test is next touched: one composited width pin per package).

**Mutation table** (each applied in place, the named file run, reversed by inverse edit, the file
`cmp`'d byte-for-byte against a pre-mutation snapshot — 8 of 8 restored identical):

| # | mutation | file run | result | test that reddened |
| --- | --- | --- | --- | --- |
| 1 | `BTSignals._signal_row`: `write_guarded(...)` → `self.write(selector, build())` | `test_base_widgets.py` | 1 failed, 19 passed | `test_signal_malformed_value_after_a_good_poll_is_a_yellow_unavailable_row` |
| | same | `test_medi38_unavailable_state.py` | 1 failed, 43 passed | `test_a_malformed_hero_poll_after_a_good_one_is_not_shown_as_live[BTSignals]` |
| 2 | fallback drops `value_color="yellow"` | `test_base_widgets.py` | 1 failed, 19 passed | the same signals pin (on the style) |
| 3 | fallback word `unavailable` → `unavail.` | `test_base_widgets.py` | 1 failed, 19 passed | the same signals pin (on the text) |
| | same | `test_medi38_unavailable_state.py` | 1 failed, 43 passed | `test_a_malformed_hero_poll_after_a_good_one_is_not_shown_as_live[BTSignals]` |
| 4 | `BTBestPlays.update_data`: `write_guarded(...)` → `self.write(f"#bto-bp-row-{i}", _row(...))` | `test_base_widgets.py` | 1 failed, 19 passed | `test_best_plays_malformed_entry_after_a_good_poll_lands_on_unavailable` |
| 5 | fallback `UNAVAILABLE_LINE` → `UNAVAILABLE_LINE.strip()` | `test_base_widgets.py` | 1 failed, 19 passed | same (column pin) |
| 6 | `panels.py`: `value_color` ignored (`value_style = "bold white"`) | `test_panels.py` | 1 failed, 145 passed | `test_fmt_signal_trailing_value_color_replaces_bold_white_and_nothing_else` |
| | same | `test_base_widgets.py` | 1 failed, 19 passed | the signals pin (on the style) |
| 7 | a private `_coerce_points` pasted into `bt_sparklines.py` | `test_sparkline_common.py` | 2 failed, 97 passed | `test_helpers_are_the_shared_functions[BTSparklines]`, `test_no_module_redefines_a_shared_helper[BTSparklines]` |
| 8 | `panels.py` `HeroRow.render_box`: `body = build()` moved outside the guard | `test_medi38_unavailable_state.py` | 6 failed, 38 passed | `…[BTOverviewHero]` among the six hero rows |

The review's own mutation (the two `write_guarded` blocks → plain `write`) is rows 1 and 4: 335/0
and 257/0 before this round, 1 failed in each named file now.

**Rendering proof.** `render_case.py base b8_fix1_base` against the WP-A capture:

```
$ cmp b8_wpa_base.default.170x50.txt     b8_fix1_base.default.170x50.txt      -> identical (exit 0)
$ cmp b8_wpa_base.default.pin-143x50.txt b8_fix1_base.default.pin-143x50.txt  -> identical (exit 0)
```

Byte-identical at both sizes: the fallbacks are unreachable on the sweep payload and `value_color`
defaults to the previous markup, so M3 moved nothing.

**Tests.** Named set green: `test_base_widgets.py` 20 (was 18), `test_medi38_unavailable_state.py`
44 (was 38: two rows × three claims), `test_panels.py` 146 (was 145), `test_sparkline_common.py` 99
(was 89: one class × ten cases), `test_title_blank_row.py` 53, `test_base_address_icons.py` 2,
`test_markup_safety.py` 78, `test_base_terminal_screen.py` 3, `test_refresh_guard.py` 7,
`test_dashboard_screen.py` 26, `test_address_rule.py` 10, `test_address_icons_everywhere.py -k
base` 2 (41 deselected); `-m guard tests` last — see the commit. **Name-list diff** against
`24e13d3`: `test_base_widgets.py` +2 (`test_best_plays_malformed_entry_after_a_good_poll_lands_on_unavailable`,
`test_signal_malformed_value_after_a_good_poll_is_a_yellow_unavailable_row`); `test_panels.py` +1
(`test_fmt_signal_trailing_value_color_replaces_bold_white_and_nothing_else`);
`test_medi38_unavailable_state.py` and `test_sparkline_common.py` no function added or removed —
their new cases are table rows. No deletion, no rename anywhere.

**Branch 8 WP-A re-review of fix round 1 (2026-09-20): Approved.** All six findings ADDRESSED, each behind a mutation the reviewer re-ran against the named file: both `write_guarded` removals now redden the composited pins (the signals one also reddens `test_a_malformed_hero_poll_after_a_good_one_is_not_shown_as_live[BTSignals]`); the `value_color=None` path was compared against a re-implementation of the pre-fix `fmt_signal_trailing` over 4,200 label/value/indicator/colour/width combinations with 0 differences; the `_HERO_ROWS` absent-word field is load-bearing (`"--"` → `"ZZZ"` reddens the talismans case); `b8_rev2_base.*` re-rendered from `81ef1da` cmp identical to `b8_wpa_base.*`. 385 passed over nine named files, 191 guard. One new Minor, N1: MEDI-38 claim 2 (a real `0` is a number) is untested for every `_HERO_ROWS` entry, BT included — filed as follow-up #33, not fixed. **WP-A closed at `81ef1da`; WP-B starts from this head.**

**Branch 8 WP-B outcome (2026-09-20).** The six top-level bakery widgets are on the bases:
`HeroMetrics(HeroRow)` with `HeroBox(HeroBoxBase)` (kept under its own name because
`minimal.tcss` has a bare `HeroBox` block), `Leaderboard(TableLeaderboard)`,
`CookieChart(SparklinePanel)` with the copy's 30-cell `SPARK_WIDTH`, `SignalsPanel(SignalsPanelBase)`
on `fmt_signal_trailing`, `ActivityFeed(RichLogFeed)` keyed on the copy's four fields, and
`EVTable(PanelBase)`. Every class name and every `update_data` parameter list is unchanged and
`widgets/__init__.py` is untouched, so `screens/bakery.py`'s `PANELS` and the panel-row agreement
test were not touched. Every spacer `Static`, per-panel title class and `DEFAULT_CSS` title block
is gone from the six modules; the two **geometry** blocks stay (`Leaderboard > DataTable { height:
1fr }`, `ActivityFeed > RichLog { height: 1fr; padding: 0 1; scrollbar-size: 1 1 }`).
`themes/minimal.tcss` lost exactly the five bakery title blocks — `Leaderboard > Static`,
`CookieChart > .chart-title`, `SignalsPanel > .signals-title`, `ActivityFeed > .feed-title`,
`EVTable > .ev-title` — and nothing else (the nine bare `HeroMetrics` / `HeroBox` / `Leaderboard` /
`Leaderboard DataTable` / `CookieChart` / `SignalsPanel` / `ActivityFeed` / `ActivityFeed RichLog` /
`EVTable` geometry blocks remain; a `guard` test pins the five absences).
**`maxpane_dashboard/templates/` is deleted whole** — nine files, `git rm` by pathspec — and every
live reference retired: `tests/screens/test_refresh_guard.py` no longer walks the template screen,
`tests/widgets/test_markup_safety.py`'s two hostile-entry tests run against a local
`_HostileBoard(TableLeaderboard)` instead of `GameLeaderboard`, `tests/widgets/test_sparkline_common.py`
lists `CookieChart` where it listed `GameSparklines`, `tests/widgets/test_panels.py` drops
`maxpane_dashboard.templates` from the clash scan, `CLAUDE.md` (three tier lines, the tree, the
hazards bullet) and `rules/widgets.md` (frontmatter path, the copy-source sentences, step 3 of
"Reuse before you build") describe the deletion. `panels.py` changed by docstring only (four
"the template" mentions → "the since-deleted template"); no code line in it moved.

*Line counts are raw `wc -l`.*

| file | before | after |
| --- | --- | --- |
| `widgets/hero_metrics.py` | 187 | 124 |
| `widgets/leaderboard.py` | 87 | 93 |
| `widgets/cookie_chart.py` | 115 | 65 |
| `widgets/signals_panel.py` | 118 | 116 |
| `widgets/activity_feed.py` | 214 | 160 |
| `widgets/ev_table.py` | 111 | 105 |
| **six bakery modules total** | **832** | **663** |
| `templates/` (9 files) | 1,080 | 0 |
| `themes/minimal.tcss` (5 bakery title blocks) | 2965 | 2942 |
| `widgets/panels.py` | 978 | 979 |
| `tests/widgets/test_bakery_widgets.py` (new, 32 tests) | — | 744 |

**169 lines out of the six modules, 1,080 out of `templates/`, 23 out of the stylesheet; one
line into `panels.py` (a docstring wrap).** The leaderboard grew by six: its `__init__` now stashes
the rates and the leader's count for the base's `build_row(index, item)` hook, and the docstring
records why an unreadable leader leaves the gap column saying `--`.

**Rendering proof.** `render_case.py bakery b8_wpb_bakery` and `render_case.py base b8_wpb_base`
on the sweep payloads under the real stylesheet and a frozen clock, at 170×50 and at the 143 pin,
against the WP-A-head captures:

```
$ cmp b8_before_bakery.default.170x50.txt     b8_wpb_bakery.default.170x50.txt
b8_before_bakery.default.170x50.txt b8_wpb_bakery.default.170x50.txt differ: char 2876, line 13
$ cmp b8_before_bakery.default.pin-143x50.txt b8_wpb_bakery.default.pin-143x50.txt
b8_before_bakery.default.pin-143x50.txt b8_wpb_bakery.default.pin-143x50.txt differ: char 2427, line 13
$ cmp b8_fix1_base.default.170x50.txt        b8_wpb_base.default.170x50.txt       -> identical (exit 0)
$ cmp b8_fix1_base.default.pin-143x50.txt    b8_wpb_base.default.pin-143x50.txt   -> identical (exit 0)
```

Base is byte-identical at both sizes (the `panels.py` change is docstring-only, as it should be).
Bakery differs at both sizes in three panels and nowhere else, and every difference is a
`Loading...` that became `unavailable`: line 13, COOKIE TRENDS (`  Loading...` → `  unavailable`,
two cells further right because the seed was the bare `LOADING` and the fallback is the
`UNAVAILABLE_LINE` row shape); lines 19–23, SIGNALS (one `Loading...` → three rows `Late-Join EV`
/ `Gap Trend` / `Leader Dominance` each ending `unavailable  ●`, then `→ Recommendation:
unavailable`); lines 34–36, BEST PLAYS (`Loading...` → three `unavailable` rows). Hero boxes, the
leaderboard row, the feed line, every title and every column are unchanged. The cause is the
payload, not the widgets: `tests/address_sweep/builders.py:555-597`'s bakery payload carries no
`chart_histories`, no `late_join_ev` / `gap_analysis` / `dominance` / `recommendation` and no
`boost_rankings` / `attack_rankings`, so the `keys(...)` adapters pass `None`; the copies raised on
`None` into the screen's `except` and left the mount's `Loading...` seed on screen as if live — the
MEDI-38 stale-value case — and the migrated panels say `unavailable` where they could not look.

**Failed-read statement.** From the real manager, `chart_histories`, `late_join_ev`, `gap_analysis`,
`dominance`, `recommendation`, `boost_rankings` and `attack_rankings` are never `None`
(`data/manager.py:130-131, 141, 159, 182, 184, 192-194` compute them unconditionally) and a wholly
failed fetch re-raises out of `fetch_and_compute` (`manager.py:85-87`), so the screen skips every
panel and the `as of` marker carries the age. `None` reaches these widgets only from a partial
payload — what `DashboardScreen`'s `keys()` yields for an absent key — and the sweep payload above
is the one place that happens today. `bakeries` and `events`, by contrast, arrive as `[]` when
their sub-fetch failed (`data/client.py:330-334` and `343-347` log a warning and substitute the
empty list): a failed read wearing a real negative's clothes, the C1 shape Branch 7 fixed in dota's
manager, pre-existing here and filed as #35 rather than fixed in a widget work package.

**Mutations.** Eighteen, each restored by inverse edit (`filecmp` against a snapshot, `restored=True`
in every row) and each run against the one named file:

| # | mutation | file run | result | test that reddened |
| --- | --- | --- | --- | --- |
| 1 | `hero_metrics.py` `_BAR_CELLS` 12 → 10 | `test_bakery_widgets.py` | 1 failed, 31 passed | `test_countdown_bar_is_twelve_cells_and_the_percent_is_elapsed` |
| 2 | countdown label always `SEASON COUNTDOWN` | same | 1 failed, 31 passed | `test_an_ended_season_relabels_the_box_and_says_so_in_yellow` |
| 3 | `leaderboard.py` leader highlight `index == 0` → `== 1` | same | 1 failed, 31 passed | `test_the_leader_row_is_bold_with_a_green_rate_and_the_second_is_not` |
| 4 | `Bakery` column 24 → 22 | same | 1 failed, 31 passed | `test_leaderboard_header_cells_sit_at_the_five_column_widths` |
| 5 | `cookie_chart.py` `SPARK_WIDTH = 30` dropped (base default 22) | same | 1 failed, 31 passed | `test_cookie_chart_draws_a_thirty_cell_bar_after_an_eight_cell_label` |
| 6 | `_label_cell` escapes before the clip | same | 1 failed, 31 passed | `test_cookie_chart_escapes_the_name_after_clipping_it` |
| 7 | `isinstance(histories, dict)` guard removed | same | 1 failed, 31 passed | `test_cookie_chart_says_unavailable_when_the_histories_are_not_a_dict` |
| 8 | `signals_panel.py` fallback drops `value_color="yellow"` | same | 1 failed, 31 passed | `test_a_signal_the_manager_could_not_compute_says_unavailable` |
| 9 | recommendation written unescaped | same | 1 failed, 31 passed | `test_the_recommendation_is_centred_and_escaped` |
| 10 | `None` recommendation → `""` | same | 1 failed, 31 passed | `test_a_missing_recommendation_is_unavailable_not_blank` |
| 11 | `activity_feed.py` `dedupe_key` gains the title | same | 1 failed, 31 passed | `test_the_dedupe_key_is_time_launcher_type_and_description` |
| 12 | `hhmm` → `time.localtime` formatting | same | 2 failed, 30 passed | `test_the_feed_paints_time_iconed_launcher_and_the_title`, `test_a_launcher_less_event_is_the_bakerys_own` |
| 13 | `ev_table.py` `_row` reads `boost_rankings or []` | same | 1 failed, 31 passed | `test_rankings_the_manager_could_not_produce_say_unavailable_thrice` |
| 14 | header `{'EV':>10}` → `{'EV':>9}` | same | 1 failed, 31 passed | `test_ev_table_header_and_rows_sit_at_the_14_10_14_8_cells` |
| 15 | `minimal.tcss`: `Leaderboard > Static { … margin: 0 0 1 0 }` pasted back | same | 1 failed, 31 passed | `test_the_stylesheet_carries_no_bakery_title_block` |
| | same | `test_title_blank_row.py` | 55 passed | none — the blank-row count is unchanged because the base's margin and the pasted one coincide; that is why the guard test exists |
| 16 | `_UNAVAILABLE = "[yellow]unavailable[/]"` pasted into `hero_metrics.py` | `test_panels.py` | 1 failed, 152 passed | `test_no_migrated_module_redeclares_what_panels_py_owns[widgets/hero_metrics.py]` |
| 17 | a private `_coerce_points` pasted into `cookie_chart.py` | `test_sparkline_common.py` | 2 failed, 96 passed | `test_helpers_are_the_shared_functions[CookieChart]`, `test_no_module_redefines_a_shared_helper[CookieChart]` |
| 18 | `CookieChart(SparklinePanel)` → `CookieChart(PanelBase)` | `test_panels.py` | 1 failed, 152 passed | `test_every_migrated_panel_subclasses_a_panels_base[bakery-6]` |

**Tests.** Named set green, one command per group: **A** (widgets/screens) 619 passed —
`test_activity_feed_degradation.py` 30, `test_hero_metrics_degradation.py` 34,
`test_ev_table_catalog_source.py` 4 (the 21 functions of the three acceptance files unchanged:
`git diff --stat b3b3e1a -- <the three>` is empty), `test_bakery_widgets.py` 32 (new),
`test_panels.py` 153 (was 146: six `bakery` modules in the redeclaration walk, one `[bakery-6]`
row), `test_title_blank_row.py` 55 (was 53: `Leaderboard`, `ActivityFeed`), `test_markup_safety.py`
78 (unchanged), `test_sparkline_common.py` 98 (was 99: one function out, `CookieChart` replaces
`GameSparklines` row for row), `test_hidden_shared_address_icons.py` 8 (was 10), `test_medi38_unavailable_state.py`
44, `test_base_widgets.py` 20, `test_refresh_guard.py` 6 (was 7), `test_dashboard_screen.py` 26,
`test_app_startup.py` 21, `test_address_rule.py` 10; **B** `test_address_icons_everywhere.py -k
"bakery or base"` 4 passed (39 deselected); **C** the doc-pinning files
(`rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`) 4,081 passed in 12:32; `-m guard tests`
last, after the two docs were final: 192 passed (8,171 deselected). **Name-list diff** against `b3b3e1a`, exactly the four template tests
the brief names and nothing else: `test_refresh_guard.py` −`test_template_screen_inherits_the_guard`;
`test_sparkline_common.py` −`test_template_seeds_an_import_not_a_copy`;
`test_hidden_shared_address_icons.py` −`test_each_template_uses_the_helper_and_defines_no_formatter`;
`test_markup_safety.py` `test_template_leaderboard_survives_hostile_entries` →
`test_table_leaderboard_survives_hostile_entries` and `…_hostile_address_fallback` →
`test_table_leaderboard_survives_hostile_address_fallback` (re-targeted, the brief's option, so the
hostile-`DataTable` coverage survives the template's deletion). `test_panels.py`,
`test_title_blank_row.py` and the three acceptance files: no function added, removed or renamed.

**Remaining `templates` mentions are all history**, none a live path: `CLAUDE.md` (the hazards
bullet says they were deleted), `rules/widgets.md` (two past-tense sentences), `panels.py`
docstrings (four "since-deleted template"), `screens/refresh_guard.py:16`,
`widgets/sparkline_common.py:11-22`, `widgets/surf/pool4u_signals.py:3`, `HANDOVER.md:139, 181, 186`
(the backlog items this work package closes) and the dated plan/PRD/review documents under
`docs/`. `ls maxpane_dashboard | grep -c templates` is 0.

**Deviations from a byte-identical migration**, each intended and each pinned:
(1) three panels show `unavailable` instead of a stale `Loading...` on a `None` payload (the
render diff above; MEDI-38); (2) `CookieChart` writes a blank line for an empty `[]` series where
the copy drew a thirty-cell `▁` baseline ending `0 ●` — a flat baseline is a run of zeroes that
never happened (the `SparklinePanel` contract); (3) `CookieChart` says `unavailable` on its first
line for a non-dict `histories`, distinct from `{}` which blanks all three; (4) `CookieChart._label_cell`
escapes **after** the base clips, so a name with `[` reaches the screen whole; (5) the feed's time
column goes through `fmt.hhmm` instead of the copy's private `_format_event_time` — `None` and a
non-numeric stamp render `??:??` as before, and so now does a non-positive stamp (`0`), which the
copy printed as the local epoch hour; (6) the feed gains the base's flicker guard: a poll with nothing new
leaves the log alone where the copy cleared and redrew it every non-empty poll (same pixels unless
an unkeyed field — `success`, `is_outgoing` or `linked_bakery_name`; the key is
`timestamp:launcher:type:description` — changes underneath a drawn key, which an immutable
activity log does not do; the review probed `success` `False→True` on a repeated key and the
copy redrew `✓` where the migrated feed keeps `✗`); (7) `_who_text`
passes no `explorer=` — the copy declared none and Abstract (chain 2741) is not in
`widgets/explorer.py`'s allowlist, so the row renders a copy icon and no link, as the sweep's
`explorer=None` case asserts; (8) leaderboard rows are built inside the base's per-row guard, so one
unreadable bakery is one missing line, and a leader whose `tx_count` cannot be read leaves every
gap `--` rather than raising; (9) a `None` recommendation renders `→ Recommendation: unavailable`
and any other value is `str()`-ed before escaping; (10) `EVTable` renders three `unavailable` rows
for `None` rankings; (11) `_format_event`'s two byte-identical success branches (outgoing and
incoming) are one branch; (12) the two hostile-entry tests were re-targeted rather than deleted.

**Seen, not fixed** (filed as #34–#40 in `docs/handover_followups_2026_09.md`): the
`SparklinePanel` base writes `EMPTY_TEXT` for a `None` series (C1 shape in the base, Tier 2);
bakery's client substitutes `[]` for a failed bakeries/activity fetch (C1, Tier 1); `_label_cell` is
a private base hook a subclass now overrides; `Leaderboard.update_data`'s `prize_pool_usd` is
unused (pre-existing); the bare `HeroBox { height: 7; border: … }` block leaves three inner rows so
the countdown bar / rate sub-line composites only without the border (the existing degradation
test already dodges it with a border-less harness, as does the new file); the DataTable cursor
row's `color: $text` hides the leader's `[green]` rate on every leaderboard; and the sweep's bakery
payload lacks the chart/signal/ranking keys, so it certifies the degraded shape of three panels and
never their live one.

**Branch 8 WP-B review (2026-09-20): Approved, 0 Critical, 0 Important, 3 Minor.** The reviewer
rendered `BakeryScreen` on a full payload (every key the sweep lacks: three 8-point series, EV,
gap, dominance, recommendation, both rankings, four bakeries incl. a 29-char and a markup-bearing
name, five events across all `_format_event` branches) against a `b3b3e1a` worktree at 170×50 and
143×50: byte-identical at both sizes, with COOKIE TRENDS, SIGNALS and BEST PLAYS live; hero bodies
identical over seven input cases, and a 25-case panel matrix identical except the MEDI-38
corrections already listed as deviations (the copy raised `TypeError` on a `None`/non-list series
and executed markup in the recommendation). `fmt.hhmm` is `localtime` like the deleted helper — no
timestamp shifts. The `[]`-series blank is unreachable live (`cache.py:99` appends a point per
snapshot bakery per poll). #34 confirmed real in the base, seven subscribers, stands as filed.
Hostile tests bite (3 and 4 fail on the two mutations); three of the eighteen mutations re-run
and matched; the two new `test_title_blank_row` rows redden on the margin. Minors: M1 the rule
file named `screens/bakery.py` (125 lines) as the shortest migrated screen — `cattown.py` is 87,
corrected; M2 deviation (6) understated the flicker guard's unkeyed fields — corrected above;
M3 `test_bakery_widgets.py:347-348` asserts a cell string, recorded as debt under #39. Named set
563 passed; `-m guard tests` 192 passed. Tree clean, no worktree left.

## Branch 9 — `refactor/series-cache` (three work packages)

Spec: HANDOVER.md §3 item 6, first half — `SeriesCache` in `data/series_cache.py`, subclassed by
the per-poll series caches. Survey 2026-09-20 (scratchpad `branch9_survey.md`, anchors below are
against main `53a71d5`). Tier 2: a new shared `data/` module, 6 dashboards, > 6 files.

**Facts.** Six caches share the `max_history` shape — `data/cache.py` (bakery `DataCache`, 237
lines), `cattown_cache.py` (195), `dota_cache.py` (193), `ocm_cache.py` (349), `frenpet_cache.py`
(334), `base_cache.py` (379); 1,687 lines. `talismans_cache.py` (366) and `ttt_cache.py` (838)
are OUT: neither constructor takes `max_history` (`talismans_cache.py:67`, `ttt_cache.py:126`),
both are event/state machines whose series are hourly buckets and whose payloads are pydantic
dumps; the only code they would share is the atomic-write block (follow-up #41). Byte-identical
across the six bar the log noun: the atomic-write block (`cache.py:156-170` ≡ `cattown:123-140` ≡
`dota:121-138` ≡ `ocm:216-233` ≡ `frenpet:207-225` ≡ `base:265-282`), `get_latest`,
`last_updated`, the open/JSON-decode guard, the `"Skipped %d …"` warning. Per-cache specifics the
base must carry as hooks: bakery season-reset `dq.clear()` (`cache.py:90-98`) and the
"leave an all-expired bakery untracked" rule (`:219-222`); dota's lane guard (`dota_cache.py:61-68`);
ocm's `burn_history` at its own `maxlen=400` with per-series `max_age` (`ocm_cache.py:266-279`),
`_append_burn_sample` (`:111-130`), `holder_count` (`:170-183`), `"version": 2` with a pre-v2 branch
that clears the burn series (`:262-287`) and a private `_coerce_point` copy (`:321-349`) that
`series_points.py:24-26` already names as debt; frenpet's `"schema_version": 2` (`:194`, `:271-274`),
per-pet dict merged by assignment (`:285-296`), the three population deques the manager reads as
attributes (`frenpet_manager.py:419-421`), and the four managers sharing one instance
(`app.py:122-136`); base's LRU `_touch` and load-time cap (`base_cache.py:104-128`, `:320-353`),
`record_overview_point` skipping `None` (`:216-221` — the repo's reference statement of the
sentinel rule), `record_token`'s `ts = timestamp or time.time()` (`:160`). Persistence is driven
only from the six managers' `close()`; no screen or `app.py` calls it. `history_size` means
key-count in bakery/frenpet/base and representative-series point-count in cattown/dota/ocm, both
asserted (`test_cache.py:337`, `test_base_cache.py:126-183`). Tests: `test_cache.py` 18,
`test_cache_corruption.py` 12 (the only tests touching cattown/dota, 2 each), `test_base_cache.py`
11, `test_frenpet_cache.py` 24 (pins `inspect.signature(load_from_file)` and reads the population
deques as attributes), `test_ocm_cache.py` 17 (pins `payload["version"] == 2`),
`tests/test_app_startup.py:306-334` (frenpet shared-cache reload); `test_base_client.py:731` and
`test_token_detail.py:409` `patch()` the name `base_manager.BaseTokenCache`. Log literals bound by
tests: `"Skipped"` (six assertions), `"least-recently-updated"`. `tests/data/test_series_points.py`
does not exist; the branch-order table's mention of it is wrong — `coerce_point(s)` is covered in
`test_cache_corruption.py:68-112`.

**Design — `data/series_cache.py` (~150 lines, one owner, lands first).**

```python
@dataclass(frozen=True)
class SeriesSpec:
    name: str                      # attribute AND JSON key, e.g. "prize_pool_history"
    maxlen: int | None = None      # None → max_history
    max_age: float | None = None   # None → the loader's max_age= argument (default None)
    allow_negative: bool = False

class SeriesCache:
    SERIES: tuple[SeriesSpec, ...] = ()
    VERSION_KEY: str | None = None     # ocm "version", frenpet "schema_version"; others None
    VERSION: int = 1
    NOUN: str = "cache"                # log noun: "CatTown cache", "Base token cache", …
    def __init__(self, max_history: int = 120) -> None   # builds one public deque per SERIES
    def record(self, name: str, ts: float, value: float | None) -> bool   # drops None; never 0
    def _mark(self, snapshot) -> None                    # sets _latest / _last_updated
    def get_series(self, name: str) -> list[TimeSeriesPoint]
    def get_latest(self); last_updated (property)
    history_size (property) → len(first declared series); dict-keyed subclasses override
    def save_to_file(self, path: str) -> None            # atomic write of _payload()
    def _payload(self) -> dict                           # saved_at, max_history, VERSION_KEY, each SERIES; + extra_payload()
    def extra_payload(self) -> dict                      # hook, default {}
    def load_from_file(self, path, *, now: float | None = None, max_age: float | None = None) -> None
    def before_load(self, payload: dict, version: int) -> None    # hook (ocm pre-v2 clear)
    def restore_extra(self, payload: dict, *, now: float) -> int  # hook, returns dropped count (keyed series, scalars)
    def coerce_keyed(self, raw, *, now, max_age) -> tuple[dict[str, list[TimeSeriesPoint]], int]  # for the dict-of-series three
```

`load_from_file`: open/decode guard → `isinstance(payload, dict)` guard → version = `int(payload.get(VERSION_KEY) or 1)`
when `VERSION_KEY` is set, else 1 → `before_load` → for each spec: `coerce_points(payload.get(name), now=reference,
max_age=spec.max_age if spec.max_age is not None else max_age, allow_negative=spec.allow_negative)`, `clear()` +
`extend(good)` → `restore_extra` → one `"Skipped %d unusable or expired point(s) while loading %s %s"` warning when
dropped > 0 → `_log_loaded(payload)` hook (info). `reference = time.time() if now is None else now`, docstring reusing
`frenpet_cache.py:243-255`. `update()` stays a per-cache method built from `_mark` + `record`. Each cache keeps its
named getters as one-line wrappers over `get_series` (the managers and tests call them). The three dict-of-series
caches keep their dict and eviction; they call `coerce_keyed` from `restore_extra` and write the dict from
`extra_payload`.

**Decisions (each pinned by a test in the WP that lands it):**
- **R1 — no sentinel in a series.** `record()` drops `None`. `cattown_manager.py:102-111` passes `None` (not `0` /
  `0.0`) for a failed raffle read and for an empty entry list; `frenpet_manager.py:156-162` passes `battle_rate=None`
  to the cache when the attacks fetch fails — the widget dict's `global_battle_rate` stays as it is (its display
  default is follow-up #43). `CatTownCache.update(leader_weight_kg: float | None = None, raffle_total_tickets:
  int | None = None)`, `FrenPetCache.update(battle_rate: float | None = None)`. This is a CLAUDE.md convention
  outranking "preserve behaviour": the persisted zero outlived the outage and read as a real negative.
- **R2 — loaders take `now=`** (rules/data.md "Inject the clock"); the six managers keep calling with the default.
- **R3 — `record_token(timestamp=None)` uses `is None`, not `or`;** `update_holder_count(count, *, now=None)`.
- **R4 — `max_age` preserves today's behaviour exactly:** `None` for cattown/dota/frenpet/base, caller-supplied for
  bakery (`manager.py:67-69`), per-series consts for ocm. A test per WP asserts a 30-day-old point survives on the
  unwindowed four; whether to window them is follow-up #42, not this branch.
- **R5 — the dict guard is inherited by bakery and base** (a top-level JSON list no longer raises out of the loader);
  a test feeds `[]` to each of the six.
- **R6 — `history_size` stays two-meaning:** base default is the first declared series' point count (cattown, dota,
  ocm); bakery, frenpet, base override to their key count. No test changes.
- **R7 — the base clears before extend.** base_cache's `load_from_file` after an `update()` stops concatenating;
  its manager loads before the first update (`base_manager.py:69`, `:111`) so nothing live changes; a test pins the
  new order.
- **Persisted shape is unchanged for every file.** `VERSION_KEY`/`VERSION` stay `"version"`/2 (ocm) and
  `"schema_version"`/2 (frenpet); the four unversioned files gain NO version key (a bump or rename would route live
  ocm files through the pre-v2 clear and start frenpet's population series empty). Acceptance is fixture-first: for
  each of the six, a file written by `53a71d5`'s code is committed under `tests/fixtures/cache/<name>_53a71d5.json`
  (the implementer generates them from a `git worktree` of `53a71d5` with `PYTHONPATH` pointing at it, deterministic
  timestamps) and `tests/data/test_series_cache.py` loads each with `now=` pinned and asserts the series
  point-for-point equal to what the pre-branch class loads from the same file.
- `_coerce_point` and `_CLOCK_SKEW_TOLERANCE_SECONDS` in `ocm_cache.py` are deleted; `series_points.py:24-26` is
  rewritten to say the fold happened.
- Expected render diff: none — no widget or screen changes; the sweep cases for cattown, base, ocm, frenpet are
  re-rendered before/after and `cmp`'d anyway (`render_case.py`).

**WP-A — base + the two simplest caches.** Owner of `data/series_cache.py` (new), `tests/data/test_series_cache.py`
(new: spec table, `record` drops `None`, `now=` honoured, dict guard, clear-before-extend, per-series `max_age`,
version read, atomic-write failure path with the `.tmp` removed, fixture round-trips for dota + cattown),
`dota_cache.py`, `cattown_cache.py`, `cattown_manager.py` (R1 only), `tests/data/test_cattown_manager.py` (NEW — no cattown manager test exists;
one regression test: a failed raffle read and an empty entry list append nothing), `tests/fixtures/cache/dota_53a71d5.json`,
`cattown_53a71d5.json`. Named tests: the two new/changed test files + `test_cache_corruption.py` +
`tests/data/test_dota_manager.py` + `tests/screens/test_dashboard_screen.py` +
`tests/screens/test_address_icons_everywhere.py -k 'cattown or dota'` + `-m guard tests`.

**WP-B — bakery + base terminal.** `cache.py`, `base_cache.py` (also fixes the `save_to_file` docstring that omits
the three `overview_*` keys, `:242-252`), fixtures `history_53a71d5.json`, `base_53a71d5.json`, round-trip tests
appended to `test_series_cache.py`. `test_cache.py`, `test_base_cache.py` unchanged. Named tests: those two +
`test_series_cache.py` + `test_cache_corruption.py` + `tests/data/test_base_manager.py` + `test_base_client.py`
+ `test_token_detail.py` (the two `patch()`es) + `tests/screens/test_base_terminal_screen.py` + `-m guard tests`.

**WP-C — ocm + frenpet.** `ocm_cache.py` (delete `_coerce_point`, keep `version` 2, pre-v2 branch in `before_load`,
`holder_count` in `extra_payload`/`restore_extra`, `update_holder_count(now=)`), `frenpet_cache.py`
(`schema_version` 2, population deques stay public attributes via `SERIES`, per-pet dict via `coerce_keyed`,
`update(battle_rate=None)`), `frenpet_manager.py` (R1 only), `series_points.py` docstring, fixtures
`ocm_53a71d5.json` (version 2 with burn series) + `ocm_v1_53a71d5.json` (no version key) + `frenpet_53a71d5.json` +
`frenpet_v1_53a71d5.json`, round-trip tests. `test_ocm_cache.py`, `test_frenpet_cache.py` unchanged except the one
`battle_rate` regression test added to `tests/data/test_frenpet_manager.py`. Named tests: those + `test_series_cache.py`
+ `test_cache_corruption.py` + `tests/test_app_startup.py` + `tests/data/test_ocm_manager.py` +
`tests/screens/test_address_icons_everywhere.py -k ocm` + `tests/screens/test_frenpet_screens.py` + `-m guard tests`.

Sequence A → B → C, one implementer at a time (single writer), opus review per WP, ≤ 2 fix rounds, whole-branch
review at the end, suite once by the controller on the branch head.

**Tests (branch acceptance).** The five existing cache test files and `tests/test_app_startup.py` unchanged (`git diff
--stat` empty against `53a71d5`) except where a signature the plan changes forces it — none expected. Six fixture
round-trips. Mutation proofs per WP: `record()` keeping `None` → the R1 tests; dropping the dict guard → the `[]`
test; `extend` without `clear()` → the R7 test; `reference = time.time()` ignoring `now` → the `now=` test; removing
the `.tmp` cleanup → the atomic-write test. Every proof prints the mutated line before the run.

**Docs.** rules/data.md gains a "Series caches" paragraph under "Validate persisted series per point" (subclass
`SeriesCache`; declare `SERIES`; `record()` drops `None`; never add a version key to a file that has none, never
rename one); HANDOVER.md §3 item 6 marked half-done (SeriesCache landed, RpcPool = Branch 10, `manager_base` =
follow-up #44); the branch-order table row 9 corrected (`test_series_points.py` → `test_series_cache.py`);
follow-ups #41–#44 filed at planning time (below).

**Branch 9 WP-A outcome (2026-09-20).** Commit `d5fd9d7` on `refactor/series-cache`.
`data/series_cache.py` (new) + `dota_cache.py` and `cattown_cache.py` as subclasses +
`cattown_manager.py` (R1 only) + two fixtures + the generator script + two test files.

| file | before (`53a71d5`) | after | note |
|---|---|---|---|
| `maxpane_dashboard/data/series_cache.py` | — | **367** (137 code, 154 docstring, 18 comment, 58 blank) | new; the plan's "~150 lines" read as code lines |
| `maxpane_dashboard/data/cattown_cache.py` | 195 | **95** (33 code) | `update()` + three one-line getters |
| `maxpane_dashboard/data/dota_cache.py` | 193 | **92** (31 code) | ditto, plus the lane guard |
| `maxpane_dashboard/data/cattown_manager.py` | 302 | **306** | R1 only: two seeds `0`/`0.0` → `None`, +4 comment lines |
| `tests/data/test_series_cache.py` | — | **629** (38 tests) | probe + fixture round-trips + dota lane guard |
| `tests/data/test_cattown_manager.py` | — | **195** (5 tests) | new file; no cattown manager test existed |
| `tests/scripts/make_cache_fixtures.py` | — | **182** | provenance; never run by a test |
| `tests/fixtures/cache/{cattown,dota}_53a71d5.json` | — | 2 files | written by `53a71d5`'s own code |

Net for the two caches: 388 → 187 lines, with the duplicated persistence removed rather than moved
per-file. `tests/data/test_cache_corruption.py` is byte-unchanged (`git diff --stat` empty) and its
six `"Skipped"` assertions still pass against the base's reworded warning.

**Mutation proofs.** Every mutation was applied by an in-place string replace, the mutated line
printed with `grep -n`/`sed -n` *before* the run, and restored by inverse edit and `diff`'d against a
pre-mutation snapshot (`RESTORED IDENTICAL` for all four files; no `git checkout/stash/reset/restore/clean`).

| # | mutation | file(s) run | failing test(s) by name |
|---|---|---|---|
| a | `record()`: `if value is None: value = 0.0` (appends the sentinel) | `test_cattown_manager.py test_series_cache.py` | `test_record_drops_none_and_says_so`, `test_a_failed_raffle_read_records_no_ticket_point`, `test_a_competition_with_no_entries_records_no_leader_weight`, `test_the_failed_and_good_cycles_are_distinguishable_in_the_series` |
| b | `if not isinstance(payload, dict)` → `if False` | `test_series_cache.py test_cache_corruption.py` | `test_a_non_dict_payload_leaves_the_cache_untouched[list]`, `[str]`, `[null]`, `[int]` (`AttributeError: 'int' object has no attribute 'get'`) |
| c | `series.clear()` deleted, `extend` kept (R7) | `test_series_cache.py` | `test_load_clears_before_extending` |
| d | `reference = time.time()` ignoring `now=` | `test_series_cache.py` | `test_load_validates_points_against_now_not_the_wall_clock`, `test_a_spec_max_age_beats_the_calls_max_age`, `test_the_skipped_warning_names_the_count_and_the_cache`, `test_load_clears_before_extending`, `test_save_then_load_round_trips_the_series` |
| e | `os.remove(tmp_path)` cleanup deleted from the `except OSError` | `test_series_cache.py` | `test_a_failed_write_leaves_no_tmp_file_behind` |
| f | dota lane guard → `lanes.get(k)` + `0.0` for a missing lane | `test_series_cache.py test_dota_manager.py` | `test_a_missing_lane_records_nothing` |
| g | `cattown_manager`: `raffle_total_tickets: int \| None = 0` | `test_cattown_manager.py` | `test_a_failed_raffle_read_records_no_ticket_point`, `test_the_failed_and_good_cycles_are_distinguishable_in_the_series` |

**Render.** `python render_case.py cattown …` / `dota …` at `5869760` (before any code change) and at
the WP-A tree, both views at 170×50 and at the 143-column pin. `cmp` on all four pairs:
`IDENTICAL cattown.default.170x50`, `IDENTICAL cattown.default.pin-143x50`,
`IDENTICAL dota.default.170x50`, `IDENTICAL dota.default.pin-143x50` — the plan's expected diff (none).

**Where a failed read now yields `None`** (`grep -n`):
`maxpane_dashboard/data/series_cache.py:146-147` `if value is None:` / `return False` — the one
place a sentinel could enter a persisted series, and it refuses;
`maxpane_dashboard/data/cattown_cache.py:61-62` `leader_weight_kg: float | None = None,` /
`raffle_total_tickets: int | None = None,`;
`maxpane_dashboard/data/cattown_manager.py:105` `raffle_total_tickets: int | None = None` (was `0`)
and `:113` `leader_weight: float | None = None` (was `0.0`);
`maxpane_dashboard/data/dota_cache.py:79` `if lane_key in lanes:` — the pre-existing lane guard, kept.

**Deviations from the plan, and why.**
1. `_log_loaded(payload)` in the Design block became `_log_loaded(self, path, loaded)`. The line it
   replaces is `"Loaded CatTown cache from %s: %d total points"`; the payload alone cannot produce the
   loaded count, which is the number the log exists to state.
2. `_payload()` still reads `time.time()` for `saved_at`. The plan fixes `save_to_file(self, path)` and
   `_payload(self)`, so there is nowhere to inject a save clock without widening the signature the
   managers call. `saved_at` is write-side metadata no loader reads back; the injected-clock rule
   (rules/data.md) is about the load path, where the only wall-clock read is now the `now is None`
   fallback. The fixture script freezes `saved_at` after the fact rather than patching the clock.
3. The base always `coerce_points` + `clear()` + `extend()`; the old cattown/dota loaders had an
   `if not isinstance(points, list): continue` that *skipped* the clear, so a non-list value under a
   series key left the in-memory deque as it was. Reachable only on a load-after-update, which no
   manager does (both load in `__init__`), and R7 chooses clear-before-extend explicitly.
4. The base's warning is `"Skipped %d unusable or expired point(s) while loading %s %s"`, per the plan —
   the old text said `"unusable point(s)"` and named the cache inside the format string. The literal
   `"Skipped"` that `test_cache_corruption.py` binds is unchanged.
5. `SeriesSpec.max_age` and `allow_negative` are exercised by the probe subclass only: neither cattown
   nor dota needs them (R4 keeps both unwindowed). `coerce_keyed`, `before_load`, `extra_payload` and
   `restore_extra` likewise have no subclass caller until WP-B/WP-C, so each is pinned by a probe test
   here rather than shipped untested.
6. The generator script went to `tests/scripts/make_cache_fixtures.py` (brief) rather than the
   top-level `scripts/` where the capture tools live. It is test provenance, it reads nothing live, and
   `tests/scripts/` is not collected (pytest takes `test_*.py` only).

**Found, not fixed** — follow-ups #45–#47 in `docs/handover_followups_2026_09.md`.

**Branch 9 WP-A review (2026-09-20): Approved, 0 Critical, 0 Important, 5 Minor.** Compatibility proven both
ways against a `53a71d5` worktree: both fixtures load point-for-point identically in the old and the new class
(manager call shape, no `now=`), and the new class's save is byte-identical to the fixture with `saved_at`
stripped — key order, values, types, no version key; the fixture script re-run inside the worktree reproduced
both committed files md5-identical. R1 end to end: failed raffle read and empty entry list record nothing, a
genuine `0` still records `(ts, 0.0)`, the manager diff is the two R1 hunks only, and `SparklinePanel` renders
the now-empty series as `EMPTY_TEXT` rather than a zero baseline. Contract matches the Design block member for
member; no undisclosed deviation. Seven mutations re-run by the reviewer; fixture round-trips bite. Renders
reproduced independently, identical ×4. Minors, carried into WP-B's brief: M1 the R5 `[]` test drives `_Probe`
only — feed `[]` to each real class as it migrates; M2 a series key holding a non-list is cleared with no log
line (`series_cache.py:336-342`) — the base gets one warning naming the key; M3
`test_a_cache_with_no_version_key_reads_version_1` asserts the wrong key name (rigor only, the shape is bound
elsewhere); M4 the `VERSION_KEY is not None` guard on the read path is an equivalent mutant (note, no change);
M5 a `-> int` annotation on a `int | None` fake. Branch-level Docs items (rules/data.md paragraph, HANDOVER §3
item 6, table row 9) remain for the closure commit. 98 + 6 + 192 passed.

**Branch 9 WP-B outcome (2026-09-20).** Commit `2f5f3b7` on `refactor/series-cache`.
`data/cache.py` (bakery) and `data/base_cache.py` as `SeriesCache` subclasses + three
additions to the base + two pre-branch fixtures + the generator extended + tests appended.

| file | before (`53a71d5`) | after | note |
|---|---|---|---|
| `maxpane_dashboard/data/cache.py` | 237 (114 code, 68 docstring, 18 comment, 37 blank) | **202** (95 code, 55 docstring, 17 comment, 35 blank) | `SERIES = ()`; the whole payload rides on the two hooks |
| `maxpane_dashboard/data/base_cache.py` | 379 (209 code, 84 docstring, 29 comment, 57 blank) | **379** (186 code, **108** docstring, 27 comment, 58 blank) | -23 code, +24 docstring: the persistence went, the reasoning stayed |
| `maxpane_dashboard/data/series_cache.py` | 367 (157 code) at WP-A | **417** (180 code) | `SeriesSpec.key`, `SIZE_NOUN`, the `restore_extra` inputs, M2's warning |
| `tests/data/test_series_cache.py` | 629 (38 tests) at WP-A | **1027** (53 tests) | +15: two fixture round-trips, R5 on four real classes, R7, R1/R3, R4 both ways, M2 |
| `tests/scripts/make_cache_fixtures.py` | 182 at WP-A | **383** | `make_bakery()`, `make_base()` |
| `tests/fixtures/cache/{history,base}_53a71d5.json` | — | 2 files | written by `53a71d5`'s own code |

Net for the two caches: 616 → 581 total lines but **323 → 281 code lines**, and the
duplicated persistence (atomic write, open/decode guard, per-point validation, the
"Skipped" warning) is gone rather than moved. `tests/data/test_cache.py`,
`test_base_cache.py` and `test_cache_corruption.py` are byte-unchanged
(`git diff --stat 53a71d5 --` empty for all three) — they are the acceptance, and
`test_base_cache.py:176-183` (load *then* update) is untouched by R7 as the brief predicted.

**The `SeriesSpec.key` decision: the field was added** (the brief's preferred option).
Base's three overview deques are the attributes `volume_history` / `eth_price_history` /
`trade_count_history` but have always been *persisted* as `overview_volume` /
`overview_eth_price` / `overview_trade_count`, and renaming either half empties every
existing `~/.maxpane/base_cache.json`'s sparklines on the next load. The alternative —
overriding `_payload` and the SERIES restore loop in `base_cache.py` — would have meant
not declaring the three as `SERIES` at all, which is the mechanism this branch exists to
share. The field is append-only (`key: str | None = None`, JSON key defaults to `name`),
its whole implementation is the `json_key` property, and it is pinned by the base fixture
round-trip: mutation (e) reddens six tests. **Key order** is a second, separate problem —
the base writes declared series *before* `extra_payload`, and this file has always led
with `histories`. That is handled locally, by a six-line `_payload` override in
`base_cache.py`, rather than by another base-class knob, because ocm wants `holder_count`
*after* its series and frenpet wants `histories` *before* its three: no single base
ordering serves WP-C, so the base's order stays as WP-A's reviewer approved it.

**Mutation proofs.** Each mutation was an in-place string swap by a helper that refuses a
non-unique match, the mutated line printed with `grep -n`/`sed -n` *before* the run, and
restored by the inverse swap and `diff`'d against a pre-mutation snapshot (`RESTORED
IDENTICAL` for all three files; no `git checkout/stash/reset/restore/clean`).

| # | mutation | file(s) run | failing test(s) by name |
|---|---|---|---|
| a | `cache.py` `restore_extra`: `if not good: continue` deleted (an all-expired bakery gets an empty deque) | `test_series_cache.py test_cache.py` | `test_a_bakery_whose_points_all_expired_is_left_untracked`, `TestStaleHistoryIsNotRestored::test_a_fully_expired_bakery_is_not_tracked_at_all` |
| b | `cache.py` `update`: the season-reset `dq.clear()` replaced by `pass` | `test_cache.py test_series_cache.py` | `TestSeasonResetClearsHistory::test_collapse_to_near_zero_clears_the_bakery` |
| c | `base_cache.py`: `ts = timestamp or time.time()` (R3 reverted) | `test_series_cache.py test_base_cache.py` | `test_record_token_honours_a_zero_timestamp` |
| d | `series_cache.py`: `series.clear()` deleted, `extend` kept (R7) | `test_series_cache.py test_base_cache.py test_cache_corruption.py` | `test_base_overview_load_replaces_rather_than_concatenates`, `test_load_clears_before_extending` |
| e | `SeriesSpec.json_key` returns `self.name` (the `key=` ignored) | `test_series_cache.py test_base_cache.py test_cache_corruption.py test_base_terminal_screen.py` | `test_base_loads_a_pre_branch_cache_file`, `test_wp_b_resaves_the_pre_branch_file_key_for_key[base]`, `test_base_overview_load_replaces_rather_than_concatenates`, `test_base_restores_a_thirty_day_old_point`, `test_a_series_key_that_is_not_a_list_is_named_in_a_warning`, `test_base_cache_survives_corrupt_points` |
| f | `series_cache.py`: the M2 non-list warning replaced by `pass` | `test_series_cache.py` | `test_a_series_key_that_is_not_a_list_is_named_in_a_warning` |
| g | `series_cache.py`: `if not isinstance(payload, dict)` → `if False` (R5) | `test_series_cache.py test_cache.py test_base_cache.py test_cache_corruption.py` | `test_an_empty_list_payload_leaves_a_real_cache_untouched[bakery]`, `[base]`, `[cattown]`, `[dota]` (`AttributeError`), plus the four `test_a_non_dict_payload_leaves_the_cache_untouched` cases |
| h | `base_cache.py` `record_overview_point`: `total_volume or 0.0` etc. (the sentinel) | `test_series_cache.py test_base_cache.py test_base_manager.py test_base_terminal_screen.py` | `test_record_overview_point_skips_none_and_keeps_a_real_zero`, `test_eth_failure_records_no_price_point`, `test_empty_trending_records_no_volume_point`, `test_outage_then_recovery_does_not_report_false_rising`, `test_no_zero_ever_reaches_the_persisted_file` |

**Compatibility, both directions.** The same probe run against a `53a71d5` worktree
(`PYTHONPATH` prepended) and against the branch head produced identical output: both
fixtures load point-for-point the same into the old and the new class through the
managers' call shape (no `now=`), and the re-saved key *list* is identical —
`['saved_at', 'max_history', 'histories']` for bakery and
`['saved_at', 'max_history', 'histories', 'overview_volume', 'overview_eth_price',
'overview_trade_count']` for base, with no version key. Re-running the extended generator
inside the worktree reproduced the two WP-A fixtures md5-identical, which is the
determinism claim for the two new ones.

**Render.** `python render_case.py bakery …` / `base …` at `f2767b5` (before any code
change) and at the WP-B tree, both at 170×50 and at the 143-column pin. `cmp` on all four
pairs: `IDENTICAL bakery.default.170x50`, `IDENTICAL bakery.default.pin-143x50`,
`IDENTICAL base.default.170x50`, `IDENTICAL base.default.pin-143x50` — the plan's expected
diff (none).

**Where a failed read yields `None`** (`grep -n`):
`maxpane_dashboard/data/series_cache.py:166` `if value is None:` — the one place a sentinel
could enter a persisted series, and it refuses;
`maxpane_dashboard/data/base_cache.py:227` `total_volume: float | None,` and the two
siblings, folded onto `record()` so the skip is the shared rule rather than three local
`if`s; `maxpane_dashboard/data/base_cache.py:197`
`ts = time.time() if timestamp is None else timestamp` — the R3 half of the same idea
applied to a *timestamp*: `0.0` is a value, not an absence.

**Deviations from the plan/brief, and why.**
1. `restore_extra(self, payload, *, now)` became
   `restore_extra(self, payload, *, path, now, max_age=None)`. Both bakery and base need
   `path` for warnings that name the offending file (base's "least-recently-updated" line
   is bound by `test_base_cache.py:128`), and bakery needs `max_age` because its window is
   *caller*-supplied (`manager.py:67-69`), not declared per series. The two probe
   subclasses in `test_series_cache.py` were updated to match; nothing else implemented the
   hook.
2. `SIZE_NOUN` was added to the base. The save log is `"%s saved to %s (%d points)"` and
   prints `history_size`, which for these two caches counts bakeries and tokens. Leaving it
   would have shipped a wrong noun on a number in a log file; the fix is one class attribute
   and one word per subclass, and it serves frenpet ("pets") at WP-C.
3. Key order is a `_payload` override in `base_cache.py`, not a base-class facility. Reason
   in the decision paragraph above: ocm and frenpet want opposite orders, so a shared knob
   would be guesswork until WP-C measures them.
4. Base now degrades *per key* rather than abandoning the file. Previously a non-dict
   `histories` returned early, so the three `overview_*` series were skipped too; with the
   base class they are restored first and only the keyed half is abandoned. That is the same
   strengthening as R5, one level down, and it is why both subclasses carry a
   `_loaded_*: int | None` sentinel: `_log_loaded` stays silent when the load bailed, so the
   "Loaded … 0 tokens" line the old code never printed is still not printed. Untested on
   purpose — follow-up #49.
5. Log wording moved with `NOUN`. Bakery's is `"cache history"`, which keeps
   `"Failed to save cache history: %s"` verbatim and the closing
   `"Loaded cache history from %s: %d bakeries, up to %d points each"` verbatim via a
   `_log_loaded` override; the three lines that embedded the noun mid-sentence now read
   `"No cache history file to load"`, `"cache history file %s has unexpected format"` and
   `"… while loading cache history %s"` (was `"No cache file …"`, `"Cache file %s …"`,
   `"… while loading cache %s"`). Base's `NOUN` reproduces every one of its lines
   unchanged. The literals tests bind — `"Skipped"` (six assertions in
   `test_cache_corruption.py`), `"least-recently-updated"`, `"unexpected format"`,
   `"truncating"` — all survive.
6. The base's skipped warning now says `"unusable or expired point(s)"` for base too (it
   said `"unusable point(s)"`); WP-A already made that the one wording.

**Found, not fixed** — follow-ups #48–#50 in `docs/handover_followups_2026_09.md`: the
bakery cache's keyed dict is merged rather than replaced on load (the keyed twin of R7,
unreachable today, decide it once for all three keyed caches at WP-C); a non-dict
`histories` is untested for bakery and base; `test_base_cache.py:172` asserts a bound
(`<= 2`) where it means a value. All three Minor, all Tier 0 when their file is next
touched.

**Branch 9 WP-B review (2026-09-20): Approved, 0 Critical, 0 Important, 6 Minor.** Byte-level compatibility
proven both ways against a `53a71d5` worktree through the managers' exact call shapes: keyed dicts key-for-key
and in order, every point identical, re-saved JSON text equal to the fixture with `saved_at` normalised; all
four fixtures regenerate md5-identical from the pre-branch code. The base-terminal migration is real (no
`json`/`os`/`coerce_points` import, no persistence method left; 23 code lines out, 24 docstring lines in).
Six keyed-series probes (untracked-when-expired, season reset, LRU order, load cap, case-duplicate pass,
per-update truncation) agree pre/post. `SeriesSpec.key` is default-preserving for cattown/dota. Five
reviewer mutations bit the named tests, incl. key order bound by exactly one assertion. Minors: M1 base's
non-dict-`histories` warning understates that the overview series were restored (folded into #49); M2 #49
is a behaviour change for base, not only a test gap (folded in); M3 `record_token` has no production caller,
the R3 test docstring implies one; M4 `test_an_empty_list_payload_leaves_a_real_cache_untouched` asserts a
state that already held before the load — record a point first; M5 bakery log wording lowercase-initial
after the `NOUN` move; M6 the `_loaded_*` sentinel is a hidden contract between `restore_extra` and
`_log_loaded` — one sentence in the base's hook docstring. M3–M6 carried into WP-C's brief. 188 + 3 + 7 +
192 passed.

**Branch 9 WP-C outcome (2026-09-20).** Commit `032a9df` on `refactor/series-cache`.
`data/ocm_cache.py` and `data/frenpet_cache.py` as `SeriesCache` subclasses +
`frenpet_manager.py` (R1 only) + the `series_points.py` docstring the branch retires +
two base-class docstring notes + four pre-branch fixtures + the generator extended +
tests appended.

| file | before (`53a71d5`) | after | note |
|---|---|---|---|
| `maxpane_dashboard/data/ocm_cache.py` | 349 (156 code, 108 docstring, 28 comment, 57 blank) | **315** (89 code, 133 docstring, 41 comment, 52 blank) | **-67 code**: persistence, `_coerce_point` and `_CLOCK_SKEW_TOLERANCE_SECONDS` all gone |
| `maxpane_dashboard/data/frenpet_cache.py` | 334 (140 code, 124 docstring, 21 comment, 49 blank) | **328** (113 code, 133 docstring, 33 comment, 49 blank) | -27 code, +9 docstring: the persistence went, the schema story stayed |
| `maxpane_dashboard/data/frenpet_manager.py` | 581 (285 code) | **593** (288 code) | R1 only: one name split into two, +3 code, +9 comment |
| `maxpane_dashboard/data/series_cache.py` | 417 at WP-B | **434** | **0 code lines**: M6's two hook-docstring notes only |
| `maxpane_dashboard/data/series_points.py` | 133 (58 docstring) | **138** (63 docstring) | docstring only: the debt it named is paid |
| `tests/data/test_series_cache.py` | 1027 (53 tests) at WP-B | **1475** (67 tests) | +14: four fixture round-trips, the two v1 files, R3, R4-per-series, #48 x3, M4 widened to six classes |
| `tests/data/test_frenpet_manager.py` | 632 (24 tests) | **729** (27 tests) | +3: the R1 regression, both directions plus a genuine zero |
| `tests/scripts/make_cache_fixtures.py` | 383 at WP-B | **554** | `make_ocm()`, `make_ocm_v1()`, `make_frenpet()`, `make_frenpet_v1()` |
| `tests/fixtures/cache/{ocm,ocm_v1,frenpet,frenpet_v1}_53a71d5.json` | — | 4 files | written by `53a71d5`'s own code (the two v1 files derived from them, see below) |

Net for the two caches: 683 → 643 total lines but **296 → 202 code lines**, and the last
private `coerce_point` copy in the package is gone. `tests/data/test_ocm_cache.py`,
`test_frenpet_cache.py`, `test_cache_corruption.py` and `tests/test_app_startup.py` are
byte-unchanged (`git diff --stat 53a71d5 --` empty for all four) — they are the acceptance.

**The pre-v2 mechanism: `before_load` takes the key off the payload.** The old loader
built its restore list per version and simply left `burn_history` out of it; the base
class has one list, driven by `SERIES`, so "skip this series this time" had to be said
some other way. Three candidates: a per-spec skip hook on the base, a version-dependent
`SERIES` override, or removing the key. The third won because it needs nothing from the
base and cannot be half-done: clearing the deque in `before_load` is *undone one line
later* by the restore loop, which reads `payload["burn_history"]` and extends from
whatever a stale or hand-edited file holds there — and version gating, not key presence,
is what decides this (`test_ocm_cache.py::test_v1_file_with_an_injected_burn_history_is_ignored`
has pinned that since the burn series shipped). The base's `before_load` docstring already
anticipated payload mutation ("a series cleared **or a key migrated**"). A missing key
coerces to "no points", and the base's clear-before-extend empties the deque, so the two
halves of the old behaviour both survive. Mutation (c) below is the proof: clearing
instead of popping reddens two tests.

The one thing that could not follow it is the *message*. `before_load` is not handed
`path`, and the file's name is the actionable half of "OCM cache %s is version %d
(pre-burn-series)", so both caches record the version in `before_load` and log from
`restore_extra`, the first hook that knows both the path and (for frenpet) the pet count
the sentence quotes. Both hooks still run ahead of the "Skipped ..." warning and the
closing info line, so the log *order* is unchanged — confirmed line for line by the
worktree comparison below.

**Mutation proofs.** Each mutation was an in-place string swap by a helper that refuses a
non-unique match, the mutated line printed with `grep -n`/`sed -n` *before* the run, and
restored by the inverse swap and `diff`'d against a pre-mutation snapshot (`RESTORED
IDENTICAL` for all four files; no `git checkout/stash/reset/restore/clean`).

| # | mutation | file(s) run | failing test(s) by name |
|---|---|---|---|
| a | `ocm_cache.py`: `VERSION = 3` | `test_ocm_cache.py test_series_cache.py` | `test_save_load_round_trip` (the `payload["version"] == 2` pin), `test_stale_points_are_dropped`, `test_future_dated_points_are_dropped`, `test_ocm_loads_a_pre_branch_cache_file`, `test_wp_c_resaves_the_pre_branch_file_key_for_key[ocm]`, `test_ocm_windows_each_series_by_its_own_max_age` |
| b | `frenpet_cache.py`: `VERSION_KEY = "version"` | `test_frenpet_cache.py test_series_cache.py` | `TestFrenPetCachePopulationPersistence::test_save_stamps_the_schema_version`, `test_wp_c_resaves_the_pre_branch_file_key_for_key[frenpet]` |
| c | `ocm_cache.py` `before_load`: `payload.pop(...)` replaced by `self.burn_history.clear()` (the restore loop then puts it back) | `test_ocm_cache.py test_series_cache.py` | `test_v1_file_with_an_injected_burn_history_is_ignored`, `test_a_v1_ocm_file_carrying_a_burn_history_still_starts_empty` |
| d | `ocm_cache.py` `_append_burn_sample`: the `unchanged and too_soon` dedupe removed | `test_ocm_cache.py test_series_cache.py` | `test_mints_alone_do_not_extend_the_burn_series`, `test_a_changed_burn_count_is_recorded_immediately` |
| e | `frenpet_manager.py`: `battle_rate=global_battle_rate` (the `0.0` sentinel restored) | `test_frenpet_manager.py` | `TestFrenPetManagerBattleRateSentinel::test_a_failed_attacks_read_records_no_battle_rate_point` |
| f | `ocm_cache.py`: `update_holder_count` ignores `now=` | `test_ocm_cache.py test_series_cache.py test_ocm_manager.py` | `test_update_holder_count_honours_an_injected_clock` |
| g | `series_cache.py` `_payload`: `[list(pt) …]` → `[[float(ts), float(val)] …]` (frenpet's old spelling, applied base-wide) | `test_frenpet_cache.py test_series_cache.py test_ocm_cache.py test_cache_corruption.py` | **none — 134 passed.** Expected: every point in these deques is already a `tuple[float, float]` (`record()` and `coerce_points` both cast), so the two spellings emit identical JSON. The round-trip tests compare the re-saved file to the fixture key for key and value for value and see no difference, which is the claim. |
| h | `ocm_cache.py`: the `burn_history` spec's `max_age=BURN_WINDOW_SECONDS` removed | `test_ocm_cache.py test_series_cache.py` | `test_stale_points_are_dropped`, `test_ocm_windows_each_series_by_its_own_max_age` |

Two expectations from the brief did *not* hold and are recorded rather than engineered
away. (a) also reddens `test_stale_points_are_dropped` and `test_future_dated_points_are_dropped`,
because a v3 class reading a v2 file drops the burn series those two assert on — the same
damage a real bump would do to a user. (c) does **not** redden
`test_ocm_loads_a_pre_branch_v1_cache_file`: the v1 fixture has no `burn_history` key at
all (that is what makes it a v1 file), so "restore it anyway" restores nothing. The test
that tells the two mechanisms apart has to inject the key, which is why
`test_a_v1_ocm_file_carrying_a_burn_history_still_starts_empty` exists alongside the
fixture test rather than instead of it.

**Compatibility, both directions.** One probe, run unchanged against a `53a71d5` worktree
(`PYTHONPATH` prepended) and against the WP-C tree, loading all four fixtures through the
managers' exact call shapes (`OCMCache.load_from_file(path)`, `FrenPetCache.load_from_file(path,
now=...)`) with `time.time` pinned to the fixtures' clock: **`diff` empty**. Every series
point for point, the per-pet dict key for key, `holder_count`, `history_size`, and every
log line — including `"OCM cache … is version 1 (pre-burn-series)…"`, `"FrenPet cache … is
schema v1; per-pet history (3 pets) kept in full…"` and both closing `"Loaded …"` lines —
identical in wording, arguments and order. Re-saving each v2 fixture reproduces it key for
key **in order** with only `saved_at` differing. Re-running the extended generator inside
the worktree reproduced the four WP-A/WP-B fixtures md5-identical, which is the determinism
claim for the four new ones.

The two v1 fixtures are **derived, not generated**, and the script says so in
`make_ocm_v1`/`make_frenpet_v1`: the pre-burn-series and pre-schema-2 code is older than
`53a71d5` and exists in no tree this branch can check out, so each is its v2 sibling minus
exactly the keys that version never wrote (`version` + `burn_history`; `schema_version` +
the three population series), key order otherwise untouched — the shape the hand-written v1
payloads in `test_ocm_cache.py` and `test_frenpet_cache.py` have always described.

**Render.** `python render_case.py ocm …` / `frenpet …` / `frenpet_full …` /
`frenpet_wallet …` / `frenpet_perf …` before any code change and again on the WP-C tree,
every view of every case at 170x50 and at the 143-column pin. `cmp` on all 16 pairs:
`IDENTICAL ocm.default.170x50`, `IDENTICAL ocm.default.pin-143x50`,
`IDENTICAL frenpet.default.170x50`, `IDENTICAL frenpet.default.pin-143x50`,
`IDENTICAL frenpet_full.default.{170x50,pin-143x50}`,
`IDENTICAL frenpet_full.view-2.{170x50,pin-143x50}`,
`IDENTICAL frenpet_full.view-3.{170x50,pin-143x50}`,
`IDENTICAL frenpet_full.view-4.{170x50,pin-143x50}`,
`IDENTICAL frenpet_wallet.default.{170x50,pin-143x50}`,
`IDENTICAL frenpet_perf.default.{170x50,pin-143x50}` — the plan's expected diff (none).

**Where a failed read yields `None`** (`grep -n`):
`maxpane_dashboard/data/frenpet_cache.py:134` `self, snapshot: FrenPetSnapshot, battle_rate: float | None = None`
— the default moved from `0.0` to `None`, so a caller that cannot measure the rate says so
by omission as well as by argument;
`maxpane_dashboard/data/frenpet_cache.py:156` `self.record("battle_rate_history", ts, battle_rate)`
— folded onto the base's `record()`, which is the one place the sentinel is refused;
`maxpane_dashboard/data/frenpet_manager.py:165` `measured_battle_rate: float | None = None`
and `:176` `self.cache.update(snapshot, battle_rate=measured_battle_rate)` — the persisted
value; `:171-172` `global_battle_rate = (0.0 if measured_battle_rate is None else …)` — the
*display* value, deliberately unchanged (follow-up #43).
`maxpane_dashboard/data/ocm_cache.py:153-155` — the three sparkline appends now go through
`record()` too; OCM's own `None` discipline stays where it was, in
`ocm_manager.py:117-128`, which skips `update()` entirely on `read_failures`.

**Follow-up #48 is closed: all three keyed caches keep merging.** Bakery, base and frenpet
all assign per key on load and none of them clears the dict first, so a key tracked in
memory but absent from the file keeps its deque. Every caller loads in `__init__` before
its first `update()`, so nothing live changes either way — which is exactly why it is now
pinned (`test_a_keyed_load_merges_rather_than_replaces[bakery|base|frenpet]`) instead of
left to drift into three different answers. It is the keyed twin of R7 and the opposite
decision, because R7 governs series whose identity is fixed while these dicts' keys arrive
and leave.

**Deviations from the plan/brief, and why.**
1. The pre-v2 mechanism and the move of both version messages into `restore_extra`, above.
2. `FrenPetCache`'s save log lost its second number. The base's line is
   `"%s saved to %s (%d %s)"` and prints `history_size` with `SIZE_NOUN`, so it now reads
   `"FrenPet cache saved to … (3 pets)"` where it used to read
   `"… (3 pets, 18 population points)"`. `SIZE_NOUN = "pets"` is the brief's instruction and
   the alternative is a second base-class knob for one log line in one cache. Filed as #51.
   No test binds the literal (`rg "population points"` finds only the two lines in that file).
3. `FrenPetCache` degrades *per key* on a malformed `histories`, as base and bakery already
   do since WP-B. Pre-branch the loader returned before the population block, so those three
   series kept whatever the session had; now they are restored from the file and only the
   keyed half is abandoned. Same strengthening, one level down, and the `_loaded_pets`
   sentinel keeps `_log_loaded` silent so the "Loaded … 0 pets" line the old code never
   printed is still not printed. Folded into #49, which now names all three.
4. `OCMCache.load_from_file` gained `now=` and `max_age=` from the base (R2). The manager's
   call is unchanged and every ocm series names its own window, so `max_age=` is inert here;
   `now=` is what let `test_ocm_windows_each_series_by_its_own_max_age` state exact expected
   points instead of a tolerance around the wall clock.
5. `update()` on both caches now floats through `record()` rather than `deque.append`, so a
   `None` is *droppable* on every series, not only on frenpet's battle rate. No production
   caller passes `None` for the other five, and the pre-existing `None` discipline
   (`ocm_manager.py:117-128` skipping the whole update) is untouched.
6. `_append_burn_sample` stays a hand-written append. Its dedupe and its prune are specific
   to a cumulative counter sampled far more often than it moves, and `record()` has no
   vocabulary for either; the brief says so and mutation (d) shows the behaviour is pinned.
7. M4 (`test_an_empty_list_payload_leaves_a_real_cache_untouched`) was widened past the
   brief: the seed-then-load shape the reviewer asked for is applied to **six** classes, not
   four, because ocm and frenpet arrive in the same commit and the parametrisation was being
   rewritten anyway.
8. M5 (bakery log wording) was left alone, as the brief allows.

**Found, not fixed** — follow-ups #51-#53 in `docs/handover_followups_2026_09.md`, all Minor.

**Branch 9 WP-C review (2026-09-20): Needs fixes 0 Critical, 1 Important; fix round 1 `47ef487`; re-review
ADDRESSED.** Compatibility proven byte-level on all four fixtures both ways through the managers' call shapes
(int pet keys in order, `holder_count`, raw JSON text identical bar `saved_at`); the live pre-v2 shapes load
identically old vs new; a nine-row version-value table shows only `"2"`/`2.0` moved, toward keeping the burn
series (M1 → folded into #54). R1 hunk only in the manager; `global_battle_rate` identical pre/post in every
case; the four-manager shared cache covered by the frozen `test_app_startup.py`. Six reviewer mutations bit.
I1: the three new manager tests built a bare `FrenPetManager`, whose `__init__` loads the real
`~/.maxpane/frenpet_cache.json`, and were red on the owner's machine — an autouse fixture now points
`fm._CACHE_FILE` at `tmp_path` (verified with the real cache copied into a temp HOME: 3 failed → 51 passed;
fixture disabled → the same 3 red). M2: `_compute_battle_rate` answers `0.0` for "cannot compute" and that
still reaches the series — pre-existing, outside R1's scope, docstring corrected, filed #54 (Important, Tier 1).
M3: base-emitted log lines now carry the `series_cache` logger name (precedent from WP-A/B; the NOUN in the
message is the grep that works). Branch Docs landed in the closure commit: rules/data.md "Series caches"
paragraph, HANDOVER §3 item 6 half-done, table row 9 (at planning).

**Whole-branch review (2026-09-20, `git diff 53a71d5..521bd59`, opus): Approved — 0 Critical, 0 Important,
9 Minor.** Environment-dependent tests (`test_series_cache.py`, `test_cattown_manager.py`,
`test_frenpet_manager.py`) 99 passed under an empty temp HOME, a temp HOME holding the owner's 19
`~/.maxpane/*.json` and the real HOME read-only (every mtime unchanged afterwards). Fuzz: 6 classes × 33
payloads + 4 file shapes = 198 cases, zero exceptions escaped `load_from_file`, zero sentinel points; a
392-case old-vs-new equivalence run against a `53a71d5` worktree differs only in the documented R5/R7/#49
buckets (filed as #59 for reference). All eight fixtures regenerate md5-identical from the worktree; the
six acceptance test files and `CLAUDE.md` are byte-unchanged; twelve render pairs (six dashboards × 170 and
143 columns) identical old vs new; every manager call site resolves on the migrated classes; the shared
FrenPet cache hold in `app.py` covered by the frozen `test_app_startup.py`. Three cross-WP mutations: the
version key never written → 5 red across `test_series_cache.py` and both frozen ocm/frenpet files; base
forwarding `max_age` to the keyed half → nothing red (#56); bakery's dead-key rule imposed on all three →
3 red, none frenpet's (#57). Docs Minors folded into this closure: `rules/data.md` no longer claims a
byte-identical re-save (parsed JSON with `saved_at` excused) and names the two derived v1 fixtures (M6);
table row 9 now carries the measured `+179 net` instead of the estimate (M7); #46 and #42 anchors re-taken
on the head (M8); #49 reads "Tier 0 per file" (M9). Code Minors filed: #55 `get_latest() -> Any` on six
caches (with M5 `allow_negative` unused), #56, #57, #58 `_loaded_version` naming. Reviewer confirmed
follow-ups #45 and #54 are pre-existing zeros the branch strictly narrows, not blockers.

## Branch 10 — `refactor/rpc-pool` (option B: classifier hoist + library seams; three work packages)

Spec: HANDOVER.md §3 item 6, second half. Survey 2026-09-20 (scratchpad `branch10_survey.md`, 503 lines;
anchors below are against main `269beda`). Tier 2: a new shared `data/` module, nine clients, > 6 files.
**Owner decision 2026-09-20: option B**, after the survey showed the HANDOVER's full `RpcPool` would
override nine individually tested error policies (not five — `rpc_common.py`'s MEDI-17 table predates
curator, surf, surf_pool4, curator_nft_holders and fwa_logs) and that its "~700 lines removed" is
reachable only by deleting policy the outage-born tests protect. **Owner constraint 2026-09-20:** the
data layer will also serve other frontends (web sites); `data/` + `analytics/` must work as an
importable library — configuration injected at construction, no import-time environment reads, no
module-global mutable state. The survey found `data/` + `analytics/` already import nothing from
Textual/rich/widgets/screens/app (AST-verified); the obstacles are constructor seams (§9c/e below).

**Facts.** Five boolean endpoint-limitation tables: `ttt_client.py:268-290` (21 fragments),
`curator_client.py:225-232` (22), `surf_client.py:1101-1106` (20), `surf_pool4_client.py:343-348` (20,
byte-identical to surf, bound by the agreement test `test_surf_pool4_client.py:311`), `cattown_client.py:66-82`
(15, a **Base** pool with 11 fragments no Ethereum client carries). The four Ethereum tables differ only
by `personal token` (ttt), `api key` (dropped by curator with no note — drift) and curator's drpc route
triplet (`can't route` / `cannot route` / `route your request`, `curator_client.py:230`). Three range tables:
`curator_client.py:248-254` (11: four span fragments + 7 result-count/response-size fragments, justified
at `:241-247` by THE LIST's ~4.3 logs/block), `surf_client.py:1108-1114` and `surf_pool4_client.py:350-362`
(5 each, identical; `exceeds limit of` is mevblocker's honest cap). Four copies of
`_MALFORMED_REQUEST_CODES = {-32600,-32601,-32602,-32604,-32700}` (`ttt:295`, `curator:256`, `surf:1116`,
`surf_pool4:364`; cattown has none). Predicates: `_looks_like_endpoint_limitation` ×5 (ttt `:298`, curator
`:259`, surf `:1119`, surf_pool4 `:407`, cattown `:104`), `_is_range_limitation` ×3 (curator `:269`, surf
`:1129`, surf_pool4 `:424-459` — the only one taking `requested_span`, which encodes rules/data.md's drpc
archive-depth rule "rotate, do not shrink" via `_named_block_limit` `:387-404`). Kind-based classifiers
`talismans_client._classify_rpc_error:428-481` and `fwa_logs._classify_rpc_error:1382-1434` with their own
marker tables (`talismans:373-388`, `fwa_logs:1318-1327`; fwa_logs has **no** `_RANGE_CAP_MARKERS`, it inlines
the check at `:1415` — HANDOVER is half wrong there) are **out of scope**: they return typed kinds their
pagers consume as data. Seven semantic flips a naive union would ship (survey §1e): non-dict `err` → `True`
in four clients, `False` in cattown (`:106`, untested); `query returned more than` = rotate in cattown,
shrink in curator; `timeout` = rotate in four, shrink in talismans/fwa_logs; drpc `code 35` = shrink in
talismans/fwa_logs, rotate-when-limit-met in surf_pool4; `rate limit` = rotate ×4, retry-same-endpoint in
fwa_logs; `exceeds` vs cattown's `exceeded`. Callers and what they do on each answer: survey §2. Tests
pinning this area: 773 across seven client files (`test_ttt_client.py` 101, `test_curator_client.py` 115,
`test_surf_client.py` 208, `test_surf_pool4_client.py` 180, `test_cattown_client.py` 39,
`test_talismans_client.py` 52, `test_fwa_logs.py` 78) + `test_rpc_shared.py` 52 (its `:375` asserts each
client still defines `_rpc`; `:444` asserts the MEDI-17 rationale is in `rpc_common.__doc__`; `:277-294`
guards `ENDPOINT_DEAD_CODES` re-declaration but `ALL_CLIENTS:58-67` scans only `*_client.py`). Fixtures:
`tests/fixtures/surf/pool4/rpc_error_states.json` (4 probes), `log_range_messages.json` (10 probes; drpc
answers the identical "ranges over 10000 blocks" sentence at spans 403200/10000/2400/300 and succeeds at
10), `tests/fixtures/fwa/rpc_errors.json` (14), talismans' inline `_LIVE_ERRORS`
(`test_talismans_client.py:471`), `MANIFEST.json` (any new pool4 fixture must be listed or
`scripts/capture_pool4.py --dry-run` drifts). Library seams (§9): import-time env reads `ocm_client.py:48`
(module constant, ctor default `:121`), `cattown_client.py:167` (class attr, ctor default `:187`),
`frenpet_client.py:81`; `_CACHE_DIR = Path.home() / ".maxpane"` in eight managers (`manager.py:30`,
`base_manager.py:30`, `dota_manager.py:23`, `cattown_manager.py:37`, `frenpet_manager.py:39`,
`talismans_manager.py:60`, `ttt_manager.py:62`, `ocm_manager.py:31`) with no ctor override except ocm's
`cache_file`; seven managers construct their client inside `__init__` with no seam (`BaseManager:55/61`,
`CatTownManager:50/51`, `DOTAManager:39/40`, `FrenPetManager:74/80,82`, `DataManager:54/55`,
`TalismansManager:84/85`, `TTTManager:109/110-111`); talismans' log pool is not injectable
(`talismans_client.py:730` hard-references `_LOG_RPCS`). `fwa_logs.py` re-declares `_ENDPOINT_DEAD_CODES`
as a bare set (`:260`), re-implements `jsonrpc_payload` (`:1645-1652`) and `pace` (`:1581-1585`) and
hand-rolls the `OwnedHttpClient` lifecycle (`:1490-1495`) — the MEDI-17 hoist missed it because it is not
a `*_client.py`. Pacing is per instance everywhere (`_last_rpc_at` ×9, `rpc_common.pace` pure); no
module-global rotation index; `rpc_common.py` imports only stdlib + httpx (no circular hazard as long as
the new module never imports a client).

**Design — `data/rpc_classify.py` (~120 lines incl. attribution comments, one owner, lands first).**

```python
# Every fragment keeps the provider/date comment it carries today; attribution is the point.
ETH_ENDPOINT_LIMITATION_FRAGMENTS: tuple[str, ...]   # union of ttt/curator/surf/surf_pool4 = 24
BASE_ENDPOINT_LIMITATION_FRAGMENTS: tuple[str, ...]  # cattown's 15, unchanged (Base providers phrase differently)
RANGE_CAP_FRAGMENTS: tuple[str, ...]                 # the 5 span fragments (surf / surf_pool4 / curator)
RESULT_CAP_FRAGMENTS: tuple[str, ...]                # curator's 7 result-count / response-size fragments
MALFORMED_REQUEST_CODES: frozenset[int]              # {-32600, -32601, -32602, -32604, -32700}, one copy

def looks_like_endpoint_limitation(err: Any, *, fragments: tuple[str, ...],
                                   unstructured_is_limitation: bool = True) -> bool
    # message-first over `fragments`; then MALFORMED_REQUEST_CODES only when the message missed
    # (ttt/curator/surf/p4 shape); cattown passes unstructured_is_limitation=False and gets no code check
    # (its today's behaviour) — expressed as a second keyword `check_codes: bool = True`.
def is_range_limitation(err: Any, *, fragments: tuple[str, ...],
                        requested_span: int | None = None) -> bool
    # surf_pool4's body (:424-459) hoisted with _named_block_limit and its two regexes, EXCEPT that the
    # named-limit guard counts blocks and is consulted only after a RANGE_CAP fragment matched (WP-A
    # deviation: curator's "result limit of 10000 reached" names rows, and a verbatim hoist read it as a
    # 10000-block limit and refused to shrink a 2000-block page);
    # requested_span=None reproduces curator's and surf's present predicate exactly.
```

Each client keeps its `_rpc*` bodies, pools, exception classes and pagers untouched and binds thin
module-level names so every caller and every `patch()` target survives: e.g. in `surf_client.py`
`_ENDPOINT_LIMITATION_PATTERNS = ETH_ENDPOINT_LIMITATION_FRAGMENTS`, `_RANGE_LIMITATION_PATTERNS =
RANGE_CAP_FRAGMENTS`, `def _looks_like_endpoint_limitation(err): return looks_like_endpoint_limitation(err,
fragments=…)`; curator passes `fragments=RANGE_CAP_FRAGMENTS + RESULT_CAP_FRAGMENTS`; cattown passes
`fragments=BASE_…, unstructured_is_limitation=False, check_codes=False`. `rpc_classify` imports nothing
from any client (planner note 3). `rpc_common.py` gains one docstring paragraph ("the fragment tables are
data and now live in one attributed place; the policies that consume them do not") — `test_rpc_shared.py:444`
stays true.

**Decisions.**
- **P1 — two endpoint tables, not one.** Ethereum (24) and Base (15) stay separate: cattown's fragments are
  Base-provider phrasings and merging would make ttt rotate on `method not found` where it is terminal today.
  The Ethereum union widens each of the four clients by 1–4 fragments **in the rotate direction only** on a
  state call (the next endpoint may answer); no shrink path is touched. The implementer verifies the four
  classification tests stay green byte-unchanged; a fragment that reddens one is reported, not edited.
- **P2 — range fragments split by family, not unioned.** surf/surf_pool4 keep the 5 span fragments; curator
  keeps 5 + 7. surf's `_get_logs_shrinking` (`surf_client.py:3033-3082`) treats a short read as success, so
  teaching it to shrink on a result cap would be silent data loss where today it rotates.
- **P3 — the one deliberate behaviour change: curator passes `requested_span`.** curator still holds
  `eth.drpc.org` for logs (`curator_client.py:110`) and lacks the archive-depth guard, so a drpc "ranges over
  10000 blocks" at a span ≤ 10000 halves its window three times for nothing. After P3 it rotates. Pinned by a
  new test in `test_rpc_classify.py` driven by `log_range_messages.json`; if an existing curator test asserts
  the old shrink for that message, it is rewritten consciously and named in the WP-A outcome.
- **P4 — talismans and fwa_logs keep their kind-based classifiers.** Their drpc `code 35` shrink is the same
  defect P3 fixes for curator, but their pagers consume kinds and `suggested_to`; hoisting is a Tier 1 per
  client with its own fixture run — filed (#65), not done here.
- **P5 — the surf↔surf_pool4 agreement test is restated, not deleted:** `test_surf_pool4_client.py:311`
  becomes an identity assertion on the imported tuples. It is the only line in the seven acceptance files
  that changes, and the outcome paragraph must say so.
- **P6 — library seams are additive.** Every new constructor parameter is keyword-only with a default that
  reproduces today's behaviour; the module-level `_CACHE_DIR` / `_CACHE_FILE` / `_RPC_URL` / `RPC_URL` /
  `INDEXER_DB` names are **kept** (tests monkeypatch them, and `Path.home()` touches no disk) but are read at
  construction, not baked into a signature default: `rpc_url: str | None = None` →
  `rpc_url if rpc_url is not None else os.environ.get(…, default)` inside `__init__`. `poll_interval` stays
  (follow-up #64).
- **P7 — no process-level rate limiter in this branch.** Aggregate rate under N concurrent clients is N× the
  measured-safe pacing; that belongs to the hosting backend and is filed with the survey's numbers (#60).
- **P8 — HANDOVER's `RpcPool` is recorded as declined** with the survey's reasons, in the closure commit; the
  branch keeps its name for the programme table's continuity.

**WP-A — `rpc_classify` + five clients** (one implementer). Files: NEW `data/rpc_classify.py`; `ttt_client.py`,
`curator_client.py`, `surf_client.py`, `surf_pool4_client.py`, `cattown_client.py` (tables and predicates
replaced by imports/bindings; `_rpc*` bodies untouched); `rpc_common.py` docstring paragraph; NEW
`tests/data/test_rpc_classify.py`: (i) every probe of `rpc_error_states.json`, `log_range_messages.json` and
`tests/fixtures/fwa/rpc_errors.json` walked through both predicates with a hand-typed expected action per
probe (rotate / shrink / terminal / not-a-limitation) for each of the five client bindings; (ii) the drpc
sentence at spans 403200/10000/2400/300 → shrink only when the named limit < span, rotate otherwise, for
curator and surf_pool4; (iii) cattown's non-dict error → `False` (the path no test covers today); (iv) each
client's bound tuple `is` the shared object; (v) `rpc_classify` imports nothing from `maxpane_dashboard.data`
beyond stdlib (AST). Acceptance: `test_ttt_client.py`, `test_curator_client.py`, `test_surf_client.py`,
`test_cattown_client.py`, `test_talismans_client.py`, `test_fwa_logs.py` byte-unchanged (`git diff --stat`
empty), `test_surf_pool4_client.py` changed only at the agreement test (P5), all green; `test_rpc_shared.py`
green with one added guard "no `*_client.py` defines `_ENDPOINT_LIMITATION_PATTERNS = (` as a literal".
Mutation proof: drop `personal token` from the Ethereum union → name the test that reddens; make
`is_range_limitation` ignore `requested_span` → the drpc-span test reddens for curator AND surf_pool4.

**WP-B — library seams** (one implementer, after WP-A; `cattown_client.py` is shared with WP-A so strictly
sequential). Files: `ocm_client.py`, `cattown_client.py`, `frenpet_client.py` (env read at construction, P6);
`talismans_client.py` (`log_rpcs: list[str] | None = None` → `self._log_rpcs`, `_get_logs` uses it; a
banned-host check like the state pool's); the seven managers (`manager.py`, `base_manager.py`,
`dota_manager.py`, `cattown_manager.py`, `frenpet_manager.py`, `talismans_manager.py`, `ttt_manager.py`) gain
keyword-only `client=None`, `cache=None` where a cache exists, `cache_path: str | Path | None = None`
(default → the module `_CACHE_FILE` at construction); `ocm_manager.py` gains `client=` symmetry if missing.
NEW `tests/data/test_manager_seams.py`: per manager, an injected fake client + `tmp_path` cache path → no
read or write under `Path.home()` (monkeypatch `Path.home` to raise), `fetch_and_compute()` still returns a
dict with the manager's model keys; per client, the env variable set AFTER import is honoured by a new
instance and an explicit argument beats it. Acceptance: every manager's existing test file green and
byte-unchanged, `tests/test_app_startup.py` byte-unchanged and green (the app's call shapes are unchanged),
`tests/screens/test_dashboard_screen.py` + one composing screen test per touched manager. Mutation proof:
revert one manager's `cache_path` plumbing → its seam test reddens by touching `Path.home`.

**WP-C — fwa_logs joins the shared transport** (Tier 0-sized, one implementer, may be the session; after
WP-B). `fwa_logs.py`: import `ENDPOINT_DEAD_CODES`, `jsonrpc_payload`, `pace`; `FWALogClient` mixes in
`OwnedHttpClient`; delete the four local copies only where byte-equivalent (the implementer diffs `_post`'s
inline pacing against `pace` first — if it differs, report and leave it). `test_rpc_shared.py`: add
`fwa_logs` (and `curator_nft_holders` if absent) to `ALL_CLIENTS` so the existing guards scan it, and make
`test_error_pattern_tables_are_not_re_declared` AST-shaped (WP-A review M5: the substring guard misses
`_ENDPOINT_LIMITATION_PATTERNS = tuple([...])`) and scan `fwa_logs.py`'s `_RESULT_CAP_MARKERS` too.
Acceptance: `test_fwa_logs.py` byte-unchanged and green; `test_rpc_shared.py` green; `tests/screens/test_fwa_screen.py`.

**Tests.** Named sets per WP as above, always plus `-m guard tests`. No suite by an implementer or reviewer;
the controller runs it once on the branch head. Fixture-first: no new fixture is captured (no network); the
three committed corpora are the classifier's evidence.

**Docs (closure commit).** `HANDOVER.md` §3 item 6 second half rewritten to B with the two factual
corrections (fwa_logs has no `_RANGE_CAP_MARKERS`; nine policies, not five) and `RpcPool` marked declined
2026-09-20; branch-order row 10 measured after WP-C; `rules/data.md` gains "RPC error classification lives in
`data/rpc_classify.py`: two endpoint tables (Ethereum / Base), two range families (span / result-count),
predicates take the table as a parameter; pass `requested_span` wherever the request had one"; `rpc_common.py`
docstring paragraph (WP-A); the owner's frontend constraint recorded under "## Later phases" with the seam
inventory that remains (#60, #63, #64).

**WP-A outcome (2026-09-20, commit b635f51).** `data/rpc_classify.py` landed at 361 lines (stdlib + `typing`
only, AST-asserted leaf): `ETH_ENDPOINT_LIMITATION_FRAGMENTS` 24 (union of ttt 21 / curator 22 / surf 20 /
surf_pool4 20, every provider comment moved with its fragment), `BASE_ENDPOINT_LIMITATION_FRAGMENTS` 15
verbatim (P1), `RANGE_CAP_FRAGMENTS` 5 + `RESULT_CAP_FRAGMENTS` 7 (P2), one `MALFORMED_REQUEST_CODES`, the two
predicates and `named_block_limit`. Five clients bind; every module-level name survives; no `_rpc` body,
pool, ban set, exception or pager touched; talismans/fwa_logs untouched (P4). P3 done: curator `_rpc_logs`
takes keyword-only `requested_span` and `_get_logs_shrinking` passes the page's own span; no existing
curator test asserted the old shrink, so none was rewritten. **Deviation, filed by the implementer:** hoisting
`is_range_limitation` verbatim would have reddened `test_a_result_cap_halves_the_window_instead_of_killing_the_sweep`
— `_NAMED_LIMIT_OF_RE` reads 10000 out of curator's captured `"result limit of 10000 reached"` (rows, not
blocks), so a 2000-block page would refuse to shrink, rotate, exhaust both log endpoints and kill the log
tier; the named-limit guard counts blocks, so it is consulted only after a `RANGE_CAP` fragment matched. For
surf and surf_pool4 (fragments == the span family) the predicate is statement-for-statement unchanged. Two
smaller corrections: curator's range family gained `exceeds limit of` (5 span fragments where it had 4 — the
plan's own composition, an untested widening); the survey's curator range count is 11 (4 + 7), not 10. P5:
`test_the_error_pattern_tables_agree_with_surf_client` restated `==` → `is`, the only hunk in the seven
acceptance files; the other six are byte-unchanged (`git diff --stat` empty). `rpc_common.py` +1 docstring
paragraph; `test_rpc_shared.py` +`test_error_pattern_tables_are_not_re_declared` globbing `data/*_client.py`.
NEW `test_rpc_classify.py` 50 tests: all 17 committed error bodies through all five bindings against a
hand-typed action table, the drpc sentence at 403200/10000/2400/300, cattown's non-dict flip, table identity,
the leaf check, union membership, three anti-vacuity guards. Mutations: drop `personal token` → 3 union tests
red (no acceptance test isolates the fragment — hence the minimal pairs); ignore `requested_span` → the
drpc-span test red for curator AND surf_pool4 plus 5 pre-existing surf_pool4 pins; cattown
`unstructured_is_limitation=True` → the non-dict test red and no cattown acceptance test (the survey's R1
gap, confirmed). Named runs: 12 `tests/data` files 1,104 passed; guard 192; five composing screen files 624.
Line delta across the five clients **−52** (ttt −23, curator +27, surf 0, surf_pool4 −61, cattown +5), not
the estimated ~−330: the tables shrank as predicted, curator and surf_pool4 gained docstrings recording why
the span and the two units matter — evidence did not get smaller.

**WP-A review (2026-09-20, `git diff 4899809..b635f51`, opus): Approved — 0 Critical, 0 Important, 7 Minor.**
Risk 1 verified exact: from a `4899809` worktree, both trees' predicates run side by side over all 14 distinct
error bodies in the three committed corpora plus 4 non-dict shapes at spans {None, 10, 300, 2400, 10000, 50400,
403200} — zero differing cells for surf and surf_pool4 and for `_looks_like_endpoint_limitation` on all five
clients; the only 103 differing cells are curator's range predicate, i.e. P3. Curator: drpc rotates at spans
≤ 10000 and shrinks above; result caps shrink at every span. ttt's union gain is exactly the drpc routing
triplet, none a substring of its terminal payloads. No test patches any hoisted name; every client keeps a
real module-level `def` and every `_rpc*` call is a bare global lookup. Leaf and identity confirmed. Mutations:
`looks_like_endpoint_limitation` → always True: 33 red across four acceptance files; → always False: 38 red;
a re-typed literal in ttt → exactly the new guard red; **deleting the result-cap escape (the plan's verbatim
hoist) → `test_a_result_cap_halves_the_window_instead_of_killing_the_sweep` red** — independent confirmation of
the implementer's deviation. Line counts: five clients −52 confirmed; `data/` net +321; whole diff +914.
Minors folded here: M1 the design line no longer says "verbatim" and the Facts count reads 11; M2
`curator_client.py:118`'s drpc comment ("hard 10k-block page cap") contradicted the module's own new docstring
and rules/data.md (the limit is archive depth) — reworded; M7 the two source-reading tests carry
`@pytest.mark.guard`. Filed: #66 (M3 curator's action table is evaluated at `requested_span=None`, a
configuration curator no longer uses, and the mevblocker-at-curator-spans rotate is covered nowhere; M4 the
empty-table anti-vacuity guard breaks on the first differing row and walks only ttt and cattown), #67 (M6
`surf_pool4_client._named_block_limit` is a decorative alias — `is_range_limitation` calls its own module-level
name, so patching the client attribute changes nothing). M5 (substring-shaped re-declaration guard) assigned
to WP-C, which touches that test.


**WP-B outcome (2026-09-20, commit 7ee4470, 13 files, +894/−57).** Seven managers (`manager.py` bakery,
`base_manager`, `dota_manager`, `cattown_manager`, `frenpet_manager`, `talismans_manager`, `ttt_manager`) gained
keyword-only `client=None`, `cache=None`, `cache_path: str | Path | None = None` (→ the module `_CACHE_FILE` at
construction; the instance path is what `load_from_file` / `save_to_file` use; dota/talismans/ttt now create the
injected path's parent, not `_CACHE_DIR`). `ocm_manager` gained only the missing `cache=`; `cache_file` kept, widened
to `Path | str | None`. Clients: `OCMClient(rpc_url=None)` + `_RPC_URL_ENV`, `CatTownClient(rpc_url=None)` +
`RPC_URL_ENV`, `FrenPetClient(indexer_db=None)` + `INDEXER_DB_ENV` — env consulted at construction, explicit
argument wins; `TalismansClient(*, log_rpcs=None)` → `self._log_rpcs` iterated by `_get_logs`, plus a new
`_BANNED_RPC_HOSTS` (ttt's set, entry for entry) enforced over all three pools at construction. Every kept
module-level name (`_CACHE_DIR`, `_CACHE_FILE`, `_RPC_URL`, `RPC_URL`, `INDEXER_DB`, `_LOG_RPCS`) unchanged in value
and still a working monkeypatch target; `app.py` untouched. Acceptance: `git diff --stat 9b77ae1..7ee4470 -- tests/`
shows only the new `test_manager_seams.py` (615 lines, 13 tests). Mutations: cattown's cache calls back to
`str(_CACHE_FILE)` → its seam test red, `test_cattown_manager.py` green (the old file cannot see it); `OCMClient` env
back in the signature default → the construction-time env test red; talismans `_get_logs` back to the module
`_LOG_RPCS` → its seam test red while `test_get_logs_uses_the_log_endpoint_pool` stayed green (compares by value).
Named runs: 15 data files 387 passed; +10 neighbours 720; guard 194; four screen files 39. **Four deviations, filed by
the implementer:** (1) `TTTManager` needed a class-level `_cache_path = None` fallback — `test_ttt_manager.py` builds
via `__new__` and patches the module `_CACHE_FILE`; (2) no `*_KEYS` tuple exists for cattown/dota/ttt/ocm models,
so those seam tests compare against a legacy-built reference key set instead of an imported contract — follow-up #68;
(3) patching `Path.home` cannot catch a manager ignoring `cache_path` because `_CACHE_DIR` is evaluated at import, so
the biting guard redirects the module default to `tmp_path/forbidden` and asserts it is never created; (4) talismans
had no ban check at all (the brief described ttt's); `rpc.flashbots.net` not added: no shipped pool carries it and
ttt's set, which talismans mirrors under an agreement test, does not either — the whole-branch review (Minor 3) noted
that the new gate DOES scan the injectable log pool, so adding the host by hostname to both sets is #61's job.

**WP-B review (2026-09-20, `git diff 9b77ae1..7ee4470`, opus): Needs fixes — 0 Critical, 2 Important, 6 Minor; the
production diff was found clean.** Signature-diffed all twelve constructors against `9b77ae1`: every new parameter
keyword-only with a default, no positional moved, `poll_interval` still first; `git diff --stat -- tests/` shows only
the new seam file; all `app.py` constructions keyword-only. Under a temp HOME all eight managers built with no
`cache_path` resolve to their module `_CACHE_FILE` (8/8). talismans' ban check rejects no host any existing call site
passes (29 constructions in its test file, the manager default, the seam file). `tests/test_app_startup.py::
test_frenpet_managers_share_one_cache` byte-unchanged and green. Seam file run against a copy of the owner's real
`~/.maxpane/*.json` (19 files) in a temp HOME: 13 passed, nine cache checksums byte-identical before and after.
Fourteen mutations proved eleven of thirteen seam tests bite. **I1:** `_assert_isolated` redirects the module default to
an empty `tmp_path/forbidden`, so a manager that still LOADS from `_CACHE_FILE` is a silent no-op — reverting only the
`load_from_file` call in each of the eight managers survived 8/8, and three docstrings claimed otherwise; the load half
is the half that puts numbers on screen, and a library host reading another deployment's cache would ship green.
**I2:** `mgr.client is injected` appears nowhere; making `BaseManager` always build a real `BaseChainClient` survived
13/13 and ran 6.35 s instead of 1.38 s under a dead proxy — real sockets, hard constraint 3. Minors: M1 the
`os.environ.get(ENV) or MODULE_DEFAULT` shape serves an import-time value to new instances after the variable is
unset or emptied (satisfies the plan's wording; not a regression; docstring sentence); M2 the four managers without a
`*_KEYS` contract compare against a key set derived from the code under test (construction-path equivalence, not a
payload contract) — #68; M3 talismans' `_BANNED_RPC_HOSTS` is a sixth hand-typed copy bound by no agreement test and
missing from `test_banned_host_lists_still_raise_at_construction`'s parametrize; M4 its comment says "mirrors ttt and
fwa" but fwa's set has an eighth, state-pool-only entry; M5 `_CACHE_DIR` is now unreferenced at runtime in all eight
managers while four frozen test files still monkeypatch it (#69); M6 the "forbidden was created" arm of the isolation
helper fired in none of the mutations. Fix round 1 (I1, I2, M1, M3, M4 folded) sent to the resumed implementer.

**WP-B fix round 1 (2026-09-20, commit c43ce34, 6 files, +369/−170; production changes comment-only, verified by a
non-comment diff filter).** I1: `test_manager_seams.py`'s isolation helper redirected each module default to an
EMPTY `tmp_path/forbidden`, so a manager still loading `_CACHE_FILE` read an absent file and came up empty exactly as
if it had obeyed `cache_path` — an absent path cannot tell "loaded the right file" from "loaded the wrong, missing
one". Replaced by a helper that SEEDS the redirected default with a populated cache written by that manager's own
cache class, then asserts in order: the seed is non-empty; a control manager pointed at it DOES load it (anti-vacuity,
probe per cache: `history_size` for six, `operations_total` for talismans, `dict(last_seen_block)` for ttt); the seam
manager comes up empty; after one `fetch_and_compute()` + save the seam file exists and the seeded bytes are
unchanged. Bakery's and ocm's seeds use `time.time()` because per-series `max_age` would otherwise expire them on
load and make the control step fail loudly. I2: `assert mgr.client is <injected>` twice per test (seeder and seam
manager) in all eight, and every client class patched to a raise-on-every-attribute fake as the socket backstop.
Mutations: reverting only the load call in `base_manager.py:82` + `ttt_manager.py:148` reddened exactly the base and
ttt seam tests at the load step, the other eleven green (under the old helper all 13 stayed green); `base_manager.py:73`
always building a real client reddened exactly the base seam test on the identity assert (under `7ee4470` all 13
passed and real sockets opened). Folded: M3 `test_banned_host_lists_still_raise_at_construction` parametrizes
fwa/ttt/talismans and a new `test_talismans_and_ttt_ban_exactly_the_same_hosts` binds the sixth hand-typed copy
(`==` on the sets, `fwa − ttt == {"eth.drpc.org"}`); the seam file's duplicate arm trimmed to the log-pool seam; M4
talismans' comment now says it mirrors ttt exactly and names the agreement test; M1 one docstring sentence in
ocm/cattown/frenpet clients states the import-time fallback. Named runs: seam file 13; three data files + eight
manager files + `test_app_startup.py` 306; guard 194.

**WP-B scoped re-review (2026-09-20, `git diff 7ee4470..c43ce34`, opus): I1 ADDRESSED, I2 ADDRESSED.** The load-only
revert (`load_from_file(str(_CACHE_FILE))`) applied one manager at a time reddened all eight seam tests on the step-3
assertion "loaded its module default instead of the injected cache_path" — 1 failed / 12 passed each time, where at
`7ee4470` the same mutation survived 8/8; bakery and ocm redden because their seeds carry `fetched_at=time.time()`, so
`max_age` does not expire them on load. The anti-vacuity step was instrumented in place: every probe is non-zero after
the seeder loads and falsy for a fresh manager (bakery 2, base 3, frenpet 5, talismans 1 via `operations_total`,
cattown/dota/ocm 1, ttt the two `last_seen_block` entries), so steps 2 and 3 constrain each other. Save-only reverts
still bite (bakery, ocm) and dota's `mkdir` arm bites. I2: identity asserted at step 1 and step 3 in the shared helper,
so all eight are covered; the `if client is None` drop in base, frenpet and talismans each reddened exactly its own
seam test; the fake is a plain class whose `__getattr__` returns an async raiser, no `unittest.mock` in the file, patched
into all eight modules; the base mutation that passed in 6.35 s at `7ee4470` on real sockets now fails in 0.27 s.
Scope confirmed: production diff non-comment-empty; only `test_rpc_shared.py` pre-existing test touched; the agreement
test asserts `==` and `fwa − ttt == {"eth.drpc.org"}` and reddens on one deleted host; the seam file's ban test kept
only the log-pool arm and reddens on dropping `*self._log_rpcs`. New Minor filed: #70 (`cache=` identity asserted for
frenpet and ocm only; six of eight `cache=` seams delete green). Named runs: two changed files 68; 18-file set 573;
guard 194; five screen files 48. 24 mutations, inverse-edit restored, tree clean after each.


**WP-C outcome (2026-09-20, commit de27166, 2 files, +172/−43; `fwa_logs.py` +13/−28).** All four brief items were
found behaviour-identical after a statement-by-statement diff and replaced: `_ENDPOINT_DEAD_CODES` → import alias of
`rpc_common.ENDPOINT_DEAD_CODES` (sole use is `in`; frozenset reads as the set did); `_payload` → `jsonrpc_payload`
(key-for-key and order-for-order identical; no fwa request fixture exists to pin bytes; the per-instance
`_request_id` increment stays); `_post`'s inline pacing → `pace` (`__init__` stores `max(0.0, float(...))`, so
truthiness ⟺ `> 0`; same elapsed point, same sleep, same stored timestamp; the no-sleep path makes one
`monotonic()` call instead of two, and nothing patches it); `FWALogClient(OwnedHttpClient)` with its identical
`close`/`__aenter__`/`__aexit__` deleted, `_client`/`_owns_client` kept in `__init__`. Deliberately LEFT:
`fwa_logs._strip0x` also strips uppercase `0X` where `evm_abi.strip0x` does not — binding it would change every FWA
log decoder on an uppercase prefix — so it stays under a per-NAME `CODEC_EXEMPTIONS` entry pinned by a divergence test
that reddens the day the two agree (never a module skip); `fwa_logs` stays out of `RPC_CLIENTS` (that list asserts a
`_rpc` it lacks) and the positive envelope guard moved to a wider `JSONRPC_MODULES` instead of a parametrised skip.
`ALL_CLIENTS` gained `curator_nft_holders` and `fwa_logs` (both non-`*_client.py` modules the MEDI-17 glob never saw),
so five codec/lifecycle/dead-code guards now scan them. M5 done: `test_error_pattern_tables_are_not_re_declared`
walks top-level `Assign`/`AnnAssign` nodes and requires every value node to be `Name`/`Attribute`/`BinOp(Add)` — a
deviation from the brief's bare-Name wording because `curator_client.py:253` composes two shared families on purpose
(P2); any `Constant`/`Tuple`/`List`/`Set`/`Dict`/`Call` fails. P4 allow-set `_P4_LOCAL_TABLES` (talismans'
`_RESULT_CAP_MARKERS`/`_RANGE_CAP_MARKERS`, fwa_logs' `_RESULT_CAP_MARKERS`) cites P4/#65, with two anti-vacuity
defences: the walk must have SEEN ttt's, curator's, fwa_logs' and every exempted table, and a new guard test asserts
each exempted table is still a literal that would otherwise fail. Mutations: re-added dead-codes literal in fwa_logs
→ exactly the dead-codes guard (1F/140P, all 78 acceptance green); ttt `= tuple(["x"])` → exactly the AST guard,
allow-set entries green, and the OLD substring guard shown blind to it; mixin dropped → the lifecycle guard AND 21 of
78 `test_fwa_logs.py` on `AttributeError` at `close()`. Acceptance: `test_fwa_logs.py` byte-unchanged, 78/78; only
`test_rpc_shared.py` under `tests/` in the diff. Named runs: five data files 271→279; +4 neighbours 403; guard
194→195; `test_fwa_screen.py` 22. Minors raised by the implementer: `evm_abi.strip0x` does not strip `0X` (→ #71);
`rpc_common`'s "all eight / all five" docstring counts and three unmarked source-reading tests (folded in the
closure commit).

**WP-C review (2026-09-20, `git diff 61e0c53..de27166`, opus): Approved — 0 Critical, 0 Important, 6 Minor.** The
three claims the controller singled out all hold: (a) the `+`-admitting AST rule requires every node of the value
expression to be `Name`/`Attribute`/`BinOp`/`Add`/`Load`, so `SHARED + ("x",)` and `SHARED + tuple([...])` both redden
the guard while curator's P2 composition stays green; (b) `CODEC_EXEMPTIONS` is per name — making `_strip0x`
identical to the shared helper reddens exactly the divergence test, and a second forbidden def in fwa_logs still
reddens two codec guards; (c) pacing: `_min_call_interval` is assigned once as `max(0.0, float(...))`, so truthiness
is `> 0`; both bodies run side by side out of tree with a faked sleep over seven boundary cases (first call at 0.05
and at 0, interval 0 with a recent last call, 1 ms, 1 s, negative last call, NaN through `max`) gave identical sleep
counts and durations; `jsonrpc_payload` bytes identical to the deleted literal. The `fwa_logs.py` diff is six hunks,
none touching the classifier, markers, learned window, scanner or endpoint list. Nine mutations, each reddening the
advertised test; the `_payload` revert left all 78 acceptance tests green (behaviour-neutral by construction). Minors:
1 the AST walk read only the top level, so a nested `if True:` restatement in `surf_client.py` passed (63 green),
caught in ttt only via the three anchored pairs — **folded**: the walk now descends every module-scope compound
statement and stops at function/class bodies, and `_BOUND_TABLES_TODAY` anchors all nine (module, table) pairs;
controller mutations: nested restatement ADDED beside surf's binding → exactly the guard red; surf's binding renamed
→ exactly the guard red. 2 `fwa_logs._addr_topic` / `_word` / `_uint` restate `evm_abi` codec arithmetic under other
names (→ #71). 3 the `0X` divergence the exemption protects is exercised by no test — all 78 acceptance tests stay
green with the copy made identical (→ #71). 4 `rpc_common.py` docstrings "all eight" (×2) / "all five" — **folded**.
5 `_CLASSIFIER_SOURCES` and `ALL_CLIENTS` disagree about which non-`*_client.py` modules count (→ #72). 6 fwa's
pacing path is exercised only at `min_call_interval=0.0` while production runs 0.05 (→ #73). The implementer's
three-marker Minor is **folded** (guard set 195 → 198). Named runs: two changed files 141; eight-file set 443; guard
195; `test_fwa_screen.py` 22. Tree clean after every restore.

**Branch 10 closure (2026-09-20).** Three work packages, all Approved (WP-A 0C/0I/7M; WP-B 0C/2I/6M → fix round →
both ADDRESSED; WP-C 0C/0I/6M). Production `269beda..de27166 -- maxpane_dashboard/`: +869/−321, net +548 (row 10 has
the split). Acceptance held throughout: seven client test files, all eight manager test files, `test_fwa_logs.py` and
`test_app_startup.py` byte-unchanged. New tests: `test_rpc_classify.py` (50), `test_manager_seams.py` (13), plus the
AST-shaped re-declaration guard, the P4 self-check and the talismans↔ttt agreement in `test_rpc_shared.py`. Filed
#60–#73. `HANDOVER.md` §3 item 6 rewritten to option B with `RpcPool` declined; `rules/data.md` gained the
classification paragraph. Whole-branch review and the single full suite follow in the closure sequence below.


**Whole-branch review (2026-09-20, `git diff 269beda..a788ba4`, opus): Approved — 0 Critical, 0 Important, 5 Minor.**
Check 1: all eight managers built out of tree with a raise-on-everything client and `Path.home` raising; 14/14 bound
tables are the `rpc_classify` objects by identity; sizes ETH 24 / BASE 15 / RANGE 5 / RESULT 7 / CODES 5. Check 2:
acceptance byte-unchanged (seven client files, eight manager files, `test_app_startup.py`; `tests/` diff is exactly
the two new files, `test_rpc_shared.py` and P5's one-token change); 31 committed error bodies × 7 spans × 10 predicates
= 2,170 cells per tree against a read-only `269beda` worktree — 9 differing cells, all curator's range predicate: the
drpc/1rpc/blastapi "named limit already met" rows flip to rotate (P3) and mevblocker's honest cap flips to shrink (the
disclosed widening, pinned by `test_rpc_classify.py`'s hand-typed row and its own test); both kind-classifiers
unchanged cell for cell. Check 3: 46 URL literals in each tree, zero added or removed; three module-level env
fallbacks + three construction-time reads, no new variable; no key/signer/clipboard/socket line added; flashbots in no
pool; the two new test files run in 1.62 s under a dead proxy. Check 4: importing all 100 `data/` + `analytics/`
modules leaves no `textual`/`rich` in `sys.modules`; the only file written is the injected cache path;
`~/.maxpane` byte-identical. Check 5: every figure re-measured true; guard 198; #60–#73 present. Check 6: six new
mutations (import-leaf, an `AnnAssign` literal in cattown, a P4 table turned binding, flashbots ADDED to talismans'
set, the log-pool arm dropped from the gate, talismans save-only revert) each reddened exactly the advertised test.
Minors: 1 `HANDOVER.md` item 7 still prescribed "`RpcPool` config" — **folded**; 2 row 10's split summed to +561 (the
seam group double-counted `cattown_client`, `rpc_common` +12 was in no group) — **folded**; 3 the WP-B outcome's
justification for leaving flashbots out of talismans' ban set no longer matched a gate that scans the log pool —
**folded** (sentence corrected; the by-hostname ban is #61); 4 `ocm_manager.py` used truthiness (`client or
OCMClient()`, `if cache_file`) where the other seven read `is None`, so a falsy injected client silently built a real
one — **folded** with a regression test; 5 `PriceClient()` is built unconditionally in `ttt_manager` and
`frenpet_manager`, a second un-injectable client the seam tests must monkeypatch — **filed #74** and added to the
"Later phases" inventory. Named runs: three new files 126; guard 198; seven client acceptance files 773; manager set
186. Fix wave committed as `4da926e`.

**Fix-wave scoped re-review (2026-09-20, `git diff a788ba4..4da926e`, opus): Minors 1–4 ADDRESSED, 5 FILED-as-agreed.**
Every `RpcPool` mention left in HANDOVER, the programme doc and `.claude/rules/` is a decline record or Branch 9's
historical plan text; the row 10 split re-measured figure by figure and partitions the 19 changed files exactly
(1 + 5 + 11 + 1 + 1); the flashbots sentence matches the gate at `talismans_client.py:552` and #61 carries the
by-hostname fix; `test_ocm_manager.py` byte-unchanged and behaviour-neutral (no test passes a falsy client or an
empty path). Mutation: restoring `client or OCMClient()` reddened exactly the new regression test on its identity
assert, 13 green. New Minor: restoring the `if cache_file` truthiness left all 24 green — the path half was
unpinned — **folded by the controller**: the same test now also builds with `cache_file=""` under a `chdir` into
`tmp_path` and asserts the result is not the module default; controller mutation: truthiness restored → exactly that
test red on the new assert. Guard 198.


## Branch 11 — `docs/new-dashboard-checklist` (Tier 0, session implements)

Spec: HANDOVER.md §3 item 7. Cut from main `aee445e` after Branch 10 merged. "Reuse before you build" in
`rules/widgets.md` now opens with the eight-step new-dashboard checklist in dependency order — models contract
(#68 for the four without a tuple), client on `OwnedHttpClient` binding `rpc_classify` tables with the policy and
its error corpus local, `SeriesCache` subclass, manager with the WP-B seams, `DashboardScreen` subclass with
`PANELS`, `widgets/<game>/` on `panels.py` with `_chain.py` `EXPLORER`, one `SweepCase` per screen, the six
surfaces — each step naming its base and the test that proves it; the reuse order (shared modules → the
dashboard's `_fmt.py` and sibling → a migrated sibling on `panels.py`) and the divergence / mandated-redundancy
paragraphs are kept below it, with `data/`'s shared modules and talismans' agreement-bound ban set added to the
lists. The "~600 lines" figure from HANDOVER is replaced by a measurement: dota ~1,550 lines across `data/`,
`screens/`, `widgets/dota/` and ocm ~1,830 on main at Branch 10's close. HANDOVER item 7 marked done. Tests: the
one file that pins `rules/widgets.md` (`tests/widgets/test_panels.py`, on a phrase this edit does not touch) and
`-m guard`; no production code.

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

- **Data layer as a library for other frontends (owner, 2026-09-20).** `data/` + `analytics/` import nothing
  from Textual/rich/widgets/screens/app already (AST-verified in the Branch 10 survey). Branch 10 WP-B adds
  the constructor seams (client, cache, cache path, env reads at construction, talismans log pool). Remaining
  after it: a process-level rate limiter for N concurrent clients against keyless hosts (#60), the FrenPet
  shared-cache hold that lives in `app.py:123-136` rather than the data layer (#63), `poll_interval` in every
  manager signature (#64), the three `@lru_cache` ABI loaders in `fwa_logs.py` returning mutable dicts (#62), and
  the unconditional `PriceClient()` in `ttt_manager` and `frenpet_manager` — a second, un-injectable client (#74).
- **`RpcPool` as HANDOVER §3.6b wrote it — declined 2026-09-20 (owner chose option B).** Reasons in the Branch
  10 section: nine individually tested error policies, seven fragments whose meaning flips between clients,
  ~1,053 tests in the blast radius, and the "~700 lines" only reachable by deleting pinned policy. Revisit only
  if a second frontend needs one rotation loop, and then with the survey's §1e table as the risk register.

- Panels by composition (`format_row` injected) once every dashboard is on `panels.py`.
- surf / curator / fwa fully onto `PANELS` + panel subclasses.
- Per-row copy for `DataTable` / `RichLog` panels (Textual selection does not reach them).
- The 16 in-body integer sweeps listed in `docs/handover_followups_2026_09.md` #4.
- `data/manager_base.py` (`_error_count` / `last_success` / `as_of_hhmm` / last-good fold; HANDOVER §3 item 6,
  second half) — follow-up #44; needs a survey of the fourteen managers first.
