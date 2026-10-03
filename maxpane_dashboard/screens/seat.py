"""PEPEPANE's six composed dashboards; shared DashboardScreen owns every refresh."""
from __future__ import annotations
import logging
from rich.text import Text
from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, DataTable, RichLog, Input
from maxpane_dashboard.data.seat_models import SEAT_WIDGET_SIGNATURES
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen, keys
from maxpane_dashboard.screens.seat_task_detail import SeatTaskDetail
from maxpane_dashboard.widgets.fmt import DASH
from maxpane_dashboard.widgets.seat import (
    SeatHero, SeatNow, SeatJob, SeatLog, SeatMachine, SeatCost, SeatOutputTokens, SeatLedgerTable,
    SeatConfig, SeatSkills, SeatRecords, SeatNodes, SeatControl, SeatGate, SeatAudit,
)
from maxpane_dashboard.widgets.seat.seat_table import SeatTable
from maxpane_dashboard.widgets.status_bar import StatusBar

logger = logging.getLogger(__name__)

#: WP4 foundation pins measured 2026-10-03 on textual 8.2.8. Each body was
#: swept downward at every width 134..100 / height 50..16, then certified by
#: boundary_set (100/150 columns, 16/60 rows, pin ±1 and table tier onsets).
#: Healthy, 50-skill/400-record worst and unattributed payloads agree. At 131
#: the shared hero clips; all six widths clear at 132. Full body content and
#: healthy/worst certification after WP5 remain WP6 work; these describe the
#: mounted foundation, not the final redesign. Raw LOG scrollback is unbounded
#: and keeps its own horizontal scrollbar. No bounded table hides columns at
#: a body's pin. LEDGER full clears at 126, so
#: the former 210-column LEDGER_NEVER_CLEARS_BELOW exception is removed.
SEAT_BODY_PINS = {
    #: SEAT: top needs 20 rows, LEDGER 10, fixed title/hero/status 10 => 40.
    #: At 39 a registered container scrolls and the title advertises ‹ taller.
    "SEAT": (132, 40),
    #: LIVE: NOW/JOB and LOG need 20 body rows; whole at 30, scrolling at 29.
    "LIVE": (132, 30),
    #: CONFIG & SKILLS: two independently scrolling tables, body floor 12;
    #: whole at 22, body scrolling at 21. Values fit without a clipped form.
    "CONFIG & SKILLS": (132, 22),
    #: RECORDS: table body floor 10; whole at 20, body scrolling at 19.
    "RECORDS": (132, 20),
    #: NODES: table body floor 10; independently measured whole at 20, not 19.
    "NODES": (132, 20),
    #: CONTROL: GATE/AUDIT floor 16; whole at 26, scrolling at 25.
    "CONTROL": (132, 26),
}
SEAT_FULL_LAYOUT_COLUMNS = max(width for width, _ in SEAT_BODY_PINS.values())
SEAT_FULL_LAYOUT_ROWS = max(height for _, height in SEAT_BODY_PINS.values())

#: Restated from ``screens/surf.py`` (never imported from there -- the fork touches no surf module);
#: bound by ``tests/screens/test_seat_layout.py::test_the_taller_hint_is_the_repo_spelling``.
TALLER_HINT = "‹ taller"


TITLE_BAR_ID = "seat-title-bar"
HERO_ID = "seat-hero"
BODY_ID = "seat-body"
DASHBOARDS = ("SEAT", "LIVE", "CONFIG & SKILLS", "RECORDS", "NODES", "CONTROL")
BODY_IDS = dict(zip(DASHBOARDS, ("seat-body-seat", "seat-body-live", "seat-body-config", "seat-body-records", "seat-body-nodes", "seat-body-control")))
SCROLL_CONTAINERS = {
    "SEAT": ("seat-body-seat", "seat-seat-machine", "seat-seat-cost"),
    "LIVE": ("seat-body-live", "seat-live-left"),
    "CONFIG & SKILLS": ("seat-body-config",), "RECORDS": ("seat-body-records",),
    "NODES": ("seat-body-nodes",), "CONTROL": ("seat-body-control", "seat-control-left", "seat-control-right"),
}
KEY_HINTS = {
    "SEAT": "[dim]1–6 dashboards · enter detail[/]",
    "LIVE": "[dim]1–6 dashboards · h beats · n next · enter detail[/]",
    "CONFIG & SKILLS": "[dim]1–6 dashboards · tab table · space toggle[/]",
    "RECORDS": "[dim]1–6 dashboards · f filter · m more · enter detail[/]",
    "NODES": "[dim]1–6 dashboards · w window[/]",
    "CONTROL": "[dim]r restart · d drain · s/S stop/start · b boot · o/D/x[/]",
}
INITIAL_TITLE = "PEPEPANE · connecting…"


