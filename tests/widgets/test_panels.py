"""The shared panel bases (``widgets/panels.py``) and their subscribers.

Branch 6 of the refactor programme. ``widgets/panels.py`` hoists the four
panel shapes every dashboard had hand-copied -- a titled panel, a hero row,
a signals panel, a sparkline panel and a ``RichLog`` feed -- plus the two
strings (``UNAVAILABLE``, ``LOADING``) that had nine and sixty-eight copies.

Branch 7 WP-A added the sixth shape, :class:`TableLeaderboard` (eight
hand-written copies of one title-over-a-``DataTable``), and widened three of
the bases for cattown and dota: the ``Text`` branch of ``render_box``,
label-less and separator signal rows, and ``SparklinePanel``'s
``LABEL_WIDTH`` / ``SHOW_ARROW`` / ``EMPTY_TEXT`` / ``fmt_value``. **Every
widening is a class attribute carrying the Branch 6 default**, which is why
the Branch 6 cases below are unchanged rather than re-tuned: if one of them
had to move, the widening was not additive.

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
import importlib
import inspect
import logging
import pathlib
import pkgutil
import re

import pytest
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import DataTable, RichLog, Static

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.widgets import panels
from maxpane_dashboard.widgets.panels import (
    LOADING,
    LOADING_ROW,
    UNAVAILABLE,
    UNAVAILABLE_LINE,
    HeroBoxBase,
    HeroRow,
    PanelBase,
    RichLogFeed,
    SignalsPanelBase,
    SparklinePanel,
    TableLeaderboard,
    fmt_signal,
    fmt_signal_trailing,
)
from maxpane_dashboard.widgets.sparkline_common import (
    SPARK_CHARS,
    SPARK_WIDTH,
    fmt_compact,
)

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


async def test_panel_base_write_logs_a_warning_when_it_cannot_write(caplog) -> None:
    """A degraded step gets a line in ``~/.maxpane/maxpane.log`` (fix round 1, M2).

    Before Branch 6 ocm's staking overview and supply breakdown wrote with a
    bare ``query_one(...).update(...)``, so a missing target raised into
    ``DashboardScreen._do_refresh`` and was logged at ``warning``. ``write``
    swallows it; swallowing it *silently* would make a panel that cannot
    render invisible in the one place it would ever be noticed.
    """

    class _A(App):
        def compose(self):
            yield _Panel()

    async with _A().run_test(size=_SIZE) as pilot:
        panel = pilot.app.query_one(_Panel)
        with caplog.at_level(
            logging.WARNING, logger="maxpane_dashboard.widgets.panels"
        ):
            assert panel.write("#t-nothing-here", "x") is False
        messages = [r.getMessage() for r in caplog.records
                    if r.levelno == logging.WARNING]
        assert any("t-nothing-here" in m and "_Panel" in m for m in messages), messages


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


class HeroBoxDouble(HeroBoxBase):
    """A hero box that states its own width, as every real one does.

    ``HeroBoxBase`` deliberately states no geometry -- a base class's name is
    a CSS type selector for every subclass, so a width there would reach
    every dashboard -- and ``minimal.tcss`` gives each dashboard's **own**
    box class ``width: 1fr`` (``OCMHeroBox``). Without a width the first box
    takes the whole row and the second never reaches the compositor (the
    ``test_cattown_talismans_address_icons.py`` precedent the MEDI-38
    harness cites).

    These three claims were silently borrowing that width from bakery's bare
    ``HeroBox { width: 1fr }`` block in ``minimal.tcss`` until fix round 1
    renamed the base out of that collision (I1) -- the collision itself,
    demonstrated. Not named ``_TestHeroBox``: a leading underscore is not a
    CSS identifier, and ``Test…`` is what pytest collects.
    """

    DEFAULT_CSS = """
    HeroBoxDouble {
        width: 1fr;
    }
    """


class _Hero(_Replay, HeroRow):
    BOX_CLASS = HeroBoxDouble
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


#: A click action of the shape ``widgets/address.py`` writes onto the copy
#: icon's own span. Nothing here calls the real action; what is being tested
#: is that the ``meta`` survives from ``build()`` to the pixel.
_CLICK = "app.copy_address('0xfeed')"


class _TextHero(_Replay, HeroRow):
    """A hero row whose box body is a ``Text``, not a markup string."""

    BOX_CLASS = HeroBoxDouble
    BOXES = (("t-text-box", "GAMMA"),)

    def _poll(self, word: str = "clickme") -> None:
        body = Text()
        body.append(word, style=Style(color="green", bold=True,
                                      meta={"@click": _CLICK}))
        self.render_box("#t-text-box", "GAMMA", lambda: body)


async def test_render_box_with_a_text_body_keeps_its_spans_to_the_pixel() -> None:
    """Branch 7: cattown's LEADER box is an address, and an address is a
    ``Text`` whose copy icon lives in a ``Style`` with a click ``meta``.

    Interpolating that body into ``f"[dim]{label}[/]\\n\\n{body}"`` -- which
    is what the ``str`` path does and what every hero row did before -- calls
    ``Text.__str__`` and flattens the style away, leaving an icon that looks
    right and copies nothing. The branch builds the head with
    ``Text.from_markup`` and **adds** the body instead.

    The claim is read off the compositor at the cell, the same way
    ``tests/widgets/address_probe.icon_targets`` reads a real icon: the
    ``meta`` is on screen, not merely on the object.
    """

    class _A(App):
        CSS_PATH = CSS_PATH

        def compose(self):
            yield _TextHero()

    async with _A().run_test(size=_SIZE) as pilot:
        hero = pilot.app.query_one(_TextHero)
        hero.update_data(word="clickme")
        await pilot.pause()

        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]

        # The label row is still above the body, with its blank row between.
        label_y = next(y for y, row in enumerate(rows) if "GAMMA" in row)
        body_y = next(y for y, row in enumerate(rows) if "clickme" in row)
        assert body_y == label_y + 2, rows[label_y:body_y + 1]

        # And the body's click meta reached the cell.
        x = rows[body_y].index("clickme")
        meta = pilot.app.screen.get_style_at(x, body_y).meta or {}
        assert meta.get("@click") == _CLICK, meta


async def test_render_box_with_a_text_body_still_degrades_on_a_raise() -> None:
    """The ``Text`` branch did not open a hole in the MEDI-38 guard."""

    class _Boom(_TextHero):
        def _poll(self, word: str = "clickme") -> None:
            def build():
                raise ValueError("no body")
            self.render_box("#t-text-box", "GAMMA", build)

    text = await _text(_Boom)
    assert "unavailable" in text, text
    assert "GAMMA" in text, text


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


class _Signals(_Replay, SignalsPanelBase):
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


async def test_a_hostile_recommendation_reaches_the_screen_as_text(
) -> None:
    """Review M5. ``analytics/dota_signals.py`` puts the game API's
    ``winner`` into the recommendation, and cattown's names a species, so
    the string that reaches this line is third-party.

    ``Static.update`` defers the markup parse into Textual's message pump,
    which is **outside** every ``try`` this widget has: an unescaped
    ``[/x]`` would take the app down rather than degrade a row. Composited,
    because the point is what a reader sees.

    Mutation that reddens this: drop the ``safe_markup`` call in
    ``render_recommendation``.
    """
    text = await _text(
        _Signals, alpha=_SIG, beta=_SIG, recommendation="push [/x] lane"
    )
    assert "push [/x] lane" in text, text


def test_fmt_signal_label_less() -> None:
    """talismans' and ttt's spelling (Branch 7): the value names itself.

    The label column is not blanked, it is **absent** -- a run of spaces
    where a label used to be would look like a cell the panel failed to
    fill.
    """
    assert fmt_signal(_SIG, label_width=18, dim_label=False, labelled=False) == (
        "  [green]●[/] [green]42%[/]"
    )
    # The width and dim flag are inert on this path, so a panel that sets
    # them and then goes label-less cannot drift.
    assert fmt_signal(_SIG, label_width=4, dim_label=True, labelled=False) == (
        "  [green]●[/] [green]42%[/]"
    )


def test_fmt_signal_escapes_a_hostile_value_str() -> None:
    """Branch 7 change 3. ttt escaped here, talismans did not, and a signal
    value can carry a token symbol -- anyone can deploy an ERC-20 named
    ``[/x]``.

    Mutation that reddens this: drop the ``safe_markup`` call in
    ``fmt_signal`` (``value = sig.get("value_str", "")``).
    """
    out = fmt_signal(
        {"label": "Sym", "value_str": "[red]x", "color": "green"},
        label_width=5, dim_label=False,
    )
    assert "\\[red]x" in out, out
    assert "[red]x" not in out.replace("\\[red]x", ""), out


class _HostileSignals(_Signals):
    """The same claim at the pixel: a hostile value renders literally."""

    def _poll(self, alpha=None, beta=None, recommendation="") -> None:
        self.render_signal("#t-sig-a", "Alpha Rate", alpha)


async def test_a_hostile_value_str_reaches_the_screen_as_text_not_markup() -> None:
    """Textual defers ``Text.from_markup`` into the message pump, so an
    unescaped ``[/x]`` raises *outside* the panel's guard and kills the app.
    Composited, so the claim is what a reader sees.
    """
    text = await _text(
        _HostileSignals,
        alpha={"label": "Sym", "value_str": "[/x] drained", "color": "green"},
    )
    assert "[/x] drained" in text, text


class _MixedSignals(_Replay, SignalsPanelBase):
    """A label-less row and a ``None`` separator, the talismans/ttt shape."""

    TITLE = "SIGNALS"
    ROWS = (
        ("t-mix-a", "Alpha Rate"),
        None,
        ("t-mix-b", None),
    )

    def _poll(self, alpha=None, beta=None) -> None:
        self.render_signal("#t-mix-a", "Alpha Rate", alpha)
        self.render_signal("#t-mix-b", "Beta Rate", beta, labelled=False)


async def test_a_none_rows_item_paints_a_separator_between_the_rows() -> None:
    """Row 0 title, 1 the base's blank row, 2 the labelled row, 3 the
    separator, 4 the label-less row -- and the label is gone from row 4, not
    merely blanked."""
    rows = await _lines(
        _MixedSignals,
        alpha=_SIG,
        beta={"label": "Beta Rate", "value_str": "7 open", "color": "cyan"},
    )
    assert rows[0].strip() == "SIGNALS", rows[:6]
    assert not rows[1].strip(), rows[:6]
    assert "Staking Rate" in rows[2] and "42%" in rows[2], rows[:6]
    assert not rows[3].strip(), rows[:6]
    assert "7 open" in rows[4], rows[:6]
    assert "Beta Rate" not in rows[4], rows[:6]
    # Two spaces of padding, the indicator, one space, then the value: no
    # label column was reserved and left empty.
    assert rows[4].strip().startswith("● 7 open"), repr(rows[4])


async def test_the_seed_row_lands_on_the_first_row_not_the_first_item() -> None:
    """``ROWS`` may open with anything; the ``Loading...`` seed belongs to
    the first row that has an id, or a panel whose ``ROWS`` began with a
    separator would seed nothing at all."""

    class _LeadingSeparator(_MixedSignals):
        ROWS = (None, ("t-mix-a", "Alpha Rate"), ("t-mix-b", None))

        def _poll(self, alpha=None, beta=None) -> None:
            return

    rows = await _lines(_LeadingSeparator, polls=[])
    assert not rows[2].strip(), rows[:6]
    assert rows[3].strip() == "Loading...", rows[:6]


async def test_a_label_less_row_that_could_not_be_read_still_says_so() -> None:
    """MEDI-38 does not lapse because the row has no label column."""
    rows = await _lines(_MixedSignals, alpha=_SIG, beta=None)
    assert "unavailable" in rows[4], rows[:6]
    assert "Beta Rate" not in rows[4], rows[:6]


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


#: The talismans/ttt spelling of a sparkline panel (Branch 7): a wider label
#: column, no trend arrow, and a *worded* empty state. Every one of the three
#: is a class attribute whose default is Branch 6's, so ``_Sparks`` above --
#: which sets none of them -- still renders exactly as it did.
class _WideSparks(_Sparks):
    LINE_IDS = ("t-wspark-0",)
    LABEL_WIDTH = 12
    SHOW_ARROW = False
    EMPTY_TEXT = "[dim]waiting for data...[/]"

    def fmt_value(self, value, unit: str) -> str:
        return f"{int(value):,}{unit}"

    def _poll(self, label="Supply", points=None, unit="") -> None:
        self.render_series([(label, points, "green", unit)])


async def test_the_label_column_widens_to_label_width() -> None:
    """Twelve cells, not eight: ``VeryLongLabe`` is clipped at 12 and
    ``Supply`` is padded to 12, both measured from the ``.panel-line``
    padding the default case measures from."""
    short = await _lines(_WideSparks, label="Supply", points=_SERIES)
    assert short[2].startswith("   Supply        "), repr(short[2])
    long = await _lines(_WideSparks, label="VeryLongLabelHere", points=_SERIES)
    assert long[2].startswith("   VeryLongLabe  "), repr(long[2])


async def test_show_arrow_false_draws_no_arrow_and_no_trailing_space() -> None:
    """talismans and ttt draw none. The arrow *and* the space before it go:
    a value cell that ends in a space is a cell the panel padded for
    something it then did not draw."""
    rows = await _lines(_WideSparks, points=_SERIES)
    assert not any(ch in rows[2] for ch in "▲▼▬"), repr(rows[2])
    assert rows[2] == rows[2].rstrip(), repr(rows[2])
    # The default still draws it, so the attribute is the only difference.
    default = await _lines(_Sparks, points=_SERIES)
    assert "▲" in default[2], repr(default[2])


async def test_fmt_value_override_is_what_reaches_the_cell() -> None:
    """dota's frontline formatter, talismans' grouped integers and ttt's
    ``$…B`` differ from ``fmt_compact`` on values their own panels show, so
    the hook -- not a hoist -- is what keeps their digits."""
    rows = await _lines(_WideSparks, points=_SERIES)
    assert "2,000" in rows[2], repr(rows[2])
    assert fmt_compact(2_000.0) not in rows[2], repr(rows[2])


@pytest.mark.parametrize(
    "points", [None, [], [(1.0,)]], ids=["none", "empty", "ragged"]
)
async def test_empty_text_is_what_an_unusable_series_writes(points) -> None:
    """``""`` is a default, not the contract: a panel that words its empty
    state writes the words, and never a flat baseline either way."""
    rows = await _lines(_WideSparks, points=points)
    assert rows[2].strip() == "waiting for data...", rows[:4]


async def test_the_first_line_is_seeded_with_empty_text_when_there_is_one() -> None:
    """A panel with an ``EMPTY_TEXT`` has one sentence for "nothing yet" and
    "nothing usable"; seeding ``Loading...`` under it would be a second word
    for one state."""

    class _Unpolled(_WideSparks):
        def _poll(self, label="Supply", points=None, unit="") -> None:
            return

    rows = await _lines(_Unpolled, polls=[])
    assert rows[2].strip() == "waiting for data...", rows[:4]
    # And the Branch 6 default is still `Loading...`.
    class _UnpolledDefault(_Sparks):
        def _poll(self, label="Supply", points=None, unit="") -> None:
            return

    rows = await _lines(_UnpolledDefault, polls=[])
    assert rows[2].strip() == "Loading...", rows[:4]


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
    """The keyed path: ``dedupe_key`` returns a hashable ``tx_hash``, so
    ``_seen_keys`` fills. This case passed even while the contract read the
    key set -- which is why the two key-less cases below exist."""
    text = await _text(_Feed, polls=[{"events": [_ev(1)]}, {"events": []}])
    assert "event 1" in text, text
    assert "No activity yet" not in text, text


async def test_a_key_less_feed_survives_a_later_empty_poll() -> None:
    """Fix round 2, N3. ``dedupe_key`` returning ``None`` is the documented
    "always new" mode (``panels.py``), and it never puts anything in
    ``_seen_keys``. While the empty-poll branch tested that set, a feed in
    this mode was wiped by the very next empty poll: live rows replaced with
    ``No activity yet`` -- a false degradation on screen. The contract now
    hangs off ``_drawn``.

    Mutation that reddens this: ``if not self._drawn`` -> ``if not
    self._seen_keys`` in the empty-poll branch.
    """

    class _KeyLessFeed(_Feed):
        def dedupe_key(self, event: dict):
            return None

    text = await _text(
        _KeyLessFeed, polls=[{"events": [_ev(1)]}, {"events": []}]
    )
    assert "event 1" in text, text
    assert "No activity yet" not in text, text


async def test_an_unhashable_key_feed_survives_a_later_empty_poll() -> None:
    """Fix round 2, N3, the second key-less path: M3 routes an unhashable
    ``tx_hash`` to "always new" without recording it, so the key set stays
    empty and the next empty poll used to clear the drawn rows."""
    unhashable = {"tx_hash": ["x"], "n": 9, "bad": False}
    text = await _text(_Feed, polls=[{"events": [unhashable]},
                                     {"events": []}])
    assert "event 9" in text, text
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


async def test_an_unhashable_dedupe_key_renders_instead_of_blanking_the_feed() -> None:
    """Fix round 1, M3. A third-party payload can hand us ``tx_hash: ["x"]``.

    ``key in self._seen_keys`` raised ``TypeError`` out of ``update_data``
    after the log was already cleared, so one malformed hash blanked the
    whole feed. An unhashable key cannot be deduped, so the event is always
    new and always drawn.
    """
    unhashable = {"tx_hash": ["x"], "n": 9, "bad": False}
    text = await _text(_Feed, polls=[{"events": [unhashable]},
                                     {"events": [unhashable]}])
    assert "event 9" in text, text
    assert "No activity yet" not in text, text


async def test_a_subclass_without_format_row_fails_loudly() -> None:
    """Fix round 1, M4. ``NotImplementedError`` is a programming error.

    Caught by the broad per-row guard it became "No activity yet" forever,
    which reads as a quiet feed rather than as a feed that was never wired
    up.
    """

    class _NoHook(RichLogFeed):
        TITLE = "ACTIVITY"
        LOG_ID = "t-nohook-log"

    class _A(App):
        def compose(self):
            yield _NoHook()

    async with _A().run_test(size=_SIZE) as pilot:
        feed = pilot.app.query_one(_NoHook)
        with pytest.raises(NotImplementedError):
            feed.render_events([{"tx_hash": "0x1"}])


# -- 5b. RichLogFeed snapshot mode (Branch 7 WP-A, fix round 1 -- review C1) --


class _Snapshot(_Feed):
    """A roster rather than a log: the whole state, every poll."""

    SNAPSHOT = True

    def dedupe_key(self, event: dict):
        return None


async def test_a_snapshot_feed_paints_unavailable_for_a_none_poll() -> None:
    """The finding itself. A drawn roster, then a **failed read**.

    Every row of a roster carries a number that is only true of the poll it
    came from -- dota's rows carry HP and ALIVE/DEAD. Keeping them through a
    read that never happened is "a stale number presented as live", which
    this repo treats as worse than an empty panel. ``None`` is the failed
    read and it says so.
    """
    text = await _text(_Snapshot, polls=[{"events": [_ev(1)]},
                                         {"events": None}])
    assert "unavailable" in text, text
    assert "event 1" not in text, text
    assert "No activity yet" not in text, text


async def test_a_snapshot_feed_paints_the_empty_line_for_an_empty_list() -> None:
    """The other half, and the reason the two inputs may not be merged: a
    read that succeeded and found nothing is a **real negative**, and it
    must be representable as something other than "could not look"."""
    text = await _text(_Snapshot, polls=[{"events": [_ev(1)]},
                                         {"events": []}])
    assert "No activity yet" in text, text
    assert "unavailable" not in text, text
    assert "event 1" not in text, text


async def test_a_snapshot_feed_with_no_showable_row_says_unavailable_not_empty() -> None:
    """Re-review N1. A drawn roster, then a poll whose rows arrived but none of
    which ``format_row`` can show. The read succeeded and returned a state,
    so "No activity yet" is a statement the panel cannot support -- it must
    say it could not *show* the state. A stream keeps its Branch 6 answer
    (``test_every_row_unwritable_falls_back_to_the_empty_line``); reverting
    the ``SNAPSHOT`` branch of the ``written == 0`` write reddens this test
    and only this test.
    """
    text = await _text(_Snapshot, polls=[{"events": [_ev(1)]},
                                         {"events": [_ev(2, bad=True),
                                                     _ev(3, bad=True)]}])
    assert "unavailable" in text, text
    assert "No activity yet" not in text, text
    assert "event 1" not in text, text


async def test_a_snapshot_feed_re_paints_a_roster_that_did_not_change() -> None:
    """No row survives a poll -- not even an identical one.

    The stream contract's flicker guard would leave the log untouched when
    nothing is new, which for a roster means the *same* rows staying up for
    a reason ("nothing new") that is indistinguishable from the panel having
    stopped updating. Snapshot mode skips the guard, so the log is cleared
    and re-painted every time.
    """
    feed = _Snapshot()

    class _A(App):
        def compose(self):
            yield feed

    async with _A().run_test(size=_SIZE) as pilot:
        feed.update_data(events=[_ev(1)])
        await pilot.pause()
        log = feed.query_one(f"#{_Snapshot.LOG_ID}", RichLog)

        cleared: list[int] = []
        real_clear = log.clear
        log.clear = lambda *a, **k: (cleared.append(1), real_clear(*a, **k))[1]

        feed.update_data(events=[_ev(1)])
        await pilot.pause()

        assert cleared == [1], "a snapshot poll did not re-paint"


async def test_a_stream_feed_keeps_the_rows_a_snapshot_would_drop() -> None:
    """The contrast, on one payload, so the split is visible in one place.

    ``_Feed`` is ``SNAPSHOT = False`` -- the Branch 6 contract, byte for
    byte -- and a stream is *right* to keep its rows: an event that happened
    is still true when the next poll brings nothing.
    """
    assert RichLogFeed.SNAPSHOT is False, "the default must stay stream"

    class _KeyLessStream(_Feed):
        def dedupe_key(self, event: dict):
            return None

    text = await _text(
        _KeyLessStream, polls=[{"events": [_ev(1)]}, {"events": None}]
    )
    assert "event 1" in text, text
    assert "unavailable" not in text, text


# -- 6. TableLeaderboard (Branch 7) ------------------------------------------


class _Table(_Replay, TableLeaderboard):
    """The eight tables' shared shape, at its smallest."""

    TITLE = "TABLE"
    TABLE_ID = "t-table"
    COLUMNS = (("#", 4), ("Name", 12))
    EMPTY_ROW = ("--", "No data")
    ROW_CAP = 3

    def build_row(self, index: int, item: dict):
        if item.get("skip"):
            return None
        if item.get("wide"):
            # One cell too many: ``DataTable.add_row`` raises, which is the
            # *add* failing rather than the build, so the per-row guard is
            # the only thing that can save the rows around it.
            return (str(index + 1), item["name"], "surplus")
        return (str(index + 1), item["name"])

    def _poll(self, rows=None, footer=None) -> None:
        self.render_table(rows, footer=footer)


