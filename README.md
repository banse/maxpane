# MaxPane

Terminal dashboard for blockchain games on Base, Abstract, and Ethereum.

Track leaderboards, signals, and analytics for RugPull Bakery, FrenPet, Cat Town, OCM, DOTA, and Base token trading — all from your terminal.

## Install

### Quick install (dashboard only)

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
maxpane --theme minimal        # use minimal theme
maxpane --poll-interval 60     # poll every 60s instead of 30s
```

### Available games

`bakery` `frenpet` `base` `cattown` `ocm` `dota`

### Available themes

`matrix` `minimal` `bloomberg` `htop` `retro` `bakery` `frenpet` `base`
