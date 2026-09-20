"""MEDI-38: the hero rows and signals panels degrade to an explicit
``unavailable`` state instead of "Loading..." forever.

Composited (``render_strips``), never the content string.  The harness has
no ``try/except`` around ``update_data`` -- unlike the screens, which
swallow a widget's exception and thereby leave the *previous* poll's
numbers on screen as if live.  So a payload that raised inside the widget
fails here, which is the point: the guard must live in the widget.

Three claims per widget:

1. a failed read (``None`` everywhere) renders ``unavailable``, not
   "Loading..." and not a crash;
2. a real ``0`` is a number, not "loading" and not ``unavailable``;
3. a malformed payload -- or, for the roster, a **failed read** -- after a
   good one lands on ``unavailable``: the good poll's number is gone, not
   presented as live.

**The two hero rows Branch 7 WP-B migrated are in a second table, not the
first**, and claim 1 is the reason. ``TalismansHeroMetrics`` and
``TTTHeroMetrics`` are handed scalars, not signal dicts, and a ``None``
scalar from their managers is a *deliberate* "nothing to report" --
``total_cores`` while the enumeration syncs -- which renders ``--``. It is
not a failed read, and making it say ``unavailable`` would be a **false
degradation**, the mirror of the defect this file exists for. So for those
two, claim 1 becomes: an all-``None`` poll renders ``--``, never
``Loading``, and never the word reserved for a read that failed. Claims 2
and 3 are unchanged, and claim 3 is the one that matters here -- it is the
guard those four bare ``query_one(...).update(...)`` calls never had.

**The base terminal's two scalar panels (Branch 8 WP-A, fix round 1, review
I1) are in that second table too**, with their own word for "absent": the
manager omits ``eth_price`` / ``total_volume`` on a poll that found no
tokens and the copy rendered ``...`` for it (``No data`` for the gainer), and
``BTSignals`` is handed plain strings, not signal dicts -- ``None`` is a
signal it could not compute this poll, rendered ``...`` since the copy. So
the table carries the *absent* word per row (``--`` or ``...``), and claim 1
asserts that word, never ``Loading`` and never ``unavailable``.
"""

from __future__ import annotations

import inspect

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.app import MaxPaneApp

from maxpane_dashboard.widgets.base.overview.bt_hero_metrics import BTOverviewHero
from maxpane_dashboard.widgets.base.overview.bt_signals import BTSignals
from maxpane_dashboard.widgets.cattown.ct_hero_metrics import CTHeroMetrics
from maxpane_dashboard.widgets.cattown.ct_signals import CTSignals
from maxpane_dashboard.widgets.dota.dota_activity_feed import DOTAActivityFeed
from maxpane_dashboard.widgets.dota.dota_hero_metrics import DOTAHeroMetrics
from maxpane_dashboard.widgets.dota.dota_signals import DOTASignals
from maxpane_dashboard.widgets.ocm.ocm_hero_metrics import OCMHeroMetrics
from maxpane_dashboard.widgets.ocm.ocm_signals import OCMSignals
from maxpane_dashboard.widgets.talismans.tal_hero_metrics import (
    TalismansHeroMetrics,
)
from maxpane_dashboard.widgets.talismans.tal_signals import TalismansSignals
from maxpane_dashboard.widgets.ttt.ttt_hero_metrics import TTTHeroMetrics
from maxpane_dashboard.widgets.ttt.ttt_signals import TTTSignals


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
    OCMHeroBox, CTHeroBox, DOTAHeroBox,
    TalismansHeroBox, TTTHeroBox, BTHeroBox { height: 9; }
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


class _Hostile:
    """A scalar whose every formatting path raises.

    The hero rows' formatters (``fmt.fmt_int`` / ``fmt.fmt_float``) swallow
    ``TypeError`` and ``ValueError`` on purpose, so a mere wrong *type* --
    the string ``"four"`` -- renders ``--`` and never reaches the guard.
    This raises something they do not catch, which is what a malformed
    payload has to do to test that the guard is there at all.
    """

    def __int__(self):
        raise RuntimeError("boom")

    def __float__(self):
        raise RuntimeError("boom")

    def __str__(self):
        raise RuntimeError("boom")

    def __format__(self, spec):
        raise RuntimeError("boom")


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
    # Branch 7 WP-A, fix round 1 (review C1). Not a hero row or a signals
    # panel: the hero ROSTER, which is the third shape where a read that
    # never happened used to be shown as live. Every row carries an HP and
    # an ALIVE/DEAD flag that is true only of the poll it came from, so the
    # "bad" payload here is the **failed read** itself (``heroes=None``) --
    # the panel is a snapshot and must clear and say ``unavailable``, not
    # keep the previous roster. The manager was serving ``[]`` for a failed
    # read, which made that distinction unreachable; both halves are fixed.
    pytest.param(
        DOTAActivityFeed,
        dict(heroes=[{"name": "Axe", "faction": "orc", "hero_class": "tank",
                      "lane": "top", "hp": 500, "max_hp": 600,
                      "alive": True, "level": 4}]),
        "Axe",
        dict(heroes=None),
        id="DOTAActivityFeed",
    ),
    pytest.param(
        TalismansSignals,
        dict(conservation_signal=_SIG, cutmerge_signal=_SIG,
             forge_momentum_signal=_SIG, mythic_scarcity_signal=_SIG),
        "fine",
        dict(conservation_signal={"value_str": object(), "color": 5}),
        id="TalismansSignals",
    ),
    # Branch 7 WP-B. Four bare `query_one(...).update(...)` calls before the
    # migration, so a malformed signal dict raised into the screen's
    # `except` and left the previous poll's rows up as if they were live --
    # and a signal the manager could not compute rendered `--`, the word
    # the analytics uses for "nothing to report". Both are fixed by being
    # on `SignalsPanelBase`.
    pytest.param(
        TTTSignals,
        dict(fresh_launch_signal=_SIG, buybacks_ready_signal=_SIG,
             decay_window_signal=_SIG, concentration_signal=_SIG),
        "fine",
        dict(buybacks_ready_signal={"value_str": object(), "color": 5}),
        id="TTTSignals",
    ),
]

