# Copy-icon rule — follow-ups

Filed at the end of `feature/address-copy-icons` (plan `docs/superpowers/plans/2026-09-14-address-copy-icons.md`,
spec `docs/address_copy_PRD.md`). Each item was found by a task or whole-branch review, adjudicated, and
deliberately **not** fixed on the branch. The branch allowed one final fix wave, and these came out of its
re-review or were judged not worth that wave. Nothing here is a known break of the rule on a screen a user can
reach at a pinned width, except where an item says so.

## Owner decisions

- **STAKERS at its pin — decided 2026-09-15, kept as is.** The `4` body's STAKERS panel shows the whole address
  from 121 columns, with a 40-cell anti-poisoning window at 119–120 (`widgets/surf/pool4u_stakers.py`,
  `_ADDR_SHORT_COLS`). The owner reviewed this against the 2026-09-12 request for whole addresses and confirmed
  the windowed pin is the intended behavior: the owner sees whole addresses at normal width, and no code changes.
  The "raise the pin to 121" alternative below is declined, not merely unchosen.
- **Curator `f` does not open the analysis body — decided 2026-09-15, `f` opening the filter is correct.**
  `screens/curator.py:829` binds `f` to `action_toggle_filter`, which only acts in MODE_LIST (opens or applies
  the `l` record view's custom filter editor); it is a no-op elsewhere. That has been true since `9c5eb2d`
  (2026-08-20, "wire filtered list controls"), which superseded `e67938b`'s original `f` → `action_toggle_analysis`
  binding (2026-08-18). The owner confirmed the current binding as intended — CLAUDE.md and README.md were wrong,
  not the code, and both were corrected to describe `f` as the filter key.
  **Closed the same day.** The owner asked for the orphaned `action_toggle_analysis` (~:1423, MODE_ANALYSIS:
  OPERATORS / SEGMENTS / CLEANED LIST) to be bound to **`a`** ("yes bind it to a") rather than re-nominating `f`
  or any other key already spoken for. `screens/curator.py:828` now binds it, without `priority` (unlike `f` and
  `e`, which are accept/apply keys inside the filter editor's own workflow and must win even against a focused
  field there — `a` plays no part in that workflow). Verified, not assumed: a focused Textual `Input` in the
  filter editor consumes any printable character itself before either kind of binding is even checked, so
  `priority=True` on `a` would not have changed this specific interaction either — see the comment beside the
  binding and `tests/screens/test_curator_screen.py::test_a_inside_the_filter_editor_types_the_letter_instead_of_switching`.
  `a` behaves exactly like `y` from every mode (mirrors `action_toggle_mode`, minus the wallet gate) and is
  deliberately **not** added to `KEY_HINTS` — the owner asked for the binding, not the hint, and that string is
  pinned against the worst case at 138 columns. The address sweep now reaches the body with the key tuple
  `("a",)` instead of calling the action directly.
- **Visible trades made to fit the icon without raising a pin.**
  - curator `l` table: ADDRESS shows a 40-cell window instead of the whole address.
  - curator `y` WALLET line: windowed at 138.
  - curator `l` hero cards: now gapless (`margin: 0`), while the dashboard hero keeps `0 1`.
  - surf LAUNCHPAD COINS: NAME 18 → 16.
  - surf HATCHES lever grid: 17 → 15 (window 8/6 → 6/6).
  - TTT fees/leaderboard SYM: 8 → 5; a no-symbol row shows `--` beside an icon that copies the address.
  - FWA below its pin: sheds columns behind `‹ widen` rather than cropping.

## Enforcement gaps (tests)

- **Pin-size crops that eat a window's tail.** At pin sizes E2 runs only its per-row checks. A crop that removes
  ` ⧉` *and* a tail character (`0xc0c0…c0c`) no longer matches as a window. Seed presence runs only at 170.
  Keep presence at pins, with a per-case, per-size list of seeds a view may legitimately drop (e.g. surf
  SIGNALS' deploy line at 143).
- **Unlabelled wrong-row icons.** A row that shows another row's address with its icon, and no name beside it, is
  invisible to a composited sweep. Only per-panel "row n shows entry n's address" tests catch it.
- **Label index.**
  - It false-positives when the name lives in a child record of the address's record.
  - It matches by substring.
  - It reads only the cell before the icon.
- **Exemptions.** The guard never checks that an exempt class is still uncovered, so stale exemptions persist.
- **E1 shapes.**
  - It misses `"…".join((a[:6], a[-4:]))` and `Text.assemble(a[:6], "…", a[-4:])`.
  - It would false-positive on `rows[:5] + rows[-5:]`.
- **Import-based coverage.** Coverage is keyed on a module importing `widgets.address` directly. A wrapper
  module that re-exports it gives an empty mounted set.
- **Bakery case.** The case sweeps CookieChart, SignalsPanel and EVTable in a failure state: the fake payload
  lacks `chart_histories`, `late_join_ev` and `boost_rankings`.
- **Mutation proofs missing.**
  - OCM click test and `activity_feed_template` helper test.
  - Prose both-ends test, which counts icons only.
  - cattown LEADER cap: no long-name test.
  - settlement icon drop: not isolated by the degradation regex.

## Rendering defects (rare or dead-code paths)

- **TTT symbol `⧉`.** Label hardening empties it, so the cell falls back to the address: 13 cells in a 7-cell
  column, with the icon cropped. Fix: `_safe_symbol` treats a glyph-only symbol as `--`.
- **surf `_cap_detail`** (`analytics/surf_signals.py`).
  - After the cut, two kept addresses are glued together with no separator, so neither matches.
  - A re-cap on load destroys both.
  - Reaching it needs a >160-character method name containing an address, or a hand-edited cache.
- **surf SIGNALS deploy line at its 143 pin.** It shows `new contract…` with the address dropped whole. The
  address is never bisected, but at 143 the reader cannot see which contract fired. This predates the branch
  and was exposed by the pin sweep.
- **surf feed.**
  - `_cell_fit` can cut between an address and its NBSP icon.
  - `break_long_words` can split a marked unit.
- **surf HATCHES.**
  - The detail line is dropped whole when it begins with an address wider than the room.
  - The lever grid has no wider tier.
- **surf caches.** Deploy details persisted before the branch hold a pre-shortened address, with no icon until
  replaced (≤ 24 h live).
- **Stale theme colours.** curator list hero and signals keep the old theme's colours until the next refresh
  after `t`.
- **Cursor move.** Clicking an icon in a `DataTable` (surf STAKERS, curator tables) moves the row cursor.
- **Pre-existing, not from the branch:**
  - `widgets/surf/launchpad._clip` measures `len()`, not `cell_len`; NAME at 16 makes a CJK coin name crop
    silently sooner.
  - curator `_apply_columns` picks a tier against `content_size`, which includes the scrollbar gutter.
- **Dead code.** base `graduated`, `launch_feed`, `top_movers`, `trending_table`, `bt_leaderboard`,
  `_legacy_overview`, and `overview.py`. The last is shadowed by the `overview/` package and cannot be
  imported. All of them are converted but mounted by no screen, so none is swept. Delete or wire them.
- **Minor helper and clipboard notes.**
  - `_fit` emits `…` for width ≤ 0.
  - `StatusBar.message`'s `getattr` fallback is dead.
  - `_clear` captures the bar at post time.
  - `await proc.wait()` after SIGKILL has no timeout of its own.
  - FWA drift with two addresses (before → after) is untested.

## Surf adjustments of 2026-09-15 (`e` key, all stakers, launchpad heights)

- **`launchpad._COIN_CHROME_ROWS = 3` is hand-typed.** It assumes the coin table never shows a horizontal
  scrollbar. `max_scroll_y == 0` is asserted only at the width pin and above.
- **Short launchpads waste rows.** With fewer than 20 coins, COINS keeps its `2fr` share and leaves blank rows
  that ACTIVITY used to get.
- **No spare cells beside the STAKERS scrollbar.** The 353-row table always scrolls, and its 2-cell scrollbar
  exactly uses the tier budget's 2 spare cells at 119 and 121. `_TITLE_PADDING_COLS = 2` matches the scrollbar
  only by coincidence. The every-staker width sweep reddens if the scrollbar grows.
- **Shadowed variable.** `pool4u_stakers.footer_line` reuses the name `shown` for the formatted top-3 value after
  consuming the `shown=` parameter. There is no bug today, but it is a trap for the next edit.
- **Stale test comment.** `tests/screens/test_surf_screen.py` ~:2439 still says "the ten are distinguishable"
  for a 20-coin payload.
- **Bisect note.** Commit `59799ab` is red in isolation (a layout test's row counter counted the footer); `fe938a2`
  fixes the counter.
- **Layout contract.** RECENT FLOW's BURNED/STAKERS legs render `0` on a sell into headroom (verified on chain,
  fixture `tests/fixtures/surf/pool4/`), `--` when unread, and four decimals for a sub-cent payout.
- **Unreachable 9-cell share.** `pool4u_stakers._fmt_share_cell` renders a negative sub-step share as
  `"-<0.0001%"`, 9 cells against `_PCT_COLS = 8`. It cannot occur today: `staker_rows` only folds positive
  balances. It would be cut with an ellipsis if a producer ever sent one.
- **IMD headroom is 1 cell.** Over the synthetic worst case (`1200.0B`, 7 cells) the IMD column (`_IMD_COLS = 8`)
  has one spare cell since the small-stake digits change gave two of its cells to share.

## Flaky test (pre-existing, load-sensitive) -- FIXED 2026-09-17

- `tests/screens/test_curator_screen.py::test_delayed_custom_name_does_not_block_reset_or_clear_new_input` waited
  on wall-clock timeouts (`asyncio.wait_for(..., timeout=0.25)` for the reset, `timeout=1` for the name lookup).
  - Failures: once in the final fix wave's batch run (at `e70b239`, before the `a` binding existed), and once with
    `TimeoutError` on the 0.25 s reset wait during the full per-directory suite at `33d771a` (screens chunk, 17 min).
  - It passed alone 3/3 on the same head.
  - The test sets `nft_input.value` directly and presses only `f`, so the curator `a` binding cannot reach it.
  - **Fix applied**: the 0.25 s bound on `asyncio.wait_for(asyncio.shield(reset), ...)` was raised to 10 s. No
    event to await instead of task completion exists here -- `name_releases[key]` is only ever set in the
    `finally` below the wait, well after it, so *any* timeout that lets `reset` finish proves reset never needed
    the delayed worker; the 0.25 s figure was a tight wall-clock guess about how fast an ordinary click settles,
    not a bound tied to anything the reset path depends on, which is exactly why concurrent directory-level load
    (an ordinarily-fast `pilot.click()` taking a bit longer under scheduling pressure) could trip it with nothing
    actually blocked. Proved deterministically without recreating real load: wrapping every `pilot.pause()` call
    with an extra 50-100ms sleep (`pilot.click()` alone uses `pause()` five times internally) reproduces the exact
    `TimeoutError` on the old 0.25 s bound 10/10 runs, and the same wrapped run passes 10/10 on the raised bound;
    a further mutation (3 s per `pause()`, ~15 s of added latency) still fails even the raised bound, confirming
    it is a generous hang-guard rather than a disabled check. No production code changed -- the widget already
    resets synchronously with no worker/timer in that path, so there was no better "settled" signal to await.

## Design notes kept as is

- `widgets/surf/_icons.py` marks addresses in prose *before* fitting. It is a distinct responsibility, and
  `widgets/address.py` points to it.
- `data/curator_list_filters._windowed` is a second copy of the window rule, kept because `data/` must not import
  `widgets/`, and held in step by an agreement test.
- PRD §6: surf's deploy signal keeps the whole address inside its persisted detail text rather than in a separate
  field. It renders windowed with its icon on both the live and the `last:` paths.
- PRD §9's history note names `list_hero` as missed by the pre-implementation scan. It was not. The missed modules
  were `cleaned_list`, `lists`, `wallet` and `list_filter`.
