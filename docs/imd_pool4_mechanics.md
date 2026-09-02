# IMD pool4 — "protocol owned inference" (CappedBurnHook + sIMD + RewardDripper)

Research for a fourth `surf` **view**, compiled 2026-09-01. Not a ninth dashboard — the curator
`y`/`f` and surf `l` precedent: one more body swap on `SurfScreen`, hero left mounted.

**Status at time of writing: pool4 is NOT live on mainnet.** It has been running on **Sepolia**
through three successive launches (2026-08-29, 08-30, 09-01), the third of which was deployed
**~01:30 before this document** and is still being exercised. The dev's own announce post
(2026-08-29 21:41 UTC, tx `0x5afe9a4bd8…`) sets the intent:

**UPDATE 2026-09-01 23:10 UTC — the launch is POSTPONED by the dev, in his own words.** Announce
self-post #29, tx `0x5aaf54604396`:

> "today a new model from claude came out so i am taking a bit of time to test with the latest
> model. Our hook rebalances liquidity which is one of the most dangerous things you can do on a
> pool"

Two things follow. The `imd.fun` 24-hour countdown lapsed without a deployment and there is now no
stated date — so the dashboard's **not-yet-discovered path stays the one that runs**, and it stays
that way indefinitely rather than for hours. And the dev has named the hazard himself: the hook
**rebalances liquidity**, which is what `rebalance()`, `backstop()` and `refTick()` do, and it is
the single most consequential behaviour on this pool. THE RATCHET's `pool4_backstop_centred` is the
panel watching exactly the thing its author considers most dangerous.

Still no `0x2840`-shaped address anywhere in the channel's complete history, so discovery correctly
yields `not-discovered`.

> "Over the next 48 hours i will remove around 20% of the current LP and readd it on a new
> imd/eth pool with a new hook i've been working on, hopefully if all goes well will move all lp
> to this new pool over the coming weeks"

and the follow-up reply (2026-08-29 22:14, tx `0xca32b85a66…`) fixes one integration point:

> "yep, the new hook will keep feeding the same burnExecutor"

**Every number below is a live read or a decoded log, never a documented one.** The hook is
**unverified source** on Sepolia; its interface was recovered from `PUSH4` selectors in the
deployed bytecode + Openchain, its events by keccak pre-image search, and its semantics by
decoding complete transaction log sets. Inferences that the chain does not prove outright are
labelled **(inferred)**.

---

## Cast of addresses

### Sepolia — launch 3, the current one (2026-09-01 02:03–02:06 UTC)

| Label | Address | What it is |
|---|---|---|
| test IMD | `0xB37d54bC1F1d9271fc57D7E03192976baA39Cc82` | `IdentityMD Test` ERC-20, 1,000,000,000 supply, minted to the dev |
| **hook** | `0xa1B997A9861B2b8aC17B4c615089cCC2a5416840` | the pool's sole LP. Unverified. Low 14 bits `0x2840` — see the flag note |
| hook deployer | `0x24bB15691f4e77004D0C72bDC90eaA4279e6Ced6` | CREATE2's the hook to its mined address (`0x3e00b72e`) |
| **StakedIMD** | `0x1600E14C663679c98B35B61e239F20792BB317cc` | ERC-4626 vault, `sIMD`. **Verified source** |
| **RewardDripper** | `0x4dBE172254033aAC3a3374Fb10b422605B0B449B` | rate-limits the 10% reward share into the vault. **Verified source** |
| PoolSwapTest | `0x374283De53d7596387f86eA8DA25e92C11f5BC4b` | the test router the dev swaps through (`0x2229d0b4`) |
| v4 PoolManager | `0xE03A1074c86CFeDd5C142C4F04F1a1536e203543` | Sepolia canonical |
| burn sink | `0x000000000000000000000000000000000000dEaD` | `burnSink()` |

Pool id `0xb789dff37d37…` (from the `Swap` topic), key = (ETH native / test IMD, fee 10000,
tickSpacing 60, hooks = the hook).

### Sepolia — the two earlier launches (kept for the layer-by-layer comparison)

