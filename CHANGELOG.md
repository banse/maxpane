# Changelog

## Unreleased — since v0.8.4 (2026-08-29)

344 commits, 2026-08-29 → 2026-09-23. Every data source is still keyless and read-only.

### Surfboard — new views

- **`s` SWARM** — a live view of the IMD agent swarm's own control plane: CAPABILITY beside
  THROUGHPUT, IN FLIGHT beside LAUNCHES, SITES full-width beneath, and a hero of its own (AGENTS,
  WORKING, ACCEPTED 24h, QUEUE, BREAKER, SERVICES). First shipped 2026-09-16, rebuilt for swarm v2
  on 2026-09-21.
  - SITES: click an ENS name (`mswap.site.identitymd.eth`) to open the site itself
    (`https://mswap.site.identitymd.eth.limo/`). Builds that were replaced, and builds that never
    got a name, are left out; if that leaves nothing, the panel says `No current site`.
  - IN FLIGHT shows each job's dispatch or failure note.
- **`a` AGENT** — one seat's lifetime record, read from the keyless `/seats` endpoint:
  - a hero row with SEAT, ACCEPTED, ACCEPT RATE, REVIEWED, RANK and STATUS (worked / online);
  - a row of seat cards: owner (ENS name where one resolves), runtime, TEAMMATES, OTHERS, RANK;
  - a row of node cards: ROLES, then ORACLE / REVIEW / BUILD, each `accepted of attempts` with a
    rate, then OTHERS and BOARD;
  - RECORD: every work attempt the seat made, with its state, node and the first sentence of its
    answer. A failed attempt's answer is red, and the job id opens that job on the IMD explorer.
  - The title bar names the seat: `SURFBOARD · Identity.md AGENT #<seat>`.
- **`i`** — asks for your Identity.md seat (the NFT id), saves it to `~/.maxpane/config.toml` and
  opens AGENT on it. This replaces the `MAXPANE_IMD_SEAT` environment variable.
- **`b` BOARD** — the lifetime contributors LEADERBOARD beside FLEET (worker runtimes, models,
  daemons, OS, profiles, concurrency, heartbeat, paused workers, and CONTRIBUTORS: devices and
  seats, accepted of attempts, rejected and pending, turns and wall-clock hours, tokens in and out).
  It has its own six-box hero. Sort with `o` / `O` or by clicking a header. Enter or a click on a
  row saves that seat and opens AGENT; `▸` marks the selected seat.
- **`4` POOL4 MARKET** — pool4 read as a market: RECENT FLOW, BURN & SUPPLY, SIGNALS, STAKERS
  (whole addresses, every staker up to 999, keeps your scroll position) and IF IMD FALLS (the
  hook's bid ladder as IMD falls). Its hero shows IMD PRICE, DOWNSIDE BID and STAKING, and
  includes the realised trailing staking return from `Dripped` events.
- **`e` POOL4 protocol** (experimental, not shown in the hint) — THE SPLIT, THE RATCHET, HATCHES and
  sIMD VAULT. It first shipped as `p` on 2026-09-02 and moved to `e`. POOL4 FLOW was removed,
  because RECENT FLOW already shows those rows.
- The status hint now reads `l launchpad · 4 pl4 · s swm · a agt · b brd`; `esc` leaves any of the
  six alternate views.

### THE LIST (curator)

- **`a`** opens the linked-wallet analysis view.

### Every dashboard — addresses

- **Copy icon:** a `⧉` beside every 0x address, name and prose address, on every dashboard
  (hidden ones included). Clicking it copies through the native clipboard (`pbcopy`), falling back
  to OSC 52. The status bar says `copied`, `unconfirmed` or `unavailable`.
- **Explorer links:** clicking an address opens it on its own chain's explorer (Etherscan,
  Basescan, or Sepolia's explorer for a Sepolia row). The address is also a terminal hyperlink, so
  Cmd+click works in Terminal.app and iTerm2. A chain the app does not know gets no link rather
  than a guessed one.
- **Select to copy:** drag across a text panel and releasing the mouse copies the selection;
  `ctrl+c` after a drag does the same.

### Fixes worth knowing

- Surfboard: `eth.drpc.org` left the mainnet log pool (its free plan answers old ranges with a
  misleading error); POOL4 FLOW rows now come from the PoolManager's `Swap` event; IF IMD FALLS
  says `not reached` for rungs outside the band; the pool4 market view shows one clock.
- SWARM, AGENT and BOARD:
  - an unread value says `unavailable` and a real zero stays a zero;
  - each panel keeps its own `as of` clock;
  - a count too wide for its card is shortened (`10.0K`, `10K`), never cut and never read wrong
    (`4.6K of 5K`, not `5K of 5K`);
  - wall-clock hours are rounded, with `N min` under half an hour.
- Every dashboard: panels that could go blank on a failed read now say `unavailable`; every panel
  title has one blank row under it.
- Layout pins re-measured for every new view: SWARM 141 × 42, AGENT 139 × 33, BOARD 141 × 33,
  POOL4 MARKET 119 × 35, POOL4 protocol 99 × 45. The app-wide 143 is unchanged.

### Under the hood

- A refactor programme across every dashboard:
  - shared panel bases (`widgets/panels.py`);
  - one screen base (`DashboardScreen`, with a declarative `PANELS` dispatch);
  - shared formatters and row fitting (`widgets/fmt.py`, `widgets/rowfit.py`);
  - one strip-then-escape sanitiser;
  - a `SeriesCache` base for the six series caches;
  - one RPC error classifier;
  - injectable client, cache and path seams on the managers.
- Removed: the `templates/` copy sources and 20 unreachable Base widget modules.
- Tests: about 10,500, all network-free, run in parallel with
  `pytest -n 4 --dist loadfile`. Guards enforce the copy-icon and explorer rules on every
  dashboard.
