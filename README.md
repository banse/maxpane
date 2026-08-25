# MaxPane

Terminal dashboards for onchain games, NFT collections, and trading on Base, Abstract, and Ethereum.

Track leaderboards, signals, trends, and analytics for onchain projects — all from your terminal.

Every dashboard is **read-only and keyless**: public RPCs and public APIs only, no API keys of any
kind, no wallet, no signing, no transactions.

## Dashboards

| Game | Chain | What you see |
|------|-------|-------------|
| **Surfboard** | Ethereum | surfsurf.eth announce feed (threaded replies), ten detectors, IMD market, v4 launchpad, IDMD NFT |
| **THE LIST** | Ethereum | Zero-custody allowlist game: hourly doomsday clock, survival signals, fan-out patterns, linked-wallet analysis |
| **FWA** | Ethereum | NFT gacha pool, inverse-weighted VRF draws, pull EV |
| **Base Trading** | Base | Trending tokens, volume, ETH price, signals |
| **FrenPet** | Base | Pet battles, leaderboard, activity, trends |
| **Cat Town** | Base | Fishing competition, KIBBLE economy, catches |
| **Ten Thousand Tokens** | Ethereum | NFT burn-to-launch on UniV4, fee engines, holder claims |
| **Talismans** | Ethereum | Core-conservation NFT collection, materials, essence × tier |

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

Nine detectors answer one question continuously:

> **Did something just happen in the surfsurf universe — and how early am I?**

New post · LP migration · identity gate · new deploy · bridge staging · burn · decoy pool ·
burn readiness · hot coin. Each renders `state · age · one-line detail`, and a detector only
re-fires on a *new* event: baselines advance on the successful read that detected the last one,
and never on a failed read — an outage cannot fire a burn or un-fire a migration.

The hero (LAUNCHPAD · FLOW · BURN · SUPPLY) reads the launchpad: how big the coin population is
and how fast it is growing, how many distinct creators are behind it, how much of it is actually
trading, and what the burn pipeline owes — the IMD side under BURN, the ETH side under FLOW.
LAUNCHPAD and FLOW carry the launchpad tier's own `as of HH:MM` on their titles, because that
tier refreshes on a slower clock than the title bar's and a failed sweep leaves the last good
numbers standing behind an older marker rather than blanking them.

The POOL and LP boxes this row used to carry are gone, and not because the 2026-08-17 v3→v4
migration reversed: POOL's three facts are each shown elsewhere now (pool liquidity in IMD
MARKET, the decoy count on the signals rail), and LP could only ever say `MIGRATED` once the old
position was burned — read live off-chain rather than assumed. An earlier v4 hook launch was
announced and then publicly retracted by the dev on 2026-08-16; nothing on this dashboard watches
for it any more.

The announce feed **threads replies**. A post that drew answers shows one `▸ 3 replies` line
instead of three more rows; click it — or focus it and press `enter` or `space` — and the
answers unfold, indented one column per level, with `▾` marking an open thread. The feed
remembers which threads you opened across refreshes, so a 30-second repaint never folds a
conversation back up under you. The indent is taken out of the reply's own text width rather
than added to the row, so opening a thread costs rows and never columns — nothing else on the
screen moves.

Press **`l`** to swap the whole dashboard body for the v4 launchpad's own view: LAUNCHPAD COINS
takes the left column and CURVE FLOW over BURN PIPELINE share a rail on the right — the same
two-column shape the main dashboard uses, split wider because the coin table has nine fixed
columns and cannot give any of them back. The hero (LAUNCHPAD · FLOW · BURN · SUPPLY) stays on
screen the whole time; `esc` backs out, one-way. The launchpad view is whole from
**135 columns**, inside the 143 the widest dashboard already asks for.

The NFT floor is shown as `n/a — no keyless source`, not estimated. There is no keyless floor
feed for this collection, and a made-up number on a dashboard people trade against is worse than
an honest gap.

### THE LIST — the linked-wallet view (`f`)

THE LIST is a zero-custody allowlist game: send ETH, take points on a square-root curve, and the
lowest-ranked wallets fall off the list at the top of every hour. The curve pays a *sublinear*
return on size, so one person splitting a stake across ten wallets outscores the same ETH sent
once. That makes the interesting question not who is on the list, but **how much of the list is
the same hand**.

Press **`f`** for as much of an answer as a public chain can support. The doomsday clock stays on
screen the whole time; `esc` goes back.

