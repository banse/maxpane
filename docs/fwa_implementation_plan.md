# FWA "Gacha Terminal" Dashboard — Implementation Plan

> Created: 2026-07-26
> Target: MaxPane dashboard #9 (`fwa`)
> Mode: **Deep** — new chain-data integration, integer-exact financial math on display, a
> single-point-of-failure log gateway, a hard external deadline (2026-08-04), and a number on
> screen that tells a user whether to spend ETH.
>
> Authoritative spec: [`docs/fwa_PRD.md`](fwa_PRD.md) (APPROVED — not re-litigated here)
> Research inputs: [`docs/fwa_technical_findings.md`](fwa_technical_findings.md) ·
> [`docs/fwa_game_mechanics.md`](fwa_game_mechanics.md)
> Work packages: [`docs/fwa_work_packages.md`](fwa_work_packages.md)

---

## 1. Problem statement

MaxPane ships 8 dashboards. FWA (`fwa.fun`) is #9: an Ethereum-mainnet NFT gacha pool whose
economics collapse into one observable gap (the harmonic mean backing you pay for versus the
arithmetic mean the pool holds — a live ratio, ~3.5× at block 25621114; see findings §13.7 and
never hardcode it) and one continuously-answerable question: **is a pull worth it right now?**

The engineering problem is *not* "can we read the chain" — the research already proved every read
works keylessly, bit-exact, in 3.3 seconds. The engineering problems are:

1. **Interface-before-implementation.** Seven widgets, four data sources, three endpoint pools and a
   pure-math analytics layer must be built concurrently by different agents. Without a frozen data
   contract they will not compose.
2. **Honesty under partial information.** Floors exist for 22 of 38 collections and the two largest
   weight buckets (68% combined) are unpriced. The flagship number must be a band with a coverage
   badge, never a confident point estimate.
3. **Degradation as a feature.** `eth_getLogs` has exactly two keyless providers. The dashboard must
   never blank out, never crash, and never show a silently wrong number when one dies.
4. **A hard clock.** $FWA emissions stop **2026-08-04T19:01:23Z** — likely *before or just after*
   this dashboard ships. The post-emissions state is not an edge case; it is probably the default
   state within two weeks.

**Success criteria** are PRD §12 verbatim. Nothing is added to them.

---

## 2. Scope boundaries (fixed by the PRD — do not renegotiate)

| | |
|---|---|
| **In** | One overview screen `FWAScreen`, 7 widgets, data layer, analytics, tests, registration |
| **Out** | Wallet-scoped views, depositor views, `wallet_input.py` wiring, second screen |
| **Never** | Signing, sending, key prompts, transaction construction, API keys of any kind |
| **Never shown** | Anything in PRD §13 (see §11 traceability table below) |

The dashboard is strictly **read-only** and every source is **keyless**. Fixing the stale endpoints
in `maxpane_dashboard/data/ttt_client.py` (dead llamarpc, keyed Ankr, dead Reservoir) is a known
separate defect — it is **out of scope here** and must not be copy-pasted into FWA code.

---

## 3. Known facts

- **Chain:** Ethereum mainnet (1). Protocol ~66k blocks old → a full historical backfill is cheap
  (58 s for 9 event types across all history).
- **8 contracts**, all Etherscan-verified, all cross-wired onchain, all addresses triple-verified.
- **Enumeration is a solved recipe** (findings §6.1): pin block → `activeListingCount()` →
  Multicall3 sweep `slotToListing` upward from slot 1 skipping zeros until `n` non-zero ids →
  Multicall3 `listings(id)` → assert three aggregate invariants bit-for-bit.
- **`listings()` is a flat 11-tuple of static types** — head-only encoding, 352 bytes, *no* dynamic
  tuple. The Talismans decode trap does not apply to it, but PRD rule 10 still requires a raw-hex
  fixture assertion.
- **Existing infrastructure to copy verbatim:** `talismans_client.py`'s `_rpc` / `_eth_call` /
  `_get_logs` / `_multicall` / `_encode_aggregate3` / `_decode_aggregate3_result` machinery
  (pure-stdlib ABI helpers, no `eth_abi` dependency). Its `_encode_call3` **already strips the `0x`
  prefix from callData** — the trap in findings §6.5 is pre-solved by the existing helper.
