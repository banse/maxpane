# Changelog

## Unreleased

- Surfboard AGENT: keep the last good record for up to six seats, each with its own timestamp.
  Temporary host overload shows `busy · retrying`, or `busy` beside the cached record's timestamp.
  Eligible pending answers, oracle panels and submission job details now say `loading…`.

## v0.9.3 — 2026-09-26

- Surfboard `a` AGENT: STATUS no longer reads `⚙ 9 of 1` when a seat runs more jobs than its
  `maxConcurrency`. Oracle jobs do not count against that limit, so a seat can legitimately run
  more of them at once; STATUS then reads `⚙ 9 working`.

## v0.9.2 — 2026-09-25

63 commits since v0.9.1. Every data source is still keyless and read-only. All of it is in
Surfboard's `a` AGENT view.

### RECORD

- New columns: `tok` (output tokens) and `panel` (oracle panel agreement, e.g. `✓ 39/35`). The
  role column is gone and model names are shortened (FLEET uses the same short names, keeping the
  effort word). Outvoted rows show the panel's figure or its YES/NO answer; a panel that closed
  without quorum shows as closed.
- Oracle rows show the seat's own answer.json value and notes. `bytes32` answers are decoded to
  their text (`Strasbourg`, not `0x5374…`); a value that is not valid text keeps its hex.
- Every answer ends in `»`, which opens a popup:
  - **ANSWER** (oracle rows): question, this seat's answer (the full hex, with the decoded text
    beneath for `bytes32`), the panel result and notes;
  - **SUBMISSION** (other rows): the job and its nodes, the objective, this seat's status, usage,
    checks, findings and full reply, and up to eight other seats' answers.
  Both popups close with Space, Escape or the `X` at the top right.
- `more` loads 20 older rows at a time (up to 400); the title toggles `all` / `not completed`;
  the title ends with `type 'i' to change seat`.

### Cards and hero

- COLLAB lists the seat's top two teammates; NODES shows accepted count and rate per node
  (ORACLE / REVIEW / BUILD). The third card row (ROLES, per-node cards, OTHERS, BOARD) is gone,
  so RECORD gets the room.
- RUNTIME turns a line yellow with `↑` when an update is available: the claude or codex version
  is behind the latest npm release (`@anthropic-ai/claude-code`, `@openai/codex`, checked hourly),
  or the daemon differs from the version most of the fleet runs. The tooltip says what it
  compared against, or that the check is pending or failed.
- Hero: WORK (hours and output tokens), ACCEPTED (`242 of 280`, then the rate), RANK with a
  green `▲N` / red `▼N` since the seat's rank last moved. SEAT, WORK, ACCEPTED, REVIEWED and RANK
  leave their second line blank, as STATUS does.

## v0.9.1 — 2026-09-23

- Surfboard `4` POOL4 MARKET: RECENT FLOW and BURN & SUPPLY no longer read `unavailable` for a
  day after the pool4 hook takes a fee on a liquidity operation rather than a swap (mainnet tx
  `0xd5dc8a2a…`, block 26,038,050). The swap read now also fetches the pool's `ModifyLiquidity`
  events, in the same request, so such a fee is recognised instead of being taken for a short
  read.

## v0.9.0 — 2026-09-23 (since v0.8.4, 2026-08-29)

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



## pepepane (unreleased) — 2026-09-26

This section sits below the release history on purpose: the `pepepane` branch appends to every shared file at its end so
that `git merge main` from upstream never conflicts here (spec §1 #7; `docs/decisions.md`). The branch adds one dashboard,
**PEPEPANE**, behind a lean `pepepane` console script that runs on the IdentityMD worker host itself — VPS seat #7 as user
`imd-dash`, Mac seat #420 beside Docker Desktop. Nothing is registered in the `maxpane` menu; `main`'s dashboards,
`app.py`, `__main__.py` and `themes/minimal.tcss` are unchanged.

- **PEPEPANE** (`pepepane`, key `c` for CONTROL): hero `SEAT · LIVE · TODAY · VERDICTS · GATE · UNIT`; panels NOW (with the
  "why idle" queue line), LOG (the raw daemon lines, control-stripped and redacted), LEDGER (one row per `accepted` line,
  keyed so it cannot lie: stored ≠ submitted ≠ accepted; verdicts joined by `hash12`), COST (API-equal token formulas per
  runtime, buckets per model/effort, the Codex weekly quota — tokens, never dollars), CONFIG & SKILLS (derived tiers, the
  hints fingerprint, `restart required`), MACHINE (unit, host, retention, orphans, plane). Local sources first: journald
  or `docker logs`, config-home names and mtimes, runtime transcripts, `imd` CLI text, systemd/cgroup/docker counters;
  `api.imd.fun` only for verdicts, standing and plane facts, and `--offline` removes it. `pepepane --once` prints the
  status document (schema v2, `docs/seat_status_schema_v2.md`) — usable over plain ssh at 3 a.m.
- **Control verbs** — the one recorded break of MaxPane's read-only charter, for this branch only (`docs/decisions.md`
  PEPEPANE-CTRL): restart, drained restart, stop/start, boot enable/disable, skills on/off, kill-orphans, doctor, as
  plan → apply → verify through the root stdlib broker `imd_dashd/` over a unix socket on the VPS (`SO_PEERCRED`, single-use
  plan ids, one write in flight, a fresh idle gate at apply, transient `systemd-run` children with the worker's posture,
  an audit line per phase) and an in-process Docker broker on the Mac. The TUI process itself stays read-only. Tier,
  capacity and update are static CONTROL lines, not verbs.
