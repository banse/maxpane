"""Pure NFT identity normalization and local catalog projection.

Normalization validates identity/shape, not chain proof: source readers remain
responsible for proving deployment and code-bound interpretations. Nested mint,
utility, price and stats facts are copied, never guessed or recomputed here.
"""
from copy import deepcopy
from datetime import datetime
from math import isfinite
import re


FILTER_DEFAULTS = {'chain': 'all', 'stage': 'launched', 'mint': 'all',
                   'idmd': 'all', 'utility': 'all', 'search': '', 'sort': 'newest'}
FILTER_VALUES = {
    'chain': ('all', 'ethereum', 'robinhood'),
    'stage': ('launched', 'building'),
    'mint': ('all', 'open', 'route-open', 'closed', 'not-started', 'sold-out',
             'ended', 'paused', 'unconfigured', 'auction / delivery', 'conditional',
             'awaiting-season-end', 'awaiting-finalization', 'blank-season', 'auction-open', 'unknown'),
    'idmd': ('all', 'yes', 'conditional', 'no', 'unknown'),
    'sort': ('newest', 'name'),
}
_ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}')
_PROJECT = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')


def collection_identity(chain_id, contract):
    """Return exact supported-chain identity, with no name/chain fallback."""
    if type(chain_id) is not int or chain_id not in (1, 4663):
        return None
    if not isinstance(contract, str) or not _ADDRESS.fullmatch(contract) or int(contract[2:],16)==0:
        return None
    return f'{chain_id}:{contract.lower()}'


def build_identity(chain_id, project_id):
    if type(chain_id) is not int or chain_id not in (1, 4663):
        return None
    if not isinstance(project_id,str) or not _PROJECT.fullmatch(project_id):
        return None
    return f'build:{chain_id}:{project_id.lower()}'


def normalize_record(raw, *, sources=None):
    """Translate scanner top-level names; preserve nested evidence verbatim.

    Accept an already normalized record too. Contradictory identities are
    rejected rather than merged. Sources, when supplied, are original source
    envelopes; this function has no clock and never manufactures one.
    """
    if not isinstance(raw,dict):
        return None
    def value(key, old=None):
        return raw[key] if key in raw else raw.get(old or key)
    for new, old in (('chain_id','chainId'), ('contract','contractAddress'),
                     ('project_id','projectId')):
        if new in raw and old in raw and raw[new] != raw[old]:
            return None
    chain, contract = value('chain_id','chainId'), value('contract','contractAddress')
    category = raw.get('category')
    project = value('project_id','projectId')
    if category == 'launched':
        identity = collection_identity(chain,contract)
    elif category == 'in_the_making':
        if contract is not None:
            return None
        if project is None and isinstance(raw.get('id'),str):
            pieces=raw['id'].split(':',2)
            project=pieces[2] if len(pieces)==3 and pieces[0]=='build' else None
        identity=build_identity(chain,project)
    else:
        return None
    if identity is None or raw.get('id') is not None and str(raw['id']).lower()!=identity:
        return None
    def mapping(key,old=None):
        item=value(key,old)
        return deepcopy(item) if isinstance(item,dict) else {}
    def sequence(key,old=None):
        item=value(key,old)
        return deepcopy(item) if isinstance(item,list) else []
    def text(key,old=None):
        item=value(key,old)
        return item if isinstance(item,str) else None
    activity=mapping('activity')
    benefit=mapping('idmd_benefit','idmdBenefit')
    if benefit.get('status') not in ('yes','conditional','no','unknown'):
        benefit['status']='unknown'
    mint=mapping('mint')
    if not isinstance(mint.get('state'),str):
        mint['state']='unknown'
    return dict(
        id=identity, category=category, chain_id=chain,
        contract=contract.lower() if category=='launched' else None,
        project_id=project.lower() if isinstance(project,str) else None,
        name=text('name'), symbol=text('symbol'), description=text('description'),
        standard=text('standard'), deployment=mapping('deployment'),
        jobs=sequence('jobs'), sites=sequence('sites'), repositories=sequence('repositories'),
        launch_ids=sequence('launch_ids','launchIds'), launch_number=value('launch_number','launchNumber'),
        idmd_benefit=benefit, mint=mint, stats=mapping('stats'), chain_reads=mapping('chain_reads','chainReads'),
        read_block=value('read_block','readBlock'), activity=activity, evidence=sequence('evidence'),
        unknowns=sequence('unknowns'), code_hash=text('code_hash','codeHash'),
        rule_review=mapping('rule_review','ruleReview'), related_tokens=sequence('related_tokens','tokens'),
        utility=sequence('utility'), utility_summary=text('utility_summary','utilitySummary'),
        utility_review=mapping('utility_review','utilityReview'),
        stage=text('stage') or activity.get('stage'),
        last_meaningful_at=value('last_meaningful_at') or activity.get('lastMeaningfulAt'),
        sources=deepcopy(sources) if isinstance(sources,dict) else mapping('sources'),
    )


