"""``imd_dashd/drain.py`` -- the drain-restart state machine (spec §11 `drain-restart` row; mutation proof 17)."""
from __future__ import annotations

import pytest

from imd_dashd.drain import (
    DRAIN_MAX_S, Drain, EVENT_ARMED, EVENT_CANCELLED, EVENT_EXPIRED, EVENT_FIRE, EVENT_LOST, EVENT_REARMED,
)

T0 = 1_790_000_000.0
PLAN = "7f3a9c1e2b4d6081"


def test_arm_then_four_consecutive_idle_beats_fire():
    # spec §11: "counts consecutive idle beats … when 4 beats are reached runs the same fresh apply-time gate"
    drain = Drain(now=lambda: T0)
    assert drain.arm(PLAN) == EVENT_ARMED
    assert drain.armed is not None and drain.armed.plan_id == PLAN
    assert drain.armed.to_dict() == {"armedAtUtc": "2026-09-21T14:13:20Z", "idleBeats": 0, "rearmed": 0,
                                     "expiresAtUtc": "2026-09-21T18:13:20Z"}
    events = [drain.on_heartbeat("idle", T0 + 30 * i) for i in range(1, 5)]
    assert events == [None, None, None, EVENT_FIRE]
    assert drain.armed is None                       # fired: the broker owns the restart from here


def test_drain_rearms_on_work():
    # mutation proof 17: a `1 task running` beat after idle beats resets the count and audits drain_rearmed
    drain = Drain(now=lambda: T0)
    drain.arm(PLAN)
    assert drain.on_heartbeat("idle", T0 + 30) is None
    assert drain.on_heartbeat("idle", T0 + 60) is None
    assert drain.armed.idle_beats == 2
    assert drain.on_heartbeat("running", T0 + 90) == EVENT_REARMED
    assert drain.armed.idle_beats == 0 and drain.armed.rearmed == 1
    # three more idle beats are NOT enough after the reset -- the count restarted
    assert [drain.on_heartbeat("idle", T0 + 120 + 30 * i) for i in range(3)] == [None, None, None]
    assert drain.armed is not None
    assert drain.on_heartbeat("idle", T0 + 240) == EVENT_FIRE


def test_running_beats_before_any_idle_do_not_count_as_rearms():
    drain = Drain(now=lambda: T0)
    drain.arm(PLAN)
    assert drain.on_heartbeat("running", T0 + 30) is None
    assert drain.armed.rearmed == 0


def test_expires_after_the_task_budget_maximum():
    # spec §11: DRAIN_MAX_S = 14400 (TaskBudget.maxWallClockMs max) then drain_expired
    assert DRAIN_MAX_S == 14400
    drain = Drain(now=lambda: T0)
    drain.arm(PLAN)
    assert drain.tick(T0 + DRAIN_MAX_S) is None
    assert drain.tick(T0 + DRAIN_MAX_S + 1) == EVENT_EXPIRED
    assert drain.armed is None
    drain.arm(PLAN)
    assert drain.on_heartbeat("idle", T0 + DRAIN_MAX_S + 1) == EVENT_EXPIRED   # a late beat expires, never fires


def test_cancel_and_double_arm_and_lost():
    drain = Drain(now=lambda: T0)
    with pytest.raises(RuntimeError, match="drain_not_armed"):
        drain.cancel()
    drain.arm(PLAN)
    with pytest.raises(RuntimeError, match="drain_already_armed"):
        drain.arm("0000000000000001")
    assert drain.cancel() == EVENT_CANCELLED and drain.armed is None
    assert drain.lose() is None
    drain.arm(PLAN)
    assert drain.lose() == EVENT_LOST and drain.armed is None
    assert drain.on_heartbeat("idle", T0 + 30) is None and drain.tick(T0 + 99999) is None


def test_restore_rearms_the_same_drain_with_its_deadline():
    # a fire the fresh gate refused puts the SAME drain back: plan id and DRAIN_MAX_S deadline unchanged (spec §11)
    drain = Drain(now=lambda: T0)
    drain.arm(PLAN)
    state = drain.armed
    assert [drain.on_heartbeat("idle", T0 + 30 * i) for i in range(1, 5)][-1] == EVENT_FIRE and drain.armed is None
    assert drain.restore(state) == EVENT_REARMED
    assert drain.armed is state and state.plan_id == PLAN and state.idle_beats == 0 and state.rearmed == 1
    assert drain.armed.to_dict()["expiresAtUtc"] == "2026-09-21T18:13:20Z"            # never a fresh 4 h
    with pytest.raises(RuntimeError, match="drain_already_armed"):
        drain.restore(state)
    assert drain.tick(T0 + DRAIN_MAX_S + 1) == EVENT_EXPIRED