def _item(name: str, **flags) -> dict:
    return {"name": name, **flags}


async def test_table_paints_title_blank_row_then_the_header() -> None:
    """Row 0 title, row 1 the base's blank row, row 2 the column header --
    the same three rows every other ``PanelBase`` paints, which is the point
    of putting the table on one."""
    rows = await _lines(_Table, rows=[_item("alpha")])
    assert rows[0].strip() == "TABLE", rows[:5]
    assert not rows[1].strip(), rows[:5]
    assert rows[2].split() == ["#", "Name"], rows[:5]
    assert rows[3].split() == ["1", "alpha"], rows[:5]


async def test_the_loading_seed_row_appears_only_when_loading_row_is_set() -> None:
    """Six of the eight tables seed one and two do not, and *which cell*
    says the word differs -- so the subclass types the whole tuple and the
    base never guesses a column."""

    class _Unpolled(_Table):
        def _poll(self, rows=None, footer=None) -> None:
            return

    bare = await _lines(_Unpolled, polls=[])
    assert not bare[3].strip(), bare[:5]

    class _Seeded(_Unpolled):
        LOADING_ROW = ("--", "Loading...")

    seeded = await _lines(_Seeded, polls=[])
    assert seeded[3].split() == ["--", "Loading..."], seeded[:5]


