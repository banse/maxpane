"""Headless Textual tests for the surf dashboard screen (WP5).

A fake manager returns the frozen ``SURF_KEYS`` dict (no network), the screen
is pushed via ``App.run_test()``, and we assert against **composited output**
(``_compositor.render_strips()``), never a widget's content string alone.

Zero network, zero wall clock: every time-derived string
(``feed_last_post_age_s``, signal ages) arrives pre-computed in the payload,
which is why the fetch instant 2026-08-08T04:00:00Z can be replayed forever.
All sample values are lifted from ``tests/fixtures/surf/captures/`` -- the real
payloads fetched 2026-08-08 -- not invented.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App

from maxpane_dashboard import __version__
from maxpane_dashboard.data.surf_models import SURF_KEYS
from maxpane_dashboard.screens.surf import SurfScreen
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf import (
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfMarket,
    SurfNft,
    SurfSignals,
)
# Imported, never re-spelled: the hook vocabulary is WP4's
# ``SurfManager._hook_status()`` ("LAUNCHED" / "NOT LIVE" / None), frozen in
# WP0's SURF_KEYS comment and PRD §4, and WP3's SurfHero branches on these two
# constants. A lowercase-snake literal here would drive the widget's unknown-
# value arm, so this file would certify a render nobody will ever see.
from maxpane_dashboard.widgets.surf.hero import HOOK_NOT_LIVE

_THEMES = Path(__file__).resolve().parents[2] / "maxpane_dashboard" / "themes"
_TCSS = _THEMES / "minimal.tcss"

_WIDGET_CLASSES = {
    "SurfHero": SurfHero,
    "SurfSignals": SurfSignals,
    "SurfFeed": SurfFeed,
    "SurfDevActivity": SurfDevActivity,
    "SurfMarket": SurfMarket,
    "SurfNft": SurfNft,
}

#: The WP3<->WP5 dispatch contract: exactly the PRD §5 key groups.  Local copy
#: until WP0 exports SURF_WIDGET_SIGNATURES beside SURF_KEYS (open issue) --
#: the mechanical dispatch test below still catches any drift against
#: SURF_KEYS.
SURF_WIDGET_SIGNATURES = {
    "SurfHero": (
        "hook_status", "lp_liquidity", "lp_imd", "lp_weth", "lp_owner_ok",
        "gate_open", "identities_written", "imd_supply", "imd_burned_cum",
    ),
    "SurfSignals": (
        "sig_post_state", "sig_post_detail", "sig_post_age_s",
        "sig_lp_state", "sig_lp_detail", "sig_lp_age_s",
        "sig_gate_state", "sig_gate_detail", "sig_gate_age_s",
        "sig_deploy_state", "sig_deploy_detail", "sig_deploy_age_s",
        "sig_bridge_state", "sig_bridge_detail", "sig_bridge_age_s",
        "sig_burn_state", "sig_burn_detail", "sig_burn_age_s",
    ),
    "SurfFeed": ("feed_items", "feed_nonce", "feed_last_post_age_s"),
    "SurfDevActivity": ("dev_activity",),
    "SurfMarket": (
        "imd_price_usd", "imd_change_24h_pct", "imd_vol_24h_usd",
        "pool_liquidity_usd", "fp_price_usd", "parity_pct",
        "supply_series", "price_series",
    ),
    "SurfNft": (
        "nft_holders", "nft_transfers_24h", "nft_dev_holdings",
        "nft_written", "nft_last_sales", "nft_floor",
    ),
}

#: Keys the screen itself consumes: ``as_of`` (freshness bookkeeping),
#: ``degraded`` (title bar), ``eth_usd`` (context; unrendered in v1).
META_KEYS = frozenset({"as_of", "degraded", "eth_usd"})

# -- fixed instants, all from tests/fixtures/surf/captures/ -------------
_TS_POST_13 = 1_786_076_831   # announce nonce 13, 2026-08-07T04:27:11Z
_TS_POST_12 = 1_785_903_575   # announce nonce 12, 2026-08-05T04:19:35Z
_TS_REPLY = 1_785_795_251     # pasta-sauce reply, 2026-08-03T22:14:11Z
_AS_OF = 1_786_161_600.0      # the fetch instant: 2026-08-08T04:00:00Z
_ANNOUNCE = "0x200E710aCAA6A93bbc77146026328C40F1d60fB1"
_REPLIER = "0x1c3A0Ad54418Fe843953C71dF23637DE732Ce159"
# Full 42-char addresses, never pre-shortened: WP3's ``long_addr`` returns any
# string of 17 characters or fewer unchanged, so a short-form fixture would
# make the poisoning defence a no-op in this file. Both are live in
# frenpet.eth's history today (ops_eth_txs.json) and are the two WP3 and WP4
# test against.
_REAL_UNKNOWN = "0x61CC704c7A5B7071c7B3f4Cc09A9CBC86373f14E"   # unlabelled LP-fee dest
_SPOOF = "0xF3083828702C1989710CECA517412071c2f60Ee6"          # 1-gwei lookalike


def _sample_data() -> dict:
    """A representative full payload, every value captures-derived."""
    return {
        # -- meta ---------------------------------------------------------
        "as_of": _AS_OF,
        "degraded": [],
        "eth_usd": 1919.2,          # 0.7074 / priceNative 0.0003686
        # -- feed ---------------------------------------------------------
        "feed_nonce": 14,           # eth_getTransactionCount(announce)
        "feed_last_post_age_s": _AS_OF - _TS_POST_13,   # 84769.0 -> "23h"
        "feed_items": [
            {
                "ts": _TS_POST_13,
                "kind": "self",
                "from_addr": _ANNOUNCE,
                "from_label": "announce",
                "text": (
                    "I moved 33 eth to the LP on mainnet "
                    "https://etherscan.io/tx/0x90a0f8e2b039e8d86d1b10e33e6"
                    "1e12d13728444e0a9e5ac258051cccb64d669. Hopefully in "
                    "the coming days will be able to share more what been "
                    "working on, as always 0 promises."
                ),
                "tx_hash": "0xe397869a2ed1299f24618c377112a6e9637395d2c1e2"
                           "1e742ce30e6201440055",
            },
            {
                "ts": _TS_POST_12,
                "kind": "self",
                "from_addr": _ANNOUNCE,
                "from_label": "announce",
                "text": "@RektSconey created this explorer of the NFTs "
                        "https://idmd-reader.pages.dev. Burned 15745 more "
                        "tokens from the LP fees, made huge progress today "
                        "on the system, will share more when have something "
                        "concrete.",
                "tx_hash": "0xeb2b8272330a0224df369373d177356ca321668f44d5"
                           "2e2e46f08645bcf36fc8",
            },
            {
                # the community reply, typographic apostrophe intact --
                # markup-hostile third-party text (PRD §6.4)
                "ts": _TS_REPLY,
                "kind": "reply",
                "from_addr": _REPLIER,
                "from_label": None,
                "text": "Bro cooked this so hard it smells like my "
                        "grandma’s pasta sauce after marinating "
                        "overnight. Absolute Michelin alpha.",
                "tx_hash": "0xdcb8bf92a26aac481939880c17087e66fc32b036eb84"
                           "3bd7f10fb302ade760c9",
            },
        ],
        # -- signals (states the product can emit: ok/watch/fired/None) ----
        #
        # Every detail string below is **WP2's output vocabulary**, copied
        # verbatim from the detector bodies and the ``MATRIX`` table in
        # wp2.md Tasks WP2.4-WP2.8 -- not paraphrased. ``build_signals``
        # cannot emit anything else, and this screen's composited assertions
        # (and the WP5.5 width measurement) are calibrated on these exact
        # widths. Re-copy them if a WP2 detector's detail changes.
        #
        # Two state/age pairings worth reading twice, both WP2 rules
        # (``FIRED_TTL_S = 86400``):
        #   * post + bridge are ``fired`` because their ages are under 24 h;
        #     a FIRED row keeps the *event's* detail verbatim.
        #   * burn is ``ok`` because its event is 2.99 d old, so WP2 relaxes
        #     it to the composed ``<live detail> · last: <event detail>``
        #     form while keeping the event's age.
        "sig_post_state": "fired",
        # WP2's LP_POST_DETAIL -- the "#N" form with straight quotes and a
        # 48-char body ellipsis, not a "nonce 13 -> 14" gloss.
        "sig_post_detail": '#14 "I moved 33 eth to the LP on mainnet https://eth…"',
        "sig_post_age_s": _AS_OF - _TS_POST_13,
        "sig_lp_state": "ok",
        "sig_lp_detail": "liquidity holds",
        "sig_lp_age_s": None,
        "sig_gate_state": "ok",
        # No "/2000": WP2 omits the denominator deliberately (the cap is a
        # documented number, and documented numbers are read live or not
        # shown -- CLAUDE.md rule 4). WP2's `test_no_live_value_is_hardcoded`
        # bans the literal 2000 from that module outright.
        "sig_gate_detail": "closed · 1 written",
        "sig_gate_age_s": None,
        "sig_deploy_state": "ok",
        "sig_deploy_detail": "no new contract",
        "sig_deploy_age_s": None,
        "sig_bridge_state": "fired",
        "sig_bridge_detail": "mint 114,367 IMD → frenpet.eth",
        "sig_bridge_age_s": _AS_OF - (_TS_POST_13 - 720.0),  # staged 12 min pre-add
        "sig_burn_state": "ok",
        "sig_burn_detail": "supply flat · last: burn 15,745 IMD",
        "sig_burn_age_s": _AS_OF - _TS_POST_12,   # 2.99 d -> relaxed past FIRED_TTL_S
        # -- hero -----------------------------------------------------------
        # ``hook_status`` is spelled the way the *producer* spells it: WP4's
        # ``SurfManager._hook_status()`` returns exactly "LAUNCHED" / "NOT
        # LIVE" / None, WP0's SURF_KEYS comment freezes it, and WP3's
        # SurfHero branches on HOOK_NOT_LIVE / HOOK_LAUNCHED. The constant is
        # imported rather than retyped so this fixture cannot drift back to
        # the lowercase-snake form, which canonicalises to "NOT_LIVE", misses
        # both branches and renders the widget's fallback arm ("NOT_LIVE" /
        # "unrecognized status") -- a render no live payload can produce.
        "hook_status": HOOK_NOT_LIVE,
        "lp_liquidity": 2_162_384_733_113_558_190,   # raw uint128, abbreviated by the widget
        "lp_imd": 388_421.0,
        "lp_weth": 142.7067,
        "lp_owner_ok": True,
        "gate_open": False,
        "identities_written": 1,
        "imd_supply": 2_376_731.868679,
        # The observed 2026-08-05 event, NOT the 58,848 all-time ledger of
        # PRD §1: ``imd_burned_cum`` is observation-scoped (WP4.5 --
        # ``SurfCache.observed_burn_total()`` accumulates over successive
        # supply readings; ``None`` before the first successful read, ``0.0``
        # once watched with nothing moved). WP3's SurfHero prints it as
        # ``burned {n:,.0f} observed``, so an all-time value here would make
        # the screen certify an all-time claim that copy exists to avoid.
        "imd_burned_cum": 15_745.0,
        # -- market ---------------------------------------------------------
        "imd_price_usd": 0.7074,
        "imd_change_24h_pct": 30.89,
        "imd_vol_24h_usd": 244_178.0,
        "pool_liquidity_usd": 548_701.21,
        "fp_price_usd": 0.7274,
        "parity_pct": -2.7495188834204012,   # (0.7074/0.7274 - 1) * 100
        "supply_series": [
            [_TS_POST_12 - 86_400, 2_392_476.868679],  # before the 15,745 burn
            [_TS_POST_12, 2_376_731.868679],           # the step down
            [int(_AS_OF), 2_376_731.868679],
        ],
        "price_series": [
            [int(_AS_OF) - (23 - i) * 3600, 0.5404 + i * 0.00726]
            for i in range(24)                          # +30.89% over 24h
        ],
        # -- nft ------------------------------------------------------------
        "nft_holders": 667,
        "nft_transfers_24h": 38,
        "nft_dev_holdings": 3,
        "nft_written": 1,
        "nft_last_sales": [
            {"ts": int(_AS_OF) - 7_200, "token_id": 1204, "eth": 0.219},
            {"ts": int(_AS_OF) - 26_000, "token_id": 421, "eth": 0.2},
        ],
        "nft_floor": None,   # always None in v1 -> "n/a -- no keyless source"
        # -- activity --------------------------------------------------------
        # Newest first, the order WP4's ``_activity_rows`` emits and the order
        # WP3's table renders without re-sorting.
        "dev_activity": [
            {
                # Unknown counterparty: the **full 42-char** address, which is
                # what WP4 emits (``_activity_rows`` writes the raw
                # ``counterparty`` string when there is no label;
                # ``test_an_unknown_counterparty_is_never_marked_known`` pins
                # exactly this one). A pre-shortened fixture would sail
                # through WP3's ``long_addr`` untouched -- it returns any
                # string of <=17 chars unchanged -- and the screen test would
                # bless the first-6/last-4 short form the anti-poisoning rule
                # exists to prevent. Renders dimmed as ``0x61CC704c…73f14E``.
                "ts": _TS_POST_13 - 60,
                "wallet_label": "surfsurf.eth",
                "kind": "transfer",
                "counterparty": _REAL_UNKNOWN,
                "counterparty_known": False,
                "value_eth": 0.31,
                "tx_hash": "0x" + "2b" * 32,
            },
            {
                # The live poisoning shape, end to end: a zero-value transfer
                # from an unknown lookalike. WP3's ``_row_markup`` drops the
                # (transfer, value 0, unknown) triple outright, so this row
                # must never reach a pixel -- asserted in WP5.4's
                # ``test_the_activity_view_defends_against_address_poisoning``.
                "ts": _TS_POST_13 - 120,
                "wallet_label": "frenpet.eth",
                "kind": "transfer",
                "counterparty": _SPOOF,
                "counterparty_known": False,
                "value_eth": 0.0,
                "tx_hash": "0x" + "3c" * 32,
            },
            {
                "ts": _TS_POST_13 - 300,
                "wallet_label": "frenpet.eth",
                "kind": "LP",
                "counterparty": "NFPM",
                "counterparty_known": True,
                "value_eth": 33.25,
                "tx_hash": "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9"
                           "e5ac258051cccb64d669",
            },
            {
                "ts": _TS_POST_13 - 900,
                "wallet_label": "surfsurf.eth",
                "kind": "bridge",
                "counterparty": "OFT endpoint",
                "counterparty_known": True,
                "value_eth": 0.0,
                "tx_hash": "0x" + "1a" * 32,
            },
        ],
    }


def _frozen_payload(**overrides) -> dict:
    """Exactly ``SURF_KEYS`` -- a key added upstream appears here as ``None``."""
    sample = _sample_data()
    payload = {key: sample.get(key) for key in SURF_KEYS}
    payload.update(overrides)
    return payload


def _all_none_payload() -> dict:
    """Every contract key present, every value ``None`` (full outage)."""
    return {key: None for key in SURF_KEYS}


class _FakeManager:
    """Stand-in for SurfManager that never touches the network.

    ``raises=True`` is a *defensive* double, not a model of an outage: the
    real ``SurfManager.fetch_and_compute`` never raises (WP4 guarantees the
    full ``SURF_KEYS`` dict with ``None`` values under every failure
    combination).  Use ``_all_none_payload()`` for an outage; ``raises=True``
    only to prove a mis-wired manager cannot take the screen down.
    """

    def __init__(self, payload: dict | None = None, raises: bool = False) -> None:
        self._payload = payload if payload is not None else _frozen_payload()
        self._raises = raises
        self._error_count = 3
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        if self._raises:
            raise RuntimeError("all three pools are down")
        return dict(self._payload)

    async def close(self) -> None:
        pass


class _Harness(App):
    """Push a single SurfScreen for testing (no app stylesheet)."""

    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


class _ThemedHarness(_Harness):
    """Same, but with the real ``minimal.tcss`` loaded.

    Valid before WP6 adds a surf block: loading the stylesheet without surf
    rules leaves ``SurfScreen.DEFAULT_CSS`` in charge, and keeps passing after
    WP6 restates it.
    """

    CSS_PATH = _TCSS


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see."""
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _plain(widget) -> str:
    visual = widget.visual
    return getattr(visual, "plain", str(visual))


