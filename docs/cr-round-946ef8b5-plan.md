# CR round 946ef8b5: AGENT and BOARDROOM card details

Date: 2026-10-21. Batch `946ef8b5-6c1e-4795-8783-8a2c4bd65f30` is already
claimed by the controller. This document records the implementation contract,
work plan and verification evidence.

## Scope and approach

Tier 2: two views, shared rendering/CSS surfaces, and a small nested projection
extension. Target less than 1,000 production lines, with three disjoint owners,
no package reviews, and one final review. Existing card order, stable IDs and
the latest RECORD title rollback remain unchanged. No signing, credentials,
new speculative RPCs, or hidden dashboard hydration.

Prefer existing source projections plus a narrowly bounded card reader over
loading the full Work or Oracle detail board. This preserves BOARDROOM's
polling cost and lifecycle; it also means unread assignment facts must remain
unknown until an explicit, sufficiently complete source supplies them.

## The ten requests

| Note prefix | Target | Required result |
|---|---|---|
| `f82ffe5a` | AGENT / seat | Inner footer: working → `swarming`, idle → `ready`, offline → `offline`. Paused retains `ON`; unknown remains unknown. |
| `08851371` | AGENT / rewards | Remove outer card footer; keep USD inner footer and payment evidence in hover. |
| `38eee226` | AGENT / accepted | Swap current titles to outer `ACCEPTED`, inner `JOBS`; keep acceptance percentage. |
| `a28a52b4` | AGENT / nodes | Outer title `SHIPPED`; keep existing LAUNCHES/JOBS labels and contributing-job count. |
| `99064851` | AGENT / runtime | Show daemon base version without trailing build text; right-align green effort in inner footer with the model value above. Preserve raw version/model evidence and update checking. |
| `bfd75075` | BOARDROOM / work | Brighter green digits, inner heading `JOBS`, inner footer showing the most-running node category, e.g. `3 build`. |
| `47b57c3c` | BOARDROOM / oracles | Inner heading `JOBS`, inner footer counting distinct agents currently running Oracle work, e.g. `8 agents`. |
| `8d412790` | BOARDROOM / board | Three rows: tokens, jobs, capacity; acceptance rate in inner footer. |
| `b76bbef5` | BOARDROOM / surf-nft | Explain and restore the meaningful existing inner footer; preserve observed counts. |
| `5867d7b3` | BOARDROOM / header | Move page header into the free central gap below top cards and above terminal, with every existing height unchanged. |

## Source semantics and minimal contract

The actual BOARDROOM projection is `data/surfboard.py:cards`, not
`analytics/surfboard.py`. Keep `SURFBOARD_CARD_FIELDS` and widget signatures
unchanged. Reuse `secondary` for the WIP/ORACLES inner-footer text and `detail`
for source, clock and coverage evidence. Unknown displays as a dash; zero is
only a confirmed zero.

Extend `SURFBOARD_FLEET_FIELDS` with `tokens`, `jobs`, `capacity`, `accept_rate`,
all numeric-or-None. Reuse `data['surf_leaderboard_hero']`, already assembled
by `_swarm_board_keys` before `hub.cards`, with independent source validity:

- `tokens`: `effort.tokens`, the existing sum of contributor input/output tokens.
- `jobs`: `workers.working`, current occupied work slots; do not call this a
  distinct-job total. The controller confirmed this interpretation together with
  the token, capacity and acceptance mappings above.
- `capacity`: `workers.capacity`, with incomplete worker coverage remaining None.
- `accept_rate`: `rate.percent`, percentage 0–100 from canonical seat records;
  never divide contributor receipts by canonical attempts. Zero attempts have
  unknown rate, not 0% or 100%.

Keep existing fleet metadata for hover and its independent outer duration
footer. Do not let an unavailable worker roster blank valid tokens or rate;
do not let valid workers make unavailable contributor/record values look current.
Expose each metric's source and observation time in the existing detail string.

### Current-assignment evidence: required data prerequisite

