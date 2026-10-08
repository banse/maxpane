"""Bounded live IMD events and an input; no I/O or clock in this widget."""
from collections import deque
from textual.message import Message
from textual.widgets import Input, RichLog, Static
from rich.text import Text
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.fmt import fmt_int, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import clip, cell_len, WIDEN_HINT
from maxpane_dashboard.widgets.surf._icons import mark_addresses, keep_units, unmark, link_in_order

COMMAND_LIMIT = 512
REPLY_LIMIT = 200
EVENT_LIMIT = 60
#: IMD event/command prose does not carry chain identity; copy without guessing an explorer.
EXPLORER = None


def fit_prose(value, width, *, style="") -> tuple[Text, bool]:
    """Fit literal served text, preserving address/icon units and safe links."""
    marked, addresses, spans = mark_addresses(flatten(value), width=17)
    fitted = keep_units(marked, spans, clip(marked, max(0, width)))
    out = Text(unmark(fitted or ("…" if marked and width else "")), style=style)
    link_in_order([out], addresses, explorer=EXPLORER)
    return out, cell_len(marked) > width


def fitted_prose(value, width, *, style="") -> Text:
    return fit_prose(value, width, style=style)[0]


class SurfboardTerminal(PanelBase):
    TITLE = "IMD TERMINAL · recent events"
    DEFAULT_CSS = """
    SurfboardTerminal { height: 1fr; min-height: 11; border: round #475047; background: #080c09; padding: 0 1; }
    SurfboardTerminal > .panel-title { height: 1; color: #a2d84a; }
    SurfboardTerminal > .terminal-overview { height: 1; color: #a5b29d; text-wrap: nowrap; }
    SurfboardTerminal > RichLog { height: 1fr; min-height: 3; background: #080c09; scrollbar-size-vertical: 1; scrollbar-gutter: stable; }
    SurfboardTerminal > Input { height: 3; background: #101710; border: round #475047; color: #d8ddd5; }
    SurfboardTerminal > Input:focus { border: round #a2d84a; }
    """

    class CommandRequested(Message):
        def __init__(self, command):
            super().__init__()
            self.command = command

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._events = None
        self._overview = None
        self._sources = {}
        self._replies = deque(maxlen=REPLY_LIMIT)
        self._reply_serial = 0
        self._paint_serial = 0
        self._row_keys = []
        self._pending_scroll = None

    def compose_body(self):
        yield Static(Text("network unavailable"), classes="terminal-overview")
        yield RichLog(id="surfboard-events", wrap=False, min_width=1, max_lines=260, auto_scroll=False, markup=False)
        yield Input(placeholder="? for commands", id="surfboard-command", max_length=COMMAND_LIMIT)

    @property
    def command_input(self):
        return self.query_one("#surfboard-command", Input)

    def focus_input(self):
        self.command_input.focus()

    def add_reply(self, lines):
        for line in [lines] if isinstance(lines, str) else lines:
            for part in str(line).splitlines() or [""]:
                self._reply_serial += 1
                self._replies.append((f"reply:{self._reply_serial}", flatten(part)))
        self._paint()

    def clear_replies(self):
        self._replies.clear()
        self._paint()

    def update_data(self, surfboard_overview=None, surfboard_events=None, surfboard_sources=None, **_kwargs):
        self._overview = surfboard_overview if isinstance(surfboard_overview, dict) else None
        self._sources = surfboard_sources if isinstance(surfboard_sources, dict) else {}
        if isinstance(surfboard_events, list):
            unique = {}
            for row in surfboard_events:
                if isinstance(row, dict) and isinstance(row.get("key"), str):
                    unique[row["key"]] = row
            self._events = list(unique.values())[-EVENT_LIMIT:]
        else:
            self._events = None
        self._paint()

    def on_resize(self):
        self.call_after_refresh(self._paint)

    def _overview_source(self):
        source = self._sources.get("overview")
        return source if isinstance(source, dict) else {}

    def _header(self, width):
        if self._overview is None:
            return Text("network unavailable", style="#d5a24e"), False
        overview = self._overview or {}
        fields = (("agents_online", "online"), ("working_now", "working"),
                  ("jobs_24h", "jobs"), ("oracles_24h", "oracles"), ("accepted_24h", "steps"))
        parts = []
        for key, label in fields:
            value = overview.get(key)
            shown = fmt_int(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else "—"
            parts.append(f"{shown} {label}")
        text = " · ".join(parts[:2]) + "  |  24h " + " · ".join(parts[2:])
        source = self._overview_source()
        if source.get("state") == "stale":
            text = "stale · " + text
        return fit_prose(text, width, style="#a5b29d")

    def _event_text(self, row, previous_job, width):
        job = row.get("job_id")
        grouped = job is not None and job == previous_job
        token = row.get("token_id")
        actor = f"#{token}" if isinstance(token, int) and not isinstance(token, bool) and token >= 0 else "swarm"
        state = flatten(row.get("state")) or flatten(row.get("step")) or "unknown"
        role = flatten(row.get("role")).casefold()
        # Some native events describe role separately from their running state.
        if state in ("running", "executing"):
            state = {"builder": "building", "implement": "building",
                     "reviewer": "reviewing", "review": "reviewing"}.get(role, state)
        prefix = f"{'└' if grouped else '›'} {hhmm(row.get('timestamp'))} {clip(flatten(row.get('kind')) or 'event', 7):<7} {actor:<7} {clip(state, 11):<11} "
        line, clipped = fit_prose(prefix + flatten(row.get("objective")), width)
        line.stylize("#71856d", 0, min(8, len(line)))
        return line, clipped

    def _paint(self):
        if not self.is_mounted:
            return
        log = self.query_one(RichLog)
        old_y = int(log.scroll_y)
        following = not self._row_keys or log.scroll_y >= log.max_scroll_y
        anchor = self._row_keys[old_y] if old_y < len(self._row_keys) else None
        if self._pending_scroll is not None:
            following, anchor, old_y = self._pending_scroll
        self._pending_scroll = (following, anchor, old_y)
        width = max(1, log.scrollable_content_region.width)
        rows = []
        clipped = False
        previous = None
        if not self._events:
            rows.append(("events:empty", Text("events unavailable" if self._events is None else "no recent events", style="dim")))
        for row in self._events or []:
            line, lost = self._event_text(row, previous, width)
            clipped |= lost
            rows.append(("event:" + row["key"], line))
            previous = row.get("job_id")
        for key, reply in self._replies:
            line, lost = fit_prose(reply, width, style="#c2d5b9")
            clipped |= lost
            rows.append((key, line))
        keys = [key for key, _ in rows]
        self._row_keys = keys
        self._paint_serial += 1
        serial = self._paint_serial
        log.clear()
        for _, line in rows:
            log.write(line, scroll_end=False)
        source = self._overview_source()
        clock = " · read " + hhmm(source.get("read_ts")) if source.get("read_ts") is not None else ""
        header, header_clipped = self._header(width)
        hint = " " + WIDEN_HINT if clipped or header_clipped else ""
        self.write(".panel-title", Text(self.TITLE + clock + hint))
        self.write(".terminal-overview", header)

        def restore():
            if serial != self._paint_serial:
                return
            self._pending_scroll = None
            if following:
                log.scroll_end(animate=False, immediate=True, x_axis=False)
            else:
                y = keys.index(anchor) if anchor in keys else min(old_y, max(0, len(keys) - 1))
                log.scroll_to(y=y, animate=False, immediate=True)
        self.call_after_refresh(restore)

    def on_input_submitted(self, event):
        if event.input is self.command_input:
            event.stop()
            command = event.value[:COMMAND_LIMIT]
            self.command_input.value = ""
            if command.strip():
                self.add_reply("> " + command)
                self.post_message(self.CommandRequested(command))
