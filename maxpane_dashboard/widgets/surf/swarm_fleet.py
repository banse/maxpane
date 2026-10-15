"""Labelled worker metadata groups and the independent contributor token metric."""
from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten, strip_tags
from maxpane_dashboard.widgets.panels import SignalsPanelBase
from maxpane_dashboard.widgets.sparkline_common import fmt_compact
from maxpane_dashboard.widgets.surf._fmt import source_clock, short_model
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token

# Eleven cells align the longest label, tokens/job, plus one separating cell.
# Runtime shows two values; OS and slots expand in pairs. Three named model /
# effort pairs keep their omitted count inline. Daemon shows the leader.
# RECEIPTS has a blank row under its sub-header and five /contributors
# lines (owner, 2026-09-22: "show more data about the contributors"); a pair
# that outgrows its line keeps its first value and counts the rest as +N.
LABEL_WIDTH = 11
_NAMES = ('runtime', None, 'model', None, 'daemon', None, 'os', None,
          'profile', None, 'slots', None,
          'paused', 'paused-detail', None, None, 'contributors', None,
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
    SurfSwarmFleet > #surf-fleet-contributors { color: $text-muted; text-style: bold; }
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = None

    def on_resize(self):
        if self._data is not None:
            self.update_data(**self._data)

    def update_data(self, swarm_fleet=None, swarm_board_summary=None,
                    swarm_board_as_of_hhmm=None, swarm_workers_as_of_hhmm=None,
                    swarm_outcomes_source=None, swarm_contributors_as_of_hhmm=None, **_kwargs):
        self._data = dict(swarm_fleet=swarm_fleet, swarm_board_summary=swarm_board_summary,
                         swarm_board_as_of_hhmm=swarm_board_as_of_hhmm,
                         swarm_workers_as_of_hhmm=swarm_workers_as_of_hhmm,
                         swarm_outcomes_source=swarm_outcomes_source,
                         swarm_contributors_as_of_hhmm=swarm_contributors_as_of_hhmm)
        self.write('.panel-title', Text('FLEET · workers as of ' + source_clock(swarm_workers_as_of_hhmm)))
        for name in filter(None, _NAMES):
            self.query_one(f'#surf-fleet-{name}').tooltip = None
            self.write_guarded(f'#surf-fleet-{name}',
                               lambda name=name: self._line(name, swarm_fleet, swarm_board_summary, swarm_contributors_as_of_hhmm),
                               self._label(name) + Text('unavailable', style='yellow'))
        self.query_one('#surf-fleet-paused-detail').display = bool(self._paused(swarm_fleet))

    def _room(self):
        return max(self.size.width - 2, 0)

    @staticmethod
    def _label(label):
        return Text().append(label.ljust(LABEL_WIDTH), style='dim')

    def _number_style(self):
        return Style(color=self.app.get_css_variables()['foreground'], bold=True, dim=False)

    def _item(self, name, count):
        return Text().append(strip_tags(flatten(name)), style='dim').append(' ').append(fmt_int(count), style=self._number_style())

    def _fit(self, label, parts, empty='none reported'):
        prefix = self._label(label) if label else Text()
        if not parts:
            return prefix + Text(empty, style='dim')
        for keep in range(len(parts), -1, -1):
            values = parts[:keep] + ([Text(f'+{len(parts)-keep}', style=self._number_style())] if keep < len(parts) else [])
            text = prefix + Text(' · ').join(values)
            if text.cell_len <= self._room():
                return text
        text = Text(rowfit.clip(prefix.plain + f'+{len(parts)}', self._room()))
        text.stylize(self._number_style(), len(prefix.plain))
        return text

    def _metadata_row(self, label, parts, omitted=0, compact_label=False):
        """Fit names by terminal cells; preserve complete counts and count omissions."""
        for keep in range(len(parts), -1, -1):
            hidden = omitted + len(parts) - keep
            suffix = Text(f' +{hidden}', style=self._number_style()) if hidden else Text()
            values = [part.plain.rpartition(' ')[::2] for part in parts[:keep]]
            label_width = LABEL_WIDTH
            natural = LABEL_WIDTH + sum(part.cell_len for part in parts[:keep]) + 3 * max(keep - 1, 0) + suffix.cell_len
            if compact_label and natural > self._room():
                label_width = len(label) + 1
            room = self._room() - label_width - suffix.cell_len - 3 * max(keep - 1, 0)
            name_room = room - sum(cell_len(count) + 1 for _, count in values)
            if name_room < keep:
                continue
            widths = [cell_len(name) for name, _ in values]
            while sum(widths) > name_room:
                widest = max(range(keep), key=widths.__getitem__)
                widths[widest] -= 1
            fitted = [Text(rowfit.clip(name, width), style='dim') + Text(' ' + count, style=self._number_style())
                      for (name, count), width in zip(values, widths)]
            return Text(label.ljust(label_width), style='dim') + Text(' · ').join(fitted) + suffix
        return Text(f'+{omitted + len(parts)}', style=self._number_style())

    def _group(self, label, parts, columns=1, limit=None):
        """Group metadata, reserving the last row's inline omission count."""
        shown = parts if limit is None else parts[:limit]
        if not shown:
            return self._label(label) + Text('none reported', style='dim')
        lines = []
        for start in range(0, len(shown), columns):
            group = shown[start:start + columns]
            omitted = len(parts) - len(shown) if start + columns >= len(shown) else 0
            lines.append(self._metadata_row(label if not lines else '', group, omitted,
                                            compact_label=columns > 1))
        return Text('\n').join(lines)

    @staticmethod
    def _paused(fleet):
        rows = fleet.get('paused') if isinstance(fleet, dict) else None
        return [row for row in rows if isinstance(row, dict) and seat_token(row.get('token_id')) is not None] if isinstance(rows, list) else []

    def _model_lines(self, fleet):
        rows = fleet.get('models') if isinstance(fleet, dict) else None
        prefix = self._label('model')
        if not isinstance(rows, list):
            return prefix + Text('unavailable', style='yellow')
        parts = []
        full = []
        for row in rows:
            if isinstance(row, dict):
                model = row.get('model')
                raw_name = 'none' if model is None else strip_tags(flatten(model)) or '—'
                if model is not None and row.get('effort') is not None:
                    raw_name += ' ' + strip_tags(flatten(row['effort']))
                full.append(self._item(raw_name, row.get('count')))
                if model is None:
                    continue
                cleaned = short_model(model)
                name = cleaned or '—'
                if cleaned and row.get('effort') is not None:
                    name += ' ' + strip_tags(flatten(row['effort']))
                parts.append(self._item(name, row.get('count')))
        self.query_one('#surf-fleet-model').tooltip = Text('\n').join(full) if full else None
        return self._group('model', parts, limit=3)

    def _count(self, value, word='', compact=False):
        out = Text().append(fmt_compact(value) if compact else fmt_int(value), style=self._number_style())
        return out.append(' ' + word, style='dim') if word else out

    def _wall_clock(self, ms):
        """Wall-clock time to the nearest hour; under half an hour, whole minutes
        (a floor read 59 minutes as ``0 h`` and 5.9 h as ``5 h``, F64)."""
        if ms < _MS_PER_HOUR // 2:
            return self._count((ms + _MS_PER_MINUTE // 2) // _MS_PER_MINUTE, 'min')
        return self._count((ms + _MS_PER_HOUR // 2) // _MS_PER_HOUR, 'h')

    def _contributors(self, name, summary):
        """One /contributors line; its first value unread is the whole line unread."""
        summary = summary if isinstance(summary, dict) else {}
        get = lambda key: seat_token(summary.get('receipt_' + key if key in ('seats','attempts','accepted','rejected','pending') else key))
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
            return Text('RECEIPTS · read ' + source_clock(clock), style='bold')
        if name in ('devices', 'accepted', 'rejected', 'turns', 'tokens-io'):
            return self._contributors(name, summary)
        if name == 'tokens':
            value = summary.get('tokens_per_completed_job') if isinstance(summary, dict) else None
            return self._label('tokens/job') + (Text('unavailable', style='yellow') if value is None else
                                              self._count(value, '(served)'))
        if name == 'model':
            return self._model_lines(fleet)
        label = self._label(name)
        if not isinstance(fleet, dict):
            return Text() if name == 'paused-detail' else label + Text('unavailable', style='yellow')
        if name in _MIXES:
            rows = fleet.get(_MIXES[name])
            if not isinstance(rows, list):
                return label + Text('unavailable', style='yellow')
            parts = [self._item(row.get('value'), row.get('count')) for row in rows if isinstance(row, dict)]
            self.query_one(f'#surf-fleet-{name}').tooltip = Text('\n').join(parts) if parts else None
            if name == 'profile':
                return self._fit(name, parts)
            if name == 'daemon':
                return self._group(name, parts[:1])
            return self._group(name, parts, columns=2, limit=2 if name == 'runtime' else None)
        paused = self._paused(fleet)
        if name == 'paused-detail':
            parts = [Text(f"#{row['token_id']} until {hhmm(row['until_ts'])} ×{fmt_int(row['failures'])}") for row in paused]
            return self._fit('', parts, '')
        if not isinstance(fleet.get('paused'), list):
            return label + Text('unavailable', style='yellow')
        return label + (Text(fmt_int(len(paused)), style='bold red') if paused else Text('none', style='green'))
