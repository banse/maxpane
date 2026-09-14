"""The full-width raw, cleaned, and filtered tables used by curator list mode."""

from __future__ import annotations

import math
import re

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.address import ADDRESS_RE, ICON_COLS, address_text
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
    with_optional_suffix,
)
from maxpane_dashboard.widgets.curator.cleaned_list import EXPORT_FAILED
from maxpane_dashboard.widgets.markup_safety import safe_markup, visible_len

#: The copy icon's own click action, read back off a windowed ADDRESS
#: cell's ``Style(meta=...)`` span rather than off its (possibly
#: ellipsis-broken) visible text -- see ``_ListTable._address_key``'s own
#: docstring for why the visible-text pattern alone is not enough any
#: more. Matches ``widgets.address.copy_action``'s own format exactly.
_COPY_ACTION_RE = re.compile(r"app\.copy_address\('(0x[0-9a-fA-F]{40})'\)")

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

#: **Six, not a proven worst case -- restored 2026-09-14 fix round 2, after
#: round 1 shrank it to five on a false premise.** The comment that shipped
#: with five claimed ``"1,000"`` (five characters) was the widest value
#: this column ever carries because ``_renumber_and_publish`` numbers
#: ``1..MAX_ROWS``. That is false: ``_render_view``'s own ``shown = usable
#: if self._payload.get("complete") else usable[:MAX_ROWS]`` shows every
#: row a **complete** list holds, uncapped by ``MAX_ROWS`` -- and complete
#: lists longer than 999 rows are real (committed fixtures put
#: ``contributors_total`` at 15,576 and ``clean_contributors`` at 9,273). At
#: five columns ``"10,000"`` rendered ``"10,00"``, a wrong-looking number
#: with no marker, and the pinned YOU row shared the same crop. There is no
#: exact ceiling to size against -- nothing here bounds how large a
#: complete export can be -- so six is not a proof either, only headroom:
#: it holds every committed fixture and any population up to 999,999.
#: ``test_a_complete_list_past_nine_thousand_nine_hundred_ninety_nine_rows_shows_its_real_index``
#: is the tripwire for the five-column crop this reverts.
_INDEX_COLS = 6
_RANK_COLS = 6
_JOIN_COLS = 6
#: The address cell's own **display** width -- round 2's fix, replacing
#: round 1's column-stealing one. The copy icon's two columns have to come
#: from somewhere, and round 1 took them from ``_INDEX_COLS`` (wrongly, see
#: its own comment above) and ``_ENS_COLS``. Per recipe step 6.3 ("when
#: growing would move a pin, shorten the displayed address"): the address
#: itself pays for its own icon instead. ``42 - ICON_COLS`` = 40, the
#: anti-poisoning window (``MIN_SHORT_COLS`` is 11; 40 is nowhere near
#: it -- ``address_text``'s own ``short_address`` only trims the address's
#: *middle*, three hex digits here, at this width) rather than the full,
#: bare 42-character address every row showed in every tier before this
#: task. The window before/after: was unwindowed (``0x…`` the full 42
#: characters); now ``0x`` + 31 hex + ``…`` + 6 hex (40 characters) -- the
#: icon's own click target still copies the real, complete address either
#: way, only the displayed text is shorter.
_ADDRESS_COLS = 40
#: The ADDRESS column's total width: the display above plus the copy
#: icon's two cells, local to this panel exactly like ``leaderboard.py``'s
#: own ``_WALLET_COLS``. Present in every tier (narrow/minimum both keep
#: ADDRESS), so every declared cost below grows by ``ICON_COLS`` -- but
#: ``_ADDRESS_COLS`` shrank by the same ``ICON_COLS``, so this column's
#: *total* width (42) is unchanged from before the copy-icon conversion.
_ADDRESS_COLS_TOTAL = _ADDRESS_COLS + ICON_COLS
#: A soft cap, not a measured worst case: ENS names are unbounded strings
#: and this column ellipsis-truncates its own value past this width (see
#: ``_ens_cell`` below). Round 1 reclaimed one column here to pay for the
#: ADDRESS icon; round 2 reverted that (the icon is now paid entirely out
#: of ``_ADDRESS_COLS``'s own display width, above) and restored the
#: pre-Task-3 value.
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
    ("address", "ADDRESS", _ADDRESS_COLS_TOTAL),
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
    ("address", "ADDRESS", _ADDRESS_COLS_TOTAL),
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


