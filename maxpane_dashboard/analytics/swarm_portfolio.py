"""Pure filtering and sums of an already apportioned portfolio scan."""
from copy import deepcopy
import math


def _known(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _sum(rows, key):
    values = [row.get(key) for row in rows]
    valid = [value for value in values if _known(value)]
    return sum(valid) if valid or not values else None


def project(snapshot, chain='all', query='', show_no_sale=False, sort='value'):
    """Filter all sections without independently quoting parts of a token sale."""
    result = deepcopy(snapshot)
    seats = snapshot.get('seats')
    seat_metrics = dict(seats_count=len(seats) if isinstance(seats,list) else None,
                        seat_ids=[str(row['token_id']) for row in seats or []])
    query = query.strip().lower()
    def matches(row):
        return (str(chain) == 'all' or str(row.get('chain_id')) == str(chain)) and (
            not query or query in ' '.join(str(row.get(key) or '') for key in
                                          ('symbol', 'name', 'token_address', 'contract_address', 'id')).lower())
    all_assets = snapshot.get('assets')
    if all_assets is None:
        result.update(holdings=None, metrics={key:None for key in (
            'total_usd', 'wallet_usd', 'staked_usd', 'unclaimed_usd', 'ready_usd', 'locked_usd',
            'pending_usd', 'unknown_reward_usd', 'holding_count', 'position_count', 'claim_count',
            'nft_count', 'nft_collections', 'seats_count', 'hidden_count')})
        result['metrics'].update(partial=True, claims_partial=True, **seat_metrics)
        return result
    assets = [deepcopy(row) for row in all_assets if matches(row)]
    ids = {row['id'] for row in assets}
    def rank(row):
        value = row.get('total_usd')
        return (not _known(value), -value if _known(value) else 0, row.get('symbol') or '', row['id'])
    assets.sort(key=(lambda row:(row.get('symbol') or '', row['id'])) if sort == 'symbol' else rank)
    result['assets'] = assets
    # Show unknown valuations even when hiding observations with zero proceeds.
    held = [row for row in assets if not _known(row.get('wallet_quantity')) or row['wallet_quantity'] > 0]
    hidden = [row for row in held if row.get('wallet_usd') == 0 and row.get('sell_state') in ('none','no_pool')]
    result['holdings'] = held if show_no_sale else [row for row in held if row not in hidden]
    for name in ('positions','rewards','utilities'):
        result[name] = [deepcopy(row) for row in snapshot.get(name) or [] if row.get('asset_id') in ids
                        or row.get('asset_id') is None and matches(row)]
    for name in ('nfts','standings'):
        result[name] = [deepcopy(row) for row in snapshot.get(name) or [] if matches(row)]
    metrics = {key + '_usd': _sum(assets, key + '_usd') for key in
               ('wallet','staked','ready','locked','pending','unknown_reward')}
    rewards = result['rewards']
    metrics['staked_usd'] = _sum(result['positions'], 'value_usd')
    metrics['unclaimed_usd'] = _sum(rewards, 'value_usd')
    claims_partial = (snapshot.get('coverage') or {}).get('claims_complete') is not True
    if claims_partial and not rewards: metrics['unclaimed_usd'] = None
    if any(row.get('status') == 'unknown' for row in rewards): metrics['ready_usd'] = None
    if not all_assets and (snapshot.get('coverage') or {}).get('malformed_rows'):
        metrics = {key:None for key in metrics}
    metrics['total_usd'] = _sum([dict(value=value) for value in
        (metrics['wallet_usd'],metrics['staked_usd'],metrics['unclaimed_usd'])], 'value')
    metrics.update(holding_count=len(held), position_count=len(result['positions']),
        claim_count=len(rewards), nft_count=_sum(result['nfts'],'count'), nft_collections=len(result['nfts']),
        **seat_metrics, hidden_count=len(hidden),
        partial=snapshot.get('state') in ('partial','stale','unavailable','loading') or claims_partial
                or any(row.get('total_usd') is None for row in assets), claims_partial=claims_partial)
    result['metrics'] = metrics
    return result
