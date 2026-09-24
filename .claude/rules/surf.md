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
| `l` | MODE_LAUNCHPAD | LAUNCHPAD COINS over LAUNCHPAD ACTIVITY left; CURVE FLOW / BURN PIPELINE / BURNKEEPERS in the rail | `SurfHero` stays |
| `e` | MODE_POOL4 (protocol, experimental, not on the bar) | THE SPLIT over THE RATCHET left; HATCHES over sIMD VAULT in the rail | `SurfHero` stays |
| `4` | MODE_POOL4_USER (market) | RECENT FLOW beside BURN & SUPPLY over SIGNALS; STAKERS beside IF IMD FALLS | `SurfPool4UserHero`: IMD PRICE / DOWNSIDE BID / STAKING |
| `s` | MODE_SWARM | CAPABILITY beside THROUGHPUT; IN FLIGHT beside LAUNCHES; SITES full-width beneath | `SurfSwarmHero`: AGENTS / WORKING / ACCEPTED 24h / QUEUE / BREAKER / SERVICES |
| `a` | MODE_AGENT | seat-card row with COLLAB/NODES; RECORD full-width beneath | `SurfSwarmAgentHero`: SEAT / WORK / ACCEPTED / REVIEWED / RANK / STATUS |
| `b` | MODE_BOARD | Lifetime LEADERBOARD beside FLEET | `SurfSwarmBoardHero`: SEATS / LIVE / PAUSED / CAPACITY / ACCEPT RATE / RECEIPTS |

`SurfHero`'s fourth box is BOARDS (owner, 2026-09-22; it replaced IMD SUPPLY): `hero.BOARD_KEYS`
lists `a`/`b`/`s`/`4` in THE LIST filter card's shape, and an agreement test binds each key to
its `SurfScreen` binding. `imd_supply` is still read and no widget shows it. The `minimal`
tier writes `b leaderboard` (13 cells, no quotes or dash) so the hero's marker stays dark at 87.

`_SURF_HERO_MODES` **enumerates** the modes that get `SurfHero` rather than negating one: a body
with a hero of its own would otherwise inherit `True` from a `!=` check and paint two heroes into
one row. Every alternate hero widget (`4`, `s`, `a`, `b`) is composed once at startup and toggled with the
body — curator's per-mode hero, not one widget with a mode branch. `_SCROLL_COLUMNS[mode]` names
the containers whose scrolling lights `‹ taller`; every swarm and agent container that can scroll
is registered there, bound by the layout test. Surf's `e` and curator's `e` (export), and the
two `l`s, are separate bindings on separate screens. The feed threads replies behind an
expand/collapse toggle, with NEW REPLY on the rail so a collapsed thread still announces itself.

## Tiers, clocks and degraded groups

`TIER_LAUNCHPAD`, `TIER_POOL4`, `TIER_POOL4_STAKERS` and the four swarm tiers (`TIER_SWARM`,
`TIER_SWARM_SCORES`, `TIER_SWARM_SEAT`, `TIER_SWARM_BOARD`) are spawned and never awaited, with independent last-good slots and their own `as of HH:MM` on a slower clock than the
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

**Three hero cards, not four**: surf's own hero said `BURN` and `SUPPLY` when this was decided, and a pool4
card called BURN would show hook trim burns, so burn lives in the chart panel.

**`SurfPool4Flow` lives in this body only** (since 2026-09-14). `_do_refresh` dispatches RECENT
FLOW with `self.query(SurfPool4Flow)` rather than `query_one` — `query_one` does **not** raise on
multiple matches in this Textual version, it returns the first — and the loop stays. The
per-instance keywords (`quiet_mainnet`, `quiet_as_of`, `classes="market"`) are vestigial and
filed as F15 in `docs/surf_pool4_followups.md`.

