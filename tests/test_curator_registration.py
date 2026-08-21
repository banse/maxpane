"""WP7: THE LIST is registered on every surface that must agree.

CLAUDE.md's "Adding one touches the same six surfaces" note, applied to
dashboard eight: ``GAMES`` in ``screens/game_select.py``, the manager/screen
wiring and ``_GAME_CYCLE`` in ``app.py``, ``MaxPaneApp.__init__``'s own
``initial_game`` default, the ``--game`` choices in ``__main__.py``, the
CLAUDE.md dashboard table and the README.  A dashboard registered on five of
the six is worse than one registered on none: it half-works.

``tests/test_surf_registration.py`` is the worked example this file is
modelled on, and the two differ in one structural way worth stating: surf was
an **append** at menu position 1, curator is an **insert** at position 2, so
every key below it shifted.  That is why nearly every assertion here is
*derived from* ``GAMES`` -- a later hide, show or reorder must move these
tests rather than break them.  Three things are deliberately not derived:

* ``CURATOR_ROW`` is pinned verbatim, because the *copy* is what must not
  drift and the key is part of what a user reads off the screen;
* ``MANAGER_ATTRS`` is hardcoded, because the failure it guards is a manager
  that was **never built**, which a derived list cannot see;
* the contiguity of the menu's hotkeys is **not** asserted here at all.  It
  already lives in ``tests/test_fwa_theme.py:490`` (inside
  ``test_game_cli_choice_includes_fwa``, whose name gives no hint that it
  guards this) as ``keys == [str(i) for i in range(1, len(GAMES) + 1)]``, and
  a second copy would be one more surface to drift.

Zero network.  Every manager on the app is replaced by a stub before
``run_test()``, and the curator screen is driven by a frozen payload loaded
from ``tests/fixtures/curator/screen/``.
"""

from __future__ import annotations

import asyncio
import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest
from textual.app import App

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.data.curator_manager import CuratorManager
from maxpane_dashboard.screens.curator import (
    CURATOR_FULL_LAYOUT_COLUMNS,
    CuratorScreen,
    LIST_RAW,
    MODE_LIST,
)
from maxpane_dashboard.screens.game_select import GAMES, GameSelectScreen
from maxpane_dashboard.themes import THEMES, THEME_NAMES
from maxpane_dashboard.widgets.curator import (
    ACTIVITY_TITLE,
    CLOSEST_CALLS_TITLE,
    CLUSTERS_TITLE,
    CuratorListFilterEditor,
    LEADERBOARD_TITLE,
    SIGNAL_LABELS,
    SIGNALS_TITLE,
)

REPO = Path(__file__).resolve().parents[1]
_TCSS = REPO / "maxpane_dashboard" / "themes" / "minimal.tcss"
_SCREEN_FIXTURES = REPO / "tests" / "fixtures" / "curator" / "screen"


def _resolved_imports(path: Path):
    """Yield ``(line, target)`` for every import, resolved from its package."""
    relative = path.relative_to(REPO).with_suffix("").parts
    package = relative[:-1]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            keep = len(package) - (node.level - 1)
            assert keep >= 0, f"{path}:{node.lineno} imports beyond package root"
            base = package[:keep]
        else:
            base = ()
        if node.module:
            base = (*base, *node.module.split("."))
        for alias in node.names:
            yield node.lineno, ".".join((*base, alias.name))


def _is_import_beneath(target: str, package: str) -> bool:
    return target == package or target.startswith(f"{package}.")


def test_nft_holder_data_layer_and_curator_widgets_keep_mvc_boundaries():
    holder_source = (
        REPO / "maxpane_dashboard" / "data" / "curator_nft_holders.py"
    ).read_text()
    assert "textual" not in holder_source
    assert "private_key" not in holder_source
    assert "eth_send" not in holder_source
    widget_dir = REPO / "maxpane_dashboard" / "widgets" / "curator"

    widget_paths = sorted(widget_dir.glob("*.py"))
    assert widget_paths
    for path in widget_paths:
        for lineno, target in _resolved_imports(path):
            for forbidden in (
                "maxpane_dashboard.data",
                "maxpane_dashboard.analytics",
            ):
                assert not _is_import_beneath(target, forbidden), (
                    f"{path.name}:{lineno} imports {target} across the MVC boundary"
                )
            assert target.split(".")[0] not in {"httpx", "aiohttp"}, (
                f"{path.name}:{lineno} imports {target} -- widgets do not make "
                "HTTP calls"
            )


