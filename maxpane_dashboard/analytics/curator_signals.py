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
    "you_weight_eth",
    "you_tx_count",
    "you_first_hour",
    "you_joined_utc",
    "you_weight_share_pct",
    "you_ladder_rows",
    "you_next_rank",
    "you_next_rank_needs_eth",
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


# ---------------------------------------------------------------------------
# The fan-out heuristic v1
# ---------------------------------------------------------------------------


def find_clusters(
    deposits: Any,
    contributors: Any,
    *,
    min_size: int = CLUSTER_MIN_SIZE,
    max_block_span: int = CLUSTER_MAX_BLOCK_SPAN,
) -> list[dict]:
    """Groups of single-deposit wallets sending byte-identical amounts close
    together — a **shape in the data**, reported as such.

    The rule (PRD §5, all three parts a first guess): at least
    ``min_size`` wallets whose *only* deposit is the same amount **to the wei**,
    landing inside ``max_block_span`` blocks.  Wallets that deposited more than
    once are excluded by construction: escalating against your own record is the
    opposite of fanning out.

    Amounts group on the **integer**.  Two sends one wei apart are equal as ETH
    floats and are not equal on chain, and the whole point of the rule is that
    the amounts match exactly.

    The block bound is what keeps the rule meaningful: the wallets sitting at
    the minimum deposit are identical in amount by definition, and without a
    window they would form one group spanning the entire game.

    ``points`` and ``points_share_pct`` are ``None`` — never ``0`` — when the
    folded table has no score to report.  The pattern is still real; it just has
    no number attached.
    """
    events = _usable_deposits(deposits)
    if not events:
        return []

    rows = [
        row
        for row in (contributors or [])
        if isinstance(getattr(row, "address", None), str)
        and _int_or_none(getattr(row, "tx_count", None)) is not None
    ]
    by_address = {row.address.lower(): row for row in rows}
    total_points = sum(
        row.points for row in rows if _int_or_none(getattr(row, "points", None)) is not None
    )

    found: list[dict] = []
    for amount, run in _cluster_runs(events, min_size, max_block_span):
        found.extend(_cluster_rows(run, amount, by_address, total_points))

    found.sort(
        key=lambda row: (
            -(row["points"] or 0),
            -row["size"],
            -row["last_block"],
        )
    )
    return found


def _cluster_runs(
    events: list[Any], min_size: int, max_block_span: int
) -> list[tuple[int, list[Any]]]:
    """``(amount_wei, members)`` for every maximal run that clears the rule.

    The one place the rule is implemented.  :func:`find_clusters` turns these
    into rows and :func:`cluster_members` turns them into a set of addresses;
    two copies of the grouping would be two rules that drift apart, and the
    leaderboard's ``flagged`` column and the cluster table would then disagree
    on screen about the same wallets.
    """
    ladders: dict[str, int] = {}
    for event in events:
        key = event.contributor.lower()
        ladders[key] = ladders.get(key, 0) + 1

    groups: dict[int, list[Any]] = {}
    for event in events:
        if ladders.get(event.contributor.lower()) != 1:
            continue
        groups.setdefault(event.amount_wei, []).append(event)

    runs: list[tuple[int, list[Any]]] = []
    for amount, members in groups.items():
        if len(members) < min_size:
            continue
        members.sort(key=lambda e: e.block_number)
        run: list[Any] = []
        for event in members:
            if run and event.block_number - run[0].block_number > max_block_span:
                if len(run) >= min_size:
                    runs.append((amount, run))
                run = []
            run.append(event)
        if len(run) >= min_size:
            runs.append((amount, run))
    return runs


def cluster_members(
    deposits: Any,
    *,
    min_size: int = CLUSTER_MIN_SIZE,
    max_block_span: int = CLUSTER_MAX_BLOCK_SPAN,
) -> set[str]:
    """The lowercase addresses that sit inside some fan-out run.

    This is what the leaderboard's ``flagged`` column reads, and it comes off
    the same grouping the cluster table does — see :func:`_cluster_runs`.
    """
    return {
        event.contributor.lower()
        for _amount, run in _cluster_runs(_usable_deposits(deposits), min_size, max_block_span)
        for event in run
    }


