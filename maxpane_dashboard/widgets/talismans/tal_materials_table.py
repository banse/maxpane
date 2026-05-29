"""Materials ledger DataTable for the Talismans dashboard.

Renders a ranked ledger of materials, each with its essence class, live
token count and core count.

| #  | MATERIAL | ESSENCE | TOKENS | CORES |

All cells handle ``None`` and malformed inputs by collapsing to ``"--"``.

Copied from ``ttt_claims_table.py`` and adapted to the Talismans data
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


def _fmt_text(value) -> str:
    if value is None:
        return _DASH
    s = str(value).strip()
    return s if s else _DASH


class TalismansMaterialsTable(Vertical):
    """Ranked ledger of materials by holdings."""

    DEFAULT_CSS = """
    TalismansMaterialsTable > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TalismansMaterialsTable > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("MATERIALS LEDGER", classes="tal-materials-title")
        yield Static(" ", classes="tal-materials-spacer")
        table = DataTable(
            id="tal-materials-dt", classes="tal-materials-table"
        )
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#tal-materials-dt", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=3)
        table.add_column("MATERIAL", width=16)
        table.add_column("ESSENCE", width=9)
        table.add_column("TOKENS", width=8)
        table.add_column("CORES", width=8)
        table.add_row(_DASH, "Loading...", _DASH, _DASH, _DASH)

    def update_data(
        self,
        materials_ledger=None,
        **_kwargs,
    ) -> None:
        """Refresh the table with the ranked materials ledger."""
        table = self.query_one("#tal-materials-dt", DataTable)
        table.clear()

        ledger = materials_ledger or []
        if not ledger:
            table.add_row(_DASH, "No data", _DASH, _DASH, _DASH)
            return

        for idx, row in enumerate(ledger[:12], start=1):
            if not isinstance(row, dict):
                continue
            rank = row.get("rank", idx)
            material = _fmt_text(row.get("material"))
            essence = _fmt_text(row.get("essence"))
            tokens = _fmt_int(row.get("tokens"))
            cores = _fmt_int(row.get("cores"))

            if idx == 1:
                rank_str = f"[bold]{rank}[/]"
                material = f"[bold]{material}[/]"
            else:
                rank_str = str(rank)

            table.add_row(rank_str, material, essence, tokens, cores)
