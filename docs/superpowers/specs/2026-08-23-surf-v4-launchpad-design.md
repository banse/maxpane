# Surf v4 Migration And Launchpad View Design

**Date:** 2026-08-23
**Status:** Approved in conversation; pending written-spec review
**Branch:** `feature/surf-v4-launchpad`

## 1. Scope

The `surf` dashboard reads a world that moved. Between 2026-08-16 and 2026-08-21
surfsurf.eth migrated all liquidity from Uniswap v3 to v4, retracted the "v4
hook" framing, shipped an IMD-denominated launchpad, and replaced the
BurnExecutor with a permissionless one. Five of surf's panels now report stale,
misleading, or structurally unanswerable state.

This change has two parts:

1. **repair** the default view against the post-migration contracts; and
2. **add one context view** (`g`, LAUNCHPAD) for the launchpad, on the body-swap
   precedent set by curator's `y` and `f`.

`app.py`, `__main__.py` and `GAMES` are untouched: this is an expansion of an
existing dashboard, not a ninth one, so there is no six-surface renumber.

This remains a read-only dashboard. It never signs, sends a transaction,
constructs state-changing calldata, or requires an API key. The permissionless
burn pipeline described in §7 is **displayed, never called**.

### Evidence base

Every claim below was read from chain on 2026-08-23 with keyless endpoints, or
decoded from the announcement channel. Load-bearing reads carry their citation
inline. The research probes live in the session scratchpad; nothing in this spec
rests on documentation alone, per CLAUDE.md's "read values live" rule.

## 2. What Moved

### 2.1 The v3 position is burned, not empty

`NonfungiblePositionManager.positions(1167726)` reverts `Invalid token ID` and
`ownerOf(1167726)` reverts `ERC721: owner query for nonexistent token`. The
position was withdrawn and burned in tx `0xa640874c…` at 2026-08-17 02:18 UTC.

The client currently turns both reverts into `None`, and `_lp_lines` renders
`None` as *unknown*. A completed, announced migration therefore reads as a
failed RPC call.

### 2.2 The real market is a hookless v4 pool

Seven minutes after the v3 burn, tx `0x038773e8…` (2026-08-17 02:25 UTC) minted a
full-range v4 position through the v4 PositionManager. The `ModifyLiquidity` log
names pool
`0xb07d640fd9e2eb9dc81b953c8e4fd006bdfeaf276010fb5418eb763ca15abfb3`
with `tickLower -887200`, `tickUpper 887200`, `liquidityDelta +157400387495567549793`.

That pool is native **ETH/IMD**, `fee = 10000` (1.00%), `tickSpacing 200`, and
**`hooks = 0x0`** — there is no hook on the IMD pool. Announce channel,
2026-08-16: *"We aren't creating a 'univ4 hook', we are creating a new agentic
p2p protocol."* The `HOOK` hero card hunts a hooked IMD pool that will never
exist.

The identification is confirmed independently: `LaunchpadHook.imdEthPoolId()`
returns exactly that pool id.

### 2.3 The market panel quotes a corpse

| Pool | Liquidity | 24h volume | Price |
|---|---|---|---|
| v4 `0xb07d640f…` (real) | $805,927 | $286,616 | $1.077 |
| v3 `0xD6A822D0…` (what surf reads) | $2,195 | $7,270 | $1.080 |

The v4 PoolManager holds 373,521 IMD; the v3 pool holds 1,466. Surf
under-reports its own subject's market by roughly 370x on liquidity and 40x on
volume.

### 2.4 Thirty-eight ETH/IMD v4 pools exist; one is real

`Initialize` logs on the v4 PoolManager filtered to `currency1 == IMD` return 38
pools since block 25,000,000. Thirty-seven were opened by third parties at fee
tiers from 5% to 98%, including six squatted within one pip of the real 1% tier
(`9997`, `9998`, `9999`, `10001`, `10002`). Creation is ongoing; the most recent
was 2026-08-22 17:38 UTC.