@pytest.mark.parametrize("payload", [None, []], ids=["none", "empty"])
async def test_an_empty_payload_paints_the_empty_row_exactly_once(payload) -> None:
    """Not a blank table, which reads as a panel that has not polled yet --
    and not one "No data" row per poll either."""
    rows = await _lines(_Table, polls=[{"rows": payload}] * 3)
    shown = [r for r in rows if "No data" in r]
    assert len(shown) == 1, rows[:8]
    assert shown[0].split() == ["--", "No", "data"], shown


async def test_row_cap_slices_the_payload() -> None:
    rows = await _lines(_Table, rows=[_item(n) for n in "abcde"])
    body = [r.split()[1] for r in rows[3:8] if r.strip()]
    assert body == ["a", "b", "c"], rows[:9]


async def test_an_uncapped_table_draws_every_row() -> None:
    """``ROW_CAP = None`` is the matrix table's spelling."""

    class _Uncapped(_Table):
        ROW_CAP = None

    rows = await _lines(_Uncapped, rows=[_item(n) for n in "abcde"])
    body = [r.split()[1] for r in rows[3:9] if r.strip()]
    assert body == ["a", "b", "c", "d", "e"], rows[:10]


async def test_build_row_returning_none_skips_and_the_index_is_the_slice_position() -> None:
    """The non-dict guard talismans and ttt carry.

    Two claims, and the second is the one the plan mis-stated (review M4):
    the skipped item leaves **no blank line** between the rows that did
    render, *and* ``index`` counts the position in the capped slice, not the
    number of rows drawn -- so the third item is still item 3 and prints
    rank ``3``. That is what ``tal_leaderboard.py`` does today and what the
    base must keep doing, because a subclass bolds on ``index == 0``.
    """
    rows = await _lines(
        _Table, rows=[_item("a"), _item("b", skip=True), _item("c")]
    )
    assert rows[3].split() == ["1", "a"], rows[:7]
    assert rows[4].split() == ["3", "c"], rows[:7]
    assert not rows[5].strip(), rows[:7]


