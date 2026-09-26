"""Tail sources for PEPEPANE: the daemon's stdout as a line stream, and the thread that follows it.

The IdentityMD daemon exposes no socket, status file or JSON output (spec §2); its
stdout is the only local event stream (§5.1). On the VPS that stream is journald
(``journalctl -u imd-worker.service -o json -f``), on the Mac it is the Docker
json-file log (``docker logs -f --tail 200 --timestamps imd-worker``). This module
turns either into ``RawLine`` records and runs one daemon thread that redacts,
classifies and queues them for ``SeatManager.drain()`` on the ordinary poll tick
(§4.3, §9). The thread never touches the ledger, a widget or Textual: it fills a
``queue.Queue`` and nothing else.

Three traps the sources exist to survive (spec §5.1, §9, §18):

* **A vacuumed journald cursor is detected from data, not from the exit code.**
  ``sd_journal_seek_cursor`` seeks to the *closest* surviving entry when the cursor
  is gone, so ``--after-cursor`` may return the oldest surviving record with exit 0.
  The first record's ``__REALTIME_TIMESTAMP`` is compared with the persisted
  ``lastTsUtc``; more than ``GAP_TOLERANCE_S`` newer (or a non-zero exit before any
  record) is a gap: the note is kept, the cursor is dropped and the next attach uses
  ``--since <lastTsUtc>``.
* **Only ``docker logs -f --tail 200`` is trusted for "latest".** On 2026-09-20 every
  other read form (``--tail 400``, ``--since``, no tail) returned a segment three
  hours stale with no error. The ``--since <watermark>`` backfill is therefore
  *untrusted*: it is ingested only when its newest daemon stamp is not older than the
  persisted watermark nor than the follower's first stamped line; otherwise it is
  discarded whole with ``STALE_BACKFILL_REASON`` -- never turned into a gap, never
  allowed to resurrect old rows.
* **A dead tail is visible.** The thread stamps ``alive_at`` at least every
  ``ALIVE_STAMP_S`` even when no line arrives, restarts an exited source with backoff
  ``BACKOFF_MIN_S`` -> ``BACKOFF_MAX_S`` and reports why through ``reason``.

Every subprocess is spawned through an injected ``popen``/``run`` seam with a list
argv, never a shell; ``run`` always carries ``timeout=``; every ``Popen`` owner has a
documented ``stop_timeout_s`` used by ``close()``. Tests use ``ListLineSource`` and
never a real ``journalctl`` or ``docker`` (spec §14).
"""

from __future__ import annotations

import json
import logging
import os
import re
import select
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol

from maxpane_dashboard.analytics import seat_redact
from maxpane_dashboard.data.seat_models import parse_iso

logger = logging.getLogger(__name__)

# --- constants (contract §B, spec §5.1, §9) -----------------------------------------

JOURNAL_FIRST_RUN_SINCE = "-14d"   #: first journald run, no cursor and no lastTsUtc (spec §5.1)
GAP_TOLERANCE_S = 60               #: first entry newer than lastTsUtc + 60 s -> gap (spec §5.1, §9)
DOCKER_TAIL_LINES = 200            #: the ONLY trusted docker logs form is -f --tail 200 (spec §5.1 Mac)
DOCKER_BACKFILL_TIMEOUT_S = 25     #: the one-shot --since backfill is bounded like every docker call (spec §4.2)
BACKOFF_MIN_S = 1                  #: restart backoff floor (spec §9)
BACKOFF_MAX_S = 30                 #: restart backoff ceiling (spec §9, §18)
ALIVE_STAMP_S = 1.0                #: the thread stamps aliveAt every second even with no lines (spec §9)
TAIL_FILE = "seat_tail.json"       #: under ~/.maxpane (spec §9 Watermarks)
KIND_JOURNALD = "journald"
KIND_DOCKER = "docker-log"
KIND_LIST = "list"

