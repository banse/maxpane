"""Copy icons on every 0x address the curator widgets render (Task 3).

PRD: ``docs/address_copy_PRD.md``. Task 3 brief:
``.superpowers/sdd/2026-09-14-address-copy-icons/task-3-brief.md``.

Widget-level tests (each widget constructed directly and driven through
``update_data``), matching the precedent Tasks 5-8 already established
rather than the dispatch template's full-screen sketch -- see
``task-3-report.md`` for why: curator's own screen test module names two
classes ending in "Harness", the default (dashboard) body needs an ``h``
keypress to even reach three of these five widgets (the screen opens on
Raw Lists), and two of the four bodies the template's own sketch exercises
(wallet, analysis) hold nothing this task converts. None of that machinery
is needed here: every widget below takes its payload straight through
``update_data``, exactly like Tasks 5/7's own address-icon tests.

Five sites confirmed in the brief (recipe step 1):

- ``activity.py``: the deposit feed's identity cell (``short_label`` over
  ``address``/``name``).
- ``closest_calls.py``: the SAVIOR cell (``short_label`` over
  ``savior``/``savior_name``).
- ``leaderboard.py``: the WALLET cell (``short_label`` over
  ``address``/``name``).
- ``list_hero.py``: the wallet card's address line (the full, unshortened
  address, PRD's "address stays visible even when ENS exists").
- ``signals.py``: HOUR SAVED's and WHALE's identity part -- the only two of
  the rail's seven rows that ever carry a wallet.

**Grown in the 2026-09-14 fix round** (review item 1: "everywhere a 0x
address is displayed" covers all of ``widgets/curator/*``, and the brief's
six-module list was incomplete) to also cover ``cleaned_list.py`` (the `f`
view's CLEANED LIST wallet cell), ``lists.py`` (the `l` view's raw/cleaned/
filtered ADDRESS column), ``wallet.py`` (the `y` view's WALLET panel), and
``list_filter.py``'s selected custom NFT collection row (not the `:201`
cache key, which stays a dict key rather than a display and is still
correctly left alone). ``operators.py``, ``segments.py`` and ``clusters.py``
were checked and confirmed false positives -- they render evidence labels
and pattern words, never a bare address -- and stay untouched. The
screen-level test below (restored per the same item) is the proof that all
of these compose into one screen without a stray or missing icon.
"""

from __future__ import annotations

import importlib
import inspect

import pytest
from textual.app import App

from tests.widgets.address_probe import CopyRecorder, icon_targets, link_targets

ADDR = "0x" + "abcdef0123" * 4
CASES = ["activity", "closest_calls", "leaderboard", "list_hero", "signals"]


class _WidgetApp(CopyRecorder, App):
    def __init__(self, widget, payload):
        super().__init__()
        self._widget, self._payload = widget, payload

    def compose(self):
        yield self._widget

    def on_mount(self):
        self._widget.update_data(**self._payload)


def _widget_class(mod):
    classes = [c for _, c in inspect.getmembers(mod, inspect.isclass)
               if c.__module__ == mod.__name__ and hasattr(c, "update_data")]
    assert classes, f"{mod.__name__} defines no widget with update_data"
    return classes[0]


#: name -> update_data kwargs carrying ADDR, built from each widget's real
#: row shape (``CURATOR_ROW_KEYS`` / each module's own ``update_data``
#: signature, read off the source rather than guessed).
SEEDED: dict[str, dict] = {
    "activity": dict(activity_rows=[{
        "kind": "deposit", "ts": 1_700_000_000, "address": ADDR, "name": None,
        "amount_eth": 3.6, "credited_eth": 2.8, "new_weight": 7.03,
        "tx_count": 1, "tx_hash": "0x" + "ab" * 32, "log_index": 1,
    }]),
    "closest_calls": dict(closest_call_rows=[{
        "hour": 1, "volume_eth": 5.0, "margin_eth": 0.5,
        "savior": ADDR, "savior_name": None,
    }]),
    "leaderboard": dict(leaderboard_rows=[{
        "rank": 1, "address": ADDR, "name": None, "points": 100,
        "credit_eth": 1.0, "tx_count": 1, "link_conf": None, "flagged": None,
    }]),
    "list_hero": dict(
        you_address=ADDR, you_ens=None, list_view="raw",
        you_rank=1, contributors_total=10,
        you_points=10, you_credit_eth=1.0,
    ),
    "signals": dict(
        whale_wallet=ADDR, whale_ens=None, whale_amount_eth=1.0, whale_age_s=60,
    ),
}


