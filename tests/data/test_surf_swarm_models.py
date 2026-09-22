"""The ``s``, ``a`` and ``b`` bodies' data contract, as ``surf_models.py`` freezes it.

The polish WP1 freezes thirty-three keys, including separate workers and
contributors clocks and selected-seat lookups. Every tuple below is hand-typed on purpose -- a copy an agreement
test binds is the one legitimate copy (CLAUDE.md, Conventions), and deriving
it from the module would make the test agree with whatever the module says.
"""

import pytest

from maxpane_dashboard.data import surf_models as models

from maxpane_dashboard.data.surf_models import (
    SURF_KEYS,
    SURF_ROW_KEYS,
    SWARM_KEYS,
    SWARM_SEAT_REVIEW_STATUSES,
    SWARM_SEAT_SELECTED_FIELDS,
    SWARM_SEAT_STATES,
    SWARM_SEAT_SUMMARY_FIELDS,
    SWARM_WIDGET_SIGNATURES,
)

#: The v2 keys still in the block, in the order WP0 appended them (plan §1.1,
#: §1.2, A1): fourteen, less the window fold's node rows (AGENT-seats WP5).
SWARM_V2_KEYS = (
    "swarm_queue_total",
    "swarm_breaker",
    "swarm_skill_summary",
    "swarm_launch_summary",
    "swarm_inflight_rows",
    "swarm_skill_rows",
    "swarm_launch_rows",
    "swarm_site_rows",
    "swarm_seat_selected",
    "swarm_seat_summary",
    "swarm_seat_as_of_hhmm",
)

#: The four ``/seats`` keys the AGENT-seats WP0 appended after the v2 tail
#: (``docs/surf_agent_seats_plan.md`` §1.1), in order.
SWARM_SEATS_KEYS = (
    "swarm_seat_state",
    "swarm_seat_work_rows",
    "swarm_seat_node_rows",
    "swarm_seat_teammates",
)

#: BOARD additions follow the existing seat block; the sources remain separate.
SWARM_BOARD_KEYS = (
    "swarm_board_summary", "swarm_board_rows", "swarm_fleet",
    "swarm_board_as_of_hhmm", "swarm_workers_as_of_hhmm",
    "swarm_seat_live", "swarm_seat_contrib",
)

#: The retired swarm v1 and seat-window keys. Named so the test that
#: says they are gone cannot pass on a typo.
SWARM_RETIRED_KEYS = (
    "swarm_seat_rows",
    "swarm_seat_feedback_rows",
    "swarm_roster_window",
    "swarm_jobs_in_flight",
    "swarm_jobs_blocked",
    "swarm_queue_depths",
    "swarm_field_rows",
    "swarm_queue_rows",
    "swarm_blocked_rows",
    "swarm_shipped_rows",
    "swarm_score_rows",
)