| # | when | token | hook | `rewardsRecipient` | `capFloor` |
|---|---|---|---|---|---|
| 1 | 08-29 15:10 | `0x6ca2626F1f…` | `0x1230007b24ADeC383B26CEaF3739E6D306016840` | `0x…beEF` (stub) | 50,000,000 |
| 2 | 08-30 02:31 | `0x05D0CA857D…` | `0xCA0612FF8bC6298Dc8baFB7d40ACBb0d3eEaE840` | `0x…beEF` (stub) | 50,000,000 |
| 3 | 09-01 02:03 | `0xB37d54bC1F…` | `0xa1B997A9861B2b8aC17B4c615089cCC2a5416840` | **RewardDripper** | 250,000,000 |

This is exactly the "three launches, each adding a layer" the reveal describes: the fee split,
then the retained protocol cut, then the staking vault wired to a real recipient.

### Mainnet — what exists today

| Label | Address | Note |
|---|---|---|
| IMD | `0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7` | `BridgedFP is OFT`; the dev was still doing `setPeer`/`setEnforcedOptions`/`send` on it at **2026-09-01 06:37 UTC** |
| LaunchpadHook | `0x51768F5dA32B…` | the *existing* v4 hook, `burnAccruedImd()` — pool4 is a **different, new** pool |
| BurnExecutor | `0xe29386719C155B6847aD5a4E97C6674f10ffc750` | permissionless since 08-20; the dev says the new hook keeps feeding it |
| v4 PositionManager | `0xbD216513d74C8724199e4bdBAFDedFe1E1156AbC` | ops wallet's `modifyLiquidities` calls |

**No pool4 hook, vault or dripper is deployed on mainnet as of 2026-09-01 06:37 UTC.** The
dashboard must therefore *discover* the mainnet addresses rather than ship them hardcoded.

---

## The hook: `beforeInitialize` + `beforeAddLiquidity` + `afterSwap`, sole LP

The hook address's low 14 bits are the v4 permission flags — and this document got them wrong
on first pass. The address *ends* `6840`, so the visible `840` is a mined vanity tail and the
flag field is `0x6840 & 0x3FFF` = **`0x2840`**, not `0x840`. The nibble above the visible tail is
set and reading the tail as the field silently drops a permission.

Settled by asking the contract rather than by arithmetic on the address —
`getHookPermissions()` (`0xc4e833ce`) on **all three** launch hooks returns
`beforeInitialize`, `beforeAddLiquidity`, `afterSwap` and nothing else, and the decoded mask
agrees with each address's own low 14 bits:

```
launch 1  0x1230007b…6840   low14 = 0x2840   getHookPermissions = 0x2840   agree
launch 2  0xCA0612FF…E840   low14 = 0x2840   getHookPermissions = 0x2840   agree
launch 3  0xa1B997A9…6840   low14 = 0x2840   getHookPermissions = 0x2840   agree

0x2840 = BEFORE_INITIALIZE (1<<13) | BEFORE_ADD_LIQUIDITY (1<<11) | AFTER_SWAP (1<<6)
```

Three bits, and the architecture is in all three:

* `beforeInitialize` — **nobody else can open a pool with this hook.** The hook gates its own
  pool's creation, so there is exactly one pool4 and it is the one the hook initialised itself
  via `initializePool(uint160)`.
* `beforeAddLiquidity` — **nobody else can LP.** The hook is the pool's only liquidity provider,
  which is what lets it treat the position as its own balance sheet.
* `afterSwap` — it reacts *after* the swap settles. The two RETURNS_DELTA bits are **not** set,
  so the hook cannot alter a swap's price or take a delta mid-swap. It works by calling
  `modifyLiquidity` on its own position afterwards.

**Consequence for any consumer:** a fingerprint gate written as `low14 == 0x840` rejects the real
hook, and one written as `low14 & 0x840` accepts a hook that does not gate pool initialisation.
Use the full `0x2840`, and read `getHookPermissions()` as the corroborating source.

### Recovered interface (from bytecode selectors)

