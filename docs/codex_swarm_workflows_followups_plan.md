# Codex plan — SWARM WORKFLOWS follow-ups (written 2026-10-04; rules updated 2026-10-05)

The SWARM WORKFLOWS programme (`docs/surf_swarm_workflows_spec.md`) merged and was pushed to
`origin/main` at `1147b6d` on 2026-10-04. Its close filed **F73–F85** in
`docs/surf_swarm_followups.md` and **#80–#81** in `docs/handover_followups_2026_09.md`. This plan
covers every one of them. Owner decisions are flagged in §9 and are **not** for Codex to make.
Older open items in other follow-up docs are out of scope.

## 0. Read first

1. **`CLAUDE.md` at the repo root is binding**, every line of it. In particular: Hard
   constraints (read-only, keyless, no test touches the network, read values live); Task triage
   (each item below names its tier — follow only that tier's pipeline); Conventions; Tests.
   Where `~/.codex/AGENTS.md` asks for something else (TDD-first is fine; "always dispatch"
   is not), `CLAUDE.md` wins.
2. `.claude/rules/widgets.md` and `.claude/rules/surf.md` (third-party text, address icons and
   links, panels).
3. `.claude/skills/terminal-layout/SKILL.md` before anything that could change how SWARM is sized.
   **None of the items below is expected to move a pin. If a layout sweep reddens, stop and report
   instead of re-pinning.**
4. The item's own entry in the follow-up doc. It holds the evidence; this plan holds the fix.

## 1. Where to work

This brief is for maxpane **`main`**. In your clone, `/Users/banse/codex/maxpane`, run
`git fetch autopull && git switch -c feature/swarm-workflows-followups autopull/main`, and do
every item on that branch. `autopull` is this repo; its `main` is `origin/main` `41691bf` (which
includes the 2026-10-05 test-speed changes to `CLAUDE.md` and `scripts/`) plus this plan's update.

Use the clone's own `.venv/bin/python`. Check once that it imports the clone. Run this from
outside the repo, because `python -c` imports from the current directory first:
`cd /tmp && /Users/banse/codex/maxpane/.venv/bin/python -c "import maxpane_dashboard; print(maxpane_dashboard.__file__)"`.

That venv runs Textual 8.2.8, while the owner's dev venv runs 8.1.1. The 2026-10-05 Linux dry run
passed every layout sweep on 8.2.8 (`docs/handover_followups_2026_09.md`, "CI dry run"). If a
layout result here disagrees with a pin, report it with both versions named; do not re-pin.

## 2. Rules for every item

- **One item, one commit**, made by pathspec (`git commit -- <paths>`). Use `git add` only for a
  brand-new file's exact path. Never `git stash`, `reset`, `restore`, `clean`, or `checkout --`
  a file. **Never merge, push or tag**: you stop at a committed branch, and the owner merges.
- **Tests follow `CLAUDE.md` "Tests", in two steps:**
  - **While editing:** run only the cases that exercise the touched behaviour, by node id or
    `-k`, on the touched test file and on the screen or manager test that composites it. Screen
    runs get `HOME=$(mktemp -d)`. SWARM's composing files are `tests/screens/test_surf_swarm_*.py`.
  - **Once, before each commit:** run the touched test files and the composing screen or manager
    file whole, with `HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist worksteal <files>`.
    Add the fast guard set, `.venv/bin/python -m pytest -m "guard and not mounts_app" tests`.
    `-m mounts_app` is only for a changed binding or key, which no item here makes.
  - **After a doc edit**, also run
    `.venv/bin/python -m pytest -m docpin tests/test_surf_registration.py tests/test_curator_registration.py`.
  - **Never run the full suite**: it runs only when the owner asks or before a tag. Never start a
    second pytest while one is running.
- **Mutation proof** wherever an item says so, with `scripts/mutate.py` (usage in its
  docstring: `--file --old --new --expect <node id> -- <pytest args>`, or `--mutants
  mutants.json`). Only `KILLED` with the named `--expect` test counts. `WRONG TEST`, `SURVIVED`
  and `ERROR` are not proof. Report the script's verdict lines.
- **Measure, never derive.** For any SWARM width or height question, use
  `scripts/measure_layout.py s <payload> WxH` (its docstring lists the forms; payload names are
  `PAYLOADS` in `tests/screens/test_surf_swarm_layout.py`).
- **Assert on composited output** (`render_strips()` or the existing `_render` / `_screen_text`
  helpers), never on a content string.
- **Close the entry as you land it.** In the same commit, mark the follow-up entry
  `CLOSED 2026-MM-DD (<hash>)` with one sentence on how. Append a **Landed** block under the item
  in this file: the commit, the tests run with their counts, and each mutant with the test that
  reddened. The exception is WP2–WP4: they change what a dashboard paints, so their entries
  close only after the owner's live look (§3).
- **No subagents are required.** If you dispatch one anyway, only one writer touches the tree
  at a time.

## 3. Order and stop points

| # | Item | Tier | Severity | Stop after? |
|---|------|------|----------|-------------|
| WP1 | #80 control characters reach the terminal | 2 | Important (security) | **Yes**, final review |
| WP2 | F76 IN FLIGHT prose addresses get no icon | 1 | Important | no |
| WP3 | F80 LAUNCHES `#` cuts four-digit numbers | 0 | Important when reachable | no |
| WP4 | F85 sparklines outside `SparklinePanel` (fwa, curator, surf) | 1 per dashboard | Important | **Yes**, owner's live look |
| WP5 | F74 F75 F77 F78 F79 F81 F82 F83 #81 | 0 each | Minor | **Yes**, end of plan |

**Live look before hardening** (`CLAUDE.md` triage).
1. Commit WP2, WP3 and WP4 as code and tests.
2. Then stop and give the owner the command:
   `cd /Users/banse/codex/maxpane && .venv/bin/python -m maxpane_dashboard --game surf`.
   They look at `s` for IN FLIGHT and LAUNCHES, and at the sparkline panels on fwa, curator and
   surf. Ask once for the owner's terminal size.
3. Live data has no 1000th launch and no failed read, so the look checks that nothing else moved.
4. Fold in any corrections. Then close the three entries, write their Landed blocks, and ask
   for the reviews.

WP1 changes a render only for control characters, which live data does not carry, so it needs
no live stop.

**Reviews** are run by the owner from Claude Code with `CLAUDE.md`'s reviewer contract:
- **WP1 (Tier 2, well under ~1,000 production lines):** no task review. The final review, on
  the most capable model, is the only one. You get one fix wave, and a scoped re-review follows
  only if that fix wave touched production code.
- **WP2 and each WP4 dashboard (Tier 1):** one `sonnet` review each and at most one fix round.
  A re-review follows only if the fix touched production code.
- **Tier 0:** no review.
- **Minor-only findings are filed, not fixed.**

---

## 4. WP1 — #80: strip control characters at the widget boundary (Tier 2, shared widget)

**Defect.** `widgets/markup_safety.flatten` (`:97`) only collapses whitespace
(`" ".join(text.split())`), and Rich's `Text` strips only BEL, BS, VT, FF and CR. An ESC, NUL or C1
CSI in a served string therefore reaches the terminal driver's output. A probe rendered
`"\x1b]0;PWNED"` through a `Text` and found it intact in the output. Whoever controls a displayed
string can inject OSC or CSI sequences: token symbols, IMD objectives and failures, ENS names,
announce posts. The data layer already strips controls for one path (`data/surf_swarm.py:1606`
`_STORED_CONTROLS`, `:1657`), so the precedent exists, but the widget boundary has no general
guard.

**Change.**
1. Add `strip_controls(text: str) -> str` to `widgets/markup_safety.py`. It removes every
   character whose `unicodedata.category` is `Cc` (C0, DEL, C1) **except `\n` and `\t`**. Do not
   strip `Cf`: ZWJ (U+200D) joins emoji sequences. Bidi format characters are F60, an owner
   decision, so leave them alone.
2. Call it inside `flatten` (after `str()`, before the whitespace collapse), `safe_markup` and
   `strip_tags`. `sanitize_cell` inherits it through `flatten`. Check that the order in
   `sanitize_cell`'s docstring still reads true.
3. **Inventory the literal-`Text` sinks** that bypass all three helpers. Find candidates with
   `rg -n "Text\(|Text\.assemble|append\(" maxpane_dashboard/widgets` and keep the ones whose
   argument is third-party. Known ones: WORKFLOWS' text cell (`swarm_workflows._text_cell`);
   IN FLIGHT's template and objective (its docstring at `swarm_inflight.py:10-12` says they avoid
   `sanitize_cell`); feed rows (`widgets/surf/feed.py:507` `_row_text`); tooltips built from served text;
   `address_prose`'s prose. Route each one through `strip_controls` (or `flatten` where it
   already wants one line). List every sink, and what you did with it, in the Landed block.