DexScreener returns one of these decoys (`0xa2e09ca3…`, $5,032 liquidity) in the
same response as the real pool, so *"pick the deepest pool"* is not a safe
selection rule.

### 2.5 A live launchpad the dashboard cannot see

Three new verified contracts:

| Contract | Address |
|---|---|
| LaunchpadFactory | `0x73d1ae084F04f793A5bbd6B623d74400C9Fc3f42` |
| LaunchpadHook | `0x51768F5dA32BA2008304cC81674da51aCb802888` |
| BurnExecutor (v2) | `0xe29386719C155B6847aD5a4E97C6674f10ffc750` |

Since 2026-08-19: **146 coins launched by 146 distinct creators**, **4,683
`CurveSwap` events by 673 distinct traders**, **3,299 IMD burned across 66
`ImdBurned` events**. Live reads: `imdToBurn = 15.06 IMD`,
`totalRealImd = 20,577.66 IMD`, `burnFeeBps = 50`, `creatorFeeBps = 50`
(`MAX_FEE_BPS = 500`), `totalCreatorEthOwed = 0.0749 ETH`,
`coinSupply = 1e27`, `initialPriceWad = 6695853418114`.

`SurfDevActivity` already shows these transactions — as unlabeled dim rows to an
unknown address. `0x51768F5d…` is the LaunchpadHook, and `burnAccruedImd()` is
the dev's single most frequent transaction.

### 2.6 The burn pipeline is permissionless and two-stage

Announce channel, 2026-08-20: *"updated the burnExecutor contract so anyone can
call it, would be nice if someone creates a bot for it."*

Stage 1 `LaunchpadHook.burnAccruedImd()` moves accrued IMD to the executor.
Stage 2 `BurnExecutor.bridgeToBaseBurnReceiver()` LayerZero-sends it to the Base
burn receiver `0xf9d7cbf5bef2f5c9ba93a70f31ddca6457716793`, dropping mainnet
supply. Both are callable by anyone.

## 3. Address And Constant Additions

`data/surf_addresses.py` gains, all EIP-55 checksummed and covered by the
existing recompute test:

```
LAUNCHPAD_HOOK        0x51768F5dA32BA2008304cC81674da51aCb802888
LAUNCHPAD_FACTORY     0x73d1ae084F04f793A5bbd6B623d74400C9Fc3f42
BURN_EXECUTOR_V2      0xe29386719C155B6847aD5a4E97C6674f10ffc750
POSITION_MANAGER_V4   0xbD216513d74C8cf14cf4747E6AaA6420FF64ee9e
BASE_BURN_RECEIVER    0xf9d7cbf5bEF2f5c9bA93a70F31dDCa6457716793
```

`BURN_EXECUTOR` is renamed `BURN_EXECUTOR_V1` and **kept**: it holds 0.664 IMD
of residue and appears in the historical burn ledger. Every new address gets a
`KNOWN_LABELS` entry — that is what stops the launchpad contracts rendering
through the address-poisoning fallback as anonymous truncated hex.

New topics, each vendored beside its preimage so the existing recompute test
covers them:

```
ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)
Launched(bytes32,address,address,string,string,uint256,uint256)
CurveSwap(bytes32,address,address,bool,uint256,uint256,uint256,uint256,uint256)
ImdBurned(uint256)
CreatorFeeAccrued(address,uint256)
```

New selectors: `extsload(bytes32)`, `coinCount()`, `allCoins(uint256)`,
`poolIdOf(address)`, `imdEthPoolId()`, `imdToBurn()`, `totalRealImd()`,
`burnFeeBps()`, `creatorFeeBps()`, `totalCreatorEthOwed()`,
`spotPriceEthPerCoin(bytes32)`, `getCurve(bytes32)`, `tokenBalance()`,
`minBridgeAmount()`, `previewBridge()`, `balanceOf(address)`.

### The pool id is read, never hardcoded

