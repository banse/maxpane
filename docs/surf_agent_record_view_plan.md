# Surf AGENT: card rows merged, RECORD taller, `more` and a not-completed filter (spec + plan, 2026-09-24)

This is a Tier 2 change:
- A card row is removed.
- A widget signature in `data/surf_models.py` changes.
- The AGENT row pin moves.
- RECORD gets two click actions.
- The manager's enrichment window follows the view.

Every item below is an owner decision from 2026-09-24, made on screenshots of AGENT #420. Where a detail was not
given, the controller chose it; those choices are marked **(controller)**.

Precedence: CLAUDE.md > this spec > WP steps > implementer report.

---

## CODEX — START HERE

1. The base is autopull's local main. It is unpushed, and this clone's `origin/main` is behind:
   ```bash
   cd /Users/banse/codex/maxpane
   git status --short        # expect .codex/ .venv311/, the pool4 oracle fixture and this plan
   git fetch /Library/Vibes/autopull main
   test "$(git rev-parse FETCH_HEAD)" = 0db16621bcc3fd8be8847325e2f26bea9af75ba2 || echo STOP
   # main now tracks the pool4 fixture; the untracked copy here is byte-identical (checked 2026-09-24):
   git show FETCH_HEAD:tests/fixtures/surf/pool4/oracle_25955365.json | cmp - tests/fixtures/surf/pool4/oracle_25955365.json \
     && rm tests/fixtures/surf/pool4/oracle_25955365.json || echo STOP
   git switch -c feature/surf-agent-record-view FETCH_HEAD
   .venv311/bin/python -m pip install -e . -q
   ```
   If either check prints STOP, stop and report.
2. Read `CLAUDE.md`, `.claude/rules/surf.md`, `widgets.md`, `data.md` and `.claude/skills/terminal-layout/SKILL.md`.
   Then read the pin blocks beside `SURF_AGENT_FULL_LAYOUT_{COLUMNS,ROWS}` and `RECORD_NEVER_CLEARS_BELOW`
   in `screens/surf.py`.
3. Run WP0–WP5 **straight through**, with no pause between WPs. Stop only on §6. Write one final report (§7).
4. Never push, merge, tag, bump the version or rewrite history. Commit per WP.
5. Use `.venv311/bin/python` with `env -u NO_COLOR`. Run named tests plus `-m guard`, and never the full suite.

---

## 1. What the owner asked for

### 1.1 RECORD column order

The columns become `when · job · node · state · model · took · tok · panel · answer`. `tok` moves in front of
`panel`, and nothing else changes: compact still drops `tok`, and tight still drops answer, model and took and keeps
panel.

### 1.2 COLLAB takes the top two teammates

COLLAB is in the seat-card row. It keeps its first line and adds the two teammates with the most shared jobs:

```
      COLLAB
    261 seats
  #1626 ×161
  #1731 ×151
```

- The teammate lines use today's TEAMMATES formatting (bold `#token`, dim `×N`) and order (shared jobs descending,
  then token ascending).
- COLLAB never shows `+N more`, because its first line already counts the seats.
- An unread teammates list shows a yellow `unavailable` on line 2. An empty list shows a dim `none yet` on line 2
  **(controller)**.
- Seat gating is as today: pending, never-paired and unavailable show as the other seat cards do.

### 1.3 TEAMMATES becomes NODES

The card keeps its slot (under STATUS). Its body is one line per node the seat worked:

```
       NODES
  ORACLE 224 85.2 %
  REVIEW 1 100.0 %
     +2 more
```

- The line reads `<NODE> <accepted> <rate>`:
  - The node name comes from `NODE_TITLES` (ORACLE, REVIEW, BUILD) and is dim.
  - The accepted count is bold green when above 0, else bold.
  - The rate is `fmt_win_rate(accepted / attempts)`, bold. When `attempts` is `None` or 0 the rate is `—`.
- An unknown node key is shown by its own flattened key, fitted with a visible `…` **(controller)**. The key is
  third-party text, so it is not upper-cased.
