"""Scrollable source-bound NFT facts; no wallet eligibility is inferred."""
from urllib.parse import urlsplit
from rich.style import Style
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from maxpane_dashboard.widgets.address import address_text, address_prose, hash_text, job_text, site_text, PROSE_ADDRESS_RE
from maxpane_dashboard.widgets.explorer import IMD, SITES
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import PanelBase
from maxpane_dashboard.widgets.fmt import hhmm
from . import EXPLORER


def source_url(value):
    """Only literal public HTTPS links; no executable/credential-bearing URL."""
    if not isinstance(value,str) or len(value)>4096 or flatten(value)!=value or any(char.isspace() for char in value):
        return None
    try:
        parts=urlsplit(value)
        if (parts.scheme!='https' or not parts.hostname or '.' not in parts.hostname
            or parts.username or parts.password or parts.port not in (None,443)
            or '\\' in value or any(ord(char)<33 for char in value)):
            return None
        return value
    except ValueError:
        return None


def _clock(value):
    return hhmm(value) if type(value) in (int,float) else flatten(value) or '—'


def _facts(value):
    if isinstance(value,(list,tuple)):
        return '; '.join(_facts(item) for item in value)
    if isinstance(value,dict):
        return '; '.join(f'{flatten(key)}: {_facts(item)}' for key,item in value.items())
    return flatten(value) if value is not None else '—'


def source_text(label,url,links,*,explorer=None,action='open_source'):
    """Source links keep address/copy spans separate from the generic URL action."""
    cleaned=source_url(url)
    text=address_prose(flatten(label) or cleaned or '—',explorer=explorer)
    if cleaned:
        index=len(links); links.append(cleaned)
        style=Style(link=cleaned,meta={'@click':f'{action}({index})'})
        if PROSE_ADDRESS_RE.search(text.plain):
            text.append(' [source]',style=style)
        else:
            text.style=style
    return text