State: `token() poolManager() poolId() poolKey() owner() burnSink() rewardsRecipient()
backstop() marketOpen() rebalanceEnabled()`
Config: `BPS_DENOMINATOR() rewardShareBps() lpFee() capFloor() keeperReward()`
Position: `tickSpacing() tickLower() tickUpper() refTick() currentTick() currentSqrtPriceX96()
positionLiquidity() ethInPool() tokensInPool()`
Counters: `totalBurned() totalRewarded() totalFeeToken() retainedEth() lastClaimBlock()`
Actions: `initializePool(uint160) settleClaims() rebalance() withdrawFees(address)
setBurnSink(address) setRewardsRecipient(address) setCapFloor(uint256) setKeeperReward(uint256)
closeMarket(address)`

### Events

| topic0 | signature | meaning |
|---|---|---|
| `0xaf7c505e…` | `FeeCollected(uint256,uint256)` | the 1% swap fee, `(imdAmount, ethAmount)` — the protocol/inference cut |
| `0x32afb955…` | *(pre-image not found)* `(uint128 liquidityRemoved, uint256 toBurn, uint256 toRewards, uint256 eth)` | **accrual** on a sell |
| `0x10ea7188…` | `ClaimsSettled(uint256,uint256,uint256)` | **settlement**: `(burned, rewarded, eth)` — the actual dEaD + dripper transfers |
| `0xa66e3643…` | *(pre-image not found)* `(uint256 before, uint256 after)` | pool IMD reserve, emitted on buys |
| `0xe3966151…` | *(pre-image not found)* `(int24, int24, uint128, uint256)` | the **new** backstop position |
| `0xbdf538ed…` | *(pre-image not found)* `(uint128, uint256, uint256, uint256)` | the **retired** backstop, emitted just before it |
| `0xdeb5099d…` | `FeesWithdrawn(address,uint256,uint256)` | owner pulls the accrued protocol cut |
| `0x0cbcc38b…` | `KeeperRewardPaid(address,uint256)` | paid on `rebalance()` |
| `0x5da4124c…` | `Rebalanced(int24)` | new reference tick |

The four unresolved topics were searched over ~45,000 name×signature candidates without a hit;
they are named here for what their operands provably are, not for what they are called.

---

## The mechanism, proven from one transaction each

### A BUY — tx `0x841e5af58c…` (0.01 ETH in)

```
Swap(amount0 = -0.01 ETH, amount1 = +8,822,655.7085 IMD, tick 205992, fee 10000)
6909 Transfer  hook ← 0.0001 ETH
FeeCollected(0, 0.0001 ETH)                      ← 1% of 0.01, in ETH
0xa66e3643(900,000,000 → 891,177,344.2915)       ← pool IMD reserve, −8,822,655.7085
Transfer  PoolManager → buyer  8,822,655.7085 IMD
```

The fee on a buy is taken **in ETH** and retained (`retainedEth`). The pool's IMD reserve falls
by exactly what the buyer received.

### A SELL — tx `0x028d1448a9…` (8,500,000 IMD in)

```
Swap(amount0 = +0.0094 ETH, amount1 = -8,500,000 IMD, tick 206180)
ModifyLiquidity(-887220, 887220, 0, 0)           ← zero-delta poke to collect
6909 Transfer  hook ← 85,000 IMD
FeeCollected(85,000 IMD, 0)                      ← 1% of 8,500,000, in IMD
ModifyLiquidity(-887220, 887220, −280.6271e18, 0)  ← hook REMOVES liquidity
6909 Transfer  hook ← 0.0094 ETH  and  ← 8,415,000 IMD
0x32afb955(280.6271e18, 7,573,500, 841,500, 0.0094 ETH)
```

7,573,500 + 841,500 = **8,415,000 = 8,500,000 − 85,000**. The sold IMD, minus the 1% fee, is
pulled straight back out of the position and never becomes pool reserve.

### The settlement — tx `0xb0cc226147…`

```
Transfer  PoolManager → 0x…449B (RewardDripper)   990,000 IMD
Transfer  PoolManager → 0x…dEaD                 8,910,000 IMD
ClaimsSettled(8,910,000, 990,000, 0.0135 ETH)
```

