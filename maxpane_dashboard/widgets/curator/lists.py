"""The full raw and cleaned record lists used by the curator ``l`` view.

Both widgets are render-only. They receive the existing manager rows, cap their
own display at 100, and shed named columns rather than clipping them silently.
"""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import (
    ADDR_COLS,
    DASH,
    fmt_eth_compact,
    fmt_points,
    short_addr,
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
from maxpane_dashboard.widgets.curator.leaderboard import _flag_cell, _link_glyph
from maxpane_dashboard.widgets.markup_safety import safe_markup

RAW_LIST_TITLE = "THE RAW LIST"
CLEANED_LIST_TITLE = "THE CLEANED LIST"

RAW_LIST_UNAVAILABLE = "raw list unavailable"
RAW_LIST_EMPTY = "no contributors"
CLEANED_LIST_UNAVAILABLE = "analysis unavailable"
CLEANED_LIST_EMPTY = "no wallets survive"

MAX_ROWS = 100

_RANK_COLS = 4
_POINTS_COLS = 7
_CREDIT_COLS = 8
_TX_COLS = 4
_FLAG_COLS = 4
_LINK_COLS = 4
_NAME_COLS = 10

_RAW_FULL = (
    ("rank", "#", _RANK_COLS),
    ("address", "ADDRESS", ADDR_COLS),
    ("points", "POINTS", _POINTS_COLS),
    ("credit", "CREDIT", _CREDIT_COLS),
    ("tx", "TX", _TX_COLS),
    ("flag", "FLAG", _FLAG_COLS),
    ("name", "NAME", _NAME_COLS),
    ("link", "LINK", _LINK_COLS),
)
_RAW_COMPACT = tuple(column for column in _RAW_FULL if column[0] != "name")
_RAW_NARROW = tuple(
    column for column in _RAW_COMPACT if column[0] not in ("credit", "tx")
)
_RAW_TIERS = (
    ("full", tier_cost(_RAW_FULL), _RAW_FULL, ""),
    ("compact", tier_cost(_RAW_COMPACT), _RAW_COMPACT, "‹ widen: NAME"),
    (
        "narrow",
        tier_cost(_RAW_NARROW),
        _RAW_NARROW,
        "‹ widen: NAME + CREDIT + TX",
    ),
)

_CLEANED_FULL = (
    ("rank", "#", _RANK_COLS),
    ("address", "ADDRESS", ADDR_COLS),
    ("points", "POINTS", _POINTS_COLS),
    ("credit", "CREDIT", _CREDIT_COLS),
    ("name", "NAME", _NAME_COLS),
)
_CLEANED_COMPACT = tuple(
    column for column in _CLEANED_FULL if column[0] != "name"
)
_CLEANED_NARROW = tuple(
    column for column in _CLEANED_COMPACT if column[0] != "credit"
)
_CLEANED_TIERS = (
    ("full", tier_cost(_CLEANED_FULL), _CLEANED_FULL, ""),
    (
        "compact",
        tier_cost(_CLEANED_COMPACT),
        _CLEANED_COMPACT,
        "‹ widen: NAME",
    ),
    (
        "narrow",
        tier_cost(_CLEANED_NARROW),
        _CLEANED_NARROW,
        "‹ widen: NAME + CREDIT",
    ),
)


def _rank(value) -> str:
    if value is None or isinstance(value, bool):
        return DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return DASH


def _name(value) -> str:
    if not isinstance(value, str):
        return DASH
    cleaned = " ".join(value.split())
    if not cleaned:
        return DASH
    if cell_len(cleaned) > _NAME_COLS:
        cleaned = f"{set_cell_size(cleaned, _NAME_COLS - 1)}…"
    return safe_markup(cleaned)


def _address(value) -> str:
    return safe_markup(short_addr(value))


def _raw_values(row: dict) -> dict:
    return {
        "rank": _rank(row.get("rank")),
        "address": _address(row.get("address")),
        "points": fmt_points(row.get("points")),
        "credit": fmt_eth_compact(row.get("credit_eth")),
        "tx": _rank(row.get("tx_count")),
        "flag": _flag_cell(row.get("flagged")),
        "name": _name(row.get("name")),
        "link": _link_glyph(row.get("link_conf"), None),
    }


def _cleaned_values(row: dict) -> dict:
    return {
        "rank": _rank(row.get("clean_rank")),
        "address": _address(row.get("address")),
        "points": fmt_points(row.get("points")),
        "credit": fmt_eth_compact(row.get("credit_eth")),
        "name": _name(row.get("name")),
    }


class _ListTable(Vertical):
    """Shared table mechanics; subclasses define only their frozen row shape."""

    TITLE = ""
    TABLE_ID = ""
    TIERS: tuple = ()
    UNAVAILABLE = ""
    EMPTY = ""

    DEFAULT_CSS = """
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
        height: auto;
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

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="curator-list-title")
        yield Static("", classes="curator-list-note")
        yield DataTable(id=self.TABLE_ID, classes="curator-list-table")

    def on_mount(self) -> None:
        table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({}, columns, default="…"))

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _apply_columns(self, table: DataTable) -> tuple:
        width = table.content_size.width or self.content_size.width
        _name, columns, hint = pick_tier(self.TIERS, width)
        install_columns(table, columns, self._columns)
        self._columns = columns
        self._hint = hint
        return columns

    def _set_heading(self, note: str) -> None:
        width = max(self.content_size.width - 2, 0)
        title, placed = title_with_hint(self.TITLE, self._hint, width)
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

    def update_data(self, leaderboard_rows=None, **_kwargs) -> None:
        self._payload = {"rows": leaderboard_rows, "seen": True}
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._export_path: str | None = None
        self._export_failed = False

    def compose(self) -> ComposeResult:
        yield Static(self.TITLE, classes="curator-list-title")
        yield Static("", classes="curator-list-note")
        receipt = Static("", classes="curator-list-receipt")
        receipt.display = False
        yield receipt
        yield DataTable(id=self.TABLE_ID, classes="curator-list-table")

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
        if width and len(prefix) + len(path) > width:
            keep = max(width - len(prefix) - 1, 1)
            path = f"…{path[-keep:]}"
        line.update(f"[dim]{prefix}{safe_markup(path)}[/]")

    def update_data(
        self, clean_list_rows=None, analysis_as_of_hhmm=None, **_kwargs
    ) -> None:
        self._payload = {
            "rows": clean_list_rows,
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
