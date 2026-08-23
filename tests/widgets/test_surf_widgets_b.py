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
import re

import pytest
from textual.app import App, ComposeResult
from textual.color import Color

from maxpane_dashboard.themes import THEMES
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


class _ThemedHarness(_Harness):
    """The same, with every registered theme available and one selected.

    Only the colour assertions need it: ``[dim]`` is resolved by *blending the
    foreground into the background*, so what it composites to is a fact about
    the theme, not about the markup.  A default-theme measurement would say
    nothing about the ten themes this app ships.
    """

    def __init__(self, widget, theme: str) -> None:
        super().__init__(widget)
        self._theme_name = theme

    def on_mount(self) -> None:
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = self._theme_name


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _screen_lines(app) -> list[str]:
    """Composited text split into rows, trailing pad stripped.

    Row *order* and row *membership* are the claims this file makes about the
    NFT panel, and ``needle in _screen_text(app)`` can make neither: every
    string the panel renders was also somewhere on the screen before the rows
    were rearranged.
    """
    return [line.rstrip() for line in _screen_text(app).split("\n")]


def _painted(app, needle: str) -> tuple[str, str] | None:
    """``(fg, bg)`` of the first composited segment containing *needle*.

    Reads the compositor, so markup, theme and CSS have all already been
    applied -- this is the colour that reached the screen, not the tag that
    asked for it.
    """
    for strip in app.screen._compositor.render_strips():
        for segment in strip:
            if needle in segment.text and segment.style:
                style = segment.style
                if style.color and style.bgcolor:
                    return (
                        style.color.get_truecolor().hex,
                        style.bgcolor.get_truecolor().hex,
                    )
    return None


def _weight(app, needle: str) -> bool | None:
    """``style.bold`` of the first composited segment containing *needle*.

    ``None`` when the needle never reached the compositor, so "not bold" and
    "not rendered" cannot be confused.

    Separate from :func:`_painted` because bold is *not a colour*: ``_painted``
    reads ``(fg, bg)`` only, so an emphasis assertion written through it alone
    still passes with every ``[bold]`` deleted from the widget.
    """
    for strip in app.screen._compositor.render_strips():
        for segment in strip:
            if needle in segment.text and segment.style:
                return bool(segment.style.bold)
    return None


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


async def test_feed_separates_posts_with_a_blank_line():
    """Posts are multi-line and carry no other separator.

    Without a blank row a long message runs straight into the next post's
    date and the two read as one message -- which is exactly how the feed
    looked on the first real screenshot of it.

    Asserted on the composited rows, not on the markup list: a blank line
    that never reaches a pixel would separate nothing. The date column is
    the anchor because it is the first thing on a post's opening row.
    """
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 40)) as pilot:
        widget.update_data(feed_nonce=14, feed_items=_FEED_ITEMS)
        await pilot.pause()
        rows = [row.rstrip() for row in _screen_text(app).split("\n")]

        # Row indices where a post begins: its date is the leading token.
        starts = [
            i for i, row in enumerate(rows)
            if re.match(r"\s*\d\d-\d\d \d\d:\d\d\s", row)
        ]
        assert len(starts) >= 2, f"need two posts to test a separator, saw {starts}"

        # Every post after the first is preceded by a blank row.
        for i in starts[1:]:
            assert not rows[i - 1].strip(), (
                f"post at row {i} has no blank line above it: {rows[i - 1]!r}"
            )

        # And the separator is exactly one row -- two would waste a third of
        # a short feed panel on whitespace.
        for i in starts[1:]:
            assert rows[i - 2].strip(), (
                f"post at row {i} has two blank rows above it, not one"
            )


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


async def test_feed_unbreakable_token_past_budget_is_truncated_and_advertised():
    """A single unbreakable token past the wrap budget must never render
    past the usable width in silence -- fix round 1.

    ``docs/surf_game_mechanics.md`` documents a real ``EOE1.`` encrypted
    envelope (A256GCM/PBKDF2 format) the subject himself posted; it was a
    tweet, not an announce-channel tx ("no onchain counterpart found yet"
    per that doc), so the literal bytes are not part of this repo's
    committed captures. The token below mirrors that documented shape --
    ``EOE1.`` plus a long no-space base64 payload -- and the same shape
    covers any address hash, base64 blob or URL pasted into a real
    announce message: none of those contain a space for ``textwrap.wrap``
    to break on.

    ``textwrap.wrap(..., break_long_words=False)`` places such a token on
    its own line even when that line is *wider* than the wrap budget --
    confirmed directly: reverting the ``_item_lines`` fix below still keeps
    every rendered row within ``RichLog``'s own width (its internal
    ``shrink=True`` clips it regardless), but with **no** ``…`` and **no**
    ``WIDEN_HINT`` -- a silent clip, exactly what the scrollbar-gutter fix
    above exists to prevent for the *other* silent-clip path.
    """
    token = (
        "EOE1.eyJ2IjoxLCJhbGciOiJBMjU2R0NNIiwicCI6eyJuIjoyMDAwMCwiciI6OCwicCI6"
        "MX0sInMiOiI5ZjNhMWMyZTdkNGI1YTZmIn0."
        + "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5eg" * 8
    )
    hostile = [
        {
            "ts": 1785795251,
            "kind": "self",
            "from_addr": _CHANNEL,
            "from_label": "channel",
            "text": f"ledger backup: {token} -- keep this safe",
            "tx_hash": "0xenvelope",
        }
    ]
    widget = SurfFeed()
    app = _Harness(widget)
    async with app.run_test(size=(120, 24)) as pilot:
        assert 120 - 4 >= FULL_TEXT_WIDTH  # still the wide tier
        widget.update_data(feed_nonce=14, feed_items=hostile)
        await pilot.pause()
        log = widget.query_one("#surf-feed-log")
        usable = log.scrollable_content_region.width
        screen = _screen_text(app)

        # No rendered row exceeds the usable width (RichLog's own shrink
        # already guarantees this even when the marker is missing -- this
        # pins the invariant explicitly rather than relying on that as an
        # implementation detail of a widget we don't own).
        for line in screen.splitlines():
            assert len(line.rstrip()) <= usable + 1  # +1: the left gutter col

        # The blob itself was cut -- not merely re-wrapped elsewhere.
        assert token not in screen
        assert token[:40] in screen  # the head of the token still renders
        assert "ledger backup" in screen  # surrounding message still there

        # ...and the cut is visibly announced, not silent.
        assert "…" in screen
        assert WIDEN_HINT in screen


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


# ---------------------------------------------------------------------
# SurfDevActivity
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    SurfDevActivity,
    _row_markup,
)

#: The real 2026-08-07 04:2x staging choreography (ops_eth_token_transfers)
#: plus the two poisoning shapes that live in frenpet.eth's history today.
#:
#: ``wallet_label`` is the **producer's** vocabulary, not an ENS name: WP1
#: fills it from ``_DEV_WALLET_LABELS = {DEV_WALLET: "dev", OPS_WALLET:
#: "ops"}``, WP4 passes it straight through and re-checks it against
#: ``DEV_WALLETS = {"dev": ..., "ops": ...}``.  The ENS spellings live in
#: ``KNOWN_LABELS`` ("dev · surfsurf.eth" / "ops · frenpet.eth") and reach
#: the screen through the *hero*, not through this column.  The rows below
#: are all ops-wallet (frenpet.eth) history except the last, which is the
#: dev wallet (surfsurf.eth) -- hence "ops" / "dev".
_SPOOF = "0xF3083828702C1989710CECA517412071c2f60Ee6"   # 1-gwei lookalike
_REAL_UNKNOWN = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"  # LP-fee ETH dest

