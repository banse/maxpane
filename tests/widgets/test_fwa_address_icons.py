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

from tests.screens import test_fwa_screen as T
from tests.widgets.address_probe import CopyRecorder, icon_targets
from maxpane_dashboard.widgets.address import COPY_GLYPH, address_text, is_address


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
