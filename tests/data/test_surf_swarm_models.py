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

#: Nine surviving/new row shapes, fields in contract order (v2, BOARD, /workflows).
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
        "launch_id", "job_id", "production", "ticker", "token_name", "token_address",
        "pair", "pool_fee", "requester", "policy_version",
        "site_label", "site_ens_name", "site_link_method", "site_link_trusted",
        "verdict", "checks", "liquidity",
        "launch_number", "kind", "status", "chain_id", "repo_url", "commit",
        "parked_reason", "artifact_count", "created_ts", "updated_ts",
        "artifacts",
    ),
    "swarm_site_rows": (
        "launch_number", "launch_ticker", "production_link", "link_method", "link_trusted",
        "label", "ens_name", "cid", "bytes", "status", "tx_hash",
        "block_number", "job_id", "superseded_by",
    ),
    # docs/surf_swarm_workflows_spec.md §2 (WP2, 2026-10-03): GET /workflows.
    "swarm_workflow_rows": (
        "workflow_id", "status", "contracts_job_id", "frontend_job_id", "objective",
        "failure", "created_ts", "updated_ts", "waiting_for_hosting",
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
        "output_tokens", "panel_state", "panel_agreed", "panel_quorum", "panel_size",
        "panel_figure", "panel_answer_type", "panel_answer_bool",
        "oracle_question", "oracle_chain_id", "oracle_member_ok", "oracle_member_reason", "oracle_seat_answer", "oracle_notes",
        "sub_reply", "sub_failure_reason", "sub_turns", "sub_cached_input_tokens",
        "sub_failed_checks", "sub_findings", "sub_artifacts", "sub_others", "sub_others_total",
        "job_read", "job_detail_state", "job_blocked_reason", "job_nodes", "job_read_ts",
    ),
}

#: The four AGENT-body widgets (AGENT-seats plan §1.3).
AGENT_WIDGETS = (
    "SurfSwarmAgentHero", "SurfSwarmSeatCards",
    "SurfSwarmSeatRecord",
)

#: The twelve mounted SWARM, AGENT and BOARD target widgets, by class name.
#: WORKFLOWS took CAPABILITY's place on 2026-10-03; CAPABILITY is parked
#: (``SWARM_PARKED_WIDGET_SIGNATURES``, read from the export below).
SWARM_TARGET_WIDGETS = {
    "SurfSwarmBoardHero", "SurfSwarmLeaderboard", "SurfSwarmFleet",
    "SurfSwarmHero",
    "SurfSwarmLatestLaunches",
    "SurfSwarmWorkflows",
    "SurfSwarmLaunches",
    "SurfSwarmSites",
    "SurfSwarmAgentHero",
    "SurfSwarmSeatCards",
    "SurfSwarmSeatRecord",
}


def test_the_swarm_block_includes_runtime_checks_and_rank_delta():
    """Thirty-two existing keys, the served health status word and the owner's ENS name,
    runtime/rank/read keys, F-S5's two REWARDS keys, the /workflows rows
    and their independent successful-read marker, plus the launches tier marker."""
    assert len(SWARM_KEYS) == 43
    assert len(set(SWARM_KEYS)) == 43
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
    assert SWARM_KEYS[-33:] == (SWARM_V2_KEYS + SWARM_SEATS_KEYS + SWARM_BOARD_KEYS
                                + ("swarm_health_status", "swarm_seat_owner_ens", "swarm_runtime_latest",
                                   "swarm_runtime_as_of_hhmm", "swarm_fleet_daemon", "swarm_seat_rank_delta", "swarm_seat_read",
                                   "swarm_seat_rewards", "swarm_seat_rewards_state",
                                   "swarm_workflow_rows", "swarm_workflows_as_of_hhmm", "swarm_launches_as_of_hhmm"))


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
            assert key in (*SWARM_KEYS, "as_of"), f"{widget} takes {key!r}, not a declared snapshot key"


def test_every_signature_kwarg_is_unique_within_its_widget():
    for widget, kwargs in SWARM_WIDGET_SIGNATURES.items():
        assert len(kwargs) == len(set(kwargs)), widget
        assert kwargs, widget


