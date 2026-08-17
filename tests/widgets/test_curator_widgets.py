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

from maxpane_dashboard.widgets.curator import (
    NO_ENS,
    NO_WALLET_SET,
    ACTIVITY_EMPTY,
    ACTIVITY_UNAVAILABLE,
    CLOSEST_CALLS_UNAVAILABLE,
    CLUSTERS_EMPTY,
    CLUSTERS_UNAVAILABLE,
    LEADERBOARD_EMPTY,
    LEADERBOARD_TITLE,
    LEADERBOARD_UNAVAILABLE,
    NEVER_SAVED,
    NO_JUDGED_HOURS,
    NO_WALLET,
    PHASE_UNAVAILABLE,
    SIGNAL_LABELS,
    SIGNALS_FULL_WIDTH,
    SPARKLINES_TITLE,
    UNKNOWN_GLYPH,
    WAITING,
    CuratorActivity,
    CuratorClosestCalls,
    CuratorClusters,
    CuratorWalletLadder,
    CuratorWalletNext,
    CuratorWalletStanding,
    CuratorWalletTarget,
    CuratorWalletAddress,
    CuratorWalletHero,
    CuratorHero,
    CuratorLeaderboard,
    CuratorSignals,
    CuratorSparklines,
)
from tests.curator_sybil_fixtures import worst_case_rows
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


# ===========================================================================
# WP4.3 — CuratorLeaderboard
# ===========================================================================

#: Shapes come from CURATOR_ROW_KEYS["leaderboard_rows"]; magnitudes from the
#: 2026-08-16 capture (rank 1 credit 461.1 ETH, the 9x60 ETH fan-out at 4-12).
#:
#: ``link_conf`` is ``None`` on all three, and that is the state the dashboard
#: is in until the linkage sweep first completes: WP3's adapter seeds the
#: sub-key on every row and fills it later, so ``None`` is the shipped-today
#: reading rather than a missing field.  The tests that care about a grade set
#: their own; leaving these ungraded is what keeps the Tier-A fallback (R5)
#: exercised by every other leaderboard test in this file.
def _lb_rows(count: int = 3) -> list[dict]:
    base = [
        {"rank": 1, "address": "0x381fe4861234567890abcdef1234567890abCDEF",
         "points": 21473, "credit_eth": 461.1, "tx_count": 7, "flagged": False,
         "name": None, "link_conf": None},
        {"rank": 2, "address": "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
         "points": 13038, "credit_eth": 170.0, "tx_count": 3, "flagged": False,
         "name": "surfsurf.eth", "link_conf": None},
        {"rank": 4, "address": "0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91",
         "points": 7745, "credit_eth": 60.0, "tx_count": 1, "flagged": True,
         "name": None, "link_conf": None},
    ]
    out = []
    for i in range(count):
        row = dict(base[i % len(base)])
        row["rank"] = i + 1
        out.append(row)
    return out


def test_the_leaderboard_columns_are_the_frozen_row_keys():
    """A column reading a key the producer does not emit renders ``--``
    forever with a green suite behind it."""
    from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS

    assert set(_lb_rows(3)[0]) == set(CURATOR_ROW_KEYS["leaderboard_rows"])


async def test_a_none_list_and_an_empty_list_render_different_states():
    """``None`` is a dead fold; ``[]`` is a game with no contributors."""
    dead = await _rendered(CuratorLeaderboard, leaderboard_rows=None)
    empty = await _rendered(CuratorLeaderboard, leaderboard_rows=[])
    assert LEADERBOARD_UNAVAILABLE in dead
    assert LEADERBOARD_EMPTY in empty
    assert LEADERBOARD_EMPTY not in dead and LEADERBOARD_UNAVAILABLE not in empty


async def test_at_most_ten_rows_reach_the_board():
    text = await _rendered(
        CuratorLeaderboard, leaderboard_rows=_lb_rows(25), size=(143, 30)
    )
    # Rows render an identity, which is a name when the wallet has one -- the
    # fixture mixes both, the way the chain does.
    ranks = [line for line in text.splitlines() if "0x" in line or ".eth" in line]
    assert len(ranks) == 10


async def test_the_your_own_row_is_emphasised_case_insensitively():
    """Addresses arrive checksummed from eth_call and lowercase from a log
    topic.  A case-sensitive match fires for one of those and not the other,
    and the reader's own row silently stops being marked."""
    rows = _lb_rows(3)
    for you in (rows[1]["address"], rows[1]["address"].lower(),
                rows[1]["address"].upper()):
        text = await _rendered(
            CuratorLeaderboard, leaderboard_rows=rows, you_address=you
        )
        assert "▸" in text, you
    plain = await _rendered(CuratorLeaderboard, leaderboard_rows=rows)
    assert "▸" not in plain


async def test_the_cluster_flag_has_three_states_not_two():
    """``False`` is "the fold ran and this wallet is not in a cluster";
    ``None`` is "the fold did not run".  Rendering both as blank would claim
    a clean board we never computed."""
    rows = _lb_rows(3)
    # The column header is itself a flag glyph, so the assertions count
    # occurrences rather than testing for presence.
    flagged = await _rendered(CuratorLeaderboard, leaderboard_rows=rows)
    assert flagged.count("⚑") >= 2          # header + the flagged row
    unknown = await _rendered(
        CuratorLeaderboard,
        leaderboard_rows=[{**r, "flagged": None} for r in rows],
    )
    assert unknown.count("⚑") == 1          # header only
    assert "?" in unknown
    clean = await _rendered(
        CuratorLeaderboard,
        leaderboard_rows=[{**r, "flagged": False} for r in rows],
    )
    assert clean.count("⚑") == 1 and "?" not in clean


async def test_a_hostile_address_string_renders_literally():
    """No real address is ``[/x]`` — but a mangled payload is, and Textual
    defers ``Text.from_markup`` into the message pump, so the MarkupError
    would land outside the screen's try/except and kill the app."""
    rows = [{"rank": 1, "address": "[/x]", "points": 1, "credit_eth": 1.0,
             "tx_count": 1, "flagged": False}]
    text = await _rendered(CuratorLeaderboard, leaderboard_rows=rows)
    assert "[/x]" in text


async def test_a_malformed_row_costs_its_own_row_and_not_the_panel():
    rows = [{"rank": "nonsense", "address": None, "points": "x",
             "credit_eth": "y", "tx_count": None, "flagged": False},
            _lb_rows(1)[0]]
    text = await _rendered(CuratorLeaderboard, leaderboard_rows=rows)
    assert "0x381f" in text          # the good row still rendered
    assert "nonsense" not in text


@pytest.mark.parametrize(
    "width,expect_hint",
    [(143, ""), (60, ""), (46, "‹ widen: TX"), (36, "‹ widen: TX + CREDIT")],
)
async def test_narrow_boards_announce_the_columns_they_shed(width, expect_hint):
    widget = CuratorLeaderboard()
    app = _Harness(widget)
    async with app.run_test(size=(width, 20)) as pilot:
        widget.update_data(leaderboard_rows=_lb_rows(3))
        await pilot.pause()
        text = _screen_text(app)
    if expect_hint:
        assert "widen" in text
    else:
        assert "widen" not in text
    assert "0x381f" in text          # never clipped away entirely


# ===========================================================================
# Cross-table guards (all three DataTable panels)
# ===========================================================================


def test_every_declared_tier_cost_is_the_measured_one():
    """A hand-typed cost that drifts low makes a panel choose a layout it
    cannot render — and then clip in silence, which is the one thing the
    width tiers exist to prevent."""
    from maxpane_dashboard.widgets.curator import closest_calls as cc_mod
    from maxpane_dashboard.widgets.curator import clusters as cl_mod
    from maxpane_dashboard.widgets.curator import leaderboard as lb_mod
    from maxpane_dashboard.widgets.curator._table import tier_cost

    for module in (lb_mod, cc_mod, cl_mod, *_analysis_tier_modules()):
        for name, cost, columns, _hint in module._TIERS:
            assert cost == tier_cost(columns), (module.__name__, name)


def _analysis_tier_modules():
    """The `f` view's tiered-table modules, one per panel as they land."""
    from maxpane_dashboard.widgets.curator import operators as op_mod

    modules = [op_mod]
    for name in ("segments", "cleaned_list"):
        try:
            modules.append(
                __import__(
                    f"maxpane_dashboard.widgets.curator.{name}", fromlist=["_TIERS"]
                )
            )
        except ModuleNotFoundError:  # pragma: no cover - pre-WP4.2/4.3 only
            pass
    return tuple(modules)


def test_tier_costs_descend_so_a_narrow_panel_can_reach_the_narrow_layout():
    from maxpane_dashboard.widgets.curator import closest_calls as cc_mod
    from maxpane_dashboard.widgets.curator import clusters as cl_mod
    from maxpane_dashboard.widgets.curator import leaderboard as lb_mod

    for module in (lb_mod, cc_mod, cl_mod, *_analysis_tier_modules()):
        costs = [cost for _n, cost, _c, _h in module._TIERS]
        assert costs == sorted(costs, reverse=True), module.__name__
        assert module._TIERS[0][3] == "", "the widest tier sheds nothing"
        for _n, _c, _cols, hint in module._TIERS[1:]:
            assert hint, "every narrower tier names what it dropped"


# ===========================================================================
# WP4.4 — CuratorSparklines
# ===========================================================================


def _volume_series() -> list:
    """Hour-bucketed routed volume, folded from ``Deposited`` logs.

    The four values are the hour totals the live bundle
    ``20260817T000322Z_grace-late.json`` reconciles wei-exact against three
    independent state reads: hours 0-3 at 851.89 / 9987.26 / 2263.83 /
    2738.92 ETH.
    """
    return [
        [1786910327, 851.89],
        [1786913927, 9987.26],
        [1786917527, 2263.83],
        [1786921127, 2738.92],
    ]


def _contributors_series() -> list:
    return [[1786910327, 66], [1786913927, 145], [1786917527, 213],
            [1786921127, 252]]


async def test_both_series_draw_through_the_shared_sparkline_helper():
    from maxpane_dashboard.widgets.sparkline_common import SPARK_CHARS

    text = await _rendered(
        CuratorSparklines,
        volume_series=_volume_series(),
        contributors_series=_contributors_series(),
        hourly_threshold_eth=5.0,
    )
    assert any(ch in text for ch in SPARK_CHARS)
    assert "VOL/h" in text and "WALLETS" in text


async def test_the_volume_spark_labels_the_survival_bar_from_the_payload():
    """A volume sparkline without the bar is a pretty picture with no
    meaning — the only thing that matters about an hour is whether it cleared
    the threshold.  The number is read live, never a remembered 5.00."""
    text = await _rendered(
        CuratorSparklines,
        volume_series=_volume_series(),
        contributors_series=_contributors_series(),
        hourly_threshold_eth=7.5,
    )
    assert "7.50 ETH bar" in text
    assert "5.00" not in text


async def test_an_unknown_threshold_dashes_the_bar_rather_than_inventing_one():
    text = await _rendered(
        CuratorSparklines,
        volume_series=_volume_series(),
        contributors_series=_contributors_series(),
    )
    assert f"{DASH} ETH bar" in text


async def test_a_none_series_and_an_empty_series_render_the_same_state():
    """Deliberate, and the one place in this package where they agree: both
    mean "no history to draw", and a flat baseline would be a line the data
    never justified.  A failed read still reaches the reader — through the
    title bar's degraded groups, not through this panel."""
    dead = await _rendered(CuratorSparklines, volume_series=None,
                           contributors_series=None)
    empty = await _rendered(CuratorSparklines, volume_series=[],
                            contributors_series=[])
    assert WAITING in dead and WAITING in empty


async def test_a_series_with_a_null_point_survives_through_coerce_points():
    """A single ``null`` in a cache file used to abort startup for every
    dashboard; ``coerce_points`` is the boundary and it is imported, not
    re-implemented."""
    dirty = [[1786910327, 851.89], None, [1786913927, None],
             ["bad", "worse"], [1786917527, 2263.83]]
    text = await _rendered(
        CuratorSparklines,
        volume_series=dirty,
        contributors_series=_contributors_series(),
        hourly_threshold_eth=5.0,
    )
    assert WAITING not in text          # two good points still draw a line
    assert "2.26K ETH" in text or "2.3K ETH" in text


async def test_the_trend_arrow_is_the_shared_one():
    from maxpane_dashboard.widgets.sparkline_common import trend_arrow

    rising = _contributors_series()
    assert "▲" in trend_arrow(rising)
    text = await _rendered(
        CuratorSparklines,
        volume_series=_volume_series(),
        contributors_series=rising,
        hourly_threshold_eth=5.0,
    )
    assert "▲" in text


async def _spark_at(width: int) -> str:
    widget = CuratorSparklines()
    app = _Harness(widget)
    async with app.run_test(size=(width, 8)) as pilot:
        widget.update_data(
            volume_series=_volume_series(),
            contributors_series=_contributors_series(),
            hourly_threshold_eth=5.0,
        )
        await pilot.pause()
        return _screen_text(app)


async def test_a_narrow_rail_sheds_the_bar_label_before_the_sparkline():
    """Order of sacrifice: the bar label (a constant a reader learns once),
    then the spark's width, then the trend value.  The row label never goes —
    a nameless sparkline is decoration."""
    text = await _spark_at(38)
    assert "VOL/h" in text and "WALLETS" in text
    assert "ETH bar" not in text


@pytest.mark.parametrize("width", (44, 40, 38, 34))
async def test_the_shed_bar_label_is_announced_and_not_dropped_in_silence(width):
    """The bar label is not free to lose: the module's own docstring calls it
    "the only reason the volume line means anything", because a sparkline's
    scale is relative to its own window and the survival threshold is the
    only thing an hour's volume is judged against.

    Between 38 and 45 columns it used to disappear under a clean ``TRENDS``:
    the marker fired only when the *trend value* went, two tiers later.  A
    shed column that is not announced is indistinguishable from data that is
    not there — wp4.md's ground rule, and this panel was the one exception.
    """
    text = await _spark_at(width)
    assert "ETH bar" not in text          # it really is shed at this width
    assert "widen" in text                # ...and the title says so


async def test_the_bar_label_and_the_marker_are_never_both_present():
    """The complement: a marker that is always on says nothing (the
    fwa_signals trap), so the widest tier carries no marker at all."""
    text = await _spark_at(60)
    assert "5.00 ETH bar" in text
    assert "widen" not in text


# ===========================================================================
# WP4.5 — CuratorSignals (the seven-row rail)
# ===========================================================================


