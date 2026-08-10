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
        # The raw v3 ``L`` used to render beside the WETH side as
        # ``2.60e+19``. It was dropped on request: scientific notation of an
        # unnamed unit told a reader nothing the WETH side does not. The
        # payload still carries ``lp_liquidity`` -- the LP MIGRATION detector
        # reads it -- so this asserts the *box* dropped it, not the key.
        assert "2.60e+19" not in screen
        assert "· L " not in screen
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
    from maxpane_dashboard.widgets.surf.hero import (
        TIER_WIDTHS,
        _gate_lines,
        _hook_lines,
        _lp_lines,
        _supply_lines,
    )

    for tier, need in TIER_WIDTHS.items():
        renderings = []
        for status in (HOOK_NOT_LIVE, HOOK_LAUNCHED, None, "", "holder-gated"):
            renderings.append(_hook_lines(status, tier))
        for owner in (True, False, None):
            renderings.append(_lp_lines(388421.0, 142.7067, owner, tier))
        for gate in (True, False, None):
            # 2000 is the IDMD cap and therefore the counter's widest
            # reachable value, not a hypothetical: ``2000/2000 written`` is
            # 17 columns and used to overflow the tight tier's advertised 16
            # with nothing in this sweep to catch it. A bounded quantity's
            # bound belongs in the measurement.
            for written in (1, None, 999, 2000):
                renderings.append(_gate_lines(gate, written, tier))
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


async def test_hero_unreadable_hook_says_unconfirmed_not_that_nothing_was_read():
    """``hook_status is None`` now has two producers, and one of them read.

    WP4's ``_hook_status`` returns ``None`` both when the logs group never
    answered *and* when the window held a hooked ``Initialize`` whose signer
    could not be attributed (``hook_unverified``) -- ``PoolManager.initialize``
    is permissionless, so naming the dev there would be a guess. The copy has
    to be true of both: "unconfirmed" is, "status unknown" reads only as the
    first.
    """
    widget = SurfHero()
    app = _Harness(widget)
    async with app.run_test(size=(160, 12)) as pilot:
        widget.update_data(**{**_FULL_HERO, "hook_status": None})
        await pilot.pause()
        screen = _screen_text(app)
        assert "unconfirmed" in screen
        # Never the two answers we have not earned.
        assert "NOT LIVE" not in screen
        assert "LAUNCHED" not in screen
        # ...and never the fallback arm, which means something else entirely.
        assert "unrecognized status" not in screen


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
)

#: A realistic mixed payload: the 2026-08-07 morning, 12 minutes after the
#: staging mint (ops_eth_token_transfers.json: +114,366.9 IMD OFT-minted to
#: frenpet.eth at 04:21:35) and two hours after the nonce-13 announce post.
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
}


async def test_signals_labels_are_the_prd_names_wp5_and_wp6_assert_on():
    """The label vocabulary is a cross-WP interface, pinned in one place.

    WP5's screen test and WP6's stylesheet/outage acceptance tests assert
    these exact PRD §3 strings against composited output.  If someone
    shortens a label for width, this goes red *here* -- in the widget WP
    that owns the string -- instead of in two WPs that only consume it.
    """
    assert DETECTOR_LABELS == (
        "NEW POST",
        "LP MIGRATION",
        "GATE OPEN",
        "NEW DEPLOY",
        "BRIDGE STAGE",
        "BURN",
    )


async def test_signals_fired_rows_carry_state_and_age_in_words():
    """FIRED must survive greyscale: the word, the age, the glyph -- in text."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**_FULL_SIGNALS)
        await pilot.pause()
        screen = _screen_text(app)
        assert "NEW POST FIRED 2h ago" in screen
        assert "BRIDGE STAGE FIRED 12m ago" in screen
        assert "NEW DEPLOY WATCH" in screen
        assert "LP MIGRATION OK" in screen
        assert "GATE OPEN OK" in screen
        assert "BURN OK" in screen
        # Details ride along.
        assert "+114,367 IMD minted to frenpet.eth" in screen
        assert "frenpet.eth nonce 29→30" in screen


async def test_signals_all_six_rows_always_render():
    """None-state rows are dashes -- six rows on screen no matter what."""
    widget = SurfSignals()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data()
        await pilot.pause()
        screen = _screen_text(app)
        for label in DETECTOR_LABELS:
            assert f"{label} --" in screen, label
        # No invented state: nothing fired, nothing ok.
        assert "FIRED" not in screen
        assert "OK" not in screen.replace("SIGNALS", "")


async def test_signals_fired_without_age_omits_the_age_not_the_state():
    row = _fmt_signal_row("LP MIGRATION", "fired", "liquidity -37%", None)
    assert "LP MIGRATION FIRED" in row
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
    async with app.run_test(size=(120, 14)) as pilot:
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
        # This is the assertion that actually matters: every other detector
        # still updated normally in the *same* refresh cycle -- one poisoned
        # row cannot freeze the panel at stale content.
        assert "BRIDGE STAGE FIRED 12m ago" in screen
        assert "+114,367 IMD minted to frenpet.eth" in screen
        assert "NEW DEPLOY WATCH" in screen
        assert "frenpet.eth nonce 29→30" in screen
        assert "LP MIGRATION OK" in screen
        assert "GATE OPEN OK" in screen
        assert "BURN OK" in screen


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
    """``IMD $0.7074 · 24h ± ▲ +30.89%`` -- composited, not the markup."""
    widget = SurfMarket()
    app = _Harness(widget)
    async with app.run_test(size=(120, 14)) as pilot:
        widget.update_data(**_FULL_MARKET)
        await pilot.pause()
        assert "IMD $0.7074 · 24h ± ▲ +30.89%" in _line_with(app, "$0.7074")


async def test_market_price_row_keeps_its_shape_when_the_change_turns_or_fails():
    """Down, flat and unread render the same row with the same label.

    The ``None`` case is the one that matters: a failed read must still say
    *what* could not be read rather than leaving a bare label -- and it must
    never fall back to a zero, which on a 24h change reads as "unmoved".
    """
    expected = {
        -3.80: "IMD $0.7074 · 24h ± ▼ -3.80%",
        0.0: "IMD $0.7074 · 24h ± ● +0.00%",
        None: "IMD $0.7074 · 24h ± --",
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
    "minimal": (("$ spread", "under FP"),),
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
