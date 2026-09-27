"""TASK: one LEDGER row's local facts and the plane's row, side by side (spec §8 LEDGER ``»``).

The record-detail frame (``screens/record_detail.py``: bordered box, focused
scroll, ``PRESS SPACE OR ESC TO CLOSE``) with two sections. LOCAL is what the
daemon's stdout and the runtime's transcript say -- stamps, phases seen, session
files, tokens by class, ttft, wall, effort, the work-dir abnormal flag. PLANE is
what ``api.imd.fun`` says -- the job (linked on the IMD explorer), the node key,
the plane's accept stamp, the verdict and its lag, the failure reason and class
as enum words. **Never prompts, tool outputs or summaries** (safety §5.4): the
objective and the agent's sentence are prose NOW already shows, API error
messages are raw runtime text -- only their statuses are counted here.

The base's ``_title`` reads ``job_id``, ``node_key``, ``submitted_ts``/``accepted_ts``
(epoch seconds) and ``role``; :func:`adapt_row` supplies them from the frozen
``SEAT_ROW_KEYS["seat_tasks_rows"]`` shape.
"""

from __future__ import annotations

from copy import deepcopy

from rich.text import Text

from maxpane_dashboard.analytics.seat_redact import redact
from maxpane_dashboard.analytics.seat_signals import as_of_hhmm, parse_iso
from maxpane_dashboard.analytics.seat_tiers import tier_label
from maxpane_dashboard.screens.record_detail import RecordDetailScreen
from maxpane_dashboard.widgets.address import job_text
from maxpane_dashboard.widgets.explorer import IMD
from maxpane_dashboard.widgets.fmt import DASH, EMDASH, as_float, fmt_age, fmt_int, mmdd_hhmm
from maxpane_dashboard.widgets.markup_safety import strip_tags
from maxpane_dashboard.widgets.seat_words import seat_token

__all__ = ["LOCAL_FIELDS", "NEVER_SHOWN", "PLANE_FIELDS", "SeatTaskDetail", "adapt_row"]

#: Row fields the LOCAL section may read.
LOCAL_FIELDS = (
    "acceptedUtc", "submittedUtc", "storedUtc", "hash12", "durationS", "agentRan", "phases", "sessionFiles", "turns", "turnsDefinition",
    "tokens", "sideModelTokens", "ttftMs", "wallMs", "turn1Context", "maxTurns", "maxTurnsReached", "apiErrors", "runtime", "model", "effort",
    "tierDerived", "workDirAbnormal", "preAgentFailure", "cancelled", "leaseClosed", "repair", "resent", "interruptedByRestart", "kind", "role",
)
#: Row fields the PLANE section may read.
PLANE_FIELDS = ("jobId", "nodeKey", "acceptedAtApi", "outcome", "outcomeAsOfUtc", "verdictLagS", "failureReason", "failureClass", "source")
#: Third-party prose this screen never paints (spec §8 LEDGER; safety §5.4).
NEVER_SHOWN = ("objective", "lastMessage", "lastMessageUtc")

_count = seat_token


from maxpane_dashboard.widgets.seat.hero import _word


def _n(value: object) -> str:
    return fmt_int(value) if _count(value) is not None else DASH


def adapt_row(row: object) -> dict:
    """The frame's title keys from a ledger row: ``job_id``, ``node_key``, ``role``, ``submitted_ts``, ``accepted_ts``."""
    source = row if isinstance(row, dict) else {}
    return {
        "job_id": source.get("jobId") if isinstance(source.get("jobId"), str) else None,
        "node_key": _word(source.get("nodeKey")) or _word(source.get("nodeId8")) or None,
        "role": _word(source.get("role")) or None,
        "submitted_ts": parse_iso(source.get("submittedUtc")),
        "accepted_ts": parse_iso(source.get("acceptedUtc")),
    }


