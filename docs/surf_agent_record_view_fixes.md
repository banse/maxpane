# Surf AGENT record view — fix wave

Branch `feature/surf-agent-record-view`, head `5409f17`. This is the only fix wave for the
review of `docs/surf_agent_record_view_plan.md`. Five reviews ran (WP0, WP1, WP2, WP3, WP4 plus
one whole-branch review). Every finding below was checked against `5409f17`. Findings that
existed only on an intermediate commit and are already fixed on the head are not listed
(these include the SKILL.md 33 → 25 guard and the `SurfSwarmNodeCards` contract test).

Run X1–X7 straight through, with no pause. Commit once per item or as one commit per logical
group. Do not merge or push. At the end, send one report: the commit(s), the tests you ran with
their counts, and a mutation proof for X1, X2 and X3 that names the test that turned red.

Rules as before: CLAUDE.md conventions, no network in tests, and no pin changes (none of these
items moves a pin; if one would, stop and report instead).

## Important

### X1 — `set_record_view` crashes on a non-numeric view value (WP2)

`data/surf_manager.py:5542` `SurfManager.set_record_view(cap, open_only)` runs
`max(40, min(400, cap))`. `cap=None` or `cap="x"` raises `TypeError`. The widget's
`SurfSwarmSeatRecord.set_record_view` (`widgets/surf/swarm_seat_record.py:~192`) has the same
shape.

Fix: accept `cap` only as an `int` that is not a `bool`. Anything else leaves the current view
unchanged (a no-op, no raise, no `mark_due`). `open_only` is used only when it is a `bool`;
otherwise it is a no-op too. Apply this in both the manager and the widget.

Tests: parametrize `None`, `"x"`, `1.5`, `True` and `[]` for cap, and `"yes"` and `None` for
`open_only`. Assert that nothing raises, the attributes are unchanged, and (manager) the tier is
not marked due. Mutation proof: remove the guard in the manager and name the test that turns red.

### X2 — `record_window` / `record_state` raise on malformed rows (WP0)

`analytics/surf_swarm_signals.py:153-162`:
- `record_window(None, …)` raises `TypeError`.
- A non-dict item (`"bad"`) raises `AttributeError` in `record_state`.

The widget guards against a non-list but not against a non-dict item, and both the widget and
the manager call these helpers. Fix it once, in the helpers:
- A non-list or non-tuple `rows` gives `[]`.
- A non-`Mapping` item is skipped, so it is not selected and not counted.
- `record_state` of a non-`Mapping` gives `None`.

Leave the order and the 40..400 clamp unchanged.

Tests in `tests/analytics/test_surf_swarm_signals.py`: `None`, `"abc"`, and a mixed list
`[{"work_status": "failed"}, "bad", 3, None]`. The mixed list gives exactly the one dict row, in
both filter modes. Mutation proof: remove the item skip and name the test that turns red.

## Minor (do them in this wave; each is small)

### X3 — refresh-path seat reset is untested (whole-branch 1, WP3)

`screens/surf.py:4383-4391` resets the RECORD view when the seat token changes through the data
path instead of through `_seat_entered`. This happens when the default "most active" seat
changes, and on the first refresh after a restart. The whole-branch reviewer turned the
condition into `if False and …`, and `test_surf_swarm_screen.py` plus
`test_surf_swarm_seat_record.py` stayed green (196 passed).

Add a screen test: two `_do_refresh` payloads with different seat tokens and no `_seat_entered`
in between, after a `more` click and a filter click. Assert that the cap and the filter are back
to 40/all on the screen and in the manager. Also assert that the first refresh (token was
`None`) does not call `set_record_view`. Mutation proof: the same `if False and …` edit, and
name the test that turns red.

### X4 — one filter predicate (whole-branch 2)

`widgets/surf/swarm_seat_record.py:201` restates `record_window`'s predicate inline for
`_filtered_count`. Hoist one pure helper into `analytics/surf_swarm_signals.py`, for example
`record_selected(rows, open_only) -> list[dict]`, the filtered but unclamped list, with the X2
tolerance. `record_window` becomes `record_selected(...)[:clamp]`, and the widget counts
`len(record_selected(...))`. The existing count test (405 filtered rows) stays as it is.

### X5 — one `+N older` formatter (whole-branch 3)

`seat_footer` is now called only as `seat_footer(self._state, None, None)`
(`swarm_seat_record.py:219`), so its `rows`/`cap` parameters and `older_line` are dead in
production. Meanwhile line ~226 builds a second `+N older` string. Keep one formatter:
- `older_line` takes the filtered count and the cap and is what the widget's footer calls.
- `seat_footer` loses the dead parameters.

Update `__all__` and any test that calls them. The footer text must not change (`+N older ·
more`, `no incomplete records`).

### X6 — NODES fits the key before sizing the numbers (WP1, whole-branch 4)

`widgets/surf/swarm_agent_cards.py:~727` `_nodes_body` measures the `_num` line with the
unfitted `flatten(key)` and only fits the key afterwards. As a result, a long unknown node key
pushes the accepted count to its coarsest form, even though the key is then cut off with an
ellipsis. Fit the third-party key to its column first, then choose the number forms against
the remaining width. Known keys (ORACLE/REVIEW/BUILD) must render byte-identically to now.

Test: a 40-character unknown key at the card's width keeps the exact count (e.g. `224`, not
`0.2K`) and ellipsises the key.

### X7 — orphaned comment (WP2)

`data/surf_manager.py:1101-1110`: the new `record_cap` / `record_open_only` lines sit between
the `#:` comment about the default seat and `self._seat_saved`, which that comment documents.
Move the two lines below `_seat_saved` and give them one short `#:` of their own (the view is
the screen's; 40..400; it resets on a seat change).

## File, do not fix

Append this to `docs/surf_agent_record_view_followups.md`:

- **F-R1 — stale non-terminal points after grow → shrink → grow** (whole-branch 5). Rows 41–400
  that were read earlier keep their cached point, and it is not re-read while the row is
  outside the window. After the window grows again, those rows show the old value until the
  due read reaches them (4 per cycle), behind the seat's `as of` only. The impact is low
  because old rows are almost always terminal. The same thing already happens inside the
  40-row window after a restart.

## Tests to run at the end

`tests/analytics/test_surf_swarm_signals.py tests/widgets/test_surf_swarm_seat_record.py
tests/widgets/test_surf_swarm_agent_cards.py tests/widgets/test_surf_widget_contract.py
tests/data/test_surf_swarm_models.py tests/data/test_surf_manager_answers.py
tests/data/test_surf_manager_oracle.py tests/screens/test_surf_swarm_screen.py`, then
`tests/screens/test_surf_swarm_layout.py -k "agent or record"`, then `-m guard`. Do not run the
full suite; the controller runs it once, before the merge.
