# Codex plan — SWARM layout v3 (written 2026-10-05)

> **Do not use any superpowers skill** (brainstorming, writing-plans, executing-plans,
> subagent-driven-development, test-driven-development, requesting-code-review, or any other
> `superpowers:*` skill), even where a skill's own trigger says it must run. The superpowers plugin
> is disabled for this project (`CLAUDE.md`, "Task triage"). This plan and `CLAUDE.md` are the
> whole process.

**Tier 2.** The change adds two popups and widens a data contract (workflow history, hero
signature). It edits the shared `widgets/markup_safety.py` and touches more than 6 files. The owner
designed it in chat on 2026-10-05, working from two screenshots of the live SWARM body. Part A is the spec.
Part B is the plan. Estimated production size is under ~1,000 lines. Under `CLAUDE.md`, the
packages therefore get **no task review**: the only review is the final whole-branch review, run from
Claude Code. **Every line number below is a starting point, not a fence: verify it before editing.**

---

## Part A — Spec (the owner's decisions; do not redesign them)

### A1. Layout (SWARM body, key `s`)

Today: hero · `WORKFLOWS | THROUGHPUT` · `IN FLIGHT | LAUNCHES` · `SITES`.
New:

```
hero:  AGENTS · WORKING · ACCEPTED 24h · LAUNCHES · WORKFLOWS · SITES
top:   LAUNCHES (left, takes the rest)      | THROUGHPUT (right, as today)
mid:   WORKFLOWS — full width
bottom: SITES — full width
```

- **IN FLIGHT is parked:** unmounted, with its module, class and tests kept. This follows the
  CAPABILITY precedent: add `"SurfSwarmInFlight": ("swarm_inflight_rows", "swarm_as_of_hhmm",
  "swarm_network")` to `SWARM_PARKED_WIDGET_SIGNATURES` (`data/surf_models.py:1657`). Every
  "mounted / consumed" test takes the exemption from that export, never from a hand-typed copy.
  The jobs read that feeds it stays as it is.
- **The line under each table stays as a blank row.** The footer `Static` (`_swarm_table.py:197`,
  `_write_footer` :321) keeps its row, but LAUNCHES and WORKFLOWS write `""` into it. Their words move
  to the hero (A2). SITES has no footer today and gets none.
- **Row heights are measured, not predicted** (terminal-layout skill). LAUNCHES, WORKFLOWS and
  SITES all scroll inside themselves. Give each a `min-height` floor and decide where the `1fr`
  goes by measurement. The owner's live look (B, WP4 STOP) settles the split.

### A2. Hero cards

QUEUE, BREAKER and SERVICES leave the hero. Three summary cards take their places, in this order:
**LAUNCHES · WORKFLOWS · SITES**. Each card has the existing two body lines. Line 1 is the total,
bold, like ACCEPTED 24h. Line 2 is the per-status counts, largest first, joined by ` · `. Line 2
keeps only the `<n> <status>` pairs that fit **whole** in the box's measured content width
(`_box_width`, `swarm_hero.py:249`). It never cuts a pair mid-word. The box has 19 content cells at
today's pin.

