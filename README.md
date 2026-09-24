# MaxPane

Terminal dashboards for onchain games, NFT collections, and trading on Base, Abstract, and Ethereum.

Track leaderboards, signals, trends, and analytics for onchain projects — all from your terminal.

Every dashboard is **read-only and keyless**: public RPCs and public APIs only, no API keys of any
kind, no wallet, no signing, no transactions.

## Dashboards

| Game | Chain | What you see |
|------|-------|-------------|
| **Surfboard** | Ethereum | surfsurf.eth announce feed (threaded replies), ten detectors, IMD market, v4 launchpad, pool4 ratchet, IMD swarm, IDMD NFT |
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

Ten detectors answer one question continuously:

> **Did something just happen in the surfsurf universe — and how early am I?**

New post · new reply · LP migration · identity gate · new deploy · bridge staging · burn ·
decoy pool · burn readiness · hot coin. Each renders `state · age · one-line detail`, and a detector only
re-fires on a *new* event: baselines advance on the successful read that detected the last one,
and never on a failed read — an outage cannot fire a burn or un-fire a migration.

The hero (LAUNCHPAD · FLOW · BURN · BOARDS) reads the launchpad: how big the coin population is
and how fast it is growing, how many distinct creators are behind it, how much of it is actually
trading, and what the burn pipeline owes — the IMD side under BURN, the ETH side under FLOW.
BOARDS lists the keys that open the other boards: `'a' - imd agent`, `'b' - leaderboard`,
`'s' - swarm` and `'4' - pool4` (the narrowest hero tier writes `b leaderboard`, without the quotes and dash).
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

Press **`l`** to swap the whole dashboard body for the v4 launchpad's own view — five panels in
two columns. LAUNCHPAD COINS and LAUNCHPAD ACTIVITY take the left column: the ten most-traded
coins of the last day with their market caps in dollars, and under them a live feed of the
launchpad's own buys, sells and launches. CURVE FLOW, BURN PIPELINE and BURNKEEPERS share the
rail on the right — where the ETH is going, what the burn pipeline has accrued and staged, and
who has actually pushed the button. BURNKEEPERS is the new one: `bridgeToBaseBurnReceiver()` is
callable by anyone, so this ranks the wallets that have called it by IMD burned and shows the
LayerZero fee each really paid — the fee, not the transaction's value, whose surplus the executor
refunds. maxpane never calls it, and never offers to: it only reports that it is callable and
what it has cost the people who did. The hero (LAUNCHPAD · FLOW · BURN · BOARDS) stays on screen
the whole time; `esc` backs out, one-way. The launchpad view is whole from **138 columns**,
inside the 143 the widest dashboard already asks for, and from **31 rows** — below that it
scrolls and says `‹ taller`.

Press **`e`** for the experimental pool4 protocol view (it is not named on the status bar) — the same trick a third time, a third body under the same hero. pool4
makes IMD's pool a one-way ratchet: buys drain a reserve that a floor stops them draining past,
sells burn most of what they sell, and a slice of every swap is retained to pay for the protocol's
own inference. THE SPLIT and THE RATCHET take the left column — the reward split
**measured from the live counters** rather than quoted from anyone's documentation, and the reserve
against its floor and how far it is from it. The swap-by-swap log of what each trade burned, paid
out, and left behind is the `4` view's RECENT FLOW. HATCHES and sIMD VAULT share the rail: which powers over the
contracts are still live and who holds them, and what a staker is actually being paid — which a
drip rate sets, not pool volume, so the panel shows the backlog as days of runway rather than an
APR derived from fee flow that would be wrong by orders of magnitude.

**pool4 went live on Ethereum mainnet on 2026-09-02**, and the protocol that shipped is not the
one the testnet launches described — which is exactly why nothing on this view is a constant. The
reward split is **three-way** on mainnet, through a Reward Distributor that has no testnet
counterpart: of every 100 IMD retired, 85 is burned and the remaining 15 is cut between stakers,
bonding and the NFT-holding node daemons. Bonding is the *remainder* of that cut rather than a
number the contract will tell you, so the view derives it and labels it as derived. The reward
share went up by half and the reserve floor fell by five orders of magnitude between testnet and
mainnet, and the view needed no change for either: it reads whichever it is pointed at. One more thing worth knowing before
you read the burn figure: mainnet's burn sink is a **pass-through executor**, not the dead address,
so what sits in it is what is *queued*, not what has been burned.

