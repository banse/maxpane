# SURFBOARD — AGENT body on `/seats/{tokenId}`: work-package plan

**Spec:** `docs/surf_agent_seats_spec.md` (APPROVED 2026-09-21, D1–D5 settled — not reopened here).
**Tier:** 2 (new endpoint, new contract keys, five AGENT widgets, a new cache tier, pins move).
**Precedence:** CLAUDE.md > spec > this plan > implementer report. A plan line that contradicts the
spec is a plan defect; a spec line that contradicts CLAUDE.md is a spec defect filed in §9, never
overruled in code.
**House style:** `docs/surf_swarm_v2_implementation_plan.md` (additive freeze in WP0, late flip,
`_KEYS_PENDING_CONSUMERS` carve-out). No sample code below — only signatures and key names.

---

## 0. Blocking questions — ANSWERED 2026-09-21, all three as recommended

The owner answered all three on 2026-09-21: **Q-A** add `"pending"`; **Q-C** the owner cell uses the package
`EXPLORER` (mainnet Etherscan), and the gap with rules/surf.md is filed as a follow-up; **Q-M** the hero shows
`72 · 6 pending`. The table below records what was asked. Wherever the plan says "under Q-A", "per Q-M" or
similar, that decision now applies.

| # | question | why it blocks | recommendation |
|---|---|---|---|
| Q-A | `swarm_seat_state` is `"ok" \| "unknown_seat" \| None`, where `None` means both "not yet read" and "read failed, no last-good". §3 wants `Loading…` for the first and `unavailable` for the second, which that key cannot express. | Every AGENT widget renders a different word for each | Add `"pending"` to the state set: `None` = read failed and no last-good for this token; `"pending"` = no read of this token has finished yet (a switch in flight included). |
| Q-C | The owner cell's explorer. The spec says the package `EXPLORER` (D5, "Etherscan"). `rules/surf.md` says swarm addresses link by their own row's `chain_id`. | Which key the summary carries | Follow the spec: `EXPLORER` (`widgets/surf/_fmt.py:57`, `ETHEREUM`). `chainId` is `1` on all 8 captures. File the rules-vs-spec gap in the followups doc. Do not add `chain_id` to the summary. |
| Q-M | `reviewed` counts every review, so it includes the pending ones: #420 has 72 reviews = 66 sent + 5 submitted + 1 queued. The spec's `72 (+n pending)` reads as additive. | Hero wording, and the SEAT RECORD "by status" row | Freeze `reviewed = len(reviews)` and `review_status` as the spec says. In WP3, render `72 · 6 pending` (a subset), not `+6`. Owner to confirm the wording. |

---

## 1. Contract target (what WP0 freezes, what WP5 flips)

### 1.1 Keys in `SWARM_KEYS`

| key | status after this branch | shape |
|---|---|---|
| `swarm_seat_selected` | changed | `{token_id, agent_id, selected_by}`. `unseen_token` retires. `selected_by` stays in `cursor` / `saved` / `most_active`. |
| `swarm_seat_state` | **new** | `"ok" \| "unknown_seat" \| None` (plus `"pending"` if Q-A is accepted) |
| `swarm_seat_summary` | changed | `{attempts, accepted, reviewed, review_status, mean_score, scored, roles, online, owner, paired_ts, last_active_ts, collaborators, runtime}` |
| `swarm_seat_work_rows` | **new** (replaces `swarm_seat_node_rows`) | row keys: `job_id, node_key, role, job_state, objective, accepted_ts` |
| `swarm_seat_feedback_rows` | row shape changed | row keys: `value, verdict, status, node_key, role, job_id, tx_hash, chain_id, sent_ts` |
| `swarm_seat_as_of_hhmm` | re-sourced | the seat tier's marker (was the sweep's) |
| `swarm_roster_window` | **new** | `{jobs, oldest_ts}` |
| `swarm_seat_node_rows` | **retired in WP5** | — |
| `swarm_seat_rows` | unchanged (roster) | — |

Summary field notes (frozen as spec §4; every field is `None` when the source did not carry it):
- `review_status`: `{sent, submitted, queued}`, ints.
- `roles`: `[{role, count}]`, from `reviews[].role`, sorted by count descending, then role.
- `collaborators`: an int, `len(collaborators[])`.
- `runtime`: the raw `"<id> <version>"` of `runtimes[0]`, or `None` if the list is empty. Clipping happens at the widget (see §9 D).
- `last_active_ts`: the newest of `acceptedAt` / `sentAt`.
- `paired_ts`: `pairedAt` parsed to a timestamp.
- `owner`: the 0x string, validated with `fullmatch` at the widget, not in the fold.

### 1.2 New permanent exports in `data/surf_models.py` (WP0)

`SWARM_SEAT_SELECTED_FIELDS`, `SWARM_SEAT_SUMMARY_FIELDS`, `SWARM_SEAT_REVIEW_STATUSES = ("sent", "submitted", "queued")`,
`SWARM_SEAT_STATES` (`("ok", "unknown_seat")`, plus `"pending"` under Q-A), `SWARM_ROSTER_WINDOW_FIELDS = ("jobs", "oldest_ts")`.

### 1.3 Transitional exports (WP0 adds them, WP5 deletes them)

- `SWARM_SEAT_FEEDBACK_ROW_KEYS_NEXT`: the target feedback row tuple.
- `SWARM_AGENT_SIGNATURES_NEXT`: the target entries for the five AGENT widgets:

| widget (class name unchanged) | target signature |
|---|---|
| `SurfSwarmAgentHero` | `swarm_seat_selected, swarm_seat_summary, swarm_seat_state, swarm_seat_as_of_hhmm` |
| `SurfSwarmRoster` | `swarm_seat_rows, swarm_seat_selected, swarm_roster_window, swarm_scores_as_of_hhmm` (§9 F) |
| `SurfSwarmSeatVerdicts` (title becomes `SEAT RECORD`) | `swarm_seat_summary, swarm_seat_state, swarm_seat_as_of_hhmm` |
| `SurfSwarmSeatRecord` (title stays `RECORD`) | `swarm_seat_work_rows, swarm_seat_state, swarm_seat_as_of_hhmm` (`swarm_network` dropped) |
| `SurfSwarmSeatFeedback` | `swarm_seat_feedback_rows, swarm_seat_state, swarm_seat_as_of_hhmm` |

