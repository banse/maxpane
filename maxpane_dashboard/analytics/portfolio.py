"""Pure wallet projections over the existing swarm market projection."""

from copy import deepcopy
from math import isfinite

from maxpane_dashboard.analytics.swarm_tokens import project_snapshot as market_snapshot, select_tokens


def _number(value) -> bool:
    return type(value) in (int, float) and isfinite(value) and value >= 0


def _positive(value) -> bool:
    return _number(value) and value > 0


def _ready(row: dict) -> bool:
    return (row['claim_state'] == 'ready' and row['claim_read_state'] in {'ok', 'stale'}
            and _positive(row['claimable_quantity']))


def _value(row: dict, quantity: str, state: str) -> float | None:
    amount = row[quantity]
    if row[state] != 'ok' or not _number(amount):
        return None
    if amount == 0:
        return 0
    price = row['price_usd']
    if row.get('market_state', 'ok') != 'ok' or not _number(price):
        return None
    value = amount * price
    return value if isfinite(value) else None


def _identity(row: dict) -> tuple:
    address = row.get('token_address')
    if address:
        return row.get('chain_id') or row['chain'], str(address).casefold()
    return row['chain'], row['id']


def _deduplicate(tokens: list[dict]) -> tuple[list[dict], dict]:
    rows, identities, aliases = [], {}, {}
    for original in tokens:
        row = deepcopy(original)
        identity = _identity(row)
        if identity not in identities:
            identities[identity] = row['id']
            rows.append(row)
        aliases[row['id']] = identities[identity]
    return rows, aliases


def _liquidity_tokens(tokens: list[dict]) -> list[dict]:
    """One launch position contributes once, even when two rows reference it."""
    rows, seen = [], set()
    for row in tokens:
        position = row.get('paired_position_id') or row.get('launch_pool')
        identity = (row['chain'], str(position).casefold()) if position else _identity(row)
        if identity not in seen:
            seen.add(identity)
            rows.append(row)
    return rows


def _subtotal(tokens: list[dict], quantity: str, state: str, value: str) -> tuple:
    positions = [row for row in tokens if row[quantity] != 0 or row[state] != 'ok']
    values = [row[value] for row in positions if row[value] is not None]
    return (sum(values) if values or not positions else None, len(values), len(positions))


def _pnl(tokens: list[dict], *, live=False) -> tuple:
    """Unrealized USD P/L needs current value and cost for every held position."""
    held = [row for row in tokens if row['held_quantity'] != 0 or row['balance_state'] != 'ok']
    if any(row['held_usd'] is None or not _number(row.get('held_cost_usd')) for row in held):
        return None, None
    if live and any(row.get('basis_state') != 'ok' or not row.get('basis_source')
                    or row.get('basis_read_at') is None
                    or row.get('basis_quantity') != row['held_quantity'] for row in held):
        return None, None
    cost = sum(row['held_cost_usd'] for row in held)
    gain = sum(row['held_usd'] for row in held) - cost
    if not isfinite(gain) or not isfinite(cost):
        return None, None
    percent = gain / cost * 100 if cost else None
    return gain, percent if percent is not None and isfinite(percent) else None


def _live_sources(result, snapshot):
    if snapshot['is_mock']:
        return result
    sources = deepcopy(snapshot.get('sources') or {})
    result.update(wallet_generation=snapshot.get('wallet_generation'), sources=sources)
    metrics = result['metrics']
    if metrics is not None:
        catalogue = sources.get('catalogue') or {}
        discovery = catalogue.get('coverage_complete', catalogue.get('complete', False))
        for name, source in (('held', 'balances'), ('claimable', 'claims')):
            complete = (sources.get(source) or {}).get('complete', False)
            if name == 'held':
                complete = complete and discovery
            partial = not complete or metrics[name + '_known'] < metrics[name + '_total']
            metrics[name + '_partial'] = partial
            if partial and metrics[name + '_known'] == 0:
                metrics[name + '_value'] = None
        if metrics['held_partial']:
            metrics['pnl_usd'] = metrics['pnl_percent'] = None
        agents = sources.get('agents') or {}
        metrics.update(agents_state=agents.get('state', 'unavailable'), agents_as_of=agents.get('as_of'))
    return result


