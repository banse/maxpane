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
    SurfHero,
    _burn_lines,
    _lp_lines,
    _pool_lines,
)

#: 2026-08-23 chain state, post-migration: the v3 LP position (#1167726) was
#: burned 2026-08-17 (``lp_state == "gone"``), the live pool is the hookless
#: v4 pool (``pool_venue == "v4"``), and 37 of the 38 ETH/IMD v4 pools on
#: mainnet are third-party decoys at fee tiers up to 98% -- this pool's own
#: fee is 1% (``pool_fee_bps == 10000``, Uniswap's fee unit is hundredths of
#: a bip: ``fee / 1e6``).
#:
#: ``imd_burned_cum`` is 15,745 -- the single 2026-08-05 event -- and NOT the
#: 58,848 all-time ledger (12039+31064+15745) of PRD §1.  WP4 accumulates this
#: key from supply readings taken *after* this install started watching, so an
#: all-time fixture here would be pinning a number the data layer can never
#: produce, and would quietly certify all-time copy in the widget.  See the
#: ``imd_burned_cum`` note in WP3.2 and WP4 open issue 4.
_FULL_HERO = {
    "pool_venue": "v4",
    "pool_fee_bps": 10000,
    "pool_liquidity_usd": 805_927.0,
    "pool_id_source": "hook",
    "decoy_pool_count": 37,
    "lp_state": "gone",
    "lp_imd": None,
    "lp_weth": None,
    "lp_owner_ok": None,
    "burn_accrued": 1_234.56,
    "burn_staged": 45.0,
    "burn_ready": False,
    "imd_supply": 2376731.868679,
    "imd_burned_cum": 15745.0,
}


# -- the four brief-mandated pure-function tests (Task 8 step 1) -------


def test_lp_card_says_migrated_not_unknown() -> None:
    lines = _lp_lines(lp_state="gone", lp_imd=None, lp_weth=None, lp_owner_ok=None, tier="full")
    text = " ".join(lines)
    assert "migrated" in text
    assert "unknown" not in text and "--" not in text


def test_lp_card_still_says_unknown_on_a_failed_read() -> None:
    lines = _lp_lines(lp_state=None, lp_imd=None, lp_weth=None, lp_owner_ok=None, tier="full")
    assert "migrated" not in " ".join(lines)


def test_pool_card_names_the_venue_and_the_decoys() -> None:
    lines = _pool_lines(pool_venue="v4", pool_fee_bps=10000, pool_liquidity_usd=805927.0,
                        decoy_pool_count=37, pool_id_source="hook", tier="full")
    text = " ".join(lines)
    assert "v4" in text and "1%" in text and "38" in text


def test_pool_card_flags_a_fallback_id() -> None:
    """If the hook read failed the panel must not imply it knows the pool."""
    lines = _pool_lines(pool_venue="v4", pool_fee_bps=None, pool_liquidity_usd=None,
                        decoy_pool_count=None, pool_id_source="fallback", tier="full")
    assert "?" in " ".join(lines) or "unverified" in " ".join(lines)


def test_burn_card_distinguishes_zero_from_unread() -> None:
    zero = _burn_lines(burn_accrued=0.0, burn_staged=0.0, burn_ready=False,
                       imd_burned_cum=3299.0, tier="full")
    unread = _burn_lines(burn_accrued=None, burn_staged=None, burn_ready=None,
                         imd_burned_cum=None, tier="full")
    assert " ".join(zero) != " ".join(unread)
    assert "0" in " ".join(zero)


# -- SurfHero integration tests (composited output) ---------------------


async def test_hero_full_payload_renders_all_four_boxes_on_screen():
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**_FULL_HERO)
        await pilot.pause()
        screen = _screen_text(app)
        # POOL: venue, fee tier and the decoy-inclusive pool count.
        assert "v4" in screen
        assert "1%" in screen
        assert "38" in screen
        assert "$805.9K" in screen
        # LP: a completed migration is a fact in words, not a dash.
        assert "MIGRATED" in screen
        assert "v3 position migrated" in screen
        # BURN: the tri-state headline plus the pipeline's own numbers.
        assert "NOT READY" in screen
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
    This same accumulator now also feeds BURN's own cumulative line, so the
    distinction is checked there too.
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


async def test_hero_burn_ready_flips_between_true_false_and_unknown():
    """``burn_ready`` is tri-state: three renders, never two.

    ``False`` ("not ready yet") and ``None`` ("cannot tell") must not
    collapse into the same word -- the inverse of the rail bug where a dead
    group's ``-- unknown`` and a real "none yet" both read confident and
    green through an outage.
    """
    for ready, expect, forbid in (
        (True, "READY", "NOT READY"),
        (False, "NOT READY", None),
        (None, None, "READY"),
    ):
        widget = SurfHero()
        app = _Harness(widget)
        async with app.run_test(size=(160, 12)) as pilot:
            widget.update_data(**{**_FULL_HERO, "burn_ready": ready})
            await pilot.pause()
            screen = _screen_text(app)
            if expect is not None:
                assert expect in screen, (ready, screen)
            if forbid is not None:
                assert forbid not in screen, (ready, screen)


async def test_hero_pool_venue_both_values_render_distinctly():
    """Both real values the manager emits (v3 pre-migration, v4 post) must
    reach the box, not just the one ``_FULL_HERO`` happens to use.

    ``lp_state`` must NOT be left at ``_FULL_HERO``'s own ``"gone"`` here:
    that renders ``"v3 position migrated"`` in the LP box (see
    ``test_hero_lp_gone_renders_migrated_not_unknown_on_screen``), and that
    string contains the literal substring ``"v3"`` -- so the ``venue ==
    "v3"`` case would pass on the LP box's own leakage even if the POOL box
    rendered nothing resembling ``v3`` at all (a Task 13 review finding).
    ``lp_state="live"`` -- the sibling ``test_hero_owner_changed_is_loud_
    words_not_colour`` fixture, which renders IMD/WETH amounts instead --
    keeps the LP box's text free of both venue words, so this assertion is
    genuinely checking the POOL box alone.
    """
    for venue in ("v3", "v4"):
        widget = SurfHero()
        app = _Harness(widget)
        async with app.run_test(size=(160, 12)) as pilot:
            widget.update_data(**{
                **_FULL_HERO,
                "pool_venue": venue,
                "lp_state": "live",
                "lp_imd": 388_421.0,
                "lp_weth": 142.7067,
            })
            await pilot.pause()
            assert venue in _screen_text(app), venue


async def test_hero_pool_id_source_fallback_warns_on_screen():
    """A fallback pool id must not carry fee/decoy numbers that might be
    somebody else's pool (CLAUDE.md rule 3)."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{
            **_FULL_HERO,
            "pool_fee_bps": None,
            "pool_liquidity_usd": None,
            "decoy_pool_count": None,
            "pool_id_source": "fallback",
        })
        await pilot.pause()
        screen = _screen_text(app)
        assert "pool id unverified" in screen
        assert "1%" not in screen


async def test_hero_owner_changed_is_loud_words_not_colour():
    """lp_owner_ok=False means the LP NFT moved -- the launch precondition."""
    live_lp = {**_FULL_HERO, "lp_state": "live", "lp_imd": 388421.0, "lp_weth": 142.7067}

    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**live_lp, "lp_owner_ok": False})
        await pilot.pause()
        screen = _screen_text(app)
        assert "OWNER CHANGED" in screen
        assert "owner ✓" not in screen
        assert "MIGRATED" not in screen

        # And None is unknown -- neither the checkmark nor the alarm.
        widget.update_data(**{**live_lp, "lp_owner_ok": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "OWNER CHANGED" not in screen
        assert "owner ✓" not in screen
        assert "owner --" in screen


async def test_hero_lp_gone_renders_migrated_not_unknown_on_screen():
    """``lp_state == "gone"`` is a completed migration, read live off-chain --
    it must never render as ``unknown`` (the bug this rebuild fixes)."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "lp_state": "gone",
                              "lp_imd": None, "lp_weth": None, "lp_owner_ok": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "MIGRATED" in screen
        assert "OWNER CHANGED" not in screen


