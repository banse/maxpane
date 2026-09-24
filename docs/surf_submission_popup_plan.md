# Surf AGENT: SUBMISSION popup for every non-oracle and failed RECORD row (F-A2, spec + plan, 2026-09-24)

Tier 2: new row and cache keys in `data/surf_models.py`, a new cache slot, a new screen, and a change to the
persistence rule in `.claude/rules/surf.md`. Owner decisions (2026-09-24):
- Build F-A2 now.
- **The cache may store reply texts** (bounded, §3).

Example: seat 420's `hunt_d` run on `7b9c907d` (Fren Review, a job to find weaknesses in Magic Internet Frens'
Cauldron hook). RECORD shows only `the local build failed, so this was not submitted:`. The API also knows the job is
`blocked` (`node hunt_b: runtime_error`), the seat's `failureReason` (`local_build_failed`), its usage
(fable 5.1, 61 turns, 22:56, 75K out) and what the seven other seats on the job did: six were refused by their
runtime ("flagged for possible cybersecurity risk"), and one wrote outside its allowed paths.

Precedence: CLAUDE.md > this spec > WP steps > implementer report.

---

## CODEX — START HERE

1. The base is autopull's local main. It is unpushed, and this clone's `origin/main` is behind:
   ```bash
   cd /Users/banse/codex/maxpane
   git status --short        # only .codex/ .venv311/, the pool4 oracle fixture and this plan
   git fetch /Library/Vibes/autopull main
   test "$(git rev-parse FETCH_HEAD)" = d0a71487d7c9704797eb3b94391bd54de2b7fc77 || echo STOP
   git switch -c feature/surf-submission-popup FETCH_HEAD
   .venv311/bin/python -m pip install -e . -q
   ```
   If the hash differs, stop and report.
2. Read `CLAUDE.md`, `.claude/rules/surf.md`, `widgets.md`, `data.md` and `.claude/skills/terminal-layout/SKILL.md`.
   Then read `docs/surf_answer_popup_plan.md` (the ANSWER popup this plan builds beside) and
   `docs/surf_answer_popup_fixes.md` (its review lessons: F1 failed-read rule, F5/F6 one home, F8 hex cut).
3. Run WP0–WP5 **straight through**, with no pause between WPs. Stop only on §7. Write one final report (§8).
4. Never push, merge, tag, bump the version or rewrite history. Commit per WP.
5. Use `.venv311/bin/python` with `env -u NO_COLOR`. Run named tests plus `-m guard`, and never the full suite.

---

## 1. The source (probed live 2026-09-24, control plane `23659b86`, read-only and keyless)

**`GET /jobs/<id>/submissions`** is already read for RECORD's answer column (`surf_swarm_client.submissions`,
`surf_swarm.submission_answer`, at most 4 jobs per cycle). Today only the first sentence of this seat's `summary`
is kept. Per item:
- `hash`, `nodeKey`, `role`, `attempt`, `seat{tokenId, agentId}`, `outcome`, `accepted`
- `failureReason`: seen `local_build_failed`, `runtime_error`, `path_violation`
- `summary`: the agent's Markdown reply, or on failure the daemon's failure line plus output
- `usage{model, turns, runtime, inputTokens, outputTokens, cachedInputTokens, wallClockMs}`
- `verdict{…, failedChecks[]}` (null on this failed run), `findings[]`, `artifacts[]{hash, name, path, bytes, mediaType}`
- `verificationErrors`, plus more that we do not use

Measured on `7b9c907d`: 8 submissions, 11,660 bytes.
- Seat 420's summary is 2,051 characters: the line `the local build failed, so this was not submitted:`, then a forge log that
  **begins mid-line and stops mid-warning**. All of it is lint warnings; **the compile error itself is not in the
  published text**.
- The other six `runtime_error` summaries (213 chars) read *"This content was flagged for possible cybersecurity risk … Trusted
  Access for Cyber program: https://chatgpt.com/cyber"*.
- `path_violation` reads *"wrote outside the task's allowed paths: test/fren-review/hunt_c/HuntCBase.sol"*.

