# BOARD content and FLEET layout refresh

**Status:** complete; live preview shown, scoped checks green, final review approved

**Date:** 2026-10-15

**Tier:** 2 — changes the hero contract, manager projection and more than six files

**Size:** under 1,000 production lines; one final review, no package reviews

## User outcome and scope

BOARD makes the recorded-seat leaderboard, launch contributors and current fleet
easier to compare at the owner's **149 × 45** terminal. The rack puts acceptance,
launch participation and cumulative effort in the requested positions; the body
uses the leaderboard's spare right-hand space to make FLEET metadata readable.
Success is the approved content composited at that size with every existing
leaderboard column retained, explicit omission counts and working hover details.

Keep the existing six equal nine-row cards, native panels, sorting, selection,
keyboard routing and independent source clocks. Reuse keyless readers and their
existing scheduling. No endpoint or signing capability is added. Follow KISS and
the existing data → manager → primitive projection → render-only widget boundary;
no extra MVC layer is required. Work in the established workspace/branch and
preserve concurrent edits and untracked files.

## Approved rendering

All BOARD cards use neutral/default gray styling. Remove
visible stale wording while retaining last-good values and literal hover source
details, including independent timestamps and retained/partial/unavailable state.
An unread value remains unknown, not zero; known empty data remains distinct.

| Outer card | Inner heading | Main content and subtitle | Outer footer |
|---|---|---|---|
| TOP SEAT | AGENT | Canonical rank-one seat ID; that seat's accept rate, e.g. `95.9%` | That seat's accepted count, e.g. `4.188k accepted` |
| RECORDED | SEATS | Recorded seat count; online seat count | Recorded attempts |
| ACCEPT RATE | ACCEPTED | Existing acceptance-rate digits; `%` subtitle | Accepted / attempts |
| LAUNCHES (replaces OUTCOMES) | CONTRIBUTORS | `seats`, `claude`, `codex` rows | Distinct jobs contributing to launches |
| WORKERS | NOW | Existing live / working / capacity rows | Existing footer |
| EFFORT | Existing heading | `tokens`, `turns`, `hours` rows | Full whole years / weeks / days text, using boardroom FLEET duration formatting with hours omitted |

Other card content is unchanged. Tokens are the sum of contributor input and
output tokens; do not include cached-input tokens or substitute receipts. If
either input or output is unknown, the total is unknown. Hours and the duration
footer derive from the same contributor wall-clock total.

FLEET changes are presentation-only:

- Show runtime's top two items on one line, with `+N` after the second for omitted
  runtime categories. Preserve full sanitized values on hover.
- Show the top three named model/effort pairs on separate lines; append `+N` to
  the third line. Remove the advertised-note line. A worker can still contribute
  to several distinct model/effort pairs under the existing source semantics.
- Put OS and slots items two per line. Keep all categories reachable; count
  unavoidable width omissions honestly. Keep daemon's existing leading version
  and profile's existing fitting behavior.
- Put a blank line after each complete category: runtime, model, daemon, OS,
  profile, slots, heartbeat and paused. Paused detail belongs within its category.
- Make the `RECEIPTS` subheader bold like `FLEET`; keep its separate source clock.
  Preserve receipt meanings and missing-value behavior.
- Reclaim the leaderboard's empty tail after STATE for the FLEET/RECEIPTS rail.
  At 149 × 45, no existing leaderboard column may be dropped to buy that width.
- Rename the visible `launch contribution` tab to `launch contributors`.

## Data contract and honesty constraints

Keep `surf_leaderboard_hero` and its existing widget signature. The controller
froze the following `SURF_LEADERBOARD_HERO_FIELDS`; every field is present in
each projection, primitives only, with `None` for unread values:

```python
{
    "top": ("state", "read_ts", "token_id", "accepted", "rank", "empty", "percent"),
    "recorded": ("state", "read_ts", "seats", "attempts", "online", "online_state", "online_read_ts"),
    "rate": ("state", "read_ts", "accepted", "attempts", "percent"),
    "launches": ("state", "read_ts", "seats", "claude", "codex", "jobs", "runtime_known", "runtime_state", "runtime_read_ts"),
    "workers": ("state", "read_ts", "live", "working", "capacity"),
    "effort": ("state", "read_ts", "tokens", "turns", "hours", "wall_clock_ms"),
}
```

Retain existing hero states and allow `pending` and `failed` for the first
launch-contribution read. `recorded.online` counts distinct canonical recorded
seat IDs present in a complete current worker roster, not devices or served
worker count. Missing/incomplete roster leaves that exact count unknown and
retains independent `online_state` / `online_read_ts`.

Required facts are the canonical top seat's accepted/attempts/percentage;
recorded seats, attempts and an independently observed online seat count;
launch-contributor seat count, claude/codex contributor-seat counts and distinct
contributing jobs; and contributor tokens, turns and wall-clock hours. Source
metadata must describe the exact captured values, including secondary worker
observations used by RECORDED and LAUNCHES. A worker failure must not erase
canonical counts, and a launch failure must not erase independent fleet facts.