async def test_hero_lp_unread_state_stays_unknown_on_screen():
    """``lp_state is None`` -- nobody answered -- stays the honest dash."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "lp_state": None,
                              "lp_imd": None, "lp_weth": None, "lp_owner_ok": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "MIGRATED" not in screen
        assert "—" in screen


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
        assert "acc 0" not in screen
        assert "stg 0" not in screen
        assert "MIGRATED" not in screen
        # burn_ready is None here, not False -- must not read as "not ready".
        assert "READY" not in screen


async def test_hero_garbage_pool_venue_is_escaped_not_parsed():
    """``pool_venue`` is manager-controlled today, but the render path
    escapes defensively anyway -- the crash would happen inside the message
    pump, well outside any try/except around the refresh call."""
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "pool_venue": "[/x] v5"})
        await pilot.pause()  # the crash would happen inside the message pump
        screen = _screen_text(app)
        assert "v5" in screen


def test_hero_tier_table_is_measured_not_rounded():
    """The thresholds are the widths their own layouts need, in order."""
    from maxpane_dashboard.widgets.surf.hero import (
        COMPACT_WIDTH,
        MINIMAL_WIDTH,
        TIER_WIDTHS,
        TIGHT_WIDTH,
        _tier_for,
    )

    assert COMPACT_WIDTH > TIGHT_WIDTH > MINIMAL_WIDTH
    # ``0`` is "not laid out yet"; ``on_resize`` corrects the guess.
    assert _tier_for(0) == "compact"
    assert _tier_for(COMPACT_WIDTH) == "compact"
    # There is no tier above ``compact``: the ``full`` tier existed only to
    # hold ``· L <liquidity>``, and when that field was dropped it would have
    # rendered identically to its neighbour. A tier that shows exactly what
    # the next one shows is a lie about the ladder, so it went too.
    assert _tier_for(COMPACT_WIDTH + 50) == "compact"
    assert _tier_for(COMPACT_WIDTH - 1) == "tight"
    assert _tier_for(TIGHT_WIDTH) == "tight"
    assert _tier_for(TIGHT_WIDTH - 1) == "minimal"
    assert TIER_WIDTHS == {
        "compact": COMPACT_WIDTH,
        "tight": TIGHT_WIDTH,
        "minimal": MINIMAL_WIDTH,
    }


def test_every_hero_tier_fits_the_width_it_advertises():
    """Render every box in every state at every tier, then *measure* it.

    This is what makes the constants above honest: a copy edit that grows a
    subtitle past its tier fails here rather than reappearing as an ellipsis
    on someone's terminal. Live *numbers* are deliberately out of scope --
    they cannot be shortened without lying, so a quantity that outgrows its
    box lights the marker instead (see the test below).
    """
    from maxpane_dashboard.widgets.markup_safety import visible_len
    from maxpane_dashboard.widgets.surf.hero import TIER_WIDTHS, _supply_lines

    for tier, need in TIER_WIDTHS.items():
        renderings = []
        for venue in ("v3", "v4", None, ""):
            for source in ("hook", "fallback", None):
                for decoy in (0, 37, None):
                    renderings.append(
                        _pool_lines(venue, 10000, 805_927.0, source, decoy, tier)
                    )
        for state in ("live", "gone", None):
            for owner in (True, False, None):
                renderings.append(_lp_lines(state, 388421.0, 142.7067, owner, tier))
        for ready in (True, False, None):
            # 15,745 is the real observed single-event burn (PRD §1); the
            # combined accrued/staged line is the one this box compacts
            # (fmt_compact), unlike LP/SUPPLY's full-precision quantities --
            # see the "why compact" note in ``_burn_lines``'s own docstring.
            for accrued in (0.0, 1_234.56, 15_745.0, None):
                renderings.append(_burn_lines(accrued, 45.0, ready, 15_745.0, tier))
        for burned in (15745.0, 0.0, None):
            renderings.append(_supply_lines(2376731.868679, burned, tier))

        for lines in renderings:
            widest = max(visible_len(line) for line in lines)
            assert widest <= need, (
                f"{tier} tier advertises {need} columns but renders "
                f"{widest}: {[line for line in lines if visible_len(line) == widest]}"
            )


async def test_hero_a_number_too_big_for_its_box_is_announced_not_cut_in_silence():
    """A quantity cannot be tiered, so the box says so instead.

    ``burned 15,74…`` -- a number cut mid-digits with nothing to mark it --
    is the failure this replaces. When even the narrowest copy cannot fit a
    live value, the border carries the marker.
    """
    from maxpane_dashboard.widgets.surf.hero import MINIMAL_WIDTH, WIDEN_HINT

    widget = SurfHero()
    app = _Harness(widget)
    # Four boxes across a 60-column app: ~7 content columns each, far below
    # MINIMAL_WIDTH, so even the shortest copy cannot fit.
    async with app.run_test(size=(60, 12)) as pilot:
        widget.update_data(**_FULL_HERO)
        await pilot.pause()
        assert WIDEN_HINT in _screen_text(app)

    # ...and with room to spare it stays dark.
    widget2 = SurfHero()
    app2 = _Harness(widget2)
    async with app2.run_test(size=(4 * (MINIMAL_WIDTH + 8) + 4, 12)) as pilot:
        widget2.update_data(**_FULL_HERO)
        await pilot.pause()
        assert WIDEN_HINT not in _screen_text(app2)


# ---------------------------------------------------------------------
# SurfSignals
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.markup_safety import visible_len  # noqa: E402
from maxpane_dashboard.widgets.surf.signals import (  # noqa: E402
    DETECTOR_LABELS,
    MIN_DETAIL_COLS,
    RENDER_FAILED_DETAIL,
    SEPARATOR_COLS,
    WIDEN_HINT,
    SurfSignals,
    _cut_detail,
    _fmt_signal_row,
    _head,
    _visible_rows,
)

#: A realistic mixed payload: the 2026-08-07 morning, 12 minutes after the
#: staging mint (ops_eth_token_transfers.json: +114,366.9 IMD OFT-minted to
#: frenpet.eth at 04:21:35) and two hours after the nonce-13 announce post.
#: ``lp``, ``gate``, ``burn`` and ``hot`` are ``ok`` -- deliberately, so this
#: fixture also exercises the quiet-collapse: four rows fold into one line
#: and the other five (two FIRED, two WATCH... see below) keep their own.
_FULL_SIGNALS = {
    "sig_post_state": "fired",
    "sig_post_detail": "#14 · I moved 33 eth to the LP on mainnet",
    "sig_post_age_s": 7200.0,
    "sig_lp_state": "ok",
    "sig_lp_detail": "pos #1167726 liquidity unchanged",
    "sig_lp_age_s": None,
    "sig_gate_state": "ok",
    "sig_gate_detail": "closed · 1/2000 written",
    "sig_gate_age_s": None,
    "sig_deploy_state": "watch",
    "sig_deploy_detail": "frenpet.eth nonce 29→30",
    "sig_deploy_age_s": 900.0,
    "sig_bridge_state": "fired",
    "sig_bridge_detail": "+114,367 IMD minted to frenpet.eth",
    "sig_bridge_age_s": 720.0,
    "sig_burn_state": "ok",
    "sig_burn_detail": "last burn 15,745 IMD",
    "sig_burn_age_s": None,
    "sig_decoy_state": "watch",
    "sig_decoy_detail": "decoy #4 · fee unknown",
    "sig_decoy_age_s": None,
    "sig_burnready_state": "fired",
    "sig_burnready_detail": "burn ready · balance 12,000 IMD",
    "sig_burnready_age_s": 300.0,
    "sig_hot_state": "ok",
    "sig_hot_detail": "5 coins tracked, none hot",
    "sig_hot_age_s": None,
}

#: How many of ``_FULL_SIGNALS``' nine detectors fold: lp, gate, burn, hot.
_FULL_SIGNALS_QUIET_COUNT = 4


async def test_detector_labels_are_the_nine():
    """The label vocabulary is a cross-task interface, pinned in one place.

    The screen tests and the app-level acceptance tests assert these exact
    PRD §3 strings against composited output.  If someone shortens a label
    for width, this goes red *here* -- in the widget module that owns the
    string -- instead of in the tasks that only consume it.
    """
    assert DETECTOR_LABELS == (
        "NEW POST", "LP MOVE", "GATE OPEN", "NEW DEPLOY", "BRIDGE STAGE",
        "BURN", "DECOY POOL", "BURN READY", "HOT COIN",
    )


def test_no_label_is_longer_than_the_old_widest():
    """The head is unshrinkable, so a longer label costs panel width.
    `BRIDGE STAGE` (12) was the widest before and must stay the widest."""
    assert max(len(x) for x in DETECTOR_LABELS) == len("BRIDGE STAGE")


def test_ok_rows_fold_into_one_quiet_line():
    rows = _visible_rows({
        "post": "fired", "lp": "ok", "gate": "ok", "deploy": "ok",
        "bridge": "ok", "burn": "ok", "decoy": "fired", "burnready": "watch",
        "hot": "ok",
    })
    assert "NEW POST" in rows and "DECOY POOL" in rows and "BURN READY" in rows
    assert "6 quiet" in rows


def test_an_unknown_row_never_folds():
    """The rule curator's rail shipped wrong: a dead detector folded in with
    the OK ones reads confident and green through an outage."""
    rows = _visible_rows({
        "post": "ok", "lp": "ok", "gate": None, "deploy": "ok",
        "bridge": "ok", "burn": "ok", "decoy": "ok", "burnready": "ok",
        "hot": "ok",
    })
    assert "GATE OPEN" in rows
    assert "8 quiet" in rows


def test_all_quiet_still_renders_the_panel():
    rows = _visible_rows({k: "ok" for k in
                          ("post", "lp", "gate", "deploy", "bridge", "burn",
                           "decoy", "burnready", "hot")})
    assert "9 quiet" in rows


async def test_signals_fired_rows_carry_state_and_age_in_words():
    """FIRED and WATCH must survive greyscale: the word, the age, the glyph --
    in text -- and stay on their own line rather than folding.
    """
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 16)) as pilot:
        widget.update_data(**_FULL_SIGNALS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "NEW POST FIRED 2h ago" in screen
        assert "BRIDGE STAGE FIRED 12m ago" in screen
        assert "NEW DEPLOY WATCH" in screen
        assert "DECOY POOL WATCH" in screen
        assert "BURN READY FIRED 5m ago" in screen
        # Details ride along on the rows that keep their own line.
        assert "+114,367 IMD minted to frenpet.eth" in screen
        assert "frenpet.eth nonce 29→30" in screen
        # lp, gate, burn and hot are all `ok` in this fixture -- quiet-collapse
        # folds them into one line, so none of their own "... OK" text survives.
        assert "LP MOVE OK" not in screen
        assert "GATE OPEN OK" not in screen
        assert "BURN OK" not in screen
        assert "HOT COIN OK" not in screen
        assert f"{_FULL_SIGNALS_QUIET_COUNT} quiet" in screen


async def test_signals_all_nine_rows_always_render_when_nothing_is_ok():
    """None-state rows are unknown, not OK -- nine rows on screen, no fold."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 16)) as pilot:
        widget.update_data()
        await pilot.pause()
        screen = _screen_text(app)
        for label in DETECTOR_LABELS:
            assert f"{label} --" in screen, label
        # No invented state: nothing fired, nothing ok, nothing folded.
        assert "FIRED" not in screen
        assert "OK" not in screen.replace("SIGNALS", "")
        assert "quiet" not in screen


