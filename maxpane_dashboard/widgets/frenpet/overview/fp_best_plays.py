"""Top earners and rising stars tables for the FrenPet Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _truncate(name: str, width: int = 15) -> str:
    """Truncate a name and pad/clip to width."""
    if len(name) > width:
        return name[: width - 1] + "."
    return name.ljust(width)


class FPBestPlays(Vertical):
    """Side-by-side tables showing top earners and rising stars."""

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
            f"  {'Top Earners':<14} {'Score':>10}    {'Rising Stars':<14} {'ATK+DEF':>8}",
            classes="fpo-bp-body",
            id="fpo-bp-header",
        )
        yield Static("", classes="fpo-bp-body")
        yield Static("[dim]  Loading...[/]", classes="fpo-bp-body", id="fpo-bp-row-0")
        yield Static("", classes="fpo-bp-body", id="fpo-bp-row-1")
        yield Static("", classes="fpo-bp-body", id="fpo-bp-row-2")

    def update_data(
        self,
        top_earners: list[tuple[str, str]],
        rising_stars: list[tuple[str, str]],
    ) -> None:
        """Show top 3 earners by score and top 3 rising stars by ATK+DEF."""
        for i in range(3):
            widget = self.query_one(f"#fpo-bp-row-{i}", Static)

            # Earner side
            if i < len(top_earners):
                e_name, e_value = top_earners[i]
                star = "[yellow]\u2605[/] " if i == 0 else "  "
                e_name_str = _truncate(e_name, 14)
                e_value_str = f"[green]{e_value:>10}[/]"
            else:
                star = "  "
                e_name_str = " " * 14
                e_value_str = " " * 10

            # Rising star side
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
