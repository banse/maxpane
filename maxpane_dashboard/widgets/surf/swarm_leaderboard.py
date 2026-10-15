"""Recorded-seat outcomes with independent effort and worker facts."""
from rich.style import Style
from rich.text import Text
from textual.widgets import DataTable, Static
from textual.widgets.data_table import RowDoesNotExist
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int, fmt_float, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.surf._fmt import source_clock, short_model
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token, outcomes_clock
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
# The reader permits six-digit job totals; the split keeps both exact counts
# by removing separator spaces only when necessary.
_LAUNCH_SPECS=(('rank','#',4),('seat','seat',7),('jobs','jobs',6),
               ('launches','launches',8),('build_review','build/review',13),
               ('model','model',14),('effort','effort',6),
               ('runtime','runtime',11),('state','state',16))
_LAUNCH_KEYS=tuple(key for key,_,_ in _LAUNCH_SPECS)
_LAUNCH_TIERS={'full':_LAUNCH_KEYS, 'compact':tuple(key for key in _LAUNCH_KEYS if key!='runtime'),
               'tight':('rank','seat','jobs','launches')}
_LAUNCH_LADDER=rowfit.Ladder(*((name,table_cols(w for key,_,w in _LAUNCH_SPECS if key in keep))
                              for name,keep in _LAUNCH_TIERS.items()))
_BUILD_REVIEW_NOTE=('Build/review: distinct contributing jobs; build includes implementation, '
                    'integration and tests. A job can count as both build and review, so counts can overlap.')


def _model_pairs(item):
    """Keep model and effort paired; the manager supplies current worker settings."""
    pairs=item.get('advertised_models')
    if not isinstance(pairs,list):
        return []
    clean={(strip_tags(flatten(pair['model'])),strip_tags(flatten(pair.get('effort'))) or None)
           for pair in pairs if isinstance(pair,dict) and isinstance(pair.get('model'),str)
           and strip_tags(flatten(pair['model']))}
    return sorted(clean,key=lambda pair:(pair[0],pair[1] or ''))


def _build_review(item):
    counts=tuple(seat_token(item.get(key)) for key in ('build_jobs','review_jobs'))
    return counts if all(value is not None for value in counts) else None

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

    def on_mouse_move(self,event):
        self.parent._show_row_tooltip(event.style.meta.get('row'))


