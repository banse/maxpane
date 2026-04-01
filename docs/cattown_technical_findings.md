# Cat Town Fishing -- Technical Findings

> Research date: 2026-03-28
> Chain: Base (Chain ID 8453)

## 1. Contract Addresses (All on Base Mainnet)

### Core Tokens
| Contract | Address | Notes |
|----------|---------|-------|
| KIBBLE Token | `0x64cc19A52f4D631eF5BE07947CABA14aE00c52Eb` | ERC-20, Solidity 0.8.24, audited by Sourcehat |
| BARON Token | `0x89CD293538C2390992CDFb3520cFb136748CD9B9` | ERC-20, Virtuals Protocol AI agent token |
| Founders Collection | `0xb46cAE60Bf243f1060ffab43611CA808966BF1cB` | ERC-721, 1,555 supply |

### Core Game Systems
| Contract | Address | Type |
|----------|---------|------|
| World | `0x298c0d412b95c8fc9a23FEA1E4d07A69CA3E7C34` | Proxy, impl: `0x622d2d1ef8ef75551a0f79b1116b3dc119ad9ccd` |
| World Events | `0x34E348caC019034fA7D106a96F829a010840696c` | - |

### Fishing
| Contract | Address | Type |
|----------|---------|------|
| Fishing Game | `0xC05Dde2e6E4c5E13E3f78B6Cb4436CFEf6d7AbD3` | UUPS Proxy, impl: `0xe2c5df2157fd0467f408a4ea309bb3a069d3232c` |
| Fishing Rods | `0x3395581Be91082721Fb9bF781D9eA21F0ad1AF85` | Proxy |
| Competition | `0x62a8F851AEB7d333e07445E59457eD150CEE2B7a` | Proxy |
| Fish Raffle | `0x5E183eBc7CA4dF353170C35b4D69Ea9f42317b28` | - |
| Free to Play Pool | `0x131E680dc7A146F00b282FBd7d6261c5B38c4Fa6` | Proxy |

### Items & Equipment
| Contract | Address | Type |
|----------|---------|------|
| Item Minter V1 | `0x408C186C1fFCc78592cbdae9B04da8a64A975550` | Proxy |
| Item Minter V2 | `0x7b65ec82cB4600Bc1dCc5124a15594976f19eA14` | Proxy |
| Gacha Machine | `0xAD0ee945B4Eba7FB8eB7540370672E97eB951F1a` | Proxy |
| Sell Items (Supermarket) | `0x49936db5Dcbc906D682CFa2dcfAb0788e3ee5808` | Proxy |
| Player Equipment | `0xA9a7f9eDD67eEE40747bB3ec2d92Dab1C8B83d75` | Proxy |

### Staking
| Contract | Address | Type |
|----------|---------|------|
| Revenue Share | `0x9e1Ced3b5130EBfff428eE0Ff471e4Df5383C0a1` | Proxy |

### Price Oracle
| Contract | Address |
|----------|---------|
| KIBBLE Oracle | `0xE97B7ab01837A4CbF8C332181A2048EEE4033FB7` |

### DEX / Liquidity
| Contract | Address |
|----------|---------|
| KIBBLE/WETH Pool (Sushi v2) | `0x8e93c90503391427bff2a945b990c2192c0de6cf` |

### Key Wallets
| Wallet | Address |
|--------|---------|
| Treasury | `0x1762BFeae2E37C5dd8635459266c0a33e12334e6` |
| Developer | `0x77d3365afCc72E2119A5033b30FA205c1Bc99ffa` |
| Deployer | `0xa6bee3f99ee2b70672a34a983af0bbf79c028cd9` |

### Legacy/Deprecated
| Contract | Address |
|----------|---------|
| Legacy Staking | `0xc3398Ae89bAE27620Ad4A9216165c80EE654eE96` |
| Legacy Fishing | `0x8f9C456C928a33a3859Fa283fb57B23c908fE843` |
| Legacy Sell Items | `0x38E0943be3C328d58B3b16a95545E04F1Eb931d4` |
| Legacy Quests | `0x479016d1e8f3968c161F42e52F47db57fd3256fe` |
| Legacy Quest Requirements | `0xbBf3Ea58Ca18Ff51c8211794ff4FabB03b731DC5` |
| Cats & Floofs Migration | `0x441E1bA5Ae10d238397F5102F406AFe44DD01B6a` |
| Legacy Cat Town | `0x10A77395a07917C5Eb71fEEB86696B7612f9730F` |

