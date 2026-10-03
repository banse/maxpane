"""Mounted body support for the round-9 screen; expanded content lands in WP5."""
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static, RichLog
from maxpane_dashboard.widgets.panels import PanelBase, SparklinePanel
from maxpane_dashboard.widgets.seat.hero import _word
from maxpane_dashboard.analytics.seat_signals import parse_iso, gate_preview


class SeatJob(PanelBase):
    TITLE = 'JOB'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._jobs = []
        self._selected_key = None

    def compose_body(self) -> ComposeResult:
        yield Static(Text('no jobs yet'), id='seat-job-content')

    def update_data(self, seat_current_jobs=None, seat_jobs=None, seat_sources=None, seat_as_of_hhmm=None,
                    seat_offline=None, **_kwargs):
        running = {j.get('jobId') for j in seat_current_jobs or []}
        jobs = [j for j in seat_jobs or [] if j.get('jobId') in running] if running else (seat_jobs or [])[:1]
        self._jobs = jobs or (seat_current_jobs or [])
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

    def _paint(self):
        row = self.selected_row()
        self.write('#seat-job-content', Text('no jobs yet' if row is None else
                   ' · '.join(_word(row.get(k)) for k in ('nodeId8', 'nodeKey', 'role') if row.get(k))))


class SeatOutputTokens(SparklinePanel):
    TITLE = 'OUTPUT TOKENS / DAY · 14 d'
    LINE_IDS = ('seat-output-tokens-series',)
    LABEL_WIDTH = 8
    SHOW_ARROW = False
    MIN_POINTS = 2
    EMPTY_TEXT = 'no token data yet'

    def update_data(self, seat_cost_series=None, seat_cost_tokens=None, seat_output_tokens=None,
                    seat_sources=None, seat_as_of_hhmm=None, **_kwargs):
        raw = (seat_cost_series or {}).get('outputTokensPerDay') or []
        points = [(parse_iso(row[0] + 'T00:00:00Z'), row[1]) for row in raw
                  if isinstance(row, (list, tuple)) and len(row) == 2 and isinstance(row[0], str)]
        self.render_series([('out tok', points, 'cyan', '')])


class SeatControl(PanelBase):
    TITLE = 'CONTROL'

    def compose_body(self):
        yield Static(Text('broker unavailable'), id='seat-control-body-content')

    def update_data(self, seat_control_gate=None, seat_control_drain=None, seat_control_in_flight=None,
                    seat_control_broker_reachable=None, seat_unit_boot_enabled=None, seat_unit_graceful_stop_possible=None,
                    seat_unit_active_state=None, seat_host_kind=None, seat_machine_orphans=None, seat_daemon_version=None,
                    seat_release_available=None, seat_control_plan=None, seat_control_status=None, seat_control_mode=None,
                    seat_sources=None, **_kwargs):
        word, _ = gate_preview(seat_control_gate, broker_reachable=seat_control_broker_reachable,
                               drain=seat_control_drain, in_flight=seat_control_in_flight)
        lines = [f'[r] restart — {_word(word)}', '[d] drain-restart', '[s] stop · [S] start',
                 '[b] boot · [o] kill orphans · [D] doctor', '[x] cancel drain',
                 'skills, boot, capacity, tiers → CONFIG & SKILLS (3)']
        if seat_control_status:
            lines.append(_word(seat_control_status))
        self.write('#seat-control-body-content', Text('\n'.join(lines)))


class SeatGate(PanelBase):
    TITLE = 'GATE'

    def compose_body(self):
        yield Static(Text('gate unavailable'), id='seat-gate-content')

    def update_data(self, seat_control_gate=None, seat_control_drain=None, seat_sources=None, seat_as_of_hhmm=None, **_kwargs):
        gate = seat_control_gate or {}
        self.write('#seat-gate-content', Text('\n'.join(f'{label}: {_word(gate.get(key)) or "--"}' for label, key in
                   [('idle beats', 'idleBeats'), ('plane', 'planeMode'), ('running', 'planeRunning'),
                    ('last line', 'lastLifecycleLine'), ('outbox', 'outboxFiles')])) )


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
                log.write(Text(' · '.join(_word(row.get(k)) for k in ('ts', 'verb', 'phase', 'outcome') if row.get(k))))
