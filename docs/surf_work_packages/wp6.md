# WP6 — Registration + integration (sole owner of every shared file)

**Goal:** Wire the finished surf dashboard into the five surfaces that must agree (`GAMES`, `app.py`, `--game`, CLAUDE.md, README), prove it launches and degrades cleanly offline, and land the release-ready integration commits.

**Work-package numbering — quote this table, never memory.** WP6 is the package that triages a red suite it did not cause (Task WP6.1) and that reports ownership violations (Task WP6.1's `git diff --stat` gate), so a wrong map here routes exactly the escalation this WP exists to catch. The table below is quoted verbatim from `plan/wp5.md` lines 7–16, which publishes it as *"the single source — quote this table, never memory"* after earlier drafts of this plan set carried three mutually inconsistent numberings. If it ever disagrees with a sentence elsewhere in this document, the table wins:

| WP | Owns | What this WP hands to WP5 |
|---|---|---|
| WP0 | `data/surf_addresses.py`, `data/surf_models.py`, `tests/fixtures/surf/**` | `SURF_KEYS`, the seven model dataclasses, the committed captures |
| WP1 | `data/surf_client.py` | (nothing directly — WP5 never imports the client) |
| WP2 | `analytics/surf_signals.py` | (nothing directly — signals reach WP5 through the manager payload) |
| WP3 | `maxpane_dashboard/widgets/surf/**` | the six widget classes, their `update_data` kwargs and their rendered copy |
| WP4 | `data/surf_cache.py`, `data/surf_manager.py` | `SurfManager.fetch_and_compute()` / `close()` |
| **WP5** | **`screens/surf.py`, `tests/screens/test_surf_screen.py`** | — (that document) |
| WP6 | `app.py`, `screens/game_select.py`, `__main__.py`, `themes/minimal.tcss`, `CLAUDE.md`, `README.md`, `pyproject.toml` | registration; consumes WP5's hand-off note |

One refinement the WP5 table compresses: the **root** of `tests/fixtures/surf/` is WP0's alone (two WP0 tests glob it non-recursively and fail on any extra file), while WP2 owns the one file under `tests/fixtures/surf/signals/`.

**Dependencies:** WP0 (`data/surf_addresses.py`; `data/surf_models.py` → `SURF_KEYS`), WP1 (`data/surf_client.py`), WP2 (`analytics/surf_signals.py` + its fixture), WP3 (`widgets/surf/` → `SurfHero`, `SurfSignals`, `SurfFeed`, `SurfDevActivity`, `SurfMarket`, `SurfNft`), WP4 (`data/surf_cache.py`; `data/surf_manager.py` → `SurfManager`, `SOURCES`), WP5 (`screens/surf.py` → `SurfScreen`, `SURF_FULL_LAYOUT_COLUMNS`, plus its WP6 hand-off note). **WP6 runs last; nothing runs in parallel with it.**

**Owner note — the exclusive-ownership list.** These files have exactly one owner in this plan and that owner is WP6. No other work package may open them for writing, and WP6 may not write anything outside this list:

| File | What WP6 does to it |
|---|---|
| `maxpane_dashboard/app.py` | manager + screen imports, `self._surf_manager`, `_prefetch_manager` map entry, `_launch_game` branch, `_GAME_CYCLE`, `action_quit` close |
| `maxpane_dashboard/screens/game_select.py` | one `GAMES` row, key `"7"` |
| `maxpane_dashboard/__main__.py` | `--game` choices (**default stays `fwa`**); `FULL_LAYOUT_COLUMNS` only if WP5 measured wider than 143 |
| `maxpane_dashboard/themes/minimal.tcss` | the surf structural block WP5 flagged in its hand-off |
| `CLAUDE.md` | dashboard table row 7 + the "six visible dashboards" heading |
| `README.md` | dashboards table, usage block, width note, version example |
| `pyproject.toml` | version bump |
| `tests/test_surf_registration.py` (new) | every assertion WP6 adds |
| `tests/test_app_startup.py`, `tests/test_game_select_quit.py` | the two hardcoded `MANAGER_ATTRS` / `ALL_GAMES` lists |

`maxpane_dashboard/themes/__init__.py` and the `--theme` choices are **out of scope**: PRD §10 leaves a dedicated `surf` theme off the critical path, so `THEME_NAMES` stays at ten and `tests/test_fwa_theme.py::test_theme_cli_choices_match_theme_names` must stay green untouched.

**Interface assumptions — verify in Task WP6.1 before editing anything.** If one of these is false, stop and report it; do not reshape `app.py` around a different signature.

- `maxpane_dashboard.data.surf_manager.SurfManager(poll_interval: int = 30)` constructs without touching the network (house pattern: `httpx.AsyncClient` is built, no request is issued) — **WP4**.
- `await SurfManager.fetch_and_compute() -> dict` and `await SurfManager.close()` exist — **WP4**.
- `maxpane_dashboard.screens.surf.SurfScreen(data_manager, poll_interval: int = 30, name: str = "surf", **kwargs)` (WP5, Task WP5.1).
- `maxpane_dashboard.data.surf_models.SURF_KEYS: tuple[str, ...]` is the exact PRD §5 key list — **WP0**. Every registration assertion in this WP is derived from it, so WP0 is a hard prerequisite even though WP6 never imports anything else of WP0's.
- `maxpane_dashboard.screens.surf.SURF_FULL_LAYOUT_COLUMNS: int` is pinned and measured (WP5, Task WP5.5).

**The frozen menu row.** Chosen once, here, and asserted verbatim by a test so nobody re-words it later:

```python
("7", "surf", "Mission Control", "surfsurf.eth announce channel + launch detectors on Ethereum")
```

"Mission Control" is the PRD §1 name for the subject; the id is `surf` per the frozen module surface.

---

## Why the edits are sequenced app.py → `__main__.py` → `GAMES` (and not the other way round)

Three existing test files derive their expectations from `GAMES` and go red the instant a game appears there without the rest of the wiring:

| Test | Derivation | Goes red if `GAMES` grows first |
|---|---|---|
| `tests/test_cli_game_choices.py::test_reachable_games_still_work` | `for _key, game, *_rest in GAMES` → runs the real parser | yes — `--game surf` exits 2 |
| `tests/test_cli_game_choices.py::test_every_game_choice_is_offered_by_the_menu` | `visible = {…GAMES…}` | yes — same |
| `tests/test_app_startup.py::test_every_game_choice_has_a_prefetch_manager` | `for _key, game_id, *_ in GAMES` | yes — `_prefetch_manager("surf")` is `None` |

Adding the manager and the screen branch first, then the CLI choice, then the menu row means **every commit in this WP leaves the suite green**, and the three tests above flip from red to green by themselves at Task WP6.5 — which is the point of deriving them from `GAMES` rather than hardcoding ids.

### Registration tests expected to pass unchanged (and why)

| File | Why it needs no edit |
|---|---|
| `tests/test_cli_game_choices.py` | every assertion is derived from `GAMES`; `UNREACHABLE_GAMES` names only the three FrenPet variants, which surf does not touch |
| `tests/test_fwa_theme.py::test_game_cli_choice_includes_fwa` | asserts on the *id* `fwa` and on hotkey contiguity `1..N` — `N` is `len(GAMES)`, so key `"7"` keeps it green |
| `tests/test_fwa_theme.py::test_theme_cli_choices_match_theme_names` | no theme is added |
| `tests/screens/test_refresh_guard.py::test_every_polling_screen_uses_the_guard` | discovers screens with `pkgutil.iter_modules`; `SurfScreen` already satisfies it (WP5 Task WP5.6) and the `>= 12` floor only rises |
| `tests/test_cli_font_size.py::test_the_documented_width_matches_the_layout` | renders **FWA**, not surf; only Task WP6.7 can disturb it, and that task re-runs it |
| `tests/screens/test_surf_screen.py` (WP5) | WP6 adds no screen behaviour; its `test_surf_fits_inside_the_documented_app_width` is the one that Task WP6.7 turns green |

Two files **do** need editing because their lists are hardcoded rather than derived — `tests/test_app_startup.py` (`ALL_GAMES`, `MANAGER_ATTRS`) and `tests/test_game_select_quit.py` (`MANAGER_ATTRS`). Both are handled in Task WP6.2.

---

### Task WP6.1: Pre-flight — verify WP0–WP5 landed, record the baseline

**Files:**
- Create: none · Modify: none · Test: none (this task exists so the later ones can be trusted)

**Interfaces:**
- Consumes: everything in the assumption list above.
- Produces: three recorded numbers used by later tasks — the baseline test count, `SURF_FULL_LAYOUT_COLUMNS`, and confirmation that no earlier WP touched a shared file.

**Steps:**

- [ ] Read WP5's ownership table (`plan/wp5.md` lines 7–16 — the same one quoted at the top of this document) and its hand-off section (`plan/wp5.md`, "WP6 hand-off summary"), then CLAUDE.md's "Hiding a dashboard touches five surfaces and they must agree" paragraph. The three hand-off items are Tasks WP6.6, WP6.7 and WP6.5 below. **Route any question about a module by that table, not by memory** — WP0 owns `surf_addresses.py` + `surf_models.py`, WP1 the client, WP2 the signals, WP3 the widgets, WP4 the cache + manager, WP5 the screen.

- [ ] Confirm every interface assumption mechanically:

```bash
cd /Library/Vibes/autopull && .venv/bin/python - <<'EOF'
import inspect
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data.surf_models import SURF_KEYS
from maxpane_dashboard.screens.surf import SurfScreen, SURF_FULL_LAYOUT_COLUMNS

m = SurfManager(poll_interval=30)          # must not touch the network
assert inspect.iscoroutinefunction(m.fetch_and_compute)
assert inspect.iscoroutinefunction(m.close)
sig = inspect.signature(SurfScreen.__init__)
assert list(sig.parameters)[:4] == ["self", "data_manager", "poll_interval", "name"], sig
print("SURF_KEYS:", len(SURF_KEYS))
print("SURF_FULL_LAYOUT_COLUMNS:", SURF_FULL_LAYOUT_COLUMNS)
EOF
```

  Expected: no exception, a key count matching PRD §5, and a printed width. **Record the width** — Task WP6.7 branches on whether it exceeds 143.

- [ ] Confirm no shared file has been touched by an earlier WP (they were told not to; verify rather than trust):

```bash
cd /Library/Vibes/autopull && git diff --stat main...HEAD -- maxpane_dashboard/app.py maxpane_dashboard/__main__.py maxpane_dashboard/screens/game_select.py maxpane_dashboard/themes/minimal.tcss CLAUDE.md README.md
```

  Expected: **empty output**. Any file listed here means two owners edited it — stop and report before continuing. Name the offending WP from the quoted ownership table above (`plan/wp5.md` lines 7–16), not from the numbering in any other prose: an escalation sent to the wrong owner is worse than none.

- [ ] Record the baseline suite result:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest -q 2>&1 | tail -3
```

  Expected: all passed, with a count noticeably above the pre-surf ~2100 (WP0–WP5 added their own suites). Write the number down; Task WP6.12 compares against it. If anything is red *before* WP6 edits a line, fix ownership attribution first — WP6 must not inherit another WP's failure. Map the failing path to its owner with the quoted table: `data/surf_addresses.py` / `data/surf_models.py` → WP0, `data/surf_client.py` → WP1, `analytics/surf_signals.py` → WP2, `widgets/surf/` → WP3, `data/surf_cache.py` / `data/surf_manager.py` → WP4, `screens/surf.py` → WP5.

- [ ] No commit for this task.

---

### Task WP6.2: `app.py` — build the manager, prefetch it, close it on quit

**Files:**
- Modify: `maxpane_dashboard/app.py`
- Modify: `tests/test_app_startup.py`, `tests/test_game_select_quit.py`
- Test: `tests/test_surf_registration.py` (create)

**Interfaces:**
- Consumes: `maxpane_dashboard.data.surf_manager.SurfManager(poll_interval: int = 30)`, `await .fetch_and_compute()`, `await .close()`.
- Produces: `MaxPaneApp._surf_manager: SurfManager`; `MaxPaneApp._prefetch_manager("surf") -> SurfManager`; `action_quit` awaits `self._surf_manager.close()`.

**Steps:**

- [ ] Write the failing test. Create `tests/test_surf_registration.py`:

```python
"""WP6: the surf dashboard is registered on every surface that must agree.

CLAUDE.md's "Hiding a dashboard touches five surfaces and they must agree"
note applies in reverse to *adding* one: ``GAMES`` in
``screens/game_select.py``, the manager/screen wiring and ``_GAME_CYCLE`` in
``app.py``, the ``--game`` choices in ``__main__.py``, the CLAUDE.md dashboard
table and the README.  A dashboard registered on four of the five is worse
than one registered on none: it half-works.

Every assertion below is derived from ``GAMES`` wherever it can be, so a later
hide, show or reorder *moves* these tests instead of breaking them -- the
mistake the hardcoded ``bakery`` assertions made before they were rewritten.

Zero network: managers are replaced by stubs before ``run_test()``, and the CLI
is driven with ``MaxPaneApp`` swapped for a recorder, exactly the way
``tests/test_cli_game_choices.py`` and ``tests/test_app_startup.py`` do it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.game_select import GAMES, GameSelectScreen

REPO = Path(__file__).resolve().parents[1]

#: The one menu row this WP adds, asserted verbatim so the copy cannot drift.
SURF_ROW = (
    "7",
    "surf",
    "Mission Control",
    "surfsurf.eth announce channel + launch detectors on Ethereum",
)

#: Attribute names of every manager ``MaxPaneApp.__init__`` builds.  Hardcoded
#: on purpose: the failure this guards is a manager that was *never built*, and
#: a list derived from the app could not see that.
MANAGER_ATTRS = [
    "_bakery_manager",
    "_frenpet_manager",
    "_frenpet_full_manager",
    "_frenpet_wallet_manager",
    "_frenpet_perf_manager",
    "_base_manager",
    "_cattown_manager",
    "_ocm_manager",
    "_dota_manager",
    "_ttt_manager",
    "_talismans_manager",
    "_fwa_manager",
    "_surf_manager",
]


class CountingManager:
    """Manager that records fetches and closes.  Never touches the network."""

    def __init__(self) -> None:
        self._error_count = 0
        self.calls = 0
        self.closed = 0

    async def fetch_and_compute(self) -> dict[str, Any]:
        self.calls += 1
        return {}

    async def close(self) -> None:
        self.closed += 1


def _stubbed_app(initial_game: str = "base") -> tuple[MaxPaneApp, dict[str, CountingManager]]:
    """The real app with every manager replaced by a stub."""
    app = MaxPaneApp(initial_game=initial_game)
    stubs: dict[str, CountingManager] = {}
    for attr in MANAGER_ATTRS:
        stub = CountingManager()
        stubs[attr] = stub
        setattr(app, attr, stub)
    return app, stubs


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see.

    Reaching into the compositor is the only way to prove a line is *on
    screen* rather than merely present in a widget's content.
    """
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


# ---------------------------------------------------------------------------
# app.py: the manager
# ---------------------------------------------------------------------------


def test_every_manager_attribute_exists_on_a_fresh_app() -> None:
    """``__init__`` builds every manager, surf included."""
    app = MaxPaneApp()
    for attr in MANAGER_ATTRS:
        assert getattr(app, attr, None) is not None, f"{attr} was never built"


def test_surf_manager_takes_the_poll_interval() -> None:
    """The app hands its poll interval to SurfManager like every other game."""
    from maxpane_dashboard.data.surf_manager import SurfManager

    app = MaxPaneApp(poll_interval=45)
    assert isinstance(app._surf_manager, SurfManager)


def test_surf_has_a_prefetch_manager() -> None:
    """No --game choice may fall through the prefetch map silently."""
    app = MaxPaneApp()
    assert app._prefetch_manager("surf") is app._surf_manager


def test_quit_closes_the_surf_manager() -> None:
    """``q`` must await ``SurfManager.close()`` -- cache saved, client closed.

    Goes through the menu quit path (``space`` dismisses the splash, ``q`` on
    the menu bubbles to the app binding), which is the path LOW-19 fixed and
    the one a user reaches with ``m`` then ``q``.
    """

    async def _run() -> None:
        app, stubs = _stubbed_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press("q")
            await pilot.pause()

        assert stubs["_surf_manager"].closed == 1, (
            "SurfManager.close() ran "
            f"{stubs['_surf_manager'].closed} times on quit; the surf cache is "
            "not persisted and its httpx client is abandoned"
        )
        for attr, stub in stubs.items():
            assert stub.closed == 1, f"{attr} closed {stub.closed} times"
        assert app._exception is None

    asyncio.run(_run())
```

- [ ] Run it and observe the failure:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -v
```

  Expected: 4 failed. `test_every_manager_attribute_exists_on_a_fresh_app` → `AssertionError: _surf_manager was never built`; `test_surf_manager_takes_the_poll_interval` → `AttributeError: 'MaxPaneApp' object has no attribute '_surf_manager'`; `test_surf_has_a_prefetch_manager` → the same `AttributeError`; `test_quit_closes_the_surf_manager` → `closed == 0` (the stub was attached by `setattr` but `action_quit` never mentions it).

- [ ] Extend the two hardcoded lists in the existing startup tests so their coverage grows with the app. In `tests/test_app_startup.py`, append `"surf"` to `ALL_GAMES` and `"_surf_manager"` to `MANAGER_ATTRS`:

```python
#: Every ``--game`` choice, including the ones hidden from the select screen.
ALL_GAMES = [
    "bakery",
    "frenpet",
    "frenpet_full",
    "frenpet_wallet",
    "frenpet_perf",
    "base",
    "cattown",
    "ocm",
    "dota",
    "ttt",
    "talismans",
    "fwa",
    "surf",
]

#: Attribute names of every manager the app builds in ``__init__``.
MANAGER_ATTRS = [
    "_bakery_manager",
    "_frenpet_manager",
    "_frenpet_full_manager",
    "_frenpet_wallet_manager",
    "_frenpet_perf_manager",
    "_base_manager",
    "_cattown_manager",
    "_ocm_manager",
    "_dota_manager",
    "_ttt_manager",
    "_talismans_manager",
    "_fwa_manager",
    "_surf_manager",
]
```

  In `tests/test_game_select_quit.py`, append `"_surf_manager"` to its own `MANAGER_ATTRS` (same 13-entry list). Both files then fail too — `test_failing_prefetch_does_not_kill_app[surf]` asserts `isinstance(app._prefetch_manager("surf"), BoomManager)` and gets `None`, and the quit tests find an unstubbed real manager. That is the intended red.

- [ ] Implement, minimally, in `maxpane_dashboard/app.py`. Four edits, each at an exact anchor:

```python
# 1. manager import, keeping the block alphabetical (ocm < surf < talismans)
from maxpane_dashboard.data.ocm_manager import OCMManager
from maxpane_dashboard.data.surf_manager import SurfManager
from maxpane_dashboard.data.talismans_manager import TalismansManager
```

```python
# 2. __init__, immediately after the talismans manager and before the
#    FWAManager comment block
        self._talismans_manager = TalismansManager(poll_interval=poll_interval)
        self._surf_manager = SurfManager(poll_interval=poll_interval)
```

```python
# 3. the prefetch map
            "talismans": self._talismans_manager,
            "surf": self._surf_manager,
            "fwa": self._fwa_manager,
        }.get(game_id)
```

```python
# 4. action_quit, immediately before self.exit()
        try:
            await self._surf_manager.close()
        except Exception as exc:
            logger.warning("Error during surf shutdown: %s", exc)
        self.exit()
```

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py tests/test_app_startup.py tests/test_game_select_quit.py -v
```

  Expected: all green, including the new `test_failing_prefetch_does_not_kill_app[surf]` — the prefetch path never installs a screen, so it does not need the `_launch_game` branch that lands in the next task. Any remaining failure here is a real defect, not sequencing.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/app.py tests/test_surf_registration.py tests/test_app_startup.py tests/test_game_select_quit.py && git commit -m "feat(surf): build, prefetch and gracefully close the surf manager"
```

---

### Task WP6.3: `app.py` — install `SurfScreen` and put surf in the tab cycle

**Files:**
- Modify: `maxpane_dashboard/app.py`
- Test: `tests/test_surf_registration.py` (append)

**Interfaces:**
- Consumes: `maxpane_dashboard.screens.surf.SurfScreen(data_manager, poll_interval, name="surf")`.
- Produces: `MaxPaneApp._launch_game("surf")` installs and shows the screen named `"surf"`; `MaxPaneApp._GAME_CYCLE` ends with `"surf"`.

**Steps:**

- [ ] Write the failing test (append to `tests/test_surf_registration.py`):

```python
# ---------------------------------------------------------------------------
# app.py: the screen and the tab cycle
# ---------------------------------------------------------------------------


def test_launching_surf_installs_the_surf_screen() -> None:
    """``_launch_game('surf')`` must reach a SurfScreen, not the else-return.

    Driven through ``_launch_game`` rather than the menu because the menu row
    lands two tasks later; the branch is what is under test here.
    """
    from maxpane_dashboard.screens.surf import SurfScreen

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game("surf", first=True)
            await pilot.pause()

            assert isinstance(app.screen, SurfScreen), (
                f"_launch_game('surf') left {type(app.screen).__name__} on "
                "screen -- the branch is missing and it hit `else: return`"
            )
            assert app.screen.name == "surf"
            assert app.is_screen_installed("surf")
            assert app._exception is None

    asyncio.run(_run())


def test_launching_surf_twice_reuses_one_installed_screen() -> None:
    """The install is guarded, so ``m`` -> surf -> ``m`` -> surf leaks nothing."""

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game("surf", first=True)
            await pilot.pause()
            installed = len(app._installed_screens)
            for _ in range(5):
                app._launch_game("surf")
                await pilot.pause()
            assert len(app._installed_screens) == installed
            assert app._exception is None

    asyncio.run(_run())


def test_surf_is_in_the_tab_cycle_exactly_once() -> None:
    """Tab must reach surf, and must not visit it twice per lap."""
    assert MaxPaneApp._GAME_CYCLE.count("surf") == 1, MaxPaneApp._GAME_CYCLE


def test_tab_from_the_previous_game_reaches_surf() -> None:
    """The cycle is walked for real, not re-declared.

    ``_launch_game`` is replaced by a recorder so no second dashboard mounts
    (which would start a real poll timer).
    """
    cycle = MaxPaneApp._GAME_CYCLE
    previous = cycle[cycle.index("surf") - 1]

    async def _run() -> None:
        app, _stubs = _stubbed_app(previous)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game(previous, first=True)
            await pilot.pause()
            app._current_game = previous

            launched: list[str] = []
            app._launch_game = lambda game_id, **kw: launched.append(game_id)

            await pilot.press("tab")
            await pilot.pause()

            assert launched == ["surf"], (
                f"tab from {previous} went to {launched} instead of surf"
            )
            assert app._current_game == "surf"

    asyncio.run(_run())
```

- [ ] Run and observe the failure:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -k "surf_screen or tab_cycle or reaches_surf or reuses_one" -v
```

  Expected: 4 failed. `test_launching_surf_installs_the_surf_screen` → `AssertionError: _launch_game('surf') left SplashScreen on screen -- the branch is missing and it hit 'else: return'`; `test_surf_is_in_the_tab_cycle_exactly_once` → `0 != 1`; `test_tab_from_the_previous_game_reaches_surf` → `ValueError: 'surf' is not in list` at `cycle.index("surf")`.

- [ ] Implement in `maxpane_dashboard/app.py`. Three edits:

```python
# 1. screen import, alphabetical (splash < surf < talismans)
from maxpane_dashboard.screens.splash import SplashScreen
from maxpane_dashboard.screens.surf import SurfScreen
from maxpane_dashboard.screens.talismans import TalismansScreen
```

```python
# 2. _GAME_CYCLE -- same order as GAMES, surf appended last
    _GAME_CYCLE = ["fwa", "base", "frenpet", "cattown", "ttt", "talismans", "surf"]
```

```python
# 3. _launch_game, inserted after the "fwa" branch and before `else: return`
        elif game_id == "surf":
            if not self.is_screen_installed("surf"):
                self.install_screen(
                    SurfScreen(
                        self._surf_manager,
                        self.poll_interval,
                        name="surf",
                    ),
                    name="surf",
                )
        else:
            return
```

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py tests/test_app_startup.py -v
```

  Expected: all green, including `test_tab_does_not_cycle_games_off_a_dashboard` (unchanged) and the parametrized `[surf]` prefetch case.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/app.py tests/test_surf_registration.py && git commit -m "feat(surf): install SurfScreen and add surf to the tab cycle"
```

---

### Task WP6.4: `__main__.py` — accept `--game surf`, keep `fwa` as the default

**Files:**
- Modify: `maxpane_dashboard/__main__.py`
- Test: `tests/test_surf_registration.py` (append)

**Interfaces:**
- Consumes: `MaxPaneApp(initial_game=...)` (already wired).
- Produces: `--game surf` parses and reaches `MaxPaneApp(initial_game="surf")`; `--game` default remains `"fwa"`.

**Steps:**

- [ ] Write the failing test (append). The CLI runner is a local copy of the one in `tests/test_cli_game_choices.py` on purpose — `tests/test_fwa_theme.py` keeps its own for the same reason: a shared import would couple two registration suites that must be able to fail independently.

```python
# ---------------------------------------------------------------------------
# __main__.py: the --game choice
# ---------------------------------------------------------------------------


def _run_cli(monkeypatch, argv: list[str]) -> dict:
    """Invoke ``__main__.main()`` with *argv*, returning the app's kwargs.

    No TUI is started, no terminal is resized, and ``logging.basicConfig`` is
    neutered so a test run never truncates ``~/.maxpane/maxpane.log``.
    """
    import maxpane_dashboard.__main__ as cli

    captured: dict = {}

    class _StubApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(cli, "_maximize_terminal", lambda *a, **k: None)
    monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
    monkeypatch.setattr(cli.sys, "argv", ["maxpane", *argv])
    cli.main()
    return captured


def test_game_surf_is_accepted(monkeypatch) -> None:
    captured = _run_cli(monkeypatch, ["--game", "surf"])
    assert captured["initial_game"] == "surf"
    assert captured.get("ran") is True


def test_the_default_game_is_still_fwa(monkeypatch) -> None:
    """CLAUDE.md pins fwa as position 1 *and* the ``--game`` default.

    Adding a dashboard must never move it: hiding or displacing the default
    silently breaks launch, which is why this assertion sits next to the one
    that adds surf.
    """
    captured = _run_cli(monkeypatch, [])
    assert captured["initial_game"] == "fwa"


def test_a_typo_is_still_rejected(monkeypatch) -> None:
    """The choices list stays a whitelist -- ``--game surfs`` must exit 2."""
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--game", "surfs"])
```

- [ ] Run and observe the failure:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -k "game_surf_is_accepted or default_game or typo" -v
```

  Expected: 1 failed, 2 passed. `test_game_surf_is_accepted` → `SystemExit: 2` from argparse (`error: argument --game: invalid choice: 'surf'`).

- [ ] Implement in `maxpane_dashboard/__main__.py`:

```python
    parser.add_argument(
        "--game",
        default="fwa",
        choices=["fwa", "base", "frenpet", "cattown", "ttt", "talismans", "surf"],
```

  `default="fwa"` is deliberately left alone — CLAUDE.md's "check `default=` every time" cuts both ways.

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py tests/test_cli_game_choices.py -v
```

  Expected: all green. `test_every_game_choice_is_offered_by_the_menu` still passes because it only checks menu → CLI, and surf is not on the menu yet; the reverse direction is asserted in the next task.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/__main__.py tests/test_surf_registration.py && git commit -m "feat(surf): accept --game surf (default stays fwa)"
```

---

### Task WP6.5: `screens/game_select.py` — the menu row, key `7`

**Files:**
- Modify: `maxpane_dashboard/screens/game_select.py`
- Test: `tests/test_surf_registration.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `GAMES` row `("7", "surf", "Mission Control", "surfsurf.eth announce channel + launch detectors on Ethereum")`; pressing `7` on the menu dismisses with `"surf"`.

**Steps:**

- [ ] Write the failing test (append):

```python
# ---------------------------------------------------------------------------
# game_select.py: the menu row -- the surface a user actually presses
# ---------------------------------------------------------------------------


def test_surf_is_menu_entry_seven() -> None:
    """The row is asserted verbatim so the copy cannot drift silently."""
    row = next((g for g in GAMES if g[1] == "surf"), None)
    assert row is not None, "surf is not registered in GAMES"
    assert tuple(row) == SURF_ROW, f"menu row drifted: {row}"


def test_the_menu_and_the_tab_cycle_offer_the_same_games_in_the_same_order() -> None:
    """Two orderings of one list are one bug waiting to happen.

    ``_GAME_CYCLE`` and ``GAMES`` are separate literals in separate files;
    this is the assertion that keeps them in step, and it is derived from
    both rather than restating either.
    """
    assert MaxPaneApp._GAME_CYCLE == [game_id for _key, game_id, *_ in GAMES]


def test_the_cli_choices_are_exactly_the_menu(monkeypatch) -> None:
    """CLI -> menu, the direction ``test_cli_game_choices`` does not assert.

    It checks that every menu entry is an accepted choice; this checks that
    every accepted choice is a menu entry, in order.  Together they pin the
    two lists to each other.
    """
    import argparse

    seen: dict[str, list[str]] = {}
    real_add_argument = argparse.ArgumentParser.add_argument

    def spy(self, *args, **kwargs):
        if args and args[0] == "--game":
            seen["choices"] = list(kwargs.get("choices") or [])
        return real_add_argument(self, *args, **kwargs)

    monkeypatch.setattr(argparse.ArgumentParser, "add_argument", spy)
    _run_cli(monkeypatch, [])

    assert seen["choices"] == [game_id for _key, game_id, *_ in GAMES]


def test_pressing_seven_opens_the_surf_dashboard() -> None:
    """The whole path: splash -> menu -> the key the row advertises.

    The key is read out of ``GAMES`` rather than typed as "7", so a future
    reorder moves this test with the menu instead of breaking it.
    """
    from maxpane_dashboard.screens.surf import SurfScreen

    key = next(k for k, game_id, *_ in GAMES if game_id == "surf")

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press(key)
            await pilot.pause()

            assert isinstance(app.screen, SurfScreen)
            assert app.screen.name == "surf"
            assert app._exception is None
        assert app.return_code != 1

    asyncio.run(_run())


def test_the_menu_lists_the_surf_row() -> None:
    """The row reaches the compositor -- not merely the GAMES list."""

    async def _run() -> None:
        app, _stubs = _stubbed_app("surf")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            text = _screen_text(app)
            assert "[7]" in text
            assert SURF_ROW[2] in text          # Mission Control
            assert "announce channel" in text   # from the description

    asyncio.run(_run())
```

- [ ] Run and observe the failure:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -k "menu or cli_choices or pressing_seven" -v
```

  Expected: 5 failed. `test_surf_is_menu_entry_seven` → `AssertionError: surf is not registered in GAMES`; `test_the_menu_and_the_tab_cycle_offer_the_same_games_in_the_same_order` → the cycle has a trailing `surf` the menu lacks; `test_the_cli_choices_are_exactly_the_menu` → same shape; `test_pressing_seven_opens_the_surf_dashboard` → still on `GameSelectScreen` (key 7 is unbound); `test_the_menu_lists_the_surf_row` → `"[7]" not in text`.

- [ ] Implement in `maxpane_dashboard/screens/game_select.py` — one row appended, keys stay contiguous `1..7`:

```python
    ("5", "ttt", "Ten Thousand Tokens", "NFT collection w/ UniV4 burn-to-launch on Ethereum"),
    ("6", "talismans", "Talismans", "Core-conservation NFT collection on Ethereum"),
    ("7", "surf", "Mission Control", "surfsurf.eth announce channel + launch detectors on Ethereum"),
]
```

- [ ] Run to green — this is the moment the three auto-extending suites pick surf up on their own:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py tests/test_cli_game_choices.py tests/test_fwa_theme.py tests/test_app_startup.py tests/test_game_select_quit.py -v
```

  Expected: all green, specifically including `test_reachable_games_still_work` (now runs `--game surf`), `test_every_game_choice_is_offered_by_the_menu`, `test_every_game_choice_has_a_prefetch_manager` and `test_game_cli_choice_includes_fwa`'s contiguity assertion (`keys == ["1".."7"]`).

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/screens/game_select.py tests/test_surf_registration.py && git commit -m "feat(surf): add Mission Control as game-select entry 7"
```

---

### Task WP6.6: `themes/minimal.tcss` — the surf structural block (WP5 hand-off item 1)

**Files:**
- Modify: `maxpane_dashboard/themes/minimal.tcss`
- Test: `tests/test_surf_registration.py` (append)

**Interfaces:**
- Consumes: `SurfScreen.DEFAULT_CSS` (WP5 Task WP5.1) — the block restates it; `SURF_FULL_LAYOUT_COLUMNS`.
- Produces: a `/* ── Surf screen ── */` block in the shared stylesheet whose rules match `DEFAULT_CSS` and add **no vertical padding** to `#hero-row`.

**Why this is not optional.** An app stylesheet always outranks `DEFAULT_CSS` in Textual. `minimal.tcss` already defines `#title-bar`, `#middle-row`, `#separator` and `#bottom-row` globally (lines 12–130), so those four ids come from this file for *every* screen — surf included — regardless of what `SurfScreen.DEFAULT_CSS` says. `#hero-row` and the six surf widget types have no global rules today, which is why WP5's tests pass without this block; the block exists so the screen is stable under all ten themes and so a later edit to the shared ids cannot silently reshape surf.

**Steps:**

- [ ] Write the failing test (append):

```python
# ---------------------------------------------------------------------------
# themes/minimal.tcss: the shared stylesheet must know about surf
# ---------------------------------------------------------------------------

_TCSS = REPO / "maxpane_dashboard" / "themes" / "minimal.tcss"


def _surf_block() -> str:
    """The surf section of the shared stylesheet, or '' if absent."""
    text = _TCSS.read_text(encoding="utf-8")
    marker = "/* ── Surf screen"
    if marker not in text:
        return ""
    start = text.index(marker)
    nxt = text.find("/* ── ", start + len(marker))
    return text[start:] if nxt == -1 else text[start:nxt]


def test_the_shared_stylesheet_has_a_surf_block() -> None:
    """DEFAULT_CSS is a fallback; the app stylesheet is what actually renders."""
    block = _surf_block()
    assert block, (
        "themes/minimal.tcss has no surf block -- SurfScreen's proportions "
        "come from DEFAULT_CSS only, which any theme edit to the shared ids "
        "(#middle-row, #bottom-row, #separator) can silently override"
    )
    for selector in (
        "SurfScreen #hero-row",
        "SurfHero",
        "SurfSignals",
        "SurfFeed",
        "SurfDevActivity",
        "SurfMarket",
        "SurfNft",
    ):
        assert selector in block, f"{selector} is not styled in the surf block"


def test_the_surf_hero_row_has_no_vertical_padding() -> None:
    """The FWA coverage-badge lesson, applied before it can bite.

    ``#hero-row`` is ten rows and SurfSignals fills them with a title plus six
    detector rows inside a border.  A vertical pad here clips the sixth row --
    the BURN detector -- exactly the way ``padding: 1 2`` clipped the FWA
    coverage badge.  Horizontal padding (``0 1``, ``0 2``) is fine.
    """
    import re

    block = _surf_block()
    hero = re.search(r"SurfScreen #hero-row\s*\{([^}]*)\}", block)
    assert hero, "no SurfScreen #hero-row rule in the surf block"
    for line in hero.group(1).splitlines():
        line = line.strip()
        if line.startswith("padding:"):
            vertical = line.split(":", 1)[1].strip().rstrip(";").split()[0]
            assert vertical == "0", (
                f"vertical padding {vertical!r} on #hero-row will clip the "
                "sixth detector row"
            )


def test_all_six_detectors_survive_the_real_stylesheet() -> None:
    """Composited proof, under ``minimal.tcss``, at the pinned width.

    This is a regression guard rather than the driver for the block: it also
    passes with DEFAULT_CSS alone today.  It is what turns red if a future
    theme edit -- or a "tidy" of the block above -- costs the screen a row.
    """
    import importlib.util

    from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS

    path = REPO / "tests" / "screens" / "test_surf_screen.py"
    spec = importlib.util.spec_from_file_location("_surf_screen_harness", path)
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    async def _run() -> None:
        screen = harness.SurfScreen(
            harness._FakeManager(), poll_interval=30, name="surf"
        )
        app = harness._ThemedHarness(screen)
        async with app.run_test(size=(SURF_FULL_LAYOUT_COLUMNS, 48)) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.pause()
            text = harness._screen_text(app)
            for label in (
                "NEW POST",
                "LP MIGRATION",
                "GATE OPEN",
                "NEW DEPLOY",
                "BRIDGE STAGE",
                "BURN",
            ):
                assert label in text, f"{label} never reached the compositor"

    asyncio.run(_run())
```

- [ ] Run and observe the failure:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -k "stylesheet or hero_row or six_detectors" -v
```

  Expected: 2 failed, 1 passed. `test_the_shared_stylesheet_has_a_surf_block` → the assertion message above; `test_the_surf_hero_row_has_no_vertical_padding` → `AssertionError: no SurfScreen #hero-row rule in the surf block`. `test_all_six_detectors_survive_the_real_stylesheet` passes already — stated up front so a green result is not mistaken for the block existing.

- [ ] Implement: append to `maxpane_dashboard/themes/minimal.tcss`, after the FWA block, verbatim:

```css

/* ── Surf screen ──────────────────────────────────────────────────────── */

/* Structure only, restating SurfScreen.DEFAULT_CSS. An app stylesheet always
 * outranks DEFAULT_CSS in Textual, so anything this block leaves out is not
 * "inherited from the screen" -- it is whatever this file already says for the
 * shared ids (#title-bar, #middle-row, #separator, #bottom-row, lines 12-130).
 * Same reasoning, and same failure mode, as the FWA block above.
 *
 * The id rules are scoped to `SurfScreen` on purpose. `#hero-row` is unused
 * elsewhere today, and an unscoped rule for it would silently become law for
 * the next dashboard that picks the same id.
 *
 * Colour belongs in a Theme, not here: this stylesheet is shared by all ten
 * themes, so naming a theme-specific variable would raise a parse error under
 * the other nine.
 */

SurfScreen #hero-row {
    height: 10;
    padding: 0 0;
    margin: 1 0 0 0;
}

