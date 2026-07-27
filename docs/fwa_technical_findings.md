# Fake World Assets (FWA) — Technical Findings

Data-layer reconnaissance for the planned MaxPane **FWA** dashboard.

**Research date: 2026-07-25.** All live values pinned to Ethereum mainnet blocks **25612655–25612716**
(2026-07-25 ~22:00–22:15 UTC) unless stated. Everything below was obtained **keylessly** except where
explicitly marked *research-only*.

Companion file: `docs/fwa_game_mechanics.md` (protocol mechanics, formulas, parameters, strategy).

---

## 1. Network

| Field | Value |
|---|---|
| Chain | Ethereum mainnet |
| Chain id | **1** (`eth_chainId` → `0x1`, verified on 4 independent public RPCs) |
| Block time | ~12 s |
| Protocol deploy block | **25546793** (FWA core config write) / **25546799** (`FWATokenHook.deploymentBlock()`) |
| Acquisitions enabled since | block **25575879** = 2026-07-20T19:01:23Z |
| Protocol age at research time | ~66,000 blocks — **a full historical backfill is cheap** |

---

## 2. Contract registry

All 8 addresses come from https://www.fwa.fun/docs/deployments, and all 8 were **independently
verified three ways**: (a) EIP-55 checksum recomputed locally via keccak-256, (b) `eth_getCode`
returns bytecode on chain id 1, (c) the Etherscan-verified `Contract Name` matches the doc label.

| # | Label | Address | Code size | Verified | Role |
|---|---|---|---:|---|---|
| 1 | **FWA** (core pool) | `0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c` | 21,425 B | ✅ Etherscan (`FWA`) | Accounting, positions, weighting, VRF selection, settlement, crown, config |
| 2 | **FWARewards** | `0x6a1a1C0CfB3D3C538e13D36d608a5bcaa992fc78` | 11,514 B | ✅ (`FWARewards`) | $FWA emissions, purchaser epochs, reward buys, hot/cold split |
| 3 | **FWAVRFService** | `0xa084c33Fb7a467307452898b8D58165ebd2E5D9f` | 6,344 B | ✅ (`FWAVRFService`) | Chainlink VRF 2.5 subscription coverage, request fees, sponsored processing |
| 4 | **FWAToken** ($FWA) | `0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845` | 11,394 B | ✅ (`FWAToken`) | ERC-20, 18 dec, 1e27 supply, buyback routing — **matches the address in the brief** |
| 5 | **FWATokenHook** | `0x2C67ebA8A50AF0dB5Fba55F725247a75CbDA6444` | 7,072 B | ✅ (`FWATokenHook`) | Uniswap v4 hook: `externalBuysEnabled` gate + 1% trading fee |
| 6 | **FWAClaim** | `0xd4085d38855F17EdF0B1CCBFad7B3846fb305655` | 1,800 B | ✅ (`FWAClaim`) | Merkle-gated v1 snapshot distribution (snapshot block 25,452,023) |
| 7 | **FWAWhitelist** | `0x854352b275cF6A0DfFCf2983C986FBe9345e17c3` | 2,683 B | ✅ (`FWAWhitelist`) | Collection curation, sticky blocking, TTT-funded entry |
| 8 | **Splitter** | `0x1C175b9F0e8C73eD3e677e1cBb1B5A2DD4373Bfe` | 3,949 B | ✅ (`Splitter`) | Protocol-fee split 63% / 7% / 30% |

### Wiring proof (strongest anti-hallucination check — every read confirmed onchain)

```
FWA.rewards()            → 0x6a1a1C0CfB3D3C538e13D36d608a5bcaa992fc78   (FWARewards)
FWA.token()              → 0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845   (FWAToken)
FWA.vrfService()         → 0xa084c33Fb7a467307452898b8D58165ebd2E5D9f   (FWAVRFService)
FWA.payoutAddress()      → 0x1C175b9F0e8C73eD3e677e1cBb1B5A2DD4373Bfe   (Splitter)
FWARewards.fwa()         → 0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c   (FWA)
FWARewards.token()       → FWAToken
FWARewards.tokenHook()   → FWATokenHook
FWARewards.tokenPoolManager() → 0x000000000004444c5dc75cB358380D2e3dE08A90 (Uniswap v4 PoolManager)
FWAToken.hook()          → FWATokenHook
FWATokenHook.token()     → FWAToken
FWAWhitelist.fwa()       → FWA
FWAWhitelist.ttt()       → 0x26D7Ad0E930b54b84C00DAad077Ee31Ba9e2Fb2E   (TTT)
```

No address in the research bundle is orphaned.

### Satellite addresses (newly discovered — not on any docs page)

| Label | Address | How found | Notes |
|---|---|---|---|
| **Protocol owner (EOA)** | `0x019817aD02a31B990433542097bE29D97613E8Cb` | `FWA.owner()`, `FWAWhitelist.owner()`, `Splitter.owner()`, `FWAClaim.owner()`, `FWATokenHook.feeAddress()` | `eth_getCode` = `0x` → **plain EOA, no multisig, no timelock**. Same address as the TTT creator in `docs/tenthousandtokens_technical_findings.md`. |
| **Splitter snapshot NFT** | `0xb33d806a94B6770C9d309E0842a75f8E6edCd5A6` | `Splitter.NFT_ADDRESS()` | `name()` = "TokenWorks S02", `symbol()` = "S02" — the soulbound NFT taking the 30% leg |
| **Splitter secondary recipient** | `0x8e5963F8219789e90d8712609B216C31263317a3` | `Splitter.SECONDARY_OWNER()` | the 7% leg |
| **Chainlink VRF 2.5 coordinator** | `0xD7f86b4b8Cae7D942340FF628F82735b7a20893a` | `FWA.vrfCoordinatorAndSubId()` | |
| **Uniswap v4 PoolManager** | `0x000000000004444c5dc75cB358380D2e3dE08A90` | `FWARewards.tokenPoolManager()` | singleton — holds every v4 pool's tokens |
| **Multicall3** | `0xcA11bde05977b3631167028862bE2a173976CA11` | canonical | used for enumeration |
| **Ten Thousand Tokens** | `0x26D7Ad0E930b54b84C00DAad077Ee31Ba9e2Fb2E` | `FWAWhitelist.ttt()` | 49.08% of pool weight **and** the permissionless-whitelist burn token |
| **$FWA/ETH Uniswap v4 poolId** | `0x230ecd3c25b44af30db59c15f70df7794eb13f67a200f230b7400daa96fe804d` | DexScreener `pairAddress` | **a poolId, NOT a deployed contract address** |
| **Dead address** | `0x000000000000000000000000000000000000dEaD` | `FWAWhitelist.DEAD_ADDRESS()` | burn target; currently 0 FWA |

**⚠ TRAP:** `FWAToken.pool()` returns `0x6a1a1C0CfB3D3C538e13D36d608a5bcaa992fc78` — that is
**FWARewards**, the authorized distributor/pool-operator, **not a Uniswap pool**. The real v4 pool is
identified by the poolId above inside PoolManager. `FWAToken.poolKey()` exposes the raw key.

---

## 3. Keyless RPC endpoints — capability matrix

The keyless RPCs are **not interchangeable**. Measured 2026-07-25:

| Endpoint | `eth_call` | Batch JSON-RPC | `eth_getLogs` | Notes |
|---|:--:|:--:|:--:|---|
| `https://ethereum-rpc.publicnode.com` | ✅ | ✅ **best batcher** | ❌ | *"Archive requests require a personal token."* 429s under aggressive batching — batch ≤ 60 with ~0.12 s spacing was stable; batch 150 rapid-fire failed. |
| `https://eth.drpc.org` | ✅ | ❌ | ✅ **only keyless log source** | Hard cap **10,000 blocks per request** (*"ranges over 10000 blocks are not supported on free plan"*). Occasional 408 *"Request timeout on the free plan"* on heavy single calls. |
| `https://gateway.tenderly.co/public/mainnet` | ✅ | — | ✅ **no block-range cap** | Second keyless log source; used for the full-history scans in this doc. |
| `https://1rpc.io/eth` | ✅ | ❌ | ❌ | `-32001 "reached the usage limit"` on logs |
| `https://cloudflare-eth.com` | ✅ | ❌ | — | usable fallback for state |
| `https://eth.llamarpc.com` | ❌ | — | — | **DEAD — HTTP 521.** Still the primary in `maxpane_dashboard/data/ttt_client.py:66` — stale. |
| `https://rpc.ankr.com/eth` | ❌ | — | — | **now requires an API key.** Still listed in `maxpane_dashboard/data/ttt_client.py:52` — stale. |

**Recommended split for the FWA data layer:**