def _signals_full() -> dict:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (a judged hour with a live deficit, a HourSaved and a nonzero balance
    #  have all never been observed on chain; capture B/C are the windows)
    return dict(
        phase="judged",
        settled=False,
        sig_settled_state="ok",
        sig_at_risk_state="fired",
        first_judged_hour=24,
        hour_needed_eth=1.4,
        hour_seconds_left=753,
        last_saved_hour=26,
        last_saved_wallet="0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
        last_saved_age_s=720,
        whale_amount_eth=461.1,
        whale_wallet="0x381fe4861234567890abcdef1234567890abCDEF",
        whale_age_s=180,
        clusters_count=1,
        flagged_points_share_pct=12.4,
        forced_eth=0.0,
        rescued_total_eth=None,
        you_rank=12,
        you_points=1234,
        you_credit_eth=3.6,
        you_required_next_eth=4.1,
        you_marginal_points=120,
    )


def test_the_rail_renders_exactly_the_frozen_signal_rows():
    """Seven rows, in ``SIGNAL_ROWS`` order, ending in ``you``.

    The tuple used to end in ``rescued``, which contradicted every spec the
    widget author reads; ``rescued_total_eth`` renders inside FORCED ETH.
    """
    from maxpane_dashboard.data.curator_models import SIGNAL_ROWS
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    assert sig_mod.SIGNAL_KEYS == SIGNAL_ROWS
    assert len(SIGNAL_LABELS) == len(SIGNAL_ROWS) == 7
    assert SIGNAL_ROWS[-1] == "you" and SIGNAL_LABELS[-1] == "YOU"


def test_the_rail_knows_exactly_the_frozen_state_vocabulary():
    from maxpane_dashboard.data.curator_models import CURATOR_SIGNAL_STATES
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    assert sig_mod.SIGNAL_STATES == CURATOR_SIGNAL_STATES


def test_the_label_cell_is_sized_to_the_labels_the_rail_actually_renders():
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    assert sig_mod.LABEL_COLS == max(len(label) for label in SIGNAL_LABELS)


async def test_all_seven_rows_reach_the_compositor():
    """The FWA coverage-badge lesson: a rail inside a fixed-height row loses
    its LAST row first, and YOU is last.  Pinned at the rail's real height —
    title + spacer + seven rows."""
    for height in (24, 9):
        text = await _rendered(CuratorSignals, size=(80, height), **_signals_full())
        for label in SIGNAL_LABELS:
            assert label in text, (height, label)


async def test_an_unknown_state_is_never_rendered_as_ok():
    """``None`` is the third state of ``isSettled()`` and it is not False."""
    text = await _rendered(CuratorSignals, settled=None, sig_settled_state=None)
    assert "list open" not in text and "list FROZEN" not in text
    assert "unknown" in text


async def test_hour_at_risk_says_n_a_during_grace_and_never_goes_blank():
    text = await _rendered(
        CuratorSignals, phase="grace", sig_at_risk_state="ok",
        hour_needed_eth=None, first_judged_hour=24,
    )
    assert "n/a until hour 24" in text


async def test_the_first_judged_hour_is_read_from_the_payload():
    """``24`` is ``gracePeriod // hourDuration`` on *this* deployment; a
    literal would be wrong on the next one and neither operand is in the flat
    dict."""
    text = await _rendered(
        CuratorSignals, phase="grace", first_judged_hour=48, hour_needed_eth=None
    )
    assert "n/a until hour 48" in text
    assert "hour 24" not in text


async def test_a_judged_hour_distinguishes_a_zero_deficit_from_an_unknown_one():
    """``ethNeededThisHour()`` is 0 whenever a judged hour is already safe —
    a real answer.  ``None`` is a failed read and must never light the row."""
    safe = await _rendered(
        CuratorSignals, phase="judged", hour_needed_eth=0.0, hour_seconds_left=900
    )
    assert "hour is safe" in safe
    unknown = await _rendered(
        CuratorSignals, phase="judged", hour_needed_eth=None, hour_seconds_left=900
    )
    assert "hour is safe" not in unknown and "needs" not in unknown


async def test_forced_eth_expects_a_dash_and_shouts_on_a_nonzero():
    """H5.  Zero is the expected, healthy state and renders quietly.  Any
    nonzero value is an anomaly — forced ETH, never a deposit — and must be
    visually distinct."""
    assert EMDASH in await _rendered(CuratorSignals, forced_eth=0.0)
    loud = await _rendered(CuratorSignals, forced_eth=1.5)
    assert "1.5" in loud and "forced" in loud.lower()
    # Scanned on the row itself, not the rail: "HOUR AT RISK" is a mandated
    # PRD §4 label and it contains "at risk" -- of the *hour* failing, which
    # is the one thing on this dashboard genuinely at risk.  A rail-wide grep
    # for that phrase reports the honest label and misses nothing else, so
    # the money words are scanned where money words would go.
    row = next(line for line in loud.splitlines() if "FORCED ETH" in line)
    for banned in ("TVL", "balance held", "locked", "at risk", "capital"):
        assert banned.lower() not in row.lower(), banned
    for banned in ("TVL", "locked", "capital"):
        assert banned.lower() not in loud.lower(), banned


async def test_the_swept_total_rides_in_the_forced_row_not_a_row_of_its_own():
    """``rescued_total_eth`` is real and rare; the rail has no eighth row to
    give it, and YOU is the row that would have been pushed off."""
    text = await _rendered(CuratorSignals, forced_eth=1.5, rescued_total_eth=0.5)
    assert "0.50 ETH swept" in text
    assert "RESCUED" not in text


async def test_hour_saved_renders_a_never_fired_state_rather_than_waiting():
    """HourSaved may never fire in this game's whole life.  A permanently
    blank row is indistinguishable from a broken one."""
    assert NEVER_SAVED in (await _rendered(CuratorSignals, last_saved_hour=None))
    fired = await _rendered(
        CuratorSignals, last_saved_hour=26,
        last_saved_wallet="0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
        last_saved_age_s=720,
    )
    assert "hour 26" in fired and "0x200e" in fired


async def test_the_three_log_fed_rows_agree_when_the_logs_pool_is_dead():
    """HOUR SAVED, WHALE and FARM are folded from the same group, and all
    three must say ``-- unknown`` when it is degraded.

    They did not.  FARM could tell "read it, found nothing" from "did not
    read" because ``clusters_count`` has a representable zero; the other two
    have none -- ``last_saved_hour`` and ``whale_amount_eth`` are ``None`` for
    both facts -- so they rendered a confident green ``none yet`` /
    ``none this hour`` off a refresh that could not look.  Live-state /
    dead-logs is the *expected* outage here (CLAUDE.md: state and logs need
    different endpoint pools), not a corner.
    """
    dead = await _rendered(
        CuratorSignals,
        last_saved_hour=None,
        whale_amount_eth=None,
        clusters_count=None,
        degraded=["logs"],
    )
    rows = {
        label: line
        for label in ("HOUR SAVED", "WHALE", "FARM")
        for line in dead.splitlines()
        if label in line
    }
    assert set(rows) == {"HOUR SAVED", "WHALE", "FARM"}
    for label, line in rows.items():
        assert "unknown" in line, f"{label}: {line!r}"
        assert NEVER_SAVED not in line and "none this hour" not in line, label
        assert UNKNOWN_GLYPH in line, label

    # ...and the real negatives survive: a healthy read that found nothing
    # still says so, which is the whole point of keeping the two apart.
    quiet = await _rendered(
        CuratorSignals,
        last_saved_hour=None,
        whale_amount_eth=None,
        clusters_count=0,
        degraded=[],
    )
    assert NEVER_SAVED in quiet and "none this hour" in quiet


@pytest.mark.parametrize("groups", [["state"], ["wallet"], ["state", "wallet"]])
async def test_another_groups_outage_does_not_touch_the_log_fed_rows(groups):
    """Only the group these rows are folded from may unknown them."""
    text = await _rendered(
        CuratorSignals, last_saved_hour=None, whale_amount_eth=None,
        degraded=groups,
    )
    assert NEVER_SAVED in text and "none this hour" in text


def test_the_widget_spells_the_degraded_group_the_frozen_way():
    """``LOGS_GROUP`` is restated in the widget because ``widgets/`` may not
    import ``data/``; this is the agreement half."""
    from maxpane_dashboard.data.curator_models import CURATOR_DEGRADED_GROUPS
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    assert sig_mod.LOGS_GROUP in CURATOR_DEGRADED_GROUPS


async def test_the_farm_row_uses_pattern_language():
    text = await _rendered(
        CuratorSignals, clusters_count=1, flagged_points_share_pct=12.4
    )
    assert "fan-out" in text.lower()
    for word in ("sybil", "cheat", "fraud", "attack"):
        assert word not in text.lower(), word


async def test_the_farm_row_separates_no_clusters_from_no_analysis():
    none_found = await _rendered(CuratorSignals, clusters_count=0)
    assert "no fan-out patterns" in none_found
    not_run = await _rendered(CuratorSignals, clusters_count=None)
    assert "no fan-out patterns" not in not_run and "unknown" in not_run


async def test_the_you_row_is_absent_not_zeroed_when_no_wallet_is_configured():
    """All YOU keys None means MAXPANE_WALLET is unset.  'rank --, 0 pts'
    reads as a wallet with no score; the honest render names the variable."""
    text = await _rendered(CuratorSignals, you_rank=None, you_points=None)
    assert NO_WALLET in text
    assert "0 pts" not in text


async def test_the_you_row_carries_the_credit_the_first_kwarg_table_forgot():
    """Amendment 3: ``you_credit_eth`` stays a key and reaches this row —
    the honest YOU line is ``rank · pts · credit · next ≥``."""
    text = await _rendered(CuratorSignals, size=(90, 24), **_signals_full())
    assert "rank 12" in text and "1,234 pts" in text
    assert "3.60 credit" in text and "next ≥ 4.10 ETH" in text


async def test_every_state_carries_a_glyph_or_a_word_not_only_a_colour():
    text = await _rendered(CuratorSignals, **_signals_full())
    assert any(glyph in text for glyph in ("▶", "◐", "●"))


def test_the_four_states_have_four_distinct_glyphs_so_the_rail_reads_grey():
    """The rail's docstring promises colour is never the sole carrier.  It
    was, for the ``ok``/unknown pair: both mapped to ``●`` and only the style
    token separated them, so a reader in greyscale — or a colour-blind one —
    saw a healthy dot for a reading nobody made."""
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    glyphs = [sig_mod._STATE_STYLE[state][0]
              for state in (None, "ok", "watch", "fired")]
    assert len(set(glyphs)) == 4, glyphs
    assert sig_mod._STATE_STYLE[None][0] == UNKNOWN_GLYPH != sig_mod._STATE_STYLE["ok"][0]


@pytest.mark.parametrize("value", (None, "", "garbage", "OK!", 0, 3))
async def test_an_unreadable_state_word_never_borrows_the_ok_or_fired_glyph(value):
    """``_state_of``'s fallback is the whole state→colour mapping's only
    guard and nothing asserted it: two independent mutations of it (unknown →
    ``ok``, unknown → ``fired``) left the entire suite green, so an
    unreadable signal could have rendered as a green healthy dot or a red
    alarm and no test would have noticed.

    Asserted on the composited glyph rather than on the style token: the
    glyph is what a reader actually resolves, and it is what makes the
    docstring's greyscale promise true.  The grace arm is the vehicle because
    it returns the state word bare, with no "unknown" word beside it to make
    the mistake visible.
    """
    text = await _rendered(
        CuratorSignals, phase="grace", first_judged_hour=24,
        sig_at_risk_state=value,
    )
    row = next(line for line in text.splitlines() if "HOUR AT RISK" in line)
    assert UNKNOWN_GLYPH in row, (value, row)
    for borrowed in ("●", "◐", "▶"):
        assert borrowed not in row, (value, borrowed, row)


async def test_an_unreadable_phase_never_calls_an_unjudged_hour_safe():
    """``phase`` is ``None`` whenever ``isSettled()`` or the ``once`` tier
    failed — and ``ethNeededThisHour()`` answers **0** all the way through
    grace, so falling through to the judged branch rendered a green
    ``hour is safe`` about an hour nobody has judged.  The hero already
    handles this input correctly and ``analytics.at_risk_state`` returns
    ``(None, "phase unavailable")`` for it; this row used to be the one
    surface that contradicted both."""
    for phase in (None, "", "frozen"):
        text = await _rendered(
            CuratorSignals, phase=phase, hour_needed_eth=0.0,
            hour_seconds_left=900,
        )
        row = next(line for line in text.splitlines() if "HOUR AT RISK" in line)
        assert "hour is safe" not in row, phase
        assert PHASE_UNAVAILABLE in row, phase
        assert UNKNOWN_GLYPH in row, phase


async def test_the_forced_row_separates_a_zero_balance_from_an_unreadable_one():
    """The twin of ``test_a_judged_hour_distinguishes_a_zero_deficit_from_an
    _unknown_one``, and the one row in the family that was missing it: the
    mutation ``if forced is None: forced = 0.0`` left the suite green, and it
    renders a failed balance read as the healthy em dash with a green glyph —
    on the row whose entire purpose is anomaly detection.

    The general guard ``test_no_widget_renders_a_bare_zero_for_a_missing
    _value`` cannot reach it: the false-healthy render is ``—``, not a zero.
    """
    zero = await _rendered(CuratorSignals, forced_eth=0.0)
    row = next(line for line in zero.splitlines() if "FORCED ETH" in line)
    assert EMDASH in row

    unknown = await _rendered(CuratorSignals, forced_eth=None)
    row = next(line for line in unknown.splitlines() if "FORCED ETH" in line)
    assert EMDASH not in row and "unknown" in row
    assert UNKNOWN_GLYPH in row


#: The capture's **rank-1** wallet, ``0x75d5…b074`` — 30 853 points, a 490.90
#: ETH high-water mark and ``requiredNext = highWater + minEscalation``.  The
#: widest real YOU row in
#: ``tests/fixtures/curator/screen/grace_payload.json``, restated here so the
#: widget suite stays free of the screen's fixtures; the values are asserted
#: against that file by
#: ``test_the_captured_rank_one_wallet_is_the_one_this_suite_measures``.
def _signals_captured_you() -> dict:
    return dict(
        _signals_full(),
        you_rank=1,
        you_points=30_853,
        you_credit_eth=490.9,
        you_required_next_eth=491.0,
        you_marginal_points=3,
    )


def _worst_case_signals() -> dict:
    """The payload :data:`SIGNALS_FULL_WIDTH` is derived from.

    Taken from the module rather than restated: the point of the composited
    tests below is that the *rendered* rail agrees with the derivation, and a
    second copy of the probe would let the two drift.
    """
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    return dict(sig_mod.WIDTH_PROBE)


def test_the_captured_rank_one_wallet_is_the_one_this_suite_measures():
    """The restated YOU values above are the producer's, not a plausible
    typing of them.  Without this the suite could re-measure the constant
    against a wallet the manager never emits — the exact failure the constant
    has already had twice."""
    import json
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures" / "curator" / "screen" / "grace_payload.json"
    )
    payload = json.loads(fixture.read_text("utf-8"))
    mine = _signals_captured_you()
    for key in ("you_rank", "you_points", "you_credit_eth",
                "you_required_next_eth", "you_marginal_points"):
        assert mine[key] == payload[key], key


def test_the_published_width_is_the_panels_worst_case_not_one_fixtures():
    """**Three numbers have stood in this constant and only the third is a
    property of the panel.**

    76 came off an example row in a docstring; at 76 the rail rendered by
    silently dropping ``next ≥ 4.10 ETH (+120 pts)``.  82 was measured — but
    against ``_signals_full()``, an invented four-figure wallet — so WP6's
    screen sweep, run against the capture's rank-1 wallet, needed **84** and
    reported the disagreement.  Re-measuring against that better fixture
    would have been the same mistake a third time: the YOU row's width is a
    function of the *reader's own* credit and the reader is not on the
    captured list.

    So the constant is the worst case over the producer's whole vocabulary,
    and this test pins the ordering that makes it one: it must clear the
    invented wallet, the widest real wallet in the capture, and the two
    numbers that were published before it.
    """
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    invented = sig_mod.measure_signals_width(_signals_full())
    captured = sig_mod.measure_signals_width(_signals_captured_you())

    assert invented == 82, invented          # the number wp4.md published
    assert captured == 84, captured          # what WP6's screen sweep found
    assert SIGNALS_FULL_WIDTH > captured > invented > 76
    assert SIGNALS_FULL_WIDTH == sig_mod.measure_signals_width(
        sig_mod.WIDTH_PROBE
    )


