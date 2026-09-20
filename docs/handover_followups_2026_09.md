# HANDOVER.md execution — follow-ups (2026-09-19)

Residuals from executing `HANDOVER.md` §2 (test suite) and §3.0 (MEDI-38 unavailable state).
Each is Minor under CLAUDE.md "Follow-ups" unless it says otherwise: do it as Tier 0 when its
file is next touched; never its own branch.

## §2.3 — boundary-set sweeps: what the mutation proofs showed

Every one of the 13 collapsed sites was re-proven on 2026-09-19 by re-applying its named
mutation (pin too low, pin too high, the launchpad seam, the ttt symbol width). 17 of 20
mutations reddened the named test at the boundary. The three that did not are pre-existing
insensitivities the old integer walks shared — re-running the old full ranges with the same
mutation stayed green too — and are listed here rather than patched:

1. **`test_the_swarm_body_is_whole_from_its_pinned_width` cannot see a too-high pin.**
   `SURF_SWARM_FULL_LAYOUT_COLUMNS` set to 130 leaves every case green, because widths between
   the true pin (116) and the mutated one fall into the `_OWN_WHOLE_FROM` branch, which also
   asserts "whole". Only `test_..._pinned_height` has a below-pin clip assertion. A too-high
   pin is not a wrong number on screen, so Minor; the fix is an `else` branch asserting the
   shipped table marks below `_OWN_WHOLE_FROM["capture"]`, as the market body's test does.
2. **`test_no_ttt_table_scrolls_at_or_above_the_pin` asserts nothing below the pin** (its
   docstring says so; PRD §5 allows it). `FULL_LAYOUT_COLUMNS` 143→150 stays green;
   `_SYM_WIDTH` 5→6 reddens it at 143, so the pin itself is still bound.
3. **`test_the_row_marker_agrees_with_the_scrollbar_at_every_height` no longer detects the
   mutation its docstring names.** With `_render_title`'s `if _recheck:` disabled, all 72
   cases of the OLD range (36..53 × 4 payloads) pass, not only the 32 of the boundary set. The
   docstring's "measured with the fix disabled, the disagreement appears on the no-lever body
   at 41" has drifted: either `_show_mode`'s own deferred pass now suffices or the one-row
   boundary moved with the body's content. Re-measure (terminal-layout skill) and either
   re-anchor the sweep's threshold or record that the recheck is belt-and-braces.

A seam mutation must be applied in **`themes/minimal.tcss`**, not only in `SurfScreen.DEFAULT_CSS`:
the app stylesheet outranks the widget's, so the DEFAULT_CSS-only mutation is a no-op (this is
why the first `12fr:5fr` proof stayed green). With both stylesheets mutated the boundary set
reddens at 131, 132 (both payloads), 133, 136, 137 — the same edge the full range found.

4. **Sixteen integer sweeps outside the 13 named sites** are still walks, inside test bodies
   rather than parametrize lists: `test_surf_swarm_layout.py:1315,1356`,
   `test_surf_pool4_market_layout.py:1437`, `test_surf_screen.py:4034,5677,6072,6962`,
   `test_curator_screen.py:713,2164,5055` and siblings. Collapse each to `boundary_set` when
   its file is next touched, with the same mutation proof.

## §2.2 — markers

5. `guard` is applied per file (`pytestmark`) to the five files whose tests read repo source or
   docs: `test_address_rule.py`, `test_address_sweep_registry.py`,
   `test_curator_registration.py`, `test_surf_registration.py`, `test_fwa_guardrails.py`.
   `test_fwa_theme.py` is mixed (registration + WCAG + tcss text) and is left unmarked.

## §3.0 — MEDI-38 unavailable state

6. **The hero boxes' fourth line is clipped in production.** `OCMHeroBox`, `CTHeroBox` and
   `DOTAHeroBox` are `height: 7` with a border and `padding: 1 2` in `themes/minimal.tcss`,
   leaving three content rows for label / blank / value; the subtitle line every box writes
   (`43.2% minted`, `mint cost: …`, `split between top fishers`, `mcap ▲ 3.0%`) never reaches a
   pixel — the same defect the `TalismansHeroBox` comment in the stylesheet records. Pre-existing
   (the old widgets wrote the same four lines); `tests/widgets/test_medi38_unavailable_state.py`
   gives the boxes `height: 9` in its own harness so the widget's output can be asserted. Fixing
   it touches the shared stylesheet — Tier 2 per CLAUDE.md, owner's call whether to drop the
   subtitle or grow the box.
7. **Managers still substitute `--` for a failed signal.** `ocm`/`cattown`/`dota` managers hand
   the screen `_sig_default = {"value_str": "--", "color": "dim"}` when analytics raise, so the
   widgets' `unavailable` row is reached only when the key is missing or `None`. A "could not
   compute" that arrives as `--` is indistinguishable from "nothing to report" (CLAUDE.md: a real
   negative needs a value distinct from "could not look"). Data layer, out of §3.0's scope;
   Tier 1 per dashboard.

## §3.1 — dead base code (branch `refactor/dead-base-code`)

8. **46 orphaned rule blocks remain in the base section of `themes/minimal.tcss`.** The Branch 1
   plan scoped the theme edit to the five `OverviewPanel` blocks "and nothing else", so the
   implementer stopped there (reviewer: plan defect, Minor). After the deletions no surviving
   Python defines `TrendingTable`, `PriceSparklines`, `VolumeSparklines`, `TopMovers`,
   `VolumeBars`, `GeckoPools`, `LaunchFeed`, `LaunchStats`, `GraduatedTokens`, `TokenPrice`,
   `TokenChart`, `PoolInfo`, `TradeFeed`, `TokenSignals`, `FeeClaims`, `FeeLeaderboard`,
   `FeeStats`, `OverviewHero`, `_HeroCard` or the ids `#ov-hero-row`, `#ov-sparklines`,
   `#ov-sep`, `#ov-bottom`, `#ov-left`, `#ov-right` (a type selector matches a class and its
   bases, so `BTOverviewHero` does not keep `OverviewHero` alive). No runtime effect; no test
   pins tcss-to-class correspondence. One Tier 0 sweep of the whole block when the stylesheet is
   next touched; re-point the comment at `widgets/surf/_pool4.py:199-201`, which cites five of
   these selectors as evidence for the blank-row convention.

## §3.2 — sanitiser hoist (branch `refactor/sanitize-cell`)

9. **Two bracket regexes twelve lines apart in `widgets/markup_safety.py`.** `_MARKUP_TAG`
   (`\[/?[^\[\]]*\]`, behind `visible_len`) and the hoisted `TAG_LIKE` (`\[[^\[\]]*\]`, behind
   `strip_tags`) — `TAG_LIKE` matches a strict superset. The Branch 2 spec froze `visible_len`, so the
   pair was left; collapse to one pattern in Branch 3 (`refactor/fmt-rowfit`) with a test that
   `visible_len` is unchanged on the fwa fixtures that pin it (reviewer M7, 2026-09-19).
   **Done 2026-09-19, Branch 3 WP-A:** `_MARKUP_TAG = TAG_LIKE`, pinned by
   `test_visible_len_is_unchanged_by_the_tag_pattern_alias` on six literal probes.

## §3.3 — fmt / rowfit (branch `refactor/fmt-rowfit`)

10. **Goldens that pin the shared function through a module alias, not the call site.**
    `tests/widgets/test_surf_pool4u_depth.py` (`depth_mod.fmt_eth`) and
    `tests/widgets/test_fwa_widgets_a.py` (`mod.as_float`, two tests) assert the re-exported
    `widgets.fmt` name; mutating the call site (`pool4u_depth.py` ladder cell to `places=4`) leaves
    them green and only a pre-existing render test reddens. Coverage exists, but not where the
    commit record says. Minor: move each assertion onto the call site when its file is next touched
    (WP-B review M3, 2026-09-20).
11. **`widgets/fmt.as_float` raises `OverflowError` on an int too large for a float** (`10**400`),
    and so do `fmt_eth`, `fmt_age`, `fmt_countdown`, `fmt_points`, `fmt_pct`; only
    `(TypeError, ValueError)` are caught, while `hhmm`/`mmdd` catch `OverflowError` too. Pre-existing
    in both `_fmt.py` bodies; the module docstring's "nothing here raises" is false at that magnitude
    and `test_fmt.py`'s hostile set tops out at `10**30`. A hand-edited cache file is third-party
    input and `json` parses unbounded ints, though no concrete payload key was traced. Tier 0: add
    `OverflowError` to the tuple and a `±10**400` probe (WP-B review M4, 2026-09-20).
12. **`screens/surf.py` `_fmt_hhmm` is a fourth `hhmm`-shaped formatter** (EMDASH marker,
    `isinstance` type gate) outside WP-B's survey, while `rules/widgets.md` now lists `hhmm`/`mmdd`
    under "import, never copy". Tier 0 when `screens/surf.py` is next touched: express it as
    `fmt.hhmm(ts, unknown=EMDASH)` behind a golden, or record why the type gate must stay
    (WP-B review M6, 2026-09-20).
