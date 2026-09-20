"""The ``s`` and ``a`` bodies' data contract, as ``surf_models.py`` freezes it.

WP0 of ``docs/surf_swarm_v2_implementation_plan.md`` (2026-09-21) grew the
block from eighteen to thirty-two under Amendment A2: the fourteen v2 keys
(§1.1's four, §1.2's four, A1's six) are appended as one contiguous tail and
the eight keys §1 lists as "Removed" stay until WP7 retires them with their
widgets. Every tuple below is hand-typed on purpose -- a copy an agreement
test binds is the one legitimate copy (CLAUDE.md, Conventions), and deriving
it from the module would make the test agree with whatever the module says.
"""

import pytest

from maxpane_dashboard.data.surf_models import (
    SURF_KEYS,
    SURF_ROW_KEYS,
    SWARM_KEYS,
    SWARM_WIDGET_SIGNATURES,
)

#: The pre-v2 row shapes. All five survive until WP7 (A2).
SWARM_ROW_NAMES = ("swarm_field_rows", "swarm_queue_rows", "swarm_blocked_rows",
                   "swarm_shipped_rows", "swarm_score_rows")

#: The fourteen v2 keys in the order WP0 appended them (plan §1.1, §1.2, A1).
SWARM_V2_KEYS = (
    "swarm_queue_total",
    "swarm_breaker",
    "swarm_skill_summary",
    "swarm_launch_summary",
    "swarm_inflight_rows",
    "swarm_skill_rows",
    "swarm_launch_rows",
    "swarm_site_rows",
    "swarm_seat_rows",
    "swarm_seat_selected",
    "swarm_seat_summary",
    "swarm_seat_node_rows",
    "swarm_seat_feedback_rows",
    "swarm_seat_as_of_hhmm",
)

#: The eight §1 marks "Removed"; A2 defers the removal to WP7.
SWARM_RETIRING_KEYS = (
    "swarm_jobs_in_flight",
    "swarm_jobs_blocked",
    "swarm_queue_depths",
    "swarm_field_rows",
    "swarm_queue_rows",
    "swarm_blocked_rows",
    "swarm_shipped_rows",
    "swarm_score_rows",
)

#: The seven v2 row shapes, fields in contract order (plan §1.2 + A1).
SWARM_V2_ROW_SHAPES = {
    "swarm_inflight_rows": (
        "job_id", "template", "objective", "created_ts", "age_s", "node_key",
        "node_role", "node_state", "agent_token", "agent_id", "revisions",
    ),
    "swarm_skill_rows": (
        "skill_id", "version", "role", "kind", "tier", "judge", "checks",
        "requires",
    ),
    "swarm_launch_rows": (
        "launch_number", "kind", "status", "chain_id", "repo_url", "commit",
        "parked_reason", "artifact_count", "created_ts", "updated_ts",
        "artifacts",
    ),
    "swarm_site_rows": (
        "label", "ens_name", "cid", "bytes", "status", "tx_hash",
        "block_number", "job_id", "superseded_by", "failure",
    ),
    "swarm_seat_rows": (
        "token_id", "agent_id", "nodes", "jobs", "roles", "accepted",
        "rejected", "revisions", "mean_score", "scored", "working_now",
        "last_active_ts",
    ),
    "swarm_seat_node_rows": (
        "job_id", "template", "node_key", "role", "state", "attempt",
        "revisions", "verdict_status", "rejection_code", "failed_checks",
        "detail", "at_ts",
    ),
    "swarm_seat_feedback_rows": (
        "value", "node_key", "job_id", "tx_hash", "chain_id", "block_number",
        "sent_ts",
    ),
}

#: The eleven target widgets of §1.4 + A1, by class name.
SWARM_TARGET_WIDGETS = {
    "SurfSwarmHero",
    "SurfSwarmInFlight",
    "SurfSwarmThroughput",
    "SurfSwarmCapability",
    "SurfSwarmLaunches",
    "SurfSwarmSites",
    "SurfSwarmAgentHero",
    "SurfSwarmRoster",
    "SurfSwarmSeatRecord",
    "SurfSwarmSeatVerdicts",
    "SurfSwarmSeatFeedback",
}


def test_the_swarm_block_is_thirty_two_keys():
    """18 pre-v2 + 14 v2 = 32 until WP7 retires eight (A2)."""
    assert len(SWARM_KEYS) == 32
    assert len(set(SWARM_KEYS)) == 32
    assert all(k.startswith("swarm_") for k in SWARM_KEYS)