**Every panel title on this view names its network** — `THE RATCHET · MAINNET`, `· SEPOLIA`, or
`· —` when no read has landed yet. That is not decoration: the view still reads the live Sepolia
deployment whenever it has not adopted a mainnet hook, and a testnet number on an unmarked panel
would be a fiction presented as live.

**How it finds the mainnet contracts is worth reading before you trust a number on this view.**
The strong path is the dev's own announce channel: an address named in a post he sent to himself
is signed by his key and cannot be forged. **He has not posted the mainnet hook**, so automatic
discovery correctly refuses it, and the operator chose instead to accept the addresses published
on `pool4.imd.fun/docs`. That is a real widening of what this dashboard trusts, and the chain
fingerprint does not close it: an address shaped to carry the right Uniswap v4 permission bits can
be mined in about twenty thousand tries, four of the five getters checked are only proof that
*something* is there, and the token a candidate reports is the candidate's own claim. Prevention
was not available; **disclosure was**, so HATCHES names which source an adoption came from and a
docs-sourced one carries a warning marker where a dev-signed one does not. A self-post, if one
ever lands, overrides the page.

Bonding is live — it takes 40% of the reward share and its held and earned balances are readable —
but it lives *inside* the Reward Distributor: no separate bond contract is named by any contract
this dashboard reads, so the HATCHES row for it says `unknown`, which is "we did not look here"
rather than "it is not there". Read-only and keyless as everywhere else: `drip()` and `rebalance()`
are permissionless and pay a keeper reward, and maxpane reports that they are callable and by whom
and never offers to call one. `esc` backs out, one-way. The view is whole from **99 columns and
45 rows**.

The NFT floor is shown as `n/a — no keyless source`, not estimated. There is no keyless floor
feed for this collection, and a made-up number on a dashboard people trade against is worse than
an honest gap.

Press **`s`** for the IMD swarm's own control plane (2026-09-16; rebuilt 2026-09-21) — the fifth
body, and the agent workforce this repo's own branches are built by, watched live rather than read
from a changelog. CAPABILITY is the swarm's skill catalogue — every skill with its role, kind,
tier and the judge that scores it — beside THROUGHPUT: how much the job list holds and how it
splits by state, how long a delivery takes (median, p90, worst) over the jobs that carry a delivery
stamp, why jobs were cancelled, and how many completed in the last day, counted off every job this
dashboard has ever seen rather than off the window the host happens to serve. IN FLIGHT lists the
jobs executing right now, newest first, with the seat that holds each and the node it is on, beside
LAUNCHES — the deployed artifacts, one row per launch with its status, chain, repo commit and
contract address, every real address carrying the copy icon and linking its **own** chain's
explorer, because the corpus mixes mainnet and Sepolia in one list. SITES, the ENS-named sites,
runs full-width beneath: a site's name resolves a content hash rather than a wallet, so it carries
no copy icon, but a click on it opens the site itself (`mswap.site.identitymd.eth` opens
`https://mswap.site.identitymd.eth.limo/`). A build replaced by a newer one and a build that never
got a name are left out; when that leaves nothing, the panel says `No current site`, not `No data`. The hero swaps too, the second Surfboard view (after `4`) to do so, for
AGENTS (online/enrolled), WORKING, ACCEPTED 24h, QUEUE, BREAKER and SERVICES; a zero is a zero and
only a failed read says `unavailable`.

Press **`a`** for the AGENT body — one seat's **lifetime record** from its own keyless
`/seats/{tokenId}` page. Press **`i`** to choose and save a seat; without a saved seat, the view
uses the most active seat found in the job data. The hero shows SEAT, ACCEPTED, ACCEPT RATE,
REVIEWED, RANK (rank, turns and hours on the contributors leaderboard) and STATUS. ACCEPT RATE
is accepted work divided by attempts. STATUS shows a green `● online` for a connected, idle
worker (or its capacity while working), any pause, and the seat's newest activity from `/seats`:
`worked MM-DD HH:MM` when its newest attempt is newer than its newest accepted work, otherwise
`accepted MM-DD HH:MM`. ACCEPTED carries the seats clock; the STATUS and BOARD titles name no
clock (the screen title does).

