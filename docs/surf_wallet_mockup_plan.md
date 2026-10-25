# WALLET / SWARM — A/B density revision plan

Date: 2026-10-25. Owner choice remains A start view, B artifact detail mode.
Revision 2 implements the feedback: **“space should be used more efficiently,
and more widgets, not just cards and tables, only 1 row of cards.”** The isolated
DEMO boundary remains; proposal C and live integration are outside scope.
Tier 2 because new demo-local widgets are introduced; expected below 1,000
production lines, one implementation package, final review only. No separate
planning workspace or intermediate task review.

## Design decision

Two approaches were considered: compress the existing cards/tables, or replace
the second card row with different visual tools. Compression alone keeps the
same information hierarchy and does not satisfy the request for more widgets.
Use the mixed-widget layout: one six-card rack, then a sparkline, labeled bars,
a payment breakdown and a selected relationship diagram. Keep the existing
matrix palette, monospace typography and neutral panel frames; green represents
observed usage, yellow draws attention to follow-ups. Do not change shared theme
files. Explicit labels carry meaning without reliance on color alone.

The current PRD and selected ASCII A/B sections are authoritative. The old
12-card render and its checks are historical evidence, not acceptance of this
revision. Root determines exact heights from the rendered 149×45 composition.

## Ownership and dependencies

| Owner | Files and responsibility | Dependency |
|---|---|---|
| Planner | `docs/surf_wallet_PRD.md`, this plan, `docs/surf_wallet_ascii_mockups.md`, `docs/surf_wallet_game_mechanics.md` | Owner feedback and approved A/B semantics |
| Root implementer | `scripts/surf_wallet_demo.py`, `tests/screens/test_surf_wallet_demo.py` | Current density design contract |
| Root coordinator | Actual verification and preview paths in this plan; final measured wording in the four docs | Working render and scoped tests |
| Final reviewer | Review of the six-file diff; reversible mutation only | Owner-size previews shown and checks complete |

This is one coupled code package. The planner's four documentation files and
root's two code/test files are disjoint and may progress in parallel. Preserve
concurrent edits; do not touch unlisted production files, registry, data models,
shared widgets or themes. No additional dependencies or general dashboard
framework. A shared-file requirement is a scope issue, not permission to expand.

## Work package: denser standalone demo

### 1. Distribution semantics and regression tests

First update the relevant tests to fail on the old twelve-card layout and absent
widgets. Keep the existing deterministic 84 orders, 28 artifacts and exact money.
Derive a daily request series from timestamps and an exclusive request-status
partition. Name the bucket rule; payment state, execution outcome and follow-up
flag are different facts. Status bar counts must sum to 84 without counting a
request twice. The four open follow-ups remain their own list.

Derive onchain signal counts from the 18 contract identities, including tokens
once and excluding linked site mirrors. Rule and complete-window coverage remain
separate measurements. Positive partial history is active evidence with a lower
bound; incomplete zero is unknown. Do not sum different application units or
actor addresses across contracts. Payment amounts remain Decimal-derived;
settled/unsettled bars count attempts while paid/refunded values show IMD.

Acceptance: tests prove the distributions reconcile to their named populations,
series bins use the fixed window, money remains 62.5 paid / 1.0 refunded, and
no existing unknown/zero, subset or site-attribution behavior changes.

### 2. One hero row and mixed overview widgets

Reuse unchanged `HeroRecord`, `NewsHeroCard`, `PanelBase` and appropriate shared
sparkline helpers. A keeps REQUESTS/JOBS/WORKFLOWS/LAUNCHES/ORACLES/SCHEDULES.
Move secondary values into short, scope-labeled footers and widgets. A compact
four-column band contains request activity, request status, onchain usage and
payments. Its target height is eight rows; measure rather than infer fit.

