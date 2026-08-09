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
