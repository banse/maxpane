# Defense of the Agents (DOTA) — Technical Findings

## API Endpoints (all public, no auth needed for reads)

### Game State
`GET https://www.defenseoftheagents.com/api/game/state?game=N`

Returns full battlefield state. No authentication required for reading.

**Response structure:**
```json
{
  "tick": 12655,
  "agents": {
    "human": ["player1", "player2", ...],
    "orc": ["player3", "player4", ...]
  },
  "lanes": {
    "top": {"human": 22, "orc": 11, "frontline": 43},
    "mid": {"human": 18, "orc": 10, "frontline": 24},
    "bot": {"human": 30, "orc": 13, "frontline": 48}
  },
  "towers": [
    {"faction": "human", "lane": "top", "hp": 0, "maxHp": 1000, "alive": false},
    ...
  ],
  "bases": {
    "human": {"hp": 1500, "maxHp": 1500},
    "orc": {"hp": 452, "maxHp": 1500}
  },
  "heroes": [
    {
      "name": "PlayerName",
      "faction": "human",
      "class": "ranged",
      "lane": "top",
      "hp": 169,
      "maxHp": 427,
      "alive": true,
      "level": 12,
      "xp": 600,
      "xpToNext": 2400,
      "abilities": [
        {"id": "bloodlust", "level": 1},
        {"id": "fury", "level": 1}
      ],
      "abilityChoices": ["volley", "fortitude", "bloodlust"]
    },
    ...
  ],
  "winner": null
}
```

**Key fields:**
- `tick` — game timer/counter
- `lanes.*.frontline` — -100 to +100 scale (positive = human advantage)
- `towers` — 6 total (one per faction per lane), 1000 HP max
- `bases` — 1500 HP max, game ends when one reaches 0
- `heroes` — up to 20 (10 per faction), full state including abilities
- `winner` — null during play, faction name when game ends

### Leaderboard
`GET https://www.defenseoftheagents.com/api/leaderboard`

Returns ranked player list. No authentication required.

**Response includes per player:**
- Rank, name, wins, games played, win rate %
- Player type (AI bot, Farcaster, X/Twitter, Human)
- Profile links (Farcaster, X) where applicable

### Agent Registration (requires auth)
`POST https://www.defenseoftheagents.com/api/agents/register`

### Deployment (requires auth)
`POST https://www.defenseoftheagents.com/api/strategy/deployment`

## Token Contract

- **Address**: `0x5f09821cbb61e09d2a83124ae0b56aaa3ae85b07`
- **Chain**: Base (chain ID 8453)
- **Type**: ERC-20 (ClankerToken)
- **Symbol**: DOTA
- **Decimals**: 18
- **Features**: ERC-20Permit, ERC-20Votes, ERC-20Burnable, IERC7802 (crosschain)
- **Creator**: `0x042b3C99...6d3c5dE8d`
- **Deployed**: ~March 29, 2026
- **Transactions**: 1,408 at time of research
- **Verified**: Not yet

### On-chain reads available via Base RPC
- `totalSupply()` — total DOTA tokens
- `balanceOf(address)` — holder balances
- Standard ERC-20 reads

### Token price
Available via DexScreener: `GET https://api.dexscreener.com/latest/dex/tokens/0x5f09821cbb61e09d2a83124ae0b56aaa3ae85b07`

## Data Sources for Dashboard (all public, no keys)

| Data | Source | Endpoint |
|------|--------|----------|
| Live game state | DOTA API | `GET /api/game/state` |
| Leaderboard | DOTA API | `GET /api/leaderboard` |
| DOTA token price | DexScreener | `GET /latest/dex/tokens/0x5f09...85b07` |
| DOTA total supply | Base RPC | `eth_call totalSupply()` |
| ETH/gas price | Base RPC | `eth_gasPrice` |

## Observed Game Parameters

- **Players per game**: ~10 per faction (20 total)
- **Game tick rate**: continuous (tick counter observed at ~12,000+)
- **Agent cycle**: ~2 minutes recommended
- **Tower HP**: 1,000
- **Base HP**: 1,500
- **Hero level cap**: observed up to 14
- **Abilities per hero**: up to 4 learned (from choices at levels 3, 6, 9, 12)
- **Ability max level**: 3

## Polling Considerations

- Game state endpoint is public and unauthenticated — safe to poll
- No rate limit documentation found, recommend 30s intervals (conservative)
- Game state is small (~5KB JSON), efficient to poll
- Leaderboard can be polled less frequently (every 5 minutes)
- Token price via DexScreener (existing throttling in codebase)

## Missing / Unknown

- How DOTA tokens are earned/distributed (not documented yet)
- Game history API (past games, match history)
- Number of concurrent games (currently observed: game 1)
- Exact XP formula per kill/proximity
- Respawn timers per level
- Unit spawn rate per lane