# -- contract sanity -----------------------------------------------------


def test_surf_keys_covers_the_local_signature_map():
    """Every dispatched kwarg is a contract key, and the map + META is total.

    This is the tripwire for WP0<->WP5 drift (the contract vs. this screen's
    dispatch map) while SURF_WIDGET_SIGNATURES lives locally: a key added to
    SURF_KEYS that no widget receives, or a kwarg here that left the contract,
    both fail loudly.
    """
    dispatched = {k for sig in SURF_WIDGET_SIGNATURES.values() for k in sig}
    assert dispatched <= set(SURF_KEYS), (
        f"dispatch kwargs not in SURF_KEYS: {sorted(dispatched - set(SURF_KEYS))}"
    )
    unconsumed = set(SURF_KEYS) - dispatched - META_KEYS
    assert not unconsumed, f"contract keys reach no widget: {sorted(unconsumed)}"


def test_bindings_are_refresh_and_the_view_toggle():
    """``c`` swaps the announce feed and the dev-activity table in one slot."""
    keys = {binding.key for binding in SurfScreen.BINDINGS}
    assert keys == {"r", "c"}


# -- mount ---------------------------------------------------------------


async def test_screen_mounts_all_six_widgets():
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()

        for cls in _WIDGET_CLASSES.values():
            screen.query_one(cls)
        # Slot grid: hero row holds two widgets, middle row the swap pair
        # plus the market, bottom row the NFT panel alone.
        assert len(screen.query_one("#hero-row").children) == 2
        assert len(screen.query_one("#middle-row").children) == 3
        assert len(screen.query_one("#bottom-row").children) == 1
        # The dev-activity view starts hidden; the feed starts showing.
        assert screen.query_one(SurfFeed).display is True
        assert screen.query_one(SurfDevActivity).display is False
        # WP5.3 wires ``_title_line`` into ``_do_refresh``, and RefreshGuard
        # fires that refresh on screen resume, so by the time ``pilot.pause()``
        # returns the placeholder ``INITIAL_TITLE`` has already been replaced
        # by the fetched payload's title -- this is no longer the pre-refresh
        # state the old assertion checked. Asserted against **composited
        # output**, not the widget's content string (house rule): a title
        # that never reaches the compositor would still pass a ``_plain()``
        # check while being invisible to a real user.
        assert "SURF · IMD $0.71 · parity -2.7% · feed #14 (23h)" in _screen_text(app)


