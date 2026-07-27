# FWA Dashboard — PRD

**Project:** Fake World Assets (fwa.fun) — "The Gacha Terminal"
**Target:** MaxPane dashboard #9
**Chain:** Ethereum mainnet (chain id 1)
**Date:** 2026-07-26 (live values verified 2026-07-25)
**Status:** Approved spine + scope; ready for implementation planning

Source research: [`docs/fwa_game_mechanics.md`](fwa_game_mechanics.md) · [`docs/fwa_technical_findings.md`](fwa_technical_findings.md)

---

## 1. Product summary

FWA is a gachapon machine for blue-chip NFTs. Depositors list an NFT with committed ETH
backing; that backing sets an **inverse** draw weight and funds an irrevocable standing bid.
A purchaser pays one price for one Chainlink-VRF-selected random position, then chooses:
keep the NFT, or accept the standing bid for 85% of its backing.

The dashboard takes the **purchaser's seat**. Its job is to answer one question continuously:

> **Is a pull worth it right now?**

Everything on screen either feeds that number or explains it.

### Why this project earns a dashboard

The protocol's entire economics collapse into a single observable gap:

| Measure | Measured at block 25612701 | Meaning |
|---|---|---|
| Harmonic mean backing | 0.123874 ETH | what a pull costs you |
| Arithmetic mean backing | 0.481327 ETH | what the pool actually holds |
| **Gap** | **3.885×** | the protocol, in one number |

> **The gap is a live ratio, not a constant.** The figures above are measured from the full
> pinned distribution (findings §13.8) and are a point-in-time observation, not constants — a
> crude live re-check two days later, after the pool grew 53%, put the gap at ≤3.49×. The
> 0.1247 / 0.5002 / 4.0× triple quoted in early research came from a sweep that failed its own
> aggregate check and is superseded (findings §13.7). Never hardcode the multiple, never assert
> it in a test, never print it in prose — compute and render it at the current block.

Inverse weighting means cheap positions dominate the odds and rich positions are
effectively unreachable — CryptoPunks hold 137.10 ETH of backing across 3 positions for
**0.000%** of the draw weight. That tension is inherently visual and nothing currently
renders it.

### Live scale (verified 2026-07-25)

| Metric | Value |
|---|---|
| Acquisitions requested | 58,006 |
| Settlements | 51,522 |
| Active positions | 3,867 |
| ETH in core | ~2,551 |
| Cumulative protocol revenue | 720.688 ETH |
| Allowed collections / with live positions | 51 / 38 |

### Settlement outcome mix — the protocol's most revealing statistic

| Outcome | Share |
|---|---|
| Accept bid, paid in $FWA | 73.92% |
| Accept bid, paid in ETH | 13.84% |
| Relist (purchaser becomes depositor) | 7.64% |
| **Keep the NFT** | **4.60%** |
| Force-finalized | 0.00% |

~88% sell straight back. Almost nobody wants the art — they want the $FWA. This single
table reframes the whole protocol and belongs on screen.

---

## 2. Scope

**In scope:** one overview screen, `FWAScreen`, consistent with TTT / Talismans / Base.

**Out of scope:** wallet-scoped or depositor views. The Gacha Terminal spine is a
purchaser's seat, and purchasers hold no persistent onchain state worth a second screen.
No `wallet_input.py` wiring.

**Non-goals:** the dashboard is strictly read-only. It never signs, never sends, never
prompts for a key. It does not attempt to place deposits or acquisitions.

---

## 3. The flagship metric: Pull EV

```
EV = Σ pᵢ · max(0.85 · backingᵢ , floorᵢ)  −  acquisitionFee  +  rebateShare · surcharge

where  pᵢ = (1e36 / backingᵢ) / totalWeight
```

Three components, each independently interesting:

1. **Base sell-back** — because weights are inverse to backing, expected sell-back is
   `0.85 × harmonicMean ≈ 0.106 ETH` against a price of `≈ 0.137 ETH`. Pure flipping is
   **−22% EV**. Stating this plainly is a service to the user.
2. **Option value** — the purchaser chooses *after* seeing the draw, so every position
   whose floor exceeds `0.85 × backing` contributes real optionality. The observed 4.60%
   keep-rate is the market's own estimate of how often that option pays.
