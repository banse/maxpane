"""Hero metric boxes for the Defense of the Agents dashboard.

Every box is written on every ``update_data`` call (MEDI-38, the rule the
hero template states): a value the manager could not read arrives as
``None`` and renders an explicit ``unavailable`` marker instead of the
"Loading..." the old copy showed forever; a real ``0`` market cap renders
as ``$0``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Shown in place of a value the backend could not supply this poll.
_UNAVAILABLE = "[yellow]unavailable[/]"


def _fmt_usd(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


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
        winning_faction: str | None = "tied",
        human_base_hp: int | None = 0,
        orc_base_hp: int | None = 0,
        base_max_hp: int | None = None,
        winner: str | None = None,
        token_price_usd: float | None = None,
        token_price_change_24h: float | None = None,
        token_market_cap: float | None = None,
        top_player_name: str | None = "",
        top_player_wins: int | None = 0,
        top_player_win_rate: float | None = 0.0,
        **_kwargs,
    ) -> None:
        """Refresh all hero boxes; a missing value says so."""
        self._render_box("#dota-hero-faction", "FACTION LEAD",
                         self._faction_body, winning_faction, winner)
        self._render_box("#dota-hero-basehp", "BASE HP",
                         self._hp_body, human_base_hp, orc_base_hp, base_max_hp)
        self._render_box("#dota-hero-token", "$DOTA TOKEN",
                         self._token_body, token_market_cap, token_price_change_24h)
        self._render_box("#dota-hero-top", "TOP PLAYER",
                         self._top_body, top_player_name, top_player_wins,
                         top_player_win_rate)

    # -- box bodies -------------------------------------------------------

    @staticmethod
    def _faction_body(winning_faction, winner) -> str:
        if winner:
            return (
                f"[bold yellow]GAME OVER[/]\n"
                f"[dim]{safe_markup(str(winner).upper())} wins[/]"
            )
        if winning_faction is None:
            return _UNAVAILABLE
        if winning_faction == "tied":
            return "[bold white]TIED[/]\n[dim]even match[/]"
        color = "cyan" if winning_faction == "human" else "red"
        return (
            f"[bold {color}]{safe_markup(str(winning_faction).upper())}[/]\n"
            f"[dim]leading[/]"
        )

    @staticmethod
    def _hp_body(human_base_hp, orc_base_hp, base_max_hp) -> str:
        if base_max_hp is None or human_base_hp is None or orc_base_hp is None:
            return _UNAVAILABLE
        human_pct = f"{human_base_hp / base_max_hp * 100:.0f}%" if base_max_hp else "?"
        orc_pct = f"{orc_base_hp / base_max_hp * 100:.0f}%" if base_max_hp else "?"
        return (
            f"[cyan]H: {human_base_hp:,}/{base_max_hp:,}[/] [dim]({human_pct})[/]\n"
            f"[red]O: {orc_base_hp:,}/{base_max_hp:,}[/] [dim]({orc_pct})[/]"
        )

    @staticmethod
    def _token_body(token_market_cap, token_price_change_24h) -> str:
        if token_market_cap is None:
            return _UNAVAILABLE
        change_str = ""
        if token_price_change_24h is not None:
            arrow = "▲" if token_price_change_24h >= 0 else "▼"
            color = "green" if token_price_change_24h >= 0 else "red"
            change_str = f"[{color}]{arrow} {abs(token_price_change_24h):.1f}%[/]"
        return (
            f"[bold white]{_fmt_usd(token_market_cap)}[/]\n"
            f"[dim]mcap[/] {change_str}"
        )

    @staticmethod
    def _top_body(top_player_name, top_player_wins, top_player_win_rate) -> str:
        if not top_player_name:
            return _UNAVAILABLE
        wins = "?" if top_player_wins is None else f"{top_player_wins}"
        rate = "?" if top_player_win_rate is None else f"{top_player_win_rate:.0f}%"
        return (
            f"[bold white]{safe_markup(top_player_name)}[/]\n"
            f"[dim]{wins}W · {rate} WR[/]"
        )

    def _render_box(self, selector: str, label: str, build, *args) -> None:
        """Write one box, degrading to an explicit unavailable state.

        The body is built inside the guard: a malformed value (a string
        where a number was expected) must land on ``unavailable`` here, not
        raise into the screen's ``except`` and leave the previous poll's
        number on screen as if it were live.
        """
        try:
            box = self.query_one(selector, DOTAHeroBox)
        except Exception:
            return
        try:
            box.update(f"[dim]{label}[/]\n\n{build(*args)}")
        except Exception:
            try:
                box.update(f"[dim]{label}[/]\n\n{_UNAVAILABLE}")
            except Exception:
                pass