4. `.claude/rules/widgets.md`, section "Escape every third-party string": add two sentences
   saying that the helpers also drop control characters and that a literal `Text` built from
   served text calls `strip_controls`.

**Tests** (TDD: write them red first).
- `tests/widgets/test_markup_safety.py`:
  - each of `strip_controls`, `flatten`, `safe_markup`, `strip_tags` and `sanitize_cell` drops
    `\x1b`, `\x00`, `\x07`, `\x7f` and `\x9b`;
  - `strip_controls` keeps `\n` and `\t`;
  - an emoji ZWJ sequence and CJK text are unchanged;
  - `[/x]` still renders literally.
- **Render level, on composited output**, one case per sink shape, fed
  `"ok\x1b]0;PWNED\x07\x1b[31mred\x00"`. The output must hold no `\x1b`, `\x00` or `\x9b`, and
  must still show the printable remainder. Shapes:
  - a `DataTable` cell via `sanitize_cell` (e.g. LAUNCHES `repo`);
  - a `Static` via `flatten`;
  - a `RichLog` row (IN FLIGHT);
  - a literal-`Text` cell (WORKFLOWS);
  - one non-surf dashboard (a token symbol on base or ttt).
- **Mutation proof:**
  - drop the call from `flatten`: the unit tests and the `DataTable`/`Static` render cases must
    fail;
  - drop it from WORKFLOWS' sink: that render case must fail.

