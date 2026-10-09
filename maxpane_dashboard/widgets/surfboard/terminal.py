"""Bounded live IMD events and an input; no I/O or clock in this widget."""
from collections import deque
import math
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, RichLog, Static
from rich.text import Text
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.fmt import fmt_int, hhmm, fmt_age
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.rowfit import clip, cell_len, WIDEN_HINT
from maxpane_dashboard.widgets.surf._icons import mark_addresses, keep_units, unmark, link_in_order
from maxpane_dashboard.widgets.sparkline_common import fmt_compact

COMMAND_LIMIT = 512
REPLY_LIMIT = 200
EVENT_LIMIT = 60
#: IMD event/command prose does not carry chain identity; copy without guessing an explorer.
EXPLORER = None
INK = "#9fc99c"
DIM = "#537b52"
LIVE = "#b0edba"
FAIL = "#8b342a"
STEP_WORDS = {
    "implement": ("built", "building"), "build_contract_project": ("built", "building"),
    "build_dapp": ("built", "building"), "test": ("tested", "testing"),
    "tests": ("tested", "testing"), "review": ("reviewed", "reviewing"),
    "contract_review": ("reviewed", "reviewing"), "integrate": ("integrated", "integrating"),
    "manifest": ("attested", "attesting"), "deploy": ("deployed", "deploying"),
    "publish": ("published", "publishing"),
}
LIVE_STATES = frozenset(word for pair in STEP_WORDS.values() for word in pair) | {
    "working", "running", "executing", "leased", "accepted", "completed", "posted", "joined",
}