def test_the_width_probe_carries_every_field_at_its_widest():
    """A probe is only worth the reasons behind its entries, so each one is
    asserted against the bound it claims.

    The point ceiling is the load-bearing one and it is the one a widget
    cannot check for itself: ``widgets/`` may not import ``analytics/``, so
    the literal lives in the widget and the agreement lives here — the
    pattern this suite already uses for ``SIGNAL_ROWS`` and the cluster
    fold's span.
    """
    from maxpane_dashboard.analytics.curator_signals import points_for_weight
    from maxpane_dashboard.widgets.curator import _fmt
    from maxpane_dashboard.widgets.curator import leaderboard as lb_mod
    from maxpane_dashboard.widgets.curator import signals as sig_mod

    # creditCap and POINTS_PER_ETH, from the capture's own `once` tier
    # (tests/fixtures/curator/screen/README.md): 1000e18 and 1000.  Lifetime
    # weight telescopes to at most 2 * creditCap -- the contract's own
    # argument for the uint96 cast in `_credit`.
    credit_cap_wei = 1000 * 10**18
    ceiling = points_for_weight(2 * credit_cap_wei, 1000)
    assert sig_mod.MAX_CURVE_POINTS == ceiling == 44_721
    # ...and the leaderboard's own cell is sized from the same ceiling.
    assert lb_mod._POINTS_COLS >= len(f"{ceiling:,}")

    # The cluster table's POINTS cell is the same ceiling times the largest
    # cluster that module admits: a row's `points` is the SUM over its
    # members (`_cluster_rows`), which a per-wallet ceiling does not bound.
    from maxpane_dashboard.widgets.curator import clusters as cl_mod

    assert cl_mod.MAX_CLUSTER_POINTS == (10**cl_mod.MAX_SIZE_COLS - 1) * ceiling
    assert cl_mod._POINTS_COLS >= len(f"{cl_mod.MAX_CLUSTER_POINTS:,}")

    assert sig_mod._WIDEST_ETH == max(_fmt.COMPACT_ETH_PROBE)

    # Every field of the widest *real* payload is inside the probe.
    captured = _signals_captured_you()
    probe = sig_mod.WIDTH_PROBE
    for key in ("you_rank", "you_points", "you_credit_eth",
                "you_required_next_eth", "you_marginal_points",
                "whale_amount_eth", "clusters_count"):
        assert probe[key] >= captured[key], key
    # 2 291 wallets on the captured list; the probe is a decade past it.
    assert probe["you_rank"] >= 10 * 2_291

    # ...and a kwarg added to the rail cannot slip past the probe unmeasured.
    kwargs = {
        name
        for name, p in inspect.signature(CuratorSignals.update_data)
        .parameters.items()
        if p.kind is not p.VAR_KEYWORD and name != "self"
    }
    assert set(probe) == kwargs, sorted(kwargs ^ set(probe))

    # `degraded` is the one probe entry that is not a maximum: a dead group
    # replaces a row's parts with `-- unknown`, which is narrower than every
    # value it stands in for.  Pinned rather than asserted in prose.
    for groups in ([sig_mod.LOGS_GROUP], ["state", sig_mod.LOGS_GROUP, "wallet"]):
        assert sig_mod.measure_signals_width({**probe, "degraded": groups}) <= (
            sig_mod.SIGNALS_FULL_WIDTH
        )


async def test_the_rail_needs_the_width_it_publishes():
    """The other half, composited: at the published width the worst-case row
    reaches the screen whole, and one column under it the rail *says* it
    could not.

    This is the assertion that bites when the derivation is wrong rather
    than the probe — a forgotten ``padding: 0 1`` in the ``+ 2``, or a copy
    edit that grows a row the probe does not exercise.  A test comparing the
    constant to its own formula could not.
    """
    fits = await _rendered(
        CuratorSignals, size=(SIGNALS_FULL_WIDTH, 24),
        **_worst_case_signals(),
    )
    assert "next ≥ 99,999.00 ETH (+44,721 pts)" in fits
    assert "widen" not in fits

    cut = await _rendered(
        CuratorSignals, size=(SIGNALS_FULL_WIDTH - 1, 24),
        **_worst_case_signals(),
    )
    assert "next ≥ 99,999.00 ETH" not in cut
    assert "widen" in cut


async def test_the_captured_wallet_starves_at_the_width_wp4_first_published():
    """WP6's finding, pinned so it cannot come back.

    At 82 — the constant as wp4.md published it — the rail renders the
    capture's rank-1 wallet by dropping ``next ≥ 491.00 ETH``, the only
    actionable number it carries.  It says so, which is why this was a
    measurement error rather than a silent clip; the error was in the number
    a screen would have budgeted from.
    """
    for width in (82, 83):
        cut = await _rendered(
            CuratorSignals, size=(width, 24), **_signals_captured_you()
        )
        assert "next ≥ 491.00 ETH" not in cut, width
        assert "widen" in cut, width

    fits = await _rendered(
        CuratorSignals, size=(84, 24), **_signals_captured_you()
    )
    assert "next ≥ 491.00 ETH (+3 pts)" in fits
    assert "widen" not in fits


async def test_a_narrow_rail_drops_parts_from_the_end_and_says_so_when_starved():
    widget = CuratorSignals()
    app = _Harness(widget)
    async with app.run_test(size=(30, 12)) as pilot:
        widget.update_data(**_signals_full())
        await pilot.pause()
        text = _screen_text(app)
    for label in SIGNAL_LABELS:
        assert label in text, label          # the head never shrinks
    assert "widen" in text


# ===========================================================================
# WP4.6 — CuratorActivity
# ===========================================================================


def _act_row(**over) -> dict:
    """One ``Deposited`` row, shaped by CURATOR_ROW_KEYS["activity_rows"].

    The numbers are the captured witness of the weight formula: the announce
    EOA's deposit #1, 0.05 ETH at 19975 bps -> 0.099875 weight, block
    25769888.  The tx hash is that row's, truncated to a plausible shape.
    """
    row = {
        "ts": 1786910400,
        "address": "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
        "amount_eth": 3.6,
        "credited_eth": 2.8,
        "new_weight": 7.03,
        "tx_count": 4,
        "hour": 1,
        "kind": "deposit",
        "name": None,
        "tx_hash": "0x240bf1a800000000000000000000000000000000000000000000000000000001",
        "log_index": 12,
    }
    row.update(over)
    return row


def _act_rows() -> list[dict]:
    return [_act_row()]


def test_the_activity_columns_are_the_frozen_row_keys():
    from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS

    assert set(_act_row()) == set(CURATOR_ROW_KEYS["activity_rows"])


def test_the_kind_cell_is_sized_to_the_vocabulary_its_producer_emits():
    """The dev/ops lesson (CLAUDE.md).  The producer emits exactly
    {deposit, joined, saved}; a cell wider than 'deposit' is padding on every
    row and a cell narrower is a value cut mid-word."""
    from maxpane_dashboard.data.curator_models import CURATOR_ACTIVITY_KINDS
    from maxpane_dashboard.widgets.curator import activity as act_mod

    assert act_mod.KIND_COLS == max(len(k) for k in CURATOR_ACTIVITY_KINDS)


async def test_rows_are_deduped_by_tx_hash_and_log_index():
    """PRD §4.  A re-org replay or an overlapping incremental sweep resends
    rows; without the pair as the key, every deposit renders twice and the
    feed silently doubles the game's apparent activity."""
    dup = _act_rows() + _act_rows()
    text = await _rendered(CuratorActivity, activity_rows=dup)
    assert text.count("tx#4") == 1


async def test_two_logs_from_one_transaction_both_survive_the_dedupe():
    """The other half, and the reason the key is a *pair*: a wallet's first
    deposit emits ``Deposited`` and ``FirstDeposit`` in one transaction, and
    a saving deposit emits ``HourSaved`` with it.  Keying on the hash alone
    deletes a real row while still failing to catch a replay."""
    same_tx = [
        _act_row(kind="deposit", log_index=12, tx_count=4),
        _act_row(kind="joined", log_index=13, tx_count=4,
                 amount_eth=0.05, credited_eth=0.05, new_weight=0.099875),
    ]
    text = await _rendered(CuratorActivity, activity_rows=same_tx)
    assert "deposit" in text and "joined" in text


async def test_a_missing_timestamp_renders_dashes_not_the_epoch():
    """WP2.8's stamp can fail.  ``ts=None`` renders ``--:--``; a 0 would
    render ``00:00`` on 1970-01-01, which looks like data."""
    text = await _rendered(CuratorActivity, activity_rows=[_act_row(ts=None)])
    assert NO_STAMP in text and "00:00" not in text
    zero = await _rendered(CuratorActivity, activity_rows=[_act_row(ts=0)])
    assert NO_STAMP in zero and "00:00" not in zero


async def test_every_formatting_step_degrades_independently():
    """MEDI-37: one unparseable field costs its own cell, not the row and not
    the panel."""
    broken = _act_row(amount_eth="not a number", new_weight=None,
                      tx_count="seven")
    text = await _rendered(CuratorActivity, activity_rows=[broken])
    assert "0x200e" in text            # the row still rendered
    assert "not a number" not in text and "seven" not in text


async def test_a_zero_credit_is_a_real_reading_and_not_an_unknown_one():
    """H3: a deposit above the 1000 ETH cap credits nothing and still counts
    fully toward the hour's survival.  ``+0.00`` is the answer; ``--`` is
    what a failed read looks like, and nothing divides by either."""
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (no deposit above the cap has ever landed; the largest is 461.1 ETH)
    capped = _act_row(amount_eth=1200.0, credited_eth=0.0, new_weight=1000.0)
    text = await _rendered(CuratorActivity, activity_rows=[capped])
    assert "+0.000 credit" in text or "+0.00 credit" in text
    unknown = await _rendered(
        CuratorActivity, activity_rows=[_act_row(credited_eth=None)]
    )
    assert f"{DASH} credit" in unknown


async def test_a_none_list_and_an_empty_list_render_differently():
    dead = await _rendered(CuratorActivity, activity_rows=None)
    empty = await _rendered(CuratorActivity, activity_rows=[])
    assert ACTIVITY_UNAVAILABLE in dead
    assert ACTIVITY_EMPTY in empty
    assert ACTIVITY_EMPTY not in dead and ACTIVITY_UNAVAILABLE not in empty


async def test_the_first_deposit_and_saved_rows_are_tagged_in_words():
    """Colour is never the sole carrier: the kind cell spells it out."""
    rows = [
        _act_row(kind="saved", log_index=1),
        _act_row(kind="joined", log_index=2),
        _act_row(kind="deposit", log_index=3),
    ]
    text = await _rendered(CuratorActivity, activity_rows=rows)
    for kind in ("saved", "joined", "deposit"):
        assert kind in text, kind


async def test_the_feed_caps_its_rows_and_says_so_in_code():
    from maxpane_dashboard.widgets.curator import activity as act_mod

    many = [_act_row(log_index=i, tx_count=i) for i in range(60)]
    text = await _rendered(CuratorActivity, activity_rows=many, size=(143, 40))
    rendered = [line for line in text.splitlines() if "0x200e" in line]
    assert len(rendered) == act_mod.MAX_ROWS == 25


async def test_a_hostile_kind_or_address_renders_literally():
    row = _act_row(kind="[/x]", address="[/x]")
    text = await _rendered(CuratorActivity, activity_rows=[row])
    assert "[/x]" in text


def _widest_act_row() -> dict:
    """The widest row the producer can emit, and a real one.

    The 461.1 ETH deposit is the largest send in the 2026-08-16 captures and
    it took the leaderboard's top wallet to 899.00 weight, so its delta cell
    is ``(+461.10 credit → 899.00 wt)`` — 28 columns, where the *sample* row
    in the module docstring is 24.  Every width assertion below measures
    against this row: the tiers were sized against the sample, so the panel
    clipped its own headline event dark at four widths and reported nothing.
    """
    return _act_row(
        address="0x381fe4861234567890abcdef1234567890abCDEF",
        amount_eth=461.1, credited_eth=461.1, new_weight=899.0, tx_count=12,
    )


async def _feed_at(width: int, rows) -> str:
    widget = CuratorActivity()
    app = _Harness(widget)
    async with app.run_test(size=(width, 12)) as pilot:
        widget.update_data(activity_rows=rows)
        await pilot.pause()
        return _screen_text(app)


@pytest.mark.parametrize(
    "width,shed",
    [(143, ""), (79, ""), (71, "credit wording"), (51, "credit + weight"),
     (41, "credit, weight, tx"), (33, "kind, credit, weight, tx")],
)
async def test_narrow_feeds_announce_the_fields_they_shed(width, shed):
    text = await _feed_at(width, _act_rows())
    assert "0x200e" in text          # the identifying cell never goes
    if shed:
        assert "widen" in text
    else:
        assert "widen" not in text


@pytest.mark.parametrize(
    "width,tail",
    # Each boundary is ONE column wider than it was: the identity cell holds a
    # name now (PRD §13 A9).  The tails are unchanged, which is the point --
    # the largest real deposit still survives every tier.
    [(143, "(+461.10 credit → 899.00 wt)  tx#12"),
     (78, "(+461.10 credit → 899.00 wt)  tx#12"),   # the full tier's floor
     (68, "(+461.10 → 899.00)  tx#12"),             # compact's
     (48, "461.10Ξ  tx#12"),                        # narrow's
     (40, "461.10Ξ"),                               # minimal's
     (33, "461.10Ξ")],                              # floor's
)
async def test_the_largest_captured_deposit_survives_every_tier_boundary(
    width, tail
):
    """``RichLog`` is composed ``wrap=False``, so ``write()`` narrows an
    over-wide line at write time with **no** ``…`` and nothing in the title.
    A tier whose declared cost is under what its own row needs therefore
    clips in perfect silence — which is the single failure the tiers exist to
    prevent, and it is what a sweep run against the narrow sample row cannot
    see.  Each width here is the narrowest terminal its tier claims to fit.
    """
    text = await _feed_at(width, [_widest_act_row()])
    assert tail in text, width


@pytest.mark.parametrize("width", (73, 74, 75, 76))
async def test_the_widths_that_used_to_clip_the_whale_row_now_announce_it(width):
    """The regression, pinned at the widths that had it.  ``FULL_WIDTH`` was
    70 where this row needs 74, so 73-76 rendered the full layout and let
    ``write()`` eat the ``tx#12`` — no ``…``, no marker, no way for a reader
    to know the cell was there.  Now they drop to the compact tier and say
    so."""
    text = await _feed_at(width, [_widest_act_row()])
    assert "widen" in text
    assert "tx#12" in text            # the cell that used to be eaten