#: (invented) docker cold start: the --since window when no watermark exists yet; docker
#: accepts Go durations, and 336h is the 14 days JOURNAL_FIRST_RUN_SINCE gives journald (spec §5.6).
DOCKER_FIRST_RUN_SINCE = "336h"
#: (invented) the docker dedup set holds the last 2,000 (ts, text) keys (contract C.7 rule).
DEDUP_KEYS_MAX = 2000
#: (invented) default unit / container names, as spec §1 names them.
WORKER_UNIT_DEFAULT = "imd-worker.service"
CONTAINER_DEFAULT = "imd-worker"

#: The daemon's own stamp: ``<ISO-8601 ms Z> `` (spec §5.1 Format). Used here only to pick
#: the newest stamp of a backfill body before anything is classified; the grammar's ``TS``
#: (WP2) is the same shape and should import this constant rather than restate it.
DAEMON_STAMP_RE = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z) ", re.ASCII)
#: Docker's ``--timestamps`` prefix: RFC3339Nano, which Go trims to as few fractional digits
#: as the value needs (0-9), always followed by one space. With ``--timestamps`` every line
#: carries exactly one, so exactly one is stripped and the daemon's own stamp remains.
DOCKER_TS_PREFIX_RE = re.compile(
    r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d) ", re.ASCII
)

STALE_BACKFILL_REASON = "backfill stale segment, discarded"

Clock = Callable[[], float]
Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


# --- line records and the source protocol -------------------------------------------


@dataclass(frozen=True)
class RawLine:
    """One line as a source delivers it, before redaction and classification."""

    text: str                        # the daemon line (Docker prefix already stripped; journald MESSAGE)
    cursor: str | None = None        # journald __CURSOR
    invocation: str | None = None    # journald _SYSTEMD_INVOCATION_ID
    realtime_us: int | None = None   # journald __REALTIME_TIMESTAMP (microseconds)
    trusted: bool = True             # False for a docker --since backfill body


class LineSource(Protocol):
    """A follower over the daemon's stdout.

    ``lines()`` blocks and yields ``RawLine`` records; it yields ``None`` as an idle tick
    at least every ``ALIVE_STAMP_S`` while no line arrives, so the owning thread can stamp
    ``alive_at`` without a second thread. It returns when the underlying process exits.
    """

    kind: str

    def open(self) -> None: ...
    def lines(self) -> Iterator[RawLine | None]: ...
    def exit_code(self) -> int | None: ...
    def close(self) -> None: ...
    def backfill(self) -> list[RawLine] | None: ...


def split_docker_prefix(raw: str) -> tuple[str | None, str]:
    """Split Docker's ``--timestamps`` prefix off ``raw``: ``(docker_stamp, rest)``.

    ``docker_stamp`` is ``None`` when the line carries no prefix. The daemon's own
    ``<ISO ms Z>`` stamp, when present, is the first token of ``rest``.
    """
    match = DOCKER_TS_PREFIX_RE.match(raw)
    if match is None:
        return None, raw
    return raw[: match.end() - 1], raw[match.end():]


def daemon_stamp(text: str) -> str | None:
    """The daemon's ``<ISO ms Z>`` stamp at the head of ``text``, or ``None`` when unstamped."""
    match = DAEMON_STAMP_RE.match(text)
    return match.group("ts") if match else None