- **OPERATORS** — one row per linked group, widest first: how many wallets, the evidence that
  links them (`identical 0.45Ξ send ×10 in one wave · shared first funder 0x1a2b3c4d… ×7`), the
  share of all points the group holds, and a one-cell confidence marker — `⚑` several independent
  kinds of evidence or shared money provenance, `◌` exactly two, `?` not analyzed yet.
- **SEGMENTS** — the same population cut into bands: the linked groups, the early cohort, the
  late-grace cohort, the multiplier bands, the per-hour cohorts.
- **CLEANED LIST** — the points total against what is left once linked groups come out, and your
  own rank in both.

Press **`e`** while that view is open to write the cleaned list to
`~/.maxpane/curator_clean_list.json` (and a `.csv` of the same rows). The panel prints the path it
wrote; a list it could not compute writes nothing rather than an empty allowlist file.

The `y` view grows two lines from the same analysis: `linked`, which reads either a pattern
(`1,995-wallet group · matching send amounts · shared funder chain`) or `not linked to any group`,
and a clean rank under your raw one (`#47 with farms removed`). The leaderboard's flag column is
graded the same way.

**It is read-only analysis, in pattern language, and it is never an accusation.** The chain can
show that twelve wallets sent an identical amount four seconds apart from one funder; it cannot
show why, and this dashboard does not guess. So it describes shapes — *linked*, *fan-out*, a flag
glyph — and never labels a wallet or a person. Groups are scored, never wallets on their own; two
independent kinds of evidence are required before anything is called linked at all; and no verdict
is ever written to disk, so a later sweep can and does put wallets back on the clean list.

The analysis runs *behind* the dashboard, so the clock and the signals paint first and the three
panels read `analysis unavailable` for the first minute or so of a cold start. They fill in on
their own slower schedule and stamp their own `as of HH:MM`, which is deliberately not the title
bar's.

