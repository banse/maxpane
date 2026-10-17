"""Persisted NFT evidence is bounded and keeps its original observation clocks."""
import json

from maxpane_dashboard.data.surf_nft_cache import SurfNftCache


def evidence(address='0x' + '1' * 40, stamp=100):
    return {'chainId': 1, 'address': address, 'checkedAt': stamp,
            'readTimestamp': '1970-01-01T00:01:40Z', 'readBlock': 123,
            'codePresent': True, 'standard': 'ERC-721'}


def test_round_trip_keeps_evidence_clock_and_resumable_progress(tmp_path):
    path = tmp_path / 'nft.json'
    key = '1:0x' + '1' * 40
    cache = SurfNftCache(path=path, clock=lambda: 200)
    from maxpane_dashboard.data.surf_nft_discovery import empty_discovery_state
    discovery = empty_discovery_state()
    discovery['sources']['launches'].update(tail_cursor=13, head_at=100)
    state = {'discovery': discovery,
             'evidence': {key: evidence()},
             'progress': {key: {'started_at': 100, 'cursor': 12}},
             'records': None}
    cache.save(state)
    loaded = SurfNftCache(path=path, clock=lambda: 300).load()
    assert loaded['evidence'][key] == evidence()
    assert loaded['progress'][key]['cursor'] == 12
    assert loaded['discovery']['sources']['launches']['tail_cursor'] == 13
    assert loaded['records'] is None


def test_invalid_evidence_row_does_not_discard_valid_neighbor(tmp_path):
    path = tmp_path / 'nft.json'
    good, bad = '1:0x' + '1' * 40, '1:0x' + '2' * 40
    path.write_text(json.dumps({'version': 1, 'saved_at': 200,
        'evidence': {good: evidence(), bad: evidence('0x' + '3' * 40)},
        'progress': {}, 'discovery': {}, 'records': None}))
    loaded = SurfNftCache(path=path, clock=lambda: 300).load()
    assert list(loaded['evidence']) == [good]
    assert loaded['cache_partial'] is True


def test_future_source_observation_and_nonfinite_values_are_not_retained(tmp_path):
    path = tmp_path / 'nft.json'
    key = '1:0x' + '1' * 40
    state = {'evidence': {key: evidence(stamp=301)}, 'discovery': {},
             'progress': {}, 'records': None}
    cache = SurfNftCache(path=path, clock=lambda: 300)
    cache.save(state)
    assert cache.load()['evidence'] == {}
    state['evidence'][key]['checkedAt'] = float('nan')
    cache.save(state)
    assert cache.load()['evidence'] == {}


def test_limits_keep_selected_stage_and_qualify_truncation(tmp_path, monkeypatch):
    monkeypatch.setattr(SurfNftCache, 'MAX_STAGES', 1)
    monkeypatch.setattr(SurfNftCache, 'MAX_STAGE_BYTES', 100)
    a, b, c = ('1:0x' + digit * 40 for digit in '123')
    state = {'progress': {a: {'started_at': 100}, b: {'started_at': 101},
                           c: {'started_at': 102, 'large': 'x' * 101}}}
    cache = SurfNftCache(path=tmp_path / 'nft.json', clock=lambda: 200)
    cache.save(state, selected_id=a)
    loaded = cache.load()
    assert list(loaded['progress']) == [a]
    assert loaded['cache_partial'] is True


def test_oversized_input_is_rejected_before_json_parse(tmp_path, monkeypatch):
    path = tmp_path / 'nft.json'
    path.write_text(' ' * 101)
    monkeypatch.setattr(SurfNftCache, 'MAX_BYTES', 100)
    monkeypatch.setattr(json, 'loads', lambda *_a, **_kw: (_ for _ in ()).throw(
        AssertionError('oversize file parsed')))
    assert SurfNftCache(path=path, clock=lambda: 200).load()['records'] is None


def test_failed_atomic_replace_preserves_old_file(tmp_path, monkeypatch):
    path = tmp_path / 'nft.json'
    cache = SurfNftCache(path=path, clock=lambda: 200)
    cache.save({'records': []})
    old = path.read_bytes()
    def fail(*_a):
        raise OSError('disk full')
    monkeypatch.setattr('maxpane_dashboard.data.surf_nft_cache.os.replace', fail)
    assert cache.save({'records': None}) is False
    assert path.read_bytes() == old
    assert list(tmp_path.iterdir()) == [path]


def test_byte_limit_evicts_old_facts_and_persists_selected_progress(tmp_path):
    from maxpane_dashboard.data.surf_nft_discovery import empty_discovery_state
    cache = SurfNftCache(path=tmp_path / 'nft.json', clock=lambda: 3000)
    key = '1:0x' + '1' * 40
    discovery = empty_discovery_state()
    discovery['sources']['publications'].update(head_at=100, tail_cursor=21)
    discovery['raw']['publications'] = [
        dict(id=f'{index:08x}-aaaa-4aaa-8aaa-aaaaaaaaaaaa', title='x' * 9000,
             _observed_at=index + 1) for index in range(2000)]
    state = dict(discovery=discovery, evidence={key: evidence()},
                 progress={key: dict(started_at=100, completed_operations=12)})
    prepared = cache.prepare(state, selected_id=key)
    assert prepared['cache_partial'] is True
    assert prepared['discovery']['truncated'] is True
    assert len(prepared['discovery']['raw']['publications']) < 2000
    observations = [row['_observed_at'] for row in prepared['discovery']['raw']['publications']]
    assert max(observations) == 2000 and min(observations) > 1
    assert cache.save(prepared, selected_id=key)
    assert cache.path.stat().st_size <= cache.MAX_BYTES
    loaded = cache.load()
    assert loaded['evidence'][key] == evidence()
    assert loaded['progress'][key]['completed_operations'] == 12
    assert loaded['discovery']['sources']['publications']['tail_cursor'] == 21
