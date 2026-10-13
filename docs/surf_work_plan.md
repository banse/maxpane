# WORK IN PROGRESS — implementation plan

Approved design: `surf_work_PRD.md`, proposal 2, 2026-10-13. Research:
`surf_work_game_mechanics.md`. New body and source contract make this Tier 2.
Target about 850–1,000 production lines; count actual changes before review.
If the complete change stays below roughly 1,000 lines, use one final review
and no package reviews. Correctness takes precedence over a line target.

## Frozen seams and ownership

`w` opens `MODE_WORK = "work"`, body id `surf-work-body`. Classes are
`SurfWorkHero` and `SurfWorkBody`, each accepting the `surf_work` keyword plus ignored foreign contract keys.
The exact payload and counts are in PRD §4; implement against that contract.
No implementer may silently revise it. Report mismatches to the controller.

| Package | Owner | Exclusive files |
|---|---|---|
| Planning | planning agent | These three `docs/surf_work_*` documents |
| Data | data implementer | New `data/surf_work.py`, `data/surf_work_reader.py`; `data/surf_manager.py`, `data/surf_cache.py`, `data/surf_models.py`; work data tests and committed fixtures |
| Widgets | UI implementer | New `widgets/surf/work.py` (hero/body/tree/detail); work widget tests |
| Integration | controller | `screens/surf.py`, `screens/surfboard.py`, `themes/minimal.tcss`; work screen/layout tests, composing registration tests, `scripts/measure_layout.py` if needed; README, Surf rules, terminal-layout documentation and followups |

These are file seams, not function seams. Shared modules have one owner.
Workers are not alone; they must not revert others' edits. No subagents or
commits from implementers. Reuse existing utilities rather than editing a
shared renderer for a local need. If a shared renderer truly must change,
assign it to the controller before editing.

## WP1 — contract and bounded reader

Dependencies: approved PRD; parent has inspected live public payloads.
Expected work units: contract/fold 45–60 min; reader/lifecycle 45–60 min.

1. Write failing normalization and count tests. Export `surf_work`, row-key
   constants and the two widget signatures; preserve existing signature
   agreement and no-data-import rules.
2. Build a pure normalization/projection module with an injected `now_ts`.
   Count every working node, not the old one-node `inflight_rows` projection.
   Deduplicate jobs/seats, distinguish missing nodes from empty nodes, and
   use node state rather than verdict for activity.
3. Build WorkReader around existing client methods: fresh pages 100/100,
   detail cap 24 with stated priority and no history merge. Preserve latest
   successful whole snapshot across list failures/busy responses; ordinary
   missing details remain explicit partial coverage.
4. Add active-only manager state, detached lifecycle/cancellation and the
   cache tier/slot. Register persisted-slot validation. Make the current
   cached payload available on first paint and refresh completion.

Acceptance:

- No API access from widgets or screen handlers; no new host pool.
- Empty success displays zeros; initial failure displays None; later failure
  retains values with the old read clock and stale state.
- Missing linked jobs/details, capped fan-out and unknown assignments are
  visible; stale cached workflow history cannot enter the current snapshot.
- Concurrent triggers do not create duplicate work sweeps; inactive mode
  starts none. Busy stops at that detail and invokes existing backoff behavior.
- Synthetic tests cover fresh/stale/empty/failed/partial snapshots, multiple
  working nodes per job, same seat on two nodes, accepted verdict with working
  state, duplicate links, malformed persisted fields and future clocks.

Named tests: `tests/data/test_surf_work.py`,
`tests/data/test_surf_work_reader.py` (including manager lifecycle);
existing composing cache/model/manager tests only where those seams change.

## WP2 — hero and work tree/detail

Dependencies: frozen PRD contract; can run alongside WP1 using synthetic
payloads. Expected work units: hero 30 min; tree/detail 45–60 min; controls
and selection retention 30–45 min.

1. Write failing compositor tests for six equal rack heroes and their counts,
   unknown values and independent source states; reuse existing card renderer.
2. Implement workflow → job → step navigation and OTHER JOBS. Keep referenced
   missing jobs visible. Display real selected details, not a text-only tree
   without interaction. Put initial selection on newest executing work.
3. Implement stable selection/expansion, local find, four filters, and safe
   workflow/job/step details. Parent paths survive descendant matches.
4. Expose small body methods/messages for the screen to route find/filter/
   Escape; widgets never request network work. Use injected `now_ts` for ages.

Acceptance:

- The approved mock hierarchy and full-height detail panel work on real
  normalized data. Refresh preserves a still-present selection and removes
  stale detail when a selected record disappears.
- Selecting each record type shows appropriate metadata/dependencies/notes.
- Filters do not change hero totals. No match is distinct from unavailable.
- Third-party brackets/markup/newlines cannot execute or distort layout;
  address cells use established copy/explorer helpers.
