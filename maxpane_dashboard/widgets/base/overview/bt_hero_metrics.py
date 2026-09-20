"""Hero metric boxes for the Base Trading Overview view.

The row, the boxes' ``Loading...`` seed and the build-inside-the-guard write
are :class:`~maxpane_dashboard.widgets.panels.HeroRow`'s (Branch 8, WP-A).
What stays here is what only this dashboard knows: the four bodies, and
their own words for a value that is *absent* rather than *failed* --
``...`` for a price, change or volume the manager omitted this poll, and
``No data`` for a top gainer when no token moved, which is the copy's own
text for a real negative and not the base's ``unavailable``. The
``unavailable`` marker is what a body that *raises* lands on (MEDI-38),
which no body here did before and every body now can.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import HeroBoxBase, HeroRow


class BTHeroBox(HeroBoxBase):
    """A single hero metric box with label and value.

    Kept as its own class because ``minimal.tcss`` names ``BTHeroBox`` for
    this dashboard's box geometry.
    """


def _price_body(eth_price) -> str:
    if eth_price is None:
        return "[bold white]...[/]"
    try:
        price_str = f"${float(eth_price):,.2f}"
    except (ValueError, TypeError):
        # The manager hands the title bar's own string on the sweep payload
        # (``$3,000``); a string that is not a number is shown as it came.
        price_str = safe_markup(str(eth_price))
    return f"[bold white]{price_str}[/]"


def _change_body(eth_change_24h) -> str:
    if eth_change_24h is None:
        return "[bold][dim]...[/][/]"
    try:
        change_val = float(eth_change_24h)
    except (ValueError, TypeError):
        return f"[bold]{safe_markup(str(eth_change_24h))}[/]"
    if change_val >= 0:
        return f"[bold][green]+{change_val:.2f}%[/][/]"
    return f"[bold][red]{change_val:.2f}%[/][/]"


def _volume_body(total_volume) -> str:
    if total_volume is None:
        return "[bold white]...[/]"
    try:
        vol = float(total_volume)
    except (ValueError, TypeError):
        return f"[bold white]{safe_markup(str(total_volume))}[/]"
    if vol >= 1_000_000_000:
        vol_str = f"${vol / 1_000_000_000:.1f}B"
    elif vol >= 1_000_000:
        vol_str = f"${vol / 1_000_000:.1f}M"
    elif vol >= 1_000:
        vol_str = f"${vol / 1_000:.1f}K"
    else:
        vol_str = f"${vol:,.0f}"
    return f"[bold white]{vol_str}[/]"


def _gainer_body(top_gainer_name, top_gainer_pct) -> str:
    if not top_gainer_name:
        # A real negative -- no token moved -- in the copy's own words.
        return "[dim]No data[/]"
    try:
        pct_val = float(top_gainer_pct) if top_gainer_pct is not None else 0.0
        pct_str = f"+{pct_val:.1f}%"
    except (ValueError, TypeError):
        pct_str = safe_markup(str(top_gainer_pct)) if top_gainer_pct else "?"
    return (
        f"[bold white]{safe_markup(top_gainer_name)}[/]\n"
        f"[green]{pct_str}[/]"
    )


class BTOverviewHero(HeroRow):
    """Row of hero metric boxes: ETH Price, 24h Change, Volume, Top Gainer."""

    BOX_CLASS = BTHeroBox

    BOXES = (
        ("bto-hero-eth", "ETH PRICE"),
        ("bto-hero-change", "24H CHANGE"),
        ("bto-hero-volume", "VOLUME"),
        ("bto-hero-gainer", "TOP GAINER"),
    )

    def update_data(
        self,
        eth_price: float | str | None = None,
        eth_change_24h: float | str | None = None,
        total_volume: float | str | None = None,
        top_gainer_name: str | None = None,
        top_gainer_pct: float | str | None = None,
    ) -> None:
        """Refresh all hero boxes with live values."""
        self.render_box("#bto-hero-eth", "ETH PRICE",
                        lambda: _price_body(eth_price))
        self.render_box("#bto-hero-change", "24H CHANGE",
                        lambda: _change_body(eth_change_24h))
        self.render_box("#bto-hero-volume", "VOLUME",
                        lambda: _volume_body(total_volume))
        self.render_box("#bto-hero-gainer", "TOP GAINER",
                        lambda: _gainer_body(top_gainer_name, top_gainer_pct))
