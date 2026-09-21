# HANDOVER (Codex) — surf AGENT body: seat details instead of ROSTER, BY NODE instead of FEEDBACK

**Status:** design APPROVED by the owner 2026-09-21 ("yes go with the proposed changes"); implementation
handed to Codex. Written by Claude from a live reality check of seat #420 (`GET api.imd.fun/seats/420`,
2026-09-21 20:12 UTC) against the owner's screenshot.
**Tier:** 2 (CLAUDE.md triage): retires a widget and two contract keys, adds a widget and two contract
keys, changes `data/surf_models.py`, > 6 files. The spec is §1–§5 of this file; the plan is §6.
**Authority:** the base repo's `CLAUDE.md` (hard constraints, conventions, tiers) > this file > your own
judgement. Where this file contradicts CLAUDE.md, CLAUDE.md wins — record it as a defect of this file in
your hand-back, do not silently resolve it.

---

## 0. Setup — do this first, exactly

The work builds on commits that exist **only** in the owner's local checkout `/Library/Vibes/autopull`
(16 commits over `origin/main 339ae9a`, unpushed: the seat prompt, the `/seats` programme, and the hero
title fix `c529ee5`). This clone is on `fix/theme-token-markup` with 46 unrelated unpushed commits —
**leave that branch untouched.**

```bash
cd /Users/banse/codex/maxpane
git status --short                     # must show only the untracked .codex/ and this file
git remote add autopull /Library/Vibes/autopull   # read-only use: fetch only, NEVER push to it
git fetch autopull main
git switch -c feature/surf-agent-seat-details autopull/main
git log --oneline -1                   # expect c529ee5 fix(surf): AGENT hero titles share one row …

# Layout pins are measured on composited output and depend on Textual. The owner's tree runs
# Python 3.11 + textual 8.1.1; this clone's .venv is 3.13 + 8.2.8. Measure and test on the owner's:
python3.11 -m venv .venv311 && .venv311/bin/pip install -e . 'textual==8.1.1' pytest pytest-asyncio pytest-xdist
.venv311/bin/python -c "import maxpane_dashboard,textual;print(maxpane_dashboard.__file__, textual.__version__)"
# must print /Users/banse/codex/maxpane/maxpane_dashboard/__init__.py 8.1.1
```

Use `.venv311/bin/python -m pytest` for every run below. Commit this handover file as the first commit
on the branch (`docs(surf): seat-details handover`), so the spec travels with the code.

**Never:** push anywhere, merge, tag, bump the version, touch `/Library/Vibes/autopull`, or touch the
untracked owner files if they appear (`docs/netnet_*`, `docs/seat_*`, `docs/standardreserve_*`,
`docs/surf_swarm_v2_*`, `tests/fixtures/surf/pool4/oracle_25955365.json`). Commit with pathspecs only.
One writer in the tree at a time — if you parallelise, parallelise reading/planning, not edits to the
same tree.

---

## 1. Why — what the owner saw, and what is true

Every number on the owner's screen for seat #420 matched `/seats/420` (ACCEPTED `12 of 164`,
REVIEWED `161 / 90 pending` = 5 submitted + 85 queued, SCORE `1.00 (161 scored)`, COLLAB `48`,
by role `implement 160 · review 1`, sent 71). The body is *correct but not useful*:

1. **ROSTER contradicts the lifetime record (F29).** It is folded from `/jobs`, the newest 100 jobs
   (~3 h). Row #420 said `2 nodes · 2 jobs · acc 1`, beside a hero saying 12 accepted. One seat of many
   rows is not what the reader came for; the selected seat's details are.