# -- title line (pure) ---------------------------------------------------

from maxpane_dashboard.screens import surf as surf_mod


def test_title_line_composes_the_mandated_format():
    line = surf_mod._title_line(_frozen_payload())
    # PRD §4: SURF · IMD $x.xx · parity ±x.x% · feed #N (age) + flags + version
    assert line.startswith("SURF · IMD $0.71 · parity -2.7% · feed #14 (23h)")
    assert line.endswith(f"v{__version__}")
    assert "degraded" not in line          # nothing degraded in the sample


def test_title_line_all_none_shows_emdashes_never_zeros():
    line = surf_mod._title_line(_all_none_payload())
    assert "IMD —" in line
    assert "parity —" in line
    assert "feed #— (—)" in line
    assert "$0.00" not in line and "0.0%" not in line   # None is never 0-coerced


def test_title_line_renders_degraded_and_lp_owner_warning():
    line = surf_mod._title_line(
        _frozen_payload(degraded=["logs", "market"], lp_owner_ok=False)
    )
    assert "· degraded: logs, market" in line
    assert "⚠ LP owner changed" in line    # position #1167726 left frenpet.eth


def test_fmt_age_tiers():
    assert surf_mod._fmt_age(None) == "—"
    assert surf_mod._fmt_age(42.0) == "42s"
    assert surf_mod._fmt_age(84_769.0) == "23h"     # the sample's real age
    assert surf_mod._fmt_age(5_400.0) == "90m"      # 90 min is the m/h boundary
    assert surf_mod._fmt_age(3 * 86_400.0) == "3d"  # 36 h is the h/d boundary
    assert surf_mod._fmt_age(-5.0) == "—"           # a negative age is nonsense