class SeatTaskDetail(RecordDetailScreen):
    """One ledger row, LOCAL and PLANE -- see the module docstring."""

    TITLE_WORD = "TASK"
    ID_PREFIX = "seat-task-detail"
    SHOW_ROLE = True

    def __init__(self, row: dict) -> None:
        super().__init__(adapt_row(row))
        source = row if isinstance(row, dict) else {}
        # Not ``self.task``: ``task`` is a read-only property on Textual's ``MessagePump`` (the asyncio Task).
        self._task_row = {key: deepcopy(source.get(key)) for key in LOCAL_FIELDS + PLANE_FIELDS + ("nodeId8", "nodeId")}

    def title_node(self):
        return _word(self._task_row.get("nodeKey")) or _word(self._task_row.get("nodeId8")) or EMDASH

    def compose_sections(self):
        yield from self.section("LOCAL", *self._local_lines(), first=True)
        yield from self.section("PLANE", *self._plane_lines())

    # -- LOCAL ----------------------------------------------------------------

    def _local_lines(self) -> list[Text]:
        t = self._task_row
        stamps = Text()
        stamps.append("accepted ", style="dim").append(mmdd_hhmm(parse_iso(t.get("acceptedUtc"))))
        stamps.append(" · submitted ", style="dim").append(as_of_hhmm(t.get("submittedUtc")) or DASH)
        stamps.append(" · stored ", style="dim").append(as_of_hhmm(t.get("storedUtc")) or DASH)
        if t.get("hash12"):
            stamps.append(f" ({_word(t.get('hash12'))})", style="dim")
        took = as_float(t.get("durationS"))
        phases = t.get("phases") if isinstance(t.get("phases"), list) else []
        phase_words = " → ".join(_word(p) for p in phases if _word(p)) or DASH
        run = Text()
        run.append("took ", style="dim").append(f"{took:.1f} s" if took is not None else DASH)
        run.append(" · agent ran ", style="dim").append("✓" if t.get("agentRan") is True else ("✗ (pre-agent failure)" if t.get("preAgentFailure") else DASH))
        run.append(" · phases: ", style="dim").append(phase_words)
        tokens = t.get("tokens") if isinstance(t.get("tokens"), dict) else {}
        usage = Text()
        usage.append("session files ", style="dim").append(_n(t.get("sessionFiles")))
        usage.append(" · turns ", style="dim").append(_n(t.get("turns"))).append(f" ({_word(t.get('turnsDefinition')) or DASH})", style="dim")
        usage.append(" · in ", style="dim").append(_n(tokens.get("input")))
        usage.append(" · out ", style="dim").append(_n(tokens.get("output")))
        usage.append(" · cached ", style="dim").append(_n(tokens.get("cached")))
        usage.append(" · cache write ", style="dim").append(_n(tokens.get("cacheWrite")))
        ttft, wall = _count(t.get("ttftMs")), as_float(t.get("wallMs"))
        max_turns = _count(t.get("maxTurns"))
        timing = Text()
        timing.append("ttft ", style="dim").append(f"{fmt_int(ttft)} ms" if ttft is not None else DASH)
        timing.append(" · wall ", style="dim").append(f"{wall / 1000:.1f} s" if wall is not None else DASH)
        timing.append(" · turn-1 context ", style="dim").append(_n(t.get("turn1Context")))
        timing.append(" · max turns ", style="dim").append(str(max_turns) if max_turns is not None else DASH)
        timing.append(" (reached)" if t.get("maxTurnsReached") is True else " (not reached)", style="yellow" if t.get("maxTurnsReached") is True else "dim")
        model = Text()
        model.append(_word(t.get("runtime")) or DASH, style="bold").append(" ")
        model.append(f"{_word(t.get('model')) or 'runtime default'}/{_word(t.get('effort')) or DASH} {tier_label(t.get('tierDerived') if isinstance(t.get('tierDerived'), str) else None)}")
        flags = [name for name in ("repair", "resent", "leaseClosed", "interruptedByRestart") if t.get(name) is True]
        if _word(t.get("cancelled")):
            flags.append(f"cancelled {_word(t.get('cancelled'))}")
        state = Text()
        state.append("work dir ", style="dim").append("abnormal (.imd/reads or artifacts left)" if t.get("workDirAbnormal") is True else ("normal" if t.get("workDirAbnormal") is False else DASH),
                                                      style="yellow" if t.get("workDirAbnormal") is True else "")
        state.append(" · flags: ", style="dim").append(", ".join(flags) if flags else "none")
        errors = t.get("apiErrors") if isinstance(t.get("apiErrors"), list) else []
        by_status: dict[str, int] = {}
        for error in errors:
            status = _count(error.get("status")) if isinstance(error, dict) else None
            key = str(status) if status is not None else "?"
            by_status[key] = by_status.get(key, 0) + 1
        api = Text()
        api.append("api errors: ", style="dim")
        api.append(" · ".join(f"{k} ×{v}" for k, v in sorted(by_status.items())) if by_status else "none",
                   style="red" if by_status else "")
        return [stamps, run, usage, timing, model, state, api]

    # -- PLANE ----------------------------------------------------------------

    def _plane_lines(self) -> list[Text]:
        t = self._task_row
        job = Text()
        job.append("job ", style="dim")
        job.append_text(job_text(t.get("jobId"), 36, explorer=IMD, style="bold"))
        job.append(" · node ", style="dim").append(_word(t.get("nodeKey")) or DASH)
        outcome = _word(t.get("outcome")) or "unknown"
        colour = {"accepted": "green", "rejected": "red", "failed": "red", "pending": "yellow"}.get(outcome, "dim")
        verdict = Text()
        verdict.append("verdict ", style="dim").append(outcome, style=colour)
        verdict.append(" · as of ", style="dim").append(as_of_hhmm(t.get("outcomeAsOfUtc")) or DASH)
        verdict.append(" · plane accepted ", style="dim").append(as_of_hhmm(t.get("acceptedAtApi")) or DASH)
        verdict.append(" · lag ", style="dim").append(fmt_age(t.get("verdictLagS")))
        reason = _word(t.get("failureReason"))
        klass = _word(t.get("failureClass"))
        failure = Text()
        failure.append("failure ", style="dim")
        failure.append(f"{reason} ({klass})" if reason and klass else (reason or EMDASH), style="red" if reason else "dim")
        source = t.get("source") if isinstance(t.get("source"), dict) else {}
        sources = Text()
        sources.append("sources: ", style="dim")
        sources.append(f"row {_word(source.get('row')) or DASH} · outcome {_word(source.get('outcome')) or DASH} · reason {_word(source.get('reason')) or DASH}")
        return [job, verdict, failure, sources]
