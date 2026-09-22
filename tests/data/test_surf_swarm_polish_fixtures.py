"""WP0 provenance for the polish corpus; tests never fetch a route."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parents[1] / 'fixtures/surf/swarm/v4'
CAPTURES = ('submissions_73d7dcd7', 'submissions_76296dcd', 'submissions_33016bad',
            'seat_420', 'workers', 'skills', 'health')


def test_polish_manifest_binds_exact_capture_bytes_and_utc_provenance():
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    assert set(manifest['files']) == {*CAPTURES, 'submissions_hostile'}
    assert {p.stem for p in ROOT.glob('*.json')} == {*CAPTURES, 'submissions_hostile', 'MANIFEST'}
    for name, entry in manifest['files'].items():
        raw = (ROOT / f'{name}.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        assert len(raw) == entry['bytes']
        assert isinstance(json.loads(raw), dict)
        assert datetime.fromisoformat(entry['captured_at']).utcoffset().total_seconds() == 0
        if name in CAPTURES:
            assert entry['url'].startswith('https://api.imd.fun/')
            assert entry['http_status'] == 200
        else:
            assert entry['provenance'].startswith('Hand-made')


def test_polish_captures_serve_the_required_fields_without_secret_keys():
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key not in {'privateKey', 'apiKey', 'secret', 'accessToken', 'password'}
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    bodies = {name: json.loads((ROOT / f'{name}.json').read_text()) for name in CAPTURES}
    for body in bodies.values():
        walk(body)
    for name in CAPTURES[:3]:
        assert bodies[name]['submissions']
        assert any(str(row.get('seat', {}).get('tokenId')) == '420'
                   for row in bodies[name]['submissions'])
        assert all({'hash', 'summary', 'usage'} <= row.keys() for row in bodies[name]['submissions'])
    assert any(runtime.get('premiumModel') for worker in bodies['workers']['workers']
               for runtime in worker.get('runtimes', []))
    assert any(skill.get('record') for skill in bodies['skills']['skills'])
    assert any(skill.get('inference') for skill in bodies['skills']['skills'])
    assert isinstance(bodies['health']['status'], str)
    hostile = json.loads((ROOT / 'submissions_hostile.json').read_text())['submissions'][0]['summary']
    assert '[/x]' in hostile and '/Users/' in hostile and 'x' * 500 in hostile
