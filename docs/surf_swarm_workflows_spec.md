# Surf SWARM WORKFLOWS, THROUGHPUT fold, AGENT MODEL card, sparkline `unavailable` — spec and plan

Owner request 2026-10-03: "for F16: collapse THROUGHPUT's state and cancel-reason blocks behind a
key; F51: hide CAPABILITY widget on SWARM and add workflows instead. dont delete CAPABILITY widget
but park it for a later to build SKILLS board. F54: replace the content of the SCORE card with LLM
model info (advertised_model / advertised_effort). fix those together with #34". The design below
was presented in chat the same day. The owner answered "go with your recommendations": `x`, collapsed
by default, and MODEL read from the seat's own `/seats` record.

Tier 2: a new widget and contract keys, a shared `widgets/panels.py` change, two surf bodies and
seven sparkline dashboards, and more than six files. Branch `feature/surf-swarm-workflows`, cut from `fa2bde6`.
Follow-ups this closes: F16 (SWARM half), F23, F47, F51 and F54 in `docs/surf_swarm_followups.md`,
plus #34 in `docs/handover_followups_2026_09.md`.

## 1. THROUGHPUT folds its rollups behind `x` (F16; closes F23 and F47)

* **The key.** `x` on SWARM toggles THROUGHPUT's `states` and `cancel reasons` blocks. It is a
  no-op on every other body.
  * Free on this screen: `r l e 4 s a i b o O f escape`.
  * Free in the app: `q t tab m`.
  * Free in `DataTable`'s own bindings. The implementer verifies this, never assumes it.
* **State.**
  * The state lives on the screen instance, in memory. It is never written to `config.toml`.
  * **The default is collapsed.**
  * It survives refreshes and body switches (`s` → `a` → `s` keeps it).
* **Widget API.** `SurfSwarmThroughput.set_expanded(expanded: bool)`.
  * A non-bool is ignored.
  * It repaints from the stored payload; no data is needed.
  * The widget's own default stays **expanded**, so nothing changes until the screen applies its
    state (WP4 → WP5 sequencing).
* **Collapsed.**
  * The states block, the cancel-reasons block and the blank separator line above them are not
    painted (`display: none`, not empty lines).
  * The panel is its title, the blank row and the fixed rows: window, durations, completed 24h.
  * Title: `THROUGHPUT · as of HH:MM · x more`, with `· stale` before the hint when it applies.
* **Expanded.** The blocks show as today and the title ends `· x less`.
  * Both hints are the same 6 cells, so the title width does not move on a toggle.
  * The hint is never clipped. At the SWARM column pin it is whole in every title state: marker
    present, `stale` true. If the title cannot fit whole, the text before the hint clips with `…`.
    Arithmetic says `THROUGHPUT · as of 17:45 · stale · x more` is 41 cells; the implementer
    **measures**.
* **The row pin is measured collapsed.**
  * `#surf-swarm-top`'s floor equals THROUGHPUT's collapsed composited height (floor = content,
    terminal-layout skill).
  * `test_the_top_row_floor_is_its_auto_height_panels_own_lines` keeps binding the floor.
  * `SURF_SWARM_FULL_LAYOUT_ROWS` is re-swept on every payload. Expect about 36–38 rows; quote the
    measurement, not this guess.
* **Expanded may need more rows than the pin.**
  * No line may be lost in silence. Either the body scrolls with `‹ taller` lit, or the top row
    grows with THROUGHPUT.
  * `test_no_height_loses_a_row_of_either_body_in_silence` (or a sibling) gains the expanded
    state.
  * It also gains F47's canned regression: a payload with more states than the capture.
  * With the default collapsed, the pin no longer depends on the state vocabulary. That is F23's
    "bind the pin" option, met by construction.
