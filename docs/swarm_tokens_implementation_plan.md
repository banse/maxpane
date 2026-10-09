# SWARM TOKENS mock implementation plan

Approved direction: version 1 Market overview; all production chains, filtered
from All by default; 149×45. Branch: `feature/surfboard-hub-9`.
Tier 2: new dashboard widgets and nested screen. Target scope is under 1,000
production lines (roughly 200 data/analytics, 500 UI, 100 integration/demo), an
implementation aim to check against the actual diff rather than a guarantee.
Under the repository's small-Tier-2 exception, use one final review only.

## Frozen primitive contract

Package A publishes the model key tuples and widget signatures in
`data/swarm_tokens_models.py`; it does not extend the existing SURF_KEYS.

Snapshot: `tokens: list[dict]`, `activity: list[dict]`, `as_of: float`,
`is_mock: bool` (always true in this phase).

Token record:

| Keys | Types / meaning |
|---|---|
| `id`, `launch_id` | stable `chain:launch` string identity; integer launch ID |
| `symbol`, `name`, `chain` | strings; chain `eth`, `base`, or `rh` |
| `launched_at` | timestamp, seconds |
| `price_usd`, `change_24h`, `mcap_usd`, `volume_24h` | float or None |
| `buys_24h`, `sells_24h` | integer or None |
| `paired_amount`, `paired_symbol` | float or None; unit string |
| `lp_state` | `two-sided`, `one-token`, `one-quote`, `withdrawn`, `unknown` |
| `sparkline` | list of float samples or None; equal-window 24h price history |
| `verdict` | display-state string |

Optional detail fields: `fdv_usd`, `fee_pct` (nullable
floats) and `status` (string). No addresses, explorer actions or copy glyphs are
required for synthetic identities. Future live identity will use chain+address.

Activity record: `id: str`, `token_id: str`, `ts: float`, `kind: str`,
`amount: float|None`, `asset: str`. Token identity resolves symbol and chain.

Pure API:

```python
select_tokens(tokens, *, chain="all", query="", lp_state="all", sort="volume")
project_snapshot(snapshot, *, chain="all", query="", lp_state="all", sort="volume")
```

Projection keys: `tokens`, `metrics`, `newly_launched`, `gainers`, `losers`,
`activity`, `as_of`, `is_mock`. The helper uses snapshot `as_of` as its injected
clock. No imports of Textual, data clients or wall-clock reads in analytics.
The UI selects from four named sort options; unknown numeric values sort
last. All subviews derive from the same filtered IDs. Gainers require positive
change and losers negative change; both need known price. Keep one-sided
positions eligible and show their LP context. Never fill empty rankings with
unknowns or zero-change tokens.

## Package A — mock records and pure projection

Owner: one data implementer. Disjoint from packages B and C.

Files:
- `maxpane_dashboard/data/swarm_tokens_models.py`
- `maxpane_dashboard/data/swarm_tokens_demo.py`
- `maxpane_dashboard/analytics/swarm_tokens.py`
- `tests/data/test_swarm_tokens_demo.py`
- `tests/analytics/test_swarm_tokens.py`

Task A1 (30–60 minutes): define the primitive contract and deterministic,
plausible mock population. Include all supported chains, recent/old launches,
every LP state, zero and unknown metrics, independent sparklines and duplicate
symbols with different stable IDs. `demo_snapshot()` returns independent data.
Acceptance: no network imports/calls, arithmetic counters match the records,
mock status explicit, and records provide enough rows to exercise scrolling.

Task A2 (30–60 minutes): implement pure selection/projection using tests first.
Acceptance: filters affect every widget population consistently; rank order,
time-window boundaries, ties, missing values and zero values are deterministic;
unknown coverage remains visible; filtering does not mutate the fixture.

## Package B — dashboard widgets

Owner: one widget implementer. Starts once package A's contract is agreed;
packages may proceed in parallel because files are disjoint.

Files:
- `maxpane_dashboard/widgets/swarm_tokens/__init__.py` and dashboard-owned widgets
- `tests/widgets/test_swarm_tokens.py`

Task B1 (30–60 minutes): render version 1's metric strip, main table and three
supporting panels with shared panel/metric primitives and sparkline helpers.
Consume named primitive arguments from the frozen contract. Widgets do not
import data modules. Acceptance: approved columns and panels render; unknowns
and zeros differ; token sparks are independent; names safely render as text.

## Package C — screen, hub route and offline entry

Owner: root/session; integration depends on packages A and B contracts.

Files:
- `maxpane_dashboard/screens/swarm_tokens.py`
- `maxpane_dashboard/demos/__init__.py`, `demos/swarm_tokens.py`
- `maxpane_dashboard/screens/surfboard.py`
- `maxpane_dashboard/widgets/surfboard/rack.py` (demo-card presentation/activation)
- Relevant new screen tests and existing hub tests
- `maxpane_dashboard/themes/minimal.tcss` (scoped screen CSS mirror)
- Required guard registries only if the new nested screen triggers them; root
  alone owns shared registry files and documents the narrow registration reason.

Task C1 (30–60 minutes): compose version 1 at the target size.
Screen subclasses DashboardScreen and uses an offline
manager adapter; it owns filter/selection state and routes primitive projections
through named update_data arguments. Widgets do not import data modules.
Acceptance: all approved panels/columns visible in the 149×45 mock render;
MOCK DATA remains unmistakable; unknown values and independent sparks render.

Task C2 (30–60 minutes): wire filters, sort, search, token detail and selection
identity; push the screen from the SWARM TOKENS hub card and add standalone
module entry. Acceptance: full workflow works offline, Escape returns to hub,
and no top-level game number or existing dashboard route changes.

## Render, harden and verify

Root is the sole render owner. Show the actual mock screen at 149×45 before
layout sweep/docs or review. The user's mock-first requirement explicitly
supersedes the normal live-data render for this feature phase.

Then test composited strips at 149×45 and smaller widths/heights. Pin only
measured boundaries, preserve all main-table fields via scrolling, and show
overflow hints. Verify chain/search/LP interactions, one-row and empty results,
safe text, native per-token sparks, unknown/zero distinctions, selection after
sorting, details, hub return and standalone network isolation. Use mutation
proof only for measured layout pins or another repository-mandated risk.

Run focused cases while editing. Before commit, run touched test files and
composing screen files once with isolated HOME and fast non-mounting guards.
Add only registration checks relevant to changed bindings/registry surfaces.
No full suite, networked tests, browser/clipboard calls or live data acquisition.

One final whole-feature reviewer inspects the scoped diff and named risks.
Root owns one fix wave and a scoped rereview only for production-code fixes;
minor-only findings go to followups. Commit explicit task files only and leave
unrelated branch work untouched. No push or live-data rollout in this task.

## Measured implementation

The mock render at 149×45 retains all 24 scrollable rows and all thirteen table
columns, with the three supporting panels visible. The measured full-layout
boundary is 145×40; below it the outer viewport exposes scrolling with
`widen`/`taller` hints. Named layout constants and their boundary tests live
beside the new screen, independent of the existing hub's pins.
