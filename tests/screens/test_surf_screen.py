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
from maxpane_dashboard.screens.surf import INITIAL_TITLE, TALLER_HINT, SurfScreen
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
        #
        # ``wallet_label`` is ``"dev"``/``"ops"`` -- the *producer's* whole
        # vocabulary (``surf_client._DEV_WALLET_LABELS``, passed through by
        # ``surf_manager._activity_rows``), pinned against it by
        # ``test_the_activity_fixture_speaks_the_producers_wallet_vocabulary``.
        # It read ``"surfsurf.eth"``/``"frenpet.eth"`` until 2026-08-10, which
        # the pipeline never emits: those are the ``KNOWN_LABELS`` spellings
        # and they reach the user through the hero's ``owner ✓`` line instead.
        # Two things hid it. The activity cell was 12 columns wide, exactly
        # enough for ``surfsurf.eth``, so nothing looked wrong; and the
        # manager's defence-in-depth sender re-check keys on ``DEV_WALLETS``,
        # whose keys are ``dev``/``ops``, so an ENS-spelled label matched no
        # entry and skipped the check entirely. Narrowing the cell to the real
        # vocabulary rendered ``sur``/``fre`` and exposed both.
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
                "wallet_label": "dev",
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
                "wallet_label": "ops",
                "kind": "transfer",
                "counterparty": _SPOOF,
                "counterparty_known": False,
                "value_eth": 0.0,
                "tx_hash": "0x" + "3c" * 32,
            },
            {
                "ts": _TS_POST_13 - 300,
                "wallet_label": "ops",
                "kind": "lp",
                "counterparty": "NFPM",
                "counterparty_known": True,
                "value_eth": 33.25,
                "tx_hash": "0x90a0f8e2b039e8d86d1b10e33e61e12d13728444e0a9"
                           "e5ac258051cccb64d669",
            },
            {
                "ts": _TS_POST_13 - 900,
                "wallet_label": "dev",
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


def test_refresh_is_the_only_binding():
    """``c`` is gone: nothing is hidden, so nothing can be swapped in.

    The key existed only because the announce feed and the dev-activity panel
    shared one slot. Both are permanently on screen since the three-row
    restructure, so a swap key would toggle two panels that are both already
    visible -- and the status bar would advertise a "view" that is not a view.
    """
    keys = {binding.key for binding in SurfScreen.BINDINGS}
    assert keys == {"r"}
    assert not hasattr(SurfScreen, "action_toggle_view"), (
        "the swap action outlived its binding -- an action with no key is a "
        "surface nobody can reach and nobody maintains"
    )


def test_the_initial_title_names_the_dashboard_the_menu_names():
    """The title bar is the only place the name is read *inside* the app.

    Derived from ``GAMES``, never a second literal: the menu row and the
    screen's own title must not be able to drift apart again. They did --
    the rename reached the menu, the README and CLAUDE.md and stopped at
    ``INITIAL_TITLE``, so pressing the menu key opened a screen still
    titled with the old name for the whole first fetch, and permanently on
    the degraded path (``_title_line`` is what replaces it, and a manager
    that raises never reaches it).
    """
    from maxpane_dashboard.screens.game_select import GAMES

    name = next(row[2] for row in GAMES if row[1] == "surf")
    assert name in INITIAL_TITLE, (
        f"the menu calls this dashboard {name!r}; its own title bar says "
        f"{INITIAL_TITLE!r}"
    )


# -- mount ---------------------------------------------------------------


async def test_screen_mounts_all_six_widgets():
    manager = _FakeManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()

        for cls in _WIDGET_CLASSES.values():
            screen.query_one(cls)
        # Slot grid: the hero owns the top row alone; the middle row is the
        # feed beside a rail of SIGNALS over DEV ACTIVITY; the bottom row is
        # the market beside the NFT panel.
        assert len(screen.query_one("#hero-row").children) == 1
        assert len(screen.query_one("#middle-row").children) == 2
        assert len(screen.query_one("#surf-right-rail").children) == 2
        assert len(screen.query_one("#bottom-row").children) == 2
        # Nothing is hidden -- that is the whole point of the three-row grid.
        for cls in _WIDGET_CLASSES.values():
            assert screen.query_one(cls).display is True, f"{cls.__name__} is hidden"
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
        assert "IDENTITY.MD" in text
        # The hook vocabulary the manager actually emits reaches the hero in
        # words. ``NOT_LIVE`` (underscore) is WP3's *fallback* headline for an
        # unrecognised value, so asserting its absence is the tripwire against
        # this fixture drifting back to the lowercase-snake spelling — both
        # forms are 8 characters, so both survive the hero box's
        # ``text-overflow: ellipsis`` here and the two stay separable.
        assert "NOT LIVE" in text
        assert "NOT_LIVE" not in text
        # The observed burn reached the hero, and PRD §1's all-time ledger is
        # nowhere on screen — the manager cannot produce it. At 150 columns a
        # hero box has ~15 content columns (150·3/5 = 90, −2 screen padding
        # = 88, ÷4 boxes = 22, −2 margin −2 border −4 padding), which selects
        # the hero's ``minimal`` tier: the copy is the short ``burn 15,745``,
        # and the quantity is *whole*. This used to assert the prefix
        # ``"burned 15,7"`` because the full copy was ellipsised here to
        # ``burned 15,74…`` — a number cut mid-digits, with nothing marking
        # the cut. That was final-review I-2; the shed field replaced it.
        assert "burn 15,745" in text
        assert "burned 15,74…" not in text
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

        # The title bar was not half-overwritten with a broken frame -- and
        # it still names the dashboard the menu names. This is the *only*
        # path on which ``INITIAL_TITLE`` is what the user reads for good
        # (``_title_line`` never runs), so the name has to be right here.
        # Composited, not the content string: the title bar is centred and
        # one row high, and a name that never reaches a pixel is not a name.
        text = _screen_text(app)
        assert INITIAL_TITLE in text.split("\n")[0]
        assert "Mission Control" not in text
        # Every widget is still mounted and rendering.
        assert "SIGNALS" in text
        assert "IDENTITY.MD" in text


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


# -- everything on screen at once ---------------------------------------
#
# The `c` swap is gone with the slot it swapped. These are what replaced its
# three tests: the panels it used to alternate between are now both permanently
# composited, side by side with the rail, and no key can take either away.


async def test_the_feed_and_the_activity_panel_are_both_on_screen_at_once():
    """The instruction, stated as an assertion: nothing is hidden.

    Composited, not `display`: a panel mounted at zero height satisfies a
    visibility flag while showing the user nothing.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        for title in ("ANNOUNCE FEED", "SIGNALS", "DEV ACTIVITY",
                      "IMD MARKET", "IDENTITY.MD", "V4 HOOK"):
            assert title in text, f"{title} is not on screen"


async def test_no_key_can_hide_a_panel():
    """`c` was the only key that could, and it is gone.

    Pressing it now must be inert -- not "swap something else", not crash.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        before = _screen_text(app)

        await pilot.press("c")
        await pilot.pause()

        assert _screen_text(app) == before, "`c` still changes the screen"
        assert "DEV ACTIVITY" in before and "ANNOUNCE FEED" in before


async def test_the_status_bar_never_advertises_a_view():
    """No slot has two views any more, so `view: …` would name nothing.

    Asserted on the composited status bar, because the string is built inside
    ``StatusBar._update_right`` -- a screen that kept calling
    ``set_active_view`` would put a stale word on a bar this dashboard shares
    with nine others.
    """
    screen = SurfScreen(_FakeManager(), poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()

        text = _screen_text(app)
        assert "view:" not in text
        assert "surf" in text.split("\n")[-1]   # the bar is otherwise intact


async def test_the_activity_panel_defends_against_address_poisoning():
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

        text = _screen_text(app)
        assert "DEV ACTIVITY" in text
        # The genuine unknown renders in the wide, poisoning-resistant window…
        assert "0x61CC704c…73f14E" in text
        # …and never in the classic short form the lookalike collides with.
        assert "0x61CC…f14E" not in text
        # The dust row reaches no pixel at all -- not the address, not the tail.
        assert "F3083828" not in text
        assert "f60Ee6" not in text


# -- the three-row layout -----------------------------------------------
#
# The hero spans the full width on a row of its own; the middle row is the
# announce feed beside a rail stacking SIGNALS over DEV ACTIVITY; the bottom
# row is IMD MARKET beside IDENTITY.MD, on the same column seam as the row
# above it. Every assertion below is geometric or composited -- the
# arrangement is what the user asked for, so "the widget is mounted" is not
# enough: it has to land where they put it.

#: The rail id, spelled once. Scoped to ``SurfScreen`` in both stylesheets.
_RAIL = "#surf-right-rail"


class _screen_at:
    """``async with _screen_at(w, h) as (app, screen, pilot):`` -- refreshed."""

    def __init__(self, width: int = 150, height: int = 46, payload=None) -> None:
        self._size = (width, height)
        self._payload = payload
        self._ctx = None

    async def __aenter__(self):
        manager = _FakeManager(
            payload=self._payload if self._payload is not None
            else _widen_sweep_payload()
        )
        self._screen = SurfScreen(manager, poll_interval=30, name="surf")
        self._app = _ThemedHarness(self._screen)
        self._ctx = self._app.run_test(size=self._size)
        pilot = await self._ctx.__aenter__()
        await pilot.pause()
        await self._screen._do_refresh()
        await pilot.pause()
        return self._app, self._screen, pilot

    async def __aexit__(self, *exc):
        return await self._ctx.__aexit__(*exc)


async def test_the_hero_owns_a_full_width_row_of_its_own():
    """The hero is the whole top row -- nothing shares it."""
    async with _screen_at(150, 46) as (app, screen, _pilot):
        hero_row = screen.query_one("#hero-row")
        hero = screen.query_one(SurfHero)

        assert len(hero_row.children) == 1, (
            "something else is still sharing the hero row: "
            f"{[type(c).__name__ for c in hero_row.children]}"
        )
        assert hero.region.width == hero_row.region.width == 150
        # All four boxes are laid out inside that full width, in order.
        xs = [box.region.x for box in hero.children]
        assert len(xs) == 4 and xs == sorted(xs)
        assert xs[-1] + hero.children[-1].region.width <= 150


async def test_the_right_rail_stacks_the_signals_above_the_dev_activity():
    """SIGNALS sits on top of DEV ACTIVITY, both in the middle row's rail."""
    async with _screen_at(150, 46) as (app, screen, _pilot):
        rail = screen.query_one(_RAIL)
        signals = screen.query_one(SurfSignals)
        activity = screen.query_one(SurfDevActivity)
        feed = screen.query_one(SurfFeed)

        assert [type(c).__name__ for c in rail.children] == [
            "SurfSignals", "SurfDevActivity",
        ]
        # Stacked, not side by side: same column, signals strictly above.
        assert signals.region.x == activity.region.x == rail.region.x
        assert signals.region.y + signals.region.height <= activity.region.y
        # ...and the whole rail is to the right of the feed, in one row.
        assert feed.region.x + feed.region.width <= rail.region.x
        assert feed.region.y == rail.region.y

        # Composited, not just geometric: both titles reach a pixel, in order.
        text = _screen_text(app)
        assert text.index("SIGNALS") < text.index("DEV ACTIVITY")


async def test_the_bottom_row_puts_the_market_left_of_the_nft_panel():
    """The third row, and it shares the middle row's column seam.

    The seam is the point: two rows split 3:2 read as one grid, and a market
    panel that started one column off from the feed above it would read as a
    mistake even though every panel was present.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        row = screen.query_one("#bottom-row")
        market = screen.query_one(SurfMarket)
        nft = screen.query_one(SurfNft)
        feed = screen.query_one(SurfFeed)
        rail = screen.query_one(_RAIL)

        assert [type(c).__name__ for c in row.children] == ["SurfMarket", "SurfNft"]
        # Side by side, market first, in one row, below the middle row.
        assert market.region.y == nft.region.y
        assert market.region.x + market.region.width <= nft.region.x
        assert row.region.y >= rail.region.y + rail.region.height
        # The seam: the market/NFT boundary is the feed/rail boundary.
        assert market.region.width == feed.region.width
        assert nft.region.x == rail.region.x

        text = _screen_text(app)
        assert text.index("IMD MARKET") < text.index("IDENTITY.MD")
        # ...and both are below the rail's two panels.
        assert text.index("DEV ACTIVITY") < text.index("IMD MARKET")


async def test_the_hero_row_is_no_taller_than_the_hero():
    """The dead space above the feed: the row used to reserve 10 rows for 7.

    Sized to its content instead. Composited, because the failure is *blank
    rows* -- a region height alone would not show them.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        hero_row = screen.query_one("#hero-row")
        hero = screen.query_one(SurfHero)
        assert hero_row.region.height == hero.region.height

        lines = _screen_text(app).split("\n")
        top, bottom = hero_row.region.y, hero_row.region.y + hero_row.region.height
        assert lines[bottom - 1].strip(), (
            "the hero row's last line is blank -- it is still taller than its content"
        )
        # The row directly under the hero belongs to the middle row's margin,
        # and there is exactly one of them.
        assert not lines[bottom].strip()
        assert lines[bottom + 1].strip(), "more than one blank row under the hero"
        assert top == 2


async def test_the_bottom_row_sizes_to_the_nft_panel_and_strands_no_rows():
    """The other half of the complaint: ~a fifth of the screen was empty.

    The NFT panel is the last thing on screen above the status bar, so any row
    the bottom row reserves beyond the panel's own content is dead. Asserted
    against composited output: the last non-blank row before the status bar
    must be the panel's last line, not eight rows above it.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        bottom = screen.query_one("#bottom-row")
        nft = screen.query_one(SurfNft)
        assert bottom.region.height == nft.region.height

        lines = _screen_text(app).split("\n")
        status_row = len(lines) - 1
        assert "q quit" in lines[status_row]
        last_content = max(i for i in range(status_row) if lines[i].strip())
        # One margin row between the panel and the status bar, no more.
        assert status_row - last_content <= 2, (
            f"{status_row - last_content - 1} dead rows above the status bar"
        )
        assert "0.200 ETH" in lines[last_content], (
            "the last NFT sale is not the last thing on screen"
        )


async def test_a_taller_terminal_hands_every_new_row_to_the_feed():
    """Slack goes to the feed, never back into the fixed rows.

    Fourteen more terminal rows must arrive as fourteen more feed rows -- if
    the hero or the NFT panel takes a share of them the dead space is back.
    """
    async with _screen_at(150, 46) as (_app, screen, _pilot):
        short = {
            "feed": screen.query_one(SurfFeed).region.height,
            "hero": screen.query_one(SurfHero).region.height,
            "nft": screen.query_one(SurfNft).region.height,
        }
    async with _screen_at(150, 60) as (_app, screen, _pilot):
        tall = {
            "feed": screen.query_one(SurfFeed).region.height,
            "hero": screen.query_one(SurfHero).region.height,
            "nft": screen.query_one(SurfNft).region.height,
        }

    assert tall["feed"] - short["feed"] == 14, (
        f"the feed absorbed {tall['feed'] - short['feed']} of 14 new rows"
    )
    assert tall["hero"] == short["hero"]
    assert tall["nft"] == short["nft"]


async def test_a_terminal_too_short_for_six_detectors_says_so():
    """Rows are the columns problem again: the loss must be advertised.

    Sizing every row to its content is what removed the dead space, and the
    price is that the rail is only as tall as the middle row -- where the old
    layout gave the signals a fixed ten-row band that survived down to a
    ~16-row terminal. Below 29 rows the sixth detector (BURN, always the
    first to go) no longer fits. ``overflow-y: auto`` on the rail is the
    row-wise ``‹ widen``: nothing is drawn while everything fits, and the
    scrollbar appears exactly when something is missing.

    Both halves are asserted, because a rail that scrolled *always* would
    satisfy the second one while being the permanently-lit marker this
    codebase keeps warning about.
    """
    async with _screen_at(150, 46) as (app, screen, _pilot):
        text = _screen_text(app)
        for label in ("NEW POST", "LP MIGRATION", "GATE OPEN",
                      "NEW DEPLOY", "BRIDGE STAGE", "BURN"):
            assert label in text, f"{label} is missing at a normal height"
        assert screen.query_one(_RAIL).show_vertical_scrollbar is False, (
            "the rail scrolls even when everything fits -- a marker that is "
            "always on says nothing"
        )

    async with _screen_at(150, 28) as (app, screen, _pilot):
        assert "BURN" not in _screen_text(app), (
            "28 rows fits all six detectors after all -- re-measure"
        )
        assert screen.query_one(_RAIL).show_vertical_scrollbar is True, (
            "a detector row was dropped with nothing on screen to say so"
        )


#: What the market panel exists to show, as composited fragments.  Matched
#: inside the panel's own rectangle and nowhere else: "parity" is also in the
#: title bar and "supply" in the hero, so a whole-screen match would keep
#: reading the market as present long after it had gone.
_MARKET_FIELDS = ("$0.7074", "vol 24h", "parity", "price ", "supply")

#: The six detectors, in the order the panel renders them; BURN is last and so
#: always the first to be scrolled off.
_DETECTORS = ("NEW POST", "LP MIGRATION", "GATE OPEN", "NEW DEPLOY",
              "BRIDGE STAGE", "BURN")

#: The activity rows the sweep payload produces, once the dust row is dropped.
#: Composited fragments, unique to that panel.
_ACTIVITY_ROWS = ("0x61CC704c…73f14E", "NFPM", "OFT endpoint")

#: The height at and above which the whole rail fits: ``SurfSignals`` is 8 rows
#: (title, spacer, six detectors) plus the one-row margin that separates it
#: from the activity panel, and ``SurfDevActivity`` is floored at
#: ``ACTIVITY_MIN_HEIGHT``, so the rail's content is a constant 16 and the
#: other rows of the screen cost a fixed 21. Measured, not derived -- the
#: arithmetic is here to explain the number, the sweep below is what pins it.
#:
#: **36 -> 37 on 2026-08-10**, the one row the rail separator costs. The
#: ``‹ taller`` marker therefore lights at 36 where it used to light at 35,
#: and the first genuinely-lost activity row moved 33 -> 34 with it: the
#: marker still leads the loss by exactly two rows, which is the property
#: that matters and which ``test_the_marker_lights_before_the_first_line_is_
#: actually_lost`` pins at both ends.
FIRST_WHOLE_HEIGHT = 37


def _visible_panel(app, widget, clip) -> str:
    """Composited text of *widget*'s rectangle, intersected with *clip*'s.

    Two things ``_region_text`` below does not do, both of which these sweeps
    need.  It assumes the whole region is on-screen, and at these heights a
    panel's region can start *below* the last composited row -- which is the
    failure being measured, so it has to clip rather than raise.  And a widget
    inside a scroll container keeps its full region even when the container
    paints only part of it, so without intersecting the container's rectangle
    this would read whatever is painted underneath and call it the panel.
    """
    lines = _screen_text(app).split("\n")
    region = widget.region.intersection(clip.region)
    return "\n".join(
        lines[y][region.x : region.x + region.width]
        for y in range(region.y, min(region.y + region.height, len(lines)))
    )


def _missing_at(app, screen) -> list[str]:
    """Everything the three-row layout promises that is not composited.

    Deliberately not "every row of every panel": the feed and the activity log
    are scrolling ``RichLog``s that legitimately show fewer posts on a shorter
    terminal, exactly as they do on a taller one with more posts. What is
    promised is the *fixed* content -- the six detectors, the market's five
    figures -- plus the activity panel's declared floor, which is what
    ``ACTIVITY_MIN_HEIGHT`` exists to make measurable.
    """
    text = _screen_text(app)
    market = _visible_panel(
        app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
    )
    missing = [d for d in _DETECTORS if d not in text]
    missing += [f"market {f}" for f in _MARKET_FIELDS if f not in market]
    if "DEV ACTIVITY" not in text:
        missing.append("DEV ACTIVITY")
    missing += [f"activity {r}" for r in _ACTIVITY_ROWS if r not in text]
    return missing


async def test_every_panel_is_whole_on_a_terminal_that_fits_them():
    """The positive half, at the height the rail first fits and well above it.

    Without this the sweep below is satisfied by a marker welded permanently
    to the title bar -- the failure mode this codebase keeps recording.
    """
    for height in (FIRST_WHOLE_HEIGHT, 46, 60):
        async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, height) as (app, screen, _p):
            assert _missing_at(app, screen) == [], (
                f"at {SURF_FULL_LAYOUT_COLUMNS}x{height} the layout is short of "
                f"{_missing_at(app, screen)}"
            )
            assert TALLER_HINT not in _screen_text(app), (
                f"the row marker is lit at {SURF_FULL_LAYOUT_COLUMNS}x{height}, "
                "where everything fits"
            )
            assert screen.query_one(_RAIL).show_vertical_scrollbar is False


async def test_no_height_drops_content_without_saying_so():
    """The row-wise half of the ``‹ widen`` contract, swept height by height.

    The contract is not "everything always fits" -- at 28 rows it cannot. It
    is that a height which costs the screen a promised line must light the row
    marker on the **title bar**: row 0, the one row a short terminal can never
    push off, unlike the panel titles themselves.

    The sweep runs to 16 rows because the failure it guards moved. In the
    two-row layout the market lived in the rail, shrank silently and was gone
    by 31; here it sits in an ``auto`` bottom row and survives to 20, below
    which the screen itself scrolls and the bottom row goes off the end. Both
    ends of that range have to stay advertised.
    """
    for height in range(40, 15, -1):
        async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, height) as (app, screen, _p):
            missing = _missing_at(app, screen)
            lit = TALLER_HINT in _screen_text(app).split("\n")[0]
            if missing:
                assert lit, (
                    f"at {SURF_FULL_LAYOUT_COLUMNS}x{height} the screen lost "
                    f"{missing} with nothing on screen to say so"
                )


async def test_the_marker_lights_before_the_first_line_is_actually_lost():
    """It leads the loss by two rows, and that is the floor doing its job.

    ``SurfDevActivity`` is ``1fr`` in a scroll container, so it shrinks rather
    than overflowing; ``min-height: ACTIVITY_MIN_HEIGHT`` is what converts
    "the rail is one row short" into an overflow the screen can see. The two
    rows of slack are the blank tail of that floor: at 36 and 35 the rail is
    genuinely painting less than it holds, and by 34 a real activity row has
    gone. A marker that lit at 34 instead would have let two heights of
    silent shrinkage through, which is precisely how the market disappeared
    from this rail before.

    Both numbers moved up one on 2026-08-10 (35/33 -> 36/34) when the rail
    gained its one-row separator. The *lead* is what this test is about, and
    it is unchanged -- which is the point: the separator cost a row of rail,
    not a row of warning.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, FIRST_WHOLE_HEIGHT - 1) as (
        app, screen, _p
    ):
        assert TALLER_HINT in _screen_text(app).split("\n")[0]
        assert screen.query_one(_RAIL).show_vertical_scrollbar is True
        assert _missing_at(app, screen) == [], (
            "the marker no longer leads the loss -- re-measure both numbers"
        )

    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, FIRST_WHOLE_HEIGHT - 3) as (
        app, screen, _p
    ):
        assert _missing_at(app, screen), (
            f"{FIRST_WHOLE_HEIGHT - 3} rows fits everything after all -- the "
            "marker leads the loss by more than two rows now"
        )


