"""Headless Textual tests for FWA widgets group B (WP-11).

Covers the four widgets of PRD §5 that WP-11 owns:

* ``FWASignals``          -- five signal rows
* ``FWAActivityFeed``     -- live draws, and the mandatory degraded states
* ``FWAChaseBoard``       -- richest positions, ~0% odds, jackpot ratio
* ``FWASettlementTable``  -- outcome mix + crown history

Each widget is mounted in a tiny ``App`` via ``App.run_test()`` and
``update_data()`` is exercised three ways:

* (a) no args
* (b) all-``None`` payload built from ``FWA_WIDGET_SIGNATURES``
* (c) a representative full payload

Every call must complete without raising. Content assertions go through the
``DataTable`` / ``RichLog`` APIs, or through the module-level pure formatters.

Group A's widgets live in ``test_fwa_widgets_a.py``; the two files are disjoint.
Zero network access.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, RichLog, Static

from maxpane_dashboard.data.fwa_models import FWA_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fwa.fwa_activity_feed import (
    UNAVAILABLE_LINE,
    FWAActivityFeed,
)
from maxpane_dashboard.widgets.fwa.fwa_chase_board import CROWN_GLYPH, FWAChaseBoard
from maxpane_dashboard.widgets.fwa.fwa_settlement_table import (
    UNAVAILABLE_TEXT,
    FWASettlementTable,
)
from maxpane_dashboard.widgets.fwa.fwa_signals import (
    EMISSIONS_ENDED,
    FWASignals,
    _fmt_emissions,
    _fmt_pool_temp,
)


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _static_text(widget: Static) -> str:
    """Plain text of a ``Static``'s current content (markup included)."""
    return str(getattr(widget, "_Static__content", ""))


def _log_text(log: RichLog) -> str:
    """All rendered lines of a ``RichLog``, joined."""
    return "\n".join(strip.text for strip in log.lines)


def _none_payload(widget_name: str) -> dict:
    return {key: None for key in FWA_WIDGET_SIGNATURES[widget_name]}


# -- fixtures ----------------------------------------------------------

_SIGNAL_PAYLOAD = {
    "pool_temp_signal": {
        "label": "pool temp",
        "value_str": "COLD 41m · surcharge → YOU (100%)",
        "indicator": "●",
        "color": "green",
    },
    "buy_gate_signal": {
        "label": "buy gate",
        "value_str": "CLOSED · outside buys blocked",
        "indicator": "■",
        "color": "red",
    },
    "emissions_signal": {
        "label": "emissions",
        "value_str": EMISSIONS_ENDED,
        "indicator": "●",
        "color": "dim",
    },
    "vrf_queue_signal": {
        "label": "vrf queue",
        "value_str": "0 pending requests",
        "indicator": "●",
        "color": "green",
    },
    "param_drift_signal": {
        "label": "param drift",
        "value_str": "no drift · 9 params live",
        "indicator": "●",
        "color": "green",
    },
}

_DRAW_EVENTS = [
    {
        "ts": 1784900000,
        "block_number": 25612701,
        "tx_hash": "0xabc",
        "purchaser": "0xABCD000000000000000000000000000000001234",
        "collection": "0x1111111111111111111111111111111111111111",
        "collection_name": "Nakamigos",
        "token_id": 4471,
        "outcome": "bid_fwa",
        "outcome_label": "sold back ($FWA)",
        "amount_eth": 0.118,
    },
    {
        "ts": 1784899000,
        "block_number": 25612600,
        "tx_hash": "0xdef",
        "purchaser": "0xBEEF000000000000000000000000000000005678",
        "collection": "0x2222222222222222222222222222222222222222",
        "collection_name": None,
        "token_id": None,
        "outcome": "kept",
        "outcome_label": "kept the NFT",
        "amount_eth": 0.0,
    },
    {
        "ts": 1784898000,
        "block_number": 25612500,
        "tx_hash": "0x123",
        "purchaser": "0xCAFE000000000000000000000000000000009999",
        "collection": "0x3333333333333333333333333333333333333333",
        "collection_name": "Art Blocks",
        "token_id": 78000123,
        "outcome": "relist",
        "outcome_label": "relisted",
        "amount_eth": 1.5,
    },
]

