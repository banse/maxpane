# Sybil / fan-out detection for THE LIST — research & measured analysis

Research for a MaxPane feature: strengthen the curator (`THE LIST`) wallet view so a reader can
see which contributors are one operator running many wallets, and ship the detection logic as a
**standalone, keyless, maxpane-independent** module others can reuse.

Prompted by surfsurf.eth (Adam, `@surfcoderepeat`) on 2026-08-17: *"Would be cool if someone does
some analysis, removes clear sybils … Segment them on the per hour event and multiplier … Also an
800 eth deposit for example can do whale lists."* Linked tx
`0x3b53aa1dabad44d955a12bbd72a50affafb41274edfa9bd42f370ac5c9623d13` is a **786 ETH** `deposit()`
in hour 6 — his own "whale" example.

All numbers verified onchain 2026-08-17. Raw datasets preserved under
`docs/curator_sybil_data/` (see the manifest at the end); every measurement here is reproducible
from them, keyless.

---

## 0. The one-paragraph answer

The contract's own doc comment says it: the sqrt points curve **actively rewards splitting a
bankroll across wallets**, and it delegates sybil-clustering to off-chain analysis of the event
data. Splitting a stake `W` across `k` wallets turns `sqrt(W)` points into `sqrt(k)·sqrt(W)` — a
`sqrt(k)` bonus that is unbounded, and since every wei is refunded in the same transaction the
only cost is gas (dollars per wallet). So the population is heavily farmed **by construction, not
by accident**, and the honest question is not "who cheated" (unknowable) but "which points are
one operator's fan-out." Measured on the live game: a conservative, multi-signal floor of
**~6,300 wallets (≈40% of contributors) holding ≈43% of all points** is farm-operated, dominated
by three operators. The dashboard already ships a v1 fan-out heuristic; this document measures how
well it does (≈50% of points flagged, but for partly wrong reasons) and specifies a stronger,
still-keyless, still-pattern-language successor.

---

## 1. What the contract does to invite this

From `docs/curator_game_mechanics.md` (verified source, immutable):

- **Points are `floor(sqrt(weight_wei)) · 1000 / 1e9`** — concave. 1 ETH-weight → 1000 pts, 4 →
  2000, 100 → 10 000. One wallet with weight `W` scores `sqrt(W)`; `k` wallets sharing it score
  `k·sqrt(W/k) = sqrt(k)·sqrt(W)`. **Doubling wallets is +41% points forever; 100 wallets is 10×.**
- **All ETH is refunded in-tx** (the deposit transaction refunds every wei). Weight is "high-water
  mark held in a real EOA at that instant"; the standing cost of a wallet is ~2 transactions of
  gas. There is no capital lock — only a per-wallet gas cost of dollars.
- **Early-bird multiplier decays 2.0× → 1.0× over the 24 h grace period**, per second. A rational
  farm deploys *early and fast* to bank the high multiplier — which **concentrates farm activity in
  the first hours and tightens every temporal signal.** (Measured: `earlyMultiplierBps` 19 975 at
  launch → ~10 116 by hour 23.)
- **EOA-only** (`tx.origin == msg.sender`, `code.length == 0`): no contract can deposit, so there
  are no disperse.app-style *deposit* fan-outs inside the event set (every deposit is its own EOA's
  own tx — verified: 0 txs emit `Deposited` for >1 contributor). Disperse still appears one hop
  *upstream*, in the funding.

This is the opposite of a linear-in-capital drop (EigenLayer set *no floor* precisely so splitting
is pointless). THE LIST's curve subsidizes splitting, so detection has to carry the whole load.

---

## 2. Live population shape (snapshot 2026-08-17, hour 23–24, not settled)

Full event sweep, blocks 25769870–25776962 (`deposits.json.gz`, 22 319 `Deposited`;
`first_deposits.json.gz`, 15 576 `FirstDeposit`). Reconciles with `stats()` to within the txs that
landed during the ~80 s sweep. **Total points at snapshot: 26 585 740.** Points recomputed
wei-exact (`isqrt(weight)·1000//1e9`) and matched against `pointsOf()` for sampled wallets.

- **Credit** (final high-water): min 0.05 / median **0.45** / p90 **14.0** / p99 98.8 / max 1000.0
  (the cap; that wallet sent 4040 ETH in one tx, credited 1000). The median and p90 are *literally
  the two biggest farm amounts* — the farms set the population's quantiles.
- **Weight**: median 0.82 / p90 20.95 / max 1363 ETH-weight. **Points**: median 907 / p90 4 577 /
  max 36 924.
- **14 064 single-deposit wallets (90.3%)** vs 1 512 laddered (9.7%); max 120 deposits from one
  wallet. 1 468 wallets (9.4%) sit at exactly the 0.05 minimum.
