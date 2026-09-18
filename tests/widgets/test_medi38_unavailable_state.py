"""MEDI-38: the three old hero rows and four old signals panels degrade to
an explicit ``unavailable`` state instead of "Loading..." forever.

Composited (``render_strips``), never the content string.  The harness has
no ``try/except`` around ``update_data`` -- unlike the screens, which
swallow a widget's exception and thereby leave the *previous* poll's
numbers on screen as if live.  So a payload that raised inside the widget
fails here, which is the point: the guard must live in the widget.

Three claims per widget:

1. a failed read (``None`` everywhere) renders ``unavailable``, not
   "Loading..." and not a crash;
2. a real ``0`` is a number, not "loading" and not ``unavailable``;
3. a malformed payload after a good one lands on ``unavailable`` -- the
   good poll's number is gone, not presented as live.
"""

from __future__ import annotations

import inspect

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.app import MaxPaneApp

from maxpane_dashboard.widgets.cattown.ct_hero_metrics import CTHeroMetrics
from maxpane_dashboard.widgets.cattown.ct_signals import CTSignals
from maxpane_dashboard.widgets.dota.dota_hero_metrics import DOTAHeroMetrics
from maxpane_dashboard.widgets.dota.dota_signals import DOTASignals
from maxpane_dashboard.widgets.ocm.ocm_hero_metrics import OCMHeroMetrics
from maxpane_dashboard.widgets.ocm.ocm_signals import OCMSignals
from maxpane_dashboard.widgets.talismans.tal_signals import TalismansSignals


