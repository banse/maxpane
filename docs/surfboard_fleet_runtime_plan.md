# Boardroom FLEET runtime summary

**Date:** 2026-10-15
**Status:** implemented and reviewed; local validation complete
**Tier:** 2 — replacement of the private FLEET card contract
**Size:** below 1,000 production lines; one final review, no package reviews

## Approved result

FLEET will explain the online fleet's runtime mix and current software instead
of listing top agents. The owner selected the runtime design and approved direct
implementation. The final inner footer contains only the leading model and its
effort, for example `astra 6 xhigh`; omit the `top model` label.

| Card surface | Content |
|---|---|
| Outer title | `FLEET` |
| Inner title | `RUNTIMES` |
| First row | `codex` and its percentage of distinct online seats |
| Second row | `claude` and its percentage of distinct online seats |
| Third row | `daemon` and the most-used version without its `+build` suffix |
| Inner footer | Most-used advertised model and its paired effort |
| Outer footer | Existing centered `worked <years>y <weeks>w <days>d` |

Use leaderboard foreground green for row values; keep labels, frames and the
model/effort footer neutral. Preserve source information on hover, initial
loading behavior, last-good data during refresh and the independent worked-time
source. Unknown facts remain unknown, not zero. The change introduces no
endpoint, timer or cache and follows the existing pure data → manager → widget
boundary.

The owner explicitly said **“no new preview needed go with that.”** This
overrides the normal live-preview and owner-approval gate for this change.
The earlier standalone mock was shown at 149 × 45; proceed directly with
integration and automated geometry checks without requesting another preview.

## Frozen card contract and calculations

Replace obsolete `top_agents` with the primitive `fleet_summary` dictionary:

```python
(
    "codex_percent", "claude_percent", "daemon", "model", "effort",
    "online", "runtime_known", "state", "read_ts",
)
```

All fields are present on each snapshot. Retain matching last-good facts and
their worker source clock during refresh or failure. The existing contributor
duration retains its own clock; neither source freshens the other.

- **Runtime shares:** group normalized current workers by distinct online seat
  ID and deduplicate devices. A seat contributes at most once per runtime;
  `both` contributes once each to codex and claude. Divide by all distinct
  online seats. Require a complete roster and nonempty known runtime IDs for
  every seat before claiming either percentage. Incomplete coverage is unknown.
  A complete empty roster is loaded with unknown percentages, never 0/0.
  Hover explains overlap, the denominator and known-runtime coverage; the two
  shares may sum above 100%.
- **Daemon:** strip the `+build` suffix before counting versions across current
  workers. Select the most-used base version, with deterministic name ordering
  for ties. Do not turn missing versions into a vote.
- **Model and effort:** count current advertised `(model, effort)` pairs from
  normalized workers, deduplicating each pair per worker and excluding absent
  models. Select the most-used pair with deterministic name ordering for ties.
  Preserve its effort; do not combine effort levels or average them. Hover
  identifies this as current advertised configuration, not historical job use.

## Ownership and sequence

| Owner | Exclusive files | Dependency |
|---|---|---|
| Planning agent | This document only | Approved design and frozen contract |
| Data implementer | `maxpane_dashboard/data/surfboard.py`, `surf_models.py`, `surf_manager.py`, `surf_leaderboard_hero.py`; corresponding data tests | Frozen `fleet_summary` seam; extract shared runtime counts without changing existing leaderboard facts |
| UI implementer | `maxpane_dashboard/widgets/surfboard/rack.py`; `tests/widgets/test_surfboard_rack.py` | Frozen seam and approved card appearance |
| Controller | `tests/surfboard_fixtures.py`, `tests/screens/test_surfboard_layout.py`, documentation, pin comments and integration verification | Integrated data and UI packages |

Data and UI work may run in parallel because file ownership is disjoint.
Preserve others' changes and report cross-owner defects rather than editing
their files. Reuse the current workspace and branch. No subagent delegation
from implementers and no separate package review.

## Acceptance and verification

1. Use focused TDD for aggregation, unknown/empty/partial roster behavior,
   duplicate devices, overlapping runtimes, missing runtime coverage, daemon
   suffix aggregation, model/effort pairing, ties and retained source clocks.
   Exercise manager capture and the private contract agreement.
2. Check composited rendering: the three row values are green; labels, borders
   and the model/effort footer are neutral. Verify centered worked duration,
   literal-safe metadata, first-load indication, retained refresh data and
   missing facts. No test uses the network or real clipboard.
3. Integrate fixtures and verify actual boardroom geometry at **146 × 37** and
   **149 × 45**, including fit of the model/effort footer. Inspect rendered
   content, not merely absence of a size hint. Update pin evidence only if the
   measured result warrants it; do not generate another owner preview.
4. Use `scripts/mutate.py` for targeted calculation/decoder and composited
   regression proof. Controller allocates serial mutation slots; restore exact
   bytes before other verification imports or final review.
5. Run touched test files and composing manager/screen files once before commit,
   the fast guard set and applicable docpins using `.venv/bin/python`; unset
   `NO_COLOR` for color verification. No full-suite run is added.
6. One final review on the most capable model after integration; one fix wave
   and a scoped re-review only if fixes change production code. File Minor-only
   residuals in the existing follow-ups document. Update this status and commit
   locally with scoped evidence; do not push.

Completion means the production card displays the approved live-derived runtime,
daemon and model/effort facts while preserving loading, retention and layout.
No further user confirmation is required.

## Delivery evidence

The production card uses the approved runtime rows, base daemon and unlabelled
model/effort footer. Existing duration, destination and last-good loading behavior
are preserved. The 146 × 37 minimum and 149 × 45 owner size remain unchanged.

Validation covered 637 data/manager cases, 78 rack cases, 18 composing screen
cases and 89 layout cases. One migrated palette assertion needed the resolved
theme foreground rather than an optional theme override; its focused rerun
passed. Eight implementation mutants and two review mutants were rejected and
restored exactly. The 124 fast guards and 12 documentation pins passed.
No full suite or new preview.

Final review found no Critical or Important issues. Its one Minor documentation
wording issue is filed in `docs/surfboard_followups.md`.
