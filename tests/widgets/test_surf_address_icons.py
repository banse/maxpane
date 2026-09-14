"""Surf: every displayed 0x address carries a ``⧉`` that copies exactly it.

PRD: ``docs/address_copy_PRD.md``. Asserted against **composited output**
through ``tests/widgets/address_probe.icon_targets``: the glyph's position is
read off the compositor and the address it copies is read off the style at
that cell, which is the click target a reader would hit.

Four bodies (dashboard, ``l``, ``p``, ``4``), plus the three places where a
surf address is not a plain cell: the announce feed's prose, the signals
panel's detail prose, and the HATCHES discovery sentence.
"""

from __future__ import annotations

import pytest
from rich.cells import cell_len
from textual.app import App, ComposeResult

from maxpane_dashboard.screens.surf import (
    SURF_FULL_LAYOUT_COLUMNS,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_USER_FULL_LAYOUT_COLUMNS,
    SurfScreen,
)
from maxpane_dashboard.widgets.address import (
    COPY_GLYPH,
    address_text,
    is_address,
    short_address,
)
from tests.screens.test_surf_screen import (
    _FakeManager,
    _ThemedHarness,
    _frozen_payload,
    _mainnet_pool4_payload,
)
from tests.widgets.address_probe import CopyRecorder, icon_targets

#: A full address seeded into an announce post body. Built, not typed, so it
#: cannot be a character short of forty hex.
FEED_ADDR = "0x" + "5C2F9dA1b3E4c6D7e8F9" * 2
DEPLOY_ADDR = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"


class _CopyHarness(CopyRecorder, _ThemedHarness):
    pass


def _app(payload):
    return _CopyHarness(SurfScreen(_FakeManager(payload), poll_interval=30, name="surf"))


def _addresses_in(payload) -> set[str]:
    found: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            if is_address(v):
                found.add(v)
            else:
                # prose: a post body or a signal detail carrying an address
                import re
                found.update(re.findall(r"0x[0-9a-fA-F]{40}", v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(payload)
    return found


def _rows(app) -> list[str]:
    return [
        "".join(seg.text for seg in strip)
        for strip in app.screen._compositor.render_strips()
    ]


def _feed_payload() -> dict:
    """The frozen payload with a full address in the newest post's body."""
    payload = _frozen_payload()
    items = [dict(item) for item in payload["feed_items"]]
    items[0]["text"] = f"send to {FEED_ADDR} and nothing else"
    payload["feed_items"] = items
    return payload


async def _targets(payload, keys=(), size=(160, 60)):
    app = _app(payload)
    async with app.run_test(size=size) as pilot:
        for key in keys:
            await pilot.press(key)
        await pilot.pause()
        return icon_targets(app), app


# -- every body -----------------------------------------------------------


async def test_every_surf_body_renders_icons_and_every_icon_copies_a_payload_address():
    for payload, keys in ((_feed_payload(), ()), (_frozen_payload(), ("l",)),
                          (_mainnet_pool4_payload(), ("p",)),
                          (_mainnet_pool4_payload(), ("4",))):
        targets, _ = await _targets(payload, keys)
        assert targets, f"no copy icon on the surf body after {keys}"
        known = _addresses_in(payload)
        for x, y, address in targets:
            assert address in known, (keys, x, y, address)


def _stakers(payload):
    return [row["address"] for row in payload["pool4_stakers"]]


async def test_each_address_panel_carries_an_icon_for_its_own_addresses():
    """Not merely "some icon": each panel's own addresses, by name.

    The sweep above is satisfied by one icon anywhere; this one names the
    address each converted panel is responsible for, so a panel that lost its
    icon cannot hide behind a neighbour that kept one.
    """
    frozen = _frozen_payload()
    mainnet = _mainnet_pool4_payload()
    unknown = [r["counterparty"] for r in frozen["dev_activity"]
               if not r["counterparty_known"] and r["value_eth"] > 1e-9]
    cases = (
        # DEV ACTIVITY's unknown counterparty (the dust spoof is dropped)
        (frozen, (), set(unknown)),
        # LAUNCHPAD ACTIVITY wallet, BURNKEEPERS wallet. The coin table's
        # CREATOR is not here: it has no icon yet, pending an owner decision
        # (see ``test_the_coin_table_creator_carries_its_copy_icon``).
        (frozen, ("l",), {r["wallet"] for r in frozen["launchpad_activity"]}
         | {r["wallet"] for r in frozen["launchpad_burnkeepers"]}),
        # HATCHES: the address block and the lever grid
        (mainnet, ("p",), {mainnet["pool4_hook_addr"], mainnet["pool4_vault_addr"],
                           mainnet["pool4_dripper_addr"],
                           mainnet["pool4_distributor_addr"]}
         | {r["addr"] for r in mainnet["pool4_hatches"] if r.get("addr")}),
        # STAKERS
        (mainnet, ("4",), set(_stakers(mainnet))),
    )
    for payload, keys, expected in cases:
        assert expected, keys
        targets, _ = await _targets(payload, keys)
        copied = {address for _x, _y, address in targets}
        assert expected <= copied, (keys, sorted(expected - copied))


async def test_clicking_a_stakers_icon_copies_that_row_address():
    payload = _mainnet_pool4_payload()
    app = _app(payload)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        targets = [t for t in icon_targets(app) if t[2] in set(_stakers(payload))]
        assert targets
        x, y, address = targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]


# -- the feed: prose icons, and a click that copies without toggling -------


async def test_a_feed_icon_click_copies_and_does_not_toggle_the_thread():
    payload = _feed_payload()
    app = _app(payload)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        body = app.screen.query_one("#surf-feed-body")
        before = body.virtual_size
        feed_targets = [t for t in icon_targets(app)
                        if body.region.contains(t[0], t[1])]
        assert feed_targets, (
            "no copy icon inside the feed: seed a post body carrying a full address "
            "into this test's payload, or the test proves nothing")
        x, y, address = feed_targets[0]
        assert address == FEED_ADDR
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]
        assert app.screen.query_one("#surf-feed-body").virtual_size == before


