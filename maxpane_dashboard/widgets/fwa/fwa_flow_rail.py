"""Chain-backed ETH -> buyback -> FWA value-flow rail.

Rows arrive pre-normalized and ordered.  This widget only formats them, keeps
configured basis points beside observed values, and carries direction and
integrity in text so colour is never required to understand the flow.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.cell_fitting import fit_cell, pad_cell
from maxpane_dashboard.widgets.table_tiers import WIDEN_HINT, title_with_hint

_NA = "n/a"
_MAX_ROWS = 32

_DIRECTION = {
    "in": "IN  >",
    "out": "OUT <",
    "branch": "BR +>",
    "state": "ST  =",
}


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


def _integer(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _value_text(value, unit) -> str:
    number = _number(value)
    if number is None:
        return _NA
    kind = str(unit or "none").lower()
    if kind == "eth":
        return f"{number:,.4f} ETH"
    if kind == "fwa":
        return f"{number:,.2f} FWA"
    if kind == "bps":
        return f"{number / 100:.2f}%"
    if kind == "seconds":
        return f"{number:,.0f}s"
    if kind == "blocks":
        return f"{number:,.0f} blocks"
    if kind == "count":
        return f"{number:,.0f}"
    return f"{number:,.2f}"


def _configured_text(value) -> str:
    bps = _integer(value)
    return "" if bps is None else f"cfg {bps / 100:.2f}%"


def _as_of(value) -> str:
    number = _number(value)
    return _NA if number is None else f"t{int(number):,}"


def _row_line(row: dict, width: int) -> tuple[str, bool]:
    """Format one row, shedding whole optional fields before fitting."""
    direction = _DIRECTION.get(str(row.get("direction") or "").lower(), "?   ")
    label_raw = str(row.get("label") or row.get("key") or _NA).strip() or _NA
    label = fit_cell(label_raw, 23 if width <= 0 or width >= 72 else 17)[0]
    observed = f"obs {_value_text(row.get('value'), row.get('unit'))}"
    configured = _configured_text(row.get("configured_bps"))
    state = str(row.get("state") or "").strip()
    detail = str(row.get("detail") or "").strip()

    integrity = str(row.get("integrity") or "unknown").strip().lower()
    flags: list[str] = []
    if integrity not in ("ok", "unknown", ""):
        flags.append(f"! {integrity}")
    if row.get("verified_source") is False:
        flags.append("unverified")
    if row.get("stale") is True:
        flags.append("stale")

    line = f"{direction} {pad_cell(label, 23)}  {observed}"
    shed = False
    if configured:
        line += f"  {configured}"
    if width <= 0 or width >= 58:
        if state:
            line += f"  [{state}]"
        if flags:
            line += f"  {' · '.join(flags)}"
    elif state or flags:
        shed = True
    if width <= 0 or width >= 84:
        if detail:
            line += f"  · {detail}"
    elif detail:
        shed = True

    fitted, clipped = fit_cell(line, width if width > 0 else 160)
    return fitted, shed or clipped


class FWAFlowRail(Vertical):
    """Ordered, non-wrapping display of the protocol's value routes."""

    DEFAULT_CSS = """
    FWAFlowRail {
        min-height: 14;
        border: solid $panel;
        background: $surface;
    }
    FWAFlowRail > .fwa-flow-title,
    FWAFlowRail > .fwa-flow-note {
        width: 100%;
        padding: 0 1;
    }
    FWAFlowRail > .fwa-flow-title {
        text-style: bold;
        color: $text-muted;
    }
    FWAFlowRail > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static("FWA VALUE FLOW", id="fwa-flow-title", classes="fwa-flow-title")
        yield Static(" ", id="fwa-flow-note", classes="fwa-flow-note")
        yield RichLog(
            id="fwa-flow-log",
            wrap=False,
            highlight=False,
            markup=False,
            max_lines=_MAX_ROWS + 4,
        )

    def update_data(
        self,
        *,
        network_flow_rows=None,
        network_flow_available=None,
        network_flow_history_complete=None,
        network_flow_as_of_block=None,
        network_flow_as_of_ts=None,
        network_flow_stale=None,
    ) -> None:
        try:
            rows = [row for row in list(network_flow_rows or []) if isinstance(row, dict)]
        except TypeError:
            rows = []
        available = bool(rows) if network_flow_available is None else bool(
            network_flow_available
        )
        self._payload = {
            "rows": rows[:_MAX_ROWS],
            "available": available,
            "history": network_flow_history_complete,
            "block": network_flow_as_of_block,
            "as_of": network_flow_as_of_ts,
            "stale": network_flow_stale,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _render_view(self) -> None:
        try:
            log = self.query_one("#fwa-flow-log", RichLog)
            title = self.query_one("#fwa-flow-title", Static)
            note = self.query_one("#fwa-flow-note", Static)
        except Exception:
            return

        width = log.content_size.width
        if width <= 0:
            width = max(self.content_size.width - 2, 0)
        rows = self._payload.get("rows") or []
        lines = [_row_line(row, width) for row in rows]
        shed = any(was_shed for _line, was_shed in lines)

        title_text, placed = title_with_hint(
            "FWA VALUE FLOW", "‹ widen: state + detail" if shed else "", max(width, 0)
        )
        title.update(title_text)

        block = _integer(self._payload.get("block"))
        block_text = _NA if block is None else f"#{block:,}"
        history = self._payload.get("history")
        history_text = (
            "history complete"
            if history is True
            else "history partial"
            if history is False
            else "history n/a"
        )
        status: list[str] = [history_text, f"as of {block_text} / {_as_of(self._payload.get('as_of'))}"]
        if self._payload.get("stale") is True:
            status.insert(0, "STALE")
        integrity_count = sum(
            1
            for row in rows
            if str(row.get("integrity") or "unknown").lower()
            not in ("ok", "unknown", "")
        )
        if integrity_count:
            status.append(f"INTEGRITY {integrity_count}")
        note_text = " · ".join(status)
        note.update(Text(fit_cell(note_text, width if width > 0 else 160)[0]))

        log.clear()
        log.auto_scroll = False
        if shed and not placed:
            log.write(Text(WIDEN_HINT))
        if not self._payload.get("available"):
            log.write(Text("! value flow unavailable"))
            if not rows:
                log.write(Text("  no last-good flow snapshot"))
                return
            log.write(Text("  showing labelled last-good rows"))
        elif not rows:
            log.write(Text("no value-flow rows in snapshot"))
            return

        log.write(Text(fit_cell("ETH  >  BUYBACK  >  FWA", width or 160)[0]))
        for line, _was_shed in lines:
            log.write(Text(line))
        self.call_after_refresh(log.scroll_home, animate=False)
