"""Worker metadata mixes, plus the independently served contributors token metric."""
from datetime import datetime
from rich.text import Text
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten, strip_tags
from maxpane_dashboard.widgets.panels import SignalsPanelBase
from maxpane_dashboard.widgets.surf._fmt import source_clock
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token

_NAMES=('runtime','daemon','os','profile','slots','heartbeat','tokens-label','tokens','contributors','paused')
_MIXES={'runtime':'runtimes','daemon':'daemons','os':'os','profile':'profiles','slots':'concurrency'}
class SurfSwarmFleet(SignalsPanelBase):
    TITLE='FLEET'
    ROWS=tuple((f'surf-fleet-{name}',None) for name in _NAMES)
    DEFAULT_CSS='''
    SurfSwarmFleet > .panel-line { text-wrap: nowrap; text-overflow: ellipsis; }
    '''
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._data=None
    def on_resize(self):
        if self._data is not None:self.update_data(**self._data)
    def update_data(self,swarm_fleet=None,swarm_board_summary=None,
                    swarm_board_as_of_hhmm=None,swarm_workers_as_of_hhmm=None,**_kwargs):
        self._data=dict(swarm_fleet=swarm_fleet,swarm_board_summary=swarm_board_summary,
                        swarm_board_as_of_hhmm=swarm_board_as_of_hhmm,swarm_workers_as_of_hhmm=swarm_workers_as_of_hhmm)
        self.write('.panel-title',Text('FLEET · workers as of '+source_clock(swarm_workers_as_of_hhmm)))
        for name in _NAMES:
            self.write_guarded(f'#surf-fleet-{name}',lambda name=name:self._line(name,swarm_fleet,swarm_board_summary,swarm_board_as_of_hhmm),Text(f'{name} unavailable'))
    def _fit(self,label,parts,empty):
        room=max(self.size.width-2,0)
        if not parts:return Text(label+empty)
        for keep in range(len(parts),-1,-1):
            values=parts[:keep]+([f'+{len(parts)-keep}'] if keep<len(parts) else [])
            text=label+' · '.join(values)
            if rowfit.cell_len(text)<=room:return Text(text)
        return Text(rowfit.clip(label+f'+{len(parts)}',room))
    def _line(self,name,fleet,summary,clock):
        if name=='tokens-label':return Text('tokens / completed job')
        if name=='tokens':
            value=summary.get('tokens_per_completed_job') if isinstance(summary,dict) else None
            return Text('unavailable' if value is None else f'{fmt_int(value)} (served)')
        if name=='contributors':return Text('contributors as of '+source_clock(clock))
        label='PAUSED ' if name=='paused' else name+' '
        if not isinstance(fleet,dict):return Text(label+'unavailable')
        if name in _MIXES:
            rows=fleet.get(_MIXES[name])
            if not isinstance(rows,list):return Text(label+'unavailable')
            parts=[strip_tags(flatten(row.get('value')))+' '+fmt_int(row.get('count')) for row in rows if isinstance(row,dict)]
            return self._fit(label,parts,'none reported')
        if name=='heartbeat':
            endpoints=[fleet.get('heartbeat_oldest_ts'),fleet.get('heartbeat_newest_ts')]
            if any(value is None for value in endpoints):return Text(label+'unavailable')
            return Text(label+' – '.join(datetime.fromtimestamp(value).strftime('%H:%M:%S') for value in endpoints))
        paused=fleet.get('paused')
        if not isinstance(paused,list):return Text(label+'unavailable')
        parts=[f"#{row['token_id']} until {hhmm(row['until_ts'])} ×{fmt_int(row['failures'])}" for row in paused if isinstance(row,dict) and seat_token(row.get('token_id')) is not None]
        return self._fit(label,parts,'none')