```
state / views    → https://ethereum-rpc.publicnode.com  + Multicall3   (batchable, fast)
event logs       → https://gateway.tenderly.co/public/mainnet (no cap)
                   fallback https://eth.drpc.org (10k-block pages)
generic fallback → https://cloudflare-eth.com
```

⚠ Two of MaxPane's existing TTT RPC endpoints are dead/keyed. Fixing `ttt_client.py` is a
prerequisite, not an FWA-specific task.

### ABI acquisition (research-only, not for the shipped data layer)

| Source | Result |
|---|---|
| **Etherscan HTML page** `https://etherscan.io/address/{addr}#code` | ✅ **works keylessly with a plain User-Agent.** Full ABI JSON sits in `<pre id="js-copytextarea2">`; Solidity sources sit in `data-cname='<path>' data-csource='<code>'` attributes; the contract name follows the literal text `Contract Name`. Yielded all 8 ABIs (core 172 entries, rewards 112, vrf 71, token 87, hook 52, claim 31, whitelist 34, splitter 59) and 9 source files including `src/FWA.sol` (2,370 lines) and `src/FWAConfigKeys.sol`. **Research use only** — do not put HTML scraping in the shipped data layer; commit the ABIs to the repo instead. |
| `https://anyabi.xyz/api/get-abi/1/{addr}` | ✅ keyless mirror of the Etherscan verified source; cross-checked against selectors extracted from live bytecode |
| Sourcify v2 `https://sourcify.dev/server/v2/contract/1/{addr}` | ❌ **404 — no match for any FWA contract** (unlike Talismans, where Sourcify was the winner) |
| Blockscout `https://eth.blockscout.com/api/v2/smart-contracts/{addr}` | ⚠ HTTP 200, ~88 KB JSON, but **no `abi` / `source_code` / `is_verified` fields** — bytecode only |
| Etherscan API v1/v2 `getabi` | ❌ requires an API key — forbidden by the hard constraint |

**Action for implementation:** vendor the 8 ABIs into `maxpane_dashboard/data/abis/fwa/*.json` (same
pattern as `docs/talismans_abi.json`) so runtime never touches Etherscan.

---

## 4. View functions — FWA core (`0xB276F62D…`)

### 4.1 Pricing & pool aggregates

| Signature | Selector | Returns | Decode notes | Dashboard use |
|---|---|---|---|---|
| `quoteAcquisitionPrice()` | `0x987df4cd` | `(uint256 fee, uint256 vrf, uint256 total)` | **THE right primitive** — one call gives the exact minimum `msg.value`. Must be called with an explicit `gasPrice` (see §7). | Price tile |
| `acquisitionFee()` | — | `uint256` wei | `= (weightedBackingTotal / totalWeight) * 11000 / 10000`, two floor divisions. Returns 0 if `totalWeight == 0`. | Price tile, price history |
| `totalWeight()` | — | `uint256` | Σ of `1e36/backing`. Live 31,217,322,873,711,845,581,134 | Odds denominator |
| `weightedBackingTotal()` | — | `uint256` | **⚠ NOT a wei amount and NOT TVL** — see §6 trap 3 | EV numerator only |
| `activeListingCount()` | `0x4681a7c6` | `uint256` | Live 3,867–3,891 | Fee-split denominator |
| `nextListingId()` | — | `uint256` | Live 56,586–56,616 | Cumulative deposits proxy |
| `feeShareTotal()` | — | `uint256` | **Always == `activeListingCount()`** (feeShare = 1 each) — a free invariant check | Health check |
| `BPS()` | — | `uint256` = 10000 | | Formula constant |

### 4.2 Positions

| Signature | Selector | Returns | Decode notes |
|---|---|---|---|
| `listings(uint256 listingId)` | `0xde74e57b` | `(address collection, address depositor, address allocatee, uint256 tokenId, uint256 weight, uint256 value, uint256 feeShare, uint256 feeDebt, uint256 slot, uint64 allocatedAt, uint8 status)` | **Flat 11-tuple, all static types → head-only ABI encoding, 11 × 32 bytes = 352 B.** `value` is the backing in wei. `allocatee` = `0x0` while unallocated. `status == 1` = Active. |
| `slotToListing(uint256 slot)` | `0xe2881eb7` | `uint256 listingId` | **1-indexed and NON-CONTIGUOUS** — see §6 trap 1 |
| `collectionWhitelisted(address)` | — | `bool` | Live: all 51 whitelisted collections return true; a random address returns false |

**Verified example** — `listings(56508)`:
```
collection  0x26D7Ad0E930b54b84C00DAad077Ee31Ba9e2Fb2E   (TTT)
depositor   0xb873bDcBa0e9E40503A562abFeB4CCE80CC33119
allocatee   0x0000000000000000000000000000000000000000
tokenId     8976
weight      4524886877828054
value       221000000000000000000                        (221 ETH — the largest position)
feeShare    1
feeDebt     6590500784182843196
slot        1141
allocatedAt 0
status      1                                            (Active)
```
Python check: `10**36 // (221 * 10**18) == 4524886877828054` ✅ exact.

### 4.3 Crown

| Signature | Returns | Live value |
|---|---|---|
| `topListingId()` | `uint256` (0 = vacant) | 56283 (at one sample block) |
| `topListingPot()` | `uint256` wei | 60242085156350313 = 0.060242 ETH (at that block) |
| `topThresholdBps()` | `uint256` | **1000** (challenger needs ≥ 1.10× incumbent backing) |
| `topListingShareBps()` | `uint256` | **100** (docs say 500 — changed by the owner at block 25592190) |

ETH needed to take the crown = `listings(topListingId()).value * (BPS + topThresholdBps) / BPS`.

### 4.4 Economic parameters (all confirmed to exist and return)

| Getter | Live value | Meaning |
|---|---|---|
| `ownerAcquisitionFeeBps()` | 100 | 1% protocol acquisition cut |
| `ownerSettlementFeeBps()` | 100 | 1% protocol settlement cut (keep-NFT only) |
| `settlementDiscountBps()` | **8500** | **⚠ this is the PURCHASER PAYOUT RATE (85%), not the 15% discount** |
| `retainedToProtocol()` | true | the 15% retained slice goes to the protocol |
| `selectionSlippageBps()` | 1000 | protocol-capped upward fee drift |
| `selectionTimeoutBlocks()` | 30 | inclusive word deadline |
| `settlementWindow()` | 86400 | 24 h purchaser-exclusive |
| `finalizeWindow()` | 604800 | 7 d anyone-can-finalize |
| `callbackGasLimit()` | 900000 | |
| `owner()` | `0x019817aD…E8Cb` | EOA |

### 4.5 Balances, escrow and queue

| Getter | Live value | Use |
|---|---|---|
| `accruedOwnerFees()` | 2.7226 – 3.4616 ETH | protocol fees awaiting the permissionless `payoutFees()` |
| `acquisitionEscrowTotal()` | 2.196 – 2.734 ETH | escrowed, unresolved acquisition fees |
| `acquisitionRefundCreditTotal()` | 0.173675 ETH | unclaimed pull refunds |
| `acquisitionRefundCredit(address)` | per-user | refund-credit lookup |
| `reservedStagedCount()` | 23 – 30 | deposits in the FIFO staging line, not yet weighted |
| `pendingAcquisitionCount()` | 2 – 8 | open acquisition requests |
| `unsettledAcquisitionCount()` | 16 – 20 | allocated but not settled |
| `unfulfilledVrfCount()` | 2 | VRF words outstanding |
| `lastIssuedSequence()` | 57,790 – 57,825 | FIFO head/tail — queue lag = `lastIssued − nextToProcess` |
| `nextSequenceToProcess()` | 57,775 – 57,806 | |
| `eth_getBalance(FWA core)` | **2,340.27 – 2,551.37 ETH** | the real ETH the protocol holds (backing + escrow + accrued fees). **Use this, not `weightedBackingTotal`, for a TVL tile.** |

### 4.6 VRF wiring (never disclosed in the docs)

| Getter | Value |
|---|---|
| `vrfCoordinatorAndSubId()` | `(0xD7f86b4b8Cae7D942340FF628F82735b7a20893a, 86051977179707821307457886411406404562727233339972463773011284528235484806451)` |
| `vrfRequestConfig()` | `(0x8077df514608a09f83e4e8d300645594e5d7234665448ba83f51a50f842bd3d9, 900000)` — (keyHash, callbackGasLimit) |
| `vrfServiceFee()` | proxies `FWAVRFService.requestFee()` — **gas-price dependent, see §7** |

---

## 5. View functions — satellite contracts

### FWARewards `0x6a1a1C0C…`

