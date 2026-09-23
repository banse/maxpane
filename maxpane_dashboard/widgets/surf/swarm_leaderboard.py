"""Lifetime contributor seats, enriched by workers; token metadata survives clipping."""
from rich.style import Style
from rich.text import Text
from textual.widgets import DataTable, Static
from textual.widgets.data_table import RowDoesNotExist
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int, fmt_float, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.surf._fmt import source_clock
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase, table_cols

# Counts keep every decimal digit without grouping separators. This reserves
# five cells for five-digit counters while keeping all twelve columns at the
# measured pin. Runtime is the only named free-text clipping exception.
_SPECS=(('rank','#',3),('seat','seat',7),('runtime','runtime',11),('devices','dev',3),
        ('attempts','att',5),('accepted','acc',5),('rejected','rej',5),('pending','pend',5),
        ('rate','rate',6),('turns','turns',5),('hours','hrs',6),('state','state',16))
_ALL=tuple(key for key,_,_ in _SPECS)
_COMPACT=tuple(key for key in _ALL if key not in ('turns','hours','devices'))
_TIGHT=('rank','seat','attempts','accepted','rate','state')

class _SeatTable(DataTable):
    """A BOARD row's first click uses the same selection message as Enter."""
    async def _on_click(self, event):
        event.prevent_default()  # Delegate once; Textual otherwise also calls its MRO handler.
        meta = event.style.meta
        row, column = meta.get("row"), meta.get("column")
        if (isinstance(row, int) and 0 <= row < self.row_count
                and isinstance(column, int) and 0 <= column < len(self.columns)):
            self.move_cursor(row=row, column=column, scroll=False)
        await super()._on_click(event)


