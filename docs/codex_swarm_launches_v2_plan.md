# Codex plan: SWARM launches, round 2 (written 2026-10-06)

> **Do not use any superpowers skill.** This plan, the round-1 plan (`docs/codex_swarm_launches_plan.md`,
> c9352030), `docs/codex_swarm_launches_fix1.md`–`fix4.md` and `CLAUDE.md` are the whole process.

**Tier 2.** The owner asked for these changes on 2026-10-06 from two screenshots of the merged round-1 build: the
SWARM board's SITES table and the launch popup of #794. The questions marked *owner* were decided in chat. Every
line number is a starting point at autopull `33563899` (round 1 merged); verify it before editing.

**Fixtures:** `tests/fixtures/surf/swarm/v9/` (11 captures plus `MANIFEST.json`, 2026-10-06). The controller put it
in your clone **untracked**. Commit it in WP1, unchanged. Your sandbox has no network, so never re-capture.

---

## Part A: Spec

### A1. SITES: an actual `site` column (*owner*)

- Rename the `ens` column (`widgets/surf/swarm_sites.py:113-120`, key `ens`, `_ENS_COLS = 33` at `:100`) to
  **`site`**.
- **Show** the site's host, `<label>.sites.imd.fun`, for example `win.sites.imd.fun`, **linked** to
  `https://<label>.sites.imd.fun`.
- **Label source:** the row's derived label, exactly as round 1 builds the link (`label`, else `ensName` minus
  `.site.identitymd.eth`). A row with no valid label shows `--`.
- **The ENS name is no longer shown** in SITES. It stays in the data.
- **Width:** keep 33 cells. Clip long hosts with `…`, never inside `.sites.imd.fun`: clip the label part first.
- `site_text` (`widgets/address.py`) gains a display mode that renders the host instead of the ENS name. The link
  target is unchanged.

### A2. SITES: one blank line above the status bar (*owner*)

- **Requirement:** at every pin, a blank row sits between SITES' last visible line and the status bar. Remove one
  row of SITES' height for it, for example `margin-bottom: 1` on `SurfSwarmSites` or on `#surf-swarm-body`'s last
  child. Mirror it in `SurfScreen.DEFAULT_CSS` and `themes/minimal.tcss:2615`.
- **Re-measure** the SWARM pins (`surf.py` pin block, `test_surf_swarm_layout._S_THRESHOLDS`). SITES' onset moves
  by one row. The SWARM pin 129×35 must hold, or **stop and ask**.

### A3. Launch popup: describe each check (*owner*)

Every check heading gets a short plain description after the state (`screens/swarm_detail.py:120-134`):

| Check | Heading |
|---|---|
| K1 | `K1 · pass — a launch row on a production chain` |
| K2 | `K2 · pass — deployed by the swarm's launch wallet` |
| K3 | `K3 · pass — deployed code matches the swarm's attested build` |
| K4 | `K4 · pass — passed the swarm's admission checks` |
| K6 | `K6 · info — who holds the pool liquidity` |
| K7 | `K7 · info — outside audits or bounties on record` |
| K8 | `K8 · <state> — pool liquidity: paired amount, range, lock` (A5) |

- The description is dim. The state keeps its current words.
- At narrow popup widths the description clips first, with `…`.
- Sepolia rows keep `K<n> · --` with the description.