#: The REAL captured poisoning transfer (``tests/fixtures/surf/captures/
#: ops_eth_txs.json``, tx ``0x78dde333…``, 2026-06-06T11:48:23Z): the spoof
#: sends exactly ``1_000_000_000`` wei -- 1 gwei, ``1e-9`` ETH -- not the
#: hand-typed ``0.0`` a first pass of this fixture used.  1 gwei is Python
#: -truthy, so a bare ``not value`` check renders it; only a value
#: *threshold* (``activity._DUST_ETH``) catches it.  Used instead of a
#: literal ``0.0`` in ``_DEV_ACTIVITY`` below so the fixture exercises the
#: exact live attack shape, not a stand-in for it.
_REAL_DUST_WEI = 1_000_000_000
_REAL_DUST_TS = 1780746503
_REAL_DUST_TX = "0x78dde33315dcd41e262c26d86f75fb3cfaa03f973cc5f20b976da6d50cf743d7"

#: A REAL captured legitimate small transfer (same capture file, tx
#: ``0x98df1902…``, 2026-07-17T03:25:11Z, from an unrelated unknown
#: sender): ``95772789712599`` wei ~= ``9.577e-5`` ETH, about 95,772x the
#: dust threshold.  Proves the threshold catches the attack's exact value
#: without swallowing honest small activity that sits near it.
_REAL_SMALL_WEI = 95772789712599
_REAL_SMALL_SENDER = "0x91604F590d66Ace8975eeD6bd16cf55647d1C499"
_REAL_SMALL_TS = 1784258711
_REAL_SMALL_TX = "0x98df190207ef5afee8f806eb6002d832eff45611ce43bd85ac77106e5736d42d"

_DEV_ACTIVITY = [
    {
        "ts": 1786076603,
        "wallet_label": "ops",
        "kind": "lp",
        "counterparty": "NFPM",
        "counterparty_known": True,
        "value_eth": 33.25,
        "tx_hash": "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9e5ac258051cccb64d669",
    },
    {
        "ts": 1786076495,
        "wallet_label": "ops",
        "kind": "bridge",
        "counterparty": "OFT endpoint",
        "counterparty_known": True,
        "value_eth": 0.0,
        "tx_hash": "0xc7acbcc0b164",
    },
    {
        "ts": 1783519943,
        "wallet_label": "ops",
        "kind": "transfer",
        "counterparty": _REAL_UNKNOWN,
        "counterparty_known": False,
        "value_eth": 8.0,
        "tx_hash": "0x9ea235039668",
    },
    {  # the poisoning row: the REAL 1-gwei lookalike transfer, not 0.0
        "ts": _REAL_DUST_TS,
        "wallet_label": "ops",
        "kind": "transfer",
        "counterparty": _SPOOF,
        "counterparty_known": False,
        "value_eth": _REAL_DUST_WEI / 1e18,
        "tx_hash": _REAL_DUST_TX,
    },
    {  # manager-labelled dust: dropped regardless of any other field
        "ts": 1783518000,
        "wallet_label": "dev",
        "kind": "dust",
        "counterparty": _SPOOF,
        "counterparty_known": False,
        "value_eth": 0.0,
        "tx_hash": "0xdust2",
    },
]


async def test_activity_known_labels_and_values_render():
    """The wallet column renders the producer's label, not an ENS name.

    WP1 emits ``"dev"`` / ``"ops"`` in ``wallet_label`` and WP4 re-checks
    exactly those two keys, so a fixture spelled ``"frenpet.eth"`` would
    certify a column that never appears on screen.  The ENS spellings belong
    to ``KNOWN_LABELS`` and reach the user through the hero's ``owner ✓``
    line instead.
    """
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)
        assert "ops" in screen
        assert "frenpet.eth" not in screen   # not this column's vocabulary
        assert "NFPM" in screen
        assert "33.250 ETH" in screen
        assert "OFT endpoint" in screen   # known zero-value row still renders


async def test_activity_unknown_addresses_render_long_form_never_shortform():
    """0x+8+…+6 -- the form that distinguishes the live spoof pair."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)
        assert "0x61CC704c…73f14E" in screen
        # Never the classic first-6/last-4 shortener the spoof collides with.
        assert "0x61CC…f14E" not in screen


async def test_activity_dust_rows_are_never_rendered():
    """The poisoning vector: nothing from either dust row reaches a pixel."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)
        assert "F3083828" not in screen           # long form absent
        assert "f60Ee6" not in screen             # tail absent too
        assert "dust" not in screen               # not even the kind


def test_activity_row_markup_drop_rules_are_exact():
    """Pure-function check: exactly the poisoning triple is dropped.

    ``base`` is the REAL 1-gwei captured poisoning row (``_REAL_DUST_WEI``
    == ``1_000_000_000`` wei == ``1e-9`` ETH), Python-truthy -- proving the
    drop rule is a value *threshold*, not a ``not value`` falsiness check
    that only catches a hand-typed ``0.0``.
    """
    base = dict(_DEV_ACTIVITY[3])  # real 1-gwei unknown transfer -> dropped
    assert base["value_eth"] == 1e-9  # truthy; this is the point of the test
    assert _row_markup(base) is None
    assert _row_markup({**base, "kind": "dust", "value_eth": 5.0}) is None
    # Any leg of the triple broken -> the row renders.
    assert _row_markup({**base, "value_eth": 0.001}) is not None
    assert _row_markup({**base, "counterparty_known": True}) is not None
    assert _row_markup({**base, "kind": "burn"}) is not None
    # Malformed input degrades to a dropped row, never a raise.
    assert _row_markup(None) is None
    assert _row_markup("junk") is None
    assert _row_markup({}) is not None  # renders a dash row, doesn't raise


async def test_activity_real_captured_dust_row_is_dropped():
    """The exact live poisoning row -- real sender, real hash, real 1-gwei
    value -- from ``ops_eth_txs.json`` must never reach the screen, whole
    and standalone (not mixed into the larger ``_DEV_ACTIVITY`` fixture).
    """
    real_row = {
        "ts": _REAL_DUST_TS,
        "wallet_label": "ops",
        "kind": "transfer",
        "counterparty": _SPOOF,
        "counterparty_known": False,
        "value_eth": _REAL_DUST_WEI / 1e18,
        "tx_hash": _REAL_DUST_TX,
    }
    assert _row_markup(real_row) is None

    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=[real_row])
        await pilot.pause()
        screen = _screen_text(app)
        assert "F3083828" not in screen
        assert "no recent activity" in screen


async def test_activity_legitimate_small_transfer_still_renders():
    """A genuinely small REAL transfer (~9.577e-5 ETH, ~95,772x the dust
    threshold) from an unrelated unknown sender must still render -- the
    threshold targets the attack's exact value, not "small" in general.
    """
    real_row = {
        "ts": _REAL_SMALL_TS,
        "wallet_label": "ops",
        "kind": "transfer",
        "counterparty": _REAL_SMALL_SENDER,
        "counterparty_known": False,
        "value_eth": _REAL_SMALL_WEI / 1e18,
        "tx_hash": _REAL_SMALL_TX,
    }
    assert _row_markup(real_row) is not None

    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=[real_row])
        await pilot.pause()
        screen = _screen_text(app)
        assert "0x91604F59…d1C499" in screen  # long_addr(sender), dimmed
        assert "no recent activity" not in screen


