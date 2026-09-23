"""Labelled worker metadata groups and the independent contributor token metric."""
from datetime import datetime
from rich.text import Text
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten, strip_tags
from maxpane_dashboard.widgets.panels import SignalsPanelBase
from maxpane_dashboard.widgets.sparkline_common import fmt_compact
from maxpane_dashboard.widgets.surf._fmt import source_clock, short_model
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token

# Eleven cells align the longest label, tokens/job, plus one separating cell.
# At BOARD's 37 outer cells the content is 33, leaving 22 for whole mix items.
# The model's second line carries its exact omitted count and advertised note.
# CONTRIBUTORS has a blank row under its sub-header and five /contributors
# lines (owner, 2026-09-22: "show more data about the contributors"); a pair
# that outgrows its line keeps its first value and counts the rest as +N.
LABEL_WIDTH = 11
_NAMES = ('runtime', 'model', 'model-note', 'daemon', 'os', 'profile', 'slots',
          'heartbeat', None, 'paused', 'paused-detail', None, 'contributors', None,
          'devices', 'accepted', 'rejected', 'turns', 'tokens-io', 'tokens')
_MS_PER_HOUR = 3_600_000
_MS_PER_MINUTE = 60_000
_MIXES = {'runtime': 'runtimes', 'daemon': 'daemons', 'os': 'os',
          'profile': 'profiles', 'slots': 'concurrency'}


