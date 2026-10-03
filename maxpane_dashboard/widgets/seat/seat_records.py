"""Complete cached record cells and stable cursor, with bounded display windows."""
from rich.text import Text
from rich.style import Style
from textual.widgets import Static
from maxpane_dashboard.analytics.seat_records import record_state, record_window
from maxpane_dashboard.analytics.seat_signals import parse_iso
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import mmdd_hhmm, short_model
from maxpane_dashboard.widgets.seat.hero import _word
from maxpane_dashboard.widgets.seat._chain import job_link_style
from maxpane_dashboard.widgets.seat.seat_table import SeatTable
from maxpane_dashboard.widgets.seat.ledger import _took
from maxpane_dashboard.widgets.seat.seat_job_text import panel_row, plain
from maxpane_dashboard.widgets.seat_oracle_answer import panel_text, tok_text, _STATE_COLORS
from maxpane_dashboard.widgets.seat_words import NODE_TITLES
from maxpane_dashboard.widgets.seat_icons import mark_addresses, keep_units, link_in_order, unmark
from maxpane_dashboard.widgets.explorer import for_chain_id


class SeatRecords(SeatTable):
    TITLE = 'RECORDS'
    TABLE_ID = 'seat-records-table'
    ROW_CAP = 400
    EMPTY_LINE = 'no records'
    COLUMN_SPECS = (('when','when',11),('job','job',8),('node','node',6),('state','state',9),
                    ('model','model',9),('took','took',6),('tok','tok',6),('panel','panel',9),('answer','answer',20),('detail','',1))
    TIER_COLUMNS = {'full': tuple(k for k,_,_ in COLUMN_SPECS),
                    'compact': ('when','job','node','state','panel','answer','detail')}
    LADDER = rowfit.Ladder(('full',105),('compact',76))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.limit, self.open_only = 40, False
        self._records = self._clock = None

    def update_data(self, seat_records_rows=None, seat_records_window=None, seat_sources=None,
                    seat_as_of_hhmm=None, seat_offline=None, **_kwargs):
        self.TITLE = 'RECORDS · offline · cached' if seat_offline else 'RECORDS'
        self._records = seat_records_rows
        self._clock = (seat_as_of_hhmm or {}).get('seatWork')
        self.set_window(self.limit, self.open_only)

    def set_window(self, limit, open_only):
        self.limit, self.open_only = max(40, min(400, limit)), open_only
        rows = record_window(self._records, self.limit, open_only) if isinstance(self._records, list) else None
        self.store(rows, self._clock)

    def column_width(self, key, tier, budget, width):
        fixed = sum(w+2 for k,_,w in self.COLUMN_SPECS if k in self.TIER_COLUMNS[tier] and k != 'answer')
        return max(12, budget-fixed-2) if key == 'answer' else width

    def build_cells(self, item):
        panel = item.get('panel') or {}
        width = next(w for k,_,w in self._installed if k == 'answer')
        raw = plain(item.get('answerPreview'))
        colour = ''
        if not raw:
            answer_state = item.get('answerState') or 'not read'
            raw = {'not_read':'not read'}.get(answer_state, answer_state)
            colour = 'yellow' if answer_state in ('busy', 'unavailable') else 'dim'
        marked, addresses, spans = mark_addresses(raw, width=max(8,min(42,width-2)))
        cut = keep_units(marked, spans, rowfit.clip(marked,width))
        answer = Text(unmark(cut), style=colour)
        link_in_order([answer], addresses, explorer=for_chain_id(panel.get('chainId')))
        state = record_state(item)
        node = _word(item.get('nodeKey'))
        return {'when': mmdd_hhmm(parse_iso(item.get('submittedUtc') or item.get('acceptedUtc'))),
                'job': Text(_word(item.get('jobId'))[:8],style=job_link_style(item.get('jobId'))),
                'node': Text(rowfit.clip(NODE_TITLES.get(node,node).lower(),6)),
                'state': Text(rowfit.clip(_word(state) or '—',9),style=_STATE_COLORS.get(state,'dim')),
                'model': Text(rowfit.clip(short_model(item.get('model')) or '—',9)),
                'took':Text(_took(item.get('durationS'))),'tok':Text(tok_text((item.get('tokens') or {}).get('output'))),
                'panel': panel_text(panel_row(panel)), 'answer': answer,
                'detail': Text('»',style=Style(meta={'@click':f'screen.record_detail({item.get("key")!r})'}))}

    def _render_title(self, as_of):
        text = Text(self.TITLE + ' · ')
        text.append('all', style=Style(meta={'@click':'screen.record_filter("all")'}))
        text.append(' · ').append('not completed', style=Style(meta={'@click':'screen.record_filter("open")'}))
        if as_of:
            text.append(' · as of ' + str(as_of), style='dim')
        if self._widen or self._clipped:
            text.append(' ‹ widen', style='dim')
        self.write('.panel-title', text)

    def _repaint(self):
        super()._repaint()
        if not self.is_mounted:
            return
        total = len(record_window(self._records,400,self.open_only)) if isinstance(self._records,list) else 0
        text = Text('all',style=Style(meta={'@click':'screen.record_filter("all")'}))
        text.append(' · ').append('not completed',style=Style(meta={'@click':'screen.record_filter("open")'}))
        older = max(0,total-self.limit)
        if older:
            text.append(f' · +{older} older · ').append('more',style=Style(meta={'@click':'screen.record_more'}))
        if not self._seat_rows:
            text.append(' · ' + (self.EMPTY_LINE if self._records is not None else 'records unavailable'),style='dim')
        footer=self.query_one('#'+self.footer_id,Static); footer.display=True; footer.update(text)