## 2. Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (App Router), PWA (standalone, portrait) |
| Wallet | wagmi/viem, Coinbase Smart Wallet, OnchainKit |
| VRF | Gelato VRF (survived 50k mints/weekend, 1000 mints/min peak) |
| RPC | Alchemy Enterprise (2B Compute Units/month) |
| Realtime | Ably (websocket-based, `/api` returns Ably auth tokens) |
| Art | Aseprite sprites, Lua scripting for trait rules |
| Docs | GitBook at docs.cat.town |
| Contract Pattern | ERC-1967 UUPS upgradeable proxies, Solidity 0.8.21-0.8.24 |
| NFT Standards | ERC-721 (fish, treasures, PFPs), ERC-1155 (items/equipment) |
| Analytics | Dune dashboard: `dune.com/0xkhmer/cat-town` |
| CDN | `cdn.cat.town` for game assets |

## 3. Data Retrieval Assessment

### What's Available Onchain (readable via eth_call)
- **KIBBLE balances and allowances** -- standard ERC-20 reads
- **Fish NFTs** -- ERC-721 ownership, metadata (weight, species, rarity)
- **Competition state** -- leaderboard data on Competition contract
- **Staking positions** -- Revenue Share contract reads
- **Rod ownership** -- Fishing Rods contract
- **Player equipment** -- Player Equipment contract
- **KIBBLE price** -- KIBBLE Oracle contract
- **VRF fee** -- readable from Fishing Game contract
- **Transaction history** -- event logs from all contracts

### What's NOT Available / Harder to Get
- **No public API documentation** -- no tRPC, REST, or GraphQL endpoints found
- **No agent.json or skill.md** bootstrap endpoints (both return 404)
- **Contract ABIs are largely unavailable** -- contracts are UUPS proxies and source is unverified on BaseScan (except KIBBLE token)
- **Timing mini-game state** -- client-side only, not onchain
- **Weather/time-of-day conditions** -- likely server-determined or time-based
- **Exact drop rate probabilities** -- not published
- **Hot streak state** -- unclear if onchain or client-side
- **Reputation scores** -- likely in World or Fishing Game contract but ABI unknown

### Data Retrieval Strategy (for dashboard)

**Tier 1: Direct onchain reads (no API needed)**
- KIBBLE price via Oracle contract
- KIBBLE token stats (supply, burned, holders) via token contract
- Player's fish NFTs via Fishing Game contract events
- Competition results via Competition contract events
- Staking revenue via Revenue Share contract events
- Pool liquidity via DEX contract

**Tier 2: Event log parsing**
- Fish identification events (species, weight, rarity, player, timestamp)
- Competition entry/result events
- Raffle ticket purchases and drawings
- Boost/item purchases
- Staking deposits/withdrawals/claims

**Tier 3: Reverse-engineering needed**
- Function selectors from transaction data (dominant fishing selector: `0x71c9f256`)
- ABI reconstruction from proxy implementation contracts
- Frontend source analysis for API calls and data structures

**Tier 4: External sources**
- DexScreener API for KIBBLE price charts
- Dune Analytics dashboard (`dune.com/0xkhmer/cat-town`) for aggregate stats
- CoinGecko API for token market data

## 4. Comparison to AutoPet Architecture

### Data Retrieval Patterns

| Pattern | AutoPet (FrenPet) | Cat Town Applicability |
|---------|-------------------|----------------------|
| Game API client (REST) | `game_api.py` -> api.pet.game | **No public API found** -- would need to reverse-engineer frontend or go onchain-only |
| GraphQL indexer | Ponder/subgraph for target discovery | **Dune** available but not real-time; would need custom indexer |
| Direct RPC reads | `contracts.py` with AsyncWeb3 | **Primary approach** -- all core state is onchain |
| Event stream (websocket) | `event_stream.py` for Attack events | **Ably** used for realtime but auth required; fallback to RPC event polling |
| Local SQLite cache | `indexer/db.py` for fast lookups | **Same pattern works** -- cache fish NFTs, competition state, staking data |

