# FrenPet Performance Dashboard — Design Spec

## Purpose

A wallet-specific FrenPet dashboard focused on pet performance comparison. Shows how each pet is performing relative to the others and over time. Uses the standard 6-panel overview template.

## Dashboard Identity

- **Game select entry:** "FrenPet Performance"
- **Game ID:** `frenpet_perf`
- **Title bar:** `FrenPet · Performance · 0x030A...4A51 · 5 pets`
- **Requires wallet:** uses the wallet input screen if no wallet is configured in `~/.maxpane/config.toml`

## Data Sources

All data reuses existing infrastructure — no new APIs or RPC calls needed.

- **Managed pets:** `get_pets_by_owner(address)` via Ponder GraphQL (existing)
- **Per-pet fields:** score, win_qty, loss_qty, attack_points, defense_points, level, status
- **Score velocity:** computed from per-pet score history in cache (`pet_score_histories`)
- **Global data:** `top_pets` for context (existing)
- **Recent attacks:** filtered to wallet pet IDs (existing)

No on-chain RPC calls required — all data comes from the Ponder indexer and cache. This dashboard is lighter than the wallet dashboard.

## Layout (Standard 6-Panel Template)

```
┌──────────────────────────────────────────────────────────────────────┐
│ FrenPet · Performance · 0x030A...4A51 · 5 pets                     │
├──────────────┬──────────────┬──────────────┐                        │
│ TOTAL W/L    │ TOTAL SCORE  │ AVG WIN RATE │  ← Hero cards          │
│ 2,709 / 1,346│ 818K         │ 66.8%        │                        │
│ 4,055 battles│ across 5 pets│ across 5 pets│                        │
├──────────────┴──────┬───────┴──────────────┤                        │
│ PET COMPARISON      │ TRENDS               │  ← Middle row          │
│ # Name   Score WR%  │ Score    ▁▂▃ 818K    │                        │
│ ★ Kek    297K 68.3% │ Velocity ▅▆▇ +1.0K/hr│                        │
│ 2 Jeff   239K 70.5% │ Win Rate ▅▆▅ 66.8%   │                        │
│ 3 Duder  142K 66.2% │                      │                        │
│ 4 Walter  79K 63.8% ├──────────────────────┤                        │
│ 5 Kalle   60K 59.7% │ SIGNALS              │                        │
│                     │ Avg Win Rate   66.8% │                        │
│                     │ Score Velocity +1K/hr│                        │
│                     │ Weakest Pet    Kalle │                        │
│                     │ → Recommendation     │                        │
├─────────────────────┼──────────────────────┤                        │
│ ACTIVITY            │ PET VELOCITY         │  ← Bottom row          │
│ 18:42 Kek → Won +2k│ Kek     ▃▅▇█ +312/hr │                        │
│ 18:41 Jeff → Won +1k│ Jeffrey ▃▄▆█ +287/hr │                        │
│ ...                 │ Duder   ▂▃▅▇ +198/hr │                        │
│                     │ Walter  ▂▃▄▅ +124/hr │                        │
│                     │ Kalle   ▁▂▃▄  +89/hr │                        │
├─────────────────────┴──────────────────────┤                        │
│ q quit · r refresh · m menu · tab switch · 30s poll                 │
└──────────────────────────────────────────────────────────────────────┘
```

## Widget Specifications

### 1. Hero Cards — `FPPerfHero` (Horizontal, 3 boxes)

| Card | Primary value | Subtitle | Data source |
|------|--------------|----------|-------------|
| TOTAL W/L | `{wins}` green / `{losses}` red | `{total} total battles` | Sum of win_qty, loss_qty across all pets |
| TOTAL SCORE | Combined score with K/M suffix | `across {n} pets` | Sum of pet scores |
| AVG WIN RATE | Combined win rate % | `across {n} pets` | Total wins / total battles * 100 |

### 2. Pet Comparison Table — `FPPerfPets` (DataTable)

Columns: `#` (4) | `Name` (16) | `Score` (12) | `Win Rate` (10) | `ATK/DEF` (12) | `Velocity` (10)