async def test_the_market_keeps_its_figures_far_below_the_rail():
    """143x30: the height at which the old layout showed a blank rail.

    Moving the market out of the scrolling rail and into the ``auto`` bottom
    row is what bought this: every figure is still composited ten rows below
    the height the rail stops fitting, and the panel is still its full seven
    rows rather than a title over nothing.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 30) as (app, screen, _p):
        panel = _visible_panel(
            app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
        )
        assert all(field in panel for field in _MARKET_FIELDS), (
            f"the market lost {[f for f in _MARKET_FIELDS if f not in panel]}"
        )
        assert screen.query_one(SurfMarket).region.height == 7
        # ...and the rail's own loss is still advertised, in words.
        assert TALLER_HINT in _screen_text(app).split("\n")[0]
        assert screen.query_one(_RAIL).show_vertical_scrollbar is True


async def test_the_market_panel_is_not_clipped_at_the_pinned_layout_width():
    """Nothing is cut here at the width the layout is measured at.

    Pairing the sparklines with their figures and adding the bridge block
    took the panel's widest row from ~33 rendered columns to 71, i.e. from
    "fits anything" to a panel that is clean only from a **140**-column
    terminal against the 142 this layout is measured at. Two columns of
    margin, on a row whose width moves with ``fmt_price``'s precision band --
    a sub-cent IMD renders ``$0.000200`` where today's $0.7074 renders
    ``$0.0200`` and costs two more.

    The panel grew its own tiers on 2026-08-11 (``widgets/surf/market.py``:
    five of them, measured off the rows it actually paints), so a narrower
    terminal now sheds a named field and says so rather than ellipsising in
    silence. That is the *narrow* half and it is pinned in the widget tests.
    This is the wide half, and it stays here because the two are different
    claims: a tiered panel that sheds a field it did not have to would pass
    every test over there and be wrong on every terminal anyone owns.
    """
    for width in (SURF_FULL_LAYOUT_COLUMNS, 143, 160):
        async with _screen_at(width, 46) as (app, screen, _p):
            panel = _visible_panel(
                app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
            )
            assert "…" not in panel, (
                f"at {width} columns the market is cut with nothing to say so:\n"
                f"{panel}"
            )
            # The bridge block is the part that is newly wide, and the two
            # ends of it are the two that must survive: what IMD is, and
            # that the spread is gross.
            assert "IMD is FP bridged 1:1 from Base" in panel
            assert "gross of fees" in panel
            # ...and it says so, too: a panel shedding a field it has room
            # for would satisfy every assertion above.
            assert "‹ widen" not in panel, (
                f"at {width} columns the market sheds a field it has room "
                f"for:\n{panel}"
            )


async def test_the_market_advertises_its_own_shedding_on_the_real_screen():
    """The narrow half, on the composited screen rather than in a harness.

    The widget tests drive ``SurfMarket`` in a bare harness where its content
    box is the whole app; here it is ``7fr`` of a 13-column seam inside a
    padded row, which is the geometry that actually decides how many columns
    it gets -- and the geometry a widget test cannot see. **139 is the first
    terminal width that costs the market a field** and it is three below the
    142 this screen clears at, so the two halves of the contract are pinned
    at both ends and one column apart:

    * at 140 the panel is whole and unmarked;
    * at 139 a field is gone, the marker names it, and no row is cut.

    Deliberately *not* derived from ``SURF_FULL_LAYOUT_COLUMNS``: the market
    is not the panel that sets that number (the announce feed is), so tying
    the two together would make this test pass through any regression that
    moved them in step.
    """
    market_first_full_terminal = 140
    assert market_first_full_terminal < MEASURED_FULL_LAYOUT_COLUMNS, (
        "the market is now the panel that sets the full-layout width -- "
        "re-measure it and correct every surface that names the feed"
    )

    async with _screen_at(market_first_full_terminal, 46) as (app, screen, _p):
        whole = _visible_panel(
            app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
        )
    assert "‹ widen" not in whole and "…" not in whole, whole
    assert "vol 24h" in whole and "gap narrows" in whole

    async with _screen_at(market_first_full_terminal - 1, 46) as (app, screen, _p):
        shed = _visible_panel(
            app, screen.query_one(SurfMarket), screen.query_one("#bottom-row")
        )
    assert "…" not in shed, f"a row is cut where a tier should have fitted:\n{shed}"
    assert "vol 24h" not in shed, f"nothing was shed one column down:\n{shed}"
    # The marker is on this panel's own rectangle, and it names the field.
    assert "‹ widen" in shed.split("\n")[0], shed
    assert "24h volume" in shed.split("\n")[0], shed


async def test_the_row_marker_follows_a_live_resize_in_both_directions():
    """Dragging the window is the common case, and it refetches nothing.

    The title bar is composed from the last payload, so without a resize
    hook the marker only corrects itself on the next 30-second poll: half a
    minute of a lit marker on a terminal that now fits, or -- worse -- of a
    dark one on a terminal that no longer does.
    """
    async with _screen_at(SURF_FULL_LAYOUT_COLUMNS, 46) as (app, _screen, pilot):
        assert TALLER_HINT not in _screen_text(app).split("\n")[0]

        await pilot.resize_terminal(SURF_FULL_LAYOUT_COLUMNS, 30)
        await pilot.pause()
        assert TALLER_HINT in _screen_text(app).split("\n")[0], (
            "the terminal shrank past the rail and the marker stayed dark"
        )

        await pilot.resize_terminal(SURF_FULL_LAYOUT_COLUMNS, 46)
        await pilot.pause()
        assert TALLER_HINT not in _screen_text(app).split("\n")[0], (
            "the terminal grew back and the marker stayed lit"
        )


#: A payload with every flag the title bar can carry lit at once: the LP owner
#: warning and three degraded groups. Not a hypothetical -- ``degraded`` is a
#: list the manager grows one entry per failing source group, and the LP flag
#: is independent of it.
def _worst_case_title_payload() -> dict:
    return _frozen_payload(
        feed_items=_representative_feed_items(),
        degraded=["logs", "market", "nft"],
        lp_owner_ok=False,
    )


async def test_the_row_marker_survives_a_title_bar_full_of_warnings():
    """The one loss signal on the screen must not be the first thing lost.

    ``#title-bar`` is one row high and the ``Static`` *wraps*: everything past
    the first line reaches no pixel at all -- no ``…``, no scrollbar, nothing.
    With three degraded groups and the LP warning the line ran 118 columns, so
    at 100 the wrap fell inside the degraded list and took ``‹ taller`` (and
    the version tail) with it. The rail was scrolling, DEV ACTIVITY's rows
    were off screen, and the screen said so nowhere -- and only when a source
    was *also* down, which is precisely when a reader needs both.

    So the marker rides in front of the warnings. It is the only advertisement
    on this screen with no second home: the LP flag is also the hero's
    ``OWNER CHANGED`` box, and a degraded group is also its own panel's
    unavailable state, but nothing else anywhere says a row went off the
    bottom.
    """
    payload = _worst_case_title_payload()
    for width in (100, 120, 143, SURF_FULL_LAYOUT_COLUMNS):
        async with _screen_at(width, 30, payload=payload) as (app, screen, _p):
            assert screen.query_one(_RAIL).show_vertical_scrollbar is True, (
                f"{width}x30 fits the rail after all -- pick a shorter height"
            )
            row0 = _screen_text(app).split("\n")[0]
            assert TALLER_HINT in row0, (
                f"at {width}x30 the rail is scrolling and row 0 says nothing:\n"
                f"{row0!r}"
            )
            # The warning it now precedes is still on the same row -- the fix
            # is an ordering, not a trade of one advertisement for another.
            assert "⚠ LP owner changed" in row0, row0

    # ...and it stays dark on a terminal that fits, warnings or no warnings:
    # this must not become a marker that is simply always on.
    async with _screen_at(100, 46, payload=payload) as (app, screen, _p):
        assert screen.query_one(_RAIL).show_vertical_scrollbar is False
        assert TALLER_HINT not in _screen_text(app)


#: A width where ``SurfDevActivity`` is genuinely below its widest tier, for
#: the resize test below.  It must **not** be ``SURF_FULL_LAYOUT_COLUMNS``:
#: that constant is by definition the width at which nothing is shed, so using
#: it here made the "before" assertion vacuous the moment the constant was
#: re-measured from 135 to 176 -- the panel already showed the amount column,
#: and the test could no longer see a re-tier happen at all.  It was 143 while
#: the full row needed 66 columns of rail; the row needs 58 now, so 143 is
#: inside the *clean* band and re-tiers from nothing.  120 is a real terminal
#: width, is inside the marked band pinned above, and leaves the panel a
#: genuine tier below its widest.
_NARROW_FOR_RE_TIER = 120


async def test_the_activity_panel_re_tiers_when_the_terminal_is_resized():
    """``SurfDevActivity.on_resize`` outlived the ``c`` swap that motivated it.

    It was written because the panel was composed hidden and therefore first
    rendered at zero width, where ``_tier_for`` optimistically picks ``full``.
    That is gone, but the path is not: ``RichLog`` rows are formatted at write
    time against the width they were written at, so a widened terminal shows
    yesterday's tier -- padded, shrunken and marked -- until something
    re-renders them. Nothing else does.
    """
    async with _screen_at(_NARROW_FOR_RE_TIER, 46) as (app, screen, pilot):
        activity = screen.query_one(SurfDevActivity)
        assert "0.310 ETH" not in _region_text(app, activity)

        await pilot.resize_terminal(200, 46)
        await pilot.pause()

        panel = _region_text(app, screen.query_one(SurfDevActivity))
        assert "0.310 ETH" in panel, (
            "the rows kept the narrow terminal's tier after it was widened"
        )
        assert "‹ widen" not in panel


# -- the pinned full-layout width ---------------------------------------

from maxpane_dashboard.__main__ import _DEFAULT_FONT_SIZE  # noqa: E402
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


async def _widen_markers(width: int, payload: dict | None = None) -> int:
    """Composited ``‹ widen`` count at *width*, whole screen.

    Defaults to the representative (no-unbreakable-token) payload; pass
    ``payload=`` to measure against something else, e.g. the full sample with
    the tx-linked post.  There is no ``view`` argument any more: every panel
    is composited at once, so one render measures the whole dashboard.
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
        return _screen_text(app).count("‹ widen")


