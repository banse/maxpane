"""Every FWA address carries a copy icon (PRD: docs/address_copy_PRD.md).

Renders the full ``FWAScreen`` with a representative payload and asserts,
against the **composited** screen (``icon_targets``, never a content string):
every ``⧉`` on screen copies a known address from the payload, and clicking
one actually copies it (through ``CopyRecorder``, which never touches the
real clipboard).

Adapted from the dispatch template's sample code:

* the harness is ``tests.screens.test_fwa_screen._Harness`` (found via
  ``dir(T)`` + ``n.endswith("Harness")``, same as the template's lookup —
  ``_Harness`` sorts before ``_ThemedHarness`` alphabetically, so the same
  loop the template gave picks the plain one, and this file pins that
  instead of hand-naming it, so a future rename of the harness is still
  found);
* the fake manager is ``tests.screens.test_fwa_screen._FakeManager``, whose
  constructor is ``(payload: dict | None = None, raises: bool = False)`` —
  the template's ``T._FakeManager(payload)`` already matches it positionally.
"""

from __future__ import annotations

import pytest

from tests.screens import test_fwa_screen as T
from tests.widgets.address_probe import CopyRecorder, icon_targets
from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
from maxpane_dashboard.analytics import fwa_signals as sig
from maxpane_dashboard.widgets.address import COPY_GLYPH, address_text, is_address
from maxpane_dashboard.widgets.fwa.fwa_signals import FWASignals


def _fwa_harness() -> type:
    """``tests.screens.test_fwa_screen``'s plain ``App`` harness.

    Factored out once here because four tests in this file now need it (the
    fix-round-2 SIGNALS tests included, which must composite the real
    ``FWAScreen`` rather than a bare widget -- see the note above
    ``test_an_address_typed_drift_signal_shows_its_icon_and_copies_it``).
    """
    return next(
        getattr(T, n)
        for n in dir(T)
        if isinstance(getattr(T, n), type) and n.endswith("Harness")
    )


def _addresses_in(payload) -> set[str]:
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str) and is_address(v):
            found.add(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(payload)
    return found


async def test_fwa_renders_icons_and_every_icon_copies_a_payload_address():
    payload = T._sample_data()
    harness = _fwa_harness()

    class _CopyHarness(CopyRecorder, harness):
        pass

    app = _CopyHarness(T.FWAScreen(T._FakeManager(payload), poll_interval=30))
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert targets, "no copy icon on the FWA dashboard"
        known = _addresses_in(payload)
        for x, y, address in targets:
            assert address in known, address
        x, y, address = targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]


async def test_every_visible_address_field_shows_an_icon():
    """Broader than the first test: every one of the screen's known
    address-bearing fields is represented among the copied targets, not just
    "at least one icon exists somewhere".
    """
    payload = T._sample_data()
    harness = _fwa_harness()
    app = harness(T.FWAScreen(T._FakeManager(payload), poll_interval=30))
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        copied = {address for _x, _y, address in icon_targets(app) if address}

        # The odds board default view is visible; the activity feed is not
        # (toggled in with `c`), so only the odds board's own addresses are
        # asserted here.
        assert payload["crown_holder"] in copied
        for row in payload["collection_odds"]:
            assert row["address"] in copied
        for row in payload["chase_positions"]:
            assert row["collection"] in copied
        for row in payload["crown_history"]:
            assert row["holder"] in copied


def test_a_named_holder_shows_its_name_and_copies_its_address():
    holder = "0x" + "12ab34cd56" * 4
    t = address_text(holder, label="whale.eth", width=20)
    assert t.plain == "whale.eth " + COPY_GLYPH


# -- SIGNALS panel: the PARAM DRIFT row (fix rounds 1 and 2) ----------------
#
# Unlike the other six sites, this one is not a plain field -- the value it
# renders is composed prose (``analytics/fwa_signals.py``'s
# ``param_drift_signal``) that may or may not contain a 0x value, and if it
# does that value may be a genuine address or a bytes32 hash. Both cases are
# driven through the real analytics builder, not a hand-typed payload, so the
# fixture is exactly what the manager could hand the widget.
#
# **Round 1 mounted a bare ``FWASignals`` at 100 columns and missed a real
# defect**: at 143/170/200 -- every documented terminal width up to 240 --
# the real SIGNALS rail, inside the real ``FWAScreen``, is narrower than a
# bare widget's 100-column harness ever exercised, and the panel's own CSS
# ellipsis cropped the row *before* the icon at the end of it
# (`tests/screens/test_address_icons_everywhere.py`'s FWA sweep is what
# caught it). Both tests below composite the real screen at
# ``FULL_LAYOUT_COLUMNS`` instead, through the same harness/fake-manager
# shape the other tests in this file already use.


