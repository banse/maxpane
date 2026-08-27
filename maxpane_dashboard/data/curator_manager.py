"""Orchestrator for the curator dashboard — THE LIST.

One coordination point between three independently failing source groups, four
refresh tiers and one frozen output contract.  Exposes one public coroutine,
:meth:`CuratorManager.fetch_and_compute`, which returns **exactly**
:data:`~maxpane_dashboard.data.curator_models.CURATOR_KEYS` — always, under
every failure combination, and without ever letting an exception escape.

Source groups and how they die
------------------------------

===========  ==========================================  =====================
Group        Client call                                 Dies as
===========  ==========================================  =====================
``state``    ``fetch_state`` + ``fetch_balance`` +       the state RPC pool
             ``fetch_config``                            (publicnode + fallbacks)
``logs``     ``fetch_logs`` + ``fetch_blockscout_logs``  the logs RPC pool
                                                         (tenderly + drpc)
``wallet``   ``fetch_wallet``                            either, or a bad address
===========  ==========================================  =====================

The three names are :data:`~maxpane_dashboard.data.curator_models.CURATOR_DEGRADED_GROUPS`
verbatim, because the title bar renders them verbatim.  A manager that invented
a fourth (``"rpc"``, ``"config"``) would light a banner the screen's formatter
has never seen.

**State and logs sit on different endpoint pools**, so live-state/dead-logs is
the *expected* outage rather than a corner case: the clock, the phase and the
forced-ETH anomaly keep working while the leaderboard, the series, the activity
feed and the clusters go to last-good behind an ``as of HH:MM`` marker.  The
reverse happens too.  Neither one may present the other's absence as a zero.

Four rules this module exists to enforce
----------------------------------------

1. **The settlement latch beats the live read (H1).**  ``isSettled()`` is
   polled on the fast tier and the first ``True`` is handed to
   :meth:`~maxpane_dashboard.data.curator_cache.CuratorCache.observe_settlement`,
   which writes the evidence down once.  From then on an RPC outage degrades
   the freshness marker and never the phase.  ``settle()`` is permissionless, so
   the ``Settled`` *event* is the obituary and fills in the final hour and
   totals if it ever appears — it never creates the verdict.
2. **The series are fed from folded ``Deposited`` logs only (H2).**  The fast
   tier's payload keys and the series writer's inputs are disjoint sets and
   ``test_the_fast_tier_payload_cannot_reach_the_series`` asserts it rather than
   reasoning about it.  The hour comes off the event's *indexed* second topic,
   so no timestamp and no state read participates.
3. **A failed read is ``None``, never ``0``.**  Every reading handed to
   ``build_signals`` is either a real value or ``None``.  This contract has
   three legitimate zeros — the hour total at a boundary, the deficit during
   grace or on a safe hour, and a credited delta above the 1000 ETH cap — and
   each stays distinguishable from an outage.
4. **The balance is always forced ETH (H5).**  Every wei of a deposit is
   refunded in the same transaction, so ``eth_getBalance`` feeds ``forced_eth``
   and nothing else: never a volume, never a TVL, never a hero total.

Where the division happens
--------------------------

Most manager models remain wei-native. ``build_signals`` divides its own
presentation values once, the cache's series writer divides its buckets once
on the way to disk, and ``_filtered_routed_eth`` performs this module's one
intended presentation conversion for the filtered hero. Two divisions is how
a number silently becomes 1e-18 of itself, so
``test_the_manager_divides_to_eth_exactly_once`` pins this module's count at
one.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics.curator_signals import (
    READING_KEYS,
    bucket_start_ts,
    build_signals,
    cluster_members,
    fold_deposits,
    hourly_buckets,
    project_leaderboard_rows,
    WHALE_MIN_ETH,
)
from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data import ens
from maxpane_dashboard.data import curator_archive
from maxpane_dashboard.data import curator_clusters
from maxpane_dashboard.data import curator_published
from maxpane_dashboard.data.curator_published import PublishedVersion, version_label
from maxpane_dashboard.data.curator_cache import (
    DEFAULT_CACHE_PATH,
    NFT_HOLDER_TTL_SECONDS,
    SLOT_BLOCKSCOUT,
    SLOT_CONFIG,
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    TIER_ANALYSIS,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_ONCE,
    TIER_SLOW,
    CuratorCache,
)
from maxpane_dashboard.data.curator_client import LOG_GROUPS, CuratorClient
from maxpane_dashboard.data.curator_models import (
    CURATOR_DEGRADED_GROUPS,
    CURATOR_KEYS,
    CURATOR_SERIES_KEYS,
    DepositEvent,
)
from maxpane_dashboard.data.evm_abi import addr_from_topic, strip0x
from maxpane_dashboard.data.curator_list_filters import (
    FILTER_FAMILIES,
    FilterContext,
    FilterSpec,
    NftCollectionRef,
    custom_nft_label,
    filter_rows,
    parse_nft_collection,
)
from maxpane_dashboard.data.curator_nft_holders import (
    NftHolderClient,
    NftHolderPending,
    NftHolderUnavailable,
    wallet_universe_fingerprint,
)
from maxpane_dashboard.data.curator_list_source import load_export_list
from maxpane_dashboard.data.safe_call import safe_call as _safe_call

logger = logging.getLogger(__name__)


def _opt_int(value: Any) -> int | None:
    """An ``int`` if the value is one, else ``None``.  ``bool`` is not one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _str_or_none(value: Any) -> str | None:
    """A non-empty ``str``, else ``None``.  Third-party fields only."""
    return value if isinstance(value, str) and value else None


#: The status words ``/versions`` folds its counts by.  ``status_counts`` was
#: the one place an unbounded third-party mapping entered a payload this
#: dashboard PERSISTS -- every other field in the provenance block is a
#: scalar, and the curator cache is already 26 MB on the live install, so a
#: service answering ten thousand keys would have written all of them into it
#: forever.  An allowlist rather than a size cap: the vocabulary is the three
#: words the export's own ``status`` field uses, the block is provenance that
#: nothing computes from, and a fixed key set is a stronger bound than a
#: number somebody has to pick.  A fourth word the publisher invents is
#: dropped from the provenance, not from the analysis.
_PUBLISHED_STATUS_WORDS = ("clean", "flagged", "review")


def _published_block(
    version: PublishedVersion,
    *,
    fetched_at: float,
    archived_version: str | None,
) -> dict[str, Any]:
    """The slot's ``published`` provenance, assembled field by field.

    Field by field, and coerced, for one reason: **no boolean may enter
    ``SLOT_CLUSTERS``**.  The no-verdict rule there is "no boolean anywhere in
    the payload" with a permanently empty allowlist, and ``/versions`` carries
    a ``"published": true`` stage flag beside fields that are all third-party
    strings — so copying an entry, or trusting one of its values, trips the
    guard.  The service's own *word* for the stage (``"published"`` /
    ``"superseded"``) is the only form of that fact this dashboard would ever
    persist; the flag itself never travels.  Every value below is a string, a
    number or ``None``, and a hostile one degrades to absence rather than to a
    coerced lie.

    The key set is the one :func:`curator_clusters.slot_payload` documents and
    :func:`_analysis_version` reads back, unchanged.
    """
    counts = version.status_counts if isinstance(version.status_counts, Mapping) else {}
    return {
        "version_id": _str_or_none(version.version_id),
        "content_hash": _str_or_none(version.content_hash),
        "detector_version": _str_or_none(version.detector_version),
        "rule_set": _str_or_none(version.rule_set),
        "rules_sha256": _str_or_none(version.rules_sha256),
        "snapshot_block": _opt_int(version.snapshot_block),
        "status_counts": {
            name: counts[name]
            for name in _PUBLISHED_STATUS_WORDS
            if _opt_int(counts.get(name)) is not None
        },
        "fetched_at": float(fetched_at),
        "archived_version": _str_or_none(archived_version),
    }


def _is_same_published(held: Any, version: PublishedVersion) -> bool:
    """Is the held slot already this exact published analysis?

    **Both** halves are compared.  The id alone is not enough: the publisher
    rebuilds under one id, and an id-only check would keep serving superseded
    rows until the id itself changed.  The hash alone is not enough either —
    it is what names the bytes, but the id is what names the archive
    directory, and the two must agree before a tick may decide there is
    nothing to do.
    """
    if not isinstance(held, Mapping):
        return False
    published = held.get("published")
    if not isinstance(published, Mapping):
        return False
    return (
        published.get("version_id") == version.version_id
        and published.get("content_hash") == version.content_hash
    )


def _analysis_version(published: Any) -> str | None:
    """``version_label`` off the slot's own persisted ``published`` block.

    ``published`` is :func:`curator_clusters.slot_payload`'s own
    ``{version_id, content_hash, detector_version, rule_set, rules_sha256,
    snapshot_block, status_counts, fetched_at, archived_version}``, copied
    whole by the manager and never computed here (that module's own
    docstring).  Absent on every slot until a later wiring lands the live
    fetch, and on any malformed slot -- a hand-edited cache file is
    third-party input too -- this degrades to ``None`` rather than raising;
    the caller only ever interpolates the result when it is a real string, so
    a missing version renders the freshness marker alone, never the word
    "None".
    """
    if not isinstance(published, Mapping):
        return None
    version_id = published.get("version_id")
    if not isinstance(version_id, str) or not version_id:
        return None
    status_counts = published.get("status_counts")
    return version_label(
        PublishedVersion(
            version_id=version_id,
            content_hash=published.get("content_hash") or "",
            detector_version=published.get("detector_version"),
            rule_set=published.get("rule_set"),
            rules_sha256=published.get("rules_sha256"),
            snapshot_block=published.get("snapshot_block"),
            cluster_count=published.get("cluster_count"),
            status_counts=status_counts if isinstance(status_counts, dict) else {},
        )
    )


def _looks_like_address(value: Any) -> bool:
    """A 20-byte hex address, checked locally before a request is spent on it."""
    if not isinstance(value, str):
        return False
    body = value[2:] if value.lower().startswith("0x") else value
    if len(value) != 42 or len(body) != 40:
        return False
    try:
        int(body, 16)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Log decoding — raw rows in, models out
# ---------------------------------------------------------------------------
#
# The client hands back log rows **verbatim** so that the decoders have exactly
# one caller and one hostile-input suite, and this is that decoder.  It reads
# both dialects the two sources speak, because the Blockscout cross-check has to
# be diffable against the RPC sweep:
#
#   RPC (tenderly / drpc)   blockNumber "0x18937a0"   transactionHash   logIndex
#                           blockTimestamp "0x6a82174f"
#   Blockscout REST         block_number 25770244     transaction_hash  index
#                           block_timestamp "2026-08-16T21:13:35.000000Z"
#
# Two rules run through all of it:
#
# * **A short or malformed payload decodes to ``None``, never to zeros.**  A
#   reverted call and a truncated log both come back as something ``int(x, 16)``
#   would happily turn into a 0, and a 0 here is a deposit that never happened
#   sitting on the leaderboard.
# * **A missing timestamp stays ``None``.**  Every captured row carries one
#   (H14 is struck through), but the fallback batch exists for an endpoint that
#   omits it, and ``ts=None`` renders ``--:--`` where a ``0`` renders
#   1970-01-01 — which looks like data.

#: ``Deposited``'s seven data words, in the order the ABI declares them.
_DEPOSIT_DATA_WORDS = (
    "amount_wei",
    "credited_delta_wei",
    "weight_added_wei",
    "new_weight_wei",
    "tx_count",
    "hour_total_wei",
    "early_bps",
)

#: ``Launched``'s seven data words — no indexed fields at all.
_LAUNCHED_DATA_WORDS = (
    "launch_time",
    "hourly_threshold_wei",
    "grace_period",
    "hour_duration",
    "min_deposit_wei",
    "min_escalation_wei",
    "credit_cap_wei",
)


def _topics(row: Any) -> list[str]:
    """The row's topic array, ``None`` padding dropped (Blockscout pads to 4)."""
    if not isinstance(row, dict):
        return []
    raw = row.get("topics")
    if not isinstance(raw, (list, tuple)):
        return []
    return [t for t in raw if isinstance(t, str)]