def test_the_feeds_cells_are_sized_from_the_formatter_not_from_an_example():
    """``COMPACT_ETH_COLS`` is measured off ``fmt_eth_compact`` itself, so a
    cell cannot be sized to whichever row the author had on screen."""
    from maxpane_dashboard.widgets.curator import activity as act_mod
    from maxpane_dashboard.widgets.curator._fmt import (
        COMPACT_ETH_COLS,
        COMPACT_ETH_PROBE,
    )

    assert COMPACT_ETH_COLS == max(len(fmt_eth_compact(v))
                                   for v in COMPACT_ETH_PROBE) == 6
    # ...and it is not a universal bound; the probe is the contract's range.
    assert len(fmt_eth_compact(999_999.0)) == 7
    widest = _widest_act_row()
    assert len(act_mod._delta_cell(widest, "full")) == act_mod._DELTA_COLS == 28
    assert len(act_mod._delta_cell(widest, "compact")) <= act_mod._DELTA_SHORT_COLS
    # 75, not 74: the identity cell holds a NAME now (PRD §13 A9) and
    # `surfsurf.eth` is one column wider than a truncated address.  One is all
    # the screen can afford -- see NAME_COLS' own note for the sweep.
    from maxpane_dashboard.widgets.curator._fmt import ADDR_COLS, NAME_COLS
    assert NAME_COLS - ADDR_COLS == 1
    assert act_mod.FULL_WIDTH == 75


# ===========================================================================
# WP4.7 — CuratorClosestCalls
# ===========================================================================


def _call_rows() -> list[dict]:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (no hour has been judged yet; capture B is the window)
    return [
        {"hour": 26, "volume_eth": 5.42, "margin_eth": 0.42, "savior": None,
         "savior_name": None},
        {"hour": 25, "volume_eth": 61.0, "margin_eth": 56.0, "savior": None,
         "savior_name": None},
        {"hour": 24, "volume_eth": 5.0, "margin_eth": 0.0,
         "savior": "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
         "savior_name": "surfsurf.eth"},
    ]


def test_the_closest_call_columns_are_the_frozen_row_keys():
    from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS

    assert set(_call_rows()[0]) == set(CURATOR_ROW_KEYS["closest_call_rows"])


async def test_closest_calls_ascend_by_margin():
    text = await _rendered(CuratorClosestCalls, closest_call_rows=_call_rows())
    rows = [line for line in text.splitlines() if line.strip().startswith("h")]
    order = [line.split()[0] for line in rows]
    assert order == ["h24", "h26", "h25"]


async def test_a_zero_margin_is_a_number_not_a_dash():
    """An hour that survived by nothing at all is the tightest possible call
    and the most interesting row this board can show."""
    text = await _rendered(CuratorClosestCalls, closest_call_rows=_call_rows())
    assert "0.000" in text or "0.00" in text


async def test_an_unsaved_hour_renders_an_em_dash_in_the_savior_column():
    """``HourSaved`` has never fired on chain.  The column says "nobody
    pulled this hour back", which is a fact, rather than going blank."""
    text = await _rendered(
        CuratorClosestCalls,
        closest_call_rows=[{"hour": 26, "volume_eth": 5.42, "margin_eth": 0.42,
                            "savior": None}],
    )
    assert EMDASH in text


async def test_the_pre_judging_state_names_the_instant_from_the_payload():
    """PRD §4's exact state, with the instant read live — a hardcoded date
    would be wrong the moment this dashboard outlives the deployment."""
    text = await _rendered(
        CuratorClosestCalls,
        closest_call_rows=[],
        first_judged_hour=24,
        grace_ends_utc="2026-08-17 19:58:47Z",
    )
    assert f"{NO_JUDGED_HOURS} — judging begins 2026-08-17 19:58:47Z" in text


#: The pre-judging sentence exactly as the grace-phase payload produces it:
#: the captured deployment's ``grace_ends_utc`` and ``first_judged_hour``.
#: Seventy columns, which is where the defect lived — the test above renders
#: at the suite's default 143 and never saw a slot narrower than the string.
_PRE_JUDGING_SENTENCE = (
    f"{NO_JUDGED_HOURS} — judging begins 2026-08-17 19:58:47 UTC · hour 24"
)


@pytest.mark.parametrize("width", (143, 49, 40, 24))
async def test_the_pre_judging_sentence_survives_a_slot_narrower_than_itself(
    width,
):
    """The one sentence this panel exists to say, whole, at every width.

    The note was ``text-wrap: nowrap; text-overflow: ellipsis`` and the
    sentence is **70 columns**; the panel's ``3fr`` share of the curator
    screen's bottom row is about **49** at the screen's own full-layout
    width.  So through the entire grace period — the phase this panel spends
    most of its life in — the screen ellipsised ``· hour 24``, then ``UTC``,
    then the seconds, under a clean ``CLOSEST CALLS`` title.  Truncation with
    no marker is indistinguishable from a payload that carried no hour, which
    is the confusion every explicit state in this package exists to prevent.

    Asserted on the composited text with whitespace collapsed, because the
    fix spends **rows**: the note wraps rather than clipping, so the sentence
    crosses a line break at every width under 70 and is contiguous only once
    the newlines and the row padding are folded away.  ``143`` stays in the
    sweep so a future "just make it one line again" is caught at both ends.
    """
    text = await _rendered(
        CuratorClosestCalls,
        size=(width, 20),
        closest_call_rows=[],
        first_judged_hour=24,
        grace_ends_utc="2026-08-17 19:58:47 UTC",
    )
    assert _PRE_JUDGING_SENTENCE in " ".join(text.split()), width
    assert "…" not in text, width          # the ellipsis glyph, never here


async def test_the_pre_judging_note_wraps_instead_of_raising_a_widen_marker():
    """``‹ widen`` would be the *other* honest fix, and it is the wrong one.

    A marker here would light on the curator screen for the whole grace
    period and could only be cleared by a screen ~72 columns wider than the
    one FWA binds — so the panel would advertise a loss it is not taking.
    Nothing is shed, so nothing is announced: the sentence is bought with the
    spare rows this slot has, exactly as the surf announce feed buys its
    wrapping tier (CLAUDE.md).  The *table*'s own markers are untouched, and
    the next test pins that they still fire.
    """
    text = await _rendered(
        CuratorClosestCalls,
        size=(60, 20),                      # every column set still fits
        closest_call_rows=[],
        first_judged_hour=24,
        grace_ends_utc="2026-08-17 19:58:47 UTC",
    )
    assert _PRE_JUDGING_SENTENCE in " ".join(text.split())
    assert "widen" not in text


async def test_the_wrapping_note_still_carries_the_tables_relocated_marker():
    """The note is where ``‹ widen`` goes when the title bar cannot hold it
    (``_table.title_with_hint`` returns ``placed=False``).  Wrapping must not
    cost that path: at 24 columns the table has shed two column sets and the
    marker rides in front of the sentence, wrapping with it."""
    text = await _rendered(
        CuratorClosestCalls,
        size=(24, 20),
        closest_call_rows=[],
        first_judged_hour=24,
        grace_ends_utc="2026-08-17 19:58:47 UTC",
    )
    assert "widen" in text
    assert _PRE_JUDGING_SENTENCE in " ".join(text.split())


async def test_a_none_list_is_not_the_pre_judging_state():
    dead = await _rendered(CuratorClosestCalls, closest_call_rows=None,
                           grace_ends_utc="2026-08-17 19:58:47Z")
    assert CLOSEST_CALLS_UNAVAILABLE in dead
    assert NO_JUDGED_HOURS not in dead


async def test_a_row_with_an_unreadable_margin_sorts_last_not_first():
    """The top of this board is a claim about how close the game came to
    ending; a missing measurement is not evidence of a close call."""
    rows = _call_rows() + [{"hour": 30, "volume_eth": None, "margin_eth": None,
                            "savior": None}]
    text = await _rendered(CuratorClosestCalls, closest_call_rows=rows)
    ordered = [line.split()[0] for line in text.splitlines()
               if line.strip().startswith("h")]
    assert ordered[-1] == "h30"


# ===========================================================================
# WP4.8 — CuratorClusters
# ===========================================================================


def _cluster_rows() -> list[dict]:
    """The real 2026-08-16 fan-out: ranks 4-12, nine wallets, 60 ETH each,
    inside a six-minute window (about 28 blocks)."""
    return [
        {"size": 9, "amount_eth": 60.0, "first_block": 25769888,
         "last_block": 25769916, "points": 69705, "points_share_pct": 12.4},
    ]


def test_the_cluster_columns_are_the_frozen_row_keys():
    from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS

    assert set(_cluster_rows()[0]) == set(CURATOR_ROW_KEYS["cluster_rows"])


async def test_the_captured_fan_out_renders_as_its_shape():
    text = await _rendered(CuratorClusters, cluster_rows=_cluster_rows())
    assert "9× 60.00Ξ · 28 blocks" in text
    assert "69,705" in text and "12.4%" in text


def test_the_pattern_cell_is_sized_to_the_shapes_the_fold_can_emit():
    """The ``dev``/``ops`` lesson, in the direction that cuts.

    ``_PATTERN_COLS`` was 21 — the width of the *one* captured example,
    ``9× 60.00Ξ · 28 blocks``.  The fold emits any ``size`` from
    ``CLUSTER_MIN_SIZE`` up to every wallet on THE LIST and any span up to
    ``CLUSTER_MAX_BLOCK_SPAN``, so ten wallets is already 22 columns.  The
    widget may not import ``analytics/``; this is the agreement half.
    """
    from maxpane_dashboard.analytics.curator_signals import (
        CLUSTER_MAX_BLOCK_SPAN,
        CLUSTER_MIN_SIZE,
    )
    from maxpane_dashboard.widgets.curator import clusters as cl_mod

    assert cl_mod.MAX_BLOCK_SPAN == CLUSTER_MAX_BLOCK_SPAN
    widest = {"size": 252, "amount_eth": 999.99, "first_block": 0,
              "last_block": CLUSTER_MAX_BLOCK_SPAN, "points": 1,
              "points_share_pct": 1.0}
    assert len(cl_mod._row_values(widest, True)["pattern"]) <= cl_mod._PATTERN_COLS
    assert (len(cl_mod._row_values(widest, False)["pattern"])
            <= cl_mod._PATTERN_SHORT_COLS)
    smallest = {**widest, "size": CLUSTER_MIN_SIZE, "amount_eth": 0.05,
                "last_block": CLUSTER_MIN_SIZE}
    assert len(cl_mod._row_values(smallest, True)["pattern"]) <= cl_mod._PATTERN_COLS


@pytest.mark.parametrize("size,span", [(10, 32), (12, 32), (100, 32), (252, 28)])
async def test_a_fan_out_wider_than_the_captured_one_is_not_cut_mid_word(
    size, span
):
    """At 80 columns a twelve-wallet cluster used to read ``· 32 block`` —
    the trailing ``s`` eaten by the ``DataTable``, on the panel's headline
    value, at full width, with no ``‹ widen``.  Nine wallets fit, so the whole
    suite was green over the one shape that did.

    The ``points`` here is the **live** board's top row (2 663 784 on
    2026-08-17), not the capture's 69 705: every clusters fixture in this file
    used to carry a value that happened to fit ``_POINTS_COLS`` at 8, so this
    test was green while the panel cut its own headline number.
    """
    rows = [{"size": size, "amount_eth": 60.0, "first_block": 0,
             "last_block": span, "points": 2_663_784, "points_share_pct": 12.4}]
    text = await _rendered(CuratorClusters, cluster_rows=rows, clusters_count=1,
                           size=(80, 14))
    assert f"{size}× 60.00Ξ · {span} blocks" in text
    assert "2,663,784" in text
    assert "widen" not in text


@pytest.mark.parametrize("width", [80, 120, 138, 143, 200, 250])
async def test_the_points_cell_holds_the_widest_sum_the_fold_can_emit(width):
    """A cell width is fixed; a panel's width is not, so a cell that is one
    column short cuts at **every** terminal size and no ``‹ widen`` fires --
    the marker reports shed *columns*, not truncated ones.

    The row is the ceiling itself: the largest cluster this module admits, at
    the highest score the curve can return per wallet.
    """
    from maxpane_dashboard.widgets.curator import clusters as cl_mod

    rows = [{"size": 10**cl_mod.MAX_SIZE_COLS - 1, "amount_eth": 10.0,
             "first_block": 0, "last_block": cl_mod.MAX_BLOCK_SPAN,
             "points": cl_mod.MAX_CLUSTER_POINTS, "points_share_pct": 100.0}]
    text = await _rendered(CuratorClusters, cluster_rows=rows, clusters_count=1,
                           size=(width, 14))
    assert f"{cl_mod.MAX_CLUSTER_POINTS:,}" in text, text


async def test_the_share_column_dashes_rather_than_claiming_zero():
    """``points_share_pct`` is None when total points are unknown — a
    division refused, not a zero measured.  ``0.0%`` there would assert that
    these wallets hold none of the score."""
    text = await _rendered(
        CuratorClusters,
        cluster_rows=[{**_cluster_rows()[0], "points_share_pct": None}],
    )
    assert "0.0%" not in text
    assert DASH in text


async def test_an_empty_cluster_list_is_a_real_negative():
    empty = await _rendered(CuratorClusters, cluster_rows=[], clusters_count=0)
    dead = await _rendered(CuratorClusters, cluster_rows=None)
    assert CLUSTERS_EMPTY in empty
    assert CLUSTERS_UNAVAILABLE in dead
    assert CLUSTERS_EMPTY not in dead and CLUSTERS_UNAVAILABLE not in empty


async def test_the_cluster_panel_uses_pattern_language_only():
    """The same forbidden-word list the analytics layer is held to (WP3.10):
    one person spreading a deposit and nine people copying a trade produce
    identical logs, so intent is not something this panel may assert."""
    text = await _rendered(
        CuratorClusters, cluster_rows=_cluster_rows(), clusters_count=1,
        flagged_points_share_pct=12.4,
    )
    assert "fan-out" in text.lower()
    for word in ("sybil", "cheat", "fraud", "attack", "wash", "abuse"):
        assert word not in text.lower(), word


async def test_the_cluster_summary_counts_the_groups_and_their_share():
    text = await _rendered(
        CuratorClusters, cluster_rows=_cluster_rows(), clusters_count=1,
        flagged_points_share_pct=12.4,
    )
    assert "1 fan-out group" in text and "12.4% of all points" in text


@pytest.mark.parametrize(
    "width,shed",
    [(60, ""), (36, "block window"), (26, "block window + POINTS")],
)
async def test_a_narrow_cluster_table_sheds_the_block_window_first(width, shed):
    widget = CuratorClusters()
    app = _Harness(widget)
    async with app.run_test(size=(width, 14)) as pilot:
        widget.update_data(cluster_rows=_cluster_rows(), clusters_count=1)
        await pilot.pause()
        text = _screen_text(app)
    assert "9× 60.00Ξ" in text          # the finding itself never sheds
    if shed:
        assert "widen" in text and "blocks" not in text
    else:
        assert "widen" not in text and "28 blocks" in text


async def test_a_shed_column_is_announced_even_when_the_title_bar_is_too_narrow():
    """Going silent is not an option: below the width the descriptive hint
    needs, the marker moves into the note line rather than disappearing.
    Reached by the cluster panel at 26 columns, where "FAN-OUT PATTERNS" plus
    the bare marker is one column over budget."""
    for cls in (CuratorLeaderboard, CuratorClosestCalls, CuratorClusters):
        widget = cls()
        app = _Harness(widget)
        async with app.run_test(size=(26, 14)) as pilot:
            widget.update_data()
            await pilot.pause()
            text = _screen_text(app)
        assert "widen" in text, cls.__name__


