# Curator Filtered List View - Design Spec

**Date:** 2026-08-20
**Status:** Approved in brainstorming; pending written-spec review and implementation plan
**Branch:** `feature/curator-list-record-hero`
**Scope:** THE LIST dashboard's dedicated list view only

## 1. Summary

Extend THE LIST's `l` view from two sortable tables to three:

1. `THE RAW LIST`
2. `THE CLEANED LIST`
3. `THE FILTERED LIST`

The filtered list is always derived from raw rows. Three keyboard presets cover
the common cohorts, and a keyboard-driven editor exposes additional range,
identity, window, and linked-pattern filters. The existing list-only hero changes
with the visible list, table indexes follow the current sort order, and the
filtered result can be exported as JSON in exactly the order shown.

This work stays on the dedicated feature branch. It does not change the shared
dashboard hero or any non-list view.

## 2. Goals

- Add a filtered list with the same table behavior and visual hierarchy as the
  raw and cleaned lists.
- Make presets `1`, `2`, and `3` immediate and predictable.
- Provide a compact custom-filter editor opened and applied with `f`.
- Keep filtering synchronous, deterministic, keyless, and offline.
- Use all validated exported raw rows when available; otherwise use the live
  first 1,000 rows.
- Keep the hero and configured-wallet row consistent with the visible list and
  current table sort.
- Export the filtered rows in the visible order with sequential indexes.
- Preserve the existing address and ENS widths and fit the full table in the
  supported 143-column layout.

## 3. Non-goals

- Do not delete or redesign the Linked Analysis implementation. It is only made
  inaccessible for now.
- Do not add network reads, a new polling tier, or a new cache slot.
- Do not persist custom filter settings across process restarts.
- Do not add a query language, free-form expression parser, pagination system,
  or arbitrary address search.
- Do not change the raw/clean ranking rules or the sybilkit segmentation rules.
- Do not alter other dashboard views or shared hero-card components.

## 4. Terms And State

### Source rows

`THE FILTERED LIST` uses the same raw-row contract as `THE RAW LIST`.

- When `~/.maxpane/curator_raw_list.json` is present, parses successfully, and
  contains exactly the authoritative contributor count, all exported rows are
  the filter source.
- Otherwise, the source is the live raw slice, capped at 1,000 rows.
- A complete export that no longer matches the authoritative contributor count
  is rejected rather than partially trusted.

The raw and cleaned source-selection behavior remains unchanged.

### Filter state

The screen owns three separate pieces of state:

- the active list view: raw, cleaned, or filtered;
- the active filtered result specification, which may be a preset, a custom
  specification, or empty;
- the retained custom-editor draft for this process session.

Presets do not overwrite the retained custom draft. The first custom-editor open
starts blank. Reopening it later restores the last custom values entered during
the session.

### Index And Rank

- `INDEX` is the row's one-based position in the currently visible sort order.
- Raw rank and clean rank remain stable domain values.
- Sorting any header recomputes `INDEX` as `1..N` without changing raw or clean
  ranks.
- The configured-wallet row is outside the scrolling table and does not consume
  an index.

## 5. Presets

Pressing a preset key while the list view is active switches directly to the
filtered table and replaces the active filtered specification.

| Key | Label | Exact rule | Hero summary |
|-----|-------|------------|--------------|
| `1` | first 1000 wallets | `first_index` from 1 through 1,000, inclusive | `join #1-1,000` |
| `2` | joined hour 0 | `first_hour == 0` | `joined hour 0` |
| `3` | whale splash | wallet has at least one individual deposit of 25 ETH or more | `single deposit >=25 ETH` |

The whale preset uses the existing `WHALE_MIN_ETH` threshold and retained deposit
events. It is not a test of total credit, total weight, or 800 ETH credited.

## 6. Custom Filter Specification

