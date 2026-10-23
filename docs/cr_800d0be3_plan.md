# CR 800d0be3: AGENT, BOARDROOM, NFT and WORK corrections

Status: implementation and scoped final review complete; batch claimed by controller. Nine notes are
grouped into four work packages. Tier 2 because several dashboards and the shared
flat-data contract change. Target: fewer than 1,000 changed production lines; one
final review, no package reviews. No new service, endpoint pool or background
scheduler is needed.

## Scope and interpretation

The controller read the batch with `python -m change_requests ... read` and owns
completion/archiving. Queue submission is not completion. Existing uncommitted or
untracked work remains outside this batch. The changes are keyless and read-only;
failed or incomplete reads must not become fabricated zeros.

Two implementation options were considered. A new aggregate reader could supply
all four views, but adds cache lifetime and ownership complexity. The chosen
approach extends each existing pure projection and its bounded reader only where
the requested semantics require additional evidence. Existing cache-first paint,
view ownership, cancellation, rate limits and polling remain in force.

### AGENT: four notes

* `nodes` becomes **LAUNCHES / JOBS**; `models` becomes **ORACLE / JOBS**. The
  number is distinct jobs in that category, not accepted submissions or node
  attempts. The inner footer is the percentage of those same jobs with accepted
  work by the selected seat. Multiple nodes/retries in one job count once; any
  accepted contribution makes that job accepted. Do not silently use the global
  receipt acceptance rate as the category rate.
* Preserve the user's earlier exclusion of testnets. Launch classification needs
  existing explicit production-chain launch evidence; oracle classification needs
  the request's explicit chain. Missing classification or missing outcome remains
  unknown. A proven empty set displays zero jobs and an undefined percentage,
  rather than 100% or an invented zero-percent success rate.
* Runtime changes must clear old warning state when a runtime becomes current or
  a different seat is selected. Audit current/outdated/pending/unavailable and
  daemon-majority disagreement using independently dated sources. Keep the current
  model/effort presentation unless a bug requires correction.
* OWNER text links to `https://explorer.imd.fun/wallet/<address>`, while the copy
  action still copies the actual wallet. Use the existing address/explorer
  helpers. Scope this explicit owner override to the AGENT owner card; update
  address-link expectations, do not globally redirect all Ethereum addresses.

Source map: `data/surf_agent_work.py:accepted_rows/candidates/oracle_candidates/
record_candidates/summarize` currently classify accepted work only.
`data/surf_agent_hero.py:project/_runtime` builds the card facts.
`widgets/surf/agent_rack_hero.py:agent_records/AgentRackCard` is the current rack
renderer; the similarly named legacy `swarm_agent_cards.py` is not the target.
`data/surf_manager.py:_spawn_runtime_latest/_read_runtime_latest` owns refreshes.

### BOARDROOM: three notes

* TOKENS displays the latest three launched production tokens, newest first,
  independent of their volume or whether they launched within 24 hours. Reuse
  the canonical launch cohort in `SwarmTokensManager._ranking_summary()['latest']`; the current rack
  consumes `token_ranking`, which represents a different ranking. Preserve token
  identity and stable tie ordering. Keep the turnover meter's own meaning.
* WIP outer footer displays the count of running original workflows, including
  `0 workflows` for a proven empty set. Its existing working-job/node text must
  display `0 working` when the evidence establishes there are none. Unknown
  coverage remains a dash: the request says zero **when none**, not on outage.
* The current WIP outer footer is the SWARM 24H sparkline, because
  `SurfboardRack.update_data()` swaps `footer_data` between `work` and `swarm`.
  Move that sparkline to BUILT BY SWARM and remove that card's current build/review
  footer. Do not move the wrong footer by reading the data keys in isolation.
* SIGNALS uses the existing detector states, not announcement reply counts.
  Render the count before the label (`0 SIGNALS`, `3 SIGNALS`) and retain the
  existing meter if it fits. A zero requires all detectors known; partial detector
  coverage cannot certify no active signals. Validate known/fired counts and
  preserve independent source times.

Source map: `data/surfboard.py:cards` owns cards and detector counts;
`widgets/surfboard/rack.py:signal_meter_text/_work_footer/meter_text/
SurfboardCard/SurfboardRack.update_data` owns the footer wiring and rendering.
`data/swarm_tokens_manager.py:catalogue_summary` already exposes newest rows.

### NFT: one note

Trace fresh discovery end-to-end: fresh source head -> candidate extraction ->
bounded inspection -> retained evidence -> published rows. Discovery currently
rotates at most four source pages per advance with a five-minute head TTL;
`SurfNftManager` polls at 30 seconds and guards its single active cycle. Investigate
the actual cause before reducing TTLs or increasing budgets. A new launch arriving
after a completed initial scan must eventually become a displayed verified NFT,
even with historical tails and inspection backlog. Do not restart full history
every poll or permanently prioritize the selected old collection.

For duplicate display, select a representative only when the normalized name and
the same direct launch-job request IDs and verified deployment sender match
(and chain identity matches). The owner clarified “same oracle” to “same job
request AND same deployer” during implementation. Choose the most minted,
then the newest deployment as a tie-breaker. Missing provenance preserves both
collections. This is representative selection, not a claim that a hidden
collection is illegitimate. No name-only exclusion list or legitimacy score.

