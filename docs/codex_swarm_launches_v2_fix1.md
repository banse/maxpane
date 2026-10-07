# Codex fix round: SWARM launches round 2 (verification of 786e47ce, written 2026-10-06)

> **Do not use any superpowers skill.** This brief, `docs/codex_swarm_launches_v2_plan.md` and `CLAUDE.md` are the
> whole process.

**Branch:** `feature/swarm-launches-2`; continue from `786e47ce`.

**Verified:** two independent reviews from Claude Code, one of spec and UI, one of data on live data.
- **Live K8:** matches an independent PoolManager probe on **all 30 live pools** (paired amount Δ 0.0000%).
  - Verdicts: 36 live launches `✓ swarm`, 5 parked `✗ K4`. H1 is fixed on the owner's real cache.
  - Cadence: at most 10 reads per cycle, 300 s, no starvation.
- **Every A-item and B3 regression is done** in a mounted app on Textual 8.1.1 and 8.2.8.
- **Mutants:** of your recorded mutants, 16 were re-run and all killed.

**This round:** one commit, with tests and named mutants in the body. **Add `tests/screens/test_surf_screen.py` to
every pre-commit set**: it is red on `786e47ce`, and none of your sets ran it. Never merge, push or tag.

## Must fix

**P1 · Two red tests in `tests/screens/test_surf_screen.py`** (pass on base `33563899`, fail on `786e47ce`):
- `test_the_two_hand_typed_widget_dicts_account_for_every_exported_widget` → "a widget is in two role dicts at
  once: {'SurfSwarmThroughput'}".
  - **Fix:** in `_SWARM_WIDGET_CLASSES` (`:167`), replace `"SurfSwarmThroughput": SurfSwarmThroughput` with
    `"SurfSwarmLatestLaunches": SurfSwarmLatestLaunches`. THROUGHPUT is already covered by
    `_PARKED_WIDGET_CLASSES`.
- `test_every_list_row_in_the_fixture_matches_the_frozen_row_shape` → "swarm_launch_rows[0] is missing
  ['liquidity']".
  - **Fix:** in `_sample_data()` (around `:1572`), add `liquidity`: `None` on Sepolia rows, and the
    `empty_liquidity()` shape on production rows.

**P2 · The `liq` column is invisible at the owner's terminal.**
- **What happens:** it shows at 91–115 columns and from 171 up, but **not at 116–170**, which includes 143×46 and
  150×46. The "add `liq` if there is room" rule exists only for `tight` (`swarm_launches.py:163`).
- **Fix:** apply the same rule to `compact` and `roomy` (`budget >= tier_width + 14` → `liq` right after `verdict`),
  so it is visible from about 130 columns. Still never ahead of ticker or verdict.
- **Then:**
  - update `test_liquidity_tier_priority_and_degraded_cells`, which pins compact@120 without `liq`;
  - re-measure the LAUNCHES onsets (the `surf.py` pin comment, `_S_THRESHOLDS`);
  - assert `liq` is present at **143** and **150**.
- **Mutant:** the room rule in `tight` only.

**P3 · A parked or not-yet-deployed launch with no artifacts shows K8 `unknown` / `…` forever.** Affected live:
#787, #814, #826, and #816 while admitted. They have no pool, so "not read yet" is a read that never comes.
- **Fix:** with no artifacts and status `parked` or `abandoned` → `liquidity = empty_liquidity('na')`, which shows
  `--`. While `admitted` with no artifacts, keep `…`.

## Should fix (test gaps; each mutant survived the branch tests)

- **P4 · Native ETH is 18 decimals (A5.2) is not pinned.** Mutant O11 survives, and it would leave **9 of the 30
  live pools** without K8.
  - **Test:** a manager case from an ETH-paired capture (#775): no `decimals()` call to `0x0…0`, and a K8 result.
- **P5 · "Oldest-read first" is not pinned.** The reversed-sort mutant survives, because at most 10 pools are ever
  due in the test.
  - **Test:** 15 or more due pools with distinct `read_ts` → the 10 oldest are chosen.
- **P6 · LATEST LAUNCHES cap.** Test with 6 or more production rows → exactly 5 (kills a cap of 6).
- **P7 · Verdict colour.** A withdrawn row's verdict cell stays green `✓ swarm` (kills "verdict red on
  withdrawal").
- **P8 · Boundaries.**
  - `tick == tickUpper` is **not** in range;
  - share is `None` outside range.

  (Mutants O17 and O4 are equivalent on live data today.)

## Nits

- **K8 lock line:** add `(L = deployed L)` after "never withdrawn", as specified. When the owner is not a policy
  factory, say `held by <owner>` without "(unverified)" unless it is a contract with no verified source.
- **LATEST LAUNCHES title** wraps onto 2 lines at 32 cells or narrower: clip the `· as of` marker like the other
  titles.
- **LATEST empty / unavailable word** sits under 5 blank rows: show it in the first row, under the title.
- **Ambiguous pool evidence** (two distinct `ModifyLiquidity` logs, or the token in two initialized pools) is re-read
  every 300 s forever. Persist an `ambiguous` marker once a complete receipt set parses ambiguously.
- **K8 bootstrap** uses `fetch_launch_evidence` (tx + receipt) where only receipts are needed. Read receipts only.
- **H1 retry:** stop the every-1,800 s re-read for a parked launch whose K4 is already a definite `fail` and whose
  admission list is legitimately empty (a deploy-failure park).
- **Mutant record:** the e0c05688 body records the tcss-only gap mutant as killed by the composited gap test. In
  fact only the CSS-agreement test kills it, because DEFAULT_CSS still supplies the margin. State the correction in
  this round's commit body.

**Report:** test counts including `test_surf_screen.py`, `test_surf_signals.py` and `test_surf_swarm_inflight.py`,
on both Textual versions, plus the mutant list.
