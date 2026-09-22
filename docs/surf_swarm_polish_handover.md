# Surf swarm polish — handover for Codex (Tier 2)

Owner request 2026-09-22, from screenshots of BOARD (`b`), AGENT (`a`) and SWARM (`s`):

- FLEET (BOARD) and SEAT (AGENT) should be more structured and readable. The references are
  BURN & SUPPLY / SIGNALS (`widgets/surf/pool4u_burn.py`, `pool4u_signals.py`), IMD MARKET
  (`widgets/surf/market.py`) and THROUGHPUT (`widgets/surf/swarm_throughput.py`): a fixed label
  column, grouped lines, bold values, colour only where a value means something.
- LEADERBOARD: every column sortable. The selected seat, offline seats and currently working
  seats are highlighted.
- The SWARM and AGENT hero cards use colour where a value is a status.
- RECORD: the `objective` column shows the same prompt on every row. Show **the agent's answer**
  instead: the first sentence of the seat's own reply (owner decision, below).
- Plan any other valuable fields the API has gained (§1.3).

Read `CLAUDE.md`, `.claude/rules/surf.md`, `.claude/rules/widgets.md` and
`.claude/skills/terminal-layout/SKILL.md` before writing code. Precedence: CLAUDE.md > this
document > your own judgement.

## 0. Setup

- Precondition: `git fetch autopull` then `autopull/main` == `91818e4` (the BOARD merge). If not,
  stop and report.
- Branch `feature/surf-swarm-polish` from `autopull/main`. One writer. Commit with explicit paths
  only. Use `.venv311` and `env -u NO_COLOR HOME=$(mktemp -d)`.
- Never commit `tests/fixtures/surf/pool4/oracle_25955365.json`. Do not touch any untracked file
  you did not create.
- The first commit contains this document plus the WP0 captures.
- No push, merge, tag, version bump, middle tier or full suite. The controller runs the full
  suite once, after review.

## 1. What the API serves (measured by Claude, 2026-09-22 ~13:45 UTC)

The shared reference is `/Library/Vibes/aidude/docs/imd-api-changelog.md` (swept 10:00 UTC today).
Read §2–§4 there. The four routes below are **not in it**; Claude found them on this sweep.

### 1.1 New routes (keyless GET, same host pool)

| Route | Shape | Use |
|---|---|---|
| `/jobs/{id}/submissions` | `{jobId, repoUrl, baseCommit, count, submissions[]}` | **every seat's submission for the job** |
| `/jobs/{id}/result` | `{jobId, state, complete, source[], files[], delivery}` | winning bundle + artifact URLs |
| `/artifacts/{hash}` | raw file (`application/octet-stream`) | e.g. `answer.json`; `404 unknown_artifact` |
| `/bundles/{hash}` | git bundle | not for this dashboard |

A `submissions[]` item carries:
- `hash` (= `/seats` `work[].submissionHash`, **exact match**), `nodeKey`, `role`, `attempt`,
  `deviceKey` and `seat{tokenId, agentId}`;
- `outcome` and `accepted` (bool);
- `oracleResult{status accepted|rejected|pending, detail}` (oracle jobs; `null` otherwise);
- `usage{model, runtime, turns, inputTokens, outputTokens, cachedInputTokens, wallClockMs}`;
  `model` can be `null`; wallClockMs is an int here;
- `summary`: **the agent's own reply, Markdown**;
- `verdict{status, evaluation, detail, failedChecks[]}`;
- `findings[]`, `artifacts[]`, `createdAt`.

Payload size: 93 KB for a 40-submission oracle job and 17 KB for a 2-node build job.

Measured on seat #420's six newest jobs: the hash matched every time; `usage.model` was
`claude-sonnet-5` while `/workers` advertises `premiumModel claude-fable-5-1`. The **advertised**
model and the model a job **actually ran on** differ, and both are worth showing, labelled as such.

First sentences of #420's replies after stripping Markdown: 5 of 6 distinct and informative
(`I wrote artifacts/answer.json with a floor of 190000000000000000 wei (0.19 ETH).`); one was
boilerplate (`check-answer.mjs prints ok.`). Other seats open with
`Created and validated [artifacts/answer.json](/home/imd-worker/.identitymd/work/…)` — a link whose
target is a **local filesystem path** (home directories, user names). §2.5 says how to clean it.

### 1.2 Changes to routes we already read

- `/workers` `runtimes[]` gains `premiumModel{model, effort}` on daemons ≥ `0.1.0+56872758`,
  **asserted by the daemon, not probed**. Measured: `gpt-6-astra xhigh` 41 · `claude-fable-5-1 high`
  33 · the rest advertise none (105 workers).
- `/skills` items gain `inference` (`standard` / `economy` / absent) and `record{attempts,
  accepted, rejected, pending, wallClockMs}` (14 of 30 skills carry one; wallClockMs is a string).
  `skill_rows` (`data/surf_swarm.py:327`) reads neither.
  Example: `adversarial-review` 103 attempts, 0 accepted, 103 pending; `build-contract-project`
  83 / 70 / 1 / 12.
- `/health` gains `status` (`ok`), `operatorSurface`, `taskNetwork`, `lotusTargets`. Only `status`
  is usable; the changelog says not to build on the other three.
- `/workflows` appears: 20 two-stage launches (`contractsJobId` + `frontendJobId`, status,
  failure).

### 1.3 What this plan takes, and what it files

