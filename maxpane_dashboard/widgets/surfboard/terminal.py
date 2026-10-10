"""Bounded live IMD events and an input; no I/O or clock in this widget."""
from collections import deque
import math
import re
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
from maxpane_dashboard.widgets.explorer import for_chain_id

COMMAND_LIMIT = 512
REPLY_LIMIT = 200
EVENT_LIMIT = 60
#: Untagged prose stays copy-only; event metadata can supply its own chain explorer.
EXPLORER = None
DIM = "#b1b1b1"
LIVE = "green"
FAIL = "red"
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
    "asked", "answered", "signed", "passed", "onchain", "hosted", "awake",
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


def _event_title(value):
    """The website's short objective caption, kept literal for Rich rendering."""
    text = flatten(value).strip()
    text = re.sub(r"^Answer this question about chain \d+ over blocks \d+ to \d+, exactly as \S+ pins it:\s*", "", text, flags=re.I)
    text = re.sub(r"\s*Write only artifacts/answer\.json.*$", "", text, flags=re.I)
    text = re.split(r"[.?!](?:\s|$)", text, maxsplit=1)[0]
    text = re.sub(r",? as of the pinned window", "", text, flags=re.I)
    text = re.sub(r"^what (?:is|was|are|were) (?:the )?", "", text, flags=re.I).strip()
    return text[:1].upper() + text[1:]


def _joined(*parts):
    return " · ".join(part for part in parts if part)


def _job_of(row):
    return row.get("job_id") if row and row.get("kind") not in ("launch", "agent") else None


def fit_prose(value, width, *, style="", explorer=EXPLORER) -> tuple[Text, bool]:
    """Fit literal served text, preserving address/icon units and safe links."""
    marked, addresses, spans = mark_addresses(flatten(value), width=17)
    fitted = keep_units(marked, spans, clip(marked, max(0, width)))
    out = Text(unmark(fitted or ("…" if marked and width else "")), style=style)
    link_in_order([out], addresses, explorer=explorer)
    return out, cell_len(marked) > width


def fitted_prose(value, width, *, style="") -> Text:
    return fit_prose(value, width, style=style)[0]


