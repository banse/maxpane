"""Headless Textual tests for surf widgets group A (WP3).

Covers the shared formatters, ``SurfHero``, ``SurfSignals`` and ``SurfMarket``.
Group B (feed, dev activity, NFT) lives in ``test_surf_widgets_b.py``.

Every content assertion reads the *composited* screen via
``_compositor.render_strips()`` -- a string that never reaches a pixel must not
pass (house rule).  Zero network: these widgets have no I/O by construction;
``test_surf_widget_contract.py`` proves it structurally with an AST scan.

Payload values are derived from the committed captures under
``tests/fixtures/surf/captures/`` (see the table in docs/plans wp3), so the
representative payloads are the real 2026-08-08 chain state, not invented
numbers.
"""

from __future__ import annotations

import inspect

from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.surf import _fmt


class _Harness(App):
    """Mount a single widget instance so we can drive ``update_data``."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    """Composited screen text -- what a user would actually see."""
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


def _none_payload(widget) -> dict:
    """All-``None`` payload built from the widget's own signature."""
    return {
        name: None
        for name, param in inspect.signature(widget.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    }


# ---------------------------------------------------------------------
# _fmt -- pure formatters
# ---------------------------------------------------------------------


def test_fmt_age_buckets():
    assert _fmt.fmt_age(45) == "45s"
    assert _fmt.fmt_age(720) == "12m"
    assert _fmt.fmt_age(7200) == "2h"
    assert _fmt.fmt_age(3 * 86400) == "3d"
    assert _fmt.fmt_age(0) == "0s"


def test_fmt_age_none_and_negative_are_dashes_never_zero():
    """A missing age is unknown, not ``0s`` -- ``None`` never 0-coerces."""
    assert _fmt.fmt_age(None) == "--"
    assert _fmt.fmt_age(-5) == "--"
    assert _fmt.fmt_age("garbage") == "--"
    assert _fmt.fmt_age(float("nan")) == "--"


def test_fmt_price_precision():
    # 0.7074 is the live IMD price in dexscreener_imd.json -- four decimals,
    # not the FWA sub-cent five, and never scientific notation.
    assert _fmt.fmt_price(0.7074) == "$0.7074"
    assert _fmt.fmt_price(1917.74) == "$1,917.74"
    assert _fmt.fmt_price(0.0003686) == "$0.000369"
    assert _fmt.fmt_price(None) == "--"


def test_fmt_liquidity_handles_raw_v3_uint():
    # positions().liquidity is a raw uint128 ~1e19 -- compact K/M/B suffixes
    # are meaningless there, scientific is honest.
    assert _fmt.fmt_liquidity(26010397574917496158) == "2.60e+19"
    assert _fmt.fmt_liquidity(548701.21) == "548.7K"
    assert _fmt.fmt_liquidity(None) == "--"


def test_long_addr_distinguishes_the_live_spoof_pair():
    """0x+8+…+6 must tell the real fee recipient from its live poisoner.

    Both addresses are in frenpet.eth's history right now
    (ops_eth_txs.json): the spoof matches the real address's first 6 and
    last 4 -- the classic short-form collision -- but differs inside the
    first-8 and last-6 windows this format shows.
    """
    real = _fmt.long_addr("0xF3084Bc7380D2dEfaA5bB42DCA6F517424D60eE6")
    spoof = _fmt.long_addr("0xF3083828702C1989710CECA517412071c2f60Ee6")
    assert real == "0xF3084Bc7…D60eE6"
    assert spoof == "0xF3083828…f60Ee6"
    assert real != spoof
    assert _fmt.long_addr(None) == "--"
    assert _fmt.long_addr("") == "--"


def test_long_addr_does_not_escape_markup_the_caller_owns_that():
    """Contract: ``long_addr`` returns raw text; escaping is the widget's job.

    A hostile on-chain string routed through ``long_addr`` (e.g. a short
    display name standing in for an address) must come back byte-identical,
    ``[/x]`` and all -- proving this formatter never calls ``safe_markup``.
    If it started escaping here, a widget that *also* escapes (as the house
    rule requires at the render boundary) would double-escape and show the
    user literal backslash-bracket text instead of the intended glyph. This
    test is the tripwire: change it and the double-escaping question has to
    be answered deliberately, not discovered on screen.
    """
    assert _fmt.long_addr("[/x]") == "[/x]"


def test_hhmm_mmdd_fallbacks():
    assert _fmt.hhmm(None) == "??:??"
    assert _fmt.hhmm("junk") == "??:??"
    assert _fmt.mmdd(None) == "??-??"
    # Real values are localtime-dependent; assert the shape only.
    assert len(_fmt.hhmm(1786076831)) == 5
    assert len(_fmt.mmdd(1786076831)) == 5


# ---------------------------------------------------------------------
# SurfHero
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.hero import (  # noqa: E402
    HOOK_LAUNCHED,
    HOOK_NOT_LIVE,
    SurfHero,
)

#: Live 2026-08-08 chain state: pool sides from dexscreener_imd.json
#: liquidity.base/quote, supply from imd_token.json total_supply/1e18.
#:
#: ``hook_status`` is spelled the way the *manager* spells it (WP4
#: ``_hook_status`` -> "NOT LIVE" / "LAUNCHED" / None, frozen in WP0's
#: SURF_KEYS comment and PRD §4).  A lowercase-snake fixture here would make
#: this whole file green against a widget that mis-renders every live payload.
#:
#: ``imd_burned_cum`` is 15,745 -- the single 2026-08-05 event -- and NOT the
#: 58,848 all-time ledger (12039+31064+15745) of PRD §1.  WP4 accumulates this
#: key from supply readings taken *after* this install started watching, so an
#: all-time fixture here would be pinning a number the data layer can never
#: produce, and would quietly certify all-time copy in the widget.  See the
#: ``imd_burned_cum`` note in WP3.2 and WP4 open issue 4.
_FULL_HERO = {
    "hook_status": HOOK_NOT_LIVE,
    "lp_liquidity": 26010397574917496158,
    "lp_imd": 388421.0,
    "lp_weth": 142.7067,
    "lp_owner_ok": True,
    "gate_open": False,
    "identities_written": 1,
    "imd_supply": 2376731.868679,
    "imd_burned_cum": 15745.0,
}


async def test_hero_full_payload_renders_all_four_boxes_on_screen():
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**_FULL_HERO)
        await pilot.pause()
        screen = _screen_text(app)
        # HOOK: the launch state is words, not colour (PRD §3/§11).
        assert "NOT LIVE" in screen
        # LP: both pool sides and the owner sanity flag.
        assert "388.4K IMD" in screen
        assert "142.71 WETH" in screen
        assert "2.60e+19" in screen
        assert "owner ✓ frenpet.eth" in screen
        # GATE: closed, 1/2000 written (identity_counters + research).
        assert "CLOSED" in screen
        assert "1/2000 written" in screen
        # SUPPLY: full-precision supply + the burn this install has observed.
        # The word "observed" is load-bearing: the widget cannot know the
        # all-time total, so it must not imply one (WP4 open issue 4).
        assert "2,376,732 IMD" in screen
        assert "burned 15,745 observed" in screen
        assert "cum" not in screen