def test_cr01_name_resolution_stays_in_the_curator_mvc_path():
    screen_path = (
        REPO / "maxpane_dashboard" / "screens" / "curator.py"
    )
    tree = ast.parse(
        screen_path.read_text(encoding="utf-8"), filename=str(screen_path)
    )
    client_module = "maxpane_dashboard.data.curator_nft_holders"
    allowed_holder_signals = {
        f"{client_module}.NftHolderPending",
        f"{client_module}.NftHolderUnavailable",
    }
    for lineno, target in _resolved_imports(screen_path):
        assert not (
            _is_import_beneath(target, client_module)
            and target not in allowed_holder_signals
        ), (
            f"curator.py:{lineno} imports the NFT holder client directly: {target}"
        )

    curator_classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CuratorScreen"
    ]
    assert len(curator_classes) == 1, (
        "curator.py must define exactly one module-level CuratorScreen"
    )
    handlers = [
        node for node in curator_classes[0].body
        if isinstance(node, ast.FunctionDef)
        and node.name == "on_nft_collection_add_requested"
    ]
    assert len(handlers) == 1, (
        "CuratorScreen must define exactly one immediate synchronous "
        "on_nft_collection_add_requested handler"
    )
    handler = handlers[0]
    assert not any(isinstance(node, ast.Await) for node in ast.walk(handler)), (
        "the NFT add message handler must not await network work"
    )
    scheduled_workers = [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr == "run_worker"
        and node.args
        and isinstance(node.args[0], ast.Call)
        and isinstance(node.args[0].func, ast.Attribute)
        and isinstance(node.args[0].func.value, ast.Name)
        and node.args[0].func.value.id == "self"
        and node.args[0].func.attr == "_resolve_nft_collection_name"
        and any(
            keyword.arg == "group"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "_NFT_NAME_LOOKUP_WORKER_GROUP"
            for keyword in node.keywords
        )
        and any(
            keyword.arg == "exclusive"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )
    ]
    assert len(scheduled_workers) == 1, (
        "the NFT add handler must schedule one exclusive dedicated-group "
        "CuratorScreen name worker"
    )

    workers = [
        node for node in curator_classes[0].body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_resolve_nft_collection_name"
    ]
    assert len(workers) == 1, (
        "CuratorScreen must define exactly one immediate async NFT name worker"
    )
    worker = workers[0]
    manager_calls = [
        node.value
        for node in ast.walk(worker)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "resolve_nft_collection_name"
        and isinstance(node.value.func.value, ast.Attribute)
        and node.value.func.value.attr == "_data_manager"
        and isinstance(node.value.func.value.value, ast.Name)
        and node.value.func.value.value.id == "self"
    ]
    assert len(manager_calls) == 1, (
        "the CuratorScreen worker must resolve custom NFT names once through "
        "self._data_manager.resolve_nft_collection_name(...)"
    )

    for path in (REPO / "maxpane_dashboard" / "screens").glob("*.py"):
        if path.name == "curator.py":
            continue
        other_tree = ast.parse(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        for lineno, target in _resolved_imports(path):
            assert not (
                target in {
                    "maxpane_dashboard.widgets.curator.*",
                    "maxpane_dashboard.widgets.curator.FilterApplyRequested",
                    "maxpane_dashboard.widgets.curator.list_filter.*",
                    "maxpane_dashboard.widgets.curator.list_filter.FilterApplyRequested",
                }
            ), f"{path.name}:{lineno} imports the curator filter-apply event"
        for node in ast.walk(other_tree):
            if isinstance(node, ast.Name):
                assert node.id != "FilterApplyRequested", (
                    f"{path.name}:{node.lineno} uses the curator filter-apply event"
                )
            elif isinstance(node, ast.Attribute):
                assert node.attr != "FilterApplyRequested", (
                    f"{path.name}:{node.lineno} uses the curator filter-apply event"
                )


def test_cr01_copy_does_not_leak_into_the_shared_curator_hero():
    shared_path = (
        REPO / "maxpane_dashboard" / "widgets" / "curator" / "hero.py"
    )
    executable_strings = tuple(text for _line, text in _rendered_strings(shared_path))
    for forbidden in (
        "YOUR WALLET", "multiple filters applied",
        "NFT holder data loading",
    ):
        assert all(forbidden not in text for text in executable_strings), (
            f"shared curator hero contains list-only copy {forbidden!r}"
        )

#: The one menu row this WP adds, asserted verbatim so the copy cannot drift.
CURATOR_ROW = (
    "2",
    "curator",
    "THE LIST",
    "Zero-custody allowlist game w/ an hourly doomsday clock on Ethereum",
)

#: The id every surface spells.  One literal, used by every assertion below
#: that has to name the dashboard at all, so a rename fails once and loudly.
GAME_ID = CURATOR_ROW[1]

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
    "_curator_manager",
]

#: The three hero box headlines the GRACE payload renders (PRD §3's table:
#: CLOCK · THE LIST · CURVE).  The judged and settled phases swap the third
#: for SURVIVAL and FINAL; the theme sweep below drives grace, so these three
#: are the ones that must reach the compositor under all ten palettes.
HERO_HEADLINES = ("CLOCK", "THE LIST", "CURVE")

#: The five panel titles, imported rather than retyped -- a literal copied
#: into this file would certify a string nobody renders.
PANEL_TITLES = (
    LEADERBOARD_TITLE,
    SIGNALS_TITLE,
    ACTIVITY_TITLE,
    CLOSEST_CALLS_TITLE,
    CLUSTERS_TITLE,
)


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


class CountingManager:
    """Manager that records fetches and closes.  Never touches the network."""

    def __init__(self) -> None:
        self._error_count = 0
        self.calls = 0
        self.closed = 0
        #: ``_launch_game`` reads this off the curator manager to build the
        #: screen, so the stub has to carry it.
        self.wallet = None

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


def _screen_lines(app) -> list[str]:
    strips = app.screen._compositor.render_strips()
    return ["".join(seg.text for seg in strip) for strip in strips]


def _menu_row(game_id: str) -> tuple[str, str, str, str]:
    """The ``GAMES`` row for *game_id*, or a failure that names it."""
    for row in GAMES:
        if row[1] == game_id:
            return row
    pytest.fail(f"{game_id!r} is not offered by the selection menu")


# ---------------------------------------------------------------------------
# app.py -- the manager
# ---------------------------------------------------------------------------


def test_every_manager_attribute_exists_on_a_fresh_app() -> None:
    """``__init__`` builds every manager, the curator's included."""
    app = MaxPaneApp()
    for attr in MANAGER_ATTRS:
        assert getattr(app, attr, None) is not None, f"{attr} was never built"


def _manager_attrs_literals() -> dict[str, list[str]]:
    """Every module-level ``MANAGER_ATTRS`` literal under ``tests/``, by path.

    Found by walking the tree rather than by importing four modules by name,
    because the failure below is precisely "a copy nobody remembered": a fifth
    file that grows one is covered the day it is written.
    """
    found: dict[str, list[str]] = {}
    for path in sorted((REPO / "tests").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):  # pragma: no cover - a broken test file
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "MANAGER_ATTRS" not in names or not isinstance(node.value, ast.List):
                continue
            found[str(path.relative_to(REPO))] = [
                el.value
                for el in node.value.elts
                if isinstance(el, ast.Constant) and isinstance(el.value, str)
            ]
    return found


