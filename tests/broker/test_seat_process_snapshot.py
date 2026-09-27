"""The container kill snapshot reads metadata only, including every UID."""
import json
from pathlib import Path

import pytest

from imd_dashd.process_snapshot import snapshot
from tests.broker._harness import write_fake_proc


def test_snapshot_exact_identity_all_uids_and_no_command_bodies(tmp_path):
    fixture = Path('tests/fixtures/seat/broker/procs_orphan.json')
    spec = json.loads(fixture.read_text())
    write_fake_proc(tmp_path, spec)
    for path in tmp_path.glob('*/cmdline'):
        path.unlink()  # a metadata reader cannot require argv, credentials or task file bodies
    rows = snapshot(tmp_path, now=spec['now'], clk_tck=100)
    assert len(rows) == len(spec['procs'])
    assert any(r['uid'] == 0 for r in rows)
    assert all(set(r) == {'pid', 'ppid', 'pgid', 'uid', 'cgroup', 'start_ticks', 'age_s'} for r in rows)
    for row in rows:
        original = next(p for p in spec['procs'] if p['pid'] == row['pid'])
        assert row['start_ticks'] == original['start_ticks']
    first = tmp_path / str(rows[0]['pid']) / 'stat'
    first.write_text('unreadable format')
    with pytest.raises((ValueError, IndexError)):
        snapshot(tmp_path, now=spec['now'], clk_tck=100)
