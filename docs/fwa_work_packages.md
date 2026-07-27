# FWA "Gacha Terminal" — Work Packages

> Created: 2026-07-26
> Source: [`docs/fwa_implementation_plan.md`](fwa_implementation_plan.md) · Spec:
> [`docs/fwa_PRD.md`](fwa_PRD.md) (APPROVED, authoritative)
> **21 work packages across 7 waves. Peak concurrency: 7 agents. ~65 new files, ~132 new tests.**
>
> All four open questions were ruled on by the user on 2026-07-26 and are folded in here: the module
> splits are **approved and PRD §6 amended to match**; the theme is a **full registered `fwa` Theme**,
> not CSS alone; the **post-emissions state is the PRIMARY tested case**; and WP-21 backfills the
> missing Talismans README rows. Nothing below is pending approval.

Every agent must read, before writing any code:

1. `/Library/Vibes/autopull/docs/fwa_PRD.md` — the spec. §7 (ten correctness rules) and §13 (open
   questions that must not be displayed) are binding on every WP.
2. `/Library/Vibes/autopull/docs/fwa_technical_findings.md` — addresses, signatures, topics, decode
   notes, endpoints, rate limits.
3. `/Library/Vibes/autopull/docs/fwa_implementation_plan.md` — §8 architecture, §10 correctness
   traceability, §11 suppression list, §12 degradation matrix, §14 file ownership.

Global rules, non-negotiable in every WP:

- **READ-ONLY.** No signing, no sending, no key prompts, no `keystore`/`eth_account`/private-key
  imports anywhere in FWA code.
- **KEYLESS.** Banned hosts: `eth.llamarpc.com`, `rpc.ankr.com`, `api.reservoir.tools`,
  `api-mainnet.magiceden.dev`, `sourcify.dev`, `etherscan.io`, `api.etherscan.io`.
- **No test may touch the network.** Fixtures only.
- **Widgets never import models, clients or analytics.** `update_data()` takes primitives.
- **Only the owner WP writes a shared file.** See plan §14. If your WP is not listed as owner of
  `app.py` / `game_select.py` / `__main__.py` / `minimal.tcss` / `themes/__init__.py`, do not open
  them for writing.

---

## Dependency graph

```
WAVE 1 ── no dependencies, start immediately
  WP-1  Interface freeze .................. [Backend Architect]      M
  WP-2  ABI vendoring + enums + topics .... [Evidence Collector]     M
  WP-3  Offline fixture corpus ............ [Evidence Collector]     M
  WP-4  EV & pricing math (TDD) ........... [AI Engineer]            L

WAVE 2 ── 7 in parallel
  WP-5  analytics/fwa_signals.py .......... [Senior Developer]       M   <- 1, 4
  WP-6  data/fwa_client.py   (state pool) . [Data Engineer]          L   <- 1, 2, 3
  WP-7  data/fwa_logs.py     (log pool) ... [Data Engineer]          L   <- 1, 2, 3
  WP-8  data/fwa_market.py   (off-chain) .. [API Tester]             M   <- 1, 3
  WP-9  data/fwa_cache.py ................. [Data Engineer]          M   <- 1
  WP-10 Widgets A (3) ..................... [Frontend Developer]     M   <- 1
  WP-11 Widgets B (4) ..................... [Frontend Developer]     M   <- 1

WAVE 3 ── 3 in parallel
  WP-12 data/fwa_manager.py ............... [Backend Architect]      L   <- 4,5,6,7,8,9
  WP-13 screens/fwa.py + widgets __init__ . [UI Designer]            M   <- 10, 11
  WP-14 Refresh-budget benchmark .......... [Performance Benchmarker] M  <- 6, 9

WAVE 4 ── 2 in parallel
  WP-15 Degradation suite ................. [API Tester]             M   <- 12, 13
  WP-16 Full fwa Theme + CSS + tests ...... [UI Designer]            M   <- 13

WAVE 5 ── 1 (owns all shared files)
  WP-17 Registration ...................... [Senior Developer]       S   <- 12, 13, 16

WAVE 6 ── 2 in parallel
  WP-18 Correctness/scope guardrails ...... [Reality Checker]        M   <- 17
  WP-19 Accessibility & theme audit ....... [Accessibility Auditor]  S   <- 17

WAVE 7 ── 2 in parallel
  WP-20 Full-suite integration ............ [Test Results Analyzer]  M   <- all
  WP-21 README + CLAUDE.md + docstrings ... [Technical Writer]       S   <- 17
```

Critical path: **WP-1 → WP-6 → WP-12 → WP-13 → WP-16 → WP-17 → WP-18 → WP-20**

---

# WAVE 1

---

## WP-1 — Interface freeze: models + flat-dict contract + widget signatures

**Agent:** Backend Architect
*Why:* this WP produces nothing but boundaries. It is the single contract that seven wave-2 agents
code against simultaneously; getting the seams right is architecture work, not implementation work.

**Dependencies:** none · **Wave:** 1 · **Size:** M · **Blocks:** WP-4 (soft), WP-5, WP-6, WP-7,
WP-8, WP-9, WP-10, WP-11, WP-12, WP-13

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_models.py`
- `/Library/Vibes/autopull/tests/data/test_fwa_models.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/data/talismans_models.py` — frozen-model style, the
  docstring-as-contract convention, `TalismanSignal` shape
- `/Library/Vibes/autopull/maxpane_dashboard/data/ttt_models.py`
- `/Library/Vibes/autopull/docs/fwa_PRD.md` §5, §6 · `docs/fwa_implementation_plan.md` §8.5

**Work**

1. Ten frozen (`model_config = ConfigDict(frozen=True)`) Pydantic models. The seven from PRD §6,
   named exactly as the PRD names them, plus three plumbing models:

   | Model | Fields (indicative — finalize types here) |
   |---|---|
   | `Position` | `listing_id, collection, depositor, allocatee, token_id, weight, backing_wei, fee_share, fee_debt, slot, allocated_at, status` |
   | `CollectionOdds` | `address, name, positions, weight, weight_share_pct, eth_backed, floor_eth: float\|None, floor_source: str, eth_per_odds_point: float\|None, floor_note: str` |
   | `PullEV` | `lower_eth, best_eth, fee_eth, rebate_eth, collections_priced: int, collections_total: int, weight_priced_pct: float` — **no `point_eth` field exists**; the band is structural |
   | `Crown` | `listing_id, depositor, pot_wei, seize_wei, threshold_bps, share_bps, vacant: bool` |
   | `PoolTemp` | `seconds_since_last_request, token_share_bps: int, hot_gap, cold_gap, forced_share_bps: int` (signed — `-1` means dynamic) |
   | `ConfigParam` | `key: int, name: str, value: int, block_number: int, is_drift: bool` |
   | `SettlementMix` | `outcome: str, count: int, share_pct: float` |
   | `FWASignal` | `label, value_str, indicator, color` — identical contract to `TalismanSignal` |
   | `DrawEvent` | `ts, block_number, tx_hash, purchaser, collection, token_id, outcome, outcome_label, amount_eth` |
   | `FWASnapshot` | `fetched_at, block_number, positions, crown, pool_temp, params, ...` |

   `backing_wei` / `pot_wei` / `weight` stay **`int`** — never floats. Wei→ETH conversion happens at
   the presentation boundary only.

2. Export **`FWA_DATA_KEYS: tuple[str, ...]`** — every key `FWAManager.fetch_and_compute()` returns,
   grouped and commented by consumer widget. Use the draft in implementation-plan §8.5 as the
   starting point; you own the final names. Include every `*_available` flag — a widget must be able
   to render an explicit unavailable state without inferring it from `None`.

3. Export **`FWA_WIDGET_SIGNATURES: dict[str, tuple[str, ...]]`** mapping each of the seven widget
   class names to its exact `update_data()` kwarg names. This is what lets WP-10/WP-11 and WP-12 be
   written concurrently and verified mechanically.

4. Document in the module docstring, tersely and unambiguously: the inverse-weight rule; that
   `settlement_discount_bps == 8500` is the **purchaser payout rate**, not a discount; that
   `weighted_backing_total` is neither wei nor ETH and must never be labelled TVL; and that
   `forced_share_bps` is **signed int256**.

**Tests (~8)**
- all ten models construct from representative data and are immutable (mutation raises)
- `FWA_DATA_KEYS` has no duplicates and every entry is a valid identifier
- `FWA_WIDGET_SIGNATURES` covers exactly the seven PRD §5 widget classes
- every kwarg in `FWA_WIDGET_SIGNATURES` appears in `FWA_DATA_KEYS`
- `PullEV` has no attribute named `point_eth`, `value_eth` or `ev_eth` (band-only guard)
- `PoolTemp.forced_share_bps` accepts `-1`
- `Position.backing_wei` rejects a float

**Acceptance criteria**
- `from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS, FWA_WIDGET_SIGNATURES` works
- Zero imports of any client, cache, analytics or Textual module
- No wei value is typed `float` anywhere
- `pytest tests/data/test_fwa_models.py` green

---

## WP-2 — Vendor the 8 ABIs, recover the two enums, emit topics + selectors

**Agent:** Evidence Collector
*Why:* this is provenance work — retrieve artifacts keylessly, prove they match the live bytecode,
record where each came from, and leave nothing in shipped code that phones home.

**Dependencies:** none · **Wave:** 1 · **Size:** M · **Blocks:** WP-6, WP-7

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/fwa_core.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/fwa_rewards.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/fwa_vrf_service.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/fwa_token.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/fwa_token_hook.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/fwa_claim.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/fwa_whitelist.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/splitter.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/topics.json`
- `/Library/Vibes/autopull/maxpane_dashboard/abis/fwa/selectors.json`
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_enums.py`
- `/Library/Vibes/autopull/scripts/vendor_fwa_abis.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/abis/cattown/` — vendored-ABI directory convention
- `/Library/Vibes/autopull/maxpane_dashboard/abis/multicall3.json`
- `docs/fwa_technical_findings.md` §2 (addresses + expected ABI entry counts), §3 (acquisition
  sources), §6.6 (the unread enums), §8 (the 9 confirmed topic0 hashes + full event list)

**Work**

1. Write `scripts/vendor_fwa_abis.py`: a **one-shot, research-only** script that fetches all 8 ABIs
   keylessly and writes them to `maxpane_dashboard/abis/fwa/`. Preference order:
   `https://anyabi.xyz/api/get-abi/1/{addr}` (keyless mirror), then the Etherscan HTML page with a
   plain User-Agent (ABI JSON in `<pre id="js-copytextarea2">`). Sourcify 404s for all 8 — do not try
   it. Etherscan API v1/v2 requires a key — forbidden.
   **The script must be imported by nothing.** Add a module-level docstring saying so explicitly.

2. Verify each ABI before committing:
   - entry counts match findings §2: core **172**, rewards **112**, vrf **71**, token **87**, hook
     **52**, claim **31**, whitelist **34**, splitter **59**
   - the ABI contains the getters the dashboard depends on (`quoteAcquisitionPrice`, `listings`,
     `slotToListing`, `activeListingCount`, `totalWeight`, `weightedBackingTotal`, `topListingId`,
     `topListingPot`, `topThresholdBps`, `topListingShareBps`, `settlementDiscountBps`,
     `feeShareTotal`, `lastIssuedSequence`, `nextSequenceToProcess`, `unfulfilledVrfCount`,
     `pendingAcquisitionCount`, `unsettledAcquisitionCount`, `reservedStagedCount`,
     `accruedOwnerFees`, `acquisitionEscrowTotal`; rewards `emissionStart`, `currentEpoch`,
     `hotGap`, `coldGap`, `forcedTokenShareBps`, `lastAcquisitionTs`, `tokenShareBps`,
     `purchaserDailyPot`, `depositorRatePerSec`; vrf `requestFee`, `subscriptionNativeBalance`,
     `minimumSubscriptionBuffer`, `availableProcessorSurplus`; hook `externalBuysEnabled`;
     whitelist `TTT_AMOUNT`, `collectionWhitelisted`; splitter `totalReceived`)
   - the getters findings §12.1 proves **do not exist** are absent (`surchargeBps`,
     `whitelistEnabled`, `minBacking`, `protocolFeeToTokenBps`, `INVERSE_WEIGHT_NUMERATOR`,
     `acquisitionsEnabled`, `activeCount`, `emissionEnd`) — if any appears, flag it, do not use it