class SurfboardTerminal(PanelBase):
    TITLE = "IMD TERMINAL"
    DEFAULT_CSS = """
    SurfboardTerminal { height: 1fr; min-height: 11; border: round #345533; background: #050805; color: $foreground; padding: 0 1; }
    SurfboardTerminal > .panel-title { height: 2; margin: 0; padding: 0; border-bottom: solid #253c24; color: $foreground; text-style: none; text-wrap: nowrap; }
    SurfboardTerminal > RichLog { height: 1fr; min-height: 3; background: #050805; scrollbar-size-vertical: 1; scrollbar-gutter: stable; scrollbar-color: #345533; }
    SurfboardTerminal > .terminal-prompt { height: 3; border: round #345533; background: #101710; }
    SurfboardTerminal > .terminal-prompt:focus-within { border: round #9fc99c; }
    SurfboardTerminal > .terminal-prompt > Static { width: 2; height: 1; color: $text-muted; }
    SurfboardTerminal Input { width: 1fr; height: 1; min-height: 1; padding: 0; background: #101710; border: none; color: $foreground; }
    SurfboardTerminal Input:focus { border: none; }
    SurfboardTerminal > .terminal-footer { height: 2; border-top: solid #253c24; color: $text-muted; text-wrap: nowrap; }
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
                    details = row.get("details")
                    if row.get("kind") == "review" and isinstance(details, dict) and type(details.get("scores")) is int and details["scores"] == 0:
                        continue
                    unique["event:" + row["key"]] = row
            ordered = sorted(unique, key=lambda key: _number(unique[key].get("timestamp")) or 0)[-EVENT_LIMIT:]
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
                result.append(shown, style="bold " + LIVE).append(" " + label, style=self.rich_style.color.name)
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

    def _event_fields(self, row, grouped):
        details = row.get("details")
        details = details if isinstance(details, dict) else {}
        raw_kind = row.get("kind")
        token = row.get("token_id")
        has_agent = isinstance(token, int) and not isinstance(token, bool) and token >= 0
        actor = f"agent #{token}" if has_agent else "swarm"
        state = flatten(row.get("state")) or flatten(row.get("step")) or "unknown"
        role = flatten(row.get("role")).casefold()
        step = flatten(row.get("step")).casefold()
        objective = flatten(row.get("objective"))
        if raw_kind == "job" and row.get("job_id"):
            objective = max([objective] + [flatten(e.get("objective")) for e in (self._events or {}).values()
                                           if e.get("job_id") == row["job_id"]], key=len)
        oracle = step == "oracle_assess" or re.match(r"^answer this question about chain \d+ over blocks", objective, re.I)
        kind = "joined" if raw_kind == "agent" else "oracle" if oracle else "job"
        title = _event_title(objective)
        description = "" if grouped else title
        words = STEP_WORDS.get(role) or STEP_WORDS.get(step)
        if raw_kind == "job":
            actor, state, description = "swarm", "asked" if oracle else "posted", title
        elif raw_kind == "done":
            actor, description = "swarm", title
            if state == "completed":
                state = "signed" if oracle else "completed"
                steps = details.get("steps")
                if not oracle and steps is not None:
                    description = _joined(title, f"{steps} step" + ("" if steps == 1 else "s"))
            elif state in ("failed", "blocked"):
                state = "stopped"
                description = _joined(title, flatten(details.get("failure")))
        elif raw_kind == "node":
            reason = flatten(details.get("reason"))
            if state == "accepted":
                state = "answered" if oracle else words[0] if words else "passed"
            elif state == "failed":
                if "cancel" in reason.casefold():
                    actor, state = "swarm", "cancelled"
                    description = _joined(description, step)
                else:
                    description = _joined(description, step, reason)
            elif state in ("ready", "waiting"):
                state, description = ("called" if has_agent else "queued"), _joined(title, step)
            elif state in ("running", "assigned", "executing", "leased", "working", "building", "reviewing"):
                state = "working" if oracle else words[1] if words else "working"
        elif raw_kind == "review":
            actor, state = "verifier", "onchain"
            scores, accepted = details.get("scores"), details.get("accepted")
            counts = "scores unavailable" if scores is None else f"{scores} score" + ("" if scores == 1 else "s")
            if scores is not None and accepted is not None:
                counts += ", all accepted" if accepted == scores else ", all rejected" if accepted == 0 else f", {accepted} accepted"
            description = _joined(description, counts)
        elif raw_kind == "site":
            actor = "publisher"
            ens, cid = flatten(details.get("ens_name")), flatten(details.get("cid"))
            state = "hosted" if ens else "published"
            description = _joined(description, ens or (cid[:16] + "…" if cid else "site unavailable"))
        elif raw_kind == "launch":
            actor, state = "deployer", "deployed"
            launch = details.get("launch_number")
            name = flatten(details.get("token")) or ("launch unavailable" if launch is None else f"launch {launch}")
            chain = details.get("chain_id")
            chain_name = {1: "Ethereum", 8453: "Base", 11155111: "Sepolia"}.get(chain)
            description = _joined(name, chain_name or ("chain unavailable" if chain is None else f"chain {chain}"))
        elif raw_kind == "agent":
            accepted, failed = details.get("seat_accepted"), details.get("seat_failed")
            last = _number(details.get("last_work"))
            worked = last is not None or (accepted or 0) + (failed or 0) > 0
            seen_work = False
            for event in (self._events or {}).values():
                if event.get("key") == row.get("key"):
                    break
                if event.get("kind") == "node" and event.get("token_id") == token:
                    seen_work = True
            history_known = accepted is not None and failed is not None
            shift = ""
            if worked or seen_work:
                state = "awake"
                now = _number(self._footer.get("as_of"))
                if last is not None and now is not None and now >= last:
                    age = now - last
                    shift = f"last worked {fmt_age(age)} ago" if age < 3600 else f"back after {fmt_age(age)}"
            elif history_known:
                state, shift = "ready", "first shift"
            owner = flatten(details.get("owner"))
            seats = details.get("owner_seats")
            if owner and seats is not None and seats > 1:
                owner += f", {seats} seats"
            description = _joined(owner, shift)
        else:
            kind = flatten(raw_kind) or "event"
        return kind, actor, state, description

    def _event_text(self, row, previous_row, width):
        job = _job_of(row)
        grouped = job is not None and job == _job_of(previous_row)
        kind, actor, state, description = self._event_fields(row, grouped)
        failed = state in ("failed", "stopped")
        state_ink = FAIL if failed else LIVE if state in LIVE_STATES else DIM if state in ("queued", "called", "waiting", "ready") else self.rich_style.color.name
        line = Text("└ " if grouped else "> ", style=FAIL if failed else DIM)
        clipped = False
        for value, cells, style in ((hhmm(row.get("timestamp")), 7, DIM), (kind, 8, self.rich_style.color.name),
                                     (actor, 13, self.rich_style.color.name), (state, 13, "bold " + state_ink)):
            clipped |= cell_len(value) > cells
            text = Text(clip(value, cells), style=style)
            text.pad_right(max(0, cells - text.cell_len))
            line.append_text(text)
        metadata = row.get("details")
        explorer = for_chain_id(metadata.get("chain_id")) if isinstance(metadata, dict) else EXPLORER
        detail, lost = fit_prose(description, max(0, width - line.cell_len), style=FAIL if failed else self.rich_style.color.name, explorer=explorer)
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
                rendered.stylize("bold " + self.rich_style.color.name, index, index + len(value))
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
                line, lost = fit_prose(replies[key], width, style=self.rich_style.color.name)
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