- Star marker (★) for top pet by score
- Score with K/M suffix
- Win Rate as percentage: `win_qty / (win_qty + loss_qty) * 100`
- Velocity computed from per-pet score cache history (points/hour)
- Velocity colored: green if positive and high, yellow if moderate, dim if near zero
- Sorted by score descending
- Emoji-stripped pet names

### 3. Trends — `FPPerfTrends` (sparklines)

Three sparklines from cache time series:
- **Score** (green) — sum of all pet scores over time
- **Velocity** (cyan) — combined score velocity over time (pts/hr)
- **Win Rate** (yellow) — combined win rate over time

Width 20, standard block chars.

### 4. Signals — `FPPerfSignals` (key-value rows)

| Signal | Value | Indicator logic |
|--------|-------|----------------|
| Avg Win Rate | combined % | strong ≥60, balanced 40-60, weak <40 |
| Score Velocity | combined pts/hr | growing >0, stalled =0, declining <0 |
| Weakest Pet | name + win rate | needs work <60%, ok 60-70%, strong ≥70% |
| Recommendation | text string | based on signals |

### 5. Activity — `FPPerfActivity` (RichLog)

Same as wallet dashboard activity — recent battles filtered to wallet pet IDs. Reuse `FPWalletActivity` widget directly or copy the pattern.

### 6. Pet Velocity — `FPPerfVelocity` (per-pet sparklines)

One sparkline row per pet showing individual score velocity over time:
- Pet name (truncated to ~10 chars), sparkline (width 10), velocity value
- Color: green if ≥200/hr, cyan if ≥100/hr, yellow if ≥50/hr, dim if <50/hr
- Sorted by velocity descending
- Data from per-pet score cache history

## Implementation Approach

### New files

| File | Purpose |
|------|---------|
| `maxpane_dashboard/screens/frenpet_perf.py` | Screen (follows cattown.py pattern) |
| `maxpane_dashboard/widgets/frenpet/perf/` | Widget subdirectory (6 widgets) |
| `maxpane_dashboard/widgets/frenpet/perf/__init__.py` | Re-exports |
| `maxpane_dashboard/widgets/frenpet/perf/fpp_hero.py` | Hero cards |
| `maxpane_dashboard/widgets/frenpet/perf/fpp_pets.py` | Pet comparison DataTable |
| `maxpane_dashboard/widgets/frenpet/perf/fpp_trends.py` | Sparklines |
| `maxpane_dashboard/widgets/frenpet/perf/fpp_signals.py` | Signal indicators |
| `maxpane_dashboard/widgets/frenpet/perf/fpp_activity.py` | Battle feed (reuse wallet pattern) |
| `maxpane_dashboard/widgets/frenpet/perf/fpp_velocity.py` | Per-pet velocity sparklines |
| `maxpane_dashboard/analytics/frenpet_perf_signals.py` | Signal computation (pure functions) |

### Modified files

| File | Change |
|------|--------|
| `maxpane_dashboard/app.py` | Add perf manager, screen import, launch logic, game cycle |
| `maxpane_dashboard/screens/game_select.py` | Add "FrenPet Performance" entry |
| `maxpane_dashboard/__main__.py` | Add `frenpet_perf` to CLI choices |
| `maxpane_dashboard/themes/minimal.tcss` | Add CSS for FPP widget classes |

### Data flow

The performance dashboard reuses the same `FrenPetManager` data — all needed fields are already in the `fetch_and_compute()` return dict:
- `managed_pets` — pet objects with score, win_qty, loss_qty, attack_points, defense_points
- `pet_score_histories` — per-pet score time series for velocity calculation
- `pet_velocities` — already computed per-pet velocities
- `recent_attacks` — for activity feed
- `pet_names` — for name resolution in activity

No new data fetching methods needed. The screen just uses existing data differently.

### Velocity calculation

Score velocity (pts/hr) per pet is already computed by the manager via `calculate_velocity(history)` in `frenpet_signals.py`. The per-pet velocities are in the `pet_velocities` dict keyed by pet ID. For the combined velocity, sum all per-pet velocities.

### Wallet input

Same pattern as wallet and full dashboards — check `get_wallet()`, show `WalletInputScreen` if missing.

## Out of Scope

- Action recommendations dashboard (future — "What should I do next?")
- Per-pet detail drill-down (could be added as a future view)
- Historical W/L tracking (would need attack history caching)
