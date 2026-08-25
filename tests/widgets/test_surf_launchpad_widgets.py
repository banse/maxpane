import pytest
from textual.app import App

from maxpane_dashboard.widgets.surf.launchpad import (
    SurfBurnPipeline, SurfCurveFlow, SurfLaunchpadCoins,
)

HOSTILE = {
    "ticker": "[/x]", "name": "[bold red]pwn[/]", "creator": "0xdead",
    "creator_known": False, "age_s": 60.0, "price_eth": 0.0071,
    "change_24h_pct": 34.0, "swaps_24h": 88, "swaps_all": 140,
    "imd_burned": 142.1,
}

# Task 11: SURF_ROW_KEYS["launchpad_coins"] (Task 1, frozen) -- a well-formed
# row for the tests below that aren't specifically about hostile input.
_ROW = {
    "ticker": "ICE", "name": "Ice Coin",
    "creator": "0x8ca0000000000000000000000000000000e5e8",
    "creator_known": False, "age_s": 7_200.0, "price_eth": 0.0071,
    "change_24h_pct": 34.0, "swaps_24h": 41, "swaps_all": 97,
    "imd_burned": 250.0,
}
_ROWS = [_ROW]

#: Render size for every mount in this module.  **Not** Textual's default
#: 80x24, and that is the whole point: ``SurfLaunchpadCoins``' nine fixed
#: columns need ``launchpad._TABLE_FULL_WIDTH`` (89, re-swept 2026-08-25 when
#: MCAP replaced PRICE -- was 93) before the last of them reaches a pixel, so
#: at 80 the ``SW ALL`` header and every ``swaps_all`` value are clipped by
#: the compositor and *no* assertion in this file could see them. That is
#: not hypothetical: this module rendered at 80 until 2026-08-24, so Task
#: 11's whole ``SW ALL`` column could have been deleted with these tests
#: green. 100 clears 89 with room to spare and keeps the panel's own
#: ``‹ widen`` marker unlit, which is the state the column assertions want
#: to measure.
_RENDER_SIZE = (100, 24)


async def _render_coins(coins, **kwargs):
    """Mount ``SurfLaunchpadCoins``, feed it ``coins`` (and any
    ``update_data`` kwarg -- ``coin_count``, ``launch_count``,
    ``as_of_hhmm``) via ``update_data``, and return ``(widget,
    composited_text)``.

    Same render-then-composite pattern the pre-existing tests in this
    module already use (CLAUDE.md: assert against composited output --
    ``_compositor.render_strips()`` -- never the content string, which
    would pass a naive test while the value never reaches a pixel).

    Task 3 fix: a strip is one screen *row*, made of one segment per
    distinct markup style; the previous join here (``"\\n".join(seg.text
    for strip in strips for seg in strip)``) put a newline between every
    *segment*, not every row, so a row with more than one style span (this
    module's own title, once the note and the widen marker share it) split
    across several joined "lines" even though it painted as one. It stayed
    invisible while every panel's rows carried at most one span; a
    multi-span title row is what exposes it. Segments now join within a
    row first, and only rows join on ``\\n``.
    """
    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=coins, **kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
        return widget, text


@pytest.mark.asyncio
async def test_hostile_ticker_and_name_never_reach_markup() -> None:
    """launch(string,string) is permissionless: anyone can name a coin `[/x]`.

    Asserted against composited output -- a string that never reaches a pixel
    passes a naive content-string test while being invisible to the user.
    """
    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=[HOSTILE], coin_count=146, as_of_hhmm="01:14")
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
        assert "pwn" in text          # the value is shown...
        assert "[bold red]" not in text   # ...but never as markup
        assert "[/x]" not in text


@pytest.mark.asyncio
async def test_a_quiet_coin_renders_a_dash_not_zero_percent() -> None:
    quiet = HOSTILE | {"ticker": "Q", "name": "Quiet", "change_24h_pct": None,
                       "swaps_24h": 0, "swaps_all": 0}

    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=[quiet], coin_count=1, as_of_hhmm="01:14")
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
        assert "0%" not in text


