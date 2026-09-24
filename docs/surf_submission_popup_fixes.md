# FIX WAVE — surf SUBMISSION popup (after the per-WP and whole-branch reviews, 2026-09-24)

For: Codex, on `feature/surf-submission-popup` in this clone (head `5b82d2b`). This is the branch's **one** fix wave
(CLAUDE.md Tier 2). Precedence: CLAUDE.md > the plan (as amended below) > this brief.

Run straight through, stopping only for one of these:
- a plan defect
- a named test you cannot make green
- a layout pin that would move

Rules:
- Use `.venv311/bin/python` with `env -u NO_COLOR`.
- Run the named tests plus `-m guard`, never the suite.
- Never push, merge, tag, bump the version or rewrite history.
- Nothing in the background.
- Commit this brief with the first fix commit.

Note: `tests/data/test_surf_manager_pool4_market.py` needs the **untracked** `tests/fixtures/surf/pool4/oracle_25955365.json`.
Do not commit it and do not touch that test. It is a separate item for the owner.

## 1. Plan amendments (commit them with F3, in `docs/surf_submission_popup_plan.md`)

- **§2.2 JOB line (controller defect, the review's I3):** the job facts can be up to 48 h old. A row that leaves the
  40-row window keeps its answer point and its `»`, and its job detail is never due again. `blocked` is not terminal.
  So the JOB line always ends with `· as of HH:MM`, taken from the job point's `read_ts`. The time format comes from the
  shared `widgets/fmt.hhmm`, the `as of` form every other marker uses. This needs a new row key `job_read_ts`
  (float | None), appended to §3.3 and to the frozen tuple.
- **§3.2 eligibility (controller defect, the review's M4):** "not read yet" was a promise that off-panel oracle rows never
  kept. Their job was never eligible. A job is now eligible when its row is in the first 40 **and** would open a
  SUBMISSION popup: not joined, `answer_state` in `read`/`no_reply`, and a valid identity. The node key and the
  failed/rejected status stop mattering. A row with a button therefore always gets its job read eventually. The
  per-cycle cap of 2 and the 120 s due time stay.
- **§3.1 size bound (the review's M5):** the 8,000-byte bound measures the **on-disk** encoding that `surf_cache` writes
  (default `json.dump`: `ensure_ascii`, default separators). That is how `_bound_oracle_point` already measures. Fix
  the worst-case figure in the plan and in `docs/imd_swarm_api.md` to what the new measurement gives.

## 2. Items

Each item gets a fix and a regression test. **Prove** means:
1. Break the code on purpose.
2. Name the test that goes red.
3. Restore the code by inverse edit.

| id | sev | what | where | done when |
|---|---|---|---|---|
| **F1 (I1)** | Important | A cut that ends at `https:/` or `https://` is matched as a local path. The point then fails its load-time safety check (`_safe_reply` / `_valid_short_text`) and is dropped. The job is re-read every cycle, and its answer never shows | `surf_swarm.py` `_text_prefix` (~1592, ~1633), `_bound_text_fields` (~1973), `failed_checks` 300 cut | After **any** cut (the 200-char others line, the 4,096 reply, the 300 failed-checks, each byte-cascade step), the result passes the same safety predicate the loader applies. Either re-run the strippers on the cut text or back the cut off to before the partial URL. Tests: one case each for a cut landing exactly on `https:/` and on `https://`, for the others line, the reply cap and a cascade trim. Each point survives `coerce_answers_slot` unchanged. **Prove:** remove the post-cut step, and the cut-at-`https:/` test goes red |
| **F2 (I2)** | Important | A long non-ASCII `answer` (for example `'审计发现'*700+'。'`, or `'━'*3000`) is larger than the byte budget on its own. `bound_answer_point` returns `None`, and the manager writes `unavailable`. That is a false degradation, and a regression from before this branch | `surf_swarm.py` ~1675, `surf_manager.py` ~5812 | `answer` is the **last** target of the cascade, trimmed by the same hex-safe, URL-safe cut. `bound_answer_point` returns `None` only when nothing can be trimmed further. Regression test: the three summaries above give state `read`, a bounded point, and a RECORD answer that is not `unavailable`. **Prove:** drop `answer` from the targets, and the test goes red |
| **F3 (I3)** | Important | The JOB line shows job facts that may be 48 h old as if they were current | `screens/submission_detail.py` ~717, row fold `enrich_job_rows` | Per the amended §2.2: `job_read_ts` in the row. The JOB line composites `· as of HH:MM` for `read` and for `unavailable`, when a cached point exists and the last read failed. It shows nothing for `not_read`. Pilot test on the hunt fixture: the composited JOB line contains `as of` plus the fixture's time. **Prove:** drop the marker, and the test goes red |
| **F4 (M4)** | Minor | Off-panel oracle rows always show `JOB not read yet` | `surf_swarm.job_details_due` ~1733 | Per the amended §3.2. Test: an off-panel, completed oracle row with a button becomes due, and a joined row never does |
| **F5 (M5, WP1-m1)** | Minor | The byte budget measures compact JSON, but the cache writes the default encoding, which takes about 2× the bytes on disk | `bound_answer_point`, `_valid_submission_facts` | Measure exactly as `_bound_oracle_point` does. The F-series cascade test and the stress cases assert against that encoding. Update the size figures in `docs/imd_swarm_api.md` and the plan with **measured** numbers, including the bytes32 oracle point (WP5 review: 1,715 did not reproduce) |
| **F6 (M6)** | Minor, measured | `coerce_answers_slot` takes 0.585 s at 400 points of about 6 KB, and it runs 4× per `fetch_and_compute` on the event loop, which is about 2.3 s | `surf_manager.py` 5793, 5817, 6171, 6177; `_safe_reply`, `_answer_link_spans` | Measure first with a 400-point synthetic slot, and put the number in the commit message. Then: either run the full per-point coercion once per cycle and on load (the in-memory slot is already validated in between), **or** make `_safe_reply` a single-regex scan. Either way the cap and the hostile-field tests stay green. Target: ≤ 0.1 s per cycle at the cap. Put before and after in the report |
| **F7 (WP1-m3)** | Minor | `others` is gated on **this** row's node key, not on each sibling's own key | `surf_swarm._submission_facts` ~1616 | Filter each sibling by its own `nodeKey` (oracle keys excluded). A non-oracle row still gets `others` (possibly `[]`). An oracle row still gets `None`. Test: a mixed job with one oracle sibling excludes that sibling and does not count it in `others_total` |
| **F8 (WP4-m1)** | Minor | The popup's `out` tokens use `fmt_compact` directly. RECORD carries 999,500–999,999 to `1.0M`, so the two views can differ for the same row | `submission_detail.py:66`, `swarm_seat_record.py:242` | One helper, `tok_text`, in `_oracle_answer.py` (or `_fmt.py`), used by both. Test at 999,700: both show `1.0M` |
| **F9 (WP1-m2)** | Minor | The job-detail cap, max age and due time rely on function defaults | `surf_manager._pool_swarm_job_details` ~5822 | Named constants in `surf_manager.py` beside the `SWARM_ANSWER_*` constants (`SWARM_JOB_DETAIL_PER_CYCLE`, `_CACHE_CAP`, `_MAX_AGE_S`, `_DUE_S`), each with a `#` comment, passed explicitly |
| **F10 (WP2-m1)** | Minor | The `swarm_seat_record.py:14` docstring still says the answer lights `‹ widen` when cut | — | It says: `‹ widen` only when there is no popup button |

**Not in this wave (filed):**
- M7: the layout test certifies the historical, button-less case at 167.
- This is already stated in the `#:` block.
- Add it to `docs/surf_answer_popup_followups.md` as a known follow-up, and change nothing else.

## 3. Commits, tests, report

- **Commits:**
  - `fix(surf): F1 F2 cuts pass the load check; answer is the last trim` (with this brief)
  - `fix(surf): F3 F4 job line as of; every button row's job is eligible` (with the plan amendments)
  - `fix(surf): F5 F6 F7 on-disk byte bound, one coercion per cycle, sibling node filter`
  - `refactor(surf): F8 F9 F10 one tok formatter, named job-detail constants, docstring`
- **Tests:**
  ```
  tests/data/test_surf_swarm_answers.py tests/data/test_surf_manager_answers.py tests/data/test_surf_cache_swarm.py
  tests/data/test_surf_swarm_oracle.py tests/data/test_surf_manager_oracle.py tests/data/test_surf_swarm_models.py
  tests/data/test_surf_swarm_seats.py tests/data/test_surf_manager_swarm.py
  tests/widgets/test_surf_swarm_seat_record.py tests/screens/test_submission_detail.py tests/screens/test_oracle_answer.py
  tests/screens/test_surf_screen.py        (whole file, once, at the end)
  tests/screens/test_surf_swarm_layout.py -k "agent or record or oracle or polish"
  tests/test_address_rule.py tests/test_address_sweep_registry.py
  the doc-pinning files for any doc you edit (rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/)
  -m guard --ignore=tests/data/test_surf_manager_pool4_market.py   (only if that fixture is absent)
  ```
- **One final report:**
  - commits (hash and subject)
  - tests and counts
  - for each proof, which test went red
  - F6 before and after, in seconds
  - the new measured byte sizes
  - every deviation and its reason
- After you, the controller runs one scoped re-review and the full suite once. The merge is the owner's.
