# SURFBOARD hub dashboard specification

## Scope and acceptance

Add **9 · SURFBOARD HUB**, game ID `surfboard`, to MaxPane's start screen. It uses the approved
Equipment Rack design at **149 columns × 45 rows**, with four card rows and six columns.
It launches every existing SURFBOARD view and displays a live IMD command monitor.

This specification and its work-package plan are the deliverable of the current planning
task on `feature/surfboard-hub-9`. Implementation follows the plan; no production dashboard
is registered by this documentation commit. The data-consistency changes below are required
implementation work, not fixes claimed to have already shipped.

Entries 1–8 retain their numbers. Entry 1 remains Surfboard and the default/prefetched dashboard.
The new hub is a separate entrance while its design is evaluated. `--game surfboard` is added
with the CLI's existing meaning: choose the startup prefetch target; it still shows the menu.

## Four-row rack

```text
┌────────────┬────────────┬────────────┬────────────┬────────────┬────────────┐
│ ANNOUNCE   │ SWARM      │ AGENT      │ BOARD      │ LAUNCHPAD  │ POOL4      │
├────────────┼────────────┴────────────┴────────────┴────────────┼────────────┤
│ PROTOCOL   │                                                 │ SWARM      │
│            │              IMD TERMINAL                       │ TOKENS     │
├────────────┤              live events                         ├────────────┤
│ PORTFOLIO  │              and typed commands                  │ EARNINGS   │
├────────────┤                                                 ├────────────┤
│ BAY 11     │              > command                           │ BAY 12     │
└────────────┴─────────────────────────────────────────────────┴────────────┘
```

The terminal occupies columns 2–5 across rows 2–4, with one card at each side in every
lower row. Twelve card positions: seven working launchers, three future dashboards, two
empty slots. Keep the six-column topology when smaller; use measured minimum sizes and
visible scrolling/`‹ widen`/`‹ taller`, never an unnoticed reflow to fewer columns.

The existing mock script remains an independent design artifact. Production uses shared
`HeroBoxBase`/`PanelBase` primitives and a `DashboardScreen` subclass, not imports from `scripts/`.
Retain dark faceplates, inset readouts, restrained green lamps and the recessed terminal.
Palette reference: background `#141714`, card `#252a24`, terminal `#080c09`, text `#d8ddd5`,
accent `#a2d84a`, warning `#d5a24e`. Keep palette application scoped to the rack and compatible
with Textual theme contrast; legacy bodies retain their styles. No idle blinking or fake activity.

Each card has title, explicit status, two readout lines and an eight-cell meter. Give the
focused card a visible border. Its full metric definition, exact ratio/count and source clock
are available in a compact detail line above the global status bar; hover may mirror focus,
but no information is hover-only. This line also explains planned and empty cards.
Missing, stale, planned and quiet-zero states have different words, not just colors.

### Active card readouts and meters

| Card | Primary / secondary | Meter | Native destination |
|---|---|---|---|
| ANNOUNCE | latest self-post age / fired signal count | ALERT: fired / all known registered detectors | `MODE_DASHBOARD` |
| SWARM | snapshot agents online / snapshot work in progress | 24H: eight 3-hour accepted-step buckets | `MODE_SWARM` |
| AGENT | selected seat / accepted work percentage | PASS: accepted / all submitted attempts | `MODE_AGENT` |
| BOARD | recorded seat count / selected seat rank | PASS: fleet accepted / fleet attempts | `MODE_BOARD` |
| LAUNCHPAD | factory coin count / new in rolling 24h | TRADE: active coins / complete population | `MODE_LAUNCHPAD` |
| POOL4 | pool4 venue IMD price / realised staking return, trailing 7d | STAKE: vault IMD / current total IMD supply | `MODE_POOL4_USER` |
| PROTOCOL | protocol IMD burned / protocol IMD rewarded | BURN: measured split's burn share | `MODE_POOL4` |

