"""MEDI-38: HeroMetrics must show an explicit unavailable state, never raise.

The three hero boxes are fed straight from the bakery tRPC payload, which
can return ``null`` for any field (an inactive season, a failed
sub-request) and can produce ``NaN`` from a division upstream.  Both used
to reach an f-string format spec:

    >>> f"{None:.2f}"   # TypeError
    >>> int(float('nan') * 3600)   # ValueError

``BakeryScreen`` catches that and logs a warning, so the app survives --
but the box is left on ``Loading...`` (or on a stale value from an earlier
poll) for as long as the bad field persists, with nothing on screen saying
the number is not live.  That is the failure this file forbids.

Assertions run against composited output
(``screen._compositor.render_strips()``) rather than the widget's content
string: a string that never reaches a pixel would satisfy a naive test
while being invisible to the user.  Each case is also pumped through an
idle cycle, because Textual defers markup parsing -- a ``MarkupError``
raised in the message pump bypasses the screen's ``try/except`` entirely
and takes the app down (HIGH-7).
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.hero_metrics import HeroMetrics

#: The full argument set, all present and well-formed.
GOOD = dict(
    prize_pool_eth=12.5,
    prize_pool_usd=41_000.0,
    hours_remaining=71.5,
    season_id=4,
    season_active=True,
    leader_name="Crumb Cartel",
    leader_cookies=139_300.0,
    leader_rate=5_800.0,
)

#: Values a JSON payload can legally hold where a number was expected.
BAD_VALUES = [None, float("nan"), float("inf"), "n/a", {}]

#: Fields whose absence must not stop the other boxes from rendering.
NUMERIC_FIELDS = [
    "prize_pool_eth",
    "prize_pool_usd",
    "hours_remaining",
    "leader_cookies",
    "leader_rate",
]


class _Harness(App):
    """Mount HeroMetrics with the production geometry.

    ``themes/minimal.tcss`` gives ``HeroBox`` ``width: 1fr``; without it the
    first box takes the whole row and the other two never reach the
    compositor, so an assertion about the LEADER box would fail for reasons
    of layout rather than of behaviour.
    """

    CSS = """
    HeroBox {
        width: 1fr;
        height: 7;
        padding: 1 2;
        text-align: center;
    }
    """

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _composited(app) -> str:
    return "\n".join(
        "".join(seg.text for seg in strip)
        for strip in app.screen._compositor.render_strips()
    )


async def _render(**kwargs) -> tuple[str, App]:
    """Drive a mounted HeroMetrics and return what actually reached pixels.

    The terminal is sized wide enough for all three boxes: at the 80-column
    default the row is clipped after the first box, and an assertion about
    the LEADER box would then pass or fail for reasons of geometry rather
    than of the behaviour under test.
    """
    widget = HeroMetrics()
    app = _Harness(widget)
    async with app.run_test(size=(220, 24)) as pilot:
        widget.update_data(**kwargs)
        await pilot.pause()
        return _composited(app), app


# ---------------------------------------------------------------------------
# the reported failure: missing data
# ---------------------------------------------------------------------------


async def test_all_none_renders_unavailable_not_loading() -> None:
    """Every field null: the boxes say so instead of raising or hanging."""
    args = dict(GOOD)
    args.update({k: None for k in NUMERIC_FIELDS})
    args["leader_name"] = None
    args["season_id"] = None

    rendered, app = await _render(**args)

    assert app._exception is None, f"died in the pump: {app._exception!r}"
    assert "unavailable" in rendered, (
        "an all-null payload must state that the values are unavailable; "
        f"got: {rendered!r}"
    )
    assert "Loading..." not in rendered, (
        "a box left on its compose-time placeholder is indistinguishable "
        "from a dashboard that is still starting up (MEDI-38)"
    )
    # The labels are still there -- the row degraded, it did not vanish.
    for label in ("PRIZE POOL", "LEADER"):
        assert label in rendered


@pytest.mark.parametrize("field", NUMERIC_FIELDS)
@pytest.mark.parametrize("bad", BAD_VALUES, ids=repr)
async def test_one_bad_field_does_not_block_the_other_boxes(field, bad) -> None:
    """A single malformed field must not cost the whole row.

    The pre-fix code raised on the first bad box, abandoning every box
    after it in the same ``update_data`` call.
    """
    args = dict(GOOD)
    args[field] = bad

    rendered, app = await _render(**args)

    assert app._exception is None, f"{field}={bad!r} died in the pump"
    assert "Loading..." not in rendered, (
        f"{field}={bad!r} left a box on 'Loading...': {rendered!r}"
    )
    # The leader name is the last box written; if an earlier box aborted the
    # update, this is what goes missing.
    if field not in ("leader_cookies", "leader_rate"):
        assert "Crumb Cartel" in rendered, (
            f"{field}={bad!r} stopped the update before the LEADER box: "
            f"{rendered!r}"
        )


async def test_nan_never_prints_as_nan() -> None:
    """``NaN`` degrades to the unavailable marker, not to the text 'nan'."""
    args = dict(GOOD)
    args["prize_pool_eth"] = float("nan")
    args["prize_pool_usd"] = float("nan")

    rendered, app = await _render(**args)

    assert app._exception is None
    assert "nan" not in rendered.lower().replace("unavailable", "")
    assert "unavailable" in rendered


# ---------------------------------------------------------------------------
# hostile data (HIGH-7's pattern) and the happy path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    ["[/x] Bakers", "[/]", "[/bold] Crew", "[not a tag] Guild", "[#00ff00 on]"],
)
async def test_hostile_leader_name_still_renders(hostile) -> None:
    """A player-chosen name is escaped, and the box still updates."""
    args = dict(GOOD)
    args["leader_name"] = hostile

    rendered, app = await _render(**args)

    assert app._exception is None, f"{hostile!r} crashed the pump"
    assert "139.3K cookies" in rendered, (
        f"the LEADER box froze on {hostile!r}: {rendered!r}"
    )


async def test_happy_path_still_shows_live_numbers() -> None:
    """The degradation work did not blunt the normal render."""
    rendered, app = await _render(**GOOD)

    assert app._exception is None
    assert "12.50 ETH" in rendered
    assert "$41,000" in rendered
    assert "Crumb Cartel" in rendered
    assert "unavailable" not in rendered


async def test_ended_season_is_not_an_unavailable_state() -> None:
    """A finished season is a real answer, not missing data."""
    args = dict(GOOD)
    args["season_active"] = False

    rendered, app = await _render(**args)

    assert app._exception is None
    assert "Season Ended" in rendered
    assert "SEASON 4" in rendered
