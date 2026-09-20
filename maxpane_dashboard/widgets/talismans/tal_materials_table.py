"""Materials ledger DataTable for the Talismans dashboard.

Renders a ranked ledger of materials, each with its essence class, live
token count and core count.

| #  | MATERIAL | ESSENCE | TOKENS | CORES |

All cells handle ``None`` and malformed inputs by collapsing to ``"--"``.

The title, its blank row, the columns, the seed row and the
clear-then-repopulate contract are
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s (Branch 7,
WP-B); ``_fmt_int`` is now ``widgets/fmt.fmt_int``, one definition
instead of six.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import DASH, fmt_int
from maxpane_dashboard.widgets.panels import TableLeaderboard


def _fmt_text(value) -> str:
    """A trimmed string, or :data:`~maxpane_dashboard.widgets.fmt.DASH`.

    Stays local: nothing else in the repo renders a free-text cell this
    way, and a helper with one user is not a hoist.
    """
    if value is None:
        return DASH
    s = str(value).strip()
    return s if s else DASH


class TalismansMaterialsTable(TableLeaderboard):
    """Ranked ledger of materials by holdings."""

    TITLE = "MATERIALS LEDGER"

    TABLE_ID = "tal-materials-dt"

    COLUMNS = (
        ("#", 3),
        ("MATERIAL", 16),
        ("ESSENCE", 9),
        ("TOKENS", 8),
        ("CORES", 8),
    )

    ROW_CAP = 12

    LOADING_ROW = (DASH, "Loading...", DASH, DASH, DASH)

    EMPTY_ROW = (DASH, "No data", DASH, DASH, DASH)

    #: Geometry only: the title and its blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    TalismansMaterialsTable > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        materials_ledger=None,
        **_kwargs,
    ) -> None:
        """Refresh the table with the ranked materials ledger."""
        self.render_table(materials_ledger)

    def build_row(self, index: int, row) -> tuple | None:
        """One material's row; rank 1 is bold."""
        if not isinstance(row, dict):
            return None
        rank = row.get("rank", index + 1)
        material = _fmt_text(row.get("material"))
        essence = _fmt_text(row.get("essence"))
        tokens = fmt_int(row.get("tokens"))
        cores = fmt_int(row.get("cores"))

        if index == 0:
            rank_str = f"[bold]{rank}[/]"
            material = f"[bold]{material}[/]"
        else:
            rank_str = str(rank)

        return (rank_str, material, essence, tokens, cores)
