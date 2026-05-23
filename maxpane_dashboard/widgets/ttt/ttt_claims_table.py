"""γ-view (Holder Claim Math) DataTable for the TTT dashboard.

Renders six static scenario rows from
``analytics.ttt_signals.claim_math_scenarios``.  Each row models what
the per-NFT 24h holder claim would look like at a given burn level:

| SCENARIO     | UNBURNED | SHARE/DEPOSIT | 24h PROJECTION |

The "Today" row -- always row 1 -- is rendered bold so the user has a
visual anchor.  (Previously a ``× TODAY`` multiplier column lived to the
right of ``24h PROJECTION`` but was dropped in CR7 because the cell got
clipped by the scrollbar at common terminal widths.)

Like ``TTTFeesTable`` this widget is a sibling under the screen; the
screen toggles ``display`` between the two on the ``c`` keybinding.
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


def _fmt_share(value) -> str:
    """``value`` is a percent (e.g. ``0.30`` => ``0.3000%``)."""
    if value is None:
        return _DASH
    try:
        return f"{float(value):.4f}%"
    except (TypeError, ValueError):
        return _DASH


def _fmt_eth(value) -> str:
    if value is None:
        return _DASH
    try:
        return f"{float(value):.5f} Ξ"
    except (TypeError, ValueError):
        return _DASH


def _fmt_multiplier(value) -> str:
    if value is None:
        return _DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DASH
    if v <= 0:
        return _DASH
    return f"{v:.2f}×"


class TTTClaimsTable(Vertical):
    """γ view -- claim-math scenarios across burn levels."""

    DEFAULT_CSS = """
    TTTClaimsTable > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TTTClaimsTable > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("γ HOLDER CLAIM MATH", classes="ttt-claims-title")
        yield Static(" ", classes="ttt-claims-spacer")
        table = DataTable(id="ttt-claims-table", classes="ttt-claims-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#ttt-claims-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("SCENARIO", width=14)
        table.add_column("UNBURNED", width=10)
        table.add_column("SHARE/DEPOSIT", width=14)
        table.add_column("24h PROJECTION", width=14)
        table.add_row(_DASH, _DASH, "Loading...", _DASH)

    def update_data(
        self,
        claim_math_scenarios=None,
        **_kwargs,
    ) -> None:
        """Refresh the six scenario rows."""
        table = self.query_one("#ttt-claims-table", DataTable)
        table.clear()

        scenarios = claim_math_scenarios or []
        if not scenarios:
            table.add_row(_DASH, _DASH, "No data", _DASH)
            return

        for idx, row in enumerate(scenarios[:6]):
            if not isinstance(row, dict):
                continue
            scenario = row.get("scenario") or _DASH
            unburned = _fmt_int(row.get("unburned"))
            share = _fmt_share(row.get("share_pct"))
            projected = _fmt_eth(row.get("projected_24h_eth"))

            # Highlight the "Today" row (always the first scenario)
            is_today = (
                str(scenario).strip().lower() == "today" or idx == 0
            )
            if is_today:
                scenario = f"[bold]{scenario}[/]"
                unburned = f"[bold]{unburned}[/]"
                share = f"[bold]{share}[/]"
                projected = f"[bold]{projected}[/]"

            table.add_row(scenario, unburned, share, projected)
