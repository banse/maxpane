"""One-shot keyless evidence capture; never imported by tests.

Run with .venv311/bin/python tests/scripts/capture_oracle_requests.py.
Use --summarize to re-derive the join counts offline from the raw corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1] / 'fixtures/surf/swarm/oracle'
HOST = 'https://api.imd.fun'


def summarize():
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    if any(entry.get('committed') is False for entry in manifest['files'].values()):
        raise SystemExit('--summarize needs the full corpus; the committed set is slimmed '
                         '(MANIFEST "slimmed"). Re-run the capture first.')
    seat = json.loads((ROOT / 'seat_420.json').read_bytes())
    work = [row for row in seat['work'] if row['nodeKey'] == 'oracle_assess']
    details = [json.loads(p.read_bytes()) for p in ROOT.glob('request_*.json')]
    counts = Counter(oracle_work=len(work))
    coverage = set()
    # Null members is served for blocked requests; no member join is possible.
    for row in work:
        matches = [(d, m) for d in details for m in (d.get('members') or [])
                   if m.get('submissionHash') == row['submissionHash']]
        if not matches:
            counts['not_on_panel'] += 1
            counts['not_on_panel_' + row['status']] += 1
            continue
        d, member = matches[0]
        counts['matched'] += 1
        agreement = d.get('agreement') or {}
        inside = row['submissionHash'] in (agreement.get('cluster') or [])
        status = d['status']
        coverage.add(status + ('_in' if inside else '_out'))
        counts[status] += 1
        if status in ('attested', 'disagreed'):
            counts['in_cluster' if inside else 'outside_cluster'] += 1
            counts[status + ('_in' if inside else '_out')] += 1
        if inside and d.get('toleranceBps') == 1000 and (member.get('answer') or {}).get('figure') != agreement.get('figure'):
            coverage.add('tolerance_unequal')
        if status == 'attested' and not inside and (member.get('answer') or {}).get('figure') == '0':
            coverage.add('outvoted_zero')
    for d in details:
        if d.get('answerType') == 'bool':
            coverage.add('bool')
        if d.get('status') == 'blocked':
            coverage.add('blocked')
    return {'counts': dict(counts), 'coverage': sorted(coverage),
            'note': 'No attested outvoted seat-420 member with figure 0 in the captured history.' if 'outvoted_zero' not in coverage else 'An outvoted zero answer is captured.'}


def capture():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {'host': HOST, 'note': '', 'files': {}}
    with httpx.Client(timeout=30, headers={'Accept': 'application/json'}, follow_redirects=False) as client:
        def get(name, path, why, params=None):
            time.sleep(0.2)
            response = client.get(HOST + path, params=params)
            raw = response.content
            (ROOT / (name + '.json')).write_bytes(raw)
            manifest['files'][name] = {
                'url': str(response.url), 'captured_at': datetime.now(timezone.utc).isoformat(),
                'http_status': response.status_code, 'sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw), 'selected_because': why,
            }
            (ROOT / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
            if response.status_code == 200:
                return response.json()
            if name not in ('invalid_id', 'unknown_id'):
                response.raise_for_status()
            return None

        seat = get('seat_420', '/seats/420', 'join source: every seat attempt')
        requests = []
        before = None
        page = 0
        while True:
            page += 1
            params = {'limit': '200'}
            if before:
                params['before'] = before
            body = get(f'list_{page}', '/oracle/requests', 'complete list history for reproducible counts', params)
            rows = body['requests']
            requests.extend(rows)
            if len(rows) < 200:
                break
            cursor = min(row['createdAt'] for row in rows)
            if before and cursor >= before:
                raise RuntimeError('list cursor did not advance')
            before = cursor
        jobs = {row['jobId'] for row in seat['work'] if row['nodeKey'] == 'oracle_assess'}
        special = set()
        for row in requests:
            reasons = []
            if row.get('jobId') in jobs:
                reasons.append('seat 420 job; confirm membership by submissionHash')
            for label, match in [('blocked', row.get('status') == 'blocked'), ('bool', row.get('answerType') == 'bool'), ('assessing', row.get('status') == 'assessing')]:
                if match and label not in special:
                    reasons.append(label + ' shape')
                    special.add(label)
            if reasons:
                get('request_' + row['id'], '/oracle/requests/' + row['id'], '; '.join(reasons))
        get('invalid_id', '/oracle/requests/not-a-uuid', 'malformed id status')
        get('unknown_id', '/oracle/requests/00000000-0000-4000-8000-000000000000', 'well-formed unknown id status')
    result = summarize()
    manifest['note'] = {'derived': result, 'assessing_present_in_list': any(r.get('status') == 'assessing' for r in requests), 'bool_present_in_list': any(r.get('answerType') == 'bool' for r in requests), 'list_count': len(requests)}
    (ROOT / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest['note'], indent=2))


def capture_member():
    """Small filtered evidence set; never rewrite the original full-corpus manifest."""
    out = ROOT / 'filtered'
    out.mkdir(exist_ok=True)
    manifest = {'host': HOST, 'files': {}}
    seat = json.loads((ROOT / 'seat_420.json').read_bytes())
    work = {(row['jobId'], row['submissionHash']) for row in seat['work']}
    chosen = next((detail, member) for path in sorted(ROOT.glob('request_*.json'))
                  for detail in [json.loads(path.read_bytes())]
                  for member in detail.get('members') or []
                  if (detail['jobId'], member['submissionHash']) in work)
    with httpx.Client(timeout=30, headers={'Accept': 'application/json'}) as client:
        def get(name, path, params=None):
            time.sleep(0.2)
            response = client.get(HOST + path, params=params)
            response.raise_for_status()
            raw = response.content
            (out / (name + '.json')).write_bytes(raw)
            manifest['files'][name] = dict(url=str(response.url),
                captured_at=datetime.now(timezone.utc).isoformat(), http_status=response.status_code,
                sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            return response.json()
        manifest['version'] = get('version', '/version')
        detail, member = chosen
        path = '/oracle/requests/' + detail['id']
        hit = get('hit', path, {'members': member['submissionHash']})
        assert any(m['submissionHash'] == member['submissionHash'] for m in hit['members'])
        miss = get('miss', path, {'members': '0' * 64})
        assert miss['members'] == []
        listed = client.get(HOST + '/oracle/requests', params={'limit': '500'})
        listed.raise_for_status()
        assessing = next((r for r in listed.json()['requests'] if r['status'] == 'assessing'), None)
        if assessing:
            path = '/oracle/requests/' + assessing['id']
            full = client.get(HOST + path); full.raise_for_status()
            members = full.json().get('members') or []
            key = members[0]['submissionHash'] if members else '0' * 64
            get('assessing', path, {'members': key})
            manifest['assessing_full_bytes'] = len(full.content)
        else:
            manifest['assessing'] = 'No live assessing request in the newest 500.'
    for entry in manifest['files'].values():
        entry['control_plane_commit'] = manifest['version']['commit']
    (out / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({name: entry['bytes'] for name, entry in manifest['files'].items()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summarize', action='store_true')
    parser.add_argument('--member', action='store_true')
    args = parser.parse_args()
    if args.member:
        capture_member()
    elif args.summarize:
        result = summarize()
        manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
        rows = [r for p in ROOT.glob('list_*.json') for r in json.loads(p.read_bytes())['requests']]
        manifest['note'] = {'derived': result, 'assessing_present_in_list': any(r.get('status') == 'assessing' for r in rows), 'bool_present_in_list': any(r.get('answerType') == 'bool' for r in rows), 'list_count': len(rows)}
        (ROOT / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    else:
        capture()
