"""Optional payout timestamps preserve legacy valid reward balances."""
import pytest

from maxpane_dashboard.data.surf_swarm import coerce_rewards_slot

NOW = 1_800_000_000


def point(**values):
    return dict(owner='0x'+'ab'*20, paired_ts=NOW-100000, raw=10**18,
                decimals=18, seats=1, transfers=2, read_ts=NOW-10, **values)


def test_legacy_reward_points_and_known_payment_timestamp_roundtrip():
    legacy = point()
    current = point(last_paid_ts=NOW-100)
    result = coerce_rewards_slot({'420': legacy, '7': current}, now=NOW)
    assert result['420'] == dict(legacy, last_paid_ts=None)
    assert result['7'] == current
    assert coerce_rewards_slot(result, now=NOW) == result


@pytest.mark.parametrize('bad', [None, True, -1, '123', float('nan'), float('inf'), NOW+1, NOW-9, NOW-100001])
def test_invalid_optional_timestamp_drops_only_timestamp(bad):
    raw = point(last_paid_ts=bad)
    assert coerce_rewards_slot({'420': raw}, now=NOW)['420'] == dict(raw, last_paid_ts=None)


@pytest.mark.parametrize('changes', [dict(raw=0), dict(transfers=0)])
def test_reward_timestamp_needs_a_positive_recorded_payment(changes):
    raw = point(last_paid_ts=NOW-100) | changes
    assert coerce_rewards_slot({'420': raw}, now=NOW)['420']['last_paid_ts'] is None