**Before the commit** (§2): `tests/widgets/test_markup_safety.py`, the widget test file of
every touched sink, their composing screen files, and `tests/screens/test_address_icons_everywhere.py`,
all whole. Then the fast guard set, and the docpin command (step 4 edits a rules file).

**Stop after WP1.** Commit, write the Landed block, and wait for the final review.

## 5. WP2 — F76: IN FLIGHT's prose addresses get the copy icon (Tier 1, surf only)

**Defect.** IN FLIGHT renders a whole 0x address inside an objective or note as plain text, with
no copy icon. That breaks `CLAUDE.md`'s address convention. The E2/E7 sweep misses it only
because no seeded IN FLIGHT objective or note carries an address.

**Change.**
1. WORKFLOWS already does this right (`032e6e7`). Its `_text_cell` runs the surf fitted-prose
   route from `widgets/surf/_icons.py`:
   - `mark_addresses`;
   - `rowfit.clip` to the column on `cell_len`;
   - `keep_units` (an address and its icon are kept whole, or dropped whole in front of the `…`);
   - `unmark`;
   - `link_prose(Text(...), explorer=None)`.

   **Hoist that route into `_icons.py`** as one function, for example
   `fit_prose(text, cols, *, style=None) -> Text`. Make WORKFLOWS call it, and make IN FLIGHT's
   objective and note cells call it too. A helper two modules need is hoisted, never re-declared.
2. `explorer=None`: an IN FLIGHT row carries no chain id, so the address copies but links
   nowhere (the WORKFLOWS precedent).
3. Keep each cell's text semantics:
   - notes are strip-then-escape today (`swarm_inflight.py:211`, `sanitize_cell` →
     `Text.from_markup`), so strip tags before the helper, so that what reads on screen does not
     change except for the icon;
   - objectives stay literal.
4. `tests/address_sweep/builders.py`: seed one whole address in an IN FLIGHT objective and one in
   a note in surf's payload, and list both in the surf case's `unlinked`.

**Tests.**
- Widget test (`tests/widgets/test_surf_swarm_inflight.py`): an address in an objective and an
  address in a note each show the icon on the compositor (`icon_targets`), and neither links
  (`link_targets`).
- A narrow column keeps the address whole or drops it whole before `…`.
- WORKFLOWS' existing tests stay green unchanged. That is the proof the hoist is behaviour-neutral.
- **Mutation proof:** route IN FLIGHT back to its old cells. The new widget test and the
  address-sweep surf case must fail.

