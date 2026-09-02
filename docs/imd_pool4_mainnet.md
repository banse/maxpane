# pool4 on MAINNET — what actually shipped, and how it differs from Sepolia

Compiled 2026-09-02, the day pool4 went live. **Every number here is a live mainnet read**, not a
figure from `pool4.imd.fun/docs`. Where the docs and the chain agree it is noted; where they cannot
be checked it is said. This supersedes `docs/imd_pool4_mechanics.md` for anything mainnet-specific;
that document remains the record of the Sepolia deployment the view was built against.

## The cast (all verified to have code on mainnet)

| Component | Address | bytes |
|---|---|---|
| **Market hook** | `0xc6c965bd164c483e87d0b550671798e9a3602840` | 21,126 |
| **sIMD vault** | `0x9efa934d9fad4ae28c998a40195646b965a97247` | 6,205 |
| **Reward Distributor** *(new — no Sepolia counterpart)* | `0x9046739E1535B40EfBe6AB3f45d0024b690eCA30` | 2,334 |
| **Reward Dripper** | `0xe6D3De6daEAf327fCA42745f1998FcD989e00884` | 2,970 |
| Burn Executor | `0xe29386719C155B6847aD5a4E97C6674f10ffc750` | pre-existing |
| IMD token | `0xD34a99Bc0f67aE1bbd63C660e6d0b0dd03E263B7` | pre-existing |
| v4 PoolManager | `0x000000000004444c5dc75cb358380d2e3de08a90` | mainnet canonical |

**The discovery gate would accept this hook.** `low14 = 0x2840`, `getHookPermissions()` returns
exactly `beforeInitialize | beforeAddLiquidity | afterSwap`, and `token()` returns the known mainnet
IMD. The `0x2840` work holds on the real deployment — the fingerprint transferred intact.

## What changed, and whether the view adapts by itself

| | Sepolia launch-3 | Mainnet | view adapts? |
|---|---|---|---|
| `rewardShareBps` | 1000 (10%) | **1500 (15%)** | **yes** — read live |
| `capFloor` | 250,000,000 IMD | **1,000 IMD** | **yes** — read live |
| `lpFee` | 10000 (1%) | 10000 (1%) | unchanged |
| `burnSink` | `0x…dEaD` | **BurnExecutor `0xe293…c750`** | yes, but see below |
| `rewardsRecipient` | the Dripper | **the Distributor** | **NO — breaks the vault path** |
| vault `decimals()` | 24 | 24 | yes |

**Two hook getters recovered from bytecode**, neither in any public signature database — selectors
computed from the docs' own vocabulary and confirmed present.

**Correction (WP6, verified):** an earlier draft of this document said these exist only on mainnet.
That was an assumption, never measured, and it is **wrong** — the Sepolia launch-3 hook answers both.
The difference is the *value*, not the presence:

```
                         Sepolia                    Mainnet
capDecayTokensPerDay()   2**128-1 (no decay)        1,000 IMD/day
inventoryCap()           472,569,750.77 IMD         5,413.26 IMD
tokensInPool()           472,569,750.77 IMD         5,413.26 IMD    <- cap == inventory on BOTH
control: vault()         reverts                    reverts
```

This mattered: a test written as "point it at Sepolia and watch the fields go `None`" would have
**passed for the wrong reason**. The absence case has to be driven by a getter made to revert, which
is what a differently-built future hook actually looks like.

**Second correction (WP1, verified) — and this one falsified a claim of mine that three decisions
were built on.** An earlier draft said `inventoryCap()` equals `tokensInPool()` *on both chains*, so
"the cap tracks the inventory rather than binding it". That was **a snapshot, not a law**. It holds
on Sepolia only because the decay rate there is the no-decay sentinel, so the cap never moves. On
mainnet the cap decays at 1,000 IMD/day and the two drift apart between events:

```
                    inventoryCap        tokensInPool        headroom
mainnet            5,331.227804        5,236.544041        94.683763 IMD
sepolia      472,569,750.774434  472,569,750.774434         0.000000
```

**94.68 IMD is fully representable as a float difference** — the 12-wei gap that made the earlier
subtraction argument correct was itself an artefact of sampling moments after an event. An equality
test would be flaky on mainnet and green on Sepolia for the wrong reason.

