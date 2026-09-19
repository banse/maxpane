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
