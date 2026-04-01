"""Hero metric boxes for the Defense of the Agents dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class DOTAHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class DOTAHeroMetrics(Horizontal):
    """Row of hero metric boxes: Faction Lead, Base HP, Token Price, Top Player."""

    DEFAULT_CSS = """
    DOTAHeroMetrics > DOTAHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield DOTAHeroBox(
            "[dim]FACTION LEAD[/]\n\n"
            "[dim]Loading...[/]",
            id="dota-hero-faction",
        )
        yield DOTAHeroBox(
            "[dim]BASE HP[/]\n\n"
            "[dim]Loading...[/]",
            id="dota-hero-basehp",
        )
        yield DOTAHeroBox(
            "[dim]$DOTA TOKEN[/]\n\n"
            "[dim]Loading...[/]",
            id="dota-hero-token",
        )
        yield DOTAHeroBox(
            "[dim]TOP PLAYER[/]\n\n"
            "[dim]Loading...[/]",
            id="dota-hero-top",
        )

    def update_data(
        self,
        winning_faction: str = "tied",
        human_base_hp: int = 0,
        orc_base_hp: int = 0,
        base_max_hp: int = 0,
        winner: str | None = None,
        token_price_usd: float | None = None,
        token_price_change_24h: float | None = None,
        token_market_cap: float | None = None,
        top_player_name: str = "",
        top_player_wins: int = 0,
        top_player_win_rate: float = 0.0,
        **_kwargs,
    ) -> None:
        """Refresh all hero boxes with live values."""
        # -- Faction lead --
        faction_box = self.query_one("#dota-hero-faction", DOTAHeroBox)
        if winner:
            faction_box.update(
                f"[dim]FACTION LEAD[/]\n\n"
                f"[bold yellow]GAME OVER[/]\n"
                f"[dim]{winner.upper()} wins[/]"
            )
        elif winning_faction == "tied":
            faction_box.update(
                f"[dim]FACTION LEAD[/]\n\n"
                f"[bold white]TIED[/]\n"
                f"[dim]even match[/]"
            )
        else:
            color = "cyan" if winning_faction == "human" else "red"
            faction_box.update(
                f"[dim]FACTION LEAD[/]\n\n"
                f"[bold {color}]{winning_faction.upper()}[/]\n"
                f"[dim]leading[/]"
            )

        # -- Base HP --
        hp_box = self.query_one("#dota-hero-basehp", DOTAHeroBox)
        if base_max_hp > 0:
            human_pct = human_base_hp / base_max_hp * 100
            orc_pct = orc_base_hp / base_max_hp * 100
            hp_box.update(
                f"[dim]BASE HP[/]\n\n"
                f"[cyan]H: {human_base_hp:,}/{base_max_hp:,}[/] [dim]({human_pct:.0f}%)[/]\n"
                f"[red]O: {orc_base_hp:,}/{base_max_hp:,}[/] [dim]({orc_pct:.0f}%)[/]"
            )
        else:
            hp_box.update(
                "[dim]BASE HP[/]\n\n"
                "[dim]Loading...[/]"
            )

        # -- Token market cap --
        token_box = self.query_one("#dota-hero-token", DOTAHeroBox)
        if token_market_cap is not None and token_market_cap > 0:
            if token_market_cap >= 1_000_000:
                mcap_str = f"${token_market_cap / 1_000_000:.1f}M"
            elif token_market_cap >= 1_000:
                mcap_str = f"${token_market_cap / 1_000:.1f}K"
            else:
                mcap_str = f"${token_market_cap:,.0f}"
            change_str = ""
            if token_price_change_24h is not None:
                arrow = "\u25b2" if token_price_change_24h >= 0 else "\u25bc"
                color = "green" if token_price_change_24h >= 0 else "red"
                change_str = f"[{color}]{arrow} {abs(token_price_change_24h):.1f}%[/]"
            token_box.update(
                f"[dim]$DOTA TOKEN[/]\n\n"
                f"[bold white]{mcap_str}[/]\n"
                f"[dim]mcap[/] {change_str}"
            )
        else:
            token_box.update(
                "[dim]$DOTA TOKEN[/]\n\n"
                "[dim]Loading...[/]"
            )

        # -- Top player --
        top_box = self.query_one("#dota-hero-top", DOTAHeroBox)
        if top_player_name:
            top_box.update(
                f"[dim]TOP PLAYER[/]\n\n"
                f"[bold white]{top_player_name}[/]\n"
                f"[dim]{top_player_wins}W \u00b7 {top_player_win_rate:.0f}% WR[/]"
            )
        else:
            top_box.update(
                "[dim]TOP PLAYER[/]\n\n"
                "[dim]Loading...[/]"
            )
