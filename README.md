# MaxPane

Terminal dashboards for onchain games, NFT collections, and trading on Base, Abstract, and Ethereum.

Track leaderboards, signals, trends, and analytics for 9 onchain projects — all from your terminal.

Every dashboard is **read-only and keyless**: public RPCs and public APIs only, no API keys of any
kind, no wallet, no signing, no transactions.

## Dashboards

| Game | Chain | What you see |
|------|-------|-------------|
| **Base Trading** | Base | Trending tokens, volume, ETH price, signals |
| **FrenPet** | Base | Pet battles, leaderboard, activity, trends |
| **Cat Town** | Base | Fishing competition, KIBBLE economy, catches |
| **DOTA** | Base | Defense of the Agents idle MOBA, heroes, lanes |
| **Rugpull Bakery** | Abstract | Bake cookies, boost/attack, season prizes |
| **OCM** | Ethereum | Onchain Monsters staking, supply, burns |
| **Ten Thousand Tokens** | Ethereum | NFT burn-to-launch on UniV4, fee engines, holder claims |
| **Talismans** | Ethereum | Core-conservation NFT collection, materials, essence × tier |
| **FWA** | Ethereum | NFT gacha pool, inverse-weighted VRF draws, pull EV |

### FWA — Fake World Assets

A gachapon machine for NFTs. Depositors list an NFT with committed ETH backing; that backing sets an
**inverse** draw weight — the cheaper the position, the more likely it is drawn — and simultaneously
funds an irrevocable standing bid. A purchaser pays one price for one Chainlink-VRF-selected random
position, then chooses, *after* seeing what they drew: keep the NFT, or take 85% of its backing.

The dashboard takes the purchaser's seat and answers one question continuously:

> **Is a pull worth it right now?**

Everything on screen either feeds that number or explains it. The flagship figure is a **band**, not
a point: keyless floor prices cover 26 of the 38 collections holding live positions, but those 26
account for only about a fifth of the draw weight, so roughly 79.6% of what you are actually likely
to draw has no keyless floor. A single confident EV number would be a lie that costs someone ETH, so
the band ships with an inseparable coverage badge. The harmonic-vs-arithmetic backing gap — the
protocol in one number — is computed live at the current block and never printed as a constant.

## Install

### pipx (recommended)

```bash
pipx install maxpane
```

### uv

```bash
uv tool install maxpane
```

### pip

```bash
pip install maxpane
```

Requires Python 3.11+

### Full install (with Matrix intro sequence)

The full experience includes a Rust-powered Matrix-inspired intro animation. This requires [Rust](https://rustup.rs/) in addition to Python.

```bash
git clone https://github.com/banse/maxpane.git
cd maxpane

# Build the intro binary
cd maxpane && cargo build --release && cd ..

# Install the Python dashboard
pip install -e .

# Run with intro
./maxpane/target/release/maxpane && maxpane
```

Or add an alias to your shell config (`~/.zshrc` or `~/.bashrc`):

```bash
alias maxpane='~/path/to/maxpane/maxpane/target/release/maxpane && command maxpane'
```

## Usage

```bash
maxpane                        # launch dashboard (default: bakery)
maxpane --game frenpet         # start on FrenPet view
maxpane --game base            # start on Base trading view
maxpane --game cattown         # start on Cat Town view
maxpane --game dota            # start on DOTA view
maxpane --game ocm             # start on OCM view
maxpane --game ttt             # start on Ten Thousand Tokens view
maxpane --game talismans       # start on Talismans view
maxpane --game fwa             # start on Fake World Assets view
maxpane --theme minimal        # use minimal theme
maxpane --poll-interval 60     # poll every 60s instead of 30s
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `m` | Return to game selection menu |
| `tab` | Cycle to next game |
| `r` | Refresh data |
| `t` | Cycle theme |
| `q` | Quit |

### Terminal size

**FWA wants ~200 columns.** That is the width at which its bottom row (activity feed · chase board ·
settlement table) can render every column at once; the three slots measure ~81 / ~55 / ~56 columns
there, which is exactly what the three widgets need.

Below that the widgets do not wrap or clip silently: each one drops its least important columns and
says so in its own title with a `‹ widen` marker. That is deliberate, tested behaviour, not a bug —
a table that quietly loses a column still *looks* complete, which is the failure mode the marker
exists to prevent.

What a narrow terminal costs you, in the order things go:

| Widget | At ~200 cols | At ~140 cols |
|--------|--------------|--------------|
| Activity feed | full line: time · wallet · collection #token · outcome · ETH | drops the ETH amounts (`‹ widen for amounts`); the outcome label is reworded, never cut mid-word |
| Chase board | `# COLLECTION TOKEN BACKING ODDS JACKPOT` | drops `TOKEN` then `BACKING` (`‹ widen: TOKEN/BACKING`); `ODDS` and `JACKPOT` are the last to go because they carry the board's entire point |
| Settlement table | `OUTCOME/HOLDER COUNT SHARE ETH` | drops `COUNT` (`‹ widen: COUNT`); `SHARE` is never dropped — the outcome mix *is* the share column |
| Signals panel | 5 rows, no truncation | rows are ellipsized rather than wrapped (wrapping would push the fifth signal off the bottom) and the title grows `‹ widen` |

The hero row (PULL EV · PRICE · CROWN), the odds board and the sparkline have no column-dropping
tiers, so nothing disappears from them. And no number *changes* with the width — a narrow terminal
costs you fields, never correctness.

### Available themes

`matrix` `minimal` `bloomberg` `htop` `retro` `bakery` `frenpet` `base` `talismans` `fwa`

Ten themes. `talismans` and `fwa` are game-specific palettes that pair with their dashboards
(`maxpane --game fwa --theme fwa`), but any theme works with any game.