- **Which nodes are listed:** every `swarm_seat_node_rows` entry with `attempts > 0` or `accepted > 0`.
- **Sort order (controller):** accepted descending, then attempts descending, then `NODE_TITLES` order, then key.
  For #420 this gives ORACLE, REVIEW, BUILD and one unknown key, so the card shows ORACLE, REVIEW and `+2 more`.
- **Line rule:** the TEAMMATES rule, reused. With ≤ 3 nodes all are shown; with more, the first two plus
  `+N more`.
- Counts that do not fit shorten by the node cards' honest-number forms (`fmt_int` → `fmt_compact` → whole `K`).
  Those helpers (`_whole`, `_forms`, `_num`, `_reading`) move into `widgets/surf/_swarm_seat.py` and are not copied.
- **Empty and unread:** no listed node shows a dim `no nodes yet`. An unread list shows `unavailable`. Seat gating is
  as today.

### 1.4 The third card row goes away

`SurfSwarmNodeCards` (ROLES, ORACLE, REVIEW, BUILD, OTHERS, BOARD) is removed from the AGENT body, together with its
module `widgets/surf/swarm_node_cards.py`. Anything still used elsewhere is hoisted first; `NODE_TITLES` already
lives in `_swarm_seat.py`.

**The owner accepted that these facts leave the screen:**
- ROLES
- the per-node `chain` counts and short role names
- OTHERS as a separate sum
- BOARD's `acc of / rejected / pending` from `/contributors`

What stays on screen: the hero's RANK still reads `swarm_seat_contrib`, and the data keys stay in the payload, so
nothing in `data/` is removed. `rank_body` and `contrib_body` stay in `_swarm_seat.py`. `board_body` goes if nothing
else uses it; say so in the report.

### 1.5 RECORD fills the freed space

RECORD is already the body's elastic panel, so the freed height goes to it. Its floor stays 6.
- **Re-sweep `SURF_AGENT_FULL_LAYOUT_ROWS` in situ**, on the payloads its `#:` block names. It is expected to
  **fall** (the removed row plus its blank row). Write the new number and the measured evidence in the block.
- The width pin `SURF_AGENT_FULL_LAYOUT_COLUMNS` must **not** rise. Re-sweep it too, with NODES and the new COLLAB
  in the seat row.
- Update the onsets that the block attributes to the node row: those facts are gone, so delete them rather than keep
  them as history.

### 1.6 `more` in RECORD's footer

The footer `+227 older` becomes `+227 older · more`.
- `more` is a click target: dim word, bold on the click span.
- Its `@click` meta is `screen.record_more()`, built like the `»` button, with the action text fixed and taking no
  argument.
- Each click shows **20 more rows**, or the remainder when fewer are left. With nothing left the footer has no `more`
  and no `+N older`.
- The screen owns the window: `record_cap`, starting at `ROW_CAP` (40).
- It resets to 40 when the seat changes. It is not persisted, so a restart shows 40 again **(controller)**.
- The table keeps its scroll position and cursor across a `more` click, the way it keeps them across a refresh.
- No keyboard binding (owner: keyboard opening of RECORD details is deferred; the same holds here) **(controller)**.

### 1.7 The `not completed` filter beside the title

The title reads `RECORD · all · not completed · as of 17:33`.
- `all` and `not completed` are both click targets. The active one is bold accent; the inactive one is dim.
- A click calls `screen.record_filter('all')` or `screen.record_filter('open')`, the only two values; the action
  re-validates them.
- **`not completed`** shows every row whose **displayed** state word is not `completed`: pending, failed, rejected,
  cancelled, blocked, or any word the API adds.
  - The displayed state is the one RECORD's state cell already computes: the attempt `status`, except accepted rows
    and rows with no status, which show the job state.
  - Hoist that computation into one pure function, `record_state(row) -> str | None`, in
    `analytics/surf_swarm_signals.py`. Widgets and manager both import it (widgets may import pure analytics).
  - A row whose state is `None` (unread) counts as not completed **(controller)**: it is not known to be completed.
- **Order:** the filter is applied first, then the window. `+N older` counts the filtered rows beyond the window.
- Toggling the filter keeps `record_cap` as it is.
- A filter that leaves no rows shows a dim `no incomplete records` in the footer. That is a real empty, not
  `unavailable`.
