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

from maxpane_dashboard.analytics import fwa_signals as _signals
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
    WIDEN_HINT,
    FWASignals,
    _fmt_emissions,
    _fmt_pool_temp,
    _visible_len,
)

_plain_len = _visible_len


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


# -- measured slot widths ----------------------------------------------
#
# A widget mounted alone in ``_Harness`` fills the terminal, so running the
# harness at these sizes reproduces the width each widget actually gets from
# ``#bottom-row``'s 3fr/2fr/2fr split. Measured against the real
# ``minimal.tcss`` at 200- and 140-column terminals (WP-13's screen sizes):
#
#   terminal   feed   chase   settlement
#   200         83      55        56
#   140         58      38        38
#
# The feed numbers are the *container*; its RichLog has ``padding: 0 1`` and so
# renders two columns narrower (81 / 56).
WIDE_FEED = (83, 24)
NARROW_FEED = (58, 24)
#: Wide enough for the chase board's `full` tier. Raised from 55 when the ODDS
#: column went from 6 to 9 columns: the board ranks the *least* likely
#: positions, whose odds are ~1e-5%, and three decimals rendered every row as
#: `0.000%`.
WIDE_TABLE = (58, 24)
NARROW_TABLE = (38, 24)


def _static_text(widget: Static) -> str:
    """Plain text of a ``Static``'s current content (markup included)."""
    return str(getattr(widget, "_Static__content", ""))


def _log_text(log: RichLog) -> str:
    """All rendered lines of a ``RichLog``, joined."""
    return "\n".join(strip.text for strip in log.lines)


def _none_payload(widget_name: str) -> dict:
    return {key: None for key in FWA_WIDGET_SIGNATURES[widget_name]}


# -- fixtures ----------------------------------------------------------

#: The five signal rows, built by the **real** builders with pinned inputs
#: (WP-20).  These were hand-written and carried ``"color": "green"`` /
#: ``"red"`` and ``"indicator": "■"`` -- none of which
#: ``analytics/fwa_signals.py`` can emit.  Its vocabulary is
#: ``$success | $warning | $error | dim`` and its indicator is always ``●``
#: (WP-19 moved the colours to theme variables because the CSS name ``green``
#: is ``#008000``, which fails AA against every possible background).  A panel
#: test fed colours the product cannot produce measures the fixture, not the
#: panel.  Clocks are injected, so this reads the same on both sides of the
#: 2026-08-04 emissions stop.
_EMISSION_START = 1_784_574_083
_EMISSION_DURATION = 1_785_870_083 - _EMISSION_START

