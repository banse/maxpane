"""Tests for ``maxpane_dashboard.analytics.fwa_signals``.

Zero network, zero clock dependence.

Every time-sensitive test pins its own frozen timestamp.  The emissions hard
stop (2026-08-04T19:01:23Z) lands *during* this build, so **no test may depend
on the wall-clock relationship between "now" and the stop** in either
direction: this suite must give identical results on 2026-08-03 and on
2026-08-05.  Nothing here calls ``time.time()`` or ``datetime.now()``, and
``test_emissions_suite_is_independent_of_the_wall_clock`` enforces that
mechanically for both this file and the module under test.

Both branches are covered.  The ended branch is written first because it is the
state the dashboard will spend virtually all of its life in; the live countdown
is covered just as thoroughly because it is what renders today.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import fwa_signals as sig
from maxpane_dashboard.data.fwa_models import FWASignal, PoolTemp

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fwa"
_MODULE_SOURCE = Path(sig.__file__).read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """Source with docstrings and comments stripped.

    The structural tests below assert on what the code *does*, not on what the
    prose *mentions* — a docstring is allowed to name the thing it forbids.
    """
    return re.sub(r"#[^\n]*", "", re.sub(r'"""(?:.|\n)*?"""', "", source))

# Onchain emission window (findings / PRD §8): 1784574083 + 15 days.
EMISSION_START = 1_784_574_083
EMISSION_DURATION = 15 * 24 * 3_600
EMISSION_STOP = 1_785_870_083  # 2026-08-04T19:01:23Z


@pytest.fixture(scope="module")
def config_events() -> list[dict]:
    """All 27 ``ConfigSet`` logs: 21 launch-write + 6 post-launch changes."""
    raw = json.loads((_FIXTURES / "logs_config_set.json").read_text(encoding="utf-8"))
    return raw["expected_decoded"]["all_events"]


@pytest.fixture(scope="module")
def launch_only(config_events: list[dict]) -> list[dict]:
    return [e for e in config_events if e["blockNumber"] == 25_546_793]


# ---------------------------------------------------------------------------
# 3. Emissions status
#
# The stop lands mid-build, so both branches are real code paths and both are
# tested.  ENDED comes first: it is the state the dashboard lives in from
# 2026-08-04 onward and it must be correct on the day it flips, unattended.
# Every clock below is injected, so the results do not move when the real date
# crosses the stop.
# ---------------------------------------------------------------------------


def test_emissions_elapsed_never_negative():
    """PRIMARY: a clock past the hard stop renders 'ended', never a negative."""
    row = sig.emissions_signal(
        now_ts=EMISSION_STOP + 21 * 86_400,
        emission_start=EMISSION_START,
        emission_duration=EMISSION_DURATION,
    )
    assert "emissions ended" in row.value_str
    assert "-" not in row.value_str
    assert "−" not in row.value_str
    assert "21d" in row.value_str
    assert row.color == sig.SIGNAL_MUTED


@pytest.mark.parametrize("offset", [0, 1, 60, 86_400, 400 * 86_400])
def test_emissions_ended_never_renders_a_negative_number(offset: int):
    """No clock at or past the stop may produce a minus sign anywhere."""
    row = sig.emissions_signal(
        now_ts=EMISSION_STOP + offset,
        emission_start=EMISSION_START,
        emission_duration=EMISSION_DURATION,
    )
    assert row.value_str.startswith("emissions ended")
    assert not re.search(r"[-−]\s*\d", row.value_str)


def test_emissions_stop_boundary_is_ended_not_a_zero_countdown():
    row = sig.emissions_signal(
        now_ts=EMISSION_STOP,
        emission_start=EMISSION_START,
        emission_duration=EMISSION_DURATION,
    )
    assert "ended" in row.value_str
    assert "left" not in row.value_str


def test_emissions_counting_down():
    """The live branch — what renders today, with a pinned clock either way."""
    row = sig.emissions_signal(
        now_ts=EMISSION_STOP - (8 * 86_400 + 4 * 3_600),
        emission_start=EMISSION_START,
        emission_duration=EMISSION_DURATION,
        current_epoch=7,
    )
    assert "emissions live" in row.value_str
    assert "8d 4h left" in row.value_str
    assert "epoch 7" in row.value_str
    assert row.color == sig.SIGNAL_WARN


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [
        (1, "1s"),
        (90, "1m"),
        (3 * 3_600 + 25 * 60, "3h 25m"),
        (8 * 86_400 + 4 * 3_600, "8d 4h"),
        (EMISSION_DURATION, "15d"),  # the instant emissions opened
    ],
)
def test_emissions_live_countdown_across_the_whole_window(remaining: int, expected: str):
    """Every point strictly before the stop counts down, and never says ended."""
    row = sig.emissions_signal(
        now_ts=EMISSION_STOP - remaining,
        emission_start=EMISSION_START,
        emission_duration=EMISSION_DURATION,
    )
    assert row.value_str == f"emissions live · {expected} left"
    assert row.color == sig.SIGNAL_WARN
    assert "ended" not in row.value_str
    assert not re.search(r"[-−]\s*\d", row.value_str)


def test_emissions_one_second_either_side_of_the_stop():
    """The branch flips exactly at the stop and nowhere else."""
    args = (EMISSION_START, EMISSION_DURATION)
    assert "left" in sig.emissions_signal(EMISSION_STOP - 1, *args).value_str
    assert "ended" in sig.emissions_signal(EMISSION_STOP, *args).value_str
    assert "ended" in sig.emissions_signal(EMISSION_STOP + 1, *args).value_str


def test_emissions_suite_is_independent_of_the_wall_clock():
    """A test that passes today and fails on 2026-08-05 is a defect.

    ``emissions_signal`` takes ``now_ts`` as an argument and has no wall-clock
    fallback, so neither branch can be reached by accident of the calendar.
    Asserted structurally rather than by trust: neither the module nor this
    suite may call ``time.time()`` / ``datetime.now()``.
    """
    assert sig.emissions_signal().value_str == "emissions status unavailable"

    # Needles are assembled at runtime so this assertion does not trip over its
    # own source text.
    forbidden = [
        f"{module}.{call}("
        for module, call in (
            ("time", "time"),
            ("datetime", "now"),
            ("datetime", "today"),
            ("date", "today"),
        )
    ]
    suite_source = Path(__file__).read_text(encoding="utf-8")
    for source in (_MODULE_SOURCE, suite_source):
        code = _code_only(source)
        for needle in forbidden:
            assert needle not in code

    # Same inputs, same row — the only clock that matters is the injected one.
    args = (EMISSION_STOP + 3_600, EMISSION_START, EMISSION_DURATION)
    assert sig.emissions_signal(*args) == sig.emissions_signal(*args)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"now_ts": EMISSION_STOP + 1},
        {"now_ts": EMISSION_STOP + 1, "emission_start": EMISSION_START},
        {"now_ts": EMISSION_STOP + 1, "emission_duration": EMISSION_DURATION},
        {"now_ts": EMISSION_STOP + 1, "emission_start": 0, "emission_duration": 0},
    ],
)
def test_emissions_unavailable_inputs_degrade_not_raise(kwargs: dict):
    row = sig.emissions_signal(**kwargs)
    assert row.value_str == "emissions status unavailable"
    assert row.color == sig.SIGNAL_MUTED


def test_emissions_never_falls_back_to_documented_constants():
    """A failed read degrades; it does not silently use the documented window."""
    row = sig.emissions_signal(now_ts=EMISSION_STOP + 1, emission_start=EMISSION_START)
    assert "unavailable" in row.value_str
    # The documented constants exist for tests/docs, and match the real window.
    assert sig.DOCUMENTED_EMISSION_STOP == EMISSION_STOP


# ---------------------------------------------------------------------------
# 1. Pool temperature
# ---------------------------------------------------------------------------


def test_pool_temp_hot():
    """<= 60 s since the last request: the whole surcharge goes to depositors."""
    row = sig.pool_temp_signal(
        seconds_since_last_request=12, token_share_bps=0, hot_gap=60, cold_gap=3_600
    )
    assert row.value_str == "HOT 12s · surcharge → depositors"
    assert row.color == sig.SIGNAL_MUTED


def test_pool_temp_cold():
    """>= 3600 s: the surcharge comes back to the purchaser as $FWA allowance."""
    row = sig.pool_temp_signal(
        seconds_since_last_request=4_000,
        token_share_bps=10_000,
        hot_gap=60,
        cold_gap=3_600,
    )
    assert row.value_str == "COLD 1h 6m · surcharge → YOU (100%)"
    assert row.color == sig.SIGNAL_GOOD


def test_pool_temp_midband():
    row = sig.pool_temp_signal(
        seconds_since_last_request=1_830,
        token_share_bps=5_000,
        hot_gap=60,
        cold_gap=3_600,
    )
    assert row.value_str == "WARM 30m · surcharge → YOU 50%"
    assert row.color == sig.SIGNAL_WARN
    assert "est" not in row.value_str


def test_pool_temp_live_share_wins_over_the_ramp():
    """A cold clock with a live 0 bps read reports the live truth, not the ramp."""
    temp = sig.resolve_pool_temp(
        4_000, token_share_bps=0, hot_gap=60, cold_gap=3_600
    )
    assert temp is not None
    assert temp.token_share_bps == 0
    assert temp.share_estimated is False
    row = sig.pool_temp_signal_for(temp)
    assert "COLD" in row.value_str
    assert "depositors" in row.value_str


def test_pool_temp_estimated_fallback():
    """No live read: the ramp is a label only, and the estimate is flagged."""
    temp = sig.resolve_pool_temp(
        1_830, token_share_bps=None, hot_gap=60, cold_gap=3_600
    )
    assert temp is not None
    assert temp.share_estimated is True
    assert temp.token_share_bps == 5_000
    row = sig.pool_temp_signal_for(temp)
    assert row.value_str == "WARM 30m · surcharge → YOU ~50% est"
    assert row.color == sig.SIGNAL_WARN


def test_pool_temp_estimated_endpoints_default_to_documented_ramp():
    """Unread endpoints fall back to the documented 60/3600 as a static label."""
    temp = sig.resolve_pool_temp(30, token_share_bps=None)
    assert temp is not None
    assert temp.share_estimated is True
    assert temp.token_share_bps == 0
    # The documented pair is never written back into the live fields.
    assert temp.hot_gap == 0
    assert temp.cold_gap == 0
    assert sig.pool_temp_signal_for(temp).value_str.startswith("HOT 30s")


def test_pool_temp_forced_override():
    row = sig.pool_temp_signal(
        seconds_since_last_request=720,
        token_share_bps=0,
        hot_gap=60,
        cold_gap=3_600,
        forced_bps=3_400,
    )
    assert row.value_str == "OVERRIDE 12m · surcharge → YOU 34% (dial pinned)"
    assert row.color == sig.SIGNAL_WARN


def test_pool_temp_dynamic_is_not_an_override():
    temp = sig.resolve_pool_temp(720, token_share_bps=2_000, forced_bps=-1)
    assert temp is not None
    assert temp.forced_share_bps == -1
    assert "dial pinned" not in sig.pool_temp_signal_for(temp).value_str


def test_pool_temp_unsigned_decode_bug_is_not_a_huge_share():
    """``2**256 - 1`` is a decode bug (trap 4), not a pinned dial."""
    temp = sig.resolve_pool_temp(720, token_share_bps=2_000, forced_bps=2**256 - 1)
    assert temp is not None
    assert temp.forced_share_bps == -1
    row = sig.pool_temp_signal_for(temp)
    assert "dial pinned" not in row.value_str
    assert "YOU 20%" in row.value_str


@pytest.mark.parametrize("temp", [None, PoolTemp(seconds_since_last_request=30)])
def test_pool_temp_unavailable(temp):
    """No clock read, or a PoolTemp whose share never resolved."""
    if temp is not None:
        temp = temp.model_copy(update={"token_share_bps": None})
    row = sig.pool_temp_signal_for(temp)
    assert row.value_str == "pool temp unavailable"
    assert row.color == sig.SIGNAL_MUTED


def test_pool_temp_signal_without_any_reads_is_unavailable():
    row = sig.pool_temp_signal()
    assert row.value_str == "pool temp unavailable"
    assert row.color == sig.SIGNAL_MUTED
    assert sig.resolve_pool_temp(None) is None


def test_pool_temp_negative_gap_is_clamped():
    temp = sig.resolve_pool_temp(-5, token_share_bps=0)
    assert temp is not None
    assert temp.seconds_since_last_request == 0
    assert "-" not in sig.pool_temp_signal_for(temp).value_str


# ---------------------------------------------------------------------------
# 2. Buy gate
# ---------------------------------------------------------------------------


def test_buy_gate_red_when_false():
    row = sig.buy_gate_signal(False)
    assert row.color == sig.SIGNAL_BAD
    assert "GATED" in row.value_str


def test_buy_gate_footnote_present():
    """The DexScreener contradiction is explained on the row itself."""
    row = sig.buy_gate_signal(False)
    assert sig.BUY_GATE_FOOTNOTE in row.value_str
    # The scare quotes are the load-bearing part: they say the "buys" are not
    # what they look like. The contract name was dropped when the row was
    # shortened to fit -- it named something the reader cannot act on.
    assert '"buys"' in row.value_str


def test_buy_gate_row_fits_the_signals_panel():
    """The footnote is only worth carrying if it survives the width.

    The long form ran 61 columns against a panel that gets about 55, so it
    clipped mid-word and left a permanent widen marker -- the explanation was
    costing more clarity than it bought.
    """
    row = sig.buy_gate_signal(False)

    assert len(row.value_str) + 2 <= 55, (
        f"gated row is {len(row.value_str) + 2} columns: {row.value_str!r}"
    )


def test_buy_gate_green_when_true():
    row = sig.buy_gate_signal(True)
    assert row.color == sig.SIGNAL_GOOD
    assert "OPEN" in row.value_str


def test_buy_gate_unavailable():
    row = sig.buy_gate_signal(None)
    assert row.value_str == "buy gate unavailable"
    assert row.color == sig.SIGNAL_MUTED


# ---------------------------------------------------------------------------
# 4. VRF queue
# ---------------------------------------------------------------------------


def test_vrf_queue_depth_arithmetic():
    row = sig.vrf_queue_signal(
        last_issued=1_042,
        next_to_process=1_027,
        pending=3,
        unsettled=18,
        unfulfilled_vrf=2,
        subscription_balance=31 * 10**18,
        minimum_buffer=35 * 10**16,
    )
    assert row.value_str == "depth 15 · 3 open · 18 unsettled · 2 vrf out"
    assert row.color == sig.SIGNAL_GOOD


def test_vrf_queue_red_on_low_subscription():
    """A depleted subscription stalls every acquisition and outranks depth."""
    row = sig.vrf_queue_signal(
        last_issued=1_042,
        next_to_process=1_041,
        subscription_balance=2 * 10**17,
        minimum_buffer=35 * 10**16,
    )
    assert row.color == sig.SIGNAL_BAD
    assert "SUBSCRIPTION LOW" in row.value_str
    assert "0.20" in row.value_str and "0.35" in row.value_str
    assert "stall" in row.value_str


def test_vrf_queue_deep_is_yellow():
    row = sig.vrf_queue_signal(
        last_issued=1_100,
        next_to_process=1_000,
        pending=8,
        selection_timeout_blocks=30,
    )
    assert row.color == sig.SIGNAL_WARN
    assert "depth 100" in row.value_str
    assert "stall after 30 blk" in row.value_str


def test_vrf_queue_boundary_depth_is_still_green():
    row = sig.vrf_queue_signal(last_issued=sig.QUEUE_DEPTH_OK, next_to_process=0)
    assert row.color == sig.SIGNAL_GOOD
    row = sig.vrf_queue_signal(last_issued=sig.QUEUE_DEPTH_OK + 1, next_to_process=0)
    assert row.color == sig.SIGNAL_WARN


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"last_issued": 10},
        {"next_to_process": 10},
        {"last_issued": 5, "next_to_process": 9},  # negative depth == decode bug
    ],
)
def test_vrf_queue_unavailable_inputs(kwargs: dict):
    row = sig.vrf_queue_signal(**kwargs)
    assert row.value_str == "VRF queue unavailable"
    assert row.color == sig.SIGNAL_MUTED


def test_vrf_queue_healthy_subscription_is_not_red():
    row = sig.vrf_queue_signal(
        last_issued=20,
        next_to_process=18,
        subscription_balance=3138 * 10**16,
        minimum_buffer=35 * 10**16,
    )
    assert row.color == sig.SIGNAL_GOOD


# ---------------------------------------------------------------------------
# 5. Parameter drift
# ---------------------------------------------------------------------------


def test_param_drift_filters_the_launch_write(config_events):
    """27 logs in, 6 genuine post-launch changes out (findings §13.11)."""
    assert len(config_events) == 27
    assert sig.launch_write_blocks(config_events) == {25_546_793}
    changes = sig.post_launch_changes(config_events)
    assert len(changes) == 6
    assert all(c["block_number"] != 25_546_793 for c in changes)


def test_launch_write_detected_without_the_constructor_only_keys(config_events):
    """Fallback path: a bulk write at the earliest block is still the launch."""
    trimmed = [e for e in config_events if e["key"] not in (1, 24, 63)]
    assert sig.launch_write_blocks(trimmed) == {25_546_793}
    assert len(sig.post_launch_changes(trimmed)) == 6


def test_tail_slice_has_no_launch_write(config_events):
    """An incremental tail carries no launch write and must not invent one."""
    tail = [e for e in config_events if e["blockNumber"] > 25_546_793]
    assert sig.launch_write_blocks(tail) == set()
    assert len(sig.post_launch_changes(tail)) == 6
    row = sig.param_drift_signal(tail)
    # No launch write means no "before" value — the row states the new value
    # rather than inventing a transition.
    assert row.value_str == "6 changes · crown tithe → 100"


def test_param_drift_launch_block_can_be_pinned(config_events):
    assert len(sig.post_launch_changes(config_events, launch_block=25_546_793)) == 6
    assert len(sig.post_launch_changes(config_events, launch_block=0)) == 27


def test_param_drift_detects_tithe_change(config_events):
    row = sig.param_drift_signal(config_events)
    assert row.color == sig.SIGNAL_WARN
    assert row.value_str == "6 changes · crown tithe 500→100"
    assert "21" not in row.value_str  # the launch write never leaks into the count


def test_param_drift_nominal(launch_only):
    """Launch write only: nothing has been changed since deployment."""
    assert len(launch_only) == 21
    row = sig.param_drift_signal(launch_only)
    assert row.value_str == "params nominal"
    assert row.color == sig.SIGNAL_GOOD


def test_param_drift_unavailable():
    for events in (None, [], [{"nonsense": 1}]):
        row = sig.param_drift_signal(events)
        assert row.value_str == "config history unavailable"
        assert row.color == sig.SIGNAL_MUTED


def test_param_drift_live_mismatch_is_red(config_events):
    """Live state disagreeing with the last ConfigSet is an anomaly, not drift."""
    row = sig.param_drift_signal(config_events, live_params={15: 250})
    assert row.color == sig.SIGNAL_BAD
    assert "live ≠ onchain history" in row.value_str
    assert "crown tithe" in row.value_str


def test_param_drift_live_agreement_reports_history_only(config_events):
    """Live matching the last ConfigSet is not a mismatch — 6 changes still shown."""
    row = sig.param_drift_signal(config_events, live_params={15: 100, 13: 1_000})
    assert row.color == sig.SIGNAL_WARN
    assert row.value_str == "6 changes · crown tithe 500→100"


def test_param_drift_missing_live_params_is_not_a_false_alarm(config_events):
    """Talismans posture: nothing to compare means quiet, never a red alarm."""
    for live in (None, {}, []):
        row = sig.param_drift_signal(config_events, live_params=live)
        assert row.color == sig.SIGNAL_WARN


def test_param_drift_never_implies_constructor_only_keys_are_settable(config_events):
    """Keys 1, 24 and 63 are constructor-only (findings §13.3)."""
    assert sig.is_settable(1) is False
    assert sig.is_settable(24) is False
    assert sig.is_settable(63) is False
    assert sig.is_settable(15) is True
    changes = sig.post_launch_changes(config_events)
    assert all(c["settable"] for c in changes)
    assert not {c["key"] for c in changes} & {1, 24, 63}


def test_param_drift_accepts_hex_and_snake_case_logs():
    """The log layer's shape is not pinned yet; both conventions decode."""
    events = [
        {"key": "0xf", "value": "0x1f4", "blockNumber": "0x185d029"},
        {"key": 1, "value": 900_000, "block_number": 25_546_793},
        {"key": 15, "value": 100, "block_number": 25_592_190},
    ]
    row = sig.param_drift_signal(events)
    assert row.value_str == "1 change · crown tithe 500→100"
    assert row.color == sig.SIGNAL_WARN


