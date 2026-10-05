# Codex plan — SWARM WORKFLOWS follow-ups (written 2026-10-04; rules updated 2026-10-05)

> **Do not use any superpowers skill** (brainstorming, writing-plans, executing-plans,
> subagent-driven-development, test-driven-development, requesting-code-review, or any other
> `superpowers:*` skill), even where a skill's own trigger says it must run. The superpowers
> plugin is disabled for this project (`CLAUDE.md`, "Task triage"). This plan and `CLAUDE.md`
> are the whole process.

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

**Landed — 2026-10-05 (WP1 only, Tier 2; owner review Approved: 0 Critical, 0 Important, 5 Minor).**

Commit: `fix(widgets): strip terminal controls at widget boundaries`. This block belongs to
that same commit; resolve its hash with
`git log -1 --format=%h --grep='^fix(widgets): strip terminal controls at widget boundaries$'`.
The handoff reports the resulting hash (a commit cannot embed its own hash).

`strip_controls` removes all Unicode `Cc` except newline/tab and preserves `Cf`, including
ZWJ and the owner-deferred bidi characters. `flatten`, `safe_markup`, `strip_tags`, and
`sanitize_cell` now share that boundary. Layout pins remain unchanged. The rules file now requires the boundary for literal `Text` as well as markup.

Literal-`Text` inventory (`rg -n "Text\\(|Text\\.assemble|append\\(" maxpane_dashboard/widgets`):

| Sink | Disposition |
|---|---|
| `address._clean_label` → `address_text` labels/invalid-address fallback, `job_text` invalid-id fallback, `site_text` labels | Reuse `flatten` before fitting; copy glyph removal retained. |
| `address.address_prose` | `strip_controls` before address matching and span construction. |
| `address.hash_text` invalid-hash display | Strip display controls; link validation still uses the original input. |
| Bakery `activity_feed._format_event`: title, description, linked bakery name | `strip_controls` before literal appends. |
| Cattown `ct_activity_feed._catch_to_text`: species | `strip_controls`; fisher/name uses `address_text`. |
| OCM `ocm_activity_feed._event_to_text`: token id, count, unknown event type | `strip_controls`; event-type dispatch still uses the original value. |
| TTT `ttt_activity_feed._fmt_burn`: token id | `strip_controls`; symbol already uses `safe_markup`, actor uses `address_text`. |
| FWA `fwa_activity_feed._token_label`: nonnumeric token label | `strip_controls` before fitting; collection/purchaser names already use `address_text`. |
| FWA `fwa_signals._fmt_drift`: value and indicator | `strip_controls` before literal prose/address composition. |
| FWA `fwa_settlement_table._render_crown`: rank prefix | `strip_controls` before measuring/fitting; holder already uses `address_text`. |
| Curator `list_hero._wallet_title`, `_compact_filter_summary` → `_wallet_text` | `flatten` for ENS title; `strip_controls` for filter clauses before measuring. |
| Curator `wallet.CuratorWalletAddress._render_view`: ENS/non-address facts | `strip_controls` before measuring/appending. |
| SURF `activity._row_fields` → `_row_text`: known-counterparty label | `strip_controls` before the row budget; other counterparties already use `address_text`. |
| SURF `signals._signal_detail` → `_signal_row_content`: detail containing an address | Reuse `flatten` before marking/fitting; the no-address path already uses `safe_markup`. |
| AGENT `swarm_agent_cards._runtime_body`: latest-version and fleet-daemon tooltips | `strip_controls` on both literal tooltip lines. |
| WORKFLOWS `_text_cell`: failure / first-sentence objective | Already calls `flatten` on both branches; inherits the fix, no duplicate sanitization. |
| IN FLIGHT `_cell`: template, role/state, objective | Already calls `flatten`; note uses `sanitize_cell`. Inherits the fix. |
| SURF feed `_row_text` / `_row_line_texts` | Served message/label already crosses `safe_markup` in `_item_lines` before Rich parsing; inherits the fix. |
| SWARM hero breaker/health, throughput rollup names, AGENT identity/model/effort/node labels and model/node tooltips, FLEET mixed-value labels, LAUNCHES artifact names, RECORD filter labels/summary and oracle figures | Already cross `flatten`, `strip_tags`, `sanitize_cell`, or `short_model` (which uses the same helpers); inherit the fix. |
| Other address-bearing feeds, hero cards, tables and Curator signal identities | Already use the shared address helpers above; inherit label/fallback protection. |
| Remaining `Text` / append candidates | Constants, numeric/date formatters, validated seat ids/UUIDs/addresses, strict `source_clock` HH:MM, manager-generated clocks, allowlisted network words, already-parsed safe `Text`, or list-building rather than rendered text. No additional served-text bypass found. |

