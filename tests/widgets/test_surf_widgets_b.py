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
        "kind": "LP",
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
