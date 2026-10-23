"""The Sworn screen sends selection intent and retains cached popup state."""
from copy import deepcopy
from pathlib import Path
import pytest

from textual.app import App
from textual.widgets import DataTable, Input

from maxpane_dashboard.screens.sworn_screen import SwornScreen
from maxpane_dashboard.widgets.sworn.explorer import SwornExplorer
from maxpane_dashboard.widgets.sworn.details import SwornDetailScreen
from tests.widgets.test_sworn_explorer import payload, painted


class Manager:
    def __init__(self):
        self.payload = payload(); self.calls = 0; self.selections = []
    def get_snapshot(self):
        return deepcopy(self.payload)
    def select(self, value):
        self.selections.append(value)
    def is_loading(self, view=None):
        return False
    async def fetch_and_compute(self):
        self.calls += 1
        return self.get_snapshot()


class Harness(App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'
    def __init__(self):
        super().__init__(); self.manager = Manager()
    def on_mount(self):
        self.push_screen(SwornScreen(self.manager))


async def settle(pilot, predicate):
    for _ in range(12):
        await pilot.pause()
        if predicate():
            return
    assert predicate()


async def test_enter_popup_escape_returns_same_card_and_lookup_remains_editable():
    app = Harness()
    async with app.run_test(size=(149, 45)) as pilot:
        screen = app.screen
        await settle(pilot, lambda: screen.query_one(SwornExplorer).selected is not None)
        assert 'SWORN #10' in painted(app)
        await pilot.press('enter')
        assert isinstance(app.screen, SwornDetailScreen)
        assert app.screen.row['token_id'] == 10
        await pilot.press('escape')
        assert app.screen is screen
        assert screen.query_one(SwornExplorer).selected['token_id'] == 10
        await pilot.press('/')
        await pilot.press('n', 'p', 'r', 'f')
        assert screen.query_one(Input).value == 'nprf'


async def test_row_selection_blanks_old_identity_until_matching_response_and_icon_opens():
    app = Harness()
    async with app.run_test(size=(149, 45)) as pilot:
        screen = app.screen
        await settle(pilot, lambda: screen.query_one(SwornExplorer).selected is not None)
        table = screen.query_one(DataTable)
        table.move_cursor(row=1)
        await settle(pilot, lambda: app.manager.selections == ['9'])
        panel = screen.query_one(SwornExplorer)
        assert panel.selected is None
        screen.action_inspect_card(9)
        new = deepcopy(app.manager.payload)
        new['sworn_selection'] = '9'
        new['sworn_selected']['token_id'] = 9
        panel.update_data(**new)
        await settle(pilot, lambda: isinstance(app.screen, SwornDetailScreen))
        assert app.screen.row['token_id'] == 9


async def test_main_fit_and_narrow_view_preserve_scroll_access():
    async with Harness().run_test(size=(149, 45)) as pilot:
        panel = pilot.app.screen.query_one(SwornExplorer)
        await settle(pilot, lambda: panel.selected is not None)
        assert panel.query_one('#sworn-body').region.right <= 149
        assert panel.query_one('#sworn-content').max_scroll_y == 0
        await pilot.resize_terminal(80, 45)
        assert panel.has_class('compact')
        assert panel.query_one('#sworn-content').max_scroll_y > 0


async def test_visible_row_chevron_opens_that_card():
    async with Harness().run_test(size=(149, 45)) as pilot:
        screen = pilot.app.screen
        panel = screen.query_one(SwornExplorer)
        await settle(pilot, lambda: panel.selected is not None)
        table = panel.query_one(DataTable)
        for y in range(table.region.y, table.region.bottom):
            line = screen._compositor.render_strips()[y].text
            x = line.find('»', table.region.x, table.region.right)
            if x >= 0:
                await pilot.click(offset=(x, y))
                break
        else:
            raise AssertionError('No row chevron painted')
        assert isinstance(pilot.app.screen, SwornDetailScreen)
        assert pilot.app.screen.row['token_id'] == 10


async def test_checksummed_claimant_lookup_matches_reader_normalization():
    async with Harness().run_test(size=(149, 45)) as pilot:
        screen = pilot.app.screen
        panel = screen.query_one(SwornExplorer)
        await settle(pilot, lambda: panel.selected is not None)
        value = '0x' + 'AbCd' * 10
        screen._select('  ' + value + '  ')
        assert pilot.app.manager.selections[-1] == value.lower()
        response = payload()
        response['sworn_selection'] = value.lower()
        response['sworn_selected']['claimant'] = value.lower()
        panel.update_data(**response)
        await pilot.pause()
        assert panel.selected['claimant'] == value.lower()
        assert 'SWORN #10' in painted(pilot.app)


@pytest.mark.parametrize('width', [104, 105, 106])
async def test_responsive_boundary_preserves_fixed_labels_and_table_columns(width):
    async with Harness().run_test(size=(width, 45)) as pilot:
        panel = pilot.app.screen.query_one(SwornExplorer)
        await settle(pilot, lambda: panel.selected is not None)
        assert panel.has_class('compact') == (width < 105)
        table = panel.query_one(DataTable)
        assert table.virtual_size.width <= table.size.width
        assert panel.query_one('#sworn-body').region.right <= width
        if not panel.has_class('compact'):
            assert '» ARTWORK & SOURCE DETAILS' in painted(pilot.app)
            assert 'WALLET FACTS' in painted(pilot.app)


@pytest.mark.parametrize('width', [80, 149])
async def test_short_terminal_can_scroll_to_all_body_content(width):
    async with Harness().run_test(size=(width, 20)) as pilot:
        panel = pilot.app.screen.query_one(SwornExplorer)
        await settle(pilot, lambda: panel.selected is not None)
        assert panel.max_scroll_y > 0
        panel.scroll_end(animate=False)
        await pilot.pause()
        viewport = panel.query_one('#sworn-content')
        assert viewport.region.bottom <= 19
        facts = panel.query_one('#sworn-facts')
        viewport.scroll_to(y=facts.region.y - viewport.region.y + viewport.scroll_y, animate=False)
        await pilot.pause()
        assert 'WALLET FACTS' in painted(pilot.app)