Below, place CREATED beside a selected-artifact relationship diagram and the
four open request follow-ups. The table takes roughly two thirds of the width.
Keep a compact RECORD below. The diagram follows the selected artifact and makes
linked-contract evidence, unknown mappings and static-site absence distinct.
Use literal sanitized Rich Text at rendering boundaries. Every displayed number
must come from a fixture fact or derived count; no decorative fake chart data.

Acceptance: exactly six aligned nine-row cards, full footers, all four insights,
selected diagram and follow-up list are visible at 149×45 without outer overflow.
CREATED retains all 28 rows through internal scrolling, RECORD all 84 orders.
Only implemented controls appear in the footer; no filters or links are added.

### 3. Preserve B and navigation; replace its context paragraph

B retains its one row of six cards and left-list/right-detail split. Reuse the
payments widget below its list instead of the plain context paragraph. Keep all
existing artifact details, evidence placeholders and usage qualifications.

Acceptance: A starts by default; Enter opens B at the same ID; B arrows update
all selected content; Escape returns to the same current ID in A with sensible
scroll restoration. Both modes remain reachable at 100×30 and recover at 149×45.
CLI exports and invalid-input handling remain unchanged. No network, config,
cache, clipboard or browser side effects and no live Boardroom integration.

## Verification sequence

1. During editing run only named tests for changed distributions, geometry or
   selection in `tests/screens/test_surf_wallet_demo.py`. Test actual composited
   rows and regions, not just content strings. Await observable state.
2. Preserve offline guards and existing fixture/detail cases. Include partial
   positive and partial zero evidence in aggregate usage checks. Verify every
   fixed-height widget's final line and all labels remain visible.
3. Export A and B at 149×45 plus an unknown/static selection. Inspect rasterized
   SVGs and show the actual renders before final review. This is a fixture DEMO;
   it does not certify live sources or production layout pins.
4. Use `scripts/mutate.py` for one named distribution or geometry regression and
   prove the test reddens; restore byte for byte by inverse edit.
5. Before commit run the touched/composing demo test file once, docpins and fast
   guards. The standalone app composes itself; no production screen suites,
   registry checks or full repository suite are needed.

```bash
.venv/bin/python -m pytest tests/screens/test_surf_wallet_demo.py -q
.venv/bin/python -m pytest -m docpin tests/test_surf_registration.py tests/test_curator_registration.py -q
.venv/bin/python -m pytest -m 'guard and not mounts_app' tests -q
env -u NO_COLOR .venv/bin/python scripts/surf_wallet_demo.py --export /tmp/surf-wallet-overview.svg --size 149x45 --view overview
env -u NO_COLOR .venv/bin/python scripts/surf_wallet_demo.py --export /tmp/surf-wallet-detail.svg --size 149x45 --view detail --select site-atlas
```

## Final review and completion

Root dispatches one final reviewer with the exact `CLAUDE.md` reviewer contract,
the six-file diff and named risks: one-row geometry, derived distributions,
unknown/zero and coverage, subset/deduplication, A/B selection and side effects.
No package review, repository crawl or full suite. One fix wave for Critical or
Important findings; scoped re-review only if production code changes. File
Minor findings without expanding scope. Commit only task-owned files; no push.

Root records actual revision-2 measurements, checks, preview paths and review
below. Final handoff includes the demo run command and distinguishes this
preview from future live sources and a Boardroom entry point.

## Revision 2 execution record

Implemented the single-row overview and four insight widgets, selected-artifact
diagram and four follow-ups in the existing standalone script. Daily fixture
timestamps now span the fixed 30D window; counts, request identities, amounts
and artifact evidence are unchanged. Request states partition 84 orders as
67 completed, 5 in flight, 6 exceptions and 6 not admitted. Follow-up flags are
a separate four-item set. Onchain bars count 4 positive, 1 quiet and 13 unknown
contract identities, plus 6/18 rules and 4/6 complete windows.