async def test_signals_fired_without_age_omits_the_age_not_the_state():
    row = _fmt_signal_row("LP MOVE", "fired", "liquidity -37%", None)
    assert "LP MOVE FIRED" in row
    assert "ago" not in row
    assert "-- ago" not in row


async def test_signals_unknown_state_renders_as_unknown_not_ok():
    """A state string the widget doesn't know is unknown -- never OK."""
    row = _fmt_signal_row("NEW POST", "exploded", "detail", 5.0)
    assert "NEW POST --" in row
    assert "OK" not in row and "FIRED" not in row


async def test_signals_hostile_markup_survivor_degrades_only_its_own_row():
    """A detail that clears ``safe_markup`` but still breaks Textual's own
    markup parser must not take the whole panel down.

    ``]][[/][/ malformed`` escapes cleanly through ``rich.markup.escape``
    (the primitive ``safe_markup`` wraps -- it turns the brackets into
    ``\\[``/``\\]`` so Rich's own parser reads it literally) but Textual's
    own ``textual.markup`` parser is stricter and still raises
    ``MarkupError: closing tag '[/malformed]' does not match any open tag``
    on the *escaped* string -- verified directly against this project's
    pinned Textual (8.1.1) before writing this test. The announce channel
    this detail quotes is attacker-writable (PRD §6.4), so this shape is
    reachable with real chain data, not a synthetic stress string.
    """
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 16)) as pilot:
        widget.update_data(
            **{**_FULL_SIGNALS, "sig_post_detail": "]][[/][/ malformed"}
        )
        await pilot.pause()
        screen = _screen_text(app)
        # The poisoned row: true state still shows (never stale, never the
        # dead-detector dash -- the read succeeded, only the detail broke
        # rendering), detail replaced with an explicit, visibly-wrong marker.
        assert "NEW POST FIRED 2h ago" in screen
        assert RENDER_FAILED_DETAIL in screen
        assert "malformed" not in screen
        assert "NEW POST --" not in screen
        # This is the assertion that actually matters: every other *visible*
        # detector still updated normally in the *same* refresh cycle -- one
        # poisoned row cannot freeze the panel at stale content.
        assert "BRIDGE STAGE FIRED 12m ago" in screen
        assert "+114,367 IMD minted to frenpet.eth" in screen
        assert "NEW DEPLOY WATCH" in screen
        assert "frenpet.eth nonce 29→30" in screen
        assert "DECOY POOL WATCH" in screen
        assert "BURN READY FIRED 5m ago" in screen
        # The folded rows are unaffected by the poisoned FIRED row -- still
        # one summary line, not frozen or dropped.
        assert f"{_FULL_SIGNALS_QUIET_COUNT} quiet" in screen


async def test_signals_detail_is_escaped_and_newline_flattened():
    """Detail strings quote announce text -- attacker-writable (PRD §6.4)."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_SIGNALS,
                "sig_post_detail": "[/x] pwn\nsecond line",
            }
        )
        await pilot.pause()  # a MarkupError would raise inside the pump here
        screen = _screen_text(app)
        assert "pwn second line" in screen  # flattened, rendered literally


def test_signals_head_is_never_wider_than_the_panel_it_gets():
    """The unshrinkable part of a row must fit the pinned full-layout width.

    ``SurfSignals`` is the 2fr of a 3fr:2fr hero row, so it gets ``2W/5 - 4``
    content columns -- 53 at the pinned ``W = 143`` -- and ``padding: 0 1``
    on the body rows leaves 51.  The head is glyph + full PRD §3 label +
    state word + age; if *that* stops fitting, the panel genuinely needs a
    wider terminal.  While it fits, the detail is truncated to what is left
    and the marker stays dark -- which is what keeps ``‹ widen`` meaningful.
    """
    available = 2 * 143 // 5 - 4 - 2  # == 51
    worst = max(
        visible_len(_head(label, state, age))
        for label in DETECTOR_LABELS
        for state in ("fired", "watch", "ok", None, "exploded")
        for age in (None, 45.0, 7200.0, 100 * 86400.0)
    )
    # "  ▶ BRIDGE STAGE FIRED 100d ago" -- the widest head this widget can
    # build.  The realistic fired row ("... 12m ago") is 30.
    assert worst == 31, worst
    # Head + separator + a usable detail stub still fits the real panel.
    assert worst + SEPARATOR_COLS + MIN_DETAIL_COLS <= available


async def test_signals_long_detail_is_truncated_and_does_not_light_the_marker():
    """A 100-char detail in a 60-column panel: label intact, tail cut, no widen.

    This is the FWA buy-gate lesson.  WP2 builds details up to
    ``DETAIL_LIMIT = 48`` and its relaxed-FIRED form composes an even longer
    ``... · last: ...`` string, so real rows are 80-105 columns against a
    51-column panel.  If the *whole row* set ``clipped``, ``‹ widen`` would
    be lit during healthy operation and would stop meaning anything.
    """
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(60, 14)) as pilot:
        widget.update_data(**{**_FULL_SIGNALS, "sig_post_detail": "x" * 100})
        await pilot.pause()
        screen = _screen_text(app)
        assert "NEW POST FIRED 2h ago" in screen   # head survives whole
        assert "…" in screen                       # detail was cut, visibly
        assert "x" * 40 not in screen              # and really cut
        assert WIDEN_HINT not in screen            # a fitted head is not clipped


async def test_signals_narrow_width_announces_clipping():
    """``‹ widen`` fires when the *head* cannot fit -- 26 columns is below 30."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(26, 14)) as pilot:
        widget.update_data(**_FULL_SIGNALS)
        await pilot.pause()
        assert WIDEN_HINT in _screen_text(app)

    app2 = _Harness(SurfSignals())
    async with app2.run_test(size=(120, 14)) as pilot:
        app2._widget.update_data(**_FULL_SIGNALS)
        await pilot.pause()
        assert WIDEN_HINT not in _screen_text(app2)


#: The real bridge-row detail, whose quantity the old cut bisected.
_BRIDGE_DETAIL = "mint 114,367 IMD → frenpet.eth"


def test_the_detail_cut_never_lands_inside_a_number():
    """Every budget, one real detail: no proper prefix of the figure survives.

    Swept rather than spot-checked, because the defect was one specific budget
    landing one specific way -- ``mint 114,…`` at 100 terminal columns. The
    property is the fix: at *no* budget may the panel show part of a number
    and stop, because 114 reads as a different quantity from 114,367 and
    nothing on the row marks the cut.
    """
    partials = tuple("114,367"[:cut] for cut in range(1, len("114,367")))
    for budget in range(MIN_DETAIL_COLS, len(_BRIDGE_DETAIL) + 4):
        cut = _cut_detail(_BRIDGE_DETAIL, budget)
        assert len(cut) <= max(budget, 0), (budget, cut)
        assert cut != "…", f"a bare ellipsis at budget {budget}"
        if cut.endswith("…"):
            assert not cut[:-1].endswith(partials), (
                f"budget {budget} rendered {cut!r}, which is 114,367 cut "
                "through the middle"
            )
    # The sweep is only worth something if it covers the budgets that used to
    # bisect the figure -- one dropping a digit, one dropping the comma.
    assert _cut_detail(_BRIDGE_DETAIL, 10) == "mint…"
    assert _cut_detail(_BRIDGE_DETAIL, 9) == "mint…"


