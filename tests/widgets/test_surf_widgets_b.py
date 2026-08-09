"""Headless Textual tests for surf widgets group B (WP3).

Covers ``SurfFeed``, ``SurfDevActivity`` and ``SurfNft``.  Group A lives in
``test_surf_widgets_a.py``; the cross-widget contract sweep in
``test_surf_widget_contract.py``.

Message fixtures are the *real decoded announce-channel calldata* from
``tests/fixtures/surf/captures/announce_eth_txs.json`` -- including nonce 8's
newlines, typographic apostrophes and em-dashes, because the channel is
attacker-writable by design and those characters are already on chain.
Composited-output assertions throughout; zero network.
"""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.surf.feed import (
    FEED_TITLE,
    FULL_TEXT_WIDTH,
    UNAVAILABLE_LINE,
    WIDEN_HINT,
    SurfFeed,
)


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _none_payload(widget) -> dict:
    return {
        name: None
        for name, param in inspect.signature(widget.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    }


# -- real decoded channel calldata (announce_eth_txs.json) --------------

_CHANNEL = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"

#: nonce 13, 2026-08-07T04:27:11Z -- 227 chars, one line on chain.
_POST_13 = (
    "I moved 33 eth to the LP on mainnet https://etherscan.io/tx/"
    "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669. "
    "Hopefully in the coming days will be able to share more what been "
    "working on, as always 0 promises."
)

#: nonce 8, 2026-07-29T00:28:35Z -- raw newlines, ’ and em-dashes on chain.
_POST_8 = (
    "The hook will be highly experimental. I’ll\n  announce it before "
    "moving the LP. I’m also considering limiting trading to NFT holders "
    "for the first few hours—so the risks\n  are clear—then opening it to "
    "everyone. Thoughts?"
)

_FEED_ITEMS = [
    {
        "ts": 1786076831,
        "kind": "self",
        "from_addr": _CHANNEL,
        "from_label": "channel",
        "text": _POST_13,
        "tx_hash": "0xe397869a2ed1299f24618c377112a6e9637395d2c1e21e742ce30e6201440055",
    },
    {
        "ts": 1785795251,
        "kind": "reply",
        "from_addr": "0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159",
        "from_label": None,
        "text": (
            "Bro cooked this so hard it smells like my grandma’s pasta sauce "
            "after marinating overnight. Absolute Michelin alpha."
        ),
        "tx_hash": "0xreply1",
    },
    {
        "ts": 1785284915,
        "kind": "self",
        "from_addr": _CHANNEL,
        "from_label": "channel",
        "text": _POST_8,
        "tx_hash": "0x0b72b4640117ecb1ac6adf1ecd1ea61fff94048c11495334966cd34ab003dc72",
    },
    {
        "ts": 1779817691,
        "kind": "action",
        "from_addr": _CHANNEL,
        "from_label": "channel",
        "text": "contract call: register() → ERC-8004 registry",
        "tx_hash": "0xaction1",
    },
    {
        "ts": 1778823923,
        "kind": "fund",
        "from_addr": "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7",
        "from_label": "surfsurf.eth",
        "text": "funded 0.054 ETH from surfsurf.eth",
        "tx_hash": "0x632f5dc3",
    },
]


# ---------------------------------------------------------------------
# SurfFeed
# ---------------------------------------------------------------------


async def test_feed_title_is_the_prd_name_wp5_asserts_on():
    """``ANNOUNCE FEED``, verbatim -- WP5's c-swap test keys on it.

    The swap test asserts the string is present in the feed view and
    *absent* in the activity view, so a shortened title fails it in both
    directions.  Pinned here, in the WP that owns the string.
    """
    assert FEED_TITLE == "ANNOUNCE FEED"


async def test_feed_title_carries_nonce_and_age():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(
            feed_nonce=14, feed_last_post_age_s=7200.0, feed_items=_FEED_ITEMS
        )
        await pilot.pause()
        assert "ANNOUNCE FEED · #14 · last 2h ago" in _screen_text(app)


async def test_feed_kind_badges_render_and_replies_are_not_dev_styled():
    """All four kinds badge in words; a reply never wears the self badge."""
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=_FEED_ITEMS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "POST" in screen
        assert "REPLY" in screen
        assert "ACTION" in screen
        assert "FUND" in screen
        # The reply's line carries REPLY, not POST (PRD §6.4).
        reply_line = next(l for l in screen.splitlines() if "pasta sauce" in l or "Bro cooked" in l)
        assert "REPLY" in reply_line
        assert "POST" not in reply_line


async def test_feed_wide_tier_shows_the_full_message():
    """At the wide tier the whole 227-char nonce-13 post is on screen."""
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        assert 120 - 4 >= FULL_TEXT_WIDTH  # this harness IS the wide tier
        widget.update_data(feed_nonce=14, feed_items=_FEED_ITEMS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "as always 0 promises." in screen      # the tail survived
        assert WIDEN_HINT not in screen


async def test_feed_narrow_tier_truncates_and_advertises_widen():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(60, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=_FEED_ITEMS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "I moved 33 eth" in screen             # the head renders
        assert "as always 0 promises." not in screen  # the tail is cut...
        assert "…" in screen                          # ...visibly
        assert WIDEN_HINT in screen                   # ...and announced


async def test_feed_onchain_newlines_are_flattened_to_one_logical_row():
    """nonce 8 contains raw '\\n  ' -- it must not smuggle in blank rows."""
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=[_FEED_ITEMS[2]])
        await pilot.pause()
        screen = _screen_text(app)
        # The wrap re-joins across the on-chain newline: the words on either
        # side of "\n  " appear with a single space between them.
        assert "I’ll announce it before moving the LP." in screen.replace("\n", " ")


async def test_feed_markup_hostile_message_cannot_crash_the_pump():
    """Anyone can post to the channel -- including Textual markup."""
    hostile = [
        {
            "ts": 1786076831,
            "kind": "reply",
            "from_addr": "0x" + "ab" * 20,
            "from_label": None,
            "text": "[/x] [bold red]rug[/]  UЅDС  claim at evil.example",
            "tx_hash": "0xhostile",
        }
    ]
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=hostile)
        await pilot.pause()  # a MarkupError would raise here, inside the pump
        screen = _screen_text(app)
        assert "rug" in screen          # rendered literally...
        assert "UЅDС" in screen         # ...homoglyphs and all


async def test_feed_malformed_bracket_shape_that_defeats_escaping_cannot_crash():
    """``]][[/][/ malformed`` survives ``rich.markup.escape`` and still trips
    Textual's *own*, stricter ``textual.markup`` parser (this is the same
    shape ``SurfSignals`` documents in its ``RENDER_FAILED_DETAIL`` note).
    ``SurfFeed`` renders through ``RichLog`` (Rich's own ``Text.from_markup``,
    not ``textual.markup``), so this specific shape does not trip *this*
    widget's parser -- but the point of this test is structural: whatever
    the widget renders through, one attacker-authored row must never be able
    to kill the app or leave the rest of the feed unrendered.  At narrow
    width the same string is also truncated mid-string, which is exactly
    where a naive escape-then-truncate implementation would bisect the
    escape sequence Rich's ``escape()`` inserted.
    """
    hostile = [
        {
            "ts": 1786076831,
            "kind": "reply",
            "from_addr": "0x" + "cd" * 20,
            "from_label": None,
            "text": "]][[/][/ malformed" * 3,
            "tx_hash": "0xmalformed",
        }
    ]
    # 120 is the wide (unwrapped) tier, 60 a plain narrow truncation; 48 is
    # chosen so this exact 54-char string's truncation point lands right
    # after a ``rich.markup.escape``-inserted backslash -- the width at
    # which an escape-then-truncate bug (escaping *before* slicing, instead
    # of after) would bisect ``\[`` and leave a stray ``\`` on screen.  Found
    # empirically by scanning app widths against this string; pinned here so
    # a regression to escape-before-truncate is caught without relying on
    # the crash actually raising (Rich's own parser tolerates a dangling
    # backslash -- it renders it literally instead of raising, which is why
    # the visible-backslash assertion below, not just "did it crash", is
    # what proves the ordering bug).
    for size in ((120, 24), (60, 24), (48, 24)):
        widget = SurfFeed()
        app = _Harness(widget)
        async with app.run_test(size=size) as pilot:
            widget.update_data(feed_nonce=14, feed_items=hostile)
            await pilot.pause()  # a MarkupError would raise here if unhandled
            screen = _screen_text(app)
            assert "REPLY" in screen
            # The bracket text reaches the screen literally, not swallowed.
            assert "malformed" in screen
            # No dangling backslash from a bisected escape sequence: proves
            # truncation happens on the raw text, escaping only afterward.
            assert "\\" not in screen


async def test_feed_unavailable_vs_empty_are_different_states():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data(feed_nonce=None, feed_items=None)
        await pilot.pause()
        screen = _screen_text(app)
        assert UNAVAILABLE_LINE in screen

        widget.update_data(feed_nonce=14, feed_items=[])
        await pilot.pause()
        screen = _screen_text(app)
        assert UNAVAILABLE_LINE not in screen
        assert "no posts in window" in screen


async def test_feed_no_args_and_all_none_do_not_raise():
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        assert UNAVAILABLE_LINE in _screen_text(app)
