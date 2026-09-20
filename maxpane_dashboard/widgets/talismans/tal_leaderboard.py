"""Top collectors leaderboard for the Talismans dashboard.

Renders a ``DataTable`` of the top collectors, ranked by holdings.  Each
row carries wallet address, live token count, total cores and Mythic
count.

All format helpers tolerate ``None`` -- rendering ``"--"`` rather than
crashing -- because the manager may forward gaps verbatim.

The title, its blank row, the table's cursor/zebra/columns, the seed row
and the clear-then-repopulate contract are
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s (Branch 7,
WP-B). What stays here is what only Talismans knows: the wallet cell, the
rank and the rank-1 bolding. The local ``_fmt_int`` is gone --
``widgets/fmt.fmt_int`` is the one definition of the six identical copies
it was one of.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import DASH, fmt_int
from maxpane_dashboard.widgets.panels import TableLeaderboard
from maxpane_dashboard.widgets.talismans._chain import EXPLORER

#: display budget for the wallet address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced. The table's "WALLET"
#: column is already 14 wide (recipe step 6, PRD §5): W(12) + ICON_COLS(2)
#: fits inside it without moving the column width.
_WALLET_COLS = 12


class TalismansLeaderboard(TableLeaderboard):
    """DataTable leaderboard showing top collectors by holdings."""

    TITLE = "TOP COLLECTORS"

    TABLE_ID = "tal-leaderboard-table"

    COLUMNS = (
        ("#", 3),
        ("WALLET", 14),
        ("TOKENS", 8),
        ("CORES", 8),
        ("MYTHICS", 8),
    )

    LOADING_ROW = (DASH, "Loading...", DASH, DASH, DASH)

    EMPTY_ROW = (DASH, "No data", DASH, DASH, DASH)

    #: Geometry only: the title and its blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    TalismansLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        top_collectors=None,
        **_kwargs,
    ) -> None:
        """Refresh the leaderboard with up to 10 ranked collectors."""
        self.render_table(top_collectors)

    def build_row(self, index: int, row) -> tuple | None:
        """One collector's row. Rank 1 is bold; the wallet cell carries the icon."""
        if not isinstance(row, dict):
            return None
        is_top = index == 0
        rank = row.get("rank", index + 1)
        wallet = address_text(
            row.get("address"),
            width=_WALLET_COLS,
            style="bold" if is_top else "",
            explorer=EXPLORER,
        )
        tokens = fmt_int(row.get("tokens"))
        cores = fmt_int(row.get("cores"))
        mythics = fmt_int(row.get("mythics"))

        # Bold row 1
        if is_top:
            rank_str = f"[bold]{rank}[/]"
            tokens = f"[bold]{tokens}[/]"
            cores = f"[bold]{cores}[/]"
            mythics = f"[bold]{mythics}[/]"
        else:
            rank_str = str(rank)

        return (rank_str, wallet, tokens, cores, mythics)