# ===========================================================================
# WP4.9 — the widget contract
# ===========================================================================

#: Every widget this package exports, in screen order.  The map below is
#: derived from these classes rather than hand-typed, so it cannot rot; what
#: *is* hand-typed is this tuple, and
#: ``test_the_signature_map_covers_every_widget_this_package_exports`` is
#: what makes forgetting to add a class to it fail.
_WIDGETS = (
    CuratorHero,
    CuratorLeaderboard,
    CuratorSparklines,
    CuratorSignals,
    CuratorActivity,
    CuratorClosestCalls,
    CuratorClusters,
    # The `y` view's four panels and its own hero (PRD §13 A8).  Same seam,
    # same guarantees: the screen splats the whole flat dict at them too.
    CuratorWalletHero,
    CuratorWalletAddress,
    CuratorWalletLadder,
    CuratorWalletStanding,
    CuratorWalletTarget,
    CuratorWalletNext,
)


def _kwargs_of(cls) -> tuple[str, ...]:
    return tuple(
        name
        for name, param in inspect.signature(cls.update_data).parameters.items()
        if param.kind is not param.VAR_KEYWORD and name != "self"
    )


CURATOR_WIDGET_SIGNATURES: dict[str, tuple[str, ...]] = {
    cls.__name__: _kwargs_of(cls) for cls in _WIDGETS
}

#: The one kwarg the screen supplies that is **not** a manager key: the CLI /
#: ``MAXPANE_WALLET`` address, so the leaderboard can mark the reader's own
#: row.  It is named here so the exception is a decision rather than a hole.
#:
#: It used to be three.  ``hourly_threshold_eth`` and ``first_judged_hour``
#: were about to be hardcoded into a widget ("/5.00 ETH", "n/a until hour
#: 24") because no frozen surface carried them; WP0's 2026-08-17 amendment
#: added both to ``CURATOR_KEYS`` and they are now dispatched from the
#: payload like every other chain value.
_SCREEN_SUPPLIED = {"you_address"}


def _exported_widget_classes() -> set[str]:
    """Widget classes re-exported from ``widgets.curator``'s package root."""
    import maxpane_dashboard.widgets.curator as pkg
    from textual.widget import Widget

    return {
        name
        for name in pkg.__all__
        if isinstance(getattr(pkg, name), type)
        and issubclass(getattr(pkg, name), Widget)
    }


def test_every_widget_kwarg_is_a_curator_key():
    """Containment, from the widget side.  A widget that reads a key the
    manager does not emit renders None forever with a green suite behind it —
    which is exactly what this repo's seam-drift defect class looks like."""
    from maxpane_dashboard.data.curator_models import CURATOR_KEYS

    for cls, sig in CURATOR_WIDGET_SIGNATURES.items():
        unknown = set(sig) - set(CURATOR_KEYS) - _SCREEN_SUPPLIED
        assert not unknown, f"{cls}: {sorted(unknown)}"


def test_the_signature_map_covers_every_widget_this_package_exports():
    """A widget added without an entry here is a widget nobody checks."""
    assert set(CURATOR_WIDGET_SIGNATURES) == _exported_widget_classes()


def test_every_widget_accepts_the_whole_flat_dict():
    """``**_kwargs`` on every ``update_data``: the screen splats the manager
    dict at each widget, so a foreign key must be ignored, not fatal."""
    for cls in _WIDGETS:
        has_var_kw = any(
            p.kind is p.VAR_KEYWORD
            for p in inspect.signature(cls.update_data).parameters.values()
        )
        assert has_var_kw, f"{cls.__name__}.update_data lacks **_kwargs"


def test_every_kwarg_has_a_none_default():
    """House idiom: every kwarg optional, defaulting to ``None``, so a
    partial payload is a degraded render rather than a TypeError."""
    for cls in _WIDGETS:
        for name, param in inspect.signature(cls.update_data).parameters.items():
            if name == "self" or param.kind is param.VAR_KEYWORD:
                continue
            assert param.default is None, f"{cls.__name__}.{name}"


def test_the_keys_no_widget_reads_are_named_here_rather_than_forgotten():
    """The other direction of the seam, from this side: keys that reach no
    widget in this package.  WP6.1 asserts totality against the *screen*,
    which also dispatches to the title bar and the status bar, so this is a
    record rather than a failure — it exists so the next person can tell a
    deliberate omission from a dropped key."""
    from maxpane_dashboard.data.curator_models import CURATOR_KEYS

    dispatched = {k for sig in CURATOR_WIDGET_SIGNATURES.values() for k in sig}
    unread = set(CURATOR_KEYS) - dispatched
    # Everything here belongs to the title bar / status bar (WP6), not to a
    # panel: the freshness marker, the degraded groups, and the two settled
    # keys the hero reads through `settled_hour` / `lived_desc` instead.
    assert unread == {"as_of", "as_of_hhmm", "degraded", "settled_observed_at"} or \
        unread <= {"as_of", "as_of_hhmm", "degraded", "settled_observed_at"}, (
            sorted(unread)
        )


def _full_payload() -> dict:
    """One payload carrying **every** ``CURATOR_KEYS`` entry plus the screen's
    ``you_address`` — splatted at every widget, exactly as the screen will.

    SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    (the judged / at-risk / saved / settled halves of this have no capture
    yet; captures B and C are their windows.)
    """
    return dict(
        phase="judged",
        settled=False,
        settled_hour=None,
        settled_at_ts=None,
        settled_observed_at=None,
        lived_desc="alive 27 h",
        current_hour=27,
        hour_fed_eth=3.6,
        hour_needed_eth=1.4,
        hour_seconds_left=753,
        grace_seconds_left=0,
        grace_ends_utc="2026-08-17 19:58:47Z",
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
        last_saved_hour=26,
        last_saved_wallet="0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
        last_saved_age_s=720,
        whale_amount_eth=461.1,
        whale_wallet="0x381fe4861234567890abcdef1234567890abCDEF",
        whale_age_s=180,
        clusters_count=1,
        flagged_points_share_pct=12.4,
        forced_eth=0.0,
        rescued_total_eth=None,
        sig_settled_state="ok",
        sig_at_risk_state="fired",
        you_rank=12,
        you_points=1234,
        you_credit_eth=3.6,
        you_required_next_eth=4.1,
        you_marginal_points=120,
        # the `y` view (PRD §13 A8)
        you_weight_eth=7.03,
        you_tx_count=4,
        you_first_hour=0,
        you_joined_utc="2026-08-16 19:58 UTC",
        you_weight_share_pct=0.42,
        you_ladder_rows=[
            {"hour": 0, "amount_eth": 1.1, "credited_eth": 1.1, "weight_eth": 2.13,
             "early_x": 1.94, "capped": False, "ts": None},
            {"hour": 1, "amount_eth": 1200.0, "credited_eth": 0.0, "weight_eth": 0.0,
             "early_x": 1.91, "capped": True, "ts": None},
        ],
        you_next_rank=11,
        you_next_rank_needs_eth=604.0,
        you_next_send_passes=False,
        leaderboard_rows=_lb_rows(3),
        activity_rows=[_act_row(log_index=1), _act_row(log_index=2, tx_count=5)],
        closest_call_rows=_call_rows(),
        cluster_rows=_cluster_rows(),
        volume_series=_volume_series(),
        contributors_series=_contributors_series(),
        degraded=[],
        as_of_hhmm="22:58",
        as_of=1787000341.0,
        you_address="0xcB0b0531e86A9aC36Fa865cA8e3dbccF047FDA91",
        you_ens="surfsurf.eth",
        whale_ens=None,
        last_saved_ens=None,
        # ---- the linkage analysis (WP0's eleven) --------------------------
        # The three row lists come from the **committed worst-case slices**
        # rather than from a hand-typed row apiece: the three-way exercise
        # splats this payload at every widget at 143 columns, so taking the
        # slices here is free coverage of the widest strings the analysis can
        # produce, and it cannot drift from the shapes WP3 has to emit.
        operator_rows=worst_case_rows("operator_row_worst.json"),
        operators_count=len(worst_case_rows("operator_row_worst.json")),
        segment_rows=worst_case_rows("segment_rows_worst.json"),
        clean_list_rows=worst_case_rows("clean_list_rows_worst.json"),
        clean_points=_clean_totals()["clean_points"],
        clean_contributors=_clean_totals()["clean_contributors"],
        # Deliberately NOT `as_of_hhmm`: the analysis sweep is a slower tier
        # than the fast one, so the two markers differ in the normal case and
        # a payload that made them equal would hide a panel wired to the
        # wrong one (PRD §5 -- each panel shows its own freshness).
        analysis_as_of_hhmm="22:41",
        # A linked reader, which is the state that exercises the widest
        # rendering: the group size, four reasons, and -- by WP3's contract --
        # NO clean rank, because a linked wallet is removed from that list.
        you_linked_state="linked",
        you_linked_group_size=1995,
        you_linked_reasons=_worst_case_envelope_reasons(),
        you_clean_rank=None,
    )


def _clean_totals() -> dict:
    """The clean-list slice's ``totals`` block — the summary WP4's panel
    renders and the two scalars ``_full_payload`` needs."""
    from tests.curator_sybil_fixtures import worst_case_envelope

    return worst_case_envelope("clean_list_rows_worst.json")["totals"]


def _worst_case_envelope_reasons() -> list[str]:
    """The widest operator's own reasons — the ``worst`` entry, which lives
    **outside** ``rows`` and is the payload a sweep driven by
    ``worst_case_rows`` alone never sees."""
    from tests.curator_sybil_fixtures import worst_case_envelope

    return list(worst_case_envelope("operator_row_worst.json")["worst"]["reasons"])


def test_the_full_payload_is_exactly_the_frozen_contract():
    """The three-way exercise is only worth anything if its "full" payload
    really is full."""
    from maxpane_dashboard.data.curator_models import CURATOR_KEYS

    assert set(_full_payload()) == set(CURATOR_KEYS) | _SCREEN_SUPPLIED


#: What each widget must have on screen after the full payload: the markers
#: a data row carries (any of them), and how many lines must carry one.  Row
#: counts, not just "something rendered" — a panel that quietly drops half
#: its rows passes a smoke test.
_EXPECTED_ROWS = {
    "CuratorHero": (("THE LIST",), 1),
    # One of the three fixture rows carries a verified ENS name, so the
    # marker is "a row rendered an identity", not "a row rendered hex".
    "CuratorLeaderboard": (("0x", ".eth"), 3),
    "CuratorSparklines": (("▲", "▼", "●"), 2),
    "CuratorSignals": (("▶", "◐", "●"), 7),   # the rail's last row is YOU
    "CuratorActivity": (("0x200e",), 2),
    "CuratorClosestCalls": (("h2",), 3),
    "CuratorClusters": (("9×",), 1),
    # The `y` view.  The ladder's marker is the multiplier column, which only a
    # data row carries; the two facts panels are label/value lines.
    "CuratorWalletLadder": (("×",), 2),
    "CuratorWalletStanding": (("rank", "pts", "weight"), 3),
    "CuratorWalletNext": (("≥", "ETH"), 2),
    "CuratorWalletTarget": (("pts", "rank"), 2),
    "CuratorWalletHero": (("YOUR", "#", "pts"), 3),
    "CuratorWalletAddress": (("wallet", "ens"), 2),
}


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("mode", ("no-args", "all-none", "full"))
async def test_the_three_way_exercise(cls, mode):
    """No args, all-``None``, and the whole flat dict — every widget, through
    the compositor, no raise and nothing left saying "Loading"."""
    if mode == "no-args":
        payload = {}
    elif mode == "all-none":
        payload = {name: None for name in _kwargs_of(cls)}
    else:
        payload = _full_payload()

    widget = cls()
    app = _Harness(widget)
    async with app.run_test(size=(143, 30)) as pilot:
        widget.update_data(**payload)
        await pilot.pause()
        text = _screen_text(app)

    assert text.strip(), f"{cls.__name__} rendered an empty screen"
    assert "Loading" not in text
    if mode == "full":
        markers, count = _EXPECTED_ROWS[cls.__name__]
        rendered = [
            line for line in text.splitlines() if any(m in line for m in markers)
        ]
        assert len(rendered) >= count, (cls.__name__, markers, len(rendered))


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
async def test_a_second_update_replaces_rather_than_appends(cls):
    """A refresh every 15 s must not grow the panel; the feed and the tables
    are the ones this bites."""
    widget = cls()
    app = _Harness(widget)
    async with app.run_test(size=(143, 30)) as pilot:
        widget.update_data(**_full_payload())
        await pilot.pause()
        first = _screen_text(app)
        widget.update_data(**_full_payload())
        await pilot.pause()
        assert _screen_text(app) == first, cls.__name__


@pytest.mark.parametrize("cls", _WIDGETS, ids=lambda c: c.__name__)
async def test_no_widget_renders_a_bare_zero_for_a_missing_value(cls):
    """None-vs-0 is the whole point of this dashboard: 0 ETH needed and "we
    could not read what is needed" look nothing alike."""
    widget = cls()
    app = _Harness(widget)
    async with app.run_test(size=(143, 30)) as pilot:
        widget.update_data(**{name: None for name in _kwargs_of(cls)})
        await pilot.pause()
        text = _screen_text(app)
    for banned in ("0.00 ETH", "0 wallets", "0 pts", "rank 0", "0.0%"):
        assert banned not in text, (cls.__name__, banned)


def test_no_theme_token_reaches_the_rich_parsed_activity_feed():
    """``[$warning]`` is Textual *Content* markup.  ``RichLog.write`` parses
    with Rich's own ``Text.from_markup``, which does not know ``$`` tokens and
    raises ``MarkupError`` instead of degrading — the FWA activity-feed crash,
    caught there by eye.  Only string literals are inspected: this docstring
    has to quote the very token it forbids."""
    from maxpane_dashboard.widgets.curator import activity as act_mod

    tree = ast.parse(inspect.getsource(act_mod))
    # Docstrings are excluded: the prose above has to quote the token it
    # forbids, and so does this module's own.  Only *rendered* literals are
    # scanned -- f-strings decompose into Constant parts, so a token inside
    # one still survives as its own segment and is still caught.
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            for token in ("[$success]", "[$error]", "[$warning]", "[$"):
                assert token not in node.value, (token, node.value)


# -- the status bar's opt-in key hints (curator asks; the others must not) ----


def test_the_status_bar_without_hints_is_byte_identical_to_before():
    """Nine other dashboards share this widget: the hints are opt-in, and a
    screen that never calls `set_key_hints` must render exactly what it always
    did -- `tab switch` and `updated Ns ago` included."""
    from maxpane_dashboard.widgets.status_bar import StatusBar

    bar = StatusBar()
    rendered = {}
    bar.query_one = lambda *a, **k: type(
        "Sink", (), {"update": lambda _self, text: rendered.__setitem__("text", text)}
    )()
    bar.update_data(last_updated_seconds_ago=3, error_count=0, poll_interval=30)

    assert "tab[/] switch" in rendered["text"]
    assert "updated 3s ago" in rendered["text"]


