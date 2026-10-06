import copy
from tests.analytics.test_surf_launch_checks import fixture
from maxpane_dashboard.analytics import surf_launch_sites as ls
from maxpane_dashboard.analytics.surf_launch_checks import extract_facts

def test_v8_zto_named_trust_and_conflict():
    launch = fixture('launch_737'); facts = extract_facts(launch)
    facts['row'] = launch
    sites = fixture('sites')['sites']
    site = next(s for s in sites if s['label'] == 'zto')
    job = ls.site_job_facts(fixture('job_zto_site'))
    links = ls.match_sites([site], {launch['id']: facts}, {site['id']: job}, [])
    assert links[site['id']] == {'launch_id': launch['id'], 'method': 'named', 'trusted': True}
    job['paid_by'] = '0x' + '1' * 40
    assert ls.match_sites([site], {launch['id']: facts}, {site['id']: job}, [])[site['id']]['trusted'] is False
    other = copy.deepcopy(facts); other['row']['id'] = 'other'
    assert ls.match_sites([site], {launch['id']: facts, 'other': other}, {site['id']: job}, []) == {}

def test_v8_workflow_project_and_sepolia_are_distinct():
    sites = fixture('sites')['sites']; workflows = fixture('workflows_100')['workflows']
    launch = fixture('launch_737'); facts = extract_facts(launch); facts['row'] = launch
    genesis = next(s for s in sites if s['label'] == 'genesis')
    flow = next(w for w in workflows if w.get('frontendJobId') == genesis['jobId'])
    facts['job_ids'] = [flow['contractsJobId']]
    assert ls.match_sites([genesis], {launch['id']: facts}, {}, workflows)[genesis['id']]['method'] == 'workflow'
    adam = next(s for s in sites if s['label'] == 'adam')
    job = ls.site_job_facts(fixture('job_adam_site'))
    facts['job_ids'] = job['project_jobs']
    assert ls.match_sites([adam], {launch['id']: facts}, {adam['id']: job}, [])[adam['id']]['method'] == 'project'
    facts['row']['chainId'] = 11155111
    assert ls.match_sites([adam], {launch['id']: facts}, {adam['id']: job}, []) == {}
