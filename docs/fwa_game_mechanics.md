# Fake World Assets (FWA) — Protocol / Game Mechanics

Research notes for the planned MaxPane **FWA** dashboard (9th dashboard).

- **Project:** Fake World Assets — a parody of the "Real World Assets" (RWA) narrative
- **Studio:** TokenWorks (https://token.works · https://x.com/token_works) — the same studio behind
  Ten Thousand Tokens (TTT), for which MaxPane already ships a dashboard
- **Site:** https://www.fwa.fun/ · Docs: https://www.fwa.fun/docs/overview · Activity: https://www.fwa.fun/activity
- **Chain:** Ethereum mainnet (chain id 1)
- **Core contract:** `0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c` (`FWA`)
- **Token:** `0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845` (`$FWA`, ERC-20, 18 decimals, 1e27 fixed supply)
- **Research date:** 2026-07-25 (all live values pinned to mainnet blocks 25612655–25612716)

Companion file: `docs/fwa_technical_findings.md` (addresses, ABIs, endpoints, enumeration recipe).

---

## 1. What FWA is — the RWA parody framing

RWA protocols tokenize "real world assets" and wrap them in institutional language. FWA inverts the
joke: it takes **fake** world assets (JPEGs) and gives them the most literal financial primitive
possible — a fully pre-funded, irrevocable standing bid — then hands them out **at random**, like a
Japanese gachapon machine.

Official tagline (https://www.fwa.fun/docs/overview):

> "An onchain protocol where deposited NFTs, each backed by depositor ETH, become positions others
> acquire at random."

> "Fake World Assets is an onchain, randomized NFT acquisition protocol. Depositors list NFTs
> together with committed ETH backing, similar to a Uniswap V2 pair. That backing sets each
> position's selection weight and funds an irrevocable standing bid from the depositor to reacquire
> the NFT. Anyone can pay the pool-derived acquisition price to receive one randomly selected NFT
> position."

Two clarifications that matter for implementation:

| Common misreading | Reality |
|---|---|
| "Uniswap V2 pair" means there is a V2 pool | It is **only a prose metaphor** for the NFT+ETH pairing. There is no V2 pair anywhere in the protocol. |
| The $FWA token pool is V2 | The $FWA market is a **Uniswap v4** pool with a custom hook (`FWATokenHook`), addressed by **poolId**, not by a pair address. |
| More backing = drawn more often | **Inverse.** `weight = 1e36 / backing`. More backing = drawn *less* often. See §5. |

There is **one single global pool**. There is no per-collection pool, no per-collection price, no
per-collection weight multiplier. The only per-collection state anywhere is a boolean eligibility
mapping.

---

## 2. The three roles

From https://www.fwa.fun/docs/roles and /docs/overview:

| Role | What they do | What they put in | What they get |
|---|---|---|---|
| **Depositor** | Pairs an ERC-721 with committed ETH backing to create a *position* | An NFT + ETH (min 0.01 ETH) | An equal share of every acquisition fee while listed, √backing-weighted $FWA emissions, the crown pot if they hold the top deposit, and their backing back on exit |
| **Purchaser** | Pays the pool-derived acquisition price for **one randomly selected** position | ETH (acquisition fee + VRF service fee) | One randomly selected NFT position, then a settlement choice (keep / relist / sell back for 85% of backing in ETH or $FWA), plus a daily pro-rata $FWA pot and possibly a surcharge-funded $FWA buy allowance |
| **The protocol** | Sets bounded parameters, takes bounded cuts | Nothing | 1% of each acquisition fee, 1% settlement cut when the purchaser keeps the NFT, and the 15% retained settlement discount |

Docs, verbatim on the protocol role: *"It can tune parameters, but it cannot touch locked backing or
redirect accounted depositor ETH earnings."*

**Background processors are explicitly NOT a role**: *"Automation normally advances deferred requests,
but anyone can use the same public processor and no processor can provide randomness or skip request
order."*

**Stated depositor risk** (docs, /docs/overview): *"depositing provides liquidity to the protocol and
carries risk of loss. Your NFT can be selected earlier than its weight-implied average, ending its
earnings before fees have time to compound, so you can come out behind the cut you expected. FWA
rewards have no guaranteed value."*

---

## 3. Deposit lifecycle

```
pick NFT ──► listNFT(collection, tokenId) payable
              │
              ├─ collection eligibility checked (whitelistEnabled == true today)
              ├─ msg.value must be >= minBacking (0.01 ETH)
              │
              ▼
        STAGED (if VRF requests are open) ──► FIFO staging line
              │  activateListings(n) drains it once the queue is idle
              ▼
        ACTIVE  (status == 1)
              │  weight = 1e36 / backing, added to totalWeight
              │  feeShare = 1, feeDebt checkpointed  → earns from this point on
              │  eligible for the crown, earns √backing $FWA emissions
              │
              ├──► updateBacking(listingId, newBacking) payable  → reprices weight, may seize crown
              ├──► claimListingFees([ids]) / withdrawEarnings()  → pull accrued ETH
              │
              ├──► withdrawListing(listingId)   (depositor only; waits for open requests to clear)
              │       ► NFT + backing return to depositor, crown forfeited if held
              │
              └──► SELECTED by a VRF draw → ALLOCATED → see §4/§6
```

Key mechanics:

- **The backing does three jobs at once** (docs, /docs/prizes-odds): it funds the standing bid, it
  sets the selection weight, and it is the depositor's own returnable stake. *"It is the depositor's
  own capital, not a reward paid out alongside the NFT."*
- **Backing is segregated, never pooled.** *"Each position's ETH is tracked in its own per-position
  accounting slot and is never commingled with fee balances or other positions."* Solvency invariant:
  `Σ credited ≤ Σ collected`, with credits rounded conservatively.
- **Backing is mutable.** `updateBacking(uint256,uint256)` (payable) exists and emits
  `BackingUpdated`. Earlier readings of the docs implied backing was frozen for a listing's life —
  that is wrong.
- **FIFO staging.** *"New deposits made while requests are open wait in a first-in-first-out staging
  line, so later deposits and callback timing cannot alter an existing draw."* Staged positions carry
  no weight and earn nothing yet. Live: `reservedStagedCount()` = 23–30.
- **Custody.** NFTs move via standard `transferFrom` / `safeTransferFrom`. The protocol is
  collection-agnostic — *"Nothing in the core accounting cares which NFT a position holds."*
- **Only the depositor can withdraw.** *"The owner can never withdraw, move, or seize a depositor's
  pairing."*

---

## 4. Acquisition lifecycle (purchaser side)

```
quoteAcquisitionPrice()  ──► (poolFee, vrfFee, total)
        │
        ▼
acquire(maxAcquisitionFee, minWeightedValue [, maxNegativeSlippageBps]) payable
        │  ─ pool fee ESCROWED (not yet spent)
        │  ─ VRF service fee paid to FWAVRFService (nonrefundable once coverage bought)
        │  ─ overpayment returns immediately
        │  ─ reverts if the pool already moved past the caller's bounds
        ▼
AcquisitionRequested  ──► Chainlink VRF 2.5 request (native-payment, dedicated subscription)
        │
        │  Requests settle STRICTLY in creation order (FIFO). A later callback cannot jump ahead.
        │  If the callback cannot finish inline, processAcquisitions(n) advances the head —
        │  permissionless and unpaid; an approved operator may use a capped sponsored route.
        ▼
selection: P(position i) = weight_i / totalWeight
        ▼
NFTAllocated  ──► "Allocation doesn't transfer anything right away."
        │
        │  settlementWindow = 24h  (purchaser exclusive)
        │       ├─ keepNFT(id)                   → NFT to purchaser, backing (−1%) to depositor
        │       ├─ relistNFT(id) payable          → keep + relist atomically with fresh backing
        │       ├─ acceptDepositorBid(id)         → purchaser gets 85% of backing in ETH
        │       └─ acceptBidAsTokens(id, minOut)  → same 85%, delivered as $FWA
        │
        │  after 24h: the depositor may resolve
        │  after finalizeWindow = 7d: anyone may finalizeUnsettled(id)
        │       → default outcome: NFT to purchaser, backing to depositor
        ▼
settled
```

**Failure modes** (all three convert the escrowed pool fee into a *pull-based* refund credit;
the VRF service fee is never refunded):

| Mode | Trigger | Refund |
|---|---|---|
| Empty pool | Every position left before the request reached the head | Pool fee → `acquisitionRefundCredit` |
| Price drift | Another acquisition moved the price past the snapshotted bounds | Pool fee → credit, rather than settling at a stale price |
| Late / missing word | Deadline is **inclusive**; strictly afterwards *anyone* may expire the head request | Pool fee → credit; **VRF fee kept** (it bought callback coverage) |

Refunds are pulled with `withdrawAcquisitionRefund()`. Credit balances live in
`acquisitionRefundCredit(address)` / `acquisitionRefundCreditTotal()`. Pull-based by design so a
hostile recipient cannot block ordered processing.

**Anti-steering guarantee** (docs, /docs/safety): *"The selectable pool can mutate only after every
earlier request is terminal. An authenticated callback records an on-time word; the public processor
later advances ready requests in order."*

---

## 5. Positions & weighting — the inverse-weight core

Verbatim from https://www.fwa.fun/docs/prizes-odds, and confirmed against the verified Solidity
source and against all 3,867 live positions (0 mismatches):

```
INVERSE_WEIGHT_NUMERATOR = 1e36                       // solidity constant

weight_i  = 1e36 / backing_i                          // backing in WEI, integer floor division
totalWeight = Σ weight_i
P(select i) = weight_i / totalWeight
expected draws until position i is selected ≈ totalWeight / weight_i
```

> "A position's selection weight is inversely proportional to its committed backing. Pair an NFT with
> more ETH and it's selected less often; pair it with less and it's selected more. […] Because the
> bid is fully funded, a depositor can't make a position rarer or advertise a larger standing bid
> without committing more ETH."

> "Lightly-backed positions are common. You usually receive something small. The highest-backed
> positions are the rarest. A richly-backed NFT is selected rarely, so it tends to sit in the pool a
> long time."

- The numerator is *"sized far above any realistic backing so the division never rounds to zero."*
- Floor: `minBacking` = 0.01 ETH → max weight per position = `1e36 / 1e16` = `1e20`.
- **No cap on backing and no documented max-weight cap.**
- Every position has `feeShare = 1` regardless of backing (verified: `feeShareTotal() == activeListingCount()`).

### Live illustration (block ≈ 25612701)

| Collection | Positions | Total backing | Share of selection weight |
|---|---:|---:|---:|
| Ten Thousand Tokens | 1,732 | 966.91 ETH | **49.083 %** |
| Art Blocks Explorations | 416 | 42.15 ETH | 18.987 % |
| Nakamigos | 478 | 129.67 ETH | 8.707 % |
| fwogs | 210 | 26.05 ETH | 6.973 % |
| Otherdeed Expanded | 195 | 45.41 ETH | 4.033 % |
| VeeFriends Series 2 | 116 | 32.99 ETH | 2.402 % |
| Opepen Edition | 104 | 41.99 ETH | 1.793 % |
| Wolf Game | 45 | 5.89 ETH | 1.649 % |
| Farmer | 38 | 4.01 ETH | 1.514 % |
| Pudgy Penguins | 14 | 60.59 ETH | 0.011 % |
| CryptoPunks 721 | 3 | 137.10 ETH | **0.000 %** |
| Bored Ape Yacht Club | 3 | 28.80 ETH | 0.001 % |

That table *is* the protocol. The chase items hold enormous ETH and essentially never come out.

**Backing distribution across 3,867 live positions, measured at pinned block 25612701:**
min 0.015 ETH · median 0.15 ETH · max 221.0 ETH · total 1,861.2933 ETH ·
**arithmetic mean 0.481327 ETH vs harmonic mean 0.123874 ETH (3.885× gap)**.
The price tracks the harmonic mean — see §6.

> **Corrected 2026-07-27.** This paragraph previously read min 0.012 · total 1,827.63 ·
> arithmetic 0.5002 · harmonic 0.1247 · gap 4.0×. Four of those six were wrong — they came from
> an unpinned scan that failed its own aggregate check, and the set was self-inconsistent
> (`0.5002 × 3,867 = 1,934 ETH`, matching neither the stated nor the real total). The figures
> above are measured from the complete, invariant-verified distribution. **The gap is a live
> ratio and drifts** — a re-check two days later, after the pool grew 53%, put it at ≤3.49×.
> See `fwa_technical_findings.md` §13.7-13.8. Never hardcode it.

---

## 6. Pricing & allocation

Verbatim source, `src/FWA.sol` (verified on Etherscan):

```solidity
function acquisitionFee() public view returns (uint256) {
    if (totalWeight == 0) return 0;
    uint256 ev = weightedBackingTotal / totalWeight;
    return ev * (BPS + surchargeBps) / BPS;
}
```

```
EV              = weightedBackingTotal / totalWeight          // TWO sequential floor divisions
acquisitionFee  = EV * (BPS + surchargeBps) / BPS             // BPS = 10000, surchargeBps = 1000
                = 1.10 * EV
total quote     = acquisitionFee + vrfServiceFee              // via quoteAcquisitionPrice()
```

Because weights are inverse to backing, `weightedBackingTotal / totalWeight` **is the harmonic mean
of all backings** — dominated by the cheapest positions. Equivalent form: `EV = n / Σ(1/backing_i)`.

> "An acquisition costs roughly the average value of the position you might receive, plus a small
> acquisition surcharge (10% by default). […] Because the lightly-backed positions are the ones you
> almost always receive, the price tracks them, while the rare highest-backed positions barely move
> it." — https://www.fwa.fun/docs/pricing-draw

**Verified bit-exact at block 25612655:**
`weightedBackingTotal = 3890999999999999999275601332649457427323`,
`totalWeight = 31280618816683353089152`,
`EV = 124390122292745553 wei`,
`EV * 11000 // 10000 = 136829134522020108 wei` = `acquisitionFee()` — zero wei error.

### Request-time bounds

| Bound | Who sets it | Meaning |
|---|---|---|
| `maxAcquisitionFee` | purchaser (0 disables) | revert/refund if the pool fee exceeds this |
| `minWeightedValue` | purchaser (0 disables) | revert/refund if the pool's weighted value falls below this |
| `maxNegativeSlippageBps` | purchaser, 0–100% | downward fee drift tolerated before a refund credit is issued |
| `selectionSlippageBps` | **protocol**, 10% default, snapshotted per request | hard cap on upward fee drift |

---

## 7. The standing bid

Every position carries a **pre-funded, irrevocable standing bid** from its depositor to reacquire the
NFT. There is no bid expiry, no bid negotiation, and no way to advertise a bid you have not funded.

```
bid payout to the purchaser = backing * settlementDiscountBps / BPS      // 8500 bps = 85%
retained slice              = backing * (BPS - settlementDiscountBps)/BPS // 1500 bps = 15%
```

> "Accept the depositor bid. You sell the NFT back to its original depositor for the pre-funded
> standing bid: seller is you, buyer is the depositor, and the price is most of the backing, after a
> settlement discount (you receive 85% by default). The NFT returns to the depositor, and the slice
> you give up is that discount." — https://www.fwa.fun/docs/winning

> "You can never keep both the NFT and the ETH; accepting the bid requires transferring the NFT to
> the depositor."

**Naming trap:** the onchain getter is `settlementDiscountBps()` and it returns **8500**. That is the
*purchaser payout rate* (85%), **not** the 15% discount its name suggests. Labelling 8500 as "the
discount" in a widget inverts the economics.

The 15% retained slice goes to the protocol while `retainedToProtocol() == true` (live: true); if
flipped false it is shared back to depositors instead. **Purchaser proceeds are identical either
way.**

### Settlement outcomes (all-time, deploy block → 25612716)

| Outcome | Function | Events | Count | Share |
|---|---|---|---:|---:|
| Accept bid, settled as $FWA | `acceptBidAsTokens(uint256,uint256)` | `DepositorBidAcceptedAsTokens` | 38,083 | **73.92 %** |
| Accept bid, in ETH | `acceptDepositorBid(uint256)` | `DepositorBidAccepted` | 7,133 | 13.84 % |
| Keep and relist | `relistNFT(uint256)` payable | `NFTRelisted` | 3,934 | 7.64 % |
| Keep the NFT | `keepNFT(uint256)` | `NFTKept` | 2,372 | 4.60 % |
| Force-finalized by anyone | `finalizeUnsettled(uint256)` | `UnsettledFinalized` | 0 | 0.00 % |

51,522 settlements against 58,006 `AcquisitionRequested`. **~88% of purchasers sell the NFT straight
back**, and the overwhelming majority take $FWA rather than ETH. Only 4.6% keep the JPEG. Nobody has
ever been force-finalized.

Delivery semantics: `keepNFT` is **strict** (reverts on failure, so the purchaser can fall back to
accepting the bid). Every other resolution delivers best-effort and, on failure, emits
`NFTDeliveryFailed`, leaving the NFT claimable via `recoverStuckNFT` (success emits
`StuckNFTRecovered`).

---

## 8. Collections

The protocol is collection-agnostic by design: *"The long-term goal is for the protocol to support
every NFT collection, permissionlessly."* Today `whitelistEnabled` is **true**, so `listNFT` and
`relistNFT` both check a per-collection mapping.

**⚠ The docs page https://www.fwa.fun/docs/collections is materially stale.** It lists 16 launch
collections and warns *"The live onchain allowlist is authoritative and may change."* It has. The
live allowlist enumerated from `CollectionWhitelistSet(address,bool)` logs is **51 collections**, all
currently `true`, none blocked. **38 of them hold live positions.** One of the documented 16
(VeeFriends, `0xa3AEe8BcE55BEeA1951EF834b99f3Ac60d1ABeeB`) has zero live positions.

A dashboard must derive the collection list from `CollectionWhitelistSet` logs plus enumerated
positions — **never** from the docs page.

The 16 documented launch collections (all still `collectionWhitelisted() == true`):

| Collection (doc label) | Address | onchain `name()` if different |
|---|---|---|
| Ten Thousand Tokens | `0x26D7Ad0E930b54b84C00DAad077Ee31Ba9e2Fb2E` | |
| CryptoPunks 721 (wrapper) | `0x000000000000003607fce1aC9e043a86675C5C2F` | |
| Milady Maker | `0x5Af0D9827E0c53E4799BB226655A1de152A425a5` | `Milady` |
| Bored Ape Yacht Club | `0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D` | |
| Azuki | `0xED5AF388653567Af2F388E6224dC7C4b3241C544` | |
| Doodles | `0x8a90CAb2b38dba80c64b7734e58Ee1dB38B8992e` | |
| CrypToadz | `0x1CB1A5e65610AEFF2551A50f76a87a7d3fB649C6` | `Cryptoadz` |
| Pudgy Penguins | `0xBd3531dA5CF5857e7CfAA92426877b022e612cf8` | |
| Meebits | `0x7Bd29408f11D2bFC23c34f18275bBf23bB716Bc7` | |
| Checks | `0x036721e5A769Cc48B3189EFbb9ccE4471E8A48B1` | |
| MAX PAIN AND FRENS BY XCOPY | `0xd1169e5349d1cB9941F3DCbA135C8A4b9eACFDDE` | `MAX PAIN AND FRENS OPEN EDITION BY XCOPY` |
| XCORE | `0xC04E0000726ED7c5b9f0045Bc0c4806321BC6C65` | minimal proxy, 45 bytes of code |
| CryptoDickbutts | `0x42069ABFE407C60cf4ae4112bEDEaD391dBa1cdB` | `CryptoDickbutts S3` |
| VeeFriends | `0xa3AEe8BcE55BEeA1951EF834b99f3Ac60d1ABeeB` | zero live positions |
| mfers | `0x79FCDEF22feeD20eDDacbB2587640e45491b757f` | `mfer` (symbol MFER) |
| DeadFellaz | `0x2acAb3DEa77832C09420663b0E1cB386031bA17B` | |

Notable post-launch additions (subset of the 35 beyond the docs):
Nouns `0x9C8fF314C9Bc7F6e59A9d9225Fb22946427eDC03` · Nakamigos `0xd774557b647330C91Bf44cfEAB205095f7E6c367` ·
MutantApeYachtClub `0x60E4d786628Fea6478F785A6d7e704777c86a7c6` · Opepen Edition `0x6339e5E072086621540D0362C4e3Cea0d643E114` ·
Art Blocks `0xAB00000000002ADE39f58F9D8278a31574fFBe77` · Art Blocks Explorations `0x942BC2d3e7a589FE5bd4A5C6eF9727DFd82F5C8a` ·
CryptoCitizens `0xbDdE08BD57e5C9fD563eE7aC61618CB2ECdc0ce0` · Chimpers `0x307AF7d28AfEE82092aA95D35644898311CA5360` ·
Otherdeed Expanded `0x790B2cF29Ed4F310bf7641f013C65D4560d28371` · Koda `0xE012Baf811CF9c05c408e879C399960D1f305903` ·
Wolf Game `0xC7E67762821b2ED6c0a1F423547B2899822d8650` · VeeFriends Series 2 `0x9378368ba6b85c1FbA5b131b530f5F5bEdf21A18` ·
Rektguy `0xB852c6b5892256C264Cc2C888eA462189154D8d7` · Quirkies `0xD4B7D9bb20fA20dDADa9eCEf8a7355ca983cCCB1` ·
Wrappers `0xd716473C8Eb83A2102deF2B6390D9dfe74b2f580` · fwogs `0x8fe1a377B83921fe1429aDB1b8fbFECd45De9cd8` ·
Good Vibes Club `0xB8Ea78fcaCEf50d41375E44E6814ebbA36Bb33c4`

**Whitelist semantics:**
- Removing a collection **blocks only future listings**. Existing positions still allocate, settle
  and withdraw.
- `FWAWhitelist` supports **sticky owner blocking**, which prevents the permissionless path from
  re-adding a blocked collection.
- **TTT-funded permissionless path**: `burnToWhitelist(address collection, uint256[] tokenIds)` adds
  an unblocked collection after `TTT_AMOUNT()` Ten Thousand Tokens NFTs are irreversibly sent to
  `0x…dEaD`. **Live `TTT_AMOUNT() = 0`, so the path is still disabled.** The transfer is permanent
  and *"changes only the target collection's eligibility; it does not create a deposit or grant
  control over FWA."* This is a real, verifiable cross-link to the existing MaxPane TTT dashboard.

---

## 9. Fees, payment split, and protocol revenue

### 9.1 What a purchaser pays

```
purchaser pays = acquisitionFee (escrowed, refundable as a pull credit)
               + vrfServiceFee  (paid to FWAVRFService, NONREFUNDABLE once coverage is bought)
```

### 9.2 Acquisition waterfall — exact order from `src/FWA.sol` L1668-1696

This resolves the ambiguity in the prose docs. The order is:

```
1.  acquisitionFeePaid = acquisition.priceEscrowed
2.  slice        = acquisitionTokenSlice[requestId]        // dynamic hot/cold $FWA-buy allowance
3.  distributable = acquisitionFeePaid - slice
4.  ownerCut      = distributable * ownerAcquisitionFeeBps / BPS      // charged on fee MINUS slice
5.  distributable -= ownerCut
6.  if topListingId != 0:
        topShare = distributable * topListingShareBps / BPS           // crown tithe, AFTER owner cut
        topListingPot += topShare
        _distribute(distributable - topShare)
    else:
        _distribute(distributable)                                    // tithe folds back into the split
```

`_distribute` credits **equally across every active position** — `feeShare = 1` for all of them, so
per-position credit is `distributable / activeListingCount`, independent of backing. Accounting is a
dividend accumulator: `accFeePerEV` tracks fee-per-share and a **ceiled** `feeDebt` checkpoint at
deposit means a position only earns from acquisitions during its own tenure. Ceiling rounding keeps
`credited ≤ collected`.

> "Every acquisition fee, minus the protocol cut and the crown tithe […] is split equally across all
> active positions. Every position earns the same amount per acquisition, no matter its backing."
> — https://www.fwa.fun/docs/fees

**Nothing is burned at acquisition.** No part of the acquisition payment buys $FWA except the
purchaser's own surcharge-derived allowance.

### 9.3 Complete fee table

| # | Fee | Onchain identifier | Live value | Paid by | Received by | When |
|---|---|---|---|---|---|---|
| 1 | Acquisition surcharge | `surchargeBps` (no getter) | **1000 bps (10%)** | purchaser | split: depositor fee income + purchaser $FWA allowance | every acquisition |
| 2 | Protocol acquisition cut | `ownerAcquisitionFeeBps()` | **100 bps (1%)** | out of the fee | protocol (`accruedOwnerFees`) | every acquisition, after the token slice |
| 3 | Crown tithe | `topListingShareBps()` | **100 bps (1%)** — docs say 500 | out of the fee | `topListingPot` | every acquisition, after the owner cut, only while a crown exists |
| 4 | Protocol settlement cut | `ownerSettlementFeeBps()` | **100 bps (1%)** | depositor (from backing return) | protocol | only when the purchaser **keeps** the NFT |
| 5 | Settlement discount | `settlementDiscountBps()` = 8500 → 1500 bps retained | **15%** | purchaser (foregone) | protocol while `retainedToProtocol()==true`; else depositors | only when the purchaser **accepts the bid** |
| 6 | $FWA trading fee | `FEE_BIPS` (no getter) | **100 bps (1%)** on buys AND sells, LP fee 0 | trader | separate fee wallet, **not** the Splitter | every $FWA trade |
| 7 | VRF service fee | `serviceGasEstimate/serviceMarginBps/serviceFlatWei` | 800,000 gas / 3000 bps / 0 wei | purchaser | `FWAVRFService` | every acquisition request |
| 8 | Protocol-fee → $FWA buyback | `protocolFeeToTokenBps` (no getter) | **0 (off)** | — | recycled into buybacks instead of the payout | when enabled |

Derived amounts:

```
protocol acquisition revenue = distributable * 100 / 10000
crown tithe                  = (distributable - ownerCut) * 100 / 10000
per-position credit          = (distributable - ownerCut - topShare) / activeListingCount
depositor return, keep-NFT   = backing * (10000 - 100) / 10000       // depositor gets 99%
purchaser payout, accept-bid = backing * 8500 / 10000                // 85%
```

### 9.4 Protocol payout & the Splitter

`payoutFees()` is **permissionless** — anyone can push the accrued balance. Its destination on
mainnet is the `Splitter`. Live: `accruedOwnerFees()` = 3.4616 ETH awaiting a push.

```
ownerShareBps          = 7000  (70%)
nftShareBps            = 3000  (30%)
SECONDARY_OWNER_DIVISOR = 10

→ primary recipient   70% * 9/10 = 63%
→ secondary recipient 70% * 1/10 =  7%   (0x8e5963F8219789e90d8712609B216C31263317a3)
→ snapshot NFTs                    30%   (TokenWorks S02, 0xb33d806a94B6770C9d309E0842a75f8E6edCd5A6)

per-NFT share = (0.30 * received_ETH) / SNAPSHOT_SUPPLY
```

Live: `totalReceived()` = **720.688 ETH** cumulative protocol fee revenue (a hard onchain number,
better than any third-party estimate) · `SNAPSHOT_SUPPLY` = 264 · `MAX_TOKEN_ID` = 324 ·
`claimablePerToken()` = 0.818964 ETH · `pendingOwner()` = 295.099 ETH · `pendingSecondaryOwner()` =
32.789 ETH · `claimsClosed()` = false.

The split changes apply **only to future receipts**. The eligible id cap and active-supply
denominator are fixed at Splitter deployment; later mints and remints above the cap are excluded, and
a burned snapshot id cannot claim. `SWEEP_DELAY` = 31,536,000 s (1 year),
`SWEEP_AVAILABLE_AT` = 1815759815 (2027-07-16). The wind-down is an *earliest sweep time*, not an
automatic expiry; the first successful sweep permanently closes both holder and recipient claims.

---

## 10. $FWA tokenomics

`FWAToken` `0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845` — `name()` = "Fake World Assets",
`symbol()` = "FWA", `decimals()` = 18, `totalSupply()` = **1e27 = 1,000,000,000 FWA**, `launched()` = true.

### 10.1 Supply split — immutable, set at deployment

| Bucket | Share | Amount | Destination |
|---|---:|---:|---|
| Market | 50% | 500,000,000 FWA | single-sided Uniswap **v4** position (poolId `0x230e…804d`) |
| Emissions | 30% | 300,000,000 FWA | `FWARewards` — 150M depositors + 150M purchasers |
| Snapshot claims | 20% | 200,000,000 FWA | `FWAClaim`, Merkle-gated, snapshot at Ethereum block **25,452,023** |

> "The fixed FWA supply split (50% market / 30% emissions / 20% snapshot claims) and the 15-day,
> 1%-per-side daily emission schedule are set at deployment and cannot be changed afterward."
> — https://www.fwa.fun/docs/config

### 10.2 The launch buy-block — still active

> "The market charges a flat 1% on buys and sells. Sells stay open while outside buys are gated. The
> gate is owner-controlled and starts closed so early supply is earned through protocol use rather
> than bought by outside traders." Footnote: *"Sells always open; `externalBuysEnabled = false` until
> the protocol operator changes it; registered FWARewards buys may run while outside buys are
> closed."* — https://www.fwa.fun/docs/fwa

**Verified live 2026-07-25: `FWATokenHook.externalBuysEnabled()` = FALSE.** The gate lives on the
**hook**, not on the token (calling it on `FWAToken` reverts). Toggle:
`setExternalBuysEnabled(bool)`, event `ExternalBuysEnabledSet(bool)`.

This is why DexScreener reports ~11,400 "buys" in 24h despite the gate — those are
`FWARewards`-routed protocol buys (the purchaser $FWA allowance and the settle-as-FWA path), which
are exempt.

**Transfers are also restricted:** *"users can hold $FWA and trade it through the configured pool,
but cannot freely transfer it directly between ordinary wallets."* Footnote: *"Token transfers pass
only for mint/burn, configured distributor legs, and hook-authorized PoolManager flows."* $FWA is
**not** a free ERC-20. `getTransferAllowance()` = 0 live.

### 10.3 Emission schedule (live, verified)

| Field | Value |
|---|---|
| `EMISSION_DAYS()` | 15 |
| `EMISSION_DURATION()` | 1,296,000 s |
| `emissionStart()` | 1784574083 = **2026-07-20T19:01:23Z** (block 25575879) |
| Emission end | 1785870083 = **2026-08-04T19:01:23Z** |
| `depositorRatePerSec()` | 115740740740740740740 wei/s → ×86400 = **10,000,000 FWA/day** = 1% of supply |
| `purchaserDailyPot()` | 1e25 = **10,000,000 FWA/day** |
| Combined | 20,000,000 FWA/day = **2% of supply per day** |
| `currentEpoch()` | 5 (day 5 of 15 as of 2026-07-25) |
| `FWAToken.balanceOf(FWARewards)` | 210,411,718.88 FWA remaining of the 300M allocation |

Note `emissionStart` and the `ACQUISITIONS_ENABLED = 1` config write share the exact same second
(block 25575879) — emissions and the live protocol were switched on together.

### 10.4 Three earn paths

| Path | Who | Mechanism |
|---|---|---|
| **Dynamic surcharge split** | purchaser | The surcharge flexes with the time since the previous acquisition request. Cold pool → the whole surcharge becomes a $FWA-buy allowance for the next successful purchaser. Busy pool → it all goes to depositors as fee income. In between it slides. |
| **Depositor rewards, by √value** | depositor | `accTokenPerSqrt` accumulator over `sqrt(backing)`. *"Re-adds the size incentive the equal fee-split removes, but paid in $FWA so acquisition prices stay untouched."* Pauses when the pool is empty. |
| **Purchaser rewards, daily** | purchaser | Each day's 10,000,000 FWA pot is split pro-rata over that day's successful acquisitions. **Refunded acquisitions don't count.** |

Hot/cold interpolation (docs, /docs/fwa):

```
edge→$FWA share interpolates LINEARLY between
   hotGap  =   60 s   → 0%   to $FWA (all to depositors)
   coldGap = 3600 s   → 100% to the $FWA buy
overridable via forcedTokenShareBps  (-1 = dynamic, else 0..10000)
```

Live: `hotGap()` = 60, `coldGap()` = 3600, `forcedTokenShareBps()` = **-1 (dynamic)**.
The purchaser's buy is **pull-based** (`claimAccruedTokens` → `_buyTokens` inside `FWARewards` via a
v4 unlock) and happens **outside** the VRF callback. In withdraw-only migration mode an otherwise
unspendable allowance can be recovered as ETH via `withdrawTokenBuyAllowanceAsETH`.

### 10.5 Buyback — designed, currently dormant

> "In the intended steady-state phase after emissions, a configurable share of protocol fees can fund
> a buyback that is rate-limited and price-bounded, then routes it straight back to the two sides
> that keep the protocol alive: a slice to depositors (through the same √value rewards accumulator),
> a slice to purchasers (into the current day's pot), and a slice to burn, defaulting to 40% / 40% /
> 20%. The buyback is permissionless (anyone can poke it for a small caller bounty) and
> rate-limited."

Live on `FWAToken`: `routeDepositorBps()` = 4000, `routePurchaserBps()` = 4000, `routeBurnBps()` = 2000
(confirms 40/40/20) · `CALLER_REWARD_BPS()` = 50 (0.5% bounty) · `BUYBACK_DELAY_BLOCKS()` = 1 ·
`BUYBACK_INCREMENT()` = 1e18 · `buybackSqrtPriceLimitX96()` = 477782542051216404772491119593238 ·
**`lastBuybackBlock()` = 0 — no buyback has ever executed.** Burn address `0x…dEaD` holds 0 FWA.
Gated by `protocolFeeToTokenBps` which is 0.

`totalSupply()` reads exactly 1e27 today, but the design is deflationary once buybacks turn on.
**Read it live; do not hardcode.**

### 10.6 Claim contract

`FWAClaim` `0xd4085d38855F17EdF0B1CCBFad7B3846fb305655` — `claimsEnabled()` = true,
`merkleRoot()` = `0x304c5bafbde1693914071ed4981f750f846f9963cb0cec3914bf7bf02d17a1af`,
functions `claim(uint256,bytes32[])`, `claimed(address)`, `rescue(address,uint256)`.
The claim owner controls the root, the enabled flag, and rescue of unclaimed tokens.
No conventional linear vesting contract exists anywhere in the protocol.

---

## 11. Top deposit reward — "the crown"

This is the single most game-like mechanic and the natural hero stat.

> "The crown is a challenge against the current holder, not a continuously ranked leaderboard. […]
> The contract does not scan for or automatically backfill the absolute largest deposit, so a vacant
> crown can be claimed by any active position and a slightly larger position may still fall short of
> the takeover threshold." — https://www.fwa.fun/docs/top-reward

State is a single `topListingId` (0 = vacant) plus a running `topListingPot`.

**Takeover test** (from source `_beatsTop`):

```
value * BPS  >=  listings[topListingId].value * (BPS + topThresholdBps)
with topThresholdBps = 1000  →  challenger backing >= 1.10 × incumbent backing
```

Triggered automatically on activation or on a `updateBacking` value-raise, or explicitly via
`claimTopSpot(uint256 listingId)`. **Note the signature takes a listing id** — a bare
`claimTopSpot()` does not exist. `claimTopSpot` is a no-op if you already hold the crown (the guard
is load-bearing: it prevents you wiping your own pot).

| Event | Signature | Meaning |
|---|---|---|
| `TopListingSet` | `(uint256 indexed listingId, address indexed depositor)` | crown moved |
| `TopListingFunded` | `(uint256 indexed listingId, uint256 amount, uint256 newPot)` | tithe added |
| `TopListingSettled` | `(uint256 indexed listingId, address indexed depositor, uint256 amount)` | pot paid out |

**Payout rule:** *"When the crowned deposit leaves the pool or is overtaken, the pot earned during
its tenure pays out to its depositor. […] Lowering or withdrawing forfeits it and settles the pot."*
With no crown, *"the tithe just folds back into the equal split, so nothing is lost."*

**Live crown history** (deploy block 25546799 → 25612716, keyless log scan):
33 `TopListingSet`, 12 `TopListingSettled`, **91.096 ETH total pots paid out**.
Largest single pot **38.400795 ETH** (listing 13024, block 25605461). Next: 19.688061 ETH
(listing 4702), 12.883555 ETH (listing 45152). All three went to
`0x60ceef10f9dd4a5d7874f22f461048ea96f475f6`, who has won the crown **4 times**.

⚠ **Every takeover emits a PAIR of `TopListingSet` events** — first `listingId=0 / address(0)` to
vacate, then the new holder. Dedupe on that or you will double-count crown reigns.

A genuine leaderboard *can* be synthesized from `TopListingSettled` even though the live mechanic is
a single-holder crown.

---

## 12. Parameters — defaults, live values, bounds

Source: https://www.fwa.fun/docs/config (23 published parameters) plus live reads.
`BPS = 10000`. Percent ranges are basis points.

| # | Parameter | Config key | Doc default | **Live value** | Allowed range | Contract |
|---|---|---:|---|---|---|---|
| 1 | Acquisition surcharge | 13 `SURCHARGE_BPS` | 10% | **1000 bps** | any nonneg bps; **no contract cap** | FWA |
| 2 | Crown tithe | 15 `TOP_LISTING_SHARE_BPS` | 5% | **100 bps (1%)** ⚠ changed | 0–100% of the distributable fee | FWA |
| 3 | Crown threshold | 16 `TOP_THRESHOLD_BPS` | 10% | **1000 bps** | 0–100% over the current crown value | FWA |
| 4 | Depositor bid rate | 17 `SETTLEMENT_DISCOUNT_BPS` | 85% to purchaser | **8500 bps** | 50–100%, not below the protocol settlement cut | FWA |
| 5 | Retained-to-protocol | 40 `RETAINED_TO_PROTOCOL` | on | **true** | on/off | FWA |
| 6 | Protocol acquisition cut | 18 `OWNER_ACQUISITION_FEE_BPS` | 1% | **100 bps** | 0–100% of the pool acquisition fee | FWA |
| 7 | Protocol settlement cut | 19 `OWNER_SETTLEMENT_FEE_BPS` | 1% | **100 bps** | 0% – current depositor bid rate | FWA |
| 8 | Positive settlement slippage | 14 `SELECTION_SLIPPAGE_BPS` | 10% | **1000 bps** | 0–100% | FWA |
| 9 | Negative settlement slippage | — (per request) | 10% | purchaser-chosen | 0–100% **per purchaser** | FWA |
| 10 | Request confirmations | 7 `REQUEST_CONFIRMATIONS` | 3 blocks | **3** | 3–200 blocks | FWA |
| 11 | VRF service fee | — | 800k gas / 30% / 0 flat | **800000 / 3000 bps / 0 wei** | owner-set gas estimate, margin, flat wei | FWAVRFService |
| 12 | Selection timeout | 11 `SELECTION_TIMEOUT_BLOCKS` | 30 blocks | **30** | confirmations+2 … 7,200 blocks | FWA |
| 13 | Settlement window | 20 `SETTLEMENT_WINDOW` | 24 h | **86400 s** | 0 s – current finalize window | FWA |
| 14 | Finalize window | 21 `FINALIZE_WINDOW` | 7 d | **604800 s** | current settlement window or longer; no cap | FWA |
| 15 | Min backing | 22 `MIN_BACKING` | 0.01 ETH | **1e16 wei** | any nonneg wei; 0 disables | FWA |
| 16 | Cold-gap edge band | — | 1 min / 60 min | **60 s / 3600 s** | any two second values, hot < cold | FWARewards |
| 17 | Forced edge split | — | dynamic | **-1 (dynamic)** | -1 dynamic, or 0–100% to force the $FWA share | FWARewards |
| 18 | External $FWA buys | — | gated (off) | **false** | on/off (sells always open) | FWATokenHook |
| 19 | Protocol-fee → $FWA | 23 `PROTOCOL_FEE_TO_TOKEN_BPS` | 0% (off) | **0** | 0–100% of accrued protocol fees | FWA |
| 20 | Mainnet protocol-fee split | — | 63 / 7 / 30 | **7000 owner / 3000 nft, div 10** | 0–100% owner-side share, future receipts only | Splitter |
| 21 | Buyback routing split | — | 40 / 40 / 20 | **4000 / 4000 / 2000** | three shares summing to 100% | FWAToken |
| 22 | Buyback price floor | — | ~10% launch-price tolerance | `sqrtPriceLimitX96` = 477782542051216404772491119593238 | owner-updated sqrt-price limit | FWAToken |
| 23 | Settle-as-$FWA | 44 `ACCEPT_BID_AS_TOKENS_ENABLED` | on | **true** | on/off | FWA |
| 24 | Callback gas limit | 1 `CALLBACK_GAS_LIMIT` | — | **900000** | — | FWA |
| 25 | Acquisitions enabled | 41 `ACQUISITIONS_ENABLED` | starts 0 | **1 since block 25592194** | on/off | FWA |
| 26 | Withdraw-only mode | 42 `WITHDRAW_ONLY` | off | **never set (false)** | on/off | FWA |
| 27 | Whitelist enabled | 43 `WHITELIST_ENABLED` | on | **true** | on/off | FWA |
| — | **Immutable** | — | 50/30/20 supply split; 15-day, 1%-per-side emission schedule | **cannot be changed** | — | FWAToken / FWARewards |

Docs closing note: *"Low-level processing settings—such as staging batch sizes, callback gas budgets,
and keeper transaction policy—are intentionally omitted here; they do not change participant
economics or request order."* So more onchain params exist than the 23 published.

### Parameter change history — only 6 `ConfigSet` events since deployment

| Block | Key | Value | Meaning |
|---|---|---|---|
| 25546799 | 62 | address | `WHITELIST_MANAGER` set |
| 25546799 | 61 | address | `PAYOUT_ADDRESS` set (→ Splitter) |
| 25575879 | 41 | 1 | **acquisitions ENABLED** (same second as `emissionStart`) |
| 25592182 | 41 | 0 | acquisitions paused |
| 25592190 | 15 | 100 | **crown tithe 500 → 100 bps** |
| 25592194 | 41 | 1 | acquisitions re-enabled |

(The launch config write at deploy block 25546793 set the full initial parameter set; the 6 above are
the subsequent changes. The tithe change was bracketed by a deliberate pause/resume.)

**⚠ Docs-vs-onchain contradiction, resolved:** the docs and the Solidity source both declare
`topListingShareBps = 500` (5%). The **live value is 100 (1%)**, changed by the owner at block
25592190. This is an owner parameter change, not stale docs. **A dashboard must use the live value.**

---

## 13. Roles, admin powers, and safety

### Admin powers (verbatim, https://www.fwa.fun/docs/safety)

> "Admin powers are contract-specific. Owners can pause operations, tune bounded settings, manage
> market and claim gates, and configure future fee routing. **They cannot withdraw a depositor's
> escrowed NFT or backing, or redirect accounted depositor and purchaser ETH credits.** Token rewards
> are administered separately: in withdraw-only migration mode, after open requests clear, the
> rewards owner can move remaining reward supply to a replacement deployment, so an announced claim
> window matters. On mainnet, the independent splitter owner also controls the split for future
> receipts and may close claims and sweep residue after one year."

### Governance risk

The protocol owner is a **plain EOA, not a multisig and not a timelock**:

```
FWA.owner() == FWAWhitelist.owner() == Splitter.owner() == FWAClaim.owner()
            == FWATokenHook.feeAddress()
            == 0x019817aD02a31B990433542097bE29D97613E8Cb
eth_getCode(0x019817aD…) == 0x   (zero bytes → EOA)
```

Note: this is the **same address** as the Ten Thousand Tokens creator recorded in
`docs/tenthousandtokens_technical_findings.md`. All contracts use Solady `Ownable` with the two-step
handover pattern (`requestOwnershipHandover` / `completeOwnershipHandover` / `ownershipHandoverExpiresAt`).

### Safety mechanisms

| Mechanism | Behaviour |
|---|---|
| **Depositor-only withdrawal** | *"A position's NFT and its ETH backing can only ever be withdrawn by the depositor who paired them."* Active exits wait until every issued acquisition is terminal, bounded by each request's fixed word deadline. |
| **Loading phase** | *"The pool deploys with acquisitions off, so positions can be stocked before the protocol goes live."* (`ACQUISITIONS_ENABLED` starts 0.) |
| **Pause / emergency exit** | *"The team can halt acquisitions and new deposits. Already-issued requests must still process or expire; then active positions may exit normally. Staged positions cannot be cancelled: once the queue is idle, anyone can activate them and the depositor can withdraw through the normal path."* Pause does **not** freeze withdrawals and cannot seize escrow. |
| **Ordered anti-steering** | Requests settle in creation order; new deposits wait in a FIFO staging line; a missing request expires after its fixed deadline. Head-of-line blocking is real but bounded by `selectionTimeoutBlocks` = 30 (~6 min at 12 s/block). |
| **Whitelist circuit breaker** | Gates only new listings and relists; existing positions, allocations and settlements remain usable. |
| **Minimum backing** | *"a floor that keeps dust positions from distorting prices and selection weights."* |
| **Reentrancy hardening** | Solady `ReentrancyGuard` (`nonReentrant` on state-changing entry points) with effects-before-interactions ordering. |
| **Non-blocking ETH sends** | `SafeTransferLib.forceSafeTransferETH`, which the recipient cannot revert. |
| **Pull-based refunds** | Expiry, empty-pool and slippage refunds accrue in `acquisitionRefundCredit` and are pulled with `withdrawAcquisitionRefund`, *"so a hostile recipient cannot block ordered processing."* |
| **Best-effort NFT delivery** | Failure emits `NFTDeliveryFailed`; the NFT stays claimable via `recoverStuckNFT`. `keepNFT` alone is strict. |
| **Solvency by construction** | `Σ credited ≤ Σ collected`, enforced by conservative (ceiling) rounding. |

---

## 14. Strategy considerations

### 14.1 What a depositor optimizes

A depositor is a **liquidity provider whose position has a random, weight-determined lifetime**.

```
expected lifetime, in acquisitions ≈ totalWeight / weight_i = totalWeight * backing_i / 1e36
expected fee income  ≈ expected_lifetime * (distributable_per_acquisition / activeListingCount)
```

Because every position earns the **same** fee per acquisition regardless of backing, but a
higher-backed position **survives more acquisitions**, expected ETH fee income scales roughly with
backing — purely through duration, not through share size. Docs, /docs/fees: *"On average, the larger
the backing, the more ETH the position earns over its lifetime, purely because it sticks around
longer."*

Levers:

| Lever | Effect |
|---|---|
| **Backing size** | Higher backing → lower weight → longer expected tenure → more fee accruals, plus larger √backing $FWA emissions and crown eligibility. Costs more locked capital and raises the standing-bid obligation. |
| **Backing vs floor** | The depositor is short an option: if `0.85 × backing > collection floor`, a rational purchaser sells the NFT straight back and the depositor pays 15% of backing for the privilege of keeping a JPEG they already owned. If `0.85 × backing < floor`, the purchaser keeps it and the depositor gets 99% of backing back — effectively a floor-price sale. **The break-even is `backing = floor / 0.85 = 1.1765 × floor`.** |
| **Timing / duration risk** | The headline risk: *"selected earlier than its weight-implied average, ending its earning life before fees and rewards have much time to compound."* Variance is highest for lightly-backed positions. |
| **Crown play** | Post 1.10× the incumbent's backing to seize the crown and accrue the 1% tithe from every acquisition during your tenure. Historically worth 38.4 ETH in a single reign. Lowering or withdrawing forfeits and settles the pot. |
| **Fee dilution** | Every new position dilutes the equal split. `activeListingCount` is the denominator — 3,867 today. Track it. |
| **Emission clock** | √backing $FWA emissions **stop 2026-08-04T19:01:23Z**. After that only the ETH fee split remains, materially changing depositor returns. |
| **Repricing** | `updateBacking` lets a depositor re-tune weight and bid without unwinding — cheaper than withdraw + relist. |

### 14.2 What a purchaser optimizes

A purchaser is buying **one draw from the harmonic-mean distribution at a 10% markup**.

```
you pay      = 1.10 × harmonic_mean(backings)  +  vrfServiceFee
you receive  = one position, drawn ∝ 1/backing
              → best case: keep the NFT (worth ≈ collection floor)
              → or:        sell it back for 0.85 × that position's backing
```

The structural edge and the structural drag:

| Factor | Direction | Live magnitude |
|---|---|---|
| **Harmonic vs arithmetic gap** | ➕ | harmonic 0.123874 ETH vs arithmetic 0.481327 ETH — a **3.885× gap** at block 25612701, and a *live ratio* that must be recomputed, never hardcoded. The pool holds far more ETH than the price implies. The gap is the option value in the tail. |
| **Surcharge** | ➖ | flat 10% fee drag on every pull |
| **Settlement discount** | ➖ | selling back returns only **85%** of that position's backing — a further 15% haircut on the exit most purchasers actually take |
| **Combined round-trip if you always sell back** | ➖ | `0.85 × drawn_backing / (1.10 × harmonic_mean)`. At the harmonic mean itself that is `0.85/1.10 = 0.773` — you lose ~23%. **Buying to immediately sell back is negative-EV by construction; you must be drawing above-mean positions or valuing the $FWA rewards.** |
| **$FWA rewards** | ➕ | daily pot 10,000,000 FWA split pro-rata over that day's successful acquisitions, plus the hot/cold surcharge allowance. **This is what makes the round trip work while emissions run.** 73.92% of settlements taking the $FWA exit is the market confirming it. |
| **Hot/cold timing** | ➕ | buy after a long gap (approaching `coldGap` = 3600 s) and the **entire** surcharge becomes your $FWA buy allowance instead of depositor income. This is a directly exploitable, publicly observable edge. |
| **Chase upside** | ➕ | `max_backing × 0.85 / acquisitionFee` = "jackpot ratio". At 221 ETH max backing and a 0.1363 ETH fee that is a **~1,378× best-case payout** — at a probability of `1e36/221e18 / totalWeight` ≈ 1.45e-7. |
| **Slippage bounds** | ➕ | set `maxAcquisitionFee` / `maxNegativeSlippageBps` tightly; a refused settle becomes a pull credit, and only the VRF fee is lost |
| **Queue risk** | ➖ | strict FIFO; a stalled head request blocks you until anyone expires it after 30 blocks |

**Backing-vs-floor spread is the purchaser's real signal.** Positions where the drawn backing's 85%
exceeds that collection's floor are "rational sell-back" and churn fast; positions where the floor
exceeds 85% of backing are worth keeping. Since selection is inverse to backing, a purchaser cannot
target these — but the *aggregate* composition of the pool tells them whether the current price is
mispriced relative to real NFT value.

### 14.3 Weight share is a zero-sum game between depositors

`P(select i) = weight_i / totalWeight`. A depositor who wants a longer tenure must raise backing, but
every *other* depositor lowering theirs raises their own weight and lowers everyone else's expected
tenure. The composition is therefore unstable and worth charting over time.

---

## 15. Dashboard implications (summary)

- **Live and busy.** 58,006 acquisition requests, 51,522 settlements, 3,867 active positions,
  ~2,551 ETH held in the core contract, 720.7 ETH cumulative protocol revenue. Historical backfill is
  cheap (the protocol is only ~66,000 blocks old).
- **Signature visual:** harmonic vs arithmetic mean backing (a live gap, ~3.9× when measured) and the inverse-weight
  composition table (TTT 49% of odds vs CryptoPunks 0.000% of odds on 137 ETH of backing).
- **Hero stat candidate:** the crown — a single-holder, 1.10×-takeover, ETH-denominated pot, with a
  real 91 ETH payout history and a synthesizable leaderboard.
- **Hard countdown:** emissions end **2026-08-04T19:01:23Z**. The dashboard should degrade
  gracefully after that (rewards go to zero, only fees remain).
- **Binary state flags worth a badge each:** `externalBuysEnabled` (false — the biggest scheduled
  token event), `ACQUISITIONS_ENABLED` (true), `protocolFeeToTokenBps` (0 — buybacks dormant),
  `TTT_AMOUNT` (0 — permissionless whitelist path disabled), `retainedToProtocol` (true).
- **Cross-link:** TTT is both the largest weight bucket (49%) and the permissionless whitelist token,
  and the FWA owner is the TTT creator. MaxPane already ships a TTT dashboard.
- **Weak spot:** keyless NFT floor prices. See `docs/fwa_technical_findings.md` §9 — the two largest
  weight buckets (TTT 49.08%, Art Blocks 18.99%) have no reliable keyless floor source.
