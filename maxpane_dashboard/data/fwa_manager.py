"""Orchestrator for the Fake World Assets (FWA) "Gacha Terminal" dashboard (WP-12).

The single coordination point between three *independently failing* data pools,
four refresh tiers and one frozen output contract.  Exposes one public coroutine,
:meth:`FWAManager.fetch_and_compute`, which returns **exactly**
:data:`~maxpane_dashboard.data.fwa_models.FWA_DATA_KEYS` — always, under every
failure combination, and without ever letting an exception escape.

Everything below it is already tested in isolation; this module is wiring plus
the degradation policy.


The three pools
---------------

They are three different origins with three different failure modes, so they are
issued **concurrently** (``asyncio.gather(..., return_exceptions=True)``) and each
one degrades on its own:

======================  ==============================  ===========================
Pool                    Client                          Dies as
======================  ==============================  ===========================
**A — chain state**     :class:`FWAClient`              ``degraded_sources=["chain"]``
**B — event logs**      :class:`FWALogClient`           ``degraded_sources=["logs"]``
**C — off-chain market** :class:`FWAMarketClient`       ``degraded_sources=["market"]``
======================  ==============================  ===========================

Pool B is the design's single point of failure and gets the most careful
treatment: when it is down the activity feed and the settlement table are served
the **persisted last-good aggregates with their original ``as_of_ts``**, so the
screen reads "as of 14:32" instead of going blank *or* presenting stale numbers
as live.  ``feed_unavailable_reason`` carries the why.


Refresh tiers (PRD §6; the intervals live in :mod:`fwa_cache`, never here)
-------------------------------------------------------------------------

* ``fast`` 15 s — ``acquisitionFee``, pool temperature, VRF queue, crown.
* ``medium`` 60 s — the full block-pinned position sweep, and everything derived
  from it: odds board, chase board, Pull EV.
* ``slow`` 900 s — DexScreener, GeckoTerminal OHLCV, DefiLlama, and the
  background CoinGecko floor sweep.
* ``tail`` 30 s — the incremental ``eth_getLogs`` scan.
* ``once`` — the full-history log backfill (config params, allowlist, settlement
  mix) plus token metadata, which rides along in the hot batch.

The manager asks :meth:`FWACache.tiers_due` what to fetch and fetches nothing
else.  **The hot path never touches the network for floors**: it calls
:meth:`FWAMarketClient.cached_floors`, which is synchronous and does zero I/O.
The floor sweep itself paces at 6 s per collection (~4 minutes for 38) and is
therefore run as a *detached* task that no cycle ever awaits.


Nine things that are easy to get wrong here, and are not
--------------------------------------------------------

1. **The CoinGecko spacing is 6.0 s, not the module default 2.5 s.**  At 2.5 s a
   live sweep drew 26 consecutive 429s out of 36 calls and priced 6 of 38
   collections (findings §13.14).  :data:`COINGECKO_MIN_SPACING` is the override.

2. **The EV is fed through** :func:`fwa_market.floors_for_ev`, which omits
   unpriced collections instead of defaulting them to ``0.0``.  A zero floor
   *raises* ``lower_eth`` — ``max(sellback, 0.0)`` hands the position its full
   sell-back value inside the pessimistic bound — and inflates
   ``collections_priced``.  It collapses the band toward a confident lie from the
   direction you would not expect (findings §13.15).

3. **This module owns the one wei→ETH conversion.**  Models are wei-native and
   ``Wei`` is strict, so a float raises rather than truncating.  ``draw_events``
   rows arrive wei-native as ``amount_wei`` and leave as ``amount_eth``;
   ``crown_history`` rows already carry ``payout_eth`` because they are
   presentation payloads with no model behind them and are passed through.

4. **The arithmetic mean comes from the sweep, not from** ``eth_getBalance``.
   The balance includes escrow and accrued owner fees, so it is an upper bound on
   backing.  ``report["backing_total_wei"]`` is the exact sum at the pinned block.
   ``eth_getBalance(core)`` is surfaced separately, and only, as
   ``core_balance_eth``.

5. **The harmonic/arithmetic gap is computed every tick.**  It is a live ratio —
   3.885× on the pinned distribution, ≤3.49× two days later — not a constant.

6. ``fetch_hot_batch`` costs up to **three** ``eth_call``s: the aggregate3 batch
   plus ``quoteAcquisitionPrice()`` (its own gas price and gas bound) plus
   ``tokenShareBps(gap)`` (whose argument the batch itself reads).

7. **A failed read is ``None``, never ``0``.**  ``externalBuysEnabled()``,
   ``TTT_AMOUNT()`` and ``lastBuybackBlock()`` all legitimately read zero, so
   conflating the two would make a dead RPC look like a closed buy gate.

8. **Sweeps are block-pinned and never merged.**  A sweep is published through
   :meth:`FWACache.set_sweep`, which replaces the slot wholesale and refuses a
   rewind.  A failed invariant check means ``invariants_ok=False`` and
   ``odds_stale=True`` — never a plausible total.  The odds board renders *stale*;
   the EV is **withheld** (``ev_available=False``), because a number derived from
   an incomplete position set is wrong rather than merely old.

9. **Never** ``weighted_backing_total``.  It is ``Σ(weight × backing)``,
   dimensionless, and reads like a count of ETH.  It has no data key and is used
   here only inside the invariant check.

What is persisted, and what is bounded
--------------------------------------

Two files, two policies.

``~/.maxpane/fwa_cache.json`` holds the **aggregates and display payloads** —
settlement mix, crown history, the last 50 draws, config history, the allowlist —
always, unbounded in time and tiny in bytes.  They are the whole Pool B
degradation story: when the log endpoint dies these are what render, behind an
honest ``as of HH:MM``.

``~/.maxpane/fwa_log_state.json`` holds the **raw decoded events**, so the
one-time full-history backfill stays one-time.  Unbounded, that file is tens of
MB on the live chain and grows forever, so it is bounded three ways:

1. High-volume events are kept for :data:`LOG_RAW_WINDOW_BLOCKS` back from the
   watermark — a *block* window, so the bound does not move with activity.
2. :data:`LOG_ALLTIME_EVENTS` are kept whole (~130 logs all-time). The
   aggregates they drive — crown reigns, parameter drift, the allowlist — are
   all-time by definition and windowing them would silently rewrite history.
3. A hard :data:`LOG_STATE_MAX_BYTES` ceiling, enforced by shrinking the window
   and finally by dropping the windowed events outright.

The one aggregate a window would corrupt is the settlement mix, which WP-7
derives from ``len(store[event])``.  The export therefore carries an **all-time
count baseline**, and :meth:`FWAManager._correct_windowed_aggregates` recomputes
the mix from it, so 73.92% of 51,522 never quietly becomes 71% of the last four
hours.  Every trim is logged: a bound that discards data silently reads as "we
have full history" when we do not.

USD figures appear only where a USD source exists.  The ETH/USD rate is *derived*
from the one DexScreener pair (``price_usd / price_native_eth``) and is ``None``
when either leg is missing — no rate is ever invented, and a missing rate renders
``—`` rather than an ETH number wearing a dollar sign.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from maxpane_dashboard.analytics import fwa_ev
from maxpane_dashboard.analytics.fwa_signals import (
    buy_gate_signal,
    emissions_signal,
    invariant_summary,
    param_drift_signal,
    pool_temp_signal_for,
    resolve_config_params,
    resolve_pool_temp,
    vrf_queue_signal,
)
from maxpane_dashboard.data.fwa_cache import (
    DEFAULT_CACHE_PATH,
    SERIES_FWA_PRICE_USD,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_ONCE,
    TIER_SLOW,
    TIER_TAIL,
    FWACache,
)
from maxpane_dashboard.data.fwa_client import FWAClient
from maxpane_dashboard.data.fwa_logs import (
    REASON_UNAVAILABLE,
    SETTLEMENT_EVENTS,
    FWALogClient,
    settlement_mix_rows,
)
from maxpane_dashboard.data.fwa_market import FWAMarketClient, floors_for_ev
from maxpane_dashboard.data.fwa_models import (
    FWA_DATA_KEYS,
    CollectionOdds,
    Crown,
    Position,
    PullEV,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths and knobs
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(DEFAULT_CACHE_PATH).parent

#: Raw decoded log store, persisted beside the tiered cache.
#:
#: ``FWACache`` persists the *aggregates* (the last-good display payload), which
#: is what the degraded path renders.  This sidecar holds the raw events, so the
#: one-time full-history backfill stays one-time across restarts instead of
#: costing a fresh archive scan on every launch.
#:
#: It is **bounded** — see :data:`LOG_RAW_WINDOW_BLOCKS` and
#: :data:`LOG_STATE_MAX_BYTES`.  An unbounded export of the live chain is tens of
#: MB and grows forever, which is not something to leave in ``~/.maxpane`` for a
#: tool people install with pipx.
_LOG_STATE_PATH = str(_CACHE_DIR / "fwa_log_state.json")

#: Sidecar schema version.  Bumped when the retention shape changes so an old
#: unbounded file is re-trimmed on the next write rather than read as authoritative.
LOG_STATE_VERSION = 2

#: How far back the **high-volume** raw events are persisted, in blocks
#: (~4 hours at 12 s/block).
#:
#: A *block* window rather than an event count, so the bound is predictable
#: regardless of protocol activity.  Sized from what the raw events are actually
#: for after a restart:
#:
#: * the activity feed renders 25 rows off a 50-row payload, and the busiest
#:   window on record ran 1,327 ``AcquisitionRequested`` per 500 blocks (findings
#:   §5) — 2.65/block, so 1,200 blocks is ~3,200 draws, 60x the feed depth.  On
#:   the all-time average of 0.88/block it is still ~1,000 draws, 20x;
#: * the tail scan needs **no** retained events to resume — it resumes from the
#:   persisted ``last_seen_block`` watermark.  The overlap only has to cover the
#:   boundary block's identity dedupe, which one block would do.
#:
#: Everything the settlement table and crown history need is retained
#: independently and exactly: see :data:`LOG_ALLTIME_EVENTS` and the all-time
#: count baseline.
#:
#: Measured on the real full-history dump: 300 blocks retains 631 allocations,
#: 12x the feed depth, for 1.5 MiB. See :data:`LOG_STATE_MAX_BYTES`.
LOG_RAW_WINDOW_BLOCKS = 300

#: Rows retained per high-volume event type **regardless of the block window**.
#:
#: The block window bounds the maximum; this bounds the minimum.  Without it a
#: quiet chain would leave the window nearly empty and the activity feed short
#: after a restart — the window is sized against *today's* ~2 draws per block,
#: and nothing guarantees that rate holds.  On a busy chain this is a no-op
#: because the window already exceeds it.
LOG_RAW_MIN_ROWS = 200

#: Hard ceiling on the sidecar.  Enforced by shrinking the window and, if that is
#: still not enough, dropping the windowed events entirely — the all-time events
#: and the count baseline always survive, so the aggregates stay exact.
LOG_STATE_MAX_BYTES = 4 * 1024 * 1024

#: Number of window shrinks attempted before the raw events are dropped outright.
LOG_STATE_SHRINK_ATTEMPTS = 3

#: How far behind the head a restored watermark may be before the catch-up scan
#: is abandoned in favour of a fresh full backfill (~7 days at 12 s/block).
#:
#: Below this the tail closes the gap and every aggregate stays exact.  Above it
#: the single catch-up window gets long enough that re-deriving from scratch is
#: both cheaper to reason about and the only way to keep the settlement counts
#: and crown history honest.
LOG_CATCHUP_MAX_BLOCKS = 50_000

#: Event types persisted **all-time**.  ~130 logs across the protocol's entire
#: history (33 ``TopListingSet``, 12 ``TopListingSettled``, 27 ``ConfigSet``,
#: 51 ``CollectionWhitelistSet``), and the aggregates they drive — crown reigns
#: and payouts, parameter drift, the allowlist — are all-time *by definition*.
#: Windowing them would silently turn "17 reigns" into "reigns since Tuesday".
LOG_ALLTIME_EVENTS: frozenset[str] = frozenset(
    {
        "ConfigSet",
        "CollectionWhitelistSet",
        "TopListingSet",
        "TopListingFunded",
        "TopListingSettled",
    }
)

#: In-memory only: listing id -> ``{collection, token_id}``, accumulated from the
#: position sweeps so the activity feed can name the collection behind a draw
#: even when the listing's ``NFTListed`` log predates the retained window.
#: ``NFTAllocated`` carries no collection address, so without this a truncated
#: store would render the zero address.  FIFO-evicted; never persisted.
LISTING_INDEX_MAX = 20_000

#: FWA core's first config write — findings §2, "Protocol deploy block".  A scan
#: floor, never a rendered value: starting the backfill at 0 costs the paging
#: endpoint 2,500 windows for blocks that cannot contain an FWA log.
FWA_DEPLOY_BLOCK = 25_546_793

#: CoinGecko spacing override (findings §13.14).  The module default of 2.5 s
#: drew 26 consecutive 429s out of 36 live calls and priced 6 of 38 collections.
COINGECKO_MIN_SPACING = 6.0

#: Activity-feed depth handed to :meth:`FWALogClient.snapshot`.
FEED_LIMIT = 50

#: Chase-board rows produced.  The widget renders the top 12; the surplus costs
#: nothing and lets the screen change its mind without a manager change.
CHASE_ROWS = 25

#: Crown-history rows kept in the persisted last-good payload.
CROWN_HISTORY_CAP = 25

#: Sparkline depth (hourly candles).
OHLCV_LIMIT = 100

#: Degradation source labels.  ``fwa_signals.degraded_label`` turns these into
#: the exact strings the widgets render.
SOURCE_CHAIN = "chain"
SOURCE_LOGS = "logs"
SOURCE_MARKET = "market"

#: Keys of :meth:`FWALogClient.snapshot` that are worth persisting as last-good.
#:
#: ``price_history`` (one row per block that saw an ``AcquisitionRequested``),
#: ``backing_updates`` and ``collection_registry`` are dropped: they are cycle
#: inputs, not display payloads, and writing them every tick would put megabytes
#: through the cache file for data no widget reads.
_LOG_CACHE_KEYS: tuple[str, ...] = (
    "available",
    "reason",
    "as_of_ts",
    "last_seen_block",
    "settlement_mix",
    "crown_history",
    "crown_sets_total",
    "crown_payouts_total",
    "crown_paid_eth",
    "draw_events",
    "config_history",
    "allowed_collections",
    "event_counts",
)

#: ``ConfigSet`` key -> the hot-batch view that reads the same parameter live.
#:
#: Drives ``resolve_config_params`` and the drift comparison, which is *always*
#: live-vs-last-``ConfigSet`` and never live-vs-documented (PRD §7 rule 6).  Only
#: keys with a live getter in :data:`fwa_client.HOT_VIEWS` appear; a key we cannot
#: read is omitted rather than back-filled from its own history.
_LIVE_PARAM_VIEWS: dict[int, str] = {
    11: "selection_timeout_blocks",   # SELECTION_TIMEOUT_BLOCKS
    14: "selection_slippage_bps",     # SELECTION_SLIPPAGE_BPS
    15: "top_listing_share_bps",      # TOP_LISTING_SHARE_BPS  (500 -> 100, live)
    16: "top_threshold_bps",          # TOP_THRESHOLD_BPS
    17: "settlement_discount_bps",    # SETTLEMENT_DISCOUNT_BPS (purchaser payout)
    18: "owner_acquisition_fee_bps",  # OWNER_ACQUISITION_FEE_BPS
    19: "owner_settlement_fee_bps",   # OWNER_SETTLEMENT_FEE_BPS
    20: "settlement_window",          # SETTLEMENT_WINDOW
    21: "finalize_window",            # FINALIZE_WINDOW
    40: "retained_to_protocol",       # RETAINED_TO_PROTOCOL (bool)
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _safe_call(fn: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    """Call *fn*, returning *default* on any exception.

    An analytics bug must degrade one number, not the whole cycle.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — that is the entire point
        logger.debug("FWA analytics call %s failed: %s", getattr(fn, "__name__", fn), exc)
        return default


