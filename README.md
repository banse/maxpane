# MaxPane

Terminal dashboard for blockchain games on Base, Abstract, and Ethereum.

Track leaderboards, signals, trends, and analytics for 6 onchain games — all from your terminal.

## Dashboards

| Game | Chain | What you see |
|------|-------|-------------|
| **Base Trading** | Base | Trending tokens, volume, ETH price, signals |
| **FrenPet** | Base | Pet battles, leaderboard, activity, trends |
| **Cat Town** | Base | Fishing competition, KIBBLE economy, catches |
| **DOTA** | Base | Defense of the Agents idle MOBA, heroes, lanes |
| **Rugpull Bakery** | Abstract | Bake cookies, boost/attack, season prizes |
| **OCM** | Ethereum | Onchain Monsters staking, supply, burns |

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

### Available themes

`matrix` `minimal` `bloomberg` `htop` `retro` `bakery` `frenpet` `base`