/* padding stays `0 1` -- horizontal only.
 *
 * The row is ten rows tall and SurfSignals spends them on a title plus six
 * detector rows inside a border. Vertical padding drops the sixth row, and the
 * sixth row is the BURN detector: the panel would still look complete while
 * one of the six advertised signals was simply absent. That is the FWA
 * coverage-badge bug (see the FWAHeroBox comment above) in a different widget,
 * and tests/test_surf_registration.py asserts all six reach the compositor. */
SurfHero {
    width: 3fr;
    padding: 0 1;
}

SurfSignals {
    width: 2fr;
    padding: 0 1;
}

/* The two views of the middle-left slot, toggled with `c`. Both carry the same
 * width so the swap does not reflow the row. */
SurfFeed, SurfDevActivity {
    width: 3fr;
    padding: 0 1;
}

SurfMarket {
    width: 2fr;
    padding: 0 1;
}

SurfNft {
    width: 1fr;
    padding: 0 1;
}

/* The two scrolling panes. `SurfFeed` and `SurfDevActivity` each compose a
 * title `Static` plus a `RichLog` (see their DEFAULT_CSS), and the `RichLog`
 * is what must absorb the leftover height -- without `height: 1fr` it sizes to
 * its content and the panel grows or shrinks as posts arrive.
 *
 * No `DataTable` rule here on purpose: not one of the six surf widgets mounts
 * a `DataTable`. Feed and activity use `RichLog`; hero, signals, market and
 * NFT are `Static` rows only. A selector for a widget that is never mounted
 * matches nothing and reads, to the next person, as though it were load-
 * bearing.
 *
 * `padding` and `scrollbar-size` are deliberately *not* restated: the widget
 * DEFAULT_CSS owns them, this block already pads the containing widget, and
 * restating the padding here would double it. */