**Why the flip is late.** The screen dispatch at `screens/surf.py` ~4185 reads `SWARM_WIDGET_SIGNATURES`
generically. Flipping the export before the widgets accept the new keys raises `TypeError` in every
screen test. So:
- WP3 and WP4 build to `…_NEXT`, and keep each retiring name as a **named, ignored parameter** defaulting to `None`.
- WP5 flips the export, deletes `…_NEXT`, and removes the ignored parameters.

---

## 2. Work packages

Dependency order and parallelism:

```
WP0 ──► WP1a ─┐
   └──► WP1b ─┴─► WP2 ──► WP3 ─┐
                         └─► WP4 ─┴─► WP5 ──► WP6 ──► WP7 (final review, fix wave, suite)
```

- **WP1a ‖ WP1b** (disjoint files).
- **WP3 ‖ WP4** (disjoint files; both read `surf_models.py` and neither edits it).
- Everything else runs serially.

Shared-file owners (one at a time, each sequentially owned):

| file | owners |
|---|---|
| `data/surf_models.py` | WP0, then WP5 |
| `tests/screens/test_surf_screen.py` | WP0, then WP5 |
| `tests/test_surf_registration.py` | WP0, then WP5 |
| `tests/data/test_surf_swarm_models.py` | WP0, then WP5 |
| `data/surf_swarm.py` | WP1b, then WP5 |
| `analytics/surf_swarm_signals.py` | WP5 only |
| `screens/surf.py` | WP6 only |
| `themes/minimal.tcss` | WP6 only |
| `tests/screens/test_surf_swarm_layout.py` | WP5 (payload builders), then WP6 (re-sweep) |
| `README.md` | WP6 only |

Named test command (every WP): `.venv/bin/python -m pytest <named files>` then
`.venv/bin/python -m pytest -m guard tests sybilkit/sybilkit_tests` (seconds). Never a directory, never the suite.

### WP0 — fixtures, API doc, contract freeze (additive)

**Files owned**
- `tests/fixtures/surf/swarm/seats/` (new): the fixture files and `MANIFEST.json` below.
- `tests/surf_swarm_fixtures.py`: loader `swarm_seat_capture(name: str) -> dict`.
- `tests/data/test_surf_swarm_fixtures.py`.
- `docs/imd_swarm_api.md`.
- `maxpane_dashboard/data/surf_models.py` (pass 1).
- `tests/data/test_surf_swarm_models.py` (pass 1).
- `tests/data/test_surf_models.py`.
- `tests/screens/test_surf_screen.py` (pass 1).
- `tests/test_surf_registration.py` (pass 1).

**Fixtures** (copied byte-for-byte from the session scratchpad `seat_capture/`; not re-fetched, not edited):

| target file | source | what it pins |
|---|---|---|
| `seat_420.json` | `420.json` | the defect seat: attempts 74, accepted 12, 72 reviews (66 sent / 5 submitted / 1 queued with `txHash`/`chainId`/`sentAt` null) |
| `seat_0.json` | `0.json` | the largest seat (90 KB, 202 reviews): `online:false`, `runtimes:[]` |
| `seat_1649.json` | `1649.json` | the `codex` runtime, `"codex-cli 0.149.0"` |
| `seat_516.json` | `516.json` | the smallest seat: 10 / 4, one `submitted` review |
| `unknown_seat_404.json` | same | the 404 body |
| `invalid_request_400.json` | same | the 400 body |
| `jobs_window_100.json` | same | `/jobs` at `count: 100` |
| `job_80c853bd_winner_only.json` | same | a competitive detail listing the winner only |
| `MANIFEST.json` | new | for each file: host, route, HTTP status, UTC capture time, `/version`, and one line of selection criteria (the v2 corpus MANIFEST style) |

**`docs/imd_swarm_api.md`**
- Line 30: `/jobs` becomes "newest 100 jobs; `count` is the page length; no pagination; parameters ignored". Keep the 2026-09-16 "62 jobs" reading as history.
- Line 40: remove `/seats` from the absent routes.
- Add a `/seats/{tokenId}` section: the field table (spec §2), the three review statuses, 404 `unknown_seat`, 400 `invalid_request`, and `/seats` with no id → 404.

**Symbols in `surf_models.py`**
- `SWARM_KEYS`: add `swarm_seat_state`, `swarm_seat_work_rows`, `swarm_roster_window`. Annotate `swarm_seat_node_rows` with `# retired in WP5`.
- `SURF_ROW_KEYS`: add `swarm_seat_work_rows`. Leave `swarm_seat_feedback_rows` at its current shape.
- Add the exports in §1.2 and the `_NEXT` exports in §1.3.
- `SWARM_WIDGET_SIGNATURES`: **unchanged** in WP0.

**Tests**
- `test_surf_swarm_fixtures.py`:
  - every MANIFEST entry exists and parses;
  - the defect numbers read off the files (74 / 12 / 72; the 66/5/1 status split; the queued review with its null fields);
  - `jobs_window_100.json` has `count == 100 == len(jobs)`.
- `test_surf_swarm_models.py`: the `_NEXT` tuples and the §1.2 exports as hand-typed literals, compared with exact equality.
- `test_surf_models.py`: raise the `SURF_KEYS` count tripwire by 3.
- `test_surf_screen.py`:
  - put the 3 new keys in `_KEYS_PENDING_CONSUMERS` (line 792);
  - add a sample `swarm_seat_work_rows` row to `_sample_data`, so the row-shape walk (~5833) has one per declared shape.
- `test_surf_registration.py`:
  - triage the 3 new keys in `_NON_NUMERIC_KEYS`;
  - fix the stale F20 comment (~1393) while the file is open.

**Mutation proof:** none (literal freeze). A reviewer spot-checks that deleting one new key from `SWARM_KEYS` reddens `test_surf_models.py` and the pending carve-out.

**Named tests:** `tests/data/test_surf_swarm_fixtures.py tests/data/test_surf_swarm_models.py tests/data/test_surf_models.py tests/screens/test_surf_screen.py tests/test_surf_registration.py`, plus `-m guard` (the guard set covers the `docs/` pinning tests).

**Must NOT touch:** any `maxpane_dashboard/` file other than `surf_models.py`; the v2 fixture corpus; `SWARM_WIDGET_SIGNATURES`.

### WP1a — `SwarmClient.fetch_seat` (parallel with WP1b)

**Files owned:** `maxpane_dashboard/data/surf_swarm_client.py`, `tests/data/test_surf_swarm_client.py`.

