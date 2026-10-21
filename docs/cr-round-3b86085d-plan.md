# CR round 3b86085d — initial specification and implementation plan

Batch `3b86085d-df68-4d9d-9bcc-05ff5c411aed`, baseline `d4726004`.
The controller has claimed the batch. The eleven submitted requests authorize implementation;
there is no additional design-approval step. This is Tier 2 because several dashboards and
their data/screen seams change. This document is the initial plan, not completion evidence.

## Required behavior

| Area | Acceptance criteria |
| --- | --- |
| BOARDROOM heading and navigation | Remove the visible WORKFLOWS link below the first card row. Restore `IMD BOARDROOM` to the original top header. Use the existing gap above the terminal for `↑ ↓ ← → arrow keys to navigate cards · ↵ to open selected dashboard`. Preserve card, gap, terminal and overall heights. |
| FLEET card | Change jobs to **successfully completed jobs**, as clarified by the owner, using overview `job_states.completed`. Current occupied workers, accepted jobs and execution attempts are different quantities; no substitution based on a convenient existing counter. |
| TOKENS card | Outer footer shows total 24-hour volume across **all launched tokens**. The total must not depend on displayed/ranked rows or a filter. Verify population coverage, pool deduplication, units and the rolling window. |
| NFT refresh | Diagnose and fix the actual refresh boundary so opening the view and subsequent eligible refreshes retrieve and publish current data. Preserve source/cache TTL policy where it works; do not bypass it globally. |
| Work tree mouse actions | Clicking a node's text selects that node. Only its disclosure icon expands/collapses it. Preserve keyboard navigation, links/copy actions and selection across refreshes where the item still exists. |
| Oracle tree mouse actions | Apply the same icon/text separation to the answer tree; selecting text updates the corresponding detail without toggling disclosure. |
| Work tabs | Replace the `All` status choice with `Open` and add a `Blocked` tab. Blocked shows blocked jobs and workflows. In Open, OTHER JOBS excludes blocked jobs. Preserve any separate build/review filtering and search unless inspection proves they are the same status control. |
| Work retention and coverage | Load and retain jobs and workflows from the preceding 24 hours; also load every existing workflow. Keep older still-open work visible. The all-workflows requirement is a catalog coverage requirement, not permission to inflate current activity totals. |
| Work/Oracle borders | Remove borders around Work widgets and around Oracle REQUESTS / SELECTED REQUEST widgets. Preserve their titles, content, selection behavior and usable layout. |

The tree request filed under `surf.swarm` maps to the Work/WIP tree: current
`screens/surf.py` mounts table-based swarm panels for MODE_SWARM and `SurfWorkBody` for
MODE_WORK; `change_requests/catalogue.py` also lists the tree under `surf.work`. Do not add
a new tree to BUILT BY SWARM. The AGENT card order and previous RECORD-title rollback are
outside this round.

## Source facts, open questions and contract freeze

- BOARDROOM presentation lives in `widgets/surfboard/rack.py` and `screens/surfboard.py`;
  hub projection lives in `data/surfboard.py`, with manager integration owned by the controller.
  Reuse the existing one-row top header and central gap rather than inserting a row.
- `_WorkTree` and `SurfWorkBody` are in `widgets/surf/work.py`; its existing filter options
  include all/build/review/blocked. `_AnswerTree` and the two Oracle panels are in
  `widgets/surf/oracles.py`. The implementer will confirm the smallest event-handling change.
- **Frozen aggregate facts:** live overview reported 14,206 completed versus 5 executing and 14,643 created jobs. FLEET uses the completed value only. TOKENS uses retained selected-pool rolling `volume_24h` in USD for every canonical launched token, including older/inactive launches; duplicate pools count once per chain, conflicting quotes are excluded. A partial known subtotal is marked `≥`, missing data stays a dash, and zero requires observed zero or a complete empty catalogue. The footer uses existing card numerator/state fields; internal catalogue summary adds `turnover` (value/state/known/total/as_of). Hub reads only catalogue/markets, no longer unused hourly volume history.
- **Display contract:** unavailable aggregates remain `None` and paint dashes. A known incomplete token-volume subtotal uses the explicit `≥` qualifier; source clocks and detailed coverage stay in hover details.
- **NFT worker investigation:** identify whether scheduling, cache eligibility, observation
  timestamps or publication suppresses refresh. Report the specific root-owned manager seam
  if the repair crosses that boundary; do not duplicate lifecycle logic in the screen.