SurfFeed > RichLog,
SurfDevActivity > RichLog {
    height: 1fr;
}
```

- [ ] Run to green, and re-run WP5's screen suite to prove the block did not disturb it:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py tests/screens/test_surf_screen.py -v
```

  Expected: all green.

- [ ] Verify the last rule against what the widgets actually mount, rather than trusting the block above:

```bash
cd /Library/Vibes/autopull && grep -n "RichLog\|DataTable" maxpane_dashboard/widgets/surf/*.py
```

  Expected: `RichLog` in `feed.py` and `activity.py` only, and **no `DataTable` anywhere**. If that holds, the block is right as written. If a surf widget has since grown a `DataTable`, add a selector for that widget — do not add one speculatively, and do not restore the `SurfFeed/SurfDevActivity/SurfNft DataTable` rule the earlier draft of this plan carried: it matched nothing.

- [ ] Prove the padding test bites: temporarily change `SurfScreen #hero-row`'s `padding: 0 0;` to `padding: 1 0;`, run `.venv/bin/python -m pytest tests/test_surf_registration.py -k hero_row -v` and confirm it goes red with the clipping message, then restore `0 0` and re-run to green.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/themes/minimal.tcss tests/test_surf_registration.py && git commit -m "feat(surf): restate the surf layout in the shared stylesheet"
```

---

### Task WP6.7: `FULL_LAYOUT_COLUMNS` reconciliation (WP5 hand-off item 2)

**Files:**
- Modify: `maxpane_dashboard/__main__.py` (**only if** `SURF_FULL_LAYOUT_COLUMNS > 143`)
- Test: `tests/test_surf_registration.py` (append)

**Interfaces:**
- Consumes: `maxpane_dashboard.screens.surf.SURF_FULL_LAYOUT_COLUMNS` (WP5's measured value).
- Produces: `maxpane_dashboard.__main__.FULL_LAYOUT_COLUMNS >= SURF_FULL_LAYOUT_COLUMNS`, with the `--font-size` help text and the README width table agreeing.

**Steps:**

- [ ] Read the measured value recorded in Task WP6.1 and run WP5's tripwire:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/screens/test_surf_screen.py -k fits_inside -v
```

  Two outcomes, both legitimate:
  - **green** — surf fits inside 143. Nothing in `__main__.py` changes; go to the app-level test below.
  - **red** — the failure message names both numbers (`surf needs N columns but __main__.FULL_LAYOUT_COLUMNS documents 143`). WP5 left it red by design; WP6 is what turns it green.