def test_every_copy_of_manager_attrs_names_every_manager_the_app_builds() -> None:
    """The stub list is hardcoded in **four** test modules, and a dashboard is
    added by growing all of them.

    Wave 5 grew three and missed the fourth: ``tests/test_game_select_quit.py``
    kept a list ending at ``_surf_manager``, so a **real** ``CuratorManager``
    survived into ``run_test()`` and the ``q`` it presses awaited its real
    ``close()`` -- which saves the cache.  Five headless tests that document
    "zero network" therefore rewrote the developer's own
    ``~/.maxpane/curator_cache.json`` (7.5 MB of folded deposit history) with
    an empty 299-byte one, and the LOW-19 close-once guarantee silently stopped
    covering dashboard eight.

    Hardcoding the lists is right -- a list derived from the app cannot see a
    manager that was never built (see ``MANAGER_ATTRS`` above) -- so this is
    the agreement half of that redundancy, the ``_GAME_CYCLE`` pattern
    CLAUDE.md documents.  It is deliberately not "the four copies are equal to
    each other": four copies that agree and are all short would pass that.
    """
    app = MaxPaneApp()
    built = {name for name in vars(app) if name.endswith("_manager")}
    assert "_curator_manager" in built  # the app half, so this cannot pass empty

    copies = _manager_attrs_literals()
    assert len(copies) >= 4, f"expected four copies of MANAGER_ATTRS, found {sorted(copies)}"
    for path, attrs in copies.items():
        assert set(attrs) == built, (
            f"{path}'s MANAGER_ATTRS disagrees with the managers "
            f"MaxPaneApp.__init__ builds: missing {sorted(built - set(attrs))}, "
            f"unknown {sorted(set(attrs) - built)}. Every copy must be grown "
            "when a dashboard is added -- an ungrown one leaves a REAL manager "
            "in a headless test, which quits by writing the user's own cache."
        )


def test_the_curator_manager_takes_the_poll_interval() -> None:
    """The app hands its poll interval on, like every other game."""
    app = MaxPaneApp(poll_interval=45)
    assert isinstance(app._curator_manager, CuratorManager)
    assert app._curator_manager.poll_interval == 45


def test_the_curator_manager_takes_the_wallet_and_normalises_it() -> None:
    """The YOU row is wallet-scoped, so this manager is one of the few that
    takes an address.

    ``MaxPaneApp.__init__``'s parameter is ``wallet_address`` and the app does
    **not** keep it on ``self``, so the only place it survives is on the
    manager -- which is where ``_launch_game`` reads it back from.  The empty
    string ``config.get_wallet()`` returns when nothing is configured must
    normalise to ``None``, not to a falsy address the YOU row would try to
    render.
    """
    address = "0x2d3f0000000000000000000000000000000000ab"
    assert MaxPaneApp(wallet_address=address)._curator_manager.wallet == address
    assert MaxPaneApp(wallet_address="")._curator_manager.wallet is None
    assert MaxPaneApp()._curator_manager.wallet is None


def test_the_prefetch_map_points_at_the_curator_manager() -> None:
    """Identity, not truthiness: a second manager would poll twice and warm
    a cache the screen never reads."""
    app = MaxPaneApp()
    assert app._prefetch_manager(GAME_ID) is app._curator_manager


def test_quit_closes_the_curator_manager_exactly_once() -> None:
    """``q`` must await ``CuratorManager.close()`` -- client closed, cache saved.

    Driven through the **menu** quit path, which is the one that used to skip
    ``action_quit`` entirely (LOW-19): ``GameSelectScreen`` deliberately does
    not handle ``q``, so it bubbles to the app binding and both quit paths run
    the same graceful shutdown.  Exactly once, because a second close would
    mean two shutdown chains and a cache written twice.
    """
    app, stubs = _stubbed_app(initial_game=GAME_ID)

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")  # dismiss the splash
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press("q")
            await pilot.pause()

    asyncio.run(_run())
    assert stubs["_curator_manager"].closed == 1, (
        "CuratorManager.close() ran "
        f"{stubs['_curator_manager'].closed} times on quit; the curator cache "
        "is written by close() and the httpx client is closed there"
    )
    for attr, stub in stubs.items():
        assert stub.closed == 1, f"{attr} closed {stub.closed} times"


# ---------------------------------------------------------------------------
# app.py -- the screen install
# ---------------------------------------------------------------------------


def test_launching_curator_reaches_a_curator_screen() -> None:
    """Not the ``else: return`` at the bottom of ``_launch_game``.

    A missing branch is silent: the menu dismisses, nothing is pushed, and the
    user is left staring at the selection screen with no error anywhere.
    """
    app, _stubs = _stubbed_app()

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game(GAME_ID, first=True)
            await pilot.pause()
            assert isinstance(app.screen, CuratorScreen)
            assert app.screen.name == GAME_ID

    asyncio.run(_run())


def test_launching_curator_twice_reuses_one_installed_screen() -> None:
    """``is_screen_installed`` guards the install, so ``tab`` back and forth
    does not stack a second screen (and a second refresh timer) on every lap."""
    app, _stubs = _stubbed_app()

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game(GAME_ID, first=True)
            await pilot.pause()
            first = app.screen
            app._launch_game(GAME_ID)
            await pilot.pause()
            assert app.screen is first, "a second CuratorScreen was installed"

    asyncio.run(_run())


def test_the_installed_screen_is_told_which_wallet_to_watch() -> None:
    """The address reaches the screen, and by the route the wiring documents.

    ``_launch_game`` runs long after ``__init__``'s ``wallet_address`` local
    is out of scope, so the screen's wallet is read back off the manager.  If
    the app ever kept a second copy, this is the test that notices the two
    disagreeing.
    """
    address = "0x2d3f0000000000000000000000000000000000ab"
    app = MaxPaneApp(wallet_address=address)
    for attr in MANAGER_ATTRS:
        stub = CountingManager()
        stub.wallet = address if attr == "_curator_manager" else None
        setattr(app, attr, stub)

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._launch_game(GAME_ID, first=True)
            await pilot.pause()
            assert app.screen._wallet == address

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# app.py -- the tab cycle
# ---------------------------------------------------------------------------


def test_curator_appears_in_the_tab_cycle_exactly_once() -> None:
    """Twice would visit it twice a lap; never would strand it behind ``m``."""
    assert MaxPaneApp._GAME_CYCLE.count(GAME_ID) == 1


def test_tab_from_the_previous_cycle_entry_reaches_curator() -> None:
    """The previous entry is *read from the cycle*, never named.

    Naming it would pin this test to today's order, and curator's whole
    registration is an insert -- the thing that reorders neighbours.
    """
    cycle = MaxPaneApp._GAME_CYCLE
    previous = cycle[cycle.index(GAME_ID) - 1]

    app, _stubs = _stubbed_app()

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            app._current_game = previous
            app._launch_game(previous, first=True)
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            assert app._current_game == GAME_ID, (
                f"tab from {previous!r} landed on {app._current_game!r}"
            )
            assert isinstance(app.screen, CuratorScreen)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# screens/game_select.py -- the menu row