| Getter | Live value | Use |
|---|---|---|
| `EMISSION_DAYS()` | 15 | |
| `EMISSION_DURATION()` | 1296000 | |
| `emissionStart()` | 1784574083 = 2026-07-20T19:01:23Z | **emissions end 1785870083 = 2026-08-04T19:01:23Z** |
| `depositorRatePerSec()` | 115740740740740740740 wei/s | ×86400 = 10,000,000 FWA/day |
| `purchaserDailyPot()` | 1e25 | 10,000,000 FWA/day |
| `currentEpoch()` | 5 | day 5 of 15 |
| `hotGap()` / `coldGap()` | 60 / 3600 | hot/cold dial band |
| `forcedTokenShareBps()` | **-1** (int) | -1 = dynamic. **Signed** — decode as int256, not uint256. |
| `lastAcquisitionTs()` | 12 s old at read time | drives the hot/cold dial |
| `sqrtBackingTotal()` | 1,878,489,165,016 – 1,902,743,059,396 | √backing emission denominator |
| `accTokenPerSqrt()` | 248056035632562725245670389098325150896442160870325 | accumulator |
| `tokenBuyAllowanceTotal()` | 0.0886 ETH | pending purchaser $FWA buys |
| `isBuying()` | false | reentrancy/state flag |
| `tokenShareBps(uint256)` | *(not called)* | probable hot/cold interpolation helper — see §11 |

### FWAVRFService `0xa084c33F…`

| Getter | Live value |
|---|---|
| `serviceGasEstimate()` | 800000 |
| `serviceMarginBps()` | 3000 (30%) |
| `serviceFlatWei()` | 0 |
| `approvedCallbackGasLimit()` | 900000 |
| `approvedVrfKeyHash()` | `0x8077df51…d3d9` (same as core) |
| `maxSponsoredCount()` | 10 |
| `subscriptionNativeBalance()` | **31.3777 ETH** |
| `availableProcessorSurplus()` | 14.5968 – 14.6047 ETH |
| `minimumSubscriptionBuffer()` | 0.35 ETH |
| `maxFulfillmentCostWei()` | 0.35 ETH |
| `requestFee()` | **gas-price dependent — see §7** |

### FWAToken `0xa0Df17B5…`

| Getter | Live value |
|---|---|
| `name()` / `symbol()` / `decimals()` | "Fake World Assets" / "FWA" / 18 |
| `totalSupply()` | **1e27** exactly (read live — deflationary by design once buybacks start) |
| `launched()` | true |
| `routeDepositorBps()` / `routePurchaserBps()` / `routeBurnBps()` | 4000 / 4000 / 2000 |
| `CALLER_REWARD_BPS()` | 50 (0.5% buyback caller bounty) |
| `BUYBACK_DELAY_BLOCKS()` / `BUYBACK_INCREMENT()` | 1 / 1e18 |
| `lastBuybackBlock()` | **0 — no buyback has ever run** |
| `buybackSqrtPriceLimitX96()` | 477782542051216404772491119593238 |
| `getTransferAllowance()` | 0 |
| `hook()` | FWATokenHook |
| `pool()` | ⚠ FWARewards, **not** a Uniswap pool |
| `poolKey()` | raw v4 PoolKey |

Balance snapshot: FWARewards **210,036,532 – 210,411,718 FWA** (of the 300M emissions allocation) ·
FWAClaim **3,643,035.67 FWA** (of a stated 200M — see §11) · PoolManager **19,294,940 – 19,716,777 FWA** ·
`0x…dEaD` **0 FWA** · FWA core **0 FWA**.

### FWATokenHook `0x2C67ebA8…`

| Getter | Live value |
|---|---|
| `externalBuysEnabled()` | **false** — outside buys still gated |
| `deploymentBlock()` | 25546799 |
| `poolManager()` | `0x000000000004444c5dc75cB358380D2e3dE08A90` |
| `feeAddress()` | `0x019817aD…E8Cb` (= protocol owner) |
| `token()` | FWAToken |

Toggle: `setExternalBuysEnabled(bool)`, event `ExternalBuysEnabledSet(bool)`.

### FWAWhitelist `0x854352b2…`

| Getter / function | Live value |
|---|---|
| `TTT_AMOUNT()` | **0** — permissionless path disabled |
| `ttt()` | `0x26D7Ad0E930b54b84C00DAad077Ee31Ba9e2Fb2E` |
| `DEAD_ADDRESS()` | `0x…dEaD` |
| `fwa()` | FWA core |
| `blocked(address)` | none blocked today |
| `burnToWhitelist(address,uint256[])` | entry function; event `BurnedForWhitelist(address,address,uint256[])` |
| `setTTTAmount(uint256)` | owner-only; event `TTTAmountSet(uint256)` |

### Splitter `0x1C175b9F…`

| Getter | Live value |
|---|---|
| `totalReceived()` | **720.687972802453422917 ETH** — hard onchain cumulative protocol revenue |
| `ownerShareBps()` / `INITIAL_OWNER_SHARE_BPS()` | 7000 / 7000 |
| `nftShareBps()` | 3000 |
| `SECONDARY_OWNER_DIVISOR()` | 10 → effective 63 / 7 / 30 |
| `SECONDARY_OWNER()` | `0x8e5963F8219789e90d8712609B216C31263317a3` |
| `NFT_ADDRESS()` | `0xb33d806a94B6770C9d309E0842a75f8E6edCd5A6` ("TokenWorks S02") |
| `SNAPSHOT_SUPPLY()` / `MAX_TOKEN_ID()` | 264 / 324 |
| `claimablePerToken()` | 0.818963605457333434 ETH |
| `pendingOwner()` / `pendingSecondaryOwner()` | 295.099 ETH / 32.789 ETH |
| `claimsClosed()` | false |
| `SWEEP_DELAY()` / `SWEEP_AVAILABLE_AT()` | 31536000 / 1815759815 (2027-07-16) |

### FWAClaim `0xd4085d38…`

`claimsEnabled()` = true · `merkleRoot()` = `0x304c5bafbde1693914071ed4981f750f846f9963cb0cec3914bf7bf02d17a1af` ·
`token()` = FWAToken · `claim(uint256,bytes32[])` · `claimed(address)` · `rescue(address,uint256)`.

---

## 6. Enumerating live positions — production recipe + three traps

### 6.1 The recipe (measured: 3,867 positions in **3.3 seconds / 17 `eth_call`s**)

```
1.  blockTag = eth_blockNumber()                          # PIN IT — the pool churns every few seconds
2.  n        = activeListingCount()  @ blockTag
3.  batch slotToListing(slot) for slot = 1, 2, 3, …        # via Multicall3 aggregate3, 500 calls/eth_call
    skip zero results
    stop once n non-zero listingIds have been collected    # NOT once slot == n
4.  batch listings(listingId) for every collected id       # via Multicall3, same blockTag
5.  verify:  Σ (1e36 // value_i)                      == totalWeight()          @ blockTag
             Σ (weight_i * value_i)                   == weightedBackingTotal() @ blockTag
             (Σ weighted / Σ weight) * 11000 // 10000 == acquisitionFee()       @ blockTag
```

**Proof of completeness at pinned block 25612701** — all three recomputed aggregates matched onchain
**bit-for-bit**:

```
totalWeight          recomputed 31217322873711845581134                      == onchain ✅
weightedBackingTotal recomputed 3866999999999999999373145521289217360095     == onchain ✅
acquisitionFee       recomputed 136260883651302691                           == onchain ✅
all 3,867 rows status == 1 (Active)
```

### 6.2 TRAP 1 — slots are 1-indexed and **non-contiguous** (the dynamic/struct-array analogue)

`_allocateSlot()` uses a **free list** (`freeSlotHead` / `nextFreeSlot`) and only grows
`nextUnusedSlot` when the free list is empty. Removed listings therefore leave **permanent holes** in
the slot space.

> Scanning `slot = 1..activeListingCount` silently drops positions. The first attempt found only
> **3,624 of 3,879** and the recomputed `weightedBackingTotal` was off by exactly `255e36` — a
> *plausible-looking* number that would have shipped a wrong price and wrong odds.

Correct behaviour: scan slots **upward from 1, skipping zeros, until you have collected
`activeListingCount` non-zero ids**. In practice slots **1..4500** were needed to find 3,867 live
positions. Budget ~1.2× headroom and assert the count.

This is FWA's equivalent of the Talismans `coresOf()` decode trap and the TTT dynamic-tuple issue —
**the aggregate-invariant check in step 5 is the only thing that catches it.** Ship that check as a
runtime assertion, not just a test.

### 6.3 TRAP 2 — you MUST pin the block

An unpinned 6-minute scan returned 3,654 rows whose recomputed totals did **not** match onchain. The
pool mutates every few seconds (1,327 `AcquisitionRequested` + 1,076 `NFTListed` in a 500-block /
~100-minute window). Pass `blockTag` to every `eth_call` in the sweep.