_CHASE_POSITIONS = [
    {
        "rank": 1,
        "listing_id": 56508,
        "collection": "0x4444444444444444444444444444444444444444",
        "collection_name": "CryptoPunks",
        "token_id": 3100,
        "backing_eth": 221.0,
        "odds_pct": 0.0000045,
        "expected_draws": 221000.0,
        "jackpot_ratio": 1378.0,
        "sellback_eth": 187.85,
    },
    {
        "rank": 2,
        "listing_id": 12345,
        "collection": "0x5555555555555555555555555555555555555555",
        "collection_name": None,
        "token_id": None,
        "backing_eth": 88.5,
        "odds_pct": 0.0001,
        "expected_draws": None,
        "jackpot_ratio": None,
        "sellback_eth": None,
    },
]

_SETTLEMENT_MIX = [
    {"outcome": "bid_fwa", "label": "accept bid, $FWA", "count": 1932, "share_pct": 73.92},
    {"outcome": "bid_eth", "label": "accept bid, ETH", "count": 362, "share_pct": 13.84},
    {"outcome": "relist", "label": "relist", "count": 200, "share_pct": 7.64},
    {"outcome": "kept", "label": "keep the NFT", "count": 120, "share_pct": 4.60},
    {"outcome": "forced", "label": "force-finalized", "count": 0, "share_pct": 0.0},
]

_CROWN_HISTORY = [
    {
        "rank": 1,
        "holder": "0xAAAA000000000000000000000000000000001111",
        "reigns": 4,
        "payout_eth": 41.5,
        "last_block": 25612701,
        "last_ts": 1784900000,
    },
    {
        "rank": 2,
        "holder": "0xBBBB000000000000000000000000000000002222",
        "reigns": 2,
        "payout_eth": 12.0,
        "last_block": 25600000,
        "last_ts": 1784800000,
    },
]


# -- signals -----------------------------------------------------------


@pytest.mark.asyncio
async def test_signals_renders_five_rows():
    widget = FWASignals()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(**_SIGNAL_PAYLOAD)
        rows = [
            "#fwa-sig-pool-temp",
            "#fwa-sig-buy-gate",
            "#fwa-sig-emissions",
            "#fwa-sig-vrf",
            "#fwa-sig-drift",
        ]
        assert len(rows) == 5
        for selector in rows:
            text = _static_text(widget.query_one(selector, Static))
            assert text.strip(), f"{selector} rendered empty"
            assert "--" not in text


@pytest.mark.asyncio
async def test_signals_none_payload_safe():
    widget = FWASignals()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(**_none_payload("FWASignals"))
        for selector in (
            "#fwa-sig-pool-temp",
            "#fwa-sig-buy-gate",
            "#fwa-sig-emissions",
            "#fwa-sig-vrf",
            "#fwa-sig-drift",
        ):
            assert "--" in _static_text(widget.query_one(selector, Static))
        # Malformed payloads must not raise either.
        widget.update_data(
            pool_temp_signal="not a dict",
            buy_gate_signal=[],
            emissions_signal={},
            vrf_queue_signal={"value_str": None},
            param_drift_signal={"color": "green"},
        )


def test_signals_pool_temp_direction_in_words():
    hot = _fmt_pool_temp(
        {"value_str": "HOT 12s · surcharge → depositors", "color": "red"}
    )
    assert "→ depositors" in hot
    cold = _fmt_pool_temp(
        {"value_str": "COLD 41m · surcharge → YOU (100%)", "color": "green"}
    )
    assert "→ YOU" in cold
    # Colour-only payload gets an explicit textual fallback.
    bare = _fmt_pool_temp({"value_str": "38°", "color": "#f59e0b"})
    assert "direction unknown" in bare


def test_signals_emissions_never_negative_countdown():
    # The primary case: the window has elapsed.
    ended = _fmt_emissions({"value_str": EMISSIONS_ENDED, "color": "dim"})
    assert EMISSIONS_ENDED in ended
    assert "-" not in ended.replace("[/]", "")
    # A countdown that ran past the stop is rewritten, never shown negative.
    for bad in ("-2d 3h", "−13h 04m", "ends in -41s"):
        out = _fmt_emissions({"value_str": bad, "color": "red"})
        assert EMISSIONS_ENDED in out
        assert bad not in out
    # A live countdown before the stop still renders verbatim.
    live = _fmt_emissions({"value_str": "8d 04h left", "color": "green"})
    assert "8d 04h left" in live