- [ ] Write the failing test (append) — the app-level statement of the same invariant, so it holds for every dashboard added later, not just surf:

```python
# ---------------------------------------------------------------------------
# __main__.FULL_LAYOUT_COLUMNS must cover every dashboard, surf included
# ---------------------------------------------------------------------------


def test_the_documented_width_covers_surf() -> None:
    """``--font-size`` help quotes this number; it must not become a lie."""
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
    from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS

    assert FULL_LAYOUT_COLUMNS >= SURF_FULL_LAYOUT_COLUMNS, (
        f"surf needs {SURF_FULL_LAYOUT_COLUMNS} columns, the app documents "
        f"{FULL_LAYOUT_COLUMNS}: raise FULL_LAYOUT_COLUMNS and the README "
        "width table together"
    )


def test_the_readme_quotes_the_documented_width() -> None:
    """The README's width table is prose around one number; pin them together."""
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert f"≥ {FULL_LAYOUT_COLUMNS}" in readme, (
        f"README's width table never mentions ≥ {FULL_LAYOUT_COLUMNS}"
    )
```

- [ ] Run and observe:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -k "documented_width or readme_quotes" -v
```

  Expected: if surf measured ≤ 143 both pass immediately (say so explicitly in the task report — a passing test written before its subject is only acceptable when it is an invariant, which this is). If surf measured wider, `test_the_documented_width_covers_surf` fails with the message above and `test_the_readme_quotes_the_documented_width` fails on the stale `≥ 143`.

- [ ] Implement **only in the wider case**, in `maxpane_dashboard/__main__.py` (substitute the measured `N`):

```python
#: It has come down twice.  198 while the FWA activity feed shared the bottom
#: row (it took 3fr of 7 and left the chase board and settlement table ~55
#: columns each); 172 once the feed moved into the odds board's slot behind
#: ``c``; and 143 once the buy-gate signal was shortened, which was what the
#: last marker had been waiting on -- the signals panel, not a table, was the
#: binding constraint at the end.
#:
#: It went back up to N when the surf dashboard landed: SurfScreen measures N
#: columns before its last ``‹ widen`` marker clears in both ``c`` views
#: (``screens/surf.py::SURF_FULL_LAYOUT_COLUMNS``, measured against composited
#: output).  This constant documents the *widest* dashboard, so it is the max
#: over all of them, never the most recent one.
#:
#: Font size is the only lever most people have over this -- a window is
#: already as wide as the display.
FULL_LAYOUT_COLUMNS = N
```

  and update the README width table in the same edit (the `≥ 143` row becomes `≥ N`, with a surf row added), since `test_the_readme_quotes_the_documented_width` covers it.

- [ ] Run to green — both the surf and FWA width tests, because raising the constant moves FWA's test too:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py tests/screens/test_surf_screen.py tests/test_cli_font_size.py -v
```

  Expected: all green. Watch `test_the_documented_width_matches_the_layout` specifically: it asserts FWA shows **zero** markers at `FULL_LAYOUT_COLUMNS` and **at least one** at `FULL_LAYOUT_COLUMNS - 4`. Raising the constant keeps the first true and can break the second — if it does, the "tight, not padded" claim now belongs to surf, not FWA, and that test must be reworded to assert the tightness against the *widest* dashboard. Report the wording change rather than deleting the assertion.