def test_param_drift_renders_bools_as_words():
    events = [
        {"key": 1, "value": 900_000, "block_number": 100},
        {"key": 41, "value": 0, "block_number": 100},
        {"key": 41, "value": 1, "block_number": 200},
    ]
    row = sig.param_drift_signal(events)
    assert row.value_str == "1 change · acquisitions off→on"


def test_resolve_config_params_flags_drift_against_history_only(config_events):
    params = sig.resolve_config_params(config_events, {15: 100, 13: 1_000, 17: 8_500})
    by_key = {p.key: p for p in params}
    assert by_key[15].name == "TOP_LISTING_SHARE_BPS"
    assert by_key[15].block_number == 25_592_190
    assert by_key[15].is_drift is False
    assert by_key[13].block_number == 25_546_793
    assert by_key[13].is_drift is False

    drifted = sig.resolve_config_params(config_events, {15: 500})
    assert drifted[0].is_drift is True  # matches the docs, contradicts the chain


def test_resolve_config_params_omits_keys_with_no_live_read(config_events):
    assert sig.resolve_config_params(config_events, None) == []
    assert len(sig.resolve_config_params(config_events, {15: 100})) == 1


# ---------------------------------------------------------------------------
# Cross-cutting contract
# ---------------------------------------------------------------------------