- Working build/review states are based on all normalized nodes; future or
  missing timestamps do not produce fabricated elapsed execution duration.

Named tests: `tests/widgets/test_surf_work.py` (including hero compositor cases). Assert composited strips, not only
internal content strings. No network or clipboard calls.

## WP3 — route, mode and lifecycle integration

Dependencies: WP1/WP2 interfaces; controller may scaffold imports/mode after
the classes exist. Expected work units: mode/route 45–60 min; composition
and registration checks 30–45 min.

1. Add Surf `w`, MODE_WORK and body/hero visibility. Add boardroom `w` through
   existing `open_mode(..., return_context="surfboard")` route shape.
2. Compose once; dispatch `surf_work` to both classes. Toggle work-active on
   mode/resume/suspend; preserve existing AGENT/SWARM runtime behavior.
3. Route `f` by mode, add `/` local find, preserve input typing and normal
   Escape/back. Refresh remains guarded. Add discoverable key hints within
   measured status-bar capacity; do not silently cut existing required words.
4. Give the work tree and detail pane independent scroll, body spare height
   and mode-specific marker accounting. Mirror screen CSS in minimal.tcss.

Acceptance: opening from Surf or the boardroom reaches the same view; back
returns correctly; one hero/body is visible; AGENT filters and all other
bindings retain behavior. No app registry or game numbering changes.

Named tests: `tests/screens/test_surf_work_screen.py`,
`tests/screens/test_surf_work_layout.py`; scoped existing Surf/boardroom route
tests while editing; composing files once before commit.

## WP4 — live render, then geometry and verification

Dependencies: WP1–WP3 working end to end. Expected work units: live preview
30 min; geometry/verification 45–60 min. Do not reverse this order.

1. Controller reads the public keyless API and renders the production body at
   the owner's 149×45 terminal size. Show the render to the owner before
   writing geometry claims, hardening pins or dispatching review. Fixtures
   and mock payloads do not count as this live step.
2. Apply concrete owner corrections, then measure in situ using the existing
   sweep approach. Add measured body pins and `#:` blocks, update the skill
   pin table and scroll registrations. Capture, stress, unavailable, known
   empty and independently partial cases must fit or honestly mark loss.
3. Prove decoder/concurrency/pin tests bite with `scripts/mutate.py`. At
   minimum: ignore second working node; count accepted verdict as activity;
   replace missing nodes with empty; merge old workflows; continue after busy;
   advance failed read clock; start sweep while inactive; move each new pin
   by one. Use targeted test selectors and inverse restore only.
4. Once before commit run touched test files and composing files, isolated
   HOME if parallel, plus fast guards. Run mounts_app registration tests
   because bindings changed; docpin tests because registration docs changed.
   Run address sweep if an address cell changed. No full suite.

Reference commands (substitute the actual touched/composing file list):

```sh
env -u NO_COLOR HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist worksteal <files> -q
.venv/bin/python -m pytest -m 'guard and not mounts_app' tests -q
.venv/bin/python -m pytest -m mounts_app tests/test_surf_registration.py tests/test_curator_registration.py tests/test_fwa_guardrails.py -q
.venv/bin/python -m pytest -m docpin tests/test_surf_registration.py tests/test_curator_registration.py -q
```

## WP5 — final review and closeout

Dependencies: live preview, scoped verification and measured geometry.
Controller owns the final review dispatch and any commit.

- One whole-change review if actual production size remains under roughly
  1,000 lines. Give the reviewer CLAUDE.md's contract verbatim, exact file
  scope, focused risk checks and latest evidence. No review-only cleanup.
- At most one final fix wave and one scoped rereview if production changed.
  Minor-only findings go in `docs/surf_work_followups.md`.
- Update routing/source documentation after facts are verified. Preserve the
  existing Japanese rack captions and prior dashboard changes.
- Commit only owned task files, report the exact scoped tests and material
  limitations (bounded local coverage, no global count or percentage).
- No server startup, background shell command, deploy, push or full-suite
  run is part of this task. No plan workspace is left behind.

## Delivery evidence

Implemented in the consolidated files listed above. Real keyless renders at
149×45 preceded layout hardening; the final live view was also rechecked.
The measured work body fits from 126×30. Counts remain qualified by loaded
page/detail coverage. The boardroom advertises `w work`; other Surf bodies
retain their existing status-bar phrase and width.

Final focused data/widget/screen/layout run: 78 passed. Existing status-bar
boundary checks: 7 passed. Guard checks: 124 passed. Mount/registration/doc
checks: 89 passed. Decoder/concurrency/layout/selection mutation checks:
15 killed and restored. The broader affected run passed 906 cases; its six
initial failures were resolved and verified with focused follow-up runs.
The final review approved all four findings after one fix wave.
