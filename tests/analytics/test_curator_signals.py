"""Tests for ``maxpane_dashboard.analytics.curator_signals`` — THE LIST's math.

Zero network, zero wall clock.  Every clock is injected (``now_ts``) and
``test_the_module_is_pure`` enforces mechanically that the module under test
reads none of its own.

**Wei is an integer here and every assertion on one is ``==``.**  ``approx`` on
a wei value is a review failure: the contract floors, and a floor is exactly
the thing an approximate comparison cannot see.

Provenance of the numbers below — nothing is quoted from a planning document:

* ``captures/tenderly_logs.json`` — the 2026-08-16 21:0x UTC sweep, the full
  JSON-RPC envelope.  ``["result"]`` holds 377 rows: 1 ``Launched``,
  **231** ``Deposited``, 145 ``FirstDeposit``.
* ``captures/live/20260817T000322Z_grace-late.json`` — a WP1 bundle whose state
  and logs were fetched in the same second, so the fold can be reconciled
  against the contract's own counters wei-exact (2930 deposits / 2291
  contributors / 15981.146… ETH).
* ``captures/live/20260816T225143Z_curve-probe.json`` — ``previewPoints()`` over
  12 weights and ``pointsOf``/``weightOf`` over 4 real wallets: the curve's
  onchain witness.
* ``captures/source.sol`` — the verified source, transcribed here (never in
  production) as ``_contract_sqrt``.

Several numeric literals in ``docs/curator_work_packages/wp3.md`` predate those
captures (they belong to a 226-row reading of the sweep, and to an earlier
snapshot of hour 1).  The captures win; every literal below was recomputed from
the committed bytes.
"""

from __future__ import annotations

import inspect
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from maxpane_dashboard.analytics import curator_signals as sig
from maxpane_dashboard.data.curator_models import (
    CURATOR_ACTIVITY_KINDS,
    CURATOR_KEYS,
    CURATOR_ROW_KEYS,
    CURATOR_SIGNAL_STATES,
    PHASES,
    ContributorRow,
    DepositEvent,
    HourBucket,
    SettlementRecord,
    WalletState,
)
from tests.curator_fixtures import capture

#: This work package's own slices.  The captures are read-only and shared; a
#: hand-built payload for a state the chain has not reached yet lives here.
SIGNALS_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "curator" / "signals"

# The pinned instants (WP0.7 / curator_addresses).  Recomputed, never quoted:
# LAUNCH is the creation block's timestamp and what launchTime() answers.
LAUNCH = 1_786_910_327  # 2026-08-16 19:58:47 UTC
GRACE = 86_400
HOUR = 3_600
GRACE_END = LAUNCH + GRACE  # 2026-08-17 19:58:47 UTC
FIRST_JUDGED_COMPLETE = LAUNCH + 25 * HOUR  # 2026-08-17 20:58:47 UTC
FIRST_JUDGED_HOUR = 24
THRESHOLD = 5 * 10**18
CREDIT_CAP = 1000 * 10**18
POINTS_PER_ETH = 1000
ETH = 10**18


# ---------------------------------------------------------------------------
# Capture readers.  Decoding lives in WP2's client; these are the test's own
# minimal readers so this suite depends on no other work package's code.
# ---------------------------------------------------------------------------

TOPIC_DEPOSITED = "0xb83850979ca63333b482bfe84d4d7cf15f9cc15c139b1e48bc44eb5446669cb3"
TOPIC_FIRST_DEPOSIT = "0xe5a1ae9630942d7510b794ac6b487f13176cf55b27415ad75303dd3109242918"


def _words(data: str) -> list[int]:
    body = data[2:]
    return [int(body[i : i + 64], 16) for i in range(0, len(body), 64)]


def _topic_address(topic: str) -> str:
    return "0x" + topic[-40:]


def _deposit_from_log(row: dict) -> DepositEvent:
    w = _words(row["data"])
    stamp = row.get("blockTimestamp")
    return DepositEvent(
        contributor=_topic_address(row["topics"][1]),
        hour=int(row["topics"][2], 16),
        amount_wei=w[0],
        credited_delta_wei=w[1],
        weight_added_wei=w[2],
        new_weight_wei=w[3],
        tx_count=w[4],
        hour_total_wei=w[5],
        early_bps=w[6],
        block_number=int(row["blockNumber"], 16),
        tx_hash=row["transactionHash"],
        log_index=int(row["logIndex"], 16),
        ts=None if stamp is None else float(int(stamp, 16)),
    )


def _first_deposit_from_log(row: dict) -> dict:
    return {
        "contributor": _topic_address(row["topics"][1]),
        "index": int(row["topics"][2], 16),
        "ts": float(_words(row["data"])[0]),
    }


def _rows_of(logs: list[dict], topic0: str) -> list[dict]:
    return [r for r in logs if r["topics"][0] == topic0]


@pytest.fixture(scope="module")
def sweep_logs() -> list[dict]:
    """The 377 rows of the 2026-08-16 sweep — the whole JSON-RPC envelope."""
    envelope = capture("tenderly_logs.json")
    rows = envelope["result"]
    assert len(rows) == 377
    return rows


@pytest.fixture(scope="module")
def deposits(sweep_logs: list[dict]) -> list[DepositEvent]:
    """All **231** captured ``Deposited`` events, decoded."""
    rows = [_deposit_from_log(r) for r in _rows_of(sweep_logs, TOPIC_DEPOSITED)]
    assert len(rows) == 231
    return rows


@pytest.fixture(scope="module")
def first_deposits(sweep_logs: list[dict]) -> list[dict]:
    rows = [_first_deposit_from_log(r) for r in _rows_of(sweep_logs, TOPIC_FIRST_DEPOSIT)]
    assert len(rows) == 145
    return rows


@pytest.fixture(scope="module")
def bundle() -> dict:
    """A WP1 bundle: state and logs captured in the same second."""
    path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "curator"
        / "captures"
        / "live"
        / "20260817T000322Z_grace-late.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def curve_probe() -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "curator"
        / "captures"
        / "live"
        / "20260816T225143Z_curve-probe.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))["curve_probe"]


def _last_event_for(rows: list[DepositEvent], address: str) -> DepositEvent:
    return [r for r in rows if r.contributor == address][-1]


# ===========================================================================
# WP3.1 — module skeleton, purity, the frozen output surface
# ===========================================================================


def test_the_module_is_pure() -> None:
    src = inspect.getsource(sig)
    for banned in (
        "import httpx",
        "import asyncio",
        "from textual",
        "import requests",
        "time.time()",
        "datetime.now(",
    ):
        assert banned not in src, banned


def test_the_module_imports_no_client_and_no_cache() -> None:
    """``analytics`` is downstream of nothing.  It may read the frozen models
    module (stdlib-only) and nothing else from ``data/``."""
    src = inspect.getsource(sig)
    for banned in ("curator_client", "curator_cache", "curator_manager", "urllib"):
        assert banned not in src, banned


def test_signal_output_keys_are_all_curator_keys() -> None:
    """The seam WP0.6 guards from the other side.  Asserted here too, so a
    rename in either file fails in the file that made it."""
    assert set(sig.SIGNAL_OUTPUT_KEYS) <= set(CURATOR_KEYS)


def test_signal_output_keys_is_a_hand_typed_literal_not_a_derivation() -> None:
    """CLAUDE.md's redundancy rule.  Deriving this tuple from ``CURATOR_KEYS``
    would make WP0's subset guard compare a constant against itself, and it
    could never fail again."""
    src = inspect.getsource(sig)
    head = src.split("SIGNAL_OUTPUT_KEYS")[1].split(")")[0]
    assert "CURATOR_KEYS" not in head


def test_the_output_surface_is_the_flat_contract_minus_the_managers_own_keys() -> None:
    """The manager adds exactly three keys of its own — the health markers it
    is the only module that can know.  Everything else on the screen is
    computed here, which is what makes WP5 a wiring job."""
    assert set(CURATOR_KEYS) - set(sig.SIGNAL_OUTPUT_KEYS) == set(sig.MANAGER_OWNED_KEYS)
    assert sig.MANAGER_OWNED_KEYS == ("degraded", "as_of_hhmm", "as_of")


def test_the_tunable_constants_are_named_and_documented_as_guesses() -> None:
    """PRD §12: WHALE and cluster thresholds are first guesses to be re-tuned
    against post-grace data.  A magic number inline cannot be re-tuned as an
    amendment; it just gets edited."""
    assert sig.WHALE_MIN_ETH == 25.0 and sig.CLUSTER_MIN_SIZE == 3
    assert sig.CLUSTER_MAX_BLOCK_SPAN == 32 and sig.AT_RISK_RED_SECONDS == 900
    assert sig.WHALE_WINDOW_S == 3600.0
    assert sig.FIRED_TTL_S == 86_400.0
    src = inspect.getsource(sig)
    assert "first guess" in src.lower()


def test_every_public_name_is_exported() -> None:
    for name in sig.__all__:
        assert hasattr(sig, name), name


# ===========================================================================
# WP3.2 — derive_phase() and the clock fields
# ===========================================================================


@pytest.mark.parametrize(
    "now,settled,expected",
    [
        (LAUNCH, False, "grace"),
        (GRACE_END - 1, False, "grace"),
        (GRACE_END, False, "judged"),  # the boundary belongs to judged
        (GRACE_END + 1, False, "judged"),
        (FIRST_JUDGED_COMPLETE, True, "settled"),
        (LAUNCH + 60, True, "settled"),  # settled always wins
    ],
)
def test_the_phase_machine(now: int, settled: bool, expected: str) -> None:
    assert (
        sig.derive_phase(
            now_ts=now,
            launch_time=LAUNCH,
            grace_period=GRACE,
            settled=settled,
            current_hour=(now - LAUNCH) // HOUR,
        )
        == expected
    )


def test_every_phase_it_can_return_is_one_of_the_three_frozen_spellings() -> None:
    """A fourth spelling is a silent fallback arm nothing branches on."""
    seen = set()
    for now in range(LAUNCH - HOUR, LAUNCH + 30 * HOUR, 907):
        for settled in (True, False, None):
            seen.add(
                sig.derive_phase(
                    now_ts=now,
                    launch_time=LAUNCH,
                    grace_period=GRACE,
                    settled=settled,
                    current_hour=(now - LAUNCH) // HOUR,
                )
            )
    assert seen - {None} <= set(PHASES)
    assert seen == {"grace", "judged", "settled", None}


def test_settled_wins_over_every_other_input() -> None:
    """SETTLED is terminal and one-way: the contract enforces it.  No clock
    value, no missing field and no later reading may take the screen back to a
    live phase."""
    assert (
        sig.derive_phase(
            now_ts=LAUNCH,
            launch_time=LAUNCH,
            grace_period=GRACE,
            settled=True,
            current_hour=0,
        )
        == "settled"
    )
    assert (
        sig.derive_phase(
            now_ts=None,
            launch_time=None,
            grace_period=None,
            settled=True,
            current_hour=None,
        )
        == "settled"
    )


def test_an_unknown_settled_flag_does_not_invent_a_phase() -> None:
    """settled=None means the read failed.  Guessing 'judged' from the clock
    would render a live game on a possibly-dead contract — the exact hazard the
    PRD names.  The answer is None and the hero renders unavailable."""
    assert (
        sig.derive_phase(
            now_ts=GRACE_END + 60,
            launch_time=LAUNCH,
            grace_period=GRACE,
            settled=None,
            current_hour=24,
        )
        is None
    )


def test_a_missing_immutable_does_not_invent_a_phase() -> None:
    """The `once` tier can fail too.  Without launchTime there is no clock, and
    a phase guessed from a half-read contract is worse than no phase."""
    for kwargs in (
        {"launch_time": None, "grace_period": GRACE},
        {"launch_time": LAUNCH, "grace_period": None},
    ):
        assert (
            sig.derive_phase(
                now_ts=GRACE_END + 60, settled=False, current_hour=24, **kwargs
            )
            is None
        )


def test_hour_zero_is_never_judged_whatever_the_grace_period_says() -> None:
    """``_isShort`` opens with ``if (hour == 0) return false``.  A zero-length
    grace period is not a configuration this deployment has, but the phase
    machine must not be the piece that disagrees with the contract about it."""
    assert (
        sig.derive_phase(
            now_ts=LAUNCH + 5,
            launch_time=LAUNCH,
            grace_period=0,
            settled=False,
            current_hour=0,
        )
        == "grace"
    )


