"""LAUNCHPAD getter and history cards from matching source observations."""
from maxpane_dashboard.analytics.surfboard import count, number
from maxpane_dashboard.data.surf_launchpad_volume import coerce_snapshot
from maxpane_dashboard.data.surf_pool4_hero import _facts, _source
from maxpane_dashboard.data.surfboard import _launchpad_volume


def _volume(data, launchpad, pad, market, now):
    snapshot = coerce_snapshot(launchpad.get('volume_2h'), now=now)
    if snapshot is not None and (count(number(snapshot['known'])) is None
            or snapshot['total'] is not None and count(number(snapshot['total'])) is None):
        snapshot = None
    quote = number(data.get('eth_usd')) if market['state'] != 'unavailable' else None
    quote = quote if quote is not None and quote > 0 else None
    # The captured envelope owns failure state, not a later global degraded list.
    points, state, _ = _launchpad_volume(
        {'eth_usd': quote}, {'volume_2h': snapshot}, {'launchpad': pad, 'quote': market}, now)
    if pad['state'] == 'unavailable':
        points, state = None, 'unavailable'
    usd = number(sum(points)) if points is not None else None
    if points is not None and usd is None and state == 'ok':
        state = 'partial'
    observed = snapshot or {}
    stamps = [pad['read_ts'], observed.get('read_ts')]
    if quote is not None:
        stamps.append(market['read_ts'])
    stamps = [stamp for stamp in stamps if stamp is not None]
    return dict(state=state, read_ts=min(stamps) if stamps else None, usd=usd, points=points,
                until=observed.get('until'), known=observed.get('known'), total=observed.get('total'),
                quote=quote, quote_read_ts=market['read_ts'], volume_read_ts=observed.get('read_ts'))


def project(*, data: dict, launchpad: dict, sources: dict, now: float) -> dict:
    """Use native whole units; covered volume conversion remains shared with the rack."""
    pad, market = (_source(sources, name, now) for name in ('launchpad', 'market'))
    population = count(number(data.get('launchpad_coin_count')))
    swept = count(number(data.get('launchpad_launch_count')))
    history = dict(pad)
    if history['state'] == 'ok' and (population is None or swept is None or population != swept):
        history['state'] = 'partial'
    coins = _facts(history, count=population, new_24h=count(number(data.get('launchpad_new_24h'))), swept=swept)
    flow = _facts(history, swaps=count(number(data.get('launchpad_swap_count'))),
                  traders=count(number(data.get('launchpad_trader_count'))),
                  creators=count(number(data.get('launchpad_creator_count'))))
    fees = _facts(pad, eth=number(data.get('launchpad_creator_eth_owed')))
    ready = data.get('burn_ready')
    queue = _facts(pad, accrued=number(data.get('burn_accrued')), staged=number(data.get('burn_staged')),
                   sendable=number(data.get('burn_bridgeable')), ready=ready if type(ready) is bool else None)
    burned = _facts(history, imd=number(data.get('launchpad_burned_total')))
    return dict(coins=coins, flow=flow, volume=_volume(data, launchpad, pad, market, now),
                fees=fees, queue=queue, burned=burned)