# ---------------------------------------------------------------------------


def test_the_curator_menu_row_is_pinned_verbatim() -> None:
    """The copy is the artefact; the key is part of what the user reads."""
    assert CURATOR_ROW in GAMES, (
        f"the menu row for {GAME_ID} is {_menu_row(GAME_ID)!r}, not {CURATOR_ROW!r}"
    )


def test_the_curator_row_is_not_wildly_wider_than_its_neighbours() -> None:
    """The menu line is ``[N]  Name  description`` and a long description
    wraps or clips on a narrow terminal.

    Measured against the other rows rather than pinned to a number: what
    matters is that this row does not stand out, and the fleet's longest row
    moves as dashboards come and go.
    """
    def _width(row) -> int:
        key, _game_id, name, desc = row
        return len(f"[{key}]  {name}  {desc}")

    ours = _width(_menu_row(GAME_ID))
    others = [_width(row) for row in GAMES if row[1] != GAME_ID]
    assert ours <= max(others) + 6, (
        f"the {GAME_ID} row is {ours} columns against a longest-other of "
        f"{max(others)}; shorten the description"
    )


def test_pressing_the_menu_key_opens_the_curator_screen() -> None:
    """The key is read out of ``GAMES``, so a renumber moves this test."""
    key, game_id, _name, _desc = _menu_row(GAME_ID)
    app, _stubs = _stubbed_app()

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("space")  # dismiss the splash
            await pilot.pause()
            assert isinstance(app.screen, GameSelectScreen)
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, CuratorScreen), (
                f"menu key {key!r} opened {type(app.screen).__name__}"
            )
            assert app.screen._mode == MODE_LIST
            assert app.screen._list_view == LIST_RAW

    asyncio.run(_run())