async def test_activity_markup_hostile_label_cannot_crash_the_pump():
    """Counterparty text is third-party even when 'known' upstream."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(
            dev_activity=[
                {
                    "ts": 1786076603,
                    "wallet_label": "[/x] evil",
                    "kind": "transfer",
                    "counterparty": "[bold]Kraken[/bold]",
                    "counterparty_known": True,
                    "value_eth": 1.0,
                    "tx_hash": "0x1",
                }
            ]
        )
        await pilot.pause()  # MarkupError would surface here
        assert "Kraken" in _screen_text(app)


def test_activity_tier_table_is_measured_not_rounded():
    """Each threshold is the width its own layout really needs.

    Asserting the constants against themselves would prove nothing, so every
    tier is rendered at exactly its threshold and measured: if a format string
    grows a separator, the layout stops fitting its own number and this fails.
    """
    from maxpane_dashboard.widgets.markup_safety import visible_len
    from maxpane_dashboard.widgets.surf.activity import (
        COMPACT_WIDTH,
        FULL_WIDTH,
        MINIMAL_WIDTH,
        _tier_for,
    )

    assert FULL_WIDTH > COMPACT_WIDTH > MINIMAL_WIDTH
    # ``0`` is "not laid out yet" and optimistically picks the widest layout;
    # ``on_resize`` corrects it once the panel has a size.
    assert _tier_for(0) == "full"
    assert _tier_for(FULL_WIDTH) == "full"
    assert _tier_for(FULL_WIDTH - 1) == "compact"
    assert _tier_for(COMPACT_WIDTH) == "compact"
    assert _tier_for(COMPACT_WIDTH - 1) == "minimal"

    # The widest row this feed produces: an unknown 17-column counterparty
    # window and a two-digit ETH amount.
    row = _DEV_ACTIVITY[2]
    for tier, need in (
        ("full", FULL_WIDTH),
        ("compact", COMPACT_WIDTH),
        ("minimal", MINIMAL_WIDTH),
    ):
        markup = _row_markup(row, tier, need)
        assert markup is not None
        assert visible_len(markup) <= need, (
            f"{tier} needs more than the {need} columns it advertises"
        )
        assert "0x61CC704c…73f14E" in markup


def test_activity_the_wallet_column_yields_before_the_address_window():
    """Below the narrowest tier the address window is still never cut.

    ``RichLog(wrap=False)`` would shrink the line silently, and a window cut
    to ``0xF308`` re-creates the exact spoof collision this module exists to
    prevent.  The wallet label is a *label*: it shrinks, then goes whole.  The
    window is a fingerprint and does neither.
    """
    from maxpane_dashboard.widgets.markup_safety import visible_len
    from maxpane_dashboard.widgets.surf.activity import ADDR_COLS, MINIMAL_WIDTH

    row = _DEV_ACTIVITY[2]  # unknown counterparty, 8 ETH transfer
    # "MM-DD" + gap + the window: the last width that still carries a date.
    # It is *not* the absolute floor -- the date goes too, one column below,
    # and ``test_activity_never_writes_a_row_wider_than_the_log_it_goes_in``
    # sweeps from here to zero.
    floor = 5 + 2 + ADDR_COLS
    for width in range(MINIMAL_WIDTH, floor - 1, -1):
        markup = _row_markup(row, "minimal", width)
        assert markup is not None
        assert "0x61CC704c…73f14E" in markup, f"window cut at width {width}"
        assert visible_len(markup) <= width, f"row overflows at width {width}"


def test_activity_never_writes_a_row_wider_than_the_log_it_goes_in():
    """``RichLog(wrap=False)`` shrinks silently, so the row must fit already.

    The sweep above stopped at ``5 + 2 + ADDR_COLS`` -- 24, the last width
    that works -- and the defect lived one column below it.  With the wallet
    cell gone the row is *still* ``MM-DD`` + gap + window == 24 columns, and
    the right rail hands this panel ``ceil(6W/13) - 5`` == 23 at a 59-60
    column terminal.  ``write()`` then narrowed the line with no ``…``, no
    marker and nothing in the title: ``0x61CC704c…73f14`` at 60 columns --
    a truncated address that no longer looks truncated -- and at 40 the
    ``…`` itself went, leaving ``0x61CC7``.

    Two invariants, swept to zero over every tier and both counterparty
    kinds, because the fitting arithmetic is per-cell and each dropped cell
    also drops a ``_GAP``:

    * a row that is rendered fits the width it was rendered for;
    * a rendered *unknown* counterparty is the whole window, never a prefix
      of it -- cut to ``0xF308`` both live spoofs collide with their targets.

    Below the window's own width there is no field left to shed, so the row
    is withheld (``None``) rather than cut, and the panel says so instead of
    showing it (``test_activity_withholds_the_rows_it_cannot_render_whole``).
    """
    from maxpane_dashboard.widgets.markup_safety import visible_len
    from maxpane_dashboard.widgets.surf.activity import FLOOR_WIDTH, MINIMAL_WIDTH

    window = "0x61CC704c…73f14E"
    unknown = _DEV_ACTIVITY[2]          # unknown counterparty, 8 ETH
    known = _DEV_ACTIVITY[0]            # known label, 33.25 ETH
    for tier in ("full", "compact", "minimal"):
        for width in range(1, MINIMAL_WIDTH + 1):
            for row in (unknown, known):
                markup = _row_markup(row, tier, width)
                if markup is None:
                    continue
                assert visible_len(markup) <= width, (
                    f"{tier} row overflows a {width}-column log by "
                    f"{visible_len(markup) - width}: RichLog will shrink it "
                    f"with no ellipsis -- {markup!r}"
                )
            cut = _row_markup(unknown, tier, width)
            if cut is not None:
                assert window in cut, (
                    f"the anti-poisoning window was cut at width {width} "
                    f"({tier}): {cut!r}"
                )

    # ...and the floor is the window itself: at ``FLOOR_WIDTH`` every row
    # still renders, one column below it the widest one cannot.  Without
    # this the invariants above are satisfied by a widget that renders
    # nothing at any width.
    assert _row_markup(unknown, "minimal", FLOOR_WIDTH) is not None
    assert window in _row_markup(unknown, "minimal", FLOOR_WIDTH)
    assert _row_markup(unknown, "minimal", FLOOR_WIDTH - 1) is None


def test_activity_the_wallet_cell_is_whole_or_gone_never_shrunk():
    """Three columns against a two-member vocabulary have nothing to shrink.

    ``_budget`` used to narrow the cell one column at a time
    (``max(wallet_cols + spare, 0)``), so the widths just above the drop
    rendered ``de`` and ``op`` -- cut with no ``…`` and nothing in the title,
    which is the same silent-cut defect as the ``fwa clai`` one cell to the
    right. Shedding it whole is what the module's own rule asks for, and it
    is also what keeps two adjacent rows in the same columns.

    On ``_budget`` rather than on pixels because it is the rule that is being
    pinned, at every width and tier at once;
    ``test_activity_columns_never_disagree_between_two_rows`` renders it.
    """
    from maxpane_dashboard.widgets.surf.activity import (
        FULL_WIDTH,
        _WALLET_COLS,
        _budget,
    )

    seen = set()
    for tier in ("full", "compact", "minimal"):
        for width in range(1, FULL_WIDTH + 1):
            for who, known in (("0x61CC704c…73f14E", False), ("NFPM", True)):
                _keep, wallet_cols, _who = _budget(
                    tier, width, 11, who, known, 12
                )
                assert wallet_cols in (0, _WALLET_COLS), (
                    f"the wallet cell was shrunk to {wallet_cols} columns at "
                    f"width {width} ({tier}): a cut label, not a shed one"
                )
                seen.add(wallet_cols)
    # Both outcomes really occur, so the assertion is not vacuously true of a
    # cell that is simply always there.
    assert seen == {0, _WALLET_COLS}


def test_activity_cells_are_sized_from_the_producers_own_vocabularies():
    """The cross-layer pin. **This is what makes the narrow cells safe.**

    ``widgets/`` may not import from ``data/`` (CLAUDE.md), so
    ``_WALLET_COLS`` and ``_KIND_COLS`` are literals in the widget. A *test*
    may import both sides, and this one does: it is the only thing standing
    between a producer that grows a longer label and a user discovering a
    truncated cell.

    Both defects it was written for were real. ``_WALLET_COLS`` was **12**
    against a vocabulary of ``{"dev", "ops"}`` -- nine dead columns on every
    row, which is the gap the user reported between the wallet and the kind
    column. ``_KIND_COLS`` was **8** against a vocabulary containing
    ``"fwa claim"``, so that kind rendered ``fwa clai``: cut mid-word, no
    ``…``, nothing in the title. Equality in both directions on purpose --
    ``>=`` re-admits the padding, ``<=`` re-admits the cut.
    """
    from maxpane_dashboard.data.surf_client import (
        DEV_TX_KINDS,
        _DEV_WALLET_LABELS,
    )
    from maxpane_dashboard.widgets.surf._fmt import DASH
    from maxpane_dashboard.widgets.surf.activity import (
        FULL_WIDTH,
        _KIND_COLS,
        _WALLET_COLS,
    )

    # ``DASH`` is what each cell falls back to when the field is missing, so
    # it is part of the vocabulary the cell has to hold.
    labels = set(_DEV_WALLET_LABELS.values()) | {DASH}
    assert _WALLET_COLS == max(len(x) for x in labels), (
        f"the wallet cell is {_WALLET_COLS} columns for a vocabulary whose "
        f"widest member is {max(labels, key=len)!r}"
    )
    kinds = set(DEV_TX_KINDS) | {DASH}
    assert _KIND_COLS == max(len(k) for k in kinds), (
        f"the kind cell is {_KIND_COLS} columns for a vocabulary whose "
        f"widest member is {max(kinds, key=len)!r}"
    )

    # ...and every member really does survive whole through the renderer, not
    # merely fit an arithmetic check on the constants.
    for kind in sorted(DEV_TX_KINDS):
        markup = _row_markup(
            {
                "ts": 1786076603,
                "wallet_label": "ops",
                "kind": kind,
                "counterparty": "NFPM",
                "counterparty_known": True,
                "value_eth": 1.0,
            },
            "full",
            FULL_WIDTH,
        )
        assert markup is not None and kind in markup, f"{kind!r} was cut"


async def test_activity_spends_no_columns_between_the_wallet_and_the_kind():
    """The reported defect, on composited pixels rather than on a constant.

    ``fwa claim`` is the widest kind the producer emits and ``ops`` a whole
    member of the wallet vocabulary, so the two cells are exactly full here:
    the only thing that may separate them is the one ``_GAP``. Rendered
    before the fix this read ``ops`` + eleven spaces + ``fwa clai``.
    """
    from maxpane_dashboard.widgets.surf.activity import _GAP

    # Both sides of the assertion below are built from ``_GAP``, so widening
    # it would move them together and leave this green. Pinned here, once:
    # two columns between cells is the design, not a derived quantity.
    assert _GAP == 2

    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(
            dev_activity=[
                {
                    "ts": 1786076603,
                    "wallet_label": "ops",
                    "kind": "fwa claim",
                    "counterparty": "FWA splitter",
                    "counterparty_known": True,
                    "value_eth": 1.5,
                    "tx_hash": "0xfwa",
                }
            ]
        )
        await pilot.pause()
        screen = _screen_text(app)
        gap = " " * _GAP
        # The whole run of cells, so a cell that is too *wide* fails here as
        # well as one that is too narrow: an over-padded kind cell puts three
        # spaces before the counterparty and this stops matching.
        assert f"ops{gap}fwa claim{gap}FWA splitter{gap}1.500 ETH" in screen, (
            "the wallet cell still pads past its vocabulary, or the kind "
            f"cell still cuts 'fwa claim':\n{screen}"
        )


#: Every hex run this panel may put on screen, as a regex. Asserting on the
#: whole window as a literal would be satisfied by a panel that also renders
#: a *prefix* of it somewhere -- and a prefix is precisely the defect: cut to
#: ``0xF308`` the two live spoof addresses collide with the two real fee
#: recipients they impersonate.
#: ``*`` and not ``+``: the narrowest clip of all left a bare ``0x`` behind,
#: which a ``+`` quantifier does not match at all.
_HEX_RUN = re.compile(r"0x[0-9A-Fa-f…]*")


async def _activity_lines(width: int, rows: list[dict]) -> list[str]:
    """Composited rows of a standalone activity panel at *width* columns."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(width, 20)) as pilot:
        widget.update_data(dev_activity=rows)
        await pilot.pause()
        return _screen_text(app).splitlines()