def _every_signal() -> list[FWASignal]:
    """One nominal and one degraded row from each of the five builders."""
    return [
        sig.pool_temp_signal(12, 0, 60, 3_600),
        sig.pool_temp_signal(1_830, None, 60, 3_600),
        sig.pool_temp_signal(4_000, 10_000, 60, 3_600),
        sig.pool_temp_signal(720, 0, 60, 3_600, 3_400),
        sig.pool_temp_signal(),
        sig.buy_gate_signal(False),
        sig.buy_gate_signal(True),
        sig.buy_gate_signal(None),
        sig.emissions_signal(EMISSION_STOP + 86_400, EMISSION_START, EMISSION_DURATION),
        sig.emissions_signal(EMISSION_STOP - 86_400, EMISSION_START, EMISSION_DURATION),
        sig.emissions_signal(),
        sig.vrf_queue_signal(1_042, 1_027, 3, 18, 2, 31 * 10**18, 35 * 10**16),
        sig.vrf_queue_signal(1_142, 1_027),
        sig.vrf_queue_signal(1_042, 1_041, subscription_balance=1, minimum_buffer=2),
        sig.vrf_queue_signal(),
        sig.param_drift_signal([{"key": 1, "value": 1, "block_number": 1}]),
        sig.param_drift_signal(None),
    ]


