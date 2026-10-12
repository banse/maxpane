# SWARM live hero integration — proposal 2

## Approved scope

The owner approved the proposal 2 Textual mockup (“no looks all good”). Connect
its six equipment cards to existing SWARM data: FLEET, OUTPUT, WORKFLOWS, LAUNCHES,
LATEST WORKFLOW and SITES. Preserve the approved ordering, equal nine-row cards,
grey casings, dark insets, aligned lists, preview and native Digits. The live
preview target is **149 columns × 45 rows**.

This is Tier 2: new production widget and payload contract, fewer than 1,000
production lines overall, one final review and no package reviews. KISS: one
primitive dictionary, one mode-specific hero and existing clients/caches. No new
endpoint, client, poller, credentials or configuration writes. Superpowers remain
disabled. Keep the four native SWARM body panels and other dashboard heroes intact.

The root explicitly approved one scheduling extension: native SWARM visibility
may enable the existing hourly accepted-step source, with its existing 60-second
cadence, cache, backoff and task deduplication. This is not a second chart fetch.

## Frozen primitive contract

Add `surf_swarm_hero` to the model key set. Its dictionary contains exactly
`fleet`, `output`, `workflows`, `launches`, `workflow` and `sites` sections.
Each section carries `state: "ok" | "stale" | "unavailable"` and
`read_ts: float | None` (UTC epoch of its successful source observation).
Register `SurfSwarmRackHero.update_data(*, surf_swarm_hero=None)` as the widget
signature. No cache objects, dataclasses, Rich objects or Textual objects cross
the seam; widgets never import data modules.

| Section | Additional fields |
| --- | --- |
| `fleet` | `online`, `working`, `enrolled`: nonnegative integers or `None` |
| `output` | `steps`, `jobs`, `oracles`: nonnegative integers or `None`; `points: list[number] | None`; `points_state`, `points_read_ts` |
| `workflows` | `total: int | None`; `statuses: list[{status: str, count: int}] | None` |
| `launches` | `total: int | None`; `statuses: list[{status: str, count: int}] | None` |
| `workflow` | `objective: str | None`, `age_s: float | None`, `status: str | None` |
| `sites` | `count: int | None` |

`points_state` uses the same state vocabulary; `points_read_ts` is an independent
UTC epoch. All numbers must be finite; booleans are not counts. `None` means
unavailable, zero is real, and successful empty lists remain distinguishable from
unread lists. An absent top-level payload renders six explicit unavailable cards.

FLEET uses online/working/enrolled from the captured overview. OUTPUT maps
`steps=accepted_24h`, `jobs=jobs_24h`, `oracles=oracles_24h`. Its chart is accepted
steps only, from the existing 24-hour series aggregated into three-hour buckets.
Do not infer throughput percentages or invent missing history points.

WORKFLOWS counts the cached workflow records by their actual status vocabulary.
LAUNCHES uses `swarm_launch_summary.by_status`, retaining the existing
production-only `launch_summary` filter. Preserve all valid status buckets in the
contract, sorted descending by count with a stable name tie-break. The renderer
shows the first three and the truthful `N cached` total, not a lifetime claim.
Preserve existing missing-status semantics: workflow total includes valid mapping
rows while blank/None status buckets are omitted; launch total sums valid existing
`by_status` counts. Never invent a status or relabel missing data running/completed.
When a populated cache has no readable status buckets, render `Status unavailable`,
not an empty-cache or zero claim.

LATEST WORKFLOW selects the newest valid, nonfuture `created_ts`, with workflow id
as a deterministic tie-break. Objective, age and footer status come from that same
record. Use an injected `now`; `updated_ts` must not select an older workflow just
because it changed recently. Empty cache displays “No workflows in cache”. A
nonempty list with no admissible timestamp makes the latest section unavailable.
A selected row's absent objective stays unavailable while retaining its real age
and status, with `Objective unavailable` in the preview. The footer safely formats
that status rather than a fixed RUNNING label.

SITES applies the existing current-site semantics exactly: a named `ens_name`, no
`superseded_by`, and status other than `superseded`. It counts current named
records, not verified website uptime. Reuse or hoist that pure predicate through
root coordination; do not import a widget into data or fork its semantics.

## Source versions, freshness and rendering

Capture values and observation clocks synchronously from the same cache versions.
Do not combine older `_cycle` rows with newly advanced detached-source timestamps
in `_project_hub`. Retained successful data stays visible behind stale markers;
projection time, event creation time and another source's success are not read time.
Observation and event timestamps must be finite, positive and no later than the
injected `now`; reject zero and future timestamps rather than treating them as fresh.

