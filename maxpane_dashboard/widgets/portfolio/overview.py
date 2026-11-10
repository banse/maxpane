"""Portfolio A: a local projection of the retained wallet scan."""
from __future__ import annotations

from rich.text import Text
from textual.containers import Grid, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.swarm_portfolio import project
from maxpane_dashboard.widgets.address import ICON_COLS, address_prose, address_text
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase, TableLeaderboard
from maxpane_dashboard.widgets.rowfit import clip
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord
from maxpane_dashboard.widgets.surf.pool4_hero import Pool4HeroCard
from maxpane_dashboard.widgets.swarm_tokens import _quantity, _usd
from .filter import PortfolioFilterEditor

#: Scan assets carry their own chain IDs; the API reads Ethereum and Robinhood.
EXPLORER = for_chain_id
CHAIN_NAMES = {1: 'ETH', 8453: 'BASE', 4663: 'RH'}


def chain_name(value):
    return CHAIN_NAMES.get(value, str(value) if value is not None else '—')


def token_cell(row, width=14, *, contract=False):
    label = flatten((row.get('name') if contract else row.get('symbol')) or row.get('name'))
    return address_text(row.get('token_address') or row.get('contract_address'), width=max(1, width - ICON_COLS),
                        label=label or ('Token' if row.get('token_address') else 'Contract'),
                        explorer=EXPLORER(row.get('chain_id')))


def sale_text(row):
    value = row.get('sellable_pct')
    if isinstance(value, (int, float)):
        return f'{value:.0f}%'
    state = flatten(row.get('sell_state'))
    return 'limited' if state == 'partial' else state or '—'


class PortfolioHeroCard(Pool4HeroCard):
    """Unknown source facts stay unknown; the manager alone retains old facts."""

    def set_record(self, data):
        super().set_record(data)
        self.tooltip = Text(flatten(data.title) + ' · as of ' + hhmm(data.read_ts, unknown='—'))
        if data.key == 'pf-total':
            self.tooltip = Text('Source estimate of combined wallet, stake and reward proceeds. '
                                'Net proceeds are not guaranteed. · as of ' + hhmm(data.read_ts, unknown='—'))

    def _footer(self):
        self.border_subtitle = ''

    def _present_record(self, data):
        return data

    def count_caption(self, value):
        return value

    def _subtitle_value(self, value):
        return value


def hero_records(metrics=None, snapshot=None):
    metrics, snapshot = metrics or {}, snapshot or {}
    def count(key):
        value = metrics.get(key)
        return f'{value:,}' if isinstance(value, int) else '—'
    definitions = (
        ('total', 'TOTAL VALUE', 'known value' if metrics.get('partial') else 'combined value', 'total_usd', 'USD'),
        ('wallet', 'WALLET', count('holding_count') + ' tokens', 'wallet_usd', 'USD'),
        ('staked', 'STAKED', count('position_count') + ' positions', 'staked_usd', 'USD'),
        ('unclaimed', 'UNCLAIMED', count('claim_count') + ' rewards', 'unclaimed_usd', 'USD'),
        ('nfts', 'NFTS', 'OWNED', 'nft_count', count('nft_collections') + ' collections'),
        ('seats', 'SEATS', 'OWNED', 'seats_count', 'Identity.md'),
    )
    for key, title, heading, metric, subtitle in definitions:
        value = metrics.get(metric)
        digits = '' if value is None else (f'{int(value):,}' if value >= 100 or float(value).is_integer() else f'{value:.2f}')
        if len(digits) > 7:
            digits = _quantity(value)
        yield HeroRecord('pf-' + key, title, heading, '', subtitle=subtitle,
                         digits=digits, accent=False,
                         state=snapshot.get('seats_state' if key == 'seats' else 'state') or 'loading',
                         read_ts=snapshot.get('seats_as_of' if key == 'seats' else 'as_of'))


