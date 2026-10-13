# ORACLES — implementation plan

Approved design: `surf_oracles_PRD.md`, 2026-10-13; source findings:
`surf_oracles_game_mechanics.md`. New Surf body and contract make this Tier 2.
Target less than roughly 1,000 added/changed production lines through reuse;
count actual size before review. Below that threshold use one final review
and no package reviews. If correctness requires a larger change, keep the
requirements and apply Tier 2 task reviews instead of compressing code.

## Frozen seams and file ownership

`Ctrl+o` opens `MODE_ORACLES = "oracles"`; body id `surf-oracles-body`.
`SurfOraclesHero` and `SurfOraclesBody` consume only `surf_oracles` plus
ignored foreign dispatch keys. Exact fields, bounds and states are frozen
in PRD §3–5. Contract changes go through the controller before implementation.

| Package | Owner | Exclusive files |
| --- | --- | --- |
| Planning | Planning agent | `docs/surf_oracles_game_mechanics.md`, `docs/surf_oracles_PRD.md`, `docs/surf_oracles_plan.md` |
| Data | Data implementer | New `data/surf_oracles.py`, `data/surf_oracles_reader.py`; `data/surf_swarm_client.py`, `data/surf_models.py`, `data/surf_cache.py`, `data/surf_manager.py`; corresponding data tests and committed fixtures |
| UI | UI implementer | New `widgets/surf/oracles.py`; `tests/widgets/test_surf_oracles.py` |
| Integration | Controller | `screens/surf.py`, `screens/surfboard.py`, `themes/minimal.tcss`; ORACLES screen/layout tests, composing registration tests, measurement tooling if needed; README, Surf rules, terminal-layout documentation and existing Surf followups |

These are file seams, not function seams. Data and UI may run in parallel
after contract freeze. Each worker is one owner, is not alone in the tree,
must preserve others' work and must report cross-file defects. Workers do
not commit or dispatch subagents. Shared-widget changes, if unavoidable,
must be reassigned explicitly before edits; prefer existing helpers.

## WP1 — contract, bounded projection and detached reader

Dependency: approved PRD and controller's verified full-member live probe.
Budget estimate: contract/normalization 45–60 minutes; reader/cache/lifecycle
45–60 minutes. Data implementer owns this package.

1. Write failing client and normalization tests; add `surf_oracles`, field
   tuples and two widget signatures to the existing models contract.
2. Add validated full-detail reader to SwarmClient using its existing pool.
   Preserve filtered AGENT reads. Commit a bounded public fixture and use an
   injected transport; no test calls the network.
3. Normalize one newest page of 100 requests. Preserve raw status, including
   `mismatch`, validate clocks/IDs, distinguish unknown from empty and expose
   partial page coverage. Chain IDs must be strictly positive integers;
   zero becomes unknown. Keep selected ID stable when valid.
4. Decode only selected detail through existing exact-hash oracle helpers.
   Validate request/job identity; use member tokenId directly if valid.
   Deduplicate hashes; retain unknown-seat answers and all typed values.
   Project members as the full `SURF_ROW_KEYS['swarm_seat_work_rows']`
   primitive RECORD row plus `seat`, with unrelated fields None.
5. Persist at most eight LRU details and 64 extracted members per detail,
   canonical point facts once each. Register persisted validation and prune
   malformed entries without discarding valid siblings.
6. Implement detached active-only collection, one coalesced task, list 60s,
   detail 120s, retry backoff 120s, terminal invalidation and 24h terminal
   freshness/reuse TTL. Expiry is not deletion: preserve valid bounded
   last-good entries across persistence as stale until successful replacement
   or eight-entry LRU eviction. Preserve old clocks on failure. A late old
   selection cannot overwrite the current request's detail.
7. Expose `set_oracles_active`, `set_oracle_request`,
   `get_oracles_snapshot` and `project_hub` dispatch; cancellation is awaited
   on shutdown. A setter must not await a network read.

Acceptance: list/detail failures are independent and explicit; no list
fan-out or extra submissions lookup; old AGENT behavior/cache unchanged;
zero/false/empty are retained; limits hold across repeated selections and
cache reload. Unknown status never receives a guessed successful outcome.

Named tests: `tests/data/test_surf_oracles.py`,
`tests/data/test_surf_oracles_reader.py`; focused existing client/cache/models/
manager tests for changed seams, including existing oracle exact-hash tests.

## WP2 — six heroes, request list and answer tree

Dependency: frozen primitive contract. Runs alongside WP1 with synthetic
payloads. Estimate: heroes/table 30–45 minutes; detail/tree 45–60 minutes;
selection/filter preservation 30 minutes. UI implementer owns this package.

1. Write failing compositor tests for six equal nine-row rack cards, scoped
   counts and unknown states. Reuse NewsHeroCard/HeroRecord and approved
   mock conventions rather than introducing another rack renderer.
2. Build left requests and right selected summary/tree in one body. Reuse
   PanelBase chrome, fit questions to terminal cells, keep panel target,
   quorum, agreement and loaded/returned answer coverage distinct.
3. Group answer branches using projected panel_state and existing formatter
   wording. Each actionable leaf holds its exact normalized Member; emit
   `AnswerSelected` for the screen's existing OracleAnswerScreen.
