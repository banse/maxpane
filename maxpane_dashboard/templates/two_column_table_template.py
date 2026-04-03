"""Two-column table template -- copy and adapt for new game dashboards.

Pattern: Vertical container with side-by-side data displayed using
Static widgets (not two DataTables).  A header row labels both columns,
then N data rows each show left-side and right-side entries inline.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_best_plays.py
  - maxpane_dashboard/widgets/cattown/ct_best_plays.py
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_NUM_ROWS = 5


def _truncate(name: str, width: int = 15) -> str:
    """Truncate a name and pad/clip to width."""
    if len(name) > width:
        return name[: width - 1] + "."
    return name.ljust(width)


class GameBestPlays(Vertical):
    """Side-by-side tables showing two ranked lists.

    Rename for your game, e.g. ``CTBestPlays``, ``DOTABestPlays``.
    Adjust the header labels, row count, and update_data() parameters.
    """

    DEFAULT_CSS = """
    GameBestPlays > .ev-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    GameBestPlays > .ev-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("BEST PLAYS", classes="ev-title")
        yield Static("", classes="ev-body")
        yield Static(
            f"  {'Left Column':<14} {'Value':>10}    {'Right Column':<14} {'Value':>8}",
            classes="ev-body",
            id="game-bp-header",
        )
        yield Static("", classes="ev-body")
        for i in range(_NUM_ROWS):
            default_text = "[dim]  Loading...[/]" if i == 0 else ""
            yield Static(default_text, classes="ev-body", id=f"game-bp-row-{i}")

    def update_data(
        self,
        left_entries: list[tuple[str, str]] | None = None,
        right_entries: list[tuple[str, str]] | None = None,
    ) -> None:
        """Show ranked entries in two columns.

        Each entry is ``(name, formatted_value)``.
        Adapt column semantics to your game.
        """
        left = left_entries or []
        right = right_entries or []

        for i in range(_NUM_ROWS):
            widget = self.query_one(f"#game-bp-row-{i}", Static)

            # Left side
            if i < len(left):
                l_name, l_value = left[i]
                star = "[yellow]\u2605[/] " if i == 0 else "  "
                l_name_str = _truncate(l_name, 14)
                l_value_str = f"[green]{l_value:>10}[/]"
            else:
                star = "  "
                l_name_str = " " * 14
                l_value_str = " " * 10

            # Right side
            if i < len(right):
                r_name, r_value = right[i]
                r_star = "[yellow]\u2605[/] " if i == 0 else "  "
                r_name_str = _truncate(r_name, 14)
                r_value_str = f"[green]{r_value:>8}[/]"
            else:
                r_star = "  "
                r_name_str = ""
                r_value_str = ""

            widget.update(
                f"{star}{l_name_str} {l_value_str}  {r_star}{r_name_str} {r_value_str}"
            )
