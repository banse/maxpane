"""The six selected-token cards reuse Surf's rack renderer and palette."""
from textual.containers import Grid

from maxpane_dashboard.widgets.fmt import as_float
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, LocalSourceHeroCard
from maxpane_dashboard.widgets.swarm_tokens import _change, _paired
from ._fmt import metric_label, source, token_source


def records(token=None, launch=None, contributors=None, sources=None, is_mock=False):
    token, launch = token or {}, launch or {}
    seats = None if contributors is None else len({row['seat'] for row in contributors
        if isinstance(row, dict) and row.get('seat') is not None})
    market, liquidity = token_source(token, 'market'), token_source(token, 'liquidity')
    launch_source, contribution_source = source(sources, 'launch'), source(sources, 'contributors')
    result = []
    for key, label, field, heading in (
        ('price', 'PRICE', 'price_usd', 'USD'),
        ('cap', 'MARKET CAP', 'mcap_usd', 'USD'),
        ('volume', 'VOLUME', 'volume_24h', 'USD / 24H'),
    ):
        value = as_float(token.get(field))
        scale, unit = (1e9, 'BUSD') if value is not None and value >= 1e9 else (
            (1e6, 'MUSD') if value is not None and value >= 1e6 else
            (1000, 'kUSD') if key != 'price' and value is not None and value >= 1000 else (1, 'USD'))
        face = '--' if value is None else f'{value / scale:.5g}'
        if face.startswith('0.'):
            face = face[1:]
        result.append(HeroRecord(key='token-' + key, title=label,
            heading=unit + (' / 24H' if key == 'volume' else ''), digits=face,
            footer=_change(token.get('change_24h')) + ' · 24h' if key == 'price' else 'SELECTED POOL',
            state='ok' if is_mock else market['state'], read_ts=market['read_ts'],
            accent=(is_mock or market['state'] == 'ok') and value is not None))
    result.append(HeroRecord(key='token-launch', title='LAUNCH', heading='NUMBER',
        digits=metric_label(launch.get('number') if launch else token.get('launch_id')) or '--',
        subtitle=metric_label(launch.get('status') or token.get('status')) or '--', footer='LAUNCH RECORD',
        state=launch_source['state'], read_ts=launch_source['read_ts'], accent=launch_source['state'] == 'ok'))
    result.append(HeroRecord(key='token-contributors', title='CONTRIBUTORS', heading='SEATS',
        digits='--' if seats is None else ('≥' if contribution_source['partial'] else '') + str(seats),
        footer='ACCEPTED', state=contribution_source['state'], read_ts=contribution_source['read_ts'],
        accent=contribution_source['state'] == 'ok' and seats is not None))
    result.append(HeroRecord(key='token-position', title='POSITION', heading='LAUNCH LP',
        stats=(('state', metric_label(token.get('lp_state')) or '--'), ('paired', metric_label(_paired(token)))),
        footer='ORIGINAL POSITION', state='ok' if is_mock else liquidity['state'],
        read_ts=liquidity['read_ts'], accent=False))
    return result


class DetailHero(Grid):
    DEFAULT_CSS = '''
    DetailHero {width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1;}
    '''

    def compose(self):
        for record in records():
            yield LocalSourceHeroCard(record)

    def update_data(self, *, token=None, launch=None, contributors=None, sources=None, is_mock=False):
        for record in records(token, launch, contributors, sources, is_mock):
            self.query_one('#hero-' + record.key, LocalSourceHeroCard).set_record(record)