**Pin check.** The icon is paid inside the prose budget, so no pin should move.
1. Run `.venv/bin/python scripts/measure_layout.py s <payload> 137:139x35` for every SWARM
   payload, both folds (`--expanded`). From 138 up, every size must read `whole`.
2. Before the commit, `tests/screens/test_surf_swarm_layout.py` runs whole with the rest
   (§2).
3. If anything reddens, stop and report.

## 6. WP3 — F80: LAUNCHES' `#` shows the whole launch number (Tier 0)

**Defect.** `swarm_launches.py:270` formats `launch_number` with `fmt_int`, which groups
thousands. So 1000 becomes `1,000`, five cells in a four-cell column, and the `DataTable` paints
`1,00` with no ellipsis: a wrong number on screen. The `#:` comment at `:80` ("four cells hold
9999") is true only without grouping. Today's highest number is about 62, so this is latent.

**Change.**
- A launch number is an identifier, not a magnitude. Render it as plain digits: the integer
  as a string, or `DASH` when unusable.
- Five or more digits do not fit. Mark such a cell with the base's clipped-cell route
  (`SwarmTableBase._clipped`, set from `build_cells`, which lights `‹ widen`) and show it with a
  visible `…`. Never cut it silently.
- Fix the `:80` comment.
- The footer's counts stay `fmt_int`; they are magnitudes.

**Tests.**
- `tests/widgets/test_surf_swarm_launches.py`, on composited output: 62 → `62`, 1000 → `1000`,
  9999 → `9999`, and 12345 → a visible `…` with `‹ widen` lit.
- **Mutation proof:** put `fmt_int` back. The 1000 case must fail.

## 7. WP4 — F85: the other sparklines tell a failed read from an empty one (Tier 1, one per dashboard)

**Defect.** #34 fixed `widgets/panels.SparklinePanel` only. The sparklines outside the base still
draw a `None` series (a failed read) like `[]` (a real empty one). That is "a failed read in the
real negative's clothes" (`CLAUDE.md` Conventions).

**Step 1: inventory first.** Run `rg -ln "build_sparkline|sparkline_common" maxpane_dashboard/widgets`
and exclude `panels.py` and its subclasses. Expected candidates: `widgets/fwa/fwa_sparkline.py`,
`widgets/curator/sparklines.py`, and surf's market and pool4 sparklines (check
`widgets/surf/pool4_vault.py`, `pool4u_burn.py` and the market panels). For each, record:
- what it paints for `None`, for `[]` and for a non-list;
- what its manager passes when the read fails.

**Step 2: per dashboard, its own commit, in the order fwa, curator, surf.**
- The widget's `None` or non-list paints yellow `unavailable`, reusing `panels.UNAVAILABLE` or
  `UNAVAILABLE_LINE` (never re-declared). `[]` keeps its empty sentence.
