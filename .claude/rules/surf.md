---
paths:
  - "maxpane_dashboard/screens/surf.py"
  - "maxpane_dashboard/widgets/surf/**/*"
  - "maxpane_dashboard/data/surf*"
  - "maxpane_dashboard/analytics/surf*"
  - "tests/**/*surf*"
  - "tests/fixtures/surf/**/*"
  - "docs/imd_swarm_api.md"
---

# surf — the Surfboard dashboard and its five swapped bodies

Key history and withdrawn statements are in `docs/decisions.md`; this file states only what is
true now. Layout pins live beside their constants in `#:` blocks; the terminal-layout skill's
table names them and this file repeats no numbers.

## Keys and bodies

Surf is position 1, the `--game` default, and the dashboard prefetched at launch. Its status
hint reads `l launchpad · 4 pl4 · s swm · a agt · b brd`, in one markup run (adjacent
differently-styled runs never share a composited line). `#status-left` is `width: auto`, so an
over-long hint never shortens the phrase — the compositor crops the bar at the terminal edge and
the poll word and right label fall off — which is why the layout test asserts the **whole bar**
(right label inside the bar's region, ` poll` composited), not the phrase: the bar is whole from
`STATUS_BAR_WHOLE_FROM` in `tests/screens/test_surf_swarm_layout.py` (measured 2026-09-21; it was
never whole at the `4` body's own pin with either phrase). `l launchpad` must never shorten.

A **mode** is a whole second body with its own panels, never two panels sharing one slot. Each
of the six alternate modes swaps `#middle-row`/`#separator`/`#bottom-row`, `escape` backs out one-way, and none
is a new dashboard (no six-surface renumber; `app.py`, `__main__.py`, `GAMES` untouched):

| key | mode | body | hero |
|---|---|---|---|
| `l` | MODE_LAUNCHPAD | LAUNCHPAD COINS over LAUNCHPAD ACTIVITY left; CURVE FLOW / BURN PIPELINE / BURNKEEPERS in the rail | `SurfLaunchpadHero`: COINS / CURVE FLOW / VOLUME / CREATOR FEES / BURN QUEUE / BURNED |
| `e` | MODE_POOL4 (protocol, experimental, not on the bar) | THE SPLIT over THE RATCHET left; HATCHES over sIMD VAULT in the rail | `SurfHero` stays |
| `4` | MODE_POOL4_USER (market) | RECENT FLOW beside BURN & SUPPLY over SIGNALS; STAKERS beside IF IMD FALLS | `SurfPool4UserHero`: IMD PRICE / DOWNSIDE BID / STAKING |
| `s` | MODE_SWARM | WORKFLOWS beside LATEST LAUNCHES; LAUNCHES and SITES full-width; `x` opens the newest production launch | `SurfSwarmRackHero`: FLEET / OUTPUT / WORKFLOWS / LAUNCHES / LATEST WORKFLOW / SITES |
| `a` | MODE_AGENT | seat-card row with COLLAB/NODES; RECORD full-width beneath | `SurfSwarmAgentHero`: SEAT / ACCEPTED JOBS / WORK / REWARDS / RANK / STATUS |
| `b` | MODE_BOARD | Recorded-seat LEADERBOARD beside FLEET | `SurfSwarmBoardHero`: TOP SEAT / RECORDED / ACCEPT RATE / OUTCOMES / WORKERS / EFFORT |

The legacy `SurfHero` remains mounted and dispatched for its existing contract,
but `_SURF_HERO_MODES` is empty: every active mode now has its own hero. The
legacy BOARDS shortcut agreement remains tested separately. Alternate heroes
are composed once at startup and toggled with the
body — curator's per-mode hero, not one widget with a mode branch. `_SCROLL_COLUMNS[mode]` names
the containers whose scrolling lights `‹ taller`; every swarm and agent container that can scroll
is registered there, bound by the layout test. Surf's `e` and curator's `e` (export), and the
two `l`s, are separate bindings on separate screens. The feed threads replies behind an
expand/collapse toggle, with NEW REPLY on the rail so a collapsed thread still announces itself.

## LAUNCHPAD rack hero (`l`)

`surf_launchpad_hero` projects the existing launchpad slot and current ETH/USD
quote. Factory and swept counts remain separate; incomplete history qualifies
COINS, CURVE FLOW and BURNED without degrading independently readable fees or
queue getters. The queue uses previewBridge readiness. Event-derived burned
IMD remains distinct from protocol totals.

VOLUME reuses the rack's two-hour conversion over eight completed 15-minute
buckets. Coverage, window end, volume read and quote read remain independent;
unavailable quotes show no invented total or chart. Native values and the hero
share one slot assembly in both full-cycle and hub refresh paths. Source clocks
are captured with their values before detached reads can replace the cache.

## Tiers, clocks and degraded groups

`TIER_LAUNCHPAD`, `TIER_POOL4`, `TIER_POOL4_STAKERS` and the swarm tiers (`TIER_SWARM`,
`TIER_SWARM_SCORES`, `TIER_SWARM_LAUNCHES`, `TIER_SWARM_SEAT`, `TIER_SWARM_BOARD`) are spawned and never awaited, with independent last-good slots and their own `as of HH:MM` on a slower clock than the
title bar's. `SOURCE_POOL4` (`p4`) is the **eighth and last** degraded group — that name took the
worst-case title row to exactly the pinned width — so the staker sweep and the swarm tiers
**name no group at all**, not even with nothing to serve: they serve last-good behind their own
marker plus a conditional `stale` word derived from the two tiers' TTLs summed
(`STALE_AFTER_S = 2400 s` on STAKERS), never chosen. A false degradation is the same defect as a
missed one (`tests/data/test_surf_manager_pool4_market.py::test_a_sweep_with_nothing_to_serve_names_no_group_at_all`).

## POOL4 protocol body (`e`, MODE_POOL4)

**Every panel title carries the network word** — `· MAINNET`, `· SEPOLIA`, or `· —`. The view
was built against a live Sepolia deployment and still renders it whenever no mainnet hook has
been adopted. One helper produces the word (`widgets/surf/_pool4.network_word`) and it is an
**allowlist**: anything outside `POOL4_NETWORKS` — including `None`, which means no sweep has
completed — renders the em dash. The widget restates the tuple rather than importing `data/`,
and its test asserts the two agree in both directions, so a third network reddens the suite
instead of blanking five titles.

**Discovery is the security boundary of this view, and the fingerprint does not hold it up.** The
hook address is discovered from the dev's announce channel, which is attacker-writable by design,
so **provenance is the only unforgeable gate**: only a *self-post* (`from == to == announce`) is
a candidate. Everything else is a filter. The chain fingerprint: the low 14 bits must **equal**
`BEFORE_INITIALIZE | BEFORE_ADD_LIQUIDITY | AFTER_SWAP` — equality, not a subset test, and not the
address's visible tail (the hook ends `6840`; `0x6840 & 0x3FFF` is `0x2840`; the plan, PRD and
research doc all said `0x840`, and both failure modes are committed as attack fixtures under
`tests/fixtures/surf/pool4/`). It is forgeable — a `0x2840`-shaped address mines in ~20,000 tries,
four of five getters are liveness checks, `token()` is chosen by the candidate — so:

- **Never re-nominate from storage.** The persisted-adoption defence was deleted (A27): a
  hand-edited cache file returned *adopted* against a real attempt. If a self-post ages out of the
  channel window, read more of the channel or re-establish provenance from the chain.
- **The announce channel has not named the mainnet hook**, so discovery correctly refuses it and
  the operator accepted `pool4.imd.fun/docs` as a *candidate* source. That widens the trust
  surface, and HATCHES discloses it: `pool4_discovery_source` is its own payload key, a
  docs-sourced adoption renders `⚠ via docs`, a dev-signed one renders plainly, and
  `unattributed` reads at least as weakly as `docs` because `None` is where a producer bug comes
  to rest. A self-post overrides the page. Source words are restated in the widget with an
  agreement test against `POOL4_DISCOVERY_SOURCES`.

**Mainnet is a different protocol from testnet** and self-adapted because nothing was a
constant: the reward share rose by half, the reserve floor fell five orders of magnitude. What did
not self-adapt is *structure*: mainnet inserted a Reward Distributor, so the vault is three hops
from the hook, the split is three-way (85 burned, then stakers / bonding / nodes from the
remaining 15), **bonding has no getter** — it is the remainder, derived and labelled as derived —
and mainnet's `burnSink` is a **pass-through BurnExecutor**, not `0x…dEaD`: what sits in it is
queued, not burned. No *separate* bond contract is named by anything the dashboard reads, so the
HATCHES row is `unknown` ("we did not look"), never `absent`. Three hook event signatures have no
recovered pre-image (one survived a 538,740-candidate sweep); they keep operand-shaped names and
the decoder keys off the topic0 constant — never invent a signature string. Some ceiling tests
still have no mainnet fixture.

Two testing traps: a test written as "point it at Sepolia and watch these fields go `None`"
passes for the wrong reason (the getters exist on both chains; drive absence with a getter made to
revert), and `inventoryCap() == tokensInPool()` holds on Sepolia only because of the no-decay
sentinel — on mainnet they drift by whole tokens between events.

## POOL4 MARKET body (`4`, MODE_POOL4_USER)

`e` is the protocol and `4` is the market: both read the same `TIER_POOL4` sweep and answer
different questions. Two-thirds of this body is the 62 keys `TIER_POOL4` already produces; the
delta is four fast-tier reads, one pure depth-ladder analytics module, and a long-tier sIMD
`Transfer` sweep on `TIER_POOL4_STAKERS` / `SLOT_POOL4_STAKERS` with its own
`pool4_stakers_as_of_hhmm`. A digit key on a *screen* is an established pattern (curator's filter
presets) and collides with nothing app-level.

**Six rack hero cards** (2026-10-12): IMD PRICE, sIMD RATE, STAKING, VAULT,
DOWNSIDE BID and DRIP QUEUE. The manager projects existing sources into
`surf_pool4_hero`; source clocks belong to the captured values. Holders retain
the separate staker fold clock; incomplete folds show a lower bound and another
network's count is unavailable. Burn remains in the chart panel.

**`SurfPool4Flow` lives in this body only** (since 2026-09-14). `_do_refresh` dispatches RECENT
FLOW with `self.query(SurfPool4Flow)` rather than `query_one` — `query_one` does **not** raise on
multiple matches in this Textual version, it returns the first — and the loop stays. The
per-instance keywords (`quiet_mainnet`, `quiet_as_of`, `classes="market"`) are vestigial and
filed as F15 in `docs/surf_pool4_followups.md`.

**The native body panels omit `as of` markers.** Rack heroes show dated partial
or stale reads in their outer footer, with independent source details on hover.
STAKERS instead gains `stale` in its
concentration footer only when its 1800 s fold and the title bar drift further apart than healthy
operation explains — `QUIET_NETWORK`'s shape applied to time, costing no row. The `e` body keeps
all of its markers.

**Two honesty contracts.** The ladder quotes the position *as it stands now* and never promises
protection — a `rebalance()` closes the backstop band and redeploys it, so *guaranteed*,
*protected*, *safe* and *floor* are forbidden in its composited body (checked against pixels, not
by source grep). An **unread** band is not an **absent** one: both used to paint
`band used 0.0%` byte-identically. STAKING reports a **realised** trailing return from `Dripped`
events over a measured 7-day window, never the delivery cap, never the bare word *APR*.

**Its pins are its own** (`SURF_POOL4_USER_FULL_LAYOUT_{COLUMNS,ROWS}`), measured in situ. Since
2026-09-12 this is surf's *wide* body: STAKERS prints all 42 characters and is the binding
panel; the copy icon paid for its two cells by windowing (`_ADDR_SHORT_COLS` at the pin, the
whole address only above it), not by moving the pin. A change to a cell's contents here is a
change to a pin — re-sweep, never adjust to a guess. PRD §4.1 carries the whole trade.

## SWARM body (`s`, MODE_SWARM) and AGENT body (`a`, MODE_AGENT)

Answers what the IMD swarm — the agent workforce this repo's own branches are built by — is doing:
who is online, what is executing and on which seat, what has launched, how fast work moves; and,
on `a`, one seat's own record. Rebuilt 2026-09-21 (swarm v2, `docs/surf_swarm_v2_implementation_plan.md`,
WP0–WP7). Its control-plane feed reads **one** keyless source under two names (`SWARM_API_HOSTS`:
`api.imd.fun` and its Railway host — one deployment, measured by `/version`, rotated per request,
never shrunk; `follow_redirects=False`, a redirect is a host nobody allowlisted). The same source
serves `/oracle/requests` (paged) and `/oracle/requests/{uuid}` for RECORD panel outcomes:
`data/surf_swarm_client.py` is the HTTP layer and nothing else; `data/surf_swarm.py` is the pure
fold — no network, no clock (`now_ts` injected), no Textual; the shared rollups are
`analytics/surf_swarm_signals.py`, imported by fold and widgets alike so both count with one
implementation. The contract is `SWARM_KEYS` and `SWARM_WIDGET_SIGNATURES` in
`data/surf_models.py`; the screen's dispatch table is bound to it by identity, and every row dict
carries exactly its `SURF_ROW_KEYS` fields.