Two more rows of cards sit under the hero, on one column grid with it and a blank row between
rows. The seat row shows OWNER (the owner's ENS name when it has a forward-verified one, otherwise
the address; either way with a copy icon for the address and an Etherscan link, plus when the
seat was paired), RUNTIME (runtime, daemon version and device count), SCORE (mean score, how
many reviews were scored and, when they differ, entries served), FEEDBACK (reviews sent,
submitted and queued), COLLAB (how many seats it has worked with) and TEAMMATES by shared jobs.
The node row shows ROLES (reviews by role, full names), one card each for the three nodes
(ORACLE, REVIEW, BUILD), titled whether or not the seat has worked them — accepted of attempts,
the acceptance percentage, the node's roles shortened (`impl`, `rev`) and its `chain` count of
sent and submitted feedback transactions — then OTHERS, the same sums over every other node; a
card with no attempts, nothing accepted and no chain count, OTHERS included, shows `—`, and a
count too wide for its card is shortened (`10.0K`, then `10K`) rather than cut, never so far that
two different counts read alike or the wrong way round (`4.6K of 5K`, not `5K of 5K`). Then BOARD
(accepted of attempts, rejected and pending on the contributors leaderboard). RANK and BOARD stay
visible when the seats read fails; a good contributors read without the seat says `not listed`,
an unread source says `unavailable`. Long runtime, daemon, node, role and ENS names are cut with
a visible `…`.
RECORD runs below the cards, with no blank row under its title: every attempt with date and
time, job (the first eight characters of its id, linked to its page on `explorer.imd.fun`), node
(`oracle`, `review`, `build`), state, the model used, duration, panel outcome, output tokens and the seat's own answer.
Joined oracle rows show the answer.json value and the start of its notes; a cut row's `»` opens
the cached question, full retained value and notes. Failed members show their reason in red.
Other rows show the first sentence of the reply — in red when the attempt failed. Queued, unavailable, not served and
empty replies remain distinct, and keep their own colours on a failed attempt. Links to local files are reduced to their labels, and absolute
local paths to filenames before display. A review that passed and work that won a job remain separate counts.
SEAT names `#N never paired` for a seat that has never paired; a failed read says `unavailable`.
`esc` backs out of either body, one-way.

Press **`b`** for BOARD: aggregated lifetime contributors beside the live worker fleet.
SEATS, ACCEPT RATE and RECEIPTS come from contributors; LIVE, PAUSED and CAPACITY come
from workers. LEADERBOARD includes every fully parsed contributor seat and scrolls; runtime/state and
FLEET metadata keep their own source clocks. One failed endpoint leaves the other's facts
visible. FLEET groups metadata under aligned labels, including an **advertised** model mix,
with whole entries followed by exact `+N` omissions. Its CONTRIBUTORS group has a separate
clock, a blank row, then devices and seats, accepted of attempts, rejected and pending, turns
and wall-clock hours (rounded; minutes under half an hour), input and output tokens, and the served tokens-per-completed-job
metric; a pair too wide for its line keeps its first value and counts the rest as `+N`. The
LEADERBOARD table sits one cell in from its title. Worker advertisement can differ from
the model that actually ran a RECORD submission. BOARD contains no wallet or token ranking.
Click any LEADERBOARD column header to sort; click the active header to reverse. The default
sort is rank, so the first click on `#` reverses it. `o` cycles the sort
column and `O` reverses it. Global ranks and the cursor's seat identity remain stable. The
selected seat is bold with an accent rank cell, working is green, paused red, offline dim and
unknown yellow; every state retains its word.

SWARM and AGENT status colours retain their words — except AGENT's STATUS, which writes a green
`⚙` for "working" (`⚙ 3 of 8`, `● online · ⚙ 0 of 1`) to save width: green means healthy, online, working or accepted;
red means offline, paused or down; yellow marks unavailable or existing pending counts. Zero
working is dim `quiet`. Rates and scores are bold without invented thresholds. BOARD's offline
rows are dim. SEAT stays as it is by owner decision; its larger grouping exceeded the budget
(F54). QUEUE counts stay bold without status colour.

