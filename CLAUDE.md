# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MaxPane is an automation service for the **RugPull Bakery** game on **Abstract** blockchain (chain 2741). It is the RugPull Bakery equivalent of what AutoPet (in `../autopet/`) is to FrenPet. MaxPane reuses AutoPet's proven infrastructure (executor, transactor, event bus, scheduler, API/dashboard, keystore, nonce management, spending guard) and adapts the game-specific logic for a different game on a different chain.

## Relationship to AutoPet

AutoPet (`../autopet/`) is the reference implementation. Its architecture should be followed:
- **Reuse directly:** RPCProvider, Signer, NonceManager, Transactor, SpendingGuard, EventBus, GasMonitor, ActionScheduler, SQLite models pattern, FastAPI structure, React dashboard structure
- **Adapt:** Game-specific contracts, API client, strategy logic, service loop actions, game mechanics calculations
- **Drop:** Commit-reveal executor (RugPull Bakery uses VRF, not commit-reveal), sniper system (no 1v1 PvP targeting), indexer/Ponder GraphQL (replaced by tRPC API), pet agents (replaced by bakery agent)

## Target Game: RugPull Bakery

### Chain & Network
- **Chain:** Abstract (Chain ID 2741)
- **RPC:** `https://api.mainnet.abs.xyz`
- **Explorer:** `https://abscan.org`
- **Currency:** ETH for gas/buy-in; Cookies are in-game season-scoped balances (NOT ERC-20 tokens)
- **Wallet:** Abstract Global Wallet (standard EOA signing works for contract calls)

### Contract Addresses
| Contract | Address |
|----------|---------|
| SeasonManager | `0x327E83B8517f60973473B2F2cA0eC3a0FEBB5676` |
| PrizePool | `0x7FDF300dbe9588faB6787C2875376C8a0521Eb72` |
| PlayerRegistry | `0x663D69eCFF14b4dbD245cdac03f2e1DEb68Ed250` |
| ClanRegistry | `0xbffCc2C852f6b6E5CFeF8630a43B6CD06194E1AC` |
| BoostManager | `0xa8a91aC36dD6a1055D36bA18aE91348f3AA3d7F9` |
| Bakery | `0xaEB8Eef0deAbA98E3B65f6311DD7F997e72B837a` |

### Key Contract Functions
- `Bakery.bake()` — bake cookies (0 wei, just gas)
- `BoostManager.purchaseBoost(boostId, targetClanId)` — buy boost/attack (requires VRF fee as msg.value)
- `BoostManager.getVrfFee()` — current VRF fee in wei
- `PlayerRegistry.register(address referrer, uint256 clanId)` — register for season (msg.value = buy-in)
- `PlayerRegistry.getBuyInAmount()` — current season buy-in in wei
- `ClanRegistry.createClan(string name)` — create a bakery
- `ClanRegistry.joinClan(uint256 clanId)` — join existing bakery
- `SeasonManager` — season state queries

### Game Mechanics
- **Baking:** Core action, produces cookies for your bakery. Free (gas only). Can be automated on interval.
- **Boosts** (spend cookies to buff your bakery):
  | ID | Name | Success % | Cookie Cost | Effect | Duration |
  |----|------|-----------|-------------|--------|----------|
  | 1 | Ad Campaign | 60% | 1.2M | 1.25x | 4h |
  | 2 | Motivational Speech | 40% | 800K | 1.25x | 4h |
  | 3 | Secret Recipe | 35% | 2.5M | 1.5x | 8h |
  | 4 | Chef's Help | 50% | 4.5M | 2x | 8h |
- **Attacks** (spend cookies to debuff rival bakeries):
  | ID | Name | Success % | Cookie Cost | Effect | Duration |
  |----|------|-----------|-------------|--------|----------|
  | 5 | Recipe Sabotage | 60% | 1.2M | -25% | 4h |
  | 6 | Fake Partnership | 35% | 600K | -25% | 4h |
  | 7 | Kitchen Fire | 20% | 3.2M | -100% | 2h |
  | 8 | Supplier Strike | 30% | 2.2M | -50% | 4h |
- Failed boosts/attacks still consume cookies
- Max 5 active boosts and 5 active debuffs per bakery simultaneously
- Leaving a bakery burns 50% of cookies
- Cookies reset each season
- VRF fee (~0.000022 ETH) required as msg.value for boost/attack transactions

### Game API (tRPC)
Base: `https://www.rugpullbakery.com/api/trpc`
- `leaderboard.getActiveSeason` — current season state
- `leaderboard.getTopBakeries` — leaderboard
- `leaderboard.getBakeryById` — specific bakery data
- `leaderboard.getBakeryMembers` — member roster
- `leaderboard.getPlayerBakery` — player's current bakery
- `leaderboard.getMyBakeryInit` — initialization state
- `leaderboard.getActivityFeed` — recent activity

