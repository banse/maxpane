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
