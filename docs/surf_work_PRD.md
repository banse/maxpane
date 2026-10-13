# PRD — WORK IN PROGRESS

Status: proposal 2 and mock data approved by the owner, 2026-10-13.
Tier 2: one new Surf body with a new data contract and detached source tier.

## 1. Approved scope

The request is “design a new dashboard for work in progress. jobs being
worked on” and “and workflows”. The selected design is a workflow tree at
left, selected work details at right, and six rack hero cards above both.

| Outer title | Inner title | Value | Footer meaning |
|---|---|---|---|
| JOBS | ACTIVE | Executing loaded jobs | executing |
| WORKFLOWS | ACTIVE | Active loaded workflows | in progress |
| SEATS | WORKING | Distinct assigned seats on working nodes | assigned seats |
| BUILD | STEPS | Working build/test/integration nodes | building |
| REVIEW | STEPS | Working review nodes | reviewing |
| BLOCKED | JOBS | Loaded jobs whose state is blocked | needs attention |

Use equal existing rack cards, black inner boxes, gray labels, green active
work, orange waiting and red blocked states. Unknown values use an em dash.
All summaries are explicitly scoped to loaded records. No estimated percent
complete, ETA, new transaction behavior or work submission is included.

## 2. Navigation and interaction

- `w` toggles `MODE_WORK = "work"` in Surf. The boardroom's `w` shortcut opens
  this same body through existing Surf routing and return context.
- No new app dashboard, number, `--game` value or game-select registry entry.
- One `SurfWorkHero` and one `SurfWorkBody` are composed once and toggled with
  the mode; both receive only the `surf_work` keyword.
- The left WORK TREE nests workflow → contracts/frontend job → step. A job
  linked twice can appear twice but is counted once. OTHER JOBS groups
  unfinished jobs without a displayed workflow parent.
- Default tree includes nonterminal workflows, including blocked workflows.
  Completed/cancelled/superseded/failed workflows remain hidden unless they
  provide context for a known executing job. Loaded terminal job siblings can
  remain under a displayed workflow as useful dependency context.
- Default selection is the newest executing job, ordered by update timestamp,
  creation timestamp and stable id; else newest unfinished workflow, else a
  remaining visible job. Do not select an empty group when useful work exists.
- Up/down selects; left/right collapses/expands. Selecting a row updates the
  detail pane immediately. Enter opens the selected record's local detail;
  job explorer links use the existing helpers rather than an invented URL.
- `/` focuses a local find input. Match objective, id, step key and seat text;
  matching descendants retain their parent path. Search triggers no API call.
- `f` cycles all → build → review → blocked. Build/review match working nodes
  in those roles; blocked matches blocked jobs/workflows and their context.
  Filter the tree, never the hero counts. Surf's existing AGENT `f` behavior
  stays unchanged through mode-aware screen dispatch.
- `r` requests the existing guarded refresh path. Esc closes an open find
  editor first, then uses normal one-way back/boardroom return semantics.
- Preserve a selected stable id, expansion and filter through refresh. If
  the selected item leaves the bounded snapshot, pick the next useful default
  and discard its obsolete detail. Never leave an old detail beside a new row.

## 3. Selected record details

Workflow: objective, status, creation/update age, both linked jobs, failure
and hosting wait when the API reports it.

Job: objective, id/template/state, creation/update age, blocker, all loaded
step rows with seat/state/update, latest dispatch note and related jobs.

Step: key, role/state, seat, attempt/revisions, dependencies, update age,
dispatch note and its age, failure and verdict. Unknown values stay unknown;
a missing detail says so explicitly. Accepted outcomes are real step states.

The tree and detail pane scroll independently and use all available body
height. At 149×45 the design must show the six equal heroes and both panes.
Width/height pins are measured after the live preview, never copied from a
sibling. Shorter/narrower layouts retain reachable content and advertise
`‹ taller` / `‹ widen` where relevant rather than silently clipping.

## 4. Frozen payload contract

Export `surf_work` in `SURF_KEYS`; both widget signatures are exactly
`("surf_work",)`. Widgets receive primitives and never import `data/`.