Press **`l`** for the complete record view. Its summary hero compares THE LIST, the configured
wallet, and THE CLEANED LIST above one full-width table; **`c`** switches between THE RAW LIST and
THE CLEANED LIST and remembers that choice when you leave. The table mirrors the record NFT
traits: rank, join order, wallet, points, weight, credit, deposits, first hour, and grace/judged
window, plus the linkage mark on the raw list. Click any column header to sort the loaded rows;
click it again to reverse the order. The interactive table is capped at 1,000 rows to keep
refreshes responsive. **`e`** exports the full, uncapped list currently shown to
`~/.maxpane/curator_raw_list.json` or `~/.maxpane/curator_cleaned_list.json`.

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
maxpane                        # launch dashboard (default: surf)
maxpane --game surf            # start on surfsurf.eth Surfboard view
maxpane --game curator         # start on THE LIST (WhitelistCurator) view
maxpane --game fwa             # start on Fake World Assets view
maxpane --game base            # start on Base trading view
maxpane --game frenpet         # start on FrenPet view
maxpane --game cattown         # start on Cat Town view
maxpane --game ttt             # start on Ten Thousand Tokens view
maxpane --game talismans       # start on Talismans view
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
| 109–112 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, surf `IDENTITY.MD ‹ widen for /2000 written`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen…`, curator `SIGNALS ‹ widen`, curator `ACTIVITY ‹ widen…`, curator `FAN-OUT PATTERNS ‹ widen` |
| 113–122 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen…`, curator `SIGNALS ‹ widen`, curator `ACTIVITY ‹ widen…`, curator `FAN-OUT PATTERNS ‹ widen: block window` |
| 123–126 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen: TX`, curator `SIGNALS ‹ widen`, curator `ACTIVITY ‹ widen: credit wording` |
| 127–133 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen: TX`, curator `SIGNALS ‹ widen` |
| 134 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `SIGNALS ‹ widen` |
| 135–137 | surf `ANNOUNCE FEED ‹ widen`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `SIGNALS ‹ widen` |
| 138–141 | surf `ANNOUNCE FEED ‹ widen`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen` |
| 142 | surf `IMD MARKET ‹ widen for 24h volume and bridge flow`, FWA `SIGNALS ‹ widen` |
| **≥ 143** | **nothing — full layout**, with one exception below |

The table starts at 109 rather than running down to zero because narrower terminals light
*more* markers, not the same ones: below 109 surf's `DEV ACTIVITY` marker changes wording
to `‹ widen: time, kind, ETH` as the time and kind columns go too, and below 89 surf's
`IDENTITY.MD` runs out of room to name its shed field beside the title and falls back to a
bare `‹ widen`. It stays bare down to 76; at 75–74 the stats row sheds `transfers/24h` as
well, and the shorter wording that names both — `‹ widen: 24h /2000`, 18 columns against
25 — fits beside the title again, so the hint is *descriptive at a narrower terminal than
the bare one it replaced*. Below 74 the floor line is what overflows, and it has no field
to shed, so the marker is bare again. Every one of those is a
panel saying what it dropped,
which is the system working; the table lists the last few to go out, not every marker a
narrow terminal can show.

THE LIST's own layout is whole at **138**, five columns under the number at the bottom of
the table, so it is never the dashboard that decides how wide you need to be. Its last
marker to go out is `SIGNALS`, the rail of seven detectors ending in YOU; the leaderboard
clears at 134, the activity feed at 127 and the fan-out table at 123. Two notes on reading
its rows above. `FAN-OUT PATTERNS` and `CLOSEST CALLS` share one slot — `c` swaps them —
so the table names whichever the current phase opens on, and the other behaves the same
way. And 138 is a *height-independent* number on purpose: the right rail reserves the
column its scrollbar would need, so a short window scrolls the rail instead of quietly
narrowing the panel that sets the width. The `f` view is whole at **137**, one column
inside the dashboard body it swaps out and six inside the number at the bottom of the
table, so pressing it never asks for a wider terminal than the screen you pressed it on;
its own binding panel is `OPERATORS`, whose evidence cell is the widest thing on it.
The two swapped views need rows rather than columns: the `f` body fits whole from 48
rows and the `y` body from 40, and below that each scrolls and says so with `‹ taller`.

`IMD MARKET` is the one row that moves with the data rather than with your terminal. Its
widest line carries the IMD/FP gap in dollars, and prices under a cent print with six
decimals instead of four — so a **tighter** peg is a **wider** panel: `$0.007100` where a
2.75% spread would print `$0.0200`. The table shows the wide case, which is also the
normal one for a 1:1 bridge; on a day the peg is loose the marker goes out around 140.

The exception is a post, not a panel. When an announce post links a transaction, its own
punctuation can glue the URL to the 66-character hash into a single token no column budget
can break — the captured one is 91 columns wide — so surf's `ANNOUNCE FEED` truncates it
and keeps its `‹ widen` lit above 143 (that particular post needs 216). The marker is
right: the link really is cut. The table's 143 is the width at which every *layout* is
whole, and the next post linking a transaction arrives with a token of its own length, so
no fixed number can promise more than that.

A maximized window is already as wide as your display, so **font size is the
only lever**: roughly 169 columns at 17 pt on a laptop screen, about 205 at
14 pt. maxpane sets 17 pt on launch, so zooming out *beforehand* gets
overwritten — pass `--font-size 13` (or export `MAXPANE_FONT_SIZE=13`) to
change it, or `--font-size 0` to have maxpane leave your terminal alone
entirely. At 17 pt a laptop lands at 169, which already clears the 143 the
full layout wants — you need `--font-size` for a smaller screen, not for the
full layout.

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

Some dashboards add their own. FWA, TTT, Talismans and THE LIST bind `c` to swap panels; in THE
LIST's `l` view it switches the full-width raw and cleaned tables. **Surfboard binds `l`** to swap
the whole dashboard body for the v4 launchpad's own view — LAUNCHPAD COINS on the left, CURVE
FLOW over BURN PIPELINE in a right-hand rail — with the hero (LAUNCHPAD · FLOW · BURN · SUPPLY)
left on screen the whole time; `esc` backs out, one-way, and its status hint reads
`l launchpad`. In Surfboard's announce feed, `enter` or `space` on a `▸ n replies` line (or a click) opens and
closes that thread. (THE LIST's `l` and Surfboard's `l` are two
different dashboards' own bindings, not one shared key — see each dashboard's own row above for
what it does there.) **THE LIST binds `y`** for your own standing — every send you
made with the multiplier it got, what each one actually credited, your share of all weight, the
single send that would pass the rank above you, and (from the linked-wallet analysis) whether you
are in a group and what your rank is without one (`esc` goes back; the clock stays on screen either
way). **It binds `f`** for the linked-wallet view described above, and **`l`** for the record view.
Inside either secondary view, **`e`** exports the list on screen. THE LIST's status bar names all
four: `c panels · y you · f linked · l lists`; `e` is not in the hints because it only acts in
those views, where the active list panel prints what it wrote. **It also binds `w`**, which asks for the wallet its
YOU row is about — rank, points, credit, and the exact amount that wallet must send next to beat
its own high-water mark. The address is validated, saved to `~/.maxpane/config.toml`, and picked
up by every wallet-scoped dashboard on the next launch, so it is the easiest way to set one:

```bash
maxpane --game curator --wallet 0xYourAddress   # or press w once, inside the app
MAXPANE_WALLET=0xYourAddress maxpane            # the env var overrides the saved file
```

### Terminal size

**The widest layout wants 143 columns.** That is the width at which every widget on every dashboard
can render its full column set for the data it holds today. The 143 is **FWA's**, and it is FWA's
again: surf set this number at 176 and then 152 for part of 2026-08-10, came down to 142, and now
reads **143** as well — level with FWA rather than under it, because surf's `IMD MARKET` needs one
more column than the announce feed once the IMD/FP peg is tight (see the note under the table
above). Either way the app-wide number is the max of the two and has not moved. One thing 143
does not promise is a clean announce feed on every possible post: a post that links a transaction
can carry a single unbreakable token wider than the panel, and the feed correctly truncates it and
says so at any width (see the note under the table above).

143 is inside the ~169 columns a laptop gets at the 17 pt maxpane sets on launch, so the full
layout is reachable without touching `--font-size`. It briefly was not: surf's number stood at 176
for part of 2026-08-10, until the seam between its two columns moved from 3:2 to 7:6 and handed the
announce feed exactly the share it needed instead of 24 columns more. Only the split moved to get
there, and at 152 and above nothing at all was given up.

What took surf the rest of the way down was the two panels either side of that seam getting
narrower, not the seam moving again. The announce feed lowered its own wrapping threshold from 76
to 71 columns, so it wraps posts from **142** instead of 151. The dev-activity panel was reserving
12 columns for a wallet cell whose whole vocabulary is `dev` and `ops` and one column too few for
its widest transaction kind, so it was both padded and cutting `fwa claim` mid-word; sizing both
cells to what the data actually contains took the panel from 66 columns to 58 and it now clears
from a 135-column terminal. That is why the table above no longer has a band where the dev-activity
panel is the only thing still asking for width.

One honest caveat on the seam. 7:6 was measured when the feed needed 81 columns and the rail 71;
they need 76 and 63 now, which a seam nearer 76:63 would collect at 139 rather than 142. The three
columns are real and deliberately unspent: the app-wide number is FWA's 143, so a surf screen
clearing at 139 would not change a single width a user sees — and that seam is no longer what binds
surf anyway, since the market panel in the row below it asks for 143.

Surfboard's `l` launchpad view is a second layout with its own number: **135 columns**, on a
12:5 split rather than the dashboard's 7:6. It gets its own seam because it balances different
things — a nine-column coin table that cannot shrink at all against a rail of short label/value
lines — and on the dashboard's 7:6 the table would not have got its columns until a 177-column
terminal, wider than any laptop reaches. 135 is inside 143, so the app-wide number is unchanged.

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

## sybilkit — the analysis library, on its own

The clustering behind THE LIST's `f` view is not part of the dashboard. It lives in
[`sybilkit`](sybilkit/README.md), a **separate Python distribution** in this repository that knows
nothing about maxpane, Textual, or any particular allowlist — THE LIST is one preset it ships, not
its subject. maxpane reaches it through exactly one adapter module, and you can use it without
maxpane at all.

```bash
pip install sybilkit              # the pure core — zero third-party packages
pip install "sybilkit[sources]"   # adds httpx and the keyless fetchers
```

```bash
sybilkit analyze           --contract 0x… --from-block N --out clusters.json
sybilkit segments          --contract 0x… --preset curator
sybilkit export-clean-list --contract 0x… --preset curator --out clean_list.json
```

Keyless like everything else here: public RPCs and a public explorer, no key of any kind, no
signing, no writes. It scores *clusters* rather than wallets, requires at least two independent
signal families and five members before a group exists at all, and emits `reasons` with a
graduated confidence instead of a verdict. See [`sybilkit/README.md`](sybilkit/README.md) for the
API, the endpoint table and the benchmark gate.

`sybilkit` is built and released on its own — a maxpane release does not publish it, and
`pip install maxpane` does not pull it in yet. Until it is on PyPI, maxpane's import of it is
guarded: with the library absent the dashboard runs exactly as before and the `f` view reports
`analysis unavailable` instead of failing.
