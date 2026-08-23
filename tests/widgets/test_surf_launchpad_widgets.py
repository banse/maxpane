import pytest
from textual.app import App

from maxpane_dashboard.widgets.surf.launchpad import (
    SurfBurnPipeline, SurfCurveFlow, SurfLaunchpadCoins,
)

HOSTILE = {
    "ticker": "[/x]", "name": "[bold red]pwn[/]", "creator": "0xdead",
    "creator_known": False, "age_s": 60.0, "price_eth": 0.0071,
    "change_1h_pct": 34.0, "swaps_1h": 88, "imd_burned": 142.1,
}


@pytest.mark.asyncio
async def test_hostile_ticker_and_name_never_reach_markup() -> None:
    """launch(string,string) is permissionless: anyone can name a coin `[/x]`.

    Asserted against composited output -- a string that never reaches a pixel
    passes a naive content-string test while being invisible to the user.
    """
    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test() as pilot:
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
    quiet = HOSTILE | {"ticker": "Q", "name": "Quiet", "change_1h_pct": None,
                       "swaps_1h": 0}

    class _A(App):
        def compose(self):
            yield SurfLaunchpadCoins()

    async with _A().run_test() as pilot:
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

    async with _A().run_test() as pilot:
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

    async with _A().run_test() as pilot:
        widget = pilot.app.query_one(SurfBurnPipeline)
        widget.update_data(burn_accrued=None, burn_staged=None, burn_ready=None,
                           burned_total=None, burn_events=None)
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        assert "ready" not in "\n".join(seg.text for s in strips for seg in s)