**No panel on this body renders an `as of` marker.** STAKERS instead gains `stale` in its
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
WP0–WP7). It reads **one** keyless third-party source under two names (`SWARM_API_HOSTS`:
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
run. `GET /jobs` (one shot, no pagination, no ETag) is re-fetched only when one of the host's
counters (`connectedDaemons`/`activeEnrollments`/`workingNow`/`acceptedLastDay`, every `pending*`)
has moved since the manager last saw them, or when `SWARM_LIST_CEILING_S` has elapsed regardless.
`GET /jobs/{id}` follows for every **executing** job (plan §1.5; a 404 drops the detail, never the
row or the read). The slow tier (`TIER_SWARM_SCORES`) sweeps the newest `SWARM_SWEEP_CAP` details
plus `/skills`, `/launches` and `/sites` on its own clock and feeds CAPABILITY, LAUNCHES, SITES and
the internal seat-selection fold; `swarm_throughput` is folded off the **live** slot because its widget shows
the live marker (two clocks never meet behind one `as of`). A third slot, `SLOT_SWARM_JOBS_SEEN`,
is a map of every job either tier has read (pruned by age and cap, stored only when it changed so
the 60 s tick does not rewrite the cache file for nothing): it is the sole source of `completed_24h`
and retains nodes for the internal most-active-seat selection after the host's window moves past them.

**The AGENT body shows one seat's lifetime record** (`docs/surf_agent_seat_details_handover.md`).
`i` saves the selected token; without one, `choose_seat` uses the most active seat from the internal
job-data roster. ROSTER and FEEDBACK are retired, along with Enter-on-roster selection,
`select_seat` and the cursor path. The roster remains an internal fold, not an emitted contract key.
`GET /seats/{tokenId}` runs on `TIER_SWARM_SEAT`, one seat per cycle. `set_seat` only marks that
tier due, with no network await in a handler. Its unchanged single-token slot prevents seat A's
numbers appearing under seat B: `swarm_seat_state` is `"pending"` until B's read lands.

Hero WORK reads turns, lifetime output tokens and hours (in that line order, owner 2026-09-25) from `/contributors` through
`swarm_seat_contrib` and `_swarm_seat.work_body`. Input and cached-input tokens are excluded;
missing output tokens say `-- tokens`. WORK and RANK distinguish `not listed` from
`unavailable` independently of the seats state. ACCEPTED combines `accepted of attempts`
with the bold percentage on line 2; zero attempts displays `no attempts`, while a missing
counter displays `unavailable`. There is no `of attempts` caption and no hero `as of` line:
RECORD's title retains the seat read's freshness marker. STATUS's third line is the newest activity (owner,
2026-09-22): `worked MM-DD HH:MM` (summary `last_worked_ts`, the newest `work[].submittedAt` of
any status) when it is newer than `last_won_ts` or nothing was accepted, else `accepted MM-DD
HH:MM` (the newest `work[].acceptedAt`). Feedback `reviews[].sentAt` is a separate timestamp, never seat activity. STATUS reads worker
capacity/pause/offline independently of seats, with a bare `STATUS` title (its worker clock
was removed by the owner on 2026-09-22) and exactly three body lines. `swarm_seat_live.live_state` preserves unknown pause evidence as unavailable (F48);
known zero working is idle, which STATUS writes as a green `● online` (`ONLINE_LINE`; only
that part green, the counts after it dim); STATUS writes `⚙` (`WORKING_GLYPH`) for the word
"working" in its counts (owner, 2026-09-22). RANK (hero column 5 since 2026-09-22) reads only
`swarm_seat_contrib` through `_swarm_seat.contrib_body` / `rank_body`. RANK's second line is
`swarm_seat_rank_delta`: previous rank minus current rank, green `▲N` upward or red `▼N`
downward. `SLOT_SWARM_SEAT_RANK` persists each seat's `{rank, prev}`; validate each point on
load, update only on an observed valid rank change and keep the delta through unchanged
reads. A first observation has no delta; unranked/unavailable/not-listed reads show none and
leave history unchanged. A bad seats state hides its accepted date without hiding valid worker facts.
AGENT has one seat-card row in `widgets/surf/swarm_agent_cards.py` below its hero and above
RECORD. `SurfSwarmSeatCards` shows OWNER (address/verified ENS via `address_text` and package
`EXPLORER`, paired stamp), RUNTIME (runtime, daemon, devices), SCORE (mean, scored, differing
entries), FEEDBACK (sent/submitted/queued), COLLAB and NODES. Both rows use the same column
weights with a blank row between. NODES sits under STATUS.

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
An outdated runtime or differing daemon is yellow with a trailing ` ↑`; reserve its two
cells within the existing fit budget. All other lines retain their old rendering. The RUNTIME
box tooltip is a literal `Text`: npm latest/version/check time, fleet reference/count, or
`update check pending` (runtime id absent from `swarm_runtime_latest`: not yet checked),
`update check unavailable` (a checked version of None: the read failed), `runtime not checked`,
`no fleet majority`; a pending, unknown or unavailable seat has no tooltip. No new workers read,
no new degraded group, no pin change.