async def test_one_unaddable_row_is_skipped_and_the_others_land() -> None:
    """Mutation that reddens this: delete the per-row ``try`` in
    ``render_table``. The exception then escapes after ``clear()`` and the
    table is left **empty** -- on a leaderboard that reads as "nobody is
    playing", which is worse than the one row it could not draw."""
    rows = await _lines(
        _Table, rows=[_item("a"), _item("b", wide=True), _item("c")]
    )
    body = [r.split()[1] for r in rows[3:7] if r.strip()]
    assert body == ["a", "c"], rows[:7]
    assert "No data" not in "\n".join(rows), rows[:7]


async def test_a_skipped_row_is_logged_at_warning(caplog) -> None:
    """Review M1. Skipping is right; skipping *silently* is not.

    ``PanelBase.write`` settled this in Branch 6: a degraded step is worth a
    line in ``~/.maxpane/maxpane.log``, because that log is the only place a
    row that never drew would ever be noticed. The line names the class and
    the row index, so the missing item can be found in the payload.
    """

    class _A(App):
        def compose(self):
            yield _Table()

    async with _A().run_test(size=_SIZE) as pilot:
        table = pilot.app.query_one(_Table)
        with caplog.at_level(
            logging.WARNING, logger="maxpane_dashboard.widgets.panels"
        ):
            table.render_table([_item("a"), _item("b", wide=True)])
            await pilot.pause()
        messages = [r.getMessage() for r in caplog.records
                    if r.levelno == logging.WARNING]
        assert any("_Table" in m and "row 1" in m for m in messages), messages


