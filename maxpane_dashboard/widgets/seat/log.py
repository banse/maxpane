"""LOG: the daemon's raw lines, control-stripped, redacted, classified -- append-only (spec §8 LOG, §9).

At 3 a.m. the raw log is the truth and this panel saves an ssh + ``journalctl -n``.
It is a ``RichLogFeed`` with one deliberate difference, recorded as a contract
decision: :meth:`render_events` **appends** the rows whose ``seq`` it has not seen
and never ``clear()``s on a poll. The base's stream mode repaints the whole feed
whenever anything is new; a live log that repainted 40 lines every 5 s would
flicker and would scroll the operator away from the line they were reading.
Only a user action (``h`` collapses heartbeats) repaints, from the widget's own
ring of the last :attr:`MAX_LINES` lines.

Rows are styled by the grammar's kind: connection events dim, lifecycle plain,
``paused``/``build mismatch``/``installed; … available``/``task failed``/``re-sending``/
``cancelled`` bold yellow, heartbeats dim and collapsible. The kind words are the
grammar's (``data/seat_log_grammar.py``), restated here because a widget may not
import ``maxpane_dashboard.data`` (spec §14); ``tests/widgets/test_seat_now_log.py``
binds the two sets.

Every line is redacted again on the way to the log (control characters first,
spec §13), even though the fold already did: the widget is the last hand before
the terminal.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import RichLog, Static

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import parse_iso
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.panels import RichLogFeed

__all__ = ["SeatLog"]


class SeatLog(RichLogFeed):
    """Append-only daemon log -- see the module docstring."""

    TITLE = "LOG"
    LOG_ID = "seat-log"
    FOOTER_ID = "seat-log-footer"
    WRAP = False
    HIGHLIGHT = False
    MAX_LINES = 400
    EMPTY_LINE = "[dim]  no lines yet[/]"
    #: The class ``l`` toggles; the screen sizes the row it lives in by it.
    TALL_CLASS = "seat-log-tall"

    #: Grammar words restated (plan deviation 4); bound to ``data/seat_log_grammar`` by a test.
    HEARTBEAT_KIND = "heartbeat"
    CONNECTION_KINDS = frozenset({"connected", "admitted", "server_closed", "reconnecting", "ws_response", "ws_socket"})
    HIGHLIGHT_KINDS = frozenset({"rate_limited", "build_skew", "release_avail", "local_fail", "resending", "cancelled"})
    STYLE_BY_KIND: dict[str, str] = {
        **{kind: "dim" for kind in CONNECTION_KINDS},
        **{kind: "bold yellow" for kind in HIGHLIGHT_KINDS},
        HEARTBEAT_KIND: "dim",
    }


    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ring: list[dict] = []
        self._collapsed = False
        self._tall = False
        self._last_seq = 0

    def compose_body(self) -> ComposeResult:
        yield from super().compose_body()
        yield Static("", id=self.FOOTER_ID, classes="panel-line")

    @property
    def last_seq(self) -> int:
        return self._last_seq

    # -- hooks --------------------------------------------------------------

    def dedupe_key(self, event: dict) -> str | None:
        seq = event.get("seq") if isinstance(event, dict) else None
        return str(seq) if isinstance(seq, int) and not isinstance(seq, bool) else None

    def format_row(self, event: dict) -> Text | None:
        kind = event.get("kind")
        if self._collapsed and kind == self.HEARTBEAT_KIND:
            return None
        text = strip_tags(redact(event.get("text")))
        stamp = event.get("ts") if isinstance(event.get("ts"), str) else ""
        body = text[len(stamp):].lstrip(" ") if stamp and text.startswith(stamp) else text
        epoch = parse_iso(stamp) if stamp else None
        clock = time.strftime("%H:%M:%S", time.localtime(epoch)) if epoch is not None else "--:--:--"
        style = self.STYLE_BY_KIND.get(kind, "") if isinstance(kind, str) else ""
        # ``style=""`` (not ``None``): an unstyled row carries the empty string, which ``str()`` renders as "".
        return Text(f"{clock} {body}", style=style)

    # -- rendering (append-only; contract decision) -------------------------

    def render_events(self, events) -> None:
        try:
            log = self.query_one(f"#{self.LOG_ID}", RichLog)
        except Exception:  # noqa: BLE001 -- not composed yet
            return
        if not events:
            if not self._drawn:
                log.clear()
                log.write(self.EMPTY_LINE)
            return
        fresh: list[dict] = []
        for event in events:
            key = self.dedupe_key(event)
            if key is None or key in self._seen_keys:
                continue
            self._seen_keys.add(key)
            fresh.append(event)
        if not fresh:
            return
        if not self._drawn:
            log.clear()  # the placeholder, once
        written = 0
        for event in fresh:
            try:
                row = self.format_row(event)
                if row is None:
                    continue
                log.write(row)
            except Exception:  # noqa: BLE001 -- one bad row is one missing line
                continue
            written += 1
        if written:
            self._drawn = True
            log.auto_scroll = True
            self.call_after_refresh(log.scroll_end, animate=False)

    # -- the contract -------------------------------------------------------

    def update_data(self, seat_log_lines=None, seat_log_seq=None, seat_log_footer=None, seat_sources=None, **_kwargs) -> None:
        if isinstance(seat_log_lines, list):
            seen = {line.get("seq") for line in self._ring}
            for line in seat_log_lines:
                if isinstance(line, dict) and isinstance(line.get("seq"), int) and line["seq"] not in seen:
                    self._ring.append(line)
                    seen.add(line["seq"])
            del self._ring[:-self.MAX_LINES]
            self.render_events(seat_log_lines)
        # ``None`` = the tail is gated (dead or stale): the log freezes where it is (spec §8 LOG degraded).
        if isinstance(seat_log_seq, int) and not isinstance(seat_log_seq, bool):
            self._last_seq = max(self._last_seq, seat_log_seq)
        tail = seat_sources.get("tail") if isinstance(seat_sources, dict) else None
        tail_ok = tail.get("ok") if isinstance(tail, dict) else None
        footer = strip_tags(redact(seat_log_footer)) if seat_log_footer is not None else ""
        self.write(f"#{self.FOOTER_ID}", Text(footer, style="yellow" if tail_ok is False else "dim"))
        self._write_title()

    def _write_title(self) -> None:
        words = [self.TITLE]
        if self._collapsed:
            words.append("heartbeats hidden")
        self.write(".panel-title", Text(" · ".join(words)))

    # -- key actions ----------------------------------------------------------

    def toggle_heartbeats(self) -> bool:
        """Hide or show heartbeat rows; repaints from the ring (a user action, not a poll)."""
        self._collapsed = not self._collapsed
        try:
            log = self.query_one(f"#{self.LOG_ID}", RichLog)
        except Exception:  # noqa: BLE001
            return self._collapsed
        log.clear()
        self._seen_keys.clear()
        self._drawn = False
        self.render_events(list(self._ring))
        self._write_title()
        return self._collapsed

    def toggle_tall(self) -> bool:
        """Flip the tall class; the screen's stylesheet gives the row its height."""
        self._tall = not self._tall
        self.set_class(self._tall, self.TALL_CLASS)
        return self._tall