- [ ] Commit (skip entirely if nothing changed except the two new tests, which still get committed):

```bash
cd /Library/Vibes/autopull && git add maxpane_dashboard/__main__.py README.md tests/test_surf_registration.py && git commit -m "fix(surf): document the widest dashboard's column requirement"
```

---

### Task WP6.8: Offline degradation smoke — the whole app, every source down

**Files:**
- Modify: none
- Test: `tests/test_surf_registration.py` (append)

**Interfaces:**
- Consumes: `SURF_KEYS`; `maxpane_dashboard.data.surf_manager.SOURCES` (the degraded vocabulary — the doubles must speak it, never invent names); the app path splash → menu → `7`.
- Produces: a committed acceptance test for PRD §11.3 ("all six detectors degrade to explicit states under full network outage; no signal fires").

**Steps:**

- [ ] Write the test (append). Two managers: one that raises on every fetch (the DNS-failure shape) and one that returns the full contract with every value `None` (the all-sources-down shape the manager is actually specified to produce):

```python
# ---------------------------------------------------------------------------
# PRD §11.3: full outage renders explicit states, never a crash or a zero
# ---------------------------------------------------------------------------


class BoomManager:
    """Every fetch fails, the way an offline launch fails."""

    def __init__(self) -> None:
        self._error_count = 1
        self.calls = 0

    async def fetch_and_compute(self) -> dict[str, Any]:
        self.calls += 1
        raise RuntimeError("no network")

    async def close(self) -> None:
        return None


class DeadSourcesManager:
    """Every source is down, but the contract is still honoured in full.

    ``degraded`` is built from the real :data:`SOURCES` tuple, not from
    hand-written names.  The vocabulary is PRD §5's "list[str] of source-group
    names" and the manager can only ever emit members of it -- a double that
    invents ``"state_rpc"``/``"blockscout"`` would still light the banner up
    while proving nothing about the strings the screen will actually receive,
    and would hide a ``_fmt_degraded`` bug that only bites on real group names.
    Importing the tuple also means a renamed group turns this test red instead
    of leaving it quietly testing a dead vocabulary.
    """

    def __init__(self) -> None:
        from maxpane_dashboard.data.surf_manager import SOURCES
        from maxpane_dashboard.data.surf_models import SURF_KEYS

        self._error_count = 1
        self.calls = 0
        self._keys = SURF_KEYS
        # `sorted` is the order the specified outage path emits (WP4's
        # `_cycle` sorts the collected group names); the outermost guard emits
        # `list(SOURCES)`. Same six names either way.
        self._degraded = sorted(SOURCES)

    async def fetch_and_compute(self) -> dict[str, Any]:
        self.calls += 1
        payload: dict[str, Any] = {key: None for key in self._keys}
        payload["degraded"] = list(self._degraded)
        return payload

    async def close(self) -> None:
        return None


def _offline_app(manager) -> MaxPaneApp:
    app, _stubs = _stubbed_app("surf")
    app._surf_manager = manager
    return app


@pytest.mark.parametrize("factory", [BoomManager, DeadSourcesManager])
def test_offline_launch_of_surf_never_kills_the_app(factory) -> None:
    """Splash -> menu -> [7] with the surf manager down: degraded, not dead."""
    key = next(k for k, game_id, *_ in GAMES if game_id == "surf")

    async def _run() -> None:
        manager = factory()
        app = _offline_app(manager)
        async with app.run_test(size=(143, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()

            assert app.screen.name == "surf"
            assert app._exception is None, repr(app._exception)
            assert app.is_running
            assert manager.calls >= 1, "the screen never even tried to fetch"
        assert app.return_code != 1

    asyncio.run(_run())


def test_a_full_outage_renders_explicit_states_not_zeros() -> None:
    """Every detector is on screen, none of them reads as a live number.

    ``0`` is the forbidden rendering: CLAUDE.md's "a failed read is None,
    never 0" exists because a zeroed supply reads as a 100% burn.
    """
    key = next(k for k, game_id, *_ in GAMES if game_id == "surf")

    async def _run() -> None:
        app = _offline_app(DeadSourcesManager())
        async with app.run_test(size=(143, 48)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()

            text = _screen_text(app)
            for label in (
                "NEW POST",
                "LP MIGRATION",
                "GATE OPEN",
                "NEW DEPLOY",
                "BRIDGE STAGE",
                "BURN",
            ):
                assert label in text, f"{label} vanished under outage"
            assert "degraded" in text.lower(), (
                "the title bar never told the operator sources are down"
            )
            assert "FIRED" not in text, (
                "a signal fired on an outage -- baselines moved on a failed read"
            )
            assert "$0.00" not in text, "a missing price rendered as zero"

    asyncio.run(_run())
```