**The job list is gated on `/health`'s own counters.** The live tier reads `GET /health` every
run. `GET /jobs` (one bounded recent page; validated pagination is available, no ETag) is re-fetched only when one of the host's
counters (`connectedDaemons`/`activeEnrollments`/`workingNow`/`acceptedLastDay`, every `pending*`)
has moved since the manager last saw them, or when `SWARM_LIST_CEILING_S` has elapsed regardless.
`GET /jobs/{id}` follows for every **executing** job (plan §1.5; a 404 drops the detail, never the
row or the read; an all-host `503 busy` stops the fan-out at that id, stores nothing and backs the
tier off in both tiers -- `SurfManager._swarm_details`, F-S3 -- and the live tier also puts its
list gate back). The slow tier (`TIER_SWARM_SCORES`) sweeps the newest `SWARM_SWEEP_CAP` details
plus `/skills` and `/workflows` (`?limit=SWARM_WORKFLOW_PAGE_SIZE`) on its own
clock and feeds WORKFLOWS and the internal seat-selection fold; `/skills` is still
read and folded for the parked CAPABILITY (below), which no body mounts; `swarm_throughput` is folded off the **live** slot because its parked widget retains
the live marker (two clocks never meet behind one `as of`). A third slot, `SLOT_SWARM_JOBS_SEEN`,
is a map of every job either tier has read (pruned by age and cap, stored only when it changed so
the 60 s tick does not rewrite the cache file for nothing): it is the sole source of `completed_24h`
and retains nodes for the internal most-active-seat selection after the host's window moves past them.

