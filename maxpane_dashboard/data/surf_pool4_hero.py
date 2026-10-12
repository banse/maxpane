"""Six POOL4 rack facts from matching flat values and captured source clocks."""
from maxpane_dashboard.analytics.surf_pool4_depth import MAX_TICK, band_distance_pct
from maxpane_dashboard.analytics.surfboard import count, number
from maxpane_dashboard.data.surf_news_hero import _stamp


def _source(sources, name, now):
    raw = sources.get(name)
    raw = raw if isinstance(raw, dict) else {}
    stamp = _stamp(raw.get('read_ts'), now)
    state = raw.get('state')
    return dict(state=state if stamp is not None and state in ('ok', 'partial', 'stale')
                else 'unavailable', read_ts=stamp)


def _joined(sources):
    if not sources or any(source['state'] == 'unavailable' for source in sources):
        return dict(state='unavailable', read_ts=None)
    state = ('stale' if any(source['state'] == 'stale' for source in sources) else
             'partial' if any(source['state'] == 'partial' for source in sources) else 'ok')
    return dict(state=state, read_ts=min(source['read_ts'] for source in sources))


def _facts(source, **values):
    if source['state'] == 'unavailable':
        values = dict.fromkeys(values)
    known = sum(value is not None for value in values.values())
    state = ('unavailable' if not known else source['state'] if source['state'] != 'ok'
             else 'partial' if known < len(values) else 'ok')
    return dict(state=state, read_ts=source['read_ts'], **values)


def _signed(value):
    return value if type(value) in (int, float) and number(abs(value)) is not None else None


def _tick(value):
    return value if type(value) is int and -MAX_TICK <= value <= MAX_TICK else None


def project(*, data: dict, sources: dict, now: float) -> dict:
    """No re-pricing or re-annualising: the existing producer owns each metric."""
    pool, market, stakers = (_source(sources, name, now) for name in ('pool4', 'market', 'stakers'))
    price = _facts(_joined([pool, market]), usd=number(data.get('pool4_price_usd')))
    usable_price = price['state'] != 'unavailable'
    venue = data.get('pool4_cheaper_venue')
    price.update(venue=venue if usable_price and venue in ('here', 'reference') else None,
                 gap_pct=_signed(data.get('pool4_venue_gap_pct')) if usable_price else None)
    rate = _facts(pool, imd=number(data.get('pool4_share_price')))
    staking = _facts(pool, apr=number(data.get('pool4_trailing_return_pct')))

    assets = _facts(pool, imd=number(data.get('pool4_vault_assets')),
                    simd=number(data.get('pool4_vault_shares')))
    holders = _facts(stakers, holders=count(data.get('pool4_staker_count')))
    contributing = [source for source in (assets, holders) if source['state'] != 'unavailable']
    vault = _facts(_joined(contributing), imd=assets['imd'], simd=assets['simd'], holders=holders['holders'])
    holder_source = sources.get('stakers')
    incomplete = isinstance(holder_source, dict) and holder_source.get('partial') is True
    vault.update(holders_state=holders['state'], holders_read_ts=holders['read_ts'],
                 holders_partial=holders['holders'] is not None and (incomplete or holders['state'] == 'partial'))

    status = data.get('pool4_backstop_state')
    if status not in ('none', 'deployed') or pool['state'] == 'unavailable':
        bid = dict(pool, state='unavailable', status=None, eth=None, distance_pct=None)
    elif status == 'none':
        bid = dict(pool, status='none', eth=None, distance_pct=None)
    else:
        distance = band_distance_pct(_tick(data.get('pool4_current_tick')),
                                     _tick(data.get('pool4_backstop_lower_tick')))
        bid = _facts(pool, status=status, eth=number(data.get('pool4_backstop_eth')),
                     distance_pct=number(distance))
    queue = _facts(pool, imd=number(data.get('pool4_backlog_imd')),
                   per_day=number(data.get('pool4_drip_per_day')), days=number(data.get('pool4_backlog_days')))
    return dict(price=price, rate=rate, staking=staking, vault=vault, bid=bid, queue=queue)
