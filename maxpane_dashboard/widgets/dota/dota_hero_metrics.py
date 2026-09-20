"""Hero metric boxes for the Defense of the Agents dashboard.

Every box is written on every ``update_data`` call (MEDI-38, the rule the
hero shape states): a value the manager could not read arrives as ``None``
and renders an explicit ``unavailable`` marker instead of the
"Loading..." the old copy showed forever; a real ``0`` market cap renders
as ``$0``.

The row itself, the boxes' seed text and the build-inside-the-guard write
are :class:`~maxpane_dashboard.widgets.panels.HeroRow`'s (Branch 7, WP-A).
"""

from __future__ import annotations

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow


def _fmt_usd(value: float) -> str:
    """A USD amount with a K/M suffix. One user -- this module's token box.

    Not ``sparkline_common.fmt_compact``: that one has no ``$`` and gains a
    ``B`` suffix, and a market cap's digits are a pixel this branch does not
    move.
    """
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


class DOTAHeroBox(HeroBoxBase):
    """A single hero metric box with label and value.

    Kept as its own class because ``minimal.tcss`` names ``DOTAHeroBox`` for
    this dashboard's box geometry, as does the MEDI-38 harness CSS.
    """


class DOTAHeroMetrics(HeroRow):
    """Row of hero metric boxes: Faction Lead, Base HP, Token Price, Top Player."""

    BOX_CLASS = DOTAHeroBox

    BOXES = (
        ("dota-hero-faction", "FACTION LEAD"),
        ("dota-hero-basehp", "BASE HP"),
        ("dota-hero-token", "$DOTA TOKEN"),
        ("dota-hero-top", "TOP PLAYER"),
    )

    def update_data(
        self,
        winning_faction: str | None = "tied",
        human_base_hp: int | None = 0,
        orc_base_hp: int | None = 0,
        base_max_hp: int | None = None,
        winner: str | None = None,
        # Unused by any box -- the token box shows the market cap, not the
        # price -- but `screens/dota.py`'s PANELS row sends it, and the
        # agreement test in `tests/screens/test_dashboard_screen.py` requires
        # every key it sends to be a *named* parameter here. Dropping the
        # parameter without dropping the key would redden that test.
        token_price_usd: float | None = None,
        token_price_change_24h: float | None = None,
        token_market_cap: float | None = None,
        top_player_name: str | None = "",
        top_player_wins: int | None = 0,
        top_player_win_rate: float | None = 0.0,
        **_kwargs,
    ) -> None:
        """Refresh all hero boxes; a missing value says so."""
        self.render_box(
            "#dota-hero-faction", "FACTION LEAD",
            lambda: self._faction_body(winning_faction, winner),
        )
        self.render_box(
            "#dota-hero-basehp", "BASE HP",
            lambda: self._hp_body(human_base_hp, orc_base_hp, base_max_hp),
        )
        self.render_box(
            "#dota-hero-token", "$DOTA TOKEN",
            lambda: self._token_body(token_market_cap, token_price_change_24h),
        )
        self.render_box(
            "#dota-hero-top", "TOP PLAYER",
            lambda: self._top_body(top_player_name, top_player_wins,
                                   top_player_win_rate),
        )

    # -- box bodies -------------------------------------------------------

    @staticmethod
    def _faction_body(winning_faction, winner) -> str:
        if winner:
            return (
                f"[bold yellow]GAME OVER[/]\n"
                f"[dim]{safe_markup(str(winner).upper())} wins[/]"
            )
        if winning_faction is None:
            return UNAVAILABLE
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
            return UNAVAILABLE
        human_pct = f"{human_base_hp / base_max_hp * 100:.0f}%" if base_max_hp else "?"
        orc_pct = f"{orc_base_hp / base_max_hp * 100:.0f}%" if base_max_hp else "?"
        return (
            f"[cyan]H: {human_base_hp:,}/{base_max_hp:,}[/] [dim]({human_pct})[/]\n"
            f"[red]O: {orc_base_hp:,}/{base_max_hp:,}[/] [dim]({orc_pct})[/]"
        )

    @staticmethod
    def _token_body(token_market_cap, token_price_change_24h) -> str:
        if token_market_cap is None:
            return UNAVAILABLE
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
            return UNAVAILABLE
        wins = "?" if top_player_wins is None else f"{top_player_wins}"
        rate = "?" if top_player_win_rate is None else f"{top_player_win_rate:.0f}%"
        return (
            f"[bold white]{safe_markup(top_player_name)}[/]\n"
            f"[dim]{wins}W · {rate} WR[/]"
        )
