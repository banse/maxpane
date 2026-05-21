# Ten Thousand Tokens (TTT) — Technical Findings

## Network
- **Chain**: Ethereum mainnet (chain ID 1)
- **Block time**: ~12 seconds

## Master Contract
- **Address**: `0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e`
- **Type**: ERC-721 NFT factory + ERC20 launcher
- **Symbol**: TTT
- **Creator**: `0x019817ad02a31b990433542097be29d97613e8cb`
- **Deployed**: May 2026

## Contract Architecture (7 contracts total)
- **NFT factory** (master, above) — ERC721 + `burnAndLaunch` orchestrator
- **TTT ERC20 instances** — one per launched token, deployed by the factory; symbol pattern `TTT` or named (e.g. `TFT`, `ONE`, `BURN`, `STR`); each has 1B supply
- **TTTHook** — Uniswap V4 hook shared across all launched pools (handles decay tax, fee splitting, buyback routing)
- **FeeSplitter** — receives fees, performs 50/30/10/10 distribution, maintains `accETHPerShare`
- **OnChainRenderer** — SVG generator (rings + moons + glyph)
- **GlobalDistributorHandler** — allowlist / claim controller
- **Interfaces** — IPoolManager, IPositionManager, IAllowanceTransfer (Uniswap V4 + Permit2)

## Key Reads for the Dashboard

| Need | Source | Method |
|------|--------|--------|
| Max supply / burn count | NFT factory | `MAX_SUPPLY()` (constant 10_000), `burnCount()` |
| Per-NFT pending claim | FeeSplitter | `accETHPerShare()` (or equivalent) + `rewardDebt[tokenId]` |
| Cumulative ETH to holders | FeeSplitter | `totalHolderFeesPaid()` or sum of `Deposit` events × 30% |
| Recent launches | NFT factory | `BurnAndLaunch(tokenId, erc20, deployer, block)` events |
| Recent fee deposits | FeeSplitter | `Deposit(tokenAddress, ethAmount)` events |
| Launched-token list | NFT factory | All historical `BurnAndLaunch` events |
| Per-token buyback reservoir | TTT-<n> ERC20 | `reservoir()` or balance read |
| Per-token buyback events | TTT-<n> ERC20 | `Buyback(caller, ethSpent, tokensBought)` events |
| Block number for decay calc | RPC | `eth_blockNumber` |

**Exact ABI / event names will be confirmed from the verified source on Etherscan during implementation.** The contract is verified.

## Decay Tax Formula
```
buyTax(currentBlock, launchBlock) = max(99 - (currentBlock - launchBlock), 1)   # percent
sellTax = 1                                                                     # percent, constant
```
- Block 0 (launch): 99%
- Block 50: 49%
- Block 98+: 1% (floor)

## Holder Concentration Formula
```
unburned       = 10_000 - burnCount
per_nft_share  = 0.30 / unburned                                                # fraction of each deposit
per_nft_claim  = (accETHPerShare - rewardDebt[tokenId]) / SCALE
```
Marginal impact: each additional burn raises every remaining NFT's per-deposit share by `0.30 * (1/(N-1) - 1/N)` where `N = unburned`.

## Buyback Bounty
```
bounty_eth(token) = 0.005 * min(reservoir(token), 1 ETH)
```
A token becomes interesting to bots when reservoir > ~0.1 ETH (bounty > 0.0005 ETH ≈ gas-positive at low gas).

## Data Sources for Dashboard (all keyless)

| Data | Source | Endpoint | TTL |
|------|--------|----------|-----|
| On-chain reads | Public Ethereum RPC | `https://eth.llamarpc.com` (primary), `https://ethereum.publicnode.com`, `https://cloudflare-eth.com` (fallbacks) | 15s |
| Multicall batching | Multicall3 | `0xcA11bde05977b3631167028862bE2a173976CA11` | n/a |
| Launched-token prices / vol / mcap | DexScreener | `GET https://api.dexscreener.com/tokens/v1/ethereum/<addr>,<addr>,...` (≤30 per call) | 30s |
| NFT floor + 24h sales | Reservoir (keyless) | `GET https://api.reservoir.tools/collections/v7?contract=0x26d7...fb2e` | 60s |
| ETH/USD price | Existing `price.py` (CoinGecko keyless) | reused from other dashboards | 60s |

## Public RPC Notes
- Public RPCs are rate-limited (typically 100–300 RPS aggregate per IP).
- Multicall3 collapses dozens of reads into one HTTP call — essential for keeping refresh cycles under 100ms of RPC time.
- Event log queries (`eth_getLogs`) over wide block ranges can be rejected; cap range at 10,000 blocks per call and paginate.
- Cache aggressively: per-block reads at 15s TTL, historical events persisted to local snapshot (so we don't rescan the full log on every refresh).

## Polling Strategy
- Default 30s poll, matching OCM/Base patterns.
- Each refresh: 1 multicall batch (NFT factory + FeeSplitter + each launched token's reservoir) + 1 DexScreener batch + 1 Reservoir call. Total ~3 HTTP requests.
- Event logs (`BurnAndLaunch`, `Deposit`, `Buyback`): incremental — query only `lastSeen → latest`. Persist to `data/snapshot.py`-style local store keyed by event topic.

## Address Discovery
- The list of launched ERC20 addresses is **derived** from `BurnAndLaunch` events on the factory. Not hardcoded — the dashboard auto-discovers as new tokens launch.
- For each new ERC20, optionally cache its symbol + decimals once (immutable).

## Missing / Unknown (to verify during implementation)
- Exact event signatures and method names on the factory and FeeSplitter (must be confirmed from verified source on Etherscan).
- Whether the FeeSplitter exposes a cheap aggregate `totalHolderFeesPaid()` view, or we must sum `Deposit` events.
- Whether the buyback reservoir is held in ETH or wrapped (likely ETH given the whitepaper language).
- Whether Reservoir's keyless tier covers `collections/v7` reliably for this collection; if not, fall back to "Floor: —" gracefully.

## Related Public Resources
- Whitepaper: https://www.token.works/ten-thousand-tokens-whitepaper.html
- Site: https://www.tenthousandtokens.net/
- Docs: https://www.tenthousandtokens.net/docs
- OpenSea: https://opensea.io/collection/ten-thousand-tokens
- Etherscan: https://etherscan.io/address/0x26d7ad0e930b54b84c00daad077ee31ba9e2fb2e
