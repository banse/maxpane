"""Essence × tier matrix DataTable for the Talismans dashboard.

Renders a 3-row breakdown of live tokens by essence (Lithic / Lumic /
Mythic) across tier columns (Raw / Cut / Fine / Prime / Bonded), plus a
``TOTAL`` column per row and a bold ``TOTAL`` summary row at the bottom.

All cells handle ``None`` and malformed inputs by collapsing to ``"--"``.

Copied from ``ttt_fees_table.py`` and adapted to the Talismans data
contract.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

_DASH = "--"


def _fmt_int(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _DASH


class TalismansMatrixTable(Vertical):
    """Essence × tier breakdown of the live token population."""

    DEFAULT_CSS = """
    TalismansMatrixTable > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TalismansMatrixTable > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("ESSENCE × TIER MATRIX", classes="tal-matrix-title")
        yield Static(" ", classes="tal-matrix-spacer")
        table = DataTable(id="tal-matrix-dt", classes="tal-matrix-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#tal-matrix-dt", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("ESSENCE", width=9)
        table.add_column("RAW", width=7)
        table.add_column("CUT", width=7)
        table.add_column("FINE", width=7)
        table.add_column("PRIME", width=7)
        table.add_column("BONDED", width=7)
        table.add_column("TOTAL", width=8)
        table.add_row(_DASH, _DASH, _DASH, _DASH, _DASH, _DASH, "Loading...")

    def update_data(
        self,
        essence_tier_matrix=None,
        **_kwargs,
    ) -> None:
        """Refresh the matrix rows plus the bold totals row."""
        table = self.query_one("#tal-matrix-dt", DataTable)
        table.clear()

        matrix = essence_tier_matrix or {}
        if not isinstance(matrix, dict):
            matrix = {}
        rows = matrix.get("rows") or []
        totals = matrix.get("totals") or {}

        if not rows and not totals:
            table.add_row(_DASH, _DASH, _DASH, _DASH, _DASH, _DASH, "No data")
            return

        for row in rows:
            if not isinstance(row, dict):
                continue
            table.add_row(
                str(row.get("essence") or _DASH),
                _fmt_int(row.get("raw")),
                _fmt_int(row.get("cut")),
                _fmt_int(row.get("fine")),
                _fmt_int(row.get("prime")),
                _fmt_int(row.get("bonded")),
                _fmt_int(row.get("total")),
            )

        if isinstance(totals, dict) and totals:
            table.add_row(
                "[bold]TOTAL[/]",
                f"[bold]{_fmt_int(totals.get('raw'))}[/]",
                f"[bold]{_fmt_int(totals.get('cut'))}[/]",
                f"[bold]{_fmt_int(totals.get('fine'))}[/]",
                f"[bold]{_fmt_int(totals.get('prime'))}[/]",
                f"[bold]{_fmt_int(totals.get('bonded'))}[/]",
                f"[bold]{_fmt_int(totals.get('total'))}[/]",
            )
