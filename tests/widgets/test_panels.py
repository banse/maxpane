"""The shared panel bases (``widgets/panels.py``) and ocm as their first user.

Branch 6 of the refactor programme. ``widgets/panels.py`` hoists the four
panel shapes every dashboard had hand-copied -- a titled panel, a hero row,
a signals panel, a sparkline panel and a ``RichLog`` feed -- plus the two
strings (``UNAVAILABLE``, ``LOADING``) that had nine and sixty-eight copies.

**Composited, under the real app stylesheet.** ``minimal.tcss`` outranks a
widget's ``DEFAULT_CSS``, so a convention stated in only one of the two
renders differently in the app than in a bare mount; ``composite_lines``
with ``css_path=CSS_PATH`` is the harness ``test_title_blank_row.py``
already uses for exactly that reason. It is the shared helper: it is not
copied here.

**Two-poll claims.** "a malformed poll after a good one", "an empty poll
after a populated one" and "the placeholder is written once, not once per
poll" are claims about a *sequence*, and the shared helper calls
``update_data`` once. Each double below therefore mixes in ``_Replay``:
``update_data(polls=[{...}, {...}])`` applies each poll in order inside the
one mount, so the sequence is composited through the same helper rather
than through a second copy of the strip join. The one claim that is not
about pixels at all -- that a poll with nothing new does not ``clear()``
the log, ocm's flicker guard -- mounts the widget itself and spies on the
log.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import RichLog, Static

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.widgets import panels
from maxpane_dashboard.widgets.panels import (
    LOADING,
    UNAVAILABLE,
    HeroBox,
    HeroRow,
    PanelBase,
    RichLogFeed,
    SignalsPanel,
    SparklinePanel,
    fmt_signal,
)
from maxpane_dashboard.widgets.sparkline_common import SPARK_CHARS, fmt_compact

from tests.widgets.surf_compositing import composite_lines

_SIZE = (80, 20)


class _Replay:
    """``update_data(polls=[...])`` applies each poll in order.

    The one shared compositing helper calls ``update_data`` once, and three
    of the claims below are about what a *second* poll does to what the
    first one painted. Replaying inside the widget keeps those claims on
    the shared helper instead of on a hand-rolled second copy of it.
    """

    def update_data(self, polls=None, **kwargs) -> None:
        for poll in (polls if polls is not None else [kwargs]):
            self._poll(**poll)


async def _lines(cls, **payload) -> list[str]:
    return await composite_lines(
        cls, _SIZE, css_path=CSS_PATH, region_only=True, **payload
    )


async def _text(cls, **payload) -> str:
    return "\n".join(await _lines(cls, **payload))


# -- 1. PanelBase -----------------------------------------------------------


class _Panel(_Replay, PanelBase):
    TITLE = "TEST PANEL"

    def compose_body(self) -> ComposeResult:
        yield Static("", classes="panel-line", id="t-body")

    def _poll(self, body: str = "body text") -> None:
        self.write("#t-body", body)


async def test_panel_base_paints_title_blank_row_then_body() -> None:
    """Row 0 title, row 1 blank, row 2 body -- and the blank row is the base's.

    Mutation that reddens this: delete ``margin: 0 0 1 0`` from
    ``PanelBase.DEFAULT_CSS``. That margin is the *only* source of the row
    once the five per-panel ``OCM* > .<x>-title`` rules are gone from
    ``minimal.tcss``, so nothing else can paint it back.
    """
    rows = await _lines(_Panel)

    assert rows[0].strip() == "TEST PANEL"
    assert not rows[1].strip(), f"no blank row under the title: {rows[:4]}"
    assert rows[2].strip() == "body text", rows[:4]


async def test_panel_base_write_reports_a_missing_widget_instead_of_raising() -> None:
    """``write`` is the guard: a selector that matches nothing returns ``False``."""

    class _Probe(_Panel):
        def _poll(self, body: str = "body text") -> None:
            # Recorded on the widget so the claim is about the real mount.
            self.hit = self.write("#t-nothing-here", body)

    class _A(App):
        def compose(self):
            yield _Probe()

    async with _A().run_test(size=_SIZE) as pilot:
        probe = pilot.app.query_one(_Probe)
        probe.update_data()
        await pilot.pause()
        assert probe.hit is False
        assert probe.write("#t-body", "ok") is True


# -- 2. HeroRow -------------------------------------------------------------


class _TestHeroBox(HeroBox):
    pass


class _Hero(_Replay, HeroRow):
    BOX_CLASS = _TestHeroBox
    BOXES = (("t-hero-a", "ALPHA"), ("t-hero-b", "BETA"))

    def _poll(self, alpha=None, beta=None) -> None:
        self.render_box("#t-hero-a", "ALPHA", lambda: _alpha_body(alpha))
        self.render_box("#t-hero-b", "BETA", lambda: f"{beta:,}")


def _alpha_body(alpha) -> str:
    """A real ``0`` is a number; only a failed read says unavailable."""
    if alpha is None:
        return UNAVAILABLE
    return f"{alpha:,}"


async def test_hero_box_renders_unavailable_for_a_failed_read() -> None:
    text = await _text(_Hero, alpha=None, beta=None)
    assert "unavailable" in text, text
    assert "Loading" not in text, text


async def test_hero_box_renders_a_real_zero_as_a_number() -> None:
    text = await _text(_Hero, alpha=0, beta=0)
    assert "unavailable" not in text, text
    assert "Loading" not in text, text
    assert "0" in text, text


async def test_hero_box_malformed_poll_after_a_good_one_is_not_shown_as_live() -> None:
    """``beta="lots"`` raises inside ``f"{beta:,}"``, which is the point:
    the build happens inside the guard, so the box lands on ``unavailable``
    rather than the previous poll's number staying on screen as if live."""
    text = await _text(
        _Hero, polls=[{"alpha": 1234, "beta": 4321}, {"alpha": 1234, "beta": "lots"}]
    )
    assert "unavailable" in text, text
    assert "4,321" not in text, text
    assert "1,234" in text, text


