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
    endpoints answering the same window, must not inflate the table."""
    doubled = deposits + list(reversed(deposits))
    assert sig.fold_deposits(doubled, first_deposits, points_per_eth=POINTS_PER_ETH) == rows


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
        tx_hash="0x" + f"{block_number:064x}"[:64],
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