Ratios, readiness conditions and rejected meter alternatives are fixed in
`surfboard_game_mechanics.md`. Dollar price is explicitly the POOL4 venue's `pool4_price_usd`,
not an unrelated IMD pair selected by ticker. The mock's generic price change/volume and
unscoped swap count are replaced by these source-backed metrics. PROTOCOL is always marked
experimental and its network is visible in the detail line.

Bar encoding: eight horizontal cells, with partial-cell fill if useful; always expose the
exact numeric ratio in the focused detail line. Unknown renders a dim `—`, not an empty 0%
bar. Planned uses an unlit empty casing. A zero denominator has an explicit no-data word and
no ratio. Invalid negatives, non-finite values, booleans and values above 100% are rejected.
SWARM's mini chart uses shared sparkline primitives and their common linear min–max scale
across eight consecutive sums of three provider hourly buckets; show its end time and count
range on focus. Distinguish an all-zero quiet day from a flat nonzero series by the exact count.
Never interpret the final bucket as a complete UTC interval without source evidence.

Future cards are SWARM TOKENS, PORTFOLIO and EARNINGS. They say “planned / coming soon,” make
no network requests for their future features, and cannot open a nonexistent screen. They may
take focus to explain their status; Enter shows that explanation. Empty bays are not focusable.

## Data sources and consistency correction

Keep one `SurfManager`, its existing clients and one cache writer. Extend that manager with
small public read/normalization methods; do not start a separate hub manager.

| Data family | Authority | Consumers and meaning |
|---|---|---|
| Submitted-work outcomes | `/seats/records`, one validated snapshot | Hub AGENT/BOARD, AGENT acceptance and rank, BOARD outcome rows/totals/rank, terminal seat inspection |
| Device effort | `/contributors` | Work duration, turns, token usage and explicitly labelled receipt statistics; not seat outcome denominators |
| Worker presence | `/workers` | Existing worker/fleet/status facts, with their own clock and device/slot units |
| Seat details | `/seats/{id}` | Owner, pairing, history, collaborations and node analysis; no aggregate override |
| Network monitor | `/swarm.health`, `.counts`, `.events`, `.owners` | SWARM card, matching existing SWARM headlines, terminal header/feed/status/jobs |
| Step history | `/steps/hourly` | SWARM mini chart only; do not overwrite the snapshot's 24h total |
| Announce, launchpad, pool4 | Existing validated manager/cache slots | Corresponding cards; no duplicate scans |

### One submitted-work snapshot

Normalize seat IDs once; join by token ID, never agent label, wallet or device order. Validate
the envelope count against the unique rows. Require nonnegative integer counters (reject bool)
and `attempts == accepted + rejected + failed + pending` per row. Duplicate IDs, conflicting
IDs or invalid counters invalidate the outcome snapshot as a whole. Continue serving the last
validated whole snapshot with its age and failure state; without one, outcomes/rank are unavailable.
Other data families can still refresh. No synthetic zeros, row dropping to improve rank, or
fallback to contributor outcome totals.

Canonical rank: descending accepted, descending accepted/attempts, then numeric seat ID
ascending. A zero-attempt row has no rate and sorts after a defined rate at the same accepted
count. Use exact integer cross-products for fraction comparison where needed. Fleet acceptance
is total accepted / total attempts, not the mean of percentages. Ranked population is exactly
the validated recorded-seat population; worker-only or owner-only seats are not added to it.
An absent selected seat says “no submitted record in summary”; it does not imply unpaired/offline.

Introduce a separate selected-seat outcome payload and source state so `/seats/{id}` failure
does not hide available summary acceptance/rank, and contributor failure does not hide BOARD
outcomes. History and nodes retain their detail-source state. Rename “ACCEPTED JOBS” to
“ACCEPTED WORK”; these are submitted attempts/steps, not unique completed jobs.

BOARD's outcome totals use this same snapshot. Its explicitly named RECEIPTS and effort
figures may retain contributor accounting, with its own source clock; contributor pending
must not be displayed as active work. Update BOARD captions to make its recorded-seat
population clear. Preserve sort controls and tie-breaking behavior except for the corrected source.