@pytest.mark.parametrize("name", CASES)
async def test_each_curator_widget_puts_an_icon_on_a_seeded_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.curator.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}, (name, targets)


@pytest.mark.parametrize("name", CASES)
async def test_clicking_the_icon_copies_exactly_that_address(name):
    mod = importlib.import_module(f"maxpane_dashboard.widgets.curator.{name}")
    app = _WidgetApp(_widget_class(mod)(), SEEDED[name])
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        target = next(t for t in icon_targets(app) if t[2] == ADDR)
        await pilot.click(offset=(target[0], target[1]))
        await pilot.pause()
        assert app.copied == [ADDR], name


async def test_leaderboard_lower_cases_a_checksummed_address():
    """Two sources spell one wallet two ways (``eth_call`` checksums it, a
    log topic decodes lowercase); the icon must copy one spelling so "this
    row is you" (a case-insensitive compare) is never contradicted by what
    the clipboard actually holds."""
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.leaderboard")
    checksummed = "0x" + "ABCDEF0123" * 4
    app = _WidgetApp(_widget_class(mod)(), dict(leaderboard_rows=[{
        "rank": 1, "address": checksummed, "name": None, "points": 100,
        "credit_eth": 1.0, "tx_count": 1, "link_conf": None, "flagged": None,
    }]))
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert targets, "no copy icon on the leaderboard"
        addresses = {t[2] for t in targets}
        assert checksummed.lower() in addresses
        assert checksummed not in addresses


async def test_activity_lower_cases_a_checksummed_address():
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.activity")
    checksummed = "0x" + "ABCDEF0123" * 4
    app = _WidgetApp(_widget_class(mod)(), dict(activity_rows=[{
        "kind": "deposit", "ts": 1_700_000_000, "address": checksummed, "name": None,
        "amount_eth": 3.6, "credited_eth": 2.8, "new_weight": 7.03,
        "tx_count": 1, "tx_hash": "0x" + "ab" * 32, "log_index": 1,
    }]))
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        addresses = {t[2] for t in icon_targets(app)}
        assert checksummed.lower() in addresses
        assert checksummed not in addresses


async def test_closest_calls_lower_cases_a_checksummed_address():
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.closest_calls")
    checksummed = "0x" + "ABCDEF0123" * 4
    app = _WidgetApp(_widget_class(mod)(), dict(closest_call_rows=[{
        "hour": 1, "volume_eth": 5.0, "margin_eth": 0.5,
        "savior": checksummed, "savior_name": None,
    }]))
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        addresses = {t[2] for t in icon_targets(app)}
        assert checksummed.lower() in addresses
        assert checksummed not in addresses


async def test_signals_lower_cases_a_checksummed_address():
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.signals")
    checksummed = "0x" + "ABCDEF0123" * 4
    app = _WidgetApp(_widget_class(mod)(), dict(
        whale_wallet=checksummed, whale_ens=None, whale_amount_eth=1.0, whale_age_s=60,
    ))
    async with app.run_test(size=(150, 40)) as pilot:
        await pilot.pause()
        addresses = {t[2] for t in icon_targets(app)}
        assert checksummed.lower() in addresses
        assert checksummed not in addresses


async def test_list_hero_lower_cases_a_checksummed_address():
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.list_hero")
    checksummed = "0x" + "ABCDEF0123" * 4
    app = _WidgetApp(_widget_class(mod)(), dict(
        you_address=checksummed, you_ens=None, list_view="raw",
        you_rank=1, contributors_total=10, you_points=10, you_credit_eth=1.0,
    ))
    async with app.run_test(size=(150, 12)) as pilot:
        await pilot.pause()
        addresses = {t[2] for t in icon_targets(app)}
        assert checksummed.lower() in addresses
        assert checksummed not in addresses


async def test_list_hero_wallet_card_shows_the_verified_ens_name_and_still_copies_the_address():
    """PRD §13 A9 / the record-list hero contract: the icon goes on the
    address, and a verified ENS name still stands in as the shown text."""
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.list_hero")
    app = _WidgetApp(_widget_class(mod)(), dict(
        you_address=ADDR, you_ens="reader.eth", list_view="raw",
        you_rank=1, contributors_total=10, you_points=10, you_credit_eth=1.0,
    ))
    async with app.run_test(size=(150, 12)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}
        strips = app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
        assert "reader.eth" in text


