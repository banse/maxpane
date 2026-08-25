import re

import pytest
from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.widgets.surf.burnkeepers import (
    EMPTY_LINE, FULL_WIDTH, SurfBurnkeepers, TITLE, UNAVAILABLE_LINE,
)

_ROWS = [
    {"wallet": "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7", "wallet_known": True,
     "imd_burned": 15670.787926, "eth_paid": 5.4921052213582e-05, "burns": 2},
    {"wallet": "0x84CB570CfeA8C6afd3B6C1AB491Db754886bf8e7", "wallet_known": False,
     "imd_burned": 31.23838, "eth_paid": 2.7274720356026e-05, "burns": 1},
    {"wallet": "0xe5B1275FB926613D983dA33fBfe1F331b7f64F2A", "wallet_known": False,
     "imd_burned": 29.979176, "eth_paid": 2.7646331857556e-05, "burns": 1},
    {"wallet": "0x887b86B6B6957F7bbeA88B8CEfD392f39236A88C", "wallet_known": False,
     "imd_burned": 23.280267, "eth_paid": 2.7646331857556e-05, "burns": 1},
]


async def _render(rows, size=(40, 24), **kwargs):
    class _A(App):
        def compose(self):
            yield SurfBurnkeepers()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfBurnkeepers)
        widget.update_data(launchpad_burnkeepers=rows, **kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join(seg.text for strip in strips for seg in strip)
        return widget, text


@pytest.mark.asyncio
async def test_the_leaderboard_ranks_by_imd_burned() -> None:
    _widget, text = await _render(_ROWS)
    assert TITLE in text
    rows = [r for r in text.splitlines() if "0x" in r]
    assert rows[0].strip().startswith("0x047F")
    assert "15.7K" in text          # the dev's two burns, summed


@pytest.mark.asyncio
async def test_the_eth_column_shows_the_fee_not_the_value_sent() -> None:
    """0x887b sent 0.001 ETH and really paid 0.000027646331857556.
    The whole point of the column."""
    _widget, text = await _render(_ROWS)
    assert "0.001" not in text


@pytest.mark.asyncio
async def test_an_unread_fee_is_a_dash_and_the_rest_of_the_row_survives() -> None:
    row = dict(_ROWS[0], eth_paid=None)
    _widget, text = await _render([row])
    assert "15.7K" in text          # from logs -- unaffected
    assert "--" in text             # the fee alone is unknown
    assert "0.00" not in text       # and never a zero fee


@pytest.mark.asyncio
async def test_a_dead_sweep_and_a_quiet_one_say_different_things() -> None:
    _w, dead = await _render(None)
    _w, quiet = await _render([])
    assert UNAVAILABLE_LINE in dead and EMPTY_LINE not in dead
    assert EMPTY_LINE in quiet and UNAVAILABLE_LINE not in quiet


@pytest.mark.asyncio
async def test_no_row_is_wider_than_the_panel_says_it_is() -> None:
    """A sized cell is not a fitted one: `len()` counts characters where the
    terminal counts cells."""
    _widget, text = await _render(_ROWS, size=(FULL_WIDTH + 2, 24))
    for row in text.splitlines():
        assert cell_len(row.rstrip()) <= FULL_WIDTH + 2, row


@pytest.mark.asyncio
async def test_a_narrow_panel_marks_before_it_clips() -> None:
    """The rail's other panels are plain `Static`s with no marker of their
    own -- so if this one binds, it MUST be able to say so. This is the
    property that disqualified the 5:2 seam when the `l` body was last
    swept."""
    _widget, text = await _render(_ROWS, size=(FULL_WIDTH - 4, 24))
    assert "‹ widen" in text, text


@pytest.mark.asyncio
async def test_a_hostile_wallet_string_never_reaches_markup() -> None:
    """`"[/x]" not in text` alone cannot fail for the right reason, and
    neither can "the neighbour still renders" alone: `_row_markup`'s own
    `except Exception: return None` drops exactly the hostile row and
    leaves the well-formed neighbour untouched, which renders identical
    text to correct sanitisation -- a regression that quietly *ate* the
    hostile row would still pass a check that only looks at the neighbour.

    Two things prove the hostile row itself was rendered and cleaned,
    rather than silently dropped:

    1. **Row count.** Two input rows must produce two rendered data rows.
       Counted here via the ETH cell's own shape (``0.`` + exactly six
       digits) -- one per row at this magnitude -- rather than by physical
       line, because a single logical row can compose from more than one
       styled `Segment` in the compositor's own strips.
    2. **The hostile row's own surviving content.** Its `imd_burned` /
       `eth_paid` are given values that cannot be confused with
       `_ROWS[1]`'s, so their presence proves *that* row specifically
       survived, not merely that *some* row with different numbers did.
    """
    hostile = dict(
        _ROWS[0], wallet="[/x]", wallet_known=False,
        imd_burned=777.111222, eth_paid=8.8e-05, burns=3,
    )
    _widget, text = await _render([hostile, _ROWS[1]])

    assert "[/x]" not in text                       # the markup never survives...
    assert len(re.findall(r"0\.\d{6}", text)) == 2  # ...both rows rendered...
    assert "777.11" in text         # the hostile row's own imd_burned
    assert "0.000088" in text       # the hostile row's own eth_paid
    assert "31.24" in text          # 0x84CB's own imd_burned, unaffected
    assert "0.000027" in text       # 0x84CB's own eth_paid, unaffected
