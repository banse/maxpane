# FWA Ecosystem Dashboard — Research and Chain Validation

**Project:** Fake World Assets ecosystem (`$FWA`)
**Chain:** Ethereum mainnet (`chainId = 1`)
**Research date:** 2026-08-28
**Reference block:** `25,849,738` (`2026-08-27T23:05:23Z`)
**Block hash:** `0x33634e81dda7593a761b5c221ea2961ba6b0afebc881f670a92f72535cca76e1`
**Status:** Research complete; live values are observations, never application constants

This document extends the purchaser-focused research in
[`fwa_game_mechanics.md`](fwa_game_mechanics.md) and
[`fwa_technical_findings.md`](fwa_technical_findings.md). It covers the platform,
`$FWA` tokenomics, rewards, FWAIR drops, and independently deployed products that use
FWA. The official documentation was read first; every dashboard-critical live or mutable
claim below was then checked against deployed bytecode, verified ABIs where available,
direct calls, or event logs.

## 1. Research contract

The dashboard must remain:

- read-only and keyless;
- chain-first for live state;
- explicit about measured, derived, and estimated values;
- independently degradable by source group;
- honest that there is no canonical onchain registry of every project built on FWA.

Source precedence:

```text
block-pinned contract state
  > paged contract logs
  > verified source and ABI
  > first-party project API
  > first-party documentation
  > third-party market metadata
```

Documentation explains intended mechanics. It is not the source of current values.
First-party APIs are useful indexes, but a dashboard metric remains provisional until its
contract address and accounting invariants match the chain.

## 2. Official system model

Primary documentation:

