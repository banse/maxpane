# AGENT card labels and current action

Approved scope: the AGENT dashboard only. This is Tier 2 because the hero contract gains one field. Expected production change is comfortably below 1,000 lines; one final review, without package reviews.

## Requested presentation

- SEAT: inner `IDMD` becomes `AGENT`; the existing idle/paused online caption becomes `ONLINE`; outer `AGENT #id` becomes `ERC-8004 #id`. Preserve the seat digit and identifier value. Working/offline behavior stays unchanged.
- STATUS: when working, replace `active` with the current job node's short action: `oracling`, `auditing`, `reviewing`, `building`, `manifesting`, `researching`, `testing`, `designing`, `frontending`, or `implementing`.
- Clear the outer footer text of OWNER, MODELS, and NODES in every source state, including unknown/missing. Preserve their inner state captions, values, link/copy actions, colors, borders, and card dimensions.
- Put exactly one blank terminal row between the RECORD title/hints and table header. Preserve the existing title wording and filters.

## Current-action source and contract

Add `current_action: str | None` to `SURF_AGENT_HERO_FIELDS['status']`. Values are one of the ten approved action words; `None` means no current node could be established. Existing status fields keep their meanings.

Use the existing `SLOT_SWARM` live snapshot, captured synchronously with the other hero inputs. `SurfManager.fetch_and_compute` already offers `_spawn_swarm` independently of the visible body. `_pool_swarm` reads `/health`, the recent `/jobs` list, and details for executing jobs on the existing 60-second tier. Thus direct AGENT entry does not depend on previously visiting WIP or boardroom. Do not add endpoints, polling loops, or job-history fanout.

Select only nodes with `state == 'working'`, within a detail whose job is `executing` and belongs to the snapshot's current executing job list, whose `seat.tokenId` matches the selected seat. Use all matching nodes, not `inflight_rows`, which reduces a job to one node and can hide parallel workers. Require a fresh successful swarm read and fresh complete workers data confirming that the selected seat is working. Failed, expired, malformed, mismatched, or missing inputs produce `None`; never resurrect an action from retained history.

If multiple matching nodes are working, use the newest valid `updatedAt`; break ties deterministically by job ID then node key. Prefer timestamped nodes over undated ones; deterministic ordering may select a working node when all matching nodes lack a timestamp. Reject invalid/future timestamps for ordering. A confirmed working node does not need a recent node-update timestamp: long-running nodes can remain unchanged while their containing snapshot is freshly read.

`/seats/{token}.work[]` describes submitted attempts, so `jobState == executing` or submission status `pending` there is not evidence that the seat is currently working on that node. `/workers` provides working counts, not node assignments. Neither source may supply a guessed action. Older jobs outside the existing recent window may have no current detail; display the honest fallback `working` instead of expanding this task into a historical discovery change.

## Action mapping

Normalize node keys case-insensitively into underscore/hyphen/space-separated words; numbered suffixes do not change an action. Match explicit categories in this precedence, before falling back to the role:

| Node category | Caption |
| --- | --- |
| oracle | oracling |
| audit | auditing |
| review (including adversarial review) | reviewing |
| manifest | manifesting |
| research | researching |
| test/tests/testing | testing |
| design | designing |
| frontend | frontending |
| build | building |
| implement | implementing |

Specific categories precede generic `build`/`implement` so `build_frontend` is `frontending` and `build_contract_project_4` is `building`; `audit_review` is `auditing`. Recognize ordinary grammatical forms of these category words without arbitrary substring matching. If the key gives no category, an explicit recognized role may supply it. An unknown role/key leaves `current_action` unset. The UI uses `working` when the live working count is positive but `current_action` is unset, and retains existing idle/offline/paused captions.

## Verification and boundaries

Tests remain offline. Verify all ten mappings, precedence, multiple nodes, selected-seat isolation, refresh/removal, stale/failed sources, and direct AGENT use without WIP data. Compositor tests verify the requested text, cleared footers, retained inner content, and exactly one blank row. Render live keyless at 149×45 before final layout measurement, pin/document hardening, or review. Measure AGENT in situ with `scripts/measure_layout.py`; change a pin only if measured, never by adding one to the old value.

Source references: `data/surf_agent_hero.py::_status`, `data/surf_manager.py::_agent_hero_capture` / `_agent_hero` / `_pool_swarm`, `data/surf_swarm.py::seat_work_rows` / `normalize_workers`, `widgets/surf/agent_rack_hero.py::agent_records`, and `widgets/surf/swarm_seat_record.py`'s title-margin override.
