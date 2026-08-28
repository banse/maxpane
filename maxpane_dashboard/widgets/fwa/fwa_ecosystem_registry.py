"""Verified-integration registry for projects built on FWA."""

from __future__ import annotations

from rich.cells import cell_len
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
    ("project", "PROJECT / SURFACE", 24),
    ("lifecycle", "STATE", 11),
    ("primary", "PRIMARY", 24),
    ("eth", "ETH ACCOUNTING", 20),
    ("fwa", "FWA ACCOUNTING", 20),
    ("source", "SOURCE", 11),
    ("detail", "DETAIL", 24),
)
_WIDE_COLUMNS = (
    ("project", "PROJECT / SURFACE", 22),
    ("lifecycle", "STATE", 10),
    ("primary", "PRIMARY", 21),
    ("eth", "ETH ACCOUNTING", 18),
    ("fwa", "FWA ACCOUNTING", 18),
    ("source", "SOURCE", 11),
)
_COMPACT_COLUMNS = (
    ("project", "PROJECT / SURFACE", 20),
    ("lifecycle", "STATE", 10),
    ("primary", "PRIMARY", 19),
    ("eth", "ETH", 16),
    ("fwa", "FWA", 16),
)
_TINY_COLUMNS = (
    ("project", "PROJECT", 14),
    ("primary", "PRIMARY", 14),
    ("eth", "ETH", 16),
    ("fwa", "FWA", 16),
)

