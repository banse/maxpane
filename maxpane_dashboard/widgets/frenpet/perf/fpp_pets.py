"""Pet comparison table for the FrenPet Performance view."""

from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

# Strip emoji and other non-BMP characters that cause terminal width issues
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"  # Misc symbols, emoticons, etc.
    "\U00002702-\U000027b0"  # Dingbats
    "\U0000fe00-\U0000fe0f"  # Variation selectors
    "\U0000200d"             # Zero-width joiner
    "\U000020e3"             # Combining enclosing keycap
    "]+",
    flags=re.UNICODE,
)


def _fmt_score(score: float) -> str:
    """Format score with K/M/B suffix."""
    if score >= 1_000_000_000:
        return f"{score / 1_000_000_000:.1f}B"
    if score >= 1_000_000:
        return f"{score / 1_000_000:.1f}M"
    if score >= 1_000:
        return f"{score / 1_000:.1f}K"
    return f"{score:,.0f}"


def _velocity_color(velocity: float) -> str:
    """Return color name based on velocity magnitude."""
    if velocity >= 200:
        return "green"
    if velocity >= 100:
        return "cyan"
    if velocity >= 50:
        return "yellow"
    return "dim"


class FPPerfPets(Vertical):
    """Pet comparison table with score, win rate, ATK/DEF, and velocity."""

    DEFAULT_CSS = """
    FPPerfPets > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPPerfPets > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("PET COMPARISON", classes="fpp-pets-title")
        table = DataTable(id="fpp-pets-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#fpp-pets-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Name", width=16)
        table.add_column("Score", width=12)
        table.add_column("Win Rate", width=10)
        table.add_column("ATK/DEF", width=12)
        table.add_column("Velocity", width=10)

    def update_data(
        self,
        pets: list,
        pet_velocities: dict[int, float] | None = None,
    ) -> None:
        """Clear and repopulate the pet comparison table."""
        table = self.query_one("#fpp-pets-table", DataTable)
        table.clear()

        velocities = pet_velocities or {}

        if not pets:
            table.add_row("--", "No pets", "--", "--", "--", "--")
            return

        # Sort by score descending
        sorted_pets = sorted(
            pets,
            key=lambda p: p.get("score", 0),
            reverse=True,
        )

        for idx, pet in enumerate(sorted_pets, start=1):
            raw_name = pet.get("name", "") or f"#{pet.get('id', '?')}"
            pet_name = _EMOJI_RE.sub("", raw_name).strip()
            if not pet_name:
                pet_name = f"#{pet.get('id', '?')}"

            score = float(pet.get("score", 0))
            wins = pet.get("wins", pet.get("win_qty", 0))
            losses = pet.get("losses", pet.get("loss_qty", 0))
            atk = pet.get("atk", pet.get("attack_points", 0))
            defense = pet.get("def", pet.get("defense_points", 0))

            # Win rate
            total_battles = wins + losses
            win_rate = (wins / total_battles * 100) if total_battles > 0 else 0.0

            # Velocity
            pet_id = pet.get("id", 0)
            velocity = velocities.get(int(pet_id), 0.0)

            score_str = _fmt_score(score)
            wr_str = f"{win_rate:.1f}%"
            atk_def_str = f"{atk}/{defense}"
            vel_color = _velocity_color(velocity)
            vel_str = f"[{vel_color}]+{velocity:,.0f}/hr[/]"

            # Star marker + bold for top pet
            if idx == 1:
                rank_str = "\u2605"
                name_str = f"[bold]{pet_name}[/]"
                score_str = f"[bold]{score_str}[/]"
            else:
                rank_str = str(idx)
                name_str = pet_name

            table.add_row(
                rank_str,
                name_str,
                score_str,
                wr_str,
                atk_def_str,
                vel_str,
            )