- The widen marker and the title's `as of` keep working. The title stays one line at every tier (see WP3).

## 2. Data: the enrichment window follows the view (WP2)

Today answers, oracle panels and job details are read only for `rows[:SWARM_ANSWER_ROW_CAP]` (40). Rows loaded by
`more`, or pulled forward by the filter, would read `not read` forever. That promises a read that never comes.

- **Seam:** `SurfManager.set_record_view(cap: int, open_only: bool) -> None`, modelled on `set_seat`:
  - an attribute write, no I/O, no await
  - it marks `TIER_SWARM_SEAT` due
  - `cap` is clamped to `[SWARM_ANSWER_ROW_CAP, SWARM_ANSWER_CACHE_CAP]`, i.e. 40..400
- **The window:** one pure function, `record_window(rows, cap, open_only) -> list`, in
  `analytics/surf_swarm_signals.py`, used by the manager (eligibility) and the widget (display).
  - It filters first, then applies the window.
  - The widget and the manager call the same function with the same arguments, so they cannot drift.
- **Eligibility:** `answer_jobs_due`, the oracle-panel read and `job_details_due` take the window rows in place of
  `rows[:SWARM_ANSWER_ROW_CAP]`.
- **Per-cycle caps are unchanged:** 4 submission jobs, the oracle page and pair caps, and 2 job details. Rows loaded
  by `more` fill in over the next cycles, and their unread state stays honest (`not read`).
- The cache caps (400 points, 48 h) are unchanged. That is why the window stops at 400.
- **Screen:** on `record_more` and `record_filter`, set the screen state, call `set_record_view`, repaint RECORD from
  the rows it already has, and schedule the normal guarded refresh. **No network await in the handler.**

## 3. Contract (WP0 freezes it)

- `SWARM_WIDGET_SIGNATURES`:
  - `SurfSwarmNodeCards` is removed.
  - `SurfSwarmSeatCards` adds `swarm_seat_node_rows`. It keeps `swarm_seat_teammates`, which COLLAB now reads.
- The screen's PANELS dispatch loses the node-card row. The identity binding test follows.
- `record_state` and `record_window` are exported from `analytics/surf_swarm_signals.py`, each with its own tests.
- No new payload key. No new cache slot. No new clock or degraded group.

## 4. Work packages

**WP0 — contract and pure helpers.**
- The signature change.
- `record_state` and `record_window`, with tests:
  - every state word (pending, failed, rejected, cancelled, blocked, unknown)
  - `None` → not completed
  - an accepted row takes the job state
  - filter then window
  - cap clamping
- RECORD's state cell switches to `record_state` with no visible change; its tests stay green unchanged.
- Commit `feat(surf): freeze record view helpers and merged card contract`.

**WP1 — cards.**
- COLLAB (§1.2) and NODES (§1.3).
- Hoist the honest-number helpers.
- Remove `SurfSwarmNodeCards` and its module, and remove it from `widgets/surf/__init__.py`, `compose`, `PANELS`,
  `_SCROLL_COLUMNS` and the address sweep's AGENT case, as each applies.
- Re-sweep both AGENT pins in situ (§1.5).
- **Tests (composited):**
  - The #420 capture gives COLLAB `261 seats` plus two teammate lines.
  - NODES shows ORACLE, REVIEW, `+2 more` with the fixture's numbers.
  - Exactly 3 nodes: all shown.
  - An unknown key is fitted with `…`.
  - `attempts` None → `—`.
  - Unread and empty lists; pending, never-paired and unavailable gating.
  - The stress payload's `99,999` counts shorten, never cut.
  - No node-card widget in the AGENT DOM.
- **Prove:** make the line rule show 3 of 4 nodes, and name the test that goes red.
- Commit `feat(surf): COLLAB lists top teammates, NODES replaces TEAMMATES, node row removed`.

**WP2 — data window.**
- `set_record_view`, and the three eligibility sites on `record_window`.
- **Tests** (fixtures, fake clock, transport that raises on anything unexpected):
  - `set_record_view(80, False)` makes rows 40–79 eligible, and the per-cycle caps still hold.
  - `open_only` makes an old failed row eligible that is outside the first 40.
  - A cap above 400 clamps.
  - The setter performs no I/O.
  - A seat change resets the manager's view to 40/False, the same seam as `set_seat`.