async def test_activity_withholds_the_rows_it_cannot_render_whole():
    """Narrower than the window, the panel says ``‹ widen`` -- it never cuts.

    Composited, across every width from below the narrowest tier down to a
    log too narrow for the address alone. The rule is the module's whole
    reason to exist: **no hex run on this panel is ever a prefix of the
    window**. Before the fix a 60-column terminal rendered
    ``0x61CC704c…73f14`` and a 40-column one ``0x61CC7``, the second with
    the ``…`` gone as well, so a truncated address stopped looking truncated.

    Withholding is not the same as having nothing to show: ``no recent
    activity`` at a width where rows exist would be a different lie, so it is
    excluded by name.
    """
    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT

    window = "0x61CC704c…73f14E"
    rows = [_DEV_ACTIVITY[0], _DEV_ACTIVITY[2]]  # a known label and the window
    withheld = 0
    for width in range(12, 34):
        lines = await _activity_lines(width, rows)
        text = "\n".join(lines)
        for run in _HEX_RUN.findall(text):
            assert run == window, (
                f"{run!r} at {width} columns is a cut anti-poisoning window"
            )
        assert "no recent activity" not in text, (
            f"{width} columns claims the wallets are quiet; they are not"
        )
        if window not in text:
            withheld += 1
            assert SHORT_HINT in text, (
                f"the rows went at {width} columns with nothing said at all"
            )
    # ...and the sweep really does cross the floor, so the assertions above
    # are not all being made about the same branch.
    assert 0 < withheld < 22, (
        f"{withheld} of 22 widths withheld their rows -- the sweep no longer "
        "straddles the width where the window stops fitting"
    )


async def test_activity_columns_never_disagree_between_two_rows():
    """One budget for the batch, not one per row.

    ``_budget`` sized the wallet cell from *that row's* counterparty, so a
    row whose window is 17 columns dropped the cell while the ``NFPM`` row
    beside it kept it -- at 70 columns that put ``08-07  de  0x61CC…`` above
    ``08-07  ops  NFPM``: two counterparty columns, three different wallet
    widths, and ``dev``/``ops`` cut to two letters with no ``…``.
    ``RichLog`` is composed ``wrap=False`` precisely so the columns line up
    down the panel, which only holds if every row is fitted to the same plan.

    Swept, because the disagreement only appears where one row can afford a
    cell the other cannot.
    """
    rows = [_DEV_ACTIVITY[0], _DEV_ACTIVITY[1], _DEV_ACTIVITY[2]]
    marks = ("NFPM", "OFT endpoint", "0x61CC704c…73f14E")
    # From the narrowest terminal that still fits every row (a 17-column log
    # -- the window alone, date and all) up through both tier boundaries. The
    # disagreement lived at the bottom of this range, where the 17-column
    # window can no longer afford a cell that ``NFPM`` beside it still can:
    # the wallet cell below a 29-column log, the date below a 24-column one.
    for width in sorted(set(range(20, 120, 2)) | {21, 27, 28, 30, 32, 49, 61,
                                                  70, 143}):
        lines = await _activity_lines(width, rows)
        starts = {
            mark: line.index(mark)
            for mark in marks
            for line in lines
            if mark in line
        }
        assert len(starts) == len(marks), (
            f"only {sorted(starts)} rendered at {width} columns"
        )
        assert len(set(starts.values())) == 1, (
            f"the counterparty column moves between rows at {width} "
            f"columns: {starts}"
        )
        # The wallet cell is all-or-nothing, so the labels agree too: either
        # every row carries one whole or none does. A two-letter ``de`` is
        # the silent cut this rules out.
        labels = [bool(re.search(r"\d\d\s+(dev|ops)\s", line)) for line in lines
                  if any(mark in line for mark in marks)]
        assert len(set(labels)) == 1, (
            f"some rows carry a wallet label at {width} columns and some do "
            f"not: {lines}"
        )
        # ...and whole. A cell shrunk to two columns is cut on *every* row at
        # once, so the agreement assertion above cannot see it: this looks at
        # the cell's own text, immediately after the stamp and its gap.
        for line in lines:
            assert not re.search(r"\d\d {2}(?:de|d|op|o)(?= )", line), (
                f"the wallet label is cut at {width} columns: {line!r}"
            )