def test_all_signals_return_four_keys():
    for row in _every_signal():
        assert set(row.model_dump()) == {"label", "value_str", "indicator", "color"}
        assert row.label and row.value_str
        assert row.indicator == sig.INDICATOR


def test_all_colors_in_allowed_set():
    assert sig.SIGNAL_COLORS == {"$success", "$warning", "$error", "dim"}
    for row in _every_signal():
        assert row.color in sig.SIGNAL_COLORS


def test_no_signal_uses_a_css_colour_name():
    """The regression WP-19 fixed: CSS names, not theme variables.

    ``Static``/``Content`` markup resolves ``[green]`` through Textual's CSS
    name table to ``#008000``, whose contrast peaks at 4.09:1 against pure
    black — it fails WCAG AA on every background there is, so no palette can
    rescue it.  ``$success``/``$warning``/``$error`` resolve per theme and are
    required ``Theme`` fields, hence defined under all ten registered themes.
    """
    banned = {"green", "yellow", "red", "cyan", "magenta", "blue", "white"}
    assert not (sig.SIGNAL_COLORS & banned)
    for colour in sig.SIGNAL_COLORS:
        assert colour.startswith("$") or colour == sig.SIGNAL_MUTED
    for row in _every_signal():
        assert row.color not in banned


def test_every_builder_tolerates_all_none():
    """No builder raises on a completely dead input set (PRD §9)."""
    rows = [
        sig.pool_temp_signal(None, None),
        sig.buy_gate_signal(None),
        sig.emissions_signal(None, None, None, None),
        sig.vrf_queue_signal(None, None, None, None, None, None, None, None),
        sig.param_drift_signal(None, None),
    ]
    for row in rows:
        assert "unavailable" in row.value_str
        assert row.color == sig.SIGNAL_MUTED