COLLAB keeps its collaborator count and adds the top two teammate tokens, ordered by shared
jobs descending then token ascending; bold `#token`, dim `×N`, never `+N more`. An empty
list says `none yet`, an unread list `unavailable`, below the count.
NODES reads `swarm_seat_node_rows`: include attempts > 0 or accepted > 0, sorted by accepted
descending, attempts descending, `NODE_TITLES` order, then key. Each line is dim node name,
bold accepted count (green above zero) and bold `fmt_win_rate(accepted / attempts)`; missing
or zero attempts show `—`. Known names are ORACLE/REVIEW/BUILD, unknown keys retain their
flattened, fitted text with a visible `…`. Up to three nodes show in full; more show two and
`+N more`. Empty is `no nodes yet`, unread is `unavailable`. Counts shorten through the
honest forms in `_swarm_seat.py`: `fmt_int`, `fmt_compact`, whole K/M, never a clipped number.
Pending/unavailable gate all seats-backed cards; never paired is said once in OWNER, with
dashes elsewhere. Runtime, daemon and ENS names retain explicit ellipsis fitting.

The third card row and `SurfSwarmNodeCards` module are removed (owner, 2026-09-24): ROLES,
per-node chain counts and short role names, OTHERS and the contributor BOARD counts leave
AGENT. Their payload facts remain. `rank_body` and `contrib_body` still supply the hero's
RANK independently of seat availability; unused `board_body` is deleted. Worker metadata
remains in the separate BOARD body; STATUS supplies AGENT's liveness.

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
except completed, including None. `record_window` filters first, then clamps the view to
40..400 and takes its rows. Older counts are after filtering; empty filtered views say
`no incomplete records`, unread remains unavailable.
`screen.record_more()` adds 20 to screen-owned `record_cap` (initially 40, maximum 400),
keeping cursor and scroll position. Its footer target is bold dim `more`; at the cap only
the remaining older count stays. Both actions call the I/O-free `SurfManager.set_record_view`,
which stores cap/open_only and marks `TIER_SWARM_SEAT` due, repaint cached rows, then schedule
the usual guarded refresh. No handler awaits network. A seat change resets 40/all in manager
and screen; the view is not persisted, and filter toggles keep the cap.

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
`EXPLORER` by the decision above. SITES renders content hashes only and is a named exemption in
the icon sweep; its ens column links a `<label>.site.identitymd.eth` name to
`https://<label>.site.identitymd.eth.limo/` through `address.site_text` (explorer `SITES`, kind
`site`; owner 2026-09-23), and it leaves out superseded rows and rows with no ENS name -- a feed that leaves nothing reads
`No current site`, an empty feed `No data` (F68). `swarm_site_rows` keeps `superseded_by` for that
filter only; `failure` left the contract (F69), and the label column is one label wide (F67). RECORD's job id is not an address: it links the IMD explorer (not a chain)
through `address.job_text`, with no icon; COLLAB teammate tokens pass through no address helper. The `parked_reason` cell in LAUNCHES clips to its column with a
visible `…` (accepted, `docs/decisions.md`).

**The explorer's own inference headline is deliberately absent**: no public route serves that
number, so this view shows none of it — absent, never estimated.

