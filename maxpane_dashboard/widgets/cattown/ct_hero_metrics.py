"""Hero metric boxes for the Cat Town dashboard.

Every box is written on every ``update_data`` call (MEDI-38, the rule the
hero shape states): a payload the manager could not read arrives as
``None`` and renders an explicit ``unavailable`` marker instead of the
"Loading..." the old copy showed forever, and a real ``0`` prize pool
renders as ``0 KIBBLE`` rather than collapsing into "loading".

The row itself, the boxes' seed text and the build-inside-the-guard write
are :class:`~maxpane_dashboard.widgets.panels.HeroRow`'s (Branch 6). The
LEADER box is why ``render_box`` grew a ``rich.text.Text`` branch in Branch
7: it renders an address through ``widgets/address.py``, whose copy icon is
a ``Style`` with a click ``meta`` that markup parsing would flatten away.
"""

from __future__ import annotations

import time

from rich.text import Text

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.cattown._chain import EXPLORER
from maxpane_dashboard.widgets.cattown._fmt import _countdown, _fmt_kibble
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow

#: display budget for the leader name/address, excluding the icon -- the same
#: 12-cell window the deleted ``_short_addr`` produced (recipe step 6, PRD §5).
#: No pin binds this hero box.
_LEADER_COLS = 12


class CTHeroBox(HeroBoxBase):
    """A single hero metric box with label and value.

    Kept as its own class because ``minimal.tcss`` names ``CTHeroBox`` for
    this dashboard's box geometry, as do the MEDI-38 and address-icon
    harnesses' CSS.
    """


class CTHeroMetrics(HeroRow):
    """Row of three hero metric boxes: Prize Pool, Competition, Top Fisher."""

    BOX_CLASS = CTHeroBox

    BOXES = (
        ("ct-hero-prize", "PRIZE POOL"),
        ("ct-hero-competition", "COMPETITION"),
        ("ct-hero-fisher", "LEADER"),
    )

    def update_data(
        self,
        competition_state: dict | None = None,
        top_fisher: dict | None = None,
        **_kwargs,
    ) -> None:
        """Refresh all three hero boxes; a missing value says so."""
        self.render_box(
            "#ct-hero-prize", "PRIZE POOL",
            lambda: self._prize_body(competition_state),
        )
        self.render_box(
            "#ct-hero-competition", "COMPETITION",
            lambda: self._competition_body(competition_state),
        )
        self.render_box(
            "#ct-hero-fisher", "LEADER",
            lambda: self._leader_body(top_fisher),
        )

    # -- box bodies -------------------------------------------------------

    @staticmethod
    def _prize_body(state: dict | None) -> str:
        prize = state.get("prize_pool_kibble") if state else None
        if prize is None:
            return UNAVAILABLE
        participants = state.get("num_participants") or 0
        return (
            f"[bold white]{_fmt_kibble(prize)} KIBBLE[/]\n"
            f"[dim]split between top fishers"
            f"{f'  ·  {participants} active' if participants else ''}[/]"
        )

    @staticmethod
    def _competition_body(state: dict | None) -> str:
        if not state:
            return UNAVAILABLE
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
            return UNAVAILABLE
        display_name = fisher.get("display_name", "")
        weight = fisher.get("weight_kg") or 0.0
        body = Text()
        body.append_text(address_text(
            fisher.get("address", ""),
            label=display_name or None,
            width=_LEADER_COLS,
            style="bold green",
            explorer=EXPLORER,
        ))
        body.append("\n")
        body.append(f"{weight:.1f}kg", style="dim")
        return body
