"""Hero metric boxes displayed across the top of the bakery dashboard.

On ``widgets/panels.py`` since Branch 8 WP-B: :class:`HeroMetrics` is a
:class:`~maxpane_dashboard.widgets.panels.HeroRow` and each box body is
built inside :meth:`~maxpane_dashboard.widgets.panels.HeroRow.render_box`'s
guard, so a field the backend could not supply renders an explicit
``unavailable`` marker and a box that fails outright still says so rather
than sitting on a stale value or on ``Loading...`` forever (MEDI-38).
"""

from __future__ import annotations

from maxpane_dashboard.analytics.leaderboard import format_cookies
from maxpane_dashboard.analytics.production import format_rate
from maxpane_dashboard.widgets.fmt import as_float
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow

#: Seasons run about thirty days; the countdown bar is drawn against that.
_SEASON_HOURS = 30 * 24
#: Cells in the countdown's progress bar.
_BAR_CELLS = 12


class HeroBox(HeroBoxBase):
    """Bakery's hero box.

    A class of its own, not the base directly, because ``minimal.tcss`` has
    a bare ``HeroBox { ... }`` block that states this dashboard's geometry
    (``width: 1fr``, ``height: 7``, the border) and must keep matching it --
    and must **not** reach any other dashboard's boxes, which is why the base
    is called ``HeroBoxBase`` (``tests/widgets/test_panels.py``).
    """


class HeroMetrics(HeroRow):
    """Row of three hero metric boxes: Prize Pool, Season Countdown, Leader."""

    BOX_CLASS = HeroBox

    BOXES = (
        ("hero-prize", "PRIZE POOL"),
        ("hero-countdown", "SEASON COUNTDOWN"),
        ("hero-leader", "LEADER"),
    )

    def update_data(
        self,
        prize_pool_eth: float,
        prize_pool_usd: float,
        hours_remaining: float,
        season_id: int,
        season_active: bool,
        leader_name: str,
        leader_cookies: float,
        leader_rate: float,
    ) -> None:
        """Refresh all three hero boxes with live values.

        Each box is rendered independently: one bad field degrades its own
        box and the other two still land. No exception leaves this method.
        """
        self.render_box(
            "#hero-prize", "PRIZE POOL",
            lambda: self._prize_body(prize_pool_eth, prize_pool_usd),
        )
        # The countdown box's *label* is the season number once the season has
        # ended -- computed outside the guard, so a failed hours read under an
        # ended season still shows the label the copy showed.
        season_label = "SEASON" if season_id is None else f"SEASON {season_id}"
        self.render_box(
            "#hero-countdown",
            "SEASON COUNTDOWN" if season_active else season_label,
            lambda: self._countdown_body(hours_remaining, season_label, season_active),
        )
        self.render_box(
            "#hero-leader", "LEADER",
            lambda: self._leader_body(leader_name, leader_cookies, leader_rate),
        )

    # -- box bodies -----------------------------------------------------------

    @staticmethod
    def _prize_body(prize_pool_eth, prize_pool_usd) -> str:
        eth = as_float(prize_pool_eth)
        usd = as_float(prize_pool_usd)
        eth_str = f"{eth:.2f} ETH" if eth is not None else UNAVAILABLE
        usd_str = f"${usd:,.0f}" if usd is not None else UNAVAILABLE
        if eth is None:
            return f"{UNAVAILABLE}\n[dim]{usd_str}[/]"
        return f"[bold white]{eth_str}[/]\n[dim]{usd_str}[/]"

    @staticmethod
    def _countdown_body(hours_remaining, season_label: str, season_active) -> str:
        if not season_active:
            return "[bold yellow]Season Ended[/]"

        hours = as_float(hours_remaining)
        if hours is None:
            return f"{UNAVAILABLE}\n[dim]{season_label}[/]"

        total_seconds = int(hours * 3600)
        days = total_seconds // 86400
        rem_hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        countdown_str = f"{days}d {rem_hours}h {minutes}m"

        elapsed_fraction = max(0.0, min(1.0, 1.0 - hours / _SEASON_HOURS))
        filled = int(elapsed_fraction * _BAR_CELLS)
        bar = "█" * filled + "░" * (_BAR_CELLS - filled)
        pct = int(elapsed_fraction * 100)
        return f"[bold white]{countdown_str}[/]\n[dim]{bar} {pct}%[/]"

    @staticmethod
    def _leader_body(leader_name, leader_cookies, leader_rate) -> str:
        cookies = as_float(leader_cookies)
        rate = as_float(leader_rate)
        cookies_str = (
            f"{format_cookies(cookies)} cookies" if cookies is not None else UNAVAILABLE
        )
        rate_str = format_rate(rate) if rate is not None else "--/hr"
        # Player-chosen: escape before it reaches markup rendering.
        name = safe_markup(leader_name) or "[dim]unknown[/]"
        return f"[bold white]{cookies_str}[/]\n[dim]{name}  {rate_str}[/]"
