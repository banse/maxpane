"""JOB, token history and control facts for the six-dashboard screen."""
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static, RichLog
from maxpane_dashboard.widgets.panels import PanelBase, SparklinePanel
from maxpane_dashboard.widgets.seat.hero import _word
from maxpane_dashboard.widgets.seat.seat_job_text import api_sections, facts, outcome_usage
from maxpane_dashboard.widgets.seat._chain import job_link_style
from maxpane_dashboard.widgets.fmt import fmt_int, DASH
from maxpane_dashboard.analytics.seat_signals import parse_iso, as_of_hhmm


class SeatJob(PanelBase):
    TITLE = 'JOB'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._jobs = []
        self._selected_key = None

    def compose_body(self) -> ComposeResult:
        with VerticalScroll(id='seat-job-scroll'):
            yield Static(Text('no jobs yet'), id='seat-job-content')

    def update_data(self, seat_current_jobs=None, seat_jobs=None, seat_sources=None, seat_as_of_hhmm=None,
                    seat_offline=None, **_kwargs):
        self._offline = seat_offline is True
        self._clock = (seat_as_of_hhmm or {}).get('standing')
        current = seat_current_jobs or []
        self._running = {job.get('jobId') for job in current}
        cached = {job.get('jobId'): job for job in seat_jobs or []}
        self._jobs = [dict(job, **{key:value for key,value in cached.get(job.get('jobId'), {}).items() if value is not None})
                      for job in current] if current else (seat_jobs or [])[:1]
        if not any(self._identity(j) == self._selected_key for j in self._jobs):
            self._selected_key = self._identity(self._jobs[0]) if self._jobs else None
        self._paint()

    @staticmethod
    def _identity(job):
        return job.get('key') or job.get('jobId')

    def selected_row(self):
        return next((j for j in self._jobs if self._identity(j) == self._selected_key), None)

    def next_job(self):
        if self._jobs:
            index = next((i for i, j in enumerate(self._jobs) if self._identity(j) == self._selected_key), 0)
            row = self._jobs[(index + 1) % len(self._jobs)]
            self._selected_key = self._identity(row)
            self._paint()

    def on_resize(self):
        if self._jobs:
            self._paint()

    def _paint(self):
        row = self.selected_row()
        if row is None:
            self.write('.panel-title', Text('JOB · none yet'))
            self.write('#seat-job-content', Text('no jobs yet', style='dim'))
            return
        working = row.get('jobId') in self._running
        title = 'JOB · working' if working else 'JOB · last · stored'
        stamp = self._clock if working else as_of_hhmm(row.get('storedUtc'))
        self.write('.panel-title', Text(title + (f' · as of {stamp}' if working and stamp else f' {stamp}' if stamp else '')))
        text = Text(' · '.join(_word(row.get(k)) for k in ('nodeId8', 'nodeKey', 'role') if row.get(k)))
        if row.get('jobId'):
            text.append(' · job ').append(str(row['jobId'])[:8], style=job_link_style(row['jobId']))
        if len(self._jobs) > 1:
            text.append(f' · {self._jobs.index(row)+1} of {len(self._jobs)}', style='dim')
        text.append(' · Enter detail', style='dim')
        for heading, content in api_sections(row, working=working, offline=self._offline, width=max(12, self.content_region.width-2)):
            text.append('\n\n' + heading + '\n', style='bold').append_text(content)
        text.append('\n').append_text(outcome_usage(row)).append('\n').append_text(facts(row))
        self.write('#seat-job-content', text)


class SeatOutputTokens(SparklinePanel):
    TITLE = 'OUTPUT TOKENS / DAY · 14 d'
    LINE_IDS = ('seat-output-tokens-series',)
    LABEL_WIDTH = 8
    SHOW_ARROW = False
    MIN_POINTS = 2
    EMPTY_TEXT = 'no token data yet'

    def compose_body(self):
        yield from super().compose_body()
        yield Static("", id="seat-output-summary")

    def update_data(self, seat_cost_series=None, seat_cost_tokens=None, seat_output_tokens=None,
                    seat_sources=None, seat_as_of_hhmm=None, **_kwargs):
        raw = (seat_cost_series or {}).get('outputTokensPerDay') or []
        points = [(parse_iso(row[0] + 'T00:00:00Z'), row[1]) for row in raw
                  if isinstance(row, (list, tuple)) and len(row) == 2 and isinstance(row[0], str)]
        metrics = seat_output_tokens or {}
        self.EMPTY_TEXT = ('1 day so far' if len(points) == 1 else
                           'no token data yet (sessions: ' + _word(metrics.get('reason') or 'unavailable') + ')')
        self.render_series([('out tok', points, 'cyan', '')])
        count = lambda key: fmt_int(metrics[key]) if metrics.get(key) is not None else DASH
        self.write('#seat-output-summary', Text(f'today {count("today")} · 7 d {count("sevenDays")} · avg {count("averagePerDay")} / day', style='dim'))


class SeatGate(PanelBase):
    TITLE = 'GATE'

    def compose_body(self):
        yield Static(Text('gate unavailable'), id='seat-gate-content')

    def update_data(self, seat_control_gate=None, seat_control_drain=None, seat_sources=None, seat_as_of_hhmm=None, **_kwargs):
        gate = seat_control_gate or {}
        stamp = (seat_as_of_hhmm or {}).get('broker')
        self.write('.panel-title', Text('GATE' + (f' · as of {stamp}' if stamp else '')))
        word = lambda key: _word(gate.get(key)) if gate.get(key) is not None else DASH
        self.write('#seat-gate-content', Text('\n'.join([
            f'idle beats: {word("idleBeats")} of {word("idleBeatsRequired")}',
            f'plane: {word("planeMode")} · running {word("planeRunning")}',
            f'last line: {word("lastLifecycleLine")}', f'outbox files: {word("outboxFiles")}',
            f'unit active: {word("unitActive")}',
        ])))


class SeatAudit(PanelBase):
    TITLE = 'AUDIT'

    def compose_body(self):
        yield RichLog(id='seat-audit-log', wrap=True, markup=False, highlight=False)

    def update_data(self, seat_control_last_audit=None, seat_control_in_flight=None, seat_sources=None,
                    seat_as_of_hhmm=None, **_kwargs):
        log = self.query_one('#seat-audit-log', RichLog)
        log.clear()
        rows = seat_control_last_audit
        if not rows:
            log.write(Text('no audit entries' if rows == [] else 'audit unavailable', style='dim'))
        else:
            for row in rows[-20:]:
                text = Text((as_of_hhmm(row.get('ts')) or DASH) + ' ' + ' '.join(_word(row.get(k)) for k in ('verb', 'phase', 'outcome') if row.get(k)), style='dim')
                if row.get('verified') is not None:
                    text.append(f' · verified {row["verified"]}', style='green' if row['verified'] is True else 'red')
                if row.get('connected') is not None:
                    text.append(' · connected ' + _word(row['connected']), style='green' if row['connected'] is True else 'yellow')
                if row.get('seq') is not None:
                    text.append(f' (#{row["seq"]})')
                log.write(text)
