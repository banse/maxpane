"""Six PROTOCOL cards from existing whole-unit facts and one captured pool read."""
from maxpane_dashboard.analytics.surfboard import count, number
from maxpane_dashboard.data.surf_models import POOL4_COUNTER_STATES, POOL4_REWARD_PATHS
from maxpane_dashboard.data.surf_pool4_hero import _facts, _signed, _source


def _percentage(value, denominator):
    share = count(value)
    if denominator is None or share is None or share > denominator:
        return None
    return share / denominator * 100


def project(*, data: dict, sources: dict, now: float) -> dict:
    """The native producer owns units, headroom, derived bonding and drift."""
    pool = _source(sources, 'pool4', now)
    totals = _facts(pool, burned=number(data.get('pool4_total_burned')),
                    rewarded=number(data.get('pool4_total_rewarded')),
                    fees=number(data.get('pool4_total_fee_token')))
    inventory = _facts(pool, cap=number(data.get('pool4_inventory_cap')),
                       reserve=number(data.get('pool4_tokens_in_pool')),
                       headroom=_signed(data.get('pool4_cap_headroom')))

    route = data.get('pool4_reward_path')
    route = route if route in POOL4_REWARD_PATHS else None
    if route == 'direct':
        # No distributor subdivision exists on the explicit direct route.
        split = _facts(pool, path=route)
        split.update(staking_pct=None, nodes_pct=None, bonding_pct=None)
    else:
        denominator = count(data.get('pool4_bps_denominator'))
        if route is None or number(denominator) is None or denominator == 0:
            denominator = None
        split = _facts(pool, path=route,
            staking_pct=_percentage(data.get('pool4_distributor_staking_bps'), denominator),
            nodes_pct=_percentage(data.get('pool4_distributor_nodes_bps'), denominator),
            bonding_pct=_percentage(data.get('pool4_distributor_bonding_bps'), denominator))

    unsettled = _facts(pool, burn=number(data.get('pool4_unsettled_burn')),
                       rewards=number(data.get('pool4_unsettled_stakers')))
    delivery = _facts(pool, queued=number(data.get('pool4_backlog_imd')),
                      ready=number(data.get('pool4_drippable')),
                      per_day=number(data.get('pool4_drip_per_day')))
    counters = data.get('pool4_counter_state')
    checks = _facts(pool, counters=counters if counters in POOL4_COUNTER_STATES else None,
                    drift_bps=_signed(data.get('pool4_split_drift_bps')), path=route)
    return dict(totals=totals, inventory=inventory, split=split,
                unsettled=unsettled, delivery=delivery, checks=checks)
