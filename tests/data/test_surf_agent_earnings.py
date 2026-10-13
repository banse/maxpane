"""Offline earned-table decoding; real row samples, no explorer connection."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from maxpane_dashboard.data.surf_agent_earnings import (
    AgentEarningsClient, MAX_BYTES, MAX_ROWS, coerce_rows, parse_earned_html, summarize,
)

FIXTURES = Path(__file__).parents[1] / 'fixtures/surf/agent_earnings'
OWNER = '0x84F4b7424e1B0464f9C749725C1F34bed9AA8aDA'
NOW = 1_791_924_000.0


def raw_rows():
    return json.loads((FIXTURES / 'rows.json').read_text())


def page(rows, *, owner=OWNER, module='b7', split=False):
    """Reduced captured framing with changed module IDs and dynamic props."""
    flight = ('a:I[1,[],"EarnedProvider"]\n'
              f'{module}:I[2,[],"EarnedTable"]\n'
              '1:' + json.dumps(['$', '$La', None, {'wallet': owner, 'children': '$L2'}]) + '\n'
              '2:' + json.dumps(['$', f'$L{module}', None, {'rows': rows}]) + '\n')
    chunks = [flight[:90], flight[90:]] if split else [flight]
    return ''.join('<script>self.__next_f.push(' + json.dumps([1, chunk]) + ')</script>' for chunk in chunks)


def test_captured_rows_and_chunked_dynamic_exports_decode_without_javascript():
    captured = parse_earned_html((FIXTURES / 'earned.html').read_text(), OWNER)
    assert captured is not None and len(captured) == 4
    assert parse_earned_html(page(raw_rows(), module='f00', split=True), OWNER.lower()) == captured
    assert captured[0] == {
        'chain_id': 4663, 'token_address': '0x8b0af445930544286743dcac225702836debf19a',
        'job_id': '03691248-f445-41ce-8d20-6503c0f8b105',
        'launched_ts': 1791920212.342, 'builder': False, 'claimed': False,
    }
    assert sum(row['builder'] for row in captured) == 1
    assert sum(row['claimed'] for row in captured) == 1


def test_empty_table_is_a_real_zero_but_absent_or_wrong_wallet_is_unknown():
    assert parse_earned_html(page([]), OWNER) == []
    assert summarize([], set(), NOW) == {'earned': 0, 'worked_on': 0, 'claimed': 0, 'worked_recent': False}
    for html in ('', '<html>not found</html>', page([])[:-30], page([], owner='0x' + '1' * 40)):
        assert parse_earned_html(html, OWNER) is None


@pytest.mark.parametrize('change', [
    {'launchId': 'not-a-job'}, {'chainId': True}, {'chainId': 0},
    {'tokenAddress': '0x1234'}, {'tokenAddress': None}, {'jobId': '../secret'},
    {'cuts': ['mystery']}, {'cuts': []}, {'claim': {'state': 'pending'}},
    {'claim': None},
])
def test_one_malformed_row_invalidates_the_whole_table(change):
    rows = raw_rows()
    rows[0].update(change)
    assert parse_earned_html(page(rows), OWNER) is None


@pytest.mark.parametrize('at', [None, 'invalid', '2026-10-13', '2026-10-13T19:36:52'])
def test_bad_or_missing_date_cannot_make_recent_work(at):
    row = raw_rows()[2]
    row['at'] = at
    parsed = parse_earned_html(page([row]), OWNER)
    assert parsed is not None and parsed[0]['launched_ts'] is None
    assert summarize(parsed, {row['jobId']}, NOW)['worked_recent'] is False


def test_earned_counts_assets_not_rows_or_units_and_claims_require_explicit_state():
    row = parse_earned_html(page([raw_rows()[2]]), OWNER)[0]
    row['launched_ts'] = NOW - 1
    duplicate = dict(row, builder=False, claimed=True)
    other_chain = dict(row, chain_id=1 if row['chain_id'] != 1 else 4663, builder=False)
    rows = [row, duplicate, other_chain]
    assert summarize(rows, {row['job_id']}, NOW) == {
        'earned': 2, 'worked_on': 1, 'claimed': 1, 'worked_recent': True,
    }
    assert summarize(rows, {'11111111-1111-1111-1111-111111111111'}, NOW) == {
        'earned': 2, 'worked_on': 0, 'claimed': 1, 'worked_recent': False,
    }
    raw = raw_rows()[0]
    raw['amount'] = 0
    assert summarize(parse_earned_html(page([raw]), OWNER), set(), NOW)['earned'] == 1


@pytest.mark.parametrize('age,recent', [(0, True), (86399.999, True), (86400, False), (-1, False)])
def test_recent_work_uses_launch_time_with_an_injected_clock(age, recent):
    row = parse_earned_html(page([raw_rows()[2]]), OWNER)[0]
    row['launched_ts'] = NOW - age
    assert summarize([row], {row['job_id']}, NOW)['worked_recent'] is recent


@pytest.mark.parametrize('field,value', [
    ('chain_id', True), ('chain_id', 0), ('token_address', 'bad'), ('job_id', 'bad'),
    ('launched_ts', float('nan')), ('launched_ts', float('inf')), ('launched_ts', True),
    ('launched_ts', 10 ** 500),
    ('builder', 1), ('claimed', 'claimed'),
])
def test_cache_revalidation_is_atomic(field, value):
    rows = parse_earned_html(page(raw_rows()), OWNER)
    rows[-1][field] = value
    assert coerce_rows(rows) is None


def test_cache_revalidation_copies_normalizes_and_bounds_every_row():
    rows = parse_earned_html(page(raw_rows()), OWNER)
    rows[0]['token_address'] = rows[0]['token_address'].upper().replace('0X', '0x')
    original = copy.deepcopy(rows)
    result = coerce_rows(rows)
    assert result[0]['token_address'] == rows[0]['token_address'].lower()
    assert rows == original and result is not rows
    assert coerce_rows([rows[0]] * (MAX_ROWS + 1)) is None
    assert coerce_rows({}) is None
    assert coerce_rows([{}]) is None
    assert parse_earned_html(page([raw_rows()[0]] * (MAX_ROWS + 1)), OWNER) is None
    assert parse_earned_html(' ' * (MAX_BYTES + 1), OWNER) is None


def test_flight_text_records_are_length_delimited_not_executable_component_text():
    payload = '2:["$","$Lb7",null,{"rows":[]}]\n'
    prefix = f'ff:T{len(payload.encode()):x},' + payload
    html = '<script>self.__next_f.push(' + json.dumps([1, prefix]) + ')</script>' + page(raw_rows())
    assert parse_earned_html(html, OWNER) == parse_earned_html(page(raw_rows()), OWNER)


def test_captured_resource_hints_do_not_hide_the_table():
    hint = ':HL["/_next/static/chunks/34dbb9ytjix2a.css","style"]\n'
    html = '<script>self.__next_f.push(' + json.dumps([1, hint]) + ')</script>' + page(raw_rows())
    assert parse_earned_html(html, OWNER) == parse_earned_html(page(raw_rows()), OWNER)


async def test_client_uses_one_fixed_get_and_owns_its_injected_transport():
    calls = []
    def respond(request):
        calls.append(request)
        assert request.method == 'GET'
        assert str(request.url) == f'https://explorer.imd.fun/wallet/{OWNER.lower()}/earned'
        assert request.extensions['timeout']['read'] == 15.0
        return httpx.Response(200, text=(FIXTURES / 'earned.html').read_text())
    client = AgentEarningsClient(transport=httpx.MockTransport(respond))
    assert len(await client.fetch(OWNER)) == 4
    await client.close()
    assert client._client.is_closed and len(calls) == 1


@pytest.mark.parametrize('status,headers,body', [
    (302, {'location': 'https://example.com/'}, ''), (500, {}, ''), (200, {}, '<html>oops'),
    (200, {'content-length': str(MAX_BYTES + 1)}, ''), (200, {}, 'x' * (MAX_BYTES + 1)),
])
async def test_client_never_follows_redirects_and_caps_response_bytes(status, headers, body):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers=headers, text=body)
    async with AgentEarningsClient(transport=httpx.MockTransport(respond)) as client:
        assert await client.fetch(OWNER) is None
    assert len(calls) == 1


async def test_bad_owner_cannot_construct_request_and_timeout_is_unavailable():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout('offline')
    async with AgentEarningsClient(transport=httpx.MockTransport(timeout)) as client:
        for owner in (None, True, '../secret', OWNER + '?x=1', []):
            assert await client.fetch(owner) is None
        assert calls == []
        assert await client.fetch(OWNER) is None
        assert len(calls) == 1