class SurfSwarmLeaderboard(SwarmTableBase):
    TITLE='LEADERBOARD · lifetime'
    TABLE_ID='surf-swarm-leaderboard-table'
    ROW_CAP=None
    EMPTY_LINE='no contributors yet'
    COLUMN_SPECS=_SPECS
    TIER_COLUMNS={'full':_ALL,'compact':_COMPACT,'tight':_TIGHT}
    LADDER=rowfit.Ladder(*((name,table_cols(w for key,_,w in _SPECS if key in keep))
                          for name,keep in TIER_COLUMNS.items()))
    #: Owner, 2026-09-22: one blank cell left of the table, one fewer on its
    #: right -- a 1-cell margin paid for by a 1-cell vertical scrollbar, so
    #: ``GUTTER_COLS`` (2) is margin plus scrollbar and the ladder's budget,
    #: and with it the BOARD width pin, is unchanged.
    DEFAULT_CSS='''
    SurfSwarmLeaderboard > DataTable { margin: 0 0 0 1; scrollbar-size-vertical: 1; }
    SurfSwarmLeaderboard > .board-clocks { height: 1; padding: 0 1; text-wrap: nowrap; text-overflow: ellipsis; }
    '''
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._selected=None
        self._clipped_fields=set()
        self._sort_key='rank'
        self._sort_reverse=False
    def compose_body(self):
        for child in super().compose_body():
            yield _SeatTable(id=child.id, cursor_foreground_priority='renderable') if isinstance(child, DataTable) else child
        yield Static('',classes='board-clocks')
    def update_data(self,swarm_board_rows=None,swarm_seat_selected=None,
                    swarm_board_as_of_hhmm=None,swarm_workers_as_of_hhmm=None,**_kwargs):
        selected=swarm_seat_selected if isinstance(swarm_seat_selected,dict) else {}
        self._selected=seat_token(selected.get('token_id'))
        self.store(swarm_board_rows,None)
        self.write('.board-clocks',Text(f'contributors as of {source_clock(swarm_board_as_of_hhmm)} · workers as of {source_clock(swarm_workers_as_of_hhmm)}'))
    def _repaint(self):
        # Column installation and row rendering both clear the table. Capture
        # immutable identity first; saved selection and cursor are independent.
        try:
            table = self.query_one(DataTable)
        except Exception:
            table = None
        token = (self.token_for_row(table.ordered_rows[table.cursor_row].key)
                 if table is not None and table.row_count else None)
        self._clipped_fields=set()
        super()._repaint()
        if token is not None and table is not None:
            for index, row in enumerate(table.ordered_rows):
                if self.token_for_row(row.key) == token:
                    table.move_cursor(row=index)
                    break

    def sort_by(self, key):
        if key not in _ALL:
            return
        self._sort_reverse = not self._sort_reverse if key == self._sort_key else False
        self._sort_key = key
        self._repaint()

    def cycle_sort(self):
        self.sort_by(_ALL[(_ALL.index(self._sort_key) + 1) % len(_ALL)])

    def reverse_sort(self):
        self._sort_reverse = not self._sort_reverse
        self._repaint()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if event.data_table.id == self.TABLE_ID:
            event.stop()
            self.sort_by(event.column_key.value)

    def column_plan(self, tier, budget):
        marker = '▼' if self._sort_reverse else '▲'
        return tuple((key, label[:width-1] + marker if key == self._sort_key else label, width)
                     for key, label, width in super().column_plan(tier, budget))

    def _sort_value(self, item):
        if not isinstance(item, dict):
            return None
        field = {'seat':'token_id', 'rate':'accept_rate', 'hours':'wall_clock_s',
                 'state':'live_state'}.get(self._sort_key, self._sort_key)
        value = item.get(field)
        if self._sort_key in ('runtime', 'state'):
            return strip_tags(flatten(value)).casefold() if isinstance(value, str) else None
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def render_table(self, rows, *, footer=None):
        # Always restart from served order: ties must not inherit the previous
        # view sort. Append missing values separately so reverse keeps them last.
        known, missing = [], []
        for item in rows:
            (missing if self._sort_value(item) is None else known).append(item)
        ordered = sorted(known, key=self._sort_value, reverse=self._sort_reverse) + missing
        super().render_table(ordered, footer=footer)

    def _render_title(self, as_of):
        room = max(self.size.width - self.TITLE_PADDING_COLS, 0)
        widen = self._widen or self._clipped
        base = self.TITLE
        if widen and room and rowfit.cell_len(base) + 2 + rowfit.cell_len(rowfit.WIDEN_HINT) > room:
            base = "LEADERBOARD"
        self.write(".panel-title", Text(rowfit.title_with_hint(base, widen, room)))

    def build_cells(self,item):
        token=seat_token(item.get('token_id'))
        if token is None: return None
        state=item.get('live_state')
        state_text={'idle':'○ idle','offline':'offline'}.get(state,'unavailable')
        if state=='working': state_text=f"● working {fmt_int(item.get('working'))}"
        elif state=='paused': state_text=f"⏸ {hhmm(item.get('paused_until_ts'))} ×{fmt_int(item.get('failures'))}"
        rate=item.get('accept_rate')
        hours=item.get('wall_clock_s')
        raw={key:str(item[key]) if seat_token(item.get(key)) is not None else '—' for key in ('rank','devices','attempts','accepted','rejected','pending','turns')}
        raw.update(seat=('▸' if token==self._selected else '')+f'#{token}',
                   runtime=item.get('runtime') if item.get('runtime') is not None else 'unavailable',
                   rate='—' if rate is None else fmt_float(rate*100,'.1f')+'%',
                   hours='—' if hours is None else fmt_float(hours/3600,'.1f'),state=state_text)
        cells={}
        for key,_,width in _SPECS:
            cell=Text.from_markup(sanitize_cell(raw[key],width))
            if rowfit.cell_len(strip_tags(flatten(raw[key]))) > width:
                self._clipped=True
                self._clipped_fields.add(key)
            selected = token == self._selected
            color = {'working':'green', 'paused':'red', 'idle':None, 'offline':None}.get(state, 'yellow') if key == 'state' else None
            if selected and key == self._keys[0]:
                color = self.app.get_css_variables().get('accent', 'cyan')
            cell.style = Style(color=color, bold=True if selected else None,
                               dim=True if state == 'offline' else None,
                               meta={'seat_token':token} if key == 'seat' else None)
            cells[key]=cell
        return cells
    def token_for_row(self,row_key):
        """Read immutable identity from the actual DataTable row, never its visible text."""
        try:
            cell=self.query_one(DataTable).get_row(row_key)[self._keys.index('seat')]
            return seat_token(cell.style.meta.get('seat_token')) if isinstance(cell,Text) and isinstance(cell.style,Style) else None
        except (KeyError,AttributeError,ValueError,IndexError,RowDoesNotExist):
            return None