# -- activity feed -----------------------------------------------------


@pytest.mark.asyncio
async def test_activity_feed_line_count():
    widget = FWAActivityFeed()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(**_none_payload("FWAActivityFeed"))
        widget.update_data(
            draw_events=_DRAW_EVENTS,
            feed_available=True,
            feed_unavailable_reason=None,
            feed_as_of_ts=1784900000,
        )
        log = widget.query_one("#fwa-activity-log", RichLog)
        assert len(log.lines) == len(_DRAW_EVENTS)
        text = _log_text(log)
        # Outcome is spelled out, not only colour-coded.
        assert "sold back ($FWA)" in text
        assert "kept the NFT" in text
        assert "Nakamigos #4471" in text
        assert "0.118 ETH" in text


@pytest.mark.asyncio
async def test_activity_feed_unavailable_renders_explicit_line():
    widget = FWAActivityFeed()
    app = _Harness(widget)
    async with app.run_test():
        # Unavailable from a cold start: explicit line, never blank.
        widget.update_data(
            draw_events=None,
            feed_available=False,
            feed_unavailable_reason="log endpoint 429",
            feed_as_of_ts=None,
        )
        log = widget.query_one("#fwa-activity-log", RichLog)
        text = _log_text(log)
        assert UNAVAILABLE_LINE in text
        assert "log endpoint 429" in text
        assert len(log.lines) >= 1
        title = _static_text(widget.query_one("#fwa-feed-title", Static))
        assert "unavailable" in title


@pytest.mark.asyncio
async def test_activity_feed_unavailable_keeps_last_good_with_as_of_header():
    widget = FWAActivityFeed()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(draw_events=_DRAW_EVENTS, feed_available=True)
        widget.update_data(
            draw_events=None,
            feed_available=False,
            feed_unavailable_reason="logs down",
            feed_as_of_ts=1784900000,
        )
        log = widget.query_one("#fwa-activity-log", RichLog)
        text = _log_text(log)
        assert UNAVAILABLE_LINE in text
        # Last-good content is kept...
        assert "Nakamigos #4471" in text
        # ...and labelled as of a time, never presented as live.
        title = _static_text(widget.query_one("#fwa-feed-title", Static))
        assert "as of" in title


@pytest.mark.asyncio
async def test_activity_feed_available_but_empty_is_not_blank():
    widget = FWAActivityFeed()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(draw_events=[], feed_available=True)
        log = widget.query_one("#fwa-activity-log", RichLog)
        assert len(log.lines) == 1
        assert "No draws" in _log_text(log)


# -- chase board -------------------------------------------------------


@pytest.mark.asyncio
async def test_chase_board_zero_odds_renders_three_decimals():
    widget = FWAChaseBoard()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(**_none_payload("FWAChaseBoard"))
        widget.update_data(chase_positions=_CHASE_POSITIONS, chase_available=True)
        table = widget.query_one("#fwa-chase-dt", DataTable)
        assert table.row_count == len(_CHASE_POSITIONS)
        first = [str(cell) for cell in table.get_row_at(0)]
        assert "0.000%" in first
        assert "0" not in [cell.strip() for cell in first]
        assert "1,378×" in first
        assert "221.00" in first
        second = [str(cell) for cell in table.get_row_at(1)]
        assert "0.000%" in second  # 0.0001 still renders three decimals
        assert "--" in second  # missing jackpot ratio


@pytest.mark.asyncio
async def test_chase_board_crown_coincidence_noted():
    widget = FWAChaseBoard()
    app = _Harness(widget)
    async with app.run_test():
        # Without a crown id nothing is claimed.
        widget.update_data(chase_positions=_CHASE_POSITIONS, chase_available=True)
        note = widget.query_one("#fwa-chase-note", Static)
        assert note.display is False

        # topListingId == the max-backing listing: say so.
        widget.update_data(
            chase_positions=_CHASE_POSITIONS,
            chase_available=True,
            crown_listing_id=56508,
        )
        assert note.display is True
        note_text = _static_text(note)
        assert "56508" in note_text
        assert "crown and chase #1 are one position" in note_text
        assert CROWN_GLYPH in note_text
        table = widget.query_one("#fwa-chase-dt", DataTable)
        assert CROWN_GLYPH in str(table.get_row_at(0)[0])

        # The crown moves: no coincidence, no claim.
        widget.update_data(
            chase_positions=_CHASE_POSITIONS,
            chase_available=True,
            crown_listing_id=99999,
        )
        assert note.display is False