* **`completed 24h accumulating since HH:MM` wraps today.** It is one of the capture's sixteen
  lines.
  * Measure it at THROUGHPUT's width at the new pin.
  * If it still wraps, it costs the collapsed pin a row. Shorten the value to
    `counting since HH:MM` (`ACCUMULATING_WORD = "counting"`), per the skill's "shorten the value"
    rule. Otherwise leave it.

## 2. WORKFLOWS replaces CAPABILITY on SWARM (F51)

### Source

`GET /workflows?limit=12` on the swarm host pool. It is keyless and read-only, and sends
`cache-control: public, max-age=30`.

Probed 2026-10-03 (`tests/fixtures/surf/swarm/v6/`):

* **Envelope:** `{count, workflows[]}`, newest `createdAt` first.
  * `count` is the page size, never a total.
  * The default page is 100 rows and 372,677 bytes. `limit=12` is 29,253 bytes.
  * A `before=<ISO createdAt>` cursor exists and is not used.
* **Row keys:** `id`, `objective`, `status`, `failure`, `contractsJobId`, `frontendJobId`,
  `waitingForHosting`, `createdAt`, `updatedAt`.
  * `objective` is free text up to about 6 KB, usually one paragraph.
  * `status` is open vocabulary. The 100-row page holds 80 completed, 19 blocked, 1 cancelled.
  * `failure` is a str or null; it is non-null on all 20 non-completed rows.
  * `contractsJobId` is a UUID, never null in 100 rows.
  * `frontendJobId` is a UUID or null (null in 16 of 100).
  * `waitingForHosting` is a bool.
* **Real failure text carries square brackets and addresses.** It contains
  `[FAIL: project constructor failed] setUp() (gas: 0)`, and two failures embed a 0x address.
* **`/launches` carries no job id.** Nothing joins a workflow to its launch.

### Data (`data/`)

* **Client.** `SwarmClient.fetch_workflows(limit=SWARM_WORKFLOW_LIMIT) -> list[dict] | None`.
  * Parameters go through `params=`, never a `?` in the path.
  * `limit` must be a strict `int` in 1..100. Anything else returns `None` before any request.
  * The body's `workflows` must be a list, else `None`. `[]` passes as a real empty page.
  * The module docstring and the tests that pin "only oracle getters carry parameters"
    (`test_the_jobs_request_carries_no_query…`, `test_a_path_with_a_query_string_is_refused…`)
    name `/workflows` as the one other parameterised getter.
* **Contract** (`data/surf_models.py`):
  * `SWARM_WORKFLOW_LIMIT = 12`. An agreement test binds it to `SurfSwarmWorkflows.ROW_CAP`;
    `data/` never imports a widget.
  * `SWARM_KEYS += "swarm_workflow_rows"`, a `list[dict] | None`:
    * `None` = the read failed or never happened;
    * `[]` = a real empty page.
  * `SURF_ROW_KEYS["swarm_workflow_rows"] = ("workflow_id", "status", "contracts_job_id",
    "frontend_job_id", "objective", "failure", "created_ts", "updated_ts", "waiting_for_hosting")`.
