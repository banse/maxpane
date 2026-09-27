"""Append-only JSONL audit log with a monotonic ``seq`` (spec §11 audit line, §13 "What the audit log may contain").

One line per plan, apply, verify, refusal, canary and drain event, plus an hourly ``reads`` line that
carries read-verb counts only (spec §11 "Read verbs … audited as counts only"). The caller passes names and
ids only -- never a file body, a config value, a device key or a refused skill id (spec §13). The
file is created ``0o600`` (VPS: root under ``LogsDirectory`` 0700; Mac: ``~/.maxpane/seat_audit.jsonl``).
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from imd_dashd.redact import redact_tree

Clock = Callable[[], float]

PHASES = ("plan", "apply", "verify", "refused", "canary", "drain_armed", "drain_rearmed", "drain_fire",
          "drain_cancelled", "drain_expired", "drain_lost", "reads")
AUDIT_FIELDS = ("ts", "seq", "peer_uid", "verb", "phase", "plan_id", "args", "preconditions", "outcome",
                "verified", "connected", "cursor_before", "cursor_after")


def iso_utc(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


class Audit:
    def __init__(self, path: str | Path, *, now: Clock = time.time, mode: int = 0o600) -> None:
        self._path = Path(path)
        self._now = now
        self._mode = mode
        self._seq = self._last_seq_on_disk()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def seq(self) -> int:
        return self._seq

    def _last_seq_on_disk(self) -> int:
        try:
            with self._path.open("rb") as fh:
                last = 0
                for raw in fh:
                    try:
                        seq = json.loads(raw).get("seq")
                    except (ValueError, AttributeError):
                        continue
                    if isinstance(seq, int) and seq > last:
                        last = seq
                return last
        except OSError:
            return 0

    def append(self, **fields) -> int:
        """Write one line; fills ``ts`` and ``seq``; unknown field names raise ``TypeError``; returns the seq."""
        unknown = set(fields) - set(AUDIT_FIELDS) | {"ts", "seq"} & set(fields)
        if unknown:
            raise TypeError(f"audit fields not allowed: {sorted(unknown)}")
        phase = fields.get("phase")
        if phase not in PHASES:
            raise ValueError(f"unknown audit phase {phase!r}")
        self._seq += 1
        record = {name: None for name in AUDIT_FIELDS}
        record.update(fields)
        record["ts"] = iso_utc(self._now())
        record["seq"] = self._seq
        line = (json.dumps(redact_tree(record), separators=(",", ":"), ensure_ascii=True, default=str) + "\n").encode("utf-8")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, self._mode)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
        return self._seq

    def tail(self, n: int) -> list[dict]:
        """The newest *n* records, oldest first; a corrupt line is skipped, never raised."""
        if n <= 0:
            return []
        try:
            raw_lines = self._path.read_bytes().splitlines()
        except OSError:
            return []
        out: list[dict] = []
        for raw in reversed(raw_lines):
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if isinstance(record, dict):
                out.append(record)
            if len(out) == n:
                break
        out.reverse()
        return out


__all__ = ["AUDIT_FIELDS", "Audit", "Clock", "PHASES", "iso_utc"]
