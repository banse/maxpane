"""Seat-only cursor retention is shared by every row-selectable panel."""
import copy

import pytest
from textual.widgets import DataTable

from maxpane_dashboard.widgets import seat as widgets
from tests.address_sweep.builders import _seat_app, _seat_payload
from tests.screens.test_seat_round9_navigation import strips


def assert_cursor_painted(screen, table):
    y = table.region.y + table.header_height + table.cursor_row - int(table.scroll_y)
    assert table.region.y <= y < table.region.bottom
    assert screen.get_style_at(table.region.x + 2, y).bgcolor == table.get_component_rich_style('datatable--cursor').bgcolor


@pytest.mark.parametrize('name, dashboard, key, identity', [
    ('SeatSkills', '3', 'seat_skills_rows', 'id'),
    ('SeatRecords', '4', 'seat_records_rows', 'key'),
    ('SeatNodes', '5', 'seat_nodes_all_rows', 'nodeKey'),
])
async def test_every_selectable_table_retains_identity_on_insert_resize_and_show(name, dashboard, key, identity):
    assert hasattr(widgets, name), name
    flat = _seat_payload()
    flat[key] = [{identity: f'row-{i:02d}', 'nodeKey': f'row-{i:02d}', 'on': True,
                  'jobId': 'b1fb1439-7d2e-4a0f-8c3b-9e5d1f2a6b70', 'attempts': i+1} for i in range(50)]
    app = _seat_app(flat)
    async with app.run_test(size=(134, 30)) as pilot:
        await pilot.pause()
        await pilot.press(dashboard)
        await pilot.pause()
        panel = app.screen.query_one(getattr(widgets, name))
        table = panel.query_one(DataTable)
        assert table.cursor_type == 'row'
        table.move_cursor(row=22)
        await pilot.pause()
        selected = panel.selected_row()[identity]
        scroll = table.scroll_y
        anchor = panel._seat_rows[int(scroll)][identity]
        flat[key].insert(0, {identity: 'new-row', 'nodeKey': 'new-row', 'on': False})
        await app.screen._do_refresh()
        await pilot.pause()
        assert panel.selected_row()[identity] == selected
        assert table.scroll_y == scroll + 1
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert panel.selected_row()[identity] == selected
        assert table.scroll_y == scroll + 1
        await pilot.press('2', dashboard)
        await pilot.pause()
        assert panel.selected_row()[identity] == selected
        assert table.scroll_y == scroll + 1
        assert selected in '\n'.join(strips(app.screen)) or name == 'SeatRecords'
        assert_cursor_painted(app.screen, table)
        # Hidden refresh rebuilds the table too; retain its saved viewport until
        # the body is shown, even if more than one hidden refresh arrives.
        await pilot.press('2')
        await pilot.pause()
        flat[key].insert(0, {identity: 'hidden-row', 'nodeKey': 'hidden-row', 'on': False})
        await app.screen._do_refresh()
        await app.screen._do_refresh()
        await pilot.press(dashboard)
        await pilot.pause()
        assert panel.selected_row()[identity] == selected
        assert table.scroll_y == scroll + 2
        assert anchor in strips(app.screen)[table.region.y + table.header_height]
        assert_cursor_painted(app.screen, table)
        # Once restored, a user's new viewport must become the next anchor.
        table.scroll_to(y=scroll + 3, animate=False, immediate=True)
        await pilot.pause()
        moved_anchor = panel._seat_rows[int(table.scroll_y)][identity]
        await app.screen._do_refresh()
        await pilot.pause()
        assert table.scroll_y == scroll + 3
        assert moved_anchor in strips(app.screen)[table.region.y + table.header_height]
        assert_cursor_painted(app.screen, table)


async def test_config_table_retains_setting_after_refresh():
    flat = _seat_payload()
    flat['seat_host_kind'] = 'docker'
    async with _seat_app(flat).run_test(size=(132,22)) as pilot:
        await pilot.pause()
        await pilot.press('3')
        await pilot.pause()
        panel = pilot.app.screen.query_one(widgets.SeatConfig)
        table = panel.query_one(DataTable)
        assert table.cursor_type == 'row'
        table.move_cursor(row=next(i for i,r in enumerate(panel._seat_rows) if r['key']=='boot'))
        await pilot.pause()
        table.scroll_to(y=4,animate=False,immediate=True)
        await pilot.pause()
        selected = panel.selected_row()['key']
        selected_index = table.cursor_row
        top = table.scroll_y
        anchor = panel._seat_rows[int(top)]['setting']
        # The wrapper appears above the selected boot row but below the viewport's
        # top (daemon); preserve both identities, so only the cursor index increases.
        flat['seat_host_kind'] = 'systemd'
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        assert panel.selected_row()['key'] == selected
        assert table.cursor_row == selected_index + 1
        assert table.scroll_y == top
        await pilot.resize_terminal(100,22)
        await pilot.pause()
        assert panel.selected_row()['key'] == selected
        assert table.cursor_row == selected_index + 1
        assert table.scroll_y == top
        await pilot.press('2','3')
        await pilot.pause()
        assert panel.selected_row()['key'] == selected
        assert table.cursor_row == selected_index + 1
        assert table.scroll_y == top
        assert anchor in strips(pilot.app.screen)[table.region.y + table.header_height]
        table.scroll_to(y=table.max_scroll_y,animate=False,immediate=True)
        await pilot.pause()
        assert_cursor_painted(pilot.app.screen, table)
        await pilot.press('up')
        await pilot.pause()
        assert table.cursor_row == selected_index
        assert_cursor_painted(pilot.app.screen, table)
