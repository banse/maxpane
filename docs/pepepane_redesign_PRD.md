# PEPEPANE round 9 — redesign PRD

> **Adapted copy (2026-10-03).** Source: `/Library/Vibes/aidude/docs/superpowers/specs/2026-10-03-pepepane-redesign-design.md`.
> The approved spec is reproduced verbatim below. The round-9 brief is the implementation plan.

---

# PEPEPANE redesign — six dashboards behind selectable hero cards — design spec

- **Date:** 2026-10-03. **Status:** design approved by the owner in chat on 2026-10-03; spec reviewed the same day, with R9 decided.
- **Amends:** `2026-09-26-pepepane-design.md` (the "base spec"). Section 14 lists every base-spec rule this document changes. Everything not listed there stays in force.
- **Built by:** Codex in `/Users/banse/codex/maxpane`, branch `pepepane`, starting at `f4de533` (broker `imd-dashd 0.1.4`). Claude writes the briefs and verifies each round. Nothing is pushed or tagged.
- **Rounds:** round 9 builds sections 4 to 9. Round 10 builds section 10. Section 11 is later work.

## Summary for the owner

PEPEPANE today shows six panels at once and needs a 134 × 50 terminal. After this redesign the six hero cards are the navigation: each card stands for one dashboard, the selected card has the green border, and only that dashboard is shown below.

| Key | Card and dashboard | Shows |
|---|---|---|
| `1` | SEAT | MACHINE, COST, OUTPUT TOKENS, LEDGER |
| `2` | LIVE | NOW, JOB (question and result of the current or last job), LOG |
| `3` | CONFIG & SKILLS | every setting with how it changes; every skill, with on/off toggles |
| `4` | RECORDS | the plane's record of this seat's work, as on SURFBOARD's AGENT board |
| `5` | NODES | one row per node type: counts, acceptance rate, paid, launch |
| `6` | CONTROL | today's CONTROL popup as a dashboard, with the gate facts and the audit tail |

Round 9 changes the screen, adds the API reads the new widgets need, and fixes twelve measured defects. It adds no control verb and changes no gate or systemd unit. Round 10 adds the two broker verbs that make capacity and inference tiers editable.

---

## 1. Purpose, scope, success criteria

**Purpose.** One dashboard per question, switched from the hero row, following MaxPane's own rules for bodies, pins and panels. The operator sees more of each topic and needs a smaller terminal.

**In scope, round 9.** The screen model, the six cards, the six dashboards, the new JOB widget, RECORDS, NODES, skill and boot toggles through the broker verbs that exist today, the API reads and the ledger cache those need, and the defects of section 9.

**In scope, round 10.** The broker verbs `capacity-set` and `tier-set`, and the CONFIG rows that use them.

**Out of scope.** A chain join for paid status, any change to SURFBOARD, registering PEPEPANE in the `maxpane` menu, and every item the base spec excludes in its section 11 ("Excluded entirely").

**Success criteria.** Each is checked by a test or a host measurement in the round's verification.

1. Six cards select six bodies by key `1` to `6` and by mouse click. Exactly one card has the green border. PEPEPANE starts on LIVE.
2. Every body has its own measured layout pin. No body needs more than 134 columns or 50 rows.
3. JOB shows the question of a running job within one poll cycle of the standing read that names it. Once the plane serves them, it shows the reply and the verdict of the last job. Each text is fetched once and then read from the ledger.
4. CONFIG lists every worker setting with its value and its change path. SKILLS lists every skill the listing returns. A skill and the boot setting can be toggled there with the same plan, typed confirm, apply and verify as today.
5. RECORDS has the columns, filter, colours and row window of SURFBOARD's RECORD panel, plus a row cursor and `enter`.
6. NODES shows one row per node type with attempts, verdict counts, acceptance rate, paid and launch counts.
7. CONTROL offers every verb of today's popup with unchanged gate, confirm and audit behaviour. No popup remains for control.
8. On seat #3, COST and OUTPUT TOKENS show token figures, the daemon version is shown, MACHINE shows journal facts, and a retried 401 does not raise "auth degraded".
9. Round 9 changes no control verb, no gate rule, no systemd unit file and not the installer. Its broker-side changes are limited to `imd_dashd/summarise_claude.py` (defects D2 and D5), the broker's version identity, and the probe's p09 output (D10). The build regenerates `deploy/vps/MANIFEST.sha256` and `requirements.lock`, as every round does.

---

## 2. Owner decisions (2026-10-03)

| # | Decision | Effect |
|---|---|---|
| R1 | The hero cards match the dashboards and are selectable. Names and order: SEAT, LIVE, CONFIG & SKILLS, RECORDS, NODES, CONTROL. | Today's TODAY, VERDICTS, GATE and UNIT cards are replaced. Their facts move (section 5). |
| R2 | The selected card has the green border. | The border no longer shows health. Health moves to the card label and the title bar (section 5). |
| R3 | Config edits come in two rounds. | Round 9: skill and boot toggles with existing verbs. Round 10: capacity and tier verbs. This promotes `capacity set` and `tier set` under base spec §16 #3. |
| R4 | Question and result text comes from the public API and is cached in the local ledger. | Amends "never render or persist `summary`" for API text. Local transcripts and workspaces stay unread. |
| R5 | Paid status: API now, a chain join later. | Taken before `paidBy` was found (section 3, F6). The API now names the payer, so the paid column ships in round 9 from the API. The chain join stays later work. |
| R6 | The new widget is titled `JOB`. | Section 6.2. |
| R7 | On CONTROL, `r` plans a restart, as in today's popup. On the other five dashboards `r` refreshes. | Section 4.3. |
| R8 | The new API reads are allowed. | Extends base spec §16 #6 (section 8.1). |
| R9 | Round 9 may change one broker-side file, `imd_dashd/summarise_claude.py`. Decided at spec review: "round 9 is ok with broker". | Defect D2 lives there. It runs as `imd-worker` in a transient unit and only reads transcripts. No verb, gate or unit file changes. The broker's version string moves with it, so the hosts load a new broker build at the round-9 install. |

---

## 3. Measured facts this design rests on

All measured on 2026-10-03 unless a date is given. "Clone" is `/Users/banse/codex/maxpane` at `f4de533`.

**F1. The green LIVE border is the health colour, not a selection marker.** `screens/seat.py:192-194` colours only `#seat-hero-live` from the classes `seat-hero-green|amber|red`, which `SeatHero._repaint` sets (`widgets/seat/hero.py:270-272`). No hero box in the codebase is focusable, clickable or selected.

**F2. MaxPane switches bodies by display on one screen.** SURFBOARD composes every body once and sets `.display` per mode (`screens/surf.py`, `_show_mode`). Hidden bodies are still updated on every refresh. The terminal-layout skill requires: "Each swapped body gets its own pin, swept in situ against its own panels" and "A swapped-in body is composed once and hidden, so the first keypress paints a complete frame". `rules/surf.md`: "A mode is a whole second body with its own panels, never two panels sharing one slot."

