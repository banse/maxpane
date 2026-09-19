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