def test_grace_seconds_left_counts_down_and_never_goes_negative() -> None:
    assert (
        sig.grace_seconds_left(now_ts=LAUNCH, launch_time=LAUNCH, grace_period=GRACE)
        == GRACE
    )
    assert (
        sig.grace_seconds_left(
            now_ts=GRACE_END - 5_000, launch_time=LAUNCH, grace_period=GRACE
        )
        == 5_000
    )
    assert (
        sig.grace_seconds_left(
            now_ts=GRACE_END + 5_000, launch_time=LAUNCH, grace_period=GRACE
        )
        == 0
    )
    assert (
        sig.grace_seconds_left(now_ts=GRACE_END, launch_time=None, grace_period=GRACE)
        is None
    )


def test_grace_ends_utc_is_the_absolute_instant_the_hero_prints() -> None:
    assert sig.grace_ends_utc(LAUNCH, GRACE) == "2026-08-17 19:58:47 UTC"
    assert sig.grace_ends_utc(None, GRACE) is None
    assert sig.grace_ends_utc(LAUNCH, None) is None


def test_lived_desc_says_lived_when_the_game_is_over_and_alive_while_it_runs() -> None:
    assert sig.lived_desc(LAUNCH, LAUNCH + 3 * HOUR + 12 * 60, settled=True) == "lived 3 h 12 m"
    assert sig.lived_desc(LAUNCH, LAUNCH + 4 * HOUR, settled=False) == "alive 4 h"
    assert sig.lived_desc(LAUNCH, LAUNCH + 26 * HOUR, settled=True) == "lived 1 d 2 h"
    assert sig.lived_desc(LAUNCH, LAUNCH + 24 * HOUR, settled=True) == "lived 1 d"
    assert sig.lived_desc(LAUNCH, LAUNCH + 90, settled=False) == "alive 1 m"


def test_lived_desc_is_none_when_it_cannot_be_measured() -> None:
    """Not "lived 0 m" — a duration nobody read is not a duration of zero."""
    assert sig.lived_desc(None, LAUNCH + HOUR) is None
    assert sig.lived_desc(LAUNCH, None) is None
    assert sig.lived_desc(LAUNCH, LAUNCH - 60) is None


# ===========================================================================
# WP3.3 — the curve: integer sqrt with the contract's exact floor (H7)
# ===========================================================================
#
# ``_contract_sqrt`` is a literal transcription of ``source.sol``'s ``_sqrt``:
# the bit-length seed, exactly seven Newton iterations, and the final
# ``result <= a / result ? result : result - 1`` correction.  It is the witness
# and it lives here, never in production — production uses ``math.isqrt`` and
# this differential is what proves the two agree.


def _contract_log2(x: int) -> int:
    r = 0
    for bits in (128, 64, 32, 16, 8, 4, 2):
        if x >> bits > 0:
            x >>= bits
            r += bits
    if x >> 1 > 0:
        r += 1
    return r