async def test_activity_relays_out_on_resize_never_shrunk_by_richlog():
    """The tier tracks the terminal, and the title tracks the tier."""
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)
        assert "33.250 ETH" in screen
        assert "‹ widen" not in screen

        # Narrower than the full row: the amount goes, and is advertised.
        await pilot.resize_terminal(60, 20)
        await pilot.pause()
        screen = _screen_text(app)
        assert "33.250 ETH" not in screen
        assert "‹ widen for amounts" in screen
        assert "0x61CC704c…73f14E" in screen

        # ...and widening puts it back, with the marker dark again.
        await pilot.resize_terminal(110, 20)
        await pilot.pause()
        screen = _screen_text(app)
        assert "33.250 ETH" in screen
        assert "‹ widen" not in screen


async def test_activity_a_panel_too_narrow_to_name_what_it_shed_still_says_so():
    """A panel narrower than its own hint must not go silent.

    The hint is appended to the title and dropped when it cannot fit beside
    it, because this ``Static`` has no ``text-overflow`` and an over-long
    title wraps onto a second line, pushing a row out of the log.  That was
    harmless while the panel had a ``3fr`` slot -- ``DEV ACTIVITY`` plus the
    24-column minimal hint needs 38, and the slot was wider than that at
    every width the dashboard runs at.  In the right rail it is not: at 80
    terminal columns the panel is 30 wide, sheds the time, kind and amount
    columns, and used to say nothing at all about it.

    The bare marker is the fallback: it names no field, but "something was
    dropped here" is the contract, and it fits in seven columns.

    **36, not 34.** ``SHORT_HINT`` is a *prefix* of both descriptive hints, so
    ``SHORT_HINT in screen`` alone cannot tell the fallback from a hint for the
    wrong tier -- and the width chosen decides whether it can tell at all. The
    panel here is on the ``minimal`` tier, whose 24-column hint needs 38; the
    ``compact`` hint needs 33. At 34 columns *neither* fits, so a fallback
    chain wrongly routed through ``compact`` renders exactly what the correct
    one renders and no assertion at that width can see the difference. 36 is
    inside the 35..39 band where ``compact`` fits and ``minimal`` does not,
    which is the only place the routing is observable at all -- verified by
    mutating the chain and watching this test, and only this test, redden.
    """
    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT, WIDEN_HINTS

    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(36, 20)) as pilot:
        widget.update_data(dev_activity=_DEV_ACTIVITY)
        await pilot.pause()
        screen = _screen_text(app)

        assert WIDEN_HINTS["minimal"] not in screen, (
            "the descriptive hint fits after all at 36 columns -- re-measure"
        )
        # The tier's own hint does not fit; a hint belonging to a *wider* tier
        # does, and would name ``amounts`` while staying silent about the time
        # and kind columns this tier also shed.
        assert WIDEN_HINTS["compact"] not in screen, (
            "the panel fell back to a hint for a tier it is not in"
        )
        assert SHORT_HINT in screen, "the panel shed three columns in silence"
        # The fallback never costs the log a row: the title is still one line.
        assert "0x61CC704c…73f14E" in screen


async def test_activity_unavailable_vs_empty_vs_none_args():
    widget = SurfDevActivity()
    app = _Harness(widget)
    async with app.run_test(size=(110, 20)) as pilot:
        widget.update_data(dev_activity=None)
        await pilot.pause()
        assert "activity unavailable" in _screen_text(app)

        widget.update_data(dev_activity=[])
        await pilot.pause()
        screen = _screen_text(app)
        assert "no recent activity" in screen
        assert "activity unavailable" not in screen

        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        assert "activity unavailable" in _screen_text(app)


# -- SurfDevActivity: the launchpad label allowlist ----------------------
#
# LaunchpadHook was the dev's single most frequent counterparty and used to
# render as an anonymous truncated hex address purely because it was absent
# from the label allowlist -- WP1 (Task 1 of the v4/launchpad plan) added
# LAUNCHPAD_HOOK, LAUNCHPAD_FACTORY and BURN_EXECUTOR_V2 to
# ``data/surf_addresses.KNOWN_LABELS``. This widget never imports that map
# (widgets receive primitives only, CLAUDE.md) and renders whatever
# ``counterparty`` / ``counterparty_known`` it is handed, so the fix lives
# entirely upstream in the manager's allowlist lookup; what belongs here is
# proof the render side actually surfaces it, and proof a lookalike absent
# from the allowlist still renders dimmed and truncated -- no fallback, no
# fuzzy match, no prefix match (PRD §4 / CLAUDE.md's address-poisoning
# defense).


async def test_activity_a_known_launchpad_counterparty_renders_as_its_label():
    """``burnAccruedImd`` -- the dev's most frequent call -- classifies as
    the existing ``burn`` kind (``surf_client.DEV_TX_KINDS`` already carried
    it), so this exercises the exact row shape the migration produces."""
    row = {
        "ts": 1000.0,
        "wallet_label": "dev",
        "kind": "burn",
        "counterparty": "LaunchpadHook",
        "counterparty_known": True,
        "value_eth": 0.0,
        "tx_hash": "0x" + "aa" * 32,
    }
    lines = await _activity_lines(110, [row])
    text = "\n".join(lines)
    assert "LaunchpadHook" in text
    assert "burn" in text


async def test_activity_an_unknown_launchpad_lookalike_still_renders_dimmed_and_truncated():
    """The allowlist is the poisoning defence: a lookalike that is one hex
    digit off the real ``LAUNCHPAD_HOOK`` address and arrives with
    ``counterparty_known=False`` must still render through the anti-
    poisoning window, never the trusted label -- proving there is no
    fallback, fuzzy, or prefix match anywhere in the render path either.
    """
    from maxpane_dashboard.data.surf_addresses import LAUNCHPAD_HOOK
    from maxpane_dashboard.widgets.surf._fmt import long_addr

    lookalike = "0x" + ("0" if LAUNCHPAD_HOOK[2] != "0" else "1") + LAUNCHPAD_HOOK[3:]
    assert lookalike.lower() != LAUNCHPAD_HOOK.lower()
    row = {
        "ts": 1000.0,
        "wallet_label": "dev",
        "kind": "burn",
        "counterparty": lookalike,
        "counterparty_known": False,
        "value_eth": 0.0,
        "tx_hash": "0x" + "bb" * 32,
    }
    lines = await _activity_lines(110, [row])
    text = "\n".join(lines)
    assert "LaunchpadHook" not in text
    assert long_addr(lookalike) in text