- **Join spikes**: hours 3–5 (the 0.45 / 14 / 10 ETH farms) and 19–20 (randomized batches).
- Game **survived grace**: hour 24 arrived safe (>5 ETH), 15 638 contributors, 114 487 ETH routed.

---

## 3. How the current v1 rule does (and where it is wrong)

The shipped heuristic (`analytics/curator_signals.find_clusters`): **≥3 single-deposit wallets,
byte-identical `amount_wei`, chained gap ≤32 blocks.** Measured on the live set:

> **139 clusters · 7 119 wallets · 13 257 942 points = 49.87% of all points.**

Close to the true floor by *total*, but its composition is off in two ways that matter for a
per-wallet claim on the wallet view:

**It over-includes minimum-deposit crowds.** ≈1 460 of those wallets are the 0.05-ETH group, which
is provably *mixed* — the funding evidence (§5) shows some 0.05 clusters are 6/9 same-operator and
some are organic strangers who all happened to send the minimum. "Byte-identical" is doing no work
when the amount is the floor everyone pays.

**It misses randomized-amount farms entirely.** The strongest single-operator signature in the
data is a batch of exactly **100 wallets registered in consecutive `FirstDeposit` indices within 2
blocks, amounts jittered 0.0989–0.0995 ETH** — no two identical, so a byte-identical rule sees
nothing, yet P(100 strangers doing that) ≈ 0. Twelve such quantized batches (sizes 100/51/50)
exist. It also misses **window-separated waves** of the same operator: the 2.067-ETH operator ran
two waves (hours 13–14 and 18–20, zero member overlap) tied together only by the identical odd
amount and an identical 0.001 gwei priority fee.

Parameter sweep (`same_amount_clusters.json`) confirms the window is the *least* important knob —
32→∞ blocks moves flagged wallets 7 119 → 8 828; amount-roundness and corroborating fingerprints
dominate. min_size barely matters (the mass sits in a few giant clusters).

---

## 4. The three operators the data actually contains (`cluster_economics.json`)

The sqrt subsidy each farm captured — points earned vs. the same ETH in one wallet — is the
"sybil multiplier":

| shape | wallets | ETH routed | points | share | sqrt subsidy |
|---|---|---|---|---|---|
| 0.45 ETH, h3–4 | 1 995 | 897.8 | 1 811 322 | 6.81% | **44.6×** |
| 14.0 ETH, h4–13 | 997 | 13 958 | 4 755 046 | 17.89% | 31.6× |
| 10.0 ETH, h5 | 769 | 7 690 | 3 245 928 | 12.21% | 27.7× |
| 1.2 ETH, h1 | 300 | 360 | 454 865 | 1.71% | 17.3× |
| 2.067 ETH, h13–14 + h18–20 | 324 | 669.7 | 524 403 | 1.97% | ~14× |
| 5 randomized idx-batches, h19–20 | 500 | 47.7 | 165 599 | 0.62% | 10× each |
| 171.99 ETH ring, h20–21 | 10 | 1 719.9 | 139 218 | 0.52% | 3.2× |

16 audited clusters total **6 303 wallets (40.5%), 25 430 ETH (22.3% of volume), 11 498 903 points
= 43.3% of all points** — the conservative farm floor. The `w∞/min3` envelope (69.3% of points) is
the noisy upper bound.

**Operator linkage** (the finding that makes this cluster-level, not wallet-level): the 0.45 and
10.0 farms share **gas limit 91 600 and priority fee 0.1 gwei** — one operator, 3 085 wallets,
8 620 ETH. Cadence fingerprints: the 0.45 farm deposits in bursts of *exactly* 20 or 30 txs/block;
the 14.0 farm is a metronome — exactly 1 tx every ~2 blocks for 8.5 hours (a dripper that the
32-block window still catches because it drips faster than the window).

---

## 5. Which signals discriminate on this population (measured, not theorized)

220 deposit txs fetched (`tx_fingerprints.json`, 160 cluster members + 60 controls) and 221
funding lookups (`funding.json`, Blockscout, bounded). Results:

**DISCRIMINATING**

1. **Funder-is-a-fellow-cluster-member (peel chain).** In every fully-resolved farm sample,
   **10/10 members were funded by another member of the same cluster** — serial chains where the
   funder itself deposited one block earlier. Controls: 0/47 funders belong to any suspect cluster
   (35/47 are contributors — people funding from their own main wallet, which is normal and *not*
   the signal). This is the single strongest signal. **Needs one per-address history call each.**
   Note the inversion of ChainCred's negative result (§7): *shared* funder is weak here (these
   farms use chains, not hubs — distance-2 found almost nothing); *funder ∈ same behavioral
   cluster* is near-perfect.
