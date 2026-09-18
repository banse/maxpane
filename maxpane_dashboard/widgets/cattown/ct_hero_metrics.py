"""Hero metric boxes for the Cat Town dashboard.

Every box is written on every ``update_data`` call (MEDI-38, the rule the
hero template states): a payload the manager could not read arrives as
``None`` and renders an explicit ``unavailable`` marker instead of the
"Loading..." the old copy showed forever, and a real ``0`` prize pool
renders as ``0 KIBBLE`` rather than collapsing into "loading".
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static
from maxpane_dashboard.widgets.address import address_text

#: display budget for the leader name/address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced (recipe step 6, PRD §5).
#: No pin binds this hero box.
_LEADER_COLS = 12

#: Shown in place of a value the backend could not supply this poll.
_UNAVAILABLE = "[yellow]unavailable[/]"


def _fmt_kibble(amount: float) -> str:
    """Format KIBBLE amount with K/M suffix."""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    return f"{amount:,.0f}"


def _countdown(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {mins}m"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


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
        """Refresh all three hero boxes; a missing value says so."""
        self._render_box("#ct-hero-prize", "PRIZE POOL",
                         self._prize_body, competition_state)
        self._render_box("#ct-hero-competition", "COMPETITION",
                         self._competition_body, competition_state)
        self._render_box("#ct-hero-fisher", "LEADER",
                         self._leader_body, top_fisher)

    # -- box bodies -------------------------------------------------------

    @staticmethod
    def _prize_body(state: dict | None) -> str:
        prize = state.get("prize_pool_kibble") if state else None
        if prize is None:
            return _UNAVAILABLE
        participants = state.get("num_participants") or 0
        return (
            f"[bold white]{_fmt_kibble(prize)} KIBBLE[/]\n"
            f"[dim]split between top fishers"
            f"{f'  ·  {participants} active' if participants else ''}[/]"
        )

    @staticmethod
    def _competition_body(state: dict | None) -> str:
        if not state:
            return _UNAVAILABLE
        is_active = state.get("is_active", False)
        seconds_remaining = state.get("seconds_remaining") or 0
        total_vol = state.get("total_volume_kibble") or 0
        vol_str = f"{_fmt_kibble(total_vol)} total volume" if total_vol else ""
        if is_active:
            return (
                f"[bold yellow]LIVE[/]  [bold white]{_countdown(seconds_remaining)}[/]\n"
                f"[dim]{vol_str}[/]"
            )
        end_time = state.get("end_time") or 0
        if end_time > 0 and seconds_remaining <= 0:
            # Competition ended -- show how long ago
            ago = max(int(time.time()) - end_time, 0)
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
        return f"[bold white]{countdown}[/]\n[dim]{vol_str}[/]"

    @staticmethod
    def _leader_body(fisher: dict | None) -> str | Text:
        if not fisher:
            return _UNAVAILABLE
        display_name = fisher.get("display_name", "")
        weight = fisher.get("weight_kg") or 0.0
        body = Text()
        body.append_text(address_text(
            fisher.get("address", ""),
            label=display_name or None,
            width=_LEADER_COLS,
            style="bold green",
        ))
        body.append("\n")
        body.append(f"{weight:.1f}kg", style="dim")
        return body

    def _render_box(self, selector: str, label: str, build, payload) -> None:
        """Write one box, degrading to an explicit unavailable state.

        The body is built inside the guard: a malformed payload (a string
        where a number was expected) must land on ``unavailable`` here, not
        raise into the screen's ``except`` and leave the previous poll's
        number on screen as if it were live.
        """
        try:
            box = self.query_one(selector, CTHeroBox)
        except Exception:
            return
        try:
            body = build(payload)
            if isinstance(body, Text):
                text = Text()
                text.append(label, style="dim")
                text.append("\n\n")
                text.append_text(body)
                box.update(text)
            else:
                box.update(f"[dim]{label}[/]\n\n{body}")
        except Exception:
            try:
                box.update(f"[dim]{label}[/]\n\n{_UNAVAILABLE}")
            except Exception:
                pass
