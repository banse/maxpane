from uuid import UUID
from copy import deepcopy
from maxpane_dashboard.analytics.surf_signals import build_signals, FIRED_TTL_S
from tests.surf_launch_fixtures import launch_event

NOW = 1791247200.


def cycle(base, events, now=NOW):
    return build_signals(base, {'swarm_launch_events': None if events is None else {'events': events, 'ts': now}}, now)


def test_swarm_seeds_silently_then_admitted_live_and_multiple_fire_once():
    a, b = launch_event(737, status='admitted'), launch_event(747)
    signals, base = cycle({}, [a])
    assert signals['sig_swarm_state'] == 'watch'
    a['status'] = 'live'
    signals, base = cycle(base, [a, b], NOW+10)
    assert signals['sig_swarm_state'] == 'fired'
    assert len(signals['swarm_launch_fired']) == 2
    assert '+1' in signals['sig_swarm_detail']
    assert '#747' in signals['sig_swarm_detail']
    signals, base = cycle(base, [a, b], NOW+20)
    assert signals['sig_swarm_age_s'] == 10
    assert all(row['ts'] == NOW+10 for row in signals['swarm_launch_fired'])


def test_swarm_restart_outage_ttl_and_no_refire(tmp_path):
    from maxpane_dashboard.data.surf_cache import SurfCache
    _, base = cycle({}, [])
    event = launch_event()
    _, base = cycle(base, [event])
    cache = SurfCache(path=str(tmp_path/'cache.json'), clock=lambda: NOW+20)
    cache.set_baselines(base, now=NOW+20); cache.save()
    other = SurfCache(path=cache.path, clock=lambda: NOW+30); other.load()
    signals, base = cycle(other.get_baselines(), None, NOW+30)
    assert signals['sig_swarm_state'] == 'fired' and signals['sig_swarm_age_s'] == 30
    assert signals['sig_swarm_chain_id'] == event['chain_id']
    signals, base = cycle(base, [event], NOW+FIRED_TTL_S)
    assert signals['sig_swarm_state'] == 'ok'
    assert signals['swarm_launch_fired'] == []


def test_swarm_600_seen_eviction_never_refires_and_pending_survives():
    pending = launch_event(status='admitted')
    _, base = cycle({}, [pending])
    events = [launch_event(launch_id=str(UUID(int=i+1)), number=1000+i) for i in range(600)]
    for batch in range(6):
        _, base = cycle(base, events[batch*100:(batch+1)*100], NOW+batch)
    assert len(base['swarm_live_seen']) == 500
    assert base['swarm_live_seen'][0] == events[100]['launch_id']
    signals, base = cycle(base, events[:100], NOW+FIRED_TTL_S+10)
    assert signals['sig_swarm_state'] == 'ok' and not signals['swarm_launch_fired']
    pending['status']='live'
    signals, _ = cycle(base, [pending], NOW+FIRED_TTL_S+20)
    assert signals['sig_swarm_state'] == 'fired'
    assert signals['swarm_launch_fired'][0]['launch_id'] == pending['launch_id']


def test_swarm_bad_read_or_seen_never_fires_and_first_live_read_is_silent():
    event = launch_event()
    signals, base = cycle({}, [event])
    assert signals['sig_swarm_state'] == 'ok'
    for bad in (None, {}, {'events':[{'launch_id':'bad'}], 'ts':NOW}):
        signals, advanced = build_signals(base, {'swarm_launch_events':bad}, NOW+1)
        assert signals['sig_swarm_state'] is None
        assert advanced['swarm_live_seen'] == base['swarm_live_seen']
    signals, _ = cycle({'swarm_live_seen':['invalid']}, [event])
    assert signals['sig_swarm_state'] is None


def test_swarm_non_live_production_transition_below_highwater_fires():
    pending=launch_event(status='reviewing')
    _, base=cycle({}, [pending,launch_event(747)])
    pending['status']='live'
    result, _=cycle(base,[pending],NOW+1)
    assert result['sig_swarm_state']=='fired'
    assert '#737' in result['sig_swarm_detail']


def test_swarm_lower_number_first_seen_live_fires_and_two_out_of_order_fire():
    high = launch_event(number=751)
    _, base = cycle({}, [high])
    lower = launch_event(747)
    other = launch_event(734)
    signals, advanced = cycle(base, [high, lower, other], NOW+1)
    assert {r['number'] for r in signals['swarm_launch_fired']} == {734, 747}
    assert advanced['swarm_launch_evicted_floor'] == 0