### What We Can Reuse from AutoPet
- **RPCProvider** with primary/backup failover (change chain_id to 8453/Base)
- **NonceManager** for transaction sequencing
- **SpendingGuard** for daily gas limits
- **EventBus** for internal event routing
- **GasMonitor** for Base chain gas tracking
- **SQLite models pattern** for local caching
- **FastAPI dashboard** structure
- **React dashboard** components and layout

### What Needs New Implementation
- **ABI extraction** -- need to reverse-engineer from proxy implementations or frontend bundle
- **KIBBLE token interaction** -- ERC-20 approval + spending (not needed in AutoPet/MaxPane)
- **Competition tracking** -- weekly cycle monitoring, leaderboard polling
- **Fish NFT indexing** -- ERC-721 event parsing for catch history
- **Condition monitoring** -- time-of-day and weather tracking for optimal fishing windows
- **Staking analytics** -- revenue share tracking and yield calculations

### Automation Challenges (vs AutoPet/MaxPane)
1. **Timing mini-game** is client-side -- automation requires browser/client interaction, not just contract calls
2. **Identification requires KIBBLE** -- need token approval and balance management
3. **No VRF fee function found** -- may need to extract from tx data or frontend
4. **Unverified contracts** -- ABI reconstruction is the biggest technical hurdle
5. **Ably auth** -- realtime events need authenticated websocket connection

## 5. Dashboard Data Opportunities

### High-Value Dashboard Widgets
1. **KIBBLE Economy** -- price, supply, burn rate, staking APY
2. **Competition Leaderboard** -- current week standings, prize pool size
3. **Fish Catch Feed** -- real-time catches with species/weight/rarity
4. **Condition Tracker** -- current time-of-day + weather + season = available fish
5. **Staking Dashboard** -- deposited amount, pending rewards, claim history
6. **Raffle Status** -- tickets purchased, progress bar level, prize pool
7. **Player Stats** -- reputation level, rod tier, total catches, best fish
8. **Token Analytics** -- KIBBLE/ETH price, volume, liquidity depth

### Data Freshness Requirements
| Widget | Update Frequency | Source |
|--------|-----------------|--------|
| KIBBLE Price | 30s | Oracle contract or DEX pool |
| Competition Leaderboard | 5min | Competition contract events |
| Fish Catch Feed | Real-time | Fishing Game contract events (or Ably) |
| Conditions | 1min | Time-based calculation + weather API/contract |
| Staking | 10min | Revenue Share contract reads |
| Raffle | 1h | Fish Raffle contract reads |
| Token Stats | 5min | KIBBLE token contract + DexScreener |

## 6. URLs & External Resources

| Resource | URL |
|----------|-----|
| Main site | https://cat.town |
| Fishing | https://cat.town/fishing |
| Gacha | https://cat.town/supermarket |
| Staking | https://cat.town/bank/staking |
| Docs | https://docs.cat.town |
| Contract addresses | https://docs.cat.town/welcome/addresses |
| Dune dashboard | https://dune.com/0xkhmer/cat-town |
| DexScreener | https://dexscreener.com/base/0x8e93c90503391427bff2a945b990c2192c0de6cf |
| CoinGecko | https://www.coingecko.com/en/coins/kibble |
| Virtuals (BARON) | https://app.virtuals.io/virtuals/9965 |
| Twitter | https://twitter.com/cattownbase |
| Discord | https://discord.gg/cattown |
| Telegram | https://t.me/WelcomeToCatTown |
| Warpcast | https://warpcast.com/cattown |
| Bug bounty | rob@cat.town ($50-$10,000 ETH) |
| Audit | Sourcehat (June 4, 2024) -- KIBBLE token |

## 7. Key Unknowns / Next Steps

1. **ABI extraction** -- Biggest blocker. Options:
   - Decompile proxy implementations on BaseScan (Dedaub/Heimdall)
   - Extract from Next.js frontend bundle (wagmi ABI imports)
   - Monitor transaction calldata to reconstruct function signatures
2. **Realtime data** -- Ably auth mechanism needs investigation for event streaming
3. **Weather system** -- Is it onchain, server-side, or real-world weather API?
4. **Drop rate tables** -- Not published; could be estimated from historical catch data
5. **VRF fee amount** -- Need to read from contract or estimate from tx values (~0.00003 ETH observed)
6. **Staking APY** -- Calculable from revenue share events + total staked amount