@pytest.mark.asyncio
async def test_chase_board_unavailable_renders_explicit_state():
    widget = FWAChaseBoard()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(chase_positions=None, chase_available=False)
        table = widget.query_one("#fwa-chase-dt", DataTable)
        assert table.row_count == 1
        assert "unavailable" in " ".join(str(c) for c in table.get_row_at(0))
        assert "unavailable" in _static_text(
            widget.query_one("#fwa-chase-note", Static)
        )


# -- settlement table --------------------------------------------------


@pytest.mark.asyncio
async def test_settlement_shares_sum_displayed_as_100():
    widget = FWASettlementTable()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(**_none_payload("FWASettlementTable"))
        widget.update_data(
            settlement_mix=_SETTLEMENT_MIX,
            crown_history=_CROWN_HISTORY,
            crown_sets_total=33,
            crown_payouts_total=12,
            crown_paid_eth=91.096,
            settle_available=True,
            settle_as_of_ts=1784900000,
        )
        table = widget.query_one("#fwa-settle-dt", DataTable)
        cells = [
            " ".join(str(c) for c in table.get_row_at(i))
            for i in range(table.row_count)
        ]
        joined = "\n".join(cells)
        assert "100.00%" in joined
        assert "73.92%" in joined and "0.00%" in joined
        # crown section: per-holder aggregation, 4 reigns for one wallet
        assert "0xAAAA..1111" in joined
        assert "33 sets" in joined and "12 paid" in joined and "91.096" in joined
        # the headline stat is computed from the rows, not hardcoded
        note = _static_text(widget.query_one("#fwa-settle-note", Static))
        assert "87.76%" in note
        assert "sell straight back" in note
        assert "4.60% keep the NFT" in note
        title = _static_text(widget.query_one("#fwa-settle-title", Static))
        assert "as of" in title


@pytest.mark.asyncio
async def test_settlement_table_unavailable_renders_explicit_state():
    widget = FWASettlementTable()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data(
            settlement_mix=None,
            crown_history=None,
            crown_sets_total=None,
            crown_payouts_total=None,
            crown_paid_eth=None,
            settle_available=False,
            settle_as_of_ts=None,
        )
        table = widget.query_one("#fwa-settle-dt", DataTable)
        assert table.row_count >= 1
        joined = " ".join(
            " ".join(str(c) for c in table.get_row_at(i))
            for i in range(table.row_count)
        )
        assert UNAVAILABLE_TEXT in joined
        assert "unavailable" in _static_text(
            widget.query_one("#fwa-settle-title", Static)
        )
        assert UNAVAILABLE_TEXT in _static_text(
            widget.query_one("#fwa-settle-note", Static)
        )


# -- frozen contract ---------------------------------------------------


@pytest.mark.asyncio
async def test_group_b_widgets_accept_frozen_signature_kwargs():
    """Each widget accepts exactly its ``FWA_WIDGET_SIGNATURES`` kwargs."""
    import inspect

    cases = [
        ("FWASignals", FWASignals),
        ("FWAActivityFeed", FWAActivityFeed),
        ("FWAChaseBoard", FWAChaseBoard),
        ("FWASettlementTable", FWASettlementTable),
    ]
    for name, cls in cases:
        expected = set(FWA_WIDGET_SIGNATURES[name])
        params = inspect.signature(cls.update_data).parameters
        declared = {
            key
            for key, param in params.items()
            if key != "self" and param.kind is not param.VAR_KEYWORD
        }
        assert expected <= declared, f"{name} is missing {expected - declared}"
        widget = cls()
        app = _Harness(widget)
        async with app.run_test():
            widget.update_data(**{key: None for key in expected})