**Canonical rule:** If `/skill.md` and `/agent.json` ever disagree with a fresh live contract read, use the live contract read.

### Bootstrap Endpoints
- `https://www.rugpullbakery.com/agent.json` — machine-readable live state, costs, actions
- `https://www.rugpullbakery.com/skill.md` — full prose gameplay guide

## Architecture (adapted from AutoPet)

```
maxpane/
├── backend/
│   ├── core/                  # Shared kernel (same pattern as autopet)
│   │   ├── config.py          # Settings with MAXPANE_ env prefix
│   │   ├── models.py          # SQLAlchemy models (bake logs, boost/attack logs, tx logs)
│   │   ├── events.py          # Event bus (BakeCompleted, BoostResult, AttackResult, etc.)
│   │   └── contracts.py       # RPCProvider + BakeryContracts (6 contracts)
│   ├── scheduler/
│   │   ├── engine.py          # Action scheduling (bake, boost, attack)
│   │   └── gas_monitor.py     # Abstract chain gas monitoring
│   ├── strategy/
│   │   ├── boost.py           # When to boost, which boost to use
│   │   ├── attack.py          # Target bakery selection, attack type selection
│   │   └── bake.py            # Bake interval optimization
│   ├── executor/              # Reuse from autopet, change chain_id to 2741
│   │   ├── signer.py
│   │   ├── transactor.py
│   │   └── nonce_manager.py
│   ├── api/                   # FastAPI dashboard
│   │   ├── app.py
│   │   └── routes/
│   ├── game_api.py            # tRPC client for rugpullbakery.com
│   ├── abis/                  # ABI JSONs for all 6 contracts
│   ├── main.py                # Entry point
│   └── service_loop.py        # Core loop: bake, check boosts, check attacks
├── frontend/                  # React + Vite dashboard
├── scripts/
├── data/
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## Key Differences from AutoPet

| Aspect | AutoPet (FrenPet) | MaxPane (RugPull Bakery) |
|--------|-------------------|--------------------------|
| Chain | Base (8453) | Abstract (2741) |
| Core action | Battle (bonk) every 30min | Bake cookies continuously |
| Randomness | Commit-reveal (2 txs) | VRF (1 tx + fee) |
| Competition | 1v1 pet battles | Team bakery vs bakery |
| Currency | $FP (ERC-20) | Cookies (contract balance, non-transferable) |
| Reward model | Ongoing ETH from leaderboard | Season prize pool (winner-take-all) |
| Strategy focus | Target selection (which pet to attack) | Resource allocation (when to boost vs attack vs save) |
| Time horizon | Indefinite (pet lifetime) | Season-scoped (~2 weeks) |

## Build & Run

### Backend
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Frontend
```bash
cd frontend && npm install && npm run build
```

### Run
```bash
python -m backend.main
# or
./scripts/start.sh
```

### Tests
```bash
pytest                          # all tests
pytest tests/strategy/          # strategy tests only
pytest tests/strategy/test_boost.py::test_ev_calculation  # single test
pytest -x                       # stop on first failure
```

### Environment Variables
```
MAXPANE_KEYSTORE_PATH=./data/keystore.json
MAXPANE_KEYSTORE_PASSWORD=<password>
MAXPANE_RPC_URL=https://api.mainnet.abs.xyz
MAXPANE_BACKUP_RPC_URL=<backup-rpc>
MAXPANE_BAKERY_ID=<your-bakery-id>
MAXPANE_DAILY_GAS_LIMIT_ETH=0.01
MAXPANE_DRY_RUN=false
MAXPANE_LOG_LEVEL=INFO
MAXPANE_API_PORT=8421
MAXPANE_API_TOKEN=<random-token>
```

## Strategy Considerations

The bot's primary value is in strategic decision-making, not just automation:
- **Baking** is the baseline — automate at regular intervals
- **Boost timing** — use expected value: `EV = success_rate * cookie_cost * (multiplier - 1) * remaining_duration_value - cookie_cost`. Stack boosts for multiplicative effect
- **Attack timing** — target the leading bakery, consider their active boost state. EV calculation must account for rival's cookie production rate and remaining season time
- **Cookie budget** — failed attempts burn cookies. Conservative early, aggressive when trailing near season end
- **Leaderboard monitoring** — poll `getTopBakeries` to inform boost/attack decisions
- **Season awareness** — strategies should shift based on time remaining in season
