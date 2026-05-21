# Ten Thousand Tokens (TTT) — Protocol Mechanics

## Overview
Ten Thousand Tokens is an experimental Ethereum-mainnet protocol by TokenWorks. A fixed 10,000-NFT collection serves as a permissionless ERC20 launchpad: each NFT can be `burnAndLaunch()`'d once to deploy a paired ERC20 (1B supply) into a Uniswap V4 pool with a shared hook. Un-burned NFT holders share 30% of all trading fees from all launched tokens.

## Collection
- **Size**: 10,000 NFTs (immutable, code-enforced cap)
- **Standard**: ERC-721 with on-chain SVG rendering
- **Soulbound until sellout**: every transfer / approval reverts until `totalMinted == MAX_SUPPLY`. After sellout, NFTs are permanently transferable.
- **Status (May 2026)**: Fully minted; OpenSea floor ~0.0502 ETH; ~109+ tokens already launched.

## Mint (closed, May 2026)
Three concurrent paths during a 7-day window:

| Path | Price | Cap | Gating |
|------|-------|-----|--------|
| Public mint | 0.01 ETH | 3 / wallet | Blocked first 24h |
| Gated mint | 0.01 ETH | Merkle-encoded | Always active |
| Claim | Free | S02 Soulbound balance | Non-refundable |

`burnAndRefund()` is available for paid mints if the window closes unsold.

## Burn-and-Launch Mechanic
- **`burnAndLaunch(tokenId)`**: permissionless, reentrancy-guarded, callable by the NFT owner.
- **Per-token supply**: 1,000,000,000 (1B) TTT-<n>
- **Hardcoded initial price**: 10 ETH ≡ 1B tokens (i.e. 1 token = 10⁻⁸ ETH at launch)
- **Pool**: Uniswap V4, paired ETH/TTT-<n>, shared TTTHook
- **Liquidity seeded**: 1 wei ETH + full 1B supply, locked to burn address (permanent)
- **One-shot**: `loadingLiquidity` flag prevents re-initialization

## Fee Model

### Buy-Side Tax (Decay)
- Starts **99%** at launch block, drops **1% per block** down to **1% floor**
- Decay completes after **98 blocks** (~20 minutes at 12s blocks)
- Block-based, no oracles — deterministic schedule
- "Rewards waiting" by design

### Sell-Side Tax
- **Flat 1%** at all times, no decay

### Fee Distribution (every fee deposit, split four ways)
| Recipient | Share | Mechanism |
|-----------|-------|-----------|
| Token deployer (the NFT burner) | 50% | Immediate ETH transfer |
| Un-burned NFT holders (pool) | 30% | Cumulative accrual; pull-claim |
| TokenWorks | 10% | Immediate transfer |
| PunkStrategy | 10% | Buyback wallet transfer |

### Holder Pool — MasterChef-Style Accrual
- Cumulative `accETHPerShare` updated on every deposit
- Per-NFT claimable: `(accETHPerShare − rewardDebt[id]) / SCALE`
- **Dynamic concentration**: divisor is `(10,000 − burnCount)`, so each remaining NFT's share grows as more burn:

| Burns | Share per un-burned NFT |
|-------|-------------------------|
| 0 | 0.003% |
| 5,000 | 0.006% |
| 9,000 | 0.030% |
| 9,990 | 3.000% |
| 9,999 | 30.000% |

## Buyback Mechanism (per launched token)
- Buy-side fees above the 1% resting rate are routed by the hook: TTT → ETH → token contract's reservoir.
- Anyone can call **`TTT.buyback()`** to execute: it draws up to **1 ETH per block** from the reservoir, buys TTT, and holds the bought tokens inert (permanently removed from circulation).
- **Bounty: 0.5%** of the swap goes to the caller — a permissionless MEV-style opportunity.

## Burn Economics — Costly Signaling
Burning is a signal of conviction. The cost of burning is the forfeited proportional claim on all future holder-pool deposits.
- As the platform matures and the holder pool grows, the implicit launch-quality bar rises.
- Late-stage burns mean abandoning a now-larger income share — only high-conviction launches stay economic.

## On-Chain Rendering
- Black background + 3 fixed-radius orbital rings (220, 320, 440) + 1–4 seed-derived moons + a centered 5×5 symmetric pixel glyph
- 4 glyph modes (grid / rings / blocks / diagonal), Visualize Value vocabulary
- 65-entry sine LUT (130 bytes), deterministic from `keccak256(abi.encode(tokenId))`
- `tokenURI` gas: ~260,000

## Design Principles
- Immutable supply cap, no governance override
- Identical canonical parameters across all launches (price, liquidity, fee tier)
- One-time launch window per token via `loadingLiquidity` flag
- No screening, vetting, or liquidity subsidy from the protocol
- Contingent fee stream: realized ETH is bounded above by swap volume and below by zero — protocol does not manufacture volume

## Key Numbers Cheat Sheet
- 10,000 NFTs total
- 1B ERC20 supply per launched token
- 10 ETH initial pool value
- 99% → 1% buy tax over 98 blocks
- 1% flat sell tax
- 50 / 30 / 10 / 10 fee split
- 1 ETH/block max buyback draw, 0.5% bounty
- 5×5 pixel glyph, 65-entry sine LUT

## Sources
- Whitepaper: https://www.token.works/ten-thousand-tokens-whitepaper.html
- Project site: https://www.tenthousandtokens.net/
- Docs: https://www.tenthousandtokens.net/docs
- TokenWorks announcement: https://x.com/token_works/status/2055365804762292614
- OpenSea collection: https://opensea.io/collection/ten-thousand-tokens