#: Swarm keys frozen ahead of their widget, by name. Filled by WP2 of
#: ``docs/surf_swarm_workflows_spec.md`` (2026-10-03) with the /workflows rows
#: and **emptied by that spec's WP5** (the same day), which names the key in
#: ``SWARM_WIDGET_SIGNATURES``. Empty again: a key frozen ahead of its widget
#: fills it, and the equality below reddens until the wiring consumes it.
#: Mirrors ``tests/screens/test_surf_screen.py::_KEYS_PENDING_CONSUMERS``.
_KEYS_PENDING_CONSUMERS: frozenset[str] = frozenset()


def _consumed_keys() -> set[str]:
    """Every key a mounted *or parked* widget's signature names. A parked
    widget (``SWARM_PARKED_WIDGET_SIGNATURES``, read from the export -- never a
    hand-typed copy) keeps its keys consumed: ``swarm_skill_rows`` and
    ``swarm_skill_summary`` are still read and wait for a SKILLS board."""
    return {k for sig in (*SWARM_WIDGET_SIGNATURES.values(),
                          *models.SWARM_PARKED_WIDGET_SIGNATURES.values()) for k in sig}


def test_every_v2_key_but_the_marker_reaches_at_least_one_signature():
    """Every one is named by some target widget -- including the
    marker (``swarm_seat_as_of_hhmm`` is read by every AGENT widget), so the
    exception set is empty and the assertion is over the whole tail.

    Since WP2 of the workflows spec the claim is over every ``SWARM_KEYS``
    entry, not only the v2 tail: what no signature names must be exactly the
    named pending set -- equality, so the carve-out can neither hide a second
    orphan nor outlive the wiring that consumes it."""
    named = _consumed_keys()
    named |= {"swarm_breaker", "swarm_services_up", "swarm_health_status"}  # screen title alarms
    unreached = set(SWARM_V2_KEYS) - named
    assert unreached == set(), sorted(unreached)
    assert set(SWARM_KEYS) - named == _KEYS_PENDING_CONSUMERS, sorted(set(SWARM_KEYS) - named)


def test_the_signature_names_exactly_the_twelve_target_widgets():
    assert set(SWARM_WIDGET_SIGNATURES) == SWARM_TARGET_WIDGETS
    assert len(SWARM_WIDGET_SIGNATURES) == 11


def test_a_parked_widget_is_not_also_a_mounted_target():
    """Parked means no body mounts it: a name in both maps would be
    dispatched by the screen *and* exempted from "mounted" by every test."""
    assert not set(models.SWARM_PARKED_WIDGET_SIGNATURES) & set(SWARM_WIDGET_SIGNATURES)


def test_workflows_reads_the_rows_and_its_own_clock():
    """Final review I1: retained workflows carry their own successful-read clock."""
    assert SWARM_WIDGET_SIGNATURES["SurfSwarmWorkflows"] == (
        "swarm_workflow_rows", "swarm_workflows_as_of_hhmm",
    )


def test_no_retired_key_is_named_by_a_target_signature():
    """The signatures describe the post-WP7 widgets: none may lean on a key
    WP7 deleted, or the screen's binding would name a key nothing emits."""
    named = {k for sig in SWARM_WIDGET_SIGNATURES.values() for k in sig}
    assert not (named & set(SWARM_RETIRED_KEYS)), sorted(named & set(SWARM_RETIRED_KEYS))


def test_no_swarm_key_leaks_a_raw_envelope():
    for bad in ("swarm_jobs", "swarm_health", "swarm_details", "swarm_skills",
                "swarm_launches", "swarm_sites", "swarm_workflows"):
        assert bad not in SURF_KEYS


# --- AGENT body on /seats/{tokenId}: WP0 freeze (docs/surf_agent_seats_plan.md §1.2, §1.3) ---