3. **$FWA rebate** — the surcharge share routed back to the purchaser (see §4).

### Rendered as a band, not a point

Keyless floor prices (CoinGecko) cover **26 of 38** collections with live positions — but those
26 are only ~20% of pool *weight*, because TTT (49.08%) and Art Blocks (18.99%) are both
unpriceable. **~79.6% of the draw weight has no floor**, which is why the band is not optional.
(Measured 2026-07-27; findings §13.14 supersedes the earlier 22/38 and 68% figures.) The
widget therefore shows:

- **Lower bound** — an unpriced position contributes **zero**, not even its guaranteed
  sell-back leg. Count only value you can verify. Strictly pessimistic; cannot mislead.
- **Best estimate** — the unknown *floor* is dropped from the `max()`, but the position keeps
  its guaranteed `0.85 × backing` sell-back leg.
- **Coverage badge** — `N/M collections · P% of weight priced`.

> **Clarification (2026-07-27), after WP-4 hit the ambiguity.** An earlier wording said the
> lower bound "counts unknown floors as 0". Taken literally that is
> `max(0.85·backing, 0) = 0.85·backing` — identical to the best-estimate case, collapsing the
> band to a point in every scenario and defeating the entire mechanism. The reading above is
> the operative one. At zero coverage it degrades correctly: `best = sell-back only`,
> `lower = −fee`.

A number that tells someone to spend ETH must be honest about its own uncertainty. Never
render a single confident EV figure while a third of the pool is unpriced.

---

## 4. The timing dial nobody is trading

The 10% surcharge is split dynamically by **time since the last acquisition request**:

| Seconds since last request | Surcharge destination |
|---|---|
| ≤ 60 s | 100% to depositors |
| 60 s – 3600 s | linear ramp |
| ≥ 3600 s | 100% to the purchaser's $FWA allowance |

`forcedTokenShareBps = -1` (dynamic). On a cold pool the surcharge comes back to *you*, so
the effective price is materially lower. This is publicly observable, directly exploitable,
and — as far as the research found — surfaced nowhere. It gets a first-class widget.

> Implementation note: `tokenShareBps(uint256)` linearity is unconfirmed. Read the live
> value rather than recomputing the ramp; use the ramp only as a fallback label.

---

## 5. Widget mapping

Layout follows the canonical MaxPane template (`screens/talismans.py:58-80`):

```
title-bar
hero metrics                    (3 cards)
middle-row      [ leaderboard | right-col: sparkline + signals ]
separator
bottom-row      [ activity feed | table A | table B ]
status bar
```

| Slot | Widget | Content |
|---|---|---|
| Hero 1 | `FWAHeroMetrics` | **PULL EV** — band (best estimate + lower bound), green/red, coverage badge |
| Hero 2 | `FWAHeroMetrics` | **PRICE** — live `acquisitionFee()`, with the harmonic-vs-arithmetic gap bar |
| Hero 3 | `FWAHeroMetrics` | **CROWN** — pot in ETH/USD + "ETH to seize" = `1.10 × incumbent backing` |
| Leaderboard | `FWAOddsBoard` | 38 live collections: positions, % of draw weight, ETH backed, floor, **ETH-per-odds-point**. Sorted by weight share. TTT 49.08% ↔ Punks 0.000% |
| Sparkline | `FWASparkline` | $FWA price, GeckoTerminal hourly OHLCV (100 candles) |
| Signals | `FWASignals` | Pool temperature (s since last request → your surcharge share) · buy-gate badge · emissions countdown · VRF queue depth · parameter-drift alarm |
| Activity feed | `FWAActivityFeed` | Live draws: wallet, collection drawn, and the settlement choice made |
| Table A | `FWAChaseBoard` | Richest positions: backing, ~0% odds, **jackpot ratio** (max 221 ETH → 1,378×) |
| Table B | `FWASettlementTable` | Settlement outcome mix + crown history (**17 deduped reigns** across 10 holders — 33 raw logs less 16 vacate shadows — 12 payouts, 91.096 ETH) |

Row/line budgets must match the existing widgets — mirror the counts in
`widgets/talismans/` and `widgets/ttt/` rather than inventing new sizes.

### The crown and the jackpot are the same position

