# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MaxPane is a CLI app for onchain dashboards. It started with gaming dashboards but then got
expanded to NFT and trading dashboards. Most dashboards implement a template with the same
widgets that initially got created for the RugPull Bakery gaming dashboard.

The details for all added games can be found in the `docs/` subdirectory.

For every new dashboard the workflow is like this: make a deep research and analysis about the
project that should get a new dashboard. Analyze the tokenomics / game mechanics and save the
results in a dedicated .md file in the docs directory (same pattern like the already existing
files). Then use superpowers to brainstorm ideas for the new dashboard to show the most
interesting data. If the user doesn't say otherwise use the existing template with its widgets
and find the best matching data for each widget for the specific project and create a PRD.md
specification for the new dashboard. Once the user agrees to the proposal use the
project-planner agent to create an implementation plan that divides the work in work packages
that shall be assigned to the best matching agents so they can then work in parallel on the
different work packages. Always delegate work to best matching agents, if possible in parallel.

---

## Hard constraints — read this before writing any code

**1. Strictly read-only.** MaxPane never signs, never sends a transaction, never constructs
calldata for a state change, and never prompts for a private key or keystore password. There is
no signer, no transactor, no nonce manager and no keystore anywhere in this repo, and none may
be added. If a task seems to need one, the task is wrong.

**2. Keyless.** Every data source must work with **no API key of any kind**. The app is
installed with `pipx`/`uv`/`pip` by people who should not have to register for anything. No
Alchemy, no Infura, no keyed Etherscan, no OpenSea key, no Moralis, no NFTPort. If a metric has
no keyless source, the metric is dropped and the UI says so — it is never faked and never
silently blank.

> An earlier version of this file described MaxPane as a transaction-signing bot for RugPull
> Bakery, complete with a `MAXPANE_KEYSTORE_PASSWORD` env var and an executor/transactor/nonce
> manager. **None of that ever existed in this repo.** It was documentation inherited from a
> different project, and it actively pointed agents at reintroducing key handling into a
> deliberately keyless read-only tool. If you find any instruction like that, it is wrong.

**3. No test may touch the network.** Assert it structurally — inject a transport that raises on
use. Every external payload is a committed fixture under `tests/fixtures/`.

**4. Read values live; never hardcode a documented one.** Docs drift, chains do not. Real
example: one protocol documents a 5% fee that is 1% on chain, and a "4.0×" ratio quoted in
research measured 3.885×, then 3.49×, then 2.956× on three consecutive days.

---

## Architecture

```
maxpane_dashboard/          the app (published to PyPI as `maxpane`)
├── __main__.py             CLI entry point: --game, --theme, --wallet, --poll-interval
├── app.py                  MaxPaneApp: manager wiring, screen install, _GAME_CYCLE
├── config.py
├── abis/                   vendored ABI JSON per protocol — never fetched at runtime
├── analytics/              PURE functions: signals, EV math. No I/O, no Textual imports.
├── data/                   per-dashboard client / cache / manager / models
├── screens/                one Screen per dashboard + splash, game_select, wallet_input
├── templates/              copy-sources for new dashboards — see the hazard note below
├── themes/                 minimal.tcss + the registered Theme objects
└── widgets/                shared widgets + one package per dashboard

maxpane/                    Rust intro sequence (Matrix-style boot animation), separate crate
tests/                      analytics/ data/ screens/ widgets/ fixtures/
docs/                       per-project research, PRDs, implementation plans, code reviews
scripts/                    one-shot tooling (ABI vendoring etc). Imported by nothing.
```

**Data flow:** `client` (fetch, keyless) → `cache` (tiered TTL, persisted to `~/.maxpane/`) →
`manager` (`fetch_and_compute()` → a flat dict) → `screen` (dispatch to widgets) → `widgets`
(render primitives only). Widgets never import from `data/` or `analytics/`; they receive
`str`/`int`/`float`/`bool`/`dict`/`list[dict]`.

## The seven visible dashboards

| # | `--game` | Chain | Subject |
|---|---|---|---|
| 1 | `fwa` | Ethereum | Fake World Assets, inverse-weighted NFT gacha pool |
| 2 | `base` | Base | trending tokens, volume, signals |
| 3 | `frenpet` | Base | pet battles, leaderboard, activity |
| 4 | `cattown` | Base | fishing competition, KIBBLE economy |
| 5 | `ttt` | Ethereum | Ten Thousand Tokens, NFT + UniV4 burn-to-launch |
| 6 | `talismans` | Ethereum | core-conservation NFT collection |
| 7 | `surf` | Ethereum | surfsurf.eth Surfboard: announce channel + launch detectors |