async def _markers_outside_the_activity_panel(width: int) -> int:
    """The same count, minus the ones inside ``SurfDevActivity``'s rectangle.

    The activity panel is the one widget the three-row layout genuinely
    narrowed -- it swapped a ``3fr`` slot of its own for a share of the right
    rail -- so it is the last panel to come clean as the terminal widens.
    Subtracting it is how the tests below still say something about *the
    other five*, and it is how the seam's balance is measured: the two
    numbers are now adjacent where they were 41 columns apart.
    """
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        whole = _screen_text(app).count("‹ widen")
        panel = _region_text(app, screen.query_one(SurfDevActivity))
        return whole - panel.count("‹ widen")


# -- the seam, and the width it buys ------------------------------------
#
# Both lower rows split on one seam, and *where* that seam sits is the whole
# full-layout width. It is a measurement, not a taste call: the left column's
# binding panel is ``SurfFeed`` (the columns it needs before it breaks a post)
# and the right column's is ``SurfDevActivity`` (the rail it needs before it
# sheds a field), so the narrowest terminal serving both is their sum -- and
# only a seam near their ratio collects it.
#
# **The two needs, and the sweep, are both dated. Re-measure before quoting.**
#
# *At the 3:2 -> 7:6 re-seam*, the needs were 81 and 71 (sum 152). 3:2 handed
# the feed 0.60 W against the 0.538 it needed, so the rail reached 71 only at
# 176: 24 columns wider than the layout required, and past the ~169 a laptop
# gets at the 17 pt MaxPane forces on launch. Swept over the real screen then:
#
#     5:3 187 · 13:8 184 · 8:5 183 · 3:2 176 · 7:5 169 · 11:8 167 · 4:3 164
#     1:1 162 · 9:7 161 · 5:4 158 · 11:9 156 · 12:11 156 · 6:5 155 · 10:9 154
#     19:17 154 · 9:8 153 · 13:11 153 · 17:15 153 · 7:6 152 · 8:7 152
#     23:20 152 · 81:71 152
#
# *Today the needs are 76 and 63* -- ``feed.FULL_TEXT_WIDTH`` came down 76 ->
# 71 (feed's need 81 -> 76) and the activity row's cells were sized to their
# producer's vocabularies (rail's need 71 -> 63). Sum 139. Re-swept the same
# way, patching both copies of the seam (``DEFAULT_CSS`` *and* the
# ``minimal.tcss`` block, which outranks it -- patching one alone measures
# nothing):
#
#     5:3 166 · 13:8 163 · 8:5 162 · 3:2 156 · 1:1 152 · 7:5 149 · 11:8 148
#     12:11 146 · 4:3 145 · 10:9 145 · 17:15 144 · 8:7 143 · 9:7 142 · 7:6 142
#     13:11 141 · 5:4 140 · 6:5 140 · 11:9 139 · 23:19 139 · 76:63 139
#
# So the floor moved 152 -> 139 and the seam that collects it moved with it:
# ~1.21 now (76:63), not ~1.14-1.19. **7:6 costs 142, three columns above the
# floor**, and the layout keeps it: ``__main__.FULL_LAYOUT_COLUMNS`` is FWA's
# 143 again, so a surf screen that cleared at 139 instead of 142 would not
# move one number a user sees. Re-seaming is what you do when one of the two
# needs moves; recording the three columns is what you do meanwhile.
#
# These constants used to be ``FIRST_CLEAN_WIDTH`` (an alias for
# ``SURF_FULL_LAYOUT_COLUMNS``) and ``FIRST_CLEAN_WIDTH_WITHOUT_THE_ACTIVITY_
# PANEL = 135``, describing the 3:2 seam with 41 columns of daylight between
# them. Both moved with the seam.

