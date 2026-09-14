"""E3: nothing can hide from the sweep."""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import pkgutil

from maxpane_dashboard.screens.game_select import GAMES
from tests.address_sweep.registry import CASES

SCREENS = pathlib.Path("maxpane_dashboard/screens")
HELPER_MODULE = "maxpane_dashboard.widgets.address"

#: The hidden screens the app still installs (``app.py``); GAMES lists only the
#: visible ones, so these are named here and checked against the app's source.
HIDDEN_SCREENS = ("frenpet_full", "frenpet_wallet", "frenpet_perf", "dota", "bakery", "ocm")


def _game_id(entry) -> str:
    """GAMES entries are ``(key, id, name, description)`` tuples."""
    return entry[1]


def _composes_status_bar(cls: ast.ClassDef) -> bool:
    for node in ast.walk(cls):
        if isinstance(node, ast.Yield) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "StatusBar":
                return True
    return False


def _status_bar_screen_classes() -> set[str]:
    """Screen classes that compose a StatusBar themselves: every dashboard, hidden or not."""
    names = set()
    for path in SCREENS.glob("*.py"):
        src = path.read_text()
        if "yield StatusBar" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Screen") and _composes_status_bar(node):
                names.add(node.name)
    return names


def test_the_screen_scan_finds_the_dashboards():
    assert len(_status_bar_screen_classes()) >= 14


def test_every_dashboard_screen_has_a_sweep_case():
    registered = {c.screen_class.__name__ for c in CASES}
    assert registered == _status_bar_screen_classes(), (
        "a screen composes a StatusBar with no SweepCase, or a case names a screen that is gone")


def test_every_games_entry_is_covered():
    names = {c.name for c in CASES}
    missing = [_game_id(g) for g in GAMES if _game_id(g) not in names]
    assert not missing, missing


def test_every_hidden_screen_the_app_installs_is_covered():
    app_src = pathlib.Path("maxpane_dashboard/app.py").read_text()
    names = {c.name for c in CASES}
    for hidden in HIDDEN_SCREENS:
        assert f'name="{hidden}"' in app_src, (hidden, "no longer installed; update HIDDEN_SCREENS")
        assert hidden in names, hidden


def test_case_names_are_unique():
    names = [c.name for c in CASES]
    assert len(names) == len(set(names)), names


def test_an_address_rendering_case_seeds_at_least_one_address():
    empty = [c.name for c in CASES if not c.address_free and not c.seeded]
    assert not empty, empty


def _module_names(package: str) -> list[str]:
    """``package`` and every module under it; a plain module is just itself."""
    pkg = importlib.import_module(package)
    names = [package]
    if hasattr(pkg, "__path__"):
        names += [m.name for m in pkgutil.walk_packages(pkg.__path__, prefix=package + ".")]
    return names


def test_a_dashboard_whose_widgets_use_the_helper_cannot_be_address_free():
    wrong = []
    for case in CASES:
        if not case.address_free:
            continue
        modules = [case.screen_class.__module__]
        for package in case.widget_packages:
            modules += _module_names(package)
        for name in modules:
            src = pathlib.Path(inspect.getfile(importlib.import_module(name))).read_text()
            if HELPER_MODULE in src:
                wrong.append((case.name, name))
    assert not wrong, wrong


def test_every_case_names_widget_packages_that_exist():
    for case in CASES:
        assert case.widget_packages, case.name
        for package in case.widget_packages:
            importlib.import_module(package)