| card | line 1 | line 2 (example from live data) | source |
|---|---|---|---|
| LAUNCHES | `100` | `75 live · 25 parked` | `swarm_launch_summary["by_status"]` + total (today's `build_footer`, `swarm_launches.py:284`) |
| WORKFLOWS | `138` (whole history, A4) | `102 completed · 28 blocked` → whatever fits | `swarm_workflow_rows` (today's `build_footer`, `swarm_workflows.py:244`) |
| SITES | rows the table **shows** (superseded builds hidden, as SITES' filter does) | `90 named · 1 failed` | `swarm_site_rows` |

- **Missing data:** a `None` source shows yellow `unavailable`, as the other cards do. An empty
  list is a real `0`.
- **Move, don't copy, the word builders.** Today's two `build_footer` bodies, plus a new SITES
  one, move to the hero, or to a pure helper both can import (CLAUDE.md "Reuse before you build").
  The SITES count must use the **same** superseded predicate the SITES table uses. Hoist it; do not
  re-declare it.
- **Contract (freeze first, WP2):**
  - `WIDGET_SIGNATURES["SurfSwarmHero"]` (`surf_models.py:1524`) drops `swarm_queue_total`,
    `swarm_breaker`, `swarm_services_up` and `swarm_health_status`. It gains
    `swarm_launch_summary`, `swarm_workflow_rows` and `swarm_site_rows`.
  - `swarm_queue_total` has no consumer left, so remove it from the contract and from the fold.
    This is the controller's choice; the owner can veto it at the plan review.
  - Breaker, services and health move to the title (A3).

### A3. Title alarms (SWARM mode only)

Nothing shows while all is well. When something is bad, append one segment to the screen title
in SWARM mode only. Use the same ` · ` joiner as the degraded groups (`_render_title`, `surf.py:3944`).

- `swarm_breaker` is a dict with `tripped is True` → `⚠ breaker open`.
- `swarm_services_up` names exactly one service `False` → `⚠ <name> down`. Two or more → `⚠ <n>
  services down`. Names come from `SERVICE_NAMES` (`swarm_hero.py:93`); hoist it if the screen needs it.
- `swarm_health_status` is a string other than `"ok"` → `⚠ health <status>`. Sanitise it
  (`sanitize_cell`) and cap it at 12 cells; it is third-party text.
- **Unknown is not bad.** `None`, a non-dict, or an unreported service (`None` state) raises no
  alarm. A failed read is the degraded group's job; check that a failed `/health` already shows
  one, and say so in the evidence.
- **Width.** Measure the title with every alarm lit, plus every degraded group, at the SWARM pin.
  It must not move `WORST_CASE_TITLE_COLUMNS` (`tests/screens/test_surf_screen.py:3502`, 143) or any
  pin. If it would, shorten the words. If no honest short form exists, **stop and ask**.

### A4. WORKFLOWS: whole history in the table, plus a detail popup

- **API (probed live 2026-10-05, keyless):** `GET /workflows?limit=<1..100>` returns newest
  `createdAt` first. `before=<ISO createdAt>` pages back. On 2026-10-05 the whole history was
  138 workflows in 2 pages (375 KB + 61 KB), back to 2026-09-17, growing about 8 a day. Statuses
  seen: completed 102, blocked 28, cancelled 6, **superseded 2** (open vocabulary). Commit a fresh
  two-page capture as a fixture with a MANIFEST entry. No test touches the network.
- **Client:** `SwarmClient.fetch_workflows` (`data/surf_swarm_client.py:292`) gains `before:
  str | None`.
  - Accept only a strict ISO-8601 UTC string (the API's own `createdAt` shape). Send it in
    `params=`, never in the path. Refuse anything else with `None` before any request.
  - Add a history getter that pages: page 1 with `limit=100`, then `before=<last raw createdAt>`.
  - Stop on a short or empty page, on a cursor that does not advance, or at
    `SWARM_WORKFLOW_MAX_PAGES`.
  - Dedupe by `id`.
  - Page-1 failure → `None`. A later page's failure → the pages read so far, logged.
  - Wait `SWARM_INTER_CALL_DELAY` between pages.
- **Manager (the sweep, `surf_manager.py` ~6239–6315, last-good at :6314):**
  - **Cold start:** with no persisted history, or a persisted history not marked complete,
    backfill page by page.
  - **Every sweep:** read page 1 (`limit=100`) and **merge by `workflow_id`** into the persisted
    rows. Fetched rows win. Persisted rows outside the fetched range are kept as last-good.
  - Keep the newest `SWARM_WORKFLOW_HISTORY_CAP` rows (start at 1,000), newest `created_ts`
    first, `None` last.
  - **Known limit, to document:** a workflow's status change after it has left the newest 100 is
    seen only on a later backfill.
  - **Failure:** page 1 failing on a cold start publishes `None`. Page 1 failing with history
    persisted keeps last-good, under the existing `as of` behaviour. Never `[]`; see
    `docs/handover_followups_2026_09.md` #96–#98 for why.
- **Contract:**
  - `SWARM_WORKFLOW_LIMIT = 12` (`surf_models.py:1650`) and its agreement with
    `SurfSwarmWorkflows.ROW_CAP` (`tests/data/test_surf_swarm_models.py:470`,
    `tests/widgets/test_surf_swarm_workflows.py:106`) become the page size (100), the page cap
    and the history cap.
  - Keep one agreement test per constant the widget restates.
  - `swarm_workflow_rows`' row shape does not change (`surf_models.py:2021`).
- **Table:** `SurfSwarmWorkflows` shows every row, newest first, and scrolls inside itself. The
  title keeps its `as of`.
- **Detail popup (new):**
  - **Opening:** Enter on a highlighted row, or a click on a row, opens `WorkflowDetailScreen`, a
    `RecordDetailScreen` subclass (`screens/record_detail.py:15`). It works from a **snapshot** of
    that row (`deepcopy`, like RECORD's popups).
  - **Sections:** status · created / updated · contracts job and frontend job · waiting for
    hosting · objective · failure.
  - **Job ids** render through `job_text(..., explorer=JOB_EXPLORER)`, the same link as RECORD and
    today's WORKFLOWS columns.
  - **Objective and failure** are shown whole and wrapped as literal `Text`. Failure text carries
    `[FAIL: …]` brackets and 0x addresses. Never parse it as markup. Every whole address gets its
    copy icon with `explorer=None` (`_icons.mark_addresses` / `link_prose`, as WP2-F76 did): no
    chain id, so never guess an explorer.
  - **Clicks on job links:** a click on a job-id link inside the table must still open that
    link, not the popup. Verify this on Textual 8.1.1 *and* 8.2.8, because the selection
    behaviour differs (#89).
  - `SwarmTableBase` has no row-select handling today. Add it to WORKFLOWS only, never to the
    shared base.

### A5. `x` opens a popup (F73)

- `x` (SWARM only, as today) opens `ThroughputDetailScreen`, a `RecordDetailScreen` subclass.
  It shows THROUGHPUT's **states** and **cancel-reasons** blocks, today's expanded content
  (`swarm_throughput.py` `_render_view` :408, blocks at :439 / :444), from a snapshot. A
  missing block shows yellow `unavailable`.
- **The inline fold goes:** `set_expanded` (:347), the hidden blocks, `_throughput_expanded`,
  `_apply_throughput_fold` and the `x less` word. THROUGHPUT always shows its short form, and its title
  keeps `x more` as the hint.
- **Fold persistence:** none. The owner dropped it, because nothing is left to remember.

### A6. SITES: wider label, plus a `job` column

- **Label column.** Today it is 13 cells (`_LABEL_COLS`, `swarm_sites.py`). Live labels: median 14,
  max 32. Widen it toward whole labels at the owner's width, taking cells from whichever column the
  measurement says gives least. The tiers (`full` 95 / `compact` 87 / `tight` 69) are re-derived by
  measurement.
- **New `job` column:**
  - Built with `job_text(job_id, JOB_COLS, explorer=JOB_EXPLORER)`, exactly as RECORD
    (`swarm_seat_record.py:381`) and WORKFLOWS (`swarm_workflows.py:177`) do.
  - The link opens `https://explorer.imd.fun/jobs/<id>` (`widgets/explorer.py:200`).
  - Default position: last. The owner moves it at the live look if wanted.
  - Live data: all 100 sites carry a `jobId`. `job_id` is already in `swarm_site_rows`
    (`surf_models.py:2016`).

### A7. Status bar

- `KEY_HINTS` (`screens/surf.py:2537`) becomes `"[dim]x more · 4 pl4 · s swm · a agt · b brd[/]"`.
- The `l` key **stays bound and working**, just unlisted, as `e` already is. The owner removed
  only the hint. Update its `#:` block above, keeping its history: append a dated paragraph,
  never rewrite it.
- **Tests that grep the hint, or depend on the 134-column onset:**
  - `test_surf_screen.py:2555, 4108, 5159`;
  - `test_surf_swarm_layout.py:129, 141, 878, 1038` (`KEY_HINT_PHRASE`), `:1045`
    (`STATUS_BAR_WHOLE_FROM = 134`);
  - `test_surf_swarm_screen.py:226, 800`;
  - `test_surf_launchpad_screen.py:79`;
  - `test_surf_pool4_screen.py:342–389`;
  - `test_surf_pool4_market_layout.py:1401–1450`.
- The hint is shorter, so the onset should fall. **Re-measure it; don't subtract.**

### A8. `markup_safety`: F60 + #100

- **F60:** `_CONTROLS` (`widgets/markup_safety.py:87`) also matches the nine bidi format
  characters U+202A–U+202E and U+2066–U+2069. Keep U+200D (ZWJ joins emoji) and every other
  `Cf`. Update `strip_controls`' docstring. Update the #95 test that pins "exactly Cc": it becomes
  "Cc plus exactly these nine".
- **#100:** `flatten` (:107) collapses again after stripping, so `flatten("a \x1b b") == "a b"`
  with no edge spaces: `" ".join(strip_controls(" ".join(text.split())).split())`. Keep #94: a
  CR/VT/FF/NEL still separates words.
- **Tests:** add a regression case for each, in `tests/widgets/test_markup_safety.py`. Prove both
  with `scripts/mutate.py`.

### A9. Follow-ups this closes or changes

- **Close:**
  - **F55:** closed by removal, since the SERVICES card is gone.
  - **F60.**
  - **F73:** popup.
  - **#100.**
  - **F84:** pagination done as history in the table; detail popup done; status-bar hint done as a
    swap with `l launchpad`; fold persistence dropped by the owner; the SKILLS board **stays open**.
- **IN FLIGHT parked:**
  - Mark F76, F86 and F87 as "IN FLIGHT parked 2026-10-05; applies when it returns".
  - The address sweep's IN FLIGHT seeds (`SURF_UNLINKED` `_SWARM_OBJECTIVE` / `_SWARM_NOTE`,
    `tests/address_sweep/builders.py`) leave with the widget.
  - The surf `s` wide size went 170 → 400 columns for IN FLIGHT. Re-measure it; return it to the
    narrowest size at which every remaining seed renders whole.

---

## Part B — Plan

### B0. Where to work

```bash
cd /Users/banse/codex/maxpane
git fetch autopull && git switch -c feature/swarm-layout-v3 autopull/main   # autopull/main = b4017da
```

The clone's `.venv` runs Textual 8.2.8; the owner's dev venv runs 8.1.1. Run anything
selection- or click-shaped on both. The session exports `NO_COLOR=1`, which turns 18 colour tests
red, so run tests as `env -u NO_COLOR …`.

### B1. Rules (CLAUDE.md, current; read it first)

- **Tests, two steps:**
  - While editing: node ids or `-k` only.
  - Once before each commit: the touched test files and the composing screen file whole, via
    `HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist worksteal <files>`.
  - Plus the guard set: `.venv/bin/python -m pytest -m "guard and not mounts_app" tests`.
  - Plus `-m mounts_app tests/test_surf_registration.py tests/test_curator_registration.py
    tests/test_fwa_guardrails.py`, because `BINDINGS`, `KEY_HINTS` and widget registration
    change here.
  - Plus the doc pins: `-m docpin tests/test_surf_registration.py tests/test_curator_registration.py`.
- **No full suite.** The controller runs it only if the owner asks or before a tag.
- **Mutation proof:** `scripts/mutate.py`. Report which test reddened.
- **Layout:** `scripts/measure_layout.py s <payload> WxH`, run in situ. Sweeps run on boundary
  sets (`tests/screens/_sweeps.py`).
- **CSS:** every screen rule goes into both `SurfScreen.DEFAULT_CSS` and `themes/minimal.tcss`
  (lines 2443–2620), identically.
- **Process:**
  - Commit per WP, with a pathspec.
  - Never merge or push.
  - Touch only your branch.
  - Leave no plan workspace or scratch files in the tree.

### B2. Order and stops

| WP | content | stop |
|---|---|---|
| WP1 | A8 `markup_safety` (F60 + #100) | none; it is independent |
| WP2 | Data contract and data: A2 contract, A4 client and manager, `swarm_queue_total` removal, IN FLIGHT parked | none |
| WP3 | Widgets: A2 hero cards, blank footers, A4 table + row select, A6 SITES, A5 THROUGHPUT fold removal | none |
| WP4 | Screen: A1 layout, A4 / A5 popups, A3 title alarms, A7 status bar | **STOP: the owner's live look** |
| WP5 | Hardening: pins re-swept, `#:` blocks, layout tests, address sweep, docs, follow-ups | then report for the final review |

**The WP4 STOP is hard.**
- Run the app keyless against live data at the owner's terminal size. Ask once if you don't
  know it; their screenshots were about 150×46.
- Show the owner the render, or have them run it in their terminal.
- Wait for their reply in chat before WP5.
- Do **not** re-sweep pins, write `#:` blocks, write docs or close follow-up entries before
  that reply.
- Fold the owner's corrections into WP4 first. Last time this stop was skipped; this time it is
  the only gate before hardening.

### B3. WP1: `markup_safety` (A8)

- **Files:** `widgets/markup_safety.py`, `tests/widgets/test_markup_safety.py`.
- **Mutants:**
  - Drop the bidi range: the new F60 case must redden.
  - Revert the second collapse: the #100 case must redden.
- **Tests:** `test_markup_safety.py` whole, plus the guard set. `markup_safety` is shared, so also
  run `-k` subsets of one consumer's widget file per dashboard that uses `flatten` /
  `sanitize_cell`. A full suite is not needed.
- **Commit:** `fix(markup): strip bidi format characters; collapse after stripping (F60, #100)`.

### B4. WP2: data

1. **Freeze the contract first, in its own commit:**
   - the `WIDGET_SIGNATURES` edits (A2);
   - the parked IN FLIGHT entry (A1);
   - `swarm_queue_total` removed;
   - the workflow constants (A4);
   - the agreement tests updated to read the new exports.
2. **Client:** `before` validation and the paging getter, with fixtures from a fresh two-page
   capture. Test the cases in A4: short page, empty page, stalled cursor, page cap, dedupe,
   page-1 failure, later-page failure, and a refused `before` (path-unsafe / non-ISO).
3. **Manager:** cold backfill, per-sweep page-1 merge, cap, failure semantics. Inject the clock.
   Test every failure path with a transport that raises.
4. **Mutants:**
   - drop the merge (persisted rows lost);
   - drop the cursor-advance guard;
   - publish `[]` on a cold page-1 failure.
- **Tests:** the touched data tests whole, plus the swarm manager / models files, plus the guard set.

### B5. WP3: widgets

- **Hero:** three cards (A2), whole-pair fitting, yellow `unavailable` for `None`, `0` for `[]`.
  Composited tests (`render_strips()`) for each card at the pin width and at a narrow width.
- **Footers:** LAUNCHES and WORKFLOWS write `""`. Their row remains; test the row exists and is blank.
- **WORKFLOWS:** the whole list, plus row select (Enter / click) posting a message the screen
  handles. A click on a job link opens the link, not the popup. Test the click on 8.1.1 and 8.2.8.
- **SITES:** the wider label and the `job` column (A6). Test the link target with
  `tests/widgets/address_probe.py` `link_targets`.
- **THROUGHPUT:** the fold removed (A5); its blocks rendered by a function the popup can call.
- **Mutants (one per behaviour):**
  - a card cutting mid-pair;
  - a footer still written;
  - SITES `job` without its explorer;
  - Enter not posting the message.

### B6. WP4: screen (then STOP)

- **Layout:** `compose()` (`surf.py:3402`) and the CSS in both places (A1). Mount IN FLIGHT
  nowhere.
- **Popups:**
  - `x` → `ThroughputDetailScreen`.
  - The WORKFLOWS row message → `WorkflowDetailScreen`.
  - Both use snapshots and push through `app.push_screen`, as `_open_record_detail` does
    (`surf.py:4018`).
  - No network await in a message handler.
- **Title alarms** (A3). **`KEY_HINTS`** (A7).
- **Tests:** `-k` while editing; the composing SWARM screen file(s) whole before the commit.
- **Then the STOP in B2.**

### B7. WP5: hardening (after the owner's reply)

1. **Re-sweep the SWARM pins:**
   - Use `scripts/measure_layout.py s <each _S_PAYLOADS> lo:hi x rows`, with the range centred
     on the new numbers, never starting at the pin.
   - Update `SURF_SWARM_FULL_LAYOUT_COLUMNS` / `_ROWS` (`surf.py:1666`, `:1739`) and their `#:`
     blocks. Append dated paragraphs; never rewrite one.
   - Retire `INFLIGHT_NEVER_CLEARS_BELOW` (`test_surf_swarm_layout.py:117`) with IN FLIGHT.
   - Re-measure `LAUNCHES_NEVER_CLEARS_BELOW` / `LAUNCHES_HIDES_NO_COLUMN_FROM` in LAUNCHES' new
     container.
   - Add any new SITES / WORKFLOWS onset to the boundary set.
2. **Status-bar onset** (A7): re-measure; update every test listed there.
3. **Address sweep** (A9).
4. **Docs:**
   - `.claude/rules/surf.md` SWARM section.
   - `README.md`: the `s` paragraph, the `x` sentence, and `l` (still works, no longer
     listed).
   - The terminal-layout `SKILL.md` pin table, SWARM row.
   - `CHANGELOG.md` Unreleased.
   - Closings in `docs/surf_swarm_followups.md` and `docs/handover_followups_2026_09.md` (A9).
   - Every new doc-reading test carries `@pytest.mark.docpin`.
5. **Report** the branch head, per-WP evidence (tests, mutants, measurements) and the live-look
   corrections taken. Then **stop for the final review**, which is run from Claude Code.

### B8. After the final review

- **One fix wave**, for Critical and Important findings only. Minor findings are filed, not
  fixed.
- A scoped re-review follows only if the fix touched production code.
- Merge and push are the owner's.