#: Column-points a maximized laptop terminal has to spend: columns times font
#: size, which is very nearly constant because the window is already as wide as
#: the display. Measured 169 columns at 17 pt, and the README's other quoted
#: pair falls out of the same number -- 2873 / 14 == 205.2, i.e. the "about 205
#: at 14 pt" it prints two lines later.
LAPTOP_COLUMN_POINTS = 2873

#: Columns a laptop gets at the font size ``__main__`` forces on launch. The
#: whole point of the seam re-measurement: at 3:2 the full layout needed 176 and
#: was therefore unreachable here without ``--font-size``.
#:
#: **Derived from ``_DEFAULT_FONT_SIZE``, not written down.** It was the bare
#: literal ``169`` until final review I-3, which left the premise of
#: ``test_the_full_layout_is_reachable_at_the_forced_font_size`` unpinned:
#: raising the forced size to 24 pt would have dropped a real laptop to 119
#: columns while the test happily went on rendering at 169 and passing, with
#: the claim in its own name false. Now the same edit moves this number and
#: the test measures the width the app actually produces.
LAPTOP_COLUMNS_AT_THE_FORCED_FONT = LAPTOP_COLUMN_POINTS // _DEFAULT_FONT_SIZE

#: The narrowest width at which **no** surf panel composites a ``‹ widen``,
#: swept one column at a time over the real screen and pinned in both
#: directions by ``test_the_measured_full_layout_width_is_exactly_the_tight_one``.
#:
#: Deliberately kept as an **independent literal** rather than an alias for
#: ``SURF_FULL_LAYOUT_COLUMNS``, even now that the two agree. The source
#: constant is quoted by ``__main__.FULL_LAYOUT_COLUMNS``, the ``--font-size``
#: help text, the README width table and CLAUDE.md; this number is what the
#: screen actually measures. Aliasing them would turn every cross-check below
#: into a constant compared against itself, which pins nothing -- the whole
#: point is that a widget growing a column moves *this* one and the mismatch
#: is what goes red.
#:
#: They have been apart twice, both times for one commit, both times because
#: a re-measurement lands before the five surfaces that quote it: 24 apart
#: when the 3:2 -> 7:6 re-seam brought the measurement 176 -> 152, and 10
#: apart when sizing the activity row's wallet and kind cells to the
#: producer's real vocabularies (``{"dev", "ops"}`` and ``DEV_TX_KINDS``)
#: took ``activity.FULL_WIDTH`` 66 -> 58 and this measurement 152 -> 142.
#: ``test_the_documented_width_still_covers_the_measured_one`` held the
#: direction meanwhile (generous is safe; short clips). Both reconciliations
#: landed; both constants read **142**.
#:
#: **The binding panel changed hands at 142 and stayed changed.** The activity
#: panel clears from a 135-column terminal now -- seven columns below this --
#: so the last marker standing at 141 is ``SurfFeed``'s. Every claim of the
#: form "the activity panel is the one still buying width" belongs to the 176
#: and 152 eras.
MEASURED_FULL_LAYOUT_COLUMNS = 142

#: The narrowest width at which every panel *except* the activity is clean --
#: i.e. the width ``SurfFeed`` alone asks for. It was 41 below the number
#: above at the 3:2 seam (that gap *was* the defect), one below it at 7:6, and
#: 10 below it after ``feed.FULL_TEXT_WIDTH`` dropped 76 -> 71 so the feed
#: would wrap in a narrower column. It is now **equal** to it: the activity
#: row's shrink handed those last 10 columns back, and the feed is the only
#: panel still asking for width at all.
MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL = 142

#: How far the *activity* column may drift above the feed's before the seam is
#: worth re-cutting. Not a tolerance to widen when a measurement disappoints:
#: it is width the rail is buying that the feed has stopped using. Lower it
#: when a re-seam banks some; never raise it to make a number pass.
#:
#: **Zero**, and it stays zero: the activity panel clears seven columns below
#: the feed, so it is buying nothing. A ratchet above 0 would let that gap
#: re-open in silence.
#:
#: Read what it measures, though, and not more. This number is deliberately
#: one-sided -- it subtracts the activity panel and nothing else -- so it goes
#: blind exactly when the *feed* is the panel above the seam's balance point,
#: which is the regime the screen is in now. The recoverable width today is
#: **3 columns** (7:6 collects the layout at 142; a 76:63-shaped seam collects
#: it at the 139 the two panels actually sum to), measured in the seam table
#: above and not visible here at all. Those three columns are unspent on
#: purpose: ``__main__.FULL_LAYOUT_COLUMNS`` is FWA's 143, so surf clearing at
#: 139 rather than 142 would change nothing anyone sees. If the feed's or the
#: rail's need moves again, re-sweep the table before re-seaming -- do not
#: raise this constant to describe it.
RECOVERABLE_SEAM_SLACK = 0

#: Readable alias at the one site that wants to say "the width at which this
#: panel has everything it needs".
FIRST_CLEAN_WIDTH = MEASURED_FULL_LAYOUT_COLUMNS


async def test_a_narrow_tier_advertises_rather_than_truncating_silently():
    """Well below the threshold every drop is announced, never silent."""
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 20) > 0


# -- the seam's measured consequences (the sweep is documented above) ----


async def test_the_measured_full_layout_width_is_exactly_the_tight_one():
    """Both directions, both sides a render of the real screen.

    Too high and the app would document a terminal wider than any panel
    needs; too low and it documents one that clips. The ``-1`` assertion is
    what keeps a widget that quietly grows a column failing *here*, with the
    number in hand.
    """
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS) == 0, (
        f"a marker survives at {MEASURED_FULL_LAYOUT_COLUMNS} -- the measured "
        "width clips, re-measure it"
    )
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 1) > 0, (
        f"the screen is already clean at {MEASURED_FULL_LAYOUT_COLUMNS - 1} -- "
        "the measured width is padded, re-measure it"
    )


async def test_the_full_layout_is_reachable_at_the_forced_font_size():
    """The prize. ``__main__`` forces 17 pt, which is ~169 columns on a laptop.

    At the 3:2 seam this was one marker short of clean -- the dev-activity
    panel one tier down, permanently, on the font size the app itself picks.
    A "full layout" no user reaches without passing ``--font-size 12`` is not
    a full layout, it is a footnote.

    The width is *derived* from ``_DEFAULT_FONT_SIZE`` (see
    ``LAPTOP_COLUMNS_AT_THE_FORCED_FONT``), so changing what the app forces
    moves what this renders at instead of leaving the claim in the name
    quietly false.
    """
    assert await _widen_markers(LAPTOP_COLUMNS_AT_THE_FORCED_FONT) == 0, (
        f"a panel is still shedding fields at {LAPTOP_COLUMNS_AT_THE_FORCED_FONT} "
        "columns, the width the forced font size actually gives"
    )


async def test_the_two_columns_now_clear_at_the_same_width():
    """No panel is buying width above the rest any more.

    At 3:2 the other five panels were clean from 135 and the activity panel
    only at 176: 41 columns bought for one widget, every one of them wasted
    on a feed that had already stopped needing them. The 7:6 seam closed that
    to one column; the feed's ``FULL_TEXT_WIDTH`` dropping 76 -> 71 re-opened
    it to 10, deliberately, as width a future seam re-cut could spend.

    It is **zero** now, and from the other direction: sizing the activity
    row's wallet and kind cells to the producer's real vocabularies took
    ``activity.FULL_WIDTH`` 66 -> 58, and that panel now clears from 135 --
    seven columns *below* the feed. The last panel asking for width is
    ``SurfFeed``, which is what the two assertions at the bottom pin. If the
    activity panel ever becomes the last one again, they say so by name.

    The gap may shrink freely; it may not grow, because a growing gap means
    one column is again buying width the other stopped using.

    What this does **not** say: that the seam is optimal. It is one-sided by
    construction -- it subtracts the activity panel, so it can only see the
    rail overshooting the feed, never the feed overshooting the rail, which is
    the direction the screen overshoots in today. The seam table above has
    that number (3 columns, deliberately unspent); see
    ``RECOVERABLE_SEAM_SLACK``.
    """
    assert await _markers_outside_the_activity_panel(
        MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL
    ) == 0
    assert await _markers_outside_the_activity_panel(
        MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL - 1
    ) > 0, "those panels are clean below the measured width -- re-measure it"
    assert (
        MEASURED_FULL_LAYOUT_COLUMNS - MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL
    ) <= RECOVERABLE_SEAM_SLACK, (
        "the gap between the two columns grew: one is buying width the other "
        "has already stopped using. Re-cut the seam for the feed's current "
        f"FULL_TEXT_WIDTH, or lower {RECOVERABLE_SEAM_SLACK} deliberately"
    )
    # ...and the last marker standing is the *feed's* -- outside the activity
    # panel, which by then has been clean for seven columns already.
    assert await _widen_markers(MEASURED_FULL_LAYOUT_COLUMNS - 1) == 1
    assert await _markers_outside_the_activity_panel(
        MEASURED_FULL_LAYOUT_COLUMNS - 1
    ) == 1, (
        "the activity panel is the last one asking for width again -- it "
        f"should be clean from {ACTIVITY_FIRST_FULL_TERMINAL}, well below this"
    )
    # Said directly too, on that panel's own rectangle: the arithmetic above
    # implies it, but only as long as both counts stay right.
    assert "‹ widen" not in await _activity_panel(
        MEASURED_FULL_LAYOUT_COLUMNS - 1
    )


async def test_the_documented_width_still_covers_the_measured_one():
    """``SURF_FULL_LAYOUT_COLUMNS`` may be generous; it may never be short.

    It read 176 against a measured 152 for one commit, then 152 against a
    measured 142 for another, because reconciling it reaches ``__main__``, the
    README and CLAUDE.md and belongs to a commit of its own each time; both
    now read 142. The direction is what this pins either way: a
    documented width *below* the measured one is a width that clips, which is
    the failure this whole marker system exists to prevent. Kept as an
    inequality on purpose -- it must survive the next re-measurement landing
    one commit ahead of the surfaces that quote it.
    """
    assert SURF_FULL_LAYOUT_COLUMNS >= MEASURED_FULL_LAYOUT_COLUMNS
    assert await _widen_markers(SURF_FULL_LAYOUT_COLUMNS) == 0