* **Fold.** `surf_swarm.workflow_rows(workflows) -> list[dict]` (the LAUNCHES fold's shape).
  * One row per mapping, exactly the row keys.
  * Strings are raw `_str` values; escaping is the widget's job.
  * Timestamps go through `_ts`. `waiting_for_hosting` is a strict bool, else `None`.
  * Rows are ordered newest `created_ts` first.
  * No truncation in `data/`: the data layer also serves web frontends.
* **Manager.**
  * `_pool_swarm_scores` asks `fetch_workflows` after `fetch_sites`, guarded on its own (R-B:
    partial success is success). The payload gains `"workflows"`.
  * It is not asked when the tier fails early (`/jobs` unread, or a busy detail host), exactly
    like skills, launches and sites.
  * `_swarm_scores_keys` publishes `sw.workflow_rows(wf) if wf is not None else None`.
* **Upgrade: never a false degradation.**
  * A `SLOT_SWARM_SCORES` persisted before this change has no `"workflows"` key. That means "never
    read", not "read failed".
  * When the last-good slot lacks the key, the manager makes `TIER_SWARM_SCORES` due on the next
    cycle. Otherwise the panel would say `unavailable` for up to 30 minutes after an upgrade.
  * Pin this with a test.
* **Docs.**
  * `docs/imd_swarm_api.md` gains a `/workflows` section with the probe facts above.
  * `docs/surf_PRD.md` §5 gains the key (`tests/data/test_surf_models.py` reads it).

### Widget `SurfSwarmWorkflows` (`widgets/surf/swarm_workflows.py`)

* **Basics.**
  * A `SwarmTableBase` subclass.
  * `TITLE = "WORKFLOWS"`, `TABLE_ID = "surf-swarm-workflows-table"`.
  * `ROW_CAP = 12`, `CURSOR_TYPE = "row"`.
  * `EMPTY_LINE = None`: degraded words stay in the table, as in LAUNCHES. The empty word is
    `no workflows`.
* **Signature:** `update_data(swarm_workflow_rows=None, swarm_scores_as_of_hhmm=None, **_kwargs)`.
* **Columns.**

  | key | header | cells | content |
  |---|---|---|---|
  | `when` | `when` | 11 | `mmdd_hhmm(created_ts)`, `--` when `None` |
  | `status` | `status` | 9 | `sanitize_cell`; colour on the **raw** word (below) |
  | `contracts` | `contracts` | 9 | `job_text(contracts_job_id, 8, explorer=JOB_EXPLORER)` |
  | `frontend` | `frontend` | 8 | `job_text(…)`, or a dim `—` for `None` (no frontend job) |
  | `text` | `objective / failure` | ≥ 20, elastic | below |

  * Status colours: `completed` green, `blocked` red, `cancelled` dim, anything else yellow.
  * The text column takes every spare cell above its 20-cell floor (LAUNCHES' `column_plan`
    shape).
* **The text cell.**
  * A row whose status is not `completed` and whose `failure` is a non-empty string shows the
    failure, in red.
  * Every other row shows the objective's **first sentence**: flattened, then cut after the first
    `.` followed by whitespace or the end, then fitted with `rowfit.clip` (`cell_len`).
  * The cell is a pre-built `rich.text.Text`, so the text renders literally. **Not**
    `sanitize_cell`: its `strip_tags` would delete `[FAIL: project constructor failed]`, the
    failure's own words. This is IN FLIGHT's objective precedent.
  * A clipped text cell shows its `…` and does **not** light `‹ widen`; that is also IN FLIGHT's
    objective precedent. Only a shed column lights the marker.
* **An embedded 0x address in that text** follows whatever IN FLIGHT's objective cell does under
  `tests/test_address_rule.py` and `tests/screens/test_address_icons_everywhere.py`. The
  implementer reads both and reports the answer. The 100-row fixture has two such failures.
* **Footer.** Built from the rows the widget was handed: `newest 12 · 8 blocked · 4 completed`,
  ordered by count descending, then by word. `None` or `[]` gets no footer (the base's rule).
* **Tiers.**
  * The starting proposal: `full` (all five), `compact` (`frontend` shed), `tight` (`when` shed
    too).
  * The implementer measures in situ and may refine the ladder.
* **Title.** `WORKFLOWS · as of HH:MM`, from `swarm_scores_as_of_hhmm` (LAUNCHES' clock).

### Screen

* **Layout.** `#surf-swarm-top` holds WORKFLOWS (left, CAPABILITY's place) and THROUGHPUT.
* **CSS**, identical in `SurfScreen.DEFAULT_CSS` and `themes/minimal.tcss`:
  * `SurfSwarmWorkflows { width: 1fr; height: 1fr; min-height: 8; padding: 0 1; }`. There is no
    `max-width`: the text column uses the room.
  * CAPABILITY's block goes.
* **Wiring.**
  * `_SWARM_PANELS`: CAPABILITY → WORKFLOWS.
  * `SWARM_WIDGET_SIGNATURES`: `"SurfSwarmWorkflows": ("swarm_workflow_rows",
    "swarm_scores_as_of_hhmm")` replaces CAPABILITY's entry.
* **Pins.**
  * `SURF_SWARM_FULL_LAYOUT_COLUMNS` is re-swept, because CAPABILITY bound it. The `#:` block
    names the new binder.
  * `CAPABILITY_OPTIONAL_FULL_COLUMNS` and its sweep are retired.
  * The row pin follows §1.
* **`KEY_HINTS` is unchanged.** The status bar is at its width; `x` is hinted in THROUGHPUT's
  title.
* **Docs.** README "Keyboard shortcuts" (the owner of keys) gains `x`. So do
  `.claude/rules/surf.md` and the terminal-layout skill's pin table and CAPABILITY paragraph.

### CAPABILITY is parked, not deleted

* **What stays:**
  * `widgets/surf/swarm_capability.py`, its class and `tests/widgets/test_surf_swarm_capability.py`;
  * the `/skills` read;
  * `swarm_skill_rows` / `swarm_skill_summary`.

  A future SKILLS board mounts it.
* **What goes:** SWARM's compose, `_SWARM_PANELS`, the CSS (both places) and
  `SWARM_WIDGET_SIGNATURES`.
* **New export:** `surf_models.SWARM_PARKED_WIDGET_SIGNATURES = {"SurfSwarmCapability":
  ("swarm_skill_rows", "swarm_skill_summary", "swarm_scores_as_of_hhmm")}`.
  * Every test that asks "is every exported widget mounted" or "is every key consumed" takes its
    exemption from this export, never from a hand-typed copy.
  * The widget-contract test keeps checking CAPABILITY's `update_data` against it.
* **The module docstring** says it was parked on 2026-10-03 for a SKILLS board. Its tier widths
  were last certified in situ on SWARM, so that board re-sweeps them.

## 3. AGENT's SCORE card becomes MODEL (F54)

* **Data.** `SWARM_SEAT_SUMMARY_FIELDS += "models"`: `list[{"model": str, "effort": str | None}]
  | None`.
  * Source: `/seats` `runtimes[].premiumModel`, through the existing
    `surf_swarm._advertised_models` helper (unique pairs, sorted by model then effort). Reuse it;
    never re-declare it.
  * `None` when `runtimes` is absent or not a list.
  * `[]` when a served list carries no usable `premiumModel`, seat #0's empty list included.
  * It is the **advertised** model. RECORD's `model` column stays the model a submission actually
    used.
  * It is folded at compute time from the stored raw seat (`surf_manager.py` `seat_summary_from_seat(seat)`),
    so it needs no cache migration. The implementer verifies this.
* **Card.**
  * Key and id become `model` / `surf-swarm-card-model`; its CSS `width: 20fr` moves in both
    places.
  * Title `MODEL`.
  * Gated like every seats card (`_seat_body`: pending, busy, never paired, unavailable).
* **Card body.**
  * One line per pair: `short_model(model)` in bold, then ` effort` dim. A `None` effort shows the
    model alone.
  * Each line is fitted to the card with a visible `…`, since model ids are third-party text.
  * Three pairs or fewer: every pair. More: the first two, then a dim `+N more` (NODES' shape).
  * `[]` → dim `not advertised`. `None` → yellow `unavailable`.
* **Tooltip.**
  * Every pair raw, one per line (`claude-fable-5-1 · high`), flattened.
  * Cleared on repaint, like RUNTIME's and NODES'.
* **Leaves the screen:** the mean score, `on N scored`, `N entries` and `NO_FEEDBACK_LINE`. The
  data fields `mean_score` / `scored` / `reviewed` / `review_entries` stay.
* **AGENT pin.**
  * The card's content changed, so the AGENT pin is re-swept; it moves only by measurement.
  * The stress payload gains four pairs, one a long unknown model id.
  * The v4/v5 `seat_420` captures carry `claude-fable-5-1` / `high`. The older `seats/` captures
    carry no `premiumModel`.

## 4. A sparkline that could not read says `unavailable` (#34)

* **`SparklinePanel.render_series`** (`widgets/panels.py`):
  * `points is None`, or not a list or tuple (a hand-edited cache file), shows yellow
    `unavailable`.
    * With `EMPTY_KEEPS_LABEL` set: `  [dim]<label cell>[/]  [yellow]unavailable[/]`.
    * Otherwise: `UNAVAILABLE_LINE`.
  * An entry that does not unpack shows `UNAVAILABLE_LINE` bare.
  * These keep `EMPTY_TEXT`, the real-empty sentence, as today: `[]`, fewer than `MIN_POINTS`
    usable points, or no usable point at all.
* **It is latent.** No manager passes `None` today, so nothing on screen changes.
  * Bakery's manager collapsing `None` to `[]` is #75, left open.
  * The sparklines outside this base (fwa, curator, surf market/pool4) are filed, not fixed.
* **Tests.**
  * Flip the two `"none"` cases in `tests/widgets/test_panels.py` (around :522 and :629).
  * Flip `test_an_empty_series_says_waiting_beside_its_label` in `tests/widgets/test_base_widgets.py`.
  * Add one case per `SparklinePanel` subscriber (CookieChart, TalismansSparkline, CTSparklines,
    TTTSparkline, DOTASparklines, OCMSparklines, BTSparklines), over `None` / `[]`, on composited
    output.

## 5. Out of scope, filed at close

* #75, bakery's `None` → `[]`.
* The non-`SparklinePanel` sparklines.
* `/workflows` pagination, a workflow detail popup, the SKILLS board itself.
* Any status-bar hint change.
* Persisting the THROUGHPUT fold.

## 6. Plan

Work packages run one at a time, each by one implementer, each followed by one task review
(reviewer contract verbatim, mid-tier model). Fix rounds are capped at 2. Afterwards come one
whole-branch review on the most capable model, one fix wave, one scoped re-review, then the full
suite once, by the controller. Every WP commits by pathspec, including the attribution lines from
the session.

* **Named tests.** Every WP's set includes `-m guard` and the doc-pinning tests for any doc it
  edits. Find those with `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`.
* **Mutation proof.** Every behaviour change carries one: keep `orig` in memory, assert
  `count(old) == 1`, restore by inverse edit, and name which test reddened.

### WP1 — #34, `SparklinePanel` (shared widget)

* **Files:** `widgets/panels.py`, `tests/widgets/test_panels.py`, `tests/widgets/test_base_widgets.py`,
  plus at most one new test file for the per-subscriber cases.
* **Work:** §4 exactly. Read every subscriber's `render_series` call site. If any passes an
  iterable that is neither a list nor a tuple, stop and report rather than widening the check.
* **Tests:**
  * `tests/widgets/test_panels.py`, `tests/widgets/test_base_widgets.py`,
    `tests/widgets/test_sparkline_common.py`;
  * each subscriber's own widget test file;
  * `-m guard`.

### WP2 — data: `/workflows`, the fold, the sweep, seat `models`

* **Files:**
  * `data/surf_models.py`, `data/surf_swarm_client.py`, `data/surf_swarm.py`, `data/surf_manager.py`;
  * `docs/imd_swarm_api.md`, `docs/surf_PRD.md`;
  * `tests/data/test_surf_swarm_client.py`, the fold's test file, `tests/data/test_surf_manager_swarm.py`,
    `tests/data/test_surf_swarm_models.py`, `tests/data/test_surf_models.py`;
  * `tests/screens/test_surf_screen.py`, where the new key enters `_KEYS_PENDING_CONSUMERS` with
    the precedent's comment.
* **Work:** §2 "Data", the seat-summary half of §3, `SWARM_PARKED_WIDGET_SIGNATURES` exported but
  not yet used, and the upgrade rule.
* **Fixtures** are committed with this spec: `v6/workflows_limit12.json`, `v6/workflows_100.json`
  and a MANIFEST. Hostile and malformed rows are built inside tests from those rows.
* **Tests:** the files above, `tests/test_surf_registration.py` if it binds key counts, and
  `-m guard`. Run `tests/screens/test_surf_screen.py` once at the end, not in the loop.

### WP3 — AGENT MODEL card

* **Files:**
  * `widgets/surf/swarm_agent_cards.py`;
  * `screens/surf.py` (the one CSS line) and `themes/minimal.tcss` (the same line);
  * `tests/widgets/test_surf_swarm_agent_cards.py`;
  * the AGENT screen and layout tests that name SCORE, ` scored` or the card id;
  * the AGENT pin `#:` block if the sweep moves it.
* **Work:** §3, the card half.
* **Tests:**
  * `tests/widgets/test_surf_swarm_agent_cards.py`, `tests/screens/test_surf_swarm_screen.py`;
  * the AGENT layout sweep file(s) and `tests/screens/test_address_icons_everywhere.py`;
  * the CSS agreement test;
  * `-m guard`.

### WP4 — SWARM widgets: WORKFLOWS (new) and THROUGHPUT's fold API

* **Files:**
  * `widgets/surf/swarm_workflows.py` (new) and `widgets/surf/swarm_throughput.py`;
  * `tests/widgets/test_surf_swarm_workflows.py` (new) and `tests/widgets/test_surf_swarm_throughput.py`.
* **Not exported** from `widgets/surf/__init__.py` yet: an exported widget must be mounted. WP5
  exports and mounts it in one commit.
* **Work:**
  * §2 "Widget".
  * §1's widget half: `set_expanded`, the title hint, the collapsed display. The widget's own
    default stays expanded.
  * The `ROW_CAP == SWARM_WORKFLOW_LIMIT` agreement test.
* **Tests:** the four test files plus `tests/widgets/test_surf_swarm_capability.py` (untouched,
  must stay green) and `-m guard`.

### WP5 — SWARM body: mount, park, key, CSS, pins, docs

* **Files:**
  * `screens/surf.py`, `themes/minimal.tcss`;
  * `widgets/surf/__init__.py`, `widgets/surf/swarm_capability.py` (docstring only);
  * `data/surf_models.py` (the `SWARM_WIDGET_SIGNATURES` flip);
  * `README.md`, `.claude/rules/surf.md`, `.claude/skills/terminal-layout/SKILL.md`;
  * the surf screen, swarm screen, swarm layout, widget-contract, registration and swarm-models
    tests.
* **Work:**
  * §1's screen half: `x`, the default collapsed, the top-row floor.
  * §2 "Screen" and "parked".
  * Empty `_KEYS_PENDING_CONSUMERS` again.
  * Re-sweep both SWARM pins on the boundary set, on every SWARM payload (capture, worst case, v3
    executing notes, the stress payload, the extra-states payload), in both fold states.
  * Rewrite the two `#:` blocks: the new numbers, the binder, and what moved and why.
* **Tests:**
  * the named screen, layout and contract files;
  * `tests/screens/test_address_icons_everywhere.py`;
  * the doc-pinning tests;
  * `-m guard`.

### WP6 — close (controller)

* CHANGELOG `Unreleased`.
* Resolve F16 (SWARM half), F23, F47, F51 and F54 in `docs/surf_swarm_followups.md`.
* Resolve #34 in `docs/handover_followups_2026_09.md`.
* File the §5 items and any review residuals.
* Memory.
* The full suite once, then report to the owner. No merge, push or tag without the owner.
