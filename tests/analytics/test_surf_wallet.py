from copy import deepcopy
from decimal import Decimal

from maxpane_dashboard.analytics.surf_wallet import payment_totals, summary, usage_signal, usage_text


def test_unread_is_distinct_from_observed_empty():
    unread = summary({'orders': None, 'artifacts': None}, now=1000)
    assert unread['counts']['REQUESTS'] is None and unread['counts']['CONTRACTS'] is None
    assert unread['daily'] is None and unread['signals'] is None
    empty = summary({'orders': [], 'artifacts': []}, now=1000)
    assert empty['counts']['REQUESTS'] == empty['counts']['CONTRACTS'] == 0
    assert empty['daily'] == [0] * 30


def test_partial_zero_stays_unknown_and_sites_do_not_duplicate_usage():
    contract = dict(id='1:contract', kind='CONTRACT', usage=dict(count=0, complete=False, unit='updates', actors=0))
    site = dict(id='site:one', kind='SITE', linked_id=contract['id'], binding_checked=True)
    token = dict(id='1:token', kind='TOKEN', usage=dict(count=4, complete=True, unit='redemptions', actors=3))
    assets = [contract, site, token]
    by_id = {a['id']: a for a in assets}
    assert usage_signal(contract, by_id) == usage_signal(site, by_id) == 'NO DATA'
    assert usage_text(contract, by_id) == '--'
    result = summary({'orders': [], 'artifacts': assets}, now=1000)
    assert result['counts']['CONTRACTS'] == 2 and result['counts']['TOKENS'] == 1
    assert result['signals'] == {'Active': 1, 'Quiet': 0, 'Unknown': 1}
    contract['usage']['count'] = 2
    assert usage_signal(site, by_id) == 'LINKED ACTIVE'
    assert usage_text(contract, by_id).startswith('>=2 updates')


def test_order_window_and_state_partition_do_not_count_children_or_old_requests():
    rows = [dict(id=str(i), action=action, timestamp=1000, payment_state=payment,
                 outcome=outcome, in_flight=flight, follow_up=attention)
            for i, (action, payment, outcome, flight, attention) in enumerate([
                ('job.open', 'settled', 'completed', False, False),
                ('job.continue', 'settled', 'working', True, False),
                ('oracle.request', 'settled', 'blocked', False, True),
                ('schedule.topup', 'failed', 'not admitted', False, True),
                ('launch.open', 'settled', 'admitted', False, False)])]
    rows.append(dict(rows[0], id='old', timestamp=1000 - 31 * 86400))
    result = summary({'orders': rows, 'artifacts': [], 'sources': {}}, now=1001)
    assert result['counts']['REQUESTS'] == 5 and result['counts']['JOBS'] == 2
    assert sum(result['states'].values()) == 5
    assert result['states'] == {'Completed': 1, 'In flight': 1, 'Attention': 1, 'Not admitted': 1, 'Unknown': 1}
    assert sum(result['daily']) == 5
    assert result['counts']['ATTENTION'] == 2


def test_amounts_are_exact_asset_scoped_deduplicated_and_refunds_unknown():
    p = dict(chain_id=1, asset='0x'+'a'*40, symbol='IMD', decimals=18, amount='0.1', tx_hash='0x'+'1'*64)
    rows = [dict(payment_state='settled', payments=[p]),
            dict(payment_state='settled', payments=[dict(p, amount='0.2', tx_hash='0x'+'2'*64)]),
            dict(payment_state='settled', payments=[deepcopy(p)])]
    values = payment_totals(rows)
    assert len(values) == 1 and Decimal(values[0]['paid']) == Decimal('0.3')
    assert values[0]['count'] == 2 and values[0]['refunded'] is None
    assert values[0]['refund_complete'] is False
    rows.append(dict(payment_state='settled', payments=None))
    assert payment_totals(rows)[0]['paid_complete'] is False
    assert payment_totals([dict(payment_state='settled', payments=None)]) is None


def test_projection_uses_observation_clock_when_now_is_unread():
    snapshot = dict(orders=[dict(timestamp=1000, action='job.open')], artifacts=[], as_of=1001)
    assert summary(snapshot, now=None)['counts']['REQUESTS'] == 1
    snapshot['as_of'] = None
    assert summary(snapshot, now=None)['orders'] is None


def test_atomic_scale_amounts_do_not_round_at_decimal_default_precision():
    amount = '123456789012345678901234567890.123456789012345678'
    payment = dict(chain_id=1, asset='0x'+'a'*40, decimals=18, amount=amount, tx_hash='0x'+'1'*64)
    rows = [dict(payment_state='settled', payments=[payment])]
    assert payment_totals(rows)[0]['paid'] == amount
    maximum = 2**256 - 1
    rows = [dict(payment_state='settled', payments=[dict(payment, amount=str(maximum), decimals=0,
                                                       tx_hash='0x' + digit*64)]) for digit in ('1', '2')]
    assert payment_totals(rows)[0]['paid'] == str(2*maximum)