**`GET /jobs/<id>`** (`surf_swarm_client.fetch_job`, already exists) returns:
- `state` (e.g. `blocked`) and `blockedReason` (`node hunt_b: runtime_error`)
- `nodes[]{key, role, state, attempt, failureReason, dispatchNote, seat, …}`

On `7b9c907d`: hunt_a ready/1, hunt_b **failed/3 runtime_error**, hunt_c ready/2, hunt_d ready/2, report waiting/0,
verify waiting/0; `seat` null on every node. The existing `SLOT_SWARM_JOBS_SEEN` keeps node summaries **without**
`failureReason`, `attempt` or `blockedReason`. Do not widen that shared slot; §3 adds a new one.

**Also found (G1):** oracle request `4c11a919` has `answerType: "bytes32[]"`, a list of 0x + 64-hex pool ids. The
branch's normalisation turns any list other than `address[]` into `None`, so RECORD showed `—`. Fixed in WP1.

## 2. Behaviour

### 2.1 Which rows get a button, and which popup

Joined oracle rows (the seat's answer.json was found) keep the `»` → ANSWER popup, unchanged.

Every **other** row with a valid job UUID and 64-hex hash, and whose answer read succeeded
(`answer_state` in `read`, `no_reply`), gets a `»` → **SUBMISSION** popup when either:
- its answer text is cut, **or**
- its `work_status` is `failed` or `rejected`. A failed row gets the button even when its text fits (owner: failed
  jobs are the interesting ones).

This covers review/build/hunt rows, off_panel oracle rows, and failed oracle rows such as `bundle upload failed (500)`.

- The button, glyph, spacing and action validation match the ANSWER button. The action is
  `screen.open_submission('<uuid>','<hex64>')`.
- A row with a button does not light `‹ widen`, as with joined rows. Only rows without a button still light it.
- Rows whose answer is `not read` / `not served` / `unavailable` get no button: nothing to show.

### 2.2 The SUBMISSION popup — `screens/submission_detail.py`

Share the frame with the ANSWER popup: hoist title, sections, the focused `VerticalScroll`, the pinned centred
`PRESS ENTER TO CLOSE`, enter/escape bindings and `DEFAULT_CSS` into **one** base in `screens/`, and make
`OracleAnswerScreen` subclass it. No second copy of the frame. Name the base something no widget or stylesheet uses.

```
SUBMISSION · 7b9c907d · hunt_d · tests · 09-24 06:13

JOB        blocked · node hunt_b: runtime_error                           (job detail; `not read yet` / `unavailable`)
NODES      hunt_a ready 1 · hunt_b failed 3 runtime_error · hunt_c ready 2 · hunt_d ready 2 · report waiting · verify waiting
OBJECTIVE  🐸 Fren Review — pepes help pepes. The Identity.md swarm red-teams …   (row `objective`, whole, wrapped)

THIS SEAT  failed · local_build_failed
           fable 5.1 · 61 turns · 22m 56s · 75.0K out · 6.2M cached in
           checks failed: —  · findings 0 · artifacts —
REPLY      the local build failed, so this was not submitted:
           published excerpt only — the build error may not be in it           (dim; only for local_build_failed)
           estamp >= p.votingEndsAt;
                ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           …                                                               (whole stored reply, scrolls)

OTHER SEATS ON THIS JOB (7)
  hunt_a  #1     runtime_error   This content was flagged for possible cybersecurity risk.
  hunt_b  #47    runtime_error   This content was flagged for possible cybersecurity risk.
  hunt_c  #2     path_violation  wrote outside the task's allowed paths: test/fren-review/hunt_c/HuntCBase.sol
  …                                                               (+N more when > 8)

                               PRESS ENTER TO CLOSE
```

- **State colours:** RECORD's `_STATE_COLORS` (`swarm_seat_record.py:76`). Hoist it into `_oracle_answer.py` and
  import it in both places; never copy it.
- **REPLY** renders the stored reply line by line and keeps its indentation and box-drawing characters.
  - Lines longer than the box **wrap**. Do not truncate, and do not scroll horizontally; the ANSWER popup's
    `max_scroll_x == 0` rule holds here too.
  - For `local_build_failed`, show the dim excerpt note. Never claim which error failed the build.
- **OTHER SEATS** comes from the same submissions body. It excludes this hash, is sorted by node key then seat token,
  and shows at most 8 with `+N more`. Each line is `answer_sentence` of that seat's summary, ≤ 200 characters.
  Shown only for non-oracle node keys: an oracle job's panel belongs in the ANSWER popup.
- **Addresses** in any third-party text (objective, reply, other lines, blocked reason) go through `address_prose`
  with `explorer=None`: a non-oracle job carries no chain id, so it gets the icon and no link (rules/widgets.md:
  unknown chain → no link, never a guess). A 64-hex hash stays unlinked.
- Every third-party string reaches `Static` as a pre-built `rich.text.Text`.
- **Opening** works like `action_open_oracle_answer`: re-validate, find the row in the rows last rendered,
  snapshot it, never fetch, and post `answer no longer listed` when the row is gone. Two rows of one job must open
  their own hash (lesson F7).
- **Geometry:** certify at 80×24, 139×33 and 40×12. No region overflow, no horizontal scroll, the footer visible
  and centred.

## 3. Data contract (WP0 freezes it)

### 3.1 Reply facts — extend the answers slot (`SLOT_SWARM_ANSWERS`)

They are read from the submissions body already fetched, so they cost no new request. Append to
`SWARM_ANSWER_CACHE_FIELDS`:

| field | type | rule |
|---|---|---|
| `reply` | str \| None | this seat's `summary`, ≤ 4,096 chars (`ANSWER_TEXT_CAP`). Cleaned: local paths via the existing `_strip_answer_paths`, Markdown link targets via `_strip_answer_links`, ANSI escape sequences removed, `\t` → 4 spaces, every other control character removed **except `\n`**. Everything else verbatim. The cut must never end inside a `0x` hex run (reuse F8's `_oracle_prefix` in `surf_swarm.py`; rename it to a neutral name and use it for both) |
| `failure_reason` | str \| None | `failureReason`, fullmatch `[a-z][a-z0-9_]{0,63}`, else `None` |
| `turns` | int \| None | `usage.turns`, strict int ≥ 0 |
| `cached_input_tokens` | int \| None | `usage.cachedInputTokens`, strict int ≥ 0 |
| `failed_checks` | str \| None | `verdict.failedChecks` names, cleaned, joined `", "`, ≤ 300 chars; `None` when there is no verdict |
| `findings` | int \| None | `len(findings)` when it is a list |
| `artifacts` | list[dict] \| None | ≤ 10 × `{name: str ≤ 80, bytes: int ≥ 0 \| None}` |
| `others` | list[dict] \| None | non-oracle node keys only: ≤ 8 × `{node_key ≤ 40, token: int, outcome ≤ 20, failure_reason, line ≤ 200}`, in the §2.2 order |
| `others_total` | int \| None | count of other submissions before the cap |