- If the manager collapses a failed read to `[]`, **do not change the manager here**. File it as
  a new follow-up (the #75 shape).
- A sparkline that already tells them apart closes with evidence and no code change.

**Tests.** One composited case per widget over `None`, `[]` and a non-list, plus one mutant per
widget (drop the `None` branch; the `None` case must fail). Tests as in §2: while editing, the
widget's cases; before the commit, the widget's test file and the dashboard's composing screen
file, whole.

## 8. WP5 — the Tier 0 items (one commit each, any order)

- **F74: keep the upgrade rule, and say why.**
  - Check that `SurfCache.load` seeds no tier clock and that nothing marks
    `TIER_SWARM_SCORES` fresh before `SurfManager._upgrade_swarm_scores_slot` runs (it is called
    at the end of the cache load).
  - If that holds, the rule only matters if tier clocks are ever persisted. Rewrite the method's
    docstring (`surf_manager.py:1179`) to say so, and close F74 as "kept deliberately".
    The test helper `_warm_cache_with_scores_slot` (`tests/data/test_surf_manager_swarm.py:2045`)
    already says this; leave it.
  - If a path does warm the clock, add a test that drives that path, and close F74 as "not dead".
  - No behaviour change either way.
- **F75: gate skills, launches and sites on `isinstance(…, list)`.**
  - `data/surf_manager.py:6419`, `:6420` and `:6431` gate on `is not None`; workflows at `:6437`
    already gate on `isinstance(…, list)`.
  - Test in `tests/data/test_surf_manager_swarm.py`: a persisted slot with `"skills": {}`
    (and the same for launches and sites) publishes `None`, not `[]`.
  - **Mutation proof:** revert one gate. Its case must fail.
- **F77: WORKFLOWS, a red failure with an embedded address.** In
  `tests/widgets/test_surf_swarm_workflows.py`, a row whose status is not `completed` and whose
  failure embeds a whole address composites the failure in red and the address with its icon and
  no link. Test only.
- **F78: WORKFLOWS' 20-cell text floor.** At a panel width whose budget is under `TIGHT_WIDTH`,
  the text column is exactly `TEXT_MIN_COLS` and clips with `…`. **Mutation proof:**
  `max(TEXT_MIN_COLS, spare)` → `spare` (`swarm_workflows.py:231`) must fail it. Test only.
- **F79: an unreadable workflow entry.**
  - Pin what WORKFLOWS paints for `workflow_rows([{"bogus": 1}])`: expected a row of `--` cells
    and no status. Keep that behaviour; a served entry the read cannot use is shown, not hidden.
  - Assert the footer's status counts do not count it.
  - Test only, unless the pinned behaviour turns out to crash or to show a stale value, in which
    case stop and report.
- **F81: LAUNCHES' tight `repo` cell.** In `tests/widgets/test_surf_swarm_launches.py`: at the
  `tight` tier, the composited `repo` cell ends in `…` and is at most `_TIGHT_REPO_COLS` wide.
  **Mutation proof:** `repo_cols = _REPO_COLS` at every tier (the re-review's mutant G) must
  fail it. Test only.
- **F82: SWARM's whole body at 80 rows.**
  - In `tests/screens/test_surf_swarm_layout.py`, add one test parametrised over `_S_PAYLOADS`
    × `_FOLDS`, like `test_the_swarm_body_is_whole_from_its_pinned_width` (`:746`). Render at
    (`SURF_SWARM_FULL_LAYOUT_COLUMNS`, `_COLUMN_SWEEP_HEIGHT`) and judge with `_check_width`.
  - Assert the same invariants as the 35-row sweep: no hidden column, no horizontal scrollbar,
    no region overflow, no clipped line, no unnamed mark.
  - Mark it like its neighbours (`sweep`).
  - While editing, run only it, with `-k`.
- **F83: stale docstring.** `tests/screens/test_surf_swarm_screen.py:7` still names ROSTER, SEAT
  RECORD and FEEDBACK. Rewrite it from the screen's current `compose`.
- **#81: kwarg typo.** `tests/widgets/test_title_blank_row.py:284` passes `burn_history`, but
  `TTTSparkline.update_data` takes `burns_history`; its `**_kwargs` swallowed the typo. Fix the
  name. Check that `_SERIES` has at least `MIN_POINTS` (2) points so the case draws a real line,
  and assert the composited line is not `unavailable`.

**Stop after WP5.** Report:
- the branch head and the commit list;
- per item: its tier, the tests run with their counts, and the mutants with which test
  reddened;
- every follow-up you filed;
- `git status --short`.

## 9. Not for Codex — owner decisions

Do none of these unless the owner writes the decision into this section.

- **F73. On SWARM at 138×35, pressing `x` reveals nothing without scrolling.** Expanded
  THROUGHPUT needs 15 lines (21 on the extra-states payload). The body clears it only from
  55 rows (73).
  - Options: accept it; grow the expanded top row's floor, which pushes the body into
    scrolling at 35 rows instead; or **show the states and cancel-reason blocks in a popup on
    `x`**, which works at any height. The SUBMISSION and ANSWER popups are the precedent.
  - Controller's recommendation: the popup.
- **F84.** `/workflows` pagination, a workflow detail popup, the SKILLS board (CAPABILITY is
  parked in `SWARM_PARKED_WIDGET_SIGNATURES`), a status-bar hint for `x`, and persisting the fold
  across restarts.
  - The status bar has no slack: it is whole only from 134 columns (F18, F43). Adding an `x`
    hint raises that 134.
- **F60.** Whether `strip_controls` should also drop bidi format characters (U+202A–U+202E,
  U+2066–U+2069).
- **A release tag.** `CHANGELOG.md` `Unreleased` carries this programme and everything since v0.9.3.
- **F55** (optional measurement). Re-measure the hero's SERVICES mixed-state line at the new
  138×35 pin. Its numbers are still the 141×42 ones.
