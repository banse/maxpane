"""Pure widgets for the dedicated Built by Swarm token dashboard."""
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.address import address_text, is_address, job_text, short_hex, site_text
from maxpane_dashboard.widgets.fmt import as_float, fmt_int, hhmm, mmdd
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase, TableLeaderboard
from maxpane_dashboard.widgets.surf._fmt import JOB_EXPLORER, SITE_EXPLORER
from maxpane_dashboard.widgets.swarm_tokens import _chart, _change, _paired, _quantity, _usd
from ._fmt import EXPLORER, cell, line, metric_label, prose, source, source_label, title, token_source
from .hero import DetailHero

__all__ = ['DetailHero', 'LaunchSummary', 'ContributorTable', 'MarketPanel', 'PositionPanel', 'ArtifactTable']


class _TextPanel(PanelBase):
    DEFAULT_CSS = '''
    _TextPanel {height: 1fr; min-height: 3; border: none;}
    _TextPanel > VerticalScroll {height: 1fr; overflow-x: hidden; scrollbar-size: 1 1;}
    _TextPanel .detail-body {height: auto; padding: 0 1; link-color: $foreground;}
    '''

    def compose_body(self):
        with VerticalScroll():
            yield Static(Text('unavailable'), classes='detail-body')

    def on_resize(self):
        if hasattr(self, '_data'):
            self.update_data(**self._data)

    def body(self, rows):
        self.write('.detail-body', Text('\n').join(rows))


class LaunchSummary(_TextPanel):
    TITLE = 'LAUNCH'
    DEFAULT_CSS = '''
    LaunchSummary > .token-objective {height: 2; margin-bottom: 1;}
    LaunchSummary #token-launch-objective {height: auto; padding: 0 1; link-color: $foreground;}
    '''

    def compose_body(self):
        with VerticalScroll(classes='token-objective'):
            yield Static(Text('objective   --'), id='token-launch-objective')
        yield from super().compose_body()

    def update_data(self, *, token=None, launch=None, sources=None, is_mock=False):
        self._data = dict(token=token, launch=launch, sources=sources, is_mock=is_mock)
        token, launch = token or {}, launch or {}
        title(self, source(sources, 'launch'))
        chain = launch.get('chain_id', token.get('chain_id'))
        stamp = launch.get('recorded_ts')
        site = site_text(launch.get('site_ens_name'), 70, label=launch.get('site_label'),
                         explorer=None if is_mock else SITE_EXPLORER)
        self.write('#token-launch-objective', line('objective', launch.get('objective'), chain))
        self.body([
            line('status', launch.get('status'), chain),
            line('verdict', launch.get('verdict'), chain),
            line('recorded', mmdd(stamp, unknown='--') + ' ' + hhmm(stamp, unknown='--:--')),
            line('site', site), line('repository', launch.get('repo_url'), chain),
        ])
        self.tooltip.append('\nRecord time is the launch request time, not deployment time.')


class MarketPanel(_TextPanel):
    TITLE = 'MARKET · 24H'

    def update_data(self, *, token=None):
        self._data = dict(token=token)
        token = token or {}
        title(self, token_source(token, 'market'))
        history = token_source(token, 'history')
        room = max(2, self.content_size.width - 3)
        pool = token.get('market_pool')
        pool_text = address_text(pool, width=max(11, room - 14), explorer=EXPLORER(token.get('chain_id'))) if is_address(pool) else cell(pool, room - 12)
        self.body([
            Text(_chart(token, room), style='green'),
            Text('history ' + source_label(history), style='dim'),
            line('source', token.get('market_source')),
            line('price', _usd(token.get('price_usd'), price=True)),
            line('change', _change(token.get('change_24h'))),
            line('buys / sells', _quantity(token.get('buys_24h')) + ' / ' + _quantity(token.get('sells_24h'))),
            line('FDV', _usd(token.get('fdv_usd'))), line('pool', pool_text),
        ])
        self.tooltip.append('\nQuotes, volume and buys/sells describe the selected indexed pool.\nHourly price samples preserve gaps.\nSource: ' + flatten(token.get('market_source')))


