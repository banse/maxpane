"""Deterministic, reviewed token relationships and NFT utility; no network/LLM.

A deployed status describes a reviewed capability in matching deployed code,
not guaranteed activation, earnings or eligibility. Token identity/metadata is
checked separately by the caller. Native ETH is never represented as ERC-20.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from .hints import infer_utility

_DATA = json.loads(Path(__file__).with_name('nft-utilities.json').read_text())
DEPLOYED = _DATA['deployed']
BUILDS = _DATA['builds']


def _address(value):
    return value.lower() if isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', value) and int(value[2:], 16) else None


def _deployed(chain):
    return next((r for r in DEPLOYED if chain.get('codePresent') is True
                 and r['chainId'] == chain.get('chainId')
                 and r['contract'].lower() == str(chain.get('address', '')).lower()
                 and r['codeHash'].lower() == str(chain.get('codeHash', '')).lower()), None)


def utility_read_specs(chain_evidence):
    """Ordered zero-argument ABI reads; addressFrom resolves a prior NFT getter.

    With namespace, caller stores results in dependencyReads[namespace] with
    address, chainId, readBlock and reads. All reads use the NFT snapshot block.
    """
    rule = _deployed(chain_evidence or {})
    return copy.deepcopy(rule.get('readSpecs', [])) if rule else []


def _build(record, jobs):
    ids = {j.get('id') for j in record.get('jobs', [])}
    for rule in BUILDS:
        job = jobs.get(rule['jobId']) or {}
        if (rule['jobId'] not in ids or rule['chainId'] != record.get('chainId')
                or hashlib.sha256(str(job.get('objective', '')).encode()).hexdigest() != rule['objectiveSha256']):
            continue
        if rule.get('deliveryCommit') and (job.get('delivery') or {}).get('commit') != rule['deliveryCommit']:
            continue
        if rule.get('sourceReference') and rule['sourceReference'] not in job.get('objective', ''):
            continue
        if str(job.get('state', '')).lower() in {'blocked', 'parked', 'failed', 'cancelled', 'canceled', 'rejected'}:
            continue
        return rule
    return None


def _read(chain, rule, path):
    if '.' not in path:
        return (chain.get('reads') or {}).get(path)
    namespace, name = path.split('.', 1)
    dep = (chain.get('dependencyReads') or {}).get(namespace) or {}
    spec = next((s for s in rule.get('readSpecs', []) if s.get('namespace') == namespace and s['name'] == name), {})
    expected = spec.get('address') or (chain.get('reads') or {}).get(spec.get('addressFrom'))
    if (not _address(expected) or _address(dep.get('address')) != _address(expected)
            or dep.get('chainId') != chain.get('chainId') or chain.get('readBlock') is None
            or dep.get('readBlock') != chain.get('readBlock')):
        return None
    return (dep.get('reads') or {}).get(name)


def enrich_utility(record, chain_evidence=None, *, jobs=None):
    """Return a deep copy. ``jobs`` is a mapping of full public job records.

    Never match names or abbreviated listing objectives. Changed bytecode or
    missing build provenance can produce explicitly inferred category hints,
    never verified utility or eligibility. No evidence produces unknown utility. Optional tokens[].onchain is added later by the metadata reader.
    """
    result = copy.deepcopy(record)
    chain = chain_evidence or {}
    if chain.get('proofOnly') is True:
        result.update(tokens=[], utility=[{'kind': 'other', 'title': 'Utility reads pending',
                      'description': 'Deployment identity is checked; utility evidence is pending.',
                      'status': 'unknown', 'conditions': '', 'evidence': []}],
                      utilitySummary='Utility evidence is pending.', utilityReview={'status': 'pending'})
        return result
    is_build = record.get('category') == 'in_the_making'
    rule = _build(record, jobs or {}) if is_build else _deployed(chain)
    if not is_build and rule and (record.get('chainId') != chain.get('chainId')
            or _address(record.get('contractAddress')) != _address(chain.get('address'))):
        rule = None
    if not rule:
        hints = infer_utility(record, chain, jobs=jobs)
        result.update(tokens=[], utility=hints or [{'kind': 'other', 'title': 'Utility not yet verified',
                      'description': 'No matching reviewed implementation or complete build provenance is available.',
                      'status': 'unknown', 'conditions': 'Absence of evidence does not establish absence of utility.', 'evidence': []}],
                      utilitySummary=('Automatic category hints; token relationships and utility remain unverified.'
                                      if hints else 'Token relationships and utility are unverified.'),
                      utilityReview={'status': 'unreviewed', 'hintMethod': 'deterministic-text-and-abi-v1' if hints else None})
        return result
    evidence = copy.deepcopy(rule['evidence'])
    tokens = []
    for item in rule.get('tokens', []):
        token = {k: copy.deepcopy(v) for k, v in item.items() if k != 'addressRead'}
        address = _read(chain, rule, item['addressRead']) if item.get('addressRead') else item.get('address')
        token['address'] = _address(address)
        token.setdefault('chainId', rule['chainId'])
        token.setdefault('name', token.get('symbol') or 'Unidentified token')
        token.setdefault('symbol', None)
        token.setdefault('roles', [])
        token.setdefault('conditions', '')
        token['status'] = ('planned' if is_build else 'configured') if token['address'] else 'unverified-address'
        if not token['address']:
            token['conditions'] = (token['conditions'] + ' Mainnet token address has not been verified.').strip()
        token.setdefault('evidence', copy.deepcopy(evidence))
        tokens.append(token)
    result['tokens'] = tokens
    result['utility'] = copy.deepcopy(rule['utility'])
    for item in result['utility']:
        item.setdefault('conditions', '')
        item.setdefault('evidence', copy.deepcopy(evidence))
        if is_build and item['status'] == 'deployed':
            item['status'] = 'implemented'
    result['utilitySummary'] = rule['summary']
    result['utilityReview'] = {'status': 'reviewed-build' if is_build else 'matched-code',
                              'reviewedAt': _DATA.get('reviewedAt'), 'evidence': evidence,
                              'asOf': chain.get('readTimestamp'), 'readBlock': chain.get('readBlock'),
                              'scope': 'Reviewed capabilities; activation, wallet eligibility and future returns are not guaranteed.'}
    return result