def test_the_kind_vocabulary_did_not_grow():
    """``burnAccruedImd`` maps onto the existing ``burn`` kind, so the kind
    cell's width is unchanged and surf's 142/143 columns are safe. A
    standing guard, not a regression test: shorten a label if a future kind
    ever needs one, and never widen the layout for it.
    """
    from maxpane_dashboard.data.surf_client import DEV_TX_KINDS
    from maxpane_dashboard.widgets.surf.activity import _KIND_COLS

    assert DEV_TX_KINDS == frozenset(
        {"deploy", "lp", "burn", "bridge", "fwa claim", "transfer", "other"}
    )
    assert max(len(k) for k in DEV_TX_KINDS) == len("fwa claim")
    assert _KIND_COLS == 9


# ---------------------------------------------------------------------
# SurfNft
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.nft import (  # noqa: E402
    FLOOR_UNAVAILABLE,
    SurfNft,
)

#: identity_counters.json (667 holders), research (38 transfers/day, dev
#: holds 3, 1/2000 written).
#:
#: The sales are the **only** realized IDMD prices anyone has decoded: both
#: legs of the dev wallet's Seaport purchase ``0x5b4d1b44...eadad2`` at ts
#: 1786163591 -- token 1751 at 0.18 ETH and token 354 at 0.1838989 ETH,
#: whose realized values sum to the transaction's own ``value`` exactly
#: (WP1 §"One real Seaport purchase").  They are decoded from that tx's
#: ``OrderFulfilled`` logs, *not* from ``identity_transfers_page1.json``:
#: WP0.7's ``test_no_idmd_transfer_row_carries_a_price`` pins that no row of
#: that capture carries a price at all, so a price attributed to one would
#: be invented -- which is what the header of this file promises not to do.
_FULL_NFT = {
    "nft_holders": 667,
    "nft_transfers_24h": 38,
    "nft_dev_holdings": 3,
    "nft_written": 1,
    "nft_last_sales": [
        {"ts": 1786163591, "token_id": 1751, "eth": 0.18},
        {"ts": 1786163591, "token_id": 354, "eth": 0.1838989},
    ],
    "nft_floor": None,  # pinned None in v1 (PRD §5)
}


async def test_nft_full_payload_renders_stats_and_sales():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        screen = _screen_text(app)
        assert "667" in screen and "holders" in screen
        assert "38" in screen and "transfers/24h" in screen
        assert "dev holds 3" in screen
        assert "1/2000 written" in screen
        # Both legs of the one real Seaport fill, at three decimals.
        assert "#1751" in screen and "0.180 ETH" in screen
        assert "#354" in screen and "0.184 ETH" in screen


async def test_nft_rows_are_stats_then_dev_holdings_then_floor_then_sales():
    """Row *membership* and row *order*, composited line by line.

    Every string asserted here was on the screen under the previous
    arrangement too -- the written count sat on its own row reading
    ``identities 1/2000 written`` and ``dev holds 3`` was the tail of the
    stats row -- so a ``needle in screen_text`` assertion cannot tell the two
    layouts apart, and this whole rearrangement would be invisible to it.
    """
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        lines = _screen_lines(app)
        first = next(i for i, line in enumerate(lines) if "holders" in line)
        assert [line.strip() for line in lines[first : first + 5]] == [
            "667 holders · 38 transfers/24h · 1/2000 written",
            "dev holds 3 identities",
            f"floor {FLOOR_UNAVAILABLE}",
            # The blank row asked for on 2026-08-11: the collection's figures
            # and the sales block answer different questions, and the floor
            # line reads as part of the sales story without it. Asserted as
            # an empty element of the sequence rather than skipped, so a row
            # that quietly collapses fails here.
            "",
            "last sales (Seaport)",
        ]
        # The old wording of the written row, which must not survive anywhere:
        # ``identities`` now labels the dev holdings and nothing else.
        assert "identities 1/2000" not in _screen_text(app)


async def test_nft_dev_holdings_row_degrades_to_a_dash_never_to_zero():
    """A dead Blockscout is not a dev who sold out.

    The dev row is the one row this rearrangement created, so it needs its own
    ``--`` proof: ``dev holds 0 identities`` would be a claim about the dev's
    wallet that no read was able to make.
    """
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**{**_FULL_NFT, "nft_dev_holdings": None})
        await pilot.pause()
        lines = _screen_lines(app)
        assert any(line.strip() == "dev holds -- identities" for line in lines), lines
        assert "dev holds 0" not in _screen_text(app)


async def test_nft_floor_is_the_explicit_unavailable_state_never_a_number():
    """No keyless floor source exists; the UI says so (PRD §5 nft_floor)."""
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        screen = _screen_text(app)
        assert FLOOR_UNAVAILABLE in screen
        assert "floor 0" not in screen           # never faked as zero

        # v2 escape hatch: if a float ever arrives, render it -- with units.
        # 0.25 is a *hypothetical* v2 value, deliberately not one of the two
        # realized prices above, so this assertion cannot be satisfied by a
        # sale line; there is no keyless floor source to take a real one from.
        widget.update_data(**{**_FULL_NFT, "nft_floor": 0.25})
        await pilot.pause()
        screen = _screen_text(app)
        assert "0.250 ETH" in screen
        assert FLOOR_UNAVAILABLE not in screen


@pytest.mark.parametrize("theme_name", sorted(THEMES))
async def test_nft_missing_floor_is_muted_not_warned(theme_name):
    """The absence is permanent, so it is de-emphasised rather than flagged.

    It rendered ``[yellow]`` -- the warning vocabulary -- for a fact that
    cannot change: there is no keyless floor source for this collection at
    all (PRD §5), so the line is a standing statement, not an alert about
    something wrong right now.  A warning colour on a permanent condition is
    a warning the eye learns to skip.

    Pinned as a *relationship*, not as a hex literal: the value must composite
    at exactly the de-emphasis the panel's own labels already use, which is
    what ``[dim]`` means once the theme has resolved it, and must not
    composite at the theme's warning colour.  Every registered theme, because
    ``[dim]`` is a blend of foreground into background and its result is a
    property of the palette.
    """
    widget = SurfNft()
    app = _ThemedHarness(widget, theme_name)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()

        value = _painted(app, FLOOR_UNAVAILABLE)
        label = _painted(app, "holders")       # a [dim] label on the stats row
        figure = _painted(app, "667")          # a [bold] figure on the same row
        assert value and label and figure
        assert value[0] == label[0], (
            f"{theme_name}: the floor value composites at {value[0]}, the "
            f"panel's muted labels at {label[0]}"
        )
        assert value[0] != figure[0], f"{theme_name}: still at full emphasis"

        warning = Color.parse(app.current_theme.warning).hex.lower()
        assert value[0].lower() != warning, f"{theme_name}: still a warning"
        assert value[0].lower() != "#ffff00", f"{theme_name}: still [yellow]"


@pytest.mark.parametrize("theme_name", sorted(THEMES))
async def test_nft_muted_floor_is_still_legible_in_every_theme(theme_name):
    """Muted, not erased -- the line exists to say *why* there is no floor.

    ``[dim]`` blends the foreground toward the background, so "de-emphasised"
    and "invisible" are the same instruction with a different palette behind
    it.  WCAG AA for body text is the floor; the ruler is the accessibility
    suite's own, imported rather than retyped so the two cannot disagree.
    """
    from tests.widgets.test_fwa_accessibility import AA, contrast

    widget = SurfNft()
    app = _ThemedHarness(widget, theme_name)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        painted = _painted(app, FLOOR_UNAVAILABLE)
        assert painted, "the floor line never reached the compositor"
        fg, bg = painted
        assert contrast(fg, bg) >= AA, (
            f"{theme_name}: the muted floor line is {contrast(fg, bg):.2f}:1 "
            f"against its background ({fg} on {bg}) -- that is dimmed to "
            "unreadable, not de-emphasised"
        )