**Persistence rule change (owner-approved 2026-09-24).** `.claude/rules/surf.md` and the `SWARM_ANSWER_CACHE_FIELDS`
`#:` block currently say "never summaries". They become: "a bounded, cleaned reply (≤ 4,096 chars) and other
seats' first lines (≤ 200) persist; never a raw envelope". Update both.

- **Size:** one answer point is ≤ 8,000 bytes as compact UTF-8 JSON, after a trim cascade: `others` lines, then
  `reply`, then `failed_checks`. Hoist the F-series byte-budget cascade into one helper both slots use; do not write
  a second one. Worst case 400 points × 8 KB ≈ 3.2 MB beside the oracle slot's ≈ 2.1 MB.
- **Migration:** old points lack the fields and are dropped, then re-read (≤ 4 jobs a cycle). Accepted.
- **Validation:** `coerce_answers_slot` validates every new field per point, and a hostile field drops only that point.
  The stored-answer safety check (`_safe_stored_answer`) must not reject a `reply` for its newlines. Give `reply` its
  own check: its cap, no control characters except `\n`, no local path left.

### 3.2 Job facts — new slot `SLOT_SWARM_JOB_DETAIL`

Keyed job UUID → `{state, blocked_reason, nodes, read_ts, terminal}`.
- `state`: str ≤ 40 \| None.
- `blocked_reason`: str ≤ 200, cleaned \| None.
- `nodes`: ≤ 16 × `{key ≤ 40, role ≤ 20, state ≤ 20, attempt: int ≥ 0 \| None, failure_reason}`.
- `terminal`: true when `state` ∈ `{"completed", "failed", "cancelled"}`. `blocked` is **not** terminal (a blocked
  job can resume).

