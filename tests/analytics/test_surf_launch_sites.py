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


def test_v8_unrelated_genesis_and_adam_do_not_claim_a_production_launch():
    launch = fixture('launch_737')
    facts = dict(extract_facts(launch), row=launch)
    sites = [s for s in fixture('sites')['sites'] if s['label'] in ('genesis', 'adam')]
    adam = next(s for s in sites if s['label'] == 'adam')
    jobs = {adam['id']: ls.site_job_facts(fixture('job_adam_site'))}
    assert ls.match_sites(sites, {launch['id']: facts}, jobs, fixture('workflows_100')['workflows']) == {}


def test_site_matching_500_launches_100_sites_1000_workflows_under_50ms():
    from time import perf_counter
    from uuid import UUID
    row = fixture('launch_737')
    base = dict(extract_facts(row), row=row)
    launches = {str(UUID(int=i+1)): dict(base, job_ids=[str(UUID(int=i+1001))]) for i in range(500)}
    template = fixture('sites')['sites'][0]
    sites = [dict(template, id=str(UUID(int=i+2001)), jobId=str(UUID(int=i+3001))) for i in range(100)]
    workflows = [dict(frontendJobId=str(UUID(int=i+3001)), contractsJobId=str(UUID(int=i+1001))) for i in range(1000)]
    start = perf_counter()
    links = ls.match_sites(sites, launches, {}, workflows)
    elapsed = perf_counter() - start
    assert len(links) == 100
    assert elapsed < .05, f'{elapsed:.6f}s'


def test_workflow_and_project_matches_to_different_launches_remain_ambiguous():
    from uuid import UUID
    row = fixture('launch_737')
    first = dict(extract_facts(row), row=row)
    second = copy.deepcopy(first)
    job_id = str(UUID(int=1234))
    second['job_ids'] = [job_id]
    site = fixture('sites')['sites'][0]
    workflows = [{'frontendJobId': site['jobId'], 'contractsJobId': first['job_ids'][0]}]
    jobs = {site['id']: {'project_jobs': [job_id]}}
    assert ls.match_sites([site], {row['id']: first, str(UUID(int=4321)): second}, jobs, workflows) == {}


def test_fix2_workflow_index_ignores_invalid_job_identifiers():
    launch=fixture('launch_737'); facts=dict(extract_facts(launch), row=launch)
    site=next(s for s in fixture('sites')['sites'] if s['label']=='genesis')
    flow=next(w for w in fixture('workflows_100')['workflows'] if w.get('frontendJobId')==site['jobId'])
    facts['job_ids']=[flow['contractsJobId']]
    malformed=[{'frontendJobId':[1],'contractsJobId':{}},
               {'frontendJobId':site['jobId'],'contractsJobId':'not-a-uuid'},
               {'frontendJobId':None,'contractsJobId':flow['contractsJobId']}]
    assert ls.match_sites([site], {launch['id']:facts}, {}, [flow]+malformed)==ls.match_sites([site], {launch['id']:facts}, {}, [flow])
    facts['job_ids']=['not-a-uuid']
    assert ls.match_sites([site], {launch['id']:facts}, {}, malformed)=={}


def test_fix2_site_memo_tracks_matching_inputs_only():
    launch = fixture('launch_737'); facts = dict(extract_facts(launch), row=launch)
    site = next(s for s in fixture('sites')['sites'] if s['label'] == 'zto')
    launches = {launch['id']: facts}; sites = [site]
    jobs = {site['id']: ls.site_job_facts(fixture('job_zto_site'))}
    workflows = fixture('workflows_100')['workflows']
    original = ls.site_match_key(sites, launches, jobs, workflows)
    assert len(original) == 64
    noisy = copy.deepcopy(launches)
    noisy[launch['id']].update(ticker='changed', checks={'K3': 'noise'}, detail_failed_ts=999)
    noisy[launch['id']]['row']['updatedAt'] = 'later'
    noisy[launch['id']]['job_ids'].reverse()
    noisy[launch['id']]['row']['artifacts'].reverse()
    assert ls.site_match_key(sites[::-1], noisy, jobs, workflows[::-1] + workflows) == original
    assert ls.site_match_key(sites, launches, jobs, workflows + [{'frontendJobId': [1], 'contractsJobId': {}}]) == original
    mutations = [
        lambda s,l,j,w: l.update({site['id']: l.pop(launch['id'])}),
        lambda s,l,j,w: l[launch['id']]['job_ids'].clear(),
        lambda s,l,j,w: l[launch['id']]['row'].update(status='abandoned'),
        lambda s,l,j,w: l[launch['id']]['row'].update(chainId=11155111),
        lambda s,l,j,w: l[launch['id']].update(requester='0x'+'1'*40),
        lambda s,l,j,w: next(a for a in l[launch['id']]['row']['artifacts'] if a['role']=='token').update(address='0x'+'1'*40),
        lambda s,l,j,w: s[0].update(jobId=workflows[0]['contractsJobId']),
        lambda s,l,j,w: s[0].update(id=launch['id']),
        lambda s,l,j,w: j[site['id']].update(paid_by='0x'+'1'*40),
        lambda s,l,j,w: j[site['id']]['project_jobs'].append(launch['id']),
        lambda s,l,j,w: j[site['id']]['addresses'].clear(),
        lambda s,l,j,w: w.append({'frontendJobId': site['jobId'], 'contractsJobId': launch['id']}),
    ]
    for mutate in mutations:
        args = copy.deepcopy((sites, launches, jobs, workflows)); mutate(*args)
        assert ls.site_match_key(*args) != original
