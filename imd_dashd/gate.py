"""The idle gate G (spec §11 steps (a)-(e)) and the plane half's dropped child.

``evaluate()`` is pure over what the broker read *fresh at apply time*: journal lines as
``(epoch, message)``, the standing child's ``{"running_count", "at"}`` (or ``None``), the outbox
file count (``None`` = unreadable), the unit state (``None`` = unreadable). Unknown fails closed
(``gate_unknown(<x>)``); no typed ack can override it. The broker never consumes the TUI's ledger --
the regexes below are a minimal, anchored copy of Appendix B (spec §11 (c)).

Run as a script (``gate.py --standing <url>``) it is the in-process ``urllib`` child the broker drops
to ``imd-worker`` for step (b): it returns only ``{"running_count": int, "at": iso}`` to root.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # python3 -I: no script dir

import json
import re
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass

IDLE_BEATS_REQUIRED = 4
IDLE_WINDOW_S = 180            #: idle beats count only heartbeats newer than now - 3 min (spec §9, §11 (a))
GATE_STANDING_TIMEOUT_S = 8
GATE_STANDING_MAX_AGE_S = 2.0  #: a standing read older than this is not "fresh" -> local-only (spec §11 (b))

TS = r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z) "
HEARTBEAT_RE = re.compile(
    TS + r"(?P<state>alive|disconnected) (?P<uptime>\d+m|\d+h\d+m|\d+d\d+h) · "
    r"(?P<work>idle|(?P<running>\d+) tasks? running) · (?P<submitted>\d+) submitted"
    r"(?: · fleet (?P<online>\d+) online, (?P<enrolled>\d+) enrolled)?"
    r"(?: · (?:paused until (?P<until>\d\d:\d\d) after (?P<failed>\d+) failed runs?(?:: (?P<reason>.*?))? — run imd doctor"
    r"|(?P<unregistered>token not registered as an agent — run imd doctor)))?$", re.ASCII)
ACCEPTED_RE = re.compile(
    TS + r"accepted (?:(?P<role>implement|tests|review|integrate) (?P<node8>[0-9a-f]{8}) — .+? \(max \d+ turns\)"
    r"|question (?P<node8_q>[0-9a-f]{8})"
    r"|campaign (?P<node8_c>[0-9a-f]{8}) — .+? \(\d+ runs\))$", re.ASCII)
TERMINAL_RE = re.compile(
    TS + r"(?:submitted (?:implement|tests|review|integrate) for [0-9a-f]{8}"
    r"|answered [0-9a-f]{8} with \d+ citation\(s\)"
    r"|counterexample for .+|campaign could not run: .+|exhausted \d+ runs, nothing found"
    r"|submission stored \([0-9a-f]{12}\) — awaiting verdict"
    r"|cancelled [0-9a-f]{8}: (?:lease_expired|job_cancelled|superseded|operator))$", re.ASCII)


def iso_utc(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def iso_utc_ms(epoch: float) -> str:
    """Millisecond stamp for the standing child's ``at`` so ``standing_age_s`` is honest (spec §11 example 0.4 s)."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + f".{int(round((epoch % 1) * 1000)) % 1000:03d}Z"


