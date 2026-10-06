"""Pure production-site joins; requester-written addresses need payer trust."""
import re
from maxpane_dashboard.analytics.surf_launch_checks import address, mappings, is_production

_OBJECTIVE_ADDRESS = re.compile(r'(?<![0-9a-fA-F])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])', re.I)

def site_job_facts(job):
    project = job.get('project') or {}
    objective = job.get('objective')
    return {
        'paid_by': address(job.get('paidBy')),
        'project_jobs': list(dict.fromkeys(v['jobId'] for v in mappings(project.get('versions')) if isinstance(v.get('jobId'), str)))[:100],
        'addresses': list(dict.fromkeys(x.lower() for x in _OBJECTIVE_ADDRESS.findall(objective if isinstance(objective, str) else '')))[:100],
    }

def match_sites(sites, launches, jobs, workflows):
    """Return unique first-method matches; ambiguity never chooses a launch."""
    out = {}
    for site in sites:
        candidates = []
        job = jobs.get(site.get('id'), {})
        for launch_id, facts in launches.items():
            row = facts.get('row', {})
            if not is_production(row):
                continue
            ids = set(facts.get('job_ids', []))
            method, trusted = None, True
            if any(w.get('frontendJobId') == site.get('jobId') and w.get('contractsJobId') in ids for w in mappings(workflows)):
                method = 'workflow'
            elif ids.intersection(job.get('project_jobs', [])):
                method = 'project'
            else:
                tokens = [address(a.get('address')) for a in mappings(row.get('artifacts')) if a.get('role') == 'token']
                if any(t and t in job.get('addresses', []) for t in tokens):
                    method = 'named'
                    trusted = bool(facts.get('requester') and job.get('paid_by') == facts['requester'])
            if method:
                candidates.append({'launch_id': launch_id, 'method': method, 'trusted': trusted})
        if len(candidates) == 1:
            out[site['id']] = candidates[0]
    return out