- **Canonical screen layout** is `screens/talismans.py:58-80`. FWA uses it with no toggle key
  (Talismans' `c` binding exists only because it hides one of two bottom tables; FWA shows both).
- **CSS convention** is widget-class selectors appended at the end of
  `maxpane_dashboard/themes/minimal.tcss` (Talismans block at 1717-1769; file ends at 1770) — not
  `#id` rules. PRD §10's "`#fwa-*` CSS rules" is satisfied by a `/* ── FWA screen ── */` block in
  the same style as its neighbours, **plus** a registered `fwa` Theme (§8.6) per the user's ruling.
  Themes are registered in `themes/__init__.py` and `THEME_NAMES` is derived from `THEMES.keys()`, so
  registration order sets the `t`-key cycle order.

## 4. Constraints

| Constraint | Consequence |
|---|---|
| Keyless only | publicnode/cloudflare/1rpc for state; tenderly/drpc for logs; DexScreener, GeckoTerminal, CoinGecko, DefiLlama for market. No Etherscan API, no Alchemy, no Reservoir, no OpenSea key. |
| No Etherscan scraping in shipped code | ABIs are **vendored** into `maxpane_dashboard/abis/fwa/`. Any retrieval script lives in `scripts/`, is run once, and is imported by nothing. |
| publicnode refuses `eth_getLogs` | State and logs **must** use different endpoint pools. This is a hard structural requirement, not a preference. |
| Multicall3 ≤ 500 calls per `eth_call` | 3,867 positions ≈ 8 calls for `listings`, ≈ 9-10 for the slot scan to ~4,500 → ~17-18 `eth_call`s ≈ 3.3 s per sweep. Too heavy for a 15 s tick. |
| publicnode 429s under aggressive batching | ≤ 500 calls per Multicall3 `eth_call`; ≤ 60 elements per raw JSON-RPC batch with ~0.12 s spacing. |
| CoinGecko NFT floors | ≥ 2.5 s spacing, still 429s; 38 collections = 203 s. Background sweep only, 15 min TTL, persisted. Never on the fast path. |
| No test may touch the network | Every fixture is committed. Math is pure and offline-verifiable. |
| Widgets never import models/analytics | `update_data()` takes primitives (`str`/`int`/`float`/`bool`/`dict`/`list[dict]`) only — existing project rule. |
| Read parameters live | No documented value may be hardcoded (crown tithe is documented 5%, live 1%). |

## 5. Assumptions (stated so they can be challenged)

1. WP-2 and WP-3 (ABI vendoring, fixture recording) have **outbound network access at build time**.
   Everything after them is offline. If network is unavailable, WP-2/WP-3 block the whole plan —
   this is the single hard prerequisite.
2. The live values in the research docs (block 25612655-25612716, 2026-07-25) are stable enough to
   use as *test fixtures*. They are **not** used as display values — every displayed number is read
   live.
3. **Emissions will have ended by, or very shortly after, ship date** — the stop is
   2026-08-04T19:01:23Z and it lands mid-build. **Ruled by the user: the post-emissions state is the
   PRIMARY case.** Every WP builds and tests the after-state as the normal state; the live countdown
   is the secondary/legacy path. **No acceptance criterion anywhere in this plan may assume a live
   countdown.**
4. `tokenShareBps(uint256)` is read live; the documented linear ramp is used **only as a label**.

## 6. Key unknowns

| Unknown | Impact | Mitigation (all from PRD §13 — none blocks work) |
|---|---|---|
| VRF fee genuinely 0 vs unset-`gasPrice` artifact | Price tile shows one number or two | Always call `quoteAcquisitionPrice()` with explicit `gasPrice` + bounded `gas` (e.g. `0x200000`); render the returned tuple; never sum two sources |
| `tokenShareBps` linearity | Pool-temperature accuracy | Read the live value; ramp is a label only |
| `ListingStatus` / `AcquisitionStatus` enums | Labelling non-active positions | **Recovered from the vendored ABIs in WP-2** into `data/fwa_enums.py`; unknown values render as `status N` |
| FWAClaim 3.6M of 200M | Circulating-supply narrative | **No claim-progress figure anywhere in the UI** |
| 500M FWA "in the pool" | Token-supply narrative | **Never asserted anywhere in the UI** |
| 16 of 38 collections have no keyless floor | The flagship EV number | Handled by construction: lower bound zeroes them, best estimate excludes them, coverage badge states it |

---

## 7. Verified registration call sites

PRD §10's line numbers re-audited against the current tree on 2026-07-26. **All still valid within
a few lines**; deltas noted.

| File | PRD says | Verified | Change |
|---|---|---|---|
| `maxpane_dashboard/app.py` | 17-18 | manager imports block **11-18** (talismans 17, ttt 18) | insert `from maxpane_dashboard.data.fwa_manager import FWAManager` after line **14** (keeps alphabetical order after `frenpet_manager`) |
| `maxpane_dashboard/app.py` | 32-33 | screen imports block **19-33** (talismans 32, ttt 33) | insert `from maxpane_dashboard.screens.fwa import FWAScreen` in the block (after line **27**) |
| `maxpane_dashboard/app.py` | 89-90 | manager init block **67-90** (talismans **90**) | add `self._fwa_manager = FWAManager(poll_interval=poll_interval)` after line **90** |
| `maxpane_dashboard/app.py` | 155-163 | initial-game chain **101-166** (talismans branch **161-166**) | add `elif self._initial_game == "fwa":` after line **166** |
| `maxpane_dashboard/app.py` | 184 | `_GAME_CYCLE` at **184** ✅ | append `"fwa"` |
| `maxpane_dashboard/app.py` | 255-269 | install chain **192-272** (talismans branch **261-270**, `else: return` at **271**) | add `elif game_id == "fwa":` after line **270** |
| `maxpane_dashboard/app.py` | 393-399 | shutdown chain **354-400** (talismans **396-399**, `self.exit()` at **400**) | add try/except `await self._fwa_manager.close()` after line **399** |
| `maxpane_dashboard/screens/game_select.py` | 22-23 | `GAMES` list **11-24** (talismans row **23**) | add `("9", "fwa", "Fake World Assets", "NFT gacha pool w/ inverse-weighted VRF draws on Ethereum")` after line **23** |
| `maxpane_dashboard/__main__.py` | 56 | `--game` choices **56** ✅ | append `"fwa"` |
| `maxpane_dashboard/__main__.py` | — | `--theme` choices **51** (missing from PRD §10 — **now in scope**) | append `"fwa"`. An `fwa` Theme **is** registered (§8.6), so this line is mandatory, not conditional. Owned by WP-17; WP-16 hands over the exact one-line diff. |
| `maxpane_dashboard/themes/minimal.tcss` | `#fwa-*` rules | file is **1770 lines**; Talismans block **1717-1769** | append a `/* ── FWA screen ── */` widget-class block at EOF |

> **These four files (`app.py`, `game_select.py`, `__main__.py`, `minimal.tcss`) are the only shared
> files in the whole plan.** `minimal.tcss` + `themes/__init__.py` are owned exclusively by WP-16;
> `app.py` + `game_select.py` + `__main__.py` are owned exclusively by WP-17. No other work package
> may touch any of them. See §14.

---

## 8. Architecture and file inventory

### 8.1 New files

```
maxpane_dashboard/
  abis/fwa/
    fwa_core.json            fwa_rewards.json      fwa_vrf_service.json
    fwa_token.json           fwa_token_hook.json   fwa_claim.json
    fwa_whitelist.json       splitter.json
    topics.json              # generated: event name -> topic0
    selectors.json           # generated: function signature -> 4-byte selector
  data/
    fwa_models.py            # THE INTERFACE — frozen Pydantic models + flat-dict key contract
    fwa_enums.py             # ListingStatus / AcquisitionStatus recovered from the ABIs
    fwa_client.py            # STATE pool: publicnode + Multicall3, sweep, invariants, quote
    fwa_logs.py              # LOG pool: tenderly + drpc, decoders, backfill + tail
    fwa_market.py            # off-chain keyless: DexScreener, GeckoTerminal, CoinGecko, DefiLlama
    fwa_cache.py             # tiered TTL cache + persistence + last-good snapshots
    fwa_manager.py           # orchestration, degradation, fetch_and_compute()
  analytics/
    fwa_ev.py                # pure integer/float math: weights, means, fee, EV band, ratios
    fwa_signals.py           # signal rows, badges, thresholds, countdowns, drift
  widgets/fwa/
    __init__.py
    fwa_hero_metrics.py      fwa_odds_board.py        fwa_sparkline.py
    fwa_signals.py           fwa_activity_feed.py     fwa_chase_board.py
    fwa_settlement_table.py
  screens/
    fwa.py                   # FWAScreen
scripts/
  vendor_fwa_abis.py         # one-shot, research-only, imported by nothing
tests/
  fixtures/fwa/*.json        # recorded raw hex + recorded HTTP payloads
  data/test_fwa_models.py         test_fwa_client.py       test_fwa_logs.py
  data/test_fwa_market.py         test_fwa_cache.py        test_fwa_manager.py
  data/test_fwa_refresh_budget.py test_fwa_degradation.py
  analytics/test_fwa_ev.py        test_fwa_signals.py
  widgets/test_fwa_widgets.py
  screens/test_fwa_screen.py
  test_fwa_theme.py               # theme registration + --theme fwa selection
  test_fwa_guardrails.py
```

Modified files, in total: `themes/minimal.tcss` and `themes/__init__.py` (WP-16), `app.py`,
`screens/game_select.py`, `__main__.py` (WP-17), plus `README.md` and `CLAUDE.md` (WP-21).

### 8.2 Module boundaries (committed — PRD §6 amended to match)

The user approved both decompositions and **PRD §6 has been amended accordingly**, so the two
documents no longer disagree. This is the committed layout, not a deviation. No behaviour is added,
removed or changed relative to the approved scope.

| Concern | Module | Rationale |
|---|---|---|
| State reads — "RPC + Multicall3" | `data/fwa_client.py` | PRD §6 mandates that logs and state use **different endpoint pools**, with different retry, pagination and failure semantics. |
| Event logs | `data/fwa_logs.py` | publicnode refuses `eth_getLogs`; Pool B has its own pagination caps and its own degradation story. Independently testable failure domain. |
| Off-chain feeds — DexScreener, GeckoTerminal, CoinGecko floors, DefiLlama | `data/fwa_market.py` | Third-party HTTP contracts with hostile rate limits and partial coverage; nothing in common with chain plumbing. |
| Pure pricing/EV math | `analytics/fwa_ev.py` | Repo precedent: bakery ships `analytics/ev.py` + `analytics/signals.py`; Cat Town ships three analytics modules. Lets the integer-exact math be developed strictly TDD against fixtures. |
| Signal rows, badges, thresholds | `analytics/fwa_signals.py` | Presentation-facing judgement, separable from the arithmetic. |

Three data modules and two analytics modules = five agents working concurrently with zero file
contention. PRD §9's `test_fwa_signals.py` row is satisfied by `test_fwa_ev.py` +
`test_fwa_signals.py` together.

### 8.3 Endpoint pools (hard-wired, never crossed)

```
POOL A — state / views          POOL B — event logs             POOL C — off-chain, keyless
  https://ethereum-rpc.           https://gateway.tenderly.co     api.dexscreener.com
    publicnode.com  (batcher)       /public/mainnet (no cap)      api.geckoterminal.com
  fallback cloudflare-eth.com     fallback https://eth.drpc.org   api.coingecko.com/api/v3/nfts
  fallback https://1rpc.io/eth      (10,000-block pages)          api.llama.fi
  Multicall3 0xcA11bde0…76CA11    NEVER publicnode (refuses)      api.opensea.io (opportunistic)
```

**Banned hosts** (guardrail-tested in WP-18): `eth.llamarpc.com`, `rpc.ankr.com`,
`api.reservoir.tools`, `api-mainnet.magiceden.dev`, `sourcify.dev`, any `etherscan.io` URL,
any `api.etherscan.io` URL.

### 8.4 Refresh tiers and call budget

| Tier | Interval | Feeds | Budget |
|---|---|---|---|
| Fast | 15 s | `quoteAcquisitionPrice`, `acquisitionFee`, pool temperature (`lastAcquisitionTs`), VRF queue depth, crown pot, gate flags, `eth_getBalance(core)` | **1** Multicall3 `eth_call` (~30 views across 8 contracts) + 1 balance call |
| Medium | 60 s | full position enumeration → odds board, chase board, Pull EV | **~17-18** `eth_call`s, ~3.3 s, single-flight |
| Slow | 15 min | CoinGecko floor sweep (persisted), DexScreener, GeckoTerminal OHLCV, DefiLlama | 38 × ≥2.5 s background, off the hot path |
| Tail | 30 s | `eth_getLogs` lastSeen → latest on Pool B | 1-2 requests |
| Once | startup | config params, 51-collection allowlist (`CollectionWhitelistSet`), token metadata, full log backfill | ~58 s one-time, persisted |

**Interaction rule (the risk the brief calls out):** the 60 s sweep must never starve the 15 s tier.
Enforced by (a) a single-flight lock — if a sweep is still running when the next 60 s tick fires,
**skip** it rather than queue it; (b) the fast tier never awaits the sweep; (c) the sweep publishes
atomically (build a new position list, then swap) so widgets never read a half-built pool; (d) every
sweep pins one `blockTag` and its three invariant assertions run at that same block.

### 8.5 The interface: `data/fwa_models.py`

WP-1 freezes three things simultaneously, and nothing else may start until it lands:

1. **Models** — PRD §6's seven (`Position`, `CollectionOdds`, `PullEV`, `Crown`, `PoolTemp`,
   `ConfigParam`, `SettlementMix`) plus three plumbing models the Talismans/TTT convention requires
   (`FWASignal` — the `{label, value_str, indicator, color}` row; `DrawEvent` — one activity-feed
   line; `FWASnapshot` — the per-cycle container). All frozen (`ConfigDict(frozen=True)`).