def _wei_to_eth(value: Any) -> float | None:
    """The one wei -> ETH conversion in the FWA stack.  ``None`` stays ``None``.

    Models are wei-native by contract; this is the presentation boundary and the
    only place the division is allowed to happen.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value) / fwa_ev.WEI_PER_ETH
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    """``int`` or ``None`` — ``None`` in, ``None`` out.  Never a silent ``0``.

    ``bool`` is deliberately accepted and widened to ``0``/``1``: several config
    parameters (``RETAINED_TO_PROTOCOL``) are on-chain bools and their live value
    has to be comparable against a ``ConfigSet`` integer.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _first(*values: Any) -> Any:
    """First value that is not ``None``.  ``0`` and ``False`` are real answers."""
    for value in values:
        if value is not None:
            return value
    return None


def _short_address(address: str) -> str:
    """``0xb276…ac1c`` — the honest fallback when no collection name is known."""
    addr = str(address or "")
    return f"{addr[:6]}…{addr[-4:]}" if len(addr) >= 12 else addr or "unknown"


def _dump(model: Any) -> dict | None:
    """``model_dump()`` or ``None``.  Signals are optional by contract."""
    if model is None:
        return None
    try:
        return model.model_dump()
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not dump %r: %s", model, exc)
        return None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class FWAManager:
    """Fetches FWA data across three pools, computes analytics, returns a flat dict.

    Parameters
    ----------
    poll_interval:
        Seconds between automatic refreshes.  Reported in the status bar; the
        actual fetch decisions come from the cache's tier TTLs, not from this.
    clock:
        Injectable wall clock, shared with the cache so tests can drive TTL expiry
        without sleeping.
    cache_path / log_state_path:
        Where the tiered cache and the raw log store live.
    client / log_client / market_client / cache:
        Pre-built collaborators, for tests.  When omitted, real ones are
        constructed — the market client always with
        ``coingecko_min_spacing=`` :data:`COINGECKO_MIN_SPACING`.
    persist_log_state:
        Write the (bounded) raw event store to *log_state_path* so the
        full-history backfill is a one-time cost.  The escape hatch: with it off
        the dashboard still renders from the persisted aggregates while a fresh
        backfill runs.  See :data:`_LOG_STATE_PATH`.
    log_raw_window_blocks / log_state_max_bytes:
        Retention window and hard file ceiling.  See the class docstring.
    """

    def __init__(
        self,
        poll_interval: int = 30,
        *,
        clock: Any = time.time,
        cache_path: str = DEFAULT_CACHE_PATH,
        log_state_path: str | None = None,
        client: Any = None,
        log_client: Any = None,
        market_client: Any = None,
        cache: Any = None,
        persist_log_state: bool = True,
        log_raw_window_blocks: int = LOG_RAW_WINDOW_BLOCKS,
        log_state_max_bytes: int = LOG_STATE_MAX_BYTES,
        feed_limit: int = FEED_LIMIT,
        chase_rows: int = CHASE_ROWS,
    ) -> None:
        self.poll_interval = poll_interval
        self._clock = clock
        self._cache_path = cache_path
        self._log_state_path = (
            _LOG_STATE_PATH if log_state_path is None else log_state_path
        )
        self._persist_log_state = persist_log_state
        self._log_raw_window_blocks = max(0, int(log_raw_window_blocks))
        self._log_state_max_bytes = max(1024, int(log_state_max_bytes))
        self._feed_limit = feed_limit
        self._chase_row_limit = chase_rows

        self.client = client if client is not None else FWAClient()
        self.logs = log_client if log_client is not None else FWALogClient()
        self.market = (
            market_client
            if market_client is not None
            else FWAMarketClient(coingecko_min_spacing=COINGECKO_MIN_SPACING)
        )
        self.cache = cache if cache is not None else FWACache(clock=clock)

        self._cycle_count = 0
        self._error_count = 0
        self._last_fetch_ts: float = 0.0
        self._last_success_ts: float = 0.0

        # Single-flight guard for the 60 s sweep.  A sweep still running when the
        # next tick fires is *skipped*, never queued: queueing a multi-second
        # sweep behind a 60 s cadence is how a dashboard ends up rendering a block
        # from ten minutes ago.
        self._sweep_running = False

        # Detached background floor sweep (never awaited by a cycle).
        self._floor_task: asyncio.Task | None = None

        #: Live config parameters resolved against ``ConfigSet`` history. Not a
        #: data key — the flat contract has no parameter table — but the resolved
        #: rows are the drift row's evidence and are useful to a drill-down.
        self.config_params: tuple = ()

        self._log_backfill_done = False
        self._catchup_done = False
        self._restored_last_seen = 0

        # All-time per-event counts as of ``_event_baseline_block``.  Empty means
        # "the in-memory store *is* all-time", which is true after a full backfill
        # and false after a windowed restore.  This is what keeps the settlement
        # mix reporting 73.92% of 51,522 rather than 71% of the last four hours.
        self._event_baseline: dict[str, int] = {}
        self._event_baseline_block = 0
        self._all_time_counts: dict[str, int] | None = None

        # Memory-only listing index accumulated from the sweeps (see
        # :data:`LISTING_INDEX_MAX`).
        self._listing_index: dict[int, dict[str, Any]] = {}

        self._invariants_ok = True
        self._core_balance_wei: int | None = None
        self._collection_addresses: tuple[str, ...] = ()

        self._load_state()

    # ------------------------------------------------------------------
    # Startup / shutdown
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Restore the cache, the floor cache and the raw log store.  Never raises."""
        cache_dir = Path(self._cache_path).parent
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create %s: %s", cache_dir, exc)

        try:
            self.cache.load_from_file(self._cache_path)
        except Exception as exc:  # noqa: BLE001 — load_from_file is fail-soft, belt and braces
            logger.warning("FWA cache load failed: %s", exc)

        # Floors: rebuild FloorQuote-shaped rows from the cache's per-collection
        # entries so the very first tick already has something to price with.
        try:
            restored = {}
            for addr, entry in self.cache.floors_snapshot().items():
                payload = entry.payload if isinstance(entry.payload, dict) else {}
                floor_eth = payload.get("floor_eth")
                source = str(payload.get("source") or "missing")
                if source == "suppressed":
                    status = "suppressed"
                elif floor_eth is not None:
                    status = "ok"
                else:
                    status = "missing"
                restored[addr] = {
                    "address": addr,
                    "floor_eth": floor_eth,
                    "source": source,
                    "status": status,
                    "note": payload.get("note") or "",
                    "fetched_at": entry.ts,
                }
            if restored:
                self.market.import_floor_cache(restored)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FWA floor cache restore failed: %s", exc)

        # Raw log store.  Restoring does not make Pool B "available" — that is
        # earned by a live scan — but it does make the backfill a one-time cost.
        try:
            with open(self._log_state_path) as handle:
                state = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.debug("No FWA log state to load (%s): %s", self._log_state_path, exc)
            return
        if not self.logs.import_state(state):
            return
        self._log_backfill_done = True
        self._restored_last_seen = _opt_int(state.get("last_seen_block")) or 0
        try:
            self._event_baseline = {
                str(name): int(count)
                for name, count in (state.get("event_baseline") or {}).items()
            }
            self._event_baseline_block = _opt_int(state.get("event_baseline_block")) or 0
        except (TypeError, ValueError) as exc:
            logger.warning("FWA log count baseline unreadable, dropping it: %s", exc)
            self._event_baseline = {}
            self._event_baseline_block = 0
        logger.info(
            "Restored FWA log state from %s: watermark block %d, raw events from "
            "block %s, all-time counts %s",
            self._log_state_path,
            self._restored_last_seen,
            state.get("raw_from_block", "(unbounded)"),
            "restored" if self._event_baseline else "recomputed from the store",
        )

    def save_cache(self) -> None:
        """Persist the tiered cache.  Never raises."""
        try:
            self.cache.save_to_file(self._cache_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FWA cache save failed: %s", exc)

    # -- bounded raw-event retention ---------------------------------------

    def _all_time_event_counts(self) -> dict[str, int]:
        """All-time per-event counts, correct across a windowed restore.

        With no baseline the in-memory store *is* all-time and its own counts are
        the answer.  With one, the answer is the baseline plus everything ingested
        **after** the baseline block — strictly after, because WP-7's tail resumes
        *at* ``last_seen_block`` and re-reads that block's logs.
        """
        try:
            live = self.logs.event_counts()
        except Exception as exc:  # noqa: BLE001
            logger.debug("event_counts unavailable: %s", exc)
            return dict(self._event_baseline)
        if not self._event_baseline:
            return {str(name): int(count) for name, count in live.items()}

        counts = dict(self._event_baseline)
        floor = self._event_baseline_block
        for name in live:
            try:
                fresh = sum(
                    1
                    for row in self.logs.entries(name)
                    if int(row.get("block_number") or 0) > floor
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("counting %s beyond block %d failed: %s", name, floor, exc)
                continue
            counts[str(name)] = counts.get(str(name), 0) + fresh
        return counts

    def _windowed_log_state(self, window_blocks: int) -> tuple[dict, dict[str, int]]:
        """Export the log store with the high-volume events bounded by block window.

        Returns ``(state, dropped)``.  Three retention rules, in order:

        1. :data:`LOG_ALLTIME_EVENTS` are kept whole — ~130 logs all-time, and the
           crown / drift / allowlist aggregates they drive are all-time by
           definition.
        2. Everything else is kept at or after ``head - window_blocks``, **or** as
           the newest :data:`LOG_RAW_MIN_ROWS` rows, whichever is more. The window
           bounds the maximum; the row floor bounds the minimum, so a quiet chain
           cannot leave the feed empty.
        3. ``NFTListed`` additionally keeps any row a *retained* draw or settlement
           refers to, whatever its block.  ``NFTAllocated`` carries no collection
           address, so dropping the listing that a retained draw points at would
           render the zero address in the feed.

        The state also carries the all-time count baseline, so a windowed restore
        still reports the all-time settlement mix rather than a window of it.
        """
        try:
            state = self.logs.export_state()
        except Exception as exc:  # noqa: BLE001
            logger.warning("FWA log state export failed: %s", exc)
            return {}, {}

        counts = self._all_time_event_counts()
        head = _opt_int(state.get("last_seen_block")) or 0
        state["version"] = LOG_STATE_VERSION
        state["event_baseline"] = counts
        state["event_baseline_block"] = head

        events = state.get("events")
        if not isinstance(events, dict) or not head:
            state["raw_from_block"] = 0
            state["raw_window_blocks"] = None
            return state, {}

        floor = max(0, head - int(window_blocks))
        min_rows = LOG_RAW_MIN_ROWS if window_blocks > 0 else 0
        kept: dict[str, list] = {}
        dropped: dict[str, int] = {}
        referenced: set[int] = set()

        def _window(rows: list) -> list:
            """In-window rows, or the newest ``min_rows``, whichever is more."""
            keep = [r for r in rows if int(r.get("block_number") or 0) >= floor]
            if len(keep) >= min_rows or len(rows) <= min_rows:
                return keep if len(keep) >= min_rows else list(rows)
            newest = sorted(rows, key=lambda r: int(r.get("block_number") or 0))
            return newest[-min_rows:]

        for name, rows in events.items():
            rows = list(rows or [])
            if name in LOG_ALLTIME_EVENTS:
                kept[name] = rows
                continue
            if name == "NFTListed":
                continue  # handled after the referenced ids are known
            keep = _window(rows)
            if len(keep) != len(rows):
                dropped[name] = len(rows) - len(keep)
            kept[name] = keep
            if name == "NFTAllocated" or name in SETTLEMENT_EVENTS:
                referenced.update(int(r.get("listing_id") or 0) for r in keep)

        listed = list(events.get("NFTListed") or [])
        keep_listed = [
            r
            for r in listed
            if int(r.get("block_number") or 0) >= floor
            or int(r.get("listing_id") or 0) in referenced
        ]
        if len(keep_listed) != len(listed):
            dropped["NFTListed"] = len(listed) - len(keep_listed)
        kept["NFTListed"] = keep_listed

        state["events"] = kept
        state["raw_from_block"] = floor
        state["raw_window_blocks"] = int(window_blocks)
        return state, dropped

    def _save_log_state(self) -> None:
        """Persist a bounded raw log store via atomic temp-then-rename.

        Never raises.  The window is shrunk up to
        :data:`LOG_STATE_SHRINK_ATTEMPTS` times if the serialised state exceeds
        :data:`LOG_STATE_MAX_BYTES`, and if that is still not enough the windowed
        events are dropped outright — the all-time events and the count baseline
        survive either way, so the aggregates stay exact.

        Every trim is logged.  A bound that quietly discards data reads as "we
        have full history" when we do not.
        """
        if not self._persist_log_state:
            return

        window = self._log_raw_window_blocks
        blob: str | None = None
        for attempt in range(LOG_STATE_SHRINK_ATTEMPTS + 1):
            state, dropped = self._windowed_log_state(window)
            if not state:
                return
            candidate = json.dumps(state)
            size = len(candidate.encode("utf-8"))
            if dropped:
                logger.debug(
                    "FWA log state trimmed to the last %d blocks (from block %s): "
                    "dropped %s; all-time counts and %s kept whole",
                    window,
                    state.get("raw_from_block"),
                    ", ".join(f"{n} x{c}" for n, c in sorted(dropped.items())),
                    "/".join(sorted(LOG_ALLTIME_EVENTS)),
                )
            if size <= self._log_state_max_bytes:
                blob = candidate
                break
            if attempt == LOG_STATE_SHRINK_ATTEMPTS:
                logger.debug(
                    "FWA log state still %d bytes over the %d byte ceiling after "
                    "%d shrinks — dropping the windowed raw events entirely; the "
                    "aggregates and the all-time counts are unaffected",
                    size - self._log_state_max_bytes,
                    self._log_state_max_bytes,
                    LOG_STATE_SHRINK_ATTEMPTS,
                )
                state, _dropped = self._windowed_log_state(0)
                blob = json.dumps(state)
                break
            window = max(1, window // 4)
            logger.debug(
                "FWA log state is %d bytes, over the %d byte ceiling — shrinking "
                "the retention window to %d blocks",
                size,
                self._log_state_max_bytes,
                window,
            )

        if blob is None:  # pragma: no cover — the loop always sets it
            return

        tmp = self._log_state_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._log_state_path) or ".", exist_ok=True)
            with open(tmp, "w") as handle:
                handle.write(blob)
            os.replace(tmp, self._log_state_path)
            logger.debug(
                "FWA log state written to %s (%d bytes, ceiling %d)",
                self._log_state_path,
                len(blob.encode("utf-8")),
                self._log_state_max_bytes,
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("FWA log state save failed: %s", exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    async def close(self) -> None:
        """Persist everything and close all three HTTP clients."""
        task = self._floor_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._floor_task = None

        self.save_cache()
        self._save_log_state()

        for name, client in (
            ("state", self.client),
            ("logs", self.logs),
            ("market", self.market),
        ):
            try:
                await client.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("closing the FWA %s client failed: %s", name, exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_and_compute(self) -> dict[str, Any]:
        """Run one refresh cycle and return the flat dashboard dict.

        Returns exactly :data:`FWA_DATA_KEYS`, always.  **No exception escapes**:
        a total failure still returns the full key set with every ``*_available``
        flag down and ``degraded_sources`` naming what died, because a widget can
        render an explicit unavailable state but cannot render a traceback.
        """
        try:
            return await self._cycle()
        except Exception as exc:  # noqa: BLE001 — the outermost guard
            self._error_count += 1
            logger.exception("FWA refresh cycle failed outright: %s", exc)
            payload = self._blank_payload()
            payload["degraded_sources"] = [SOURCE_CHAIN, SOURCE_LOGS, SOURCE_MARKET]
            payload["feed_unavailable_reason"] = f"refresh failed: {exc}"
            return payload

    # ------------------------------------------------------------------
    # The cycle
    # ------------------------------------------------------------------

    async def _cycle(self) -> dict[str, Any]:
        now = float(self._clock())
        self._cycle_count += 1
        self._last_fetch_ts = now

        tiers = set(self.cache.tiers_due(now))
        degraded: set[str] = set()

        state_res, logs_res, market_res = await asyncio.gather(
            self._pool_state(tiers, now),
            self._pool_logs(tiers, now),
            self._pool_market(tiers, now),
            return_exceptions=True,
        )
        state = self._unwrap(state_res, SOURCE_CHAIN, degraded)
        logs = self._unwrap(logs_res, SOURCE_LOGS, degraded)
        market = self._unwrap(market_res, SOURCE_MARKET, degraded)

        if state.get("failed"):
            degraded.add(SOURCE_CHAIN)
        if not logs.get("live"):
            degraded.add(SOURCE_LOGS)
        if not market.get("live"):
            degraded.add(SOURCE_MARKET)
        if len(degraded) < 3:
            # At least one origin answered; the screen's "updated Ns ago" only
            # starts counting when every pool is dark.
            self._last_success_ts = now

        # Rule 8: BackingUpdated after the pinned block makes the cached backing —
        # and therefore the harmonic mean and the flagship EV — wrong.
        self._apply_backing_updates()

        # Once-tier bookkeeping is shared: the startup work is the log backfill
        # plus the token metadata that rides along in the hot batch.
        if TIER_ONCE in tiers and logs.get("once_done") and state.get("hot") is not None:
            self.cache.set_startup(
                {
                    "allowed_collections": logs.get("allowed_collections") or [],
                    "token_symbol": (state.get("hot") or {}).get("token_symbol"),
                    "token_total_supply": (state.get("hot") or {}).get(
                        "token_total_supply"
                    ),
                    "config_params": len(logs.get("config_events") or []),
                },
                ts=now,
            )
            self.cache.mark_fetched(TIER_ONCE, now)

        payload = self._assemble(now, state, logs, market, sorted(degraded))

        # Started only once the sweep has told us which collections are in the
        # pool, which is why this sits after assembly rather than inside Pool C.
        if TIER_SLOW in tiers or self._floor_task is None:
            self._start_floor_sweep()

        self._sample_series(now, payload)
        self.save_cache()
        return payload

    def _unwrap(self, result: Any, source: str, degraded: set[str]) -> dict[str, Any]:
        """Turn one ``gather`` slot into a dict, recording a raised pool as dead."""
        if isinstance(result, BaseException):
            self._error_count += 1
            logger.warning("FWA %s pool raised: %s", source, result)
            degraded.add(source)
            return {}
        return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------
    # Pool A — chain state (FWAClient)
    # ------------------------------------------------------------------

    async def _pool_state(self, tiers: set[str], now: float) -> dict[str, Any]:
        """Hot batch (fast tier) + block-pinned position sweep (medium tier).

        Never raises.  A dead RPC leaves ``hot`` on the cache's last-good payload
        with ``hot_live=False``, and leaves the sweep on whatever block the cache
        already holds, flagged stale.
        """
        out: dict[str, Any] = {
            "hot": None,
            "hot_live": False,
            "positions": (),
            "sweep_block": None,
            "sweep_stale": True,
            "sweep_report": None,
            "sweep_skipped": False,
            "core_balance_wei": self._core_balance_wei,
            "failed": False,
        }

        # -- fast tier: the ~47-view Multicall3 batch (+2 follow-up eth_calls) --
        hot: dict[str, Any] | None = None
        attempted = TIER_FAST in tiers or self.cache.get_hot_batch() is None
        if attempted:
            try:
                hot = await self.client.fetch_hot_batch()
            except Exception as exc:  # noqa: BLE001 — documented not to raise; belt and braces
                logger.warning("FWA hot batch raised: %s", exc)
                hot = None
            if hot is not None and self._hot_usable(hot):
                self.cache.set_hot_batch(hot, ts=now)
                self.cache.mark_fetched(TIER_FAST, now)
                out["hot_live"] = True
            else:
                self.cache.mark_failed(TIER_FAST, now)
                self._error_count += 1
                hot = None
        if hot is None:
            # Either the read failed or the tier is simply still fresh; only the
            # first of those is a degradation.
            entry = self.cache.get_hot_batch()
            hot = dict(entry.payload) if entry and isinstance(entry.payload, dict) else None
            if attempted:
                out["failed"] = True
        out["hot"] = hot

        # -- medium tier: the sweep, single-flight ---------------------------
        if TIER_MEDIUM in tiers:
            if self._sweep_running:
                out["sweep_skipped"] = True
                logger.debug(
                    "FWA position sweep already in flight — skipping this tick "
                    "(skipped, never queued)"
                )
            else:
                await self._run_sweep(out, now)

            balance = await self._fetch_core_balance()
            if balance is not None:
                self._core_balance_wei = balance
        out["core_balance_wei"] = self._core_balance_wei

        # Always read the *published* sweep, so what the widgets see is whatever
        # the cache accepted — block-pinned, never rewound, never merged.
        entry = self.cache.get_sweep()
        if entry is not None:
            payload = entry.payload or ()
            out["positions"] = tuple(p for p in payload if isinstance(p, Position))
            out["sweep_block"] = entry.block
            out["sweep_stale"] = bool(entry.stale)
        return out

    async def _run_sweep(self, out: dict[str, Any], now: float) -> None:
        """Sweep, check the invariants, publish atomically."""
        self._sweep_running = True
        try:
            block, positions, report = await self.client.sweep_positions()
        except Exception as exc:  # noqa: BLE001 — documented not to raise
            logger.warning("FWA position sweep raised: %s", exc)
            # A sweep that never ran violated no invariant.  Flipping the flag
            # here made a dead RPC render "invariant mismatch", naming the wrong
            # cause on the single most common failure — and contradicting the
            # note in _blank_payload that a *missing* sweep is reported through
            # degraded_sources.  The chain pool is already marked degraded, so
            # the honest render is "degraded: chain" alone.
            block, positions, report = 0, [], {
                "invariants_ok": True,
                "sweep_failed": True,
                "skipped": False,
                "mismatches": (f"sweep raised: {exc}",),
            }
        finally:
            self._sweep_running = False

        report = report or {}
        out["sweep_report"] = report
        if report.get("skipped"):
            out["sweep_skipped"] = True

        # The runtime aggregate assertions, on pairs read at the *same* pinned
        # block.  Comparing a pinned sweep against the unpinned hot batch would
        # manufacture mismatches: the pool grew 53% in two days.
        ok = bool(report.get("invariants_ok"))
        ok = ok and bool(
            _safe_call(
                invariant_summary,
                swept_total_weight=report.get("total_weight_computed"),
                chain_total_weight=report.get("total_weight_onchain"),
                swept_weighted_backing=report.get("weighted_backing_total_computed"),
                chain_weighted_backing=report.get("weighted_backing_total_onchain"),
                derived_fee_wei=report.get("acquisition_fee_computed"),
                chain_fee_wei=report.get("acquisition_fee_onchain"),
                fee_share_total=report.get("collected"),
                active_listing_count=report.get("expected"),
                default=False,
            )
        )
        self._invariants_ok = ok

        if block > 0 and positions:
            stored = self.cache.set_sweep(block, positions, invariants_ok=ok, ts=now)
            if stored and ok:
                self.cache.mark_fetched(TIER_MEDIUM, now)
            else:
                if not ok:
                    # Flags the slot stale and marks the tier due; the backoff
                    # below then spaces the retry so a persistent mismatch does
                    # not turn into a per-tick sweep loop.
                    self.cache.note_invariant_mismatch(
                        "; ".join(str(m) for m in report.get("mismatches", ()))
                    )
                self.cache.mark_failed(TIER_MEDIUM, now)
                self._error_count += 1
        elif not report.get("skipped"):
            self.cache.mark_failed(TIER_MEDIUM, now)
            self._error_count += 1
            out["failed"] = True

    async def _fetch_core_balance(self) -> int | None:
        """``eth_getBalance(core)`` — the only "value held" source (PRD §7 rule 4).

        ``0`` is how the client reports failure and the core has never held zero,
        so a zero is treated as unavailable and the last known figure is kept
        rather than punching a hole in the meta row.
        """
        try:
            balance = await self.client.fetch_eth_balance()
        except Exception as exc:  # noqa: BLE001
            logger.debug("eth_getBalance(core) raised: %s", exc)
            return None
        value = _opt_int(balance)
        return value if value and value > 0 else None

    @staticmethod
    def _hot_usable(hot: dict[str, Any]) -> bool:
        """Did the aggregate3 batch decode anything at all?

        Not ``hot["_ok"]``: that demands *every* view, including
        ``tokenShareBps`` and the quote, which fail independently and often.  One
        decoded core aggregate is enough to call the batch a success.
        """
        return any(
            hot.get(key) is not None
            for key in ("acquisition_fee", "active_listing_count", "total_weight")
        )

    def _apply_backing_updates(self) -> None:
        """``BackingUpdated`` newer than the pinned sweep invalidates it (rule 8)."""
        block = self.cache.sweep_block
        if not block:
            return
        try:
            updates = self.logs.backing_updates(since=block + 1)
        except Exception as exc:  # noqa: BLE001
            logger.debug("backing_updates lookup failed: %s", exc)
            return
        newest = max((int(u.get("block_number", 0)) for u in updates), default=0)
        if newest > block:
            self.cache.note_backing_updated(newest)

    # ------------------------------------------------------------------
    # Pool B — event logs (FWALogClient).  The single point of failure.
    # ------------------------------------------------------------------

    async def _pool_logs(self, tiers: set[str], now: float) -> dict[str, Any]:
        """Backfill (once) or tail (30 s), then snapshot.

        When the endpoint is down this still returns a payload — the in-process
        aggregates if a scan ever succeeded this run, otherwise the cache's
        persisted last-good — together with the ``as_of_ts`` it was captured at.
        ``live`` says which.  Nothing stale is ever reported as live.
        """
        out: dict[str, Any] = {
            "payload": None,
            "live": False,
            "as_of_ts": None,
            "reason": REASON_UNAVAILABLE,
            "config_events": None,
            "allowed_collections": [],
            "once_done": self._log_backfill_done,
        }

        scanned, once_done = await self._scan_logs(tiers, now)
        out["once_done"] = out["once_done"] or once_done
        if scanned:
            self._all_time_counts = self._all_time_event_counts()

        snap = self.logs.snapshot(feed_limit=self._feed_limit)
        self._correct_windowed_aggregates(snap)
        live = bool(snap.get("available"))
        out["live"] = live
        out["reason"] = None if live else (snap.get("reason") or REASON_UNAVAILABLE)

        if live:
            if scanned:
                self.cache.mark_fetched(TIER_TAIL, now)
            self.cache.set_log_aggregates(
                {key: snap.get(key) for key in _LOG_CACHE_KEYS}
                | {"crown_history": (snap.get("crown_history") or [])[:CROWN_HISTORY_CAP]},
                ts=snap.get("as_of_ts") or now,
                block=_opt_int(snap.get("last_seen_block")),
            )
            out["payload"] = snap
            out["as_of_ts"] = snap.get("as_of_ts") or now
        else:
            if scanned:
                self.cache.mark_failed(TIER_TAIL, now)
                self._error_count += 1
            if self._has_log_content(snap):
                # A scan succeeded earlier this run and then the endpoint went
                # away: the in-process aggregates are the freshest last-good.
                out["payload"] = snap
                out["as_of_ts"] = snap.get("as_of_ts")
            else:
                cached = self.cache.get_log_aggregates()
                if cached is not None and isinstance(cached.payload, dict):
                    out["payload"] = cached.payload
                    out["as_of_ts"] = cached.payload.get("as_of_ts") or cached.ts

        payload = out["payload"] or {}
        out["allowed_collections"] = list(payload.get("allowed_collections") or [])
        out["config_events"] = self._config_events(payload)
        return out

    async def _scan_logs(self, tiers: set[str], now: float) -> tuple[bool, bool]:
        """Decide between a full backfill, a bounded catch-up and a tail.

        Returns ``(scanned, once_done)``.  Three cases, cheapest first:

        * **Restored watermark, recent** — the common case.  A tail from
          ``last_seen_block``, bounded by however long the app was closed.  The
          raw retention window having aged out costs nothing here: the tail
          resumes from the *watermark*, not from the retained events.
        * **Restored watermark, stale beyond** :data:`LOG_CATCHUP_MAX_BLOCKS` — a
          fresh full backfill.  Scanning the gap would still work, but at that
          distance re-deriving is the only way to keep the settlement counts and
          crown history exact rather than exact-plus-a-hole.
        * **Nothing restored** — first install: the full history, once.
        """
        if TIER_ONCE in tiers and not self._log_backfill_done:
            head = await self._head_block()
            result = await self._full_backfill(head) if head > 0 else {}
            if result.get("available"):
                return True, True
            # The once tier has no TTL, so without an explicit backoff a failing
            # backfill would be retried on every 15 s tick.
            self.cache.mark_failed(TIER_ONCE, now)
            return head > 0, False

        if TIER_ONCE in tiers and not self._catchup_done:
            self._catchup_done = True
            head = await self._head_block()
            gap = head - self._restored_last_seen if head > 0 else 0
            if head > 0 and gap > LOG_CATCHUP_MAX_BLOCKS:
                logger.info(
                    "FWA log state is %d blocks behind the head (cap %d) — running a "
                    "full backfill instead of a catch-up so the settlement mix and "
                    "crown history stay exact",
                    gap,
                    LOG_CATCHUP_MAX_BLOCKS,
                )
                result = await self._full_backfill(head)
                return True, bool(result.get("available"))
            await self.logs.tail()
            return True, True

        if TIER_TAIL in tiers:
            await self.logs.tail()
            return True, False

        return False, False

    async def _full_backfill(self, head: int) -> dict:
        """Scan the whole history and reset the count baseline.

        After this the in-memory store *is* all-time, so the baseline is dropped:
        keeping it would double-count everything before the old baseline block.
        """
        result = await self.logs.backfill(FWA_DEPLOY_BLOCK, head)
        if result.get("available"):
            self._log_backfill_done = True
            self._catchup_done = True
            self._event_baseline = {}
            self._event_baseline_block = 0
            self._all_time_counts = None
            self._save_log_state()
        return result

    def _correct_windowed_aggregates(self, snap: dict[str, Any]) -> None:
        """Repair the two aggregates a windowed raw store would understate.

        Only reached after a windowed restore (``_event_baseline`` non-empty).

        * **Settlement mix** — WP-7 derives it from ``len(store[event])``, which
          after a windowed restore is a window, not the all-time 51,522.  The
          all-time counts are recomputed from the persisted baseline and handed
          to the same pure ``settlement_mix_rows`` the client would have used.
        * **Draw events** — ``NFTAllocated`` carries no collection address, so a
          draw whose ``NFTListed`` log predates the window would render the zero
          address.  The sweep-derived listing index is merged in on top of the
          log-derived one, which covers every listing that was live recently.

        Crown history, crown totals, parameter drift and the allowlist need no
        repair: their events are retained all-time (:data:`LOG_ALLTIME_EVENTS`).
        """
        if not self._event_baseline:
            return

        counts = self._all_time_counts or self._all_time_event_counts()
        rows = _safe_call(
            settlement_mix_rows, {name: counts.get(name, 0) for name in SETTLEMENT_EVENTS}
        )
        if rows:
            snap["settlement_mix"] = rows
        snap["event_counts"] = dict(counts)

        if not self._listing_index:
            return
        try:
            merged = {**self.logs.listing_index(), **self._listing_index}
            draws = self.logs.draw_events(self._feed_limit, merged)
        except Exception as exc:  # noqa: BLE001
            logger.debug("re-resolving draw collections failed: %s", exc)
            return
        snap["draw_events"] = [row.model_dump() for row in draws]

    def _remember_listings(self, positions: tuple[Position, ...]) -> None:
        """Accumulate the sweep's listing index, FIFO-bounded, memory only."""
        for position in positions:
            self._listing_index[position.listing_id] = {
                "collection": str(position.collection).lower(),
                "token_id": position.token_id,
            }
        overflow = len(self._listing_index) - LISTING_INDEX_MAX
        if overflow > 0:
            for key in list(self._listing_index)[:overflow]:
                self._listing_index.pop(key, None)

    async def _head_block(self) -> int:
        try:
            return int(await self.logs.head_block())
        except Exception as exc:  # noqa: BLE001
            logger.debug("log head_block failed: %s", exc)
            return 0

    def _config_events(self, payload: dict[str, Any]) -> list[dict]:
        """Raw ``ConfigSet`` entries when we hold them, else the cached history.

        The raw entries are richer: ``param_drift_signal`` identifies the 21-log
        constructor write from them and can then render the ``500→100`` transition.
        The cached ``config_history`` is already launch-filtered, which still gives
        a correct change count — just a terser row.
        """
        try:
            entries = self.logs.entries("ConfigSet")
        except Exception as exc:  # noqa: BLE001
            logger.debug("ConfigSet entries unavailable: %s", exc)
            entries = []
        if entries:
            return entries
        history = payload.get("config_history")
        return list(history) if isinstance(history, list) else []

    @staticmethod
    def _has_log_content(snap: dict[str, Any]) -> bool:
        if snap.get("draw_events") or snap.get("crown_history"):
            return True
        return any(
            int(row.get("count") or 0) > 0
            for row in (snap.get("settlement_mix") or [])
            if isinstance(row, dict)
        )

    # ------------------------------------------------------------------
    # Pool C — off-chain market (FWAMarketClient)
    # ------------------------------------------------------------------

    async def _pool_market(self, tiers: set[str], now: float) -> dict[str, Any]:
        """DexScreener + GeckoTerminal + DefiLlama on the slow tier; floors never.

        The floor sweep is *detached*: at 6 s per collection it takes minutes, and
        a refresh cycle that waited for it would stall the whole dashboard.  Every
        tick reads :meth:`FWAMarketClient.cached_floors`, which does no I/O.
        """
        out: dict[str, Any] = {
            "market": None,
            "candles": [],
            "fees": None,
            "live": False,
            "floors": {},
        }

        if TIER_SLOW in tiers:
            market, market_ok = await self.market.fetch_fwa_market()
            candles, candles_ok = await self.market.fetch_ohlcv_hour(limit=OHLCV_LIMIT)
            fees, _fees_ok = await self.market.fetch_protocol_fees()
            out["market"] = market
            out["candles"] = list(candles or [])
            out["fees"] = fees
            out["live"] = bool(market_ok or candles_ok)
            if out["live"]:
                self.cache.mark_fetched(TIER_SLOW, now)
                self.cache.set_market(
                    {"market": market, "candles": out["candles"], "fees": fees},
                    ts=now,
                )
            else:
                self.cache.mark_failed(TIER_SLOW, now)
                self._error_count += 1
        else:
            # Not due: serve the cached payload and report it as not-live, which
            # is honest without being alarming — the slow tier is 15 minutes wide.
            entry = self.cache.get_market()
            if entry is not None and isinstance(entry.payload, dict):
                out["market"] = entry.payload.get("market")
                out["candles"] = list(entry.payload.get("candles") or [])
                out["fees"] = entry.payload.get("fees")
                out["live"] = True

        if out["market"] is None or not out["candles"]:
            entry = self.cache.get_market()
            if entry is not None and isinstance(entry.payload, dict):
                if out["market"] is None:
                    out["market"] = entry.payload.get("market")
                if not out["candles"]:
                    out["candles"] = list(entry.payload.get("candles") or [])
                if out["fees"] is None:
                    out["fees"] = entry.payload.get("fees")

        out["floors"] = _safe_call(self.market.cached_floors, default={}) or {}
        return out

    def _start_floor_sweep(self) -> None:
        """Kick off the background CoinGecko sweep if one is not already running."""
        if self._floor_task is not None and not self._floor_task.done():
            return
        addresses = self._collection_addresses
        if not addresses:
            return
        try:
            self._floor_task = asyncio.create_task(self._sweep_floors(addresses))
        except RuntimeError as exc:  # no running loop (shouldn't happen in the app)
            logger.debug("could not start the FWA floor sweep: %s", exc)

    async def _sweep_floors(self, addresses: tuple[str, ...]) -> None:
        """Background floor sweep; persists each quote into the cache.  Never raises."""
        try:
            quotes, _available = await self.market.fetch_nft_floors(addresses)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("FWA floor sweep failed: %s", exc)
            return
        for address, quote in (quotes or {}).items():
            _safe_call(
                self.cache.set_floor,
                address,
                quote.floor_eth,
                source=quote.source,
                note=quote.note,
                ts=quote.fetched_at or None,
            )

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _assemble(
        self,
        now: float,
        state: dict[str, Any],
        logs: dict[str, Any],
        market: dict[str, Any],
        degraded: list[str],
    ) -> dict[str, Any]:
        """Build the flat dict.  Every branch here is a rendering decision."""
        hot: dict[str, Any] = state.get("hot") or {}
        positions: tuple[Position, ...] = state.get("positions") or ()
        report: dict[str, Any] = state.get("sweep_report") or {}
        floors = market.get("floors") or {}

        self._remember_listings(positions)
        odds_stale = bool(state.get("sweep_stale")) or not self._invariants_ok
        names = {
            str(addr).lower(): (getattr(quote, "name", None) or None)
            for addr, quote in floors.items()
        }

        # -- price legs.  Never a computed guess, never a sum. ----------------
        fee_wei = _opt_int(_first(hot.get("quote_fee_wei"), hot.get("acquisition_fee")))
        vrf_wei = _opt_int(hot.get("quote_vrf_wei"))
        quote_total_wei = _opt_int(hot.get("quote_total_wei"))
        payout_bps = _opt_int(hot.get("settlement_discount_bps"))
        if payout_bps is None:
            payout_bps = fwa_ev.DEFAULT_PURCHASER_PAYOUT_BPS

        # -- pool temperature (the rebate share the EV needs) -----------------
        last_acq_ts = _opt_int(hot.get("last_acquisition_ts"))
        gap = None if not last_acq_ts else max(0, int(now) - last_acq_ts)
        pool_temp = _safe_call(
            resolve_pool_temp,
            gap,
            token_share_bps=_opt_int(hot.get("token_share_bps")),
            hot_gap=_opt_int(hot.get("hot_gap")) or 0,
            cold_gap=_opt_int(hot.get("cold_gap")) or 0,
            forced_bps=_first(_opt_int(hot.get("forced_token_share_bps")), -1),
        )
        rebate_share = 0.0
        if pool_temp is not None and pool_temp.token_share_bps is not None:
            rebate_share = pool_temp.token_share_bps / fwa_ev.BPS

        # -- position-derived aggregates --------------------------------------
        pairs = [(p.backing_wei, p.collection) for p in positions if p.backing_wei > 0]
        backings = [backing for backing, _collection in pairs]
        total_weight = _safe_call(fwa_ev.total_weight, backings, default=0) or 0

        harmonic_wei = _safe_call(fwa_ev.harmonic_mean_wei, backings, default=0) or 0
        # Fact 4: the exact arithmetic mean comes from the sweep's own backing
        # total, not from eth_getBalance(core) — which also holds escrow and
        # accrued owner fees and is therefore an upper bound.
        backing_total_wei = _opt_int(report.get("backing_total_wei"))
        if backing_total_wei is None and backings:
            backing_total_wei = sum(backings)
        arithmetic_wei = (
            backing_total_wei // len(backings) if backing_total_wei and backings else 0
        )
        # Fact 5: a live ratio, recomputed every tick.  3.885x on the pinned
        # distribution, <=3.49x two days later — never a constant.
        gap_x = (arithmetic_wei / harmonic_wei) if harmonic_wei > 0 else None

        # -- the EV band ------------------------------------------------------
        # Fact 2: floors_for_ev omits unpriced collections. A 0.0 default would
        # raise lower_eth and inflate collections_priced.
        floors_eth = _safe_call(floors_for_ev, floors, default={}) or {}
        band = None
        if pairs and fee_wei is not None:
            band = _safe_call(
                fwa_ev.pull_ev_band,
                pairs,
                floors_eth,
                fee_wei,
                payout_bps,
                rebate_share,
            )
        pull_ev = None
        if band is not None:
            pull_ev = _safe_call(
                PullEV,
                lower_eth=band["lower_eth"],
                best_eth=band["best_eth"],
                fee_eth=band["acquisition_fee_eth"],
                rebate_eth=band["rebate_eth"],
                collections_priced=band["collections_priced"],
                collections_total=band["collections_total"],
                weight_priced_pct=band["weight_priced_pct"],
            )
        # An EV from an incomplete sweep is *wrong*, not stale, so it is withheld
        # rather than labelled (PRD §7 rule 11).  The odds board keeps rendering
        # with odds_stale=True, because a listing is still a listing.
        ev_available = pull_ev is not None and not odds_stale

        odds_rows = self._odds_rows(positions, total_weight, floors, names)
        chase_rows = self._chase_rows(positions, total_weight, fee_wei, payout_bps, names)

        # -- crown ------------------------------------------------------------
        crown = self._crown(hot, positions)
        eth_usd = self._eth_usd(market.get("market"))
        crown_pot_eth = _wei_to_eth(crown.pot_wei) if crown is not None else None

        # -- signals ----------------------------------------------------------
        live_params = {
            key: int(hot[view])
            for key, view in _LIVE_PARAM_VIEWS.items()
            if hot.get(view) is not None
        }
        config_events = logs.get("config_events") or []
        # Resolved live-vs-last-``ConfigSet`` (never live-vs-documented, rule 6).
        # The flat contract has no parameter table, so these are held for the
        # status bar / a future drill-down and, more usefully, they make an
        # owner write loud: the owner is a plain EOA with no multisig and no
        # timelock and has already moved the crown tithe mid-flight.
        self.config_params = tuple(
            _safe_call(resolve_config_params, config_events, live_params, default=[]) or ()
        )
        drifted = [p.name for p in self.config_params if p.is_drift]
        if drifted:
            logger.warning(
                "FWA live parameters disagree with the last ConfigSet: %s",
                ", ".join(drifted),
            )

        signals = {
            "pool_temp_signal": _dump(_safe_call(pool_temp_signal_for, pool_temp)),
            "buy_gate_signal": _dump(
                _safe_call(buy_gate_signal, hot.get("external_buys_enabled"))
            ),
            "emissions_signal": _dump(
                _safe_call(
                    emissions_signal,
                    now,
                    _opt_int(hot.get("emission_start")),
                    _opt_int(hot.get("emission_duration")),
                    _opt_int(hot.get("current_epoch")),
                )
            ),
            "vrf_queue_signal": _dump(
                _safe_call(
                    vrf_queue_signal,
                    _opt_int(hot.get("last_issued_sequence")),
                    _opt_int(hot.get("next_sequence_to_process")),
                    _opt_int(hot.get("pending_acquisition_count")),
                    _opt_int(hot.get("unsettled_acquisition_count")),
                    _opt_int(hot.get("unfulfilled_vrf_count")),
                    _opt_int(hot.get("subscription_native_balance")),
                    _opt_int(hot.get("minimum_subscription_buffer")),
                    _opt_int(hot.get("selection_timeout_blocks")),
                )
            ),
            "param_drift_signal": _dump(
                _safe_call(param_drift_signal, config_events, live_params)
            ),
        }

        # -- log-derived: feed + settlement -----------------------------------
        log_payload: dict[str, Any] = logs.get("payload") or {}
        log_live = bool(logs.get("live"))
        as_of = _opt_float(logs.get("as_of_ts"))
        draw_rows = [
            self._draw_row(row, names)
            for row in (log_payload.get("draw_events") or [])
            if isinstance(row, dict)
        ]
        mix_rows = [
            dict(row) for row in (log_payload.get("settlement_mix") or []) if isinstance(row, dict)
        ]
        crown_rows = [
            dict(row) for row in (log_payload.get("crown_history") or []) if isinstance(row, dict)
        ]
        settle_has_data = bool(crown_rows) or any(
            int(row.get("count") or 0) > 0 for row in mix_rows
        )

        # -- market / sparkline -----------------------------------------------
        market_payload = market.get("market") or {}
        candles = list(market.get("candles") or [])
        history = candles or self.cache.get_series(SERIES_FWA_PRICE_USD)
        fees = market.get("fees") or {}

        # -- meta --------------------------------------------------------------
        active_positions = _first(
            _opt_int(hot.get("active_listing_count")), len(positions)
        )
        current_block = max(
            _opt_int(state.get("sweep_block")) or 0,
            _opt_int(log_payload.get("last_seen_block")) or 0,
        )
        if degraded and self._last_success_ts:
            last_updated = max(0.0, now - self._last_success_ts)
        else:
            last_updated = 0.0

        payload = {
            # ---- hero: EV -------------------------------------------------
            "pull_ev_best_eth": pull_ev.best_eth if pull_ev else None,
            "pull_ev_lower_eth": pull_ev.lower_eth if pull_ev else None,
            "ev_available": ev_available,
            "ev_collections_priced": pull_ev.collections_priced if pull_ev else 0,
            "ev_collections_total": pull_ev.collections_total if pull_ev else 0,
            "ev_weight_priced_pct": pull_ev.weight_priced_pct if pull_ev else 0.0,
            "ev_rebate_eth": pull_ev.rebate_eth if pull_ev else None,
            # ---- hero: PRICE ----------------------------------------------
            "acquisition_fee_eth": _wei_to_eth(fee_wei),
            "vrf_fee_eth": _wei_to_eth(vrf_wei),
            "quote_total_eth": _wei_to_eth(quote_total_wei),
            "price_available": fee_wei is not None,
            "harmonic_mean_eth": _wei_to_eth(harmonic_wei) if harmonic_wei else None,
            "arithmetic_mean_eth": _wei_to_eth(arithmetic_wei) if arithmetic_wei else None,
            "hm_am_gap_x": gap_x,
            # ---- hero: CROWN ----------------------------------------------
            "crown_pot_eth": crown_pot_eth,
            "crown_pot_usd": (
                crown_pot_eth * eth_usd
                if crown_pot_eth is not None and eth_usd is not None
                else None
            ),
            "crown_seize_eth": _wei_to_eth(crown.seize_wei) if crown else None,
            "crown_holder": crown.depositor if crown else None,
            "crown_vacant": bool(crown.vacant) if crown else False,
            "crown_available": crown is not None,
            # ---- odds board -------------------------------------------------
            "collection_odds": odds_rows,
            "odds_available": bool(odds_rows),
            "odds_as_of_block": state.get("sweep_block"),
            "odds_stale": odds_stale,
            # ---- sparkline ---------------------------------------------------
            "fwa_price_history": history,
            "fwa_price_usd": _opt_float(market_payload.get("price_usd")),
            "fwa_price_change_24h": _opt_float(
                market_payload.get("price_change_24h_pct")
            ),
            "spark_available": bool(history),
            # ---- signals -----------------------------------------------------
            **signals,
            # ---- activity feed ------------------------------------------------
            "draw_events": draw_rows,
            # Live-but-empty is a real state ("no draws in this window"); only a
            # dead Pool B renders the paused line.
            "feed_available": log_live,
            "feed_unavailable_reason": None if log_live else logs.get("reason"),
            "feed_as_of_ts": as_of,
            # ---- chase board ----------------------------------------------------
            "chase_positions": chase_rows,
            "chase_available": bool(chase_rows),
            "crown_listing_id": (
                crown.listing_id if crown is not None and not crown.vacant else None
            ),
            # ---- settlement table ------------------------------------------------
            "settlement_mix": mix_rows,
            "crown_history": crown_rows,
            "crown_sets_total": _opt_int(log_payload.get("crown_sets_total")),
            "crown_payouts_total": _opt_int(log_payload.get("crown_payouts_total")),
            "crown_paid_eth": _opt_float(log_payload.get("crown_paid_eth")),
            "settle_available": settle_has_data,
            "settle_as_of_ts": as_of,
            # ---- meta ---------------------------------------------------------------
            "active_positions": active_positions or 0,
            "core_balance_eth": _wei_to_eth(state.get("core_balance_wei")),
            "cumulative_revenue_eth": _wei_to_eth(hot.get("splitter_total_received")),
            "take_rate_pct": _opt_float(fees.get("take_rate_pct")),
            "current_block": current_block,
            "invariants_ok": self._invariants_ok,
            "degraded_sources": degraded,
            "last_updated_seconds_ago": last_updated,
            "error_count": self._error_count,
            "poll_interval": self.poll_interval,
        }

        self._collection_addresses = tuple(
            str(row["address"]) for row in odds_rows
        ) or self._collection_addresses
        return self._finalise(payload)

    # -- row builders -----------------------------------------------------

    def _odds_rows(
        self,
        positions: tuple[Position, ...],
        total_weight: int,
        floors: dict[str, Any],
        names: dict[str, str | None],
    ) -> list[dict]:
        """One row per collection holding live positions, richest odds first."""
        if not positions:
            return []
        grouped: dict[str, dict[str, int]] = {}
        for position in positions:
            if position.backing_wei <= 0:
                continue
            address = str(position.collection).lower()
            bucket = grouped.setdefault(
                address, {"positions": 0, "weight": 0, "backing_wei": 0}
            )
            bucket["positions"] += 1
            bucket["weight"] += position.weight
            bucket["backing_wei"] += position.backing_wei

        shares = _safe_call(
            fwa_ev.collection_weight_shares,
            [(p.backing_wei, str(p.collection).lower()) for p in positions if p.backing_wei > 0],
            total_weight or None,
            default={},
        ) or {}

        rows: list[dict] = []
        for address, bucket in grouped.items():
            quote = floors.get(address)
            floor_eth = _opt_float(getattr(quote, "floor_eth", None))
            source = str(getattr(quote, "source", "missing") or "missing")
            note = str(getattr(quote, "note", "") or "")
            share = float(shares.get(address, 0.0))
            eth_backed = _wei_to_eth(bucket["backing_wei"]) or 0.0
            # ETH backed per point of draw odds — the number that makes the
            # inversion legible (137 ETH / 0.00023% for CryptoPunks).  Withheld
            # when the collection has no floor, per the CollectionOdds contract.
            per_point = (
                (eth_backed / share) if (floor_eth is not None and share > 0) else None
            )
            odds = _safe_call(
                CollectionOdds,
                address=address,
                name=names.get(address) or _short_address(address),
                positions=bucket["positions"],
                weight=bucket["weight"],
                weight_share_pct=share,
                backing_wei=bucket["backing_wei"],
                floor_eth=floor_eth,
                floor_source=source,
                eth_per_odds_point=per_point,
                floor_note=note,
            )
            if odds is None:
                continue
            rows.append(
                {
                    "rank": 0,
                    "address": odds.address,
                    "name": odds.name,
                    "positions": odds.positions,
                    "weight_share_pct": odds.weight_share_pct,
                    "eth_backed": eth_backed,
                    "floor_eth": odds.floor_eth,
                    "floor_source": odds.floor_source,
                    "eth_per_odds_point": odds.eth_per_odds_point,
                    "floor_note": odds.floor_note,
                }
            )
        rows.sort(key=lambda row: (-row["weight_share_pct"], row["address"]))
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows

    def _chase_rows(
        self,
        positions: tuple[Position, ...],
        total_weight: int,
        fee_wei: int | None,
        payout_bps: int,
        names: dict[str, str | None],
    ) -> list[dict]:
        """The richest positions, with the odds and jackpot ratio beside them."""
        if not positions:
            return []
        ranked = sorted(
            (p for p in positions if p.backing_wei > 0),
            key=lambda p: -p.backing_wei,
        )[: self._chase_row_limit]

        rows: list[dict] = []
        for rank, position in enumerate(ranked, start=1):
            address = str(position.collection).lower()
            expected = _safe_call(
                fwa_ev.expected_draws_until, position.backing_wei, total_weight
            )
            if expected is not None and expected == float("inf"):
                expected = None
            rows.append(
                {
                    "rank": rank,
                    "listing_id": position.listing_id,
                    "collection": address,
                    "collection_name": names.get(address),
                    "token_id": position.token_id,
                    "backing_eth": _wei_to_eth(position.backing_wei) or 0.0,
                    "odds_pct": (
                        _safe_call(
                            fwa_ev.selection_probability,
                            position.backing_wei,
                            total_weight,
                            default=0.0,
                        )
                        or 0.0
                    )
                    * 100.0,
                    "expected_draws": expected,
                    "jackpot_ratio": (
                        _safe_call(
                            fwa_ev.jackpot_ratio,
                            position.backing_wei,
                            fee_wei,
                            payout_bps,
                        )
                        if fee_wei
                        else None
                    ),
                    "sellback_eth": _wei_to_eth(
                        _safe_call(
                            fwa_ev.sellback_payout_wei,
                            position.backing_wei,
                            payout_bps,
                            default=0,
                        )
                    ),
                }
            )
        return rows

    def _crown(
        self, hot: dict[str, Any], positions: tuple[Position, ...]
    ) -> Crown | None:
        """The single-holder crown.  ``None`` when ``topListingId()`` is unreadable.

        ``vacant`` is authoritative and distinct from a zero pot: an empty throne
        and a throne with no tithe in it are different states.
        """
        listing_id = _opt_int(hot.get("top_listing_id"))
        if listing_id is None:
            return None
        vacant = listing_id == 0
        incumbent = None
        if not vacant:
            incumbent = next(
                (p for p in positions if p.listing_id == listing_id), None
            )
        threshold_bps = _first(_opt_int(hot.get("top_threshold_bps")), 0)
        seize_wei = 0
        if incumbent is not None:
            seize_wei = (
                _safe_call(
                    fwa_ev.crown_seize_wei,
                    incumbent.backing_wei,
                    threshold_bps or fwa_ev.DEFAULT_TOP_THRESHOLD_BPS,
                    default=0,
                )
                or 0
            )
        return _safe_call(
            Crown,
            listing_id=listing_id,
            depositor=None if incumbent is None else incumbent.depositor,
            pot_wei=_first(_opt_int(hot.get("top_listing_pot")), 0),
            seize_wei=seize_wei,
            threshold_bps=threshold_bps,
            share_bps=_first(_opt_int(hot.get("top_listing_share_bps")), 0),
            vacant=vacant,
        )

    @staticmethod
    def _draw_row(raw: dict[str, Any], names: dict[str, str | None]) -> dict:
        """One activity-feed row: the wei -> ETH boundary for ``amount_wei``."""
        collection = str(raw.get("collection") or "").lower()
        return {
            "ts": _opt_int(raw.get("ts")) or 0,
            "block_number": _opt_int(raw.get("block_number")) or 0,
            "tx_hash": str(raw.get("tx_hash") or ""),
            "purchaser": str(raw.get("purchaser") or ""),
            "collection": collection,
            "collection_name": raw.get("collection_name") or names.get(collection),
            "token_id": _opt_int(raw.get("token_id")),
            "outcome": str(raw.get("outcome") or ""),
            "outcome_label": str(raw.get("outcome_label") or ""),
            "amount_eth": _wei_to_eth(raw.get("amount_wei")) or 0.0,
        }

    @staticmethod
    def _eth_usd(market: Any) -> float | None:
        """ETH/USD derived from the one $FWA pair, or ``None``.

        ``price_usd`` and ``price_native_eth`` quote the same token, so their
        ratio is the ETH price with no extra request and no invented rate.  A
        missing leg yields ``None`` and every USD cell renders ``—``.
        """
        if not isinstance(market, dict):
            return None
        usd = _opt_float(market.get("price_usd"))
        native = _opt_float(market.get("price_native_eth"))
        if usd is None or native is None or native <= 0:
            return None
        return usd / native

    # -- series + contract enforcement -------------------------------------

    def _sample_series(self, now: float, payload: dict[str, Any]) -> None:
        """Bucket this cycle into the hourly series.  ``None`` leaves it untouched."""
        _safe_call(
            self.cache.sample_series,
            now,
            fwa_price_usd=payload.get("fwa_price_usd"),
            acquisition_fee_eth=payload.get("acquisition_fee_eth"),
            active_positions=payload.get("active_positions") or None,
            crown_pot_eth=payload.get("crown_pot_eth"),
        )

    def _finalise(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return exactly :data:`FWA_DATA_KEYS`, no more and no less.

        A missing key is filled from the blank payload and an unknown key is
        dropped with an ERROR: silently shipping a key the contract does not
        declare is how a widget ends up reading a value nobody froze.
        """
        out = self._blank_payload()
        for key, value in data.items():
            if key in out:
                out[key] = value
            else:
                logger.error(
                    "FWAManager produced %r, which is not in FWA_DATA_KEYS — dropped",
                    key,
                )
        return out

    def _blank_payload(self) -> dict[str, Any]:
        """Every key present, every source down, nothing invented."""
        payload: dict[str, Any] = dict.fromkeys(FWA_DATA_KEYS)
        payload.update(
            {
                "ev_available": False,
                "ev_collections_priced": 0,
                "ev_collections_total": 0,
                "ev_weight_priced_pct": 0.0,
                "price_available": False,
                "crown_vacant": False,
                "crown_available": False,
                "collection_odds": [],
                "odds_available": False,
                "odds_stale": True,
                "fwa_price_history": [],
                "spark_available": False,
                "draw_events": [],
                "feed_available": False,
                "chase_positions": [],
                "chase_available": False,
                "settlement_mix": [],
                "crown_history": [],
                "settle_available": False,
                "active_positions": 0,
                "current_block": 0,
                # "no invariant was violated" — a *missing* sweep is reported
                # through degraded_sources, not by flipping this flag.
                "invariants_ok": True,
                "degraded_sources": [],
                "last_updated_seconds_ago": 0.0,
                "error_count": self._error_count,
                "poll_interval": self.poll_interval,
            }
        )
        return payload


__all__ = [
    "COINGECKO_MIN_SPACING",
    "FWA_DEPLOY_BLOCK",
    "FWAManager",
]