2. **SCORE and FEEDBACK carry no signal.** `reviews[].verdict` is `accepted` and `value` is `1` on
   **every** review ever read (161/161 for #420 today; 202+72+13+9 across the committed fixtures).
   "Accepted" there means *passed review*, not *won the job*. FEEDBACK is a list of 161 identical
   `1`s, 85 of them queued with no tx.
3. **The number that does vary is the win rate:** `accepted / attempts` = 12 / 164 = **7.3 %**.
   Per node: `oracle_assess` 159 reviewed, 10 won (6.3 %); `adversarial_review` 1/1;
   `build_contract_project` 1/1. That is what FEEDBACK's space should say.
4. **STATUS "last 18:11" is not the seat's activity.** It is the newest `reviews[].sentAt` — when the
   *oracle's feedback transaction* went onchain as the queue drained. The seat last **won** at
   06:10 local (`work[0].acceptedAt` 04:10Z). `/seats` serves no "last attempt" time.
5. **RECORD's `when` is `HH:MM` only**, and #420's twelve rows run 09-20 19:48 → 09-21 06:10 across
   midnight with no date.
6. **Unused data `/seats` already serves:** `agentId`, `daemonVersion` (null on seat #0 — a real
   "not reported"), `devices`, `collaborators[] {tokenId, agentId, sharedJobs}`,
   `work[].launch` (e.g. `"evm_project"`, 9 rows on seat #0; null elsewhere = real "none"),
   `work[].submissionHash`.

(The hero title row was item 7; it is already fixed in `c529ee5` — do not redo it.)

---

## 2. Target design (approved)

```
[SEAT IDMD #420][ACCEPTED 12 of 164][WIN RATE 7.3 %][REVIEWED 161 / 90 pending][COLLAB 48][STATUS ● online / won 09-21 06:10]
┌ SEAT ───────────────────────────────┐┌ BY NODE ─────────────────────────────────────────────────┐
│ IDMD #420 · agent 50939             ││ node                    roles    reviewed  won  win  chain│
│ owner 0xe5b1…2f2a ⧉                 ││ oracle_assess           implement     159   10  6.3%  69  │
│ paired 09-20 07:34 · online ●       ││ adversarial_review      review          1    1  100%   1  │
│ runtime claude 2.1.278 · 1 device   ││ build_contract_project  implement       1    1  100%   1  │
│ daemon 0.1.0+5e34612c               ││                                                          │
│ attempts 164 · won 12 (7.3 %)       ││ TEAMMATES  #1242 ×9 · #617 ×7 · #1299 ×7 · #1310 ×7 · +44 │
│ feedback 71 sent · 5 submitted      ││                                                          │
│          85 queued                  ││                                                          │
│ score 1.00 on 161 scored            ││                                                          │
└─────────────────────────────────────┘└──────────────────────────────────────────────────────────┘
┌ RECORD · every won job, lifetime ─────────────────────────────────────────────────────────────────┐
│ when         job       node                role    state      launch        sub       objective…  │
│ 09-21 06:10  88d94855  adversarial_review  review  completed  —             aa9380cc  Build Swap… │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Column names and exact words above are the intent; widths and which columns hide first are yours to
measure (§5). Rules for every panel:

- **Hero:** SEAT, ACCEPTED, REVIEWED, COLLAB unchanged. **SCORE → WIN RATE**: `7.3 %` over
  `of attempts` (the counts already sit in ACCEPTED; no second counter here). STATUS: `online ●` /
  `offline ○`, then `won MM-DD HH:MM` (newest `work[].acceptedAt`), then the tier's `as of HH:MM`
  as today. **Never** the word "last" for a `sentAt` stamp. Titles stay on one row (the `c529ee5`
  regression test must stay green).
- **SEAT** (the existing `SurfSwarmSeatVerdicts` / `swarm_seat_verdicts.py`, retitled `SEAT`; keep the
  class and module name — renaming ripples through a dozen tests for no reader benefit; say so in its
  docstring): identity, owner (address cell, copy icon + package `EXPLORER`, as today), paired, online,
  runtime, devices, daemon, attempts/won/win rate, feedback by status, score line, by role (keep
  `_fit_roles` "+N more"). The score line stays — it is a true number — but moves out of the hero.
- **BY NODE** (new widget `SurfSwarmSeatNodes`, `widgets/surf/swarm_seat_nodes.py`, subclass of
  `widgets/panels.py` per rules/widgets.md — reuse `_swarm_table.SwarmTableBase` if it fits, like
  CAPABILITY does): one row per `nodeKey` seen in `reviews[]` or `work[]`; columns node, roles,
  reviewed, won, win (won/reviewed), chain (reviews with a tx: `sent` + `submitted`). Under it one
  TEAMMATES line: collaborators by `sharedJobs` desc, token asc, as `#token ×shared`, as many as fit,
  then `+N` — tokens are integers, not addresses: no copy icon. Empty collaborators list = `none yet`
  (a real zero); `None` = unavailable.
- **RECORD:** `when` becomes `MM-DD HH:MM`; add `launch` (`—` for null = real none, sanitised string
  otherwise) and `sub` (first 8 hex of `submissionHash`, plain text — it is an off-chain hash, **no
  explorer link**, never through `hash_text`/`for_chain_id`). Objective keeps the remaining width and
  its `‹` behaviour.
- **Retired:** `SurfSwarmRoster` (+ `swarm_roster.py`), `SurfSwarmSeatFeedback`
  (+ `swarm_seat_feedback.py`), their tests, Enter-on-roster selection and its screen handler. The
  seat is chosen by `i` (saved seat) or defaults to the most active seat of the job window, as today.

Denominators — state them in docstrings, never mix them:
- hero / SEAT win rate = `accepted / attempts` (lifetime counters served by `/seats`);
- BY NODE win = `won / reviewed` for that node (`attempts` is not served per node). The two can differ
  in the first decimal (12/164 = 7.3 % vs 12/161 = 7.5 %) — that is why the headers differ
  ("of attempts" vs "reviewed").

---

## 3. Data contract (WP1 freezes it in `data/surf_models.py` before any fold or widget)

`SWARM_SEAT_SUMMARY_FIELDS` — **add** `agent_id` (str, from `/seats agentId`; decimal string as
served), `daemon` (str; `""` when served null = "not reported", `None` when absent/wrong type),
`devices` (int), `win_rate` (float in [0,1] or `None`; `None` when `attempts` or `accepted` is `None`
**or `attempts == 0`** — the widget then says `no attempts` when attempts is `0` and `unavailable` when
`None`), `last_won_ts` (newest `work[].acceptedAt`), `last_sent_ts` (newest `reviews[].sentAt`).
**Remove** `last_active_ts` (it conflated the two). Every field `None` when not carried; a real zero
stays `0`.

New keys:
- `swarm_seat_node_rows` — `list[dict]`, `SURF_ROW_KEYS`: `node_key, roles (list[str]), reviewed,
  won, onchain, queued`; sorted `reviewed` desc, `won` desc, `node_key` asc. A node only in `work[]`
  has `reviewed 0`.
- `swarm_seat_teammates` — `list[dict] | None`, `SURF_ROW_KEYS`: `token_id (int), agent_id (str|None),
  shared_jobs (int)`; sorted as §2. `None` when `collaborators` is not a list; malformed members are
  dropped (strict decimal-string/int parse — reuse `parse_seat_token` / `_seat_id`, do not re-declare).

Changed: `swarm_seat_work_rows` gains `launch`, `submission_hash` (both `None` when absent;
`submission_hash` accepted only as 64 hex chars, else `None`).
`swarm_seat_selected.agent_id` comes from `/seats` when the roster row lacks it (the saved-seat-off-
the-roster case today shows no agent id).

Retired: `swarm_seat_feedback_rows`, `swarm_roster_window` (+ `SWARM_ROSTER_WINDOW_FIELDS`),
`swarm_seat_rows` as a *contract key* (the manager still folds the roster internally — `choose_seat`'s
`most_active` default needs it — it just is not emitted), `selected_by == "cursor"` (and
`choose_seat`'s `cursor_token` parameter, `SurfManager.select_seat`). `set_seat` stays.

`SWARM_WIDGET_SIGNATURES`: drop `SurfSwarmRoster`, `SurfSwarmSeatFeedback`; add
`"SurfSwarmSeatNodes": ("swarm_seat_node_rows", "swarm_seat_teammates", "swarm_seat_state",
"swarm_seat_as_of_hhmm")`; `SurfSwarmSeatVerdicts` gains `swarm_seat_selected` (closes F30's panel half:
"never paired" can now name `#N`).

The persisted seat slot (`SLOT_SWARM_SEAT`, `coerce_seat_slot`) already stores the whole `/seats`
payload — no cache change, no new fetch, no new endpoint. Still one `/seats` read per cycle.

---

## 4. Must honour (CLAUDE.md — the reviewer will check each)

Read-only GET, keyless, **no test touches the network** (the committed fixtures under
`tests/fixtures/surf/swarm/seats/` cover every case: #420, #0 with `launch` rows and null `daemonVersion`,
#1649, #516, the 404/400 bodies — do not capture new ones; if you believe you must, stop and ask).
A failed read is `None`, never `0`; a real negative (`no attempts`, `none yet`, `—` launch, `not
reported` daemon) is distinct from `unavailable`. Every third-party string (node keys, roles, launch,
objective, daemon, runtime) through `markup_safety`; the owner address through `widgets/address.py`
+ the package `EXPLORER`; tokens are not addresses. Inject the clock. Widgets render only (no `data/`
import). Reuse `widgets/fmt.py`, `rowfit.py`, `surf/_fmt.py` (`hhmm` etc.) before writing a formatter;
a date+time formatter two widgets need is hoisted into `surf/_fmt.py` once. Tests assert composited
output (`render_strips()`), prove they bite (§6), and never wait on the wall clock.

---

## 5. Layout (read `.claude/skills/terminal-layout/SKILL.md` before WP4)

The AGENT pins live in `screens/surf.py`: `SURF_AGENT_FULL_LAYOUT_COLUMNS` (134),
`SURF_AGENT_FULL_LAYOUT_ROWS` (40), `RECORD_NEVER_CLEARS_BELOW` (268), each with a `#:` block that is
the **only** place its numbers may live; CSS is mirrored in `screens/surf.py DEFAULT_CSS` and
`themes/minimal.tcss` (a guard binds them). Re-sweep all three in situ exactly as the current blocks
describe (every width 60–225 at height 80; every height 20–61 at width 150 and at the column pin;
capture = seat #0/#420 fixtures, worst case = the stretched payload in
`tests/screens/test_surf_swarm_layout.py`, extended with: 30 nodes, 999 teammates, 64-char node keys,
`launch` strings, five-digit per-node counters). Rewrite the `#:` blocks with what binds now (ROSTER no
longer does). Dropping FEEDBACK's row should **lower** the row pin — report the new number; the
owner's terminals are 35 and 31 rows (F16), so say whether it now fits either. Do not hand-pick a
number; the layout test's thresholds (`_A_THRESHOLDS`) move with the blocks.

---

## 6. Work packages (serial; each ends green on its named set and in its own commit)

Every WP: TDD — failing test first, smallest change, refactor green. **Mutation proof** for each
behaviour marked ⚑: break the production line, run the named test, confirm *that* test reddens for
*that* reason, restore by inverse edit, record it in the commit message. Named set for every WP =
the files listed + `-m guard` (`.venv311/bin/python -m pytest -m guard tests -q`, ~2 min).

**WP1 — contract.** `data/surf_models.py` per §3; update `tests/data/test_surf_swarm_models.py`,
`tests/data/test_surf_models.py`, `tests/widgets/test_surf_widget_contract.py`,
`tests/test_surf_registration.py`. Expect transitional reds in the manager/widget/screen tests — list
them in the commit message; WP2–WP4 turn them green. (Precedent: the `/seats` WP0 did the same.)

**WP2 — pure fold.** `data/surf_swarm.py`: extend `seat_summary_from_seat` (⚑ win_rate `None` at
attempts 0 and at a missing counter; ⚑ `last_won_ts` reads only `work[]`, `last_sent_ts` only
`reviews[]`), add `seat_node_rows` (⚑ a node only in `work[]`; ⚑ `onchain` counts `sent`+`submitted`
not `queued`), `seat_teammates` (⚑ string and int tokenIds, bool/negative/non-decimal dropped),
extend `seat_work_rows` (⚑ submission hash validated), delete `seat_review_rows` and `roster_window`,
drop `choose_seat`'s cursor path. Tests: `tests/data/test_surf_swarm_seats.py`,
`tests/data/test_surf_swarm_fixtures.py`, `tests/data/test_surf_swarm_v2.py`. Fixture truths to pin
(read them from the fixtures in the test, do not hardcode derived numbers you did not compute there):
#420 fixture → 74 attempts, 12 accepted, win rate 12/74; #0 → 9 work rows with `launch`,
`daemon == ""`.

**WP3 — manager.** `data/surf_manager.py`: emit the new keys, stop emitting the retired ones, remove
`select_seat` and the cursor bookkeeping, keep the internal roster fold feeding `choose_seat`, fill
`swarm_seat_selected.agent_id` from the seat read. `data/surf_cache.py` only if a comment names a
retired key. Tests: `tests/data/test_surf_manager_swarm.py` (⚑ the key set emitted equals the contract
exactly; ⚑ seat switch still never shows seat A's node rows/teammates under seat B).

**WP4 — widgets + screen + layout.** New `widgets/surf/swarm_seat_nodes.py` (+ export in
`widgets/surf/__init__.py`); `swarm_seat_verdicts.py` → SEAT content; `swarm_agent_hero.py` WIN RATE /
STATUS `won`; `swarm_seat_record.py` columns; delete `swarm_roster.py`, `swarm_seat_feedback.py` and
their tests; `screens/surf.py` compose (`#surf-agent-top`: SEAT | BY NODE), both CSS copies, PANELS
dispatch, remove the roster `DataTable` selection handler, the `MODE_AGENT` docstring; the three pins
re-swept (§5). Tests: `tests/widgets/test_surf_swarm_agent_hero.py` (⚑ "won", never "last", for the
STATUS stamp), `tests/widgets/test_surf_swarm_seat_verdicts.py`, `tests/widgets/test_surf_swarm_seat_state.py`,
new `tests/widgets/test_surf_swarm_seat_nodes.py` (⚑ `none yet` vs `unavailable`; ⚑ `+N` teammates
marker when cut; ⚑ a markup-bearing node key renders literally), `tests/widgets/test_surf_swarm_seat_record.py`
(⚑ the date survives midnight: two rows on different days show different `MM-DD`),
`tests/screens/test_surf_swarm_screen.py`, `tests/screens/test_surf_swarm_layout.py`,
`tests/screens/test_surf_screen.py`, `tests/screens/test_address_icons_everywhere.py` (the owner cell
must still carry its icon; teammates must not), `tests/test_surf_registration.py`.

**WP5 — docs.** README AGENT paragraph (l.160–170: no ROSTER, no Enter-to-pick, `i` picks; win rate;
BY NODE) (README has no Enter-on-roster key row today — check anyway); `.claude/rules/surf.md` AGENT section (l.148–185);
`docs/surf_swarm_followups.md`: close F29 (removed), F30 (panel names `#N`), F28/F27 if the SEAT
rewrite resolves them (say how), file every residual as the next F-number; `docs/decisions.md` one
entry (2026-09-2x: ROSTER and FEEDBACK retired, why — §1 items 1–4); `docs/imd_swarm_api.md`: note
`collaborators`, `launch`, `submissionHash`, `daemonVersion` null. Run the doc-pinning tests:
`rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/` and every file it names.

---

## 7. Done means — and the hand-back

1. Every WP's named set green on `.venv311`, each WP one commit (pathspec), ⚑ proofs in the messages.
2. **Do not run the full suite** (CLAUDE.md: the controller runs it once, before merge). Instead run the
   middle tier once at the end and report it:
   `HOME=$(mktemp -d) .venv311/bin/python -m pytest -n 4 --dist loadfile -m 'not screen' sybilkit/sybilkit_tests tests`
   plus `.venv311/bin/python -m pytest tests/screens/test_surf_swarm_screen.py tests/screens/test_surf_swarm_layout.py tests/screens/test_surf_screen.py tests/screens/test_address_icons_everywhere.py -q`.
3. Render it once for real and look: `.venv311/bin/python -m maxpane_dashboard --game surf`, `a`, at
   134×(new row pin) and at the owner's 119 and 138 columns — the network read is the app's, not a
   test's. Say in the hand-back what you saw for seat #420 (it will show today's numbers, not the
   fixture's).
4. Hand-back note appended to this file as §8: branch name, commit list, the new pin numbers and what
   binds each, ⚑ proofs, every deviation from this file and why, residuals filed. **Stop there.**
   Claude runs the final whole-branch review against the reviewer contract in CLAUDE.md, one fix wave,
   the full suite once; the owner decides merge and push.

Out of scope: any change to the `s` SWARM body, `/jobs` handling, the seat tier's TTL, new endpoints,
F16 as a decision (just report whether the new pin fits), a version bump.

## 8. Implementation hand-back — 2026-09-22

Branch: `feature/surf-agent-seat-details`, based on fetched `autopull/main` at `c529ee5`.
The original `fix/theme-token-markup` branch and `/Library/Vibes/autopull` were left untouched.
No push, merge, tag, version bump or release-validation suite was performed. The full release
suite is intentionally deferred under the repository's remote-push authorization rule.

### Commits and review

- `6ccb643` — handover spec.
- `b3075b9` — WP1 contract.
- `ccf9adc` — WP2 pure fold.
- `c813162` — WP3 manager.
- `8c66bbd` — widgets, screen and measured layout.
- `9c50184` — integration correction for the retired cursor assertion.
- `cc0b8c7` — documentation and residuals.
- `ed426b2` — initial hand-back and verification record.

Agency planning, backend, frontend and documentation agents were used with one repository
writer at a time. The controller reviewed each package diff. WP3 had one important finding:
missing node source lists must remain unavailable; a failing regression preceded the fix.
The final whole-branch review belongs to the receiving controller, as requested in §7.

### Layout and real-app observation

The canonical pin blocks are in `maxpane_dashboard/screens/surf.py`:

- `SURF_AGENT_FULL_LAYOUT_COLUMNS = 131`: the status bar binds. The body clears at 117
  columns on captures and 118 on the stretched payload; RECORD reaches its full tier at 119.
- `SURF_AGENT_FULL_LAYOUT_ROWS = 32`: the top floor is 13 rows (SEAT title, blank and eleven
  details), RECORD's floor is 8; hero/chrome use the remaining rows. Height fell from 40 to 32.
- `RECORD_NEVER_CLEARS_BELOW = 297`: objective clearance on both committed seat captures;
  the 400-character worst objectives still correctly show the widen marker.

Measured every integer width 60–225 at height 80 for #0, #420 and the extended worst payload;
height 20–61 at width 150 and the final column pin; successive objective-clearance widths 225–297.
Boundary tests cover the tier edges, pin−1/pin/pin+1 and clearance−1/clearance.
A 35-row terminal fits. A 31-row terminal still requires scrolling; F16 remains a separate decision.

The actual CLI was launched against its normal read-only network sources in isolated temporary
homes, with saved seat 420, Python 3.11 and Textual 8.1.1. SVGs and inspected PNGs are in
`/tmp/surf-seat-details-live/` (temporary evidence, not committed):

- 134×32: panels fit, four RECORD rows visible, `+150 older`, objective widen marker visible.
- 119×35: all fixed table columns and hero values fit, seven RECORD rows visible. The status bar
  is below its guaranteed width; the objective remains visibly clipped.
- 138×31: taller indicator and body scrollbar visible; RECORD begins below the initial viewport.

At approximately 00:35–00:37 Europe/Berlin on 2026-09-22, seat 420 showed 190 accepted of 201
attempts (94.5%), 351 reviewed, 270 pending, 81 sent, 6 submitted, 264 queued, 76 collaborators,
score 0.99 on 351 and last won 09-21 23:35. Earlier queue counters differed as the queue drained.
No live values were added to test fixtures. The source work order was not strictly chronological;
that pre-existing behavior is F42.

### Verification

All runs used Python 3.11 / Textual 8.1.1. Targeted checks only; no full suite.

| Check | Result |
| --- | --- |
| WP1 contract target | 86 passed; broader named set 267 passed with 3 planned transitional failures |
| WP2 fold and contract | 258 passed |
| WP3 manager | 72 passed |
| WP4 layout | 180 passed |
| WP4 widget/contract/registration | 202 passed |
| WP4 complete named set | 652 passed, 3 obsolete address-anchor failures; corrected anchors passed; restored proof targets and anchors 22 passed |
| WP5 all 50 discovered test files | 4,596 passed; 4 worker reports of the same missing-fixture collection error |
| Final middle tier (run once) | 8,660 passed, 1 expected failure, 7 failures and 6 collection errors; causes and scoped recovery below |
| Scoped manager seams plus local Sybilkit | 459 passed, 1 expected failure |
| Final four screen files | 571 passed in 770.14s |
| Fixture recovery: four previously affected files | 99 passed in 2.92s |
| Guard recovery after authorized fixture copy | 199 passed, 9,099 deselected in 75.09s |

The middle tier's seven failures were six absent-oracle cases and the obsolete cursor assertion.
Its six collection errors were two installed-Sybilkit imports and four worker reports of the
absent oracle. The cursor and Sybilkit issues were resolved with scoped checks. After the user
authorized copying the existing oracle fixture, all four affected test files passed, including
the previously uncollectable market-manager module. The exact `-m guard tests -q` command was
attempted for every package; those initial attempts stopped during collection. Its recovery run
now passes. All identified verification failures have scoped passing results; the original
middle-tier run remains recorded as failed and was not repeated.
Doc discovery also matched nine fixture/helper files that are not executable test files; the
50 `test_*.py` files ran with `--continue-on-collection-errors` and four workers to obtain useful
results beyond the known collection blocker. Final broad commands used isolated temporary homes.
Logs: `/tmp/wp5-docs.log`, `/tmp/wp5-guard.log`, `/tmp/final-middle-tier.log`,
`/tmp/final-scoped-recovery.log`, `/tmp/final-surf-screens.log`.
Fixture recovery logs: `/tmp/seat-details-fixture-recovery.log` and
`/tmp/seat-details-guard-recovery.log`.

Mutation checks deliberately broke production behavior, observed the named regression fail,
and restored by inverse edits. Commit messages contain package evidence:

- WP2: undefined win rates; crossed work/review timestamps; work-only nodes; sent/submitted
  versus queued and missing transaction hashes; strict string/integer teammates; invalid hashes.
- WP3: exact emitted keys; stale nodes and teammates after selection changes; unavailable nodes.
- WP4: STATUS source/label; teammates empty state and omitted count; node sanitizer; RECORD date;
  one-cell changes in both directions for width, height and objective-clearance pins.

### Deviations and remaining work

- WP1's requested transitional reds conflict with “every named set green”; they were recorded
  explicitly and resolved as the dependent packages landed. A temporary roster-window constant
  remained importable until WP2 removed its last fold consumer.
- Repository strip-then-escape sanitization takes precedence over the handover's literal-markup
  wording. A mutation test proves the sanitizer is used.
- The old RECORD clearance constant actually lived in the layout test, despite §5 locating all
  three pins in the screen. It now has one canonical screen block and is imported by the test.
- F30 closes only for SEAT; tokenless unknown-seat footers in RECORD/BY NODE remain F39.
- F27 is resolved by separate feedback lines; F28's single-token cache remains open; F29 closes
  with ROSTER removal. F40 records spec defects, F41 missing work-list conflation, F42 source order.
- `NO_COLOR=1` was inherited from the execution environment. Color-sensitive tests and later live
  renders removed it from child environments; production behavior and color assertions were kept.
- The setup command installed a released Sybilkit package that lacks two modules present in
  this checkout. The middle-tier command exposed those import errors. A scoped rerun with
  `PYTHONPATH=$PWD/sybilkit/src` passed all manager seam and Sybilkit tests (459 passed,
  1 expected failure). The environment now installs local Sybilkit editable
  (`pip install --no-deps -e ./sybilkit`), and its import path was verified inside this checkout.
  The two formerly uncollectable files then passed all 16 tests without a path override.
- The middle-tier command also exposed one omitted test migration: a manager-seam assertion
  still expected `_seat_cursor`. The test-only integration commit now asserts that the retired
  state is absent while preserving saved-seat injection and no-network checks.
- The baseline oracle fixture `tests/fixtures/surf/pool4/oracle_25955365.json` was initially absent.
  After the first hand-back, the user explicitly authorized copying the existing fixture from
  `/Library/Vibes/autopull` for local tests, with the requirement never to commit it. The copy
  matches the source byte-for-byte (SHA-256
  `f44b0f482ce3dc2b18faac09e2f1e5aa15789828dc097491fb28c70b8d608144`); the source is unchanged.
  The fixture remains untracked and was never staged. The four affected test files and guard
  check now pass in isolated temporary homes, resolving this verification blocker. No production
  code changed, and neither the middle tier nor the full release suite was repeated.

Stop here for the receiving controller's whole-branch review and the owner's merge/push decision.
