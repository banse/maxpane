"""Headless tests for the FWA NETWORK hero."""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult
from textual.widgets import Static

from maxpane_dashboard.data.fwa_ecosystem_models import FWA_NETWORK_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fwa.fwa_network_hero import FWANetworkHero


class _Harness(App):
    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _plain(widget, selector: str) -> str:
    visual = widget.query_one(selector, Static).visual
    return getattr(visual, "plain", str(visual))


def _signature_names(method) -> tuple[str, ...]:
    return tuple(name for name in inspect.signature(method).parameters if name != "self")


async def test_network_hero_signature_is_exact_and_keyword_only() -> None:
    signature = inspect.signature(FWANetworkHero.update_data)
    assert _signature_names(FWANetworkHero.update_data) == FWA_NETWORK_WIDGET_SIGNATURES[
        "FWANetworkHero"
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for name, parameter in signature.parameters.items()
        if name != "self"
    )


async def test_network_hero_blank_payload_is_honest() -> None:
    widget = FWANetworkHero()
    async with _Harness(widget).run_test(size=(120, 12)):
        widget.update_data(
            **{
                key: None
                for key in FWA_NETWORK_WIDGET_SIGNATURES["FWANetworkHero"]
            }
        )
        for selector in (
            "#fwa-network-platform",
            "#fwa-network-tokenomics",
            "#fwa-network-ecosystem",
        ):
            text = _plain(widget, selector)
            assert "Loading" not in text
            assert "n/a" in text
            assert " 0 " not in text


async def test_network_hero_renders_live_values_and_separate_health_counts() -> None:
    widget = FWANetworkHero()
    async with _Harness(widget).run_test(size=(150, 12)):
        widget.update_data(
            network_ready=True,
            network_state_block=25_849_738,
            network_state_stale=False,
            network_active_listings=321,
            network_pull_quote_eth=0.117916,
            network_pending_count=7,
            network_unsettled_count=3,
            network_crown_pot_eth=12.3456,
            network_token_supply_fwa=986_380_736.7727,
            network_burned_since_genesis_fwa=13_619_263.2273,
            network_burned_since_genesis_pct=1.361926,
            network_last_buyback_age_s=7_265,
            network_drop_count=2,
            network_project_family_count=5,
            network_project_healthy_count=4,
            network_project_degraded_count=1,
            network_project_unverified_count=1,
        )
        platform = _plain(widget, "#fwa-network-platform")
        token = _plain(widget, "#fwa-network-tokenomics")
        ecosystem = _plain(widget, "#fwa-network-ecosystem")

        assert "321 listings" in platform
        assert "0.1179 ETH" in platform
        assert "25,849,738" in platform and "LIVE" in platform
        assert "986,380,737 FWA" in token
        assert "13,619,263 FWA" in token and "1.36%" in token
        assert "2h ago" in token
        assert "healthy 4" in ecosystem
        assert "degraded 1" in ecosystem
        assert "unverified 1" in ecosystem
        assert "READY" in ecosystem


async def test_network_hero_stale_and_degraded_are_spelled_out() -> None:
    widget = FWANetworkHero()
    async with _Harness(widget).run_test(size=(120, 12)):
        widget.update_data(
            network_ready=False,
            network_state_block=99,
            network_state_stale=True,
        )
        assert "STALE" in _plain(widget, "#fwa-network-platform")
        assert "DEGRADED" in _plain(widget, "#fwa-network-ecosystem")