@pytest.mark.asyncio
async def test_burn_pipeline_shows_ready_only_when_ready() -> None:
    class _A(App):
        def compose(self):
            yield SurfBurnPipeline()

    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfBurnPipeline)
        widget.update_data(burn_accrued=15.06, burn_staged=0.0, burn_ready=True,
                           burned_total=3299.0, burn_events=66)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        assert "ready" in "\n".join(seg.text for s in strips for seg in s)


@pytest.mark.asyncio
async def test_burn_pipeline_unknown_is_not_ready() -> None:
    class _A(App):
        def compose(self):
            yield SurfBurnPipeline()

    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfBurnPipeline)
        widget.update_data(burn_accrued=None, burn_staged=None, burn_ready=None,
                           burned_total=None, burn_events=None)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        assert "ready" not in "\n".join(seg.text for s in strips for seg in s)


# ---------------------------------------------------------------------------
# Task 11 -- the day-not-hour rename, the SWAPS ALL column, the population
# disagreement note, and the narrower CREATOR window that pays for it.
# ---------------------------------------------------------------------------


# Task 11's own version of this test asserted the column sum with
# ``_PRICE_COLS`` in it (79). Task 7 replaced that column with ``_MCAP_COLS``
# (six columns narrower), which retired the constant this test named -- see
# ``test_the_table_still_needs_exactly_seventy_five_columns`` near the bottom
# of this file for the superseding version, kept beside the MCAP tests it
# now travels with rather than left here referencing a constant that no
# longer exists.


@pytest.mark.asyncio
async def test_the_table_names_the_day_not_the_hour():
    _, out = await _render_coins(_ROWS)
    assert "24H%" in out and "1H%" not in out


@pytest.mark.asyncio
async def test_both_swap_columns_reach_the_compositor_with_their_own_value():
    """``SW 24H`` and ``SW ALL`` are two columns carrying two fields.

    The header half is cheap and was already covered; the *value* half was
    not, and it is the half that can silently disappear. ``SW ALL`` is the
    ninth and last fixed column, so it is the first thing the compositor
    drops -- at Textual's default 80 columns neither its header nor its
    number is ever painted, which is how this module could have gone on
    passing with ``_coin_row`` reading the pre-rename ``swaps_1h`` for both
    cells (or reading nothing at all for the second one).

    Two distinct values, deliberately: 41 today against 97 all-time. A row
    where the two agreed would pass just as happily against a widget that
    rendered one field twice.
    """
    _, out = await _render_coins(_ROWS)
    assert "SW 24H" in out and "SW ALL" in out
    assert "41" in out and "97" in out


@pytest.mark.asyncio
async def test_the_title_reports_a_population_the_sweep_could_not_reach():
    """146 coins with 66 swept is the bug that produced this whole task.
    Rendering the subset as if it were the population is what hid it.
    """
    _, out = await _render_coins(_ROWS, coin_count=146, launch_count=66)
    assert "146 coins · 66 read" in out


@pytest.mark.asyncio
async def test_an_agreeing_count_says_it_once():
    _, out = await _render_coins(_ROWS, coin_count=146, launch_count=146)
    assert "146 coins" in out and "read" not in out


@pytest.mark.asyncio
async def test_a_sweep_failure_says_nothing_about_the_population():
    """``launch_count is None`` means the sweep failed outright -- there is
    nothing to compare ``coin_count`` against, so the note must keep
    today's plain ``{coin_count} coins`` (+ ``as of``) rather than claiming
    either agreement or disagreement. Not one of the brief's five
    illustrative tests, but the one that would catch a bug where the
    comparison fires on a missing ``launch_count`` instead of staying
    silent -- the other half of the same fix
    ``test_the_title_reports_a_population_the_sweep_could_not_reach`` and
    ``test_an_agreeing_count_says_it_once`` prove between them.
    """
    _, out = await _render_coins(_ROWS, coin_count=146, launch_count=None)
    assert "146 coins" in out and "read" not in out