2. **`FWA_DATA_KEYS`** — an explicit, importable tuple of every key `fetch_and_compute()` returns,
   grouped by consumer widget. This is what makes the contract machine-checkable: WP-12's tests
   assert the manager returns exactly these keys, and WP-13's screen test asserts every key is
   dispatched.
3. **Widget signature table** — the exact `update_data(**kwargs)` signature of all seven widgets, in
   the module docstring. Widget WPs and the manager WP both code against it.

Draft key groups (WP-1 finalizes names; shape is fixed):

```
hero      pull_ev_best · pull_ev_lower · ev_available · ev_coverage_collections ·
          ev_coverage_weight_pct · acquisition_fee_eth · vrf_fee_eth · quote_total_eth ·
          harmonic_mean_eth · arithmetic_mean_eth · hm_am_gap_x · price_available ·
          crown_pot_eth · crown_pot_usd · crown_seize_eth · crown_holder · crown_available
odds      collection_odds[] {rank,name,address,positions,weight_share_pct,eth_backed,
                             floor_eth|None,floor_source,eth_per_odds_point,floor_note} ·
          odds_available · odds_as_of_block · odds_stale
spark     fwa_price_history[[ts,close]] · fwa_price_usd · fwa_price_change_24h · spark_available
signals   pool_temp_signal · buy_gate_signal · emissions_signal · vrf_queue_signal ·
          param_drift_signal            (each an FWASignal dump or None)
feed      draw_events[] {ts,block_number,tx_hash,purchaser,collection,token_id,outcome,
                         outcome_label,amount_eth} · feed_available · feed_unavailable_reason
chase     chase_positions[] {rank,listing_id,collection,token_id,backing_eth,odds_pct,
                             expected_draws,jackpot_ratio,sellback_eth}
settle    settlement_mix[] {outcome,count,share_pct} · crown_history[] ·
          crown_sets_total · crown_payouts_total · crown_paid_eth · settle_available
meta      active_positions · eth_in_core · cumulative_revenue_eth · take_rate_pct ·
          current_block · invariants_ok · degraded_sources[] ·
          last_updated_seconds_ago · error_count · poll_interval
```

