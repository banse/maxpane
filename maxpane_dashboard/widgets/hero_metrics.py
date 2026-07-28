"""Hero metric boxes displayed across the top of the dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup

from maxpane_dashboard.analytics.leaderboard import format_cookies
from maxpane_dashboard.analytics.production import format_rate


#: Shown in place of a value the backend could not supply this poll.
_UNAVAILABLE = "[yellow]unavailable[/]"


def _num(value: object) -> float | None:
    """Return *value* as a finite float, or ``None`` if it is not one.

    The bakery tRPC API can return ``null`` for any of these fields (an
    inactive season, a failed sub-request), and a failed division upstream
    can produce ``NaN``/``inf``.  Both used to reach an f-string format
    spec and raise -- ``TypeError`` for ``None``, ``ValueError`` once
    ``int()`` saw the ``NaN`` -- which left the box frozen on
    "Loading..." for as long as the bad value persisted (MEDI-38).
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


class HeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class HeroMetrics(Horizontal):
    """Row of three hero metric boxes: Prize Pool, Season Countdown, Leader."""

    DEFAULT_CSS = """
    HeroMetrics > HeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield HeroBox(
            "[dim]PRIZE POOL[/]\n\n"
            "[dim]Loading...[/]",
            id="hero-prize",
        )
        yield HeroBox(
            "[dim]SEASON COUNTDOWN[/]\n\n"
            "[dim]Loading...[/]",
            id="hero-countdown",
        )
        yield HeroBox(
            "[dim]LEADER[/]\n\n"
            "[dim]Loading...[/]",
            id="hero-leader",
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

        Each box is rendered independently and defensively: a field the
        backend could not supply renders an explicit ``unavailable``
        marker, and a box that fails outright still says so rather than
        sitting on a stale value or on "Loading..." forever (MEDI-38).
        No exception leaves this method -- a raise here would abandon the
        remaining boxes mid-update.
        """
        self._update_prize(prize_pool_eth, prize_pool_usd)
        self._update_countdown(hours_remaining, season_id, season_active)
        self._update_leader(leader_name, leader_cookies, leader_rate)

    # -- individual boxes ---------------------------------------------------

    def _update_prize(self, prize_pool_eth: float, prize_pool_usd: float) -> None:
        try:
            eth = _num(prize_pool_eth)
            usd = _num(prize_pool_usd)
            eth_str = f"{eth:.2f} ETH" if eth is not None else _UNAVAILABLE
            usd_str = f"${usd:,.0f}" if usd is not None else _UNAVAILABLE
            body = (
                f"[bold white]{eth_str}[/]\n[dim]{usd_str}[/]"
                if eth is not None
                else f"{_UNAVAILABLE}\n[dim]{usd_str}[/]"
            )
            self.query_one("#hero-prize", HeroBox).update(
                f"[dim]PRIZE POOL[/]\n\n{body}"
            )
        except Exception:
            self._fail_box("#hero-prize", "PRIZE POOL")

    def _update_countdown(
        self, hours_remaining: float, season_id: int, season_active: bool
    ) -> None:
        try:
            countdown_box = self.query_one("#hero-countdown", HeroBox)
            season_label = "SEASON" if season_id is None else f"SEASON {season_id}"

            if not season_active:
                countdown_box.update(
                    f"[dim]{season_label}[/]\n\n[bold yellow]Season Ended[/]"
                )
                return

            hours = _num(hours_remaining)
            if hours is None:
                countdown_box.update(
                    f"[dim]SEASON COUNTDOWN[/]\n\n{_UNAVAILABLE}\n"
                    f"[dim]{season_label}[/]"
                )
                return

            total_seconds = int(hours * 3600)
            days = total_seconds // 86400
            rem_hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            countdown_str = f"{days}d {rem_hours}h {minutes}m"

            # Progress bar (assume ~30-day seasons)
            total_season_hours = 30 * 24
            elapsed_fraction = max(
                0.0, min(1.0, 1.0 - hours / total_season_hours)
            )
            filled = int(elapsed_fraction * 12)
            bar = "\u2588" * filled + "\u2591" * (12 - filled)
            pct = int(elapsed_fraction * 100)

            countdown_box.update(
                f"[dim]SEASON COUNTDOWN[/]\n\n"
                f"[bold white]{countdown_str}[/]\n"
                f"[dim]{bar} {pct}%[/]"
            )
        except Exception:
            self._fail_box("#hero-countdown", "SEASON COUNTDOWN")

    def _update_leader(
        self, leader_name: str, leader_cookies: float, leader_rate: float
    ) -> None:
        try:
            cookies = _num(leader_cookies)
            rate = _num(leader_rate)
            cookies_str = (
                f"{format_cookies(cookies)} cookies"
                if cookies is not None
                else _UNAVAILABLE
            )
            rate_str = format_rate(rate) if rate is not None else "--/hr"
            name = safe_markup(leader_name) or "[dim]unknown[/]"
            self.query_one("#hero-leader", HeroBox).update(
                f"[dim]LEADER[/]\n\n"
                f"[bold white]{cookies_str}[/]\n"
                f"[dim]{name}  {rate_str}[/]"
            )
        except Exception:
            self._fail_box("#hero-leader", "LEADER")

    def _fail_box(self, selector: str, label: str) -> None:
        """Last resort: say the box is unavailable rather than leave it stale."""
        try:
            self.query_one(selector, HeroBox).update(
                f"[dim]{label}[/]\n\n{_UNAVAILABLE}"
            )
        except Exception:
            pass
