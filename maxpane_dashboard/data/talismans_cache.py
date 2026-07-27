"""Persistent state for the Talismans NFT dashboard (WP3b).

Tracks:

* The current live per-token state (``tokens``), keyed by token id.
* The set of all known token ids (``known_ids``): genesis 1..1536 plus every
  id ever produced as an operation output.
* A ring buffer of the most recent 200 activity events (``activity_log``),
  newest first.
* Hourly distribution samples: mythic count, total token count, and operation
  counts -- each 168 hours (7 days) deep, for the sparkline widgets.
* Cumulative counters (operations, mythics ever forged) and the one-time
  core-conservation baseline.
* A dedupe set so re-scanning overlapping block ranges never double-counts an
  operation.

Persistence: serialised to ``~/.maxpane/talismans_cache.json`` (fail-soft on
missing / corrupt file). Mirrors the patterns in
:mod:`maxpane_dashboard.data.ttt_cache` for save/load (atomic temp+rename,
per-section try/except) and hourly bucket aggregation.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque

from maxpane_dashboard.data.series_points import coerce_points
from maxpane_dashboard.data.talismans_models import (
    TalismanActivityEvent,
    TalismanToken,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache sizing
# ---------------------------------------------------------------------------

_HOURLY_HISTORY_HOURS = 168          # 7 days
_ACTIVITY_RING_BUFFER = 200

# Genesis token ids are deterministic 1..1536.
_GENESIS_FIRST_ID = 1
_GENESIS_LAST_ID = 1536


def _hour_bucket(ts: float) -> float:
    """Floor a timestamp to the start of its hour."""
    return float(int(ts // 3600) * 3600)


class TalismansCache:
    """In-memory state for one Talismans dashboard process.

    All collections are designed for single-threaded asyncio access -- no
    locking.
    """

    def __init__(self) -> None:
        # Live per-token state, keyed by token id.
        self.tokens: dict[int, TalismanToken] = {}

        # Every token id we know to exist (genesis + operation outputs).
        self.known_ids: set[int] = set()

        # Activity ring buffer, newest events first.
        self.activity_log: deque[TalismanActivityEvent] = deque(
            maxlen=_ACTIVITY_RING_BUFFER
        )

        # Hourly distribution samples, 7d deep: (hour_ts, value).
        self.mythic_hourly: deque[tuple[float, float]] = deque(
            maxlen=_HOURLY_HISTORY_HOURS
        )
        self.tokencount_hourly: deque[tuple[float, float]] = deque(
            maxlen=_HOURLY_HISTORY_HOURS
        )
        # (hour_ts, ops_in_that_hour)
        self.ops_hourly: deque[tuple[float, float]] = deque(
            maxlen=_HOURLY_HISTORY_HOURS
        )

        # Incremental scan watermark, e.g. {"ops": block_number}.
        self.last_seen_block: dict[str, int] = {}

        # Cumulative counters.
        self.operations_total: int = 0
        self.mythics_ever_forged: int = 0  # cumulative "bond" count
        self.cores_invariant_baseline: int = 0  # set once on first scan

        # Dedupe keys so re-scans don't double count operations.
        self.seen_tx_ops: set[str] = set()

    # ------------------------------------------------------------------
    # Id registry
    # ------------------------------------------------------------------

    def seed_genesis_ids(self) -> None:
        """Add the deterministic genesis ids 1..1536 to ``known_ids``."""
        self.known_ids.update(range(_GENESIS_FIRST_ID, _GENESIS_LAST_ID + 1))

    def register_result_ids(self, op: dict) -> None:
        """Add an operation's output id(s) to ``known_ids``."""
        rid = op.get("result_id")
        if rid is not None:
            self.known_ids.add(int(rid))
        rid_b = op.get("result_id_b")
        if rid_b is not None:
            self.known_ids.add(int(rid_b))

    def set_token_states(self, tokens: dict[int, TalismanToken]) -> None:
        """Replace the live token registry."""
        self.tokens = dict(tokens)

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    @staticmethod
    def _dedupe_key(event: TalismanActivityEvent) -> str:
        # result_id is the unique id created by the op (bondedId / lithicId /
        # headId / mergedId), so it distinguishes multiple same-type ops sharing
        # a tx and source token — making the key collision-proof.
        return f"{event.tx_hash}:{event.op_type}:{event.token_id_a}:{event.result_id}"

    def apply_operation(self, event: TalismanActivityEvent) -> None:
        """Record an operation event, deduping by (tx_hash, op_type, token_id_a, result_id).

        On a genuinely new event: prepend to the activity log, bump the total
        operation count, increment ``mythics_ever_forged`` for bond ops, and
        bucket the event into ``ops_hourly`` (per-hour count). Re-applying an
        already-seen event is a no-op (so overlapping re-scans never double
        count).

        Every bond fuses a matter + event token into a Mythic (see
        ``docs/talismans_game_mechanics.md``), so counting bonds == counting
        Mythic forges; ``mythics_ever_forged`` is therefore exact.
        """
        key = self._dedupe_key(event)
        if key in self.seen_tx_ops:
            return
        self.seen_tx_ops.add(key)

        self.activity_log.appendleft(event)
        self.operations_total += 1
        if event.op_type == "bond":
            self.mythics_ever_forged += 1

        bucket = _hour_bucket(event.timestamp)
        if self.ops_hourly and self.ops_hourly[-1][0] == bucket:
            self.ops_hourly[-1] = (bucket, self.ops_hourly[-1][1] + 1)
        else:
            self.ops_hourly.append((bucket, 1.0))

    def get_activity_for_display(
        self, limit: int = 25
    ) -> list[TalismanActivityEvent]:
        """Return recent activity events sorted by (block, timestamp) desc."""
        events = list(self.activity_log)
        events.sort(
            key=lambda e: (int(e.block_number or 0), int(e.timestamp or 0)),
            reverse=True,
        )
        if limit is None or limit < 0:
            return events
        return events[:limit]

    # ------------------------------------------------------------------
    # Distribution samples
    # ------------------------------------------------------------------

    def sample_distribution(
        self, now_ts: float, mythic_count: int, token_count: int
    ) -> None:
        """Sample mythic + token counts into the hourly deques.

        Dedupes by hour: if the most-recent bucket is already at the current
        hour, overwrite it instead of appending a duplicate (avoids flat
        lines from multiple samples within an hour).
        """
        bucket = _hour_bucket(now_ts)
        mval = float(mythic_count)
        tval = float(token_count)
        if self.mythic_hourly and self.mythic_hourly[-1][0] == bucket:
            self.mythic_hourly[-1] = (bucket, mval)
        else:
            self.mythic_hourly.append((bucket, mval))
        if self.tokencount_hourly and self.tokencount_hourly[-1][0] == bucket:
            self.tokencount_hourly[-1] = (bucket, tval)
        else:
            self.tokencount_hourly.append((bucket, tval))

    def set_invariant_baseline_if_unset(self, total_cores: int) -> None:
        """Set the conservation baseline once, on the first complete scan."""
        if self.cores_invariant_baseline == 0 and total_cores > 0:
            self.cores_invariant_baseline = int(total_cores)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        """Persist cache to disk via atomic temp-then-rename."""
        payload = {
            "saved_at": time.time(),
            "tokens": {
                str(tid): t.model_dump() for tid, t in self.tokens.items()
            },
            "known_ids": sorted(self.known_ids),
            "activity_log": [e.model_dump() for e in self.activity_log],
            "mythic_hourly": [[float(ts), float(v)] for (ts, v) in self.mythic_hourly],
            "tokencount_hourly": [
                [float(ts), float(v)] for (ts, v) in self.tokencount_hourly
            ],
            "ops_hourly": [[float(ts), float(v)] for (ts, v) in self.ops_hourly],
            "last_seen_block": dict(self.last_seen_block),
            "operations_total": int(self.operations_total),
            "mythics_ever_forged": int(self.mythics_ever_forged),
            "cores_invariant_baseline": int(self.cores_invariant_baseline),
            "seen_tx_ops": list(self.seen_tx_ops),
        }
        tmp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, path)
            logger.info(
                "Talismans cache saved to %s (%d tokens, %d activity)",
                path,
                len(self.tokens),
                len(self.activity_log),
            )
        except OSError as exc:
            logger.warning("Failed to save Talismans cache: %s", exc)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def load_from_file(self, path: str) -> None:
        """Load saved state. Silent no-op on missing / corrupt file."""
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.info("No Talismans cache to load (%s): %s", path, exc)
            return
        if not isinstance(payload, dict):
            logger.warning("Talismans cache %s has unexpected shape", path)
            return

        # Tokens
        try:
            for tid, data in (payload.get("tokens") or {}).items():
                try:
                    self.tokens[int(tid)] = TalismanToken.model_validate(data)
                except Exception as exc:
                    logger.debug("Skipping bad token %s: %s", tid, exc)
        except Exception as exc:
            logger.warning("tokens block bad: %s", exc)

        # Known ids
        try:
            for tid in payload.get("known_ids") or []:
                self.known_ids.add(int(tid))
        except Exception as exc:
            logger.warning("known_ids block bad: %s", exc)

        # Activity (preserve stored order; appendleft would reverse it)
        try:
            self.activity_log.clear()
            for evt in payload.get("activity_log") or []:
                try:
                    self.activity_log.append(
                        TalismanActivityEvent.model_validate(evt)
                    )
                except Exception as exc:
                    logger.debug("Skipping bad activity event: %s", exc)
        except Exception as exc:
            logger.warning("activity_log block bad: %s", exc)

        # Hourly deques.
        #
        # Per-point validation via the shared helper (MEDI-14).  The previous
        # loop wrapped the whole series in one try/except, so a single bad
        # point abandoned every *remaining* point in that series -- silent
        # truncation rather than a crash.  It also accepted ``len(pt) >= 2``,
        # so a 3-element entry became a point.  ``coerce_points`` never
        # raises, drops only the offending entries, and reports the count.
        for attr in ("mythic_hourly", "tokencount_hourly", "ops_hourly"):
            try:
                deq: deque = getattr(self, attr)
                deq.clear()
                good, dropped = coerce_points(payload.get(attr))
                deq.extend(good)
                if dropped:
                    logger.warning(
                        "Skipped %d unusable point(s) in Talismans %s",
                        dropped,
                        attr,
                    )
            except Exception as exc:
                logger.warning("%s block bad: %s", attr, exc)

        # Watermarks
        try:
            for k, v in (payload.get("last_seen_block") or {}).items():
                self.last_seen_block[str(k)] = int(v)
        except Exception:
            pass

        # Scalar counters
        try:
            self.operations_total = int(payload.get("operations_total") or 0)
            self.mythics_ever_forged = int(
                payload.get("mythics_ever_forged") or 0
            )
            self.cores_invariant_baseline = int(
                payload.get("cores_invariant_baseline") or 0
            )
        except Exception as exc:
            logger.warning("counters block bad: %s", exc)

        # Dedupe set
        try:
            for key in payload.get("seen_tx_ops") or []:
                self.seen_tx_ops.add(str(key))
        except Exception:
            pass

        logger.info(
            "Loaded Talismans cache from %s: %d tokens, %d known ids, %d activity",
            path,
            len(self.tokens),
            len(self.known_ids),
            len(self.activity_log),
        )


__all__ = ["TalismansCache"]
