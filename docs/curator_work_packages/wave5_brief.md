# Wave-5 brief — everything WP7 has to wire, and what will check it

Written by the waves-3/4 gate after WP5 (cache + manager) and WP6 (screen) landed. Full suite
**4241 passed / 0 failed / 0 skipped** in 270 s, tree clean, and **every file this branch
changes is a new file** — `git diff main --name-status` has no `M` row at all, so all six
registration surfaces are still exactly as `main` left them. WP7 has all of its work ahead of
it and none of it half-done.

Where this file and `wp7.md` disagree, this file wins (it was measured against the tree today);
where this file and the source disagree, the source wins.

---

## 0. State of the tree

| | |
|---|---|
| suite | 4241 passed, 0 failed, 0 skipped (wave 2 ended at 4030; waves 3–4 net **+211**) |
| `git status --porcelain` | empty |
| curator tests | 932 across 11 modules; waves 3–4 contributed cache 55, degradation 12, manager 81, screen 62 |
| `__main__.FULL_LAYOUT_COLUMNS` | **143**, untouched |
| `screens.curator.CURATOR_FULL_LAYOUT_COLUMNS` | **138**, independently re-swept by this gate |
| `__version__` | 0.6.1, and `pyproject.toml` agrees — `pip install -e .` will not move it |

Waves 3–4 commits, newest first: `98b8ae6` sweep the width in two dimensions and advertise a
cut rail · `4581ced` tick WP6's checkboxes · `db6c4e0` the screen · `2bf69b5` freeze three
capture-derived screen payloads · `0c5fddd` pin the other two legitimate zeros · `5dc084b` gate
the fast tier · `32124e5` an analytics failure degrades · `07ae03b` the event cap is a lower
bound · `69cee15` a dead log filter · `6075288` the persisted contributors curve · `ff304d1`
WP5 sign-off.

---

## 1. The manager — `maxpane_dashboard/data/curator_manager.py`

```python
class CuratorManager:
    def __init__(self, poll_interval: int = 30, *,
                 client=None, cache=None, wallet: str | None = None,
                 clock=time.time, cache_path: str = DEFAULT_CACHE_PATH) -> None
    async def fetch_and_compute(self) -> dict   # exactly CURATOR_KEYS, never raises
    async def close(self) -> None               # closes the client, then persists the cache
    def save_cache(self) -> None
```

- `DEFAULT_CACHE_PATH` is `~/.maxpane/curator_cache.json` (`data/curator_cache.py`). Add it to
  CLAUDE.md's caches sentence.
- `SOURCES = ("state", "logs", "wallet")` is exported from this module and is what the title
  bar's `⚠` list is built from. Import it rather than typing the three strings.
- `wallet` is normalised with `wallet or None`, so passing the empty string `get_wallet()`
  returns when nothing is configured is safe and yields the `set MAXPANE_WALLET` YOU row.

**The app's own parameter is `wallet_address`, not `wallet`** (`MaxPaneApp.__init__`), and it is
**not stored on `self`**. `wp7.md`'s sketch `CuratorManager(poll_interval=poll_interval,
wallet=wallet)` names a local that does not exist. The construction line is:

```python
self._curator_manager = CuratorManager(poll_interval=poll_interval, wallet=wallet_address)
```

and the screen, which is built later in `_launch_game` where `wallet_address` is out of scope,
should read it back off the manager (`wallet=self._curator_manager.wallet`) rather than
introducing a second stored copy that can drift from the wallet the manager actually scores.

---

## 2. The screen — `maxpane_dashboard/screens/curator.py`

```python
class CuratorScreen(RefreshGuard, Screen):
    REFRESH_WORKER_NAME = "curator-refresh"
    BINDINGS = [r, c]
    def __init__(self, data_manager, poll_interval: int = 30,
                 name: str = "curator", wallet: str | None = None, **kwargs)
```

Module-level names WP7 will want: `CURATOR_FULL_LAYOUT_COLUMNS = 138`, `INITIAL_TITLE`,
`TALLER_HINT = "‹ taller"`, `RAIL_FULL_HEIGHT`, `MANAGER_FAILURE_SECONDS = 999`,
`VIEW_CLUSTERS = "clusters"`, `VIEW_CLOSEST = "closest"`,
`CLOSEST_ID = "curator-closest-calls"`, `CLUSTERS_ID = "curator-clusters"`.

Install branch, matching the surf/fwa shape already in `_launch_game`:

```python
elif game_id == "curator":
    if not self.is_screen_installed("curator"):
        self.install_screen(
            CuratorScreen(
                self._curator_manager,
                self.poll_interval,
                name="curator",
                wallet=self._curator_manager.wallet,
            ),
            name="curator",
        )