At block 25612701 `topListingId == 56508` — the 221 ETH position. So "1,378× best case" on the
chase board and "ETH to seize the crown" on hero 3 are two views of **one listing**, and the
widgets must not present them as unrelated facts. Whether that stays true is a live question
(the crown moves when someone out-backs it), so the screen should detect the coincidence rather
than assume it: when `topListingId` is also the max-backing position, say so.

Two smaller consumer notes: `weight_share_pct` is rounded to 6 dp and the 38 collection values
sum to `100.000001`, not `100.0` — any widget asserting an exact 100 will trip. And Punks
measures 0.00023%, not the earlier synthetic 0.00021%; both round to the documented 0.000%.

### The crown is not a leaderboard

The "top deposit reward" is a **single-holder crown**, not a ranked table. Takeover
requires `≥ 1.10 × incumbent backing`. Historical crown sets/settlements are synthesized
from `TopListingSettled` logs — **dedupe the vacate+set event pairs**, they arrive together.
One wallet currently holds 4 crowns.

---

## 6. Data layer

New files, following the Talismans/TTT convention:

| File | Purpose |
|---|---|
| `maxpane_dashboard/abis/fwa/*.json` | 8 vendored ABIs: core, rewards, vrf, token, hook, whitelist, splitter, claim |
| `maxpane_dashboard/data/fwa_models.py` | `Position`, `CollectionOdds`, `PullEV`, `Crown`, `PoolTemp`, `ConfigParam`, `SettlementMix` + the frozen `FWA_DATA_KEYS` / `FWA_WIDGET_SIGNATURES` interface |
| `maxpane_dashboard/data/fwa_client.py` | **state pool** — RPC + Multicall3 position enumeration |
| `maxpane_dashboard/data/fwa_logs.py` | **log pool** — `eth_getLogs` against a separate endpoint set |
| `maxpane_dashboard/data/fwa_market.py` | off-chain: DexScreener, GeckoTerminal, CoinGecko floors |
| `maxpane_dashboard/data/fwa_cache.py` | tiered TTL cache |
| `maxpane_dashboard/data/fwa_manager.py` | orchestration + `fetch_and_compute()` |
| `maxpane_dashboard/analytics/fwa_ev.py` | pure EV/odds math — offline-testable, TDD |
| `maxpane_dashboard/analytics/fwa_signals.py` | badges and thresholds |
| `maxpane_dashboard/screens/fwa.py` | `FWAScreen` |
| `maxpane_dashboard/widgets/fwa/` | the 7 widgets above |

**Amendment (2026-07-26).** The client and analytics modules are each split, approved after
planning. State and log reads *must* use different endpoint pools (see below), so collapsing
them into one file would have put an oversized module on the critical path; and pure math
separates cleanly from presentation badges. Repo precedent: bakery already ships
`analytics/ev.py` alongside `analytics/signals.py`.

ABIs are **vendored into the repo**. Etherscan HTML scraping was a research technique only
and must not appear in the shipped data layer.

### Endpoints

**State reads** — `https://ethereum-rpc.publicnode.com`, the only tested endpoint that
supports JSON-RPC batching. All position enumeration goes through Multicall3
`0xcA11bde05977b3631167028862bE2a173976CA11`, max 500 calls per `eth_call`, so 3,867
positions resolve in ~8 calls. **Multicall3 callData must be passed without the `0x`
prefix.** Fallbacks: `https://cloudflare-eth.com`, `https://1rpc.io/eth`.

**Log reads** — publicnode **refuses `eth_getLogs`**. Use
`https://gateway.tenderly.co/public/mainnet` (no range cap), fallback `https://eth.drpc.org`
(10,000-block pages, no batching). This is the design's one genuine single point of
failure: if both fail, the activity feed and crown history degrade to an explicit
"unavailable" state while every other widget keeps working. The dashboard must never
blank out because logs are down.

**Market data** — DexScreener `/latest/dex/tokens/0xa0Df…C845` (observed: $0.031, FDV
$31.1M, liquidity $1.19M, 24h volume $5.0M). OHLCV from GeckoTerminal
`/networks/eth/pools/{poolId}/ohlcv/hour` — 100 candles, ~10 days of history maximum
because the pool was created 2026-07-16. Revenue/TVL cross-check via DefiLlama
`api.llama.fi/summary/fees/fake-world-assets`.

