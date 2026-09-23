# PLAN — surf AGENT RECORD: PANEL and tok columns, short model names (handover §5B)

**Spec:** `docs/surf_oracle_panels_handover.md` §5B (owner-chosen 2026-09-23). 5A (ORACLE-tile line)
is **out of scope** here: the owner has not chosen it yet.
**Tier:** 2. It adds row keys to `data/surf_models.py`, reads a new endpoint, adds a cache slot, and
touches more than 6 files.
**Implementer:** Codex, one work package at a time, in the order below. Every WP touches different
files, but each one builds on the one before it, so do not run them in parallel.
**Branch:** `feature/surf-oracle-panels` from `main` @ `71289c9` (v0.9.1). Commit once per WP and
use the WP id in the subject: `feat(surf): WP2 oracle panel fold`.
**Precedence:** CLAUDE.md > handover §5B > this plan > implementer report. If this plan contradicts
the handover, it is listed in §0.2. Anything else is a plan defect: stop and report it.

Live facts were re-checked on 2026-09-23 at about 21:00 UTC. `GET /oracle/requests?limit=5` returns 200 with
`{count, attester, requests[]}`. A detail returns 200 with 27 keys, including `agreement.cluster[]` (64-hex
hashes) and `members[]{ok, answer{notes,…}, submissionHash, wallet, reason}`. `panelSize` was 15 and
`quorum` was 12 on the newest request.

---

## 0. Owner decisions

Owner-approved plan corrections (2026-09-23): failed list reads without a cached point store a nonterminal error point; the trailing-newline model test expects shortening after cleaning.


### 0.1 D1–D4: all four approved by the owner in chat on 2026-09-23

| # | question | decision | why |
|---|---|---|---|
| D1 | `compact` tier: with `role` gone, what does it drop? | drops `tok` | otherwise `full == compact`, and a ladder rung that sheds nothing fails the ladder tests |
| D2 | the panel cell when the oracle read **failed** (no cached point) | yellow `unavail` (7) | the repo's "unavailable" is yellow. The whole word is 11 cells |
| D3 | the panel cell for an oracle row that is **not fetched yet** | dim `not read` (8) | the same words the answer cell uses for the same state |

The widths behind D1 (the sum of `table_cols` estimates; WP5 re-measures them): full is about 102 cells, compact (no `tok`)
about 96, and tight about 53. Compact keeps `answer`, `model` and `took` for panels 96–101 cells wide.
| D4 | a pending row whose panel is `no-q` | the `state` cell still says `pending` (as served) | §5B says the PANEL column carries the "closed" answer. Changing `state` would be 5A-scope |

### 0.2 Where this plan departs from §5B (spec defects, filed here)

- **`panel` is 9 cells, not 8.** Panels run up to 112 members, so `✓ 105/112` is 9 cells. 8 would clip
  the widest real value. Derive the width in code (`1 + 1 + 3 + 1 + 3`), with a `#:` comment.
- **`tok` goes through `sparkline_common.fmt_compact`**, whose suffix is upper-case (`1.5K`, `22K`), not the
  handover's `1.5k`. That is the reuse rule: do not write a second compact formatter. `fmt_compact` prints `--` for a
  non-number, and this cell prints `—` (EMDASH, like `model`/`took`). Map it at the call site.
- **A 64-hex hash equal to the seat's hash, on a panel whose `jobId` appears twice in the list, is
  `unavailable`**, not the first match. This follows the rule `submission_answer` applies to duplicate hashes.

---

## 1. Data contract (frozen in WP1, before any fold or widget code)

### 1.1 `SURF_ROW_KEYS["swarm_seat_work_rows"]` gains, after `took_s`

```
"output_tokens",   # int | None; submission usage.outputTokens, same read as model/took_s
"panel_state",     # SWARM_PANEL_STATES
"panel_agreed",    # int | None; agreement.agreed
"panel_members",   # int | None; len(members)
"panel_size",      # int | None; panelSize (assessing denominator)
"panel_figure",    # str | None; agreement.figure, decimal STRING, never parsed to float
"panel_answer_type", # str | None; answerType ("uint256", "bool", …) as served, flattened
```