async def test_a_copy_click_on_a_feed_toggle_copies_and_does_not_toggle():
    """The guard itself: the one surf widget with its own ``on_click``.

    ``SurfFeedToggle`` renders no address today, so the screen-level test
    above cannot reach its handler -- a click on a post's icon lands on a
    ``SurfFeedRow``, which has none. This mounts a toggle carrying an icon so
    the handler's guard is what decides, and removing it reddens here.
    """
    from maxpane_dashboard.widgets.surf.feed import SurfFeedToggle

    toggled: list[str] = []

    class _Toggle(SurfFeedToggle):
        def action_toggle(self) -> None:
            toggled.append(self.tx_hash)

    class _App(CopyRecorder, App):
        def compose(self) -> ComposeResult:
            yield _Toggle(address_text(FEED_ADDR), tx_hash="0xabc", id="t")

    app = _App()
    async with app.run_test(size=(80, 5)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert len(targets) == 1
        x, y, address = targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [FEED_ADDR]
        assert toggled == [], "a copy click also toggled the thread"
        await pilot.click(offset=(0, y))           # the displayed text
        await pilot.pause()
        assert toggled == ["0xabc"], "a click elsewhere must still toggle"


async def test_a_transaction_hash_in_a_post_gets_no_icon():
    """The frozen newest post links a 64-hex tx hash; it is not an address."""
    targets, _ = await _targets(_frozen_payload(), size=(SURF_FULL_LAYOUT_COLUMNS, 60))
    assert all(address is not None and len(address) == 42 for _x, _y, address in targets)
    assert not any(address.lower().startswith("0x90a0f8e2") for _x, _y, address in targets)


# -- DEV ACTIVITY keeps its anti-poisoning window beside the icon ----------


async def test_dev_activity_keeps_the_eight_six_window_and_its_amount_at_the_pin():
    payload = _frozen_payload()
    app = _app(payload)
    unknown = next(r["counterparty"] for r in payload["dev_activity"]
                   if not r["counterparty_known"] and r["value_eth"] > 1e-9)
    async with app.run_test(size=(SURF_FULL_LAYOUT_COLUMNS, 60)) as pilot:
        await pilot.pause()
        rows = _rows(app)
        window = short_address(unknown, 17)
        assert window == f"{unknown[:10]}…{unknown[-6:]}"
        line = next(r for r in rows if f"{window} {COPY_GLYPH}" in r)
        assert "ETH" in line, "the full tier (amount) no longer fits at the pin"


# -- the l body ------------------------------------------------------------


async def test_launchpad_windows_stay_eleven_cells_beside_their_icons_at_the_pin():
    payload = _frozen_payload()
    app = _app(payload)
    async with app.run_test(size=(SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, 60)) as pilot:
        await pilot.press("l")
        await pilot.pause()
        rows = _rows(app)
        text = "\n".join(rows)
        for address in ({r["wallet"] for r in payload["launchpad_activity"]}
                        | {r["wallet"] for r in payload["launchpad_burnkeepers"]}):
            assert f"{short_address(address, 11)} {COPY_GLYPH}" in text, address
        # The coin table is unchanged at its pin: every header whole, and the
        # CREATOR window still the 11-cell form.
        header = next(r for r in rows if "TICKER" in r)
        assert "BURNED" in header, "the coin table's last header was cut at the pin"
        creator = payload["launchpad_coins"][0]["creator"]
        assert short_address(creator, 11) in text


@pytest.mark.xfail(strict=True, reason=(
    "OPEN, for the owner: the coin table's CREATOR window is already the "
    "narrowest honest form (11) and the table has no free columns at "
    "_TABLE_FULL_WIDTH, so the icon cannot be placed without either NAME "
    "18 -> 16 (measured: holds the pin) or raising the pin (forbidden). "
    "Strict, so the day the icon lands this reddens and the marker comes off."))
async def test_the_coin_table_creator_carries_its_copy_icon():
    """The coin table alone, so no neighbour's icon can satisfy it."""
    from maxpane_dashboard.widgets.surf.launchpad import SurfLaunchpadCoins

    payload = _frozen_payload()

    class _App(App):
        def compose(self) -> ComposeResult:
            yield SurfLaunchpadCoins()

    app = _App()
    async with app.run_test(size=(120, 20)) as pilot:
        app.query_one(SurfLaunchpadCoins).update_data(
            coins=payload["launchpad_coins"], as_of_hhmm="01:14")
        await pilot.pause()
        copied = {a for _x, _y, a in icon_targets(app)}
        assert {c["creator"] for c in payload["launchpad_coins"]} <= copied


# -- the p body: HATCHES ---------------------------------------------------


async def test_hatches_block_keeps_seventeen_and_the_grid_gives_up_two_at_the_pin():
    payload = _mainnet_pool4_payload()
    app = _app(payload)
    async with app.run_test(size=(SURF_POOL4_FULL_LAYOUT_COLUMNS, 60)) as pilot:
        await pilot.press("p")
        await pilot.pause()
        text = "\n".join(_rows(app))
        hook = payload["pool4_hook_addr"]
        assert f"{short_address(hook, 17)} {COPY_GLYPH}" in text
        lever = next(r["addr"] for r in payload["pool4_hatches"] if r.get("addr"))
        assert f"{short_address(lever, 15)} {COPY_GLYPH}" in text
        assert "HATCHES" in text and "‹" not in next(
            r for r in _rows(app) if "HATCHES" in r)


async def test_hatches_discovery_prose_gets_an_icon_and_the_citation_does_not():
    payload = _mainnet_pool4_payload()
    targets, app = await _targets(payload, ("p",), size=(220, 60))
    hook = payload["pool4_hook_addr"]
    tx = payload["pool4_discovery_source_tx"]
    assert is_address(tx) is False
    copied = [address for _x, _y, address in targets]
    # the discovery detail names the hook in prose (from the fixture)
    assert "0xa1B997A9861B2b8aC17B4c615089cCC2a5416840" in copied or hook in copied
    assert all(address is not None for address in copied)


# -- the 4 body: STAKERS ---------------------------------------------------


async def test_stakers_show_the_whole_address_when_there_is_room_and_forty_at_the_pin():
    payload = _mainnet_pool4_payload()
    addr = _stakers(payload)[0]

    app = _app(payload)
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        assert any(f"{addr} {COPY_GLYPH}" in r for r in _rows(app))

    app = _app(payload)
    async with app.run_test(size=(SURF_POOL4_USER_FULL_LAYOUT_COLUMNS, 60)) as pilot:
        await pilot.press("4")
        await pilot.pause()
        rows = _rows(app)
        shown = short_address(addr, 40)
        assert cell_len(shown) == 40
        assert any(f"{shown} {COPY_GLYPH}" in r for r in rows), rows
        title = next(r for r in rows if "STAKERS" in r)
        assert "‹" not in title, "STAKERS marked at its own pin"


# -- signals: detail prose -------------------------------------------------


async def test_a_new_contract_detail_renders_its_window_and_an_icon_that_copies_it():
    from maxpane_dashboard.widgets.surf.signals import SurfSignals

    class _App(CopyRecorder, App):
        def compose(self) -> ComposeResult:
            yield SurfSignals()

    app = _App()
    async with app.run_test(size=(120, 16)) as pilot:
        widget = app.query_one(SurfSignals)
        widget.update_data(sig_deploy_state="fired", sig_deploy_age_s=60.0,
                           sig_deploy_detail=f"new contract {DEPLOY_ADDR} · surfsurf.eth")
        await pilot.pause()
        text = "\n".join(_rows(app))
        assert f"new contract {short_address(DEPLOY_ADDR, 17)} {COPY_GLYPH}" in text
        targets = icon_targets(app)
        assert [a for _x, _y, a in targets] == [DEPLOY_ADDR]
        x, y, _a = targets[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [DEPLOY_ADDR]


async def test_a_cut_detail_never_bisects_an_address_window():
    from maxpane_dashboard.widgets.surf.signals import SurfSignals

    window = short_address(DEPLOY_ADDR, 17)
    for width in range(30, 80):
        class _App(App):
            def compose(self) -> ComposeResult:
                yield SurfSignals()

        app = _App()
        async with app.run_test(size=(width, 16)) as pilot:
            widget = app.query_one(SurfSignals)
            widget.update_data(sig_deploy_state="fired", sig_deploy_age_s=60.0,
                               sig_deploy_detail=f"new contract {DEPLOY_ADDR} · surfsurf.eth")
            await pilot.pause()
            row = next(r for r in _rows(app) if "NEW DEPLOY" in r)
            has_start = "0x8004" in row
            assert (f"{window} {COPY_GLYPH}" in row) == has_start, (width, row)
            assert cell_len(row.rstrip()) <= width, (width, row)


def test_the_deploy_detector_publishes_the_whole_address():
    """PRD §6: the full address reaches the widget; nothing shortens it first."""
    from maxpane_dashboard.analytics import surf_signals as sig

    assert not hasattr(sig, "_short_addr")
