"""Read-only wallet earnings from the explorer's bounded, served flight table."""
from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
import json
import re

import httpx

from maxpane_dashboard.data.rpc_common import OwnedHttpClient

MAX_BYTES = 4 * 1024 * 1024
MAX_ROWS = 4096
_ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}')
_UUID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
_STATES = {'locked', 'claimable', 'claimed', 'held'}


def _matches(pattern: re.Pattern, value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _positive(value: object) -> bool:
    # datetime's representable positive epoch range; excludes NaN and infinity.
    return type(value) in (int, float) and 0 < value < 253402300800


def coerce_rows(value: object) -> list[dict] | None:
    """Revalidate the entire cache list; never silently undercount a bad point."""
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        return None
    result = []
    for row in value:
        if (not isinstance(row, dict) or type(row.get('chain_id')) is not int
                or not 0 < row['chain_id'] <= 2 ** 53
                or not _matches(_ADDRESS, row.get('token_address'))
                or not _matches(_UUID, row.get('job_id'))
                or 'launched_ts' not in row
                or (row['launched_ts'] is not None and not _positive(row['launched_ts']))
                or type(row.get('builder')) is not bool or type(row.get('claimed')) is not bool):
            return None
        result.append({
            'chain_id': row['chain_id'], 'token_address': row['token_address'].lower(),
            'job_id': row['job_id'].lower(), 'launched_ts': row['launched_ts'],
            'builder': row['builder'], 'claimed': row['claimed'],
        })
    return result


def _timestamp(value: object) -> float | None:
    if not isinstance(value, str) or len(value) > 40 or 'T' not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        result = parsed.timestamp() if parsed.tzinfo else None
        return result if _positive(result) else None
    except (ValueError, OverflowError, OSError):
        return None


def _normalize(rows: object) -> list[dict] | None:
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        return None
    result = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        claim, cuts = row.get('claim'), row.get('cuts')
        if (not _matches(_UUID, row.get('launchId'))
                or not isinstance(claim, dict) or claim.get('state') not in _STATES
                or claim.get('launchId') != row['launchId']
                or type(row.get('chainId')) is not int or not 0 < row['chainId'] <= 2 ** 53
                or type(claim.get('chainId')) is not int or claim['chainId'] != row['chainId']
                or not _matches(_UUID, row.get('jobId'))
                or not isinstance(cuts, list) or not cuts
                or any(cut not in ('swarm', 'builder') for cut in cuts)):
            return None
        if row.get('tokenAddress') is None and 'tokenAddress' in row and claim['state'] == 'held':
            continue  # A held allocation does not identify an earned token yet.
        result.append({
            'chain_id': row['chainId'], 'token_address': row.get('tokenAddress'),
            'job_id': row['jobId'], 'launched_ts': _timestamp(row.get('at')),
            'builder': 'builder' in cuts, 'claimed': claim['state'] == 'claimed',
        })
    return coerce_rows(result)


class _FlightScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.script = None
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.script = []

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag != 'script' or self.script is None:
            return
        source = ''.join(self.script).strip()
        self.script = None
        match = re.fullmatch(r'self\.__next_f\.push\((.*)\);?', source, re.S)
        if match:
            payload = json.loads(match[1])
            if isinstance(payload, list) and len(payload) == 2 and payload[0] == 1 and isinstance(payload[1], str):
                self.chunks.append(payload[1])


def _records(flight: bytes) -> list[tuple[str, object, bool]]:
    """Skip byte-counted text records so their content cannot pose as a table."""
    records = []
    position = 0
    while position < len(flight):
        header = re.match(rb'([0-9a-f]*):', flight[position:])
        if not header:
            raise ValueError('invalid flight record')
        position += header.end()
        if flight[position:position + 1] == b'T':
            length = re.match(rb'T([0-9a-f]+),', flight[position:])
            if not length:
                raise ValueError('invalid text record')
            position += length.end() + int(length[1], 16)
            if position > len(flight):
                raise ValueError('truncated text record')
            continue
        end = flight.find(b'\n', position)
        if end == -1:
            raise ValueError('truncated flight record')
        body = flight[position:end]
        position = end + 1
        if not header[1] and body.startswith(b'HL'):
            json.loads(body[2:])  # Resource hints carry no component identity.
            continue
        if not header[1]:
            raise ValueError('missing flight identity')
        if body in (b'X', b'C'):
            continue
        imported = body.startswith(b'I')
        records.append((header[1].decode(), json.loads(body[1:] if imported else body), imported))
    return records


def parse_earned_html(html: str, owner: str) -> list[dict] | None:
    """Resolve export names and validate the served wallet; never execute JS."""
    if not isinstance(html, str) or not _matches(_ADDRESS, owner):
        return None
    try:
        if len(html.encode('utf-8')) > MAX_BYTES:
            return None
        parser = _FlightScripts()
        parser.feed(html)
        parser.close()
        records = _records(''.join(parser.chunks).encode('utf-8'))
        exports = {name: {key for key, value, imported in records
                         if imported and isinstance(value, list) and len(value) >= 3 and value[2] == name}
                   for name in ('EarnedProvider', 'EarnedTable')}
        if any(len(refs) != 1 for refs in exports.values()):
            return None
        references = {name: '$L' + next(iter(refs)) for name, refs in exports.items()}
        found = {name: [] for name in exports}
        stack = [value for _, value, imported in records if not imported]
        while stack:
            value = stack.pop()
            if isinstance(value, list):
                if len(value) == 4 and value[0] == '$' and isinstance(value[3], dict):
                    for name, ref in references.items():
                        if value[1] == ref:
                            found[name].append(value[3])
                stack.extend(value)
            elif isinstance(value, dict):
                stack.extend(value.values())
        if any(len(props) != 1 for props in found.values()):
            return None
        wallet = found['EarnedProvider'][0].get('wallet')
        if not _matches(_ADDRESS, wallet) or wallet.lower() != owner.lower():
            return None
        return _normalize(found['EarnedTable'][0].get('rows'))
    except (ValueError, TypeError, RecursionError, OverflowError):
        return None


def summarize(rows: list[dict], accepted_job_ids: set[str], now: float) -> dict:
    """Wallet asset totals; builder participation belongs to the selected seat."""
    accepted = {job.lower() for job in accepted_job_ids}
    earned, worked, claimed = set(), set(), set()
    recent = False
    for row in rows:
        asset = (row['chain_id'], row['token_address'])
        earned.add(asset)
        if row['claimed']:
            claimed.add(asset)
        if row['builder'] and row['job_id'] in accepted:
            worked.add(asset)
            launched = row['launched_ts']
            recent |= launched is not None and 0 <= now - launched < 86400
    return {'earned': len(earned), 'worked_on': len(worked), 'claimed': len(claimed), 'worked_recent': recent}


class AgentEarningsClient(OwnedHttpClient):
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(transport=transport, timeout=15.0, follow_redirects=False)
        self._owns_client = True

    async def fetch(self, owner: str) -> list[dict] | None:
        if not _matches(_ADDRESS, owner):
            return None
        url = f'https://explorer.imd.fun/wallet/{owner.lower()}/earned'
        try:
            async with self._client.stream('GET', url, timeout=15.0, follow_redirects=False) as response:
                response.raise_for_status()
                length = response.headers.get('content-length')
                if length is not None and (not length.isdecimal() or int(length) > MAX_BYTES):
                    return None
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > MAX_BYTES:
                        return None
                    body.extend(chunk)
                return parse_earned_html(body.decode('utf-8'), owner)
        except (httpx.HTTPError, ValueError):
            return None