- **Prove:**
  - Revert one site to `rows[:SWARM_ANSWER_ROW_CAP]`, and name the test that goes red.
  - Remove the clamp, and name the test that goes red.
- Commit `feat(surf): record enrichment follows the view window`.

**WP3 — RECORD.**
- The column order (§1.1), the footer `more` (§1.6) and the title filter (§1.7).
- `SurfScreen.action_record_more` and `action_record_filter`.
- **Tests** (pilot; await observable state, no wall-clock waits):
  - The composited header order is `took tok panel`.
  - Clicking `more` shows 60 rows and the footer's count drops by 20. A last click shows the remainder and the
    footer disappears.
  - A seat change resets to 40.
  - Clicking `not completed` leaves only rows whose composited state is not `completed`, and the title shows it
    active. Clicking `all` restores them.
  - The filter's empty footer.
  - The manager's `set_record_view` receives each change, and the manager records no network call.
  - A forged action argument (`record_filter('x')`) does nothing.
  - The title is not clipped at the tight, compact and full tiers at the AGENT pin, with `‹ widen` honest.
- Re-sweep RECORD's tiers (102/94/53 should not move, because only the order changed) and `RECORD_NEVER_CLEARS_BELOW`.
  Write any change into the `#:` blocks with evidence.
- **Prove:**
  - Break the filter predicate, and name the test that goes red.
  - Make `more` add 19, and name the test that goes red.
- Commit `feat(surf): RECORD tok before panel, more rows, not-completed filter`.

**WP4 — docs.**
- README: the AGENT section and the keys table ("click `more`", "click `all`/`not completed`").
- `rules/surf.md`:
  - the seat-card row
  - NODES, COLLAB, and the node row gone
  - RECORD's column order
  - the window, filter, `set_record_view` and `record_window`
- `docs/decisions.md`: one dated line (row three removed with the facts it carried; RECORD view window).
- Run the doc-pinning tests (`rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`; in zsh, pipe the list through
  `xargs`, because an unquoted variable is not word-split) and `-m guard`.
- Commit `docs(surf): agent cards merged, record view`.

**WP5 — follow-ups file.**
- `docs/surf_agent_record_view_followups.md`: anything found and not done, with its size. This file can be part of the
  WP4 commit.

## 5. Tests to run (named, plus `-m guard`)

```
tests/analytics/test_surf_swarm_signals.py
tests/widgets/test_surf_swarm_seat_record.py tests/widgets/test_surf_swarm_agent_cards.py tests/widgets/test_surf_swarm_seat_state.py
tests/data/test_surf_swarm_models.py tests/data/test_surf_manager_answers.py tests/data/test_surf_manager_oracle.py
tests/data/test_surf_swarm_answers.py tests/data/test_surf_manager_swarm.py
tests/screens/test_submission_detail.py tests/screens/test_oracle_answer.py
tests/screens/test_surf_swarm_layout.py -k "agent or record or oracle or polish"
tests/screens/test_surf_screen.py          (whole file, once, after WP3)
tests/test_address_rule.py tests/test_address_sweep_registry.py tests/screens/test_address_icons_everywhere.py -k surf
tests/screens/test_dashboard_screen.py tests/screens/test_surf_swarm_screen.py tests/widgets/test_surf_widget_contract.py
-m guard
```

## 6. Stop conditions

- The base hash or the fixture check fails.
- The width pin would rise, or the row pin would rise.
- RECORD's tiers 102/94/53 would move.
- A rule here contradicts CLAUDE.md or `rules/*.md`. Report it as a plan defect.
- A named test cannot be made green.
- Anything would need a key, a new endpoint, or network in a test.

## 7. Final report (one)

- Commits (hash and subject).
- Tests and counts.
- Which test went red for each proof.
- Pins before and after, with the sweep evidence.
- What left the screen, including whether `board_body` was deleted.
- Every deviation, with its reason.

After you, the controller runs one task review per WP, a whole-branch review, one fix wave, one scoped re-review
and the full suite once. The owner decides the merge.