def test_hints_replace_tab_switch_and_the_cycle_age_but_never_the_errors():
    """An error count must never be the thing that falls off the end of the
    line, which is why the hints buy their room from `tab switch` too."""
    from maxpane_dashboard.widgets.status_bar import StatusBar

    bar = StatusBar()
    rendered = {}
    bar.query_one = lambda *a, **k: type(
        "Sink", (), {"update": lambda _self, text: rendered.__setitem__("text", text)}
    )()
    bar.set_key_hints("[dim]c[/] panels [dim]·[/] [dim]y[/] wallet")
    bar.update_data(last_updated_seconds_ago=3, error_count=4, poll_interval=30)

    text = rendered["text"]
    assert "c[/] panels" in text and "y[/] wallet" in text
    assert "tab[/] switch" not in text
    assert "updated" not in text
    assert "4 errors" in text
    assert "30s poll" in text


# ===========================================================================
# CuratorWalletAddress — which wallet this view is about (PRD §13 A9)
# ===========================================================================


async def test_the_wallet_panel_names_the_address_in_full():
    """Every other panel describes *a* wallet without naming it; with two
    wallets configured on two machines the pages are indistinguishable."""
    address = "0x047F606fD5b2BaA5f5C6c4aB8958E45CB6B054B7"
    text = await _rendered(CuratorWalletAddress, you_address=address,
                           you_ens="surfsurf.eth")
    assert address.lower() in text
    assert "surfsurf.eth" in text


async def test_the_wallet_panel_shows_a_long_name_whole():
    """The one place with room for it: the tables cap a name at the identity
    cell's width, and a truncated name is exactly when the full one is wanted."""
    long_name = "a-very-long-ens-name-indeed.eth"
    text = await _rendered(CuratorWalletAddress, you_address="0x" + "ab" * 20,
                           you_ens=long_name, size=(60, 10))
    assert long_name in text


async def test_a_wallet_with_no_ens_says_so_rather_than_dashing():
    """Most wallets have no reverse record; a dash reads as a lookup that
    failed."""
    text = await _rendered(CuratorWalletAddress, you_address="0x" + "ab" * 20)
    assert NO_ENS in text


async def test_no_wallet_configured_names_the_two_ways_to_fix_it():
    text = await _rendered(CuratorWalletAddress)
    assert NO_WALLET_SET in text
    assert "0x" not in text


async def test_a_hostile_ens_name_cannot_reach_markup():
    """ENS names are the most attacker-controlled strings on this screen:
    anyone can set a reverse record to `[/x]` and no permission is needed."""
    text = await _rendered(CuratorWalletAddress, you_address="0x" + "ab" * 20,
                           you_ens="[/x][bold red]owned[/]", size=(60, 10))
    assert "[/x]" in text or "owned" in text     # rendered as text, not markup
    assert text.strip(), "a markup-hostile name blanked the panel"


def test_a_name_never_widens_a_table_cell():
    """Every width on this screen was measured against an identity cell of a
    fixed size.  A 255-character name that grew the cell would make every one
    of those measurements fiction."""
    from maxpane_dashboard.widgets.curator._fmt import NAME_COLS, short_label

    for name in ("surfsurf.eth", "a" * 255, "x" * (NAME_COLS + 1), "ok.eth"):
        assert len(short_label(name, "0x" + "ab" * 20)) <= NAME_COLS, name


def test_the_identity_cell_holds_the_names_people_actually_have():
    """12 columns is `surfsurf.eth` exactly -- the measurement that set it."""
    from maxpane_dashboard.widgets.curator._fmt import NAME_COLS, short_label

    assert NAME_COLS == len("surfsurf.eth")
    assert short_label("surfsurf.eth", None) == "surfsurf.eth"
    assert short_label("vitalik.eth", None) == "vitalik.eth"


async def test_a_verified_name_replaces_the_hex_in_the_leaderboard():
    rows = _lb_rows(3)
    text = await _rendered(CuratorLeaderboard, leaderboard_rows=rows)
    assert "surfsurf.eth" in text
    # ...and the wallets without one still render their address.
    assert "0x381f" in text


async def test_a_verified_name_replaces_the_hex_in_the_signal_rows():
    text = await _rendered(
        CuratorSignals,
        whale_amount_eth=42.0,
        whale_wallet="0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
        whale_ens="surfsurf.eth",
        whale_age_s=120,
    )
    assert "surfsurf.eth" in text


# ===========================================================================
# WP5.1 — CuratorWalletStanding: the `linked` line
#
# The `y` view's own answer to "am I in one of the groups the FARM row
# counts".  Three states and they are three different facts: analyzed and
# clear, analyzed and linked, and **not analyzed**, which is the one a
# reassuring default would turn into a lie.
# ===========================================================================


def _standing_full() -> dict:
    """The standing panel's non-linkage kwargs, at PRD §6's own numbers.

    The four linkage kwargs are deliberately **absent**: every test below
    sets the one it is about, and a default here would have the honesty
    tests asserting against a value they did not choose.

    SYNTHETIC — the reader's own standing has no capture and cannot have
    one: the wallet these numbers describe is whoever runs the dashboard.
    The magnitudes are PRD §6's worked example (``#412 raw, #47 with clear
    farms removed``, on a list of 10,643), which is also the example the
    clean-rank line below is measured against.
    """
    return dict(
        you_rank=412,
        you_points=1234,
        you_credit_eth=3.6,
        you_weight_eth=7.03,
        you_tx_count=4,
        you_weight_share_pct=0.42,
        you_first_hour=0,
        you_joined_utc="2026-08-16 19:58 UTC",
        contributors_total=10_643,
    )


async def test_the_linked_line_reads_unknown_before_the_analysis_runs():
    """``None`` is "the sweep has not run", never a confident "clean".

    This is the honesty rule of the whole work package: a green "not linked"
    off an analysis that never ran is a lie in the reassuring direction, and
    the reader has no way to tell it from an answer.
    """
    text = await _rendered(CuratorWalletStanding, you_linked_state=None,
                           **_standing_full())
    assert "unknown" in text
    assert "not linked" not in text          # never a confident negative


async def test_a_clean_wallet_says_not_linked():
    """The representable negative: the sweep ran and found no group."""
    text = await _rendered(CuratorWalletStanding, you_linked_state="clean",
                           you_linked_reasons=[], **_standing_full())
    assert "not linked to any group" in text


async def test_a_linked_wallet_shows_pattern_language_reasons():
    text = await _rendered(
        CuratorWalletStanding, you_linked_state="linked",
        you_linked_group_size=1995,
        you_linked_reasons=["identical 0.45Ξ send", "same funder"],
        **_standing_full())
    assert "1,995" in text and "same funder" in text
    for word in ("sybil", "cheat", "fraud", "attack", "abuse", "wash"):
        assert word not in text.lower(), word


async def test_the_standing_panel_uses_pattern_language_in_every_state():
    """The panel's own forbidden-word test, over every state it can reach and
    over the widest reasons the analysis fixtures actually hold.

    ``CuratorClusters`` and ``CuratorSignals`` each have one of these; this
    panel now renders producer-supplied phrases too, so it needs its own.
    The reasons come from the committed worst-case slice rather than from a
    plausible typing of one — the same rule the width probe below follows.
    """
    from tests.curator_sybil_fixtures import row_payloads

    reasons = [
        reason
        for _label, row in row_payloads("operator_row_worst.json")
        for reason in (row.get("reasons") or [])
    ]
    assert reasons, "the worst-case slice carried no reasons to scan"

    for state, kwargs in (
        (None, {}),
        ("clean", {"you_linked_reasons": []}),
        ("linked", {"you_linked_group_size": 1995,
                    "you_linked_reasons": reasons}),
    ):
        text = await _rendered(
            CuratorWalletStanding, you_linked_state=state,
            size=(300, 24), **kwargs, **_standing_full(),
        )
        for word in ("sybil", "cheat", "fraud", "attack", "abuse", "wash"):
            assert word not in text.lower(), (state, word)


async def test_an_unreadable_linked_state_is_unknown_rather_than_clean():
    """A fourth spelling from the producer is a silent fallback arm — and the
    arm it would fall into here is the reassuring one.  ``PHASES`` has the
    same guard on the hero, for the same reason."""
    text = await _rendered(CuratorWalletStanding, you_linked_state="linkedish",
                           **_standing_full())
    assert "unknown" in text
    assert "not linked" not in text
    assert "linkedish" not in text


async def test_a_hostile_linkage_reason_cannot_reach_markup():
    """Reasons are producer strings and the producer folds attacker-chosen
    data; Textual defers ``Text.from_markup`` into the message pump, so a
    malformed one raises outside the screen's try/except and kills the app."""
    text = await _rendered(
        CuratorWalletStanding, you_linked_state="linked",
        you_linked_group_size=12,
        you_linked_reasons=["[/x][bold red]owned[/]"],
        size=(200, 24), **_standing_full())
    assert "[/x]" in text or "owned" in text
    assert text.strip(), "a markup-hostile reason blanked the panel"


async def test_a_nonsense_reasons_payload_costs_the_reasons_and_not_the_panel():
    """``None``/a dict/a bare string where ``list[str]`` was promised: the
    line degrades to what it can still say, the panel keeps rendering."""
    for reasons in (None, {"a": 1}, 7, ["", "   ", None]):
        text = await _rendered(
            CuratorWalletStanding, you_linked_state="linked",
            you_linked_group_size=1995, you_linked_reasons=reasons,
            **_standing_full())
        assert "1,995" in text, reasons
        assert "412" in text, reasons          # the rest of the panel survived


# ===========================================================================
# WP5.2 — CuratorWalletStanding: the clean-rank line
#
# PRD §6: "you're #412 raw, #47 with clear farms removed."  Beside the raw
# rank, never instead of it -- the whole value of the number is the gap.
# ===========================================================================


def _facts_line(text: str, label: str) -> str:
    """The one composited line of a facts panel that starts with ``label``.

    The linkage lines are asserted against **their own line**, not against
    the whole panel: "unknown" appears somewhere on this panel in three
    different states, and a substring test over the panel would pass while
    the wrong line carried it.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(label):
            return stripped
    raise AssertionError(f"no {label!r} line rendered in:\n{text}")


async def test_the_clean_rank_renders_beside_the_raw_rank():
    from maxpane_dashboard.widgets.curator.wallet import CLEAN_RANK_SUFFIX

    text = await _rendered(CuratorWalletStanding, you_clean_rank=47,
                           you_linked_state="clean", you_linked_reasons=[],
                           **_standing_full())
    assert "412 of 10,643" in text                 # the raw rank survives
    assert f"#47 {CLEAN_RANK_SUFFIX}" in text


async def test_the_clean_rank_is_unknown_before_the_analysis_runs():
    """``None`` with a raw rank in hand is "the sweep has not run", and the
    one thing it must never do is echo the raw rank: two identical numbers
    read as "the farms cost you nothing", which is a finding."""
    from maxpane_dashboard.widgets.curator.wallet import CLEAN_RANK_SUFFIX

    text = await _rendered(CuratorWalletStanding, you_clean_rank=None,
                           you_linked_state=None, **_standing_full())
    assert "412 of 10,643" in text
    assert "unknown" in _facts_line(text, "clean")
    assert f"#412 {CLEAN_RANK_SUFFIX}" not in text


async def test_a_linked_reader_is_removed_rather_than_unknown():
    """Both are ``you_clean_rank is None`` and they are different facts:
    WP3's contract makes the removed wallets ``None``-for-removed, so the
    widget tells the two apart by ``you_linked_state`` or not at all."""
    from maxpane_dashboard.widgets.curator.wallet import (
        CLEAN_RANK_REMOVED,
        UNKNOWN_VALUE,
    )

    removed = _facts_line(
        await _rendered(
            CuratorWalletStanding, you_clean_rank=None,
            you_linked_state="linked", you_linked_group_size=1995,
            you_linked_reasons=["same funder"], **_standing_full()),
        "clean",
    )
    unknown = _facts_line(
        await _rendered(
            CuratorWalletStanding, you_clean_rank=None,
            you_linked_state=None, **_standing_full()),
        "clean",
    )
    cleared = _facts_line(
        await _rendered(
            CuratorWalletStanding, you_clean_rank=None,
            you_linked_state="clean", you_linked_reasons=[],
            **_standing_full()),
        "clean",
    )

    assert CLEAN_RANK_REMOVED in removed
    assert "unknown" not in removed
    assert UNKNOWN_VALUE in unknown
    # Analyzed and clear, but no rank came back: still unknown, never
    # "removed" -- this reader was not removed from anything.
    assert UNKNOWN_VALUE in cleared
    assert CLEAN_RANK_REMOVED not in cleared


async def test_the_clean_rank_line_says_what_the_number_is_a_rank_in():
    """A bare ``#47`` under a ``rank 412`` line is two numbers and no
    relation.  The suffix is the only thing that makes the pair readable."""
    from maxpane_dashboard.widgets.curator.wallet import CLEAN_RANK_SUFFIX

    line = _facts_line(
        await _rendered(CuratorWalletStanding, you_clean_rank=47,
                        you_linked_state="clean", you_linked_reasons=[],
                        **_standing_full()),
        "clean",
    )
    assert CLEAN_RANK_SUFFIX in line
    for word in ("sybil", "cheat", "fraud", "attack", "abuse", "wash"):
        assert word not in line.lower(), word


# ===========================================================================
# WP5.3 — CuratorLeaderboard: the confidence-graded flag
#
# `link_conf` is additive: `flagged` stays, because the bool is filled by
# analytics/curator_signals.py and that module must stay byte-identical to
# what shipped.  So the cell grades off the new sub-key when it has one and
# off the shipped bool when it does not -- and the ruled semantics of the
# fallback are the R5 controller ruling, not the brief's first sketch: a
# Tier-A-flagged wallet must not LOSE its `⚑` the day the graded column
# arrives, because the `c` view's cluster table is still flagging it.
# ===========================================================================


def _plain(markup: str) -> str:
    """``[yellow]⚑[/]`` -> ``⚑`` — what a reader in greyscale is left with."""
    import re

    return re.sub(r"\[[^\]]*\]", "", markup)


def test_the_flag_has_four_distinct_glyphs():
    """Colour is never the sole carrier; a reader in greyscale must tell the
    four apart (the CuratorSignals precedent).

    The four are asserted over what ``_link_glyph`` can actually *emit*,
    including through the Tier-A fallback, rather than over a table of
    constants that nothing has to use.
    """
    from maxpane_dashboard.widgets.curator import leaderboard as lb

    assert len({lb.LINK_HIGH, lb.LINK_LOW, lb.LINK_CLEAN, lb.LINK_UNKNOWN}) == 4

    reachable = {
        _plain(lb._link_glyph(conf, flagged))
        for conf in ("high", "low", "clean", None, "nonsense")
        for flagged in (True, False, None)
    }
    assert reachable == {lb.LINK_HIGH, lb.LINK_LOW, lb.LINK_CLEAN,
                         lb.LINK_UNKNOWN}, sorted(reachable)


def test_the_graded_cell_falls_back_to_the_shipped_tier_a_cell(): 
    """R5, as a truth table.  ``link_conf`` wins where it has an opinion; a
    grade this widget cannot read hands the cell back to the bool, which is
    the answer a *different* fold really did produce."""
    from maxpane_dashboard.widgets.curator import leaderboard as lb

    table = {
        # (link_conf, flagged): the glyph a reader sees
        ("high", True): lb.LINK_HIGH,
        ("high", None): lb.LINK_HIGH,
        ("low", True): lb.LINK_LOW,          # the grade outranks the bool
        ("low", None): lb.LINK_LOW,
        ("clean", False): lb.LINK_CLEAN,
        ("clean", True): lb.LINK_CLEAN,
        (None, True): lb.LINK_HIGH,          # the shipped flag never blanks
        (None, False): lb.LINK_CLEAN,
        (None, None): lb.LINK_UNKNOWN,       # fold-not-run, not clean
        ("nonsense", None): lb.LINK_UNKNOWN,
    }
    for (conf, flagged), expected in table.items():
        assert _plain(lb._link_glyph(conf, flagged)) == expected, (conf, flagged)


async def test_link_conf_grades_the_flag():
    row = _lb_rows(1)[0]
    rows = [
        {**row, "rank": 1, "link_conf": "high", "flagged": True},
        {**row, "rank": 2, "link_conf": "low", "flagged": True},
        {**row, "rank": 3, "link_conf": "clean", "flagged": False},
        {**row, "rank": 4, "link_conf": None, "flagged": None},
    ]
    text = await _rendered(CuratorLeaderboard, leaderboard_rows=rows, size=(143, 30))
    # header + the one high row: the `low` row's Tier-A `True` did NOT put a
    # second flag on the board.
    assert text.count("⚑") == 2, text
    assert "◌" in text
    assert "?" in text


async def test_a_tier_a_flag_survives_the_day_the_graded_column_arrives():
    """R5.  Before the sweep has ever run every ``link_conf`` is ``None``,
    and the Tier-A bool is still the only linkage answer on the dashboard --
    the `c` view's cluster table is drawn from it.  A graded cell that
    rendered `?` there would contradict the panel next to it and take a
    shipped flag off the board."""
    flagged = await _rendered(
        CuratorLeaderboard,
        leaderboard_rows=[{**_lb_rows(1)[0], "flagged": True, "link_conf": None}],
    )
    assert flagged.count("⚑") == 2          # header + the row
    assert "?" not in flagged

    # ...and `?` is what a row NEITHER fold could judge reads.
    unknown = await _rendered(
        CuratorLeaderboard,
        leaderboard_rows=[{**_lb_rows(1)[0], "flagged": None, "link_conf": None}],
    )
    assert "?" in unknown and unknown.count("⚑") == 1


async def test_an_unreadable_grade_is_never_rendered_as_clean():
    """A fifth spelling from the producer must not land in the empty cell,
    which is the *clean* rendering -- the same rule the signal rail keeps for
    a state word it does not know."""
    text = await _rendered(
        CuratorLeaderboard,
        leaderboard_rows=[{**_lb_rows(1)[0], "link_conf": "medium",
                           "flagged": None}],
    )
    assert "?" in text


async def test_a_hostile_link_conf_cannot_reach_markup():
    """The grade is a payload string like any other, and it is never
    rendered -- only mapped.  Pinned so a later "show the confidence word"
    edit cannot quietly hand `Text.from_markup` a stranger's string."""
    text = await _rendered(
        CuratorLeaderboard,
        leaderboard_rows=[{**_lb_rows(1)[0], "link_conf": "[/x][bold]owned[/]",
                           "flagged": None}],
    )
    assert "owned" not in text and "[/x]" not in text
    assert "?" in text
    assert "0x381f" in text          # the row itself still rendered


