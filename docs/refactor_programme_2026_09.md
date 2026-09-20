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
   placeholder). Named because the dota roster is the one subscriber where an empty list is a
   real negative; the manager serves `None` for a failed read, so the always-new path
   with `[]` keeps the last roster under the status bar's as-of marker, which is what every
   other feed in the app does.
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
   `ROW_CAP` slices; `build_row` returning `None` skips without a gap in the ranks the subclass
   assigns; one `add_row` that raises leaves the other rows on screen (mutation: delete the
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