| Section | Source and clock |
| --- | --- |
| Fleet / output numbers | Existing `surfboard_sources.overview` envelope and its captured overview payload; reuse its state/read_ts and visibility-dependent cadence |
| Output chart | Existing `surfboard_sources.hourly` envelope and `surfboard_hourly.points`; independent state/read_ts, 60-second cadence |
| Workflows / latest workflow | `SLOT_SWARM_SCORES.payload.workflows` with its own `workflows_ts`; scores tier TTL (1,800 seconds), never the whole slot's newer timestamp |
| Launches | Captured `SLOT_SWARM_LAUNCHES` catalogue/facts projection and route-specific `launches_ts`; existing launch-tier cadence (60 seconds) and launch failure evidence |
| Sites | Same slot's site records and route-specific `sites_ts`; existing site cadence (300 seconds), independent of launch and policy reads |

Use current overview/hourly source envelopes, including retained last-good failure
states. Do not recreate their metadata from flat counts. Workflow failures can
retain `workflows_ts` while the enclosing scores slot advances; a newer scores
entry must not make that history fresh. An early scores-tier failure also retains
the prior successful observation. Keep launch/site status route-specific: failed
launch or policy work must not falsely stale a freshly observed site list, and a
new launch read must not refresh older site records.

OUTPUT's main `state/read_ts` follows the numeric overview only. Its hourly state
is independent: healthy points show `24H` plus the graph; missing chart data shows
`24H unavailable`; stale chart data shows `24H stale HH:MM` without plotting. A
stale main-card footer takes precedence. Never degrade fresh output numbers solely
because their optional chart failed. A successful all-zero chart is real data.

Other healthy footers retain the approved AGENTS/JOBS/DEPLOYMENTS/status/ENS labels.
Stale sections show a concise `stale HH:MM` footer and keep their real read clock
available in the tooltip. Unavailable fields stay explicit. Escape/flatten all
third-party status and objective text at the widget boundary.

## Work packages and ownership

1. **Planning agent:** only `docs/surf_swarm_hero_live_plan.md`; freeze the contract
   and communicate decisions. No production edits.
2. **Data owner:** `data/surf_models.py`, `data/surf_manager.py`, new pure
   `data/surf_swarm_hero.py`, and corresponding projection/manager tests. Declare
   the contract, project matched snapshots, preserve independent failures/clocks,
   and add `set_swarm_active(bool)` as eligibility only. Offer hourly when
   `_hub_active or _swarm_active`; supply stays hub-only. Reuse existing scheduling
   and cache deduplication. No awaiting network work from a message handler.
3. **Widget owner:** `widgets/surf/swarm_rack_hero.py`, its package export, and new
   widget tests. Adapt the frozen dictionary to the accepted card design. Reuse
   the existing rack renderer; coordinate with root before moving it into a
   neutral shared module or touching other owners' files. Preserve NEWS behavior.
4. **Root:** `screens/surf.py`, theme CSS, composing/contract tests, and measured
   pins/documentation as needed. Show the new hero only in MODE_SWARM; synchronize
   manager eligibility on mode entry, suspend and resume, refreshing on entry.
   Root owns any mock-demo adapter changes, live preview, integration and commit.

Paths under `data/`, `widgets/`, `screens/` and themes are relative to
`maxpane_dashboard/`; tests are under `tests/`. Data and widget work may proceed in
parallel after contract freeze. Root integration depends on both. Preserve others'
work and report cross-owner issues rather than editing another package.

## Verification and delivery

- Use focused failing tests before implementation. While editing, run only changed
  cases. Tests must never reach the network or real clipboard.
- Cover real zeros versus unread sources, empty lists, actual/unknown status
  buckets, production-only launches, superseded/unnamed sites, stable latest
  workflow selection and hostile/long text.
- Cover independent overview/hourly states, retained workflow failure timestamps,
  launch/site clock separation and cached projections after detached completions.
  Verify visibility toggles reuse the existing hourly task/cadence and disable its
  eligibility when neither SWARM nor the rack is visible.
- Assert composited values and actual geometry at 149×45: six equal nine-row cards,
  complete titles/footers, native site digits and unchanged contextual body panels.
  Verify mode switching preserves NEWS and all other heroes.
- When production renders, show a keyless live 149×45 preview to the owner before
  pin hardening, layout records or final review. Keep artifacts temporary and
  disclose unavailable/stale source data through the designed UI.
- After live corrections settle, measure the actual compositor in situ. Change
  pins only when measured evidence requires it; prove the relevant geometry and
  source/projection assertions bite with targeted reversible mutations.
- Before commit, run affected complete test files and composing files once with
  isolated HOME and `-n 4 --dist worksteal`, fast `guard and not mounts_app` checks
  and applicable docpins. No full suite without owner request.
- One independent final review, one fix wave, and one scoped re-review only if
  fixes touch production code. File Minor-only residuals via the existing process.

Complete SWARM's live-data confirmation before presenting the next dashboard's
three ASCII proposals in the owner's repeated mockup → API workflow.