TDD began with the missing metrics helper and twelve-card layout. The final
focused file passes **13 tests in 6.94 s**: semantics, exact money, whole card
footers, composited widget labels/bars, selected diagrams (including static and
unresolved site mappings), A/B identity, 100×30 scroll/resize recovery and SVG
exports. At 149×45 the overview exposes eleven artifact rows, previously seven,
with no outer scrolling. Both modes retain one six-card row. No production pin,
shared widget, theme, source or registration surface changed.

Mutation proof: allowing linked sites into the contract signal population was
KILLED by `test_widgets_partition_requests_and_count_contract_evidence_once`;
the tool restored the file. Required docpins: **12 passed**, 121 deselected.
Fast guards: **128 passed, 1 pre-existing failure**, 16,842 deselected. This is
the same SWARM TOKENS section-extraction failure reproduced against HEAD in
revision 1; its test, theme and screen remain unchanged against current HEAD.
No full suite was run.

Exported and inspected `/tmp/maxpane-wallet-dense-{overview,detail,token,unknown,static}.png`
and matching SVGs using `env -u NO_COLOR` and local `resvg_py`/Menlo. The rendered
overview/detail and additional mapping cases were shown before final review.
Independent final review: **Approved, no findings**. The reviewer inspected
both updated previews and verified ten focused cases covering composited
layout, artifact mappings, A/B identity, resize and unknown/zero semantics.
Replacing exception outcomes with follow-up flags was KILLED by
`test_widgets_partition_requests_and_count_contract_evidence_once`; the source
was restored byte for byte. The review left no additional working-tree changes.

## Historical revision 1 execution record

The following records commit `e109b1ec`, the original twelve-card overview.
It is retained as provenance and does not certify revision 2.


Implemented in `scripts/surf_wallet_demo.py` (405 lines) with the isolated
composing tests in `tests/screens/test_surf_wallet_demo.py`. The first test run
failed on the missing module. The final focused run passed 11 tests in 6.24 s:
fixture populations, exact amounts, outcome counts, signal semantics, both card
grids, five detail cases, A/B identity, narrow scrolling, resize and SVG exports.

Initial compositor checks exposed a startup highlight resetting selection;
source-ready gating and current-row validation fixed it. Raster inspection
exposed one clipped B-card subtitle, shortened to `in contracts`. Both modes
now assert whole captions, inset corners and equal card geometry at 149×45.
The overview also checks the actual matrix accent color. At 100×30 both modes
scroll; restoring 149×45 removes outer overflow.

Exports inspected and shown: `/tmp/maxpane-wallet-overview.png`,
`/tmp/maxpane-wallet-detail.png`, `/tmp/maxpane-wallet-token.png`,
`/tmp/maxpane-wallet-unknown.png`, `/tmp/maxpane-wallet-static.png`, each with a
matching SVG. The shell sets `NO_COLOR=1`; previews were exported with
`env -u NO_COLOR` and rasterized locally using the installed `resvg_py` with
Menlo. No production theme or user's environment was modified.

Mutation proof: replacing `self.selected_id = current` with a reset to
`site-atlas` was KILLED by
`test_detail_selection_changes_and_returns_without_index_reset`. The mutation
tool restored the source byte for byte.

Required docpins passed: 12 tests, 121 deselected. Fast guards: 128 passed,
1 failed, 16,841 deselected. The failure is the existing
`test_screen_css_agrees_with_application_stylesheet` in
`tests/screens/test_swarm_tokens.py`: its section extraction also includes the
unrelated SWORN Explorer CSS. It reproduces against HEAD test/CSS copies; the
imported screen and both originals match HEAD byte for byte. No task-owned file
causes or changes that failure. No full suite was run.

Independent final review: **Approved, no findings**. The reviewer verified five
named tests covering fixture totals, composited overview, A/B selection, narrow
resize recovery and exports, and inspected both 149×45 previews. Its mutation
removing the incomplete-zero safeguard was KILLED by
`test_usage_distinguishes_unknown_zero_partial_and_linked_evidence`; the source
was restored byte for byte and the working-tree status was unchanged.

Completion covers the isolated fictional DEMO only. Live sources and a
Boardroom entry point remain outside this preview.