def test_the_detail_cut_keeps_a_number_that_fits():
    """The other direction: an intact quantity is never shed for the guard.

    ``_cut_detail`` fires only on a cut *through* digits. A cut that lands
    after the figure keeps it whole -- without this, "drop every trailing
    number" would satisfy the sweep above while costing the reader figures
    that fitted.
    """
    detail = "supply flat · last: burn 15,745 IMD"
    assert _cut_detail(detail, len(detail)) == detail          # nothing to do
    assert _cut_detail(detail, 32) == "supply flat · last: burn 15,745…"
    # ...and one column narrower the cut falls inside the figure, so it goes.
    assert _cut_detail(detail, 31) == "supply flat · last: burn…"


def test_signals_row_truncation_is_pure_and_keeps_the_head():
    """``available`` drives the cut; ``None`` means "width unknown, don't cut".

    The long payload is WP2's relaxed-FIRED composition shape -- the one that
    deliberately blows past ``DETAIL_LIMIT`` -- so this is the real input, not
    a stress string.
    """
    long_detail = "nonce 13 · no new post · last: " + "y" * 60
    full = _fmt_signal_row("NEW POST", "ok", long_detail, None)
    assert long_detail in full          # unsized widget: never truncate

    cut = _fmt_signal_row("NEW POST", "ok", long_detail, None, available=40)
    assert "NEW POST OK" in cut         # head intact
    assert "…" in cut                   # tail cut, visibly
    assert visible_len(cut) <= 40

    # Too narrow for a usable detail: the head renders alone, never a bare "…".
    head_only = _fmt_signal_row(
        "BRIDGE STAGE", "fired", long_detail, 7200.0, available=31
    )
    assert "BRIDGE STAGE FIRED 2h ago" in head_only
    assert "…" not in head_only


# ---------------------------------------------------------------------
# SurfMarket
# ---------------------------------------------------------------------

from maxpane_dashboard.widgets.surf.market import SurfMarket  # noqa: E402

#: dexscreener_imd.json / dexscreener_fp.json, fetched 2026-08-08:
#: IMD $0.7074 +30.89% vol $244,178 pool $548,701.21; FP $0.7274 →
#: parity (0.7074/0.7274 − 1)·100 = −2.75%.  The supply series is the real
#: burn staircase: pre-07-31 supply, the 31,064 burn, the 15,745 burn, then
#: the 08-07 bridge-in mint of 114,366.9 (imd_token.json end state).
_SUPPLY_SERIES = [
    [1784000000, 2309194.0],
    [1785467000, 2278130.0],
    [1785903575, 2262384.97],
    [1786076495, 2376731.868679],
]
_PRICE_SERIES = [[1785900000 + i * 3600, 0.53 + i * 0.004] for i in range(48)]

_FULL_MARKET = {
    "imd_price_usd": 0.7074,
    "imd_change_24h_pct": 30.89,
    "imd_vol_24h_usd": 244178.0,
    "pool_liquidity_usd": 548701.21,
    "fp_price_usd": 0.7274,
    "parity_pct": -2.75,
    "supply_series": _SUPPLY_SERIES,
    "price_series": _PRICE_SERIES,
}


async def test_market_full_payload_renders_all_numbers():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        screen = _screen_text(app)
        assert "IMD $0.7074" in screen        # the figure is named, not bare
        assert "▲ +30.89%" in screen          # glyph AND sign, not colour alone
        assert "vol 24h $244.2K" in screen
        assert "pool $548.7K" in screen
        # Two spaces after ``FP``: the label is padded to ``IMD``'s width so
        # both figures share a column.  Spelled out rather than derived from
        # ``market.ROW_LABELS`` -- a re-worded label should redden this and be
        # re-typed on purpose.  That the padding is *computed* and not a magic
        # space is a separate claim, pinned by
        # ``test_market_the_price_and_the_fp_figure_start_in_one_column``.
        assert "FP  $0.7274" in screen
        assert "parity ▼ -2.75%" in screen    # negative: IMD below FP


async def test_market_supply_sparkline_shows_the_burn_steps():
    """The supply bar must actually vary -- burns step down, mints step up."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        screen = _screen_text(app)
        supply_line = next(l for l in screen.splitlines() if "supply" in l)
        # More than one distinct block char = the staircase is visible.
        blocks = {c for c in supply_line if c in "▁▂▃▄▅▆▇█"}
        assert len(blocks) >= 2, supply_line
        assert "2.4M" in supply_line          # the live end-state, labelled


async def test_market_short_or_missing_series_say_waiting():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**{**_FULL_MARKET, "supply_series": [], "price_series": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert screen.count("waiting for data") == 2


async def test_market_no_args_and_all_none_render_dashes_never_zero():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data()
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        screen = _screen_text(app)
        assert "$0.00" not in screen
        assert "+0.00%" not in screen
        assert "--" in screen


async def test_market_malformed_series_points_are_skipped_not_fatal():
    """A single null in a persisted series must not kill the panel."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_MARKET,
                "supply_series": [None, [1, None], "junk", *_SUPPLY_SERIES],
            }
        )
        await pilot.pause()
        screen = _screen_text(app)
        assert "2.4M" in screen  # the valid points still render


# -- SurfMarket: the two-column layout and the bridge block -------------
#
# The panel is ~77 columns in the bottom row at 143 and its left-hand fields
# use barely 31 of them, so the sparklines moved up beside the rows they
# belong to (price with price, supply with the IMD-token figures) and the
# freed rows carry what the panel had never said out loud: IMD *is* FP,
# bridged, and the parity percentage above is the spread between the two
# sides of one asset.


def _lines(app) -> list[str]:
    """Composited rows, right-trimmed -- the panel is padded to the width."""
    return [line.rstrip() for line in _screen_text(app).splitlines()]


def _line_with(app, needle: str) -> str:
    return next(line for line in _lines(app) if needle in line)


# -- SurfMarket: the price row's label, its window, and the FP row --------
#
# The price row was the one line on the whole surf screen whose number was
# unnamed -- ``$0.7074  ▲ +30.89% 24h`` -- sitting directly above a row that
# says ``FP`` out loud.  It now takes that row's shape: a label, a ``·``
# join, and a labelled change, with the two figures in one column.
#
# ``±`` is deliberate and is not decoration: it reads exactly as the ``+/-``
# the wording was asked for and costs two columns fewer on the panel that
# binds the whole screen's width.


