# Surf AGENT RECORD filter — spec and plan

Owner request 2026-10-02: "add a filter to the AGENT dashboard RECORD table. It should work like the
filter in THE LIST dashboard … typing f replaces the table with a filter view … reuse as much of
THE LIST filter as possible … filter by node, state, model, combined with AND, or any other useful
RECORD properties." Design approved in chat the same day with the three recommendations: the editor
takes the seat cards *and* RECORD, the read-dependent groups ship now with a `not read yet` count,
WHEN is a dropdown. Tier 2: a shared widget hoisted out of curator, two dashboards, > 6 files.
Branch `feature/surf-record-filter` (from `2541194`).

## What the reader sees

* **`f` on AGENT** hides the seat-card row and RECORD and shows the filter editor in their place;
  the hero stays. `f` again or APPLY FILTER applies; RESET ALL clears the draft (it does not apply);
  `esc` closes the editor and discards the draft (a second `esc` leaves AGENT as today). Leaving
  AGENT or changing seat closes it too. `f` is a no-op on every other body.
* **RECORD's title** gains a third mode word: `RECORD · all · not completed · filtered · as of HH:MM`.
  `filtered` exists only while a filter is stored; it is bold accent when active, dim otherwise, and
  clicks `screen.record_filter('filtered')`. `all` / `not completed` keep the stored filter for a
  later click on `filtered`. Applying an empty filter clears it and shows `all` (THE LIST's rule:
  an empty filter is not an empty result). A seat change clears it.
* **The footer, in `filtered` mode**, is one line: the summary, then the counts, then the existing
  older/more tail — `oracle · outvoted · since 09-25 14:00 · 12 match · 4 not read yet · +183 older · more`.
  The summary is clipped first (`…`); the counts never are. Nothing matching and nothing unread says
  `no matching records`. Seat-state overrides (pending/busy/unavailable) win as today.

## Groups

AND across groups; inside a checkbox group the ticked options match any (THE LIST's rule).

| group | control | values | evaluated on |
|---|---|---|---|
| NODE | checkbox per node key in this seat's rows | raw `node_key` | every row |
| STATE | checkbox per `record_state` present | the state word | every row |
| WHEN | Select any / last 24 h / last 7 days / last 30 days | `since_ts` | every row |
| MODEL | checkbox per short model among read rows | raw `model` ids | rows with a submission read |
| PANEL | Select any / agreed / outvoted / no quorum / assessing / blocked / off panel / unavailable | `panel_state` | oracle rows with a panel read |
| ANSWER | Select any / replied / no reply / not served / unavailable | `answer_state` | rows with a submission read |
| TOOK | from / to, minutes (decimal) | `took_s / 60` | rows with a submission read |
| TOK | from / to, output tokens (integer) | `output_tokens` | rows with a submission read |

* **Choices are the seat's own.** NODE, STATE and MODEL list what the RECORD rows (the whole lifetime
  list, not the window) contain when the editor opens, plus anything already selected, so a stored
  choice is always visible and removable. NODE labels are `NODE_TITLES` words lower-cased (`oracle`)
  or the flattened key fitted with `…`; MODEL labels are `_fmt.short_model`, several raw ids sharing a
  label share one checkbox. Third-party labels reach the `Checkbox` as a `rich.text.Text`. A group
  with no choices says so in dim (`no models read yet`).
* **WHEN is absolute once applied.** The dropdown keeps the reader's word (`7d`); on apply the screen
  turns it into `since_ts = clock() - 7 days` through its own clock seam, and the summary says
  `since MM-DD HH:MM` — a fixed cutoff, stated, never a window silently sliding while the app is
  open. Re-applying recomputes it. A row's time is `submitted_ts`, else `accepted_ts`; a row with
  neither does not match a WHEN filter.
* **Validation** reuses THE LIST's: non-negative numbers, `from` ≤ `to`, the error on the `from`
  field with the field outlined and focused, nothing applied while invalid.

## Rows nobody has read yet

MODEL, PANEL, ANSWER, TOOK and TOK exist only for rows whose submission (or panel) has been read, and
the seat cycle reads at most four jobs per 120 s, only inside RECORD's window. So:

1. **The read window is the base filter.** `record_window(rows, cap, open_only, spec)` applies the
   mode and NODE/STATE/WHEN, then the 40..400 cap — the same function in the manager (scheduling
   answer, job-detail and oracle reads) and the widget (painting). The read-dependent groups never
   decide what gets read: that would be circular.
2. **Each active read-dependent group answers yes, no or unknown** for a row in that window:
   * a read value: compared (`no` when the read served no value, e.g. no model);
   * `not_read` on a row that can be read (canonical lower-case job UUID and 64-hex submission
     hash, `record_readable`) → unknown, *not read yet*; on a row that never can be → `no`;
   * `unavailable` (the read failed, it retries) → unknown, *unavailable*, unless the group
     selected `unavailable` itself;
   * MODEL/TOOK/TOK on `not_served` → `no`; PANEL on a non-oracle row → `no`.