```

### Ids the screen composes

Containers: `#title-bar`, `#hero-row`, `#middle-row`, `#curator-right-rail`, `#separator`,
`#bottom-row`. The only two widget ids the screen sets are `#curator-closest-calls` and
`#curator-clusters` (the `c` swap pair, both mounted, one hidden). Every other widget is placed
by **type** selector — `CuratorHero`, `CuratorLeaderboard`, `CuratorSparklines`,
`CuratorSignals`, `CuratorActivity`, `CuratorClosestCalls`, `CuratorClusters`.

---

## 3. `themes/minimal.tcss` — and the one thing that will break if you copy verbatim

WP7.5 says "copy `CuratorScreen.DEFAULT_CSS` into the stylesheet". **Do not copy it verbatim.
This gate ran the experiment and it collapses the layout.**

The screen's tests run under `_ThemedHarness`, which already loads the real `minimal.tcss`. So
everything WP6 measured — 138 columns, the 3:5 and 5:3 seams, all 62 screen tests — was
measured with the shared, unscoped rules at the top of `minimal.tcss` **beating**
`CuratorScreen.DEFAULT_CSS`, because an app stylesheet always outranks `DEFAULT_CSS` in Textual.
Two shared rules currently win:

| shared rule (minimal.tcss) | value in force today | what `CuratorScreen.DEFAULT_CSS` says |
|---|---|---|
| `#bottom-row` (line 126) | `height: 1fr` | `height: auto` |
| `#title-bar` (line 12) | `padding: 0 2` | no padding |

Measured on the running screen at 138×48 today: `#bottom-row` is **17 rows**, `#title-bar` is
**134 columns** wide.

Copying `DEFAULT_CSS` verbatim scopes `CuratorScreen #bottom-row { height: auto }`, which then
wins, and `CuratorActivity`'s own `height: auto` takes the screen:

```
minimal.tcss as it is now        →  hero 8 · middle-row 17 · bottom-row 17 · rail 17
+ DEFAULT_CSS copied verbatim    →  hero 8 · middle-row  1 · bottom-row 47 · rail  1
                                    "SIGNALS" and "YOU" no longer reach the compositor at all
```

The whole seven-row detector rail disappears, the screen starts scrolling (a screen scrollbar
also eats two columns, 138 → 136), and — the nasty part — the `‹ widen` count goes to **zero at
137 as well**, because the panels that were asking for a column are no longer composited. The
width test would pass while the rail was gone.

**The fix is one word.** Restate the bottom row as `height: 1fr` in the curator block:

```
CuratorScreen #bottom-row {
    height: 1fr;
    margin: 0 0 1 0;
}
```

Verified by this gate against a scratch copy of `minimal.tcss` with the whole block appended:
markers 12 at 136, 12 at 137, **0 at 138**, `#bottom-row` back to 17 rows — i.e. bit-identical
to the layout WP6 pinned. Everything else in `DEFAULT_CSS` can be copied as written.

Then either raise the disagreement with WP6 (`screens/curator.py` is their file — report, do
not edit) or make `height` on `#bottom-row` an explicit, commented exception in WP7.6's
two-copies-agree test. Do not "fix" it by changing the block to `auto`.

`#title-bar` and `#separator` stay **out** of the block, exactly as `wp7.md` says: the shared
rules already style them for every screen, and `WORST_CASE_TITLE_COLUMNS = 90` was swept with
the shared `padding: 0 2` in force, so 90 ≤ 134 holds.

### Selectors the block needs

Screen-level geometry only, the surf/FWA block shape. Ids scoped to `CuratorScreen`, widget
types unscoped (none of them exists on another screen):

```
CuratorScreen #hero-row              height: auto; margin: 1 0 0 0      (no vertical padding)
CuratorHero                          width: 1fr; padding: 0 1
CuratorScreen #middle-row            height: 1fr; margin: 1 0 0 0
CuratorLeaderboard                   width: 3fr; padding: 0 1
CuratorScreen #curator-right-rail    width: 5fr; height: 1fr; overflow-y: auto;
                                     scrollbar-gutter: stable; scrollbar-size: 1 1
                                     (no vertical padding)
CuratorSparklines                    width: 1fr; height: auto; padding: 0 1; margin: 0 0 1 0
CuratorSignals                       width: 1fr; height: auto; padding: 0 1
CuratorScreen #bottom-row            height: 1fr; margin: 0 0 1 0     ← see above, NOT auto
CuratorActivity                      width: 5fr; height: auto; padding: 0 1
CuratorClosestCalls                  width: 3fr; height: auto; padding: 0 1
CuratorClusters                      width: 3fr; height: auto; padding: 0 1
```

