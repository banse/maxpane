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
    PROSE_ADDRESS_RE,
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
                # prose: a post body or a signal detail carrying an address.
                # Hex-bounded (PROSE_ADDRESS_RE), so a 66-char tx hash's
                # 40-hex prefix is not counted as a known address.
                found.update(m.group(0) for m in PROSE_ADDRESS_RE.finditer(v))
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
                          (_mainnet_pool4_payload(), ("e",)),
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
        # coin CREATOR, LAUNCHPAD ACTIVITY wallet, BURNKEEPERS wallet. The
        # creators are also activity wallets in this fixture, so the coin
        # table's own icons are asserted by region in
        # ``test_the_coin_table_creator_carries_its_copy_icon``.
        (frozen, ("l",), {c["creator"] for c in frozen["launchpad_coins"]}
         | {r["wallet"] for r in frozen["launchpad_activity"]}
         | {r["wallet"] for r in frozen["launchpad_burnkeepers"]}),
        # HATCHES: the address block and the lever grid
        (mainnet, ("e",), {mainnet["pool4_hook_addr"], mainnet["pool4_vault_addr"],
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


async def test_a_link_click_on_a_feed_toggle_opens_and_does_not_toggle():
    """The other half of the guard (fix round 1, M1): a click on the *linked
    span* of an address the toggle renders runs the explorer action and
    never the toggle's own click behaviour; a click on plain text still
    toggles. Mirrors the copy-click test above, with ``is_explorer_click``
    as the guard under test."""
    from maxpane_dashboard.widgets.explorer import ETHEREUM
    from maxpane_dashboard.widgets.surf.feed import SurfFeedToggle

    toggled: list[str] = []
    opened: list[tuple[str, str, str]] = []

    class _Toggle(SurfFeedToggle):
        def action_toggle(self) -> None:
            toggled.append(self.tx_hash)

    class _App(CopyRecorder, App):
        def compose(self) -> ComposeResult:
            text = address_text(FEED_ADDR, explorer=ETHEREUM)
            text.append("  plain")
            yield _Toggle(text, tx_hash="0xabc", id="t")

        def action_open_explorer(self, name: str, kind: str, value: str) -> None:
            opened.append((name, kind, value))

    app = _App()
    async with app.run_test(size=(80, 5)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert len(targets) == 1
        x, y, _ = targets[0]
        await pilot.click(offset=(x - 2, y))       # the last cell of the shown address
        await pilot.pause()
        assert opened == [("etherscan", "address", FEED_ADDR)]
        assert toggled == [], "a link click also toggled the thread"
        assert app.copied == []
        await pilot.click(offset=(x + 4, y))       # "plain", past the icon
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


async def test_the_coin_table_creator_carries_its_copy_icon():
    """Both fixture creators, by the coin table's own region, at the pin.

    The ``l`` body at ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``, so the icon is
    asserted where NAME 18 -> 16 paid for it -- and only icons inside the coin
    table count: in this fixture both creators are also LAUNCHPAD ACTIVITY
    wallets, whose icons must not satisfy it. Then one is clicked.
    """
    from maxpane_dashboard.widgets.surf.launchpad import SurfLaunchpadCoins

    payload = _frozen_payload()
    creators = {c["creator"] for c in payload["launchpad_coins"]}
    assert len(creators) == 2
    app = _app(payload)
    async with app.run_test(size=(SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, 60)) as pilot:
        await pilot.press("l")
        await pilot.pause()
        region = app.screen.query_one(SurfLaunchpadCoins).region
        in_table = [t for t in icon_targets(app) if region.contains(t[0], t[1])]
        assert {a for _x, _y, a in in_table} == creators, in_table
        rows = _rows(app)
        for creator in creators:
            assert any(f"{short_address(creator, 11)} {COPY_GLYPH}" in rows[y]
                       for _x, y, a in in_table if a == creator), creator
        header = next(r for r in rows if "TICKER" in r)
        assert "BURNED" in header, "the coin table's last header was cut at the pin"
        x, y, address = in_table[0]
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address]


# -- the p body: HATCHES ---------------------------------------------------


async def test_hatches_block_keeps_seventeen_and_the_grid_gives_up_two_at_the_pin():
    payload = _mainnet_pool4_payload()
    app = _app(payload)
    async with app.run_test(size=(SURF_POOL4_FULL_LAYOUT_COLUMNS, 60)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        text = "\n".join(_rows(app))
        hook = payload["pool4_hook_addr"]
        assert f"{short_address(hook, 17)} {COPY_GLYPH}" in text
        lever = next(r["addr"] for r in payload["pool4_hatches"] if r.get("addr"))
        assert f"{short_address(lever, 15)} {COPY_GLYPH}" in text
        assert "HATCHES" in text and "‹" not in next(
            r for r in _rows(app) if "HATCHES" in r)


async def test_hatches_discovery_prose_gets_an_icon_and_the_citation_does_not():
    """On the discovery detail's own row, at the ``p`` pin and wide.

    Located by row, not by "some icon copies an address": the address block a
    few lines below carries its own icons, so a whole-panel check passes with
    the detail's icon cut off. At the pin the detail is fitted to a 35-cell
    room; the address must arrive as its 17-cell window with the icon, never
    cut mid-window with the icon gone. The citation row is a transaction hash
    and carries no icon at either width.
    """
    payload = _mainnet_pool4_payload()
    named = PROSE_ADDRESS_RE.search(payload["pool4_discovery_detail"]).group(0)
    assert not is_address(payload["pool4_discovery_source_tx"])
    for width in (SURF_POOL4_FULL_LAYOUT_COLUMNS, 220):
        app = _app(payload)
        async with app.run_test(size=(width, 60)) as pilot:
            await pilot.press("e")
            await pilot.pause()
            rows = _rows(app)
            # HATCHES sits in the rail, so its lines share a row with the
            # left column: located by content, never by a row's start.
            label_y = next(i for i, r in enumerate(rows) if "discovery adopted" in r)
            detail_y = label_y + 1
            assert "adopted 0x" in rows[detail_y], (width, rows[detail_y])
            cite_y = next(i for i in range(detail_y + 1, len(rows))
                          if " tx 0x" in rows[i])
            targets = icon_targets(app)
            on_detail = [a for _x, y, a in targets if y == detail_y]
            assert on_detail == [named], (width, rows[detail_y], on_detail)
            assert f"{short_address(named, 17)} {COPY_GLYPH}" in rows[detail_y], (
                width, rows[detail_y])
            assert not [t for t in targets if t[1] == cite_y], (width, rows[cite_y])
            assert COPY_GLYPH not in rows[cite_y]


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


async def test_a_relaxed_row_quoting_an_address_in_its_last_clause_keeps_the_icon():
    """The relaxed form ``analytics/surf_signals.build_signals`` composes when a
    fired event has aged out: ``f"{detail} · last: {entry['detail']}"``, here
    under a WATCH head (an ``ok`` row folds away and would paint nothing).

    Wide: the ``last:`` clause's address is its window plus an icon that
    copies it. Swept narrow: whenever any of the window is painted, all of it
    and its icon are, and the row fits.
    """
    from maxpane_dashboard.widgets.surf.signals import SurfSignals

    detail = f"surfsurf.eth nonce 4→5 · last: new contract {DEPLOY_ADDR} · surfsurf.eth"
    window = short_address(DEPLOY_ADDR, 17)

    class _App(CopyRecorder, App):
        def compose(self) -> ComposeResult:
            yield SurfSignals()

    for width in [120, *range(40, 110, 3)]:
        app = _App()
        async with app.run_test(size=(width, 16)) as pilot:
            app.query_one(SurfSignals).update_data(
                sig_deploy_state="watch", sig_deploy_detail=detail)
            await pilot.pause()
            y, row = next((i, r) for i, r in enumerate(_rows(app)) if "NEW DEPLOY" in r)
            targets = [t for t in icon_targets(app) if t[1] == y]
            painted = "0x8004" in row
            assert (f"last: new contract {window} {COPY_GLYPH}" in row) == painted, (
                width, row)
            assert [a for _x, _y, a in targets] == ([DEPLOY_ADDR] if painted else []), (
                width, row)
            assert cell_len(row.rstrip()) <= width, (width, row)
            if width == 120:
                assert painted, row
                x, ty, _a = targets[0]
                await pilot.click(offset=(x, ty))
                await pilot.pause()
                assert app.copied == [DEPLOY_ADDR]


def test_the_deploy_detector_publishes_the_whole_address():
    """PRD §6: the full address reaches the widget; nothing shortens it first."""
    from maxpane_dashboard.analytics import surf_signals as sig

    assert not hasattr(sig, "_short_addr")


# -- explorer links in fitted prose (refactor programme 2026-09, Branch 4 WP-A) ---------
#
# ``_icons.link_prose`` / ``link_in_order`` take an ``explorer=``: the shown
# address (whole, or its window) right before each surviving glyph gets the
# helper's own link span; ``None`` links nothing but the glyph, as before.


def _link_spans(text):
    from rich.style import Style

    from maxpane_dashboard.widgets.explorer import parse_open_action

    out = []
    for span in text.spans:
        if isinstance(span.style, Style) and span.style.link:
            out.append((text.plain[span.start:span.end], span.style.link,
                        parse_open_action(span.style.meta.get("@click"))))
    return out


def test_link_prose_without_an_explorer_is_unchanged():
    from rich.text import Text

    from maxpane_dashboard.widgets.surf import _icons as I

    marked, _, _ = I.mark_addresses(f"gm {FEED_ADDR} and {DEPLOY_ADDR}")
    before = I.link_prose(Text(I.unmark(marked)))
    after = I.link_prose(Text(I.unmark(marked)), None)
    assert after == before
    assert _link_spans(after) == []
    assert [a for _x, _y, a in _prose_targets(after)] == [FEED_ADDR, DEPLOY_ADDR]


def test_link_prose_links_the_whole_address_before_each_surviving_glyph():
    from rich.text import Text

    from maxpane_dashboard.widgets import explorer as X
    from maxpane_dashboard.widgets.surf import _icons as I

    marked, _, _ = I.mark_addresses(f"gm {FEED_ADDR} and {DEPLOY_ADDR}")
    text = I.link_prose(Text(I.unmark(marked)), X.ETHEREUM)
    assert _link_spans(text) == [
        (FEED_ADDR, X.address_url(X.ETHEREUM, FEED_ADDR), (X.ETHEREUM, "address", FEED_ADDR)),
        (DEPLOY_ADDR, X.address_url(X.ETHEREUM, DEPLOY_ADDR), (X.ETHEREUM, "address", DEPLOY_ADDR)),
    ]
    assert [a for _x, _y, a in _prose_targets(text)] == [FEED_ADDR, DEPLOY_ADDR]
    # A wrap that kept only the first unit links only the first address.
    cut = Text(I.unmark(marked)[: marked.index(DEPLOY_ADDR)])
    I.link_prose(cut, X.ETHEREUM)
    assert [s[0] for s in _link_spans(cut)] == [FEED_ADDR]


def test_link_in_order_links_the_window_before_each_glyph_to_its_own_address():
    from rich.text import Text

    from maxpane_dashboard.widgets import explorer as X
    from maxpane_dashboard.widgets.surf import _icons as I

    marked, addresses, _ = I.mark_addresses(f"adopted {FEED_ADDR} by {DEPLOY_ADDR}", 17)
    plain = Text(I.unmark(marked))
    I.link_in_order([plain], addresses)
    assert _link_spans(plain) == []

    text = Text(I.unmark(marked))
    I.link_in_order([text], addresses, X.SEPOLIA)
    assert _link_spans(text) == [
        (short_address(FEED_ADDR, 17), X.address_url(X.SEPOLIA, FEED_ADDR), (X.SEPOLIA, "address", FEED_ADDR)),
        (short_address(DEPLOY_ADDR, 17), X.address_url(X.SEPOLIA, DEPLOY_ADDR), (X.SEPOLIA, "address", DEPLOY_ADDR)),
    ]
    assert [a for _x, _y, a in _prose_targets(text)] == [FEED_ADDR, DEPLOY_ADDR]
    assert text.plain == plain.plain, "the link adds no cells"


def test_link_in_order_links_only_a_window_of_that_address():
    """A glyph whose window is not of the address it is linked to (a fitter
    that bisected a unit) keeps its copy action and gets no link: a link to
    the wrong page is worse than none."""
    from rich.text import Text

    from maxpane_dashboard.widgets import explorer as X
    from maxpane_dashboard.widgets.surf import _icons as I

    text = Text(f"x 0xdead…beef {COPY_GLYPH} then {COPY_GLYPH}")
    I.link_in_order([text], [FEED_ADDR, DEPLOY_ADDR], X.ETHEREUM)
    assert _link_spans(text) == []
    assert [a for _x, _y, a in _prose_targets(text)] == [FEED_ADDR, DEPLOY_ADDR]


def _prose_targets(text):
    """``(start, end, address)`` for every copy glyph in ``text``."""
    from rich.style import Style

    from maxpane_dashboard.widgets.address import parse_copy_action

    return [
        (s.start, s.end, parse_copy_action(s.style.meta.get("@click")))
        for s in text.spans
        if isinstance(s.style, Style) and parse_copy_action(s.style.meta.get("@click"))
    ]