- [ ] Run it:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -k "offline_launch or full_outage" -v
```

  Expected: green on the first run, because WP5 Task WP5.3 already covers the all-`None` payload at the screen level. That is precisely why the next step is mandatory rather than optional — an acceptance test nobody has seen fail is not evidence.

  Two assertions can misfire on **WP3's** rendered copy rather than on a defect, and must be adjusted rather than deleted if they do: `"FIRED" not in text` fails if `SurfSignals` prints a legend naming the three states (scope it to the six detector rows via `screen.query_one(SurfSignals)`'s rendered lines instead of the whole screen), and `"$0.00" not in text` depends on how `SurfMarket` formats a price. Both widgets live in `widgets/surf/`, which the ownership table assigns to WP3 — not WP4, which owns the manager that feeds them. Check the exact strings against `maxpane_dashboard/widgets/surf/` and against WP5's `tests/screens/test_surf_screen.py` before changing anything; the widget copy is WP3's to define and WP5's screen suite is the closest existing assertion of it.

- [ ] Prove the tests bite (three mutations, one at a time, each restored before the next):
  1. In `maxpane_dashboard/app.py`, comment out the `elif game_id == "surf":` branch → both parametrized cases go red on `app.screen.name == "surf"`. Restore.
  2. In `maxpane_dashboard/screens/surf.py`, make the title-bar builder drop the degraded suffix → `test_a_full_outage_renders_explicit_states_not_zeros` goes red on the `"degraded"` assertion. Restore (WP6 does not own this file — the mutation is local and uncommitted; `git diff maxpane_dashboard/screens/surf.py` must be empty afterwards).
  3. Point the `DeadSourcesManager` payload's `imd_price_usd` at `0` instead of `None` → the `"$0.00"` assertion goes red *if* the market widget formats zero that way; if it does not, replace that assertion with whatever the widget actually renders for `0` and note the finding. Restore.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add tests/test_surf_registration.py && git commit -m "test(surf): pin the full-outage rendering of the registered dashboard"
```

