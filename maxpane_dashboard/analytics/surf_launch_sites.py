"""Pure production-site joins; requester-written addresses need payer trust."""
import hashlib
import json
import re
from maxpane_dashboard.analytics.surf_ids import parse_job_id
from maxpane_dashboard.analytics.surf_launch_checks import address, mappings, is_production

_OBJECTIVE_ADDRESS = re.compile(r'(?<![0-9a-fA-F])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])', re.I)

def site_job_facts(job):
    project = job.get('project')
    if project is not None and not isinstance(project, dict):
        return None
    project = project or {}
    objective = job.get('objective')
    return {
        'paid_by': address(job.get('paidBy')),
        'project_jobs': list(dict.fromkeys(v['jobId'] for v in mappings(project.get('versions')) if isinstance(v.get('jobId'), str)))[:100],
        'addresses': list(dict.fromkeys(x.lower() for x in _OBJECTIVE_ADDRESS.findall(objective if isinstance(objective, str) else '')))[:100],
    }

def site_match_key(sites, launches, jobs, workflows):
    """Hash only join semantics; read clocks, order and bytecode are irrelevant."""
    launch_inputs = []
    for launch_id, facts in launches.items():
        row = facts.get('row', {})
        if is_production(row):
            tokens = {address(a.get('address')) for a in mappings(row.get('artifacts'))
                      if a.get('role') == 'token' and address(a.get('address'))}
            launch_inputs.append((launch_id, sorted(set(facts.get('job_ids', []))),
                                  sorted(tokens), facts.get('requester')))
    site_inputs = []
    for site in sites:
        job = jobs.get(site.get('id')) or {}
        site_inputs.append((site.get('id'), site.get('jobId'), job.get('paid_by'),
                            sorted(set(job.get('project_jobs', []))),
                            sorted(set(job.get('addresses', [])))))
    workflow_inputs = set()
    for row in mappings(workflows):
        frontend, contracts = parse_job_id(row.get('frontendJobId')), parse_job_id(row.get('contractsJobId'))
        if frontend is not None and contracts is not None:
            workflow_inputs.add((frontend, contracts))
    inputs = (sorted(launch_inputs), sorted(site_inputs), sorted(workflow_inputs))
    return hashlib.sha256(json.dumps(inputs, separators=(',', ':')).encode()).hexdigest()


def match_sites(sites, launches, jobs, workflows):
    """Index joins once; ambiguity across any methods never chooses a launch."""
    job_launches, token_launches, frontend_jobs = {}, {}, {}
    for launch_id, facts in launches.items():
        row = facts.get('row', {})
        if not is_production(row):
            continue
        for job_id in facts.get('job_ids', []):
            job_launches.setdefault(job_id, set()).add(launch_id)
        for artifact in mappings(row.get('artifacts')):
            token = address(artifact.get('address'))
            if artifact.get('role') == 'token' and token:
                token_launches.setdefault(token, set()).add(launch_id)
    for workflow in mappings(workflows):
        frontend = parse_job_id(workflow.get('frontendJobId'))
        contracts = parse_job_id(workflow.get('contractsJobId'))
        if frontend is not None and contracts is not None:
            frontend_jobs.setdefault(frontend, set()).update(job_launches.get(contracts, ()))
    out = {}
    for site in sites:
        job = jobs.get(site.get('id')) or {}
        candidates = {}
        for token in job.get('addresses', []):
            for launch_id in token_launches.get(token, ()):
                requester = launches[launch_id].get('requester')
                candidates[launch_id] = {'launch_id': launch_id, 'method': 'named',
                                        'trusted': bool(requester and job.get('paid_by') == requester)}
        for job_id in job.get('project_jobs', []):
            for launch_id in job_launches.get(job_id, ()):
                candidates[launch_id] = {'launch_id': launch_id, 'method': 'project', 'trusted': True}
        for launch_id in frontend_jobs.get(site.get('jobId'), ()):
            candidates[launch_id] = {'launch_id': launch_id, 'method': 'workflow', 'trusted': True}
        if len(candidates) == 1:
            out[site['id']] = next(iter(candidates.values()))
    return out
