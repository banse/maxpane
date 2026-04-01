# RugPull Bakery - Game Mechanics

## Overview

RugPull Bakery is a team-based cookie-baking competition on Abstract blockchain (Chain ID 2741). Players join bakeries (teams), bake cookies, use boosts/attacks, and compete for a season prize pool.

## Chain & Network

- **Chain:** Abstract (Chain ID 2741)
- **RPC:** `https://api.mainnet.abs.xyz`
- **Explorer:** `https://abscan.org`
- **Currency:** ETH for gas/buy-in; Cookies are in-game season-scoped balances (NOT ERC-20 tokens)
- **Wallet:** Abstract Global Wallet (standard EOA signing works)

## Contract Addresses (Season 3)

| Contract | Address |
|----------|---------|
| SeasonManager | `0x327E83B8517f60973473B2F2cA0eC3a0FEBB5676` |
| PrizePool | `0x7FDF300dbe9588faB6787C2875376C8a0521Eb72` |
| PlayerRegistry | `0x663D69eCFF14b4dbD245cdac03f2e1DEb68Ed250` |
| ClanRegistry | `0xbffCc2C852f6b6E5CFeF8630a43B6CD06194E1AC` |
| BoostManager | `0xa8a91aC36dD6a1055D36bA18aE91348f3AA3d7F9` |
| Bakery | `0x080F7ad315AB65f02A821F072170d469D444A6c4` |

**Note:** Bakery contract address changed from `0xaEB8...` (Season 1-2) to `0x080F...` (Season 3+).

## Season Structure

- Seasons last ~14 days
- Players register with a buy-in (currently 0.002 ETH)
- Prize pool = seed amount + all buy-ins
- Season 3: ~9.37 ETH prize pool, ~1.2 ETH seed

## Reward Distribution (Season 3+)

**Changed from winner-take-all to top-3 split.**

Prize pool is split among the top 3 bakeries. Exact split ratios TBD -- until confirmed, assume **equal split (33.3% each)**.

The PrizePool contract uses a Merkle-root-based claim system (`claimPrize` requires merkle proofs). Distribution is computed off-chain and committed as a `resultsRoot` after season ends, so split ratios can change per season without contract changes.

**Impact on strategy:**
- Finishing 2nd or 3rd now has significant value (was zero before)
- Defending a top-3 position becomes viable strategy
- Attack calculus changes: attacking #2 while you're #3 may not be optimal anymore
- Late-join EV improves: you're betting on top-3 finish, not just winning

## Core Actions

### Baking
- Produces cookies for your bakery
- Free (gas only, ~0.000022 ETH)
- Core action, automate on interval

### Boosts (spend cookies to buff your bakery)

| ID | Name | Success % | Cookie Cost | Effect | Duration |
|----|------|-----------|-------------|--------|----------|
| 1 | Ad Campaign | 60% | 1.2M | 1.25x | 4h |
| 2 | Motivational Speech | 40% | 800K | 1.25x | 4h |
| 3 | Secret Recipe | 35% | 2.5M | 1.5x | 8h |
| 4 | Chef's Help | 50% | 4.5M | 2.0x | 8h |

### Attacks (spend cookies to debuff rival bakeries)

| ID | Name | Success % | Cookie Cost | Effect | Duration |
|----|------|-----------|-------------|--------|----------|
| 5 | Recipe Sabotage | 60% | 1.2M | -25% | 4h |
| 6 | Fake Partnership | 35% | 600K | -25% | 4h |
| 7 | Kitchen Fire | 20% | 2.2M | **-75%** | 2h |
| 8 | Supplier Strike | 30% | 2.2M | -50% | 4h |

**Kitchen Fire changed:** Cost reduced from 3.2M to 2.2M, debuff changed from -100% to -75%.

## Key Rules

- Failed boosts/attacks still consume cookies
- Max 5 active boosts and 5 active debuffs per bakery simultaneously
- **Leaving a bakery burns 100% of cookies** (changed from 50%)
- Cookies reset each season
- VRF fee (~0.000022 ETH) required as msg.value for boost/attack transactions
- Cookie scale: 10000 (raw values divided by 10000 for display)

## Game API (tRPC)

Base: `https://www.rugpullbakery.com/api/trpc`

- `leaderboard.getActiveSeason` -- current season state
- `leaderboard.getTopBakeries` -- leaderboard
- `leaderboard.getBakeryById` -- specific bakery data
- `leaderboard.getBakeryMembers` -- member roster
- `leaderboard.getPlayerBakery` -- player's current bakery
- `leaderboard.getMyBakeryInit` -- initialization state
- `leaderboard.getActivityFeed` -- recent activity

## Bootstrap Endpoints

- `https://www.rugpullbakery.com/agent.json` -- machine-readable live state
- `https://www.rugpullbakery.com/skill.md` -- full prose gameplay guide

## Changelog

| Date | Change |
|------|--------|
| 2026-03-29 | Prize distribution changed from winner-take-all to top-3 split (ratios TBD) |
| 2026-03-29 | Leave penalty changed from 50% to 100% of cookies |
| 2026-03-29 | Kitchen Fire: cost 3.2M→2.2M, debuff -100%→-75% |
| 2026-03-29 | Bakery contract address changed to 0x080F... |