* `capDecayTokensPerDay()` = **1,000 IMD/day** (`0x55e62941`) — the ratchet the docs describe as
  *"buys lower the inventory cap"*.
* `inventoryCap()` (`0xdb445ee8`) — the ceiling the decay walks down. **It is not equal to
  `tokensInPool()`; see the second correction below.** An earlier draft of this bullet read
  "currently equal to `tokensInPool()` to within 12 wei, i.e. the cap is sitting on the inventory",
  which was a single sample taken moments after an event, stated as a property. Live values move
  and are given in the drift table rather than here, precisely so this bullet cannot go stale
  again.

## The break: the vault is three hops away, not two

Sepolia: `hook.rewardsRecipient()` → **Dripper** → `dripper.vault()` → StakedIMD.
Mainnet: `hook.rewardsRecipient()` → **Distributor** → `distributor.dripper()` → Dripper →
`dripper.vault()` → sIMD.

The view's two-hop path calls `vault()` on the Distributor, which has no such method. **Vault and
dripper reads fail outright on mainnet** until this is fixed. This is the one change that is not
self-adapting.

## The reward split is now three-way, inside the Distributor

Recovered interface: `stakingBps() nftBps() dripper() asset() owner() distribute()
stakingEarned() bondingEarned() nftEarned() heldBonding() heldNft() setDripper(address)
emergencyWithdraw(address)`.

Live, and the chain confirms the docs **exactly**:

```
stakingBps 3000 (30%) · nftBps 3000 (30%) · bonding 4000 (40%, the remainder)
stakingEarned 3.1490 IMD · bondingEarned 4.1986 IMD · nftEarned 3.1490 IMD
heldBonding   4.1986 IMD · heldNft       3.1490 IMD
```

So per 100 IMD retired: **85 burned, 4.5 stakers, 6.0 bonding, 4.5 nodes**. Bonding is the
*remainder*, not its own getter — deriving it as `10000 - stakingBps - nftBps` is the only way to
get it, and that derivation should be named as such rather than hardcoded at 4000.

`nft` in the code is `nodes` in the docs — the NFT-holding compute daemons the announce channel
described in August ("you'll need an NFT, a codex or claude subscription… one NFT per daemon").

## Live state at time of writing

```
hook   tokensInPool 5,487.3465 IMD · ethInPool 3.7976 ETH · inventoryCap 5,487.3465
       ^ a single sample. cap and reserve DRIFT — see the drift table above; do not read
         this block as evidence they are equal
       capFloor 1,000 · totalBurned 59.4807 · totalRewarded 10.4966 · totalFeeToken 0.8437 IMD
       retainedEth 0.0479 ETH · currentTick 72,761 · refTick 72,667 · marketOpen · rebalanceEnabled
vault  decimals 24 · totalAssets 1,293.31 IMD · share price 7.902919 IMD
drip   rate 0.001 IMD/s (86.4/day) · drippable 0 · canDrip false · minDrip 1.0
```

`10.4966 / (59.4807 + 10.4966) = 15.00%` — the 85/15 split, confirmed from the counters themselves.

Docs say the soft launch seeded 4 ETH / 5,000 IMD; the pool now holds 3.7976 ETH / 5,487.35 IMD, so
trading has already moved it. `retainedEth` is non-zero here where Sepolia's was always swept to 0.

## Discovery: the operator's decision, and what it costs

**The announce channel has not named this hook.** Its newest post is still 2026-09-01. Under
amendment A27 the gate requires a dev-signed self-post, so automatic discovery correctly refuses
and the view would show SEPOLIA while mainnet is live.

**The operator has chosen to accept `pool4.imd.fun/docs` as a candidate source.** All six addresses
are in that page's server-rendered HTML (no JSON API, no key required). Implemented as a *candidate*
source only — the full chain fingerprint still applies, and the announce channel remains the
stronger path and overrides it when a self-post lands.

**The cost, stated once and then not relitigated:** the docs site becomes a trusted input. Anyone
who can change that page can name a hook, and the fingerprint alone will not stop them — a
`0x2840`-shaped address mines in ~20,000 tries, four of the five getters are pure liveness checks,
and `token()` is the candidate's own choice. The mitigation is disclosure rather than prevention:
**the panel names which source an adoption came from**, so weaker provenance identifies itself
instead of hiding behind the same word as a dev-signed post.
