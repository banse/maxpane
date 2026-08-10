# MaxPane

Terminal dashboards for onchain games, NFT collections, and trading on Base, Abstract, and Ethereum.

Track leaderboards, signals, trends, and analytics for onchain projects — all from your terminal.

Every dashboard is **read-only and keyless**: public RPCs and public APIs only, no API keys of any
kind, no wallet, no signing, no transactions.

## Dashboards

| Game | Chain | What you see |
|------|-------|-------------|
| **FWA** | Ethereum | NFT gacha pool, inverse-weighted VRF draws, pull EV |
| **Base Trading** | Base | Trending tokens, volume, ETH price, signals |
| **FrenPet** | Base | Pet battles, leaderboard, activity, trends |
| **Cat Town** | Base | Fishing competition, KIBBLE economy, catches |
| **Ten Thousand Tokens** | Ethereum | NFT burn-to-launch on UniV4, fee engines, holder claims |
| **Talismans** | Ethereum | Core-conservation NFT collection, materials, essence × tier |
| **Surfboard** | Ethereum | surfsurf.eth announce feed, six launch detectors, IMD market, IDMD NFT |

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

### Surfboard — surfsurf.eth

The onchain experiments of the FrenPet dev, watched from the front-runner's seat. He announces
by sending **UTF-8 calldata to himself** — a channel that emits no logs at all, so every
event-driven watcher is structurally blind to it and a nonce poll sees a post within one refresh
interval. That asymmetry is the whole point of the dashboard.

Six detectors answer one question continuously:

> **Did something just happen in the surfsurf universe — and how early am I?**

New post · LP migration · identity gate · new deploy · bridge staging · burn. Each renders
`state · age · one-line detail`, and a detector only re-fires on a *new* event: baselines advance
on the successful read that detected the last one, and never on a failed read — an outage cannot
fire a burn or un-fire a migration.

The NFT floor is shown as `n/a — no keyless source`, not estimated. There is no keyless floor
feed for this collection, and a made-up number on a dashboard people trade against is worse than
an honest gap.

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
maxpane                        # launch dashboard (default: fwa)
maxpane --game fwa             # start on Fake World Assets view
maxpane --game base            # start on Base trading view
maxpane --game frenpet         # start on FrenPet view
maxpane --game cattown         # start on Cat Town view
maxpane --game ttt             # start on Ten Thousand Tokens view
maxpane --game talismans       # start on Talismans view
maxpane --game surf            # start on surfsurf.eth Surfboard view
maxpane --theme minimal        # use minimal theme
maxpane --poll-interval 60     # poll every 60s instead of 30s
maxpane --font-size 12         # smaller font = more columns (see below)
maxpane --font-size 0          # leave my terminal exactly as I set it
maxpane --version              # which build is this, and which Python runs it
```

### Making the panes fit ("‹ widen")

Widgets drop columns when their slot is too narrow and say so in the title —
`ACTIVITY ‹ widen for amounts`, `CHASE BOARD ‹ widen: TOKEN`. That is terminal
**width in columns**. Check yours with `tput cols`. Across every dashboard the
last marker goes out at:

| columns | what still shows |
|--------:|------------------|
| ≤ 134 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen`, FWA `SIGNALS ‹ widen` |
| 135–142 | surf `DEV ACTIVITY ‹ widen`, FWA `SIGNALS ‹ widen` |
| 143–175 | surf `DEV ACTIVITY ‹ widen` (FWA is already full) |
| **≥ 176** | **nothing — full layout**, with one exception below |

The exception is a post, not a panel. When an announce post links a transaction, its own
punctuation can glue the URL to the 66-character hash into a single token no column budget
can break — the captured one is 91 columns wide — so surf's `ANNOUNCE FEED` truncates it
and keeps its `‹ widen` lit above 176 (that particular post needs 194). The marker is
right: the link really is cut. The table's 176 is the width at which every *layout* is
whole, and the next post linking a transaction arrives with a token of its own length, so
no fixed number can promise more than that.

A maximized window is already as wide as your display, so **font size is the
only lever**: roughly 169 columns at 17 pt on a laptop screen, about 205 at
14 pt. maxpane sets 17 pt on launch, so zooming out *beforehand* gets
overwritten — pass `--font-size 13` (or export `MAXPANE_FONT_SIZE=13`) to
change it, or `--font-size 0` to have maxpane leave your terminal alone
entirely. At 17 pt a laptop lands at 169, one tier short of the full layout,
so reaching it means passing a smaller `--font-size`.

### Checking your version

```console
$ maxpane --version
maxpane 0.5.0
Python 3.13.2 (/Users/you/.local/pipx/venvs/maxpane/bin/python)
```

The interpreter path is there for a reason. `pipx` and `uv` both put their
shims in `~/.local/bin`, and neither will overwrite a `maxpane` it doesn't
own — the second one you use prints a warning and declines:

```
⚠️  File exists at ~/.local/bin/maxpane and points to
    ~/.local/share/uv/tools/maxpane/bin/maxpane, not
    ~/.local/pipx/venvs/maxpane/bin/maxpane. Not modifying.
```

When that happens the install succeeds and reports the new version, but the
*older* tool still answers to `maxpane`. If the version above isn't the one
you just installed, that's the cause — uninstall the copy you don't want
(`uv tool uninstall maxpane` or `pipx uninstall maxpane`) and reinstall with
the other, so a single manager owns the command.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `m` | Return to game selection menu |
| `tab` | Cycle to next game |
| `r` | Refresh data |
| `t` | Cycle theme |
| `q` | Quit |

### Terminal size

**The widest layout wants 176 columns.** That is the width at which every widget on every dashboard
can render its full column set for the data it holds today. **FWA wants 143**; the 176 belongs to
**surf**, whose dev-activity panel shares the narrow right rail so that all six of its panels stay
on screen at once. One thing 176 does not promise is a clean announce feed on every possible post:
a post that links a transaction can carry a single unbreakable token wider than the panel, and the
feed correctly truncates it and says so at any width (see the note under the table above).

On FWA, press **`c`** to swap the odds board for the activity feed — they share the wide middle-left
slot, so the bottom row belongs to the chase board and the settlement table alone. That split is why
FWA's requirement is 172 and not 198: with the feed in the bottom row, three widgets needing 79, 54
and 55 columns had to share it, and none of them fit until the terminal was very wide. Shortening
the buy-gate signal then took it from 172 to 143. TTT and Talismans use the same `c` pattern; surf
does not, because nothing on it is hidden.

Below that the widgets do not wrap or clip silently: each one drops its least important columns and
says so in its own title with a `‹ widen` marker. That is deliberate, tested behaviour, not a bug —
a table that quietly loses a column still *looks* complete, which is the failure mode the marker
exists to prevent.

What a narrow terminal costs you, in the order things go:

| Widget | Full layout | At ~140 cols |
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
