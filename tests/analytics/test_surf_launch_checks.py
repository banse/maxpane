"""Production launch evidence, exclusively from the committed v8 capture."""
import copy
import json
from pathlib import Path
import pytest
from maxpane_dashboard.analytics import surf_launch_checks as lc
from maxpane_dashboard.data.keccak import keccak256

FIX = Path(__file__).parents[1] / 'fixtures/surf/swarm/v8'
def fixture(name):
    return json.loads((FIX / f'{name}.json').read_text())
def evidence(number):
    row = fixture(f'launch_{number}')
    tx = fixture(f'rpc_{number}_tx')['result']
    receipt = fixture(f'rpc_{number}_receipt')['result']
    code = fixture(f'rpc_{number}_code_{"other" if number == 734 else "token"}')['result']
    artifact = next(a for a in row['artifacts'] if a['role'] == ('other' if number == 734 else 'token'))
    return row, {'transactions': {tx['hash']: tx}, 'receipts': {tx['hash']: receipt}, 'codes': {artifact['address']: code}}
def checked(number=737, **kwargs):
    row, rpc = evidence(number)
    facts = lc.extract_facts(row)
    return row, facts, lc.check_launch(row, facts, fixture('launch_policies')['policies'], rpc, keccak=keccak256, **kwargs)

@pytest.mark.parametrize('number', [734, 737, 747])
def test_v8_attestation_checks(number):
    row, facts, checks = checked(number)
    assert lc.verdict(row, checks) == {'state': 'swarm', 'passed': 4, 'failed': None}
    assert checks['K3']['state'] == ('pass_immutables' if number == 747 else 'pass')
    assert checks['K3']['evidence']['unmatched_artifacts'] == []
    if number == 734:
        assert facts['ticker'] is None
        assert checks['K3']['evidence']['contracts'][0]['name'] == 'Counter'
        assert checks['K6']['state'] == 'na'
    if number == 747:
        assert checks['K3']['evidence']['contracts'][0]['creation_offset'] == 740

def test_v8_pool_fee_is_manifest_fee():
    _, facts, _ = checked()
    assert facts['pool_fee'] == 3000
    assert facts['pair'] == 'IMD'
    assert not {'rewardSnapshot', 'allocations', 'claims'} & facts.keys()

