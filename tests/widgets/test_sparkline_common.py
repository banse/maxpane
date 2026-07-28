"""MEDI-36: the sparkline helpers are shared code, not per-dashboard copies.

``templates/`` is the seed every new dashboard is grown from, so a defect
there is a defect in every dashboard that has not been written yet.  The
review found the mechanism in action: ``_coerce_points`` existed as three
byte-identical copies (ttt, talismans, fwa -- each copied from the
previous dashboard) alongside three *older* copies (ocm, cattown, dota)
that had never received the ``None``-tolerance hardening at all, while
``templates/sparkline_template.py`` -- the file the ninth dashboard will
be copied from -- carried the unhardened version.

Two things are therefore asserted here:

1. **Single definition.**  Every dashboard's ``_coerce_points`` /
   ``_build_sparkline`` must *be* the shared function object, and no
   sparkline module may define its own.  This is the guard that stops the
   fork from re-opening -- a future dashboard that pastes the helpers
   instead of importing them fails this test.
2. **The hardening actually reaches every dashboard**, including the
   template.  Each widget is mounted in a real ``App`` and driven with a
   history full of ``None`` entries and ragged rows, then pumped through
   an idle cycle, because Textual defers markup parsing: a widget that
   raises inside the message pump takes the whole app down (HIGH-7).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.templates.sparkline_template import GameSparklines
from maxpane_dashboard.widgets import sparkline_common
from maxpane_dashboard.widgets.cattown.ct_sparklines import CTSparklines
from maxpane_dashboard.widgets.dota.dota_sparklines import DOTASparklines
from maxpane_dashboard.widgets.fwa.fwa_sparkline import FWASparkline
from maxpane_dashboard.widgets.ocm.ocm_sparklines import OCMSparklines
from maxpane_dashboard.widgets.talismans.tal_sparkline import TalismansSparkline
from maxpane_dashboard.widgets.ttt.ttt_sparkline import TTTSparkline

#: Every widget class that draws a block sparkline, with its module.
SPARKLINE_WIDGETS = [
    OCMSparklines,
    CTSparklines,
    DOTASparklines,
    TTTSparkline,
    TalismansSparkline,
    FWASparkline,
    GameSparklines,  # the template -- the seed for dashboard #9
]

#: Histories no ``float`` arithmetic survives untreated.  Each of these
#: raised ``TypeError``/``IndexError`` in the unhardened copies.
POISONED_HISTORIES = [
    [None, (1.0, 2.0), (2.0, 3.0)],           # a null entry
    [(1.0, None), (2.0, 3.0)],                # a null value
    [(1.0, 2.0), "x"],                        # a string where a pair belongs
    [(1.0, 2.0), (2.0, "nope")],              # an unparseable value
    [[1.0], (2.0, 3.0)],                      # a ragged row
    [None, None],                             # nothing usable at all
    "not-a-series",                           # not a series at all
]


class _Harness(App):
    """Mount a single widget so ``update_data`` can be driven headlessly."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _history_kwargs(widget_cls, value) -> dict:
    """Build kwargs passing *value* to every history parameter."""
    params = inspect.signature(widget_cls.update_data).parameters
    kwargs = {
        name: value
        for name in params
        if name.endswith("_history") or name.startswith("series_")
    }
    if "spark_available" in params:
        # FWA gates rendering on this; without it the widget short-circuits
        # to its unavailable state and never reaches the coercion path.
        kwargs["spark_available"] = True
    return kwargs


# ---------------------------------------------------------------------------
# 1. one definition, imported everywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("widget_cls", SPARKLINE_WIDGETS, ids=lambda c: c.__name__)
def test_helpers_are_the_shared_functions(widget_cls) -> None:
    """No dashboard may carry its own copy of the sparkline helpers."""
    module = inspect.getmodule(widget_cls)

    coerce = getattr(module, "_coerce_points", None)
    assert coerce is sparkline_common.coerce_points, (
        f"{module.__name__} does not use the shared coerce_points; a private "
        "copy is how the ttt/talismans/fwa fork happened (MEDI-36)"
    )

    build = getattr(module, "_build_sparkline", None)
    assert build in (
        sparkline_common.build_sparkline,
        sparkline_common.build_sparkline_from_points,
    ), (
        f"{module.__name__} does not use a shared build_sparkline; fixes to a "
        "private copy reach no other dashboard (MEDI-36)"
    )