def test_swarm_eviction_floor_uses_evicted_numbers_not_observation_high(tmp_path):
    from maxpane_dashboard.data.surf_cache import SurfCache
    rows = [launch_event(launch_id=str(UUID(int=i+1)), number=1000+i) for i in range(500)]
    _, base = cycle({}, rows)
    late = launch_event(747)
    _, base = cycle(base, [late], NOW+1)
    assert base['swarm_launch_evicted_floor'] == 1000
    assert base['swarm_live_numbers'][late['launch_id']] == 747
    cache = SurfCache(path=str(tmp_path/'floor.json'), clock=lambda: NOW+2)
    cache.set_baselines(base, now=NOW+2); cache.save()
    cache.load()
    restored = cache.get_baselines()
    assert restored['swarm_launch_evicted_floor'] == 1000
    assert restored['swarm_live_numbers'] == base['swarm_live_numbers']
    assert restored['swarm_live_seen'] == base['swarm_live_seen']
    _, restored = cycle(restored, [launch_event(734)], NOW+3)
    assert restored['swarm_launch_evicted_floor'] == 1001


def test_swarm_legacy_highwater_does_not_become_an_eviction_floor():
    high = launch_event(number=751)
    base = {'swarm_live_seen': [high['launch_id']], 'swarm_launch_high_water': 751}
    signals, advanced = cycle(base, [high, launch_event(747)], NOW+1)
    assert signals['sig_swarm_state'] == 'fired'
    assert advanced['swarm_launch_evicted_floor'] == 0
    assert 'swarm_launch_high_water' not in advanced


def test_swarm_corrupt_seen_and_floor_remain_failed_after_cache_roundtrip(tmp_path):
    from maxpane_dashboard.data.surf_cache import SurfCache
    for key, invalid in [('swarm_live_seen', ['bad']), ('swarm_launch_evicted_floor', -1),
                         ('swarm_launch_evicted_floor', True), ('swarm_launch_evicted_floor', '751')]:
        cache = SurfCache(path=str(tmp_path/'corrupt.json'), clock=lambda: NOW)
        cache.set_baselines({key: invalid}, now=NOW); cache.save()
        cache.load()
        assert cache.get_baselines()[key] is None
        signals, recovered = cycle(cache.get_baselines(), [launch_event()])
        assert signals['sig_swarm_state'] is None
        signals, _ = cycle(recovered, [launch_event(), launch_event(747)], NOW+1)
        assert signals['sig_swarm_state'] == 'fired'


def test_fired_enrichment_keeps_original_clock_and_never_revives_expired():
    _, base = cycle({}, [])
    event = launch_event(ticker=None, token_address=None, verdict_state='partial', verdict_passed=1)
    _, base = cycle(base, [event], NOW+1)
    enriched = {**event, 'ticker': 'ZTO', 'token_address': launch_event()['token_address'], 'verdict_state': 'swarm', 'verdict_passed': 4}
    signals, base = cycle(base, [enriched], NOW+61)
    fired = signals['swarm_launch_fired'][0]
    assert fired['ts'] == NOW+1
    assert fired['ticker'] == 'ZTO' and fired['token_address'] == enriched['token_address']
    assert fired['verdict_state'] == 'swarm' and fired['verdict_passed'] == 4
    assert '✓' in signals['sig_swarm_detail']
    signals, _ = cycle(base, [enriched], NOW+1+FIRED_TTL_S)
    assert not signals['swarm_launch_fired']


def test_fix3_selected_launch_tracks_detector_watch_fired_and_unknown():
    old = launch_event(747); watch = launch_event(737, status='admitted', ticker='字'*120)
    _, base = cycle({}, [old])
    old['status'] = 'admitted'  # Already seen; must not displace the actual WATCH.
    signals, base = cycle(base, [old, watch], NOW+1)
    assert signals['sig_swarm_launch']['launch_id'] == watch['launch_id']
    assert signals['sig_swarm_launch']['number'] == 737
    signals, _ = cycle(base, None, NOW+2)
    assert signals['sig_swarm_launch'] is None
    watch['status'] = 'live'
    signals, base = cycle(base, [watch], NOW+3)
    assert signals['sig_swarm_launch']['number'] == 737
    assert signals['sig_swarm_launch']['extra_count'] == 0
    signals, _ = cycle(base, [watch], NOW+FIRED_TTL_S+4)
    assert signals['sig_swarm_launch'] is None
