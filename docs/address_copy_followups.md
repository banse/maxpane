# Copy-icon rule — follow-ups

Filed at the end of `feature/address-copy-icons` (plan `docs/superpowers/plans/2026-09-14-address-copy-icons.md`,
spec `docs/address_copy_PRD.md`). Each item was found by a task or whole-branch review, adjudicated, and
deliberately **not** fixed on the branch. The branch allowed one final fix wave, and these came out of its
re-review or were judged not worth that wave. Nothing here is a known break of the rule on a screen a user can
reach at a pinned width, except where an item says so.

## Owner decisions

- **STAKERS at its pin.** The `4` body's STAKERS panel shows the whole address from 121 columns, but a 40-cell
  anti-poisoning window at 119–120 (`widgets/surf/pool4u_stakers.py`, `_ADDR_SHORT_COLS`). The window pays for
  the icon without raising `SURF_POOL4_USER_FULL_LAYOUT_COLUMNS`. That reverses the 2026-09-12 request for whole
  addresses. The alternative is to raise that pin to 121.
- **Curator `f` does not open the analysis body.** `screens/curator.py` binds `f` to the filter editor.
  `action_toggle_analysis` has no key, while CLAUDE.md still says `f` swaps in OPERATORS / SEGMENTS / CLEANED
  LIST. This predates the branch (the key moved after `e67938b`). The address sweep reaches the body by calling
  the action directly. Either rebind or change the docs.
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

## Design notes kept as is

- `widgets/surf/_icons.py` marks addresses in prose *before* fitting. It is a distinct responsibility, and
  `widgets/address.py` points to it.
- `data/curator_list_filters._windowed` is a second copy of the window rule, kept because `data/` must not import
  `widgets/`, and held in step by an agreement test.
- PRD §6: surf's deploy signal keeps the whole address inside its persisted detail text rather than in a separate
  field. It renders windowed with its icon on both the live and the `last:` paths.
- PRD §9's history note names `list_hero` as missed by the pre-implementation scan. It was not. The missed modules
  were `cleaned_list`, `lists`, `wallet` and `list_filter`.