async def test_both_lower_rows_split_on_the_same_seam():
    """The columns line up down the screen -- a real, visible property.

    The middle row's seam and the bottom row's are one line, so SIGNALS/DEV
    ACTIVITY sit directly above IDENTITY.MD rather than beside a ragged edge.
    Swept across the seam's own rounding: ``fr`` shares land on different
    integers at different widths, and the two rows must round *together*.
    """
    for width in (MEASURED_FULL_LAYOUT_COLUMNS, 158, 163,
                  LAPTOP_COLUMNS_AT_THE_FORCED_FONT, 176, 201):
        async with _screen_at(width, 48) as (_app, screen, _p):
            feed = screen.query_one(SurfFeed).region
            rail = screen.query_one(_RAIL).region
            market = screen.query_one(SurfMarket).region
            nft = screen.query_one(SurfNft).region
            assert feed.right == rail.x, f"middle row has a gap at {width}"
            assert market.right == nft.x, f"bottom row has a gap at {width}"
            assert feed.right == market.right, (
                f"at {width} the middle row's seam is at {feed.right} and the "
                f"bottom row's at {market.right} -- the columns do not line up"
            )


# -- the blank row between the rail's two panels ------------------------


async def test_a_blank_row_separates_the_signals_from_the_dev_activity():
    """The two rail panels read as one block without it.

    Asserted three ways, because each alone is satisfied by a bug: the
    geometry (one row of gap), the *composited* content of that row (blank
    across the rail's full width -- a gap with something painted in it is not
    a separator), and that the rows on either side are **not** blank, which is
    what stops a panel that merely grew a trailing empty line from passing.
    """
    async with _screen_at(MEASURED_FULL_LAYOUT_COLUMNS, 48) as (app, screen, _p):
        signals = screen.query_one(SurfSignals).region
        activity = screen.query_one(SurfDevActivity).region
        rail = screen.query_one(_RAIL).region

        assert activity.y - signals.bottom == 1, (
            f"the rail's two panels are {activity.y - signals.bottom} rows "
            "apart, expected exactly one blank row between them"
        )

        lines = _screen_text(app).split("\n")

        def _rail_slice(y: int) -> str:
            return lines[y][rail.x : rail.x + rail.width]

        assert _rail_slice(signals.bottom).strip() == "", (
            "the separating row is not blank: "
            f"{_rail_slice(signals.bottom)!r}"
        )
        assert _rail_slice(signals.bottom - 1).strip() != "", (
            "the signals panel already ended in a blank row -- this test is "
            "measuring padding that was there before, not the separator"
        )
        assert _rail_slice(activity.y).strip() != "", (
            "the activity panel starts on a blank row -- the gap is two rows "
            "wide, not one"
        )
        # The separator must not have cost either panel a line.
        assert "BURN" in _screen_text(app)
        assert "DEV ACTIVITY" in _rail_slice(activity.y)


async def test_a_linked_post_advertises_widen_at_the_full_layout_width():
    """A tx-linked post's ``‹ widen`` at the full-layout width is correct,
    not a bug -- do not "fix" this by raising ``SURF_FULL_LAYOUT_COLUMNS``.

    The nonce-13 capture's tx-link token (a URL glued to a 66-char hex hash
    by the post's own punctuation) is 91 columns and cannot be wrapped, so
    ``SurfFeed`` truncates it visibly and says so. The house rule is "never
    clip silently"; this is that rule working.

    The *reason* not to chase it, corrected: this token is 91 columns and
    therefore finite, and the marker does clear -- at 216, pinned below.
    (The earlier wording claimed "no finite width fixes it", which was
    measurably false and would send the next reader to the wrong conclusion.)
    The conclusion is unchanged and rests on different ground: 216 is far past
    the ~169 columns a laptop gets at the forced 17 pt, and the *next* post
    linking a transaction brings its own token of its own length, so no pinned
    width settles the general case.

    It was 194 while the seam was 3:2. Narrowing the feed's share to buy the
    layout 24 columns overall moved it out to 216 -- the one thing the new
    seam costs, and it is a width nobody reaches under either seam.
    """
    assert (
        await _widen_markers(
            MEASURED_FULL_LAYOUT_COLUMNS, payload=_frozen_payload()
        )
        > 0
    )
    assert (
        await _widen_markers(SURF_FULL_LAYOUT_COLUMNS, payload=_frozen_payload())
        > 0
    )
    # Where it actually clears -- measured, not asserted from the comment.
    assert await _widen_markers(215, payload=_frozen_payload()) > 0
    assert await _widen_markers(216, payload=_frozen_payload()) == 0


# -- the hero's own width tiers (final-review I-2) -----------------------

from maxpane_dashboard.widgets.surf.hero import (  # noqa: E402
    WIDEN_HINT as HERO_WIDEN_HINT,
)


def _region_text(app, widget) -> str:
    """Composited text of just *widget*'s rectangle on the screen.

    ``_screen_text`` is the whole screen, which is useless for "nothing in
    the hero is truncated": the feed below it legitimately renders ``…`` on
    an over-long token. Slicing the compositor's strips to the widget's own
    region keeps the claim about the widget it is made about.
    """
    strips = app.screen._compositor.render_strips()
    region = widget.region
    return "\n".join(
        "".join(seg.text for seg in strips[y])[region.x : region.x + region.width]
        for y in range(region.y, region.y + region.height)
    )


async def _hero_text(width: int) -> str:
    """Composited text of the hero row alone at *width* columns."""
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfHero))


def _hero_fields(text: str) -> set[str]:
    """The hero's content words, free of box drawing and padding.

    Two renders at different widths differ in border length and padding even
    when they show the same fields, so a raw string compare would always
    differ. This reduces a render to what it actually *says*.
    """
    box_drawing = "─│┌┐└┘┬┴├┤┼"
    scrubbed = "".join(" " if ch in box_drawing else ch for ch in text)
    return set(scrubbed.split())


async def test_the_hero_cuts_neither_a_number_nor_a_title_at_the_pinned_width():
    """I-2: ``burned 15,74…`` and ``IDENTITY GA…`` must not be reachable.

    A truncated *word* is a shortened word; a truncated *number* still reads
    as a number, and a truncated panel title reads as a different panel. The
    hero sheds whole fields instead, so at the pinned width every title and
    every quantity arrives intact.
    """
    hero = await _hero_text(SURF_FULL_LAYOUT_COLUMNS)

    for whole in (
        "V4 HOOK", "LP #1167726", "IDENTITY GATE", "IMD SUPPLY",   # the titles
        "2,376,732 IMD", "388.4K IMD", "142.71 WETH",              # the numbers
        "1/2000", "NOT LIVE", "CLOSED", "owner ✓",
        # Since the hero took the full row this width reaches the *widest*
        # tier, so the fields the narrow tiers shed are all present too --
        # whole, and with the word that scopes them ("observed") intact.
        "burned 15,745 observed", "owner ✓ frenpet.eth",
        "since 2026-05-14", "detectors armed", "1/2000 written",
    ):
        assert whole in hero, f"{whole!r} did not survive the hero row whole"

    # The raw v3 ``L`` is gone from the box at every width, including this
    # one, where the widest tier renders. Dropped on request: rendered
    # ``2.16e+18`` it named no unit and said nothing ``142.71 WETH`` does not.
    assert "· L " not in hero

    # The general statement the list above is a sample of: at the pinned
    # width the hero truncates nothing at all.
    assert "…" not in hero, f"something in the hero is still ellipsised:\n{hero}"


async def test_the_hero_spends_new_columns_in_the_documented_order():
    """Widening restores the shed fields cheapest-last: `written`, then owner/burn.

    Pins the *order* rather than just the endpoints, because the order is the
    product decision about what a reader can most afford to lose.

    The widths are measured on the real full-width row, not guessed -- a box
    gets roughly a quarter of the terminal minus its own frame, so the tiers
    land at 91 / 99 / 119 columns (see the sweep in the module docstring of
    ``widgets/surf/hero.py``). They used to be 139 / 200 / 240 when the hero
    had half a row.

    A fourth tier used to sit above these three, holding ``· L <liquidity>``.
    The field was dropped on request, and the tier went with it rather than
    becoming a tier that renders exactly what ``compact`` renders. ``wide``
    below is therefore no longer a distinct tier -- it is kept in the sweep
    precisely to assert that extra columns now buy *nothing*, which is the
    claim that would quietly go untested if the width were simply deleted.
    """
    narrow = await _hero_text(91)     # minimal tier
    tight = await _hero_text(99)      # tight tier
    mid = await _hero_text(119)       # compact tier
    wide = await _hero_text(127)      # still compact: there is nothing wider

    # The dropped liquidity field is absent at every width, including the
    # widest -- there is no tier that brings it back.
    for text in (narrow, tight, mid, wide):
        assert "· L " not in text
        assert "e+" not in text, "a raw uint128 is rendering somewhere in the hero"

    # Past `compact`, extra columns buy nothing: the two widest renders agree
    # field for field. Without this the collapsed ladder would be untested.
    assert _hero_fields(mid) == _hero_fields(wide)

    # The observed burn: a whole short form, never cut digits.
    assert "burn 15,745" in narrow
    assert "burn 15,745" in tight
    assert "burned 15,745 observed" in mid
    for text in (narrow, tight, mid):
        assert "burned 15,74…" not in text

    # The owner assertion: the tick is the claim, the ENS name is decoration.
    assert "owner ✓" in narrow and "frenpet.eth" not in narrow
    assert "owner ✓" in tight and "frenpet.eth" not in tight
    assert "owner ✓ frenpet.eth" in mid

    # `N/2000 written` and `since <date>` are the minimal tier's own drops.
    assert "1/2000" in narrow and "written" not in narrow
    assert "1/2000 written" in tight

    # Nothing is truncated at any of the four widths.
    for text in (narrow, tight, mid, wide):
        assert "…" not in text


async def test_the_hero_marker_is_dark_on_every_terminal_anyone_owns():
    """The marker fires only when the *narrowest* tier cannot fit.

    Bolting a bare ``‹ widen`` onto the hero would leave it permanently lit
    -- back when the row was shared, the full copy needed ~220 columns,
    past the ~169 a laptop gets at the forced 17 pt. A marker that is on
    everywhere means nothing (the trap ``widgets/surf/signals.py``
    documents). Tying it to the narrowest tier keeps it dark, and the
    full-width row lowers the floor much further: 82 columns, which is
    narrower than any terminal this dashboard is usable in at all.
    """
    assert HERO_WIDEN_HINT == "‹ widen"

    for width in (82, 100, SURF_FULL_LAYOUT_COLUMNS, 143, 169, 200, 240):
        assert HERO_WIDEN_HINT not in await _hero_text(width), (
            f"the hero advertises a loss at {width} columns"
        )

    # ...and it is not merely unreachable: one column narrower a box can no
    # longer fit ``OWNER CHANGED``/``2,376,732 IMD`` at any tier, and says so.
    assert HERO_WIDEN_HINT in await _hero_text(81)


# -- the activity panel's own width tiers (final-review I-1) -------------

from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    FULL_WIDTH as ACTIVITY_FULL_WIDTH,
)
from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    _tier_for as _activity_tier_for,
)
from maxpane_dashboard.widgets.surf.activity import (  # noqa: E402
    WIDEN_HINTS as ACTIVITY_WIDEN_HINTS,
)

#: The unknown-counterparty window as ``_fmt.long_addr`` renders the real
#: unlabelled LP-fee destination. Spelled once here: every assertion below is
#: about *this exact string* surviving whole, because the classic
#: first-6/last-4 short form collides with a live spoof (see the module
#: docstring of ``widgets/surf/activity.py``).
_ADDR_WINDOW = "0x61CC704c…73f14E"

#: The hints, as **test-local literals**. Asserting
#: ``ACTIVITY_WIDEN_HINTS[tier] in text`` instead would be satisfied by an
#: empty hint -- i.e. by a widget that sheds the column in exactly the
#: silence these tests exist to catch. Proven: emptying the widget's table
#: left every assertion green until this literal was introduced.
_ACTIVITY_HINTS = {
    "compact": "‹ widen for amounts",
    "minimal": "‹ widen: time, kind, ETH",
}


