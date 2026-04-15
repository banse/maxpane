# FrenPet Wallet Dashboard — Design Spec

## Purpose

A wallet-specific FrenPet dashboard focused on tracking earnings and rewards for your pets. Uses the standard 6-panel overview template (same layout as Bakery, Cat Town, DOTA, OCM, Base Trading dashboards).

## Dashboard Identity

- **Game select entry:** "FrenPet Wallet" — separate from the existing "FrenPet" (overview) and "FrenPet Full" (multi-view) dashboards
- **Game ID:** `frenpet_wallet`
- **Title bar:** `FrenPet · Wallet · 0x030A...4A51 · 5 pets`
- **Requires wallet:** uses the wallet input screen (same as FrenPet Full) if no wallet is configured in `~/.maxpane/config.toml`

## Data Sources

All data comes from existing infrastructure — no new APIs needed.

### On-chain (Base RPC calls to Diamond contract)

Contract: `0x0e22b5f3e11944578b37ed04f5312dfc246f443c` on Base

| Function | Returns | Used for |
|----------|---------|----------|
| `pendingEth(petId)` | uint256 (wei) | Pending ETH per pet |
| `ethOwed(petId)` | uint256 (wei) | Total ETH owed per pet |
| `fpOwed(petId)` | uint256 (wei) | Claimable FP per pet |
| `calculateFpPerSecond(petId)` | uint256 | FP earning rate per pet |
| `userShares(address)` | uint256 | Wallet's staked FP shares |
| `totalShares()` | uint256 | Total pool shares |
| `totalFpInPool()` | uint256 | Total FP in staking pool |

### GraphQL (Ponder indexer)

- `get_pets_by_owner(address)` — all pets for the wallet (existing method, must pass checksummed address — no `.lower()`)

### Existing manager data

- `managed_pets` — pet objects with score, win_qty, loss_qty, attack_points, defense_points
- `pet_score_histories` — per-pet score time series from cache
- `recent_attacks` — filtered to wallet's pet IDs for activity feed
- ETH price from DexScreener (for USD conversion)

## Layout (Standard 6-Panel Template)

```
┌──────────────────────────────────────────────────────────────────────┐
│ FrenPet · Wallet · 0x030A...4A51 · 5 pets                          │
├──────────────┬──────────────┬──────────────┐                        │
│ ETH REWARDS  │ POOL SHARE   │ APR / ROI    │  ← Hero cards          │
│ 0.0847 ETH   │ 0.12%        │ 34.2%        │                        │
│ ~$172 · 5pets│ of 677K FP   │ on 2,450 FP  │                        │
├──────────────┴──────┬───────┴──────────────┤                        │
│ YOUR PETS           │ TRENDS               │  ← Middle row          │
│ # Name    Score W/L │ Total Score ▁▂▃ 818K │                        │
│ ★ Kek     297K  ... │ ETH Rewards ▁▂▃ 0.08 │                        │
│ 2 Jeffrey  239K ... │ Win Rate    ▅▆▅  68% │                        │
│ 3 Duder   142K  ... │                      │                        │
│ 4 Walter   79K  ... ├──────────────────────┤                        │
│ 5 Kalle    60K  ... │ SIGNALS              │                        │
│                     │ FP/sec    0.042      │                        │
│                     │ Win Rate  68.4%      │                        │
│                     │ Pool Share 0.12%     │                        │
│                     │ → Recommendation     │                        │
├─────────────────────┼──────────────────────┤                        │
│ ACTIVITY            │ BEST PLAYS           │  ← Bottom row          │
│ 18:42 Kek → Won +2k│ Top Earner: Kek      │                        │
│ 18:41 Jeff → Won +1k│ Most Efficient: Jeff │                        │
│ ...                 │                      │                        │
├─────────────────────┴──────────────────────┤                        │
│ q quit · r refresh · m menu · tab switch · 30s poll                 │
└──────────────────────────────────────────────────────────────────────┘
```

## Widget Specifications

### 1. Hero Cards — `FPWalletHero` (Horizontal, 3 boxes)

| Card | Primary value | Subtitle | Data source |
|------|--------------|----------|-------------|
| ETH REWARDS | Sum of `pendingEth(petId)` + `ethOwed(petId)` for all pets, formatted as ETH | `~${usd_value} · {n} pets` | On-chain RPC + ETH price |
| REWARD POOL SHARE | `userShares / totalShares * 100` | `of {totalFpInPool} FP pool` | On-chain RPC |
| APR / ROI | Annualized: `(eth_earned_per_year / fp_staked_value_in_eth) * 100` | `on {userShares} FP staked` | On-chain RPC + ETH price |

**APR calculation:**
- `fp_per_second` = sum of `calculateFpPerSecond(petId)` for all pets
- `fp_per_year` = `fp_per_second * 86400 * 365`
- `eth_per_year` = estimated from current `pendingEth` rate (extrapolate from cache history)
- `staked_fp` = `userShares(address)`
- APR = `eth_per_year / (staked_fp * fp_price_in_eth) * 100`