**NFT floors** — CoinGecko `/api/v3/nfts/ethereum/contract/{addr}`, **22 of 38 collections
only**, ≥2.5 s spacing between calls. Cache for hours, never on the fast path.

**Confirmed dead — do not use:** `eth.llamarpc.com` (521), `rpc.ankr.com/eth` (now
requires a key), `api.reservoir.tools` (DNS gone), Sourcify (404 for all 8 contracts).
**There is no project API** — `/api/*`, `/llms.txt` and `/sitemap.xml` all 404, so every
number must come from chain or a public aggregator.

### Contract addresses (all Etherscan-verified, `eth_getCode` non-empty, cross-wired onchain)

| Label | Address |
|---|---|
| FWA core | `0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c` |
| FWARewards | `0x6a1a1C0CfB3D3C538e13D36d608a5bcaa992fc78` |
| FWAVRFService | `0xa084c33Fb7a467307452898b8D58165ebd2E5D9f` |
| FWAToken ($FWA) | `0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845` |
| FWATokenHook (Uniswap v4) | `0x2C67ebA8A50AF0dB5Fba55F725247a75CbDA6444` |
| FWAClaim | `0xd4085d38855F17EdF0B1CCBFad7B3846fb305655` |
| FWAWhitelist | `0x854352b275cF6A0DfFCf2983C986FBe9345e17c3` |
| Splitter | `0x1C175b9F0e8C73eD3e677e1cBb1B5A2DD4373Bfe` |
| Owner (plain EOA — no multisig, no timelock) | `0x019817aD02a31B990433542097bE29D97613E8Cb` |
| VRF 2.5 coordinator | `0xD7f86b4b8Cae7D942340FF628F82735b7a20893a` |
| Uniswap v4 PoolManager | `0x000000000004444c5dc75cB358380D2e3dE08A90` |
| $FWA/ETH v4 **poolId** (not a contract) | `0x230ecd3c25b44af30db59c15f70df7794eb13f67a200f230b7400daa96fe804d` |

### Refresh tiers

| Tier | Interval | Feeds |
|---|---|---|
| Fast | 15 s | `acquisitionFee()`, pool temperature, VRF queue depth, crown pot |
| Medium | 60 s | full position enumeration → odds board, chase board, Pull EV |
| Slow | 15 min | CoinGecko floors, DexScreener, GeckoTerminal OHLCV |
| Once | startup | config parameters, 51-collection allowlist, token metadata |

---

## 7. Correctness rules

These are non-negotiable; each one corresponds to a trap the research actually hit.

1. **Weight is inverse.** `weight = 1e36 / backing` (`INVERSE_WEIGHT_NUMERATOR`). Verified
   against all 3,867 live positions, 0 mismatches. Any proportional-weighting assumption
   is wrong.
2. **`acquisitionFee()` uses two floor divisions.** `(weightedBackingTotal / totalWeight)
   × 11000 / 10000`, integer arithmetic throughout. Reproduced bit-exact at block
   25612655 — the test must assert bit-exactness, not approximate equality.
3. **`settlementDiscountBps() = 8500` is the purchaser *payout* (85%)**, not the 15%
   discount. Naming trap; do not invert it.
4. **`weightedBackingTotal` is not TVL.** It is `Σ(weight × backing) ≈ count × 1e36`. For
   value held, use `eth_getBalance(core)`.
5. **Fees split *equally* across positions.** `feeShare = 1` each; verified
   `feeShareTotal() == activeListingCount()`. Backing buys *duration*, not share size.
6. **Read parameters live, never from docs.** The crown tithe is documented at 5% but live
   at 1% (`ConfigSet key=15 → 100`, block 25592190). Only 6 `ConfigSet` events exist ever,
   so one topic filter drives the entire parameter-drift widget.
7. **Derive the allowlist from `CollectionWhitelistSet` logs** — 51 collections live, not
   the 16 in the docs.
8. **Backing is mutable** via `updateBacking(uint256,uint256) payable`. Cached positions
   go stale; never treat backing as immutable.
9. **Always quote with explicit `gasPrice` and bounded `gas`.** Two agents disagreed on
   whether the VRF fee is genuinely 0 or an unset-`gasPrice` artifact; explicit parameters
   make the question moot.
