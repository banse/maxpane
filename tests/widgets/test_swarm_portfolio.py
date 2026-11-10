from copy import deepcopy

import pytest
from textual.app import App

from maxpane_dashboard.widgets.portfolio.overview import SwarmPortfolioOverview, token_cell
from maxpane_dashboard.widgets.portfolio.inspector import SwarmPortfolioInspector


WALLET = '0x' + '12' * 20
TOKEN = '0x' + '34' * 20


def portfolio_snapshot():
    asset = dict(id='1:' + TOKEN, chain_id=1, token_address=TOKEN, symbol='ALPHA', name='Alpha',
                 wallet_quantity=1400, wallet_usd=700, staked_quantity=0, staked_usd=0,
                 ready_quantity=100, ready_usd=50, locked_quantity=0, locked_usd=0,
                 pending_quantity=0, pending_usd=0, unknown_reward_quantity=0, unknown_reward_usd=0,
                 total_usd=750, sell_state='partial', sellable_pct=37, pool={}, connections=[], source={})
    return dict(wallet=WALLET, state='ok', as_of=1794237045, assets=[asset], positions=[],
                rewards=[dict(id='reward-1', asset_id=asset['id'], chain_id=1, token_address=TOKEN,
                              symbol='ALPHA', quantity=100, value_usd=50, status='ready',
                              source_name='Launch reward', kind='Launch reward', site_url=None)],
                nfts=[], standings=[], utilities=[], chains=[dict(chain_id=1, block=123)],
                coverage=dict(claims_complete=True, malformed_rows=0, contracts_scanned=1, hidden_count=0),
                error=None)


class OverviewApp(App):
    def __init__(self):
        super().__init__()
        from maxpane_dashboard.themes import THEMES
        self.register_theme(THEMES['matrix'])
        self.theme = 'matrix'

    def compose(self):
        yield SwarmPortfolioOverview()


def painted(app):
    return '\n'.join(strip.text for strip in app.screen._compositor.render_strips())


def test_long_token_names_reserve_the_copy_icon_inside_the_column():
    from maxpane_dashboard.widgets.address import parse_copy_action
    row = dict(token_address=TOKEN, chain_id=1, symbol='非常に長いトークンの名前')
    value = token_cell(row, 11)
    assert value.cell_len <= 11
    assert value.plain.endswith(' ⧉')
    assert any(parse_copy_action((span.style.meta or {}).get('@click')) == TOKEN for span in value.spans)


def test_model_snapshot_and_widget_signature_agree():
    import inspect
    import json
    from pathlib import Path
    from maxpane_dashboard.data.swarm_portfolio_client import normalize_result
    from maxpane_dashboard.data.swarm_portfolio_manager import SwarmPortfolioManager
    from maxpane_dashboard.data.swarm_portfolio_models import SNAPSHOT_KEYS, WIDGET_SIGNATURES, empty_snapshot
    parameters = inspect.signature(SwarmPortfolioOverview.update_data).parameters
    keywords = tuple(name for name, value in parameters.items() if value.kind == value.KEYWORD_ONLY)
    assert keywords == WIDGET_SIGNATURES['SwarmPortfolioOverview']
    assert set(empty_snapshot()) == set(SNAPSHOT_KEYS)
    assert set(SwarmPortfolioManager(client=object()).get_snapshot()) == set(SNAPSHOT_KEYS)
    raw = json.loads((Path(__file__).parents[1] / 'fixtures/portfolio_scan/captured.json').read_text())
    normalized = normalize_result(raw, raw['wallet']['address'], now=raw['at'])
    assert set(normalized) == set(SNAPSHOT_KEYS)


async def test_overview_paints_approved_sections_and_keeps_unknown_unknown():
    async with OverviewApp().run_test(size=(149, 45)) as pilot:
        overview = pilot.app.query_one(SwarmPortfolioOverview)
        overview.update_data(snapshot=portfolio_snapshot())
        await pilot.pause()
        output = painted(pilot.app)
        for label in ('TOTAL VALUE', 'WALLET', 'STAKED', 'UNCLAIMED', 'NFTS', 'SEATS',
                      'HOLDINGS', 'UNCLAIMED REWARDS', 'STAKES', 'NFT INVENTORY', 'SEATS & ELIGIBILITY'):
            assert label in output
        assert 'TOKEN UTILITIES' not in output
        assert 'ALPHA' in output and '37%' in output and '$700' in output
        empty = {key: None for key in portfolio_snapshot()}
        empty.update(wallet='0x' + '56' * 20, state='loading')
        overview.update_data(snapshot=empty)
        await pilot.pause()
        output = painted(pilot.app)
        assert 'ALPHA' not in output
        assert '0 tokens' not in output
        assert 'Seats  —' in output
        assert overview.query_one('#hero-pf-total').data.digits == ''


