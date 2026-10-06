"""Pool facts from committed v8/v9 receipts; live K8 state is added in WP2."""
import copy
import json
from pathlib import Path

import pytest

from maxpane_dashboard.analytics import surf_launch_checks as lc
from maxpane_dashboard.analytics import surf_launch_liquidity as ll
from maxpane_dashboard.data import surf_models as models
from maxpane_dashboard.data import surf_swarm as sw

FIX = Path(__file__).parents[1] / 'fixtures/surf/swarm'
FIELDS = ('state', 'range_state', 'paired_symbol', 'paired_amount', 'token_amount',
          'pool_fee', 'tick', 'tick_lower', 'tick_upper', 'owner', 'owner_is_factory',
          'lock', 'withdrawn_pct', 'share', 'read_ts')


def fixture(number, suffix):
    version = 'v8' if number in (737, 747) else 'v9'
    return json.loads((FIX / version / f'{suffix.format(number=number)}.json').read_text())


def pool_fixture(number):
    row = fixture(number, 'launch_{number}')
    receipt = fixture(number, 'rpc_{number}_receipt')['result']
    return row, {receipt['transactionHash']: receipt}


def test_liquidity_contract_exact_fields_and_unknowns():
    assert models.SWARM_LIQUIDITY_KEYS == FIELDS
    assert ll.LIQUIDITY_KEYS == FIELDS
    assert ll.empty_liquidity() == dict.fromkeys(FIELDS) | {'state': 'unknown'}
    rows = sw.launch_rows(json.loads((FIX / 'v9/launches_100.json').read_text())['launches'])
    assert all('liquidity' in row for row in rows)
    assert all(row['liquidity'] is None for row in rows)
    assert 'liquidity' in models.SURF_ROW_KEYS['swarm_launch_rows']


@pytest.mark.parametrize('number,fee', [(737, 12500), (747, 12500), (775, 3000), (791, 12500)])
def test_initialize_fee_belongs_to_launch_pool(number, fee):
    row, receipts = pool_fixture(number)
    facts = ll.pool_initialize(row, receipts)
    assert facts['pool_fee'] == fee
    assert facts['emitter'] == ('0x8366a39cc670b4001a1121b8f6a443a643e40951' if number == 791
                               else '0x000000000004444c5dc75cb358380d2e3de08a90')
    token = next(a['address'].lower() for a in row['artifacts'] if a['role'] == 'token')
    assert token in (facts['currency0'], facts['currency1'])
    assert lc.extract_facts(row)['pool_fee'] is None, 'the manifest never supplies a live fee'
    assert ll.coerce_initialize(facts) == facts


def test_initialize_refuses_wrong_launch_malformed_and_ambiguous_logs():
    row, receipts = pool_fixture(737)
    _, others = pool_fixture(747)
    assert ll.pool_initialize(row, others) is None
    receipt = next(iter(receipts.values()))
    log = next(log for log in receipt['logs'] if log['topics'][0] == ll.INITIALIZE_TOPIC)
    for field, bad in [('address', 'bad'), ('data', '0x1234'), ('topics', [ll.INITIALIZE_TOPIC])]:
        changed = copy.deepcopy(receipts)
        candidate = next(l for l in next(iter(changed.values()))['logs'] if l['topics'][0] == ll.INITIALIZE_TOPIC)
        candidate[field] = bad
        assert ll.pool_initialize(row, changed) is None
    receipt['logs'].append(copy.deepcopy(log))
    assert ll.pool_initialize(row, receipts) is not None, 'identical duplicate evidence agrees'
    receipt['logs'][-1]['address'] = '0x' + '1' * 40
    assert ll.pool_initialize(row, receipts) is None, 'different emitters cannot identify one pool'


def test_liquidity_coercion_rejects_nonfinite_and_bool_numbers():
    value = ll.empty_liquidity()
    assert ll.coerce_liquidity(value) == value
    for field, bad in [('paired_amount', float('nan')), ('paired_amount', -1),
                       ('token_amount', 10**400), ('share', float('inf')),
                       ('tick', True), ('owner_is_factory', 1), ('state', 'safe')]:
        assert ll.coerce_liquidity(dict(value, **{field: bad})) is None