Every `*_available` flag exists so a widget can render an explicit unavailable state without
guessing from a `None`.

### 8.6 Theme: a registered `fwa` Theme, not a CSS block alone

**Ruled by the user.** PRD §11's gachapon/casino register is delivered as a *full theme*, mirroring
how `talismans` is registered at `themes/__init__.py:132`. Three artifacts, two owners:

| Artifact | File | Owner |
|---|---|---|
| `#fwa-*` / widget-class CSS block | `themes/minimal.tcss` (append at EOF) | **WP-16** |
| `Theme(name="fwa", …)` registration | `themes/__init__.py` | **WP-16** |
| `"fwa"` in `--theme` choices | `__main__.py:51` | **WP-17** (WP-16 supplies the one-line diff) |

The split of the third row is deliberate: `__main__.py` stays **exclusively WP-17's file** even
though the change is thematic, so the contention discipline in §14 holds without exception. WP-16
never opens `__main__.py`; it hands WP-17 the literal diff to apply.

Palette (PRD §11 — restraint over novelty; the numbers are the content):

| Semantic | Colour | Rule |
|---|---|---|
| EV sign | green / red | **Never the sole carrier.** Always paired with a glyph or sign character (`▲`/`▼`, `+`/`−`). Enforced by a WP-10 widget test and re-verified by WP-19. |
| Pool temperature | cold → hot gradient | Paired with a direction in words (`→ YOU` / `→ depositors`). |
| Crown | gold | **Reserved exclusively for the crown.** Appears nowhere else on the screen. |
| Everything else | theme variables (`$panel`, `$surface`, `$text-muted`, `$primary`) | So the FWA screen stays legible under all other registered themes. |

Two known contrast risk spots, both explicitly assigned to WP-19's audit: **gold-on-dark on the
crown tile**, and the **red/green EV sign**. If either fails contrast under any registered theme, the
fix is to adjust the theme's colour, not to drop the glyph.

Theme work is testable and therefore tested: WP-16 ships `tests/test_fwa_theme.py` covering
registration, `THEME_NAMES` membership and the palette contract; WP-17 appends the `--theme fwa`
CLI-selection tests to the same file in wave 5 (sequential, so no contention).

---

## 9. Reuse map — what to copy, what is genuinely new

| Slot | Closest existing artifact | Verdict |
|---|---|---|
| `FWAHeroMetrics` | `widgets/talismans/tal_hero_metrics.py` (4 boxes) · `templates/hero_metrics_template.py` | **Adapt.** 3 boxes not 4; each box adds a second render line (EV band / gap bar / seize price). Reuse `_fmt_int`/`_fmt_float` helpers and the `"--"`-on-`None` discipline verbatim. |
| `FWAOddsBoard` | `widgets/talismans/tal_leaderboard.py` · `templates/leaderboard_template.py` | **Reuse structure as-is.** DataTable, local `_short_addr`/`_fmt_*` helpers, 6 columns. |
| `FWASparkline` | `widgets/talismans/tal_sparkline.py` | **Reuse `_build_sparkline` and `_coerce_points` verbatim** (copy into the file — project rule keeps format helpers local). One series instead of two. |
| `FWASignals` | `widgets/talismans/tal_signals.py` (4 rows) | **Reuse as-is**, 5 rows. Same `_fmt_signal` + `{label,value_str,indicator,color}` contract. |
| `FWAActivityFeed` | `widgets/talismans/tal_activity_feed.py` · `templates/activity_feed_template.py` | **Reuse as-is** (RichLog). New: must render an explicit `logs unavailable` line, which Talismans does not have. |
| `FWAChaseBoard` | `widgets/talismans/tal_materials_table.py` | **Reuse as-is** (ranked DataTable). |
| `FWASettlementTable` | `widgets/talismans/tal_matrix_table.py` | **Adapt** — two stacked sections (outcome mix + crown history) in one widget. |
| Status bar | `widgets/status_bar.py` | **Reuse verbatim.** Do not build a new one; do not use `templates/status_bar_template.py`. |
| Screen | `screens/talismans.py:58-80` | **Reuse layout verbatim.** Drop the `c` toggle binding and `on_mount` display juggling — FWA shows both bottom tables. |
| RPC plumbing | `data/talismans_client.py` `_rpc`/`_eth_call`/`_get_logs`/`_multicall`/`_encode_aggregate3`/`_decode_aggregate3_result`/`_encode_uint`/`_decode_uint`/`_decode_address` | **Copy verbatim.** `_encode_call3` already strips `0x` from callData — findings §6.5's trap is pre-solved. |
| Cache | `data/talismans_cache.py` (hourly buckets, ring buffer, atomic temp+rename persistence) | **Reuse pattern**, retarget to `~/.maxpane/fwa_cache.json`. New: per-tier TTL tracking and last-good log snapshots. |
| Manager | `data/talismans_manager.py` (`_safe_call`, flat-dict return, `close()`) | **Reuse pattern.** New: three-pool partial-failure accounting and `degraded_sources`. |
| DexScreener / GeckoTerminal | `data/base_client.py` (`_wait_dexscreener`, `_wait_gecko`, retry) | **Reuse the pacing helpers.** GeckoTerminal *OHLCV* is new — no existing dashboard fetches candles. |
| CoinGecko NFT floors | *nothing exists* (`data/price.py` is `/simple/price` only) | **Genuinely new.** Rate-limited background sweep with persistence. |
| ABI vendoring dir | `abis/cattown/` | **Same pattern**, `abis/fwa/`. |