def test_every_swarm_key_appears_in_surf_keys_exactly_once():
    for key in SWARM_KEYS:
        assert SURF_KEYS.count(key) == 1, key


def test_the_swarm_block_is_contiguous_and_last():
    positions = [SURF_KEYS.index(k) for k in SWARM_KEYS]
    assert positions == sorted(positions)
    assert positions == list(range(positions[0], positions[0] + len(SWARM_KEYS)))
    assert positions[-1] == len(SURF_KEYS) - 1


def test_the_fourteen_v2_keys_are_the_tail_of_the_block_in_order():
    """The v2 keys are appended, not interleaved: the tail is exactly them.

    Order matters because WP7 deletes the eight retiring keys by name from
    the head and expects the tail to be the final block's second half.
    """
    assert SWARM_KEYS[-14:] == SWARM_V2_KEYS


def test_the_eight_retiring_keys_are_still_present_until_wp7():
    """A2: removing them before WP7 reddens the manager, screen and triage
    tests that still emit and consume them. They go with their widgets."""
    for key in SWARM_RETIRING_KEYS:
        assert key in SWARM_KEYS, key
    # ...and every one of them is pre-v2, i.e. sits ahead of the tail.
    for key in SWARM_RETIRING_KEYS:
        assert SWARM_KEYS.index(key) < len(SWARM_KEYS) - 14, key


def test_every_swarm_row_shape_is_declared_and_is_a_payload_key():
    for name in SWARM_ROW_NAMES + tuple(SWARM_V2_ROW_SHAPES):
        assert name in SURF_ROW_KEYS, name
        assert SURF_ROW_KEYS[name], name
        assert name in SURF_KEYS, name


def test_the_field_row_is_exactly_the_frozen_shape():
    """The old FIELD shape survives until WP7 deletes the widget (A2)."""
    assert SURF_ROW_KEYS["swarm_field_rows"] == (
        "job_id", "template", "objective", "node_key", "role", "node_state",
        "agent_token", "agent_id", "revisions", "dispatch_note", "moved_ts",
        "age_s",
    )


@pytest.mark.parametrize("name", sorted(SWARM_V2_ROW_SHAPES))
def test_each_v2_row_shape_is_exactly_the_frozen_field_tuple(name):
    """Field order is part of the contract: WP3's fold builds the dicts in
    this order and WP5/WP6/WP6a's tables read them by name."""
    assert SURF_ROW_KEYS[name] == SWARM_V2_ROW_SHAPES[name]


def test_every_v2_row_shape_has_unique_fields():
    for name, fields in SWARM_V2_ROW_SHAPES.items():
        assert len(fields) == len(set(fields)), name


def test_every_signature_key_is_a_swarm_key():
    """A signature may name only what the block carries -- a kwarg that is
    not a contract key would be a widget reading a value nothing emits."""
    for widget, kwargs in SWARM_WIDGET_SIGNATURES.items():
        for key in kwargs:
            assert key in SWARM_KEYS, f"{widget} takes {key!r}, not a SWARM_KEYS entry"


def test_every_signature_kwarg_is_unique_within_its_widget():
    for widget, kwargs in SWARM_WIDGET_SIGNATURES.items():
        assert len(kwargs) == len(set(kwargs)), widget
        assert kwargs, widget


def test_every_v2_key_but_the_marker_reaches_at_least_one_signature():
    """All fourteen are named by some target widget -- including the
    marker (``swarm_seat_as_of_hhmm`` is read by every AGENT widget), so the
    exception set is empty and the assertion is over the whole tail."""
    named = {k for sig in SWARM_WIDGET_SIGNATURES.values() for k in sig}
    unreached = set(SWARM_V2_KEYS) - named
    assert unreached == set(), sorted(unreached)


def test_the_signature_names_exactly_the_eleven_target_widgets():
    assert set(SWARM_WIDGET_SIGNATURES) == SWARM_TARGET_WIDGETS
    assert len(SWARM_WIDGET_SIGNATURES) == 11


def test_no_retiring_key_is_named_by_a_target_signature():
    """The signatures describe the post-WP7 widgets: none may still lean on
    a key that WP7 deletes, or WP7 would break its own binding."""
    named = {k for sig in SWARM_WIDGET_SIGNATURES.values() for k in sig}
    assert not (named & set(SWARM_RETIRING_KEYS)), sorted(named & set(SWARM_RETIRING_KEYS))


def test_no_swarm_key_leaks_a_raw_envelope():
    for bad in ("swarm_jobs", "swarm_health", "swarm_details", "swarm_skills",
                "swarm_launches", "swarm_sites"):
        assert bad not in SURF_KEYS
