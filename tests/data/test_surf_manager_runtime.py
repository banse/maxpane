"""Package TTLs, persisted validation and fleet reuse; all clients are network-dead."""
import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from maxpane_dashboard.data import surf_swarm as sw
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_WORKERS, SLOT_SWARM_RUNTIME_LATEST
from tests.data.test_surf_manager import FakeClock, NOW
from tests.data.test_surf_manager_swarm import _FakeSwarm, _manager, _seated, _settle
from tests.surf_swarm_fixtures import swarm_seat_capture, swarm_capture_v3


class FakeNpm:
    def __init__(self):
        self.calls = Counter()
        self.versions = {runtime: json.loads((Path(__file__).parents[1] / 'fixtures' / 'surf' / 'npm' /
                          f'{runtime}_latest.json').read_text())['version'] for runtime in ('claude', 'codex')}

    async def fetch_latest(self, runtime):
        self.calls[runtime] += 1
        return self.versions[runtime]

    async def close(self):
        pass


def seats():
    first = copy.deepcopy(swarm_seat_capture('seat_420'))
    first['runtimes'] = [{'id':'claude', 'version':'2.1.278 (Claude Code)'},
                         {'id':'codex', 'version':'codex-cli 0.155.1'},
                         {'id':'unknown', 'version':'1.0.0'}]
    second = {**copy.deepcopy(first), 'tokenId':'421'}
    return {420:first, 421:second}


async def refresh(manager):
    data = await manager.fetch_and_compute()
    await _settle(manager)
    return data


async def test_npm_package_ttl_survives_seat_switch_and_restart(tmp_path):
    clock, npm = FakeClock(NOW), FakeNpm()
    manager, _ = await _seated(tmp_path, _FakeSwarm(seats=seats()), seat=420, clock=clock, npm_client=npm)
    try:
        assert not npm.calls
        manager.set_agent_active(True)
        await refresh(manager)
        assert npm.calls == {'claude':1, 'codex':1}
        data = await refresh(manager)
        assert data['swarm_runtime_latest'] == npm.versions
        assert set(data['swarm_runtime_as_of_hhmm']) == {'claude', 'codex'}
        manager.set_seat(421)
        await refresh(manager); await refresh(manager)
        clock.advance(3599)
        await refresh(manager)
        assert npm.calls == {'claude':1, 'codex':1}
    finally:
        await manager.close()
    restarted_npm = FakeNpm()
    restarted = _manager(tmp_path, _FakeSwarm(seats=seats()), seat=421, clock=clock, npm_client=restarted_npm)
    try:
        restarted.set_agent_active(True)
        await refresh(restarted); await refresh(restarted)
        assert not restarted_npm.calls
        clock.advance(1)
        await refresh(restarted)
        assert restarted_npm.calls == {'claude':1, 'codex':1}
    finally:
        await restarted.close()


async def test_npm_failure_replaces_old_check_and_waits_for_ttl(tmp_path):
    clock, npm = FakeClock(NOW), FakeNpm()
    manager, _ = await _seated(tmp_path, _FakeSwarm(seats=seats()), seat=420, clock=clock, npm_client=npm)
    try:
        manager.set_agent_active(True)
        await refresh(manager)
        npm.versions = {'claude':None, 'codex':None}
        clock.advance(3600)
        await refresh(manager)
        data = await refresh(manager)
        assert data['swarm_runtime_latest'] == {'claude':None, 'codex':None}
        assert npm.calls == {'claude':2, 'codex':2}
        manager.set_agent_active(False)
        clock.advance(3600)
        await refresh(manager)
        assert npm.calls == {'claude':2, 'codex':2}
    finally:
        await manager.close()


async def test_unknown_runtime_and_no_selected_seat_never_request_npm(tmp_path):
    npm = FakeNpm()
    payloads = seats(); payloads[420]['runtimes'] = [{'id':'unknown', 'version':'1.0.0'}]
    manager, _ = await _seated(tmp_path, _FakeSwarm(seats=payloads), seat=420, npm_client=npm)
    try:
        manager.set_agent_active(True)
        await refresh(manager)
        assert not npm.calls
        manager._spawn_runtime_latest(None, None, NOW)
        assert not npm.calls
    finally:
        await manager.close()


async def test_runtime_cache_load_drops_bad_points_independently(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm(), npm_client=FakeNpm())
    manager.cache.store_last_good(SLOT_SWARM_RUNTIME_LATEST, {
        'claude': {'version':'2.1.281', 'checked_ts':NOW},
        'codex': {'version':'[/x]', 'checked_ts':NOW},
        'unknown': {'version':'1.0.0', 'checked_ts':NOW},
    }, ts=NOW)
    await manager.close()
    restored = _manager(tmp_path, _FakeSwarm(), npm_client=FakeNpm())
    try:
        assert restored.cache.get_last_good(SLOT_SWARM_RUNTIME_LATEST).payload == {
            'claude': {'version':'2.1.281', 'checked_ts':NOW}}
    finally:
        await restored.close()


async def test_fleet_majority_reuses_workers_slot_and_tie_is_unknown(tmp_path):
    manager = _manager(tmp_path, _FakeSwarm(), npm_client=FakeNpm())
    raw = swarm_capture_v3('workers')
    workers = copy.deepcopy(raw['workers'][:2])
    workers[0]['daemonVersion'], workers[1]['daemonVersion'] = '0.1.0+abc', '0.1.0+def'
    try:
        for expected, version in [(None, '0.1.0+def'), (('0.1.0+abc',2,2),'0.1.0+abc')]:
            workers[1]['daemonVersion'] = version
            manager.cache.store_last_good(SLOT_SWARM_WORKERS, sw.normalize_workers({'workers':workers}), ts=NOW)
            data = manager._swarm_board_keys(None, manager.cache.get_last_good(SLOT_SWARM_WORKERS), 420)
            assert data['swarm_fleet_daemon'] == expected
        assert not manager.swarm_client.calls
    finally:
        await manager.close()


async def test_new_seat_reads_only_its_new_package_inside_other_package_ttl(tmp_path):
    npm = FakeNpm()
    payloads = seats()
    payloads[420]['runtimes'] = payloads[420]['runtimes'][:1]
    payloads[421]['runtimes'] = payloads[421]['runtimes'][1:2]
    manager, _ = await _seated(tmp_path, _FakeSwarm(seats=payloads), seat=420, npm_client=npm)
    try:
        manager.set_agent_active(True)
        await refresh(manager)
        assert npm.calls == {'claude':1}
        manager.set_seat(421)
        await refresh(manager); await refresh(manager)
        assert npm.calls == {'claude':1, 'codex':1}
    finally:
        await manager.close()


@pytest.mark.parametrize('stamp', [None, True, 'x', -1, float('nan'), float('inf'), NOW + 1, 10**1000])
def test_runtime_cache_timestamp_validation_preserves_valid_siblings(stamp):
    from maxpane_dashboard.data.surf_runtime import coerce_runtime_slot
    good = {'version':'2.1.281', 'checked_ts':NOW}
    assert coerce_runtime_slot({'claude':good, 'codex':{'version':'0.156.1', 'checked_ts':stamp}}, now=NOW) == {'claude':good}
