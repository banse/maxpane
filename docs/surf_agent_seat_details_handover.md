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