3. A row shows when every group says yes. A row with no `no` and at least one unknown is **counted,
   never shown and never dropped**: `N not read yet` (any unknown cause is not-read) and
   `N unavailable`; the first drains as reads land. `+N older · more` counts base-filtered rows past
   the cap, exactly as today.

## Reuse: what moves out of curator

* **`analytics/range_filters.py`** (new, pure, stdlib): `FilterValidationError(field, message)`,
  `parse_number(field, value, *, integer)`, `check_order(parsed, pairs)`, `row_number(row, field,
  *, integer)`, `number_text`, `range_text(label, low, high, *, unit="")` — curator's own private
  copies today. `data/curator_list_filters.py` imports them and re-exports `FilterValidationError`;
  its behaviour and its tests are unchanged.
* **`widgets/filter_editor.py`** (new, shared, Textual only — no `data/` or `analytics/` import):
  `FilterEditorBase(Vertical)` owns the chrome THE LIST's editor carries today — the error line
  (`ERROR_ID`), the titled-group grid (4 columns, 2 under 100 content columns via `compact-filter`),
  `range_group` (from/to `Input(type="number")`), `select_group`, `titled_group`,
  `section_title`, the APPLY FILTER / RESET ALL row, `values()` / `set_values()` over the declared
  `RANGE_FIELDS` and `SELECT_OPTIONS`, `show_error` / `clear_error`, and the button dispatch, which
  posts the subclass's own `APPLY_MESSAGE` / `RESET_MESSAGE`. Its classes are generic
  (`filter-groups`, `filter-group`, `filter-group-title`, `filter-section-title`, `filter-range`,
  `filter-field`, `filter-actions`, `filter-invalid`) and its `DEFAULT_CSS` styles them.
* **`CuratorListFilterEditor`** subclasses it: it declares its ranges and selects, composes WHALE,
  LINKED PATTERNS and NFT HOLDERS through the base builders, and keeps its own
  `FilterApplyRequested` / `FilterResetRequested` (the CR-01 guard in
  `tests/test_curator_registration.py` keeps that event curator's). Its ids and its error id
  (`curator-filter-error`) are unchanged; the generic classes lose the `curator-` prefix in
  `screens/curator.py` and `themes/minimal.tcss` (both places, the parity test) and in four test
  lines. THE LIST renders the same.
* **Surf's filter logic** lives in a new `analytics/surf_record_filter.py` (pure; it imports
  `range_filters` and `surf_swarm_signals.record_state`). *Changed from this spec's first draft,
  which put it in `surf_swarm_signals.py`:* `tests/analytics/test_surf_swarm_signals.py` pins that
  module to import nothing from `maxpane_dashboard`, and the parser needs `range_filters`.
  `record_selected` / `record_window` move with it (gaining `spec`), so there is still one window
  function. It exports `RecordFilter` (frozen), `WHEN_SECONDS`, `parse_record_filter(values, *,
  now_ts)`, `record_base_match`, `record_read_match`, `record_readable`, `record_view(rows, cap,
  open_only, spec) -> RecordView(rows, older, not_read, unavailable)`, `record_filter_choices(rows)`.
  `record_readable` restates the canonical job-id and hash patterns (analytics may not import
  `widgets/explorer`); an agreement test binds it to the data layer's own read rule,
  `surf_swarm_client.parse_job_id` and `surf_swarm._hex64` — *built:* the rule the seat cycle
  actually reads by, rather than this draft's `_oracle_answer.valid_identity`. Both new
  analytics modules join `_PURE_ANALYTICS_ALLOWED` in the surf widget contract test.

## Surf pieces

* `SurfManager.set_record_view(cap, open_only, spec=None)` stores a `RecordFilter` (anything else is
  ignored, as a malformed cap is today) and marks the seat tier due; `set_seat` clears it. Every
  `record_window` call passes it. No I/O, no await.
* `SurfSwarmSeatRecord.set_record_view(cap, open_only, spec=None)`; `filter_choices()` hands the
  screen primitive choices for the editor; title and footer as above.
* `widgets/surf/swarm_record_filter.py`: `SurfRecordFilterEditor(FilterEditorBase)`; `async
  load(choices, values)` rebuilds the three checkbox groups (awaited, so ids never collide) with
  each box's value set at construction; `RecordFilterApplyRequested` / `RecordFilterResetRequested`.
  *Built, beyond this draft:* the module is imported directly and is **not** in
  `widgets/surf/__init__.__all__` (the contract test derives `_ALL_WIDGETS` from `__all__` and
  requires `update_data`; the disk walk still checks its imports for purity). Its group gap is
  `padding-bottom`, not the base's `margin-bottom`: a grid row is sized to its tallest group's
  content and the margin is then taken out of it, which cut a checkbox group's last option off
  in silence; its dropdowns and ranges draw on one line. The read note under the groups is a
  wrapping `Static` (`READ_NOTE`), not a `section_title`: an 82-cell `Label` scrolled the editor
  sideways below 84 columns. The footer's `unavailable` count is plain yellow on a dim line.