def _filters(filters):
    result=dict(FILTER_DEFAULTS)
    if filters is not None:
        if not isinstance(filters,dict) or set(filters)-set(result):
            raise ValueError('unknown NFT filter')
        result.update(filters)
    if any(result[key] not in choices for key,choices in FILTER_VALUES.items()):
        raise ValueError('invalid NFT filter value')
    if not isinstance(result['search'],str) or not isinstance(result['utility'],str) or not result['utility']:
        raise ValueError('invalid NFT search or utility')
    return result


def _mint_state(row):
    value=row.get('mint',{}).get('state')
    return value.casefold() if isinstance(value,str) and value.casefold() not in ('unverified','') else 'unknown'


def _stamp(value):
    if type(value) in (int,float):
        return value if isfinite(value) and value>0 else None
    if not isinstance(value,str):
        return None
    try:
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp.timestamp() if stamp.tzinfo is not None else None
    except (ValueError,OverflowError,OSError):
        return None


def select_rows(rows, *, filters=None):
    """Apply common filters; stage selects a table only in project_snapshot."""
    choice=_filters(filters)
    if rows is None:
        return None
    selected=[]
    needle=choice['search'].strip().casefold()
    for raw in rows:
        row=normalize_record(raw)
        if row is None:
            continue
        if choice['chain']!='all' and row['chain_id']!={'ethereum':1,'robinhood':4663}[choice['chain']]:
            continue
        if choice['idmd']!='all' and row['idmd_benefit']['status']!=choice['idmd']:
            continue
        if choice['mint']=='route-open':
            routes=row['mint'].get('routes')
            if not isinstance(routes,list) or not any(isinstance(route,dict) and route.get('state')=='open' for route in routes):
                continue
        elif choice['mint']!='all' and _mint_state(row)!=choice['mint']:
            continue
        if choice['utility']!='all' and not any(isinstance(item,dict) and item.get('kind')==choice['utility'] for item in row['utility']):
            continue
        terms=[row.get(key) for key in ('id','name','symbol','contract','project_id')]
        terms += [job.get('id') for job in row['jobs'] if isinstance(job,dict)]
        if needle and not any(needle in term.casefold() for term in terms if isinstance(term,str)):
            continue
        selected.append(row)
    if choice['sort']=='name':
        selected.sort(key=lambda row: ((row['name'] or '').casefold(),row['id']))
    else:
        def newest(row):
            stamp=_stamp(row['deployment'].get('timestamp') if row['category']=='launched' else row['last_meaningful_at'])
            return stamp is None, -(stamp or 0), row['id']
        selected.sort(key=newest)
    return selected


def project_snapshot(snapshot, *, filters=None, selected_id=None):
    """Filter cached facts without I/O, time renewal or wallet conclusions."""
    choice=_filters(filters)
    rows=select_rows(snapshot.get('nft_rows'),filters=choice)
    builds=select_rows(snapshot.get('nft_build_rows'),filters=choice)
    mint_known=None if rows is None else sum(_mint_state(row)!='unknown' for row in rows)
    idmd_known=None if rows is None else sum(row['idmd_benefit']['status']!='unknown' for row in rows)
    coverage=snapshot.get('nft_coverage') or {}
    known_summary=snapshot.get('nft_summary') or {}
    def count(predicate,known):
        return None if rows is None or rows and not known else sum(predicate(row) for row in rows)
    summary=dict(
        deployed=None if rows is None else len(rows),
        building=None if builds is None else len(builds),
        mint_open=count(lambda row:_mint_state(row)=='open',mint_known),
        idmd_free=count(lambda row:row['idmd_benefit']['status']=='yes',idmd_known),
        conditional=count(lambda row:row['idmd_benefit']['status']=='conditional',idmd_known),
        chains=None if rows is None or builds is None else len({row['chain_id'] for row in rows+builds}),
        mint_known=mint_known, idmd_known=idmd_known,
        partial=(coverage.get('complete') is not True or rows is None or builds is None
                 or mint_known!=len(rows or []) or idmd_known!=len(rows or [])),
        observed_at=known_summary.get('observed_at'),
    )
    visible=rows if choice['stage']=='launched' else builds
    selected=next((row for row in visible or [] if row['id']==selected_id),None)
    if selected is None and visible:
        selected=visible[0]
    readme=snapshot.get('nft_readme')
    if not isinstance(readme,dict) or selected is None or readme.get('identity')!=selected['id']:
        readme=None
    return dict(nft_rows=rows,nft_build_rows=builds,nft_summary=summary,
                nft_selected=deepcopy(selected),nft_readme=deepcopy(readme),
                nft_sources=deepcopy(snapshot.get('nft_sources') or {}),
                nft_coverage=deepcopy(coverage),as_of=snapshot.get('as_of'))
