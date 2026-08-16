"""Frozen interface for the curator dashboard — THE LIST.

Boundaries only: this module imports nothing but the standard library.  No
client, no cache, no analytics, no Textual.  Every other curator module codes
against what is declared here, and four of them are written in parallel by
agents that never speak to each other — so a field named wrong in this file is
discovered a wave later, at the cost of the wave.

Unit discipline
    **Models are wei-native; the flat dict is the presentation boundary.**
    ``*_wei`` fields are ``int``; ``CuratorManager`` divides exactly once when
    it builds the flat dict, which is why the dict carries ``hour_fed_eth`` /
    ``volume_routed_eth`` while the models carry ``current_hour_total_wei`` /
    ``volume_wei``.  ``test_no_wei_key_leaks_into_the_flat_dict`` and
    ``test_no_eth_denominated_field_reaches_a_model`` pin both directions.

Naming discipline
    **Model fields mirror the chain; flat-dict keys mirror the PRD.**  The
    getter is ``isSettled()`` so the field is ``settled``; the hero key is
    ``phase``.  ``ethNeededThisHour()`` is ``hour_needed_wei`` on the model and
    ``hour_needed_eth`` in the dict.  The mapping table lives in
    ``curator_manager``; nothing here is renamed to match a widget, and
    ``test_no_flat_dict_key_masquerades_as_a_model_field`` forbids the
    confusion.

Raw discipline
    **The client returns what it read; interpretation is pure-function work.**
    :class:`DepositEvent` carries the nine decoded event words and nothing
    derived — ``points``, ``margin`` and cluster membership are all
    ``analytics/curator_signals``'s, which is what gives those functions exactly
    one caller and one test suite each.  :class:`LogSweep` carries raw log rows
    for the same reason.

Outage discipline
    **A failed read is ``None``, never ``0``.**  Every field a read can fail to
    produce is ``… | None``.  Nothing here defaults to ``0``: a zero written
    into a persisted series outlives the outage that produced it, and no
    consumer can tell it from a real measurement afterwards.

The three legitimate zeros
    This contract makes that rule unusually load-bearing, because it has zeros
    that are *answers*:

    * ``currentHourTotal()`` is ``0`` at every hour boundary, for as long as it
      takes the next deposit to land — while ``lastActiveHour()`` still names
      the previous bucket.  A sparkline fed from this view reads the boundary as
      a 99.5% crash (it did: 9987.26 → 51.48 ETH across 2026-08-16 21:58:47 UTC,
      captured in ``hour_boundary_h1_h2.json``).  History is folded from
      ``Deposited`` logs only; the fast tier never writes into a series.
    * ``ethNeededThisHour()`` is ``0`` through the entire grace period and again
      whenever a judged hour is already safe.  A ``None`` here must never light
      the HOUR AT RISK state, and a ``0`` must never be rendered as unknown.
    * ``creditedDelta`` is ``0`` for a deposit above the 1000 ETH cap, which
      still counts *fully* toward hourly survival.  Nothing may divide by it.

Why ``has_joined`` is its own field
    ``contributors(address)`` packs ``firstHour + 1`` into a ``uint32`` so that
    ``0`` can mean "never deposited".  ``firstHourOf(address)`` un-shifts it and
    returns **two** words, ``(hour, hasJoined)``.  ``(0, false)`` is a stranger
    and ``(0, true)`` is someone who deposited in the launch hour; one field
    cannot carry both, and a scalar decode of that view renders every stranger
    as a founder.  ``lastActiveHour()`` is two words for the same reason —
    ``(hour, total)`` — and ``stats()`` is three.

Nothing in this module is read-write.  ``deposit()``, ``settle()`` and
``rescue()`` are read *about*, never called.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The three phases of the settlement state machine, in order.
#:
#: One tuple, imported by the analytics layer (which produces it), the manager
#: (which passes it through), the widgets (which branch on it) and the screen
#: (which picks the swap-slot default from it).  A fourth spelling anywhere is a
#: silent fallback arm.
PHASES: tuple[str, ...] = ("grace", "judged", "settled")

#: The seven signal-rail rows, in render order.  ``sig_settled_state`` and
#: ``sig_at_risk_state`` are the two whose colour is a judgement rather than a
#: number; the rest are observations.
SIGNAL_ROWS: tuple[str, ...] = (
    "settled",
    "at_risk",
    "hour_saved",
    "whale",
    "clusters",
    "forced_eth",
    "rescued",
)


# ---------------------------------------------------------------------------
# Chain state
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CuratorState:
    """One batched ``eth_call`` round — the PRD fast tier — plus the balance.

    Eight views in one batch: ``isSettled``, ``currentHour``,
    ``currentHourTotal``, ``ethNeededThisHour``, ``timeLeftInHour``,
    ``lastActiveHour`` (2 words), ``earlyMultiplierBps``, ``stats`` (3 words);
    ``forced_balance_wei`` comes from a separate ``eth_getBalance``.

    Every field is independently failable: one sub-call that reverted or was
    dropped degrades *that* field to ``None``, not the round.

    ``settled`` is a ``bool | None`` and the three states are all distinct:
    ``True`` (the game is over), ``False`` (it is running) and ``None`` (we do
    not know).  Only the first may render SETTLED.

    ``current_hour`` and ``last_active_hour`` disagreeing is **normal**, not an
    error: at an hour boundary the clock has moved and no deposit has landed in
    the new bucket yet.  Post-grace that same shape is the at-risk state.

    ``forced_balance_wei`` is **always forced ETH**, never deposits — every wei
    of a deposit is refunded in the same transaction.  It feeds the ``forced_eth``
    anomaly row and must never reach a volume, TVL or hero total; the expected
    rendering is ``—``.
    """

    settled: bool | None
    current_hour: int | None
    current_hour_total_wei: int | None
    hour_needed_wei: int | None
    hour_seconds_left: int | None
    last_active_hour: int | None
    last_active_hour_total_wei: int | None
    early_bps: int | None
    volume_wei: int | None
    contributors: int | None
    tx_count: int | None
    forced_balance_wei: int | None
    block_number: int | None = None


@dataclass(frozen=True, slots=True)
class CuratorConfig:
    """The ``once`` tier: eight immutables, one constant, one address.

    Read **live**, never hardcoded (CLAUDE.md).  ``curator_addresses`` pins the
    same numbers so a test can prove the live read agrees, but the dashboard
    always renders what the chain answered.  Nothing on this contract can change
    them — there is no owner power that reaches a parameter — so ``once`` is a
    genuine forever cache rather than a long TTL.

    ``deployer`` is an address string, not a number: decode it with
    ``decode_address``.
    """

    launch_time: int | None
    hourly_threshold_wei: int | None
    grace_period: int | None
    hour_duration: int | None
    min_deposit_wei: int | None
    min_escalation_wei: int | None
    credit_cap_wei: int | None
    first_judged_hour: int | None
    points_per_eth: int | None
    deployer: str | None


@dataclass(frozen=True, slots=True)
class WalletState:
    """The six argument-taking views, for the YOU row.  Only when a wallet is set.

    ``first_hour`` is **already un-shifted** — it is ``firstHourOf()``'s first
    word, not the packed struct's ``firstHour + 1``.  ``has_joined`` is the
    second word, and it exists because ``first_hour == 0`` is ambiguous without
    it: ``(0, False)`` means "never deposited" and must never render as "joined
    in hour 0".

    ``required_next_wei`` is what the *next* deposit from this address must
    exceed (high-water mark + ``minEscalation``); it is a live number that grows
    every time the wallet deposits.
    """

    address: str
    points: int | None
    weight_wei: int | None
    contributed_wei: int | None
    tx_count: int | None
    first_hour: int | None
    has_joined: bool | None
    required_next_wei: int | None


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DepositEvent:
    """One decoded ``Deposited`` log.  Raw words only — nothing derived.

    ``contributor`` and ``hour`` are the two **indexed** topics, which is why
    hour bucketing needs no timestamp at all: the hour is in the log, and its
    wall clock is ``launchTime + hour * hourDuration``, exact by construction.

    ``credited_delta_wei`` may legitimately be ``0`` (a deposit above the credit
    cap) and ``weight_added_wei`` with it.  Both are still real measurements;
    neither is a failed read, and nothing may divide by either.

    ``weight_added_wei == credited_delta_wei * early_bps // 10_000``, floored —
    an identity that holds for all 231 captured rows and is re-asserted wei-exact
    by the analytics suite.

    ``ts`` is the block's wall clock, filled by the bounded
    ``eth_getBlockByNumber`` batch, and is ``None`` when that read failed.  A
    ``None`` renders ``--:--``, never ``00:00``.  ``(tx_hash, log_index)`` is the
    de-dupe key: without it a re-org replay renders every deposit twice.
    """

    contributor: str
    hour: int
    amount_wei: int
    credited_delta_wei: int
    weight_added_wei: int
    new_weight_wei: int
    tx_count: int
    hour_total_wei: int
    early_bps: int
    block_number: int
    tx_hash: str
    log_index: int
    ts: float | None = None


@dataclass(frozen=True, slots=True)
class LogSweep:
    """One ``eth_getLogs`` window, grouped by event, rows still raw.

    Each group holds the log dicts as the endpoint served them, with ``topics``,
    ``data``, ``blockNumber``, ``transactionHash`` and ``logIndex`` intact — the
    decoders live downstream so they have exactly one caller and one hostile-input
    suite.

    ``()`` means "read, nothing matched" **or** "this one filter failed".  A
    frozen tuple cannot hold ``None``, so the per-group failure travels
    out-of-band in the client's ``log_group_failed`` dict and reaches the user
    through the manager's ``degraded`` list.  A sweep where **every** group
    failed returns ``None`` instead of a :class:`LogSweep`.
    """

    from_block: int | None
    to_block: int | None
    deposits: tuple[dict, ...] = ()
    first_deposits: tuple[dict, ...] = ()
    hour_saved: tuple[dict, ...] = ()
    settled: tuple[dict, ...] = ()
    rescued: tuple[dict, ...] = ()
    launched: tuple[dict, ...] = ()


# ---------------------------------------------------------------------------
# Folds
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContributorRow:
    """One folded leaderboard row.  Produced by the fold, not by the client.

    ``credit_wei`` is the address's high-water mark — its credited net
    contribution — not the gross it routed; ``weight_wei`` is the sum of
    ``creditedDelta × earlyBps``, which is what the curve turns into points.
    The two diverge for anyone who deposited late, and calling either "volume"
    is wrong.

    ``points`` stays ``None`` until the curve is applied.  A ``0`` there would
    render a real entry as having scored nothing.

    ``first_index`` is ``FirstDeposit``'s **1-based** index; it maxes at exactly
    ``totalContributors``.
    """

    address: str
    weight_wei: int
    credit_wei: int
    tx_count: int
    first_hour: int | None
    first_index: int | None
    points: int | None = None


@dataclass(frozen=True, slots=True)
class HourBucket:
    """One hour of the game, folded from ``Deposited`` logs only.

    Never from ``currentHourTotal()`` — that view zeroes at every boundary and a
    series fed from it renders the boundary as a crash.

    ``judged`` is false for the in-progress hour and for every hour before
    ``firstJudgedHour``: the contract's own ``_isShort`` returns false while
    ``lastActive == hour``, so the hour you are living in is never judged.

    ``saved_by`` is the address of a ``HourSaved`` savior and is ``None`` for
    every hour that event never fired in — which, as of the captures, is all of
    them.  It may never fire at all; the row renders its explicit never-fired
    state rather than waiting for a payload.
    """

    hour: int
    volume_wei: int
    deposits: int
    judged: bool
    saved_by: str | None = None


@dataclass(frozen=True, slots=True)
class SettlementRecord:
    """The settlement evidence record — the latch, and later the obituary.

    ``settle()`` is permissionless and may lag death indefinitely, so
    ``isSettled()`` is polled and the *view* is the source of truth.  The first
    three fields are that observation: on the first ``True``, the manager writes
    ``{value, block_number, observed_at}`` and **never re-reads through it**.
    A later outage degrades the freshness marker, never the phase.

    The last four are filled from the ``Settled`` log when it eventually
    appears, and stay ``None`` until then — possibly forever.  ``settled_hour``
    is the hour that failed; ``settled_at_ts`` is the log's own timestamp word,
    not the observation time.
    """

    settled: bool
    block_number: int | None
    observed_at: float
    settled_hour: int | None = None
    settled_at_ts: int | None = None
    total_contributors: int | None = None
    total_volume_wei: int | None = None


__all__ = [
    "PHASES",
    "SIGNAL_ROWS",
    "CuratorState",
    "CuratorConfig",
    "WalletState",
    "DepositEvent",
    "LogSweep",
    "ContributorRow",
    "HourBucket",
    "SettlementRecord",
]