async def test_a_wrong_width_empty_row_fails_at_mount() -> None:
    """Review M2. ``EMPTY_ROW`` is added on the one path ``render_table``
    reaches when there is nothing else to show, so a wrong tuple breaks the
    **degraded** state -- the state nobody is watching when it happens. It
    is a programming error in the subclass, so it fails loudly at mount,
    naming the class, rather than painting an empty table in production.
    """

    class _BadEmpty(_Table):
        TABLE_ID = "t-bad-empty"
        EMPTY_ROW = ("--",)          # one cell, two columns

    class _A(App):
        def compose(self):
            yield _BadEmpty()

    with pytest.raises(TypeError, match="_BadEmpty.EMPTY_ROW"):
        async with _A().run_test(size=_SIZE):
            pass


async def test_a_wrong_width_loading_row_fails_at_mount() -> None:
    """The same check on the seed row. ``DataTable.add_row`` raises on a
    surplus cell but **pads a short one in silence**, so only half of this
    would ever have been noticed without the check."""

    class _BadLoading(_Table):
        TABLE_ID = "t-bad-loading"
        LOADING_ROW = ("--", "Loading...", "surplus")

    class _A(App):
        def compose(self):
            yield _BadLoading()

    with pytest.raises(TypeError, match="_BadLoading.LOADING_ROW"):
        async with _A().run_test(size=_SIZE):
            pass


async def test_correctly_sized_rows_mount_and_paint() -> None:
    """The other side of M2: the check must not fire on a table that is
    right, including one whose ``EMPTY_ROW`` is the default empty tuple."""

    class _NoEmpty(_Table):
        TABLE_ID = "t-no-empty"
        EMPTY_ROW = ()

    rows = await _lines(_NoEmpty, rows=[_item("a")])
    assert rows[3].split() == ["1", "a"], rows[:6]

    class _RightWidths(_Table):
        TABLE_ID = "t-right-widths"
        LOADING_ROW = ("--", "Loading...")

        def _poll(self, rows=None, footer=None) -> None:
            return

    seeded = await _lines(_RightWidths, polls=[])
    assert seeded[3].split() == ["--", "Loading..."], seeded[:6]


async def test_the_footer_row_lands_last() -> None:
    """The matrix table's bold TOTAL line, under the capped slice."""
    rows = await _lines(
        _Table, rows=[_item("a"), _item("b")], footer=("T", "total")
    )
    assert rows[3].split() == ["1", "a"], rows[:7]
    assert rows[4].split() == ["2", "b"], rows[:7]
    assert rows[5].split() == ["T", "total"], rows[:7]


async def test_a_subclass_without_build_row_fails_loudly() -> None:
    """As in ``RichLogFeed``: an unwired hook is a programming error and must
    not be swallowed into a table that silently draws nothing."""

    class _NoHook(TableLeaderboard):
        TITLE = "TABLE"
        TABLE_ID = "t-nohook-table"
        COLUMNS = (("#", 4),)

    class _A(App):
        def compose(self):
            yield _NoHook()

    async with _A().run_test(size=_SIZE) as pilot:
        table = pilot.app.query_one(_NoHook)
        with pytest.raises(NotImplementedError):
            table.render_table([{"name": "a"}])


async def test_the_table_keeps_its_columns_cursor_and_zebra() -> None:
    """All eight tables agreed on these three; the base states them once."""

    class _A(App):
        def compose(self):
            yield _Table()

    async with _A().run_test(size=_SIZE) as pilot:
        table = pilot.app.query_one(f"#{_Table.TABLE_ID}", DataTable)
        assert table.cursor_type == "row"
        assert table.zebra_stripes is True
        assert [str(c.label) for c in table.columns.values()] == ["#", "Name"]


# -- 6b. Branch 8 WP-A: the three append-only extensions ---------------------
#
# ``fmt_signal_trailing`` (the older signals row shape the base terminal and
# bakery share), ``SparklinePanel.SPARK_WIDTH`` and ``RichLogFeed.HEADER_LINE``.
# Each defaults to what every existing subscriber already had, so the cases
# above this section stay green unchanged -- and each case here names the
# mutation it exists to redden.