`990,000 / 9,900,000 = 10.00%`. Settlement is opportunistic — it rides the next swap — and
`settleClaims()` is the permissionless way to force it.

### The split, three ways, to the basis point

Per unit of **IMD sold into the pool**:

| slice | share | destination | on-chain proof |
|---|---|---|---|
| protocol / inference | **1.00%** | `totalFeeToken`, owner `withdrawFees` | `FeeCollected` |
| **burn** | **89.10%** | `0x…dEaD` | `ClaimsSettled[0]` |
| stakers | **9.90%** | RewardDripper → sIMD | `ClaimsSettled[1]` |

`rewardShareBps() = 1000` and `BPS_DENOMINATOR() = 10000` on **all three** launches — the split
did hold to the basis point every time. Independent confirmation from the running totals:

* Σ of all 17 `FeeCollected` IMD legs = **3,650,057.78** = `totalFeeToken()` exactly.
* Σ of all 17 `ClaimsSettled[0]` = **325,220,148.198** = `totalBurned()` exactly, and equals the
  `0x…dEaD` balance of the test token exactly.
* Σ of all 17 `ClaimsSettled[1]` = **36,135,572.022** = `totalRewarded()` exactly.
* 36,135,572.022 / 361,355,720.220 = **10.0000%**.

On a **buy** the fee is ETH and there is no burn — buys are not deflationary, sells are.

---

## What this does to supply — the ratchet

Buys take IMD out of the pool. Sells do **not** put it back; 89.1% of it is destroyed. So the
pool's IMD reserve is **monotonically non-increasing**, and on the current Sepolia launch it went
`900,000,000 → 472,569,750.77` in about 65 minutes. 325,220,148.198 of the 1,000,000,000 test
supply — **32.5%** — was burned in that window.

That is the headline and it is also the hazard: an ordinary constant-product pool round-trips,
this one does not. Every sell is a one-way supply event, and the pool's ability to keep quoting
depends on the ETH side plus the backstop, not on regaining inventory.

`capFloor()` is what stops it running to zero. It rose 50,000,000 → 250,000,000 between launch 2
and launch 3, and launch 1 shows it binding **to the wei**:

```
launch 1, capFloor() = 50,000,000
  blk 11593535  reserve  361,315,580.9592 → 249,690,286.9590
  blk 11593563  reserve  249,690,286.9590 → 152,030,338.5414
  blk 11593595  reserve  152,030,338.5414 →  50,000,000.0000   ← exactly capFloor()
```

The reserve descends through eight buys of arbitrary size and then stops on a round
50,000,000.000000000000000000 — a buy that would have taken it below the floor was **clamped at
the floor**. A buy landing on that number by chance is not a credible reading. So `capFloor` is a
floor on the pool's IMD reserve that binds **the swap path**: the pool will not sell its last
`capFloor` tokens.

Two honest qualifications:

* It binds the swap path, **not every path**. Launch 1's live `tokensInPool()` now reads
  **48,849,555.29**, which is *below* its own floor. Between the clamp and that reading sit a
  sell and a backstop reshuffle (`0xbdf538ed` retires the old backstop, `0xe3966151…` announces
  the new one), so a rebalance can move the reserve past the floor even though a swap cannot.
* Nothing here proves *what the hook does with the tokens it declines to sell*, only that it
  stops selling. The earlier guess in this document — that sold IMD is returned to the position
  instead of burned once the floor is reached — is **not** supported by the logs and has been
  withdrawn.

Launch 2 gives the ratchet its cleanest single proof. At blk 11608025 a **900,000,000 IMD sell**
produced `FeeCollected(9,000,000, 0)` and an accrual of `burn = 801,900,000` /
`rewards = 89,100,000` — 1% / 89.1% / 9.9% of 900,000,000 to the wei — and `tokensInPool()` is
**still 81,093,594**, exactly where the preceding buy left it. Nine hundred million IMD went into
the pool and not one token of it became reserve.

