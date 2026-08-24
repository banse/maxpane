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
#: columns need ``launchpad._TABLE_FULL_WIDTH`` (93) before the last of them
#: reaches a pixel, so at 80 the ``SW ALL`` header and every ``swaps_all``
#: value are clipped by the compositor and *no* assertion in this file could
#: see them. That is not hypothetical: this module rendered at 80 until
#: 2026-08-24, so Task 11's whole ``SW ALL`` column could have been deleted
#: with these tests green. 100 clears 93 with room to spare and keeps the
#: panel's own ``‹ widen`` marker unlit, which is the state the column
#: assertions want to measure.
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
    """
    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test(size=_RENDER_SIZE) as pilot:
        widget = pilot.app.query_one(SurfLaunchpadCoins)
        widget.update_data(coins=coins, **kwargs)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        text = "\n".join(seg.text for strip in strips for seg in strip)
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
        text = "\n".join(seg.text for strip in strips for seg in strip)
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
        text = "\n".join(seg.text for strip in strips for seg in strip)
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


def test_the_table_still_needs_exactly_seventy_nine_columns():
    """The new column is paid for by shortening CREATOR, not by widening the
    panel. Raising a width constant is reserved for when no honest short
    form exists, and a truncated address is an honest short form.
    """
    from maxpane_dashboard.widgets.surf import launchpad as lp

    assert (lp._TICKER_COLS + lp._NAME_COLS + lp._ADDR_COLS + lp._AGE_COLS
            + lp._PRICE_COLS + lp._PCT_COLS + lp._SWAPS_COLS
            + lp._SWAPS_ALL_COLS + lp._BURNED_COLS) == 79


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
