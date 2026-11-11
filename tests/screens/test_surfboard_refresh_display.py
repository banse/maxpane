"""Pending reads must not repaint loaded cards with intermediate snapshots."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from maxpane_dashboard.widgets.surfboard.rack import SurfboardCard
from maxpane_dashboard.data.reader import ReaderHandle
from tests.screens.test_surfboard_layout import HubHarness
from tests.surfboard_fixtures import HubPayloadManager, hub_payload


class PendingManager(HubPayloadManager):
    busy = False

    def is_loading(self, view=None):
        return self.busy

    def get_hub_snapshot(self):
        return deepcopy(self.payload)


def harness():
    payload = hub_payload()
    rows = {row['key']: row for row in payload['surfboard_cards']}
    rows['agent'].update(token_id=650, primary='IDMD #650', secondary='0 of 1 slots',
                         status='paused', meter_state='not_accepting', meter_kind='presence')
    app = HubHarness(payload)
    manager = PendingManager(payload)
    app.hub._data_manager = manager
    return app, manager


def painted(app, key):
    card = app.hub.query_one(f'#surfboard-card-{key}', SurfboardCard)
    return [tuple((segment.text, str(segment.style)) for segment in
                  row.crop(card.region.x, card.region.right)) for row in
            app.hub._compositor.render_strips()[card.region.y:card.region.bottom]]


@pytest.mark.parametrize('size', [(143, 37), (149, 45)])
@pytest.mark.parametrize('interim', ['stale', 'loading'])
async def test_pending_snapshot_keeps_every_card_text_and_ink_until_completion(size, interim):
    app, manager = harness()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        keys = [card.key for card in app.hub.query(SurfboardCard)]
        before = {key: painted(app, key) for key in keys}
        completed = deepcopy(manager.payload)
        manager.busy = True
        for row in manager.payload['surfboard_cards']:
            row.update(status=interim, primary='999', secondary='99 working',
                       numerator=0, points=[0] * 8)
        raw = deepcopy(manager.payload)
        await app.hub._do_refresh()
        await pilot.pause()
        assert {key: painted(app, key) for key in keys} == before
        assert manager.payload == raw
        for key in ('board', 'work', 'oracles'):
            assert app.hub.query_one(f'#surfboard-card-{key}').data['status'] == interim

        rows = {row['key']: row for row in completed['surfboard_cards']}
        for key, caption in [('board', 'working'), ('work', 'working'), ('oracles', 'agents')]:
            rows[key].update(status='idle', primary='0', secondary=f'0 {caption}')
        manager.payload, manager.busy = completed, False
        await app.hub._do_refresh()
        await pilot.pause()
        for key, caption in [('board', 'working'), ('work', 'working'), ('oracles', 'agents')]:
            assert painted(app, key) != before[key]
            card = app.hub.query_one(f'#surfboard-card-{key}')
            assert card._display_data['primary'] == '0'
            assert card._display_data['status'] == 'idle'
            assert f'0 {caption}' in '\n'.join(''.join(text for text, _ in line) for line in painted(app, key))


async def test_pending_snapshot_never_keeps_a_previous_seat_identity():
    app, manager = harness()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        row = next(row for row in manager.payload['surfboard_cards'] if row['key'] == 'agent')
        card = app.hub.query_one('#surfboard-card-agent')
        manager.busy = True
        row.update(token_id=7, primary='IDMD #7', secondary='— of — slots',
                   status='loading', meter_state='unknown')
        await app.hub._do_refresh()
        await pilot.pause()
        assert card._display_data['primary'] == 'IDMD #7'
        assert 'NOT ACCEPTING' not in '\n'.join(''.join(text for text, _ in line) for line in painted(app, 'agent'))
        row.update(token_id=None, primary='', secondary='type in', status='empty', meter_state='empty')
        await app.hub._do_refresh()
        await pilot.pause()
        assert card.empty_seat and card.query_one('Input').display
        assert 'EMPTY SEAT' in '\n'.join(''.join(text for text, _ in line) for line in painted(app, 'agent'))


async def test_completed_failure_applies_after_pending_read_and_cold_cards_can_populate():
    app, manager = harness()
    manager.busy = True
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        card = app.hub.query_one('#surfboard-card-board')
        assert card._display_data['primary'] == '863'
        before = painted(app, 'board')
        row = next(row for row in manager.payload['surfboard_cards'] if row['key'] == 'board')
        row.update(status='unavailable', primary='—', secondary='— working')
        await app.hub._do_refresh()
        await pilot.pause()
        assert painted(app, 'board') == before
        manager.busy = False
        app.hub._set_loading(False)
        # Completion metadata may arrive before the final projection is dispatched.
        # Do not briefly paint the last intermediate failure in that gap.
        assert card._display_data['status'] == 'active'
        await pilot.pause()
        assert card._display_data['status'] == 'unavailable'
        assert card._display_data['primary'] == '863'
        assert painted(app, 'board') != before


async def test_stopping_view_during_read_does_not_schedule_another_projection():
    app, manager = harness()
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        manager.busy = True
        app.hub._set_loading(True)
        app.hub.start_refresh = Mock()
        app.hub._stop_view()
        app.hub.start_refresh.assert_not_called()


@pytest.mark.parametrize('new_revision', [True, False])
async def test_reader_completion_paints_final_snapshot_without_requesting_another_read(new_revision):
    app, manager = harness()
    handle = ReaderHandle(Mock(), 'surf', {})
    app.hub._data_manager = handle
    async with app.run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        def publish(payload, busy):
            handle._publish(handle._generation, deepcopy(payload), {}, {}, busy)
            app.hub._tick_loading()
        publish(manager.payload, False)
        await app.workers.wait_for_complete()
        await pilot.pause()
        before = painted(app, 'board')
        pending = deepcopy(manager.payload)
        row = next(row for row in pending['surfboard_cards'] if row['key'] == 'board')
        row.update(status='stale', primary='0', secondary='0 working')
        publish(pending, True)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert painted(app, 'board') == before
        reads = handle.runtime._submit.call_count
        if new_revision:
            row['status'] = 'idle'
        publish(pending, False)
        assert app.hub.query_one('#surfboard-card-board')._display_data['status'] == 'active'
        await app.workers.wait_for_complete()
        await pilot.pause()
        card = app.hub.query_one('#surfboard-card-board')
        assert card._display_data['status'] == ('idle' if new_revision else 'stale')
        assert card._display_data['primary'] == '0'
        assert painted(app, 'board') != before
        assert handle.runtime._submit.call_count == reads
