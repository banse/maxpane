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

# surf — the Surfboard dashboard and its four swapped bodies

Key history and withdrawn statements are in `docs/decisions.md`; this file states only what is
true now. Layout pins live beside their constants in `#:` blocks; the terminal-layout skill's
table names them and this file repeats no numbers.

## Keys and bodies

Surf is position 1, the `--game` default, and the dashboard prefetched at launch. Its status
hint reads `l launchpad · 4 pool4 · s swarm`, in one markup run (adjacent differently-styled
runs never share a composited line; the acceptance test greps for the whole phrase), read back
off composited output against `StatusBar`'s left-label budget. `l launchpad` must never shorten.

A **mode** is a whole second body with its own panels, never two panels sharing one slot. Each
of the four swaps `#middle-row`/`#separator`/`#bottom-row`, `escape` backs out one-way, and none
is a new dashboard (no six-surface renumber; `app.py`, `__main__.py`, `GAMES` untouched):

| key | mode | body | hero |
|---|---|---|---|
| `l` | MODE_LAUNCHPAD | LAUNCHPAD COINS over LAUNCHPAD ACTIVITY left; CURVE FLOW / BURN PIPELINE / BURNKEEPERS in the rail | `SurfHero` stays |
| `e` | MODE_POOL4 (protocol, experimental, not on the bar) | THE SPLIT over THE RATCHET left; HATCHES over sIMD VAULT in the rail | `SurfHero` stays |
| `4` | MODE_POOL4_USER (market) | RECENT FLOW beside BURN & SUPPLY over SIGNALS; STAKERS beside IF IMD FALLS | `SurfPool4UserHero`: IMD PRICE / DOWNSIDE BID / STAKING |
| `s` | MODE_SWARM | THE FIELD beside a rail of QUEUE over THROUGHPUT; JUST SHIPPED full-width beneath | `SurfSwarmHero`: AGENTS / IN FLIGHT / ACCEPTED TODAY |

`_SURF_HERO_MODES` **enumerates** the modes that get `SurfHero` rather than negating one: a body
with a hero of its own would otherwise inherit `True` from a `!=` check and paint two heroes into
one row. A second hero widget is composed once at startup and toggled with the body — curator's
per-mode hero, not one widget with a mode branch. Surf's `e` and curator's `e` (export), and the
two `l`s, are separate bindings on separate screens. The feed threads replies behind an
expand/collapse toggle, with NEW REPLY on the rail so a collapsed thread still announces itself.

## Tiers, clocks and degraded groups

`TIER_LAUNCHPAD`, `TIER_POOL4`, `TIER_POOL4_STAKERS` and the two swarm tiers are spawned and never
awaited, each with its own last-good slot and its own `as of HH:MM` on a slower clock than the
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

**Three hero cards, not four**: surf's own hero already says `BURN` and `SUPPLY`, and a pool4
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

## SWARM body (`s`, MODE_SWARM)

Answers what the IMD swarm — the agent workforce this repo's own branches are built by — is doing:
who is online, what each seat is working on and why it is stuck, what shipped, how fast work
moves. It reads **one** keyless third-party host, the swarm's control plane
(`docs/imd_swarm_api.md`): `data/surf_swarm_client.py` is the HTTP layer and nothing else;
`data/surf_swarm.py` is the pure fold — no network, no clock, no Textual.

**The job list is gated on `/health`'s own counters.** The live tier reads `GET /health` every
run. `GET /jobs` (~27.5 KB, one shot, no pagination, no ETag or version) is re-fetched only when
one of the host's counters (`connectedDaemons`/`activeEnrollments`/`workingNow`/
`acceptedLastDay`, every `pending*`) has moved since the manager last saw them, or when a ceiling
has elapsed regardless — curator's `(version_id, content_hash)` precedent one size down.
`GET /jobs/{id}` follows for every non-terminal job (the only source of agent attribution,
subtasks and dispatch notes); a 404 on one drops that row, not the read. A slower tier sweeps
every detail plus `/launches` and `/sites` on its own clock, feeding score and throughput only.
QUEUE renders `PENDING` plus the summed total and only the nonzero named counters, gated on the
same as-of marker `_is_unavailable` uses; a dict of real zeros still renders (`PENDING 0`).

**The explorer's own inference headline is deliberately absent**: no public route serves that
number, so this view shows none of it — absent, never estimated (FWA's uncovered collections and
pool4's NFT floor follow the same rule).

Pins: `screens/surf.SURF_SWARM_FULL_LAYOUT_{COLUMNS,ROWS}`, each `#:` block naming the binding
panel (`SWARM_TOP_ID` for rows since QUEUE's counter block landed) and the sweep. THE FIELD wraps
its objective line instead of clipping it, with a shed marker when a continuation is dropped.
