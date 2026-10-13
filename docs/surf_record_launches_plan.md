# AGENT RECORD launch view

Status: implemented and verified 2026-10-14 for the owner's 2026-10-13 request; scoped final re-review approved. Evidence is in `surf_swarm_followups.md`.

## Scope and decision

Replace `not completed` with `launches`; show the exact hint `'i' to change seat · 'f' to filter records` wherever the complete hint fits. Add a LAUNCHES dropdown to the existing filter editor. Preserve the table columns, paging, selected-row behavior, stored-filter behavior and 40–400 row cap.

Use the existing validated job-membership source behind NODES. Raw work-row `launch` is only intent: seat 3 currently has 14 such labels but 9 confirmed launch jobs, while seat 7 has 3 labels and no confirmed launch jobs. Filtering raw labels would show incorrect results. Re-fetching details only for already-matching RECORD rows would instead starve unknown membership. Reuse the independently scheduled, bounded membership reader and its cache; join its result into every RECORD projection and read-window input.

This is a job-membership view, not an acceptance filter. A rejected or failed attempt belongs in `launches` when its job is confirmed launched; the STATE filter remains independent. Oracle records remain a separate work type, as in the existing NODES classification. Requested, deploying, parked or abandoned launches are not confirmed live launches.

## Frozen contract

- Add `launch_state` to `SURF_ROW_KEYS['swarm_seat_work_rows']`: `launched`, `not_launched`, `not_read`, or `unavailable`.
- `membership_point()` remains the sole decoder of confirmed launch membership: exact canonical job ID, served chain, live launch ID/status. Never infer membership from the raw launch-kind string, acceptance, job completion or a token name.
- Oracle rows are `not_launched`. For other rows, a retained validated membership point yields `launched`/`not_launched`; missing points are `not_read`, or `unavailable` following a failed read. Invalid job IDs are `unavailable`, not eternally pending. A failed membership refresh yields `unavailable` even when a last-good point exists; retain that point for recovery under the existing bounded retention rule, but count the read uncertainty instead of presenting its old membership as a fresh decision.
- Add `RecordFilter.launches: str = 'any'`, accepting only `any` and `launched`. It is a read-dependent filter, included in `reads_active` and filter summaries. LAUNCHES options are `Any` and `Launched jobs`.
- Rename `open_only`/`record_open_only` to `launches_only`/`record_launches_only` at the existing analytics, manager, widget and screen call surfaces. The title target is `screen.record_filter('launches')`. No compatibility alias for the obsolete incomplete-only mode is needed.
- `launches_only` and an applied `launches='launched'` use the same predicate. `all`/`launches` temporarily bypass but retain a stored custom filter; `filtered` applies that filter alone, matching current interaction behavior.
- NODE/STATE/WHEN base filtering precedes the cap. When launch filtering is active, exclude known `not_launched` rows before the cap, retain unknown candidates in the window, and show only confirmed matches after the cap. Unknown candidates increment existing `not_read`/`unavailable` counts. Other read-dependent groups still never narrow their own read window. Existing verdict precedence remains: definite nonmatch beats unknown.
- Manager answer, oracle and popup-detail read windows share a post-membership-read snapshot clock; those windows and widget rendering call the same pure window logic on the same membership-enriched row shape. An unread submission hash must not prevent discovering its job's launch membership.
- Membership discovery considers all canonical nonoracle job IDs from all attempt states, independent of RECORD mode, filters and cap. Keep NODES/EARNINGS accepted-only counts unchanged: use a separate discovery candidate helper or explicit optional discovery mode rather than silently broadening accepted-work candidates. Preserve the existing 64-job batch/four-read concurrency and unknown-first fairness.

## UI

Keep the filter editor's four columns and two grid rows. Stack LAUNCHES below WHEN in its existing group so STATE/NODE lists and MODEL remain unchanged. Include LAUNCHES in the note explaining unknown reads. The launches tab uses the existing unknown-count footer; only a fully resolved empty view says `no matching records`. Do not report emptiness while reads are outstanding.

## Work packages and ownership

Estimated production diff: under 350 lines, certainly under 1,000. One final review only; no package reviews.

1. **Data package — root:** owns `data/surf_models.py`, `data/surf_swarm.py`, `data/surf_agent_work.py`, `data/surf_agent_card_sources.py`, `data/surf_manager.py` and their data tests. Freeze the new row key, add membership projection/discovery, preserve accepted-work summaries, feed identical enrichment to all manager windows and rendered rows, and rename manager view state. TDD on decoding/discovery and window integration.
2. **View/filter package — one worker or root:** owns `analytics/surf_record_filter.py`, `widgets/surf/swarm_seat_record.py`, `widgets/surf/swarm_record_filter.py`, `screens/surf.py`, and their analytics/widget/screen tests. Implement the frozen contract, title/hint, editor control, launch view/footer and mode resets. It can run in parallel with package 1 against the contract above. The worker must not edit manager/model files.
3. **Integration — root after both:** run focused composing checks, render live at the owner's 149×45 terminal size and show it before hardening/docs/review, update `.claude/rules/surf.md` and the existing RECORD filter specification to the final behavior. Own all shared docs and any integration fixes; report another owner's defect rather than editing concurrently.

## Verification and completion

- `tests/data/test_surf_agent_work.py` and `test_surf_agent_card_sources.py`: requested vs live vs parked; exact ID/chain validation; rejected-attempt discovery; deduplicated jobs; NODES accepted-only totals unchanged; unread and failed outcomes; discovery independent of view.
- `tests/analytics/test_surf_record_filter.py`: launch tab equals launch filter; known negatives before cap; unknowns counted, never shown; invalid filter values; independent STATE combinations including rejected launched work; more/older counts; no circular submission-read predicate.
- `tests/widgets/test_surf_swarm_seat_record.py` and `test_surf_swarm_record_filter.py`: composited hint, tab, empty/unknown footers, launch dropdown, round-trip/apply/reset and retained choices.
- Relevant manager tests plus `tests/screens/test_surf_swarm_screen.py`: click launches, apply the launch filter, more, return all, seat change/reset; identical answer/detail/oracle selection; membership resolving across refresh makes previously unknown rows appear.
- Focused existing `test_the_record_filter_editor_fits_and_reaches_every_control` in `tests/screens/test_surf_swarm_layout.py`: ninth control stays reachable without a ninth grid cell; no pin change unless live evidence requires one.
- Use `scripts/mutate.py` on confirmed-membership decoding, unknown retention and selected read-window agreement. Named tests must fail for each mutant; restore by inverse edit.
- Before commit run touched test files and composing files once, fast non-mounting guards, applicable docpins; no full suite. One final review under the repository contract, fix limits as Tier 2, file Minor residuals in the existing followups document. Commit locally; no push.
