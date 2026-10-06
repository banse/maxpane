"""The upcoming LATEST LAUNCHES input contract, frozen before its WP3 renderer."""
from maxpane_dashboard.data import surf_models as models


def test_latest_and_throughput_signatures_are_frozen_before_mount_switch():
    assert models.SWARM_LATEST_LAUNCHES_SIGNATURE == (
        'swarm_launch_rows', 'swarm_launches_as_of_hhmm', 'as_of')
    assert models.SWARM_THROUGHPUT_SIGNATURE == (
        'swarm_throughput', 'swarm_as_of_hhmm', 'swarm_stale')