def test_the_flag_column_is_in_every_width_tier():
    """PRD §6: the flag column never sheds.  It is the one column a reader
    cannot reconstruct from anything else on the screen -- TX and CREDIT are
    both derivable from the rows around them, and a linkage grade is not."""
    from maxpane_dashboard.widgets.curator import leaderboard as lb

    for name, _cost, columns, _hint in lb._TIERS:
        assert "flag" in {key for key, _header, _width in columns}, name


@pytest.mark.parametrize("width", (143, 60, 46, 36))
async def test_the_graded_flag_reaches_the_screen_at_every_declared_tier(width):
    """Structural presence in the tier is not the same as a glyph on a
    pixel: the narrowest tier is 33 columns and the marker has to survive
    the compositor there too."""
    widget = CuratorLeaderboard()
    app = _Harness(widget)
    async with app.run_test(size=(width, 20)) as pilot:
        widget.update_data(
            leaderboard_rows=[{**_lb_rows(1)[0], "link_conf": "high",
                               "flagged": True}]
        )
        await pilot.pause()
        text = _screen_text(app)
    assert text.count("⚑") == 2, (width, text)


# ===========================================================================
# WP5.4 — the two widget-level widths, re-measured and published
#
# WP4's screen sweep imports these rather than re-typing a number.  Both are
# derived from the builders that render (`_standing_lines`) or from the tier
# the widget actually picks (`_TIERS[0]`), so neither can drift into being a
# remembered adjective -- the failure mode CLAUDE.md records for `dev`/`ops`
# and this package records for SIGNALS_FULL_WIDTH's first two values.
# ===========================================================================


def _worst_case_reasons() -> list[list[str]]:
    """Every ``reasons`` list in the committed analysis slice, widest first."""
    from tests.curator_sybil_fixtures import row_payloads

    lists = [
        list(row.get("reasons") or [])
        for _label, row in row_payloads("operator_row_worst.json")
    ]
    return sorted((r for r in lists if r), key=lambda r: -len(" · ".join(r)))


def test_the_standing_probe_carries_the_widest_linkage_strings_the_slices_hold():
    """A widget may not open a fixture, so the probe restates the measured
    worst case and this is the agreement test.

    Both maxima are pinned, and they are **independent**: the widest reason
    (53 columns) and the most reasons on one row (4) do not come from the
    same row, so the probe takes each at its own worst.  A later slice with a
    wider phrase reddens here rather than silently making the published width
    a description of the old data.
    """
    from maxpane_dashboard.widgets.curator import wallet as wallet_mod

    lists = _worst_case_reasons()
    widest_reason = max(len(r) for group in lists for r in group)
    most_reasons = max(len(group) for group in lists)
    assert (widest_reason, most_reasons) == (53, 4), (widest_reason, most_reasons)

    probe = wallet_mod.STANDING_WIDTH_PROBE["you_linked_reasons"]
    assert max(len(r) for r in probe) >= widest_reason
    assert len(probe) >= most_reasons
    assert wallet_mod._WIDEST_REASON in {
        r for group in lists for r in group
    }, "the probe's reason is not one the slices actually hold"

    # ...and the group size the probe carries is past the widest real one.
    from tests.curator_sybil_fixtures import row_payloads

    sizes = [row.get("size") for _l, row in row_payloads("operator_row_worst.json")]
    assert wallet_mod.STANDING_WIDTH_PROBE["you_linked_group_size"] >= max(
        s for s in sizes if isinstance(s, int)
    )


def test_the_standing_probe_carries_every_kwarg_the_panel_reads():
    """A kwarg added to the panel cannot slip past the probe unmeasured —
    the guard ``CuratorSignals`` already keeps on ``WIDTH_PROBE``."""
    from maxpane_dashboard.widgets.curator import signals as sig_mod
    from maxpane_dashboard.widgets.curator import wallet as wallet_mod

    kwargs = set(_kwargs_of(CuratorWalletStanding))
    assert set(wallet_mod.STANDING_WIDTH_PROBE) == kwargs, sorted(
        kwargs ^ set(wallet_mod.STANDING_WIDTH_PROBE)
    )
    # The score ceiling is imported from the rail, never re-typed: the suite
    # asserts *that* constant against the analytics curve.
    assert wallet_mod.STANDING_WIDTH_PROBE["you_points"] == sig_mod.MAX_CURVE_POINTS


async def test_the_standing_panel_needs_the_width_it_publishes():
    """Composited, both sides of the pin: at the published width the worst
    case reaches the screen whole, and one column under it the panel *says*
    it could not.  A test comparing the constant to its own formula could
    not catch a forgotten ``padding: 0 1``."""
    from maxpane_dashboard.widgets.curator import wallet as wallet_mod

    probe = wallet_mod.STANDING_WIDTH_PROBE
    fits = await _rendered(
        CuratorWalletStanding,
        size=(wallet_mod.STANDING_FULL_WIDTH, 24), **probe,
    )
    assert "widen" not in fits
    assert fits.count(wallet_mod._WIDEST_REASON) == 4      # every reason whole

    cut = await _rendered(
        CuratorWalletStanding,
        size=(wallet_mod.STANDING_FULL_WIDTH - 1, 24), **probe,
    )
    assert "widen" in cut
    assert cut.count(wallet_mod._WIDEST_REASON) < 4


def test_the_published_standing_width_is_the_panels_worst_case_not_a_payloads():
    """The ordering that makes the constant a property of the *panel*.

    A reader carrying the widest real evidence in the slices (the 1,995-wallet
    operator's size against the widest reason list) needs 191 columns; a
    reader with no linkage at all needs 40, and that number is **unchanged by
    this work package** — both new lines are shorter than the `joined` line
    that already set it.  The published constant clears all of them.
    """
    from maxpane_dashboard.widgets.curator import wallet as wallet_mod

    base = dict(
        you_rank=412, you_points=1234, you_credit_eth=3.6, you_weight_eth=7.03,
        you_tx_count=4, you_weight_share_pct=0.42, you_first_hour=0,
        you_joined_utc="2026-08-16 19:58 UTC", contributors_total=10_643,
    )
    widest_real = _worst_case_reasons()[0]

    unlinked = wallet_mod.measure_standing_width(base)
    cleared = wallet_mod.measure_standing_width(
        {**base, "you_linked_state": "clean", "you_linked_reasons": [],
         "you_clean_rank": 47}
    )
    linked = wallet_mod.measure_standing_width(
        {**base, "you_linked_state": "linked", "you_linked_group_size": 1995,
         "you_linked_reasons": widest_real}
    )

    assert unlinked == cleared == 40
    assert linked == 191
    assert wallet_mod.STANDING_FULL_WIDTH > linked > unlinked
    assert wallet_mod.STANDING_FULL_WIDTH == wallet_mod.measure_standing_width(
        wallet_mod.STANDING_WIDTH_PROBE
    )


async def test_the_standing_panel_sheds_value_tails_and_never_its_labels():
    """The facts-panel contract, on the two new lines: at the rail's own
    share of a full-layout terminal a linked reader keeps every label and the
    group size, and loses the evidence from the end behind the marker."""
    from maxpane_dashboard.widgets.curator import wallet as wallet_mod

    text = await _rendered(
        CuratorWalletStanding, size=(51, 24),
        you_linked_state="linked", you_linked_group_size=1995,
        you_linked_reasons=_worst_case_reasons()[0],
        you_clean_rank=None, **_standing_full(),
    )
    for label in ("rank", "clean", "score", "banked", "share", "joined",
                  "linked"):
        assert _facts_line(text, label), label
    assert "1,995-wallet group" in text          # the part a reader acts on
    assert wallet_mod._WIDEST_REASON not in text  # the tail went
    assert "widen" in text                        # ...and said so


def test_the_leaderboard_publishes_the_tier_it_actually_picks():
    """Both ends of the range, and neither is re-typed: a constant that
    disagreed with ``_TIERS`` would send a screen a width the widget then
    refuses to use."""
    from maxpane_dashboard.widgets.curator import leaderboard as lb
    from maxpane_dashboard.widgets.curator._table import pick_tier, tier_cost

    assert lb.LEADERBOARD_FULL_WIDTH == tier_cost(lb._TIERS[0][2]) == 49
    assert lb.LEADERBOARD_MIN_WIDTH == tier_cost(lb._TIERS[-1][2]) == 33

    name, _columns, hint = pick_tier(lb._TIERS, lb.LEADERBOARD_FULL_WIDTH)
    assert (name, hint) == ("full", "")
    name, _columns, hint = pick_tier(lb._TIERS, lb.LEADERBOARD_FULL_WIDTH - 1)
    assert name == "compact" and hint


def test_the_graded_flag_did_not_widen_the_board():
    """``◌`` is East-Asian-ambiguous; a two-column rendering of it would have
    pushed every tier out by one and moved a published width for a glyph."""
    from rich.cells import cell_len

    from maxpane_dashboard.widgets.curator import leaderboard as lb

    for glyph in (lb.LINK_HIGH, lb.LINK_LOW, lb.LINK_UNKNOWN):
        assert cell_len(glyph) == 1, glyph
    assert cell_len(lb.LINK_CLEAN) == 0
    assert lb._FLAG_COLS >= max(
        cell_len(g) for g in (lb.LINK_HIGH, lb.LINK_LOW, lb.LINK_UNKNOWN)
    )


@pytest.mark.parametrize("width,hint", [(49, ""), (48, "‹ widen: TX")])
async def test_the_board_renders_its_published_full_tier_and_says_so_below_it(
    width, hint
):
    widget = CuratorLeaderboard()
    app = _Harness(widget)
    async with app.run_test(size=(width, 20)) as pilot:
        widget.update_data(leaderboard_rows=_lb_rows(3))
        await pilot.pause()
        text = _screen_text(app)
    assert ("widen" in text) is bool(hint), (width, text)
    assert "⚑" in text                    # the flag column is in both tiers


def test_the_standing_panel_is_the_same_height_in_every_linkage_state():
    """The rail stacks four panels in a fixed column and the last one —
    ``WHERE IT GETS YOU`` — falls off the bottom first (CLAUDE.md's FWA
    coverage-badge hazard, and `you` is last in the signal rail for the same
    reason).  A panel whose height depended on its data would move the panels
    under it on every refresh, so the line count is pinned here rather than
    left to whichever branch a payload happens to take.

    Seven lines, always.  **Two more than the five that shipped**, which is a
    measured cost and not a free one: the `y` view's last panel first fits
    at a 36-row terminal where it used to fit at 34 (swept against the real
    screen at the pinned full-layout width, with and without these lines).
    """
    from maxpane_dashboard.widgets.curator import wallet as wallet_mod

    states = (
        {},
        {"you_linked_state": None},
        {"you_linked_state": "clean", "you_linked_reasons": [],
         "you_clean_rank": 47},
        {"you_linked_state": "linked", "you_linked_group_size": 1995,
         "you_linked_reasons": _worst_case_reasons()[0]},
        {"you_linked_state": "nonsense"},
        wallet_mod.STANDING_WIDTH_PROBE,
    )
    for extra in states:
        payload = {**_standing_full(), **extra}
        lines = wallet_mod._standing_lines(wallet_mod._standing_state(payload))
        assert len(lines) == 7, (extra, [line[0] for line in lines])
        assert [line[0] for line in lines] == [
            "rank", "clean", "score", "banked", "share", "joined", "linked"
        ]


