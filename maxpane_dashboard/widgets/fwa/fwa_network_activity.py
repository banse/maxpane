"""Bounded, escaped activity feed spanning the FWA ecosystem."""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.cell_fitting import fit_cell, pad_cell
from maxpane_dashboard.widgets.table_tiers import WIDEN_HINT, title_with_hint

_MAX_EVENTS = 40
_NA = "n/a"

UNAVAILABLE_LINE = "network activity unavailable"
QUIET_LINE = "no network activity in indexed window"
LAST_GOOD_LINE = "showing labelled last-good activity"


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _as_of(value) -> str:
    number = _number(value)
    return _NA if number is None else f"t{int(number):,}"


def _age_label(timestamp, reference) -> str:
    ts = _number(timestamp)
    now = _number(reference)
    if ts is None or now is None:
        return "?"
    seconds = max(int(now - ts), 0)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3_600:
        return f"{seconds // 60}m"
    if seconds < 86_400:
        return f"{seconds // 3_600}h"
    return f"{seconds // 86_400}d"


def _amounts(event: dict) -> str:
    parts: list[str] = []
    eth = _number(event.get("eth_amount"))
    fwa = _number(event.get("fwa_amount"))
    if eth is not None:
        value = f"{eth:.3e}" if abs(eth) >= 1_000_000_000_000 else f"{eth:,.4f}"
        parts.append(f"{value} ETH")
    if fwa is not None:
        value = f"{fwa:.3e}" if abs(fwa) >= 1_000_000_000_000 else f"{fwa:,.2f}"
        parts.append(f"{value} FWA")
    return " · ".join(parts) or _NA


def _source(event: dict, width: int) -> str:
    values = [
        str(event.get("origin") or "").strip(),
        str(event.get("family") or "").strip(),
        str(event.get("version") or "").strip(),
    ]
    parts: list[str] = []
    for value in values:
        if value and value.lower() not in {part.lower() for part in parts}:
            parts.append(value)
    source = "/".join(parts) or _NA
    if len(parts) >= 3 and cell_len(source) > width:
        source = "/".join(parts[-2:])
    version = parts[-1] if len(parts) >= 2 else ""
    if version and cell_len(source) > width:
        family_width = max(width - cell_len(version) - 1, 0)
        family = fit_cell(parts[-2], family_width)[0]
        source = f"{family}/{version}" if family else version
    return fit_cell(source, width)[0]


def _event_identity(event: dict) -> str:
    event_id = str(event.get("event_id") or "").strip()
    if event_id:
        return event_id
    return (
        f"{event.get('tx_hash')!s}:"
        f"{event.get('log_index')!s}:"
        f"{event.get('event_key')!s}"
    )


def _dedupe(events) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        identity = _event_identity(event)
        if identity in seen:
            continue
        seen.add(identity)
        out.append(event)
        if len(out) >= _MAX_EVENTS:
            break
    return out


def _short_hash(value) -> str:
    tx_hash = str(value or "").strip()
    if not tx_hash:
        return _NA
    return tx_hash if len(tx_hash) <= 12 else f"{tx_hash[:6]}..{tx_hash[-4:]}"


def _event_line(event: dict, reference, width: int) -> tuple[str, bool]:
    """Format and fit one event; optional fields are shed as whole fields."""
    if width <= 0 or width >= 88:
        tier = "full"
        source_width = 18
        label_width = 24
    elif width >= 58:
        tier = "compact"
        source_width = 16
        label_width = 20
    else:
        tier = "minimal"
        source_width = 13
        label_width = 17

    age = pad_cell(_age_label(event.get("ts"), reference), 4)
    source = pad_cell(_source(event, source_width), source_width)
    label_raw = str(event.get("event_label") or event.get("event_key") or _NA)
    label = pad_cell(fit_cell(label_raw, label_width)[0], label_width)
    amount = _amounts(event)

    line = f"{age}  {source}  {label}  {amount}"
    shed = tier != "full"
    if tier == "full":
        detail = str(event.get("detail") or "").strip()
        tx = _short_hash(event.get("tx_hash"))
        if detail:
            line += f"  · {detail}"
        line += f"  {tx}"

    fitted, clipped = fit_cell(line, width if width > 0 else 160)
    return fitted, shed or clipped


class FWANetworkActivity(Vertical):
    """Recent normalized activity with explicit quiet and degraded states."""

    DEFAULT_CSS = """
    FWANetworkActivity {
        min-height: 11;
        border: solid $panel;
        background: $surface;
    }
    FWANetworkActivity > .fwa-network-feed-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWANetworkActivity > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_events: list[dict] = []
        self._last_good_as_of = None
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(
            "NETWORK ACTIVITY",
            id="fwa-network-feed-title",
            classes="fwa-network-feed-title",
        )
        yield RichLog(
            id="fwa-network-activity-log",
            wrap=False,
            highlight=False,
            markup=False,
            max_lines=_MAX_EVENTS + 4,
        )

    def update_data(
        self,
        *,
        network_events=None,
        network_feed_available=None,
        network_feed_unavailable_reason=None,
        network_feed_as_of_ts=None,
    ) -> None:
        try:
            supplied = _dedupe(list(network_events or []))
        except TypeError:
            supplied = []
        available = bool(supplied) if network_feed_available is None else bool(
            network_feed_available
        )

        if available:
            # An available empty window is genuinely quiet and replaces old data.
            self._last_events = supplied
            self._last_good_as_of = network_feed_as_of_ts
        elif supplied:
            # Cache-backed last-good rows must work on a fresh widget instance.
            self._last_events = supplied
            if network_feed_as_of_ts is not None:
                self._last_good_as_of = network_feed_as_of_ts

        self._payload = {
            "available": available,
            "reason": network_feed_unavailable_reason,
            "as_of": network_feed_as_of_ts,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _render_view(self) -> None:
        try:
            log = self.query_one("#fwa-network-activity-log", RichLog)
            title = self.query_one("#fwa-network-feed-title", Static)
        except Exception:
            return
        width = log.content_size.width
        if width <= 0:
            width = max(self.content_size.width - 2, 0)
        reference = self._payload.get("as_of")
        if reference is None:
            reference = self._last_good_as_of
        lines = [_event_line(event, reference, width) for event in self._last_events]
        shed = any(was_shed for _line, was_shed in lines)
        title_text, placed = title_with_hint(
            "NETWORK ACTIVITY", "‹ widen: detail + tx" if shed else "", width
        )
        title.update(title_text)

        log.clear()
        log.auto_scroll = False
        if shed and not placed:
            log.write(Text(WIDEN_HINT))

        if self._payload.get("available"):
            if not lines:
                log.write(Text(fit_cell(QUIET_LINE, width or 120)[0]))
                return
        else:
            reason = str(self._payload.get("reason") or "").strip()
            log.write(Text(fit_cell(UNAVAILABLE_LINE, width or 120)[0]))
            if reason:
                log.write(Text(fit_cell(f"reason: {reason}", width or 120)[0]))
            if not lines:
                log.write(Text("no last-good activity"))
                return
            stamp = _as_of(reference)
            log.write(Text(fit_cell(f"{LAST_GOOD_LINE} · as of {stamp}", width or 120)[0]))

        for line, _was_shed in lines:
            log.write(Text(line))
        self.call_after_refresh(log.scroll_home, animate=False)