@pytest.mark.asyncio
async def test_a_hostile_ticker_is_escaped_in_the_table():
    """launch(string,string) is permissionless and unpriced beyond gas.

    Correction from the brief (Ruling R4): the brief's version of this test
    asserted ``"[/x]" in out``, which is backwards and fails against a
    correct implementation. A ticker that is *only* a bracket-tag shape
    strips to nothing (:func:`_sanitize` step 2 in
    ``widgets/surf/launchpad.py`` -- the same behaviour
    ``test_hostile_ticker_and_name_never_reach_markup`` above already proves
    for ticker and name together), so the raw ``[/x]`` text never reaches
    the compositor at all.
    """
    _, out = await _render_coins([{**_ROW, "ticker": "[/x]"}])
    assert "[/x]" not in out


@pytest.mark.asyncio
async def test_the_creator_cell_truncates_to_the_narrower_eleven_column_window():
    """Task 11 pays for SWAPS ALL by shrinking CREATOR 17 -> 11 columns: six
    leading characters, an ellipsis, four trailing -- the brief's own
    example (``0x8ca0…e5e8``).  A test that only checks the width-constant
    arithmetic would not catch a bug where the constant shrinks correctly
    but the cell still renders the *old* 17-column ``long_addr()`` form,
    which truncates a different (and longer) trailing window -- exactly the
    two-halves-mask-each-other shape this task's brief warns about, and
    worse than cosmetic: it would silently widen the actual rendered
    column past its declared budget.
    """
    _, out = await _render_coins([_ROW])
    assert "0x8ca0…e5e8" in out
    assert "0x8ca00000…00e5e8" not in out


# ---------------------------------------------------------------------------
# Task 2 -- a blank line under CURVE FLOW and BURN PIPELINE
# ---------------------------------------------------------------------------


def test_curve_flow_puts_a_blank_line_under_its_title() -> None:
    from maxpane_dashboard.widgets.surf.launchpad import FLOW_TITLE, _flow_lines
    lines = _flow_lines(4683, 673, 1.25, "01:14")
    assert FLOW_TITLE in lines[0]
    assert lines[1] == "", lines


def test_burn_pipeline_puts_a_blank_line_under_its_title() -> None:
    from maxpane_dashboard.widgets.surf.launchpad import (
        BURN_TITLE, _pipeline_lines,
    )
    lines = _pipeline_lines(0.5, 30.0, 25.0, True, 15745.0, "01:14", 30.0)
    assert BURN_TITLE in lines[0]
    assert lines[1] == "", lines


@pytest.mark.asyncio
async def test_the_blank_line_reaches_the_screen_in_both_rail_panels() -> None:
    """A blank line the compositor collapses is not a blank line.

    Asserted on composited rows, not on the list: `Static` joins on "\\n" and
    an empty entry is only a rendered row if the panel is `height: auto` and
    the line is actually painted.
    """
    from textual.app import App
    from maxpane_dashboard.widgets.surf.launchpad import (
        BURN_TITLE, FLOW_TITLE, SurfBurnPipeline, SurfCurveFlow,
    )

    class _A(App):
        def compose(self):
            yield SurfCurveFlow()
            yield SurfBurnPipeline()

    async with _A().run_test(size=(60, 24)) as pilot:
        pilot.app.query_one(SurfCurveFlow).update_data(
            swap_count=4683, trader_count=673, creator_eth_owed=1.25,
            as_of_hhmm="01:14",
        )
        pilot.app.query_one(SurfBurnPipeline).update_data(
            burn_accrued=0.5, burn_staged=30.0, burn_ready=True,
            burn_min_bridge=25.0, burn_bridgeable=30.0,
            burned_total=15745.0, as_of_hhmm="01:14",
        )
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]

    for title in (FLOW_TITLE, BURN_TITLE):
        i = next(n for n, row in enumerate(rows) if title in row)
        assert rows[i + 1].strip() == "", (title, rows[i + 1])