def test_value_strings_fit_the_signals_panel():
    """The widget drops the label and renders ``value_str`` alone on one line.

    Talismans rows land around 65 characters; anything materially longer is
    clipped, and a clipped row silently loses the part that carries the meaning
    (the buy-gate footnote was 101 characters before this test existed).
    """
    for row in _every_signal():
        assert len(row.value_str) <= 64, row.value_str


def test_no_documented_default_hardcoded():
    """No ``500``-as-crown-tithe literal: the tithe is read live (PRD §7 rule 6)."""
    code = _code_only(_MODULE_SOURCE)
    assert not re.search(r"(?<![\d_.])500(?![\d_])", code)
    assert "TOP_LISTING_SHARE_BPS" not in code  # names come from the vendored map


def test_no_hardcoded_harmonic_arithmetic_gap():
    """The hm/am gap is a live ratio (findings §13.7-13.8), not a constant here."""
    for forbidden in ("3.885", "3.49", "hm_am", "gap_x"):
        assert forbidden not in _MODULE_SOURCE


# ---------------------------------------------------------------------------
# Scalar helpers
# ---------------------------------------------------------------------------


def test_invariant_summary_all_matching():
    assert (
        sig.invariant_summary(
            swept_total_weight=31_100,
            chain_total_weight=31_100,
            swept_weighted_backing=3_891 * 10**36,
            chain_weighted_backing=3_891 * 10**36,
            derived_fee_wei=136_260_883_651_302_691,
            chain_fee_wei=136_260_883_651_302_691,
            fee_share_total=3_891,
            active_listing_count=3_891,
        )
        is True
    )