def parse_iso(text: object) -> float | None:
    """``2026-09-26T03:40:09Z`` or with fractional seconds -> epoch; ``None`` when unusable."""
    if not isinstance(text, str) or not text.endswith("Z"):
        return None
    body = text[:-1]
    frac = 0.0
    if "." in body:
        body, frac_text = body.split(".", 1)
        try:
            frac = float("0." + frac_text) if frac_text.isdigit() else 0.0
        except ValueError:
            return None
    try:
        parsed = time.strptime(body, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    import calendar
    return calendar.timegm(parsed) + frac


@dataclass
class GateResult:
    safe: bool
    reason: str | None
    idle_beats: int
    idle_beats_required: int
    newest_heartbeat_age_s: float | None
    plane: dict
    last_lifecycle_line: str | None
    lifecycle_open: bool | None
    outbox_files: int | None
    unit_active: bool | None
    graceful_stop_possible: bool | None
    unknown: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def idle_beats(lines: Sequence[tuple[float, str]], *, now: float) -> tuple[int, float | None]:
    """Consecutive ``· idle ·`` heartbeats, newest first, among heartbeats newer than ``now - IDLE_WINDOW_S``.

    Returns ``(count, newest_heartbeat_age_s)``; ``(0, None)`` when no heartbeat is in the window.
    A frozen tail therefore cannot vouch "idle" (spec §9).
    """
    count = 0
    newest_age: float | None = None
    for epoch, text in reversed(list(lines)):
        match = HEARTBEAT_RE.match(text)
        if not match:
            continue
        if epoch < now - IDLE_WINDOW_S:
            break
        if newest_age is None:
            newest_age = max(0.0, now - epoch)
        if match.group("work") != "idle":
            break
        count += 1
    return count, newest_age


def newest_lifecycle(lines: Sequence[str]) -> tuple[str | None, bool | None]:
    """The newest anchored lifecycle line and whether it leaves a task open (spec §11 (c)).

    ``(line, True)`` when the newest lifecycle line is an ``accepted …`` with no later terminal line;
    ``(line, False)`` when it is terminal; ``(None, None)`` when the window holds no lifecycle line.
    """
    for text in reversed(list(lines)):
        if ACCEPTED_RE.match(text):
            return text, True
        if TERMINAL_RE.match(text):
            return text, False
    return None, None


def _accepted_node8(line: str) -> str | None:
    match = ACCEPTED_RE.match(line)
    if not match:
        return None
    return match.group("node8") or match.group("node8_q") or match.group("node8_c")


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def evaluate(*, journal_lines: Sequence[tuple[float, str]], standing: dict | None, offline: bool,
             outbox_files: int | None, unit_active: bool | None, graceful_stop_possible: bool | None,
             now: float) -> GateResult:
    lines = list(journal_lines)
    beats, newest_age = idle_beats(lines, now=now)
    last_line, lifecycle_open = newest_lifecycle([text for _, text in lines])

    plane: dict = {"mode": "local-only", "running": None, "as_of": None, "standing_age_s": None}
    if not offline and isinstance(standing, dict):
        at = parse_iso(standing.get("at"))
        running = standing.get("running_count")
        if at is not None and isinstance(running, int) and not isinstance(running, bool):
            age = max(0.0, now - at)
            plane["as_of"] = standing.get("at")
            plane["standing_age_s"] = round(age, 1)
            if age <= GATE_STANDING_MAX_AGE_S:
                plane["mode"] = "plane+local"
                plane["running"] = running

    unknown: str | None = None
    reason: str | None = None
    if outbox_files is None:
        unknown, reason = "outbox", "gate unknown: outbox unreadable"
    elif unit_active is None:
        unknown, reason = "unit", "gate unknown: unit unreadable"
    elif lifecycle_open:
        node8 = _accepted_node8(last_line or "") or "?"
        accept_epoch = next((epoch for epoch, text in reversed(lines) if text == last_line), None)
        reason = f"task running {node8}" + (f" · {_mmss(now - accept_epoch)}" if accept_epoch is not None else "")
    elif newest_age is not None and beats == 0 and any(
            HEARTBEAT_RE.match(t) and HEARTBEAT_RE.match(t).group("work") != "idle"
            for _, t in lines[-1:] if HEARTBEAT_RE.match(t)):
        reason = "task running (newest heartbeat)"
    elif plane["mode"] == "plane+local" and plane["running"]:
        reason = f"plane reports {plane['running']} running"
    elif beats < IDLE_BEATS_REQUIRED:
        reason = f"idle {beats}/{IDLE_BEATS_REQUIRED} beats"
    elif outbox_files > 0:
        reason = f"outbox {outbox_files} file" + ("s" if outbox_files != 1 else "")
    elif unit_active is False:
        reason = "unit inactive"

    return GateResult(
        safe=reason is None, reason=reason, idle_beats=beats, idle_beats_required=IDLE_BEATS_REQUIRED,
        newest_heartbeat_age_s=None if newest_age is None else round(newest_age, 1), plane=plane,
        last_lifecycle_line=last_line, lifecycle_open=lifecycle_open, outbox_files=outbox_files,
        unit_active=unit_active, graceful_stop_possible=graceful_stop_possible, unknown=unknown,
    )
