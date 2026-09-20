"""Essence × tier matrix DataTable for the Talismans dashboard.

Renders a 3-row breakdown of live tokens by essence (Lithic / Lumic /
Mythic) across tier columns (Raw / Cut / Fine / Prime / Bonded), plus a
``TOTAL`` column per row and a bold ``TOTAL`` summary row at the bottom.

All cells handle ``None`` and malformed inputs by collapsing to ``"--"``.

The title, its blank row, the columns, the seed row and the
clear-then-repopulate contract are
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s (Branch 7,
WP-B). This panel is the base's **only** ``footer=`` subscriber: its bold
TOTAL line comes out of a different payload key than its rows, so it is a
row the table can have when it has no others -- which is why
``render_table`` paints ``No data`` only when there is no footer either.
``_fmt_int`` is now ``widgets/fmt.fmt_int``.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import DASH, fmt_int
from maxpane_dashboard.widgets.panels import TableLeaderboard


class TalismansMatrixTable(TableLeaderboard):
    """Essence × tier breakdown of the live token population."""

    TITLE = "ESSENCE × TIER MATRIX"

    TABLE_ID = "tal-matrix-dt"

    COLUMNS = (
        ("ESSENCE", 9),
        ("RAW", 7),
        ("CUT", 7),
        ("FINE", 7),
        ("PRIME", 7),
        ("BONDED", 7),
        ("TOTAL", 8),
    )

    #: Three essences and no more; the matrix is not a ranking to cut off.
    ROW_CAP = None

    LOADING_ROW = (DASH, DASH, DASH, DASH, DASH, DASH, "Loading...")

    EMPTY_ROW = (DASH, DASH, DASH, DASH, DASH, DASH, "No data")

    #: Geometry only: the title and its blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    TalismansMatrixTable > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        essence_tier_matrix=None,
        **_kwargs,
    ) -> None:
        """Refresh the matrix rows plus the bold totals row."""
        matrix = essence_tier_matrix or {}
        if not isinstance(matrix, dict):
            matrix = {}
        rows = matrix.get("rows") or []
        totals = matrix.get("totals") or {}

        footer = None
        if isinstance(totals, dict) and totals:
            footer = (
                "[bold]TOTAL[/]",
                f"[bold]{fmt_int(totals.get('raw'))}[/]",
                f"[bold]{fmt_int(totals.get('cut'))}[/]",
                f"[bold]{fmt_int(totals.get('fine'))}[/]",
                f"[bold]{fmt_int(totals.get('prime'))}[/]",
                f"[bold]{fmt_int(totals.get('bonded'))}[/]",
                f"[bold]{fmt_int(totals.get('total'))}[/]",
            )

        self.render_table(rows, footer=footer)

    def build_row(self, index: int, row) -> tuple | None:
        """One essence's row across the five tiers, plus its total."""
        if not isinstance(row, dict):
            return None
        return (
            str(row.get("essence") or DASH),
            fmt_int(row.get("raw")),
            fmt_int(row.get("cut")),
            fmt_int(row.get("fine")),
            fmt_int(row.get("prime")),
            fmt_int(row.get("bonded")),
            fmt_int(row.get("total")),
        )
