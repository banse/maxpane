"""Four saved assignments route through one native screen without cross-slot writes."""
import pytest
from textual.widgets import Input

from maxpane_dashboard import config
from maxpane_dashboard.screens.surf import MODE_AGENT
from maxpane_dashboard.widgets.surfboard import SurfboardRack
from tests.screens.test_surfboard_screen import HubManager, hub_app
from tests.surfboard_fixtures import hub_payload


class SeatManager(HubManager):
    def __init__(self, seats):
        super().__init__()
        self.seats = tuple(seats)
        self.seat = self.seats[0]

    def get_hub_seats(self):
        return self.seats

    def set_hub_seats(self, seats):
        self.seats = tuple(seats)

    async def fetch_hub_snapshot(self):
        payload = hub_payload()
        keys = ('agent', 'agent-2', 'agent-3', 'agent-4')
        payload['surfboard_cards'] = [c for c in payload['surfboard_cards'] if c['key'] not in keys]
        for slot, (key, token) in enumerate(zip(keys, self.seats)):
            payload['surfboard_cards'].append(dict(
                key=key, title='AGENT', seat_slot=slot, token_id=token,
                primary='' if token is None else f'IDMD #{token}',
                secondary='type in seat no' if token is None else '0 of 3 slots',
                status='empty' if token is None else 'idle',
                meter_state='empty' if token is None else 'idle', meter_kind='activity',
                numerator=43200, denominator=86400,
                destination=None if token is None else MODE_AGENT))
        return payload


@pytest.fixture
def seat_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '_CONFIG_DIR', tmp_path)
    monkeypatch.setattr(config, '_CONFIG_FILE', tmp_path / 'config.toml')
    return tmp_path / 'config.toml'


def app_with_seats(seats):
    app, _ = hub_app()
    manager = SeatManager(seats)
    app._surf_manager = manager
    return app, manager


async def test_open_each_saved_card_selects_its_seat_without_persisting(seat_config, monkeypatch):
    app, manager = app_with_seats((420, 516, 0, 1649))
    writes = []
    monkeypatch.setattr(config, 'save_seat', writes.append)
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        native = None
        for slot, key in enumerate(('agent', 'agent-2', 'agent-3', 'agent-4')):
            hub.query_one(SurfboardRack).focus_card(key)
            await pilot.press('enter')
            assert app.screen.name == 'surf'
            assert app.screen._mode == MODE_AGENT
            assert manager.seat == manager.seats[slot]
            assert app.screen._agent_slot == slot
            native = native or app.screen
            assert app.screen is native
            await pilot.press('escape')
            assert app.screen is hub
            assert manager.seats == (420, 516, 0, 1649)
            assert manager.seat == 420
        assert writes == []
        assert not seat_config.exists()


@pytest.mark.parametrize('slot', range(4))
async def test_empty_input_saves_only_its_assignment_without_opening(slot, seat_config):
    app, manager = app_with_seats((None, None, None, None))
    key = ('agent', 'agent-2', 'agent-3', 'agent-4')[slot]
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        rack = hub.query_one(SurfboardRack)
        rack.focus_card(key)
        await pilot.press('enter')
        field = hub.query_one(f'#surfboard-card-{key}').query_one(Input)
        assert app.focused is field
        field.value = '#0'
        await pilot.press('enter')
        await pilot.pause()
        expected = tuple(0 if index == slot else None for index in range(4))
        assert manager.seats == expected
        assert config.get_surfboard_seats() == expected
        assert app.screen is hub
        assert hub.query_one(f'#surfboard-card-{key}').data['token_id'] == 0
        assert not field.display


async def test_secondary_prompt_updates_its_origin_then_native_entry_restores_primary(seat_config):
    for slot, token in enumerate((420, 516, 0, 1649)):
        config.save_surfboard_seat(slot, token)
    app, manager = app_with_seats(config.get_surfboard_seats())
    async with app.run_test(size=(149, 45)) as pilot:
        app.open_surf_mode(MODE_AGENT, token_id=516, seat_slot=1)
        await pilot.press('i')
        field = app.screen.query_one('#wi-input', Input)
        assert field.value == '516'
        field.value = '527'
        await pilot.press('enter')
        assert app.screen.name == 'surf'
        assert manager.seat == 527
        assert config.get_surfboard_seats() == manager.seats == (420, 527, 0, 1649)
        # Programmatic/leaderboard selection uses the same originating slot.
        app.screen.select_seat(999)
        assert config.get_surfboard_seats() == manager.seats == (420, 999, 0, 1649)
        await pilot.press('m', '1')
        assert app.screen.name == 'surf' and app.screen._agent_slot == 0
        assert manager.seat == 420
        app.screen.select_seat(3)
        assert config.get_surfboard_seats() == manager.seats == (3, 999, 0, 1649)


async def test_invalid_submission_and_failed_save_preserve_empty_draft(seat_config, monkeypatch):
    app, manager = app_with_seats((420, None, None, None))
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        hub = app.screen
        rack = hub.query_one(SurfboardRack)
        rack.focus_card('agent-2')
        await pilot.press('enter')
        field = app.focused
        field.value = '#'
        await pilot.press('enter')
        assert app.screen is hub and app.focused is field
        assert manager.seats == (420, None, None, None)
        assert not seat_config.exists()
        painted = '\n'.join(strip.text for strip in hub._compositor.render_strips())
        assert 'invalid seat no' in painted

        def fail_save(*_args):
            raise OSError('read-only config')

        monkeypatch.setattr(config, 'save_surfboard_seat', fail_save)
        field.value = '516'
        await pilot.pause()
        assert 'invalid seat no' not in '\n'.join(strip.text for strip in hub._compositor.render_strips())
        await pilot.press('enter')
        await hub._do_refresh()
        await pilot.pause()
        assert app.screen is hub and field.value == '516'
        assert manager.seats == (420, None, None, None)
        assert not seat_config.exists()
        assert 'save failed' in '\n'.join(strip.text for strip in hub._compositor.render_strips())