`POOL_V4_ID` is vendored **only as a cross-check**. The live value comes from
`LaunchpadHook.imdEthPoolId()` on every chain read. A mismatch logs a warning and
the live value wins.

This is CLAUDE.md's "read values live; never hardcode a documented one" applied
where it has teeth: 37 decoy pools make a stale constant actively dangerous, and
the dev has already moved his liquidity once. If the hook read fails, the
vendored id is the last-good fallback and the panel says so.

## 4. Reading v4 State Keylessly

v4 has no `slot0()`. Pool state is read through
`PoolManager.extsload(bytes32)` against the mapping at slot 6:

```
base   = keccak256(poolId ‖ uint256(6))
base+0 = sqrtPriceX96 (bits 0-159) | tick (160-183) | protocolFee (184-207) | lpFee (208-231)
base+3 = liquidity
```

Verified on `ethereum-rpc.publicnode.com`: `sqrtPriceX96 = 3757351088368496721754945570926`,
`tick = 77186`, `lpFee = 10000`, `liquidity = 7393092836965392068604`, giving
0.00044463 ETH per IMD. Cross-checked against DexScreener's $1.077 at
ETH $2,426.85 — agreement within 0.2%.

**Price therefore has two independent keyless sources.** The market panel uses
extsload for price and DexScreener for volume. When the two prices disagree by
more than **2%** of the extsload price, the panel renders the extsload value and
marks the row degraded rather than silently preferring one source; the observed
agreement today is 0.2%, so 2% is roughly a ten-fold margin over normal drift.
Neither source is trusted to identify *which* pool is real; that comes from the
hook.

`publicnode` batches state calls and is the correct pool for `extsload`;
`eth_getLogs` continues to go to tenderly/drpc, per the standing split.

## 5. Tiering And Fetch Budget

Launchpad and decoy-pool reads live on their own long tier with their own
last-good slot and their own `as of HH:MM`, deliberately on a slower clock than
the title bar's. The sweep is **spawned, never awaited**, on the
`_spawn_crosscheck` precedent, so first paint cannot block on it. A tripwire test
asserts the first payload is not behind the launchpad read and fails by timing
out.

**The coin table is ranked from logs, not from per-coin calls.** One `getLogs`
over `CurveSwap` yields per-coin swap counts and volumes for all 146 coins with
zero per-coin reads. Curve state is then read only for the rows actually
rendered (~15). Cost is one log scan plus one multicall whether the launchpad
holds 146 coins or 1,460 — the same "budget to candidates, never the full
population" discipline as the curator sweep.

A failed launchpad sweep folds into the degraded group **only when there is
nothing to serve**; otherwise a stale `launchpad_as_of_hhmm` is the signal.

## 6. Default View Repairs

### 6.1 Hero row: POOL · LP · BURN · SUPPLY

`HOOK` becomes **POOL**: the live pool's venue and fee (`v4 · 1%`), its
liquidity, and a decoy count (`1 of 38 pools`). `GATE` leaves the hero and
survives as a detector row; its slot becomes **BURN** (§7). `LP` and `SUPPLY`
keep their positions.

### 6.2 The LP card: revert is not failure

A revert is **not** a failed read. The contract answered, and the answer was
"this position no longer exists." Collapsing both into `None` is exactly the
failure CLAUDE.md describes: a row that renders identically for "we looked and
there was nothing" and "we could not look."

The client therefore distinguishes:

* **revert with reason** → a representable state. v3 position gone renders
  `migrated 08-17`, never unknown.
* **transport failure / no answer** → `None` → unknown, as today.

The card's live content is the v4 position: ops holds exactly one NFT on the v4
PositionManager (`balanceOf` = 1, confirmed live), and its composition and
owner-sanity flag render as the v3 card's did.

### 6.3 Market panel

Repointed at the v4 pair. The v3 pool is retained only as a dim `legacy pool`
line, so the migration stays legible rather than vanishing.

### 6.4 Dev activity labelling

