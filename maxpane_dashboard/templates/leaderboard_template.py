"""Leaderboard template -- copy and adapt for new game dashboards.

Pattern: Vertical container with a title Static and a DataTable.
Uses fixed-width columns, zebra stripes, and cursor_type="row".
Highlights the leader row with bold markup.

**The blank row under the title is not optional.**  Every panel title in
this repo is followed by one blank row (``margin: 0 0 1 0`` on the title's
own class), so a panel is separated from whatever sits above it.  Keep that
rule when you copy this file.  On 2026-09-12 a survey found 36 panel titles
across the app missing it and **all six of these templates** missing it too,
which is how it spread: a defect in a copy-source is a defect in every
dashboard not yet written.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_overview_leaderboard.py
  - maxpane_dashboard/widgets/cattown/ct_leaderboard.py

Every displayed 0x address -- and every name that stands in for one -- goes
through ``widgets/address.py`` and carries the copy icon. That is a repo rule,
not a style: tests/test_address_rule.py fails on a private address formatter
and tests/screens/test_address_icons_everywhere.py fails on an address that
reaches the screen without its icon. Copy this, keep the import.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.address import ICON_COLS, address_text
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Display budget for the name/address cell, excluding the icon. The
#: DataTable column below is ``NAME_COLS + ICON_COLS`` wide so the icon
#: never shortens the previous 16-cell display (recipe: grow where there
#: is slack -- this template has no layout pin to protect).
NAME_COLS = 16


class GameLeaderboard(Vertical):
    """Leaderboard panel with DataTable of top entries.

    Rename for your game, e.g. ``CTLeaderboard``, ``DOTALeaderboard``.
    Update column definitions and update_data() to match your schema.
    """

    DEFAULT_CSS = """
    /* The title. `margin: 0 0 1 0` IS THE BLANK ROW UNDER IT and it is
       mandatory -- see the module docstring. The selector is the bare
       `> Static` because the DataTable below is not one; give the title its
       own class when you adapt this and the margin goes with the class. */
    GameLeaderboard > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
        margin: 0 0 1 0;
    }
    GameLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LEADERBOARD")
        table = DataTable(id="game-leaderboard-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#game-leaderboard-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        # Adapt columns to your game
        table.add_column("#", width=4)
        table.add_column("Name", width=NAME_COLS + ICON_COLS)
        table.add_column("Score", width=12)
        table.add_column("Detail", width=12)
        table.add_column("Status", width=10)

    def update_data(self, entries: list[dict] | None = None) -> None:
        """Clear and repopulate the leaderboard table with live data.

        Adapt the dict keys to your game's leaderboard schema.
        """
        table = self.query_one("#game-leaderboard-table", DataTable)
        table.clear()

        if not entries:
            table.add_row("--", "No data", "--", "--", "--")
            return

        for idx, entry in enumerate(entries[:10], start=1):
            score = entry.get("score", 0)
            detail = entry.get("detail", "")
            status = entry.get("status", "")

            # Format score with K/M/B suffix
            score_f = float(score)
            if score_f >= 1_000_000_000:
                score_str = f"{score_f / 1_000_000_000:.1f}B"
            elif score_f >= 1_000_000:
                score_str = f"{score_f / 1_000_000:.1f}M"
            elif score_f >= 1_000:
                score_str = f"{score_f / 1_000:.1f}K"
            else:
                score_str = f"{score_f:,.0f}"

            # detail / status came from an API / another player, so they must
            # be escaped before they reach Rich markup rendering. DataTable
            # defers Text.from_markup to its idle handler, so an unescaped
            # "[/x]" crashes the app from inside the message pump.
            detail = safe_markup(detail)
            status = safe_markup(status)

            # The name/address cell is a pre-built Text (address_text), not a
            # markup string: it needs no safe_markup escaping, and it is how
            # the copy icon's click action survives -- a markup string could
            # never carry a Style with @click meta on just the glyph. A
            # player name stands in for the address when one is set; the
            # icon still copies the address either way.
            name_display = address_text(
                entry.get("address"),
                label=entry.get("name") or None,
                width=NAME_COLS,
                style="bold" if idx == 1 else "",
            )

            # Highlight the leader row
            if idx == 1:
                score_str = f"[bold]{score_str}[/]"

            table.add_row(str(idx), name_display, score_str, detail, status)
