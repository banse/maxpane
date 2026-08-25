import re

import pytest
from textual.app import App

from maxpane_dashboard.widgets.surf.launchpad_activity import (
    EMPTY_LINE, SurfLaunchpadActivity, TITLE, UNAVAILABLE_LINE,
)

_ROWS = [
    {"kind": "buy", "ticker": "ICE", "wallet": "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7",
     "wallet_known": True, "eth": 0.012, "age_s": 120.0},
    {"kind": "sell", "ticker": "K-256", "wallet": "0x84CB570CfeA8C6afd3B6C1AB491Db754886bf8e7",
     "wallet_known": False, "eth": 0.0031, "age_s": 420.0},
    {"kind": "launch", "ticker": "PYCR", "wallet": "0xe5B1275FB926613D983dA33fBfe1F331b7f64F2A",
     "wallet_known": False, "eth": None, "age_s": 840.0},
]


async def _render(rows, size=(60, 24), **kwargs):
    class _A(App):
        def compose(self):
            yield SurfLaunchpadActivity()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadActivity)
        widget.update_data(launchpad_activity=rows, **kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        return widget, "\n".join(seg.text for strip in strips for seg in strip)


async def _render_strips(rows, size=(60, 24), **kwargs):
    """Same render as :func:`_render`, but returns the compositor's own
    strips rather than flattening them to text -- for assertions that need
    a segment's ``style`` (colour), not just its characters.
    """
    class _A(App):
        def compose(self):
            yield SurfLaunchpadActivity()

    async with _A().run_test(size=size) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadActivity)
        widget.update_data(launchpad_activity=rows, **kwargs)
        await pilot.pause()
        return widget, pilot.app.screen._compositor.render_strips()


def _segment_color(strips, needle: str):
    """The resolved truecolor of the first segment whose text contains
    ``needle``, or ``None`` if no segment does.
    """
    for strip in strips:
        for seg in strip:
            if needle in seg.text and seg.style is not None and seg.style.color:
                return seg.style.color.get_truecolor()
    return None


@pytest.mark.asyncio
async def test_the_feed_renders_buys_sells_and_launches() -> None:
    _widget, text = await _render(_ROWS)
    assert TITLE in text
    assert "BUY" in text and "SELL" in text and "NEW" in text
    assert "ICE" in text and "K-256" in text and "PYCR" in text


@pytest.mark.asyncio
async def test_a_dead_sweep_and_a_quiet_one_say_different_things() -> None:
    _w, dead = await _render(None)
    _w, quiet = await _render([])
    assert UNAVAILABLE_LINE in dead and EMPTY_LINE not in dead
    assert EMPTY_LINE in quiet and UNAVAILABLE_LINE not in quiet


@pytest.mark.asyncio
async def test_a_launch_shows_no_eth_amount_at_all() -> None:
    """`eth is None` on a launch. A `0.000 ETH` beside it would be a number
    answering a question nobody asked -- the same defect that put a
    LayerZero fee beside a five-figure burn on the dev feed."""
    _widget, text = await _render([_ROWS[2]])
    assert "ETH" not in text


@pytest.mark.asyncio
async def test_a_hostile_ticker_never_reaches_markup() -> None:
    """`launch(string,string)` is permissionless: anyone can name a coin
    `[/x]` for the price of gas.

    Rendered alongside a well-formed row rather than alone -- but "the
    neighbour still renders" is not, on its own, enough either:
    `_row_markup`'s own `except Exception: return None` drops exactly the
    hostile row and leaves the well-formed neighbour untouched, which
    renders identical text to correct sanitisation. A regression that
    quietly *ate* the hostile row would still pass a check that only looks
    at the neighbour, which is exactly the hole a naive version of this
    fix left open.

    Two things prove the hostile row itself was rendered and cleaned,
    rather than silently dropped:

    1. **Row count.** Two input rows must produce two rendered data rows.
       Counted via the ETH amount cell's own shape (four decimal digits
       followed by ``" ETH"``) -- one per row, since both rows here are a
       buy/sell with a swap size, not a launch.
    2. **The hostile row's own surviving content.** Its `eth` is given a
       value that cannot be confused with `_ROWS[1]`'s, so its presence
       proves *that* row specifically survived, not merely that *some* row
       with different numbers did.
    """
    hostile = dict(
        _ROWS[0], ticker="[/x]", wallet="0xdead", wallet_known=False,
        eth=0.0777, age_s=999.0,
    )
    widget, text = await _render([hostile, _ROWS[1]])

    assert "[/x]" not in text                            # the markup never survives...
    assert len(re.findall(r"\d\.\d{4} ETH", text)) == 2  # ...both rows rendered...
    assert "0.0777" in text              # the hostile row's own eth
    assert "0.0031" in text              # 0x84CB's own eth, unaffected
    assert "K-256" in text                # ...and the row beside it still renders