### 6.4 TRAP 3 — `weightedBackingTotal` is not ETH

```
weightedBackingTotal = Σ (weight_i * backing_i)
                     = Σ ((1e36 / backing_i) * backing_i)
                     ≈ activeListingCount * 1e36
```

Observed `3.890999999…e39` against exactly **3,891** active listings. Its unit is **neither wei nor
ETH**. Rendering it as "3,891 ETH TVL" would be a factual error, and it is a tempting mistake because
the leading digits look like a count of ETH.

**For a TVL tile use `eth_getBalance(FWA core)` (2,340–2,551 ETH) or the enumerated
`Σ backing_i` (1,827.63 ETH).** The difference between those two is escrow + accrued fees + the
crown pot.

### 6.5 TRAP 4 — Multicall3 `aggregate3` hand-encoding

The `Call3` struct is `(address target, bool allowFailure, bytes callData)`, selector `0x82ad56cb`,
returning `(bool success, bytes returnData)[]`. When hand-encoding, **`callData` must be passed
WITHOUT its `0x` prefix**, otherwise the node rejects the whole payload with
`cannot unmarshal invalid hex string into Go struct field TransactionArgs.data`.
Batch size 500 calls per `eth_call` worked reliably against publicnode.

### 6.6 Status enum

`status == 1` = Active for every live position. Values 2, 3, 4 were observed in a drifting scan but
the enum definitions were **not read** — they are in `src/FWA.sol` (`ListingStatus` /
`AcquisitionStatus`). See §11.

---

## 7. VRF observability & the gas-price gotcha

### The gotcha

`FWA.vrfServiceFee()` proxies `FWAVRFService.requestFee()`, which depends on **`tx.gasprice`**. The
source comment says it outright: *"Relies on `tx.gasprice`; quote via an `eth_call` using the intended
transaction gas price."*

A normal `eth_call` with no `gasPrice` returns **0**. Measured at one block:

| `gasPrice` passed | `requestFee()` |
|---|---|
| unset / 0 | 0.000000000 ETH |
| 0.5 gwei | 0.000520 ETH |
| 1 gwei | 0.001040 ETH |
| 50 gwei | 0.052000 ETH |

`800000 × 1 gwei × 1.30 = 0.00104 ETH` — the three components reconcile exactly at 1 gwei.

**You must pass both `gasPrice` AND a bounded `gas` (e.g. `0x200000`)**, or the node rejects the call
with `insufficient funds for gas * price`.

⚠ Two research agents disagreed here: one measured nonzero at explicit gas prices, the other read
`quoteAcquisitionPrice()` → `(137141801557519602, 0, 137141801557519602)` and `requestFee()` = 0 and
concluded the fee is currently **waived** because the subscription is over-funded
(`subscriptionNativeBalance()` = 31.38 ETH vs `minimumSubscriptionBuffer()` = 0.35 ETH). **Both
readings may be artifacts of an unset `gasPrice`.** See §11 — this is unresolved. The safe
implementation is identical either way: **always call `quoteAcquisitionPrice()` with an explicit
`gasPrice` and render the returned tuple; never sum two sources and never assume a nonzero VRF fee.**

### Queue / liveness observability

| Signal | Source |
|---|---|
| Queue depth | `lastIssuedSequence() − nextSequenceToProcess()` (live 15–19) |
| Open requests | `pendingAcquisitionCount()` (2–8) |
| Allocated, unsettled | `unsettledAcquisitionCount()` (16–20) |
| VRF words outstanding | `unfulfilledVrfCount()` (2) |
| Stall threshold | `selectionTimeoutBlocks()` = 30 blocks ≈ 6 min |
| Head-of-queue age | `acquisitionMeta(requestId).wordDeadlineBlock` vs `eth_blockNumber` |
| Subscription solvency | `FWAVRFService.subscriptionNativeBalance()` (31.38 ETH) vs `minimumSubscriptionBuffer()` (0.35 ETH) |
| Processor surplus | `availableProcessorSurplus()` (14.60 ETH) |
| Reconciliation | `reconcileUnfulfilledVrfCount()` (state-changing, informational only) |

A depleted subscription stalls **every** acquisition — worth a red badge.

---

## 8. Events

Full event set on FWA core is **38 events** (from the verified ABI). Confirmed `topic0` hashes:

| Event | topic0 | Signature | Dashboard use |
|---|---|---|---|
| `AcquisitionRequested` | `0xf23e34f4aa4a06ecddd309d9692e7b7ca45b76fd0d5f4ce4f7fbf29731d9abd6` | `(uint256, address, uint256, uint256)` | request feed; **carries `acquisitionFee` and `totalWeight` in data → a full price history is reconstructable from events alone, no archive state needed** |
| `NFTKept` | `0xe71c2721f75bef3206b21176a6d26685852a16878249fc84d18f443f959bb8f5` | `(uint256, address, address, uint256)` | settlement mix |
| `DepositorBidAccepted` | `0x88ebc94b0ff4693b3d25995dc7c5c4e5683a8ca7de00836773ca24c8b69d78e3` | `(uint256, address, address, uint256, uint256)` | settlement mix |
| `DepositorBidAcceptedAsTokens` | `0x819cd055ab6ba83877ab68882609b8d7aa75d4951f6d89fa99d3b59fa45f439f` | `(uint256, address, address, uint256, uint256, uint256)` | settlement mix (73.9% of all) |
| `NFTRelisted` | `0x5fa40266a1e401404f322db009d5f8631ed44abc96b84784d9f8f90a8846abd8` | `(uint256, uint256, uint256)` | settlement mix |
| `UnsettledFinalized` | `0x6f4528c508dc00c3d0fb4dcffe0346f48ae4332f18abe3d4eff0b27895997929` | `(uint256, address, address)` | abandonment counter (0 all-time) |
| `TopListingSet` | `0x24ace256adc6182b122f3aa90b19d20b6d637236a63154d9a6ceb9032b50b514` | `(uint256 indexed, address indexed)` | crown moves — **⚠ emitted in vacate+set PAIRS, dedupe** |
| `TopListingSettled` | `0x72747a194a7ea234ca6c67bae23a563ff193d2efe4611bec783df82b40c47892` | `(uint256 indexed, address indexed, uint256)` | crown payout leaderboard |
| `ConfigSet` | `0x150110afd46e9924086bf85c855aae25722518b293155bf0ae689dd99a2e88cc` | `(uint256 indexed key, uint256 value)` | parameter-drift watcher |

Remaining FWA core events (topic0 not individually recorded — derive from the ABI):

`NFTListed(uint256,uint256,address,address,uint256,uint256,uint256)` ·
`ListingStaged(...)` · `ListingWithdrawn(uint256,address,uint256)` ·
`BackingUpdated(uint256,address,uint256,uint256,uint256)` ·
`AcquisitionSequenced(uint256,uint64,uint64,uint256)` ·
`AcquisitionProcessed(uint256,uint64,uint8,address)` ·
`AcquisitionExpired(uint256,uint64,address,uint256)` ·
`AcquisitionRefundedNoListing` · `AcquisitionRefundedSlippage` · `AcquisitionRefundWithdrawn` ·
`NFTAllocated(uint256,uint256,address,address,uint256,uint256)` ·
`NFTDeliveryFailed(uint256,address,address,uint256)` · `StuckNFTRecovered(uint256,address)` ·
`TopListingFunded(uint256,uint256,uint256)` ·
`EarningsAccrued` · `EarningsWithdrawn` ·
`RandomnessCached` · `RandomnessTimedOut` · `VrfServiceFeePaid` ·
`FeesPaidOut(address,uint256)` ·
`CollectionWhitelistSet(address,bool)`

Satellite events: `FWARewards.ListingRewardRepriced` (hook `onListingRepriced(uint256,uint256)`) ·
`FWATokenHook.ExternalBuysEnabledSet(bool)` · `FWAWhitelist.BurnedForWhitelist(address,address,uint256[])` ·
`FWAWhitelist.TTTAmountSet(uint256)`.

### `ConfigSet` key map (from `src/FWAConfigKeys.sol`)

This turns one event topic into a complete parameter-drift widget.