async def test_an_address_typed_drift_signal_shows_its_icon_and_copies_it():
    # Deliberately not one of `T._sample_data()`'s own addresses (0x11/0x22/
    # 0x33/0x44/0xab repeated, or `f"0x{i:040x}"` for a small `i`) -- a
    # coincidental match there would let this test pass by finding some
    # *other* widget's icon for the same-looking address instead of the
    # drift row's own, which is exactly how the first version of this
    # mutation check below went undetected.
    address = "0x" + "61" * 20
    events = [{"key": 61, "value": int(address, 16), "block_number": 25_600_000}]
    row = sig.param_drift_signal(events).model_dump()
    assert address in row["value_str"], "fixture sanity: the analytics side is untouched"

    payload = T._sample_data()
    payload["param_drift_signal"] = row
    harness = _fwa_harness()

    class _CopyHarness(CopyRecorder, harness):
        pass

    app = _CopyHarness(T.FWAScreen(T._FakeManager(payload), poll_interval=30))
    async with app.run_test(size=(FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        plain = "\n".join(
            "".join(seg.text for seg in strip)
            for strip in app.screen._compositor.render_strips()
        )
        assert address not in plain, (
            "the whole, unwindowed address reached the screen -- at this "
            f"width the row's CSS ellipsis will crop its icon off: {plain!r}"
        )

        targets = [t for t in icon_targets(app) if t[2] == address]
        assert targets, (
            f"no icon on screen at {FULL_LAYOUT_COLUMNS} columns copies the "
            "drift address -- it was cropped off the row"
        )
        x, y, copied_address = targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]


async def test_a_bytes32_typed_drift_signal_is_shortened_with_no_icon():
    value_hex = "cc" * 32
    events = [{"key": 24, "value": int(value_hex, 16), "block_number": 25_600_000}]
    # Key 24 (VRF_KEY_HASH) is constructor-only, so its own block is
    # auto-excluded as the launch write by default (tests/analytics/
    # test_fwa_signals.py::test_param_drift_bytes32_value_is_also_the_full_value
    # carries the same note); pin launch_block elsewhere so this reads as a
    # genuine post-launch change.
    row = sig.param_drift_signal(events, launch_block=1).model_dump()
    assert f"0x{value_hex}" in row["value_str"], "fixture sanity"

    payload = T._sample_data()
    payload["param_drift_signal"] = row
    harness = _fwa_harness()

    app = harness(T.FWAScreen(T._FakeManager(payload), poll_interval=30))
    async with app.run_test(size=(FULL_LAYOUT_COLUMNS, 48)) as pilot:
        await pilot.pause()
        assert not any(
            addr == f"0x{value_hex}" for _x, _y, addr in icon_targets(app)
        ), "a bytes32 value must never carry a copy icon"
        plain = "\n".join(
            "".join(seg.text for seg in strip)
            for strip in app.screen._compositor.render_strips()
        )
        # Shortened (66 characters would not fit undetected), never the raw
        # 64-hex value, and the surrounding prose survives.
        assert f"0x{value_hex}" not in plain
        assert "0xcccccccc…cccccc" in plain
        assert "VRF_KEY_HASH" in plain


# -- an unnamed address is never budgeted below the window floor (final review F1) --
#
# The helper never windows an address below ``MIN_SHORT_COLS``: a caller that
# asked for less got a wider cell than it budgeted, and whatever bounded the
# cell cut its end -- the icon, or on a RichLog line whatever came after it.
# The manager leaves ``collection_name`` / ``purchaser_name`` / ``holder_name``
# None when no name is known, so each of these is a live path.

from rich.cells import cell_len  # noqa: E402
from textual.widgets import RichLog  # noqa: E402

from maxpane_dashboard.widgets.fwa import fwa_activity_feed as _feed  # noqa: E402
from maxpane_dashboard.widgets.fwa.fwa_chase_board import FWAChaseBoard  # noqa: E402
from maxpane_dashboard.widgets.fwa.fwa_settlement_table import FWASettlementTable  # noqa: E402
from tests.widgets import test_fwa_widgets_b as B  # noqa: E402

_UNNAMED = "0x" + "9a" * 20


def _region_targets(app, widget) -> list:
    region = widget.region
    return [t for t in icon_targets(app) if region.contains(t[0], t[1])]


async def test_an_unnamed_chase_row_keeps_its_icon_on_the_real_screen_at_120():
    payload = T._sample_data()
    payload["chase_positions"] = [
        {**payload["chase_positions"][0], "collection": _UNNAMED, "collection_name": None},
    ]
    app = T._ThemedHarness(T.FWAScreen(T._FakeManager(payload), poll_interval=30))
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        board = app.screen.query_one(FWAChaseBoard)
        assert [t[2] for t in _region_targets(app, board)] == [_UNNAMED], (
            "the unnamed collection's icon was cut off the CHASE BOARD cell at 120 columns"
        )


@pytest.mark.parametrize("token_id", [4471, 78000123])
@pytest.mark.parametrize(("size", "tier"), [(B.WIDE_FEED, "full"), (B.NARROW_FEED, "compact")])
async def test_an_unnamed_feed_row_at_label_budget_keeps_icons_amount_and_eth(size, tier, token_id):
    """A row whose outcome label is exactly the label budget fits its line.

    ``78000123`` (an Art Blocks id) cannot sit beside an 11-cell address in
    either tier's collection budget, so it is shed whole rather than pushing
    the end of the line off the log.
    """
    event = {
        **B._DRAW_EVENTS[0],
        "token_id": token_id,
        "purchaser": _UNNAMED,
        "purchaser_name": None,
        "collection": "0x" + "8b" * 20,
        "collection_name": None,
        "outcome": "custom",
        "amount_eth": 0.05,
    }
    widget = _feed.FWAActivityFeed()
    app = B._Harness(widget)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        log = widget.query_one("#fwa-activity-log", RichLog)
        # The widget's own budget, so the label sits exactly at it: if the
        # budget over-counts the line's real room, the end of the line goes.
        width = widget._log_width(log)
        assert _feed._tier_for(width) == tier
        fixed = _feed._FIXED_FULL if tier == "full" else _feed._FIXED_COMPACT
        label = "x" * (width - fixed)
        widget.update_data(draw_events=[{**event, "outcome_label": label}], feed_available=True)
        await pilot.pause()
        rows = [
            "".join(seg.text for seg in strip)
            for strip in app.screen._compositor.render_strips()
        ]
        line = next((row for row in rows if f"→ {label}" in row), None)
        assert line is not None, f"the label was cropped off the line: {rows!r}"
        if tier == "full":
            assert "0.050 ETH" in line, f"the amount was cropped off the line: {line!r}"
        assert cell_len(log.lines[0].text) <= log.scrollable_content_region.width
        copied = {t[2] for t in _region_targets(app, widget)}
        assert copied == {_UNNAMED, "0x" + "8b" * 20}, copied


@pytest.mark.parametrize("columns", range(25, 41))
async def test_an_unnamed_crown_holder_keeps_its_icon_at_the_narrow_tiers(columns):
    """25-40 covers ``tiny`` from its narrowest through ``minimal``: before the
    fix, ``tiny``'s 14-cell label cut the icon at 25 and 26 columns."""
    widget = FWASettlementTable()
    app = B._Harness(widget)
    history = [{**B._CROWN_HISTORY[0], "holder": _UNNAMED}]
    async with app.run_test(size=(columns, 24)) as pilot:
        widget.update_data(
            settlement_mix=B._SETTLEMENT_MIX,
            crown_history=history,
            settle_available=True,
        )
        await pilot.pause()
        headers = [str(c.label) for c in widget.query_one("#fwa-settle-dt").columns.values()]
        assert "COUNT" not in headers, ("not a narrow tier", headers)
        assert [t[2] for t in _region_targets(app, widget)] == [_UNNAMED], (
            f"the unnamed holder's icon was cut off the label column at {columns} columns"
        )


async def test_a_narrow_crown_box_sheds_the_dollar_figure_never_the_icon():
    from maxpane_dashboard.widgets.fwa.fwa_hero_metrics import FWAHeroMetrics
    from tests.widgets import test_fwa_widgets_a as A

    widget = FWAHeroMetrics()
    app = A._Harness(widget)
    async with app.run_test(size=(80, 24)) as pilot:
        widget.update_data(**{**A._FULL_HERO, "crown_holder": _UNNAMED, "crown_holder_name": None})
        await pilot.pause()
        box = widget.query_one("#fwa-hero-crown")
        assert [t[2] for t in _region_targets(app, box)] == [_UNNAMED], (
            "the crown holder's icon was cut off a narrow hero box"
        )
    wide = FWAHeroMetrics()
    app = A._Harness(wide)
    async with app.run_test(size=(FULL_LAYOUT_COLUMNS, 24)) as pilot:
        wide.update_data(**{**A._FULL_HERO, "crown_holder": _UNNAMED, "crown_holder_name": None})
        await pilot.pause()
        box = wide.query_one("#fwa-hero-crown")
        rows = ["".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()]
        assert any("$41,230" in row for row in rows), "the dollar figure is shed only when narrow"
        assert [t[2] for t in _region_targets(app, box)] == [_UNNAMED]


async def test_a_drift_row_too_narrow_for_its_label_sheds_the_label_never_the_icon():
    """At 120 columns the SIGNALS rail cannot hold the drift row's prose, an
    11-cell window and the icon; the CSS ellipsis used to cut the icon."""
    address = "0x" + "61" * 20
    events = [{"key": 61, "value": int(address, 16), "block_number": 25_600_000}]
    payload = T._sample_data()
    payload["param_drift_signal"] = sig.param_drift_signal(events).model_dump()
    app = T._ThemedHarness(T.FWAScreen(T._FakeManager(payload), poll_interval=30))
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(FWASignals)
        assert [t[2] for t in _region_targets(app, panel)] == [address], (
            "the drift address's icon was cropped off the SIGNALS row at 120 columns"
        )
        rows = ["".join(s.text for s in strip) for strip in app.screen._compositor.render_strips()]
        row = next(r for r in rows if "0x6161" in r)
        assert "change" in row, f"the label was shed whole where its head still fits: {row!r}"
