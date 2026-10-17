"""Small, conservative utility hints from directly associated public evidence.

This is keyword/interface classification, not semantic verification. It makes no
network calls, resolves no addresses, and never evaluates wallet eligibility.
Limits bound work on untrusted text; ambiguous clauses are deliberately skipped.
"""
import re

MAX_TEXT = 40_000
MAX_JOBS = 30
MAX_ABI = 500
ORDER = ('staking', 'defi', 'game', 'governance', 'access', 'rewards', 'art', 'identity', 'holder_free_mint')
DEAD = {'failed', 'cancelled', 'canceled', 'rejected', 'parked', 'blocked', 'abandoned', 'expired'}
CONDITIONS = ('Automatic category hint only; deployment, activation and eligibility are not verified. '
              'Source wording or an interface does not establish working behavior or promised returns.')
NFT = re.compile(r'\b(?:nfts?|erc[ -]?721|erc[ -]?1155|collectibles?|collection)\b', re.I)
NEGATIVE = re.compile(r"\b(?:no|not|never|without|cannot|can.t|doesn.t|don.t|isn.t|aren.t|won.t|exclude[ds]?|excluding|except|ineligible|disabled|unsupported|unimplemented|removed)\b", re.I)
BOILERPLATE = re.compile(r'\b(?:out[- ]of[- ]scope|outside (?:the )?scope|non[- ]goals?|examples?|for instance|e\.g\.|mock(?:s|ed)?|test(?:s|ing)?[- ]only|security|vulnerabilit\w*|exploit\w*|attack\w*|audit(?:ing)?|reentrancy|checklist|future ideas|unlike)\b', re.I)
META = {
    'staking': ('Staking-related features', 'Associated evidence suggests a staking mechanism; the staked asset and reward rights need verification.'),
    'defi': ('DeFi-related features', 'Associated evidence suggests a vault, collateral, lending or liquidity mechanism.'),
    'game': ('Game-related utility', 'Associated evidence describes game participation, characters or equipment.'),
    'governance': ('Governance-related utility', 'Associated evidence describes proposals or governance voting.'),
    'access': ('Membership or access', 'Associated evidence describes a pass, membership or gated access.'),
    'rewards': ('Possible funded rewards', 'Associated evidence describes holder rewards or revenue distribution; this is not a yield guarantee.'),
    'art': ('Artwork or collectibles', 'Associated evidence describes collectible artwork or generative images.'),
    'identity': ('Identity or credentials', 'Associated evidence describes identity cards, credentials or wallet attestations.'),
}


def _clauses(text):
    excluded_section = False
    for line in str(text or '')[:MAX_TEXT].splitlines():
        line = line.strip().lstrip('#*>- ').strip()
        if not line:
            excluded_section = False
            continue
        if len(line) < 100 and (line.endswith(':') or line.isupper()):
            excluded_section = bool(BOILERPLATE.search(line) or NEGATIVE.search(line))
            continue
        if excluded_section:
            continue
        # Do not use an earlier sentence's holder requirement for a later free mint.
        for clause in re.split(r'[;\n]|(?<=[.!?])\s+', line):
            clause = clause.strip()
            negation_text = re.sub(r'\b(?:no cost|no (?:fixed )?lock|without (?:a )?lock)\b', 'unrestricted', clause, flags=re.I)
            if not clause or NEGATIVE.search(negation_text) or BOILERPLATE.search(clause):
                continue
            yield clause