# -- 3. SignalsPanel --------------------------------------------------------


_SIG = {"label": "Staking Rate", "value_str": "42%", "color": "green",
        "indicator": "●"}


def test_fmt_signal_at_width_18_plain() -> None:
    """ocm's and dota's spelling, hand-typed rather than derived."""
    assert fmt_signal(_SIG, label_width=18, dim_label=False) == (
        "  [green]●[/] Staking Rate       [green]42%[/]"
    )


def test_fmt_signal_at_width_15_dim() -> None:
    """cattown's and the template's spelling (Branch 7's subscriber)."""
    assert fmt_signal(_SIG, label_width=15, dim_label=True) == (
        "  [green]●[/] [dim]Staking Rate   [/] [green]42%[/]"
    )


class _Signals(_Replay, SignalsPanel):
    TITLE = "SIGNALS"
    ROWS = (("t-sig-a", "Alpha Rate"), ("t-sig-b", "Beta Rate"))
    RECOMMENDATION_ID = "t-sig-rec"

    def _poll(self, alpha=None, beta=None, recommendation="") -> None:
        self.render_signal("#t-sig-a", "Alpha Rate", alpha)
        self.render_signal("#t-sig-b", "Beta Rate", beta)
        self.render_recommendation(recommendation)


@pytest.mark.parametrize(
    "alpha", [None, {}, "not a dict"], ids=["none", "empty-dict", "not-a-dict"]
)
async def test_render_signal_says_unavailable_for_a_signal_it_could_not_read(
    alpha,
) -> None:
    text = await _text(_Signals, alpha=alpha)
    assert "Alpha Rate" in text, text
    assert "unavailable" in text, text


async def test_render_signal_lands_on_the_fallback_row_for_a_malformed_dict() -> None:
    """``{"label": object()}`` raises inside the format; the panel must not."""
    text = await _text(_Signals, alpha={"label": object()}, beta=_SIG)
    assert "unavailable" in text, text
    assert "Alpha Rate" in text, text
    # The sibling row still rendered: one malformed signal is one row.
    assert "42%" in text, text


async def test_render_recommendation_is_blank_for_an_empty_string() -> None:
    blank = await _text(_Signals, alpha=_SIG, beta=_SIG, recommendation="")
    assert "->" not in blank, blank
    filled = await _text(_Signals, alpha=_SIG, beta=_SIG, recommendation="stake now")
    assert "-> stake now" in filled, filled


# -- 4. SparklinePanel ------------------------------------------------------


class _Sparks(_Replay, SparklinePanel):
    TITLE = "TRENDS"
    LINE_IDS = ("t-spark-0",)

    def _poll(self, label="Supply", points=None, unit="") -> None:
        self.render_series([(label, points, "green", unit)])