Reads:
- Through the existing `fetch_job`, only for jobs of rows in RECORD's 40-row window whose node key is not an oracle
  key, or whose `work_status` is failed/rejected.
- At most **2 per cycle**, due every 120 s while nonterminal, cap 400 entries, max age 48 h, with the injected clock.
- A failed read is `unavailable`, never an empty job.
- Add the slot to `surf_cache` and to the slot-count test with its name in the comment (lesson I1).

### 3.3 Row keys (append to `swarm_seat_work_rows`, each with its `#` comment)

`sub_reply`, `sub_failure_reason`, `sub_turns`, `sub_cached_input_tokens`, `sub_failed_checks`, `sub_findings`,
`sub_artifacts`, `sub_others`, `sub_others_total`: copied from the answer point, all `None` when there is no point.

`job_read` is one of `"read"`, `"not_read"`, `"unavailable"`, and comes with `job_state`, `job_blocked_reason`,
`job_nodes`.

**Name collision:** the row already has `job_state` (from `/seats` `jobState`). Name the detail's state
`job_detail_state`, and keep the old key untouched.

Update `_sample_data()` and the frozen-shape agreement tests with realistic values: the hunt row, a bundle-500 oracle
row, a completed review row, and a row with no point.

### 3.4 G1 — list answer types beyond `address[]`

In the answer.json normalisation (`_seat_answer`), any other `…[]` type whose items are all strings that fullmatch
`0x[0-9a-fA-F]{1,64}` or `[0-9]{1,78}` gives the items joined by one space, at most 20; otherwise `None`.
- RECORD shows `N values` (`1 value`).
- The ANSWER popup lists one per line: hex through the full string, no icon (not an address) and no link.
- The live `bytes32[]` fixture (§4 capture) must show `N values`, not `—`.

## 4. Fixtures (live capture, once, by you, keyless GET)

Extend `tests/scripts/` with a `capture_submissions.py` (or a mode of the oracle capture script), the same MANIFEST
discipline (sha256, bytes, UTC capture time, control-plane commit from `/version`). Capture under
`tests/fixtures/surf/swarm/submissions/`:
- `/jobs/7b9c907d-99b9-405b-8491-6088c77d4cc9/submissions` and `/jobs/7b9c907d-…`: the hunt job
- the submissions and job for seat 420's `2d73c9e2…` (oracle, `bundle upload failed (500)`)
- one completed non-oracle job of seat 420 (review or build) if the window has one; the v4 `submissions_33016bad`
  fixture may serve if none is live
- the oracle detail (`?members=`) for `4c11a919…` (the `bytes32[]` request) under `oracle/filtered/`

Tests never touch the network. The transport serves these, and raises on anything else.

## 5. Work packages

**WP0 — contract.** All keys and fields of §3, the new slot constant, and the agreement tests.
Commit `feat(surf): freeze submission popup keys and job-detail slot`.

**WP1 — data.**
- The §4 capture first.
- Reply facts in `submission_answer`, with the cleaning and caps of §3.1.
- The byte-budget helper, hoisted and shared.
- `SLOT_SWARM_JOB_DETAIL`: extraction, per-point coercion, prune, and the due/cap logic in `surf_manager`.
- The row fold.
- G1.

Tests, from fixtures plus hand-built hostile dicts:
- The hunt row carries `failure_reason == "local_build_failed"`, `turns == 61`, 7 others (6 `runtime_error`,
  1 `path_violation`) and `job_blocked_reason == "node hunt_b: runtime_error"`.
- A reply keeps its newlines and box characters, loses `/Users/<x>/…` paths and ANSI escapes, and a cut never
  leaves a fake address.
- The ≤ 8,000-byte bound holds, with every cascade step exercised (lesson F9).
- Old-shape answer points are dropped.
- A hostile field drops only its point.
- The job-detail slot: 2 reads per cycle, terminal jobs frozen, `blocked` re-read after 120 s, and a failed read is
  `unavailable`.
- Two hashes of one job each keep their own reply (lesson F2).
- `bytes32[]` → the value string.

