"""Expected-value tables for boosts and attacks."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _fmt_ev(value: float) -> str:
    """Format an EV value with color and sign."""
    if value >= 0:
        return f"[green]+{value:,.0f}[/]"
    return f"[red]{value:,.0f}[/]"


def _fmt_ratio(value: float) -> str:
    """Format a gap-closure ratio with color."""
    if value > 0:
        return f"[green]{value:.1f}x[/]"
    return f"[dim]0.0x[/]"


def _truncate(name: str, width: int = 15) -> str:
    """Truncate a name and pad/clip to width."""
    if len(name) > width:
        return name[: width - 1] + "."
    return name.ljust(width)


class EVTable(Vertical):
    """Side-by-side tables showing best boost and attack plays."""

    DEFAULT_CSS = """
    EVTable > .ev-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    EVTable > .ev-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("BEST PLAYS", classes="ev-title")
        yield Static("", classes="ev-body")
        yield Static(
            f"  {'Boosts':<14} {'EV':>10}    {'Attacks':<14} {'Gap':>8}",
            classes="ev-body",
            id="ev-header",
        )
        yield Static("", classes="ev-body")
        yield Static("[dim]  Loading...[/]", classes="ev-body", id="ev-row-0")
        yield Static("", classes="ev-body", id="ev-row-1")
        yield Static("", classes="ev-body", id="ev-row-2")

    def update_data(
        self,
        boost_rankings: list[tuple[str, float]],
        attack_rankings: list[tuple[str, float]],
    ) -> None:
        """Show top 3 boosts by EV and top 3 attacks by gap-closure ratio."""
        for i in range(3):
            widget = self.query_one(f"#ev-row-{i}", Static)

            # Boost side
            if i < len(boost_rankings):
                b_name, b_ev = boost_rankings[i]
                star = "[yellow]\u2605[/] " if i == 0 else "  "
                b_name_str = _truncate(b_name, 14)
                b_ev_raw = f"+{b_ev:,.0f}" if b_ev >= 0 else f"{b_ev:,.0f}"
                b_ev_str = f"[green]{b_ev_raw:>10}[/]" if b_ev >= 0 else f"[red]{b_ev_raw:>10}[/]"
            else:
                star = "  "
                b_name_str = " " * 14
                b_ev_str = " " * 10

            # Attack side
            if i < len(attack_rankings):
                a_name, a_ratio = attack_rankings[i]
                a_star = "[yellow]\u2605[/] " if i == 0 else "  "
                a_name_str = _truncate(a_name, 14)
                a_ratio_raw = f"{a_ratio:.1f}x"
                a_ratio_str = f"[green]{a_ratio_raw:>8}[/]" if a_ratio > 0 else f"[dim]{a_ratio_raw:>8}[/]"
            else:
                a_star = "  "
                a_name_str = ""
                a_ratio_str = ""

            widget.update(
                f"{star}{b_name_str} {b_ev_str}  {a_star}{a_name_str} {a_ratio_str}"
            )