def title_line(data: dict, *, row_hint: bool) -> str:
    token = data.get("seat_token_id")
    token_word = str(token) if isinstance(token, int) and not isinstance(token, bool) else DASH
    kind = data.get("seat_host_kind") if isinstance(data.get("seat_host_kind"), str) else DASH
    as_of = data.get("seat_as_of_hhmm") if isinstance(data.get("seat_as_of_hhmm"), dict) else {}
    clock = as_of.get("tail") if isinstance(as_of.get("tail"), str) else "--:--"
    line = f"PEPEPANE · IDMD #{token_word} · {escape(kind)} · as of {escape(clock)}"
    if data.get("seat_hero_state") in ("amber", "red"):
        reasons = data.get("seat_hero_reasons") or []
        if reasons:
            colour = "red" if data["seat_hero_state"] == "red" else "yellow"
            line += f" · [{colour}]⚠ {escape(str(reasons[0]))}[/]"
    if row_hint:
        line += f" · [yellow]{TALLER_HINT}[/]"
    if data.get("seat_offline") is True:
        line += " · [dim]offline[/]"
    return line


class SeatStatusBar(StatusBar):
    """Seat has dashboard-specific keys; it has no shared application's menu."""

    def _ordinary_status(self, last_updated_seconds_ago, error_count, poll_interval):
        errors = f" · [red]{error_count} errors[/]" if error_count else ""
        return f"[dim]q quit · t theme ·[/] {self._key_hints} [dim]· {poll_interval}s poll[/]{errors}"