def test_the_activity_hints_are_the_strings_this_file_asserts_on():
    """Pin the literals above to the widget's own table, both directions."""
    assert {
        tier: ACTIVITY_WIDEN_HINTS[tier] for tier in _ACTIVITY_HINTS
    } == _ACTIVITY_HINTS
    # The widest layout sheds nothing, so it advertises nothing.
    assert ACTIVITY_WIDEN_HINTS["full"] == ""
    assert set(ACTIVITY_WIDEN_HINTS) == set(_ACTIVITY_HINTS) | {"full"}


async def _activity_panel(width: int) -> str:
    """Composited text of the activity panel's own rectangle at *width*.

    The panel's rectangle, not the whole screen: the NFT panel one row below
    it renders ``38 transfers/24h``, so a whole-screen ``"transfer" in text``
    -- which is what this file used to assert for "the kind column is
    present" -- was true at every width, including the ones where the kind
    column had been shed. Both panels are always composited now, so the
    contamination is permanent and the fix is to stop reading the screen when
    the claim is about one panel.
    """
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfDevActivity))


#: The two quantities the captured signal details carry, spelled here because
#: every partial form of them below is derived from these strings rather than
#: typed out. ``_sample_data`` builds the details that contain them.
_SIGNAL_QUANTITIES = ("114,367", "15,745")


async def _signals_panel(width: int) -> str:
    """Composited text of the signals panel's own rectangle at *width*."""
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfSignals))


async def test_a_signal_detail_is_never_cut_through_a_number():
    """``mint 114,…`` is the defect; ``mint …`` is the fix (final review I-3).

    A detector detail is free text quoted from the announce channel, so it is
    truncated with a visible ``…`` at every width -- that part is deliberate
    and documented, and it is why this panel's ``‹ widen`` deliberately does
    *not* light for it. What is not allowed is where the cut lands: at 100
    columns it fell inside the bridge row's ``114,367`` and the burn row's
    ``15,745``, putting ``mint 114,…`` and ``burn 15,…`` on screen. A reader
    cannot tell 114 thousand from 114 million there, and nothing marks it.

    The house rule is to shed a whole field instead, which is exactly the fix
    the hero took for ``burned 15,74…``. Swept across every width where the
    panel is narrow enough to cut, so it pins the *rule* and not one width.

    Positively bound too: the details are still rendered and still truncated
    here, so a widget that stopped showing details at all would not pass.
    """
    import re

    # 92 is the narrowest width where the bridge row still has a detail budget
    # at all (below it the head renders alone, which is the panel's own
    # documented floor and not a cut).
    for width in range(92, 130):
        panel = await _signals_panel(width)
        assert "…" in panel, f"nothing is truncated at {width} -- widen the sweep"
        assert re.search(r"BRIDGE STAGE FIRED .* · \S", panel), (
            f"the bridge row lost its detail entirely at {width} columns"
        )
        for quantity in _SIGNAL_QUANTITIES:
            for cut in range(2, len(quantity)):
                partial = f"{quantity[:cut]}…"
                assert partial not in panel, (
                    f"{partial!r} at {width} columns: the detail was cut "
                    f"through {quantity}, which reads as a different number"
                )


async def test_a_whole_quantity_still_survives_where_it_fits():
    """The other half: backing the cut off must not swallow an intact number.

    Without this, dropping every trailing digit run unconditionally would
    pass the test above and quietly cost the reader a figure that fitted.
    """
    wide = await _signals_panel(MEASURED_FULL_LAYOUT_COLUMNS)
    assert "15,745" in wide, (
        "the burn row's quantity no longer survives whole at the full width"
    )


async def _activity_usable_columns(width: int) -> int:
    """Columns the activity log really has to spend, from a real render.

    This is the number ``_tier_for`` selects on -- ``RichLog``'s scrollable
    content region, i.e. the rail minus the panel's padding, the log's padding
    and the log's permanent scrollbar gutter -- not the panel's region width.
    """
    from textual.widgets import RichLog

    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        panel = screen.query_one(SurfDevActivity)
        return panel._log_width(panel.query_one("#surf-activity-log", RichLog))


#: The narrowest terminal at which the activity row fits whole -- i.e. at
#: which the ETH amount column survives. Derived below from the rail formula
#: and the widget's own ``FULL_WIDTH``, then pinned against a real render, so
#: it is not a third literal to keep in step by hand.
ACTIVITY_FIRST_FULL_TERMINAL = 135


def test_the_activity_fixture_speaks_the_producers_vocabularies():
    """The payload every width sweep above renders must be a real payload.

    Cross-layer on purpose: this file may import ``data/`` (the widget may
    not), and without that import the fixture is free to invent labels the
    pipeline never emits -- which is exactly what it did. ``surfsurf.eth`` and
    ``frenpet.eth`` sat here from WP5 until 2026-08-10, so every width
    conclusion drawn from this payload was drawn against a 12-column label
    where production sends three, and the manager's own sender re-check
    (``surf_manager.DEV_WALLETS``, keyed ``dev``/``ops``) silently matched
    nothing and skipped.

    Both directions: the fixture may only use labels the producer emits, and
    it must exercise *every* one of them, so a vocabulary that grows a third
    wallet cannot go unrendered by the sweeps.

    The ``kind`` column is the same claim one cell to the right, and it had
    the same defect: the LP row was spelled ``"LP"`` where the producer emits
    ``"lp"``. Harmless on width (two columns either way) but every sweep in
    this file was rendering a kind the pipeline never emits -- and the
    widget's only kind branches are ``"dust"`` and ``"transfer"``, both
    lower-case, so a case-folding change would have gone uncaught here.
    One direction only: ``DEV_TX_KINDS`` has seven members and this payload
    exists to measure widths, not to enumerate them -- ``tests/widgets/
    test_surf_widgets_b.py::test_activity_cells_are_sized_from_the_producers
    _own_vocabularies`` renders every one of them.
    """
    from maxpane_dashboard.data.surf_client import (
        DEV_TX_KINDS,
        _DEV_WALLET_LABELS,
    )
    from maxpane_dashboard.data.surf_manager import DEV_WALLETS

    kinds = {row["kind"] for row in _widen_sweep_payload()["dev_activity"]}
    assert kinds <= set(DEV_TX_KINDS), (
        f"the fixture sends kinds {sorted(kinds - set(DEV_TX_KINDS))}, which "
        "the client never emits"
    )

    produced = set(_DEV_WALLET_LABELS.values())
    used = {row["wallet_label"] for row in _widen_sweep_payload()["dev_activity"]}
    assert used <= produced, (
        f"the fixture sends wallet labels {sorted(used - produced)}, which "
        "the client never emits -- the width sweeps are measuring a payload "
        "production does not produce"
    )
    assert used == produced, (
        f"the fixture never renders {sorted(produced - used)}: a label the "
        "producer emits is missing from every width sweep in this file"
    )
    # ...and the manager's defence-in-depth re-check really does key on these
    # same names, which is the half an ENS-spelled label quietly bypassed.
    assert set(DEV_WALLETS) == produced


async def test_the_activity_rail_reaches_full_width_well_below_the_pinned_width():
    """Where the rail hits ``FULL_WIDTH`` -- 135 now, and 152 once.

    The rail is ``6fr`` of the 7:6 seam, so it gets the columns the feed's
    ``floor(7W/13)`` leaves -- ``ceil(6W/13)`` -- and the log spends five of
    them on two paddings and a permanent scrollbar gutter. That makes
    ``ceil(6W/13) - 5`` usable columns. The formula is the stable part and is
    swept first; only where it crosses ``FULL_WIDTH`` moved.

    It used to cross at exactly 152 (``ceil(912/13) - 5 == 66 ==
    ACTIVITY_FULL_WIDTH``), and that identity was the app's whole documented
    floor. Sizing the wallet cell to the producer's two-member vocabulary and
    the kind cell to its widest member took the row 66 -> 58, so the crossing
    moved down to 135 and this panel stopped being what sets the floor. Both
    ends are pinned: a row that quietly grows a column again moves the
    crossing back up and reddens here with the number in hand.

    ``widgets/surf/activity.py`` documented the slope as ``0.46 * terminal -
    4``, i.e. 62/67/74 at 143/152/169 against the real 61/66/73 -- an
    off-by-one that also hid the identity (final review I-2). The arithmetic
    below is written out independently of the widget so a widget that starts
    lying agrees with nothing.
    """
    from math import ceil

    for terminal in (120, ACTIVITY_FIRST_FULL_TERMINAL, 143, 150,
                     MEASURED_WIDTH_WITHOUT_THE_ACTIVITY_PANEL,
                     MEASURED_FULL_LAYOUT_COLUMNS, 160,
                     LAPTOP_COLUMNS_AT_THE_FORCED_FONT, 200):
        assert await _activity_usable_columns(terminal) == ceil(6 * terminal / 13) - 5, (
            f"the rail's usable width at {terminal} columns is not "
            "ceil(6W/13) - 5 any more -- re-derive the note in "
            "widgets/surf/activity.py::_tier_for before trusting it"
        )

    # Where it crosses, both directions, against the widget's own constant.
    assert await _activity_usable_columns(ACTIVITY_FIRST_FULL_TERMINAL) == (
        ACTIVITY_FULL_WIDTH
    ), "the rail no longer hands the panel exactly its full row at 135"
    assert await _activity_usable_columns(ACTIVITY_FIRST_FULL_TERMINAL - 1) == (
        ACTIVITY_FULL_WIDTH - 1
    ), "the width below no longer falls one column short -- re-measure"
    # ...and 135 really is the *first* such width, not merely one of them.
    assert ACTIVITY_FIRST_FULL_TERMINAL == min(
        w for w in range(60, 260) if ceil(6 * w / 13) - 5 >= ACTIVITY_FULL_WIDTH
    )
    # The panel is therefore clean well before the screen as a whole is, which
    # is the shape this change produced and the reason the floor is now the
    # feed's to set.
    assert ACTIVITY_FIRST_FULL_TERMINAL < MEASURED_FULL_LAYOUT_COLUMNS

    # ...and the note a reader lands on quotes the widths that were measured.
    # Derived from the renders above, so re-deriving the formula wrong a second
    # time reddens this instead of shipping.
    doc = " ".join(_activity_tier_for.__doc__.split())
    assert "0.46 * terminal - 4" not in doc, (
        "the rail's usable width is ceil(6W/13) - 5; 0.46W - 4 is the "
        "approximation that put 67 where the measured 66 was"
    )
    for terminal in (ACTIVITY_FIRST_FULL_TERMINAL, 143,
                     MEASURED_FULL_LAYOUT_COLUMNS,
                     LAPTOP_COLUMNS_AT_THE_FORCED_FONT):
        usable = await _activity_usable_columns(terminal)
        assert f"{usable} at {terminal}" in doc, (
            f"_tier_for's note does not say the rail has {usable} columns at "
            f"{terminal}, which is what the screen renders"
        )


async def test_the_activity_panel_shows_every_column_at_its_own_clean_width():
    """The positive half: at ``FIRST_CLEAN_WIDTH`` nothing is shed and nothing
    is advertised. Without this, the tests below could be satisfied by a
    widget that simply always renders its narrowest tier."""
    panel = await _activity_panel(FIRST_CLEAN_WIDTH)
    assert _ADDR_WINDOW in panel
    assert "0.310 ETH" in panel          # the amount column is present...
    assert "transfer" in panel           # ...and so is the kind column
    # ...and the HH:MM half of the stamp, which the minimal tier sheds. The
    # hour itself is local (``_fmt.hhmm``), so the shape is what is asserted.
    import re

    assert re.search(r"\d\d-\d\d \d\d:\d\d", panel), (
        "the stamp lost its HH:MM half at the panel's own clean width"
    )
    assert "‹ widen" not in panel        # ...so there is nothing to advertise


