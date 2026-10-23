# SURF loading review and bounded implementation plan

Date: 2026-10-23. Audit base: `9511bb26`. Tier 2: shared reader behavior and
multiple dashboard data families. The owner authorizes implementation and the
previously deferred R2 verification. No full suite, new service, public schema,
endpoint replacement, or architectural rewrite is planned. Target: fewer than
1,000 production lines across all packages; one final review, no package reviews.

## Required behavior

Keep the existing client → cache → manager → reader snapshot → screen → widget
boundary. A visible scope gets its retained observations before network work,
refreshes immediately, and polls without queueing missed ticks. Leaving cancels
and drains its reads; returning uses the same identity's cache. Completed reads
must reach the UI even when they finish between monitor ticks. A changed seat,
record selection, job revision, or deployment cannot borrow another version's
facts. Source observation times survive memo hits and failures. Unknown counts
remain `None`; zero requires complete evidence. No name-based “latest contract”
or legitimacy rule is introduced.

The SWORN address reported by the owner is
`0x0da2679000ea5380d1361cc3cca7d4e8c881f766`. Root's public-reference check links
it to launch 2404 and contracts job `4f2565af…`; the NFT audit found that candidate
already retained but not inspected. This is an acquisition queue problem, not
evidence permitting replacement of every same-name deployment.

## Actual lifecycle and coverage

`app.py` registers lazy factories with one `ReaderRuntime`. Managers, HTTP
clients, cache files, projections and cancellation execute on `maxpane-reader`.
`ReaderHandle` keeps copied local payloads keyed by view and selection identity,
rejects old generations, and retains up to 16 scopes. `DashboardScreen` paints
those references on its 0.2s loading tick; ReaderRuntime owns the 30s acquisition
clock. Its monitor projects detached updates at most once per second, and skips
missed polling deadlines rather than replaying them. Direct non-reader managers
use the screen's existing guarded refresh lifecycle.

`SurfManager.set_active_view` cancels owned tasks, retains completed slots, marks
tiers due and propagates eligibility to borrowed NFT/token managers. A new
refresh drains retired scopes before acquisition. Native modes share one manager;
nested NFT/TOKENS/portfolio/detail screens use separate handles with shared
reader-side clients. Whole-request cancellation does not close clients.

| View / owner | Eligible reads and projection | Coverage / checks |
|---|---|---|
| BOARDROOM / `fetch_hub_snapshot` | Overview, records, workers/contributors, hourly; bounded work/oracle summaries; feed/market/POOL4 card reads; token catalogue/market/volume; NFT proof discovery | Returns cached projection while tasks run. Full WORK/NFT/POOL4 destination collectors excluded. Shared workflow-status mismatch reproduced below. |
| NEWS / `dashboard` | Awaited `_cycle`: chain, channel, market, recent logs, existing NFT/activity sources; detached launchpad/swarm/launch evidence | First persisted snapshot and already-completed detached result can be withheld by ReaderRuntime. Existing launch/site evidence inspected by entity owner. |
| SWARM / `swarm` | Overview/hourly, live jobs, scores/workflows, launch/site evidence | Independent source clocks; bounded site evidence has permanent-cache defect. Native collection is detached. |
| AGENT / `agent` | Workers/contributors/records, selected seat, bounded answers/jobs/oracles/rewards/runtime sources, market | Seat facts keyed by token and rewards by owner/pairing. Selection can fail to invalidate native collection throttle; reproduced. |
| LEADERBOARD / `board` | Workers/contributors/records; token catalogue and bounded launch contribution reader | One-second contribution offer has separate small publication path; no full projection per idle offer. Keep existing rapid-completion coverage. |
| WORK / `work` | `WorkReader`: recent and paginated jobs/workflows, required active/project context, optional details; atomic snapshot | Workflow completeness preserved separately from job detail coverage. Fixed-prefix optional reads starve job25; rotate and retain revision-bound observations. |
| ORACLES / `oracles` | `OraclesReader`: 60s list tier; selected detail with row-version/TTL checks | Selection and terminal-version invalidation tests pass. BOARDROOM only owns list, not selected details. No new defect established. |
| PROTOCOL / `pool4`, MARKET / `pool4_user` | Channel + market, pool discovery/state/history, separate staker reader | Single-flight tasks and scope cancellation inspected. R2 rolling windows/headers must remain intact; live duration still to measure. |
| LAUNCHPAD / `launchpad` | Detached launchpad state/history plus market | 600s source tier within visible 30s offers; no overlapping sweep. R2 rollback/checkpoint assertions remain required. |
| TOKENS / child manager | Bounded paginated catalogue and market/history/trade/provenance tasks | Entity audit validates chain/address identity and task guards. Shared launch-facts eviction prevents older selected evidence from surviving. |
| TOKEN DETAIL / per-visit child | Selected market + launch/site/job contributions | Parent owns fixes to discarded job observation envelope; memo hit currently advances contributor clock without HTTP. |
| PORTFOLIO / child | Shared token catalogue; wallet balances and claims | Identity/generation checks and cancel/reentry tests exist; include bounded lifecycle smoke, no new defect established. |
| NFT / child manager | Discovery, bounded launch/job hydration, proof/full inspections, selected README | NFT owner measured SWORN proof starvation despite retained candidate; joined workflow intent and fair probe progress are separate from proof validity. |
| WORKFLOWS guide / local manager | Bundled dated catalogue only | `POLL_DATA=False`, no HTTP/client creation. Existing integration test confirms hub stops and selection survives reopen. Keep static. |

