"""Top collectors leaderboard for the Talismans dashboard.

Renders a ``DataTable`` of the top collectors, ranked by holdings.  Each
row carries wallet address, live token count, total cores and Mythic
count.  Format helpers are local to this file so the widget has no
dependency on game-specific analytics modules.

All format helpers tolerate ``None`` -- rendering ``"--"`` rather than
crashing -- because the manager may forward gaps verbatim.

Copied from ``ttt_leaderboard.py`` and adapted to the Talismans data
contract.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.talismans._chain import EXPLORER

_DASH = "--"

#: display budget for the wallet address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced. The table's "WALLET"
#: column is already 14 wide (recipe step 6, PRD §5): W(12) + ICON_COLS(2)
#: fits inside it without moving the column width.
_WALLET_COLS = 12


# -- format helpers ----------------------------------------------------


def _fmt_int(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _DASH


# -- widget ------------------------------------------------------------


class TalismansLeaderboard(Vertical):
    """DataTable leaderboard showing top collectors by holdings."""

    DEFAULT_CSS = """
    TalismansLeaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TalismansLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TOP COLLECTORS", classes="tal-leaderboard-title")
        yield Static(" ", classes="tal-leaderboard-spacer")
        table = DataTable(
            id="tal-leaderboard-table", classes="tal-leaderboard-table"
        )
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#tal-leaderboard-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=3)
        table.add_column("WALLET", width=14)
        table.add_column("TOKENS", width=8)
        table.add_column("CORES", width=8)
        table.add_column("MYTHICS", width=8)
        table.add_row(_DASH, "Loading...", _DASH, _DASH, _DASH)

    def update_data(
        self,
        top_collectors=None,
        **_kwargs,
    ) -> None:
        """Refresh the leaderboard with up to 10 ranked collectors."""
        table = self.query_one("#tal-leaderboard-table", DataTable)
        table.clear()

        collectors = top_collectors or []
        if not collectors:
            table.add_row(_DASH, "No data", _DASH, _DASH, _DASH)
            return

        for idx, row in enumerate(collectors[:10], start=1):
            if not isinstance(row, dict):
                continue
            rank = row.get("rank", idx)
            is_top = idx == 1
            wallet = address_text(
                row.get("address"),
                width=_WALLET_COLS,
                style="bold" if is_top else "",
                explorer=EXPLORER,
            )
            tokens = _fmt_int(row.get("tokens"))
            cores = _fmt_int(row.get("cores"))
            mythics = _fmt_int(row.get("mythics"))

            # Bold row 1
            if is_top:
                rank_str = f"[bold]{rank}[/]"
                tokens = f"[bold]{tokens}[/]"
                cores = f"[bold]{cores}[/]"
                mythics = f"[bold]{mythics}[/]"
            else:
                rank_str = str(rank)

            table.add_row(rank_str, wallet, tokens, cores, mythics)