| setUint | | | setBool | | setAddr | |
|---|---|---|---|---|---|---|
| 1 | `CALLBACK_GAS_LIMIT` | 16 | `TOP_THRESHOLD_BPS` | 40 `RETAINED_TO_PROTOCOL` | 60 | `VRF_COORDINATOR` |
| 2 | `VRF_SUB_ID` | 17 | `SETTLEMENT_DISCOUNT_BPS` | 41 `ACQUISITIONS_ENABLED` | 61 | `PAYOUT_ADDRESS` |
| 7 | `REQUEST_CONFIRMATIONS` | 18 | `OWNER_ACQUISITION_FEE_BPS` | 42 `WITHDRAW_ONLY` | 62 | `WHITELIST_MANAGER` |
| 10 | `MAX_ACTIVATIONS_PER_ACQUISITION` | 19 | `OWNER_SETTLEMENT_FEE_BPS` | 43 `WHITELIST_ENABLED` | 63 | `VRF_SERVICE` |
| 11 | `SELECTION_TIMEOUT_BLOCKS` | 20 | `SETTLEMENT_WINDOW` | 44 `ACCEPT_BID_AS_TOKENS_ENABLED` | | |
| 12 | `MAX_ACQUISITIONS_PER_TX` | 21 | `FINALIZE_WINDOW` | | | |
| 13 | `SURCHARGE_BPS` | 22 | `MIN_BACKING` | | | |
| 14 | `SELECTION_SLIPPAGE_BPS` | 23 | `PROTOCOL_FEE_TO_TOKEN_BPS` | | | |
| 15 | `TOP_LISTING_SHARE_BPS` | 24 | `VRF_KEY_HASH` | | | |
| | | 25 | `MAX_STAGED_LISTINGS` | | | |

### Historical scan cost

A full backfill of 9 event types across the **entire** protocol history took **58 seconds** keylessly
via `eth.drpc.org` at 10,000 blocks per request (~7 requests per event type). Via
`gateway.tenderly.co` there is no range cap at all. **A MaxPane data layer can realistically backfill
everything on first run and then tail incrementally.**

Measured all-time counts (deploy → block 25612716): 58,006 `AcquisitionRequested` · 51,522
settlements · 33 `TopListingSet` · 12 `TopListingSettled` (91.096 ETH paid) · 6 `ConfigSet` (plus the
launch write) · 51 unique collections in `CollectionWhitelistSet`.

---

## 9. Off-chain data sources

### 9.1 Project API — none exists

| Probe | Result |
|---|---|
| `https://www.fwa.fun/api/{activity,positions,pool,stats,listings}` | **all HTTP 404** |
| `https://www.fwa.fun/activity` | HTTP 200 HTML (41,823 B) — no embedded API or RPC references |
| `/llms.txt`, `/llms-full.txt`, `/sitemap.xml`, `/robots.txt` | **all HTTP 404** (Next.js SPA shell served with 404 status) |
| `/docs` | 307 → `/docs/overview` |

**Conclusion: the FWA data layer must be pure RPC + DexScreener/GeckoTerminal + DefiLlama.** Doc pages
are server-rendered, so plain `curl` + HTML strip works for research — no JS shell problem.

Doc slug map (labels do **not** match slugs):

| Nav label | Slug |
|---|---|
| How it works | `/docs/overview` |
| Deployments | `/docs/deployments` |
| Positions & weighting | `/docs/prizes-odds` |
| Pricing & allocation | `/docs/pricing-draw` |
| Collections | `/docs/collections` |
| Settlement | `/docs/winning` |
| Fees & protocol revenue | `/docs/fees` |
| Top deposit reward | `/docs/top-reward` |
| $FWA | `/docs/fwa` |
| Safety | `/docs/safety` |
| Parameters | **`/docs/config`** |
| Roles | `/docs/roles` |
| Deploy your own | `/docs/deploy` (🚧 Coming Soon, no content) |

`/docs/parameters`, `/docs/token`, `/docs/how-it-works`, `/docs/positions`, `/docs/settlement` all 404.

### 9.2 $FWA market data — keyless, confirmed working

**DexScreener** `https://api.dexscreener.com/latest/dex/tokens/0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845`

Returns exactly **1 pair**. Observed 2026-07-25:

| Field | Value |
|---|---|
| `chainId` / `dexId` / `labels` | `ethereum` / `uniswap` / `["v4"]` |
| `pairAddress` | `0x230ecd3c25b44af30db59c15f70df7794eb13f67a200f230b7400daa96fe804d` (**a v4 poolId**) |
| `quoteToken` | ETH (`0x0000…0000`) |
| `priceUsd` / `priceNative` | `0.03017` – `0.03114` / `0.00001610` – `0.00001662` ETH |
| `fdv` = `marketCap` | 30,174,653 – 31,144,901 USD |
| `liquidity.usd` / `.base` / `.quote` | 1,167,159 – 1,186,401 USD / 19,272,525 – 19,716,777 FWA / 305.48 – 312.82 ETH |
| `volume.h24` / `h6` / `h1` | 5,017,328 – 5,180,238 / 1,134,984 / 108,693 USD |
| `txns.h24` | **11,366–11,747 buys / 12,756–13,152 sells** |
| `priceChange.h24` | +50.32% |
| `pairCreatedAt` | 1784223815000 = **2026-07-16T17:43:35Z** |

⚠ Nonzero buys despite `externalBuysEnabled == false` — those are FWARewards-routed protocol buys.
Worth an explanatory footnote in the UI or it reads as a contradiction.

**GeckoTerminal** — accepts the v4 poolId directly:
`https://api.geckoterminal.com/api/v2/networks/eth/pools/0x230ecd3c…804d`

`data.attributes`: `base_token_price_usd` (0.0319594670947466), `base_token_price_native_currency`,
`fdv_usd` (31,959,467.09), `price_change_percentage{m5,m15,m30,h1,h6,h24}`,
`transactions{…}{buys,sells,buyers,sellers}`, `pool_created_at`, `name` = "FWA / ETH".
**⚠ `market_cap_usd` returns `"0.0"` — unusable, use DexScreener's `fdv`.**

### 9.3 OHLCV history — available, keyless

`https://api.geckoterminal.com/api/v2/networks/eth/pools/{poolId}/ohlcv/{timeframe}`

| Timeframe | Params | Candles returned | Shape |
|---|---|---:|---|
| `day` | `?limit=30` | **6** (pool age limited; oldest ts 1784505600) | `[ts, open, high, low, close, volume]`, newest first |
| `hour` | `?limit=100` | **100** | same — **best sparkline source** |
| `minute` | `?aggregate=15&limit=50` | **50** | same |

Hard ceiling: the pool was created 2026-07-16T17:43:35Z, so **~10 days of history** is all that
exists today. A daily chart will look sparse until ~August.

### 9.4 DefiLlama — keyless, works, but read the caveats

| Endpoint | Shape |
|---|---|
| `https://api.llama.fi/summary/fees/fake-world-assets?dataType=dailyFees` | `{name, slug, category:"Gamified Mining", chains:["Ethereum"], total24h, total7d, total30d, totalAllTime, change_1d, …chart}` |
| same URL, `dataType=dailyRevenue` / `dailyHoldersRevenue` / `dailySupplySideRevenue` | same shape |
| `https://api.llama.fi/protocol/fake-world-assets` | full protocol record; `defillamaId` 8292; `gecko_id` = null, `cmcId` = null |
| `https://api.llama.fi/tvl/fake-world-assets` | **a BARE NUMBER**, not a JSON object: `3211155.7353703226` |

Observed 2026-07-25 (USD):

| Series | 24h | 7d | 30d | All-time |
|---|---:|---:|---:|---:|
| dailyFees | 5,797,920 | 6,164,171 | 6,164,171 | 11,962,091 |
| dailyRevenue | 512,877 | 536,416 | — | 1,049,293 |
| dailySupplySideRevenue | 5,285,042 | 5,627,759 | — | 10,912,801 |
| dailyHoldersRevenue | **0** | **0** | **0** | **0** |

Daily fee chart points: `1784592000`=426,505 · `1784678400`=1,177,218 · `1784764800`=1,708,898 ·
`1784851200`=2,851,550 · `1784937600`=5,797,920.

DefiLlama's own methodology strings (useful for cross-checking a widget):
Fees = *"Acquisition fees (~10% surcharge over the pool's expected value) paid by NFT purchasers, plus
settlement fees taken from listing backings."*
Revenue = *"Team share of the protocol's cut of acquisition and settlement fees, plus any fees diverted
to FWA-token buybacks."*
HoldersRevenue = *"FWA-token buybacks funded from protocol fees."* (0 all-time — consistent with
`protocolFeeToTokenBps = 0` and `lastBuybackBlock() = 0`.)
SupplySideRevenue = *"Share of acquisition fees distributed to NFT depositors (equal split across active
listings plus the top-listing pot), plus the snapshot soulbound-NFT holders' share of protocol fees
via the Splitter."*

Derived stat worth a tile: **take rate = dailyRevenue / dailyFees = 8.8%** — one number that captures
the protocol's whole economic posture (~91% of fees flow to depositors, not the team).