2. **Cluster-uniform priority-fee + gas-limit.** Each true farm collapses to **one** priority-fee
   value and **one** gas limit; 60 controls show **27** distinct priority fees and **15** gas
   limits. The *uniformity* is the signal, not the value (odd watermarks like 11 500 001 wei or
   0.001 gwei tie waves together; but 0.035 gwei is also a common honest default). **Free from
   `eth_getTransactionByHash`.**
3. **Consecutive `FirstDeposit`-index runs with near-identical (±10%) amounts, ≤2-block spacing.**
   Catches the jitter-amount batches a byte-identical rule cannot. 281 runs ≥3 (byte-identical
   first amounts) / 3 779 wallets; 499 runs / 7 369 wallets at ±10%. Biggest: **180 consecutive
   indices in 7 blocks, all 0.45 ETH.** No plausible organic mechanism. **Logs only.**
4. **Batch cadence quantization** — exactly 20/30 txs per block, or a metronomic 1-per-N-block
   drip. **Logs only.**
5. **Byte-identical *non-round* amounts** (2.067, 171.99, 0.063…) — tiny clusters, essentially no
   false positives, and they link window-separated waves. **Logs only.**

**NOISY (never convict on these alone)**

- Byte-identical *round/minimum* amounts alone — the 0.05 crowd is provably mixed.
- Fresh nonce (≤2) — 55% of *controls* are also nonce-0; and the biggest-capital rings (171.99,
  2.067-wave-1) use **aged** wallets (nonces to 3 592). Freshness discounts, never convicts.
- Funder-is-any-contributor — true for 74% of controls.
- Tx type — 97% of everyone is type-2.
- **Credit-threshold whale lists (Adam's "800 ETH+")** — only **2 wallets** qualify (1 806 ETH,
  0.25% of points), because real whale capital is *split*: 171.99×10, 14×997, 10×769. A whale
  *segment* has to be defined on the operator, not the single send.

**Segments Adam asked for** (`whales_segments.json`): index 1–1000 ("early CT") = 6.4% of wallets,
**7.61% of points**; hours 22–23 (last grace) = 742 wallets, **2.39% of points** (FOMO at ≤1.06×,
not multiplier chasers).

---

## 6. What is feasible keyless, in tiers (this is the module's spine)

Endpoints (all keyless, all verified in this research): logs via
`gateway.tenderly.co/public/mainnet` (800-block chunks, no splits needed); state /
`eth_getTransactionByHash` via `ethereum-rpc.publicnode.com` (batches; **requires a `User-Agent`
header** or 403); per-address history via Blockscout REST `eth.blockscout.com/api/v2/…` (keyless,
50/page keyset pagination; **stalls python-urllib, answers curl/httpx in <1 s**; ~3 req/s clean, 0
× 429). `eth.drpc.org` returns HTTP 500 on batch `getTransactionByHash` and a routing-error *string*
on some log calls — classify failover on message text, per the repo's existing rule.

| tier | extra network | signals unlocked |
|---|---|---|
| **A — logs only** | one `eth_getLogs` sweep (already done every refresh) | temporal bursts, block-adjacency runs, identical & near-identical amounts, ladder shapes, `≈W/k` optimal-split signature, index-run runs, cadence quantization, window-separated same-amount waves |
| **B — + `getTransactionByHash`** | ~1 call per deposit tx, batched (minutes once, cached) | nonce-at-deposit, priority-fee / max-fee / gas-limit uniformity classes, tx type |
| **C — + Blockscout per-address** | ~1–2 calls per contributor, background sweep, cached forever | **first-funder graph** (peel chains, funder∈cluster), fan-out trees, lifecycle (first-tx date, tx count), CEX-funder labeling |

Tier A is free and already in the fast path. Tier B is a bounded one-shot per new deposit tx. Tier
C is a **slow background enrichment sweep** (measured precedent: the existing curator crosscheck
runs detached because a full Blockscout read is ~200 s; awaiting it in-cycle blanks the dashboard).
Impractical keyless: whole-chain graph mining, `trace_`/`debug_`, curated Nansen-grade labels,
supervised ML — all out of proportion for a TUI, and Tier A+B+C reaches most of the value.

---

## 7. Prior art distilled (web practice + local ChainCred)

Full survey in the research datasets; the load-bearing conclusions:

