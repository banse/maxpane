"""Three-card NETWORK overview for Fake World Assets.

This is a passive presentation widget.  It accepts only the frozen primitive
payload dispatched by the screen and never reaches into data, clocks, or I/O.
Unavailable readings are rendered as ``n/a`` so a failed read cannot be
mistaken for a measured zero.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal

from maxpane_dashboard.widgets.fwa.fwa_hero_metrics import FWAHeroBox

_NA = "n/a"


def _as_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _fmt_number(value, places: int = 2) -> str:
    number = _as_float(value)
    return _NA if number is None else f"{number:,.{places}f}"


def _fmt_count(value) -> str:
    if value is None or isinstance(value, bool):
        return _NA
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError, OverflowError):
        return _NA


def _fmt_age(value) -> str:
    seconds = _as_float(value)
    if seconds is None or seconds < 0:
        return _NA
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3_600:
        return f"{int(seconds // 60)}m"
    if seconds < 86_400:
        return f"{int(seconds // 3_600)}h"
    return f"{int(seconds // 86_400)}d"


class FWANetworkHero(Horizontal):
    """Platform, tokenomics, and ecosystem health at one glance."""

    DEFAULT_CSS = """
    FWANetworkHero {
        height: 7;
    }
    FWANetworkHero > FWAHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 1;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield FWAHeroBox(
            "[dim]PLATFORM[/]\n\n[dim]Loading...[/]",
            id="fwa-network-platform",
            classes="fwa-network-hero-box",
        )
        yield FWAHeroBox(
            "[dim]TOKENOMICS[/]\n\n[dim]Loading...[/]",
            id="fwa-network-tokenomics",
            classes="fwa-network-hero-box",
        )
        yield FWAHeroBox(
            "[dim]ECOSYSTEM[/]\n\n[dim]Loading...[/]",
            id="fwa-network-ecosystem",
            classes="fwa-network-hero-box",
        )

    def update_data(
        self,
        *,
        network_ready=None,
        network_state_block=None,
        network_state_stale=None,
        network_active_listings=None,
        network_pull_quote_eth=None,
        network_pending_count=None,
        network_unsettled_count=None,
        network_crown_pot_eth=None,
        network_token_supply_fwa=None,
        network_burned_since_genesis_fwa=None,
        network_burned_since_genesis_pct=None,
        network_last_buyback_age_s=None,
        network_drop_count=None,
        network_project_family_count=None,
        network_project_healthy_count=None,
        network_project_degraded_count=None,
        network_project_unverified_count=None,
    ) -> None:
        """Render the exact frozen NETWORK hero contract."""
        platform = self.query_one("#fwa-network-platform", FWAHeroBox)
        tokenomics = self.query_one("#fwa-network-tokenomics", FWAHeroBox)
        ecosystem = self.query_one("#fwa-network-ecosystem", FWAHeroBox)

        state = _NA
        if network_state_stale is True:
            state = "STALE"
        elif network_state_block is not None:
            state = "LIVE"
        block = _fmt_count(network_state_block)
        platform.update(
            "[dim]PLATFORM[/]\n"
            f"[bold]{_fmt_count(network_active_listings)} listings[/]"
            f" · {_fmt_number(network_pull_quote_eth, 4)} ETH\n"
            f"queue {_fmt_count(network_pending_count)} pending"
            f" · {_fmt_count(network_unsettled_count)} unsettled\n"
            f"crown {_fmt_number(network_crown_pot_eth, 3)} ETH\n"
            f"[dim]{state} · block {block}[/]"
        )

        burned_pct = _as_float(network_burned_since_genesis_pct)
        pct = _NA if burned_pct is None else f"{burned_pct:.2f}%"
        tokenomics.update(
            "[dim]TOKENOMICS[/]\n"
            f"[bold]{_fmt_number(network_token_supply_fwa, 0)} FWA[/]\n"
            f"burned {_fmt_number(network_burned_since_genesis_fwa, 0)} FWA\n"
            f"genesis burn {pct}\n"
            f"[dim]last buyback {_fmt_age(network_last_buyback_age_s)} ago[/]"
        )

        readiness = _NA
        if network_ready is True:
            readiness = "READY"
        elif network_ready is False:
            readiness = "DEGRADED"
        ecosystem.update(
            "[dim]ECOSYSTEM[/]\n"
            f"[bold]{_fmt_count(network_drop_count)} drops[/]"
            f" · {_fmt_count(network_project_family_count)} families\n"
            f"healthy {_fmt_count(network_project_healthy_count)}\n"
            f"degraded {_fmt_count(network_project_degraded_count)}"
            f" · unverified {_fmt_count(network_project_unverified_count)}\n"
            f"[dim]{readiness}[/]"
        )
