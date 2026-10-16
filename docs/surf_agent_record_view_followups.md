# Surf AGENT record view follow-ups — 2026-09-24

The review fix wave resolves X1–X7; F-R1 below remains filed, not changed.

The owner approved testing the committed submissions #420 capture (232 collaborators,
#1626 ×158, #1731 ×150, ORACLE 219/256) instead of the newer screenshot numbers.
The screenshot values remain covered separately by a synthetic composited case.
No fixture or oracle detail manifest was changed.

The 400-row limit is intentional: at that limit the remaining older count stays,
and `more` is no longer offered. Larger histories require a separate product decision.

Controller scoped re-review and the full suite remain before the owner's merge decision.

- **F-R1 — stale non-terminal points after grow → shrink → grow** (whole-branch 5). Rows 41–400
  that were read earlier keep their cached point, and it is not re-read while the row is
  outside the window. After the window grows again, those rows show the old value until the
  due read reaches them (4 per cycle), behind the seat's `as of` only. The impact is low
  because old rows are almost always terminal. The same thing already happens inside the
  40-row window after a restart.

- **F-R2 — current action outside the recent jobs snapshot** (2026-10-16, scoped limitation).
  The STATUS card uses fresh working-node assignments from the existing recent-job feed.
  An older active job outside that feed, an unknown node category, or an unread assignment
  displays `working`. Extending discovery would be a separate Tier 2 data-reader change;
  the label update adds no requests or history scans.

The 2026-10-16 card-label update was previewed with live keyless data at 149×45 for
idle seat #420 and active seat #1621 (`building`). In-situ measurement with
`scripts/measure_layout.py` remains 132 columns × 29 rows: capture420 was measured
at widths 130–134, and worst-a at heights 26–31. The new blank row below RECORD
uses the existing table viewport; no pin or card width changed.

- **F-R3 — older manager contract assertion omits the launch read clock** (test-only, Tier 0).
  `tests/data/test_surf_manager_swarm.py::test_board_keys_are_exact_before_finalization_and_survive_cold_start`
  excludes `swarm_launch_read_ts` from its expected top-level signal fields. The same
  failure was reproduced with all three changed data modules loaded from baseline
  commit `43ae60f4`, without changing workspace source. Update that assertion when
  the manager swarm test file is next touched; no production change is needed here.

- **F-R4 — busy-source card assertion predates suppressed source notices** (2026-10-16).
  `tests/screens/test_surf_swarm_layout.py::test_busy_agent_cards_keep_independent_records_at_the_pin`
  expects visible `busy` text, but the current display override suppresses it. REWARDS
  renders its neutral placeholders instead. The failure also reproduces with both changed
  production modules loaded from pre-swap commit `4c9ec0b3`, at the original 132-column pin.
  Reconcile this older assertion with the approved source-notice behavior separately.

- **F-R5 — status-bar boundary assertion is outdated** (2026-10-16).
  `tests/screens/test_surf_swarm_layout.py::test_the_status_bar_edge_is_where_it_was_measured`
  expects clipping at 128 columns, but the footer already fits there. The failure reproduces
  with production modules loaded from `4c9ec0b3`, without changing workspace source.
  Re-measure the separate status-bar boundary before updating its assertion.

The 2026-10-16 STATUS/OWNER swap was shown with live data for seat #1581 at 149×45.
OWNER now ends the first row; STATUS starts the second. In-situ measurement sets the
AGENT minimum to 137 columns × 29 rows. The review's outdated OWNER width expectation
and the analogous compact STATUS test were corrected in tests only; no production fix
or scoped re-review was needed. The focused files pass all 100 cases; the two baseline
failures above remain outside this swap.