async def test_first_four_cards_paint_active_frames_and_digits_only(monkeypatch):
    from rich.color import Color
    monkeypatch.delenv('NO_COLOR', raising=False)
    async with OverviewApp().run_test(size=(149,45)) as pilot:
        app = pilot.app
        app.query_one(SwarmPortfolioOverview).update_data(snapshot=portfolio_snapshot())
        await pilot.pause()
        green = Color.parse(app.get_css_variables()['accent']).get_truecolor()
        digit_color = app.ansi_theme.ansi_colors[2]
        for key in ('total', 'wallet', 'staked', 'unclaimed', 'nfts', 'seats'):
            card = app.query_one('#hero-pf-' + key)
            rows = [strip.crop(card.region.x, card.region.right)
                    for strip in app.screen._compositor.render_strips()[card.region.y:card.region.bottom]]
            top = next(index for index, row in enumerate(rows) if '┌' in row.text)
            active = key in ('total', 'wallet', 'staked', 'unclaimed')
            frames = [segment for segment in rows[top] if '┌' in segment.text]
            assert frames and all((segment.style.color.get_truecolor() == green) == active for segment in frames)
            if active:
                bottom = rows[top + 4]
                usd = bottom.crop(bottom.text.index('USD'), bottom.text.index('USD') + 3)
                assert all(segment.style.color.get_truecolor() == green for segment in usd)
                left, right = rows[top].text.index('┌'), rows[top].text.index('┐')
                digits = [segment for row in rows[top + 1:top + 4]
                          for segment in row.crop(left + 1, right) if segment.text.strip()]
                assert digits and all(segment.style.color.get_truecolor() == digit_color for segment in digits)
                assert all(segment.style.color.get_truecolor() != green for segment in rows[-1] if segment.text.strip())


async def test_inspector_is_native_popup_and_preserves_safe_address_actions():
    from maxpane_dashboard.screens.record_detail import RecordDetailScreen
    snapshot = portfolio_snapshot()
    snapshot['assets'][0]['name'] = '[bold] literal'
    async with OverviewApp().run_test(size=(149, 45)) as pilot:
        modal = SwarmPortfolioInspector(snapshot['assets'][0], snapshot)
        pilot.app.push_screen(modal)
        await pilot.pause()
        assert isinstance(modal, RecordDetailScreen)
        output = painted(pilot.app)
        assert 'WHERE IT SITS' in output and 'ONE COMBINED VALUATION' in output
        assert 'Wallet' in output and '$700' in output and '37%' in output
        assert 'PRESS SPACE OR ESC TO CLOSE' in output
        assert modal.query_one('.record-detail-box').region.width == 110
        assert '⧉' in output
        await pilot.press('escape')
        assert pilot.app.screen is not modal


async def test_inspector_master_list_changes_token_without_fetch_or_closing():
    from textual.widgets import DataTable, Static
    snapshot = portfolio_snapshot()
    second = deepcopy(snapshot['assets'][0])
    second.update(id='4663:' + '0x' + '78' * 20, chain_id=4663,
                  token_address='0x' + '78' * 20, symbol='BETA',
                  unknown_reward_quantity=3, unknown_reward_usd=8, ready_quantity=0, ready_usd=0)
    snapshot['assets'].append(second)
    async with OverviewApp().run_test(size=(149,45)) as pilot:
        modal = SwarmPortfolioInspector(snapshot['assets'][0], snapshot)
        pilot.app.push_screen(modal)
        await pilot.pause()
        table = modal.query_one('#pf-inspector-table', DataTable)
        table.focus()
        await pilot.press('down')
        assert pilot.app.screen is modal
        assert modal.row['id'] == second['id']
        assert 'readiness unknown' in painted(pilot.app)
        assert 'BETA' in str(modal.query_one('.record-detail-title', Static).render())


async def test_stakes_and_selected_utilities_use_contract_identity_and_nfts_open_own_facts():
    from textual.widgets import DataTable
    snapshot = portfolio_snapshot()
    contract = '0x' + 'ab' * 20
    snapshot['positions'] = [dict(id='position', asset_id=snapshot['assets'][0]['id'], chain_id=1,
        contract_address=contract, name='Alpha vault', symbol='ALPHA', quantity=50, value_usd=25,
        pending_usd=2, apr=3.5)]
    snapshot['utilities'] = [dict(snapshot['positions'][0], kind='Stake', role='takes', joined=True)]
    nft = dict(id='collection', chain_id=1, contract_address=contract, name='Collectible',
               symbol='NFT', count=2, token_ids=['7','9'])
    snapshot['nfts'] = [nft]
    async with OverviewApp().run_test(size=(149,45)) as pilot:
        overview = pilot.app.query_one(SwarmPortfolioOverview)
        overview.update_data(snapshot=snapshot)
        await pilot.pause()
        assert 'Alpha vault' in painted(pilot.app)
        assert overview.query_one('#pf-stakes-table', DataTable).row_count == 1
        modal = SwarmPortfolioInspector(nft, snapshot)
        pilot.app.push_screen(modal)
        await pilot.pause()
        assert modal.row['id'] == nft['id']
        assert 'NFT INVENTORY' in painted(pilot.app)
        assert 'Token IDs  7, 9' in painted(pilot.app)


