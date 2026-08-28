"""Responsive table of manager-enumerated FWAIR launches."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.cell_fitting import fit_cell
from maxpane_dashboard.widgets.table_tiers import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    tier_cost,
    title_with_hint,
)

_NA = "n/a"

_FULL_COLUMNS = (
    ("launch_id", "ID", 4),
    ("drop", "DROP", 20),
    ("phase", "PHASE", 10),
    ("open", "OPEN", 4),
    ("tokens", "TOKENS", 7),
    ("supported", "SUPPORTED", 9),
    ("supporters", "SUPPORTERS", 9),
    ("launched", "LAUNCHED", 8),
    ("terminal", "TERMINAL", 8),
    ("backing", "BACKING", 9),
    ("total", "TOTAL ETH", 9),
    ("artist", "ARTIST ETH", 9),
    ("principal", "PRINC ETH", 9),
    ("reserve", "RES FWA", 10),
)
_WIDE_COLUMNS = (
    ("launch_id", "ID", 4),
    ("drop", "DROP", 18),
    ("phase", "PHASE", 10),
    ("support", "SUP/TOTAL", 10),
    ("done", "TERM/LAUNCH", 12),
    ("funding", "FUND ETH", 10),
    ("reserve", "RES FWA", 10),
)
_COMPACT_COLUMNS = (
    ("launch_id", "ID", 4),
    ("drop", "DROP", 13),
    ("phase", "PHASE", 10),
    ("funding", "FUND ETH", 10),
    ("done", "TERM/LAUNCH", 10),
)
_TINY_COLUMNS = (
    ("launch_id", "ID", 4),
    ("phase", "PHASE", 10),
    ("funding", "FUND ETH", 9),
    ("done", "TERM/LAUNCH", 10),
)

DROP_TABLE_TIERS = (
    ("full", tier_cost(_FULL_COLUMNS), _FULL_COLUMNS, ""),
    (
        "wide",
        tier_cost(_WIDE_COLUMNS),
        _WIDE_COLUMNS,
        "‹ widen: launch counters",
    ),
    (
        "compact",
        tier_cost(_COMPACT_COLUMNS),
        _COMPACT_COLUMNS,
        "‹ widen: support + reserve",
    ),
    ("tiny", tier_cost(_TINY_COLUMNS), _TINY_COLUMNS, WIDEN_HINT),
)


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


def _fmt_int(value) -> str:
    if value is None or isinstance(value, bool):
        return _NA
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError, OverflowError):
        return _NA


def _fmt_amount(value, places: int = 3) -> str:
    number = _number(value)
    return _NA if number is None else f"{number:,.{places}f}"


def _pair(left, right) -> str:
    return f"{_fmt_int(left)}/{_fmt_int(right)}"


def _text(value, width: int) -> Text:
    return Text(fit_cell(str(value), width)[0])


def _row_values(row: dict, columns: tuple) -> dict[str, Text]:
    widths = {key: width for key, _header, width in columns}
    name = str(row.get("collection_name") or "").strip()
    if not name:
        name = str(row.get("collection_address") or row.get("launch_address") or _NA)
        if len(name) > 14:
            name = f"{name[:6]}..{name[-4:]}"
    phase = str(row.get("phase") or _NA).strip() or _NA
    integrity = str(row.get("integrity") or "unknown").lower()
    if integrity not in ("ok", "unknown", ""):
        phase = f"! {phase}"

    funding = row.get("total_backing_eth")
    if funding is None:
        funding = row.get("backing_eth")
    values = {
        "launch_id": _fmt_int(row.get("launch_id")),
        "drop": name,
        "phase": phase,
        "open": (
            "yes"
            if row.get("support_open") is True
            else "no"
            if row.get("support_open") is False
            else _NA
        ),
        "tokens": _fmt_int(row.get("token_count")),
        "supported": _fmt_int(row.get("supported_count")),
        "supporters": _fmt_int(row.get("supporter_count")),
        "launched": _fmt_int(row.get("launched_count")),
        "terminal": _fmt_int(row.get("terminal_count")),
        "support": _pair(row.get("supported_count"), row.get("token_count")),
        "done": _pair(row.get("terminal_count"), row.get("launched_count")),
        "funding": _fmt_amount(funding),
        "backing": _fmt_amount(row.get("backing_eth")),
        "total": _fmt_amount(row.get("total_backing_eth")),
        "artist": _fmt_amount(row.get("artist_credit_eth")),
        "principal": _fmt_amount(row.get("supporter_principal_eth")),
        "reserve": _fmt_amount(row.get("supporter_reserve_fwa"), 1),
    }
    return {
        key: _text(values.get(key, _NA), widths[key])
        for key, _header, _width in columns
    }


class FWAIRDropBoard(Vertical):
    """FWAIR launches with honest width shedding and explicit freshness."""

    DEFAULT_CSS = """
    FWAIRDropBoard {
        min-height: 11;
        border: solid $panel;
        background: $surface;
    }
    FWAIRDropBoard > .fwair-title,
    FWAIRDropBoard > .fwair-note {
        width: 100%;
        padding: 0 1;
    }
    FWAIRDropBoard > .fwair-title {
        text-style: bold;
        color: $text-muted;
    }
    FWAIRDropBoard > DataTable {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static("FWAIR DROPS", id="fwair-title", classes="fwair-title")
        yield Static(" ", id="fwair-note", classes="fwair-note")
        yield DataTable(id="fwair-drop-table")

    def on_mount(self) -> None:
        table = self.query_one("#fwair-drop-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns, _hint = self._apply_columns(table)
        table.add_row(*cells({"launch_id": Text("Loading...")}, columns, Text("")))

    def update_data(
        self,
        *,
        network_drop_rows=None,
        network_drops_available=None,
        network_drops_as_of_block=None,
        network_drops_stale=None,
    ) -> None:
        try:
            rows = [row for row in list(network_drop_rows or []) if isinstance(row, dict)]
        except TypeError:
            rows = []
        available = bool(rows) if network_drops_available is None else bool(
            network_drops_available
        )
        self._payload = {
            "rows": rows,
            "available": available,
            "block": network_drops_as_of_block,
            "stale": network_drops_stale,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _table_width(self, table: DataTable) -> int:
        return table.content_size.width or self.content_size.width

    def _apply_columns(self, table: DataTable) -> tuple[tuple, str]:
        _name, columns, hint = pick_tier(DROP_TABLE_TIERS, self._table_width(table))
        install_columns(table, columns, self._columns)
        self._columns = columns
        return columns, hint

    def _render_view(self) -> None:
        try:
            table = self.query_one("#fwair-drop-table", DataTable)
            title = self.query_one("#fwair-title", Static)
            note = self.query_one("#fwair-note", Static)
        except Exception:
            return
        columns, hint = self._apply_columns(table)
        width = max(self.content_size.width - 2, 0)
        title_text, placed = title_with_hint("FWAIR DROPS", hint, width)
        title.update(title_text)

        block = _fmt_int(self._payload.get("block"))
        state = "live"
        if not self._payload.get("available"):
            state = "unavailable · last good" if self._payload.get("rows") else "unavailable"
        if self._payload.get("stale") is True:
            state = f"{state} · stale"
        note.update(Text(fit_cell(f"{state} · as of #{block}", width or 120)[0]))

        if hint and not placed:
            table.add_row(*cells({columns[0][0]: Text(WIDEN_HINT)}, columns, Text("")))
        rows = self._payload.get("rows") or []
        if not rows:
            message = "no launches" if self._payload.get("available") else "drop data unavailable"
            table.add_row(*cells({columns[0][0]: Text(message)}, columns, Text("")))
            return
        for row in rows:
            table.add_row(*cells(_row_values(row, columns), columns, Text(_NA)))