`role` **stays** in the data row, because other readers use it. Only the RECORD widget stops showing it.

### 1.2 New tuples in `surf_models.py`

```python
#: One per RECORD row. The first eight are joined outcomes (handover §3, §5B).
#: not_oracle = the row's node is not oracle_assess; off_panel = the list was read back past
#: the row's submittedAt and no request carries its jobId, or a final panel's members lack
#: its hash (failed runs never reach a panel) -- a real negative; not_read = not fetched
#: yet; unavailable = the read failed or was ambiguous, with no cached point.
SWARM_PANEL_STATES = (
    "agreed", "outvoted", "no_quorum_in", "no_quorum_out", "assessing", "blocked",
    "off_panel", "not_oracle", "not_read", "unavailable",
)
#: Oracle node key(s) whose rows are joined to /oracle/requests. Data-only: the
#: widget reads panel_state and never restates this tuple.
SWARM_ORACLE_NODE_KEYS = ("oracle_assess",)
#: SLOT_SWARM_ORACLE point fields (job UUID -> submission hash -> point). Extracted
#: facts only: never members' notes, never the question, never the raw detail.
SWARM_ORACLE_CACHE_FIELDS = (
    "request_id", "status", "in_cluster", "on_panel", "agreed", "members",
    "panel_size", "figure", "answer_type", "read_ts", "terminal",
)
```

`SWARM_ANSWER_FIELDS` and `SWARM_ANSWER_CACHE_FIELDS` gain `"output_tokens"`. The cache coercion already
requires `set(point) == set(SWARM_ANSWER_CACHE_FIELDS)`, so every cached answer point from before this change is
**dropped and re-read once** (4 jobs per cycle). That is intended: say so in the WP1 commit message and do
not add a legacy branch.

`SWARM_WIDGET_SIGNATURES["SurfSwarmSeatRecord"]` does **not** change. It still reads
`swarm_seat_work_rows`, which now has more fields.

---

## 2. Fetch strategy (the manager, WP3). Read the handover's traps §6 first

Run after `_pool_swarm_answers` inside `_pool_swarm_seat`, and only for state `"ok"`. Contain every call in `_guard`.
A failure stays local to this step and never fails the seat tier.

1. **Candidate rows** = RECORD's displayed window `rows[:SWARM_ANSWER_ROW_CAP]` (40) whose `node_key ∈
   SWARM_ORACLE_NODE_KEYS`, with a canonical `job_id` and a 64-hex `submission_hash`.
2. **Due rows** = candidates with no cached point, or with a cached point that is not `terminal` and is older than
   `SWARM_ORACLE_DUE_S` (120 s). If there are no due rows, **make no request at all**, not even the list. The
   steady state costs nothing once every visible panel is final.
3. **List walk**: `fetch_oracle_requests(limit=SWARM_ORACLE_PAGE_LIMIT, before=None)`, then keep paging with
   `before=<oldest createdAt of the previous page>` while (a) some due row's `job_id` is still unmatched,
   (b) the previous page was full (`len == limit`), (c) its oldest `createdAt` is **later** than
   the oldest unmatched due row's `submitted_ts` (a request is created before any submission to it),
   and (d) fewer than `SWARM_ORACLE_PAGE_CAP` pages have been read this cycle. Constants: `PAGE_LIMIT = 200`,
   `PAGE_CAP = 4`. Put each value in a `#:` block with the measurement behind it (590 requests over
   4.7 days on 2026-09-23, so about 125 a day).
   - A due row whose job is unmatched **after** the walk reached a page older than its `submitted_ts`, or reached
     a short page (the end of history), is `off_panel`, stored `terminal=True`.
   - A row that is still unmatched when the page cap stops the walk stays not_read. It gets no point.
   - A failed list read (`None`) ends the walk. Rows it could not settle keep their prior point; rows without a cached point receive a nonterminal `status: None` error point (`unavailable`).