Nothing in `templates/` needs to be rebuilt, and nothing in `templates/` is sufficient unmodified.

---

## 10. Correctness-rule traceability (PRD §7)

Every one of the ten non-negotiable rules is assigned an owner and an enforcement mechanism. A rule
with no test is not enforced.

| # | Rule | Owner WP | Enforcement |
|---|---|---|---|
| 1 | `weight = 1e36 / backing` (**inverse**) | WP-4 | `test_fwa_ev.py`: recompute weights for a recorded position set; assert Σ equals the recorded `totalWeight()` **exactly**. Runtime assertion in WP-6's sweep. |
| 2 | `acquisitionFee()` = two floor divisions, integer throughout | WP-4 | `test_fwa_ev.py`: at pinned block **25612655**, `weightedBackingTotal=3890999999999999999275601332649457427323`, `totalWeight=31280618816683353089152` → assert `EV == 124390122292745553` and `fee == 136829134522020108` with `==`, **not** `pytest.approx`. Second pinned case at 25612701 → `136260883651302691`. |
| 3 | `settlementDiscountBps()==8500` is the purchaser **payout** (85%) | WP-4, WP-10 | Named `purchaser_payout_bps` in code; `test_fwa_guardrails.py` (WP-18) greps shipped FWA modules for the string `discount` adjacent to `8500` and for any UI label calling 8500 a discount. |
| 4 | `weightedBackingTotal` is **not** TVL | WP-6, WP-18 | `eth_getBalance(core)` is the only source for an ETH-held figure. Guardrail test asserts no FWA widget renders `weighted_backing_total` with an ETH/TVL unit label. |
| 5 | Fees split **equally**; `feeShare == 1` | WP-6 | Runtime invariant `feeShareTotal() == activeListingCount()`; surfaced as part of `invariants_ok`. |
| 6 | Read parameters **live**, never from docs | WP-6, WP-7, WP-18 | Every parameter in the flat dict traces to an `eth_call` or a `ConfigSet` log. Guardrail test asserts no FWA module contains the literals `500` for crown tithe, `5%`, or a hardcoded parameter dict. |
| 7 | Derive the allowlist from `CollectionWhitelistSet` logs | WP-7 | Startup backfill builds the 51-collection registry; a hardcoded collection list is a guardrail failure. Address→name from onchain `name()`, not from the docs page. |
| 8 | Backing is **mutable** (`updateBacking`) | WP-6, WP-9, WP-12 | Positions are never merged across blocks; every sweep is block-pinned and fully rebuilt; `BackingUpdated` in the tail invalidates the cached sweep; invariant mismatch → `odds_stale=True`. |
| 9 | Always quote with explicit `gasPrice` + bounded `gas` | WP-6 | `test_fwa_client.py` asserts the `eth_call` params dict for `quoteAcquisitionPrice()` / `requestFee()` contains both `gasPrice` and `gas`. Never sum two fee sources — render the returned tuple. |
| 10 | Assert struct-array decodes against known-good raw hex | WP-3, WP-6 | `tests/fixtures/fwa/listings_56508.json` holds the recorded 352-byte return; the decode test asserts all 11 fields including `value == 221000000000000000000` and `weight == 4524886877828054`. Same for the `aggregate3` result blob. |

Plus the two enumeration traps that the research proved will silently ship wrong numbers:

| Trap | Owner | Enforcement |
|---|---|---|
| Slots are 1-indexed and **non-contiguous** (free list leaves permanent holes) | WP-6 | Scan upward skipping zeros until `activeListingCount` non-zero ids are collected — **never** `slot = 1..n`. Budget 1.2× headroom (~4,500). Assert the collected count; on shortfall, mark degraded rather than publishing. |
| The block **must** be pinned for the whole sweep | WP-6 | One `blockTag` threaded through every `eth_call` of the sweep and all three invariant checks. Unit-tested by asserting the pinned tag appears in every recorded request. |

---

## 11. PRD §13 suppression list — what must NOT appear in the UI

| Open question | UI rule | Enforced by |
|---|---|---|
| VRF fee 0 vs artifact | Render the `quoteAcquisitionPrice()` tuple as returned. No computed/predicted VRF fee. No "fee waived" claim. | WP-6, WP-10, WP-18 |
| `tokenShareBps` linearity | Show the **live** share value. The 60 s/3600 s ramp may appear only as a static label ("hot 60s → cold 3600s"), never as a computed prediction. | WP-5, WP-11 |
| `ListingStatus`/`AcquisitionStatus` | Only ABI-recovered names are shown; unrecovered values render `status N`. | WP-2 |
| FWAClaim 3.6M / 200M | **No claim-progress figure, percentage, bar or count anywhere.** | WP-18 |
| 500M FWA "in the pool" | **Never claimed.** No supply-placement statement. | WP-18 |
| No floor for 16 of 38 collections | EV renders as a band with a coverage badge. Never a single confident EV. No pool-wide "backing vs floor" aggregate. Art Blocks contracts show `multi-collection contract — floor not meaningful`, never a number. | WP-4, WP-8, WP-10 |

WP-18 ships `tests/test_fwa_guardrails.py` as executable enforcement: static scans over
`maxpane_dashboard/**/fwa*` and `widgets/fwa/`, `screens/fwa.py` asserting absence of banned hosts,
banned claim strings, hardcoded parameters, and any signing/keystore import.

---

## 12. Degradation matrix (PRD §9 — mandatory, not polish)

Each row is a required test in WP-15, driven end-to-end through the screen harness.