**Symbols**
- Add `SwarmClient.fetch_seat(token: int) -> dict | None`.
- Add the module constant `UNKNOWN_SEAT = {"error": "unknown_seat"}`. It is a normalised result, returned as a fresh copy, not a shared mutable.
- Add a private `_get` variant, or a keyword on `_get`, that hands a 404 body back to the caller. Today's `_get` discards non-200 bodies.

**Rules**
- A token that is not an `int`, is a `bool`, or is negative returns `None` **before any request** (the `fetch_job` / `_is_path_segment` precedent). The path is `f"/seats/{token:d}"`; caller text never reaches it.
- 200 with a JSON object → the dict.
- 404 whose JSON `error == "unknown_seat"` → `UNKNOWN_SEAT`. This is an answer: stop, no rotation.
- 404 with any other body (a removed route, an HTML page) → rotate; if every host fails → `None`. A missing route must never render "never paired".
- 400, any other non-200, a transport error, or non-JSON → rotate, then `None`.
- Same pacing, host pool and `follow_redirects=False` as the other reads.

**Tests** (`httpx.MockTransport` over the committed fixtures; the raising transport elsewhere):
- each of the six branches above;
- the host is rotated on 400 and on a non-`unknown_seat` 404, and not rotated on `unknown_seat`;
- a bool, a negative, a `str` and `"1?x"` issue zero requests.

**Mutation proof:**
- (1) treat every 404 as `unknown_seat` → the "removed route" test reddens;
- (2) drop the bool guard → the zero-request test reddens.