def _data_words(row: Any) -> list[str]:
    """The row's data blob split into 32-byte words.  A partial tail is dropped."""
    if not isinstance(row, dict):
        return []
    raw = row.get("data")
    if not isinstance(raw, str):
        return []
    body = strip0x(raw)
    return [body[i : i + 64] for i in range(0, len(body) - len(body) % 64, 64)]


def _hex_or_int(value: Any) -> int | None:
    """An ``int`` from either dialect's number, or ``None``.  Never a ``0`` guess."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value, 16) if value.lower().startswith("0x") else int(value, 10)
        except ValueError:
            return None
    return None


def _row_block(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    return _hex_or_int(row.get("blockNumber", row.get("block_number")))


def _row_log_index(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    return _hex_or_int(row.get("logIndex", row.get("index")))


def _row_tx_hash(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    value = row.get("transactionHash", row.get("transaction_hash"))
    return value if isinstance(value, str) and value else None


def _row_ts(row: Any) -> float | None:
    """The row's own block timestamp, in epoch seconds, or ``None``.

    Read from the row rather than re-fetched: every captured row on both
    sources carries one, and a client that discards a stamp it was handed pays
    a round trip for nothing (H14, refuted and inverted).
    """
    if not isinstance(row, dict):
        return None
    raw = row.get("blockTimestamp", row.get("block_timestamp"))
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) if raw > 0 else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    if raw.lower().startswith("0x"):
        value = _hex_or_int(raw)
        return float(value) if value else None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def decode_deposit(row: Any) -> DepositEvent | None:
    """One ``Deposited`` row → :class:`DepositEvent`, or ``None`` if unusable.

    ``contributor`` and ``hour`` are the two **indexed** topics, which is why
    hour bucketing needs no timestamp at all: the hour is in the log and its
    wall clock is ``launchTime + hour × hourDuration``, exact by construction.
    The seven data words are taken raw — nothing derived, nothing divided.
    """
    topics = _topics(row)
    words = _data_words(row)
    if len(topics) < 3 or topics[0].lower() != A.TOPIC_DEPOSITED.lower():
        return None
    if len(words) < len(_DEPOSIT_DATA_WORDS):
        return None
    block = _row_block(row)
    log_index = _row_log_index(row)
    tx_hash = _row_tx_hash(row)
    if block is None or log_index is None or tx_hash is None:
        # Without the de-dupe key a re-org replay renders every deposit twice.
        return None
    try:
        values = {
            name: int(words[i], 16) for i, name in enumerate(_DEPOSIT_DATA_WORDS)
        }
        hour = int(strip0x(topics[2]), 16)
    except ValueError:
        return None
    return DepositEvent(
        contributor=addr_from_topic(topics[1]),
        hour=hour,
        block_number=block,
        tx_hash=tx_hash,
        log_index=log_index,
        ts=_row_ts(row),
        **values,
    )


def decode_first_deposit(row: Any) -> dict | None:
    """One ``FirstDeposit`` row → ``{"contributor", "index", "ts"}``.

    ``index`` is the second **indexed** topic, is 1-based, and maxes at exactly
    ``totalContributors``.  The data word is the contract's own timestamp; the
    row's block stamp is the fallback.
    """
    topics = _topics(row)
    if len(topics) < 3 or topics[0].lower() != A.TOPIC_FIRST_DEPOSIT.lower():
        return None
    try:
        index = int(strip0x(topics[2]), 16)
    except ValueError:
        return None
    words = _data_words(row)
    ts: float | None = None
    if words:
        try:
            stamped = int(words[0], 16)
        except ValueError:
            stamped = 0
        ts = float(stamped) if stamped > 0 else None
    return {
        "contributor": addr_from_topic(topics[1]),
        "index": index,
        "ts": ts if ts is not None else _row_ts(row),
    }


def decode_hour_saved(row: Any) -> dict | None:
    """One ``HourSaved`` row → ``{"hour", "wallet", "ts"}``.  Never fired yet."""
    topics = _topics(row)
    if len(topics) < 3 or topics[0].lower() != A.TOPIC_HOUR_SAVED.lower():
        return None
    try:
        hour = int(strip0x(topics[2]), 16)
    except ValueError:
        return None
    return {"hour": hour, "wallet": addr_from_topic(topics[1]), "ts": _row_ts(row)}


def decode_settled(row: Any) -> dict | None:
    """One ``Settled`` row → the obituary's four values.  Never the latch.

    ``isSettled()`` is derived, so it can flip with no log at all; this row is
    evidence about the past and only fills in details the view cannot give.
    """
    topics = _topics(row)
    words = _data_words(row)
    if len(topics) < 2 or topics[0].lower() != A.TOPIC_SETTLED.lower():
        return None
    if len(words) < 3:
        return None
    try:
        return {
            "hour": int(strip0x(topics[1]), 16),
            "ts": int(words[0], 16),
            "total_contributors": int(words[1], 16),
            "total_volume_wei": int(words[2], 16),
        }
    except ValueError:
        return None


def decode_rescued_total(rows: Any) -> int | None:
    """Sum the ``Rescued`` amounts.  ``None`` when the filter did not read.

    ``0`` is a real answer — the event has never fired on chain and may never —
    so an empty tuple sums to ``0`` while a ``None`` input stays ``None``.
    """
    if rows is None:
        return None
    total = 0
    for row in rows:
        topics = _topics(row)
        words = _data_words(row)
        if len(topics) < 2 or topics[0].lower() != A.TOPIC_RESCUED.lower():
            continue
        if not words:
            continue
        try:
            total += int(words[0], 16)
        except ValueError:
            continue
    return total


def decode_launched(row: Any) -> dict | None:
    """One ``Launched`` row → the seven immutables it announced.

    A **cross-check**, never the source: the ``once`` tier reads the same
    numbers off the contract's own getters, because a log is what the deployer
    said and a getter is what the contract will do.
    """
    topics = _topics(row)
    words = _data_words(row)
    if not topics or topics[0].lower() != A.TOPIC_LAUNCHED.lower():
        return None
    if len(words) < len(_LAUNCHED_DATA_WORDS):
        return None
    try:
        return {
            name: int(words[i], 16) for i, name in enumerate(_LAUNCHED_DATA_WORDS)
        }
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source groups — PRD §5's exact vocabulary, and the screen renders it verbatim
# ---------------------------------------------------------------------------

SOURCE_STATE = "state"
SOURCE_LOGS = "logs"
SOURCE_WALLET = "wallet"

#: Hand-typed rather than derived from ``CURATOR_DEGRADED_GROUPS`` on purpose
#: (CLAUDE.md's redundancy rule): the agreement is asserted by a test, and a
#: derivation would make that test compare a constant against itself.
SOURCES: tuple[str, ...] = (SOURCE_STATE, SOURCE_LOGS, SOURCE_WALLET)

#: group -> the cache slot holding its last-good payload.  ``config`` and
#: ``blockscout`` have slots of their own but no group: the immutables are part
#: of the *state* story the user is told, and Blockscout is a cross-check whose
#: absence degrades the ``logs`` group it checks.
GROUP_SLOT: dict[str, str] = {
    SOURCE_STATE: SLOT_STATE,
    SOURCE_LOGS: SLOT_LOGS,
    SOURCE_WALLET: SLOT_WALLET,
}


#: Exactly the ``READING_KEYS`` entries the fast tier produces.
#:
#: Note what is **absent**: the hour total and the last-active-hour pair.  Both
#: are on :class:`CuratorState`, both are read every 15 s, and neither is a
#: reading ``build_signals`` accepts — the hour history is folded from
#: ``Deposited`` logs alone (H2).  This tuple and
#: :data:`~maxpane_dashboard.data.curator_cache.SERIES_INPUT_KEYS` are asserted
#: disjoint, so the day someone "helpfully" feeds the live hour total into the
#: sparkline, a test says so before a user sees a 99.5% crash that never
#: happened.
FAST_TIER_PAYLOAD_KEYS: tuple[str, ...] = (
    "settled",
    "current_hour",
    "hour_needed_wei",
    "hour_seconds_left",
    "early_bps",
    "volume_wei",
    "contributors",
    "tx_count",
    "forced_balance_wei",
)

#: The five row keys whose emptiness is a claim about the chain rather than
#: about this install.  ``None`` = the source did not read; ``[]`` = it read and
#: found nothing.  The series keys are deliberately absent: they are this
#: cache's own history, and an empty one is a fact about the install.
#:
#: ``you_ladder_rows`` belongs here for the same reason as the other four and
#: for a sharper one: an empty ladder rendered as fact says *you have never
#: deposited* to somebody who has, which is the one claim on the wallet view a
#: reader would act on.
_SOURCE_BACKED_ROW_KEYS: tuple[str, ...] = (
    "leaderboard_rows",
    "activity_rows",
    "closest_call_rows",
    "cluster_rows",
    "you_ladder_rows",
)

#: The ``once`` tier's readings, straight off :class:`CuratorConfig`.
CONFIG_PAYLOAD_KEYS: tuple[str, ...] = (
    "launch_time",
    "grace_period",
    "hour_duration",
    "hourly_threshold_wei",
    "first_judged_hour",
    "points_per_eth",
    "credit_cap_wei",
)


NFT_FAILURE_BACKOFF_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class _NftScanRequest:
    collections: tuple[NftCollectionRef, ...]
    wallets: tuple[str, ...]
    fingerprint: str

    @property
    def key(self) -> tuple[tuple[str, ...], str]:
        return tuple(item.key for item in self.collections), self.fingerprint


@dataclass(frozen=True, slots=True)
class FilteredListResult:
    rows: list[dict] | None
    complete: bool
    source_reason: str | None
    holder_receipt: str | None = None
    routed_eth: float | None = None


class CuratorManager:
    """Fetches THE LIST across three source groups and returns a flat dict."""

    def __init__(
        self,
        poll_interval: int = 30,
        *,
        client: Any = None,
        cache: Any = None,
        wallet: str | None = None,
        clock: Any = time.time,
        cache_path: str = DEFAULT_CACHE_PATH,
        analysis_transport: Any = None,
        nft_client_factory: Callable[[], Any] = NftHolderClient,
    ) -> None:
        self._nft_client_factory = nft_client_factory
        self._nft_client: Any = None
        self._nft_collection_labels: dict[str, str] = {}
        self._nft_task: Any = None
        self._nft_running_request: _NftScanRequest | None = None
        self._nft_queued_request: _NftScanRequest | None = None
        self._nft_failed_until: dict[tuple[str, str], float] = {}
        self.poll_interval = poll_interval
        self._clock = clock
        self._cache_path = str(cache_path)
        #: The wallet the YOU row is about.  Read from the **constructor** —
        #: the app passes ``--wallet`` / ``MAXPANE_WALLET`` — never from the
        #: process environment in here, so a test drives it without patching
        #: anything and two managers in one process can watch two wallets.
        self.wallet = wallet or None
        self.client = client if client is not None else CuratorClient()
        self.cache = cache if cache is not None else CuratorCache(
            path=self._cache_path, clock=clock
        )

        self._cycle_count = 0
        self._error_count = 0
        #: Groups whose most recent *attempt* failed.  Cleared on success only,
        #: so a group that failed two cycles ago and is not due to retry yet
        #: stays reported as degraded rather than reading as healthy because its
        #: tier happens to be backed off.
        self._failed_groups: set[str] = set()
        #: True while the folded totals disagree with the contract's own
        #: counters — the slow tier's cross-check sets it and a repair sweep
        #: clears it.
        self._fold_stale = False
        #: Set by the cross-check when the fold looks short: the next medium
        #: tick re-sweeps from here instead of from the watermark.
        self._repair_from_block: int | None = None
        #: The newest fast-tier answers, re-served while that tier is still
        #: fresh.  This is **not** a last-good store and it is deliberately not
        #: the cache's: it is set on every *attempted* fast tick, to ``None``
        #: when the attempt failed, so it can never outlive the tier's own TTL.
        #: Serving a reading from twelve seconds ago is what a 15 s TTL means;
        #: serving one from across an outage is what PRD §11's row 1 forbids,
        #: and the two are kept apart by clearing these on failure.
        self._fast_state: Any = None
        self._fast_wallet: Any = None
        #: The detached slow-tier cross-check, or ``None`` when none is in
        #: flight.  See :meth:`_spawn_crosscheck` for why it is not awaited.
        self._crosscheck_task: Any = None
        #: The detached Tier-B+C analysis sweep, on the exact same pattern.
        self._analysis_task: Any = None
        #: True only while the most recent analysis sweep RAN and failed to
        #: publish.  "Could not run yet" (no events, no live-read config) is a
        #: different fact and never sets it — see :meth:`_pool_analysis`.
        self._analysis_failed = False
        #: Once-per-process marker for the missing-library log line.
        self._sybilkit_missing_logged = False
        #: The session the analysis sweep's published-analysis fetch may use.
        #: A test injects an ``httpx`` transport here; production leaves it
        #: ``None`` and the sweep borrows the client's own HTTP session.  With
        #: neither available the sweep cannot run and opens **nothing** —
        #: which is what keeps a bare test double socket-free.
        self._analysis_transport = analysis_transport

        try:
            self.cache.load()
        except Exception as exc:  # noqa: BLE001 — load is fail-soft; belt and braces
            logger.warning("Curator cache load failed: %s", exc)

    # -- lifecycle -----------------------------------------------------------

    def save_cache(self) -> None:
        try:
            self.cache.save()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator cache save failed: %s", exc)

    def _history_complete(self, fold: list[Any] | None = None) -> bool:
        """Whether the retained deposit history has no known lost rows."""
        rows = self.cache.fold_rows() if fold is None else fold
        return (
            self.cache.dropped_events == 0
            and len(rows) == len(self.cache.first_deposits())
        )

    def cached_list_rows_with_ens(self, rows) -> list[dict]:
        """Copy list rows and attach only fresh names already in the cache."""
        labelled = [dict(row) for row in rows if isinstance(row, Mapping)]
        known = self.cache.ens.names_fresh(
            ens.DEFAULT_TTL_SECONDS, float(self._clock())
        )
        for row in labelled:
            address = row.get("address")
            if isinstance(address, str):
                row["name"] = known.get(address.lower())
        return labelled

    def full_list_rows(self, *, cleaned: bool) -> list[dict] | None:
        """Return one complete export list from held data, without network I/O."""
        fold = self.cache.fold_rows()
        if not self._history_complete(fold):
            return None
        if cleaned:
            entry = self.cache.analysis_last_good()
            slot = (
                entry.payload
                if entry is not None and isinstance(entry.payload, Mapping)
                else None
            )
            if slot is None:
                return None
            expected = _opt_int(slot.get("clean_contributors"))
            if expected is None or expected < 0:
                return None
            rows = curator_clusters.clean_list_rows_from_fold(
                slot, fold, limit=None
            )
            if [row["clean_rank"] for row in rows] != list(
                range(1, expected + 1)
            ):
                return None
        else:
            if self._fold_stale or self.cache.get_last_good(SLOT_LOGS) is None:
                return None
            rows = project_leaderboard_rows(
                fold, cluster_members(self.cache.events()), limit=None
            )
            entry = self.cache.analysis_last_good()
            slot = (
                entry.payload
                if entry is not None and isinstance(entry.payload, Mapping)
                else None
            )
            curator_clusters.merge_leaderboard_grade(rows, slot)

        return self.cached_list_rows_with_ens(rows)

    def _filter_families(self) -> dict[str, frozenset[str]] | None:
        entry = self.cache.analysis_last_good()
        payload = entry.payload if entry is not None else None
        if not isinstance(payload, Mapping) or not isinstance(payload.get("groups"), list):
            return None
        found: dict[str, set[str]] = {}
        for group in payload["groups"]:
            if not isinstance(group, Mapping):
                continue
            families = {
                value for value in group.get("families", ())
                if isinstance(value, str) and value in FILTER_FAMILIES
            }
            for member in group.get("members", ()):
                if isinstance(member, str) and member.strip():
                    found.setdefault(member.casefold(), set()).update(families)
        return {address: frozenset(values) for address, values in found.items()}

    def _filter_whales(self, expected_count: Any) -> frozenset[str] | None:
        fold = self.cache.fold_rows()
        trusted_count = isinstance(expected_count, int) and not isinstance(expected_count, bool)
        if not trusted_count or len(fold) != expected_count or not self._history_complete(fold):
            return None
        floor_wei = int(WHALE_MIN_ETH * 10**18)
        return frozenset(
            event.contributor.casefold()
            for event in self.cache.events()
            if event.amount_wei >= floor_wei
        )

    async def resolve_nft_collection_name(
        self, collection: NftCollectionRef
    ) -> str:
        if collection.key in self._nft_collection_labels:
            return self._nft_collection_labels[collection.key]
        if self._nft_client is None:
            self._nft_client = self._nft_client_factory()
        name = await self._nft_client.collection_name(collection)
        label = parse_nft_collection(
            NftCollectionRef(
                collection.chain,
                collection.address,
                name or custom_nft_label(collection.chain, collection.address),
            )
        ).label
        self._nft_collection_labels[collection.key] = label
        return label

    def _queue_nft_scan(
        self,
        collections: tuple[NftCollectionRef, ...],
        wallets: tuple[str, ...],
        fingerprint: str,
    ) -> None:
        request = _NftScanRequest(collections, wallets, fingerprint)
        running = self._nft_task
        if running is not None and not running.done():
            if (
                self._nft_running_request is None
                or self._nft_running_request.key != request.key
            ):
                self._nft_queued_request = request
            return
        self._nft_task = asyncio.ensure_future(
            self._run_nft_scan_queue(request)
        )

    async def _run_nft_scan_queue(
        self, request: _NftScanRequest
    ) -> None:
        try:
            current: _NftScanRequest | None = request
            while current is not None:
                self._nft_running_request = current
                for collection in current.collections:
                    hit = self.cache.nft_holders(
                        collection.key, current.fingerprint
                    )
                    if hit is not None and hit.fresh:
                        continue
                    failure_key = (collection.key, current.fingerprint)
                    if self._nft_failed_until.get(failure_key, 0) > self._clock():
                        continue
                    if self._nft_client is None:
                        self._nft_client = self._nft_client_factory()
                    try:
                        scan = await self._nft_client.scan(
                            collection, current.wallets
                        )
                    except Exception as exc:  # source degradation boundary
                        logger.warning("NFT holder scan failed: %s", exc)
                        self._nft_failed_until[failure_key] = (
                            self._clock() + NFT_FAILURE_BACKOFF_SECONDS
                        )
                        continue
                    if (
                        not scan.complete
                        or scan.checked != len(current.wallets)
                    ):
                        self._nft_failed_until[failure_key] = (
                            self._clock() + NFT_FAILURE_BACKOFF_SECONDS
                        )
                        continue
                    self.cache.store_nft_holders(
                        collection.key,
                        wallet_fingerprint=current.fingerprint,
                        holders=scan.holders,
                        checked=scan.checked,
                        failed=scan.failed,
                        block_number=scan.block_number,
                        ts=self._clock(),
                    )
                    self._nft_failed_until.pop(failure_key, None)
                current = self._nft_queued_request
                self._nft_queued_request = None
        finally:
            self._nft_running_request = None
            self._nft_task = None

    def _nft_filter_context(
        self,
        spec: FilterSpec,
        rows: list[dict],
    ) -> tuple[dict[str, frozenset[str]] | None, str | None]:
        if not spec.nft_collections:
            return None, None
        wallets = tuple(sorted({
            row["address"].casefold()
            for row in rows
            if isinstance(row.get("address"), str)
            and len(row["address"]) == 42
            and row["address"].startswith(("0x", "0X"))
            and all(
                char in "0123456789abcdefABCDEF"
                for char in row["address"][2:]
            )
        }))
        fingerprint = wallet_universe_fingerprint(wallets)
        found: dict[str, frozenset[str]] = {}
        stale_stamps: list[float] = []
        missing: list[NftCollectionRef] = []
        refresh: list[NftCollectionRef] = []
        for collection in spec.nft_collections:
            hit = self.cache.nft_holders(collection.key, fingerprint)
            if hit is None:
                missing.append(collection)
                refresh.append(collection)
            else:
                found[collection.key] = hit.holders
                if not hit.fresh:
                    stale_stamps.append(hit.ts)
                    refresh.append(collection)
        refreshable = tuple(
            collection for collection in refresh
            if self._nft_failed_until.get(
                (collection.key, fingerprint), 0
            ) <= self._clock()
        )
        if refreshable:
            self._queue_nft_scan(refreshable, wallets, fingerprint)
        if missing:
            blocked = any(
                self._nft_failed_until.get(
                    (item.key, fingerprint), 0
                ) > self._clock()
                for item in missing
            )
            if blocked:
                raise NftHolderUnavailable("NFT holder data unavailable")
            raise NftHolderPending("NFT holder data loading")
        receipt = None
        if stale_stamps:
            oldest = min(stale_stamps)
            receipt = "NFT holders as of " + time.strftime(
                "%H:%M", time.localtime(oldest)
            )
        return found, receipt

    def filtered_list_rows(
        self,
        directory,
        *,
        expected_count,
        live_rows,
        you_row,
        spec: FilterSpec,
    ) -> FilteredListResult:
        source = load_export_list(
            Path(directory),
            cleaned=False,
            expected_count=expected_count,
            live_rows=live_rows,
            you_row=you_row,
        )
        if not isinstance(source.rows, list):
            return FilteredListResult(None, source.complete, source.reason)
        rows = self.cached_list_rows_with_ens(source.rows)
        nft_holders, holder_receipt = self._nft_filter_context(
            spec, rows
        )
        context = FilterContext(
            families_by_address=self._filter_families() if spec.families else None,
            whale_addresses=self._filter_whales(expected_count) if spec.whale else None,
            nft_holders_by_collection=nft_holders,
        )
        rows = filter_rows(rows, spec, context)
        return FilteredListResult(
            rows,
            source.complete,
            source.reason,
            holder_receipt,
            self._filtered_routed_eth(rows),
        )

    def _filtered_routed_eth(
        self, rows: list[dict] | None
    ) -> float | None:
        if rows is None or not self._history_complete():
            return None
        addresses = {
            address.casefold()
            for row in rows
            if isinstance(row, dict)
            and isinstance((address := row.get("address")), str)
            and len(address) == 42
            and address.startswith(("0x", "0X"))
            and all(char in "0123456789abcdefABCDEF" for char in address[2:])
        }
        total_wei = sum(
            event.amount_wei
            for event in self.cache.events()
            if event.contributor.casefold() in addresses
        )
        return total_wei / 10**18

    async def _cancel_nft_scan(self) -> None:
        task = self._nft_task
        self._nft_task = None
        self._nft_queued_request = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        """Stop both detached tasks, close the client, then persist the cache.

        Never raises.  In that order, and the save happens even when the close
        raises.  The detached cross-check holds the same client, so it is
        cancelled and awaited *first* -- closing sockets out from under a task
        that is still paging is how a clean quit turns into a traceback on the
        way down -- and the analysis sweep borrows the same session, so it is
        stopped right beside it for the same reason.  The client owns sockets
        and the cache owns a file; closing before saving means no in-flight
        response can still be folding rows into the structures the save is
        walking, and saving in a ``finally`` means a client that throws on the
        way out cannot cost the user the whole game's history.
        """
        await self._cancel_nft_scan()
        if self._nft_client is not None:
            try:
                await self._nft_client.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("closing NFT holder client failed: %s", exc)
        await self._cancel_crosscheck()
        await self._cancel_analysis()
        try:
            await self.client.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("closing the curator client failed: %s", exc)
        finally:
            self.save_cache()

    # -- guarded calls and degradation ---------------------------------------

    async def _guard(self, call: Any, name: str) -> Any:
        """Await ``call()``; a raise becomes ``None``, logged, never escaping.

        The clients document ``None`` on failure, so a raise here is a bug in
        the client or a transport surprise — either way it costs one source
        group's reading, not the refresh cycle.
        """
        try:
            return await call()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Curator %s raised: %s", name, exc)
            return None

    def _note(self, group: str, ok: bool) -> None:
        """Record this cycle's attempt for ``group``.  Unknown names are refused.

        A group name that is not in :data:`SOURCES` would reach the title bar
        verbatim, so it is a programming error rather than a display quirk.
        """
        if group not in SOURCES:
            raise ValueError(
                f"unknown curator source group {group!r}; expected one of {SOURCES}"
            )
        if ok:
            self._failed_groups.discard(group)
        else:
            self._failed_groups.add(group)
            self._error_count += 1

    # -- the fast tier: state + the forced-ETH anomaly (H1, H5) --------------

    async def _pool_state(self, now: float) -> dict[str, Any]:
        """One batched ``eth_call`` round and one ``eth_getBalance``.  Never raises.

        Exactly two requests per fast tick: the eight views travel in a single
        JSON-RPC batch (with ``eth_blockNumber`` as its last entry, so the
        readings and the height describe the same block) and the balance is a
        second call on purpose — it is a **bare int** on the client, so nothing
        can reach it by reading a state object and mistake it for a deposit.

        The balance is **always forced ETH** (H5).  Every wei of a deposit is
        refunded inside the same transaction, so a non-zero balance is an
        anomaly — somebody ``selfdestruct``-ed ETH into the contract — and it
        feeds ``forced_eth`` alone.  It is never a volume, a TVL or a hero
        total, and ``0`` is the *healthy* answer.

        ``settled`` goes to the latch and nowhere else this tier can write.
        **No series is touched here**: :data:`FAST_TIER_PAYLOAD_KEYS` and the
        cache's ``SERIES_INPUT_KEYS`` are disjoint by test (H2).
        """
        state, balance = await asyncio.gather(
            self._guard(self.client.fetch_state, "fetch_state"),
            self._guard(self.client.fetch_balance, "fetch_balance"),
        )
        if state is not None:
            state = dataclasses.replace(state, forced_balance_wei=_opt_int(balance))
            # The one-way latch (H1).  A False or None observation cannot clear
            # a True one, so this is safe to call every tick.
            self.cache.observe_settlement(
                getattr(state, "settled", None),
                block_number=_opt_int(getattr(state, "block_number", None)),
                now=now,
            )

        ok = state is not None and balance is not None
        if ok:
            self.cache.store_last_good(SLOT_STATE, self._state_payload(state), ts=now)
            self.cache.mark_fetched(TIER_FAST, now)
        else:
            # A half-failure keeps whatever did come back for *this* payload but
            # must not overwrite the last-good with a half-empty round, and must
            # not restart the TTL as though the tier were healthy.
            self.cache.mark_failed(TIER_FAST, now)
        self._note(SOURCE_STATE, ok)
        return {"state": state, "ok": ok}

    @staticmethod
    def _state_payload(state: Any) -> dict[str, Any]:
        """``FAST_TIER_PAYLOAD_KEYS`` off one :class:`CuratorState`.

        Field for field, no derivation and no division: the model is wei-native
        and ``build_signals`` is the presentation boundary.
        """
        return {key: getattr(state, key, None) for key in FAST_TIER_PAYLOAD_KEYS}

    async def _pool_config(self, tiers: set[str], now: float) -> dict[str, Any] | None:
        """The ``once`` tier: the eight immutables plus ``POINTS_PER_ETH``.

        Read **live** and never hardcoded (CLAUDE.md), even though
        ``curator_addresses`` pins the same numbers — the pins exist so a test
        can prove the live read agrees, not so the dashboard can skip it.
        Nothing on this contract can change them, so one success is final; a
        *failure* still comes due again after the tier's backoff.
        """
        cached = self.cache.get_last_good(SLOT_CONFIG)
        if TIER_ONCE not in tiers:
            return cached.payload if cached is not None else None
        config = await self._guard(self.client.fetch_config, "fetch_config")
        if config is None:
            self.cache.mark_failed(TIER_ONCE, now)
            self._note(SOURCE_STATE, False)
            return cached.payload if cached is not None else None
        payload = {key: getattr(config, key, None) for key in CONFIG_PAYLOAD_KEYS}
        # One extra live read rides the slot WITHOUT joining the readings:
        # `CONFIG_PAYLOAD_KEYS` mirrors the frozen `READING_KEYS` one for one,
        # and `build_signals` has no use for the minimum -- but the analysis
        # sweep's preset refuses to exist without it (ruling R13: everyone
        # sends the minimum, so the minimum identifies nobody).  `_readings`
        # iterates `CONFIG_PAYLOAD_KEYS`, so this key never reaches it.
        payload["min_deposit_wei"] = _opt_int(
            getattr(config, "min_deposit_wei", None)
        )
        self.cache.store_last_good(SLOT_CONFIG, payload, ts=now)
        self.cache.mark_fetched(TIER_ONCE, now)
        return payload

    # -- the fast tier, second half: the YOU views ---------------------------

    async def _pool_wallet(self, now: float) -> Any:
        """The six argument-taking views, and **only** when a wallet is set.

        With no wallet configured this makes **zero** requests and returns
        ``None``: every ``you_*`` key is then ``None`` because there is nobody
        to ask about, which is a different fact from a source being down and is
        reported differently (:meth:`_degraded` never names ``wallet`` in that
        case).

        An address that cannot be one is rejected **here**, before any request:
        sending garbage to a public node to be told what we could have checked
        locally is both rude and slow, and the failure is reported as a wallet
        degradation rather than an outage.

        A wallet that is not on the list is a **successful** read, not a
        failure: the contract answers ``minDeposit`` for a stranger, which is
        exactly the number that wallet needs and the most useful thing on the
        row.
        """
        if not self.wallet:
            return None
        if not _looks_like_address(self.wallet):
            logger.warning(
                "Curator wallet %r is not an address; the YOU row is unavailable "
                "and nothing was sent to the node",
                self.wallet,
            )
            self._note(SOURCE_WALLET, False)
            return None
        state = await self._guard(
            lambda: self.client.fetch_wallet(self.wallet), "fetch_wallet"
        )
        ok = state is not None and not getattr(self.client, "wallet_failed", False)
        if ok:
            self.cache.store_last_good(SLOT_WALLET, {"address": self.wallet}, ts=now)
        self._note(SOURCE_WALLET, ok)
        return state

    # -- the medium tier: the log sweep and the fold -------------------------

    def _sweep_from_block(self) -> int:
        """Where the next sweep starts.

        A deposit-loss marker wins, then a repair range, the watermark + 1, and
        finally the creation block. A cache with known loss cannot repair
        itself incrementally because the missing rows may predate its watermark.
        **Never the head**: an absent watermark means "we have never folded
        anything", and starting from now would leave the whole game unfolded
        behind an empty leaderboard with no error anywhere.  The full backfill
        is one sweep in practice — 377 rows from block 25 769 870, validated in
        the research.
        """
        if self.cache.dropped_events > 0:
            return A.CREATION_BLOCK
        if self._repair_from_block is not None:
            return max(A.CREATION_BLOCK, self._repair_from_block)
        watermark = self.cache.last_seen_block()
        if watermark is None:
            return A.CREATION_BLOCK
        return max(A.CREATION_BLOCK, watermark + 1)

    def _log_group_failed(self) -> dict[str, bool]:
        """The client's per-filter failure dict, defensively.

        ``LogSweep``'s ``()`` is ambiguous — "read, nothing matched" or "this
        filter died" — and only this dict tells them apart.  A double that does
        not define it is treated as "nothing failed", which is what a client
        that cannot report partial failure is in fact claiming.
        """
        flags = getattr(self.client, "log_group_failed", None)
        if not isinstance(flags, dict):
            return dict.fromkeys(LOG_GROUPS, False)
        return {group: bool(flags.get(group)) for group in LOG_GROUPS}

    def _logs_read_groups(self) -> set[str]:
        """Which log groups have ever been read successfully, across restarts.

        This is what separates ``[]`` from ``None`` for a group whose history is
        legitimately empty: ``HourSaved`` and ``Rescued`` have never fired on
        chain, so "read it, found nothing" is the *expected* answer and must not
        render as an outage — while a group nobody has ever managed to read must
        not render as an empty game.
        """
        entry = self.cache.get_last_good(SLOT_LOGS)
        payload = entry.payload if entry is not None else None
        groups = payload.get("groups_read") if isinstance(payload, dict) else None
        return {g for g in groups if g in LOG_GROUPS} if isinstance(groups, list) else set()

    async def _pool_logs(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Sweep, decode, fold and persist.  Never raises.

        Incremental by design: after the first backfill the client only hands
        back rows newer than the watermark, so the cache is the only place the
        rest of the game exists.  The watermark advances **only** on a
        successful sweep — advancing it on a failure would skip that range
        forever, and the leaderboard would be permanently wrong with no symptom.
        """
        if TIER_MEDIUM not in tiers:
            return {"ok": None, "swept": False}

        from_block = self._sweep_from_block()
        previous_watermark = self.cache.last_seen_block()
        repairing_history = (
            self.cache.dropped_events > 0 and from_block == A.CREATION_BLOCK
        )
        sweep = await self._guard(
            lambda: self.client.fetch_logs(from_block), "fetch_logs"
        )
        if sweep is None:
            self.cache.mark_failed(TIER_MEDIUM, now)
            self._note(SOURCE_LOGS, False)
            return {"ok": False, "swept": True, "from_block": from_block}

        failed = self._log_group_failed()
        decoded = [decode_deposit(row) for row in getattr(sweep, "deposits", ())]
        events = [event for event in decoded if event is not None]
        decode_loss = len(decoded) - len(events)
        if decode_loss:
            logger.warning(
                "Curator sweep: %d of %d Deposited row(s) did not decode and were "
                "dropped rather than zeroed",
                decode_loss,
                len(decoded),
            )
            if not repairing_history:
                self.cache.dropped_events += decode_loss
        self.cache.store_events(events, now=now)

        firsts = [decode_first_deposit(row) for row in getattr(sweep, "first_deposits", ())]
        self.cache.store_first_deposits([row for row in firsts if row is not None])
        saved = [decode_hour_saved(row) for row in getattr(sweep, "hour_saved", ())]
        self.cache.store_hour_saved([row for row in saved if row is not None])
        if not failed["rescued"]:
            self.cache.store_rescued_total(
                decode_rescued_total(getattr(sweep, "rescued", ()))
            )
        for row in getattr(sweep, "settled", ()):
            obituary = decode_settled(row)
            if obituary is not None:
                # The obituary only. The verdict is the view's, and the latch
                # refuses to be created by a log (H1).
                self.cache.record_settled_event(
                    hour=obituary["hour"],
                    ts=obituary["ts"],
                    contributors=obituary["total_contributors"],
                    volume_wei=obituary["total_volume_wei"],
                )

        # The watermark is where the *next* sweep starts, so it may only move
        # over a range every filter actually covered.  A sweep in which one
        # topic filter died read that range for five groups and not for the
        # sixth, and advancing past it would skip the sixth's rows **forever** —
        # ``store_fold``'s own contract, and the failure the gap-repair tier
        # exists because of.  ``last_block=None`` is its documented "rows in,
        # watermark unchanged" combination: what arrived is kept, and the range
        # is swept again next tick.
        covered = not any(failed.values()) and decode_loss == 0
        sweep_to_block = _opt_int(getattr(sweep, "to_block", None))
        if any(failed.values()):
            logger.warning(
                "Curator sweep from block %d had a dead filter (%s); the rows it "
                "did return are folded but the watermark stays put so the range "
                "is re-read rather than skipped",
                from_block,
                ", ".join(sorted(g for g, dead in failed.items() if dead)),
            )
        elif decode_loss:
            logger.warning(
                "Curator sweep from block %d had undecodable Deposited rows; "
                "valid rows are folded but the watermark stays put so the "
                "history is repaired from creation",
                from_block,
            )
        self._refold(
            config,
            last_block=sweep_to_block if covered else None,
            now=now,
        )

        repair_covers_watermark = (
            previous_watermark is None
            or (
                sweep_to_block is not None
                and sweep_to_block >= previous_watermark
            )
        )
        if repairing_history and covered and repair_covers_watermark:
            repaired = self.cache.dropped_events
            self.cache.dropped_events = 0
            logger.info(
                "Curator history repair restored the creation-block sweep; "
                "cleared the marker for %d lost event(s)",
                repaired,
            )

        groups_read = self._logs_read_groups() | {
            group for group, dead in failed.items() if not dead
        }
        self.cache.store_last_good(
            SLOT_LOGS,
            {
                "groups_read": sorted(groups_read),
                "events": len(self.cache.events()),
                "last_block": self.cache.last_seen_block(),
            },
            ts=now,
        )
        self.cache.mark_fetched(TIER_MEDIUM, now)
        # A partial sweep is still a sweep: the rows that arrived are folded and
        # persisted, and the groups that died reach the user through `degraded`
        # rather than through a silently empty table.
        self._note(SOURCE_LOGS, covered)
        if self._repair_from_block is not None:
            logger.info(
                "Curator gap repair swept from block %d and completed", from_block
            )
            self._repair_from_block = None
            self._fold_stale = False
        return {
            "ok": True,
            "swept": True,
            "from_block": from_block,
            "sweep": sweep,
            "failed": failed,
        }

    def _refold(
        self, config: dict[str, Any] | None, *, last_block: int | None, now: float
    ) -> None:
        """Re-run the pure folds over the whole persisted history.

        Every fold is a pure function of the events, so this is idempotent and
        the cheapest correct thing: a sweep that recovers a missed range simply
        produces the right answer next cycle instead of patching a running
        total.  The analytics calls go through ``_safe_call`` so a fold bug costs
        one number rather than the cycle.
        """
        cfg = config or {}
        events = self.cache.events()
        # ``default=None`` rather than ``[]``: a fold that *raised* is not a fold
        # that found nobody.  Handing ``[]`` on to ``store_fold`` would blank the
        # leaderboard, advance the watermark past the range that produced it and
        # — before the curve below was written per hour — launder the failure
        # into a literal ``0`` in a *persisted* series, which is the one thing
        # the house rule forbids outright.
        rows = _safe_call(
            fold_deposits,
            events,
            self.cache.first_deposits(),
            points_per_eth=cfg.get("points_per_eth"),
            default=None,
        )
        if rows is None:
            logger.warning(
                "Curator fold over %d event(s) failed; keeping the previous table "
                "and the watermark rather than publishing an empty one",
                len(events),
            )
        else:
            self.cache.store_fold(rows, last_block=last_block, now=now)

        buckets = _safe_call(
            hourly_buckets,
            events,
            launch_time=cfg.get("launch_time"),
            hour_duration=cfg.get("hour_duration"),
            first_judged_hour=cfg.get("first_judged_hour"),
            hourly_threshold_wei=cfg.get("hourly_threshold_wei"),
            default=[],
        )
        # Without the launch anchor a bucket has no wall clock, so there is
        # nothing honest to plot: the series waits for the `once` tier rather
        # than inventing a timeline.
        #
        # Both curves are written **per bucket**, walking the dense hourly fold
        # in order and accumulating the joiners of each hour — the same running
        # sum ``build_signals`` computes, so the persisted history and the
        # freshly computed one are the same curve rather than one point of it.
        # Stamping a single cumulative total at the newest bucket produced a
        # one-point series, and a sparkline with one point renders
        # "waiting for data..." forever however long the game has run.
        joined_by_hour: dict[int, int] = {}
        for row in rows or ():
            first_hour = getattr(row, "first_hour", None)
            if first_hour is not None:
                joined_by_hour[first_hour] = joined_by_hour.get(first_hour, 0) + 1
        pairs = []
        joined: list[tuple[float, int]] = []
        running = 0
        for bucket in buckets or ():
            running += joined_by_hour.get(bucket.hour, 0)
            stamp = _safe_call(
                bucket_start_ts,
                bucket.hour,
                cfg.get("launch_time"),
                cfg.get("hour_duration"),
            )
            if stamp is not None:
                pairs.append([stamp, bucket.volume_wei])
                joined.append((stamp, running))
        if pairs:
            self.cache.record_hour_buckets(pairs, now=now)
        # Only a fold that actually ran may write the contributor curve: a
        # failed one has no count, and ``0`` is not the count of a failure.
        if rows is not None:
            for stamp, total in joined:
                self.cache.record_contributor_count(total, ts=stamp, now=now)

    # -- the slow tier: the independent cross-check and gap repair -----------

    def _spawn_crosscheck(
        self, tiers: set[str], now: float, state: Any, config: dict[str, Any] | None
    ) -> Any:
        """Start the cross-check **detached**; never wait for it.

        Awaiting it inside the cycle put the whole dashboard behind a read of
        the contract's *entire* log history, on every launch and on every slow
        tick.  Measured through the real app: first payload after **201.2 s**,
        of which ``fetch_blockscout_logs`` was 202.6 of 203.8 s in cycle 0
        while the next cycle took 0.8 s.  The fold that drives every panel was
        ready in under a second and the reader watched an empty SIGNALS rail --
        the doomsday clock this dashboard exists for -- for three and a half
        minutes.  Blockscout pages 50 logs at a time and the contract is past
        19 500 of them and climbing, so the wait grows with the game and the
        slow tier's own 420 s period does not.

        Nothing downstream needs the answer *this* cycle.  The cross-check
        publishes no key: it either agrees with the fold or schedules a repair
        sweep by setting ``_repair_from_block``, which the next medium tick
        reads.  Skipping it entirely is already a supported, tested state
        (``{"ok": None, "checked": False}``), so a payload built before it
        lands is a payload this manager was always allowed to produce.

        One at a time.  While a sweep is in flight the slow tier stays *due*
        (only the call itself marks it), so every cycle offers again and the
        guard here is what keeps a 200-second read from stacking up thirty
        deep behind a 30-second poll.

        ``now`` is the spawn time, deliberately: it stamps the last-good slot
        and therefore the ``as of HH:MM`` marker, and a marker that claims the
        *end* of a three-minute read is a marker claiming data is fresher than
        it is.

        **What this does not fix.**  The sweep still costs O(whole history)
        every slow tick, and the history grows while :data:`TIER_SLOW`'s 420 s
        period does not — at the launch-week rate the two cross over within a
        day, after which the guard above simply runs one sweep after another in
        the background.  That is bandwidth, not latency, and no reader waits on
        it; a cross-check that pages only down to a persisted verified-to-block
        watermark is the real answer and is PRD §12 material, not v1.
        """
        if TIER_SLOW not in tiers:
            return None
        running = self._crosscheck_task
        if running is not None and not running.done():
            logger.debug("Curator cross-check still in flight; not starting another")
            return running
        self._crosscheck_task = asyncio.ensure_future(
            self._crosscheck_detached(tiers, now, state, config)
        )
        return self._crosscheck_task

    async def _crosscheck_detached(
        self, tiers: set[str], now: float, state: Any, config: dict[str, Any] | None
    ) -> None:
        """:meth:`_pool_crosscheck` with nobody to raise at.

        A detached task's exception surfaces at garbage-collection time as an
        "exception was never retrieved" line and never as a degraded source,
        so it is caught here.  ``CancelledError`` is re-raised: that one is
        :meth:`close` doing its job.
        """
        try:
            await self._pool_crosscheck(tiers, now, state, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            logger.warning("Curator cross-check failed: %s", exc)

    async def _cancel_crosscheck(self) -> None:
        """Stop an in-flight cross-check and wait for it to actually be gone."""
        task = self._crosscheck_task
        self._crosscheck_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            logger.debug("curator cross-check stopped on close: %s", exc)

    async def _pool_crosscheck(
        self, tiers: set[str], now: float, state: Any, config: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Diff the fold against an independent source and the contract's counters.

        Two checks, both of which end in *re-sweep*, never in a quietly wrong
        number:

        * **Blockscout** serves the same logs over a different transport.  Any
          ``Deposited`` row it has that the fold does not is a gap, and the
          oldest such block is where the repair sweep starts.
        * **``stats()``** is the contract's own deposit counter.  It is only
          comparable when the fold covers the block the counter was read at —
          the two are read seconds apart on *different endpoint pools*, so a
          fold that is merely younger is not a fold that is short.
        """
        if TIER_SLOW not in tiers:
            return {"ok": None, "checked": False}

        rows = await self._guard(
            self.client.fetch_blockscout_logs, "fetch_blockscout_logs"
        )
        gap_block: int | None = None
        if rows is None:
            # The cross-check is unavailable, which is not the same as the logs
            # being unavailable: the fold still stands on the RPC sweep.
            self.cache.mark_failed(TIER_SLOW, now)
        else:
            known = {
                (event.tx_hash.lower(), event.log_index)
                for event in self.cache.events()
            }
            watermark = self.cache.last_seen_block()
            for row in rows:
                event = decode_deposit(row)
                if event is None:
                    continue
                if (event.tx_hash.lower(), event.log_index) in known:
                    continue
                if watermark is None or event.block_number > watermark:
                    # Newer than anything we have swept is not a gap: the two
                    # sources are read minutes apart and Blockscout is often
                    # ahead. Only a row *inside* the range we claim to have
                    # folded is evidence that we missed something.
                    continue
                gap_block = (
                    event.block_number
                    if gap_block is None
                    else min(gap_block, event.block_number)
                )
            self.cache.store_last_good(
                SLOT_BLOCKSCOUT, {"rows": len(rows), "gap_block": gap_block}, ts=now
            )
            self.cache.mark_fetched(TIER_SLOW, now)

        counter = _opt_int(getattr(state, "tx_count", None))
        state_block = _opt_int(getattr(state, "block_number", None))
        watermark = self.cache.last_seen_block()
        covered = (
            counter is not None
            and state_block is not None
            and watermark is not None
            and watermark >= state_block
        )
        seen = len(self.cache.events())
        if covered and seen < counter:
            logger.warning(
                "Curator fold is short: %d folded deposits against the "
                "contract's own %d at block %s — re-sweeping",
                seen,
                counter,
                state_block,
            )
            gap_block = A.CREATION_BLOCK if gap_block is None else min(
                gap_block, A.CREATION_BLOCK
            )

        if gap_block is not None:
            # Publish the shortfall rather than the number: the fold is stale
            # until the repair sweep lands, and `degraded` is how the user is
            # told.
            self._fold_stale = True
            self._repair_from_block = gap_block
            self._note(SOURCE_LOGS, False)
            # The repair runs on the next medium tick, so bring it forward.
            self.cache.mark_failed(TIER_MEDIUM, now, retry_after=0.0)
        return {"ok": rows is not None, "checked": True, "gap_block": gap_block}

    # -- the analysis tier: the detached Tier-B+C sweep (WP3) ----------------

    def _spawn_analysis(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> Any:
        """Start the analysis sweep **detached**; never wait for it.

        :meth:`_spawn_crosscheck`'s pattern, verbatim, for the same measured
        reason: a full tier-C funding pass is minutes long (~200 lookups at
        Blockscout's ~3 req/s per sweep, and that is the *bounded* version),
        and awaiting it in-cycle would put the doomsday clock behind it.
        Nothing downstream needs the answer this cycle: the sweep publishes
        into ``SLOT_CLUSTERS`` and the **next** cycle's merge reads it; a
        payload built before it lands is the already-supported "analysis not
        yet run" state.

        One at a time: while a sweep is in flight the analysis tier stays due
        (only :meth:`_pool_analysis` marks it), so every cycle offers again
        and the guard here is what keeps a minutes-long read from stacking up
        behind a 30-second poll.  ``now`` is the spawn time and stamps the
        slot — a marker taken at the end of a long read claims the data is
        fresher than it is.
        """
        if TIER_ANALYSIS not in tiers:
            return None
        running = self._analysis_task
        if running is not None and not running.done():
            logger.debug("Curator analysis sweep still in flight; not starting another")
            return running
        self._analysis_task = asyncio.ensure_future(
            self._analysis_detached(tiers, now, config)
        )
        return self._analysis_task

    async def _analysis_detached(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> None:
        """:meth:`_pool_analysis` with nobody to raise at.

        Same shape as :meth:`_crosscheck_detached`: a detached task's
        exception surfaces as an "exception was never retrieved" line at GC
        time and never as a degraded source, so it is caught here.  A sweep
        that RAN and failed marks its tier failed (backoff) and sets
        ``_analysis_failed`` — which lights the ``logs`` banner **only while
        there is no analysis last-good to serve** (see :meth:`_degraded`).
        ``CancelledError`` is re-raised: that one is :meth:`close` working.
        """
        try:
            await self._pool_analysis(tiers, now, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            self._analysis_failed = True
            # Completion time, not spawn time (M4): a sweep that took 200 s to
            # die must not have those 200 s deducted from its retry spacing.
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            logger.warning("Curator analysis sweep failed: %s", exc)

    async def _cancel_analysis(self) -> None:
        """Stop an in-flight analysis sweep and wait for it to be gone."""
        task = self._analysis_task
        self._analysis_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            logger.debug("curator analysis sweep stopped on close: %s", exc)

    def _analysis_session(self) -> tuple[Any, Any]:
        """``(client, transport)`` the published-analysis read may use.

        An injected transport wins (tests); otherwise the real client's own
        ``httpx`` session is borrowed (production — ``_client`` is the
        attribute every ``OwnedHttpClient`` subclass carries, and the sweep is
        cancelled in :meth:`close` *before* that session closes).  A double
        with neither means the sweep fetches nothing and runs tier A only —
        no test can open a socket by forgetting to inject.
        """
        if self._analysis_transport is not None:
            return None, self._analysis_transport
        return getattr(self.client, "_client", None), None

    async def _pool_analysis(
        self, tiers: set[str], now: float, config: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Read THE LIST's **published** analysis and publish it as a last-good.

        The producer changed and nothing else did: the tier, the slot, the
        detached spawn, the freshness marker and every degradation rule are the
        ones :meth:`_spawn_analysis` and :meth:`_degraded` already describe.
        What this method does now is check a version and, only if it moved,
        fetch the analysis, rebuild it over the LOCAL fold, store it and
        archive what it supersedes.

        **The order is the design.**

        1. the tier gates it, as before;
        2. no ``sybilkit`` is the cannot-run state — the *reconstruction* still
           needs the library even though the verdicts no longer do;
        3. no events, or no live-read rate/minimum, is the same cannot-run
           state, for the same reason it always was;
        4. no session is cannot-run too (see :meth:`_analysis_session`): a
           double with neither a client nor a transport was never able to open
           anything, so nothing was asked and nothing is degraded;
        5. the version check.  ``None`` is a **failed** read — a source was
           asked and did not answer — so the tier backs off and the held
           payload is left exactly as it is;
        6. **the same ``version_id`` AND the same ``content_hash`` end the
           tick.**  A published version is immutable and content-addressed, so
           this is the whole cost story: ~1 KB per tick instead of the live
           export's 8.3 MB.  Both halves are load-bearing — the publisher
           rebuilds under one id, and an id-only comparison would serve
           superseded rows until the id itself changed;
        7. the two bulk reads, which land together or not at all;
        8. the rebuild, in a worker thread: the pure folds measured 0.1 s but
           ``Dataset.from_events`` took 0.5 s over 28,353 events, and the TUI's
           event loop must wear neither;
        9. the archive, in its own thread and its own ``try`` — housekeeping
           that moves megabytes and must never fail the load;
        10. **one** store, from a complete pair, carrying the analysis and its
            provenance together.

        Step 9 runs BEFORE step 10 rather than after it, which inverts the
        plan's sketch, and the reason is step 10's own rule.  The slot has to
        record ``published.archived_version`` — the
        :func:`curator_archive.archive_key` that stops the module re-archiving
        an analysis it has already archived, on a run where the files it would
        move are the ones the previous run just wrote.  The key is not knowable
        until the archive has answered, so recording it after a store means a
        *second* store, and "the slot is written once, from a complete pair" is
        the stronger rule.

        What the sketched ordering was protecting — a failed archive must not
        cost the analysis — is kept by the ``try``: whatever the archive does,
        the store below runs.
        """
        if TIER_ANALYSIS not in tiers:
            return {"ok": None, "swept": False}
        if not curator_clusters.SYBILKIT_AVAILABLE:
            # The guarded-import compatibility story: an older install or a
            # partial environment cannot rebuild the published membership into
            # sybilkit objects, so absence is the cannot-run state — spaced
            # retry, no banner, the analysis keys in their honest not-yet-run
            # None.  Checked BEFORE the version request so a machine without
            # the library never spends one.
            if not self._sybilkit_missing_logged:
                self._sybilkit_missing_logged = True
                logger.info(
                    "sybilkit is not installed; the linked-wallet analysis "
                    "panels stay in their unavailable state"
                )
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            return {"ok": None, "swept": False}
        cfg = config if isinstance(config, dict) else {}
        events = self.cache.events()
        rate = _opt_int(cfg.get("points_per_eth"))
        minimum = _opt_int(cfg.get("min_deposit_wei"))
        if not events or rate is None or rate <= 0 or minimum is None:
            # Completion-time stamp (M4): the retry clock must not have the
            # sweep's own duration deducted from it.  Freshness stamps stay
            # spawn-time — only failures are stamped at completion.
            # Deliberately does NOT clear `_analysis_failed`: a failed sweep
            # followed by a cannot-run one keeps its banner state.
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            return {"ok": None, "swept": False}

        client, transport = self._analysis_session()
        if client is None and transport is None:
            # Not a dead source: nothing was asked.  In production
            # `_analysis_session` always borrows the real client's own
            # session, so this is the bare-double state — and treating it as a
            # failure would light `logs` for a test that simply never wired a
            # transport, which is the opposite of what a degradation means.
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            return {"ok": None, "swept": False}

        version = await curator_published.fetch_published_version(
            client=client, transport=transport
        )
        if (
            version is None
            or _str_or_none(version.version_id) is None
            or _str_or_none(version.content_hash) is None
        ):
            # An id or a hash that is not a string is a FAILED read, not a
            # version.  It could never match the held block, so every tick
            # would re-download the whole export; and the two together name a
            # directory under `<root>/archive/`, which `archive_key` would
            # refuse anyway.  Refused here, once, rather than degrading twice.

            self._analysis_failed = True
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            return {"ok": False, "swept": True}

        entry = self.cache.analysis_last_good()
        held = (
            entry.payload
            if entry is not None and isinstance(entry.payload, Mapping)
            else None
        )
        if _is_same_published(held, version):
            # Nothing to download.  The tier restarts on its SUCCESS clock and
            # the held payload keeps its own stamp: it IS the current analysis,
            # and re-storing it to move a marker would be the second write this
            # method exists not to make.
            self._analysis_failed = False
            self.cache.mark_fetched(TIER_ANALYSIS, now)
            return {"ok": True, "swept": False}

        analysis = await curator_published.fetch_published_analysis(
            version, client=client, transport=transport
        )
        if analysis is None:
            # Either bulk read missing means no pair, and half a pair is not a
            # payload: the held rows stay exactly where they are.
            self._analysis_failed = True
            self.cache.mark_failed(TIER_ANALYSIS, float(self._clock()))
            return {"ok": False, "swept": True}

        preset = curator_clusters.build_preset(rate, minimum)
        firsts = self.cache.first_deposits()
        result = await asyncio.to_thread(
            lambda: curator_clusters.build_analysis_from_published(
                events,
                firsts,
                clusters=analysis.clusters,
                rows=analysis.rows,
                totals=analysis.totals,
                wallet=self.wallet,
                config=preset,
            )
        )

        archived_version = await self._archive_published(
            version, rows=analysis.rows, result=result, previous_slot=held
        )
        self.cache.store_analysis(
            curator_clusters.slot_payload(
                result,
                published=_published_block(
                    version, fetched_at=now, archived_version=archived_version
                ),
            ),
            ts=now,
        )
        self.cache.mark_fetched(TIER_ANALYSIS, now)
        self._analysis_failed = False
        return {"ok": True, "swept": True}

    async def _archive_published(
        self,
        version: PublishedVersion,
        *,
        rows: Any,
        result: Any,
        previous_slot: Any,
    ) -> str | None:
        """Move the superseded exports aside; return the key to record.

        The key is :func:`curator_archive.archive_key` — the version id **and**
        the content hash — and it is deliberately the same compound identity
        :func:`_is_same_published` uses here.  This method is the only place
        the two meet, so it is the only place they could disagree: while the
        archive keyed on the id alone, a republish under one id re-fetched and
        re-stored the analysis while the archive said "already done", leaving
        the record view serving the previous build's rows at ``complete=True``.

        ``None`` means "do not record this analysis as archived", and it is
        returned for **every** outcome that is not a clean pair on disk:

        * the module raised (it says it never does; a caller that trusts that
          is one release away from being wrong);
        * ``failed`` names either published list.  A mid-archive ``OSError``
          can leave ``root`` holding the OLD cleaned list beside the NEW raw
          one, both answering ``complete=True`` to ``load_export_list`` — a
          stale list presented as current, which is the one thing this
          dashboard may never do.  :func:`curator_archive.archive_and_write`
          cannot unwind that safely, so it reports and the caller decides.

        ``failed`` naming anything else — a manifest, an already-archived old
        export — is not a split pair and does not cost the analysis its flag.

        **The flag records a fact; it does not schedule a retry**, and no
        retry is attempted.  Once the store below records this version and its
        hash, every later tick short-circuits on them and never reaches this
        method again for this analysis.  That is deliberate: the only way to
        come back would be to make the cheap path depend on the flag, which
        would re-download the whole export every 1,800 s for as long as the
        condition lasted — and after a mid-archive failure the retry is futile
        anyway, because ``root`` then holds one new list whose counterpart is
        already in the archive directory, which is exactly the state
        ``_pair_blocked`` refuses.  What actually happens is the repo's
        designed unavailable state: with an export missing or unreadable,
        ``load_export_list`` falls back to the capped live rows at
        ``complete=False`` behind its own marker, until a new published
        version arrives and archives cleanly.

        The whole call runs in a worker thread: on the live install it moves
        7.3 MB and writes ~8 MB of JSON, and the TUI's event loop is not the
        place for that.  ``root`` is the cache's own directory, which is the
        directory the record view exports into and reads from; nothing here
        computes a home directory of its own.
        """
        root = Path(self.cache.path).parent
        archived_at = float(self._clock())
        key = curator_archive.archive_key(version.version_id, version.content_hash)
        try:
            outcome = await asyncio.to_thread(
                lambda: curator_archive.archive_and_write(
                    root,
                    version_id=version.version_id,
                    content_hash=version.content_hash,
                    rows=rows,
                    # Folded in here rather than passed in: it is one pass over
                    # every analysed address (19,522 on the live population) and
                    # it belongs on the same thread as the write it feeds.
                    bands=curator_clusters.bands_by_address(result),
                    previous_slot=previous_slot,
                    now=archived_at,
                )
            )
        except Exception as exc:  # noqa: BLE001 — housekeeping never fails a load
            logger.warning(
                "Curator archive raised for %s; the analysis still published: %s",
                key,
                exc,
            )
            return None
        split = [
            name
            for name in (
                curator_archive.RAW_LIST_NAME,
                curator_archive.CLEANED_LIST_NAME,
            )
            if name in outcome.failed
        ]
        if split:
            # NOT a retry marker: nothing here or below re-attempts the
            # archive for this analysis (see the docstring).  What declining
            # the flag buys is that no slot ever CLAIMS a split pair was
            # archived — so a later fetch of this same analysis, from a fresh
            # cache or a re-publish, archives instead of skipping, and the
            # record view degrades honestly to capped live rows meanwhile.
            logger.warning(
                "Curator archive left %s unwritten for %s; recording no "
                "archived version, and the record view falls back to the "
                "capped live rows until a new analysis is published",
                ", ".join(split),
                key,
            )
            return None
        return key


    # -- the WP3 seam --------------------------------------------------------

    def _log_reading(
        self, name: str, values: list, *, swept: bool, failed: bool = False
    ) -> list | None:
        """``[]`` when the read happened and found nothing; ``None`` when it did not.

        Collapsing the two makes a dead logs pool indistinguishable from a quiet
        chain — and *quiet* is the state that kills this contract, so the
        difference is the whole dashboard.

        Three questions in order, and the order is the point:

        1. **Do we hold rows?**  Then serve them.  The fold is accumulated and
           is last-good by construction, behind the ``as of HH:MM`` marker.
        2. **Did *this group's own filter* die in this sweep?**  Then ``None``.
           ``swept`` is a fact about the sweep, not about the group: a sweep
           whose ``deposits`` filter died still returns a ``LogSweep``, so
           keying off it alone reads a dead filter as "read it, found nothing"
           — the exact conflation 1ba8370 fixed one level up, reintroduced one
           level down.  It only bites while a group has no history, which is to
           say on the first run.
        3. **Has anyone ever read this group?**  Then ``[]``: ``HourSaved`` and
           ``Rescued`` have never fired on chain, so "read it, found nothing" is
           the *expected* answer and must not render as an outage.
        """
        if values:
            return values
        if failed:
            return None
        if swept or name in self._logs_read_groups():
            return []
        return None

    def _readings(
        self,
        *,
        state: Any = None,
        config: Any = None,
        logs: Any = None,
        wallet_state: Any = None,
        log_groups_failed: Any = None,
    ) -> dict[str, Any]:
        """Everything ``build_signals`` reads, and only that.

        Three provenances, deliberately different:

        * **fast-tier values are live-only.**  A dead state pool means the
          clock, the phase truth, ``earlyBps`` and the forced-ETH row are
          ``None`` and render *unavailable* — not a stale number wearing a live
          face (PRD §11's degradation matrix, row 1).
        * **config comes from the cache**, because immutables cannot go stale.
          Reading them once and remembering is not staleness, it is what
          ``once`` means.
        * **log-derived values come from the accumulated fold**, which *is*
          last-good and is served behind the ``as of HH:MM`` marker.  The sweep
          is incremental, so this is the only place the game's history exists.

        The settlement record is the latch, not a read: it beats whatever
        ``isSettled()`` said this cycle (H1).
        """
        cfg = config if isinstance(config, dict) else {}
        swept = logs is not None
        # Per-filter, not per-sweep.  Absent means "nothing is known to have
        # failed", which is what a caller that cannot report partial failure is
        # in fact claiming.
        dead = log_groups_failed if isinstance(log_groups_failed, dict) else {}
        read: dict[str, Any] = {key: None for key in READING_KEYS}

        for key in FAST_TIER_PAYLOAD_KEYS:
            read[key] = getattr(state, key, None)
        for key in CONFIG_PAYLOAD_KEYS:
            read[key] = cfg.get(key)

        # A historical rank is computable only when every enumerated wallet has
        # a retained deposit row. Legacy capped files stay incomplete until
        # their one-time creation-block repair finishes.
        read["history_complete"] = self._history_complete()

        read["deposits"] = self._log_reading(
            "deposits",
            self.cache.events(),
            swept=swept,
            failed=bool(dead.get("deposits")),
        )
        read["first_deposits"] = self._log_reading(
            "first_deposits",
            self.cache.first_deposits(),
            swept=swept,
            failed=bool(dead.get("first_deposits")),
        )
        read["hour_saved"] = self._log_reading(
            "hour_saved",
            self.cache.hour_saved(),
            swept=swept,
            failed=bool(dead.get("hour_saved")),
        )
        read["rescued_total_wei"] = self.cache.rescued_total_wei()

        read["settlement_record"] = self.cache.settlement_record()
        read["wallet_state"] = wallet_state
        return read

    # -- public API ----------------------------------------------------------

    def set_wallet(self, address: str | None) -> bool:
        """Point the YOU row at a different wallet.  Returns whether it moved.

        The constructor is still the normal way in (``--wallet`` /
        ``MAXPANE_WALLET``); this is the reader changing their mind at runtime,
        from the screen's ``w`` key.  It is deliberately more than
        ``self.wallet = address``, because three pieces of state are *about the
        old address* and each would otherwise render under the new one:

        * ``_fast_wallet`` — the within-TTL re-serve.  Left alone, the previous
          wallet's rank, credit and "next ≥" survive on screen under somebody
          else's address for up to one fast tier;
        * the ``wallet`` last-good slot, whose payload is literally
          ``{"address": <the old one>}`` — dropped rather than re-served behind
          an ``as of`` marker.

        Dropping that slot also settles the stale-failure question, which is why
        ``_failed_groups`` is **not** touched here: :meth:`_degraded` degrades a
        group whose last-good is absent, so between the switch and the first
        successful read the new wallet reads as degraded either way — which is
        the honest state, since nothing has been read about it yet.  Discarding
        the old address's failure as well would change nothing observable, and
        this repo does not keep code no test can pin.

        The fast tier is then expired so the next cycle actually refetches: a
        tier with 12 of its 15 seconds left is "fresh", and without this the row
        stays empty after a keypress that looked like it worked.

        The **analysis linkage needs no expiry at all**: the B+C sweep is
        about the population, not about one wallet, so ``you_linked_*`` /
        ``you_clean_rank`` are re-answered by the next cycle's merge from the
        **already-held** analysis last-good (:meth:`_merge_analysis` asks
        ``curator_clusters.you_linkage`` about ``self.wallet`` every cycle).
        Expiring :data:`TIER_ANALYSIS` here would burn a minutes-long sweep to
        re-learn facts the slot already holds.

        A no-op when the address is unchanged (including ``""``/``None`` both
        meaning *no wallet*), so a reader who re-types the same address does not
        pay a refetch or lose their last-good.
        """
        normalised = address or None
        if normalised == self.wallet:
            return False
        self.wallet = normalised
        self._fast_wallet = None
        self.cache.drop_last_good(SLOT_WALLET)
        self.cache.expire(TIER_FAST)
        return True

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Run one refresh cycle and return the flat dashboard dict.

        **No exception escapes.**  A total failure still returns the full key
        set with every value ``None`` and ``degraded`` naming what died,
        because a widget can render an explicit unavailable state but cannot
        render a traceback.  The screen's own ``try``/``except`` is belt and
        braces for a mis-wired manager, never the documented outage path.
        """
        try:
            return await self._cycle()
        except Exception as exc:  # noqa: BLE001 — the outermost guard
            self._error_count += 1
            logger.exception("Curator refresh cycle failed outright: %s", exc)
            payload = self._blank_payload()
            payload["degraded"] = sorted(SOURCES)
            self._stamp(payload)
            return payload

    async def _cycle(self) -> dict[str, Any]:
        now = float(self._clock())
        self._cycle_count += 1
        tiers = set(self.cache.tiers_due(now))

        # The immutables first: the fold and the series both need the launch
        # anchor, and everything else is independent of them.
        config = await self._pool_config(tiers, now)

        # Both halves of the fast tier ride the same pool and the same tick —
        # and both are **gated on the tier**, the way the medium and slow halves
        # are.  Ungated, `TIER_TTL_SECONDS["fast"]` and its failure backoff are
        # decorative: `--poll-interval 5` is accepted (`_MIN_POLL_INTERVAL`), so
        # the eight-view batch, the balance and the six YOU views were being
        # re-sent three times per declared 15 s window against keyless public
        # endpoints, and a rate-limited host was hammered rather than backed
        # off.  PRD §5 sizes this tier at 15 s; this is where that number takes
        # effect.
        if TIER_FAST in tiers:
            state_out, wallet_state = await asyncio.gather(
                self._pool_state(now), self._pool_wallet(now)
            )
            state = state_out.get("state")
            self._fast_state = state
            self._fast_wallet = wallet_state
        else:
            state = self._fast_state
            wallet_state = self._fast_wallet

        logs_out = await self._pool_logs(tiers, now, config)
        # Started, not awaited: it reads the whole log history over a second
        # transport and takes minutes, while publishing no key.  See
        # `_spawn_crosscheck`.
        self._spawn_crosscheck(tiers, now, state, config)
        # Started, not awaited, for the same reason: the bounded funding pass
        # alone is ~70 s of paced requests.  The NEXT cycle's merge reads what
        # it publishes.  See `_spawn_analysis`.
        self._spawn_analysis(tiers, now, config)

        readings = self._readings(
            state=state,
            config=config,
            logs=logs_out.get("sweep"),
            wallet_state=wallet_state,
            log_groups_failed=logs_out.get("failed"),
        )
        signals = _safe_call(build_signals, readings, now_ts=now, default=None)
        if not isinstance(signals, dict):
            logger.warning("build_signals returned %r — publishing the blank contract", signals)
            payload = self._blank_payload()
            # `degraded` is recomputed from SOURCE health below, and the sources
            # may all be perfectly healthy — the analytics are what died.  Left
            # alone this publishes 49 None values under `degraded == []`, i.e. a
            # total internal failure wearing the face of a healthy picture, and
            # `_safe_call` intercepts the most likely internal failure before the
            # outermost handler (which does exactly this) can ever see it.
            self._failed_groups.update(SOURCES)
        else:
            payload = dict(signals)

        # ``build_signals`` defaults its six list keys to ``[]`` — total over
        # hostile input, which is right for it and wrong for the four
        # SOURCE-BACKED ones here.  WP0 froze "a None list means the source is
        # dead, [] means genuinely nothing", and the widgets branch on it: left
        # as ``[]``, a dead logs pool would assert that nobody has ever
        # deposited.  The distinction is only knowable at this seam, because
        # only the manager knows whether the read happened.
        if readings.get("deposits") is None:
            for key in _SOURCE_BACKED_ROW_KEYS:
                if not payload.get(key):
                    payload[key] = None

        # The persisted series survive a restart. An empty one is left as
        # ``build_signals`` produced it.
        for key in CURATOR_SERIES_KEYS:
            stored = self.cache.get_series(key)
            if stored:
                payload[key] = stored

        # The analysis merge runs BEFORE the ENS labelling (the WP3 brief
        # sketched after) for one reason: the clean list's identity cells are
        # the leaderboard's exactly, and a merge that ran second would hand
        # the labeller rows it never saw.
        _safe_call(self._merge_analysis, payload)

        await self._label_with_ens(payload, now)

        payload["degraded"] = self._degraded()
        self._stamp(payload)
        return self._finalise(payload)

    # -- the analysis merge (WP3.4) ------------------------------------------

    def _you_list_row(
        self, payload: Mapping[str, Any], analysis: Mapping[str, Any] | None
    ) -> dict[str, Any] | None:
        """Project the configured wallet once, independent of display caps."""
        if not isinstance(self.wallet, str) or not self.wallet:
            return None

        address_key = self.wallet.lower()
        visible = next(
            (
                row
                for row in payload.get("leaderboard_rows") or ()
                if isinstance(row, Mapping)
                and str(row.get("address", "")).lower() == address_key
            ),
            None,
        )
        first_index = visible.get("first_index") if visible else None
        if first_index is None:
            for row in self.cache.fold_rows():
                if str(getattr(row, "address", "")).lower() == address_key:
                    first_index = getattr(row, "first_index", None)
                    break

        you_keys = (
            "you_rank",
            "you_clean_rank",
            "you_points",
            "you_credit_eth",
            "you_weight_eth",
            "you_tx_count",
            "you_first_hour",
        )
        if (
            payload.get("leaderboard_rows") is None
            and first_index is None
            and all(payload.get(key) is None for key in you_keys)
        ):
            return None

        row = {
            "rank": payload.get("you_rank"),
            "clean_rank": payload.get("you_clean_rank"),
            "address": self.wallet,
            "points": payload.get("you_points"),
            "credit_eth": payload.get("you_credit_eth"),
            "weight_eth": payload.get("you_weight_eth"),
            "tx_count": payload.get("you_tx_count"),
            "first_hour": payload.get("you_first_hour"),
            "first_index": first_index,
            "name": None,
            "link_conf": None,
        }
        curator_clusters.merge_leaderboard_grade([row], analysis)
        return row

    def _merge_analysis(self, payload: dict[str, Any]) -> None:
        """Merge the detached sweep's last-good into the flat dict.  In place.

        The ENS-merge shape: ``build_signals`` never sees these keys, the
        adapter's lookups fill them, and the widget's unavailable states do
        the rest.  Three states, never collapsed:

        * **no last-good** — every analysis key stays ``None`` (the blank
          payload's own value; an ``[]`` here would be an empty table
          asserting nobody is linked, off a read that never happened) and
          ``link_conf`` is seeded ``None`` on every leaderboard row (R9);
        * **analyzed, nothing linked** — ``operators_count == 0`` with real
          empty rows, a representable zero;
        * **analyzed and linked** — rows, counts, the reader's linkage, and
          the ``flagged_points_share_pct`` **override-with-fallback** (plan
          §6 risk 2 as pre-ruled): the analysis's share wins when it carries
          one, Tier A's ``build_signals`` value stands otherwise.

        Rows are **copied** out of the slot: the ENS labeller writes ``name``
        onto the payload's rows next, and writing into the cached slot would
        persist names into the analysis payload where they outlive every name
        TTL.  ``analysis_as_of_hhmm`` is the slot's own spawn-time stamp —
        the sweep's freshness moves on its own schedule, never the fast
        tier's.
        """
        entry = self.cache.analysis_last_good()
        slot = (
            entry.payload
            if entry is not None and isinstance(entry.payload, Mapping)
            else None
        )
        # Pre-100 caches already carry every clean rank.  Upgrade their display
        # slice only when the persisted fold can supply the complete new range.
        if slot is not None:
            clean_rows = slot.get("clean_list_rows")
            clean_count = _opt_int(slot.get("clean_contributors"))
            if (
                isinstance(clean_rows, list)
                and clean_count is not None
                and clean_count >= 0
            ):
                expected = min(curator_clusters.CLEAN_LIST_LIMIT, clean_count)
                if len(clean_rows) < expected:
                    rebuilt = curator_clusters.clean_list_rows_from_fold(
                        slot, self.cache.fold_rows()
                    )
                    if [row["clean_rank"] for row in rebuilt] == list(
                        range(1, expected + 1)
                    ):
                        migrated = dict(slot)
                        migrated["clean_list_rows"] = rebuilt
                        self.cache.store_analysis(migrated, ts=entry.ts)
                        slot = migrated
        rows = payload.get("leaderboard_rows")
        curator_clusters.merge_leaderboard_grade(
            rows if isinstance(rows, list) else None, slot
        )
        if slot is not None:
            for key in ("operator_rows", "segment_rows", "clean_list_rows"):
                value = slot.get(key)
                payload[key] = (
                    [dict(row) for row in value if isinstance(row, Mapping)]
                    if isinstance(value, list)
                    else None
                )
            for key in (
                "operators_count",
                "clean_points",
                "clean_contributors",
                "points_total",
            ):
                payload[key] = _opt_int(slot.get(key))
            share = slot.get("flagged_points_share_pct")
            if isinstance(share, (int, float)) and not isinstance(share, bool):
                payload["flagged_points_share_pct"] = float(share)
            payload["analysis_as_of_hhmm"] = entry.as_of_hhmm()
            payload["analysis_version"] = _analysis_version(slot.get("published"))
            if self.wallet:
                payload.update(curator_clusters.you_linkage(self.wallet, slot))
        payload["you_list_row"] = self._you_list_row(payload, slot)

    # -- reverse ENS (PRD §13 A9) --------------------------------------------

    def _rendered_addresses(self, payload: Mapping[str, Any]) -> list[str]:
        """Every address this payload will put on screen, and nothing else.

        Resolving the whole contributor table would be thousands of addresses
        for ten visible rows.  The set is: the leaderboard's rows, the activity
        feed's, the two signal wallets, the savior column, and the reader's own.
        """
        out: list[str] = []
        # ``clean_list_rows`` renders the same identity cell the leaderboard
        # does (bounded: the adapter caps the rendered slice), so its
        # addresses are part of the on-screen set — after the analysis merge,
        # which is why the merge runs first.
        for key in ("leaderboard_rows", "activity_rows", "clean_list_rows"):
            for row in payload.get(key) or ():
                if isinstance(row, dict) and isinstance(row.get("address"), str):
                    out.append(row["address"])
        you_list_row = payload.get("you_list_row")
        if isinstance(you_list_row, Mapping) and isinstance(
            you_list_row.get("address"), str
        ):
            out.append(you_list_row["address"])
        for row in payload.get("closest_call_rows") or ():
            if isinstance(row, dict) and isinstance(row.get("savior"), str):
                out.append(row["savior"])
        for key in ("whale_wallet", "last_saved_wallet"):
            value = payload.get(key)
            if isinstance(value, str):
                out.append(value)
        if isinstance(self.wallet, str):
            out.append(self.wallet)
        return out

    async def _ens_names_for_addresses(
        self, addresses, now: float
    ) -> dict[str, str]:
        """Resolve every uncached address in bounded THE LIST-only batches."""
        known = self.cache.ens.names_fresh(ens.DEFAULT_TTL_SECONDS, now)
        misses = self.cache.ens.misses_fresh(ens.MISS_TTL_SECONDS, now)
        wanted: list[str] = []
        seen: set[str] = set()
        for address in addresses:
            if not _looks_like_address(address):
                continue
            key = address.lower()
            if key in known or key in misses or key in seen:
                continue
            seen.add(key)
            wanted.append(address)

        for start in range(0, len(wanted), ens.MAX_ADDRESSES):
            batch = wanted[start : start + ens.MAX_ADDRESSES]
            resolved = await self._guard(
                lambda batch=batch: self.client.fetch_ens_names(batch),
                "fetch_ens_names",
            )
            if resolved is None:
                continue
            if not isinstance(resolved, Mapping):
                logger.warning(
                    "Curator fetch_ens_names returned %r, not a mapping",
                    type(resolved),
                )
                continue
            batch_keys = {address.lower() for address in batch}
            new_names = {
                address.lower(): name
                for address, name in resolved.items()
                if isinstance(address, str)
                and address.lower() in batch_keys
                and isinstance(name, str)
                and name
            }
            if new_names:
                _safe_call(self.cache.ens.set_names, new_names, ts=now)
                known.update(new_names)
            _safe_call(
                self.cache.ens.note_misses,
                [address for address in batch if address.lower() not in known],
                ts=now,
            )
        return known

    async def label_list_rows_with_ens(self, rows) -> list[dict]:
        """Copy and ENS-label a validated complete raw or cleaned list."""
        labelled = [dict(row) for row in rows if isinstance(row, Mapping)]
        now = float(self._clock())
        await self._ens_names_for_addresses(
            (row.get("address") for row in labelled), now
        )
        return self.cached_list_rows_with_ens(labelled)

    async def _label_with_ens(self, payload: dict[str, Any], now: float) -> None:
        """Attach verified reverse-ENS names to the addresses being rendered.

        Cosmetic by construction: every failure path here leaves the payload
        exactly as it was, and every widget falls back to the shortened hex.
        Nothing is resolved twice -- a fresh name and a fresh *miss* both mean
        "do not ask" (see :class:`ens.NameStore`), and without the miss half
        most wallets would be re-queried on every tick forever, because most
        wallets have no reverse record.
        """
        known = await self._ens_names_for_addresses(
            self._rendered_addresses(payload), now
        )

        if not known:
            return

        for key in ("leaderboard_rows", "activity_rows", "clean_list_rows"):
            for row in payload.get(key) or ():
                if isinstance(row, dict) and isinstance(row.get("address"), str):
                    row["name"] = known.get(row["address"].lower())
        you_list_row = payload.get("you_list_row")
        if isinstance(you_list_row, dict) and isinstance(
            you_list_row.get("address"), str
        ):
            you_list_row["name"] = known.get(you_list_row["address"].lower())
        for row in payload.get("closest_call_rows") or ():
            if isinstance(row, dict) and isinstance(row.get("savior"), str):
                row["savior_name"] = known.get(row["savior"].lower())
        for src, dst in (
            ("whale_wallet", "whale_ens"),
            ("last_saved_wallet", "last_saved_ens"),
        ):
            value = payload.get(src)
            if isinstance(value, str):
                payload[dst] = known.get(value.lower())
        if isinstance(self.wallet, str):
            payload["you_ens"] = known.get(self.wallet.lower())

    def _stamp(self, payload: dict[str, Any]) -> None:
        """Fill the freshness marker from the newest *successful* read.

        It moves only when something actually answered, which is what makes the
        settlement case honest: after the endpoints die the phase word stays
        SETTLED and this marker is what freezes, so the reader can see exactly
        how old the picture is.
        """
        stamp = None
        try:
            stamp = self.cache.newest_as_of()
        except Exception as exc:  # noqa: BLE001
            logger.debug("curator as-of lookup failed: %s", exc)
        payload["as_of"] = stamp
        payload["as_of_hhmm"] = (
            time.strftime("%H:%M", time.localtime(stamp)) if stamp else None
        )

    # -- contract enforcement ------------------------------------------------

    def _finalise(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return exactly :data:`CURATOR_KEYS`, no more and no less.

        A key this manager invents is dropped and logged rather than shipped: a
        screen that has to ask whether a key exists is a screen with a silent
        fallback arm.
        """
        out = self._blank_payload()
        for key, value in data.items():
            if key in out:
                out[key] = value
            else:
                logger.error(
                    "CuratorManager produced %r, which is not in CURATOR_KEYS — dropped",
                    key,
                )
        return out

    def _blank_payload(self) -> dict[str, Any]:
        """Every key present, every source down, nothing invented.

        The four **source-backed** row keys stay ``None``.  WP0 froze the pair
        of meanings and the widgets act on them: a ``None`` list means *source
        dead* and renders the unavailable state, while ``[]`` means *genuinely
        nothing* and renders "no deposits yet".  Seeding ``[]`` here would make
        a dead logs pool assert that nobody has ever deposited.

        The two **series** keys are different and stay ``[]``: they are this
        cache's own history rather than a source's answer, and an empty history
        is a fact about this install, not about the network.
        """
        payload: dict[str, Any] = dict.fromkeys(CURATOR_KEYS)
        payload["degraded"] = []
        for key in CURATOR_SERIES_KEYS:
            payload[key] = []
        return payload

    def _client_degradation(self) -> set[str]:
        """The groups the client's own flags implicate.

        Read defensively with ``getattr``: the real client sets all six, but a
        test double implementing only the ``fetch_*`` coroutines need not, and
        this method must not raise because a client is *less* chatty about
        outages.  Each flag is reset at the start of the call it describes, so
        reading it right after that call reflects only this cycle.

        ``log_group_failed`` is the one that matters most.  ``LogSweep``'s
        ``()`` means both "read, nothing matched" and "this filter died", and
        without this dict a dead ``Settled`` filter reads as *the game is
        alive*.
        """
        out: set[str] = set()
        client = self.client
        if getattr(client, "state_failed", False):
            out.add(SOURCE_STATE)
        if getattr(client, "config_failed", False):
            # The `once` tier rides its own schedule but it is part of the same
            # story the user is told about the state pool.
            out.add(SOURCE_STATE)
        if getattr(client, "logs_failed", False):
            out.add(SOURCE_LOGS)
        groups = getattr(client, "log_group_failed", None)
        if isinstance(groups, dict) and any(groups.values()):
            out.add(SOURCE_LOGS)
        if getattr(client, "blockscout_truncated", False):
            out.add(SOURCE_LOGS)
        if self.wallet and getattr(client, "wallet_failed", False):
            out.add(SOURCE_WALLET)
        return out

    def _degraded(self) -> list[str]:
        """Groups the screen must not present as live, sorted, ⊆ :data:`SOURCES`.

        A group is degraded when its last attempt failed, **or** it has never
        produced a payload, **or** the client's own flags say this cycle's read
        was incomplete.

        The one exception is ``wallet`` with no wallet configured: nothing is
        wrong, nothing was attempted, and every ``you_*`` key is ``None``
        because there is nobody to ask about — not because a source died.
        """
        out = set(self._failed_groups)
        for group, slot in GROUP_SLOT.items():
            if group == SOURCE_WALLET and not self.wallet:
                out.discard(group)
                continue
            if self.cache.get_last_good(slot) is None:
                out.add(group)
        out |= self._client_degradation()
        # The analysis sweep folds the published linked-wallet analysis over
        # the log story (plan §6 risk 7 — no new group name; the title bar's
        # vocabulary is frozen).
        # A failed sweep lights ``logs`` ONLY while there is no analysis
        # last-good to serve: with one, the keys ride behind their own
        # ``analysis_as_of_hhmm`` marker and nothing lights; and a sweep that
        # has never been *able* to run is not a failure at all
        # (``_analysis_failed`` stays False on the cannot-run path).
        if self._analysis_failed and self.cache.analysis_last_good() is None:
            out.add(SOURCE_LOGS)
        if not self.wallet:
            out.discard(SOURCE_WALLET)
        return sorted(out & set(SOURCES))


__all__ = [
    "CONFIG_PAYLOAD_KEYS",
    "decode_deposit",
    "decode_first_deposit",
    "decode_hour_saved",
    "decode_launched",
    "decode_rescued_total",
    "decode_settled",
    "FAST_TIER_PAYLOAD_KEYS",
    "FilteredListResult",
    "GROUP_SLOT",
    "SOURCES",
    "SOURCE_LOGS",
    "SOURCE_STATE",
    "SOURCE_WALLET",
    "CuratorManager",
]
