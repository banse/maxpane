# Cat Town Fishing Game -- Mechanics & Game Theory

> Research date: 2026-03-28
> Source: https://docs.cat.town/fishing/ and onchain analysis
> Chain: Base (Chain ID 8453)

## 1. Core Game Loop

1. **Select a fish pool** (Isabella's Lake at cat.town/fishing)
2. **Cast your bobber** and wait for a bite
3. **Reel in** via timing mini-game: stop on green (PURRFECT) or yellow (OK); red = fish escapes
4. **Identify your catch** -- costs $0.25 in KIBBLE per item, uses Gelato VRF for onchain randomness
5. Fish is minted as an ERC-721 NFT
6. Treasures and rare artifacts do NOT require identification
7. Repeat

## 2. Fish Species (35 across 5 rarities)

### Common (12 species, 0.5-10kg)
| Fish | Weight | Condition |
|------|--------|-----------|
| Bluegill | 0.5-1.2kg | Any |
| Pink Salmon | 2.5-5kg | Any |
| Amber Tilapia | 2-2.4kg | Any |
| Rainbow Trout | 0.5-2.5kg | Any |
| Smallmouth Bass | 1-3kg | Spring |
| Brook Trout | 0.5-2kg | Summer |
| Crappie | 0.5-1kg | Autumn |
| Yellow Perch | 0.5-1.5kg | Winter |
| Oddball | 5-10kg | Morning |
| Crab | 0.5-1kg | Afternoon |
| Goby | 1-2kg | Evening |
| Eel | 0.5-3kg | Night |

### Uncommon (5 species, 1-22.5kg)
| Fish | Weight | Condition |
|------|--------|-----------|
| Pike | 4-12kg | Any |
| Tiger Trout | 1-21kg | Morning |
| Tambaqui | 6-21kg | Afternoon |
| Peacock Bass | 2.5-22.5kg | Evening |
| Common Carp | 2-21kg | Night |

### Rare (6 species, 10-43kg)
| Fish | Weight | Condition |
|------|--------|-----------|
| Catfish | 18-40kg | Any |
| Blue Mahseer | 20-42kg | Morning |
| Taimen | 10-42.5kg | Afternoon |
| Twilight Barbel | 14-42kg | Evening |
| Redtail Catfish | 13-42.5kg | Night |
| King Snapper | 25-43kg | Rain/Storm |

### Epic (6 species, 30-45kg)
| Fish | Weight | Condition |
|------|--------|-----------|
| Sun-Kissed Catfish | 30-43.5kg | Sun |
| Amberfin Catfish | 32.5-45kg | Sun/Heatwave |
| Paddlefish | 35-43.5kg | Morning |
| Goliath Tigerfish | 38-43.5kg | Afternoon |
| Arapaima | 35-43kg | Evening |
| Young Bull Shark | 38-44kg | Night |

### Legendary (6 species, 35-50kg)
| Fish | Weight | Condition |
|------|--------|-----------|
| Elusive Marlin | 45-50kg | Storm |
| Radiant Catfish | 35-47.5kg | Heatwave |
| Alligator Gar | 42-46.5kg | Spring |
| Muskellunge | 42.5-45.5kg | Summer |
| Freshwater Stingray | 40-47kg | Autumn |
| Sturgeon | 42-46kg | Winter |

## 3. Treasures (33 items across 5 rarities)

| Rarity | Items | Value Range |
|--------|-------|-------------|
| Common | Coffee Cup, Old Boot, Driftwood (Wind/Storm), Metal Rivets, Soda Can, Bike Tire, Soggy Chips | $0.10-$0.75 |
| Uncommon | Meteorite Fragment, Pirate Doubloon (Wind/Storm), Pristine Snowflake (Snow), Vintage Harmonica, Solar Pearl (Sun/Heatwave), Dubious Tome, Old Wristwatch, Ancient Fossil | $1.50-$5.00 |
| Rare | Mysterious Locket, Freshwater Pearl, Bronze Goblet, Lovely Duck (Rain/Storm), Misty Duck (Rain/Storm), Gold Band, Snow Globe (Snow) | $7.50-$30.00 |
| Epic | Message in a Bottle, Jade Figurine, Fancy Duck (Rain), Lost Compass (Wind), Gilded Sundial (Heatwave), Diamond, Frozen Tusk (Snow) | $0.10-$100.00 |
| Legendary | Dawnbreak Ring (Morning), Solar Ring (Afternoon), Twilight Ring (Evening), Moonlight Ring (Night) | $250.00 each |

## 4. Conditions System

Catches are gated by three condition axes:
- **Time of Day:** Morning, Afternoon, Evening, Night
- **Weather:** Sun, Rain, Wind, Storm, Heatwave, Snow
- **Season:** Spring, Summer, Autumn, Winter

Higher-rarity catches generally require more specific conditions.

## 5. Hot Streaks

- Every PURRFECT catch (green segment) earns a **hot streak charge**
- Charges slow down the catch bar, making subsequent perfects easier (compounding advantage)
- Higher streaks increase **double-dip chance** (catching 2 fish at once)
- With Apex Predator rod, double-dips become **triple-dips** (3 fish at once)
- Upgradeable via: Streak Strength, Charge Limits, Double-Dip Chance

## 6. Fishing Rods (6 tiers, gated by reputation)

| Rod | Reputation Required | Bite Time | Grace Period | Double-Dip | Streak Bonuses |
|-----|---------------------|-----------|-------------|------------|----------------|
| Rookie's Rod | Free | - | +3 sec | 10% | - |
| Balanced Reed | Friendly (9,000) | -1 sec | +2 sec | 40% | Max +1, Strength +15% |
| Sterling Pursuit | Companion (36,000) | -4 sec | +1 sec | 65% | Max +2, Strength +35% |
| Expert's Edge | Devoted (144,000) | -8 sec | +2 sec | 80% | Min +1, Max +3, Strength +60% |
| Crystal Elite | Cherished (720,000) | -9 sec | +1 sec | 100% | Min +1, Max +4, Strength +80%, +50% Second Chance |
| Apex Predator | Cherished (720,000) | -10 sec | +2 sec | 75% (Triple-Dip!) | Min +2, Max +4, Strength +100% |

## 7. Reputation System (10 stages)

| Stage | Min Points | Key Unlocks |
|-------|-----------|-------------|
| Cold | -6,000 | Negative standing |
| Cautious | -3,000 | Negative standing |
| Neutral | 0 | Starting point |
| Acquaintance | 3,000 | Basic perks |
| Friendly | 9,000 | Balanced Reed rod |
| Companion | 36,000 | Sterling Pursuit rod |
| Devoted | 144,000 | Expert's Edge rod |
| Cherished | 720,000 | Crystal Elite / Apex Predator rod |
| Beloved | 3,600,000 | Premium rewards |
| Inseparable | 21,600,000 | Best rewards |

Earned by: fishing with Isabella, gacha with Rosie/K.K. Bento, shopping, quests, events.

## 8. Weekly Competition

- **Schedule:** Saturday morning through Sunday night (UTC)
- **Entry:** Automatic -- all fish caught during the window are entered
- **Ranking:** By heaviest single fish caught
- **Prize Pool Source:** 10% of all KIBBLE spent on fish identification during the week

**Leaderboard Prize Distribution (Top 10):**

| Rank | Share |
|------|-------|
| 1st | 30% |
| 2nd | 20% |
| 3rd | 10% |
| 4th-5th | 8% each |
| 6th | 7% |
| 7th | 5% |
| 8th-10th | 4% each |

## 9. Fish Raffle

- **Host:** Paulie
- **Drawing:** 8pm Friday UTC (before weekend tournament)
- **Ticket Cost:** 20kg of fish per ticket
- **Free Entry:** Everyone gets 1 free ticket per week
- **Ticket Purchase Window:** Monday through Friday (UTC)
- Progressive leveling: ticket purchases fill a shared progress bar; higher levels unlock larger prize pools
- Prize pool funded from a portion of weekend fishing tournament rewards

## 10. Identification Fee Revenue Split

When a player pays $0.25 KIBBLE to identify a fish:

| Destination | Share |
|-------------|-------|
| Caught Treasures (rewards pool) | 70% |
| Leaderboard Prize Pool | 10% |
| KIBBLE Stakers | 10% |
| Town Treasury | 7.5% |
| Burned (permanent deflation) | 2.5% |

## 11. Gacha System

- **Location:** Rosie's or K.K. Bento's shop
- **Cost:** $0.45 KIBBLE + $0.05 ETH per play
- **Limit:** 5 plays/day (resets 00:00 UTC)
- **5 Rarity Tiers:** Common, Uncommon, Rare, Epic, Legendary
- **9 Permanent Collections:** Toy Minis, Daruma Dolls, Plant Minis, Villagers Minis, Friends of Cat Town, Postcards, Key Items, Red Envelopes, Treasures
- **5 Seasonal Collections** (rotate quarterly)
- **Top Prize:** Lucky Gold Cat (worth $777 in KIBBLE)
- Revenue share: portion goes to KIBBLE stakers (paid Wednesdays)

## 12. Token Economics

### KIBBLE Token
- **Total Supply:** 1,000,000,000 (1B)
- **Burned:** Over 553M (66%+)
- **Circulating:** ~446.7M
- **Holders:** ~28,500
- **Buy/Sell Tax:** 3% each (1% treasury, 1% liquidity, 1% developer)
- **In-game Sales Tax:** 5% on all item sales to NPCs
- **Available on:** Uniswap, Hydrex

### BARON Token
- **Platform:** Virtuals Protocol (AI agent token)
- **Utility:** Hold 1M+ BARON to unlock Baron's Bounties (first-come challenges for KIBBLE rewards)
- **DEX:** Uniswap (BARON/WETH, BARON/VIRTUAL pools)

### Founders Collection NFT
- **Supply:** 1,555 unique cat PFPs

## 13. Staking (Revenue Share)

- **Location:** Wealth & Whiskers Bank (cat.town/bank/staking)
- **Mechanism:** Deposit KIBBLE, earn proportional share of weekly game revenue
- **Payout Schedule:**
  - Mondays: Fishing revenue share
  - Wednesdays: Gacha revenue share
- No lock-up periods mentioned
- Rewards scale with total game activity (more players = bigger staker payouts)

## 14. Special Events (Seasonal)

Past/upcoming events introduce limited-time fish, treasures, and conditions:
- Aavegotchi Halloween Fishing (Oct 27-31) -- ghost fish and cursed treasures
- Thanksgiving Fishing Weekend
- Festive Fishing Frenzy (Christmas)
- Valentines Fishing
- St Patrick's Fishing
- Base App Launch Event

## 15. Referral / Pioneer Program

- Pioneers earn 1 cent USDC per fish caught by referrals AND 1 cent per gacha spin
- Daily USDC payouts at 00:00 UTC
- Up to $500/week cap
- Referred players get a free fishing rod

---

## Game Theory Analysis

### Optimal Strategy Considerations

**Fishing Efficiency:**
- The core bottleneck is the **timing mini-game** (client-side skill check, not purely onchain)
- Hot streak mechanics create compounding returns -- consistent perfect catches should be prioritized
- Rod progression is reputation-gated -- identification volume is the primary reputation driver

**Weekend Competition:**
- Only the heaviest SINGLE fish matters, not total volume
- Legendary fish (45-50kg) only appear in specific conditions (Storm, Heatwave, specific seasons)
- Optimal weekend strategy: fish only during favorable conditions for legendary spawns
- During weekdays: maximize volume for reputation, raffle tickets, and prize pool contribution

**Resource Allocation:**
- ID cost ($0.25 KIBBLE) is the primary sink -- 70% flows to treasure pool, creating a redistribution mechanism
- Fish weight converts to raffle tickets at 20kg/ticket -- excess weight has value even if not competition-winning
- Staking KIBBLE earns passive revenue from ALL players' fishing and gacha activity
- The 2.5% burn creates continuous deflation -- long-term KIBBLE appreciation thesis

**EV Calculations:**
- Per identification: $0.25 cost -> 70% chance of treasure ($0.10 to $250.00 range) + reputation points
- Staking yield = (your_stake / total_staked) * (10% of all ID fees + gacha revenue share)
- Competition EV = P(top_10) * prize_share * weekly_prize_pool
- Raffle EV = (your_tickets / total_tickets) * raffle_prize_pool

**Key Differences from RugPull Bakery:**

| Aspect | RugPull Bakery | Cat Town Fishing |
|--------|---------------|-----------------|
| Core action | Bake cookies (gas only) | Fish + Identify ($0.25 KIBBLE) |
| Competition | Team bakery vs bakery | Individual leaderboard (heaviest fish) |
| Randomness | VRF for boosts/attacks | VRF for fish identification + client-side timing |
| Currency | Cookies (non-transferable) | KIBBLE (ERC-20, tradeable) |
| Time horizon | Season-scoped (~2 weeks) | Ongoing weekly cycles |
| Strategy focus | Boost/attack resource allocation | Condition-based fishing timing |
| Revenue model | Season prize pool (winner-take-all) | Revenue share (staking + competition + raffle) |
| Automation potential | High (bake is gas-only tx) | Lower (timing mini-game is skill-based) |
