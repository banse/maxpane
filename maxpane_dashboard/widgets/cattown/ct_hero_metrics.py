"""Hero metric boxes for the Cat Town dashboard."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


def _short_addr(address: str) -> str:
    """Shorten a wallet address to 0xABCD..1234 format."""
    if len(address) > 10:
        return f"{address[:6]}..{address[-4:]}"
    return address


def _fmt_kibble(amount: float) -> str:
    """Format KIBBLE amount with K/M suffix."""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    return f"{amount:,.0f}"


class CTHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class CTHeroMetrics(Horizontal):
    """Row of three hero metric boxes: Prize Pool, Competition, Top Fisher."""

    DEFAULT_CSS = """
    CTHeroMetrics > CTHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield CTHeroBox(
            "[dim]PRIZE POOL[/]\n\n"
            "[dim]Loading...[/]",
            id="ct-hero-prize",
        )
        yield CTHeroBox(
            "[dim]COMPETITION[/]\n\n"
            "[dim]Loading...[/]",
            id="ct-hero-competition",
        )
        yield CTHeroBox(
            "[dim]LEADER[/]\n\n"
            "[dim]Loading...[/]",
            id="ct-hero-fisher",
        )

    def update_data(
        self,
        competition_state: dict | None = None,
        top_fisher: dict | None = None,
        **_kwargs,
    ) -> None:
        """Refresh all three hero boxes with live values."""
        # -- Prize Pool --
        prize_box = self.query_one("#ct-hero-prize", CTHeroBox)
        if competition_state and competition_state.get("prize_pool_kibble", 0) > 0:
            prize = competition_state["prize_pool_kibble"]
            participants = competition_state.get("num_participants", 0)
            prize_box.update(
                f"[dim]PRIZE POOL[/]\n\n"
                f"[bold white]{_fmt_kibble(prize)} KIBBLE[/]\n"
                f"[dim]split between top fishers"
                f"{f'  ·  {participants} active' if participants else ''}[/]"
            )
        else:
            prize_box.update(
                "[dim]PRIZE POOL[/]\n\n"
                "[dim]Loading...[/]"
            )

        # -- Competition --
        comp_box = self.query_one("#ct-hero-competition", CTHeroBox)
        if competition_state:
            is_active = competition_state.get("is_active", False)
            seconds_remaining = competition_state.get("seconds_remaining", 0)
            total_vol = competition_state.get("total_volume_kibble", 0)
            vol_str = f"{_fmt_kibble(total_vol)} total volume" if total_vol else ""
            if is_active:
                days = seconds_remaining // 86400
                hours = (seconds_remaining % 86400) // 3600
                mins = (seconds_remaining % 3600) // 60
                if days > 0:
                    countdown = f"{days}d {hours}h {mins}m"
                elif hours > 0:
                    countdown = f"{hours}h {mins}m"
                else:
                    countdown = f"{mins}m"
                comp_box.update(
                    f"[dim]COMPETITION[/]\n\n"
                    f"[bold yellow]LIVE[/]  [bold white]{countdown}[/]\n"
                    f"[dim]{vol_str}[/]"
                )
            else:
                end_time = competition_state.get("end_time", 0)
                if end_time > 0 and seconds_remaining <= 0:
                    # Competition ended — show how long ago
                    ago = int(time.time()) - end_time
                    if ago < 0:
                        ago = 0
                    ago_days = ago // 86400
                    ago_hours = (ago % 86400) // 3600
                    ago_mins = (ago % 3600) // 60
                    if ago_days > 0:
                        countdown = f"Ended {ago_days}d {ago_hours}h ago"
                    elif ago_hours > 0:
                        countdown = f"Ended {ago_hours}h {ago_mins}m ago"
                    else:
                        countdown = f"Ended {ago_mins}m ago"
                else:
                    days = seconds_remaining // 86400
                    hours = (seconds_remaining % 86400) // 3600
                    mins = (seconds_remaining % 3600) // 60
                    if days > 0:
                        countdown = f"Starts in {days}d {hours}h"
                    elif hours > 0:
                        countdown = f"Starts in {hours}h {mins}m"
                    else:
                        countdown = f"Starts in {mins}m"
                comp_box.update(
                    f"[dim]COMPETITION[/]\n\n"
                    f"[bold white]{countdown}[/]\n"
                    f"[dim]{vol_str}[/]"
                )
        else:
            comp_box.update(
                "[dim]COMPETITION[/]\n\n"
                "[dim]Loading...[/]"
            )

        # -- Leader (#1 position) --
        fisher_box = self.query_one("#ct-hero-fisher", CTHeroBox)
        if top_fisher:
            display_name = top_fisher.get("display_name", "")
            addr = _short_addr(top_fisher.get("address", ""))
            name_str = display_name if display_name else addr
            weight = top_fisher.get("weight_kg", 0.0)
            fisher_box.update(
                f"[dim]LEADER[/]\n\n"
                f"[bold green]{name_str}[/]\n"
                f"[dim]{weight:.1f}kg[/]"
            )
        else:
            fisher_box.update(
                "[dim]LEADER[/]\n\n"
                "[dim]Loading...[/]"
            )
