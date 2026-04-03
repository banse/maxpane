"""Hero metrics template -- copy and adapt for new game dashboards.

Pattern: Horizontal row of three hero boxes (Static widgets) displaying
key top-level metrics.  Each box has a dim label, bold value, and dim
subtitle.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_hero_metrics.py
  - maxpane_dashboard/widgets/cattown/ct_hero_metrics.py
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class GameHeroBox(Static):
    """A single hero metric box with label and value.

    Rename for your game, e.g. ``CTHeroBox``, ``DOTAHeroBox``.
    """

    DEFAULT_CSS = ""


class GameHeroMetrics(Horizontal):
    """Row of three hero metric boxes.

    Rename for your game, e.g. ``CTHeroMetrics``, ``DOTAHeroMetrics``.
    Update compose() box IDs and update_data() parameters.
    """

    DEFAULT_CSS = """
    GameHeroMetrics > GameHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield GameHeroBox(
            "[dim]METRIC ONE[/]\n\n"
            "[dim]Loading...[/]",
            id="game-hero-one",
        )
        yield GameHeroBox(
            "[dim]METRIC TWO[/]\n\n"
            "[dim]Loading...[/]",
            id="game-hero-two",
        )
        yield GameHeroBox(
            "[dim]LEADER[/]\n\n"
            "[dim]Loading...[/]",
            id="game-hero-leader",
        )

    def update_data(
        self,
        metric_one_value: str = "",
        metric_one_subtitle: str = "",
        metric_two_value: str = "",
        metric_two_subtitle: str = "",
        leader_name: str = "",
        leader_subtitle: str = "",
    ) -> None:
        """Refresh all three hero boxes with live values.

        Adapt parameters to your game's key metrics.
        """
        # -- Metric One --
        box1 = self.query_one("#game-hero-one", GameHeroBox)
        if metric_one_value:
            box1.update(
                f"[dim]METRIC ONE[/]\n\n"
                f"[bold white]{metric_one_value}[/]\n"
                f"[dim]{metric_one_subtitle}[/]"
            )

        # -- Metric Two --
        box2 = self.query_one("#game-hero-two", GameHeroBox)
        if metric_two_value:
            box2.update(
                f"[dim]METRIC TWO[/]\n\n"
                f"[bold white]{metric_two_value}[/]\n"
                f"[dim]{metric_two_subtitle}[/]"
            )

        # -- Leader --
        box3 = self.query_one("#game-hero-leader", GameHeroBox)
        if leader_name:
            box3.update(
                f"[dim]LEADER[/]\n\n"
                f"[bold white]{leader_name}[/]\n"
                f"[dim]{leader_subtitle}[/]"
            )
        else:
            box3.update(
                "[dim]LEADER[/]\n\n"
                "[dim]No data[/]"
            )
