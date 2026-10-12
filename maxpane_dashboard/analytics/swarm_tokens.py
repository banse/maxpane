"""Pure, clock-injected projections for the SWARM TOKENS market overview."""

from copy import deepcopy
from math import isfinite

from maxpane_dashboard.analytics.swarm_tokens_hero import project as project_hero


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
    volumes = [row['volume_24h'] for row in tokens if row['volume_24h'] is not None
               and row.get('market_state', 'ok') == 'ok']
    counts = {state: sum(row['lp_state'] == state for row in tokens)
              for state in ('two-sided', 'one-token', 'one-quote', 'unknown')}
    one_sided = counts['one-token'] + counts['one-quote']
    paired = [row for row in tokens if row.get('liquidity_state', 'ok') == 'ok'
              and type(row.get('paired_amount')) in (int, float)
              and isfinite(row['paired_amount']) and row['paired_amount'] >= 0
              and isinstance(row.get('paired_symbol'), str) and row['paired_symbol'].strip()]
    partial = len(paired) < len(tokens)
    totals = {}
    for asset in ('IMD', 'ETH'):
        amounts = [row['paired_amount'] for row in paired if row['paired_symbol'].strip().upper() == asset]
        totals[asset] = sum(amounts) if amounts or not partial else None
    metrics = {
        'total': len(tokens), 'new_24h': len(new), 'two_sided': counts['two-sided'],
        'one_sided': one_sided, 'unknown': counts['unknown'],
        'other': len(tokens)-counts['two-sided']-one_sided-counts['unknown'],
        'volume_24h': sum(volumes) if volumes else None,
        'volume_known': len(volumes), 'volume_total': len(tokens),
        'liquidity_imd': totals['IMD'], 'liquidity_eth': totals['ETH'],
        'liquidity_partial': partial,
    }
    priced = [row for row in tokens
              if row['price_usd'] is not None and row['price_usd'] > 0
              and row['change_24h'] is not None
              and row.get('market_state', 'ok') == 'ok']
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
        'tokens_hero': project_hero(tokens, catalogue=extra.get('sources', {}).get('catalogue'),
                                    now=now, is_mock=snapshot['is_mock']), **extra,
    }