def test_invariant_summary_catches_the_plausible_partial_sweep():
    """A sweep missing 255 slots is off by exactly 255e36 and looks fine."""
    assert (
        sig.invariant_summary(
            swept_weighted_backing=3_624 * 10**36,
            chain_weighted_backing=3_879 * 10**36,
        )
        is False
    )


def test_invariant_summary_off_by_one_wei_fails():
    assert (
        sig.invariant_summary(
            derived_fee_wei=136_260_883_651_302_692,
            chain_fee_wei=136_260_883_651_302_691,
        )
        is False
    )


def test_invariant_summary_skips_unavailable_pairs():
    assert sig.invariant_summary() is True
    assert sig.invariant_summary(swept_total_weight=10, chain_total_weight=None) is True
    assert sig.invariant_summary(fee_share_total=3_891, active_listing_count=3_890) is False


def test_degraded_label_exact_strings():
    assert sig.degraded_label("logs") == "logs unavailable — activity paused"
    assert sig.degraded_label("chain") == "chain unavailable"
    assert sig.degraded_label("state") == "chain unavailable"
    assert sig.degraded_label("LOGS") == "logs unavailable — activity paused"
    assert sig.degraded_label("market") == "market data unavailable"
    assert sig.degraded_label("floors") == "floor prices unavailable"
    assert sig.degraded_label("something-new") == "something-new unavailable"
    assert sig.degraded_label("") == "unavailable"