---

### Task WP6.9: Manual smoke run — the real binary, offline and live

**Files:** none (verification only; no commit)

**Interfaces:**
- Consumes: the installed console script / `python -m maxpane_dashboard`.
- Produces: a written observation list for the final report. This is the only step in the WP that a test cannot replace, because it exercises the real terminal, the real caches under `~/.maxpane/`, and the real network stack.

**Steps:**

- [ ] Forced-offline run. `httpx` honours proxy env vars by default (`trust_env=True`), so pointing everything at the discard port makes every request fail immediately without unplugging anything:

```bash
cd /Library/Vibes/autopull && ALL_PROXY=http://127.0.0.1:9 MAXPANE_ETH_RPC_URL=http://127.0.0.1:9 .venv/bin/python -m maxpane_dashboard --game surf --font-size 0 --log-level INFO
```

  Expected, and to be written down as observed or not:
  - splash appears, then the menu with a `[7]  Mission Control  surfsurf.eth announce channel + launch detectors on Ethereum` row;
  - pressing `7` mounts the dashboard within a frame; nothing blank, nothing half-drawn;
  - the title bar carries the `degraded: …` suffix; the status bar shows a non-zero error count;
  - all six detector rows are present with explicit unavailable states — **no row reads `FIRED`, `OK`, or a number**;
  - hero, market, feed, activity and NFT panels each show their own unavailable state; the NFT floor line reads the explicit `no keyless source` copy;
  - `c` still swaps feed ↔ dev activity, `r` re-attempts and fails again without stacking workers, `tab` cycles surf → fwa, `m` returns to the menu;
  - `q` exits cleanly to the shell (`echo $?` → `0`).

- [ ] Inspect the log — errors are expected, tracebacks reaching Textual are not:

```bash
grep -c "Traceback" ~/.maxpane/maxpane.log; grep -i "WorkerFailed\|surf" ~/.maxpane/maxpane.log | tail -20
```

  Expected: zero `WorkerFailed`; surf fetch failures logged at WARNING/ERROR with a source name; no `Traceback` originating in `screens/surf.py` or `widgets/surf/`.

- [ ] Live run (network on), to see the dashboard do its actual job:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m maxpane_dashboard --game surf --font-size 13
```

  Sanity-check against the captures (values as of 2026-08-08, expected to have moved): feed nonce ≥ 14 with the latest self-post decoded; IMD price near \$0.71 and the FP parity within a couple of percent; pool liquidity around \$549k; supply ≈ 2,376,731 IMD; IDMD holders ≈ 667; gate CLOSED, with the **identities-written line reading the unavailable state, not `1/2000`**; hook status NOT LIVE. **A value that matches the capture *exactly* to many decimals is a red flag** — it means a hardcoded constant leaked past PRD §6.2 and CLAUDE.md's "read values live" rule. Report any such match instead of celebrating it.

  **Three fields render `--` on a healthy live run, and that is correct — do not file it as a bug.** `identities_written`, `nft_written` and `nft_transfers_24h` all have **no keyless producer in v1** (WP0 open issue 9: the verified IdentityMD source exposes only `totalSupply` and `identityAllowed`, with no written-hash counter; Blockscout serves a *lifetime* transfer count, not a 24h rate). WP4 pins this deliberately — `_nft_payload` passes `NftStats.written` through untouched and `tests/data/test_surf_manager.py::test_nft_stats_reach_the_payload_and_the_floor_stays_none` asserts `data["nft_written"] is None` *specifically* to stop someone "fixing" it later with the lifetime counter. So expect, verbatim from WP3's widgets:

  - `SurfHero` identity-gate box: `CLOSED` over `-- written` (`_fmt_count(None)` → `--`);
  - `SurfNft` written line: `identities --/2000 written`;
  - `SurfNft` stats line: `667 holders · -- transfers/24h · dev holds 3`.

  A run that shows `1/2000` or a transfers-per-day number is the finding worth reporting — it means a documented constant was hardcoded past the missing producer.

- [ ] Confirm the cache file appears and reloads:

```bash
ls -l ~/.maxpane/surf_cache.json && .venv/bin/python -c "import json;d=json.load(open('$HOME/.maxpane/surf_cache.json'));print(sorted(d)[:10])"
```

  Expected: the file exists after a clean `q`, parses as JSON, and a second launch renders instantly from it behind an `as of HH:MM` marker.

- [ ] No commit. Record the observations for the final report; anything that misbehaves is a defect report against the owning WP (per CLAUDE.md: report defects in other agents' files, do not fix them).

---

### Task WP6.10: `CLAUDE.md` + `README.md` — the two documentation surfaces

**Files:**
- Modify: `CLAUDE.md`, `README.md`
- Test: `tests/test_surf_registration.py` (append)

**Interfaces:**
- Consumes: `GAMES`.
- Produces: CLAUDE.md dashboard table row 7 and an updated section heading; README dashboards table, usage line and description; a docs tripwire that auto-extends with `GAMES`.

**Steps:**

- [ ] Write the failing test (append):

```python
# ---------------------------------------------------------------------------
# the documentation surfaces (CLAUDE.md, README) -- derived from GAMES
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


