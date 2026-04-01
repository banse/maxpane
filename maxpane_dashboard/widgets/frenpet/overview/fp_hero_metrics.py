"""Hero metric boxes for the FrenPet Overview view."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class FPHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class FPOverviewHero(Horizontal):
    """Row of three hero metric boxes: Players Treasure, Playing Since, Leader."""

    DEFAULT_CSS = """
    FPOverviewHero > FPHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield FPHeroBox(
            "[dim]PLAYERS TREASURE[/]\n\n"
            "[dim]Loading...[/]",
            id="fpo-hero-treasure",
        )
        yield FPHeroBox(
            "[dim]PLAYING SINCE[/]\n\n"
            "[dim]Loading...[/]",
            id="fpo-hero-since",
        )
        yield FPHeroBox(
            "[dim]LEADER[/]\n\n"
            "[dim]Loading...[/]",
            id="fpo-hero-leader",
        )

    def update_data(
        self,
        fp_reward_pool: float | int,
        game_start_timestamp: int,
        top_pet: object | None,
    ) -> None:
        """Refresh all three hero boxes with live values."""
        # -- Players Treasure --
        treasure_box = self.query_one("#fpo-hero-treasure", FPHeroBox)
        pool_str = f"{int(fp_reward_pool):,} FP"
        treasure_box.update(
            f"[dim]PLAYERS TREASURE[/]\n\n"
            f"[bold white]{pool_str}[/]\n"
            f"[dim]in reward pool[/]"
        )

        # -- Playing Since --
        since_box = self.query_one("#fpo-hero-since", FPHeroBox)
        now = time.time()
        elapsed = max(0, now - game_start_timestamp)
        years = int(elapsed // (365.25 * 86400))
        months = int((elapsed % (365.25 * 86400)) // (30.44 * 86400))
        since_str = f"{years}y {months}m"
        since_box.update(
            f"[dim]PLAYING SINCE[/]\n\n"
            f"[bold white]{since_str}[/]\n"
            f"[dim]Base L2[/]"
        )

        # -- Leader --
        leader_box = self.query_one("#fpo-hero-leader", FPHeroBox)
        if top_pet is not None:
            pet_id = getattr(top_pet, "id", "?")
            score = float(getattr(top_pet, "score", 0))
            atk = getattr(top_pet, "attack_points", 0)

            # Format score with M/B suffix
            if score >= 1_000_000_000:
                score_str = f"{score / 1_000_000_000:.1f}B"
            elif score >= 1_000_000:
                score_str = f"{score / 1_000_000:.1f}M"
            elif score >= 1_000:
                score_str = f"{score / 1_000:.1f}K"
            else:
                score_str = f"{score:,.0f}"

            leader_box.update(
                f"[dim]LEADER[/]\n\n"
                f"[bold white]Pet #{pet_id}[/]\n"
                f"[dim]{score_str} pts \u00b7 ATK {atk}[/]"
            )
        else:
            leader_box.update(
                f"[dim]LEADER[/]\n\n"
                f"[dim]No data[/]"
            )
