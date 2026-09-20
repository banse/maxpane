"""Shared base class for the per-poll time-series caches.

Six dashboards keep the same shape of cache: a handful of fixed-length
``deque`` series of ``(timestamp, value)`` points, the most recent
snapshot, and a JSON file under ``~/.maxpane/`` that survives a restart.
Those six grew independently, so the atomic-write block, the
open/JSON-decode guard, the ``isinstance(payload, dict)`` guard, the
per-point validation and the "Skipped N ..." warning were copied five
times over -- and drifted: two loaders lost the dict guard, four reached
for ``time.time()`` internally against ``rules/data.md`` ("Inject the
clock"), and one extended its deques without clearing them first.

``SeriesCache`` is the one copy.  A subclass declares its series in
``SERIES``; everything else -- ``record``, ``get_series``,
``get_latest``, ``last_updated``, ``history_size``, ``save_to_file``,
``load_from_file`` -- is inherited.  ``update()`` stays per-cache,
because only the subclass knows how to read its own snapshot, but it is
written on ``_mark`` + ``record`` rather than on bare ``deque.append``.

Two rules are enforced here rather than trusted to each caller:

* **A failed read is ``None``, never ``0``** (CLAUDE.md Conventions).
  ``record()`` takes ``float | None`` and *drops* ``None``.  A sentinel
  zero appended to one of these series is persisted by ``save_to_file``,
  so it outlives the outage that produced it and reads for ever after as
  a real measurement of zero.
* **The clock is injected.**  ``load_from_file`` takes ``now=``; the
  only wall-clock read on the load path is the ``now is None`` fallback
  for callers that genuinely mean "now".

Persisted shape is the subclass's business: ``VERSION_KEY``/``VERSION``
name a version field for the caches that already have one, and a cache
whose file carries no version key must never gain one -- an older build
reading a renamed key sees a downgrade and starts its series empty.

Thread safety: single-threaded asyncio use.  No locking is performed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from maxpane_dashboard.data.series_points import TimeSeriesPoint, coerce_points

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeriesSpec:
    """One declared time series on a :class:`SeriesCache` subclass.

    Parameters
    ----------
    name:
        The public attribute holding the ``deque``, and -- unless ``key``
        says otherwise -- the JSON key it is persisted under.  One name,
        so a rename cannot desynchronise the two halves.
    key:
        JSON key, when the persisted name differs from the attribute.
        Exists for files already on disk: ``BaseTokenCache`` keeps its
        three overview deques in ``volume_history`` and friends but has
        always written them as ``overview_volume``/``overview_eth_price``/
        ``overview_trade_count``, and renaming either half would make
        every user's ``~/.maxpane/base_cache.json`` load empty.  Leave it
        ``None`` for a new series: one name is better than two.
    maxlen:
        Per-series cap.  ``None`` -- the default -- uses the cache-wide
        ``max_history``.
    max_age:
        Series window in seconds applied when loading.  ``None`` defers
        to the ``max_age=`` argument of ``load_from_file`` (itself
        ``None`` by default, meaning "no age check": these series are
        bounded by ``maxlen``, not by a clock).
    allow_negative:
        Set for series that can legitimately go below zero.  Counts,
        prices and pool balances cannot, and a negative one is
        corruption.
    """

    name: str
    maxlen: int | None = None
    max_age: float | None = None
    allow_negative: bool = False
    key: str | None = None

    @property
    def json_key(self) -> str:
        """The key this series is persisted under."""
        return self.key if self.key is not None else self.name


class SeriesCache:
    """Base for the fixed-series, file-persisted dashboard caches.

    Subclasses declare :attr:`SERIES` and implement ``update()``.

    Parameters
    ----------
    max_history:
        Maximum number of samples to keep per series, for every spec
        that does not name its own ``maxlen``.  At a 30-second poll
        interval, 120 samples covers 60 minutes.
    """

    #: The series this cache keeps, in declaration order.  The first one
    #: is the "representative" series :attr:`history_size` counts.
    SERIES: tuple[SeriesSpec, ...] = ()

    #: JSON key holding the payload's schema version, or ``None`` for a
    #: file that has never carried one (and must not start).
    VERSION_KEY: str | None = None

    #: Schema version written under :attr:`VERSION_KEY`.
    VERSION: int = 1

    #: Log noun, e.g. ``"CatTown cache"``.  Appears in every message this
    #: class emits, so a user grepping ``~/.maxpane/maxpane.log`` can see
    #: which dashboard's file misbehaved.
    NOUN: str = "cache"

    #: What :attr:`history_size` counts, for the one log line that prints
    #: it.  ``"points"`` for the series caches; the caches keyed by
    #: bakery, token or pet override it, because saying "3 points" when
    #: the 3 means bakeries is a wrong number in a log file.
    SIZE_NOUN: str = "points"

    def __init__(self, max_history: int = 120) -> None:
        self._max_history = max_history
        for spec in self.SERIES:
            series: deque[TimeSeriesPoint] = deque(
                maxlen=spec.maxlen if spec.maxlen is not None else max_history
            )
            setattr(self, spec.name, series)
        self._latest: Any = None
        self._last_updated: float | None = None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _mark(self, snapshot: Any) -> None:
        """Store ``snapshot`` as the latest and stamp ``last_updated``."""
        self._latest = snapshot
        self._last_updated = snapshot.fetched_at

    def record(self, name: str, ts: float, value: float | None) -> bool:
        """Append ``(ts, value)`` to series ``name``; return whether it was.

        ``value is None`` means "this read failed" or "there was nothing
        to read", and the point is **dropped**, never zero-filled.  That
        is the CLAUDE.md convention -- *a failed read is ``None``, never
        ``0``; never write a sentinel into a history series* -- and it
        matters most here of all, because these series are persisted:
        a zero written during an outage is indistinguishable, once the
        outage is over, from a genuine measurement of zero, and it drags
        every sparkline scale and trend computed from the series.

        A real ``0.0`` is a value like any other and is recorded.
        """
        if value is None:
            return False
        series: deque[TimeSeriesPoint] = getattr(self, name)
        series.append((float(ts), float(value)))
        return True

    def get_series(self, name: str) -> list[TimeSeriesPoint]:
        """Return ``[(timestamp, value), ...]`` for the named series."""
        return list(getattr(self, name))

    def get_latest(self) -> Any:
        """Return the most recently stored snapshot, or ``None``."""
        return self._latest

    @property
    def last_updated(self) -> float | None:
        """Epoch timestamp of the last ``update()`` call, or ``None``."""
        return self._last_updated

    @property
    def history_size(self) -> int:
        """Number of points in the first declared series (representative).

        Caches keyed by token/pet/team override this with their key
        count; the two meanings are documented and both are asserted by
        existing tests.
        """
        if not self.SERIES:
            return 0
        return len(getattr(self, self.SERIES[0].name))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _payload(self) -> dict[str, Any]:
        """Build the dict ``save_to_file`` writes.

        ``saved_at``, ``max_history``, the version key when the subclass
        names one, one entry per declared series, then whatever
        :meth:`extra_payload` adds.
        """
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "max_history": self._max_history,
        }
        if self.VERSION_KEY is not None:
            payload[self.VERSION_KEY] = self.VERSION
        for spec in self.SERIES:
            payload[spec.json_key] = [list(pt) for pt in getattr(self, spec.name)]
        payload.update(self.extra_payload())
        return payload

    def extra_payload(self) -> dict[str, Any]:
        """Hook: extra keys to persist (keyed series, scalars).  Default none."""
        return {}

    def save_to_file(self, path: str) -> None:
        """Persist accumulated history to JSON for restart survival.

        The write is atomic: the payload goes to ``<path>.tmp`` and is
        then ``os.replace``d onto ``path``, so a crash mid-write cannot
        leave a half-written cache file behind for the next startup to
        choke on.  A failed write removes the temp file rather than
        leaving it to accumulate.
        """
        payload = self._payload()

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
            logger.info(
                "%s saved to %s (%d %s)",
                self.NOUN,
                path,
                self.history_size,
                self.SIZE_NOUN,
            )
        except OSError as exc:
            logger.warning("Failed to save %s: %s", self.NOUN, exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def before_load(self, payload: dict[str, Any], version: int) -> None:
        """Hook: run before any series is restored.  Default no-op.

        Used by caches whose older schema versions need a series cleared
        or a key migrated before the generic restore runs.
        """

    def restore_extra(
        self,
        payload: dict[str, Any],
        *,
        path: str,
        now: float,
        max_age: float | None = None,
    ) -> int:
        """Hook: restore whatever :meth:`extra_payload` wrote.

        Returns the number of points dropped, which the caller folds into
        the single "Skipped ..." warning.  Default: nothing to restore.

        It is handed the same three inputs :meth:`load_from_file` has,
        because the keyed-series caches need all of them: ``path`` for
        the warnings that name the offending file, ``now`` as the
        validation clock, and ``max_age`` because the bakery cache's
        window is supplied by its *caller* (``manager.py`` passes the
        sparkline window) rather than declared per series.
        """
        return 0

    def coerce_keyed(
        self,
        raw: Any,
        *,
        now: float,
        max_age: float | None = None,
    ) -> tuple[dict[str, list[TimeSeriesPoint]], int]:
        """Validate a dict-of-series payload, returning ``(series, dropped)``.

        For the caches keyed by token address, pet id or team name.
        Never raises: a non-dict payload, or a key whose value is not a
        list, degrades to "no history for that key" exactly as a
        corrupt point degrades to "one fewer point".
        """
        out: dict[str, list[TimeSeriesPoint]] = {}
        dropped_total = 0
        if not isinstance(raw, dict):
            return out, 0
        for key, points in raw.items():
            if not isinstance(points, list):
                continue
            good, dropped = coerce_points(points, now=now, max_age=max_age)
            dropped_total += dropped
            out[str(key)] = good
        return out, dropped_total

    def load_from_file(
        self,
        path: str,
        *,
        now: float | None = None,
        max_age: float | None = None,
    ) -> None:
        """Load previously saved history from a JSON file.

        Silently does nothing if the file is missing or corrupted.
        Existing in-memory data is replaced on successful load.

        Individual points are validated: anything unusable (``null``, a
        string, ``NaN``, a wrong-length entry, a negative value, a
        future-dated timestamp) is dropped and counted rather than
        raising, because every manager loads its cache in ``__init__``
        and one bad value used to abort MaxPane startup for every
        dashboard.

        Parameters
        ----------
        now:
            Reference clock, in epoch seconds, used to validate the
            persisted points -- a point dated in the future is
            corruption, not history.  Passing it explicitly is what
            keeps this method a pure function of its inputs: reaching
            for ``time.time()`` internally makes the same file load
            differently depending on when it is read, and on a machine
            whose clock ran fast when the file was *written* it silently
            empties the series it just saved.  ``None`` falls back to the
            wall clock for callers that genuinely mean "now".
        max_age:
            Window, in seconds, for every series whose ``SeriesSpec``
            does not name its own.  ``None`` -- the default -- disables
            the age check, which is what the deque-bounded series want.
        """
        reference = time.time() if now is None else now
        try:
            with open(path) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.info("No %s file to load (%s): %s", self.NOUN, path, exc)
            return

        if not isinstance(payload, dict):
            logger.warning(
                "%s file %s has unexpected format, skipping", self.NOUN, path
            )
            return

        version = 1
        if self.VERSION_KEY is not None:
            try:
                version = int(payload.get(self.VERSION_KEY) or 1)
            except (TypeError, ValueError):
                version = 1
        self.before_load(payload, version)

        loaded = 0
        skipped = 0
        for spec in self.SERIES:
            raw = payload.get(spec.json_key)
            if raw is not None and not isinstance(raw, list):
                # coerce_points degrades a non-list to "no points", which
                # is the right behaviour and a silent one: the series
                # empties and nothing says why.  Say why, once, naming the
                # key -- a hand-edited cache file is third-party input and
                # the user is the only one who can fix it.
                logger.warning(
                    "%s %s: series %r is not a list; cleared",
                    self.NOUN,
                    path,
                    spec.json_key,
                )
            good, dropped = coerce_points(
                raw,
                now=reference,
                max_age=spec.max_age if spec.max_age is not None else max_age,
                allow_negative=spec.allow_negative,
            )
            skipped += dropped
            series: deque[TimeSeriesPoint] = getattr(self, spec.name)
            # Clear first: a load after an update() must be a restore,
            # not a concatenation of the file onto whatever this process
            # has already sampled.
            series.clear()
            series.extend(good)
            loaded += len(series)

        skipped += self.restore_extra(
            payload, path=path, now=reference, max_age=max_age
        )

        if skipped:
            logger.warning(
                "Skipped %d unusable or expired point(s) while loading %s %s",
                skipped,
                self.NOUN,
                path,
            )
        self._log_loaded(path, loaded)

    def _log_loaded(self, path: str, loaded: int) -> None:
        """Hook: the one info line closing a successful load."""
        logger.info("Loaded %s from %s: %d total points", self.NOUN, path, loaded)


__all__ = ["SeriesCache", "SeriesSpec", "TimeSeriesPoint"]
