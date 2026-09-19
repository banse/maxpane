"""``widgets/fmt.py`` -- the shared pure formatters (Branch 3 WP-B).

Every exported name is exercised here; the goldens that pin each dashboard's
former private copy live beside that dashboard's own tests.  The purity test
mirrors ``test_surf_rowfit.test_rowfit_is_pure_enough_for_a_widget_to_import``
with one difference: ``time`` is *allowed*, because ``hhmm`` / ``mmdd`` render
a caller-supplied timestamp in local time -- and the clock test below proves
that is the only use it gets.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from maxpane_dashboard.widgets import fmt
from maxpane_dashboard.widgets.fmt import (
    DASH,
    EMDASH,
    as_float,
    fmt_age,
    fmt_countdown,
    fmt_eth,
    fmt_pct,
    fmt_points,
    hhmm,
    mmdd,
)

_HOSTILE = (None, True, False, "x", "", [], {}, object(), b"\x00",
            float("nan"), float("inf"), float("-inf"))


def test_the_export_list_is_exactly_the_public_surface():
    assert set(fmt.__all__) == {
        "DASH", "EMDASH", "as_float", "fmt_age", "fmt_countdown", "fmt_eth",
        "fmt_pct", "fmt_points", "hhmm", "mmdd",
    }
    for name in fmt.__all__:
        assert hasattr(fmt, name), name


def test_the_two_markers_are_distinct_and_two_and_one_cells():
    assert DASH == "--" and EMDASH == "—" and DASH != EMDASH


def test_as_float_refuses_bools_nan_inf_and_nonsense_without_raising():
    for value in _HOSTILE:
        assert as_float(value) is None, value
    assert as_float("3.5") == 3.5
    assert as_float(0) == 0.0
    assert as_float(-2) == -2.0
    assert as_float(10**18) == 1e18


def test_fmt_eth_default_is_two_grouped_places_and_a_real_zero_renders():
    assert fmt_eth(0) == "0.00"
    assert fmt_eth(0.0) == "0.00"
    assert fmt_eth(1.5) == "1.50"
    assert fmt_eth(8401) == "8,401.00"
    assert fmt_eth(1234.5678) == "1,234.57"
    assert fmt_eth(-2) == "-2.00"


def test_fmt_eth_places_parameter():
    assert fmt_eth(0, places=4) == "0.0000"
    assert fmt_eth(0.123456789, 4) == "0.1235"
    assert fmt_eth(1234.5678, places=3) == "1,234.568"
    assert fmt_eth(0.0057, places=6) == "0.005700"


def test_fmt_eth_unit_is_appended_after_one_space_and_never_on_the_marker():
    assert fmt_eth(1.5, unit="ETH") == "1.50 ETH"
    assert fmt_eth(1.5, 4, "Ξ") == "1.5000 Ξ"
    assert fmt_eth(0, unit="ETH") == "0.00 ETH"
    assert fmt_eth(None, unit="ETH") == DASH
    assert fmt_eth("abc", unit="ETH") == DASH
    assert fmt_eth(1.5, unit="") == "1.50"


def test_fmt_eth_renders_the_dash_for_none_bool_and_non_numeric():
    for value in (None, True, False, "abc", "", float("nan"), float("inf"), [], {}):
        assert fmt_eth(value) == DASH, value


def test_fmt_age_buckets_and_rejects_negative_and_unknown():
    assert fmt_age(None) == DASH
    assert fmt_age(-1) == DASH           # an event from the future is corrupt input
    assert fmt_age(0) == "0s"
    assert fmt_age(45) == "45s"
    assert fmt_age(89) == "89s"
    assert fmt_age(90) == "2m"
    assert fmt_age(12 * 60) == "12m"
    assert fmt_age(90 * 60) == "2h"
    assert fmt_age(2 * 3600) == "2h"
    assert fmt_age(36 * 3600) == "2d"
    assert fmt_age(3 * 86400) == "3d"
    assert fmt_age("abc") == DASH
    assert fmt_age(True) == DASH


def test_fmt_countdown_hour_boundary_and_zero_are_real_states():
    assert fmt_countdown(3600) == "1:00:00"   # timeLeftInHour() at the boundary
    assert fmt_countdown(0) == "00:00"         # grace clamped at 0
    assert fmt_countdown(59) == "00:59"
    assert fmt_countdown(11565) == "3:12:45"
    assert fmt_countdown(3599.9) == "59:59"
    assert fmt_countdown(None) == DASH
    for value in (-1, -5, -86400):
        assert fmt_countdown(value) == DASH
        assert ":" not in fmt_countdown(value)


def test_fmt_points_zero_is_a_real_score_and_none_is_not():
    assert fmt_points(0) == "0"
    assert fmt_points(31622) == "31,622"
    assert fmt_points(31622.9) == "31,622"
    assert fmt_points(None) == DASH
    assert fmt_points("abc") == DASH


def test_fmt_pct_distinguishes_an_unknown_share_from_a_zero_one():
    assert fmt_pct(None) == DASH
    assert fmt_pct(0) == "0.0%"
    assert fmt_pct(12.44) == "12.4%"
    assert fmt_pct(100) == "100.0%"


def test_hhmm_default_unknown_marker_and_override():
    for value in (None, 0, 0.0, -1, "", "abc", [], False):
        assert hhmm(value) == "??:??", value
        assert hhmm(value, unknown="--:--") == "--:--", value
    stamp = 1786910327
    assert hhmm(stamp) != "??:??"
    assert hhmm(stamp) == hhmm(stamp, unknown="--:--")
    t = time.localtime(stamp)
    assert hhmm(stamp) == f"{t.tm_hour:02d}:{t.tm_min:02d}"


def test_hhmm_infinity_renders_the_marker_instead_of_raising():
    """``int(float("inf"))`` raises ``OverflowError``; the curator copy this
    replaced let that escape (2026-09-20).  Pinned on both defaults."""
    for value in (float("inf"), float("-inf")):
        assert hhmm(value) == "??:??"
        assert hhmm(value, unknown="--:--") == "--:--"
        assert mmdd(value) == "??-??"
        assert mmdd(value, unknown="xx-xx") == "xx-xx"


def test_hhmm_and_mmdd_out_of_range_stamps_render_the_marker():
    for value in (10**18, 2**70, 1e20):
        assert hhmm(value) == "??:??"
        assert mmdd(value) == "??-??"


def test_mmdd_default_unknown_marker_and_override():
    for value in (None, 0, -1, "", "abc"):
        assert mmdd(value) == "??-??", value
        assert mmdd(value, unknown="--") == "--", value
    stamp = 1786910327
    t = time.localtime(stamp)
    assert mmdd(stamp) == f"{t.tm_mon:02d}-{t.tm_mday:02d}"


@pytest.mark.parametrize("fn", [as_float, fmt_age, fmt_countdown, fmt_eth,
                                fmt_pct, fmt_points, hhmm, mmdd])
def test_no_formatter_raises_on_hostile_input(fn):
    """Widgets run inside Textual's message pump; a raise there kills the app."""
    for value in _HOSTILE + ("[/x]", [1, 2], {"a": 1}, 10**30):
        out = fn(value)
        if fn is not as_float:
            assert isinstance(out, str), (fn.__name__, value)


def test_fmt_is_pure_enough_for_a_widget_to_import():
    """It sits under ``widgets/``, so it may reach neither I/O nor ``data/``
    nor ``analytics/`` nor Textual.  ``time`` is the one allowed extra --
    ``hhmm`` / ``mmdd`` render a caller-supplied timestamp -- and the next
    test proves the clock itself is never read.
    """
    path = Path(fmt.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    allowed = {"__future__", "time", "maxpane_dashboard.widgets.sparkline_common"}
    assert imported <= allowed, f"`fmt` reaches {sorted(imported - allowed)}"


def test_fmt_never_reads_the_clock():
    """``time`` is imported for ``localtime`` only: no ``time.time()``,
    ``monotonic()``, ``perf_counter()`` or ``datetime.now()`` anywhere."""
    src = Path(fmt.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "time":
                calls.add(node.func.attr)
    assert calls == {"localtime"}, calls