Prefer the common normalized projection for representative selection so hero
counts, the table and BOARDROOM NFT totals agree. Representative selection must
not prevent explicit identity inspection or erase retained evidence. Sources and
README selection must follow the selected representative's identity.

Source map: `data/surf_nft_discovery.py:advance/_accept_page/_ingest`;
`data/surf_nft_manager.py:_offer/_cycle/_discover/_publish/get_snapshot`;
`data/surf_nft_rules/catalog.py:project_catalog`;
`analytics/surf_nft.py:normalize_record/select_rows/project_snapshot`.

### WORK: one note

An original workflow is open only while its own lifecycle is active. Completed,
cancelled, failed, superseded, paused and blocked workflows must not reappear as
open because a continuation runs. Keep paused/blocked state inspectable through
the appropriate existing view/filter; retain historical context without making
it active. Follow-up jobs appear as normal JOBS independently of the finished
workflow and must not disappear because their IDs occur in project history.

`widgets/surf/work.py:flow_view` currently treats open as merely not blocked.
Its global `linked_jobs` also removes jobs from JOBS even when their parent should
not be rendered. Fix membership and visibility together. Derive summary workflow
counts from the same lifecycle rule. Refresh known nonterminal original workflow
records when needed; retaining an old page indefinitely cannot prove it remains
open. Preserve bounded scans and failure-retained last-good data.

Swap existing running and completed colors in this view: `_tone` currently maps
accepted/completed to the accent and working/executing to green. Keep failures
red and pending/unknown distinct. Do not change network states or other views.

Source map: `data/surf_work.py:_workflow/snapshot/project`;
`data/surf_work_reader.py` for page/context refresh;
`widgets/surf/work.py:_tone/SurfWorkBody._rebuild`.

## Ownership, contracts and sequence

1. **Controller: BOARDROOM and shared integration.** Own
   `data/surf_models.py`, `data/surf_manager.py`, `data/surf_swarm.py`,
   `data/surf_swarm_hero.py`, `data/surfboard.py`,
   `data/swarm_tokens_manager.py`, `widgets/surfboard/rack.py`, shared address
   helper changes if needed, global docs/guards and final integration tests.
2. **AGENT implementer.** Own `data/surf_agent_work.py`,
   `data/surf_agent_hero.py`, `widgets/surf/agent_rack_hero.py` and their dedicated
   tests/fixtures. Send exact new contract fields and manager call-site changes to
   controller before depending on them. Do not edit shared seams.
3. **NFT implementer.** Own NFT discovery/manager/cache/model/rules modules,
   `analytics/surf_nft.py`, NFT widget changes only if needed, and dedicated NFT
   tests/fixtures. Escalate changes to generic `surf_models.py` or manager routing
   to controller. Never modify external aidude or IMDB sources.
4. **WORK implementer.** Own `data/surf_work.py`, `data/surf_work_reader.py`,
   `widgets/surf/work.py`, and their dedicated tests/fixtures. Share the lifecycle
   rule and any contract change with controller; do not edit shared seams.

The architecture planner owns this file only. Implementers are not alone in the
checkout and may not revert another package. Freeze the AGENT contract additions
before integrating rendering. The NFT and WORK packages can run independently;
the controller integrates BOARDROOM zero semantics after WORK's summary rule is
settled. Reuse one lifecycle definition at the existing data boundary rather than
adding competing UI and manager classifications.

## Validation and completion

Use focused failing regressions first, then the smallest fix. Tests inject
transports and use committed fixtures; no test accesses the network. Essential
cases include mixed outcomes and duplicate attempts per job; testnet exclusions;
unknown chain/outcome; runtime warning reset; OWNER link plus copy payload; newest
token ordering with old/high-volume tokens; empty versus unread work; partial
signals; new NFT after terminal history; no polling overlap; duplicate names with
different/missing job requests and deployers; equal/unknown mint counts; finished workflow plus an
executing follow-up; paused workflow; preservation of ordinary job visibility.

Run each touched behavior while editing. Before commit, run touched files plus
their composing screen/manager files once with isolated HOME and four worksteal
workers; run the fast guard and doc-pin sets. Include address sweeps for OWNER.
Use `scripts/mutate.py` for changed decoder/concurrency behavior and any moved
layout pin. No full suite and no registration mount sweep unless keys or other
registration surfaces change.

Before layout hardening or final review, show keyless live renders of BOARDROOM,
AGENT, NFT and WORK at the owner's known terminal size. Read the terminal-layout
skill if geometry changes; use existing measuring/render helpers and inspect
composited output. Live rendering is separate from the network-free test suite.
Record any upstream partial coverage rather than promising completeness.

One whole-diff final review after integration; one fix wave and scoped re-review
only if production fixes are needed. File Minor findings in followups. Commit
only this batch, then complete/archive it with the real commit and actual test
and live-render evidence. Do not close while any of the nine intents remains
unimplemented or unverified.