def realtime_us_to_iso(realtime_us: int) -> str:
    """``__REALTIME_TIMESTAMP`` (microseconds) -> the daemon's ``YYYY-MM-DDTHH:MM:SS.mmmZ`` shape."""
    seconds, rest = divmod(int(realtime_us), 1_000_000)
    stamp = datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{stamp}.{rest // 1000:03d}Z"


def journal_since_arg(last_ts_utc: str | None) -> str:
    """The ``--since`` value for a fallback attach: ``YYYY-MM-DD HH:MM:SS UTC`` (systemd.time(7)).

    journalctl does not take the daemon's ``T…Z`` form; it takes a space-separated stamp
    with an optional ``UTC`` suffix. Milliseconds are floored -- a duplicate second is
    harmless because ledger rows are idempotent upserts (spec §9). An unusable value falls
    back to ``JOURNAL_FIRST_RUN_SINCE`` rather than raising inside the tail thread.
    """
    epoch = parse_iso(last_ts_utc)
    if epoch is None:
        return JOURNAL_FIRST_RUN_SINCE
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# --- sources ----------------------------------------------------------------------------


def _coerce_raw(item: str | RawLine, *, trusted: bool = True) -> RawLine:
    if isinstance(item, RawLine):
        if item.trusted == trusted:
            return item
        return RawLine(item.text, item.cursor, item.invocation, item.realtime_us, trusted)
    return RawLine(text=str(item), trusted=trusted)


class ListLineSource:
    """Replay a captured log in tests and in ``--host fixture`` (spec §4.4, §14).

    ``delay_s`` sleeps between lines; ``time_scale`` replays the stamps' own spacing
    divided by that factor (``60.0`` = one minute of log per second). Both wait in
    ``ALIVE_STAMP_S`` slices and yield ``None`` ticks meanwhile, exactly like the real
    sources. ``exit_code`` is what ``exit_code()`` reports once the list is exhausted.
    """

    kind = KIND_LIST

    def __init__(
        self,
        lines: Iterable[str | RawLine],
        *,
        backfill: Iterable[str | RawLine] | None = None,
        exit_code: int = 0,
        delay_s: float = 0.0,
        time_scale: float | None = None,
    ) -> None:
        self._lines = [_coerce_raw(item) for item in lines]
        self._backfill = None if backfill is None else [
            _coerce_raw(item, trusted=False) for item in backfill
        ]
        self._scripted_exit = exit_code
        self._delay_s = max(0.0, float(delay_s))
        self._time_scale = time_scale
        self._exit: int | None = None
        self._opened = False

    def open(self) -> None:
        self._opened = True
        self._exit = None

    def _pause(self, seconds: float) -> Iterator[None]:
        remaining = seconds
        while remaining > 0:
            slice_s = min(ALIVE_STAMP_S, remaining)
            time.sleep(slice_s)
            remaining -= slice_s
            yield None

    def lines(self) -> Iterator[RawLine | None]:
        previous_epoch: float | None = None
        for raw in self._lines:
            if self._delay_s:
                yield from self._pause(self._delay_s)
            if self._time_scale:
                stamp = daemon_stamp(raw.text)
                epoch = parse_iso(stamp) if stamp else None
                if epoch is not None and previous_epoch is not None and epoch > previous_epoch:
                    yield from self._pause((epoch - previous_epoch) / self._time_scale)
                if epoch is not None:
                    previous_epoch = epoch
            yield raw
        self._exit = self._scripted_exit

    def exit_code(self) -> int | None:
        return self._exit

    def close(self) -> None:
        self._opened = False

    def backfill(self) -> list[RawLine] | None:
        return None if self._backfill is None else list(self._backfill)


__all__ = [
    "ALIVE_STAMP_S", "BACKOFF_MAX_S", "BACKOFF_MIN_S", "CONTAINER_DEFAULT", "DAEMON_STAMP_RE",
    "DEDUP_KEYS_MAX", "DOCKER_BACKFILL_TIMEOUT_S", "DOCKER_FIRST_RUN_SINCE", "DOCKER_TAIL_LINES",
    "DOCKER_TS_PREFIX_RE", "GAP_TOLERANCE_S", "JOURNAL_FIRST_RUN_SINCE", "KIND_DOCKER",
    "KIND_JOURNALD", "KIND_LIST", "LineSource", "ListLineSource", "RawLine",
    "STALE_BACKFILL_REASON", "TAIL_FILE", "WORKER_UNIT_DEFAULT", "daemon_stamp",
    "journal_since_arg", "realtime_us_to_iso", "split_docker_prefix",
]
