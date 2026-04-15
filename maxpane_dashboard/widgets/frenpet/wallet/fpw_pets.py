"""Pet table for the FrenPet Wallet view."""

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


def _fmt_eth(wei: int) -> str:
    """Format wei to ETH with 3-4 decimal places."""
    eth = wei / 1e18
    if eth >= 0.1:
        return f"{eth:.3f}"
    return f"{eth:.4f}"


class FPWalletPets(Vertical):
    """Pet table panel with DataTable of wallet pets."""

    DEFAULT_CSS = """
    FPWalletPets > Static {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPWalletPets > DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("PETS", classes="fpw-pets-title")
        table = DataTable(id="fpw-pets-table")
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#fpw-pets-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("#", width=4)
        table.add_column("Name", width=16)
        table.add_column("Score", width=12)
        table.add_column("W/L", width=12)
        table.add_column("ATK/DEF", width=12)
        table.add_column("ETH", width=8)

    def update_data(self, pets: list) -> None:
        """Clear and repopulate the pet table with live data."""
        table = self.query_one("#fpw-pets-table", DataTable)
        table.clear()

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
            wins = pet.get("wins", 0)
            losses = pet.get("losses", 0)
            atk = pet.get("atk", pet.get("attack_points", 0))
            defense = pet.get("def", pet.get("defense_points", 0))
            pending_eth_wei = pet.get("pending_eth_wei", 0)

            score_str = _fmt_score(score)
            wl_str = f"{wins}/{losses}"
            atk_def_str = f"{atk}/{defense}"
            eth_str = _fmt_eth(pending_eth_wei)

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
                wl_str,
                atk_def_str,
                eth_str,
            )