⚠ **DefiLlama TVL ($3.21M) is far below the core contract's real ETH balance (2,340–2,551 ETH).** They
measure different things. **Prefer the onchain balance.**

### 9.5 Press (third-party, unverified)

CryptoBriefing, https://cryptobriefing.com/fake-world-assets-surpasses-collector-crypt-revenue/ —
*"roughly 2,000 ETH in transaction volume across approximately 90,000 total transactions"*,
*"around 35,000 individual purchases"*, within four days of the *"protocol relaunch: July 20"*.
Team = two people, Adam (@Rhynotic) and Teto (@tetonotsorry). Claims FWA is *"#1 by TVL"* in the
Gamified Mining category with *"94.7% of the $3.06m category total"*.

These are **superseded by direct event counts** (58,006 requests, 51,522 settlements) and should not
be used as data-layer inputs. No X/Twitter data was retrievable. No public Dune dashboard was found
(treat as a negative finding, not a confirmed absence — Dune search is not web-indexed).

---

## 10. Keyless NFT floor prices — ranked options + recommendation

This is **the weakest link in the whole data layer.**

| Rank | Source | Endpoint | Keyless? | Coverage of the 38 live FWA collections | Verdict |
|---|---|---|---|---|---|
| 1 | **CoinGecko NFT (per-contract)** | `https://api.coingecko.com/api/v3/nfts/ethereum/contract/{addr}` | ✅ | **22 OK / 11 hard 404 / 5 rate-limited 429** | Best available. Returns `floor_price.{native_currency,usd}`, `market_cap`, `volume_24h`, `floor_price_in_usd_24h_percentage_change`, `number_of_unique_addresses`, `total_supply`. Cross-checks: BAYC 8.75 ETH vs OpenSea 8.7471. **Harsh rate limit** — needed ≥2.5 s spacing and still hit 429s; 38 collections took **203 s**. |
| 2 | **OpenSea v2 (opportunistic)** | `https://api.opensea.io/api/v2/collections/{slug}/stats` | ⚠ partial | 200 for popular slugs, **401 for others** | Verified 200 without a key: ten-thousand-tokens 0.0514, boredapeyachtclub 8.7471, cryptopunks 32.42, nakamigos 0.12099729 — and survived 10/10 rapid calls. But milady-maker returned **401**, and `…/chain/ethereum/contract/{addr}` returned 401 for `0x8fe1a377…`. Behaves like CDN-cached popular collections leaking through. **Never a primary source; opportunistic gap-filler only.** |
| 3 | Reservoir | `https://api.reservoir.tools/collections/v7` | ❌ | — | **FULLY DEAD — DNS does not resolve** (`Could not resolve host: api.reservoir.tools`). ⚠ This is the floor source hardcoded at `maxpane_dashboard/data/ttt_client.py:62`, so **the existing TTT dashboard's floor feed is already broken.** |
| 4 | Magic Eden RTP | `https://api-mainnet.magiceden.dev/v3/rtp/ethereum/collections/v7?contract={addr}` | ❌ | — | HTTP 400 `"Not Found."` for both `?contract=` and `?id=` variants. Not a usable Reservoir replacement. |
| 5 | CoinGecko NFT bulk | `https://api.coingecko.com/api/v3/nfts/markets?asset_platform_id=ethereum&per_page=250` | ❌ | — | HTTP 401, `error_code 10005` — *"limited to PRO API subscribers"*. Only per-contract lookups are keyless. |

### The coverage gap is economically severe, not cosmetic

CoinGecko **404s** on:

| Missing collection | Positions | Share of selection weight |
|---|---:|---:|
| **Ten Thousand Tokens** | 1,732 | **49.083 %** |
| **Art Blocks Explorations** | 416 | **18.987 %** |
| CryptoPunks 721 (wrapper) | 3 | 0.000 % |
| fwogs, Wolf Game, Farmer, CryptoCitizens, Wrappers, PXL NET, glitch Gallery | — | — |

**The two largest weight buckets (~68% combined) have no CoinGecko floor.**

### Art Blocks nuance

A contract-level floor is **semantically wrong** for Art Blocks. `name()` on
`0x942BC2d3e7a589FE5bd4A5C6eF9727DFd82F5C8a` returns "Art Blocks Explorations", but OpenSea resolves
that same contract to slug `friendship-bracelets-by-alexis-andre` — **one contract hosts many distinct
collections with different floors**. Any per-contract floor for `0x942BC2d3…` or
`0xAB00000000002ADE39f58F9D8278a31574fFBe77` will be misleading.

### Recommendation

1. Use **CoinGecko per-contract** as the primary, refreshed on a slow background cadence (one
   collection per ~3 s, full sweep every ~15 min, persisted to a local snapshot). Never in the hot
   refresh path.
2. **Opportunistically** try OpenSea v2 for the collections CoinGecko 404s on, treat any 401 as a
   silent miss, and cache aggressively.