Pins: `screens/surf.SURF_SWARM_FULL_LAYOUT_{COLUMNS,ROWS}` (CAPABILITY binds the width; the top
row's `min-height` is a floor equal to THROUGHPUT's own fixed line count, so the row pin is the
body's three rows of content and not a `1fr` split) and `SURF_AGENT_FULL_LAYOUT_{COLUMNS,ROWS}`
(card rows above RECORD on one column grid; the seat row's OWNER binds the width; RECORD's floor is 6; the measured binding content lives in each pin's `#:` block).
Named permanent exceptions, each
with a measured clearing width in the `#:` block and in the layout test (`INFLIGHT_NEVER_CLEARS_BELOW`,
`LAUNCHES_NEVER_CLEARS_BELOW`, `LAUNCHES_HIDES_NO_COLUMN_FROM`, `RECORD_NEVER_CLEARS_BELOW`):
IN FLIGHT and LAUNCHES share a 4fr:5fr row measured so LAUNCHES hides no table column from below
the pin up; RECORD's elastic `answer` column keeps `‹ widen` lit only when its cleaned reply
actually clips and has no popup button. The button-less capture's clearing width is recorded
beside its constant. Heroes are part of the tested whole-body states; their clipped boxes fail those sweeps. F55 separately
records the mixed SERVICES combinations which still clip and are not a whole-state guarantee.
The original swarm grid decisions remain recorded in `docs/decisions.md`; the old A1 agent-grid
arithmetic is historical (F32). AGENT now has its hero and one seat-card row above elastic RECORD.


**Polish answer reads** (`docs/surf_swarm_polish_handover.md`): RECORD renders
`when · job · node · state · model · took · tok · panel · answer`; objective remains
in the data row for other readers. The answer is the first cleaned sentence from the exact
`work[].submissionHash` in `/jobs/{uuid}/submissions`, never another seat's or a hash prefix.
Markdown link destinations disappear and remaining absolute local paths reduce to basenames,
including quoted/backticked paths with spaces. `file://` is local; bare home roots become `~`
without exposing the user segment. HTTP(S) URLs remain intact. Parse only the first 4,096
characters with linear link scanning and bounded fixed-point stripping. Preserve newline
sentence boundaries before flattening; widgets still sanitize third-party text.

The answer cell distinguishes read, `not read`, `unavailable`, `not served` and `no reply`.
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
Nonterminal results retry after 120 seconds; completed/failed/cancelled are terminal, **blocked
is not**. Cap at 400 jobs/48 hours with the injected clock. Failed reads are unavailable; absent
points are not read. Row `job_detail_state` is separate from the original seat `job_state`.
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
not_read is dim `not read`, unavailable is yellow `unavail`. Missing required counts are
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
Other scalar values are flattened and capped at 200 characters. Question/reason/notes caps are
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
scores and QUEUE counts are bold without thresholds or status colour. SWARM SERVICES keeps
explicit up/down/unreported words and a separately served health word; its pre-existing mixed-state clipping is F55. The new
health row fits the existing hero height. BOARD's offline rows are dim, per its own row design;
its hero is unchanged by polish. Every colour assertion uses actual composited styles.

CAPABILITY keeps its original seven columns at `SURF_SWARM_FULL_LAYOUT_COLUMNS`. The optional
full tier adds `inf` and `acc/att` from `CAPABILITY_OPTIONAL_FULL_COLUMNS`; just below that
onset only those two fields are shed. Its widen marker remains honest below the onset. Layout
tests permit only these optional omissions and still require all original columns, no original clipping and no horizontal table scroll. RECORD's committed enriched
v4 first 40 button-less submission-message fallback clears at `RECORD_NEVER_CLEARS_BELOW`; one column below clips the informative answer.
Rows with ANSWER or SUBMISSION buttons are exempt: their popup replaces the reply widen marker.
The build reply from work index 125 is outside that displayed-window measurement.


## BOARD (`b`, MODE_BOARD)

Contributors and workers retain independent values and `as of` markers. FLEET's
CONTRIBUTORS group (owner, 2026-09-22) has a blank row under its sub-header, then devices ·
seats, accepted of attempts, rejected · pending, turns · wall-clock hours (rounded; `N min` under half an hour, F64) and input · output
tokens (compact), then tokens/job; each line's first value unread is the whole line
`unavailable`, a missing second value is omitted, and a pair too wide keeps its first value
plus `+N`. The input/output sums are `None` when any row does not serve them. LEADERBOARD's
table has a 1-cell left margin and a 1-cell scrollbar (`GUTTER_COLS` stays 2). A missing source is
unavailable; an empty worker metadata mix says none reported. LEADERBOARD retains every seat,
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

IN FLIGHT keeps the folded dispatch/failure note as its last column. Actual note clipping
lights widen in every tier; a fitting literal ellipsis does not. Full tier is a column
guarantee, not a promise that arbitrary notes fit; measured content limits are in surf.py.
