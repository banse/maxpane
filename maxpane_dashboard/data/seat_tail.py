"""Tail sources for PEPEPANE: the daemon's stdout as a line stream, and the thread that follows it.

The IdentityMD daemon exposes no socket, status file or JSON output (spec §2); its
stdout is the only local event stream (§5.1). On the VPS that stream is journald
(``journalctl -u imd-worker.service -o json -f``), on the Mac it is the Docker
json-file log (``docker logs -f --tail 200 --timestamps imd-worker``). This module
turns either into ``RawLine`` records and runs one daemon thread that classifies,
redacts and queues them for ``SeatManager.drain()`` on the ordinary poll tick
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
from dataclasses import asdict, dataclass, replace
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


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


# --- persisted state --------------------------------------------------------------------

_STATE_KEYS = {
    "kind": "kind", "cursor": "cursor", "lastTsUtc": "last_ts_utc",
    "invocation": "invocation", "watermarkTs": "watermark_ts",
}


@dataclass
class TailState:
    """``~/.maxpane/seat_tail.json`` -- the follower's watermark (spec §9 Watermarks).

    ``cursor`` is journald's ``__CURSOR``; ``last_ts_utc`` is the newest DAEMON stamp
    ingested on either runtime (never Docker's ``-t`` stamp, never "last line seen");
    ``watermark_ts`` equals ``last_ts_utc`` for docker and is kept separate for clarity.
    """

    version: int = 1
    kind: str | None = None
    cursor: str | None = None
    last_ts_utc: str | None = None
    invocation: str | None = None
    watermark_ts: str | None = None

    @classmethod
    def load(cls, path: Path) -> "TailState":
        """Read ``path``; a missing, corrupt, foreign-version or non-object file yields defaults."""
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.info("no tail state to load (%s): %s", path, exc)
            return cls()
        if not isinstance(payload, dict) or payload.get("version") != 1:
            logger.warning("tail state %s has an unexpected shape; starting fresh", path)
            return cls()
        state = cls()
        for json_key, attr in _STATE_KEYS.items():
            setattr(state, attr, _str_or_none(payload.get(json_key)))
        return state

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        return {"version": self.version, **{k: data[attr] for k, attr in _STATE_KEYS.items()}}

    def save(self, path: Path) -> None:
        """Atomic write (tmp + ``os.replace``), mode 0600. Never raises: a failed save is logged."""
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.to_payload(), handle)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("failed to save tail state %s: %s", path, exc)
            try:
                os.remove(tmp)
            except OSError:
                pass


# --- gap and stale-backfill rules (pure) ------------------------------------------------


def detect_gap(*, first_realtime_utc: str | None, last_ts_utc: str | None, exit_code: int | None) -> str | None:
    """The journald gap rule (spec §5.1 VPS transport, §9 Watermarks).

    Returns ``"gap <lastTs>→<first available>"`` when the first returned record is more than
    ``GAP_TOLERANCE_S`` newer than the persisted ``last_ts_utc``, **or** when the attach exited
    non-zero before delivering anything (``first_realtime_utc`` is then ``None`` and rendered
    ``?``). ``None`` when there is nothing to compare against (first run) or no gap.
    """
    if last_ts_utc is None:
        return None
    if exit_code not in (None, 0):
        return f"gap {last_ts_utc}→{first_realtime_utc or '?'}"
    if first_realtime_utc is None:
        return None
    first, last = parse_iso(first_realtime_utc), parse_iso(last_ts_utc)
    if first is None or last is None:
        return None
    if first > last + GAP_TOLERANCE_S:
        return f"gap {last_ts_utc}→{first_realtime_utc}"
    return None


def backfill_is_stale(*, newest_backfill_ts: str | None, watermark_ts: str | None, follower_first_ts: str | None) -> bool:
    """The discard rule for the untrusted docker ``--since`` body (spec §5.1 Mac transport).

    Stale when the body has no daemon stamp at all, when its newest stamp is older than the
    persisted watermark, or when it is more than ``GAP_TOLERANCE_S`` older than the first
    stamped line the trusted follower delivered.
    """
    newest = parse_iso(newest_backfill_ts)
    if newest is None:
        return True
    watermark = parse_iso(watermark_ts)
    if watermark is not None and newest < watermark:
        return True
    follower_first = parse_iso(follower_first_ts)
    if follower_first is not None and newest < follower_first - GAP_TOLERANCE_S:
        return True
    return False


def _iter_pipe_lines(proc: Any, *, tick_s: float) -> Iterator[str | None]:
    """Yield decoded lines from ``proc.stdout``; ``None`` when ``tick_s`` passes with no data.

    Reads the raw fd with ``select`` so a silent daemon never blocks the thread for longer
    than one tick. EOF (the child closed its end) ends the iteration.
    """
    fd = proc.stdout.fileno()
    buffer = b""
    while True:
        ready, _, _ = select.select([fd], [], [], tick_s)
        if not ready:
            yield None
            continue
        chunk = os.read(fd, 65536)
        if not chunk:
            if buffer:
                yield buffer.decode("utf-8", "replace").rstrip("\r")
            return
        buffer += chunk
        while True:
            newline = buffer.find(b"\n")
            if newline < 0:
                break
            line, buffer = buffer[:newline], buffer[newline + 1:]
            yield line.decode("utf-8", "replace").rstrip("\r")


def _stop_process(proc: Any, stop_timeout_s: float) -> None:
    """SIGTERM, wait ``stop_timeout_s``, then SIGKILL. Idempotent; never raises."""
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(stop_timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(1.0)
    except (OSError, ValueError):
        pass
    try:
        if proc.stdout is not None:
            proc.stdout.close()
    except (OSError, ValueError):
        pass


def _message_text(value: object) -> str:
    """journald encodes a non-UTF-8 ``MESSAGE`` as an array of byte values."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(b, int) and 0 <= b < 256 for b in value):
        return bytes(value).decode("utf-8", "replace")
    return "" if value is None else str(value)


class JournaldSource:
    """``journalctl -u <unit> -o json -f`` behind an injected ``popen`` (spec §5.1 VPS transport).

    ``cursor`` wins over ``since``: ``--after-cursor <cursor>`` when a cursor is known, else
    ``--since <since>`` (``JOURNAL_FIRST_RUN_SINCE`` on a first run, ``journal_since_arg()``
    of the last stamp on a gap fallback). ``stop_timeout_s`` is how long ``close()`` waits
    after SIGTERM before SIGKILL.
    """

    kind = KIND_JOURNALD

    def __init__(
        self,
        unit: str = WORKER_UNIT_DEFAULT,
        *,
        cursor: str | None = None,
        since: str | None = JOURNAL_FIRST_RUN_SINCE,
        popen: Callable[..., Any] = subprocess.Popen,
        stop_timeout_s: float = 5.0,
    ) -> None:
        self._unit = unit
        self._cursor = cursor
        self._since = since or JOURNAL_FIRST_RUN_SINCE
        self._popen = popen
        self._stop_timeout_s = stop_timeout_s
        self._proc: Any = None

    def argv(self) -> list[str]:
        base = ["journalctl", "-u", self._unit, "-o", "json", "-f"]
        if self._cursor:
            return base + ["--after-cursor", self._cursor]
        return base + ["--since", self._since]

    def open(self) -> None:
        argv = self.argv()
        self._proc = self._popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0
        )

    def lines(self) -> Iterator[RawLine | None]:
        if self._proc is None:
            return
        for line in _iter_pipe_lines(self._proc, tick_s=ALIVE_STAMP_S):
            if line is None:
                yield None
                continue
            raw = self._parse_record(line)
            if raw is not None:
                yield raw
        try:
            self._proc.wait(self._stop_timeout_s)
        except subprocess.TimeoutExpired:
            pass

    @staticmethod
    def _parse_record(line: str) -> RawLine | None:
        try:
            record = json.loads(line)
        except ValueError:
            return None
        if not isinstance(record, dict):
            return None
        realtime: int | None = None
        try:
            realtime = int(record["__REALTIME_TIMESTAMP"])
        except (KeyError, TypeError, ValueError):
            realtime = None
        return RawLine(
            text=_message_text(record.get("MESSAGE")),
            cursor=_str_or_none(record.get("__CURSOR")),
            invocation=_str_or_none(record.get("_SYSTEMD_INVOCATION_ID")),
            realtime_us=realtime,
        )

    def exit_code(self) -> int | None:
        return None if self._proc is None else self._proc.poll()

    def close(self) -> None:
        if self._proc is not None:
            _stop_process(self._proc, self._stop_timeout_s)

    def backfill(self) -> list[RawLine] | None:
        return None