- **Every major hunt** (Hop 2022, Optimism 2022, Arbitrum/Nansen 2023, LayerZero/Chaos Labs 2024,
  Starknet 2024) converged on the same stack: **funding-graph clustering** as the linking layer +
  **temporal/behavioral near-duplication** as the confirmation layer, and *no production system
  trusts either alone.* Best published supervised result (arXiv 2505.09313, LightGBM on 193 701
  addrs): F1 0.930 — and its **top features are lifecycle timestamps** ("born together, act
  together"), above topology, above amounts.
- **False positives are the failure mode, not a rounding error.** Chaos Labs cut its own LayerZero
  flag list from 2M → 803k to control FPs and still called it "not definitive." Hop rejected any
  report with "a non-negligible chance of eliminating legitimate users." Recurring honest classes
  wrongly flagged: CEX-hot-wallet funding, disperse.app payroll, OTC between friends, one human
  with a few wallets. Every serious process set a **minimum cluster size (Hop ≥10, LayerZero ≥20)**
  to keep small honest multi-wallet users out of scope.
- **Local ChainCred (`/Library/Vibes/chaincred`) already measured the key negative result** for us:
  against a labeled ~54-sybil benchmark + 500-wallet population, **no per-wallet signal separated
  sybils from power users** (funder fan-out: 42% of sybils vs 32% of ordinary wallets share a
  distributor-range funder — statistically identical, precision stuck at the ~9% base rate; as a
  penalty it wrongly hit 34% of honest wallets). The surviving design principles, adopted here:
  **compound conditions (2–3 simultaneous triggers) beat single thresholds**; **multiplicative
  confidence**, not binary flags; **graduated, time-decaying** freshness penalties; **discount, not
  ban** (appealable). Directly reusable assets: the 12 CEX hot-wallet addresses
  (`packages/common/src/constants/selectors.ts`), the gwei-rounding gas-fingerprint primitive, and
  the **benchmark-regression-gate test pattern** (a labeled list + a median-gap ceiling that made
  heuristic drift visible). What does *not* transfer: sleep-dip and any lifetime-history signal (our
  wallets have 1–5 txs), cross-chain mirroring, protocol-diversity — all meaningless for one
  contract in a 24 h window.

The synthesis across all of it: **score clusters, not wallets; a cluster is real only when ≥2
independent signal families agree; minimum size ≥5; render reasons, never verdicts; never persist a
verdict a later crawl can't revise.**

---

## 8. The pattern-language constraint (must be resolved before building)

The curator dashboard was deliberately built to **never accuse**. Three tests enforce a
forbidden-word list — `test_the_output_carries_no_accusatory_vocabulary` scans the *entire*
`analytics/curator_signals.py` **source** for `sybil, cheat, fraud, attack, abuse, farmer`; two
widget tests scan the composited `CuratorSignals` and `CuratorClusters` renders for
`sybil/cheat/fraud/attack` (+ `wash/abuse`). The on-screen vocabulary is "**FAN-OUT PATTERNS**",
"linked wallets", `⚑`. Rationale (sound): *one person spreading a deposit and nine people copying a
trade produce identical logs* — the chain cannot prove intent.

The user now explicitly asks for "**sybil** detection." These reconcile cleanly, and the split is
the crux of the design:

- The **standalone library** is a general-purpose sybil/cluster-analysis tool — it may use the word
  "sybil" freely in its own name, API, and docs. It lives outside every scanned surface.
- The **maxpane dashboard** keeps pattern-language on screen (fan-out / linked / `⚑`) unless the
  user chooses to relax it. The forbidden-word tests stay green because the library is a separate
  distribution the analytics-source scan never reads.

This is the primary decision to confirm with the user (see the proposal that accompanies this doc).

---

## 9. Dataset manifest (`docs/curator_sybil_data/`)

Reproducible, keyless, captured 2026-08-17 hour 23–24 (game not settled):

- `deposits.json.gz` — 22 319 decoded `Deposited` rows (the whole event history to snapshot)
- `first_deposits.json.gz` — 15 576 `FirstDeposit` rows (1-based enumeration of the list)
- `population.json` — credit/weight/points quantiles, single-vs-laddered, per-hour joins/volume
- `same_amount_clusters.json` — v1 rule result + the min_size×window grid + 37 staggered groups
- `index_runs.json` — consecutive-index runs (byte-identical and ±10%)
- `cluster_economics.json` — the 16 audited operators with points/share/subsidy
- `tx_fingerprints.json` — 220 deposit-tx nonce/gas/type fingerprints (suspects + controls)
- `funding.json` — 221 Blockscout funder lookups (peel-chain evidence)
- `suspects.json` — the 16 clusters' sampled members + 60 controls
- `whales_segments.json` — top-20 by credit, index-1000 and last-grace segments
- `sweep_meta.json` — block range, reconciliation vs `stats()`

Per the CLAUDE.md live-read rule, these are **snapshots for calibration**, not values to hardcode;
the module reads the chain live and the labeled subset here is what a regression gate measures
against.