10. **Watch for dynamic-tuple decode traps** — the known Talismans gotcha. Any getter
    returning a struct array needs its decode asserted against a known-good raw hex
    fixture.
11. **Position storage has free-list slot holes.** A naive sweep returns 3,624 of 3,879
    slots and yields a total off by exactly `255e36` — plausible-looking and silently
    wrong, which is the most dangerous failure mode this dashboard has. Every sweep is
    **block-pinned**, results are never merged across blocks, `BackingUpdated` invalidates
    the cache, and a runtime invariant assertion must fail loudly rather than render a
    wrong number. Added after planning surfaced it; see plan risk R5.

### Waterfall (from verified source)

```
acquisitionFee
  − token slice (dynamic, pool-temperature dependent)
  − 1% owner cut
  − 1% crown tithe
  = remainder, split equally across all active positions
```

Splitter `totalReceived() = 720.688 ETH` cumulative, legs 63/7/30, effective take rate 8.8%.

---

## 8. Time-sensitive context

**$FWA emissions hard-stop: 2026-08-04T19:01:23Z** (`emissionStart` 1784574083 + 15 days),
20M FWA/day = 2% of supply/day. Roughly 9 days out at time of writing.

Consequence for design: the emissions countdown is a *signal row*, not a hero tile.
Anything built around the emission event goes stale in days; the pool mechanics do not.
The dashboard must remain fully meaningful after emissions end — and should degrade
gracefully, showing "emissions ended" rather than a negative countdown.

**The stop lands mid-build, so the post-emissions state is the PRIMARY tested case** and
the live countdown is the secondary/legacy one. No acceptance criterion anywhere may assume
a running countdown.

**Buy gate:** `FWATokenHook.externalBuysEnabled() = false`. Outside buys are still blocked;
DexScreener's 11.4k "buys" are FWARewards-routed distributions, not open-market purchases.
Flipping this flag is the single biggest scheduled event for the token, so it earns a
red/green badge that a user can watch.

---

## 9. Testing

Mirroring `tests/` layout for Talismans:

| File | Covers |
|---|---|
| `tests/data/test_fwa_models.py` | model construction, field validation, the frozen interface constants |
| `tests/data/test_fwa_client.py` | state pool: Multicall3 encoding (callData with `0x` stripped), the ≤500-call batch cap, block-pinned sweeps, **free-list slot holes**, fallback rotation |
| `tests/data/test_fwa_logs.py` | log pool: paging, endpoint fallback, `TopListingSettled` vacate+set dedupe |
| `tests/data/test_fwa_market.py` | DexScreener / GeckoTerminal / CoinGecko shapes against recorded fixtures, partial floor coverage |
| `tests/data/test_fwa_cache.py` | tiered TTL behaviour, `BackingUpdated` invalidation |
| `tests/data/test_fwa_manager.py` | orchestration, single-flight sweeps, atomic publish, partial-failure degradation |
| `tests/analytics/test_fwa_ev.py` | **the math**: inverse weight, harmonic mean, bit-exact `acquisitionFee` at pinned block 25612655, EV band, coverage accounting, crown seize price, surcharge ramp |
| `tests/analytics/test_fwa_signals.py` | badge thresholds and states |
| `tests/widgets/test_fwa_widgets.py` | widget `update_data()` contracts |
| `tests/screens/test_fwa_screen.py` | headless screen test, per the Talismans convention |

All math tests run offline against fixtures. No test may require network access.

**Degradation tests are mandatory**, not optional: logs endpoint down, floors partially
missing, RPC fallback exhausted, market data down, the combined worst case, an invariant
mismatch, and the elapsed emissions window (the *primary* case — see §8). Each must render a
clear degraded state rather than a crash or a silently wrong number.

---

## 10. Registration checklist

> **Line numbers below were captured at spec time and have since drifted.** The
> implementation plan publishes a verified delta table; treat that as authoritative and
> re-verify before editing. Anchor on surrounding code, not on the numbers here.