def test_fmt_signal_trailing_with_an_indicator_has_the_three_padded_cells() -> None:
    """Mutation: any of the three default widths (20 / 12 / 10) -> this
    reddens. Label padded to 20, value right-aligned in 12, the dot and the
    indicator padded to 10, exactly ``SignalsPanel._fmt_row``'s branch."""
    out = fmt_signal_trailing("Late-Join EV", "+$1.20", indicator="positive",
                              color="green")
    assert out == (
        "  [dim]Late-Join EV        [/]"
        "[bold white]      +$1.20[/]"
        "  [green]● positive  [/]"
    ), out


def test_fmt_signal_trailing_without_an_indicator_ends_after_the_value() -> None:
    """Mutation: append the dot when ``indicator is None`` -> this reddens.
    Bakery's branch for a signal with nothing to indicate."""
    out = fmt_signal_trailing("Dominance", "42%")
    assert out == "  [dim]Dominance           [/][bold white]         42%[/]", out
    assert "●" not in out


def test_fmt_signal_trailing_with_an_empty_indicator_is_the_dot_alone() -> None:
    """Mutation: pad the empty indicator out to ten cells (``● `` plus ten
    spaces) -> this reddens. The base terminal's rows colour the dot and say
    nothing after it; ten trailing cells would wrap at the pin width."""
    out = fmt_signal_trailing("Buy/Sell", "Bullish", indicator="", color="green")
    assert out.endswith("[/]  [green]●[/]"), out
    assert out == out.rstrip()


def test_fmt_signal_trailing_value_color_replaces_bold_white_and_nothing_else() -> None:
    """Mutation: ignore ``value_color``, or let it also recolour the label or
    the dot -> this reddens. Branch 8 WP-A fix round 1 (review M3): the
    degraded row's word is yellow like every other degraded signal row, and
    the default is the ``[bold white]`` every live row had."""
    live = fmt_signal_trailing("Sym", "ok", indicator="", color="green")
    degraded = fmt_signal_trailing("Sym", "unavailable", indicator="",
                                   color="yellow", value_color="yellow")
    assert "[bold white]" in live and "[bold white]" not in degraded, degraded
    assert degraded == (
        f"  [dim]{'Sym':<20}[/][yellow]{'unavailable':>12}[/]  [yellow]●[/]"
    ), degraded
    # The keyword touches the value cell only: label and dot as before.
    assert degraded.startswith(f"  [dim]{'Sym':<20}[/]"), degraded
    assert live.replace("[bold white]", "[yellow]").replace("[green]", "[yellow]") == (
        fmt_signal_trailing("Sym", "ok", indicator="", color="yellow", value_color="yellow")
    )


def test_fmt_signal_trailing_honours_the_three_width_keywords() -> None:
    """Mutation: ignore any of ``label_width`` / ``value_width`` /
    ``indicator_width`` -> this reddens."""
    out = fmt_signal_trailing("L", "v", indicator="i", label_width=3,
                              value_width=4, indicator_width=2)
    assert out == "  [dim]L  [/][bold white]   v[/]  [dim]● i [/]", out


def test_fmt_signal_trailing_escapes_a_hostile_value_and_keeps_its_width() -> None:
    """Mutation: drop either ``safe_markup`` call, or escape *before*
    padding -> this reddens. A value spelled ``[red]x`` renders literally
    and still occupies twelve cells: the escape's backslash is consumed by
    the parser, so the padding has to be applied to the raw string."""
    out = fmt_signal_trailing("Sym", "[red]x", indicator="[/x]", color="green")
    assert "\\[red]x" in out, out
    assert "\\[/x]" in out, out
    assert out.count("[red]x") == 1 and "[/x]" not in out.replace("\\[/x]", ""), out
    rendered = Text.from_markup(out).plain
    assert rendered == f"  {'Sym':<20}{'[red]x':>12}  ● {'[/x]':<10}", rendered


class _NarrowSparks(_Sparks):
    LINE_IDS = ("t-nspark-0",)
    SPARK_WIDTH = 20


async def test_spark_width_is_the_bars_cell_count() -> None:
    """Mutation: ``build_sparkline_from_points(pts)`` without
    ``width=self.SPARK_WIDTH`` -> this reddens. The base terminal draws 20,
    bakery's cookie chart 30, everyone else the shared 22 -- and the
    default is that 22, so ``_Sparks`` above still draws what it drew."""
    narrow = await _lines(_NarrowSparks, points=_SERIES)
    assert sum(ch in SPARK_CHARS for ch in narrow[2]) == 20, repr(narrow[2])
    default = await _lines(_Sparks, points=_SERIES)
    assert sum(ch in SPARK_CHARS for ch in default[2]) == SPARK_WIDTH == 22, (
        repr(default[2])
    )


class _HeadedFeed(_Feed):
    LOG_ID = "t-hfeed-log"
    HEADER_LINE = "[dim]  # header row[/]"


async def test_a_header_line_is_written_above_the_rows_on_every_paint() -> None:
    """Mutation: drop the ``HEADER_LINE`` write in ``render_events`` -> this
    reddens. Title, blank, header, then the rows; a second poll re-paints
    it once, never twice."""
    rows = await _lines(_HeadedFeed, polls=[
        {"events": [{"n": 1, "tx_hash": "a"}]},
        {"events": [{"n": 2, "tx_hash": "b"}]},
    ])
    assert rows[2].strip() == "# header row", rows[:6]
    assert "event" in rows[3], rows[:6]
    assert sum("# header row" in r for r in rows) == 1, rows[:8]


async def test_a_header_never_stands_over_an_empty_table() -> None:
    """Mutation: drop the ``clear()`` on the ``written == 0`` path -> this
    reddens. Rows arrived and none could be shown: the placeholder alone,
    no heading above nothing."""
    rows = await _lines(_HeadedFeed, events=[{"bad": True, "n": 0}])
    assert not any("# header row" in r for r in rows), rows[:6]
    assert rows[2].strip() == "No activity yet", rows[:6]


async def test_a_feed_without_a_header_line_writes_none() -> None:
    """The default. Mutation: seed ``HEADER_LINE`` with a string -> this
    reddens, and so does every pre-existing feed test above."""
    rows = await _lines(_Feed, events=[{"n": 1, "tx_hash": "a"}])
    assert rows[2].strip() == "event 1", rows[:6]