# -- degraded formatting (pure) -- review round 1 -----------------------
#
# _fmt_degraded's job is to make anything short of "nothing is degraded"
# ((None)/[]) visibly wrong. A bare ``except TypeError: return ""`` used to
# turn a malformed ``degraded`` value into the *healthy* line -- the exact
# failure this project exists to prevent, on the most prominent line of the
# screen.


def test_fmt_degraded_healthy_inputs_render_empty():
    assert surf_mod._fmt_degraded(None) == ""
    assert surf_mod._fmt_degraded([]) == ""


def test_fmt_degraded_bare_string_is_one_group_not_characters():
    # A string is iterable character-by-character; treat it as a single
    # group name instead of exploding "logs" into "l, o, g, s".
    assert surf_mod._fmt_degraded("logs") == " · degraded: logs"


def test_fmt_degraded_list_with_a_non_string_element_still_renders():
    assert surf_mod._fmt_degraded(["logs", 42]) == " · degraded: logs, 42"


def test_fmt_degraded_unexpected_shapes_never_render_the_healthy_line():
    # None of these mean "nothing is degraded" -- an int cannot be iterated
    # and a dict is not a list of names -- so none may collapse to "", which
    # the title line renders identically to a genuinely healthy state.
    assert surf_mod._fmt_degraded(42) != ""
    assert surf_mod._fmt_degraded({"logs": True}) != ""
    assert "degraded" in surf_mod._fmt_degraded(42)
    assert "degraded" in surf_mod._fmt_degraded({"logs": True})