`scrollbar-gutter: stable` on the rail is load-bearing, not cosmetic: it is the whole subject of
commit `98b8ae6`. Without it the rail's inner width is a function of the terminal's *height*,
and the pinned width was true at 48 rows and false at 40.

The `3fr`/`5fr` and `5fr`/`3fr` seams are **measurements**, re-swept with the gutter in place
(10:17 / 7:12 / 13:22 / 17:29 reach 137, 3:5 and 4:7 reach 138, 5:8 → 140, 1:2 → 150, 1:1 → 173).
Do not tidy them into 1:1.

**No CSS class from a widget's own `DEFAULT_CSS` belongs in this block.** The inner classes —
`.curator-lb-title` / `.curator-lb-note` / `#curator-lb-table`, `.curator-signals-title` /
`.curator-signals-row`, `.curator-spark-title` / `.curator-spark-line`,
`.curator-activity-title`, `.curator-cc-title` / `.curator-cc-note`, `.curator-cl-title` /
`.curator-cl-note`, `#curator-hero-boxes` / `CuratorHeroBox` / `#curator-hero-note` — are all
owned by the seven widget modules and none of them collides with a shared selector. The surf
block sets the precedent: restate a widget's internals here and you give one rule two owners.

---

## 4. The six surfaces, in the order they must be edited

`app.py` → `__main__.py` → `GAMES`. The registration tests derive from `GAMES`, so growing that
list first turns four suites red until the wiring catches up.

### 4.1 `app.py` — seven edits, not eight

`wp7.md`'s step 5 ("the initial-game chain: `elif self._initial_game == "curator":`") **does not
exist in this file.** There is no such chain; `rg -n "_initial_game" maxpane_dashboard/app.py`
returns four hits and none of them is a branch. The prefetch is a single dict in
`_prefetch_manager`. Ignore that step.

| # | edit | where |
|---|---|---|
| 1 | `from maxpane_dashboard.data.curator_manager import CuratorManager` | manager import block (~line 18) |
| 2 | `from maxpane_dashboard.screens.curator import CuratorScreen` | screen import block (~line 35) |
| 3 | `self._curator_manager = CuratorManager(poll_interval=poll_interval, wallet=wallet_address)` | beside `self._surf_manager` (~line 104) |
| 4 | `"curator": self._curator_manager,` | the `_prefetch_manager` dict (~line 164) |
| 5 | `elif game_id == "curator":` install branch | `_launch_game`, after the surf branch (~line 297) |
| 6 | `_GAME_CYCLE = ["surf", "curator", "fwa", "base", "frenpet", "cattown", "ttt", "talismans"]` | ~line 200, **hand-typed literal** |
| 7 | `await self._curator_manager.close()` in its own `try/except` | the shutdown chain (~line 459) |

The sixth *surface* (`initial_game: str = "surf"`, line 72) is **verified and not edited** —
curator goes in at position 2, surf stays position 1. Say so in the commit body; the 2026-08-10
reorder was missed precisely because nobody wrote that down.

### 4.2 `__main__.py`

One edit: insert `"curator"` at index 1 of the `--game` `choices` list (line 256). Leave
`default="surf"` (line 255), the help text, `--theme` `choices` (line 242) and
`FULL_LAYOUT_COLUMNS = 143` (line 59) alone.

### 4.3 `screens/game_select.py`

Insert at key `"2"` and renumber 3..8. Leave every commented-out hidden row where it is —
those comments are the restore instructions.

Measured, since WP7.4 asks: the proposed description makes the row
`[2] THE LIST — Zero-custody allowlist game w/ an hourly doomsday clock on Ethereum` = **82**
columns, against a current longest of 80 (`[2] Fake World Assets — …`) and a median of 58. Two
columns over the incumbent longest is inside "a few"; if you want it under, dropping
`Zero-custody ` gives 69. Either is defensible — the point is that it was measured.

---

## 5. What will check each surface