3. Generate `topics.json`: `{event_name: {"topic0": "0x…", "signature": "Name(type,…)",
   "indexed": [...] }}` for **every** event in the core ABI (38) plus the satellite events
   (`FWARewards.ListingRewardRepriced`, `FWATokenHook.ExternalBuysEnabledSet`,
   `FWAWhitelist.BurnedForWhitelist`, `FWAWhitelist.TTTAmountSet`). Computed locally from the
   canonical signature via keccak-256. **Must reproduce all 9 topic0 hashes recorded in findings §8
   exactly** — that is the correctness check on your keccak.

4. Generate `selectors.json`: `{signature: "0x…"}` for every view function used, again computed
   locally. Must reproduce the recorded selectors: `quoteAcquisitionPrice()` = `0x987df4cd`,
   `activeListingCount()` = `0x4681a7c6`, `listings(uint256)` = `0xde74e57b`,
   `slotToListing(uint256)` = `0xe2881eb7`, `aggregate3` = `0x82ad56cb`.

5. Write `data/fwa_enums.py` recovering **`ListingStatus`** and **`AcquisitionStatus`** from the
   vendored ABI/source (findings §12.2 item 4 — these are the two unread enums). Expose them as
   plain `dict[int, str]` maps plus a `listing_status_label(n)` / `acquisition_status_label(n)`
   helper that returns `f"status {n}"` for any unrecovered value. Empirically `1 == Active`; 2, 3, 4
   were observed. **If the enum names cannot be recovered from the ABI, ship the fallback labels and
   say so in the docstring — do not guess names.**

6. Also emit `abis/fwa/config_keys.json`: the `ConfigSet` key → parameter-name map from findings §8
   (keys 1,2,7,10-25,40-44,60-63). This is what turns one topic filter into the whole
   parameter-drift widget.

**Tests** — none of its own; WP-6/WP-7 tests consume these artifacts. Acceptance is verified by
assertion inside the script and by the WP-20 sweep.

**Acceptance criteria**
- All 8 ABI files parse as JSON arrays with the documented entry counts
- `topics.json` reproduces all 9 known topic0 hashes bit-for-bit
- `selectors.json` reproduces all 5 known selectors bit-for-bit
- `fwa_enums.py` imports with no network access and no dependency on `scripts/`
- `grep -r "etherscan" maxpane_dashboard/` returns nothing
- Nothing under `maxpane_dashboard/` imports `scripts/vendor_fwa_abis.py`

---

## WP-3 — Offline fixture corpus

**Agent:** Evidence Collector (second instance — disjoint files from WP-2)
*Why:* every later WP is required to be network-free. Somebody has to go get the real bytes once,
prove they are real, and commit them. That is evidence collection.

**Dependencies:** none · **Wave:** 1 · **Size:** M · **Blocks:** WP-6, WP-7, WP-8; supports WP-4

**Files to create** (all under `/Library/Vibes/autopull/tests/fixtures/fwa/`)
- `listings_56508.json` — the recorded raw 352-byte `eth_call` return for `listings(56508)`
- `aggregate3_positions.json` — a recorded Multicall3 `aggregate3` return blob covering ≥ 3
  `listings` calls (success + one deliberate `allowFailure` miss)
- `aggregate3_slots.json` — a recorded `slotToListing` batch return **including zero results**, so
  the free-list-hole path is exercised
- `hot_batch.json` — a recorded ~30-view hot Multicall3 return across all 8 contracts
- `quote_acquisition_price.json` — the returned `(fee, vrf, total)` tuple with the `gasPrice`/`gas`
  params that produced it recorded alongside
- `pinned_aggregates.json` — `{block, totalWeight, weightedBackingTotal, acquisitionFee,
  activeListingCount}` for blocks **25612655** and **25612701**
- `backing_distribution.json` — the 3,867 backing values (or a faithful reduced set with the
  documented min/median/max/total/harmonic/arithmetic preserved)
- `logs_acquisition_requested.json`, `logs_settlements.json` (all four outcome events),
  `logs_top_listing_set.json` (**must contain at least one vacate+set pair**),
  `logs_top_listing_settled.json`, `logs_config_set.json` (all 6 events),
  `logs_collection_whitelist_set.json` (51 collections), `logs_backing_updated.json`
- `coingecko_nft_200.json`, `coingecko_nft_404.json`, `coingecko_nft_429.json`
- `dexscreener_fwa.json`, `geckoterminal_ohlcv_hour.json` (100 candles),
  `defillama_fees_summary.json`
- `rpc_errors.json` — recorded error bodies: publicnode `eth_getLogs` refusal, drpc
  `"ranges over 10000 blocks are not supported"`, publicnode 429, the Multicall3
  `"cannot unmarshal invalid hex string"` rejection

**Files to read**
- `docs/fwa_technical_findings.md` §4.2 (the verified `listings(56508)` field values), §6.1 (the
  pinned-block aggregates), §8 (topic0 + counts), §9 (endpoint payload shapes), §10 (CoinGecko
  behaviour), §11 (rate-limit error strings)

**Work**

1. Record each payload once, keylessly, from the endpoint documented for it. Pin `blockTag` for
   every chain read so the fixture is reproducible.
2. Store the **raw** response body, not a parsed convenience form — the whole point is to test the
   decoders.
3. Add a `_meta` block to every fixture: source URL, method, params, block number, capture
   timestamp. A fixture with no provenance is not acceptable.
4. Include a `README` key inside `pinned_aggregates.json` stating the expected derived values so
   WP-4 can assert against them without re-deriving from prose.
5. If a payload cannot be captured live, hand-construct it from the hex/values already quoted in
   `fwa_technical_findings.md` and mark `_meta.source = "reconstructed from findings §N"`.

**Tests** — one smoke test may live in `tests/data/test_fwa_client.py` (WP-6): every fixture file
loads and has a `_meta` block.

**Acceptance criteria**
- Every fixture parses, has `_meta` provenance, and contains raw bodies
- `listings_56508.json` decodes to the 11 documented values, in particular
  `value == 221000000000000000000` and `weight == 4524886877828054`