async def test_hero_zero_observed_burn_never_claims_none_was_ever_burned():
    """The day-one payload: healthy RPC, one supply read, nothing observed yet.

    WP4's ``observed_burn_total()`` returns ``None`` until the first successful
    supply read and ``0.0`` from then on, so a fresh install with a working RPC
    is handed ``0.0`` within one refresh -- while ~58,849 IMD had in fact been
    burned before the install existed (PRD §1).  Printing ``burned 0`` there is
    a confident false statement about the token, so ``0.0`` gets its own
    phrasing and no quantity is formatted.  ``None`` stays the unavailable dash.
    """
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "imd_burned_cum": 0.0})
        await pilot.pause()
        screen = _screen_text(app)
        assert "no burn observed yet" in screen
        assert "burned 0" not in screen
        # The supply beside it is live and must still render.
        assert "2,376,732 IMD" in screen

        # None is "we have never read a supply", not "zero burned".
        widget.update_data(**{**_FULL_HERO, "imd_burned_cum": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "no burn observed yet" not in screen
        assert "burned 0" not in screen
        assert f"burned {_fmt.DASH}" in screen   # _fmt is imported at file top


async def test_hero_launched_and_gate_open_flip_the_words():
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "hook_status": HOOK_LAUNCHED, "gate_open": True})
        await pilot.pause()
        screen = _screen_text(app)
        assert "LAUNCHED" in screen
        assert "NOT LIVE" not in screen
        assert "OPEN" in screen
        assert "CLOSED" not in screen


async def test_hero_real_hook_vocabulary_never_hits_the_fallback():
    """The two values the manager actually emits must reach dedicated states.

    Both literals render *something* through the fallback arm too -- it
    uppercases whatever it is handed -- so asserting "NOT LIVE" in the screen
    proves nothing about which branch ran.  The subtitle is the tell: only the
    fallback says "unrecognized status".  This is the regression guard for the
    vocabulary mismatch (widget on ``not_live``/``launched`` vs manager on
    ``NOT LIVE``/``LAUNCHED``), which was silent on day one and would have
    stripped the $success styling from launch day itself.
    """
    assert (HOOK_NOT_LIVE, HOOK_LAUNCHED) == ("NOT LIVE", "LAUNCHED")

    for status, expected_sub in (
        (HOOK_NOT_LIVE, "detectors armed"),
        (HOOK_LAUNCHED, "v4 hook live"),
        # Case/spacing drift from the manager still lands on the real state.
        ("not live", "detectors armed"),
        ("launched", "v4 hook live"),
    ):
        widget = SurfHero()
        app = _Harness(widget)
        async with app.run_test(size=(160, 12)) as pilot:
            widget.update_data(**{**_FULL_HERO, "hook_status": status})
            await pilot.pause()
            screen = _screen_text(app)
            assert expected_sub in screen, status
            assert "unrecognized status" not in screen, status


async def test_hero_owner_changed_is_loud_words_not_colour():
    """lp_owner_ok=False means the LP NFT moved -- the launch precondition."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "lp_owner_ok": False})
        await pilot.pause()
        screen = _screen_text(app)
        assert "OWNER CHANGED" in screen
        assert "owner ✓" not in screen

        # And None is unknown -- neither the checkmark nor the alarm.
        widget.update_data(**{**_FULL_HERO, "lp_owner_ok": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "OWNER CHANGED" not in screen
        assert "owner ✓" not in screen
        assert "owner --" in screen


async def test_hero_no_args_and_all_none_render_dashes_never_zero():
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        screen = _screen_text(app)
        assert "Loading" not in screen
        assert "—" in screen
        # A dead RPC must not render as a zero supply or a zero burn
        # (the false-BURN hazard, game_mechanics §Hazards 5).
        assert "0 IMD" not in screen
        assert "burned 0" not in screen


async def test_hero_unknown_hook_status_is_escaped_not_parsed():
    """The manager owns the vocabulary; a new value must render, not crash."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "hook_status": "[/x] holder-gated"})
        await pilot.pause()  # the crash would happen inside the message pump
        screen = _screen_text(app)
        assert "HOLDER-GATED" in screen
        # This is the arm the two real values must never reach.
        assert "unrecognized status" in screen
