# HANDOVER (Codex) — surf BOARD body (`b`), live seat state, dispatch notes, ACCEPT RATE

**Status:** scope and placement APPROVED by the owner 2026-09-22, all four parts: SWARM leaderboard,
fleet + paused, IN FLIGHT dispatch notes, AGENT live state + rejected. Placement: **a new body on key
`b`**, so the `s` SWARM body stays exactly as it is. Also approved: rename WIN RATE → **ACCEPT RATE**,
and the AGENT height of **32 rows** is accepted (F16's AGENT half closes).
Written by Claude from live keyless probes of `api.imd.fun` on 2026-09-22 ≈01:55–02:05 UTC.
**Tier:** 2: two new endpoints, a new tier, new contract keys, a new body, new widgets, > 6 files.
§1–§5 are the spec; §6 is the plan.
**Authority:** the repo's `CLAUDE.md` > this file > your judgement. Where this file contradicts
CLAUDE.md, CLAUDE.md wins; record it as a defect of this file in your hand-back.

---

## 0. Setup — precondition, then branch

The owner fast-forwards the reviewed seat-details branch into `/Library/Vibes/autopull` main
**before** you start. Check it; if it does not hold, **stop and report**. Do not merge anything
yourself.

```bash
cd /Users/banse/codex/maxpane
git status --short            # untracked only: .codex/ .venv311/ tests/fixtures/surf/pool4/oracle_25955365.json
                              #   tests/fixtures/surf/swarm/v3/ (the captures below) and this file
git fetch autopull main
git log --oneline -1 autopull/main   # MUST be 75fcb2e docs(surf): file F44–F45 … — else STOP
git switch -c feature/surf-swarm-board autopull/main
```

Same rules as the last two handovers:
- use `.venv311` (Python 3.11, textual 8.1.1, local sybilkit editable);
- `HOME=$(mktemp -d)` and `env -u NO_COLOR` for anything that composes a screen;
- TDD: write the failing test first;
- ⚑ = mutation proof, recorded in the commit message;
- commit with explicit pathspecs only, and never commit `tests/fixtures/surf/pool4/oracle_25955365.json`;
- one writer in the tree at a time;
- never push, merge or tag; no full suite;
- no test touches the network.

The first commit is this file plus the v3 fixtures and their MANIFEST (see WP1).

---

## 1. What the API serves now (measured)

### `GET /contributors` (32 KB)

Top level: `{receipts: 8226, tokensPerCompletedJob: 371004, contributors: [101 rows]}`.

Each row has these fields:
- `deviceKey`
- `wallet` (0x)
- `tokenId`: a decimal **string**
- `attempts`, `accepted`, `rejected`, `pending`: ints
- `wallClockMs`, `inputTokens`, `outputTokens`, `cachedInputTokens`: decimal **strings** (large integers)
- `turns`: int

Facts:
- `attempts == accepted + rejected + pending` on all 101 rows.
- **Rows are per device, not per seat.** Seats #1089 and #1129 each have two rows, from two devices.
  Aggregate by `tokenId`: sum every counter and count the devices.
- Swarm sums: 8,226 attempts (= `receipts`), 6,555 accepted, 242 rejected, 1,429 pending.
- 8 contributors are not live in `/workers`.
- **Token counts are not comparable across runtimes.** Claude seats report `inputTokens` without the
  cache (median 1,256); codex seats report millions (median 2.4 M). `tokensPerCompletedJob` could not
  be reproduced from the rows (in+out / accepted ≈ 36 k, all incl. cached ≈ 680 k, neither is 371 k).
  → Show it only **as served, labelled**. Never recompute it and never rank seats by tokens.

### `GET /workers` (97 KB)

Top level: `{count: 91, workers: [91 rows]}`.

Each row has these fields:
- `deviceKey`, `seat {tokenId (str), agentId (str)}`
- `working` (int), `maxConcurrency` (int)
- `paused`: `null`, or `{until (ISO), consecutiveFailures (int)}`
- `daemonVersion`, `runtimes [{id, version}]`, `profiles [str]`, `tools [str]`, `skills [str]` (30 on 88 seats)
- `platform {os, arch, nodeVersion}`
- `connectedHere`, `connectedAt`, `lastHeartbeatAt`

What the capture shows:
- **11 seats paused**, each after 3 failures, with `until` a few minutes out.
- Total capacity (sum of `maxConcurrency`) is 151; `working` is 0 on all 91.
- Runtimes: codex 53, claude 37, both 1.
- Daemons: `0.1.0+5e34612c` 67, `+1308af71` 18, `+285d1984` 3, `+358bb77c` 2.
- OS: linux 75, darwin 12, win32 4.
- Profiles: `none+foundry` 68, `none` 23.
- `/health` says `connectedDaemons 92` at the same minute. That is a different count from a different
  route: label each count with its own source and never reconcile the two.

### `GET /jobs/<id>`

Already read: `nodes[].seat`, `nodes[].verdict`. **New and useful:**
- `nodes[].dispatchNote` (+ `dispatchNoteAt`), e.g.
  `"no online contributor is eligible for this node; 8 paused after repeated failures"`;
- `nodes[].failureReason`, e.g. `"budget_exhausted"` on a failed node with `seat: null`,
  `attempt: 3`.

`allowedPaths` is low value: do not display it.

### Two sources disagree slightly

In the same minute, `/seats/420` said attempts 204 / accepted 190, while `/contributors` said
207 / 189 (+ 2 rejected, 16 pending). **Every number on screen comes from exactly one source, and a
line never mixes the two.**

### Captures

These are already in the tree, untracked, at `tests/fixtures/surf/swarm/v3/`. Commit them in WP1 with a
`MANIFEST.json` (route, http_status 200, captured_on 2026-09-22, captured_at "≈01:55–02:05Z (live
probe by Claude)", selected_because):

| file | selected because |
|---|---|
| `workers.json` | 91 live, 11 paused |
| `contributors.json` | per-device rows, two seats with two devices each |
| `health.json` | connectedDaemons 92 beside workers 91 |
| `seat_420_with_contributors.json` | `/seats/420` read in the same minute as the two above; shows the source mismatch |
| `job_5a4dfb13_dispatch_note.json` | an executing job with a dispatchNote |
| `job_0ed3e9f8_blocked.json` | a failed node, `budget_exhausted`, seat null |
| `job_33016bad_two_node_verdict.json` | a two-node detail carrying `seat` + `verdict` |

Tests may reshape these (drop a list, stringify a number) inside the test. Never fetch.

---

## 2. Design

### 2.1 WP0 first, on its own: ACCEPT RATE + F16

The AGENT hero box WIN RATE is retitled **ACCEPT RATE**. The formula is unchanged: `accepted /
attempts` from `/seats`, with the `of attempts` second line. Change every user-facing
"win rate" / "won" that means `accepted`:
- SEAT's `won M (… % of attempts)` → `accepted M (… % of attempts)`;
- BY NODE's `won` / `win` headers → `acc` / `rate`;
- STATUS's `won MM-DD HH:MM` → `accepted MM-DD HH:MM`, and `no wins yet` → `none accepted yet`.

Contract field names may stay (`win_rate`, `last_won_ts`); say so in the docstring rather than
renaming keys. Mark F16 in `docs/surf_swarm_followups.md` **closed for AGENT** ("owner accepted 32
rows, 2026-09-22"). The `s` body's 42 rows remains F16's open half.

### 2.2 The BOARD body — key `b`, the seventh surf mode

```
[SEATS 101][LIVE 91 workers][PAUSED 11][CAPACITY 0 of 151 working][ACCEPT RATE 79.7 %][RECEIPTS 8,226]
┌ LEADERBOARD · lifetime · as of HH:MM ─────────────────────────────┐┌ FLEET · as of HH:MM ────────┐
│  #  seat   runtime  dev   att   acc  rej  pend   rate  turns  hrs  state          ││ runtime  codex 53 · claude 37 · both 1 │
│  1  #494   codex      1   348   293   13    42  84.2%  1,420 20.3  ○ idle         ││ daemon   5e34612c 67 · 1308af71 18 · +2 │
│  2  #1548  claude     1   244   222    3    19  91.0%    912  …    ⏸ 01:58 ×3     ││ os       linux 75 · darwin 12 · win32 4 │
│  …  every seat, scrolls; ▸ marks the AGENT seat                                   ││ profile  foundry 68 · none 23          │
│                                                                                   ││ slots    1×50 · 2×30 · 3×3 · 4×8       │
│                                                                                   ││ heartbeat 01:54:48 – 01:55:06          │
│                                                                                   ││ tokens / completed job 371,004 (served)│
│                                                                                   ││ PAUSED  #990 until 01:55 ×3 · …        │
└───────────────────────────────────────────────────────────────────────────────────┘└────────────────────────────────────────┘
```

- **Hero** (six boxes, the shared hero base, titles top-aligned like `c529ee5`):

  | box | shows | source |
  |---|---|---|
  | SEATS | seat count | aggregated `/contributors` |
  | LIVE | worker count, labelled "workers" | `/workers` |
  | PAUSED | paused seats | `/workers` |
  | CAPACITY | `working of maxConcurrency` sums | `/workers` |
  | ACCEPT RATE | swarm `accepted / attempts` | `/contributors` sums |
  | RECEIPTS | `receipts` | `/contributors` |

  `/health`'s `connectedDaemons` is **not** shown here: it stays on `s`, where it already is.
- **LEADERBOARD** (new widget, a `SwarmTableBase` subclass like CAPABILITY): one row per seat,
  aggregated.
  - Sort: `accepted` desc, then rate desc, then token asc; `#` is that rank.
  - Columns: `#`, seat, runtime (from `/workers`; `offline` when the seat is not in a good
    `/workers` read; `unavailable` when `/workers` is unread), dev, att, acc, rej, pend,
    rate (acc/att; `—` at 0 attempts), turns, hrs (wallClockMs, 1 dp), state.
  - State values: `● working N`, `○ idle`, `⏸ HH:MM ×N` (paused until, failures), `offline`,
    `unavailable`.
  - The wallet is **not** shown here: AGENT already shows the owner as an address cell. No token column.
  - `▸` marks the current AGENT seat.
  - **Enter on a row = what `i` does with that number:** validate, persist to `~/.maxpane/config.toml`
    through `maxpane_dashboard.config.save_seat` — the function `SeatInputScreen` uses (`screens/seat_input.py:81`); no second writer, call the
    manager's `set_seat`, and open AGENT. No network await in the handler.
- **FLEET** (new widget, a fixed-line panel): runtime / daemon / os / profile / slots mixes as
  `value count`, sorted by count desc then value, as many as fit then `+N`. Also:
  - the heartbeat range (oldest–newest `lastHeartbeatAt`, `HH:MM:SS`);
  - `tokens / completed job N (served)`;
  - a PAUSED line with seats sorted by `until`, as `#token until HH:MM ×failures`, `+N`.

  Daemon versions are shown as served: do not call any of them "latest" or "outdated", since the
  API does not say which is current.
- A failed `/workers` read with a good `/contributors` read still paints LEADERBOARD (runtime and
  state `unavailable`) and vice versa. Each panel carries the `as of HH:MM` of the read it used.

### 2.3 AGENT additions

- **STATUS** (hero), from the seat's `/workers` row(s), with devices aggregated:
  - `working N of M` when live;
  - `⏸ until HH:MM ×N` when paused;
  - `accepted MM-DD HH:MM` (from WP0);
  - `offline` when the seat is absent from a good `/workers` read, `unavailable` when `/workers` is
    unread. The old `online` bool from `/seats` is replaced by this.

  Keep three lines; the box width is measured in WP5.
- **SEAT panel**, one new line group from `/contributors` only, labelled so it cannot be read as a
  sum of the `/seats` line above:
  - `contributors  207 att · 189 acc · 2 rej · 16 pend`
  - `              2,189 turns · 8.1 h · rank #N of M`
  - A seat absent from a good read: `contributors  not listed` (a real negative).
  - Unread: `contributors  unavailable`.

  From `/workers`: `skills 30 · profiles none, foundry · linux x64` (the fields are third-party:
  sanitise them).
- REJECTED is served again, so the D2 rationale ("not served") no longer holds for rejections. Record
  that in `docs/decisions.md` in WP6.

### 2.4 IN FLIGHT (`s` body)

`swarm_inflight_rows` gains `note` (str | None) and `note_kind` (`"dispatch"` | `"failure"` | None):
- `dispatchNote` when the row's node carries one;
- else `failureReason`;
- else None.

Render it as the row's last column (clipped, `‹` when cut, sanitised). The `s` pins and
`INFLIGHT_NEVER_CLEARS_BELOW` are re-swept in situ. IN FLIGHT still lists only `executing` jobs:
do not widen it to blocked jobs.

---

## 3. Data contract (WP1 freezes it in `data/surf_models.py`)

New keys (names are proposals; keep them if nothing in CLAUDE.md argues otherwise):

- `swarm_board_summary`: `{seats, live, paused, capacity, working, attempts, accepted, rejected,
  pending, receipts, tokens_per_completed_job}`. Each field is `None` when its source is unread.
- `swarm_board_rows`: `SURF_ROW_KEYS`, with:
  - `rank, token_id (int), agent_id (str|None), devices, runtime (str|None), attempts, accepted,
    rejected, pending, accept_rate (float|None), turns, wall_clock_s (float|None)`;
  - `live_state` (`"working"|"idle"|"paused"|"offline"|None`), `working`, `paused_until_ts`, `failures`.
- `swarm_fleet`: `{runtimes, daemons, os, profiles, concurrency}` (each a list of `{value, count}`),
  plus `heartbeat_oldest_ts`, `heartbeat_newest_ts`, and `paused: [{token_id, until_ts, failures}]`.
  `None` when `/workers` is unread.
- `swarm_board_as_of_hhmm` (the contributors read), `swarm_workers_as_of_hhmm` (the workers read).
- `swarm_seat_live`: `{live (bool), working, max_concurrency, paused_until_ts, failures,
  heartbeat_ts, devices}`. `live False` = absent from a good read; the key is `None` when unread.
- `swarm_seat_contrib`: `{listed (bool), attempts, accepted, rejected, pending, turns, wall_clock_s,
  rank, ranked_of}`. `listed False` = absent from a good read; `None` when unread.

Changes to existing contract:
- `swarm_seat_summary` gains `skills (int)`, `profiles (list[str])`, `platform (str)` from
  `/workers`, **or** put those in `swarm_seat_live`. Choose one and say why; they must not be mixed
  into `/seats` fields.
- `swarm_inflight_rows` gains `note`, `note_kind`.
- `SWARM_WIDGET_SIGNATURES` gains `SurfSwarmBoardHero`, `SurfSwarmLeaderboard`, `SurfSwarmFleet`,
  and extends `SurfSwarmAgentHero`, `SurfSwarmSeatVerdicts`, `SurfSwarmInFlight`.

Parsing, in `data/surf_swarm.py`:
- decimal-string counters are parsed strictly: ASCII digits only; a bool, float, negative or garbage
  value → `None`. Reuse `parse_seat_token` / `_seat_id` for token ids; do not re-declare them.
- A malformed row is dropped, never zero-filled.
- A missing top-level list → the whole key is `None` (see I2 of the last wave).

---

## 4. Fetching

- `SwarmClient.fetch_workers()` and `fetch_contributors()`: GET, the same host pool, rotation and
  pacing as the siblings; `dict | None`.
- **One new tier, `TIER_SWARM_BOARD`**, TTL 120 s with the siblings' backoff and stale rules. It has
  **two last-good slots**, `SLOT_SWARM_WORKERS` and `SLOT_SWARM_CONTRIBUTORS`, each validated per
  field on load (third-party input). One failed endpoint never blanks the other.
- The tier refreshes whatever body is open, like the other swarm tiers: AGENT's live state needs it
  too. Both reads happen once per cycle; there is no per-seat fan-out.
- Seat selection on AGENT (`set_seat`) does **not** re-read the board tier. AGENT's live and
  contributors keys are looked up in the cached board slots for the selected token, so a seat switch
  is instant and can never show seat A's live state under seat B.

---

## 5. Layout (read `.claude/skills/terminal-layout/SKILL.md` first)

- **New pins:** `SURF_BOARD_FULL_LAYOUT_COLUMNS` / `_ROWS`, with `#:` blocks in `screens/surf.py`.
  CSS goes in both `DEFAULT_CSS` and `themes/minimal.tcss`. Sweep in situ as the AGENT blocks describe:
  - widths 60–225 at height 80, and heights 20–61 at 150 and at the pin;
  - capture = the v3 fixtures;
  - worst case = 999 seats, five-digit counters, 64-char runtimes/daemons, 99 paused, 20 daemon
    versions.

  LEADERBOARD scrolls, so it floors at 8 lines like the other tables. Report whether the BOARD body
  fits the owner's 35 and 31 rows.
- **Re-swept pins:**
  - `SURF_AGENT_FULL_LAYOUT_*` (131 × 32): STATUS and SEAT change.
  - `SURF_SWARM_FULL_LAYOUT_*` (141 × 42) and `INFLIGHT_NEVER_CLEARS_BELOW`: IN FLIGHT's note column.

  If a pin moves, update its `#:` block, the test thresholds and the SKILL.md row together.

---

## 6. Work packages (serial, each its own commit(s), named set green + `-m guard`)

**WP0 — ACCEPT RATE + F16 (Tier 0 scale).** §2.1.
- Tests: `tests/widgets/test_surf_swarm_agent_hero.py`, `tests/widgets/test_surf_swarm_seat_verdicts.py`,
  `tests/widgets/test_surf_swarm_seat_nodes.py`, `tests/screens/test_surf_swarm_screen.py -k same_row`.
- ⚑ The old title/words are gone from composited output.

**WP1 — fixtures + contract.**
- Commit the v3 fixtures + `MANIFEST.json` + a loader beside `swarm_seat_capture()` in
  `tests/surf_swarm_fixtures.py`.
- Freeze §3 in `data/surf_models.py`.
- Update `tests/data/test_surf_swarm_models.py`, `tests/data/test_surf_models.py`,
  `tests/widgets/test_surf_widget_contract.py`, `tests/test_surf_registration.py`.
- Update `docs/imd_swarm_api.md` with §1. Transitional reds allowed: list them in the commit message.

**WP2 — client + pure folds.**
- `data/surf_swarm_client.py`: the two fetches; tests use a transport that raises on use, plus
  canned responses.
- `data/surf_swarm.py`: `board_rows`, `board_summary`, `fleet`, `seat_live`, `seat_contrib`, and the
  inflight note. ⚑ proofs:
  - devices aggregate per token (#1089 = 248+13 attempts);
  - strict string-int parse (`"12.5"`, `"-1"`, `True` → None);
  - `offline` vs `unavailable`;
  - a paused seat's `until`/failures;
  - `listed False` vs `None`;
  - the note prefers dispatchNote over failureReason.
- Pin fixture truths by computing them in the test from the fixture: never hardcode a derived number.

**WP3 — manager + cache.**
- `data/surf_cache.py`: tier + two slots + coerce.
- `data/surf_manager.py`: the task, keys, per-endpoint degrade, AGENT lookups by selected token.
- Tests: `tests/data/test_surf_manager_swarm.py`. ⚑ proofs:
  - the exact emitted key set;
  - a failed `/workers` keeps the leaderboard;
  - a seat switch never shows the old seat's live/contrib;
  - a hand-edited slot is refused.

**WP4 — BOARD body.**
- Widgets `swarm_board_hero.py`, `swarm_leaderboard.py`, `swarm_fleet.py` (+ `__init__` exports).
- `screens/surf.py`:
  - `MODE_BOARD`, `Binding("b", "toggle_board", "Board", show=False)`;
  - `_show_mode` and the hero swap (BOARD is not in `_SURF_HERO_MODES`, per the
    enumerate-don't-negate rule);
  - PANELS dispatch, the Enter handler, both CSS copies, pins (§5).
- README "Keyboard shortcuts" (the owner of keys) + a BOARD paragraph; `.claude/rules/surf.md`.
- Tests: new widget test files; `tests/screens/test_surf_swarm_screen.py` (b opens/escape/twice; one
  hero per body; the Enter-sets-seat-and-persists path through the same writer; the bindings test —
  update `test_the_bindings_gained_a_and_i_and_nothing_else`);
  `tests/screens/test_surf_swarm_layout.py`; `tests/screens/test_address_icons_everywhere.py`
  (the BOARD body must carry no 0x text at all, or it gets icons);
  `tests/screens/test_surf_screen.py`; `tests/test_surf_registration.py`.
- ⚑ proofs: Enter persists via the shared writer; `▸` follows the AGENT seat; `+N` markers in FLEET;
  every third-party string escaped.

**WP5 — AGENT + IN FLIGHT.**
- §2.3 and §2.4 in `swarm_agent_hero.py`, `swarm_seat_verdicts.py`, `swarm_inflight.py`.
- Re-sweep the AGENT and SWARM pins.
- Tests: the AGENT widget/screen/layout files + `tests/widgets/test_surf_swarm_inflight.py`. ⚑ proofs:
  - the `/contributors` line never shares a line with `/seats` numbers;
  - `not listed` vs `unavailable`;
  - STATUS `offline` vs `unavailable`;
  - the note column clips with `‹`.

**WP6 — docs.**
- `docs/decisions.md`: BOARD as a body, not a fourth `s` row (owner, 2026-09-22); D2 partially
  withdrawn (rejections served by `/contributors`); token counts shown only as served.
- `docs/surf_swarm_followups.md`: close what this closes, file residuals as the next F-numbers.
- `docs/imd_swarm_api.md` final.
- Run the doc-pinning tests: `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`, and every file
  it names.

---

## 7. Done means — hand-back

1. Every WP green on its named set + `-m guard`, one commit each (pathspec), ⚑ in the messages.
2. Run the middle tier once at the end:
   `env -u NO_COLOR HOME=$(mktemp -d) .venv311/bin/python -m pytest -n 4 --dist loadfile -m 'not screen' sybilkit/sybilkit_tests tests`
   Then run every `tests/screens/` file you touched. **No full suite.**
3. Render once for real (`--game surf`, then `b`, `a`, `s`) at each new pin and at 119 / 138 columns.
   Say what you saw.
4. Append §8 hand-back:
   - branch, commits;
   - every pin number, and what binds it;
   - ⚑ proofs;
   - each deviation, and why;
   - residuals filed.

   **Stop.** Claude runs the final whole-branch review, one fix wave, and the full suite once. The
   owner decides merge and push.

Out of scope: `/health` changes, `/seats` changes, pagination of `/jobs`, token-based rankings or
costs, a version bump, and pushing.

---

## 8. Codex hand-back — 2026-09-22

Branch: `feature/surf-swarm-board`, based on fetched `autopull/main` at
`75fcb2ee89690069eb895dca16db3816c6b56e83`. The fetched ref and source repository's main/HEAD
both passed §0 before branch creation. Packages ran in order with one repository writer.
No push, merge, tag, version bump or full-suite run. The protected oracle fixture remains untracked.

### Commits

| Package | Commit | Result |
|---|---|---|
| Setup/captures | `c8dcb28` | handover, seven unchanged v3 captures, provenance/checksum MANIFEST |
| WP0 | `d051dcc` | ACCEPT RATE/accepted labels, measured label geometry, F16 and F45 |
| WP1 | `4aec105` | frozen 32-key SWARM/191-key SURF contract, loader and source documentation |
| WP2 | `47d2247` | endpoint reads, strict folds, worker state/metadata, dispatch notes and F44 |
| WP3 | `9218d21` | detached BOARD tier, independent validated slots and selected-seat lookups |
| WP4 | `7899026` | BOARD widgets/body, shared seat selection and composited status coverage |
| WP5 | `44e6255` | source-separated AGENT details, IN FLIGHT notes and measured geometry |
| WP6 | `28f1ecf` | decisions, final API documentation and follow-ups |

This §8 is committed separately after the final checks below.

### Tests and mutation proofs

Every ⚑ has exact mutations and failing test IDs in its package commit message. Each mutation
was reversed before proceeding. Test processes used `.venv311`; screen composition used an
isolated HOME with NO_COLOR removed. Tests used frozen/canned sources and no network or clipboard.
Mutation processes cleared only the target module's bytecode and used PYTHONDONTWRITEBYTECODE.

| Package | Red → verification evidence | Mutation coverage |
|---|---|---|
| WP0 | 17 initial failures; 61 named + 232 layout passed; guard 200 | seven changes: old title/accepted labels, SEAT/BY NODE words and both width boundaries |
| WP1 | 20 initial failures; 311 passed + five explicitly staged signature failures; guard 200 | contract-only package; all three BOARD and two AGENT signature seams resolved by WP4/WP5 |
| WP2 | 78 initial failures; 528 passed; guard 200 | seven changes cover all six flags: device aggregation, decimal/bool rejection, offline, pause pairing, missing vs empty contributors, dispatch precedence |
| WP3 | 28 initial failures; 320 passed; guard 200 | six changes cover exact keys, independent failure, token isolation, load validator and both consumption validators |
| WP4 | final focused 531 passed; COINS boundary 2 passed; guard 200 | 18 changes cover persistence, selected marker, exact omissions, third-party text/clocks, real-unavailable labels and pin boundaries; controller independently proved 142→141 fails, restored 142 passes |
| WP5 | 15 initial failures; literal-ellipsis regression failed first; named 1,026 passed/one stale skill-read failure, recovered 13; restored affected 337 passed; guard 200 | 17 changes cover all four flags plus source gates/clocks, sanitization, literal ellipsis, narrow overflow and both height/IN FLIGHT boundaries |
| WP6 | 4,732 passed across all 50 discovered test files; guard 200 | documentation-only; no new mutation requirement |

WP4's initial named run had 885 passes and six failures: four stale expectations recovered in
four passing checks; two declared AGENT signature seams waited for WP5. WP4's first mutation
harness had an inverse-offset defect, repaired before rerunning all 18 proofs; that invalid run
is excluded from the evidence. The clean harness and WP5 compare the complete restored source
with its pre-mutation text. WP5's stale skill-row failure read 32 before its update to 36; the
exact registration check passed in recovery and in the final restored gate.

### Measured layout

Canonical measurement records remain beside the constants in `screens/surf.py`; the skill table,
CSS copies and permanent boundaries agree. Pins were remeasured because acceptance labels,
the `b board` status hint, AGENT source groups and IN FLIGHT note widths changed rendered content.

| Surface | Final columns × rows | Binding content / exception |
|---|---|---|
| BOARD `b` | **142 × 23** | full leaderboard columns from 141, whole status from 142; FLEET fixes height; table floor eight lines |
| AGENT `a` | **142 × 36** | body full from 138, hero from 134, whole status from 142; SEAT's 15 detail lines require a 17-row top floor |
| SWARM `s` | **142 × 42** | body from 141, whole status from 142; unchanged THROUGHPUT/top-row height floor |
| LAUNCHPAD `l` | **142 × 31** | unchanged body from 138; new status hint binds width |
| App-wide | **143 columns**, unchanged | existing market seam; no app-wide height claim |
| Pool4 bodies | **99 × 45** experimental; **119 × 35** market, unchanged | their body pins do not promise the expanded status hint fits |

WP0 first moved AGENT 131→132×32 for the accepted labels. WP4's region-only status measurement
initially suggested 141; visual inspection showed the final `f` in `surf` was clipped. Comparing
the expected right label to its actual composite established 142 and now permanently guards it.

BOARD swept each integer width 60–225 at 80 rows and heights 20–61 at 150 and the measured pin,
using captures, 999-seat/five-digit/long-runtime/99-pause/20-version stress and source failures.
WP5 repeated those ranges for 11 AGENT payloads and three SWARM payloads, including #0, #420,
duplicate reviews, v3, stress and independent missing-source states. No region overflow remained.
A fixed 63-column SEAT overflowed at width 60; a failing regression preceded the flexible share
capped at 63 outer / 59 content cells.

BY NODE now reaches selected/compact/full widths at 105/125/138. SEAT fixed lines clear at 108
for #0, 106 for #420/v3, 128 under five-digit stress, and 70 without a seat. Long worker metadata
and runtime strings retain explicit ellipses; ordinary fixed labels and failures fit. IN FLIGHT's
full-tier/no-note lower bound moves 190→**222**. The captured 81-character note clears at **532**,
and a synthetic 309-character note at **1558**, checked in situ on both adjacent widths and with
the full composite. These are named content exceptions, not enlarged body guarantees.
RECORD's **297** objective onset and LAUNCHES' **205** onset remain unchanged.

BOARD fits both owner heights: 119×35 uses tight columns and 138×31 compact columns, with widen
but no taller cue. The tests do not promise whole status below 142; actual live fit also depends
on the theme/version labels (F43). AGENT now scrolls vertically at both owner sizes
(F46); SWARM continues to do so (F16). Long notes/record objectives may retain widen at full pins.

### Resolved specification details and deviations

- §0 required captures in the first commit while WP1 repeated that requirement after WP0.
  A capture-only setup commit satisfied §0; implementation then followed WP0–WP6.
- The mockup's 101 SEATS are device rows; the capture aggregates to **99 seats**. Tests derive
  fixture totals. The omitted fifth daemon is `0.1.0+e9ca5510`, count 1. Workers' 91 and health's
  92 remain independent facts, and LIVE uses the valid served count.
- Worker metadata lives in `swarm_seat_live`, keeping `/seats` pure. IN FLIGHT's existing rows
  argument carries note/note_kind, so no redundant widget keyword was added.
- Cache load accepts the manager's pure coercers; absent validators refuse BOARD slots. Manager
  revalidation also protects injected caches. No cache-to-client/fold import was introduced.
- Source clocks identify last-good versions. Changed valid payloads update only their own slot;
  unchanged successful reads advance scheduling. Partial failure preserves the failed source,
  stores a changed successful counterpart and uses the 120-second backoff.
- Missing/malformed worker pause state drops its row rather than inventing idle. Unknown optional
  metadata remains unknown; supplied empty metadata remains a real empty read.
- D2's old `/seats` premise is historical: v3 #420 itself serves rejected 2/pending 12. New displayed
  rejections are contributor-sourced; the seats fold and discrepant totals are not reconciled.
- Contributor counters use plain integers to keep the specified two-line group whole under
  five-digit stress. Their clock shares the second line; worker metadata has its own clock line.
  STATUS retains three body lines; its worker clock is in the title, seats clock in ACCEPTED.
- AGENT's requested additions raise height from the accepted 32 to 36. That new requirement is
  filed as F46; the earlier owner acceptance was not silently extended.

### Final §7 checks and real CLI observations

- Middle tier ran **once**, exactly the requested `-n 4 --dist loadfile -m 'not screen'
  sybilkit/sybilkit_tests tests`: **8,973 passed, 1 xfailed**, 126.03 s.
- Every touched screen file ran: `test_address_icons_everywhere.py`, `test_surf_screen.py`,
  `test_surf_swarm_layout.py`, `test_surf_swarm_screen.py`: **762 passed**, 478.40 s.
- Real `.venv311/bin/python -m maxpane_dashboard --game surf --font-size 0` processes ran
  in sized PTYs with fresh isolated HOME, saved seat #420, NO_COLOR removed, and actual keyless
  reads. All nine exited 0 and produced SVGs/PNGs under `/tmp/board-final-live/`:
  `b-420-142x23`, `a-420-142x36`, `s-420-142x42`, plus each mode at 119×35 and138×31.
  These are actual CLI captures, separate from the dead-transport test renders.
- At approximately **06:35–06:37 Europe/Berlin on 2026-09-22**, BOARD showed 101 live-derived
  contributor seats (the current payload differs from the frozen 99), 93–95 workers, 0 paused,
  capacities 153–156 and 8,286 receipts. The selected #420 marker stayed visible. All 12 columns
  and the whole status were visible at 142×23. At119×35 the tight table and at 138×31 the compact
  table showed widen without taller; fleet values/omission counts remained readable. Status
  cropped at 119; the captured BOARD138 frame showed its full right label.
- AGENT at 142×36 showed seats 191/205 separately from contributors 190/208, workers 0 of 1,
  independent clocks and metadata, without taller. RECORD retained its objective widen. Both
  owner geometries showed taller/body scrolling; 119 also visibly abbreviated hero boxes and
  BY NODE columns. Their status bars were cropped, consistent with the measured guarantee.
- SWARM at 142×42 had live health/job data, while CAPABILITY/LAUNCHES/SITES said unavailable.
  Its executing row's note was a dash, so the real capture does not claim to exercise the
  fixture's dispatch text. IN FLIGHT/LAUNCHES retained their named widen cues. Crucially,
  THROUGHPUT's accumulation message wrapped and lit taller even at 142×42: **F47**, not a green
  live height result. Both owner sizes also showed taller. Frozen v3 renders and mutation
  tests separately prove the actual dispatch note column.
- No full suite, push, merge or tag was run. Full release validation is intentionally deferred
  to the specified review/owner workflow. Screenshots and logs are local artifacts, not committed
  captures; no live payload was added to the test corpus.

### Follow-ups and stop point

- **F44 fixed** in `47d2247`: shared `_hex64`; regression
  `test_work_and_review_dedup_share_one_hex64_validator`.
- **F45 fixed** in `d051dcc`: permanent duplicated-review capture in layout boundaries.
- **F46 filed**: owner decision on AGENT's new 36-row requirement.
- **F47 filed**: live SWARM accumulation message wraps and needs scrolling at 142×42;
  the fixture pin does not cover that observed state. No extra layout fix wave was run.
- **F16 SWARM remains open** at 42 rows; its AGENT 32-row acceptance is historical.
- **F18/F43 remain open** for narrow status-bar fit and version/theme label dependency. WP4
  fixes the incomplete composite assertion, without claiming to fix those product constraints.
- Existing F24/F28 seats-fetch/cache limitations, F39 tokenless RECORD/BY NODE, F41 missing-work
  conflation and F42 source chronology remain outside this scope.

All requested implementation and documentation changes are committed with explicit paths.
Only the intentional local `.codex/`, `.venv311/` and protected oracle fixture remain untracked.
Stop here for Claude's whole-branch review and one fix wave; owner decides merge and push.

## 9. Fix wave — final whole-branch review 2026-09-22 (the ONE fix wave)

Review verdict on `c8dcb28..347ba5e`: **Needs fixes: 0 Critical, 1 Important**. Named risks all
held (keyless GET-only, aggregation 101→99, source separation, `save_seat` reuse, markup safety,
cache fail-closed, 131 boundary cases, six mutation proofs re-reddened for the claimed reason).
This is the only fix wave; a scoped re-review follows, then the controller runs the full suite once.
Same rules as §0: branch `feature/surf-swarm-board`, one writer, pathspec commits, `.venv311`,
`env -u NO_COLOR HOME=$(mktemp -d)`, no network, never commit the pool4 oracle fixture, no push /
merge / tag / full suite. Precedence: CLAUDE.md > this §9 > §0–§7 — where §9 contradicts §3 or §5,
§9 wins and §3/§5 are edited to match in the same commit.

### Owner decisions (2026-09-22) — these replace the open questions in §8

- **D-A (status hints): shorten every hint, keep `b`.** `KEY_HINTS` becomes
  `l launchpad · 4 pl4 · s swm · a agt · b brd` (43 cells; `rules/surf.md` requires `l launchpad`
  never shortens — it doesn't; one markup run as before). Goal: the status hint no longer binds
  any surf body's width. Re-sweep in situ and return each pin to what its **body** needs:
  LAUNCHPAD (was 138 before this branch), SWARM (was 141), AGENT (body full from 138 per §8, or
  lower after D-B), BOARD (leaderboard full from 141). If the whole bar still binds anywhere,
  report the measured number — do not pick different words yourself. Update the `#:` blocks, the
  terminal-layout SKILL table, `STATUS_BAR_WHOLE_FROM`, README key prose if it quotes the hint,
  and `rules/surf.md`'s quoted hint text.
- **D-B (F46): trim AGENT back to 32 rows at its column pin.**
  1. Remove the worker **metadata** line (skills / profiles / platform and its clock line) from
     AGENT — BOARD's FLEET already shows it. Worker live state stays in STATUS.
  2. Render the contributor group on **one** line wherever it fits at the pin (it keeps its own
     clock; still never mixed with `/seats` numbers on one line).
  3. **M5:** drop the `/seats` `online ●` flag from SEAT's paired line (§2.3 "replaced" means
     replaced) — STATUS's worker state is the only liveness on screen.
  Then re-measure. If 32 is not reached, stop and report the measured row count and which line
  binds; do not remove anything else. On 32: close F46 in `docs/surf_swarm_followups.md` with the
  measurement; the old 17-row SEAT top floor is re-derived, not kept.
- **D-C (M9): a mouse click on a LEADERBOARD row selects too** (saves, sets, opens AGENT), same as
  Enter. Pin it with a pilot test (click → monkeypatched `save_seat` called once with that token)
  and write it into §2 and README.

### I1 (Important) — a present-but-malformed row must not become a real negative

`data/surf_swarm.py:1016` admits a contributor row only when all nine counters parse (including
the undisplayed `inputTokens`/`outputTokens`/`cachedInputTokens`); `:1044/:1047` drop a worker row
with no `paused` key or any bad field; then `:1161` `live=bool(rows)` and `:1322` `listed=False`
turn the dropped seat into `offline` / `contributors not listed` while LIVE still counts it.
Reproduced on v3 fixtures: #420 with `cachedInputTokens=None` → `listed False`, seats 98;
#420's worker row with `paused` popped → `live_state 'offline'`, LIVE 91.

Fix:
- Contributor admission requires only the **displayed** counters (`attempts`, `accepted`,
  `rejected`, `pending`, and whatever else a widget actually renders — list them in the
  docstring). An undisplayed field that fails to parse becomes `None` on that row, never a drop.
- Worker admission: a missing or malformed `paused` is **unknown pause state** (`None`), not a
  drop and not "not paused"; the row still counts toward live and its seat is `live`, with PAUSED
  counting only rows whose pause state was read. Any other bad field follows the same rule:
  unknown field, row kept, if the tokenId parsed.
- A row whose **tokenId** parsed but which still cannot be admitted: remember that token in a
  `malformed_tokens` set per source; `seat_live` / `seat_contrib` for such a token answer
  `None` → the widget's `unavailable`, never `offline` / `not listed`. Only a token absent from a
  successfully read list is a real negative.
- Edit §3's "a malformed row is dropped" to say this (spec defect, CLAUDE.md wins).
- Tests, each proven to bite (mutate → the named test reddens for the stated reason → inverse edit):
  the two reproductions above as regressions (seat stays listed / live; seat count stays 99; a
  bad-tokenId row still drops), plus a malformed-but-tokened row → `unavailable` on AGENT
  composited.

### Minors — fix in this wave

- **M2** `tests/screens/test_surf_screen.py:2539`: `"‹ widen" in title or not bar_whole` cannot
  fail below the pin. Assert the COINS widen hint directly on the body, independent of the bar
  (proof: `if False and show_marker:` at `widgets/surf/launchpad.py:688` must redden it). Replace
  the bare `138` at `:2640`/`:2866` with a named constant bound to the `#:` block.
- **M3** `tests/screens/test_surf_swarm_layout.py:810–825`: the BOARD below-pin branch must assert
  LEADERBOARD's own degradation (widen lit, a column shed), not be satisfiable by the status crop;
  narrow `_EXCLUDED_FROM_WHOLE["b"]` to the worst-case payload only, so a false `‹ widen` at the pin
  on the capture fails.
- **M4** `widgets/surf/swarm_leaderboard.py:69`: detect clipping by width comparison, as WP5 did
  for IN FLIGHT — a fitting runtime containing `…` must not light widen (regression first).
- **M7** `themes/minimal.tcss:2598` comment "thirteen" vs `min-height: 17` (re-derive after D-B);
  fix the BOARD block's indentation to match its neighbours in both CSS copies; restore the
  `swarm_inflight.py` docstring rationale for why template/objective avoid `sanitize_cell`.
- **M8** `test_surf_board_body_has_no_wallet_or_token_address_text`: inject the 0x text through a
  field the BOARD fold actually receives (a `/contributors` / `/workers` row field), so the test
  would redden if the fold kept `wallet`.

### Not in this wave

- **M6 / F47**: pre-existing — `swarm_throughput.py` is untouched; the live overflow was an extra
  `states` row (content-dependent height, F23), not the wrap. Re-word F47 accordingly and link F23.
- **F16** (SWARM 42 rows) stays open for the owner.

### Named test set (run once at the end, plus per-item while working)

The BOARD/AGENT data and widget files (the 13 from the review), `tests/screens/test_surf_screen.py`,
`test_surf_swarm_layout.py`, `test_surf_swarm_screen.py`, `test_address_icons_everywhere.py`,
`tests/test_surf_registration.py`, and `-m guard`. No middle tier, no full suite.

### Hand-back

Append **§10**: commit table, each fix with its red→green and mutation evidence, the re-measured
pins (every surf body, columns × rows, and what binds), whether AGENT reached 32, the named-set
result, and `git status --short`. Stop there for the scoped re-review.

---

## 10. Codex fix-wave hand-back — stopped at D-B, 2026-09-22

**AGENT did not reach 32 rows.** The exact requested row removals produced a measured
**33-row** minimum. Per §9 D-B (“If 32 is not reached, stop and report … do not remove
anything else”), the wave stopped at this gate. No production fix was retained; the trial
and its temporary tests were reversed by explicit inverse edits, with every changed file
compared against its captured original text. F46 remains open.

Branch: `feature/surf-swarm-board`; starting HEAD: `61c5f28` (the committed §9 instructions).
One repository writer; a separate planning agent was read-only. No network, middle tier,
full suite, push, merge or tag.

### Commit table

| Change | Commit/result |
|---|---|
| Approved §9 instructions | `61c5f28`, already present before this run |
| D-B/M5 feasibility trial | Uncommitted; entirely inverse-restored after the stop gate |
| This hand-back | Documentation-only commit, `docs(surf): report D-B 33-row stop gate` |

### D-B measurement and red → green evidence

The trial removed the worker metadata and worker-clock rows, joined the two contributor
rows into one line retaining every counter, turns, hours, rank and its own clock, and removed
`/seats` liveness from the paired line (M5). It preserved STATUS worker state, every other
SEAT fact, title spacing, hero geometry and RECORD's existing floor. Both CSS copies used
the actual reduced SEAT floor.

- Temporary widget regressions
  `test_fix_wave_contributors_keep_every_fact_and_clock_on_one_line` and
  `test_fix_wave_worker_metadata_and_seats_liveness_are_absent`: **2 failed → 2 passed**.
- An in-situ fixture screen probe measured ordinary v3 and five-digit stress payloads,
  widths 190–245 and heights 31–35 at their whole-content widths.
- Temporary `test_fix_wave_agent_requested_height_gate`, parameterized across both payloads
  at 32 and 33 rows: **2 failed at 32; 2 passed at 33**, 3.56 s. Both 32-row cases reached
  the actual `taller` assertion after passing horizontal-content, overflow and 14-row floor
  assertions. This was a measured height failure, not a prediction from arithmetic.
- At 33 rows: SEAT/top region starts at y=10 and is 14 rows; RECORD starts at y=24 and is
  8 rows; status is at y=32. At 32, `‹ taller` and body scrolling remain; RECORD is below
  the initial viewport. The controller inspected the 32/33 rendered PNGs.
- Binder: **12 SEAT detail lines + title + mandatory blank = 14 rows**. RECORD's existing
  floor is **8**; unchanged remaining chrome uses **11**: measured total **33**.
  `.claude/rules/widgets.md` requires the title blank; it was not removed to force success.
- Keeping the original full labels on one contributor line also widened this diagnostic
  trial: whole-content onset **208 columns** for v3, **240** for five-digit stress.
  These are unoptimized trial measurements, **not proposed or adopted pins**. Even with
  enough width for every fact, the height remained 33. No additional field removal or
  layout redesign was inferred from D-B.

The temporary trial patch and evidence are local:
`/tmp/board-wave-gate/trial.patch`, `results.json`, `inverse-proof.json`,
`v3-208x32.png`, `v3-208x33.png`; test logs:
`/tmp/board-wave-gate-red.log`, `board-wave-gate-green.log`,
`board-wave-gate-height-test.log`, `board-wave-gate-restored-green.log`.
No successful fix or mutation proof is claimed for an unlanded trial. Reaching 32 requires
an additional owner decision about which further row or layout constraint may change.

### Findings left pending by the stop gate

| §9 item | Result |
|---|---|
| D-A shortened hints and body-bound pins | Pending; current hints and pins restored/unchanged |
| D-B / F46 | Measured 33, not 32; stopped as directed; F46 remains open |
| D-C / M9 row click selection | Pending |
| I1 malformed-but-tokened source rows | Pending; no normalization/cache change made |
| M2 COINS assertion and named boundary | Pending |
| M3 BOARD degradation assertion/exclusion | Pending |
| M4 literal runtime ellipsis | Pending |
| M5 duplicate `/seats` liveness | Trial regression passed; change restored with D-B |
| M7 CSS comments/indentation and IN FLIGHT rationale | Pending |
| M8 wallet test provenance | Pending |
| M6 / F47 wording correction | Pending; §9's correction attributes the observed overflow to an extra states row (F23), not the wrap |
| F16 SWARM height | Remains open as instructed |

§3/§5, the skill table and canonical pin comments were not rewritten for a trial that was
not adopted. No later fix or additional fix wave was performed after the stop condition.

### Production pins after restoration

These are the existing §8 measurements, **not new certifications from this stopped wave**.

| Surf body | Columns × rows | Existing binder |
|---|---|---|
| Dashboard | 143 × no single fixed row pin | IMD MARKET seam; rail scrolling is separately measured |
| LAUNCHPAD `l` | 142 × 31 | Expanded status hint; body itself clears at 138 |
| Experimental pool4 `e` | 99 × 45 | HATCHES/rail; body guarantee excludes whole status |
| Pool4 market `4` | 119 × 35 | Existing ladder/rail content; body guarantee excludes whole status |
| SWARM `s` | 142 × 42 | Status width; THROUGHPUT/top-row floor, with F23/F47 content-dependent residual |
| AGENT `a` | 142 × 36 | Status width; existing 17-row SEAT top floor |
| BOARD `b` | 142 × 23 | Status width; FLEET height, eight-line table floor |

### Verification and final status

After exact inverse restoration, the original SEAT widget file and AGENT row/floor boundary
tests passed: **27 passed in 5.94 s**. `git diff --check` is clean. Only this hand-back is
committed. The final named set and guard run were **not run**: the explicit D-B stop occurred
before a completed fix wave existed to verify. The preceding implementation's green named,
guard and middle-tier results remain recorded in §8; they are not claimed as new results here.

`git status --short` after the documentation commit:

```text
?? .codex/
?? .venv311/
?? tests/fixtures/surf/pool4/oracle_25955365.json
```

The protected oracle fixture remains untracked. Stop here for the owner to resolve the D-B
height constraint before the pending fixes resume.

## 11. Amendment to §9 — resolve the D-B stop and finish the wave (2026-09-22)

§10's stop was correct under §9's wording, but that gate was meant for **D-B only**. This
amendment replaces D-B's gate; every other §9 item (D-A, D-C, I1, M2–M5, M7, M8, M6/F47 wording)
is to be done in this same wave. It is still the ONE fix wave — §10 changed no production code.

**D-B′ — AGENT height.** Re-apply the §10 trial (worker metadata and worker-clock lines off AGENT,
`/seats` liveness off the paired line = M5), plus two **merges that remove no fact**:

1. `paired MM-DD HH:MM` joins the identity line: `IDMD #420 · agent 50939 · paired 09-20 07:34`.
2. `N queued` joins the feedback line: `feedback 149 sent · 10 submitted · 38 queued`.
   (The owner-visible 33-row PNG shows `38 queued` alone on a line; that line goes.)

**Contributors: one line only where it fits, never a wider pin.** §10's trial kept the full
single line and pushed the whole-content onset to 208/240 columns — that is not allowed.
The contributors group stays two lines when the SEAT panel is too narrow for one, and goes to one
line only above that width. It keeps every counter, turns, hours, rank and its own clock. The
AGENT **column** pin is set by D-A's re-sweep and must not rise because of this group.

Then measure AGENT's row minimum at its column pin, for ordinary v3 and five-digit stress.
- ≤ 32 → close F46 with the measurement.
- 33 or more → **do not stop and do not cut further**. Adopt the measured value as the pin, update
  the `#:` block, and leave F46 open with the number and the binding line for the owner.

Each merged line gets a composited regression (both facts on one line, the old line gone), proven
to bite. Re-derive the SEAT top floor and the `minimal.tcss` comment (M7) from the new line count.

**Order:** D-A (hints, re-sweep all surf pins) → D-B′ → I1 → D-C → M2, M3, M4, M7, M8 → F47
wording → named set (§9) + `-m guard` once at the end. Append **§12** in §9's hand-back format,
covering every item. Stop there for the scoped re-review. No push, merge, tag or full suite.