def project_snapshot(snapshot: dict, *, chain: str = 'all', query: str = '',
                     lp_state: str = 'all', assets: str = 'all',
                     sort: str = 'value') -> dict:
    """Keep held balances and ready claims separate, with coverage in totals.

    Shared filters select holdings and claims; the table, held value and market
    panels use only positive wallet holdings. Claims retain their own population.
    Agent counts are wallet-wide. Input and output collections are detached.
    """
    wallet = snapshot.get('wallet')
    agents = deepcopy(snapshot.get('agents')) if wallet is not None else []
    if agents is not None:
        agents = list({agent['id']: agent for agent in agents}.values())
    if wallet is not None and snapshot['tokens'] is None:
        return _live_sources(dict(wallet=wallet, tokens=None, metrics=None, claimable=None,
                    gainers=None, losers=None, activity=None, agents=agents,
                    as_of=snapshot['as_of'], is_mock=snapshot['is_mock']), snapshot)

    rows, aliases = _deduplicate(snapshot['tokens'] or []) if wallet is not None else ([], {})
    selected = []
    for row in rows:
        if row['claim_read_state'] == 'ok' and row['claim_state'] in {'none', 'locked', 'claimed'}:
            row['claimable_quantity'] = 0
        if row['claim_state'] == 'unavailable':
            row['claimable_quantity'] = None
        held, ready = _positive(row['held_quantity']), _ready(row)
        if not (held or ready) or (assets == 'held' and not held) or (assets == 'claimable' and not ready):
            continue
        row['held_usd'] = _value(row, 'held_quantity', 'balance_state')
        row['claimable_usd'] = _value(row, 'claimable_quantity', 'claim_read_state')
        selected.append(row)
    activity = [dict(row, token_id=aliases.get(row['token_id'], row['token_id']))
                for row in snapshot.get('activity') or []]
    base = dict(snapshot, tokens=selected, activity=activity)
    tokens = select_tokens(selected, chain=chain, query=query, lp_state=lp_state,
                           sort=sort if sort not in {'value', 'claimable'} else 'symbol')
    if sort in {'value', 'claimable'}:
        key = 'held_usd' if sort == 'value' else 'claimable_usd'
        tokens.sort(key=lambda row: (row[key] is None, -(row[key] or 0), row['id']))
    claims = _subtotal(tokens, 'claimable_quantity', 'claim_read_state', 'claimable_usd')
    claimable = sorted((row for row in tokens if _ready(row)),
                       key=lambda row: (row['claimable_usd'] is None,
                                        -(row['claimable_usd'] or 0), row['id']))
    pnl, pnl_percent = _pnl(tokens, live=not snapshot['is_mock'])
    tokens = [row for row in tokens if _positive(row['held_quantity'])]
    held = _subtotal(tokens, 'held_quantity', 'balance_state', 'held_usd')
    market = market_snapshot(dict(base, tokens=tokens))
    liquidity = market_snapshot(dict(base, tokens=_liquidity_tokens(tokens)))['metrics']
    online = (sum(agent['online'] is True for agent in agents)
              if agents is not None and all(agent['online'] is not None for agent in agents) else None)
    metrics = dict(
        total=len(tokens), held_value=held[0], held_known=held[1], held_total=held[2],
        claimable_value=claims[0], claimable_known=claims[1], claimable_total=claims[2],
        agents_total=len(agents) if agents is not None else None, agents_online=online,
        liquidity_imd=liquidity['liquidity_imd'], liquidity_eth=liquidity['liquidity_eth'],
        liquidity_partial=liquidity['liquidity_partial'],
        pnl_usd=pnl, pnl_percent=pnl_percent,
    )
    return _live_sources(dict(
        wallet=wallet, tokens=tokens, metrics=metrics, claimable=claimable,
        gainers=market['gainers'], losers=market['losers'], activity=market['activity'],
        agents=agents, as_of=snapshot['as_of'], is_mock=snapshot['is_mock'],
    ), snapshot)
