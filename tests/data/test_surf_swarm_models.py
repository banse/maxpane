from maxpane_dashboard.data.surf_models import SURF_KEYS, SURF_ROW_KEYS, SWARM_KEYS

SWARM_ROW_NAMES = ("swarm_field_rows", "swarm_queue_rows", "swarm_blocked_rows",
                   "swarm_shipped_rows", "swarm_score_rows")


def test_the_swarm_block_is_eighteen_keys():
    assert len(SWARM_KEYS) == 18
    assert len(set(SWARM_KEYS)) == 18
    assert all(k.startswith("swarm_") for k in SWARM_KEYS)


def test_every_swarm_key_appears_in_surf_keys_exactly_once():
    for key in SWARM_KEYS:
        assert SURF_KEYS.count(key) == 1, key


def test_the_swarm_block_is_contiguous_and_last():
    positions = [SURF_KEYS.index(k) for k in SWARM_KEYS]
    assert positions == sorted(positions)
    assert positions == list(range(positions[0], positions[0] + len(SWARM_KEYS)))
    assert positions[-1] == len(SURF_KEYS) - 1


def test_every_swarm_row_shape_is_declared_and_is_a_payload_key():
    for name in SWARM_ROW_NAMES:
        assert name in SURF_ROW_KEYS, name
        assert SURF_ROW_KEYS[name], name
        assert name in SURF_KEYS, name


def test_the_field_row_is_exactly_the_frozen_shape():
    assert SURF_ROW_KEYS["swarm_field_rows"] == (
        "job_id", "template", "objective", "node_key", "role", "node_state",
        "agent_token", "agent_id", "revisions", "dispatch_note", "moved_ts",
        "age_s",
    )


def test_no_swarm_key_leaks_a_raw_envelope():
    for bad in ("swarm_jobs", "swarm_health", "swarm_details"):
        assert bad not in SURF_KEYS