# ---------------------------------------------------------------------------
# Coverage fix round (2026-09-14): cleaned_list.py, lists.py, wallet.py,
# list_filter.py's selected custom NFT collection, and the custom_nft_label
# restructure (item 2 of the review).
# ---------------------------------------------------------------------------


async def test_cleaned_list_puts_an_icon_on_a_seeded_address():
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.cleaned_list")
    app = _WidgetApp(_widget_class(mod)(), dict(clean_list_rows=[{
        "clean_rank": 1, "address": ADDR, "name": None,
        "points": 100, "credit_eth": 1.0,
    }]))
    async with app.run_test(size=(150, 12)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}
        x, y, _ = next(t for t in targets if t[2] == ADDR)
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR]


async def test_wallet_address_panel_puts_an_icon_on_a_seeded_address():
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.wallet")
    app = _WidgetApp(mod.CuratorWalletAddress(), dict(you_address=ADDR, you_ens=None))
    async with app.run_test(size=(100, 12)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}
        x, y, _ = next(t for t in targets if t[2] == ADDR)
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR]


@pytest.mark.parametrize("view", ("raw", "cleaned", "filtered"))
async def test_each_l_view_record_table_puts_an_icon_on_a_seeded_address(view):
    mod = importlib.import_module("maxpane_dashboard.widgets.curator.lists")
    widget_cls = {
        "raw": mod.CuratorRawList,
        "cleaned": mod.CuratorCleanedList,
        "filtered": mod.CuratorFilteredList,
    }[view]
    row = {
        "rank": 1, "clean_rank": 1, "first_index": 1, "address": ADDR, "name": None,
        "points": 100, "weight_eth": 1.0, "credit_eth": 1.0, "tx_count": 1,
        "first_hour": 1, "link_conf": "clean",
    }
    kwargs = {
        "raw": dict(leaderboard_rows=[row], contributors_total=1),
        "cleaned": dict(clean_list_rows=[row], clean_contributors=1),
        "filtered": dict(filtered_rows=[row], filtered_complete=True),
    }[view]
    app = _WidgetApp(widget_cls(), kwargs)
    async with app.run_test(size=(150, 18)) as pilot:
        await pilot.pause()
        targets = icon_targets(app)
        assert ADDR in {t[2] for t in targets}, (view, targets)
        x, y, _ = next(t for t in targets if t[2] == ADDR)
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [ADDR], view


class _EditorApp(CopyRecorder, App):
    """The filter editor alone, driven by hand -- it has no ``update_data``
    (``set_values``/``set_custom_nfts`` are its own entry points), so the
    generic ``_WidgetApp`` (which calls ``update_data`` on mount) does not
    fit it."""

    def __init__(self, widget):
        super().__init__()
        self._widget = widget

    def compose(self):
        yield self._widget


async def test_the_selected_custom_nft_collection_renders_a_copy_icon_that_copies_its_address():
    """Item 2 of the fix round: the filter editor's selected-collections
    grid composes ``address_text`` over the collection's own ``.address``
    field for a nameless (fallback-labelled) custom collection, rather than
    showing ``custom_nft_label``'s plain, CSS-ellipsisable string."""
    from maxpane_dashboard.widgets.curator.list_filter import CuratorListFilterEditor

    app = _EditorApp(CuratorListFilterEditor(nft_choices=()))
    address = "0x" + "ABCDEF0123" * 4
    async with app.run_test(size=(143, 42)) as pilot:
        editor = app.query_one(CuratorListFilterEditor)
        editor.set_custom_nfts(({
            "label": "ETH 0xabcd…0123",
            "chain": "ethereum",
            "address": address,
            "is_fallback": True,
        },))
        await pilot.pause()
        targets = icon_targets(app)
        addresses = {t[2] for t in targets}
        assert address.lower() in addresses
        assert address not in addresses
        x, y, _ = next(t for t in targets if t[2] == address.lower())
        await pilot.click(offset=(x, y))
        await pilot.pause()
        assert app.copied == [address.lower()]