| surface | test |
|---|---|
| `GAMES` keys contiguous 1..N | **`tests/test_fwa_theme.py:490`**, inside `test_game_cli_choice_includes_fwa` (line 462) — the `keys == [str(i) for i in range(1, len(GAMES) + 1)]` block. *Not* a registration test, and its name gives no hint that it guards this. Do not duplicate it; reference it in a comment. |
| `GAMES` ↔ `_GAME_CYCLE` | `tests/test_surf_registration.py::test_the_menu_and_the_tab_cycle_offer_the_same_games_in_the_same_order` |
| `GAMES` ↔ `--game choices` | `tests/test_surf_registration.py::test_the_cli_choices_are_exactly_the_menu`, `tests/test_cli_game_choices.py::test_every_game_choice_is_offered_by_the_menu`, `::test_reachable_games_still_work` |
| every choice has a prefetch manager | `tests/test_app_startup.py::test_every_game_choice_has_a_prefetch_manager` — this is the one that catches a `--game` choice added without the `_prefetch_manager` entry |
| bare-app default | `tests/test_app_startup.py::test_a_bare_app_prefetches_the_dashboard_the_menu_opens_on` (compares `MaxPaneApp()._initial_game` to `GAMES[0][1]`; must stay green throughout) |
| `--game` default | `tests/test_surf_registration.py::test_the_default_game_is_the_first_menu_entry` |
| surf stays entry one | `tests/test_surf_registration.py::test_surf_is_menu_entry_one` (`SURF_ROW` pinned verbatim at key `"1"`) |
| prefetch failure is survivable | `tests/test_app_startup.py::test_failing_prefetch_does_not_kill_app` (parametrised over games) |
| README + CLAUDE.md rows | `tests/test_surf_registration.py::test_every_visible_dashboard_is_documented` — needs the literal `--game curator` **and** the display name `THE LIST` in README, and `` `curator` `` in CLAUDE.md |
| CLAUDE.md heading count | `tests/test_surf_registration.py::test_claude_md_counts_the_visible_dashboards` — derives the word from `len(GAMES)`, so it wants `## The eight visible dashboards` |
| README width table shape | `tests/test_surf_registration.py::_readme_width_bands()` parses it with a regex; read that parser before touching the table |
| curator ≤ app width | `tests/screens/test_curator_screen.py::test_curator_fits_inside_the_documented_app_width` (138 ≤ 143) |

---

## 6. The width decision: WP7.7 case one, nothing moves

`CURATOR_FULL_LAYOUT_COLUMNS` is **138** and this gate re-swept it independently rather than
reading the constant: column by column from 132 to 144, both `c` views, all three phases, at
**both** terminal heights (48 and 30), counting composited `‹ widen` markers over the whole
screen.

```
132  24 markers  [CuratorLeaderboard, CuratorSignals]
133  24          [CuratorLeaderboard, CuratorSignals]
134  12          [CuratorSignals]
135  12          [CuratorSignals]
136  12          [CuratorSignals]
137  12          [CuratorSignals]
138   0          []
```

138 is tight (137 is dirty) and it is the same at 30 rows as at 48 — the gutter fix holds.
**The binding panel is `CuratorSignals`**, the seven-row rail, and the reason is the YOU row: it
is the only row whose width is a function of the *reader's own* credit, and this sweep uses the
capture's rank-1 wallet (`490.90 credit` / `next ≥ 491.00 ETH`), which needs 84 content columns
against the 82 `widgets/curator/signals.SIGNALS_FULL_WIDTH` publishes. Not a defect; a
measurement note WP4 should have, and a reason not to trust the published constant as worst-case.

So: `__main__.FULL_LAYOUT_COLUMNS` stays **143**, the README's `≥ 143` line stays, and the
CLAUDE.md record `198 → 172 → 143 → 176 → 152 → 143` is **not** appended to. Add one sentence to
CLAUDE.md's width section: curator measures 138, five columns under FWA's 143, binding panel
`CuratorSignals`, and the number is height-independent because the rail reserves its scrollbar
gutter. Which dashboard binds is itself a measurement — do not restate it from an older
paragraph.

`WORST_CASE_TITLE_COLUMNS = 90`, swept separately at `RAIL_FULL_HEIGHT - 1` rows with all three
`SOURCES` degraded and `‹ taller` lit. It moves with `__version__`; the venv and
`pyproject.toml` both read 0.6.1, so WP7.11's `pip install -e .` will not disturb it.

---

## 7. What is still open

### Captures A, B, C — none of them exists yet