Rank movement compares snapshots with the same source/basis. Tag the new persisted rank basis
`seat-records-v1`; discard only legacy rank-delta baselines on migration and render no delta
for the first new baseline. Do not clear unrelated cache history or the selected seat.

For records use the existing 120-second board cadence, admitting the upstream cache of up to
600 seconds. Label successful observation “read HH:MM,” with “summary cache ≤10m” in details.
Record history may have a newer timestamp. Never patch that one newer seat into the older
fleet snapshot. Failed reads retain their earlier observation time and show stale/unavailable.
Provider timestamps, when present, are kept separately from local successful-read time.

### Snapshot and polling boundaries

Add independent last-good slots for network overview, seat records and hourly steps. Validate
persisted payloads as external input. Each publishes `read_ts`, available provider time,
availability and last-attempt failure separately; a successful response with unchanged data
can refresh read freshness without pretending the underlying record changed.

The hub should request `/swarm` no more often than every 15 seconds, with 30-second failure
backoff; `/steps/hourly` every 60 seconds with 60-second failure backoff. Use the hub screen's
normal lifecycle timer and manager tier eligibility, not a second persistent polling loop.
Full SURF collection retains the configured poll interval; a 15-second hub refresh must not
double fast-tier RPC scans. Add `SurfManager.fetch_hub_snapshot()` for lightweight source
refresh and cached assembly. One shared full-collection task and separate source-keyed tasks
join duplicate work; a global lock must not make the monitor await a slow RPC/history scan.
The hub offers due full work without awaiting it and captures whole last-good slots for its
return payload. Source tasks are shared by legacy and hub callers. Force-refresh coalesces
requests and cannot bypass in-flight protection or hammer a failed source.

Add a small overridable `DashboardScreen._fetch_data()` hook: its default calls the existing
manager `fetch_and_compute()`; the hub override calls `fetch_hub_snapshot()`. Keep inherited
panel dispatch, refresh guard and lifecycle. The hub also needs an explicit opt-out from
joining startup prefetch, after the manager's shared-task protections exist: the default
join policy stays enabled for all other screens. The hub's feed must paint while a full
startup prefetch or detached legacy scan is still running. These are narrow shared seams,
not a new scheduler or manager proxy.

Existing SWARM headlines use the shared overview values when available; they do not silently
fall back to differently defined local counts. Keep `jobsDoneLastDay`, `oraclesDoneLastDay`
and `acceptedLastDay` separate. The old observed-job history may still serve its explicitly
labelled local-history features, not global network totals.

Correct `/jobs` pagination assumptions: provide validated `limit`/`before`/`q` parameters;
page `count` is not a network total. Legacy bounded callers must explicitly state their
recent-window scope. If a consumer claims all current executing jobs, page through the needed
window with a documented cap and mark incomplete coverage; never imply a default page is the
entire network. Hub commands/feed use snapshot counts/events and do not require this sweep.

## Terminal behavior

The header uses one overview snapshot for online, working, jobs/oracles/accepted steps in 24h.
Display `time · kind · seat/source · state · objective`, with adjacent-job grouping and literal,
sanitized text. Native labels map real role/step/state combinations to queued, building,
reviewing, accepted, failed and deployed. Unrecognized states remain visible as neutral text.
No invented workspace/progress narration or mixed announce/trade events in the IMD feed.

Use the endpoint's bounded recent snapshot (currently 60 events), ordered oldest to newest
for reading. Replace/reconcile that window, not append every poll. Preserve the scroll anchor
when reading older rows; follow the tail only when already there. A refresh must not steal
input focus, clear typed text or erase command replies. Advertise “recent events” rather than
complete history; do not fabricate missing events after an outage. Command replies have a
bounded separate buffer. `clear` clears replies, preserving the live event window like imd.fun.