async def test_a_real_custom_nft_label_gets_no_icon():
    """A reader-chosen (or resolved) name is not an address; it renders as
    plain text, unchanged, and does not carry a copy icon."""
    from maxpane_dashboard.widgets.curator.list_filter import CuratorListFilterEditor

    app = _EditorApp(CuratorListFilterEditor(nft_choices=()))
    async with app.run_test(size=(143, 42)) as pilot:
        editor = app.query_one(CuratorListFilterEditor)
        editor.set_custom_nfts(({
            "label": "CryptoPunks",
            "chain": "ethereum",
            "address": "0x" + "ab" * 20,
            "is_fallback": False,
        },))
        await pilot.pause()
        assert icon_targets(app) == []
        strips = app.screen._compositor.render_strips()
        text = "\n".join("".join(seg.text for seg in strip) for strip in strips)
        assert "CryptoPunks" in text


def test_the_hero_summary_describes_a_single_nameless_custom_collection():
    """Item 2 of the fix round: a nameless custom collection's clause is
    windowed (short), so it is *described*, not collapsed to "multiple
    filters applied" the moment it is the only filter active."""
    from maxpane_dashboard.data.curator_list_filters import (
        filter_summary,
        parse_filter_values,
    )
    from maxpane_dashboard.widgets.curator.list_hero import (
        FULL_WIDTH,
        _compact_filter_summary,
    )

    address = "0x" + "ab" * 20
    spec = parse_filter_values(
        {"nft_collections": ({"chain": "ethereum", "address": address},)}
    )
    summary = filter_summary(spec)
    assert summary == ("NFT ETH 0xabab…abab",)
    result = _compact_filter_summary(summary, "full", FULL_WIDTH)
    assert result == "NFT ETH 0xabab…abab"
    assert result != "multiple filters applied"


def test_the_data_layer_window_matches_widgets_address():
    """``curator_list_filters._windowed`` is a duplicate of
    ``widgets.address``'s own anti-poisoning window, kept in step here
    because neither module may import the other (the layering runs
    ``widgets`` -> ``data``, never back)."""
    from maxpane_dashboard.data.curator_list_filters import _windowed
    from maxpane_dashboard.widgets.address import short_address

    for address in (ADDR, "0x" + "ab" * 20, "0x" + "9" * 40):
        assert _windowed(address, 11) == short_address(address, 11)


# ---------------------------------------------------------------------------
# Screen-level proof, restored (item 1 of the fix round): the brief's own
# Step 1 sketch, dropped from the original pass because none of `y`/`f`/`l`
# held a converted site at the time -- they all do now that cleaned_list.py
# (`f`), lists.py (`l`, the default body) and wallet.py (`y`) are converted.
# ---------------------------------------------------------------------------


def _addresses_in(payload) -> set[str]:
    from maxpane_dashboard.widgets.address import is_address

    found: set[str] = set()

    def walk(v):
        if isinstance(v, str) and is_address(v):
            found.add(v.lower())
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(payload)
    return found


