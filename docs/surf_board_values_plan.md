# BOARD value emphasis and percentage footers

**Date:** 2026-10-15
**Status:** implemented and verified; scoped final re-review approved
**Tier:** 2 — hero contract additions and several data/widget/composing files
**Estimate:** below 1,000 production lines; one final review, no package reviews

## Intended outcome

BOARD makes numeric FLEET and RECEIPTS facts easier to scan and uses its LAUNCHES
and WORKERS footers for useful population shares. At the owner's **149 × 45**
terminal, the existing rack/body geometry and table interactions remain intact.
This follows `surf_board_refresh_plan.md` and overrides only the behavior below.
Use KISS and the existing primitive data → manager → rendering boundary; reuse
current keyless sources, caches and schedules. No new API is required.

## Approved behavior

| Surface | Change | Retained behavior |
|---|---|---|
| FLEET / RECEIPTS | Numeric counts and `+N` omission counts use the same green as leaderboard numeric values | Labels, names, model/version/effort text, separators, units and clocks remain neutral; existing bold emphasis and missing-value semantics remain |
| Paused group | Preserve existing alarm styling | A paused count remains red; `none` remains green; identifiers and clocks retain their existing semantics |
| LEADERBOARD title | Remove the visible widen hint at every width, including narrow layouts | Responsive table tiers, ellipses, complete hover details, tab clicks, sorting and selection remain |
| LAUNCHES footer | Replace the jobs total with contributor seats as a percentage of the RECORDED seat population | LAUNCHES rows remain seats / claude / codex; retained values and source details remain available |
| WORKERS footer | Replace `CURRENT` with `x% run <leading runtime>`, e.g. `x% run codex` | Live / working / capacity rows remain unchanged |

Apply color by semantic text spans, not by searching for digits: model versions,
effort names, OS versions, slot bucket names, seat identifiers and timestamps can
contain digits without being numeric counts. Receipt duration and token numerals
are green while their units remain neutral. Preserve full metadata and count
styling through clipping, compact formatting, omission fallback and tooltips.

The owner explicitly requested removal of LEADERBOARD's widen hint. This is a
documented exception to the normal marking convention in `CLAUDE.md` and the
terminal-layout skill, limited to that panel. Do not use absence of the hint as
proof that the table fits; layout validation must inspect columns and clipping.
Do not change other panels' widen/taller behavior.

## Data meanings and frozen seam

The data owner handles additions to `SURF_LEADERBOARD_HERO_FIELDS`, the pure
projection and manager capture; the controller handles hero rendering. Keep the existing
`surf_leaderboard_hero` signature and primitive-only payload. Append these frozen
fields to the existing sections:

```python
launches: ("percent", "total_seats", "records_state", "records_read_ts")
workers: ("runtime", "runtime_percent", "runtime_count", "runtime_total", "runtime_known")
```

Each new field is present on every update with `None` for unknown, separate from
a valid zero. Percentages use one decimal place with trailing `.0` trimmed:
LAUNCHES renders `68.3%`; WORKERS renders `52.4% run codex`.

**LAUNCHES share** is `100 × distinct launch-contributor seats / canonical
recorded seats`. Reuse the complete all-history production launch snapshot and
the canonical records population; do not substitute receipt devices, online
workers or attempt totals. Require complete `ok`/`stale` records, known launch
seat count, `0 <= numerator <= denominator` and a positive denominator.
Zero contributors with positive records is 0%; unread contributors,
unread records and 0/0 are unknown. Do not clamp an inconsistent relationship
into a plausible percentage. Capture and disclose the records source's state and
read time separately from the launch source. An independent read failure may
retain matching last-good facts but cannot freshen either population.