def render_detail(row,*,nft_sources=None,nft_coverage=None,extended=False):
    """One formatter for collection basics and the separate cached evidence popup."""
    links=[]
    explorer=EXPLORER(row.get('chain_id'))
    out=Text()
    def line(label,value=None):
        if label:
            out.append(flatten(label)+'  ',style='dim')
        out.append_text(value if isinstance(value,Text) else address_prose(_facts(value),explorer=explorer))
        out.append('\n')
    def section(title):
        out.append(('\n' if out else '')+title+'\n\n',style='bold')
    def link(label,url):
        return source_text(label,url,links,explorer=explorer,action='screen.open_source')
    def evidence(items):
        for item in items if isinstance(items,list) else []:
            if isinstance(item,dict):
                line('↗',link(item.get('label') or item.get('url'),item.get('url')))
                if item.get('detail'):
                    line('',item['detail'])
            elif isinstance(item,str):
                line('',item)
    if not extended:
        line('',row.get('name') or row.get('symbol') or 'Unnamed collection')
        line('Chain',f"{ {1:'Ethereum',4663:'Robinhood'}.get(row.get('chain_id'),'Unknown chain')} · {row.get('standard') or '—'}")
        if row.get('contract'):
            line('Contract',address_text(row['contract'],explorer=explorer))
        if row.get('project_id'):
            line('Project',job_text(row['project_id'],36,explorer=IMD))
        stats=row.get('stats') or {}
        line('Supply',f"minted {_facts(stats.get('totalMinted'))} · live {_facts(stats.get('totalSupply'))} · max {_facts(stats.get('maxSupply'))}")
        burned=stats.get('burnedItems',stats.get('burned'))
        if burned is not None:
            line('Burned',burned)
        for label,key in [('Custody holders','custodyHolders'),('Beneficial holders','beneficialHolders')]:
            if stats.get(key) is not None:
                line(label,stats[key])
        if stats.get('holders') is not None:
            line('Holders',f"{_facts(stats['holders'])} · explorer estimate" if stats.get('holdersSource') else stats['holders'])
        return out,links
    mint=row.get('mint') or {}; benefit=row.get('idmd_benefit') or {}
    section('MINT ROUTES')
    line('Mint state',mint.get('state') or 'unknown')
    routes=mint.get('routes')
    if not isinstance(routes,list) or not routes:
        line('Public price',f"{_facts(mint.get('publicPrice'))} {flatten(mint.get('currency'))}")
    for route in routes or []:
        if not isinstance(route,dict):
            continue
        line(route.get('name') or 'Route',f"{_facts(route.get('price'))} {flatten(route.get('currency'))} · {flatten(route.get('state')) or 'unknown'}")
        for key in ('start','end','conditions','limits','requiredFee','burn'):
            if route.get(key) is not None:
                line(key.title(),route[key])
    for label,key in [('Starts','start'),('Ends','end'),('Limits','limits'),('Conditions','conditions')]:
        if mint.get(key) is not None:
            line(label,mint[key])
    line('IDMD',benefit.get('status') or 'unknown')
    if benefit.get('conditions'):
        line('',benefit['conditions'])
    line('Eligibility','Wallet eligibility not checked')
    if mint.get('reportedTerms'):
        line('Reported terms',mint['reportedTerms'])
    evidence(benefit.get('evidence'))
    section('UTILITY')
    if row.get('utility_summary'):
        line('',row['utility_summary'])
    for item in row.get('utility') or []:
        if isinstance(item,dict):
            line(item.get('title') or item.get('kind'),item.get('status') or 'unknown')
            for key in ('description','conditions'):
                if item.get(key):
                    line('',item[key])
            evidence(item.get('evidence'))
    if not row.get('utility'):
        line('','—')
    section('RELATED TOKENS')
    for token in row.get('related_tokens') or []:
        if not isinstance(token,dict):
            continue
        chain=token.get('chainId'); chain_explorer=EXPLORER(chain)
        line('',address_text(token.get('address'),label=token.get('symbol'),explorer=chain_explorer))
        line('Roles',token.get('roles'))
        onchain=token.get('onchain') or {}
        line('Evidence',f"{flatten(token.get('status')) or 'unknown'} · {flatten(onchain.get('status')) or 'unchecked'}")
        if onchain.get('decimals') is not None:
            line('Decimals',onchain['decimals'])
        if token.get('conditions'):
            line('',address_prose(_facts(token['conditions']),explorer=chain_explorer))
        if onchain.get('readBlock') is not None:
            line('Token read',f"block {onchain['readBlock']} · {_clock(onchain.get('readTimestamp'))}")
        evidence(token.get('evidence'))
    section('SOURCES · SWARM')
    if row.get('stage'):
        line('Stage',row['stage'])
    for job in row.get('jobs') or []:
        if isinstance(job,dict):
            line('Job',job_text(job.get('id'),36,explorer=IMD))
            line('',job.get('title'))
            if job.get('status'):
                line('State',job['status'])
    for site in row.get('sites') or []:
        if isinstance(site,dict):
            line('Site',site_text(site.get('ensName'),46,label=site.get('label'),explorer=SITES,display='host'))
            if site.get('status'):
                line('Publication',site['status'])
            if site.get('cid'):
                line('IPFS',link(site['cid'],site.get('ipfsUrl')))
    for repo in row.get('repositories') or []:
        if isinstance(repo,dict):
            url=source_url(repo.get('url')); commit=flatten(repo.get('commit'))
            line('Repository',link(url,url))
            if commit:
                pinned=f'{url}/tree/{commit}' if url and len(commit)==40 and all(c in '0123456789abcdefABCDEF' for c in commit) else None
                line('Commit',link(commit,pinned))
    section('SOURCES · CHAIN & REVIEW')
    deployment=row.get('deployment') or {}
    tx=deployment.get('transactionHash') or deployment.get('txHash')
    if tx:
        line('Deployment',hash_text(tx,48,explorer=explorer))
    for label,key in [('Factory','factory'),('Implementation','implementation')]:
        value=(deployment.get(key+'Address') or deployment.get(key)
               or (row.get('chain_reads') or {}).get(key+'Address')
               or (row.get('chain_reads') or {}).get(key))
        if value:
            line(label,address_text(value,explorer=explorer))
    line('Read block',row.get('read_block'))
    line('Mint observed',mint.get('asOf'))
    review=row.get('rule_review') or {}
    line('Rule review',review.get('status') or 'unreviewed')
    if row.get('code_hash'):
        line('Runtime hash',hash_text(row['code_hash'],48))
    if review.get('reviewedAt'):
        line('Reviewed',review['reviewedAt'])
    evidence(row.get('evidence'))
    evidence(review.get('evidence'))
    sources=dict(nft_sources or {}); sources.update(row.get('sources') or {})
    for family,source in sources.items():
        if isinstance(source,dict):
            line('Source '+flatten(family),f"observed {_clock(source.get('observed_at'))}")
            if source.get('block_number') is not None:
                line('Block',f"{source['block_number']} · {_clock(source.get('block_timestamp'))}")
    for note in row.get('unknowns') or []:
        line('Coverage',note)
    if (nft_coverage or {}).get('complete') is not True:
        line('Catalogue','Partial observed coverage')
    return out,links


class NftDetail(PanelBase,can_focus=True):
    TITLE='COLLECTION DETAIL'
    BINDINGS=VerticalScroll.BINDINGS
    DEFAULT_CSS='''
    NftDetail {height: auto; overflow-y: auto; scrollbar-gutter: stable; scrollbar-size: 1 1;}
    NftDetail #nft-detail-body {height: auto; padding: 0 1; link-color: $foreground;}
    NftDetail:focus {background: $background;}
    '''

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self._selected=None

    def compose_body(self):
        yield Static(Text('Select a collection'),id='nft-detail-body')

    def update_data(self, *, nft_selected=None,nft_sources=None,nft_coverage=None):
        row=nft_selected if isinstance(nft_selected,dict) else {}
        if self._selected!=row.get('id'):
            self.scroll_home(animate=False)
        self._selected=row.get('id')
        content=render_detail(row)[0] if row else Text('Select a collection')
        self.write('#nft-detail-body',content)
