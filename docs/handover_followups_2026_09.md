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
    (`:64-70`); `last_updated_seconds_ago` is then computed off that stamp (`:275`) and reaches
    the status bar. The only trace of the failure is `error_count`. This is the `as of HH:MM`
    convention in CLAUDE.md read backwards: the marker is the one thing that tells a reader a
    number may be old, and here it asserts freshness hardest exactly when the read failed. The
    fix is to stamp `fetched_at` from the last *successful* read (keep the previous stamp when
    `game_state is None`, or carry a separate `last_success_ts`), which is what the other
    managers' as-of markers mean. Pre-existing — it predates Branch 7 and the WP-A migration
    neither introduced nor touched it; found while verifying review C1, whose panel-side half
    (a failed read painting `unavailable` instead of the last roster) is fixed on this branch.
    **Tier 1**, not Tier 0: it changes dota's own data module and needs its own regression test
    for the two paths. Reviewer's evidence: `data/dota_manager.py:64-70`, `:101-108`, `:306`
    (Branch 7 WP-A review C1 follow-up, filed 2026-09-20).