It reads one keyless host and nothing else — the swarm's own control plane, under two names that
serve one deployment, rotated per request and never followed off the pool — and never the total it
says it has inferred for anyone: the explorer publishes a running inference figure on its own page,
and no public route on the control plane serves that number, so this view shows none of it rather
than a guess. The job list behind IN FLIGHT and THROUGHPUT is the one expensive read here, so it is
not fetched on every tick: it is re-read only when one of the host's own health counters has
actually moved, or when a ceiling has elapsed regardless, so a counter this dashboard does not
track can never freeze the list forever. A failed read serves each panel's own last-good behind an
`as of HH:MM` marker rather than a blank screen, and no new degraded group was added for it — the
title row was already full. Each body is whole from its own pin — `SURF_SWARM_FULL_LAYOUT_COLUMNS`
× `SURF_SWARM_FULL_LAYOUT_ROWS`, `SURF_AGENT_FULL_LAYOUT_COLUMNS` × `SURF_AGENT_FULL_LAYOUT_ROWS`,
and `SURF_BOARD_FULL_LAYOUT_COLUMNS` × `SURF_BOARD_FULL_LAYOUT_ROWS`
in `screens/surf.py` (the `#:` block beside each constant carries the number and how it was
measured). One caveat worth knowing before trusting the width: IN FLIGHT and LAUNCHES, which share
a row, do not clear their own full column sets below 190 and 205 columns, wider than every other pin
in the app; LAUNCHES hides no column from 138 up, and both are measured, accepted conditions at every
width this view can reach, the same shape as surf's announce feed and a linked-transaction post.

### THE LIST — the linked-wallet analysis view (`a`)

THE LIST is a zero-custody allowlist game: send ETH, take points on a square-root curve, and the
lowest-ranked wallets fall off the list at the top of every hour. The curve pays a *sublinear*
return on size, so one person splitting a stake across ten wallets outscores the same ETH sent
once. That makes the interesting question not who is on the list, but **how much of the list is
the same hand**.

Press **`a`** for as much of an answer as a public chain can support (bound 2026-09-15). The
doomsday clock stays on screen the whole time; a second `a` or `esc` goes back. `a` is not shown
in the status bar's hints — the owner asked for the binding, not the label — but `action_toggle_analysis`
behaves exactly like the `y` view's toggle. `f` opens the custom filter editor inside the `l`
record view instead (see below); the two keys are unrelated.

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
glyph — and never labels a wallet or a person. Groups are scored as groups: two independent kinds
of evidence are required before one is called linked at all. A member the publisher holds at the
edge of a group — thin evidence, not enough to call it linked — gets its own mark instead of
either verdict: `review` (`~` on the leaderboard flag column), shown rather than hidden. What
counts as thin is the publisher's rule (`v2h`, "aged-weak periphery"), not a family count of ours:
most review wallets carry one kind of evidence and some carry two. No verdict is ever written to
disk, so a later sweep can and does put wallets back on the clean list.

The analysis runs *behind* the dashboard, so the clock and the signals paint first and the three
panels read `analysis unavailable` for the first minute or so of a cold start. They fill in on
their own slower schedule and stamp their own `as of HH:MM`, which is deliberately not the title
bar's.

Press **`l`** for the complete record view. Its summary hero puts THE LIST, YOUR WALLET (your ENS
name when it has one) and THE FILTER above one full-width table; **`c`** cycles the table through
raw, cleaned and filtered and remembers that choice when you leave. The table mirrors the record NFT
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
| 109–112 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen: time, kind, ETH`, surf `IMD MARKET ‹ widen…`, surf `IDENTITY.MD ‹ widen for /2000 written`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen…`, curator `SIGNALS ‹ widen`, curator `ACTIVITY ‹ widen…`, curator `FAN-OUT PATTERNS ‹ widen` |
| 113–122 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen…`, curator `SIGNALS ‹ widen`, curator `ACTIVITY ‹ widen…`, curator `FAN-OUT PATTERNS ‹ widen: block window` |
| 123–126 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen: TX`, curator `SIGNALS ‹ widen`, curator `ACTIVITY ‹ widen: credit wording` |
| 127–133 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `TOP OF THE LIST ‹ widen: TX`, curator `SIGNALS ‹ widen` |
| 134 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `SIGNALS ‹ widen` |
| 135–137 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen`, curator `SIGNALS ‹ widen` |
| 138 | surf `ANNOUNCE FEED ‹ widen`, surf `DEV ACTIVITY ‹ widen for amounts`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen` |
| 139–141 | surf `ANNOUNCE FEED ‹ widen`, surf `IMD MARKET ‹ widen…`, FWA `SIGNALS ‹ widen` |
| 142 | surf `IMD MARKET ‹ widen for 24h volume and bridge flow`, FWA `SIGNALS ‹ widen` |
| **≥ 143** | **nothing — full layout**, with one exception below |