All bounds are inclusive. Blank numeric inputs mean that side is unbounded.
Different active fields and categories combine with logical `AND`. Selected
evidence families are the only exception: a wallet matching any selected family
passes that family field, after which the result is combined with the other
active fields using `AND`.

With no active field, the filtered result is empty.

### Join

- Join index minimum and maximum (`first_index`).
- Joined hour minimum and maximum (`first_hour`).

### Score

- Raw rank minimum and maximum (`rank`).
- Points minimum and maximum (`points`).

### Contribution

- Credit ETH minimum and maximum (`credit_eth`).
- Weight ETH minimum and maximum (`weight_eth`).
- Deposit count minimum and maximum (`tx_count`).
- Whale splash toggle: at least one individual deposit of 25 ETH or more.

### Identity

- ENS: `Any`, `Set`, or `Unset`.
- Whitespace-only or missing names count as unset.

### Window

- `Any`, `Grace`, or `Judged`.
- This reuses the table's existing grace/judged classification so display and
  filtering cannot disagree about the same row.

### Linked Patterns

- Band: `Any`, `Clean`, `Low`, `High`, or `Unknown`.
- Evidence-family toggles:
  - matching amounts (`amount`);
  - consecutive joins (`sequence`);
  - cadence (`cadence`);
  - gas fingerprint (`gas`);
  - shared funding (`funding`).

`Unknown` means no completed analysis grade exists for the wallet. Evidence
family membership is taken from the persisted analysis groups and their member
lists. The manager projects this membership into a lookup; widgets never parse
analysis groups.

## 7. Architecture

### Pure filter model

A focused data module defines a small immutable `FilterSpec`, validation, active
condition summaries, and a pure row predicate. It receives:

- raw rows;
- the filter specification;
- per-wallet evidence-family membership;
- the set of wallets with a qualifying whale deposit.

It returns filtered raw rows without I/O and without mutating its inputs.

### Manager adapter

`CuratorManager` remains the model/data boundary. It:

- resolves the complete-export or first-1,000 raw source;
- builds evidence-family membership from the current last-good analysis payload;
- derives whale membership from retained deposit events;
- calls the pure filter model;
- returns rows and source-completeness metadata to the screen.

No new network call, cache slot, or background task is introduced.

### Screen controller

The curator screen owns navigation, active filter state, the custom draft, editor
versus table mode, and export dispatch. It passes already-prepared values to the
hero, editor, and list widgets.

The table emits a screen-handled sort/order change notification. The screen uses
the ordered addresses to update the configured wallet's visible filtered index
and to provide the exact export order. The table does not update hero widgets
directly.

### View widgets

- The list hero renders only the state supplied by the screen.
- The filter editor renders labeled Textual inputs, selects, and toggles and
  reports their current values; it does not filter rows.
- The list table renders and sorts rows, recomputes visible indexes, and renders
  the fixed configured-wallet row.

This keeps the existing frontend MVC split: manager/model computes data, screen
controls the interaction, and widgets render it.

## 8. Interaction

### List navigation

- `c` cycles Raw -> Cleaned -> Filtered -> Raw.
- Cycling to Filtered with no active specification shows an empty filtered table.
- Cycling away and back retains the active filtered result for the session.

### Preset keys

- `1`, `2`, and `3` work only while the screen is in list mode.
- A preset switches to Filtered table mode and applies immediately.

### Custom editor

- `f` from any list switches to Filtered and replaces the table with the editor.
- The first open uses a blank custom draft and therefore no result rows.
- Pressing `f` again validates and applies the editor values, then restores the
  filtered table.
- Reopening restores the last custom draft, independent of any preset used in
  between.
- While the editor is open, `1`, `2`, `3`, and `c` do not activate list
  shortcuts. Digits and normal editing keys belong to the focused control.
- While the editor is open, `e` only reports the apply-first receipt defined in
  section 12.
- `Tab` and `Shift+Tab` navigate the controls using normal Textual focus rules.

### Linked Analysis