#: Eight surviving/new row shapes, fields in contract order (v2 plus BOARD).
SWARM_V2_ROW_SHAPES = {
    "swarm_board_rows": (
        "rank", "token_id", "agent_id", "devices", "runtime", "attempts", "accepted",
        "rejected", "pending", "accept_rate", "turns", "wall_clock_s", "live_state",
        "working", "paused_until_ts", "failures",
    ),
    "swarm_inflight_rows": (
        "job_id", "template", "objective", "created_ts", "age_s", "node_key",
        "node_role", "node_state", "agent_token", "agent_id", "revisions",
        "note", "note_kind",
    ),
    "swarm_skill_rows": (
        "skill_id", "version", "role", "kind", "tier", "judge", "checks",
        "requires", "inference", "attempts", "accepted", "rejected", "pending",
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
    "swarm_seat_node_rows": (
        "node_key", "roles", "reviewed", "attempts", "accepted", "onchain", "queued",
    ),
    "swarm_seat_teammates": ("token_id", "agent_id", "shared_jobs"),
    # AGENT-seats WP0 (plan §1.1): /seats work[], replaced the window node rows in WP5.
    "swarm_seat_work_rows": (
        "job_id", "node_key", "role", "job_state", "work_status", "objective", "accepted_ts",
        "submitted_ts",
        "launch", "submission_hash", "answer", "answer_state", "model", "took_s",
    ),
}

#: The four AGENT-body widgets (AGENT-seats plan §1.3).
AGENT_WIDGETS = (
    "SurfSwarmAgentHero", "SurfSwarmSeatCards", "SurfSwarmNodeCards",
    "SurfSwarmSeatRecord",
)

#: The thirteen SWARM, AGENT and BOARD target widgets, by class name.
SWARM_TARGET_WIDGETS = {
    "SurfSwarmBoardHero", "SurfSwarmLeaderboard", "SurfSwarmFleet",
    "SurfSwarmHero",
    "SurfSwarmInFlight",
    "SurfSwarmThroughput",
    "SurfSwarmCapability",
    "SurfSwarmLaunches",
    "SurfSwarmSites",
    "SurfSwarmAgentHero",
    "SurfSwarmSeatCards",
    "SurfSwarmNodeCards",
    "SurfSwarmSeatRecord",
}


def test_the_swarm_block_is_thirty_four_keys():
    """Thirty-two existing keys, the served health status word and the owner's ENS name."""
    assert len(SWARM_KEYS) == 34
    assert len(set(SWARM_KEYS)) == 34
    assert all(k.startswith("swarm_") for k in SWARM_KEYS)


def test_every_swarm_key_appears_in_surf_keys_exactly_once():
    for key in SWARM_KEYS:
        assert SURF_KEYS.count(key) == 1, key


def test_the_swarm_block_is_contiguous_and_last():
    positions = [SURF_KEYS.index(k) for k in SWARM_KEYS]
    assert positions == sorted(positions)
    assert positions == list(range(positions[0], positions[0] + len(SWARM_KEYS)))
    assert positions[-1] == len(SURF_KEYS) - 1


def test_the_v2_keys_then_the_seats_keys_are_the_tail_in_order():
    """The v2 keys are appended, not interleaved, and the /seats keys after them.

    Order matters because WP7 deleted the eight retired keys by name from
    the head, so the tail is the final block's second half.
    """
    assert SWARM_KEYS[-24:] == (SWARM_V2_KEYS + SWARM_SEATS_KEYS + SWARM_BOARD_KEYS
                                + ("swarm_health_status", "swarm_seat_owner_ens"))


def test_the_retired_keys_are_gone_and_the_ten_survivors_lead():
    """WP7 (A2): the retired keys are in no key tuple and own no row shape,
    and the ten pre-v2 survivors are the block's head, in their old order."""
    for key in SWARM_RETIRED_KEYS:
        assert key not in SWARM_KEYS, key
        assert key not in SURF_KEYS, key
        assert key not in SURF_ROW_KEYS, key
    assert SWARM_KEYS[:10] == (
        "swarm_agents_online", "swarm_agents_enrolled", "swarm_working_now",
        "swarm_accepted_today", "swarm_services_up", "swarm_throughput",
        "swarm_network", "swarm_as_of_hhmm", "swarm_scores_as_of_hhmm",
        "swarm_stale",
    )


def test_every_swarm_row_shape_is_declared_and_is_a_payload_key():
    for name in SWARM_V2_ROW_SHAPES:
        assert name in SURF_ROW_KEYS, name
        assert SURF_ROW_KEYS[name], name
        assert name in SURF_KEYS, name
    # ...and the swarm owns no other row shape.
    assert {k for k in SURF_ROW_KEYS if k.startswith("swarm_")} == set(SWARM_V2_ROW_SHAPES)


@pytest.mark.parametrize("name", sorted(SWARM_V2_ROW_SHAPES))
def test_each_v2_row_shape_is_exactly_the_frozen_field_tuple(name):
    """Field order is part of the contract: WP3's fold builds the dicts in
    this order and WP5/WP6/WP6a's tables read them by name."""
    assert SURF_ROW_KEYS[name] == SWARM_V2_ROW_SHAPES[name]
    # ...and the module's tuple names no field twice (checked on the module,
    # not on this test's own literal -- WP0 review residual, closed in WP8).
    assert len(SURF_ROW_KEYS[name]) == len(set(SURF_ROW_KEYS[name])), name


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
    """Every one is named by some target widget -- including the
    marker (``swarm_seat_as_of_hhmm`` is read by every AGENT widget), so the
    exception set is empty and the assertion is over the whole tail."""
    named = {k for sig in SWARM_WIDGET_SIGNATURES.values() for k in sig}
    unreached = set(SWARM_V2_KEYS) - named
    assert unreached == set(), sorted(unreached)


def test_the_signature_names_exactly_the_thirteen_target_widgets():
    assert set(SWARM_WIDGET_SIGNATURES) == SWARM_TARGET_WIDGETS
    assert len(SWARM_WIDGET_SIGNATURES) == 13


def test_no_retired_key_is_named_by_a_target_signature():
    """The signatures describe the post-WP7 widgets: none may lean on a key
    WP7 deleted, or the screen's binding would name a key nothing emits."""
    named = {k for sig in SWARM_WIDGET_SIGNATURES.values() for k in sig}
    assert not (named & set(SWARM_RETIRED_KEYS)), sorted(named & set(SWARM_RETIRED_KEYS))


def test_no_swarm_key_leaks_a_raw_envelope():
    for bad in ("swarm_jobs", "swarm_health", "swarm_details", "swarm_skills",
                "swarm_launches", "swarm_sites"):
        assert bad not in SURF_KEYS


# --- AGENT body on /seats/{tokenId}: WP0 freeze (docs/surf_agent_seats_plan.md §1.2, §1.3) ---


def test_the_seats_permanent_exports_are_the_frozen_literals():
    assert SWARM_SEAT_SELECTED_FIELDS == ("token_id", "agent_id", "selected_by")
    assert SWARM_SEAT_SUMMARY_FIELDS == (
        "attempts", "accepted", "reviewed", "review_entries", "review_status", "mean_score", "scored",
        "roles", "online", "owner", "paired_ts", "collaborators", "runtime",
        "agent_id", "daemon", "devices", "win_rate", "last_won_ts", "last_sent_ts",
        "last_worked_ts",
    )
    assert SWARM_SEAT_REVIEW_STATUSES == ("sent", "submitted", "queued")
    # "pending" by the owner's Q-A answer (2026-09-21); None is not a member -- it is
    # "read failed, no last-good", the absence of a state.
    assert SWARM_SEAT_STATES == ("ok", "unknown_seat", "pending")


def test_the_agent_signatures_are_the_flipped_literals():
    """AGENT-seats plan §1.3, flipped in WP5 (the screen dispatch reads these)."""
    assert {k: SWARM_WIDGET_SIGNATURES[k] for k in AGENT_WIDGETS} == {
        "SurfSwarmAgentHero": (
            "swarm_seat_selected", "swarm_seat_summary", "swarm_seat_state", "swarm_seat_as_of_hhmm",
            "swarm_seat_live", "swarm_seat_contrib",
        ),
        "SurfSwarmSeatCards": (
            "swarm_seat_summary", "swarm_seat_state", "swarm_seat_teammates",
            "swarm_seat_owner_ens",
        ),
        "SurfSwarmNodeCards": (
            "swarm_seat_summary", "swarm_seat_node_rows", "swarm_seat_contrib",
            "swarm_seat_state",
        ),
        "SurfSwarmSeatRecord": ("swarm_seat_work_rows", "swarm_seat_state", "swarm_seat_as_of_hhmm"),
    }


def test_the_agent_signatures_reach_every_seats_key_and_drop_the_window_ones():
    named = {k for w in AGENT_WIDGETS for k in SWARM_WIDGET_SIGNATURES[w]}
    assert set(SWARM_SEATS_KEYS) <= named, sorted(set(SWARM_SEATS_KEYS) - named)
    assert "swarm_network" not in named



@pytest.mark.parametrize(("name", "expected"), [
    ("SWARM_BOARD_SUMMARY_FIELDS", (
        "seats", "live", "paused", "capacity", "working", "attempts", "accepted",
        "rejected", "pending", "receipts", "tokens_per_completed_job",
    )),
    ("SWARM_FLEET_FIELDS", (
        "runtimes", "daemons", "os", "profiles", "concurrency",
        "heartbeat_oldest_ts", "heartbeat_newest_ts", "paused", "models",
    )),
    ("SWARM_SEAT_LIVE_FIELDS", (
        "live", "working", "max_concurrency", "paused_until_ts", "failures",
        "heartbeat_ts", "devices", "skills", "profiles", "platform",
        "advertised_model", "advertised_effort", "live_state",
    )),
    ("SWARM_SEAT_CONTRIB_FIELDS", (
        "listed", "attempts", "accepted", "rejected", "pending", "turns",
        "wall_clock_s", "rank", "ranked_of",
    )),
    ("SWARM_BOARD_LIVE_STATES", ("working", "idle", "paused", "offline")),
    ("SWARM_INFLIGHT_NOTE_KINDS", ("dispatch", "failure")),
])
def test_board_nested_fields_and_vocabularies_are_frozen_literals(name, expected):
    actual = getattr(models, name)
    assert actual == expected
    assert len(actual) == len(set(actual))


def test_board_signatures_carry_each_source_clock():
    assert {name: SWARM_WIDGET_SIGNATURES[name] for name in (
        "SurfSwarmBoardHero", "SurfSwarmLeaderboard", "SurfSwarmFleet",
    )} == {
        "SurfSwarmBoardHero": (
            "swarm_board_summary", "swarm_board_as_of_hhmm", "swarm_workers_as_of_hhmm",
        ),
        "SurfSwarmLeaderboard": (
            "swarm_board_rows", "swarm_seat_selected", "swarm_board_as_of_hhmm",
            "swarm_workers_as_of_hhmm",
        ),
        "SurfSwarmFleet": (
            "swarm_fleet", "swarm_board_summary", "swarm_board_as_of_hhmm",
            "swarm_workers_as_of_hhmm",
        ),
    }
    named = {key for signature in SWARM_WIDGET_SIGNATURES.values() for key in signature}
    assert set(SWARM_BOARD_KEYS) <= named


def test_inflight_note_lives_in_its_row_without_an_unused_new_kwarg():
    assert SWARM_WIDGET_SIGNATURES["SurfSwarmInFlight"] == (
        "swarm_inflight_rows", "swarm_as_of_hhmm", "swarm_network",
    )


def test_polish_answer_and_advertised_model_contracts_are_frozen():
    assert models.SWARM_ANSWER_STATES == (
        "read", "not_read", "unavailable", "not_served", "no_reply",
    )
    assert models.SWARM_ANSWER_FIELDS == ("answer", "model", "took_s", "state")
    assert models.SWARM_ANSWER_CACHE_FIELDS == (
        "answer", "model", "took_s", "state", "read_ts", "terminal",
    )
    assert models.SWARM_FLEET_MODEL_FIELDS == ("model", "effort", "count")


def test_polish_answer_fetch_window_agrees_with_record_row_cap():
    from maxpane_dashboard.widgets.surf.swarm_seat_record import SurfSwarmSeatRecord
    assert models.SWARM_ANSWER_ROW_CAP == 40
    assert models.SWARM_ANSWER_ROW_CAP == SurfSwarmSeatRecord.ROW_CAP


def test_polish_health_status_has_a_named_hero_consumer():
    import inspect
    from maxpane_dashboard.widgets.surf.swarm_hero import SurfSwarmHero
    expected = (
        "swarm_agents_online", "swarm_agents_enrolled", "swarm_working_now",
        "swarm_accepted_today", "swarm_queue_total", "swarm_breaker",
        "swarm_services_up", "swarm_health_status",
    )
    assert SWARM_WIDGET_SIGNATURES["SurfSwarmHero"] == expected
    signature = inspect.signature(SurfSwarmHero.update_data)
    actual = tuple(name for name, value in signature.parameters.items()
                   if name != "self" and value.kind != inspect.Parameter.VAR_KEYWORD)
    assert actual == expected


def test_polish_unenriched_work_rows_explicitly_wait_for_answer_read():
    from maxpane_dashboard.data.surf_swarm import seat_work_rows
    from tests.surf_swarm_fixtures import swarm_seat_capture
    rows = seat_work_rows(swarm_seat_capture("seat_420"))
    assert rows
    for row in rows:
        assert (row["answer"], row["answer_state"], row["model"], row["took_s"]) == (
            None, "not_read", None, None,
        )