`fwa` is position 1 and the `--game` default.

Hidden from the selection pane, code and tests intact: `bakery` and `ocm` (hidden on request),
`dota` (its backend is NXDOMAIN, so it could only ever render an unavailable state; 77 client
tests still pass), and three FrenPet variants (`frenpet_full`, `frenpet_wallet`,
`frenpet_perf`). Ten themes are registered.

**Hiding a dashboard touches five surfaces and they must agree**: `GAMES` in
`screens/game_select.py` (keys stay contiguous 1..N — a test asserts it), `_GAME_CYCLE` in
`app.py`, the `--game` `choices` *and* `default` in `__main__.py`, plus this table and the
README. Hiding the current default silently breaks launch, so check `default=` every time.
Tests must derive game ids from `GAMES` rather than naming them: hardcoded ids turn a
deliberate hide into a red suite.

**Adding one touches the same five**, in the order app.py → `__main__.py` → `GAMES`: the
registration tests derive their expectations from `GAMES`, so growing that list first turns
`tests/test_cli_game_choices.py` and `tests/test_app_startup.py` red until the wiring catches up.
`tests/test_surf_registration.py` is the worked example.

## Build & run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

python -m maxpane_dashboard                      # splash → game select
python -m maxpane_dashboard --game fwa           # straight to one dashboard
python -m maxpane_dashboard --game ttt --theme fwa
python -m maxpane_dashboard --version            # version + interpreter path
python -m maxpane_dashboard --font-size 0        # do not resize my terminal
```

**Layout is a function of terminal columns.** Widgets pick a tier by width and
advertise dropped columns as `‹ widen` in their title. The full layout needs
**176 columns** (`__main__.FULL_LAYOUT_COLUMNS`, pinned by tests that render
the real screens at that width). FWA needs **143**; the 176 is **surf**'s.
Launch forces 17 pt — about 169 columns on a laptop — so the top tier was
unreachable until `--font-size` / `MAXPANE_FONT_SIZE` existed, and at 176 it
still is without one.

176 clears every *layout*, not every possible string. Surf's announce feed
still lights `‹ widen` there whenever a post links a transaction: the post's
own punctuation glues the URL to the 66-char hash into one unbreakable token
(the captured one is 91 columns and clears at 194). That marker is correct and
must not be silenced by raising the constant — the next such post brings its
own length. The width sweep therefore measures against a fixture with that
post removed, pinned by `test_a_linked_post_advertises_widen_at_the_full_layout_width`.

FWA binds `c` to swap the odds board and the activity feed in one slot, so the
bottom row is the chase board and the settlement table alone. That took the
requirement from 198 to 172 (three widgets needing 79/54/55 columns cannot
share one row until it is very wide); shortening the buy-gate signal took it to
143, because by then the *signals panel* was the binding constraint, not a
table. TTT and Talismans use the same `c` pattern.

**Surf does not** — it used to, and the binding is gone. Its 2026-08-10
restructure put all six panels on screen at once (hero full width; announce
feed beside a rail of signals over dev activity; market beside IDENTITY.MD),
so there is nothing left to swap. The cost is that `SurfDevActivity` now sizes
against a `2fr` rail instead of a `3fr` slot and needs 176 for its widest row
layout, which is what moved the app-wide number 143 → 176 — the first time it
has gone **up**, and the first time a dashboard other than FWA has set it.
Widths in between are not clipping: the panel names the columns it shed.

Keys: `m` menu · `tab` cycle games · `r` refresh · `t` theme · `q` quit.
Logs go to `~/.maxpane/maxpane.log`; caches to `~/.maxpane/*.json`.

**`__version__` comes from installed distribution metadata**, not from a
constant — `maxpane_dashboard/__init__.py` reads it with
`importlib.metadata.version`. An editable install writes that metadata **once,
at install time**, so bumping `pyproject.toml` does not change what the status
bar renders or what `--version` prints until you re-run `pip install -e .`.
This is not hypothetical: this venv reported `0.3.2` for three months and four
releases, so every dev-run status bar showed a version that shipped in April.
Re-run the editable install after a version bump, and trust `--version` over
memory when a bug report cites one.

## Tests

```bash
pytest                                    # ~2100 tests, must be green
pytest tests/analytics/                   # pure math
pytest -x                                 # stop on first failure
cargo test                                # the Rust intro crate, from maxpane/
```

Use `.venv/bin/python -m pytest` — the system `python3` lacks the deps and produces alarming
collection errors that mean nothing.

## Environment variables

All optional; all override a working default. **There are no key or secret variables.**

```
MAXPANE_ETH_RPC_URL     override the Ethereum RPC
MAXPANE_BASE_RPC_URL    override the Base RPC
MAXPANE_WALLET          default wallet address for wallet-scoped views
MAXPANE_INDEXER_DB      local indexer database path
MAXPANE_BASEBOARD_ENV   Base dashboard environment file
MAXPANE_FONT_SIZE       terminal font size on launch; 0 = leave it alone
```

## Conventions

These are not style preferences. Each one is a bug that shipped, was found, and was fixed
repo-wide.

**A failed read is `None`, never `0`.** Clients that turn an outage into `0`/empty make a manager
unable to distinguish "RPC down" from "the value is zero" — and the zero then gets *persisted*,
so the corruption outlives the outage. Never write a sentinel into a history series.

**A dead source degrades to an explicit unavailable state.** Never a crash, never a blank panel,
and never a stale number presented as live. Serve last-good behind an `as of HH:MM` marker.

**Escape every third-party string before it reaches markup or a `DataTable`.** Use
`widgets/markup_safety.safe_markup`. Textual defers `Text.from_markup` into the message pump, so
a malformed name raises *outside* the screen's `try/except` and kills the app. Token symbols are
attacker-controlled: anyone can deploy an ERC-20 named `[/x]`.

**Validate persisted series per point.** Use `data/series_points.coerce_points`. A single `null`
in a cache file used to abort startup for *every* dashboard.

**Inject the clock.** No module that a test needs to control may call `time.time()` internally.
Cache loaders take `now=`; signal builders take `now_ts`.

**Screens inherit `screens/refresh_guard.RefreshGuard`.** It gives skip-not-queue refresh and
joins the startup prefetch. Do not hand-roll `run_worker(..., exclusive=True)`.

**Sparklines import `widgets/sparkline_common`.** Do not copy the helpers.

**Assert against composited output** (`_compositor.render_strips()`), not the content string. A
string that never reaches a pixel passes a naive test while being invisible to the user.

**Prove a test bites.** Mutate the code, watch the test go red, restore. This is expected for
anything concurrency- or decoder-shaped.

## Known hazards

**The templates are how bugs propagate.** `templates/` is the copy-source for new dashboards, so
a defect there is a defect in every dashboard not yet written. This is not theoretical: a
markup crash, a refresh race and a duplicated sparkline helper all reached the newest dashboard
because it was seeded from the templates. When you fix a widget, check its template — and check
whether the template has drifted *ahead* of the widget, which also happens.

**Dead endpoints.** Verified dead, do not reintroduce: `eth.llamarpc.com` (521),
`rpc.ankr.com/eth` (now keyed), `cloudflare-eth.com` (`-32046` on Ethereum), `api.reservoir.tools`
(DNS gone, API sunset). Working keyless Ethereum: `ethereum-rpc.publicnode.com` for state (it
batches, but **refuses archive `eth_getLogs`**), `gateway.tenderly.co/public/mainnet` and
`eth.drpc.org` for logs. **State and logs need different endpoint pools.**

**Classify RPC errors on message text, not code.** Providers reuse `-32602` and `-32005` for
unrelated meanings. One provider's "suggested retry range" decrements one block per round trip
and livelocks anything that follows it verbatim.

**The DOTA game API is NXDOMAIN** — that dashboard has no live backend. The Bakery season ended
2026-06-12; its API still serves, but the season is finished.

## Working with agents

Parallel agents are the norm here. What makes it work:

- **Freeze the data contract first.** A models module exporting the key list and widget
  signatures lets many agents build against one interface simultaneously.
- **One owner per shared file.** `app.py`, `screens/game_select.py`, `__main__.py` and
  `themes/minimal.tcss` belong to exactly one work package, late in the sequence.
- **Report defects in other agents' files; do not fix them.** This is what makes findings
  trustworthy, and it is how most of the good bugs in this repo were found.
- **The working tree may contain uncommitted user work.** Never `git checkout --` a file to undo
  your own edit — you will discard someone else's uncommitted changes with it.