Source TTLs deliberately differ from the visible 30s offer: WORK/oracle/live
swarm/launch lists 60s; seat/board 120s; launchpad/POOL4 600s; stakers/scores
1800s. The fix does not silently replace these policies with 30s full scans.
`surf_transport.py` shares per-host admission/cooldown in the reader loop and
per-chain heads within explicit `read_cycle` contexts. Cancellation of admission
does not reserve a future slot. Existing rolling log evidence has independent
coverage and bounded reorg policy; no claim of new provider verification here.

## Reproduced findings

1. **Persisted first paint is withheld.** `reader.py:196–214` awaits
   `fetch_and_compute` before publication; `_poll` skips an active entry task
   at 297. Offline gated manager with a valid persisted `get_snapshot` produces
   `handle.get_snapshot() == None` while loading. Real NEWS uses an awaited
   `_cycle`, so a slow source exposes this path.
2. **A completion between ticks can stay unpublished.** Reader publication at
   214 uses the returned captured payload. If a detached enrichment completed
   during that await, `is_loading == False` and `_poll` 301 has no completion
   edge left to observe. Offline probe returns `before`, cache getter returns
   `after`, and a forced monitor turn still publishes `before`. Reconcile the
   passive snapshot once after fetch, without a new fetch or extra idle polls.
3. **Seat/record changes retain the previous collection throttle.**
   `SurfManager.set_seat` / `set_record_view` mark the tier due, but
   `_fetch_visible_detail` 8040–8044 still uses `_full_started` and the old task.
   Real method probe collected seat420 at t100; selecting421 at t101 changed
   displayed identity but did not collect421 until t130. In-flight old collection
   must also be retired safely, not merely reset when already done.
4. **BOARDROOM workflow summary disagrees with WORK.**
   `SurfCardReader._work:75` counts any state except terminal/blocked as open.
   Injecting the captured workflow with `paused` produces1 instead of0;
   `future-state` produces1 instead of unknown. Reuse `workflow_is_open` and
   retain full-page/malformed-page uncertainty.
5. **Site/job joins become permanent.** Entity owner reproduced
   `surf_manager.py:5772` skipping all known site IDs, including cached `None`.
   Updated objective/project versions after one day still use old facts and one
   total job read. Newest failures can consume the three-read budget repeatedly.
6. **Launch-fact eviction defeats older-token acquisition.** Entity owner
   inserted valid launch734 into a 500-entry cache; `surf_swarm.py` coercion
   dropped it immediately. Repeated selected-token enrichment cannot survive
   publication. Preserve a bounded working set aligned with catalogue evidence
   and recent explicit acquisition, not only highest launch numbers.
7. **WORK optional detail budget never advances.** Entity owner supplied25
   recent blocked jobs; three polls made72 reads of only24 identities. Retain
   validated observations across polls and fairly admit optional work, with
   required active/project reads retaining priority.
8. **Contributor memo hits advance the source clock.** Entity owner's real
   `SwarmClient`/MockTransport reproduction showed contributor `read_ts`
   1000→1301 with no new job HTTP observations. Preserve `JobDetailRead` envelope
   and oldest contributing observation at token-detail publication.
