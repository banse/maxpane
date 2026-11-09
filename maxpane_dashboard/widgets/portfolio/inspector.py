"""Portfolio B inside the shared native record modal; no live reads."""
from copy import deepcopy
from urllib.parse import urlsplit

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Static

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.address import address_prose, address_text, is_address
from maxpane_dashboard.widgets.fmt import hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.surf_nft.detail import source_text, source_url
from maxpane_dashboard.widgets.swarm_tokens import _quantity, _usd
from .overview import EXPLORER, chain_name, sale_text, token_cell


#: Measured in the native frame with production CSS at 45 terminal rows.
#: A 94-column frame leaves 88 content columns for the workspace.
#: Inventory uses 33, the inter-column margin two, and detail receives 53.
#: Its reserved scrollbar takes two, leaving 51 for Token + address + icon.
#: At 93 columns that address's copy icon wraps onto the following line.
#: Use the actual content room: a short modal may spend another scrollbar.
#: Below this threshold inventory stacks above detail; both scroll internally.
#: The boundary is tested at 93/94 and owner examples 75, 80, 110, 147, 149.
SIDE_BY_SIDE_CONTENT_COLUMNS = 88


class SwarmPortfolioInspector(RecordDetailScreen):
    ID_PREFIX = 'pf-inspector'
    DEFAULT_CSS = '''
    SwarmPortfolioInspector #pf-inspector-workspace {height: 1fr; min-height: 24;}
    SwarmPortfolioInspector #pf-inspector-inventory {width: 33; height: 1fr; margin-right: 2;}
    SwarmPortfolioInspector #pf-inspector-inventory-title {height: 2;}
    SwarmPortfolioInspector #pf-inspector-table {height: 1fr; min-height: 3; scrollbar-gutter: stable;}
    SwarmPortfolioInspector #pf-inspector-details {height: 1fr; width: 1fr; scrollbar-gutter: stable;}
    SwarmPortfolioInspector #pf-inspector-facts {height: auto;}
    SwarmPortfolioInspector #pf-inspector-workspace.stacked {layout: vertical;}
    SwarmPortfolioInspector .stacked #pf-inspector-inventory {width: 1fr; height: 9; margin: 0 0 1 0;}
    '''

    def __init__(self, row, snapshot, *, record_kind=None):
        super().__init__(row)
        self.snapshot = deepcopy(snapshot)
        self.record_kind = record_kind or next((kind for kind in ('assets','positions','rewards','utilities','nfts')
            if any(item.get('id') == row.get('id') for item in self.snapshot.get(kind) or [])), 'facts')
        self.assets = (self.snapshot.get('assets') or []) if self.record_kind == 'assets' else []
        self.source_links = []

    def compose_sections(self):
        with Horizontal(id='pf-inspector-workspace'):
            with Vertical(id='pf-inspector-inventory'):
                yield Static(Text('TOKEN INVENTORY', style='bold'), id='pf-inspector-inventory-title')
                yield DataTable(id='pf-inspector-table', cursor_type='row', zebra_stripes=True)
            with VerticalScroll(id='pf-inspector-details'):
                yield Static(Text(), id='pf-inspector-facts')

    def on_mount(self):
        super().on_mount()
        table = self.query_one('#pf-inspector-table', DataTable)
        for label, width in (('TOKEN',12),('CHAIN',5),('TOTAL',8)):
            table.add_column(label, width=width)
        for asset in self.assets:
            table.add_row(token_cell(asset,12), Text(chain_name(asset.get('chain_id'))), Text(_usd(asset.get('total_usd'))))
        index = next((i for i, asset in enumerate(self.assets) if asset.get('id') == self.row.get('id')), 0)
        table.move_cursor(row=index, animate=False)
        self._paint_details()
        self.call_after_refresh(table.focus)
        self.call_after_refresh(self._fit_workspace)

    def on_resize(self):
        super().on_resize()
        self.call_after_refresh(self._fit_workspace)

    def _fit_workspace(self):
        room = self.query_one('.record-detail-scroll').scrollable_content_region.width
        self.query_one('#pf-inspector-workspace').set_class(room < SIDE_BY_SIDE_CONTENT_COLUMNS, 'stacked')

    def _title(self):
        title = Text('PORTFOLIO · ', style='bold')
        title.append_text(token_cell(self.row,28))
        title.append(' · '+chain_name(self.row.get('chain_id')))
        self.query_one('.record-detail-title', Static).update(title)

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id == 'pf-inspector-table' and 0 <= event.cursor_row < len(self.assets):
            self.row = deepcopy(self.assets[event.cursor_row])
            self._paint_details()
            self._title()

    def _paint_details(self):
        row, snapshot = self.row, self.snapshot
        explorer = EXPLORER(row.get('chain_id'))
        self.source_links = []
        text = Text()
        def heading(label):
            text.append(('\n' if text else '')+label+'\n\n', style='bold')
        def line(label, value):
            text.append(label+'  ', style='dim')
            text.append_text(value if isinstance(value, Text) else address_prose(flatten(value) or '—', explorer=explorer))
            text.append('\n')
        def link(label, url):
            return source_text(label, url, self.source_links, explorer=explorer, action='screen.open_source')
        if self.record_kind != 'assets':
            kind = self.record_kind
            heading({'nfts':'NFT INVENTORY','positions':'STAKE / DEPOSIT','rewards':'UNCLAIMED REWARD',
                     'utilities':'TOKEN UTILITY'}.get(kind,'RECORDED FACTS'))
            line('Collection' if kind == 'nfts' else 'Contract', token_cell(row,35,contract=kind != 'rewards'))
            line('Chain', chain_name(row.get('chain_id')))
            if kind == 'nfts':
                line('Owned', _quantity(row.get('count')))
                line('Token IDs', ', '.join(str(value) for value in row.get('token_ids') or []))
            elif kind == 'utilities':
                line('Role', row.get('role'))
                line('Joined', 'yes' if row.get('joined') is True else 'no' if row.get('joined') is False else '—')
                line('Contract TVL', _quantity(row.get('tvl_quantity'))+'  '+_usd(row.get('tvl_usd')))
            else:
                line('Principal' if kind == 'positions' else 'Amount', _quantity(row.get('quantity')))
                line('Value', _usd(row.get('value_usd')))
                if kind == 'positions':
                    line('Pending', _usd(row.get('pending_usd')))
                elif kind == 'rewards':
                    line('Readiness', row.get('status'))
                    line('Unlock', row.get('unlock_at'))
            if row.get('apr') is not None:
                line('APR', _quantity(row['apr'])+'% · '+flatten(row.get('apr_method')))
            if row.get('site_url'):
                line('Site', link(row.get('name') or 'Source', row['site_url']))
            line('Scan', hhmm(snapshot.get('as_of')) if snapshot.get('as_of') else '—')
            self.query_one('#pf-inspector-facts', Static).update(text)
            return
        heading('WHERE IT SITS')
        for label, key in (('Wallet','wallet'),('Staked','staked'),('Ready','ready'),
                           ('Locked','locked'),('Pending','pending'),('Unknown','unknown_reward')):
            value = _quantity(row.get(key+'_quantity'))+'  '+_usd(row.get(key+'_usd'))
            if key == 'ready' and row.get('unknown_reward_quantity') and not row.get('ready_quantity'):
                value = '— · readiness unknown'
            line(label, value)
        heading('ONE COMBINED VALUATION')
        line('', 'Source estimate; first-leg sale coverage only. Net proceeds not guaranteed.')
        line('Total', _usd(row.get('total_usd')))
        line('First-leg sale', sale_text(row))
        line('Sale state', row.get('sell_state'))
        line('Token', address_text(row.get('token_address') or row.get('contract_address'), explorer=explorer))
        if row.get('name'):
            line('Name', row['name'])
        pool = row.get('pool') or {}
        for key, value in pool.items():
            if key.endswith('url'):
                line(key.replace('_',' ').title(), link('Open pool', value))
            elif value is not None:
                line(key.replace('_',' ').title(), value)
        heading('CONNECTIONS')
        found = False
        for kind in ('positions','rewards','utilities'):
            related = [item for item in snapshot.get(kind) or [] if item.get('asset_id') == row.get('id')]
            for item in related:
                found = True
                line(kind.title(), token_cell(item,28,contract=kind != 'rewards'))
                details = [item.get('status'), item.get('kind'), item.get('role')]
                line('', ' · '.join(flatten(value) for value in details if value) or item.get('name'))
                if item.get('unlock_at') is not None:
                    line('Unlock', item['unlock_at'])
                if item.get('apr') is not None:
                    line('APR', _quantity(item['apr'])+'% · '+flatten(item.get('apr_method')))
                if item.get('site_url'):
                    line('Site', link(item.get('name') or 'Source', item['site_url']))
        for item in row.get('connections') or []:
            found = True
            if isinstance(item,dict):
                url = source_url(item.get('url'))
                target = urlsplit(url).path.rsplit('/',1)[-1] if url else None
                label = item.get('name') or item.get('kind')
                line('Related', address_text(target, label=flatten(label), explorer=explorer)
                     if is_address(target) else link(label, url))
                line('', item.get('how'))
            else:
                line('Related', item)
        if not found:
            line('', 'No recorded relationships')
        if row.get('token_ids') is not None:
            line('Owned IDs', ', '.join(str(value) for value in row['token_ids']))
        if row.get('site_url'):
            line('Site', link(row.get('name') or 'Source', row['site_url']))
        heading('READ PROVENANCE')
        line('Scan', hhmm(snapshot.get('as_of')) if snapshot.get('as_of') else '—')
        for chain in snapshot.get('chains') or []:
            if chain.get('chain_id') == row.get('chain_id'):
                line('Block', chain.get('block'))
        coverage = snapshot.get('coverage') or {}
        line('Claims', 'complete' if coverage.get('claims_complete') is True else
             'partial' if coverage.get('claims_complete') is False else 'unknown')
        line('Source', link('imd.vibingco.de/portfolio', 'https://imd.vibingco.de/portfolio'))
        for key, value in (row.get('source') or {}).items():
            line(key.replace('_',' ').title(), link('Source', value) if key.endswith('url') else value)
        self.query_one('#pf-inspector-facts', Static).update(text)

    def action_open_source(self, index):
        if type(index) is int and 0 <= index < len(self.source_links):
            if url := source_url(self.source_links[index]):
                self.app.open_url(url)
