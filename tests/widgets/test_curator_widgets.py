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

from maxpane_dashboard.widgets.curator import CuratorHero
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


# ===========================================================================
# WP4.2 — CuratorHero
# ===========================================================================

#: One realistic payload per phase.  Magnitudes come from the 2026-08-16
#: captures (252 wallets, 8401 ETH routed, earlyBps 19491 = 1.9491x) but
#: nothing here asserts a live-looking magnitude — the fixtures document
#: scale, not state (PRD §7).
def _grace_payload() -> dict:
    return dict(
        phase="grace",
        current_hour=1,
        grace_seconds_left=11565,
        grace_ends_utc="2026-08-17 19:58:47Z",
        hour_fed_eth=9987.26,
        hour_needed_eth=0.0,
        hour_seconds_left=1580,
        hourly_threshold_eth=5.0,
        early_multiplier_x=1.9491,
        points_per_eth_now=1396,
        contributors_total=252,
        deposits_total=497,
        volume_routed_eth=8401.0,
        top_points=21473,
    )


def _judged_payload() -> dict:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (capture B, post-grace with a live deficit, window 2026-08-17 19:58:47Z)
    return dict(
        phase="judged",
        current_hour=27,
        grace_seconds_left=0,
        grace_ends_utc="2026-08-17 19:58:47Z",
        hour_fed_eth=3.6,
        hour_needed_eth=1.4,
        hour_seconds_left=753,
        hourly_threshold_eth=5.0,
        first_judged_hour=24,
        early_multiplier_x=1.0,
        points_per_eth_now=1000,
        survival_streak_hours=3,
        closest_call_margin_eth=0.42,
        closest_call_hour=26,
        contributors_total=252,
        deposits_total=497,
        volume_routed_eth=8401.0,
        top_points=21473,
    )


def _settled_payload() -> dict:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (capture C, the settlement transition, earliest 2026-08-17 20:58:47Z)
    return dict(
        phase="settled",
        settled=True,
        current_hour=28,
        settled_hour=27,
        settled_at_ts=1787000327,
        settled_observed_at=1787000341.0,
        lived_desc="lived 1 d 01 h",
        contributors_total=252,
        deposits_total=497,
        volume_routed_eth=8401.0,
        top_points=21473,
        hourly_threshold_eth=5.0,
    )


_PAYLOAD_FOR = {
    "grace": _grace_payload,
    "judged": _judged_payload,
    "settled": _settled_payload,
}

#: The one line each phase's CLOCK box must put on screen.
_EXPECTED_HEADLINE = {
    "grace": "GRACE",
    "judged": "HOUR 27",
    "settled": "SETTLED AT HOUR 27",
}


def test_the_hero_branches_on_exactly_the_frozen_phase_vocabulary():
    """A fourth spelling anywhere is a silent fallback arm.

    The widget may not import ``data/``, so it restates ``PHASES``; this is
    the agreement half of that redundancy.
    """
    from maxpane_dashboard.data.curator_models import PHASES as FROZEN_PHASES
    from maxpane_dashboard.widgets.curator import hero as hero_mod

    assert hero_mod.PHASES == FROZEN_PHASES
    assert set(_PAYLOAD_FOR) == set(FROZEN_PHASES)


def test_the_hero_reads_no_clock_of_its_own():
    """PRD §2: clock values are poll-anchored.  A widget-local ``time.time()``
    would tick a countdown the manager did not measure, so the hero would
    disagree with the title bar's freshness marker and keep counting through
    an outage."""
    from maxpane_dashboard.widgets.curator import hero as hero_mod

    tree = ast.parse(inspect.getsource(hero_mod))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                assert name.split(".")[0] not in ("time", "datetime"), name
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # Structural, not a source scan: the prose above has to quote the
            # very calls it forbids, and a grep for them self-trips on it.
            assert node.func.attr not in ("time", "now", "utcnow", "monotonic")


async def test_volume_is_never_labelled_tvl_or_capital():
    """H4, the flagship honesty rule.  Every wei is refunded in-transaction,
    so a TVL label is not a rounding error — it is a false claim about money
    at risk, on a dashboard people will read while deciding to send 60 ETH."""
    text = await _rendered(CuratorHero, **_grace_payload())
    assert "routed (all refunded)" in text
    for banned in ("TVL", "locked", "at risk", "capital", "deposited value"):
        assert banned.lower() not in text.lower(), banned


@pytest.mark.parametrize("phase", ("grace", "judged", "settled"))
async def test_the_refunded_wording_survives_every_phase(phase):
    text = await _rendered(CuratorHero, **_PAYLOAD_FOR[phase]())
    assert "refunded" in text
    for banned in ("TVL", "locked", "at risk", "capital"):
        assert banned.lower() not in text.lower(), banned