# ---------------------------------------------------------------------------
# Task 3 -- the coin table's note moves up beside its title
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_note_shares_the_title_line_and_the_next_row_is_blank() -> None:
    widget, text = await _render_coins(
        _ROWS, coin_count=146, launch_count=146, as_of_hhmm="01:14",
    )
    rows = text.splitlines()
    i = next(n for n, row in enumerate(rows) if "LAUNCHPAD COINS" in row)
    assert "146 coins" in rows[i], rows[i]
    assert "as of 01:14" in rows[i], rows[i]
    assert rows[i + 1].strip() == "", rows[i + 1]


@pytest.mark.asyncio
async def test_the_unavailable_note_moves_up_with_the_rest_of_the_note() -> None:
    """A dead sweep must still say so, from the title line, composited."""
    from maxpane_dashboard.widgets.surf.launchpad import COINS_UNAVAILABLE
    _widget, text = await _render_coins(None, coin_count=None)
    rows = text.splitlines()
    i = next(n for n, row in enumerate(rows) if "LAUNCHPAD COINS" in row)
    assert COINS_UNAVAILABLE in rows[i], rows[i]


@pytest.mark.asyncio
async def test_the_gap_widget_replaced_the_note_widget() -> None:
    """The id follows the responsibility: a widget called `note` that can
    never carry a note is a lie left for the next reader.

    Three corrections from the brief, all needed to make this test actually
    exercise what it claims to:

    1. ``run_test()``'s ``Pilot`` unmounts the whole widget tree on exit
       (``list(widget.children) == []`` afterwards, verified empirically),
       so ``_render_coins``'s ``widget`` return value can no longer be
       queried once the ``await`` that produced it has returned -- any
       selector against it then finds nothing, including
       ``#surf-lpc-note``, which would make the *first* assertion pass
       whether or not the note widget was actually gone. The query has to
       run while the app is still mounted, inside its own ``async with``.
    2. ``DOMQuery`` has no ``__eq__`` against a plain list (it compares
       unequal either way), so the presence check has to force the query
       into a concrete list first -- the same pattern already used
       elsewhere in this repo (``test_surf_widgets_b.py``'s
       ``not list(widget.query(...))``).
    3. This Textual version's ``Static`` exposes its content as
       ``.content``, not ``.renderable`` -- the brief's attribute name
       predates this repo's pinned Textual (8.1.1), where ``Static`` has no
       ``renderable`` at all.
    """
    from textual.widgets import Static

    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=_ROWS, coin_count=146)
        await pilot.pause()
        assert list(widget.query("#surf-lpc-note")) == []
        gap = widget.query_one("#surf-lpc-gap", Static)
        assert str(gap.content).strip() == ""


@pytest.mark.asyncio
async def test_the_widen_marker_still_follows_the_note_on_the_title_line() -> None:
    from maxpane_dashboard.widgets.surf.launchpad import (
        COINS_WIDEN_HINT, _TABLE_FULL_WIDTH,
    )

    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test(size=(_TABLE_FULL_WIDTH - 20, 24)) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=_ROWS, coin_count=146, as_of_hhmm="01:14")
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        # Segments join within a row first, rows join on "\n" -- see the
        # note on the same fix in `_render_coins`. A flat per-segment join
        # would split "LAUNCHPAD COINS" from its own widen marker onto two
        # "lines" even though both paint on one screen row.
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
    row = next(r for r in text.splitlines() if "LAUNCHPAD COINS" in r)
    assert COINS_WIDEN_HINT in row, row


