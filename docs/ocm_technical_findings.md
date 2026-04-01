# Onchain Monsters (OCM) - Technical Findings

## Chain & Network

- **Chain:** Ethereum Mainnet (Chain ID 1)
- **RPC:** `https://eth.merkle.io` (used by monsterfactory.lol)
- **Explorer:** https://etherscan.io
- **Currency:** ETH for gas; $OCMD (ERC-20) for minting

## Smart Contract Addresses

| Contract | Address | Description |
|----------|---------|-------------|
| **OnChainMonsters (NFT)** | `0xaA5D0f2E6d008117B16674B0f00B6FCa46e3EFC4` | ERC-721 NFT collection, also tracks as ERC-20 "OCMOS". Solidity 0.8.0, verified. |
| **MonsterDough ($OCMD)** | `0x10971797FcB9925d01bA067e51A6F8333Ca000B1` | ERC-20 staking reward token. Solidity 0.8.0, verified. |
| **OnChainMonstersFaucet** | `0xd495a9955550c20d03197c8ba3f3a8c7f8d17eb3` | Third-party minting faucet (monsterfactory.lol). Solidity 0.8.30, optimized, verified. |

### Deploy Transaction
`0x18cafc41379b62722c3297e239b32b14e04d732440e0500b3199b3cb549da2e5`

## NFT Contract Functions

### Read Functions
| Function | Description |
|----------|-------------|
| `currentMintingCost()` | Returns cost based on supply tier (0, 1, 2, 3, or 4 OCMD) |
| `tokenURI(uint256)` | Returns base64 JSON metadata (fully on-chain) |
| `tokenIdToTraitsHash(uint256)` | Retrieves trait hash for a token |
| `walletOfOwner(address)` | Lists all tokens owned by address |
| `hashToSVG(bytes)` | Generates SVG artwork from trait hash |
| `hashToMetadata(bytes)` | Creates trait metadata JSON from hash |
| `totalSupply()` | Current number of minted monsters |

### Write Functions
| Function | Description |
|----------|-------------|
| `mintMonster()` | Mint a new NFT (original contract method) |
| `burnForMint(uint256)` | Sacrifice existing token to mint a new one |

## $OCMD Token Contract Functions

### Read Functions
| Function | Description |
|----------|-------------|
| `balanceOf(address)` | Token balance |
| `totalSupply()` | Total minted tokens |
| `name()` | "MonsterDough" |
| `symbol()` | "OCMD" |
| `decimals()` | 18 |

## Staking Contract Functions

The staking is embedded in the $OCMD contract:

| Function | Description |
|----------|-------------|
| `stakeByIds(uint256[])` | Stake specific monster token IDs |
| `getTokensStaked(address)` | View staked token IDs for a wallet |
| `unstakeByIds(uint256[])` | Unstake specific monsters + claim rewards |
| `unstakeAll()` | Unstake all + claim all accumulated rewards |

### Staking Constants
- Emission: `11,574,070,000,000` wei/second/monster (~1 OCMD/day)
- Max staked per wallet: 10
- `CLAIM_END_TIME`: February 1, 2022

## Faucet Contract Functions

| Function | Description |
|----------|-------------|
| `publicMint(uint256 amount)` | Free welcome mint, limited to 1 per address |
| `mintWithMyOwnTokens(uint256 amount)` | Mint using $OCMD tokens |
| `publicMintCount(address)` | Check if address already claimed welcome mint |
| `currentMintingCost()` | Current cost for next single mint |
| `queryMintPrice(uint256 amount)` | Total cost for a batch |
| `isClosed()` | Whether faucet is currently accepting mints |

## Data Architecture

### No Centralized API

All data is read directly from Ethereum via JSON-RPC `eth_call`. There is no REST/GraphQL API, no subgraph, no indexer. The dashboard must query contracts directly.

### Data Sources for Dashboard

| Data Point | Source | Method |
|------------|--------|--------|
| Total supply | NFT Contract | `totalSupply()` |
| Minting cost | NFT Contract | `currentMintingCost()` |
| Player's monsters | NFT Contract | `walletOfOwner(address)` |
| Monster traits/art | NFT Contract | `tokenURI(uint256)` |
| $OCMD balance | Token Contract | `balanceOf(address)` |
| $OCMD total supply | Token Contract | `totalSupply()` |
| Staked monsters | Token Contract | `getTokensStaked(address)` |
| Pending rewards | Derived | `(now - stakeTime) * emission_rate * num_staked` |
| Floor price | OpenSea/Blur API | External marketplace API |
| Holder count | Etherscan API or event logs | `Transfer` event analysis |
| Mint events | NFT Contract logs | `Transfer(0x0, to, tokenId)` events |
| Staking events | Token Contract logs | Custom staking events |

### On-chain Art Generation

Monsters are generated as SVGs from trait hashes:
1. `tokenIdToTraitsHash(tokenId)` → bytes hash
2. `hashToSVG(hash)` → SVG string
3. `hashToMetadata(hash)` → JSON traits

This is fully on-chain -- no IPFS, no external hosting.

## Technical Considerations for Dashboard

### RPC Strategy
- Ethereum mainnet RPCs are generally more reliable than L2s
- Use a dedicated RPC (Alchemy, Infura) rather than public endpoints for production
- Batch `eth_call` where possible to reduce round trips

### Key Metrics to Track
1. **Collection stats:** total supply, holder count, floor price
2. **Staking stats:** total staked, staking APY estimate, personal staked monsters
3. **Token stats:** $OCMD supply, price, daily emission
4. **Activity:** recent mints, stakes/unstakes, burns
5. **Personal portfolio:** owned monsters, staked monsters, pending rewards, $OCMD balance

### Event Signatures (for log scanning)
- **Mint:** `Transfer(address indexed from, address indexed to, uint256 indexed tokenId)` where `from == 0x0`
- **Burn/Sacrifice:** `Transfer(address indexed from, address indexed to, uint256 indexed tokenId)` where `to == 0x0`
- **Staking:** Custom events from the OCMD contract (need ABI verification)

### Comparison to Existing Dashboards

| Aspect | Cat Town | OCM |
|--------|----------|-----|
| Chain | Base | Ethereum Mainnet |
| Data source | Contracts + game API (tRPC) | Contracts only (no API) |
| Core action | Fishing (continuous) | Staking (passive) |
| Competition | Weekly fishing competitions | N/A (collection/staking) |
| Token | KIBBLE (ERC-20) | $OCMD (ERC-20) |
| NFTs | N/A | Core mechanic (monsters) |
| Activity feed | Catch events from logs | Mint/stake/unstake/burn from logs |