13. **Seven `_fmt_eth`/`_as_float` copies kept on purpose** because a golden probe differs:
    frenpet `fpw_pets`/`fpw_hero` (wei input, `None` raises `TypeError`), `fwa_chase_board`,
    `fwa_settlement_table` (×2; `True` → `1.00`/`1.0` where the shared helper says `--`/`None`),
    `ttt_claims_table`/`ttt_fees_table` (ungrouped thousands). Each carries a comment naming its
    differing probe and a golden. Unify only if the owner accepts `True → --`, grouped ttt output and
    `None → --` on frenpet as deliberate render changes (WP-B implementer, 2026-09-20).

## Branch 4 — explorer links

14. **`data/talismans_client.py:80` still lists `https://eth.merkle.io` in `_FALLBACK_RPCS`** — a
    CLAUDE.md "dead endpoints, do not reintroduce" hazard; the file's own logs-pool comment at :91
    records it answering `-32601 Method not found`. Tier 0 removal when that client is next touched
    (WP-B implementer, 2026-09-20).
15. **`tests/test_explorer_action.py::test_the_message_clears_itself_but_never_a_newer_one`**: its
    second half is a fixed 5×0.01 s window with no observable anchor (a wall-clock wait, CLAUDE.md
    "await an observable state"). Minor (WP-A review Minor 3, filed 2026-09-20).
16. **Two per-row explorer sites have no widget test that bites:** `widgets/surf/swarm_throughput.py`
    (`for_chain_id(row.get("last_chain_id"))`) and `widgets/surf/pool4u_stakers.py`
    (`for_network(self._payload.get("network"))`). Hardcoding `for_chain_id(1)` / `for_network("BASE")`
    leaves `tests/widgets/test_surf_swarm_rail.py` and `tests/widgets/test_surf_pool4u_left.py` green,
    and surf's sweep case allows all three explorers. Same shape as the tests `swarm_shipped` and
    `pool4_hatches` got in fix round 1. Minor, Tier 0 when either file is next touched (WP-B
    re-review N2, 2026-09-20).
17. **surf's `widgets/surf/_fmt.EXPLORER` is not bound by the sweep:** `SweepCase.rows_pick_explorer`
    lets any surf address link on any of its three explorers, so `EXPLORER = BASE` there passes E7.
    A widget test on one `_fmt.EXPLORER` site (the hero card or the feed) pinning `etherscan.io`
    closes it; or list surf's mainnet-only seeded wallets in `explorer_for`. Minor, Tier 0 (filed by
    the controller, 2026-09-20, from WP-B re-review N1).

## Branch 5 — dashboard screen

18. **ocm's STAKING OVERVIEW and SUPPLY BREAKDOWN stay on `Loading...` under a partial payload**
    (pre-existing, found by the WP-A review as M3; unchanged by the migration — the pre/post
    render diff at 170×50 and at the 143 pin is empty). Both widgets declare numeric defaults —
    `widgets/ocm/ocm_staking_overview.py:41` (`total_staked: int = 0, net_supply: int = 0,
    staking_ratio: float = 0.0, …`) and `widgets/ocm/ocm_supply_breakdown.py:53` (`total_supply:
    int = 0, burned_count: int = 0, …`) — but the screen's dispatch passes every key explicitly,
    so a key the manager did not produce arrives as an **explicit `None`** that overrides the
    parameter default and raises `unsupported format string passed to NoneType.__format__` inside
    `update_data`. The panel is then never updated at all and keeps its composed `Loading...`
    placeholder. That breaks CLAUDE.md "a dead source degrades to an explicit unavailable state
    behind an `as of HH:MM` marker — never a crash, a **blank panel**, a stale number presented as
    live"; `Loading...` forever is exactly the blank panel, and it reads as "still fetching"
    rather than "could not look". The fix is the MEDI-38 unavailable state in these two widgets
    (the pattern `templates/hero_metrics_template.py` already carries, §3.0 above), not a change
    to the screen or to `keys()` — the payload genuinely has no value, and `None` is the correct
    thing for the dispatch to send. Visible in the log since WP-A only because the base logs every
    degraded step at `warning`; before the migration ocm logged it at `debug`, below the handler
    level. Tier 0 when either widget is next touched (WP-A review M3, filed 2026-09-20).
