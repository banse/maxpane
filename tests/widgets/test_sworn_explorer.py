"""Sworn presentation contracts use synthetic facts, never a live provider."""
from copy import deepcopy
import inspect
from pathlib import Path

from textual.app import App
from textual.widgets import DataTable, Input

from maxpane_dashboard.data.sworn_models import WIDGET_SIGNATURES
from maxpane_dashboard.widgets.sworn.explorer import SwornExplorer


CLAIMANT = '0x' + '1' * 40
HOLDER = '0x' + '2' * 40


def payload():
    return dict(sworn_supply=10, sworn_rows=[{'token_id': 10, 'families': 2},
                {'token_id': 9, 'families': None}], sworn_selection=None,
                sworn_error=None, sworn_block=123, sworn_observed_at=1000,
                sworn_selected={'token_id': 10, 'claimant': CLAIMANT, 'holder': HOLDER,
                    'minted_at_block': 100, 'block': 123, 'observed_at': 1000,
                    'art': None, 'metadata': {'traits': [101, 201, 202],
                        'community': [10001], 'oracle': [], 'attributes': [
                            {'trait_type': 'Spawned', 'value': 'held'},
                            {'trait_type': 'Zero-Shot', 'value': 'rare'},
                            {'trait_type': 'Community 10001', 'value': '[red]literal'},
                            {'trait_type': 'community_count', 'value': 40}]}})


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


class Harness(App):
    CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'
    def compose(self):
        yield SwornExplorer()


def test_named_signature_matches_frozen_contract_and_widgets_are_render_only():
    assert tuple(inspect.signature(SwornExplorer.update_data).parameters)[1:] == WIDGET_SIGNATURES['SwornExplorer']
    for path in (Path(__file__).parents[2] / 'maxpane_dashboard/widgets/sworn').glob('*.py'):
        assert 'maxpane_dashboard.data' not in path.read_text()


async def test_artwork_uses_hero_and_input_space_with_wallet_identities_visible():
    async with Harness().run_test(size=(149, 45)) as pilot:
        panel = pilot.app.query_one(SwornExplorer)
        panel.update_data(**payload())
        await pilot.pause()
        output = painted(pilot.app)
        for word in ('CARDS', 'WALLET FACTS', 'Claimant', 'Holder', 'SWORN #10', 'w wallet'):
            assert word in output
        assert not panel.query(Input)
        assert not panel.query('LocalSourceHeroCard')
        assert 'COLLECTION' not in output and 'SELECTED' not in output
        assert panel.query_one('#sworn-art').size.height >= 37
        assert output.count('⧉') == 2
        assert '0x111' in output and '0x222' in output
        table = panel.query_one(DataTable)
        assert table.get_row('9')[1].plain == '—'
        assert table.get_row('10')[-1].plain == '»'


async def test_new_selection_cannot_paint_previous_card_or_open_it():
    async with Harness().run_test(size=(149, 45)) as pilot:
        panel = pilot.app.query_one(SwornExplorer)
        old = payload()
        panel.update_data(**old)
        panel.request('9')
        panel.update_data(**old)
        await pilot.pause()
        assert panel.selected is None
        assert 'SWORN #10' not in painted(pilot.app)
        new = deepcopy(old)
        new['sworn_selection'] = '9'
        new['sworn_selected']['token_id'] = 9
        panel.update_data(**new)
        await pilot.pause()
        assert panel.selected['token_id'] == 9
        assert 'SWORN #9' in painted(pilot.app)