def _text_kinds(clause):
    low = clause.lower()
    nft = bool(NFT.search(clause))
    kinds = []
    if (re.search(r'\b(?:stake|staking|staked)\b', low)
            and (nft or re.search(r'\b(?:erc[ -]?20|tokens?)\b', low))):
        kinds.append('staking')
    if (re.search(r'\bdefi\b', low) and (nft or re.search(r'\bprotocol\b', low))) or re.search(r'\b(?:erc[ -]?4626|nft[- ]backed lending|lending protocol|collateral(?:ized|ised)? (?:loans?|positions?)|liquidity positions?|tokenized vault|tokenised vault)\b', low):
        kinds.append('defi')
    if (re.search(r'\b(?:onchain|on-chain|blockchain|mining|strategy|rpg) game\b|\bgame(?:play| characters?| items?| equipment| participation| world)\b', low)
            or (nft and re.search(r'\b(?:game|pets?|battle|characters?)\b', low))):
        kinds.append('game')
    if re.search(r'\bgovernance\b.{0,65}\b(?:vot\w*|proposals?)\b|\b(?:holders?|members?)\b.{0,55}\bvote\b.{0,60}\b(?:proposals?|treasury|dao)\b', low):
        kinds.append('governance')
    if re.search(r'\b(?:membership (?:pass|card)|access pass|token[- ]gated access|gated (?:content|access)|members[- ]only)\b', low):
        kinds.append('access')
    if (re.search(r'\b(?:holders?|nfts?|staking|stakers?)\b.{0,75}\b(?:earn|receive|share|claim|funded|reward)\w*\b.{0,60}\b(?:rewards?|revenue|distributions?|proceeds|fees)\b', low)
            or re.search(r'\bfunded holder distributions\b|\bholder revenue shar\w*\b|\bnft staking rewards\b', low)):
        kinds.append('rewards')
    if re.search(r'\b(?:generative|onchain|on-chain|digital|nft) (?:art|artwork)\b|\b(?:svg artwork|collectible artwork|art nft|nft gallery)\b', low):
        kinds.append('art')
    if re.search(r'\b(?:identity cards?|wallet credentials?|verifiable credentials?|wallet attestations?|soulbound identity|wallet[- ]trait|wallet[- ]fact)\b', low):
        kinds.append('identity')
    # This caller is an NFT record. A free-mint holder gate may omit the NFT
    # noun, but explicit fungible-token minting never becomes an NFT benefit.
    free = re.search(r'\bfree\b.{0,40}\bmint(?:ing)?\b|\bmint(?:ing)?\b.{0,55}\b(?:free|no cost|zero cost)\b', low)
    holders = re.search(r'\bholders?\b|\bholding\b|\bowners? of\b', low)
    fungible_mint = re.search(r'\bmint(?:ing)?\b.{0,50}\b(?:erc[ -]?20|fungible|reward tokens?|tokens?)\b', low)
    ambiguous = (len(re.findall(r'\bholders?\b', low)) > 1
                 or re.search(r'\bfree\s+(?:erc[ -]?20|(?:reward\s+)?tokens?)\b', low)
                 or re.search(r'\b(?:everyone|anyone|all wallets)\b', low))
    if free and holders and not fungible_mint and not ambiguous:
        kinds.append('holder_free_mint')
    return kinds



def _excerpt(clause, kind):
    if len(clause) <= 500:
        return clause
    triggers = {'staking': r'stak', 'defi': r'defi|4626|collateral|lending|liquidity|vault',
                'game': r'game|battle|pets?|characters?', 'governance': r'governance|vote',
                'access': r'membership|access|gated', 'rewards': r'reward|revenue|distribution',
                'art': r'generative|artwork|svg|gallery', 'identity': r'identity|credential|attestation|wallet.trait',
                'holder_free_mint': r'free|mint'}
    match = re.search(triggers[kind], clause, re.I)
    start = max(0, match.start() - 120) if match else 0
    return ('…' if start else '') + clause[start:start + 500] + ('…' if start + 500 < len(clause) else '')


def _source_comments(text):
    """Read prose comments, not imports, variable names or string literals."""
    comments = re.findall(r'(?m)^\s*///?\s?(.*)$|/\*\*?([\s\S]*?)\*/', str(text or '')[:MAX_TEXT])
    return '\n'.join((line or block).replace('@notice', '').replace('@dev', '') for line, block in comments)


def _chain_matches(record, chain):
    return (record.get('chainId') == chain.get('chainId')
            and str(record.get('contractAddress') or '').lower() == str(chain.get('address') or '').lower()
            and bool(chain.get('address')))