async def test_the_one_honest_capital_sentence_appears_at_most_once():
    """PRD §6: the EOA gate means each high-water mark WAS really held in a
    real EOA.  True, and worth saying once as subtitle text — never twice,
    and never next to a volume number."""
    text = await _rendered(CuratorHero, **_grace_payload())
    assert text.lower().count("eoa") == 1
    # ...and on its own line, not in the box that carries the volume figure.
    eoa_line = next(line for line in text.splitlines() if "EOA" in line)
    assert "routed" not in eoa_line and "ETH" not in eoa_line


@pytest.mark.parametrize("phase", ("grace", "judged", "settled"))
async def test_each_phase_renders_its_own_three_boxes(phase):
    text = await _rendered(CuratorHero, **_PAYLOAD_FOR[phase]())
    assert _EXPECTED_HEADLINE[phase] in text
    assert "THE LIST" in text
    # ...and only its own.  The markers below are the ones no other phase
    # can produce -- "HOUR 27" is not one of them, because "SETTLED AT HOUR
    # 27" contains it.
    exclusive = {"grace": "GRACE", "judged": "fed ", "settled": "SETTLED AT HOUR"}
    for other, marker in exclusive.items():
        if other != phase:
            assert marker not in text, (phase, other)


async def test_the_settled_hero_reads_as_an_archive_not_as_a_failure():
    """PRD §11: SETTLED is a first-class terminal state.  Words like 'error',
    'stale' or 'unavailable' in the settled hero tell a user the dashboard is
    broken when the *game* is over."""
    text = await _rendered(CuratorHero, **_settled_payload())
    assert "SETTLED AT HOUR" in text and "list FROZEN" in text
    for wrong in ("error", "unavailable", "stale", "no data", "warning"):
        assert wrong not in text.lower(), wrong


async def test_a_missing_value_renders_the_explicit_unavailable_state():
    text = await _rendered(CuratorHero)  # no kwargs at all
    assert "unavailable" in text.lower() or text.count("--") >= 3
    assert "0.00 ETH" not in text and "0 wallets" not in text
    assert "0 contributors" not in text


async def test_an_unknown_phase_renders_a_named_fallback_not_a_blank_box():
    """phase=None is what a failed isSettled read produces (WP3.2).  The hero
    must say so rather than silently choosing GRACE, which would render a
    countdown for a game that may already be dead."""
    text = await _rendered(CuratorHero, phase=None, current_hour=30)
    assert "phase unavailable" in text.lower()
    assert "GRACE" not in text and "SETTLED AT HOUR" not in text


async def test_a_fourth_phase_spelling_is_unknown_rather_than_grace():
    text = await _rendered(CuratorHero, phase="frozen", current_hour=30)
    assert "phase unavailable" in text.lower()


async def test_the_judged_clock_reads_its_denominator_from_the_payload():
    """Amendment A1/§5: ``hourly_threshold_eth`` is read live off the ``once``
    tier.  A hardcoded "5.00" would survive every test on this deployment and
    be wrong on the next one — and the sum ``fed + needed`` cannot recover it,
    because ``ethNeededThisHour()`` answers 0 whenever the hour is already
    safe."""
    payload = {**_judged_payload(), "hourly_threshold_eth": 7.5}
    text = await _rendered(CuratorHero, **payload)
    assert "/7.50 ETH" in text
    assert "/5.00" not in text


async def test_a_judged_hour_with_a_deficit_says_so_in_words():
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    text = await _rendered(CuratorHero, **_judged_payload())
    assert "needs 1.40 ETH" in text
    safe = await _rendered(
        CuratorHero, **{**_judged_payload(), "hour_needed_eth": 0.0}
    )
    # 0.0 needed is a REAL answer on a safe hour, not an unknown one.
    assert "hour is safe" in safe
    unknown = await _rendered(
        CuratorHero, **{**_judged_payload(), "hour_needed_eth": None}
    )
    assert "hour is safe" not in unknown and "needs" not in unknown


async def test_every_hero_tier_fits_the_width_it_advertises():
    """Copy is measured, not reasoned about: every phase at every tier."""
    from maxpane_dashboard.widgets.curator import hero as hero_mod

    for tier, budget in hero_mod.TIER_WIDTHS.items():
        for build in (hero_mod._clock_lines, hero_mod._list_lines,
                      hero_mod._curve_lines):
            for payload in (_grace_payload(), _judged_payload(),
                            _settled_payload(), {}, {"phase": "grace"}):
                for line in build(payload, tier):
                    width = _visible(line)
                    assert width <= budget, (tier, build.__name__, line, width)


def _visible(markup: str) -> int:
    from maxpane_dashboard.widgets.markup_safety import visible_len

    return visible_len(markup)


async def test_a_narrow_hero_announces_the_columns_it_shed():
    """Never clip dark: below the narrowest tier the box says so."""
    widget = CuratorHero()
    app = _Harness(widget)
    async with app.run_test(size=(46, 12)) as pilot:
        widget.update_data(**_grace_payload())
        await pilot.pause()
        text = _screen_text(app)
    assert "‹ widen" in text