async def test_curator_screen_y_f_and_l_views_render_icons_for_the_seeded_address():
    """`y` -> wallet.py's ``CuratorWalletAddress``; `f` -> cleaned_list.py's
    ``CuratorCleanList``; `l` (the default body, no keypress needed) ->
    lists.py's ``CuratorRawList``.  Each view's icons must all name an
    address that is actually in its own payload (or the configured
    wallet), never a stray/garbage target -- and, for `f`/`l`, at least one
    icon must name a *row* address (not the configured wallet's own), or
    this would pass unchanged with the view's own converted widget's icon
    entirely missing: `l`'s hero (``CuratorListHero``) and `y`'s own panel
    both always carry a wallet-address icon regardless of whether the
    table/list panel under test still has its own (proven by mutation --
    see task-3-report.md).

    `f` is entered via ``screen.action_toggle_analysis()`` directly, not
    ``pilot.press("f")``: unlike every other view here, no live key binds
    to it -- ``BINDINGS`` maps ``"f"`` to ``action_toggle_filter`` (the
    record-view filter editor, a ``MODE_LIST``-only no-op elsewhere), and
    nothing in ``screens/curator.py`` calls ``action_toggle_analysis`` from
    any key or action path.  Every existing analysis-mode test in
    ``test_curator_screen.py`` already reaches it the same way; flagged as
    a concern for the reviewer (task-3-report.md) rather than fixed here --
    ``screens/curator.py``'s ``BINDINGS`` is outside curator source Task 3
    owns."""
    from tests.screens import test_curator_screen as T

    class _CopyHarness(CopyRecorder, T._ThemedHarness):
        pass

    analysis_payload = T._analysis_payload()
    list_payload = T._list_payload(3)
    cases = (
        # `y`: no row-address check -- `_wallet_payload()` carries other
        # views' row data in the same flat manager payload (a shared
        # dict), none of which `y` mode ever composes, so a generic
        # "some non-wallet address rendered" check would be meaningless
        # here.  wallet.py's own site is the wallet's own address.
        ("y", T._wallet_payload(), lambda screen: screen.action_toggle_mode(), None),
        # `f`: cleaned_list.py's own rows -- minus the configured wallet's
        # own address, which the worst-case fixture also seeds as one row
        # (the reader's own row, a real feature), and which would
        # otherwise let `y`'s or the hero's icon satisfy this check
        # without `f`'s own panel carrying one at all.
        (
            "f", analysis_payload, lambda screen: screen.action_toggle_analysis(),
            _addresses_in(analysis_payload["clean_list_rows"]) - {T._WALLET.lower()},
        ),
        # `l`: lists.py's own raw-table rows (the default body, no action
        # needed).
        (
            "l", list_payload, None,
            _addresses_in(list_payload["leaderboard_rows"]) - {T._WALLET.lower()},
        ),
    )
    for view, payload, enter, row_addresses in cases:
        screen = T._screen(payload, wallet=T._WALLET)
        app = _CopyHarness(screen)
        async with app.run_test(size=(150, 55)) as pilot:
            await screen._do_refresh()
            await pilot.pause()
            if enter is not None:
                enter(screen)
                await pilot.pause()
            targets = icon_targets(app)
            assert targets, f"no copy icon on curator after entering {view!r}"
            known = _addresses_in(payload) | {T._WALLET.lower()}
            found = set()
            for x, y_, address in targets:
                assert address is not None and address.lower() in known, (view, address)
                found.add(address.lower())
            if row_addresses:
                assert found & row_addresses, (
                    view, "no icon named a row address, only the wallet's own"
                )


# ---------------------------------------------------------------------------
# list_hero at the pin (item 3 of the fix round). An asymmetric fix (drop
# only the wallet card's left border) was tried and reverted on review: a
# three-sided card between two four-sided ones is a visible asymmetry
# nobody signed off on. The symmetric replacement -- zero every card's own
# margin, one rule, all three cards -- must give the wallet card its full
# 44-column address + icon at CURATOR_FULL_LAYOUT_COLUMNS, without costing
# the other two cards their own five-line contract, and every card must
# still show all four of its own border edges.
# ---------------------------------------------------------------------------


async def test_the_list_hero_wallet_card_fits_its_full_address_and_icon_at_138():
    from tests.screens import test_curator_screen as T
    from maxpane_dashboard.screens.curator import CURATOR_FULL_LAYOUT_COLUMNS
    from maxpane_dashboard.widgets.curator.list_hero import (
        CuratorListHero,
        CuratorListHeroBox,
    )

    class _CopyHarness(CopyRecorder, T._ThemedHarness):
        pass

    screen = T._screen(T._list_payload(3), wallet=T._WALLET)
    app = _CopyHarness(screen)
    async with app.run_test(size=(CURATOR_FULL_LAYOUT_COLUMNS, T._TALL)) as pilot:
        await screen._do_refresh()
        await pilot.pause()
        hero = screen.query_one(CuratorListHero)
        box_ids = (
            "curator-list-hero-summary",
            "curator-list-hero-wallet",
            "curator-list-hero-filter",
        )
        boxes = {box_id: hero.query_one(f"#{box_id}", CuratorListHeroBox)
                 for box_id in box_ids}

        # No card is asking for more room -- the symmetric fix must not
        # merely grow the wallet card at the other two cards' expense.
        for box_id, box in boxes.items():
            assert box.border_subtitle == "", (box_id, box.border_subtitle)

        # The wallet card needs exactly 44 (measured: 42-char address +
        # ICON_COLS); the recipe never raises a documented pin, so this
        # asserts the exact number rather than merely ">= 44".
        assert boxes["curator-list-hero-wallet"].content_size.width == 44

        # Every card keeps all four of its own border edges -- the
        # reverted attempt cost the wallet card its left edge alone, which
        # is exactly what a corner-glyph check on every card catches.
        for box_id, box in boxes.items():
            text = T._region_text(app, box, screen)
            rows = text.split("\n")
            assert len(rows) == 7, (box_id, rows)
            assert rows[0][0] == "┌" and rows[0][-1] == "┐", (box_id, rows[0])
            assert rows[-1][0] == "└" and rows[-1][-1] == "┘", (box_id, rows[-1])
            for row in rows[1:-1]:
                assert row[0] == "│" and row[-1] == "│", (box_id, row)

        # The wallet card's address line shows the full, lower-cased
        # address (not windowed) with a copy icon that actually names it.
        wallet_text = T._region_text(app, boxes["curator-list-hero-wallet"], screen)
        assert T._WALLET.lower() in wallet_text
        wallet_region = boxes["curator-list-hero-wallet"].region
        addr_targets = [
            t for t in icon_targets(app)
            if wallet_region.contains(t[0], t[1]) and t[2] == T._WALLET.lower()
        ]
        assert addr_targets, icon_targets(app)


