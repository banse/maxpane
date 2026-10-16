# WIP active project context

Approved by the owner on 2026-10-16: load full workflow context for active jobs,
including earlier jobs in the same project even without a formal parent workflow.
This extends the existing WIP body; it adds no dashboard, endpoint or layout pin.

## Behavior

Discover current executing jobs beyond the newest 100 records using the existing
job cursor and the overview's executing count as a scan hint. The API currently
ignores `state=executing`; do not rely on that query. Revalidate prior active IDs,
and never merge old executing statuses into a successful current snapshot.
Missing counts, failed/nonadvancing pages and bounds make coverage partial.
An incomplete search with no observed active jobs must not claim zero activity.

Read each executing job's full detail. Follow its served `project.versions` and
`workflow.id`, then read the referenced historical jobs and contracts/frontend
workflow relationships by ID. Age alone cannot exclude a referenced job. Use
direct, deduplicated reads instead of scanning historical job details indiscriminately.
Do not recursively expand unrelated projects discovered in historical records.
Retain complete node lists, including accepted and failed steps, within existing
node validation bounds. Only a fresh matching detail can establish current activity.

The tree groups active projects, optionally nests their formal workflows, and
shows all their job versions, including completed/blocked predecessors. Active
branches expand initially; historical job branches start collapsed and can be
opened. Each job appears once. Existing search/filter/selection/collapse behavior
and job/address links remain. Projects are not counted as formal workflows.
Historical blocked attempts must not inflate the current blocked-job count.

## Frozen public contract

Add `projects` to `SURF_WORK_FIELDS`: `None` before any usable snapshot, otherwise
a list. Existing Job, Workflow, Node and Summary field lists stay unchanged.
`SURF_WORK_PROJECT_FIELDS` is exactly:

```text
id: canonical UUID
objective: sanitized string or None
job_ids: ordered unique canonical job UUIDs, including the active seeds
workflow_ids: ordered unique canonical workflow UUIDs
active_job_ids: unique canonical UUIDs of freshly confirmed executing seeds
```

Admit a project relationship only from a valid executing job detail whose
project versions contain that job. Validate returned detail identities and
workflow membership. Version metadata can supply a job's reported name/state
when its detail cannot be read, but cannot supply working nodes or current
activity. Missing referenced records remain visible through their ID and partial
coverage; no fabricated records or completed/empty defaults.

Internal cache fields may record current-job scope and active-discovery coverage;
they must not leak into the exact public field contract. Validate persisted
relationships, deduplication, counters and bounded sizes. Legacy snapshots migrate
to empty projects with partial coverage until refreshed; no cache-version reset.

## Collection and verification

Keep the detached reader's visibility, single-flight, conservative read clock,
TTL and failure backoff. Bounded scans and detail fanout must report partial
coverage when capped: initial 100 recent jobs followed by pages of up to 500,
at most 100 discovery pages, 512 job details, 128 workflow details and 256
versions per project. Optional nonactive context retains its 24-read budget.
Busy/cancellation cannot publish a half-written snapshot;
required initial list failure retains the previous snapshot. Ordinary missing
context may publish usable active work with partial coverage.

Use offline regression tests before implementation: older active discovery,
multi-version projects, old terminal siblings, shared projects/workflows,
identity/membership errors, missing reads, cap, busy, cancellation, persistence,
and painted tree/selection/filters. Show a live keyless render at 149x45 before
final review. Run touched/composing files once, fast guards and required contract
or documentation checks. One final review for this bounded implementation; no
full repository suite. The implementation plan records package ownership.