def _number(value):
    try:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def _market_money(value):
    """The market-cap face uses two decimals; token and network counts use one."""
    for divisor, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= divisor:
            return f"${value / divisor:.2f}{suffix}"
    return f"${value:.2f}"


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
    TITLE = "IMD TERMINAL"
    DEFAULT_CSS = """
    SurfboardTerminal { height: 1fr; min-height: 11; border: round #345533; background: #050805; color: #9fc99c; padding: 0 1; }
    SurfboardTerminal > .panel-title { height: 2; margin: 0; padding: 0; border-bottom: solid #253c24; color: #9fc99c; text-style: none; text-wrap: nowrap; }
    SurfboardTerminal > RichLog { height: 1fr; min-height: 3; background: #050805; scrollbar-size-vertical: 1; scrollbar-gutter: stable; scrollbar-color: #345533; }
    SurfboardTerminal > .terminal-prompt { height: 1; background: #050805; }
    SurfboardTerminal > .terminal-prompt > Static { width: 2; height: 1; color: #537b52; }
    SurfboardTerminal Input { width: 1fr; height: 1; min-height: 1; padding: 0; background: #050805; border: none; color: #b0edba; }
    SurfboardTerminal Input:focus { border: none; }
    SurfboardTerminal > .terminal-footer { height: 2; border-top: solid #253c24; color: #537b52; text-wrap: nowrap; }
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
        self._transcript = []
        self._footer = {}
        self._elapsed = 0
        self._reply_serial = 0
        self._paint_serial = 0
        self._row_keys = []
        self._pending_scroll = None

    def compose(self):
        # The owner's web-terminal layout explicitly replaces PanelBase's title gap.
        yield Static(Text("network unavailable"), classes="terminal-overview panel-title")
        yield RichLog(id="surfboard-events", wrap=False, min_width=1, max_lines=260, auto_scroll=False, markup=False)
        with Horizontal(classes="terminal-prompt"):
            yield Static(Text("> "))
            yield Input(placeholder="? for commands", id="surfboard-command", max_length=COMMAND_LIMIT)
        yield Static(Text("$IMD unavailable · tokens unavailable · age unknown"), id="surfboard-terminal-footer", classes="terminal-footer")

    @property
    def command_input(self):
        return self.query_one("#surfboard-command", Input)

    def focus_input(self):
        self.command_input.focus()

    def add_reply(self, lines):
        for line in [lines] if isinstance(lines, str) else lines:
            for part in str(line).splitlines() or [""]:
                self._reply_serial += 1
                key = f"reply:{self._reply_serial}"
                self._replies.append((key, flatten(part)))
                self._transcript.append(key)
        self._prune_transcript()
        self._paint()

    def clear_replies(self):
        self._replies.clear()
        self._prune_transcript()
        self._paint()

    def update_data(self, surfboard_overview=None, surfboard_events=None, surfboard_sources=None, surfboard_footer=None, **_kwargs):
        self._overview = surfboard_overview if isinstance(surfboard_overview, dict) else None
        self._sources = surfboard_sources if isinstance(surfboard_sources, dict) else {}
        self._footer = surfboard_footer if isinstance(surfboard_footer, dict) else {}
        self._elapsed = 0
        if isinstance(surfboard_events, list):
            unique = {}
            for row in surfboard_events:
                if isinstance(row, dict) and isinstance(row.get("key"), str):
                    unique["event:" + row["key"]] = row
            ordered = sorted(unique, key=lambda key: (_number(unique[key].get("timestamp")) or 0, key))[-EVENT_LIMIT:]
            previous = self._events or {}
            self._events = {key: unique[key] for key in ordered}
            self._transcript.extend(key for key in ordered if key not in previous)
            self._prune_transcript()
        # A failed read keeps the already displayed historical window and its ordering.
        self._paint()

    def _prune_transcript(self):
        retained = set(self._events or {}) | {key for key, _ in self._replies}
        self._transcript = [key for key in self._transcript if key in retained]

    def update_age(self, elapsed):
        """Repaint only the footer from the screen's elapsed monotonic duration."""
        self._elapsed = _number(elapsed)
        self._paint_footer()

    def on_resize(self):
        self.call_after_refresh(self._paint)

    def _overview_source(self):
        source = self._sources.get("overview")
        return source if isinstance(source, dict) else {}

    def _header(self, width):
        if self._overview is None:
            return Text("network unavailable", style=FAIL), False
        overview = self._overview or {}
        fields = (("agents_online", "online"), ("working_now", "working"),
                  ("jobs_24h", "jobs"), ("oracles_24h", "oracles"), ("accepted_24h", "steps"))
        source = self._overview_source()
        services = overview.get("services")
        services = services if isinstance(services, dict) else {}
        result = Text()
        for compact in (False, True):
            result = Text("stale · " if source.get("state") == "stale" else "", style=DIM)
            for index, (key, label) in enumerate(fields):
                if index:
                    result.append(" | 24h " if index == 2 else " " if compact else " · ", style=DIM)
                value = overview.get(key)
                valid = isinstance(value, int) and _number(value) is not None
                shown = (fmt_compact(value) if compact and value >= 1000 else fmt_int(value)) if valid else "—"
                result.append(shown, style="bold " + LIVE).append(" " + label, style=INK)
            result.append("  ")
            for index, service in enumerate(("verifier", "publisher", "deployer")):
                if index:
                    result.append(" ")
                state = services.get(service)
                result.append(service[0].upper(), style=DIM)
                result.append("*" if state is True else "!" if state is False else "?",
                              style=LIVE if state is True else FAIL if state is False else DIM)
            if result.cell_len <= width:
                return result, compact
        result.truncate(width, overflow="ellipsis")
        return result, True

    def _event_text(self, row, previous_row, width):
        job = row.get("job_id")
        grouped = job is not None and previous_row is not None and job == previous_row.get("job_id")
        token = row.get("token_id")
        has_agent = isinstance(token, int) and not isinstance(token, bool) and token >= 0
        actor = f"agent #{token}" if has_agent else "swarm"
        state = flatten(row.get("state")) or flatten(row.get("step")) or "unknown"
        role = flatten(row.get("role")).casefold()
        step = flatten(row.get("step")).casefold()
        words = STEP_WORDS.get(role) or STEP_WORDS.get(step)
        if state == "accepted" and words:
            state = words[0]
        elif state in ("running", "executing", "leased", "working", "building", "reviewing") and words:
            state = words[1]
        elif state in ("ready", "waiting") and (row.get("kind") == "node" or words is not None):
            state = "called" if has_agent else "queued"
        kind = flatten(row.get("kind")) or "event"
        kind = {"node": "job", "agent": "joined"}.get(kind, kind)
        description = flatten(row.get("objective"))
        if grouped and description == flatten(previous_row.get("objective")):
            description = ""
        failed = state == "failed"
        state_ink = FAIL if failed else LIVE if state in LIVE_STATES else DIM if state in ("queued", "called", "waiting", "ready") else INK
        line = Text("└ " if grouped else "> ", style=FAIL if failed else DIM)
        clipped = False
        for value, cells, style in ((hhmm(row.get("timestamp")), 7, DIM), (kind, 8, INK),
                                     (actor, 13, INK), (state, 13, "bold " + state_ink)):
            clipped |= cell_len(value) > cells
            text = Text(clip(value, cells), style=style)
            text.pad_right(max(0, cells - text.cell_len))
            line.append_text(text)
        detail, lost = fit_prose(description, max(0, width - line.cell_len), style=FAIL if failed else INK)
        line.append_text(detail)
        clipped |= lost or line.cell_len > width
        line.truncate(width, overflow="ellipsis")
        return line, clipped

    def _paint_footer(self):
        if not self.is_mounted:
            return
        footer = self.query_one("#surfboard-terminal-footer", Static)
        width = max(1, footer.content_size.width)
        data = self._footer
        market = _number(data.get("market_value_usd"))
        market_known = market is not None and data.get("market_basis") in ("market_cap", "fdv") and data.get("market_state") in ("ok", "stale")
        prefix = "$IMD " + (_market_money(market) if market_known else "unavailable")
        if market_known and data.get("market_basis") == "fdv":
            prefix += " FDV"
        if data.get("market_state") == "stale":
            prefix += " mkt stale"
        tokens = data.get("inference_tokens")
        token_text = fmt_compact(tokens) if isinstance(tokens, int) and _number(tokens) is not None and data.get("overview_state") in ("ok", "stale") else None
        token_mark = " swarm stale" if data.get("overview_state") == "stale" else ""
        observed, provider = _number(data.get("as_of")), _number(data.get("provider_ts"))
        age_seconds = _number(max(0, observed + self._elapsed - provider)) if observed is not None and provider is not None and self._elapsed is not None else None
        age = fmt_age(age_seconds) if age_seconds is not None else None
        candidates = []
        for compact in (False, True):
            token_part = token_text + (" tokens" if compact else " tokens used") if token_text is not None else "tokens unavailable"
            token_part += token_mark
            age_part = (age + " ago" if compact else age + " ago last updated") if age is not None else "age unknown"
            tail = " | " + token_part + " | " + age_part
            # Goal bars shrink before any factual figure or stale qualifier does.
            room = max(1, min(24, width - cell_len(prefix + " [] $1B goal" + tail)))
            if market_known:
                filled = min(room, max(1 if market > 0 else 0, round(market / 1_000_000_000 * room)))
                bar = "=" * filled + "·" * (room - filled)
            else:
                bar = "—"
            text = prefix + " [" + bar + "] $1B goal" + tail
            candidates.append(text)
            if cell_len(text) <= width:
                break
        text = candidates[-1]
        if cell_len(text) > width:
            text = clip(text, max(0, width - cell_len(WIDEN_HINT) - 1)) + " " + WIDEN_HINT
        rendered = Text(text, style=DIM)
        for value, start in (((_market_money(market) if market_known else None), 0),
                              (token_text, text.find(" | ") + 3), (age, text.rfind(" | ") + 3), ("$1B", 0)):
            if value is not None and (index := text.find(value, start)) >= 0:
                rendered.stylize("bold " + INK, index, index + len(value))
        footer.update(rendered)

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
        replies = dict(self._replies)
        for key in self._transcript:
            if key in (self._events or {}):
                row = self._events[key]
                line, lost = self._event_text(row, previous, width)
                previous = row
            else:
                line, lost = fit_prose(replies[key], width, style=INK)
                previous = None
            clipped |= lost
            rows.append((key, line))
        keys = [key for key, _ in rows]
        self._row_keys = keys
        self._paint_serial += 1
        serial = self._paint_serial
        log.clear()
        for _, line in rows:
            log.write(line, scroll_end=False)
        hint_width = cell_len(WIDEN_HINT) + 1
        header, header_clipped = self._header(max(1, width - hint_width) if clipped else width)
        if header_clipped and not clipped:
            header, _ = self._header(max(1, width - hint_width))
        if clipped or header_clipped:
            header.append(" " + WIDEN_HINT, style=DIM)
        self.write(".terminal-overview", header)
        self._paint_footer()

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
