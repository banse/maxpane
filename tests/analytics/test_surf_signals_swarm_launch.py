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