@pytest.mark.parametrize('width', [75,80,93,94,110,147,149])
async def test_native_inspector_stacks_at_measured_address_boundary_and_keeps_provenance_reachable(width):
    from pathlib import Path
    from tests.widgets.address_probe import icon_targets
    class ThemedOverview(OverviewApp):
        CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'
    snapshot = portfolio_snapshot()
    async with ThemedOverview().run_test(size=(width,45)) as pilot:
        modal = SwarmPortfolioInspector(snapshot['assets'][0], snapshot)
        pilot.app.push_screen(modal)
        await pilot.pause()
        workspace = modal.query_one('#pf-inspector-workspace')
        inventory = modal.query_one('#pf-inspector-inventory')
        detail = modal.query_one('#pf-inspector-details')
        assert workspace.has_class('stacked') == (width < 94)
        assert modal.query_one('.record-detail-box').region.width == min(width,110)
        if width < 94:
            assert inventory.region.bottom < detail.region.y
        else:
            assert inventory.region.right < detail.region.x
        output = painted(pilot.app)
        address_line = next(line for line in output.splitlines() if 'Token  ' in line)
        assert TOKEN + ' ⧉' in address_line
        assert any(target == TOKEN for _,_,target in icon_targets(pilot.app))
        detail.scroll_end(animate=False)
        await pilot.pause()
        assert 'READ PROVENANCE' in painted(pilot.app)
        assert 'PRESS SPACE OR ESC TO CLOSE' in painted(pilot.app)
        await pilot.press('escape')
        assert pilot.app.screen is not modal


@pytest.mark.parametrize('size', [(75,24),(80,30)])
async def test_short_stacked_modal_keeps_bottom_evidence_and_close_hint_reachable(size):
    from pathlib import Path
    class ThemedOverview(OverviewApp):
        CSS_PATH = Path(__file__).parents[2] / 'maxpane_dashboard/themes/minimal.tcss'
    snapshot = portfolio_snapshot()
    async with ThemedOverview().run_test(size=size) as pilot:
        modal = SwarmPortfolioInspector(snapshot['assets'][0], snapshot)
        pilot.app.push_screen(modal)
        await pilot.pause()
        modal.query_one('.record-detail-scroll').scroll_end(animate=False)
        modal.query_one('#pf-inspector-details').scroll_end(animate=False)
        await pilot.pause()
        assert 'READ PROVENANCE' in painted(pilot.app)
        assert 'PRESS SPACE OR ESC TO CLOSE' in painted(pilot.app)
        await pilot.press('space')
        assert pilot.app.screen is not modal


@pytest.mark.parametrize('collection,heading', [('positions','STAKE / DEPOSIT'),('rewards','UNCLAIMED REWARD'),('utilities','TOKEN UTILITY')])
async def test_unresolved_records_keep_their_kind_and_known_value(collection,heading):
    snapshot = portfolio_snapshot()
    row = dict(id='unresolved',asset_id=None,chain_id=1,contract_address='0x'+'ab'*20,
               name='Unknown vault',quantity=None,value_usd=25,tvl_usd=25,role='takes',joined=True)
    snapshot[collection] = [row]
    async with OverviewApp().run_test(size=(149,45)) as pilot:
        modal = SwarmPortfolioInspector(row,snapshot)
        pilot.app.push_screen(modal)
        await pilot.pause()
        box = modal.query_one('.record-detail-box').region
        output = '\n'.join(strip.crop(box.x,box.right).text
                           for strip in modal._compositor.render_strips()[box.y:box.bottom])
        assert heading in output and 'NFT INVENTORY' not in output
        assert 'Unknown vault' in output and '$25' in output


async def test_seats_keep_their_independent_observation_state_and_clock():
    from maxpane_dashboard.widgets.fmt import hhmm
    snapshot = portfolio_snapshot()
    snapshot.update(state='stale',as_of=100,seats=[dict(token_id='7')],seats_state='ok',seats_as_of=200)
    async with OverviewApp().run_test(size=(149,45)) as pilot:
        overview = pilot.app.query_one(SwarmPortfolioOverview)
        overview.update_data(snapshot=snapshot)
        await pilot.pause()
        card = overview.query_one('#hero-pf-seats')
        assert card.data.state == 'ok' and card.data.read_ts == 200
        assert 'Seats  #7 · as of '+hhmm(200) in painted(pilot.app)


async def test_failed_source_retains_facts_without_generated_failure_notice():
    snapshot = portfolio_snapshot()
    snapshot.update(state='stale',error='timeout')
    async with OverviewApp().run_test(size=(149,45)) as pilot:
        overview = pilot.app.query_one(SwarmPortfolioOverview)
        overview.update_data(snapshot=snapshot)
        await pilot.pause()
        output = painted(pilot.app)
        assert 'Last read failed' not in output and 'Read failed' not in output
        assert 'ALPHA' in output
        assert overview.snapshot['error'] == 'timeout' and overview.snapshot['state'] == 'stale'