def test_the_curator_row_reaches_the_compositor_on_one_line() -> None:
    """Key and name on the **same composited line**.

    The loose version of this test searches the whole screen for ``[2]`` and
    for ``THE LIST`` separately, and stays green with the key sitting on some
    other dashboard's row -- which is exactly what a bad renumber produces.
    """
    key, _game_id, name, _desc = _menu_row(GAME_ID)
    app, _stubs = _stubbed_app()

    async def _run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            lines = _screen_lines(app)
            assert any(f"[{key}]" in line and name in line for line in lines), (
                f"no single composited line carries both [{key}] and {name!r}"
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# __main__.py -- the CLI
# ---------------------------------------------------------------------------


def _game_argument(monkeypatch) -> dict:
    """The ``--game`` ``choices`` and ``default``, read off the real parser.

    ``__main__`` builds its parser inside ``main()``, so the only way to see
    the argument is to run the CLI with ``MaxPaneApp`` swapped for a recorder
    and spy on ``add_argument`` -- exactly how ``test_surf_registration`` and
    ``test_cli_game_choices`` do it.  No TUI is started and no socket opened.
    """
    import argparse

    import maxpane_dashboard.__main__ as cli

    seen: dict = {}
    real_add_argument = argparse.ArgumentParser.add_argument

    def spy(self, *args, **kwargs):
        if args and args[0] == "--game":
            seen["choices"] = list(kwargs.get("choices") or [])
            seen["default"] = kwargs.get("default")
        return real_add_argument(self, *args, **kwargs)

    class _StubApp:
        def __init__(self, **kwargs):
            pass

        def run(self):  # never starts a real TUI
            return None

    monkeypatch.setattr(argparse.ArgumentParser, "add_argument", spy)
    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(cli.sys, "argv", ["maxpane"])
    cli.main()
    assert seen, "--game was never added to the parser"
    return seen


def test_the_cli_offers_curator_at_the_menus_own_position(monkeypatch) -> None:
    """Two hand-typed literals in two files, compared to each other.

    ``choices`` is deliberately not derived from ``GAMES`` (CLAUDE.md: the
    redundancy plus this agreement test is the pattern), so this compares two
    surfaces rather than a constant against itself.
    """
    choices = _game_argument(monkeypatch)["choices"]
    menu = [game_id for _key, game_id, *_ in GAMES]
    assert choices == menu
    assert choices.index(GAME_ID) == menu.index(GAME_ID) == 1


def test_the_cli_default_is_still_the_first_menu_entry(monkeypatch) -> None:
    """Curator went in at position **2**.  Position 1, the ``--game`` default
    and the bare-app prefetch all belong to whatever ``GAMES[0]`` names, and
    this insert must not have disturbed any of them."""
    default = _game_argument(monkeypatch)["default"]
    assert default == GAMES[0][1]
    assert default != GAME_ID
    assert MaxPaneApp.__init__.__defaults__ is not None
    # The sixth surface, verified rather than edited: the constructor's own
    # hand-typed literal must name the same dashboard.
    assert MaxPaneApp()._initial_game == GAMES[0][1]


# ---------------------------------------------------------------------------
# themes/minimal.tcss -- the curator block
# ---------------------------------------------------------------------------


def _curator_block() -> str:
    """The curator section of the shared stylesheet, or '' if absent."""
    text = _TCSS.read_text(encoding="utf-8")
    marker = "/* ── Curator screen"
    if marker not in text:
        return ""
    start = text.index(marker)
    nxt = text.find("/* ── ", start + len(marker))
    return text[start:] if nxt == -1 else text[start:nxt]


def test_the_shared_stylesheet_has_a_curator_block() -> None:
    """DEFAULT_CSS is a fallback; the app stylesheet is what actually renders."""
    block = _curator_block()
    assert block, (
        "themes/minimal.tcss has no curator block -- CuratorScreen's "
        "proportions come from DEFAULT_CSS only, which the shared rules for "
        "#middle-row, #bottom-row and #separator silently override"
    )
    for selector in (
        "CuratorScreen #hero-row",
        "CuratorScreen #middle-row",
        "CuratorScreen #curator-right-rail",
        "CuratorScreen #bottom-row",
        "CuratorHero",
        "CuratorLeaderboard",
        "CuratorSparklines",
        "CuratorSignals",
        "CuratorActivity",
        "CuratorClosestCalls",
        "CuratorClusters",
    ):
        assert selector in block, f"{selector} is not styled in the curator block"


@pytest.mark.parametrize("selector", ("#hero-row", "#curator-right-rail"))
def test_the_curator_rows_that_must_not_pad_vertically_do_not(selector: str) -> None:
    """Two rows lose a row of content to a single row of vertical padding.

    ``#hero-row`` is ``height: auto`` around an 8-row CuratorHero -- three
    height-7 boxes over the one-row export instruction -- so a vertical pad clips
    the instruction or the boxes' bottom border (the FWA coverage-badge bug), and
    against ``auto`` it also silently re-inflates the row.  ``#curator-right-rail``
    is worse: it holds a seven-row signal panel whose last row is YOU, and a
    fixed-height column loses its last row first.
    """
    block = _curator_block()
    rule = re.search(rf"CuratorScreen {re.escape(selector)}\s*\{{([^}}]*)\}}", block)
    assert rule, f"no CuratorScreen {selector} rule in the curator block"
    for line in rule.group(1).splitlines():
        line = line.strip()
        if line.startswith("padding:"):
            vertical = line.split(":", 1)[1].strip().rstrip(";").split()[0]
            assert vertical == "0", (
                f"vertical padding {vertical!r} on {selector} costs this row a "
                "line of content"
            )


def test_the_rail_reserves_its_scrollbar_gutter() -> None:
    """``scrollbar-gutter: stable`` is load-bearing, not cosmetic.

    Without it the scrollbar takes its column out of ``CuratorSignals`` -- the
    panel that binds this layout's width -- only on terminals under 42 rows,
    so the *width* requirement moves with the *height* and the pinned number
    is true at 48 rows and one short at 40.
    """
    rule = re.search(
        r"CuratorScreen #curator-right-rail\s*\{([^}]*)\}", _curator_block()
    )
    assert rule, "no CuratorScreen #curator-right-rail rule in the curator block"
    assert "scrollbar-gutter: stable" in rule.group(1)


# -- the two copies of the curator structure must agree ---------------------
#
# ``CuratorScreen.DEFAULT_CSS`` and the curator block restate the same layout:
# the block is what renders (an app stylesheet outranks DEFAULT_CSS),
# DEFAULT_CSS is what keeps the screen correctly proportioned when it is
# reviewed or mounted without the app stylesheet.  Edit one and not the other
# and the dashboard has two different layouts depending on which stylesheet is
# loaded -- and every screen test, which loads the real one, would certify
# only one of them.

#: Shorthand properties whose absence means "the CSS default", so that one
#: copy spelling ``padding: 0 0`` and the other omitting it is agreement.
_SHORTHAND_DEFAULTS = {"padding": "0", "margin": "0"}

#: What this comparison is about: the geometry.  Colour and text properties
#: belong to the theme and to the widgets' own DEFAULT_CSS.
_STRUCTURAL = (
    "width", "min-width", "max-width", "height", "min-height", "padding",
    "margin",
)

#: The two copies deliberately do **not** cover the same selector set, and the
#: asymmetry is load-bearing: ``#title-bar`` and ``#separator`` are
#: DEFAULT_CSS-only, because the shared stylesheet already styles those two
#: ids for every screen (lines 12 and 116) and the curator block restating
#: them would give a shared rule a second owner -- the surf block's documented
#: asymmetry, and the reason WORST_CASE_TITLE_COLUMNS was swept with the
#: shared ``padding: 0 2`` in force.
#:
#: Pinned as *sets*, not counted.  A count is the vacuity hole: renaming
#: ``CuratorClusters`` in one copy alone would drop that widget out of the
#: comparison entirely and still satisfy a length check.
_EDITOR_FALLBACK_ONLY = frozenset({
    "CuratorListFilterEditor .curator-filter-nft-selected",
    "CuratorListFilterEditor .curator-filter-nft-selected Label",
})
_DEFAULT_CSS_ONLY = frozenset({
    "#title-bar", "#separator", *_EDITOR_FALLBACK_ONLY,
})
_BLOCK_ONLY: frozenset[str] = frozenset()


def _expand(value: str) -> tuple[str, ...]:
    """CSS box shorthand -> four values, so ``0 0`` == ``0`` == ``0 0 0 0``."""
    parts = value.split()
    if len(parts) == 1:
        return tuple(parts * 4)
    if len(parts) == 2:
        return (parts[0], parts[1], parts[0], parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2], parts[1])
    return tuple(parts[:4])