def test_every_visible_dashboard_is_documented() -> None:
    """A dashboard nobody documented is a dashboard nobody finds.

    Derived from ``GAMES``, so it covers dashboard eight without being
    touched -- and goes red the moment one is added to the menu and not to
    the docs.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")

    for _key, game_id, name, _desc in GAMES:
        assert f"--game {game_id}" in readme, (
            f"README's usage block never shows `maxpane --game {game_id}`"
        )
        assert name in readme, f"README never names the {game_id} dashboard"
        assert f"`{game_id}`" in claude, (
            f"CLAUDE.md's dashboard table has no `{game_id}` row"
        )


def test_claude_md_counts_the_visible_dashboards() -> None:
    """The heading states a number; ``GAMES`` is that number."""
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    word = _NUMBER_WORDS[len(GAMES)]
    assert f"## The {word} visible dashboards" in claude, (
        f"CLAUDE.md does not say 'The {word} visible dashboards' while GAMES "
        f"lists {len(GAMES)}"
    )
```

- [ ] Run and observe the failure:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -k "documented or counts_the_visible" -v
```

  Expected: 2 failed. `test_every_visible_dashboard_is_documented` → `AssertionError: README's usage block never shows 'maxpane --game surf'`; `test_claude_md_counts_the_visible_dashboards` → CLAUDE.md still says "The six visible dashboards".

- [ ] Implement in `CLAUDE.md` — two edits. The table gains a row (keep `fwa` at position 1; the sentence under the table about `fwa` being the default is still true and stays):

```markdown
## The seven visible dashboards

| # | `--game` | Chain | Subject |
|---|---|---|---|
| 1 | `fwa` | Ethereum | Fake World Assets, inverse-weighted NFT gacha pool |
| 2 | `base` | Base | trending tokens, volume, signals |
| 3 | `frenpet` | Base | pet battles, leaderboard, activity |
| 4 | `cattown` | Base | fishing competition, KIBBLE economy |
| 5 | `ttt` | Ethereum | Ten Thousand Tokens, NFT + UniV4 burn-to-launch |
| 6 | `talismans` | Ethereum | core-conservation NFT collection |
| 7 | `surf` | Ethereum | surfsurf.eth Mission Control: announce channel + launch detectors |
```

  and, immediately after the "Hiding a dashboard touches five surfaces" paragraph, one sentence recording the direction that has now been exercised:

```markdown
**Adding one touches the same five**, in the order app.py → `__main__.py` → `GAMES`: the
registration tests derive their expectations from `GAMES`, so growing that list first turns
`tests/test_cli_game_choices.py` and `tests/test_app_startup.py` red until the wiring catches up.
`tests/test_surf_registration.py` is the worked example.
```

- [ ] Implement in `README.md` — three edits. The dashboards table:

```markdown
| **Talismans** | Ethereum | Core-conservation NFT collection, materials, essence × tier |
| **Mission Control** | Ethereum | surfsurf.eth announce feed, six launch detectors, IMD market, IDMD NFT |
```

  the usage block:

```bash
maxpane --game talismans       # start on Talismans view
maxpane --game surf            # start on surfsurf.eth Mission Control view
```

  and a short section after the FWA one, so the newest dashboard is explained rather than merely listed:

```markdown
### Mission Control — surfsurf.eth

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
```

- [ ] Run to green:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_surf_registration.py -v
```

  Expected: the whole file green.

- [ ] Prove the docs tripwire bites: delete the `maxpane --game surf` line from README, re-run `-k documented`, confirm red with the exact message, restore, re-run green.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add CLAUDE.md README.md tests/test_surf_registration.py && git commit -m "docs(surf): register Mission Control in the dashboard table and README"
```

---

### Task WP6.11: Version bump + editable reinstall

**Files:**
- Modify: `pyproject.toml`
- Test: none new (`tests/test_cli_version.py` is the existing guard)

**Interfaces:**
- Consumes: `importlib.metadata.version("maxpane")` via `maxpane_dashboard/__init__.py`.
- Produces: version `0.6.0` reported by `--version` **and** by the running status bar.

**Steps:**

- [ ] Bump the minor version — a new dashboard is a feature, and the last release was `0.5.4`:

```bash
cd /Library/Vibes/autopull && grep -n '^version' pyproject.toml
```

  Edit line 3 to `version = "0.6.0"`.

- [ ] Re-run the editable install. This is not optional housekeeping: `__version__` comes from installed distribution metadata, which an editable install writes **once, at install time**. Skipping this leaves every dev-run status bar and every `--version` reporting `0.5.4` — the exact failure CLAUDE.md records as having gone unnoticed for three months and four releases.

```bash
cd /Library/Vibes/autopull && .venv/bin/pip install -e . --no-deps -q && .venv/bin/python -m maxpane_dashboard --version
```

  Expected first line: `maxpane 0.6.0`, second line the `.venv` interpreter path.

- [ ] Run the version suite:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest tests/test_cli_version.py -v
```

  Expected: green. `test_version_matches_the_packaged_metadata` compares `__version__` against `importlib.metadata` — it passes whether or not you reinstalled, which is exactly why the manual `--version` check above is the real verification.

- [ ] Update the README's illustrative console block (`maxpane 0.5.0` → `maxpane 0.6.0`) so the example matches a version that exists. It is illustrative, not asserted; changing it costs nothing and stops it aging further.

- [ ] Commit:

```bash
cd /Library/Vibes/autopull && git add pyproject.toml README.md && git commit -m "chore: bump version to 0.6.0"
```

---

### Task WP6.12: Full suite, final review, integration commit sequence

**Files:** none (verification + handoff)

**Interfaces:**
- Consumes: everything.
- Produces: a green full suite, a reviewed commit list, and the merge command sequence for the user to approve.

**Steps:**

- [ ] Full Python suite, compared against the Task WP6.1 baseline:

```bash
cd /Library/Vibes/autopull && .venv/bin/python -m pytest -q 2>&1 | tail -5
```

  Expected: zero failures, and a count higher than the baseline by exactly the number of tests WP6 added (~28 in `tests/test_surf_registration.py`, plus the one extra `ALL_GAMES` parametrization in `tests/test_app_startup.py`). A count that grew by *less* than that means a file was collected twice or a test was silently skipped — check with `-p no:randomly --collect-only -q | tail -3`.

- [ ] Rust crate, untouched by this WP but part of "green":

```bash
cd /Library/Vibes/autopull/maxpane && cargo test 2>&1 | tail -5
```

- [ ] Confirm the working tree holds nothing unintended — WP0 committed `tests/fixtures/surf/` and WP2 its `signals/` subdirectory, and no local mutation from a prove-it-bites step survived:

```bash
cd /Library/Vibes/autopull && git status --short && git diff --stat
```

  Expected: both empty. If `maxpane_dashboard/screens/surf.py` or `refresh_guard.py` shows a diff, a mutation was not restored — restore it with the inverse edit, **never** with `git checkout --` (CLAUDE.md: the tree may hold someone else's uncommitted work).

- [ ] Review the WP's commits end to end:

```bash
cd /Library/Vibes/autopull && git log --oneline main..surf-dashboard
```

  Expected: WP0–WP5's commits followed by WP6's eight, in this order — surf manager wiring, SurfScreen install + cycle, `--game surf`, menu entry 7, stylesheet block, (optional) width reconciliation, outage test, docs, version bump.

- [ ] Re-verify the five surfaces agree, by hand, one last time (this is the check CLAUDE.md asks for, and it is cheap):

```bash
cd /Library/Vibes/autopull && grep -n '"surf"' maxpane_dashboard/screens/game_select.py maxpane_dashboard/app.py maxpane_dashboard/__main__.py && grep -n '`surf`' CLAUDE.md && grep -n -- '--game surf' README.md
```

  Expected: one `GAMES` row, four `app.py` hits (prefetch map, `_GAME_CYCLE`, `_launch_game` branch, `install_screen` name), one `__main__.py` choice, one CLAUDE.md table row, one README usage line.

- [ ] Hand off the integration sequence. **Do not run it without the user's go-ahead** — CLAUDE.md's rule is to commit or push only when asked, and the branch is the user's to merge:

```bash
# proposed, pending approval:
cd /Library/Vibes/autopull && git checkout main && git merge --no-ff surf-dashboard -m "feat: surf dashboard — surfsurf.eth Mission Control (#7)

Announce-channel detector suite for surfsurf.eth: six signals, decoded UTF-8
calldata feed, IMD market + FP parity, IDMD NFT stats. Keyless and read-only.
"
cd /Library/Vibes/autopull && .venv/bin/python -m pytest -q 2>&1 | tail -3   # green on main before anything is pushed
cd /Library/Vibes/autopull && git push origin main
cd /Library/Vibes/autopull && git tag v0.6.0 && git push origin v0.6.0        # tag triggers the PyPI publish
```

- [ ] Write the final report: the baseline vs final test counts, the measured `SURF_FULL_LAYOUT_COLUMNS` and whether `FULL_LAYOUT_COLUMNS` moved, the manual smoke observations from Task WP6.9, and any defect found in another WP's files (reported, not fixed).