class SeatScreen(DashboardScreen):
    GAME_NAME = "PEPEPANE"
    REFRESH_WORKER_NAME = "seat-refresh"
    KEY_HINTS = KEY_HINTS
    BINDINGS = [
        *[Binding(str(i + 1), f"dashboard({i})", name, show=False) for i, name in enumerate(DASHBOARDS)],
        Binding("c", "dashboard(5)", "Control", show=False),
        Binding("escape", "escape", "Back", show=False),
        Binding("r", "refresh_or_restart", "Refresh / restart", show=False),
        *[Binding(key, f"control_verb('{verb}')", verb, show=False) for key, verb in
          (("d", "drain-restart"), ("s", "stop"), ("S", "start"), ("b", "boot"),
           ("o", "kill-orphans"), ("D", "doctor"), ("x", "cancel-drain"))],
        Binding("enter", "task_detail", "Detail", show=False),
        Binding("space", "toggle_setting", "Toggle", show=False),
        Binding("tab", "config_table", "Table", show=False),
        Binding("h", "toggle_heartbeats", "Heartbeats", show=False),
        Binding("n", "next_job", "Next job", show=False),
        Binding("f", "record_filter", "Filter", show=False),
        Binding("m", "record_more", "More", show=False),
        Binding("w", "node_window", "Window", show=False),
    ]
    SCOPED_CSS = False
    DEFAULT_CSS = """
    SeatScreen #seat-title-bar { width: 100%; height: 1; content-align: center middle; text-align: center; background: $surface; color: $text-muted; text-style: bold; padding: 0 2; }
    SeatScreen #seat-hero { height: 7; margin: 0 0 1 0; }
    SeatScreen #seat-body { height: 1fr; width: 100%; }
    SeatScreen .seat-dashboard { height: 100%; width: 100%; overflow-y: auto; scrollbar-gutter: stable; scrollbar-size: 1 1; }
    SeatScreen .seat-scroll { overflow-y: auto; scrollbar-gutter: stable; scrollbar-size: 1 1; }
    SeatScreen #seat-seat-top { height: 1fr; min-height: 20; }
    SeatScreen #seat-seat-machine { width: 1fr; height: 100%; }
    SeatScreen #seat-seat-cost { width: 1fr; height: 100%; }
    SeatScreen SeatMachine { height: auto; min-height: 19; }
    SeatScreen SeatCost { height: auto; min-height: 12; }
    SeatScreen SeatOutputTokens { height: 6; }
    SeatScreen SeatLedgerTable { height: 1fr; min-height: 10; }
    SeatScreen #seat-live-row { height: 100%; min-height: 20; }
    SeatScreen #seat-live-left { width: 2fr; height: 100%; }
    SeatScreen SeatNow { height: 7; }
    SeatScreen SeatJob { height: 1fr; min-height: 10; }
    SeatScreen #seat-job-content { height: 1fr; overflow-y: auto; scrollbar-gutter: stable; }
    SeatScreen SeatLog { width: 3fr; height: 100%; min-height: 10; }
    SeatScreen #seat-config-row { height: 100%; min-height: 12; }
    SeatScreen SeatConfig, SeatScreen SeatSkills { width: 1fr; height: 100%; }
    SeatScreen SeatRecords, SeatScreen SeatNodes { height: 100%; min-height: 10; }
    SeatScreen #seat-control-row { height: 100%; min-height: 16; }
    SeatScreen #seat-control-left, SeatScreen #seat-control-right { width: 1fr; height: 100%; }
    SeatScreen SeatControl { height: auto; min-height: 14; }
    SeatScreen SeatGate { height: auto; min-height: 10; }
    SeatScreen SeatAudit { height: 1fr; min-height: 6; }
    SeatScreen #seat-control-body-content, SeatScreen #seat-gate-content { height: auto; }
    SeatScreen #seat-audit-log { height: 1fr; }
    SeatScreen #seat-confirm-strip { height: auto; display: none; }
    SeatScreen #seat-confirm-input { height: 3; }
    SeatHero { height: 7; padding: 0 1 0 0; }
    SeatHero > SeatHeroBox { width: 1fr; height: 7; padding: 0 1; margin: 0 1 0 0; border: solid $panel; background: $surface; content-align: center top; text-align: center; text-wrap: nowrap; text-overflow: ellipsis; }
    SeatHero > SeatHeroBox.seat-selected { border: solid $success; }
    SeatScreen SeatNow > .panel-line, SeatScreen SeatMachine > .panel-line, SeatScreen SeatCost > .panel-line { text-wrap: nowrap; text-overflow: ellipsis; }
    SeatScreen SeatLog > RichLog { height: 1fr; }
    SeatScreen #seat-log-footer { height: 1; }
    SeatControlScreen { align: center middle; padding: 1 0; }
    SeatControlScreen #seat-control-box { width: 100%; max-width: 120; height: 100%; border: solid $accent; padding: 0 2; }
    SeatControlScreen #seat-control-title { height: 1; margin: 0 0 1 0; }
    SeatControlScreen #seat-control-scroll { height: 1fr; min-height: 4; overflow-x: hidden; }
    SeatControlScreen #seat-control-scroll Static { height: auto; width: 100%; }
    SeatControlScreen #seat-control-static { margin: 1 0 0 0; }
    SeatControlScreen #seat-control-plan { margin: 1 0 0 0; }
    SeatControlScreen #seat-control-status { margin: 1 0 0 0; }
    SeatControlScreen #seat-control-input { height: 3; margin: 1 0 0 0; }
    SeatControlScreen #seat-control-audit { height: auto; max-height: 6; margin: 1 0 0 0; }
    """
    PANELS = tuple((cls, keys(*SEAT_WIDGET_SIGNATURES[cls.__name__])) for cls in (
        SeatHero, SeatNow, SeatJob, SeatLog, SeatMachine, SeatCost, SeatOutputTokens, SeatLedgerTable,
        SeatConfig, SeatSkills, SeatRecords, SeatNodes, SeatControl, SeatGate, SeatAudit,
    ))

    def __init__(self, manager, poll_interval=5, name=None, **kwargs):
        super().__init__(manager, poll_interval, name=name, **kwargs)
        self._last_payload = None
        self.selected_dashboard = "LIVE"
        self.prompt_open = False
        self.record_limit = 40
        self.record_open_only = False

    def compose(self) -> ComposeResult:
        yield Static(Text(INITIAL_TITLE), id=TITLE_BAR_ID)
        yield SeatHero(id=HERO_ID)
        with Vertical(id=BODY_ID):
            with VerticalScroll(id=BODY_IDS['SEAT'], classes='seat-dashboard'):
                with Horizontal(id='seat-seat-top'):
                    with Vertical(id='seat-seat-machine', classes='seat-scroll'):
                        yield SeatMachine()
                    with Vertical(id='seat-seat-cost', classes='seat-scroll'):
                        yield SeatCost()
                        yield SeatOutputTokens()
                yield SeatLedgerTable()
            with VerticalScroll(id=BODY_IDS['LIVE'], classes='seat-dashboard'):
                with Horizontal(id='seat-live-row'):
                    with Vertical(id='seat-live-left', classes='seat-scroll'):
                        yield SeatNow()
                        yield SeatJob()
                    yield SeatLog()
            with VerticalScroll(id=BODY_IDS['CONFIG & SKILLS'], classes='seat-dashboard'):
                with Horizontal(id='seat-config-row'):
                    yield SeatConfig()
                    yield SeatSkills()
            with VerticalScroll(id=BODY_IDS['RECORDS'], classes='seat-dashboard'):
                yield SeatRecords()
            with VerticalScroll(id=BODY_IDS['NODES'], classes='seat-dashboard'):
                yield SeatNodes()
            with VerticalScroll(id=BODY_IDS['CONTROL'], classes='seat-dashboard'):
                with Horizontal(id='seat-control-row'):
                    with Vertical(id='seat-control-left', classes='seat-scroll'):
                        yield SeatControl()
                    with Vertical(id='seat-control-right', classes='seat-scroll'):
                        yield SeatGate()
                        yield SeatAudit()
        with Vertical(id='seat-confirm-strip'):
            yield Static(Text(''), id='seat-confirm-plan')
            yield Input(id='seat-confirm-input')
            yield Static(Text(''), id='seat-confirm-status')
        yield SeatStatusBar()

    def on_mount(self):
        self._record_window()
        self.select_dashboard('LIVE')

    def _prime_status_bar(self, bar):
        bar.set_key_hints(KEY_HINTS[self.selected_dashboard])
        bar._update_left()

    def _update_title(self, data):
        self._last_payload = data
        self._render_title()

    def on_resize(self, _event=None):
        self.call_after_refresh(self._render_title)

    def _body_is_cut(self):
        return any(self.query_one(f'#{name}').show_vertical_scrollbar for name in SCROLL_CONTAINERS[self.selected_dashboard]) if self.is_mounted else False

    def _render_title(self, _recheck=True):
        cut = self._body_is_cut()
        line = title_line(self._last_payload, row_hint=cut) if self._last_payload is not None else INITIAL_TITLE
        self.query_one(f'#{TITLE_BAR_ID}', Static).update(Text.from_markup(line))
        if _recheck:
            self.call_after_refresh(self._recheck_row_marker, cut)

    def _recheck_row_marker(self, rendered):
        if self._body_is_cut() != rendered:
            self._render_title(_recheck=False)

    def select_dashboard(self, name):
        if name not in DASHBOARDS:
            return
        for panel in self.query(SeatTable):
            if panel.is_on_screen:
                panel.remember_view()
        if self.prompt_open:
            self._cancel_prompt()
        self.selected_dashboard = name
        for dashboard, body_id in BODY_IDS.items():
            self.query_one(f'#{body_id}').display = dashboard == name
        self.query_one(SeatHero).select_dashboard(name)
        hint = getattr(self._data_manager, 'select_dashboard', None)
        if hint is not None:
            hint(name)
        self._prime_status_bar(self.query_one(StatusBar))
        self.call_after_refresh(self._focus_dashboard)
        self.call_after_refresh(self._render_title)

    def _focus_dashboard(self):
        if self.prompt_open:
            self.query_one('#seat-confirm-input', Input).focus()
            return
        target = {'SEAT': '#seat-ledger-table', 'LIVE': '#seat-log', 'CONFIG & SKILLS': '#seat-config-table',
                  'RECORDS': '#seat-records-table', 'NODES': '#seat-nodes-table', 'CONTROL': '#seat-audit-log'}
        self.query_one(target[self.selected_dashboard]).focus()

    def on_seat_hero_selected(self, event):
        self.select_dashboard(event.dashboard)

    def action_dashboard(self, index):
        if not self.prompt_open:
            self.select_dashboard(DASHBOARDS[index])

    def action_escape(self):
        if self.prompt_open:
            self._cancel_prompt()
        else:
            self.select_dashboard('LIVE')

    def _cancel_prompt(self):
        self.prompt_open = False
        self.query_one('#seat-confirm-strip').display = False
        self._data_manager.plan_open = False
        self._focus_dashboard()

    def set_focus(self, widget, scroll_visible=True, from_app_focus=False):
        # Enforce ownership before Textual forwards the next key, not in the
        # asynchronous DescendantFocus event (which can lose the first character).
        if self.prompt_open and self.is_mounted:
            widget = self.query_one('#seat-confirm-input', Input)
        super().set_focus(widget, scroll_visible=scroll_visible, from_app_focus=from_app_focus)

    def on_key(self, event):
        if not self.prompt_open or event.key == 'escape':
            return
        field = self.query_one('#seat-confirm-input', Input)
        if event.key == 'tab' or self.app.focused is not field:
            event.stop()
            event.prevent_default()
            field.focus()
            if event.key == 'enter':
                field.action_submit()
            elif event.character and event.character.isprintable():
                field.insert_text(event.character)

    def check_action(self, action, parameters):
        return not self.prompt_open or action == 'escape'

    def action_refresh_or_restart(self):
        if self.prompt_open:
            return
        if self.selected_dashboard == 'CONTROL':
            self._request_control('restart')
        else:
            self.action_refresh()

    def action_control_verb(self, verb):
        if not self.prompt_open and self.selected_dashboard == 'CONTROL':
            self._request_control(verb)

    def _request_control(self, verb):
        # WP5 attaches the one plan/confirm/apply/verify flow here.
        self.query_one('#seat-confirm-status', Static).update(Text('write flow not available yet'))

    def action_toggle_heartbeats(self):
        if not self.prompt_open and self.selected_dashboard == 'LIVE':
            self.query_one(SeatLog).toggle_heartbeats()

    def action_next_job(self):
        if not self.prompt_open and self.selected_dashboard == 'LIVE':
            self.query_one(SeatJob).next_job()

    def action_config_table(self):
        if self.prompt_open:
            self._focus_dashboard()
        elif self.selected_dashboard == 'CONFIG & SKILLS':
            tables = [self.query_one(SeatConfig).query_one(DataTable), self.query_one(SeatSkills).query_one(DataTable)]
            tables[1 if self.app.focused is tables[0] else 0].focus()
        else:
            self.focus_next()

    def action_toggle_setting(self):
        # WP5 validates the row and starts the shared write flow.
        pass

    def action_record_filter(self):
        if not self.prompt_open and self.selected_dashboard == 'RECORDS':
            self.record_open_only = not self.record_open_only
            self._record_window()

    def action_record_more(self):
        if not self.prompt_open and self.selected_dashboard == 'RECORDS':
            self.record_limit = min(400, self.record_limit + 20)
            self._record_window()

    def _record_window(self):
        self.query_one(SeatRecords).set_window(self.record_limit, self.record_open_only)
        hint = getattr(self._data_manager, 'set_record_window', None)
        if hint:
            hint(self.record_limit, open_only=self.record_open_only)

    def action_node_window(self):
        if not self.prompt_open and self.selected_dashboard == 'NODES':
            self.query_one(SeatNodes).toggle_window()

    def on_data_table_row_selected(self, event):
        event.stop()
        if not self.prompt_open:
            self.action_task_detail()

    def action_task_detail(self):
        if self.prompt_open:
            return
        if self.selected_dashboard == 'CONFIG & SKILLS':
            self.action_toggle_setting()
            return
        panels = {'SEAT': SeatLedgerTable, 'LIVE': SeatJob, 'RECORDS': SeatRecords}
        cls = panels.get(self.selected_dashboard)
        row = self.query_one(cls).selected_row() if cls else None
        if row is not None:
            read = getattr(self._data_manager, 'cached_task_detail', None)
            detail = read(row.get('key')) if read and row.get('key') else None
            self.app.push_screen(SeatTaskDetail(detail or row))