| Finding | Decision |
|---|---|
| `/jobs/{id}/submissions` summary | **RECORD answer column** (owner request) |
| submissions `usage.model` / `wallClockMs` | **RECORD `model` and `took` columns**, beside the answer |
| `/workers` `premiumModel` | **FLEET model mix line** + **SEAT `model … (advertised)` line** |
| `/skills` `record` + `inference` | **CAPABILITY** gains an `inf` column and `acc/att` — but only if the SWARM column pin (141) does not rise, else it goes on the widen ladder's full tier |
| `/health.status` | SWARM hero SERVICES box colour (§2.4) |
| `/workflows` | **Not in this branch.** File as F51: SWARM already exceeds the owner's heights (F16) and no slot is free |
| submissions list every attempting seat | **Not in this branch.** File as F52: co-working per job is served after all (it contradicts changelog §2 "panel membership is not published"); TEAMMATES could use it later |
| `oracleResult` rejected attempts | **Not in this branch.** File as F53: a seat's rejected attempts exist only inside jobs we have not been told about |

Record §1.1 and §1.2 in `docs/imd_swarm_api.md` as a dated entry. Do not edit the aidude file;
the owner will be offered that separately.

## 2. Design

### 2.1 Colour and emphasis — one palette, meaning-bound

Follow the idiom already in `market.py` / `pool4u_signals.py` / `swarm_throughput.py`:
- dim labels;
- **bold** headline numbers;
- **green** = healthy / working / accepted / breaker closed / service up;
- **red** = offline / paused / rejected / breaker open / service down;
- **yellow stays reserved** for `unavailable` (and the existing `pending` counts that already use it).

Rules:
- A colour never replaces a word: every coloured state keeps its text, so NO_COLOR stays readable.
- No invented thresholds: ACCEPT RATE and scores are bold, not traffic-lit.
- Colour is asserted on **composited** segments (style of the rendered strip), never on the
  markup string.

### 2.2 FLEET (BOARD) — label column and groups

Today it is 11 run-on lines (screenshot: `tokens / completed job` wraps onto a second line;
`PAUSED none` sits at the bottom with no label column). Target:

```
FLEET · workers as of 13:31

runtime    codex 61 · claude 42 · +1
model      gpt-6-astra xhigh 41 · claude-fable-5-1 high 33 · none 31   (advertised)
daemon     0.1.0+79f4f4d5 82 · +3
os         linux 88 · darwin 12 · win32 4
profile    foundry+none 74 · none 30
slots      1×56 · 2×37 · 4×10 · 3×1
heartbeat  13:31:08 – 13:31:28

paused     none                                ← green "none"; a count is red, then its rows

CONTRIBUTORS · as of 13:26
tokens/job 379,059 (served)
```

- The label column has a fixed width shared by all rows (the BURN & SUPPLY shape). Values are
  bold counts with dim names.
- The `model` line reads only `premiumModel` and says `advertised`. A worker with no
  `premiumModel` counts as `none`.
- The two sources keep their own clocks: workers in the title, contributors in their sub-header.
- BOARD's **height may rise, but not above 31 rows** (the owner's smaller terminal). The
  **column pin 141 must not rise.**

### 2.3 SEAT (AGENT) — owner-approved layout (≈ 34 rows accepted)

```
SEAT · as of 13:31

seat      IDMD #420 · agent 50939
owner     0xe5b1275f…f64f2a ⧉
paired    09-20 07:34
runtime   claude 2.1.278 (Claude Code)
model     claude-fable-5-1 · high (advertised)
daemon    0.1.0+79f4f4d5 · 1 device

attempts  207 · accepted 191 · 92.3 %
reviewed  198 submissions · 352 entries
feedback  149 sent · 10 submitted · 39 queued
score     0.99 on 198 scored
by role   implement 197 · review 1

CONTRIBUTORS · as of 13:26
record    210 att · 190 acc · 2 rej · 18 pend
effort    2,274 turns · 8.3 h · rank #6 of 104
```

- The label column has a fixed width.
- Emphasis:
  - bold: the token, accepted count, reviewed count and score;
  - green: `accepted N`;
  - red: `rej` when > 0;
  - yellow: `pend` when > 0 (the existing pending convention);
  - dim: the `(advertised)` note and every label.
- Every fact on today's SEAT stays. Nothing is re-sourced: `/seats` lines and `/contributors`
  lines remain on separate lines with separate clocks.