The newest bundle in `tests/fixtures/curator/captures/live/` is
`20260817T000322Z_grace-late.json` (2026-08-17 00:03:22Z). There is no `post-grace`, no
`judged-deficit` and no `settlement` bundle.

| capture | state it needs | status |
|---|---|---|
| **A** — quiet hour crossing | `currentHourTotal() == 0` while `lastActiveHour()` still names the previous hour | missed three times (21:58:47, 22:58:47, 23:58:47) — the game took a deposit within seconds of every boundary during grace. The closest fresh-hour reading so far is **7.07 ETH**. Retryable at every `HH:58:47Z`, and easier once grace ends. |
| **B** — post-grace | `earlyMultiplierBps() == 0x2710` exactly, `currentHour() >= 24` | window opens **2026-08-17 19:58:47 UTC** — has not happened as of this brief |
| **C** — settlement | last bundle with `isSettled() == 0x0` and first with `0x1`; one-shot, no transaction, no log | earliest **2026-08-17 20:58:47 UTC** |

A detached hunter is sweeping the crossings. WP7 does not chase these; WP7.13 reconciles
whatever has landed by then.

### The `# SYNTHETIC — re-point` ledger

`rg -c "SYNTHETIC — re-point" tests/` → **33** marked lines across 12 files (25 in `.py` test
modules, 8 in fixtures and their READMEs). Waves 3–4 added 15 to the 18 the wave-2 gate counted:

```
tests/analytics/test_curator_signals.py       8
tests/widgets/test_curator_widgets.py         7
tests/screens/test_curator_screen.py          4      (WP6: the judged and settled loaders)
tests/data/test_curator_manager.py            4
tests/data/test_curator_cache.py              1
tests/data/test_curator_client.py             1
tests/fixtures/curator/… (6 files)            8
```

Three of these are **permanent** synthetic by the ledger's own reasoning and should be marked as
such rather than waited on: the `HourSaved` row (needs a judged hour to cross the threshold from
below — may never fire), the `Rescued` row (needs a force-feed plus a deployer sweep), and a
`creditedDelta == 0` deposit (needs a single send above the 1000 ETH cap; the largest real one is
461.1 ETH).

### Findings from waves 3–4 that WP7 should carry

1. **`previewPoints(uint256)` is not wired.** PRD §5 names it as a once-tier probe;
   `CuratorClient` exposes no method for `SEL_PREVIEW_POINTS` and it is deliberately not in any
   ordered selector tuple, so the manager reads the nine immutables via `fetch_config()` and
   nothing else. The curve is not unproven — `captures/live/20260816T225143Z_curve-probe.json` is
   its onchain witness, 20/20 calls matching `(isqrt(w) * rate) // 1e9` — but the PRD claim is
   false as written. WP5 reported it rather than editing WP2's file; WP7.13's "every claim in the
   plan is true or struck" pass should strike it.
2. **`build_signals` defaults its six list keys to `[]`; the manager republishes four of them as
   `None`** when the logs read did not happen, because `[]` at the manager boundary asserts that
   nobody ever deposited. A seam decision, not a defect — and exactly the kind of thing a
   later "simplification" removes.
3. **`CuratorClosestCalls._empty_note` ellipsises without a `‹ widen`** (WP6 → WP4). The lost
   tail is `· hour N`, which is the fact the empty state exists to tell. Visible, not dark, so
   not a clipping bug — but report it forward, do not work around it in the stylesheet.
4. **WP6's mutation 4 did not bite on the first attempt.** The `c`-default test as `wp6.md`
   specified it drove the reader *with* the phase default and passed against a screen that
   re-applied the default on every refresh. It now also drives *against* it. Anyone copying that
   test shape to another dashboard should copy the second half.
5. **The offline-launch acceptance criterion is an all-`None` payload, not a raising manager.**
   `fetch_and_compute` never raises (`test_no_exception_escapes_when_every_call_raises`), so a
   raising double models a mis-wired manager rather than a dead RPC. WP7.11 should use the
   all-`None` payload — `tests/screens/test_curator_screen.py::_FakeManager`,
   `_all_none_payload()`, `_grace_payload()` / `_judged_payload()` / `_settled_payload()` are
   import-safe and reusable, with no network, no clock and no cache file.

---

## Verdict

**WP7 may start.** Suite green at 4241/0/0, tree clean, all six registration surfaces
untouched, the app-wide width constant does not move, and the one real trap — copying
`CuratorScreen.DEFAULT_CSS` into `minimal.tcss` verbatim — is documented above with the
one-line fix and the measurement that proves it.