**WORKERS runtime share** uses distinct currently online seat IDs from the
captured worker roster, deduplicated across devices. Each seat votes at most once
per reported runtime; a seat advertising both claude and codex may vote once in
each. Divide the leading runtime's seat count by all distinct online seats,
not only seats with runtime metadata, and do not infer runtime from model names.
Missing/incomplete roster or zero online seats cannot produce a manufactured
percentage. Claim the leading runtime only with a complete roster and known
nonempty runtime metadata for every distinct online seat. Sort by descending
seat count, then runtime name for deterministic lexicographic tie resolution.
Otherwise leave the footer unknown and disclose `runtime_known` /
`runtime_total` coverage on hover. The owner confirmed that this means the
leading runtime among online seats.

Every dependent footer refreshes when either underlying source changes, including
the independent launch-contribution update path. Existing loading/failed/
retained states must still render correctly after the footer text changes;
avoid a loading decision coupled to the old `-- jobs` string. Keep sources and
coverage visible in literal hover details without adding stale text to cards.

## Ownership and dependencies

| Package / owner | Exclusive scope | Dependency |
|---|---|---|
| Plan / planning agent | `docs/surf_board_values_plan.md` only | Approved scope and current BOARD rules |
| UI / one implementer | `maxpane_dashboard/widgets/surf/swarm_fleet.py`, `maxpane_dashboard/widgets/surf/swarm_leaderboard.py`, and their respective widget test files | Approved semantic colors and title exception |
| Data / one implementer | Hero fields/models, pure projection, manager and their corresponding data tests | Frozen footer facts |
| Hero and integration / controller | `swarm_board_hero.py`, corresponding hero tests, composing screen/layout tests and documentation | Frozen fields; integrate both packages before live verification |

The UI, data and controller's hero packages are disjoint and can run in
parallel. One owner per file; report cross-owner findings rather than edit them.
Use the existing workspace and branch, preserve concurrent edits, and keep
temporary captures outside Git. No task review agents are needed below the
planned size.

## Verification and delivery

1. Freeze the footer field additions and runtime coverage/tie behavior. Start
   each behavior change with a focused failing test, implement the smallest
   change, then run the touched cases and relevant consumer cases.
2. Data tests cover independent source failures and recovery, retained matching
   snapshots, positive and zero denominators, known zero numerator, invalid
   relationships, duplicate devices/seats, overlapping runtime memberships,
   ties, incomplete roster, missing runtime coverage and the background launch
   update path. No test uses the network or real clipboard.
3. Assert actual composited color spans: green counts/omissions and neutral
   numeric version/effort/bucket/clock text. Assert paused red remains red.
   Exercise clipped metadata and `+N` fallbacks. Test both leaderboard modes at
   narrow and full widths for no visible widen hint, intact table tiers and
   tooltips, and working sort/selection/tab behavior.
4. Show the owner a **live production render at 149 × 45**, using the existing
   `/tmp/fleet_expanded_live.py` procedure or the app. Do this before layout
   hardening, pin evidence updates or final review. Apply owner corrections.
5. Measure any changed BOARD geometry in situ with the existing `b` sweep;
   inspect actual column content because LEADERBOARD no longer advertises its
   narrow tier. Preserve the previously approved full columns at 149 × 45.
   Update measured pins/`#:` evidence only if needed. Use `scripts/mutate.py`
   for required changed decoder/concurrency or pin behavior and targeted
   regression proof where applicable.
6. Use `.venv/bin/python` and unset `NO_COLOR=1` for color checks. Once before
   commit, run touched files and their composing manager/screen files with
   isolated HOME and `-n 4 --dist worksteal`, then
   `-m "guard and not mounts_app" tests` and applicable docpins. Relevant
   composing files include `tests/screens/test_surf_leaderboard_hero_live.py`,
   `tests/screens/test_surf_launch_contribution.py` and
   `tests/screens/test_surf_swarm_layout.py`. No full suite is added.
7. One final whole-change review on the most capable model, one fix wave, and
   one scoped re-review only for production fixes. File Minor-only residuals
   in the existing follow-ups document. Update final BOARD behavior docs and
   commit the verified changes locally with the scoped test evidence.

The user already authorized this scope; this plan adds no confirmation gate.
