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
- `swarm_fleet` gains `models` (a list of `{model, effort, count}` plus a `none` count).
- `swarm_seat_live` gains `advertised_model` and `advertised_effort` (None = not advertised,
  distinct from an unavailable read).
- Skill rows gain `inference`, `attempts`, `accepted`, `rejected`, `pending`.
- The SWARM hero payload gains `health_status`.
- A new cache slot for answers, with its coercer registered on load (fail closed when absent).
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
