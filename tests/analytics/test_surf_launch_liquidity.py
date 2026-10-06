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

from maxpane_dashboard.data.keccak import keccak256


def live_fixture(number):
    row, receipts = pool_fixture(number)
    pool = ll.pool_inputs(row, receipts)
    answers = {x['id']: x.get('result') for x in json.loads((FIX / f'v9/rpc_{number}_pool_state.json').read_text())}
    decimals = {pool[f'currency{i}']: (18 if pool[f'currency{i}'] == lc.ZERO else int(answers[10+i], 16)) for i in (0, 1)}
    return row, pool, answers, decimals


@pytest.mark.parametrize('number,paired,symbol,fee', [(737,4726.591141,'IMD',12500),(747,0,'ETH',12500),(775,14.2330796,'ETH',3000),(791,.10126446,'IMD',12500)])
def test_live_liquidity_capture_amounts_slots_and_lock(number, paired, symbol, fee):
    row, pool, answers, decimals = live_fixture(number)
    manifest = json.loads((FIX / 'v9/MANIFEST.json').read_text())['files'][f'rpc_{number}_pool_state']['request']
    calls = ll.state_calls(pool, keccak=keccak256)
    assert calls == [(x['method'], x['params']) for x in manifest[:3]]
    result = ll.liquidity_result(row, pool, [answers[i] for i in range(3)], decimals,
                                 fixture(number, 'launch_policies')['policies'],
                                 {'K2': {'evidence': {'transactions': [{'to': next(iter(pool_fixture(number)[1].values()))['to']}]}}}, now=1791300000)
    assert result['paired_amount'] == pytest.approx(paired, rel=1e-6)
    assert result['paired_symbol'] == symbol and result['pool_fee'] == fee
    assert result['lock'] == 'locked' and result['owner_is_factory'] is True
    assert result['withdrawn_pct'] == 0 and result['read_ts'] == 1791300000
    assert result['range_state'] == ('at limit' if number == 747 else 'in range')
    assert result['state'] == ('warn' if number == 747 else 'info')
    assert result['share'] == (None if number == 747 else pytest.approx(1))
    if number == 737:
        assert result['token_amount'] == pytest.approx(280622281.46, rel=1e-6)
    assert ll.coerce_pool_inputs(pool) == pool
    assert ll.coerce_liquidity(result) == result


def test_pool_evidence_binds_modify_to_initialize_and_distinguishes_missing_from_absent():
    row, receipts = pool_fixture(737)
    pool = ll.pool_inputs(row, receipts)
    assert pool['owner'] == '0xff03410d0fe5fa8f7f59f743de35e333d9857120'
    assert pool['tick_lower'] == -887220 and pool['tick_upper'] == 128940
    for field in ('address','topics'):
        changed = copy.deepcopy(receipts)
        log = next(l for l in next(iter(changed.values()))['logs'] if l['topics'][0] == ll.MODIFY_TOPIC)
        if field == 'address': log[field] = '0x'+'1'*40
        else: log[field][1] = '0x'+'1'*64
        assert ll.pool_inputs(row, changed) is None
    assert ll.pool_inputs(row, {}) is None
    clean = copy.deepcopy(receipts)
    next(iter(clean.values()))['logs'] = []
    assert ll.pool_inputs(row, clean) == {'state':'na'}
    next(iter(clean.values()))['logs'] = [{'topics':[ll.INITIALIZE_TOPIC], 'data':'bad'}]
    assert ll.pool_inputs(row, clean) is None
    assert ll.pool_inputs(dict(row, kind='evm_contracts'), {}) == {'state':'na'}


def test_signed_tick_decoding_withdrawal_burn_and_failed_reads():
    row, pool, answers, decimals = live_fixture(737)
    words = [answers[i] for i in range(3)]
    words[0] = '0x'+(((int(words[0],16) & ((1<<160)-1)) | ((-123 & ((1<<24)-1)) <<160))).to_bytes(32,'big').hex()
    assert ll.decode_state(words)['tick'] == -123
    words = [answers[i] for i in range(3)]
    words[2] = '0x'+(pool['initial_liquidity']//2).to_bytes(32,'big').hex()
    result = ll.liquidity_result(row,pool,words,decimals,[],{},now=1791300000)
    assert result['lock'] == 'withdrawn' and result['withdrawn_pct'] == pytest.approx(50)
    assert result['state'] == 'warn'
    checks = {k:lc.result('pass') for k in ('K1','K2','K3','K4')}
    checks['K8'] = result
    assert lc.verdict(row,checks)['state'] == 'swarm'
    result = ll.liquidity_result(row,dict(pool, owner='0x'+'0'*36+'dead'),[answers[i] for i in range(3)],decimals,[],{},now=1791300000)
    assert result['lock'] == 'burned'
    for i in range(3):
        failed = [answers[j] if j != i else None for j in range(3)]
        assert ll.liquidity_result(row,pool,failed,decimals,[],{},now=1791300000) is None
    assert ll.liquidity_result(row,pool,[answers[i] for i in range(3)],{},[],{},now=1791300000) is None


def test_pool_and_result_cache_ranges_and_siblings():
    row,pool,answers,decimals = live_fixture(737)
    for field,bad in [('tick_lower',True),('tick_upper',-887221),('initial_liquidity',-1),('salt','0x01'),('owner','bad')]:
        assert ll.coerce_pool_inputs(dict(pool,**{field:bad})) is None
    result=ll.liquidity_result(row,pool,[answers[i] for i in range(3)],decimals,[],{},now=1791300000)
    for field,bad in [('share',1.01),('withdrawn_pct',101),('tick_lower',128941)]:
        assert ll.coerce_liquidity(dict(result,**{field:bad})) is None


def test_one_sided_range_hour_boundary_and_missing_decimals_are_honest():
    row,pool,answers,decimals=live_fixture(737)
    row['createdAt']='2026-10-06T00:00:00Z'
    from datetime import datetime
    created=datetime.fromisoformat(row['createdAt'].replace('Z','+00:00')).timestamp()
    def price(tick):
        sqrt_price=int(1.0001**(tick/2)*2**96)
        word=((tick & (2**24-1)) <<160) | sqrt_price
        return ['0x'+word.to_bytes(32,'big').hex(),answers[1],answers[2]]
    # Token is currency1: beyond upper tick is token-only, below lower is paired-only.
    token=ll.liquidity_result(row,pool,price(128941),decimals,[],{},now=created+3600)
    assert token['range_state']=='token only' and token['paired_amount']==0 and token['token_amount']>0
    assert token['state']=='info'
    assert ll.liquidity_result(row,pool,price(128941),decimals,[],{},now=created+3601)['state']=='warn'
    paired=ll.liquidity_result(row,pool,price(-887221),decimals,[],{},now=created+3601)
    assert paired['range_state']=='paired only' and paired['token_amount']==0 and paired['paired_amount']>0
    words=[answers[0],answers[1],'0x'+'0'*64]
    zero=ll.liquidity_result(row,pool,words,decimals,[],{},now=created+3601)
    assert zero['lock']=='withdrawn' and zero['withdrawn_pct']==100
    token_currency=pool['currency1']
    altered=dict(decimals); altered[token_currency]-=6
    scaled=ll.liquidity_result(row,pool,[answers[i] for i in range(3)],altered,[],{},now=created+3601)
    baseline=ll.liquidity_result(row,pool,[answers[i] for i in range(3)],decimals,[],{},now=created+3601)
    assert scaled['token_amount']==pytest.approx(baseline['token_amount']*1e6)
    assert scaled['paired_amount']==baseline['paired_amount']
