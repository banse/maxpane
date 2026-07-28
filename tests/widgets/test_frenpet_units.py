"""Unit-label regression tests for FrenPet readouts.

Two display bugs in this area produced numbers a user could act on:

* the Performance screen labelled points-per-DAY velocities ``/hr``
  (a 24x overstatement vs. the ``/day`` label the Wallet and Pet views
  put on the identical value), and rendered negatives as ``+-500/hr``;
* the Wallet hero fed raw 18-decimal ``uint256`` reads into a formatter
  that only knows display units, printing ``37325669265659.0B FP``
  instead of ``37.3K FP``.

These tests pin the unit at the render boundary so neither can silently
come back.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.frenpet_perf_signals import compute_total_velocity
from maxpane_dashboard.analytics.frenpet_signals import calculate_velocity
from maxpane_dashboard.widgets.frenpet.perf.fpp_pets import FPPerfPets
from maxpane_dashboard.widgets.frenpet.perf.fpp_signals import FPPerfSignals
from maxpane_dashboard.widgets.frenpet.perf.fpp_trends import FPPerfTrends
from maxpane_dashboard.widgets.frenpet.perf.fpp_velocity import FPPerfVelocity
from maxpane_dashboard.widgets.frenpet.perf.velocity_format import format_velocity
from maxpane_dashboard.widgets.frenpet.wallet.fpw_hero import FPWalletHero


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _text(widget, selector: str) -> str:
    """Return the plain text a Static currently renders."""
    content = widget.query_one(selector, Static).content
    return str(getattr(content, "plain", content))


# ---------------------------------------------------------------------------
# The source of the number: calculate_velocity is points per DAY
# ---------------------------------------------------------------------------

def test_calculate_velocity_is_points_per_day() -> None:
    """Two samples 12h apart gaining 1,200 pts => 2,400 pts/day."""
    t0 = 1_800_000_000.0
    samples = [(t0, 10_000.0), (t0 + 43_200.0, 11_200.0)]

    assert calculate_velocity(samples) == pytest.approx(2400.0)
    assert compute_total_velocity({1: 2400.0, 2: 600.0}) == pytest.approx(3000.0)


def test_format_velocity_labels_days_and_keeps_sign() -> None:
    assert format_velocity(2400.0, compact=False) == "+2.4K/day"
    assert format_velocity(500.0, compact=False) == "+500/day"
    assert format_velocity(-500.0, compact=False) == "-500/day"
    assert format_velocity(-1500.0, compact=False) == "-1.5K/day"
    assert format_velocity(2_500_000.0) == "+2.5M/day"
    # The old rendering: never again.
    assert "/hr" not in format_velocity(-500.0)
    assert "+-" not in format_velocity(-500.0, compact=False)


# ---------------------------------------------------------------------------
# Performance screen widgets (MEDI-7)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_perf_signals_renders_per_day() -> None:
    widget = FPPerfSignals()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(
            avg_win_rate=55.0,
            wr_status="balanced",
            wr_color="yellow",
            total_velocity=2400.0,
            vel_status="growing",
            vel_color="green",
            weakest_name="Pet1",
            weakest_wr=20.0,
            weakest_status="weak",
            weakest_color="red",
        )
        line = _text(widget, "#fpp-sig-velocity")
        assert "2.4K/day" in line
        assert "/hr" not in line

        widget.update_data(
            avg_win_rate=55.0,
            wr_status="balanced",
            wr_color="yellow",
            total_velocity=-500.0,
            vel_status="declining",
            vel_color="red",
            weakest_name="Pet1",
            weakest_wr=20.0,
            weakest_status="weak",
            weakest_color="red",
        )
        line = _text(widget, "#fpp-sig-velocity")
        assert "-500/day" in line
        assert "+-" not in line


@pytest.mark.asyncio
async def test_perf_velocity_rows_render_per_day() -> None:
    widget = FPPerfVelocity()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(
            pets=[{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}],
            pet_velocities={1: 2400.0, 2: -500.0},
            pet_score_histories={1: [(1.0, 10.0), (2.0, 20.0)]},
        )
        body = _text(widget, "#fpp-vel-content")
        assert "2.4K/day" in body
        assert "-500/day" in body
        assert "/hr" not in body
        assert "+-" not in body


@pytest.mark.asyncio
async def test_perf_pets_table_renders_per_day() -> None:
    widget = FPPerfPets()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(
            pets=[
                {"id": 1, "name": "Alpha", "score": 50_000,
                 "wins": 10, "losses": 5, "atk": 100, "def": 80},
            ],
            pet_velocities={1: -500.0},
        )
        table = widget.query_one("#fpp-pets-table", DataTable)
        cells = [str(c) for c in table.get_row_at(0)]
        assert any("-500/day" in c for c in cells)
        assert not any("/hr" in c for c in cells)


@pytest.mark.asyncio
async def test_perf_trends_velocity_sparkline_renders_per_day() -> None:
    widget = FPPerfTrends()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(
            score_history=[(1.0, 10.0), (2.0, 20.0)],
            velocity_history=[(1.0, 1200.0), (2.0, 2400.0)],
            win_rate_history=[(1.0, 55.0)],
        )
        line = _text(widget, "#fpp-chart-velocity")
        assert "2.4K/day" in line
        assert "/hr" not in line


# ---------------------------------------------------------------------------
# Wallet hero (MEDI-33)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wallet_hero_formats_display_fp_not_wei() -> None:
    widget = FPWalletHero()
    app = _Harness(widget)
    async with app.run_test():
        # 3.73e22 raw wei == ~37,326 FP, already scaled by the caller.
        widget.update_data(
            total_eth_wei=12,
            eth_price_usd=3000.0,
            pool_share_pct=25.0,
            total_fp_in_pool=37_325.669,
            apr=12.5,
            user_shares=1_234.5,
            pet_count=2,
        )
        pool_text = _text(widget, "#fpw-hero-pool")
        apr_text = _text(widget, "#fpw-hero-apr")

        assert "37.3K FP pool" in pool_text
        assert "B FP" not in pool_text
        assert "1.2K FP staked" in apr_text