- The old `f` Linked Analysis binding is removed from the reachable UI.
- `f linked` is removed from the bottom status line.
- The existing analysis mode, widgets, and data remain in the codebase but have
  no visible key binding.

## 9. Table Contract

The filtered table has the same row look and sorting behavior as the raw table.
All three list tables gain a leading visible-order `INDEX` column. The existing
domain-rank column remains separate: raw rank in Raw and Filtered, clean rank in
Cleaned.

The raw `LINK` column is removed. Cleaned and Filtered also have no `LINK`
column. Full-tier columns are therefore:

`INDEX | RANK | JOIN # | ADDRESS | ENS | POINTS | WEIGHT | CREDIT | DEPOSITS | HOUR | WINDOW`

The exact header labels may include the existing ETH glyphs, but `INDEX` and
domain rank must remain visually distinct.

The 42-column address allocation and the enlarged ENS allocation remain intact.
The removed LINK width and the previously approved CREDIT-width reduction absorb
the new index allocation. POINTS is not reduced. The full tier must be measured
at 143 columns, and narrower tiers continue to shed secondary columns rather than
truncate addresses.

The two rows under the scrolling table remain:

1. the configured wallet, aligned to the visible columns;
2. one blank line before the bottom rule.

In Filtered, the configured wallet's index is blank when it does not match the
active specification. When it matches, its index follows the current header sort.

Each table title includes its row count, for example
`THE FILTERED LIST - 568 wallets`.

## 10. Hero Contract

The three cards are list-view-specific components. No shared hero card changes.

### First card: visible-list summary

The first card always describes the current list.

**Raw**

1. `THE LIST`
2. raw wallet count and transaction count
3. raw ETH volume
4. `routed (all refunded)`
5. list state

**Cleaned**

1. `THE CLEANED LIST`
2. cleaned wallet count
3. cleaned points
4. `after linked removal`
5. list state

**Filtered**

1. `THE FILTERED LIST`
2. matched wallet count
3. sum of matched wallet points
4. `matching current filters`
5. list state

Table sorting does not alter these aggregates. Applying a different filter does.

### Middle card: configured wallet in the visible list

Line 1 is always `THE WALLET`. The identity line uses ENS when set and otherwise
the full address at the full width tier. Line 5 remains the wallet's points.

**Raw**

2. `<raw rank> of <raw total> (raw)`
3. join index and first hour

**Cleaned**

2. `<clean rank> of <clean total> (clean)`
3. join index and first hour

**Filtered**

2. `<visible index> of <match count> (filtered)`
3. active filter values

If the configured wallet does not match, the filtered visible index is a dash.
The active-values line remains present because it describes the visible list.
Long custom summaries use stable category order and collapse excess clauses to
`+N`; they do not overflow the card.

### Third card: filter help

The third card always renders exactly these lines:

1. `THE FILTER`
2. `'1' - first 1000 wallets`
3. `'2' - joined hour 0`
4. `'3' - whale splash`
5. `'f' - for more filters`

All five lines are white and regular weight.

### Existing list subtitle

The text beneath the hero cards remains:

`press 'e' to export full list as json file - once exported the complete list will be shown below`

It has no trailing period.

## 11. Filter Summary Text

Preset summaries use the exact strings in section 5. Custom summaries name only
active values in this stable order:

1. join;
2. score;
3. contribution;
4. identity;
5. window;
6. linked patterns.

Examples include `joined hour 0`, `credit >=25 ETH`, `ENS set`,
`window judged`, and `amount or funding`. If the complete text cannot fit, the
renderer keeps the earliest clauses and appends `+N` for the omitted active
clauses. It never substitutes raw or clean ranks for the active filters.

## 12. Export

`e` continues to export the visible list.

