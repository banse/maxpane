"""Six observed NFT counts in the native nine-line rack cards."""
from textual.containers import Grid

from maxpane_dashboard.widgets.surf.news_hero import HeroRecord, LocalSourceHeroCard, _count


def nft_records(summary):
    summary=summary if isinstance(summary,dict) else {}
    records=[]
    for key,title,heading in (
        ('deployed','COLLECTIONS','DEPLOYED'),('building','IN THE MAKING','PROJECTS'),
        ('mint_open','MINT OPEN','PUBLIC ROUTES'),('idmd_free','IDMD FREE','VERIFIED'),
        ('conditional','CONDITIONAL','IDMD ROUTES'),('chains','CHAINS','OBSERVED')):
        value=summary.get(key)
        records.append(HeroRecord(key='nft-'+key,title=title,heading=heading,
            footer='OBSERVED',digits=_count(value),read_ts=summary.get('observed_at'),
            state='unavailable' if value is None else 'partial' if summary.get('partial') else 'ok',
            accent=value is not None))
    return tuple(records)


class NftHero(Grid):
    DEFAULT_CSS='''
    NftHero {width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1;}
    '''
    def compose(self):
        for record in nft_records(None):
            yield LocalSourceHeroCard(record)

    def update_data(self, *, nft_summary=None):
        for record in nft_records(nft_summary):
            self.query_one('#hero-'+record.key,LocalSourceHeroCard).set_record(record)
