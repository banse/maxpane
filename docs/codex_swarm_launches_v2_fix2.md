# Codex fix round 2: SWARM launches round 2 (verification of 69584319, written 2026-10-06)

> **Do not use any superpowers skill.** This brief, `docs/codex_swarm_launches_v2_plan.md`,
> `docs/codex_swarm_launches_v2_fix1.md` and `CLAUDE.md` are the whole process.

**Branch:** `feature/swarm-launches-2`; continue from `69584319`.

**Verified:**
- P1 and P3–P8 work, and so does every testable nit. Your 20 recorded mutants were re-run and all killed.
- Live K8 matches an independent oracle on **34 of 34** pools.
- The controller's run: 2,936 passed, guards and docpins green, **2 failed** (Q1).

**This round:** one commit. Each item gets its test and its named mutant, in the body. Keep `test_surf_screen.py`,
`test_surf_signals.py`, `test_surf_swarm_inflight.py` **and `tests/data/test_surf_client.py`** in the pre-commit
set. Never merge, push or tag.

**Q1 · Two red tests (must fix).** `tests/data/test_surf_client.py::test_every_fetcher_survives_total_outage_as_none`
and `::test_no_fetcher_turns_outage_into_zero`, both `[fetch_launch_receipts]`, fail with `TypeError: missing 1
required positional argument: 'tx_hashes'`.
- **Cause:** the new `SurfClient.fetch_launch_receipts` (`data/surf_client.py:1334`) is not in those tests'
  argument table.
- **Fix:** register it with sample `tx_hashes`, the way `fetch_launch_evidence` is registered, and make sure a total
  outage really returns `None` (not `[]` or `{}`).

**Q2 · The `liq` ladder must be monotonic: once `liq` appears, it stays at every wider width.**
- **Today** (mounted sweep 60–220, identical on both Textual versions):

  | Width | Tier | `liq` |
  |---|---|---|
  | 60–90 | tight | no |
  | 91–115 | tight | yes |
  | **116–129** | compact | **no** |
  | 130–156 | compact | yes |
  | **157–170** | roomy | **no** |
  | 171+ | full | yes |

- **Cause:** roomy's `tier_width + 14` equals full's step (166), so roomy can never show `liq`; the roomy branch is
  dead code. `test_launches_liquidity_at_owner_widths` pins the 157–170 gap as expected.
- **Fix** (*controller decision; the owner may veto*): **`liq` outranks `kind`, `repo` and `site`** at every tier.
  - **roomy** sheds `kind` instead of `liq`;
  - **compact** sheds `site` before `liq` (the SITES table shows every site anyway);
  - **tight** keeps today's set.

  The result must be monotonic from the width where `liq` first appears (today 91).
- **Then:** update `test_launches_liquidity_at_owner_widths` and `test_liquidity_tier_priority_and_degraded_cells`
  (drop the unreachable `column_plan('roomy', 166)` case), and add a **sweep test** asserting monotonic `liq`
  visibility over 60–220.
- **Re-measure:** the LAUNCHES onsets, the pin comment and `_S_THRESHOLDS`. The SWARM pin stays 129×35.
- **Mutant:** restore the roomy and compact rule.

**Q3 · Low.**
- **Lock line, non-factory owner:** append `(unverified)` when the owner has code (`eth_getCode` non-empty, read
  once and cached) and no verified source. If verified-source status is not available keyless, append
  `(contract)` for any owner with code. No live owner is affected today; all 34 are factories.
- **N03:** pin at manager level that an `ambiguous` pool shows `--`, not `…`.

**Report:** test counts on both Textual versions (the required files included), the new sweep result, and the
mutant list.