`backstop()` returns **three** words, `(int24 204180, int24 887220, uint128 11540192748389887579912)`
— 96 bytes, no ETH word. (An earlier draft of this document listed a fourth, `0.4253 ETH`; that
value comes from the *event* `0xe3966151…`, which has four operands, not from the getter. A
decoder that expects four reads past the answer.) It is a second,
single-sided position above the current tick (`currentTick() = 203988`), re-centred by the
permissionless `rebalance()` which pays `keeperReward()`. `refTick() = 204150` is the reference
it re-centres against.

---

## `StakedIMD` (sIMD) — ERC-4626, verified source

Solady `ERC4626` + `Ownable`. `name() = "Staked IMD"`, `symbol() = "sIMD"`,
`_decimalsOffset() = 6`. **No emissions, no rebase**: reward IMD is transferred in, `totalAssets`
rises, every share is worth more. There is no claim step.

Anti-JIT is two layers, and the contract's own comments say why:

1. **RewardDripper** streams rewards in small frequent steps rather than a lump.
2. A **one-block hold** — `lastDepositBlock` blocks a same-block `deposit → redeem`. The stamp
   lives in `_beforeTokenTransfer`, not `_deposit`, deliberately: keying it on the deposit `to`
   let a third party stamp any address for free (grief) and let a depositor shed it by moving
   shares to a fresh account (bypass). A positive mint stamps the holder; a transfer carries the
   sender's hold forward; burns and zero-amount moves stamp nothing.

`maxDeposit/maxMint/maxWithdraw/maxRedeem` are pause- and hold-aware, so they report 0 rather
than a number that would revert.

**Trust surface, stated plainly in the source:** while the owner has not renounced, `setPaused`
stops every entry point and `rescueERC20` can move **the staked IMD itself**. The comment calls
this "a deliberate 'move funds to safety in a worst case' hatch, not a trustless design."
Renouncing drops both, and is blocked while paused so the vault cannot be bricked. **Whether the
mainnet owner has renounced is a live read the dashboard should show, not an assumption.**

**`decimals()` returns 24, not 18** — Solady's ERC4626 reports `asset decimals + _decimalsOffset`,
and the offset here is 6. One whole `sIMD` is therefore `1e24` units, and any consumer that
divides by `1e18` is wrong by a factor of a million in both directions:

```
convertToAssets(1e18)/1e18 = 0.000001302985528554   ← wrong, looks like a dead vault
convertToAssets(1e24)/1e18 = 1.302985528554         ← the share price
totalSupply/1e18 = 21,010,977,789.12 sIMD           ← wrong, looks like an emissions farm
totalSupply/1e24 =         21,010.98 sIMD           ← the share count
cross-check: totalAssets 27,377.00 / 21,010.98 shares = 1.302986   ✓
```

Live on Sepolia: `totalAssets() = 27,377.0 IMD`, `convertToAssets(1e24) = 1.3029855` → the share
price is **1.3030 IMD**, i.e. +30.3% for a depositor at parity, accumulated in ~1.5 hours of
testnet trading. Testnet volume is synthetic; the *number* is not a forecast, the *mechanism* is.

## `RewardDripper` — verified source

Holds the lumpy 10% and releases `min(rate × min(elapsed, maxCatchup), balance)`.

* `dripRatePerSecond() = 1e18` (1 IMD/s)
* `maxCatchupSeconds() = 3600` → **per-call lump ceiling = 3,600 IMD**
* `minDripAmount() = 1,000e18`, `keeperReward() = 1e18` (0.1% of a drip; the contract enforces
  ≤ `minDripAmount / 100`)
* `drippable() = 3,600 IMD`, `canDrip() = true` at time of reading

Idle time beyond `maxCatchupSeconds` is **forfeited, not banked**, so a long quiet spell followed
by one `drip()` can never dump the buffer. `drip()` is permissionless and pays its caller.

The consequence worth putting on screen: **the vault's yield is rate-limited, not flow-limited.**
36,135,572 IMD has been rewarded; the stream can move 86,400 IMD/day. The backlog is over a
year deep at the current knobs. sIMD APR is a function of `dripRatePerSecond` and vault TVL — not
of how much the pool earned.

