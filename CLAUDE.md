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
(render primitives only). Widgets never import from `data/` or `analytics/`; they receive
`str`/`int`/`float`/`bool`/`dict`/`list[dict]`.

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
| 1 | `surf` | Ethereum | surfsurf.eth Surfboard: announce channel + launch detectors |
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
On screen the dashboard therefore speaks only patterns: *linked*, *fan-out*, `⚑`/`◌`/`?`, and
every panel has its own composited forbidden-word test. **The word "sybil" lives in the standalone
library, not in the dashboard's language**: it appears in maxpane only in the adapter's own
`FORBIDDEN_WORDS` list, in module comments, and in file/identifier names — never in a rendered
string. `analytics/curator_signals.py` still never mentions or imports the library
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

**The sweep is detached, on the `_spawn_crosscheck` precedent.** Tier-B/C analysis (tx
fingerprints via publicnode/tenderly batches, first funders via Blockscout — all keyless, all
budgeted to *candidate* members, never the full population, resumable through a cursor in the
slot) is spawned, never awaited, so it cannot block first paint;
`test_the_first_payload_is_not_behind_the_analysis_read` is the tripwire and it fails by timing
out. It lives on its own long tier — `TIER_ANALYSIS` (1800 s, 300 s after a failure) with the
`SLOT_CLUSTERS` last-good — so the analysis panels carry an `as of HH:MM` on a slower clock than
the title bar's, deliberately. A failed sweep folds into the **`logs`** degraded group only when
there is nothing to serve; otherwise a stale `analysis_as_of_hhmm` is the signal.

**Nothing is persisted as a verdict.** The slot holds revisable rows; groups carry a band *word*
and their families, never a boolean, and a test scans the cache file for one. A later sweep may
re-admit a wallet to the clean list, which is the point. The on-screen banding is **structural,
not numeric**: noisy-OR puts every gated cluster at ≥ 0.77, so `high` means ≥ 3 distinct families
or funding present and `low` means exactly two — a numeric cut would band nothing. (The library's
own 0.5 flag threshold is likewise structurally inert: everything that survives the ≥ 2-family,
≥ 5-member gate is already above it, so `flagged` == clustered.)

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
**143 columns** (`__main__.FULL_LAYOUT_COLUMNS`, pinned by tests that render
the real screens at that width). The 143 is **FWA**'s: surf held this number at
176 and then 152, and now measures **142**, one column under FWA. Launch forces
17 pt — about 169 columns on a laptop — so the top tier was unreachable until
`--font-size` / `MAXPANE_FONT_SIZE` existed; at 143 it is reachable without one.

The record, appended never rewritten: **198 → 172 → 143 → 176 → 152 → 143**.
The first three are FWA's own (see the `c` paragraph below); 176 and 152 are
surf's; and the last is FWA's again, reached without FWA moving at all — surf
came down under it when the dev-activity row's cells were sized to the
vocabularies its producer actually emits (`{dev, ops}`, `DEV_TX_KINDS`), taking
that panel 66 → 58 columns and the surf screen 152 → 142. Surf then went back
to **143** on 2026-08-12 — level with FWA, not under it — when its market panel
was re-measured against a *tight* IMD/FP peg: the dollar gap prints six
decimals below $0.01, so the healthier the peg the wider the row, and 142 had
been measured against a capture whose 2.75% spread prints the narrow case. The
app-wide number is the max of the two and did not move. Which dashboard binds
is itself a measurement; do not assume it from an older paragraph, and measure
a data-dependent width against the state the data is normally in.

**Curator measures 138** and moves nothing. Dashboard eight arrived on
2026-08-17 five columns under FWA's 143, so `FULL_LAYOUT_COLUMNS` is
untouched and the record above is **not** appended to — that record tracks
changes to the app-wide number, not every dashboard's own. The binding panel
is `CuratorSignals`, the rail's seven-row detector list ending in YOU;
`CuratorLeaderboard` clears at 134, `CuratorActivity` at 127 and
`CuratorClusters` at 123. The number is **height-independent**, and only
because `#curator-right-rail` reserves its scrollbar gutter
(`scrollbar-gutter: stable`): without that, the scrollbar took its column out
of `CuratorSignals` only on terminals under 42 rows, so this layout's *width*
requirement moved with its *height* and one pin was true at 48 rows and one
column short at 40. The sweep lives in `tests/screens/test_curator_screen.py`
and starts deliberately away from the pin, since a sweep that began at the
constant would agree with it by construction.

**The `f` view (2026-08-18) measures 137 and moved nothing either.** The
analysis body clears one column *inside* `CURATOR_FULL_LAYOUT_COLUMNS` and six
inside FWA's 143, so neither constant changes and the record above is again
**not** appended to — it tracks the app-wide number, which has not moved since
2026-08-12. Its binding panel is `CuratorOperators` (the 82-column evidence
cell), pinned by `test_the_analysis_binding_panel_is_the_operators_table`
rather than by this sentence. The two swapped bodies bind on *rows* instead:
the `f` body is whole from **48** rows and the `y` body from **40**, and below
each the body scrolls and the title bar says `‹ taller`.