**Also fix the POOL FEE (a round-1 error from the round-1 brief).** `pool_fee` comes from `manifest.pool.fee`
(`analytics/surf_launch_checks.py:48`), which is **not** the live pool's fee. The pool's `Initialize` event in the
deploy receipt says otherwise:
- fee **12500** (1.25%) on every `custom_token` / `evm_project` pool;
- **3000** on the `univ4_hook` pools (#775, #784).

The manifest says 3000 for all of them. Take `pool_fee` from the receipt's `Initialize` event (A5.1), show it as a
percentage (`1.25%`), and fall back to `--`, never to the manifest.

### A4. LATEST LAUNCHES replaces THROUGHPUT (*owner*)

- **Placement:** same place, **same layout**: top row right, beside WORKFLOWS, `width: 1fr; max-width: 46;
  height: auto`, floor 9 rows (`#surf-swarm-top { min-height: 9 }`). THROUGHPUT's CSS rules become LATEST LAUNCHES'
  rules.
- **Park THROUGHPUT**, following the IN FLIGHT precedent:
  - unmount it, keeping its module, class, popup and tests;
  - add its signature to `SWARM_PARKED_WIDGET_SIGNATURES` (`surf_models.py:1664`);
  - its data keys and the scores sweep stay as they are.
- **Content:** the **5 newest production launches** (*owner*: production only), newest **`createdAt`** first, with
  `launchNumber` desc as the tiebreak. One line each, inside the 44 content cells:

  ```
  LATEST LAUNCHES · as of 14:16            (illustrative rows)

  ◆ #794 $AGENT    RH       ✓ swarm   3m
  ◆ #791 $PEPES    RH       ✓ swarm  41m
  ◆ #787 $SNIPER   RH       ✗ K4      1h
  ◆ #784 $WIN      RH       ✓ swarm   2h
  ◆ #782 --        MAINNET  ✓ swarm   2h
  ```

  - **Columns:** `◆ #n` (6), ticker (10, `--` / `#n` per round 1's F12 rule), chain word (7), verdict (9, round 1's
    words), age (`<1m`, `Nm`, `Nh`, `Nd`, from `createdAt` against `data["as_of"]`).
  - **Width order:** if the width is short, the age goes first, then the chain word. `#n` and the verdict always
    survive.
- **Empty and failed reads:** with no production launch, `no production launch yet` (dim). A failed read is
  `unavailable` (yellow).
- **Interaction** (*owner*): Enter or a click on a row opens that launch's `LaunchDetailScreen`. **`x` on the SWARM
  board opens the popup of the top row**; with no row, `x` does nothing. `action_toggle_throughput` (`surf.py:3769`,
  binding `:2633`) is re-pointed in SWARM mode; other bodies keep what `x` does there. `KEY_HINTS` still says
  `x more`.
- **Data:** the widget reads `swarm_launch_rows` (already carrying every field) plus `swarm_launches_as_of_hhmm`.
  Its signature is frozen in WP1.

### A5. K8: v4 pool liquidity (*owner*: popup **and** a LAUNCHES `liq` column)

**A5.1 Inputs.** Everything comes from the **deploy receipt** that K2 / K6 already read:
- **`Initialize` log** (topic0 `0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438`, emitted by that
  chain's **PoolManager**; record the emitter):
  - `topics[1]` = poolId, `topics[2]` = currency0, `topics[3]` = currency1;
  - data words: `fee`, `tickSpacing`, `hooks`, `sqrtPriceX96`, `tick`.
- **The deploy `ModifyLiquidity` log** (topic0 `0xf208f491…d5ec`), from the same PoolManager and pool:
  - owner = `topics[2]`;
  - data: `tickLower`, `tickUpper`, `liquidityDelta` (call it `L0`), `salt`.
- **No pool** (`evm_contracts`, or no `Initialize` in the receipt) → K8 `na`, column `--`.

**A5.2 Live reads** (3 calls per launch, batched): `PoolManager.extsload(bytes32)`, selector `0x1e2eaeaf`.
- `stateSlot = keccak256(poolId ‖ uint256(6))`
- `slot0 = extsload(stateSlot)`: `sqrtPriceX96 = low 160 bits`, `tick = signed int24 at bits 160–183`
- `poolLiquidity = extsload(stateSlot + 3) & (2**128 - 1)`
- `positionKey = keccak256(owner(20 bytes) ‖ int24 tickLower (3 bytes, two's complement) ‖ int24 tickUpper (3) ‖
  salt (32))`
- `positionLiquidity = extsload(keccak256(positionKey ‖ uint256(stateSlot + 6))) & (2**128 - 1)`
- `decimals()` (`0x313ce567`) of the paired currency, read once and cached. Native ETH (`0x0…0`) is 18.

This works on any chain whose PoolManager is the `Initialize` emitter: Ethereum `0x000000000004444c…8a90`, Robinhood
`0x8366a39c…0951`. The v9 fixtures hold these exact reads for #737, #747, #775 and #791, and the MANIFEST says which
id is which.

**A5.2 Cadence:** re-read K8 every **300 s** per production launch with a pool, at most 10 launches per cycle,
oldest-read first. Persist the last result with its `read_ts`. K8 is market state, never final. A failed read keeps
the last good result, and the popup shows its age.

**A5.3 Derived values.**
- **Amounts** of the position at the current price: with `sa = 1.0001^(tickLower/2)`, `sb = 1.0001^(tickUpper/2)`,
  `sp = sqrtPriceX96 / 2^96`:
  - if `sp ≤ sa`: amount0 = `L·(sb−sa)/(sa·sb)`, amount1 = 0;
  - if `sp ≥ sb`: amount0 = 0, amount1 = `L·(sb−sa)`;
  - otherwise: amount0 = `L·(sb−sp)/(sp·sb)`, amount1 = `L·(sp−sa)`.

  Float is fine for display.
- **Paired currency:** the currency that is not the launch's token artifact (match on the address). The paired
  amount is that side's amount divided by `10^decimals`.
- **Range state:**
  - `in range` when `tickLower ≤ tick < tickUpper`, so two-sided: both currencies are present;
  - **`at limit`** when `|tick| ≥ 887271`, so no active liquidity. Measured on #747, #741, #740 and #754 today: the
    price has been pushed to the edge;
  - otherwise **`token only`** (only the launch token, no paired liquidity) or **`paired only`** (all of the token
    bought out), by which amount is zero.
- **Lock:**
  - `burned` if the owner is `0x0…0` or `0x0…dEaD`;
  - **`withdrawn`** (red) if `positionLiquidity < L0`, shown with the percentage removed; `positionLiquidity == 0` is
    `withdrawn 100%`;
  - otherwise **`locked`**: when the owner is a policy factory or the deploy tx's `to`, show `in factory (unverified)`.
    Measured: every live pool today has `positionLiquidity == L0`, held by factories `0xff03…`, `0x12c63b58…`,
    `0x9c9d2fcb…` or `0xa25b02a1…`, all unverified. **Never write "burned" for these.**
- **Other LPs:** `positionLiquidity / poolLiquidity` while in range. Above 1.0 is impossible, so show it as the
  share held by the launch position.

**A5.4 K8 state** (information, like K6; it **never** changes `verdict`, which stays provenance):
- `info` normally;
- `warn` for `withdrawn`, `at limit`, or `token only` older than 1 h (no buys at all yet);
- `na` with no pool;
- `unknown` when a read is missing.

**A5.5 Popup K8 section:**
- `paired 4,726.59 IMD · token 268,252,380 ZTO · in range`;
- `pool fee 1.25% · tick 106080 in [-887220, 128940]`;
- `liquidity locked in factory 0xff03…7120 (unverified) · never withdrawn (L = deployed L)`;
- `launch position 100% of active liquidity`;
- `as of 14:16`.

Addresses link through the chain explorer, as elsewhere.

**A5.6 LAUNCHES `liq` column**, width 12, placed after `verdict`. Shed it before `repo` at `compact`; keep it at
`tight` only if the width allows, and **never ahead of ticker or verdict**.

| Liquidity | Cell |
|---|---|
| in range | `4.7K IMD` / `14.2 ETH` (compact number + paired symbol) |
| token only | `one-sided` (dim) |
| at limit | `no liq` (yellow) |
| withdrawn | `withdrawn` (red) |
| no pool | `--` |
| not read yet | `…` |
| Sepolia | `--` |

**A5.7 Contract.** Freeze in WP1:
- `swarm_launch_rows` gains `liquidity` = `{state, range_state, paired_symbol, paired_amount, token_amount, pool_fee,
  tick, tick_lower, tick_upper, owner, owner_is_factory, lock, withdrawn_pct, share, read_ts}`. It is `None` on
  Sepolia; it is the K8 shape inside `checks`.
- `SURF_ROW_KEYS` lists it exactly.
- The facts slot persists the A5.1 inputs (they never change) and the last A5.3 result. Validate on load like the
  other K evidence.

### A6. Fix round 4 (H1–H3), folded in

`docs/codex_swarm_launches_fix4.md` H1–H3 are part of this round:
- **H1:** a parked launch's K4 frozen on an empty admission list (#787);
- **H2:** the `extra_count` test;
- **H3:** the nits.

### A7. Out of scope

- USD values.
- Copycat search.
- Self-deployed tokens (ADAM-style, NFT positions).
- Any "safe" or "audited" wording.
- "burned" for factory-held liquidity.

---

## Part B: Plan

### B0. Where to work

```bash
cd /Users/banse/codex/maxpane
git fetch autopull && git switch -c feature/swarm-launches-2 autopull/main   # = 33563899 (round 1 merged)
```

The untracked v9 fixtures and this plan stay in the working tree across the switch. Commit the fixtures in WP1.

### B1. Rules

The round-1 plan's B1, unchanged. **Every pre-commit set includes** `tests/analytics/test_surf_signals.py`,
`tests/widgets/test_surf_swarm_inflight.py` and the new LATEST LAUNCHES and K8 tests. Run the click and selection
tests on Textual 8.1.1 and 8.2.8. Record every mutant in the commit body.

### B2. Work packages

| WP | Content | Stop |
|---|---|---|
| WP1 | v9 fixtures commit · contract freeze (A4 signature, A5.7 keys, THROUGHPUT parked signature) · `site_text` host mode · pool-fee source | none |
| WP2 | Data: A5.1–A5.4 K8 (receipt parsing, extsload batch on chain 1 and RH clients, cadence, persistence) · pool fee from `Initialize` · A6 H1/H3 data parts | none |
| WP3 | Widgets: A1 SITES site column · A4 LATEST LAUNCHES · A5.6 `liq` column · A3 popup headings and K8 section · A6 H2 | none |
| WP4 | Screen: A2 blank line and CSS · THROUGHPUT parked, LATEST LAUNCHES mounted · the `x` re-point · pins re-measured | **STOP: the owner's live look** |
| WP5 | Hardening: B3 regressions with mutants, docs (`.claude/rules/surf.md` SITES / LAUNCHES / K-checks / layout; CHANGELOG), layout pins | report for verification |

### B3. Named regressions (each must redden under its named mutant)

1. SITES shows `win.sites.imd.fun` (the host, not the ENS name) and links it; a null-label row with a valid
   `ensName` shows its derived host. *Mutant: render `ens_name`.*
2. At every pin, a blank row separates SITES from the status bar. *Mutant: drop the margin.*
3. Popup headings carry their descriptions; the K8 section shows paired amount, range, lock and share. *Mutant: drop
   a description.*
4. Pool fee: #737 and #747 show `1.25%`, #775 shows `0.3%`, from `Initialize`. *Mutant: use `manifest.pool.fee`.*
5. LATEST LAUNCHES shows the 5 newest **production** launches by `createdAt`. Sepolia never appears. In
   `v8/launches_100.json`, #747 (created after #751) sorts above #751. Enter or a click opens the popup; `x` opens
   the top row's popup; THROUGHPUT is parked. *Mutants: sort by number; include Sepolia.*
6. K8 from the v9 fixtures:
   - **#737**: in range, ≈4,726.59 IMD, locked in factory, never withdrawn, share 100%;
   - **#747**: `at limit`, `no liq`;
   - **#775**: in range, ≈14.23 ETH, factory `0x12c63b58…`, fee 0.3%;
   - **#791**: in range on RH, ≈0.1013 IMD.

   *Mutants: owner `topics[1]`; position key without salt; tick unsigned.*
7. **Withdrawn and burned:** a synthetic `positionLiquidity = L0/2` gives `withdrawn 50%`, red; owner `0x…dEaD`
   gives `burned`. Factory-held is never `burned`. *Mutant: `<=` for `<`.*
8. **K8 never changes the verdict:** a `withdrawn` #737 is still `✓ swarm`, with `liq` red.
9. **Cadence:** K8 reads at most 10 launches per cycle, re-reads each after 300 s, and keeps the last good result on
   a failed read.
10. **H1–H3** as specified in fix4.