| File | Change |
|---|---|
| `maxpane_dashboard/app.py` | import `FWAManager` (manager imports ~11-18) |
| `maxpane_dashboard/app.py` | import `FWAScreen` (screen imports ~19-33) |
| `maxpane_dashboard/app.py` | instantiate `self._fwa_manager` (init ~67-90) |
| `maxpane_dashboard/app.py` | initial-game fetch branch for `"fwa"` (prefetch chain ~101-166) |
| `maxpane_dashboard/app.py:184` | add `"fwa"` to `_GAME_CYCLE` |
| `maxpane_dashboard/app.py` | screen install branch (install chain ~192-272; insert **before** the `else: return` at ~271) |
| `maxpane_dashboard/app.py` | shutdown: `await self._fwa_manager.close()` (~354-400) |
| `maxpane_dashboard/screens/game_select.py` | add row `("9", "fwa", "Fake World Assets", "NFT gacha pool w/ inverse-weighted VRF draws on Ethereum")` (GAMES ~11-24) |
| `maxpane_dashboard/__main__.py:56` | add `"fwa"` to `--game` choices |
| `maxpane_dashboard/__main__.py:51` | add `"fwa"` to `--theme` choices |
| `maxpane_dashboard/themes/__init__.py` | register the `fwa` `Theme` object |
| `maxpane_dashboard/themes/minimal.tcss` | `#fwa-*` CSS rules (file is ~1770 lines; Talismans block at ~1717-1769) |

All shared files above are owned by a **single** registration work package so parallel
agents never contend on them. A package that needs a one-line change here hands over the
diff rather than editing the file itself.

---

## 11. Theme

A gachapon/casino register, kept within the existing minimal aesthetic — the same way
Talismans got an alchemical treatment without breaking the template. Green/red for EV
sign, a cold→hot gradient for pool temperature, and gold reserved exclusively for the
crown. Restraint over novelty: the numbers are the content.

**Decision (2026-07-26): ship a full registered theme, not a CSS block alone.** `fwa`
becomes a selectable `Theme` in `themes/__init__.py` and a `--theme fwa` choice, so the
whole app can be recolored, not just this screen.

Two accessibility constraints follow from that palette and are non-optional:

- **Colour may never be the sole carrier of the EV sign.** Pair green/red with an explicit
  `+`/`−` glyph, so the flagship metric survives greyscale and colour-blind viewing.
- **Gold-on-dark (crown) and the red/green EV sign are the two contrast risk spots.** Both
  must clear the accessibility audit rather than being waved through as decorative.

---

## 12. Success criteria

1. Pull EV renders as an honest band with visible coverage, and never as a bare confident
   number while floors are missing.
2. `acquisitionFee()` is reproduced bit-exact in tests against a pinned block.
3. The odds board makes the harmonic/arithmetic gap immediately legible, whatever its current
   value — the multiple is computed live, never asserted or hardcoded (findings §13.7).
4. Pool temperature tells a user, at a glance, whether the surcharge currently flows to
   them or to depositors.
5. Every displayed parameter is read live from chain; no documented value is hardcoded.
6. The dashboard stays useful after emissions end on 2026-08-04, and that state is the one
   the test suite treats as normal.
7. Any dead data source degrades to an explicit unavailable state, never a wrong number.
8. The position sweep either covers every live slot or fails loudly. A partial sweep that
   renders a plausible total is a defect, not a degraded state (§7 rule 11).
9. Every number that carries meaning through colour also carries it through a glyph or
   sign, so the flagship EV metric survives greyscale and colour-blind viewing.

---

## 13. Open questions

Carried from `docs/fwa_technical_findings.md` §12. None blocks implementation; each has a
stated mitigation.

| Question | Mitigation |
|---|---|
| Is the VRF fee genuinely 0, or an unset-`gasPrice` artifact? Agents disagreed. | Always quote with explicit `gasPrice` + bounded `gas` |
| `tokenShareBps(uint256)` linearity unconfirmed | Read the live value; treat the ramp as a label only |
| `ListingStatus` / `AcquisitionStatus` enums unread | Recover from ABI during implementation |
| FWAClaim holds 3.6M of a stated 200M — genuine claims or owner `rescue`? | Do not display a claim-progress figure until resolved |
| Whether 500M FWA sits "in the pool" — PoolManager is a singleton, placement unverified | Do not make this claim anywhere in the UI |
| No reliable keyless floor source for 16 of 38 collections | The EV band's lower bound handles it by construction |