def test_title_line_with_a_malformed_degraded_value_never_reads_healthy():
    healthy = surf_mod._title_line(_frozen_payload(degraded=[]))
    for bad in (42, {"logs": True}, ["logs", 42]):
        line = surf_mod._title_line(_frozen_payload(degraded=bad))
        assert line != healthy
        assert "degraded" in line


# -- refresh dispatch ----------------------------------------------------


def _record_dispatches(screen) -> dict[str, list[dict]]:
    """Wrap every widget's ``update_data`` so we can see what it was handed."""
    calls: dict[str, list[dict]] = {name: [] for name in _WIDGET_CLASSES}

    def _wrap(name: str, original):
        def recorder(**kwargs):
            calls[name].append(kwargs)
            return original(**kwargs)

        return recorder

    for name, cls in _WIDGET_CLASSES.items():
        widget = screen.query_one(cls)
        widget.update_data = _wrap(name, widget.update_data)

    return calls


async def test_screen_dispatches_every_data_key():
    """Every ``SURF_KEYS`` group reaches the widget that owns it."""
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()
        assert manager.calls >= 1

        dispatched: set[str] = set()
        for name, signature in SURF_WIDGET_SIGNATURES.items():
            assert calls[name], f"{name}.update_data was never called"
            kwargs = calls[name][-1]
            assert set(kwargs) == set(signature), (
                f"{name} got {sorted(set(kwargs) ^ set(signature))} "
                "off-contract"
            )
            dispatched |= set(kwargs)

        # Nothing in the contract goes unrendered: it is either a widget
        # kwarg or a meta key the screen itself consumes.
        unconsumed = set(SURF_KEYS) - dispatched - META_KEYS
        assert not unconsumed, f"contract keys reach no widget: {sorted(unconsumed)}"