_SERIES = [(1_700_000_000.0, 1_000.0), (1_700_003_600.0, 2_000.0)]


@pytest.mark.parametrize(
    "points",
    [None, [], [(1.0,)], [(1.0, None), (2.0, None)]],
    ids=["none", "empty", "ragged", "none-valued"],
)
async def test_render_series_writes_nothing_for_an_unusable_series(points) -> None:
    rows = await _lines(_Sparks, points=points)
    body = "\n".join(rows[2:])
    assert not body.strip(), rows[:5]


async def test_render_series_draws_the_sparkline_value_and_arrow() -> None:
    rows = await _lines(_Sparks, points=_SERIES)
    line = rows[2]
    assert any(ch in line for ch in SPARK_CHARS), line
    assert fmt_compact(2_000.0) in line, line
    assert "▲" in line, line


async def test_render_series_pads_the_label_to_eight_cells() -> None:
    """The leading space is ``.panel-line``'s own ``padding: 0 1``; the two
    after it are the row format's, and the label occupies exactly eight
    cells whether it is shorter or longer than that."""
    short = await _lines(_Sparks, label="Supply", points=_SERIES)
    assert short[2].startswith("   Supply    "), repr(short[2])
    long = await _lines(_Sparks, label="VeryLongLabelHere", points=_SERIES)
    assert long[2].startswith("   VeryLong  "), repr(long[2])


@pytest.mark.parametrize("value", [1, 1_000, 1_000_000])
def test_fmt_compact_matches_the_ocm_formatter_it_replaces(value) -> None:
    """The hoist's one behaviour change, stated rather than assumed.

    ``sparkline_common.fmt_compact`` replaces ocm's ``_fmt_value``. The two
    agree on every magnitude an ocm series can carry (a supply capped at
    10K, an $OCMD supply in the millions), which is why the pre/post render
    of the dashboard cannot see the swap. They differ at and above 1e9
    (``fmt_compact`` gains a ``B`` suffix), on the sign of a negative
    (``fmt_compact`` buckets on ``abs``), and on non-numeric input
    (``fmt_compact`` returns ``--`` where ``_fmt_value`` raised).
    """
    def _ocm_fmt_value(v: float, unit: str = "") -> str:
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M{unit}"
        elif v >= 1_000:
            return f"{v / 1_000:.1f}K{unit}"
        elif v >= 1:
            return f"{v:.1f}{unit}"
        return f"{v:.0f}{unit}"

    assert fmt_compact(value) == _ocm_fmt_value(value)


def test_fmt_compact_diverges_above_a_billion_and_on_junk() -> None:
    assert fmt_compact(2_000_000_000) == "2.0B"
    assert fmt_compact("junk") == "--"
    assert fmt_compact(None) == "--"


# -- 5. RichLogFeed ---------------------------------------------------------


def _ev(n: int, bad: bool = False) -> dict:
    return {"tx_hash": f"0x{n:064x}", "n": n, "bad": bad}


class _Feed(_Replay, RichLogFeed):
    TITLE = "ACTIVITY"
    LOG_ID = "t-feed-log"

    def format_row(self, event: dict) -> Text:
        if event.get("bad"):
            raise ValueError("unwritable row")
        return Text(f"event {event['n']}")

    def _poll(self, events=None) -> None:
        self.render_events(events)


async def test_the_placeholder_is_written_once_across_three_empty_polls() -> None:
    """Mutation that reddens this: delete the ``clear()`` before the
    placeholder. Without it every empty poll appends another copy, once per
    refresh interval -- the defect ocm carried and the template had fixed."""
    rows = await _lines(_Feed, polls=[{}, {}, {}])
    shown = [r for r in rows if "No activity yet" in r]
    assert len(shown) == 1, rows[:8]


async def test_a_populated_feed_survives_a_later_empty_poll() -> None:
    text = await _text(_Feed, polls=[{"events": [_ev(1)]}, {"events": []}])
    assert "event 1" in text, text
    assert "No activity yet" not in text, text