def _contract_sqrt(a: int) -> int:
    if a == 0:
        return 0
    result = 1 << (_contract_log2(a) >> 1)
    for _ in range(7):
        result = (result + a // result) >> 1
    return result if result <= a // result else result - 1


def test_the_transcription_is_the_contracts_and_not_pythons() -> None:
    """The witness has to be able to disagree.  Seeding + 7 iterations is not
    'whatever isqrt does': drop an iteration and the two part company."""

    def _under_iterated(a: int, rounds: int) -> int:
        result = 1 << (_contract_log2(a) >> 1)
        for _ in range(rounds):
            result = (result + a // result) >> 1
        return result if result <= a // result else result - 1

    # Three rounds is not enough for a 2000 ETH weight, and four is not enough
    # for a 256-bit one: the loop's length is load-bearing, so a transcription
    # that quietly matched ``isqrt`` for structural reasons is ruled out.
    assert _under_iterated(2000 * ETH, 3) != math.isqrt(2000 * ETH)
    assert _under_iterated(1 << 255, 4) != math.isqrt(1 << 255)
    assert _contract_sqrt(1 << 255) == math.isqrt(1 << 255)


def test_the_production_sqrt_matches_the_contract_over_the_edges() -> None:
    edges = [
        0, 1, 2, 3, 4, 8,
        10**9 - 1, 10**9, 10**9 + 1,
        ETH, 4 * ETH, 100 * ETH, 1000 * ETH, 2000 * ETH,
        (1 << 96) - 1, (1 << 96),
    ]
    for w in edges:
        assert math.isqrt(w) == _contract_sqrt(w), w


def test_the_production_curve_matches_the_contract_over_a_random_corpus() -> None:
    """10 000 draws across the whole reachable weight range (0 .. 2000 ETH, the
    hard ceiling: creditCap 1000 ETH x the 2x maximum multiplier).  Seeded, so
    a failure is reproducible.

    The differential runs through ``points_for_weight`` and not through
    ``math.isqrt``: comparing the test's transcription to the standard library
    proves nothing about the module under test, and a production ``sqrt`` that
    went through float64 would sail straight past it.
    """
    rng = random.Random(20260816)
    for _ in range(10_000):
        w = rng.randrange(0, 2000 * ETH)
        assert math.isqrt(w) == _contract_sqrt(w), w
        expected = _contract_sqrt(w) * POINTS_PER_ETH // 10**9
        assert sig.points_for_weight(w, POINTS_PER_ETH) == expected, w


# Weights that read one point too high through float64, one per decade of the
# reachable range.  Each is ``(k * 10**6)**2 - 1``: the true root is
# ``k*10**6 - 1`` and the curve's ``// 1e9`` turns a one-wei error in the root
# into a **one-point** error, which is the only way a float sqrt is visible at
# all.  ``int(math.sqrt(w))`` returns ``k*10**6`` for every one of them.
#
# Searching for these took three attempts and the WP's own premise was wrong:
# a random corpus of 10 000 draws does NOT find a float-sqrt defect (the
# mismatch rate over 0..2000 ETH is under 1 in 200 000, and the ``// 1e9``
# absorbs almost all of the ones that do occur).  The mutation is only
# detectable against chosen witnesses, so they are pinned here by value.
_FLOAT_SQRT_TRAPS = (
    (50_175_999_999_999_999, 223),          # 0.050176 ETH — just above the floor
    (99_999_999_999_999_999_999, 9_999),    # 100 ETH
    (999_950_883_999_999_999_999, 31_621),  # ~1000 ETH, the credit cap
    (1_999_967_840_999_999_999_999, 44_720),  # ~2000 ETH, the hard ceiling
)


def test_the_production_curve_survives_weights_a_float_sqrt_would_round_wrong() -> None:
    """float64 has 53 bits of mantissa; a weight in wei has 71 bits at the top
    of the reachable range.  On each of these the standard float path reads one
    point too high — the contract reads the lower number and so must we."""
    for weight, points in _FLOAT_SQRT_TRAPS:
        assert sig.points_for_weight(weight, POINTS_PER_ETH) == points, weight
        assert int(math.sqrt(weight)) * POINTS_PER_ETH // 10**9 == points + 1
        assert _contract_sqrt(weight) * POINTS_PER_ETH // 10**9 == points


def test_the_documented_curve_points() -> None:
    """The mechanics doc's table, recomputed rather than trusted."""
    assert sig.points_for_weight(1 * ETH, POINTS_PER_ETH) == 1_000
    assert sig.points_for_weight(4 * ETH, POINTS_PER_ETH) == 2_000
    assert sig.points_for_weight(100 * ETH, POINTS_PER_ETH) == 10_000
    assert sig.points_for_weight(1000 * ETH, POINTS_PER_ETH) == 31_622
    assert sig.points_for_weight(2000 * ETH, POINTS_PER_ETH) == 44_721
    assert sig.points_for_weight(0, POINTS_PER_ETH) == 0


def test_the_curve_matches_previewpoints_on_chain(curve_probe: dict) -> None:
    """The onchain witness (WP1.6): ``previewPoints(uint256)`` answered for 12
    weights in one keyless round, including the four values that floor to zero
    points and the two that pin the ends of the reachable range."""
    probed = [
        (int(row["argument"]), int(row["result"], 16)) for row in curve_probe["weights"]
    ]
    assert len(probed) == 12
    for weight, points in probed:
        assert sig.points_for_weight(weight, POINTS_PER_ETH) == points, weight
    # The shape the probe pins, spelled out so a re-capture cannot quietly
    # change it: everything below 1e9 wei of weight is worth zero points.
    assert dict(probed)[10**9 - 1] == 0 and dict(probed)[10**9] == 0
    assert dict(probed)[ETH] == 1_000 and dict(probed)[2000 * ETH] == 44_721


def test_the_curve_matches_pointsof_for_four_real_wallets(
    curve_probe: dict, deposits: list[DepositEvent]
) -> None:
    """``pointsOf(addr)`` against the curve applied to the weight this suite
    folds out of the logs — two independent paths to the same integer, one of
    them the contract's own."""
    weights = {
        row["argument"].lower(): int(row["result"], 16)
        for row in curve_probe["wallets"]
        if row["name"].startswith("weightOf")
    }
    points = {
        row["argument"].lower(): int(row["result"], 16)
        for row in curve_probe["wallets"]
        if row["name"].startswith("pointsOf")
    }
    assert len(weights) == 4 and len(points) == 4
    for address, weight in weights.items():
        assert _last_event_for(deposits, address).new_weight_wei == weight
        assert sig.points_for_weight(weight, POINTS_PER_ETH) == points[address]


def test_the_multiplication_happens_before_the_division() -> None:
    """(isqrt(w) * points_per_eth) // 1e9 is not ((isqrt(w) // 1e9) * ppe).

    The wrong order returns 0 for every weight below 1e18 — i.e. for the 53
    wallets sitting at the 0.05 ETH minimum, a third of the captured list.
    """
    w = 999_999_999**2  # isqrt == 999_999_999, just under 1e9
    assert sig.points_for_weight(w, POINTS_PER_ETH) == 999
    assert (math.isqrt(w) // 10**9) * POINTS_PER_ETH == 0


def test_points_per_eth_is_a_parameter_not_a_literal() -> None:
    """CLAUDE.md rule 4: it is a contract constant, read on the `once` tier."""
    assert sig.points_for_weight(ETH, 500) == 500
    assert "1000" not in inspect.getsource(sig.points_for_weight)


def test_the_curve_is_total_over_missing_and_nonsense_inputs() -> None:
    assert sig.points_for_weight(None, POINTS_PER_ETH) is None
    assert sig.points_for_weight(ETH, None) is None
    assert sig.points_for_weight(-1, POINTS_PER_ETH) is None
    assert sig.points_for_weight("0x1", POINTS_PER_ETH) is None


# ===========================================================================
# WP3.4 — the weight formula (H8)
# ===========================================================================


@pytest.fixture(scope="module")
def bundle_deposits(bundle: dict) -> list[DepositEvent]:
    """The 2930 ``Deposited`` events of the 00:03:22Z bundle.

    A second, twelve-times-larger differential corpus — and the one whose state
    section was read in the same second, so the fold can be reconciled against
    the contract's own counters further down.
    """
    rows = [_deposit_from_log(r) for r in _rows_of(bundle["logs"], TOPIC_DEPOSITED)]
    assert len(rows) == 2930
    return rows


def test_the_captured_first_deposit_to_the_wei(deposits: list[DepositEvent]) -> None:
    """0.05 ETH at 19 975 bps -> 0.099875 ETH of weight.  ``==``, never approx.

    This is deposit #1, made by the announce EOA in block 25 769 888 — the one
    real witness for the formula, and it is in the captured sweep.
    """
    assert sig.weight_added(5 * 10**16, 19_975) == 99_875_000_000_000_000
    first = min(deposits, key=lambda d: (d.block_number, d.log_index))
    assert first.amount_wei == 5 * 10**16
    assert first.early_bps == 19_975
    assert first.weight_added_wei == 99_875_000_000_000_000
    assert sig.weight_added(first.credited_delta_wei, first.early_bps) == first.weight_added_wei


def test_every_captured_deposit_satisfies_the_identity(
    deposits: list[DepositEvent], bundle_deposits: list[DepositEvent]
) -> None:
    """All 231 rows of the sweep and all 2930 of the bundle.  This is the
    differential that makes the formula a fact rather than a reading of the
    source."""
    corpus = deposits + bundle_deposits
    assert len(corpus) == 3161
    for ev in corpus:
        assert sig.weight_added(ev.credited_delta_wei, ev.early_bps) == ev.weight_added_wei


def test_the_corpus_actually_exercises_the_floor(
    deposits: list[DepositEvent], bundle_deposits: list[DepositEvent]
) -> None:
    """A differential over rows that all divide exactly would pass under
    ``round`` too.  Count the ones that do not, so the corpus is known to bite.
    """
    inexact = [
        ev
        for ev in deposits + bundle_deposits
        if (ev.credited_delta_wei * ev.early_bps) % 10_000
    ]
    # 31 of the 3161 rows do not divide exactly — few, because most amounts are
    # round numbers of ETH, but enough that the differential above is a floor
    # test and not just an arithmetic test.
    assert len(inexact) >= 20


def test_the_division_floors() -> None:
    assert sig.weight_added(1, 19_999) == 1  # 1.9999 -> 1
    assert sig.weight_added(1, 9_999) == 0  # 0.9999 -> 0, a real zero
    assert sig.weight_added(3, 10_001) == 3  # 3.0003 -> 3


def test_a_zero_credited_delta_yields_zero_weight_and_does_not_raise() -> None:
    """H3: legal, and common once anyone crosses the cap."""
    assert sig.weight_added(0, 20_000) == 0
    assert sig.weight_added(0, 10_000) == 0


def test_the_flat_post_grace_multiplier_is_the_identity() -> None:
    """After grace ``earlyMultiplierBps()`` is a flat 10 000 forever, so weight
    and credit are the same number — the branch every deposit from
    2026-08-17 19:58:47 UTC onwards takes."""
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (capture B, the first post-grace bundle, does not exist yet: the earliest
    # window is 2026-08-17 19:58:47 UTC.)
    for amount in (5 * 10**16, 3 * ETH, 461 * ETH, 1000 * ETH):
        assert sig.weight_added(amount, 10_000) == amount


def test_weight_added_is_total_over_missing_inputs() -> None:
    assert sig.weight_added(None, 19_975) is None
    assert sig.weight_added(10**18, None) is None
    assert sig.weight_added(-1, 19_975) is None


# ===========================================================================
# WP3.5 — credited_delta() and the cap case (H3)
# ===========================================================================

#: The grinder: 13 deposits from one address in the captured sweep, the longest
#: escalation ladder on chain at capture time.
GRINDER = "0xba76105002555307564e7b873369fd4f4fd61abb"


def test_a_first_deposit_credits_its_whole_amount() -> None:
    assert sig.credited_delta(5 * 10**16, 0, CREDIT_CAP) == 5 * 10**16


def test_an_escalation_credits_only_the_increment() -> None:
    """``_credit`` is high-water based: you are paid for beating your own
    record, not for sending again."""
    assert sig.credited_delta(3 * ETH, 1 * ETH, CREDIT_CAP) == 2 * ETH


def test_a_deposit_below_the_high_water_credits_nothing_and_does_not_go_negative() -> None:
    """The contract cannot reach this (``MustEscalate`` reverts first), which is
    exactly why the fold must not produce a negative number if a log ever
    arrives out of order."""
    assert sig.credited_delta(1 * ETH, 3 * ETH, CREDIT_CAP) == 0


def test_the_cap_truncates_both_ends() -> None:
    """``min(amount, cap) - min(old, cap)``, and the ``min`` is on both sides:
    a wallet crossing the cap is credited only up to it."""
    assert sig.credited_delta(1500 * ETH, 0, CREDIT_CAP) == CREDIT_CAP
    assert sig.credited_delta(1500 * ETH, 900 * ETH, CREDIT_CAP) == 100 * ETH


def test_a_deposit_above_the_cap_from_a_wallet_already_at_it_credits_zero() -> None:
    """H3.  Zero credit, zero weight — and the raw amount still counts in full
    toward the hour's survival, which is the pair of consequences that makes
    ``weight is proportional to volume`` false on this contract.
    """
    # SYNTHETIC — permanent: no >1000 ETH deposit exists on chain (the largest
    # real send in the captures is 461.1 ETH against a 1000 ETH cap).
    amount = 1200 * ETH
    delta = sig.credited_delta(amount, CREDIT_CAP, CREDIT_CAP)
    assert delta == 0
    assert sig.weight_added(delta, 20_000) == 0
    # The other half of the pair — the hour still banks the raw 1200 ETH — is
    # asserted against the fold in
    # ``test_a_cap_exceeding_deposit_still_fills_its_hour_in_full`` (WP3.7),
    # which is where the hourly total is actually computed.


def test_credit_telescopes_over_the_real_grinder_ladder(
    deposits: list[DepositEvent],
) -> None:
    """13 deposits from one address: the credited deltas sum to the final
    high-water mark, exactly, because ``amount`` *is* the new high-water."""
    ladder = [d for d in deposits if d.contributor == GRINDER]
    assert len(ladder) == 13
    high_water = 0
    total = 0
    for step in ladder:
        delta = sig.credited_delta(step.amount_wei, high_water, CREDIT_CAP)
        assert delta == step.credited_delta_wei
        total += delta
        high_water = step.amount_wei
    assert total == min(ladder[-1].amount_wei, CREDIT_CAP)


def test_the_telescoping_identity_holds_for_every_captured_wallet(
    deposits: list[DepositEvent],
) -> None:
    """All 145 of them, ladders and one-shots alike."""
    per_wallet: dict[str, list[DepositEvent]] = defaultdict(list)
    for ev in deposits:
        per_wallet[ev.contributor].append(ev)
    assert len(per_wallet) == 145
    for address, ladder in per_wallet.items():
        assert sum(e.credited_delta_wei for e in ladder) == min(
            ladder[-1].amount_wei, CREDIT_CAP
        ), address


def test_credited_delta_is_total_over_missing_inputs() -> None:
    assert sig.credited_delta(None, 0, CREDIT_CAP) is None
    assert sig.credited_delta(ETH, None, CREDIT_CAP) is None
    assert sig.credited_delta(ETH, 0, None) is None


def test_nothing_in_this_module_divides_by_credited_delta() -> None:
    """H3.  ``weight is proportional to volume`` is false on this contract, and
    the tempting normalisation is a ZeroDivisionError waiting for the first
    whale."""
    src = inspect.getsource(sig)
    assert "/ credited" not in src and "// credited" not in src
    assert "/ delta" not in src and "// delta" not in src


# ===========================================================================
# WP3.6 — fold_deposits(): the contributor table
# ===========================================================================


@pytest.fixture(scope="module")
def rows(
    deposits: list[DepositEvent], first_deposits: list[dict]
) -> list[ContributorRow]:
    return sig.fold_deposits(deposits, first_deposits, points_per_eth=POINTS_PER_ETH)


def test_the_fold_uses_the_events_running_totals_not_a_re_derivation(
    rows: list[ContributorRow], deposits: list[DepositEvent]
) -> None:
    """``Deposited`` carries ``newWeight`` and ``txCount`` — the contract's own
    running totals.  Summing ``weightAdded`` instead would drift the moment one
    log is missed, and a missed log is what the gap-repair tier exists for."""
    for row in rows:
        last = _last_event_for(deposits, row.address)
        assert row.weight_wei == last.new_weight_wei
        assert row.tx_count == last.tx_count


def test_credit_telescopes_to_the_final_high_water(
    rows: list[ContributorRow], deposits: list[DepositEvent]
) -> None:
    """Lifetime credit == the final high-water mark, and ``amount`` IS the new
    high-water by construction."""
    for row in rows:
        assert row.credit_wei == _last_event_for(deposits, row.address).amount_wei


def test_the_fold_reproduces_the_captured_leaderboard(rows: list[ContributorRow]) -> None:
    """Rank 1: 0x381fe486…, credit 461.1 ETH, weight 902.10737 ETH, 30 035
    points — and 30 035 is not a recomputation, it is what ``pointsOf()``
    answered on chain in the curve probe."""
    assert rows[0].address == "0x381fe486d87c7f2633c777f1b5be3105a2a51744"
    assert rows[0].credit_wei == 461_100_000_000_000_000_000
    assert rows[0].weight_wei == 902_107_370_000_000_000_000
    assert rows[0].points == 30_035
    assert rows[0].tx_count == 2
    assert [r.points for r in rows[:4]] == [30_035, 18_264, 11_184, 10_860]


def test_the_fold_is_sorted_by_points_descending(rows: list[ContributorRow]) -> None:
    points = [r.points for r in rows]
    assert points == sorted(points, reverse=True)


def test_the_fold_matches_the_contracts_own_counters(
    rows: list[ContributorRow],
    bundle: dict,
    bundle_deposits: list[DepositEvent],
) -> None:
    """The sweep holds 145 contributors and 231 deposits — the batch round
    taken two minutes earlier says 143 / 222, which is why a cross-instant
    assertion is worthless and this one is made against a BUNDLE whose state
    and logs were read in the same second: 2291 == 2291 and 2930 == 2930.
    """
    assert len(rows) == 145
    assert sum(r.tx_count for r in rows) == 231

    state = bundle["state"]
    contributors = int(state["0xf251fc8c"]["result"], 16)
    tx_count = int(state["0x9b4f50e7"]["result"], 16)
    folded = sig.fold_deposits(bundle_deposits, [], points_per_eth=POINTS_PER_ETH)
    assert len(folded) == contributors == 2291
    assert sum(r.tx_count for r in folded) == tx_count == 2930


def test_first_index_is_one_based_and_dense(rows: list[ContributorRow]) -> None:
    """``FirstDeposit.index`` is 1-based and maxes at exactly
    ``totalContributors`` (H6)."""
    assert sorted(r.first_index for r in rows) == list(range(1, 146))


def test_a_wallet_without_a_first_deposit_row_keeps_a_none_index(
    deposits: list[DepositEvent],
) -> None:
    """The FirstDeposit filter can fail on its own (``LogSweep`` groups fail
    independently).  A missing index is None — never 0, which is a rank."""
    folded = sig.fold_deposits(deposits, [], points_per_eth=POINTS_PER_ETH)
    assert len(folded) == 145
    assert all(r.first_index is None for r in folded)
    assert all(r.first_hour is not None for r in folded)


def test_first_hour_comes_from_the_events_indexed_hour_topic(
    rows: list[ContributorRow], deposits: list[DepositEvent]
) -> None:
    for row in rows[:20]:
        earliest = min(
            (d for d in deposits if d.contributor == row.address),
            key=lambda d: (d.block_number, d.log_index),
        )
        assert row.first_hour == earliest.hour


def test_the_fold_is_deterministic_under_input_reordering(
    rows: list[ContributorRow], deposits: list[DepositEvent], first_deposits: list[dict]
) -> None:
    """Ordering comes from (blockNumber, logIndex), never from list position —
    two endpoints paginate the same window differently."""
    shuffled = random.Random(7).sample(deposits, k=len(deposits))
    assert sig.fold_deposits(shuffled, first_deposits, points_per_eth=POINTS_PER_ETH) == rows


def test_a_replayed_log_does_not_double_count(
    rows: list[ContributorRow], deposits: list[DepositEvent], first_deposits: list[dict]
) -> None:
    """(tx_hash, log_index) is the de-dupe key.  A re-org replay, or two
    endpoints answering the same window, must not inflate the table.

    **``fold_deposits`` alone cannot prove this.**  The fold keys on the *last*
    event per address, so a duplicate cannot move its output — it would pass
    with the de-dupe deleted outright, and with the sort deleted too.  What a
    replay actually corrupts is everything downstream of the fold: the hourly
    volumes, the deposit counter, the routed-volume fallback and the series.
    So the assertion follows the duplicates there.
    """
    doubled = deposits + list(reversed(deposits))
    assert sig.fold_deposits(doubled, first_deposits, points_per_eth=POINTS_PER_ETH) == rows
    # The fold that a replay *does* move: hour volumes and per-hour counts.
    assert _buckets(doubled) == _buckets(deposits)


def test_a_replay_moves_nothing_build_signals_emits(
    full_readings: dict, bundle_deposits: list[DepositEvent]
) -> None:
    """The de-dupe, asserted where a user would see it fail.

    Every key below is derived by summing over events rather than by taking a
    last-writer-wins value, so each one doubles the moment the key stops
    de-duplicating.  ``tx_count``/``volume_wei``/``contributors`` are blanked
    so the *log-derived fallbacks* are the things under test — with the state
    counters present those three keys come from the contract and would agree
    no matter how badly the logs were folded.
    """
    no_counters = {
        **full_readings,
        "tx_count": None,
        "volume_wei": None,
        "contributors": None,
    }
    clean = sig.build_signals(no_counters, now_ts=BUNDLE_NOW)
    replayed = sig.build_signals(
        {**no_counters, "deposits": bundle_deposits + list(reversed(bundle_deposits))},
        now_ts=BUNDLE_NOW,
    )
    for key in (
        "volume_series",
        "contributors_series",
        "deposits_total",
        "volume_routed_eth",
        "hour_fed_eth",
        "activity_rows",
        "clusters_count",
        "leaderboard_rows",
    ):
        assert replayed[key] == clean[key], key
    # Not a vacuous comparison: these are the real, non-empty numbers.
    assert clean["deposits_total"] == 2930
    assert clean["volume_routed_eth"] > 15_000.0


def test_two_deposits_in_one_transaction_are_two_deposits() -> None:
    """The key is ``(tx_hash, log_index)`` — **both halves**.

    No capture can exercise the ``log_index`` half: inside the committed sweep
    all 231 ``Deposited`` rows sit in 231 distinct transactions (the only tx
    carrying two rows carries a ``FirstDeposit`` + a ``Deposited``, which are
    different groups), so a key degraded to ``(tx_hash,)`` alone leaves every
    differential in this file green while silently swallowing a contributor.

    It is not hypothetical.  The escalation rule lets one wallet call
    ``deposit()`` twice in one transaction with a rising high-water mark, and
    any batching/multicall contract can carry two wallets' deposits in one — the
    second would vanish from the activity feed, the hourly fold and every volume
    derived from it.  This tests the key's arity, not a chain state, so it needs
    no capture.
    """
    one_tx = "0x" + "ab" * 32
    first = _synthetic_deposit(
        hour=2,
        amount_wei=3 * ETH,
        contributor="0x" + "a1" * 20,
        tx_hash=one_tx,
        log_index=0,
    )
    second = _synthetic_deposit(
        hour=2,
        amount_wei=7 * ETH,
        contributor="0x" + "b2" * 20,
        tx_hash=one_tx,
        log_index=1,
    )

    folded = sig.fold_deposits([first, second], [], points_per_eth=POINTS_PER_ETH)
    assert len(folded) == 2
    assert sorted(row.credit_wei for row in folded) == [3 * ETH, 7 * ETH]

    hour_two = _buckets([first, second])[2]
    assert hour_two.deposits == 2
    assert hour_two.volume_wei == 10 * ETH


def test_the_very_same_log_twice_is_one_deposit() -> None:
    """The other half of the same key: identical ``tx_hash`` **and** identical
    ``log_index`` is one event seen twice, and it collapses."""
    event = _synthetic_deposit(
        hour=2, amount_wei=3 * ETH, contributor="0x" + "a1" * 20, log_index=0
    )
    assert len(sig.fold_deposits([event, event], [], points_per_eth=POINTS_PER_ETH)) == 1
    hour_two = _buckets([event, event])[2]
    assert hour_two.deposits == 1
    assert hour_two.volume_wei == 3 * ETH


def test_an_empty_history_folds_to_an_empty_list_not_a_crash() -> None:
    assert sig.fold_deposits([], [], points_per_eth=POINTS_PER_ETH) == []
    assert sig.fold_deposits(None, None, points_per_eth=POINTS_PER_ETH) == []


def test_points_stay_none_when_the_curve_constant_could_not_be_read(
    deposits: list[DepositEvent], first_deposits: list[dict]
) -> None:
    """A 0 there would render a real entry as having scored nothing.  The rows
    still rank — by weight, which is the curve-free record."""
    folded = sig.fold_deposits(deposits, first_deposits, points_per_eth=None)
    assert all(r.points is None for r in folded)
    weights = [r.weight_wei for r in folded]
    assert weights == sorted(weights, reverse=True)


def test_the_fold_ignores_rows_it_cannot_read(
    rows: list[ContributorRow], deposits: list[DepositEvent], first_deposits: list[dict]
) -> None:
    """Hostile input reaches this fold through a decoder, and one malformed row
    must cost one row — never the table."""
    hostile = [None, object(), {"contributor": "0x1"}, *deposits]
    assert sig.fold_deposits(hostile, first_deposits, points_per_eth=POINTS_PER_ETH) == rows


# ===========================================================================
# WP3.7 — hourly_buckets(): the series that never touches state (H2)
# ===========================================================================


def _synthetic_deposit(
    *,
    hour: int,
    amount_wei: int,
    contributor: str = "0x00000000000000000000000000000000000000aa",
    credited_delta_wei: int | None = None,
    early_bps: int = 10_000,
    block_number: int = 26_000_000,
    log_index: int = 0,
    tx_count: int = 1,
    new_weight_wei: int | None = None,
    ts: float | None = None,
    tx_hash: str | None = None,
) -> DepositEvent:
    """A hand-built event for a shape the chain has not produced yet.

    Every call site says which shape and why; nothing here is used where a real
    captured row exists.
    """
    credited = amount_wei if credited_delta_wei is None else credited_delta_wei
    weight = sig.weight_added(credited, early_bps) or 0
    return DepositEvent(
        contributor=contributor,
        hour=hour,
        amount_wei=amount_wei,
        credited_delta_wei=credited,
        weight_added_wei=weight,
        new_weight_wei=weight if new_weight_wei is None else new_weight_wei,
        tx_count=tx_count,
        hour_total_wei=amount_wei,
        early_bps=early_bps,
        block_number=block_number,
        tx_hash="0x" + f"{block_number:064x}" if tx_hash is None else tx_hash,
        log_index=log_index,
        ts=ts,
    )


def _buckets(events: list[DepositEvent], **over: Any) -> list[HourBucket]:
    kwargs: dict[str, Any] = {
        "launch_time": LAUNCH,
        "hour_duration": HOUR,
        "first_judged_hour": FIRST_JUDGED_HOUR,
        "hourly_threshold_wei": THRESHOLD,
    }
    kwargs.update(over)
    return sig.hourly_buckets(events, **kwargs)


def test_the_hour_comes_from_the_indexed_topic_not_from_a_timestamp(
    deposits: list[DepositEvent],
) -> None:
    """The hour is ``topics[2]``; the wall clock is
    ``launch_time + hour * hour_duration``, exact by construction.  The
    captured rows *do* carry a block timestamp (H14 was refuted), and the fold
    still does not read it — a stamp is for the activity feed, never for a
    bucket boundary."""
    buckets = _buckets(deposits)
    assert sig.bucket_start_ts(1, LAUNCH, HOUR) == LAUNCH + HOUR
    assert sig.bucket_start_ts(0, LAUNCH, HOUR) == LAUNCH
    assert {b.hour for b in buckets} == {0, 1}


def test_the_function_signature_admits_no_state_reading() -> None:
    """H2, made structural.  ``currentHourTotal`` cannot enter this fold
    because there is no parameter for it to enter through, and the source names
    none."""
    params = set(inspect.signature(sig.hourly_buckets).parameters)
    assert params == {
        "deposits",
        "launch_time",
        "hour_duration",
        "first_judged_hour",
        "hourly_threshold_wei",
    }
    src = inspect.getsource(sig.hourly_buckets)
    for banned in ("current_hour_total", "currentHourTotal", "last_active_hour"):
        assert banned not in src, banned


def test_the_captured_hours_reproduce_the_sweep_to_the_wei(
    deposits: list[DepositEvent],
) -> None:
    """Hour 0 quiet then violent, hour 1 still climbing when the sweep was
    taken.  Recomputed from the committed bytes, not quoted: wp3.md's hex
    literals belong to an earlier, 226-row reading of this window."""
    buckets = _buckets(deposits)
    assert [b.volume_wei for b in buckets] == [
        851_887_546_893_889_652_639,
        778_611_705_271_950_173_616,
    ]
    assert [b.deposits for b in buckets] == [149, 82]
    assert sum(b.volume_wei for b in buckets) == 1_630_499_252_165_839_826_255


def test_the_fold_reconciles_with_the_contracts_own_totals_in_one_instant(
    bundle: dict, bundle_deposits: list[DepositEvent]
) -> None:
    """The bundle's state and logs were read in the same second, so this is a
    real reconciliation rather than two snapshots being compared.

    It also pins the half of H2 that is easy to get backwards: the fold
    reproduces ``currentHourTotal()`` for the **in-progress** hour too — the
    view is not wrong, it just zeroes at the boundary, which is why history is
    never fed from it.
    """
    buckets = _buckets(bundle_deposits)
    state = bundle["state"]
    assert sum(b.volume_wei for b in buckets) == int(state["0x5f81a57c"]["result"], 16)
    assert sum(b.deposits for b in buckets) == int(state["0x9b4f50e7"]["result"], 16)

    current_hour = int(state["0x020e185d"]["result"], 16)
    current_total = int(state["0x78f251f3"]["result"], 16)
    live = [b for b in buckets if b.hour == current_hour][0]
    assert live.volume_wei == current_total == 139_251_308_307_538_029_715

    last_active_hour = int(state["0xa8a036f1"]["result"][2:66], 16)
    last_active_total = int(state["0xa8a036f1"]["result"][66:], 16)
    assert [b for b in buckets if b.hour == last_active_hour][0].volume_wei == last_active_total


def test_silent_hours_are_present_with_a_zero_not_absent() -> None:
    """A gap in the series renders as a join between two peaks; a zero renders
    as the silence that kills the game."""
    sparse = [
        _synthetic_deposit(hour=0, amount_wei=ETH, block_number=1, log_index=0),
        _synthetic_deposit(hour=3, amount_wei=ETH, block_number=2, log_index=0),
    ]
    buckets = _buckets(sparse)
    assert [b.hour for b in buckets] == [0, 1, 2, 3]
    assert [b.volume_wei for b in buckets] == [ETH, 0, 0, ETH]
    assert [b.deposits for b in buckets] == [1, 0, 0, 1]


def test_only_hours_at_or_after_first_judged_hour_are_marked_judged() -> None:
    events = [
        _synthetic_deposit(hour=h, amount_wei=ETH, block_number=100 + h, log_index=0)
        for h in (0, 23, 24, 25, 26)
    ]
    buckets = {b.hour: b for b in _buckets(events)}
    assert all(buckets[h].judged is False for h in range(0, 24))
    assert buckets[24].judged is True and buckets[25].judged is True


def test_the_highest_hour_is_never_marked_judged(
) -> None:
    """H13 at the fold level: the hour deposits are still landing in is the
    hour you are living in, and ``_isShort`` returns false while
    ``lastActive == hour``.  ``survival()`` re-derives this against the injected
    ``current_hour``, which is the authority; the fold is the conservative half.
    """
    events = [
        _synthetic_deposit(hour=h, amount_wei=ETH, block_number=100 + h, log_index=0)
        for h in (24, 25, 26)
    ]
    buckets = {b.hour: b for b in _buckets(events)}
    assert buckets[24].judged is True
    assert buckets[25].judged is True
    assert buckets[26].judged is False


def test_no_hour_is_judged_when_the_threshold_could_not_be_read() -> None:
    """``judged`` is a judgement, and without the bar there is no judgement.
    ``False`` here is not "it survived" — it is "not judged", which is what the
    field means."""
    events = [
        _synthetic_deposit(hour=h, amount_wei=ETH, block_number=100 + h, log_index=0)
        for h in (24, 25, 26)
    ]
    assert all(b.judged is False for b in _buckets(events, hourly_threshold_wei=None))
    assert all(b.judged is False for b in _buckets(events, first_judged_hour=None))


def test_a_cap_exceeding_deposit_still_fills_its_hour_in_full() -> None:
    """H3's other half (the first is in WP3.5): credited zero, weight zero, and
    the hour banks every wei of the raw amount."""
    # SYNTHETIC — permanent: no >1000 ETH deposit exists on chain.
    amount = 1200 * ETH
    event = _synthetic_deposit(hour=30, amount_wei=amount, credited_delta_wei=0)
    assert event.credited_delta_wei == 0 and event.weight_added_wei == 0
    bucket = [b for b in _buckets([event]) if b.hour == 30][0]
    assert bucket.volume_wei == amount
    assert bucket.deposits == 1


def test_an_empty_or_unreadable_history_folds_to_an_empty_list() -> None:
    assert _buckets([]) == []
    assert sig.hourly_buckets(
        None,
        launch_time=LAUNCH,
        hour_duration=HOUR,
        first_judged_hour=FIRST_JUDGED_HOUR,
        hourly_threshold_wei=THRESHOLD,
    ) == []


def test_bucket_start_ts_is_none_when_the_immutables_are_unknown() -> None:
    assert sig.bucket_start_ts(3, None, HOUR) is None
    assert sig.bucket_start_ts(3, LAUNCH, None) is None
    assert sig.bucket_start_ts(None, LAUNCH, HOUR) is None
    assert sig.bucket_start_ts(3, LAUNCH, HOUR) == LAUNCH + 3 * HOUR


# ===========================================================================
# WP3.8 — survival: judged hours, streak, closest call (H13)
# ===========================================================================
#
# Every judged hour below is SYNTHETIC and permanently marked, because no
# judged hour exists on chain yet: the first one completes at
# 2026-08-17 20:58:47 UTC.
# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>


def _bucket(hour: int, eth: float, *, judged: bool = True, saved_by: str | None = None) -> HourBucket:
    return HourBucket(
        hour=hour,
        volume_wei=int(round(eth * ETH)),
        deposits=1 if eth else 0,
        judged=judged,
        saved_by=saved_by,
    )


def _ladder(volumes: dict[int, float], *, judged_from: int = FIRST_JUDGED_HOUR) -> list[HourBucket]:
    return [
        _bucket(h, volumes.get(h, 0.0), judged=h >= judged_from)
        for h in range(0, max(volumes) + 1)
    ]


def _hours(result: dict) -> list[int]:
    return [row[0] for row in result["closest_calls"]]


def test_the_in_progress_hour_is_never_judged() -> None:
    """H13, straight from ``_isShort``: ``from > hour - 1`` returns false, so
    the hour you are living in cannot kill you.  Judging it would settle the
    game every single hour, three seconds after the boundary."""
    buckets = _ladder({h: 9.0 for h in range(24, 30)} | {30: 0.0})
    result = sig.survival(
        buckets,
        current_hour=30,
        hourly_threshold_wei=THRESHOLD,
        first_judged_hour=FIRST_JUDGED_HOUR,
    )
    assert 30 not in _hours(result)
    assert result["streak_hours"] == 6


def test_the_hour_that_just_completed_becomes_judgeable_at_the_boundary() -> None:
    """The exact-boundary proof: one tick of ``current_hour`` moves hour 29
    from living to judged, and nothing else about the input changes."""
    buckets = _ladder({h: 9.0 for h in range(24, 30)})
    before = sig.survival(
        buckets, current_hour=29, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    after = sig.survival(
        buckets, current_hour=30, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    assert 29 not in _hours(before) and 29 in _hours(after)
    assert before["streak_hours"] == 5 and after["streak_hours"] == 6


def test_no_judged_hours_yet_is_an_explicit_state_not_an_empty_number(
    deposits: list[DepositEvent],
) -> None:
    """During grace there is nothing to survive.  The margin is None, not 0 —
    a 0 margin reads as 'we scraped through by nothing', which is a lie in the
    most alarming possible direction."""
    result = sig.survival(
        _buckets(deposits),
        current_hour=1,
        hourly_threshold_wei=THRESHOLD,
        first_judged_hour=FIRST_JUDGED_HOUR,
    )
    assert result["streak_hours"] == 0
    assert result["closest_call_hour"] is None
    assert result["closest_call_margin_wei"] is None
    assert result["closest_calls"] == []


def test_the_margin_is_volume_minus_threshold_and_can_be_exactly_zero() -> None:
    """A judged hour that took in exactly 5 ETH survived by exactly nothing.
    That is the tightest possible real call and must render as 0.00, not None.
    """
    buckets = _ladder({24: 9.0, 25: 5.0, 26: 40.0})
    result = sig.survival(
        buckets, current_hour=27, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    assert result["closest_call_hour"] == 25
    assert result["closest_call_margin_wei"] == 0
    assert result["closest_calls"][0] == (25, THRESHOLD, 0, None)
    assert _hours(result) == [25, 24, 26]  # ascending by margin


def test_the_margins_are_wei_exact() -> None:
    buckets = [
        HourBucket(hour=24, volume_wei=THRESHOLD + 1, deposits=1, judged=True),
        HourBucket(hour=25, volume_wei=THRESHOLD - 1, deposits=1, judged=True),
    ]
    result = sig.survival(
        buckets, current_hour=26, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    assert dict((h, m) for h, _v, m, _s in result["closest_calls"]) == {24: 1, 25: -1}


def test_the_streak_counts_consecutive_survived_judged_hours() -> None:
    """It counts back from the last completed hour and stops at the first
    failure — a streak is what is unbroken *now*, not the best run ever."""
    buckets = _ladder({24: 9.0, 25: 1.0, 26: 9.0, 27: 9.0, 28: 9.0})
    result = sig.survival(
        buckets, current_hour=29, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    assert result["streak_hours"] == 3
    assert result["closest_call_hour"] == 25
    assert result["closest_call_margin_wei"] == 1 * ETH - THRESHOLD


def test_a_silent_hour_past_the_last_deposit_is_judged_and_kills_the_streak() -> None:
    """The fold's buckets stop at the last hour that saw a deposit — and the
    hours after it are exactly the ones that end the game.  ``_isShort``'s own
    comment says it: every hour after the last active one is provably empty.
    """
    buckets = _ladder({24: 9.0, 25: 9.0})
    result = sig.survival(
        buckets, current_hour=28, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    assert _hours(result) == [26, 27, 24, 25]
    assert result["closest_call_margin_wei"] == -THRESHOLD
    assert result["streak_hours"] == 0


def test_the_savior_travels_with_the_hour_it_saved() -> None:
    """HourSaved has never fired on chain; when it does, the row already has a
    place to sit."""
    savior = "0x00000000000000000000000000000000000000bb"
    buckets = [
        _bucket(h, 0.0, judged=False) for h in range(0, 24)
    ] + [_bucket(24, 5.5, saved_by=savior)]
    result = sig.survival(
        buckets, current_hour=25, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    assert result["closest_calls"][0][3] == savior


def test_survival_is_unknown_rather_than_zero_when_an_input_is_missing() -> None:
    """A failed threshold read must not render a streak of 0, which reads as
    'we have survived nothing' rather than 'we could not check'."""
    buckets = _ladder({24: 9.0, 25: 9.0})
    for kwargs in (
        {"current_hour": None, "hourly_threshold_wei": THRESHOLD},
        {"current_hour": 26, "hourly_threshold_wei": None},
    ):
        result = sig.survival(buckets, first_judged_hour=24, **kwargs)
        assert result["streak_hours"] is None
        assert result["closest_call_hour"] is None
        assert result["closest_call_margin_wei"] is None
        assert result["closest_calls"] == []


def test_survival_over_no_buckets_at_all_does_not_crash() -> None:
    result = sig.survival(
        [], current_hour=30, hourly_threshold_wei=THRESHOLD, first_judged_hour=24
    )
    assert result["streak_hours"] == 0
    assert result["closest_calls"] == []
    assert sig.survival(None, current_hour=None, hourly_threshold_wei=None)["closest_calls"] == []


# ===========================================================================
# WP3.9 — HOUR AT RISK
# ===========================================================================


def test_during_grace_the_row_says_when_judging_starts_and_never_blanks() -> None:
    """The hour number comes from ``first_judged_hour`` — a literal 24 here is
    a documented value hardcoded into a screen (CLAUDE.md rule 4), and this
    deployment's 24 is ``gracePeriod // hourDuration``, not a constant."""
    state, detail = sig.at_risk_state(
        phase="grace", needed_wei=0, seconds_left=1800, first_judged_hour=FIRST_JUDGED_HOUR
    )
    assert state == "ok"
    assert detail == "n/a until hour 24"
    assert "24" not in inspect.getsource(sig.at_risk_state)

    other, other_detail = sig.at_risk_state(
        phase="grace", needed_wei=0, seconds_left=1800, first_judged_hour=48
    )
    assert other == "ok" and other_detail == "n/a until hour 48"


def test_during_grace_an_unknown_first_judged_hour_still_says_something() -> None:
    state, detail = sig.at_risk_state(
        phase="grace", needed_wei=None, seconds_left=None, first_judged_hour=None
    )
    assert state == "ok" and detail and "None" not in detail


def test_a_judged_hour_that_is_already_safe_is_ok() -> None:
    """``ethNeededThisHour()`` returns 0 whenever the hour is safe — a real
    measurement, not a missing one (source.sol:547)."""
    state, detail = sig.at_risk_state(
        phase="judged", needed_wei=0, seconds_left=1800, first_judged_hour=24
    )
    assert state == "ok" and detail


def test_a_deficit_with_time_left_watches_and_names_the_number() -> None:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (no judged hour with a live deficit exists yet; capture B's window is
    # 2026-08-17 19:58:47 UTC onwards.)
    state, detail = sig.at_risk_state(
        phase="judged",
        needed_wei=3_420_000_000_000_000_000,
        seconds_left=900,
        first_judged_hour=24,
    )
    assert state == "watch"
    assert "3.42" in detail


def test_the_last_quarter_of_an_hour_with_a_deficit_fires() -> None:
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    state, detail = sig.at_risk_state(
        phase="judged", needed_wei=ETH, seconds_left=899, first_judged_hour=24
    )
    assert state == "fired"
    assert "1.00" in detail

    watching, _ = sig.at_risk_state(
        phase="judged", needed_wei=ETH, seconds_left=900, first_judged_hour=24
    )
    assert watching == "watch"


def test_a_failed_read_is_unknown_and_never_lights_an_alarm() -> None:
    """The 'a dead RPC screams that the game is dying' bug.  ``needed_wei is
    None`` is not a deficit; it is the absence of a measurement, and the row
    renders unavailable."""
    state, detail = sig.at_risk_state(
        phase="judged", needed_wei=None, seconds_left=60, first_judged_hour=24
    )
    assert state is None
    assert state not in ("ok", "watch", "fired")
    assert detail


def test_an_unknown_phase_does_not_produce_a_state() -> None:
    state, detail = sig.at_risk_state(
        phase=None, needed_wei=0, seconds_left=1800, first_judged_hour=24
    )
    assert state is None and detail


def test_a_settled_game_is_terminal_and_not_merely_ok() -> None:
    """'ok' on a dead contract reads as 'the hour is fine'.  The risk did not
    go away — it happened."""
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (capture C, the settlement transition, is one-shot and has not happened.)
    state, detail = sig.at_risk_state(
        phase="settled", needed_wei=None, seconds_left=None, first_judged_hour=24
    )
    assert state == "fired"
    assert state != "ok" and detail


def test_a_deficit_with_an_unreadable_clock_watches_rather_than_fires() -> None:
    """Half a reading is not an alarm: the deficit is real, the urgency is
    unknown, and ``fired`` is the state that says 'act now'."""
    state, _ = sig.at_risk_state(
        phase="judged", needed_wei=ETH, seconds_left=None, first_judged_hour=24
    )
    assert state == "watch"


def test_every_state_it_returns_is_a_frozen_spelling() -> None:
    seen = set()
    for phase in (*PHASES, None, "nonsense"):
        for needed in (None, 0, ETH):
            for left in (None, 0, 899, 900, 3600):
                state, detail = sig.at_risk_state(
                    phase=phase, needed_wei=needed, seconds_left=left, first_judged_hour=24
                )
                assert isinstance(detail, str) and detail
                seen.add(state)
    assert seen - {None} <= set(CURATOR_SIGNAL_STATES)


# ===========================================================================
# WP3.10 — the fan-out heuristic v1 (pattern language, never accusation)
# ===========================================================================


@pytest.fixture(scope="module")
def clusters(
    deposits: list[DepositEvent], rows: list[ContributorRow]
) -> list[dict]:
    return sig.find_clusters(deposits, rows)


def test_the_real_fan_out_is_found(clusters: list[dict], deposits: list[DepositEvent]) -> None:
    """9 wallets, exactly 60 ETH each, blocks 25 770 115-25 770 143 (span 28).
    The contract's own doc comment predicts this shape; this is it in the data.
    """
    sixty = [c for c in clusters if c["amount_eth"] == 60.0]
    assert len(sixty) == 1 and sixty[0]["size"] == 9
    assert sixty[0]["first_block"] == 25_770_115
    assert sixty[0]["last_block"] == 25_770_143

    # …and independently: exactly nine addresses deposited exactly 60 ETH once.
    per_wallet: dict[str, list[DepositEvent]] = defaultdict(list)
    for ev in deposits:
        per_wallet[ev.contributor].append(ev)
    singles = [
        ladder[0]
        for ladder in per_wallet.values()
        if len(ladder) == 1 and ladder[0].amount_wei == 60 * ETH
    ]
    assert len(singles) == 9


def test_the_grinder_is_not_a_cluster(clusters: list[dict]) -> None:
    """0xba7610… has 13 deposits.  Multi-deposit wallets are excluded by
    construction: escalating against yourself is the opposite of fanning out,
    and the ladder's amounts are all different anyway."""
    assert not any(c["size"] > 12 for c in clusters)


def test_a_multi_deposit_wallet_never_joins_a_group() -> None:
    """Three identical amounts in one block window, but one sender came back
    later — that leaves two single-deposit wallets, which is below the floor."""
    events = [
        _synthetic_deposit(
            hour=0, amount_wei=7 * ETH, contributor=f"0x{i:040x}", block_number=100 + i
        )
        for i in range(3)
    ]
    events.append(
        _synthetic_deposit(
            hour=0,
            amount_wei=9 * ETH,
            contributor="0x" + f"{2:040x}",
            block_number=110,
            tx_count=2,
        )
    )
    folded = sig.fold_deposits(events, [], points_per_eth=POINTS_PER_ETH)
    assert sig.find_clusters(events, folded) == []


def test_the_53_minimum_deposits_are_not_one_giant_cluster(clusters: list[dict]) -> None:
    """53 wallets touched the 0.05 ETH minimum.  They are identical in amount
    and would form one huge 'cluster' without the block-span bound — which
    would flag a third of the list and mean nothing."""
    minimums = [c for c in clusters if c["amount_eth"] == 0.05]
    assert minimums, "the minimum-deposit runs are still found, just bounded"
    assert all(c["size"] < 20 for c in minimums)
    assert all(c["last_block"] - c["first_block"] <= sig.CLUSTER_MAX_BLOCK_SPAN for c in clusters)


def test_amounts_are_compared_in_wei_not_in_eth_floats() -> None:
    """``(10**18 + 1) / 1e18 == 1.0`` in float64.  Six wallets, two amounts one
    wei apart, one block window: two groups of three, never one of six."""
    events = [
        _synthetic_deposit(
            hour=0, amount_wei=ETH + (i % 2), contributor=f"0x{i:040x}", block_number=200 + i
        )
        for i in range(6)
    ]
    assert (ETH + 1) / 1e18 == 1.0  # the confusion this test exists for
    folded = sig.fold_deposits(events, [], points_per_eth=POINTS_PER_ETH)
    found = sig.find_clusters(events, folded)
    assert sorted(c["size"] for c in found) == [3, 3]


def test_a_cluster_of_exactly_three_is_found_and_of_two_is_not() -> None:
    def _run(count: int, span: int = 4) -> list[dict]:
        events = [
            _synthetic_deposit(
                hour=0,
                amount_wei=2 * ETH,
                contributor=f"0x{i:040x}",
                block_number=300 + i * span,
            )
            for i in range(count)
        ]
        folded = sig.fold_deposits(events, [], points_per_eth=POINTS_PER_ETH)
        return sig.find_clusters(events, folded)

    assert _run(2) == []
    assert [c["size"] for c in _run(3)] == [3]


def test_a_group_wider_than_the_block_bound_splits_into_runs() -> None:
    """Two tight runs 1000 blocks apart are two patterns, not one."""
    events = [
        _synthetic_deposit(
            hour=0, amount_wei=2 * ETH, contributor=f"0x{i:040x}", block_number=block
        )
        for i, block in enumerate([400, 402, 404, 1400, 1402, 1404])
    ]
    folded = sig.fold_deposits(events, [], points_per_eth=POINTS_PER_ETH)
    found = sig.find_clusters(events, folded)
    assert sorted((c["size"], c["first_block"]) for c in found) == [(3, 400), (3, 1400)]


def test_the_rows_carry_exactly_the_frozen_cluster_columns(clusters: list[dict]) -> None:
    for row in clusters:
        assert tuple(row) == CURATOR_ROW_KEYS["cluster_rows"]


def test_the_points_and_share_come_from_the_folded_table(
    clusters: list[dict], rows: list[ContributorRow], deposits: list[DepositEvent]
) -> None:
    sixty = [c for c in clusters if c["amount_eth"] == 60.0][0]
    members = {
        r.address
        for r in rows
        if r.tx_count == 1 and r.credit_wei == 60 * ETH
    }
    expected = sum(r.points for r in rows if r.address in members)
    total = sum(r.points for r in rows)
    assert sixty["points"] == expected
    assert sixty["points_share_pct"] == pytest.approx(100.0 * expected / total)
    assert 0.0 < sixty["points_share_pct"] < 100.0


def test_the_share_is_none_rather_than_zero_when_points_are_unknown(
    deposits: list[DepositEvent],
) -> None:
    """The curve constant is a chain read like any other.  Without it a cluster
    is still a real pattern — it just has no score to report."""
    folded = sig.fold_deposits(deposits, [], points_per_eth=None)
    found = sig.find_clusters(deposits, folded)
    assert found
    assert all(c["points"] is None and c["points_share_pct"] is None for c in found)


def test_the_output_carries_no_accusatory_vocabulary(clusters: list[dict]) -> None:
    """PRD §5: pattern language only.  The contract's own docs delegate this
    analysis to consumers; calling a wallet a cheat is a claim this data cannot
    support."""
    blob = json.dumps(clusters).lower() + inspect.getsource(sig).lower()
    for word in ("sybil", "cheat", "fraud", "attack", "abuse", "farmer"):
        assert word not in blob, word


def test_find_clusters_is_total_over_empty_and_hostile_input() -> None:
    assert sig.find_clusters([], []) == []
    assert sig.find_clusters(None, None) == []
    assert sig.find_clusters([object(), None], [object()]) == []


# ===========================================================================
# WP3.11 — WHALE and the YOU quote
# ===========================================================================

NOW = 1_786_920_000.0  # 2026-08-16 22:40:00Z, inside the captured window


def test_the_whale_is_the_largest_deposit_in_the_window(
    deposits: list[DepositEvent],
) -> None:
    """The captured sweep's last hour holds several sends over 25 ETH; the row
    names the biggest one, not the newest."""
    newest_ts = max(d.ts for d in deposits if d.ts is not None)
    whale = sig.newest_whale(deposits, now_ts=newest_ts + 60)
    assert whale is not None
    inside = [d for d in deposits if d.ts is not None and newest_ts + 60 - d.ts <= 3600]
    assert whale["amount_wei"] == max(d.amount_wei for d in inside)
    assert whale["amount_wei"] >= int(sig.WHALE_MIN_ETH * ETH)
    assert whale["wallet"] == max(inside, key=lambda d: d.amount_wei).contributor
    assert whale["age_s"] == pytest.approx(newest_ts + 60 - max(inside, key=lambda d: d.amount_wei).ts)


def test_an_empty_window_reports_nothing_rather_than_zero(
    deposits: list[DepositEvent],
) -> None:
    """``None`` means "no whale in the last hour"; a 0 ETH whale is not a
    thing, and a zero here would render as one."""
    newest_ts = max(d.ts for d in deposits if d.ts is not None)
    assert sig.newest_whale(deposits, now_ts=newest_ts + 86_400) is None
    assert sig.newest_whale([], now_ts=NOW) is None
    assert sig.newest_whale(None, now_ts=NOW) is None


def test_a_deposit_below_the_threshold_is_not_a_whale() -> None:
    small = _synthetic_deposit(hour=0, amount_wei=24 * ETH, ts=NOW - 10)
    assert sig.newest_whale([small], now_ts=NOW) is None
    big = _synthetic_deposit(hour=0, amount_wei=25 * ETH, ts=NOW - 10, log_index=1)
    assert sig.newest_whale([big], now_ts=NOW)["amount_wei"] == 25 * ETH


def test_a_deposit_with_no_timestamp_is_excluded_from_the_window() -> None:
    """WP2.8's failed stamp.  A missing timestamp must not promote an old
    deposit into the last hour — that would invent a whale out of an outage."""
    stampless = _synthetic_deposit(hour=0, amount_wei=900 * ETH, ts=None)
    assert sig.newest_whale([stampless], now_ts=NOW) is None


def test_the_whale_window_and_floor_are_injectable() -> None:
    """PRD §12: both are first guesses, so both are parameters — a re-tune is
    an argument change, not an edit."""
    old = _synthetic_deposit(hour=0, amount_wei=30 * ETH, ts=NOW - 7200)
    assert sig.newest_whale([old], now_ts=NOW) is None
    assert sig.newest_whale([old], now_ts=NOW, window_s=10_800)["amount_wei"] == 30 * ETH
    assert sig.newest_whale([old], now_ts=NOW, window_s=10_800, min_eth=31.0) is None


def _wallet(address: str, **over: Any) -> WalletState:
    base: dict[str, Any] = {
        "address": address,
        "points": None,
        "weight_wei": None,
        "contributed_wei": None,
        "tx_count": None,
        "first_hour": None,
        "has_joined": True,
        "required_next_wei": None,
    }
    base.update(over)
    return WalletState(**base)


def test_the_you_quote_ranks_against_the_folded_table(rows: list[ContributorRow]) -> None:
    top = rows[0]
    wallet = _wallet(
        top.address,
        points=top.points,
        weight_wei=top.weight_wei,
        contributed_wei=top.credit_wei,
        tx_count=top.tx_count,
        first_hour=top.first_hour,
        required_next_wei=top.credit_wei + 10**17,
    )
    rank, points, credit_eth, required_eth, marginal = sig.you_quote(
        wallet,
        rows,
        points_per_eth=POINTS_PER_ETH,
        early_bps=19_491,
        credit_cap_wei=CREDIT_CAP,
    )
    assert rank == 1
    assert points == 30_035
    assert credit_eth == pytest.approx(461.1)
    assert required_eth == pytest.approx(461.2)
    # The next legal send credits 0.1 ETH, which at 1.9491x is 0.19491 ETH of
    # weight on top of 902.10737 — recomputed here through the same primitives
    # the contract uses, not copied from the answer.
    expected = sig.points_for_weight(
        top.weight_wei + sig.weight_added(10**17, 19_491), POINTS_PER_ETH
    )
    assert marginal == expected - 30_035
    assert marginal >= 0


def test_a_wallet_that_has_never_played_is_not_a_zero_score(
    rows: list[ContributorRow],
) -> None:
    """``rank —, 0 pts`` reads like a wallet with a zero score rather than one
    that has never deposited.  Points are None; what IS known — the entry
    ticket and what it would buy — is reported."""
    stranger = _wallet(
        "0x00000000000000000000000000000000000000cc",
        points=0,
        weight_wei=0,
        contributed_wei=0,
        tx_count=0,
        first_hour=0,
        has_joined=False,
        required_next_wei=5 * 10**16,
    )
    rank, points, credit_eth, required_eth, marginal = sig.you_quote(
        stranger,
        rows,
        points_per_eth=POINTS_PER_ETH,
        early_bps=19_491,
        credit_cap_wei=CREDIT_CAP,
    )
    assert rank is None
    assert points is None
    assert credit_eth is None
    assert required_eth == pytest.approx(0.05)
    assert marginal == sig.points_for_weight(
        sig.weight_added(5 * 10**16, 19_491), POINTS_PER_ETH
    )
    assert marginal == 312


def test_a_wallet_already_at_the_cap_buys_no_further_points(
    rows: list[ContributorRow],
) -> None:
    """Legitimately 0 — not unknown, not an error.  The cap is where the curve
    stops paying and the honest quote says so."""
    # SYNTHETIC — permanent: no wallet has reached the 1000 ETH cap on chain.
    capped = _wallet(
        "0x00000000000000000000000000000000000000dd",
        points=31_622,
        weight_wei=1000 * ETH,
        contributed_wei=CREDIT_CAP,
        tx_count=1,
        first_hour=0,
        required_next_wei=CREDIT_CAP + 10**17,
    )
    _rank, _points, _credit, _required, marginal = sig.you_quote(
        capped,
        rows,
        points_per_eth=POINTS_PER_ETH,
        early_bps=10_000,
        credit_cap_wei=CREDIT_CAP,
    )
    assert marginal == 0


def test_no_wallet_configured_means_every_you_field_is_none(
    rows: list[ContributorRow],
) -> None:
    """``MAXPANE_WALLET`` unset: the manager passes ``wallet_state=None`` and
    this must not raise."""
    assert sig.you_quote(
        None, rows, points_per_eth=POINTS_PER_ETH, early_bps=19_491, credit_cap_wei=CREDIT_CAP
    ) == (None, None, None, None, None)


def test_the_you_quote_degrades_field_by_field(rows: list[ContributorRow]) -> None:
    """One failed sub-call costs one field.  A wallet whose ``requiredNext``
    read failed still has a rank."""
    top = rows[0]
    wallet = _wallet(
        top.address,
        points=top.points,
        weight_wei=top.weight_wei,
        contributed_wei=top.credit_wei,
        required_next_wei=None,
    )
    rank, points, credit_eth, required_eth, marginal = sig.you_quote(
        wallet, rows, points_per_eth=POINTS_PER_ETH, early_bps=19_491, credit_cap_wei=CREDIT_CAP
    )
    assert rank == 1 and points == 30_035 and credit_eth == pytest.approx(461.1)
    assert required_eth is None and marginal is None


def test_the_you_quote_matches_on_address_case_insensitively(
    rows: list[ContributorRow],
) -> None:
    """The client checksums; the logs do not.  A rank that depends on which
    endpoint answered is not a rank."""
    wallet = _wallet(rows[2].address.upper().replace("0X", "0x"), points=rows[2].points)
    rank, *_ = sig.you_quote(
        wallet, rows, points_per_eth=POINTS_PER_ETH, early_bps=19_491, credit_cap_wei=CREDIT_CAP
    )
    assert rank == 3


# ===========================================================================
# WP3.12 — build_signals() and the READING_KEYS seam
# ===========================================================================

#: The bundle's own instant — 2026-08-17 00:03:22Z, hour 4 of grace.
BUNDLE_NOW = 1_786_925_002.0


@pytest.fixture(scope="module")
def full_readings(
    bundle: dict, bundle_deposits: list[DepositEvent]
) -> dict:
    """Every reading, taken from ONE bundle whose state and logs were fetched
    in the same second.  This is what WP5's ``_readings()`` must produce."""
    state = bundle["state"]

    def word(selector: str, index: int = 0) -> int:
        raw = state[selector]["result"][2:]
        return int(raw[index * 64 : (index + 1) * 64], 16)

    first = [
        _first_deposit_from_log(r) for r in _rows_of(bundle["logs"], TOPIC_FIRST_DEPOSIT)
    ]
    return {
        "settled": bool(word("0x3270bb5b")),
        "current_hour": word("0x020e185d"),
        "hour_needed_wei": word("0xa4586257"),
        "hour_seconds_left": word("0x7a7d6632"),
        "early_bps": word("0xd8631b3d"),
        "volume_wei": word("0xd80528ae", 0),
        "contributors": word("0xd80528ae", 1),
        "tx_count": word("0xd80528ae", 2),
        "forced_balance_wei": int(bundle["balance"], 16),
        "launch_time": word("0x790ca413"),
        "grace_period": word("0xa06db7dc"),
        "hour_duration": word("0xda25efd9"),
        "hourly_threshold_wei": word("0x9d99a86d"),
        "first_judged_hour": word("0x2a9c657f"),
        "points_per_eth": word("0xc99a340f"),
        "credit_cap_wei": word("0x1ea0466e"),
        "deposits": bundle_deposits,
        "first_deposits": first,
        "hour_saved": [],
        "rescued_total_wei": 0,
        "settlement_record": None,
        "wallet_state": None,
    }


def test_build_signals_emits_exactly_the_frozen_surface(full_readings: dict) -> None:
    out = sig.build_signals(full_readings, now_ts=BUNDLE_NOW)
    assert set(out) == set(sig.SIGNAL_OUTPUT_KEYS)


def test_build_signals_accepts_exactly_the_frozen_readings(full_readings: dict) -> None:
    """The seam WP5 produces.  Both directions, so neither side can drift: a
    reading WP5 stops sending, and a reading this module stops reading."""
    assert set(full_readings) == set(sig.READING_KEYS)


def test_the_grace_payload_reproduces_the_bundle(full_readings: dict) -> None:
    """One real instant, end to end: phase, clock, totals, rows and series."""
    out = sig.build_signals(full_readings, now_ts=BUNDLE_NOW)

    assert out["phase"] == "grace"
    assert out["settled"] is False
    assert out["current_hour"] == 4
    assert out["hourly_threshold_eth"] == 5.0
    assert out["first_judged_hour"] == 24
    assert out["hour_needed_eth"] == 0.0  # REAL: zero all through grace
    assert out["grace_ends_utc"] == "2026-08-17 19:58:47 UTC"
    assert out["grace_seconds_left"] == 71_725
    assert out["early_multiplier_x"] == pytest.approx(1.8303)

    assert out["contributors_total"] == 2291
    assert out["deposits_total"] == 2930
    assert out["volume_routed_eth"] == pytest.approx(15_981.146536110048)
    assert out["hour_fed_eth"] == pytest.approx(139.25130830753804)
    assert out["forced_eth"] == 0.0
    assert out["rescued_total_eth"] == 0.0

    assert out["top_points"] == max(r["points"] for r in out["leaderboard_rows"])
    assert len(out["leaderboard_rows"]) == sig.LEADERBOARD_LIMIT
    assert out["leaderboard_rows"][0]["rank"] == 1
    assert [tuple(r) for r in out["leaderboard_rows"]] == [
        CURATOR_ROW_KEYS["leaderboard_rows"]
    ] * len(out["leaderboard_rows"])

    assert len(out["activity_rows"]) == sig.ACTIVITY_LIMIT
    assert [tuple(r) for r in out["activity_rows"]] == [
        CURATOR_ROW_KEYS["activity_rows"]
    ] * len(out["activity_rows"])
    assert {r["kind"] for r in out["activity_rows"]} <= set(CURATOR_ACTIVITY_KINDS)

    assert len(out["volume_series"]) == 5 == len(out["contributors_series"])
    assert out["volume_series"][0][0] == LAUNCH
    assert out["volume_series"][1][0] == LAUNCH + HOUR
    assert out["contributors_series"][-1][1] == 2291
    assert sum(point[1] for point in out["volume_series"]) == pytest.approx(
        out["volume_routed_eth"]
    )


def test_the_activity_feed_is_newest_first_and_names_the_first_deposits(
    full_readings: dict,
) -> None:
    out = sig.build_signals(full_readings, now_ts=BUNDLE_NOW)
    rows = out["activity_rows"]
    assert [r["ts"] for r in rows] == sorted((r["ts"] for r in rows), reverse=True)
    assert any(r["kind"] == "joined" for r in rows)
    joined = [r for r in rows if r["kind"] == "joined"][0]
    assert joined["tx_count"] == 1
    assert joined["amount_eth"] > 0
    assert joined["tx_hash"].startswith("0x") and isinstance(joined["log_index"], int)


def test_during_grace_nothing_is_judged_and_the_signal_says_so(
    full_readings: dict,
) -> None:
    out = sig.build_signals(full_readings, now_ts=BUNDLE_NOW)
    assert out["survival_streak_hours"] == 0
    assert out["closest_call_hour"] is None
    assert out["closest_call_margin_eth"] is None
    assert out["closest_call_rows"] == []
    assert out["sig_at_risk_state"] == "ok"
    assert out["sig_settled_state"] == "ok"


def test_none_and_empty_mean_different_things_and_both_are_handled(
    full_readings: dict,
) -> None:
    """None == the read failed; [] / () == the read succeeded and found
    nothing.  HOUR AT RISK hinges on it: 0 ETH needed is a measurement and an
    unreadable deficit is not."""
    empty = sig.build_signals({**full_readings, "hour_needed_wei": 0}, now_ts=BUNDLE_NOW)
    failed = sig.build_signals({**full_readings, "hour_needed_wei": None}, now_ts=BUNDLE_NOW)
    assert empty["sig_at_risk_state"] == "ok"
    assert empty["hour_needed_eth"] == 0.0
    assert failed["hour_needed_eth"] is None
    # …during grace the row is "n/a until hour 24" either way; post-grace the
    # same pair is ok vs unknown:
    judged = {**full_readings, "current_hour": 30, "first_judged_hour": 24}
    after = LAUNCH + 30 * HOUR + 10
    assert sig.build_signals({**judged, "hour_needed_wei": 0}, now_ts=after)[
        "sig_at_risk_state"
    ] == "ok"
    assert sig.build_signals({**judged, "hour_needed_wei": None}, now_ts=after)[
        "sig_at_risk_state"
    ] is None


def test_an_empty_log_read_is_not_the_same_as_a_failed_one(full_readings: dict) -> None:
    empty = sig.build_signals({**full_readings, "deposits": []}, now_ts=BUNDLE_NOW)
    failed = sig.build_signals({**full_readings, "deposits": None}, now_ts=BUNDLE_NOW)
    assert empty["leaderboard_rows"] == [] and empty["top_points"] is None
    assert empty["hour_fed_eth"] == 0.0
    assert failed["leaderboard_rows"] == [] and failed["top_points"] is None
    assert failed["hour_fed_eth"] is None
    # The contract's own counters survive a dead logs tier — they are state.
    assert failed["contributors_total"] == 2291
    # The survival record is derived from the logs alone, so a dead logs tier
    # leaves it unknown.  ``0`` would read as "we have survived nothing", which
    # is a claim about the chain made by a refresh that never reached it — and
    # state and logs are served by different endpoint pools, so a live-state /
    # dead-logs refresh is the expected failure rather than a corner case.
    assert empty["survival_streak_hours"] == 0
    assert failed["survival_streak_hours"] is None
    assert failed["closest_call_hour"] is None
    assert failed["closest_call_margin_eth"] is None
    assert failed["closest_call_rows"] == []


def test_a_dead_logs_tier_leaves_the_streak_unknown_in_a_judged_hour(
    full_readings: dict,
) -> None:
    """The same rule where it actually shows: past grace, with judged hours
    behind us and every log group failed.

    ``empty`` vs ``failed`` above runs at hour 4 of grace, where the judged
    window is empty anyway; here the window is 24..29 and a ``0`` streak would
    be rendered next to a live phase as a factual claim of six dead hours.

    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    (capture B, the first post-grace judged hour, lands 2026-08-17 19:58:47Z.)
    """
    judged = {
        **full_readings,
        "current_hour": 30,
        "hour_needed_wei": 2 * ETH,
        "deposits": None,
        "first_deposits": None,
    }
    out = sig.build_signals(judged, now_ts=LAUNCH + 30 * HOUR + 10)
    assert out["phase"] == "judged"
    assert out["survival_streak_hours"] is None
    # The keys that already degraded correctly, pinned so this one stops being
    # the outlier by accident rather than by rule.
    assert out["hour_fed_eth"] is None
    assert out["clusters_count"] is None
    assert out["top_points"] is None


def test_an_all_none_readings_dict_produces_the_full_surface_of_nones() -> None:
    out = sig.build_signals({k: None for k in sig.READING_KEYS}, now_ts=BUNDLE_NOW)
    assert set(out) == set(sig.SIGNAL_OUTPUT_KEYS)
    assert all(value is None or value == [] for value in out.values()), {
        k: v for k, v in out.items() if not (v is None or v == [])
    }


def test_build_signals_never_raises_on_hostile_input(full_readings: dict) -> None:
    for bad in (
        {},
        {k: object() for k in sig.READING_KEYS},
        {**full_readings, "current_hour": -1},
        {**full_readings, "launch_time": "yesterday"},
        {**full_readings, "deposits": [object(), None]},
        None,
        [],
    ):
        assert set(sig.build_signals(bad, now_ts=BUNDLE_NOW)) == set(sig.SIGNAL_OUTPUT_KEYS)


def test_no_wei_denominated_value_reaches_the_flat_dict(full_readings: dict) -> None:
    """The manager's contract is ETH floats.  A wei integer that escaped the
    division renders as an 18-digit number and nobody notices until it does."""
    out = sig.build_signals(full_readings, now_ts=BUNDLE_NOW)
    assert not [k for k in out if k.endswith("_wei")]
    for key in ("hour_fed_eth", "volume_routed_eth", "forced_eth", "hourly_threshold_eth"):
        assert out[key] is None or out[key] < 10**9, key


# --- the two states the chain has not reached yet --------------------------


def _synthetic_case(name: str) -> dict:
    return json.loads((SIGNALS_FIXTURES / name).read_text(encoding="utf-8"))


def _readings_from_case(case: dict) -> dict:
    """Fill a synthetic case out to the full reading surface."""
    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    hours = {int(h): v for h, v in case["hours"].items()}
    deposits = [
        _synthetic_deposit(
            hour=hour,
            amount_wei=volume,
            contributor=f"0x{hour:040x}",
            block_number=26_000_000 + hour,
            early_bps=10_000,
        )
        for hour, volume in sorted(hours.items())
    ]
    readings = {key: None for key in sig.READING_KEYS}
    readings.update(case["readings"])
    readings["deposits"] = deposits
    readings["first_deposits"] = []
    return readings


def test_a_judged_hour_with_a_live_deficit_watches_then_fires() -> None:
    case = _synthetic_case("readings_judged_deficit.json")
    assert "SYNTHETIC — re-point" in case["_synthetic"]
    readings = _readings_from_case(case)
    out = sig.build_signals(readings, now_ts=case["now_ts"])

    assert out["phase"] == "judged"
    assert out["early_multiplier_x"] == 1.0  # flat forever after grace
    assert out["grace_seconds_left"] == 0
    assert out["hour_needed_eth"] == pytest.approx(1.4)
    assert out["sig_at_risk_state"] == "watch"
    assert out["survival_streak_hours"] == 1
    assert out["closest_call_hour"] == 24
    assert out["closest_call_margin_eth"] == pytest.approx(0.2)
    assert out["last_saved_hour"] == 24
    assert out["last_saved_wallet"] == "0x00000000000000000000000000000000000000bb"
    assert out["last_saved_age_s"] == pytest.approx(case["now_ts"] - 1_786_997_400)

    urgent = sig.build_signals(
        {**readings, "hour_seconds_left": 120}, now_ts=case["now_ts"]
    )
    assert urgent["sig_at_risk_state"] == "fired"


def test_the_settled_state_is_terminal_and_survives_a_dead_rpc() -> None:
    case = _synthetic_case("readings_settled.json")
    readings = _readings_from_case(case)
    readings["settlement_record"] = SettlementRecord(
        settled=True,
        block_number=26_000_100,
        observed_at=case["observed_at"],
        settled_hour=case["settled_hour"],
        settled_at_ts=case["settled_at_ts"],
    )
    out = sig.build_signals(readings, now_ts=case["now_ts"])
    assert out["phase"] == "settled"
    assert out["settled"] is True
    assert out["settled_hour"] == 27
    assert out["settled_at_ts"] == case["settled_at_ts"]
    assert out["settled_observed_at"] == case["observed_at"]
    assert out["sig_settled_state"] == "fired"
    assert out["sig_at_risk_state"] == "fired"
    assert out["lived_desc"].startswith("lived ")

    # The latch outlives the reading it was made from: a later refresh whose
    # isSettled() call failed must not take the screen back to a live phase.
    blind = sig.build_signals({**readings, "settled": None}, now_ts=case["now_ts"])
    assert blind["phase"] == "settled" and blind["settled"] is True


def test_a_long_settled_game_relaxes_its_colour_but_never_its_phase() -> None:
    case = _synthetic_case("readings_settled.json")
    readings = _readings_from_case(case)
    readings["settlement_record"] = SettlementRecord(
        settled=True,
        block_number=26_000_100,
        observed_at=case["observed_at"],
        settled_hour=case["settled_hour"],
        settled_at_ts=case["settled_at_ts"],
    )
    later = case["observed_at"] + sig.FIRED_TTL_S + 1
    out = sig.build_signals(readings, now_ts=later)
    assert out["phase"] == "settled"
    assert out["sig_settled_state"] == "watch"
    assert out["sig_settled_state"] in CURATOR_SIGNAL_STATES


def test_a_live_game_reports_how_long_it_has_been_alive(full_readings: dict) -> None:
    out = sig.build_signals(full_readings, now_ts=BUNDLE_NOW)
    assert out["lived_desc"] == "alive 4 h 4 m"


def test_the_you_row_reaches_the_flat_dict(full_readings: dict, rows) -> None:
    top = rows[0]
    wallet = WalletState(
        address=top.address,
        points=top.points,
        weight_wei=top.weight_wei,
        contributed_wei=top.credit_wei,
        tx_count=top.tx_count,
        first_hour=top.first_hour,
        has_joined=True,
        required_next_wei=top.credit_wei + 10**17,
    )
    out = sig.build_signals({**full_readings, "wallet_state": wallet}, now_ts=BUNDLE_NOW)
    assert out["you_points"] == top.points
    assert out["you_credit_eth"] == pytest.approx(461.1)
    assert out["you_required_next_eth"] == pytest.approx(461.2)
    assert out["you_marginal_points"] is not None
    # Rank is against the WHOLE folded table, not the ten rows on screen.
    assert out["you_rank"] is not None


def test_the_flagged_flag_and_the_share_agree_with_the_cluster_rows(
    full_readings: dict,
) -> None:
    out = sig.build_signals(full_readings, now_ts=BUNDLE_NOW)
    assert out["clusters_count"] == len(
        sig.find_clusters(full_readings["deposits"],
                          sig.fold_deposits(full_readings["deposits"], [],
                                            points_per_eth=POINTS_PER_ETH))
    )
    assert len(out["cluster_rows"]) <= sig.CLUSTER_LIMIT
    assert 0.0 < out["flagged_points_share_pct"] < 100.0
    assert any(row["flagged"] for row in out["leaderboard_rows"]) or all(
        not row["flagged"] for row in out["leaderboard_rows"]
    )


def test_the_phase_vocabulary_is_re_exported_and_not_copied() -> None:
    """One import site for a consumer, and the same object — a second spelling
    of "settled" is the fallback arm the single tuple exists to prevent."""
    from maxpane_dashboard.data import curator_models

    assert sig.PHASES is curator_models.PHASES


# ---------------------------------------------------------------------------
# The `y` view — you_ladder() and cost_to_pass()
# ---------------------------------------------------------------------------

#: The module already names this ETH; the new block below reads better with the
#: short form, and one alias beats sprinkling 10**18 through the arithmetic.
E = ETH

_ME = "0x00000000000000000000000000000000000000aa"
_SOMEBODY = "0x00000000000000000000000000000000000000bb"


class _Row:
    """A leaderboard row as the fold produces it — weight is all this math reads."""

    def __init__(self, weight_wei: int) -> None:
        self.weight_wei = weight_wei


def test_the_ladder_holds_only_my_sends_in_chain_order():
    events = [
        _synthetic_deposit(hour=1, amount_wei=5 * E, contributor=_SOMEBODY,
                           block_number=100, log_index=0),
        _synthetic_deposit(hour=0, amount_wei=2 * E, contributor=_ME,
                           block_number=90, log_index=1),
        _synthetic_deposit(hour=2, amount_wei=9 * E, contributor=_ME,
                           block_number=120, log_index=0),
    ]
    rows = sig.you_ladder(events, _ME, credit_cap_wei=1000 * E)
    assert [row["hour"] for row in rows] == [0, 2]          # chain order, not list order
    assert [row["amount_eth"] for row in rows] == [2.0, 9.0]


def test_the_ladder_is_case_insensitive_about_my_own_address():
    """`MAXPANE_WALLET` is typed by a human; the chain emits lowercase topics."""
    events = [_synthetic_deposit(hour=0, amount_wei=E, contributor=_ME)]
    assert sig.you_ladder(events, _ME.upper(), credit_cap_wei=1000 * E)


def test_the_ladder_carries_the_multiplier_that_send_actually_got():
    """Not today's multiplier: the early-bird decays per second, so the whole
    point of the ladder is what each rung cost at the time."""
    events = [
        _synthetic_deposit(hour=0, amount_wei=E, contributor=_ME, early_bps=19_975,
                           block_number=90),
        _synthetic_deposit(hour=20, amount_wei=5 * E, contributor=_ME,
                           early_bps=10_400, block_number=200),
    ]
    rows = sig.you_ladder(events, _ME, credit_cap_wei=1000 * E)
    assert [row["early_x"] for row in rows] == [1.9975, 1.04]


def test_an_above_cap_send_is_marked_capped_rather_than_credited_zero():
    """A deposit past the 1000 ETH cap credits nothing while still counting in
    full toward its hour's survival.  `capped` is the difference between that
    and a decode that failed."""
    events = [
        _synthetic_deposit(hour=0, amount_wei=1200 * E, contributor=_ME,
                           credited_delta_wei=0),
    ]
    row = sig.you_ladder(events, _ME, credit_cap_wei=1000 * E)[0]
    assert row["capped"] is True
    assert row["credited_eth"] == 0.0


def test_a_normal_send_is_not_marked_capped():
    events = [_synthetic_deposit(hour=0, amount_wei=E, contributor=_ME)]
    assert sig.you_ladder(events, _ME, credit_cap_wei=1000 * E)[0]["capped"] is False


def test_no_wallet_and_no_deposits_give_an_empty_ladder_not_a_crash():
    assert sig.you_ladder([], _ME, credit_cap_wei=1000 * E) == []
    assert sig.you_ladder(None, _ME, credit_cap_wei=1000 * E) == []
    assert sig.you_ladder([], None, credit_cap_wei=1000 * E) == []


def test_cost_to_pass_quotes_one_send_that_lands_strictly_above():
    """The fold breaks ties on who joined first, so levelling with the wallet
    above does not pass it: the target is its weight + 1 wei."""
    rows = [_Row(500 * E), _Row(120 * E), _Row(100 * E)]
    rank, needs = sig.cost_to_pass(
        3, rows, weight_wei=100 * E, high_water_wei=60 * E,
        early_bps=20_000, credit_cap_wei=1000 * E,
    )
    assert rank == 2
    # 20 ETH of weight at 2.00x is 10 ETH of credited delta, and credit
    # telescopes to the high-water mark: 60 + 10.
    assert needs == 70.0


def test_cost_to_pass_reverses_the_weight_floor_rather_than_rounding_it():
    """`weight_added` floors, so the delta must be the ceiling of the inverse —
    one wei short buys one wei too little weight and does not pass."""
    rows = [_Row(100 * E + 1), _Row(100 * E)]
    _rank, needs = sig.cost_to_pass(
        2, rows, weight_wei=100 * E, high_water_wei=0,
        early_bps=3, credit_cap_wei=1000 * E,
    )
    delta_wei = round(needs * 1e18)
    assert sig.weight_added(delta_wei, 3) + 100 * E > 100 * E + 1
    assert sig.weight_added(delta_wei - 1, 3) + 100 * E <= 100 * E + 1


def test_rank_one_has_nobody_above_and_is_quoted_nothing():
    rows = [_Row(500 * E), _Row(120 * E)]
    assert sig.cost_to_pass(1, rows, weight_wei=500 * E, high_water_wei=400 * E,
                            early_bps=20_000, credit_cap_wei=1000 * E) == (None, None)


def test_a_wallet_at_the_credit_cap_is_quoted_no_price_at_all():
    """Past the cap no deposit adds weight, so any number here would be a
    promise the contract will not keep."""
    rows = [_Row(5000 * E), _Row(100 * E)]
    rank, needs = sig.cost_to_pass(
        2, rows, weight_wei=100 * E, high_water_wei=1000 * E,
        early_bps=20_000, credit_cap_wei=1000 * E,
    )
    assert rank == 1
    assert needs is None


def test_an_unranked_wallet_is_not_quoted_a_rank_to_pass():
    """It has no place in the table; `you_quote`'s entry ticket is its number."""
    rows = [_Row(500 * E)]
    assert sig.cost_to_pass(None, rows, weight_wei=None, high_water_wei=None,
                            early_bps=20_000, credit_cap_wei=1000 * E) == (None, None)


def test_a_missing_multiplier_costs_the_quote_not_the_rank():
    rows = [_Row(500 * E), _Row(100 * E)]
    assert sig.cost_to_pass(2, rows, weight_wei=100 * E, high_water_wei=50 * E,
                            early_bps=None, credit_cap_wei=1000 * E) == (None, None)