async def test_market_price_row_names_its_figure_and_its_window():
    """``IMD $0.7074 · 24h ±  ▲ +30.89%`` -- composited, not the markup.

    Two spaces after ``±``: the window labels are padded to a common width
    so the glyphs line up with ``parity``'s one row down, the same way the
    figures above them are padded to one column. Spelled out here rather
    than built from the constant, so a change to the padding has to be a
    deliberate edit to this string.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        assert "IMD $0.7074 · 24h ±  ▲ +30.89%" in _line_with(app, "$0.7074")


async def test_market_the_change_and_parity_glyphs_start_in_one_column():
    """``24h ±`` and ``parity`` are padded to a common width, not hand-spaced.

    The literals in the tests either side of this one pin *a* number of
    spaces; none of them pins the property those spaces exist for, which is
    that the two rows' ``▲``/``▼`` land in the same column. This measures
    that in composited output, then re-words one label in memory and
    measures again -- a hand-typed gap would keep the literals green while
    the two glyphs drifted apart, which is exactly how the figures above
    them were misaligned before ``_labelled`` was derived.
    """
    from maxpane_dashboard.widgets.surf import market as M

    def _glyph_col(line: str) -> int:
        """Column of whichever direction glyph this row happens to carry.

        The two rows do not always point the same way -- the fixture's 24h
        change is up and its parity is down -- so pinning one glyph would
        make this test depend on the payload rather than on the padding.
        """
        cols = [line.index(g) for g in ("▲", "▼", "●") if g in line]
        assert cols, f"no direction glyph in {line!r}"
        return min(cols)

    async def glyph_columns(app):
        return (
            _glyph_col(_line_with(app, "$0.7074")),
            _glyph_col(_line_with(app, "parity")),
        )

    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        change_col, parity_col = await glyph_columns(app)
        assert change_col == parity_col, (
            f"the 24h glyph is at column {change_col} and parity's at "
            f"{parity_col}; the two windows are not padded to one width"
        )

        original = M.PARITY_LABEL
        try:
            M.PARITY_LABEL = "parity spread"
            widget.update_data(**_FULL_MARKET)
            await pilot.pause()
            change_col, parity_col = await glyph_columns(app)
            assert change_col == parity_col, (
                "a longer parity label left the 24h window behind: the "
                "padding is not derived from both labels"
            )
        finally:
            M.PARITY_LABEL = original


async def test_market_price_row_keeps_its_shape_when_the_change_turns_or_fails():
    """Down, flat and unread render the same row with the same label.

    The ``None`` case is the one that matters: a failed read must still say
    *what* could not be read rather than leaving a bare label -- and it must
    never fall back to a zero, which on a 24h change reads as "unmoved".
    """
    expected = {
        -3.80: "IMD $0.7074 · 24h ±  ▼ -3.80%",
        0.0: "IMD $0.7074 · 24h ±  ● +0.00%",
        None: "IMD $0.7074 · 24h ±  --",
    }
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        for change, row in expected.items():
            widget.update_data(**{**_FULL_MARKET, "imd_change_24h_pct": change})
            await pilot.pause()
            assert row in _line_with(app, "$0.7074"), (
                f"a 24h change of {change!r} renders "
                f"{_line_with(app, '$0.7074')!r}"
            )


async def test_market_the_price_and_the_fp_figure_start_in_one_column():
    """``IMD`` is three characters and ``FP`` two -- and it must not show.

    The padding is **derived from the labels**, so re-wording either one
    moves both rows together.  That is what the second half asserts: a
    hand-typed two-space gap aligns the shipped wording perfectly and drifts
    the instant a label changes length, and a test spelling out ``"FP  "``
    would go on passing while the columns came apart.
    """
    from maxpane_dashboard.widgets.surf import market as market_mod

    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        assert _line_with(app, "$0.7074").index("$0.7074") == _line_with(
            app, "$0.7274"
        ).index("$0.7274")

        original = market_mod.ROW_LABELS
        try:
            market_mod.ROW_LABELS = {**original, "imd": "IMDX"}
            widget.update_data(**_FULL_MARKET)
            await pilot.pause()
            price_row = _line_with(app, "$0.7074")
            assert "IMDX $0.7074" in price_row, price_row
            assert price_row.index("$0.7074") == _line_with(app, "$0.7274").index(
                "$0.7274"
            ), (
                f"a one-character-longer label broke the column:\n{price_row}\n"
                f"{_line_with(app, '$0.7274')}"
            )
        finally:
            market_mod.ROW_LABELS = original


async def test_market_both_labelled_rows_survive_a_failed_read():
    """``IMD --`` over ``FP  --``: still labelled, still aligned, never 0."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**{**_FULL_MARKET, "imd_price_usd": None,
                              "fp_price_usd": None, "parity_pct": None})
        await pilot.pause()
        rows = [r for r in _lines(app) if r.strip()]
        price_row = next(r for r in rows if "24h" in r)
        fp_row = next(r for r in rows if "parity" in r)
        assert "IMD --" in price_row, price_row
        assert "FP  --" in fp_row, fp_row
        assert price_row.index("--") == fp_row.index("--")
        assert "$0.00" not in "\n".join(rows)


async def test_market_puts_each_sparkline_on_the_row_it_belongs_to():
    """Price beside the price, supply beside the volume/pool figures.

    Both sparklines used to own a row of their own below rows that ended at
    column 31 of 75, which is the free space this restructure spends.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        price_row = _line_with(app, "$0.7074")
        token_row = _line_with(app, "vol 24h")
        assert "price" in price_row
        assert {c for c in price_row} & set("▁▂▃▄▅▆▇█"), price_row
        assert "supply" in token_row and "2.4M" in token_row
        # ...and neither sparkline has a row to itself any more.
        assert not [l for l in _lines(app) if l.strip().startswith(("price", "supply"))]


async def test_market_sparklines_start_at_a_column_derived_from_the_rows():
    """One column for both, and it follows the rendered left-hand fields.

    A pinned constant would align the two sparklines just as well until a
    field grew past it -- and then it would collide with, or ellipsise, the
    figure it was meant to sit beside.  So the widening half is the half
    that bites: a wider FP row must push both sparklines right together.

    The **graphics** are checked as well as the labels.  ``price`` and
    ``supply`` are six characters apart in length, so two labels starting in
    one column says nothing about where the bars start -- dropping the label
    padding shifts them a column apart and every label assertion stays green.
    (The two bars do not *begin* together: a series shorter than the bar is
    right-aligned inside it, which is the point.  What must coincide is the
    column the bar field starts at.)
    """
    bars = set("▁▂▃▄▅▆▇█")

    def _bar_start(line: str) -> int:
        return next(i for i, ch in enumerate(line) if ch in bars)

    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        price_line, token_line = _line_with(app, "$0.7074"), _line_with(app, "vol 24h")
        narrow = price_line.index("price")
        assert narrow == token_line.index("supply")

        pad = _market._LABEL_WIDTH + 1
        assert price_line.index("price") + pad == token_line.index("supply") + pad
        assert _bar_start(price_line) == price_line.index("price") + pad, (
            "the price bar does not start where the padded label leaves it -- "
            "the two bar fields are a column apart"
        )

        # A far longer left-hand field on the FP row -- absurd as a price,
        # ordinary as a layout input, and the one thing a constant cannot
        # survive.
        widget.update_data(**{**_FULL_MARKET, "fp_price_usd": 123456789.12})
        await pilot.pause()
        wide = _line_with(app, "$0.7074").index("price")
        assert wide == _line_with(app, "vol 24h").index("supply")
        assert wide > narrow, (
            f"the sparkline column stayed at {narrow} while the FP row grew "
            "past it -- it is a constant, not a measurement"
        )


async def test_market_blank_row_separates_the_token_figures_from_the_bridge():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(80, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        lines = _lines(app)
        fp_row = next(i for i, l in enumerate(lines) if "FP  $0.7274" in l)
        assert lines[fp_row - 1].strip() == "", lines
        assert lines[fp_row - 2].strip() != "", "the blank is padding, not a seam"


async def test_market_bridge_block_names_the_mechanism_and_the_live_spread():
    """One token on two chains, which side is rich, and by how much.

    Every number is derived from the payload's own prices: the dollar figure
    is recomputed here from the two prices rather than spelled out, so a
    widget that printed a remembered spread would redden.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        panel = _screen_text(app)
        assert "IMD is FP bridged 1:1 from Base" in panel
        spread = abs(_FULL_MARKET["imd_price_usd"] - _FULL_MARKET["fp_price_usd"])
        assert f"${spread:.4f}" in panel                      # $0.0200/token
        assert "under FP" in panel                            # IMD is the cheap side
        assert "gross" in panel                               # fees are not in it
        assert "bridges" in panel                             # the flow that closes it


async def test_market_bridge_block_follows_the_side_the_live_prices_put_rich():
    """The direction is read off the prices, not written into the widget.

    ``parity_pct`` is pinned to the analytics definition it is computed with
    upstream -- ``(imd/fp - 1) * 100`` -- so this test states the sign once,
    in the module that owns it, and asserts the panel tells the same story
    both ways round.  A hardcoded "IMD bridges back" passes the cheap half
    and fails the rich one.
    """
    from maxpane_dashboard.analytics.surf_signals import parity_pct

    fp = _FULL_MARKET["fp_price_usd"]
    cheap = {**_FULL_MARKET, "parity_pct": parity_pct(0.7074, fp)}
    rich = {**_FULL_MARKET, "imd_price_usd": 0.7674,
            "parity_pct": parity_pct(0.7674, fp)}
    assert cheap["parity_pct"] < 0 < rich["parity_pct"]

    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(**cheap)
        await pilot.pause()
        panel = _screen_text(app)
        assert "under FP" in panel
        assert "IMD bridges back" in panel      # burn on this side lifts IMD

        widget.update_data(**rich)
        await pilot.pause()
        panel = _screen_text(app)
        assert "over FP" in panel
        assert "FP bridges in" in panel         # new supply on the rich side
        assert "IMD bridges back" not in panel