Launch counts use the existing all-history production launch-contribution
reader, retaining its production/testnet filter and accepted non-oracle seat
rules. Seats are unique IDs from that reader, not receipt devices or canonical
record count. Runtime classification uses existing worker metadata for those
seats; never infer historical runtime use from model names or call an offline
seat's absent current runtime a known zero. Deduplicate each seat within each
runtime category; a seat reporting both runtimes counts once in each. These are
known-only current counts with `runtime_known` coverage and independent
`runtime_state` / `runtime_read_ts` disclosed on hover, never historical runtime
attribution. Missing worker roster leaves runtime figures unknown; partial
roster cannot establish exact totals.

The footer counts the union of qualifying job IDs across launches and seats,
including only jobs represented by accepted non-oracle contributors,
not the sum of per-seat `jobs` fields: one job can have several contributors.
Publish that total with the same complete snapshot that supplies the rows.
Retained snapshots must retain a matching total; older snapshots without the
new fact show it unknown until rebuilt. Do not date old rows with a newer
failed/pending catalogue attempt. No new persistence version is required if the
existing decoder accepts an optional validated aggregate compatibly.

## Work packages and file ownership

| Package / owner | Exclusive files and responsibility | Dependencies |
|---|---|---|
| Plan / planning agent | This document only | Authorized requirements and repository rules |
| Data / one data implementer | `data/surf_leaderboard_hero.py`, `data/surf_models.py`, `data/surf_manager.py`, `data/surf_launch_contribution.py` as needed; corresponding hero, launch-reader and manager tests under `tests/data/` | Controller freezes primitive fields and source semantics |
| Hero / one widget implementer | `widgets/surf/swarm_board_hero.py`, `tests/widgets/test_surf_swarm_board_hero.py`; six card faces, footer/subtitle placement and hover behavior | Frozen contract; controller's shared duration/formatting seam |
| FLEET / one widget implementer | `widgets/surf/swarm_fleet.py`, `tests/widgets/test_surf_swarm_fleet.py`; metadata grouping, spacing, omissions, tooltips and RECEIPTS emphasis | Approved content; final width supplied by controller |
| Integration / controller | `screens/surf.py`, theme CSS, visible tab rename in `widgets/surf/swarm_leaderboard.py`, shared formatting reuse/hoist, corresponding widget and composing screen/layout tests, source/docs/follow-up updates | Data + hero + FLEET packages integrated; live render precedes layout hardening |

Paths above are relative to `maxpane_dashboard/` except `tests/` and `docs/`.
Data, hero and FLEET own disjoint files and may run in parallel after the freeze.
The controller owns each shared screen/theme/formatting seam; agents report
cross-owner defects rather than edit another package. Do not add package
reviewers. Keep the total implementation below the planned size or stop and
update the plan before expanding it.

## Delivery and validation

1. Freeze the fields, worker-count semantics and launch aggregate semantics.
   Reuse or hoist the existing boardroom duration formatter once so both
   consumers share it. Confirm temporary live-capture tooling remains outside Git.
2. Each implementation package starts with focused failing tests, makes the
   smallest change, and runs the touched behavior plus its consuming manager or
   screen cases. Use `.venv/bin/python`; tests inject offline transports and
   never touch network or real clipboard. Unset inherited `NO_COLOR=1` for
   composited color assertions.
3. Data coverage includes canonical top selection and rate, known empty/zero
   versus unknown, missing token components, per-source failure independence,
   unique contributor/runtime seats, deduplicated jobs across multiple launches
   and contributors, partial worker metadata, testnet exclusion, restored
   snapshots and matching aggregate/read clocks.
4. Widget coverage uses composited output, not just generated content: exact
   title/subtitle/footer positions, neutral default cards, retained values without
   visible stale text, source hover details, duration without hour fragments,
   two-item rows, model/runtime omission counts, blank category spacing and
   bold RECEIPTS. Exercise empty/missing sources and long sanitized metadata.
5. Integrate and show the owner the **live production render at 149 × 45**
   using the existing `/tmp/fleet_expanded_live.py` helper or the app itself.
   Confirm both recorded and launch-contributors table modes retain their
   columns, all six cards remain aligned, and FLEET gets the reclaimed width.
   Apply owner corrections before pin hardening or final review.
6. Re-sweep BOARD in situ through the established `b` layout measurement path.
   Verify the full boundary, one column/row below it, realistic expanded fleet
   payloads and tall paused details. Update pins and their `#:` blocks only from
   measurements. Assert honest widen/taller behavior and mutation-prove changed
   pin or decoder/concurrency behavior with `scripts/mutate.py` as applicable.
7. Once before commit, run touched test files and composing manager/screen
   files with isolated HOME and `-n 4 --dist worksteal`, plus
   `-m "guard and not mounts_app" tests` and applicable docpins. The relevant
   composing files include `tests/screens/test_surf_leaderboard_hero_live.py`,
   `tests/screens/test_surf_launch_contribution.py` and
   `tests/screens/test_surf_swarm_layout.py`. Do not run the full suite without
   the owner's request or a version tag.
8. One final whole-change review by the most capable model. One fix wave;
   one scoped re-review only if that wave changes production. File Minor-only
   residuals in the existing follow-ups document. Update BOARD documentation
   to describe the final content and measurements; cite the final green checks.

Completion requires the requested live render, preserved table interactions,
passing scoped validation and the single final review. No additional approval
checkpoint is introduced: the owner already authorized this precise scope.
