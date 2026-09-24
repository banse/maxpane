"""E3: nothing can hide from the sweep."""

from __future__ import annotations

import importlib
import inspect
import pathlib

from textual.screen import Screen

from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.screens.game_select import GAMES
from tests.address_sweep.imports import imported_names, imports_helper, widget_modules_of
from tests.address_sweep.registry import CASES

import pytest

#: Reads repo source or docs rather than exercising code (CLAUDE.md "Tests").
pytestmark = pytest.mark.guard

SCREENS = pathlib.Path("maxpane_dashboard/screens")

#: Screen modules that are not dashboards, by explicit name, so a new module is
#: a dashboard (and needs a SweepCase) unless someone adds it here on purpose.
NON_DASHBOARD_SCREEN_MODULES = (
    "splash",        # the boot animation: no data, no manager
    "game_select",   # the menu
    "wallet_input",  # the address prompt; what it echoes back is the user's own input
    "seat_input",    # surf's seat prompt: an IDMD token id, no address on it at all
    "submission_detail", # cached modal; dedicated test_submission_detail.py address coverage
    "oracle_answer", # cached modal; question/notes/value icons and links tested in test_oracle_answer.py
)

#: Screen subclasses that are shared machinery rather than a dashboard, so they
#: get no SweepCase. A **class**, never a module: excluding
#: ``screens/dashboard_screen.py`` wholesale (WP-A's first cut) would have made
#: a real dashboard later added beside the base class invisible to E3.
#: ``DashboardScreen`` has no ``compose``, no manager and no ``PANELS`` of its
#: own, so it renders nothing to sweep; its subclasses are the dashboards and
#: each of those has its own case.
ABSTRACT_SCREEN_CLASSES = (DashboardScreen, RecordDetailScreen)

#: The hidden screens the app still installs (``app.py``); GAMES lists only the
#: visible ones, so these are named here and checked against the app's source.
HIDDEN_SCREENS = ("frenpet_full", "frenpet_wallet", "frenpet_perf", "dota", "bakery", "ocm")


def _game_id(entry) -> str:
    """GAMES entries are ``(key, id, name, description)`` tuples."""
    return entry[1]


def _dashboard_screen_classes() -> set[type]:
    classes: set[type] = set()
    for path in sorted(SCREENS.glob("*.py")):
        if path.stem == "__init__" or path.stem in NON_DASHBOARD_SCREEN_MODULES:
            continue
        module = importlib.import_module(f"maxpane_dashboard.screens.{path.stem}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                cls.__module__ == module.__name__
                and issubclass(cls, Screen)
                and cls not in ABSTRACT_SCREEN_CLASSES
            ):
                classes.add(cls)
    return classes


def test_the_screen_scan_finds_the_dashboards():
    assert len(_dashboard_screen_classes()) >= 14
    for stem in NON_DASHBOARD_SCREEN_MODULES:
        assert (SCREENS / f"{stem}.py").exists(), (stem, "is gone; drop it from the tuple")


def test_every_dashboard_screen_has_a_sweep_case():
    registered = {c.screen_class for c in CASES}
    discovered = _dashboard_screen_classes()
    assert registered == discovered, (
        "a dashboard screen has no SweepCase, or a case names a screen that is gone",
        sorted(c.__name__ for c in discovered - registered),
        sorted(c.__name__ for c in registered - discovered),
    )


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


# -- the address-free agreement, on derived widget modules ----------------------------


def test_the_import_resolver_sees_every_import_form():
    helper = "maxpane_dashboard.widgets.address"
    forms = [
        ("from maxpane_dashboard.widgets.address import address_text\n", "maxpane_dashboard.widgets.x", False),
        ("import maxpane_dashboard.widgets.address\n", "maxpane_dashboard.screens.x", False),
        ("from maxpane_dashboard.widgets import address\n", "maxpane_dashboard.screens.x", False),
        ("from ..address import address_text\n", "maxpane_dashboard.widgets.surf.x", False),
        ("from .. import address\n", "maxpane_dashboard.widgets.surf.x", False),
        ("from . import address\n", "maxpane_dashboard.widgets.x", False),
        ("from .address import short_hex\n", "maxpane_dashboard.widgets", True),
    ]
    for source, module, is_package in forms:
        assert helper in imported_names(source, module, is_package), source
    assert helper not in imported_names(
        "from maxpane_dashboard.widgets.address_book import x\n", "maxpane_dashboard.widgets.x")


def test_every_case_derives_its_widget_modules():
    for case in CASES:
        assert widget_modules_of(case.screen_class.__module__), case.name


def test_a_dashboard_whose_widgets_use_the_helper_cannot_be_address_free():
    wrong = []
    for case in CASES:
        if not case.address_free:
            continue
        screen_module = case.screen_class.__module__
        for name in sorted({screen_module} | widget_modules_of(screen_module)):
            if imports_helper(name):
                wrong.append((case.name, name))
    assert not wrong, wrong
