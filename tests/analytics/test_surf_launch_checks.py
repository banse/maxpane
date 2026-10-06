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