class PortfolioTable(TableLeaderboard):
    """The same selection and table mechanics for each finite scan collection."""
    ROW_CAP = None

    def __init__(self, kind, title, columns, **kwargs):
        self.kind, self.TITLE, self.COLUMNS = kind, title, columns
        self.TABLE_ID = 'pf-' + kind + '-table'
        self.EMPTY_ROW = tuple(Text('—' if index == 0 else '') for index in range(len(columns)))
        self.rows = []
        super().__init__(**kwargs)

    def build_row(self, index, row):
        kind = self.kind
        if kind == 'holdings':
            values = (token_cell(row), chain_name(row.get('chain_id')),
                      _quantity(row.get('wallet_quantity')), _usd(row.get('wallet_usd')),
                      _usd(row.get('total_usd')), sale_text(row))
        elif kind == 'rewards':
            values = (token_cell(row, 11), row.get('status', 'unknown'),
                      _quantity(row.get('quantity')), _usd(row.get('value_usd')),
                      row.get('source_name') or row.get('kind'))
        elif kind == 'stakes':
            values = (token_cell(row, 18, contract=True), chain_name(row.get('chain_id')),
                      _quantity(row.get('quantity')), _usd(row.get('value_usd')),
                      _usd(row.get('pending_usd')), self.apr(row))
        elif kind == 'utilities':
            values = (token_cell(row, 17, contract=True), row.get('kind'), row.get('role'),
                      'yes' if row.get('joined') is True else 'no' if row.get('joined') is False else '—')
        else:
            values = (token_cell(row, 24), chain_name(row.get('chain_id')),
                      _quantity(row.get('count')), ', '.join(str(value) for value in (row.get('token_ids') or [])[:6]))
        return tuple(value if isinstance(value, Text) else address_prose(clip(flatten(value) or '—', width),
                     explorer=EXPLORER(row.get('chain_id')))
                     for value, (_, width) in zip(values, self.COLUMNS))

    @staticmethod
    def apr(row):
        value = row.get('apr')
        return f'{value:.1f}%' if isinstance(value, (float, int)) else '—'

    def update_rows(self, rows, selected=None):
        table = self.query_one(DataTable)
        previous = self.row_at(table.cursor_row)
        if selected is None and previous is not None:
            selected = previous.get('id')
        self.rows = rows if isinstance(rows, list) else []
        self.EMPTY_ROW = tuple(Text(('—' if rows is None else 'None') if index == 0 else '')
                               for index in range(len(self.COLUMNS)))
        self.render_table(self.rows)
        index = next((i for i, row in enumerate(self.rows) if row.get('id') == selected), 0)
        table.move_cursor(row=index, animate=False)

    def row_at(self, index):
        return self.rows[index] if 0 <= index < len(self.rows) else None


class PortfolioEvidence(PanelBase):
    TITLE = 'SEATS & ELIGIBILITY'

    def compose_body(self):
        with VerticalScroll(id='pf-evidence-scroll'):
            yield Static(Text('—'), id='pf-evidence', classes='panel-line')