- [Overview](https://www.fwa.fun/docs/overview)
- [Deployments](https://www.fwa.fun/docs/deployments)
- [Positions and odds](https://www.fwa.fun/docs/prizes-odds)
- [Pricing and draw](https://www.fwa.fun/docs/pricing-draw)
- [Settlement](https://www.fwa.fun/docs/winning)
- [Fees](https://www.fwa.fun/docs/fees)
- [Top-listing reward](https://www.fwa.fun/docs/top-reward)
- [`$FWA`](https://www.fwa.fun/docs/fwa)
- [FWAIR launches](https://www.fwa.fun/docs/fwair-launch)
- [Collections](https://www.fwa.fun/docs/collections)
- [Safety](https://www.fwa.fun/docs/safety)
- [Parameters](https://www.fwa.fun/docs/config)
- [Roles](https://www.fwa.fun/docs/roles)
- [Known ecosystem projects](https://www.fwa.fun/docs/testnet)

The protocol is an inverse-weighted NFT acquisition market:

1. A depositor escrows an allowlisted NFT and ETH backing.
2. Backing creates a standing bid and inverse draw weight: `weight = 1e36 / backing`.
3. A purchaser requests a Chainlink-VRF draw and receives one position.
4. The purchaser keeps/re-lists the NFT or accepts the standing bid in ETH or `$FWA`.
5. Acquisition, settlement, reward, and trading flows feed participants and the token.

The ecosystem layer adds two distinct categories:

- **FWA-native launches:** FWAIR campaigns escrow collections, collect backing from
  supporters, launch positions into FWA, and accrue ETH/`$FWA` claims.
- **Independent products:** applications such as PullPool, MegaRip, and FWAP expose one or
  more direct canonical FWA dependencies but own their separate accounting and lifecycle.

## 3. Canonical deployments

The addresses below match the official deployment page and had non-empty runtime bytecode
at the reference block.

| Component | Address |
|---|---|
| FWA core | [`0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c`](https://etherscan.io/address/0xB276F62DB0ce8CA2Ca5bc522695bE604521eAc1c) |
| FWARewards | [`0x6a1a1C0CfB3D3C538e13D36d608a5bcaa992fc78`](https://etherscan.io/address/0x6a1a1C0CfB3D3C538e13D36d608a5bcaa992fc78) |
| VRF service | [`0xa084c33Fb7a467307452898b8D58165ebd2E5D9f`](https://etherscan.io/address/0xa084c33Fb7a467307452898b8D58165ebd2E5D9f) |
| `$FWA` token | [`0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845`](https://etherscan.io/token/0xa0Df17B5aC76ABaBA36E1450E2cbCd18A620C845) |
| Token transfer escrow | [`0xcE6d5B618e034f87C7a8B6dCa65FB8669b8c301B`](https://etherscan.io/address/0xcE6d5B618e034f87C7a8B6dCa65FB8669b8c301B) |
| ERC-20 wrapper | [`0x727C739F07A89f11E883FE0F34937c55e4c3d74A`](https://etherscan.io/address/0x727C739F07A89f11E883FE0F34937c55e4c3d74A) |
| Renderer | [`0x69Cc9c633867eEE71b17142BBBc2c6aaf14c61a4`](https://etherscan.io/address/0x69Cc9c633867eEE71b17142BBBc2c6aaf14c61a4) |
| Token wrapper | [`0x470879Abd61FdCA91436fE27ed87dB2c8650f3e7`](https://etherscan.io/address/0x470879Abd61FdCA91436fE27ed87dB2c8650f3e7) |
| Uniswap v4 hook | [`0x2C67ebA8A50AF0dB5Fba55F725247a75CbDA6444`](https://etherscan.io/address/0x2C67ebA8A50AF0dB5Fba55F725247a75CbDA6444) |
| Owner splitter | [`0x7400824eec17F86Cc74385862810710F9c46Ec04`](https://etherscan.io/address/0x7400824eec17F86Cc74385862810710F9c46Ec04) |
| v1 claim | [`0xd4085d38855F17EdF0B1CCBFad7B3846fb305655`](https://etherscan.io/address/0xd4085d38855F17EdF0B1CCBFad7B3846fb305655) |
| Whitelist authority | [`0x54B641aC97A9e9375665934b8e7a7D0b2C0E898B`](https://etherscan.io/address/0x54B641aC97A9e9375665934b8e7a7D0b2C0E898B) |
| FWAIR manager | [`0xfbc8B4ac9B827BdE0Fe8B2d6aa52043704D38628`](https://etherscan.io/address/0xfbc8B4ac9B827BdE0Fe8B2d6aa52043704D38628) |

`$FWA.pool()` returns `FWARewards`; it is not a Uniswap pool address. The market is a
Uniswap v4 pool identified by a pool key and pool ID. Existing
[`fwa_market.py`](../maxpane_dashboard/data/fwa_market.py) already carries the canonical
pool ID and must remain the single source for it.

## 4. Platform snapshot

Direct FWA-core reads at the reference block:

| Metric | Observed value | Interpretation |
|---|---:|---|
| Active listings | 6,185 | live pool breadth |
| Next listing ID | 186,173 | historical sequence, not active count |
| Acquisition quote | 0.072306041013766740 ETH | fee `0.072306…`, VRF component returned `0` in this call |
| Pending / unsettled acquisitions | 3 / 3 | independent queue stages |
| Acquisition escrow | 0.216903717156842025 ETH | liability, not revenue |
| Refund credits | 0.646295071842734506 ETH | liability, not TVL |
| Crown listing | 177,831 | current top listing |
| Crown pot | 3.621990707450918289 ETH | live reward pot |
| Crown share | 50 bps | **0.5%, not the 1% currently shown in docs** |
| Crown takeover threshold | 1,000 bps | 10% above incumbent backing |
| Acquisition / settlement owner fee | 100 / 100 bps | 1% each |
| Settlement payout | 9,000 bps | 90% of backing to purchaser |
| Selection slippage / timeout | 1,000 bps / 30 blocks | live safety configuration |
| Settlement / finalize window | 3,600 / 86,400 seconds | 1 hour / 24 hours |
| Accrued owner fees | 0 ETH | point-in-time observation |

`weightedBackingTotal` is the inverse-weight denominator and must never be labelled TVL.
Pool backing must be summed from block-pinned positions or a validated direct aggregate.
Likewise, escrow and refunds are liabilities and must not be added to protocol revenue.

The zero VRF component above is not enough to establish that VRF is free. The existing
client correctly requests the quote with transaction context and rejects RPCs known to
drop `gasPrice`; the dashboard should preserve that behaviour and render an unavailable
component rather than invent zero when context is incomplete.

## 5. `$FWA` supply and fee loop

### 5.1 Genesis allocation

Deployment-block `Transfer` logs prove a `1,000,000,000 FWA` initial supply:

| Destination | Amount | Share |
|---|---:|---:|
| Uniswap v4 liquidity allocation | 500,000,000 FWA nominal | 50% |
| FWARewards | 300,000,000 FWA | 30% |
| v1 claim | 200,000,000 FWA | 20% |

The PoolManager transfer was
`499,999,999.999999999999996564 FWA`; the few remaining wei are launch dust. This matches
the nominal token allocation. The 30% rewards allocation contains two 15% buckets for
depositors and purchasers, both emitted over the same 15-day window; that window has ended.

### 5.2 Current supply and burn

At the reference block:

- `totalSupply = 986,380,736.772711768316895088 FWA`;
- cumulative supply reduction from genesis =
  `13,619,263.227288231683104912 FWA` (`1.3619263227%`);
- token name/symbol/decimals are `Fake World Assets` / `FWA` / `18`;
- token launch flag is `true`;
- hook and PoolManager links match the official deployments.

Burn is derived from a known genesis supply minus the current onchain supply. The UI must
label it `burned since genesis`, not infer that every supply reduction came from one event
category.

### 5.3 Buyback routing

Current token configuration:

```text
purchasers   40% of bought FWA
depositors   30% of bought FWA
burn         30% of bought FWA
caller       50 bps of gross buyback ETH; 99.5% enters the swap
max buyback  1 ETH per call
delay        1 block
```

The loop is live. Block `25,849,737`, transaction
[`0x645e9d…f52948a3`](https://etherscan.io/tx/0x645e9d2f5e79a0cb2d4a67c87e9b8bfbe78776a5f7fe9def16474c99f52948a3),
emitted:

```text
ETH spent      0.005694220111179496
FWA bought     767.705216499481163607
caller reward  0.000028614171412962 ETH
depositors     230.311564949844349082 FWA
purchasers     307.082086599792465442 FWA
burned         230.311564949844349083 FWA
```

`gross buyback = ethSpent + callerReward = 0.005722834282592458 ETH`; the caller reward is
50 bps of that gross amount. This is direct event-level proof of the `30 / 40 / 30` route.
Older local research that describes `40 / 40 / 20` is historical and must not drive the
new UI.

### 5.4 Rewards state

FWARewards links back to the canonical core, token, hook, and PoolManager. Live settings:

| Setting | Value |
|---|---:|
| Emission duration | 15 days / 1,296,000 seconds |
| Emission start | Unix `1,784,574,083` |
| Current epoch counter | 38 |
| Hot / cold gap | 60 / 3,600 seconds |
| Forced token share | `-1` (dynamic) |
| Token-buy allowance total | 0.565028989850830757 ETH |

The immutable daily-pot/rate getters still return their original schedule after the end.
They are not evidence of a currently streaming emission. The dashboard must make
`EMISSIONS ENDED` the primary state, then show ongoing fee-funded rewards and claimable
balances separately.

## 6. FWAIR drops

The [first-party drops catalogue](https://www.fwa.fun/drops) is an index and presentation
layer. The canonical enumerable source is the FWAIR manager:

- intake enabled;
- next launch ID `3`, therefore launch IDs `1` and `2` exist;
- minimum backing `0.05 ETH`;
- collection size range `1..10,000`;
- submission period and active-listing withdrawal delay both `30 days`.

Both known launch contracts had verified source and linked back to the manager, FWA core,
and `$FWA` token.

| Launch | Contract / collection | Phase | Funding | FWA progress | Reserves at snapshot |
|---|---|---|---|---|---|
| 1 — FWAIR PFPs | [`0x47a458…e28eCf`](https://etherscan.io/address/0x47a45870854898AC84D529C4dD05113CD5e28eCf) / `0x29f1…a620` | Complete (`4`) | 111/111, 111 supporters, 0.25 ETH each, 27.75 ETH | 111 launched, 110 terminal | 23,112.834461573234243657 FWA supporter reserve |
| 2 — SAVE ETH | [`0x2AB8D2…7453c0`](https://etherscan.io/address/0x2AB8D29384CB5Ec51e929c3027F8600a6E7453c0) / `0x3559…3560` | Complete (`4`) | 1,000/1,000, 145 supporters, 0.05 ETH each, 50 ETH | 1,000 launched, 448 terminal | 11,555.862078983021114970 FWA supporter reserve; 6.580091411705420918 ETH artist credit |

The launch phase, support-window state, funding progress, and downstream FWA position
progress are different concepts. A launch can be `Complete`, fully funded, and still have
many non-terminal FWA positions. The UI must display those dimensions independently.

During research the catalogue counters lagged direct child-contract reads as positions
settled. That is expected index latency and is the reason every drop row needs a chain
block/freshness badge.

Future drops must appear through `nextLaunchId()` plus `launches(id)`, not through a
hardcoded two-row table.

## 7. Projects built on FWA

The official ecosystem page identifies **Megarip by ripe0x** and **FWAP by 0xquit**.
This is a discovery seed, not a complete registry. Inclusion in MAXPANE requires:

1. a first-party project source;
2. deployed runtime bytecode;
3. at least one direct, readable canonical FWA dependency, with every dependency actually
   used by that version recorded separately;
4. versioned addresses, deployment blocks, and ABIs/event topics;
5. accounting invariants that can be checked without an API key.

### 7.1 PullPool and MegaRip by ripe0x

First-party sources: [PullPool docs](https://pullpool.fun/docs),
[PullPool](https://pullpool.fun/docs/pull-pool),
[GroupPull](https://pullpool.fun/docs/group-pull), and
[MegaRip](https://pullpool.fun/megarip).

These are separate products and must not share one set of economics.

#### PullPool

PullPool sells equal fixed-price tickets to fund a single FWA acquisition. Every ticket
receives the same pro-rata outcome; rounds may settle, become claimable, or refund.

Current production contract:
[`0x03C45c9C594b19ca5Fde54f38C7e6b6A5f2329d7`](https://etherscan.io/address/0x03C45c9C594b19ca5Fde54f38C7e6b6A5f2329d7#code).
Its source is verified and direct reads prove the canonical FWA core, FWARewards, and token
addresses.

At block `25,849,714`:

- 367 rounds; no currently open round and no pending pull;
- rounds 364–367 were refunding; round 363 was the last settled round;
- `paused = false`, `deprecated = false`, token payouts enabled;
- `0.005 ETH` ticket and one-day funding;
- 4% total fee; for referred tickets, one percentage point goes to the referrer and three
  percentage points go to the fee recipient;
- accounted/held ETH `0.618943394256984616`;
- token balance `155,442.979785911074829165 FWA`;
- `$FWA.isDistributor(currentPullPool) = true`.

Lifecycle decoding was independently rechecked against Ethereum at block
`25,850,301`: `getRound(367)` on PullPool v2 returned raw enum value `5`, and
`getRound(65)` on GroupPull returned `5`. The verified layouts define `0` as
the empty/none sentinel and values `1..5` as the named lifecycle states, so
those live rows are `Refunding` and `Expired`; a zero-based display lookup
would be off by one and must not be used.

Related production surfaces:

| Surface | Address | Snapshot counter/context |
|---|---|---:|
| Legacy PullPool | [`0xB2D802…D2bF3`](https://etherscan.io/address/0xB2D80254af189854Bf90D2C338d87236d67D2bF3) | historical rounds |
| GroupPull | [`0xd23DCb…D4187`](https://etherscan.io/address/0xd23DCbfD47E849DAC946689E264AaD3c6bbD4187) | 65 packs |
| Current standing-order factory | [`0xFba041…3D1E`](https://etherscan.io/address/0xFba041453dabbFE8B34409Cf88417913Cc483D1E) | 160 orders |
| Legacy standing-order factory | [`0xe60a93…B9C`](https://etherscan.io/address/0xe60a9341C3C73636B911e609dEFaf05B09EDeB9C) | 72 orders |
| Group-order factory | [`0x2315F3…F605`](https://etherscan.io/address/0x2315F319c0E47AFa26c6167e0e3a4DC46585F605) | 3 orders |

Pack/order counters are cumulative creations, not current open or active counts. The
adapter must derive open, filled, cancelled, and claimable states separately.

The live frontend applies a synthetic `+375` display offset while combining legacy and
current histories. A chain dashboard must version and deduplicate those histories instead
of copying the display count.

#### MegaRip

MegaRip pools ETH for a campaign, performs a sequence of FWA pulls, monetizes the results,
then distributes the final pot pro rata by deposit.

| Version | Contract | Deposits | Depositors | Pulls | Gross recovery |
|---|---|---:|---:|---:|---:|
| 1 | [`0x68f8E0…18D25`](https://etherscan.io/address/0x68f8E0Bd62eD310F692Ae0D01F7e568948818D25) | 31.182369 ETH | 139 | 379 | 91.6455% |
| 2 | [`0x676994…AC5c6`](https://etherscan.io/address/0x6769944589f5CC96d5F900F06539681Db84AC5c6) | 16.911 ETH | 88 | 209 | 100.6552% |
| 3 | [`0x58A1D8…D13D7D`](https://etherscan.io/address/0x58A1D8daf6d68EEC8b350684e8feCC4379D13D7D) | 13.309 ETH | 42 | 126 | 67.1837% |

`Gross recovery = final pot / deposits`; it is not investment return. MegaRip 3 therefore
returned 67.1837% of contributed principal before interpreting any separate `$FWA` claims,
equivalent to a `-32.8163%` ETH shortfall against deposits.

MegaRip 3 was finalized at the research block:

- acquisition spend `10.764747870499079235 ETH`;
- final pot `8.941490283500920765 ETH`;
- paid `8.659990213714544174 ETH`;
- 39 claim events and three depositor addresses still unclaimed;
- 126 `PullRequested`, 126 `Allocated`, and 126 `SettledBid` events;
- 2% success fee and `0.181969146 ETH` total settlement fees;
- 350 bounty events totalling `2.51925 ETH`;
- no auction because every observed backing was below the `1 ETH` auction threshold;
- no `$FWA` reward distribution yet and no distributor role.

MegaRip 3 has runtime bytecode but unverified source. Its callable ABI and event topics are
chain-confirmed; implementation-level assertions must render `CHAIN-READ` with provenance
text that says the source is unverified.

The public ripe0x `PullPool.sol` gist conflicts with the deployed current contract and is
not canonical.

### 7.2 FWAP by 0xquit

First-party source: [fwap.fun](https://fwap.fun/). FWAP describes shared pools of ETH and
FWA-allowlisted NFTs. Its public snapshot endpoint is useful as an optional index, but it
returned `stale: true` during research and must not drive canonical live state.

Two verified production generations were traced from share/receipt tokens to their house
contracts and then back to the canonical FWA core, FWARewards, and `$FWA` token:

| Generation | House | Share / receipt | Chain snapshot |
|---|---|---|---|
| v1 | [`0x00000000000E56073987EAF8694Fe54fCA2F53de`](https://etherscan.io/address/0x00000000000E56073987EAF8694Fe54fCA2F53de) | `0x0000…aC50` / `0x0000…5cBB` | 1,508 cumulative positions created; 4.207391565616996703 ETH book/liquid capital; 8,292.813827409910056719 FWA |
| v2 | [`0x000000000095f80F42F09c4515d3fF841E65a541`](https://etherscan.io/address/0x000000000095f80F42F09c4515d3fF841E65a541) | `0x0000…2c8a` / `0x0000…8635` | 1,640 cumulative positions created; 93.874646251439422329 ETH book NAV; 2.434646251439422329 ETH liquid capital; 129,959.020986185066906068 FWA |

Both houses use `0.06 ETH` configured backing, a 25% receipt-PnL share, and currently have
`$FWA` distributor permission. Reward fee is 20 bps in v1 and 40 bps in v2. V2 was epoch
7 with a three-day epoch duration at the reference block.

The cumulative counter is `nextPositionId - 1`; it is not active inventory. Active,
returned, allocated, terminal, and inventory counts must be derived independently at one
pinned block.

The API may enrich the view with projected or categorized inventory only when it exposes
its own source block and freshness. Contract getters remain authoritative for NAV,
capital, token balances, positions, and epochs. A publicly embedded third-party NFT API
credential found in site assets is intentionally excluded; MAXPANE must remain keyless and
must never copy it into code or Git.

## 8. Documentation and implementation drift

| Topic | Older or documented statement | Chain-validated state | Dashboard rule |
|---|---|---|---|
| Crown share | 1% | 50 bps / 0.5% | read `topListingShareBps()` |
| Settlement | older local research: 85% | 9,000 bps / 90% | interpret as payout, not discount |
| Buyback route | older local research: 40/40/20 | purchasers/depositors/burn = 40/30/30 | read config and events |
| Emissions | rate/daily-pot getters remain nonzero | 15-day schedule ended | render ended state first |
| Drops | catalogue counters and copy can lag | child contracts advance live | enumerate manager, pin block |
| Collections | docs describe an initial set | allowlist is mutable | derive from current events/state |
| PullPool count | frontend merges versions with offset | separate deployed histories | version and deduplicate |
| FWAP snapshot | API marked stale | direct calls continued changing | API is optional enrichment |

## 9. Existing code worth reusing

The current MAXPANE and `/Library/Vibes/autopull` implementations already provide the
production-grade purchaser view:

- `FWAHeroMetrics`, `FWAOddsBoard`, `FWASparkline`, `FWASignals`;
- `FWAActivityFeed`, `FWAChaseBoard`, `FWASettlementTable`;
- `FWAClient`, separate `FWALogs`, `FWAMarket`, tiered `FWACache`;
- block-pinned Multicall enumeration, last-good values, watermarks, and refresh guard;
- shared `StatusBar`, markup escaping, safe-call helpers, and sparkline primitives.

`/Library/Vibes/alexandria` contributes the useful architectural analogy rather than FWA
content: its Surf launchpad work uses knowledge routing, source-specific adapters, codehash
checks, fixed deployment blocks, and explicit source health.

The current `fwa_manager.py` is already large. New ecosystem work should be focused
collaborators merged at one presentation boundary, not another monolithic extension.

## 10. Runtime invariants

The implementation must assert or visibly degrade on these conditions:

- every official deployment has non-empty bytecode;
- FWA core, FWARewards, token, hook, and FWAIR links agree;
- every ecosystem adapter reads the expected FWA dependencies;
- a configured runtime codehash change raises a source-integrity warning and suspends
  current semantic metrics until the ABI is revalidated;
- supply never exceeds the known one-billion genesis supply;
- buyback route bps sum to 10,000;
- `None` never becomes numeric zero;
- state data is pinned to one block per refresh;
- log ranges start at version-specific deployment blocks and advance persisted watermarks;
- ETH/FWA liabilities are not labelled revenue, NAV, or TVL;
- a stale project API cannot overwrite fresher chain state;
- third-party text is escaped before Rich/Textual rendering.

## 11. Scope limitation

“The whole FWA ecosystem” cannot be discovered permissionlessly from one canonical
registry today. V1 can truthfully cover:

1. the full official FWA deployment graph;
2. every FWAIR launch enumerated by its manager;
3. first-party-known downstream products with chain-verified adapters;
4. an evidence-backed manifest that can grow without changing the screen contract.

The UI should say `verified integrations`, not `all projects`, and expose the evidence and
freshness behind each row.
