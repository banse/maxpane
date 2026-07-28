"""Hero metrics template -- copy and adapt for new game dashboards.

Pattern: Horizontal row of three hero boxes (Static widgets) displaying
key top-level metrics.  Each box has a dim label, bold value, and dim
subtitle.

Reference implementations:
  - maxpane_dashboard/widgets/frenpet/overview/fp_hero_metrics.py
  - maxpane_dashboard/widgets/cattown/ct_hero_metrics.py

Keep the explicit unavailable state when you copy this (MEDI-38).  A box
that is skipped when its value is missing does not go blank -- it keeps
whatever it last showed, or "Loading..." forever if the first poll was the
one that failed, and the user cannot tell a stale number from a live one.
Values and subtitles are API-sourced, so they are escaped.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Shown in place of a value the backend could not supply this poll.
_UNAVAILABLE = "[yellow]unavailable[/]"


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

        Adapt parameters to your game's key metrics.  Every box is written
        on every call: a missing value renders an explicit unavailable
        marker rather than leaving the box on its previous contents.
        """
        self._render_box("#game-hero-one", "METRIC ONE",
                         metric_one_value, metric_one_subtitle)
        self._render_box("#game-hero-two", "METRIC TWO",
                         metric_two_value, metric_two_subtitle)
        self._render_box("#game-hero-leader", "LEADER",
                         leader_name, leader_subtitle)

    def _render_box(
        self, selector: str, label: str, value: str, subtitle: str
    ) -> None:
        """Write one box, degrading to an explicit unavailable state."""
        try:
            box = self.query_one(selector, GameHeroBox)
        except Exception:
            return
        try:
            body = (
                f"[bold white]{safe_markup(value)}[/]"
                if value
                else _UNAVAILABLE
            )
            box.update(
                f"[dim]{label}[/]\n\n{body}\n[dim]{safe_markup(subtitle)}[/]"
            )
        except Exception:
            try:
                box.update(f"[dim]{label}[/]\n\n{_UNAVAILABLE}")
            except Exception:
                pass