4. Emit `RequestSelected` when request identity changes. Preserve valid
   selection and expansion through refresh, clear old detail immediately on
   selection change, and show explicit loading/unavailable/partial states.
5. Implement local find, status and dynamic chain filters. Expose small body
   methods for screen routing. Filtering leaves hero totals unchanged and
   never performs network work. Preserve typing and escape behavior.

Acceptance: 66/34 panes, independent scrolling, unknown-seat/hash fallback,
safe third-party text and existing address treatment; blocked null members
and genuine empty data are readable; unknown `mismatch` remains visible in
list/detail and `other` coverage. No-match differs from source-unavailable.

Named tests: `tests/widgets/test_surf_oracles.py`. Assert composited strips,
exact leaf identity and behavior, not only internal string attributes.
No network, real clipboard or wall-clock waits.

## WP3 — native Surf/boardroom integration

Dependency: WP1/WP2 interfaces. Controller owns all shared screen/theme files.
Estimate: route/lifecycle 45–60 minutes; composition/registration 30 minutes.

1. Add `Ctrl+o`, mode and composed-once body/hero dispatch through `PANELS`.
   Boardroom opens the same body with its existing return-context route.
   Plain `o` sorting remains unchanged; no app registration surfaces change.
2. Activate/deactivate reader with mode/resume/suspend; cancel on leave.
   Project cached ORACLES state locally every second while visible so
   detached detail completion reaches the screen promptly.
3. Route `f`, `c`, `/`, Escape, request-selection and answer-open messages.
   Network work stays behind the nonawaiting manager setters. Preserve
   focused input typing, AGENT filters, guarded refresh and back navigation.
4. Mirror screen CSS in minimal.tcss. Give list/tree real scrollable space,
   sufficient floors and honest overflow markers. Add discoverable key
   hints within measured status-bar capacity.

Acceptance: both routes reach the same native body, back returns correctly,
only the current hero/body paints, old task completion cannot change another
mode, and existing keyboard behavior remains intact.

Named tests: `tests/screens/test_surf_oracles_screen.py`,
`tests/screens/test_surf_oracles_layout.py`; focused Surf/boardroom composing
and registration cases during edits, entire affected files before commit.

## WP4 — real render before hardening, then scoped verification

Dependency: WP1–WP3 working end to end. Controller owns this sequence.
Estimate: live preview/corrections 30 minutes; measurements/checks 45–60 minutes.

1. Read the public keyless API and render the production ORACLES body at
   149×45. Show that real render to the owner before pin hardening,
   geometry documentation or review. A mock or committed fixture is not
   evidence for this step. Apply concrete owner corrections first.
2. Measure in situ through the existing layout-sweep approach. Add new
   body width/row pins, their `#:` provenance and skill table only after
   measurement. Check captured live, long-text, unavailable, empty and
   partial/capped states; below the fit boundary content remains reachable
   and loss is marked honestly. Preserve the approved 66/34 split.
3. Prove meaningful decoder/concurrency/pin tests bite with
   `scripts/mutate.py`, restoring byte for byte by inverse edits. Risks:
   wrong request/job/hash identity; duplicate-hash conflict; inferred seat;
   false/zero collapsed; page/detail cap ignored; failed clock advanced;
   inactive fetch; late old selection painted; terminal invalidation
   omitted; each new layout pin moved down and up by one.
4. Once before commit run touched tests and composing files with isolated
   HOME and `-n 4 --dist worksteal`; run fast guards. Because a binding is
   added, run mounts_app registration checks. Because registration docs
   change, run docpin checks. Run address sweeps if address cells changed.
   No full suite. Record actual commands, results and any known limitations.

```sh
env -u NO_COLOR HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist worksteal <touched-and-composing-files> -q
.venv/bin/python -m pytest -m 'guard and not mounts_app' tests -q
.venv/bin/python -m pytest -m mounts_app tests/test_surf_registration.py tests/test_curator_registration.py tests/test_fwa_guardrails.py -q
.venv/bin/python -m pytest -m docpin tests/test_surf_registration.py tests/test_curator_registration.py -q
```

## WP5 — final review and closeout

Dependency: inspected live render, measured geometry and scoped green checks.
Controller owns review dispatch, any final fix wave and any commit.

- Confirm actual production-line size. Under roughly 1,000 lines, dispatch
  one whole-change review with no package reviews; otherwise apply Tier 2's
  task-review requirement. Hand the reviewer CLAUDE.md's contract verbatim,
  exact owned diff, named risks and test/live-render evidence.
- Review risks: source freshness/identity/caps, late-selection races,
  unknown-state honesty, native routing and composited 66/34 geometry.
- One final fix wave; one scoped re-review only if production code changes.
  Minor-only findings are filed in existing Surf followups rather than fixed
  in review. Do not create unrelated cleanup or a planning workspace.
- Update route/source documentation to verified behavior. Report bounded
  newest-page coverage, unknown statuses and any partial selected detail.
  Commit only task-owned files and preserve unrelated user work.
- No push, deployment, background shell/server startup or full-suite run is
  required by this plan.