19. **`time.time()` is sampled inside the frenpet_wallet / frenpet_perf `PANELS` adapters**
    (pre-existing, carried across by WP-B rather than fixed). `screens/frenpet_wallet.py:135`
    (`eth_history = [(time.time(), eth_total_wei / 1e18)]`) and `:143`
    (`win_rate_history = [(time.time(), wr)]`), and `screens/frenpet_perf.py:125`
    (`win_rate_history = [(time.time(), compute_avg_win_rate(managed_pets))]`) each build a
    one-point history whose x value is the wall clock read at dispatch time. That breaks
    CLAUDE.md "**Inject the clock** (`now=` / `now_ts`)": the value cannot be pinned by a test
    without patching `time.time` process-wide (WP-B's own render harness has to do exactly that
    to get a stable diff), and a single-point series stamped with "now" is also a series point
    that no `coerce_points` boundary ever validated. Before WP-B the same three samples sat
    inside the screens' `_do_refresh`; the migration moved them, unchanged, into the module-level
    adapters `_wallet_trends` and `_perf_trends`, which is where the fix now belongs: give each
    adapter an injected `now_ts` (a `keys`-style partial, or a `now=` default argument the
    screen's tests can bind) rather than reading the clock. Both screens are hidden
    (`--game frenpet_wallet` / `frenpet_perf`), so the blast radius is one sparkline each.
    Minor, Tier 0 when either file is next touched (filed by WP-B, 2026-09-20).

## Branch 6 — panels

20. **`tests/widgets/test_sparkline_common.py`'s helper lookup is a fixed name list.**
    `_COERCE_NAMES = ("_coerce_points", "coerce_points")` and `_BUILD_NAMES` (`:100-101`, written
    in Branch 6 when the ocm render loop moved into `widgets/panels.SparklinePanel` and the old
    leaf-module lookup stopped resolving) enumerate the names a module may bind the shared
    helpers to. A module that imports `coerce_points` under **any other** alias — `_spark_from`,
    `_pts`, `as_points` — binds none of the listed names, `_resolve` returns `(None, None)` for
    it, and the walk simply moves on to the next module in the MRO, so a private re-implementation
    under an unlisted name passes both agreement tests. The pre-existing shape is the same: the
    original single-module form read `getattr(module, "_coerce_points", None)` and had exactly
    this hole for a differently-aliased copy; Branch 6 carried it across rather than introducing
    it. Reviewer's evidence: a private sparkline builder defined **in `widgets/panels.py`** and
    called by `render_series`, renamed `_build_sparkline` → `_spark_from`, after which
    `tests/widgets/test_sparkline_common.py` passed 89/89 — the copy sat on the MRO the walk
    covers, under a name the list does not. The fix is to assert on the *function objects* a
    module binds — walk `vars(module)` for every value that `is` one of `sparkline_common`'s
    helpers and for every locally-defined function whose body duplicates one — rather than on a
    hand-listed set of names. Minor, Tier 0 when `test_sparkline_common.py` is next touched
    (Branch 6 review M6, filed 2026-09-20; evidence corrected in fix round 2, N2).
21. **The `_drawn` read in `RichLogFeed`'s flicker guard is not bitten by any test.**
    `widgets/panels.py` `render_events`, `if not has_new and self._drawn:`. Reverting only that
    site to `self._seen_keys` leaves `tests/widgets/test_panels.py` at 52 passed, yet the
    difference is observable: a feed that drew rows key-lessly and then receives a poll whose
    every `dedupe_key` raises keeps the earlier rows under `_drawn` and is redrawn with the
    malformed poll's rows under `_seen_keys`. The committed behaviour is the documented one ("an
    all-malformed poll leaves a populated feed alone"); the test is missing. Minor, Tier 0 when
    `test_panels.py` is next touched (Branch 6 fix-round-2 re-review N4, filed 2026-09-20).
22. **The bare-block stylesheet guard admits a *qualified* base selector.**
    `tests/widgets/test_panels.py` `_BARE_BLOCK` matches a `panels.py` class name only when it
    is a whole item of a selector list, so `HeroBoxBase:hover { … }` or `HeroBoxBase.-thin { … }`
    appended to `minimal.tcss` pass (52 passed). `.-thin` is opt-in and harmless; `:hover` would
    restyle every subclass on hover — a narrower form of the I1 collision. No such rule exists
    today. If it is ever wanted, widen the guard to a name followed by a pseudo-class. Minor,
    hypothetical, Tier 0 with #21 (Branch 6 fix-round-2 re-review N5, filed 2026-09-20).

## Branch 7 — panels, small four

23. **`data/dota_manager.py` refreshes `snapshot.fetched_at` on a failed read, so the status bar
    says "updated 0s ago" for data nobody fetched.** `data/dota_manager.py:101-108` builds
    `DOTASnapshot(fetched_at=time.time(), …)` and calls `self.cache.update(snapshot)`
    unconditionally, including on the path where `game_state is None` because the fetch raised
    (`:64-70`); `last_updated_seconds_ago` is then computed off that stamp (`:283` on `841a0c7`) and reaches
    the status bar. The only trace of the failure is `error_count`. This is the `as of HH:MM`
    convention in CLAUDE.md read backwards: the marker is the one thing that tells a reader a
    number may be old, and here it asserts freshness hardest exactly when the read failed. The
    fix is to stamp `fetched_at` from the last *successful* read (keep the previous stamp when
    `game_state is None`, or carry a separate `last_success_ts`), which is what the other
    managers' as-of markers mean. Pre-existing — it predates Branch 7 and the WP-A migration
    neither introduced nor touched it; found while verifying review C1, whose panel-side half
    (a failed read painting `unavailable` instead of the last roster) is fixed on this branch.
    **Widened by the fix-round-1 re-review (N2, Critical by consequence, pre-existing):** the
    same failed read also serves the *other* `game_state`-derived keys as sentinels rather than
    `None` — captured payload from the real `DOTAManager` with a raising client:
    `human_base_hp=0`, `orc_base_hp=0`, `base_max_hp=0`, `winning_faction='tied'`, `tick=0`,
    `faction_balance_signal={'value_str': 'Contested (0 vs 0)', …}` — so the composited screen
    reads `FACTION LEAD: TIED` and `BASE HP: H: 0/0` beside two hero boxes that correctly say
    `unavailable`, and the title bar `Tick 0`. That is "a failed read is `None`, never `0`" broken
    at the manager, the same defect C1 was for `heroes`. One Tier 1 item with the `fetched_at`
    stamp: every `game_state`-derived key serves `None` when `game_state is None`, and the
    widgets already render `None` as `unavailable` (MEDI-38). Not touched on Branch 7 — only the
    `heroes` key the roster reads was in the fix round's scope.
    **Tier 1**, not Tier 0: it changes dota's own data module and needs its own regression test
    for the two paths. Reviewer's evidence: `data/dota_manager.py:64-70`, `:101-108`, `:318`
    (Branch 7 WP-A review C1 follow-up, filed 2026-09-20).
24. **`fmt_signal` treats an empty string as a value, where the eight copies treated it as
    absent.** `widgets/panels.py:284-287` reads `sig.get("label", "")`,
    `sig.get("value_str", "")`, `sig.get("color", "dim")` and `sig.get("indicator", "●")`. A
    `dict.get` default only fires when the **key is missing**; the talismans and ttt copies used
    `or`-defaults (`sig.get("value_str") or "--"`), which also fire on `""` and `None`. So a
    well-formed dict carrying `value_str=""` now renders an empty value cell where the copies
    rendered `--`. **That is the whole defect.** The colour half as first filed was wrong, and the
    re-review probed it on a mounted `TalismansSignals` after a good poll: `color=""` emits `[]`,
    Textual's parser raises, and `write_guarded` writes the fallback — a visible `● unavailable`,
    not a dropped line and not the previous value; `color=None` emits `[None]`, which Textual's
    `Content.from_markup` accepts as the null style, so the row renders normally and there is no
    defect in that direction at all (Rich's own `Text.from_markup` would raise on `[None]`, but it
    is not the parser on this path). Not reachable today and
    not introduced by WP-B: `data/talismans_models.py:84-92` and `data/ttt_models.py:127-135`
    declare all four fields as required `str`, both signal dicts are computed per poll from
    analytics rather than read back from a cache file, and the behaviour has been the base's
    since Branch 6 — WP-B only moved two more packages onto it. The fix is `or`-defaults at all
    four reads, so empty and `None` are treated as absent, which is what every copy the base
    replaced did. **Minor, Tier 0** when `widgets/panels.py` is next touched — one function, four
    lines, and a `test_panels.py` case per field. Reviewer's evidence: `widgets/panels.py:284-287`
    against the pre-migration `tal_signals.py` / `ttt_signals.py` at `e9a6307` (Branch 7 WP-B
    review M4, filed 2026-09-20).

25. **`test_ttt_widgets.py::test_both_sparkline_labels_are_padded_to_the_same_twelve_cells` only
    bites when the label *truncates*; widening `LABEL_WIDTH` reddens nothing.**
    `tests/widgets/test_ttt_widgets.py:140-160`. The WP-B fix-round-1 paragraph credits this test
    with asserting the padding rather than only the bars' shared start column, and the re-review
    showed it cannot: `LABEL_WIDTH` 12 → 13 and 12 → 14 both shift the two bars two columns right
    and leave 18 passed, because slicing exactly twelve characters out of a longer run of the same
    padding spaces yields `"BURNS       "` at 12, 13 and 14 alike. At 12 → 8 the test dies three
    lines *earlier*, on `_line_with(lines, "24H VOLUME $")` (the label has truncated to
    `24H VOLU`), so the padding assertion never executes for the mutation it was written for.
    The fix is one more assertion — `volume[start:start + 13]` ends in the bar's first cell, or
    the bar's start column pinned outright — so a widening reddens the same test. **Minor, Tier 0**
    when the file is next touched (Branch 7 WP-B re-review N1, filed 2026-09-20).

26. **Two `widgets/panels.py` docstrings still say markup parsing is deferred into the message
    pump.** `panels.py:279-281` (`fmt_signal`: "Textual defers `Text.from_markup` into the message
    pump, so an unescaped one raises *outside* the panel's guard and kills the app") and
    `panels.py:520-523` (`RichLogFeed`: "`Static`/`RichLog` defer markup parsing into the message
    pump where this widget's `try` cannot reach it"). Probed on Textual 8.1.1 during WP-A:
    `Static.update(str)` parses **synchronously** at the call, so on the `write_guarded` path a
    malformed value lands on the fallback, not outside the guard; `RichLog.write(str)` parses
    nothing (markup off by default); only `DataTable.add_row(str)` defers to `_on_idle` and kills
    the app. `.claude/rules/widgets.md:38` already states this; the two docstrings were not
    updated with it. The escape in `fmt_signal` is still required — the reason is that an
    attacker-named token would otherwise turn its row into `● unavailable` or inject a style, not
    that it would crash the app. Docstring-only. **Minor, Tier 0** with #24 when `panels.py` is
    next touched (seen in passing during the WP-B re-review closure, 2026-09-20).

## Branch 8 — panels, base terminal and bakery

27. **Six copies of the two-column "best plays" board and no base for it.** `widgets/ev_table.py`,
    `widgets/base/overview/bt_best_plays.py`, `widgets/cattown/ct_best_plays.py`,
    `widgets/dota/dota_best_plays.py`, `widgets/frenpet/overview/fp_best_plays.py` and
    `widgets/frenpet/wallet/fpw_best_plays.py` are one shape — a title, a header line, a blank,
    then N rows of `left-rank  name  value │ right-rank  name  value` — differing in column widths,
    cell formatters and row count. Branch 7 WP-A noted the first two copies; the Branch 8 survey
    counted six. Branch 8 puts `EVTable` and `BTBestPlays` on `PanelBase` with their own
    `compose_body`, as `OCMSupplyBreakdown` is, and does not add a base: a sixth base is a design
    decision over six packages, not an append-only extension, and touching cattown, dota and
    frenpet again is outside §3.4c. **Tier 2 when picked up** (a new shared widget base): a
    `TwoColumnBoard(PanelBase)` with `COLUMNS`, `ROW_CAP` and a `build_row(index, left, right)` hook,
    migrated one package at a time behind render-diff captures (filed 2026-09-20 with the Branch 8
    plan section).
28. **`data/base_client.py:742-747` returns `[]` for a failed DexScreener trending fetch — a
    failed read wearing a real negative's clothes (the dota C1 shape).** `_safe_dex_trending`
    catches every exception and returns `[]`; `data/base_manager.py:112` copies it and `:168`
    serves `"trending_tokens": []`, `:255` / `:260` build `gainers` / `losers` from the same
    list (`[]`), `:281` builds `whale_trades` from it (`[]`), and `:234` / `:246` set
    `total_volume = None` and a `"N/A"` / `"0.0%"` top gainer. So a poll on which DexScreener
    was unreachable and a poll that truly found no trending tokens produce the **same payload**,
    and the migrated widgets — correctly reading it as a real negative — paint `No data` in the
    leaderboard, `N/A 0.0%` in the TOP GAINER box and keep the feed's prior rows, where a failed
    read should degrade to `unavailable` behind the `as of` marker. Pre-existing: the copies
    showed the same, and Branch 8 WP-A (a widgets-only package) neither introduced nor touched
    it. The fix is the C1 fix: `_safe_dex_trending` returns `None` for a failed fetch and the
    manager serves `None` for every trending-derived key on that path (`trending_tokens`,
    `gainers`, `losers`, `whale_trades`, the gainer pair), which the bases already render as
    `unavailable` (`TableLeaderboard`, `HeroRow`) — and `BTActivityFeed` becomes a `SNAPSHOT`
    candidate once `None` is served, because its poll is a whole ranking whose every row is true
    only of the poll it came from (`RichLogFeed` docstring; today it must stay a stream or a
    failed read would blank a live ranking). **Tier 1**: base's own data module plus a regression
    test for the two paths, and the panel's `SNAPSHOT` flip with a render-diff capture (Branch 8
    WP-A outcome, filed 2026-09-20).
29. **The TOP GAINER hero box clips its second body line.** `themes/minimal.tcss:1032-1038`
    gives `BTHeroBox` `height: 7` with `border` and `padding: 1 2`, three content rows, and
    `widgets/base/overview/bt_hero_metrics.py::_gainer_body` writes `label`, blank, name, then
    `+12.0%` on a fourth line — which the pre-migration capture already shows cut off at 170 and
    at the 143 pin (`b8_before_base.default.*`: `DEGEN` visible, its percentage not). Sibling of
    #6 (the same theme matter on ocm / cattown / dota / talismans / ttt boxes;
    `test_medi38_unavailable_state.py`'s harness gives every box `height: 9` for that reason).
    Pre-existing, not moved by WP-A. **Minor, Tier 1** — the fix is either `height: 8` on the
    box (a pin move on the base screen: re-sweep) or folding the percentage onto the name's line
    (a cell-content change, also a re-sweep) (Branch 8 WP-A outcome, filed 2026-09-20).
30. **The BEST PLAYS header wraps at the 143 pin.** `widgets/base/overview/bt_best_plays.py`
    `compose_body` writes `  Top Gainers     Change    Top Losers     Change` — 2 + 14 + 1 + 10 +
    4 + 14 + 1 + 10 = 56 cells — and at 143 columns the panel is narrower than that plus the
    `.panel-line` padding, so the last `Change` wraps onto its own row and pushes the ten rows one
    down (`b8_before_base.default.pin-143x50.txt` line 33 shows the orphaned word; the capture
    after WP-A shows the same). Pre-existing, not moved by WP-A. The terminal-layout skill's rule
    is that a wrap at the pin is a pin defect: either the header sheds a column word at that
    width (surf's `‹ widen` marker pattern) or `FULL_LAYOUT_COLUMNS` / the base screen's pin
    moves. **Minor, Tier 1** (a pin or a pinned cell moves; re-sweep) (Branch 8 WP-A outcome,
    filed 2026-09-20).
31. **The base status bar says `updated 0s ago` after a partially failed read.** Because #28's
    `_safe_dex_trending` swallows the failure, `data/base_manager.py`'s `fetch_and_compute`
    returns a full payload on that poll and `DashboardScreen` updates the status bar from it as
    if the read succeeded; the only trace is the `[]`-shaped keys. Sibling of #23 (dota's
    `fetched_at` refreshed on a failed read) and of #28: the fix belongs in the same Tier 1 item
    — stamp freshness from the last *successful* trending read, so the `as of` marker means what
    CLAUDE.md says it means. Pre-existing (Branch 8 WP-A outcome, filed 2026-09-20).
32. **`SparklinePanel.SPARK_WIDTH`'s default (22) is load-bearing for five dashboards and only
    `test_panels.py`'s synthetic case bites when it changes.** `widgets/panels.py`
    `SparklinePanel.SPARK_WIDTH = SPARK_WIDTH` (Branch 8 WP-A) is what ocm, cattown, dota,
    talismans and ttt draw their bars at; the reviewer set it to 18 and
    `tests/widgets/test_talismans_widgets.py` + `tests/widgets/test_ttt_widgets.py` stayed at 18
    passed — their pins measure the bars' start column and the labels, not the bars' cell count
    — while only `test_panels.py::test_spark_width_is_the_bars_cell_count` (a `_Sparks` subclass
    defined in the test file) reddened. A shared default nobody's composited test measures is
    the "test that cannot fail" shape from a different side: the constant is right today, and a
    drift would show on five dashboards before any test said so. The fix is one composited
    width pin per migrated package (count the `SPARK_CHARS` run on one line, as
    `test_base_widgets.py::test_sparkline_is_twenty_blocks_wide_not_the_shared_twenty_two` does
    for base). **Minor, Tier 0** when a migrated sparkline test is next touched (Branch 8 WP-A
    review M4, filed 2026-09-20).

33. **MEDI-38 claim 2 ("a real `0` is a number, not `Loading`") is untested for the second-table
    hero rows.** `tests/widgets/test_medi38_unavailable_state.py:334-352`
    `test_a_real_zero_is_a_number_not_loading` is parametrised over `_WIDGETS` only; the `_HERO_ROWS`
    table (`TalismansHeroMetrics`, `TTTHeroMetrics`, and since Branch 8 WP-A `BTOverviewHero`,
    `BTSignals`) has a good-poll case whose payloads carry no zero (`eth_price=3_000.0`,
    `buy_sell_signal="Bullish"`). The behaviour is right by construction — `bt_hero_metrics.py`'s
    `_price_body`/`_change_body`/`_volume_body` branch on `is None`, so `0` renders `$0.00` / `+0.00%`
    / `$0` — but no test would redden if one of them grew an `if not value:`. Fix: a zero-payload
    row for each `_HERO_ROWS` entry in the good-poll case. **Minor, Tier 0** when the file is next
    touched (Branch 8 WP-A re-review N1, filed 2026-09-20).

34. **`SparklinePanel.render_series` writes `EMPTY_TEXT` for a `None` series — the C1 shape in the
    base.** `maxpane_dashboard/widgets/panels.py:573-575`: `coerce_points(None)` is `[]`, so a series
    whose points the manager could not read (`None`) and a series that is genuinely empty (`[]`) both
    land on `empty_line(label)` — a failed read wearing the real negative's clothes, the very shape
    Branch 7 WP-A fixed in dota's manager (review C1). Every `SparklinePanel` subscriber inherits it;
    bakery's `CookieChart` now sends `histories[name]` through it unguarded, so a `None` history
    blanks the line where the copy raised. Fix: a `None` *points* entry writes `UNAVAILABLE_LINE`
    (or an `EMPTY_KEEPS_LABEL`-aware yellow `unavailable`), `[]` keeps `EMPTY_TEXT`; one
    parametrised case per subscriber in `tests/widgets/test_panels.py`. **Important, Tier 2** — a
    shared `widgets/*.py` module (Branch 8 WP-B, filed 2026-09-20).

35. **Bakery's client substitutes `[]` for a failed bakeries or activity sub-fetch.**
    `maxpane_dashboard/data/client.py:330-334` (`bakeries = []` after `logger.warning("Failed to
    fetch bakeries")`) and `:343-347` (`activity = []` after a failed `get_activity_feed_global`).
    Downstream, `Leaderboard` paints `No data` and `ActivityFeed` keeps its previous rows or paints
    `No activity yet` — both real negatives — for what was a read that failed. Fix: carry `None`
    through `manager.fetch_and_compute` for those two keys and let the widgets' `None` branches
    (`TableLeaderboard`/`RichLogFeed` stream mode) say `unavailable`; pin it in
    `tests/data/test_client.py` against a transport that raises for the one sub-fetch. Pre-existing,
    not introduced by the migration. **Important, Tier 1** (bakery's own data module) (Branch 8
    WP-B, filed 2026-09-20).
    **Done 2026-09-20, `followups/important-2026-09`:** `GameSnapshot.bakeries/activity: list | None`, the
    client carries `None`, the manager derives off `[]` but passes `None` under `bakeries`/`events`, the
    cache iterates `bakeries or ()`; `Leaderboard` paints `UNAVAILABLE_ROW` through the base's footer slot
    (the one row it lands without `No data`) and `ActivityFeed` writes `UNAVAILABLE_LINE` while nothing is
    drawn, keeping rows otherwise. Pinned in `test_client.py` (404 routes, backoff zeroed), the manager
    contract, both widget files. The shared `TableLeaderboard`/`RichLogFeed` bases are untouched (#34's scope).
    Review I3: the DERIVED keys still compute off `[]` during an outage — filed as #75.

36. **`CookieChart._label_cell` overrides a private base hook.**
    `maxpane_dashboard/widgets/cookie_chart.py:31-39` wraps `super()._label_cell(label)` in
    `safe_markup` so the player-chosen name is escaped *after* the base clips it (escaping first puts
    a backslash where the clip then cuts the last character). It is right, and pinned by
    `test_cookie_chart_escapes_the_name_after_clipping_it`, but a subclass depending on a leading-
    underscore method is one rename away from silently unescaped labels. Fix: promote the hook to a
    public `label_cell` (or add an `ESCAPE_LABEL = False` knob on `SparklinePanel` whose `True`
    every subscriber with third-party labels sets) and drop the override. **Minor, Tier 2** — a
    shared-module knob (Branch 8 WP-B, filed 2026-09-20).

37. **`Leaderboard.update_data`'s `prize_pool_usd` parameter is unused.**
    `maxpane_dashboard/widgets/leaderboard.py:51-56` accepts it because `screens/bakery.py:80`'s
    `PANELS` row sends it (`keys("bakeries", "production_rates", "prize_pool_usd")`), and the body
    never reads it — inherited from the copy, kept so the signature and the panel-row agreement test
    did not move. Fix: drop it from both the signature and the `keys(...)` row in one change (the
    agreement test binds them). **Minor, Tier 1** — touches `screens/bakery.py` (Branch 8 WP-B,
    filed 2026-09-20).

38. **The bare `HeroBox` stylesheet block clips the hero boxes' fourth line in production.**
    `maxpane_dashboard/themes/minimal.tcss:31-40` gives `HeroBox` `height: 7`, `border: solid $panel`
    and `padding: 1 2`: two border rows plus two padding rows leave three inner rows, and the box
    body is `[dim]LABEL[/]\n\n{line 1}\n{line 2}` — the countdown's progress bar and the leader's
    `/hr` rate are line 2 and never composite. Both `tests/widgets/test_hero_metrics_degradation.py:67-73`
    and `tests/widgets/test_bakery_widgets.py:149` (`_HeroHarness`) assert under a **border-less**
    `HeroBox` block for exactly that reason, so nothing pins the production geometry. Fix: `height:
    8` (or drop the top/bottom padding) in the bare block and one composited screen test at the
    dashboard's pin that finds the bar; the hidden dashboard has no pin sweep, so Tier 1. Pre-
    existing. **Minor, Tier 1** (Branch 8 WP-B, filed 2026-09-20).

39. **The DataTable cursor row's `color: $text` hides a cell's own foreground colour on every
    leaderboard.** `maxpane_dashboard/themes/minimal.tcss:68-71` (`DataTable > .datatable--cursor {
    background: $panel; color: $text; }`): bakery's leader row is row 0, the cursor rests there, and
    its `[green]+5/hr[/]` rate composites in `$text` —
    `test_the_leader_row_is_bold_with_a_green_rate_and_the_second_is_not` had to assert the cell
    *string* off the table because the compositor shows no green (the bold survives). The same rule reaches ocm, cattown, dota, talismans, ttt and base.
    Whether the cursor row should keep cell colours is an owner decision (it is a highlight, after
    all); if yes, drop `color` from the block and re-render the migrated leaderboards. Pre-existing.
    **Minor, Tier 2** — shared stylesheet, > 1 dashboard (Branch 8 WP-B, filed 2026-09-20).
    Debt this created: `tests/widgets/test_bakery_widgets.py:347-348` asserts the cell string
    (`str(table.get_row_at(0)[3]) == "[green]+5/hr[/]"`) instead of composited output; whoever
    changes the cursor rule upgrades that assertion to `render_strips()` in the same change
    (WP-B review M3).

40. **The address sweep's bakery payload certifies three panels only in their degraded state.**
    `tests/address_sweep/builders.py:555-597` `_bakery_payload` carries no `chart_histories`, no
    `late_join_ev` / `gap_analysis` / `dominance` / `recommendation` and no `boost_rankings` /
    `attack_rankings`, so COOKIE TRENDS, SIGNALS and BEST PLAYS render `unavailable` on every sweep
    (the WP-B render diff is exactly those three panels) and the sweep never sees their live shape —
    a recommendation naming a bakery, a boost name, a chart label — which is where third-party text
    would reach the screen. Fix: add the seven keys with one hostile-free value each, and a
    `seeded`-style expectation that the three panels paint a value, not `unavailable`. **Minor,
    Tier 0** when the file is next touched (Branch 8 WP-B, filed 2026-09-20).

## Branch 9 — series cache (filed at planning, 2026-09-20)

41. **Five caches re-declare the atomic-write block `SeriesCache` will own.** `talismans_cache.py:225-262`,
    `ttt_cache.py:579-621`, `fwa_cache.py:845-870`, `surf_cache.py:1025-1050`, `curator_cache.py:1200-1225` (the
    `os.replace` at `:250`, `:608`, `:860`, `:1039`, `:1213`) each carry the
    `tmp → makedirs → json.dump → os.replace → except OSError → os.remove(tmp)` block that is byte-identical in
    the six Branch 9 caches. They are event/state caches, not `max_history` series caches, so they do not
    subclass `SeriesCache`; hoist `data/atomic_json.write_json(path, payload, *, noun)` out of `series_cache.py`
    and point the five at it. Talismans and ttt each define `_hour_bucket` (`talismans_cache.py:55-57`,
    `ttt_cache.py:85`) — same hoist. **Minor, Tier 2** — shared `data/` module, 5 dashboards.

42. **Four caches restore points of any age.** `cattown_cache.py:43-45` and `dota_cache.py:45-47` declare
    their `SeriesSpec`s with no `max_age`, and `frenpet_cache.py:290` / `base_cache.py:344` call
    `coerce_keyed` without one (anchors re-taken on the Branch 9 head; pre-branch they were the direct
    `coerce_points` calls); only bakery
    (caller-supplied, `manager.py:67-69`) and ocm (per-series consts) window. `test_cache.py:290-380` (MEDI-22)
    documents the cost: a stale point drags a regression toward the long-run average. Branch 9 preserves the
    unwindowed behaviour on purpose (Decision R4) and pins it. Deciding a window per dashboard
    (`max_history × poll_interval`, as bakery does) is an owner call because it shortens users' restored
    histories once. **Minor, Tier 1 per dashboard** once decided.

43. **FrenPet screens display a failed battle-rate read as `0.0`.** `screens/frenpet.py:52` and
    `screens/frenpet_full.py:413, 734` do `data.get("global_battle_rate", 0.0)`, and
    `frenpet_manager.py:156-162` sets `0.0` in its `except`. Branch 9 stops the zero reaching the cache (R1)
    but leaves the widget dict alone; the display path needs the MEDI-38 shape — `None` → `unavailable` behind
    the `as of` marker. **Important, Tier 1** (one dashboard's manager + two screens).
    **Done 2026-09-20, `followups/important-2026-09` (with #54):** the manager passes its `None` through as
    `global_battle_rate`, the three `data.get(..., 0.0)` sites default to `None`, `BattleFeed` repaints its
    footer on every call (`Battles/hr: unavailable`) and `FPGameSignals` drops the indicator; the
    recommendation treats `None` as not-an-active-meta. Widget + screen tests resolve markup to plain text.

44. **`data/manager_base.py` is in HANDOVER §3 item 6 but in no branch of the programme.** The
    `_error_count` / `last_success` / `as_of_hhmm` / last-good fold shared by the managers was named in the
    handover alongside `RpcPool` and `SeriesCache`; the branch-order table assigns §3.6a to Branch 9 and §3.6b
    to Branch 10, neither of which owns it. Recorded under "Later phases"; needs a survey of the fourteen
    managers before it is a plan. **Minor, Tier 2.**

## Branch 9 WP-A — found while implementing (2026-09-20)

45. **`CatTownClient.get_raffle_total_tickets` turns a malformed response into a real zero.**
    `cattown_client.py:222-227` returns `data.get("totalTickets", 0)`: a 200 whose JSON has no
    `totalTickets` key (a renamed field, an error object served with status 200) reads as "zero
    tickets sold" and is recorded and persisted as a measurement. Branch 9 WP-A closed the
    *exception* path — `cattown_manager.py:105` seeds `None` and the cache drops it — but a
    successful request with a missing key still yields the sentinel this convention exists to
    forbid, and the manager cannot tell it from a genuine zero. Fix: return `int | None` with
    `data.get("totalTickets")` (plus a numeric check, since the value is third-party), and let the
    existing `None` path carry it. One test: a payload of `{}` records no point. **Important,
    Tier 0** — one file, one return statement, one regression test.
    **Done 2026-09-20, `followups/important-2026-09`:** `int | None`, numeric-and-not-bool guard,
    `TestRaffleTotalTickets` (five no-count payloads → `None`; `0` / `12.0` → int; 503 still raises).

46. **`save_to_file` stamps `saved_at` from the wall clock.** `series_cache.py:209` reads
    `time.time()` inside `_payload()`; the six managers call `save_to_file(path)` with no clock, so
    the save path is the one place in these caches a test cannot control the time. No loader reads
    `saved_at` back, so nothing currently depends on it — but `tests/scripts/make_cache_fixtures.py`
    has to rewrite the field after the fact to get a deterministic fixture, which is the usual sign.
    Fix, if a future caller needs it: `save_to_file(self, path, *, now: float | None = None)`
    threaded into `_payload(now=)`, additive for every existing caller. **Minor, Tier 0** when
    `series_cache.py` is next touched.

47. **`tests/data/test_cache_corruption.py` builds its hostile payload from `time.time()` at import.**
    `:33` `NOW = time.time()`, and every loader it drives is called without `now=`, so the suite's
    own clock and the loader's are the same wall clock by coincidence rather than by construction.
    `SeriesCache.load_from_file` now takes `now=`, so the six cases can pass a frozen one and the
    future-dated entry (`[NOW + 86400, 999.0]`) can stop depending on the test and the code sampling
    `time.time()` within the same second. The file is byte-unchanged on this branch on purpose
    (branch acceptance pins it). **Minor, Tier 0** once Branch 9 has landed and the file is next
    touched — a test-rigor refinement, never its own branch.

## Branch 9 WP-B — found while implementing (2026-09-20)

48. **`DataCache.load_from_file` merges into `_history` instead of replacing it.** The bakery
    cache is the one migrated cache whose keyed dict is *not* cleared before a load:
    `cache.py:restore_extra` assigns per bakery name, so a load after an `update()` leaves this
    process's own bakeries tracked alongside the file's — the keyed twin of R7, which Branch 9
    decided for the fixed series only. Unreachable today (`manager.py:67` loads in `__init__`,
    before the first update) and behaviour-preserving as shipped, so it was left alone; the same
    question is open for `BaseTokenCache` and, at WP-C, for frenpet's per-pet dict. Decide it once
    for all three keyed caches rather than per file. **CLOSED at WP-C (2026-09-20): all three
    keep merging**, and the choice is now pinned for bakery, base and frenpet together by
    `test_series_cache.py::test_a_keyed_load_merges_rather_than_replaces` rather than left to
    drift into three different answers. It is the keyed twin of R7 and the opposite decision,
    because R7 governs series whose identity is fixed while these dicts' keys arrive and leave;
    no code changed, because merging is what all three already did.

49. **`histories` holding a non-dict is untested for bakery and base.** Both loaders warn
    "unexpected format" and restore nothing from that key (`cache.py`, `base_cache.py`,
    `restore_extra`), and on this branch base additionally keeps whatever the three `overview_*`
    series held rather than abandoning the whole file. Nothing drives that path:
    `test_cache_corruption.py` only feeds well-formed dicts and `test_series_cache.py`'s `[]` case
    stops at the *payload* guard one level up. One parametrised test per class would pin both the
    warning and the per-key degradation. The WP-B review widened this: for base it is a behaviour
    change, not only a test gap — pre-branch the load bailed before the overview block, so the
    session's own points survived; on the branch the three `overview_*` series are restored from the
    file and the `"unexpected format, skipping"` warning (`base_cache.py:326-331`) understates what
    was loaded. The message should say which half was kept and which skipped. **WP-C makes this
    three files, not two**: `FrenPetCache.restore_extra` has the same guard, and pre-branch its
    loader returned *before* the population block, so a malformed `histories` left
    `active_pets_history` / `total_score_history` / `battle_rate_history` holding whatever the
    session had; on the branch they are restored from the file first and only the keyed half is
    abandoned. Same behaviour change, same understating warning, same missing test. **Minor,
    Tier 0 per file** — wording + the parametrised case for that class, done when that cache is
    next touched; never all three in one Tier 0.

50. **`tests/data/test_base_cache.py:172` asserts `history_size <= 2`.** A bound, not a value: it
    passes at 0, so the test would stay green if `test_load_survives_unrankable_entries` restored
    nothing at all. The neighbouring assertion on `0xgood` is what actually bites. Tighten to the
    exact count once the file is editable (it is byte-frozen on this branch as the WP-B
    acceptance). **Minor, Tier 0** — test rigor, never its own branch.

## Branch 9 WP-C — found while implementing (2026-09-20)

51. **`FrenPetCache`'s save log dropped its second number.** The base's line is
    `"%s saved to %s (%d %s)"` (`series_cache.py:242-247`) and prints `history_size` with
    `SIZE_NOUN`, so the file now logs `"FrenPet cache saved to … (3 pets)"` where it used to log
    `"… (3 pets, 18 population points)"`. The population count was the number that told a user
    whether schema 2 was actually persisting the Score Trends series — the whole point of that
    schema bump — and it is the only one of the six caches with two counts worth printing.
    Nothing binds the literal (`rg "population points"` finds only that file). Fix, if the base
    is ever touched for another reason: a `save_summary()` hook returning the parenthesised text,
    defaulting to `f"{history_size} {SIZE_NOUN}"`. Not done here because a second base-class knob
    for one log line in one cache is worse than the missing number. **Minor, Tier 0** when
    `frenpet_cache.py` or `series_cache.py` is next touched.

52. **`OCMCache` restores `holder_count` from a JSON `true`.** `ocm_cache.py:restore_extra`
    keeps the pre-branch test `isinstance(payload.get("holder_count"), (int, float))`, and a bool
    is an `int` in Python, so a hand-edited `"holder_count": true` becomes a cached holder count
    of 1 — which then divides `net_supply` into `avg_per_holder` (`ocm_manager.py:132-134`) and
    puts a wrong number on screen. `series_points.coerce_point` already refuses bools for exactly
    this reason (`series_points.py:80-82`). Behaviour is preserved verbatim on this branch on purpose (the
    persisted shape is the branch's acceptance claim), so the guard was not tightened. Fix: add
    `and not isinstance(..., bool)`, with one test feeding `true`. **Minor, Tier 0** when
    `ocm_cache.py` is next touched.

53. **`test_ocm_cache.py::test_holder_count_cache` asserts a bound where it means a value.**
    `:121` `assert c.holder_count_updated > 0` passes for any clock at all, so it would stay green
    with `update_holder_count`'s timestamp wired to anything positive; the R3 behaviour it looks
    like it covers is actually pinned by
    `test_series_cache.py::test_update_holder_count_honours_an_injected_clock`. Tighten to
    `== <injected now>` once the file is editable — it is byte-frozen on this branch as the WP-C
    acceptance. **Minor, Tier 0** — test rigor, never its own branch.

54. **`_compute_battle_rate` answers `0.0` for "cannot compute" and that reaches the persisted series.**
    `maxpane_dashboard/data/frenpet_manager.py:550-576` returns `0.0` for fewer than two usable timestamps
    or a span below `_MIN_BATTLE_SPAN_HOURS` — its own docstring says "instead of a fabricated rate" — and
    since Branch 9 R1 only the failed *fetch* passes `None` to the cache, so a one-attack or empty window
    still appends `(ts, 0.0)` to `battle_rate_history` as if measured (WP-C review M2; byte-identical to
    pre-branch). Fix: return `None` when it cannot compute, pass it through, re-anchor
    `test_a_genuine_zero_rate_is_still_recorded` on a window with ≥ 2 attacks and a real zero, and add the
    empty-window case; the widget dict's display default is #43. Also (WP-C review M1) `OCMCache`'s version
    read became more permissive than the copy — `"2"` / `2.0` now read as 2 and keep the burn series where
    the copy read 1 and wiped it; hand-edit only, the safer answer, but add `"2"` and `2.0` to
    `test_before_load_sees_the_version`'s parametrisation when `test_series_cache.py` is next touched.
    **Important, Tier 1** (one dashboard's manager + its tests).
    **Done 2026-09-20, same branch (with #43):** `_compute_battle_rate -> float | None`; the function
    cannot produce a genuine zero (≥ 2 attacks always divide to a positive rate), so the re-anchor is
    "computed vs not computable": `test_a_window_that_cannot_carry_a_rate_records_no_point` (empty /
    one-attack), the three manager-level `yields_zero` tests now `is None`, plus the span-floor boundary.
    The `OCMCache` version parametrisation half stays open for when `test_series_cache.py` is next touched.


## Branch 9 — whole-branch review (2026-09-20, Approved 0C/0I/9M)

55. **`get_latest()` lost its snapshot type on all six caches at once.** `series_cache.py:176-178`
    declares `def get_latest(self) -> Any`; pre-branch each subclass declared its own
    (`-> CatTownSnapshot | None`, `-> BaseSnapshot | None`, `-> OCMSnapshot | None`, …). The whole public
    API delta of the branch is additive except these six annotations, which widened to `Any`, so
    `ocm_manager.py:124`'s `last_good = self.cache.get_latest()` and its siblings are no longer
    type-checked. The subclasses keep `_latest: XSnapshot | None` as a class annotation, so the
    information exists and is simply not on the getter. Each WP saw one slice, so nobody saw six.
    Fix: make `SeriesCache` generic in the snapshot type (`SeriesCache[SnapshotT]`), or a one-line typed
    `get_latest()` per subclass. Also (review M5) `SeriesSpec.allow_negative` (`series_cache.py:89`) has
    no subclass user yet — exercised only by the probe subclass in `test_series_cache.py`; keep it, it
    mirrors `coerce_points`. **Minor, Tier 0** when `series_cache.py` is next touched — the one
    finding filed against the base itself rather than waiting for a subclass.

56. **"`max_age` is deliberately not forwarded" is unfalsifiable for base and frenpet.**
    `base_cache.py:344` and `frenpet_cache.py:290` call `coerce_keyed(…, now=now)` and their docstrings
    (`:322-323`, `:279-280`) cite #42 for not windowing the keyed half. Reviewer mutation: forward
    `max_age` at `base_cache.py:344` → `test_series_cache.py test_base_cache.py test_base_manager.py
    test_cache_corruption.py tests/screens/test_base_terminal_screen.py` all green (121 passed). Bakery's
    *forwarding* is pinned (its caller supplies a window, `manager.py:67-69`); base's and frenpet's
    *non*-forwarding is not. Equivalent mutant today (no caller passes `max_age` to those two), so
    test-rigor only: one `load_from_file(path, now=…, max_age=600)` with a 30-day keyed point per class,
    asserting the point survives. **Minor, Tier 0** — file with #42's decision, since a window would
    flip the assertion.

57. **The three keyed caches disagree about a key whose points all died, and only two answers are
    pinned.** `cache.py:184-185` drops the bakery (`if not good: continue`); `base_cache.py:345-349` and
    `frenpet_cache.py:292-301` track the key with an empty deque. Each is byte-faithful to its own
    pre-branch loader (verified old vs new), so preserved behaviour, not a regression — but #48 pinned
    merge-vs-replace for all three together and left this sibling question unstated. Reviewer mutation:
    impose bakery's rule inside `coerce_keyed` (`series_cache.py:316-318`) → 3 failed
    (`test_coerce_keyed_validates_each_key`, `TestLoadCap::test_bloated_file_is_capped_on_load`,
    `TestLoadCap::test_load_then_save_writes_a_bounded_file`), **none of them frenpet's**. Decide once
    for the three (as #48 did) and pin frenpet's answer in either direction. **Minor, Tier 0** when
    `frenpet_cache.py` or `test_series_cache.py` is next touched.

58. **`_loaded_version` wears the `_loaded_*` sentinel's clothes.** `series_cache.py:293-301` documents
    the convention "`_loaded_<noun>: int | None` … `None` meaning the load bailed out"; `ocm_cache.py:130`
    and `frenpet_cache.py:127` declare `_loaded_version: int`, which is a schema version, never a
    bail-out flag, and frenpet carries both names side by side. A next subscriber reading the base's
    documented contract will mis-read it. One clarifying sentence in the base docstring, or rename to
    `_file_version` in both. **Minor, Tier 0** (two files, rename + docstring) when either is next
    touched.

59. **Whole-branch equivalence, recorded for the next cache change.** 392 old-vs-new load cases (33
    hostile payloads + 8 fixtures, fresh and after an in-memory point, six classes, `time.time` frozen)
    differ in 61, every one in a documented bucket: R5 dict guard bakery/base lacked (24, old raised
    `AttributeError`), R7 clear-before-extend after a seed (34, unreachable — every manager loads in
    `__init__`), per-key degradation on a malformed `histories` for base/frenpet (3, #49). No fresh-load
    difference outside R5. Log lines identical except bakery's `NOUN` rewording and frenpet's lost
    population count (#51). Not a defect; the reference for anyone asking "did Branch 9 change what a
    user's file loads as". **No action.**

## Branch 10 — RPC classifier hoist + library seams (filed at planning, 2026-09-20)

60. **No process-level RPC rate limiter exists; pacing is per instance.** `rpc_common.pace` is pure and every
    client keeps its own `_last_rpc_at` (cattown `:202`, curator `:390`, curator_nft_holders `:181`,
    fwa_client `:755`, fwa_logs `:1497`, surf `:1193`, surf_pool4 `:528`, talismans `:522`, ttt `:536`), so N
    concurrent clients in a web backend hit a keyless host at N× the pacing measured for one TUI
    (0.05–0.5 s between calls). Also: every `_rpc` restarts its pool from the top, so a dead primary is
    re-probed on every call. Belongs to whoever hosts the backend (a pool shared across requests or a
    process-level limiter); nothing in the TUI needs it. **Minor, no branch** until a second frontend exists.

61. **Flashbots' absence from every log pool is a comment, not a test.** rules/data.md says `rpc.flashbots.net`
    is never in a log pool; the code records the rejection (`ttt_client.py:143`, `talismans_client.py:94`) and
    `fwa_logs.LOG_ENDPOINTS:215-220` is a whitelist checked in `__init__`, but no test asserts the absence by
    hostname across the nine pools. One parametrised test in `test_rpc_shared.py` next to
    `test_state_and_log_endpoint_pools_stay_separate:427`. **Minor, Tier 0.** Branch 10 WP-B made the first
    injectable talismans log pool (`log_rpcs=`) and its construction gate scans it against `_BANNED_RPC_HOSTS`,
    which does not carry `rpc.flashbots.net`; add the host by hostname to ttt's set and talismans' mirror in the
    same change (the agreement test binds them) so a library caller cannot configure it either.

62. **Three `@lru_cache(maxsize=1)` ABI/topic loaders in `fwa_logs.py` (`:272`, `:283`, `:743`) return mutable
    dicts.** Process-global and shared by reference; a caller that edits the returned dict edits it for every
    later caller. Harmless today (no caller mutates), a hazard for a long-lived library host. Return a
    `MappingProxyType` or a frozen copy. **Minor, Tier 0** when `fwa_logs.py` is next touched.

63. **The FrenPet shared-cache hold lives in the app, not the data layer.** `app.py:123-136` reaches into four
    `FrenPetManager`s and assigns `_frenpet_variant.cache = _shared_frenpet_cache` because all four persist to
    the same `~/.maxpane/frenpet_cache.json`. A second frontend must reproduce that coupling or corrupt the file.
    Move the sharing into the data layer (a `cache=` argument the four take — Branch 10 WP-B adds the seam — and
    one factory that hands them the same instance). **Minor, Tier 1** (frenpet manager + app.py), after WP-B.

64. **`poll_interval` is a TUI concept in every manager signature.** All eleven managers take
    `poll_interval` as the first positional argument (`manager.py:54`, `dota_manager.py:39`, `base_manager.py:55`,
    `cattown_manager.py:50`, `frenpet_manager.py:74`, `ttt_manager.py:109`, `talismans_manager.py:84`,
    `ocm_manager.py:49`, curator `:651`, fwa `:477`, surf `:851`); a library consumer that polls on its own
    schedule still has to pass one. Make it keyword-only with a default and stop reading it in `data/` where
    only screens use it. **Minor, Tier 2** — eleven managers + the screens that construct them.

65. **talismans and fwa_logs shrink on drpc `code 35` regardless of the span they asked for.**
    `talismans_client.py:479-480` and `fwa_logs.py:1432-1433` classify "ranges over 10000 blocks are not
    supported on free plan" as `range_cap` → shrink, and both pools hold `eth.drpc.org` (`talismans_client.py:104`,
    `fwa_logs.py:217`). `log_range_messages.json` shows drpc answers that sentence identically at spans 403200,
    10000, 2400 and 300 (its limit is archive depth, ~64 blocks): a client that shrinks on it halves its window
    forever — the rules/data.md "rotate, do not shrink" defect, encoded only in `surf_pool4_client.py:424-459`
    (`requested_span`) and, after Branch 10 WP-A decision P3, in curator. Fix per client: thread the requested
    span into `_classify_rpc_error` (or check it in the pager) and demote `range_cap` to a rotate when the named
    limit ≥ the span. Fixture-first from `log_range_messages.json`; both pagers consume `suggested_to`, so each
    is its own change. **Important, Tier 1 per client.**
    **talismans done 2026-09-20, `followups/important-2026-09`:** `_rpc` reads the span off the request
    (`rpc_classify.requested_block_span`, new, unit-tested on all ten probes) and
    `_classify_rpc_error(..., requested_span=)` answers `rpc` when the named limit ≥ span; the four drpc
    probes drive the classifier, `_rpc` rotation and a pager test that pins `_log_window` untouched.
    **fwa_logs done 2026-09-20, same branch:** `_post` reads the span off its payload and both `range_cap`
    branches go through `_range_cap_unless_met`; the four probes drive the classifier, the recorded 65,923-block
    refusal still shrinks, and a backfill test pins drpc asked once with `_window`/`_window_ceiling` unlearned.
    Review I1 (fix round): the rule is ONE statement, `rpc_classify.met_block_limit` (+ `stale_range_cap_detail`),
    consulted by `is_range_limitation` and both kind-classifiers; agreement test
    `test_the_kind_classifiers_bind_the_met_limit_rule_not_a_copy`. The local marker tables stay (P4, #76).
    **#65 closed.**

## Branch 10 WP-A — review Minors (2026-09-20)

66. **`test_rpc_classify.py`'s curator rows are evaluated in a configuration curator no longer uses.**
    `tests/data/test_rpc_classify.py:231` calls the action helper with `requested_span=None`, but after WP-A
    `curator_client._get_logs_shrinking` (`:655-660`) always passes a span, so two `EXPECTED` rows
    (`:116-169`) state the reverse of curator's production behaviour: the drpc sentence reads SHRINK (curator
    now rotates at every span it uses; covered by `test_a_named_limit_the_request_already_meets_rotates`) and
    `mevblocker_range_cap` reads SHRINK where curator rotates at 2000/1000/500/300 (named cap 10000 > every
    page) — **covered nowhere**, and it is the one untested widening WP-A added (curator gained
    `exceeds limit of`). Also (M4) `test_the_expectations_would_not_survive_an_empty_fragment_table`
    (`:246-275`) `break`s on the first differing row, so it passes when ONE of 17 rows is fragment-dependent,
    and re-walks only ttt and cattown, so no range fragment is exercised by it. Fix: evaluate curator's rows
    at the spans its pager uses, add the mevblocker-at-curator-spans rotate, make the empty-table guard
    count differing rows and include curator. **Minor, Tier 0** when `test_rpc_classify.py` is next touched.

67. **`surf_pool4_client._named_block_limit` is a decorative alias.** `surf_pool4_client.py:361` binds
    `_named_block_limit = named_block_limit`, but `rpc_classify.is_range_limitation` calls its own
    module-level `named_block_limit` (`rpc_classify.py:358`), so patching the client attribute changes no
    classification; `test_rpc_classify.py:424` asserts the alias identity as if the seam were live. No test
    patches it today (`test_surf_pool4_client.py:445, 2590, 2603` only call it). Either drop the alias and
    point the three calls at `rpc_classify.named_block_limit`, or make the predicate take the limit reader as
    a parameter. **Minor, Tier 0** when `surf_pool4_client.py` is next touched.

## Branch 10 WP-B — found while implementing (2026-09-20)

68. **Four dashboards have no `*_KEYS` contract tuple in their models module.** `curator_models`, `fwa_models` and
    `surf_models` export the flat-dict key tuple the widgets restate and an agreement test binds; `cattown_models`,
    `dota_models`, `ttt_models` and `ocm_models` do not (bakery/base/frenpet/talismans carry theirs in the manager
    test file). `tests/data/test_manager_seams.py` therefore asserts those four seam payloads against a reference
    key set rather than an imported contract. Add the tuple to each models module (the manager's
    `fetch_and_compute()` keys, typed once) and point both the seam test and the existing manager test at it —
    per CLAUDE.md "Freeze the data contract first". **Minor, Tier 1 per dashboard** (models module + two test
    files), or fold into the dashboard's next Tier 1.

69. **`_CACHE_DIR` is unreferenced at runtime in all eight migrated managers, but four frozen test files still
    monkeypatch it.** After Branch 10 WP-B only `_CACHE_FILE` is read (dota/talismans/ttt moved their `mkdir` to
    `self._cache_path.parent`); `test_talismans_manager.py:69,214,284,300,324,345,362`, `test_dota_manager.py:95`,
    `test_base_manager.py:122`, `test_cattown_manager.py:130` patch `_CACHE_DIR` where it no longer bites. Harmless
    — each also patches `_CACHE_FILE`, which carries the isolation — but a reader will trust the wrong patch. Drop
    the dead patches when each file is next touched. **Minor, Tier 0 per file.**

## Branch 10 WP-B — re-review Minor (2026-09-20)

70. **`cache=` identity is pinned for only two of the eight managers that accept it.**
    `tests/data/test_manager_seams.py`'s shared helper asserts `mgr.cache is injected_cache` only when the test's
    `_build` returns a cache, and only frenpet and ocm do; the other six pass `None`. Mutation-proven by the
    re-review: dropping `if cache is None else cache` from bakery `manager.py:72`, `base_manager.py:74`,
    `dota_manager.py:57`, `cattown_manager.py:68`, `talismans_manager.py:108` and `ttt_manager.py:135` leaves 13
    passed every time — six of eight `cache=` seams can be deleted green. Same shape as WP-B's I2, one rung down.
    Fix: return the cache from each `_build` as frenpet and ocm already do. **Minor, Tier 0** when that file is next
    touched.

## Branch 10 WP-C — implementer and review Minors (2026-09-20)

71. **`fwa_logs` still carries a private codec.** (a) `fwa_logs._strip0x` (`fwa_logs.py:378`) also strips an
    uppercase `0X` where `evm_abi.strip0x` (`evm_abi.py:49`) does not, so WP-C could not bind it without changing
    FWA's decoder on an uppercase prefix; it sits under a per-name `CODEC_EXEMPTIONS` entry in
    `tests/data/test_rpc_shared.py` pinned by `test_the_one_codec_exemption_is_a_real_divergence`. The review found
    the divergence exercised by NO test: with the copy made identical all 78 `test_fwa_logs.py` tests stay green (no
    fixture carries `0X`; JSON-RPC hex is lowercase). (b) `_addr_topic` (`:417`) is `evm_abi.addr_from_topic` under
    another name and `_word` / `_uint` (`:397`, `:402`) restate `decode_uint`'s word arithmetic; `FORBIDDEN_DEFS` is
    name-based so they pass, while the `ALL_CLIENTS` comment advertises fwa_logs as codec-clean. Fix: widen
    `evm_abi.strip0x` to both spellings (eleven callers, a no-op for every live payload), delete the exemption, and
    bind the three renamed copies. **Minor, Tier 0** (one commit, `test_fwa_logs.py` byte-unchanged as acceptance).

72. **`_CLASSIFIER_SOURCES` and `ALL_CLIENTS` disagree about what a non-`*_client.py` chain module is.**
    `test_rpc_shared.py` hardcodes `fwa_logs.py` as the single exception to the `*_client.py` glob, while
    `ALL_CLIENTS` (same file, same diff) also lists `curator_nft_holders`. That module has no error table today, so
    nothing is missed, but the `ALL_CLIENTS` comment tells the next author to register a new chain module in that
    dict and says nothing about the second list. Derive `_CLASSIFIER_SOURCES` from `ALL_CLIENTS` (module file paths)
    so one registration feeds every guard. **Minor, Tier 0** when the file is next touched.

73. **fwa's pacing path is exercised only at `min_call_interval=0.0`.** `tests/data/test_fwa_logs.py:122` builds
    every client with a zero interval while production runs `_INTER_CALL_DELAY = 0.05` (`fwa_logs.py:257`), so no
    fwa test could tell `rpc_common.pace` from the inline block WP-C replaced; the equivalence rests on the review's
    out-of-tree harness plus `pace`'s own tests. Add one test at a non-zero interval with a faked clock and sleep
    that asserts the second call waits `interval − elapsed`. **Minor, Tier 0** when the file is next touched.

## Branch 10 — whole-branch review Minor (2026-09-20)

74. **`PriceClient()` is built unconditionally in two seam managers.** `ttt_manager.py:134` and
    `frenpet_manager.py:100` construct a `PriceClient` with no keyword to inject one, so `TTTManager(client=fake)`
    still owns a live HTTP client, and `tests/data/test_manager_seams.py` must monkeypatch the module-level name to
    keep the socket closed — the import-time coupling the data-layer-as-library constraint exists to remove.
    `client.py:72` already has the `price_client or PriceClient()` shape to copy (use `is None`). Add a keyword-only
    `price_client=None` to both, assert identity in the seam tests, drop the two monkeypatches. **Minor, Tier 1 per
    manager** (manager + seam test + the manager's own test file).

## Important follow-ups branch — review residuals (2026-09-20, `followups/important-2026-09`)

75. **Bakery's derived signal keys present an outage as live numbers.** `data/manager.py:109-118`: with
    `snapshot.bakeries is None` the derivations run off `[]`, so `leader_cookies` / `leader_rate` are `0.0`,
    `member_count` 1 and `top3_probability` `min(3, 1) / 1 = 1.0`, which feeds `late_join_ev` — during a
    bakeries outage `SignalsPanel` advertised a $1,661.67 positive EV off a 100 % top-three probability it
    invented, and `HeroMetrics` showed a `0.0` leader, beside a leaderboard saying `unavailable` (review I3;
    the numbers pre-date #35, which made the contradiction visible). Fix: `None` for the leader / EV / gap
    keys when the board is `None`, and the two panels' `None` branches say `unavailable`. **Important, Tier 1**
    (bakery's manager + `SignalsPanel` / `HeroMetrics` + the manager contract test).

76. **talismans' and fwa_logs' marker tables are still local (P4).** `_RESULT_CAP_MARKERS` /
    `_RANGE_CAP_MARKERS` in `talismans_client.py` and fwa's inline `"ranges over"` / `"block range" and "not
    supported"` phrasing are exempted in `tests/data/test_rpc_shared.py::_P4_LOCAL_TABLES`; #65 hoisted the
    span *rule* (`met_block_limit`) but not the tables. Hoisting them is a Tier 1 per client with a fixture
    run (`_LIVE_ERRORS`, `rpc_errors.json`); the exemption's comment now points here. **Minor, Tier 1 per client.**

77. **`named_block_limit` returns the largest number a message names, which can be the span echoed back.**
    `rpc_classify.py:240-257`: `"range 50400 blocks exceeds limit of 10000"` yields 50400, so
    `met_block_limit` reports the cap as met and refuses the one shrink that fixes it. Pre-existing exposure
    of `is_range_limitation`, now shared by four clients; a sweep of every fixture error at spans 1 / 300 /
    2400 / 10000 / 403200 found no live message that triggers it (review M2). Fix: prefer the `limit of`
    number when both patterns match, or the *smallest* block count; pin with a synthetic message. **Minor,
    Tier 0** (rpc_classify + its test).

78. **`Leaderboard.UNAVAILABLE_ROW` has no cell-count agreement check.** `widgets/leaderboard.py:38-41`:
    `panels.py:890-892` validates `len(EMPTY_ROW) == len(COLUMNS)` at compose time; the sibling constant is
    exempt, so a column added later leaves it one cell short and `render_table`'s per-row guard turns that into
    a log line and a blank table (review M3). Fix: one assertion in `tests/widgets/test_bakery_widgets.py`, or
    build the row from `COLUMNS` at class-definition time. **Minor, Tier 0.**

79. **`get_raffle_total_tickets` truncates a fractional count.** `cattown_client.py:260`: `int(12.9)` is 12; the
    test exercises `12.0` only (review M5). Harmless against the live API; a docstring word and a `12.9`
    parametrisation when the file is next touched. **Minor, Tier 0.**