Existing normalized `/workers` rows expose counts but no current job/node
assignments. `SurfCardReader.work_snapshot` deliberately exposes only the
overview's executing-job count plus its bounded workflow count. Oracle list
rows expose status and chain but no member assignments. Neither source proves
the requested top running category or distinct running Oracle agents.

The data owner's fresh API probe found that `/jobs?state=executing` is ignored.
The newest 100 jobs contain four executing jobs, matching the current `/swarm`
executing total. Their bounded `/jobs/{id}` reads expose a node's
`live: {seat, runtime, model, state, since}`. The older top-level `node.seat`
can name a different historical worker and must not establish current activity.

Use one bounded recent page plus at most 24 executing-job details through
`SurfCardReader`, only claiming complete coverage when the observed executing
IDs match the overview total and every required detail is valid. Commit minimal
fixtures, retain source times/failures and cancellation, and do not populate
hidden Work/Oracle detail caches or start their readers. A cap, count mismatch,
unread detail or changed job population makes the affected count unknown.
Do not infer activity from historical events, skills or `node.seat`.

For a complete current assignment observation:

- WIP counts nodes whose freshly read `state` is `working`, deduplicated by
  `(job_id, node_key)`, grouped
  into short node categories. Largest count wins, with a deterministic lexical
  tie-break. A queued/completed node must not inflate the winner. Primary digits
  remain the existing global executing-job count.
- ORACLES would require distinct live seat identities for a positive exact count;
  the current source does not establish that roster. Completed panel membership is
  not current activity. A competitive Oracle node's latest `live.seat` does not
  enumerate all competitors: the probe has not established a complete active
  roster, so such a snapshot yields `— agents`, not an undercount. Complete
  current coverage with no Oracle jobs can establish zero. Primary digits
  retain their existing assessing scope. Explain the exact-count limitation in
  hover and in completion evidence unless a complete current roster is proven.
- Missing/failed evidence yields dashes and explicit internal/hover coverage;
  confirmed empty current evidence yields zero. Do not reuse cached historical
  detail as if it were a fresh current count.

Do not claim a positive exact Oracle-agent count is supported until its roster
is proven. The controller must report that limitation explicitly; it does not
block the independent presentation changes or the proven WIP count.

The owner explicitly accepted `— agents` for unprovable counts and `0 agents`
only for proven emptiness. This resolves the Oracle request without inventing
a positive count. Unknown job templates also prevent a zero claim.

### NFT footer finding

`data/surfboard.py:cards` already emits `secondary = '<building> building'`, or
a dash. The renderer explicitly replaces that with an empty string because a
previous CR moved `N build · M open` to the outer footer. Restore the existing
meaningful secondary instead of introducing another metric. Keep the outer
build/open counts and no visible partial-catalogue notice; both use real values.

### Runtime and header boundaries

Daemon shortening is display-only. `data/surf_agent_hero.py` owns the runtime
update check and daemon comparison; never feed shortened text back into those
checks. Keep complete raw daemon, update result, checked timestamp and all model
advertisements in hover. The agreed shared hook is
`NewsHeroCard._inner_footer(subtitle, inside, frame, value_ink)`, with subtitle
as the existing formatted string. Its default behavior stays unchanged; only
RUNTIME selects the new alignment and ink.

Keep the original screen header's one-row allocation as blank space, and render
the movable header within the existing rack gap without adding a grid row or
stealing terminal/card space. Follow terminal bounds on resize. Preserve loading
and overflow hints and the WORKFLOWS navigation action; no duplicate tab stop.

## Owners and sequence

1. **Data owner:** `data/surfboard.py`, `data/surf_card_reader.py`,
   `data/surf_models.py` nested field declaration, narrowly needed manager wiring,
   and corresponding data tests/fixtures. Freeze facts above before publishing
   values. Root coordinates any manager edit; one owner writes each file.
2. **AGENT owner, parallel:** `widgets/surf/agent_rack_hero.py`,
   `tests/widgets/test_surf_agent_rack_hero.py` and AGENT-specific live composition
   assertions. Consume root's shared footer hook; do not edit the shared module,
   screen/theme CSS, catalogue or data files. Keep the latest card order and RECORD.