`LAUNCHPAD_HOOK`, `LAUNCHPAD_FACTORY` and `BURN_EXECUTOR_V2` enter
`KNOWN_LABELS`, and `DEV_TX_KINDS` grows the launchpad selectors so
`burnAccruedImd` renders as a named kind instead of `other`.

> **Measurement debt.** `SurfDevActivity`'s cells are sized to the exact
> vocabularies its producer emits; that sizing is what took surf 152 -> 142
> columns. A kind string longer than `fwa claim` (9 cols) widens the kind cell
> and may push surf past FWA's 143. **Re-measure; do not assume.** If a longer
> name would move the app-wide constant, shorten the name — `burn` over
> `burn accrued` — rather than moving `FULL_LAYOUT_COLUMNS`.

## 7. The BURN Hero Card And Pipeline

The card shows the two-stage pipeline's state: IMD accrued at the hook, IMD
staged at the executor, and observed cumulative burn. When accrued IMD exceeds
`minBridgeAmount()`, the card says the pipeline is **ready** — meaning anyone may
fire it.

MaxPane displays this and nothing more. It builds no calldata, quotes no gas for
the purpose of sending, and offers no action. The read-only guarantee is
unchanged; a permissionless function is simply public state worth rendering.

`imdToBurn` and `tokenBalance` are quantities with a **representable zero**:
`0` means "we looked and nothing has accrued", and it must render distinctly from
`None`, which means the read failed. Observed cumulative burn keeps the existing
`observed` wording — it covers this install's window and nothing before it.

## 8. The `g` LAUNCHPAD View

`g` swaps the dashboard body for the launchpad; the hero row stays in place.
`esc` backs out, one-way. This matches curator's `y` and `f` exactly.

```
LAUNCHPAD                            146 coins · 673 traders · as of 01:14
 TICKER  NAME                    CREATOR    AGE    ETH      Δ1h   SWAPS  IMD
 ICE     Initial Compute Event   0x28a0b8…   2d   .00712   +34%      88  142.1
 GCPU    Genesis CPU             0x28a0b8…   2d   .00690    +9%      41   38.4
 DAOs    Decentralized Agentic   0xef1d88…   3d   .00670     --      12    9.2
─────────────────────────────────────────────────────────────────────────────
 CURVE FLOW                        │ BURN PIPELINE
 4,683 swaps · 673 traders         │ accrued    15.06 IMD  ▸ ready
 ~1,170/day · buy/sell 63/37       │ executor    0.00 IMD
 creator fees owed  0.0749 ETH     │ burned     3,299 IMD · 66 events
```

Rows are ranked by recent curve volume — the market-scanner framing. A coin with
no swaps in the window renders `--` for `Δ1h`, not `0%`.

### Ticker and name are attacker-controlled

`LaunchpadFactory.launch(string,string)` is permissionless and unpriced beyond
gas: anyone can launch a coin named `[/x]`. This is the first surf panel whose
text is chosen by a hostile party rather than merely quoted from the announce
channel.

Every ticker, name and creator label passes `safe_markup` **after** newline
flattening and **after** truncation, so a cut can never bisect an escape
sequence. Each column gets its own composited forbidden-markup test.

## 9. Signals Rail

Nine detectors. `NEW POST`, `GATE OPEN`, `NEW DEPLOY`, `BRIDGE STAGE` and `BURN`
keep their current semantics; `BURN`'s executor watch is repointed at
`BURN_EXECUTOR_V2` while still recognising V1 for history.

`LP MIGRATION` is spent — it fired, and the migration is finished. It becomes
**`LP MOVE`**, repointed at the v4 position: does the ops wallet add to or remove
from pool `0xb07d640f…`.

Three are new:

* **`DECOY POOL`** — a new spoof ETH/IMD v4 pool was initialised. One `getLogs`
  on a topic already vendored.
* **`BURN READY`** — accrued IMD has crossed `minBridgeAmount` and the pipeline
  is callable by anyone.