class SwarmPortfolioOverview(VerticalScroll):
    DEFAULT_CSS = '''
    SwarmPortfolioOverview {height: 1fr; overflow: auto auto; scrollbar-gutter: stable; padding: 1 1;}
    SwarmPortfolioOverview #pf-layout {min-width: 143; height: 1fr; min-height: 34;}
    SwarmPortfolioOverview #pf-heroes {height: 9; grid-size: 6 1; grid-columns: 1fr; grid-rows: 9; grid-gutter: 0 1;}
    SwarmPortfolioOverview #pf-filter-editor {height: 1fr; min-height: 25; display: none;}
    SwarmPortfolioOverview #pf-panels {height: 1fr; min-height: 25; grid-size: 2 3; grid-columns: 3fr 2fr; grid-rows: 9fr 8fr 6fr; grid-gutter: 1 1;}
    SwarmPortfolioOverview PortfolioTable, SwarmPortfolioOverview PortfolioEvidence {height: 1fr; min-height: 5;}
    SwarmPortfolioOverview PortfolioTable > .panel-title {height: 1; text-wrap: nowrap; text-overflow: ellipsis;}
    SwarmPortfolioOverview DataTable {height: 1fr; min-height: 2; scrollbar-gutter: stable;}
    SwarmPortfolioOverview #pf-evidence-scroll {height: 1fr; scrollbar-gutter: stable;}
    SwarmPortfolioOverview #pf-evidence {height: auto; padding: 0 1;}
    '''

    class Inspect(Message):
        def __init__(self, row, snapshot, record_kind):
            super().__init__()
            self.row, self.snapshot, self.record_kind = row, snapshot, record_kind

    def __init__(self, *, view_state=None, **kwargs):
        super().__init__(**kwargs)
        self.view_state = view_state if isinstance(view_state, dict) else {}
        self.snapshot, self.projection = {}, {}
        self.selected_id = self.view_state.get('selected_id')

    def compose(self):
        with Vertical(id='pf-layout'):
            with Grid(id='pf-heroes'):
                for record in hero_records():
                    yield PortfolioHeroCard(record)
            yield PortfolioFilterEditor(scan=True, id='pf-filter-editor')
            with Grid(id='pf-panels'):
                yield PortfolioTable('holdings', 'HOLDINGS', (('TOKEN',14),('CHAIN',5),('WALLET',10),('WALLET $',10),('TOTAL $',10),('SALE',7)))
                yield PortfolioTable('rewards', 'UNCLAIMED REWARDS', (('TOKEN',11),('STATE',7),('AMOUNT',8),('VALUE',8),('SOURCE',10)))
                yield PortfolioTable('stakes', 'STAKES', (('POSITION',18),('CHAIN',5),('STAKED',10),('VALUE',10),('PENDING',10),('APR',7)))
                yield PortfolioTable('utilities', 'TOKEN UTILITIES', (('SELECTED TOKEN',17),('KIND',12),('ROLE',10),('JOINED',6)))
                yield PortfolioTable('nfts', 'NFT INVENTORY', (('COLLECTION',24),('CHAIN',5),('OWNED',8),('TOKEN IDS',28)))
                yield PortfolioEvidence()

    def on_mount(self):
        self.update_data(snapshot=self.snapshot)

    def update_data(self, *, snapshot=None):
        self.snapshot = snapshot if isinstance(snapshot, dict) else {}
        self._project()

    def _project(self):
        filters = {key: self.view_state.get(key, default) for key, default in
                   (('chain','all'),('query',''),('show_no_sale',False),('sort','value'))}
        self.projection = project(self.snapshot, **filters)
        metrics = self.projection.get('metrics') or {}
        for record in hero_records(metrics, self.snapshot):
            self.query_one('#hero-' + record.key, PortfolioHeroCard).set_record(record)
        holdings = self.projection.get('holdings')
        if not any(row.get('id') == self.selected_id for row in holdings or []):
            self.selected_id = (holdings or [{}])[0].get('id')
        self.view_state['selected_id'] = self.selected_id
        for panel in self.query(PortfolioTable):
            key = 'positions' if panel.kind == 'stakes' else panel.kind
            rows = holdings if panel.kind == 'holdings' else self.projection.get(key)
            if panel.kind == 'utilities' and rows is not None:
                rows = [row for row in rows if row.get('asset_id') == self.selected_id]
            panel.update_rows(rows, self.selected_id if panel.kind == 'holdings' else None)
        self._evidence(metrics)
        chain = {'all': 'All chains', '1': 'Ethereum', '8453': 'Base', '4663': 'Robinhood'}[filters['chain']]
        sort = 'Token A–Z' if filters['sort'] == 'symbol' else 'Value ↓'
        sale = 'Show no-sale' if filters['show_no_sale'] else 'Hide no-sale'
        text = Text('HOLDINGS  ', style='bold')
        text.append(f'FILTER · {chain} · {sort} · {sale}', style='not bold dim')
        if filters['query']:
            text.append(' · search: ' + flatten(filters['query']), style='not bold dim')
        title = self.query_one('#pf-holdings-table').parent.query_one('.panel-title', Static)
        title.update(text)
        title.tooltip = text

    def _evidence(self, metrics):
        text = Text('Seats  ', style='dim')
        seats = metrics.get('seat_ids')
        text.append('—' if metrics.get('seats_count') is None else
                    ', '.join('#'+str(value) for value in seats) if seats else 'None')
        if self.snapshot.get('seats_as_of') is not None:
            text.append(' · as of '+hhmm(self.snapshot['seats_as_of']))
        text.append('\nRead  '+(hhmm(self.snapshot.get('as_of')) if self.snapshot.get('as_of') else '—'))
        for chain in self.snapshot.get('chains') or []:
            text.append(f" · {chain_name(chain.get('chain_id'))} #{chain.get('block') or '—'}")
        standings = self.projection.get('standings')
        for row in standings or []:
            text.append('\n')
            text.append_text(token_cell(row, 20))
            for field in row.get('fields') or []:
                text.append('  '+flatten(field.get('name'))+' ')
                text.append_text(address_prose(flatten(field.get('value')), explorer=EXPLORER(row.get('chain_id'))))
        if not standings:
            text.append('\nEligibility  —' if standings is None else '\nNo recorded standings')
        self.query_one('#pf-evidence', Static).update(text)

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id != 'pf-holdings-table':
            return
        row = event.data_table.parent.row_at(event.cursor_row)
        if row and row.get('id') != self.selected_id:
            self.selected_id = self.view_state['selected_id'] = row['id']
            panel = next(panel for panel in self.query(PortfolioTable) if panel.kind == 'utilities')
            rows = self.projection.get('utilities')
            panel.update_rows([item for item in rows if item.get('asset_id') == self.selected_id] if rows is not None else None)

    def on_data_table_row_selected(self, event):
        panel = event.data_table.parent
        if not isinstance(panel, PortfolioTable):
            return
        row = panel.row_at(event.cursor_row)
        if row:
            asset = row if panel.kind == 'holdings' else next((item for item in self.projection.get('assets') or []
                          if panel.kind != 'nfts' and item.get('id') == row.get('asset_id')), None)
            kind = 'assets' if asset is not None else 'positions' if panel.kind == 'stakes' else panel.kind
            self.post_message(self.Inspect(asset if asset is not None else row, self.projection, kind))

    def focus_selection(self):
        self.query_one('#pf-holdings-table', DataTable).focus()