# -- E7 on the filter editor: a collection links to ITS chain (fix round 1, C1) --


async def _custom_collection_links(chain: str) -> tuple[str, list[str]]:
    """Mount the editor with one nameless custom collection on *chain*;
    return ``(address, the distinct link urls on screen)``."""
    from maxpane_dashboard.widgets.curator.list_filter import CuratorListFilterEditor

    app = _EditorApp(CuratorListFilterEditor(nft_choices=()))
    address = "0x" + "ABCDEF0123" * 4
    async with app.run_test(size=(143, 42)) as pilot:
        editor = app.query_one(CuratorListFilterEditor)
        editor.set_custom_nfts(({
            "label": f"{chain} 0xabcd…0123",
            "chain": chain,
            "address": address,
            "is_fallback": True,
        },))
        await pilot.pause()
        assert address.lower() in {t[2] for t in icon_targets(app)}, "the icon itself"
        urls = sorted({url for _x, _y, _n, _k, _v, url in link_targets(app) if url})
    return address.lower(), urls


async def test_a_base_custom_collection_links_to_basescan_not_etherscan():
    """A collection's *contract* address is not chain-agnostic the way a
    wallet is: the same 20 bytes on Base are a different contract, so the
    row links to the chain the reader chose in the editor's Select --
    never the package's wallet explorer."""
    address, urls = await _custom_collection_links("base")
    assert urls == [f"https://basescan.org/address/{address}"], urls


async def test_an_ethereum_custom_collection_links_to_etherscan():
    address, urls = await _custom_collection_links("ethereum")
    assert urls == [f"https://etherscan.io/address/{address}"], urls


async def test_a_custom_collection_on_an_unknown_chain_word_renders_its_address_unlinked():
    """Anything outside the editor's own vocabulary links nothing rather
    than guessing -- the icon still copies, the span carries no URL."""
    _address, urls = await _custom_collection_links("abstract")
    assert urls == [], urls


def test_the_collection_explorer_map_agrees_with_the_select_and_the_data_layer():
    """``NFT_CHAIN_EXPLORERS`` is a hand-typed copy of the chain vocabulary
    (a widget may not import ``data/``); this binds it to the Select's own
    option values and to ``data/curator_list_filters.NFT_CHAINS`` in both
    directions, so a third chain reddens here instead of linking nothing
    silently."""
    from maxpane_dashboard.data.curator_list_filters import NFT_CHAINS
    from maxpane_dashboard.widgets.curator.list_filter import (
        NFT_CHAIN_EXPLORERS,
        NFT_CHAIN_OPTIONS,
    )
    from maxpane_dashboard.widgets.explorer import BASE, ETHEREUM, EXPLORERS

    option_values = {value for _label, value in NFT_CHAIN_OPTIONS}
    assert set(NFT_CHAIN_EXPLORERS) == option_values == set(NFT_CHAINS)
    assert NFT_CHAIN_EXPLORERS == {"ethereum": ETHEREUM, "base": BASE}
    assert all(e is EXPLORERS[e.name] for e in NFT_CHAIN_EXPLORERS.values())


async def test_the_mounted_select_offers_exactly_the_declared_chain_options():
    """The declaration is only an agreement if the Select really uses it."""
    from textual.widgets import Select

    from maxpane_dashboard.widgets.curator.list_filter import (
        NFT_CHAIN_OPTIONS,
        CuratorListFilterEditor,
    )

    app = _EditorApp(CuratorListFilterEditor(nft_choices=()))
    async with app.run_test(size=(143, 42)) as pilot:
        await pilot.pause()
        select = app.query_one("#filter-nft-chain", Select)
        assert tuple(select._options) == NFT_CHAIN_OPTIONS
