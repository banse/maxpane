# Launch contribution: model, effort, and build/review columns

Approved by the owner, 2026-10-14. Tier 2: extends the nested leaderboard row
contract across data and rendering. Estimated implementation: under 400 new or
changed production lines; under 1,000 total. Disjoint data and UI packages run
in parallel, without package reviews; one final whole-change review follows
integration and the live preview.

## Outcome and scope

The launch leaderboard shows each contributing seat's current advertised model
and reasoning effort alongside its historical build/review contribution split.
This helps compare what seats contribute and how their workers are configured.
Current settings are explicitly distinguished from models actually used in past
jobs. The existing ranking remains by distinct contributing jobs across all
live production launch history, excluding testnet launches.

Success: the three added columns render at the owner's 149×45 terminal; source
fixtures prove accurate role attribution and current model association, including
seats absent from the recorded ranking. No new endpoint or per-seat request is
introduced. Existing complete rankings remain visible during cache migration,
background refresh, and temporary API failures.

## Frozen row contract

The existing top-level `swarm_launch_contribution` envelope and its loading,
coverage, timestamp, and failure meanings stay unchanged. Its `rows` entries:

| Field | Type | Meaning |
|---|---|---|
| `rank` | int | Existing descending distinct-job rank, numeric seat tie-break |
| `token_id` | int | Seat identity |
| `jobs` | int | Distinct accepted, non-oracle contributing jobs |
| `launches` | int | Distinct live production launches contributed to |
| `build_jobs` | int or None | Distinct jobs with an accepted build role for this seat |
| `review_jobs` | int or None | Distinct jobs with an accepted review role for this seat |
| `advertised_models` | list of pairs or None | Current settings joined by the manager |

Each advertised pair is exactly `{"model": str, "effort": str | None}`.
Pairs are unique and sorted by model then effort (missing effort sorts as an
empty string). `None` means no valid worker source; `[]` means a valid roster
supplies no advertised pair for this seat. Both paint an explicit unknown value.

The reader persists only the historical fields. The manager adds
`advertised_models` from the existing `SLOT_SWARM_WORKERS` payload validated with
`coerce_workers_slot`, grouped directly by `token_id`. This join must not depend
on the recorded leaderboard containing the seat. Both
`get_launch_contribution_snapshot()` and `_project_hub()` use the same projection
path. Do not mutate cached worker payloads, reader rows, or retained snapshots.

Build/review attribution uses the API's `nodes[].role`, not node-key heuristics:

- BUILD: `implement`, `integrate`, `test`, `tests`.
- REVIEW: `review`.
- Only nodes already eligible for the existing jobs count participate.
- Multiple nodes of one role on one job count once per seat and role. A seat
  doing both roles on the same job increments both counts; their sum may exceed
  `jobs`. Repeated job references across launches are deduplicated per role.
- A missing or unknown accepted role preserves the seat's jobs/launches and
  makes both aggregate split counts unknown for that seat. This conservative
  fallback must not fail the whole ranking or report unverified zeros.
- A known split may have a genuine zero. Counts are nonnegative integers,
  excluding bool, and cannot exceed `jobs` individually.

Legacy persisted snapshot rows remain readable, receiving unknown split values.
Legacy job facts without role evidence become due for the existing bounded
reader; retain the last complete snapshot while roles are backfilled. A newly
read job with a genuinely missing role is valid evidence of unknown attribution
and must not trigger endless refetches. Preserve all existing retry, rate-limit,
cancellation, cache-bound, and association-validation behavior.

## UI behavior

Add columns keyed `model`, `effort`, and `build_review` to launch contribution.
Use existing `short_model()` for the model; show the first deterministic pair
with `+N` when additional pairs exist. Effort displays that same pair's effort,
or `—` if unspecified. Hover provides every complete model/effort pairing and
labels them as current advertised settings. Escape third-party strings normally.

BUILD / REVIEW displays `B / R` (or `— / —` when unknown). Hover explains that
counts are distinct contributing jobs and can overlap. Model and effort sort by
the primary pair's corresponding text; split sorts by numeric
`(build_jobs, review_jobs)`. Missing values remain last in either direction.
Keep existing selection, seat opening, independent tab sort/cursor/scroll, and
recorded-table behavior.

Fit the added fields using the existing table ladder and honest short forms.
At narrow tiers, anything omitted or clipped must light the existing widen
indicator; no silently hidden field. Measure the full BOARD body, not a detached
widget, and preserve the current 143×35 pin if measurement supports it. Pin or
CSS changes belong to the controller after the live preview, not parallel owners.

## Work packages and ownership

| Package | Owner | Files | Dependency |
|---|---|---|---|
| Data and contract | Data implementer | `data/surf_launch_contribution.py`, `data/surf_manager.py`, `data/surf_models.py`; `tests/data/test_surf_launch_contribution.py`, `tests/data/test_surf_launch_contribution_manager.py`; `tests/fixtures/surf/launch_contribution/captured.json` | Frozen contract above |
| Table presentation | UI implementer | `widgets/surf/swarm_leaderboard.py`; `tests/widgets/test_surf_swarm_leaderboard.py` | Frozen contract; tests may supply rows directly |
| Integration, preview, layout, review | Controller | Composing tests, layout tests/constants/CSS only if required; followups documentation | Both packages complete |

Paths in the ownership table are under `maxpane_dashboard/` unless they start
with `tests/`. One owner per file; report cross-package defects to the controller.
Both implementers are sharing the worktree and must preserve others' changes.
No new endpoint, full suite, unrelated formatting, or extra feature belongs here.

## Validation and completion sequence

1. Each implementer starts with focused failing tests, makes the smallest change,
   then reruns the touched behavior and composing checks. Restore captured
   `role` fields from original public payloads, never from guesses about keys:
   `/tmp/launch-contribution-job-0.json`,
   `/tmp/launch-contribution-workflow-contract-job.json`, and
   `/tmp/launch-contribution-workflow-frontend-job.json`.
2. Data tests cover role deduplication/overlap, unknown roles, old snapshot/fact
   migration, production-only ranking, model pairing across devices, seats
   absent from recorded rows, unavailable workers, both manager projection paths,
   and no mutation/network access. Keep existing loader lifecycle tests green.
3. UI tests assert composited model/effort/split output, explicit unknowns,
   multiple-pair hover, safe text, sorting, and unchanged tab identity/selection.
   Prove decoder and migration assertions bite with targeted inverse-restored
   mutations; a role-mapping or old-cache mutation must go red.
4. Controller renders the working change keylessly with live data at 149×45 and
   shows the owner before layout hardening or review. Reuse the launch cache and
   existing worker source; do not fetch submission histories.
5. After the live preview, measure in situ using `scripts/measure_layout.py` and
   certify relevant boundary cases around BOARD's 143×35 pin, plus 149×45.
   Update pin commentary only if measurements require it. Verify changed UI with
   `tests/screens/test_surf_launch_contribution.py` and the BOARD composing/layout
   cases; no full-suite run.
6. Run touched/composing files once as prescribed by `CLAUDE.md`, fast non-mount
   guards, and relevant doc pins. One final review covers the complete diff,
   at most one fix wave and scoped production re-review. File Minor residuals
   in `docs/surf_swarm_followups.md`, record evidence, then locally commit.