Validation (Python 3.13.12, Textual 8.2.8; owner's dev Textual is 8.1.1):

- Red first: 330 failures / 4 passes across the initial helper and render cases. The two
  later address/hash-counterparty cases and two signal/rank cases also failed before their fixes.
- Focused green: 334 passed (initial shapes); 336 passed (expanded sinks/tooltips);
  334 passed (final focused controls plus updated import guard).
- First whole-file run: 2,435 passed / 19 failed. Eighteen colour assertions saw greyscale
  because this session exports `NO_COLOR=1`; one import guard needed the newly required
  pure `markup_safety` dependency. The apparent layout-file failure passed all geometry
  assertions and failed only colour; it reproduced serially and passed with `NO_COLOR` unset.
  No layout sweep or pin failed. The final validation unsets `NO_COLOR` only for the test process.
- Final whole-file validation: **2,545 passed** in 534.01 s (four workers, `worksteal`).
- Fast guard set: **120 passed**, 11,667 deselected (`-m "guard and not mounts_app" tests`).
- Doc pins: **12 passed** (`-m docpin tests/test_surf_registration.py tests/test_curator_registration.py`).
- No full-suite run. No live stop is required for WP1 by §3.

The final whole-file command (the initial command omitted `test_surf_widgets_a.py` and kept `NO_COLOR`):

```bash
env -u NO_COLOR HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist worksteal \
  tests/widgets/test_markup_safety.py \
  tests/widgets/test_address.py \
  tests/widgets/test_activity_feed_degradation.py \
  tests/widgets/test_hidden_shared_address_icons.py \
  tests/widgets/test_cattown_talismans_address_icons.py \
  tests/widgets/test_curator_widgets.py \
  tests/widgets/test_curator_address_icons.py \
  tests/widgets/test_fwa_widgets_a.py \
  tests/widgets/test_fwa_widgets_b.py \
  tests/widgets/test_fwa_address_icons.py \
  tests/widgets/test_surf_widgets_a.py \
  tests/widgets/test_surf_widgets_b.py \
  tests/widgets/test_surf_address_icons.py \
  tests/widgets/test_surf_swarm_agent_cards.py \
  tests/widgets/test_surf_swarm_workflows.py \
  tests/widgets/test_surf_swarm_launches.py \
  tests/widgets/test_surf_swarm_inflight.py \
  tests/widgets/test_ttt_widgets.py \
  tests/widgets/test_ttt_address_icons.py \
  tests/widgets/test_base_address_icons.py \
  tests/screens/test_surf_swarm_screen.py \
  tests/screens/test_surf_swarm_layout.py \
  tests/screens/test_surf_screen.py \
  tests/screens/test_curator_screen.py \
  tests/screens/test_fwa_screen.py \
  tests/screens/test_base_terminal_screen.py \
  tests/screens/test_dashboard_screen.py \
  tests/screens/test_address_icons_everywhere.py
```

Required mutation verdicts from `scripts/mutate.py`:

```text
KILLED     flatten boundary  (maxpane_dashboard/widgets/markup_safety.py)
KILLED     WORKFLOWS failure boundary  (maxpane_dashboard/widgets/surf/swarm_workflows.py)
```

The first removed `strip_controls` from `flatten`; named red tests:
`test_markup_safety.py::test_helpers_drop_controls[\x1b-flatten]`,
`test_markup_safety.py::test_flatten_static_drops_controls`, and
`test_surf_swarm_launches.py::test_repo_cell_drops_controls_before_fitting`.
The DataTable case includes C1 NEL between printable characters as well as the required OSC/CSI
payload: it proves removal happens before whitespace folding, even though later helpers also
strip controls. The second replaced WORKFLOWS' existing failure `flatten` call with raw `str`;
`test_surf_swarm_workflows.py::test_failure_cell_drops_controls` failed. Both mutants restored
byte-for-byte. The inventory corrects the brief's assumption that WORKFLOWS, IN FLIGHT and the
SURF feed bypass all three helpers: they already used them.

**Owner follow-up — 2026-10-05.** Review findings filed as #92–#95 in
`ab4ccc2`; #92/#93 remain open. The owner approved continuing WP2–WP5 and explicitly
superseded WP1 step 2: collapse whitespace before stripping remaining controls.
This preserves word boundaries for CR/VT/FF/NEL and U+001C–U+001F; the earlier
DataTable mutation-order expectation above is historical.

**Landed — #94/#95 correction (Tier 2, shared widget).**
Commit: `fix(widgets): preserve control whitespace and speed up stripping`.
`strip_controls` uses the equivalent C0/DEL/C1 regex, preserving newline/tab and Cf.
Local 6 KB flatten benchmark: 485.8 → 46.0 µs (best of five × 1,000 calls).
Red first: 27 failed / 308 passed. Focused green: 335 passed.
Whole touched/composing files: **581 passed**; fast guards: **120 passed**;
doc pins: **12 passed**. No full suite.

`scripts/mutate.py`: **KILLED whitespace order**; named red tests:
`test_flatten_collapses_whitespace_before_stripping_controls`,
`test_flatten_static_drops_controls`, and `test_repo_cell_drops_controls_before_fitting`.
The mutant restored byte-for-byte. No layout pin changed.

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

**Owner-approved exception — 2026-10-05.** All four payloads are whole at
138–139×35 collapsed. Expanded, each shows only `‹ taller` there (F73);
`capture` reproduces this on pre-WP2 `df9272f`. The owner approved continuing
WP2–WP5 with that existing height limitation and every pin unchanged.
Measured on Textual 8.2.8; the owner's dev version is 8.1.1.

**Landed — F76 (Tier 1), 2026-10-05.**
Commit: `fix(surf): add copy icons to in-flight prose` (same-commit title).
Shared `fit_prose` preserves WORKFLOWS behavior; IN FLIGHT objectives remain
literal, notes strip tags, and whole address/icon units copy without guessed links.
The address sweep seeds both fields; its SWARM wide pass uses 400 columns to
show both units, retaining the original 170-column pass and every layout pin.
Live keyless SURF shown to the owner at **200×48**; owner approved continuing.
Focused: **13 passed**; seeded SURF sweep: **1 passed**. Whole touched/composing
files plus layout/address sweeps: **779 passed** (340.37 s, four workers).
Fast guards: **120 passed**; doc pins: **12 passed**.
`scripts/mutate.py`: **KILLED IN FLIGHT old prose cells**, reddening
`test_prose_addresses_copy_without_links_and_drop_whole_when_tight` and
`test_every_rendered_address_carries_an_icon_that_copies_it_and_a_link_that_opens_it[surf-wide]`.
Owner-run Tier 1 review remains pending.

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

**Landed — F80 (Tier 0), 2026-10-05.**
Commit: `fix(surf): render launch identifiers without grouping` (same-commit title).
Plain integer identifiers fit through 9999; larger values visibly clip with
`…` and light `‹ widen`. Unusable values render the dash; footer counts retain
grouping. Live keyless 200×48 SURF shown before the column comment update.
Red first: the 1000 case painted `1,00`; focused green: **1 passed**.
Whole widget/composing screen: **130 passed**; fast guards: **120 passed**;
doc pins: **12 passed**. No pin moved.
`scripts/mutate.py`: **KILLED m1** (restore `fmt_int`), named red test
`test_launch_numbers_are_plain_identifiers_and_overflow_is_marked`.

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

**Inventory — 2026-10-05 (before WP4 fixes).**

| Widget | None / empty list / non-list | Manager on failed read |
|---|---|---|
| `FWASparkline` | waiting / waiting / waiting, unless availability flag is false | cached history or `[]`, flag from truthiness; #96 |
| `CuratorSparklines`, each row | waiting / waiting / waiting | retained cached series or `[]`; #97 |
| `SurfMarket`, price and supply | waiting / waiting / waiting | retained cache or `[]`; #98 |
| `SurfPool4Ratchet`, reserve beside healthy scalars | no spark / no spark / no spark | unknown network `None`; known network cached list, possibly empty |
| `SurfPool4UBurn` | unavailable / quiet-window sentence / empty dict treated as quiet (uniterable input already unavailable) | unread flow `None`, successful empty flow `[]`, last-good rows retained |
| Legacy Frenpet trends and velocity | missing histories collapsed to no-data/empty bars; malformed nonempty histories unchecked | cache-backed series; filed #99 outside the three prescribed dashboards |

`pool4_vault.py` only mentions the helper in documentation; it draws no sparkline.
Migrated Bakery, Base, OCM, Cattown, DOTA, Talismans and TTT classes inherit
`SparklinePanel`; formatter-only matches (`_fmt`, SWARM fleet/sites/seat,
DOTA hero) draw no sparkline and are excluded.

**Landed — F85/FWA (Tier 1), 2026-10-05.**
Commit: `fix(fwa): distinguish unavailable sparkline history` (same-commit title).
Missing/non-list history paints yellow unavailable; empty lists retain waiting.
Shared `panels.UNAVAILABLE` supplies the unavailable word/style. Live keyless
200×48 shown: price chart and 100 candles render. Manager follow-ups #96–#98 and
legacy widget follow-up #99 filed; their implementations are outside this fix.
Red first: **3 failed / 1 passed**; focused green: **4 passed**.
Whole widget/composing screen: **55 passed**; fast guards: **120 passed**;
doc pins: **12 passed**. `scripts/mutate.py`: **KILLED m1**, named red
`test_sparkline_failed_series_is_yellow_and_empty_still_waits[none]`
(and `[non-list]`). Owner-run Tier 1 review remains pending.

**Landed — F85/curator (Tier 1), 2026-10-05.**
Commit: `fix(curator): distinguish unavailable trend history` (same-commit title).
Each failed/non-list series paints shared yellow unavailable independently;
the other healthy row remains visible, and empty lists still wait.
Live keyless History shown at 200×48; failed log reads demonstrated #97's
upstream empty-list limitation. Red first: **4 failed / 2 passed**;
focused green: **6 passed**. Whole widget/composing screen: **668 passed**;
fast guards: **120 passed**; doc pins: **12 passed**.
`scripts/mutate.py`: **KILLED m1**, named red
`test_failed_trend_series_is_yellow_and_empty_still_waits[volume_series-none]`;
both rows' missing and non-list cases reddened. Owner-run Tier 1 review pending.

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

**Landed — F85/SURF (Tier 1), 2026-10-05.**
Commit: `fix(surf): distinguish failed sparkline histories` (same-commit title).
MARKET and RATCHET use shared yellow unavailable for missing/non-list history.
BURN & SUPPLY already distinguished None from empty; its non-list flow now
takes the unavailable route too. Empty-list wording and chart formatting stay intact.
Live keyless default, `e` and `4` views shown at 200×48: successful histories
draw price, supply, reserve and burn charts. No layout pin moved.
Red first: **6 failed / 4 passed**; focused green: **10 passed**.
Whole three widget files plus default/pool4/pool4-market composing screens:
**538 passed**; fast guards: **120 passed**; doc pins: **12 passed**.
`scripts/mutate.py` verdicts (all restored byte-for-byte):
- **KILLED MARKET history boundary**:
  `test_market_failed_series_is_yellow_and_empty_waits[none]`.
- **KILLED RATCHET history boundary**:
  `test_ratchet_failed_series_is_yellow_and_empty_has_no_spark[none]`.
- **KILLED BURN failed flow as empty**:
  `test_burn_failed_series_is_yellow_and_empty_is_quiet[none]`.
Owner-run Tier 1 review remains pending.

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

**Landed — F74 (Tier 0), 2026-10-05.**
Commit: `docs(surf): clarify the deliberate scores upgrade rule`.
Confirmed `SurfCache.__init__` starts with empty tier clocks, `load` restores no
clock, and the manager calls the upgrade immediately after load with no warm-up.
Kept deliberately; only the method docstring changed. Whole manager test file:
**131 passed**; fast guards: **120 passed**; doc pins: **12 passed**.
No mutation required for a comment-only change.

**Landed — F75 (Tier 0), 2026-10-05.**
Commit: `fix(surf): reject non-list persisted score routes`.
Three list gates now match workflows. Tests write and reload real cache files
for each route's dictionary and empty list, including failed summary suppression.
Red first: **3 failed**; focused green: **3 passed**; whole manager file:
**134 passed**; fast guards: **120 passed**; doc pins: **12 passed**.
`scripts/mutate.py`: **KILLED m1**, named red
`test_persisted_non_list_routes_publish_none_but_empty_lists_survive[skills]`.

**Landed — F77 (Tier 0, test only), 2026-10-05.**
Commit: `test(surf): cover red failures with embedded addresses`.
`test_red_failure_and_embedded_address_render_together_without_a_link` reads
the failure and address colors, copy target and link absence from the compositor.
Focused: **1 passed**; whole widget/composing screen: **132 passed**;
fast guards: **120 passed**; doc pins: **12 passed**. No mutation mandated.

**Landed — F78 (Tier 0, test only), 2026-10-05.**
Commit: `test(surf): pin the workflow text column floor`.
A measured widget budget below `TIGHT_WIDTH` retains a 20-cell column;
scrolling to its end exposes the composited 19-character prefix plus ellipsis.
Focused: **1 passed**; whole widget/composing screen: **133 passed**;
fast guards: **120 passed**; doc pins: **12 passed**.
`scripts/mutate.py`: **KILLED m1** (`max(TEXT_MIN_COLS, spare)` → `spare`);
named red `test_text_floor_clips_below_the_tight_budget`.

**Landed — F81 (Tier 0, test only), 2026-10-05.**
Commit: `test(surf): cover the tight launch repository cell`.
Focused: **1 passed**; whole widget/composing screen: **131 passed**;
fast guards: **120 passed**; doc pins: **12 passed**.
`scripts/mutate.py`: **KILLED m1** (always use `_REPO_COLS`);
named red `test_tight_repo_cell_fits_its_column_with_a_visible_ellipsis`.

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