class SurfSwarmLeaderboard(SwarmTableBase):
    TITLE='LEADERBOARD · recorded seats · launch contributors'
    TABLE_ID='surf-swarm-leaderboard-table'
    ROW_CAP=None
    EMPTY_LINE='no submitted records yet'
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
        self._view_mode='recorded'
        self._view_states={}
        self._restore_view=None
        self._recorded_rows=None
        self._recorded_clocks=''
        self._contribution={}
        self._row_tooltips={}
    def compose_body(self):
        for child in super().compose_body():
            yield _SeatTable(id=child.id, cursor_foreground_priority='renderable') if isinstance(child, DataTable) else child
        yield Static('',classes='board-clocks')
    def update_data(self,swarm_board_rows=None,swarm_seat_selected=None,
                    swarm_board_as_of_hhmm=None,swarm_workers_as_of_hhmm=None,
                    swarm_outcomes_source=None,swarm_contributors_as_of_hhmm=None,
                    swarm_launch_contribution=None,**_kwargs):
        selected=swarm_seat_selected if isinstance(swarm_seat_selected,dict) else {}
        self._selected=seat_token(selected.get('token_id'))
        self._recorded_rows=swarm_board_rows
        self._recorded_clocks=f'records {outcomes_clock(swarm_outcomes_source)} · effort {source_clock(swarm_contributors_as_of_hhmm)} · workers {source_clock(swarm_workers_as_of_hhmm)}'
        self._contribution=swarm_launch_contribution if isinstance(swarm_launch_contribution,dict) else {}
        self._present_view()

    def set_launch_contribution(self,snapshot):
        """Update background-read progress without replacing the recorded snapshot."""
        self._contribution=snapshot if isinstance(snapshot,dict) else {}
        if self._view_mode=='launches':
            self._present_view()

    def set_view(self,mode):
        if mode not in ('recorded','launches') or mode==self._view_mode:
            return
        self._view_states[self._view_mode]=(self._sort_key,self._sort_reverse,self._cursor_state())
        self._view_mode=mode
        self._sort_key,self._sort_reverse,self._restore_view=self._view_states.get(mode,('rank',False,(None,0)))
        recorded=mode=='recorded'
        self.COLUMN_SPECS=_SPECS if recorded else _LAUNCH_SPECS
        self.TIER_COLUMNS=type(self).TIER_COLUMNS if recorded else _LAUNCH_TIERS
        self.LADDER=type(self).LADDER if recorded else _LAUNCH_LADDER
        self._present_view()

    def _present_view(self):
        if self._view_mode=='recorded':
            self.EMPTY_LINE='no submitted records yet'
            self.UNAVAILABLE_LINE=''
            self.store(self._recorded_rows,None)
            if self.write('.board-clocks',Text(self._recorded_clocks)):
                self.query_one('.board-clocks',Static).tooltip=None
            return
        source=self._contribution
        rows=source.get('rows')
        if isinstance(rows,list):
            workers={seat_token(row.get('token_id')):row for row in (self._recorded_rows or []) if isinstance(row,dict)}
            rows=[dict(workers.get(seat_token(row.get('token_id')),{}),**row)
                  for row in rows if isinstance(row,dict)]
        state=source.get('state','pending')
        self.EMPTY_LINE='no launch contributions' if state=='ok' else 'no confirmed contributions in this read'
        self.UNAVAILABLE_LINE=''
        self.store(rows,None)

    def _cursor_state(self):
        try:
            table=self.query_one(DataTable)
        except Exception:
            return None,0
        token=(self.token_for_row(table.ordered_rows[table.cursor_row].key)
               if table.row_count else None)
        return token,table.scroll_y

    def _repaint(self):
        # Column installation and row rendering both clear the table. Capture
        # immutable identity first; saved selection and cursor are independent.
        try:
            table = self.query_one(DataTable)
        except Exception:
            table = None
        token,scroll_y=self._restore_view if self._restore_view is not None else self._cursor_state()
        self._restore_view=None
        self._clipped_fields=set()
        self._row_tooltips={}
        super()._repaint()
        if token is not None and table is not None:
            for index, row in enumerate(table.ordered_rows):
                if self.token_for_row(row.key) == token:
                    table.move_cursor(row=index,scroll=False)
                    break
        if table is not None:
            table.scroll_to(y=scroll_y,animate=False,force=True)
            self.call_after_refresh(self._refresh_row_tooltip)
        if self._view_mode=='launches':
            self._render_launch_source()

    def _render_launch_source(self):
        source=self._contribution
        state=source.get('state','pending')
        detail=strip_tags(flatten(source.get('detail') or '')) if state in ('ok','partial') else ''
        if not detail and seat_token(source.get('loaded')) is not None:
            total=seat_token(source.get('total'))
            detail=f"{source['loaded']}/{total} production launches" if total is not None else f"{source['loaded']} launches read"
        parts=[]
        if state=='partial':
            parts.append('partial')
        if source.get('read_ts') is not None:
            parts.append(f"as of {hhmm(source['read_ts'])}")
        if detail:
            parts.append(detail)
        self.write('.board-clocks',Text(' · '.join(parts),style='dim'))
        if not isinstance(source.get('rows'),list) and state!='pending':
            self._write_footer(())
        try:
            self.query_one('.board-clocks',Static).tooltip=Text(detail) if detail else None
        except Exception:
            pass

    def sort_by(self, key):
        if key not in tuple(spec[0] for spec in self.COLUMN_SPECS):
            return
        self._sort_reverse = not self._sort_reverse if key == self._sort_key else False
        self._sort_key = key
        self._repaint()

    def cycle_sort(self):
        keys=tuple(spec[0] for spec in self.COLUMN_SPECS)
        self.sort_by(keys[(keys.index(self._sort_key) + 1) % len(keys)])

    def reverse_sort(self):
        self._sort_reverse = not self._sort_reverse
        self._repaint()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        if event.data_table.id == self.TABLE_ID:
            event.stop()
            self.sort_by(event.column_key.value)

    def on_data_table_row_highlighted(self,event: DataTable.RowHighlighted):
        if event.data_table.id==self.TABLE_ID:
            self.call_after_refresh(self._refresh_row_tooltip)

    def _refresh_row_tooltip(self):
        table=self.query_one(DataTable)
        row=table.cursor_row
        if table._show_hover_cursor and table.is_mouse_over:
            row=self.screen.get_style_at(*self.app.mouse_position).meta.get('row')
        self._show_row_tooltip(row)

    def _show_row_tooltip(self,row):
        table=self.query_one(DataTable)
        tooltip=None
        if self._view_mode=='launches':
            tooltip=Text(_BUILD_REVIEW_NOTE)
            if isinstance(row,int) and 0<=row<table.row_count:
                tooltip=self._row_tooltips.get(self.token_for_row(table.ordered_rows[row].key),tooltip)
        table.tooltip=tooltip

    def column_plan(self, tier, budget):
        marker = '▼' if self._sort_reverse else '▲'
        return tuple((key, label[:width-1] + marker if key == self._sort_key else label, width)
                     for key, label, width in super().column_plan(tier, budget))

    def _sort_value(self, item):
        if not isinstance(item, dict):
            return None
        if self._sort_key in ('model','effort'):
            pairs=_model_pairs(item)
            value=(short_model(pairs[0][0]) if self._sort_key=='model' else pairs[0][1]) if pairs else None
            return value.casefold() if value else None
        if self._sort_key=='build_review':
            return _build_review(item)
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
        full_labels=('recorded seats','launch contributors')
        for prefix,labels in (('LEADERBOARD · ',full_labels),('',full_labels),
                              ('',('recorded','launches')),('',('rec','launches'))):
            if not room or rowfit.cell_len(prefix+' · '.join(labels))<=room:
                break
        title=Text(prefix)
        accent=self.app.get_css_variables().get('accent','cyan')
        for index,(mode,label) in enumerate(zip(('recorded','launches'),labels)):
            if index:title.append(' · ')
            active=mode==self._view_mode
            title.append(label,style=Style(color=accent if active else None,bold=active,dim=not active,
                                          meta={'@click':f"screen.board_view('{mode}')"}))
        # Owner: BOARD keeps fitted tabs and cell ellipses, without a widen hint.
        self.query_one('.panel-title',Static).auto_links=False
        self.write('.panel-title',title)

    def build_cells(self,item):
        token=seat_token(item.get('token_id'))
        if token is None: return None
        state=item.get('live_state')
        unknown='—'
        state_text={'idle':'○ idle','offline':'offline'}.get(state,unknown)
        if state=='working': state_text=f"● working {fmt_int(item.get('working'))}"
        elif state=='paused': state_text=f"⏸ {hhmm(item.get('paused_until_ts'))} ×{fmt_int(item.get('failures'))}"
        rate=item.get('accept_rate')
        hours=item.get('wall_clock_s')
        raw={key:str(item[key]) if seat_token(item.get(key)) is not None else '—' for key in ('rank','devices','attempts','accepted','rejected','pending','turns','jobs','launches')}
        raw.update(seat=('▸' if token==self._selected else '')+f'#{token}',
                   runtime=item.get('runtime') if item.get('runtime') is not None else unknown,
                   rate='—' if rate is None else fmt_float(rate*100,'.1f')+'%',
                   hours='—' if hours is None else fmt_float(hours/3600,'.1f'),state=state_text)
        if self._view_mode=='launches':
            pairs=_model_pairs(item)
            counts=_build_review(item)
            raw.update(model=((short_model(pairs[0][0]) or '—')+(f' +{len(pairs)-1}' if len(pairs)>1 else '')) if pairs else '—',
                       effort=(pairs[0][1] or '—') if pairs else '—',
                       build_review=f'{counts[0]} / {counts[1]}' if counts is not None else '— / —')
            details=('Current advertised settings:\n'+'\n'.join(f'{model} · {effort or "—"}' for model,effort in pairs)
                     if pairs else 'No current advertised settings' if item.get('advertised_models')==[]
                     else 'Current advertised settings —')
            self._row_tooltips[token]=Text(details+'\n'+_BUILD_REVIEW_NOTE)
        cells={}
        for key,_,width in self.COLUMN_SPECS:
            if key=='build_review' and rowfit.cell_len(raw[key])>width:
                raw[key]=raw[key].replace(' ','')
            display=raw[key]
            if key=='model' and len(pairs)>1:
                suffix=f' +{len(pairs)-1}'
                display=rowfit.clip(short_model(pairs[0][0]) or '—',width-rowfit.cell_len(suffix))+suffix
            cell=Text.from_markup(sanitize_cell(display,width))
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
