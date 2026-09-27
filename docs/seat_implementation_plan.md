> **Overridden by `pepepane` (2026-09-26).** This document describes the mode A/B/C design, the six-surface registration and menu key 9; it is superseded by `docs/pepepane_PRD.md` and `docs/pepepane_plan.md` and kept unedited below for its history (lineage research: `sweep-seat-prd-lineage.md`).

# SEAT — implementation plan

> **POSTPONED 2026-09-21 (owner).** Not started. The API-only half of this idea — one agent's view,
> fed by the control plane and nothing local — ships instead as the `a` AGENT body of the surf swarm
> branch (`docs/surf_swarm_v2_implementation_plan.md`, Amendment A1). This plan stays as written for
> the day the local-state dashboard is wanted; its §0 review of the writer's schema still holds.

Plan for `docs/seat_PRD.md` (owner's PRD, 2026-09-20). Written 2026-09-21 from the PRD, the live
mode-B writer (`/Library/Vibes/aidude/tools/surf/_worker_page.py`, emitter at lines 1193–1262, and
its output `data/surf/worker-status.json`, 13 KB, `schemaVersion: 1`) and the registry survey.
**Triage: Tier 2** — a new dashboard, six-surface registration, four shared owner-gated files.
House conventions apply unchanged and are not re-derived (`CLAUDE.md`, `.claude/rules/*.md`,
`.claude/skills/terminal-layout/SKILL.md`). **Runs after the SWARM v2 branch is merged**; it
shares no file with it except the registry surfaces, which SWARM v2 does not touch.

---

## 0. PRD review — what the plan corrects before building on it

**R1 — The schema in PRD §3 is not the schema the writer emits. The writer is the contract.**
Differences, all live in the file today: `seat.server` exists (PRD omits); `seat.capacity` is a
string; `seat.owner` (PRD) **does not exist** — there is no address in the `seat` block;
`daemon.heartbeatAgeSeconds` exists; `container.status` exists and `container.memoryPercent`
replaces the PRD's `memoryLimit`; `container.pids` is a string; `fleet.deployBreaker` and
`fleet.controlPlaneVersion` exist; `reputation.rows[]` carry `tag2` and `client` (an address) and
**no `jobId`**; `current`, `reputation` and `cost` are **whole-block `null`** when their source is
not ok, and inside an ok block any field may still be `null`; `sources` has **eight** blocks
(`heartbeat`, `status`, `container`, `stats`, `tasks`, `chain`, `health`, `transcripts`), not two.
WP0 freezes schema v1 **from the emitter** into `docs/seat_status_schema_v1.md` (the cross-repo
contract the PRD §8 asks for) and copies the live file, verified free of any private key, as the
healthy fixture. The PRD's JSON block is superseded by that document.

**R2 — Mode A is asserted, not measured (PRD §9 says so).** Its paths, the log format after
rotation and the permission decision are all unconfirmed on the VPS. The plan therefore builds
**one reader interface and one implementation** (mode B, the status file). Mode A is a second
implementation behind the same interface, planned as **WP7, gated on a measurement task** the
owner runs on the VPS (a script that prints what the four paths contain, as non-root) — no code
for it is written against assumptions. Mode C is not planned.

**R3 — `sources` decides availability, not the presence of a value.** The PRD says it; the writer
does it (a not-ok block is emitted as `null`, or field-by-field `null`). The manager's rule is one
function: a block whose `sources.<name>.ok` is false yields `None` for every key it feeds, even
when values are present (a future writer might keep stale values). Which source feeds which block
is frozen in WP0 (`SEAT_BLOCK_SOURCES`), read off the emitter: `seat`←`status`, `daemon`←`heartbeat`,
`container`←`container`+`stats`, `fleet`←`health`, `current`/`tasks`←`tasks`, `reputation`←`chain`,
`cost`←`transcripts`.

**R4 — The hero's three states need named thresholds, not "~10 minutes".** The writer runs every
5 minutes; amber is two missed writes. WP2 names `SEAT_STALE_AFTER_S = 600.0` with a `#:` block
saying exactly that, and the classification takes `now_ts` (the whole panel is untestable
otherwise). Precedence is frozen: **red** (`daemon.state != "alive"` or `container.running`
falsy) beats **amber** (file age) beats green; a file so old that its "alive" is meaningless is
still amber, because the reader cannot know — the age is shown beside the word.

**R5 — Cost has no money in it, and the PRD is right.** Tokens only. WP4's COST panel takes no
price input and has no `$` anywhere; a test greps the rendered strips for it.

**R6 — `fleet` duplicates the SWARM hero's numbers through a second path.** It stays (it is what
the writer has, and the PRD's "is it me or the swarm" question needs it beside the machine), but
MACHINE labels it `fleet (via writer)` so a reader does not take it for a live read.

**R7 — Visibility.** The PRD registers SEAT at menu key `9`. On every machine without a writer the
dashboard is one panel saying how to get one. That is the PRD's call and the plan follows it;
the alternative (launchable by `--game seat` only, hidden from the menu like `frenpet_full`) is a
one-line change in WP6 if the owner prefers. **Default: visible at `9`.**

**R8 — No `docs/seat_game_mechanics.md` exists.** PRD §2 carries the five facts and
`/Library/Vibes/aidude/docs/worker-runbook.md` the operator detail; the CLAUDE.md pipeline asks for a
mechanics doc per dashboard. WP0 writes a short one that points at both rather than restating them.

**R9 — Prefetch.** `MaxPaneApp` prefetches the menu's default dashboard, not every manager; the seat
manager reads a local file and is cheap, so it joins `_prefetch_manager` like every other.

**Open for the owner (defaults stated):** (a) menu-visible at `9` — default *yes* (R7); (b) the
env var name — default `MAXPANE_SEAT_STATUS` (the PRD's), a file path, not a secret; (c) whether the
task-ledger and reputation series are persisted for sparklines in this branch — default *no*: the
PRD lists no sparkline panel, so `SeatCache` records `cost_output_tokens_history` and
`accepted_history` for a later panel and nothing reads them yet (this is the one place the plan
builds ahead; drop it if unwanted).

---

## 1. Frozen data contract (WP0)

`data/seat_models.py`: `SEAT_KEYS`, `SEAT_ROW_KEYS`, `SEAT_WIDGET_SIGNATURES`, `SEAT_BLOCK_SOURCES`,
`SEAT_SCHEMA_VERSION = 1`. Widgets receive `str` / `int` / `float` / `bool` / `dict` / `list[dict]`.
A failed read is `None`; a not-ok source is `None` for its block (R3); a representable zero is `0`.

### 1.1 Scalar keys

| key | type | from |
|---|---|---|
| `seat_status_state` | `str` | `"ok" \| "stale" \| "malformed" \| "absent" \| "unconfigured"` — the reader's own verdict, never `None` |
| `seat_status_age_s` | `float \| None` | `now - generatedAtUtc` |
| `seat_generated_hhmm` | `str \| None` | the `as of` marker every panel shows |
| `seat_token_id`, `seat_agent_id` | `int \| None` | `seat.tokenId`, `seat.agentId` |
| `seat_device_key` | `str \| None` | `seat.deviceKey` (a public id; the writer asserts the private key is absent — WP1 asserts it again on read) |
| `seat_eligibility` | `str \| None` | third-party text |
| `seat_capacity` | `str \| None` | as emitted |
| `seat_offers` | `list[str]` | `[]` when unknown **and** the block is ok; `None` never (a list key) — availability comes from `seat_status_state` + the block flag below |
| `seat_server` | `str \| None` | |
| `seat_daemon_state` | `str \| None` | `alive \| disconnected \| unknown` |
| `seat_daemon_uptime`, `seat_daemon_work` | `str \| None` | |
| `seat_daemon_working` | `bool \| None` | |
| `seat_daemon_submitted` | `int \| None` | |
| `seat_heartbeat_age_s` | `int \| None` | |
| `seat_build_mismatch` | `bool \| None` | |
| `seat_container_running` | `bool \| None` | |
| `seat_container_status`, `seat_container_image`, `seat_container_restart_policy` | `str \| None` | |
| `seat_container_restarts` | `int \| None` | |
| `seat_container_memory`, `seat_container_memory_pct`, `seat_container_cpu_pct`, `seat_container_pids` | `str \| None` | as emitted (strings) |
| `seat_fleet_online`, `seat_fleet_enrolled`, `seat_fleet_working`, `seat_fleet_accepted_day`, `seat_fleet_queued` | `int \| None` | |
| `seat_fleet_breaker` | `str \| None` | |
| `seat_control_plane_version` | `str \| None` | |
| `seat_current` | `dict \| None` | `{task_id, kind, phase, started_ts, elapsed_s, artifact, max_turns, message}`; `None` = idle **or** unknown — disambiguated by `seat_block_ok["tasks"]` |
| `seat_reputation` | `dict \| None` | `{accepted, rejected, tags: list[str], from_block, to_block}` |
| `seat_cost` | `dict \| None` | `{runs, turns, input_tokens, output_tokens, cache_write, cache_read, model}` |
| `seat_block_ok` | `dict` | `{block: bool \| None}` for the eight sources; `None` when the file itself could not be read |
| `seat_hero_state` | `str \| None` | `"alive" \| "down" \| "stale"`, computed in analytics (R4) |

### 1.2 Row keys

| key | fields |
|---|---|
| `seat_task_rows` | `task_id, kind, started_ts, seconds, phase, submission_id, answer` |
| `seat_feedback_rows` | `block, outcome, tag1, tag2, client, tx_hash` (newest first as emitted) |

### 1.3 `SEAT_WIDGET_SIGNATURES`

```
SeatHero:        seat_hero_state, seat_daemon_state, seat_daemon_uptime, seat_daemon_work, seat_eligibility,
                 seat_token_id, seat_agent_id, seat_status_age_s, seat_generated_hhmm
SeatCurrentWork: seat_current, seat_task_rows, seat_block_ok, seat_generated_hhmm
SeatTaskLedger:  seat_task_rows, seat_block_ok, seat_generated_hhmm
SeatReputation:  seat_reputation, seat_feedback_rows, seat_block_ok, seat_generated_hhmm
SeatCost:        seat_cost, seat_block_ok, seat_generated_hhmm
SeatMachine:     seat_container_running, seat_container_status, seat_container_image,
                 seat_container_restart_policy, seat_container_restarts, seat_container_memory,
                 seat_container_memory_pct, seat_container_cpu_pct, seat_container_pids,
                 seat_build_mismatch, seat_fleet_online, seat_fleet_enrolled, seat_fleet_working,
                 seat_fleet_accepted_day, seat_fleet_queued, seat_fleet_breaker,
                 seat_control_plane_version, seat_block_ok, seat_generated_hhmm
```
Plus the status-bar keys every screen serves (`last_updated_seconds_ago`, `error_count`,
`poll_interval`). `tests/screens/test_dashboard_screen.py`'s `PANELS` walk binds every row to a
named `update_data` parameter for free once the screen inherits `DashboardScreen`.

### 1.4 Module boundaries

- `data/seat_client.py` — `SeatStatusSource` (protocol: `read() -> dict`, raises `SeatReadError`
  with a `reason`), `StatusFileSource(path)` (mode B). Path resolved **at construction**:
  explicit `status_path=` wins, else `MAXPANE_SEAT_STATUS`, else `""` = unconfigured. Reads the
  file, rejects > 1 MB, non-JSON, non-dict, wrong `schemaVersion`; asserts no key named like a
  private key (`privateKey`, `mnemonic`, `secret`) — a file that carries one is **refused**, not
  displayed. No network, no `docker`, no subprocess (a test greps the module for `subprocess`,
  `docker`, `httpx`).
- `analytics/seat_signals.py` — pure: `status_state(doc, now_ts)`, `hero_state(...)`,
  `block_ok(doc)`, `duration_rollup(tasks)`, `accepted_rate(rep)`, `token_totals(cost)`. Clock
  injected everywhere.
- `data/seat_cache.py` — `SeatCache(SeriesCache)`, `SERIES = (SeriesSpec("cost_output_tokens_history"),
  SeriesSpec("accepted_history"))`, file `~/.maxpane/seat_cache.json`. **No cache tier for the
  file itself** (PRD §5 is right).
- `data/seat_manager.py` — `SeatManager(*, client=None, cache=None, cache_path=None, status_path=None)`,
  `fetch_and_compute() -> dict` of exactly `SEAT_KEYS` under every failure; `_error_count`.
- `widgets/seat/` — `_chain.py` (`EXPLORER = ETHEREUM`, `#:` naming the writer's chain read and
  `identity.chainId` 1), `hero.py` (`HeroRow`/`HeroBoxBase`), `current_work.py` (`PanelBase`),
  `task_ledger.py` (`TableLeaderboard`), `reputation.py` (`TableLeaderboard` + `HEADER` counts),
  `cost.py` (`SignalsPanelBase`), `machine.py` (`SignalsPanelBase`, two groups with a separator).
- `screens/seat.py` — `DashboardScreen`, `GAME_NAME = "SEAT"`, `PANELS`, `compose`, no `__init__`.

---

## 2. Panels and their degraded states

| panel | live | block not ok | file stale | file absent / unconfigured |
|---|---|---|---|---|
| HERO | green `alive 2h53m · idle · eligible · IDMD #420 · agent 50939` | `unavailable` per box | **amber**, `as of HH:MM · 23 min old` | one red box: `no seat status — set MAXPANE_SEAT_STATUS` |
| CURRENT WORK | task line + the agent's own `message` (escaped, clipped) | `unavailable` | last-good behind marker | `unavailable` |
| TASK LEDGER | rows, footer `recent window · n tasks` | `unavailable` row | rows behind marker | `unavailable` |
| REPUTATION | `accepted 27 · rejected 0 · blocks 26013352–26020322`, rows with `tx` via `hash_text(explorer=EXPLORER)` and `client` via `address_text` | `unavailable` (the chain block fails often — this is the common case) | behind marker | `unavailable` |
| COST | tokens grouped, `model` | `unavailable` | behind marker | `unavailable` |
| MACHINE | container group · separator · fleet group | per-group `unavailable` (container and stats are separate sources) | behind marker | `unavailable` |

`current == null` with `tasks` ok is **idle**, rendered as `idle · last: <tasks[0]> at HH:MM`; with
`tasks` not ok it is `unavailable`. Submitted and accepted are never on the same line.

---

## 3. Work packages

Same discipline as every Tier 2 here: one implementer per package, one review per diff (reviewer
contract, mid-tier), fix rounds ≤ 2, whole-branch review on the most capable model, one fix wave,
one scoped re-review, full suite once by the controller. Ownership follows symbols.

### WP0 — contract freeze + schema doc + fixtures · Backend Architect · files: **new** `data/seat_models.py`, `docs/seat_status_schema_v1.md`, `docs/seat_game_mechanics.md`, `tests/fixtures/seat/*`, `tests/data/test_seat_models.py`
Schema doc written **from the emitter** (R1), field by field with type, nullability and feeding
source. Fixtures: `status_healthy.json` (the live file, copied; assert no private key),
`status_idle.json` (`current: null`), `status_chain_down.json` (`sources.chain.ok: false`,
`reputation: null`), `status_chain_down_with_values.json` (not-ok **with** values left in — the
R3 case), `status_down.json` (`daemon.state: "disconnected"`, `container.running: false`),
`status_malformed.json` (truncated), `status_wrong_schema.json` (`schemaVersion: 2`),
`status_with_secret.json` (a `privateKey` key — must be refused). Test: every fixture parses to the
documented shape or is named in the refusal table; `SEAT_KEYS` has no duplicates; every signature
key is in `SEAT_KEYS`.

### WP1 — client · Backend Architect · files: **new** `data/seat_client.py`, `tests/data/test_seat_client.py`
As §1.4. Tests on `tmp_path` copies of the fixtures, never the real file (`HOME` isolated; the
env var read after import — `test_manager_seams` shape). Refusal cases raise `SeatReadError` with
the documented reason. Zero-network is structural (no `httpx` import) and tested by grep.

### WP2 — the pure layer · AI Engineer (strict TDD) · files: **new** `analytics/seat_signals.py`, `tests/analytics/test_seat_signals.py`
`SEAT_STALE_AFTER_S` with its `#:` block (R4). Every function takes its clock. Tests pin the
precedence table (down beats stale beats alive), the boundary (age == threshold), `None` under two
samples for the duration rollup, and purity (AST walk, no `data`/`textual`/`httpx`).

### WP3 — manager + cache · Backend Architect · files: **new** `data/seat_manager.py`, `data/seat_cache.py`, `tests/data/test_seat_manager.py`, `tests/data/test_seat_cache.py`, `tests/data/test_manager_seams.py` (one added test)
`fetch_and_compute` returns exactly `SEAT_KEYS` for every fixture and for an absent file;
`SEAT_BLOCK_SOURCES` applied as one function; `record()` drops `None`. Mutation: serve the values
from a not-ok block → the R3 test reddens; return `0` for a failed count → the None test reddens.

### WP4 — widgets · Frontend Developer · files: **new** `widgets/seat/*`, `tests/widgets/test_seat_widgets.py`, `tests/widgets/test_title_blank_row.py` (add the package), `tests/widgets/test_panels.py` (`MIGRATED_PACKAGES["seat"] = 6`)
Six widgets on the bases; every third-party string (`message`, `answer`, `eligibility`, `tags`,
`image`, `model`) through `safe_markup`/`sanitize_cell`; `tx` and `client` through
`widgets/address.py` with `EXPLORER`. Composited tests per panel per degraded column of §2; a `[/x]`
in `answer` renders literally; no `$` on COST (R5).

### WP5 — screen, layout, sweep case · Senior Developer · files: **new** `screens/seat.py`, `tests/screens/test_seat_screen.py`, `tests/screens/test_seat_layout.py`, `tests/address_sweep/builders.py` (one `SweepCase`), `themes/minimal.tcss` (seat geometry block)
`DashboardScreen` subclass with `PANELS`; hero row over a 2 + 2 + 1 body (CURRENT WORK beside
MACHINE, TASK LEDGER beside REPUTATION, COST across — starting shape, the sweep decides);
`SEAT_FULL_LAYOUT_{COLUMNS,ROWS}` swept in situ over the healthy fixture and a worst case (27
feedback rows, 9 tasks, a 400-char `message`), straddling the neighbouring pins in the SKILL
table; `#:` blocks written from the measurement. `SweepCase(name="seat", explorer=ETHEREUM,
seeded=(one client address, one tx hash))`.

### WP6 — registration (shared-file owner, last) · Senior Developer · files: `app.py`, `__main__.py`, `screens/game_select.py`, `README.md`, `.claude/rules/dashboard-registry.md`, `.claude/skills/terminal-layout/SKILL.md` (pin row), `tests/test_app_startup.py` (`ALL_GAMES`, `MANAGER_ATTRS`), `tests/test_surf_registration.py`, `tests/test_game_select_quit.py`, `tests/test_curator_registration.py` (the other three `MANAGER_ATTRS` copies), **new** `tests/test_seat_registration.py`
In the registry's order: `app.py` (`_seat_manager` in `__init__`, `_prefetch_manager`, `_GAME_CYCLE`,
the `elif`) → `__main__.py` choices → `GAMES` row `("9", "seat", "SEAT", "Your IdentityMD worker:
liveness, work, reputation, cost")` (contiguity test stays green because 9 follows 8) → README
table + usage line → the four `MANAGER_ATTRS` copies and `ALL_GAMES`
(`test_every_copy_of_manager_attrs_names_every_manager_the_app_builds` is the proof). No theme is
required (ten palettes, one stylesheet). `test_seat_registration.py` derives its expectations from
`GAMES`, the curator file's shape.

### WP7 — mode A reader · **gated** · Backend Architect · files: `data/seat_client.py` (a second `SeatStatusSource`), `tests/fixtures/seat/docker/*`, `docs/seat_install.md`
Starts only after the owner has run the measurement script (`scripts/probe_seat_host.py`, written
in WP1: prints, as the dashboard's uid, whether each of the four mode-A paths is readable, the
first and last line of the container log, and the log-rotation settings) **on the VPS** and
committed its output as the fixtures. The reader then folds Docker's files into the same schema-v1
dict, so nothing downstream changes. The permission decision goes in `seat_install.md`, written
by the owner's choice, never "run as root because it worked".

### WP8 — whole-branch review · fix wave · scoped re-review · full suite once · controller

**Sequence:** WP0 → {WP1, WP2} → WP3 → WP4 → WP5 → WP6 → WP8. WP7 whenever its gate opens, as its
own Tier 1 follow-on if after merge. WP1 and WP2 own disjoint files.

---

## 4. Test plan

- **Data:** models (contract), client (every fixture, refusal table, env at construction, no
  subprocess/network by grep), cache (`SeriesCache` fixture round-trip pattern), manager (exact
  keys under every fixture; R3 mutation; seams test).
- **Analytics:** precedence, boundary, purity.
- **Widgets:** six files' worth of composited cases in one file, every §2 cell; escape cases; no `$`.
- **Screens:** `test_seat_screen.py` (PANELS walk is inherited), `test_seat_layout.py` (pins,
  whole-ness), address sweep at 170 and at the pin, `test_dashboard_screen.py` and
  `test_refresh_guard.py` collect the new screen automatically.
- **Registration:** the four copies, `ALL_GAMES`, contiguity, `--game seat`, prefetch identity.
- **Guard:** `-m guard tests` in every named set.
- Full suite once, by the controller, before merge.

## 5. Risks

- **R-A The writer's schema drifts.** It is another repo's code. `SEAT_SCHEMA_VERSION` refuses a
  different version (degrade: `seat_status_state = "malformed"` with the version in the reason);
  a field that goes missing inside v1 is `None`, never a crash — WP1 tests a file with every
  optional field removed.
- **R-B A calm panel over a dead daemon.** The R4 precedence is the mitigation; the test that
  serves `alive` in a 30-minute-old file and asserts amber is the one that must never be weakened.
- **R-C The real file on the developer machine.** Every test uses `tmp_path`; `MAXPANE_SEAT_STATUS`
  is deleted from the environment in `tests/conftest.py` for the whole run (one line, WP1).
- **R-D `client` addresses and `tx` hashes on REPUTATION.** 27 rows today; ROW_CAP 10 and the
  sweep at the pin keep the table whole; the icon budget is measured, not assumed.
- **R-E Mode A never gets measured.** Then WP7 never starts and the dashboard remains mode-B only,
  which is a complete, honest product on macOS and on any host with the writer installed. The
  install doc says so.

## 6. What can start now

WP0, on branch `feature/seat-dashboard` off `main`, **after** `feature/surf-swarm-v2` has merged.