**Prove:**
- Remove the newline allowance → the reply test goes red.
- Make `blocked` terminal → the re-read test goes red.
- Drop the per-point validation of `others` → the hostile test goes red.

Commit `feat(surf): submission reply, other seats and job detail facts`.

**WP2 — RECORD.**
- The button rule of §2.1: cut **or** failed/rejected. Two actions, one validator.
- The `‹ widen` exemption for any row with a button.
- G1's `N values`.
- Re-sweep RECORD in situ. AGENT 139×33 and the tiers 102/94/53 must not move.
- `RECORD_NEVER_CLEARS_BELOW`'s `#:` block says which rows still count toward it. Move the number only if the
  sweep says so, and stop if a pin moves.

Tests, composited:
- The uncut failed row has `»` with `open_submission`.
- A cut review row has `»`.
- A joined oracle row keeps `open_oracle_answer`.
- A `not read` row has no button.
- A row with a hostile id or hash has no button.
- The widen marker lights only for button-less cuts.

Commit `feat(surf): RECORD opens the submission popup`.

**WP3 — popup frame hoist.** Move the ANSWER popup's frame into the shared base (§2.2) with **no visible change**:
the ANSWER popup's tests pass unchanged. Commit `refactor(surf): one popup frame`.

**WP4 — SUBMISSION popup.** `screens/submission_detail.py` per §2.2, and `SurfScreen.action_open_submission`.

Pilot tests, awaiting observable state:
- The hunt row's popup shows `blocked · node hunt_b: runtime_error`, the NODES line, the objective, `failed ·
  local_build_failed`, the usage line, the excerpt note, the reply start, and 7 others with `#1` … `#1548`.
- The bundle-500 row shows its reply, without OTHER SEATS (oracle node) and without the excerpt note.
- `job_read = not_read` shows `not read yet`.
- Enter and escape close the popup, and the AGENT body is still showing afterwards.
- Two rows of one job open their own hash.
- Addresses in the reply get icons and no links.
- Geometry at 80×24, 139×33 and 40×12.
- A `[/x]` in any field cannot raise.

Commit `feat(surf): SUBMISSION popup`.

**WP5 — docs.**
- README "Keyboard shortcuts": the `»` click opens ANSWER or SUBMISSION.
- `rules/surf.md`: the persistence change, the new slot and the button rule.
- `rules/data.md` / `docs/imd_swarm_api.md`:
  - the measured submissions and job facts
  - the finding that a failed build publishes only an excerpt
  - `bytes32[]`
- `docs/surf_answer_popup_followups.md`: F-A2 done. Add anything you found.
- Run the doc-pinning tests (`rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`) and `-m guard`.

Commit `docs(surf): submission popup`.

## 6. Tests to run (named, plus `-m guard`)

```
tests/data/test_surf_swarm_answers*.py (whichever holds submission_answer) tests/data/test_surf_swarm_oracle.py
tests/data/test_surf_manager_oracle.py tests/data/test_surf_cache.py tests/data/test_surf_cache_swarm.py
tests/data/test_surf_swarm_client.py tests/data/test_surf_swarm_models.py
tests/widgets/test_surf_swarm_seat_record.py tests/screens/test_oracle_answer.py tests/screens/test_submission_detail.py
tests/screens/test_surf_screen.py        (whole file, once, after WP4)
tests/screens/test_surf_swarm_layout.py -k "agent or record or oracle or polish"
tests/test_address_rule.py tests/test_address_sweep_registry.py
-m guard
```

## 7. Stop conditions

- The base hash differs from `d0a7148`.
- A layout pin would move.
- A rule here contradicts CLAUDE.md or `rules/*.md` (report it as a plan defect).
- A named test cannot be made green.
- Anything that would need a key, a new endpoint, or network in a test.

## 8. Final report (one)

- Commits (hash and subject).
- Tests and counts.
- Which test went red for each proof.
- The sweep numbers before and after.
- The measured point sizes (typical and maximal).
- Which fixtures were captured, with their sizes.
- Every deviation, with its reason.

After you, the controller runs one task review per WP, a whole-branch review, one fix wave, one scoped re-review
and the full suite once. The owner decides the merge.