- The `model` line comes from `swarm_seat_live` (the worker's `premiumModel`). If the worker
  advertises none, show `none advertised`. If the worker read failed, show `unavailable`.
- The contributors group is always two lines, with sub-header `CONTRIBUTORS · as of HH:MM`. The
  single-line join from the fix wave is retired, because the group is now a labelled block.
- **Owner accepted ≈ 34 rows.** Measure it in situ and put the number in the `#:` block.
  **AGENT's column pin 138 must not rise.** Widen the label column only as far as that allows.

### 2.4 Hero colours — SWARM (`s`) and AGENT (`a`)

| Box | Colour rule |
|---|---|
| SWARM WORKING | green when > 0; dim when 0, with the word `quiet` (the changelog says 0 working is normal, not an outage) |
| SWARM QUEUE | bold count; yellow only for the existing pending shape |
| SWARM BREAKER | green `closed` / red `open` |
| SWARM SERVICES | green for each up service; red for each down one; `/health.status` `ok` green, anything else red with its word |
| AGENT STATUS | green `working N of M`; dim `idle`; red `offline` / `paused …`; yellow `unavailable` |
| AGENT ACCEPTED | green accepted (already), bold attempts |
| AGENT REVIEWED | bold count; yellow pending (already) |

AGENTS, ACCEPTED 24h, ACCEPT RATE, SCORE and COLLAB stay bold numbers. BOARD's hero is out of
scope.

### 2.5 RECORD — answer, model, took

The `objective` column is **replaced** by `answer`, and two narrow columns are added: `model`
(`usage.model`, e.g. `claude-sonnet-5`) and `took` (`usage.wallClockMs` → `7m`, `1h 04m`). Final
column order:

`when · job · node · role · state · launch · sub · model · took · answer`

`answer` is the elastic column that keeps RECORD's `‹ widen` contract. Replace
`RECORD_NEVER_CLEARS_BELOW` with the answer column's measured onset for the committed capture.

Deriving the answer (a pure function in `data/surf_swarm.py`, unit-tested on the captures):
1. Take the submission whose `hash` equals the work row's `submissionHash`.
2. From its `summary`:
   - Markdown links `[text](target)` → `text` (the target is dropped: it is often a local path
     with a user name);
   - drop backticks, `**` / `__` / `*` emphasis and leading list markers;
   - replace any remaining absolute path (`/home/…`, `/Users/…`, `/root/…`, `C:\…`) with its
     last component;
   - flatten whitespace.
3. Take the first sentence (split on `.`/`!`/`?` followed by whitespace, or a newline). The
   widget clips it with `sanitize_cell` (third-party text).

Keep these states distinct:

| State | Cell |
|---|---|
| answer read | the sentence |
| submissions not fetched yet (still queued) | dim `not read` |
| fetch failed | yellow `unavailable` |
| the seat's hash is absent from a successful read | dim `not served` |
| empty or null summary | dim `no reply` |

`model` null shows `—`; `took` missing shows `—`. These columns come from the same read, so their
states follow the answer's.

Fetching (on `TIER_SWARM_SEAT`, after `/seats`, never in a handler):
- Read `/jobs/{id}/submissions` for the selected seat's newest work rows, **up to RECORD's
  `ROW_CAP` (40)**, bound by an agreement test.
- At most `SWARM_ANSWER_PER_CYCLE` jobs per cycle (pick one, measure, put it in a `#:` block).
  RECORD fills progressively; rows still queued read `not read`.
- The client adds `submissions(job_id)`: same host pool, pacing, `follow_redirects=False`,
  the job id validated as a UUID before interpolation, and a 404 → the job's cell is
  `unavailable`, never a rotate-and-fail of the whole tier.
- Cache: a new slot keyed by `(jobId, submissionHash)` that stores **only the extracted fields**
  (`answer`, `model`, `took_s`, `state`), never the 100 KB payload.
  - A row whose job state is terminal (`completed`, `cancelled`, `failed`) is kept and never
    re-read.
  - Other rows re-read when due.
  - Prune by cap and age, the `SLOT_SWARM_JOBS_SEEN` pattern.
  - Validate every loaded point (a hand-edited cache file is third-party input); an invalid slot
    is refused.
- Seat A's answers must never appear under seat B: the key contains the submission hash, and a
  test switches seats.

### 2.6 LEADERBOARD — sortable, highlighted rows

- **Sort:** clicking a column header sorts by it; a second click on the same header reverses.
  Key `o` (free on surf; check `BINDINGS`) cycles the sort column for keyboard users; `O`
  reverses.
  - The sorted header shows `▲`/`▼`, and that marker must fit the column (measure it, and move no
    pin).
  - The default is today's rank order.
  - The `#` rank cell always shows the **global rank**, never the row position.
  - The sort is stable; `None` sorts last in both directions.
  - Sorting happens in the widget (a render-side reorder of the served rows); the manager and
    fold are untouched.
  - The sort survives refresh and tier-width changes, and the cursor stays on the same **token**
    across a re-sort.
  - A header click never selects a seat or saves it; data-row click/Enter behaviour is unchanged.
- **Row highlights:**
  - selected seat: `▸` (kept), bold, with the row's first cell in the accent colour;
  - working (`live_state` working): the state cell green;
  - offline: the whole row dim, with the word `offline` kept;
  - paused: the state cell red;
  - unknown state: yellow `unavailable` (as now).
- README gains `o`/`O` and the header click in the surf key table. `KEY_HINTS` does **not** gain
  them: the status-bar width was just settled.

## 3. Contract changes (WP1 freezes them in `data/surf_models.py`)

- `SURF_ROW_KEYS` for the RECORD rows gains `answer`, `answer_state`, `model`, `took_s`.
  `objective` stays in the row (other readers), but RECORD stops rendering it.
- `swarm_fleet` gains `models`, a list of `{model, effort, count}`. The explicit
  `{model: None, effort: None, count: N}` bucket counts workers advertising no usable model.
  Each worker contributes once per distinct model/effort pair; multiple runtimes can make
  the sum exceed LIVE. This is advertisement, never a successful model probe.
- `swarm_seat_live` gains `advertised_model` and `advertised_effort` (None = not advertised,
  distinct from an unavailable read). Multiple distinct pairs are sorted, with model and
  effort strings joined in the same pair order; missing effort uses `—`.
  It also gains `live_state` using BOARD's working/idle/paused/offline/None vocabulary, so WP5
  can preserve unknown pause evidence rather than paint it as idle (F48).
- Skill rows gain `inference`, `attempts`, `accepted`, `rejected`, `pending`.
- The SWARM hero payload gains `health_status`.
- A new cache slot for answers, with its coercer registered on load (fail closed when absent).
  Answer states are `read`, `not_read`, `unavailable`, `not_served`, `no_reply`. The persisted
  JSON map is job UUID → exact submission hash → extracted `{answer, model, took_s, state}`
  plus `read_ts` and `terminal` bookkeeping. Queued `not_read` has no persisted point.
  RECORD puts the explicit read state in `answer`; model/took are shown only for `read` or
  `no_reply`, otherwise `—`, so stale metadata cannot look successfully fetched.
  The terminal no-reread rule includes failed terminal attempts while retained; pruning can
  make them eligible again. No raw submissions envelope or uncleaned summary is stored.
- Every addition goes through `SWARM_KEYS` / `SWARM_WIDGET_SIGNATURES` and the agreement tests.
  The widget restates tuples where the pattern already does.

## 4. Layout budget (re-sweep in situ, terminal-layout skill)

| Body | Today | Allowed |
|---|---|---|
| BOARD `b` | 141 × 23 | columns **must not rise**; rows ≤ 31 |
| AGENT `a` | 138 × 32 | columns **must not rise**; rows ≈ 34 (owner-accepted; measured) |
| SWARM `s` | 141 × 42 | columns **must not rise**; rows must not rise (F16 open) |
| others | unchanged | unchanged; `STATUS_BAR_WHOLE_FROM` 134 unchanged |

**Stop rule (unlike §9 of the BOARD handover, it is per item):**
- If one item cannot meet its budget, skip that item's layout change.
- Record the measured number and the binding line in the hand-back.
- **Continue with every other item.** Do not stop the wave.

## 5. Work packages (serial; each ends with its named tests + `-m guard`)

- **WP0 captures.** Commit this doc plus live captures under `tests/fixtures/surf/swarm/v4/`, with
  a MANIFEST (URL, UTC time, sha256), taken with one paced keyless GET each:
  - `/jobs/73d7dcd7-aab5-47f8-9462-69b8e0f8b2e9/submissions` (oracle, 40 submissions, #420
    informative);
  - `/jobs/76296dcd-55e2-4eaa-9e18-0c34ec1ff0e5/submissions` (#420's boilerplate sentence);
  - `/jobs/33016bad-ed32-4065-8c2e-269ce6ccc0a3/submissions` (build + review);
  - `/seats/420`, `/workers` (with `premiumModel`), `/skills` (with `record`/`inference`) and
    `/health` (with `status`).
  - Also make one hand-made hostile variant: a summary with `[/x]` markup, a local path and a
    500-character sentence.
  No test reads the network.
- **WP1 contract** (§3), with the agreement tests red first.
- **WP2 data:** the client's `submissions()`, the answer extraction, the fold fields
  (fleet models, seat live model, skill record/inference, health status), the manager tier
  scheduling and the cache slot.
- **WP3 FLEET + SEAT** restructure (§2.2, §2.3) and measurement.
- **WP4 LEADERBOARD** sort + highlights (§2.6).
- **WP5 heroes** (§2.4).
- **WP6 RECORD** columns (§2.5) and CAPABILITY columns (§1.3), with measurement.
- **WP7 docs:**
  - `rules/surf.md` (keys, RECORD, SEAT, FLEET, palette) and README;
  - `docs/imd_swarm_api.md` dated entry (§1);
  - `docs/decisions.md` (objective → answer; advertised vs ran model; palette);
  - `docs/surf_swarm_followups.md`: F51–F53, plus any item skipped by the stop rule.

Mutation proofs are mandatory for:
- the answer extraction (a link target leaks, or a path is not reduced);
- hash matching (seat A's answer under seat B);
- `not read` vs `unavailable` vs `not served`;
- sort stability and the global-rank cell;
- a header click not selecting;
- the colour of a state (assert on composited style: a red `offline` turned default must fail);
- every moved pin, ±1.
For each proof, name the test that reddens and say why.

## 6. Done means — hand-back as §6.1 of this file

- a commit table;
- per-WP red→green evidence and mutation proofs;
- measured pins (columns × rows, what binds) for BOARD, AGENT, SWARM;
- which budget items were skipped;
- the named-set result (every touched data/widget/screen test file, `test_address_icons_everywhere.py`,
  `tests/test_surf_registration.py`) and `-m guard`;
- real CLI captures at 138×31 and 119×35 for `b`, `a`, `s`, with seat #420;
- `git status --short`.

Stop there for Claude's final whole-branch review. The owner decides merge and push.

## 6.1 Hand-back — 2026-09-22

### Scope and commits

The fetched `autopull/main` and `91818e4` both resolved to
`91818e49b211d43170608ef9105891e1c81a9a27`; §0 passed before branching.
Work is on `feature/surf-swarm-polish`, with one repository writer at a time.
All commits use explicit paths. No push, merge, tag, version bump, middle tier or full suite.
The full release suite is deferred to the controller after review, as requested.

| WP | Commit | Result |
|---|---|---|
| 0 | `4e1af77` | This handover, seven paced live captures, hostile variant and SHA-256 MANIFEST |
| 1 | `91ad004` | Frozen row/payload/cache contracts and mandatory answer-slot coercer |
| 2 | `56afd44` | Exact-hash answer extraction, bounded detached reads, validated extracted cache and new fold fields |
| 3 | `54e7ffa` | Grouped FLEET, measured BOARD height, F50 test correction; SEAT budget skip F54 |
| 4 | `a177e51` | Twelve-column sorting, stable token cursor, semantic row styles and no-save headers |
| 5 | `d77b7d4` | Hero state words/colours and health; F48 fixed, mixed-services limitation F55 |
| 6 | `bc126c2` | RECORD answer/model/took, optional CAPABILITY fields, measured onsets, complete local-path cleaning |
| 7 | This documentation commit | Rules, README, API entry, decisions, follow-ups, layout reference and this hand-back |

WP0's seven GETs returned 200, with actual UTC capture times in the committed MANIFEST.
The three submission captures contain 40/30/2 entries and all contain seat #420. Workers
were 107: 43 gpt-6-astra/xhigh, 34 claude-fable-5-1/high, 30 without an advertised model.
Those are capture observations, not permanent counts. The shared aidude changelog was read
only; its afternoon entry already contained the routes described as absent in §1.

### Test-first evidence

All pytest commands used `.venv311`, isolated temporary HOME and unset NO_COLOR; tests used
fixtures/mocks and made no network requests. Counts below are each WP's final named coverage,
not an additive count of unique tests across the branch. Red/green logs are local `/tmp/polish-wpN-*`.

| WP | First red | Restored named green | Guard green |
|---|---|---:|---:|
| 0 | 2 missing-corpus assertions | 36 | 200 |
| 1 | 12 contract assertions; then explicit queued-default regression after collection exposed the missing field | 371 across nonoverlapping runs | 200 |
| 2 | 45 data/client and 6 manager assertions | 686 | 200 |
| 3 | 4 composited FLEET cases and old 23-row BOARD pin; temporary exact SEAT layout failed at 34/36, passed at 37 | 583 (166 width cases + 417 remaining) | 200 |
| 4 | 18 widget and 3 pilot cases | 90 (81 widget/screen + 9 affected layout) | 200 |
| 5 | 17 composited cases; explicit service-word regression also failed before correction | 138 | 200 |
| 6 | 10 RECORD cases, 3 CAPABILITY cases, 4 delimited-path cases, 3 Windows-forward-path cases; old RECORD pin and mismatched CSS cap red | 138 (117 widget/data + 21 layout) | 200 |
| 7 | Documentation only; final branch gate below | 1,287 | 200 |

WP6's initial final checks exposed five old `full` tier expectations at 141 and a skill-table
297-vs-204 agreement failure. They now require the exact original seven CAPABILITY columns
in baseline tier, and the skill quotes 204. Whole-content/scroll assertions remain. The final
requires-empty and stale-usage tests use known other-cell values so unrelated dashes cannot
satisfy their assertions. IN FLIGHT stress was restored byte-for-byte; only RECORD stress
uses an answer. No production mutations remain.

### Mutation evidence

Every mutation below failed the intended assertion, then was reversed with exact source-byte
restoration and a green focused or named run. Full test names, parameters, reasons and logs
are also in the corresponding commit messages. Initial mutations that failed the wrong
assertion or survived were rejected as evidence and corrected, as recorded here.

| WP | Mutation → test that reddens and reason |
|---|---|
| 1 | Remove required answer coercer → `test_polish_answers_slot_is_registered_and_refuses_unvalidated_load`: unvalidated persisted payload is admitted |
| 2 | Keep link target / keep absolute path → `test_answer_sentence_drops_private_targets_paths_and_preserves_sentence_boundaries`: destination or private path survives |
| 2 | Compare hash prefix / bypass seat metadata → `test_exact_hash_does_not_match_a_prefix_or_another_seat`: another submission or seat receives the reply |
| 2 | Queued→unavailable / raise four-job cap to five → `test_progressive_answers_distinguish_queued_failed_absent_and_reply`: queue/state or request bound is wrong |
| 2 | Failed→not served / absent→unavailable → `test_submission_states_are_distinct`: failure is confused with successful absence |
| 2 | Drop cached-answer cleaning → `test_answer_cache_refuses_any_bad_point`: a local path passes cache validation |
| 2 | Use first cached hash → `test_cached_answers_match_exact_submission_hash_in_both_seat_orders`: replies cross seat identities. The initial one-order switch proof survived, so this two-order regression was added and killed it |
| 2 | Omit manager's injected coercer → `test_cache_load_and_consumption_revalidate_every_answer`: real validated cache restoration fails |
| 2 | Unknown pause→idle → `test_live_state_keeps_unknown_pause_distinct_from_idle_and_positive_evidence`: lack of evidence falsely becomes idle |
| 3 | BOARD rows 27→26 / 28 → `test_board_polish_row_pin_is_tight_and_keeps_fleet_whole`: at-pin still scrolls / pin-minus-one already fits |
| 3 | Paused red→default → `test_polish_paused_state_and_numbers_have_composited_styles`: composited ANSI-red assertion fails |
| 3 | Model omission +N off by one → `test_polish_groups_align_labels_and_keep_the_advertised_model_prefix`: exact +2 continuation is wrong |
| 3 | Inject false whole-body capture with cropped status, AGENT and SWARM → `test_the_body_is_whole_from_its_pinned_width`: status cropping alone cannot prove body degradation (F50) |
| 4 | Add token tie-break / move None partition first → `test_every_sort_column_is_stable_and_missing_last_both_ways`: stable source order / missing-last rule fails |
| 4 | Replace global rank with row position → `test_seat_sort_is_numeric_and_global_rank_is_not_row_position`: rendered global 9 becomes 1 |
| 4 | Sort header also selects → `test_board_header_sorts_without_saving_then_selects_sorted_token_once`: no-save assertion sees token 10. Initial mutation failed sorting instead and was rejected; corrected mutation preserves sorting and kills no-save |
| 4 | Paused red→default → `test_selected_and_live_states_have_composited_styles`: actual cursor-row colour fails |
| 4 | Remove token cursor restoration → `test_cursor_token_zero_and_sort_survive_refresh_and_width_tiers`: cursor loses token 0 |
| 5 | Offline red→default → `test_polish_worker_status_words_and_composited_colors`: composited RGB fails |
| 5 | Unknown pause fallback→idle → `test_polish_unknown_pause_fold_reaches_unavailable_not_idle`: visible unavailable is lost (F48) |
| 5 | Health ok green→red → `test_polish_hero_state_words_have_composited_colors`: composited health RGB fails |
| 5 | Service words→identical dots → `test_polish_mixed_services_remain_distinct_without_color`: visible states no longer distinguish up/down |
| 6 | RECORD 204→203 / 205 → `test_polish_record_answer_clearance_matches_committed_v4_window`: marker still lit at 203 / already dark at 204 |
| 6 | CAPABILITY 166→165 / 167 → `test_polish_capability_optional_tier_preserves_baseline_and_clears_at_measured_onset`: optional columns absent at 165 / already present at 166 |
| 6 | Collapse not served / allow stale usage → `test_polish_answer_states_and_same_read_usage`: distinct word lost / failed row leaks model and duration |
| 6 | Disable clipped-answer marker → `test_polish_answer_sanitization_and_actual_clipping_drive_widen`: clipped CJK answer lacks widen |
| 6 | Remove delimited-path pass → `test_delimited_absolute_paths_with_spaces_keep_only_basename`: four private paths survive |
| 6 | Remove forward-slash drive separator → `test_windows_forward_slash_absolute_paths_keep_only_basename`: three C:/ paths survive |
| 6 | Shed original checks column → `test_polish_capability_optional_tier_preserves_baseline_and_clears_at_measured_onset`: original-column guarantee fails |
| 6 | Remove empty-requires dash → `test_requires_is_joined_and_empty_is_a_dash`: explicit empty cell is lost |

Proof counts: WP1 1, WP2 12, WP3 6, WP4 6, WP5 4, WP6 11. Evidence summaries:
`/tmp/polish-wp2-mutation-summary.log`, `/tmp/polish-wp3-proofs/results.json`,
`/tmp/polish-wp4-proofs/`, `/tmp/polish-wp5-proofs/results.json`,
`/tmp/polish-wp6-proofs/results.json`; WP1's log is `/tmp/polish-wp1-mutation.log`.

### Measured layout and budget decisions

| Body/content | Result | Binding evidence |
|---|---|---|
| BOARD | **141×27**, rows previously 23 | FLEET with paused detail is 16 rows + 11 chrome. At 26 it scrolls; at 27 whole. At 140 LEADERBOARD sheds three columns; 141 retains all twelve |
| AGENT | **138×32**, unchanged | Existing SEAT/BY NODE over eight-row RECORD; 31 remains taller, 32 fits. RECORD's compact tier intentionally sheds role/launch/sub while retaining answer/model/took |
| SWARM | **141×42**, unchanged | Original seven CAPABILITY columns bind width; sixteen-line THROUGHPUT/top row binds height. 41 remains taller. Named long-content and F55 limitations remain |
| RECORD answer | Clears at **204**, previously objective clearance 297 | At 203 panel/answer are 200/79 cells and clip; at 204 they are 201/80 and clear; 205 remains whole |
| CAPABILITY optional fields | Full from **166** | At 165 panel/budget 115/113 sheds only inf and acc/att; at 166 116/114 fits all nine, no horizontal scroll |

The committed v4 seat has 191 work rows; RECORD displays the first 40 in source order. Its
matched boilerplate reply at index 0 is 27 cells, and informative reply at index 1 is 80 cells.
The build job at index 125 is outside this measured window. A synthetic 500-character answer
and the committed hostile fixture still clip with an honest marker. CAPABILITY's forced-full
trial at 141 overflowed horizontally by 25 cells, so the permitted wider tier is used. Both
CSS caps are 118; allocation at 141 stays 91. All other body/status pins and KEY_HINTS remain.

**Skipped under §4: F54.** The exact approved SEAT grouping needs **138×37**:
18-row SEAT + 8-row RECORD + 11 chrome. Both captured v4 and five-digit stress were whole at
37 and scrolled at 34/36. The entire restructure, advertised-model line and removal of the
responsive contributors join are deferred. No facts or group gaps were removed to force 34.
Measurement: `/tmp/test_polish_seat_budget.py`, `/tmp/polish-wp3-seat-budget-v4/`.

**Filed:** F51 workflows, F52 per-job co-working, F53 rejected-attempt discovery, F54 above,
and F55 mixed SERVICES clipping. **Fixed:** F48 unknown pause (WP5) and F50 vacuous below-pin
test branch (WP3). F16, F47 and F49 remain outside this wave.

F55 predates polish: at 141×42 the 19-cell SERVICES content already clipped its 33-cell mixed
line. Explicit state words increase that example to 46 cells (`verifier down publ…` rendered);
health unavailable fits its second body line. The mixed line clears at 302 terminal columns,
all-unreported at 386; these are content measurements, not adopted pins. This branch does
not claim every service combination is whole at 141. See follow-up evidence paths.

### Final branch checks and real CLI captures

- Named set: **1,287 passed in 780.22 seconds** (13:00), exit 0.
- Guard: **200 passed, 9,757 deselected in 119.60 seconds**, exit 0.
- `git diff --check`: clean.
- No middle tier or full suite was run.

The named set contains every touched data/widget/screen test file, plus
`tests/screens/test_address_icons_everywhere.py` and `tests/test_surf_registration.py`.
The final command was `.venv311/bin/python -m pytest -q` with these 19 paths:

```text
tests/data/test_surf_cache_swarm.py
tests/data/test_surf_manager_answers.py
tests/data/test_surf_manager_swarm.py
tests/data/test_surf_models.py
tests/data/test_surf_swarm_models.py
tests/data/test_surf_swarm_polish.py
tests/data/test_surf_swarm_polish_fixtures.py
tests/data/test_surf_swarm_seats.py
tests/data/test_surf_swarm_v2.py
tests/screens/test_address_icons_everywhere.py
tests/screens/test_surf_swarm_layout.py
tests/screens/test_surf_swarm_screen.py
tests/test_surf_registration.py
tests/widgets/test_surf_swarm_agent_hero.py
tests/widgets/test_surf_swarm_capability.py
tests/widgets/test_surf_swarm_fleet.py
tests/widgets/test_surf_swarm_hero.py
tests/widgets/test_surf_swarm_leaderboard.py
tests/widgets/test_surf_swarm_seat_record.py
```

Invocation copy: `/tmp/polish-final-named-paths.txt`; logs:
`/tmp/polish-final-named.log` and `/tmp/polish-final-guard.log`.

Six actual CLI runs used `.venv311/bin/python -m maxpane_dashboard --game surf --font-size 0`
in sized PTYs, temporary HOME with saved seat #420, unset NO_COLOR, and Textual's screenshot
at 45 seconds. These were live reads, separate from the offline tests. All six exited 0;
all SVGs were converted to PNG and visually inspected. Directory: `/tmp/polish-final-live/`,
with paired `.svg`, `.png`, `.ansi` and a local SHA-256/UTC-mtime `MANIFEST.json`.

| Mode | 138×31 capture | 119×35 capture | Observed |
|---|---|---|---|
| BOARD | `b-420-138x31.svg` | `b-420-119x35.svg` | Selected #420, grouped FLEET, source clocks and LEADERBOARD widen; no taller |
| AGENT | `a-420-138x31.svg` | `a-420-119x35.svg` | 31 rows shows taller and RECORD is below the visible body. At 119×35 RECORD shows four fetched replies with actual model/duration, then not read; long replies widen. Narrow hero fields clip below the width pin |
| SWARM | `s-420-138x31.svg` | `s-420-119x35.svg` | Both show taller, 0 quiet, closed, all services up and health ok. CAPABILITY is unavailable at capture time, with its narrow-tier widen marker |

The unavailable live CAPABILITY state is recorded as observed; it is not proof of a healthy
skills read or of the new columns' live contents. Their source/rendering proof uses committed
v4 fixtures and the named tests. Live title warnings for activity/pad were also retained.
No retry capture was substituted to hide these states.

### Repository hand-off

After the WP7 documentation commit, `git status --short` has no tracked changes:

```text
?? .codex/
?? .venv311/
?? tests/fixtures/surf/pool4/oracle_25955365.json
```

The protected pool4 oracle fixture remains untracked and uncommitted; pre-existing `.codex/`
and `.venv311/` are untouched. No credentials or secrets were added. All review artifacts
under `/tmp` are local and are not part of the commits. Stop here for Claude's whole-branch
review; the owner decides merge and push.

## 7. Fix wave — final whole-branch review 2026-09-22 (the ONE fix wave)

Review of `91818e4..8e2adfd`: **Needs fixes: 0 Critical, 4 Important**. Every named risk held:
- keyless GET-only, UUID fullmatch, and a 404 degrades one job only;
- detached tier with no handler await, and `SWARM_ANSWER_PER_CYCLE` in its `#:` block;
- seat isolation by exact hash, proven;
- five distinct states;
- sort stable with None last, global rank, token cursor, no-save header, no key collision;
- every changed pin ±1 reddened;
- colour asserted on the composite;
- contract agreement and docs.

Same rules as §0. Precedence: CLAUDE.md > §7 > §0–§6. Where §7 contradicts §2.5, §3 or
`docs/decisions.md`, edit them to match in the same commit.

**Owner decision (2026-09-22): SEAT stays as it is.** F54 stays open; do not implement §2.3.

### I1 — one non-idempotent summary wipes the whole answer slot (`data/surf_swarm.py:1451/1520/1533`)

`coerce_answers_slot` accepts a stored answer only when `answer_sentence(answer) == answer`, and
`answer_sentence` is not idempotent (list-marker and emphasis stripping run once:
`- 1) Wrote answer.json.` → `1) Wrote answer.json.` → `Wrote answer.json.`). The effects:
- `prune_answers` refuses the whole slot → `{}`;
- every RECORD row shows `not read`;
- terminal jobs are re-fetched every cycle.

The reviewer's fuzz found 36 of 20,093 such inputs (e.g. `[[a](b)](c)`, `x_*_y`, `- 2) nested`).

Fix both halves:
- **Per-point validation** (CLAUDE.md: "Validate persisted series per point"). A bad stored point
  is dropped alone, never the slot. The rest of the slot survives, and only the dropped job is due
  again.
- **The stored check is a safety predicate, not a re-derivation.** A stored `answer` is valid when:
  - it is a `str` within the length cap;
  - it contains no link target and no absolute path (the same detectors I4 uses);
  - it contains no control characters.
  Also make `answer_sentence` idempotent (iterate its strip passes to a fixed point, bounded).
  Assert both with a property-style test over a generated corpus that includes the reviewer's
  three examples.

Regressions, each proven to bite:
- the reviewer's 6-job probe: job 0's summary `- 1) Wrote answer.json. More.`, and the slot keeps
  the other five `read` after one cycle;
- no further GET for a terminal job on cycle 2;
- one hand-planted bad point drops that point only.

### I2 — quadratic link scanning on the UI loop (`surf_swarm.py:1432`)

`answer_sentence('[a](' * n)` took 0.125 s at 4 KB, 1.96 s at 16 KB and 31.7 s at 64 KB. It runs
on the app's event loop, and a seat's summary is third-party input: any seat can freeze everyone
who selects it.

Fix:
- **bound the input:** parse at most the first 4,096 characters of `summary` (only the first
  sentence is kept, so cut before parsing);
- **make link stripping linear:** one left-to-right pass or a non-backtracking regex, never a
  rescan per unclosed `[x](`.

Regression: a 100 KB hostile summary (`'[a](' * 25_000`, plus a nested-bracket variant) completes
under a generous bound (e.g. 50 ms). The test measures work, not wall-clock time: count
characters visited or iterations. Proof: restore the old scan and the test reddens.

### I3 — one failed read freezes a terminal job at `unavailable` for up to 48 h (`surf_swarm.py:1574`, `surf_manager.py:5735/5744`)

A transport failure is stored as `unavailable` with `terminal=True`, and `answer_jobs_due` skips it
until the age/cap prune. That is a *false* degradation after the source recovers (CLAUDE.md
convention). §3 and `docs/decisions.md` called this the owner's rule; it was the spec's, and it
is a spec defect.

Fix:
- **A 404 (or the seat's hash absent from a successful read) stays frozen**: it is a real answer
  about that job.
- **A transport or parse failure is never frozen.** It stays `unavailable` on screen but is due
  again after the tier's normal backoff, still within `SWARM_ANSWER_PER_CYCLE`.
- A running job's `unavailable` point does not inherit `terminal` when the job turns terminal.

Regressions:
- a failure followed by a recovered read → the next due cycle turns it `read`;
- a 404 point is never re-read;
- running → terminal does not freeze an `unavailable` point.

Correct §3 and `docs/decisions.md`.

### I4 — absolute local paths survive cleaning (`surf_swarm.py:1459`)

The lookbehind `(?<![\w:/\\])` protects URLs, but it also skips paths after a colon or a slash:
- `file:///home/imd-worker/.identitymd/work/x/answer.json` survives;
- `Saved at:/home/bob/answer.json.` survives;
- `/Users/John Smith/work/answer.json` becomes `John Smith/work/answer.json`;
- a bare home directory (`in /home/imd-worker and`) becomes `imd-worker`, the user name.

Fix:
- `file://` URIs are paths, not links to keep. Reduce them like any path.
- Detect an absolute path after `:`, `=`, `(`, quotes or whitespace. Keep protecting `http(s)://`
  URLs; those are dropped as link targets only when inside `[text](target)`.
- **Home roots** (`/home/<user>`, `/Users/<user>`, `/root`, `C:\Users\<user>`, `C:/Users/<user>`)
  never expose `<user>`:
  - a path under a home root reduces to its last component, provided that component is not the
    user segment;
  - a bare home directory becomes `~`;
  - a user segment containing spaces is consumed up to the next `/` that starts a known
    subdirectory, or to the end of the path (be explicit, test it).
- Regressions: the four examples above, plus a URL that must survive unchanged, plus the I1
  property test (cleaning ∘ cleaning = cleaning).

### Minors in this wave

- **M1:** remove restated pin numbers from prose (`.claude/rules/surf.md:196,280,284,309`,
  `README.md:202,588,603`: 27, 37, 166, 204). Name the constant instead. Bind the SKILL table's
  BOARD row (141 × 27) with the same agreement test as the AGENT row.
- **M2:** `swarm_hero.py:154` QUEUE goes back to bold; yellow is reserved for `unavailable` and the
  pre-existing pending counts (§2.1).
- **M3:** `swarm_seat_record.py:213` `took` under 60 s renders `<1m` (seconds are noise at this
  column width), never `0m`.

### Not in this wave (file or leave)

- **M4** (the first click on `#` under the default rank sort reverses it): accepted, since the
  active column reverses. Note it in README.
- **M5** (`advertised_model`/`advertised_effort` unrendered until F54): note in F54.
- **M6** (cosmetic changes such as `[/x]` → `[x]`): add to F-next as a Minor, to do when the
  function is next touched.

### Named test set (once at the end)

- `tests/data/test_surf_manager_answers.py`, `test_surf_swarm_polish.py`,
  `test_surf_swarm_polish_fixtures.py`, `test_surf_cache_swarm.py`, `test_surf_swarm_models.py`
  and `test_surf_models.py`;
- `tests/widgets/test_surf_swarm_hero.py` and `test_surf_swarm_seat_record.py`;
- `tests/screens/test_surf_swarm_screen.py` and `test_surf_swarm_layout.py -k "record or board"`;
- the SKILL/README agreement tests (`rg -n 'SKILL\.md|README\.md|rules/' tests/` and run what it
  names);
- `-m guard`.

### Hand-back

Append **§7.1** in §6.1's format:
- commits;
- per-finding red→green and mutation evidence (name the test that reddens, and why);
- the named-set and guard results;
- `git status --short`.

Stop there for the scoped re-review.