@pytest.mark.asyncio
async def test_a_single_malformed_row_does_not_take_down_the_panel() -> None:
    _widget, text = await _render([{"kind": None}, _ROWS[0]])
    assert "ICE" in text


@pytest.mark.asyncio
async def test_a_narrow_panel_names_the_columns_it_sheds() -> None:
    from maxpane_dashboard.widgets.surf.launchpad_activity import (
        COMPACT_WIDTH, WIDEN_HINTS,
    )
    _widget, text = await _render(_ROWS, size=(COMPACT_WIDTH + 4, 24))
    assert "‹ widen" in text, text
    assert "ETH" not in text            # the shed column is really gone


@pytest.mark.asyncio
async def test_the_known_wallet_is_labelled_from_the_allowlist() -> None:
    """`0x047F…54B7` is DEV_WALLET. The allowlist is what makes a label
    trustworthy; a poisoner's lookalike renders dimmed and truncated.

    `"0x047F" in text` alone cannot tell a known wallet from an unknown one
    apart -- both render the identical address text and differ only by
    style (cyan vs dim), so a regression that ignored `wallet_known`
    entirely would still pass a text-only check. This renders the same
    address both ways and asserts on the composited segment's own colour:
    cyan is a hued colour (green and blue channels well above red); dim
    resolves to a neutral grey (red, green and blue near-equal) -- the
    property the docstring actually claims to verify.
    """
    known_row = _ROWS[0]
    unknown_row = dict(_ROWS[0], wallet_known=False)

    _widget, known_strips = await _render_strips([known_row])
    _widget2, unknown_strips = await _render_strips([unknown_row])

    known_color = _segment_color(known_strips, "0x047F")
    unknown_color = _segment_color(unknown_strips, "0x047F")

    assert known_color is not None and unknown_color is not None
    assert known_color != unknown_color
    # cyan: a real hue, red suppressed relative to green/blue.
    assert known_color.red < known_color.green and known_color.red < known_color.blue
    # dim: a desaturated grey, all three channels close together.
    assert abs(unknown_color.red - unknown_color.green) <= 4
    assert abs(unknown_color.green - unknown_color.blue) <= 4


def test_the_kind_cell_fits_the_whole_display_vocabulary() -> None:
    """Both directions: no member is cut, and the cell is not padded past
    the widest one. A widget may not import `data/`, so the producer's
    vocabulary is a literal here -- and this test is what keeps the literal
    honest, exactly as `test_activity_cells_are_sized_from_the_producers_
    own_vocabularies` does for the dev feed.

    Calls the producer rather than comparing one literal against another:
    a `set(KIND_WORDS) == {"buy", "sell", "launch"}` check next to a
    producer import that is never called cannot detect drift in either
    direction -- it would stay green if the producer grew a fourth kind, or
    renamed one, as long as nobody also remembered to edit this file's own
    literal. Feeding the producer inputs shaped to yield one of each kind
    and reading its own output back is what keeps the literal honest.

    ``_launchpad_feed_from_logs``, not ``_activity_rows`` and not
    ``_launchpad_activity_rows`` either: the producer has been renamed
    twice since this test was first written, both times to avoid a name
    ``surf_manager`` already owns for a *different* stage of the same
    pipeline (``surf_manager._activity_rows`` is the unrelated dev-activity
    feed, and ``surf_manager._launchpad_activity_rows`` is the very next
    stage -- the converter from ``LaunchpadEvent`` models to payload dicts,
    not this function's own log-row producer). See this function's own
    docstring in ``data/surf_client.py``. Importing the current name is
    what keeps this test calling the real producer rather than silently
    failing to import at all -- and a third rename would break it the same
    way, which is why it is called out explicitly here rather than assumed
    stable.
    """
    from rich.cells import cell_len

    from maxpane_dashboard.data.surf_client import (
        _launchpad_feed_from_logs,  # test-only import
    )
    from maxpane_dashboard.widgets.surf.launchpad_activity import (
        KIND_WORDS, _KIND_COLS,
    )

    rows = _launchpad_feed_from_logs(
        swaps=[
            {"pool_id": "0xa", "trader": "0xT1", "is_buy": True,
             "eth_amount_wei": 12 * 10**15, "block": 100},
            {"pool_id": "0xa", "trader": "0xT2", "is_buy": False,
             "eth_amount_wei": 3 * 10**15, "block": 99},
        ],
        merged={
            "0xa": {"ticker": "ICE", "creator": "0xC1", "block": 90},
            "0xb": {"ticker": "PYCR", "creator": "0xC2", "block": 50},
        },
        head=110,
        now_ts=1000.0,
    )
    kinds = {row["kind"] for row in rows}
    assert kinds == {"buy", "sell", "launch"}
    assert set(KIND_WORDS) == kinds
    assert _KIND_COLS == max(cell_len(w) for w in KIND_WORDS.values())