async def test_refresh_renders_title_and_all_panels():
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        title = _plain(screen.query_one("#title-bar"))
        assert "SURF · IMD $0.71 · parity -2.7% · feed #14 (23h)" in title

        text = _screen_text(app)
        # Panel titles (the WP3 widget-interface strings).
        assert "SIGNALS" in text
        assert "ANNOUNCE FEED" in text
        assert "MARKET" in text
        assert "IDMD NFT" in text
        # The hook vocabulary the manager actually emits reaches the hero in
        # words. ``NOT_LIVE`` (underscore) is WP3's *fallback* headline for an
        # unrecognised value, so asserting its absence is the tripwire against
        # this fixture drifting back to the lowercase-snake spelling — both
        # forms are 8 characters, so both survive the hero box's
        # ``text-overflow: ellipsis`` here and the two stay separable.
        assert "NOT LIVE" in text
        assert "NOT_LIVE" not in text
        # The observed burn reached the hero, and PRD §1's all-time ledger is
        # nowhere on screen — the manager cannot produce it. Only the prefix is
        # asserted: at 150 columns a hero box has 14 content columns
        # (150·3/5 = 90, −2 screen padding = 88, ÷4 boxes = 22, −2 margin
        # −2 border −4 padding), so WP3.2's full ``burned 15,745 observed``
        # copy is ellipsised. The exact string is WP3's to pin at box width.
        assert "burned 15,7" in text
        assert "58,848" not in text
        # The clipping trap: all six detector rows reach the compositor.
        # SurfSignals is six rows + title inside #hero-row's fixed height —
        # if a theme or CSS change costs it a row, BURN (the last) goes first.
        for label in ("NEW POST", "LP MIGRATION", "GATE OPEN",
                      "NEW DEPLOY", "BRIDGE STAGE", "BURN"):
            assert label in text, f"detector row {label!r} clipped or missing"
        # The floor is explicitly unavailable, never faked (PRD §4).
        assert "no keyless source" in text


async def test_screen_survives_manager_exception():
    """Belt and braces: the screen stands; only the StatusBar is marked.

    This is **not** the specified outage path — WP4's manager never raises,
    it returns all-``None`` (see ``test_screen_survives_all_none_payload``,
    which is the real-outage test).  A raising manager models a mis-wired or
    non-manager object, i.e. a programming error, and this test exists so
    that error degrades instead of killing the app.
    """
    manager = _FakeManager(raises=True)
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        status = screen.query_one(StatusBar).query_one("#status-left")
        rendered = _plain(status)
        assert "updated 999s ago" in rendered
        assert "3 errors" in rendered   # manager's _error_count is surfaced

        # The title bar was not half-overwritten with a broken frame.
        assert "Mission Control" in _plain(screen.query_one("#title-bar"))
        # Every widget is still mounted and rendering.
        text = _screen_text(app)
        assert "SIGNALS" in text
        assert "IDMD NFT" in text