# -- 7. Agreement: the migrated packages carry no copy of what the bases own --


#: The dashboard packages that are on ``widgets/panels.py``, each mapped to
#: **how many** ``update_data`` widget classes the walk below must find.
#: **One table, one place**: Branch 7 WP-A added ``cattown`` and ``dota`` to
#: Branch 6's ``ocm``, and WP-B appended ``"talismans": 7`` and ``"ttt": 7``
#: -- two entries, no test body touched, because every claim below is
#: parametrised over this table.
#:
#: The count is not decoration and not derived from the package (deriving it
#: would compare ``__all__`` against itself and pass on a package whose
#: panels had all been deleted). It is the hand-checked number of panels,
#: and it reddens when one is dropped, renamed out of ``__all__``, or added
#: without being put on a base. It is **per package** because the packages
#: genuinely differ: talismans and ttt export seven each, the others six.
MIGRATED_PACKAGES = {
    "ocm": 6, "cattown": 6, "dota": 6, "talismans": 7, "ttt": 7,
    # Branch 8 WP-A. A dotted name: ``_package`` imports
    # ``maxpane_dashboard.widgets.base.overview`` and the walk globs its six
    # ``bt_*.py`` modules (``BTHeroBox`` has no ``update_data``, so the row
    # exports seven names and the count is six).
    "base.overview": 6,
}


def _package(name: str):
    return importlib.import_module(f"maxpane_dashboard.widgets.{name}")


def _package_modules(name: str) -> list[pathlib.Path]:
    return sorted(pathlib.Path(inspect.getfile(_package(name))).parent.glob("*.py"))


