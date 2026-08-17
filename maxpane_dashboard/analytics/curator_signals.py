"""Pure math for the curator dashboard — THE LIST.

Everything derived on that screen is computed here: the phase machine, the
curve, the folds over the ``Deposited`` history, the survival record, the
fan-out heuristic and the YOU quote.  No I/O, no widgets, no clock of its own —
``now_ts`` is a parameter of every function that needs one, which is what makes
a replay of the 2026-08-16 captures reproducible forever.

Unit discipline
    **Wei stays an ``int`` through every fold.**  The division to ETH happens
    exactly once, at the presentation boundary, and that boundary is
    :func:`build_signals` — the function whose output keys are the flat dict's.
    Nothing downstream of it divides again, and nothing upstream of it divides
    at all.  A helper that returns wei says ``_wei`` in its name; a flat-dict
    key that carries ETH says ``_eth``.

The three legitimate zeros
    ``creditedDelta == 0`` (a deposit above the credit cap), ``ethNeededThisHour
    () == 0`` (all through grace, and again whenever a judged hour is already
    safe) and ``currentHourTotal() == 0`` (every hour boundary, until the next
    deposit lands) are all real measurements.  ``None`` is the only failed read.
    Every function here is total over that distinction: no division by a
    credited delta, no ``max()`` over a possibly-empty sequence without a
    default, and no state that treats a ``None`` as a number.

    In particular a ``None`` never lights an alarm.  ``HOUR AT RISK`` with an
    unknown deficit renders unavailable, not ``watch`` — a dead RPC must not
    scream that the game is dying.

Pattern language, never accusation
    :func:`find_clusters` reports a *shape* in the data: single-deposit wallets,
    byte-identical amounts, a tight block window.  The contract's own comments
    delegate that analysis to consumers, and the data cannot support a claim
    about intent.  The output vocabulary is deliberately limited to the shape.

The tunables (PRD §12) are the named constants at the top of this module and
every one of them is a **first guess**, to be re-tuned against post-grace data
and recorded as an amendment.  A magic number inline cannot be re-tuned; it
just gets edited.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from maxpane_dashboard.data.curator_models import (
    CURATOR_ACTIVITY_KINDS,
    PHASES,
    ContributorRow,
    HourBucket,
)

# ---------------------------------------------------------------------------
# Tunables — PRD §12.  Every one of these is a FIRST GUESS.
# ---------------------------------------------------------------------------

#: A single deposit at or above this many ETH is a WHALE.  **First guess**: it
#: is roughly 5x the hourly survival threshold as this contract was configured,
#: which is the scale at which one send visibly changes the hour.  Re-tune
#: against post-grace data and record it as a PRD amendment.
WHALE_MIN_ETH = 25.0

#: How far back the WHALE row looks (PRD §4: "largest single deposit last 60
#: min").  **First guess**, and deliberately equal to one hour bucket so the row
#: and the hero clock talk about the same window.
WHALE_WINDOW_S = 3600.0

#: A fan-out needs at least this many single-deposit wallets.  **First guess**
#: from PRD §5; two identical amounts is a coincidence anyone can produce.
CLUSTER_MIN_SIZE = 3

#: …landing inside this many blocks.  **First guess** — about six minutes of
#: mainnet.  Without the bound, the 53 wallets sitting at the minimum deposit
#: would form one meaningless "cluster" spanning the whole game.
CLUSTER_MAX_BLOCK_SPAN = 32

#: HOUR AT RISK goes from ``watch`` to ``fired`` with fewer than this many
#: seconds left in a short judged hour.  **First guess**: a quarter of an hour
#: is about the point at which a rescue has to be already in flight.
AT_RISK_RED_SECONDS = 900

#: How long a ``fired`` row keeps its fired framing before relaxing (surf's
#: precedent, same value).  Only the SETTLED row uses it: settlement is
#: terminal, so the *phase* never relaxes, but the rail's colour does — a game
#: that died three days ago is not news.  **First guess.**
FIRED_TTL_S = 86_400.0

#: Row budgets.  The widgets truncate further; these bound what crosses the
#: manager boundary at all, so a long game cannot grow the payload without
#: bound.
LEADERBOARD_LIMIT = 10
ACTIVITY_LIMIT = 40
CLOSEST_CALL_LIMIT = 10
CLUSTER_LIMIT = 10

#: The three signal spellings, mirrored from ``CURATOR_SIGNAL_STATES``.  A
#: fourth anywhere is a silent fallback arm; ``None`` (unknown) is not a
#: spelling, it is the absence of one.
STATE_OK = "ok"
STATE_WATCH = "watch"
STATE_FIRED = "fired"

_BPS = 10_000
_WEI = 10**18
#: ``sqrt(1e18) == 1e9`` — the curve's fixed-point scale, from ``_curve``.
_SQRT_SCALE = 10**9


# ---------------------------------------------------------------------------
# The two seams
# ---------------------------------------------------------------------------

#: Everything :func:`build_signals` reads, and the only thing it reads.
#:
#: **Outage encoding, uniform across every entry:** ``None`` means *the read
#: failed*; ``[]`` / ``()`` means *the read succeeded and found nothing*; ``0``
#: is a measurement.  The two are never interchangeable here — an empty judged
#: history means "nothing has been judged yet" and a ``None`` means "we could
#: not look", and the screen says different things about each.
#:
#: A missing key is treated exactly like ``None``, so a caller that has not
#: implemented a tier yet degrades one row instead of raising.
READING_KEYS: tuple[str, ...] = (
    # --- fast tier (one batched eth_call) ---------------------------------
    "settled",                # bool | None — isSettled(); None is "unknown"
    "current_hour",           # int | None — currentHour()
    "hour_needed_wei",        # int | None — ethNeededThisHour(); 0 is REAL
    "hour_seconds_left",      # int | None — timeLeftInHour(); never 0
    "early_bps",              # int | None — earlyMultiplierBps()
    "volume_wei",             # int | None — stats() word 0
    "contributors",           # int | None — stats() word 1
    "tx_count",               # int | None — stats() word 2
    "forced_balance_wei",     # int | None — eth_getBalance(CURATOR)
    # --- once tier (immutables, read live, never hardcoded) ---------------
    "launch_time",            # int | None
    "grace_period",           # int | None
    "hour_duration",          # int | None
    "hourly_threshold_wei",   # int | None
    "first_judged_hour",      # int | None
    "points_per_eth",         # int | None
    "credit_cap_wei",         # int | None
    # --- logs tier ---------------------------------------------------------
    "deposits",               # list[DepositEvent] | None — [] is a read that found none
    "first_deposits",         # list[dict] | None — {"contributor", "index", "ts"}
    "hour_saved",             # list[dict] | None — {"hour", "wallet", "ts"}
    "rescued_total_wei",      # int | None — summed Rescued events; 0 is REAL
    # --- manager-held records ---------------------------------------------
    "settlement_record",      # SettlementRecord | None — the latch, not a read
    "wallet_state",           # WalletState | None — None when no wallet is set
)

#: The three flat-dict keys :func:`build_signals` does **not** produce.  They
#: are the manager's own health markers: which groups degraded, and when the
#: payload was assembled.  Nothing here can know either.
MANAGER_OWNED_KEYS: tuple[str, ...] = ("degraded", "as_of_hhmm", "as_of")

#: Exactly the keys :func:`build_signals` emits — always all of them.
#:
#: Hand-typed rather than derived from ``CURATOR_KEYS`` on purpose (CLAUDE.md's
#: redundancy rule): a derivation would make WP0's subset guard compare a
#: constant against itself, and it could never fail again.
SIGNAL_OUTPUT_KEYS: tuple[str, ...] = (
    "phase",
    "settled",
    "settled_hour",
    "settled_at_ts",
    "settled_observed_at",
    "lived_desc",
    "current_hour",
    "hour_fed_eth",
    "hour_needed_eth",
    "hour_seconds_left",
    "grace_seconds_left",
    "grace_ends_utc",
    "hourly_threshold_eth",
    "first_judged_hour",
    "early_multiplier_x",
    "points_per_eth_now",
    "survival_streak_hours",
    "closest_call_margin_eth",
    "closest_call_hour",
    "contributors_total",
    "deposits_total",
    "volume_routed_eth",
    "top_points",
    "last_saved_hour",
    "last_saved_wallet",
    "last_saved_age_s",
    "whale_amount_eth",
    "whale_wallet",
    "whale_age_s",
    "clusters_count",
    "flagged_points_share_pct",
    "forced_eth",
    "rescued_total_eth",
    "sig_settled_state",
    "sig_at_risk_state",
    "you_rank",
    "you_points",
    "you_credit_eth",
    "you_required_next_eth",
    "you_marginal_points",
    "leaderboard_rows",
    "activity_rows",
    "closest_call_rows",
    "cluster_rows",
    "volume_series",
    "contributors_series",
)


# ---------------------------------------------------------------------------
# Coercion — every entry point is total over hostile input
# ---------------------------------------------------------------------------


def _int_or_none(value: Any) -> int | None:
    """An ``int`` if the value is one, else ``None``.

    ``bool`` is rejected on purpose: ``True`` is not the hour 1, and a ``False``
    that slipped into a numeric field is a decode bug, not a zero.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _num_or_none(value: Any) -> float | None:
    """A finite number as ``float``, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _eth(wei: Any) -> float | None:
    """The one division in the whole dashboard: wei -> ETH, at the boundary."""
    amount = _int_or_none(wei)
    if amount is None:
        return None
    return amount / _WEI


# ---------------------------------------------------------------------------
# The phase machine and the clock fields
# ---------------------------------------------------------------------------


def derive_phase(
    *,
    now_ts: float | None,
    launch_time: int | None,
    grace_period: int | None,
    settled: bool | None,
    current_hour: int | None,
) -> str | None:
    """One of :data:`PHASES`, or ``None`` when it cannot be known.

    Three rules, in this order:

    1. **Settled wins over everything.**  The predicate the contract enforces is
       one-way (deposits revert ``AlreadySettled`` once any judged hour fails),
       so no clock value and no later reading may take the screen back to a live
       phase.  It answers ``"settled"`` even with every other input missing.
    2. **Unknown is ``None``, never a guess.**  ``settled is None`` means the
       read failed; deriving ``"judged"`` from the clock would render a live
       game on a contract that may already be dead.
    3. Otherwise the grace boundary decides, and **the boundary itself belongs
       to ``judged``** — ``earlyMultiplierBps()`` goes flat at exactly
       ``launchTime + gracePeriod`` and ``firstJudgedHour`` is that same
       instant's hour.

    ``current_hour`` is not a second clock; it carries the one fact the elapsed
    seconds cannot: ``_isShort`` opens with ``if (hour == 0) return false``, so
    hour 0 is never judged whatever the configuration says.
    """
    if settled is True:
        return "settled"
    if settled is not False:
        return None

    now = _num_or_none(now_ts)
    launch = _int_or_none(launch_time)
    grace = _int_or_none(grace_period)
    if now is None or launch is None or grace is None:
        return None

    if _int_or_none(current_hour) == 0:
        return "grace"
    return "judged" if now - launch >= grace else "grace"


def grace_seconds_left(
    *, now_ts: float | None, launch_time: int | None, grace_period: int | None
) -> int | None:
    """Seconds until judging begins — ``0`` once grace is over, never negative.

    ``0`` here is a measurement ("grace is finished"); ``None`` is "we could not
    read the clock".  The hero renders those two very differently.
    """
    now = _num_or_none(now_ts)
    launch = _int_or_none(launch_time)
    grace = _int_or_none(grace_period)
    if now is None or launch is None or grace is None:
        return None
    return max(0, int(launch + grace - now))


def grace_ends_utc(launch_time: int | None, grace_period: int | None) -> str | None:
    """The absolute instant grace ends, as the hero prints it.

    A countdown alone is unreadable at a glance and unquotable in a screenshot;
    the absolute instant is what a reader can act on.
    """
    launch = _int_or_none(launch_time)
    grace = _int_or_none(grace_period)
    if launch is None or grace is None:
        return None
    stamp = datetime.fromtimestamp(launch + grace, tz=timezone.utc)
    return stamp.strftime("%Y-%m-%d %H:%M:%S UTC")


def lived_desc(
    launch_time: int | None, end_ts: float | None, *, settled: bool = False
) -> str | None:
    """``"lived 3 h 12 m"`` for a finished game, ``"alive 4 h"`` for a live one.

    ``None`` when either end of the interval is unknown, or when the interval
    runs backwards: a duration nobody could measure is not a duration of zero.
    """
    launch = _int_or_none(launch_time)
    end = _num_or_none(end_ts)
    if launch is None or end is None:
        return None
    seconds = int(end - launch)
    if seconds < 0:
        return None

    days, rest = divmod(seconds, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes = rest // 60

    if days:
        parts = [f"{days} d"] + ([f"{hours} h"] if hours else [])
    elif hours:
        parts = [f"{hours} h"] + ([f"{minutes} m"] if minutes else [])
    else:
        parts = [f"{minutes} m"]
    return ("lived " if settled else "alive ") + " ".join(parts)


# ---------------------------------------------------------------------------
# The curve (H7)
# ---------------------------------------------------------------------------


def points_for_weight(weight_wei: int | None, points_per_eth: int | None) -> int | None:
    """The contract's ``_curve``: ``(sqrt(weight) * POINTS_PER_ETH) / 1e9``.

    Integer throughout, and **the multiplication happens before the division**.
    The other order collapses every weight under one ETH to zero, which is a
    third of the captured list — the wallets sitting at the minimum deposit.

    ``math.isqrt`` is exact; the contract's own bit-seeded Newton loop is
    transcribed in the test suite and differentially compared against it over
    the whole reachable range.  A float ``sqrt`` is not a substitute: 53 bits of
    mantissa cannot hold a weight in wei.

    ``points_per_eth`` is a parameter because it is a contract constant read on
    the ``once`` tier — never a literal here (CLAUDE.md rule 4).
    """
    weight = _int_or_none(weight_wei)
    rate = _int_or_none(points_per_eth)
    if weight is None or rate is None or weight < 0 or rate < 0:
        return None
    return math.isqrt(weight) * rate // _SQRT_SCALE


# ---------------------------------------------------------------------------
# The weight formula (H8)
# ---------------------------------------------------------------------------


def weight_added(credited_delta_wei: int | None, early_bps: int | None) -> int | None:
    """``_credit``'s last line: ``(creditedDelta * earlyBps) / BPS``, floored.

    Wei-exact and integer-only.  The identity holds for every captured
    ``Deposited`` row — the witness is deposit #1, 0.05 ETH at 19 975 bps
    producing 0.099875 ETH of weight — and a ``round`` here would disagree with
    the chain on most of them.

    ``0`` in, ``0`` out, and that is a legitimate answer rather than a failure:
    a deposit whose new high-water mark is already above the credit cap credits
    nothing and still counts in full toward the hour's survival.
    """
    delta = _int_or_none(credited_delta_wei)
    bps = _int_or_none(early_bps)
    if delta is None or bps is None or delta < 0 or bps < 0:
        return None
    return delta * bps // _BPS


def credited_delta(
    amount_wei: int | None, old_high_water_wei: int | None, credit_cap_wei: int | None
) -> int | None:
    """``_credit``'s cap arithmetic: ``min(amount, cap) - min(old, cap)``, ≥ 0.

    The ``min`` is on **both** ends, which is what makes the ladder telescope:
    a wallet's lifetime credit is ``min(final high-water, cap)`` however many
    escalations it took to get there, and ``amount`` *is* the new high-water by
    construction.

    Three answers are zero and none of them is a failure: a wallet already at
    the cap, a re-send below the existing mark (which the contract rejects, but
    an out-of-order log must not turn into a negative), and a first deposit of
    nothing.  Nothing anywhere may divide by this value.
    """
    amount = _int_or_none(amount_wei)
    old = _int_or_none(old_high_water_wei)
    cap = _int_or_none(credit_cap_wei)
    if amount is None or old is None or cap is None:
        return None
    if amount < 0 or old < 0 or cap < 0:
        return None
    capped_new = min(amount, cap)
    capped_old = min(old, cap)
    return capped_new - capped_old if capped_new > capped_old else 0


# ---------------------------------------------------------------------------
# Folds over the event history
# ---------------------------------------------------------------------------

#: The fields the folds read off a decoded ``Deposited`` event.  Read through
#: ``getattr`` so a row that is missing one costs its own row and not the fold:
#: hostile input reaches these functions through a decoder, and one malformed
#: log must never empty the leaderboard.
_DEPOSIT_FIELDS = (
    "contributor",
    "hour",
    "amount_wei",
    "credited_delta_wei",
    "weight_added_wei",
    "new_weight_wei",
    "tx_count",
    "block_number",
    "log_index",
)


def _usable_deposits(deposits: Any) -> list[Any]:
    """Every event that carries a readable identity, ordered as the chain saw
    them and de-duplicated on ``(tx_hash, log_index)``.

    Chain order is ``(block_number, log_index)`` and never list position: two
    endpoints paginate the same window differently, and a fold that depends on
    arrival order is a fold that disagrees with itself between refreshes.
    """
    if not isinstance(deposits, (list, tuple)):
        return []

    seen: set[tuple[Any, Any]] = set()
    usable: list[Any] = []
    for event in deposits:
        values = {name: getattr(event, name, None) for name in _DEPOSIT_FIELDS}
        if not isinstance(values["contributor"], str):
            continue
        if any(
            _int_or_none(values[name]) is None
            for name in ("hour", "amount_wei", "new_weight_wei", "tx_count",
                         "block_number", "log_index")
        ):
            continue
        key = (getattr(event, "tx_hash", None), values["log_index"])
        if key in seen:
            continue
        seen.add(key)
        usable.append(event)

    usable.sort(key=lambda e: (e.block_number, e.log_index))
    return usable


def _first_index_map(first_deposits: Any) -> dict[str, int]:
    """``FirstDeposit``'s 1-based index, keyed by lowercase address.

    Accepts the mapping shape the client emits (``contributor``/``index``) and
    tolerates ``address``/``first_index`` spellings, because this seam is
    written by a different work package in a different wave.
    """
    out: dict[str, int] = {}
    if not isinstance(first_deposits, (list, tuple)):
        return out
    for row in first_deposits:
        if isinstance(row, dict):
            address = row.get("contributor") or row.get("address")
            index = _int_or_none(row.get("index") if "index" in row else row.get("first_index"))
        else:
            address = getattr(row, "contributor", None) or getattr(row, "address", None)
            index = _int_or_none(
                getattr(row, "index", None)
                if hasattr(row, "index")
                else getattr(row, "first_index", None)
            )
        if isinstance(address, str) and index is not None:
            out[address.lower()] = index
    return out


def fold_deposits(
    deposits: Any,
    first_deposits: Any,
    *,
    points_per_eth: int | None,
) -> list[ContributorRow]:
    """The contributor table, folded from the events' own running totals.

    ``Deposited`` carries ``newWeight`` and ``txCount`` — the contract's
    accumulators, not ours.  Re-deriving them by summing ``weightAdded`` would
    drift silently the moment one log is missed, and a missed log is exactly
    what the gap-repair tier exists for; taking the last event's running total
    is self-healing instead.

    ``credit_wei`` is the final high-water mark (``amount`` *is* the new
    high-water), which is the credited net contribution and **not** the gross
    the address routed.  Points stay ``None`` when ``points_per_eth`` could not
    be read: a ``0`` there would render a real entry as having scored nothing.

    Sorted by points, then weight, then the first-deposit index — total and
    deterministic, so two refreshes of the same history render the same table.
    """
    events = _usable_deposits(deposits)
    indices = _first_index_map(first_deposits)

    latest: dict[str, Any] = {}
    first_hours: dict[str, int] = {}
    for event in events:
        key = event.contributor.lower()
        latest[key] = event
        first_hours.setdefault(key, event.hour)

    rows: list[ContributorRow] = []
    for key, event in latest.items():
        weight = event.new_weight_wei
        rows.append(
            ContributorRow(
                address=event.contributor,
                weight_wei=weight,
                credit_wei=event.amount_wei,
                tx_count=event.tx_count,
                first_hour=first_hours.get(key),
                first_index=indices.get(key),
                points=points_for_weight(weight, points_per_eth),
            )
        )

    rows.sort(
        key=lambda r: (
            -(r.points if r.points is not None else 0),
            -r.weight_wei,
            r.first_index if r.first_index is not None else 1 << 62,
            r.address.lower(),
        )
    )
    return rows


def bucket_start_ts(
    hour: int | None, launch_time: int | None, hour_duration: int | None
) -> int | None:
    """An hour bucket's wall clock: ``launch_time + hour * hour_duration``.

    Exact by construction, which is the whole reason the series needs no block
    timestamps: the hour is an indexed topic on the event itself.
    """
    index = _int_or_none(hour)
    launch = _int_or_none(launch_time)
    duration = _int_or_none(hour_duration)
    if index is None or launch is None or duration is None or index < 0:
        return None
    return launch + index * duration


def hourly_buckets(
    deposits: Any,
    *,
    launch_time: int | None,
    hour_duration: int | None,
    first_judged_hour: int | None,
    hourly_threshold_wei: int | None,
) -> list[HourBucket]:
    """The hourly history, folded from ``Deposited`` logs and nothing else.

    **There is no parameter through which a state read could enter** (H2), and
    that is deliberate: the fast tier's hour-total view returns 0 at every hour
    boundary while its companion still names the previous bucket, so a series
    fed from that tier writes a crash into the history which outlives the
    boundary that produced it.  The hour comes off the event's indexed second
    topic instead.

    The series is **dense**: a silent hour is present with ``volume_wei=0``.  A
    missing hour and a silent hour are different facts, and a silent judged hour
    is the fact that ends the game.

    ``judged`` is conservative here — it is false for every hour before
    ``first_judged_hour``, false for the highest hour observed (the one deposits
    are still landing in; ``_isShort`` returns false while the live hour is the
    active one), and false throughout when the threshold or the first judged
    hour could not be read, because "judged" is a judgement and without the bar
    there is none.  :func:`survival` re-derives it against the
    injected ``current_hour``, which is the authority.
    """
    events = _usable_deposits(deposits)
    if not events:
        return []

    volumes: dict[int, int] = {}
    counts: dict[int, int] = {}
    for event in events:
        hour = event.hour
        if hour < 0:
            continue
        volumes[hour] = volumes.get(hour, 0) + event.amount_wei
        counts[hour] = counts.get(hour, 0) + 1
    if not volumes:
        return []

    highest = max(volumes)
    judging_from = _int_or_none(first_judged_hour)
    threshold = _int_or_none(hourly_threshold_wei)
    can_judge = judging_from is not None and threshold is not None

    return [
        HourBucket(
            hour=hour,
            volume_wei=volumes.get(hour, 0),
            deposits=counts.get(hour, 0),
            judged=bool(can_judge and hour >= judging_from and hour < highest),
        )
        for hour in range(0, highest + 1)
    ]


# ---------------------------------------------------------------------------
# Survival: judged hours, the streak, the closest call (H13)
# ---------------------------------------------------------------------------


def survival(
    buckets: Any,
    *,
    current_hour: int | None,
    hourly_threshold_wei: int | None,
    first_judged_hour: int | None = None,
) -> dict:
    """The survival record over the **completed, judged** hours.

    Returns ``streak_hours``, ``closest_call_hour``, ``closest_call_margin_wei``
    and ``closest_calls`` — the last a list of
    ``(hour, volume_wei, margin_wei, savior)`` ascending by margin, ties broken
    by hour so two identical margins never swap places between refreshes.

    **The in-progress hour is never judged** (H13).  ``_isShort`` returns false
    while the live hour is the active one, so judging it would end the game
    three seconds after every boundary.  The judged window is
    ``[first_judged_hour, current_hour - 1]``.

    **Silence inside that window counts.**  The fold's buckets stop at the last
    hour that saw a deposit, and the hours after it are precisely the ones that
    kill the contract — ``_isShort``'s own comment says every hour past the last
    active one is provably empty.  So a judged hour with no bucket is folded in
    at zero, but only *past a known history*: with no buckets at all there is no
    evidence of where the history ends, and inventing fatal hours out of an
    empty read is the opposite of honest.

    ``first_judged_hour`` is optional only because the fold already stamped
    ``judged`` on each bucket; pass it whenever it is known — it is the one
    input that says where judging starts when the buckets are silent there.

    Unknown inputs give ``None``, never ``0``: a failed threshold read must not
    render "we have survived nothing".
    """
    empty: dict[str, Any] = {
        "streak_hours": None,
        "closest_call_hour": None,
        "closest_call_margin_wei": None,
        "closest_calls": [],
    }

    hour_now = _int_or_none(current_hour)
    threshold = _int_or_none(hourly_threshold_wei)
    if hour_now is None or threshold is None:
        return empty

    rows = [b for b in (buckets or []) if _int_or_none(getattr(b, "hour", None)) is not None]
    volumes = {b.hour: _int_or_none(getattr(b, "volume_wei", None)) or 0 for b in rows}
    saviors = {b.hour: getattr(b, "saved_by", None) for b in rows}

    start = _int_or_none(first_judged_hour)
    if start is None:
        judged_hours = [b.hour for b in rows if getattr(b, "judged", False)]
        start = min(judged_hours) if judged_hours else None
    if start is None or not rows:
        return {**empty, "streak_hours": 0}

    window = [h for h in range(start, hour_now) if h >= 0]
    if not window:
        return {**empty, "streak_hours": 0}

    calls = [
        (hour, volumes.get(hour, 0), volumes.get(hour, 0) - threshold, saviors.get(hour))
        for hour in window
    ]

    streak = 0
    for _hour, _volume, margin, _savior in reversed(calls):
        if margin < 0:
            break
        streak += 1

    ranked = sorted(calls, key=lambda row: (row[2], row[0]))
    return {
        "streak_hours": streak,
        "closest_call_hour": ranked[0][0],
        "closest_call_margin_wei": ranked[0][2],
        "closest_calls": ranked,
    }


# ---------------------------------------------------------------------------
# HOUR AT RISK
# ---------------------------------------------------------------------------


def _eth_words(wei: int) -> str:
    """A deficit as the rail prints it — two decimals, never a bare zero."""
    amount = wei / _WEI
    if 0 < amount < 0.01:
        return "<0.01 ETH"
    return f"{amount:.2f} ETH"


def at_risk_state(
    *,
    phase: str | None,
    needed_wei: int | None,
    seconds_left: int | None,
    first_judged_hour: int | None,
) -> tuple[str | None, str]:
    """``(state, detail)`` for the HOUR AT RISK row.

    ``state`` is one of the three frozen spellings or ``None``, and **``None``
    never lights an alarm**: an unreadable ``ethNeededThisHour()`` is the
    absence of a measurement, not a deficit.  Rendering it as ``watch`` is the
    "a dead RPC screams that the game is dying" bug, and it is the single most
    likely false alarm this dashboard could produce.

    The detail is always a non-empty string, so the row never renders blank —
    during grace it says when judging starts, and the hour number comes from
    ``first_judged_hour`` rather than from the number this deployment happens to
    have (``gracePeriod // hourDuration``, and neither operand is a constant).

    A deficit with an unreadable clock is ``watch``, not ``fired``: the deficit
    is real but the urgency is unknown, and ``fired`` is the state that means
    "act now".
    """
    if phase == "settled":
        # Terminal, and deliberately not "ok": the risk did not go away, it
        # happened.  An hour came up short and that is what closed the list.
        return STATE_FIRED, "an hour came up short — the list is closed"

    if phase == "grace":
        hour = _int_or_none(first_judged_hour)
        if hour is None:
            return STATE_OK, "n/a until judging begins"
        return STATE_OK, f"n/a until hour {hour}"

    if phase != "judged":
        return None, "phase unavailable"

    needed = _int_or_none(needed_wei)
    if needed is None:
        return None, "hourly deficit unavailable"
    if needed <= 0:
        return STATE_OK, "hour is safe"

    left = _int_or_none(seconds_left)
    detail = f"hour needs {_eth_words(needed)}"
    if left is None:
        return STATE_WATCH, detail
    if left < AT_RISK_RED_SECONDS:
        minutes, seconds = divmod(max(0, left), 60)
        return STATE_FIRED, f"{detail} · {minutes:02d}:{seconds:02d} left"
    return STATE_WATCH, detail


__all__ = [
    # tunables
    "WHALE_MIN_ETH",
    "WHALE_WINDOW_S",
    "CLUSTER_MIN_SIZE",
    "CLUSTER_MAX_BLOCK_SPAN",
    "AT_RISK_RED_SECONDS",
    "FIRED_TTL_S",
    "LEADERBOARD_LIMIT",
    "ACTIVITY_LIMIT",
    "CLOSEST_CALL_LIMIT",
    "CLUSTER_LIMIT",
    # states
    "STATE_OK",
    "STATE_WATCH",
    "STATE_FIRED",
    # seams
    "READING_KEYS",
    "SIGNAL_OUTPUT_KEYS",
    "MANAGER_OWNED_KEYS",
    # phase machine and clock
    "derive_phase",
    "grace_seconds_left",
    "grace_ends_utc",
    "lived_desc",
    # curve
    "points_for_weight",
    "weight_added",
    "credited_delta",
    # folds
    "fold_deposits",
    "hourly_buckets",
    "bucket_start_ts",
    "survival",
    "at_risk_state",
]