9. **NFT candidate inspection is starved.** NFT owner measured SWORN probe rank60,
   BOARDROOM proof rank82, launch detail14/147, and linked jobs976/979 in a
   1,022-candidate backlog. Direct unchanged inspector proved ERC-721 in1.303s
   using10HTTP/10RPC. Current priority ignores explicit joined workflow NFT
   intent; recurring older work can consume bounded rounds. Additional NFT
   stage/metadata findings belong to its evidence report, not guessed here.
10. **Oversized repeated job metadata prevents NFT hydration.** NFT owner measured
    contracts job `4f2565af…` at48,594bytes, including35,283bytes of repeated
    project-version objectives. The32KiB compaction gate rejected the entire job
    and retried it forever. Keeping consumed project/source links and the exact
    workflow objective with explicit truncation reduced retained metadata to
    9,641bytes. This preserves linked acquisition evidence; it does not create a
    contract proof or collapse unrelated collection identities.

Findings5–8 and their executed reproductions are in
`/private/tmp/maxpane-loading-entities/review.md` and `findings.json`; NFT probe
artifacts are retained by the NFT owner. Findings1–4 were reproduced in memory
against current code with injected gates/clocks/payloads and no network.

## Implementation ownership and sequence

| Package / owner | Exclusive production files | Work / dependencies / estimate |
|---|---|---|
| R — `cr800_plan` | `data/reader.py`, `data/surf_work_reader.py`; WORK data decoder only if retained private detail validation needs it | Publish persisted cache before awaited acquisition; reconcile passive result once on completion; retain and fairly schedule optional WORK detail evidence with version/source clocks. Focused reader/WORK tests. ~200–300lines. |
| S — `surf_loading_entities` | `data/surf_manager.py`, `data/surf_swarm.py` | Site-facts revision/TTL/attempt fairness; bounded launch-fact retention; immediate seat/record identity refresh and old-task retirement. Own corresponding manager/swarm tests. ~150–250lines. |
| N — `cr800_nft` | `data/surf_nft_manager.py`, `data/surf_nft_discovery.py`, `data/surf_nft_rules.py`, `data/surf_nft_catalog.py` as needed | Evidence-backed workflow priority, bounded fair inspection progress, priority linked job/detail hydration; preserve per-deployment proof. NFT tests/fixtures only. ~150–300lines. |
| I — root | `data/surf_card_reader.py`, `data/swarm_token_detail.py` | Shared lifecycle helper for card workflow count; JobDetailRead envelope/source clock; composing integration tests, bounded live capture, final review and handoff. ~30–100lines. |

Paths above are relative to `maxpane_dashboard`. Test ownership follows production
files. Coordinate before touching another package's file or shared model keys.
R owns this plan. Packages can run in parallel because ownership is disjoint.
Public contracts stay unchanged; private retention fields require strict cache
validation and compatible old-cache loading. R must not fix the site cache;
S must not fix WORK or token detail. Final integration follows all packages.

## Acceptance and verification

- TDD first, then the smallest change. Decoder/state/concurrency behavior needs
  named mutation proof; no broad repeated test runs during implementation.
- Reader: blocked first fetch still paints same-scope persisted data; a completed
  detached read is visible before the next poll; late generations cannot publish;
  reentry preserves cache; missed polls/manual bursts never queue; no UI I/O or
  large payload copy; publication exceptions cannot lose good fetched data.
- WORK:25+optional jobs progress over rounds, previously loaded nodes remain,
  changed list/detail revision invalidates old evidence, source time does not
  advance on reuse, failed reads remain unknown, cancellation publishes nothing
  partial, required executing/project reads still win the bounded budget.
- Sites/launches: finite positive and negative revalidation, altered job/version
  invalidation, failure keeps prior clock, oldest pending eventually runs, selected
  old-launch evidence survives publication/reload with bounded retention.
- Identity: switch seat and record filters inside30s, including an in-flight old
  task; immediate eligible new read, no wrong-seat rows or inherited progress.
- NFT: newest joined workflow intent gets timely discovery priority, but only
  bytecode/receipt/ERC evidence proves a collection; denied/timeout candidates
  cannot starve unrelated/new candidates; staged work advances with fixed budgets
  across polls and restart; selected README remains bound to collection/repo.