def _compact_criteria(summary, budget: int) -> str:
    clauses = tuple(
        value.strip()
        for value in (summary or ())
        if isinstance(value, str) and value.strip()
    )
    for shown in range(len(clauses), -1, -1):
        hidden = len(clauses) - shown
        candidate = " · ".join(clauses[:shown])
        if hidden:
            candidate = f"{candidate} +{hidden}" if candidate else f"+{hidden}"
        if cell_len(candidate) <= max(budget, 0):
            return candidate
    return ""


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


def _address(value):
    if not isinstance(value, str) or not value.strip():
        return DASH
    # Lower-cased on purpose, ``leaderboard.py``'s own reason: two sources
    # spell one wallet two ways, and the icon copies whichever spelling
    # this cell was given.  No label: ENS is this table's own separate
    # column, so the cell is the address alone -- windowed to
    # `_ADDRESS_COLS` (recipe step 6.3: the icon is paid for by shortening
    # the display, not by taking a column from INDEX or ENS; see
    # `_ADDRESS_COLS`'s own note for the window's exact shape). The icon
    # still copies the real, complete address regardless of how much of it
    # is shown.
    return address_text(value.strip().lower(), width=_ADDRESS_COLS)


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
        self._source_receipt: str | None = None
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

    def mark_filter_applied(
        self,
        limited: bool,
        holder_receipt: str | None = None,
    ) -> None:
        """Show the filtered source boundary after a new filter application."""
        self._export_path = None
        self._export_failed = False
        receipts = []
        if limited:
            receipts.append("first 1,000 wallets only")
        if holder_receipt:
            receipts.append(holder_receipt)
        self._source_receipt = " · ".join(receipts) or None
        self._render_receipt()

    def mark_filter_unavailable(self, message: str) -> None:
        """Replace stale filter/export receipts with the source failure."""
        self._export_path = None
        self._export_failed = False
        self._source_receipt = message
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
        if self._export_path:
            line.display = True
            prefix = "saved → "
            path = self._export_path
            width = max(self.content_size.width - 2, 0)
            if width and cell_len(prefix + path) > width:
                keep = max(width - cell_len(prefix) - 1, 1)
                path = f"…{path[-keep:]}"
            line.update(f"[dim]{prefix}{safe_markup(path)}[/]")
            return
        if self._source_receipt:
            line.display = True
            line.update(safe_markup(self._source_receipt))
            return
        line.display = False
        line.update("")

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
        summary = self._payload.get("filter_summary")
        if self.KIND == "filtered" and summary:
            hint_reserve = visible_len(f"  {self._hint}") if self._hint else 0
            budget = width - visible_len(heading) - 3 - hint_reserve
            criteria = _compact_criteria(summary, budget)
            if criteria:
                heading += (
                    " [not bold dim]· "
                    + safe_markup(criteria)
                    + "[/]"
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
        """Normalise an address for the reverse row lookup.

        ``value`` is either the row's own raw ``address`` field (a plain
        ``str``) or the ADDRESS column's *rendered cell* read back off the
        ``DataTable`` (``table.get_row_at(...)``), which is now a
        pre-built ``Text`` (:func:`_address`'s copy icon needs a real
        ``Style``, not a markup string).

        A ``Text`` cell is read off its copy icon's own click action
        first, never off the visible characters: fix round 2 windows the
        display (``_ADDRESS_COLS`` = 40, the anti-poisoning window) to pay
        for the icon without touching INDEX or ENS, and a windowed address
        has an ellipsis *inside* the 40-character hex run, which
        ``ADDRESS_RE`` (a contiguous 40-hex-character pattern) can no
        longer match -- silently turning every row's key into ``None`` and
        collapsing every sort into a no-op stable pass, which is exactly
        what round 2 first shipped and a click-to-sort test caught.
        ``address_text``'s icon always carries the real, complete address
        in its own ``Style(meta={"@click": "app.copy_address(...)"})``
        span regardless of how much of it is shown, so that is read first;
        a plain ``str`` (the row's own raw field, never windowed) falls
        through to the old whole-string pattern match.
        """
        if isinstance(value, Text):
            for _start, _end, style in value.spans:
                match = _COPY_ACTION_RE.search(str(style.meta.get("@click", "")))
                if match:
                    return match.group(1).casefold()
            value = value.plain
        if not isinstance(value, str):
            return None
        match = ADDRESS_RE.search(value)
        return match.group(0).casefold() if match else None

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

    def _healthy_note(self, prefix: str = "") -> str:
        return ""

    def _unavailable_note(self) -> str:
        return self.UNAVAILABLE

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
        freshness = self._healthy_note(f"{self.EMPTY} · ")
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
            self._set_heading(
                f"[$warning]⚠ {safe_markup(self._unavailable_note())}[/]"
            )
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
            self._set_heading(
                f"[$warning]⚠ {safe_markup(self._unavailable_note())}[/]"
            )
            self._renumber_and_publish(table)
            table.add_row(*cells({}, columns, default=DASH))
            return
        if not usable:
            note = f"[dim]{self.EMPTY}[/]"
            freshness = self._healthy_note(f"{self.EMPTY} · ")
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
        clean_contributors=None, analysis_as_of_hhmm=None,
        analysis_version=None, **_kwargs
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
            "analysis_version": analysis_version,
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

    def _healthy_note(self, prefix: str = "") -> str:
        """The freshness marker, plus THE LIST's analysis version when it
        fits.  ``prefix`` is the plain text already set to render before
        this note on the heading line (the `EMPTY` word and its glue, when
        the list is empty) -- passed in only so the fit check sees the whole
        line.  The marker is load-bearing; the version is decorative and is
        what sheds on a panel too narrow for both."""
        stamp = self._payload.get("analysis_as_of_hhmm")
        if not isinstance(stamp, str) or not stamp.strip():
            return ""
        marker = f"as of {stamp.strip()}"
        version = self._payload.get("analysis_version")
        if isinstance(version, str) and version.strip():
            width = max(self.content_size.width - 2 - cell_len(prefix), 0)
            suffix = f" · {version.strip()}"
            marker = with_optional_suffix(marker, suffix, width)
        return f"[dim]{safe_markup(marker)}[/]"


class CuratorFilteredList(_ListTable):
    TITLE = FILTERED_LIST_TITLE
    TABLE_ID = "curator-filtered-list-table"
    TIERS = _RAW_TIERS
    UNAVAILABLE = FILTERED_LIST_UNAVAILABLE
    EMPTY = FILTERED_LIST_EMPTY
    KIND = "filtered"

    def update_data(
        self, filtered_rows=None, you_list_row=None,
        filtered_complete=None, filter_summary=None,
        filtered_source_reason=None, **_kwargs
    ) -> None:
        self._payload = {
            "rows": filtered_rows,
            "you_list_row": you_list_row,
            "wallet_count": (
                len(filtered_rows) if isinstance(filtered_rows, list) else None
            ),
            "complete": bool(filtered_complete),
            "filter_summary": tuple(filter_summary or ()),
            "filtered_source_reason": filtered_source_reason,
            "seen": True,
        }
        self._render_view()

    def _rows(self):
        return self._payload["rows"]

    def _row_values(self, row: dict) -> dict:
        return _raw_values(row)

    def _unavailable_note(self) -> str:
        reason = self._payload.get("filtered_source_reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
        return super()._unavailable_note()

    def export_rows(self) -> list[dict]:
        rows = []
        for index, address in enumerate(self._ordered_addresses, start=1):
            source = self._rows_by_address[address]
            rows.append({**source, "index": index})
        return rows
