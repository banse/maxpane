"""One blank row under every widget title, on every dashboard but surf.

The convention is the repo owner's and it is **mandatory**: a panel title is
followed by a blank row, then content. Surf's three bodies got theirs on
2026-09-12 (``test_every_market_panel_paints_a_blank_row_under_its_title`` and
``test_every_pool4_panel_paints_a_blank_row_under_its_title``); this file is
the same contract for the other seven dashboards, including the five hidden
ones, whose code and tests are intact and whose panels are one ``GAMES`` edit
away from being on screen again.

**Parametrised per panel, never looped.** A single test walking the table
would stop at the first failure and report one panel when three were broken --
and a fix that satisfied the first would turn the suite green with the rest
still flush. Fifty-one cases, fifty-one independent verdicts. That is what
makes this evidence rather than a smoke test.

**Composited output, under the app stylesheet.** Two mechanisms paint this row
in this repo and both are legitimate: most of these panels yield a blank
``Static`` of their own from ``compose`` (the older lineage, seeded from the
bakery templates), while ``FWAOddsBoard``, ``FWASettlementTable``,
``TTTSignals`` and ``FPPerfVelocity`` state it as ``margin: 0 0 1 0`` on the
title's own class (the lineage pass 1 wrote into ``templates/``). Asserting
against either *source* would therefore be asserting about a mechanism rather
than about the convention, and would be green on a panel that states the rule
in one of the two CSS files and is overridden in the other. The only question
that is the same question for both shapes is what reaches the compositor, so
the harness loads ``minimal.tcss`` as the app stylesheet -- where it lives in
production, and where it outranks a widget's ``DEFAULT_CSS``.

**Why the third assertion is there.** ``rows[2]`` must carry something. Without
it every case passes on a panel that has gone completely dark, because a dark
panel is all blank rows and row 1 is blank for the wrong reason. Each payload
below is therefore the smallest one that puts real text on row 2; several are
deliberately the *empty* state (``no data``, ``--``), which still prints.

Three panels failed this when it was written and each is a different shape of
the same omission -- see ``docs/`` and the commit message. The other
twenty-seven already painted the row from Python and were left alone: the
convention is about the row, and they have it.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.app import CSS_PATH

from maxpane_dashboard.widgets.cookie_chart import CookieChart
from maxpane_dashboard.widgets.ev_table import EVTable
from maxpane_dashboard.widgets.signals_panel import SignalsPanel
from maxpane_dashboard.widgets.base.overview.bt_best_plays import BTBestPlays
from maxpane_dashboard.widgets.base.overview.bt_signals import BTSignals
from maxpane_dashboard.widgets.base.overview.bt_sparklines import BTSparklines
from maxpane_dashboard.widgets.cattown.ct_activity_feed import CTActivityFeed
from maxpane_dashboard.widgets.cattown.ct_best_plays import CTBestPlays
from maxpane_dashboard.widgets.cattown.ct_leaderboard import CTLeaderboard
from maxpane_dashboard.widgets.cattown.ct_signals import CTSignals
from maxpane_dashboard.widgets.cattown.ct_sparklines import CTSparklines
from maxpane_dashboard.widgets.dota.dota_activity_feed import DOTAActivityFeed
from maxpane_dashboard.widgets.dota.dota_best_plays import DOTABestPlays
from maxpane_dashboard.widgets.dota.dota_leaderboard import DOTALeaderboard
from maxpane_dashboard.widgets.dota.dota_signals import DOTASignals
from maxpane_dashboard.widgets.dota.dota_sparklines import DOTASparklines
from maxpane_dashboard.widgets.frenpet.overview.fp_best_plays import FPBestPlays
from maxpane_dashboard.widgets.frenpet.overview.fp_game_signals import FPGameSignals
from maxpane_dashboard.widgets.frenpet.overview.fp_score_trends import FPScoreTrends
from maxpane_dashboard.widgets.frenpet.perf.fpp_signals import FPPerfSignals
from maxpane_dashboard.widgets.frenpet.perf.fpp_trends import FPPerfTrends
from maxpane_dashboard.widgets.frenpet.perf.fpp_velocity import FPPerfVelocity
from maxpane_dashboard.widgets.frenpet.wallet.fpw_best_plays import FPWalletBestPlays
from maxpane_dashboard.widgets.frenpet.wallet.fpw_signals import FPWalletSignals
from maxpane_dashboard.widgets.frenpet.wallet.fpw_trends import FPWalletTrends
from maxpane_dashboard.widgets.fwa.fwa_activity_feed import FWAActivityFeed
from maxpane_dashboard.widgets.fwa.fwa_chase_board import FWAChaseBoard
from maxpane_dashboard.widgets.fwa.fwa_odds_board import FWAOddsBoard
from maxpane_dashboard.widgets.fwa.fwa_settlement_table import FWASettlementTable
from maxpane_dashboard.widgets.fwa.fwa_signals import FWASignals
from maxpane_dashboard.widgets.fwa.fwa_sparkline import FWASparkline
from maxpane_dashboard.widgets.ocm.ocm_activity_feed import OCMActivityFeed
from maxpane_dashboard.widgets.ocm.ocm_signals import OCMSignals
from maxpane_dashboard.widgets.ocm.ocm_sparklines import OCMSparklines
from maxpane_dashboard.widgets.ocm.ocm_staking_overview import OCMStakingOverview
from maxpane_dashboard.widgets.ocm.ocm_supply_breakdown import OCMSupplyBreakdown
from maxpane_dashboard.widgets.talismans.tal_activity_feed import (
    TalismansActivityFeed,
)
from maxpane_dashboard.widgets.talismans.tal_leaderboard import TalismansLeaderboard
from maxpane_dashboard.widgets.talismans.tal_materials_table import (
    TalismansMaterialsTable,
)
from maxpane_dashboard.widgets.talismans.tal_matrix_table import TalismansMatrixTable
from maxpane_dashboard.widgets.talismans.tal_signals import TalismansSignals
from maxpane_dashboard.widgets.talismans.tal_sparkline import TalismansSparkline
from maxpane_dashboard.widgets.ttt.ttt_activity_feed import TTTActivityFeed
from maxpane_dashboard.widgets.ttt.ttt_claims_table import TTTClaimsTable
from maxpane_dashboard.widgets.ttt.ttt_fees_table import TTTFeesTable
from maxpane_dashboard.widgets.ttt.ttt_leaderboard import TTTLeaderboard
from maxpane_dashboard.widgets.ttt.ttt_signals import TTTSignals
from maxpane_dashboard.widgets.ttt.ttt_sparkline import TTTSparkline

from tests.widgets.surf_compositing import composite_lines

#: A two-point series -- the shortest input every sparkline in the repo will
#: actually draw rather than short-circuit to ``waiting for data``.
_SERIES = [(1_700_000_000.0, 1.0), (1_700_003_600.0, 2.0)]

#: The nine positional signals ``FPWalletSignals`` requires. None of them is
#: interesting here; what matters is that the panel prints three rows.
_FPW_SIGNALS = dict(
    fp_per_second=1, fp_status="ok", fp_color="green",
    win_rate=0.5, win_status="ok", win_color="green",
    pool_share=0.1, pool_status="ok", pool_color="green",
)

_FPP_SIGNALS = dict(
    avg_win_rate=0.5, wr_status="ok", wr_color="green",
    total_velocity=1.0, vel_status="ok", vel_color="green",
    weakest_name="pet", weakest_wr=0.1, weakest_status="low", weakest_color="red",
)

#: ``(id, widget class, payload)``. The id is what a failure names, so it says
#: the state as well as the panel wherever a panel has more than one.
_PANELS = [
    # -- bakery (hidden) --------------------------------------------------
    ("CookieChart", CookieChart, {"histories": {"bakery": _SERIES}}),
    ("SignalsPanel", SignalsPanel, {
        "late_join_ev": {}, "gap_analysis": {},
        "dominance": 1.0, "recommendation": "",
    }),
    ("EVTable", EVTable, {"boost_rankings": [], "attack_rankings": []}),
    # -- base -------------------------------------------------------------
    ("BTSparklines", BTSparklines, {"volume_history": _SERIES}),
    ("BTSignals", BTSignals, {}),
    ("BTBestPlays", BTBestPlays, {}),
    # -- cattown ----------------------------------------------------------
    ("CTSparklines", CTSparklines, {"prize_pool_history": _SERIES}),
    ("CTSignals", CTSignals, {}),
    ("CTBestPlays", CTBestPlays, {}),
    # Added with Branch 7 WP-A, when both moved onto `widgets/panels.py`:
    # their blank row used to come from `minimal.tcss` alone (and the
    # leaderboard's from a `CTLeaderboard > Static` block this branch
    # deletes), so neither was covered by anything. `{}` is enough for the
    # table -- the empty state still paints the column header on row 2 --
    # and the feed needs one catch, because an empty poll paints its
    # placeholder one row lower than a real row sits.
    ("CTLeaderboard", CTLeaderboard, {}),
    ("CTActivityFeed", CTActivityFeed, {
        "recent_catches": [{
            "tx_hash": "0x" + "cd" * 32,
            "timestamp": 1_700_000_000,
            "fisher_address": "0x" + "ab" * 20,
            "display_name": "",
            "species": "Trout",
            "weight_kg": 2.5,
            "rarity": "Common",
        }],
    }),
    # -- dota (hidden: NXDOMAIN backend, widgets intact) -------------------
    ("DOTASparklines", DOTASparklines, {"top_frontline_history": _SERIES}),
    ("DOTASignals", DOTASignals, {}),
    ("DOTABestPlays", DOTABestPlays, {}),
    # Added with Branch 7 WP-A, same reason as the two cattown rows above.
    # The roster feed is `RichLogFeed` in always-new mode, so one hero is a
    # real row rather than the `No heroes yet` placeholder.
    ("DOTALeaderboard", DOTALeaderboard, {}),
    ("DOTAActivityFeed", DOTAActivityFeed, {
        "heroes": [{
            "name": "Axe",
            "faction": "orc",
            "hero_class": "tank",
            "lane": "top",
            "hp": 500,
            "max_hp": 600,
            "alive": True,
            "level": 4,
        }],
    }),
    # -- ocm (hidden) ------------------------------------------------------
    ("OCMSparklines", OCMSparklines, {"supply_history": _SERIES}),
    ("OCMSignals", OCMSignals, {}),
    ("OCMSupplyBreakdown", OCMSupplyBreakdown, {}),
    # Added with Branch 6 (`widgets/panels.py`). Both were absent from this
    # table and both were wrong in a way it would have caught: the staking
    # overview stated the title margin in `minimal.tcss` AND yielded a
    # `Static("")` spacer, so it painted TWO blank rows, and the activity
    # feed was the one ocm panel whose row came from the stylesheet alone.
    # `{}` is enough for the overview -- every parameter defaults to a
    # number, so row 2 is `Total Staked`. The feed needs one event: its
    # body is a `RichLog`, and an empty poll paints the `No activity yet`
    # placeholder one row lower than a real row would sit.
    ("OCMStakingOverview", OCMStakingOverview, {}),
    ("OCMActivityFeed", OCMActivityFeed, {
        "recent_events": [{
            "tx_hash": "0x" + "ef" * 32,
            "timestamp": 1_700_000_000,
            "event_type": "mint",
            "actor_address": "0x" + "ab" * 20,
            "token_id": 7,
            "count": 1,
        }],
    }),
    # -- frenpet overview --------------------------------------------------
    ("FPScoreTrends", FPScoreTrends, {"top_pets": [], "score_histories": {}}),
    ("FPGameSignals", FPGameSignals, {"battle_rate": 1.0, "win_rate": 0.5}),
    ("FPBestPlays", FPBestPlays, {"top_earners": [], "rising_stars": []}),
    # -- frenpet wallet (hidden) -------------------------------------------
    ("FPWalletTrends", FPWalletTrends, {"score_history": _SERIES}),
    ("FPWalletSignals", FPWalletSignals, dict(_FPW_SIGNALS)),
    ("FPWalletBestPlays", FPWalletBestPlays, {
        "top_earner": None, "most_efficient": None,
    }),
    # -- frenpet perf (hidden) ---------------------------------------------
    ("FPPerfTrends", FPPerfTrends, {"score_history": _SERIES}),
    ("FPPerfSignals", FPPerfSignals, dict(_FPP_SIGNALS)),
    # Fixed 2026-09-12: title and body were adjacent with nothing between.
    ("FPPerfVelocity", FPPerfVelocity, {
        "pets": [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}],
    }),
    # -- talismans -----------------------------------------------------------
    # The whole package arrives with Branch 7 WP-B. Nothing here was covered
    # before: every talismans title was styled by its widget's own
    # `DEFAULT_CSS` and every blank row came from a `Static(" ")` spacer, so
    # the one mechanism this file refuses to assert on was the only one in
    # play. `{}` is enough for the three tables -- the empty state still
    # paints the column header on row 2 -- and the feed needs one operation,
    # because an empty poll paints its placeholder one row lower than a real
    # row sits.
    ("TalismansSparkline", TalismansSparkline, {"mythic_history": _SERIES}),
    ("TalismansSignals", TalismansSignals, {
        "conservation_signal": {"value_str": "cores conserved"},
        "cutmerge_signal": {"value_str": "net +3 cuts"},
        "forge_momentum_signal": {"value_str": "2 mythics 24h"},
        "mythic_scarcity_signal": {"value_str": "0.8% mythic"},
    }),
    ("TalismansLeaderboard", TalismansLeaderboard, {}),
    ("TalismansMaterialsTable", TalismansMaterialsTable, {}),
    ("TalismansMatrixTable", TalismansMatrixTable, {}),
    ("TalismansActivityFeed", TalismansActivityFeed, {
        "activity_events": [{
            "timestamp": 1_700_000_000,
            "op_type": "bond",
            "token_id_a": 11,
            "token_id_b": 22,
            "result_id": 33,
        }],
    }),
    # -- ttt ----------------------------------------------------------------
    ("TTTSparkline", TTTSparkline, {"burn_history": _SERIES}),
    # Two states, because the defect fixed on 2026-09-12 was visible in only
    # one of them: the optional fresh-launch row used to double as the spacer,
    # so the blank row vanished exactly when there was a fresh launch to
    # announce. A single-state case here would have stayed green through it.
    ("TTTSignals-no-fresh", TTTSignals, {
        "buybacks_ready_signal": {"value_str": "2"},
        "decay_window_signal": {"value_str": "open"},
        "concentration_signal": {"value_str": "12%"},
    }),
    ("TTTSignals-fresh-launch", TTTSignals, {
        "fresh_launch_signal": {"value_str": "3 blocks"},
        "buybacks_ready_signal": {"value_str": "2"},
        "decay_window_signal": {"value_str": "open"},
        "concentration_signal": {"value_str": "12%"},
    }),
    # Added with Branch 7 WP-B, same reason as the talismans rows above: the
    # leaderboard's blank row came from a `minimal.tcss` block that named a
    # class the widget never composed (`.leaderboard-title`) and the other
    # three from a `Static(" ")` spacer, so nothing covered any of them. The
    # feed needs one event; `{}` is enough for the three tables.
    ("TTTLeaderboard", TTTLeaderboard, {}),
    ("TTTFeesTable", TTTFeesTable, {}),
    ("TTTClaimsTable", TTTClaimsTable, {}),
    ("TTTActivityFeed", TTTActivityFeed, {
        "activity_events": [{
            "timestamp": 1_700_000_000,
            "event_type": "fee",
            "token_symbol": "TOKE",
            "eth_amount_wei": 10**16,
        }],
    }),
    # -- fwa ----------------------------------------------------------------
    ("FWAOddsBoard", FWAOddsBoard, {}),
    ("FWASparkline", FWASparkline, {}),
    ("FWASignals", FWASignals, {}),
    ("FWAActivityFeed", FWAActivityFeed, {}),
    ("FWAChaseBoard", FWAChaseBoard, {}),
    # Same two-state reason as TTTSignals: the note under this title is empty
    # only while the title itself is carrying the `as of` stamp. A dead log
    # source fills it, and that is the state a reader looks hardest at.
    ("FWASettlementTable-degraded", FWASettlementTable, {
        "settle_available": False,
    }),
    ("FWASettlementTable-healthy", FWASettlementTable, {
        "settlement_mix": [
            {"label": "sold back", "count": 9, "share": 0.9, "eth": 1.2},
        ],
        "crown_history": [],
        "settle_as_of_ts": 1_700_000_000,
    }),
]

#: Wide and tall enough that nothing here is width-tiered down to a title or
#: floored into its own scrollbar; this test is about a row, not about fitting.
_SIZE = (120, 26)


@pytest.mark.parametrize(
    "widget_cls, payload",
    [(cls, payload) for _id, cls, payload in _PANELS],
    ids=[pid for pid, _cls, _payload in _PANELS],
)
async def test_every_panel_paints_a_blank_row_under_its_title(
    widget_cls, payload
) -> None:
    """Row 0 title, row 1 blank, row 2 content -- on the composited screen."""
    rows = await composite_lines(
        widget_cls, _SIZE, css_path=CSS_PATH, region_only=True, **payload
    )

    name = widget_cls.__name__
    assert rows[0].strip(), f"{name} paints no title row at all"
    assert not rows[1].strip(), (
        f"{name} paints content directly under its title -- the blank row "
        "every dashboard's title carries is missing. Composited rows: "
        f"{rows[:4]}"
    )
    assert rows[2].strip(), (
        f"{name} paints nothing under the blank row, so the blank above is "
        "this panel being empty rather than its title's own row. Composited "
        f"rows: {rows[:4]}"
    )


def test_the_panel_table_names_every_widget_once_per_state() -> None:
    """The ids are unique, so a failure names exactly one case.

    Two widgets appear twice by design (``TTTSignals``, ``FWASettlementTable``)
    and pytest would otherwise suffix them ``0``/``1``, which says nothing
    about which state broke. This pins the hand-written ids instead.
    """
    ids = [pid for pid, _cls, _payload in _PANELS]
    assert len(ids) == len(set(ids)), "duplicate parametrisation id"
    for pid, cls, _payload in _PANELS:
        assert pid.split("-")[0] == cls.__name__, (
            f"id {pid!r} does not name its widget {cls.__name__}"
        )
