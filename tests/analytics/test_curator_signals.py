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