#: Each name had between two and ten copies across ``widgets/`` before this
#: programme. Paste one back into a migrated package and this test reddens.
#: ``_UNAVAILABLE_SIGNAL`` (talismans), ``_format_ts``, ``_fmt_int``,
#: ``_fmt_float``, ``_safe_get``, ``_DASH`` and ``_WAITING`` are listed for
#: WP-B, which hoists them; none of the three packages here defines one, so
#: listing them now costs nothing and stops one being re-introduced.
_BANNED = frozenset({
    "_UNAVAILABLE",
    "_UNAVAILABLE_SIGNAL",
    "_render_row",
    "_render_box",
    "_fmt",
    "_fmt_value",
    "_fmt_signal",
    "_format_event_time",
    "_format_ts",
    "_seen_tx_hashes",
    "_fmt_int",
    "_fmt_float",
    "_safe_get",
    "_DASH",
    "_WAITING",
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
    "path",
    [p for pkg in MIGRATED_PACKAGES for p in _package_modules(pkg)],
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_no_migrated_module_redeclares_what_panels_py_owns(path) -> None:
    bound = _bound_names(ast.parse(path.read_text(encoding="utf-8")))
    assert not (bound & _BANNED), (
        f"{path.parent.name}/{path.name} re-declares {sorted(bound & _BANNED)} "
        "-- widgets/panels.py owns these now"
    )


@pytest.mark.parametrize(
    "package,expected", sorted(MIGRATED_PACKAGES.items()), ids=lambda v: str(v)
)
def test_every_migrated_panel_subclasses_a_panels_base(package, expected) -> None:
    """Walk the package's own ``__all__``, so a widget added to a migrated
    package and *not* put on a base reddens this without anybody remembering
    to extend a hand-written list -- and check the walk found the number of
    panels that package actually has, so a dropped one reddens too."""
    pkg = _package(package)

    found = []
    for name in pkg.__all__:
        cls = getattr(pkg, name)
        if not hasattr(cls, "update_data"):
            continue
        found.append(name)
        assert issubclass(cls, _PANEL_BASES), (
            f"{package}.{name} is not on widgets/panels.py"
        )
    assert len(found) == expected, (package, found)


# The plan's fifth agreement clause ("no ``compose`` yields a ``Static``
# whose content is ``\"\"`` or ``\" \"``") is deliberately NOT written here as a
# source check: it is false as stated and the composited assertion is
# stronger. Three of the five migrated shapes yield a blank ``Static`` as
# *content* -- ``OCMSupplyBreakdown`` seeds three body lines empty and fills
# them on the first poll, ``SignalsPanelBase`` yields one before the
# recommendation, and both BEST PLAYS boards keep one between their headers
# and their rows -- so a ban would have to be narrowed to "the title's
# spacer", which no source check can tell from a seeded line. What made the
# old spacers wrong was the *row they painted*, and that is what
# ``tests/widgets/test_title_blank_row.py`` asserts, composited, for every
# panel in every migrated package: title row, exactly one blank, then
# content. A leftover spacer reddens it with two blanks -- and so does a
# spacer reached through a helper, or a regression in ``PanelBase``'s
# ``margin``, neither of which a source check would see.


def test_panels_defines_the_shared_strings_exactly_once() -> None:
    """Restored in fix round 1. This test was collateral of WP-A's own
    edit: the source slice that removed a rejected spacer check swallowed
    the function below it too, and nothing reddened, because a deleted test
    is the one defect a test suite cannot report. It is back, widened to
    :data:`UNAVAILABLE_LINE`, and every string it pins is pinned *and*
    derived, so a re-typed copy and a drifted derivation both redden."""
    assert UNAVAILABLE == "[yellow]unavailable[/]"
    assert LOADING == "[dim]Loading...[/]"
    # Derived from LOADING, not re-typed beside it: the signals seed is the
    # same words, two columns in (fix round 1, M1).
    assert LOADING_ROW == "[dim]  Loading...[/]"
    assert LOADING_ROW == LOADING.replace("[dim]", "[dim]  ", 1)
    # Same reasoning, Branch 7 fix round 1 (review C1): the snapshot feed's
    # "could not look" line is UNAVAILABLE in a feed row's column.
    assert UNAVAILABLE_LINE == "  [yellow]unavailable[/]"
    assert UNAVAILABLE_LINE == f"  {UNAVAILABLE}"
    assert panels.__all__ == [
        "UNAVAILABLE",
        "LOADING",
        "LOADING_ROW",
        "UNAVAILABLE_LINE",
        "PanelBase",
        "HeroBoxBase",
        "HeroRow",
        "SignalsPanelBase",
        "SparklinePanel",
        "RichLogFeed",
        "TableLeaderboard",
        "fmt_signal",
        "fmt_signal_trailing",
    ]


# -- 8. Agreement: a base's name is a CSS type selector (fix round 1, I1) ----


_PANELS_FILE = pathlib.Path(panels.__file__)
_TCSS = pathlib.Path(
    inspect.getfile(importlib.import_module("maxpane_dashboard.app"))
).parent / "themes" / "minimal.tcss"

#: Class names `widgets/panels.py` defines. Read off the module, so a base
#: added later is covered without editing this list.
_PANEL_CLASS_NAMES = frozenset(
    name for name, obj in vars(panels).items()
    if inspect.isclass(obj) and obj.__module__ == panels.__name__
)

#: A **bare block**: the class name standing alone as a whole selector --
#: either a rule's entire selector or one whole item of a comma-separated
#: selector list. Matched against the selector list wrapped in sentinel
#: commas, so both ends and every interior item are one expression:
#:
#:     r",\s*%s\s*," against "," + selector_list + ","
#:
#: What this admits and what it refuses (fix round 2, N1):
#:
#: * `HeroBoxBase {`            -- MATCH; bakery's bare block is exactly this
#:                                 shape and it styles every subclass.
#: * `A, HeroBoxBase, B {`      -- MATCH; a list item is a bare block too.
#: * `OCMHeroBox {`             -- no match; a dashboard's own widget class.
#: * `HeroBoxBase > X {`        -- no match; a rule *about* the base's
#:                                 children, which is the documented way to
#:                                 reach them.
#: * `PanelBase > .panel-title` -- no match; this is the cross-dashboard
#:                                 theme override `rules/widgets.md`
#:                                 documents, and the app stylesheet is where
#:                                 `DEFAULT_CSS` is meant to be overridden.
#:                                 The earlier bare-*token* regex refused it.
_BARE_BLOCK = r",\s*%s\s*,"


def _css_selector_lists(source: str) -> list[str]:
    """Every rule's selector list -- comments and declarations dropped.

    A class name inside a `/* … */` note (this branch wrote several) is prose,
    not a selector, and a `margin`/`color` value cannot be one either.
    Declaration bodies collapse to `{}` so that the text before each `{` is
    exactly one selector list, however many lines it spans.
    """
    without_comments = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    without_bodies = re.sub(r"\{[^{}]*\}", " {} ", without_comments)
    return [
        " ".join(m.group(1).split())
        for m in re.finditer(r"([^{}]*)\{", without_bodies)
        if m.group(1).strip()
    ]


def _bare_blocks(name: str, selector_lists) -> list[str]:
    """The selector lists in which `name` stands alone as a whole item."""
    pattern = re.compile(_BARE_BLOCK % re.escape(name))
    return [sl for sl in selector_lists if pattern.search(f",{sl},")]


@pytest.mark.guard
def test_no_panels_base_shares_its_name_with_another_widget_class() -> None:
    """A base's name styles every subclass, so it must be unique in the tree.

    `widgets/hero_metrics.py` and `widgets/signals_panel.py` (both
    bakery-only) own classes called `HeroBox` and `SignalsPanel`, and
    `minimal.tcss` has a bare block for each. While the new bases carried
    those names, every subscriber inherited bakery's geometry -- proven in
    review by inserting `min-width: 60` into the bakery `HeroBox` block,
    which widened ocm's SUPPLY box from 54 to 164 columns. Nothing moved on
    screen only because ocm's own blocks restated the same values and won on
    source order, which is luck, not a rule.

    Mutation that reddens this: rename `HeroBoxBase` back to `HeroBox`.
    """
    clashes: dict[str, list[str]] = {}
    for package in (
        "maxpane_dashboard.widgets",
        "maxpane_dashboard.templates",
        # A Screen subclass is a Widget, so its name is a type selector too
        # (fix round 2, N1).
        "maxpane_dashboard.screens",
    ):
        pkg = importlib.import_module(package)
        for info in pkgutil.walk_packages(pkg.__path__, package + "."):
            if info.name == panels.__name__:
                continue
            module = importlib.import_module(info.name)
            for name, obj in vars(module).items():
                if (
                    inspect.isclass(obj)
                    and obj.__module__ == module.__name__
                    and name in _PANEL_CLASS_NAMES
                ):
                    clashes.setdefault(name, []).append(module.__name__)
    assert not clashes, (
        f"widgets/panels.py shares a class name with {clashes} -- a base's "
        "name is a CSS type selector for every one of its subclasses"
    )


@pytest.mark.guard
@pytest.mark.parametrize("name", sorted(_PANEL_CLASS_NAMES))
def test_no_panels_base_is_a_bare_type_selector_in_the_stylesheet(name) -> None:
    """The app stylesheet outranks `DEFAULT_CSS`, so a bare block wins.

    Parametrised per name: a failure says which base collided, not that one
    did. `minimal.tcss` may name a *dashboard's own* widget class freely, and
    it may write `PanelBase > .panel-title { … }` -- a theme override of the
    base's own children is the documented way to restyle every panel. Only a
    **bare block**, the name standing alone as a whole selector, is forbidden.

    Mutation that reddens this: append `HeroBoxBase { min-width: 60; }` to
    minimal.tcss.
    """
    hits = _bare_blocks(name, _css_selector_lists(_TCSS.read_text(encoding="utf-8")))
    assert not hits, (
        f"minimal.tcss uses {name!r} as a bare block ({hits}); it is a "
        "widgets/panels.py base, so that block would style every subclass "
        "on every dashboard"
    )


@pytest.mark.guard
def test_the_bare_block_matcher_admits_a_theme_override() -> None:
    """The examples in `_BARE_BLOCK`'s comment, asserted (fix round 2, N1).

    Without the last case the guard refused a legitimate rule, which would
    have pushed a real theme override out of the app stylesheet and into a
    `DEFAULT_CSS` the stylesheet outranks.
    """
    sheet = """
    HeroBoxBase { width: 1fr; }
    OCMHeroBox { width: 1fr; }
    HeroBoxBase > Static { color: red; }
    PanelBase > .panel-title { color: $accent; }
    Something, HeroBoxBase, Other { height: 3; }
    """
    lists = _css_selector_lists(sheet)
    assert lists == [
        "HeroBoxBase",
        "OCMHeroBox",
        "HeroBoxBase > Static",
        "PanelBase > .panel-title",
        "Something, HeroBoxBase, Other",
    ], lists
    assert _bare_blocks("HeroBoxBase", lists) == [
        "HeroBoxBase",
        "Something, HeroBoxBase, Other",
    ]
    assert _bare_blocks("PanelBase", lists) == []
