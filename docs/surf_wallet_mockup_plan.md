# WALLET / SWARM — A/B Textual mockup plan

Date: 2026-10-25. Owner choice: A start view, B artifact detail mode. This plan
implements the isolated DEMO specified in `surf_wallet_PRD.md`; proposal C and
live data integration are outside scope. Tier 2 because this is a new interactive
body; expected below 1,000 production lines, one implementation package, final
review only. No intermediate task review or separate planning workspace.

## Ownership and dependencies

| Owner | Files and responsibility | Dependency |
|---|---|---|
| Planner | New `docs/surf_wallet_PRD.md`, this new plan | Existing mechanics, ASCII A/B and owner selection |
| Root implementer | New `scripts/surf_wallet_demo.py`, new `tests/screens/test_surf_wallet_demo.py` | PRD and plan complete |
| Root coordinator | Existing `docs/surf_wallet_ascii_mockups.md` and `docs/surf_wallet_game_mechanics.md` selection/status updates; verification result in this plan | Working preview and measured evidence |
| Final reviewer | Read-only review of this task's diff; reversible mutation only | Owner-size preview shown and scoped checks passed |

This is one coupled package. Its fixture, state and rendering share stable
identities, so no parallel code edits are needed. Preserve concurrent changes;
do not touch any unlisted production file or shared component. A required shared
edit is a scope issue to report to root, not permission to broaden the package.

## Work package: standalone demo

### 1. Fixture contract and regression tests

Create the focused tests first. Define stable artifact IDs, deterministic order,
payment and artifact populations, fixed time windows and per-artifact usage
facts. Derive visible counts from the complete mock population. The 4 tokens
are included within the 18 contracts, and the 10 site projects are independent
of the number of delivered workflows. Include all eight required cases from
the PRD and all 28 artifact rows, not only the six rows in the ASCII sketch.

Acceptance: failing tests initially demonstrate missing demo behavior; fixture
checks prove the 84-request partition, 78/6 payment partition, exact 62.5/1.0
amounts, outcome counts, 10/18/4 artifact populations and coverage relationships.
Unknown and incomplete histories do not become zero. Linked sites refer to the
same usage evidence as their contracts.

### 2. A/B composition and navigation

Follow `scripts/surf_agent_hero_demo.py` for the twelve-card rack/export pattern
and `scripts/surf_oracles_demo.py` for table/detail selection. Reuse unchanged
`HeroRecord` and `NewsHeroCard`; use existing panels and markup-safety helpers.
Keep a single selected artifact identity and separate overview scroll state.
Compose A with two rows of six heroes and B with one row of six; do not create
a generic dashboard framework or production registry entries.

Acceptance: start A, Enter opens the selected artifact in B, B arrows update all
details, Escape returns A retaining the current identity, and Escape A / q exit.
Only implemented controls appear in the footer. Scopes can be fixed captions
rather than nonfunctional selectors. Detail pages preserve metric units,
coverage, FIRST SEEN meaning and LINKED site wording. No trading or agent data.

### 3. Geometry and offline exports

Make all cards nine rows high, six equal columns per row within one cell, with
shared edges and a one-row gap in A. Keep CREATED plus compact RECORD/payment
facts visible in A at 149×45. B must expose the artifact list and details side
by side with independently reachable overflowing content. Preserve outer scroll
at 100×30 and restore geometry when returning to 149×45.

Implement `--export`, `--size`, `--view` and `--select` exactly as in the PRD.
Use explicit placeholders for external IDs/URLs, not plausible live-looking
receipts. The app must not access the network, user config/cache, browser or
real clipboard. No background process or server command.

Acceptance: composited output contains all expected titles, whole digit glyphs,
units, DEMO marker, coverage and selected detail; no card overlap or off-screen
right edge at the owner size. SVG exports deterministically reflect mode and
selection; invalid CLI input fails clearly.

## Verification sequence

1. During implementation, run only the relevant cases in
   `tests/screens/test_surf_wallet_demo.py`. Use headless Textual Pilot and real
   `render_strips()` content/regions, not source-string or markup-string checks.
   Await observable state instead of fixed wall-clock sleeps.
2. Offline guards refuse network and intercept config/cache, browser and real
   clipboard access. Exercise all artifact types; verify unknown vs zero,
   static-site semantics, no site traffic claim, shared evidence, A/B identity,
   scrolling, resize recovery and export behavior.
3. Export overview, linked-site detail, token FIRST SEEN detail, NO DATA and
   static-site detail at 149×45. Inspect actual rasterized SVGs and show the
   owner at least overview and detail. Do this before final review. This is an
   explicitly fictional mock, so no live rendering or production pin claim.
4. Prove one meaningful assertion catches a reversible geometry or selection
   regression using `scripts/mutate.py`. Name the test that reddens and restore
   by inverse edit. Do not mutate unrelated files.
5. Before commit, run the touched/composing demo test file once as a whole,
   required docpins and fast guards. This standalone app's composing file is
   its own demo test; production screen suites and full repository suite are
   unnecessary. No mount/registry checks unless the approved scope changes.

Commands from the repository root:

```bash
.venv/bin/python -m pytest tests/screens/test_surf_wallet_demo.py -q
.venv/bin/python -m pytest -m docpin tests/test_surf_registration.py tests/test_curator_registration.py -q
.venv/bin/python -m pytest -m 'guard and not mounts_app' tests -q
.venv/bin/python scripts/surf_wallet_demo.py --export /tmp/surf-wallet-overview.svg --size 149x45 --view overview
.venv/bin/python scripts/surf_wallet_demo.py --export /tmp/surf-wallet-detail.svg --size 149x45 --view detail --select site-atlas
```

`site-atlas` is the stable Atlas portal ID. Run export commands sequentially
when they share rendering state. The script without `--export` is the
interactive preview command.

## Final review and completion

Root dispatches one final reviewer after the renders and scoped checks. Include
the exact `CLAUDE.md` reviewer contract, task-owned diff and named risks: A/B
selection, unknown vs zero, token subset, site attribution and external side
effects. No package review, no repository crawl, no full suite. One fix wave for
Critical/Important findings; scoped re-review only if that wave changes code.
File Minor findings without expanding the mock.

Root records actual verification and preview paths, updates the existing design
documents with the selected A/B implementation state and commits only task-owned
files. No push. The final handoff must state DEMO-only status and the command to
run the preview. API integration and Boardroom entry remain pending user feedback.

## Execution record

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
