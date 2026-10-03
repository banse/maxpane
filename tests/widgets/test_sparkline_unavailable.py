"""#34: every ``SparklinePanel`` subscriber tells a failed read from an empty one.

``SparklinePanel.render_series`` used to write ``EMPTY_TEXT`` -- the
real-empty sentence -- for a series whose points were ``None``, because
``coerce_points(None)`` is ``[]``: a failed read wearing a real negative's
clothes. The base now writes yellow ``unavailable`` for ``None`` (beside
the label where ``EMPTY_KEEPS_LABEL`` is set), and keeps each panel's own
empty wording for ``[]``.

Each of the seven subscribers is driven here through its **own**
``update_data``, with the keyword arguments its screen's ``PANELS`` row
sends, once with every series ``None`` and once with every series ``[]``,
and the claim is read off the compositor (``render_strips()``, segments
joined per row), never off a content string. The labels and their cell
widths are hand-typed: they are each panel's own pins, and deriving them
from ``LABEL_WIDTH`` would compare the panel with itself.

Latent on screen today: no manager serves ``None`` for these keys (bakery's
manager collapsing ``None`` to ``[]`` is #75); the panel says so correctly
before a manager starts relying on it.
"""

from __future__ import annotations

import inspect

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.widgets.base.overview.bt_sparklines import BTSparklines
from maxpane_dashboard.widgets.cattown.ct_sparklines import CTSparklines
from maxpane_dashboard.widgets.cookie_chart import CookieChart
from maxpane_dashboard.widgets.dota.dota_sparklines import DOTASparklines
from maxpane_dashboard.widgets.ocm.ocm_sparklines import OCMSparklines
from maxpane_dashboard.widgets.talismans.tal_sparkline import TalismansSparkline
from maxpane_dashboard.widgets.ttt.ttt_sparkline import TTTSparkline

from tests.widgets.surf_compositing import composite_lines

_SIZE = (120, 30)

#: What ``[yellow]`` composites to under ``minimal.tcss`` -- the triplet
#: ``tests/widgets/test_bakery_widgets.py`` pins CookieChart's own
#: not-a-dict ``unavailable`` line against.
_YELLOW = (255, 255, 0)

_WAITING = "waiting for data..."

#: Bakery names for ``CookieChart``'s one ``histories`` dict: one per line.
_BAKERIES = ("Rug Co", "Dough Inc", "Flat")


def _histories(value) -> dict:
    """CookieChart takes one dict of series keyed by bakery name."""
    return {"histories": {name: value for name in _BAKERIES}}


def _each(*names: str):
    """Every other subscriber takes one keyword per series."""

    def build(value) -> dict:
        return {name: value for name in names}

    return build


#: ``(widget class, payload builder, label cells or None, empty wording)``.
#: ``None`` for the label cells is a panel that keeps no label on its
#: degraded lines (``EMPTY_KEEPS_LABEL = False``); ``""`` for the wording is
#: a panel whose empty line is blank (``EMPTY_TEXT = ""``).
_SUBSCRIBERS = [
    pytest.param(CookieChart, _histories, None, "", id="CookieChart"),
    pytest.param(
        TalismansSparkline,
        _each("mythic_history", "operations_history"),
        (f"{'MYTHIC COUNT':<16}", f"{'DAILY OPERATIONS':<16}"),
        _WAITING,
        id="TalismansSparkline",
    ),
    pytest.param(
        CTSparklines,
        _each(
            "prize_pool_history", "leader_weight_history", "raffle_tickets_history"
        ),
        None,
        "",
        id="CTSparklines",
    ),
    pytest.param(
        TTTSparkline,
        _each("burns_history", "volume_history"),
        (f"{'BURNS':<12}", f"{'24H VOLUME $':<12}"),
        _WAITING,
        id="TTTSparkline",
    ),
    pytest.param(
        DOTASparklines,
        _each(
            "top_frontline_history",
            "mid_frontline_history",
            "bot_frontline_history",
        ),
        None,
        "",
        id="DOTASparklines",
    ),
    pytest.param(
        OCMSparklines,
        _each("supply_history", "staked_history", "ocmd_supply_history"),
        None,
        "",
        id="OCMSparklines",
    ),
    pytest.param(
        BTSparklines,
        _each("volume_history", "eth_price_history", "trade_count_history"),
        (f"{'Volume':<10}", f"{'ETH':<10}", f"{'Trades':<10}"),
        _WAITING,
        id="BTSparklines",
    ),
]


def _named_parameters(cls) -> set[str]:
    """``update_data``'s named keywords, without ``self`` or a catch-all."""
    return {
        name
        for name, param in inspect.signature(cls.update_data).parameters.items()
        if name != "self" and param.kind is not param.VAR_KEYWORD
    }


def _body(cls, rows: list[str]) -> list[str]:
    """The non-blank rows under the panel's title, stripped."""
    title_at = next(i for i, row in enumerate(rows) if row.strip() == cls.TITLE)
    return [row.strip() for row in rows[title_at + 1 :] if row.strip()]


@pytest.mark.parametrize("cls, payload, cells, empty", _SUBSCRIBERS)
@pytest.mark.parametrize("state", ["none", "empty"])
async def test_a_failed_read_says_unavailable_and_an_empty_one_the_panels_own_words(
    cls, payload, cells, empty, state
) -> None:
    """``None`` -> ``unavailable`` on every line (beside its label where the
    panel keeps one); ``[]`` -> the panel's own empty wording, unchanged.

    Mutations (``widgets/panels.py``): the unlabelled unavailable line ->
    ``EMPTY_TEXT`` reddens the four ``none`` cases without labels; the
    labelled one -> ``EMPTY_TEXT`` reddens the three with labels; ``[]``
    routed to the unavailable line reddens every ``empty`` case.
    """
    # Every series the panel draws is driven, not just the first.
    assert set(payload(None)) == _named_parameters(cls), cls.__name__
    value = None if state == "none" else []
    rows = await composite_lines(
        cls, _SIZE, css_path=CSS_PATH, region_only=True, **payload(value)
    )
    body = _body(cls, rows)
    line_count = len(cls.LINE_IDS)
    if state == "none":
        if cells is None:
            expected = ["unavailable"] * line_count
        else:
            expected = [f"{cell}  unavailable" for cell in cells]
    else:
        if cells is None:
            expected = [empty] * line_count if empty else []
        else:
            expected = [f"{cell}  {empty}" for cell in cells]
    assert body == expected, rows


class _Harness(App):
    """Mount one widget under the app stylesheet."""

    CSS_PATH = CSS_PATH

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


@pytest.mark.parametrize("cls, payload, cells, empty", _SUBSCRIBERS)
async def test_the_unavailable_word_is_yellow(cls, payload, cells, empty) -> None:
    """``unavailable`` is the shared ``UNAVAILABLE`` markup, so it lands in
    yellow on every line, one segment per line. Mutation: the labelled
    unavailable line spelled without ``UNAVAILABLE``'s ``[yellow]`` -> the
    three labelled cases redden."""
    widget = cls()
    async with _Harness(widget).run_test(size=_SIZE) as pilot:
        widget.update_data(**payload(None))
        await pilot.pause()
        assert pilot.app._exception is None
        colours = [
            seg.style.color.get_truecolor()
            if seg.style is not None and seg.style.color is not None
            else None
            for strip in pilot.app.screen._compositor.render_strips()
            for seg in strip
            if "unavailable" in seg.text
        ]
    assert colours == [_YELLOW] * len(cls.LINE_IDS), (cls.__name__, colours)