@pytest.mark.parametrize("widget_cls", SPARKLINE_WIDGETS, ids=lambda c: c.__name__)
def test_no_module_redefines_a_shared_helper(widget_cls) -> None:
    """A pasted helper body must fail this test, not ship quietly.

    ``is``-identity above is satisfiable by an import; this checks the
    source itself, so a dashboard that copies the function *and* shadows
    the import is caught too.
    """
    source = Path(inspect.getmodule(widget_cls).__file__).read_text(encoding="utf-8")
    defined = {
        node.name
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    forked = defined & {"_coerce_points", "_build_sparkline", "_trend_arrow"}
    assert not forked, (
        f"{widget_cls.__name__} redefines {sorted(forked)} instead of importing "
        "from widgets/sparkline_common.py -- import it, do not copy it (MEDI-36)"
    )


def test_template_seeds_an_import_not_a_copy() -> None:
    """The template must hand the next dashboard an import.

    Whatever ``sparkline_template.py`` contains is what dashboard #9 will
    contain, verbatim.
    """
    source = Path(
        inspect.getmodule(GameSparklines).__file__
    ).read_text(encoding="utf-8")
    assert "from maxpane_dashboard.widgets.sparkline_common import" in source
    assert "def _coerce_points" not in source
    assert "def _build_sparkline" not in source


# ---------------------------------------------------------------------------
# 2. the hardening reaches every dashboard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", POISONED_HISTORIES, ids=repr)
def test_coerce_points_never_raises(bad) -> None:
    """The boundary function absorbs anything a cache can hold."""
    out = sparkline_common.coerce_points(bad)
    assert isinstance(out, list)
    assert all(
        isinstance(pt, tuple)
        and len(pt) == 2
        and all(isinstance(v, float) for v in pt)
        for pt in out
    ), f"coerce_points let a malformed pair through: {out!r}"


@pytest.mark.parametrize("bad", POISONED_HISTORIES, ids=repr)
def test_build_and_trend_never_raise(bad) -> None:
    """Downstream helpers degrade rather than raise."""
    assert isinstance(sparkline_common.build_sparkline_from_points(bad), str)
    assert isinstance(sparkline_common.trend_arrow(bad), str)


@pytest.mark.parametrize("value", [None, "abc", float("nan"), float("inf")])
def test_fmt_compact_degrades_to_a_dash(value) -> None:
    """A missing or non-finite number prints ``--``, never ``nan``."""
    assert sparkline_common.fmt_compact(value) == "--"


@pytest.mark.parametrize("widget_cls", SPARKLINE_WIDGETS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("bad", POISONED_HISTORIES, ids=repr)
async def test_widget_survives_a_poisoned_history(widget_cls, bad) -> None:
    """Every dashboard's sparkline survives a corrupt cached history.

    Driven through a mounted widget and an idle cycle, so a deferred
    message-pump failure surfaces as ``app._exception`` rather than
    passing silently.
    """
    widget = widget_cls()
    app = _Harness(widget)
    async with app.run_test() as pilot:
        widget.update_data(**_history_kwargs(widget_cls, bad))
        await pilot.pause()
        assert app._exception is None, (
            f"{widget_cls.__name__} died in the message pump on {bad!r}: "
            f"{app._exception!r}"
        )
        # The panel is still composited -- not a blank hole in the layout.
        strips = app.screen._compositor.render_strips()
        assert strips


@pytest.mark.parametrize("widget_cls", SPARKLINE_WIDGETS, ids=lambda c: c.__name__)
async def test_widget_renders_a_clean_history(widget_cls) -> None:
    """The hardening did not cost the happy path: bars reach the screen."""
    good = [(float(i), float(i * i)) for i in range(1, 12)]
    widget = widget_cls()
    app = _Harness(widget)
    async with app.run_test() as pilot:
        widget.update_data(**_history_kwargs(widget_cls, good))
        await pilot.pause()
        assert app._exception is None
        rendered = "\n".join(
            "".join(seg.text for seg in strip)
            for strip in app.screen._compositor.render_strips()
        )
        assert any(ch in rendered for ch in sparkline_common.SPARK_CHARS), (
            f"{widget_cls.__name__} drew no sparkline for a clean series; "
            f"got: {rendered!r}"
        )
