import re

import pytest
from textual.app import App

from maxpane_dashboard.widgets.surf.burnkeepers import (
    EMPTY_LINE, FULL_WIDTH, SurfBurnkeepers, TITLE, UNAVAILABLE_LINE, WIDEN_HINT,
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


async def _render_lines(rows, size, **kwargs):
    """Same render as :func:`_render`, but joins each compositor *strip*
    (one physical terminal row) into one line of its own, rather than
    joining every `Segment` with a stray ``"\\n"`` between them.

    ``_render``'s own join (``"\\n".join(seg.text for strip in strips for
    seg in strip)``) inserts a break at *every style change*, not only at
    every physical row -- harmless for a plain substring check, but it
    makes a logical row that carries more than one styled segment (this
    panel's wallet cell is coloured; the numeric cells are not) look like
    it wrapped onto two lines when it did not. A test that needs to know
    which *physical line* a value landed on -- this one does, to tell the
    title line from the row line -- has to join per strip instead.
    """
    class _A(App):
        def compose(self):
            yield SurfBurnkeepers()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfBurnkeepers)
        widget.update_data(launchpad_burnkeepers=rows, **kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        lines = ["".join(seg.text for seg in strip) for strip in strips]
        return widget, lines


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


@pytest.mark.asyncio
async def test_the_marker_lights_exactly_when_a_row_would_clip() -> None:
    """Property, not a constant: sweeping a range of widths straddling the
    true fit threshold, the composited row is ellipsised *only* when the
    ``‹ widen`` marker is also lit, and never ellipsised once the marker
    goes dark. A hardcoded width would go stale the moment either
    ``FULL_WIDTH`` or the panel's own padding changed; this cannot, because
    it checks the *relationship* between the marker and the clip rather
    than asserting either one at a number copied from a measurement.

    This is exactly the property `_set_title`'s bug violated: it compared
    ``self.size.width`` against ``FULL_WIDTH`` directly, but the
    ``padding: 0 1`` that actually eats columns lives on the *child*
    ``Static`` (`DEFAULT_CSS`), not on this container -- so at
    ``self.size.width`` in ``{FULL_WIDTH, FULL_WIDTH + 1}`` (32 and 33) the
    row attempted the full tier, overflowed the padded box by exactly the
    two columns the padding claimed were already accounted for, and CSS
    ``text-overflow: ellipsis`` cut it silently -- with the marker dark,
    because both widths already cleared the (wrong) ``width < FULL_WIDTH``
    check. That silent gap is exactly what this sweep would have caught
    before it ever reached a real screen.

    A short, unambiguous wallet (``"0xdead"``, well under the panel's own
    11-column window) is used so the wallet cell never contributes its
    own legitimate windowing ellipsis -- any ``"…"`` in the composited row
    line is therefore always a CSS clip, never the anti-poisoning window.
    """
    row = {
        "wallet": "0xdead", "wallet_known": False,
        "imd_burned": 42.00, "eth_paid": 0.0031, "burns": 3,
    }

    # Straddles both COMPACT_WIDTH and FULL_WIDTH with margin on each side,
    # not centred on either -- the standing rule elsewhere in this repo's
    # width sweeps (a range that started at the pin could not fail by
    # construction).
    checked_any = False
    for width in range(FULL_WIDTH - 8, FULL_WIDTH + 8):
        _widget, lines = await _render_lines([row], size=(width, 24))
        content = [line for line in lines if line.strip()]
        assert len(content) >= 2, (width, lines)
        title_line, row_line = content[0], content[1]

        marker_lit = WIDEN_HINT in title_line
        row_ellipsised = "…" in row_line
        checked_any = True

        if row_ellipsised:
            assert marker_lit, (
                f"width={width}: the row was silently ellipsised with the "
                f"marker dark -- {row_line!r}"
            )
        if not marker_lit:
            assert not row_ellipsised, (
                f"width={width}: no marker, yet the row was ellipsised -- "
                f"{row_line!r}"
            )

    assert checked_any, "the sweep range was empty and proved nothing"
