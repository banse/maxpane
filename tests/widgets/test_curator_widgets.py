"""Widget suite for the curator dashboard — THE LIST (WP4).

Seven render-only widgets plus their format helpers.  Everything here is
asserted against **composited output** (``app.screen._compositor.render_strips()``)
rather than against a widget's content string: a string that never reaches a
pixel passes a naive test while being invisible to the user, and this
dashboard's whole product is a set of explicit states a user has to be able
to read.

Three structural guards run before any rendering test:

1. no module under ``widgets/curator/`` imports ``data/`` or ``analytics/``
   (by AST — a string scan misses ``importlib`` and aliases);
2. none of them copies a sparkline helper (MEDI-36);
3. every vocabulary a widget branches on or sizes a cell from is asserted
   against the **frozen** tuple in ``data/curator_models``.  The widget may
   not import that module, so the literal lives in the widget and the
   agreement lives here — the redundancy-plus-agreement-test pattern
   CLAUDE.md documents for ``_GAME_CYCLE``.

Deviation from wp4.md, deliberate: the brief sketches ``_rendered(hero, ...)``
as a synchronous call.  Compositing requires a running app, so ``_rendered``
is an async helper taking the widget **class** and the tests are ``async def``
(pytest-asyncio auto mode, as ``test_surf_widget_contract.py`` does it).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from maxpane_dashboard.widgets.curator._fmt import (
    ADDR_COLS,
    DASH,
    EMDASH,
    NO_STAMP,
    as_float,
    fmt_age,
    fmt_countdown,
    fmt_eth,
    fmt_eth_compact,
    fmt_pct,
    fmt_points,
    hhmm,
    short_addr,
)

#: The package under test, as a directory — the AST guards glob it, so a
#: module added without an entry in this suite is still scanned.
CURATOR_WIDGETS_DIR = (
    Path(__file__).resolve().parents[2]
    / "maxpane_dashboard"
    / "widgets"
    / "curator"
)


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


class _Harness(App):
    """One widget, full screen, so the compositor has something to render."""

    def __init__(self, widget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _screen_text(app) -> str:
    strips = app.screen._compositor.render_strips()
    return "\n".join("".join(seg.text for seg in strip) for strip in strips)


async def _rendered(cls, *, size=(143, 24), **kwargs) -> str:
    """Composited text of ``cls`` after one ``update_data(**kwargs)``.

    ``size`` defaults to the app-wide full-layout width so copy is measured
    where the user sees it; the width tests pass their own.
    """
    widget = cls()
    app = _Harness(widget)
    async with app.run_test(size=size) as pilot:
        widget.update_data(**kwargs)
        # Pump the message loop: a deferred MarkupError surfaces here or never.
        await pilot.pause()
        return _screen_text(app)


# ===========================================================================
# WP4.1 — import hygiene and the format helpers
# ===========================================================================


def test_no_curator_widget_imports_data_or_analytics():
    """Structural, by AST — a string scan misses ``importlib`` and aliases."""
    modules = sorted(CURATOR_WIDGETS_DIR.glob("*.py"))
    assert modules, "no curator widget modules found to scan"
    for path in modules:
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            elif isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            else:
                continue
            for m in mods:
                assert ".data" not in m and ".analytics" not in m, (path.name, m)
                assert "httpx" not in m and "aiohttp" not in m, (path.name, m)


def test_no_curator_widget_copies_a_sparkline_helper():
    """MEDI-36: the helpers are imported from ``sparkline_common``, not forked."""
    for path in sorted(CURATOR_WIDGETS_DIR.glob("*.py")):
        src = path.read_text("utf-8")
        for copied in ("SPARK_CHARS", "def build_sparkline", "def trend_arrow",
                       "def coerce_points"):
            assert copied not in src, (path.name, copied)


def test_short_addr_is_eleven_columns_and_keeps_both_ends():
    """``0x1234…abcd``, and the *measured* width every address cell is sized to.

    PRD §4 calls this form "13 cols"; the form it names is 11, and the cells
    in this package are sized from ``ADDR_COLS`` so the two cannot drift.
    """
    out = short_addr("0x381fe4861234567890abcdef1234567890abCDEF")
    assert out == "0x381f…cdef"
    assert len(out) == ADDR_COLS == len("0x1234…abcd") == 11
    assert out.startswith("0x381") and out.endswith("cdef")


def test_short_addr_renders_one_spelling_for_both_of_the_payloads_two():
    """Checksummed from ``eth_call``, lowercase from a log topic — one wallet.

    Without this the same address renders two ways in two panels and the
    leaderboard's "this row is you" match reads as a different wallet.
    """
    checksummed = "0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91"
    assert short_addr(checksummed) == short_addr(checksummed.lower())


def test_every_formatter_returns_a_dash_for_none_and_never_a_zero():
    for fn in (fmt_eth, fmt_eth_compact, fmt_age, fmt_countdown, fmt_points,
               fmt_pct):
        assert fn(None) in (DASH, EMDASH), fn.__name__
    for fn in (fmt_eth, fmt_points, fmt_eth_compact):
        assert fn(0) not in (DASH, EMDASH), fn.__name__  # a real zero renders


def test_a_minimum_deposit_never_renders_as_zero():
    """``fmt_compact`` gives everything under 1.0 zero decimals, so the
    contract's own ``minDeposit`` (0.05 ETH — the most common amount on the
    feed) comes out of it as ``0``.  That is the false zero this dashboard
    exists to avoid, so small amounts keep their digits."""
    from maxpane_dashboard.widgets.sparkline_common import fmt_compact

    assert fmt_compact(0.05) == "0"  # the trap, demonstrated not remembered
    assert fmt_eth_compact(0.05) == "0.050"
    assert fmt_eth_compact(8401.0) == "8.4K"
    assert fmt_eth_compact(461.1) == "461.10"


def test_fmt_countdown_handles_the_contracts_edges():
    """``timeLeftInHour()`` returns hourDuration at an exact boundary, never
    0 (H12), and ``grace_seconds_left`` is clamped at 0 by the analytics
    layer."""
    assert fmt_countdown(3600) == "1:00:00"
    assert fmt_countdown(86400) == "24:00:00"
    assert fmt_countdown(1) == "00:01"
    assert fmt_countdown(0) == "00:00"
    assert fmt_countdown(-5) in (DASH, EMDASH)  # nonsense, never a negative clock


def test_no_formatter_ever_renders_a_negative_countdown():
    assert "-" not in fmt_countdown(0)
    # A negative input renders the unknown marker, never a signed clock:
    # ``-00:05`` would claim a deadline five seconds gone.  (``DASH`` is
    # itself two hyphens, so the assertion is on the whole string.)
    for value in (-1, -5, -86400):
        assert fmt_countdown(value) == DASH
        assert ":" not in fmt_countdown(value)


def test_a_missing_or_epoch_timestamp_renders_the_no_stamp_marker():
    """H14: a stamp that could not be read is ``--:--``; ``00:00`` on
    1970-01-01 looks like data."""
    for value in (None, 0, "", "nonsense"):
        assert hhmm(value) == NO_STAMP
    assert hhmm(1786910327) != NO_STAMP


def test_as_float_refuses_bools_and_nonsense_without_raising():
    for value in (True, False, None, "x", [], {}, float("nan"), float("inf")):
        assert as_float(value) is None
    assert as_float("3.5") == 3.5
    assert as_float(0) == 0.0


def test_fmt_pct_distinguishes_an_unknown_share_from_a_zero_one():
    assert fmt_pct(None) == DASH
    assert fmt_pct(0) == "0.0%"
    assert fmt_pct(12.44) == "12.4%"


def test_no_formatter_raises_on_hostile_input():
    """Widgets run inside Textual's message pump; a raise there kills the app."""
    hostile = ("[/x]", object(), [1, 2], {"a": 1}, b"\x00", float("nan"))
    for fn in (fmt_eth, fmt_eth_compact, fmt_age, fmt_countdown, fmt_points,
               fmt_pct, hhmm, short_addr):
        for value in hostile:
            assert isinstance(fn(value), str), (fn.__name__, value)
