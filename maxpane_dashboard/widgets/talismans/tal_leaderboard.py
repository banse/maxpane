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

_DASH = "--"


# -- format helpers ----------------------------------------------------


def _short_addr(addr) -> str:
    """Render ``0xABCD..1234`` from a full address; dash if missing."""
    if not addr:
        return _DASH
    s = str(addr).strip()
    if not s:
        return _DASH
    if len(s) <= 11:
        return s
    return f"{s[:6]}..{s[-4:]}"


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
            wallet = _short_addr(row.get("address"))
            tokens = _fmt_int(row.get("tokens"))
            cores = _fmt_int(row.get("cores"))
            mythics = _fmt_int(row.get("mythics"))

            # Bold row 1
            if idx == 1:
                rank_str = f"[bold]{rank}[/]"
                wallet = f"[bold]{wallet}[/]"
                tokens = f"[bold]{tokens}[/]"
                cores = f"[bold]{cores}[/]"
                mythics = f"[bold]{mythics}[/]"
            else:
                rank_str = str(rank)

            table.add_row(rank_str, wallet, tokens, cores, mythics)