```text
surf_work = {
  state: "ok" | "stale" | "unavailable",
  read_ts: float | None,
  now_ts: float,
  partial: bool,
  jobs_loaded: int | None,
  workflows_loaded: int | None,
  details_loaded: int | None,
  details_expected: int | None,
  summary: {jobs, workflows, seats, build, review, blocked},
  jobs: list[Job] | None,
  workflows: list[Workflow] | None
}
Job = {
  id, state, template, objective, created_ts, updated_ts, blocked_reason,
  detail_state: "ok" | "unavailable" | "not_loaded",
  nodes: list[Node] | None
}
Node = {
  key, role, state, seat, agent_id, attempt, revisions, depends_on,
  updated_ts, dispatch_note, dispatch_ts, failure, verdict
}
Workflow = {
  id, status, objective, failure, contracts_job_id, frontend_job_id,
  created_ts, updated_ts, waiting_for_hosting
}
```

IDs are validated strings. Other text fields are strings or None; times are
finite nonnegative numeric timestamps or None. `seat`, `attempt`, `revisions`
are nonnegative strict ints or None, never booleans. `depends_on` is a list of
strings or None. `waiting_for_hosting` is a strict bool or None. `verdict` is
None or normalized `{status: str|None, detail: str|None}`. Every summary value
is a nonnegative int or None. `now_ts` is injected by the manager; widgets do
not read a clock. Exact row-key constants belong in the existing `surf_models.py` contract module.

`jobs_loaded` and `workflows_loaded` describe the valid page rows, deduplicated
by id. `jobs` is the unique union of those job rows and successfully read
workflow-linked jobs; details override their older list fields. Missing
workflow references are represented by the workflow id field and a UI
placeholder, not a fabricated Job record. `details_expected` is the full
deduplicated candidate count before the cap; `details_loaded` counts valid
successful details. A malformed detail does not masquerade as an empty node
list. Counts are independent of the current UI filter.

### Count definitions

- `jobs`: unique known jobs with state `executing`.
- `blocked`: unique known jobs with state `blocked`, not inferred from prose.
- `workflows`: loaded nonempty statuses excluding `completed`, `cancelled`,
  `superseded`, `blocked` and `failed`. Unknown/missing status is not active.
- Only nodes of known executing jobs contribute to working-node counts.
  Their state must be exactly `working`; verdict does not establish activity.
- `seats`: unique valid seat ids on those working nodes.
- `build`: working nodes with role `implement`, `integrate`, `test` or `tests`.
- `review`: working nodes with role `review`.
- If any executing job lacks a readable node list, seats/build/review are
  unknown. A working node lacking a valid seat makes only seats unknown; an
  unknown working role makes build and review unknown. A genuine empty node
  list is readable. No executing jobs means known zero working counts.
- If the corresponding list has never been read, its count is None. Partial
  but readable pages produce observed counts and a visible loaded/partial
  qualification, never an unqualified global total.

## 5. Collection and trust boundary

The dedicated WorkReader uses existing `SwarmClient`, not a new HTTP stack.
`TIER_SURF_WORK` / `SLOT_SURF_WORK` have a 60-second TTL and 120-second
failure backoff. It runs only while WORK is active, detached through the
manager's lifecycle. It reads jobs limit 100 and workflows limit 100; it
never merges the scores tier's workflow history into current work.

Detail order: executing listed jobs first; references from unfinished,
nonblocked workflows next; blocked job/workflow context last. Deduplicate by
job id, cap 24 reads per cycle and make overflow explicit. Displayed missing
references remain visible as not loaded. Fresh detail facts supersede list
facts for the same id. Missing normal reads make coverage partial. All-host
busy stops fan-out, retains the prior whole snapshot and backs off.

Both list reads must succeed before replacing a snapshot. Any list failure
keeps last-good and its old read clock; no prior snapshot means unavailable.
The read timestamp is conservatively the start of successful collection;
stale means a failed latest attempt or more than 120 seconds old. Partial
means page cap, detail cap/missing, missing displayed workflow reference or
malformed rows discarded. These facts appear in the body's source/coverage
line and relevant hero/footer state without adding a global degraded group.

Validate persisted work snapshots as untrusted input. Render all remote text
using `Text` and existing sanitizers. Preserve literal brackets. Addresses
receive the repository's copy/explorer treatment; no guessed network link.
No wallet, secret, signing, transaction or write API is added.

## 6. Acceptance

The implementation must cover the approved workflow/job/step selection and
mock layout, accurate multiple-working-node counts, unavailable vs empty,
partial vs complete, failed refresh vs fresh read, stale workflow exclusion,
missing references/details, deduplication, guarded keyboard routing and
literal malicious-looking text. Tests never touch the network or clipboard.

The controller shows a live keyless 149×45 render before pin hardening,
registration documentation or final review. Only measured layout numbers enter
the `#:` block and terminal-layout table. Final checks are scoped; no full suite.