def _abi_hints(chain):
    abi = chain.get('abi')
    if not isinstance(abi, list):
        return []
    signatures, mutable = {}, set()
    for item in abi[:MAX_ABI]:
        if not isinstance(item, dict) or item.get('type') != 'function':
            continue
        name, inputs = item.get('name'), item.get('inputs', [])
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_]\w*', name) or not isinstance(inputs, list):
            continue
        types = [i.get('type') for i in inputs if isinstance(i, dict)]
        if len(types) != len(inputs) or any(not isinstance(t, str) or len(t) > 80 for t in types):
            continue
        signature = name + '(' + ','.join(types) + ')'
        signatures[signature] = item
        if item.get('stateMutability') in (None, 'nonpayable', 'payable'):
            mutable.add(name)
    result = []
    for a, b in (('stake', 'unstake'), ('stakeNFT', 'unstakeNFT'), ('stakeNfts', 'unstakeNfts'), ('stakeTokens', 'unstakeTokens')):
        if {a, b} <= mutable:
            result.append(('staking', sorted(s for s in signatures if s.split('(', 1)[0] in (a, b))))
            break
    vault = {'asset()', 'totalAssets()', 'convertToShares(uint256)', 'convertToAssets(uint256)',
             'deposit(uint256,address)', 'mint(uint256,address)', 'withdraw(uint256,address,address)', 'redeem(uint256,address,address)'}
    if vault <= signatures.keys():
        result.append(('defi', sorted(vault)))
    return result


def infer_utility(record, chain_evidence=None, *, jobs=None):
    """Return ordered inferred utility entries, or [] if evidence is insufficient.

    Full associated job objectives and collection source comments take priority
    over the record description. Failed/abandoned jobs, existing utility labels,
    mint claims and reportedTerms are never input to this classifier.
    """
    chain, jobs = chain_evidence or {}, jobs or {}
    found = {}

    def add(kind, evidence, clause=''):
        if kind not in found:
            if kind == 'holder_free_mint':
                group = ('IDMD NFT holders' if re.search(r'\b(?:idmd|identity\s*\.?\s*md)(?:\s+nfts?)?\s+holders?\b|\bholders?\s+of\s+(?:the\s+)?(?:idmd|identity\s*\.?\s*md)\b', clause, re.I)
                         else 'IMD token holders' if re.search(r'\bimd(?:\s+token)?\s+holders?\b|\bholders?\s+of\s+(?:the\s+)?imd\b', clause, re.I) else 'eligible holders')
                title = group + ': possible free NFT mint'
                description = 'Associated wording mentions a free NFT mint for ' + group + '; mint eligibility remains unverified.'
            else:
                title, description = META[kind]
            found[kind] = {'kind': kind, 'title': title, 'description': description, 'status': 'inferred',
                           'conditions': CONDITIONS, 'evidence': []}
        if evidence not in found[kind]['evidence'] and len(found[kind]['evidence']) < 3:
            found[kind]['evidence'].append(evidence)

    texts = []
    if _chain_matches(record, chain):
        source = chain.get('pinnedSource') or {}
        url = source.get('url') or chain.get('sourceUrl')
        for kind, signatures in _abi_hints(chain):
            add(kind, {'label': 'Collection ABI pattern', 'method': 'abi-pattern',
                       'url': chain.get('sourceUrl') or url, 'signatures': signatures,
                       'snippet': '; '.join(signatures)})
        text = _source_comments(source.get('text') or chain.get('sourceText'))
        if text.strip():
            texts.append((text, 'Collection source comment', url, 'source-text'))
    ids = sorted({str(j.get('id')) for j in record.get('jobs', []) if isinstance(j, dict) and j.get('id')})[:MAX_JOBS]
    linked_full = False
    for job_id in ids:
        job = jobs.get(job_id) or {}
        objective = job.get('objective')
        if not isinstance(objective, str) or not objective.strip() or job.get('id') != job_id:
            continue
        linked_full = True  # Do not revive an abandoned prompt via the listing description.
        if str(job.get('state', '')).lower() in DEAD:
            continue
        if objective.rstrip().endswith(('…', '...')):
            continue
        texts.append((objective, 'Associated full job objective', 'https://api.imd.fun/jobs/' + job_id, 'job-text'))
    if not texts and not linked_full and record.get('description'):
        texts.append((record['description'], 'Collection description (fallback)', None, 'description-text'))
    for text, label, url, method in texts:
        for clause in _clauses(text):
            for kind in _text_kinds(clause):
                add(kind, {'label': label, 'method': method, 'url': url, 'snippet': _excerpt(clause, kind)}, clause)
    return [found[kind] for kind in ORDER if kind in found]
