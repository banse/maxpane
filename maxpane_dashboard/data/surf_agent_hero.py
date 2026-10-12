"""Twelve AGENT rack facts from existing independent reads; no I/O or clock."""
from maxpane_dashboard.analytics.surf_launch_checks import address
from maxpane_dashboard.analytics.surf_swarm_signals import runtime_outdated, daemon_differs
from maxpane_dashboard.analytics.surfboard import count, number, ratio, seat_token
from maxpane_dashboard.data import surfboard_activity as activity_history
from maxpane_dashboard.data.surf_models import SURF_AGENT_HERO_FIELDS
from maxpane_dashboard.data.surf_news_hero import _stamp
from maxpane_dashboard.data.surf_pool4_hero import _facts, _source


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _text(value):
    return value if isinstance(value, str) else None


def _positive(value):
    return count(value) or None


def _detail_source(data, sources, now):
    source = _source(sources, 'seat', now)
    state = data.get('swarm_seat_state')
    if state in ('pending', 'busy'):
        return dict(state=state, read_ts=None)
    if state == 'unknown_seat' and source['state'] in ('ok', 'stale'):
        return dict(source, state='stale_unknown_seat' if source['state'] == 'stale' else 'unknown_seat')
    return source if state == 'ok' else dict(source, state='unavailable')


def _detail_facts(source, **values):
    if source['state'] not in ('ok', 'partial', 'stale'):
        return dict(source, **dict.fromkeys(values))
    return _facts(source, **values)


def _listed(source, row):
    if source['state'] == 'unavailable':
        return None
    listed = row.get('listed')
    if listed is True:
        return True
    return False if listed is False and source['state'] != 'partial' else None


def _rows(value, fields):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        return None
    return [{name: validate(row.get(name)) for name, validate in fields.items()} for row in value]


def _runtime(data, summary, detail, sources, now):
    result = _detail_facts(detail, runtime=_text(summary.get('runtime')),
                          daemon=_text(summary.get('daemon')), devices=count(summary.get('devices')))
    result.update(update_state=None, latest_version=None, checked_ts=None, fleet_daemon=None,
                  fleet_count=None, fleet_total=None, daemon_differs=None)
    if detail['state'] not in ('ok', 'partial', 'stale'):
        return result
    runtime_id, _, version = (result['runtime'] or '').partition(' ')
    checks = _mapping(sources.get('runtime'))
    raw_check = _mapping(checks.get(runtime_id))
    check = _source(checks, runtime_id, now)
    latest = _mapping(data.get('swarm_runtime_latest'))
    newest = _text(latest.get(runtime_id))
    outdated = runtime_outdated(runtime_id, version, newest)
    if runtime_id not in ('claude', 'codex'):
        update = 'not_checked'
    elif raw_check.get('state') == 'pending' or runtime_id not in latest:
        update = 'pending'
    elif check['state'] != 'ok' or outdated is None:
        update = 'unavailable'
    else:
        update = 'outdated' if outdated else 'current'
    result.update(update_state=update, latest_version=newest, checked_ts=check['read_ts'])
    majority = data.get('swarm_fleet_daemon')
    workers = _source(sources, 'workers', now)
    if (workers['state'] == 'ok' and not _mapping(sources.get('workers')).get('partial')
            and isinstance(majority, (tuple, list)) and len(majority) == 3
            and count(majority[1]) is not None and count(majority[2]) is not None):
        result.update(fleet_daemon=_text(majority[0]), fleet_count=majority[1], fleet_total=majority[2],
                      daemon_differs=daemon_differs(result['daemon'], majority))
    return result


def _status(data, summary, detail, workers, sources, token, now, activity):
    live = _mapping(data.get('swarm_seat_live'))
    incomplete = _mapping(sources.get('workers')).get('partial') is True
    state = live.get('live_state')
    state = state if state in ('working', 'idle', 'paused', 'offline') else None
    if incomplete and state == 'offline':
        state = None
    result = _facts(workers, live_state=state,
                    working=None if incomplete else count(live.get('working')),
                    capacity=None if incomplete else count(live.get('max_concurrency')),
                    devices=None if incomplete else count(live.get('devices')))
    result.update(paused_until_ts=number(live.get('paused_until_ts')) if workers['state'] != 'unavailable' else None,
                  failures=count(live.get('failures')) if workers['state'] != 'unavailable' else None)
    chronology = _detail_facts(detail, worked=_stamp(summary.get('last_worked_ts'), now),
                               accepted=_stamp(summary.get('last_won_ts'), now))
    newest = max(((stamp, kind) for kind, stamp in (('worked', chronology['worked']),
                  ('accepted', chronology['accepted'])) if stamp is not None), default=(None, None))
    result.update(last_work_ts=newest[0], last_work_kind=newest[1], work_state=detail['state'],
                  work_read_ts=detail['read_ts'])
    observed = activity_history.project(activity, token, now=now)
    meter = activity_history.meter(observed, result['live_state'], now=now)
    if result['live_state'] == 'paused' and workers['state'] in ('ok', 'partial'):
        meter.update(meter_state='paused', numerator=None)
    result.update(meter)
    return result


