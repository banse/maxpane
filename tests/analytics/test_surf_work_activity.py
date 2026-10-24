"""Rolling activity windows use the caller's clock, including updated old rows."""
import pytest

from maxpane_dashboard.analytics.surf_work import activity_ts, recent_activity


@pytest.mark.parametrize("row, stamp, recent", [
    ({"created_ts": 1, "updated_ts": 100_000}, 100_000, True),
    ({"created_ts": 100_000, "updated_ts": 1}, 100_000, True),
    ({"created_ts": 13_600}, 13_600, True),
    ({"updated_ts": 13_599}, 13_599, False),
    ({"created_ts": 100_001}, 100_001, False),
    ({"created_ts": 14_000, "updated_ts": float("nan")}, 14_000, True),
    ({"created_ts": 14_000, "updated_ts": float("inf")}, 14_000, True),
    ({"created_ts": 14_000, "updated_ts": True}, 14_000, True),
    ({"created_ts": -1, "updated_ts": "100000"}, None, False),
    ({}, None, False),
])
def test_latest_valid_activity_and_inclusive_window(row, stamp, recent):
    assert activity_ts(row) == stamp
    assert recent_activity(row, 100_000) is recent


@pytest.mark.parametrize("now", [None, True, float("nan"), float("inf"), "100000"])
def test_unknown_clock_cannot_establish_recent_activity(now):
    assert not recent_activity({"created_ts": 100_000}, now)
