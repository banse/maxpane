"""The full-width raw, cleaned, and filtered tables used by curator list mode."""

from __future__ import annotations

import math

from rich.cells import cell_len, set_cell_size
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    fmt_eth_compact,
    fmt_points,
)
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    tier_cost,
    title_with_hint,
)
from maxpane_dashboard.widgets.curator.cleaned_list import EXPORT_FAILED
from maxpane_dashboard.widgets.markup_safety import safe_markup

RAW_LIST_TITLE = "THE RAW LIST"
CLEANED_LIST_TITLE = "THE CLEANED LIST"
FILTERED_LIST_TITLE = "THE FILTERED LIST"

RAW_LIST_UNAVAILABLE = "raw list unavailable"
RAW_LIST_EMPTY = "no contributors"
CLEANED_LIST_UNAVAILABLE = "analysis unavailable"
CLEANED_LIST_EMPTY = "no wallets survive"
FILTERED_LIST_UNAVAILABLE = "filtered list unavailable"
FILTERED_LIST_EMPTY = "no wallets match"

MAX_ROWS = 1_000

_INDEX_COLS = 6
_RANK_COLS = 6
_JOIN_COLS = 6
_ADDRESS_COLS = 42
_ENS_COLS = 19
_POINTS_COLS = 7
_WEIGHT_COLS = 8
_CREDIT_COLS = 6
_DEPOSITS_COLS = 8
_HOUR_COLS = 4
_WINDOW_COLS = 6

_RAW_FULL = (
    ("index", "INDEX", _INDEX_COLS),
    ("rank", "RANK", _RANK_COLS),
    ("join", "JOIN #", _JOIN_COLS),
    ("address", "ADDRESS", _ADDRESS_COLS),
    ("ens", "ENS", _ENS_COLS),
    ("points", "POINTS", _POINTS_COLS),
    ("weight", "WEIGHT Ξ", _WEIGHT_COLS),
    ("credit", "CREDIT Ξ", _CREDIT_COLS),
    ("deposits", "DEPOSITS", _DEPOSITS_COLS),
    ("hour", "HOUR", _HOUR_COLS),
    ("window", "WINDOW", _WINDOW_COLS),
)
_RAW_COMPACT = tuple(column for column in _RAW_FULL if column[0] != "window")
_RAW_NARROW = tuple(
    column
    for column in _RAW_FULL
    if column[0] not in ("weight", "deposits", "hour", "window")
)
_RAW_MINIMUM = tuple(
    column
    for column in _RAW_FULL
    if column[0] in ("index", "rank", "address", "ens", "points")
)
_RAW_TIERS = (
    ("full", tier_cost(_RAW_FULL), _RAW_FULL, ""),
    ("compact", tier_cost(_RAW_COMPACT), _RAW_COMPACT, "‹ widen: WINDOW"),
    (
        "narrow",
        tier_cost(_RAW_NARROW),
        _RAW_NARROW,
        "‹ widen: WEIGHT + DEPOSITS + HOUR + WINDOW",
    ),
    (
        "minimum",
        tier_cost(_RAW_MINIMUM),
        _RAW_MINIMUM,
        "‹ widen: JOIN + WEIGHT + CREDIT + DEPOSITS + HOUR + WINDOW",
    ),
)

_CLEANED_FULL = (
    ("index", "INDEX", _INDEX_COLS),
    ("rank", "RANK", _RANK_COLS),
    ("join", "JOIN #", _JOIN_COLS),
    ("address", "ADDRESS", _ADDRESS_COLS),
    ("ens", "ENS", _ENS_COLS),
    ("points", "POINTS", _POINTS_COLS),
    ("weight", "WEIGHT Ξ", _WEIGHT_COLS),
    ("credit", "CREDIT Ξ", _CREDIT_COLS),
    ("deposits", "DEPOSITS", _DEPOSITS_COLS),
    ("hour", "HOUR", _HOUR_COLS),
    ("window", "WINDOW", _WINDOW_COLS),
)
_CLEANED_COMPACT = tuple(
    column for column in _CLEANED_FULL if column[0] != "window"
)
_CLEANED_NARROW = tuple(
    column
    for column in _CLEANED_FULL
    if column[0] not in ("weight", "deposits", "hour", "window")
)
_CLEANED_MINIMUM = tuple(
    column
    for column in _CLEANED_FULL
    if column[0] in ("index", "rank", "address", "ens", "points")
)
_CLEANED_TIERS = (
    ("full", tier_cost(_CLEANED_FULL), _CLEANED_FULL, ""),
    (
        "compact",
        tier_cost(_CLEANED_COMPACT),
        _CLEANED_COMPACT,
        "‹ widen: WINDOW",
    ),
    (
        "narrow",
        tier_cost(_CLEANED_NARROW),
        _CLEANED_NARROW,
        "‹ widen: WEIGHT + DEPOSITS + HOUR + WINDOW",
    ),
    (
        "minimum",
        tier_cost(_CLEANED_MINIMUM),
        _CLEANED_MINIMUM,
        "‹ widen: JOIN + WEIGHT + CREDIT + DEPOSITS + HOUR + WINDOW",
    ),
)