@pytest.mark.parametrize("theme_name", sorted(THEMES))
async def test_nft_a_real_floor_keeps_its_emphasis(theme_name):
    """Only the *absence* is muted.  A number is news; a permanent gap is not.

    The v2 escape hatch renders ``floor 0.250 ETH`` in bold, and muting that
    too would be the wrong lesson from this change: it would hide the one
    value the row is for on the day a keyless source finally exists.

    Emphasis here is **two** properties and the test has to read both.  For
    one build it read only the colour: ``_painted`` returns ``(fg, bg)``, and
    ``bold`` is a style attribute rather than a colour, so deleting ``[bold]``
    from the real-floor branch while leaving its colour alone kept every
    assertion below green -- the one property this test is named for was
    unguarded.  :func:`_weight` reads the composited ``style.bold``.
    """
    widget = SurfNft()
    app = _ThemedHarness(widget, theme_name)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**{**_FULL_NFT, "nft_floor": 0.25})
        await pilot.pause()
        value = _painted(app, "0.250 ETH")
        label = _painted(app, "floor")         # the [dim] label beside it
        figure = _painted(app, "667")          # a [bold] figure elsewhere
        assert value and label and figure
        assert value[0] == figure[0], f"{theme_name}: the real floor was muted"
        assert value[0] != label[0], f"{theme_name}: level with its own label"

        assert _weight(app, "0.250 ETH") is True, (
            f"{theme_name}: the real floor reached the screen un-bolded -- it "
            "is the colour of a figure without the weight of one"
        )
        assert _weight(app, "667") is True, (
            f"{theme_name}: the reference figure is not bold either, so the "
            "assertion above proves nothing about this panel"
        )
        assert _weight(app, "floor") is False, (
            f"{theme_name}: the label went bold with its value"
        )


async def test_nft_sales_unavailable_vs_empty():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(**{**_FULL_NFT, "nft_last_sales": None})
        await pilot.pause()
        assert "sales unavailable" in _screen_text(app)

        widget.update_data(**{**_FULL_NFT, "nft_last_sales": []})
        await pilot.pause()
        screen = _screen_text(app)
        assert "no sales in window" in screen
        assert "sales unavailable" not in screen


async def test_nft_no_args_and_all_none_render_dashes_never_zero():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        screen = _screen_text(app)
        # A dead Blockscout is not a collection with zero holders.
        assert "0 holders" not in screen
        assert f"{FLOOR_UNAVAILABLE}" in screen
        assert "--" in screen


async def test_nft_shows_three_sales_and_counts_the_ones_it_can_render():
    """The cap counts *rendered* rows, not raw ones.

    Slicing the raw list first let a malformed row eat one of the slots, so
    the panel showed fewer sales than it had. At ``_MAX_SALES`` 4 that was
    invisible -- there was a spare slot to absorb it -- and dropping to 3
    exposed it: three bad rows at the head emptied the block while good
    sales sat directly behind them. Both halves are asserted here because
    the cap alone would pass on a list with no malformed rows at all.
    """
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 20)) as pilot:
        clean = [
            {"ts": 1786163591, "token_id": 100 + i, "eth": 0.2 + i / 100}
            for i in range(6)
        ]
        widget.update_data(**{**_FULL_NFT, "nft_last_sales": clean})
        await pilot.pause()
        shown = [f"#{100 + i}" for i in range(6) if f"#{100 + i}" in _screen_text(app)]
        assert shown == ["#100", "#101", "#102"], (
            f"expected the three newest sales, got {shown}"
        )

        # Three unusable rows ahead of three good ones: the block must still
        # fill, which is what slicing-before-skipping got wrong.
        widget.update_data(
            **{
                **_FULL_NFT,
                "nft_last_sales": [None, "junk", {"ts": None, "token_id": None,
                                                  "eth": None}] + clean[:3],
            }
        )
        await pilot.pause()
        text = _screen_text(app)
        assert all(f"#{100 + i}" in text for i in range(3)), (
            "malformed rows consumed the sale slots instead of being skipped"
        )


async def test_nft_malformed_sale_rows_are_skipped():
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(90, 16)) as pilot:
        widget.update_data(
            **{
                **_FULL_NFT,
                "nft_last_sales": [
                    None,
                    "junk",
                    {"ts": None, "token_id": None, "eth": None},
                    {"ts": 1786163591, "token_id": 1751, "eth": 0.18},
                ],
            }
        )
        await pilot.pause()
        assert "#1751" in _screen_text(app)


def test_nft_stats_budget_matches_what_the_markup_actually_renders():
    """The tier is chosen on a plain string; the panel paints markup.

    If the two drift the panel measures one row and renders another -- a
    silent clip with the marker *dark*, which is strictly worse than no
    tiering at all.  Compared through Textual's own markup parser rather than
    a hand-rolled tag stripper, so the check cannot agree with the widget by
    repeating its bug.
    """
    from textual.content import Content

    from maxpane_dashboard.widgets.surf.nft import _stats_markup, _stats_variants

    variants = _stats_variants("667", "38", "1")
    for tier, plain in variants.items():
        rendered = Content.from_markup(_stats_markup(tier, "667", "38", "1")).plain
        assert rendered == plain, f"{tier}: {rendered!r} != {plain!r}"
    # The ladder only works if every rung is strictly narrower than the one
    # above it -- equal rungs would make a tier unreachable.
    assert (
        len(variants["full"])
        > len(variants["compact"])
        > len(variants["minimal"])
    )


def test_nft_every_budget_string_matches_the_markup_beside_it():
    """The stats row was the only pair pinned; these are all the others.

    ``_dev_row``, ``_sale_line``, ``_floor_row`` and the sales block's fixed
    rows each hand-pair a plain string with a markup one, and the plain half
    is what ``_render_view`` puts into ``widths`` -- the list that decides
    whether the bare marker lights for a row the tier ladder cannot shorten.
    A pair that drifts measures one string and paints another, which is a clip
    with the title claiming nothing was shed.

    The fixed pairs are *discovered* from the module rather than listed, so a
    row added later is covered without anyone remembering to come back here;
    the count is asserted so the discovery cannot quietly find nothing and
    pass.  Compared through Textual's own parser, never a hand-rolled tag
    stripper, which would only agree with the widget by repeating its bug.
    """
    from textual.content import Content

    from maxpane_dashboard.widgets.surf import nft as nft_mod
    from maxpane_dashboard.widgets.surf._fmt import DASH

    def check(pair, label):
        plain, markup = pair
        assert Content.from_markup(markup).plain == plain, (
            f"{label}: budget {plain!r} != render "
            f"{Content.from_markup(markup).plain!r}"
        )

    for dev in ("3", "1,234", DASH):
        check(nft_mod._dev_row(dev), f"_dev_row({dev!r})")
    for floor in (None, 0.25, 0.0, 1234.5):
        check(nft_mod._floor_row(floor), f"_floor_row({floor!r})")
    for sale in (
        {"ts": 1786163591, "token_id": 1751, "eth": 0.18},
        {"ts": None, "token_id": 10**40, "eth": 0.0},     # ??-?? and a long id
    ):
        check(nft_mod._sale_line(sale), f"_sale_line({sale!r})")

    fixed = {
        name: value
        for name, value in vars(nft_mod).items()
        if isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(half, str) for half in value)
    }
    assert len(fixed) >= 4, f"the sales block's fixed rows were not found: {fixed}"
    for name, pair in fixed.items():
        check(pair, name)