| Failure | Fails | Keeps working | Rendered state |
|---|---|---|---|
| **Logs endpoint down** (tenderly + drpc both fail) | activity feed, crown history, settlement mix, `ConfigSet` drift, collection registry refresh | hero (all 3), odds board, chase board, sparkline, pool temp, VRF queue, buy gate | Feed: `logs unavailable — activity paused`. Settlement table: last-good values with an explicit `as of HH:MM` staleness label, or `unavailable` if never fetched. `degraded_sources=["logs"]` in the status bar. **Never blank, never a crash.** |
| **Floors partially missing** (22/38, CoinGecko 404/429) | precise EV point estimate | everything | Hero 1 shows band + `22/38 · N% of weight priced`. Odds board floor column shows `—` for missing, `n/a (multi-collection)` for Art Blocks. Lower bound is always renderable because unknown floors are zeroed. |
| **RPC fallback exhausted** (Pool A: publicnode + cloudflare + 1rpc all fail) | live price, sweep, crown pot, queue depth | log-derived widgets if Pool B is alive; cached sparkline | Every hero card `—` with `chain unavailable`; odds board keeps the last-good sweep with `as of block N` and `odds_stale=True`; error count increments; poll continues. |
| **Emissions window elapsed** (after 2026-08-04T19:01:23Z) — **the PRIMARY case, tested first** | nothing | everything | Emissions signal row reads `emissions ended` (dim), **never a negative countdown**. EV drops the emissions-linked framing but still renders. Dashboard remains fully meaningful — PRD §12.6. The pre-stop live countdown is the *secondary* path and is tested second. |
| *(bonus, cheap)* Market feeds down (DexScreener + GeckoTerminal) | sparkline, USD conversions | all chain-derived widgets | Sparkline `waiting for data...`; crown pot shows ETH only, no USD. |

Design rule behind all five rows: **a data source that dies degrades exactly one region of the
screen, labels itself, and leaves every other number correct.** No global error screen.

---

## 13. Wave plan

Full detail in [`docs/fwa_work_packages.md`](fwa_work_packages.md). Summary:

```
WAVE 1  interfaces + evidence + pure math          (4 agents in parallel)
  WP-1  Interface freeze — models + FWA_DATA_KEYS + widget signatures   [Backend Architect]
  WP-2  Vendor 8 ABIs, recover enums, emit topics/selectors             [Evidence Collector]
  WP-3  Offline fixture corpus                                          [Evidence Collector]
  WP-4  EV & pricing math, strict TDD                                   [AI Engineer]

WAVE 2  data layer + widgets, all independent       (7 agents in parallel)
  WP-5  analytics/fwa_signals.py            <- WP-1, WP-4               [Senior Developer]
  WP-6  data/fwa_client.py    (Pool A)      <- WP-1, WP-2, WP-3         [Data Engineer]
  WP-7  data/fwa_logs.py      (Pool B)      <- WP-1, WP-2, WP-3         [Data Engineer]
  WP-8  data/fwa_market.py    (Pool C)      <- WP-1, WP-3               [API Tester]
  WP-9  data/fwa_cache.py                   <- WP-1                     [Data Engineer]
  WP-10 Widgets A: hero, odds board, spark  <- WP-1                     [Frontend Developer]
  WP-11 Widgets B: signals, feed, chase, settlement <- WP-1             [Frontend Developer]

WAVE 3  integration                                  (3 agents in parallel)
  WP-12 data/fwa_manager.py                 <- WP-4..WP-9              [Backend Architect]
  WP-13 screens/fwa.py + widgets/fwa/__init__.py <- WP-10, WP-11       [UI Designer]
  WP-14 Refresh-budget & batching benchmark <- WP-6, WP-9              [Performance Benchmarker]

WAVE 4  hardening                                    (2 agents in parallel)
  WP-15 Degradation & failure-mode suite    <- WP-12, WP-13            [API Tester]
  WP-16 Full fwa Theme + CSS + theme tests  <- WP-13                   [UI Designer]

WAVE 5  registration                                 (1 agent — shared files)
  WP-17 app.py + game_select.py + __main__.py <- WP-12, WP-13, WP-16   [Senior Developer]

WAVE 6  audit                                        (2 agents in parallel)
  WP-18 Correctness/scope guardrail tests   <- WP-17                   [Reality Checker]
  WP-19 Accessibility & multi-theme audit   <- WP-17                   [Accessibility Auditor]

WAVE 7  close-out                                    (2 agents in parallel)
  WP-20 Full-suite integration & regression triage <- all              [Test Results Analyzer]
  WP-21 README + CLAUDE.md inventory, docstring pass <- WP-17          [Technical Writer]
```

Critical path: **WP-1 → WP-6 → WP-12 → WP-13/WP-16 → WP-17 → WP-18/19 → WP-20** (7 waves).
Peak concurrency: 7 agents (wave 2).

---

## 14. Shared-file contention control

Only four files in the repo are touched by more than nothing, and each has exactly one owner:

| File | Sole owner | Wave | Note |
|---|---|---|---|
| `maxpane_dashboard/themes/minimal.tcss` | **WP-16** | 4 | append-only block at EOF |
| `maxpane_dashboard/themes/__init__.py` | **WP-16** | 4 | registers the `fwa` `Theme`, mirroring `talismans` at line 132 |
| `maxpane_dashboard/app.py` | **WP-17** | 5 | 7 insertion points (§7) |
| `maxpane_dashboard/screens/game_select.py` | **WP-17** | 5 | 1 row |
| `maxpane_dashboard/__main__.py` | **WP-17** | 5 | `--game` (56) **and** `--theme` (51). WP-16 supplies the `--theme` diff but never opens the file. |
| `tests/test_fwa_theme.py` | **WP-16** creates (wave 4) → **WP-17** appends (wave 5) | 4, 5 | sequential waves, so no concurrency |
| `maxpane_dashboard/widgets/fwa/__init__.py` | **WP-13** | 3 | WP-10/WP-11 create only their own modules |
| `maxpane_dashboard/widgets/fwa/*` , `screens/fwa.py` | **WP-19 holds an exclusive lock in wave 6** | 6 | WP-10/11/13 are finished by then |
| `README.md`, `CLAUDE.md` | **WP-21** | 7 | disjoint from WP-20's test-only edits |

Every other file in the plan is created by exactly one WP and read-only for everyone else. **No two
concurrently-running work packages write the same file anywhere in this plan.**

---

## 15. Test strategy