class SurfSwarmFleet(SignalsPanelBase):
    TITLE = 'FLEET'
    ROWS = tuple((f'surf-fleet-{name}', None) if name else None for name in _NAMES)
    DEFAULT_CSS = '''
    SurfSwarmFleet > .panel-line { text-wrap: nowrap; text-overflow: ellipsis; }
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = None

    def on_resize(self):
        if self._data is not None:
            self.update_data(**self._data)

    def update_data(self, swarm_fleet=None, swarm_board_summary=None,
                    swarm_board_as_of_hhmm=None, swarm_workers_as_of_hhmm=None, **_kwargs):
        self._data = dict(swarm_fleet=swarm_fleet, swarm_board_summary=swarm_board_summary,
                         swarm_board_as_of_hhmm=swarm_board_as_of_hhmm,
                         swarm_workers_as_of_hhmm=swarm_workers_as_of_hhmm)
        self.write('.panel-title', Text('FLEET · workers as of ' + source_clock(swarm_workers_as_of_hhmm)))
        for name in filter(None, _NAMES):
            self.write_guarded(f'#surf-fleet-{name}',
                               lambda name=name: self._line(name, swarm_fleet, swarm_board_summary, swarm_board_as_of_hhmm),
                               self._label(name) + Text('unavailable', style='yellow'))
        self.query_one('#surf-fleet-paused-detail').display = bool(self._paused(swarm_fleet))

    def _room(self):
        return max(self.size.width - 2, 0)

    @staticmethod
    def _label(label):
        return Text().append(label.ljust(LABEL_WIDTH), style='dim')

    @staticmethod
    def _item(name, count):
        return Text().append(strip_tags(flatten(name)), style='dim').append(' ').append(fmt_int(count), style='bold')

    def _fit(self, label, parts, empty='none reported'):
        prefix = self._label(label) if label else Text()
        if not parts:
            return prefix + Text(empty, style='dim')
        for keep in range(len(parts), -1, -1):
            values = parts[:keep] + ([Text(f'+{len(parts)-keep}', style='bold')] if keep < len(parts) else [])
            text = prefix + Text(' · ').join(values)
            if text.cell_len <= self._room():
                return text
        return Text(rowfit.clip(prefix.plain + f'+{len(parts)}', self._room()))

    @staticmethod
    def _paused(fleet):
        rows = fleet.get('paused') if isinstance(fleet, dict) else None
        return [row for row in rows if isinstance(row, dict) and seat_token(row.get('token_id')) is not None] if isinstance(rows, list) else []

    def _model_lines(self, fleet):
        rows = fleet.get('models') if isinstance(fleet, dict) else None
        prefix = self._label('model')
        note = self._label('')
        if not isinstance(rows, list):
            return prefix + Text('unavailable', style='yellow'), note + Text('(advertised)', style='dim')
        parts = []
        for row in rows:
            if isinstance(row, dict):
                model = row.get('model')
                cleaned = short_model(model)
                name = 'none' if model is None else cleaned or '—'
                if cleaned and row.get('effort') is not None:
                    name += ' ' + strip_tags(flatten(row['effort']))
                parts.append(self._item(name, row.get('count')))
        keep = len(parts)
        while keep and (prefix + Text(' · ').join(parts[:keep])).cell_len > self._room():
            keep -= 1
        value = Text(' · ').join(parts[:keep]) if keep else Text(f'+{len(parts)}', style='bold')
        if not parts:
            value = Text('none reported', style='dim')
        if 0 < keep < len(parts):
            note += Text(f'+{len(parts)-keep} ', style='bold')
        note += Text('(advertised)', style='dim')
        return prefix + value, note

    @staticmethod
    def _count(value, word='', compact=False):
        out = Text(fmt_compact(value) if compact else fmt_int(value), style='bold')
        return out.append(' ' + word, style='dim') if word else out

    @classmethod
    def _wall_clock(cls, ms):
        """Wall-clock time to the nearest hour; under half an hour, whole minutes
        (a floor read 59 minutes as ``0 h`` and 5.9 h as ``5 h``, F64)."""
        if ms < _MS_PER_HOUR // 2:
            return cls._count((ms + _MS_PER_MINUTE // 2) // _MS_PER_MINUTE, 'min')
        return cls._count((ms + _MS_PER_HOUR // 2) // _MS_PER_HOUR, 'h')

    def _contributors(self, name, summary):
        """One /contributors line; its first value unread is the whole line unread."""
        summary = summary if isinstance(summary, dict) else {}
        get = lambda key: seat_token(summary.get(key))
        first, parts = {
            'devices': (get('devices'), [self._count(get('devices')),
                                         get('seats') is not None and self._count(get('seats'), 'seats')]),
            'accepted': (get('accepted'), [self._count(get('accepted')) + (
                Text(' of ', style='dim') + self._count(get('attempts'))
                if get('attempts') is not None else Text())]),
            'rejected': (get('rejected'), [self._count(get('rejected')),
                                           get('pending') is not None and self._count(get('pending'), 'pending')]),
            'turns': (get('turns'), [self._count(get('turns')),
                                     get('wall_clock_ms') is not None
                                     and self._wall_clock(get('wall_clock_ms'))]),
            'tokens-io': (get('input_tokens'), [self._count(get('input_tokens'), 'in', compact=True),
                                                get('output_tokens') is not None
                                                and self._count(get('output_tokens'), 'out', compact=True)]),
        }[name]
        label = 'tokens' if name == 'tokens-io' else name
        if first is None:
            return self._label(label) + Text('unavailable', style='yellow')
        return self._fit(label, [part for part in parts if part])

    def _line(self, name, fleet, summary, clock):
        if name == 'contributors':
            return Text('CONTRIBUTORS · as of ' + source_clock(clock), style='dim')
        if name in ('devices', 'accepted', 'rejected', 'turns', 'tokens-io'):
            return self._contributors(name, summary)
        if name == 'tokens':
            value = summary.get('tokens_per_completed_job') if isinstance(summary, dict) else None
            return self._label('tokens/job') + (Text('unavailable', style='yellow') if value is None else
                                              Text(fmt_int(value), style='bold') + Text(' (served)', style='dim'))
        if name in ('model', 'model-note'):
            return self._model_lines(fleet)[name == 'model-note']
        label = self._label(name)
        if not isinstance(fleet, dict):
            return Text() if name == 'paused-detail' else label + Text('unavailable', style='yellow')
        if name in _MIXES:
            rows = fleet.get(_MIXES[name])
            if not isinstance(rows, list):
                return label + Text('unavailable', style='yellow')
            return self._fit(name, [self._item(row.get('value'), row.get('count')) for row in rows if isinstance(row, dict)])
        if name == 'heartbeat':
            endpoints = [fleet.get('heartbeat_oldest_ts'), fleet.get('heartbeat_newest_ts')]
            if any(value is None for value in endpoints):
                return label + Text('unavailable', style='yellow')
            return label + Text(' – '.join(datetime.fromtimestamp(value).strftime('%H:%M:%S') for value in endpoints))
        paused = self._paused(fleet)
        if name == 'paused-detail':
            parts = [Text(f"#{row['token_id']} until {hhmm(row['until_ts'])} ×{fmt_int(row['failures'])}") for row in paused]
            return self._fit('', parts, '')
        if not isinstance(fleet.get('paused'), list):
            return label + Text('unavailable', style='yellow')
        return label + (Text(fmt_int(len(paused)), style='bold red') if paused else Text('none', style='green'))