**F3. The journal carries neither the question nor the result.** The `accepted` line carries the allowed paths, not the objective. `submitted` and `answered` carry no result text (`data/seat_log_grammar.py`). The API carries both: `/jobs/<uuid>.objective` (full text), `/jobs/<uuid>/submissions[].summary` (the agent's reply, verbatim Markdown), and for oracle jobs `/oracle/requests/<id>` (`question`, member `answer`, `agreement`).

**F4. PEPEPANE drops that text today by rule.** `data/seat_api.py:119-130` deletes every `summary` key. `screens/seat_task_detail.py:45` names `objective` and `lastMessage` as never shown. Base spec §6, §8, §13 and §16 #13 state the rule.

**F5. Only skills have a write path.** The daemon has no `imd config` command. Every `config.json` key is read once at daemon start.
- Capacity is the `--concurrency` start flag, which overwrites `maxConcurrency` in `config.json` at every start. Seat #7 sets it in the drop-in `imd-worker.service.d/concurrency.conf`. Seat #3 has no drop-in directory; its main unit's `ExecStart` is `imd start --runtime claude --concurrency 3`. The Mac container has it baked into its command.
- Inference tiers are a hand edit of `config.json`, the file that holds the device private key. A zod-invalid file stops the daemon from starting.
- `skills-set` exists as a verb, takes one skill per plan, and has never run on a live host.

**F6. `/jobs/<uuid>` now names the payer.** The body has a `paidBy` key. It was a 0x address on all 22 non-oracle jobs sampled (9 templates, 11 payers), and `null` on the one unpaid oracle job that could be read. The `/jobs` list rows carry no `paidBy`. Recorded in `docs/imd-api-changelog.md`, entry 2026-10-03; the captured bodies are in `data/surf/pepepane-corpus/api-2026-10-03-*.json`.

**F7. The plane sheds record reads.** Between 16:58 and 17:50 UTC, `/seats/<id>/standing`, `/seats/<id>?work=N`, `/jobs/<uuid>/submissions` and `/jobs/<uuid>` for oracle jobs answered `503 {"error":"busy", …}` after about 3.2 s on every attempt (16 of 16 from the Mac; seat #3 saw the same from the VPS). In the same minutes `/jobs/<uuid>` for non-oracle jobs answered 200 in about 0.2 s on 25 of 25 reads. `data/seat_api.py` retries a 503 once on the second host, which is the same plane.

**F8. `/jobs/<uuid>.nodes[]` carries each node's state.** Each node has `key`, `role`, `state`, `attempt`, `seat{tokenId, agentId}`, `verdict{status, evaluation, detail, …}` and `failureReason`. The attempt's outcome is the node's `state`. `verdict` is the structural verifier's check, not the outcome: in the clone's real submissions captures, 92 of 145 oracle rows have `verdict.status: accepted` while the attempt was rejected or still pending, and review nodes have `verdict: null` with `state: accepted`. A node shows only its latest attempt, and an oracle job's detail names one seat of a whole panel. `seat.tokenId` and `agentId` are **strings** (`"3"`, `"52082"`), as they are in `submissions[].seat`.

**F9. SURFBOARD's RECORD panel.** `widgets/surf/swarm_seat_record.py`: columns `when 11 · job 8 · node 6 · state 9 · model 9 · took 6 · tok 6 · panel 9 · answer (min 20, takes the rest)`; three tiers; `ROW_CAP 40`, step 20, `MAX_CAP 400`; title filter `all · not completed`; rows in source order, newest first; `CURSOR_TYPE = "none"`, popups open by mouse click only. Its helpers live in `widgets/surf/_oracle_answer.py` and `analytics/surf_swarm_signals.py`, which seat widgets may not import today.

**F10. Seat #3 host facts.** Claude Code 2.1.286, daemon `0.1.0+ae69e4ec` since 06:17 UTC, worker home `/home/imd-worker`. Transcript directories: four `-home-imd-worker--identitymd-work-<jobId>-<nodeId>`, two `-home-imd-worker--identitymd-work-doctor-<6 chars>`, one `-home-imd-worker`.

---

## 4. Screen model

### 4.1 Structure

Top to bottom: the title bar, the hero row with six cards, one body area holding the six bodies, the confirm strip (section 7), the status bar. `SeatScreen` stays a `DashboardScreen` and declares every widget of every body in `PANELS`.

### 4.2 Switching

- All six bodies are composed once at start. Selecting a card sets `display` on the bodies: the selected one is shown, the other five are hidden.
- **Every `PANELS` row is updated on every refresh, shown or hidden.** `fetch_and_compute` emits each LOG line once, so a hidden LOG that skipped an update would lose lines.
- A body that becomes visible repaints at its real width. A table that was hidden re-installs the column tier that fits.
- A body updated while hidden and then shown paints exactly what it paints when it is updated while visible.
- Selecting a dashboard moves the focus to that body's main table or log, so the arrow keys work at once.
- Selection is screen state, not manager state. It is not persisted; every start opens LIVE.
- Network reads for RECORDS and NODES depend on the selected dashboard (section 8.1). The manager is told which dashboard is selected, as SURFBOARD tells its manager with `set_agent_active`.

### 4.3 Keys

| Key | Where | Action |
|---|---|---|
| `1` … `6` | everywhere | select SEAT, LIVE, CONFIG & SKILLS, RECORDS, NODES, CONTROL |
| mouse click on a card | everywhere | select that dashboard |
| `c` | everywhere | select CONTROL (kept from today) |
| `esc` | a prompt is open | cancel the prompt |
| `esc` | no prompt is open | select LIVE |
| `r` | all dashboards except CONTROL | refresh |
| `r`, `d`, `s`, `S`, `b`, `o`, `D`, `x` | CONTROL only | the control verbs (section 6.6) |
| `enter` | SEAT, LIVE, RECORDS | open the detail of the selected ledger row, the shown job, the selected record |
| `space`, `enter` | CONFIG & SKILLS | toggle the selected skill row or the `boot` row |
| `tab` | CONFIG & SKILLS | move the cursor between the CONFIG and SKILLS tables |
| `h` | LIVE | collapse or expand heartbeat lines in LOG |
| `n` | LIVE | show the next running job in JOB |
| `f` | RECORDS | switch the filter `all` / `not completed` |
| `m` | RECORDS | show 20 more rows |
| `w` | NODES | switch the window `all` / `7 d` |
| `q`, `t` | everywhere | quit, cycle theme (unchanged) |

Rules:
- **While a prompt is open,** every key except `esc` belongs to the confirm input, whatever has the focus: the digits, `c`, `tab`, `enter`, `space` and every verb, toggle and dashboard key do nothing else. `enter` submits the confirm. If the input loses the focus, the focus returns to it. Only `esc` and a click on a card leave the prompt. (Measured on textual 8.2.8: a screen binding with `priority=True`, as `enter` is today, fires before a focused input sees the key.)
- A verb key pressed outside CONTROL does nothing. `r` outside CONTROL never plans a restart. What `r` does is decided inside `SeatScreen`; the shared refresh binding of `DashboardScreen` is not changed.
- **A table's cursor stays on its row.** A refresh, a column-tier change, and hiding and showing the body keep the cursor on the same row by that row's identity (the skill id, the setting name, the record's key), and keep the scroll position. Today every refresh rebuilds the table and puts the cursor back on row 0 (defect D12).
- The `l` key and the tall-LOG row class are removed. LOG has the full body height on LIVE.
- The status bar shows the key hints of the selected dashboard.

### 4.4 Title bar

`PEPEPANE · IDMD #3 · systemd · as of 17:08`, then in this order when they apply: the alert word, `‹ taller`, `offline`.

The alert word shows the seat's worst state on every dashboard: `⚠` and the first reason of `seat_hero_reasons`, yellow for amber and red for red. It is absent when the state is green.

### 4.5 Layout pins

- Each body has its own column pin and row pin, measured by `boundary_set` sweeps on the healthy and the worst payload, with a `#:` block beside the constant, as the terminal-layout skill requires.
- `SEAT_FULL_LAYOUT_COLUMNS` and `SEAT_FULL_LAYOUT_ROWS` become the largest body pin in each direction. Neither may exceed today's 134 and 50.
- Every body names its scrolling container, so `‹ taller` lights for the selected body and for no other. A body that names none must fail a test (SURFBOARD's `test_every_mode_names_its_scrolling_columns` is the model).
- A panel that can bind a pin must be able to show `‹ widen`.
- The cap applies to each table's narrowest tier. A wider tier that needs more than the body's pin is a named exception with its own measured constant, as LEDGER has today (`LEDGER_NEVER_CLEARS_BELOW`). That constant is re-measured for the full-width LEDGER and removed if the full tier fits at the pin.

### 4.6 CSS and reuse

- All seat CSS stays in `SeatScreen.DEFAULT_CSS` with ids starting `seat-`. `themes/minimal.tcss` is not touched.
- New panels subclass `widgets/panels.py` bases and `widgets/swarm_table.SwarmTableBase`.
- Code that SURFBOARD and PEPEPANE both need is hoisted into a shared module with a re-export shim at the old path, as base spec §15 requires. Seat widgets never import `widgets/surf/*`. After a hoist commit the surf layout sweep is run once.

---

## 5. Hero cards

Six `SeatHeroBox` cards, each seven rows tall as today: label, blank, three lines. Every line keeps today's rule of honest forms: several forms, longest first, the first that fits is painted; only the shortest form may be clipped, and then the card shows `‹ widen`.

**Border.** The selected card's border has the theme's success colour, the green of today's healthy LIVE card. Every other card has the neutral panel border. No health state changes a border.

**Label.** A card's label shows that card's own state: plain when fine, yellow with ` ⚠` when amber, red with ` ⚠` when red. A label marks something the operator should act on. An unreachable API and a running task are not such states: they are said inside the card's lines, in the colours those lines have today, and leave the label plain.

| Card | Line 1 | Line 2 | Line 3 | Label turns amber when | Label turns red when |
|---|---|---|---|---|---|
| SEAT | `IDMD #3 · agent 52082 · eligible` (today's SEAT line 1) | `active · 57 MiB / 16 G` (today's UNIT line 1); ` · boot ⚠` is appended when boot is disabled | `today 12 tasks · 11 stored` or `no tasks yet today` | boot disabled | unit not active |
| LIVE | unchanged | unchanged | unchanged | hero state amber | hero state red |
| CONFIG & SKILLS | `claude 2.1.286 · ae69e4ec`, with `↑` when a release is available | `skills 50/50 · cap 3` | `restart required`, `changed since start` or `unchanged since start` | restart required; config changed since start | config projection refused |
| RECORDS | today's VERDICTS line 1 | today's VERDICTS line 2 | today's VERDICTS line 3 | never | never |
| NODES | `4 node types · 85 % accepted` | the node type with the most attempts and its rate | `paid 3 · launch 1` | never | never |
| CONTROL | today's GATE line 1 | today's GATE line 2 | today's GATE line 3 | drain armed; verb in flight; broker unreachable | gate unknown |

Degraded wordings of the reused lines stay as the base spec's hero table defines them. NODES says `nodes unavailable` and the reason in its lines when it has no rows to count.

Facts that lose their card:
- `p50 · longest` and `local N = plane N ✓` (TODAY lines 2 and 3) move to the LEDGER footer.
- `restarts`, the stop timeout and the graceful-stop line (UNIT) are already in MACHINE and stay there.

**Defect fixed here.** The runtime short form prints `claude Code)` for `2.1.286 (Claude Code)` (`hero.py:299`). The short form is the runtime id and the version number: `claude 2.1.286`.

---

## 6. The six dashboards

Layouts are given as shares. Codex measures the pins.

### 6.1 SEAT

```
┌ MACHINE ─────────────────────────┐┌ COST · 7 d ──────────────────────────┐
│ unit · host · plane               ││ tasks · tokens · buckets · quota      │
│                                   │├ OUTPUT TOKENS / DAY · 14 d ───────────┤
│                                   ││ ▂▃▅▇▅▃▂▁▃▅▇█▅▃  today · 7 d · avg     │
└───────────────────────────────────┘└───────────────────────────────────────┘
┌ LEDGER · as of 16:58 ────────────────────────────────────────────────────┐
│ when  node  role  model~tier  took  turns  out tok  stored  verdict  lag │
└──────────────────────────────────────────────────────────────────────────┘
```

MACHINE is on the left, COST over OUTPUT TOKENS on the right, LEDGER below at full width. COST needs a panel 54 cells wide (measured on `f4de533`: it shows `‹ widen` at 53), so three panels side by side do not fit 134 columns.

- **MACHINE** keeps its three groups. Two defects are fixed (section 9, D4 and D7).
- **COST** keeps its rows. The sparkline strip leaves it.
- **OUTPUT TOKENS** is a panel of its own: output tokens per day for 14 days from the ledger's `days` table, and three figures below it: today, the 7-day total, the average per day. With fewer than two days of data it says why: `no token data yet (sessions: <reason>)` or `1 day so far`. It never says `waiting for data...` without a reason.
- **LEDGER** takes the full width. Its footer gains `today p50 28 s · longest 4 m 12 s` and keeps the divergence check. `enter` opens the detail (section 6.7).

### 6.2 LIVE

```
┌ NOW · as of 17:08 ──────────┐┌ LOG ───────────────────────────────────┐
│ task · plane · » sentence    ││ 17:08:41 alive 10h50m · idle · …       │
│ queue · auth                 ││                                         │
├ JOB · last · stored 23:45 ───┤│                                         │
│ d09e7e5b · research_report   ││                                         │
│ QUESTION                     ││                                         │
│ RESULT                       ││                                         │
│ verdict · model · tokens     ││                                         │
└──────────────────────────────┘└─────────────────────────────────────────┘
```

Left column 2 shares, LOG 3 shares. NOW has a fixed height, JOB takes the rest and scrolls inside itself.

**NOW** and **LOG** keep their content. LOG's footer is unchanged.

**JOB** shows one job: the running one, or when the seat is idle the last one that ran.

| Part | Content |
|---|---|
| Title | `JOB · working · as of 17:08`, `JOB · last · stored 23:45`, or `JOB · none yet` |
| Identity line | `d09e7e5b · research_report · implement · job 4003eaef`, the job id linked to the IMD explorer. With several running jobs it ends in `· 1 of 3`. |
| QUESTION | The job's objective, wrapped to the panel. For an oracle job, the oracle request's question. |
| RESULT, while working | `in progress · <phase> · <elapsed>` and the agent's last sentence, as NOW shows it. |
| RESULT, finished | For an oracle job: this seat's answer and the panel line. Otherwise: the reply text. Then a delivery line when the job was delivered: `delivered 23:46` and the repository path. |
| Verdict line | `accepted (+17 m)`, `rejected`, `failed runtime_error` or `pending`: the ledger row's outcome, in the colours of the ledger's verdict cell. The structural verifier's result is a separate, dim part: `check: structural — paths and tree verified`. It is never shown as the verdict. |
| Usage line | `claude-fable-5-1 · 6 turns · out 10,250 · took 55 s`, from the ledger row; from the submission's `usage` when the ledger has none. |

Rules:
- **Which job.** With one running job, that job. With several, the newest accepted first; `n` steps through them in acceptance order. When none runs, the newest ledger row.
- **Question source order.** While working: `standing.running[].objective` at once, replaced by the full objective when the job detail arrives. Oracle jobs: the oracle question once it is read. The heading names the source and its age: `QUESTION (api 17:08)` or `QUESTION (cached)`.
- **Unread text is said, never blank.** `question unavailable (api: busy)`, `reply unavailable (api: 503 ×2)`, `reply not read yet`. Under `--offline`: the cached text with `(cached)`, or `unavailable (offline)`.
- **Text is shown as plain text.** No Markdown rendering and no markup parsing; line breaks and square brackets are kept. A URL inside third-party text is not made clickable.
- **A 0x address inside that text follows MaxPane's address rule,** as SURFBOARD's popups apply it: it gets the copy icon through `widgets/address.py`. Reply and objective text name no chain, so their addresses get no explorer link. Oracle text links to the oracle request's chain. Real questions and replies contain addresses: 2 of the 5 captured objectives do.
- `enter` opens the detail (section 6.7).

### 6.3 CONFIG & SKILLS

```
┌ CONFIG · as of 17:01 ─────────────────┐┌ SKILLS · 50 offered · 50 on ─────┐
│ setting      value            change   ││ id                     on  needs  │
│ …                                      ││ …                                 │
└────────────────────────────────────────┘└──────────────────────────────────┘
```

Two tables side by side, equal shares, each with a row cursor. `tab` moves between them.

**CONFIG** lists every setting the worker has.

| Row | Value from | `change` column, round 9 |
|---|---|---|
| server | projection | `fixed` |
| seat | projection `tokenId`; agent id from the API | `fixed` |
| wallet | projection, 8 characters | `fixed` |
| device key | projection, 8 characters | `fixed` |
| runtime | unit `ExecStart`, `imd status` | `start flag` |
| capacity | `imd status`, projection as fallback | `runbook` |
| offers | `imd status` | `derived` |
| inference economy | projection `inference` | `runbook` |
| inference standard | projection `inference` | `runbook` |
| inference premium | projection `inference` | `runbook` |
| premium advertised | API standing | `—` |
| wrapper | the runtime wrapper's note, where a seat has one (seat #7's Codex wrapper), as today | `—` |
| tools | projection, ids only | `imd tools` |
| hints | `hints-stat`: file name, size, sha8, date | `never` |
| boot | unit `UnitFileState` | `space` |
| auto-update | unit `ExecStart` has `--auto-update` or not | `never` |
| daemon | journal: installed build, and the available one | `runbook` |
| config file | `changed HH:MM after start → restart required` or `unchanged since start` | `—` |

- A tier with no override reads `runtime default`. A model name is never hardcoded.
- `space` or `enter` on `boot` plans `enable-boot` or `disable-boot`. On the Mac the row shows the container's restart policy as read and is not editable.
- On the Mac both table titles and the card's runtime line carry `(container)`, as the CLI-fed lines do today.
- `space` or `enter` on any other row writes one status line that says how that setting changes, for example `capacity is the --concurrency start flag: drop-in plus drained restart (runbook §4c)`. It plans nothing.
- Per-row degraded wording stays as today (`unavailable (broker: <reason>)`, the red projection-refused line).

**SKILLS** lists every skill of the `imd skills` listing. The table scrolls; there is no 12-row cap.

- Columns `id · on · needs`. The title carries the counts: `SKILLS · 50 offered · 50 on · 9 need network`.
- `space` or `enter` on a row plans `skills-set` with that id and the opposite state. The id comes from the row, so nothing is typed except the confirm. The TUI checks the id against the skill-id pattern before it plans, as today.
- After a verified toggle the footer reads `restart required · 6 CONTROL · d drain-restart`. The footer keeps the tool ids line.
- The listing reads the config file, so a toggled skill shows its new state before the restart that makes it real. The footer says so while a restart is required: `shown state applies after restart`.

### 6.4 RECORDS

```
┌ RECORDS · all · not completed · as of 17:08 ─────────────────────────────┐
│ when         job       node    state     model  took  tok   panel  answer │
│                                                       +120 older · more   │
└──────────────────────────────────────────────────────────────────────────┘
```

One full-width table, built like SURFBOARD's RECORD panel (F9): the same columns, state words, colours, filter and row window (`40`, `+20`, at most `400`). Its column tiers are measured for this body: at the body's pin the table shows at least `when`, `job`, `node`, `state`, `panel` and `answer`; wider tiers add `model`, `took` and `tok`.

Differences from SURFBOARD:
- The table has a row cursor. `enter` opens the detail (section 6.7). `f` switches the filter and `m` shows more rows; the title words and `more` stay clickable.
- Rows come from the ledger, newest first. Today the ledger holds a plane work row only where a local row matched it by `hash12`, or after `--backfill-api`, and it keeps neither `jobState` nor `launch` nor the full `submissionHash`. Round 9 stores all of that from the seat-work read it already makes (section 8.2).
- `model`, `took` and `tok` come from the local ledger row when there is one, else from the submission's `usage`.
- `answer` is the first sentence of the reply, or the oracle answer value. Unread: dim `not read`, or yellow `busy` / `unavailable`.
- Under `--offline` the title reads `RECORDS · offline · cached`.

### 6.5 NODES

```
┌ NODES · all · 7 d · as of 17:08 ─────────────────────────────────────────┐
│ node  role  n  acc  rej  fail  pend  acc %  took p50  out p50  paid  launch  last │
└──────────────────────────────────────────────────────────────────────────┘
```

One row per node type (`nodeKey`), sorted by attempts, most first.

| Column | Meaning |
|---|---|
| `node`, `role` | the plane's `nodeKey` and `role` |
| `n` | attempts in the window |
| `acc`, `rej`, `fail`, `pend` | rows by plane status |
| `acc %` | accepted ÷ attempts, the definition the lifetime line `life N of M` uses |
| `took p50`, `out p50` | median duration and median output tokens, from local ledger rows of that node |
| `paid` | rows whose job has a payer (`paidBy`) |
| `launch` | rows whose work row names a launch kind, or whose job has `launch.requested: true` or a workflow. Every job detail has a `launch` object; only `requested` says whether one was asked for. |
| `last` | when the newest row of that node was submitted |

Rules:
- The window is `all` or `7 d`, switched with `w` or by clicking the title word.
- Rows the plane has not labelled yet (a local row with no `nodeKey`) are grouped in one row `(plane unread)`.
- `paid` and `launch` count only rows whose job detail has been read. A node with no detail read shows a dim `·`, never `0`.
- The footer states coverage and definitions: `covers 259 of 262 attempts · job details read 140 of 259 · acc % = accepted ÷ attempts · paid = the job has a payer (api paidBy)`.
- `pend` is never green. Counts are never added across routes (base spec §6 rules 1 and 2).

### 6.6 CONTROL

```
┌ CONTROL ─────────────────────────────┐┌ GATE · as of 17:08 ──────────────┐
│ [r] restart — safe now (…)            ││ idle beats · plane · last line    │
│ [d] drain-restart — armed: no         ││ outbox · unit                     │
│ [s] stop · [S] start                  │├ AUDIT ────────────────────────────┤
│ [b] disable at boot — enabled         ││ 15:51 doctor plan planned (#1)    │
│ [o] kill orphans · [D] doctor         ││ …                                 │
│ [x] cancel drain                      ││                                   │
└───────────────────────────────────────┘└───────────────────────────────────┘
```

- **CONTROL** (left) is the verb list with the live gate words of today's popup. The plan block and the status appear below the list.
- **GATE** (right, top) shows the gate's facts one per line: idle beats of required, plane mode and running count, the last lifecycle line, outbox files, unit state.
- **AUDIT** (right, bottom) shows the newest audit lines through `audit-tail`, as many as fit, at most 20.
- `[k]` leaves this list; skills are toggled in SKILLS. A pointer line says where settings live: `skills, boot, capacity, tiers → CONFIG & SKILLS (3)`.
- The three static lines of the popup are replaced. Two were wrong: `capacity: 1 by decision` (seat #3 runs 3) and a tier pointer to runbook §2.1, which is the update procedure. One line remains: `update: <installed> → <available> — runbook §2.1 (drained restart)`.
- Everything else behaves as base spec §11 and the popup define: the plan block, the typed confirms, `--force`, the `local-only` acknowledgement, apply returning at once, verify polled on the tick, no automatic re-plan or re-apply, the 15 s standing cadence while a plan is open.
- `SeatControlScreen` (the popup) and `SeatScreen.apply_payload` are removed. The screen is no longer suspended during control, so the ordinary refresh serves it.
- GATE, AUDIT and the CONTROL card show a plan, an apply and a verdict within one refresh cycle. Today the audit tail and the in-flight fact come from a 300 s tier that reads five lines.
- Every panel has one writer: the ordinary `PANELS` update. The write flow never paints a panel directly.

### 6.7 The detail popup

One popup serves a ledger row, a record and the JOB widget: `SeatTaskDetail` on the `RecordDetailScreen` frame, with four sections.

| Section | Content | Shown when |
|---|---|---|
| LOCAL | as today | a local ledger row exists |
| PLANE | as today, plus `paid: yes (api paidBy)` or `paid: no payer`, the template, and the launch or workflow link | plane data exists |
| QUESTION | the full objective, or the oracle question | text is cached or readable |
| RESULT | the full reply; or the oracle answer, notes and panel line; the delivery line | text is cached or readable |

The payer's address is not displayed in round 9. The ledger stores it for the later chain work.

---

## 7. The write flow

CONFIG & SKILLS and CONTROL share one write flow and one confirm strip. The broker protocol is unchanged.

- **One prompt at a time.** A prompt is a force-node8 entry, or a plan awaiting its typed confirm. The broker still allows one write in flight.
- **The confirm strip** sits under the body. On CONTROL it is always visible. On CONFIG & SKILLS it appears when a plan opens. It shows the plan (the verb, the exact command with its target, and the warning), the input and the status line. A toggle's plan names the skill or setting it changes, so a wrong row is visible before the confirm is typed.
- **States:** idle → prompt → applying → verifying → done or failed. The words and outcomes are those of today's popup.
- **Leaving the dashboard:**
  - While a prompt awaits its confirm, selecting another dashboard drops the plan. The status reads `plan 7f3a dropped — not applied`. The plan id is never applied later.
  - While a verb is applying or verifying, it continues. The CONTROL card shows it. The outcome appears in the status line and in AUDIT.
- **`esc`** cancels an open prompt and does not change the dashboard.
- **The flow has its own clock.** It keeps polling `verify` while another dashboard is selected and while the detail popup is open. The broker evaluates a verify only when asked and forgets the watch after 120 s, so a paused poll would turn a successful restart into `unknown_plan`.
- **A late plan is dropped.** A plan reply that arrives after its dashboard was left opens no prompt.
- **`plan_open` ends with the flow.** The manager's faster standing cadence is switched off on every exit: confirm, drop, `esc`, expiry, error and verdict.
- **Refusals** are shown as the broker's enum word: `busy`, `plan_expired`, `plan_spent`, `bad_confirm`, `skill_not_listed`, `bad_skill_id`.
- **After a verified `skills-set`** the restart-required flag is set and stays until the next restart boundary, as today.

---

## 8. Data

### 8.1 New API reads

| Route | Supplies | Read for |
|---|---|---|
| `GET /jobs/<uuid>` | full `objective`, `template`, `paidBy`, `launch`, `workflow`, `oracleRequestId`, `parentJobId`, `delivery`, and `nodes[]` with this seat's verdict | JOB, RECORDS, NODES, the verdict fallback |
| `GET /jobs/<uuid>/submissions` | this seat's attempts: `summary` (the reply), `usage`, `verdict`, `oracleResult`, counts of findings and artifacts | JOB, RECORDS. Today it is read only for old failed rows. |
| `GET /oracle/requests/<id>?members=<hash>` | `question`, this seat's `answer`, `agreement` (the panel) | JOB, RECORDS, for oracle jobs |

**When they run.**
- **JOB:** for the running jobs and the last job. The job detail is read as soon as a running job's id is known (from the standing read or the work directory's name). The submissions (and the oracle request) are read about 60 s after `submission stored`, and again with backoff until they have been read.
- **RECORDS:** for rows in the visible window that lack detail, newest first, only while RECORDS is selected.
- **NODES:** job details only, for rows that lack them, newest first, only while NODES is selected, for the newest 400 rows.

**Budget.**
- At most 2 detail reads per refresh cycle, all three routes together. A refresh cycle is one `fetch_and_compute` run, every `--poll-interval` seconds (5 by default). This replaces the base cadence of at most 2 submissions reads per 300 s.
- Every result is stored in the ledger. A job, a submission or an oracle request that has been read in a terminal state is never read again.
- The existing read of failure reasons for old failed rows uses the same budget and the same stored submission. It is no longer a schedule of its own.
- Under `--offline` none of these reads run.

**`busy` is its own state** (F7).
- A `503` whose body has `error: busy` is not retried on the second host.
- It pauses that route class for 60 s, doubling on each further `busy` up to 600 s, and resets on a success. Route classes: seat routes, submissions, job detail, oracle.
- The pause is a floor for every trigger of that route class: the tier's own cadence, the extra read after `submitted` or `stored`, the 15 s cadence while a plan is open, and the detail reads.
- The source's reason reads `busy`.
- **Live facts keep base rule 4.** What only the plane knows at this moment (working, running, queue, presence) turns `unavailable` after 3 failed reads or 600 s, as today, with the reason `busy`.
- **Ledger-backed facts stay.** Verdicts, records, node counts and stored text come from the ledger and are shown with their own time, whatever the API's state. `busy` never blanks them and never turns them into zeros.
- This also applies to the existing reads of `/seats/<id>/standing` and `/seats/<id>?work=N`. The fresh standing read inside a broker `apply` is the broker's own and does not change.

**Verdict fallback** (F7, F8).
- The verdict word always comes from the seat work row's `status` once that row has been read.
- The fallback applies only until then, and only to a job that is not an oracle job (`oracleRequestId` is null). It reads the node's `state`, never `verdict.status`.
- It maps only the four ledger words: accepted, rejected, failed, pending. Any other state leaves the verdict `?`.
- It needs exactly one node of that job with this seat's token id (or one whose `key` equals the row's known `nodeKey`), and exactly one ledger row of this seat for that job and node. Otherwise the verdict stays `?`. Both ambiguities are real: in the captured `shape:dag` job one seat holds three of the eight nodes, and a seat can attempt one node several times.
- A row filled this way records its source, the detail popup's `sources` line names it, the day's counts are recomputed, and a later seat work row overwrites it.

**Oracle panels.**
- This seat's member is found by equality of the full submission hash, never by position.
- Whether the seat is in the agreeing cluster is computed before the body is redacted, because redaction replaces the cluster's hashes. Only the derived panel fields are stored.
- The panel rules are SURFBOARD's (`enrich_panel_rows` in `data/surf_swarm.py`). A test runs both on the same real body and requires the same result.

**String ids.** `seat.tokenId` and `agentId` are accepted as integers or as digit strings, everywhere (D1).

### 8.2 The ledger cache

`~/.maxpane/seat_ledger.sqlite` gains storage for what the new reads return. The schema change is additive: an existing ledger file opens and keeps its rows.

| Stored per job | Stored per attempt (job and submission hash) |
|---|---|
| objective (text), template, `paidBy`, launch kind and requested flag, workflow id, oracle request id, parent job id, delivery url and time, fetched time | reply (text), the structural check's result and detail, oracle question (text), oracle answer and notes (text), panel line, usage (model, turns, tokens, wall time), fetched time |

From the existing seat-work read the ledger also stores, per work row: the row itself when no local row matches it, `jobState`, `launch` and the full `submissionHash` (the oracle read needs the full hash). A plane row stored this way must never become a second row for a task whose local row gains its hash later.

- **One sanitiser for every stored text.** It runs `redact()`, whose first step strips control characters, then removes whatever the status document's secret canary would still match, then cuts. After it, no canary pattern matches. Today `redact()` leaves a base64 JSON blob (`eyJ…` without a dot) unchanged; the canary then reads it as a token and the whole document is refused (defect D11). The two redactor copies are not changed.
- **Fields are copied one by one.** No API sub-object is stored, or put into the document, whole: a third-party key named `secret` would trip the canary's key rule.
- **The dollar sign** is removed from stored text, as it is from every other string PEPEPANE shows, so JOB and the detail popup agree.
- **Caps.** Each text is cut at 4,096 characters; the check detail at 512. A cut text ends in `…`.
- **Retention.** Text is kept for the newest 400 records, ordered by the row's accepted time, and removed from older ones. A removed text reads `text expired` and is not read again by itself. The structured fields (template, payer, launch, outcome) are kept for every row, because NODES counts over all of them.
- **The existing schema stays readable.** The ledger's schema version does not move; the new storage is new tables or nullable columns. A file written by round 9 still opens under `f4de533`, which a rollback needs. The full objective is never written into the existing 160-character `objective` column, which the seat-work read overwrites.
- **Never elsewhere.** The text is never written to the audit log, to `~/.maxpane/maxpane.log`, or to a fixture without redaction.

### 8.3 The status document and the data contract

- The data contract is frozen first: new keys in `SEAT_KEYS`, `SEAT_ROW_KEYS` and `SEAT_WIDGET_SIGNATURES` for the six cards, JOB, OUTPUT TOKENS, RECORDS, NODES, GATE and AUDIT. `docs/seat_status_schema_v2.md` is updated in the same change. Changes are additive.
- The status document carries the JOB text for the jobs JOB can show, and a one-line answer preview per RECORDS row. It does not carry the full text of 400 records. A detail popup reads the full text from the ledger by key.
- The document stays under its 2 MiB bound on the worst payload. A test proves it.
- A contract key for the list of running jobs is added, because `seat_current` holds one job and seats #3 and #420 run three.

### 8.4 Hostile input

- Question, reply, oracle answer, notes, check detail, template and delivery url are third-party strings. Each passes the sanitiser of section 8.2.
- Multi-line text becomes a `Text` built from the plain string, with no markup parsing, so line breaks and square brackets survive. The tag-stripping helpers of `markup_safety` are for single-line cells: on real replies they delete every bracketed run and join the lines.
- The reply of a failed run is the raw runtime error. The redactor's credential shapes apply to it as to every other string.
- **Accepted this round:** the redactor replaces every 64-hex value by `<hex64>`, so a transaction hash in a reply is not readable, and its `sk-` rule also matches inside ordinary words (`risk-adjusted` becomes `risk-[redacted]`). Both are filed for round 10, which changes the broker's copy of the redactor.

---

## 9. Defects fixed in round 9

Each was measured on 2026-10-03. Each fix needs a test that fails on `f4de533`.

| # | Defect | Evidence | Required behaviour |
|---|---|---|---|
| D1 | Submission and node seat ids are strings; the parser accepts only integers, so no submission ever matches this seat and failure reasons older than 24 h never attach. | `data/seat_api.py:147-148`, `:342`; `data/seat_manager.py:1286`; the five real submissions captures under `tests/fixtures/surf/swarm/` (and the hand-made hostile one) carry string seat ids, and today's live job read has `"tokenId": "3"`. The seat fixtures are synthetic and use integers. | Integers and digit strings both parse. A fixture taken from a real capture proves the match. |
| D2 | The Claude transcript matcher hard-codes the Mac container's home, `-home-imd`. On seat #3 the home is `/home/imd-worker`, so all seven transcripts count as `manual`: no tokens, turns or model on any task, no OUTPUT TOKENS, and doctor runs are not recognised as doctor runs. | `imd_dashd/summarise_claude.py:47-50`; seat #3 `--once`: `cost.tokens: null`, `excluded: {doctor: 0, manual: 7}`; directory names in F10. | The slug prefix is derived from the projects root the summariser is given (`--root <home>/.claude/projects`), with today's constants as the fallback for a root of another shape. No new argument. Both `/home/imd` and `/home/imd-worker` are covered by fixtures. The doctor suffix is mixed case (`doctor-zN5enH`). |
| D3 | Facts learned from startup lines are lost when a new PEPEPANE process starts after the journal watermark: daemon version, release available, last admitted, submitted since start. | `data/seat_ledger.py:296-316` sets them only when the line is ingested. Seat #3: the journal has `release 0.1.0+ae69e4ec, the latest` at 06:17:50, yet `seat.daemonVersion: null`, `daemon.lastAdmittedUtc: null`. The LOG footer reads `grammar 5bfa8261 (daemon version unknown)`. | A fresh process on an already-ingested journal knows these facts. |
| D4 | MACHINE's journal row is never filled. | `data/seat_broker_client.py:1177` sets `journal: None` and nothing assigns it. Seat #3: `machine.journal: null`. | The row shows the journal window and cap as base spec §8 describes, or an explicit reason. The facts are read on a slow tier, off the refresh path, with three bounded commands measured on both seats (7 to 31 ms each). |
| D5 | A retried 401 raises a false "auth degraded". | Seat #3's 15:51 doctor transcript: line 18 is `system api_error`, status 401, retry 1 of 10; line 19, two seconds later, is an assistant message with output. The TUI showed `⚠ runtime auth degraded — api_error 401` for over an hour on an idle, healthy seat. | A 401 or 403 that was followed by model output in the same session does not count. The summariser reports whether output followed; the rule in `analytics/seat_auth.py` uses it. A fresh process and a long-running one must reach the same verdict: today the newest session is in-memory state while the sessions watermark is persisted (`data/seat_manager.py:1022-1045`), so `--once` saw no session at all. The new fact must reach the rule: today the ledger rebuilds each API error as status, message and time only (`data/seat_ledger.py:827-828`). A recovered 429 is treated the same way. |
| D6 | The SEAT card prints `claude Code)`. | `widgets/seat/hero.py:299`. | `claude 2.1.286` (section 5). |
| D7 | MACHINE prints `transcripts transcripts 30-day window`. | `widgets/seat/machine.py:181` starts the value with the row's own label; owner screenshot, seat #3. | The label once. |
| D8 | CONTROL's static lines are wrong. | `screens/seat_control.py:69-70`. | Section 6.6. |
| D9 | `503 busy` is retried on the second host and is not told apart from other failures. | `data/seat_api.py:477-535`; F7. | Section 8.1. |
| D10 | A second `pepepane --once` within seconds on an idle seat reports `tail ok=False`, reason `backfill returned no lines`. | Reproduced on seat #7 on 2026-10-03 (probe p09). | No new lines after a valid watermark is not a failure. Probe p09 prints each source's reason. |
| D11 | One third-party string can blank the whole screen. | `redact()` leaves `…base64,eyJuYW1l…` unchanged; `find_secret` then reports `jwt`, and the manager replaces the refused document with an empty one (`analytics/seat_redact.py:73` and `:92`, `data/seat_manager.py:429-438`). Reproduced with the clone's own functions. The objective shown in NOW passes the same path today. | Section 8.2: after the sanitiser no canary pattern matches. A job objective or a reply containing such a string leaves the document valid. |
| D12 | A table's cursor jumps to row 0 on every refresh. | `widgets/panels.py:942` clears and re-adds the rows on every update. Measured on the real screen at `f4de533`: cursor on row 7, one refresh, cursor on row 0. LEDGER's `enter` therefore opens the wrong row after five seconds. | Section 4.3: the cursor keeps its row. The fix lives in `widgets/seat/*`; the shared table bases are not changed. |

One anomaly was seen and not explained: the same `--once` document has `tasks.window.gapNote: "gap 2026-10-03T17:30:12.045Z→?"`. Codex reproduces it with a fixture and either fixes it or files it with the cause.

---

## 10. Round 10 — config write verbs

Design level. Its brief is written after round 9 is verified and after the measurements listed at the end of this section.

**`capacity-set {n}`**, `n` from 1 to 4.
- **systemd hosts.** The broker writes a root-owned drop-in under `/etc/systemd/system/imd-worker.service.d/` that resets `ExecStart` to the unit's current command with `--concurrency n`. The command is taken from the live unit, not from a template. It then runs `daemon-reload`. The change needs a restart, so `restartRequired` is set and CONFIG points to drain-restart.
- **An existing drop-in is adopted.** Seat #7 already has `concurrency.conf`, made by the owner. The verb rewrites that file and keeps a timestamped backup. It never adds a second drop-in that would compete with it.
- **The plan shows** the current value, the new value, the unit's `MemoryMax`, the host's available memory, the inverse value, and the warning that an out-of-memory kill reads as rejected work.
- **Verify:** the unit's `ExecStart` carries `n`; after the restart `imd status` reports `n`.
- **Mac.** Not available. Capacity is baked into the container command and a recreate is excluded. The row stays read-only.
- **Broker unit.** It needs write access to that one directory. This is a change to the audited unit and to the installer, with its own probe sections.

**`tier-set {tier, model, effort}`** and **`tier-clear {tier}`**, tier one of `economy`, `standard`, `premium`.
- A stdlib script run as `imd-worker` in a transient unit edits the `inference` block. It never prints the file. It writes a temporary file with mode 0600, keeps a timestamped backup, and renames.
- Validation before the write: the model id and effort match fixed patterns; a premium value must be the runtime's premium model with an allowed effort, otherwise the plan warns that premium would no longer be advertised.
- Validation after the write, and rollback to the backup when it fails.
- The audit line carries the verb, the tier, the model and the effort. It never carries the document.
- **UI.** `enter` on an inference row opens a two-field entry in the confirm strip, then the plan.

**Promotion rule** (base spec §16 #3). The owner exercised both procedures by hand on seat #7: inference edits on 09-22 and 09-23, the capacity drop-in on 09-27 and 10-02. On seat #3 the first use of each verb is its first exercise there; the owner runs it at an idle gap with the probe.

**To measure before the round-10 brief**, in throwaway `systemd-run` units on a real host:
1. What the daemon and `imd status` do with a zod-invalid `config.json`: exit code and output.
2. Which model and effort strings the schema accepts.
3. Whether a `config.json` without an `inference` key passes the projection's eight-key rule. Seat #3's document shows `inference: {}`.
4. How `--concurrency` outside 1 to 4 is handled.
5. `skills-set` end to end on a live host, which round 9 exercises for the first time.

---

## 11. Later

- **Paid status from the chain.** Only if `paidBy` coverage proves too thin, for example because oracle job details stay shed. The rule exists in `tools/surf/_market_page.py`.
- **The payer's address** in the detail popup, with the address rule's copy icon and explorer link for mainnet.
- **OTHER SEATS ON THIS JOB**, findings and artifact lists in the detail popup.
- **The redactor's two over-matches** (64-hex inside prose, `sk-` inside words), fixed in both copies together with round 10's broker change.

---

## 12. Testing and verification

**MaxPane's rules apply unchanged:** no test touches the network, the real journal, a real socket, a real `~/.maxpane`, Docker or ssh. Assertions run against composited output (`render_strips()`).

**Fixtures.**
- API bodies come from real captures: today's `/jobs/<uuid>` body with `paidBy`, the `503 busy` body, and submissions and oracle bodies from `tests/fixtures/surf/swarm/`, which have string ids.
- The paid, unpaid, workflow-and-launch and `busy` shapes come from the six captures of F6. A body without the `paidBy` key was never observed; its fixture is synthetic and labelled so, and it must read as "not known", not as unpaid.
- Transcript fixtures for D2 and D5 are reduced to metadata as base spec §14 requires.

**Layout.** One sweep per body, healthy and worst payload, with tightness tests that reject a looser pin. The address sweep's seat case lists the views that reach all six bodies.

**Proofs that must bite.** Each names a mutation that must turn a named test red.

1. Colour the selected card's border from the health state → the border test fails.
2. Change the label colour on selection → the label test fails.
3. Skip the update of a hidden body → a LOG line emitted while SEAT is selected is missing on LIVE.
4. Fire a verb key outside CONTROL → the test that presses `r` on LIVE sees a plan.
5. Keep a plan alive across a dashboard switch → the dropped-plan test applies it.
6. Retry `busy` on the second host, or skip the backoff → the request-count test fails.
7. Store a reply without redaction → the masked-key fixture reaches the ledger.
8. Remove a text cap or the 400-record retention → the size tests fail.
9. Accept only integer seat ids → the real-capture match fails (D1).
10. Hard-code the home slug → the `/home/imd-worker` fixture yields no tokens (D2).
11. Count a recovered 401 → the D5 fixture raises auth degraded.
12. Drop the startup-facts rebuild → the D3 fixture shows no daemon version.
13. Put full record text into the status document → the 2 MiB test fails.
14. Use the verdict fallback when two nodes of a job belong to this seat → the ambiguity test fails.
15. Show `0` for `paid` on a node with no detail read → the coverage test fails.
16. Let a canary-matching string through the sanitiser → the D11 test sees a refused document.
17. Rebuild a table without restoring the cursor → `space` plans another skill in the D12 test.
18. Leave `enter` a priority binding while a prompt is open → the confirm is never submitted.
19. Pause the verify poll while the detail popup is open → the verdict never lands.
20. Read `verdict.status` in the fallback → an oracle or a review fixture row turns `accepted`.

**Suites.** The seat suite, the contract and purity tests (`__all__`, `MIGRATED_PACKAGES`, the title-blank-row list, the allowed analytics set), and the surf layout sweep once after any hoist commit. The full suite runs once, by the controller, before the round is declared done. The cold footprint of the lean entrypoint stays within its 160 MiB budget.

**Independent verification by Claude, as in rounds 1 to 8.** Git hygiene; each new test fails on `f4de533`; the archive checked byte for byte; the broker-side diff limited to what success criterion 9 allows; `pepepane --once` read-only on seats #7 and #3 before and after the owner's install. The owner runs the install and the probe.

---

## 13. Fork hygiene

- **May change in round 9:** `maxpane_dashboard/screens/seat*.py`, `widgets/seat/*`, `data/seat_*.py`, `analytics/seat_*.py`, `seat_cli.py`, `scripts/pty_footprint2.py`, shared modules that receive a hoist (with a shim at the old path), tests, fixtures and docs. Broker-side: `imd_dashd/summarise_claude.py`, the version identity strings, the probe's p09 section, and the regenerated `MANIFEST.sha256` and `requirements.lock`.
- **Never touched:** everything base spec §15 lists as never touched; the unit files, the sshd and slice drop-ins and `install.sh` under `deploy/vps/`; the verbs, gate, drain, child-unit, projection, audit and redaction code in `imd_dashd/`; `themes/minimal.tcss`; the shared `screens/dashboard_screen.py`, `screens/refresh_guard.py`, `widgets/panels.py` and `widgets/swarm_table.py`.
- **Clone docs:** the spec is adapted into the clone's `docs/`, with dated entries in `docs/decisions.md` for each amended rule of section 14, and updates to `docs/seat_followups.md`, `docs/seat_status_schema_v2.md`, `CHANGELOG.md` and the terminal-layout skill's pin table.
- **Tier.** This is a Tier 2 change under the clone's `CLAUDE.md`.

---

## 14. Amendments to the base spec

| Base spec | Was | Now |
|---|---|---|
| §8 layout | hero over a 2+2+2 body, all six panels at once, one measured pin (as built: 134 × 50) | six bodies, one shown; one pin per body (4.5) |
| §8 HERO | SEAT · LIVE · TODAY · VERDICTS · GATE · UNIT with the precedence red, amber, green (as built: the LIVE border shows it) | six dashboard cards; the border shows selection; health on the label and the title bar (5) |
| §8 CONFIG & SKILLS | one panel with a capped skills table (as built: 12 rows and `+N more`), nothing selectable | two tables with cursors and toggles (6.3) |
| §8 COST | includes the sparkline strip | the sparkline is the OUTPUT TOKENS panel (6.1) |
| §8 LOG | `l` toggles a taller view | removed (4.3) |
| §8 LEDGER detail | "never prompts, tool outputs or summaries" | API question and reply are shown; local transcripts and workspaces stay unread (6.7) |
| §8 CONTROL | a modal opened with `c` | a dashboard; `c` selects it (6.6) |
| §6, submissions route | only failed rows older than 24 h; "never persist or render `summary`" | this seat's rows for JOB and RECORDS; the reply is stored redacted and capped (8.1, 8.2) |
| §6, routes | no `/jobs/<uuid>`, no oracle route | both are read (8.1) |
| §6 | retry once on a 5xx or a timeout, over a two-host pool | unchanged, except that `busy` is not retried and backs off (8.1) |
| §6 rule 5 | failure reasons as the enum word only | unchanged for reason cells; the reply text is shown separately in JOB and the detail |
| §10 | Claude slugs listed for `/home/imd` | derived from the worker's home (D2) |
| §10 | auth degraded when the newest transcript has a 401 or 403 | only when no model output followed it (D5) |
| §11 | `[k] skill on/off` with a typed id | toggled from the SKILLS row (6.3) |
| §11, §16 #3 | `tier set` and `capacity set` are static lines | approved as verbs for round 10 (10) |
| §13, §16 #13 | failure summaries never persisted | API text is persisted redacted, capped and bounded (8.2) |
| §6 rule 4 | a source is `unavailable` after 3 failures or 600 s | unchanged for live facts; ledger-backed facts are shown from the ledger whatever the API's state (8.1) |
| §13, the address sweep | PEPEPANE shows no 0x address | an address inside API text carries the copy icon; oracle text links to its chain (6.2) |
| §16 #6 | API consent for four route families at fixed cadences; submissions at most 2 jobs per 300 s, failed rows older than 24 h only | extended by the reads of 8.1, at most 2 detail reads per refresh cycle, each result read once |

---

## 15. Risks and open questions

1. **The plane may shed record reads for long periods.** Then RECORDS, NODES and the reply in JOB read `busy` and show what the ledger has. The design says so on screen and backs off. The verdict fallback covers non-oracle jobs. Oracle job details are shed too, so oracle rows may stay unread.
2. **`paidBy` semantics.** One unpaid oracle job read `null`; 22 non-oracle jobs read an address, among them jobs the dev or the network may have funded. So `paid` means "the job has a payer", not "an outside customer paid". The column's footer states that definition. Who the payer is stays the market page's question.
3. **Three running jobs.** JOB steps through them, but the gate's lifecycle check still names only the newest line (follow-up 56). That is a gate question and is not changed here.
4. **A dropped plan may surprise.** Selecting another dashboard while a confirm is open drops the plan. The status line says so, and nothing was applied.
5. **Ledger growth.** Text is bounded to the newest 400 records, about 5 MB at the caps. The structured fields grow with the row count, as the ledger does today (follow-up 20).
6. **Round 9 touches one broker-side file** (R9, decided). The install therefore replaces the broker package on both seats. The file is a read-only summariser run as `imd-worker`; the probe's sessions section covers it.
7. **Seat #3 probe section 20 and its worker drop-in are still open.** They are independent of this redesign.
8. **Third-party text is over-redacted.** Transaction hashes read `<hex64>`, words containing `sk-` are damaged, and dollar signs are removed. The text stays good enough to judge a job; the full record is on the IMD explorer, one click away through the job link.