async def test_market_bridge_block_is_explicitly_unavailable_without_parity():
    """No spread, no direction, no stale number -- and it says why in words.

    ``parity_pct`` is ``None`` whenever either price read fails, and a block
    about a spread that cannot be measured must not fall back to a blank
    right-hand column (indistinguishable from "at parity") or to the last
    good figure presented as live.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)          # a good render first...
        await pilot.pause()
        widget.update_data(**{**_FULL_MARKET, "parity_pct": None})
        await pilot.pause()
        panel = _screen_text(app)
        assert "spread unavailable" in panel
        assert "IMD is FP bridged 1:1 from Base" in panel   # not a market read
        for stale in ("under FP", "over FP", "bridges back", "bridges in"):
            assert stale not in panel, f"{stale!r} survived the failed read"

        # ...and the same with nothing at all in the payload.
        widget.update_data(**_none_payload(widget))
        await pilot.pause()
        panel = _screen_text(app)
        assert "spread unavailable" in panel
        assert "$0.00" not in panel


async def test_market_never_shows_a_parity_the_prices_could_not_produce():
    """A parity beside ``⚠ spread unavailable`` is a stale number shown live.

    ``parity_pct`` and the two prices are three separate payload keys, so a
    caller can hand this widget a percentage with no prices behind it -- a
    recompute that outlived its inputs, or a cache read that half-succeeded.
    The bridge block gates on all three; the parity cell must gate on the
    same three, or the panel states a spread on the same screen as the
    warning that no spread could be read.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        for missing in ("imd_price_usd", "fp_price_usd"):
            widget.update_data(**{**_FULL_MARKET, missing: None})
            await pilot.pause()
            panel = _screen_text(app)
            assert "spread unavailable" in panel, missing
            assert "-2.75%" not in panel, (
                f"{missing} could not be read, yet the panel states a parity:"
                f"\n{panel}"
            )
            assert "parity --" in panel, panel


async def test_market_names_no_rich_side_a_rendered_figure_does_not_show():
    """A direction is only named when the number on screen shows it.

    ``0.727400001`` against ``0.7274`` is a gap of 1e-9: ``fmt_price`` renders
    it ``$0.000000`` and the parity renders ``+0.00%``, so naming a rich side
    beside them is a claim neither figure supports -- the same defect shape as
    a zero standing in for a failed read.  Exact ``== 0`` is what let it
    through: float subtraction of two live prices lands on zero almost never.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    fp = _FULL_MARKET["fp_price_usd"]
    imd = fp + 1e-9
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_MARKET,
                "imd_price_usd": imd,
                "parity_pct": (imd / fp - 1) * 100,
            }
        )
        await pilot.pause()
        panel = _screen_text(app)
        assert "IMD level with FP" in panel, panel
        assert "parity ● +0.00%" in panel, panel        # neutral glyph, not ▲
        for invented in ("over FP", "under FP", "bridges in", "bridges back"):
            assert invented not in panel, f"{invented!r} on a gap of 1e-9:\n{panel}"
        assert "$0.000000" not in panel, panel


async def test_market_bridge_block_says_level_rather_than_a_zero_spread():
    """Two identical prices are the one case with no rich side to name.

    ``fmt_price(0)`` is ``$0.00``, and "IMD $0.00 under FP" would invent a
    direction out of a spread that does not exist -- the same class of
    statement as a dead feed rendering ``0``.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        fp = _FULL_MARKET["fp_price_usd"]
        widget.update_data(**{**_FULL_MARKET, "imd_price_usd": fp, "parity_pct": 0.0})
        await pilot.pause()
        panel = _screen_text(app)
        assert "level with FP" in panel
        assert "$0.00 " not in panel
        for direction in ("bridges back", "bridges in"):
            assert direction not in panel


def test_market_epsilons_are_the_rounding_boundaries_of_their_own_formatters():
    """Both thresholds are render boundaries, so pin them to what renders.

    Written as "just below shows nothing, just above shows something" rather
    than against the literals themselves: a test comparing ``_GAP_EPSILON``
    with ``5e-7`` would pass through any change to ``fmt_price``'s precision
    bands, which is the thing that decides where the boundary actually is.
    """
    from maxpane_dashboard.widgets.surf.market import (
        _GAP_EPSILON,
        _PARITY_EPSILON,
        _fmt_parity,
    )

    assert set(_fmt.fmt_price(_GAP_EPSILON * 0.9)) <= set("$0.")
    assert _fmt.fmt_price(_GAP_EPSILON * 1.1).strip("$0.") != ""

    assert "0.00%" in _fmt_parity(_PARITY_EPSILON * 0.9)
    assert "0.00%" not in _fmt_parity(_PARITY_EPSILON * 1.1)


async def test_market_bridge_copy_never_advises_a_transaction():
    """MaxPane is read-only by construction: it has no signer to advise for.

    The block describes a state and the flow that would close it. Anything
    imperative, or anything implying a payoff, is a different product.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        for payload in (_FULL_MARKET, {**_FULL_MARKET, "imd_price_usd": 0.7674}):
            widget.update_data(**payload)
            await pilot.pause()
            panel = _screen_text(app).lower()
            for banned in (
                "buy", "sell", "swap", "trade", "profit", "arb",
                "opportunity", "should", "you ", "free", "risk-free",
            ):
                assert banned not in panel, f"the panel says {banned!r}"


# -- SurfMarket: the ‹ widen tiers --------------------------------------
#
# The panel's rows are ``Static``s at ``text-overflow: ellipsis``, so a row
# that does not fit is cut with a visible ``…``.  Until 2026-08-11 nothing in
# the *title* said so -- the half of the house contract this panel had no
# machinery for at all, deferred as Minor by review while its widest row was
# ~33 columns and reopened when the sparkline pairing and the bridge block
# took that row to 71.
#
# Everything below reads the composited panel.  The tier widths are
# **measured off the widget**, never written down: the fields are live
# numbers, so a payload with a sub-cent price moves every threshold and a
# pinned 71 would quietly stop being the truth.

from maxpane_dashboard.widgets.markup_safety import visible_len  # noqa: E402
from maxpane_dashboard.widgets.surf import market as _market  # noqa: E402


def _tier_width(tier: str, payload: dict) -> int:
    """Widest rendered row of *payload* at *tier* -- the width it needs.

    Derived from the widget's own row builder, which is also what
    ``update_data`` paints, so this helper cannot drift away from the render
    the way a table of literals would.
    """
    parts = _market._parts(**payload)
    return max(visible_len(line) for line in _market._lines_for(tier, parts))


def _panel_rows(app) -> list[str]:
    """Composited, right-trimmed, blank rows dropped."""
    return [line for line in _lines(app) if line.strip()]


async def _render_at(payload: dict, line_width: int) -> tuple[list[str], str]:
    """``(rows, title)`` composited with the panel exactly *line_width* wide.

    The widget is the only child of a bare harness, so its content box is the
    app's width and one row of it is that minus the ``padding: 0 1`` on the
    row ``Static``s -- i.e. ``_line_width() == width - 2``.  Asserted here
    rather than assumed, because every threshold below is expressed in the
    widget's own units and an off-by-two would move all of them together and
    still pass.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(line_width + 2, 14)) as pilot:
        widget.update_data(**payload)
        await pilot.pause()
        assert widget._line_width() == line_width
        rows = _panel_rows(app)
        return rows, rows[0]


async def test_market_tier_budget_matches_what_it_actually_renders():
    """The trap ``widgets/surf/nft.py`` documents, closed structurally.

    A tier budget measured against a different string than the one painted
    picks a tier by one width and paints another -- it clips with the marker
    dark.  Here the measured object *is* the painted object
    (``_tier_for`` lays each candidate out with ``_lay_out`` and takes
    ``visible_len`` of the result, and ``_render_view`` paints that same
    list), and this is what pins the two together end to end: at exactly the
    width each tier says it needs, the composited panel carries that tier's
    marker and **no** ``…``.
    """
    for tier in _market.TIERS:
        width = _tier_width(tier, _FULL_MARKET)
        rows, title = await _render_at(_FULL_MARKET, width)
        assert "…" not in "\n".join(rows), (
            f"tier {tier} says it fits in {width} columns and is cut there:\n"
            + "\n".join(rows)
        )
        hint = _market.WIDEN_HINTS[tier]
        if hint:
            assert hint in title, (
                f"at {width} columns the panel renders the {tier} tier and "
                f"its title says {title!r}"
            )
        else:
            assert "widen" not in title, title
        # ...and every row really is inside the panel, not merely uncut.
        assert max(len(r) for r in rows) <= width + 2


async def test_market_drops_to_the_next_tier_one_column_below_each_threshold():
    """The other direction: a tier's width is *tight*, not generous.

    Without this every threshold could be padded by ten columns and the tests
    above would all still pass -- the panel would simply shed a field earlier
    than it had to, silently, for the rest of the widget's life.
    """
    widths = [(tier, _tier_width(tier, _FULL_MARKET)) for tier in _market.TIERS]
    for (tier, width), (next_tier, _next_width) in zip(widths, widths[1:]):
        _rows, title = await _render_at(_FULL_MARKET, width - 1)
        expected = _market.WIDEN_HINTS[next_tier]
        assert expected in title, (
            f"one column below {tier}'s {width} the panel should be at "
            f"{next_tier}; its title reads {title!r}"
        )