def test_wrong_sender_and_unavailable_are_different():
    row, rpc = evidence(737)
    facts = lc.extract_facts(row)
    tx = next(iter(rpc['transactions'].values()))
    tx['from'] = '0x' + '1' * 40
    checks = lc.check_launch(row, facts, fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K2']['state'] == 'fail'
    assert lc.verdict(row, checks)['failed'] == 'K2'
    checks = lc.check_launch(row, facts, [], {}, keccak=keccak256)
    assert checks['K2']['state'] == checks['K3']['state'] == 'unknown'
    assert lc.verdict(row, checks)['state'] == 'partial'

def test_code_mismatch_without_creation_match_fails():
    row, rpc = evidence(737)
    facts = lc.extract_facts(row)
    facts['attested'][0]['deployedCodeHash'] = '1' * 64
    facts['attested'][0]['creationCodeHash'] = '2' * 64
    checks = lc.check_launch(row, facts, fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K3']['state'] == 'fail'

def test_production_excludes_abandoned_and_sepolia():
    rows = fixture('launches_500')['launches']
    assert len([r for r in rows if lc.is_production(r)]) == 9

def test_policy_wallets_use_version_but_factories_do_not():
    policies = fixture('launch_policies')['policies']
    wallets, factories, known = lc.policy_sets(policies, 1, 26)
    assert known and '0xff03410d0fe5fa8f7f59f743de35e333d9857120' in factories
    later = copy.deepcopy(policies[0]); later['version'] = 99; later['params']['owner'] = '0x' + '1' * 40
    assert '0x' + '1' * 40 not in lc.policy_sets(policies + [later], 1, 26)[0]
    assert not lc.policy_sets(policies, 1, 99)[2]

def test_admission_and_failed_deploy_states():
    row, facts, checks = checked()
    facts['deploy_failure'] = True
    row['status'] = 'admitted'
    assert lc.check_launch(row, facts, [], {}, keccak=keccak256)['K4']['state'] == 'unknown'
    row['status'] = 'parked'
    assert lc.check_launch(row, facts, [], {}, keccak=keccak256)['K4']['state'] == 'fail'

def test_liquidity_evidence_belongs_to_its_own_launch():
    row, rpc = evidence(737)
    _, other = evidence(747)
    other_receipt = next(iter(other['receipts'].values()))
    topic = '0x' + keccak256(b'ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)').hex()
    for log in other_receipt['logs']:
        if log['topics'][0] == topic:
            log['topics'][2] = '0x' + '0' * 24 + '1' * 40
    rpc['receipts'].update(other['receipts'])
    checks = lc.check_launch(row, lc.extract_facts(row), fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K6']['evidence']['owner'] != '0x' + '1' * 40

def test_completed_code_check_is_not_hashed_again():
    row, facts, previous = checked(747)
    def forbidden(_):
        raise AssertionError('completed check repeated hashing')
    checks = lc.check_launch(row, facts, [], {}, keccak=forbidden, previous=previous)
    assert checks == previous

def test_creation_candidates_are_abi_length_guarded():
    row, rpc = evidence(747)
    contract = lc.extract_facts(row)['attested'][0]
    payload = next(iter(rpc['transactions'].values()))['input']
    assert lc.creation_candidates(payload, contract['creationCodeBytes']) == [164, 196, 228, 740]


def test_missing_artifact_is_na_and_passed_contract_never_rehashed():
    row, rpc = evidence(747)
    # #763-shaped: one matched deployment and an unattached V2TwapSwap attestation.
    row['launchNumber'] = 763
    row['artifacts'] = [a for a in row['artifacts'] if a['role'] != 'hook']
    facts = lc.extract_facts(row)
    absent = copy.deepcopy(facts['attested'][0]); absent['name'] = 'V2TwapSwap'
    facts['attested'].append(absent)
    checks = lc.check_launch(row, facts, fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert lc.verdict(row, checks)['state'] == 'swarm'
    assert checks['K3']['evidence']['contracts'][1]['state'] == 'na'
    assert checks['K3']['evidence']['contracts'][1]['reason'] == 'not deployed by this launch'
    # A second deployed contract is temporarily unavailable. The first stays passed.
    pending = copy.deepcopy(row['artifacts'][0]); pending['name'] = 'UnionCard'; pending['address'] = '0x'+'1'*40
    row['artifacts'].append(pending)
    facts['attested'].append({**absent, 'name': 'UnionCard'})
    checks['K3']['state'] = 'unknown'
    calls = []
    def counted(value):
        calls.append(value)
        return keccak256(value)
    retried = lc.check_launch(row, facts, fixture('launch_policies')['policies'], rpc, keccak=counted, previous=checks)
    assert retried['K3']['state'] == 'unknown'
    assert calls == []
    rpc['codes'][pending['address']] = next(iter(rpc['codes'].values()))
    completed = lc.check_launch(row, facts, fixture('launch_policies')['policies'], rpc, keccak=counted, previous=retried)
    assert completed['K3']['state'] == 'pass_immutables'
    assert len(calls) == 5  # one runtime hash plus four ABI candidates, only for UnionCard


@pytest.mark.parametrize('foreign,chain,expected', [(True,1,'fail'),(False,8453,'pass')])
def test_direct_creation_judges_sender_and_factory(foreign, chain, expected):
    row, rpc = evidence(737); row['chainId'] = chain
    tx = next(iter(rpc['transactions'].values())); tx['to'] = None
    policies = fixture('launch_policies')['policies']
    if chain == 8453:
        policy = copy.deepcopy(next(p for p in policies if p['version'] == row['policyVersion'] and p['params']['chainId'] == 1))
        policy['params']['chainId'] = chain; policy['params']['factory'] = None
        policies = [policy]
    if foreign: tx['from'] = '0x'+'1'*40
    checks = lc.check_launch(row, lc.extract_facts(row), policies, rpc, keccak=keccak256)
    assert checks['K2']['state'] == expected


def test_k2_every_artifact_sender_and_receipt_must_pass():
    row, rpc = evidence(737)
    tx = copy.deepcopy(next(iter(rpc['transactions'].values()))); tx['hash'] = '0x'+'1'*64; tx['from'] = '0x'+'1'*40
    row['artifacts'].append({**row['artifacts'][0], 'name': 'second', 'txHash': tx['hash']})
    rpc['transactions'][tx['hash']] = tx
    rpc['receipts'][tx['hash']] = copy.deepcopy(next(iter(rpc['receipts'].values())))
    checks = lc.check_launch(row, lc.extract_facts(row), fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K2']['state'] == 'fail'
    tx['from'] = next(iter(rpc['transactions'].values()))['from']
    rpc['receipts'][tx['hash']]['status'] = '0x0'
    checks = lc.check_launch(row, lc.extract_facts(row), fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K2']['state'] == 'fail'
    rpc['receipts'][tx['hash']]['status'] = '0x1'
    rpc['transactions'].pop(tx['hash'])
    checks = lc.check_launch(row, lc.extract_facts(row), fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K2']['state'] == 'unknown'


@pytest.mark.parametrize('field', ['owner', 'factory'])
def test_zero_policy_address_never_becomes_authority(field):
    row, rpc = evidence(737)
    # A factory authority exists only for evm_contracts.
    if field == 'factory': row.update(kind='evm_contracts', policyVersion=27)
    policies = fixture('launch_policies')['policies']
    zero_policy = copy.deepcopy(next(p for p in policies if p['params'].get('chainId') == 1))
    zero_policy['version'] = row['policyVersion']
    zero_policy['params'][field] = lc.ZERO
    policies.append(zero_policy)
    wallets, factories, _ = lc.policy_sets(policies, 1, row['policyVersion'])
    assert lc.ZERO not in wallets | factories
    tx = next(iter(rpc['transactions'].values())); tx['from' if field == 'owner' else 'to'] = lc.ZERO
    checks = lc.check_launch(row, lc.extract_facts(row), policies, rpc, keccak=keccak256)
    assert checks['K2']['state'] == 'fail'

@pytest.mark.parametrize('status,k4,want', [('parked','fail','✗ K4'),('parked','unknown','-- parked'),('admitted','fail','-- pending')])
def test_fix1_parked_and_admitted_verdict_precedence(status,k4,want):
    from maxpane_dashboard.analytics.surf_swarm_signals import launch_verdict_label
    row=fixture('launch_737'); row.update(status=status,artifacts=[])
    checks={k: {'state':'unknown'} for k in ('K1','K2','K3','K4')}
    checks['K4']['state']=k4
    assert launch_verdict_label(lc.verdict(row,checks))==want

@pytest.mark.parametrize('kind,version,expected', [('univ4_hook',19,'pass'),('custom_token',26,'pass'),('evm_contracts',27,'fail')])
def test_fix2_factories_belong_to_launch_kind(kind, version, expected):
    row, rpc = evidence(737)
    row.update(kind=kind, policyVersion=version)
    tx = next(iter(rpc['transactions'].values()))
    tx['to'] = '0x' + '2' * 40
    checks = lc.check_launch(row, lc.extract_facts(row), fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K2']['state'] == expected
    assert checks['K2']['evidence']['transactions'][0]['to'] == tx['to']

@pytest.mark.parametrize('shape', ['empty', 'renamed', 'unattested_hook'])
def test_fix2_k3_needs_matched_code_and_covers_role_artifacts(shape):
    row, rpc = evidence(737)
    facts = lc.extract_facts(row)
    if shape == 'empty':
        row['artifacts'] = []
    elif shape == 'renamed':
        for artifact in row['artifacts']: artifact['name'] += '_renamed'
    else:
        row['kind'] = 'univ4_hook'
        row['artifacts'].append({**row['artifacts'][-1], 'role':'hook', 'name':'UnattestedHook'})
    checks = lc.check_launch(row, facts, fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K3']['state'] == 'unknown'
    assert lc.verdict(row, checks)['state'] != 'swarm'
    if shape != 'empty':
        roles = ('token', 'hook') if shape == 'unattested_hook' else ('token',)
        unmatched = [a['name'] for a in row['artifacts'] if a['role'] in roles and a['name'] not in {c['name'] for c in facts['attested']}]
        assert checks['K3']['evidence']['unmatched_artifacts'] == unmatched


@pytest.mark.parametrize('kind,expected,unmatched', [
    ('custom_token', 'pass', []),
    ('evm_project', 'pass', []),
    ('univ4_hook', 'unknown', ['PoolInitializationGuard']),
])
def test_fix3_shared_hook_coverage_depends_on_launch_kind(kind, expected, unmatched):
    row, rpc = evidence(737)
    row['kind'] = kind
    checks = lc.check_launch(row, lc.extract_facts(row), fixture('launch_policies')['policies'], rpc, keccak=keccak256)
    assert checks['K3']['state'] == expected
    assert checks['K3']['evidence']['unmatched_artifacts'] == unmatched
