"""Top fighters and most active tables for the FrenPet Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_NUM_ROWS = 10


def _truncate(name: str, width: int = 15) -> str:
    """Truncate a name and pad/clip to width."""
    if len(name) > width:
        return name[: width - 1] + "."
    return name.ljust(width)


class FPBestPlays(Vertical):
    """Side-by-side tables showing top fighters (by win rate) and most active (by battles)."""

    DEFAULT_CSS = """
    FPBestPlays > .fpo-bp-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPBestPlays > .fpo-bp-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("BEST PLAYS", classes="fpo-bp-title")
        yield Static("", classes="fpo-bp-body")
        yield Static(
            f"  {'Top Fighters':<14} {'Win %':>10}    {'Most Active':<14} {'Battles':>8}",
            classes="fpo-bp-body",
            id="fpo-bp-header",
        )
        yield Static("", classes="fpo-bp-body")
        for i in range(_NUM_ROWS):
            default_text = "[dim]  Loading...[/]" if i == 0 else ""
            yield Static(default_text, classes="fpo-bp-body", id=f"fpo-bp-row-{i}")

    def update_data(
        self,
        top_earners: list[tuple[str, str]],
        rising_stars: list[tuple[str, str]],
    ) -> None:
        """Show top 10 fighters by win rate and top 10 most active by battle count."""
        for i in range(_NUM_ROWS):
            widget = self.query_one(f"#fpo-bp-row-{i}", Static)

            # Fighter side (top_earners = by win rate, min 10 battles)
            if i < len(top_earners):
                e_name, e_value = top_earners[i]
                star = "[yellow]\u2605[/] " if i == 0 else "  "
                e_name_str = _truncate(e_name, 14)
                e_value_str = f"[green]{e_value:>10}[/]"
            else:
                star = "  "
                e_name_str = " " * 14
                e_value_str = " " * 10

            # Most active side (rising_stars = by battle count)
            if i < len(rising_stars):
                r_name, r_value = rising_stars[i]
                r_star = "[yellow]\u2605[/] " if i == 0 else "  "
                r_name_str = _truncate(r_name, 14)
                r_value_str = f"[green]{r_value:>8}[/]"
            else:
                r_star = "  "
                r_name_str = ""
                r_value_str = ""

            widget.update(
                f"{star}{e_name_str} {e_value_str}  {r_star}{r_name_str} {r_value_str}"
            )