- **Work worker source findings:** the reader currently fetches one 100-workflow page, stops
  scanning jobs once the active hint is satisfied, and drops historical non-executing jobs.
  Existing `fetch_workflows(limit<=100, before=...)` and job pagination can cover the request.
  Walk workflow cursors to exhaustion; scan jobs until both the 24h boundary and current-active
  coverage are satisfied. The existing capped workflow-history helper does not prove full
  catalogue coverage by itself. Completed workflows remain part of the all-workflow catalogue.
  Retain linked project context. Existing `partial` represents incomplete coverage; no new
  model keys are needed. Widen the Work snapshot's existing workflow/job validation caps to
  admit the retained population; a safety cap must set partial, never certify a truncated total.
  Prefer existing transport/cache/projections; no new endpoint or hidden dashboard hydration.
- Freeze any new model keys/signatures with the controller before producers/consumers use
  them. Workers do not independently edit `surf_models.py` or `surf_manager.py`.

Two approaches were considered: extend existing readers/widgets at the demonstrated faulty
seams, or introduce a general tree/data-loading framework. Choose local changes and existing
helpers: this keeps the round reviewable and preserves polling boundaries, at the cost of
retaining view-specific tree construction. One tiny shared `ClickSelectTree` is justified by
the two actual consumers; it separates disclosure toggles from text highlighting and leaves
keyboard behavior intact. The controller explicitly assigns ownership of its new shared file.

## Work packages and file ownership

| Package / owner | Exclusive production ownership | Deliverable / dependencies |
| --- | --- | --- |
| WP1 — controller | `widgets/surfboard/rack.py`, `screens/surfboard.py`, BOARDROOM/token source files it explicitly claims, `themes/minimal.tcss` | Header/help geometry; executed-jobs and complete token-volume footer after source verification. Own corresponding rack/BOARDROOM tests. |
| WP2 — NFT implementer (`cr_data_946`) | Explicitly claimed NFT-only data/cache modules and their tests | Reproduced refresh regression, minimal repair, evidence of successful second refresh and failure recovery. Report shared manager integration to WP4. |
| WP3 — Work/Oracle implementer (`cr_agent_946`) | `widgets/surf/work.py`, `widgets/surf/oracles.py`, Work reader/cache projection modules explicitly claimed, corresponding tests/fixtures; shared click helper only if root explicitly assigns its file | Tree click behavior, clickable Open / Blocked / Build / Review choices, 24h retention/all-workflow loading, widget-local border CSS. Blocked children retain their parent context. Report theme/screen/model/manager changes to WP4. |
| WP4 — controller, after WP1–3 contracts | `data/surf_models.py`, `data/surf_manager.py`, `screens/surf.py`, shared helpers if needed, remaining shared CSS, CR catalogue | Wire completed data/widget contracts; match theme and screen overrides; run composing checks and show live render. |
| Plan — architect | This file only | Incorporate source findings and freeze bounded contract/estimate without touching production. |

WP1–3 may run concurrently only in their claimed files. Root reserves shared files from the
start; workers send required seam edits rather than editing them. WP4 follows contract freeze
and available implementations. Preserve other agents' and pre-existing user changes.

Initial production estimate: roughly **600–950 changed lines**; the Work/Oracle worker estimates
180–260 lines using the confirmed existing pagination and coverage machinery. The controller
checks this estimate before broader changes. If new crawling/storage machinery would push the
round over ~1,000 lines, revise the estimate/review plan rather than claiming this exception.
Within the bound, use **one final whole-change review**, no package reviews.

## Risks and focused validation

1. **Meaning/coverage:** fixture tests distinguish executed jobs from accepted/current workers;
   token volume includes a token outside visible top rows and does not double-count pools.
   Partial pages/source errors remain unknown or retain an explicitly dated prior observation.
2. **Refresh:** use an injected clock/transport; a second eligible NFT cycle sees changed source
   data and publishes it, a fresh cache avoids needless fetches, and failure permits retry.
   Exercise the real manager/screen dispatch seam without test network calls.
3. **Tree hit testing:** real mouse clicks on disclosure versus text, including indented and
   scrolled nodes, select the intended item; only disclosure changes expansion. Verify keyboard
   behavior and selection/detail consistency after a data refresh.
4. **Work population:** multiple workflow pages, duplicate IDs, a cursor that stops advancing,
   old active work, 24h boundary/expiry, blocked jobs/workflows, and failure after a partial page.
   Preserve known data on failed reads; the recent-history clock is injectable. Current summary
   counters must not accidentally count retained completed history as active work.
5. **Composition:** at **149×45**, verify top title/help placement and unchanged BOARDROOM card
   and terminal rectangles; inspect Work/Oracle border removal under both CSS variants. Check
   the smallest affected layout boundaries only after the live visual gate.