- `logs_top_listing_set.json` contains at least one vacate+set pair (so WP-7's dedupe is testable)
- `aggregate3_slots.json` contains at least one zero result
- Total fixture size stays reasonable (< ~2 MB); reduce the backing distribution if needed while
  preserving the documented statistics

---

## WP-4 — EV & pricing math, strict TDD

**Agent:** AI Engineer
*Why:* probability-weighted expectation over an inverse-weighted distribution, option value under a
post-draw choice, and coverage-aware estimation with a third of the mass unpriced — this is
statistical modelling under partial information, not plumbing. *Acceptable alternative:* Senior
Developer, if integer-exactness is judged the dominant risk over the estimation design.

**Dependencies:** none (operates on primitives, not models — deliberately, to keep it in wave 1)
**Wave:** 1 · **Size:** L · **Blocks:** WP-5, WP-12

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/analytics/fwa_ev.py`
- `/Library/Vibes/autopull/tests/analytics/test_fwa_ev.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/analytics/ev.py` — repo precedent for a pure EV module
- `/Library/Vibes/autopull/maxpane_dashboard/analytics/talismans_signals.py` — pure-function style
- `docs/fwa_PRD.md` §3 (the EV formula and the band), §4 (surcharge ramp), §7 (rules 1, 2, 3, 4)
- `docs/fwa_game_mechanics.md` §5, §6, §11, §14.2 · `docs/fwa_technical_findings.md` §4.1, §6

**Work — write the tests first, from the numbers in the docs, then implement.**

The module is pure: stdlib only, no I/O, no model imports, no Textual. Signatures take primitives
(`list[int]` of wei backings, `dict[str, float]` of floors, ints of bps).

1. `inverse_weight(backing_wei: int) -> int` = `10**36 // backing_wei`. Integer floor division.
2. `total_weight(backings: list[int]) -> int`.
3. `weighted_backing_total(backings: list[int]) -> int` = `Σ(weight_i * backing_i)`. Docstring must
   state it is **neither wei nor ETH** and must never be rendered as TVL (rule 4).
4. `expected_value_wei(weighted_total: int, total_weight: int) -> int` — **one** floor division.
5. `acquisition_fee_wei(weighted_total: int, total_weight: int, surcharge_bps: int = 1000) -> int`
   = `ev * (10000 + surcharge_bps) // 10000` — the **second** floor division. Returns `0` when
   `total_weight == 0` (rule 2).
6. `harmonic_mean_wei(backings) -> int`, `arithmetic_mean_wei(backings) -> int`,
   `hm_am_gap(backings) -> float`. The harmonic mean is what the price tracks; the gap is the
   protocol in one number.
7. `selection_probability(backing_wei, total_weight) -> float` and
   `expected_draws_until(backing_wei, total_weight) -> float`.
8. `pull_ev_band(...) -> dict` — the flagship. Given per-position `(backing_wei, collection)`, a
   floor map, `purchaser_payout_bps` (**8500 = payout, not discount** — rule 3), the live
   `acquisition_fee_wei`, and the rebate share:
   - `lower_eth`: unknown floors counted as **0** — strictly pessimistic, cannot mislead
   - `best_eth`: unknown floors **excluded from the `max()`** rather than zeroed
   - `collections_priced`, `collections_total`, `weight_priced_pct`
   - `EV = Σ pᵢ · max(0.85·backingᵢ, floorᵢ) − acquisitionFee + rebateShare · surcharge`
   - **Invariant: `lower_eth <= best_eth` always.** Assert it in the function, not only in tests.
   - Never return a single "point" value. There is no such field.
9. `jackpot_ratio(max_backing_wei, fee_wei, payout_bps) -> float` — `max_backing × 0.85 / fee`
   (~1,378× at 221 ETH and a 0.1363 ETH fee) and its probability.
10. `crown_seize_wei(incumbent_backing_wei, threshold_bps) -> int` =
    `backing * (10000 + threshold_bps) // 10000` → 1.10× at 1000 bps.
11. `surcharge_ramp_share(gap_seconds, hot_gap, cold_gap) -> float` — the **fallback label only**.
    Docstring must state that linearity is unconfirmed (PRD §4, §13) and that the live
    `tokenShareBps` value always wins.
12. `take_rate(revenue, fees) -> float`, `per_position_credit(distributable, active_count) -> int`
    (equal split, rule 5), `settlement_shares(counts: dict) -> list[dict]`.
13. `round_trip_return(drawn_backing_wei, fee_wei, payout_bps) -> float` — surfaces the
    `0.85/1.10 = 0.773` structural −23%.

**Tests (~26)** — all offline, all from documented values:
- `test_inverse_weight_exact` — `10**36 // (221*10**18) == 4524886877828054`
- `test_total_weight_matches_onchain` — recompute from `backing_distribution.json`, assert
  `== 31217322873711845581134`
- `test_weighted_backing_total_matches_onchain` — assert
  `== 3866999999999999999373145521289217360095`
- **`test_acquisition_fee_bit_exact_25612655`** — from `weightedBackingTotal =
  3890999999999999999275601332649457427323` and `totalWeight = 31280618816683353089152`, assert
  `ev == 124390122292745553` and `fee == 136829134522020108` using `==`
- **`test_acquisition_fee_bit_exact_25612701`** — assert `fee == 136260883651302691`
- `test_acquisition_fee_zero_total_weight` — returns 0, does not raise
- `test_two_floor_divisions_not_one` — a case where doing the division in one step differs by ≥1 wei
- `test_harmonic_mean` / `test_arithmetic_mean` — recompute both from the **pinned** distribution
  and assert against that, never against the superseded 0.1247 / 0.5002 pair (findings §13.7) ·
  `test_gap_is_four_x` ≈ 4.0
- `test_punks_weight_share_rounds_to_zero` — 137.10 ETH over 3 positions → 0.000%
- `test_ttt_weight_share` ≈ 49.083%
- `test_ev_band_lower_le_best` (property-style over several floor maps)
- `test_ev_band_unknown_floors_zeroed_in_lower`
- `test_ev_band_unknown_floors_excluded_in_best`
- `test_ev_band_full_coverage_collapses_band` — lower == best when every floor is known
- `test_ev_band_zero_coverage` — best falls back to the sell-back-only expectation, does not raise
- `test_ev_band_reports_coverage` — `22/38` and a weight percentage
- `test_pure_flip_is_negative_ev` — ≈ −22% at the harmonic mean
- `test_payout_bps_is_payout_not_discount` — 8500 on 1 ETH backing yields 0.85 ETH, not 0.15
- `test_crown_seize_is_110pct`
- `test_jackpot_ratio_1378x`
- `test_surcharge_ramp_endpoints` — 0% at ≤60 s, 100% at ≥3600 s, monotonic between
- `test_per_position_credit_equal_split`
- `test_settlement_shares_sum_to_100` — 73.92 / 13.84 / 7.64 / 4.60 / 0.00
- `test_round_trip_return_is_0_773`
- `test_no_float_in_wei_paths` — every wei-returning function returns `int`

**Acceptance criteria**
- Zero imports outside the stdlib. No `pytest.approx` on any wei integer.
- Both bit-exact fee assertions pass with `==`
- `pull_ev_band` cannot return a single confident number — there is no field for one
- `pytest tests/analytics/test_fwa_ev.py` green

---

# WAVE 2

---

## WP-5 — Signals, badges, thresholds

**Agent:** Senior Developer
*Why:* threshold and state-machine judgement across five heterogeneous signals, with a hard rule
that every parameter is live and every degraded state has a defined label. Broad-context work with
many small correctness traps.

**Dependencies:** WP-1, WP-4 · **Wave:** 2 · **Size:** M · **Blocks:** WP-12

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/analytics/fwa_signals.py`
- `/Library/Vibes/autopull/tests/analytics/test_fwa_signals.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/analytics/talismans_signals.py` — signal-builder style,
  including its `SYNCING`-instead-of-false-alarm discipline (`conservation_signal`), which is exactly
  the posture FWA needs
- `/Library/Vibes/autopull/maxpane_dashboard/analytics/ttt_signals.py`
- `docs/fwa_PRD.md` §5 (the five signal rows), §7 rule 6, §8 · `docs/fwa_technical_findings.md` §7

**Work** — five builders, each returning an `FWASignal` (colors limited to
`green`/`yellow`/`red`/`dim`, indicator `●`):

1. `pool_temp_signal(seconds_since_last_request, token_share_bps, hot_gap, cold_gap, forced_bps)` —
   the timing dial nobody is trading. Must answer at a glance **which way the surcharge is flowing**:
   `HOT 12s · surcharge → depositors` (dim/red) … `COLD 41m · surcharge → YOU (100%)` (green), with a
   cold→hot gradient in between. Use the **live** `token_share_bps`; if it is unavailable fall back
   to `fwa_ev.surcharge_ramp_share` and mark the value as an estimate. `forced_bps != -1` means the
   dial is overridden — say so.
2. `buy_gate_signal(external_buys_enabled)` — red `GATED` / green `OPEN`. Must carry the footnote
   that DexScreener's ~11.4k "buys" are FWARewards-routed distributions, not open-market purchases
   (findings §9.2) — otherwise the UI reads as a contradiction.
3. `emissions_signal(now_ts, emission_start, emission_duration, current_epoch)` — **the
   post-emissions state is the PRIMARY case (user ruling).** After `1785870083 =
   2026-08-04T19:01:23Z`: `emissions ended`, dim. Implement and test that branch **first**; the live
   countdown before the stop is the secondary/legacy branch. **Never a negative countdown.** Never a
   hero tile (PRD §8).
4. `vrf_queue_signal(last_issued, next_to_process, pending, unsettled, unfulfilled_vrf,
   subscription_balance, minimum_buffer, selection_timeout_blocks)` — depth = `last_issued −
   next_to_process`; green when shallow, yellow when deep, **red when
   `subscription_balance < minimum_buffer`** (a depleted subscription stalls every acquisition).
5. `param_drift_signal(config_events, live_params)` — only 6 `ConfigSet` events exist ever, so this
   is cheap and exact. Green `params nominal` when live matches the last `ConfigSet`; yellow
   `N changes · crown tithe 500→100` style when drift is present. Never compares against documented
   values (rule 6) — only against onchain history.

Plus scalar helpers the manager needs: `invariant_summary(...) -> bool`, and
`degraded_label(source: str) -> str` producing the exact strings the widgets render
(`logs unavailable — activity paused`, `chain unavailable`, `as of HH:MM`).

**Tests (~16)**
- each builder: nominal, boundary, and unavailable-input cases
- `test_pool_temp_hot` (≤60 s → depositors), `test_pool_temp_cold` (≥3600 s → purchaser),
  `test_pool_temp_midband`, `test_pool_temp_forced_override`, `test_pool_temp_estimated_fallback`
- **`test_emissions_elapsed_never_negative`** (frozen clock past 1785870083 — **the primary case,
  write this one first**), then `test_emissions_counting_down` (frozen clock before the stop)
- `test_buy_gate_red_when_false`, `test_buy_gate_footnote_present`
- `test_vrf_queue_red_on_low_subscription`, `test_vrf_queue_depth_arithmetic`
- `test_param_drift_detects_tithe_change`, `test_param_drift_nominal`
- `test_all_signals_return_four_keys`, `test_all_colors_in_allowed_set`
- `test_no_documented_default_hardcoded` — module contains no `500`-as-crown-tithe literal

**Acceptance criteria**
- Pure functions; no I/O; only `fwa_models` + `fwa_ev` imported
- Every builder tolerates `None`/missing inputs and returns a dim, honest row rather than raising
- `pytest tests/analytics/test_fwa_signals.py` green

---

## WP-6 — State client (Pool A): Multicall3, position sweep, invariants, quote

**Agent:** Data Engineer
*Why:* batched RPC enumeration with a free-list trap, block pinning, hand-rolled ABI
encode/decode and a 500-call chunking cap. This is the highest-risk plumbing in the plan.

**Dependencies:** WP-1, WP-2, WP-3 · **Wave:** 2 · **Size:** L · **Blocks:** WP-12, WP-14

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_client.py`
- `/Library/Vibes/autopull/tests/data/test_fwa_client.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/data/talismans_client.py` — **copy `_rpc`, `_eth_call`,
  `_multicall`, `_encode_aggregate3`, `_encode_call3`, `_decode_aggregate3_result`, `_encode_uint`,
  `_decode_uint`, `_decode_address`, `_pad_left`, `_strip0x` verbatim.** Note `_encode_call3` already
  strips `0x` from callData (findings §6.5 trap, pre-solved) — keep it that way and test it.
- `/Library/Vibes/autopull/maxpane_dashboard/data/ttt_client.py` — retry/fallback shape.
  **Do not copy its RPC list** (llamarpc dead, Ankr keyed).
- `docs/fwa_technical_findings.md` §4 (all view signatures + decode notes), §6 (the recipe + 4
  traps), §7 (the gas-price gotcha), §11 (rate limits)

**Work**

1. `class FWAClient` with Pool A only: primary `https://ethereum-rpc.publicnode.com`, fallbacks
   `https://cloudflare-eth.com`, `https://1rpc.io/eth`. Multicall3
   `0xcA11bde05977b3631167028862bE2a173976CA11`. **Never `eth_getLogs` here** — publicnode refuses
   it; logs are WP-7's job.
2. `fetch_hot_batch() -> dict` — one Multicall3 `eth_call` of ~30 views across all 8 contracts,
   feeding the 15 s tier: `quoteAcquisitionPrice`, `acquisitionFee`, `totalWeight`,
   `weightedBackingTotal`, `activeListingCount`, `feeShareTotal`, `topListingId`, `topListingPot`,
   `topThresholdBps`, `topListingShareBps`, `settlementDiscountBps`, `retainedToProtocol`,
   `ownerAcquisitionFeeBps`, `ownerSettlementFeeBps`, `selectionSlippageBps`,
   `selectionTimeoutBlocks`, `settlementWindow`, `finalizeWindow`, `accruedOwnerFees`,
   `acquisitionEscrowTotal`, `acquisitionRefundCreditTotal`, `reservedStagedCount`,
   `pendingAcquisitionCount`, `unsettledAcquisitionCount`, `unfulfilledVrfCount`,
   `lastIssuedSequence`, `nextSequenceToProcess`; rewards `emissionStart`, `EMISSION_DURATION`,
   `currentEpoch`, `hotGap`, `coldGap`, `forcedTokenShareBps`, `lastAcquisitionTs`,
   `tokenShareBps(gap)`, `sqrtBackingTotal`; vrf `subscriptionNativeBalance`,
   `minimumSubscriptionBuffer`, `availableProcessorSurplus`; token `totalSupply`, `launched`,
   `lastBuybackBlock`; hook `externalBuysEnabled`; whitelist `TTT_AMOUNT`; splitter `totalReceived`,
   `claimablePerToken`. Chunk if it exceeds 500 calls.
   `forcedTokenShareBps` decodes as **signed int256** (`-1` = dynamic).
3. `fetch_eth_balance(address) -> int` — `eth_getBalance(core)`. **This is the only TVL source.**
   Never `weightedBackingTotal` (rule 4).
4. `quote_acquisition_price(gas_price_wei: int) -> tuple[int,int,int]` — `eth_call` with **explicit
   `gasPrice` AND bounded `gas`** (`0x200000`), because the node otherwise rejects with
   `insufficient funds for gas * price` and an unset gasPrice silently returns 0 (rule 9,
   findings §7). Render the returned tuple; never sum two sources; never assume a nonzero VRF fee.
5. `sweep_positions() -> tuple[int, list[Position], dict]` — the recipe, exactly:
   - pin `blockTag = eth_blockNumber()` and thread it through **every** call (trap 2)
   - `n = activeListingCount() @ blockTag`
   - Multicall3-batch `slotToListing(slot)` from slot 1 upward, **skip zeros**, stop once `n`
     non-zero ids are collected — **never** `slot = 1..n` (trap 1). Budget 1.2× headroom (~4,500).
   - Multicall3-batch `listings(id)` for every collected id at the same `blockTag`
   - assert all three aggregates bit-for-bit against onchain: `Σ(1e36//value) == totalWeight()`,
     `Σ(weight*value) == weightedBackingTotal()`, `(Σweighted//Σweight)*11000//10000 ==
     acquisitionFee()`. **Ship this as a runtime assertion, not just a test** (findings §6.2).
   - return `(block_number, positions, {"invariants_ok": bool, "collected": n, "expected": n})`
   - on shortfall or invariant mismatch: return what you have with `invariants_ok=False` so the
     manager can mark the odds board stale. **Never publish numbers derived from an incomplete sweep.**
6. `decode_listing(raw_hex) -> Position` — flat 11-tuple of static types, head-only, 352 bytes.
   `value` is backing in wei; `allocatee == 0x0` means unallocated; `status == 1` is Active. Use
   `fwa_enums` for labels.
7. `single_flight` guard on `sweep_positions` — if a sweep is in progress, the second caller gets the
   previous result immediately and the tick is skipped, never queued.
8. Fallback rotation, ≤500-call chunks, ~0.12 s inter-call spacing, exception-safe (network failure
   surfaces as an empty/zero return plus a flag, never an escaping exception into the refresh loop).

**Tests (~18)** — all fixture-driven, with a transport double that **raises on any real network use**:
- `test_hot_batch_decodes_all_views` from `hot_batch.json`
- `test_forced_token_share_bps_decodes_negative_one` (signed int256)
- `test_listings_decode_bit_exact` from `listings_56508.json` — all 11 fields
- `test_aggregate3_encoding_has_no_0x_in_calldata` — inspect the encoded payload (trap 4)
- `test_aggregate3_chunking_never_exceeds_500`
- `test_aggregate3_decode_handles_failed_call` (allowFailure miss)
- `test_slot_scan_skips_zeros` from `aggregate3_slots.json`
- **`test_slot_scan_stops_on_count_not_on_slot_index`** — the 3,624-of-3,879 regression guard
- `test_sweep_pins_block_on_every_call` — assert the same `blockTag` in every recorded request
- `test_sweep_invariants_pass` / `test_sweep_invariants_fail_marks_stale`
- `test_quote_passes_explicit_gasprice_and_gas`
- `test_quote_returns_tuple_not_sum`
- `test_eth_balance_used_for_tvl_not_weighted_backing_total`
- `test_fallback_rotation_on_429` / `test_all_endpoints_dead_returns_degraded`
- `test_single_flight_skips_overlapping_sweep`
- `test_no_eth_getlogs_in_this_module` — static check
- `test_all_fixtures_have_meta` (WP-3 smoke)

**Acceptance criteria**
- All three aggregate invariants asserted at runtime, not only in tests
- No `eth_getLogs` anywhere in the module; no banned host in the endpoint list
- Zero network access in the test suite (transport double proves it)
- `pytest tests/data/test_fwa_client.py` green

---

## WP-7 — Log client (Pool B): decoders, backfill + tail, crown dedupe

**Agent:** Data Engineer (second instance)
*Why:* a separate endpoint pool with different pagination semantics, 9 event decoders, a
double-counting trap, and the plan's single genuine point of failure. Cleanly separable from WP-6.

**Dependencies:** WP-1, WP-2, WP-3 · **Wave:** 2 · **Size:** L · **Blocks:** WP-12

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_logs.py`
- `/Library/Vibes/autopull/tests/data/test_fwa_logs.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/data/talismans_client.py` — `_get_logs` auto-pagination
  and the `_decode_*_log` decoder style (note how `Cut`'s operator is the **second** data word: the
  same "count your non-indexed words" discipline applies to every FWA event)
- `/Library/Vibes/autopull/maxpane_dashboard/data/ttt_cache.py` — `last_seen_block` tailing pattern
- `docs/fwa_technical_findings.md` §8 (all events + the 9 confirmed topic0 hashes + the ConfigSet key
  map + measured all-time counts), §3 (Pool B capabilities)

**Work**

1. `class FWALogClient` with **Pool B only**: primary `https://gateway.tenderly.co/public/mainnet`
   (no block-range cap), fallback `https://eth.drpc.org` (**hard 10,000-block pages**, no batching,
   occasional 408). **Never publicnode** — it refuses `eth_getLogs`. Auto-paginate per endpoint
   capability: uncapped on tenderly, 10,000-block chunks on drpc.
2. Decoders, topic0 from `abis/fwa/topics.json` (never hardcoded here):
   `AcquisitionRequested` (carries `acquisitionFee` and `totalWeight` in data → **a full price
   history is reconstructable from events alone**, no archive state needed), `NFTKept`,
   `DepositorBidAccepted`, `DepositorBidAcceptedAsTokens`, `NFTRelisted`, `UnsettledFinalized`,
   `NFTAllocated`, `TopListingSet`, `TopListingFunded`, `TopListingSettled`, `ConfigSet`,
   `CollectionWhitelistSet`, `BackingUpdated`.
3. **`TopListingSet` arrives in vacate+set PAIRS** (`listingId=0/address(0)` then the new holder).
   Dedupe on that or crown reigns double-count. This is a named acceptance criterion.
4. `backfill(from_block, to_block)` — one-time full-history scan on first run (~58 s for 9 event
   types) with a single `topics[0]` OR-filter per scan where possible; then
   `tail(last_seen_block)` on the 30 s tier. Persist by event type via WP-9's cache.
5. Derived products:
   - `settlement_mix()` → counts + shares for the five outcomes (all-time 38,083 / 7,133 / 3,934 /
     2,372 / 0)
   - `crown_history()` → deduped sets (33) and payouts (12, 91.096 ETH), largest 38.400795 ETH,
     one wallet with 4 reigns
   - `config_history()` → the 6 `ConfigSet` events resolved through `config_keys.json`
   - `collection_registry()` → the **51** collections from `CollectionWhitelistSet` (rule 7 — never
     the docs' 16)
   - `draw_events(limit)` → activity-feed lines pairing `AcquisitionRequested`/`NFTAllocated` with
     the settlement choice actually made
   - `backing_updates(since)` → invalidation signal for WP-6's cached sweep (rule 8)
6. **Degradation is the headline requirement.** Both endpoints failing must produce
   `{"available": False, "reason": "logs endpoint unavailable"}` plus whatever last-good aggregates
   the cache holds. It must never raise into the refresh loop and must never blank the dashboard.

**Tests (~14)**
- one decode test per event type from the recorded log fixtures
- **`test_top_listing_set_dedupes_vacate_pair`**
- `test_settlement_mix_shares_match_recorded_counts` (73.92 / 13.84 / 7.64 / 4.60 / 0.00)
- `test_crown_history_counts` — 33 sets, 12 payouts, 91.096 ETH
- `test_config_history_resolves_key_15_to_crown_tithe`
- `test_collection_registry_has_51`
- `test_price_history_reconstructed_from_acquisition_requested`
- `test_drpc_paginates_at_10000_blocks` / `test_tenderly_single_request_no_cap`
- `test_range_error_string_triggers_pagination` (from `rpc_errors.json`)
- **`test_both_endpoints_down_returns_unavailable_not_raise`**
- `test_tail_resumes_from_last_seen_block`
- `test_no_publicnode_in_endpoint_list` — static check

**Acceptance criteria**
- Pool B endpoints only; publicnode appears nowhere in this module
- Crown dedupe proven by test
- Total failure returns an explicit unavailable structure; no exception escapes
- `pytest tests/data/test_fwa_logs.py` green

---

## WP-8 — Off-chain client (Pool C): DexScreener, GeckoTerminal, CoinGecko floors, DefiLlama

**Agent:** API Tester
*Why:* four third-party HTTP contracts with hostile rate limits, partial coverage, one endpoint that
returns a bare number instead of JSON, and an opportunistic source that 401s unpredictably. The skill
here is endpoint-contract verification and failure classification.

**Dependencies:** WP-1, WP-3 · **Wave:** 2 · **Size:** M · **Blocks:** WP-12

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_market.py`
- `/Library/Vibes/autopull/tests/data/test_fwa_market.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/data/base_client.py` — `_wait_dexscreener` /
  `_wait_gecko` pacing helpers and retry shape (**reuse these**)
- `/Library/Vibes/autopull/maxpane_dashboard/data/price.py` — minimal CoinGecko client (note: it is
  `/simple/price` only; NFT floors are new work)
- `docs/fwa_technical_findings.md` §9 (exact payload shapes and observed values), §10 (the floor
  coverage table and the recommendation), §11 (TTLs)

**Work**

1. `fetch_fwa_market()` — DexScreener
   `/latest/dex/tokens/0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845`, exactly 1 pair. Take
   `priceUsd`, `priceNative`, `fdv`, `liquidity`, `volume.h24`, `txns.h24`, `priceChange.h24`,
   `pairCreatedAt`. 30 s TTL.
2. `fetch_ohlcv_hour()` — GeckoTerminal
   `/networks/eth/pools/0x230ecd3c…804d/ohlcv/hour?limit=100`, newest-first
   `[ts, o, h, l, c, v]`. **The v4 poolId is accepted directly** — it is not a contract address.
   Hard ceiling ~10 days of history (pool created 2026-07-16), so a sparse series is normal, not an
   error. **`market_cap_usd` is `"0.0"` and unusable — use DexScreener's `fdv`.**
3. `fetch_nft_floors(addresses)` — CoinGecko
   `/api/v3/nfts/ethereum/contract/{addr}`. **Background sweep only**, ≥2.5 s spacing, 15 min TTL,
   persisted per collection with a timestamp. Classify outcomes: `ok` (22), `missing` (11 hard 404),
   `rate_limited` (429 → keep previous value, mark stale). Never on the hot path.
   - **Suppress Art Blocks entirely**: `0x942BC2d3e7a589FE5bd4A5C6eF9727DFd82F5C8a` and
     `0xAB00000000002ADE39f58F9D8278a31574fFBe77` return
     `floor_note = "multi-collection contract — floor not meaningful"` and `floor_eth = None`.
     One contract hosts many collections with different floors; a per-contract number is simply false.
   - **Opportunistic gap-fill only:** OpenSea v2 `/collections/{slug}/stats` may be tried for
     CoinGecko 404s; any 401 is a **silent miss**, never an error, never a hard dependency
     (findings §12.2 item 11).
4. `fetch_protocol_fees()` — DefiLlama `/summary/fees/fake-world-assets` (+ `dataType=dailyRevenue`)
   for the take-rate cross-check. Note `/tvl/fake-world-assets` returns a **bare number, not JSON**.
   DefiLlama TVL ($3.21M) diverges sharply from the core balance (2,340-2,551 ETH) — **prefer the
   onchain balance always**; DefiLlama is a cross-check, not a display source for TVL.
5. Every method returns `(value, availability_flag)` and never raises. All four sources dying must
   degrade only the sparkline, the USD conversions and the floor column.

**Tests (~12)**
- `test_dexscreener_parses_single_pair` / `test_dexscreener_missing_pair_returns_unavailable`
- `test_ohlcv_parses_100_candles_newest_first` / `test_ohlcv_short_series_is_not_an_error`
- `test_gecko_market_cap_zero_is_ignored`
- `test_coingecko_floor_ok_200` / `test_coingecko_404_classified_missing` /
  `test_coingecko_429_keeps_previous_and_marks_stale`
- **`test_art_blocks_floor_suppressed`** — both addresses, `floor_eth is None`, note present
- `test_opensea_401_is_silent_miss`
- `test_coverage_summary_reports_22_of_38`
- `test_defillama_tvl_bare_number_handled`
- `test_min_spacing_enforced_between_coingecko_calls` (fake clock, no sleeping in tests)

**Acceptance criteria**
- No API key anywhere; no banned host
- CoinGecko calls are spaced ≥2.5 s and never invoked from a fast-tier path
- Art Blocks floors are structurally impossible to render as a number
- `pytest tests/data/test_fwa_market.py` green

---

## WP-9 — Tiered cache and persistence

**Agent:** Data Engineer (third instance)
*Why:* TTL tiers, hourly buckets, last-good snapshots and atomic persistence — a self-contained data
concern with a well-established in-repo pattern.

**Dependencies:** WP-1 · **Wave:** 2 · **Size:** M · **Blocks:** WP-12, WP-14

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_cache.py`
- `/Library/Vibes/autopull/tests/data/test_fwa_cache.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/data/talismans_cache.py` — hourly buckets, ring buffer,
  atomic temp+rename save, per-section try/except load, `last_seen_block` dict
- `/Library/Vibes/autopull/maxpane_dashboard/data/ttt_cache.py`

**Work**

1. `class FWACache` persisting to `~/.maxpane/fwa_cache.json` (atomic temp+rename, fail-soft on
   missing/corrupt).
2. **Per-tier TTL tracking**: `is_fresh(tier)` / `mark_fetched(tier)` for `fast` (15 s), `medium`
   (60 s), `slow` (900 s), `tail` (30 s). The manager asks the cache what needs fetching; tiers are
   not re-implemented in the manager.
3. **Last-good snapshots** — the mechanism the whole degradation story rests on. For each of the
   three pools, store the last successful payload with its timestamp and block so a widget can render
   `as of HH:MM` rather than blanking: last-good hot batch, last-good position sweep (+ its pinned
   block), last-good log aggregates, last-good floors (per collection, per timestamp).
4. Time series for the sparkline and trend rows: `$FWA` price hourly, `acquisitionFee` hourly,
   `active_positions` hourly, `crown_pot` hourly — 168 hours deep, `deque(maxlen=168)`,
   hour-bucketed like Talismans.
5. `last_seen_block: dict[str, int]` per event type for WP-7's tail.
6. Position-sweep invalidation: `invalidate_sweep(reason)` called on `BackingUpdated` or an invariant
   mismatch (rule 8). A cached sweep always carries its block and a `stale` flag.

**Tests (~8)**
- `test_ttl_per_tier` (fake clock: fast expires at 15 s, slow at 900 s)
- `test_last_good_survives_a_failed_fetch`
- `test_last_good_carries_timestamp_and_block`
- `test_hourly_buckets_capped_at_168`
- `test_persistence_roundtrip` / `test_corrupt_file_loads_empty_not_raise`
- `test_last_seen_block_roundtrip`
- `test_invalidate_sweep_marks_stale`

**Acceptance criteria**
- Only `fwa_models` imported; no client, no analytics, no network
- Corrupt or missing cache file never raises
- `pytest tests/data/test_fwa_cache.py` green

---

## WP-10 — Widgets A: hero metrics, odds board, sparkline

**Agent:** Frontend Developer
*Why:* Textual layout, DataTable column budgets and `None`-tolerant rendering. The hero card carries
the flagship band, which has a hard honesty requirement.

**Dependencies:** WP-1 · **Wave:** 2 · **Size:** M · **Blocks:** WP-13

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/fwa_hero_metrics.py`
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/fwa_odds_board.py`
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/fwa_sparkline.py`
- `/Library/Vibes/autopull/tests/widgets/test_fwa_widgets.py` (**you create this file; WP-11 appends
  to it — WP-11 depends on you for its existence, so land it early and keep the sections separated by
  a clear comment banner**)

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/talismans/tal_hero_metrics.py` — box structure,
  `_fmt_int`/`_fmt_float`, `"--"`-on-`None` discipline
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/talismans/tal_leaderboard.py` — DataTable +
  local format helpers
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/talismans/tal_sparkline.py` — **copy
  `_build_sparkline` and `_coerce_points` verbatim**
- `/Library/Vibes/autopull/maxpane_dashboard/templates/{hero_metrics,leaderboard,sparkline}_template.py`
- `/Library/Vibes/autopull/tests/widgets/test_talismans_widgets.py` — the test harness style
- `docs/fwa_PRD.md` §3, §5

**Work**

1. **`FWAHeroMetrics`** — `Horizontal` of **three** boxes (`height: 7` to match Talismans;
   `DEFAULT_CSS` carries `margin: 0 1`):
   - **PULL EV** — the band. Big number = best estimate, signed and green/red **plus a glyph** (`▲`/
     `▼`) so the sign is not encoded in color alone. Second line = `lower bound X.XXX ETH`. Third
     line = coverage badge `22/38 · N% of weight priced`. **The coverage badge must be present
     whenever any EV value is present** — this is a tested acceptance criterion, not a nicety. When
     `ev_available` is false: `—` plus `insufficient data`.
   - **PRICE** — live `acquisition_fee_eth` (and `vrf_fee_eth` only if the returned tuple says
     nonzero — never a computed guess), plus a compact harmonic-vs-arithmetic **gap bar**
     (`0.1063 ▏▏▏▏▏▏▏▏ 0.3709  3.5×` — illustrative only; all three values are computed live at
     the current block and none may be hardcoded, see findings §13.7).
   - **CROWN** — pot in ETH and USD, plus `ETH to seize` = `1.10 × incumbent backing`. Gold is used
     **only here** (PRD §11). Vacant crown renders `vacant`, not `0`.
2. **`FWAOddsBoard`** — `DataTable`, 38 rows sorted by weight share descending. Columns:
   `#`, `Collection`, `Pos`, `% Weight`, `ETH Backed`, `Floor`, `ETH/odds pt`. Must make the
   inverse-weight tension immediately legible: TTT **49.08%** at the top, CryptoPunks **0.000%** on
   137.10 ETH near the bottom. Floor cell: `—` when missing, `n/a` + the multi-collection note when
   suppressed. Width `3fr` (mirrors `TalismansLeaderboard`).
3. **`FWASparkline`** — `$FWA` price from 100 hourly candles. Reuse the two-row Talismans structure
   but with one series plus a `price · 24h Δ` line, so the vertical budget matches. `< 2` points →
   `waiting for data...`.

**Tests (~7 of the shared file's ~14)** — mount each widget in a tiny `App`, call `update_data()`
three ways (no args / all-`None` / full payload), assert no raise:
- `test_hero_renders_band_and_coverage`
- **`test_hero_never_shows_ev_without_coverage_badge`**
- `test_hero_ev_sign_has_glyph_not_only_color`
- `test_hero_crown_vacant_renders_vacant_not_zero`
- `test_odds_board_row_count_and_sort`
- `test_odds_board_missing_floor_renders_dash` / `test_odds_board_suppressed_floor_renders_note`
- `test_sparkline_short_series_waiting`

**Acceptance criteria**
- No import of `fwa_models`, any client, or any analytics module — primitives only
- Every `update_data()` kwarg matches `FWA_WIDGET_SIGNATURES` from WP-1
- All-`None` payload renders `--`/`—` everywhere and raises nothing
- `widgets/fwa/__init__.py` is **not** created here (WP-13 owns it)

---

## WP-11 — Widgets B: signals, activity feed, chase board, settlement table

**Agent:** Frontend Developer (second instance)
*Why:* four more Textual widgets, disjoint files from WP-10, including the two that must render
explicit degraded states.

**Dependencies:** WP-1 (+ WP-10 for the shared test file's existence) · **Wave:** 2 · **Size:** M
**Blocks:** WP-13

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/fwa_signals.py`
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/fwa_activity_feed.py`
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/fwa_chase_board.py`
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/fwa_settlement_table.py`

**Files to modify**
- `/Library/Vibes/autopull/tests/widgets/test_fwa_widgets.py` — **append your section below WP-10's
  banner. Do not touch WP-10's tests.**

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/talismans/tal_signals.py` — 4-row panel with
  spacer rows; FWA needs 5 rows
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/talismans/tal_activity_feed.py` — RichLog
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/talismans/tal_materials_table.py` — ranked
  DataTable (→ chase board)
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/talismans/tal_matrix_table.py` — sectioned table
  (→ settlement table)
- `docs/fwa_PRD.md` §5, §12 · `docs/fwa_implementation_plan.md` §12 (degradation matrix)

**Work**

1. **`FWASignals`** — 5 rows, same `{label, value_str, indicator, color}` contract and `_fmt_signal`
   helper as Talismans: pool temperature · buy gate · **emissions status** (normally
   `emissions ended` — the primary case; a live countdown only before 2026-08-04T19:01:23Z) · VRF
   queue depth · parameter drift. Pool temperature carries the cold→hot gradient; because it is the row that tells
   a user which way their money is flowing, it also carries a directional word (`→ YOU` / `→
   depositors`) so it reads correctly without color.
2. **`FWAActivityFeed`** — `RichLog`, width `3fr`. One line per draw:
   `HH:MM  0xABCD..1234  drew Nakamigos #4471  → sold back ($FWA) 0.118 ETH`. Color by outcome, but
   the outcome is also spelled out in words. **When `feed_available` is false, render an explicit
   `logs unavailable — activity paused` line and keep any previously-rendered lines with an
   `as of HH:MM` header.** Never blank, never a traceback.
3. **`FWAChaseBoard`** — ranked `DataTable`, width `2fr`. Richest positions: `#`, `Collection`,
   `Token`, `Backing ETH`, `Odds`, `Jackpot ×`. Renders the protocol's central absurdity: 221 ETH at
   `0.000%` odds for a `1,378×` jackpot ratio. Odds below 0.001% render `0.000%`, never `0`.
4. **`FWASettlementTable`** — width `2fr`, two stacked sections in one widget: the outcome mix
   (73.92 / 13.84 / 7.64 / 4.60 / 0.00 with counts) and crown history (33 sets, 12 payouts,
   91.096 ETH). Both are log-derived, so both need the `as of HH:MM` staleness header and an
   `unavailable` state.

**Tests (~7 of the shared file's ~14)**
- `test_signals_renders_five_rows` / `test_signals_none_payload_safe`
- `test_signals_pool_temp_direction_in_words`
- **`test_activity_feed_unavailable_renders_explicit_line`**
- `test_activity_feed_line_count`
- `test_chase_board_zero_odds_renders_three_decimals`
- **`test_settlement_table_unavailable_renders_explicit_state`**
- `test_settlement_shares_sum_displayed_as_100`

**Acceptance criteria**
- No model/client/analytics imports; primitives only
- Both log-derived widgets have a tested explicit unavailable state
- No information conveyed by color alone
- `pytest tests/widgets/test_fwa_widgets.py` green (both sections)

---

# WAVE 3

---

## WP-12 — Manager: orchestration, tiering, degradation

**Agent:** Backend Architect
*Why:* this is where three independently-failing pools, four refresh tiers and a frozen output
contract meet. It is the architectural keystone and it should be written by whoever wrote the
contract in WP-1.

**Dependencies:** WP-4, WP-5, WP-6, WP-7, WP-8, WP-9 · **Wave:** 3 · **Size:** L
**Blocks:** WP-15, WP-17

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_manager.py`
- `/Library/Vibes/autopull/tests/data/test_fwa_manager.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/data/talismans_manager.py` — `_safe_call`, the flat-dict
  assembly, `save_cache`, `close()`, the `_error_count` discipline, and its
  `enumeration_complete` gate (only trust aggregates from a complete scan) — FWA needs the same
  posture for its position sweep
- `/Library/Vibes/autopull/maxpane_dashboard/data/ttt_manager.py` — multi-origin parallel fetch

**Work**

1. `class FWAManager(poll_interval: int = 30)` constructing `FWAClient`, `FWALogClient`,
   `FWAMarketClient`, `FWACache`; loads the cache on init.
2. `async fetch_and_compute() -> dict[str, Any]` returning **exactly `FWA_DATA_KEYS`**:
   - ask the cache which tiers are due; fetch only those
   - run the three pools **concurrently** (`asyncio.gather(..., return_exceptions=True)`) — they are
     independent origins with independent failure modes
   - each pool's failure is caught, recorded in `degraded_sources`, and replaced by the cache's
     last-good payload with its timestamp/block
   - medium tier: single-flight sweep; skip (never queue) if one is running; publish atomically
   - compute analytics through `_safe_call` so an analytics bug degrades one number, not the cycle
   - `invariants_ok` reflects the runtime aggregate assertions; when false, `odds_stale=True` and the
     odds board / EV render stale rather than wrong
   - sample the hourly series, persist the cache, increment `_error_count`, return
3. `save_cache()` and `async close()` (persist + close all three HTTP clients).
4. **Degradation is the deliverable, not a fallback.** Implement all five rows of
   implementation-plan §12 here; WP-15 will test them end-to-end.
5. USD conversion: only where a USD source exists. If DexScreener is down, ETH-only figures render
   and USD cells go `—`. Never invent a rate.

**Tests (~10)** — mocked clients, no network:
- **`test_returns_exactly_fwa_data_keys`** (set equality against `FWA_DATA_KEYS`)
- `test_state_pool_failure_degrades_only_state_widgets`
- `test_log_pool_failure_degrades_only_log_widgets`
- `test_market_pool_failure_degrades_only_market_widgets`
- `test_all_pools_fail_still_returns_full_key_set`
- `test_degraded_sources_populated`
- `test_invariant_failure_sets_odds_stale`
- `test_single_flight_sweep_skipped_not_queued`
- `test_tier_respected_fast_does_not_trigger_sweep` (fake clock)
- `test_close_persists_cache_and_closes_clients`

**Acceptance criteria**
- `fetch_and_compute()` returns exactly `FWA_DATA_KEYS`, always, under every failure combination
- No exception ever escapes `fetch_and_compute()`
- Never labels `weighted_backing_total` as ETH or TVL; `eth_in_core` comes from `eth_getBalance`
- `pytest tests/data/test_fwa_manager.py` green

---

## WP-13 — Screen assembly + widget package exports

**Agent:** UI Designer
*Why:* the canonical layout, vertical budget and visual hierarchy across seven widgets — composition
and proportion work rather than data work.

**Dependencies:** WP-10, WP-11 · **Wave:** 3 · **Size:** M · **Blocks:** WP-15, WP-16, WP-17

**Files to create**
- `/Library/Vibes/autopull/maxpane_dashboard/screens/fwa.py`
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/__init__.py`
- `/Library/Vibes/autopull/tests/screens/test_fwa_screen.py`

**Files to read (patterns)**
- `/Library/Vibes/autopull/maxpane_dashboard/screens/talismans.py` — **lines 58-80 are the canonical
  layout; copy it.** Also copy the lifecycle (`on_screen_resume` / `on_screen_suspend` /
  `_do_initial_refresh` / `_schedule_refresh` / `_do_refresh`) and the per-widget try/except dispatch
  verbatim.
- `/Library/Vibes/autopull/maxpane_dashboard/screens/ttt.py`
- `/Library/Vibes/autopull/maxpane_dashboard/templates/screen_template.py`
- `/Library/Vibes/autopull/tests/screens/test_talismans_screen.py` — the fake-manager harness

**Work**

1. `widgets/fwa/__init__.py` re-exporting all seven classes (`FWAHeroMetrics`, `FWAOddsBoard`,
   `FWASparkline`, `FWASignals`, `FWAActivityFeed`, `FWAChaseBoard`, `FWASettlementTable`).
2. `class FWAScreen(Screen)` with the canonical layout:
   ```
   Static(id="title-bar")            "FWA · Gacha Terminal · Ethereum Mainnet"
   FWAHeroMetrics()                  3 cards
   Horizontal(id="middle-row"):
       FWAOddsBoard()                3fr
       Vertical(id="right-col"):
           FWASparkline()
           FWASignals()
   Static("─" * 300, id="separator")
   Horizontal(id="bottom-row"):
       FWAActivityFeed()             3fr
       FWAChaseBoard()               2fr
       FWASettlementTable()          2fr
   StatusBar()
   ```
   **`BINDINGS = [Binding("r", "refresh", "Refresh", show=False)]` only.** No `c` toggle — Talismans
   has one solely because it hides one of two bottom tables; FWA shows both.
3. Title bar updates each cycle from the data: `FWA · {active_positions} positions · {eth_in_core}
   ETH in core · fee {acquisition_fee_eth} ETH`.
4. `_do_refresh()` dispatches every `FWA_DATA_KEYS` group to its widget inside an individual
   try/except with a `logger.debug`, exactly like `talismans.py:168-256`. On a manager exception,
   update only the `StatusBar` with `last_updated_seconds_ago=999` and return.
5. `StatusBar`: reuse `maxpane_dashboard/widgets/status_bar.py` unchanged; call `set_game_name("fwa")`
   and `set_theme_name(self.app.theme)` in `on_screen_resume`. Surface `degraded_sources` in the
   status bar if the existing API allows it; if not, leave it to the widgets and note the gap.

**Tests (~4)** — fake manager, no network, per the Talismans convention:
- `test_screen_mounts_and_refreshes`
- `test_screen_dispatches_every_data_key` — assert every `FWA_DATA_KEYS` group reaches a widget
- `test_screen_survives_manager_exception`
- `test_screen_survives_all_none_payload`

**Acceptance criteria**
- Layout matches `screens/talismans.py:58-80` structurally (title / hero / middle-row+right-col /
  separator / bottom-row / status bar)
- Every widget update is individually guarded — one widget failing never kills the refresh
- `from maxpane_dashboard.widgets.fwa import *` resolves all seven classes
- `pytest tests/screens/test_fwa_screen.py` green

---

## WP-14 — Refresh-budget and batching benchmark

**Agent:** Performance Benchmarker
*Why:* the 500-call cap, the ~18-call sweep and the 15 s/60 s tier interaction are a measurable
budget with a real failure mode (429 cascades and starved hot tiles). Measuring it is a distinct
discipline from building it.

**Dependencies:** WP-6, WP-9 · **Wave:** 3 · **Size:** M · **Blocks:** none (informs WP-20)

**Files to create**
- `/Library/Vibes/autopull/tests/data/test_fwa_refresh_budget.py`

**Files to read**
- `/Library/Vibes/autopull/maxpane_dashboard/data/fwa_client.py` (WP-6),
  `fwa_cache.py` (WP-9)
- `docs/fwa_technical_findings.md` §6.1 (17 `eth_call`s / 3.3 s measured), §11 (all rate limits)
- `docs/fwa_implementation_plan.md` §8.4

**Work** — a counting transport double (records every request, returns fixtures, never touches the
network) plus a fake clock:

1. Assert **one fast tick = 1-2 `eth_call`s** (the hot Multicall3 + the balance call), never a sweep.
2. Assert **one full sweep ≤ 20 `eth_call`s** against the 3,867-position fixture (documented: 17).
3. Assert **no Multicall3 chunk exceeds 500 calls**, and that a chunk of exactly 500 is accepted.
4. Assert **no raw JSON-RPC batch exceeds 60 elements** and that consecutive calls respect the
   ~0.12 s spacing (fake clock — tests must not actually sleep).
5. Assert the **tier interaction**: drive 8 fast ticks and 2 medium ticks through a fake clock with a
   sweep artificially slowed past 60 s; assert the overlapping sweep is **skipped, not queued**, and
   that every fast tick still completed.
6. Assert the CoinGecko sweep never runs from a fast or medium tick.
7. Record the measured call counts as explicit constants in the test file so a future regression
   shows up as a number changing, not as a vague slowdown.

**Acceptance criteria**
- Every budget above is asserted with a hard number, not a range
- Zero real sleeps, zero network
- `pytest tests/data/test_fwa_refresh_budget.py` green

---

# WAVE 4

---

## WP-15 — Degradation and failure-mode suite

**Agent:** API Tester (second instance)
*Why:* systematically breaking each endpoint pool and asserting the resulting UI state is the same
skill as verifying the endpoint contracts in the first place. PRD §9 makes this mandatory, not
optional.

**Dependencies:** WP-12, WP-13 · **Wave:** 4 · **Size:** M · **Blocks:** WP-20

**Files to create**
- `/Library/Vibes/autopull/tests/data/test_fwa_degradation.py`

**Files to read**
- `docs/fwa_PRD.md` §9 (the four mandatory scenarios), §12.7
- `docs/fwa_implementation_plan.md` §12 (the full matrix; the emissions row is flagged PRIMARY)
- `/Library/Vibes/autopull/tests/screens/test_talismans_screen.py` — harness style

**Work** — each scenario driven end-to-end (manager + real widgets + `FWAScreen` under
`App.run_test()`), asserting the **rendered** state, not just the dict.

**Scenario 1 is the emissions case, deliberately.** Per the user's ruling the post-emissions state is
the PRIMARY case, not an edge case, so it is written and passing before the others.

1. **Emissions window elapsed — PRIMARY** — frozen clock past `1785870083`. Assert: emissions row
   reads `emissions ended`; **no negative number anywhere in the rendered output**; every other widget
   renders normally; the dashboard is still fully meaningful (PRD §12.6). Then, as the *secondary*
   case, a frozen clock before the stop showing a live countdown.
2. **Logs endpoint down** — tenderly and drpc both fail. Assert: activity feed shows
   `logs unavailable`; settlement table shows last-good with `as of HH:MM` or `unavailable`;
   **hero cards, odds board, chase board and sparkline all still render real numbers**;
   `degraded_sources == ["logs"]`; no exception.
3. **Floors partially missing** — 22 ok / 11 × 404 / 5 × 429. Assert: EV band renders; coverage badge
   present and reads `22/38`; lower bound ≤ best; Art Blocks rows show the suppression note; no row
   shows a fabricated floor.
4. **RPC fallback exhausted** — publicnode + cloudflare + 1rpc all fail. Assert: hero cards show `—`
   + `chain unavailable`; odds board shows last-good with `as of block N` and stale marking;
   log-derived widgets still work; error count incremented; the next cycle still runs.
5. **Market feeds down** — DexScreener + GeckoTerminal fail. Assert: sparkline
   `waiting for data...`; crown pot renders ETH with USD `—`; no invented exchange rate.
6. **Combined worst case** — all three pools down simultaneously and an empty cache. Assert: the
   screen still mounts and refreshes, every widget shows an explicit unavailable state, and
   `fetch_and_compute()` still returns the full `FWA_DATA_KEYS` set.
7. **Invariant mismatch** — feed a sweep fixture whose aggregates do not reconcile. Assert the odds
   board and EV are marked stale and **no number derived from the bad sweep is displayed**.

**Acceptance criteria**
- All seven scenarios pass; each asserts a rendered string, not only a dict value
- Zero crashes and zero silently-wrong numbers in any scenario
- `pytest tests/data/test_fwa_degradation.py` green

---

## WP-16 — Full `fwa` Theme + CSS + theme tests

**Agent:** UI Designer (sole owner of `minimal.tcss` and `themes/__init__.py`)
*Why:* PRD §11 asks for a gachapon/casino register held inside the existing minimal aesthetic — a
restraint problem, and now a palette-design problem too. Also the sole owner of two shared files, so
it is deliberately isolated.

> **Scope ruling (2026-07-26):** the user chose a **full registered theme**, not a CSS block alone —
> going against the plan's original recommendation. Plan it properly: palette, registration, CLI
> exposure and tests.

**Dependencies:** WP-13 · **Wave:** 4 · **Size:** M · **Blocks:** WP-17

**Files to create**
- `/Library/Vibes/autopull/tests/test_fwa_theme.py` (**WP-17 appends the CLI tests to this file in
  wave 5 — leave a `# ── WP-17 CLI selection tests below ──` banner at the end**)

**Files to modify** (**exclusive ownership — no other WP may touch these**)
- `/Library/Vibes/autopull/maxpane_dashboard/themes/minimal.tcss` — append at EOF (file is currently
  1770 lines; the Talismans block sits at 1717-1769)
- `/Library/Vibes/autopull/maxpane_dashboard/themes/__init__.py` — register the `fwa` `Theme`

**Files you must NOT modify**
- `/Library/Vibes/autopull/maxpane_dashboard/__main__.py` — the `--theme` choices list at line **51**
  needs `"fwa"`, but that file is **exclusively WP-17's**. **Deliverable: hand WP-17 the exact
  one-line diff** (old line → new line, verbatim) in your completion notes. Do not open the file for
  writing. This keeps the contention discipline intact with no exception.

**Files to read (patterns)**
- `minimal.tcss` lines **1635-1769** — the TTT and Talismans blocks, which are the exact template:
  widget-class selectors, `height: 7` heroes, `3fr`/`2fr` widths, `RichLog` scrollbar sizing
- `themes/__init__.py:132-146` — exactly how the `talismans` Theme is registered and how
  `THEME_NAMES` is derived (`list(THEMES.keys())`, so registration order sets the `t`-cycle order)
- `docs/fwa_PRD.md` §11 · `docs/fwa_implementation_plan.md` §8.6

**Work**

**Part A — CSS block.** Append a `/* ── FWA screen ─────────── */` block styling: `FWAHeroMetrics`
(`height: 7`), `FWAHeroBox` (`width: 1fr; height: 7; border: solid $panel; padding: 1 2;
content-align: center middle; background: $surface; margin: 0 1`), `FWAOddsBoard` (`width: 3fr`),
`FWASparkline` (`height: auto`), `FWASignals` (`height: 1fr; overflow-y: auto`), `FWAActivityFeed`
(`width: 3fr`) + its `RichLog` (`scrollbar-size: 1 1`), `FWAChaseBoard` and `FWASettlementTable`
(`width: 2fr`). Match the neighbouring blocks' padding and margins exactly — the vertical budget is
already proven by TTT and Talismans.

**Part B — Theme registration.** Add `THEMES["fwa"] = Theme(name="fwa", …)` mirroring the
`talismans` entry at line 132. The gacha/casino palette, per PRD §11 and implementation-plan §8.6:

| Semantic | Colour | Binding rule |
|---|---|---|
| EV sign | green / red | **Never the sole carrier of meaning.** WP-10 already pairs it with `▲`/`▼`; your palette must not tempt anyone to drop the glyph. |
| Pool temperature | cold → hot gradient | Paired with a direction in words (`→ YOU` / `→ depositors`) by WP-11. |
| Crown | **gold — reserved exclusively** | Appears nowhere else on the screen. |
| Everything else | `$panel`, `$surface`, `$text-muted`, `$primary`, `$background` | So the FWA screen stays legible under the other eight registered themes, and so other screens stay legible under `fwa`. |

Restraint over novelty: the numbers are the content. No new colour constants beyond the three
semantic ramps.

**Part C — Verify.** Render `FWAScreen` at a realistic terminal size under the `fwa` theme *and*
under `matrix`/`minimal`/`bloomberg` and confirm no widget clips or scrolls unexpectedly. Check the
two known contrast risk spots yourself before handing to WP-19: **gold-on-dark on the crown tile**
and the **red/green EV sign**. If either is marginal, adjust the palette — never the glyph.

**Tests (~5)** in `tests/test_fwa_theme.py`:
- `test_fwa_theme_registered` — `"fwa" in THEMES` and `THEMES["fwa"].name == "fwa"`
- `test_fwa_in_theme_names` — `"fwa" in THEME_NAMES`, so the `t` key cycles to it
- `test_theme_cycle_includes_fwa_and_wraps` — cycling from `fwa` returns to a valid theme
- `test_fwa_theme_defines_required_colors` — the palette exposes the variables the FWA CSS block
  references; no `None`/empty colour values
- `test_crown_gold_distinct_from_ev_colors` — the gold value is not equal to either EV sign colour
  (so the crown cannot be confused with an EV state)

**Acceptance criteria**
- CSS appended at EOF only; nothing above line 1770 in `minimal.tcss` modified
- `fwa` Theme registered and present in `THEME_NAMES`; `t` cycles to it
- `FWAScreen` renders without clipping under `fwa` and under at least three other themes
- Gold appears nowhere except the crown card
- Theme variables used throughout; no hardcoded hex except the three semantic ramps
- **`__main__.py` untouched**, with the exact `--theme` one-line diff handed to WP-17
- `pytest tests/test_fwa_theme.py` green; WP-13's screen tests still green

---

# WAVE 5

---

## WP-17 — Registration (sole owner of all remaining shared files)

**Agent:** Senior Developer
*Why:* seven surgical insertions into the app's most-shared file, where an off-by-one breaks every
dashboard. Deliberately isolated as the only WP touching `app.py`, `game_select.py`, `__main__.py`.

**Dependencies:** WP-12, WP-13, WP-16 · **Wave:** 5 · **Size:** S · **Blocks:** WP-18, WP-19,
WP-20, WP-21

**Files to modify** (**exclusive ownership**)
- `/Library/Vibes/autopull/maxpane_dashboard/app.py`
- `/Library/Vibes/autopull/maxpane_dashboard/screens/game_select.py`
- `/Library/Vibes/autopull/maxpane_dashboard/__main__.py` — **both** the `--game` choices (56) and the
  `--theme` choices (51). WP-16 hands you the verbatim one-line `--theme` diff; you are the only WP
  permitted to apply it.
- `/Library/Vibes/autopull/tests/test_fwa_theme.py` — append your CLI tests **below WP-16's
  `# ── WP-17 CLI selection tests below ──` banner**. WP-16 is complete (wave 4), so there is no
  concurrency.

**Files to read**
- `docs/fwa_implementation_plan.md` §7 — the verified line-number table. **Re-verify each line
  yourself before editing; earlier WPs may have shifted nothing, but confirm.**
- `docs/fwa_implementation_plan.md` §8.6 — the theme ownership split
- `docs/fwa_PRD.md` §10 (note: §10 omits the `--theme` line; it is now in scope regardless)

**Work** — mirror the `talismans` wiring exactly, at each site:

| # | File | Site | Edit |
|---|---|---|---|
| 1 | `app.py` | manager imports (11-18) | `from maxpane_dashboard.data.fwa_manager import FWAManager` after line 14 |
| 2 | `app.py` | screen imports (19-33) | `from maxpane_dashboard.screens.fwa import FWAScreen` |
| 3 | `app.py` | `__init__` (67-90) | `self._fwa_manager = FWAManager(poll_interval=poll_interval)` after line 90 |
| 4 | `app.py` | `on_mount` prefetch chain (101-166) | `elif self._initial_game == "fwa": self.run_worker(self._fwa_manager.fetch_and_compute(), exclusive=True, name="prefetch")` |
| 5 | `app.py` | `_GAME_CYCLE` (184) | append `"fwa"` → `[..., "ttt", "talismans", "fwa"]` |
| 6 | `app.py` | `_launch_game` chain (192-272) | `elif game_id == "fwa":` installing `FWAScreen(self._fwa_manager, self.poll_interval, name="fwa")` guarded by `is_screen_installed`, inserted **before** the `else: return` at 271 |
| 7 | `app.py` | `action_quit` (354-400) | `try: await self._fwa_manager.close() except Exception as exc: logger.warning(...)` before `self.exit()` |
| 8 | `game_select.py` | `GAMES` (11-24) | `("9", "fwa", "Fake World Assets", "NFT gacha pool w/ inverse-weighted VRF draws on Ethereum")` |
| 9 | `__main__.py` | `--game` choices (56) | append `"fwa"` |
| 10 | `__main__.py` | `--theme` choices (51) | append `"fwa"` — **mandatory**, applying WP-16's verbatim diff |

**Tests (~2)** appended to `tests/test_fwa_theme.py` below WP-16's banner:
- `test_theme_cli_choice_includes_fwa` — build the argparse parser and assert `"fwa"` is an accepted
  `--theme` value (and that `--theme fwa` parses)
- `test_game_cli_choice_includes_fwa` — same for `--game fwa`

**Acceptance criteria**
- `python -m maxpane_dashboard --game fwa` boots with no import error
- `python -m maxpane_dashboard --game fwa --theme fwa` boots and applies the FWA theme
- Game-select shows `[9] Fake World Assets`; pressing `9` opens the screen
- `Tab` cycles all 9 games and returns to the start; `t` cycles through all themes including `fwa`
- `q` closes the FWA manager (cache persisted, HTTP clients closed) with no warning in
  `~/.maxpane/maxpane.log`
- Every other dashboard still launches — no regression in the eight existing screens
- `pytest tests/test_fwa_theme.py` green (both WP-16's and your sections)

---

# WAVE 6

---

## WP-18 — Correctness-rule and scope guardrails

**Agent:** Reality Checker
*Why:* the job is to go find where the shipped code quietly drifted from the ten binding rules and
the six suppression rules, and to convert each into an executable guard. Adversarial verification, not
construction.

**Dependencies:** WP-17 · **Wave:** 6 · **Size:** M · **Blocks:** WP-20

**Files to create**
- `/Library/Vibes/autopull/tests/test_fwa_guardrails.py`

**Files to read**
- `docs/fwa_PRD.md` **§7** (ten rules) and **§13** (six suppressions)
- `docs/fwa_implementation_plan.md` §10 and §11 (the traceability tables — every row needs a guard)
- Every shipped FWA module

**Work** — static scans over `maxpane_dashboard/data/fwa_*.py`, `analytics/fwa_*.py`,
`widgets/fwa/*.py`, `screens/fwa.py`, `abis/fwa/*`:

1. **Read-only:** no import of `eth_account`, `keystore`, `signer`, `transactor`, `LocalAccount`; no
   `eth_sendRawTransaction` / `eth_sendTransaction` / `personal_*` / `eth_sign`; no `private_key`.
2. **Keyless:** no `api_key`, `apikey`, `Authorization` header, `X-API-KEY`; no banned host
   (`eth.llamarpc.com`, `rpc.ankr.com`, `api.reservoir.tools`, `api-mainnet.magiceden.dev`,
   `sourcify.dev`, `etherscan.io`, `api.etherscan.io`).
3. **No Etherscan scraping in shipped code:** nothing under `maxpane_dashboard/` references
   `etherscan`, `js-copytextarea2`, `data-csource`, or imports `scripts/`.
4. **Rule 3:** 8500 is never labelled a discount in user-facing text.
5. **Rule 4:** `weighted_backing_total` never appears adjacent to `ETH`/`TVL` in any render string.
6. **Rule 6:** no hardcoded protocol parameter — specifically no crown-tithe `500`, no
   `surchargeBps = 1000` constant used as truth rather than a fallback label, no parameter dict
   copied from the docs.
7. **Rule 7:** no hardcoded collection allowlist (the registry comes from
   `CollectionWhitelistSet`); a bare 16-entry collection list is a failure.
8. **§13 suppressions:** no claim-progress string (`claimed`, `of 200,000,000`, `claim progress`);
   no `500,000,000` / `500M` supply-placement claim; no predicted/computed VRF fee; no rendered EV
   value without an adjacent coverage badge (assert via WP-10's widget, not by grep alone).
9. **Publish the verdict as tests**, one per rule, each with a message naming the PRD rule it
   enforces so a future failure is self-explaining.
10. Report — in the test docstrings, not a separate document — any rule that cannot be mechanically
    guarded and therefore relies on review.

**Acceptance criteria**
- One test per PRD §7 rule and per PRD §13 suppression, all green
- Each failure message cites its PRD rule number
- Zero findings, or every finding fixed in the owning module before this WP closes

---

## WP-19 — Accessibility and multi-theme audit

**Agent:** Accessibility Auditor
*Why:* the design leans on three colour semantics (green/red EV sign, cold→hot ramp, gold crown)
inside a TUI that now ships **ten** themes including a purpose-built `fwa` palette. Colour-only
encoding and low-contrast pairings are the exact failure mode here, and WP-16's new palette raises
the stakes rather than lowering them.

**Dependencies:** WP-17 · **Wave:** 6 · **Size:** S · **Blocks:** WP-20
**Exclusive lock:** `maxpane_dashboard/widgets/fwa/*`, `maxpane_dashboard/screens/fwa.py` for this
wave (WP-10, WP-11, WP-13 are complete).

**Files to modify**
- `/Library/Vibes/autopull/maxpane_dashboard/widgets/fwa/*.py` (fixes only)
- `/Library/Vibes/autopull/maxpane_dashboard/screens/fwa.py` (fixes only)
- `/Library/Vibes/autopull/tests/widgets/test_fwa_widgets.py` (append assertions)

**Files to read**
- `maxpane_dashboard/themes/__init__.py` — all registered themes
- `minimal.tcss` FWA block (WP-16)
- `docs/fwa_PRD.md` §11

**Work**

1. Audit every FWA render string for **colour-only encoding**. Each of these must carry a
   text/glyph signal too: EV sign (`▲`/`▼`), pool temperature direction (`→ YOU` / `→ depositors`),
   buy gate (`GATED`/`OPEN`), settlement outcome (spelled out), crown vacancy (`vacant`).
2. **The two named contrast risk spots** — check these explicitly and first:
   - **gold-on-dark on the crown tile** (gold is reserved for the crown, so it has no fallback)
   - **the red/green EV sign** — verify it is legible *and* that removing colour entirely still
     conveys the sign. Green/red must **never** be the sole carrier.
   If either fails under any theme, the fix is to **adjust WP-16's palette, never to drop the glyph**.
   Route palette changes back to WP-16's files (`themes/__init__.py`, `minimal.tcss`) — those are
   WP-16's, so coordinate rather than editing blind.
3. Check contrast and legibility of the FWA screen under **all ten registered themes** (matrix,
   minimal, bloomberg, htop, retro, bakery, frenpet, base, talismans, **fwa**) — cycle with `t`.
   Anything illegible in any theme is a defect: fix by using theme variables instead of hardcoded
   colours.
4. Check the reverse direction too: the **other eight dashboards must stay legible under the new
   `fwa` theme**, since `t` now cycles it onto every screen.
5. Verify the dim/`--`/`—` degraded states are still readable (degraded must not mean invisible).
6. Verify no widget depends on colour to distinguish two adjacent numeric columns.
7. Append the resulting assertions to `tests/widgets/test_fwa_widgets.py` (e.g. "the EV render string
   contains a glyph whenever it contains a colour tag").

**Acceptance criteria**
- No information conveyed by colour alone anywhere in the FWA screen
- Gold-on-dark crown tile and the red/green EV sign both pass contrast under **all ten** themes
- FWA screen legible under all ten themes; the other eight dashboards legible under `fwa`
- Gold still reserved exclusively for the crown
- Appended tests green; WP-13's screen tests and WP-16's theme tests still green

---

# WAVE 7

---

## WP-20 — Full-suite integration and regression triage

**Agent:** Test Results Analyzer
*Why:* the closing job is reading ~930 test outcomes across 21 work packages, separating genuine FWA
defects from cross-WP interface drift from pre-existing failures, and routing each.

**Dependencies:** all · **Wave:** 7 · **Size:** M

**Files to modify** — any FWA test file needing a fix; **no production file without naming the
owning WP in the commit message**

**Work**

1. `pytest` full suite. Establish the baseline first: the existing suite is ~796 tests; record any
   failure that pre-dates FWA and **do not fix it here** — report it.
2. Triage every FWA failure into: (a) genuine defect, (b) interface drift between two WPs, (c) test
   bug, (d) pre-existing. Fix (b) and (c); route (a) to the owning WP; report (d).
3. Verify the contract mechanically: `set(manager.fetch_and_compute().keys()) == set(FWA_DATA_KEYS)`
   and every `FWA_WIDGET_SIGNATURES` kwarg is actually dispatched by `FWAScreen`.
4. Confirm **zero network access in the whole test suite** — run with a transport that raises, or
   offline.
5. Confirm no regression in the eight existing dashboards (bakery, frenpet, base, cattown, dota, ocm,
   ttt, talismans): both their tests and a boot smoke test each.
6. Smoke test `python -m maxpane_dashboard --game fwa` **and** `--game fwa --theme fwa`, let each run
   several poll cycles, and check `~/.maxpane/maxpane.log` for warnings.
7. Confirm no acceptance criterion or test anywhere assumes a **live emissions countdown** — the
   post-emissions state is the primary case, so a suite that only passes before 2026-08-04 is a defect.
8. Report the final count and coverage per module.

**Acceptance criteria**
- `pytest` fully green; ~132 new FWA tests
- Zero regressions in the eight existing dashboards, including under the new `fwa` theme
- Zero network access anywhere in the suite
- No test depends on the current date being before the emissions stop
- Live boot runs ≥ 3 poll cycles with no warning in the log

---

## WP-21 — Docs: dashboard inventory and docstring pass

**Agent:** Technical Writer
*Why:* the repo's own inventory is drifting (`README.md` already omits Talismans) and CLAUDE.md
claims 8 dashboards. Precision-writing work, disjoint from every code file.

**Dependencies:** WP-17 · **Wave:** 7 · **Size:** S

**Files to modify**
- `/Library/Vibes/autopull/README.md` — dashboard table (~lines 13-17) and the `maxpane --game …`
  usage list (~lines 70-72)
- `/Library/Vibes/autopull/CLAUDE.md` — dashboard inventory

**Files to read**
- `README.md`, `CLAUDE.md`, `docs/fwa_PRD.md` §1, all shipped FWA module docstrings

**Work**

1. Add FWA to the README dashboard table: `| **FWA** | Ethereum | NFT gacha pool, inverse-weighted
   VRF draws, pull EV |` and `maxpane --game fwa` to the usage list.
2. **Backfill the missing Talismans rows** — confirmed in scope by the user. Talismans is currently
   absent from both the table and the usage list; add it so the README covers all **nine**
   dashboards. Two lines, and it is a genuine inventory defect.
3. Update CLAUDE.md's dashboard count and inventory to 9, and add a one-line FWA entry pointing at
   `docs/fwa_PRD.md`, `docs/fwa_game_mechanics.md`, `docs/fwa_technical_findings.md`.
4. Note the new `fwa` theme wherever themes are listed (`--theme fwa` is now a valid choice, bringing
   the registered themes to ten).
5. Docstring pass over the shipped FWA modules: every module states its purpose, its data source, and
   the traps it guards (inverse weight, two floor divisions, 8500-is-payout, `weightedBackingTotal`
   is not TVL, slots are non-contiguous, callData has no `0x`, backing is mutable). Match the density
   of `talismans_client.py`'s header, which is the house standard.
6. **Do not** touch the three research docs, the PRD, or these two planning documents.

**Acceptance criteria**
- README lists 9 dashboards (FWA added, Talismans backfilled) in both the table and the usage list
- CLAUDE.md inventory says 9 and links the three FWA docs
- The `fwa` theme is documented; theme count reads ten
- Every shipped FWA module has a purpose + source + traps docstring
- No code behaviour changed

---

## Summary

| Wave | WP | Title | Agent | Size | New files | Mod files | ~Tests |
|---|---|---|---|---|---|---|---|
| 1 | WP-1 | Interface freeze | Backend Architect | M | 2 | 0 | 8 |
| 1 | WP-2 | ABIs + enums + topics | Evidence Collector | M | 12 | 0 | 0 |
| 1 | WP-3 | Offline fixture corpus | Evidence Collector | M | ~22 | 0 | 0 |
| 1 | WP-4 | EV & pricing math (TDD) | AI Engineer | L | 2 | 0 | 26 |
| 2 | WP-5 | Signals & badges | Senior Developer | M | 2 | 0 | 16 |
| 2 | WP-6 | State client (Pool A) | Data Engineer | L | 2 | 0 | 18 |
| 2 | WP-7 | Log client (Pool B) | Data Engineer | L | 2 | 0 | 14 |
| 2 | WP-8 | Off-chain client (Pool C) | API Tester | M | 2 | 0 | 12 |
| 2 | WP-9 | Tiered cache | Data Engineer | M | 2 | 0 | 8 |
| 2 | WP-10 | Widgets A (3) | Frontend Developer | M | 4 | 0 | 7 |
| 2 | WP-11 | Widgets B (4) | Frontend Developer | M | 4 | 1 | 7 |
| 3 | WP-12 | Manager | Backend Architect | L | 2 | 0 | 10 |
| 3 | WP-13 | Screen + exports | UI Designer | M | 3 | 0 | 4 |
| 3 | WP-14 | Refresh-budget benchmark | Performance Benchmarker | M | 1 | 0 | 6 |
| 4 | WP-15 | Degradation suite | API Tester | M | 1 | 0 | 10 |
| 4 | WP-16 | **Full `fwa` Theme + CSS + tests** | UI Designer | **M** | **1** | **2** | **5** |
| 5 | WP-17 | Registration (incl. `--theme`) | Senior Developer | S | 0 | **4** | **2** |
| 6 | WP-18 | Correctness guardrails | Reality Checker | M | 1 | 0 | 10 |
| 6 | WP-19 | Accessibility audit | Accessibility Auditor | S | 0 | ~10 | +3 |
| 7 | WP-20 | Full-suite integration | Test Results Analyzer | M | 0 | as needed | +2 |
| 7 | WP-21 | Docs inventory | Technical Writer | S | 0 | 2 | 0 |
| | **Total** | | | | **~65** | **~20** | **~132** |

Changed by the 2026-07-26 rulings: **WP-16 S → M** (+1 new file `tests/test_fwa_theme.py`, +2
modified files, +5 tests) and **WP-17 +1 modified file, +2 tests** (`--theme` line and its CLI tests).
**WP count, wave count, concurrency and critical path are unchanged.**

### Parallelism

| Wave | Concurrent agents | Runs together |
|---|---|---|
| 1 | **4** | WP-1, WP-2, WP-3, WP-4 |
| 2 | **7** | WP-5, WP-6, WP-7, WP-8, WP-9, WP-10, WP-11 |
| 3 | **3** | WP-12, WP-13, WP-14 |
| 4 | **2** | WP-15, WP-16 |
| 5 | **1** | WP-17 (shared files, deliberately serial) |
| 6 | **2** | WP-18, WP-19 |
| 7 | **2** | WP-20, WP-21 |

Critical path: **WP-1 → WP-6 → WP-12 → WP-13 → WP-16 → WP-17 → WP-18 → WP-20**

### File-contention map — no two concurrent WPs write the same file

| File | Sole writer | Wave |
|---|---|---|
| `maxpane_dashboard/app.py` | WP-17 | 5 |
| `maxpane_dashboard/screens/game_select.py` | WP-17 | 5 |
| `maxpane_dashboard/__main__.py` | WP-17 — **both** `--game` (56) and `--theme` (51); WP-16 supplies the `--theme` diff but never opens the file | 5 |
| `maxpane_dashboard/themes/minimal.tcss` | WP-16 | 4 |
| `maxpane_dashboard/themes/__init__.py` | WP-16 (registers the `fwa` Theme) | 4 |
| `tests/test_fwa_theme.py` | WP-16 creates (wave 4) → WP-17 appends below the banner (wave 5) | 4, 5 |
| `maxpane_dashboard/widgets/fwa/__init__.py` | WP-13 | 3 |
| `maxpane_dashboard/widgets/fwa/*` , `screens/fwa.py` | WP-10/11/13 (waves 2-3) → WP-19 exclusive lock (wave 6) | 2-3, 6 |
| `tests/widgets/test_fwa_widgets.py` | WP-10 creates (wave 2) → WP-11 appends below the banner (same wave, disjoint section) → WP-19 appends (wave 6) | 2, 6 |
| `README.md`, `CLAUDE.md` | WP-21 | 7 |
| everything else | exactly one creating WP | — |

`tests/test_fwa_theme.py` is shared but **across** waves (WP-16 in wave 4, WP-17 in wave 5), so there
is no concurrency on it.

The only same-wave shared file is `tests/widgets/test_fwa_widgets.py` (WP-10 and WP-11). Mitigation:
WP-10 creates it first with a clear `# ── WP-11 widgets below ──` banner, and WP-11 appends only
below that banner. If the orchestrator prefers zero risk, split it into
`test_fwa_widgets_a.py` / `test_fwa_widgets_b.py` and let WP-20 reconcile the names.