def _cluster_rows(
    run: list[Any],
    amount_wei: int,
    by_address: dict[str, Any],
    total_points: int,
) -> list[dict]:
    """One row for one maximal run."""
    scores = [
        _int_or_none(getattr(by_address.get(event.contributor.lower()), "points", None))
        for event in run
    ]
    points = None if any(score is None for score in scores) else sum(scores)
    share = None
    if points is not None and total_points > 0:
        share = 100.0 * points / total_points

    return [
        {
            "size": len(run),
            "amount_eth": _eth(amount_wei),
            "first_block": run[0].block_number,
            "last_block": run[-1].block_number,
            "points": points,
            "points_share_pct": share,
        }
    ]


# ---------------------------------------------------------------------------
# WHALE and the YOU quote
# ---------------------------------------------------------------------------


def newest_whale(
    deposits: Any,
    *,
    now_ts: float | None,
    min_eth: float = WHALE_MIN_ETH,
    window_s: float = WHALE_WINDOW_S,
) -> dict | None:
    """The largest single deposit of at least ``min_eth`` in the last
    ``window_s`` seconds, or ``None`` when there was none.

    ``None`` is "no whale in the window" — never a zero, which would render as a
    whale of nothing.

    **A deposit whose timestamp could not be read is excluded**, not treated as
    now.  Admitting it would let an outage promote an old send into the last
    hour and invent an event that did not happen.

    Both bounds are parameters because both are first guesses (PRD §12): a
    re-tune is an argument, not an edit.
    """
    now = _num_or_none(now_ts)
    window = _num_or_none(window_s)
    floor_eth = _num_or_none(min_eth)
    if now is None or window is None or floor_eth is None:
        return None

    floor_wei = int(floor_eth * _WEI)
    candidates = []
    for event in _usable_deposits(deposits):
        stamp = _num_or_none(getattr(event, "ts", None))
        if stamp is None or not 0 <= now - stamp <= window:
            continue
        if event.amount_wei < floor_wei:
            continue
        candidates.append(event)

    if not candidates:
        return None

    best = max(candidates, key=lambda e: (e.amount_wei, e.block_number, e.log_index))
    return {
        "amount_wei": best.amount_wei,
        "wallet": best.contributor,
        "age_s": max(0.0, now - float(best.ts)),
        "block_number": best.block_number,
        "tx_hash": getattr(best, "tx_hash", None),
    }


def you_quote(
    wallet_state: Any,
    rows: Any,
    *,
    points_per_eth: int | None,
    early_bps: int | None,
    credit_cap_wei: int | None,
) -> tuple[int | None, int | None, float | None, float | None, int | None]:
    """``(rank, points, credit_eth, required_next_eth, marginal_points)``.

    **A wallet that has never deposited is not a wallet with a score of zero.**
    Its rank and points are ``None`` and the widget renders "not on the list
    yet"; what *is* known — the entry ticket and the points it would buy — is
    still reported, because that is the one number a reader in that position
    wants.

    ``marginal_points`` is what the next **legal** send buys: the escalation
    minimum run through the same three primitives the contract uses
    (``credited_delta`` -> ``weight_added`` -> the curve), on top of the weight
    already banked.  For a wallet at the credit cap it is legitimately ``0``.

    Every field degrades on its own: a failed ``requiredNext`` read costs the
    quote, not the rank.
    """
    blank: tuple[None, None, None, None, None] = (None, None, None, None, None)
    if wallet_state is None:
        return blank

    address = getattr(wallet_state, "address", None)
    if not isinstance(address, str):
        return blank
    key = address.lower()

    table = [
        row
        for row in (rows or [])
        if isinstance(getattr(row, "address", None), str)
    ]
    rank = None
    for index, row in enumerate(table, start=1):
        if row.address.lower() == key:
            rank = index
            break

    joined = getattr(wallet_state, "has_joined", None)
    weight = _int_or_none(getattr(wallet_state, "weight_wei", None))
    high_water = _int_or_none(getattr(wallet_state, "contributed_wei", None))
    required_next = _int_or_none(getattr(wallet_state, "required_next_wei", None))

    chain_points = _int_or_none(getattr(wallet_state, "points", None))
    points = chain_points if chain_points is not None else points_for_weight(weight, points_per_eth)

    if joined is False:
        # A stranger: the chain answers 0 to every wallet view, and a 0 here
        # would render as a played-and-scored-nothing row.
        rank = None
        points = None
        credit_eth = None
    else:
        credit_eth = _eth(high_water)

    marginal = None
    if required_next is not None and weight is not None:
        delta = credited_delta(required_next, high_water if high_water is not None else 0,
                               credit_cap_wei)
        added = weight_added(delta, early_bps)
        if added is not None:
            after = points_for_weight(weight + added, points_per_eth)
            before = points_for_weight(weight, points_per_eth)
            if after is not None and before is not None:
                marginal = after - before

    return rank, points, credit_eth, _eth(required_next), marginal