**The AGENT body shows one seat's lifetime record** (`docs/surf_agent_seat_details_handover.md`).
`i` saves the selected token; without one, `choose_seat` uses the most active seat from the internal
job-data roster. The old ROSTER and FEEDBACK tables are retired, along with Enter-on-roster selection,
`select_seat` and the cursor path. The roster remains an internal fold, not an emitted contract key.
`GET /seats/{tokenId}` runs on `TIER_SWARM_SEAT`, one seat per cycle. `set_seat` only marks that
tier due, with no network await in a handler. `SLOT_SWARM_SEAT` stores
`{"seats": {"<token>": {"state": "ok"|"unknown_seat", "seat": dict|None, "read_ts": float}}}`,
plus an optional `seen_ts` (F-S2). Keep the six most recently read: newest `seen_ts`, else
`read_ts`, first, ties by numeric token ascending. `read_ts` is when the record last changed
(the seat's `as of`); an unchanged read of a seat that is not already first stamps `seen_ts`
instead, so polling one seat writes nothing. A stored `seen_ts` is validated like `read_ts` and
may not precede it. Keys are canonical
decimal strings. Validate
entries independently, retaining valid siblings; timestamps use the cache's clock-skew tolerance.
Legacy `{token, state, seat}` slots migrate using their stored slot timestamp, without a schema
version bump. Identical seat content keeps its timestamp and does not rewrite the slot.
Only the selected token's entry supplies its record and `as of HH:MM`; switching seats never
borrows another seat's numbers. With no entry, the state is `"pending"` before a completed read,
`"busy"` after a busy response, and None after another failure.

A busy response is HTTP 503 with a JSON object whose `error` is exactly `"busy"`. Rotate through
the unchanged host pool; only all hosts answering busy yields `SEAT_BUSY`, from `fetch_seat` and,
since F-S3, `fetch_job`. Mixed failures stay None. Busy reads use normal failure backoff and preserve last-good. `swarm_seat_read` distinguishes
`"busy"`, `"failed"` and None independently of the cached record's state. Empty seat-backed
cards show `busy`; with a record, RECORD's title appends yellow `busy` after
its own `as of HH:MM`. Shed the seat hint first if space is tight. Other read failures add no
title word. Busy without a record gates the runtime facts, just like pending.

AGENT mounts `SurfSwarmAgentRackHero` (`widgets/surf/agent_rack_hero.py`) above
native RECORD. The approved rack has two equal rows of six nine-line cards, with
one blank line between: SEAT / ACCEPTED / EFFORT / REWARDS / RANK / STATUS, then
OWNER / RUNTIME / MODELS / FEEDBACK / COLLAB / NODES. The old `SurfSwarmAgentHero`
and `SurfSwarmSeatCards` remain parked; no production body mounts them.

`surf_agent_hero` is a primitive projection with independent state/read timestamps
for all twelve cards. A successful unchanged detail read confirms only that seat
in manager memory; persistence still records content changes. Restored detail is
dated stale until confirmed. Capture detail, rewards, runtime checks and activity
before detached reads can replace them. A seat switch rebuilds the entire detail
family together; reward identity remains the current owner plus pairing timestamp.
Each retained stale/partial card names its state and own source time. Missing,
pending, busy, never-paired and known-empty data remain distinct from zero. A
retained never-paired result has an explicit stale state and confirmation time;
only a successful new read clears that qualification.

ACCEPTED and RANK use the selected token's canonical `/seats/records` outcome.
ACCEPTED shows accepted attempts as digits, attempts on the inner bottom border,
and percentage plus a meter outside. Zero attempts says `no attempts`; no record
says `not recorded`. EFFORT shows contributor wall-clock hours and lifetime output
tokens; input and cached-input tokens are excluded. Rank change remains in its
literal tooltip and per-seat persisted history. These sources stay independent of
seat-detail availability.

STATUS lists working, capacity and device counts from workers. Its inner bottom
border shows the newest seat activity as `worked HH:MM` or `accepted HH:MM`;
the full date and independent detail-read clock live in its tooltip. Feedback
`reviews[].sentAt` is not seat activity. The outer footer uses the shared last-work
meter: BUSY has full green segments; IDLE has a grey label and green drains
to orange over 24h, then orange drains to empty by 72h. OFF is red with empty
segments; paused and unknown stay explicit. Partial worker coverage never invents
an offline seat or a complete capacity sum. The shared meter fold is also used by
the dashboard rack.

REWARDS (F-S5, 2026-10-02, `docs/surf_agent_rewards_spec.md`) replaced REVIEWED: IMD
paid to the seat's current owner since `pairedAt` by a known payer -- a transfer *from*
`REWARD_DISPERSE_CONTRACTS` counts only when the transaction's **sender** is in
`REWARD_DISPERSERS` (Disperse is public), one *from* `REWARD_DIRECT_PAYERS` counts as it is --
split evenly over the owner's IDMD `balanceOf`, USD at this cycle's `imd_price_usd`.
`SurfClient.fetch_seat_rewards` fails the whole read (None) on a page bound hit, a malformed
row, an unreadable sender, decimals or balance, or zero seats: a partial total never looks real.
`SLOT_SWARM_SEAT_REWARDS` keeps six seats keyed on owner + pairing (a sold seat never inherits
a total); a per-seat 600 s clock inside the seat task, 120 s failure backoff.
`swarm_seat_rewards_state` is `ok` / `pending` / None, so not-read and could-not-read differ.
`SLOT_SWARM_SEAT_RANK` persists each seat's `{rank, prev}`. Update it only on
an observed valid rank change; unchanged reads keep the delta. A first observation
has none; unranked/unavailable/not-listed reads hide it without erasing history.
OWNER uses `address_text` and the package `EXPLORER` for its verified ENS/address,
copy icon, link and paired date. MODELS shows advertised `runtimes[].premiumModel`
pairs, fitted with an explicit ellipsis; more than three show two plus `+N more`.
Its tooltip retains every raw model/effort pair. An empty served list says
`not advertised`; an unread list is unknown. RECORD's model is what actually ran.
FEEDBACK lists sent/submitted/queued review messages.

RUNTIME compares only `claude` (`@anthropic-ai/claude-code`) and `codex` (`@openai/codex`)
against keyless `registry.npmjs.org/<package>/latest`. `NpmRegistryClient` owns the fixed
allowlist, a five-second timeout and one attempt per package. Strict pure SemVer comparison
places prereleases below the corresponding release and never orders malformed values.
`set_agent_active` gates npm work to AGENT with a selected, read seat; original seat runtime
ids select at most two requests. `TIER_SWARM_RUNTIME_LATEST` / `SLOT_SWARM_RUNTIME_LATEST`
keep a one-hour check TTL **per package**, including failed checks, across seat changes and
restarts. A failure replaces the checked version with None, never an up-to-date claim.
`swarm_runtime_latest` and `swarm_runtime_as_of_hhmm` are per-runtime dictionaries.
`swarm_fleet_daemon` is the unique plurality `(version, count, reporting workers)` from the
already-read BOARD workers slot; invalid/missing version strings do not vote. Ties and empty
fleets have no reference. Daemon comparison is equality only, never hash ordering.
An outdated runtime has an explicit update subtitle; a differing daemon keeps a
trailing `↑` within the fit budget. A valid Claude CLI version drops its display-only
banner suffix; the full runtime and daemon remain in the literal tooltip. A
clipped daemon retains its label, ellipsis and update arrow and marks `widen`. The RUNTIME
box tooltip is a literal `Text`: npm latest/version/check time, fleet reference/count, or
`update check pending` (runtime id absent from `swarm_runtime_latest`: not yet checked),
`update check unavailable` (a checked version of None: the read failed), `runtime not checked`,
`no fleet majority`; unread details retain no previous version claim. No new workers read,
no new degraded group. Cached AGENT refreshes also offer the existing guarded
runtime check, using the same eligibility, TTL and endpoints.

COLLAB shows the collaborator count as digits and the top teammate/count in its
outer footer. Its tooltip retains the ordered teammate list. NODES lists accepted
counts by node, with two plus `+N more` when there are more than three. Its tooltip
retains every node's accepted/attempts counts and rate. Node ordering and source
rows are unchanged; large counts shorten without cutting a number. Runtime, ENS,
model and node text fit with explicit ellipses. Every refresh clears old tooltips.
The former third card row (`SurfSwarmNodeCards`) stays removed; worker metadata
remains in BOARD and RECORD fills all remaining space below the rack.

The AGENT body's title bar reads `SURFBOARD · Identity.md AGENT #<token>` (from
`swarm_seat_selected`, em dash when none; green, owner 2026-09-22) in place of IMD price and
parity, and prints no degraded list: its groups name the other bodies' sources, and every AGENT
card carries its own unavailable state. The row hint and the LP warning stay. Every other body
keeps all of them.

The owner's ENS name is read in `SurfManager._resolve_seat_owner` after a good seat read:
`SurfClient.fetch_ens_names` (`data/ens.resolve_names`, forward-verified, over the state pool
through `rpc_common.multicall_chunks`), held in an `ens.NameStore` with its name and miss TTLs,
so a nameless owner is not re-resolved every tick. A raise or an empty answer is a miss; OWNER
shows the address.
RECORD columns are `when · job · node · state · model · took · tok · panel · answer`.
The title is `RECORD · all · not completed · as of HH:MM`: fixed click actions
`screen.record_filter('all')` / `screen.record_filter('open')`, revalidated by the screen.
The active mode is bold accent, the inactive mode dim. A dim, unclickable `SEAT_HINT`
(`type 'i' to change seat`, owner 2026-09-24) ends flush with the answer column's text, after any
widen marker, only where it fits whole; it never adds a title line or moves a pin. `record_state` in pure analytics
owns the displayed state, shared by widget and manager. `not completed` keeps every state
except completed, including None. `record_window` (`analytics/surf_record_filter.py`, with
`record_selected` / `record_view`) filters first, then clamps the view to
40..400 and takes its rows. Older counts are after filtering; empty filtered views say
`no incomplete records`, unread remains unavailable.
`screen.record_more()` adds 20 to screen-owned `record_cap` (initially 40, maximum 400),
keeping cursor and scroll position. Its footer target is bold dim `more`; at the cap only
the remaining older count stays. Both actions call the I/O-free `SurfManager.set_record_view`,
which stores cap/open_only and marks `TIER_SWARM_SEAT` due, repaint cached rows, then schedule
the usual guarded refresh. No handler awaits network. A seat change resets 40/all in manager
and screen; the view is not persisted, and filter toggles keep the cap.

