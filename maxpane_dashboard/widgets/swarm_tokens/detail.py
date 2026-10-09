"""Cached mock token details; no links to invented onchain identifiers."""
from rich.text import Text
from textual.widgets import Static

from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.swarm_tokens import _usd, _paired


class SwarmTokenDetail(RecordDetailScreen):
    ID_PREFIX='swarm-token-detail'

    def _title(self):
        self.query_one('.record-detail-title',Static).update(Text(flatten(
            f"{self.row.get('symbol')} · {self.row.get('chain','').upper()} · #{self.row.get('launch_id')} · MOCK DATA"),style='bold'))

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
        yield from self.section('DEMO',Text('All values are mock data. Contract and pool links are not connected.'))