Start each behavior change with its failing focused test. During editing run only related
cases in the touched widget/data files and their composing manager/screen tests. Root runs
the complete touched/composing files once before commit, fast non-mounting guards, and the
required doc pins; no full suite. Use mutation proof where decoding/concurrency or a moved
layout pin requires it.

Once the integrated changes work, root shows a **keyless live render at 149×45 before** pin
sweeps, `#:` changes, completion documentation or final review. Apply owner corrections first.
After final verification/review, commit the integrated result and complete the CR batch with
the real commit hash, summary and validation evidence. Do not archive on dispatch or an
unverified render. Minor residual findings go to the existing follow-up mechanism.

NFT cause confirmed: optional explorer calls overrun the 3-second resumable slice and are retried forever. A 2-second source timeout records a failed optional response while preserving overall budget exhaustion as resumable. Four post-fix bounded live cycles completed the previously stalled observation.

## Implementation and verification — 2026-10-21

The eleven notes are implemented in the three area packages. The FLEET clarification uses
successfully completed jobs (`overview.job_states.completed`), with no fallback to working
slots. TOKENS shows the rolling USD subtotal/total from all canonical launched tokens,
including inactive/older launches, once per chain/pool. Conflicting, invalid, expired or
wrong-pool quotes are excluded; incomplete coverage is marked `≥`. The hub no longer offers
the unused hourly-volume read tier.

NFT optional public sources have a 2s deadline below the 3s inspection slice; a failed optional
response is retained so RPC inspection can advance. Global cycle exhaustion remains resumable.
The previously stalled Sworn observation advanced from October 19 to October 21 after four
bounded live cycles (10.785s, 9.581s, 10.092s, 12.354s), using a temporary cache copy.

Work now walks the workflow catalogue with retained cursors (four pages/read, explicit partial
coverage at its 10,000-workflow safety cap). Jobs retain a created-at 24h window plus older
active/project context. Interrupted history reads retain the previous snapshot; partial workflow
reads retain prior rows and observation time. Completed workflows stay accessible without
inflating current activity. Mouse text selects, disclosure icons fold, and keyboard controls
and explicit answer-popup actions remain available. Work/Oracle body panels are borderless.

Live keyless renders at 149×45 were shown before mutation/geometry hardening. BOARDROOM source
load took 9.7s and showed 14,207 completed jobs and 24 NFT collections; Work took 36.09s and
loaded 197 workflows/188 jobs. Read single-flight remains in place, including when a read exceeds
30 seconds. Layout boundaries remain BOARDROOM 143×37, Work 138×30 and Oracles 143×42. Borderless
panel height checks use virtual scroll extent, since focus can scroll the physical child region.

Affected/composing coverage: 943 distinct cases across the two scoped runs. The initial runs
found 12 outdated expectations (histogram, expired historical rows, focus-dependent child
coordinates); after updating those assertions, the three BOARDROOM files passed 429 cases and
the three Work/layout files passed 88. The other 426 cases passed unchanged. Fast guards: 128;
doc pins: 12. No full repository suite. Fourteen deliberate regressions were killed and restored:
five aggregate/navigation probes, three NFT timeout probes, two history/context probes and four
adjacent Work/Oracle height-pin probes. Live artifacts and logs are in `/private/tmp/cr-3b86085d`
and `/private/tmp/cr-3b860-nft`; these are local evidence, not runtime dependencies.

The initial final review raised one Important finding; its resolution is recorded below.

### Final review correction

The independent review found one Important issue: the first implementation retained older
`executing` jobs but dropped older standalone `blocked`/`queued` jobs. The single fix wave
retains all nonterminal states and scans until both the history window and older-open population
are covered. An early stop needs a validated overview total matching the sum of all state
counts; otherwise discovery continues to EOF within the existing page bound. Incomplete scans
preserve cached data. Listing old blocked jobs does not trigger detail fanout; recent blocked
job diagnostics and active/project enrichment remain unchanged.

A second live 149×45 preview after the fix took 34.92s and loaded 493 normalized jobs (305
blocked, 183 completed, 5 executing) plus 197 workflows. The UI scopes 18 historical context
rows separately, so its current-list and blocked-card counts intentionally differ from the full
normalized population. The premature-stop mutation was killed.

Scoped re-review: ADDRESSED / Approved, 13 named cases passed and the premature-stop
mutation was killed again and restored. The fix adds 13 regression cases, bringing affected
coverage to 956 distinct cases; the complete four-file fix scope passed 146 cases. In total,
15 implementer mutation probes and five reviewer probes were killed. Fast guards (128) and
doc pins (12) remain green. No remaining findings; no full suite was requested or run.
The IMDB task was recorded as `none`: the changes repair local readers/presentation and add
no new protocol lesson.