3. **Root, parallel:** `widgets/surfboard/rack.py`, `screens/surfboard.py`,
   `themes/minimal.tcss`, `widgets/surf/news_hero.py` footer hook,
   `change_requests/catalogue.py`, and BOARDROOM widget/screen/layout tests.
   Own integration and any final AGENT sweep changes after the AGENT owner hands
   back its files. UI tests may use the frozen contract before data completion.
4. **Planner:** this initial plan only. No production edits or subagents.

All owners are working in the same tree: preserve other edits and report
out-of-scope defects instead of fixing another owner's file.

## Verification and completion

- TDD for changed behavior, using composited rows, actual cell colors, rich
  action spans and geometry. Test each metric independently missing, confirmed
  zero and populated; long/CJK values; update and resize.
- Data tests cover duplicate job/node identities, unknown Oracle rosters,
  completed/queued nodes, ties, missing templates, truncated/failed reads, and
  independent FLEET denominators/clocks. Retain the loading-layer assertion that
  BOARDROOM never starts hidden detail readers; allow only the evidenced bounded
  card request if introduced. No real network or clipboard in tests.
- Runtime checks cover current/outdated/unknown results, base-version display,
  full hover evidence and effort/value right-edge and color agreement. Default
  shared-footer behavior must remain unchanged for other hero classes.
- Capture header/card/terminal rectangles before and after: identical card,
  terminal and viewport heights; new title lies inside the existing central gap.
  Test both CSS variants, scrolling, short/tall resize, workflow click and loading.
- Root shows the working keyless live render at 149×45 before pin sweeps,
  `#:` block changes, completion documentation or review. Then run touched and
  composing files, relevant existing source/runtime tests, layout checks, and
  `-m 'guard and not mounts_app'`; no full suite.
- One final review under CLAUDE.md's contract; one fix wave, scoped re-review
  only for production fixes. File Minor residuals in existing follow-up docs.
  Complete this batch only with all ten outcomes resolved, verification evidence
  and the real code commit hash. The approved Oracle unknown/zero behavior is
  an accepted outcome; disclose the positive-count source limitation.

## Live render and layout evidence

Fresh keyless snapshots were shown at 149×45 for AGENT #420 and BOARDROOM.
AGENT acquisition took 31.43 s; the dedicated BOARDROOM refresh took 6.05 s.
The BOARDROOM render showed four occupied slots, `2 build`, confirmed
`0 agents`, FLEET `17.1B / 4 / 1,828 / 95.51%`, and NFT `1 building`.
Preview artifacts are under `/private/tmp/cr-946ef8b5/`.

The current reader is limited to one 100-job page and 24 fresh detail reads,
with a 12-second timeout and 30-second cadence. Existing task coalescing and
exit cancellation apply. Retained active IDs are revalidated first and memory
is bounded to 24 jobs; no hidden Work or Oracle board is loaded.

The in-situ AGENT sweep retains 134×29. BOARDROOM boundary and resize checks
retain 143×37 in both stylesheets; the former header row stays allocated and
all card/terminal rectangles remain unchanged. Five UI and seven data mutation
probes were killed by named tests and restored byte for byte.

## Review and verification

The first whole-file scoped run executed 1,374 cases: 1,368 passed and six
exposed outdated test assumptions. Three concerned the changed Oracle caption,
FLEET source hover and permitted bounded hub discovery. Three predated this
round: two token-reader mocks omitted the existing `catalogue` keyword (one
also omitted the existing provenance task), and a site fixture omitted the
existing `named_ts` contract field. Test-only corrections preserve the original
checks; all six named reruns pass. No production correction was required.
The final whole-file rerun of the four corrected test files passed all 462
cases in 153.18 seconds; the other 912 scoped cases remained unchanged.

Fast guards: 128 passed. Documentation pins: 12 passed. Existing runtime-update
source checks: 40 passed. The final independent review is **Approved**, without
findings: two additional mutations were killed and restored, and ten further
named layout, workflow, data and cancellation cases passed. No full repository
suite was requested or run.

The new public API observations were captured with the owner's explicit export
approval in IMDB commit `76351297af7ccd73ec26fe53408347ebea80a647`.
