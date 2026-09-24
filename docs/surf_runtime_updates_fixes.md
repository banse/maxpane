# Surf runtime updates — fix wave

Branch `feature/surf-runtime-updates`, head `90bb33a`. This is the only fix wave for the review
of `docs/surf_runtime_updates_plan.md`. Four reviews ran: docs, data, UI, and one whole-branch
review. All four were Approved with 0 Critical and 0 Important findings. The two items below are
Minors from the whole-branch review that the controller wants fixed now. Every other Minor is
filed, not fixed.

Run R1 and R2 straight through, with no pause. Commit once per item. Do not merge or push. At the
end, send one report: the commits, the tests you ran with their counts, and a mutation proof for
each item that names the test that turned red.

Rules as before: CLAUDE.md conventions, no network in tests, and no pin changes. Neither item
moves a pin; if one would, stop and report instead.

## R1 — the RUNTIME tooltip says "unavailable" when nothing failed

`widgets/surf/swarm_agent_cards.py`:
- `_paint` (line ~156) sets the RUNTIME tooltip to `update check unavailable` before every paint.
  For a gated seat state, that text is what stays on screen.
- `_runtime_body` (line ~203) writes the same text whenever `runtime_semver(runtime_id, newest)`
  is `None`.

This makes two states that are not failures read as failures:
- **The seat is pending**, or has no summary yet. There is no runtime to check.
- **The first cycle, before npm has been read.** `_runtime_keys` builds `swarm_runtime_latest`
  only from stored points, so the runtime id is **absent** from the dict until the first check
  lands.

A failed read is different: the point is stored with a version of `None`.

The fix keeps these states apart, in the same way as a failed read (`None`) versus a real
negative:
- **Gated states** (pending, `unknown_seat`, unavailable, no summary): the default tooltip becomes
  `None`, meaning no tooltip. There is no runtime, so there is nothing to explain. It must still be
  reset on every paint, so a previous seat's tooltip never survives. The UI reviewer confirmed this
  is the reason for the reset.
- **The runtime id is absent from `swarm_runtime_latest`**, or the dict itself is `None`:
  `update check pending`.
- **The id is present and its value is `None`**, or the value is not a valid semver:
  `update check unavailable`. This is unchanged.
- `runtime not checked` (for a runtime other than claude or codex), the `latest …` line and the
  fleet daemon line are unchanged.

Tests in `tests/widgets/test_surf_swarm_agent_cards.py` cover four cases:
- a pending seat after a seat that had a tooltip: the tooltip is `None`;
- the id is absent: `update check pending`;
- the id maps to `None`: `update check unavailable`;
- a valid latest version: unchanged.

The body text must not change in any case. Mutation proof: make the absent-id branch write
`unavailable`, then name the test that turns red.

## R2 — `coerce_rank_slot` has no upper bound

`data/surf_swarm.py:2278` `coerce_rank_slot` accepts any positive `rank` and `prev`. The cache
file can be hand-edited, and it is third-party input. A value such as `{"rank": 3, "prev": 10**30}`
renders a 31-digit `▲` in the RANK box.

The fix:
- Drop a point when `rank` or a non-`None` `prev` exceeds a named bound, `RANK_MAX = 10**6`.
  Give the bound a `#:` comment stating that the board lists hundreds of seats and that the bound
  is only a sanity bound.
- Apply the same bound to a live `contrib["rank"]` in `SurfManager._seat_rank_delta`. An
  out-of-range live rank gives a delta of `None` and stores nothing.

Tests:
- In `tests/data/test_surf_swarm*.py`, next to the existing rank-slot tests: `10**6` is kept,
  `10**6 + 1` is dropped (for both `rank` and `prev`), and valid sibling points survive.
- A manager test: a live rank of `10**6 + 1` gives `swarm_seat_rank_delta is None` and leaves
  the slot unchanged.

Mutation proof: remove the bound in `coerce_rank_slot`, then name the test that turns red.

## File, do not fix

Append the following to `docs/surf_runtime_updates_followups.md`. Leave F-RU1 as it is.

- **F-RU2 — a stale persisted npm latest is compared for one cycle** (whole-branch 2). After a
  long offline gap, the stored latest version is used until the next due read. The tooltip's
  `as of HH:MM` carries no date, so a days-old check reads as today's. Low impact: the TTL is
  3,600 s and the read is due on the first cycle.
- **F-RU3 — both runtime packages are fetched** (whole-branch 4). The card compares only the
  seat's own runtime (`runtimes[0]`). The second package costs one small keyless GET per hour.
  Keep it, or fetch only the seat's runtime; decide when the file is next touched.
- **F-RU4 — `fmt_compact` renders `1000.0B tokens`** (whole-branch 5). Above 999.95 B the
  shared formatter does not carry over to a `T` suffix. This is shared-widget behaviour
  (`widgets/sparkline_common.py`), so it is out of scope here. No real seat is near it.
- **F-RU5 — `_seat_entered` calls `start_refresh` twice** (whole-branch 6). The refresh guard
  skips the second call, so there is no visible effect. Remove the second call when
  `screens/surf.py` is next touched.

## Tests to run at the end

Run these files:
- `tests/widgets/test_surf_swarm_agent_cards.py`
- `tests/widgets/test_surf_swarm_agent_hero.py`
- `tests/widgets/test_surf_widget_contract.py`
- the rank-slot test file you touched
- `tests/data/test_surf_swarm_models.py`
- `tests/screens/test_surf_swarm_screen.py`

Then run `tests/screens/test_surf_swarm_layout.py -k agent`, then `-m guard`. Do not run the full
suite. The controller runs it once, before the merge.