The table starts at 109 rather than running down to zero because narrower terminals light
*more* markers, not the same ones: below 113 surf's `DEV ACTIVITY` marker changes wording
to `‹ widen: time, kind, ETH` as the time and kind columns go too (113, not 109 — the copy
icon added two columns to the row's window cell, and the crossover moved with it), and below 89 surf's
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
narrowing the panel that sets the width. The `a` (linked-wallet analysis) body is whole at
**137**, one column inside the dashboard body it swaps out and six inside the number at the
bottom of the table, so opening it never asks for a wider terminal than the screen it opened on;
its own binding panel is `OPERATORS`, whose evidence cell is the widest thing on it.
The two swapped views need rows rather than columns: the `a` body fits whole from 48
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

Click ⧉ beside any address to copy it. Drag across any text panel to select, and releasing the
mouse copies the selection (`ctrl+c` after a drag does the same); the status bar says `copied`,
`unconfirmed` (sent by OSC 52, no native tool found) or `unavailable`. Tables and feeds
(leaderboards, activity feeds) do not select — use the ⧉ icon beside their addresses.
Click an address itself to open it on Etherscan (Basescan for the Base dashboards, Sepolia's
explorer for a Sepolia row) in your browser; the address is also a terminal hyperlink, so
Cmd+click works in Terminal.app and iTerm2 without going through the app.

Some dashboards add their own. FWA, TTT, Talismans and THE LIST bind `c` to swap panels; in THE
LIST's `l` view it cycles the full-width table through raw, cleaned and filtered. **Surfboard binds `l`** to swap
the whole dashboard body for the v4 launchpad's own five panels — LAUNCHPAD COINS over LAUNCHPAD
ACTIVITY on the left, CURVE FLOW, BURN PIPELINE and BURNKEEPERS in a right-hand rail — with the
hero (LAUNCHPAD · FLOW · BURN · BOARDS) left on screen the whole time; `esc` backs out, one-way.
**It binds `e`**, experimental and unadvertised, the same way for the pool4 protocol — THE SPLIT and THE RATCHET on the left,
HATCHES and sIMD VAULT in the rail, the same hero left where it was. **And it binds `4`** for the
POOL4 MARKET view — the same protocol read as a market rather than as a machine: RECENT FLOW
beside BURN & SUPPLY over SIGNALS, then STAKERS — whole 42-character addresses, no shortening —
beside IF IMD FALLS, a ladder of what the hook bids as IMD falls. `4` swaps the **hero** too, for
IMD PRICE, DOWNSIDE BID and STAKING. **And it binds `s`** (2026-09-16, rebuilt 2026-09-21) for the
IMD swarm's own control plane — the agent workforce this repo's own branches are built by, watched
live: CAPABILITY beside THROUGHPUT, IN FLIGHT beside LAUNCHES, SITES full-width beneath. `s` is
the second Surfboard view, after `4`, to swap the **hero**, for its own AGENTS / WORKING /
ACCEPTED 24h / QUEUE / BREAKER / SERVICES boxes. **And it binds `a`** (2026-09-21) for the AGENT
body — one seat's lifetime record: its hero row (including ACCEPT RATE), two rows of seat and
node cards (ORACLE / REVIEW / BUILD, each `accepted of attempts`), and RECORD beneath; its title
bar reads `SURFBOARD · Identity.md AGENT #<seat>` (the seat in green) in place of the IMD price,
and names no degraded source groups — each AGENT card shows its own unavailable state. **`i`** asks for your own
seat — its Identity.md NFT id — saves it to `~/.maxpane/config.toml` and opens the AGENT body on it,
like THE LIST's `w` for a wallet. **`b`** opens BOARD: the lifetime LEADERBOARD
beside FLEET, with its own six-box hero. Enter or a single click on a leaderboard row saves that seat through
the same configuration writer and opens AGENT; `▸` marks the selected seat. `esc` backs out
of any of the six alternate bodies.

| Surfboard input | Action |
|---|---|
| `l` / `e` / `4` / `s` / `a` / `b` | Open LAUNCHPAD / POOL4 protocol / POOL4 MARKET / SWARM / AGENT / BOARD |
| `i` | Choose and save an IDMD seat |
| `o` / `O` in BOARD | Cycle sort column / reverse sort |
| LEADERBOARD header click | Sort that column; click again to reverse |
| LEADERBOARD row click or Enter | Save that seat and open AGENT |
| RECORD `»` click | Open the cached oracle answer, question and notes |
| Enter / `esc` in ANSWER | Close the popup and return to AGENT |
| `esc` outside ANSWER | Return to the dashboard |

The status hint names the ones that are not experimental:
`l launchpad · 4 pl4 · s swm · a agt · b brd`. In Surfboard's announce feed, `enter` or `space` on a
`▸ n replies` line (or a click) opens and closes that thread. (THE LIST's `l` and Surfboard's `l` are two
different dashboards' own bindings, not one shared key — see each dashboard's own row above for
what it does there.) **THE LIST binds `y`** for your own standing — every send you
made with the multiplier it got, what each one actually credited, your share of all weight, the
single send that would pass the rank above you, and (from the linked-wallet analysis) whether you
are in a group and what your rank is without one (`esc` goes back; the clock stays on screen either
way). **THE LIST also binds `a`** (bound 2026-09-15) for the linked-wallet analysis view described
above, the same shape as `y` — hero left in place, a second `a` or `esc` backs out one-way — and
**`f`** for the custom filter editor inside `l`'s record view; the two are unrelated bindings on
the same screen, not one key doing two jobs. **`l`** opens the record view.
Inside it, **`e`** exports the list on screen (and the analysis body's own cleaned-list export
still fires whenever that body is open). THE LIST's status bar names all four: `c view · h history ·
y you · l lists`; `a` and `e` are not in the hints — `a` because the owner asked for the binding and
not the label, `e` because it only acts inside the record view or the analysis body, where the
active panel prints what it wrote. **It also binds `w`**, which asks for the wallet its
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
cells to what the data actually contains took the panel from 66 columns to 58. The copy icon beside
its unknown-counterparty address (`docs/address_copy_PRD.md`, 2026-09-14) then added its own two
columns back, to 60, and moved where it clears from a 135-column terminal to a 139-column one. That
is why the table above no longer has a band where the dev-activity panel is the only thing still
asking for width — that band now ends two rows later than it used to.

One honest caveat on the seam. 7:6 was measured when the feed needed 81 columns and the rail 71;
they need 76 and 63 now, which a seam nearer 76:63 would collect at 139 rather than 142. The three
columns are real and deliberately unspent: the app-wide number is FWA's 143, so a surf screen
clearing at 139 would not change a single width a user sees — and that seam is no longer what binds
surf anyway, since the market panel in the row below it asks for 143.

Surfboard's `l` launchpad view is a second layout with its own number: **138 columns**, on a 2:1
split rather than the dashboard's 7:6. It gets its own seam because it balances different things
— a nine-column coin table that cannot shrink at all against a rail of short label/value lines —
and on the dashboard's 7:6 the table would not have got its columns until a 171-column terminal,
wider than any laptop reaches. 138 is inside 143, so the app-wide number is unchanged. It was 135
while this view had three panels; the two it grew on 2026-08-25 cost it three columns, and the
split moved off 12:5 for a reason worth knowing. CURVE FLOW and BURN PIPELINE — the two rail
panels whose lines are the longest — have no `‹ widen` of their own, so a seam that lets the
*rail* run out of room first clips a line in silence, which 12:5 did, in a four-column-wide
window of terminal widths. 2:1 hands the rail more columns than its widest line can ever need, so
the coin table — which does say `‹ widen` when it runs short — is what decides the width at every
width. It also has a **height** requirement of its own — 31 rows — as THE LIST's two swapped
bodies do.

Surfboard's experimental pool4 protocol view (`e`) is a **third** layout with a third number: **99 columns**, on an
even 1:1 split, and the narrowest full layout in the app. It is narrow because none of its four
panels is a table — four label/value summaries — and it was swept on its own rather than
inherited from the launchpad's 138, which it is deliberately not equal to. It was 106 until
2026-09-14. That day POOL4 FLOW, the fitted log that decided the width, left the view, because
the `4` view's RECENT FLOW shows the same rows. The panel that decides the width now is HATCHES in
the rail, which advertises what it dropped by *appending* to its own title. The even seam used to
buy that rail a few columns of margin for exactly that reason. It has none now, and that was
measured to be safe rather than assumed: HATCHES still marks at every width below 99.

Where this view asks for more than anything else is **height**: **45 rows**, against the launchpad
view's 31, and below that the body scrolls and the title bar says `‹ taller`. Unlike the other two
layouts that 45 is a **worst case over payloads, not a constant**. It was one, briefly, when the
column that decides the height held only fixed-height panels — but mainnet gave THE SPLIT a third
leg and a distributor to report, so two of its panels now grow with the data. The practical
consequence is that this number has to be re-swept when a panel's line count changes, rather than
assumed to have held. It was re-swept when POOL4 FLOW left on 2026-09-14, and it **did not move**:
the rail (HATCHES over sIMD VAULT) was already the tallest column, so a 44-row terminal still
shows `‹ taller`.

Surfboard's SWARM view (`s`) is a layout of its own too, pinned by `SURF_SWARM_FULL_LAYOUT_COLUMNS`
and `SURF_SWARM_FULL_LAYOUT_ROWS` (**141 columns × 42 rows** since the 2026-09-21 rebuild; 116 × 28
before it). CAPABILITY's original seven columns decide the width. Its optional `inf` and
`acc/att` columns appear from `CAPABILITY_OPTIONAL_FULL_COLUMNS` and retain `‹ widen` below it.
The top row decides the height: THROUGHPUT is sixteen fixed lines and its row is floored at exactly that, so at 42 rows
the body has room for the three rows without any panel scrolling inside itself and `‹ taller` goes
dark. Mixed service states still clip in the SERVICES hero box (F55); its explicit state words
and separate health line do not make all mixed combinations whole at this pin. IN FLIGHT and
LAUNCHES have measured content exceptions recorded beside their constants in `screens/surf.py`;
they share the second row on a 4:5 split measured so that
LAUNCHES hides no column from 138 up. Like the announce feed's linked-transaction post, those are
measured and accepted conditions at this pin and below, not something a wider pin could buy back.
The AGENT view (`a`) has its own pair, `SURF_AGENT_FULL_LAYOUT_COLUMNS` ×
`SURF_AGENT_FULL_LAYOUT_ROWS`, re-measured for the card rows over RECORD. The `#:` blocks
beside those constants in `screens/surf.py` record the measured dimensions and binding content.
RECORD's cleaned answer takes the remaining width and clips with a visible `…`; its measured clearing
width lives beside `RECORD_NEVER_CLEARS_BELOW` in the same file. Short answers do not light
`‹ widen` once the table's other columns fit. The committed first 40 v4 work rows clear at
`RECORD_NEVER_CLEARS_BELOW`; one column below still clips the longest answer. BOARD uses
`SURF_BOARD_FULL_LAYOUT_COLUMNS` × `SURF_BOARD_FULL_LAYOUT_ROWS`, with grouped FLEET and
paused detail binding height. Durations below a minute display `<1m`.

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

THE LIST's linked-wallet analysis view reads a published, immutable analysis — keyless, from
`clustermap.vibingco.de` — rather than clustering wallets itself; it folds maxpane's own on-chain
history over the membership that analysis names, so every point and rank still comes from
maxpane's own data. The math behind that fold lives in
[`sybilkit`](sybilkit/README.md), a **separate Python distribution** in this repository that knows
nothing about maxpane, Textual, or any particular allowlist — THE LIST is one preset it ships, not
its subject, and its own CLI (below) still does the clustering, standalone. maxpane reaches
sybilkit through exactly one adapter module, and you can use the library without maxpane at all.

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

`sybilkit` is built and released on its own — a maxpane release does not publish it. It published
`0.1.0` to PyPI on 2026-08-19 (`0.1.1` is the latest release as of this writing), and since
**v0.8.0** `pip install maxpane` pulls it in too (`pyproject.toml` pins `sybilkit>=0.1.0`). The
import stays guarded regardless: with the library absent — an older install, a partial
environment, or a future name change — the dashboard runs exactly as before and the analysis view
reports `analysis unavailable` instead of failing.