async def test_a_poll_with_nothing_new_does_not_clear_the_log() -> None:
    """ocm's flicker guard: repeating the same ``tx_hash`` rewrites nothing,
    and the key is recorded once."""
    feed = _Feed()

    class _A(App):
        def compose(self):
            yield feed

    async with _A().run_test(size=_SIZE) as pilot:
        feed.update_data(events=[_ev(1)])
        await pilot.pause()
        log = feed.query_one(f"#{_Feed.LOG_ID}", RichLog)
        assert feed._seen_keys == {_ev(1)["tx_hash"]}

        cleared: list[int] = []
        real_clear = log.clear
        log.clear = lambda *a, **k: (cleared.append(1), real_clear(*a, **k))[1]

        feed.update_data(events=[_ev(1)])
        await pilot.pause()

        assert cleared == [], "a poll with nothing new rewrote the log"
        assert feed._seen_keys == {_ev(1)["tx_hash"]}, feed._seen_keys


async def test_one_unwritable_row_is_skipped_and_the_others_land() -> None:
    """Mutation that reddens this: drop the per-row ``try`` in
    ``render_events``. The exception then escapes after ``log.clear()`` and
    the feed is left empty -- worse than the one row it could not draw."""
    text = await _text(_Feed, events=[_ev(1), _ev(2, bad=True), _ev(3)])
    assert "event 1" in text, text
    assert "event 3" in text, text
    assert "event 2" not in text, text
    assert "No activity yet" not in text, text


async def test_every_row_unwritable_falls_back_to_the_empty_line() -> None:
    text = await _text(_Feed, events=[_ev(1, bad=True), _ev(2, bad=True)])
    assert "No activity yet" in text, text


async def test_the_feed_keeps_the_order_it_was_given_newest_on_top() -> None:
    rows = await _lines(_Feed, events=[_ev(3), _ev(2), _ev(1)])
    body = [r.strip() for r in rows if r.strip().startswith("event ")]
    assert body == ["event 3", "event 2", "event 1"], rows[:8]


async def test_a_format_row_returning_none_is_skipped_not_written() -> None:
    class _NoneFeed(_Feed):
        def format_row(self, event: dict):
            return None if event["n"] == 2 else Text(f"event {event['n']}")

    rows = await _lines(_NoneFeed, events=[_ev(1), _ev(2)])
    body = [r.strip() for r in rows if r.strip().startswith("event ")]
    assert body == ["event 1"], rows[:8]


# -- 6. Agreement: ocm carries no copy of what the bases now own -------------


_OCM_DIR = pathlib.Path(
    inspect.getfile(__import__("maxpane_dashboard.widgets.ocm", fromlist=["x"]))
).parent

#: Each name had between three and ten copies across ``widgets/`` before this
#: branch. Paste one back into the ocm package and this test reddens.
_BANNED = frozenset({
    "_UNAVAILABLE",
    "_render_row",
    "_render_box",
    "_fmt",
    "_fmt_value",
    "_fmt_signal",
    "_format_event_time",
    "_seen_tx_hashes",
})

_PANEL_BASES = (PanelBase, HeroRow)


def _bound_names(tree: ast.AST) -> set[str]:
    """Every name this module *binds* -- a docstring naming one is not a copy."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            names.add(node.attr)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
            names.add(node.target.attr)
    return names


@pytest.mark.parametrize(
    "path", sorted(_OCM_DIR.glob("*.py")), ids=lambda p: p.name
)
def test_no_ocm_module_redeclares_what_panels_py_owns(path) -> None:
    bound = _bound_names(ast.parse(path.read_text()))
    assert not (bound & _BANNED), (
        f"{path.name} re-declares {sorted(bound & _BANNED)} -- "
        "widgets/panels.py owns these now"
    )


def test_every_ocm_panel_subclasses_a_panels_base() -> None:
    import maxpane_dashboard.widgets.ocm as ocm_pkg

    found = []
    for name in ocm_pkg.__all__:
        cls = getattr(ocm_pkg, name)
        if not hasattr(cls, "update_data"):
            continue
        found.append(name)
        assert issubclass(cls, _PANEL_BASES), f"{name} is not on widgets/panels.py"
    assert len(found) == 6, found


def test_panels_defines_the_two_strings_exactly_once() -> None:
    assert UNAVAILABLE == "[yellow]unavailable[/]"
    assert LOADING == "[dim]Loading...[/]"
    assert panels.__all__ == [
        "UNAVAILABLE",
        "LOADING",
        "PanelBase",
        "HeroBox",
        "HeroRow",
        "SignalsPanel",
        "SparklinePanel",
        "RichLogFeed",
        "fmt_signal",
    ]