def test_the_seats_permanent_exports_are_the_frozen_literals():
    assert SWARM_SEAT_SELECTED_FIELDS == ("token_id", "agent_id", "selected_by")
    assert SWARM_SEAT_SUMMARY_FIELDS == (
        "attempts", "accepted", "reviewed", "review_entries", "review_status", "mean_score", "scored",
        "roles", "online", "owner", "paired_ts", "collaborators", "runtime",
        "agent_id", "daemon", "devices", "win_rate", "last_won_ts", "last_sent_ts",
        "last_worked_ts", "models",
    )
    assert SWARM_SEAT_REVIEW_STATUSES == ("sent", "submitted", "queued")
    # "pending" by the owner's Q-A answer (2026-09-21); None is not a member -- it is
    # "read failed, no last-good", the absence of a state.
    assert SWARM_SEAT_STATES == ("ok", "unknown_seat", "pending", "busy")


def test_the_agent_signatures_are_the_flipped_literals():
    """AGENT-seats plan §1.3, flipped in WP5 (the screen dispatch reads these)."""
    assert {k: SWARM_WIDGET_SIGNATURES[k] for k in AGENT_WIDGETS} == {
        "SurfSwarmAgentHero": (
            "swarm_seat_selected", "swarm_seat_summary", "swarm_seat_state",
            "swarm_seat_live", "swarm_seat_contrib", "swarm_seat_rank_delta",
            "swarm_seat_rewards", "swarm_seat_rewards_state",
        ),
        "SurfSwarmSeatCards": (
            "swarm_seat_summary", "swarm_seat_state", "swarm_seat_teammates",
            "swarm_seat_owner_ens", "swarm_seat_node_rows",
            "swarm_runtime_latest", "swarm_runtime_as_of_hhmm", "swarm_fleet_daemon",
        ),
        "SurfSwarmSeatRecord": ("swarm_seat_work_rows", "swarm_seat_state", "swarm_seat_as_of_hhmm", "swarm_seat_read"),
    }


def test_the_agent_signatures_reach_every_seats_key_and_drop_the_window_ones():
    named = {k for w in AGENT_WIDGETS for k in SWARM_WIDGET_SIGNATURES[w]}
    assert set(SWARM_SEATS_KEYS) <= named, sorted(set(SWARM_SEATS_KEYS) - named)
    assert "swarm_network" not in named



