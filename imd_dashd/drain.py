"""Drain-restart state machine (spec §11 verb table `drain-restart`).

Pure: the broker feeds it heartbeats (``on_heartbeat``) and clock ticks (``tick``); it answers with
the audit event name to record, or ``None``. Counting is *consecutive* idle beats -- any
``N task(s) running`` beat resets the count and re-arms (``drain_rearmed``); reaching ``required``
returns ``drain_fire`` and the broker then runs the same fresh apply-time gate before ``restart``.
The armed drain expires after ``DRAIN_MAX_S`` (the task budget maximum, bundle §4).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

Clock = Callable[[], float]

IDLE_BEATS_REQUIRED = 4
DRAIN_MAX_S = 14400          #: TaskBudget.maxWallClockMs max (bundle §4)

EVENT_ARMED = "drain_armed"
EVENT_REARMED = "drain_rearmed"
EVENT_FIRE = "drain_fire"
EVENT_CANCELLED = "drain_cancelled"
EVENT_EXPIRED = "drain_expired"
EVENT_LOST = "drain_lost"


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


@dataclass
class DrainState:
    plan_id: str
    armed_at: float
    expires_at: float
    idle_beats: int = 0
    rearmed: int = 0

    def to_dict(self) -> dict:
        """SEAT_BLOCK_KEYS["seat_control_drain"] with ISO stamps."""
        return {"armedAtUtc": _iso(self.armed_at), "idleBeats": self.idle_beats, "rearmed": self.rearmed,
                "expiresAtUtc": _iso(self.expires_at)}


class Drain:
    def __init__(self, *, now: Clock, required: int = IDLE_BEATS_REQUIRED, max_s: float = DRAIN_MAX_S) -> None:
        self._now = now
        self._required = required
        self._max_s = max_s
        self._state: DrainState | None = None

    @property
    def armed(self) -> DrainState | None:
        return self._state

    def arm(self, plan_id: str) -> str:
        if self._state is not None:
            raise RuntimeError("drain_already_armed")
        at = self._now()
        self._state = DrainState(plan_id=plan_id, armed_at=at, expires_at=at + self._max_s)
        return EVENT_ARMED

    def on_heartbeat(self, work: str, at: float) -> str | None:
        """``work`` is ``"idle"`` or ``"running"`` (from the heartbeat's `idle | N task(s) running`)."""
        state = self._state
        if state is None:
            return None
        if at > state.expires_at:
            return self.tick(at)
        if work == "idle":
            state.idle_beats += 1
            if state.idle_beats >= self._required:
                self._state = None
                return EVENT_FIRE
            return None
        # a task started (or is still running): the count restarts from zero -- mutation proof 17
        had_progress = state.idle_beats > 0
        state.idle_beats = 0
        if had_progress:
            state.rearmed += 1
            return EVENT_REARMED
        return None

    def tick(self, at: float) -> str | None:
        state = self._state
        if state is None:
            return None
        if at > state.expires_at:
            self._state = None
            return EVENT_EXPIRED
        return None

    def cancel(self) -> str:
        if self._state is None:
            raise RuntimeError("drain_not_armed")
        self._state = None
        return EVENT_CANCELLED

    def lose(self) -> str | None:
        """The broker is shutting down while armed: the drain does not survive (spec §11 `drain_lost`)."""
        if self._state is None:
            return None
        self._state = None
        return EVENT_LOST

    def restore(self, state: DrainState) -> str:
        """Put a fired drain back when the fresh gate refused the fire (spec §11: re-arm, then ``drain_expired`` at
        ``DRAIN_MAX_S``): the same plan id and deadline, the idle count from zero -- never a fresh 4 h."""
        if self._state is not None:
            raise RuntimeError("drain_already_armed")
        state.idle_beats = 0
        state.rearmed += 1
        self._state = state
        return EVENT_REARMED


__all__ = ["Clock", "DRAIN_MAX_S", "Drain", "DrainState", "EVENT_ARMED", "EVENT_CANCELLED", "EVENT_EXPIRED",
           "EVENT_FIRE", "EVENT_LOST", "EVENT_REARMED", "IDLE_BEATS_REQUIRED"]
