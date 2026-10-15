"""Cached token details with independent source clocks and real explorer links."""
from rich.text import Text
from textual.widgets import Static

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.swarm_tokens import _usd, _paired
from maxpane_dashboard.widgets.address import address_text, is_address
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import hhmm

EXPLORER = for_chain_id


class SwarmTokenDetail(RecordDetailScreen):
    ID_PREFIX='swarm-token-detail'

    def __init__(self, row, *, is_mock=True, as_of=None):
        super().__init__(row)
        self.is_mock, self.as_of = is_mock, as_of

    def _title(self):
        self.query_one('.record-detail-title',Static).update(Text(flatten(
            f"{self.row.get('symbol')} · {self.row.get('chain','').upper()} · #{self.row.get('launch_id')}"
            + (' · MOCK DATA' if self.is_mock else '')),style='bold'))

    def compose_sections(self):
        row=self.row
        yield from self.section('MARKET',Text(flatten(row.get('name',''))),first=True)
        for label,key in [('Price','price_usd'),('Market cap','mcap_usd'),
                          ('FDV','fdv_usd'),('24h volume','volume_24h')]:
            value=_usd(row.get(key),price=key=='price_usd')
            yield Static(Text(f'{label:18} {value}'))
        change=row.get('change_24h')
        yield Static(Text('24h change         '+('--' if change is None else f'{change:+.1f}%')))
        yield from self.section('LAUNCH POSITION',Text(flatten(row.get('lp_state','unknown'))))
        yield Static(Text(flatten(f"Paired balance     {_paired(row)}")))
        yield Static(Text(flatten(f"Launch status      {row.get('status','--')}")))
        yield Static(Text(flatten(f"Launch verdict     {row.get('verdict','--')}")))
        if self.is_mock:
            yield from self.section('DEMO',Text('All values are mock data. Contract and pool links are not connected.'))
            return
        explorer=EXPLORER(row.get('chain_id'))
        yield Static(Text('Contract           ')+address_text(row.get('token_address'),explorer=explorer))
        if is_address(row.get('paired_symbol')):
            yield Static(Text('Paired token       ')+address_text(row['paired_symbol'],explorer=explorer))
        if row.get('withdrawn_pct') is not None:
            yield Static(Text(f"Position withdrawn {row['withdrawn_pct']:.1f}%"))
        yield from self.section('SOURCES',Text(flatten(f"Market             {row.get('market_source') or '—'}")))
        pool=row.get('market_pool')
        if pool:
            yield Static(Text('Market pool        ')+(address_text(pool,explorer=explorer)
                         if is_address(pool) else Text(flatten(pool))))
        for label,key in [('Quotes','market'),('Launch liquidity','liquidity'),('Price history','history'),('Recent trades','trades')]:
            yield Static(Text(flatten(f"{label:18} as of {hhmm(row.get(key+'_read_at'))}")))
        yield Static(Text('Quotes, 24h volume and trades describe the selected indexed pool.'))
        yield Static(Text('Liquidity describes the original launch position; missing data is --.'))
        yield Static(Text('Age is the launch record time. Trade history is a recent window.'))
