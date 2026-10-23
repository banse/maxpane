"""Sworn is reachable without enabling an unmocked reader in app tests."""
import pytest
from maxpane_dashboard.app import MaxPaneApp
from maxpane_dashboard.screens.game_select import GAMES


def test_sworn_is_a_visible_game_and_reader_factory_is_lazy():
    assert GAMES[-1][0:2] == ('10', 'sworn')
    assert MaxPaneApp._GAME_CYCLE[-1] == 'sworn'
    app = MaxPaneApp(initial_game='sworn')
    assert app._sworn_manager.key == 'sworn'
    assert app._reader.thread is None


@pytest.mark.asyncio
async def test_zero_menu_shortcut_opens_tenth_dashboard_without_network():
    from tests.test_app_startup import MANAGER_ATTRS, BoomManager
    app = MaxPaneApp()
    for name in MANAGER_ATTRS:
        setattr(app, name, BoomManager())
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.press('0')
        await pilot.pause()
        assert app.screen.name == 'sworn'
        assert app.screen.GAME_NAME == 'SWORN'


def test_sworn_payload_contract_is_unique():
    from maxpane_dashboard.data.sworn_models import SWORN_KEYS, empty_payload
    assert len(SWORN_KEYS) == len(set(SWORN_KEYS))
    payload = empty_payload()
    assert set(payload) == set(SWORN_KEYS)
    assert payload['sworn_supply'] is None
    assert payload['sworn_rows'] == []