async def test_market_widen_hints_all_fit_beside_the_title_at_their_own_tier():
    """No hint may be a dead string, permanently replaced by ``SHORT_HINT``.

    Each hint has to fit beside a 10-column title inside a panel that is *at
    most* as wide as the tier that triggered it, which is 21 columns of room
    at ``minimal``.  A wording that never fits is worse than a terse one: the
    user gets ``‹ widen`` and the field name is written down nowhere.
    """
    for tier in _market.TIERS:
        hint = _market.WIDEN_HINTS[tier]
        if not hint:
            continue
        width = _tier_width(tier, _FULL_MARKET)
        _rows, title = await _render_at(_FULL_MARKET, width)
        assert hint in title, (
            f"{tier}'s hint is {len(hint)} columns and its panel is {width}: "
            f"it degrades to {_market.SHORT_HINT!r} at its own tier"
        )


#: What each hint's wording claims went, as the string that has to be gone
#: from the body for the claim to be true.  A hint is free prose, so nothing
#: connected it to the render: ``WIDEN_HINTS["minimal"] = "‹ widen: pool"``
#: named a field that never sheds and left all 21 market tests green.
_HINT_CLAIMS: dict[str, tuple[tuple[str, str], ...]] = {
    "compact": (("24h volume", "vol 24h"), ("bridge flow", "gap narrows")),
    "narrow": (("FP price", "FP  $0.7274"), ("price bar", "▁▁▁▂")),
    "minimal": (("$ spread", "under FP"), ("bar", "▃▁▁█")),
    "bare": (("bridge", "IMD is FP bridged 1:1 from Base"),),
}


async def test_market_each_widen_hint_names_a_field_that_actually_went():
    """The marker's job is to say *what* went; nothing checked that it did.

    Both directions per claim: the wording is in the hint (so a rewritten
    hint reddens here rather than silently describing something else), and
    the thing it names is off the panel at that tier (so a hint can never
    advertise a field the user is looking at).
    """
    assert set(_HINT_CLAIMS) == {t for t in _market.TIERS if _market.WIDEN_HINTS[t]}
    for tier, claims in _HINT_CLAIMS.items():
        hint = _market.WIDEN_HINTS[tier]
        rows, _title = await _render_at(_FULL_MARKET, _tier_width(tier, _FULL_MARKET))
        body = "\n".join(rows[1:])          # not the title: it *is* the hint
        for phrase, evidence in claims:
            assert phrase in hint, f"{tier}'s hint no longer says {phrase!r}"
            assert evidence not in body, (
                f"{tier}'s hint offers {phrase!r} for widening, but it is on "
                f"screen already:\n{body}"
            )


#: Which shed field each claim above is *about*, so the claims can be checked
#: for completeness and not merely for truth.  Keyed by the field name in the
#: widget's ladder; the value is the claim's phrase in :data:`_HINT_CLAIMS`.
#:
#: The gap this closes: ``_HINT_CLAIMS`` asserted every claim was true and
#: never that every loss was claimed, so ``minimal`` shed the ``$`` spread
#: *and* the supply sparkline while naming one of them, and all 21 market
#: tests stayed green.  A hint that names half of what went is the silent
#: clipping this ladder exists to replace.
_CLAIMED_FIELD: dict[str, str] = {
    "vol": "24h volume",
    "flow": "bridge flow",
    "fp": "FP price",
    "price_bar": "price bar",
    "spread": "$ spread",
    "supply_bar": "bar",
    "mechanism": "bridge",
}


def _step_losses() -> dict[str, frozenset[str]]:
    """What each tier sheds **at its own step**, from the test-owned ladder.

    Differenced from :data:`_EXPECTED_LADDER` rather than read out of
    ``market._TIER_STEPS``: the widget's steps are the thing under test, and
    a test that derived them from the widget would compare the ladder with
    itself and pin nothing.
    """
    out: dict[str, frozenset[str]] = {}
    previous: frozenset[str] = frozenset()
    for tier, cumulative in _EXPECTED_LADDER:
        out[tier] = cumulative - previous
        previous = cumulative
    return out


async def test_market_every_tier_names_every_field_it_sheds():
    """No tier may drop a labelled field and leave it out of its own hint.

    The other half of the test above, and the one that bites when the ladder
    grows: a field added to a tier's step with no wording in
    :data:`_CLAIMED_FIELD` fails here, and a wording that never reaches the
    hint fails too.  Earlier tiers' losses are deliberately *not* required --
    at 21 columns ``minimal`` cannot restate four fields, and a user narrows
    through the wider titles that named them -- so this asserts the step, not
    the cumulative set.
    """
    losses = _step_losses()
    assert set(losses) == set(_market.TIERS)
    assert losses["full"] == frozenset(), "the widest tier sheds nothing"

    for tier, fields in losses.items():
        hint = _market.WIDEN_HINTS[tier]
        if not fields:
            assert not hint, f"{tier} sheds nothing but advertises {hint!r}"
            continue
        assert hint, f"{tier} sheds {sorted(fields)} and says nothing"
        for field in fields:
            phrase = _CLAIMED_FIELD.get(field)
            assert phrase, (
                f"{tier} sheds {field!r} and no wording is recorded for it -- "
                "add one here and to the hint, or the field goes unnamed"
            )
            assert phrase in hint, (
                f"{tier} sheds {field!r} but its hint {hint!r} never names "
                f"it ({phrase!r}) -- the column went silently"
            )
            # ...and the wording is one the truth test above also checks, so
            # a phrase cannot be invented here to satisfy this test alone.
            assert any(
                phrase == claimed for claimed, _evidence in _HINT_CLAIMS[tier]
            ), f"{phrase!r} is not among {tier}'s claims in _HINT_CLAIMS"


#: The ladder, **spelled out here** rather than read from
#: ``market._TIER_STEPS``: the order is an argument (how recoverable each
#: field is from what survives, module docstring), so reordering it must be a
#: deliberate edit in two places.  Deriving this from the widget's own
#: constant would compare it against itself and pin nothing but the render.
_EXPECTED_LADDER = (
    ("full", frozenset()),
    ("compact", frozenset({"flow", "vol"})),
    ("narrow", frozenset({"flow", "vol", "fp", "price_bar"})),
    (
        "minimal",
        frozenset({"flow", "vol", "fp", "price_bar", "spread", "supply_bar"}),
    ),
    (
        "bare",
        frozenset(
            {"flow", "vol", "fp", "price_bar", "spread", "supply_bar", "mechanism"}
        ),
    ),
)


async def test_market_sheds_whole_labelled_fields_in_the_documented_order():
    """Composited: what is gone at each tier, and what is still there.

    The order is the module docstring's, and it is an argument about how
    recoverable each field is from what survives -- so it is worth asserting
    as an order and not merely as "something went".
    """
    assert [name for name, _gone in _EXPECTED_LADDER] == list(_market.TIERS)
    bars = set("▁▂▃▄▅▆▇█")
    seen: list[str] = []
    for tier, expected_gone in _EXPECTED_LADDER:
        # Row 0 is the title, whose own hint names fields -- reading it as
        # content would make "price bar" in the marker look like a price bar.
        rows = (await _render_at(_FULL_MARKET, _tier_width(tier, _FULL_MARKET)))[0][1:]
        body = "\n".join(rows)
        price_row = next((r for r in rows if "$0.7074" in r), "")
        token_row = next((r for r in rows if "pool $" in r), "")
        gone = {
            "flow": "gap narrows" not in body,
            "vol": "vol 24h" not in body,
            "fp": "FP  $0.7274" not in body,
            "price_bar": not (set(price_row) & bars),
            "spread": "under FP" not in body,
            "supply_bar": not (set(token_row) & bars),
            "mechanism": "IMD is FP bridged 1:1 from Base" not in body,
        }
        seen.append(tier)
        assert {f for f, is_gone in gone.items() if is_gone} == expected_gone, (
            f"at the {tier} tier the panel renders:\n{body}"
        )
    assert seen == [name for name, _gone in _EXPECTED_LADDER]


async def test_market_the_dollar_spread_never_appears_without_its_caveat():
    """``gross of fees`` may never be outlived by the number it qualifies.

    Bridge fees, gas on two chains and both pools' slippage are not knowable
    keylessly, so a dollar gap printed without that caveat is a gap a reader
    can take for free money.
    """
    for tier in _market.TIERS:
        rows = "\n".join(
            (await _render_at(_FULL_MARKET, _tier_width(tier, _FULL_MARKET)))[0]
        )
        if "under FP" in rows:
            assert "gross of fees" in rows, (
                f"the {tier} tier states a dollar gap uncaveated:\n{rows}"
            )


async def test_market_never_states_a_spread_of_any_kind_without_the_caveat():
    """The caveat qualifies *the spread*, not the dollar cell it started in.

    ``parity ▼ -2.75%`` never sheds, so shedding the dollar cell used to take
    the only ``gross of fees`` on the panel with it: a 100-column terminal
    (49 columns of panel) rendered a 2.75% gap on a bridged pair with no fee
    caveat anywhere on screen, which is the exact reading the caveat exists
    to stop.  Swept over every width the panel has a tier for, because that
    width is the common one and not an exotic edge.
    """
    lo = _tier_width("bare", _FULL_MARKET)
    hi = _tier_width("full", _FULL_MARKET) + 6
    for width in range(lo, hi):
        rows, _title = await _render_at(_FULL_MARKET, width)
        body = "\n".join(rows)
        if "…" in body:
            continue        # cut, and the title says so: another test's job
        assert "-2.75%" in body, body
        assert "gross of fees" in body, (
            f"at {width} columns the panel states a spread with no caveat:"
            f"\n{body}"
        )