# ---------------------------------------------------------------------------
# Fix round 1 -- .surf-lpc-title needs nowrap/ellipsis too
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_title_never_wraps_so_the_row_beneath_it_stays_blank() -> None:
    """Every other test in this file renders at 100 or 73 columns, both
    comfortably above the width where the unwrapped title's own text
    overruns the row -- so none of them could have caught this.

    ``.surf-lpc-title`` carried no ``text-wrap``/``text-overflow`` at all
    (unlike ``.surf-lpc-gap`` and the rail panels' own ``Static``s, which
    already had it): harmless while the title was always the short
    ``"LAUNCHPAD COINS  ‹ widen"``, but Task 3 put a variable-length note on
    that same row, and a long enough note wraps the title onto a second
    line -- which is the row the gap widget is supposed to own. Measured
    empirically against the real widget (not assumed): the disagreement
    note (``coin_count=146, launch_count=66``) is the widest of the three
    notes this panel renders, and without the CSS fix it wraps at width 62
    and clears at 63. 58 is comfortably inside the wrapping range with
    margin either side of that boundary.
    """
    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test(size=(58, 24)) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(
            coins=_ROWS, coin_count=146, launch_count=66, as_of_hhmm="01:14",
        )
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]

    i = next(n for n, row in enumerate(rows) if "LAUNCHPAD COINS" in row)
    assert rows[i + 1].strip() == "", rows[i + 1]


# ---------------------------------------------------------------------------
# Fix round 2 -- text-overflow: ellipsis silently ate the widen marker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_widen_marker_survives_the_whole_wrap_prone_width_band() -> None:
    """Round 1's fix traded a layout bug for an information-loss bug in the
    same width band.

    ``text-overflow: ellipsis`` alone stops the title from *wrapping*, but
    it does not know the ``‹ widen`` marker is more important than the note
    beside it -- so at exactly the widths where round 1's title (title +
    full note + marker, always) overran the row, the ellipsis clipped
    whatever came last, which was the marker itself. That is the silent-
    clipping failure this repo forbids outright, on the one panel whose
    entire job is to say a column got clipped.

    Neither of round 1's own tests could have caught it:
    ``test_the_title_never_wraps_so_the_row_beneath_it_stays_blank`` render
    at a single width (58) and only ever checked the row beneath was blank;
    ``test_the_widen_marker_still_follows_the_note_on_the_title_line``
    renders at 73, comfortably clear of the band the reviewer measured
    (45-52 for the plain note, 58-62 for the disagreement note, against
    round 1's title logic).

    This sweeps both payloads across the whole band (40-80) and asserts
    *two* things at every width: the row beneath the title is still blank
    (round 1's property, unbroken), and -- new this round -- whenever the
    panel is narrower than ``_TABLE_FULL_WIDTH`` the complete
    ``COINS_WIDEN_HINT`` string is present in the composited title row,
    never partially eaten.
    """
    from maxpane_dashboard.widgets.surf.launchpad import (
        COINS_WIDEN_HINT, _TABLE_FULL_WIDTH,
    )

    payloads = [
        {"coin_count": 146, "as_of_hhmm": "01:14"},  # plain note
        {"coin_count": 146, "launch_count": 66, "as_of_hhmm": "01:14"},  # disagreement note
    ]

    for kwargs in payloads:
        for width in range(40, 81):
            class _A(App):
                def compose(self):
                    yield SurfLaunchpadCoins()

            async with _A().run_test(size=(width, 24)) as pilot:
                widget = pilot.app.query_one(SurfLaunchpadCoins)
                widget.update_data(coins=_ROWS, **kwargs)
                await pilot.pause()
                strips = pilot.app.screen._compositor.render_strips()
                rows = ["".join(seg.text for seg in strip) for strip in strips]

            i = next(n for n, row in enumerate(rows) if "LAUNCHPAD COINS" in row)
            assert rows[i + 1].strip() == "", (kwargs, width, rows[i + 1])
            if width < _TABLE_FULL_WIDTH:
                assert COINS_WIDEN_HINT in rows[i], (kwargs, width, rows[i])