- Raw and cleaned export behavior and paths remain unchanged.
- Filtered exports write to `~/.maxpane/curator_filtered_list.json`.
- The filtered file is a plain JSON array of the current filtered row objects.
- Rows preserve the current displayed header-sort order.
- Each exported row contains `index` matching its visible one-based index.
- Raw rank remains present as the stable rank field.
- The write uses the existing atomic export behavior and receipt treatment.
- A table-state filtered result with zero rows writes `[]`.
- While the editor is open, `e` does not write and reports
  `press f to apply filters first`.

## 13. Validation And Degradation

- Numeric fields accept blank or finite non-negative numbers.
- Join index, hour, rank, points, and deposit count require integers.
- Credit and weight accept finite decimal ETH values.
- A minimum greater than its maximum is invalid.
- Invalid fields keep the editor open and identify the affected field.
- An active evidence-family filter without available analysis membership keeps
  the editor open and reports `linked analysis unavailable`.
- An active whale filter without retained deposit evidence keeps the editor open
  and reports `deposit history unavailable` rather than guessing from credit.
- If the complete raw export is unavailable, a successful filter receipt states
  that only the first 1,000 wallets were filtered.
- Missing configured-wallet data renders the existing dash/`WALLET NOT SET`
  states and never blocks the list.
- A valid filter with zero matches renders the normal empty filtered-table state.

## 14. Data Flow

1. The existing refresh produces the raw live slice, contributor count, list
   totals, last-good analysis payload, and retained deposit events.
2. The manager resolves a validated complete raw export or the first-1,000
   fallback without network I/O.
3. The manager projects evidence families and whale membership into address
   lookups.
4. A preset or validated custom `FilterSpec` is passed to the pure filter model.
5. The screen stores the result, computes its aggregate count and points, and
   dispatches list-specific hero/table payloads.
6. A table sort changes only visible order and indexes. The emitted order updates
   the middle hero's configured-wallet index and the future export order.
7. `e` serializes the currently ordered filtered rows atomically.

## 15. Testing

Implementation follows TDD: each behavior is first expressed as a failing test,
then satisfied by the smallest production change.

### Pure model tests

- Presets 1, 2, and 3, including the individual-deposit whale boundary at
  24.999... and 25 ETH.
- Every inclusive minimum and maximum field.
- Grace, judged, and any window selection.
- ENS set/unset/any.
- Band and evidence-family filters.
- `AND` across active fields and `OR` among selected evidence families.
- Empty specification and valid zero-match result.
- Stable active-condition summary ordering and `+N` compaction input.

### Manager tests

- Valid complete-export source selection.
- First-1,000 fallback when the export is absent, malformed, or count-mismatched.
- Analysis group-to-family membership projection.
- Whale address projection from deposit events.
- Explicit unavailable-analysis and unavailable-deposit-history states.
- No network calls during filtering.

### Widget tests

- `INDEX` appears first and `LINK` is absent.
- All three row shapes and rank fields.
- Sorting every header renumbers indexes while preserving domain ranks.
- Configured-wallet row alignment, matching index, and non-match blank index.
- Raw, cleaned, and filtered first-card states.
- Raw, cleaned, and filtered middle-card states.
- Exact five-line white, regular-weight filter-help card.
- Full-tier 143-column fit plus existing narrow-tier address/ENS guarantees.

### Screen tests

- Raw -> Cleaned -> Filtered -> Raw `c` cycle.
- Immediate `1`, `2`, and `3` presets.
- First blank `f` editor, second-`f` apply, retained custom draft, and validation
  failures.
- Input focus prevents preset/cycle shortcut interception.
- Filtered export path, order, indexes, empty array, and editor-open rejection.
- Current-list hero dispatch and sort-driven configured-wallet index updates.
- Linked Analysis binding/status hint hidden while implementation remains intact.
- Other curator modes and shared heroes unchanged.

### Verification

- Run the focused filter/model/manager/widget/screen tests during development.
- Run the complete curator suite.
- Run the repository suite and distinguish any already-known unrelated failures
  from regressions caused by this feature.
- All tests are keyless and offline.