### 2. Your Pets Table — `FPWalletPets` (DataTable)

Columns: `#` (4) | `Name` (16) | `Score` (12) | `W/L` (12) | `ATK/DEF` (12) | `ETH` (8)

- Star marker (★) for top pet by score
- Score formatted with K/M suffix
- W/L as `{wins}/{losses}`
- ETH shows per-pet `pendingEth + ethOwed` in ETH
- Sorted by score descending
- Emoji-stripped pet names (reuse `_EMOJI_RE`)

### 3. Trends — `FPWalletTrends` (sparklines)

Three sparklines from cache time series:
- **Total Score** (green) — sum of all pet scores over time
- **ETH Rewards** (cyan) — total pending ETH over time
- **Win Rate** (yellow) — combined win rate over time

Uses the standard sparkline pattern (block chars ▁▂▃▄▅▆▇█, width 20).

### 4. Signals — `FPWalletSignals` (key-value rows)

| Signal | Value | Indicator |
|--------|-------|-----------|
| FP/sec | sum of `calculateFpPerSecond` | earning/idle |
| Win Rate | combined wins / (wins + losses) | strong/balanced/weak |
| Pool Share | userShares / totalShares % | growing/stable/small |
| Recommendation | computed from signals | text string |

### 5. Activity — `FPWalletActivity` (RichLog)

Recent battles filtered to wallet's pet IDs only. Same format as existing FP activity:
`{time} {pet_name} → {opponent} Won/Lost +/-{points}`

Uses `pet_names` dict for name resolution, emoji-stripped.

### 6. Best Plays — `FPWalletBestPlays` (tentative, may change later)

Two sections:
- **Top Earner** — pet with highest score, showing W/L and win rate
- **Most Efficient** — pet with best win rate (min 10 battles)

## Implementation Approach

### New files

| File | Purpose |
|------|---------|
| `maxpane_dashboard/screens/frenpet_wallet.py` | Screen (follows cattown.py pattern) |
| `maxpane_dashboard/widgets/frenpet/wallet/` | Widget subdirectory (6 widgets) |
| `maxpane_dashboard/widgets/frenpet/wallet/__init__.py` | Re-exports |
| `maxpane_dashboard/widgets/frenpet/wallet/fpw_hero.py` | Hero cards |
| `maxpane_dashboard/widgets/frenpet/wallet/fpw_pets.py` | Pets DataTable |
| `maxpane_dashboard/widgets/frenpet/wallet/fpw_trends.py` | Sparklines |
| `maxpane_dashboard/widgets/frenpet/wallet/fpw_signals.py` | Signal indicators |
| `maxpane_dashboard/widgets/frenpet/wallet/fpw_activity.py` | Battle feed |
| `maxpane_dashboard/widgets/frenpet/wallet/fpw_best_plays.py` | Top earner / most efficient |
| `maxpane_dashboard/analytics/frenpet_wallet_signals.py` | Signal computation (pure functions) |

### Modified files

| File | Change |
|------|--------|
| `maxpane_dashboard/app.py` | Add wallet manager, screen import, launch logic, game cycle |
| `maxpane_dashboard/screens/game_select.py` | Add "FrenPet Wallet" entry |
| `maxpane_dashboard/__main__.py` | Add `frenpet_wallet` to CLI choices |
| `maxpane_dashboard/themes/minimal.tcss` | Add CSS for FPW widget classes |
| `maxpane_dashboard/data/frenpet_manager.py` | Add on-chain reward fetching methods |
| `maxpane_dashboard/data/frenpet_client.py` | Add RPC calls for `pendingEth`, `ethOwed`, `userShares`, etc. |

### Data flow

1. `FrenPetManager.fetch_and_compute()` already fetches managed pets via GraphQL
2. Add new method `fetch_wallet_rewards(pet_ids, wallet_address)` to `FrenPetClient` that makes RPC calls for ETH/FP reward data
3. Manager calls this, computes aggregates, adds to return dict
4. Screen distributes data to widgets via `update_data()` calls

### Wallet input

Reuses the existing wallet input screen and `~/.maxpane/config.toml` persistence. Same flow as FrenPet Full — if no wallet configured, prompt before launching.

### On-chain call budget

Per refresh cycle (every 30s):
- `pendingEth(petId)` × 5 pets = 5 calls
- `ethOwed(petId)` × 5 pets = 5 calls  
- `calculateFpPerSecond(petId)` × 5 pets = 5 calls
- `userShares(address)` = 1 call
- `totalShares()` = 1 call
- `totalFpInPool()` = 1 call

Total: 18 RPC calls per cycle. All are `view` functions (free, no gas). Serialize to avoid rate limits on public Base RPC.

## Out of Scope

- Pet performance dashboard (future — "How are my pets performing?")
- Action recommendations dashboard (future — "What should I do next?")
- FP claiming automation (backend concern, not dashboard)
- ETH claiming automation (backend concern, not dashboard)
- Best Plays content is tentative and may change