def you_ladder(
    deposits: Any,
    address: Any,
    *,
    credit_cap_wei: int | None,
) -> list[dict]:
    """The reader's own sends, oldest first, as they actually happened.

    One row per ``Deposited`` the reader produced, carrying the multiplier they
    got at that moment -- which is the number the activity feed cannot show,
    because there it is one wallet's line among everyone else's.

    ``capped`` is the honest name for a send that credited **nothing**: above
    the 1000 ETH cap a deposit still counts in full toward the hour's survival
    while adding no weight at all, so a row reading ``0 credit`` is a fact
    about the cap, not a failed read.  Rows whose credited delta cannot be
    recomputed leave it ``None`` rather than guessing a zero.
    """
    if not isinstance(address, str):
        return []
    key = address.lower()

    rows: list[dict] = []
    running_high_water = 0
    for event in _usable_deposits(deposits):
        contributor = getattr(event, "contributor", "")
        mine = isinstance(contributor, str) and contributor.lower() == key
        amount = _int_or_none(getattr(event, "amount_wei", None))
        if amount is None:
            continue
        if not mine:
            continue

        # The event carries its own credited delta; the recomputation is the
        # cross-check, and they have agreed on all 231 captured rows.
        credited = _int_or_none(getattr(event, "credited_delta_wei", None))
        if credited is None:
            credited = credited_delta(amount, running_high_water, credit_cap_wei)
        bps = _int_or_none(getattr(event, "early_bps", None))
        added = _int_or_none(getattr(event, "weight_added_wei", None))
        if added is None:
            added = weight_added(credited, bps)

        rows.append(
            {
                "hour": _int_or_none(getattr(event, "hour", None)),
                "amount_eth": _eth(amount),
                "credited_eth": _eth(credited),
                "weight_eth": _eth(added),
                "early_x": None if bps is None else bps / 10_000,
                "capped": None if credited is None else (credited == 0 and amount > 0),
                "ts": _int_or_none(getattr(event, "ts", None)),
            }
        )
        running_high_water = max(running_high_water, amount)

    return rows