async def test_screen_survives_all_none_payload():
    """A full outage renders explicit unavailable states, never zeros."""
    manager = _FakeManager(payload=_all_none_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()   # must not raise
        await pilot.pause()

        title = _plain(screen.query_one("#title-bar"))
        assert "SURF · IMD — · parity — · feed #— (—)" in title
        text = _screen_text(app)
        assert "$0.00" not in text     # a None price is never a zero price
        assert "no keyless source" in text


async def test_degraded_sources_reach_the_title_bar():
    manager = _FakeManager(
        payload=_frozen_payload(degraded=["logs", "market"], lp_owner_ok=False)
    )
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        text = _screen_text(app)
        assert "degraded: logs, market" in text
        assert "LP owner changed" in text


# -- the feed / activity toggle -----------------------------------------


async def test_c_swaps_the_feed_and_the_activity_table():
    """One slot, two views, mutually exclusive at every step."""
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        assert "ANNOUNCE FEED" in text and "DEV ACTIVITY" not in text
        assert screen._active_view == "feed"

        await pilot.press("c")
        await pilot.pause()
        text = _screen_text(app)
        assert "DEV ACTIVITY" in text and "ANNOUNCE FEED" not in text
        assert screen._active_view == "activity"

        await pilot.press("c")
        await pilot.pause()
        text = _screen_text(app)
        assert "ANNOUNCE FEED" in text and "DEV ACTIVITY" not in text
        assert screen._active_view == "feed"


async def test_the_market_and_nft_panels_are_unaffected_by_the_toggle():
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        for _ in range(3):
            text = _screen_text(app)
            assert "MARKET" in text
            assert "IDMD NFT" in text
            await pilot.press("c")
            await pilot.pause()


async def test_the_hidden_view_still_receives_updates():
    """Both widgets stay mounted and dispatched to, whichever is showing.

    Creating the activity table on demand would leave it empty for a beat
    after the first toggle, which reads as a bug. This asserts it has
    content *before* it is ever shown.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        calls = _record_dispatches(screen)
        await screen._do_refresh()
        await pilot.pause()

        assert calls["SurfDevActivity"], "the hidden activity table was never updated"
        assert calls["SurfFeed"]

        # and it renders immediately on the very first toggle
        await pilot.press("c")
        await pilot.pause()
        assert "DEV ACTIVITY" in _screen_text(app)


async def test_the_activity_view_defends_against_address_poisoning():
    """The anti-poisoning form survives all the way to the compositor.

    Two live shapes from frenpet.eth's history are in the payload: an
    unlabelled but genuine LP-fee destination, and a 1-gwei lookalike that
    collides with a real fee recipient on first-6/last-4. WP3 renders unknown
    counterparties as ``0x`` + first 8 + ``…`` + last 6 and drops the
    (transfer, zero value, unknown) triple outright -- this asserts both
    through the real screen rather than trusting the widget's own unit test,
    because a short-form *fixture* would make either defence a silent no-op.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        await pilot.press("c")          # the activity table owns the slot
        await pilot.pause()

        text = _screen_text(app)
        assert "DEV ACTIVITY" in text
        # The genuine unknown renders in the wide, poisoning-resistant window…
        assert "0x61CC704c…73f14E" in text
        # …and never in the classic short form the lookalike collides with.
        assert "0x61CC…f14E" not in text
        # The dust row reaches no pixel at all -- not the address, not the tail.
        assert "F3083828" not in text
        assert "f60Ee6" not in text


async def test_the_toggle_survives_a_missing_widget():
    """A toggle must never take the screen down (it runs outside the
    refresh path's per-widget try/except)."""
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        screen.query_one(SurfFeed).remove()
        await pilot.pause()

        screen.action_toggle_view()  # must not raise
        await pilot.pause()

        assert screen._active_view == "activity"


async def test_the_status_bar_names_the_active_view():
    """Same affordance FWA, Talismans and TTT use, so `c` is discoverable."""
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        seen = []
        bar = screen.query_one(StatusBar)
        original = bar.set_active_view
        bar.set_active_view = lambda v: (seen.append(v), original(v))[1]

        screen.action_toggle_view()
        await pilot.pause()

        assert seen == ["activity"]


async def test_both_views_get_the_identical_slot():
    """The toggle must not resize the panel underneath it.

    Both views carry ``width: 3fr`` against SurfMarket's ``2fr``; give either
    a different width and the layout jumps on every ``c`` press. Measured
    under the real stylesheet rather than trusting the numbers to stay equal
    (and it keeps holding after WP6 restates the block in minimal.tcss).
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(200, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        feed_size = screen.query_one(SurfFeed).size

        await pilot.press("c")
        await pilot.pause()
        act_size = screen.query_one(SurfDevActivity).size

        assert (act_size.width, act_size.height) == (feed_size.width, feed_size.height), (
            f"activity occupies {act_size} where the feed occupied "
            f"{feed_size} -- the panel resizes on every toggle"
        )
        assert act_size.height > 1, "the activity table collapsed instead of filling the row"


# -- the pinned full-layout width ---------------------------------------

from maxpane_dashboard.screens.surf import SURF_FULL_LAYOUT_COLUMNS


def _representative_feed_items() -> list[dict]:
    """The captured feed items minus the one carrying an unbreakable token.

    The nonce-13 post's tx-link (a URL glued to a 66-char hex hash by the
    raw text's own punctuation, no space) is 91 columns wide and cannot be
    wrapped -- ``SurfFeed`` correctly truncates it and lights its own
    ``‹ widen`` no matter how wide the panel gets, because the *next* real
    post linking a transaction will do the same thing again. That belongs to
    a fixture that documents it as permanent
    (``test_a_linked_post_advertises_widen_at_full_layout_width_forever``
    below), not to the fixture the full-layout width is measured against --
    a fixture containing an inherently-unbreakable token has no finite width
    that clears it, so it cannot be what "full layout" is measured from.
    This is the same real captures (nonce 12's short link, the reply) minus
    that one post, nothing invented.
    """
    return [
        item
        for item in _sample_data()["feed_items"]
        if item["ts"] != _TS_POST_13
    ]


def _widen_sweep_payload() -> dict:
    """The payload the full-layout-width measurement sweeps against."""
    return _frozen_payload(feed_items=_representative_feed_items())


async def _widen_markers(
    width: int, view: str = "feed", payload: dict | None = None
) -> int:
    """Composited ``‹ widen`` count at *width*, in the requested ``c`` view.

    Defaults to the representative (no-unbreakable-token) payload; pass
    ``payload=`` to measure against something else, e.g. the full sample
    with the tx-linked post.
    """
    manager = _FakeManager(
        payload=payload if payload is not None else _widen_sweep_payload()
    )
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        if view == "activity":
            await pilot.press("c")
            await pilot.pause()
        return _screen_text(app).count("‹ widen")


async def test_the_pinned_width_clears_every_widen_marker():
    """At ``SURF_FULL_LAYOUT_COLUMNS``, both views are marker-free for
    representative content. (A tx-linked post is a separate, permanent
    case -- see ``test_a_linked_post_advertises_widen_at_full_layout_width_forever``.)
    """
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS, "feed") == 0
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS, "activity") == 0


async def test_the_pinned_width_is_tight_not_padded():
    """Four columns narrower, at least one widget advertises the loss."""
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS - 4, "feed") > 0 or (
        await _widen_markers(SURF_FULL_LAYOUT_COLUMNS - 4, "activity") > 0
    ), "the documented width is higher than it needs to be"


async def test_a_narrow_tier_advertises_rather_than_truncating_silently():
    """Well below the threshold every drop is announced, never silent."""
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS - 20, "feed") > 0


async def test_a_linked_post_advertises_widen_at_full_layout_width_forever():
    """A tx-linked post's ``‹ widen`` at the full-layout width is correct,
    not a bug -- do not "fix" this by raising ``SURF_FULL_LAYOUT_COLUMNS``.

    The nonce-13 capture's tx-link token (a URL glued to a 66-char hex hash
    by the post's own punctuation) is 91 columns and cannot be wrapped. No
    finite pinned width clears it: the same shape recurs on any post that
    links a transaction, and ``SurfFeed`` will correctly re-advertise at 194
    columns, 594, or any width smaller than the token. The house rule is
    "never clip silently" -- this is that rule working, at exactly the width
    this repo has chosen to call "full layout".
    """
    assert (
        await _widen_markers(
            SURF_FULL_LAYOUT_COLUMNS, "feed", payload=_frozen_payload()
        )
        > 0
    )


def test_surf_fits_inside_the_documented_app_width():
    """WP6 coordination tripwire — mechanical, not a comment.

    ``__main__.FULL_LAYOUT_COLUMNS`` (owned by WP6/one owner) documents the
    width the *widest* dashboard needs. If surf measures wider than it, the
    app-level constant and its help text become lies; this failure message is
    the hand-off.
    """
    from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS

    assert SURF_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS, (
        f"surf needs {SURF_FULL_LAYOUT_COLUMNS} columns but "
        f"__main__.FULL_LAYOUT_COLUMNS documents {FULL_LAYOUT_COLUMNS}. "
        "Do NOT edit __main__.py from WP5 — report to WP6, which owns it, "
        "and land this test together with WP6's raise."
    )