def project(*, data: dict, sources: dict, now: float, activity=None) -> dict:
    """Manager owns selected detail identity; canonical outcomes are checked here too."""
    selected = _mapping(data.get('swarm_seat_selected'))
    token = seat_token(selected.get('token_id'))
    if token is None:
        return {name: dict.fromkeys(fields) | {'state': 'empty'}
                for name, fields in SURF_AGENT_HERO_FIELDS.items()}
    detail = _detail_source(data, sources, now)
    summary = _mapping(data.get('swarm_seat_summary'))
    seat = dict(detail, token_id=token, selected_by=_text(selected.get('selected_by')),
                read_error=data.get('swarm_seat_read') if data.get('swarm_seat_read') in ('busy', 'failed') else None)
    records, contributors, workers = (_source(sources, key, now) for key in ('records', 'contributors', 'workers'))
    outcome = _mapping(data.get('swarm_seat_outcome'))
    if seat_token(outcome.get('token_id')) != token:
        outcome = {}
    listed = _listed(records, outcome)
    accepted, attempts = (count(outcome.get(key)) if listed else None for key in ('accepted', 'attempts'))
    if accepted is not None and attempts is not None and accepted > attempts:
        accepted = None
    acceptance = (_facts(records, listed=listed, accepted=accepted, attempts=attempts) if listed is not False
                  else dict(records, listed=False, accepted=None, attempts=None))
    fraction = ratio(accepted, attempts)
    acceptance['percent'] = 100 * fraction if fraction is not None else None
    rank = (_facts(records, listed=listed, rank=_positive(outcome.get('rank')), ranked_of=count(outcome.get('ranked_of')))
            if listed else dict(records, state=records['state'] if listed is False else 'unavailable',
                                 listed=listed, rank=None, ranked_of=count(outcome.get('ranked_of')) if listed is False else None))
    delta = data.get('swarm_seat_rank_delta')
    rank['delta'] = delta if type(delta) is int and rank['rank'] is not None else None
    contrib = _mapping(data.get('swarm_seat_contrib'))
    listed = _listed(contributors, contrib)
    seconds = number(contrib.get('wall_clock_s')) if listed else None
    effort = (_facts(contributors, listed=listed, hours=seconds / 3600 if seconds is not None else None,
                     output_tokens=count(contrib.get('output_tokens')) if listed else None) if listed is not False
              else dict(contributors, listed=False, hours=None, output_tokens=None))
    reward_source = _source(sources, 'rewards', now)
    if detail['state'] not in ('ok', 'partial', 'stale'):
        reward_source = detail
    elif data.get('swarm_seat_rewards_state') == 'pending':
        reward_source = dict(state='pending', read_ts=None)
    elif detail['state'] == 'stale' and reward_source['state'] != 'unavailable':
        reward_source = dict(reward_source, state='stale')
    reward = _mapping(data.get('swarm_seat_rewards'))
    reward_facts = _detail_facts(reward_source, imd=number(reward.get('imd')), seats=_positive(reward.get('seats')))
    market = _source(sources, 'market', now)
    usd = _facts(market, usd=number(reward.get('usd')) if reward_facts['imd'] is not None else None)
    if reward_facts['state'] == 'stale' and usd['usd'] is not None:
        usd['state'] = 'stale'
    rewards = dict(state=reward_facts['state'], read_ts=reward_facts['read_ts'], imd=reward_facts['imd'],
                   usd=usd['usd'], seats=reward_facts['seats'], usd_state=usd['state'], usd_read_ts=usd['read_ts'])
    owner = _detail_facts(detail, address=address(summary.get('owner')), paired_ts=_stamp(summary.get('paired_ts'), now))
    owner = dict(state=owner['state'], read_ts=owner['read_ts'], address=owner['address'],
                 name=_text(data.get('swarm_seat_owner_ens')) if owner['address'] is not None else None, paired_ts=owner['paired_ts'])
    reviews = _mapping(summary.get('review_status'))
    return dict(seat=seat, accepted=acceptance, effort=effort, rewards=rewards, rank=rank,
        status=_status(data, summary, detail, workers, sources, token, now, activity), owner=owner,
        runtime=_runtime(data, summary, detail, sources, now),
        models=_detail_facts(detail, rows=_rows(summary.get('models'), dict(model=_text, effort=_text))),
        feedback=_detail_facts(detail, **{key: count(reviews.get(key)) for key in ('sent', 'submitted', 'queued')}),
        collab=_detail_facts(detail, count=count(summary.get('collaborators')),
            rows=_rows(data.get('swarm_seat_teammates'), dict(token_id=seat_token, shared_jobs=count))),
        nodes=_detail_facts(detail, rows=_rows(data.get('swarm_seat_node_rows'), dict(node_key=_text, accepted=count, attempts=count))))