| Command | Native behavior |
|---|---|
| `?`, `help` | List implemented commands and source/window meanings |
| `status` | Snapshot status and service availability |
| `jobs` | Snapshot job totals/states, explicitly scoped recent-event summary |
| `seat #n`, `agent #n`, bare seat number | Canonical recorded outcomes plus separately timed identity/presence |
| `find <ENS/address/#seat>` | Resolve through existing keyless ENS/address helpers and known owner/seat data |
| `me` | Inspect the selected public wallet, or selected seat's known owner; explain if neither is available |
| `grep <text>` | Case-insensitive search of the current recent-event window; bounded result count |
| `open #n` | Open the existing AGENT view for that seat, returning to the hub with Escape |
| `open <job ID or validated prefix>` | Open the documented IMD explorer job/search URL using the existing browser-link mechanism |
| `clear` | Clear command echo/replies, keeping current events |

Commands never execute a shell, submit jobs, sign, pay, or require credentials. Only the first
command word is case-folded; arguments retain their text. Validate identifiers, input length
and URL construction. Async lookups run through bounded manager work, not network awaits in
input handlers; cancel/suppress stale command replies after navigation. Rich markup, terminal
escape sequences and links from untrusted text are inert; displayed addresses use shared
copy/explorer helpers. Website-only sound/animation commands are outside this dashboard's scope.

`/` focuses input; Enter runs a command; Escape restores card focus without leaving the hub.
Outside input, arrow keys navigate cards and Enter opens one; mouse clicks do the same. Keep
MaxPane's Tab dashboard cycle outside input; inside input Tab is normal focus navigation.
Typed `q`, `m`, `t`, `r`, `/` and digits must remain text. Escape on the rack opens the menu.
These bindings supersede the standalone mock's Tab-to-card behavior in the production app.

## Navigation and ownership

Use a new `SurfboardScreen(DashboardScreen)` and the existing installed `SurfScreen`. Route
through the app and a validated public `SurfScreen.open_mode(...)` seam; app code must not
mutate `_mode`. Switch screens instead of stacking a hidden hub under each visit. Retain
`_current_game='surfboard'` during a hub-launched body visit so dashboard cycling follows entry 9.

Pass an explicit optional return context. Escape first closes an active local editor/modal,
then returns a hub-launched body to the rack; all seven body launches use the same rule.
Explicit entry 1 clears the return context and retains its original Escape behavior. Menu
and dashboard cycling clear transient routing context. Return to the previous card focus,
terminal draft and scroll position. Switching between existing bodies within a hub visit
keeps the hub return context. Placeholder activation creates no route.

The app owns the shared manager and closes it once. A screen suspend only stops its timer;
add manager-level in-flight joining so a refresh begun on one screen cannot race a refresh
from the next. One waiter's cancellation must not cancel shared work needed by another;
shutdown must cancel/await it once. Synchronize agent-only runtime eligibility with the actual
visible mode on all entry/exit routes, including menu, Tab and return from AGENT.

Register `surfboard` on all six documented registry surfaces, alias startup prefetch to the
existing SURF manager, and add the startup test's hardcoded `ALL_GAMES` entry. No new manager
means no change to the four `MANAGER_ATTRS` lists; assert shutdown remains exact-once.

## Verification and delivery

Write failing tests before each implementation package. Commit sanitized external fixtures;
tests use a raising/injected transport and never reach the network or the real clipboard.

Required cases: 149×45 composited topology and all 12 positions; smaller viewport scrolling;
all seven destinations and return paths; entry 1 isolation; menu9 and cycle8→9→1; focused
input versus global keys; refresh handoff/cancellation/close; invalid and stale source states;
zero denominators and incomplete launchpad coverage; divergent contributor/record fixtures;
partial source failures; rank migration; hostile text; bounded feed refresh and preserved input.
Test the new data contracts and widget signatures by agreement, not duplicated implementation.

Before layout hardening, show the owner the actual keyless live render at 149×45. Then measure
the new screen's independent boundaries with normal/stress/empty/degraded/wide-text payloads.
Do not copy the mock's minimum size into a certified pin or raise the app-wide pin by guess.
Update affected legacy AGENT/BOARD/SWARM layout measurements where labels or clocks changed.
Screen CSS and `themes/minimal.tcss` must agree. Use mutation proof for changed decoder,
concurrency and measured-boundary behavior. Run touched and composing tests, applicable fast
guards and registry checks; the full suite is not part of this task unless explicitly requested.