def test_nft_every_widen_hint_names_text_the_tier_actually_dropped():
    """A hint may only name a field that tier really loses.

    The trap this replaces was live for one commit's worth of drafting: the
    ladder shed ``dev holds`` and named it, then the rearrangement moved the
    dev holdings onto a row of their own -- leaving hints that pointed at a
    field the panel shows unconditionally, and no assertion anywhere that
    could notice.  So the hints are checked against the *difference* between
    the tier's row and the widest one, computed from the same builder the
    widget renders through, at a payload whose figures cannot be mistaken for
    each other.

    Also pins that every descriptive hint is *reachable*: it has to fit
    beside the title inside a panel no wider than the tier that triggers it,
    or it is a dead string permanently replaced by ``SHORT_HINT``.
    """
    from maxpane_dashboard.widgets.surf.nft import (
        PANEL_TITLE,
        SHORT_HINT,
        WIDEN_HINTS,
        _stats_variants,
    )

    variants = _stats_variants("667", "38", "1")
    widest = variants["full"]
    order = ("full", "compact", "minimal")

    for i, tier in enumerate(order):
        hint = WIDEN_HINTS[tier]
        if tier == "full":
            assert hint == "", "the widest tier sheds nothing and says nothing"
            continue
        assert hint.startswith(SHORT_HINT), hint
        # What this tier no longer renders, as literal text.
        dropped = widest
        for kept in variants[tier].split():
            dropped = dropped.replace(kept, " ", 1)
        named = [
            token.strip(",")
            for token in hint[len(SHORT_HINT) :].replace(":", " ").split()
            if token.strip(",") not in {"for"}          # connective, not a field
        ]
        assert named, f"{tier}: the hint names no field at all"
        for token in named:
            assert token in dropped, (
                f"{tier}: the hint names {token!r}, which is not in the text "
                f"this tier drops ({dropped.strip()!r})"
            )
            assert token not in variants[tier], (
                f"{tier}: the hint names {token!r}, which this tier still "
                f"renders ({variants[tier].strip()!r})"
            )

        # Reachable: the tier is active while the row above it does not fit,
        # i.e. at panel widths up to ``len(variants[order[i - 1]]) - 1``.
        ceiling = len(variants[order[i - 1]]) - 1
        assert len(PANEL_TITLE) + 2 + len(hint) <= ceiling, (
            f"{tier}: the {len(hint)}-column hint never fits beside "
            f"{PANEL_TITLE!r} in a panel of at most {ceiling} columns -- it is "
            "a dead string, always replaced by SHORT_HINT"
        )


async def test_nft_re_tiers_on_resize_and_the_title_tracks_the_tier():
    """The tier follows the terminal, in both directions, and says so.

    Without the resize hook the panel keeps whatever tier it was first laid
    out at: padded on a widened terminal, ellipsised on a narrowed one, for
    the life of the screen.

    The field that goes first is the written count, not the dev holdings it
    used to be -- the dev holdings have a row of their own now and are not
    the stats row's to trade.
    """
    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(60, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        screen = _screen_text(app)
        assert "1/2000 written" in screen
        assert "‹ widen" not in screen

        # Narrower than the whole stats row: the written count goes, said.
        await pilot.resize_terminal(40, 16)
        await pilot.pause()
        screen = _screen_text(app)
        assert "1/2000 written" not in screen
        assert "38 transfers/24h" in screen          # and the rest is whole
        assert "‹ widen for /2000 written" in screen
        # The dev holdings are *not* what a narrow stats row costs any more.
        assert "dev holds 3 identities" in screen

        # ...and widening puts it back, with the marker dark again.
        await pilot.resize_terminal(60, 16)
        await pilot.pause()
        screen = _screen_text(app)
        assert "1/2000 written" in screen
        assert "‹ widen" not in screen


async def test_nft_a_panel_too_narrow_to_name_what_it_shed_still_says_so():
    """``IDENTITY.MD`` plus the 25-column hint needs 38; 34 has to fall back.

    The bare marker names no field, but "something was dropped here" is the
    contract, and it costs seven columns.  The title has no ``text-overflow``,
    so an over-long hint would wrap the title onto a second line and push a
    sales row out of the panel instead of announcing anything.
    """
    from maxpane_dashboard.widgets.surf.nft import SHORT_HINT, WIDEN_HINTS

    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(36, 16)) as pilot:
        widget.update_data(**_FULL_NFT)
        await pilot.pause()
        screen = _screen_text(app)

        assert WIDEN_HINTS["compact"] not in screen, (
            "the descriptive hint fits after all at 36 columns -- re-measure"
        )
        assert SHORT_HINT in screen, "a field went with nothing said"
        # The fallback never costs the panel a row: the title is one line, so
        # the last sales block is still whole underneath it.
        assert "#1751" in screen and "#354" in screen


async def test_nft_a_row_the_tiers_cannot_help_is_still_advertised():
    """Only the stats row has fields to trade; the rest must still be honest.

    ``token_id`` comes out of a decoded ``OrderFulfilled`` log, so this widget
    does not get to assume a four-digit id -- and a token id is not a field it
    could shed anyway, since it is what identifies the sale.  When the row
    that overflows is one the ladder cannot shorten, the bare marker is the
    whole of what is left to say, and saying nothing is not an option.

    60 columns is deliberately wide enough for the stats row's *widest* tier,
    so this exercises the case the tier hints do not cover at all.
    """
    from maxpane_dashboard.widgets.surf.nft import SHORT_HINT

    widget = SurfNft()
    app = _Harness(widget)
    async with app.run_test(size=(60, 16)) as pilot:
        widget.update_data(
            **{
                **_FULL_NFT,
                "nft_last_sales": [
                    {"ts": 1786163591, "token_id": 10**40, "eth": 0.18},
                ],
            }
        )
        await pilot.pause()
        screen = _screen_text(app)

        # The written count is the first field the ladder sheds, so its
        # presence is what says "the stats row is at its widest tier here".
        # ``dev holds 3`` would not: that row is outside the ladder now and
        # shows at every width, so asserting it proves nothing about the tier.
        assert "1/2000 written" in screen, "the stats row fits at 60 -- re-measure"
        assert "…" in screen, "the over-long sale row was not cut after all"
        assert SHORT_HINT in screen, "a row was cut with nothing said"


# ---------------------------------------------------------------------
# Package surface
# ---------------------------------------------------------------------


def test_package_root_reexports_the_six_widget_classes():
    """``from maxpane_dashboard.widgets.surf import SurfHero`` must work.

    This is the house pattern (``widgets/ttt/__init__.py``,
    ``widgets/talismans/__init__.py``, and ``screens/fwa.py`` importing from
    ``maxpane_dashboard.widgets.fwa``), and it is the surface the screen WP
    imports from -- both ``screens/surf.py`` and its screen test spell
    ``from maxpane_dashboard.widgets.surf import (SurfDevActivity, SurfFeed,
    SurfHero, SurfMarket, SurfNft, SurfSignals)``.  A bare-docstring
    ``__init__.py`` turns both of those into ``ImportError``, and this file
    owns ``__init__.py``, so the guard belongs here.
    """
    import maxpane_dashboard.widgets.surf as pkg

    from maxpane_dashboard.widgets.surf import (
        DETECTOR_LABELS,
        FEED_TITLE,
        FLOOR_UNAVAILABLE,
        SurfDevActivity,
        SurfFeed,
        SurfHero,
        SurfMarket,
        SurfNft,
        SurfSignals,
    )

    classes = (SurfHero, SurfSignals, SurfFeed, SurfDevActivity, SurfMarket, SurfNft)
    for cls in classes:
        assert cls.__name__ in pkg.__all__, cls.__name__
        assert getattr(pkg, cls.__name__) is cls
    # The three rendered interface strings ride along, so consumers never
    # retype them (see the deliverable summary).
    assert DETECTOR_LABELS[0] == "NEW POST"
    assert FEED_TITLE == "ANNOUNCE FEED"
    assert FLOOR_UNAVAILABLE.startswith("n/a")