**Named tests:** `tests/data/test_surf_swarm_client.py tests/data/test_surf_manager_swarm.py` (the client's consumer), plus `-m guard`.

**Must NOT touch:** `surf_swarm.py`, `surf_manager.py`, `surf_cache.py`, `surf_models.py`.

### WP1b — the pure seat fold (parallel with WP1a)

**Files owned:** `maxpane_dashboard/data/surf_swarm.py` (pass 1: additions only), `tests/data/test_surf_swarm_seats.py` (new).

**Symbols added** (pure: no clock, no I/O; names are final):
- `seat_state(payload: object, token: int) -> str | None`:
  - `UNKNOWN_SEAT` → `"unknown_seat"`;
  - a dict whose `tokenId` parses to `token` → `"ok"`;
  - anything else, including a **`tokenId` mismatch** → `None`.
- `seat_summary_from_seat(payload: dict) -> dict`: exactly `SWARM_SEAT_SUMMARY_FIELDS`. Every field is `None` when absent or ill-typed. `value` is counted only when it is a real number, not a `bool`.
- `seat_work_rows(payload: dict) -> list[dict]`: exactly the `swarm_seat_work_rows` row keys, in source order (newest first).
- `seat_review_rows(payload: dict) -> list[dict]`: exactly `SWARM_SEAT_FEEDBACK_ROW_KEYS_NEXT`. `queued` → `tx_hash` / `chain_id` / `sent_ts` are `None`.
- `roster_window(jobs: object) -> dict | None`: `{jobs, oldest_ts}` over the `/jobs` list; `None` for a non-list.
- `choose_seat(rows: list[dict] | None, saved_token: int | None, cursor_token: int | None) -> dict | None` (D1):
  - the cursor, if it is on the roster;
  - else the saved seat, **whether or not it is on the roster** (`agent_id` taken from its roster row if present, else `None`);
  - else `rows[0]` as `most_active`;
  - `None` when there are no rows and no saved seat.
- `coerce_seat_slot(payload: object) -> dict | None`: the per-field validator for the persisted slot `{token, state, seat}`.
  - `token` must be an `int`, not a `bool`, and ≥ 0;
  - `state` must be in `SWARM_SEAT_STATES`;
  - `seat` must be a `dict`, or `None` iff the state is `unknown_seat`;
  - anything else → `None` (the slot is discarded, never half-trusted).
- Add each name to `__all__`.

**Kept for now** (retired in WP5): `pick_seat`, `seat_node_rows`, `seat_feedback_rows`.

**Tests:**
- Every fixture seat folds to the spec's numbers:
  - #420: 12 of 74, reviewed 72, `review_status` 66/5/1, scored 72;
  - #0: `online False`, runtime `None`;
  - #1649: runtime `"codex codex-cli 0.149.0"`;
  - #516: 4 of 10.
- A hand-edited payload with the wrong types in each field gives `None` for that field only.
- `seat_state` with a mismatched `tokenId` → `None`.
- The `choose_seat` truth table, including saved-off-roster and saved-with-`None`-rows.
- `coerce_seat_slot` refuses a `bool` token, an unknown state, `seat=None` with `"ok"`, and a list payload.
- Row tuples equal the frozen shapes (`tuple(row) == …`).

**Mutation proof:**
- (1) count a `bool` `value` as a score → the #420 scored test reddens;
- (2) remove the `tokenId` mismatch check → the mismatch test reddens;
- (3) let `choose_seat` require the saved seat on the roster → the D1 test reddens.

**Named tests:** `tests/data/test_surf_swarm_seats.py tests/data/test_surf_swarm_v2.py tests/data/test_surf_manager_swarm.py`, plus `-m guard`.

**Must NOT touch:** `analytics/`, the existing fold functions' bodies, `surf_models.py`, `surf_swarm_client.py`.

### WP2 — seat tier, selection wiring, manager keys

**Files owned:**
- `maxpane_dashboard/data/surf_cache.py`
- `maxpane_dashboard/data/surf_manager.py`
- `tests/data/test_surf_manager_swarm.py`
- `tests/data/test_surf_cache_swarm.py`
- `tests/data/test_surf_cache.py` (only the `TIERS` / `SLOTS` literals)
- `tests/data/test_manager_seams.py` (only if the seat seam moves)

**Symbols in `surf_cache.py`**
- `TIER_SWARM_SEAT = "swarm_seat"`: added to `TIERS`.
- `TIER_TTL_SECONDS[TIER_SWARM_SEAT] = 120`.
- `TIER_FAILURE_BACKOFF_SECONDS[...] = 120` (§9 N).
- `SLOT_SWARM_SEAT`: added to `SLOTS`, with its comment block.
- `SurfCache.mark_due(tier: str) -> None`: makes `tiers_due(now)` include `tier` on the next call. It **does not** clear the last-good.
- `__all__` updated.

**Symbols in `surf_manager.py`**
- `_swarm_seat_task` in `__init__`; `close()` cancels it.
- `_spawn_swarm_seat(token: int)`: detached; one token per spawn. `_pool_swarm_seat(token)`:
  - calls `fetch_seat`;
  - on a dict or `UNKNOWN_SEAT` → `store_last_good(SLOT_SWARM_SEAT, {"token", "state", "seat"})` + `mark_fetched`;
  - on `None` → `mark_failed`; the last-good stays.
- `_cancel_swarm_seat()`.
- `select_seat` / `set_seat` stay plain attribute writes, plus `self.cache.mark_due(TIER_SWARM_SEAT)`. No await, no spawn inside them.
- `_cycle`:
  - pick the token with `sw.choose_seat` over the roster rows (from the scores slot, when it exists);
  - spawn the seat tier when `TIER_SWARM_SEAT` is due and no seat task is running;
  - if a task is running for a **different** token, cancel it and spawn for the new one (one seat per cycle, no fan-out);
  - capture the slot before the spawn (the swarm/scores precedent at 5871–5919).
- `_swarm_seat_keys(...)` rewritten. The seat tier is independent of the sweep; the roster keys still come from the sweep slot:
  - `swarm_seat_selected` from `choose_seat`. `agent_id` comes from the roster row, else the seat payload's `agentId`, else `None`.
  - `swarm_seat_state`, `swarm_seat_summary`, `swarm_seat_work_rows`, `swarm_seat_feedback_rows` come from `coerce_seat_slot(last_good)` **only when `slot.token == selected.token_id`**. Otherwise they are `None` / `"pending"` (Q-A); they are never A's numbers.
  - `unknown_seat` → the summary is `None`, the work and feedback rows are `[]`, the state is `"unknown_seat"` (§9 L).
  - `swarm_seat_as_of_hhmm` is the seat slot's `LastGood.as_of_hhmm`, and only when the token matches.
  - `swarm_roster_window` = `sw.roster_window(<the /jobs list the scores sweep read>)`.
  - `swarm_seat_node_rows` stays emitted (old fold) until WP5 retires it, so the pending screen tests keep a value.
- Stop importing `seat_summary` from analytics **only if** nothing in the manager still needs it for the transitional `swarm_seat_node_rows`/old summary. Otherwise leave the import to WP5.

**Tests:**
- `test_surf_cache_swarm.py`:
  - `mark_due` makes the tier due and keeps the last-good;
  - the TTL and backoff literals;
  - `TIERS`/`SLOTS` membership;
  - the persisted slot round-trips; a hand-edited slot (bool token, unknown state) is refused per field.
- `test_surf_manager_swarm.py`, with an injected client and an injected clock:
  - the default is the most active seat; the saved seat wins **off the roster** (rewrites the test at 809, which asserted `unseen_token`);
  - the cursor; `set_seat` clears the cursor;
  - `select_seat` marks the tier due and awaits nothing (assert it is a plain function and makes no call on the client);
  - **seat switch while B's read is pending:** A's slot is present and B is selected → every seat key is `None`/`"pending"`, and no field equals A's;
  - `unknown_seat` → the state plus `[]` rows;
  - a failed read with a last-good for the same token → the last-good plus its as-of;
  - a failed read with no last-good → `None` (never `0`);
  - 400 → `None` + `mark_failed`;
  - queued reviews give rows with `tx_hash`/`chain_id`/`sent_ts` `None`;
  - one spawn per cycle, and a token change cancels the old task;
  - no sweep plus a saved seat → the seat keys are still served (the seat tier is sweep-independent); the old test at 853 changes meaning.
- `close()` cancels the seat task.

**Mutation proof** (the change is concurrency-shaped):
- (1) drop the token-match check → the switch test reddens;
- (2) spawn inside `select_seat` → the no-await test reddens;
- (3) clear the last-good in `mark_due` → the last-good test reddens.

**Named tests:** `tests/data/test_surf_manager_swarm.py tests/data/test_surf_cache_swarm.py tests/data/test_surf_cache.py tests/data/test_manager_seams.py tests/screens/test_surf_swarm_screen.py`, plus `-m guard`. The screen test must stay green: WP2 changes only values, not the export.

**Must NOT touch:** `surf_models.py`, `surf_swarm.py`, `surf_swarm_client.py`, any widget, `screens/surf.py`.

### WP3 — hero + SEAT RECORD panel (parallel with WP4)

**Files owned:**
- `maxpane_dashboard/widgets/surf/swarm_agent_hero.py`
- `maxpane_dashboard/widgets/surf/swarm_seat_verdicts.py`
- `maxpane_dashboard/widgets/surf/_swarm_seat.py` (new; shared seat-state words, §9 O)
- `tests/widgets/test_surf_swarm_agent_hero.py`
- `tests/widgets/test_surf_swarm_seat_verdicts.py`
- `tests/widgets/test_surf_swarm_seat_state.py` (new)

**`_swarm_seat.py`** (created by WP3; WP4 imports it read-only and waits for WP3's commit, or WP3 lands this file first as its own commit):
- `NEVER_PAIRED_TEMPLATE` (`#{token} never paired`);
- `seat_state_line(state, token) -> Text | None`: `None` when `state == "ok"`, `LOADING` for pending, `UNAVAILABLE` for `None`.

**Hero changes**
- `BOX_IDS` / `BOXES` → `seat, accepted, reviewed, score, collab, status` (six, same geometry).
- `NODES`, `VERDICTS` and `REVISIONS` are removed (D2).
- `update_data` names the `SWARM_AGENT_SIGNATURES_NEXT` hero entry. It carries no retiring parameter: the hero's old keys are a subset.
- Remove the `unseen_token` branch (`_seat_body` 140–148) and its yellow `#N not seen`.
- `unknown_seat`: the SEAT box shows `#N never paired`; the other five show a dim `—`, not `unavailable`.
- Box contents:
  - ACCEPTED `12 of 74`;
  - REVIEWED per Q-M;
  - SCORE `1.00` + `(72 scored)`;
  - COLLAB `24 seats`;
  - STATUS `online ●`/`offline ○` + `last HH:MM`.
- A zero renders `0`; only `None` renders `unavailable`.

**SEAT RECORD changes** (`SurfSwarmSeatVerdicts`):
- `TITLE = "SEAT RECORD"`. `ROW_IDS` / `BLOCK_IDS` rebuilt:
  - accepted of attempts;
  - reviewed by status;
  - score;
  - paired `MM-DD HH:MM`;
  - runtime (`sanitize_cell`, clipped);
  - owner (`address_text(..., explorer=EXPLORER)` in its windowed short form: `max-width: 46` cannot hold 42 characters plus a label; see §5);
  - the by-role block.
- The `codes` block and the rejected / revisions / working / first rows are removed.
- `update_data(swarm_seat_summary, swarm_seat_state, swarm_seat_as_of_hhmm)`.
- The owner is a pre-built `Text` (no markup interpolation); the runtime and the roles go through `sanitize_cell`.

**Tests** (composited `render_strips()`, not content strings):
- the signature binding test at `test_surf_swarm_agent_hero.py:98` rebinds to `…_NEXT`;
- the #420 fixture fold renders `12 of 74`, 72, and the pending count;
- state `None` → `unavailable` behind as-of;
- `"unknown_seat"` → `#420 never paired`;
- pending → `Loading…`;
- a hostile runtime `"[/x]"` and a hostile role render literally;
- the owner cell carries `⧉` and links `ETHEREUM` (`address_probe.LinkRecorder`);
- the `unseen_token` tests at 146–165 are **deleted**, and the file's docstring loses change A's text;
- a zero-attempts summary renders `0 of 0`, not `unavailable`.

**Mutation proof:** (1) render `0` for `None` → the failed-read test reddens; (2) drop `sanitize_cell` on the runtime → the hostile-string test reddens.

**Named tests:** the three test files above, `tests/widgets/test_surf_widget_contract.py`, `tests/widgets/test_panels.py`, `tests/widgets/test_title_blank_row.py`, plus `-m guard`.

**Known transitional red:** `tests/screens/test_surf_swarm_screen.py` and `test_surf_swarm_layout.py` a-body cases (the dispatch still sends old keys, so the new params get `None`).
- The implementer runs the screen test **once** and lists every red test id in the report.
- The reviewer checks that each one is an AGENT-content assertion.
- WP5 and WP6 turn them green.
- Any red outside the AGENT body blocks the WP.

**Must NOT touch:** `surf_models.py`, `screens/surf.py`, `minimal.tcss`, WP4's files, `_swarm_table.py`, `address.py`, `explorer.py`.

### WP4 — RECORD, FEEDBACK, ROSTER title (parallel with WP3)

**Files owned:**
- `maxpane_dashboard/widgets/surf/swarm_seat_record.py`
- `maxpane_dashboard/widgets/surf/swarm_seat_feedback.py`
- `maxpane_dashboard/widgets/surf/swarm_roster.py`
- `tests/widgets/test_surf_swarm_seat_record.py`
- `tests/widgets/test_surf_swarm_seat_feedback.py`
- `tests/widgets/test_surf_swarm_roster.py`

**RECORD changes**
- Column specs: `when, job, node, role, state, objective`.
  - `when` is `accepted_ts`; `state` is `job_state`.
  - `objective` is `sanitize_cell`, clipped with a visible `…`, and is the flex column. It replaces `detail`.
- Removed: `try`, `rev`, `verdict`, `detail`, `_verdict_cell`, `_detail_cell`, `DETAIL_MIN_COLS`.
- `JOB_COLS` / `NODE_COLS` stay (feedback imports them).
- `update_data(swarm_seat_work_rows, swarm_seat_state, swarm_seat_as_of_hhmm, swarm_seat_node_rows=None, swarm_network=None)`. The last two are ignored and removed in WP5.
- `ROW_CAP`: keep `40` (§9 G). The footer names the rows not shown: `+N older`.
- `FULL/COMPACT/TIGHT` are re-measured in WP6. WP4 sets provisional values from `table_cols` and says so in the `#:` comment.

**FEEDBACK changes**
- Column specs: `when, value, node, job, status, chain, tx`.
  - `when` is `sent_ts`, else the status word (`submitted`/`queued`, dim).
  - `status` is a new column.
  - `tx`: `hash_text(tx_hash, explorer=for_chain_id(chain_id))`; empty when `tx_hash is None` (queued).
  - `chain`: `chain_word(chain_id)`; `—` when `None`.
- `block_number` handling is removed.
- `update_data(swarm_seat_feedback_rows, swarm_seat_state, swarm_seat_as_of_hhmm)`.
  - The rows are read by the NEXT row shape.
  - During the transition the dispatch still sends old-shape rows. Rows missing a NEXT key render `—` in that cell, never raise.
- `ROW_CAP`: keep `12`, plus the `+N older` footer (§9 G).

**ROSTER changes**
- The title is `ROSTER · last {jobs} jobs since HH:MM · as of HH:MM`, built from `swarm_roster_window` and the roster's own marker.
- `swarm_roster_window is None` → `ROSTER · job window unknown · as of HH:MM`. It never omits the window words while showing window-scoped numbers (the spec §3 rule).
- `update_data(swarm_seat_rows, swarm_seat_selected, swarm_roster_window, swarm_scores_as_of_hhmm, swarm_seat_as_of_hhmm=None)`. The last is ignored and removed in WP5.
- Title assembly goes through `SwarmTableBase._render_title` if it accepts a prefix. If it does not, **report it** (a shared `_swarm_table.py` change is WP-scoped out; §9 P).

**Shared behaviour for all three panels**
- `swarm_seat_state == "unknown_seat"` → the `NEVER_PAIRED_TEMPLATE` line.
- `None` → `UNAVAILABLE_LINE` behind as-of.
- pending → `LOADING`.
- `[]` with `"ok"` → the panel's real-empty word.

**Tests** (composited):
- the signature and row-shape binding rebind to `…_NEXT`;
- #420 RECORD shows 12 rows, newest first;
- #0 FEEDBACK shows 12 rows plus `+190 older`;
- the queued row has no tx cell and no link;
- the submitted row's `when` is `submitted`;
- a hostile objective and a hostile node key render literally;
- the ROSTER title shows `last 100 jobs since 02:26` from `jobs_window_100.json`;
- the tx links via `for_chain_id(1)` and an unknown chain id links nothing;
- the `None` / `[]` / `unknown_seat` / pending cases stay distinct.

**Mutation proof:**
- (1) link a queued row's `None` tx → the queued test reddens;
- (2) drop the window words from the ROSTER title → the title test reddens;
- (3) render `EMPTY_LINE` for `None` → the failed-read test reddens.

**Named tests:** the three test files above, `tests/widgets/test_surf_widget_contract.py`, `tests/widgets/test_title_blank_row.py`, `tests/screens/test_address_icons_everywhere.py -k surf`, plus `-m guard`.

**Known transitional red:** same as WP3, with the same listing duty.

**Must NOT touch:** `_swarm_table.py`, `_swarm_chain.py`, `_swarm_seat.py` (read-only), `surf_models.py`, `screens/surf.py`, WP3's files.

### WP5 — contract flip + retirement of the window-based seat path

**Files owned:**
- `maxpane_dashboard/data/surf_models.py` (pass 2)
- `maxpane_dashboard/data/surf_swarm.py` (pass 2)
- `maxpane_dashboard/analytics/surf_swarm_signals.py`
- `maxpane_dashboard/data/surf_manager.py` (pass 2: only the lines emitting `swarm_seat_node_rows` / old summary imports)
- the five AGENT widget files (pass 2: delete the ignored parameters only)
- `tests/data/test_surf_swarm_models.py` (pass 2)
- `tests/screens/test_surf_screen.py` (pass 2)
- `tests/test_surf_registration.py` (pass 2)
- `tests/data/test_surf_swarm_v2.py`
- `tests/analytics/test_surf_swarm_signals.py`
- `tests/data/test_surf_manager_swarm.py` (pass 2)
- `tests/screens/test_surf_swarm_screen.py`
- `tests/screens/test_surf_swarm_layout.py` (pass 1: `_capture_payload` / `_worst_agent_payload` rebuilt on the WP1b fold and the committed seat fixtures; **no pin value changes**)

**Symbols**
- `SWARM_WIDGET_SIGNATURES`: the five AGENT entries become the `_NEXT` values.
- Deleted: `SWARM_AGENT_SIGNATURES_NEXT`, `SWARM_SEAT_FEEDBACK_ROW_KEYS_NEXT`.
- `SURF_ROW_KEYS["swarm_seat_feedback_rows"]` becomes the target shape.
- `swarm_seat_node_rows` is removed from `SWARM_KEYS` and `SURF_ROW_KEYS`.
- `test_surf_models.py` tripwire: WP5 owns that one-line change. Add the file to WP5's set.

**Test-side flips**
- The 3 keys leave `_KEYS_PENDING_CONSUMERS`.
- `swarm_seat_node_rows` leaves `_NON_NUMERIC_KEYS` and `_sample_data`.
- The sample feedback row is reshaped.

**Retirement:** see §3. The WP5 rows are done here.

**Tests:**
- `test_surf_swarm_screen.py`:
  - the picker tests (169–232) are rewritten for D1;
  - the seat-prompt tests (277–340) assert `#N never paired` for an unknown saved seat instead of `not seen`;
  - selecting a roster row issues **no** client call from the handler (spy client), then the next refresh shows the new seat;
  - **switch-pending composite:** A's slot plus B selected → no A number anywhere on the composited AGENT body.
- Widget tests rebind from `_NEXT` to `SWARM_WIDGET_SIGNATURES`.

**Mutation proof:** re-add `swarm_seat_node_rows` to one signature → `test_surf_keys_covers_the_local_signature_map` / the named-param check reddens (proves the flip is bound).

**Named tests:** every file above, plus `tests/data/test_surf_models.py`, `tests/data/test_surf_swarm_seats.py`, and `tests/screens/test_dashboard_screen.py -k surf`, plus `-m guard`.

**Allowed red:** `test_surf_swarm_layout.py` a-body **sweep** cases only (`-m sweep`); WP6 re-certifies them. Every non-sweep test in that file is green.

**Must NOT touch:** `screens/surf.py`, `minimal.tcss`, pin constants and their `#:` blocks, `README.md`, `builders.py`.

### WP6 — screen, CSS, layout re-sweep, address sweep, README, rules

**Files owned:**
- `maxpane_dashboard/screens/surf.py`
- `maxpane_dashboard/themes/minimal.tcss`
- `tests/screens/test_surf_swarm_layout.py` (pass 2)
- `tests/address_sweep/builders.py`
- `README.md`
- `.claude/skills/terminal-layout/SKILL.md` (pin table only)
- `.claude/rules/surf.md`

**Screen, CSS and pins**
- `screens/surf.py`: the CSS block (2931–2963) mirrored byte-identically in `minimal.tcss` (~2390–2606, including its arithmetic comments), the §4 pins and `#:` blocks, and `_SCROLL_COLUMNS[MODE_AGENT]` if a container changes. The generic dispatch loop needs no edit; confirm it.
- `test_surf_swarm_layout.py`: `MEASURED_AGENT_COLUMNS`, `MEASURED_AGENT_ROWS`, `RECORD_NEVER_CLEARS_BELOW` (or its replacement), `_A_THRESHOLDS`, the boundary sweeps, and the pin-relation asserts (505–513).

**`builders.py`**
- `_surf_payload` / `SURF_SEEDED` seed the owner address under `("a",)` (it now renders one).
- The comment "`a` seeds no address" is corrected.
- The owner links on `ETHEREUM` = `SweepCase.explorer`, so `rows_pick_explorer` still holds.

**Docs**
- `README.md` (160–165, 435–439, 546–547): the AGENT body wording (lifetime vs window), the new hero boxes, the panel names, and the pin numbers **read from the `#:` block**, not re-derived.
- `rules/surf.md`:
  - the modes table's hero line;
  - the AGENT paragraph (the seat tier; `/seats` as lifetime, the roster as window);
  - `TIER_SWARM_SEAT` among the swarm tiers;
  - the RECORD exception wording.

**Tests:**
- the re-sweep (§4);
- `tests/screens/test_address_icons_everywhere.py` for surf `a` at 170 and at the agent pin;
- the README and SKILL doc-pinning tests.

**Mutation proof:** move one pin by 1 below its measured value → its boundary sweep reddens (the pin-move rule).

**Named tests:**
- `tests/screens/test_surf_swarm_layout.py tests/screens/test_surf_swarm_screen.py tests/screens/test_surf_screen.py tests/screens/test_address_icons_everywhere.py tests/test_address_sweep_registry.py`;
- every file named by `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`;
- plus `-m guard`.

**Must NOT touch:** `data/`, `analytics/`, any widget module (a widget width defect is **reported** to the controller, not fixed here), `surf_models.py`.

### WP7 — docs, final review, fix wave, suite

- **Controller-owned docs:**
  - `docs/surf_swarm_followups.md`: F24 reworded (selection now lands one detached read later); F26 closed by D1; F16 cross-referenced if the row pin moved; new residuals from §9.
  - `docs/decisions.md`: the withdrawn statements — `/jobs` = every job; `#N not seen`; VERDICTS; RECORD's verifier detail.
- **Final whole-branch review** on the most capable model, with the reviewer contract verbatim.
- **ONE fix wave** (a single implementer); **ONE scoped re-review** that verdicts only the sent findings.
- **Full suite once, by the controller, before merge:** `HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist loadfile sybilkit/sybilkit_tests tests`. Cite the count.
- No plan workspace is left behind. Never merge or push without the owner.

---

## 3. Retirement list

| item | where | removed by | gate |
|---|---|---|---|
| `unseen_token` hero branch (`_seat_body` 140–148), its tests (hero test 146–165), and the module docstring text from 4e4bc30 | `widgets/surf/swarm_agent_hero.py`, `tests/widgets/test_surf_swarm_agent_hero.py` | WP3 | — |
| `unseen_token` in `pick_seat` + manager test at 809 | `data/surf_swarm.py`, `tests/data/test_surf_manager_swarm.py` | WP2 rewrites the test for D1; WP5 deletes `pick_seat` | `rg -n 'unseen_token' maxpane_dashboard tests` → only `docs/`-pinning hits, if any |
| `pick_seat` | `data/surf_swarm.py` + `__all__` + its tests | WP5 | no importer left |
| `swarm_seat_node_rows` (key, row shape, `_NON_NUMERIC_KEYS`, `_sample_data`, the manager emit) | `surf_models.py`, `test_surf_registration.py`, `test_surf_screen.py`, `surf_manager.py` | WP5 | `rg -n 'swarm_seat_node_rows' maxpane_dashboard tests` → 0 |
| `seat_node_rows` fold | `data/surf_swarm.py` + tests in `test_surf_swarm_v2.py` | WP5 | layout payload rebuilt first (WP5, same diff) |
| old `seat_feedback_rows(details, token)` (and so `block_number` in the rows) | `data/surf_swarm.py` + tests | WP5 | `rg -n 'block_number' maxpane_dashboard/data/surf_swarm.py maxpane_dashboard/widgets/surf/swarm_seat_feedback.py maxpane_dashboard/data/surf_models.py` → 0 |
| `block_number` column handling | `swarm_seat_feedback.py` | WP4 | — |
| window-based `seat_summary` (and its private helpers if they become unused: `_seat_nodes`, `_seen_node`, the `rejection_codes` rollup) | `analytics/surf_swarm_signals.py`, `tests/analytics/test_surf_swarm_signals.py` | WP5, **only if** `rg -n 'seat_summary\b'` finds no roster consumer | the roster's `seat_rows` does not use it (verify; keep what `seat_rows` needs) |
| VERDICTS rejection-codes block (`BLOCK_IDS["codes"]`) and the revisions / rejected / working / first rows | `swarm_seat_verdicts.py` + tests | WP3 | — |
| RECORD `try` / `rev` / `verdict` / `detail` columns, `_verdict_cell`, `_detail_cell`, `DETAIL_MIN_COLS` | `swarm_seat_record.py` + tests | WP4 | — |
| `swarm_network` in RECORD's signature | `surf_models.py` | WP5 (the flip) | — |
| `RECORD_NEVER_CLEARS_BELOW` (if the objective column always fits) | `screens/surf.py` `#:` block, the layout test, `rules/surf.md` | WP6 | measured, not assumed |
| transitional `_NEXT` exports and the ignored widget parameters | `surf_models.py`, the five widgets | WP5 | `rg -n '_NEXT\b' maxpane_dashboard tests` → 0 |

---

## 4. Layout work (WP6; every pin re-swept in situ, per the terminal-layout skill — measure, never derive)

| pin / floor | why it moves | where the number lives |
|---|---|---|
| `SURF_AGENT_FULL_LAYOUT_COLUMNS` (134) | The hero boxes change contents; ROSTER's title is longer; SEAT RECORD gains the owner cell; RECORD swaps `detail` for `objective`; FEEDBACK gains `status` | `screens/surf.py` `#:` block 1632–1671; `MEASURED_AGENT_COLUMNS` |
| `SURF_AGENT_FULL_LAYOUT_ROWS` (40) | The SEAT RECORD line count changes (codes block out; paired / runtime / owner / roles in) | `#:` block 1673–1683; `MEASURED_AGENT_ROWS` |
| `#surf-agent-top { min-height: 13 }` | A floor equal to SEAT RECORD's own fixed line count; re-count it | `screens/surf.py` CSS and `minimal.tcss`, identical |
| `SurfSwarmSeatVerdicts { max-width: 46 }` | The owner cell plus the label; a windowed short address keeps the width, and a full one moves it — measure both | CSS in both stylesheets |
| `SurfSwarmRoster { max-width: 86 }` | Only if the title clips at the pin (the title must never shorten away its window words) | CSS in both stylesheets |
| RECORD `FULL/COMPACT/TIGHT` (117/107/88) and `RECORD_NEVER_CLEARS_BELOW` (168) | New column set | `swarm_seat_record.py` + the `#:` block + the layout test |
| FEEDBACK `FULL/COMPACT/TIGHT` (77/67/37) | `status` column added | `swarm_seat_feedback.py` + the `minimal.tcss` comment |
| `_A_THRESHOLDS`, and the boundary sweeps at layout test 411–412 / 523–524 | Follow the pins | `tests/screens/test_surf_swarm_layout.py` |
| Pin relations at 505–513 (`AGENT < SWARM` columns and rows) | May no longer hold. If the agent pin passes the swarm pin, **report it** as a finding; do not delete the assert | the layout test |

- WP4 sets the provisional widget tiers. WP6 measures. A widget tier that must change after measuring is a WP6 finding sent back to the controller, who dispatches a scoped fix to the widget owner. WP6 does not edit widgets.
- F16 (the row pins exceed the owner's 35/31-row terminals) stays the owner's decision. This branch does not make it worse without saying so in the `#:` block and the followups.

---

## 5. Degraded states — the test matrix

| state | manager (WP2) | hero (WP3) | SEAT RECORD (WP3) | RECORD / FEEDBACK (WP4) | screen composite (WP5) |
|---|---|---|---|---|---|
| failed read, no last-good | all seat keys `None`; `mark_failed` | `unavailable` (never `0`) | `unavailable` + as-of | `UNAVAILABLE_LINE` | yes |
| failed read, last-good for the same token | last-good + its `as_of_hhmm` | numbers + as-of | same | rows + as-of | — |
| `unknown_seat` 404 (a real negative) | state `unknown_seat`, summary `None`, rows `[]` | `#N never paired` | never-paired line | never-paired line (not `EMPTY_LINE`) | yes (saved seat via `i`) |
| 400 `invalid_request` | `None` + `mark_failed` (client) | as failed | as failed | as failed | — |
| non-`unknown_seat` 404 (a route removed) | rotate → `None` | as failed (never "never paired") | — | — | — |
| seat switch A→B while B is pending | no key carries A's values; state `None`/`"pending"` | `Loading…` (Q-A) | `Loading…` | `LOADING` | **yes, assert no A number composited** |
| queued review (`txHash`/`chainId`/`sentAt` null) | row fields `None` | counted in pending | `queued 1` | `when` = `queued`, chain `—`, no tx cell, no link | — |
| submitted review (no `sentAt`) | `sent_ts None` | counted in pending | `submitted 5` | `when` = `submitted`, tx linked | — |
| persisted last-good hand-edited (bool token, unknown state, list seat, wrong-typed fields) | `coerce_seat_slot` → `None` slot; per-field `None` in the summary | `unavailable` on that field only | same | a row with a bad field keeps its row, `—` in that cell | — |
| `tokenId` mismatch in the payload | `seat_state` → `None` | as failed | — | — | — |
| zero counts (`attempts 0`) | `0`, not `None` | `0 of 0` | `0 of 0` | real-empty word | — |

---

## 6. Parallelism summary

- WP1a ‖ WP1b.
- WP3 ‖ WP4. They are disjoint files; `_swarm_seat.py` is created by WP3 and read by WP4, so WP3 commits it first or WP4 rebases on it.
- A parallel pair shares the one working tree only because their file sets are disjoint. No reviewer runs while a pair is still writing (a reviewer's inverse edit can collide with a live edit). Commit with pathspec (`git commit -- <files>`); no worktrees (the editable install resolves to the main checkout).
- WP0, WP2, WP5, WP6 and WP7 are serial.

## 7. Review cadence (Tier 2)

- One task review per WP diff (mid-tier model, reviewer contract verbatim). Fix rounds are capped at 2 per WP; residuals go to the followups doc.
- The reviewer mutates to verify and restores by inverse edit only. `git checkout` / `stash` / `reset` / `restore` / `clean` / `add` are forbidden, and the reviewer ends with `git status` clean. The tree holds untracked user docs; never touch them.
- The reviewer checks the implementer's listed transitional reds (WP3, WP4, WP5) against §2. An unlisted red is Important.
- WP7: the final whole-branch review on the most capable model, then ONE fix wave, then ONE scoped re-review, then the full suite once by the controller, then the followups doc updated.

## 8. Validation

- Each WP: its named test set plus `-m guard`, cited in the commit message.
- The branch is green end to end only after WP6. Between WP3 and WP6 the listed AGENT-content and `sweep` reds are expected, and nothing else.
- Before merge: the one suite run (WP7). A live smoke `python -m maxpane_dashboard --game surf`, then `a`, on seats #420, #0 and one unpaired id, is the owner's call. It is not a test and not run by any agent.

## 9. Risks and open questions (flagged, not decided against the spec)

- **A (spec gap):** `None` conflates pending with failed. Q-A: the recommended fix is a `"pending"` state.
- **B:** one slot means B's own last-good exists only if B was the last seat read. A switch back to A after a failed read shows `unavailable`, not A's older numbers. Acceptable per the spec text. A bounded per-token map is a follow-up if the owner wants it.
- **C:** `rules/surf.md` (per-row `chain_id`) vs spec D5 (package `EXPLORER`) for the owner. Q-C: follow the spec and file the gap.
- **D:** runtime wording. The spec shows `claude 2.1.278`; the source says `"2.1.278 (Claude Code)"` / `"codex-cli 0.149.0"`. The plan freezes the raw `"<id> <version>"` and clips at the widget. Any prettifying is an owner call, not a parser of vendor strings.
- **E:** "last 100 jobs" vs the roster also folding `SLOT_SWARM_JOBS_SEEN` (48 h). The roster's rows may cover more than the 100-job window, so the title may understate. Owner: either fold the roster from the window only, or title it as `jobs seen since HH:MM`. The plan implements the spec's title with `jobs = len(/jobs)`, `oldest_ts` = the oldest in that list, and files this.
- **F (spec gap):** the roster's marker key is not named. The plan uses `swarm_scores_as_of_hhmm`, because `swarm_seat_as_of_hhmm` is now the seat tier's.
- **G:** lifetime row caps. Seat #0 has 202 reviews. The plan keeps `ROW_CAP` 40 / 12 with a `+N older` footer. The spec says "one row per entry"; uncapped (`ROW_CAP=None`) is the alternative and costs render time on #0. Owner call.
- **H:** naming. The `SEAT RECORD` title (on `SurfSwarmSeatVerdicts`) sits beside `RECORD` (on `SurfSwarmSeatRecord`). Class names are kept to hold the signature map stable; renaming is a follow-up.
- **I:** `SWARM_SWEEP_CAP = 200` while `/jobs` serves 100. That is harmless but misleading; file it.
- **J:** persisting a 90 KB seat payload in `surf_cache.json` on every 120 s tick (F7 write amplification). Store only when the token or payload changed (the jobs-seen precedent), and **measure** the file size before and after on #0. Any perf fix needs a number.
- **K:** latency. Selection lands one detached read after the next poll. F24 is reworded, not closed.
- **L:** `unknown_seat` renders RECORD/FEEDBACK as a never-paired line, not the real-empty word. That is the plan's reading of spec §3.
- **M:** `reviewed` includes pending (Q-M).
- **N:** the seat tier's failure backoff is unspecified; 120 s is the plan's choice (the `TIER_SWARM` value).
- **O:** the shared seat-state words module (`_swarm_seat.py`) is a new private file in the surf package, not a shared `widgets/*.py`, so it adds no Tier trigger. It exists so the never-paired literal is not typed four times.
- **P:** if `SwarmTableBase._render_title` cannot take the window prefix, the change touches `_swarm_table.py` (shared by the `s` body). That is then a separate owner and a Tier 2 concern: report it, do not widen WP4.
- **Q:** between WP3 and WP6 the branch has known reds. Bisecting inside that range is not meaningful; the commit messages say so.