* `screens/surf.py`: `f` (priority, AGENT only), `record_filter('filtered')`, escape closes the
  editor first, seat change and leaving AGENT close it and clear the filter where the table is reset
  today; `_clock` seam (`time.time`) used only at apply. CSS for the editor's slot in
  `SurfScreen.DEFAULT_CSS` and `minimal.tcss`. The editor scrolls inside itself; it is not a
  `_SCROLL_COLUMNS` entry (a form, not a fixed-line panel).
* No new contract key, tier, slot, degraded group or pin. The AGENT layout test gains the editor
  state at the pin and below the compact threshold (every control inside the editor, no horizontal
  overflow).

## Work packages (run in order by the session; one reviewer each)

1. **WP1 hoist** — `analytics/range_filters.py`, `widgets/filter_editor.py`, curator's editor and
   data module on them, the class rename. Tests: `tests/analytics/test_range_filters.py` and
   `tests/widgets/test_filter_editor.py` (new), `tests/data/test_curator_list_filters.py`,
   `tests/widgets/test_curator_widgets.py`, `tests/widgets/test_curator_address_icons.py`,
   `tests/screens/test_curator_screen.py`, `tests/test_curator_registration.py`, `-m guard`.
2. **WP2 surf** — analytics, manager, RECORD widget, editor, screen, CSS, docs (README AGENT section
   and shortcuts, CHANGELOG, `rules/surf.md`, `rules/widgets.md` shared-module list,
   `rules/curator.md`). Tests: `tests/analytics/test_surf_record_filter.py` (new),
   `tests/analytics/test_surf_swarm_signals.py`,
   `tests/data/test_surf_manager_answers.py`, `tests/widgets/test_surf_swarm_seat_record.py`,
   `tests/widgets/test_surf_swarm_record_filter.py` (new), `tests/widgets/test_surf_widget_contract.py`,
   `tests/data/test_surf_manager_oracle.py`, `tests/screens/test_surf_screen.py` (bindings),
   `tests/screens/test_surf_swarm_screen.py`, `tests/screens/test_surf_swarm_layout.py`,
   `tests/test_surf_registration.py`, `-m guard`.
3. Final whole-branch review on the most capable model, one fix wave, one scoped re-review, the full
   suite once by the controller. No merge, push or tag: those are the owner's.

## Final review and follow-ups (2026-10-02)

The whole-branch review (most capable model) found 0 Critical, 2 Important, 3 Minor. Both
Important were fixed in one wave and proven by mutation:

* **I-1** — a refresh's seat-token change reset the screen's view but skipped the manager's
  whenever the old token was None, so a filter, `not completed` or `more` chosen before the
  sweep picked a seat kept narrowing the first seat's answer / job-detail / oracle reads while
  RECORD painted `all`. The pre-existing guard now also fires when the old view was not the
  default (`test_a_view_set_before_the_first_seat_is_reset_in_the_manager_too`).
* **I-2** — `PANEL_STATES` restated `data/surf_models.SWARM_PANEL_STATES` with no agreement
  test; `test_the_vocabularies_match_the_data_layer` now binds both directions.

Filed, Minor (do as Tier 0 when the file is next touched):

* **F-RF1: two unknown node keys can share one NODE box.** `load()` groups by label, and an
  unknown key's label is clipped to 16 cells, so `market_research_alpha` and
  `market_research_beta` become one `market_research…` box that ticks both. The spec meant the
  merge only for MODEL's `short_model`. Group NODE by raw key (RECORD's 6-cell node column cannot
  tell them apart either, so the box label needs a disambiguator, not just a split).
* **F-RF2: `record_time` and `_SERVED` restate the widget's own rules unbound.** The filter's
  WHEN uses `analytics/surf_record_filter.record_time` and its MODEL/TOOK/TOK use `_SERVED`;
  RECORD's when column (`swarm_seat_record.py` `_row`) and usage cells restate the same rules
  inline. Have the widget import the pure helpers (or add an agreement test) so "the filter
  matches what the column shows" cannot drift.
* **F-RF3: the filtered footer can still cut a count at narrow widths.** The summary gives way
  first, but the counts plus the older tail (up to ~67 cells, e.g. `180 match · 200 not read yet
  · 20 unavailable · +1,234 older · more`) exceed the footer below about 69 content cells, where
  the CSS ellipsis cuts the older count or `more`. Not rendered by the reviewer; measure first,
  then shorten (drop ` yet`, or move the tail) rather than clip.

