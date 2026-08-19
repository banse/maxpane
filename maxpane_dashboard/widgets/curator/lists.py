"""The full-width raw and cleaned record tables used by curator list mode."""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    DASH,
    NAME_COLS,
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
from maxpane_dashboard.widgets.curator.leaderboard import _link_glyph
from maxpane_dashboard.widgets.markup_safety import safe_markup

RAW_LIST_TITLE = "THE RAW LIST"
CLEANED_LIST_TITLE = "THE CLEANED LIST"

RAW_LIST_UNAVAILABLE = "raw list unavailable"
RAW_LIST_EMPTY = "no contributors"
CLEANED_LIST_UNAVAILABLE = "analysis unavailable"
CLEANED_LIST_EMPTY = "no wallets survive"

MAX_ROWS = 1_000

_RANK_COLS = 6
_JOIN_COLS = 6
_ADDRESS_COLS = 42
_ENS_COLS = NAME_COLS + 7
_POINTS_COLS = 7
_WEIGHT_COLS = 8
_CREDIT_COLS = 8
_DEPOSITS_COLS = 8
_HOUR_COLS = 4
_WINDOW_COLS = 6
_LINK_COLS = 4

_RAW_FULL = (
    ("rank", "#", _RANK_COLS),
    ("join", "JOIN #", _JOIN_COLS),
    ("address", "ADDRESS", _ADDRESS_COLS),
    ("ens", "ENS", _ENS_COLS),
    ("points", "POINTS", _POINTS_COLS),
    ("weight", "WEIGHT Ξ", _WEIGHT_COLS),
    ("credit", "CREDIT Ξ", _CREDIT_COLS),
    ("deposits", "DEPOSITS", _DEPOSITS_COLS),
    ("hour", "HOUR", _HOUR_COLS),
    ("window", "WINDOW", _WINDOW_COLS),
    ("link", "LINK", _LINK_COLS),
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
    if column[0] in ("rank", "address", "ens", "points", "link")
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
    ("rank", "#", _RANK_COLS),
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
    if column[0] in ("rank", "address", "ens", "points")
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
        "link": _link_glyph(row.get("link_conf"), None),
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
        if self._hint and not placed:
            marker = f"[yellow]{WIDEN_HINT}[/]"
            note = f"{marker} {note}" if note else marker
        self.query_one(".curator-list-note", Static).update(note)

    def _rows(self):
        raise NotImplementedError

    def _row_values(self, row: dict) -> dict:
        raise NotImplementedError

    def _healthy_note(self) -> str:
        return ""

    def _render_view(self) -> None:
        try:
            table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        except Exception:
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        you = self._payload.get("you_list_row")
        if isinstance(you, dict):
            try:
                values = self._row_values(you)
            except Exception:
                values = {}
            self.query_one(".curator-list-you", DataTable).add_row(
                *cells(values, columns, default=DASH)
            )
        else:
            self.query_one(".curator-list-you", DataTable).add_row(
                *cells({}, columns)
            )
        rows = self._rows()
        if rows is None:
            self._set_heading(f"[$warning]⚠ {self.UNAVAILABLE}[/]")
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
            table.add_row(*cells({}, columns, default=DASH))
            return
        if not usable:
            note = f"[dim]{self.EMPTY}[/]"
            freshness = self._healthy_note()
            if freshness:
                note = f"{note} · {freshness}"
            self._set_heading(note)
            return

        self._set_heading(self._healthy_note())
        for row in usable[:MAX_ROWS]:
            try:
                values = self._row_values(row)
            except Exception:
                values = {}
            table.add_row(*cells(values, columns, default=DASH))


class CuratorRawList(_ListTable):
    """The raw leaderboard payload, without the dashboard's ten-row cap."""

    TITLE = RAW_LIST_TITLE
    TABLE_ID = "curator-raw-list-table"
    TIERS = _RAW_TIERS
    UNAVAILABLE = RAW_LIST_UNAVAILABLE
    EMPTY = RAW_LIST_EMPTY

    def update_data(
        self, leaderboard_rows=None, you_list_row=None,
        contributors_total=None, **_kwargs
    ) -> None:
        self._payload = {
            "rows": leaderboard_rows,
            "you_list_row": you_list_row,
            "wallet_count": contributors_total,
            "seen": True,
        }
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

    def update_data(
        self, clean_list_rows=None, you_list_row=None,
        clean_contributors=None, analysis_as_of_hhmm=None, **_kwargs
    ) -> None:
        self._payload = {
            "rows": clean_list_rows,
            "you_list_row": you_list_row,
            "wallet_count": clean_contributors,
            "analysis_as_of_hhmm": analysis_as_of_hhmm,
            "seen": True,
        }
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