`renounceOwnership()` is blocked in configurations that would strand the buffer (`rate == 0`,
`vault == 0`, or `minDripAmount > rate × maxCatchup`).

---

## The `bond` tab

`imd.fun/pool4/` is a static teaser — the copy is *"pool4: protocol owned inference. the hook
will pay for the compute. no emissions. no rebases. no inflation. 24 hours."* plus three tab
labels `swap · stake · bond`. There are no addresses in the page or its JS chunks.

**No bond contract exists on Sepolia.** Every contract the dev deployed across the three launches
is accounted for above. The bond leg is announced but not yet built where anyone can read it, so
the dashboard ships a bond panel that says so rather than one that guesses.

---

## EV and tokenomics — what a holder is actually being offered

**The good, and it is genuinely unusual.** Yield here is redistributed fee revenue, not
emissions: nothing mints, so a staker's gain is not another holder's dilution. The 89.1% burn on
sells means sell pressure shrinks supply instead of only moving price, and the pool reserve
ratchets one way. Both claims are verified on chain above, not taken from the pitch.

**The catch, and it is the same fact.** A one-way pool has no restocking mechanism. Buys drain
IMD; sells burn it. The pool can only keep quoting while the ETH side and the backstop hold, and
`capFloor` — the thing that stops the reserve reaching zero — is an owner-settable number
(`setCapFloor`) on an **unverified** mainnet-bound contract. That is the single parameter most
worth watching and it is exactly the kind of documented-vs-actual gap this repo has been bitten
by before.

**Where the compute money comes from.** 1% of every swap, in whichever currency came in, retained
as `totalFeeToken` / `retainedEth` and pulled by the owner with `withdrawFees`. On Sepolia the
dev has already withdrawn twice (3,220,057.78 + 430,000 IMD, and 0.0050 + 0.0007 ETH). This is
the "protocol owned inference" claim made concrete, and its rate is directly observable: it is
1% of volume. It is also a **trusted** flow — `withdrawFees` goes to an owner-chosen address and
nothing on chain binds it to buying inference.

**For a staker.** sIMD's return is `dripRatePerSecond` divided across vault TVL, capped by the
backlog. Early and small is structurally better than late and large, and the one-block hold plus
the drip ceiling are there specifically to stop a flash-loaned deposit from taking a lump. The
honest framing for a dashboard: show the **drip rate**, the **backlog**, and the **share price**,
and let APR be derived — an APR quoted from a testnet hour would be a fantasy number.

**The powers that are not renounced yet.** Vault `setPaused` + `rescueERC20` (can move staked
IMD), dripper `rescueERC20` (can move the reward buffer), hook `setCapFloor` / `setBurnSink` /
`setRewardsRecipient` / `closeMarket` / `withdrawFees`. All are owner-only, all are live reads,
and each one has a renounce path. A view that shows their current state is worth more than one
that assumes either the best or the worst.

---

## What the dashboard must read, and how (keyless)

Everything above came from three keyless sources and no API key:

* **Sepolia / mainnet RPC** `eth_call` for every hook, vault and dripper view above. The hook's
  full state is ~20 static calls and batches cleanly on `publicnode`.
* **v4 pool state** via `PoolManager.extsload` — the repo already has this in
  `data/surf_v4.py` (`pool_state_slots`, `decode_slot0`) and `data/keccak.py`.
* **Blockscout REST** for the log history (`ClaimsSettled`, `FeeCollected`, `Rebalanced`), on the
  same keyless pattern the announce channel already uses. The hook **does** emit logs, so unlike
  the announce channel this one is indexable normally — but note `ethereum-rpc.publicnode.com`
  refuses archive `eth_getLogs`, so logs go through the tenderly/drpc pool per CLAUDE.md.

**Address discovery is the open problem.** Mainnet addresses do not exist yet. The dev has always
announced onchain first, and the announce channel is already polled every tick by this dashboard.
The mainnet hook is therefore discoverable from the channel post that announces it, and until
that post lands the view must render an explicit *not yet live* state — never a blank panel and
never a testnet number presented as mainnet.