- Root composes touched data/widget/screen files once, fast guards and applicable
  documentation pins. R2 focused header/admission/rolling-window regressions stay
  green. No full suite unless explicitly requested. One final whole-diff review.

Audit-only checks already run:11 focused cases passed in2.55s, covering reader
poll coalescing, old generation rejection, cross-handle drain, selection isolation,
Oracle selection/terminal invalidation, static guide lifecycle, cancelled host
admission and per-refresh chain-head sharing. These do not certify every dashboard.

### Package R implementation evidence

Reader publication now offers a passive persisted snapshot before acquisition or
the previous scope's cancellation barrier, then reconciles the passive snapshot
after an awaited fetch. Acquisition still waits for the barrier; generation checks
still reject late publication. An absent or failing projection cannot discard a
successful fetched result. The new first-paint and completed-enrichment tests
failed before the implementation; all30 reader cases then passed. A later
cross-handle test exposed cached paint waiting behind cancellation; moving only
passive publication before the drain fixed it, with six relevant reader/WORK
regressions passing in0.46s afterward.

WORK persists a private optional-detail cursor plus at most128 validated,
revision-bound observations. It admits at most24 optional reads after required
active/project context, refreshes retained entries after120s and drops reuse
after24h. The cursor advances on failed attempts and survives reload; list
state/update changes discard retained nodes. Same-version failed refreshes retain
the prior nodes and their source clock. `JobDetailRead.observed_at`, rather than
the poll timestamp, supplies optional observation time. Public fields are unchanged.

Four initial WORK regressions were red before implementation. The focused
WORK reader/decoder checks passed31 cases with101 deselected in1.32s; they cover
restart progress, failed-prefix fairness, bounded retention, version invalidation,
source clocks, cancellation and cache validation. A further same-version failed
refresh regression passed in the final six-case check above. These are scoped
checks, not a full suite or live-source completion claim.

Seven named mutations were killed: skip persisted paint; publish the captured
result instead of completed enrichment; restart the optional prefix; reuse a
changed revision; replace source time with poll time; discard retained nodes;
accept a future observation timestamp. Manifest:
`/private/tmp/surf-loading-reader-work-mutants.json`. All production files were
restored after mutation runs; `git diff --check` passed. Root owns the combined
integration run, live matrix and single final review.

## Bounded live comparison (root)

Live verification also established a metadata-stage blocker: a verified new
collection could remain under its artifact label while a factory held the full
enrichment focus. The NFT package reserves at most three HTTP requests for the
oldest proof-only newcomer, without replacing that focus or increasing total
budgets. A cache-reopen regression proves name/symbol progress and continued
factory progress. Final fresh-cache live verification reached Sworn/SWORN at the
owner's Registry after six normal polls (163.695 seconds); see the review report.

Render at149×45 before review/hardening. Use the existing cache read-only copy and
an isolated temporary cache for cold runs; never erase the user's cache. For each
scope record activation, first cached publication, first new source observation,
last completion, request counts by endpoint family, source observation clocks,
active task count and pending work. Cap each native scope at35s (one30s polling
deadline) and the targeted NFT/SWORN run at45s; report unfinished work as unfinished.

Observe BOARDROOM → NEWS/SWARM/AGENT/LEADERBOARD/WORK/ORACLES/POOL4/LAUNCHPAD →
BOARDROOM plus nested TOKENS/NFT/detail/portfolio as relevant. Use one copied-cache
cycle per native scope, not cold and warm repetitions of every scope. Controlled
offline gates cover cancellation races and reopen-inside30s behavior; record live
dispatch cancellation on navigation and one targeted warm reentry. Confirm cached
paint precedes new fetch and no catch-up burst occurs. Static WORKFLOWS requires
zero requests and zero acquisition polls. Use controlled offline gates for
cancellation/failure branches, not destructive live-provider manipulation.

For SWORN, trace exact chain/address through catalogue → candidate → inspection
→ visible record with public launch/job/workflow evidence. Compare old and new
deployments side by side until real identity/supersession evidence resolves them.
Measure request/latency changes against the same cache state; a10-request proof
latency is not whole-dashboard latency. Capture which views remain partially
observed rather than converting unfinished scans into known-empty results.