REGISTRY_TABLE_TIERS = (
    ("full", tier_cost(_FULL_COLUMNS), _FULL_COLUMNS, ""),
    ("wide", tier_cost(_WIDE_COLUMNS), _WIDE_COLUMNS, "‹ widen: DETAIL"),
    (
        "compact",
        tier_cost(_COMPACT_COLUMNS),
        _COMPACT_COLUMNS,
        "‹ widen: SOURCE + DETAIL",
    ),
    (
        "tiny",
        tier_cost(_TINY_COLUMNS),
        _TINY_COLUMNS,
        "‹ widen: state + source",
    ),
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


def _fmt_number(value, *, integer: bool = False) -> str:
    number = _number(value)
    if number is None:
        return _NA
    if integer:
        return f"{int(number):,}"
    return f"{number:,.3f}"


def _unit_for_primary(unit) -> tuple[str, bool]:
    kind = str(unit or "").strip().lower()
    if kind == "recovery_pct":
        return "%", False
    if kind == "nav_eth":
        return "ETH", False
    return kind.replace("_", " "), kind in ("rounds", "packs", "orders")


def _labelled_metric(label, value, unit: str, width: int, *, integer: bool = False) -> str:
    """Fit the label first while retaining the measured value's unit."""
    label_text = str(label or "value").strip() or "value"
    rendered = _fmt_number(value, integer=integer)
    suffix = f"{rendered}{' ' + unit if unit else ''}"
    if cell_len(suffix) > width:
        number = _number(value)
        compact = _NA if number is None else f"{number:.3g}"
        suffix = f"{compact}{' ' + unit if unit else ''}"
    label_width = max(width - cell_len(suffix) - 1, 0)
    label_fit = fit_cell(label_text, label_width)[0]
    text = f"{label_fit} {suffix}" if label_fit else suffix
    return fit_cell(text, width)[0]


def _project_name(row: dict) -> str:
    family = str(row.get("family") or _NA).strip() or _NA
    surface = str(row.get("surface") or "").strip()
    version = str(row.get("version") or "").strip()
    name = family if not surface or surface == family else f"{family}/{surface}"
    if version:
        name += f" {version}"
    # Only rows explicitly classified as legacy liabilities are indented.
    if row.get("is_legacy_liability") is True:
        name = f"↳ {name}"
    return name


def _row_values(row: dict, columns: tuple) -> dict[str, Text]:
    widths = {key: width for key, _header, width in columns}
    primary_unit, primary_integer = _unit_for_primary(row.get("primary_unit"))
    primary = _labelled_metric(
        row.get("primary_label"),
        row.get("primary_value"),
        primary_unit,
        widths.get("primary", 24),
        integer=primary_integer,
    )
    eth = _labelled_metric(
        row.get("eth_label"), row.get("eth_value"), "ETH", widths.get("eth", 20)
    )
    fwa = _labelled_metric(
        row.get("fwa_label"), row.get("fwa_value"), "FWA", widths.get("fwa", 20)
    )
    source = str(row.get("source_badge") or _NA).strip() or _NA
    integrity = str(row.get("integrity") or "unknown").lower()
    if integrity not in ("ok", "unknown", "") and source != "INTEGRITY":
        source = f"! {source}"
    if row.get("stale") is True:
        source = f"{source} stale"
    values = {
        "project": _project_name(row),
        "lifecycle": str(row.get("lifecycle") or _NA),
        "primary": primary,
        "eth": eth,
        "fwa": fwa,
        "source": source,
        "detail": str(row.get("detail") or _NA),
    }
    return {
        key: Text(fit_cell(values.get(key, _NA), widths[key])[0])
        for key, _header, _width in columns
    }


class FWAEcosystemRegistry(Vertical):
    """Current project surfaces plus visible legacy liabilities."""

    DEFAULT_CSS = """
    FWAEcosystemRegistry {
        min-height: 12;
        border: solid $panel;
        background: $surface;
    }
    FWAEcosystemRegistry > .fwa-registry-title,
    FWAEcosystemRegistry > .fwa-registry-note {
        width: 100%;
        padding: 0 1;
    }
    FWAEcosystemRegistry > .fwa-registry-title {
        text-style: bold;
        color: $text-muted;
    }
    FWAEcosystemRegistry > DataTable {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()

    def compose(self) -> ComposeResult:
        yield Static(
            "VERIFIED INTEGRATIONS",
            id="fwa-registry-title",
            classes="fwa-registry-title",
        )
        yield Static(" ", id="fwa-registry-note", classes="fwa-registry-note")
        yield DataTable(id="fwa-registry-table")

    def on_mount(self) -> None:
        table = self.query_one("#fwa-registry-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns, _hint = self._apply_columns(table)
        table.add_row(*cells({columns[0][0]: Text("Loading...")}, columns, Text("")))

    def update_data(
        self,
        *,
        network_project_rows=None,
        network_projects_available=None,
        network_projects_as_of_block=None,
        network_projects_stale=None,
    ) -> None:
        try:
            rows = [
                row for row in list(network_project_rows or []) if isinstance(row, dict)
            ]
        except TypeError:
            rows = []
        available = bool(rows) if network_projects_available is None else bool(
            network_projects_available
        )
        self._payload = {
            "rows": rows,
            "available": available,
            "block": network_projects_as_of_block,
            "stale": network_projects_stale,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def _table_width(self, table: DataTable) -> int:
        return table.content_size.width or self.content_size.width

    def _apply_columns(self, table: DataTable) -> tuple[tuple, str]:
        _name, columns, hint = pick_tier(
            REGISTRY_TABLE_TIERS, self._table_width(table)
        )
        install_columns(table, columns, self._columns)
        self._columns = columns
        return columns, hint

    def _render_view(self) -> None:
        try:
            table = self.query_one("#fwa-registry-table", DataTable)
            title = self.query_one("#fwa-registry-title", Static)
            note = self.query_one("#fwa-registry-note", Static)
        except Exception:
            return
        columns, hint = self._apply_columns(table)
        width = max(self.content_size.width - 2, 0)
        title_text, placed = title_with_hint("VERIFIED INTEGRATIONS", hint, width)
        title.update(title_text)

        block = self._payload.get("block")
        try:
            block_text = f"{int(block):,}" if block is not None else _NA
        except (TypeError, ValueError, OverflowError):
            block_text = _NA
        state = "live"
        if not self._payload.get("available"):
            state = "unavailable · last good" if self._payload.get("rows") else "unavailable"
        if self._payload.get("stale") is True:
            state = f"{state} · stale"
        note.update(Text(fit_cell(f"{state} · as of #{block_text}", width or 160)[0]))

        if hint and not placed:
            table.add_row(*cells({columns[0][0]: Text(WIDEN_HINT)}, columns, Text("")))
        rows = self._payload.get("rows") or []
        if not rows:
            message = (
                "no project surfaces"
                if self._payload.get("available")
                else "project data unavailable"
            )
            table.add_row(*cells({columns[0][0]: Text(message)}, columns, Text("")))
            return
        for row in rows:
            table.add_row(*cells(_row_values(row, columns), columns, Text(_NA)))
