"""Node metrics keep unknown detail counts separate from known zero counts."""
from rich.text import Text
from rich.style import Style
from textual.widgets import Static
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import mmdd_hhmm
from maxpane_dashboard.analytics.seat_signals import parse_iso
from maxpane_dashboard.widgets.seat.hero import _word
from maxpane_dashboard.widgets.seat.ledger import _took
from maxpane_dashboard.widgets.seat_oracle_answer import tok_text
from maxpane_dashboard.widgets.seat.seat_table import SeatTable


class SeatNodes(SeatTable):
    TITLE='NODES'
    TABLE_ID='seat-nodes-table'
    ROW_ID='nodeKey'
    ROW_CAP=None
    EMPTY_LINE='no node attempts'
    COLUMN_SPECS=(('node','node',18),('role','role',9),('n','n',4),('accepted','acc',4),('rejected','rej',4),
                  ('failed','fail',4),('pending','pend',4),('acc_pct','acc %',6),('duration','took p50',8),
                  ('output','out p50',8),('paid','paid',4),('launch','launch',6),('last','last',11))
    TIER_COLUMNS={'full':tuple(k for k,_,_ in COLUMN_SPECS),
                  'compact':tuple(k for k,_,_ in COLUMN_SPECS if k not in ('output','last'))}
    LADDER=rowfit.Ladder(('full',116), ('compact',93))

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.week_only=False
        self._all=self._week=None
        self._coverage={}

    def update_data(self,seat_nodes_all_rows=None,seat_nodes_week_rows=None,seat_nodes_coverage=None,
                    seat_sources=None,seat_offline=None,**_kwargs):
        self._all,self._week=seat_nodes_all_rows,seat_nodes_week_rows
        self._coverage=seat_nodes_coverage or {}
        self.TITLE='NODES' + (' · offline · cached' if seat_offline else '')
        self.store(self._week if self.week_only else self._all,None)

    def set_window(self, week_only):
        self.week_only = week_only
        self.store(self._week if self.week_only else self._all, None)

    def toggle_window(self):
        self.set_window(not self.week_only)

    def _render_title(self, as_of):
        text = Text(self.TITLE + ' · ')
        text.append('all', style=Style(meta={'@click':'screen.node_window("all")'}))
        text.append(' · ').append('7 d', style=Style(meta={'@click':'screen.node_window("week")'}))
        stamp = (self._coverage or {}).get('asOfUtc')
        if stamp:
            text.append(' · as of ' + mmdd_hhmm(parse_iso(stamp)), style='dim')
        if self._widen or self._clipped:
            text.append(' ‹ widen', style='dim')
        self.write('.panel-title', text)

    def build_cells(self,item):
        count=lambda key:Text(str(item[key]),style='yellow' if key=='pending' else '') if item.get(key) is not None else Text('·',style='dim')
        out={k:count(field) for k,field in [('n','attempts'),('accepted','accepted'),('rejected','rejected'),('failed','failed'),('pending','pending'),('paid','paid'),('launch','launch')]}
        out.update(node=Text(rowfit.clip(_word(item.get('nodeKey')),18)),role=Text(rowfit.clip(_word(item.get('role')),9)),
                   acc_pct=Text(f'{item["acceptedPercent"]:.1f}' if item.get('acceptedPercent') is not None else '·'),
                   duration=Text(_took(item.get('durationP50S'))),output=Text(tok_text(item.get('outputTokensP50'))),
                   last=Text(mmdd_hhmm(parse_iso(item.get('lastSubmittedUtc')))))
        return out

    def _repaint(self):
        super()._repaint()
        if not self.is_mounted:
            return
        coverage=self._coverage
        value=lambda key:str(coverage[key]) if coverage.get(key) is not None else '—'
        text=Text('all · 7 d [w]',style=Style(meta={'@click':'screen.node_window'}))
        text.append(f' · covers {value("covered")} of {value("attempts")} attempts · job details read {value("detailsRead")} of {value("covered")}\n',style='dim')
        text.append('acc % = accepted ÷ attempts · took/out p50 = known attempts\npaid = api paidBy present · launch = kind/requested/workflow · · = details not read',style='dim')
        footer=self.query_one('#'+self.footer_id,Static);footer.styles.height=3;footer.display=True;footer.update(text)
