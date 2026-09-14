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

from textual.app import App, ComposeResult

from tests.screens import test_fwa_screen as T
from tests.widgets.address_probe import CopyRecorder, icon_targets
from maxpane_dashboard.analytics import fwa_signals as sig
from maxpane_dashboard.widgets.address import COPY_GLYPH, address_text, is_address
from maxpane_dashboard.widgets.fwa.fwa_signals import FWASignals


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
    harness = next(
        getattr(T, n)
        for n in dir(T)
        if isinstance(getattr(T, n), type) and n.endswith("Harness")
    )

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
    harness = next(
        getattr(T, n)
        for n in dir(T)
        if isinstance(getattr(T, n), type) and n.endswith("Harness")
    )
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


# -- SIGNALS panel: the PARAM DRIFT row (fix round 1) -----------------------
#
# Unlike the other six sites, this one is not a plain field -- the value it
# renders is composed prose (``analytics/fwa_signals.py``'s
# ``param_drift_signal``) that may or may not contain a 0x value, and if it
# does that value may be a genuine address or a bytes32 hash. Both cases are
# driven through the real analytics builder, not a hand-typed payload, so the
# fixture is exactly what the manager could hand the widget.


class _SignalsHarness(App):
    """Mount a bare ``FWASignals`` -- no screen, no manager."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


async def test_an_address_typed_drift_signal_shows_its_icon_and_copies_it():
    address = "0x" + "11" * 20
    events = [{"key": 61, "value": int(address, 16), "block_number": 25_600_000}]
    row = sig.param_drift_signal(events).model_dump()
    assert address in row["value_str"], "fixture sanity: the analytics side is untouched"

    class _CopySignalsHarness(CopyRecorder, _SignalsHarness):
        pass

    widget = FWASignals()
    app = _CopySignalsHarness(widget)
    async with app.run_test(size=(100, 10)) as pilot:
        widget.update_data(param_drift_signal=row)
        await pilot.pause()
        targets = icon_targets(app)
        assert targets, "no copy icon on an address-typed drift signal"
        x, y, copied_address = targets[0]
        assert copied_address == address
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

    widget = FWASignals()
    app = _SignalsHarness(widget)
    async with app.run_test(size=(100, 10)) as pilot:
        widget.update_data(param_drift_signal=row)
        await pilot.pause()
        assert not icon_targets(app), "a bytes32 value must never carry a copy icon"
        plain = "\n".join(
            "".join(seg.text for seg in strip)
            for strip in app.screen._compositor.render_strips()
        )
        # Shortened (66 characters would not fit undetected), never the raw
        # 64-hex value, and the arrow/prefix around it survive untouched.
        assert f"0x{value_hex}" not in plain
        assert "0xcccccccc…cccccc" in plain
        assert "VRF_KEY_HASH" in plain
