"""One-shot keyless submission popup captures; never imported by tests."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1] / 'fixtures/surf/swarm'
HOST = 'https://api.imd.fun'


def capture():
    out = ROOT / 'submissions'
    out.mkdir(exist_ok=True)
    manifest = {'host': HOST, 'files': {}}
    with httpx.Client(timeout=30, follow_redirects=False, headers={'Accept': 'application/json'}) as client:
        def get(name, path, params=None, directory=out):
            target = directory / (name + '.json')
            request = client.build_request('GET', HOST + path, params=params)
            if target.exists():
                raw = target.read_bytes()  # Resume an interrupted one-shot without re-fetching captures.
            else:
                response = client.send(request)
                response.raise_for_status()
                raw = response.content
                target.write_bytes(raw)
            manifest['files'][name] = dict(url=str(request.url), captured_at=datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(),
                http_status=200, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                path=str((directory / (name + '.json')).relative_to(ROOT)))
            (out / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
            return json.loads(raw)
        version = get('version', '/version')
        seat = get('seat_420', '/seats/420')
        work = seat['work']
        hunt = '7b9c907d-99b9-405b-8491-6088c77d4cc9'
        bundle = next(row['jobId'] for row in work if row['jobId'].startswith('2d73c9e2'))
        completed = next((row['jobId'] for row in work[:40] if row.get('nodeKey') != 'oracle_assess'
                          and row.get('jobState') == 'completed'), None)
        for label, job in [('hunt', hunt), ('bundle', bundle), ('completed', completed)]:
            if job:
                get(label + '_submissions', f'/jobs/{job}/submissions')
                get(label + '_job', f'/jobs/{job}')
        if not completed:
            manifest['completed_fallback'] = 'v4/submissions_33016bad.json'
        listed = get('oracle_list', '/oracle/requests', {'limit': 500})
        request = next(r for r in listed['requests'] if r['jobId'].startswith('4c11a919'))
        member = next(row['submissionHash'] for row in work if row['jobId'] == request['jobId'])
        get('bytes32', '/oracle/requests/' + request['id'], {'members': member}, ROOT / 'oracle/filtered')
    for entry in manifest['files'].values():
        entry['control_plane_commit'] = version['commit']
    (out / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({name: entry['bytes'] for name, entry in manifest['files'].items()}))


if __name__ == '__main__':
    capture()