@pytest.mark.parametrize(("name", "expected"), [
    ("SWARM_BOARD_SUMMARY_FIELDS", (
        "seats", "live", "paused", "capacity", "working", "attempts", "accepted",
        "rejected", "pending", "devices", "turns", "wall_clock_ms", "input_tokens",
        "output_tokens", "receipts", "tokens_per_completed_job",
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
        "wall_clock_s", "rank", "ranked_of", "output_tokens",
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
    assert models.SWARM_PARKED_WIDGET_SIGNATURES["SurfSwarmInFlight"] == (
        "swarm_inflight_rows", "swarm_as_of_hhmm", "swarm_network",
    )


def test_polish_answer_and_advertised_model_contracts_are_frozen():
    assert models.SWARM_ANSWER_STATES == (
        "read", "not_read", "unavailable", "not_served", "no_reply",
    )
    assert models.SWARM_ANSWER_FIELDS == ("answer", "model", "took_s", "output_tokens", "state")
    assert models.SWARM_ANSWER_CACHE_FIELDS == (
        "answer", "model", "took_s", "output_tokens", "state", "read_ts", "terminal",
        "reply", "failure_reason", "turns", "cached_input_tokens", "failed_checks",
        "findings", "artifacts", "others", "others_total",
    )
    assert models.SWARM_FLEET_MODEL_FIELDS == ("model", "effort", "count")


def test_polish_answer_fetch_window_agrees_with_record_row_cap():
    from maxpane_dashboard.widgets.surf.swarm_seat_record import SurfSwarmSeatRecord
    assert models.SWARM_ANSWER_ROW_CAP == 40
    assert models.SWARM_ANSWER_ROW_CAP == SurfSwarmSeatRecord.ROW_CAP


def test_layout_v3_hero_contract_uses_summary_sources():
    assert SWARM_WIDGET_SIGNATURES["SurfSwarmHero"] == (
        "swarm_agents_online", "swarm_agents_enrolled", "swarm_working_now",
        "swarm_accepted_today", "swarm_launch_summary", "swarm_workflow_rows", "swarm_site_rows",
    )


def test_polish_unenriched_work_rows_explicitly_wait_for_answer_read():
    from maxpane_dashboard.data.surf_swarm import seat_work_rows
    from tests.surf_swarm_fixtures import swarm_seat_capture
    rows = seat_work_rows(swarm_seat_capture("seat_420"))
    assert rows
    for row in rows:
        assert (row["answer"], row["answer_state"], row["model"], row["took_s"]) == (
            None, "not_read", None, None,
        )


def test_oracle_contract_and_row_defaults():
    from maxpane_dashboard.data.surf_swarm import seat_work_rows
    assert models.SWARM_PANEL_STATES == (
        "agreed", "outvoted", "no_quorum_in", "no_quorum_out", "assessing", "blocked",
        "off_panel", "not_oracle", "not_read", "unavailable",
    )
    assert models.SWARM_ORACLE_NODE_KEYS == ("oracle_assess",)
    assert models.SWARM_ORACLE_CACHE_FIELDS == (
        "request_id", "status", "in_cluster", "on_panel", "agreed", "quorum",
        "panel_size", "figure", "answer_type", "answer_bool", "read_ts", "terminal",
        "question", "chain_id", "member_ok", "member_reason", "seat_answer", "notes",
    )
    for node, state in [("oracle_assess", "not_read"), ("implement", "not_oracle")]:
        row = seat_work_rows({"work": [{"nodeKey": node}]})[0]
        assert set(row) == set(models.SURF_ROW_KEYS["swarm_seat_work_rows"])
        assert row["panel_state"] == state
        assert row["output_tokens"] is None


def test_seat_resilience_contract_freezes_the_busy_sentinel_and_cache_cap():
    from types import MappingProxyType
    from maxpane_dashboard.data import surf_swarm, surf_swarm_client

    assert isinstance(surf_swarm_client.SEAT_BUSY, MappingProxyType)
    assert dict(surf_swarm_client.SEAT_BUSY) == {"error": "busy"}
    assert "SEAT_BUSY" in surf_swarm_client.__all__
    with pytest.raises(TypeError):
        surf_swarm_client.SEAT_BUSY["error"] = "changed"
    assert surf_swarm.SEAT_SLOT_CAP == 6
    assert [name for name, signature in SWARM_WIDGET_SIGNATURES.items()
            if "swarm_seat_read" in signature] == ["SurfSwarmSeatRecord"]


# --- SWARM WORKFLOWS (docs/surf_swarm_workflows_spec.md §2, WP2) -------------


def test_workflow_history_limits_are_frozen():
    assert models.SWARM_WORKFLOW_PAGE_SIZE == 100
    assert models.SWARM_WORKFLOW_MAX_PAGES == 10
    assert models.SWARM_WORKFLOW_HISTORY_CAP == 1000


def test_capability_is_parked_with_its_frozen_signature():
    """§2 "CAPABILITY is parked": the export every "is every widget mounted /
    every key consumed" test takes its exemption from (wired in WP5: this
    file's ``_consumed_keys``, the surf screen, widget-contract and
    registration tests)."""
    import inspect
    from maxpane_dashboard.widgets.surf.swarm_capability import SurfSwarmCapability

    assert models.SWARM_PARKED_WIDGET_SIGNATURES == {
        "SurfSwarmThroughput": ("swarm_throughput", "swarm_as_of_hhmm", "swarm_stale"),
        "SurfSwarmInFlight": ("swarm_inflight_rows", "swarm_as_of_hhmm", "swarm_network"),
        "SurfSwarmCapability": (
            "swarm_skill_rows", "swarm_skill_summary", "swarm_scores_as_of_hhmm",
        ),
    }
    for widget, kwargs in models.SWARM_PARKED_WIDGET_SIGNATURES.items():
        for key in kwargs:
            assert key in (*SWARM_KEYS, "as_of"), f"{widget} takes {key!r}, not a declared snapshot key"
    signature = inspect.signature(SurfSwarmCapability.update_data)
    actual = tuple(name for name, value in signature.parameters.items()
                   if name != "self" and value.kind != inspect.Parameter.VAR_KEYWORD)
    assert actual == models.SWARM_PARKED_WIDGET_SIGNATURES["SurfSwarmCapability"]