def cost_to_pass(
    rank: int | None,
    rows: Any,
    *,
    weight_wei: int | None,
    high_water_wei: int | None,
    early_bps: int | None,
    credit_cap_wei: int | None,
) -> tuple[int | None, float | None]:
    """``(rank_above, the single send that would take it)`` -- or ``None``.

    The fold ranks on points, then weight, then **who joined first**, so a tie
    does not pass anybody: the target is ``weight_above + 1`` wei, not equality.

    Everything then runs backwards through the same two primitives the contract
    uses forwards.  ``weight_added`` floors, so reaching ``need`` of it takes
    ``ceil(need * 10_000 / earlyBps)`` of credited delta; and credit telescopes
    to the high-water mark, so the *send* is ``high_water + delta`` rather than
    the delta itself.  A reader at the credit cap cannot buy weight at any
    price and gets ``None`` -- the honest answer, where a number would be a
    promise the contract will not keep.

    Returns ``(None, None)`` for rank 1 (nobody above) and for a wallet not on
    the list, whose first send is quoted by ``you_quote`` instead.
    """
    place = _int_or_none(rank)
    weight = _int_or_none(weight_wei)
    bps = _int_or_none(early_bps)
    if place is None or place <= 1 or weight is None or bps is None or bps <= 0:
        return None, None

    table = [row for row in (rows or []) if _int_or_none(getattr(row, "weight_wei", None)) is not None]
    if len(table) < place - 1:
        return None, None
    target = _int_or_none(getattr(table[place - 2], "weight_wei", None))
    if target is None or target < weight:
        return place - 1, None

    need = target - weight + 1                      # strictly past, never level
    delta = -(-need * 10_000 // bps)                # ceil, the floor's inverse
    high_water = _int_or_none(high_water_wei) or 0
    cap = _int_or_none(credit_cap_wei)
    if cap is not None:
        headroom = cap - min(high_water, cap)
        if delta > headroom:
            return place - 1, None                  # unreachable at any price
    return place - 1, _eth(high_water + delta)


# ---------------------------------------------------------------------------
# build_signals: the one place the readings become the screen's numbers
# ---------------------------------------------------------------------------


def _guard(fn: Any, default: Any = None) -> Any:
    """Run one sub-fold; a failure costs that fold and nothing else.

    The manager wraps this whole call in ``safe_call``, but losing the
    leaderboard because the fan-out grouping hiccuped is still wrong: each
    group of keys degrades on its own, exactly like each read does.
    """
    try:
        return fn()
    except Exception:  # noqa: BLE001 — deliberately total at this boundary
        return default


def _rebuilt_with_saviors(buckets: list[HourBucket], saviors: dict[int, str]) -> list[HourBucket]:
    if not saviors:
        return buckets
    return [
        HourBucket(
            hour=b.hour,
            volume_wei=b.volume_wei,
            deposits=b.deposits,
            judged=b.judged,
            saved_by=saviors.get(b.hour, b.saved_by),
        )
        for b in buckets
    ]


def _hour_saved_rows(raw: Any) -> list[dict]:
    """``HourSaved`` events, newest hour first.  It has never fired on chain."""
    rows: list[dict] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            entry = {
                "hour": getattr(entry, "hour", None),
                "wallet": getattr(entry, "wallet", None),
                "ts": getattr(entry, "ts", None),
            }
        hour = _int_or_none(entry.get("hour"))
        wallet = entry.get("wallet") or entry.get("address")
        if hour is None or not isinstance(wallet, str):
            continue
        rows.append({"hour": hour, "wallet": wallet, "ts": _num_or_none(entry.get("ts"))})
    rows.sort(key=lambda row: row["hour"], reverse=True)
    return rows


def _activity_kind(event: Any, saved: set[tuple[str, int]]) -> str:
    """One of :data:`CURATOR_ACTIVITY_KINDS`, and never a fourth spelling."""
    if (event.contributor.lower(), event.hour) in saved:
        return CURATOR_ACTIVITY_KINDS[2]  # "saved"
    if event.tx_count == 1:
        return CURATOR_ACTIVITY_KINDS[1]  # "joined" — this wallet's first
    return CURATOR_ACTIVITY_KINDS[0]  # "deposit"


def build_signals(readings: Any, *, now_ts: float) -> dict:
    """Every derived key of the flat contract, from one dict of readings.

    Emits **exactly** :data:`SIGNAL_OUTPUT_KEYS`, always all of them: a screen
    that has to ask whether a key exists is a screen with a silent fallback arm.
    The manager adds :data:`MANAGER_OWNED_KEYS` and nothing else.

    This is also **the presentation boundary**: wei becomes ETH here, once, in
    :func:`_eth`.  Nothing downstream divides again.

    ``None`` in, ``None`` out — never a zero.  The three legitimate zeros of
    this contract (a credited delta above the cap, a deficit during grace or on
    a safe hour, an hour total at a boundary) travel through as the measurements
    they are.
    """
    read = readings if isinstance(readings, dict) else {}
    now = _num_or_none(now_ts)

    out: dict[str, Any] = {key: None for key in SIGNAL_OUTPUT_KEYS}
    for key in (
        "leaderboard_rows",
        "activity_rows",
        "closest_call_rows",
        "cluster_rows",
        "volume_series",
        "contributors_series",
    ):
        out[key] = []

    # --- config, straight off the `once` tier ------------------------------
    launch_time = _int_or_none(read.get("launch_time"))
    grace_period = _int_or_none(read.get("grace_period"))
    hour_duration = _int_or_none(read.get("hour_duration"))
    threshold_wei = _int_or_none(read.get("hourly_threshold_wei"))
    first_judged = _int_or_none(read.get("first_judged_hour"))
    points_per_eth = _int_or_none(read.get("points_per_eth"))
    credit_cap = _int_or_none(read.get("credit_cap_wei"))
    early_bps = _int_or_none(read.get("early_bps"))
    current_hour = _int_or_none(read.get("current_hour"))

    out["hourly_threshold_eth"] = _eth(threshold_wei)
    out["first_judged_hour"] = first_judged
    out["current_hour"] = current_hour
    out["hour_seconds_left"] = _int_or_none(read.get("hour_seconds_left"))
    out["hour_needed_eth"] = _eth(read.get("hour_needed_wei"))
    out["forced_eth"] = _eth(read.get("forced_balance_wei"))
    out["rescued_total_eth"] = _eth(read.get("rescued_total_wei"))

    if early_bps is not None:
        out["early_multiplier_x"] = early_bps / _BPS
        fresh = points_for_weight(weight_added(_WEI, early_bps), points_per_eth)
        out["points_per_eth_now"] = None if fresh is None else float(fresh)

    # --- the settlement latch beats the live read --------------------------
    record = read.get("settlement_record")
    latched = getattr(record, "settled", None) is True
    live_settled = read.get("settled")
    settled = True if latched else (live_settled if isinstance(live_settled, bool) else None)
    out["settled"] = settled
    if latched:
        out["settled_hour"] = _int_or_none(getattr(record, "settled_hour", None))
        out["settled_at_ts"] = _int_or_none(getattr(record, "settled_at_ts", None))
        out["settled_observed_at"] = _num_or_none(getattr(record, "observed_at", None))

    phase = _guard(
        lambda: derive_phase(
            now_ts=now,
            launch_time=launch_time,
            grace_period=grace_period,
            settled=settled,
            current_hour=current_hour,
        )
    )
    out["phase"] = phase
    out["grace_seconds_left"] = _guard(
        lambda: grace_seconds_left(
            now_ts=now, launch_time=launch_time, grace_period=grace_period
        )
    )
    out["grace_ends_utc"] = _guard(lambda: grace_ends_utc(launch_time, grace_period))

    ended_at = out["settled_at_ts"] or out["settled_observed_at"] or now
    out["lived_desc"] = _guard(
        lambda: lived_desc(launch_time, ended_at, settled=phase == "settled")
    )

    # --- the folds ---------------------------------------------------------
    raw_deposits = read.get("deposits")
    has_logs = isinstance(raw_deposits, (list, tuple))
    rows = _guard(
        lambda: fold_deposits(
            raw_deposits, read.get("first_deposits"), points_per_eth=points_per_eth
        ),
        [],
    )
    buckets = _guard(
        lambda: hourly_buckets(
            raw_deposits,
            launch_time=launch_time,
            hour_duration=hour_duration,
            first_judged_hour=first_judged,
            hourly_threshold_wei=threshold_wei,
        ),
        [],
    )
    saved_rows = _guard(lambda: _hour_saved_rows(read.get("hour_saved")), [])
    buckets = _guard(
        lambda: _rebuilt_with_saviors(buckets, {row["hour"]: row["wallet"] for row in saved_rows}),
        buckets,
    )

    if saved_rows:
        newest = saved_rows[0]
        out["last_saved_hour"] = newest["hour"]
        out["last_saved_wallet"] = newest["wallet"]
        if now is not None and newest["ts"] is not None:
            out["last_saved_age_s"] = max(0.0, now - newest["ts"])

    # --- totals: the contract's own counters first -------------------------
    out["contributors_total"] = _int_or_none(read.get("contributors"))
    out["deposits_total"] = _int_or_none(read.get("tx_count"))
    out["volume_routed_eth"] = _eth(read.get("volume_wei"))
    if out["contributors_total"] is None and has_logs:
        out["contributors_total"] = len(rows)
    if out["deposits_total"] is None and has_logs:
        out["deposits_total"] = sum(b.deposits for b in buckets)
    if out["volume_routed_eth"] is None and has_logs:
        out["volume_routed_eth"] = _eth(sum(b.volume_wei for b in buckets))
    if rows:
        out["top_points"] = rows[0].points

    if has_logs and current_hour is not None:
        live = [b for b in buckets if b.hour == current_hour]
        out["hour_fed_eth"] = _eth(live[0].volume_wei) if live else 0.0

    # --- survival ----------------------------------------------------------
    # ``survival()`` is handed ``[]`` for two different facts — "the logs read
    # fine and found nothing" and "every log group failed" — and cannot tell
    # them apart, so it answers a streak of ``0`` for both.  The caller can:
    # ``has_logs`` is False exactly when the deposits read did not happen.  A
    # ``0`` there renders "we have survived nothing" off a refresh that merely
    # could not look, which is the house rule's own bug (a failed read is
    # ``None``, never ``0``) — and state and logs sit on *different endpoint
    # pools*, so live-state/dead-logs is the expected outage, not a corner.
    record_survival = (
        _guard(
            lambda: survival(
                buckets,
                current_hour=current_hour,
                hourly_threshold_wei=threshold_wei,
                first_judged_hour=first_judged,
            ),
            {},
        )
        if has_logs
        else {}
    )
    out["survival_streak_hours"] = record_survival.get("streak_hours")
    out["closest_call_hour"] = record_survival.get("closest_call_hour")
    out["closest_call_margin_eth"] = _eth(record_survival.get("closest_call_margin_wei"))
    out["closest_call_rows"] = [
        {
            "hour": hour,
            "volume_eth": _eth(volume),
            "margin_eth": _eth(margin),
            "savior": savior,
        }
        for hour, volume, margin, savior in record_survival.get("closest_calls", [])[
            :CLOSEST_CALL_LIMIT
        ]
    ]

    # --- signal states -----------------------------------------------------
    out["sig_at_risk_state"] = _guard(
        lambda: at_risk_state(
            phase=phase,
            needed_wei=_int_or_none(read.get("hour_needed_wei")),
            seconds_left=out["hour_seconds_left"],
            first_judged_hour=first_judged,
        )[0]
    )
    if settled is True:
        observed = out["settled_observed_at"]
        fresh = observed is None or now is None or (now - observed) < FIRED_TTL_S
        out["sig_settled_state"] = STATE_FIRED if fresh else STATE_WATCH
    elif settled is False:
        out["sig_settled_state"] = STATE_OK

    # --- whale -------------------------------------------------------------
    whale = _guard(lambda: newest_whale(raw_deposits, now_ts=now))
    if whale:
        out["whale_amount_eth"] = _eth(whale["amount_wei"])
        out["whale_wallet"] = whale["wallet"]
        out["whale_age_s"] = whale["age_s"]

    # --- fan-out patterns --------------------------------------------------
    found = _guard(lambda: find_clusters(raw_deposits, rows), [])
    flagged = _guard(lambda: cluster_members(raw_deposits), set())
    if has_logs:
        out["clusters_count"] = len(found)
    out["cluster_rows"] = list(found[:CLUSTER_LIMIT])
    shares = [row["points_share_pct"] for row in found]
    if shares and all(share is not None for share in shares):
        out["flagged_points_share_pct"] = sum(shares)

    # --- rows --------------------------------------------------------------
    out["leaderboard_rows"] = [
        {
            "rank": rank,
            "address": row.address,
            "points": row.points,
            "credit_eth": _eth(row.credit_wei),
            "tx_count": row.tx_count,
            "flagged": row.address.lower() in flagged,
        }
        for rank, row in enumerate(rows[:LEADERBOARD_LIMIT], start=1)
    ]

    saved_keys = {(row["wallet"].lower(), row["hour"]) for row in saved_rows}
    events = _guard(lambda: _usable_deposits(raw_deposits), [])
    out["activity_rows"] = [
        {
            "ts": event.ts,
            "address": event.contributor,
            "amount_eth": _eth(event.amount_wei),
            "credited_eth": _eth(event.credited_delta_wei),
            "new_weight": _eth(event.new_weight_wei),
            "tx_count": event.tx_count,
            "hour": event.hour,
            "kind": _activity_kind(event, saved_keys),
            "tx_hash": getattr(event, "tx_hash", None),
            "log_index": event.log_index,
        }
        for event in reversed(events[-ACTIVITY_LIMIT:])
    ]

    # --- series: from the folded buckets only ------------------------------
    out["volume_series"] = [
        [bucket_start_ts(b.hour, launch_time, hour_duration), _eth(b.volume_wei)]
        for b in buckets
        if bucket_start_ts(b.hour, launch_time, hour_duration) is not None
    ]
    joined_by_hour: dict[int, int] = {}
    for row in rows:
        if row.first_hour is not None:
            joined_by_hour[row.first_hour] = joined_by_hour.get(row.first_hour, 0) + 1
    running = 0
    contributors_series: list[list[Any]] = []
    for bucket in buckets:
        running += joined_by_hour.get(bucket.hour, 0)
        stamp = bucket_start_ts(bucket.hour, launch_time, hour_duration)
        if stamp is not None:
            contributors_series.append([stamp, running])
    out["contributors_series"] = contributors_series

    # --- YOU ---------------------------------------------------------------
    quote = _guard(
        lambda: you_quote(
            read.get("wallet_state"),
            rows,
            points_per_eth=points_per_eth,
            early_bps=early_bps,
            credit_cap_wei=credit_cap,
        ),
        (None, None, None, None, None),
    )
    (
        out["you_rank"],
        out["you_points"],
        out["you_credit_eth"],
        out["you_required_next_eth"],
        out["you_marginal_points"],
    ) = quote

    # --- YOU, the dedicated view -------------------------------------------
    # Folded from payloads already in hand.  Every field degrades on its own:
    # a dead logs pool costs the ladder and the share, not the standing, which
    # comes off the six wallet views on the other pool.
    wallet_state = read.get("wallet_state")
    address = getattr(wallet_state, "address", None)
    weight_wei = _int_or_none(getattr(wallet_state, "weight_wei", None))
    joined = getattr(wallet_state, "has_joined", None)

    if joined is not False:
        out["you_weight_eth"] = _eth(weight_wei)
        out["you_tx_count"] = _int_or_none(getattr(wallet_state, "tx_count", None))
        first_hour = _int_or_none(getattr(wallet_state, "first_hour", None))
        out["you_first_hour"] = first_hour
        joined_ts = _guard(
            lambda: bucket_start_ts(first_hour, launch_time, hour_duration)
        )
        if joined_ts is not None:
            out["you_joined_utc"] = datetime.fromtimestamp(
                joined_ts, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")

        # Share of ALL weight, folded from the same rows the leaderboard ranks.
        # `None` when the fold has nothing: 0.0% would claim a share was
        # measured and found to be nil.
        total_weight = sum(
            _int_or_none(getattr(row, "weight_wei", None)) or 0 for row in rows
        )
        if weight_wei is not None and total_weight > 0:
            out["you_weight_share_pct"] = weight_wei * 100.0 / total_weight

        out["you_ladder_rows"] = _guard(
            lambda: you_ladder(read.get("deposits"), address,
                               credit_cap_wei=credit_cap),
            [],
        )

        (
            out["you_next_rank"],
            out["you_next_rank_needs_eth"],
        ) = _guard(
            lambda: cost_to_pass(
                out["you_rank"],
                rows,
                weight_wei=weight_wei,
                high_water_wei=_int_or_none(
                    getattr(wallet_state, "contributed_wei", None)
                ),
                early_bps=early_bps,
                credit_cap_wei=credit_cap,
            ),
            (None, None),
        )

    return out


#: Re-exported so a consumer of this module has one import site for the phase
#: vocabulary it is about to branch on.  It is ``curator_models``' tuple,
#: not a copy — a second spelling of "settled" is exactly the fallback arm the
#: single tuple exists to prevent.
PHASES = PHASES


__all__ = [
    "PHASES",
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
    "find_clusters",
    "cluster_members",
    "newest_whale",
    "you_quote",
    "you_ladder",
    "cost_to_pass",
    # the seam
    "build_signals",
]
