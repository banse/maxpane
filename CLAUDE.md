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
sybilkit/                   SECOND in-repo Python distribution — see below
tests/                      analytics/ data/ screens/ widgets/ fixtures/
docs/                       per-project research, PRDs, implementation plans, code reviews
scripts/                    one-shot tooling (ABI vendoring etc). Imported by nothing.
```

**Data flow:** `client` (fetch, keyless) → `cache` (tiered TTL, persisted to `~/.maxpane/`) →
`manager` (`fetch_and_compute()` → a flat dict) → `screen` (dispatch to widgets) → `widgets`
(render primitives only): they receive `str`/`int`/`float`/`bool`/`dict`/`list[dict]`.

**Widgets may import pure, stdlib-only helpers from `analytics/`; they may not import
`data/`.** This line used to read "widgets never import from `data/` or `analytics/`", and
that was fiction on both halves — measured on 2026-08-24, **22 widget modules across four
dashboards already import `analytics/`** (`base/*` ×12 take their formatters from
`analytics/base_tokens`, `frenpet/*` ×5 from `analytics/frenpet_battle`, the bakery-era
`ev_table`/`cookie_chart`/`hero_metrics`/`leaderboard` ×4, and `surf/feed` ×1) and **10 still
import `data/`** (`base/*` ×8 for `data.base_models`, `leaderboard`/`activity_feed` for
`data.models`). Those ten are legacy debt, not licence: a widget that imports `data/` is
importing a layer that imports `httpx`. What the rule is really protecting is *purity* — no
I/O, no clock, no Textual, nothing that can reach the network — so state it that way and
prove it rather than banning a name.

`tests/widgets/test_surf_widget_contract.py` is the worked example and is stronger than the
ban it replaced: an allowlist of analytics modules a surf widget may import, plus
`test_the_allowed_analytics_modules_are_themselves_pure`, which AST-walks each allowed
module's **own** imports — and every `maxpane_dashboard.analytics.*` it finds from there, to a
fixed point — asserting none of them reaches `data`, `textual`, `httpx` or `aiohttp`. The
recursion is the part that bites: a depth-1 version was green while `analytics/surf_feed`
imported `analytics/surf_signals`, which reaches `data` in one more hop.

**`sybilkit/` is a second Python distribution in this repo**, a sibling of the `maxpane/` Rust
crate rather than a package inside `maxpane_dashboard/`: its own `pyproject.toml`, its own
`tests/`, its own version, its own PyPI name. It is a general keyless EVM sybil/fan-out cluster
toolkit — THE LIST is one *preset* it ships, not its subject — and it is **maxpane-independent**:
nothing under `sybilkit/` imports the dashboard, Textual, or httpx-at-import (the core is
stdlib-only; `httpx` is the optional `[sources]` extra, imported lazily inside the call that
needs it). Build it with `python -m build sybilkit/`; the root `python -m build` does not, and
must not, build it. See `sybilkit/README.md` for the release step. Only **one** maxpane module
imports it — `data/curator_clusters.py` — and that import is guarded (see the curator section).

## The eight visible dashboards

| # | `--game` | Chain | Subject |
|---|---|---|---|
| 1 | `surf` | Ethereum | surfsurf.eth Surfboard: announce channel (replies threaded behind an expand/collapse toggle, and NEW REPLY on the rail so a collapsed thread still announces itself), ten detectors, v3→v4 migration + launchpad (`l`) view |
| 2 | `curator` | Ethereum | THE LIST: zero-custody allowlist game, hourly doomsday clock, linked-wallet analysis |
| 3 | `fwa` | Ethereum | Fake World Assets, inverse-weighted NFT gacha pool |
| 4 | `base` | Base | trending tokens, volume, signals |
| 5 | `frenpet` | Base | pet battles, leaderboard, activity |
| 6 | `cattown` | Base | fishing competition, KIBBLE economy |
| 7 | `ttt` | Ethereum | Ten Thousand Tokens, NFT + UniV4 burn-to-launch |
| 8 | `talismans` | Ethereum | core-conservation NFT collection |

`surf` is position 1 and the `--game` default; `fwa` moved to position 2 on 2026-08-10, and
`curator` took position 2 from it on 2026-08-17. Neither is the dashboard whose data is
prefetched at launch — that is still `surf`, and it is meant to stay that way.

Hidden from the selection pane, code and tests intact: `bakery` and `ocm` (hidden on request),
`dota` (its backend is NXDOMAIN, so it could only ever render an unavailable state; 77 client
tests still pass), and three FrenPet variants (`frenpet_full`, `frenpet_wallet`,
`frenpet_perf`). Ten themes are registered.

**Hiding a dashboard touches six surfaces and they must agree**: `GAMES` in
`screens/game_select.py` (keys stay contiguous 1..N — a test asserts it), `_GAME_CYCLE` in
`app.py`, the `--game` `choices` *and* `default` in `__main__.py`, plus this table and the
README. Hiding the current default silently breaks launch, so check `default=` every time.
Tests must derive game ids from `GAMES` rather than naming them: hardcoded ids turn a
deliberate hide into a red suite.

**The sixth is `MaxPaneApp.__init__`'s own `initial_game=` default** (`app.py`), and it was
missed by the 2026-08-10 reorder — this list said "five" and the reorder obeyed it. Production
never saw it, because `__main__.py` always passes `initial_game=args.game`, but a bare
`MaxPaneApp()` (tests build one) prefetched FWA while the menu opened on Surfboard. It is now
pinned to `GAMES[0]` by
`tests/test_app_startup.py::test_a_bare_app_prefetches_the_dashboard_the_menu_opens_on`. Like
`_GAME_CYCLE` and the `--game` `choices`, it stays a **hand-typed literal rather than an import
of `GAMES`** — deriving it would make that test compare a constant against itself and it could
never fail again. Redundancy plus an agreement test is the pattern here; do not "simplify" any
of the three into a derivation.

**Adding one touches the same six**, in the order app.py → `__main__.py` → `GAMES`: the
registration tests derive their expectations from `GAMES`, so growing that list first turns
`tests/test_cli_game_choices.py` and `tests/test_app_startup.py` red until the wiring catches up.
There are two worked examples and they are different shapes.
`tests/test_surf_registration.py` is the **append** — surf went in at position 1 and no other
key moved. `tests/test_curator_registration.py` is the **position-2 insert**: every key below
it shifted, the CLAUDE.md and README tables renumbered with it, and the hardcoded lists in the
tests had to grow too: `ALL_GAMES` in `tests/test_app_startup.py`, and **`MANAGER_ATTRS`, which
exists in four files** — `tests/test_app_startup.py`, `tests/test_surf_registration.py`,
`tests/test_game_select_quit.py` and `tests/test_curator_registration.py`. Grow every copy
(`rg -n MANAGER_ATTRS tests/`): an ungrown one leaves a **real** manager inside `run_test()`,
and the `q` those tests press awaits its real `close()`, so a headless "zero network" suite
overwrites the developer's own `~/.maxpane/<game>_cache.json` with an empty one. Three of the
four were grown for the curator and the fourth was not, which is exactly how it happened; the
copies stay hardcoded (a derived list cannot see a manager that was never built) and
`tests/test_curator_registration.py::test_every_copy_of_manager_attrs_names_every_manager_the_app_builds`
is the agreement test that finds the next missed one — it discovers the copies by walking
`tests/`, so a fifth file is covered the day it is written. Prefer the insert's example when
the new dashboard is not going at the end.

### THE LIST's linked-wallet analysis — the `sybilkit` seam (2026-08-18)

Curator grew a **third view**, not a ninth dashboard: `f` swaps the dashboard body for
MODE_ANALYSIS (OPERATORS / SEGMENTS / CLEANED LIST) with the hero left in place so the doomsday
clock never leaves the screen, `e` exports the cleaned list, and the `y` view and the leaderboard
each grew a field off the same result. **There is no six-surface renumber for an expansion** —
`app.py`, `__main__.py` and `GAMES` are untouched.

**`data/curator_clusters.py` is the only maxpane module that imports `sybilkit`**, and
`test_only_curator_clusters_imports_sybilkit` asserts exactly that by walking every `.py` under
`maxpane_dashboard/` (`rg -n "import sybilkit|from sybilkit" maxpane_dashboard/` must return that
one file). It is also the *translation boundary*: the library is a general sybil-analysis toolkit
and may say so in its own strings, but `pattern_language()` re-checks every reason, label and
detail — including strings read back from a **persisted** payload, because a hand-edited cache
file is third-party input too — and swaps a forbidden word for the evidence family's own phrase.
On screen the dashboard's evidence labels therefore speak only patterns: *linked*, *fan-out*,
`⚑`/`◌`/`~`/`?` (high/low/review/unknown), and every evidence panel has its own composited
forbidden-word test.
`analytics/curator_signals.py` still never mentions or imports the library
(`test_curator_signals_never_imports_sybilkit`); its only post-release change is the decided
`LEADERBOARD_LIMIT = 100` payload cap for the `l` record view. The Tier-A `find_clusters` it
already had is unchanged and it never learns the library exists.

**The import is guarded** (`try/except ImportError` → `SYBILKIT_AVAILABLE`), and that flag is the
packaging story, not defensive habit. **`sybilkit` published to PyPI as `0.1.0` on 2026-08-19**
(https://pypi.org/project/sybilkit/0.1.0/), and maxpane's `pyproject.toml` declares
`sybilkit>=0.1.0` from **v0.8.0** onward — not before, because a `pip install maxpane` that fails
to resolve is worse than a view that degrades. That was the whole reason the dependency was held
back, and it is why the guarded import **stays**: an older install, a partial environment or a
future name change still renders `analysis unavailable` and leaves everything else working
exactly as before, rather than crashing on import.

**The analysis is read, not swept, on the `_spawn_crosscheck` precedent (2026-08-27).** THE LIST's
published, immutable linked-wallet analysis — keyless, from `clustermap.vibingco.de`, the one new
host, with no key/token/secret anywhere near it — replaced the locally computed tx-fingerprint/
funder sweep: one version check per tick, and the two bulk reads (~8.3 MB) run only
when `content_hash` has moved, because a published version never changes under its own id. The
read is spawned, never awaited, so it cannot block first paint;
`test_the_first_payload_is_not_behind_the_analysis_read` is the tripwire and it fails by timing
out. It lives on its own long tier — `TIER_ANALYSIS` (1800 s, 300 s after a failure) with the
`SLOT_CLUSTERS` last-good — so the analysis panels carry an `as of HH:MM` on a slower clock than
the title bar's, deliberately: the marker advances only when a genuinely new version lands, never
on a tick that found nothing new, because printing a fresh time beside days-old data would be a
stale number presented as live. `analysis_version` names *which* analysis sits behind that marker.
`content_hash` is publisher-asserted and never reverified against the fetched bytes — a trust
boundary, not a defect. Superseded exports are archived into
`~/.maxpane/archive/<version-id>-<hash12>/`, never deleted; nothing prunes that directory and
nobody owns doing so. A failed read folds into the **`logs`** degraded group only when there is
nothing to serve; otherwise a stale `analysis_as_of_hhmm` is the signal.

**Nothing is persisted as a verdict.** The slot holds revisable rows; groups carry a band *word*
and their families, never a boolean, and a test scans the cache file for one. A later sweep may
re-admit a wallet to the clean list, which is the point. The on-screen banding is **structural,
not numeric**: noisy-OR puts every gated cluster at ≥ 0.77, so `high` means ≥ 3 distinct families
or funding present and `low` means exactly two — a numeric cut would band nothing. (The library's
own 0.5 flag threshold is likewise structurally inert: everything that survives the ≥ 2-family,
≥ 5-member gate is already above it, so `flagged` == clustered.)

### THE LIST record-view filters and hero contract (2026-08-23)

An empty filter is not an empty result: applying a filter with every field unset returns the raw
list and switches the view back to RAW. In the NFT HOLDERS editor, custom collection controls and
the selected collections share two outer columns. Selected collections use their own compact
two-column, row-major grid: first row left, first row right, then the next row, with no blank rows
between entries.

The three record-list hero cards have a five-line contract. Keep the order stable:

1. The summary card shows `THE LIST`, wallet count, the view's primary total, its context, then
   `list FROZEN`, `list CLEANED`, or `list FILTERED`. The raw primary total is routed ETH, cleaned
   uses points, and filtered uses points followed by routed ETH without a `deposited` suffix.
2. The wallet card shows the verified ENS name or `YOUR WALLET`; `#rank of total · raw|clean|filtered`;
   join/hour detail or the active filter summary; `points · credited ETH`; and the full wallet
   address. The address stays visible even when ENS exists. The title, standing, points/ETH, and
   address use success green; the detail line uses `$success-darken-2`, matching the view word.
3. The filter card shows `THE FILTER`, then the four shortcuts: `'1' - first 1000 wallets`,
   `'2' - joined hour 0`, `'3' - whale splash`, and `'f' - more filters`.

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

**Layout is a function of terminal columns**, and the rules for it are in a
skill, not here: **`.claude/skills/terminal-layout/SKILL.md`**. Read it before
changing anything that affects how a dashboard is sized — a panel width, a
column budget, a cell formatter, an `fr` seam, a scrollbar gutter, a
`min-height`, a `‹ widen` / `‹ taller` marker, or any width or height pin. It
carries the measurement method, the fitting rules (`cell_len`, not `len()`),
what `DataTable` and `RichLog` do silently, and how to test a layout so the test
can fail.

The app-wide pin is `__main__.FULL_LAYOUT_COLUMNS = 143` (FWA's). Every other
pin lives on its own constant with its reasoning in a `#:` block beside it; this
file deliberately keeps no second copy of the numbers, because a copy drifts
from the code and a docstring cannot.

Keys: `m` menu · `tab` cycle games · `r` refresh · `t` theme · `q` quit.
Per-dashboard: `c` swaps the shared bottom-right slot (FWA, TTT, Talismans,
curator); **`l` on surf** swaps the whole dashboard body for the v4
launchpad's own five panels in two columns (LAUNCHPAD COINS over LAUNCHPAD
ACTIVITY on the left; CURVE FLOW / BURN PIPELINE / BURNKEEPERS in the rail —
curator's `y`/`f` precedent), with the hero (LAUNCHPAD/FLOW/BURN/SUPPLY)
left in place so nothing it tracks ever goes dark (`esc` backs out, one-way); surf's
status hint reads `l launchpad`. Surf's own `l` and curator's own `l` (the
record view, described below) are unrelated bindings on two different
screens, not one shared key. **`y` on curator** swaps the whole body for the reader's own
standing — ladder, share, and what passing the rank above would cost — with the
hero left in place so the doomsday clock never leaves the screen (`esc` backs
out, one-way); **`f` on curator** swaps in the linked-wallet analysis (OPERATORS
/ SEGMENTS / CLEANED LIST), also keeping the clock; **`l`** opens one full-width
record table under its own raw/wallet/cleaned summary hero, with `c` switching
RAW/CLEANED and remembering the choice; each list keeps its own typed header-click
sort, with a second click reversing it and the fixed YOU row excluded;
**`e`** exports the active list (`f` keeps its existing JSON + CSV export, while
`l` writes the full uncapped raw or cleaned JSON), and is a no-op on dashboard
and wallet modes; and **`w` on curator** prompts for the wallet its YOU row is about —
`WalletInputScreen` validates and persists to `~/.maxpane/config.toml`, so it
is app-wide from the next launch. A runtime wallet switch is more than an
assignment: `CuratorManager.set_wallet` also drops the wallet last-good (its
payload names the *old* address) and expires the fast tier, because a tier
with 12 of its 15 seconds left is "fresh" and the row would stay dark after a
keypress that looked like it worked. Curator's status hints read
`c panels · y you · f linked · l lists`. The redundant `view: closest` /
`view: clusters` tail was removed so all four labels and the worst-case
`4 errors` fit at 138 columns; each visible panel title already names that
state, and the list title is the sole RAW/CLEANED indicator. Any doc that quotes
the old hint is wrong.
Logs go to `~/.maxpane/maxpane.log`; caches to `~/.maxpane/*.json`; curator's
analysis `e` export to `~/.maxpane/curator_clean_list.json` and `.csv`, and
list-view exports to `curator_raw_list.json` or `curator_cleaned_list.json`.

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
.venv/bin/python -m pytest                    # 5,630 tests, ~11 min — see below
.venv/bin/python -m pytest tests/analytics/   # pure math
.venv/bin/python -m pytest -x                 # stop on first failure
.venv/bin/python -m pytest sybilkit            # the second distribution, 428 tests + 1 xfail
cargo test                                    # the Rust intro crate, from maxpane/ (443)
```

**The full suite takes ~11 minutes. Run it when it is actually necessary, not after every
task.** Necessary means: before a merge or a push that follows real code changes, at the end of
a multi-task branch, or when a change could plausibly reach code no targeted run covers. After a
single task — and always after a docs-only, comment-only or constant-rename edit — ask what
could have broken and run *that*: the widget's own test file, plus the screen test that
composites it; a data module's file, plus the manager test that consumes it. A docs edit usually
needs nothing, or the one test that pins the doc's content. Citing the last real green run is
better than spending eleven minutes to re-learn it.

Parallel agents run **only their own test files, never the suite** — a neighbour mid-edit
reddens it for a reason that is not yours, and eleven minutes per agent per task is the largest
avoidable cost in a multi-agent branch.

Use `.venv/bin/python -m pytest` — the system `python3` lacks the deps and produces alarming
collection errors that mean nothing. That applies to `sybilkit/` too, and there it is not
cosmetic: its fetcher tests need the `[sources]` extra, so an interpreter without `httpx`
*skips* them rather than erroring, and a suite that reports green having skipped its network
layer is the worst of both.

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
And check the widget can *tell*: a row whose real negative has no representable value —
"no whale in the last hour", "it has never fired" — renders `None` identically for "we looked
and there was nothing" and "we could not look", so it reads confident and green through an
outage. Curator's rail shipped that way: FARM said `-- unknown` off `clusters_count is None`
while HOUR SAVED and WHALE, folded from the same dead group, said `none yet`. Either give the
value a representable zero or hand the widget the `degraded` list.

**ENS names are third-party strings, and the widest kind.** Reverse resolution
lives in `data/ens.py` and is keyless; use it through a client's own multicall so
it inherits that dashboard's pool. Two rules it exists to keep: the **forward
check** is not optional (a reverse record needs nobody's permission, so an
unverified lookup lets any address claim `vitalik.eth`), and a **miss is not an
empty name** — most wallets have no record, and without recording the misses
every one of them is re-resolved on every tick forever. `ens.NameStore` holds
both TTLs. Rendering one also costs columns — see the terminal-layout skill.

For record lists, the **complete raw list is the sole ENS network-hydration boundary**. Cleaned
and filtered lists reuse the raw-list ENS cache; changing filters must never start hydration
again. When hydration finishes, repaint whichever derived list is visible so newly matched names
appear immediately. Long-running ENS, JSON export, and list-reload work owns the centered footer
message while it runs (`fetching ENS …`, for example) and clears only its own message when it
finishes, so an older operation cannot erase the status of a newer one.

**Escape every third-party string before it reaches markup or a `DataTable`.** Use
`widgets/markup_safety.safe_markup`. Textual defers `Text.from_markup` into the message pump, so
a malformed name raises *outside* the screen's `try/except` and kills the app. Token symbols are
attacker-controlled: anyone can deploy an ERC-20 named `[/x]`.

**A widget that renders third-party text through `Static` hands it a pre-built
`rich.text.Text`, never a markup string.** Same defect as the rule above, one layer out:
`Static.update("…[/x]…")` does not parse anything at call time — Textual defers
`Content.from_markup` into the message pump, so the parse failure raises *outside* the screen's
`try/except` and takes the app down. Parse it yourself, synchronously, inside your own `try`
(`Text.from_markup(...)`) and a malformed row degrades to a skipped row instead. `SurfFeed`'s
`_row_text` is the worked example.

Two things do **not** help and must not be mistaken for the guarantee: `Text.no_wrap` and
`Text.overflow` are inert through Textual 8, and a *sized* cell is not a *fitted* one. Both are
in the terminal-layout skill, with what to use instead.

**Validate persisted series per point.** Use `data/series_points.coerce_points`. A single `null`
in a cache file used to abort startup for *every* dashboard.

**Inject the clock.** No module that a test needs to control may call `time.time()` internally.
Cache loaders take `now=`; signal builders take `now_ts`.

**Screens inherit `screens/refresh_guard.RefreshGuard`.** It gives skip-not-queue refresh and
joins the startup prefetch. Do not hand-roll `run_worker(..., exclusive=True)`.

**Reuse before you build.** Almost nothing here is the first of its kind, and a
new panel written from scratch is a panel that has not learned what the existing
ones were taught. Check, in this order:

1. **a shared widget module** — `widgets/*.py` (`sparkline_common`,
   `markup_safety`, `status_bar`, `signals_panel`, `activity_feed`,
   `hero_metrics`, `leaderboard`, …). Import it; never copy out of it.
2. **the dashboard's own `_fmt.py`** (`widgets/surf/`, `widgets/curator/`) for
   formatters, and the sibling panel that already does the same *shape* of job.
   `widgets/surf/launchpad_activity.py` was built on `widgets/surf/activity.py`
   — same `RichLog` body, same width-tier ladder, same "the panel names the
   columns it shed" contract — and inherited all of that for free.
3. **`templates/`** — eight copy-sources (screen, hero metrics, signals,
   leaderboard, activity feed, two-column table, sparkline, status bar) for
   when there is no sibling to follow. Copying is the point here, so read the
   hazard note in "Known hazards" before you do.

The failure this prevents is not wasted typing, it is **divergence**: three
copies of one helper means a fix reaches one of them. This branch shipped
exactly that — the strip-then-escape sanitiser now exists in three surf widget
modules, and the `len()`-vs-`cell_len()` bug they share has to be fixed three
times instead of once. If you find yourself writing something a sibling already
does, stop and hoist it instead.

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
- **A review never fixes what it finds.** A reviewer that repairs something is reviewing its
  own work by the end of the pass, its fix skips review entirely, and the diff under review
  is no longer the diff that was submitted. New findings go on the follow-up list — named,
  with their evidence — and are scheduled like any other work. This holds for a finding that
  looks trivial, and for one in the reviewer's own earlier work; "it was one line" is how a
  review turns into an unreviewed commit. A **scoped re-review** is stricter still: anything
  outside the findings it was sent to verdict gets filed, never fixed, or the fix loop never
  terminates.
- **Verifying is not fixing.** A reviewer *should* mutate the tree to test a claim — flip a
  constant, monkeypatch a cell, render at a width — and every serious defect found here was
  caught that way rather than by reading. Restore it afterwards and confirm the tree is
  clean. The line is intent: a change made to learn something is verification, a change made
  to improve something is a fix, and only the first belongs in a review.
- **The working tree may contain uncommitted user work.** Never `git checkout --` a file to undo
  your own edit — you will discard someone else's uncommitted changes with it.