async def test_the_activity_panel_never_drops_the_amount_column_in_silence():
    """One column below the crossing the amount goes -- and is advertised.

    Measured on the real screen: at ``ACTIVITY_FIRST_FULL_TERMINAL - 1`` the
    rail is one column short of the full row, the ``0.310 ETH`` amount cannot
    fit, and ``RichLog(wrap=False)`` shrinks the line at write time with no
    ``…`` and nothing in the title. Shedding the column is correct; shedding
    it in silence is the defect -- a user comparing a 180-column window with a
    narrow one otherwise sees two different truths about one tx.

    This was asserted at 150 while the full row needed 66 columns of rail.
    The row needs 58 now, so 150 is comfortably inside the *clean* band and
    the boundary that means anything is the crossing itself.
    """
    panel = await _activity_panel(ACTIVITY_FIRST_FULL_TERMINAL - 1)
    assert "0.310 ETH" not in panel, (
        f"the amount fits after all at {ACTIVITY_FIRST_FULL_TERMINAL - 1} "
        "columns -- re-measure FULL_WIDTH"
    )
    # ...and one column wider it does, which is what makes this a boundary
    # rather than a width that happens to sit inside a wide marked band.
    assert "0.310 ETH" in await _activity_panel(ACTIVITY_FIRST_FULL_TERMINAL)
    assert _ACTIVITY_HINTS["compact"] in panel, (
        "the amount column vanished without the title saying so"
    )
    # The columns that were *not* shed are still there, whole.
    assert _ADDR_WINDOW in panel
    assert "transfer" in panel


async def test_the_activity_panel_names_the_columns_the_rail_costs_it():
    """120 columns is the minimal tier: address only, and the title says so.

    The rail is the panel's whole width budget, so a narrow terminal takes
    the time and kind columns as well as the amount. What is not negotiable
    is that the title names which fields went.

    This used to be asserted at **143**, then at **120**, and each move was
    a real widening of the row's reach. At the 3:2 seam a 143-column terminal
    put the panel in its *minimal* tier; 7:6 took that to compact. Sizing the
    wallet and kind cells to the producer's vocabularies took the compact row
    46 -> and the minimal band down again, so the tier only appears at 108.
    Both ends are pinned so the band cannot silently widen back.
    """
    panel = await _activity_panel(108)
    assert _ACTIVITY_HINTS["minimal"] in panel
    assert "0.310 ETH" not in panel and "transfer" not in panel
    assert _ADDR_WINDOW in panel

    # The tier the narrower cells bought back: 109 is no longer minimal, and
    # neither is 120, which the old row spent entirely on padding.
    for wider_width in (109, 120):
        wider = await _activity_panel(wider_width)
        assert _ACTIVITY_HINTS["minimal"] not in wider, (
            f"{wider_width} columns is back in the minimal tier"
        )
        assert _ACTIVITY_HINTS["compact"] in wider
        assert "transfer" in wider


async def test_the_narrow_activity_panel_never_cuts_the_poisoning_window():
    """80 columns leaves the log 27 usable -- and the window must survive.

    This is the correctness half of I-1, not a cosmetic one. Cut to its first
    six characters both live spoof addresses render ``0xF308``, which is the
    exact collision the wide ``0x``+8+``…``+6 window exists to prevent. The
    panel must shed whole fields -- time, kind, amount, and here the wallet
    label as well -- before it touches a single hex digit, and say so.

    At this width the panel is 30 columns and cannot fit the 24-column
    descriptive hint beside its title, so it falls back to the bare marker
    (``activity.SHORT_HINT``). That fallback exists because of this layout:
    the panel's old ``3fr`` slot never got this narrow.
    """
    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT

    panel = await _activity_panel(80)
    assert _ADDR_WINDOW in panel, "the anti-poisoning window was cut to fit"
    assert SHORT_HINT in panel, "three columns went with nothing said"
    # The fields that were shed to pay for it, and nothing half-rendered.
    assert "0.310 ETH" not in panel


async def test_the_poisoning_window_survives_every_terminal_the_rail_allows():
    """80 is not the bottom. Swept to a terminal narrower than the window.

    The rail hands this panel ``ceil(6W/13) - 5`` columns, so the test above
    measured one comfortable point of a curve that keeps falling. Below 61
    the row -- ``MM-DD`` + gap + window, 24 columns, the wallet cell already
    gone -- no longer fits the 23 the rail gives at W=59-60, and
    ``RichLog(wrap=False)`` narrowed it at write time with no ``…``, no
    marker and nothing in the title:

    * **60 columns** rendered ``0x61CC704c…73f14`` -- one hex digit short;
    * **50** rendered ``0x61CC704c…7``;
    * **40** rendered ``0x61CC7``, the ``…`` gone too, so a truncated
      address no longer looked truncated at all.

    At a log width of 13 the live spoof pair both render ``0xF308`` -- the
    single collision this panel's wide window exists to prevent, arrived at
    by the panel itself.

    The assertion is on every hex run in the panel's own rectangle rather
    than on the window as a literal, because a *prefix* is the defect and
    ``_ADDR_WINDOW not in panel`` cannot see one.
    """
    import re

    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT

    # ``*`` and not ``+``: the narrowest clip left a bare ``0x`` behind,
    # which a ``+`` quantifier does not match at all.
    hex_run = re.compile(r"0x[0-9A-Fa-f…]*")
    withheld = 0
    for width in range(34, 82):
        panel = await _activity_panel(width)
        for run in hex_run.findall(panel):
            assert run == _ADDR_WINDOW, (
                f"{run!r} at {width} columns: the anti-poisoning window was "
                "cut to make the row fit"
            )
        assert "no recent activity" not in panel, (
            f"{width} columns reports the dev wallets quiet; they are not"
        )
        if _ADDR_WINDOW not in panel:
            withheld += 1
            assert SHORT_HINT in panel, (
                f"the rows went at {width} columns with nothing said at all"
            )
    # Both branches really are exercised: the sweep straddles the width where
    # the window stops fitting, so neither assertion above is vacuous.
    assert 0 < withheld < 48, (
        f"{withheld} of 48 widths withheld their rows -- re-derive the sweep"
    )


async def test_the_activity_panel_is_never_silent_about_a_shed_column():
    """A shed column is announced at *every* width, not merely most of them.

    The marker normally goes beside the title, and ``_set_title`` drops it
    when the title bar itself is too narrow to hold it -- a Static with no
    ``text-overflow`` wraps instead, pushing a row out of the log. That was
    accepted while the band was unreachable; in the right rail it is not.
    At 46 and 50 columns the rail leaves the log 17 and 19, narrow enough
    that the ``MM-DD`` date goes, and the title bar (19 and 21 columns) can
    hold neither the descriptive hint nor the 7-column bare one. Three
    columns of date vanished with nothing said anywhere on the panel.

    The fallback is the one the withheld-rows branch already uses: say it in
    the log instead. Swept against the amount column, which is the last
    thing to go, so the two branches are "everything is here, and nothing is
    claimed" and "something went, and it is claimed".
    """
    from maxpane_dashboard.widgets.surf.activity import SHORT_HINT

    # From 24: the rail leaves the log ``ceil(6W/13) - 5`` columns, which is
    # exactly ``len(SHORT_HINT)`` there and less below it -- a terminal that
    # cannot render the seven columns of the marker itself is past the point
    # where any wording helps, and the rows are already withheld there
    # (``test_the_poisoning_window_survives_every_terminal_the_rail_allows``).
    clean = 0
    for width in sorted(set(range(24, 146, 5)) | {46, 50, 55, 80, 108, 134,
                                                  135, 143}):
        panel = await _activity_panel(width)
        if "0.310 ETH" in panel:
            clean += 1
            assert SHORT_HINT not in panel, (
                f"{width} columns shows every column and still advertises a "
                "loss -- a marker that is on everywhere means nothing"
            )
        else:
            assert SHORT_HINT in panel, (
                f"a column went at {width} columns with nothing said on the "
                f"panel at all:\n{panel}"
            )
    assert clean, "the sweep never reaches a width where nothing is shed"


# -- the NFT panel's own width tiers -------------------------------------
#
# ``SurfNft`` was the one surf widget with no marker machinery at all. It did
# not need any while it was the sole child of ``#bottom-row`` at ``1fr``; the
# three-row restructure put it beside the market at ``2fr`` of a 3:2 split, so
# it sees ~``0.4 * W - 4`` columns against the 46 its stats row needs and
# started silently ellipsising ``dev holds 3`` -- and, further down, cutting
# ``38 transfers/24h`` into ``38 transfers/24…``, a number with a different
# unit. ``text-overflow: ellipsis`` renders the ``…``; nothing put a word in
# the title, which is the half of the contract that names what went.

from maxpane_dashboard.widgets.surf.nft import (  # noqa: E402
    SHORT_HINT as NFT_SHORT_HINT,
    WIDEN_HINTS as NFT_WIDEN_HINTS,
)

#: The NFT hints as **test-local literals**, for the reason ``_ACTIVITY_HINTS``
#: is one: ``NFT_WIDEN_HINTS[tier] in panel`` is satisfied by an *empty* hint,
#: i.e. by exactly the silent shed these tests exist to catch. ``SHORT_HINT``
#: is additionally a **prefix** of both, so ``SHORT_HINT in panel`` cannot tell
#: the descriptive hint from the bare fallback -- every assertion below names
#: the whole string it means, and the two are asserted against each other.
_NFT_HINTS = {
    "compact": "‹ widen for dev holdings",
    "minimal": "‹ widen: 24h, dev",
}


def test_the_nft_hints_are_the_strings_this_file_asserts_on():
    """Pin the literals above to the widget's own table, both directions."""
    assert {tier: NFT_WIDEN_HINTS[tier] for tier in _NFT_HINTS} == _NFT_HINTS
    assert NFT_WIDEN_HINTS["full"] == "", "the widest tier sheds nothing"
    assert set(NFT_WIDEN_HINTS) == set(_NFT_HINTS) | {"full"}
    assert NFT_SHORT_HINT == "‹ widen"
    # The prefix relationship this file has to work around, stated once.
    for hint in _NFT_HINTS.values():
        assert hint.startswith(NFT_SHORT_HINT)


async def _nft_panel(width: int) -> str:
    """Composited text of the NFT panel's own rectangle at *width*.

    The panel's rectangle, not the whole screen: ``38 transfers/24h`` also
    appears nowhere else, but ``‹ widen`` appears in up to three other titles,
    so a whole-screen assertion about *this* panel's marker would be satisfied
    by the activity panel's.
    """
    manager = _FakeManager(payload=_widen_sweep_payload())
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _ThemedHarness(screen)
    async with app.run_test(size=(width, 48)) as pilot:
        await pilot.pause()
        await screen._do_refresh()
        await pilot.pause()
        return _region_text(app, screen.query_one(SurfNft))


async def test_the_nft_panel_shows_every_figure_at_its_own_clean_width():
    """The positive half: nothing shed, nothing cut, nothing advertised.

    107 is the measured boundary -- one column narrower the stats row no
    longer fits -- so this also pins that the panel is clean at every width
    the dashboard is actually meant to run at, the pinned one (142 today,
    read from the constant rather than retyped) included.
    Without it the sweep below is satisfied by a panel welded to its
    narrowest tier, which is the failure this codebase keeps recording.

    It was 123 at the 3:2 seam. The NFT panel is on the *right* of the seam,
    so widening the right column to 6:13 handed it 16 columns it did not have
    and every one of its tier boundaries moved down with that.
    """
    for width in (107, 143, 169, MEASURED_FULL_LAYOUT_COLUMNS,
                  SURF_FULL_LAYOUT_COLUMNS):
        panel = await _nft_panel(width)
        assert "667 holders" in panel, width
        assert "38 transfers/24h" in panel, width
        assert "dev holds 3" in panel, width
        assert "…" not in panel, f"the NFT panel truncates at {width}:\n{panel}"
        assert NFT_SHORT_HINT not in panel, (
            f"a marker is lit at {width} where nothing was shed"
        )