3. **Ship the backing-vs-floor widget with an explicit coverage caveat** ("floor available for 22 of
   38 collections; 68% of pool weight uncovered"). Do not compute a pool-wide "backing vs floor"
   aggregate — it would be dominated by the missing collections and would be wrong.
4. Suppress floors entirely for Art Blocks contracts, or label them "multi-collection contract — floor
   not meaningful".
5. Fix `ttt_client.py` at the same time (dead Reservoir + dead llamarpc + keyed Ankr).

---

## 11. Rate limits & caching guidance

| Concern | Guidance |
|---|---|
| **Public RPC batching** | publicnode 429s under aggressive batching. Batch **≤ 60 JSON-RPC elements** with ~0.12 s spacing, or use Multicall3 with **≤ 500 calls per `eth_call`** (which worked reliably). |
| **`eth_getLogs`** | publicnode and 1rpc **refuse it**. Use `gateway.tenderly.co/public/mainnet` (no cap) or `eth.drpc.org` (**paginate at 10,000 blocks**). |
| **Position sweep** | 3,867 positions = 17 `eth_call`s = **3.3 s**. Too heavy for a 15 s tick. Run on a **30–60 s** cadence, persist to a snapshot, and serve the hot tiles from cheap single reads (`acquisitionFee`, `activeListingCount`, `totalWeight`, `topListingId`, `topListingPot`). |
| **Hot tiles** | one Multicall3 batch of ~30 views across all 8 contracts — cheap enough for a **15 s** TTL. |
| **Event tail** | backfill once on first run (~58 s for the full history), then poll `lastSeen → latest` only. Persist by event topic, same pattern as `docs/tenthousandtokens_technical_findings.md`. |
| **CoinGecko NFT floors** | ≥ **2.5 s between calls** and still expect 429s. Background sweep only, **15 min TTL**, persist. |
| **DexScreener / GeckoTerminal** | 30 s TTL is plenty. |
| **DefiLlama** | 60 s TTL; daily granularity anyway. |
| **`quoteAcquisitionPrice`** | must carry an explicit `gasPrice` + bounded `gas`; treat as a hot tile with 15 s TTL. |
| **Block pinning** | pin `blockTag` for the whole position sweep + its invariant checks. Do **not** pin hot single reads. |

Suggested refresh tiers:

```
15 s  → hot Multicall3 batch (pool, price, crown, queue, emissions, gates)
60 s  → position sweep + aggregate invariant assertions + collection composition
60 s  → DexScreener / GeckoTerminal / DefiLlama
15 m  → CoinGecko NFT floor sweep (background, persisted)
tail  → event poll lastSeen → latest, every 30 s
```

---

## 12. OPEN QUESTIONS / UNVERIFIED

### 12.1 Claims the adversarial verifier **REFUTED** — do not carry these forward

| Refuted claim | Reality |
|---|---|
| "The ETH backing sets the position's weight" (proportional), from the original brief | **INVERSE.** `weight = 1e36 / backing`, proven against all 3,867 live positions with 0 mismatches. |
| "The $FWA pool is Uniswap V2" | **Uniswap v4**, addressed by poolId, with a custom hook. "V2 pair" in the docs is only a prose metaphor for the NFT+ETH pairing. |
| "Purchases are not live yet / 'Purchases Live Soon' / tolerate an empty pool / `acquisitionFee()` may be 0 or revert" | **Live and busy since block 25575879.** 58,006 acquisition requests; 1,327 in a single 500-block window. The landing-page widget reading was a client-render artifact, not protocol state. |
| "The live allowlist is the 16 documented launch collections" | **51 collections whitelisted onchain**, 38 with live positions, none blocked. Derive from `CollectionWhitelistSet` logs. |
| "`weightedBackingTotal` is the pool's total ETH backing / a DefiLlama TVL cross-check" | It is `Σ(weight × backing) ≈ activeListingCount × 1e36`. **Neither wei nor ETH.** |
| "Crown tithe is 5% (docs / source default 500)" | **Live 100 bps (1%)**, changed by the owner via `ConfigSet(key=15, value=100)` at block 25592190. Not stale docs — a real parameter change. |
| "`claimTopSpot()`" | Real signature is **`claimTopSpot(uint256 listingId)`**. |
| "No add/remove-backing function exists; backing is immutable for a listing's life" | **`updateBacking(uint256,uint256)` payable exists**, emits `BackingUpdated`, with the matching `FWARewards.onListingRepriced(uint256,uint256)` hook. |
| "Total purchase price = `acquisitionFee` + a nonzero VRF service fee" | The VRF fee read **0** at block 25612661 via `quoteAcquisitionPrice()`. Use the returned tuple; never assume nonzero. (Root cause disputed — see §12.2.) |
| Getters `surchargeBps()`, `whitelistEnabled()`, `minBacking()`, `protocolFeeToTokenBps()`, `INVERSE_WEIGHT_NUMERATOR()`, `accFeePerEV()`, `acquisitionsEnabled()`, `FWATokenHook.FEE_BIPS()`, `FWAToken.FEE_BIPS()`, `FWAToken.externalBuysEnabled()`, `FWA.activeCount()`, `FWARewards.emissionEnd()/startTime()/currentDay()` | **DO NOT EXIST.** Every one reverts on `eth_call`; none appears in the verified ABI or in selectors extracted from bytecode. They are source-level constants or private state described only in docs prose. **Derive instead:** surcharge = `acquisitionFee()/EV − 1`; `minBacking` / `whitelistEnabled` / `protocolFeeToTokenBps` / `ACQUISITIONS_ENABLED` / `WITHDRAW_ONLY` from `ConfigSet` history; the correct names are `activeListingCount()` and `FWATokenHook.externalBuysEnabled()`. |
| "DefiLlama `totalAllTime` includes pre-relaunch v1 fees" | The verifier found the arithmetic self-consistent (the 5-point daily chart sums to `totalAllTime`). The `total7d == total30d < totalAllTime` pattern is still unexplained but is **not** evidence of a v1 boundary. |

### 12.2 Genuinely unresolved

| # | Question | Why it matters | How to resolve |
|---|---|---|---|
| 1 | **Is the VRF service fee currently zero because the subscription is over-funded, or was every measurement an unset-`gasPrice` artifact?** Two agents disagreed: one measured 0.00104 ETH at 1 gwei, the other read 0 from `quoteAcquisitionPrice()` and cited `subscriptionNativeBalance()` = 31.38 ETH ≫ `minimumSubscriptionBuffer()` = 0.35 ETH. | Determines whether the purchase price tile shows one number or two | Call `quoteAcquisitionPrice()` and `FWAVRFService.requestFee()` at several explicit `gasPrice` values (0.1/1/10/50 gwei) in the same block and compare; read `FWAVRFService` source from Etherscan |
| 2 | **Exact VRF fee assembly formula.** Three components confirmed (800000 / 3000 bps / 0 wei) and they reconcile at 1 gwei, but whether an additional Chainlink premium term exists was not confirmed from source | Only matters if you want to predict the fee rather than read it | Read `src/FWAVRFService.sol` on Etherscan; otherwise always call `requestFee()` with an explicit gasPrice |
| 3 | **`tokenShareBps(uint256)` on FWARewards** was never called; the hot/cold interpolation is documented as linear between 60 s and 3600 s but the formula was not confirmed onchain | The hot/cold dial widget's accuracy | Call `tokenShareBps(gapSeconds)` at 0/60/1830/3600/7200 and check linearity |
| 4 | **`ListingStatus` / `AcquisitionStatus` enum values.** `status == 1` = Active empirically; values 2, 3, 4 seen but undefined | Correct labelling of non-active positions | Read the enum definitions in `src/FWA.sol` |
| 5 | **Why `FWAClaim` holds only 3,643,035.67 FWA against a stated 200,000,000 allocation (98.2% gone)** — genuine claiming or the owner exercising the documented `rescue`? | Affects any "circulating supply" narrative | Scan `Claimed` / `Rescued` / `Transfer` events on `0xd4085d38…` via `eth.drpc.org` |
| 6 | **Whether the v4 PoolManager's ~19.3–19.7M FWA is the residue of a 500,000,000 single-sided market allocation.** PoolManager is a singleton holding every v4 pool's tokens; the original placement was not verified | **Do NOT present 500,000,000 as "in the pool"** | Scan `Transfer` events into PoolManager from FWAToken deployment |
| 7 | **Whether the live whitelist contains collections beyond the 51 found.** Only `CollectionWhitelistSet` on FWA core was scanned; `FWAWhitelist`'s own `CollectionsSet` / `CollectionBlockedSet` events were not | Completeness of the collection registry | Scan FWAWhitelist events too, and `collectionWhitelisted()` any extras |
| 8 | **Exact deduction order for the `acquisitionTokenSlice`** (the dynamic hot/cold allowance) relative to the escrowed fee — the waterfall in `src/FWA.sol` L1668-1696 is confirmed, but how `acquisitionTokenSlice[requestId]` is *computed* at request time was not read | Accuracy of a revenue-waterfall widget | Read the request-side code path in `src/FWA.sol` |
| 9 | **Why DefiLlama TVL ($3.21M) diverges so sharply from the core contract's 2,340–2,551 ETH balance**, and what its `total7d == total30d < totalAllTime` pattern represents | Whether to show DefiLlama numbers at all | Compare DefiLlama's adapter source against onchain; prefer onchain regardless |
| 10 | **CoinGecko coin slug for $FWA.** A search result cites coin id `fake-world-assets` at $0.028505, but DefiLlama's protocol record returns `gecko_id = None` and `cmcId = None` | Only relevant if CoinGecko is wanted as a price fallback | `GET https://api.coingecko.com/api/v3/coins/fake-world-assets` before relying on it. **DexScreener is confirmed working and is the safer default.** |
| 11 | **Whether OpenSea's keyless behaviour is stable** or an artifact of CDN caching that could vanish without notice (10/10 rapid calls succeeded for one slug, 401 for another in the same session) | Whether the floor gap-filler can be depended on | Monitor over days; **do not build a hard dependency** |
| 12 | **Current floor prices for the 16 collections CoinGecko does not cover**, most importantly TTT (49.08% of weight) and CryptoPunks 721 | The backing-vs-floor widget | No fully-reliable keyless source found. OpenSea best-effort returned TTT 0.0514 ETH and cryptopunks 32.42 ETH — **treat as indicative, not a feed** |
| 13 | **`/docs/deploy`** is empty ("🚧 Coming Soon 🚧"), and the `/docs/deployments` subtitle promises "launch metadata" that the server-rendered HTML does not contain (no deploy blocks, no timestamps, no version tag) | Multi-deployment support is not yet a concern | Recheck later; only Ethereum mainnet is documented today |
| 14 | **No public Dune dashboard and no X/Twitter data** were obtainable. All press figures remain third-party unverified and are partly superseded by direct event counts | — | — |

---

## 13. Related resources

- Site: https://www.fwa.fun/ · Activity: https://www.fwa.fun/activity · Terms: https://www.fwa.fun/terms
- Docs index: https://www.fwa.fun/docs/overview (slug map in §9.1)
- Studio: https://token.works · https://x.com/token_works
- Etherscan (research only): https://etherscan.io/address/0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c#code
- DexScreener: https://dexscreener.com/ethereum/0x230ecd3c25b44af30db59c15f70df7794eb13f67a200f230b7400daa96fe804d
- DefiLlama: https://defillama.com/protocol/fake-world-assets
- MaxPane cross-reference: `docs/tenthousandtokens_technical_findings.md` (TTT — 49% of FWA pool weight,
  same creator EOA, and the token behind the dormant permissionless-whitelist path)

---

## 13. Corrections from WP-2 (ABI vendoring), 2026-07-27

Four corrections to the sections above, found while vendoring the verified ABIs and source.
Each was independently re-verified against mainnet or against the committed ABI files.

### 13.1 `collectionWhitelisted` lives on FWA **core**, not FWAWhitelist — CONFIRMED

`docs/fwa_work_packages.md` WP-2 grouped this getter under `fwa_whitelist`. Wrong.
Verified against the vendored ABIs:

- `fwa_core.json` → `collectionWhitelisted`, `CollectionWhitelistSet`, `CollectionNotWhitelisted`
- `fwa_whitelist.json` → write side only: `setCollections`, `CollectionsSet`, `CollectionBlockedSet`

**WP-6 and WP-7 must call it on `0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c`**, and derive the
allowlist from `CollectionWhitelistSet` logs emitted by **core**.

### 13.2 The `feeShare` contradiction — RESOLVED, PRD §7 rule 5 stands

`src/FWA.sol`'s `Listing` struct comments `feeShare` as "fee-distribution share key, √backing,
fixed at deposit", which would contradict the equal-split rule. Re-checked live:

```
activeListingCount()  = 5928
feeShareTotal()       = 5928
```

Equal at a non-trivial count, so `feeShare == 1` per position and **fees do split equally**.
The struct comment is stale or aspirational; the deployed behaviour is equal-split. Correctness
rule 5 and `per_position_credit()` are correct as specified. Do not "fix" them to √backing.

### 13.3 Three `ConfigSet` keys are constructor-only

Per `src/FWAConfigKeys.sol`, keys **1 (`CALLBACK_GAS_LIMIT`), 24 (`VRF_KEY_HASH`) and
63 (`VRF_SERVICE`)** are emitted through `ConfigSet` but rejected by `setUint`/`setAddr`. The §8
key table mis-groups them as settable. `abis/fwa/config_keys.json` carries a `settable` flag with
the correct values — read the flag, not the §8 table, so the parameter-drift widget does not imply
the owner can still change them. Keys 3-6 and 8-9 are intentionally unused (VRF pricing moved to
FWAVRFService before deployment).

### 13.4 `Listing` struct field is named `purchaser`, not `allocatee`

Same slot, same semantics; §4.2 uses the wrong name. `Position.allocatee` in `fwa_models.py` keeps
the model-side name deliberately — just don't expect the source to match.

### 13.5 Enums recovered — §12.2 item 4 is CLOSED

From `src/FWA.sol` L82-103, real names, not guesses:

| | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| `ListingStatus` | None | **Active** | Allocated | Withdrawn | Settled | Staged | — |
| `AcquisitionStatus` | None | Pending | Fulfilled | Expired | Refunded | Ready | TimedOut |

The empirically observed 2/3/4 = Allocated/Withdrawn/Settled, matching the earlier reading.

### 13.6 The pool is growing fast — never hardcode a count

`activeListingCount()` read **5,928** on 2026-07-27 against **3,867** during research on
2026-07-25: **+53% in two days.** Consequences:

- Every "3,867" in the PRD, plan and sections above is a *historical observation*, not a constant.
- The Multicall3 sweep is ~12 batched calls at current size, not ~8. WP-14's refresh-budget
  benchmark must size against the live count and headroom, not the research figure.
- All derived statistics (harmonic mean, arithmetic mean, the 4.0× gap, per-collection shares) have
  moved. Block-pinned fixtures remain valid for testing; live display must recompute.

This is the strongest possible argument for PRD §7 rule 6 — read everything from chain.

### 13.7 The "4.0× gap" is wrong AND is not a constant — SUPERSEDED

WP-4 could not reproduce the headline triple (harmonic 0.1247 ETH / arithmetic 0.5002 ETH /
gap 4.0×) from any other number in these docs, and traced why: §5 states total backing
1,827.63 ETH over 3,867 positions, which is 0.47262 ETH/position, not 0.5002. And
`1827.63 / 0.5002 = 3,653.8 ≈ 3,654` — the row count of the **unpinned, drifting scan that
§6.3 already flags as having failed its aggregate check.** The triple came from the bad sweep.

Re-measured live at block 25621114 (2026-07-27):

| Quantity | Value |
|---|---|
| `activeListingCount()` | 5,942 |
| `weightedBackingTotal()` | `5941999999999999999299301393240596379347` |
| `weightedBackingTotal / (count × 1e36)` | **1.000000** |
| harmonic mean = `weightedBackingTotal / totalWeight` | **0.106251 ETH** |
| `acquisitionFee` (recomputed, two floor divisions) | **0.116876 ETH** |
| `eth_getBalance(core)` | 2,203.760 ETH |
| arithmetic mean **upper bound** = balance / count | 0.370878 ETH |
| implied gap | **≤ 3.49×** |

Two conclusions:

1. **The gap is a live-varying ratio, not a constant, and it is currently ~3.5× — not 4.0×.**
   Never hardcode it, never assert it in a test, and never print it in prose. The odds board
   computes and renders whatever it is at the current block. PRD success criterion 3 is about
   making *the gap* legible, not a specific multiple.
2. **`weightedBackingTotal == count × 1e36` to six decimal places**, confirming both the
   inverse-weight rule and correctness rule 4 (it is a weight-scaled constant, not TVL).
   It also means the harmonic mean simplifies to `count × 1e36 / totalWeight`.

Note the arithmetic mean is only bounded, not measured: `eth_getBalance(core)` includes
acquisition escrow and accrued owner fees on top of position backing, so 0.370878 ETH is an
**upper** bound and the true gap is somewhat below 3.49×. A widget that wants the exact
arithmetic mean must sum `backing` across the pinned position sweep.

**Every appearance of 0.1247 / 0.5002 / 4.0× in the PRD, the implementation plan and §§1-12
above is superseded by this section.** They survive only as historical narrative.

### 13.8 Pinned distribution statistics — AUTHORITATIVE (supersedes §5 prose)

WP-3 captured all 3,867 backing values at block 25612701 with all three on-chain aggregate
invariants matching bit-for-bit. Four of the six prose statistics in `fwa_game_mechanics.md` §5
are wrong. The prose is also self-inconsistent: `0.5002 × 3,867 = 1,934 ETH`, which matches
neither its own stated total nor the measured one.

| Statistic | Prose (wrong) | Measured at 25612701 |
|---|---:|---:|
| min | 0.012 ETH | **0.015 ETH** |
| median | 0.15 ETH | 0.15 ETH ✅ |
| max | 221.0 ETH | 221.0 ETH ✅ |
| total | 1,827.63 ETH | **1,861.2933 ETH** |
| arithmetic mean | 0.5002 ETH | **0.481327 ETH** |
| harmonic mean | 0.1247 ETH | **0.123874 ETH** |
| **gap** | **4.0×** | **3.885×** |

The documented harmonic mean fails its own cross-check — `acquisitionFee / 1.1 = 0.12387`, not
0.1247. Two agents reached 0.123874 independently by different methods (WP-4 derived it from the
pinned aggregates; WP-3 measured it from the full distribution).

`tests/fixtures/fwa/backing_distribution.json` stores the measured values under `statistics`
(assert against these), the prose verbatim under `documented_statistics_from_prose` (marked
do-not-assert), and a `discrepancy_report`. TTT's 49.0828% weight share **is** reproducible from
the measured `by_collection` map, even though it is not derivable from the published aggregates.

### 13.9 VRF fee — OPEN QUESTION §12.2 Q1 IS SETTLED

The fee is **not** waived. Every zero reading was an unset-`gasPrice` artifact. Same block, only
`gasPrice` varied:

| `gasPrice` | VRF fee returned |
|---|---:|
| unset | 0 |
| 0.1 gwei | 0.000104 ETH |
| 1 gwei | 0.00104 ETH |
| 50 gwei | 0.052 ETH |

**The price tile must call `quoteAcquisitionPrice()` with an explicit gas price**, and the VRF leg
must be rendered from the returned tuple — never computed, never assumed zero.

Related negative result: §7's claim that `gasPrice` without a `gas` bound raises
`insufficient funds for gas * price` did **not** reproduce on Tenderly. Recorded so no downstream
test asserts on it. Keep bounding `gas` anyway — it costs nothing.

### 13.10 §3 is imprecise about publicnode and `eth_getLogs`

§3 records a flat "`eth_getLogs` ❌". The truth: publicnode serves `eth_getLogs` **fine inside
geth's ~128-block window** and refuses anything older via the archive gate. Practical guidance is
unchanged — use Pool B for logs — but **a client that capability-probes with a short range at
startup will wrongly conclude logs work on publicnode** and then fail on the first backfill.
Probe with an archive-depth range or do not probe at all.

`gateway.tenderly.co/public/mainnet` serves archive state keylessly; that is how both research
blocks were re-read live.

### 13.11 `ConfigSet` has 27 logs, not 6

21 are the launch write at a single block; **6 are genuine post-launch changes**. That reconciles
§8 exactly — the "only 6 ConfigSet events ever" claim meant six *changes*, not six logs. The
parameter-drift widget must filter out the launch block or it will report 21 spurious drifts on
first load.

### 13.12 Events reconstruct price history exactly — with one boundary rule

The first `AcquisitionRequested` in block N carries `acquisitionFee`/`totalWeight` matching state
at the **end of block N-1** bit-for-bit (verified on 7 of 8 consecutive blocks; the exception had
an earlier state-mutating tx in the same block). Comparing an event against the state at the end
of *its own* block yields a 0.017% error that reads like a rounding bug. Pin to N-1.
