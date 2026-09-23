# FIX WAVE — surf oracle panels (after the whole-branch review, 2026-09-24)

For: Codex, on `feature/surf-oracle-panels` in this clone (head `83e2127`). This is the branch's **one**
fix wave (CLAUDE.md Tier 2). The owner approved it on 2026-09-24: the request-index redesign and the
fixture slimming. Read `CLAUDE.md`, then the amended plan §2 step 3 (`docs/surf_oracle_panels_plan.md`, marked
"amended 2026-09-24"). Precedence as before: CLAUDE.md > handover §5B > plan (as amended) > this brief.

Run straight through with no stops between items, except the plan's stop conditions: a plan defect, or a named
test you cannot make green. Use `.venv311/bin/python`, and `env -u NO_COLOR` for colour tests. Run named tests plus
`-m guard` only; no suite. Never push, merge, tag, bump the version, or rewrite history (§3 below is the controller's).

## 1. Findings to fix

Each item: make the fix, add a regression test, and prove the test bites where the item says "prove".

| id | severity | what | where | done when |
|---|---|---|---|---|
| **C1** | Critical | Rows were marked final `off_panel` from a page boundary that proves nothing, and an empty first page settled every row as absent | `surf_swarm.match_requests` (~1808–1836), `surf_manager._pool_swarm_oracle` (~5816–5860), `SWARM_ORACLE_PAGE_*` | Implement the **request index** exactly as plan §2 step 3 (amended): new slot `SLOT_SWARM_ORACLE_INDEX`, forward refresh, backfill, and absence only from a complete index whose newest ≥ `submitted_ts`. `PAGE_LIMIT` becomes 500. Rewrite the `#:` blocks. **Prove:** (a) the reviewer's case: seat request on page 2, a newer unrelated request on page 1, `PAGE_LIMIT` patched to 1. It must end `agreed`/`outvoted` after the backfill, never `off_panel`. Revert the fix and show that this test goes red. (b) An empty first page on a non-empty index is a failed read. (c) A hostile index slot is discarded and rebuilt. (d) A gap larger than the page cap discards the index. (e) The fixture replay: build the index from the committed list pages and confirm that every seat-420 row the handover counts as matched (219) is found, and that only the 24 counted as not on a panel become `off_panel` |
| **M1** | Minor | A quiet seat re-read 4 list pages every 120 s forever | same | Covered by C1. Add a test: a seat whose due rows are all in a complete index makes **zero** list calls |
| **M4** | Minor | The manager used the private `sw._ts`, and the cursor depended on the served format | manager ~5816+ | Covered by C1: a public helper, and the strict ISO check before a stamp becomes a cursor |
| **I1** | Important | `tests/data/test_surf_cache.py::test_newest_as_of_is_the_freshest_successful_read` counts slots (`len(SLOTS) == 16`); now 18 with the index | `tests/data/test_surf_cache.py:230` | Update the count **and** name the two new slots in the comment. The test goes green |
| **I2** | Important | `test_surf_screen.py::_sample_data()`'s `swarm_seat_work_rows` (~1623) lacks `output_tokens` and the `panel_*` keys, so every surf screen composite rendered `unavail` | `tests/screens/test_surf_screen.py` | Give the sample rows the full frozen shape with realistic states (at least one `agreed`, one `outvoted`, one `not_oracle`). `test_every_list_row_in_the_fixture_matches_the_frozen_row_shape` goes green. Run the whole file once (it is the screen test that composites RECORD) |
| **M2** | Minor | `tok` printed `812.0` under 1,000, and `1000.0K` for 999,500–999,999 (clipped) | `swarm_seat_record.py` tok cell | Below 1,000, print the plain integer (`fmt_int`). At 1,000 and above, keep `fmt_compact`, but never print `1000.0K`: carry it to `1.0M`, like F66's node cards. Add tests for 0, 1, 812, 999, 1000, 1534, 22000, 999499, 999500, 999999 and 1234567, each fitting 6 cells |
| **M3** | Minor | FLEET showed a model made only of tags as `none` (the null-model word) plus the effort | `swarm_fleet.py:92` | Use the same empty display RECORD uses (`—`), with no effort appended when the cleaned model is empty. Add a test |

## 2. Fixture slimming (owner-approved)

The tests need about 50 of the 246 files under `tests/fixtures/surf/swarm/oracle/`. The rest cost 19 MB.
1. Keep: `MANIFEST.json`, `seat_420.json`, every `list_*.json` page, the 400/unknown-id bodies, and only the
   `request_*.json` details a test actually reads. Find them by instrumenting `open`/`Path.read_*` during
   a run of the oracle tests plus the RECORD layout tests, not by guessing. Put the kept ids in one hand-listed
   tuple in the test helper that loads them, so a missing file fails loudly.
2. `test_oracle_latest_seat_fits_existing_agent_pin` currently joins all 243 rows. Restrict it to RECORD's
   displayed window (the first 40 rows, `SWARM_ANSWER_ROW_CAP`) plus any detail the pin measurement needs. Re-run
   it, and if its numbers move, stop and report: that would be a pin change.
3. Stop loading the corpus at import time in `tests/data/test_surf_swarm_oracle.py`. Load it lazily, in a fixture.
4. `MANIFEST.json`: keep every original entry (sha256, bytes), because they are the evidence of the full capture. Add
   `"committed": false` to the removed ones, and keep the derived §4 recount in `note`. The capture script's
   `--summarize` should say it needs a fresh capture when files are missing.
5. `git rm` the removed files in the fix commit. Report the kept count and the new `du -sh`.

## 3. Commits and report

- One commit per item group: `fix(surf): C1 oracle request index` (C1+M1+M4, plus the amended plan and the rules
  text), `fix(surf): I1 I2 slot count and screen sample rows`, `fix(surf): M2 M3 token and model display`,
  `test(surf): slim oracle fixtures`. Include this brief in the first commit.
- Update `.claude/rules/surf.md` (line ~346, "Off-panel requires covered list history…"): off-panel now requires a
  complete request index covering the row's submission. Update the `SLOT_*` mentions there, `docs/imd_swarm_api.md` if it
  describes the walk, and add F-O1 (index growth) to `docs/surf_oracle_panels_followups.md`.
- **Tests to run:** `tests/data/test_surf_swarm_oracle.py`, `tests/data/test_surf_manager_oracle.py`,
  `tests/data/test_surf_cache.py`, `tests/data/test_surf_cache_swarm.py`, `tests/data/test_surf_swarm_client.py`,
  `tests/widgets/test_surf_swarm_seat_record.py`, `tests/widgets/test_surf_swarm_fleet.py`,
  `tests/screens/test_surf_screen.py`, `tests/screens/test_surf_swarm_layout.py -k "agent or record or oracle or polish"`,
  and `-m guard`.
- **One final report:** commits (hash + subject), tests and counts, which test reddened for each proof, the kept
  fixture count and size, and any deviation from this brief with its reason.
- The controller (Claude) then runs ONE scoped re-review of these findings, the full suite once, and, with the owner's
  go, strips the removed fixture blobs from the branch history (a backup ref is kept) before merge. You do **not**
  rewrite history.