- **Deploy** (`deploy/vps/`): socket-activated `imd-dashd.socket` / `imd-dashd.service`, the worker drop-in
  `20-hide-dash.conf`, the TUI slice fence `50-pepepane.conf`, the sshd `Match User imd-dash` block, `install.sh` (steps 1–8,
  idempotent, `--dry-run`, offline `pip --require-hashes` from `requirements.lock`), `probe_seat_host.sh` (the install-day
  checks → `docs/seat_install_probe.md`), `MANIFEST.sha256` + `VERIFY.md`; `scripts/build_wheels.sh` builds the
  hash-pinned wheel set and the deploy tarball on the Mac. `deploy/mac/README.md` for seat #420.
- **Hoist** (separately upstreamable, three commits): `widgets/swarm_table.py`, `widgets/seat_words.py`,
  `widgets/fmt.mmdd_hhmm` / `short_model`, with re-export shims at the old paths; the 545-case surf sweep read 545/545 on
  textual 8.2.8.
- **Pins**: `[project.optional-dependencies] seat` = textual 8.2.8, rich 15.0.0, httpx 0.28.1, pydantic 2.13.5;
  `requires-python >= 3.11`; everything under `imd_dashd/` is Python 3.11 syntax and stdlib only.
- **Docs**: `docs/pepepane_PRD.md` (the spec), `docs/pepepane_plan.md`, `docs/seat_status_schema_v2.md`,
  `docs/seat_install.md`, `docs/seat_install_probe.md` (placeholder until the owner runs the probe), `docs/seat_followups.md`;
  `docs/seat_PRD.md` and `docs/seat_implementation_plan.md` carry an overridden banner.


## PEPEPANE round 9 — 2026-10-04

- Six selectable hero cards open SEAT, LIVE, CONFIG & SKILLS, RECORDS, NODES and CONTROL; LIVE opens first. Each body stays composed and refreshes while hidden. Selection borders and health labels are independent.
- JOB shows cached API question and result text with literal formatting, copy icons and multi-job stepping. RECORDS adds filtering, row windows and cached detail; NODES shows verdict and paid/launch coverage. OUTPUT TOKENS has its own panel.
- CONFIG and SKILLS use stable row cursors. Existing skill and systemd boot actions share CONTROL's plan, typed-confirm, apply and independently polled verify flow. Detail popups cannot pause verification; leaving an unconfirmed plan drops it.
- Fixes D1–D12 cover string ids, Claude home slugs and recovered errors, startup/session persistence, journal facts, runtime labels, duplicated retention wording, CONTROL guidance, busy backoff, idle tail health, canary-safe API text and cursor preservation.
- New job/submission/oracle reads share a two-request cycle budget and a rollback-compatible schema-1 ledger cache. Text is bounded and retained for 400 records; offline mode and API outages preserve cached facts.
- Independently measured body pins yield a 131×40 screen minimum. Full table tiers fit within it. Final fixture/offline cold physical peak: 62.3 MiB while visiting every body.
- Root broker identity is imd-dashd 0.1.5. Control verbs, gates, units and installer are unchanged. Follow-ups and the full verification inventory are in `docs/seat_followups.md` and `docs/pepepane_round9_verification.md`.


## PEPEPANE round 9 fixes — 2026-10-04

- Gate previews use their own clock and successful-read timestamp: 60 seconds normally, 15 seconds on CONTROL, and each poll during a write flow. Lifecycle and phase changes still refresh promptly. Busy pauses skip the preview's standing read without changing fresh plan/apply checks. Extra UI refreshes share the API interval budget.
- Running attempts join by identity and a bounded start-time window. Ambiguous or unidentified attempts remain separate, and stale standing cannot attach a finished attempt's verdict or usage to a new retry.
- Fallback verdicts require current seat ownership and retain valid terminal outcomes after reassignment. Accepted fallback records carry the job state. API/local merges preserve grouped facts, reconcile uniquely identified missed storage events and avoid duplicate attempts.
- JOB shows an unknown finished verdict explicitly. Starting and reloading units keep the correct SEAT label. CONFIG leaves ambiguous auto-update command forms unavailable.
- Root broker files and identity remain imd-dashd 0.1.5. The existing 131×40 screen minimum is retained. Deferred byte-budget, cached-redaction and busy-class concerns are recorded in the follow-ups document.
- Ledger refreshes share their row snapshot and hydrate full text only for bounded JOB/RECORDS output. NODES retains all-history counts and coverage through structured queries; detached detail reads keep a stable candidate list per run.
- CONTROL audit tests now exercise the real manager read path. The detail-popup timer proof detects suspended verification, and an open confirmation block is checked at the 131×40 screen size.

## PEPEPANE round 9 second fix — 2026-10-05

- Tests under `tests/` now refuse and record external connection and name-resolution attempts, failing teardown even when application code catches the error. The full blocking survey identified and isolated the Mac CONTROL test and two FrenPet snapshot tests. Subprocesses and the separate sybilkit suite remain outside this in-process guard.
- Clear fallback pending outcomes after a local attempt closes without submitting; retain owned node failures without inheriting another attempt's successful state.
- Reconcile missed stored events using the measured API timestamp lead and a bounded clock window, preserving unique-attempt checks and rollback-compatible ledger storage.
- Pair live local attempts before filtering stale standing rows, removing finished-attempt phantoms without stripping a newer attempt's node labels; retain ambiguous evidence.
- Retry failed gate reads from the post-failure clock while preserving in-flight triggers, and refresh busy gate previews once at each API pause boundary without accelerating busy-broker or unavailable-plane reads.