def _rules(css: str) -> dict[str, dict[str, str]]:
    """``{selector: {property: value}}`` for the structural properties.

    A leading ``CuratorScreen `` is stripped: DEFAULT_CSS has to scope every
    rule to the screen, while the block scopes only the *ids* (the shared
    ``#middle-row`` / ``#bottom-row`` rules above it are law for ten other
    screens) and leaves the ``Curator*`` types unscoped, since those types
    exist nowhere else.  The two spellings mean the same thing here.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: dict[str, dict[str, str]] = {}
    for chunk in css.split("}"):
        if "{" not in chunk:
            continue
        head, body = chunk.split("{", 1)
        props = {}
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            name, _, value = decl.partition(":")
            name = name.strip()
            if name in _STRUCTURAL:
                props[name] = " ".join(value.split())
        if not props:
            continue
        for selector in head.split(","):
            selector = " ".join(selector.split())
            if selector.startswith("CuratorScreen "):
                selector = selector[len("CuratorScreen "):]
            out.setdefault(selector, {}).update(props)
    return out


def test_the_stylesheet_block_and_default_css_describe_one_layout() -> None:
    """Every rule the two copies share must carry the same geometry."""
    fallback = _rules(CuratorScreen.DEFAULT_CSS)
    block = _rules(_curator_block())

    assert set(fallback) - set(block) == _DEFAULT_CSS_ONLY, (
        "DEFAULT_CSS has selectors the curator block does not: "
        f"{sorted((set(fallback) - set(block)) - _DEFAULT_CSS_ONLY)} -- each "
        "is a rule the two copies no longer compare"
    )
    assert set(block) - set(fallback) == _BLOCK_ONLY, (
        "the curator block has selectors DEFAULT_CSS does not: "
        f"{sorted((set(block) - set(fallback)) - _BLOCK_ONLY)}"
    )

    for selector in sorted(set(fallback) & set(block)):
        for prop in _STRUCTURAL:
            default = _SHORTHAND_DEFAULTS.get(prop)
            left = fallback[selector].get(prop, default)
            right = block[selector].get(prop, default)
            if left is None and right is None:
                continue
            assert left is not None and right is not None, (
                f"{selector}: {prop} is declared in only one copy "
                f"(DEFAULT_CSS={left!r}, minimal.tcss={right!r})"
            )
            if prop in _SHORTHAND_DEFAULTS:
                assert _expand(left) == _expand(right), (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )
            else:
                assert left == right, (
                    f"{selector}: {prop} is {left!r} in DEFAULT_CSS and "
                    f"{right!r} in minimal.tcss"
                )


def test_selected_nft_geometry_matches_widget_and_screen_fallback_css() -> None:
    """The selected row is widget-owned and restated only for screen fallback."""
    widget = _rules(CuratorListFilterEditor.DEFAULT_CSS)
    fallback = _rules(CuratorScreen.DEFAULT_CSS)
    for selector in _EDITOR_FALLBACK_ONLY:
        assert fallback[selector] == widget[selector]


def test_the_bottom_row_is_one_fr_in_both_copies() -> None:
    """The one rule whose value is not obvious, pinned with its reason.

    ``#bottom-row`` is ``1fr``, not ``auto``, and it is the surf block's
    choice inverted.  Both of the row's slots are ``height: auto`` and
    ``CuratorActivity``'s content is a full deposit window, so ``auto`` here
    lets the row take 47 of the screen's rows, starves ``#middle-row`` down to
    one, and drops SIGNALS and YOU off the compositor entirely -- at which
    point the width sweep "passes" five columns early with the whole rail
    gone.  ``auto`` never rendered before the block existed (the shared
    ``#bottom-row { height: 1fr }`` outranks DEFAULT_CSS), which is how the
    two copies came to disagree in the first place.
    """
    for name, css in (
        ("DEFAULT_CSS", CuratorScreen.DEFAULT_CSS),
        ("minimal.tcss", _curator_block()),
    ):
        assert _rules(css)["#bottom-row"]["height"] == "1fr", (
            f"{name}'s #bottom-row is not 1fr"
        )


# ---------------------------------------------------------------------------
# every registered theme
# ---------------------------------------------------------------------------


def _grace_payload() -> dict:
    """The committed GRACE capture, as the manager's flat dict."""
    from maxpane_dashboard.data.curator_models import CURATOR_KEYS

    with open(_SCREEN_FIXTURES / "grace_payload.json") as handle:
        raw = json.load(handle)
    return {key: raw.get(key) for key in CURATOR_KEYS}


class _FrozenManager:
    """Returns one payload.  Never opens a socket, never reads a clock."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self._error_count = 0
        self.calls = 0
        self.wallet = None

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        return dict(self._payload)

    async def close(self) -> None:
        return None


class _ThemedHarness(App):
    """One CuratorScreen under the real stylesheet and one registered theme."""

    CSS_PATH = _TCSS

    def __init__(self, screen, theme_name: str) -> None:
        super().__init__()
        self._curator_screen = screen
        self._theme_name = theme_name

    def on_mount(self) -> None:
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = self._theme_name
        self.push_screen(self._curator_screen)


@pytest.mark.parametrize("theme_name", THEME_NAMES)
def test_the_curator_screen_renders_under_every_registered_theme(theme_name: str) -> None:
    """PRD §10: no theme of its own in v1, so it has to work in all ten.

    A class that exists in one palette is a dark panel in the other nine, and
    the failure is invisible to a suite that only ever renders the default.
    Asserted on **composited output**: every one of the seven detector rows,
    all three hero headlines and all five panel titles must reach a pixel, and
    nothing may ask to be widened at the width this layout is documented at.
    """
    payload = _grace_payload()
    screen = CuratorScreen(
        _FrozenManager(payload), poll_interval=30, name="curator", wallet=None
    )
    app = _ThemedHarness(screen, theme_name)

    async def _run() -> str:
        async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, 48)) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.press("h")
            await pilot.pause()
            return _screen_text(app)

    text = asyncio.run(_run())

    for label in SIGNAL_LABELS:
        assert label in text, f"{theme_name}: detector row {label!r} never rendered"
    for headline in HERO_HEADLINES:
        assert headline in text, f"{theme_name}: hero box {headline!r} never rendered"
    # CLUSTERS_TITLE and CLOSEST_CALLS_TITLE share one slot (the ``c`` pair),
    # so exactly one of the two is visible at a time.
    for title in (LEADERBOARD_TITLE, SIGNALS_TITLE, ACTIVITY_TITLE):
        assert title in text, f"{theme_name}: panel {title!r} never rendered"
    assert (CLUSTERS_TITLE in text) != (CLOSEST_CALLS_TITLE in text), (
        f"{theme_name}: the c-swap slot shows both tables or neither"
    )
    assert "‹ widen" not in text, (
        f"{theme_name}: a panel asks to be widened at "
        f"{CURATOR_FULL_LAYOUT_COLUMNS} columns, the width this layout is "
        "documented at"
    )


# ---------------------------------------------------------------------------
# the documented width
# ---------------------------------------------------------------------------


def test_the_app_wide_width_covers_the_curator_layout() -> None:
    """``FULL_LAYOUT_COLUMNS`` is the max over every dashboard.

    Curator measures 138 and FWA still binds at 143, so the constant did not
    move -- but if a curator edit ever pushed this layout past the app-wide
    number, the four surfaces that quote it (the constant, ``--font-size``'s
    help text, the README width table and CLAUDE.md's appended record) would
    all have to move together, and this is where that starts.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert CURATOR_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS, (
        f"the curator layout needs {CURATOR_FULL_LAYOUT_COLUMNS} columns but "
        f"the app documents {FULL_LAYOUT_COLUMNS}"
    )


# ---------------------------------------------------------------------------
# the documentation surfaces
# ---------------------------------------------------------------------------


def test_claude_md_documents_the_curator_dashboard() -> None:
    """The table row, at the position ``GAMES`` gives it."""
    key, game_id, _name, _desc = _menu_row(GAME_ID)
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")

    row = re.search(rf"^\|\s*{re.escape(key)}\s*\|\s*`{re.escape(game_id)}`\s*\|(.*)$",
                    text, re.M)
    assert row, (
        f"CLAUDE.md's dashboard table has no row `| {key} | `{game_id}` |` -- "
        "the table and GAMES disagree about position or spelling"
    )
    assert "Ethereum" in row.group(1), "the curator row does not name its chain"


def test_the_readme_documents_the_curator_dashboard() -> None:
    """Both halves: the table names it, the usage block shows the flag."""
    _key, game_id, name, _desc = _menu_row(GAME_ID)
    text = (REPO / "README.md").read_text(encoding="utf-8")

    assert f"--game {game_id}" in text, (
        f"the README's usage block never shows `--game {game_id}`"
    )
    assert f"**{name}**" in text, (
        f"the README's dashboard table never names {name!r}"
    )


def test_the_docs_record_the_measured_curator_width() -> None:
    """CLAUDE.md's width section states curator's own number.

    The app-wide constant did not move, so the appended record
    (198 -> 172 -> 143 -> ...) is untouched -- but "which dashboard binds is
    itself a measurement", and a width section that never mentions dashboard
    eight invites the next reader to assume it from an older paragraph.
    """
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert str(CURATOR_FULL_LAYOUT_COLUMNS) in text, (
        f"CLAUDE.md never states curator's measured {CURATOR_FULL_LAYOUT_COLUMNS}"
    )


# ---------------------------------------------------------------------------
# WP7.12 -- the static guardrails
# ---------------------------------------------------------------------------
#
# Five scans that never rot.  Each one is a hazard from the implementation
# plan's table whose enforcement is "a rule about the source", not "a value in
# a fixture" -- so they are cheap, they cannot go stale with the chain, and
# they fail on the day someone reintroduces the shape rather than on the day a
# user sees the consequence.  The four mandated *mutation* proofs are not here:
# a mutation proof is an act, and its record is the WP7.12 commit body.

#: Every production module THE LIST is made of.
CURATOR_PRODUCTION = sorted(
    [
        REPO / "maxpane_dashboard" / "analytics" / "curator_signals.py",
        REPO / "maxpane_dashboard" / "screens" / "curator.py",
        *(REPO / "maxpane_dashboard" / "data").glob("curator_*.py"),
        *(REPO / "maxpane_dashboard" / "widgets" / "curator").glob("*.py"),
    ]
)

#: Every test module that exercises it.
CURATOR_TESTS = sorted(
    [
        REPO / "tests" / "analytics" / "test_curator_signals.py",
        REPO / "tests" / "screens" / "test_curator_screen.py",
        REPO / "tests" / "widgets" / "test_curator_widgets.py",
        REPO / "tests" / "test_curator_registration.py",
        *(REPO / "tests" / "data").glob("test_curator_*.py"),
    ]
)


def test_the_guardrail_scans_are_looking_at_real_files() -> None:
    """The vacuity guard for every scan below.

    A glob that stops matching turns five tests green at once and silently.
    """
    assert len(CURATOR_PRODUCTION) >= 15, [p.name for p in CURATOR_PRODUCTION]
    assert len(CURATOR_TESTS) >= 7, [p.name for p in CURATOR_TESTS]
    for path in CURATOR_PRODUCTION + CURATOR_TESTS:
        assert path.is_file(), path


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _rendered_strings(path: Path):
    """Every string literal that is not a docstring, with its line number.

    Comments never enter the AST at all, and docstrings are dropped here, so
    what is left is the text that can actually reach a screen.  Scanning the
    raw file instead would fail on every module that *explains* the hazard it
    is avoiding -- which all of these do.
    """
    tree = _tree(path)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            yield node.lineno, node.value


def test_no_curator_module_divides_by_credited_delta() -> None:
    """H3: ``creditedDelta == 0`` is legitimate, so it may never be a divisor.

    A deposit whose new high-water mark is already above the 1000 ETH credit
    cap credits nothing and still counts in full toward the hour's survival.
    Anything that divides by it turns that legitimate zero into a crash or a
    NaN on the one deposit that matters most.
    """
    for path in CURATOR_PRODUCTION:
        for node in ast.walk(_tree(path)):
            divisor = None
            if isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Div, ast.FloorDiv, ast.Mod)
            ):
                divisor = node.right
            elif isinstance(node, ast.AugAssign) and isinstance(
                node.op, (ast.Div, ast.FloorDiv, ast.Mod)
            ):
                divisor = node.value
            if divisor is None:
                continue
            text = ast.unparse(divisor)
            assert "credited" not in text.lower(), (
                f"{path.name}:{node.lineno} divides by {text} -- creditedDelta "
                "is legitimately zero (H3)"
            )