**`f` filters RECORD** (owner 2026-10-02, `docs/surf_record_filter_spec.md`). AGENT-only,
`priority` like curator's `f`; elsewhere a no-op. It opens `SurfRecordFilterEditor`
(`widgets/surf/swarm_record_filter.py`, on THE LIST's `widgets/filter_editor.FilterEditorBase`;
imported from its module, **not** in the package `__all__`, because `_ALL_WIDGETS` is derived
from `__all__` and requires `update_data`) in place of RECORD only; the hero and the seat cards stay drawn above it (owner, 2026-10-02 --
it first replaced the cards too).
The editor posts surf's own `RecordFilterApplyRequested` / `RecordFilterResetRequested`, never
curator's. NODE / STATE / MODEL are checkboxes built from the seat's own rows on every open
(`record_filter_choices`, most frequent first, plus anything the stored filter selects); WHEN,
PANEL and ANSWER are dropdowns; TOOK and TOK are from/to ranges validated by
`analytics/range_filters`. Inside a group options OR; groups AND. `f` or APPLY validates through
`parse_record_filter` (an invalid range stays open, naming its field), which turns WHEN into a
fixed `since_ts` from `screen._clock` — the only clock read. An empty filter clears the stored
one and shows `all`; RESET ALL clears only the draft; `esc` closes the editor first, then leaves
the body. Leaving AGENT closes the editor and keeps the applied filter; a seat change (`_seat_entered`
or a refresh's token change) clears both, in the manager too — also when the view was set before
the first seat arrived (final review I-1: the manager's copy was skipped while the old token was None).
The title gains a third mode word, `filtered` (`screen.record_filter('filtered')`), only while a
filter is stored; `filtered` shows the filter alone (open_only False), `all` / `not completed`
keep it for a later click. Only the **base** groups (NODE, STATE, WHEN) shape `record_window`
and so the manager's answer, job-detail and oracle read windows (`SurfManager.record_spec`, set by
`set_record_view(cap, open_only, spec)`, I/O-free, cleared by `set_seat`); MODEL / PANEL / ANSWER /
TOOK / TOK need a row's reads and never narrow what is read. A row they cannot judge yet is
counted in the footer as `not read yet`, or yellow `unavailable` when its read failed — never shown
as a match and never dropped. The footer reads `summary · N match · N not read yet · N
unavailable · +N older · more`; the summary clips first and goes below 8 cells, then the count
words shorten (`_COUNT_WORDS`: `not read` / `unread`, `unavail`, `+N`), never a figure or `more`
(F-RF3: the worst case is 53 cells at its shortest, the 60-column floor leaves 55); nothing to
show, wait for or page to is `no matching records`.

It shows every lifetime `work[]` attempt; its `state` is the attempt's `status` unless
`accepted` (then, or with no status served, the job's state). It shows `MM-DD HH:MM` of `submittedAt` (else `acceptedAt`); the job
cell is the id's first eight characters, linked to `explorer.imd.fun/jobs/<uuid>` for a canonical
UUID (`address.job_text` on `_fmt.JOB_EXPLORER`, the allowlisted `explorer.IMD`; anything else
plain); the node cell is the key's lower-cased `NODE_TITLES` word (an unknown key fitted to
`NODE_COLS` with `…`). Launch and submission hash are not columns since 2026-09-22 (owner: the
answer gets the room); a failed attempt's *read* answer is red; the unread words keep their own dim/yellow (F65). RECORD alone has no blank row under
its title (its own `DEFAULT_CSS`, owner 2026-09-22). A null `daemonVersion`
displays `not reported`; missing daemon and counter fields remain unavailable. Review-accepted and work that won a
job are different counts. A 404 `unknown_seat` is a real negative: row 1's SEAT box names `IDMD #N` / `never paired`
through `swarm_seat_selected`; RECORD still shows the tokenless state (F39). Any other
seat 404 rotates and fails. A submissions 404 is local to that job and never rotates the host pool.
The owner address links the package `EXPLORER` (Ethereum, F31).

**`None` vs `[]` is decided in the manager, never the fold.** Every `*_rows` fold answers `[]` for
`None` and for empty input alike; only the manager knows whether the read happened, so a list never
read publishes `None` and a read list with nothing in it publishes `[]` — checked against the
argument (`jobs is not None`), never after a fold or by truthiness (F-C: `if jobs` once published
`None` for a successful read of an idle swarm). `SwarmTableBase` paints the two apart: `None` is a
yellow `unavailable` row, `[]` the panel's own real-empty word; the hero's boxes render `0` for a
zero and `unavailable` only for `None`, and `tests/test_surf_registration.py` probes the two AGENTS
halves (`0/--`, `--/0`) under a full outage and excludes the three bare-count boxes with a reason.
`seat_teammates` explicitly preserves the collaborators-list distinction itself. The legacy
`swarm_seat_work_rows` path still conflates a missing `work` list with an empty list (F41).

**Every third-party string is escaped at the widget** (`markup_safety.sanitize_cell`); every
onchain address or transaction hash uses `widgets/address` with its row's `chain_id`
(`explorer.for_chain_id`; unknown → no link), except the seat owner, which uses the package
`EXPLORER` by the decision above, and an address inside a WORKFLOWS failure or objective, which
gets its copy icon and **no** link (`_icons.link_prose(..., explorer=None)`: `/workflows` serves no
chain id and nothing joins a workflow to a launch) -- the icon sweep's `SweepCase.unlinked` names
that seeded address and asserts it copies and links nowhere. WORKFLOWS' text is a pre-built
`Text` rendered literally (IN FLIGHT's objective precedent), flattened, cut with `…` without
lighting `‹ widen`, and an address is kept whole with its icon or dropped whole. SITES renders content hashes only and is a named exemption in
the icon sweep; its label and `site` columns link to `https://<label>.sites.imd.fun/`
through `address.site_text` (explorer `SITES`, kind `site`). Prefer the API label, use the legacy
ENS-derived label only as fallback, never `site.url`. The `site` column displays the host,
not the retained ENS name; clip the label part before `.sites.imd.fun`, preserving that suffix.
Rows without either valid name show `--` and have no link;
superseded or unnamed rows are omitted -- a feed that leaves nothing reads
`No current site`, an empty feed `No data` (F68). `swarm_site_rows` keeps `superseded_by` for that
filter only; `failure` left the contract (F69), and the label column is one label wide (F67). RECORD's job id is not an address: it links the IMD explorer (not a chain)
through `address.job_text`, with no icon; COLLAB teammate tokens pass through no address helper. The `parked_reason` cell in LAUNCHES clips to its column with a
visible `…` (accepted, `docs/decisions.md`).

**The explorer's own inference headline is deliberately absent**: no public route serves that
number, so this view shows none of it — absent, never estimated.

**Production launches layout (v2):** WORKFLOWS beside
LATEST LAUNCHES; full-width LAUNCHES; full-width SITES. The owner approved the offline v9/v8
fixture render at 150×46 on 2026-10-06; this was not a new live-network measurement. The existing
SWARM pin holds, measured offline across all five layout payloads. The hero's last three cards
show totals and descending whole status/count pairs that fit the box. SITES and its hero count
share `is_current_site`; superseded or unnamed builds are excluded. LAUNCHES and WORKFLOWS keep
one blank footer row. SITES gives one row of its height to a bottom margin, leaving a blank line
above status at the pin. Its label is 32 cells plus layout pad, and its job column uses
`job_text(..., explorer=JOB_EXPLORER)`. Screen and minimal-theme CSS stay identical.

**Rack heroes (2026-10-12):** the approved balanced overview uses six nine-row
cards through `surf_swarm_hero`, reusing `NewsHeroCard`. Overview counts, hourly
accepted steps, workflows, launches and named sites keep independent source clocks.
The hourly source is eligible while the rack or native SWARM is visible. The old
`SurfSwarmHero` is parked. The live 149×45 preview preceded measurement of 141×38;
LATEST WORKFLOW's outer title binds width, while the larger hero adds three rows.

**LATEST LAUNCHES** shows the five newest production launches by `createdAt` descending, with
launch number descending as the tiebreak. It uses the launch tier marker and ages against the
snapshot's `as_of`; Sepolia never appears. Narrow widths shed age, then chain, preserving number
and verdict. A successful empty read says `no production launch yet`; an unread list says
`unavailable`. Enter/click opens that row; **`x` opens the top row's `LaunchDetailScreen`**, or
nothing when no row exists. The hint remains `x more`. The binding stays non-priority so a
focused widget's own binding wins and Input keeps typed text. Snapshot popups use the
`RecordDetailScreen` frame: scrollable content, Space/Escape or X to close, with no network await
while opening. THROUGHPUT is parked in `SWARM_PARKED_WIDGET_SIGNATURES`; its module, popup,
data, clocks and tests remain, as with IN FLIGHT and CAPABILITY.

**Production launches:** `TIER_SWARM_LAUNCHES` runs detached/single-flight at 60 seconds,
120-second launches-route failure backoff. Launches read the newest 100 every cycle; sites refresh every 300
seconds and policies every 1,800. `SLOT_SWARM_LAUNCHES` preserves each route and successful-read
clock independently. `SLOT_SWARM_LAUNCH_FACTS` retains bounded extracted facts, not huge detail
responses, with 500-entry caps. At most three production details and three eligible site jobs
are read per cycle; never-tried details precede oldest failed attempts. Sepolia and abandoned
launches are not enriched. Completed per-contract K3 evidence is reused; an attested contract
without an artifact is not applicable. Checks and indexed site matching run off the UI thread,
and links are memoized on a content hash of matching launch, site/job and workflow inputs;
read clocks, ordering and unrelated evidence do not invalidate it. Failed matching retries unchanged
inputs, logging once per exception type until a success resets the log guard. A previously unseen
policy version or a newly judged wallet mismatch refreshes policies once before judgment; a
failed refresh leaves the check unknown. A persisted policy-schema marker migrates legacy
kindless cached policies only after a successful policies read; live missing-kind policies
retain the 1,800-second TTL. K2 unknown solely because its policy version is unknown waits for
that refresh, then rejudges retained transaction evidence without fetching transactions again.
The cycle snapshots rows/events before spawning work.

Production is chain 1/8453/4663, excluding abandoned. Retained production rows still count and
pin after leaving the newest API window. LAUNCHES keeps 12 production + 12 non-production, newest
number first within each; production is bold with `◆`, other rows dim with verdict `--`. MAINNET / BASE / RH /
SEPOLIA are the chain words. The token column prefers role `token`, then `hook`, then the first
artifact. Full columns include kind/repo and `liq` after verdict. Liquidity outranks
kind, repo and site: roomy sheds kind; compact also sheds repo and site. Tight sheds the
parked reason and restores `liq` when fourteen cells fit after ticker and verdict.
Once visible, liquidity stays at every wider width. Tier onsets live in the measured pin comment.
K2 uses the chain-wide wallet set and factories declared by the launch's own kind; kinds with
no declared factory, including an absent kind, are judged on sender and receipt status alone.
A known policy version must match an explicit launch kind. K6 factory annotation uses that same
kind; an absent kind or no declared factory leaves `owner_is_factory` unknown. Complete receipts
without a ModifyLiquidity log make K6 not applicable. One-time K2/K6 rule migration retains completed K3 contracts. K1–K4 produce provenance-only `✓ swarm`, `… n/4`, or `✗ Kx`; K3 accepts deployed-code equality
or creation-code evidence (`pass (immutables)`). K3 requires at least one verified attested
contract and a verified name match for every token artifact, plus hook artifacts only for
`univ4_hook` launches. The other kinds use the unattested shared hook. All-not-applicable and
unmatched required roles remain unknown. Once every per-contract check is terminal, a coverage
gap retries RPC at most once per 1,800 seconds; a status/updatedAt change resets that back-off. Only admitted launches without artifacts say
`-- pending`; parked launches show a failed check or `-- parked`. Empty admission is K4 unknown,
including legacy cached passes. Parked/admitted launches with unknown K4 retry their detail
after 1,800 seconds even without a version change, within the three-detail budget. K6/K7/K8 are
informational, never safety claims; K8 never contributes to the K1–K4 provenance verdict.
Enter/click opens `LaunchDetailScreen`, a deep-copied snapshot with all artifacts, copy/explorer
links, pair, fee, requester, policy, evidence, site and IMD token/job link. Each check heading
adds a dim plain-language description; narrow widths clip the description before the state.
Sepolia keeps the descriptions with `--` states. Selection messages
are declared in each selectable subclass; BOARD keeps its own Enter routing.

**K8 liquidity** joins a unique token-matching Initialize event to ModifyLiquidity by emitter
and pool ID in the deploy receipts. That emitter supplies the PoolManager address; owner comes
from `topics[2]`. Signed packed ticks and the salt participate in the position storage key.
Pool fee comes only from Initialize, displayed as a percentage (12500 → 1.25%, 3000 → 0.3%);
missing evidence is `--`, never the manifest fee. No pool or complete ambiguous pool evidence is `na`; a missing read
is unknown. Both paired and token decimals are read and cached; only native ETH defaults to 18.

The independent K8 clock batches three state reads per pool, oldest eligible first, at most ten
launches per cycle and once per 300 seconds. Settled legacy facts bootstrap missing receipts
in bounded batches. A provenance batch suppresses bootstrap only for launch receipts it actually
requested, never for every launch on that chain. Immutable pool inputs, validated decimals and
the last result persist in the facts slot. Failed state reads retain the successful result's `read_ts`; a separate attempt
clock backs off failures. The popup shows that result's age against the snapshot clock.

`liquidity` and `checks.K8` share the exact `SWARM_LIQUIDITY_KEYS` shape; Sepolia liquidity is
None. The popup shows paired/token amounts, tick range, fee, owner with explorer/copy actions,
lock and share of active liquidity. Factory holdings are `in factory (unverified)`, never
burned; only zero/dead owners are burned. Non-factory owners are labelled `(contract)` only
when a successful `eth_getCode` confirms code; that read is cached by owner. Failed reads
leave the annotation absent, and no verified-source status is inferred. A position below its deployed liquidity is withdrawn,
with the removed percentage (zero remaining is 100%). Shares cannot exceed 100%. K8 warns for
withdrawal, an edge price (`at limit`), or token-only positions older than one hour. The `liq`
cell shows compact paired amount, dim `one-sided`, yellow `no liq`, red `withdrawn`, `--` for
not applicable, or `…` before a read. None of these market states changes provenance.

SITES uses workflow/project/named matching; named matches require payer agreement to highlight.
Conflicting matches produce no link. Trusted production sites pin first. Their clipped ticker suffix leaves at least four cells for
label text; untrusted suffixes alone are dim. LAUNCHES/SITES use the launch tier marker, not the scores clock.

`SWARM LAUNCH` is detector eleven; signal detail carries its own chain explorer.
`sig_swarm_launch` carries the exact detector-selected WATCH/FIRED launch (and FIRED
`extra_count`), or None for OK/DEAD. Its structured fields reserve the launch number and
verdict ahead of ticker text; address is shed before the extra-launch count. The original
plain detail string remains available to older callers. Persisted
`swarm_live_seen`, its UUID-to-number map and pending IDs cap at 500.
`swarm_launch_evicted_floor` records the highest actually evicted number to prevent replay;
first sightings below an observed high number still fire. Fired facts retain ages through restart
and refresh their ticker/token/verdict metadata on later reads. Initial reads seed silently;
failed or corrupt persisted reads do not fire. Typed fired events drive all-body title news, never parsed detail text.

**WORKFLOWS history:** cold or incomplete caches backfill pages of 100, at most 10 pages, using
strict UTC `createdAt` cursors, an advancing-cursor guard and the existing inter-call delay.
The scores slot persists raw rows plus `workflows_complete`. After completion, sweeps fetch page 1
and merge by workflow identity, fetched values winning, newest timestamps first and unknown last,
capped at 1,000. Failed page 1 returns None on cold start and retains cached last-good otherwise;
a later-page failure retains the pages read and logs it. An older workflow's status change beyond
the newest 100 is seen only on a later backfill. No row shape changes.

WORKFLOWS paints `when · status · contracts · frontend · objective / failure`; a non-completed
failure is red. Enter or a row click posts a snapshot message for `WorkflowDetailScreen`; job-link
clicks open the IMD explorer directly (verified on Textual 8.1.1 and 8.2.8). The popup shows status,
created/updated, both job links, waiting for hosting, objective and failure. Full prose wraps as
literal Text through shared control cleaning and copy-icon helpers; workflow prose has no chain
and therefore no explorer link.

**Title alarms, SWARM only:** tripped exactly True means breaker open; services exactly False
mean one named service or N services down; unknown services are not down. A non-ok health string
is sanitized and capped at 12 cells. The owner approved `health unavailable` for unread health,
because existing manager tests explicitly require no new SWARM degraded group. A title too wide
uses a source count (`src`), compact labels (`par`, `svc`, `ver`/`pub`/`dep`) and omits the redundant
SURF heading; price, parity, `as of`, LP warning, taller marker and every alarm remain. Launch-check mismatches add `⚠ launch #n K3` or `⚠ n launch checks`. Every body also shows accent
launch news for 60 minutes; the detector remains FIRED for 24 hours. Crowded SWARM titles may
use `▲ LAUNCH #n`, tighter separators and shortened health text (owner approved 2026-10-06). KEY_HINTS begins `x more`; `l` stays bound, unlisted like `e`.

CAPABILITY, IN FLIGHT and THROUGHPUT are parked, with modules, tests and reads retained. Every
mounted/consumed exemption comes from `SWARM_PARKED_WIDGET_SIGNATURES`; no current body pin
certifies a parked widget. SWARM's width still binds on SITES and the full status bar. Height
retains the nine-line top floor, the eight-line LAUNCHES floor and seven-line SITES floor plus
its blank bottom margin. LAUNCHES is the content exception: full now includes liquidity; roomy
sheds it before compact drops kind/repo. The measured onsets, no-hidden-column boundaries and
all three body pins remain beside their constants in `screens/surf.py` and enter the boundary
sets in `test_surf_swarm_layout.py`. The offline five-payload sweep preserved SWARM, AGENT and
BOARD pins; the owner approved the 150×46 fixture layout. The original grids remain historical
in `docs/decisions.md` and the appended pin blocks. All eleven active default detector rows
require 43 rows at 143 columns; the mixed fixture needs 39.

**Polish answer reads** (`docs/surf_swarm_polish_handover.md`): RECORD renders
`when · job · node · state · model · took · tok · panel · answer`; objective remains
in the data row for other readers. The answer is the first cleaned sentence from the exact
`work[].submissionHash` in `/jobs/{uuid}/submissions`, never another seat's or a hash prefix.
Markdown link destinations disappear and remaining absolute local paths reduce to basenames,
including quoted/backticked paths with spaces. `file://` is local; bare home roots become `~`
without exposing the user segment. HTTP(S) URLs remain intact. Parse only the first 4,096
characters with linear link scanning and bounded fixed-point stripping. Preserve newline
sentence boundaries before flattening; widgets still sanitize third-party text.

The answer cell distinguishes read, dim `loading…`, `unavailable`, `not served` and `no reply`.
Loading promises a scheduled read: only rows inside RECORD's selected window with a canonical
job UUID and 64-hex submission hash in either case qualify (`_oracle_answer.valid_identity` is
analytics `record_readable`, bound to the data layer's read rule; F-S1). An ineligible `not_read` row keeps
`not read`; malformed identities enriched by the manager are `unavailable`.
Model/took/tok render only for successful matching reads (`read`/`no_reply`); missing values and
other read states use `—` for those metadata cells. Failed/queued rows cannot retain stale
metadata. This model is actual submission usage, independently of worker-advertised models.
`tok` uses `usage.outputTokens`, strictly nonnegative integers: plain integers below 1,000,
then shared `fmt_compact` (`1.5K`, `22.0K`), carrying 999,500–999,999 to `1.0M`.
Exact cleaned Claude/GPT model ids shorten by rule in RECORD and FLEET; FLEET keeps the effort
word only for a nonempty cleaned model. A tag-only model shows `—` without effort. Unknown
model ids remain cleaned text, clipped by their caller.

The detached seat tier reads at most four unique submission jobs per cycle over RECORD's selected
`record_window`; several hashes from one job share one GET. Validate canonical UUIDs before paths;
a submissions 404 stays local to that job. `SLOT_SWARM_ANSWERS` stores extracted fields plus
`read_ts`/`terminal`, capped at 400 points and 48 hours, with strict load and consumption
coercion. Validation drops bad points independently, keeping valid siblings. Stored answers
must satisfy the bounded-string/link/path/control safety predicate, without re-derivation.
Successful terminal results and real negatives (404 or a successfully absent hash) remain
frozen while retained. Transport/parse failures retry after `SWARM_ANSWER_DUE_S`, within the
per-cycle cap, even on terminal jobs. Legacy unavailable/frozen entries become retryable.
Owner-approved persistence change (2026-09-24): a bounded, cleaned reply (≤ 4,096 chars) and
other seats' first lines (≤ 200) persist; never a raw envelope. Reply cleaning preserves indentation,
newlines and box characters, expands tabs, and removes ANSI, other controls, local paths and
Markdown targets. Cuts never end inside a 0x hex run. Other seats exclude the exact own hash,
are sorted by node key/token and capped at eight; oracle siblings are excluded independently,
and oracle nodes do not get other-seat summaries.
Each answer point fits 8,000 bytes in default on-disk JSON encoding, trimming other lines, reply,
failed checks, then answer through the shared oracle/submission budget helper. Partial URL schemes
are removed at cuts so load-time safety remains satisfied. Reply has its own newline-aware
safety check. Old shapes are dropped per point and re-read within the existing four-job cap.

`SLOT_SWARM_JOB_DETAIL` stores bounded job state, blocked reason and up to 16 nodes with
key/role/state/attempt/failure reason, plus `read_ts`/`terminal`. The existing `fetch_job` reads
at most two jobs per seat cycle, from rows eligible for SUBMISSION in the selected `record_window`:
not joined, answer state read/no_reply, valid UUID/hash. Off-panel oracle rows qualify.
A busy `fetch_job` ends the cycle's reads and records no point (F-S3).
Nonterminal results retry after 120 seconds; completed/failed/cancelled are terminal, **blocked
is not**. Cap at 400 jobs/48 hours with the injected clock. Failed reads are unavailable; absent
points have `job_read = "not_read"`. SUBMISSION displays dim `loading…` for these only when
the row meets the job-detail eligibility above; an ineligible row keeps `not read yet`.
Row `job_detail_state` is separate from the original seat `job_state`.
`job_read_ts` retains successful and failed read timestamps; JOB ends in `· as of HH:MM`
through shared `hhmm` whenever a cached point exists. `not_read` has no marker.

**Oracle panel reads** (`docs/surf_oracle_panels_plan.md`): after submission enrichment,
only oracle nodes in the selected `record_window` are eligible. Join list `jobId` to requests,
then confirm `members[].submissionHash`; never join by wallet or infer agreement from price equality.
Different requests for one job or conflicting duplicate member hashes are unavailable.
`SLOT_SWARM_ORACLE_INDEX` keeps validated job/request identities and complete-history boundaries,
without age pruning. Read lists only for unresolved due jobs: forward refresh then backfill share
a cap of four 500-request pages, with strictly validated UTC cursors. A forward gap beyond the
cap discards the index. An empty first page is always a failed read, and a complete index with no entries is
discarded on load (re-review N1). Indexed
jobs go directly to details with `?members=<submissionHash>`; read at most four due request/hash pairs.
Keep the exact-hash and conflicting-duplicate checks even on filtered bodies. With no due rows, make zero requests.
Retained attested/disagreed/blocked points are terminal; assessing or failed points retry after 120 seconds.
Any other nonempty status preserves joined answer facts, shows unavailable and remains nonterminal.
`SLOT_SWARM_ORACLE` retains extracted facts only, at most 400 points for 48 hours and 6,000 serialized
JSON bytes per point. Validate each persisted point; cancellation stores neither partial oracle points nor a partial index.
A failed list/detail keeps prior evidence, or yields `unavail` when no cached point exists.
No new top-level key, clock or degraded group is introduced.

PANEL states: agreed/outvoted show green `✓ agreed/quorum` or red `✗ agreed/quorum`;
with quorum absent show just the glyph and agreed count. `panel_quorum` comes from strict nonnegative
`detail.quorum`; neither filtered member count nor `panelSize` is a submitted-member count.
no_quorum_in/out show dim green/red `✓ no-q` / `✗ no-q` (closed even if STATE says pending);
assessing shows yellow `… of <panelSize>` (`…` if size is absent); blocked is dim
`blocked`, including captured null members; off_panel/not_oracle show dim `–`;
not_read is dim `loading…` for an eligible oracle row in the selected window with a valid
job UUID/hash; ineligible not_read rows keep dim `not read`. Non-oracle rows retain `–`.
Unavailable is yellow `unavail`. Missing required counts are
unavailable. Off-panel requires a complete request index whose newest timestamp covers the row’s
submission, or a final panel without the hash. A page older than submission is never an absence proof.
On non-joined outvoted/no_quorum_out rows, ANSWER prefixes `panel <figure> · `, including unread replies.
Figures retain exact decimal strings. Bool panels instead use strict `agreement.answer` via
`panel_answer_bool`: YES/NO; absent or malformed bool is `unavail`, never inferred from figure.
Full RECORD keeps every column; compact drops tok; tight also drops answer/model/took and keeps panel.
The data row retains role for other readers, but no RECORD tier displays it.

**Joined oracle answers** (`docs/surf_answer_popup_plan.md`): exact member membership plus strict boolean
`member.ok` selects answer.json's own value and notes for RECORD. Invalid values remain `None` without
losing membership. Use the request's answerType: strict bool → true/false (display YES/NO), uint256 →
1–78 decimal digits, address[] → at most 20 validated addresses joined by spaces. Other …[]
types accept at most 20 strings, each fullmatching 0x plus 1–64 hex digits or 1–78 decimal digits.
RECORD shows `N values`; ANSWER lists full values one per line without address icons or links.
Other scalar values are flattened and capped at 200 characters. A `bytes32` value is UTF-8 text
right-padded with zero bytes (the request's own `definitions`): RECORD shows the decoded text,
the popup keeps the hex and prints the text on the line beneath (owner, 2026-09-25). Anything that
does not decode to printable text keeps the hex alone; the cache stores the hex unchanged. Question/reason/notes caps are
1,000/200/4,000 characters;
question and notes keep newlines, other controls are removed. To meet the byte budget, trim notes,
then question, then reason; preserve the value. Off-panel facts are all None; old cache shapes are dropped.
Every joined answer ends in `»`, cut (`… »`) or not (owner 2026-09-24); the button's two cells come out of
the answer's own budget, so no column widens and no pin moves. Cuts do not light `‹ widen`. Only validated
job UUID/hash identities get the button. It opens a cached snapshot in `OracleAnswerScreen`; Space/Escape or
the frame's top-right `X` dismiss to AGENT (Enter does not, owner 2026-09-24). Question,
notes and address[] values use shared address helpers and the row's chain explorer; unknown chains
remain copyable without a link. Opening never fetches; closing uses the normal refresh guard.

**Other submission replies** (`docs/surf_submission_popup_plan.md`): non-joined rows with a valid
job UUID/hash and answer state read/no_reply always get `»` (owner 2026-09-24: every answer, not only cut ones). It opens a
`SubmissionDetailScreen` snapshot of the exact job/hash from the last rendered rows. Unread,
not-served and unavailable replies get no button.
Any row with a popup button is exempt from reply-based `‹ widen`; button-less cuts still mark.
Both popups share `RecordDetailScreen`'s frame, focused vertical scroll and pinned centred footer;
Space/Escape or a click on the `X` at the frame's top right return to AGENT. Job/nodes, objective, this seat's status/usage/checks/findings/artifacts,
reply and up to eight other seats are shown from cache. `local_build_failed` alone gets the excerpt
note. Prose wraps, never scrolls horizontally; addresses use shared helpers without an explorer
because these jobs carry no chain id. Every third-party string reaches Static as pre-built Text.

**Palette:** dim labels, bold counts; green healthy/working/accepted, red offline/paused/down,
yellow unavailable or existing pending counts. Zero working keeps `0 quiet` dim. Rates and
scores and summary counts are bold without thresholds or status colour. SWARM service and health
alarms live in the title; F55 is closed by removing the SERVICES card. BOARD's offline rows are dim, per its own row design;
its hero is unchanged by polish. Every colour assertion uses actual composited styles.

CAPABILITY is parked (2026-10-03) and mounted nowhere, so no pin certifies it now: its tier
widths and its optional `inf` / `acc/att` onset were last measured in situ on SWARM (its own
`swarm_capability.py` docstring records where) and the board that mounts it re-sweeps them on its own geometry; `CAPABILITY_OPTIONAL_FULL_COLUMNS`
and its sweep were retired with it. WORKFLOWS' ladder (full / compact sheds `frontend` / tight
sheds `when` too) is certified in situ on SWARM, each onset in the layout test's boundary set. RECORD's committed enriched
v4 first 40 button-less submission-message fallback clears at `RECORD_NEVER_CLEARS_BELOW`; one column below clips the informative answer.
Rows with ANSWER or SUBMISSION buttons are exempt: their popup replaces the reply widen marker.
The build reply from work index 125 is outside that displayed-window measurement.


## BOARD (`b`, MODE_BOARD)

Canonical records, contributors and workers retain independent values and read markers. BOARD ranks only the validated recorded-seat population; failed work is distinct from pending work. FLEET's
EFFORT / RECEIPTS group (owner, 2026-09-22) has a blank row under its sub-header, then devices ·
seats, accepted of attempts, rejected · pending, turns · wall-clock hours (rounded; `N min` under half an hour, F64) and input · output
tokens (compact), then tokens/job; each line's first value unread is the whole line
`unavailable`, a missing second value is omitted, and a pair too wide keeps its first value
plus `+N`. The input/output sums are `None` when any row does not serve them. LEADERBOARD's
table has a 1-cell left margin and a 1-cell scrollbar (`GUTTER_COLS` stays 2). A missing source is
unavailable; an empty worker metadata mix says none reported. LEADERBOARD retains every seat in the canonical records snapshot,
marks the selected AGENT token with `▸`, and Enter validates through `parse_seat`, calls the
shared `config.save_seat`, then reuses `_seat_entered` (set_seat, mode, scheduled refresh;
no network await in the event handler). Rendered row identity is token metadata, never clipped
text or a raw-payload index. FLEET fits whole sanitized values and counts omissions with `+N`.
Long runtime names use an explicit ellipsis/widen content exception; fixed counters cannot
clip at the full-layout pin. BOARD's measured guarantees live beside its pins in screens/surf.py.
FLEET uses fixed-width dim labels, grouped metadata, bold counts and an explicitly advertised
model mix, with workers in its title clock and contributors in a separate sub-header. A worker
counts once per distinct model/effort pair, including an explicit none bucket; multiple pairs
can make the model-count sum exceed LIVE. Paused none is green; a paused count is red.

Every LEADERBOARD column sorts through its header; repeated clicks reverse. BOARD-only `o`
cycles all columns and `O` reverses, without changing KEY_HINTS. Sort is stable on raw values,
None is last in both directions, global rank is immutable and the cursor follows its token
across refresh, resize and re-sort. Header clicks never select or persist a seat. Selected
rows are bold with an accent rank; working is green, paused red, unavailable yellow and the
whole offline row dim. Colour is checked on composited cells, including under the cursor.
BOARD uses `SURF_BOARD_FULL_LAYOUT_COLUMNS` × `SURF_BOARD_FULL_LAYOUT_ROWS`, with grouped
FLEET and paused detail binding height. The constants and their `#:` blocks own the measurements.
The existing global market title remains unchanged; source clocks belong in BOARD content.

Parked IN FLIGHT keeps the folded dispatch/failure note as its last column; these constraints apply when it returns. Actual note clipping
lights widen in every tier; a fitting literal ellipsis does not. Full tier is a column
guarantee, not a promise that arbitrary notes fit; measured content limits are in surf.py.


## SURFBOARD HUB (dashboard 9)

`surfboard` is a separate DashboardScreen using the same SurfManager and installed SurfScreen.
The title is centered muted gray `IMD BOARDROOM`. ONCHAIN FEED uses white active inset
borders and border text, matching its body; SWARM BUILDS retains its activity colors.
Seven launchers route to the native modes; Escape returns to the retained rack, while menu/Tab
clear the return context. TOKENS opens the retained SWARM TOKENS dashboard. Its LAST 24h
inset ranks the top three supported, unambiguous deployments by selected-pool 24h USD volume,
with one leading blank in each token row and price arrows aligned at the right edge,
including inactive deployments. Chain/address aliases share their earliest known launch time;
only ages from zero through less than 24 hours qualify. Missing volume never means zero.
Valid cached volumes stay in the ranking across rotating quote batches; retained stale inputs
mark the ranking stale rather than temporarily replacing its leaders with fresh lower volumes.
Green ↑ and red ↓ compare consecutive successful prices for the same token and expected/selected
pool; first, unchanged or stale prices show no marker. Fresh rows retain their direction
even when other ranked evidence is stale; a stale catalogue suppresses all directions.
The outer footer shows gray `24h` beside a green USD-volume history across all swarm tokens,
including older and inactive launches. It reuses the bounded hourly-volume reader and eight
three-hour buckets; missing intervals stay gaps. Tooltip coverage and clocks remain explicit.
Hub polling offers catalogue, shared selected markets and bounded volume history; price-history
and trade readers are unchanged.
The inset footer shows positive `x new` from the eligible canonical last-24-hour population.
Per the owner, no partial/stale/clock labels appear there; the literal tooltip retains coverage
and source clocks. Known zero-new text remains hidden on TOKENS and ONCHAIN FEED.
Portfolio opens its existing preview. LEADERBOARD shows TOP AGENTS with three canonical ranked
seats and accepted counts, led by gold/silver/bronze stars with one leading blank. Counts align
right with one trailing blank; oversized counts drop grouping, then use compact notation only
if necessary. Its activity footer remains rank one's.
Empty AGENT insets use a borderless `seat number` input, centered ↑ and `type in`; their outer
footer is centered `Identity.md`. Three-line gaps below ORACLES and PROTOCOL separate them
from the AGENT seats; regular-weight キープ / ビルディング match the muted card-footer
labels and are centered on the middle line.
Other card gaps remain one line; all card sizes stay equal.
The terminal hides automatic stale labels (including generated command summaries) and V/P/D
service flags at every width, per the owner; underlying metadata and unavailable states remain.
It supports bounded read-only commands and replaces its recent `/swarm` event window
without duplicating events or losing replies, draft or scroll anchor. Source polling and full
collection are manager-owned single-flight tasks; only the hub skips the startup prefetch join.
Acceptance/rank in HUB, AGENT and BOARD come from one complete `/seats/records` snapshot
(`attempts = accepted + rejected + failed + pending`, unique IDs, matching count). Invalid reads
retain the prior whole snapshot as stale. Upstream summary cache ≤600s is disclosed. Contributors
remain effort/receipts; workers remain presence; detail responses never overwrite shared totals.
AGENT and LEADERBOARD outer footers track selected/rank-one worker activity independently:
orange BUSY with a full green bar; gray IDLE drains green to orange over 24 hours,
then orange to empty over hours 24–72. Offline is red OFF with empty segments.
Every successful workers read refreshes activity evidence even when content is unchanged;
failed/stale/unknown evidence has no live bar. Persisted per-token stop history is validated
on load. Cached own-work `submittedAt` can seed or advance an idle anchor when
polling missed the work; a newer observed stop wins. Heartbeat, acceptance and
feedback timestamps cannot reset it. Without either source, cold idle has a dash,
not a full orange bar. The last green segment remains until the full 24h expires.
PROTOCOL uses label / amount / IMD columns, neutral inset borders/title, and a centered
outer `x% burned` footer. POOL4's inset borders/title/USD label compare consecutive valid
USD price reads: green up, orange down, neutral on first or unchanged reads. Source clocks
prevent cached repaints from clearing direction; failed/stale/missing reads do not advance
the baseline, and network/pool changes reset it. The session-local comparison is independent
of the 24h change retained in detail. POOL4's outer footer reuses the protocol's live sIMD
share price, rounded to fit; card detail retains six decimals and source freshness.
Rank migration resets only contributor-based baselines (`seat-records-v1`). See the hub PRD
and implementation plan for exact meter formulas, commands and source cadence.

## ORACLES (`Ctrl+o`)

ORACLES is a separate native mode, opened with `Ctrl+o` from Surf or the boardroom,
or through the ORACLES card replacing LAUNCHPAD. The card uses ASSESSING digits,
`n loaded` inside and `n attested` outside. Fresh positive counts paint orange; zero,
stale and unavailable paint neutral. Counts cover loaded rows, with page-cap/partial
coverage and the source clock in the tooltip; stale counts have a dated subtitle.
The boardroom shares the list reader without selected-detail reads. Either visible
consumer keeps list polling eligible; only native ORACLES enables selected details.
Its six rack cards and 66/34 request/detail body consume only `surf_oracles`.
The reader has an independent 60s list tier and 120s failure backoff; only the selected
request's details load, capped at 64 members with an eight-request LRU. Existing AGENT
filtered reads stay unchanged. Direct validated `tokenId` identifies a member's seat;
the exact submission hash joins canonical RECORD oracle facts. No wallet-to-seat guess.
The complete cached RECORD row drives the existing OracleAnswerScreen without reads.
List and detail have separate clocks; terminal details expire for freshness after 24h
or a row version change, retaining bounded stale last-good data until replacement.
Unknown statuses (including mismatch) remain visible; hero counts describe loaded rows.
Native Tree handles nested click/Space folding. Width/height pins are documented beside
`SURF_ORACLES_FULL_LAYOUT_{COLUMNS,ROWS}`. See `docs/surf_oracles_PRD.md` and plan.

## WORK IN PROGRESS (`w`)

The approved tree/detail body is `MODE_WORK`, reachable from Surf and the boardroom.
It shares SurfScreen and SurfManager; no new top-level game registration. Six rack heroes
and the body consume only `surf_work`. The work reader owns a separate 60s cache tier,
120s failure backoff, fresh 100-job/100-workflow pages and at most 24 detail reads.
The boardroom card and visible Work body share that reader; it cancels when
neither consumer is visible. No history merge or
unrelated Surf collectors run on its refresh path. Busy stops detail fanout and retains
the previous snapshot; missing individual details remain explicit partial coverage.

Counts apply to loaded jobs/workflows and every working node of executing jobs. Seats
are distinct assigned token IDs; missing executing details make step/seat counts unknown.
Creation age never claims execution duration. Current node state controls activity,
even when an older verdict says accepted. Job and workflow states have separate meanings.

The boardroom replaces PORTFOLIO with WORK IN PROGRESS. Its ACTIVE JOBS digits
and workflow subtitle share `surf_work.summary`; `work_summary` carries the
build/review footer counts. Unknown values remain em dashes; stale counts retain
an explicit timestamp. Coverage and read details remain in the card tooltip.
Click/Enter opens Work and Escape returns to the retained boardroom.

The tree groups workflow jobs and steps, then other unfinished jobs. Selection and
collapsed branches survive refreshes. Local `/` search and `f` filters preserve parents;
heroes remain unfiltered. Enter focuses details, and Escape closes search before leaving.
Addresses in objective/dependency/note prose use copy helpers without a guessed chain;
job IDs link to the existing job explorer. See `docs/surf_work_PRD.md` and plan.