async def test_market_the_parity_percentage_survives_every_tier():
    """The panel's job is the spread, so the spread is what stands last.

    What the narrow tiers shed is the *dollar restatement* of it; the
    percentage is 18 columns and never goes, so a reader on any terminal
    still learns which side of parity IMD is on.
    """
    for tier in _market.TIERS:
        rows = "\n".join(
            (await _render_at(_FULL_MARKET, _tier_width(tier, _FULL_MARKET)))[0]
        )
        assert "parity ▼ -2.75%" in rows, f"the {tier} tier lost the parity:\n{rows}"


async def test_market_narrowest_tier_keeps_the_unavailable_warning_whole():
    """``⚠ spread unavailable`` shares a row with the mechanism sentence.

    Together they are 54 columns, so on a narrow panel the *warning* is what
    ``text-overflow`` would cut -- an explicit unavailable state degrading
    into an ellipsis, which is the one outcome worse than shedding a field.
    Dropping the mechanism is why the last tier exists.
    """
    payload = {**_FULL_MARKET, "parity_pct": None}
    width = _tier_width("bare", payload)
    rows, title = await _render_at(payload, width)
    body = "\n".join(rows)
    assert "⚠ spread unavailable" in body, body
    assert "…" not in body, body
    assert _market.BRIDGE_MECHANISM not in body       # the field that paid for it
    assert _market.WIDEN_HINTS["bare"] in title


async def test_market_never_cuts_a_row_without_saying_so():
    """The whole contract, swept column by column over the real widget.

    Two failures this catches and no single-width test does: a tier that
    fits by measurement but paints one column wider, and a hint that stops
    fitting beside the title before the rows stop fitting inside the panel.
    Below the width at which even ``‹ widen`` fits beside a 10-column title
    the panel goes unmarked -- the same limit ``widgets/surf/nft.py`` records,
    and the reason the sweep starts where it does.
    """
    floor = len(_market.PANEL_TITLE) + 2 + len(_market.SHORT_HINT)
    for width in range(floor, _tier_width("full", _FULL_MARKET) + 6):
        rows, title = await _render_at(_FULL_MARKET, width)
        body = "\n".join(rows)
        if "…" in body or "widen" in title:
            assert "widen" in title, (
                f"at {width} columns the panel is cut with nothing to say so:"
                f"\n{body}"
            )
        else:
            assert body.count("$") >= 3, body   # a full panel, not an empty one


async def test_market_re_tiers_when_the_panel_is_resized():
    """Rows are formatted at the width they were formatted at, once.

    Without ``on_resize`` a widened terminal keeps the narrow tier -- fields
    shed for no reason -- and a narrowed one keeps the wide tier, ellipsised,
    with the title still claiming nothing went. Both last until the next
    30-second poll.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    narrow = _tier_width("minimal", _FULL_MARKET) + 2
    wide = _tier_width("full", _FULL_MARKET) + 2
    async with app.run_test(size=(narrow, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        assert _market.WIDEN_HINTS["minimal"] in _lines(app)[0]

        await pilot.resize_terminal(wide, 14)
        await pilot.pause()
        title = _lines(app)[0]
        assert "widen" not in title, f"still shedding after the widen: {title!r}"
        assert "vol 24h" in "\n".join(_panel_rows(app))


# -- SurfMarket: fix round 10a -- v3 -> v4 repoint, price-source disagreement
#
# The v3 pool drained to $2,195 while the live v4 pool holds $805,927 --
# quoting v3 as the panel's own number under-reported the dashboard's subject
# by ~370x. Fix round 10a repointed ``pool_liquidity_usd`` at the live pool
# (matched by the dev's own on-chain pool id rather than by size) and added
# ``legacy_pool_liquidity_usd`` as a genuinely separate figure -- this widget
# needs no venue gating at all any more: ``pool`` is always the live number,
# and ``legacy`` is gated purely on its own presence (``None`` when the v3
# pair goes unmatched). The line lives on the seam row (``#surf-mkt-gap``)
# that used to be permanently blank, at the ``full`` tier only, and carries
# no right-hand segment -- ``_second_column`` cannot see it, so it never
# moves a sparkline (see ``market._ROW_IDS``).


async def test_market_shows_the_live_v4_pool_and_keeps_v3_as_legacy():
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_MARKET,
                "pool_liquidity_usd": 805927.0,
                "legacy_pool_liquidity_usd": 2195.0,
            }
        )
        await pilot.pause()
        screen = _screen_text(app)
        assert "pool $805.9K" in screen   # the live pool figure, primary
        assert "legacy" in screen
        assert "$2.2K" in screen          # the retired v3 figure, dim


async def test_market_the_legacy_line_stays_silent_when_the_v3_pair_is_unmatched():
    """``legacy_pool_liquidity_usd is None`` (the v3 pair went unmatched, or
    the payload predates fix round 10a) must render exactly as before this
    fix round -- which is what keeps
    ``test_market_blank_row_separates_the_token_figures_from_the_bridge``
    green with no changes there."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        assert "legacy" not in _screen_text(app)


async def test_market_the_legacy_line_survives_even_with_no_live_pool_figure():
    """A cold cache before the launchpad sweep first lands can leave
    ``pool_liquidity_usd`` unread while ``legacy_pool_liquidity_usd`` (keyed
    on the v3 pair's own known address, no pool id needed) still answers --
    the legacy note must not be silently withheld waiting for a figure it
    does not depend on."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_MARKET,
                "pool_liquidity_usd": None,
                "legacy_pool_liquidity_usd": 2195.0,
            }
        )
        await pilot.pause()
        screen = _screen_text(app)
        assert "legacy" in screen
        assert "$2.2K" in screen


async def test_market_marks_a_price_source_disagreement():
    """Two independent keyless sources agree to 0.2% today; 2% is ~10x that.

    ``imd_price_usd`` is already whichever the manager preferred (the
    on-chain ``extsload`` read when available) by the time it reaches this
    widget -- the marker never re-chooses between the two, it only flags
    that DexScreener's figure disagrees with it past the threshold, so the
    disagreement is visible rather than silently absorbed.
    """
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_MARKET,
                "imd_price_usd": 1.08,
                "price_source_disagreement_pct": 7.4,
            }
        )
        await pilot.pause()
        screen = _screen_text(app)
        assert "IMD $1.08" in screen   # the preferred read, rendered as-is
        assert "?" in screen


async def test_market_price_agreement_within_threshold_shows_no_marker():
    """0.2% agreement (today's real number) must not read as degraded."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(
            **{**_FULL_MARKET, "price_source_disagreement_pct": 0.2}
        )
        await pilot.pause()
        assert "?" not in _screen_text(app)


async def test_market_a_missing_disagreement_source_is_not_agreement_or_disagreement():
    """``None`` means one source was missing -- that must not render as
    agreement (no claim either way is being made) but it is also not a
    disagreement to flag, so no marker either."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(
            **{**_FULL_MARKET, "price_source_disagreement_pct": None}
        )
        await pilot.pause()
        assert "?" not in _screen_text(app)


async def test_market_a_failed_price_read_carries_no_disagreement_marker():
    """``None`` never renders ``$0.00`` and it must not grow a ``?`` beside
    a dash either -- there is no figure for the marker to sit next to."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(100, 14)) as pilot:
        widget.update_data(
            **{
                **_FULL_MARKET,
                "imd_price_usd": None,
                "price_source_disagreement_pct": 7.4,
            }
        )
        await pilot.pause()
        assert "?" not in _screen_text(app)


async def test_market_worst_case_combined_width_matches_the_documented_ceiling():
    """Legacy line + disagreement marker together, against a tight peg (the
    module's own existing worst case) -- re-measured per fix round 10a
    rather than assumed, since the payload's shape changed. Must not exceed
    the 73-column ceiling ``SURF_FULL_LAYOUT_COLUMNS``/``FULL_LAYOUT_COLUMNS``
    were already sized against.
    """
    worst = {
        **_FULL_MARKET,
        "imd_price_usd": 0.71,
        "fp_price_usd": 0.7071,
        "pool_liquidity_usd": 805927.0,
        "legacy_pool_liquidity_usd": 2195.0,
        "price_source_disagreement_pct": 7.4,
    }
    parts = _market._parts(**worst)
    width = max(
        visible_len(line) for line in _market._lines_for("full", parts)
    )
    assert width <= 73, f"fix round 10a widened the panel's full tier to {width}"