#: The hero rows WP-B migrated, and the base terminal's two scalar panels.
#: Same three claims, except claim 1 -- see the module docstring: a ``None``
#: scalar here is the manager's deliberate "nothing to report" and must stay
#: the panel's own absent word.
#: (widget class, a good payload, what it puts on screen, a payload whose
#:  formatting raises, the absent word an all-``None`` poll renders)
_HERO_ROWS = [
    pytest.param(
        TalismansHeroMetrics,
        dict(live_tokens=1_490, token_drift=-46, mythic_count=12,
             mythic_pct=0.8, mythics_ever_forged=14, total_cores=1_536,
             cores_invariant_intact=True, operations_24h=7,
             operations_total=903),
        "1,490",
        dict(live_tokens=_Hostile()),
        "--",
        id="TalismansHeroMetrics",
    ),
    pytest.param(
        TTTHeroMetrics,
        dict(unburned=4_321, burned_pct=56.79, launches=5_679,
             launches_24h=3, holder_pool_eth_total=12.345,
             holder_pool_eth_24h=0.1234, total_mcap_usd=2_500_000.0,
             total_mcap_eth=900.0, total_mcap_token_count=42),
        "4,321",
        dict(unburned=_Hostile()),
        "--",
        id="TTTHeroMetrics",
    ),
    # Branch 8 WP-A (fix round 1, review I1). Four bare ``query_one().update``
    # calls before the migration; ``_price_body`` catches ``ValueError`` /
    # ``TypeError`` itself (the sweep payload hands it the title bar's
    # ``$3,000`` string), so the malformed value has to raise past those to
    # reach ``render_box``'s guard.
    pytest.param(
        BTOverviewHero,
        dict(eth_price=3_000.0, eth_change_24h=2.5, total_volume=1_200_000.0,
             top_gainer_name="DEGEN", top_gainer_pct=12.0),
        "$3,000.00",
        dict(eth_price=_Hostile()),
        "...",
        id="BTOverviewHero",
    ),
    # Same round. Not a hero row but the same category: handed strings, and
    # ``None`` is "could not compute this poll", which the copy rendered
    # ``...``. ``_signal_indicator`` calls ``str(value).lower()``, so the
    # hostile scalar raises inside ``build`` and lands on the fallback.
    pytest.param(
        BTSignals,
        dict(buy_sell_signal="Bullish", volume_signal="Rising",
             whale_signal="Neutral", recommendation="BUY"),
        "Bullish",
        dict(buy_sell_signal=_Hostile()),
        "...",
        id="BTSignals",
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


# -- the hero rows: claims 2 and 3 verbatim, claim 1 inverted --------------


@pytest.mark.parametrize("cls,good,shown,bad,absent", _HERO_ROWS)
async def test_a_deliberate_none_renders_a_dash_not_unavailable(
    cls, good, shown, bad, absent
):
    """A scalar the manager served as ``None`` is "nothing to report".

    Calling that ``unavailable`` would be a false degradation -- the
    dashboard claiming it could not look when it looked and there was
    nothing. ``--`` is the word for that (``...`` on the base terminal), and
    it is still not ``Loading``: the panel *did* poll.
    """
    widget = cls()
    async with _Harness(widget).run_test(size=(120, 20)) as pilot:
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert absent in text, text
    assert "Loading" not in text, text
    assert "unavailable" not in text, text


@pytest.mark.parametrize("cls,good,shown,bad,absent", _HERO_ROWS)
async def test_a_good_hero_poll_shows_its_value(cls, good, shown, bad, absent):
    widget = cls()
    async with _Harness(widget).run_test(size=(120, 20)) as pilot:
        widget.update_data(**good)
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert shown in text, text
    assert "unavailable" not in text, text


@pytest.mark.parametrize("cls,good,shown,bad,absent", _HERO_ROWS)
async def test_a_malformed_hero_poll_after_a_good_one_is_not_shown_as_live(
    cls, good, shown, bad, absent
):
    """The guard those four bare ``query_one().update()`` calls never had."""
    widget = cls()
    async with _Harness(widget).run_test(size=(120, 20)) as pilot:
        widget.update_data(**good)
        await pilot.pause()
        assert shown in _screen_text(pilot.app)
        widget.update_data(**bad)  # must not raise: the guard is the widget's
        await pilot.pause()
        text = _screen_text(pilot.app)
    assert "unavailable" in text, text
    assert shown not in text, text