- **TDD is mandatory for `analytics/fwa_ev.py` (WP-4).** The module is pure, deterministic and fully
  specified by numbers already recorded in the research docs. Tests are written from the docs
  *before* the implementation, and `acquisitionFee` bit-exactness is asserted with `==` at two
  pinned blocks. Any use of `pytest.approx` on an integer wei value is a review failure.
- **No test may require network access.** Everything goes through
  `tests/fixtures/fwa/*.json`, committed by WP-3: recorded raw `eth_call` returns (the `listings`
  352-byte tuple, an `aggregate3` result blob, the hot-batch blob), recorded `eth_getLogs` pages for
  each of the 9 event types incl. a vacate+set `TopListingSet` **pair**, a CoinGecko NFT 200 and a
  404 and a 429, a DexScreener payload, a GeckoTerminal hourly OHLCV page, and a DefiLlama summary.
- **Degradation tests are first-class** (WP-15), driven through the same headless-screen harness
  style as `tests/screens/test_talismans_screen.py`.
- **Widget tests** follow `tests/widgets/test_talismans_widgets.py` exactly: mount each widget in a
  tiny `App`, then call `update_data()` three ways — no args, all-`None`, full payload — and assert
  no raise plus expected DataTable/RichLog row counts.
- **Guardrails** (WP-18) are static-scan tests, not prose: banned hosts, banned claims, hardcoded
  parameters, signing imports.
- Estimated **~132 new tests**; the existing suite (796) must stay green.

| Test file | Owner | ~Tests |
|---|---|---|
| `tests/data/test_fwa_models.py` | WP-1 | 8 |
| `tests/analytics/test_fwa_ev.py` | WP-4 | 26 |
| `tests/analytics/test_fwa_signals.py` | WP-5 | 16 |
| `tests/data/test_fwa_client.py` | WP-6 | 18 |
| `tests/data/test_fwa_logs.py` | WP-7 | 14 |
| `tests/data/test_fwa_market.py` | WP-8 | 12 |
| `tests/data/test_fwa_cache.py` | WP-9 | 8 |
| `tests/widgets/test_fwa_widgets.py` | WP-10 + WP-11 | 14 |
| `tests/data/test_fwa_manager.py` | WP-12 | 10 |
| `tests/screens/test_fwa_screen.py` | WP-13 | 4 |
| `tests/data/test_fwa_refresh_budget.py` | WP-14 | 6 |
| `tests/data/test_fwa_degradation.py` | WP-15 | 10 |
| `tests/test_fwa_theme.py` | WP-16 (5) + WP-17 (2) | 7 |
| `tests/test_fwa_guardrails.py` | WP-18 | 10 |

---

## 16. Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **Log gateway is a genuine single point of failure.** Only two keyless `eth_getLogs` providers exist; publicnode refuses the method outright. | Medium | Activity feed, crown history, settlement mix, parameter drift, collection registry all die together | Two-endpoint Pool B with different pagination semantics (tenderly uncapped, drpc 10k pages). Persist last-good log-derived aggregates in `fwa_cache.py` and render them with an explicit `as of HH:MM` staleness label. Feed shows `logs unavailable`. All state-derived widgets keep working. Mandatory WP-15 test. |
| R2 | **Multicall3 ≤500 calls vs 3,867 positions and the 60 s tier.** ~17-18 `eth_call`s ≈ 3.3 s; a slow RPC could stretch a sweep past the next tick and starve the 15 s hot tiles. | Medium | Hot tiles go stale; 429 cascade | 500-call chunks. Single-flight lock: skip (never queue) an overlapping sweep. Fast tier never awaits the sweep. Atomic publish of a fully-built position list. WP-14 benchmarks the call count and asserts ≤ 20 `eth_call`s and no overlap. |
| R3 | **Multicall3 callData must have the `0x` prefix stripped**, or the node rejects the whole payload (`cannot unmarshal invalid hex string`). | Low (pre-solved) | Total enumeration failure | Copy `_encode_call3` from `talismans_client.py`, which already strips. WP-6 adds an explicit unit test asserting the encoded `aggregate3` payload contains no `0x` inside any bytes field. |
| R4 | **Mutable backing (`updateBacking`) invalidates cached positions**, and the pool mutates every few seconds (1,327 requests + 1,076 listings in a ~100-minute window). | High | Wrong odds, wrong price, wrong EV | Pin one `blockTag` per sweep. Never merge positions across blocks. Rebuild the whole list each sweep. Tail `BackingUpdated` to force invalidation. Re-assert all three aggregate invariants at the pinned block **as a runtime assertion, not just a test**; on mismatch set `odds_stale=True` and label the widget rather than publishing numbers. |
| R5 | **Free-list slot holes** — the first research attempt found 3,624 of 3,879 positions and produced a *plausible-looking* wrong `weightedBackingTotal` (off by exactly `255e36`). | High if naive | Ships a wrong price and wrong odds | Scan upward skipping zeros until `activeListingCount` non-zero ids collected, ~1.2× headroom. Assert the count. The aggregate-invariant check is the only detector — ship it as a runtime assertion. |
| R6 | **Emissions hard stop 2026-08-04T19:01:23Z** — ~9 days after the research date, i.e. **mid-build**. | Certain | A countdown widget goes stale / negative; a dashboard built around a dead event | **Ruled: the post-emissions state is the PRIMARY case.** It is built first, tested first (WP-15 scenario 1) and is what every acceptance criterion assumes. `emissions ended`, dim, no negative numbers, ever. The live countdown is the secondary/legacy path, tested second with a frozen clock *before* the stop. Emissions is a signal **row**, never a hero tile (PRD §8). Nothing on the screen is structurally dependent on emissions running. |
| R7 | **CoinGecko floor rate limits** — 38 collections take 203 s at ≥2.5 s spacing and still 429. | High | Coverage badge regresses below 22/38 | Background sweep only, never on the hot path; 15 min TTL; persist per-collection floors with timestamps; treat 429 as "keep previous value, mark stale"; OpenSea is opportunistic gap-fill only and any 401 is a silent miss. Never a hard dependency. |
| R8 | **Owner is a plain EOA** with no multisig or timelock and has already changed the crown tithe 500 → 100 bps mid-flight. | Medium | A hardcoded parameter silently misprices the UI | Every parameter read live; only 6 `ConfigSet` events exist ever, so one topic filter drives the whole parameter-drift widget. Guardrail test forbids hardcoded parameter literals. |
| R9 | **Interface drift** — 7 wave-2 agents coding against a contract that moves. | Medium | Rework across the whole layer | WP-1 is a hard gate: `FWA_DATA_KEYS` is importable and machine-asserted by WP-12 and WP-13. Any change after wave 1 requires an explicit contract amendment, not an ad-hoc edit. |
| R10 | **Shared-file merge conflicts** on `app.py` / `game_select.py` / `__main__.py` / `minimal.tcss`. | Medium | Broken app import, lost edits | Single-owner rule (§14). Registration is one late WP. No wave-2 agent may open those files. |
| R11 | **Stale endpoints copied from `ttt_client.py`** (llamarpc 521, keyed Ankr, Reservoir DNS gone). | Medium | A dead feed shipped on day one | Explicit banned-host list (§8.3) enforced by WP-18's static scan. Fixing `ttt_client.py` itself stays out of scope. |
| R12 | **WP-2/WP-3 need build-time network** to vendor ABIs and record fixtures. | Low | Whole plan blocked | They are the only network-dependent WPs and they run first, in parallel. Fallback: anyabi.xyz keyless mirror for ABIs; hand-construct fixtures from the raw hex already quoted in `docs/fwa_technical_findings.md` §4.2. |
| R13 | **A confident single EV number leaks into the UI** through a well-meant simplification. | Medium | The dashboard misleads someone into spending ETH | The band is structural: `PullEV` carries `lower`, `best` and coverage as *required* fields with no "point" field to render. WP-10's widget test asserts the coverage badge is present whenever an EV value is present. |
| R14 | **Art Blocks per-contract floors are semantically wrong** (one contract, many collections, different floors). | Certain | A plainly false number on screen | Suppress floors for `0x942BC2d3…` and `0xAB000000…`; render `multi-collection contract — floor not meaningful`. No pool-wide backing-vs-floor aggregate. |