* **`HOT COIN`** — a launchpad coin crossed a curve-volume threshold in the last
  hour.

### Quiet-collapse

FIRED and WATCH rows always render. Consecutive **OK** rows fold into a single
dim `· N quiet` line.

**Unknown and dead rows never fold.** This is the entire point of the mechanism,
and it is the rule curator's rail shipped wrong: FARM said `-- unknown` off a
dead group while HOUR SAVED and WHALE, folded from that same dead group, said
`none yet` — confident and green through an outage. The fold counter counts OK
rows only; a degraded detector stays on screen carrying its own state word.

### The HOT COIN threshold is derived, not invented

At ~1,170 swaps/day across ~146 coins, a naive "any swap" threshold lights the
row permanently, which is the trap `signals.py` already documents for
`‹ widen`: a marker that is always on means nothing.

The rule is therefore **relative to the hour's own distribution**, not a pinned
constant: a coin is HOT when its last-hour swap count is both

* at least **3x the median** last-hour swap count across coins with any activity
  in that hour, and
* at least **5 swaps** — a floor that stops a quiet hour (median 1) promoting a
  coin on 3 swaps.

When fewer than 5 coins traded in the hour there is no meaningful median and the
detector reports OK, not a fire. The rule is unit-tested against a fixture whose
cadence matches production, including the quiet-hour and empty-hour cases.

## 10. Layout And Width

Surf currently measures **142**, one column under FWA's 143, and the app-wide
`FULL_LAYOUT_COLUMNS` is FWA's. The default-view repairs must not move surf past
143; §6.4 names the one change likely to try.

The `g` body is full-width and the COINS table is expected to bind it. It gets
its own width sweep, **started deliberately away from the pin** so a sweep cannot
agree with the constant by construction — the shape of
`test_the_analysis_binding_panel_is_the_operators_table`. A binding-panel test
names the panel, so this document is not the pin.

If the `g` body needs more than 143, the fix is a narrower tier that sheds
columns and advertises `‹ widen`, **not** raising the app-wide constant.

Status hints grow `g launchpad`. The existing hint line was already cut down to
fit; the new label must be measured into it rather than appended on faith.

## 11. Verification

* No test touches the network: the transport that raises on use stays, and every
  new payload — v4 extsload words, `Initialize` decoy logs, `Launched`,
  `CurveSwap`, `ImdBurned`, launchpad reads — becomes a committed fixture under
  `tests/fixtures/`.
* Address checksums and every new topic and selector are recomputed from their
  vendored preimages by the existing tests.
* Composited-output assertions (`_compositor.render_strips()`) for the coin
  table, the quiet-collapse fold, and the repaired hero cards.
* A forbidden-markup test per attacker-controlled column in the coin table.
* A tripwire that first paint is not behind the launchpad sweep, failing by
  timeout.
* Distinctness tests for the three-state values: revert vs transport failure on
  the LP card; `0` vs `None` on the burn quantities; OK vs unknown in the fold.
* Concurrency- and decoder-shaped tests are mutation-proven: mutate, watch it go
  red, restore.
* Widget templates are checked for the same defects and for drift in either
  direction, per the standing templates hazard.

## 12. Out Of Scope

* **The announce feed renders a null action's text as literal `None`**
  (2026-08-16 20:02 UTC, an on-chain action whose calldata was not UTF-8). A real
  display defect, filed separately rather than folded in here.
* **The NFT-as-compute-license reframing.** The announce channel now describes
  IDMD as a daemon licence — *"one NFT per daemon running for its work to be
  accepted/valid"* (2026-08-21). Recasting the IDENTITY.MD panel's holders as
  claimed daemon slots is a fifth repair and is deferred.
* `imd.fun` as a data source. It is a website, not a keyless chain read, and the
  dashboard's sources stay on-chain.
* The p2p protocol itself, which is pre-audit and has no deployed surface to
  read.
* Any change to `app.py`, `__main__.py`, `GAMES`, or the dashboard ordering.
