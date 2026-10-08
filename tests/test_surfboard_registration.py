"""Dashboard 9 shares SURF ownership while retaining every existing menu key."""
import pytest

from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.game_select import GAMES, GameSelectScreen
from tests.screens.test_surfboard_screen import hub_app

pytestmark = pytest.mark.guard


def test_hub_is_ninth_entry_and_cycle_keeps_first_eight():
    expected = ["surf", "curator", "fwa", "base", "frenpet", "cattown", "ttt", "talismans", "surfboard"]
    assert [row[1] for row in GAMES] == expected
    assert [row[0] for row in GAMES] == [str(n) for n in range(1, 10)]
    assert GAMES[-1][2] == "SURFBOARD HUB"
    assert MaxPaneApp._GAME_CYCLE == expected


def test_prefetch_alias_and_manager_ownership_remain_shared():
    app, _ = hub_app()
    assert app._prefetch_manager("surfboard") is app._surf_manager
    assert app._prefetch_manager("surf") is app._surf_manager
    assert not hasattr(app, "_surfboard_manager")


@pytest.mark.asyncio
@pytest.mark.mounts_app
async def test_menu_nine_cycle_eight_nine_one_and_exact_once_close():
    app, managers = hub_app(initial_game="talismans")
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.press("tab")
        assert app.screen.name == "surfboard"
        assert app._current_game == "surfboard"
        await pilot.press("tab")
        assert app.screen.name == "surf"
        await pilot.press("m")
        assert isinstance(app.screen, GameSelectScreen)
        await pilot.press("9")
        assert app.screen.name == "surfboard"
        await pilot.press("q")
    assert all(manager.closed == 1 for manager in managers.values())