# ---------------------------------------------------------------------------
# Task 4 -- ten rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_table_draws_at_most_ten_coins() -> None:
    """The manager already re-caps ``launchpad_coins`` upstream
    (``LAUNCHPAD_RENDER_LIMIT``, ``data/surf_client.py``), but this widget
    re-caps defensively (``MAX_COIN_ROWS``) rather than trusting the payload
    never to grow past it -- 25 rows in, at most 10 rows out.

    Correction from the brief: its version queried
    ``widget.query_one(...)`` *after* ``_render_coins`` had returned, but
    ``run_test()``'s ``Pilot`` unmounts the whole widget tree on exit (the
    same trap ``test_the_gap_widget_replaced_the_note_widget`` above
    documents and corrects for), so any selector against the returned
    ``widget`` at that point finds nothing -- the query has to run while the
    app is still mounted, inside its own ``async with``.
    """
    from textual.widgets import DataTable

    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    rows = [dict(_ROW, ticker=f"C{i}", swaps_24h=100 - i) for i in range(25)]
    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=rows, coin_count=146)
        await pilot.pause()
        assert widget.query_one("#surf-lpc-table", DataTable).row_count == 10


# ---------------------------------------------------------------------------
# Task 7 -- MCAP replaces PRICE in the coin table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("usd, expected", [
    (23446.43, "$23.4K"),
    (999.0, "$999"),
    (1_250_000.0, "$1.3M"),
    (0.0, "$0"),          # a real, measured zero -- distinct from the dash
    (None, "--"),         # unread: price round failed, or eth_usd is None
])
def test_mcap_cell_formats(usd, expected) -> None:
    from maxpane_dashboard.widgets.surf.launchpad import _MCAP_COLS, _mcap_cell
    from rich.cells import cell_len
    rendered = _mcap_cell(usd)
    assert rendered == expected
    # A sized cell is not a fitted one: `len()` counts characters where the
    # terminal counts cells.
    assert cell_len(rendered) <= _MCAP_COLS


@pytest.mark.asyncio
async def test_the_table_shows_mcap_and_not_price() -> None:
    """Correction from the brief: its version queries
    ``widget.query_one(...)`` *after* ``_render_coins`` has returned, the
    same post-unmount trap ``test_the_gap_widget_replaced_the_note_widget``
    and ``test_the_table_draws_at_most_ten_coins`` above already correct for
    -- the query has to run while the app is still mounted.
    """
    from textual.widgets import DataTable

    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    row = dict(_ROW, mcap_usd=23446.43, mcap_eth=5.8616, price_eth=5.86e-09)
    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=[row], coin_count=146)
        await pilot.pause()
        headers = [str(c.label) for c in
                   widget.query_one("#surf-lpc-table", DataTable).columns.values()]
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)

    assert "MCAP" in headers
    assert "PRICE" not in headers
    assert "$23.4K" in text


@pytest.mark.asyncio
async def test_an_unpriced_coin_renders_a_dash_not_a_zero_mcap() -> None:
    row = dict(_ROW, mcap_usd=None, mcap_eth=None, price_eth=None)
    _widget, text = await _render_coins([row], coin_count=146)
    assert "$0" not in text


def test_mcap_cell_never_exceeds_its_own_column_budget() -> None:
    """``_mcap_cell``'s own docstring claims six columns is the genuine
    worst case, not merely the widest of the five hand-picked values in
    ``test_mcap_cell_formats`` -- this is the sweep that actually proves it,
    the same "measure, don't assume" standard ``_TABLE_FULL_WIDTH`` is held
    to elsewhere in this module.

    Caught two real defects in the brief's own naive one-decimal-always
    formatter while writing this: ``f"{v:.1f}"`` rounds half-to-*even*, so
    ``1_250_000.0`` (an exact tie at one decimal) came out ``"$1.2M"``, not
    the brief's own worked example ``"$1.3M"``; and the one-decimal form
    genuinely overruns six columns right at a tier boundary --
    ``999_949.0`` renders ``"$999.9K"``, seven columns, with no truncation
    marker of any kind (a ``DataTable`` cell has none), which is exactly the
    silent-clipping failure this repo forbids. Both are fixed in
    :func:`_round_half_up` and the digit-collapse in :func:`_mcap_cell`
    itself, not worked around here.

    Swept over a dense pseudo-random sample plus every exact tier boundary
    (using fractions most prone to a half-up/half-even disagreement or a
    round-trips-past-the-next-power-of-ten surprise), up to just under $1
    trillion -- several orders of magnitude past any real token's market
    cap, let alone a single internal launchpad coin's.
    """
    import random

    from rich.cells import cell_len

    from maxpane_dashboard.widgets.surf.launchpad import _MCAP_COLS, _mcap_cell

    rng = random.Random(0)
    values = [rng.uniform(0, 999_999_999_999) for _ in range(20_000)]
    for exp in range(0, 12):
        base = 10 ** exp
        for frac in (0.49999, 0.5, 0.50001, 0.94999, 0.95, 0.95001, 0.99999):
            values.append(base * (1 + frac) if base >= 1_000 else base + frac * base)

    for v in values:
        rendered = _mcap_cell(v)
        assert cell_len(rendered) <= _MCAP_COLS, (v, rendered)


