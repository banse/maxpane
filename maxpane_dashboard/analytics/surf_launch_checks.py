"""Pure, bounded evidence for swarm provenance; a verdict never judges safety.

The caller injects Ethereum's Keccak implementation, keeping this module usable
by widgets without importing the data layer. Raw RPC bodies are never returned.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')
HASH = re.compile(r'(?:0x)?[0-9a-fA-F]{64}\Z')
ZERO = '0x' + '0' * 40
PAIRS = {
    (1, '0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7'): 'IMD',
    (1, '0xa0df17b5ac76ababa36e1450e2cbcd18a620c845'): 'FWA',
    (4663, '0x5f7bb59365ce557c26dbcaa4ee9d39a4b95b7127'): 'IMD',
    (8453, '0xff0c532fdb8cd566ae169c1cb157ff2bdc83e105'): 'FRENPET',
}

def address(value):
    return value.lower() if isinstance(value, str) and ADDRESS.fullmatch(value) else None

def text(value, cap=256):
    return value[:cap] if isinstance(value, str) else None

def integer(value):
    return value if type(value) is int and value >= 0 else None

def mappings(value):
    return [x for x in value if isinstance(x, Mapping)] if isinstance(value, list) else []

def is_production(row):
    return isinstance(row, Mapping) and type(row.get('chainId')) is int and row['chainId'] in (1, 8453, 4663) and row.get('status') != 'abandoned'

def extract_facts(detail):
    def obj(value):
        return value if isinstance(value, Mapping) else {}
    attestation = obj(detail.get('attestation'))
    manifest = obj(attestation.get('manifest'))
    token, pool = obj(manifest.get('token')), obj(manifest.get('pool'))
    currency = address(pool.get('pairedCurrency'))
    pair = 'ETH' if currency == ZERO else PAIRS.get((detail.get('chainId'), currency))
    if pair is None and currency:
        pair = currency  # The popup's address helper owns shortening, copy and explorer links.
    return {
        'ticker': text(token.get('symbol')), 'token_name': text(token.get('name')),
        'pair': pair, 'pool_fee': integer(pool.get('fee')),
        'requester': address(detail.get('requester')), 'policy_version': integer(detail.get('policyVersion')),
        'admission': [[text(x.get('name')), text(x.get('status'))] for x in mappings(detail.get('admissionChecks'))][:64] if isinstance(detail.get('admissionChecks'), list) else None,
        'deploy_failure': detail.get('deployFailure') is not None,
        'assurances_count': len(detail['assurances']) if isinstance(detail.get('assurances'), list) else None,
        'job_ids': [x['id'] for x in mappings(detail.get('jobs')) if isinstance(x.get('id'), str)][:64],
        'attested': [{k: (integer(x.get(k)) if k == 'creationCodeBytes' else text(x.get(k))) for k in ('name', 'deployedCodeHash', 'creationCodeHash', 'creationCodeBytes')} for x in mappings(attestation.get('contracts'))][:64],
    }

def policy_sets(policies, chain_id, version, kind=None):
    """Wallets are chain-wide through version; factories belong to this kind."""
    wallets, factories, known = set(), set(), False
    for policy in mappings(policies):
        params = policy.get('params')
        if not isinstance(params, Mapping) or params.get('chainId') != chain_id:
            continue
        pv = integer(policy.get('version'))
        same_kind = kind is None or policy.get('kind') == kind
        known |= same_kind and version is not None and pv == version
        factory = address(params.get('factory'))
        if same_kind and factory and factory != ZERO:
            factories.add(factory)
        if pv is None or version is None or pv > version:
            continue
        owners = params.get('owners')
        values = [params.get('owner')] + (list(owners.values()) if isinstance(owners, Mapping) else [])
        wallets.update(a for v in values if (a := address(v)) and a != ZERO)
    return wallets, factories, known

def result(state='unknown', **evidence):
    return {'state': state, 'evidence': evidence}

def _hex(value):
    if not isinstance(value, str) or not value.startswith('0x'):
        return None
    try:
        return bytes.fromhex(value[2:])
    except ValueError:
        return None

def _hash(value):
    return value.lower().removeprefix('0x') if isinstance(value, str) and HASH.fullmatch(value) else None

def creation_candidates(tx_input, size):
    """ABI bytes values start on a word boundary after a plausible length word."""
    payload = _hex(tx_input)
    if payload is None or type(size) is not int or not 0 < size <= len(payload):
        return []
    return [i for i in range(36, len(payload) - size + 1, 32)
            if size <= int.from_bytes(payload[i-32:i], 'big') <= len(payload) - i]


def creation_match(tx_input, size, expected, keccak):
    """Hash only ABI bytes candidates, never every word of a large transaction."""
    payload, wanted = _hex(tx_input), _hash(expected)
    if wanted is None:
        return None
    for i in creation_candidates(tx_input, size):
        if keccak(payload[i:i + size]).hex() == wanted:
            return i
    return None

def check_launch(row, facts, policies, rpc, *, keccak, previous=None):
    """Recompute unknown checks only. Caller resets checks when list version moves."""
    checks = {key: result() for key in ('K1', 'K2', 'K3', 'K4', 'K6', 'K7')}
    checks['K1'] = result('pass' if is_production(row) else 'unknown', chain_id=row.get('chainId'))
    artifacts = mappings(row.get('artifacts'))
    txs, receipts, codes = (rpc.get(key, {}) for key in ('transactions', 'receipts', 'codes'))
    wallets, factories, known = policy_sets(policies, row.get('chainId'), facts.get('policy_version'), row.get('kind'))
    hashes = list(dict.fromkeys(a.get('txHash') for a in artifacts if isinstance(a.get('txHash'), str)))
    if not previous or previous.get('K2', {}).get('state', 'unknown') == 'unknown':
        tx_evidence, states = [], []
        for tx_hash in hashes:
            tx, receipt = txs.get(tx_hash), receipts.get(tx_hash)
            sender = address(tx.get('from')) if isinstance(tx, Mapping) else None
            to = address(tx.get('to')) if isinstance(tx, Mapping) else None
            status = None
            try:
                value = receipt.get('status') if isinstance(receipt, Mapping) else None
                status = int(value, 16) if isinstance(value, str) else None
            except ValueError:
                pass
            state = 'unknown'
            if known and wallets and sender and status is not None:
                state = 'pass' if sender in wallets and (not factories or to in factories) and status == 1 else 'fail'
            states.append(state)
            tx_evidence.append({'tx_hash': tx_hash, 'from': sender, 'to': to, 'receipt_status': status})
        checks['K2'] = result('fail' if 'fail' in states else 'pass' if states and all(s == 'pass' for s in states) and len(hashes) == len({a.get('txHash') for a in artifacts}) else 'unknown', transactions=tx_evidence, policy_version=facts.get('policy_version'), rule_version=2)
    if not previous or previous.get('K3', {}).get('state', 'unknown') == 'unknown':
        states, contract_evidence = [], []
        old_contracts = {c.get('name'): c for c in (previous or {}).get('K3', {}).get('evidence', {}).get('contracts', [])}
        for contract in facts.get('attested', []):
            matches = [a for a in artifacts if a.get('name') == contract.get('name')]
            old = old_contracts.get(contract.get('name'), {})
            if old.get('state') in ('pass', 'pass_immutables', 'fail', 'na'):
                states.append(old['state'])
                contract_evidence.append(dict(old))
                continue
            if not matches:
                states.append('na')
                contract_evidence.append({'name': contract.get('name'), 'state': 'na', 'reason': 'not deployed by this launch'})
                continue
            artifact = matches[0] if len(matches) == 1 else {}
            addr, tx_hash = address(artifact.get('address')), artifact.get('txHash')
            code = _hex(codes.get(addr))
            expected = _hash(contract.get('deployedCodeHash'))
            actual = keccak(code).hex() if code else None
            state, offset = 'unknown', None
            tx = txs.get(tx_hash)
            if actual and expected:
                if actual == expected:
                    state = 'pass'
                elif isinstance(tx, Mapping) and _hex(tx.get('input')) and _hash(contract.get('creationCodeHash')) and integer(contract.get('creationCodeBytes')):
                    offset = creation_match(tx['input'], contract['creationCodeBytes'], contract['creationCodeHash'], keccak)
                    state = 'pass_immutables' if offset is not None else 'fail'
            states.append(state)
            contract_evidence.append({'state': state, 'name': contract.get('name'), 'address': addr, 'tx_hash': tx_hash, 'expected_hash': expected, 'actual_hash': actual, 'creation_hash': _hash(contract.get('creationCodeHash')), 'creation_offset': offset})
        matched_names = {c['name'] for c in contract_evidence if c.get('state') in ('pass', 'pass_immutables')}
        unmatched = [a.get('name') for a in artifacts if a.get('role') in ('token', 'hook') and a.get('name') not in matched_names]
        incomplete = not matched_names or 'unknown' in states or bool(unmatched)
        checks['K3'] = result('fail' if 'fail' in states else 'unknown' if incomplete else 'pass_immutables' if 'pass_immutables' in states else 'pass', contracts=contract_evidence, unmatched_artifacts=unmatched, rule_version=2)
    admission = facts.get('admission')
    failed = [x[0] for x in admission if x[1] != 'passed'] if isinstance(admission, list) else []
    state = 'fail' if failed else 'pass' if admission is not None else 'unknown'
    if facts.get('deploy_failure') and row.get('status') != 'live':
        state = 'fail' if row.get('status') == 'parked' or failed else 'unknown'
    checks['K4'] = result(state, failed_admission=failed, deploy_failure=facts.get('deploy_failure'))
    if not previous or previous.get('K6', {}).get('state', 'unknown') == 'unknown':
        checks['K6'] = result('na' if row.get('kind') == 'evm_contracts' else 'unknown')
        topic = '0x' + keccak(b'ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)').hex()
        if row.get('kind') != 'evm_contracts':
            for receipt in (receipts.get(tx_hash) for tx_hash in hashes):
                for log in mappings(receipt.get('logs') if isinstance(receipt, Mapping) else None):
                    topics = log.get('topics')
                    if isinstance(topics, list) and len(topics) >= 3 and topics[0] == topic and _hash(topics[2]):
                        owner = address('0x' + topics[2][-40:])
                        checks['K6'] = result('info', owner=owner, emitter=address(log.get('address')), owner_is_factory=(owner in policy_sets(policies, row.get('chainId'), facts.get('policy_version'))[1] if known else None))
                        break
    checks['K7'] = result('info', assurances_count=facts.get('assurances_count'))
    if previous:
        for key, value in previous.items():
            if key in checks and value.get('state') != 'unknown':
                checks[key] = value
    return checks

def verdict(row, checks):
    passed = sum(checks.get(k, {}).get('state') in ('pass', 'pass_immutables') for k in ('K1', 'K2', 'K3', 'K4'))
    failed = next((k for k in ('K2', 'K3', 'K4') if checks.get(k, {}).get('state') == 'fail'), None)
    state = ('not_deployed' if row.get('status') == 'admitted' and not row.get('artifacts')
             else 'mismatch' if failed in ('K2', 'K3') else 'failed' if failed
             else 'parked' if row.get('status') == 'parked'
             else 'swarm' if passed == 4 else 'partial')
    return {'state': state, 'passed': passed, 'failed': failed}


def evidence_calls(tx_hashes, addresses):
    """Bounded read-only batch plan and parallel keys for its answers."""
    keys, calls = [], []
    for tx in list(dict.fromkeys(tx_hashes))[:64]:
        if _hash(tx) is None: continue
        for bucket, method in (('transactions', 'eth_getTransactionByHash'), ('receipts', 'eth_getTransactionReceipt')):
            keys.append((bucket, tx)); calls.append((method, [tx]))
    for addr in list(dict.fromkeys(addresses))[:64]:
        if address(addr) is None: continue
        keys.append(('codes', address(addr))); calls.append(('eth_getCode', [address(addr), 'latest']))
    return keys, calls


def evidence_results(keys, results):
    if results is None:
        return None
    out = {'transactions': {}, 'receipts': {}, 'codes': {}}
    for (bucket, key), value in zip(keys, results or []):
        if value is not None:
            out[bucket][key] = value
    return out