---

## 17. Validation plan

| Gate | Check |
|---|---|
| After WP-1 | `from maxpane_dashboard.data.fwa_models import FWA_DATA_KEYS` works; all 10 models constructible; `pytest tests/data/test_fwa_models.py` green |
| After WP-2 | 8 ABI files parse as JSON arrays with the expected entry counts (core 172, rewards 112, vrf 71, token 87, hook 52, claim 31, whitelist 34, splitter 59); `topics.json` reproduces all 9 known topic0 hashes from findings §8; `fwa_enums.py` exposes both enums; nothing under `maxpane_dashboard/` imports `scripts/` |
| After WP-3 | Every fixture loads offline; `listings_56508.json` decodes to the 11 documented field values |
| After WP-4 | `acquisitionFee` bit-exact at blocks 25612655 **and** 25612701; harmonic mean, arithmetic mean and the gap **recomputed from the pinned distribution** and asserted against *that*, never against the 0.1247 / 0.5002 / 4.0× triple (superseded — see findings §13.7); EV lower bound ≤ best estimate always; crown seize = 1.10 × incumbent |
| After WP-6/7/8 | Each client returns typed models from fixtures with zero network calls (asserted by a transport that raises on use); fallback rotation exercised; `gasPrice` + `gas` present in quote params |
| After WP-12 | `fetch_and_compute()` returns exactly `FWA_DATA_KEYS`; each of the three pools can fail independently without an exception escaping; `degraded_sources` populated correctly |
| After WP-13 | Headless screen test mounts, refreshes, and dispatches every key; no widget raises on all-`None` |
| After WP-14 | One fast tick = 1-2 `eth_call`s; one sweep ≤ 20 `eth_call`s; no chunk exceeds 500 calls; overlapping sweeps are skipped not queued |
| After WP-15 | All seven WP-15 scenarios render their documented state, **post-emissions tested first**; zero crashes; zero wrong numbers; no negative countdown anywhere |
| After WP-16 | `fwa` Theme registered and present in `THEME_NAMES`; FWA screen renders without clipping; gold appears only on the crown card; `pytest tests/test_fwa_theme.py` green |
| After WP-17 | `python -m maxpane_dashboard --game fwa` boots; `--theme fwa` selects the theme; Tab cycles 9 games; game-select shows `[9]`; `q` closes the FWA manager cleanly |
| After WP-18/19 | Guardrails green; no color-only encoding; gold-on-dark crown tile and the red/green EV sign both pass contrast under every registered theme |
| **Final** | `pytest` fully green (796 existing + ~132 new); live run shows the EV band with a coverage badge, the live harmonic/arithmetic gap legible on the odds board, pool temperature telling the user which way the surcharge is flowing, and the emissions row reading `emissions ended` |

---

## 18. Decisions taken (user rulings, 2026-07-26)

All four previously-open questions are resolved. Nothing in this plan is pending approval.

| # | Question | Ruling | Where reflected |
|---|---|---|---|
| 1 | The two module splits (`fwa_client` → client/logs/market, `fwa_signals` → ev/signals) | **APPROVED, both.** PRD §6 amended to match, so plan and PRD now agree. This is the committed layout. | §8.1, §8.2 |
| 2 | `fwa` Theme, or CSS block only? | **FULL THEME** — against the plan's original recommendation. CSS block *plus* a registered `Theme` in `themes/__init__.py` *plus* `--theme fwa`, with tests. | §7 (`--theme` row now mandatory), §8.6, §14, §15, WP-16, WP-17, WP-19 |
| 3 | Emissions timing | **Post-emissions is the PRIMARY tested case.** The live countdown is secondary/legacy. No acceptance criterion assumes a live countdown. | §5.3, §12, §16 R6, §17, WP-5, WP-15 |
| 4 | Backfill the missing Talismans README rows? | **YES.** WP-21 brings the README to all nine dashboards. | WP-21 |

Two verifications folded in at the same time:

- `talismans_client.py` **does** already strip the `0x` prefix from Multicall3 callData (via
  `_strip0x` inside `_encode_call3`, line 149). Confirmed correct — WP-6 keeps its explicit assertion
  test so a future refactor cannot silently reintroduce findings §6.5's failure.
- Headline numbers re-checked after the Q2 scope growth: **21 WPs, 7 waves, peak concurrency 7,
  critical path unchanged**; new files ~64 → **~65** (`tests/test_fwa_theme.py`), modified files ~18 →
  **~20**, new tests ~125 → **~132** (WP-16 +5, WP-17 +2). WP-16 resized **S → M**.