class _Harness(App):
    """Loads ``minimal.tcss`` as the app stylesheet: it is what gives each
    hero box its ``width: 1fr``.  Without it the first box takes the whole
    row and the other boxes never reach the compositor (the
    ``test_cattown_talismans_address_icons.py`` precedent).
    """

    CSS_PATH = MaxPaneApp.CSS_PATH

    #: The theme's 7-row hero box (border + ``padding: 1 2``) has three
    #: content rows, so the fourth line each box writes -- the ``%`` /
    #: ``mint cost`` subtitle -- is clipped in production today (a
    #: pre-existing theme matter, same as ``TalismansHeroBox`` per the
    #: comment in ``minimal.tcss``; filed in HANDOVER.md follow-ups).  This
    #: file asserts what the *widget* puts on screen, so give the box the
    #: row it needs.
    CSS = """
    OCMHeroBox, CTHeroBox, DOTAHeroBox { height: 9; }
    """

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see."""
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _none_payload(widget) -> dict:
    """All-``None`` payload built from the widget's own signature."""
    return {
        name: None
        for name, param in inspect.signature(widget.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    }


_SIG = {"label": "X", "value_str": "fine", "indicator": "●", "color": "green"}

#: (widget class, a good payload, the value the good payload puts on screen,
#:  a malformed payload that must raise inside the formatter)
_WIDGETS = [
    pytest.param(
        OCMHeroMetrics,
        dict(total_supply=4_321, minted_pct=43.2, total_staked=1_000,
             staking_ratio=25.0, current_minting_cost_ocmd=12.0),
        "4,321 / 10K",
        dict(total_supply="four", minted_pct=43.2),
        id="OCMHeroMetrics",
    ),
    pytest.param(
        CTHeroMetrics,
        dict(competition_state={"prize_pool_kibble": 2_500, "is_active": True,
                                "seconds_remaining": 3_700, "num_participants": 9},
             top_fisher={"address": "0x" + "ab" * 20, "weight_kg": 3.2}),
        "2.5K KIBBLE",
        dict(competition_state={"prize_pool_kibble": "lots"}, top_fisher="nobody"),
        id="CTHeroMetrics",
    ),
    pytest.param(
        DOTAHeroMetrics,
        dict(winning_faction="human", human_base_hp=900, orc_base_hp=400,
             base_max_hp=1_000, token_market_cap=2_500_000.0,
             token_price_change_24h=3.0, top_player_name="zed",
             top_player_wins=4, top_player_win_rate=80.0),
        "$2.5M",
        dict(token_market_cap="big", base_max_hp="max", human_base_hp=1),
        id="DOTAHeroMetrics",
    ),
    pytest.param(
        OCMSignals,
        dict(staking_signal=_SIG, mint_velocity_signal=_SIG, burn_rate_signal=_SIG),
        "fine",
        dict(staking_signal={"label": object()}),
        id="OCMSignals",
    ),
    pytest.param(
        CTSignals,
        dict(condition_signal=_SIG, legendary_signal=_SIG, cutoff_signal=_SIG),
        "fine",
        dict(condition_signal={"label": object()}),
        id="CTSignals",
    ),
    pytest.param(
        DOTASignals,
        dict(faction_balance_signal=_SIG, lane_pressure_signal=_SIG,
             hero_advantage_signal=_SIG),
        "fine",
        dict(faction_balance_signal={"label": object()}),
        id="DOTASignals",
    ),
    pytest.param(
        TalismansSignals,
        dict(conservation_signal=_SIG, cutmerge_signal=_SIG,
             forge_momentum_signal=_SIG, mythic_scarcity_signal=_SIG),
        "fine",
        dict(conservation_signal={"value_str": object(), "color": 5}),
        id="TalismansSignals",
    ),
]


@pytest.mark.parametrize("cls,good,shown,bad", _WIDGETS)
async def test_a_failed_read_renders_unavailable_not_loading(cls, good, shown, bad):
    widget = cls()
    async with _Harness(widget).run_test(size=(120, 20)) as pilot:
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert "unavailable" in text, text
    assert "Loading" not in text, text


@pytest.mark.parametrize("cls,good,shown,bad", _WIDGETS)
async def test_a_good_poll_shows_its_value(cls, good, shown, bad):
    widget = cls()
    async with _Harness(widget).run_test(size=(120, 20)) as pilot:
        widget.update_data(**good)
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert shown in text, text
    assert "unavailable" not in text, text


@pytest.mark.parametrize("cls,good,shown,bad", _WIDGETS)
async def test_a_malformed_poll_after_a_good_one_is_not_shown_as_live(cls, good, shown, bad):
    widget = cls()
    async with _Harness(widget).run_test(size=(120, 20)) as pilot:
        widget.update_data(**good)
        await pilot.pause()
        assert shown in _screen_text(pilot.app)
        widget.update_data(**bad)  # must not raise: the guard is the widget's
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert "unavailable" in text, text
    # The row or box the malformed value belongs to no longer shows the good
    # poll's number: a stale value presented as live is the MEDI-38 defect.
    assert shown not in text, text


@pytest.mark.parametrize(
    "cls,payload,shown",
    [
        pytest.param(OCMHeroMetrics, dict(total_supply=0, minted_pct=0.0),
                     "0 / 10K", id="ocm-supply-0"),
        pytest.param(OCMHeroMetrics, dict(total_staked=0, staking_ratio=0.0),
                     "0.0% of net supply", id="ocm-staked-0"),
        pytest.param(OCMHeroMetrics, dict(current_minting_cost_ocmd=0),
                     "mint cost: 0 $OCMD", id="ocm-cost-0"),
        pytest.param(CTHeroMetrics, dict(competition_state={"prize_pool_kibble": 0}),
                     "0 KIBBLE", id="ct-prize-0"),
        pytest.param(DOTAHeroMetrics, dict(token_market_cap=0.0),
                     "$0", id="dota-mcap-0"),
    ],
)
async def test_a_real_zero_is_a_number_not_loading(cls, payload, shown):
    widget = cls()
    async with _Harness(widget).run_test(size=(120, 20)) as pilot:
        widget.update_data(**payload)
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert shown in text, text
    assert "Loading" not in text, text
