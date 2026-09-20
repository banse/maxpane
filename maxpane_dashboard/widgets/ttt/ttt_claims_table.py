"""γ-view (Holder Claim Math) DataTable for the TTT dashboard.

Renders six static scenario rows from
``analytics.ttt_signals.claim_math_scenarios``.  Each row models what
the per-NFT 24h holder claim would look like at a given burn level:

| SCENARIO     | UNBURNED | SHARE/DEPOSIT | 24h PROJECTION |

The "Today" row -- always row 1 -- is rendered bold so the user has a
visual anchor.  (Previously a ``× TODAY`` multiplier column lived to the
right of ``24h PROJECTION`` but was dropped in CR7 because the cell got
clipped by the scrollbar at common terminal widths; ``_fmt_multiplier``
outlived it by two years and is deleted with this migration.)

Like ``TTTFeesTable`` this widget is a sibling under the screen; the
screen toggles ``display`` between the two on the ``c`` keybinding.

The title, its blank row, the columns, the seed row and the
clear-then-repopulate contract are
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s (Branch 7,
WP-B); ``_fmt_int`` is now ``widgets/fmt.fmt_int``, one definition
instead of six.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import DASH, fmt_int
from maxpane_dashboard.widgets.panels import TableLeaderboard


def _fmt_share(value) -> str:
    """``value`` is a percent (e.g. ``0.30`` => ``0.3000%``)."""
    if value is None:
        return DASH
    try:
        return f"{float(value):.4f}%"
    except (TypeError, ValueError):
        return DASH


# Not widgets/fmt.fmt_eth: ungrouped -- probe 1234.5678 renders "1234.56780 Ξ" here,
# "1,234.56780 Ξ" there; True renders "1.00000 Ξ" here, "--" there. Five decimal
# places, pinned by tests/widgets/test_ttt_address_icons.py:133.
def _fmt_eth(value) -> str:
    if value is None:
        return DASH
    try:
        return f"{float(value):.5f} Ξ"
    except (TypeError, ValueError):
        return DASH


class TTTClaimsTable(TableLeaderboard):
    """γ view -- claim-math scenarios across burn levels."""

    TITLE = "γ HOLDER CLAIM MATH"

    TABLE_ID = "ttt-claims-table"

    COLUMNS = (
        ("SCENARIO", 14),
        ("UNBURNED", 9),
        ("SHARE/DEPOSIT", 13),
        ("24h PROJECTION", 14),
    )

    #: Six scenarios; the analytics produces exactly that many.
    ROW_CAP = 6

    LOADING_ROW = (DASH, DASH, "Loading...", DASH)

    EMPTY_ROW = (DASH, DASH, "No data", DASH)

    #: Geometry only: the title and its blank row are ``PanelBase``'s.
    DEFAULT_CSS = """
    TTTClaimsTable > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        claim_math_scenarios=None,
        **_kwargs,
    ) -> None:
        """Refresh the six scenario rows."""
        self.render_table(claim_math_scenarios)

    def build_row(self, index: int, row) -> tuple | None:
        """One scenario's row; the "Today" row is bold."""
        if not isinstance(row, dict):
            return None
        scenario = row.get("scenario") or DASH
        unburned = fmt_int(row.get("unburned"))
        share = _fmt_share(row.get("share_pct"))
        projected = _fmt_eth(row.get("projected_24h_eth"))

        # Highlight the "Today" row (always the first scenario)
        is_today = str(scenario).strip().lower() == "today" or index == 0
        if is_today:
            scenario = f"[bold]{scenario}[/]"
            unburned = f"[bold]{unburned}[/]"
            share = f"[bold]{share}[/]"
            projected = f"[bold]{projected}[/]"

        return (scenario, unburned, share, projected)
