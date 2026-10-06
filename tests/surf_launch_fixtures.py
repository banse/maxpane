"""Shared v8-derived production launches for widget and screen tests."""
from maxpane_dashboard.analytics.surf_launch_checks import extract_facts, is_production, verdict
from maxpane_dashboard.data.surf_swarm import launch_rows
from tests.analytics.test_surf_launch_checks import checked, fixture


def launch_row(number=737, **overrides):
    raw = fixture(f'launch_{number}') if number in (734, 737, 747) else next(
        row for row in fixture('launches_100')['launches'] if row['launchNumber'] == number)
    row = launch_rows([raw])[0]
    facts = extract_facts(raw)
    row.update({key: value for key, value in facts.items() if key in row})
    row['production'] = is_production(raw)
    row['token_address'] = next((a['address'] for a in row['artifacts'] if a['role']=='token'), None)
    row['job_id'] = next(iter(facts.get('job_ids') or []), None)
    if number in (734, 737, 747):
        _, _, checks = checked(number)
        row.update(checks=checks, verdict=verdict(raw, checks))
    row.update(overrides)
    return row


def launch_event(capture_number=737, **overrides):
    row = launch_row(capture_number)
    check = row['verdict'] or {}
    event = dict(launch_id=row['launch_id'], number=row['launch_number'], status=row['status'],
                 ticker=row['ticker'], chain_id=row['chain_id'], token_address=row['token_address'],
                 verdict_state=check.get('state'), verdict_passed=check.get('passed'),
                 verdict_failed=check.get('failed'))
    event.update(overrides)
    return event