# ===========================================================================
# WP5.5 — THE WP4 WIRING HAND-OFF
#
# Everything WP4 needs from this work package, in the file the agreement
# tests live in.  `rg "WP4 WIRING HAND-OFF"` is the whole index.
#
# 1. `CuratorWalletStanding.update_data` — the EXACT kwarg tuple, in order,
#    to paste into `WIDGET_SIGNATURES` in screens/curator.py:
#
#        "CuratorWalletStanding": (
#            "you_rank", "you_points", "you_credit_eth", "you_weight_eth",
#            "you_tx_count", "you_weight_share_pct", "you_first_hour",
#            "you_joined_utc", "contributors_total",
#            "you_linked_state", "you_linked_reasons",
#            "you_linked_group_size", "you_clean_rank",
#        ),
#
#    The first nine are unchanged; the last four are new and are exactly the
#    four `ANALYSIS_KEY_ROUTING` routes to this widget.  Until that map grows,
#    `tests/screens/test_curator_screen.py::test_the_dispatch_map_matches_the
#    _widgets_own_signatures` is RED, and that red is this hand-off's receipt
#    -- it is the agreement test doing its job across a wave boundary, and it
#    is WP4's to close.  `test_every_widget_kwarg_is_a_curator_key` already
#    passes, so all four are real contract keys.
#
# 2. `CuratorLeaderboard.update_data` is **UNCHANGED**: `(leaderboard_rows,
#    you_address)`.  `link_conf` is a row sub-key of a payload it already
#    receives, so WP4 changes nothing for it and `ANALYSIS_KEY_ROUTING`
#    rightly has no entry for it.  What WP3 must do instead is seed
#    `row["link_conf"] = None` on every row -- `build_signals` emits no
#    placeholder for it -- and the widget then falls back to the Tier-A bool
#    (R5), so nothing on the board changes until the sweep really runs.
#
# 3. Widths, published for import rather than re-typing:
#
#      leaderboard.LEADERBOARD_FULL_WIDTH = 49   (full tier: # WALLET POINTS
#                                                 CREDIT TX ⚑)
#      leaderboard.LEADERBOARD_MIN_WIDTH  = 33   (minimal tier, flag included)
#      wallet.STANDING_FULL_WIDTH         = 254  (worst case; NOT a budget)
#      wallet.measure_standing_width(payload)    (the number a screen wants)
#
#    Neither widget moved the app-wide picture: the leaderboard's tiers are
#    unchanged (all four glyphs are one cell wide), and the standing panel
#    needs **40 columns with no linkage and 40 with a clean verdict**, the
#    same as before this work package -- the `joined` line still sets it.  The
#    screen gives that panel 54 columns at the pinned 138, measured, so
#    `CURATOR_FULL_LAYOUT_COLUMNS` does not move.  A **linked** reader is the
#    exception and it is by design: the widest evidence in the committed
#    slices needs 191 columns, so the line sheds its reasons from the end
#    behind `‹ widen` and keeps the group size.  If WP4's phase fixtures give
#    the reader a linked verdict, the `y` view will light the marker at 138 --
#    that is the surf announce-feed precedent (a layout clears; a string need
#    not), and it must not be "fixed" by raising the constant.
#
#    Height is the one thing that did move: the panel is 9 rows where it was
#    7, so the `y` view's last panel (`WHERE IT GETS YOU`) first fits at a
#    **36-row** terminal where it used to fit at 34.  Measured both ways
#    against the real screen at 138 columns, by sweeping the height.  Nothing
#    in the suite pins it and no test moved, but it is the FWA
#    coverage-badge hazard's shape -- the last panel in a fixed column goes
#    first, in silence -- so WP4 should know the number.  The rail's own
#    `margin: 0 0 2 0` between panels is where the rows can be bought back.
#
# 4. New unavailable / explicit-state strings WP4's phase tests can assert
#    against, all importable from `widgets.curator.wallet`:
#
#      UNKNOWN_VALUE      "-- unknown"                  (both new lines, and
#                                                        the ONLY rendering of
#                                                        a linkage `None`)
#      NOT_LINKED         "not linked to any group"     (an answer, not a
#                                                        default)
#      LINKED_UNSIZED     "in a group of unknown size"
#      CLEAN_RANK_SUFFIX  "with farms removed"          (renders `#47 with
#                                                        farms removed`)
#      CLEAN_RANK_REMOVED "removed as a linked wallet"
#
#    ...and from `widgets.curator.leaderboard`: LINK_HIGH `⚑`, LINK_LOW `◌`,
#    LINK_CLEAN `` (empty), LINK_UNKNOWN `?`.
#
#    None of these is re-exported from `widgets/curator/__init__.py`: that
#    file is not WP5's to edit.  WP4 owns it (it exports the three new
#    panels) and should add them there if the screen wants the package root.
# ===========================================================================


# ===========================================================================
# WP4 (sybil expansion) — the three analysis panels
#
# OPERATORS / SEGMENTS / CLEANED LIST, the `f` view's body.  Sized against the
# committed worst-case slices, never toy rows, and read through the envelope
# accessors: two of the widest payloads (`worst`, `degraded_row`) live outside
# `rows` and a sweep driven by `worst_case_rows` alone never sees them.
#
# Imports are function-local in this section on purpose: the tests were
# written before the modules existed (TDD), and a module-level import would
# have taken the whole file's collection down with it rather than failing
# exactly the tests that describe the missing widget.
# ===========================================================================


def _operator_envelope() -> dict:
    from tests.curator_sybil_fixtures import worst_case_envelope

    return worst_case_envelope("operator_row_worst.json")


def _segment_envelope() -> dict:
    from tests.curator_sybil_fixtures import worst_case_envelope

    return worst_case_envelope("segment_rows_worst.json")


def _clean_envelope() -> dict:
    from tests.curator_sybil_fixtures import worst_case_envelope

    return worst_case_envelope("clean_list_rows_worst.json")


def _operator_row(**over) -> dict:
    """One well-formed operator row, small on purpose — the worst-case tests
    read the envelope; this is for the branch tests that need a knob."""
    row = {
        "size": 10,
        "reasons": ["identical 6Ξ send ×10"],
        "points": 31_622,
        "points_share_pct": 1.2,
        "sqrt_subsidy_x": 3.2,
        "conf": "low",
    }
    row.update(over)
    return row


# -- WP4.1: CuratorOperators ------------------------------------------------


async def test_the_worst_case_operator_renders_its_size_share_and_subsidy():
    """The row the columns have to fit: 1,995 wallets, 6.81% of all points,
    44.6× sqrt subsidy, four reasons.  `worst` is its own entry in `rows`."""
    from maxpane_dashboard.widgets.curator.operators import CuratorOperators

    env = _operator_envelope()
    text = await _rendered(
        CuratorOperators,
        operator_rows=env["rows"][:6],
        operators_count=len(env["rows"]),
        flagged_points_share_pct=43.25,
        analysis_as_of_hhmm="22:41",
    )
    assert "1,995 linked" in text
    assert "6.8%" in text
    assert "44.6×" in text
    # The strongest reason renders whole, not clipped mid-word.
    assert "identical 0.45Ξ send ×1,995" in text
    # The one-line summary: the count and the share, both from the payload.
    assert "16 linked groups" in text
    assert "43.2% of all points" in text


async def test_conf_renders_as_a_glyph_never_a_word_or_a_number():
    """PRD §5.1: confidence is a filled/hollow marker consistent with the
    leaderboard's flag vocabulary.  A raw number reads as a verdict with a
    decimal point, and the grade word itself must never reach the screen."""
    from maxpane_dashboard.widgets.curator.leaderboard import (
        LINK_HIGH,
        LINK_LOW,
        LINK_UNKNOWN,
    )
    from maxpane_dashboard.widgets.curator.operators import CuratorOperators

    rows = [
        _operator_row(size=10, conf="high"),
        _operator_row(size=11, conf="low"),
        _operator_row(size=12, conf=None),
        _operator_row(size=13, conf=0.87),  # a raw score is not a grade
    ]
    text = await _rendered(
        CuratorOperators, operator_rows=rows, operators_count=4
    )
    assert LINK_HIGH in text and LINK_LOW in text and LINK_UNKNOWN in text
    assert "high" not in text and "low" not in text
    assert "0.87" not in text


async def test_operators_none_is_unavailable_and_zero_is_a_real_negative():
    """The FARM-row precedent, on the analysis panel it feeds: `None` is
    "could not analyze" and `0` is "analyzed, none linked".  Collapsing them
    renders confident and green through an outage."""
    from maxpane_dashboard.widgets.curator.operators import (
        OPERATORS_EMPTY,
        OPERATORS_UNAVAILABLE,
        CuratorOperators,
    )

    dead = await _rendered(
        CuratorOperators, operator_rows=None, operators_count=None
    )
    empty = await _rendered(
        CuratorOperators, operator_rows=[], operators_count=0
    )
    assert OPERATORS_UNAVAILABLE in dead and OPERATORS_EMPTY not in dead
    assert OPERATORS_EMPTY in empty and OPERATORS_UNAVAILABLE not in empty


async def test_the_operators_panel_shows_its_own_freshness_marker():
    """`analysis_as_of_hhmm` is the detached sweep's OWN marker, separate from
    the fast tier's `as of` — one marker for both tiers would present an
    hours-old analysis as live."""
    from maxpane_dashboard.widgets.curator.operators import CuratorOperators

    env = _operator_envelope()
    text = await _rendered(
        CuratorOperators,
        operator_rows=env["rows"][:3],
        operators_count=16,
        analysis_as_of_hhmm="22:41",
    )
    assert "as of 22:41" in text


async def test_the_operators_panel_uses_pattern_language_only():
    """The panel's own copy of the forbidden-word test (PRD §8), over the
    committed worst-case rows — the state the panel normally renders."""
    from maxpane_dashboard.widgets.curator.operators import CuratorOperators

    env = _operator_envelope()
    text = await _rendered(
        CuratorOperators,
        operator_rows=env["rows"][:6],
        operators_count=len(env["rows"]),
        flagged_points_share_pct=43.25,
        analysis_as_of_hhmm="22:41",
    )
    assert "linked" in text.lower()
    for word in ("sybil", "cheat", "fraud", "attack", "abuse", "wash"):
        assert word not in text.lower(), word


async def test_a_hostile_operator_reason_renders_literally():
    """`reasons` strings are producer copy today and third-party-shaped
    forever; `[/x]` must render as text, never raise a deferred MarkupError."""
    from maxpane_dashboard.widgets.curator.operators import CuratorOperators

    text = await _rendered(
        CuratorOperators,
        operator_rows=[_operator_row(reasons=["[/x]"])],
        operators_count=1,
    )
    assert "[/x]" in text


@pytest.mark.parametrize(
    "width,tier",
    [(138, "full"), (130, "no-sqrt"), (120, "no-points"), (100, "brief")],
)
async def test_a_narrow_operators_table_sheds_the_subsidy_column_first(
    width, tier
):
    """The derived columns go first — the subsidy multiple, then the points —
    and every shed is announced; the size, the evidence and the share are the
    finding and never shed."""
    from maxpane_dashboard.widgets.curator.operators import CuratorOperators

    env = _operator_envelope()
    widget = CuratorOperators()
    app = _Harness(widget)
    async with app.run_test(size=(width, 20)) as pilot:
        widget.update_data(
            operator_rows=env["rows"][:4], operators_count=len(env["rows"])
        )
        await pilot.pause()
        text = _screen_text(app)
    assert "1,995 linked" in text          # the finding itself never sheds
    assert "17.9%" in text                 # nor the share
    if tier == "full":
        assert "widen" not in text and "44.6×" in text
    else:
        assert "widen" in text and "44.6×" not in text
    if tier in ("no-points", "brief"):
        # The hint *names* POINTS, so assert on the value: rows[0] holds
        # 4,755,046 points and that number must be gone with its column.
        assert "4,755,046" not in text
    else:
        assert "4,755,046" in text


async def test_reasons_wider_than_the_cell_shed_whole_phrases_visibly():
    """The widest joined evidence in the slices is 159 columns — wider than
    any cell this layout can afford — so phrases are dropped from the end
    behind a visible `…`, never cut mid-word by the table in silence."""
    from maxpane_dashboard.widgets.curator.operators import CuratorOperators

    env = _operator_envelope()
    widest = max(env["rows"], key=lambda r: len(" · ".join(r["reasons"])))
    text = await _rendered(
        CuratorOperators, operator_rows=[widest], operators_count=1
    )
    assert "…" in text
    assert widest["reasons"][0] in text    # the strongest phrase stays whole


# -- WP4.2: CuratorSegments -------------------------------------------------


async def test_the_segment_bands_render_with_their_pattern_language_labels():
    """PRD §5.2: "largest operators", "early cohort" — never "whale sybil".
    The index-1000 cohort's 7.6% is the number Adam asked for by name."""
    from maxpane_dashboard.widgets.curator.segments import CuratorSegments

    env = _segment_envelope()
    text = await _rendered(
        CuratorSegments, segment_rows=env["rows"], analysis_as_of_hhmm="22:41"
    )
    assert "largest operators" in text
    assert "early cohort" in text
    assert "7.6%" in text
    assert "as of 22:41" in text


async def test_segments_none_is_unavailable_and_empty_is_a_real_negative():
    from maxpane_dashboard.widgets.curator.segments import (
        SEGMENTS_EMPTY,
        SEGMENTS_UNAVAILABLE,
        CuratorSegments,
    )

    dead = await _rendered(CuratorSegments, segment_rows=None)
    empty = await _rendered(CuratorSegments, segment_rows=[])
    assert SEGMENTS_UNAVAILABLE in dead and SEGMENTS_EMPTY not in dead
    assert SEGMENTS_EMPTY in empty and SEGMENTS_UNAVAILABLE not in empty


async def test_a_band_with_no_share_renders_a_dash_not_a_zero():
    """`degraded_row` is the committed example: a per-hour band whose share
    could not be attributed.  `0.0%` there would read "this hour scored
    nothing", a measurement nobody made — and its 56-column detail is the
    widest string in the whole fixture set, so it must render whole."""
    from maxpane_dashboard.widgets.curator.segments import CuratorSegments

    env = _segment_envelope()
    text = await _rendered(
        CuratorSegments, segment_rows=[env["degraded_row"]]
    )
    assert "0.0%" not in text
    assert DASH in text
    assert env["degraded_row"]["detail"] in text


async def test_the_segments_panel_uses_pattern_language_only():
    """The panel's own copy of the forbidden-word test (PRD §8), over every
    band in the committed slice plus the degraded row."""
    from maxpane_dashboard.widgets.curator.segments import CuratorSegments

    env = _segment_envelope()
    rows = list(env["rows"]) + [env["degraded_row"]]
    text = await _rendered(
        CuratorSegments, segment_rows=rows, analysis_as_of_hhmm="22:41"
    )
    for word in ("sybil", "cheat", "fraud", "attack", "abuse", "wash"):
        assert word not in text.lower(), word


async def test_a_hostile_segment_label_renders_literally():
    from maxpane_dashboard.widgets.curator.segments import CuratorSegments

    row = {
        "label": "[/x]",
        "contributors": 3,
        "points_share_pct": 1.0,
        "detail": "[red]3Ξ[/red]",
    }
    text = await _rendered(CuratorSegments, segment_rows=[row])
    assert "[/x]" in text
    assert "[red]" in text                  # markup rendered as text, not style


async def test_a_narrow_segments_table_sheds_the_detail_first():
    """The label is the band's identity and the share is the finding; the
    free-text detail is the first thing a narrow slot gives up, announced."""
    from maxpane_dashboard.widgets.curator.segments import CuratorSegments

    env = _segment_envelope()
    widget = CuratorSegments()
    app = _Harness(widget)
    async with app.run_test(size=(60, 20)) as pilot:
        widget.update_data(segment_rows=env["rows"])
        await pilot.pause()
        text = _screen_text(app)
    assert "widen" in text
    assert "largest operators" in text
    assert "43.2%" in text
    assert "send shapes" not in text        # the detail column is gone