def test_as_of_label():
    ts = 1_785_870_083.0
    expected = time.strftime("as of %H:%M", time.localtime(ts))
    assert sig.as_of_label(ts) == expected
    assert sig.as_of_label(None) == "as of --:--"
    assert sig.as_of_label(float("nan")) in {expected, "as of --:--"}


def test_config_key_meta_loads_the_vendored_map():
    meta = sig.config_key_meta()
    assert meta[15]["name"] == "TOP_LISTING_SHARE_BPS"
    assert meta[41]["value_type"] == "bool"
    assert sig.config_key_name(15) == "TOP_LISTING_SHARE_BPS"
    assert sig.config_key_name(15, short=True) == "crown tithe"
    assert sig.config_key_name(9_999) == "key 9999"


# ---------------------------------------------------------------------------
# Sell-back mix -- moved here from the settlement table's subtitle
# ---------------------------------------------------------------------------


_MIX = [
    {"outcome": "bid_fwa", "count": 71_800},
    {"outcome": "bid_eth", "count": 21_160},
    {"outcome": "relist", "count": 6_016},
    {"outcome": "kept", "count": 4_281},
    {"outcome": "forced", "count": 90},
]


def test_sellback_is_computed_from_the_rows():
    """Never hardcoded: the shares move and a frozen number goes stale."""
    row = sig.sellback_signal(_MIX)

    total = sum(r["count"] for r in _MIX)
    expected = 100.0 * (71_800 + 21_160) / total
    assert f"{expected:.1f}%" in row.value_str
    assert "sell straight back" in row.value_str
    assert "keep the NFT" in row.value_str


def test_sellback_counts_both_bid_currencies():
    """Taking the bid in $FWA or in ETH are both selling straight back."""
    only_fwa = sig.sellback_signal([{"outcome": "bid_fwa", "count": 1}])
    both = sig.sellback_signal(
        [{"outcome": "bid_fwa", "count": 1}, {"outcome": "bid_eth", "count": 1}]
    )

    assert "100.0%" in only_fwa.value_str
    assert "100.0%" in both.value_str


def test_sellback_missing_mix_is_unavailable_not_zero():
    """A failed log read must not render '0.0% sell straight back'.

    That would invert the protocol's headline fact -- roughly nine in ten
    purchasers sell straight back -- on exactly the failure where the reader
    can least afford to be misled.
    """
    for empty in (None, [], [{"outcome": "bid_fwa", "count": 0}]):
        row = sig.sellback_signal(empty)
        assert "0.0%" not in row.value_str
        assert row.color == sig.SIGNAL_MUTED


def test_sellback_row_fits_the_signals_panel():
    row = sig.sellback_signal(_MIX)

    assert len(row.value_str) + 2 <= 55, (
        f"sellback row is {len(row.value_str) + 2} columns: {row.value_str!r}"
    )