class PositionPanel(_TextPanel):
    TITLE = 'LAUNCH POSITION'

    def update_data(self, *, token=None):
        self._data = dict(token=token)
        token = token or {}
        title(self, token_source(token, 'liquidity'))
        chain = token.get('chain_id')
        label = 'token' if is_address(token.get('symbol')) else flatten(token.get('symbol')) or 'token'
        # Address-valued asset identifiers have their own linked row below.
        rows = [line(label, _quantity(token.get('token_amount'))), line('paired', _paired(token)),
                line('state', token.get('lp_state'), chain)]
        for label, key in (('fee', 'fee_pct'), ('withdrawn', 'withdrawn_pct')):
            value = as_float(token.get(key))
            rows.append(line(label, '--' if value is None else f'{value:g}%'))
        pool = token.get('launch_pool')
        if pool:
            rows.append(line('pool', address_text(pool, width=24, explorer=EXPLORER(chain)) if is_address(pool) else prose(short_hex(pool, 24), chain)))
        if is_address(token.get('paired_symbol')):
            rows.append(line('paired token', address_text(token['paired_symbol'], width=24, explorer=EXPLORER(chain))))
        self.body(rows)
        self.tooltip.append('\nBalances describe the original launch position, independently of the selected market pool.')


class _DetailTable(TableLeaderboard):
    ROW_CAP = None
    DEFAULT_CSS = '''
    _DetailTable {height: 1fr; border: none;}
    _DetailTable > DataTable {height: 1fr; scrollbar-size: 1 1; color: $foreground;
        link-color: $foreground;}
    _DetailTable > .detail-table-status {height: auto; padding: 0 1;}
    '''

    def compose_body(self):
        yield Static(Text(''), classes='detail-table-status')
        yield from super().compose_body()

    def show(self, rows, item, empty):
        title(self, item)
        self.render_table(rows)
        status = self.query_one('.detail-table-status', Static)
        status.display = not rows
        self.query_one(DataTable).display = bool(rows)
        if not rows:
            message = 'unavailable' if rows is None else empty
            status.update(Text(message, style='dim'))


class ContributorTable(_DetailTable):
    TITLE = 'CONTRIBUTING AGENTS'
    TABLE_ID = 'token-contributors-table'
    COLUMNS = (('seat', 8), ('role', 16), ('job', 12), ('state', 24))

    def update_data(self, *, contributors=None, sources=None):
        item = source(sources, 'contributors')
        self.show(contributors, item, 'No accepted contributors' if item['state'] == 'ok' else 'No contributors loaded')
        self.tooltip.append('\nAccepted non-oracle seats only; rows identify seat, role and job. Partial coverage is a lower bound.')

    def build_row(self, index, item):
        if not isinstance(item, dict):
            return None
        return (cell('#' + fmt_int(item.get('seat')), 8), cell(item.get('role'), 16),
                job_text(item.get('job_id'), 12, explorer=JOB_EXPLORER), cell(item.get('state'), 24))


class ArtifactTable(_DetailTable):
    TITLE = 'ARTIFACTS'
    TABLE_ID = 'token-artifacts-table'
    COLUMNS = (('type', 10), ('name', 30), ('address / destination', 70))

    def update_data(self, *, token=None, artifacts=None, sources=None, is_mock=False):
        self._token, self._mock = token or {}, is_mock
        self.show(artifacts, source(sources, 'artifacts'), 'No artifacts' if not is_mock else 'No connected artifacts in mock data')

    def build_row(self, index, item):
        if not isinstance(item, dict):
            return None
        chain = item.get('chain_id', self._token.get('chain_id'))
        explorer = None if self._mock else EXPLORER(chain)
        address = item.get('address')
        name = address_text(address, label=metric_label(item.get('name')), width=28, explorer=explorer) if is_address(address) else cell(item.get('name'), 30, chain)
        if item.get('kind') == 'site':
            destination = site_text(item.get('site_ens_name'), 70, label=item.get('site_label'), explorer=None if self._mock else SITE_EXPLORER)
        else:
            destination = address_text(address, width=68, explorer=explorer)
        return cell(item.get('kind'), 10), name, destination
