"""Pure, clock-injected projections for the SWARM TOKENS market overview."""

from copy import deepcopy

from maxpane_dashboard.analytics.swarm_tokens_hero import has_price_change, observed, project as project_hero


def select_tokens(tokens: list[dict], *, chain: str = 'all', query: str = '',
                  lp_state: str = 'all', sort: str = 'volume') -> list[dict]:
    """Filter and sort independent copies; unknown numeric values sort last."""
    needle = query.strip().casefold()
    allowed = {'one-sided': {'one-token', 'one-quote'},
               'issues': {'withdrawn', 'unknown'}}.get(lp_state, {lp_state})
    rows = [row for row in tokens
            if (chain == 'all' or row['chain'] == chain)
            and (lp_state == 'all' or row['lp_state'] in allowed)
            and (not needle or any(needle in str(row.get(key, '')).casefold()
                                   for key in ('symbol', 'name', 'launch_id', 'token_address')))]
    if sort == 'symbol':
        rows.sort(key=lambda row: (row['symbol'].casefold(), row['id']))
    else:
        key = {'volume': 'volume_24h', 'change': 'change_24h',
               'newest': 'launched_at'}[sort]
        rows.sort(key=lambda row: (row[key] is None, -(row[key] or 0), row['id']))
    return deepcopy(rows)


def project_snapshot(snapshot: dict, *, chain: str = 'all', query: str = '',
                     lp_state: str = 'all', sort: str = 'volume') -> dict:
    """Apply one selection to every panel, preserving known zero versus unknown."""
    extra = {'sources': deepcopy(snapshot['sources'])} if 'sources' in snapshot else {}
    if snapshot['tokens'] is None:
        return dict(tokens=None, metrics=None, newly_launched=None, gainers=None,
                    losers=None, activity=None, as_of=snapshot['as_of'],
                    is_mock=snapshot['is_mock'], tokens_hero=project_hero(
                        None, catalogue=extra.get('sources', {}).get('catalogue'),
                        now=snapshot['as_of'], is_mock=snapshot['is_mock']), **extra)
    tokens = select_tokens(snapshot['tokens'], chain=chain, query=query,
                           lp_state=lp_state, sort=sort)
    now = snapshot['as_of']
    new = sorted((row for row in tokens if row['launched_at'] is not None
                  and 0 <= now-row['launched_at'] < 86400),
                 key=lambda row: (-row['launched_at'], row['id']))
    hero = project_hero(tokens, catalogue=extra.get('sources', {}).get('catalogue'),
                        now=now, is_mock=snapshot['is_mock'])
    pools, volume, liquidity = (hero[key] for key in ('pools', 'volume', 'liquidity'))
    metrics = {
        'total': len(tokens), 'new_24h': len(new), 'two_sided': pools['two_sided'] or 0,
        'one_sided': pools['one_sided'] or 0, 'unknown': pools['unknown'] if pools['unknown'] is not None else len(tokens),
        'other': pools['other'] or 0,
        'volume_24h': volume['amount'] if volume['known'] else None,
        'volume_known': volume['known'] or 0, 'volume_total': len(tokens),
        'liquidity_imd': liquidity['imd'], 'liquidity_eth': liquidity['eth'],
        'liquidity_partial': liquidity['partial'],
    }
    priced = [row for row in tokens
              if has_price_change(row)
              and observed(row, 'market', now, snapshot['is_mock'])]
    gainers = sorted((row for row in priced if row['change_24h'] > 0),
                     key=lambda row: (-row['change_24h'], row['id']))
    losers = sorted((row for row in priced if row['change_24h'] < 0),
                    key=lambda row: (row['change_24h'], row['id']))
    ids = {row['id'] for row in tokens}
    activity = sorted((row for row in snapshot['activity'] or [] if row['token_id'] in ids),
                      key=lambda row: (-row['ts'], row['id']))
    return {
        'tokens': tokens, 'metrics': metrics, 'newly_launched': new,
        'gainers': gainers, 'losers': losers, 'activity': deepcopy(activity),
        'as_of': now, 'is_mock': snapshot['is_mock'],
        'tokens_hero': hero, **extra,
    }