def test_the_table_still_needs_exactly_seventy_five_columns():
    """MCAP replaces PRICE; the column-width sum is paid down 79 -> 75 by
    the four columns MCAP does not need (``_MCAP_COLS`` is 6, ``_PRICE_COLS``
    was 10) -- nothing else moved.  Supersedes
    ``test_the_table_still_needs_exactly_seventy_nine_columns`` (Task 11),
    which asserted the pre-MCAP sum and would now be asserting a stale
    number.
    """
    from maxpane_dashboard.widgets.surf import launchpad as lp

    assert (lp._TICKER_COLS + lp._NAME_COLS + lp._ADDR_COLS + lp._AGE_COLS
            + lp._MCAP_COLS + lp._PCT_COLS + lp._SWAPS_COLS
            + lp._SWAPS_ALL_COLS + lp._BURNED_COLS) == 75


# ---------------------------------------------------------------------------
# Carried-forward review finding -- the degraded-title tier inversion has no
# mirror test at a narrow width. ``_set_title``'s tier 2 normally sheds the
# note first (title > marker > note), but when ``coins is None`` the note
# *is* the ``⚠ launchpad unavailable`` warning and outranks the marker
# instead -- a flip of that priority in either direction would go undetected
# by the existing sweep, which only ever exercises well-formed payloads.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_unavailable_warning_outranks_the_widen_marker_when_both_dont_fit() -> None:
    """Mirror of ``test_the_widen_marker_survives_the_whole_wrap_prone_width_
    band`` for the degraded case: at a narrow width, with ``coins=None``, the
    ``COINS_UNAVAILABLE`` warning must survive and the ``‹ widen`` marker
    must be what gets shed -- the opposite tier-2 choice from every other
    payload this module renders, and the one the existing sweep (well-formed
    payloads only) cannot see flip.

    44-52 is comfortably inside the band the reviewer measured for this
    title's overflow (round 2's own 45-52/58-62 bands, for the plain/
    disagreement notes respectively) -- narrow enough that title + warning +
    marker cannot all fit, so tier 2 is what actually renders.
    """
    from maxpane_dashboard.widgets.surf.launchpad import (
        COINS_UNAVAILABLE, COINS_WIDEN_HINT,
    )

    for width in range(44, 53):
        class _A(App):
            def compose(self):
                yield SurfLaunchpadCoins()

        async with _A().run_test(size=(width, 24)) as pilot:
            widget = pilot.app.query_one(SurfLaunchpadCoins)
            widget.update_data(coins=None, coin_count=None, as_of_hhmm="01:14")
            await pilot.pause()
            strips = pilot.app.screen._compositor.render_strips()
            rows = ["".join(seg.text for seg in strip) for strip in strips]

        i = next(n for n, row in enumerate(rows) if "LAUNCHPAD COINS" in row)
        assert COINS_UNAVAILABLE in rows[i], (width, rows[i])
        assert COINS_WIDEN_HINT not in rows[i], (width, rows[i])