def journald_factory(
    unit: str = WORKER_UNIT_DEFAULT,
    *,
    popen: Callable[..., Any] = subprocess.Popen,
    stop_timeout_s: float = 5.0,
) -> Callable[["TailState"], JournaldSource]:
    """The ``source_factory`` for the VPS: cursor -> ``--after-cursor``; else ``--since``.

    A state with ``cursor`` attaches after it. A state with no cursor but a ``last_ts_utc``
    (the gap fallback, spec §5.1) attaches ``--since <lastTsUtc>``; a fresh state uses
    ``JOURNAL_FIRST_RUN_SINCE``.
    """

    def make(state: TailState) -> JournaldSource:
        if state.cursor:
            return JournaldSource(unit, cursor=state.cursor, popen=popen, stop_timeout_s=stop_timeout_s)
        since = journal_since_arg(state.last_ts_utc) if state.last_ts_utc else JOURNAL_FIRST_RUN_SINCE
        return JournaldSource(unit, since=since, popen=popen, stop_timeout_s=stop_timeout_s)

    return make


class DockerLogsSource:
    """``docker logs -f --tail 200 --timestamps <container>`` plus an untrusted ``--since`` backfill.

    The follower argv is the ONLY docker read form trusted for "latest" (spec §5.1 Mac
    transport); ``--since`` is never the follower. ``backfill()`` runs the one-shot
    ``docker logs --since <watermark> --timestamps`` under ``run(timeout=backfill_timeout_s)``
    and returns its lines with ``trusted=False``; the caller decides with ``backfill_is_stale``.
    ``None`` means no backfill body (no watermark, timeout, non-zero exit or OSError).
    """

    kind = KIND_DOCKER

    def __init__(
        self,
        container: str = CONTAINER_DEFAULT,
        *,
        watermark_ts: str | None = None,
        popen: Callable[..., Any] = subprocess.Popen,
        run: Runner = subprocess.run,
        backfill_timeout_s: float = DOCKER_BACKFILL_TIMEOUT_S,
        stop_timeout_s: float = 5.0,
    ) -> None:
        self._container = container
        self._watermark_ts = watermark_ts
        self._popen = popen
        self._run = run
        self._backfill_timeout_s = backfill_timeout_s
        self._stop_timeout_s = stop_timeout_s
        self._proc: Any = None

    def follower_argv(self) -> list[str]:
        return ["docker", "logs", "-f", "--tail", str(DOCKER_TAIL_LINES), "--timestamps", self._container]

    def backfill_argv(self) -> list[str]:
        since = self._watermark_ts or DOCKER_FIRST_RUN_SINCE
        return ["docker", "logs", "--since", since, "--timestamps", self._container]

    def open(self) -> None:
        argv = self.follower_argv()
        self._proc = self._popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0
        )

    def lines(self) -> Iterator[RawLine | None]:
        if self._proc is None:
            return
        for line in _iter_pipe_lines(self._proc, tick_s=ALIVE_STAMP_S):
            if line is None:
                yield None
                continue
            _, text = split_docker_prefix(line)
            yield RawLine(text=text)
        try:
            self._proc.wait(self._stop_timeout_s)
        except subprocess.TimeoutExpired:
            pass

    def exit_code(self) -> int | None:
        return None if self._proc is None else self._proc.poll()

    def close(self) -> None:
        if self._proc is not None:
            _stop_process(self._proc, self._stop_timeout_s)

    def backfill(self) -> list[RawLine] | None:
        argv = self.backfill_argv()
        try:
            completed = self._run(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=self._backfill_timeout_s,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("docker logs --since backfill failed: %s", exc)
            return None
        if completed.returncode != 0:
            logger.warning("docker logs --since backfill exited rc=%s", completed.returncode)
            return None
        body = completed.stdout or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        out: list[RawLine] = []
        for line in body.split("\n"):
            line = line.rstrip("\r")
            if not line:
                continue
            _, text = split_docker_prefix(line)
            out.append(RawLine(text=text, trusted=False))
        return out


def docker_factory(
    container: str = CONTAINER_DEFAULT,
    *,
    popen: Callable[..., Any] = subprocess.Popen,
    run: Runner = subprocess.run,
    backfill_timeout_s: float = DOCKER_BACKFILL_TIMEOUT_S,
    stop_timeout_s: float = 5.0,
) -> Callable[["TailState"], DockerLogsSource]:
    """The ``source_factory`` for the Mac: the trusted follower plus the untrusted backfill."""

    def make(state: TailState) -> DockerLogsSource:
        return DockerLogsSource(
            container, watermark_ts=state.watermark_ts, popen=popen, run=run,
            backfill_timeout_s=backfill_timeout_s, stop_timeout_s=stop_timeout_s,
        )

    return make


# --- the thread -------------------------------------------------------------------------


class TailThread:
    """One daemon thread: source -> classify raw -> redact output -> ``queue`` (spec §4.3, §9).

    The thread only fills the queue. It persists ``state`` to ``state_path`` on its
    one-second tick while the queue is empty (i.e. after each drained batch) and on ``stop()``;
    ``classify=None`` resolves to ``seat_log_grammar.classify`` at construction so this module
    imports without WP2 and tests inject their own.
    """

    def __init__(
        self,
        source_factory: Callable[[TailState], LineSource],
        queue: "queue.Queue[Any]",
        *,
        state: TailState,
        state_path: Path | None,
        now: Clock = time.time,
        backoff: tuple[float, float] = (BACKOFF_MIN_S, BACKOFF_MAX_S),
        redact: Callable[[str], str] = seat_redact.redact,
        classify: Callable[..., Any] | None = None,
    ) -> None:
        if classify is None:
            from maxpane_dashboard.data.seat_log_grammar import classify as classify_default
            classify = classify_default
        self._source_factory = source_factory
        self._queue = queue
        self._state = state
        self._state_path = None if state_path is None else Path(state_path)
        self._now = now
        self._backoff_min, self._backoff_max = float(backoff[0]), float(backoff[1])
        self._redact = redact
        self._classify = classify
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._source: LineSource | None = None
        self._alive_at: float | None = None
        self._reason: str | None = None
        self._gap_note: str | None = None
        self._backfill_note: str | None = None
        self._backfill_at: float | None = None
        self._restarts = 0
        self._backoff_s: float | None = None
        self._seq = 0
        self._dirty = False
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()

    # -- properties ---------------------------------------------------------------------

    @property
    def alive_at(self) -> float | None:
        return self._alive_at

    @property
    def reason(self) -> str | None:
        return self._reason

    @property
    def gap_note(self) -> str | None:
        return self._gap_note

    @property
    def backfill_note(self) -> str | None:
        """Sticky: ``STALE_BACKFILL_REASON`` once a backfill was discarded (LOG footer), else ``None``."""
        return self._backfill_note

    @property
    def backfill_at(self) -> float | None:
        """Epoch of the last backfill decision (the ``HH:MM`` in ``backfill HH:MM discarded``)."""
        return self._backfill_at

    @property
    def restarts(self) -> int:
        return self._restarts

    @property
    def backoff_s(self) -> float | None:
        """The wait before the next attach after the last exit; ``None`` before any exit."""
        return self._backoff_s

    @property
    def state(self) -> TailState:
        return self._state

    # -- lifecycle ----------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="seat-tail", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        source = self._source
        if source is not None:
            source.close()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout_s)
        self.persist(force=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # never let the thread die silently (spec §18 risk row)
                logger.exception("tail thread run failed")
                self._note_exit(None, delivered=0, detail=f"crashed: {exc}")
            if self._stop.is_set():
                break
            self._wait(self._backoff_s or self._backoff_min)

    def _wait(self, seconds: float) -> None:
        remaining = float(seconds)
        while remaining > 0 and not self._stop.is_set():
            slice_s = min(ALIVE_STAMP_S, remaining)
            self._stop.wait(slice_s)
            remaining -= slice_s
            self._stamp()
            self.persist()

    # -- one source lifetime ------------------------------------------------------------

    def run_once(self) -> None:
        """Open one source, follow it until it exits, note the exit. No sleeping in here.

        Docker: the untrusted ``--since`` body from ``source.backfill()`` is held until the
        follower's first *stamped* line, then judged with ``backfill_is_stale`` against the
        watermark persisted before this attach and that first stamp; a stale body is discarded
        whole, a fresh one is emitted before the held follower lines (chronological order).

        journald: when this attach used ``--after-cursor``, the FIRST record's
        ``__REALTIME_TIMESTAMP`` goes through ``detect_gap`` against ``lastTsUtc`` -- a vacuumed
        cursor may seek to the oldest surviving entry with exit 0 (spec §5.1). A gap keeps the
        note, drops the cursor (so the factory attaches ``--since <lastTsUtc>`` next) and
        restarts at once without ingesting the mis-seeked stream. A non-zero exit *before any
        record* on a cursor attach is the same fallback; a non-zero exit after records is an
        ordinary restart from the cursor those records advanced.
        """
        self._stamp()
        used_cursor = self._state.cursor is not None
        watermark_before = self._state.watermark_ts
        try:
            source = self._source_factory(self._state)
            source.open()
        except OSError as exc:
            self._note_exit(None, delivered=0, detail=f"open failed ({exc})")
            return
        self._source = source
        self._state.kind = source.kind
        pending_backfill = source.backfill()
        held: list[RawLine] = []
        follower_first_ts: str | None = None
        delivered = 0
        restart_now = False
        try:
            for raw in source.lines():
                if self._stop.is_set():
                    break
                self._stamp()
                if raw is None:
                    self.persist()
                    continue
                if delivered == 0 and not held:
                    self._reason = None
                    if used_cursor and source.kind == KIND_JOURNALD:
                        first_iso = realtime_us_to_iso(raw.realtime_us) if raw.realtime_us is not None else None
                        note = detect_gap(first_realtime_utc=first_iso, last_ts_utc=self._state.last_ts_utc, exit_code=None)
                        if note is not None:
                            self._gap_note = note
                            self._reason = note
                            self._state.cursor = None
                            self._dirty = True
                            restart_now = True
                            break
                if pending_backfill is not None:
                    held.append(raw)
                    if follower_first_ts is None:
                        follower_first_ts = daemon_stamp(raw.text)
                    if follower_first_ts is None:
                        continue
                    delivered += self._resolve_backfill(pending_backfill, watermark_before, follower_first_ts)
                    pending_backfill = None
                    for item in held:
                        delivered += self._emit(item, source.kind)
                    held = []
                    continue
                delivered += self._emit(raw, source.kind)
        finally:
            if pending_backfill is not None:
                delivered += self._resolve_backfill(pending_backfill, watermark_before, follower_first_ts)
                for item in held:
                    delivered += self._emit(item, source.kind)
            source.close()
            self._source = None
        if self._stop.is_set():
            self.persist(force=True)
            return
        if restart_now:
            self._restarts += 1
            self._backoff_s = self._backoff_min
            self.persist(force=True)
            return
        rc = source.exit_code()
        if used_cursor and source.kind == KIND_JOURNALD and delivered == 0 and rc not in (None, 0):
            note = detect_gap(first_realtime_utc=None, last_ts_utc=self._state.last_ts_utc, exit_code=rc)
            if note is not None:
                self._gap_note = note
                self._state.cursor = None
                self._dirty = True
        self._note_exit(rc, delivered=delivered)

    def _resolve_backfill(self, body: list[RawLine], watermark_before: str | None, follower_first_ts: str | None) -> int:
        stamps = [stamp for stamp in (daemon_stamp(raw.text) for raw in body) if stamp]
        newest = max(stamps) if stamps else None
        self._backfill_at = self._now()
        if backfill_is_stale(newest_backfill_ts=newest, watermark_ts=watermark_before, follower_first_ts=follower_first_ts):
            self._reason = STALE_BACKFILL_REASON
            self._backfill_note = STALE_BACKFILL_REASON
            logger.info("%s (newest %s, watermark %s, follower first %s)", STALE_BACKFILL_REASON, newest, watermark_before, follower_first_ts)
            return 0
        self._backfill_note = None
        emitted = 0
        for raw in body:
            emitted += self._emit(raw, KIND_DOCKER)
        return emitted

    def _emit(self, raw: RawLine, kind: str) -> int:
        text = self._redact(raw.text)
        try:
            line = self._classify(raw.text, invocation=raw.invocation, cursor=raw.cursor, seq=self._seq + 1)
            fields = getattr(line, "fields", None)
            cleaned = {} if fields is None else {"fields": {key: self._redact(value) if isinstance(value, str) else value for key, value in fields.items()}}
            line = replace(line, text=self._redact(line.text), **cleaned)
        except Exception:  # a hostile line must never kill the follower
            logger.exception("classify failed; line dropped")
            return 0
        ts = getattr(line, "ts", "") or ""
        if kind == KIND_DOCKER and ts:
            key = (ts, getattr(line, "text", text))
            if key in self._seen:
                return 0
            self._seen[key] = None
            while len(self._seen) > DEDUP_KEYS_MAX:
                self._seen.popitem(last=False)
        self._seq += 1
        self._queue.put(line)
        if raw.cursor is not None:
            self._state.cursor = raw.cursor
        if raw.invocation is not None:
            self._state.invocation = raw.invocation
        if ts and (self._state.last_ts_utc is None or ts > self._state.last_ts_utc):
            self._state.last_ts_utc = ts
            if kind == KIND_DOCKER:
                self._state.watermark_ts = ts
        self._dirty = True
        return 1

    def _note_exit(self, rc: int | None, *, delivered: int, detail: str | None = None) -> None:
        """Bookkeeping for one source exit: restarts, backoff 1 -> 30 s, the reason line.

        A run that delivered at least one line resets the backoff to the floor; consecutive
        empty exits double it up to ``BACKOFF_MAX_S`` (1, 2, 4, 8, 16, 30, 30 ...).
        """
        self._restarts += 1
        if self._backoff_s is None or delivered > 0:
            self._backoff_s = self._backoff_min
        else:
            self._backoff_s = min(self._backoff_s * 2, self._backoff_max)
        retry = f"retry in {int(self._backoff_s)}s"
        if detail is not None:
            self._reason = f"tail: {detail} — {retry}"
        else:
            self._reason = f"tail: exited rc={rc} — {retry}"
        self.persist(force=True)

    # -- helpers -------------------------------------------------------------------------

    def _stamp(self) -> None:
        self._alive_at = self._now()

    def persist(self, *, force: bool = False) -> None:
        """Save the state when it changed -- on the tick only while the queue is drained."""
        if not self._dirty or self._state_path is None:
            return
        if not force and not self._queue.empty():
            return
        self._state.save(self._state_path)
        self._dirty = False


__all__ = [
    'TailThread',

    'DockerLogsSource',
    'docker_factory',

    'JournaldSource',
    'journald_factory',

    'backfill_is_stale',
    'detect_gap',

    'TailState',

    "ALIVE_STAMP_S", "BACKOFF_MAX_S", "BACKOFF_MIN_S", "CONTAINER_DEFAULT", "DAEMON_STAMP_RE",
    "DEDUP_KEYS_MAX", "DOCKER_BACKFILL_TIMEOUT_S", "DOCKER_FIRST_RUN_SINCE", "DOCKER_TAIL_LINES",
    "DOCKER_TS_PREFIX_RE", "GAP_TOLERANCE_S", "JOURNAL_FIRST_RUN_SINCE", "KIND_DOCKER",
    "KIND_JOURNALD", "KIND_LIST", "LineSource", "ListLineSource", "RawLine",
    "STALE_BACKFILL_REASON", "TAIL_FILE", "WORKER_UNIT_DEFAULT", "daemon_stamp",
    "journal_since_arg", "realtime_us_to_iso", "split_docker_prefix",
]