_SORT_FIELDS = {
    "join": "first_index",
    "address": "address",
    "ens": "name",
    "points": "points",
    "weight": "weight_eth",
    "credit": "credit_eth",
    "deposits": "tx_count",
    "hour": "first_hour",
    "window": "first_hour",
}
_NUMERIC_SORT_COLUMNS = {
    "index",
    "rank",
    "join",
    "points",
    "weight",
    "credit",
    "deposits",
    "hour",
    "window",
}


class ListOrderChanged(Message):
    def __init__(self, kind: str, addresses: tuple[str, ...]) -> None:
        super().__init__()
        self.kind = kind
        self.addresses = addresses


def _rank(value) -> str:
    if value is None or isinstance(value, bool):
        return DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return DASH


def _address(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return DASH
    return safe_markup(value.strip())


def _ens(name) -> str:
    value = ""
    if isinstance(name, str):
        value = " ".join(name.split())
    if not value:
        return DASH
    if cell_len(value) > _ENS_COLS:
        value = f"{set_cell_size(value, _ENS_COLS - 1)}…"
    return safe_markup(value)


def _window(value) -> str:
    if value is None or isinstance(value, bool):
        return DASH
    try:
        hour = int(value)
    except (TypeError, ValueError):
        return DASH
    if hour < 0:
        return DASH
    return "grace" if hour < 24 else "judged"


def _raw_values(row: dict) -> dict:
    return {
        "rank": _rank(row.get("rank")),
        "join": _rank(row.get("first_index")),
        "address": _address(row.get("address")),
        "ens": _ens(row.get("name")),
        "points": fmt_points(row.get("points")),
        "weight": fmt_eth_compact(row.get("weight_eth")),
        "credit": fmt_eth_compact(row.get("credit_eth")),
        "deposits": _rank(row.get("tx_count")),
        "hour": _rank(row.get("first_hour")),
        "window": _window(row.get("first_hour")),
    }


def _cleaned_values(row: dict) -> dict:
    return {
        "rank": _rank(row.get("clean_rank")),
        "join": _rank(row.get("first_index")),
        "address": _address(row.get("address")),
        "ens": _ens(row.get("name")),
        "points": fmt_points(row.get("points")),
        "weight": fmt_eth_compact(row.get("weight_eth")),
        "credit": fmt_eth_compact(row.get("credit_eth")),
        "deposits": _rank(row.get("tx_count")),
        "hour": _rank(row.get("first_hour")),
        "window": _window(row.get("first_hour")),
    }


class _ListTable(Vertical):
    """Shared table mechanics; subclasses define only their frozen row shape."""

    TITLE = ""
    TABLE_ID = ""
    TIERS: tuple = ()
    UNAVAILABLE = ""
    EMPTY = ""
    RANK_FIELD = "rank"
    KIND = ""

    DEFAULT_CSS = """
    _ListTable {
        width: 100%;
        height: 100%;
    }
    .curator-list-title {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    .curator-list-note {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    .curator-list-table {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    .curator-list-you {
        height: 1;
        min-height: 1;
        color: $accent;
        text-style: bold;
        scrollbar-size: 0 0;
    }
    .curator-list-blank {
        width: 100%;
        height: 1;
    }
    .curator-list-receipt {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()
        self._hint = ""
        self._export_path: str | None = None
        self._export_failed = False
        self._complete_rows: list[dict] | None = None
        self._complete_expected_count: object = None
        self._live_wallet_count: object = None
        self._rows_by_address: dict[str, dict] = {}
        self._source_order: dict[str, int] = {}
        self._ordered_addresses: tuple[str, ...] = ()
        self._visible_indexes: dict[str, int] = {}
        self._sort_column: str | None = None
        self._sort_reverse = False
        self._heading_note = ""

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="curator-list-title")
        yield Static("", classes="curator-list-note")
        receipt = Static("", classes="curator-list-receipt")
        receipt.display = False
        yield receipt
        yield DataTable(id=self.TABLE_ID, classes="curator-list-table")
        you = DataTable(classes="curator-list-you")
        you.show_header = False
        yield you
        yield Static("", classes="curator-list-blank")

    def on_mount(self) -> None:
        table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        you = self.query_one(".curator-list-you", DataTable)
        you.cursor_type = "none"
        columns = self._apply_columns(table)
        table.add_row(*cells({}, columns, default="…"))
        you.add_row(*cells({}, columns))

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()
        self._render_receipt()

    def mark_exported(self, path) -> None:
        self._export_path = str(path) if path else None
        self._export_failed = False
        self._render_receipt()

    def mark_export_failed(self) -> None:
        self._export_path = None
        self._export_failed = True
        self._render_receipt()

    def _render_receipt(self) -> None:
        try:
            line = self.query_one(".curator-list-receipt", Static)
        except Exception:
            return
        if self._export_failed:
            line.display = True
            line.update(f"[$warning]⚠ {EXPORT_FAILED}[/]")
            return
        if not self._export_path:
            line.display = False
            line.update("")
            return
        line.display = True
        prefix = "saved → "
        path = self._export_path
        width = max(self.content_size.width - 2, 0)
        if width and cell_len(prefix + path) > width:
            keep = max(width - cell_len(prefix) - 1, 1)
            path = f"…{path[-keep:]}"
        line.update(f"[dim]{prefix}{safe_markup(path)}[/]")

    def _apply_columns(self, table: DataTable) -> tuple:
        width = table.content_size.width or self.content_size.width
        _name, columns, hint = pick_tier(self.TIERS, width)
        current = self._columns
        install_columns(table, columns, current)
        install_columns(
            self.query_one(".curator-list-you", DataTable), columns, current
        )
        self._columns = columns
        self._hint = hint
        return columns

    def _set_heading(self, note: str) -> None:
        self._heading_note = note
        width = max(self.content_size.width - 2, 0)
        count = self._payload.get("wallet_count")
        heading = (
            f"{self.TITLE} - {count:,} wallets"
            if isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
            else self.TITLE
        )
        title, placed = title_with_hint(heading, self._hint, width)
        self.query_one(".curator-list-title", Static).update(title)
        if self._sort_column is not None:
            direction = "↓" if self._sort_reverse else "↑"
            sort_note = f"[dim]sorted {self._sort_label()} {direction}[/]"
            note = f"{note} · {sort_note}" if note else sort_note
        if self._hint and not placed:
            marker = f"[yellow]{WIDEN_HINT}[/]"
            note = f"{marker} {note}" if note else marker
        self.query_one(".curator-list-note", Static).update(note)

    def _sort_label(self) -> str:
        for _name, _cost, columns, _hint in self.TIERS:
            for key, header, _width in columns:
                if key == self._sort_column:
                    return header
        return str(self._sort_column).upper()

    @staticmethod
    def _address_key(value) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip().casefold()

    def _source_row(self, values) -> dict | None:
        try:
            address_index = next(
                index for index, column in enumerate(self._columns)
                if column[0] == "address"
            )
            address = values[address_index]
        except (IndexError, StopIteration, TypeError):
            return None
        return self._rows_by_address.get(self._address_key(address))

    def _sort_value(self, row: dict | None) -> tuple[bool, object]:
        column = self._sort_column
        if column == "index":
            address = self._address_key(row.get("address")) if isinstance(row, dict) else None
            value = self._source_order.get(address) if address is not None else None
            return value is None, value if value is not None else 0

        field = self.RANK_FIELD if column == "rank" else _SORT_FIELDS.get(column)
        value = row.get(field) if isinstance(row, dict) and field else None
        if column in _NUMERIC_SORT_COLUMNS:
            if isinstance(value, bool):
                return True, 0.0
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                return True, 0.0
            if not math.isfinite(number):
                return True, 0.0
            return False, number

        if isinstance(value, str) and value.strip():
            return False, " ".join(value.split()).casefold()
        return True, ""

    def _apply_sort(self, table: DataTable) -> None:
        if self._sort_column is None or not self._rows_by_address:
            return

        def sort_key(values):
            missing, value = self._sort_value(self._source_row(values))
            missing_order = not missing if self._sort_reverse else missing
            return missing_order, value

        table.sort(key=sort_key, reverse=self._sort_reverse)

    def _renumber_and_publish(self, table: DataTable) -> None:
        index_column = next(
            i for i, column in enumerate(self._columns) if column[0] == "index"
        )
        addresses: list[str] = []
        visible: dict[str, int] = {}
        for row_index in range(table.row_count):
            values = table.get_row_at(row_index)
            table.update_cell_at(
                Coordinate(row_index, index_column), _rank(row_index + 1)
            )
            source = self._source_row(values)
            address = (
                self._address_key(source.get("address"))
                if isinstance(source, dict)
                else None
            )
            if address is not None:
                addresses.append(address)
                visible[address] = row_index + 1
        self._ordered_addresses = tuple(addresses)
        self._visible_indexes = visible
        self._render_you(self._columns, clear=True)
        self.post_message(ListOrderChanged(self.KIND, self._ordered_addresses))

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != self.TABLE_ID:
            return
        try:
            column = self._columns[event.column_index][0]
        except IndexError:
            return
        if column == self._sort_column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._apply_sort(event.data_table)
        self._renumber_and_publish(event.data_table)
        self._set_heading(self._heading_note)

    def _rows(self):
        raise NotImplementedError

    def _row_values(self, row: dict) -> dict:
        raise NotImplementedError

    def _healthy_note(self) -> str:
        return ""

    def set_list_source(self, rows, *, complete: bool) -> None:
        """Swap between the live slice and a validated complete export."""
        selected_complete = complete and isinstance(rows, list)
        self._complete_rows = rows if selected_complete else None
        self._complete_expected_count = (
            self._live_wallet_count if selected_complete else None
        )
        if not self._payload:
            return
        self._payload["rows"] = rows
        self._payload["complete"] = selected_complete
        self._payload["wallet_count"] = (
            len(rows) if selected_complete else self._live_wallet_count
        )
        self._render_view()

    def _select_rows(self, live_rows, wallet_count) -> tuple[object, bool, bool]:
        """Keep a complete source only while its authoritative count agrees."""
        complete = self._complete_rows
        if complete is None:
            return live_rows, False, False
        if (
            isinstance(wallet_count, int)
            and not isinstance(wallet_count, bool)
            and wallet_count == self._complete_expected_count
        ):
            unchanged = self._payload.get("rows") is complete
            return complete, True, unchanged
        self._complete_rows = None
        self._complete_expected_count = None
        return live_rows, False, False

    def _render_you(self, columns: tuple, *, clear: bool = False) -> None:
        table = self.query_one(".curator-list-you", DataTable)
        if clear:
            table.clear()
        you = self._payload.get("you_list_row")
        if isinstance(you, dict):
            try:
                values = self._row_values(you)
            except Exception:
                values = {}
            address = self._address_key(you.get("address"))
            values["index"] = _rank(self._visible_indexes.get(address))
            table.add_row(*cells(values, columns, default=DASH))
        else:
            table.add_row(*cells({}, columns))

    def _refresh_complete_metadata(self) -> None:
        """Refresh heading and footer without rebuilding complete rows."""
        if not self._columns:
            self._render_view()
            return
        self._render_you(self._columns, clear=True)
        rows = self._payload.get("rows")
        if rows:
            self._set_heading(self._healthy_note())
            return
        note = f"[dim]{self.EMPTY}[/]"
        freshness = self._healthy_note()
        if freshness:
            note = f"{note} · {freshness}"
        self._set_heading(note)

    def _render_view(self) -> None:
        try:
            table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        except Exception:
            return
        if not self._payload:
            return

        self._rows_by_address = {}
        self._source_order = {}
        self._ordered_addresses = ()
        self._visible_indexes = {}
        columns = self._apply_columns(table)
        rows = self._rows()
        if rows is None:
            self._set_heading(f"[$warning]⚠ {self.UNAVAILABLE}[/]")
            self._renumber_and_publish(table)
            table.add_row(*cells({}, columns, default=DASH))
            return
        try:
            raw = list(rows)
        except TypeError:
            raw = None
        usable = (
            [row for row in raw if isinstance(row, dict)]
            if raw is not None
            else []
        )
        if raw is None or (raw and not usable):
            self._set_heading(f"[$warning]⚠ {self.UNAVAILABLE}[/]")
            self._renumber_and_publish(table)
            table.add_row(*cells({}, columns, default=DASH))
            return
        if not usable:
            note = f"[dim]{self.EMPTY}[/]"
            freshness = self._healthy_note()
            if freshness:
                note = f"{note} · {freshness}"
            self._set_heading(note)
            self._renumber_and_publish(table)
            return

        self._set_heading(self._healthy_note())
        shown = usable if self._payload.get("complete") else usable[:MAX_ROWS]
        for index, row in enumerate(shown, start=1):
            address = self._address_key(row.get("address"))
            if address is not None:
                self._rows_by_address[address] = row
                self._source_order[address] = index
            try:
                values = self._row_values(row)
            except Exception:
                values = {}
            values["index"] = _rank(index)
            table.add_row(*cells(values, columns, default=DASH))
        self._apply_sort(table)
        self._renumber_and_publish(table)


class CuratorRawList(_ListTable):
    """The raw leaderboard payload, without the dashboard's ten-row cap."""

    TITLE = RAW_LIST_TITLE
    TABLE_ID = "curator-raw-list-table"
    TIERS = _RAW_TIERS
    UNAVAILABLE = RAW_LIST_UNAVAILABLE
    EMPTY = RAW_LIST_EMPTY
    KIND = "raw"

    def update_data(
        self, leaderboard_rows=None, you_list_row=None,
        contributors_total=None, **_kwargs
    ) -> None:
        self._live_wallet_count = contributors_total
        rows, complete, unchanged = self._select_rows(
            leaderboard_rows, contributors_total
        )
        self._payload = {
            "rows": rows,
            "you_list_row": you_list_row,
            "wallet_count": len(rows) if complete else contributors_total,
            "complete": complete,
            "seen": True,
        }
        if unchanged:
            self._refresh_complete_metadata()
        else:
            self._render_view()

    def _rows(self):
        return self._payload["rows"]

    def _row_values(self, row: dict) -> dict:
        return _raw_values(row)


class CuratorCleanedList(_ListTable):
    """The cleaned-list payload, without the analysis view's eight-row cap."""

    TITLE = CLEANED_LIST_TITLE
    TABLE_ID = "curator-cleaned-list-table"
    TIERS = _CLEANED_TIERS
    UNAVAILABLE = CLEANED_LIST_UNAVAILABLE
    EMPTY = CLEANED_LIST_EMPTY
    RANK_FIELD = "clean_rank"
    KIND = "cleaned"

    def update_data(
        self, clean_list_rows=None, you_list_row=None,
        clean_contributors=None, analysis_as_of_hhmm=None, **_kwargs
    ) -> None:
        self._live_wallet_count = clean_contributors
        rows, complete, unchanged = self._select_rows(
            clean_list_rows, clean_contributors
        )
        self._payload = {
            "rows": rows,
            "you_list_row": you_list_row,
            "wallet_count": len(rows) if complete else clean_contributors,
            "analysis_as_of_hhmm": analysis_as_of_hhmm,
            "complete": complete,
            "seen": True,
        }
        if unchanged:
            self._refresh_complete_metadata()
        else:
            self._render_view()

    def _rows(self):
        return self._payload["rows"]

    def _row_values(self, row: dict) -> dict:
        return _cleaned_values(row)

    def _healthy_note(self) -> str:
        stamp = self._payload.get("analysis_as_of_hhmm")
        if not isinstance(stamp, str) or not stamp.strip():
            return ""
        return f"[dim]as of {safe_markup(stamp.strip())}[/]"


class CuratorFilteredList(_ListTable):
    TITLE = FILTERED_LIST_TITLE
    TABLE_ID = "curator-filtered-list-table"
    TIERS = _RAW_TIERS
    UNAVAILABLE = FILTERED_LIST_UNAVAILABLE
    EMPTY = FILTERED_LIST_EMPTY
    KIND = "filtered"

    def update_data(
        self, filtered_rows=None, you_list_row=None,
        filtered_complete=None, **_kwargs
    ) -> None:
        self._payload = {
            "rows": filtered_rows,
            "you_list_row": you_list_row,
            "wallet_count": (
                len(filtered_rows) if isinstance(filtered_rows, list) else None
            ),
            "complete": bool(filtered_complete),
            "seen": True,
        }
        self._render_view()

    def _rows(self):
        return self._payload["rows"]

    def _row_values(self, row: dict) -> dict:
        return _raw_values(row)

    def export_rows(self) -> list[dict]:
        rows = []
        for index, address in enumerate(self._ordered_addresses, start=1):
            source = self._rows_by_address[address]
            rows.append({**source, "index": index})
        return rows