#: The one place ``AT RISK`` is allowed: the mandated detector label.  Matched
#: on the *whole string*, not the phrase, because the hazard is the wording
#: sitting next to a volume figure -- a row whose entire text is the label is
#: the label.
_MANDATED_AT_RISK = {"HOUR AT RISK"}

#: Words that would turn gas-priced flow into a claim about money at stake.
_CAPITAL_WORDS = (r"\btvl\b", r"\blocked\b", r"\bat risk\b", r"\bcapital\b")


def test_no_curator_surface_labels_volume_as_tvl_or_capital() -> None:
    """H4: every wei is refunded inside the same transaction.

    The number under THE LIST is gas-priced flow, not money at stake, so
    ``TVL`` / ``locked`` / ``at risk`` / ``capital`` beside it would not be
    loose wording -- it would be a false claim about money, read by somebody
    deciding whether to send 60 ETH.  The copy reads
    ``routed (all refunded)``.

    Scanned over *rendered* strings only.  ``HOUR AT RISK`` is the mandated
    detector label and is allowed as a whole string.
    """
    surfaces = [
        p for p in CURATOR_PRODUCTION
        if "widgets" in p.parts or p.name in ("curator.py", "curator_manager.py")
    ]
    assert surfaces, "the H4 scan matched no surface files"
    for path in surfaces:
        for lineno, text in _rendered_strings(path):
            if text.strip() in _MANDATED_AT_RISK:
                continue
            lowered = text.lower()
            for pattern in _CAPITAL_WORDS:
                assert not re.search(pattern, lowered), (
                    f"{path.name}:{lineno} renders {text!r}, which claims "
                    "money is at stake; every wei is refunded in-tx (H4)"
                )