143 clears every *layout*, not every possible string. Surf's announce feed
still lights `‹ widen` there whenever a post links a transaction: the post's
own punctuation glues the URL to the 66-char hash into one unbreakable token
(the captured one is 91 columns and clears at 216). That marker is correct and
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
against a `2fr` rail instead of a `3fr` slot, and at a **3:2** seam it needed
176 for its widest row layout — which moved the app-wide number 143 → 176, the
first time it had gone **up** and the first time a dashboard other than FWA
set it. Widths in between are not clipping: the panel names the columns it shed.

Later the same day the seam itself moved, **3:2 → 7:6**, and the number came
back **down: 176 → 152** — the first time it has fallen without a panel being
hidden or a field re-cut; only the split between the two columns changed. The
two binding panels are the announce feed (81 columns) and the dev-activity
rail (71), so 81 + 71 = 152 is the arithmetic floor, and 3:2 had been handing
the feed 0.60 W against the 0.538 it needed — the rail only reached 71 at 176.

**The move cost the feed its wrapping tier below 152, and the fix was not the
obvious one.** The feed's share fell with the seam, so it reached the 81
columns it then needed at 151 where 3:2 reached them at 135 — one truncated
line per post in between. The instinct is to widen the feed's column back;
**measure before you do.** Measured *in that era*, a 9:7 seam wrapped from 144
and cost 9 columns of full-layout width (152 → 161), because the panel binding
at 152 was the *dev-activity rail*, not the feed. The feed's own
`FULL_TEXT_WIDTH` was the cheap lever instead: 76 → 71 wraps from **142** and
left the full layout at 152 exactly. It buys the wrapping with *rows* instead
of columns, and the feed is the panel this layout hands its spare rows to.

**Then the number came down again, 152 → 142, and the binding panel changed
hands.** `SurfDevActivity` was reserving a 12-column wallet cell for the
two-word vocabulary its producer emits (`dev`/`ops`) and giving the kind cell
one column less than `"fwa claim"` needs, so it was simultaneously padded and
cutting a value mid-word. Sizing both cells to the producer's own vocabularies
took the panel 66 → 58 columns; it now clears from a **135**-column terminal
and the last marker standing on the surf screen is the **announce feed's**, at
142. Anything above that reads "the dev-activity rail is what binds" — this
file included, one paragraph up — is the old regime. Consequently
`FULL_LAYOUT_COLUMNS` went **152 → 143**: FWA is the widest dashboard again,
with surf one column under it. The full record:
**198 → 172 → 143 → 176 → 152 → 143**, FWA setting the first three and the
last, surf the two in between. 143 is inside the ~169 a laptop gets at the
forced 17 pt, so the full layout still needs no `--font-size`.

**The seam is now three columns off optimum, on purpose.** 7:6 was measured
when the feed needed 81 columns and the rail 71; they need 76 and 63 today, so
the two sum to 139 while 7:6 collects 142 (re-swept seam by seam in
`tests/screens/test_surf_screen.py` — 11:9 and 23:19 reach 139, 9:7 now also
costs 142, and 3:2 costs 156). Those three columns are not worth re-cutting a
settled layout for: the app-wide number is FWA's 143, so surf clearing at 139
would move nothing a user sees. Re-sweep before re-seaming, and only when one
of the two panels' needs moves again.

Keys: `m` menu · `tab` cycle games · `r` refresh · `t` theme · `q` quit.
Per-dashboard: `c` swaps the shared bottom-right slot (FWA, TTT, Talismans,
curator); **`y` on curator** swaps the whole body for the reader's own
standing — ladder, share, and what passing the rank above would cost — with the
hero left in place so the doomsday clock never leaves the screen (`esc` backs
out, one-way); **`f` on curator** swaps in the linked-wallet analysis (OPERATORS
/ SEGMENTS / CLEANED LIST), also keeping the clock; **`l`** opens one full-width
record table, with `c` switching RAW/CLEANED and remembering the choice;
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
pytest                                    # ~4650 tests, must be green
pytest tests/analytics/                   # pure math
pytest -x                                 # stop on first failure
cd sybilkit && python -m pytest           # the second distribution, ~290 tests
cargo test                                # the Rust intro crate, from maxpane/ (443)
```

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
both TTLs. Rendering one costs columns: curator caps a name at 12 (`NAME_COLS`,
exactly `surfsurf.eth`) because 15 moved its full layout 138 → 144, past the
app-wide 143 — measure before widening an identity cell, and show the whole name
only where there is room for it.

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