4. **Details**: group the matched due rows by request id. Fetch at most `SWARM_ORACLE_PER_CYCLE = 4`
   details per cycle, unread before due, in displayed order (copy `answer_jobs_due`'s ordering).
   Each detail becomes one point per seat hash (§3). `terminal = status in ("attested","disagreed","blocked")`.
   `assessing` is never terminal.
5. **Slot** `SLOT_SWARM_ORACLE` (a new `surf_cache` slot beside `SLOT_SWARM_ANSWERS`, registered wherever
   that slot is: `surf_cache.py` lines ~178/219/1195, and any `__all__`). Prune it with
   `prune_oracle(payload, now_ts, cap=400, max_age_s=48h)`, copying `prune_answers`. Store it only when
   it changed (`prior.payload != new`), as the answers slot does.
6. **Keys**: `_swarm_seat_keys` passes the oracle entry to a new pure `sw.enrich_panel_rows(rows,
   oracle, node_keys)` after `enrich_work_rows`. **No new top-level payload key**, no new `as of`, and no
   degraded group (rules/surf.md: the swarm tiers name no group).

The list response is never persisted. The list is re-walked each cycle, but only while a row is due.

---

## 3. The join (pure, `data/surf_swarm.py`; handover §3 and §5B)

`oracle_point(detail, job_id, submission_hash, *, now_ts) -> dict | None`. It returns `None` for anything it cannot
trust, and the manager stores that as a `status: None` point in the `unavailable` state (terminal False).

- The detail must be a Mapping with `jobId == job_id`, `status` a str, `members` a list, and
  `agreement` either a Mapping or null (**assessing** and **blocked** panels may carry no agreement; capture one of each
  and code from the fixture, not from this sentence).
- Match on `submissionHash` only, **never on `wallet`** and never on `jobId` alone. More than one member with the
  seat's hash, where the members are not identical, is `None`.
- `in_cluster = hash ∈ agreement.cluster` (a list of 64-hex strings; a non-list is `None`).
  Membership only: **never compare figures**. The `toleranceBps` case (Pudgy) is in the cluster with
  an unequal figure.
- `figure`: `agreement.figure` if it is a `str` that fullmatches `-?[0-9]{1,80}(\.[0-9]{1,40})?`, else `None`.
  Never `float()`/`int()` it: wei values exceed 2^53.
- Counts: `agreed` from `agreement.agreed` (non-bool int ≥ 0), `members = len(members)`,
  `panel_size` from `panelSize` (non-bool int ≥ 0, else `None`).

`enrich_panel_rows` maps each point to `panel_state`:

| point | panel_state |
|---|---|
| node not in `SWARM_ORACLE_NODE_KEYS` | `not_oracle` |
| no point | `not_read` |
| point status `None` | `unavailable` |
| `off_panel` point, or status final and `on_panel` False | `off_panel` |
| `attested`, in cluster / not in cluster | `agreed` / `outvoted` |
| `disagreed`, in / not in | `no_quorum_in` / `no_quorum_out` |
| `assessing` | `assessing` (whatever `on_panel` says) |
| `blocked` | `blocked` |
| any other status string | `unavailable` (the vocabulary is open. Log it once at debug) |

`coerce_oracle_slot` validates each point on its own, like `coerce_answers_slot`: canonical UUID keys, 64-hex
sub-keys, the exact field set, types per §1.2, and `figure` against the same regex. It drops a bad point alone.
A hand-edited cache file is third-party input.

---

## 4. Client (WP1): `data/surf_swarm_client.py`

The client's rule is that no path carries a `?` (because `/jobs` ignores parameters). That rule **stays** for every
existing getter. Add a narrow exception:

- `_get(path, *, params: Mapping[str, str] | None = None, …)`: the `?`-in-path `ValueError` still
  applies. `params` goes to `httpx` as `params=` and is built **only** by the new getter.
- `fetch_oracle_requests(*, limit: int, before: str | None = None) -> list[dict] | None`:
  refuse (return `None`, no request) a `limit` that is a bool, is not an int, or falls outside 1–500. Refuse a `before` that does
  not fullmatch `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z`. Return `requests` if it is a list, else
  `None` (`[]` is a real empty and passes through).
- `fetch_oracle_request(request_id: str) -> dict | None`: `parse_job_id` (canonical UUID) before
  interpolating. A 400 `invalid_id` or a 404 is `None`: both mean failed reads for this purpose, and the route is one
  day old, so a removed route must degrade to `unavailable`, never to `off_panel`.
- Update the module docstring and the class docstring's route list.

Tests (`tests/data/test_surf_swarm_client.py` or wherever the client's tests already live: grep
`SwarmClient(`): an `httpx.MockTransport` that **raises on any unexpected URL**, and asserts the exact query string
for `limit`/`before`, the refusals (no request made), host rotation on 5xx, and a `?` in a path still raising.

---

## 5. Widgets (WP4)

### 5.1 `widgets/surf/_fmt.py`: `short_model(raw: object) -> str | None`

A rule, not a table (handover §5B). Run `strip_tags(flatten(raw))` **before** matching, then apply `re.fullmatch` only:

```
claude-(?P<fam>[a-z]+)-(?P<maj>\d+)(?:-(?P<min>\d+))?   -> "<fam> <maj>[.<min>]"
gpt-(?P<ver>\d+(?:\.\d+)?)-(?P<name>[a-z]+)             -> "<name> <ver>"
anything else                                            -> the cleaned id, unchanged (the caller clips)
```

It returns `None` for `None` or empty input. Test it on every row of the handover's table (8 ids plus `gpt-5.5` passing through)
and on hostile input (`[/x]`, a 200-character id, `claude-opus-5-5\n`, which becomes `opus 5.5` after the required cleaning removes the trailing newline).

### 5.2 RECORD (`widgets/surf/swarm_seat_record.py`)

- `_SPECS`: `when · job · node · state · model(9) · took(6) · panel(9) · tok(6) · answer`. Delete
  `_ROLE_COLS` and the `role` cell.
- Tiers: `_ALL` is every column. `_COMPACT` is `_ALL` minus `tok` (D1). `_TIGHT` is `_COMPACT` minus `answer`, `model` and
  `took`, so it keeps `panel`.
- `model` cell: `_usage_cell` logic unchanged (only for `read`/`no_reply`). Pass the value through
  `short_model` and then `sanitize_cell(…, 9)`.
- `tok` cell: under the same `read`/`no_reply` gate, a non-bool int ≥ 0 goes through `fmt_compact`, else `—`.
- `panel` cell (a `Text` or markup through `sanitize_cell` for the numbers):

  | panel_state | cell | style |
  |---|---|---|
  | agreed | `✓ {agreed}/{members}` | green |
  | outvoted | `✗ {agreed}/{members}` | red |
  | no_quorum_in | `✓ no-q` | dim green |
  | no_quorum_out | `✗ no-q` | dim red |
  | assessing | `… {members}/{panel_size}`, or `… {members}` when size is None | yellow |
  | blocked | `blocked` | dim |
  | off_panel, not_oracle | `–` | dim |
  | not_read | `not read` | dim (D3) |
  | unavailable | `unavail` | yellow (D2) |

  If a needed count is `None`, show `unavail`. Never print `None` or `?/?`.
- **Answer cell on red rows** (`outvoted` and `no_quorum_out`): prefix `panel <figure> · ` before
  the cleaned answer. For `answer_type == "bool"`, map the figure **only** from what a captured bool fixture shows
  (§6 WP0). If WP0 finds no bool request, leave the figure raw and file a follow-up. Clip as today, so
  `‹ widen` lights when the prefix pushes the answer past its width. Keep the prefix even when the answer
  state is not `read` (`panel 4571… · not read`).
- Update the module docstring (column list and the owner dates).

### 5.3 FLEET (`widgets/surf/swarm_fleet.py::_model_lines`)

Replace `strip_tags(flatten(model))` with `short_model(model)`. The effort word stays appended (`astra 6
xhigh`). There is no pin change here, because every name gets shorter. The BOARD layout test must stay green unchanged. If
it does not, stop and report.

### 5.4 Widget tests (`tests/widgets/test_surf_swarm_seat_record.py`, `test_surf_swarm_fleet.py`)

Assert against **composited** output (`render_strips()`), including styles for each colour row in §5.2.
Cover: every `panel_state`; a `None` count in each counted state; the red-row prefix on a wei
figure longer than 2^53 (the exact digits must appear); `tok` for `None`, `0`, `1534`, `22000` and a bool;
tier membership for full, compact and tight; and `role` absent from every tier. Hostile `panel_figure` and
`model` (`[/x]`) must render as literal text.

---

## 6. Work packages

Every WP ends by running exactly the named tests plus `-m guard` (the memory "guard tests in every named set":
seconds). Never run a directory or the suite. The controller runs the full suite once, before merge.

### WP0: fixtures (tooling only; nothing in `maxpane_dashboard/`)

- `tests/scripts/capture_oracle_requests.py`: a one-shot capture (network allowed here, **never imported
  by a test**). Keyless GETs on `api.imd.fun`, 0.2 s spacing. It writes `tests/fixtures/surf/swarm/oracle/` plus a
  `MANIFEST.json` in the `swarm/v5` shape (url, captured_at, http_status, sha256, bytes,
  `selected_because`).
- Capture it **coherently, within a few minutes**: `/seats/420` (as `seat_420.json`, the join's other side),
  list page 1 (`limit=200`), list page 2 (`before=`), and details chosen by the script from the seat's own
  hashes. Cover: attested in-cluster, **attested outvoted** (an NFT floor with a `0` answer if one is still in the history),
  disagreed in-cluster, disagreed out, assessing (if any is live, and record it if none was), blocked, a
  `toleranceBps: 1000` in-cluster row with an unequal figure, and a `bool` `answerType` if the history has one.
  Add `GET /oracle/requests/not-a-uuid` (400) and a well-formed unknown UUID (record the status seen).
- Commit the raw bodies. Do not trim them: they are evidence.
- **Done when** the manifest lists every file and the handover §4 counts can be re-derived from the fixtures
  by a small script. Put the derived counts in the manifest's `note`. They will differ from 20:25 UTC, and
  that is fine.

### WP1: contract + client

Files: `data/surf_models.py`, `data/surf_swarm_client.py`, `data/surf_cache.py` (slot constant +
registration only), and the client/models tests (`tests/data/test_surf_models.py`,
`test_surf_swarm_models.py`, the client test file).
- §1 exactly. `seat_work_rows` fills the new keys with `None` / `"not_read"` for oracle rows and
  `"not_oracle"` for others. That default moves to `enrich_panel_rows` in WP2 if it is cleaner, but the row must always
  carry every key.
- `submission_answer` reads `usage.outputTokens` into `output_tokens` (non-bool int ≥ 0, else `None`),
  and `coerce_answers_slot` validates it. Keep this part here, because it is the answer slot's contract.
- §4 client.
- Tests: the existing agreement tests over `SURF_ROW_KEYS` must redden before the rows carry the new keys.
  Mutation-prove one: add the key to the tuple only and watch **which** test goes red.

### WP2: fold

Files: `data/surf_swarm.py`, `tests/data/test_surf_swarm_seats.py`, or a new `tests/data/test_surf_swarm_oracle.py`.
- `oracle_point`, `oracle_rows_due`, `match_requests(list_rows, due_rows)` (returns job→request id plus the
  ambiguous and settled-negative sets, per §2.3), `coerce_oracle_slot`, `prune_oracle` and
  `enrich_panel_rows`. Everything is pure, with the clock injected.
- Drive the tests from the WP0 fixtures: one test per §3 table row, plus the wallet trap (a member with the seat's
  wallet but another hash → not on panel), the duplicate-jobId trap, the duplicate-hash trap, the tolerance case and
  a hostile slot (bad UUID key, a float figure, extra field, `terminal: "yes"`).
- **Mutation proofs** (decoder-shaped, required): (a) match on `wallet` instead of `submissionHash`,
  (b) derive `in_cluster` by comparing figures, (c) parse `figure` with `float`. Each must redden a named test.
  Record which one in the commit message.

### WP3: manager

Files: `data/surf_manager.py`, `tests/data/test_surf_manager_answers.py`, or a new
`tests/data/test_surf_manager_oracle.py`.
- §2 exactly: `_pool_swarm_oracle(seat, token, now)` plus the key wiring in `_swarm_seat_keys`.
- Tests, with a fake `swarm_client` recording calls (no network; the injected transport raises): no due rows means **zero**
  calls; the page walk stops for each of its four reasons; `off_panel` only after coverage; the
  detail cap is 4; terminal points are never re-read and `assessing` is re-read after 120 s; a failed list or detail
  leaves the seat tier `fetched` and the other RECORD fields intact; a slot restored from a hostile cache file
  is coerced; the slot is not rewritten when nothing changed.
- A concurrency-shaped change (a new awaited step inside the detached seat read) needs its own proof:
  cancel the seat task mid-oracle-walk (`_cancel_swarm_seat`) and assert that no partial slot was stored.

### WP4: widgets

Files: `widgets/surf/_fmt.py`, `widgets/surf/swarm_seat_record.py`, `widgets/surf/swarm_fleet.py` and
their widget tests (§5). Check `tests/widgets/test_surf_widget_contract.py` (the allowed imports) and
`tests/surf_swarm_fixtures.py` (the shared payload builder must carry the new row keys).
- D1–D4 are decided (§0.1). Do not re-ask.

### WP5: layout re-sweep + docs

Files: `screens/surf.py` (the `#:` blocks only, plus a constant **only** if the sweep moves it),
`tests/screens/test_surf_swarm_layout.py`, `.claude/rules/surf.md`, `docs/imd_swarm_api.md`,
`CHANGELOG.md` (Unreleased), `docs/decisions.md` (only if a statement is withdrawn).
- Read `.claude/skills/terminal-layout/SKILL.md` first. Re-measure `FULL_WIDTH` / `COMPACT_WIDTH` /
  `TIGHT_WIDTH` with `table_cols` and re-sweep **in situ** on the enriched committed payload with the new oracle
  fixture joined. Find the full-tier onset, `RECORD_NEVER_CLEARS_BELOW`, and confirm that
  `SURF_AGENT_FULL_LAYOUT_{COLUMNS,ROWS}` (139×33) holds. Rewrite the `#:` blocks with the new numbers
  and the date. The prose there still says `role`.
- rules/surf.md: the RECORD column list (two places: "RECORD shows…" and "Polish answer reads"), the
  new endpoint in the SWARM paragraph (the one-source/two-names rule applies), and the panel states.
- `docs/imd_swarm_api.md`: `/oracle/requests` and `/oracle/requests/<uuid>`, paging (`limit` ≤ 500,
  `before`), 400 `invalid_id`, and the join.
- Tests named for this WP: the AGENT and BOARD layout tests (`-m sweep` subset in
  `test_surf_swarm_layout.py`), `tests/screens/test_surf_swarm_screen.py`, the address sweep's
  surf case (`tests/screens/test_address_icons_everywhere.py -k surf`), and every doc-pinning test
  that `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/` names.

---

## 7. Review and merge (the controller, which is Claude, not Codex)

- One task review per WP diff, using the reviewer contract in CLAUDE.md verbatim, on a mid-tier model. Fix rounds are capped at 2.
- The final whole-branch review runs on the most capable model, followed by ONE fix wave and ONE scoped re-review.
- The full suite runs once, by the controller, before merge (`HOME=$(mktemp -d) … -n 4 --dist loadfile`).
- Residuals go to a new `docs/surf_oracle_panels_followups.md`. Known entries on filing: 5A (the ORACLE tile
  line: `panel 205 of 216 agreed`, `open 3 · closed 17`) is still the owner's call, and so is the bool figure mapping if WP0 found
  no bool request.
- **Never merge, push or tag without the owner.** No version bump in this branch.

## 8. Hard-constraint checklist (every reviewer checks all of these)

- All reads are GETs, with no key and no header beyond `Accept`. Nothing signs anything.
- No test touches the network. `tests/scripts/capture_oracle_requests.py` is never imported by a test.
- `question`, `notes`, `figure`, `answerType` and the model ids are third-party text. Nothing but extracted
  fields reaches the cache. Everything shown goes through `sanitize_cell` / `strip_tags` / `Text`.
- `figure` is never a float.
- A 404/400 or a dead route leads to `unavailable`, never to `off_panel` and never to a zero.
- The widget does not import `data/`.