_SIGNAL_PAYLOAD = {
    "pool_temp_signal": _signals.pool_temp_signal(
        seconds_since_last_request=4_000,
        token_share_bps=10_000,
        hot_gap=60,
        cold_gap=3_600,
    ).model_dump(),
    "buy_gate_signal": _signals.buy_gate_signal(False).model_dump(),
    "emissions_signal": _signals.emissions_signal(
        _EMISSION_START + _EMISSION_DURATION + 21 * 86_400,
        _EMISSION_START,
        _EMISSION_DURATION,
    ).model_dump(),
    "vrf_queue_signal": _signals.vrf_queue_signal(
        last_issued=100,
        next_to_process=100,
        pending=0,
        unsettled=0,
        unfulfilled_vrf=0,
        subscription_balance=10**18,
        minimum_buffer=10**17,
    ).model_dump(),
    "param_drift_signal": _signals.param_drift_signal(
        [{"key": 15, "value": 100, "block_number": 25_592_190, "ts": 1_784_900_000}],
        {},
    ).model_dump(),
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

#: The manager's real wording is long -- WP-13's screen fixture carries
#: ``accepted bid · paid in $FWA`` (27 chars), which no narrow line can hold.
#: This is the payload that used to produce the ``→ a`` clip.
_LONG_LABEL_EVENTS = [
    {
        **event,
        "outcome_label": "accepted bid · paid in $FWA",
        "collection_name": "Ten Thousand Tokens",
    }
    for event in _DRAW_EVENTS
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
async def test_chase_board_odds_have_enough_digits_to_differ():
    widget = FWAChaseBoard()
    app = _Harness(widget)
    async with app.run_test():
        widget.update_data()
        widget.update_data(**_none_payload("FWAChaseBoard"))
        widget.update_data(chase_positions=_CHASE_POSITIONS, chase_available=True)
        table = widget.query_one("#fwa-chase-dt", DataTable)
        assert table.row_count == len(_CHASE_POSITIONS)
        first = [str(cell) for cell in table.get_row_at(0)]
        assert "0.000005%" in first, (
            "the chase board ranks the least likely positions, so three "
            "decimals rendered every row as 0.000% and the column said nothing"
        )
        assert "0" not in [cell.strip() for cell in first]
        assert "1,378×" in first
        assert "221.00" in first
        second = [str(cell) for cell in table.get_row_at(1)]
        assert "0.000100%" in second  # four zeros still resolve, unlike at 3dp
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
        # The sell-back headline no longer lives here: it moved to the
        # SIGNALS panel, where the reader is already looking for statements
        # about how the protocol behaves, and this widget got its row of
        # vertical space back. It is still computed from these same rows --
        # see tests/analytics/test_fwa_signals.py::test_sellback_*.
        note = _static_text(widget.query_one("#fwa-settle-note", Static))
        assert "sell straight back" not in note
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


# -- responsive layout -------------------------------------------------
#
# WP-13 found the real defect these cover: at 140 columns the chase board lost
# ODDS and JACKPOT -- the two columns that carry its meaning -- and still
# looked complete. Every one of these asserts both halves: the narrow layout
# says what it dropped, and the wide layout says nothing because it dropped
# nothing.


@pytest.mark.asyncio
async def test_chase_board_keeps_odds_and_jackpot_when_narrow():
    widget = FWAChaseBoard()
    app = _Harness(widget)
    async with app.run_test(size=NARROW_TABLE):
        widget.update_data(chase_positions=_CHASE_POSITIONS, chase_available=True)
        table = widget.query_one("#fwa-chase-dt", DataTable)
        headers = [str(col.label) for col in table.columns.values()]
        assert "ODDS" in headers
        assert "JACKPOT" in headers
        assert "TOKEN" not in headers  # dropped first, by design
        row = " ".join(str(c) for c in table.get_row_at(0))
        assert "0.000005%" in row and "1,378×" in row


@pytest.mark.asyncio
async def test_chase_board_narrow_announces_dropped_columns():
    widget = FWAChaseBoard()
    app = _Harness(widget)
    async with app.run_test(size=NARROW_TABLE):
        widget.update_data(chase_positions=_CHASE_POSITIONS, chase_available=True)
        title = _static_text(widget.query_one("#fwa-chase-title", Static))
        assert "widen" in title
        assert "TOKEN" in title and "BACKING" in title
        # The marker must fit the slot, or it cannot be read.
        assert _plain_len(title) <= NARROW_TABLE[0] - 2


@pytest.mark.asyncio
async def test_chase_board_wide_shows_every_column_and_no_hint():
    widget = FWAChaseBoard()
    app = _Harness(widget)
    async with app.run_test(size=WIDE_TABLE):
        widget.update_data(chase_positions=_CHASE_POSITIONS, chase_available=True)
        table = widget.query_one("#fwa-chase-dt", DataTable)
        headers = [str(col.label) for col in table.columns.values()]
        assert headers == ["#", "COLLECTION", "TOKEN", "BACKING", "ODDS", "JACKPOT"]
        title = _static_text(widget.query_one("#fwa-chase-title", Static))
        assert "widen" not in title
        row = " ".join(str(c) for c in table.get_row_at(0))
        # _CHASE_POSITIONS[0] is CryptoPunks #3100 -- the token id the narrow
        # layout drops and this one must therefore show.
        assert "3100" in row and "221.00" in row


@pytest.mark.asyncio
async def test_settlement_narrow_drops_count_and_says_so():
    widget = FWASettlementTable()
    app = _Harness(widget)
    async with app.run_test(size=NARROW_TABLE):
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
        headers = [str(col.label) for col in table.columns.values()]
        assert "SHARE" in headers  # the mix *is* the share column
        assert "COUNT" not in headers
        title = _static_text(widget.query_one("#fwa-settle-title", Static))
        assert "widen" in title and "COUNT" in title
        assert _plain_len(title) <= NARROW_TABLE[0] - 2
        # The staleness stamp moves to the note rather than being dropped.
        note = _static_text(widget.query_one("#fwa-settle-note", Static))
        assert "as of" in note
        assert _plain_len(note) <= NARROW_TABLE[0] - 2
        joined = " ".join(
            " ".join(str(c) for c in table.get_row_at(i))
            for i in range(table.row_count)
        )
        assert "100.00%" in joined
        # Labels are abbreviated, never cut into a different meaning.
        assert "$FW " not in joined and "$FW…" not in joined


@pytest.mark.asyncio
async def test_settlement_wide_keeps_count_and_stamps_the_title():
    widget = FWASettlementTable()
    app = _Harness(widget)
    async with app.run_test(size=WIDE_TABLE):
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
        headers = [str(col.label) for col in table.columns.values()]
        assert "COUNT" in headers and "ETH" in headers
        title = _static_text(widget.query_one("#fwa-settle-title", Static))
        assert "widen" not in title
        assert "as of" in title


@pytest.mark.asyncio
async def test_settlement_crown_totals_survive_a_short_box():
    """The crown TOTAL row carries figures that exist nowhere else."""
    widget = FWASettlementTable()
    app = _Harness(widget)
    async with app.run_test(size=(56, 16)):
        widget.update_data(
            settlement_mix=_SETTLEMENT_MIX,
            crown_history=_CROWN_HISTORY * 3,  # more holders than rows
            crown_sets_total=33,
            crown_payouts_total=12,
            crown_paid_eth=91.096,
            settle_available=True,
        )
        table = widget.query_one("#fwa-settle-dt", DataTable)
        rows = [
            " ".join(str(c) for c in table.get_row_at(i))
            for i in range(table.row_count)
        ]
        joined = "\n".join(rows)
        assert "33 sets" in joined and "91.096" in joined
        # A shortened holder list says that it is shortened.
        assert "top" in joined.lower()


@pytest.mark.asyncio
async def test_activity_feed_narrow_abbreviates_outcome_never_truncates_it():
    widget = FWAActivityFeed()
    app = _Harness(widget)
    async with app.run_test(size=NARROW_FEED):
        widget.update_data(draw_events=_LONG_LABEL_EVENTS, feed_available=True)
        log = widget.query_one("#fwa-activity-log", RichLog)
        text = _log_text(log)
        assert len(log.lines) == len(_LONG_LABEL_EVENTS)  # not vacuous
        # The full label does not fit; the short *word* form is used instead of
        # a cut like "→ a".
        assert "sold ($FWA)" in text
        assert "accepted bid · pai" not in text
        for line in text.splitlines():
            assert len(line) <= NARROW_FEED[0] - 2
        title = _static_text(widget.query_one("#fwa-feed-title", Static))
        assert "widen" in title


@pytest.mark.asyncio
async def test_activity_feed_wide_keeps_collection_and_amount():
    widget = FWAActivityFeed()
    app = _Harness(widget)
    async with app.run_test(size=WIDE_FEED):
        widget.update_data(draw_events=_DRAW_EVENTS, feed_available=True)
        log = widget.query_one("#fwa-activity-log", RichLog)
        text = _log_text(log)
        assert "drew Nakamigos #4471" in text
        assert "0.118 ETH" in text
        title = _static_text(widget.query_one("#fwa-feed-title", Static))
        assert "widen" not in title


@pytest.mark.asyncio
async def test_activity_feed_narrow_keeps_the_as_of_stamp():
    """Stale-presented-as-live is the one thing narrowness may not cause."""
    widget = FWAActivityFeed()
    app = _Harness(widget)
    async with app.run_test(size=NARROW_FEED):
        widget.update_data(draw_events=_DRAW_EVENTS, feed_available=True)
        widget.update_data(
            draw_events=None,
            feed_available=False,
            feed_unavailable_reason="logs down",
            feed_as_of_ts=1784900000,
        )
        title = _static_text(widget.query_one("#fwa-feed-title", Static))
        assert "as of" in title
        assert UNAVAILABLE_LINE in _log_text(
            widget.query_one("#fwa-activity-log", RichLog)
        )


@pytest.mark.asyncio
async def test_signals_clipped_row_is_announced():
    widget = FWASignals()
    app = _Harness(widget)
    async with app.run_test(size=(30, 12)):
        widget.update_data(**_SIGNAL_PAYLOAD)
        title = _static_text(widget.query_one("#fwa-sig-title", Static))
        assert WIDEN_HINT in title
    widget = FWASignals()
    app = _Harness(widget)
    async with app.run_test(size=(78, 12)):
        widget.update_data(**_SIGNAL_PAYLOAD)
        title = _static_text(widget.query_one("#fwa-sig-title", Static))
        assert WIDEN_HINT not in title


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


@pytest.mark.asyncio
async def test_settlement_eth_column_shows_the_amounts():
    """The ETH column must render the amounts, not a hardcoded dash.

    It shipped rendering `—` on every row: the column existed in the layout and
    nothing ever filled it, and no test looked. This asserts the cell *and* the
    TOTAL, so replacing either with a constant goes red.
    """
    widget = FWASettlementTable()
    app = _Harness(widget)
    async with app.run_test(size=WIDE_TABLE):
        widget.update_data(
            settlement_mix=[
                {"outcome": "bid_fwa", "label": "Accept bid, paid in $FWA",
                 "count": 3, "share_pct": 60.0, "eth_total": 12.5},
                {"outcome": "bid_eth", "label": "Accept bid, paid in ETH",
                 "count": 1, "share_pct": 20.0, "eth_total": 4.25},
                {"outcome": "forced", "label": "Force-finalized",
                 "count": 1, "share_pct": 20.0, "eth_total": None},
            ],
            settle_available=True,
        )
        table = widget.query_one("#fwa-settle-dt", DataTable)
        cells = [
            " ".join(str(c) for c in table.get_row_at(i))
            for i in range(table.row_count)
        ]
        joined = "\n".join(cells)

        assert "12.500" in joined, "the per-outcome ETH amount never rendered"
        assert "4.250" in joined
        # 12.5 + 4.25, with the amount-less outcome contributing nothing
        assert "16.750" in joined, "the TOTAL row did not sum the ETH column"


@pytest.mark.asyncio
async def test_settlement_eth_total_is_a_dash_when_nothing_carries_an_amount():
    """A mix with no ETH data totals to a dash, never 0.000.

    The windowed-restore path rebuilds the mix from counts alone; claiming
    those settlements moved 0 ETH would be a measurement nobody took.
    """
    widget = FWASettlementTable()
    app = _Harness(widget)
    async with app.run_test(size=WIDE_TABLE):
        widget.update_data(
            settlement_mix=[
                {"outcome": "bid_fwa", "label": "Accept bid, paid in $FWA",
                 "count": 3, "share_pct": 100.0, "eth_total": None},
            ],
            settle_available=True,
        )
        table = widget.query_one("#fwa-settle-dt", DataTable)
        joined = "\n".join(
            " ".join(str(c) for c in table.get_row_at(i))
            for i in range(table.row_count)
        )

        assert "0.000" not in joined