async def test_the_nft_panel_sheds_dev_holdings_rather_than_cutting_it():
    """106 columns: one short of the whole row, which is where it broke.

    It rendered ``dev holds…`` -- a labelled figure with the figure gone --
    with an unmarked title. Shedding the field is correct; shedding it in
    silence is the defect. (122 at the 3:2 seam; the panel got wider when the
    seam moved, so the same boundary is 16 terminal columns lower.)
    """
    panel = await _nft_panel(106)
    assert "dev holds" not in panel, "the truncated `dev holds…` is still there"
    # The fields that stayed, whole.
    assert "667 holders" in panel
    assert "38 transfers/24h" in panel
    assert _NFT_HINTS["compact"] in panel, "the field went with nothing said"


async def test_the_nft_panel_never_cuts_a_number_off_its_unit():
    """100 and 90 columns: ``… transfers/24h · …`` and ``38 transfers/24…``.

    A truncated word is a shortened word; a truncated *number* still reads as
    a number, and ``24…`` is a different quantity from ``24h``. The hero
    carries the same rule (``burned 15,74…``), and the NFT panel now sheds
    whole fields to keep it.
    """
    for width in (90, 100):
        panel = await _nft_panel(width)
        assert "38 transfers/24h" in panel, f"the unit was cut off at {width}"
        assert "dev holds" not in panel, width
    # Both hint branches are reachable, and which one shows is a width fact:
    # ``IDENTITY.MD`` + 2 + the 24-column hint needs 37 usable columns, which
    # the panel first has at a terminal width of 87 (101 at the 3:2 seam).
    assert _NFT_HINTS["compact"] in await _nft_panel(87)
    narrow = await _nft_panel(86)
    assert _NFT_HINTS["compact"] not in narrow, (
        "the descriptive hint fits after all at 86 columns -- re-measure"
    )
    # ...and the fallback is the *bare* marker, not the hint belonging to the
    # narrower tier. That one is 17 columns and does fit here, so a fallback
    # chain routed through it would render a marker naming ``24h`` -- a field
    # this tier still shows -- and every ``SHORT_HINT in panel`` assertion
    # would stay green, ``SHORT_HINT`` being a prefix of it.
    assert _NFT_HINTS["minimal"] not in narrow, (
        "the panel fell back to a hint for a tier it is not in"
    )
    assert NFT_SHORT_HINT in narrow, "a field went with nothing said at all"


async def test_the_nft_panel_names_the_fields_it_sheds_at_its_narrowest_tier():
    """74 columns leaves 32 usable, which fits ``667 holders`` and no more.

    The hint is terse because it has to be: an 11-column title plus two
    columns of gap leaves 18 for a marker that only appears when the panel is
    barely over 31 wide. Below that it falls back to the bare one. (87 and 80
    at the 3:2 seam -- the panel is wider now, so it takes a narrower terminal
    to drive it this far down.)
    """
    panel = await _nft_panel(74)
    assert "667 holders" in panel
    assert "transfers/24h" not in panel and "dev holds" not in panel
    assert _NFT_HINTS["minimal"] in panel

    bare = await _nft_panel(71)
    assert _NFT_HINTS["minimal"] not in bare, (
        "the descriptive hint fits after all at 71 columns -- re-measure"
    )
    assert NFT_SHORT_HINT in bare


async def test_no_width_lets_the_nft_panel_cut_a_line_in_silence():
    """The sweep: whatever gets cut, the title says so -- at every width.

    Two claims, both against composited output. Anything ellipsised is
    advertised, and no *number* is ever the thing ellipsised: the tiers shed
    whole labelled fields, so a figure is either whole or absent.
    """
    import re

    widths = sorted(
        set(range(80, SURF_FULL_LAYOUT_COLUMNS + 1, 6))
        | {86, 87, 88, 90, 100, 101, 122, 123, SURF_FULL_LAYOUT_COLUMNS}
    )
    for width in widths:
        panel = await _nft_panel(width)
        if "…" in panel:
            assert NFT_SHORT_HINT in panel, (
                f"the NFT panel cut a line at {width} in silence:\n{panel}"
            )
        assert re.search(r"\d…", panel) is None, (
            f"a number was cut off its tail at {width}:\n{panel}"
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


# -- refresh guard: skip, never queue ------------------------------------


def test_surf_screen_opts_into_the_refresh_guard():
    """Structural: the mixin comes first and the worker name is surf's own.

    The generic suite (tests/screens/test_refresh_guard.py) auto-discovers
    every polling screen; this pins the two things it cannot: MRO order and
    the name.
    """
    mro = SurfScreen.__mro__
    from textual.screen import Screen as _Screen

    from maxpane_dashboard.screens.refresh_guard import RefreshGuard

    assert mro.index(RefreshGuard) < mro.index(_Screen)
    assert SurfScreen.REFRESH_WORKER_NAME == "surf-refresh"


class _BlockingManager:
    """Parks inside ``fetch_and_compute`` until the test releases it."""

    def __init__(self) -> None:
        self._error_count = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return _frozen_payload()

    async def close(self) -> None:  # pragma: no cover - never called here
        pass


async def test_overrun_tick_is_skipped_never_queued_or_cancelled():
    """A tick landing mid-refresh is dropped; the refresh completes once."""
    manager = _BlockingManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        # on_screen_resume started the initial refresh; wait until it is
        # provably parked inside fetch_and_compute.
        await asyncio.wait_for(manager.entered.wait(), timeout=2)

        skipped_before = screen._refresh_skipped
        assert screen.start_refresh() is None          # the overrunning tick
        assert screen.start_refresh() is None          # and another
        assert screen._refresh_skipped == skipped_before + 2
        assert manager.calls == 1                      # nothing queued

        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()

        assert manager.calls == 1                      # nothing ran after
        assert screen._refresh_in_flight is False      # flag lowered
        # ...and the completed refresh actually rendered.
        assert "feed #14" in _plain(screen.query_one("#title-bar"))


async def test_manual_refresh_and_interval_tick_share_one_guard():
    """The ``r`` binding and the interval callback fund into one guard.

    Both are inherited unchanged from ``RefreshGuard`` (pinned structurally
    by ``test_every_polling_screen_uses_the_guard``); this drives the actual
    named entry points -- ``action_refresh`` (the ``r`` key) and
    ``_schedule_refresh`` (the interval timer) -- through a real SurfScreen
    to prove neither can double-run against the other nor deadlock waiting
    for the other to finish.
    """
    manager = _BlockingManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 1

        # A manual "r" press and an interval tick both land while the
        # initial refresh is still in flight -- neither may start a second
        # fetch, and neither blocks waiting on the other.
        screen.action_refresh()
        screen._schedule_refresh()
        for _ in range(20):
            await asyncio.sleep(0)
        assert manager.calls == 1, "a manual or interval tick started a second fetch"

        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert manager.calls == 1
        assert screen._refresh_in_flight is False

        # Once idle, a manual refresh runs cleanly to completion...
        manager.entered.clear()
        manager.release.clear()
        screen.action_refresh()
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 2
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert screen._refresh_in_flight is False

        # ...and so does an interval tick straight after it: no deadlock
        # either way round.
        manager.entered.clear()
        manager.release.clear()
        screen._schedule_refresh()
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 3
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert screen._refresh_in_flight is False


class _TrackingBlockingManager:
    """``_BlockingManager`` plus concurrency/failure observables.

    ``_BlockingManager`` above is kept exactly as the brief specifies it;
    this sibling adds the extra bookkeeping the prefetch-join and
    raise-recovery proofs below need (concurrency high-water mark, a
    one-shot failure) without touching that frozen class.
    """

    def __init__(self) -> None:
        self._error_count = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.concurrent = 0
        self.max_concurrent = 0
        self.fail_next = False

    async def fetch_and_compute(self) -> dict:
        self.calls += 1
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        self.entered.set()
        try:
            await self.release.wait()
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("simulated RPC failure")
            return _frozen_payload()
        finally:
            self.concurrent -= 1

    async def close(self) -> None:  # pragma: no cover - never called here
        pass


class _PrefetchHarness(App):
    """Reproduces ``MaxPaneApp.on_mount``'s startup prefetch closely enough
    to prove SurfScreen's own first refresh joins it (MEDI-35). Same worker
    name, same node (the app), same ``exclusive=True`` as the real app and
    as ``tests/screens/test_refresh_guard.py``'s generic harness -- this
    drives the identical race through a real ``SurfScreen`` so WP5's own
    sign-off does not rest solely on another screen's test file.
    """

    def __init__(self, manager: _TrackingBlockingManager) -> None:
        super().__init__()
        self._manager = manager

    def on_mount(self) -> None:
        from maxpane_dashboard.screens.refresh_guard import PREFETCH_WORKER_NAME

        self.run_worker(
            self._prefetch(),
            exclusive=True,
            name=PREFETCH_WORKER_NAME,
            exit_on_error=False,
        )

    async def _prefetch(self) -> None:
        try:
            await self._manager.fetch_and_compute()
        except Exception:
            pass


async def test_surf_first_refresh_joins_the_startup_prefetch():
    """SurfScreen's initial refresh does not race the app-node prefetch.

    The join behaviour (``_await_startup_prefetch``) is inherited unchanged
    from ``RefreshGuard`` and already covered generically (other screens) in
    ``tests/screens/test_refresh_guard.py``; this repeats the exact race
    through a real ``SurfScreen`` instance so the first paint is proven, not
    assumed, not to be a race between the placeholder title and real data.
    """
    manager = _TrackingBlockingManager()
    app = _PrefetchHarness(manager)
    screen = SurfScreen(manager, poll_interval=30, name="surf")

    async with app.run_test():
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 1

        # The dashboard screen appears while the prefetch is still running --
        # this is the ordering the real app produces (prefetch starts at
        # on_mount, the dashboard screen only appears after splash + game
        # select).
        app.push_screen(screen)
        for _ in range(50):
            await asyncio.sleep(0)

        # Joined, not raced: only the prefetch's fetch is in flight, and the
        # screen's own has not started yet.
        assert manager.max_concurrent == 1
        assert manager.calls == 1

        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)

        # The prefetch finished, then the screen's own fetch ran -- serially,
        # never concurrently -- and it produced the real first paint.
        assert manager.calls == 2
        assert manager.max_concurrent == 1
        assert "feed #14" in _plain(screen.query_one("#title-bar"))


async def test_a_raising_refresh_lowers_the_guard_flag_and_the_next_tick_still_runs():
    """The *guard* recovers from a raising manager, not just ``_do_refresh``.

    ``test_screen_survives_manager_exception`` already proves SurfScreen's
    own try/except around ``fetch_and_compute()`` degrades cleanly when
    ``_do_refresh()`` is called directly. This test drives the same failure
    through ``start_refresh()`` -- the real scheduling entry point used by
    the ``r`` binding and the interval timer -- to prove
    ``RefreshGuard._guarded_refresh``'s ``finally`` also lowers
    ``_refresh_in_flight`` and that the next scheduled tick still runs, so a
    raising manager cannot wedge the screen on placeholders for the rest of
    the session.
    """
    manager = _TrackingBlockingManager()
    screen = SurfScreen(manager, poll_interval=30, name="surf")
    app = _Harness(screen)
    async with app.run_test(size=(150, 46)) as pilot:
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        manager.fail_next = True
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()

        assert manager.calls == 1
        assert screen._refresh_in_flight is False, "a raising refresh wedged the guard"

        manager.entered.clear()
        manager.release.clear()
        screen._schedule_refresh()
        await asyncio.wait_for(manager.entered.wait(), timeout=2)
        assert manager.calls == 2, "the guard did not schedule the next tick"
        manager.release.set()
        for _ in range(50):
            await asyncio.sleep(0)
        await pilot.pause()
        assert screen._refresh_in_flight is False
        assert "feed #14" in _plain(screen.query_one("#title-bar"))