def test_no_curator_module_hardcodes_a_contract_parameter() -> None:
    """CLAUDE.md rule 4: read values live, never hardcode a documented one.

    The eight immutables plus ``POINTS_PER_ETH`` come off the ``once`` tier.
    ``curator_addresses`` pins ``LAUNCH_TIME`` so a test can prove the live
    read agrees -- it is a **pin, not a source** -- and this asserts nothing
    else ever reads it, which is the difference between a cross-check and a
    fallback that is right until it isn't.
    """
    from maxpane_dashboard.data import curator_client

    for path in CURATOR_PRODUCTION:
        if path.name == "curator_addresses.py":
            continue
        # Read off the AST, so a module may *name* the pin in a comment (and
        # curator_models.py does, explaining where it lives) without being
        # accused of reading it.  ``SEL_LAUNCH_TIME`` is the selector -- every
        # module may name that, because using it IS reading the chain.
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Name):
                assert node.id != "LAUNCH_TIME", (
                    f"{path.name}:{node.lineno} reads the pinned launchTime "
                    "instead of the chain's"
                )
            elif isinstance(node, ast.Attribute):
                assert node.attr != "LAUNCH_TIME", (
                    f"{path.name}:{node.lineno} reads the pinned launchTime "
                    "instead of the chain's"
                )
            elif isinstance(node, ast.Constant) and node.value == 1786910327:
                pytest.fail(
                    f"{path.name}:{node.lineno} hardcodes the launchTime literal"
                )

    # ...and every one of the nine really is on the once tier.
    import inspect

    config_src = inspect.getsource(curator_client.CuratorClient.fetch_config)
    for selector in (
        "SEL_LAUNCH_TIME", "SEL_HOURLY_THRESHOLD", "SEL_GRACE_PERIOD",
        "SEL_HOUR_DURATION", "SEL_MIN_DEPOSIT", "SEL_MIN_ESCALATION",
        "SEL_CREDIT_CAP", "SEL_FIRST_JUDGED_HOUR", "SEL_POINTS_PER_ETH",
    ):
        assert selector in config_src, f"fetch_config never reads {selector}"


#: Tokens that only appear in code that holds a key or signs something.
_KEY_TOKENS = (
    "api_key", "apikey", "x-api-key", "authorization", "bearer ",
    "private_key", "privatekey", "keystore", "mnemonic", "secret_key",
    "eth_sendrawtransaction", "eth_sendtransaction", "eth_signtransaction",
    "personal_sign", "signtransaction",
)

#: Libraries that exist to sign or to hold a key.
_SIGNING_IMPORTS = ("eth_account", "web3", "eth_keys", "eth_keyfile", "coincurve")


def test_no_curator_module_imports_a_signer_or_a_keystore() -> None:
    """Hard constraint 1 and 2: read-only and keyless, structurally.

    Scanned over the raw source rather than the AST -- unlike the H4 scan,
    there is no legitimate reason for any of these tokens to appear even in a
    comment here, and the whole package currently has zero hits for any of
    them.
    """
    for path in CURATOR_PRODUCTION:
        lowered = path.read_text(encoding="utf-8").lower()
        for token in _KEY_TOKENS:
            assert token not in lowered, f"{path.name} mentions {token!r}"
        for node in ast.walk(_tree(path)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                root = name.split(".")[0]
                assert root not in _SIGNING_IMPORTS, (
                    f"{path.name} imports {name} -- there is no signer in this repo"
                )


def test_no_curator_module_names_a_banned_rpc_host() -> None:
    """H11: dead, keyed or sunset endpoints, refused at construction.

    The frozenset is the enforcement; this asserts no URL anywhere in the
    curator code slips past it, including in a comment or a docstring, where a
    "try this one next" note is how a banned host comes back.
    """
    from maxpane_dashboard.data.curator_client import (
        _BANNED_HOST_SUFFIXES,
        _BANNED_RPC_HOSTS,
    )

    assert _BANNED_RPC_HOSTS and _BANNED_HOST_SUFFIXES

    for path in CURATOR_PRODUCTION:
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            for url in re.findall(r"https?://([^/\s\"')]+)", line):
                host = url.lower().split("@")[-1].split(":")[0]
                assert host not in _BANNED_RPC_HOSTS, (
                    f"{path.name}:{lineno} points at the banned host {host}"
                )
                assert not host.endswith(_BANNED_HOST_SUFFIXES), (
                    f"{path.name}:{lineno} points at {host}, which needs a key"
                )


def test_no_curator_test_can_touch_the_network() -> None:
    """Hard constraint 3, asserted structurally rather than hoped for.

    Every ``httpx.AsyncClient`` a curator test builds must be handed a
    transport -- a client without one has a live connection pool, and the
    difference between a suite that cannot reach the network and one that
    merely happens not to is a fixture going stale.
    """
    # Matched on parsed call expressions, not on text: this very file names
    # each of them as data, and a textual scan would accuse itself.
    forbidden = {
        "socket.socket", "socket.create_connection", "urlopen",
        "urllib.request.urlopen", "requests.get", "requests.post",
        "aiohttp.ClientSession",
    }
    for path in CURATOR_TESTS:
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if isinstance(node, ast.Call):
                assert ast.unparse(node.func) not in forbidden, (
                    f"{path.name}:{node.lineno} opens a real connection"
                )
        # Parsed, not grepped: test_curator_client.py contains the *string*
        # "httpx.AsyncClient(" inside an assertion about its own source, and a
        # textual scan reads that as a construction.
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if not isinstance(node, ast.Call):
                continue
            if ast.unparse(node.func) not in ("httpx.AsyncClient", "AsyncClient"):
                continue
            keywords = {kw.arg for kw in node.keywords}
            assert "transport" in keywords, (
                f"{path.name}:{node.lineno} builds an httpx.AsyncClient with "
                "no injected transport -- that client can reach the network"
            )
