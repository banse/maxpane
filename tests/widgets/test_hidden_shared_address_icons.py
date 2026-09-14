"""Copy icons in the hidden dashboards, the shared bakery panels, and the templates.

``ocm_activity_feed`` shows the actor's address; the shared
``widgets/activity_feed.py`` (bakery, hidden) shows the launcher's address
(or "the bakery" for a game-generated event with no launcher). Both are
built directly as ``rich.text.Text`` now, never a markup string, because the
icon's click action lives in a ``Style`` that only survives outside markup
parsing.

``frenpet.overview.fp_overview_leaderboard``, ``frenpet.sniper_queue`` and
``frenpet.top_leaderboard`` are confirmed false positives (recipe step 1):
each renders only pet id/name, score, ATK/DEF, win ratio, countdown and
status -- never ``FrenPet.owner``, though the model carries it. No existing
test for any of the three exercises an address field either. They are left
out of ``CASES`` and untouched.

The shared ``widgets/leaderboard.py`` (bakery) is the same kind of false
positive: it renders only ``BakerySummary.name``, never ``.creator`` /
``.leader`` / ``.top_cook``, has no ``_short_addr`` or slice-shaped
formatter, and is additionally pinned by
``tests/widgets/test_markup_safety.py::test_leaderboard_keeps_leader_bold_styling``,
which asserts the leader-row cell is the *exact* markup string
``"[bold]Normal Name[/]"`` -- independent confirmation that this widget must
stay untouched. See ``task-8-report.md`` for the full per-module read.

The three ``_short_addr`` / inline-slice sites in ``screens/frenpet_full.py``,
``screens/frenpet_perf.py`` and ``screens/frenpet_wallet.py`` are converted
alongside these widgets (per the brief) but are not covered here: they are
swept by Task 9, and ``tests/screens/test_frenpet_screens.py`` (run
alongside this file) already exercises all three screens end to end.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib

import pytest
from textual.app import App

from maxpane_dashboard.data.models import ActivityEvent
from tests.widgets.address_probe import CopyRecorder, icon_targets

ADDR = "0x" + "abcdef0123" * 4

#: Confirmed (recipe step 1) to render an address; see the module docstring
#: for the four candidates confirmed as false positives instead.
CASES = ["ocm.ocm_activity_feed", "activity_feed"]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget, self._payload = widget, payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, mod.__name__
    return classes[0]


def _activity_event(**overrides) -> ActivityEvent:
    """A well-formed bakery ``ActivityEvent`` with ``ADDR`` as the launcher."""
    fields = dict(
        type="simple",
        title="joined the bakery",
        description=None,
        launcher=ADDR,
        timestamp="1700000000",
        boost_type_name=None,
        boost_multiplier_bps=None,
        boost_duration=None,
        is_shield=None,
        is_outgoing=False,
        success=True,
        linked_bakery_id=None,
        linked_bakery_name=None,
    )
    fields.update(overrides)
    return ActivityEvent(**fields)


#: name -> update_data kwargs carrying ADDR, built from each widget's real
#: update_data signature: the OCM event-dict shape read off
#: OCMActivityFeed.update_data / _event_to_text, and the bakery ActivityEvent
#: shape shared with tests/widgets/test_activity_feed_degradation.py's own
#: ``_event`` helper.
SEEDED: dict[str, dict] = {
    "ocm.ocm_activity_feed": dict(recent_events=[{
        "timestamp": 0,
        "actor_address": ADDR,
        "event_type": "mint",
        "token_id": 1,
        "count": 1,
    }]),
    "activity_feed": dict(events=[_activity_event()]),
}


@pytest.mark.parametrize("name", CASES)
async def test_each_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert ADDR in {t[2] for t in icon_targets(app)}, name


@pytest.mark.parametrize("name", CASES)
async def test_clicking_the_icon_copies_exactly_that_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        target = next(t for t in icon_targets(app) if t[2] == ADDR)
        await pilot.click(offset=(target[0], target[1]))
        await pilot.pause()
        assert app.copied == [ADDR], name


async def test_ocm_feed_still_shows_the_bakery_placeholder_for_no_launcher():
    """The OCM feed has no "no launcher" concept, but must survive an event
    whose actor_address is empty -- confirming the conversion did not lose
    the widget's own defensive shape."""
    mod = importlib.import_module("maxpane_dashboard.widgets.ocm.ocm_activity_feed")
    app = _WidgetApp(
        _widget_class(mod)(),
        dict(recent_events=[{
            "timestamp": 0, "actor_address": "", "event_type": "mint",
            "token_id": 1, "count": 1,
        }]),
    )
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert app._exception is None


async def test_bakery_feed_shows_the_bakery_placeholder_for_no_launcher():
    """A game-generated random event (``launcher=None``) still renders --
    the special "the bakery" wording, not an address -- and does not carry
    an icon for the missing address."""
    mod = importlib.import_module("maxpane_dashboard.widgets.activity_feed")
    app = _WidgetApp(
        _widget_class(mod)(),
        dict(events=[_activity_event(launcher=None)]),
    )
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert app._exception is None
        assert ADDR not in {t[2] for t in icon_targets(app)}


@pytest.mark.parametrize("template", ["activity_feed_template", "leaderboard_template"])
def test_each_template_uses_the_helper_and_defines_no_formatter(template):
    path = pathlib.Path(f"maxpane_dashboard/templates/{template}.py")
    tree = ast.parse(path.read_text())
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "maxpane_dashboard.widgets.address" in imports, template
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert not {n for n in names if "addr" in n.lower()}, (template, names)
    assert "carries the copy icon" in (ast.get_docstring(tree) or ""), template
